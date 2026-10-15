"""
Technical indicators calculation module.
Implements RSI, EMA, and MACD analysis.
"""

import numpy as np
from typing import List, Dict, Tuple
import logging

logger = logging.getLogger(__name__)


class TechnicalIndicators:
    """Calculate technical indicators for market analysis."""

    @staticmethod
    def calculate_rsi(prices: List[float], period: int = 14) -> List[float]:
        """
        Calculate Relative Strength Index (RSI).
        
        Args:
            prices: List of closing prices
            period: RSI period (default 14)
            
        Returns:
            List of RSI values
        """
        if len(prices) < period + 1:
            return [np.nan] * len(prices)
        
        prices = np.array(prices, dtype=float)
        deltas = np.diff(prices)
        
        seed = deltas[:period]
        up = seed[seed >= 0].sum() / period
        down = -seed[seed < 0].sum() / period

        # up=0,down=0 → neutral; up>0,down=0 → all gains → RSI=100
        if up == 0 and down == 0:
            rs = 1.0
        elif down == 0:
            rs = float('inf')
        else:
            rs = up / down
        rsi = np.full(len(prices), np.nan)
        rsi[period] = 100 - 100 / (1 + rs)
        
        for i in range(period + 1, len(prices)):
            delta = deltas[i - 1]
            if delta > 0:
                up = (up * (period - 1) + delta) / period
                down = (down * (period - 1)) / period
            else:
                up = (up * (period - 1)) / period
                down = (down * (period - 1) - delta) / period
            
            if up == 0 and down == 0:
                rs = 1.0
            elif down == 0:
                rs = float('inf')
            else:
                rs = up / down
            rsi[i] = 100 - 100 / (1 + rs)
        
        return rsi.tolist()

    @staticmethod
    def calculate_ema(prices: List[float], period: int) -> List[float]:
        """
        Calculate Exponential Moving Average (EMA).
        
        Args:
            prices: List of closing prices
            period: EMA period
            
        Returns:
            List of EMA values
        """
        if len(prices) < period:
            return [np.nan] * len(prices)
        
        prices = np.array(prices, dtype=float)
        ema = np.full(len(prices), np.nan, dtype=float)
        
        multiplier = 2 / (period + 1)
        sma = np.mean(prices[:period])
        ema[period - 1] = sma
        
        for i in range(period, len(prices)):
            ema[i] = (prices[i] - ema[i - 1]) * multiplier + ema[i - 1]
        
        return ema.tolist()

    @staticmethod
    def calculate_macd(
        prices: List[float],
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9
    ) -> Tuple[List[float], List[float], List[float]]:
        """
        Calculate MACD (Moving Average Convergence Divergence).
        
        Args:
            prices: List of closing prices
            fast_period: Fast EMA period (default 12)
            slow_period: Slow EMA period (default 26)
            signal_period: Signal line period (default 9)
            
        Returns:
            Tuple of (MACD line, Signal line, Histogram)
        """
        if len(prices) < slow_period:
            return (
                [np.nan] * len(prices),
                [np.nan] * len(prices),
                [np.nan] * len(prices)
            )
        
        ema_fast = TechnicalIndicators.calculate_ema(prices, fast_period)
        ema_slow = TechnicalIndicators.calculate_ema(prices, slow_period)
        
        macd_line = [
            (f - s) if not np.isnan(f) and not np.isnan(s) else np.nan
            for f, s in zip(ema_fast, ema_slow)
        ]
        
        signal_line = TechnicalIndicators.calculate_ema(
            [x for x in macd_line if not np.isnan(x)],
            signal_period
        )
        
        # Align signal line with MACD line
        aligned_signal = [np.nan] * (len(prices) - len(signal_line)) + signal_line
        
        histogram = [
            (m - s) if not np.isnan(m) and not np.isnan(s) else np.nan
            for m, s in zip(macd_line, aligned_signal)
        ]
        
        return macd_line, aligned_signal, histogram

    @staticmethod
    def get_indicator_signals(
        prices: List[float],
    ) -> Dict[str, float]:
        """
        Generate signals from all indicators.

        Args:
            prices: List of closing prices

        Returns:
            Dictionary with indicator signals and scores
        """
        signals = {}

        # RSI Signal — score scales with distance from neutral (50)
        rsi_values = TechnicalIndicators.calculate_rsi(prices, 14)
        rsi = rsi_values[-1] if not np.isnan(rsi_values[-1]) else 50

        if rsi < 30:
            # Deeper oversold → higher score: RSI=0→100, RSI=30→70
            signals["rsi_signal"] = round(100 - (rsi / 30) * 30, 1)
            signals["rsi_direction"] = "CALL"
        elif rsi > 70:
            # Deeper overbought → higher score: RSI=70→70, RSI=100→100
            signals["rsi_signal"] = round(70 + ((rsi - 70) / 30) * 30, 1)
            signals["rsi_direction"] = "PUT"
        else:
            signals["rsi_signal"] = 40
            signals["rsi_direction"] = None

        # EMA Signal — score scales with the gap between EMA9 and EMA21
        ema_9 = TechnicalIndicators.calculate_ema(prices, 9)
        ema_21 = TechnicalIndicators.calculate_ema(prices, 21)

        ema_9_val = ema_9[-1] if not np.isnan(ema_9[-1]) else prices[-1]
        ema_21_val = ema_21[-1] if not np.isnan(ema_21[-1]) else prices[-1]

        # Normalize gap as percentage of price; wider gap = stronger trend
        gap_pct = abs(ema_9_val - ema_21_val) / max(ema_21_val, 1e-10) * 100
        ema_score = round(min(90, 50 + gap_pct * 2000), 1)

        if ema_9_val > ema_21_val:
            signals["ema_trend"] = ema_score
            signals["ema_direction"] = "CALL"
        elif ema_9_val < ema_21_val:
            signals["ema_trend"] = ema_score
            signals["ema_direction"] = "PUT"
        else:
            signals["ema_trend"] = 30
            signals["ema_direction"] = None

        # MACD Signal — score scales with histogram momentum
        macd_line, signal_line, histogram = TechnicalIndicators.calculate_macd(prices)

        macd_val = macd_line[-1] if not np.isnan(macd_line[-1]) else 0
        signal_val = signal_line[-1] if not np.isnan(signal_line[-1]) else 0
        hist_val = histogram[-1] if not np.isnan(histogram[-1]) else 0

        if len(histogram) > 1:
            prev_hist = histogram[-2] if not np.isnan(histogram[-2]) else 0

            # Use recent histogram range to normalize momentum
            recent = [h for h in histogram[-20:] if not np.isnan(h)]
            hist_range = max(abs(max(recent)), abs(min(recent)), 1e-10) if recent else 1e-10
            momentum = abs(hist_val - prev_hist)
            macd_score = round(min(95, 60 + (momentum / hist_range) * 35), 1)

            if macd_val > signal_val and hist_val > prev_hist:
                signals["macd_confirmation"] = macd_score
                signals["macd_direction"] = "CALL"
            elif macd_val < signal_val and hist_val < prev_hist:
                signals["macd_confirmation"] = macd_score
                signals["macd_direction"] = "PUT"
            else:
                signals["macd_confirmation"] = 30
                signals["macd_direction"] = None
        else:
            signals["macd_confirmation"] = 30
            signals["macd_direction"] = None
        
        return signals
