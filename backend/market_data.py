"""
Market data fetching module.
Retrieves live 1-minute candle data from Gate.io public API.
"""

import requests
import logging
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

GATEIO_BASE_URL = "https://api.gateio.ws/api/v4"


def _to_gateio_pair(symbol: str) -> str:
    """Convert BTCUSDT → BTC_USDT for Gate.io API."""
    if symbol.endswith("USDT"):
        return symbol[:-4] + "_USDT"
    return symbol


class MarketDataFetcher:
    """Fetch market data from Gate.io public API."""

    BASE_URL = GATEIO_BASE_URL
    TIMEOUT = 10

    @staticmethod
    def fetch_klines(symbol: str, interval: str = "1m", limit: int = 100) -> Optional[List]:
        """
        Fetch candlestick data from Gate.io.
        Gate.io candle format: [timestamp_sec, volume, close, high, low, open, is_closed]
        """
        try:
            url = f"{MarketDataFetcher.BASE_URL}/spot/candlesticks"
            params = {
                "currency_pair": _to_gateio_pair(symbol),
                "interval": interval,
                "limit": limit
            }
            response = requests.get(url, params=params, timeout=MarketDataFetcher.TIMEOUT)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching klines for {symbol}: {str(e)}")
            return None

    @staticmethod
    def parse_klines(klines: List) -> Tuple[List[float], List[float], List[float]]:
        """
        Parse Gate.io klines into OHLCV components.
        Format: [timestamp_sec, volume, close, high, low, open, is_closed]
        """
        closes = []
        volumes = []
        timestamps = []

        for kline in klines:
            timestamp = datetime.fromtimestamp(int(kline[0]), tz=IST)
            close = float(kline[2])
            volume = float(kline[1])

            timestamps.append(timestamp)
            closes.append(close)
            volumes.append(volume)

        return closes, volumes, timestamps

    @staticmethod
    def fetch_pair_analysis(symbol: str) -> Optional[Dict]:
        """Fetch and analyze data for a single trading pair."""
        klines = MarketDataFetcher.fetch_klines(symbol, "1m", 100)

        if not klines:
            logger.warning(f"No data retrieved for {symbol}")
            return None

        closes, volumes, timestamps = MarketDataFetcher.parse_klines(klines)

        if not closes:
            return None

        return {
            "symbol": symbol,
            "closes": closes,
            "volumes": volumes,
            "timestamps": timestamps,
            "current_price": closes[-1],
            "timestamp": timestamps[-1]
        }

    @staticmethod
    def fetch_all_pairs(pairs: List[str]) -> Dict[str, Dict]:
        """Fetch data for all trading pairs in parallel."""
        all_data = {}

        with ThreadPoolExecutor(max_workers=min(len(pairs), 10)) as executor:
            future_to_pair = {
                executor.submit(MarketDataFetcher.fetch_pair_analysis, pair): pair
                for pair in pairs
            }
            for future in as_completed(future_to_pair):
                pair = future_to_pair[future]
                try:
                    data = future.result()
                    if data:
                        all_data[pair] = data
                        logger.info(f"Successfully fetched data for {pair}")
                    else:
                        logger.warning(f"Failed to fetch data for {pair}")
                except Exception as e:
                    logger.error(f"Exception fetching {pair}: {e}")

        return all_data

    @staticmethod
    def get_current_server_time() -> datetime:
        """Get current server time (local clock, no external dependency)."""
        return datetime.now(IST)

    @staticmethod
    def calculate_next_candle_time(current_time: datetime) -> Tuple[datetime, datetime]:
        """Calculate entry and expiry times for the next 1-minute candle."""
        next_minute = current_time.replace(second=0, microsecond=0)
        if current_time.second > 0 or current_time.microsecond > 0:
            next_minute += timedelta(minutes=1)

        entry_time = next_minute
        expiry_time = next_minute + timedelta(minutes=1)

        return entry_time, expiry_time
