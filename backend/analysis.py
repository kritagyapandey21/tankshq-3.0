"""
Signal analysis module.

One engine only: "v3-reversion-plus" (signal_v3.py). For each pair it measures how over-stretched the price is with
RSI, Bollinger Bands and Stochastic RSI, and only signals when all three agree; the call expects a short pullback.
Supertrend, EMA, MACD and trend steadiness are returned as market context for the Signal Drivers panel.
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta, timezone

from config import MIN_CONFIDENCE_THRESHOLD
import signal_v3

IST = timezone(timedelta(hours=5, minutes=30))
ENGINE = "v3-reversion-plus"

logger = logging.getLogger(__name__)


class SignalAnalyzer:
    """Analyze market data and generate trading signals."""

    @staticmethod
    def analyze_pair(pair_data: Dict) -> Optional[Dict]:
        """Analyze one pair. Indicator scores are 0-100 support for the call: above 50 supports it, below 50 opposes it."""
        closes, symbol = pair_data["closes"], pair_data["symbol"]
        r = signal_v3.analyze_reversion_plus(closes)
        if not r or not r["direction"]:
            return None
        d = 1 if r["direction"] == "CALL" else -1
        comp = r["components"]
        agree = lambda x: round(max(0.0, min(100.0, 50 + 50 * x * d)), 1)
        osc_rsi, osc_bb, osc_sr = agree(comp["rsi"]), agree(comp["bollinger"]), agree(comp["stoch_rsi"])
        combined = comp["rsi"] * 0.4 + comp["bollinger"] * 0.35 + comp["stoch_rsi"] * 0.25
        # Setup strength = the average of the three readings that decide the call, so the number on screen can be
        # checked against the bars. Capped at 99: never "certain".
        confidence = round(min(99.0, (osc_rsi + osc_bb + osc_sr) / 3), 1)
        return {
            "symbol": symbol,
            "confidence": confidence,
            "direction": r["direction"],
            "price": pair_data["current_price"],
            "signals": {
                "osc_rsi": osc_rsi,                  # the three snap-back readings that decide the call
                "osc_bollinger": osc_bb,
                "osc_stoch_rsi": osc_sr,
                "rsi": agree(combined),              # the three combined
                "ema": agree(comp["ema"]),           # market context
                "macd": agree(comp["macd"]),
                "supertrend": agree(comp["supertrend"]),
                "strength": round(comp["ker"] * 100, 1),   # trend steadiness (Efficiency Ratio), not a vote
            },
        }

    @staticmethod
    def select_best_signal(
        all_analyses: List[Dict],
        min_confidence: float = MIN_CONFIDENCE_THRESHOLD
    ) -> Optional[Dict]:
        """Pick the pair with the highest setup strength that meets the minimum threshold."""
        if not all_analyses:
            return None
        qualified = [a for a in all_analyses if a["confidence"] >= min_confidence]
        if not qualified:
            logger.warning(f"No pairs met minimum confidence threshold ({min_confidence}%)")
            return None
        return max(qualified, key=lambda x: x["confidence"])

    @staticmethod
    def generate_signal(
        best_analysis: Dict,
        entry_time: datetime,
        expiry_time: datetime
    ) -> Dict:
        """Build the final signal with timing information."""
        return {
            "pair": best_analysis["symbol"],
            "direction": "BUY" if best_analysis["direction"] == "CALL" else "SELL",
            "entry_time": entry_time.strftime("%H:%M:%S"),
            "expiry_time": expiry_time.strftime("%H:%M:%S"),
            "entry_timestamp": entry_time.isoformat(),
            "expiry_timestamp": expiry_time.isoformat(),
            "confidence": round(best_analysis["confidence"], 1),
            "current_price": best_analysis["price"],
            "indicator_scores": best_analysis["signals"],
            "generated_at": datetime.now(IST).strftime("%H:%M:%S"),
            "generated_timestamp": datetime.now(IST).isoformat(),
            "candle_duration": "1 minute",
            "engine": ENGINE,
        }
