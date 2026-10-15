"""
Pocket Option integration module.
Fetches OTC candle data via PO WebSocket (primary).
Falls back to Yahoo Finance for live pairs if WebSocket fails.
"""

import requests
import logging
from typing import Dict, Optional, List, Tuple
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_UTC = timezone.utc

from po_websocket import fetch_otc_candles, OTC_SYMBOL_MAP, discover_assets, get_cached_assets

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")

# Yahoo Finance fallback for live pairs
YAHOO_SYMBOL_MAP = {
    # Major Forex
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "USDJPY=X",
    "AUD/USD": "AUDUSD=X",
    "USD/CAD": "USDCAD=X",
    "USD/CHF": "USDCHF=X",
    "NZD/USD": "NZDUSD=X",
    # Minor Forex
    "EUR/GBP": "EURGBP=X",
    "EUR/JPY": "EURJPY=X",
    "GBP/JPY": "GBPJPY=X",
    "AUD/JPY": "AUDJPY=X",
    "CAD/JPY": "CADJPY=X",
    "CHF/JPY": "CHFJPY=X",
    "GBP/AUD": "GBPAUD=X",
    "GBP/CAD": "GBPCAD=X",
    "GBP/CHF": "GBPCHF=X",
    "GBP/NZD": "GBPNZD=X",
    "AUD/CAD": "AUDCAD=X",
    "AUD/CHF": "AUDCHF=X",
    "AUD/NZD": "AUDNZD=X",
    "EUR/CAD": "EURCAD=X",
    "EUR/CHF": "EURCHF=X",
    "EUR/NZD": "EURNZD=X",
    "EUR/AUD": "EURAUD=X",
    "CAD/CHF": "CADCHF=X",
    "NZD/CAD": "NZDCAD=X",
    "NZD/CHF": "NZDCHF=X",
    "NZD/JPY": "NZDJPY=X",
    # Commodities
    "XAU/USD": "GC=F",
    "XAG/USD": "SI=F",
    # Crypto
    "BTC/USD":  "BTC-USD",
    "ETH/USD":  "ETH-USD",
    "LTC/USD":  "LTC-USD",
    "XRP/USD":  "XRP-USD",
    "BCH/USD":  "BCH-USD",
    "DOGE/USD": "DOGE-USD",
    "ADA/USD":  "ADA-USD",
    "SOL/USD":  "SOL-USD",
    "DOT/USD":  "DOT-USD",
    "BNB/USD":  "BNB-USD",
}

_YF_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}


class PocketOptionSessionManager:
    """Stores and tracks the Pocket Option lo_uid session token."""

    def __init__(self, session_token: str):
        """
        Args:
            session_token: Value of the lo_uid cookie from Pocket Option.
        """
        self.session_token = session_token
        self.session_created = datetime.now(_UTC)
        self.last_activity = datetime.now(_UTC)
        self.is_active = True
        logger.info(f"PO session registered (…{session_token[-10:]})")

    def update_activity(self):
        self.last_activity = datetime.now(_UTC)

    def get_session_age(self) -> int:
        return int((datetime.now(_UTC) - self.session_created).total_seconds())

    def get_session_status(self) -> Dict:
        return {
            "active": self.is_active,
            "age_seconds": self.get_session_age(),
            "last_activity": self.last_activity.isoformat(),
            "created_at": self.session_created.isoformat(),
        }

    def shutdown(self):
        self.is_active = False


