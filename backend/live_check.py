"""Live forward test: ask the running app for a signal every minute, wait for that candle to close, score it.

    python live_check.py --source po      --minutes 30 --token <session token> --admin-key <ADMIN_KEY>
    python live_check.py --source binance --minutes 30 --token <session token>

For each minute:
  1. GET /signal from the running backend (the real app) -> pair, BUY/SELL, entry & expiry time.
  2. Run the new v3 engine on the same live prices and record its pick for the same entry candle.
  3. When that candle has closed, look up the price at entry and at expiry and score both:
     BUY wins if the price went up, SELL wins if it went down (equal = draw, not counted).

--source po      : prices come from the backend's own Pocket Option feed (GET /admin/market-snapshot), so no second
                   Pocket Option connection is opened. Pocket Option candles are one price per minute: the price at
                   entry is the close of the minute before the entry candle, the price at expiry is the entry candle's close.
--source binance : the backend runs in crypto mode; candles come from Binance's public API.
Nothing here trades; it only reads prices.
"""

import argparse
import csv
import os
import sys
import time
from datetime import datetime, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import signal_v3 as v3  # noqa: E402

BINANCE = "https://api.binance.com/api/v3/klines"
BINANCE_SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "XRPUSDT", "DOGEUSDT", "LTCUSDT", "LINKUSDT", "SOLUSDT", "BCHUSDT"]


class Prices:
    """Where prices come from, for scoring and for the v3 engine's input."""

    def __init__(self, source, api, admin_key):
        self.source, self.api, self.admin_key = source, api, admin_key

    # --- Pocket Option, via the backend's live cache --------------------------------------------------------
    def snapshot(self):
        r = requests.get(f"{self.api}/admin/market-snapshot", headers={"X-Admin-Key": self.admin_key}, timeout=15)
        r.raise_for_status()
        return r.json()["pairs"]

    # --- each engine's pick on the same prices (best pair = highest confidence) ----------------------------
    def picks(self, engines=("v3", "v3-reversion")):
        from analysis import SignalAnalyzer
        series = self.series()
        out = {}
        for eng in engines:
            best = None
            for pair, closes in series.items():
                w = closes[-150:]
                if len(w) < 60:
                    continue
                a = SignalAnalyzer.analyze_pair({"symbol": pair, "closes": w, "current_price": w[-1]}, engine=eng)
                if a and (best is None or a["confidence"] > best[2]):
                    best = (pair, "BUY" if a["direction"] == "CALL" else "SELL", a["confidence"])
            out[eng] = best
        return out

    def series(self):
        if self.source == "po":
            return {p: [c for _, c in rows] for p, rows in self.snapshot().items()}
        series, now_ms = {}, time.time() * 1000
        for s in BINANCE_SYMBOLS:
            rows = requests.get(BINANCE, params={"symbol": s, "interval": "1m", "limit": 151}, timeout=10).json()
            series[s] = [float(r[4]) for r in rows if r[6] < now_ms][-150:]
        return series

    def v3_pick(self):
        if self.source == "po":
            series = {p: [c for _, c in rows] for p, rows in self.snapshot().items()}
        else:
            series = {}
            now_ms = time.time() * 1000
            for s in BINANCE_SYMBOLS:
                rows = requests.get(BINANCE, params={"symbol": s, "interval": "1m", "limit": 151}, timeout=10).json()
                series[s] = [float(r[4]) for r in rows if r[6] < now_ms][-150:]
        best = None
        for pair, closes in series.items():
            r = v3.analyze(closes[-150:])
            if r and r["direction"] and (best is None or r["confidence"] > best[2]):
                best = (pair, "BUY" if r["direction"] == "CALL" else "SELL", r["confidence"])
        return best

    # --- entry / expiry prices for a pair and entry minute (None = not available yet) ----------------------
    def entry_exit(self, pair, entry_ms):
        if self.source == "po":
            rows = dict((int(t), c) for t, c in self.snapshot().get(pair, []))
            e = entry_ms // 1000
            if e in rows and (e - 60) in rows:
                return rows[e - 60], rows[e]
            return None
        rows = requests.get(BINANCE, params={"symbol": pair, "interval": "1m", "startTime": entry_ms, "limit": 1}, timeout=10).json()
        if not rows or rows[0][0] != entry_ms:
            return None
        return float(rows[0][1]), float(rows[0][4])


def score(direction, p_in, p_out):
    if p_out == p_in:
        return "DRAW"
    return "WIN" if (p_out > p_in) == (direction == "BUY") else "LOSS"


