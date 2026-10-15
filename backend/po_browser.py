"""
Persistent Playwright browser session for PocketOption.
Keeps a real Chrome browser logged into PO's trading page,
intercepts its WebSocket frames, and caches candle data for all assets.
"""

import asyncio
import json
import logging
import threading
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Global thread-safe candle cache: po_symbol → [(ts, close, vol), ...]
_candle_cache: Dict[str, List[Tuple]] = {}
_cache_lock  = threading.Lock()
_session_running = False
_session_token: Optional[str] = None

# PO internal symbols to cycle through (populated from OTC_SYMBOL_MAP)
_ASSETS: List[str] = []

# Extra cookies to inject alongside lo_uid
_PO_COOKIES: List[Dict] = []

# JS injected before page load — patches WebSocket to expose it to Python
_WS_PATCH = """
window.__poWS = [];
const _OrigWS = window.WebSocket;
class PatchedWS extends _OrigWS {
    constructor(url, protocols) {
        super(url, protocols);
        if (typeof url === 'string' && url.includes('po.market')) {
            window.__poWS.push(this);
        }
    }
}
window.WebSocket = PatchedWS;
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_candles(po_symbol: str, limit: int = 100) -> Optional[List[Tuple]]:
    with _cache_lock:
        data = _candle_cache.get(po_symbol)
        return data[-limit:] if data else None


def is_running() -> bool:
    return _session_running


def get_cached_symbols() -> List[str]:
    with _cache_lock:
        return list(_candle_cache.keys())


def start_browser_session(session_token: str, extra_cookies: List[Dict] = None):
    """Launch the background browser thread (non-blocking)."""
    global _session_token, _ASSETS, _PO_COOKIES
    _session_token = session_token
    _PO_COOKIES = extra_cookies or []

    # Build asset list from OTC_SYMBOL_MAP
    try:
        from po_websocket import OTC_SYMBOL_MAP
        _ASSETS = list(OTC_SYMBOL_MAP.values())
    except Exception:
        _ASSETS = ["EURUSD_otc", "GBPUSD_otc", "USDJPY_otc", "AUDUSD_otc",
                   "USDCAD_otc", "USDCHF_otc", "NZDUSD_otc", "EURGBP_otc",
                   "EURJPY_otc", "GBPJPY_otc"]

    t = threading.Thread(target=_thread_main, args=(session_token,),
                         daemon=True, name="PO-Browser")
    t.start()
    logger.info(f"PO Browser: session thread started ({len(_ASSETS)} assets to cycle)")


# ---------------------------------------------------------------------------
# Frame parser
# ---------------------------------------------------------------------------

def _parse_frame(text: str):
    """Extract candle data from a Socket.IO text frame and update cache."""
    try:
        raw = text
        for prefix in ("451-[", "451-", "42"):
            if raw.startswith(prefix):
                raw = raw[len(prefix):]
                if prefix == "451-[":
                    raw = "[" + raw
                break

        data = json.loads(raw)
        if not isinstance(data, list) or len(data) < 2:
            return

        event, payload = data[0], data[1]
        if event not in ("loadHistoryPeriod", "successChangeSymbol",
                         "updateHistoryNew", "updateHistory", "changeSymbol"):
            return
        if not isinstance(payload, dict):
            return

        asset   = payload.get("asset", "")
        history = (payload.get("history") or payload.get("candles")
                   or payload.get("data") or [])

        candles: List[Tuple] = []
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

        if candles and asset:
            candles.sort(key=lambda x: x[0])
            with _cache_lock:
                _candle_cache[asset] = candles[-100:]
            logger.info(f"PO Browser: cached {len(candles)} candles for {asset}")

    except Exception as e:
        logger.debug(f"PO Browser frame parse: {e}")


# ---------------------------------------------------------------------------
# Async browser session
# ---------------------------------------------------------------------------

async def _browser_session(session_token: str):
    global _session_running

    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
                "--memory-pressure-off",
            ],
        )

        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 720},
        )

        # Inject WebSocket patch before any page script runs
        await ctx.add_init_script(_WS_PATCH)

        # Set session cookies
        cookies = [{"name": "lo_uid", "value": session_token,
                    "domain": ".pocketoption.com", "path": "/", "secure": True}]
        cookies.extend(_PO_COOKIES)
        await ctx.add_cookies(cookies)
        logger.info(f"PO Browser: set {len(cookies)} cookies")

        page = await ctx.new_page()

        # Attach frame listener before navigation
        def _on_ws(ws):
            if "po.market" not in ws.url:
                return
            logger.info(f"PO Browser: WS opened → {ws.url[:80]}")

            def _on_frame(payload):
                text = payload if isinstance(payload, str) else ""
                if text:
                    _parse_frame(text)

            ws.on("framereceived", _on_frame)

        page.on("websocket", _on_ws)

        # Step 1: load root to let autologin cookie establish a fresh session
        logger.info("PO Browser: navigating to trading page…")
        try:
            await page.goto(
                "https://pocketoption.com/",
                wait_until="domcontentloaded",
                timeout=60_000,
            )
        except Exception as e:
            logger.error(f"PO Browser: root navigation failed: {e}")
            await browser.close()
            return

        logger.info(f"PO Browser: root loaded → {page.url}")
        await asyncio.sleep(5)  # let autologin create a fresh ci_session

        # Log which session cookies were set after autologin
        try:
            all_cookies = await ctx.cookies()
            po_cookies = {c["name"]: c["value"][:30] for c in all_cookies
                          if "pocketoption" in c.get("domain", "")}
            logger.info(f"PO Browser: post-root cookies: {list(po_cookies.keys())}")
            has_session = "ci_session" in po_cookies or "PHPSESSID" in po_cookies
            logger.info(f"PO Browser: has new session={has_session}")
        except Exception as e:
            logger.warning(f"PO Browser: cookie check failed: {e}")

        # Step 2: navigate to the actual trading platform
        try:
            await page.goto(
                "https://pocketoption.com/en/cabinet/demo-quick-high-low/",
                wait_until="domcontentloaded",
                timeout=60_000,
            )
        except Exception as e:
            logger.error(f"PO Browser: trading page navigation failed: {e}")
            await browser.close()
            return

        logger.info(f"PO Browser: loaded → {page.url}")

        # Wait for the trading platform JS to fully boot and open WebSocket
        await asyncio.sleep(20)

        # Debug: check what loaded and how many WebSockets were captured
        try:
            title    = await page.title()
            ws_count = await page.evaluate("(window.__poWS || []).length")
            ws_states = await page.evaluate(
                "((window.__poWS || []).map(w => w.readyState))"
            )
            logger.info(f"PO Browser: title='{title}' | WS captured={ws_count} states={ws_states}")
            await page.screenshot(path="/tmp/po_browser_debug.png", full_page=False)
            logger.info("PO Browser: screenshot → /tmp/po_browser_debug.png")
        except Exception as e:
            logger.warning(f"PO Browser debug check failed: {e}")

        _session_running = True
        logger.info("PO Browser: ready — starting asset rotation")

        # Send changeSymbol for each asset in a cycle
        asset_idx = 0
        heartbeat  = 0

        while True:
            asset = _ASSETS[asset_idx % len(_ASSETS)]
            msg   = json.dumps(["changeSymbol", {"asset": asset, "period": 60}])

            try:
                sent = await page.evaluate(f"""
                    (() => {{
                        const sockets = window.__poWS || [];
                        let ok = false;
                        for (const ws of sockets) {{
                            if (ws.readyState === 1) {{
                                ws.send('42{msg}');
                                ok = true;
                            }}
                        }}
                        return ok;
                    }})()
                """)
                if sent:
                    logger.debug(f"PO Browser → {asset}")
                else:
                    logger.debug(f"PO Browser: no open WS for {asset}")
            except Exception as e:
                logger.debug(f"PO Browser send error ({asset}): {e}")

            asset_idx += 1
            heartbeat += 1

            # 0.8 s between requests → full 40-asset cycle ≈ 32 s
            await asyncio.sleep(0.8)

            # Heartbeat: keep page alive and check health every ~5 min
            if heartbeat % 375 == 0:
                try:
                    await page.evaluate("document.title")
                    cached = len(_candle_cache)
                    logger.info(f"PO Browser heartbeat: {cached} assets cached")
                except Exception:
                    logger.warning("PO Browser: page unresponsive — restarting")
                    break

        _session_running = False
        await browser.close()


# ---------------------------------------------------------------------------
# Thread entry point (auto-restarts on crash)
# ---------------------------------------------------------------------------

def _thread_main(session_token: str):
    global _session_running

    while True:
        _session_running = False
        logger.info("PO Browser: starting session…")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_browser_session(session_token))
        except Exception as e:
            logger.error(f"PO Browser thread error: {e}")
        finally:
            loop.close()

        logger.info("PO Browser: session ended — restarting in 30 s")
        _session_running = False
        time.sleep(30)
