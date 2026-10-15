"""
PocketOption candle data relay using BinaryOptionsToolsV2.

Connects to Pocket Option using the BinaryOptionsToolsV2 library,
fetches 1-minute candles for all high-payout OTC assets, and pushes
the data to the VPS backend every PUSH_INTERVAL seconds.

Usage:
    Option A — set environment variable, then run:
        set LO_UID=42["auth",{"session":"...","isDemo":0,"uid":12345,"platform":2}]
        python po_botv2_relay.py

    Option B — just run and paste when prompted:
        python po_botv2_relay.py

How to find your SSID:
    1. Log into PocketOption in your browser
    2. F12 → Network tab → filter "WS"
    3. Click the active WebSocket connection
    4. Open Messages/Frames tab
    5. Find the outgoing frame starting with 42["auth",{"session":...
    6. Copy the ENTIRE string
"""

import asyncio
import os
import time
import threading
import logging
import requests
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from BinaryOptionsToolsV2.config import Config
from BinaryOptionsToolsV2.pocketoption import PocketOptionAsync

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger("po_botv2_relay")

# ── CONFIG ───────────────────────────────────────────────────────────────────
VPS_URL       = os.environ.get(
    "RELAY_PUSH_URL",
    "https://learnwithtanishq.com/tanix-api/candle-data"
)
API_KEY       = "%23uqwrhfuiesi83"
PUSH_INTERVAL = 30        # seconds between VPS pushes
PERIOD        = 60        # candle timeframe in seconds (1 min)
DURATION      = 6000      # history to fetch in seconds (~100 candles at 1m)
MIN_PAYOUT    = 80        # only include assets with payout >= this %
FETCH_DELAY   = 0.5       # seconds between per-asset requests (rate limit safety)

# Paste your SSID here, or set the LO_UID environment variable
SSID = os.environ.get("LO_UID", "")

# ── Shared cache (written by async loop, read by push thread) ─────────────────
_cache:  Dict[str, List[List]] = {}   # symbol → [[ts, close, vol], ...]
_latest: Dict[str, float]      = {}   # symbol → most recent close price
_lock = threading.Lock()


# ── Candle parsing ────────────────────────────────────────────────────────────

def _parse_candle(raw) -> Optional[Tuple[int, float, float]]:
    """
    Convert a BinaryOptionsToolsV2 candle dict to (timestamp, close, volume).
    The library returns dicts with keys: time, open, high, low, close (no volume).
    """
    if isinstance(raw, dict):
        t = raw.get("time") or raw.get("timestamp") or raw.get("t")
        c = raw.get("close") or raw.get("c")
        v = float(raw.get("volume") or raw.get("v") or 0.0)
        if t is not None and c is not None:
            return (int(float(t)), float(c), v)
    elif isinstance(raw, (list, tuple)) and len(raw) >= 2:
        t = raw[0]
        c = raw[2] if len(raw) >= 3 else raw[1]
        v = float(raw[5]) if len(raw) >= 6 else 0.0
        if t and c:
            return (int(float(t)), float(c), v)
    return None


def _store_candles(symbol: str, raw_candles: list) -> None:
    """Parse, sort, and store candles in the shared cache."""
    parsed = []
    for raw in raw_candles:
        t = _parse_candle(raw)
        if t:
            parsed.append(list(t))
    if not parsed:
        logger.warning(f"  {symbol}: parsed 0 candles from {len(raw_candles)} raw")
        return

    parsed.sort(key=lambda x: x[0])
    parsed = parsed[-200:]   # keep last 200 candles for indicator accuracy

    with _lock:
        _cache[symbol]  = parsed
        _latest[symbol] = parsed[-1][1]

    logger.info(f"  {symbol}: {len(parsed)} candles | last_close={parsed[-1][1]:.5f}")


# ── VPS push thread ───────────────────────────────────────────────────────────

