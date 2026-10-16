"""
FastAPI application - Main entry point for the trading signal system.
Supports both Binance API and Pocket Option data sources.
Provides REST API endpoints for signal generation with session management.
"""

import asyncio
import logging
import secrets
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

# BinaryOptionsToolsV2 0.2.9 Linux build removed Logger.warn but still
# calls it internally. Patch it back before any import of the library.
try:
    import BinaryOptionsToolsV2 as _botv2
    if hasattr(_botv2, 'Logger') and not hasattr(_botv2.Logger, 'warn'):
        _botv2.Logger.warn = _botv2.Logger.info
except Exception:
    pass
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Depends, Header, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Literal
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from config import (
    HOST, PORT, ALLOWED_ORIGINS, ADMIN_KEY,
    LOG_LEVEL, LOG_FORMAT, TRADING_PAIRS, BYPASS_TRADER_ID
)
import telegram_service
import notifications
import performers
from market_data import MarketDataFetcher
from analysis import SignalAnalyzer
from pocket_option_api import PocketOptionSessionManager, PocketOptionDataFetcher
from pocket_option_config import POCKET_OPTION_ASSETS, POCKET_OPTION_CONFIDENCE_WEIGHTS
from timezone_utils import DEFAULT_TIMEZONE, is_valid_timezone, normalize_timezone, timezone_catalog
from trader_store import (
    get_timezone, set_timezone, claim_session, touch_session, release_session,
    trader_for_token, get_telegram_joined, set_telegram_joined, was_replaced,
    list_telegram_joined, reset_telegram_joined,
)

# Configure logging
logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
logger = logging.getLogger(__name__)

# Rate limiter (keyed by client IP)
limiter = Limiter(key_func=get_remote_address)

