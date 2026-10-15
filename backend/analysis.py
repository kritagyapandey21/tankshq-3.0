"""
Signal analysis and confidence scoring module.
Analyzes indicators and generates trading signals.
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
from indicators import TechnicalIndicators
from config import CONFIDENCE_WEIGHTS, MIN_CONFIDENCE_THRESHOLD

logger = logging.getLogger(__name__)


class SignalAnalyzer:
    """Analyze market data and generate trading signals."""

    @staticmethod
    def calculate_confidence_score(
        rsi_signal: float,
        ema_trend: float,
        macd_confirmation: float,
    ) -> float:
        """
        Calculate overall confidence score using weighted indicators.

        Args:
            rsi_signal: RSI signal strength (0-100)
            ema_trend: EMA trend strength (0-100)
            macd_confirmation: MACD confirmation strength (0-100)

        Returns:
            Weighted confidence score (0-100)
        """
        confidence = (
            (rsi_signal        * CONFIDENCE_WEIGHTS["rsi_signal"]) +
            (ema_trend         * CONFIDENCE_WEIGHTS["ema_trend"]) +
            (macd_confirmation * CONFIDENCE_WEIGHTS["macd_confirmation"])
        )
        return round(min(100, max(0, confidence)), 2)

    @staticmethod
    def determine_direction(
        rsi_direction: Optional[str],
        ema_direction: Optional[str],
        macd_direction: Optional[str],
    ) -> Optional[str]:
        """
        Determine final signal direction based on indicator agreement.

        Args:
            rsi_direction: RSI-based direction
            ema_direction: EMA-based direction
            macd_direction: MACD-based direction

        Returns:
            Final direction ("CALL" or "PUT"), or None if indicators disagree
        """
        directions = [rsi_direction, ema_direction, macd_direction]

        call_votes = sum(1 for d in directions if d == "CALL")
        put_votes  = sum(1 for d in directions if d == "PUT")

        if call_votes > put_votes:
            return "CALL"
        elif put_votes > call_votes:
            return "PUT"
        else:
            return None

    @staticmethod
    def analyze_pair(pair_data: Dict) -> Optional[Dict]:
        """
        Analyze a single trading pair and generate signal data.

        Args:
            pair_data: Dictionary containing closes and symbol

        Returns:
            Dictionary with analysis results
        """
        closes = pair_data["closes"]
        symbol = pair_data["symbol"]

        # Minimum 60 candles required:
        # MACD signal line needs 26 (slow EMA) + 9 (signal EMA) = 35 candles
        # before it produces any valid value. RSI(14) Wilder smoothing needs
        # enough iterations to converge — 60 gives 46 iterations, well past
        # the ~30 needed for stability.
        if len(closes) < 60:
            logger.warning(f"Insufficient data for {symbol}: {len(closes)} candles (need 60)")
            return None

        signals = TechnicalIndicators.get_indicator_signals(closes)

        confidence = SignalAnalyzer.calculate_confidence_score(
            signals.get("rsi_signal", 50),
            signals.get("ema_trend", 50),
            signals.get("macd_confirmation", 50),
        )

        direction = SignalAnalyzer.determine_direction(
            signals.get("rsi_direction"),
            signals.get("ema_direction"),
            signals.get("macd_direction"),
        )

        if direction is None:
            return None

        return {
            "symbol": symbol,
            "confidence": confidence,
            "direction": direction,
            "price": pair_data["current_price"],
            "signals": {
                "rsi":  signals.get("rsi_signal", 50),
                "ema":  signals.get("ema_trend", 50),
                "macd": signals.get("macd_confirmation", 50),
            }
        }

    @staticmethod
    def select_best_signal(
        all_analyses: List[Dict],
        min_confidence: float = MIN_CONFIDENCE_THRESHOLD
    ) -> Optional[Dict]:
        """
        Select the pair with highest confidence that meets minimum threshold.
        
        Args:
            all_analyses: List of analysis results for each pair
            min_confidence: Minimum confidence threshold
            
        Returns:
            Best signal analysis or None if no pair meets threshold
        """
        if not all_analyses:
            return None
        
        # Filter by minimum confidence
        qualified = [a for a in all_analyses if a["confidence"] >= min_confidence]
        
        if not qualified:
            logger.warning(f"No pairs met minimum confidence threshold ({min_confidence}%)")
            return None
        
        # Sort by confidence and return highest
        return max(qualified, key=lambda x: x["confidence"])

    @staticmethod
    def generate_signal(
        best_analysis: Dict,
        entry_time: datetime,
        expiry_time: datetime
    ) -> Dict:
        """
        Generate final trading signal with timing information.
        
        Args:
            best_analysis: Analysis data for selected pair
            entry_time: Signal entry time
            expiry_time: Signal expiry time
            
        Returns:
            Complete signal JSON
        """
        signal = {
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
            "candle_duration": "1 minute"
        }
        
        return signal
