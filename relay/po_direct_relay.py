"""
PocketOption Direct API Relay — no browser needed.

Connects directly to PO's WebSocket servers using your session token.
3x faster than the browser relay, no visible window, lower memory usage.

Usage — get your auth token (either works):

  Option A (preferred) — full "ssid" string from the WebSocket frames:
    1. Open the PocketOption trading page and log in
    2. F12 → Network tab → filter "WS" → click the active socket connection
    3. Open its Messages/Frames tab, find the outgoing frame starting with
       42["auth",{"session":...   and copy that ENTIRE string
    4. set LO_UID=<paste the full 42[...] string>   then run this script

  Option B — bare session cookie value:
    1. Log into PocketOption, F12 → Application → Cookies → pocketoption.com
    2. Copy the Value of the session cookie (e.g. 'lo_uid' on older PO builds)
    3. set LO_UID=<value>   then run this script

  Either way: paste it into LO_UID below, or set the LO_UID env var, then:
    python po_direct_relay.py
"""

import asyncio
import json
import os
import time
import threading
import logging
import requests
from typing import Dict, List, Tuple, Optional

import aiohttp
from aiohttp import WSMsgType

try:
    import msgpack
    _HAS_MSGPACK = True
except ImportError:
    _HAS_MSGPACK = False

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("po_direct")

# ── CONFIG ─────────────────────────────────────────────────────────────────
# When running ON the VPS itself, set RELAY_PUSH_URL=http://127.0.0.1:8000/candle-data
# (bypasses nginx/public DNS for a same-machine push). Defaults to the public URL
# for laptop/external use.
VPS_URL       = os.environ.get("RELAY_PUSH_URL",
                               "https://learnwithtanishq.com/tanix-api/candle-data")
API_KEY       = "%23uqwrhfuiesi83"
PUSH_INTERVAL = 5        # seconds between VPS pushes
CHANGE_INTERVAL = 1.0    # seconds per asset rotation on each connection

# Paste your lo_uid cookie here, or set the LO_UID environment variable
LO_UID = os.environ.get("LO_UID", "")   # ← paste here if not using env var

# Single connection — must match the regional server your browser session is
# bound to (visible in DevTools as the WS Request URL, e.g. "api-us-north").
# Sessions appear to be validated per-server: connecting with a session to a
# *different* region than it was issued from gets rejected (400 / closed
# right after upgrade), even though the token itself is valid.
PO_SERVERS = [
    ("wss://api-us-north.po.market/socket.io/",
     "https://api-us-north.po.market/socket.io/"),
]

ASSETS = [
    "EURUSD_otc", "GBPUSD_otc", "USDJPY_otc", "AUDUSD_otc", "USDCAD_otc",
    "USDCHF_otc", "NZDUSD_otc", "EURGBP_otc", "EURJPY_otc", "GBPJPY_otc",
    "AUDJPY_otc", "CADJPY_otc", "CHFJPY_otc", "GBPAUD_otc", "GBPCAD_otc",
    "GBPCHF_otc", "GBPNZD_otc", "AUDCAD_otc", "AUDCHF_otc", "AUDNZD_otc",
    "EURCAD_otc", "EURCHF_otc", "EURNZD_otc", "EURAUD_otc", "CADCHF_otc",
    "NZDCAD_otc", "NZDCHF_otc", "NZDJPY_otc", "XAUUSD_otc", "XAGUSD_otc",
    "BTCUSD_otc", "ETHUSD_otc", "LTCUSD_otc", "XRPUSD_otc", "BCHUSD_otc",
    "DOGEUSD_otc", "ADAUSD_otc", "SOLUSD_otc", "DOTUSD_otc", "BNBUSD_otc",
]