def _push_loop() -> None:
    """Background thread: pushes cached candle data to VPS every PUSH_INTERVAL seconds."""
    while True:
        time.sleep(PUSH_INTERVAL)
        with _lock:
            if not _cache:
                logger.info("Cache empty — nothing to push yet.")
                continue
            snapshot = {k: [list(c) for c in v] for k, v in _cache.items()}
            prices   = dict(_latest)

        payload = {"candles": snapshot, "latest_prices": prices}
        try:
            r = requests.post(
                VPS_URL,
                json=payload,
                headers={"X-Admin-Key": API_KEY},
                timeout=15,
            )
            if r.ok:
                logger.info(
                    f"Pushed {len(snapshot)} assets | {len(prices)} live prices → VPS"
                )
            else:
                logger.warning(f"VPS push failed: {r.status_code} {r.text[:120]}")
        except Exception as e:
            logger.warning(f"VPS push error: {e}")


# ── Main async loop ───────────────────────────────────────────────────────────

async def main(ssid: str) -> None:
    config = Config(connection_initialization_timeout_secs=20)

    async with PocketOptionAsync(ssid, config=config) as api:
        logger.info("Connected to Pocket Option — waiting for init...")
        await asyncio.sleep(5)

        # Start the background push thread
        threading.Thread(target=_push_loop, daemon=True).start()
        logger.info(
            f"Push thread started (every {PUSH_INTERVAL}s → {VPS_URL})"
        )

        while True:
            logger.info("=" * 60)
            logger.info("Refreshing asset list and payouts...")

            # ── Step 1: get active assets ──────────────────────────────────
            try:
                active_assets = await api.active_assets()
                selected = [
                    a for a in active_assets
                    if a.get("payout", 0) >= MIN_PAYOUT
                ]
                logger.info(
                    f"Total assets: {len(active_assets)} | "
                    f"Payout ≥ {MIN_PAYOUT}%: {len(selected)}"
                )

                # Print a summary grouped by type
                by_type = defaultdict(list)
                for a in selected:
                    by_type[a.get("asset_type", "unknown")].append(a)
                for atype, assets in sorted(by_type.items()):
                    symbols = ", ".join(a["symbol"] for a in assets[:5])
                    suffix  = f" +{len(assets)-5} more" if len(assets) > 5 else ""
                    logger.info(f"  {atype.upper()} ({len(assets)}): {symbols}{suffix}")

            except Exception as e:
                logger.error(f"Failed to get active assets: {e}")
                await asyncio.sleep(30)
                continue

            # ── Step 2: fetch candles for each selected asset ──────────────
            logger.info(f"Fetching candles (PERIOD={PERIOD}s, DURATION={DURATION}s)...")
            success_count = 0
            fail_count    = 0

            for asset in selected:
                symbol = asset.get("symbol") or asset.get("name", "")
                payout = asset.get("payout", 0)
                if not symbol:
                    continue

                try:
                    candles = await api.get_candles(symbol, PERIOD, DURATION)
                    if candles:
                        _store_candles(symbol, candles)
                        success_count += 1
                    else:
                        logger.warning(f"  {symbol} (payout={payout}%): empty response")
                        fail_count += 1
                except Exception as e:
                    logger.error(f"  {symbol}: fetch error — {e}")
                    fail_count += 1

                await asyncio.sleep(FETCH_DELAY)

            logger.info(
                f"Cycle done — {success_count} fetched, {fail_count} failed. "
                f"Cache: {len(_cache)} assets. Sleeping 60s..."
            )
            await asyncio.sleep(60)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    token = SSID.strip()
    if not token:
        print()
        print("=" * 62)
        print("  PocketOption BotV2 Relay")
        print("=" * 62)
        print()
        print("Enter your SSID (full 42[...] string from browser WS frames):")
        print("  1. Log into PocketOption, open F12 → Network → WS tab")
        print("  2. Click the active WebSocket connection")
        print("  3. Find the outgoing frame starting with 42[\"auth\",{\"session\":...")
        print("  4. Copy the ENTIRE string and paste below")
        print()
        token = input("SSID: ").strip()

    if not token:
        print("ERROR: SSID is required. Exiting.")
        raise SystemExit(1)

    logger.info(f"Starting relay with token ...{token[-12:]}")
    asyncio.run(main(token))
