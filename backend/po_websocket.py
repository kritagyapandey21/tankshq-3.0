"""
Pocket Option WebSocket client using aiohttp.
Connects to PO servers using lo_uid session cookie.
Dynamically discovers all available OTC assets, then fetches candle data.
"""

import asyncio
import json
import logging
import threading
from typing import Optional, List, Tuple, Dict

import aiohttp

logger = logging.getLogger(__name__)

PO_WS_BASE   = "wss://api-eu.po.market/socket.io/"
PO_HTTP_BASE = "https://api-eu.po.market/socket.io/"

_HEADERS = {
    "Origin":  "https://pocketoption.com",
    "Referer": "https://pocketoption.com/en/trading/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}


async def _get_sid(session: aiohttp.ClientSession) -> Optional[str]:
    """
    Full Socket.IO v4 polling handshake before WS upgrade:
      1. GET  ?transport=polling          → receive open packet with sid
      2. POST ?transport=polling&sid=XXX  → send SIO connect packet (body: '40')
      3. GET  ?transport=polling&sid=XXX  → drain any queued packets
    Returns sid to use in the WebSocket URL.
    """
    try:
        t = aiohttp.ClientTimeout(total=10)
        # Step 1: get session id
        url = PO_HTTP_BASE + "?EIO=4&transport=polling"
        async with session.get(url, timeout=t) as resp:
            text = await resp.text()
            json_start = text.index("{")
            data = json.loads(text[json_start:])
            sid = data.get("sid")
            if not sid:
                return None
            logger.debug(f"PO SIO sid: {sid}")

        poll_url = PO_HTTP_BASE + f"?EIO=4&transport=polling&sid={sid}"

        # Step 2: send SIO connect packet
        async with session.post(poll_url, data="40", timeout=t) as resp:
            await resp.text()

        # Step 3: drain queued packets
        async with session.get(poll_url, timeout=t) as resp:
            await resp.text()

        return sid

    except Exception as e:
        logger.warning(f"SIO polling handshake failed: {e}")
        return None

# Cached asset list: po_symbol (e.g. "EURUSD_otc") → display name (e.g. "EUR/USD-OTC")
_discovered_assets: Dict[str, str] = {}
_discovery_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Asset name helpers
# ---------------------------------------------------------------------------

def _po_symbol_to_display(po_symbol: str) -> str:
    """Convert PO internal symbol to human-readable name.
    e.g. 'EURUSD_otc' → 'EUR/USD-OTC', 'DOGEUSD_otc' → 'DOGE/USD-OTC'
    """
    base = po_symbol.replace("_otc", "").upper()
    suffix = "-OTC" if "_otc" in po_symbol.lower() else ""

    common_quotes = ["USD", "JPY", "GBP", "EUR", "AUD", "CAD", "CHF", "NZD", "BTC", "ETH"]
    for quote in common_quotes:
        if base.endswith(quote) and len(base) > len(quote):
            b = base[: -len(quote)]
            # 3-char base → standard forex
            return f"{b}/{quote}{suffix}"

    # Couldn't split — return as-is (stocks like AAPL_otc → AAPL-OTC)
    return f"{base}{suffix}"


# ---------------------------------------------------------------------------
# Asset discovery
# ---------------------------------------------------------------------------

def _parse_asset_list_msg(msg: str) -> List[Dict]:
    """
    Try to extract an asset list from a PO Socket.IO message.
    Returns list of dicts like {"po_symbol": "EURUSD_otc", "display": "EUR/USD-OTC"}.
    """
    try:
        raw = msg
        for prefix in ("451-[", "451-", "42"):
            if raw.startswith(prefix):
                raw = raw[len(prefix):]
                if prefix == "451-[":
                    raw = "[" + raw
                break

        data = json.loads(raw)
        if not isinstance(data, list) or len(data) < 2:
            return []

        event, payload = data[0], data[1]
        logger.debug(f"PO event: {event}")

        # PO sends asset lists under various event names
        asset_events = {
            "assets", "assetsList", "availableAssets",
            "instruments", "getAssets", "loadAssets",
            "updateAssets", "serverConfigure",
        }
        if event not in asset_events:
            return []

        # payload may be a list or dict
        raw_list = []
        if isinstance(payload, list):
            raw_list = payload
        elif isinstance(payload, dict):
            raw_list = (
                payload.get("data")
                or payload.get("assets")
                or payload.get("instruments")
                or []
            )

        result = []
        for item in raw_list:
            if not isinstance(item, dict):
                continue
            name = (
                item.get("symbol")
                or item.get("name")
                or item.get("asset")
                or item.get("code")
                or ""
            )
            active = item.get("active", item.get("isActive", True))
            if not name or not active:
                continue
            result.append({
                "po_symbol":   name,
                "display":     _po_symbol_to_display(name),
            })

        return result

    except Exception:
        return []


async def _discover_assets_async(session_token: str) -> Dict[str, str]:
    """
    Connect to PO WebSocket, authenticate, and collect all available assets.
    Returns mapping {po_symbol: display_name}.
    """
    headers = {**_HEADERS, "Cookie": f"lo_uid={session_token}"}
    found: Dict[str, str] = {}

    try:
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        async with aiohttp.ClientSession(headers=headers) as http:
            sid = await _get_sid(http)
            ws_url = PO_WS_BASE + "?EIO=4&transport=websocket" + (f"&sid={sid}" if sid else "")
            async with http.ws_connect(ws_url, timeout=timeout) as ws:

                # Socket.IO upgrade probe exchange
                try:
                    await ws.send_str("2probe")
                    probe = await asyncio.wait_for(ws.receive_str(), timeout=5)
                    if probe == "3probe":
                        await ws.send_str("5")
                    else:
                        await ws.send_str("40")
                        await asyncio.wait_for(ws.receive_str(), timeout=3)
                except asyncio.TimeoutError:
                    await ws.send_str("40")

                # Drain + parse initial push (3 s)
                t0 = asyncio.get_event_loop().time()
                while asyncio.get_event_loop().time() - t0 < 3:
                    try:
                        msg = await asyncio.wait_for(ws.receive_str(), timeout=0.5)
                        for item in _parse_asset_list_msg(msg):
                            found[item["po_symbol"]] = item["display"]
                    except asyncio.TimeoutError:
                        break

                if found:
                    logger.info(f"PO asset discovery (pre-auth): {len(found)} assets")
                    return found

                # Authenticate
                auth = json.dumps([
                    "auth",
                    {"session": session_token, "isDemo": 0, "uid": 0, "platform": 2},
                ])
                await ws.send_str(f"42{auth}")

                # Try requesting assets explicitly
                for event_name in ("getAssets", "loadAssets", "getAvailableAssets"):
                    await ws.send_str(f'42{json.dumps([event_name, {}])}')

                # Listen for asset list (up to 10 s)
                deadline = asyncio.get_event_loop().time() + 10
                while asyncio.get_event_loop().time() < deadline:
                    try:
                        msg = await asyncio.wait_for(ws.receive_str(), timeout=2)
                        if msg == "2":
                            await ws.send_str("3")
                            continue
                        for item in _parse_asset_list_msg(msg):
                            found[item["po_symbol"]] = item["display"]
                        if len(found) > 5:
                            break
                    except asyncio.TimeoutError:
                        break

    except Exception as e:
        logger.error(f"PO asset discovery error: {e}")

    logger.info(f"PO asset discovery result: {len(found)} assets found")
    return found


def discover_assets(session_token: str) -> Dict[str, str]:
    """
    Sync wrapper for _discover_assets_async.
    Returns {po_symbol: display_name} for all active OTC assets from PO.
    """
    result_holder: List[Dict] = [{}]

    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result_holder[0] = loop.run_until_complete(
                _discover_assets_async(session_token)
            )
        finally:
            loop.close()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=35)

    with _discovery_lock:
        if result_holder[0]:
            _discovered_assets.update(result_holder[0])

    return result_holder[0]


