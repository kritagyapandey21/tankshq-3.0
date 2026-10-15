"""
Configuration module for trading signal system.
Centralized settings and constants.
"""

import os
from typing import Dict, List

# API Configuration
BINANCE_BASE_URL = "https://api.binance.com"
COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"

# Trading Pairs to monitor (Crypto pairs)
TRADING_PAIRS = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "ADAUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "LINKUSDT",
    "LTCUSDT",
    "BCHUSDT",
    "SOLUSDT"
]

# Technical Indicators Configuration
INDICATORS_CONFIG = {
    "RSI": {
        "period": 14,
        "overbought": 70,
        "oversold": 30
    },
    "EMA": {
        "fast_period": 9,
        "slow_period": 21
    },
    "MACD": {
        "fast_period": 12,
        "slow_period": 26,
        "signal_period": 9
    }
}

# Confidence Scoring Weights
CONFIDENCE_WEIGHTS: Dict[str, float] = {
    "rsi_signal":        0.375,
    "ema_trend":         0.375,
    "macd_confirmation": 0.25,
}

# Data Fetching
CANDLES_TO_FETCH = 100
TIMEFRAME = "1m"

# Minimum confidence threshold for signal generation
MIN_CONFIDENCE_THRESHOLD = 40

# Server Configuration
HOST = "0.0.0.0"
PORT = 8000
DEBUG = False

# CORS Configuration
# Add your Vercel frontend URL here after deployment, e.g. "https://your-app.vercel.app"
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://localhost:8000,http://127.0.0.1:3000,http://127.0.0.1:8000"
    ).split(",")
    if o.strip()
]

# Logging
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Security
# Set ADMIN_KEY env var to protect /config/data-source and /update-cache.
# If not set, those endpoints are open (suitable for local dev only).
ADMIN_KEY = os.environ.get("ADMIN_KEY", "")

# One trusted Trader ID may bypass Telegram verification. Keep this value only
# in the private production .env file, never in source control.
BYPASS_TRADER_ID = os.environ.get("BYPASS_TRADER_ID", "").strip()

# Set REQUIRE_VERIFICATION=true in production so login always requires a valid
# Telegram check. When false (default) the system fails open if Telegram is
# unreachable — useful during initial setup.
REQUIRE_VERIFICATION = os.environ.get("REQUIRE_VERIFICATION", "false").lower() == "true"
