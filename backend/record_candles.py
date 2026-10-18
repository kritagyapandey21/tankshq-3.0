"""Record live Pocket Option 1-minute candles to a CSV file, for later research.

    python record_candles.py --api http://127.0.0.1:8010 --out /var/lib/tanix3/candles.csv

Every minute it reads the backend's own Pocket Option candle cache (GET /admin/market-snapshot, read-only; no second
Pocket Option connection) and appends every candle it has not saved before: pair, unix time, close.
Append-only and restart-safe: on start it reads the file to know what is already saved. Runs until stopped.
The admin key is read from backend/.env (or the ADMIN_KEY environment variable).
"""

import argparse
import csv
import os
import sys
import time
from datetime import datetime, timezone

import requests

HERE = os.path.dirname(os.path.abspath(__file__))


def admin_key() -> str:
    key = os.environ.get("ADMIN_KEY", "").strip()
    if key:
        return key.splitlines()[-1].strip()
    try:
        from dotenv import dotenv_values
        return (dotenv_values(os.path.join(HERE, ".env")).get("ADMIN_KEY") or "").strip()
    except Exception:
        return ""


def report(path: str) -> None:
    """Per pair: candles saved, hours covered, and how many continuous stretches (gaps split them)."""
    by_pair = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            by_pair.setdefault(row["pair"], []).append(int(row["time"]))
    total = sum(len(v) for v in by_pair.values())
    print(f"{len(by_pair)} pairs, {total} candles\n{'pair':<14} {'candles':>8} {'hours':>6} {'stretches':>9} {'longest':>8}  first -> last (UTC)")
    for pair, ts in sorted(by_pair.items(), key=lambda x: -len(x[1])):
        ts.sort()
        runs, run, longest = 1, 1, 1
        for a, b in zip(ts, ts[1:]):
            if b - a == 60:
                run += 1
            else:
                runs += 1
                run = 1
            longest = max(longest, run)
        first = datetime.fromtimestamp(ts[0], timezone.utc).strftime("%m-%d %H:%M")
        last = datetime.fromtimestamp(ts[-1], timezone.utc).strftime("%m-%d %H:%M")
        print(f"{pair:<14} {len(ts):>8} {len(ts) / 60:>6.1f} {runs:>9} {longest / 60:>7.1f}h  {first} -> {last}")


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--report":
        report(sys.argv[2])
        return
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8010")
    ap.add_argument("--out", default="candles.csv")
    ap.add_argument("--every", type=int, default=60, help="seconds between reads")
    args = ap.parse_args()
    key = admin_key()
    if not key:
        sys.exit("No ADMIN_KEY found (set it in backend/.env)")

    last = {}                                   # pair -> newest saved unix time
    if os.path.exists(args.out) and os.path.getsize(args.out) > 0:
        with open(args.out, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                t = int(row["time"])
                if t > last.get(row["pair"], 0):
                    last[row["pair"]] = t
    new_file = not os.path.exists(args.out) or os.path.getsize(args.out) == 0
    f = open(args.out, "a", newline="", encoding="utf-8")
    w = csv.writer(f)
    if new_file:
        w.writerow(["pair", "time", "utc", "close"])
        f.flush()
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S}  recording to {args.out} (already have {len(last)} pairs)", flush=True)

    while True:
        try:
            r = requests.get(f"{args.api}/admin/market-snapshot", headers={"X-Admin-Key": key}, timeout=20)
            r.raise_for_status()
            added = 0
            for pair, rows in r.json().get("pairs", {}).items():
                for t, close in rows:
                    t = int(t)
                    if t > last.get(pair, 0):
                        w.writerow([pair, t, datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M"), close])
                        last[pair] = t
                        added += 1
            f.flush()
            os.fsync(f.fileno())
            if added:
                print(f"{datetime.now():%H:%M:%S}  +{added} candles ({len(last)} pairs)", flush=True)
        except Exception as e:
            print(f"{datetime.now():%H:%M:%S}  error (continuing): {e}", flush=True)
        time.sleep(args.every)


if __name__ == "__main__":
    main()