def get_cached_assets() -> Dict[str, str]:
    with _discovery_lock:
        return dict(_discovered_assets)


# ---------------------------------------------------------------------------
# Candle message parser
# ---------------------------------------------------------------------------

def _parse_sio_message(msg: str) -> Optional[List[Tuple]]:
    """Extract (timestamp, close, volume) tuples from a PO Socket.IO message."""
    try:
        raw = msg
        for prefix in ("451-[", "451-", "42"):
            if raw.startswith(prefix):
                raw = raw[len(prefix):]
                if prefix == "451-[":
                    raw = "[" + raw
                break

        data = json.loads(raw)
        if not isinstance(data, list) or len(data) < 2:
            return None

        event, payload = data[0], data[1]

        if event not in (
            "loadHistoryPeriod", "successChangeSymbol",
            "history", "candles", "updateHistoryNew",
            "updateHistory", "changeSymbol",
        ):
            return None

        if not isinstance(payload, dict):
            return None

        history = (
            payload.get("history")
            or payload.get("candles")
            or payload.get("data")
            or []
        )

        candles = []
        for item in history:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                t = item[0]
                c = item[2] if len(item) >= 3 else item[1]
                v = item[5] if len(item) >= 6 else 0
                if t and c:
                    candles.append((int(t), float(c), float(v or 0)))
            elif isinstance(item, dict):
                t = item.get("time") or item.get("t") or item.get("timestamp")
                c = item.get("close") or item.get("c")
                v = item.get("volume") or item.get("v") or 0
                if t and c:
                    candles.append((int(t), float(c), float(v or 0)))

        return candles if candles else None

    except Exception as e:
        logger.debug(f"SIO parse error: {e} | msg={msg[:120]}")
        return None


