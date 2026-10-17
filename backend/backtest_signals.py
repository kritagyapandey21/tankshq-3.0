"""Backtest the signal engines on real 1-minute prices.

    python backtest_signals.py --cache <folder> [--minutes 30000] [--step 3]

What it measures
----------------
For every sampled minute t and every pair, each engine looks at the last 150 closes (exactly what the live app sees)
and calls UP / DOWN / no-signal. The trade wins if the next 1-minute close moves the called way (the app's
1-minute expiry). Like the app, it also picks the single best pair each minute (highest confidence) and scores that.

The first 60% of the period is "in-sample" (what you would tune on); the last 40% is "out-of-sample", the honest
number. Prices come from Binance's public 1-minute candles (closes only, like Pocket Option's feed). Pocket Option
OTC prices are their own synthetic series, so treat this as a test of the method, not a promise for OTC pairs.
"""

import argparse
import json
import math
import os
import sys
import time
from multiprocessing import Pool

import numpy as np
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import signal_v3 as v3  # noqa: E402

SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "XRPUSDT", "DOGEUSDT", "LTCUSDT", "LINKUSDT", "SOLUSDT", "BCHUSDT"]
WINDOW = 150
SPLIT = 0.6
PAYOUTS = (0.80, 0.85, 0.92)   # typical binary-option payouts -> break-even win rate = 1 / (1 + payout)


# ------------------------------------------------------------------------------------------------ data
def fetch_closes(symbol: str, minutes: int, cache: str) -> np.ndarray:
    path = os.path.join(cache, f"{symbol}_{minutes}.json")
    if os.path.exists(path):
        return np.array(json.load(open(path)), dtype=float)
    rows, end = [], None
    while len(rows) < minutes:
        params = {"symbol": symbol, "interval": "1m", "limit": 1000}
        if end:
            params["endTime"] = end
        r = requests.get("https://api.binance.com/api/v3/klines", params=params, timeout=20)
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        rows = batch + rows
        end = batch[0][0] - 1
        time.sleep(0.15)
    rows = rows[-minutes:]
    closes = [float(k[4]) for k in rows]
    json.dump(closes, open(path, "w"))
    return np.array(closes, dtype=float)


# ------------------------------------------------------------------------------------------------ engines
VARIANTS = {
    # name: (supertrend period, multiplier, ker_range, ker_trend)
    "v3 adaptive  ST10x2": (10, 2.0, v3.KER_RANGE, v3.KER_TREND),
    "v3 adaptive  ST10x3": (10, 3.0, v3.KER_RANGE, v3.KER_TREND),
    "v3 trend-only ST10x2": (10, 2.0, -2.0, -1.0),
    "v3 trend-only ST10x3": (10, 3.0, -2.0, -1.0),
    "v3 reversion-only": (10, 2.0, 5.0, 6.0),
}


PLUS_VARIANTS = {
    # stricter mean reversion (signal_v3.reversion_plus); chosen on the in-sample period only
    "R+ agree": dict(min_score=0.25, need_agree=True),
    "R+ agree+chop": dict(min_score=0.25, need_agree=True, ker_max=0.35),
    "R+ agree+jump1.0": dict(min_score=0.25, need_agree=True, min_shock=1.0),
    "R+ agree+chop+jump1.0": dict(min_score=0.25, need_agree=True, ker_max=0.35, min_shock=1.0),
    "R+ agree+chop+jump1.5": dict(min_score=0.25, need_agree=True, ker_max=0.35, min_shock=1.5),
    "R+ jump1.5 only": dict(min_score=0.15, need_agree=False, min_shock=1.5),
}


def run_symbol(args):
    symbol, closes, step = args
    from analysis import SignalAnalyzer  # current live engine ("v2")
    out = {name: [] for name in ["v2 current", *VARIANTS, *PLUS_VARIANTS, "pullback (trend filter)", "reversion vs trend",
                                 "supertrend alone", "ema 9/21 alone"]}
    for t in range(WINDOW - 1, len(closes) - 1, step):
        w = closes[t - WINDOW + 1:t + 1]
        move = closes[t + 1] - closes[t]
        outcome = 0 if move == 0 else (1 if move > 0 else -1)

        a = SignalAnalyzer._analyze_pair_v2({"symbol": symbol, "closes": list(w), "current_price": w[-1]})
        out["v2 current"].append((t, (1 if a["direction"] == "CALL" else -1) if a else 0, a["confidence"] if a else 0.0, outcome))

        comps = {(p, m): v3.components(w, p, m) for p, m in {(10, 2.0), (10, 3.0)}}
        for name, (p, m, kr, kt) in VARIANTS.items():
            b = v3.blend(comps[(p, m)], kr, kt)
            d = 0 if b["direction"] is None else (1 if b["direction"] == "CALL" else -1)
            out[name].append((t, d, b["confidence"], outcome))
        # Supertrend + EMA as the trend filter, mean reversion as the entry ("buy dips in an uptrend")
        cp = comps[(10, 2.0)]
        rev = v3.blend(cp, 5.0, 6.0)
        rd = 0 if rev["direction"] is None else (1 if rev["direction"] == "CALL" else -1)
        trend_dir = int(np.sign(cp["supertrend"])) if np.sign(cp["supertrend"]) == np.sign(cp["ema"]) else 0
        out["pullback (trend filter)"].append((t, rd if (rd and rd == trend_dir) else 0, rev["confidence"], outcome))
        out["reversion vs trend"].append((t, rd if (rd and rd == -trend_dir) else 0, rev["confidence"], outcome))
        for name, kw in PLUS_VARIANTS.items():
            b = v3.reversion_plus(cp, **kw)
            out[name].append((t, 0 if b["direction"] is None else (1 if b["direction"] == "CALL" else -1), b["confidence"], outcome))
        st = comps[(10, 2.0)]["supertrend"]
        out["supertrend alone"].append((t, int(np.sign(st)), abs(st) * 100, outcome))
        em = comps[(10, 2.0)]["ema"]
        out["ema 9/21 alone"].append((t, int(np.sign(em)) if abs(em) > 0.05 else 0, abs(em) * 100, outcome))
    return symbol, out