def summarize(path: str) -> None:
    """Print win rates (with the 95% margin) per engine from a live_check CSV, even while it is still running."""
    import math
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    if not rows:
        print("no scored trades yet")
        return
    print(f"entries {rows[0]['entry']} -> {rows[-1]['entry']}   ({len(rows)} scored rows)")
    for e in dict.fromkeys(r["engine"] for r in rows):
        rs = [r for r in rows if r["engine"] == e]
        wins = sum(r["result"] == "WIN" for r in rs)
        n = sum(r["result"] in ("WIN", "LOSS") for r in rs)
        p = wins / n if n else 0
        ci = 1.96 * math.sqrt(p * (1 - p) / n) * 100 if n else 0
        print(f"  {e:<18} {wins:>4} / {n:<4} = {p * 100:5.1f}%  +/-{ci:4.1f}%   draws {len(rs) - n}")


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--summary":
        summarize(sys.argv[2])
        return
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--source", choices=["po", "binance"], default="po")
    ap.add_argument("--token", required=True)
    ap.add_argument("--admin-key", default=os.environ.get("ADMIN_KEY", ""))
    ap.add_argument("--minutes", type=int, default=30)
    ap.add_argument("--log", default="live_check.csv")
    ap.add_argument("--engines", default="v3,v3-reversion", help="engines to score next to the app, comma-separated")
    ap.add_argument("--reclaim", default="", help="test Trader ID: if the session expires (e.g. backend restart), "
                                                  "log it back in automatically (needs access to the backend database)")
    args = ap.parse_args()
    engines = tuple(e.strip() for e in args.engines.split(",") if e.strip())
    head = {"Authorization": f"Bearer {args.token}"}
    prices = Prices(args.source, args.api, args.admin_key)

    def ask_signal():
        r = requests.get(f"{args.api}/signal", headers=head, timeout=60)
        if r.status_code == 401 and args.reclaim:
            import trader_store
            trader_store.claim_session(args.reclaim, args.token)
            print(f"{datetime.now():%H:%M:%S}  session had expired, logged back in as {args.reclaim}", flush=True)
            r = requests.get(f"{args.api}/signal", headers=head, timeout=60)
        return r.json() if r.ok else {"error": r.status_code, "detail": r.text[:120]}

    pending, done = [], []
    # Append, never overwrite: a restarted check keeps everything already recorded.
    new_file = not os.path.exists(args.log) or os.path.getsize(args.log) == 0
    f = open(args.log, "a", newline="", encoding="utf-8")
    w = csv.writer(f)
    if new_file:
        w.writerow(["engine", "asked_at", "pair", "direction", "confidence", "entry", "price_in", "price_out", "result"])
        f.flush()
    print(f"source: {args.source}\n{'asked':<9} {'engine':<14} {'pair':<13} {'call':<5} {'conf':>5}  entry  in -> out  result", flush=True)

    end = time.time() + args.minutes * 60
    while time.time() < end or pending:
      try:
        if time.time() < end:
            while datetime.now().second not in range(3, 9):
                time.sleep(0.5)
            asked = datetime.now().strftime("%H:%M:%S")
            try:
                sig = ask_signal()
            except Exception as e:
                sig = {"error": str(e)[:120]}
            if "pair" in sig:
                entry_ms = int(datetime.fromisoformat(sig["entry_timestamp"]).astimezone(timezone.utc).timestamp() * 1000)
                pending.append(["app (current)", asked, sig["pair"], sig["direction"], sig["confidence"], entry_ms, 0])
                try:
                    for eng, pick in prices.picks(engines).items():
                        if pick:
                            pending.append([eng, asked, pick[0], pick[1], pick[2], entry_ms, 0])
                except Exception as e:
                    print(f"{asked}  engine picks failed: {e}", flush=True)
            else:
                print(f"{asked}  no signal from the app: {sig}", flush=True)

        now_ms = time.time() * 1000
        still = []
        for p in pending:
            engine, asked, pair, d, conf, entry_ms, tries = p
            if now_ms < entry_ms + 63_000:
                still.append(p)
                continue
            try:
                io = prices.entry_exit(pair, entry_ms)
            except Exception:
                io = None
            if io is None:
                p[6] += 1
                if p[6] < 30:          # Pocket Option cache refreshes about once a minute; give it time
                    still.append(p)
                else:
                    print(f"{asked:<9} {engine:<14} {pair:<13} {d:<5}  (candle never became available, skipped)", flush=True)
                continue
            res = score(d, *io)
            done.append((engine, res))
            entry_dt = datetime.fromtimestamp(entry_ms / 1000)
            print(f"{asked:<9} {engine:<14} {pair:<13} {d:<5} {conf:>5.1f}  {entry_dt:%H:%M}  {io[0]:.6g} -> {io[1]:.6g}  {res}", flush=True)
            w.writerow([engine, asked, pair, d, conf, f"{entry_dt:%Y-%m-%d %H:%M}", io[0], io[1], res])
            f.flush()
            os.fsync(f.fileno())       # on disk now, even if the server loses power
        pending = still
        time.sleep(5 if time.time() >= end else 10)
      except Exception as e:           # never let one bad minute stop an overnight run
        print(f"{datetime.now():%H:%M:%S}  error (continuing): {e}", flush=True)
        time.sleep(10)

    print("\nSUMMARY (draws not counted)", flush=True)
    for engine in ("app (current)", *engines):
        rs = [r for e, r in done if e == engine and r != "DRAW"]
        wins = sum(r == "WIN" for r in rs)
        draws = sum(1 for e, r in done if e == engine and r == "DRAW")
        print(f"  {engine:<14} {wins}/{len(rs)} right" + (f" = {wins / len(rs) * 100:.1f}%" if rs else "") + f"   (draws: {draws})", flush=True)
    f.close()


if __name__ == "__main__":
    main()
