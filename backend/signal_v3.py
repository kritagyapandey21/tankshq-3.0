"""Signal engine: v3-reversion-plus (the only engine).

For each pair it measures how over-stretched the price is with RSI, Bollinger %B and Stochastic RSI, and only calls
a direction when all three agree (expecting a short pullback). Supertrend, the EMA 9/21/50 stack, MACD and the
Kaufman Efficiency Ratio (trend steadiness) are computed as market context for the Signal Drivers panel; they do not
decide the call.

Data note
---------
Pocket Option's candle feed gives ONE price per minute (open = high = low = close), so every indicator here works
on closing prices only. Supertrend therefore uses a close-to-close ATR (the average absolute change between closes)
instead of a high/low true range, and bands are drawn around the close.

Every component is a score in [-1, +1] (positive = bullish).
"""

from typing import Dict, List, Optional

import numpy as np

# --- tunable parameters (kept few on purpose: more knobs = more overfitting) ---------------------------
ST_PERIOD = 10          # Supertrend ATR period
ST_MULT = 2.0           # Supertrend band multiplier (3.0 = slower, fewer flips)
KER_PERIOD = 10         # efficiency-ratio window


# --------------------------------------------------------------------------------------------------
# indicator building blocks (numpy, close-only)
# --------------------------------------------------------------------------------------------------
def ema(c: np.ndarray, period: int) -> np.ndarray:
    out = np.full(len(c), np.nan)
    if len(c) < period:
        return out
    k = 2.0 / (period + 1)
    out[period - 1] = c[:period].mean()
    for i in range(period, len(c)):
        out[i] = (c[i] - out[i - 1]) * k + out[i - 1]
    return out


def rsi(c: np.ndarray, period: int = 14) -> np.ndarray:
    out = np.full(len(c), np.nan)
    if len(c) <= period:
        return out
    d = np.diff(c)
    up = d[:period].clip(min=0).mean()
    dn = (-d[:period]).clip(min=0).mean()
    out[period] = 100.0 if dn == 0 else 100 - 100 / (1 + up / dn)
    for i in range(period + 1, len(c)):
        g, l = max(d[i - 1], 0.0), max(-d[i - 1], 0.0)
        up = (up * (period - 1) + g) / period
        dn = (dn * (period - 1) + l) / period
        out[i] = 100.0 if dn == 0 else 100 - 100 / (1 + up / dn)
    return out


def macd_hist(c: np.ndarray) -> np.ndarray:
    fast, slow = ema(c, 12), ema(c, 26)
    line = fast - slow
    valid = ~np.isnan(line)
    sig = np.full(len(c), np.nan)
    if valid.sum() >= 9:
        s = ema(line[valid], 9)
        sig[np.where(valid)[0]] = s
    return line - sig