# ------------------------------------------------------------------------------------------------ scoring
def rate(wins: int, n: int) -> str:
    if n == 0:
        return "   n/a          (n=0)"
    p = wins / n
    ci = 1.96 * math.sqrt(p * (1 - p) / n)
    return f"{p * 100:5.2f}% ±{ci * 100:4.2f}  (n={n})"


def evaluate(results, t_split):
    names = list(next(iter(results.values())).keys())
    print(f"\n{'engine':<22} | {'ALL signals, out-of-sample':<28} | {'BEST PAIR each minute (like the app), out-of-sample':<30} | best pair, in-sample")
    print("-" * 132)
    summary = {}
    for name in names:
        all_w = all_n = 0
        by_t = {}
        for sym, out in results.items():
            for t, d, conf, o in out[name]:
                if d == 0 or o == 0:
                    continue
                if t >= t_split:
                    all_n += 1
                    all_w += d == o
                if conf > by_t.get(t, (None, -1))[1]:
                    by_t[t] = ((d == o), conf)
        oos = [w for t, (w, c) in by_t.items() if t >= t_split]
        ins = [w for t, (w, c) in by_t.items() if t < t_split]
        summary[name] = (sum(oos) / len(oos) if oos else 0, len(oos))
        print(f"{name:<22} | {rate(all_w, all_n):<28} | {rate(sum(oos), len(oos)):<51} | {rate(sum(ins), len(ins))}")
    print("\nWhich coins the BEST-PAIR pick lands on (out-of-sample), and its win rate there:")
    for k in ["v2 current", "v3 adaptive  ST10x2", "v3 reversion-only"]:
        picks = {}
        for sym, out in results.items():
            for t, d, conf, o in out[k]:
                if d == 0 or o == 0 or t < t_split:
                    continue
                if conf > picks.get(t, (None, -1, None))[1]:
                    picks[t] = (sym, conf, d == o)
        tally = {}
        for sym, conf, won in picks.values():
            a = tally.setdefault(sym, [0, 0]); a[0] += 1; a[1] += won
        parts = ", ".join(f"{s[:-4]} {n * 100 // max(len(picks), 1)}% ({wn * 100 // max(n, 1)}% won)"
                          for s, (n, wn) in sorted(tally.items(), key=lambda x: -x[1][0]))
        print(f"  {k:<22} {parts}")

    print("\nPer coin, ALL signals, out-of-sample win rate:")
    keys = ["v2 current", "v3 adaptive  ST10x2", "v3 reversion-only", "pullback (trend filter)"]
    print(f"{'coin':<10}" + "".join(f"{k[:24]:>26}" for k in keys))
    for sym, out in results.items():
        row = f"{sym:<10}"
        for k in keys:
            rs = [d == o for t, d, c, o in out[k] if t >= t_split and d != 0 and o != 0]
            row += f"{(sum(rs) / len(rs) * 100 if rs else 0):>18.1f}% n={len(rs):<5}"
        print(row)
    print("\nBreak-even win rate:", ", ".join(f"{int(p * 100)}% payout -> {100 / (1 + p):.1f}%" for p in PAYOUTS))
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--minutes", type=int, default=30000)
    ap.add_argument("--step", type=int, default=3)
    ap.add_argument("--symbols", default=",".join(SYMBOLS), help="comma-separated subset")
    args = ap.parse_args()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    os.makedirs(args.cache, exist_ok=True)

    data = {}
    for s in symbols:
        data[s] = fetch_closes(s, args.minutes, args.cache)
        print(f"{s}: {len(data[s])} one-minute closes")
    n = min(len(x) for x in data.values())
    data = {s: x[-n:] for s, x in data.items()}
    ups = np.mean([np.mean(np.diff(x) > 0) for x in data.values()])
    print(f"\nShare of 1-minute candles that closed up (all pairs): {ups * 100:.2f}%  (coin-flip baseline is 50%)")
    print("\nPer coin: price, minutes with NO price change, and lag-1 autocorrelation of 1-minute moves")
    print("(strongly negative = each minute tends to undo the previous one, often a price-tick artifact on cheap coins)")
    for s, x in data.items():
        r = np.diff(x)
        ac = np.corrcoef(r[:-1], r[1:])[0, 1]
        print(f"  {s:<9} price {x[-1]:>10.4f}   unchanged {np.mean(r == 0) * 100:5.1f}%   autocorr {ac:+.3f}")

    t0 = time.time()
    with Pool(min(4, os.cpu_count() or 2)) as pool:
        results = dict(pool.map(run_symbol, [(s, data[s], args.step) for s in symbols]))
    print(f"(backtest took {time.time() - t0:.0f}s, {n // args.step} sampled minutes x {len(symbols)} pairs)")
    evaluate(results, int(n * SPLIT))


if __name__ == "__main__":
    main()
