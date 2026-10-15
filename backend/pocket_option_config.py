"""
Pocket Option asset lists and configuration.
OTC pairs are fetched via PO WebSocket; live pairs fall back to Yahoo Finance.
"""

POCKET_OPTION_ASSETS = [
    # Major Forex OTC
    {"id": "1",  "name": "EUR/USD-OTC"},
    {"id": "2",  "name": "GBP/USD-OTC"},
    {"id": "3",  "name": "USD/JPY-OTC"},
    {"id": "4",  "name": "AUD/USD-OTC"},
    {"id": "5",  "name": "USD/CAD-OTC"},
    {"id": "6",  "name": "USD/CHF-OTC"},
    {"id": "7",  "name": "NZD/USD-OTC"},
    # Minor Forex OTC
    {"id": "8",  "name": "EUR/GBP-OTC"},
    {"id": "9",  "name": "EUR/JPY-OTC"},
    {"id": "10", "name": "GBP/JPY-OTC"},
    {"id": "11", "name": "AUD/JPY-OTC"},
    {"id": "12", "name": "CAD/JPY-OTC"},
    {"id": "13", "name": "CHF/JPY-OTC"},
    {"id": "14", "name": "GBP/AUD-OTC"},
    {"id": "15", "name": "GBP/CAD-OTC"},
    {"id": "16", "name": "GBP/CHF-OTC"},
    {"id": "17", "name": "GBP/NZD-OTC"},
    {"id": "18", "name": "AUD/CAD-OTC"},
    {"id": "19", "name": "AUD/CHF-OTC"},
    {"id": "20", "name": "AUD/NZD-OTC"},
    {"id": "21", "name": "EUR/CAD-OTC"},
    {"id": "22", "name": "EUR/CHF-OTC"},
    {"id": "23", "name": "EUR/NZD-OTC"},
    {"id": "24", "name": "EUR/AUD-OTC"},
    {"id": "25", "name": "CAD/CHF-OTC"},
    {"id": "26", "name": "NZD/CAD-OTC"},
    {"id": "27", "name": "NZD/CHF-OTC"},
    {"id": "28", "name": "NZD/JPY-OTC"},
    # Commodities OTC
    {"id": "30", "name": "XAU/USD-OTC"},
    {"id": "31", "name": "XAG/USD-OTC"},
    # Crypto OTC
    {"id": "40", "name": "BTC/USD-OTC"},
    {"id": "41", "name": "ETH/USD-OTC"},
    {"id": "42", "name": "LTC/USD-OTC"},
    {"id": "43", "name": "XRP/USD-OTC"},
    {"id": "44", "name": "BCH/USD-OTC"},
    {"id": "45", "name": "DOGE/USD-OTC"},
    {"id": "46", "name": "ADA/USD-OTC"},
    {"id": "47", "name": "SOL/USD-OTC"},
    {"id": "48", "name": "DOT/USD-OTC"},
    {"id": "49", "name": "BNB/USD-OTC"},
]

# Fallback live pairs (Yahoo Finance) if WebSocket fails
POCKET_OPTION_ASSETS_LIVE = [
    {"id": "1",  "name": "EUR/USD"},
    {"id": "2",  "name": "GBP/USD"},
    {"id": "3",  "name": "USD/JPY"},
    {"id": "4",  "name": "AUD/USD"},
    {"id": "5",  "name": "USD/CAD"},
    {"id": "6",  "name": "USD/CHF"},
    {"id": "7",  "name": "NZD/USD"},
    {"id": "8",  "name": "EUR/GBP"},
    {"id": "9",  "name": "EUR/JPY"},
    {"id": "10", "name": "GBP/JPY"},
    {"id": "11", "name": "AUD/JPY"},
    {"id": "12", "name": "CAD/JPY"},
    {"id": "13", "name": "CHF/JPY"},
    {"id": "14", "name": "GBP/AUD"},
    {"id": "15", "name": "GBP/CAD"},
    {"id": "16", "name": "GBP/CHF"},
    {"id": "17", "name": "GBP/NZD"},
    {"id": "18", "name": "AUD/CAD"},
    {"id": "19", "name": "AUD/CHF"},
    {"id": "20", "name": "AUD/NZD"},
    {"id": "21", "name": "EUR/CAD"},
    {"id": "22", "name": "EUR/CHF"},
    {"id": "23", "name": "EUR/NZD"},
    {"id": "24", "name": "EUR/AUD"},
    {"id": "25", "name": "CAD/CHF"},
    {"id": "26", "name": "NZD/CAD"},
    {"id": "27", "name": "NZD/CHF"},
    {"id": "28", "name": "NZD/JPY"},
    {"id": "30", "name": "XAU/USD"},
    {"id": "31", "name": "XAG/USD"},
    {"id": "40", "name": "BTC/USD"},
    {"id": "41", "name": "ETH/USD"},
    {"id": "42", "name": "LTC/USD"},
    {"id": "43", "name": "XRP/USD"},
    {"id": "44", "name": "BCH/USD"},
    {"id": "45", "name": "DOGE/USD"},
    {"id": "46", "name": "ADA/USD"},
    {"id": "47", "name": "SOL/USD"},
    {"id": "48", "name": "DOT/USD"},
    {"id": "49", "name": "BNB/USD"},
]

POCKET_OPTION_CONFIDENCE_WEIGHTS = {
    "rsi_signal":        0.375,
    "ema_trend":         0.375,
    "macd_confirmation": 0.25,
}

MIN_CONFIDENCE_THRESHOLD = 40
DEFAULT_CANDLES_TO_FETCH = 100
DEFAULT_TIMEFRAME = 60