# ---------------------------------------------------------------------------
# Candle fetching
# ---------------------------------------------------------------------------

async def _fetch_async(session_token: str, po_asset: str, limit: int) -> Optional[List[Tuple]]:
    headers = {**_HEADERS, "Cookie": f"lo_uid={session_token}"}

    try:
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        async with aiohttp.ClientSession(headers=headers) as session:
            sid = await _get_sid(session)
            ws_url = PO_WS_BASE + "?EIO=4&transport=websocket" + (f"&sid={sid}" if sid else "")
            logger.debug(f"PO WS connecting: {ws_url}")

            async with session.ws_connect(ws_url, timeout=timeout) as ws:

                # Socket.IO upgrade probe exchange
                try:
                    await ws.send_str("2probe")
                    probe = await asyncio.wait_for(ws.receive_str(), timeout=5)
                    logger.debug(f"PO probe response: {probe}")
                    if probe == "3probe":
                        await ws.send_str("5")  # confirm upgrade
                    else:
                        # Some servers skip probe — drain normally
                        await ws.send_str("40")
                        await asyncio.wait_for(ws.receive_str(), timeout=3)
                except asyncio.TimeoutError:
                    await ws.send_str("40")

                # Drain any buffered init messages
                t0 = asyncio.get_event_loop().time()
                while asyncio.get_event_loop().time() - t0 < 2:
                    try:
                        await asyncio.wait_for(ws.receive_str(), timeout=0.5)
                    except asyncio.TimeoutError:
                        break

                # Authenticate
                auth = json.dumps([
                    "auth",
                    {"session": session_token, "isDemo": 0, "uid": 0, "platform": 2},
                ])
                await ws.send_str(f"42{auth}")

                try:
                    msg = await asyncio.wait_for(ws.receive_str(), timeout=8)
                    logger.debug(f"PO auth response: {msg[:200]}")
                except asyncio.TimeoutError:
                    pass

                # Request candle history
                await ws.send_str(
                    f'42{json.dumps(["changeSymbol", {"asset": po_asset, "period": 60}])}'
                )
                await ws.send_str(
                    f'42{json.dumps(["subscribeMessage", {"action": "changeSymbol", "message": {"asset": po_asset, "period": 60}}])}'
                )

                # Collect candles (up to 15 s)
                candles: List[Tuple] = []
                deadline = asyncio.get_event_loop().time() + 15

                while asyncio.get_event_loop().time() < deadline:
                    try:
                        raw_msg = await asyncio.wait_for(ws.receive(), timeout=3)

                        if raw_msg.type == aiohttp.WSMsgType.TEXT:
                            text = raw_msg.data
                            if text == "2":
                                await ws.send_str("3")
                                continue
                            result = _parse_sio_message(text)
                            if result:
                                candles.extend(result)
                                logger.info(f"PO got {len(result)} candles for {po_asset} (total={len(candles)})")
                                if len(candles) >= 30:
                                    break

                        elif raw_msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            break

                    except asyncio.TimeoutError:
                        break

                if candles:
                    candles.sort(key=lambda x: x[0])
                    return candles[-limit:]

                logger.warning(f"PO WS: no candles received for {po_asset}")
                return None

    except Exception as e:
        logger.error(f"PO WebSocket error ({po_asset}): {e}")
        return None