class PocketOptionDataFetcher:
    """
    Fetches 1-minute OHLCV data from Yahoo Finance for Pocket Option assets.
    Forex pairs are available during market hours (Mon–Fri).
    """

    TIMEOUT = 10

    def __init__(self, session_manager: PocketOptionSessionManager):
        self.session_manager = session_manager

    def fetch_klines(self, asset_name: str, limit: int = 100) -> Optional[List[Tuple]]:
        """
        Fetch 1-minute candles.
        Priority: PO Browser session → PO WebSocket → Yahoo Finance fallback.
        Returns list of (unix_timestamp, close, volume) tuples, oldest first.
        """
        # Check discovered assets first, then fall back to static map
        cached = get_cached_assets()
        is_otc = asset_name in cached or asset_name in OTC_SYMBOL_MAP

        if is_otc:
            po_symbol = OTC_SYMBOL_MAP.get(asset_name)

            # Priority 1: relay cache (real PO data from user's local machine)
            try:
                from app import (relay_candle_cache, relay_latest_prices,
                                 relay_cache_timestamp, RELAY_STALE_SECONDS)
                from datetime import datetime, timezone as tz
                if relay_cache_timestamp and po_symbol:
                    age = (datetime.now(tz.utc) - relay_cache_timestamp).total_seconds()
                    if age < RELAY_STALE_SECONDS:
                        data = relay_candle_cache.get(po_symbol)
                        if data:
                            candles = list(data)[-limit:]
                            # Patch last candle's close with the live tick price
                            live = relay_latest_prices.get(po_symbol)
                            if live and candles:
                                last = candles[-1]
                                candles[-1] = (last[0], live, last[2] if len(last) > 2 else 0)
                                logger.info(f"Relay hit: {asset_name} | "
                                            f"candle_close={last[1]:.5f} live={live:.5f}")
                            else:
                                logger.info(f"Relay hit: {asset_name} ({len(candles)} candles)")
                            return candles
            except Exception:
                pass

            # No live relay data for this OTC pair — skip it instead of
            # substituting Yahoo Finance data. PO's active OTC roster shifts
            # constantly (see live "Currencies" list in the app), and a
            # synthetic substitute can produce signals for pairs that aren't
            # actually tradeable on PO right now. Only pairs the relay has
            # captured real candles for (i.e. confirmed active on PO) qualify.
            logger.debug(f"No live relay data for {asset_name} — skipping "
                         f"(not confirmed active on Pocket Option)")
            return None

        # Yahoo Finance path (live pairs only)
        yf_symbol = YAHOO_SYMBOL_MAP.get(asset_name)
        if not yf_symbol:
            logger.warning(f"No Yahoo Finance mapping for: {asset_name}")
            return None

        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_symbol}"
            response = requests.get(
                url,
                params={"interval": "1m", "range": "1d"},
                headers=_YF_HEADERS,
                timeout=self.TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()

            result = data["chart"]["result"][0]
            timestamps = result["timestamp"]
            q = result["indicators"]["quote"][0]
            closes = q["close"]
            volumes = q.get("volume", [0] * len(closes))

            candles = [
                (t, c, v or 0.0)
                for t, c, v in zip(timestamps, closes, volumes)
                if c is not None
            ]

            return candles[-limit:] if len(candles) > limit else candles

        except Exception as e:
            logger.error(f"Yahoo Finance fetch failed for {asset_name}: {e}")
            return None

    def parse_klines(
        self, klines: List[Tuple]
    ) -> Tuple[List[float], List[float], List[datetime]]:
        closes, volumes, timestamps = [], [], []
        for t, c, v in klines:
            timestamps.append(datetime.fromtimestamp(t, tz=IST))
            closes.append(float(c))
            volumes.append(float(v))
        return closes, volumes, timestamps

    def fetch_asset_analysis(self, asset_id: str, asset_name: str) -> Optional[Dict]:
        self.session_manager.update_activity()

        klines = self.fetch_klines(asset_name)
        if not klines:
            return None

        closes, volumes, timestamps = self.parse_klines(klines)

        if len(closes) < 30:
            logger.warning(f"Too few candles for {asset_name}: {len(closes)}")
            return None

        return {
            "asset_id": asset_id,
            "asset_name": asset_name,
            "symbol": asset_name,       # analysis.py reads "symbol"
            "closes": closes,
            "volumes": volumes,
            "timestamps": timestamps,
            "current_price": closes[-1],
            "timestamp": timestamps[-1],
        }

    def fetch_all_assets(self, asset_list: List[Dict]) -> Dict[str, Dict]:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        # Use dynamically discovered assets if available, else fall back to asset_list
        cached = get_cached_assets()
        if cached:
            # Build list from discovered PO assets: display_name as both id and name
            eligible = [
                {"id": po_sym, "name": display}
                for po_sym, display in cached.items()
            ]
            logger.info(f"Using {len(eligible)} dynamically discovered PO assets")
        else:
            eligible = [
                a for a in asset_list
                if a.get("id") and a.get("name")
                and (a["name"] in OTC_SYMBOL_MAP or a["name"] in YAHOO_SYMBOL_MAP)
            ]
            logger.info(f"Using {len(eligible)} assets from static fallback list")

        all_data: Dict[str, Dict] = {}

        def _fetch_one(asset):
            return asset["name"], self.fetch_asset_analysis(asset["id"], asset["name"])

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {pool.submit(_fetch_one, a): a for a in eligible}
            for future in as_completed(futures):
                asset_name, data = future.result()
                if data:
                    all_data[asset_name] = data
                    logger.info(f"Fetched {asset_name}")
                else:
                    logger.warning(f"No data for {asset_name}")

        return all_data

    def get_current_server_time(self) -> datetime:
        return datetime.now(IST)

    def calculate_next_candle_time(
        self, current_time: datetime
    ) -> Tuple[datetime, datetime]:
        nxt = current_time.replace(second=0, microsecond=0)
        if current_time.second > 0 or current_time.microsecond > 0:
            nxt += timedelta(minutes=1)
        return nxt, nxt + timedelta(minutes=1)