_WS_HEADERS = {
    "Origin":     "https://pocketoption.com",
    "Referer":    "https://pocketoption.com/en/cabinet/demo-quick-high-low/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

# ── Shared cache (written by async workers, read by push thread) ───────────
_cache: Dict[str, List[Tuple]] = {}   # po_symbol → [(ts, close, vol), ...]
_latest: Dict[str, float]      = {}   # po_symbol → most recent tick price
_lock = threading.Lock()


# ── Data handlers ──────────────────────────────────────────────────────────

def _store_candles(asset: str, history: list) -> None:
    if not asset or not history:
        return
    candles: List[Tuple] = []
    for item in history:
        try:
            if isinstance(item, (list, tuple)):
                t = item[0]
                c = item[2] if len(item) >= 3 else item[1]
                v = item[5] if len(item) >= 6 else 0.0
            elif isinstance(item, dict):
                t = item.get("time") or item.get("t") or item.get("timestamp")
                c = (item.get("close") or item.get("c") or
                     item.get("value") or item.get("v_close"))
                v = item.get("volume") or item.get("v") or 0.0
            else:
                continue
            if t and c:
                candles.append((int(float(t)), float(c), float(v or 0)))
        except Exception:
            continue

    if not candles:
        return

    candles.sort(key=lambda x: x[0])
    with _lock:
        _cache[asset] = candles[-200:]   # keep 200 candles for better indicator accuracy
    _latest[asset] = candles[-1][1]
    logger.info(f"  {asset}: {len(candles)} candles | price={candles[-1][1]:.5f}")


def _on_event(event: str, payload) -> None:
    """Route decoded events to the right handler."""
    if event in ("updateHistoryNewFast", "successChangeSymbol",
                 "loadHistoryPeriod", "updateHistoryNew"):
        if isinstance(payload, dict):
            asset   = payload.get("asset") or payload.get("symbol") or payload.get("a")
            history = (payload.get("history") or payload.get("candles") or
                       payload.get("data") or payload.get("h") or [])
            _store_candles(asset, history)

    elif event == "updateStream":
        def _tick(a, p):
            if a and p:
                try:
                    _latest[a] = float(p)
                except Exception:
                    pass

        if isinstance(payload, dict):
            _tick(payload.get("asset") or payload.get("a"),
                  payload.get("value") or payload.get("v") or payload.get("price"))
        elif isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    _tick(item.get("asset") or item.get("a"),
                          item.get("value") or item.get("v") or item.get("price"))
                elif isinstance(item, (list, tuple)) and len(item) >= 3:
                    _tick(item[0], item[2])


def _decode_binary(raw: bytes) -> Optional[object]:
    """Try UTF-8 JSON first, fall back to msgpack."""
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        pass
    if _HAS_MSGPACK:
        try:
            return msgpack.unpackb(raw, raw=False)
        except Exception:
            pass
    return None


# ── Socket.IO polling handshake ────────────────────────────────────────────

async def _get_sid(session: aiohttp.ClientSession, http_base: str) -> Optional[str]:
    """
    Socket.IO v4 polling handshake to get a session id (sid).
    Required before WebSocket upgrade on some PO servers.
    """
    try:
        t = aiohttp.ClientTimeout(total=10)
        async with session.get(http_base + "?EIO=4&transport=polling", timeout=t) as r:
            text = await r.text()
            sid = json.loads(text[text.index("{"):]).get("sid")
        if not sid:
            return None
        poll = http_base + f"?EIO=4&transport=polling&sid={sid}"
        async with session.post(poll, data="40", timeout=t) as r:
            await r.text()
        async with session.get(poll, timeout=t) as r:
            await r.text()
        return sid
    except Exception as e:
        logger.debug(f"SID handshake failed: {e}")
        return None


# ── Single WebSocket worker ────────────────────────────────────────────────

async def _ws_worker(token: str, ws_url: str, http_url: str,
                     assets: List[str]) -> None:
    """
    One persistent WebSocket connection to a PO server.
    Authenticates, then rotates through `assets` every CHANGE_INTERVAL seconds.
    Automatically reconnects with exponential back-off.
    """
    server_name = ws_url.split("//")[1].split(".")[0]   # e.g. "api-eu"
    retry_delay = 5

    while True:
        try:
            # A full ssid auth string isn't a valid cookie value (it contains
            # JSON syntax chars like { } [ ] " , forbidden in cookies), so only
            # send the legacy lo_uid cookie when `token` is a bare cookie value.
            is_ssid = token.lstrip().startswith(("42[", '["auth"'))
            headers = dict(_WS_HEADERS)
            if not is_ssid:
                headers["Cookie"] = f"lo_uid={token}"
            conn_timeout = aiohttp.ClientTimeout(total=None, connect=15)

            async with aiohttp.ClientSession(headers=headers) as http:
                # Socket.IO polling handshake (gets sid for the WS URL)
                sid = await _get_sid(http, http_url)
                url = ws_url + "?EIO=4&transport=websocket"
                if sid:
                    url += f"&sid={sid}"

                logger.info(f"[{server_name}] connecting...")
                async with http.ws_connect(url, headers=headers,
                                           timeout=conn_timeout,
                                           heartbeat=20) as ws:

                    # Socket.IO WebSocket upgrade probe
                    try:
                        await ws.send_str("2probe")
                        probe = await asyncio.wait_for(ws.receive_str(), timeout=5)
                        await ws.send_str("5" if probe == "3probe" else "40")
                    except asyncio.TimeoutError:
                        await ws.send_str("40")

                    # Drain any initial queued frames
                    for _ in range(5):
                        try:
                            await asyncio.wait_for(ws.receive_str(), timeout=0.5)
                        except asyncio.TimeoutError:
                            break

                    # Authenticate with PO. Two accepted formats for `token`:
                    #   1) A full "ssid" string captured from the browser's WS
                    #      frames — e.g. 42["auth",{"session":"...","isDemo":1,
                    #      "uid":12345,"platform":2}]  (preferred — exact format
                    #      PO's own client sends, correct uid/isDemo/platform)
                    #   2) A bare session token (old lo_uid-style cookie value),
                    #      which we wrap into an auth payload ourselves.
                    if is_ssid:
                        stripped = token.lstrip()
                        await ws.send_str(stripped if stripped.startswith("42") else f"42{stripped}")
                    else:
                        auth_msg = json.dumps([
                            "auth",
                            {"session": token, "isDemo": 1, "uid": 0, "platform": 2},
                        ])
                        await ws.send_str(f"42{auth_msg}")
                    logger.info(f"[{server_name}] authenticated — "
                                f"cycling {len(assets)} assets")

                    await asyncio.sleep(2)   # let auth settle before requesting data

                    pending_event: Optional[str] = None
                    asset_idx = 0
                    last_change = time.monotonic() - CHANGE_INTERVAL  # send immediately

                    while True:
                        # Non-blocking receive: wait at most 50ms before checking timer
                        try:
                            msg = await asyncio.wait_for(ws.receive(), timeout=0.05)
                        except asyncio.TimeoutError:
                            msg = None

                        if msg is not None:
                            if msg.type == WSMsgType.TEXT:
                                text = msg.data
                                if text == "2":
                                    await ws.send_str("3")   # pong

                                elif text.startswith("451-"):
                                    # Binary attachment announcement: "451-[eventName,{_placeholder}]"
                                    try:
                                        data = json.loads(text[4:])
                                        if isinstance(data, list) and data:
                                            pending_event = data[0]
                                    except Exception:
                                        pass

                                elif text.startswith("42"):
                                    # Regular text event (no binary attachment)
                                    try:
                                        data = json.loads(text[2:])
                                        if isinstance(data, list) and len(data) >= 2:
                                            _on_event(data[0], data[1])
                                    except Exception:
                                        pass

                            elif msg.type == WSMsgType.BINARY:
                                if pending_event:
                                    payload = _decode_binary(bytes(msg.data))
                                    if payload is not None:
                                        _on_event(pending_event, payload)
                                    pending_event = None

                            elif msg.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                                logger.warning(f"[{server_name}] disconnected ({msg.type.name})")
                                break

                        # Asset rotation timer
                        now = time.monotonic()
                        if now - last_change >= CHANGE_INTERVAL:
                            asset = assets[asset_idx % len(assets)]
                            try:
                                await ws.send_str(
                                    f'42{json.dumps(["changeSymbol", {"asset": asset, "period": 60}])}'
                                )
                                logger.debug(f"[{server_name}] → {asset}")
                            except Exception:
                                break
                            asset_idx += 1
                            last_change = now

            retry_delay = 5   # reset on clean exit

        except Exception as e:
            logger.error(f"[{server_name}] error: {e}")

        logger.info(f"[{server_name}] reconnecting in {retry_delay}s...")
        await asyncio.sleep(retry_delay)
        retry_delay = min(retry_delay * 2, 60)


# ── VPS push thread ────────────────────────────────────────────────────────

def _push_loop() -> None:
    """Background thread: pushes cached data to VPS every PUSH_INTERVAL seconds."""
    while True:
        time.sleep(PUSH_INTERVAL)
        with _lock:
            if not _cache:
                logger.info("No data yet — waiting...")
                continue
            snapshot = {k: [list(c) for c in v] for k, v in _cache.items()}
        payload = {
            "candles":       snapshot,
            "latest_prices": dict(_latest),
        }
        try:
            r = requests.post(VPS_URL, json=payload,
                              headers={"X-Admin-Key": API_KEY}, timeout=10)
            if r.ok:
                logger.info(
                    f"Pushed {len(snapshot)} assets | {len(_latest)} live prices"
                )
            else:
                logger.warning(f"VPS push failed: {r.status_code} {r.text[:100]}")
        except Exception as e:
            logger.warning(f"VPS push error: {e}")


# ── Entry point ────────────────────────────────────────────────────────────

async def main() -> None:
    token = LO_UID.strip()

    if not token:
        print("\n" + "=" * 62)
        print("  ERROR: auth token not set!")
        print("=" * 62)
        print("\nPreferred — full 'ssid' string from the WS frames:")
        print("  1. Open the PocketOption trading page, log in")
        print("  2. F12 → Network tab → filter 'WS' → click the socket connection")
        print("  3. Open Messages/Frames, find the frame starting with")
        print("     42[\"auth\",{\"session\":...   and copy the WHOLE string")
        print()
        print("Alternative — bare session cookie value:")
        print("  1. F12 → Application tab → Cookies → pocketoption.com")
        print("  2. Copy the Value of the session cookie (e.g. 'lo_uid')")
        print()
        print("Then either:")
        print("  A) Paste it directly into LO_UID in this file, OR")
        print("  B) In this terminal, run:")
        print("       set LO_UID=<paste_value_here>")
        print("     then run this script again.")
        print()
        return

    is_ssid = token.lstrip().startswith(("42[", '["auth"'))
    logger.info(f"PO Direct Relay starting "
                f"({'ssid' if is_ssid else 'token'}: ...{token[-12:]})")
    logger.info(f"Servers: {len(PO_SERVERS)} | Assets: {len(ASSETS)} | Push: every {PUSH_INTERVAL}s")

    # Start VPS push thread
    threading.Thread(target=_push_loop, daemon=True).start()

    # Divide assets evenly across the 3 server connections
    # e.g. 40 assets / 3 servers = ~14, 13, 13 assets each
    n = len(PO_SERVERS)
    chunk = (len(ASSETS) + n - 1) // n

    tasks = []
    for i, (ws_url, http_url) in enumerate(PO_SERVERS):
        my_assets = ASSETS[i * chunk: (i + 1) * chunk]
        if not my_assets:
            break
        name = ws_url.split("//")[1].split(".")[0]
        logger.info(f"  {name}: {my_assets[0]} … {my_assets[-1]} ({len(my_assets)} assets)")
        tasks.append(_ws_worker(token, ws_url, http_url, my_assets))

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