def supertrend(c: np.ndarray, period: int = ST_PERIOD, mult: float = ST_MULT):
    """Close-only Supertrend. Returns (direction[+1/-1], distance_in_ATR, bars_since_flip) for the last bar."""
    n = len(c)
    tr = np.abs(np.diff(c, prepend=c[0]))
    atr = np.full(n, np.nan)
    if n <= period:
        return 0, 0.0, 0
    atr[period] = tr[1:period + 1].mean()
    for i in range(period + 1, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

    up_band = c + mult * atr
    lo_band = c - mult * atr
    f_up = np.full(n, np.nan)
    f_lo = np.full(n, np.nan)
    f_up[period], f_lo[period] = up_band[period], lo_band[period]
    trend = np.zeros(n, dtype=int)
    trend[period] = 1 if c[period] >= (f_up[period] + f_lo[period]) / 2 else -1
    flips = period
    for i in range(period + 1, n):
        f_up[i] = up_band[i] if (up_band[i] < f_up[i - 1] or c[i - 1] > f_up[i - 1]) else f_up[i - 1]
        f_lo[i] = lo_band[i] if (lo_band[i] > f_lo[i - 1] or c[i - 1] < f_lo[i - 1]) else f_lo[i - 1]
        if c[i] > f_up[i - 1]:
            trend[i] = 1
        elif c[i] < f_lo[i - 1]:
            trend[i] = -1
        else:
            trend[i] = trend[i - 1]
        if trend[i] != trend[i - 1]:
            flips = i
    line = f_lo[-1] if trend[-1] == 1 else f_up[-1]
    dist = abs(c[-1] - line) / atr[-1] if atr[-1] > 0 else 0.0
    return int(trend[-1]), float(dist), int(n - 1 - flips)


def efficiency_ratio(c: np.ndarray, period: int = KER_PERIOD) -> float:
    """Kaufman Efficiency Ratio: net move / total path. 1 = straight line (trend), 0 = pure chop."""
    if len(c) <= period:
        return 0.0
    net = abs(c[-1] - c[-1 - period])
    path = np.abs(np.diff(c[-1 - period:])).sum()
    return float(net / path) if path > 0 else 0.0


def bollinger_pctb(c: np.ndarray, period: int = 20, k: float = 2.0) -> float:
    w = c[-period:]
    mid, sd = w.mean(), w.std()
    if sd == 0:
        return 0.5
    return float((c[-1] - (mid - k * sd)) / (2 * k * sd))


def stoch_rsi(c: np.ndarray, period: int = 14) -> float:
    r = rsi(c, period)
    w = r[-period:]
    w = w[~np.isnan(w)]
    if len(w) < 3 or w.max() == w.min():
        return 0.5
    return float((r[-1] - w.min()) / (w.max() - w.min()))


def clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return float(max(lo, min(hi, x)))


# --------------------------------------------------------------------------------------------------
# the engine
# --------------------------------------------------------------------------------------------------
def components(c: np.ndarray, st_period: int = ST_PERIOD, st_mult: float = ST_MULT) -> Dict[str, float]:
    """Every indicator reading, each as a score in [-1, +1] (positive = bullish), plus the efficiency ratio."""
    # ---- trend stack ------------------------------------------------------------------------------
    st_dir, st_dist, st_age = supertrend(c, st_period, st_mult)
    # a fresh flip is the strongest evidence; the signal then fades as the trend ages
    st_comp = st_dir * clip(0.6 + 0.2 * min(st_dist, 2.0) - 0.02 * max(st_age - 5, 0), 0.2, 1.0)

    e9, e21, e50 = ema(c, 9)[-1], ema(c, 21)[-1], ema(c, 50)[-1]
    scale = c[-1] * 0.0004                       # ~4 basis points: a "meaningful" EMA gap on 1-minute data
    ema_comp = clip((e9 - e21) / scale) * 0.7 + clip((c[-1] - e50) / (scale * 2)) * 0.3

    h = macd_hist(c)
    h_now, h_prev = h[-1], h[-2]
    h_scale = max(np.nanmax(np.abs(h[-30:])), 1e-12)
    macd_comp = clip(h_now / h_scale) * 0.6 + clip((h_now - h_prev) / h_scale * 2) * 0.4

    # ---- mean-reversion stack (positive = oversold / expect a bounce up) ---------------------------
    r = rsi(c, 14)[-1]
    rsi_mr = clip((50 - r) / 25)
    bb_mr = clip((0.5 - bollinger_pctb(c)) * 2.0)
    sr_mr = clip((0.5 - stoch_rsi(c)) * 2.0)

    # ---- last-minute shock: the latest 1-minute move in units of the pair's normal 1-minute move ---
    moves = np.abs(np.diff(c[-31:]))
    typical = moves[:-1].mean() if len(moves) > 1 else 0.0
    shock = float((c[-1] - c[-2]) / typical) if typical > 0 else 0.0

    return {"supertrend": st_comp, "ema": ema_comp, "macd": macd_comp,
            "rsi": rsi_mr, "bollinger": bb_mr, "stoch_rsi": sr_mr, "ker": efficiency_ratio(c), "shock": shock}


def reversion_plus(comp: Dict[str, float], min_score: float = 0.25, need_agree: bool = True,
                   ker_max: Optional[float] = None, min_shock: Optional[float] = None) -> Dict:
    """Stricter mean reversion: only trade clear, agreeing stretches, optionally only in choppy markets and
    only right after an unusually large 1-minute move in the stretched direction ("fade the jump")."""
    score = comp["rsi"] * 0.4 + comp["bollinger"] * 0.35 + comp["stoch_rsi"] * 0.25
    d = 1 if score > 0 else -1
    ok = abs(score) >= min_score
    if ok and need_agree:
        ok = all((x > 0) == (d > 0) and x != 0 for x in (comp["rsi"], comp["bollinger"], comp["stoch_rsi"]))
    if ok and ker_max is not None:
        ok = comp["ker"] <= ker_max                      # do not fade a clean, straight-line trend
    if ok and min_shock is not None:
        ok = comp["shock"] * d <= -min_shock             # BUY only after a big drop, SELL only after a big jump
    direction = ("CALL" if d > 0 else "PUT") if ok else None
    strength = abs(score) + 0.15 * min(abs(comp["shock"]), 3.0)
    return {
        "score": float(score),
        "direction": direction,
        "confidence": round(50 + 45 * min(1.0, strength / 1.0), 1) if direction else 0.0,
        "regime": "RANGING" if comp["ker"] <= 0.33 else ("TRENDING" if comp["ker"] >= 0.5 else "MIXED"),
        "ker": comp["ker"],
        "components": comp,
    }


def analyze_reversion_plus(closes: List[float]) -> Optional[Dict]:
    """v3-reversion-plus: mean reversion that only signals when RSI, Bollinger and StochRSI all agree."""
    c = np.asarray(closes, dtype=float)
    if len(c) < 60 or not np.isfinite(c).all():
        return None
    return reversion_plus(components(c), min_score=0.25, need_agree=True)