# Initialize FastAPI app
app = FastAPI(
    title="Trading Signal System",
    description="Generate 1-minute binary trading signals from multiple data sources",
    version="3.0.0"
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization", "X-Admin-Key"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add standard HTTP security headers to every response."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


async def verify_admin_key(x_admin_key: Optional[str] = Header(None)):
    """
    Dependency that enforces X-Admin-Key header on protected endpoints.
    If ADMIN_KEY env var is not set the endpoint is open (local dev only).
    """
    if not ADMIN_KEY:
        return  # no key configured — open access (dev mode)
    if x_admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")


def active_session_token(authorization: Optional[str] = Header(None)) -> str:
    """Validate and refresh the caller's active Trader ID session."""
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token or not touch_session(token):
        if token and was_replaced(token):
            raise HTTPException(
                status_code=401,
                detail="SESSION_REPLACED: This Trader ID signed in on another browser or device.",
            )
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    return token

# Request/Response models
class SignalResponse(BaseModel):
    """Signal response model."""
    pair: str
    direction: str
    entry_time: str
    expiry_time: str
    confidence: float
    current_price: float
    indicator_scores: Dict[str, float]
    generated_at: str
    candle_duration: str
    data_source: str
    chart_candles: List[Dict[str, float]] = []
    entry_timestamp: str
    expiry_timestamp: str
    generated_timestamp: str


class ServerTimeResponse(BaseModel):
    """Server time response model."""
    server_time: str
    unix_timestamp: int
    next_candle_entry: str
    next_candle_expiry: str
    server_timestamp: str
    next_candle_entry_timestamp: str
    next_candle_expiry_timestamp: str


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str
    timestamp: str
    pairs_monitored: int
    data_source: str
    session_active: bool


class ConfigRequest(BaseModel):
    """Configuration request model."""
    data_source: Literal["binance", "pocket_option"]
    session_token: Optional[str] = None


# Global state
market_data_cache: Dict = {}
cache_timestamp: Optional[datetime] = None
CACHE_DURATION_SECONDS = 60

# Relay cache: candle data pushed from user's local machine (real PO data)
# po_symbol → [(timestamp, close, volume), ...]
relay_candle_cache: Dict = {}
relay_latest_prices: Dict = {}   # po_symbol → latest real-time price
relay_cache_timestamp: Optional[datetime] = None
RELAY_STALE_SECONDS = 300  # treat cache as stale if not updated in 5 min

# Only fiat currencies — filters out crypto (BTC, ETH…) and commodities (XAU, XAG…)
_FOREX_CURRENCIES = {"EUR", "USD", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"}

def _is_forex_pair(po_symbol: str) -> bool:
    """Return True only if both legs of the pair are fiat currencies."""
    base = po_symbol.replace("_otc", "").upper()
    for quote in sorted(_FOREX_CURRENCIES, key=len, reverse=True):
        if base.endswith(quote) and len(base) > len(quote):
            return base[: -len(quote)] in _FOREX_CURRENCIES
    return False

# Current data source configuration
current_config = {
    "data_source": "binance",  # Default to binance
    "session_manager": None,
    "data_fetcher": None,
    "assets": None
}


def _init_pocket_option(token: str):
    """Initialise global PO session from a token string."""
    session_manager = PocketOptionSessionManager(token)
    data_fetcher    = PocketOptionDataFetcher(session_manager)
    current_config["data_source"]     = "pocket_option"
    current_config["session_manager"] = session_manager
    current_config["data_fetcher"]    = data_fetcher
    current_config["assets"]          = POCKET_OPTION_ASSETS


async def _po_data_loop(token: str) -> None:
    """
    Background asyncio task: connects to PO via BinaryOptionsToolsV2,
    fetches high-payout asset candles every 60 s, and writes directly
    into relay_candle_cache / relay_latest_prices.
    Reconnects automatically on any connection error.
    """
    global relay_candle_cache, relay_latest_prices, relay_cache_timestamp

    from BinaryOptionsToolsV2.config import Config
    from BinaryOptionsToolsV2.pocketoption import PocketOptionAsync

    MIN_PAYOUT  = 80
    PERIOD      = 60    # 1-minute candles
    DURATION    = 9000  # 150 candles — enough for RSI Wilder EMA to fully converge
    FETCH_DELAY = 0.5   # seconds between per-asset fetches
    MAX_EMPTY_CYCLES = 2  # consecutive all-fetches-failed cycles before forcing reconnect
    ACTIVE_ASSETS_TIMEOUT = 20  # seconds — bounds api.active_assets()
    GET_CANDLES_TIMEOUT   = 15  # seconds — bounds api.get_candles()

    config = Config(connection_initialization_timeout_secs=20)

    while True:
        try:
            async with PocketOptionAsync(token, config=config) as api:
                logger.info("PO data loop: connected via BinaryOptionsToolsV2")
                await asyncio.sleep(5)   # let connection settle
                consecutive_empty_cycles = 0

                while True:
                    selected = []
                    success_count = 0
                    active_assets_failed = False
                    try:
                        active = await asyncio.wait_for(
                            api.active_assets(), timeout=ACTIVE_ASSETS_TIMEOUT
                        )
                        selected = [a for a in active if a.get("payout", 0) >= MIN_PAYOUT]
                        logger.info(
                            f"PO data loop: {len(active)} total assets, "
                            f"{len(selected)} with payout≥{MIN_PAYOUT}%"
                        )

                        # Keep only forex (fiat/fiat) pairs — skip crypto and commodities
                        selected = [a for a in selected if _is_forex_pair(a.get("symbol", ""))]
                        logger.info(f"PO data loop: {len(selected)} forex pairs after filter")

                        # Drop assets that are no longer active/eligible
                        current_symbols = {a.get("symbol") for a in selected if a.get("symbol")}
                        for old_sym in list(relay_candle_cache.keys()):
                            if old_sym not in current_symbols:
                                del relay_candle_cache[old_sym]
                                relay_latest_prices.pop(old_sym, None)
                                logger.info(f"PO data loop: evicted stale asset {old_sym}")

                        for asset in selected:
                            symbol = asset.get("symbol", "")
                            if not symbol:
                                continue
                            try:
                                candles = await asyncio.wait_for(
                                    api.get_candles(symbol, PERIOD, DURATION),
                                    timeout=GET_CANDLES_TIMEOUT,
                                )
                                if candles:
                                    parsed = []
                                    for c in candles:
                                        t  = c.get("timestamp") or c.get("time")
                                        cl = c.get("close")
                                        if t is not None and cl is not None:
                                            parsed.append([int(float(t)), float(cl), 0.0])
                                    if parsed:
                                        parsed.sort(key=lambda x: x[0])
                                        relay_candle_cache[symbol]  = parsed[-200:]
                                        relay_latest_prices[symbol] = parsed[-1][1]
                                        success_count += 1
                            except Exception as e:
                                logger.error(f"PO data loop: fetch error for {symbol}: {e}")

                            await asyncio.sleep(FETCH_DELAY)

                    except Exception as e:
                        logger.error(f"PO data loop: inner error: {e}")
                        active_assets_failed = True

                    # Only mark the cache fresh if something actually updated this
                    # cycle. BinaryOptionsToolsV2's WebSocket channel can die
                    # silently ("half closed channel") — every get_candles call
                    # then fails forever without this check, relay_cache_timestamp
                    # kept refreshing on frozen data, and /signal kept serving the
                    # same stale winner indefinitely instead of detecting staleness.
                    # active_assets() itself can also hang on a dead channel without
                    # raising — the wait_for timeout above turns that into an
                    # exception so it counts toward the same reconnect threshold.
                    if active_assets_failed:
                        consecutive_empty_cycles += 1
                        logger.warning(
                            f"PO data loop: active_assets() failed/timed out "
                            f"(consecutive empty cycles={consecutive_empty_cycles})"
                        )
                        if consecutive_empty_cycles >= MAX_EMPTY_CYCLES:
                            raise ConnectionError(
                                "PO data loop: repeated active_assets() failures — forcing reconnect"
                            )
                    elif success_count > 0:
                        relay_cache_timestamp = datetime.now(timezone.utc)
                        consecutive_empty_cycles = 0
                        logger.info(
                            f"PO data loop: cache updated — {len(relay_candle_cache)} assets "
                            f"({success_count}/{len(selected)} refreshed)"
                        )
                    elif selected:
                        # Had candidates but every single fetch failed — the
                        # channel is almost certainly dead. Force a reconnect
                        # instead of repeating the same failure forever.
                        consecutive_empty_cycles += 1
                        logger.warning(
                            f"PO data loop: 0/{len(selected)} fetches succeeded "
                            f"(consecutive empty cycles={consecutive_empty_cycles})"
                        )
                        if consecutive_empty_cycles >= MAX_EMPTY_CYCLES:
                            raise ConnectionError(
                                "PO data loop: channel appears dead — forcing reconnect"
                            )
                    else:
                        logger.info("PO data loop: no assets currently meet payout/forex filter")

                    await asyncio.sleep(60)

        except Exception as e:
            logger.error(f"PO data loop: connection lost ({e}) — reconnecting in 30s")
            await asyncio.sleep(30)


@app.on_event("startup")
async def startup_event():
    """
    Startup order:
      1. PO_SESSION_TOKEN or LO_UID env var → Pocket Option mode
         (BinaryOptionsToolsV2 background loop feeds relay_candle_cache)
      2. Neither → Gate.io crypto mode
    """
    import os
    logger.info("Trading Signal System starting up...")

    po_token = (
        os.environ.get("PO_SESSION_TOKEN", "").strip()
        or os.environ.get("LO_UID", "").strip()
    )

    if po_token:
        _init_pocket_option(po_token)
        asyncio.create_task(_po_data_loop(po_token))
        logger.info("Started in Pocket Option mode — BinaryOptionsToolsV2 data loop running")
    else:
        logger.info("No PO token — using Gate.io (crypto) mode")
        update_binance_cache()

    # Daily "time to trade" reminder for traders who enabled notifications.
    asyncio.create_task(notifications.daily_loop())


@app.post("/config/data-source")
@limiter.limit("5/minute")
async def configure_data_source(
    request: Request,
    config: ConfigRequest,
    _: None = Depends(verify_admin_key),
):
    """
    Configure data source (Binance or Pocket Option).
    
    Args:
        config: Configuration with data source and optional session token
        
    Returns:
        Configuration status
    """
    try:
        if config.data_source == "binance":
            current_config["data_source"] = "binance"
            current_config["session_manager"] = None
            current_config["data_fetcher"] = None
            update_binance_cache()
            
            return {
                "status": "success",
                "message": "Switched to Binance API",
                "data_source": "binance"
            }
        
        elif config.data_source == "pocket_option":
            if not config.session_token:
                raise HTTPException(
                    status_code=400,
                    detail="Session token required for Pocket Option"
                )
            
            # Initialize Pocket Option session
            session_manager = PocketOptionSessionManager(config.session_token)
            data_fetcher = PocketOptionDataFetcher(session_manager)
            
            current_config["data_source"] = "pocket_option"
            current_config["session_manager"] = session_manager
            current_config["data_fetcher"] = data_fetcher
            current_config["assets"] = POCKET_OPTION_ASSETS
            
            logger.info("Switched to Pocket Option API with session token")
            
            return {
                "status": "success",
                "message": "Switched to Pocket Option API",
                "data_source": "pocket_option",
                "session_status": session_manager.get_session_status()
            }
        
        else:
            raise HTTPException(
                status_code=400,
                detail="Invalid data source. Use 'binance' or 'pocket_option'"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Configuration error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to configure data source"
        )


def update_binance_cache():
    """Update market data cache from Binance API."""
    global market_data_cache, cache_timestamp
    
    try:
        logger.info("Updating Binance market data cache...")
        market_data_cache = MarketDataFetcher.fetch_all_pairs(TRADING_PAIRS)
        cache_timestamp = datetime.now(timezone.utc)
        logger.info(f"Cache updated with {len(market_data_cache)} pairs")
    
    except Exception as e:
        logger.error(f"Error updating Binance cache: {str(e)}")


def update_pocket_option_cache():
    """Update market data cache from Pocket Option API."""
    global market_data_cache, cache_timestamp
    
    try:
        if not current_config["data_fetcher"]:
            logger.error("Pocket Option data fetcher not initialized")
            return
        
        logger.info("Updating Pocket Option market data cache...")
        market_data_cache = current_config["data_fetcher"].fetch_all_assets(
            current_config["assets"]
        )
        cache_timestamp = datetime.now(timezone.utc)
        logger.info(f"Cache updated with {len(market_data_cache)} assets")
    
    except Exception as e:
        logger.error(f"Error updating Pocket Option cache: {str(e)}")


def is_cache_valid() -> bool:
    """Check if cached market data is still valid."""
    global cache_timestamp
    
    if cache_timestamp is None:
        return False
    
    age = (datetime.now(timezone.utc) - cache_timestamp).total_seconds()
    return age < CACHE_DURATION_SECONDS


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Health check endpoint.
    
    Returns:
        Health status and system information
    """
    session_active = False
    if current_config["data_source"] == "pocket_option":
        session_active = current_config["session_manager"].is_active if current_config["session_manager"] else False
    
    data_source_name = "Binance" if current_config["data_source"] == "binance" else "Pocket Option"
    
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        pairs_monitored=len(market_data_cache) if market_data_cache else 0,
        data_source=data_source_name,
        session_active=session_active
    )


@app.get("/server-time", response_model=ServerTimeResponse, dependencies=[Depends(active_session_token)])
async def get_server_time() -> ServerTimeResponse:
    """
    Get current server time and next candle times.
    Used for frontend clock synchronization.
    
    Returns:
        Current server time and next candle entry/expiry times
    """
    try:
        if current_config["data_source"] == "binance":
            current_time = MarketDataFetcher.get_current_server_time()
            entry_time, expiry_time = MarketDataFetcher.calculate_next_candle_time(current_time)
        else:
            current_time = current_config["data_fetcher"].get_current_server_time()
            entry_time, expiry_time = current_config["data_fetcher"].calculate_next_candle_time(current_time)
        
        return ServerTimeResponse(
            server_time=current_time.strftime("%H:%M:%S"),
            unix_timestamp=int(current_time.timestamp()),
            next_candle_entry=entry_time.strftime("%H:%M:%S"),
            next_candle_expiry=expiry_time.strftime("%H:%M:%S"),
            server_timestamp=current_time.isoformat(),
            next_candle_entry_timestamp=entry_time.isoformat(),
            next_candle_expiry_timestamp=expiry_time.isoformat(),
        )
    
    except Exception as e:
        logger.error(f"Error getting server time: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve server time"
        )


@app.get("/signal", response_model=SignalResponse, dependencies=[Depends(active_session_token)])
@limiter.limit("30/minute")
async def get_signal(request: Request, background_tasks: BackgroundTasks) -> SignalResponse:
    """
    Generate trading signal for the next candle.

    Works with both Binance and Pocket Option data sources.

    Returns:
        Trading signal with pair, direction, timing, and confidence

    Raises:
        HTTPException: If signal generation fails
    """
    try:
        data_source = current_config["data_source"]

        # ── PO mode: analyze relay_candle_cache directly (fresh every click) ──
        if data_source == "pocket_option" and relay_candle_cache:
            relay_age = (
                (datetime.now(timezone.utc) - relay_cache_timestamp).total_seconds()
                if relay_cache_timestamp else 9999
            )
            if relay_age < RELAY_STALE_SECONDS:
                from po_websocket import OTC_SYMBOL_MAP
                reverse_map = {v: k for k, v in OTC_SYMBOL_MAP.items()}

                all_analyses = []
                for po_symbol, candles in relay_candle_cache.items():
                    if not _is_forex_pair(po_symbol):
                        continue
                    if len(candles) < 60:
                        continue
                    closes = [float(c[1]) for c in candles]
                    live_price = relay_latest_prices.get(po_symbol, closes[-1])
                    display = reverse_map.get(po_symbol, po_symbol)
                    analysis = SignalAnalyzer.analyze_pair({
                        "symbol": display,
                        "closes": closes,
                        "current_price": live_price,
                    })
                    if analysis:
                        all_analyses.append(analysis)

                if not all_analyses:
                    raise HTTPException(status_code=503, detail="Could not analyze any PO assets")

                best_signal = SignalAnalyzer.select_best_signal(all_analyses)
                if not best_signal:
                    raise HTTPException(status_code=503, detail="No viable signals generated")

                current_time = current_config["data_fetcher"].get_current_server_time()
                entry_time, expiry_time = current_config["data_fetcher"].calculate_next_candle_time(current_time)
                signal = SignalAnalyzer.generate_signal(best_signal, entry_time, expiry_time)
                signal["data_source"] = "Pocket Option"
                selected_symbol = next(
                    (symbol for symbol, label in reverse_map.items() if label == best_signal["symbol"]),
                    None,
                )
                signal["chart_candles"] = [
                    {"time": candle[0], "close": candle[1]}
                    for candle in relay_candle_cache.get(selected_symbol, [])[-60:]
                ]
                logger.info(
                    f"Signal (relay-direct): {signal['pair']} {signal['direction']} "
                    f"confidence={signal['confidence']:.1f}% "
                    f"from {len(all_analyses)} assets"
                )
                return SignalResponse(**signal)

        # ── Binance / fallback path ──────────────────────────────────────────
        if not is_cache_valid():
            if data_source == "binance":
                update_binance_cache()
            else:
                update_pocket_option_cache()

        if not market_data_cache:
            raise HTTPException(
                status_code=503,
                detail="Market data unavailable. Please try again."
            )

        all_analyses = []
        for asset_name, data in market_data_cache.items():
            analysis = SignalAnalyzer.analyze_pair(data)
            if analysis:
                all_analyses.append(analysis)

        if not all_analyses:
            raise HTTPException(status_code=503, detail="Could not analyze any assets")

        best_signal = SignalAnalyzer.select_best_signal(all_analyses)
        if not best_signal:
            raise HTTPException(status_code=503, detail="No viable signals generated")

        if data_source == "binance":
            current_time = MarketDataFetcher.get_current_server_time()
            entry_time, expiry_time = MarketDataFetcher.calculate_next_candle_time(current_time)
        else:
            current_time = current_config["data_fetcher"].get_current_server_time()
            entry_time, expiry_time = current_config["data_fetcher"].calculate_next_candle_time(current_time)

        signal = SignalAnalyzer.generate_signal(best_signal, entry_time, expiry_time)
        signal["data_source"] = "Binance" if data_source == "binance" else "Pocket Option"
        signal["chart_candles"] = [
            {"time": candle[0], "close": candle[1]}
            for candle in market_data_cache.get(best_signal["symbol"], {}).get("candles", [])[-60:]
        ]

        if data_source == "binance":
            background_tasks.add_task(update_binance_cache)
        else:
            background_tasks.add_task(update_pocket_option_cache)

        logger.info(
            f"Signal generated from {signal['data_source']}: {signal['pair']} "
            f"{signal['direction']} at {signal['generated_at']} "
            f"(Confidence: {signal['confidence']:.1f}%)"
        )
        return SignalResponse(**signal)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in signal generation: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )


@app.get("/data-source", dependencies=[Depends(active_session_token)])
async def get_current_data_source() -> Dict:
    """
    Get current data source configuration.
    
    Returns:
        Current data source and configuration details
    """
    source = current_config["data_source"]
    
    result = {
        "data_source": source,
        "name": "Binance API" if source == "binance" else "Pocket Option API"
    }
    
    if source == "pocket_option" and current_config["session_manager"]:
        result["session_status"] = current_config["session_manager"].get_session_status()
    
    return result


@app.get("/pairs", dependencies=[Depends(active_session_token)])
async def get_available_pairs() -> Dict:
    source = current_config["data_source"]
    if source == "binance":
        return {"data_source": "binance", "pairs": TRADING_PAIRS}
    # PO mode: use relay cache if available
    if relay_candle_cache:
        return {
            "data_source": "pocket_option",
            "assets": list(relay_candle_cache.keys()),
            "total": len(relay_candle_cache),
        }
    asset_names = [a["name"] for a in POCKET_OPTION_ASSETS]
    return {"data_source": "pocket_option", "assets": asset_names, "total": len(asset_names)}


@app.get("/correlations", dependencies=[Depends(active_session_token)])
async def get_correlations() -> Dict:
    """Return Pearson correlations between the active forex candle returns."""
    if current_config["data_source"] != "pocket_option" or not relay_candle_cache:
        return {"data_source": current_config["data_source"], "nodes": [], "links": []}

    series = {}
    for symbol, candles in relay_candle_cache.items():
        if not _is_forex_pair(symbol) or len(candles) < 20:
            continue
        closes = [float(candle[1]) for candle in candles]
        returns = [(current - previous) / previous for previous, current in zip(closes, closes[1:]) if previous]
        if len(returns) >= 10:
            series[symbol] = returns

    nodes = [{"id": symbol, "label": symbol.replace("_otc", "")} for symbol in series]
    links = []
    symbols = list(series)
    for index, first in enumerate(symbols):
        for second in symbols[index + 1:]:
            size = min(len(series[first]), len(series[second]))
            first_returns = series[first][-size:]
            second_returns = series[second][-size:]
            first_mean = sum(first_returns) / size
            second_mean = sum(second_returns) / size
            numerator = sum((a - first_mean) * (b - second_mean) for a, b in zip(first_returns, second_returns))
            first_variance = sum((value - first_mean) ** 2 for value in first_returns)
            second_variance = sum((value - second_mean) ** 2 for value in second_returns)
            denominator = (first_variance * second_variance) ** 0.5
            correlation = numerator / denominator if denominator else 0
            if abs(correlation) >= 0.05:
                links.append({"source": first, "target": second, "value": round(correlation, 3)})

    return {"data_source": current_config["data_source"], "nodes": nodes, "links": links}


@app.get("/status", dependencies=[Depends(active_session_token)])
async def get_status() -> Dict:
    source = current_config["data_source"]
    # PO mode: report relay cache health, not market_data_cache
    if source == "pocket_option":
        if relay_cache_timestamp:
            age = (datetime.now(timezone.utc) - relay_cache_timestamp).total_seconds()
            relay_valid = age < RELAY_STALE_SECONDS
        else:
            age = -1
            relay_valid = False
        return {
            "status": "operational",
            "data_source": source,
            "cache_valid": relay_valid,
            "cache_age_seconds": int(age),
            "cached_items": len(relay_candle_cache),
        }
    # Binance mode
    return {
        "status": "operational",
        "data_source": source,
        "cache_valid": is_cache_valid(),
        "cache_age_seconds": (
            int((datetime.now(timezone.utc) - cache_timestamp).total_seconds())
            if cache_timestamp else -1
        ),
        "cached_items": len(market_data_cache),
    }


@app.post("/verify-trader")
@limiter.limit("5/minute")
async def verify_trader(request: Request, payload: Dict) -> Dict:
    """
    Verify a Pocket Option trader ID via the PocketPartners Telegram bot.
    Returns {"found": true/false, ...details}.
    """
    trader_id = str(payload.get("trader_id", "")).strip()
    if not trader_id:
        raise HTTPException(status_code=400, detail="trader_id required")
    if len(trader_id) > 64:
        raise HTTPException(status_code=400, detail="trader_id too long")
    if not trader_id.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(status_code=400, detail="trader_id contains invalid characters")
    timezone_name = payload.get("timezone")
    if timezone_name is not None and not is_valid_timezone(timezone_name):
        raise HTTPException(status_code=400, detail="Invalid IANA timezone")
    if BYPASS_TRADER_ID and trader_id.casefold() == BYPASS_TRADER_ID.casefold():
        result = {"found": True, "bypassed": True, "message": "TRADER VERIFIED"}
    else:
        result = await telegram_service.verify_trader(trader_id)
    if result.get("found"):
        saved_timezone = set_timezone(trader_id, timezone_name or get_timezone(trader_id))
        result["timezone"] = saved_timezone
        token = secrets.token_urlsafe(32)
        # Newest login wins: an older session for this Trader ID (another browser/device) is signed out.
        result["replaced_previous_session"] = claim_session(trader_id, token)
        result["session_token"] = token
    return result


@app.post("/session/heartbeat")
async def session_heartbeat(_: str = Depends(active_session_token)) -> Dict:
    return {"active": True}


@app.post("/session/logout")
async def session_logout(token: str = Depends(active_session_token)) -> Dict:
    release_session(token)
    return {"logged_out": True}


@app.get("/trader/flags")
async def trader_flags(token: str = Depends(active_session_token)) -> Dict:
    """Per-trader UI flags (currently: has this trader already opened the Telegram channel)."""
    trader_id = trader_for_token(token)
    return {"telegram_joined": bool(trader_id and get_telegram_joined(trader_id))}


@app.post("/trader/telegram-joined")
async def trader_telegram_joined(token: str = Depends(active_session_token)) -> Dict:
    """Remember that this trader opened the Telegram channel so the hub stops showing the card."""
    trader_id = trader_for_token(token)
    if not trader_id:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    set_telegram_joined(trader_id)
    return {"telegram_joined": True}


class PushKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscription(BaseModel):
    endpoint: str
    keys: PushKeys


class PushEndpoint(BaseModel):
    endpoint: str


@app.get("/push/public-key")
async def push_public_key() -> Dict:
    """Public VAPID key the browser needs to create a push subscription."""
    return {"publicKey": notifications.public_key()}


@app.post("/push/subscribe")
async def push_subscribe(sub: PushSubscription, token: str = Depends(active_session_token)) -> Dict:
    """Opt this trader's browser in to the daily trading reminder."""
    trader_id = trader_for_token(token)
    if not trader_id:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    if not sub.endpoint.startswith("https://"):
        raise HTTPException(status_code=400, detail="Invalid push endpoint.")
    notifications.save_subscription(trader_id, sub.endpoint, sub.keys.p256dh, sub.keys.auth)
    return {"subscribed": True}


@app.post("/push/unsubscribe")
async def push_unsubscribe(body: PushEndpoint, _: str = Depends(active_session_token)) -> Dict:
    notifications.remove_subscription(body.endpoint)
    return {"subscribed": False}


@app.get("/notifications/today")
async def notification_today(_: str = Depends(active_session_token)) -> Dict:
    """Today's motivating message (same text as the push), for the in-app banner."""
    return notifications.todays_message()


@app.post("/push/test")
async def push_test(x_admin_key: Optional[str] = Header(None)) -> Dict:
    """Send today's notification to every subscriber right now. Requires ADMIN_KEY to be set."""
    if not ADMIN_KEY or x_admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")
    return await notifications.send_to_all()


# ── Best performers (editable from the admin page) ───────────────────

def require_admin(x_admin_key: Optional[str]) -> None:
    """Admin pages need ADMIN_KEY to be set; unlike the legacy admin endpoints they are never open."""
    if not ADMIN_KEY or not secrets.compare_digest((x_admin_key or "").encode(), ADMIN_KEY.encode()):
        raise HTTPException(status_code=403, detail="Forbidden")


class PerformerIn(BaseModel):
    handle: str
    roi: float
    photo: str = ""


class PerformersIn(BaseModel):
    month: str = "Last Month"
    performers: List[PerformerIn]


@app.get("/performers")
async def public_performers() -> JSONResponse:
    """Public: the winners podium. `configured` is false until an admin saves one (the site then uses its built-in list)."""
    data = performers.get()
    body = {"configured": bool(data), **(data or {})}
    return JSONResponse(body, headers={"Cache-Control": "public, max-age=60"})


@app.get("/admin/performers")
@limiter.limit("30/minute")
async def admin_get_performers(request: Request, x_admin_key: Optional[str] = Header(None)) -> Dict:
    require_admin(x_admin_key)
    data = performers.get()
    return {"configured": bool(data), **(data or {})}


@app.post("/admin/performers")
@limiter.limit("30/minute")
async def admin_save_performers(request: Request, body: PerformersIn, x_admin_key: Optional[str] = Header(None)) -> Dict:
    require_admin(x_admin_key)
    try:
        data = performers.save(body.month, [p.model_dump() for p in body.performers])
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    logger.info("Best performers updated by admin (%d entries)", len(data["performers"]))
    return {"configured": True, **data}


@app.post("/admin/performers/photo")
@limiter.limit("30/minute")
async def admin_upload_photo(request: Request, file: UploadFile = File(...), x_admin_key: Optional[str] = Header(None)) -> Dict:
    require_admin(x_admin_key)
    data = await file.read(performers.MAX_UPLOAD_BYTES + 1)
    try:
        return {"photo": performers.save_upload(data)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class TraderRef(BaseModel):
    trader_id: str


@app.get("/admin/telegram-joins")
@limiter.limit("60/minute")
async def admin_telegram_joins(request: Request, x_admin_key: Optional[str] = Header(None)) -> Dict:
    """Traders who opened the Telegram channel after login (their hub card is hidden)."""
    require_admin(x_admin_key)
    items = list_telegram_joined()
    return {"count": len(items), "traders": items}


@app.post("/admin/telegram-joins/remove")
@limiter.limit("60/minute")
async def admin_telegram_remove(request: Request, body: TraderRef, x_admin_key: Optional[str] = Header(None)) -> Dict:
    """Remove a trader from the list so the Join Telegram card shows for them again."""
    require_admin(x_admin_key)
    trader_id = body.trader_id.strip()
    if not trader_id or len(trader_id) > 64:
        raise HTTPException(status_code=400, detail="Invalid Trader ID")
    if not reset_telegram_joined(trader_id):
        raise HTTPException(status_code=404, detail="That Trader ID is not on the list")
    logger.info("Admin removed %s from the Telegram-opened list", trader_id.upper())
    return {"removed": True}


@app.get("/uploads/{name}")
async def get_upload(name: str) -> FileResponse:
    path = performers.upload_path(name)
    if not path:
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path, headers={"Cache-Control": "public, max-age=31536000, immutable"})


@app.get("/timezones")
async def get_timezones() -> List[Dict]:
    return timezone_catalog()


@app.post("/candle-data")
@limiter.limit("60/minute")
async def receive_candle_data(
    request: Request,
    _: None = Depends(verify_admin_key),
) -> Dict:
    """
    Receive candle data pushed from the local relay script (po_relay.py).
    Payload (new): { "candles": {symbol: [[ts,c,v]...]}, "latest_prices": {symbol: price} }
    Payload (old): { symbol: [[ts,c,v]...], ... }   (backward compat)
    """
    global relay_candle_cache, relay_latest_prices, relay_cache_timestamp
    try:
        data = await request.json()
        if not isinstance(data, dict):
            raise HTTPException(status_code=400, detail="Expected dict")

        # New format: {candles: {...}, latest_prices: {...}}
        if "candles" in data:
            candles_data   = data.get("candles", {})
            latest_data    = data.get("latest_prices", {})
        else:
            # Old format: direct symbol→candles mapping
            candles_data = data
            latest_data  = {}

        count = 0
        for symbol, candles in candles_data.items():
            if candles:
                relay_candle_cache[symbol] = [tuple(c) for c in candles]
                count += 1

        for symbol, price in latest_data.items():
            try:
                relay_latest_prices[symbol] = float(price)
            except (TypeError, ValueError):
                pass

        relay_cache_timestamp = datetime.now(timezone.utc)
        logger.info(f"Relay: {count} assets, {len(latest_data)} live prices")
        return {"status": "ok", "assets_received": count, "live_prices": len(latest_data)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Relay data error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/relay-status")
async def relay_status() -> Dict:
    """Check if the local relay is active and how fresh the data is."""
    if not relay_cache_timestamp:
        return {"relay_active": False, "assets": 0}
    age = (datetime.now(timezone.utc) - relay_cache_timestamp).total_seconds()
    return {
        "relay_active": age < RELAY_STALE_SECONDS,
        "age_seconds": int(age),
        "assets": len(relay_candle_cache),
        "live_prices": len(relay_latest_prices),
        "symbols": list(relay_candle_cache.keys()),
    }


@app.get("/relay-prices")
async def relay_prices() -> Dict:
    """Show the latest price for every asset in the relay cache."""
    from po_websocket import OTC_SYMBOL_MAP
    reverse_map = {v: k for k, v in OTC_SYMBOL_MAP.items()}
    result = {}
    for po_sym, price in relay_latest_prices.items():
        display = reverse_map.get(po_sym, po_sym)
        candles = relay_candle_cache.get(po_sym, [])
        last_candle_price = candles[-1][1] if candles else None
        result[display] = {
            "live_price": round(price, 6),
            "last_candle_price": round(last_candle_price, 6) if last_candle_price else None,
            "candles": len(candles),
        }
    # Also include assets with candle data but no live tick yet
    for po_sym, candles in relay_candle_cache.items():
        display = reverse_map.get(po_sym, po_sym)
        if display not in result and candles:
            result[display] = {
                "live_price": None,
                "last_candle_price": round(candles[-1][1], 6),
                "candles": len(candles),
            }
    return {"count": len(result), "prices": result}


@app.post("/update-cache")
@limiter.limit("5/minute")
async def manual_cache_update(
    request: Request,
    _: None = Depends(verify_admin_key),
):
    """
    Manually trigger market data cache update.
    Useful for testing and debugging.
    
    Returns:
        Update status
    """
    try:
        source = current_config["data_source"]
        
        if source == "binance":
            update_binance_cache()
        else:
            update_pocket_option_cache()
        
        return {
            "status": "success",
            "data_source": source,
            "message": f"Cache updated with {len(market_data_cache)} items",
            "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S")
        }
    
    except Exception as e:
        logger.error(f"Error in manual cache update: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to update cache"
        )


@app.post("/refresh-po-session")
@limiter.limit("3/hour")
async def refresh_po_session(
    request: Request,
    _: None = Depends(verify_admin_key),
) -> Dict:
    """
    Re-login to Pocket Option via headless browser and refresh the session token.
    Use this when the current PO session expires (signals stop coming through).
    Requires ADMIN_KEY header and PO_EMAIL / PO_PASSWORD env vars.
    """
    import os
    po_email    = os.environ.get("PO_EMAIL", "")
    po_password = os.environ.get("PO_PASSWORD", "")

    if not po_email or not po_password:
        raise HTTPException(
            status_code=400,
            detail="PO_EMAIL and PO_PASSWORD must be set to use headless re-login"
        )

    from po_auth import _login_async
    token = await _login_async()

    if not token:
        raise HTTPException(
            status_code=503,
            detail="Headless PO login failed — check credentials or CAPTCHA"
        )

    _init_pocket_option(token)
    logger.info("PO session refreshed via /refresh-po-session")
    return {"status": "success", "message": "Pocket Option session refreshed"}


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle general exceptions."""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


if __name__ == "__main__":
    import uvicorn
    
    logger.info(
        f"Starting Trading Signal System on {HOST}:{PORT}"
    )
    
    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        log_level=LOG_LEVEL.lower()
    )