def fetch_otc_candles(session_token: str, po_symbol: str, limit: int = 100) -> Optional[List[Tuple]]:
    """
    Sync entry point. Accepts either a PO internal symbol (e.g. 'EURUSD_otc')
    or a display name (e.g. 'EUR/USD-OTC').
    Returns list of (unix_timestamp, close, volume) tuples sorted oldest→newest.
    """
    # Resolve display name → po_symbol using discovered asset map
    if not po_symbol.endswith("_otc"):
        with _discovery_lock:
            reverse = {v: k for k, v in _discovered_assets.items()}
        po_symbol = reverse.get(po_symbol, po_symbol)

    result_holder: List[Optional[List[Tuple]]] = [None]

    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result_holder[0] = loop.run_until_complete(
                _fetch_async(session_token, po_symbol, limit)
            )
        except Exception as e:
            logger.error(f"WS thread error: {e}")
        finally:
            loop.close()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=30)
    return result_holder[0]


# Keep OTC_SYMBOL_MAP for backward-compat references (used as fallback)
OTC_SYMBOL_MAP = {
    "EUR/USD-OTC": "EURUSD_otc",
    "GBP/USD-OTC": "GBPUSD_otc",
    "USD/JPY-OTC": "USDJPY_otc",
    "AUD/USD-OTC": "AUDUSD_otc",
    "USD/CAD-OTC": "USDCAD_otc",
    "USD/CHF-OTC": "USDCHF_otc",
    "NZD/USD-OTC": "NZDUSD_otc",
    "EUR/GBP-OTC": "EURGBP_otc",
    "EUR/JPY-OTC": "EURJPY_otc",
    "GBP/JPY-OTC": "GBPJPY_otc",
    "AUD/JPY-OTC": "AUDJPY_otc",
    "CAD/JPY-OTC": "CADJPY_otc",
    "CHF/JPY-OTC": "CHFJPY_otc",
    "GBP/AUD-OTC": "GBPAUD_otc",
    "GBP/CAD-OTC": "GBPCAD_otc",
    "GBP/CHF-OTC": "GBPCHF_otc",
    "GBP/NZD-OTC": "GBPNZD_otc",
    "AUD/CAD-OTC": "AUDCAD_otc",
    "AUD/CHF-OTC": "AUDCHF_otc",
    "AUD/NZD-OTC": "AUDNZD_otc",
    "EUR/CAD-OTC": "EURCAD_otc",
    "EUR/CHF-OTC": "EURCHF_otc",
    "EUR/NZD-OTC": "EURNZD_otc",
    "EUR/AUD-OTC": "EURAUD_otc",
    "CAD/CHF-OTC": "CADCHF_otc",
    "NZD/CAD-OTC": "NZDCAD_otc",
    "NZD/CHF-OTC": "NZDCHF_otc",
    "NZD/JPY-OTC": "NZDJPY_otc",
    "XAU/USD-OTC": "XAUUSD_otc",
    "XAG/USD-OTC": "XAGUSD_otc",
    "BTC/USD-OTC":  "BTCUSD_otc",
    "ETH/USD-OTC":  "ETHUSD_otc",
    "LTC/USD-OTC":  "LTCUSD_otc",
    "XRP/USD-OTC":  "XRPUSD_otc",
    "BCH/USD-OTC":  "BCHUSD_otc",
    "DOGE/USD-OTC": "DOGEUSD_otc",
    "ADA/USD-OTC":  "ADAUSD_otc",
    "SOL/USD-OTC":  "SOLUSD_otc",
    "DOT/USD-OTC":  "DOTUSD_otc",
    "BNB/USD-OTC":  "BNBUSD_otc",
}
