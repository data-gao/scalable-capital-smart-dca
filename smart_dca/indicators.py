"""Technical indicators calculation module.

Supports SMA, EMA, RSI, Bollinger Bands, and Percentile calculations
without requiring mandatory third-party dependencies (pure standard Python).
"""

from dataclasses import dataclass
import math
from typing import List, Optional, Tuple


@dataclass
class IndicatorResult:
    current_price: float
    sma_200: Optional[float]
    sma_200_diff_pct: Optional[float]
    rsi_14: Optional[float]
    bb_upper: Optional[float]
    bb_mid: Optional[float]
    bb_lower: Optional[float]
    bb_pct_b: Optional[float]
    is_above_sma200: bool
    is_rsi_oversold: bool
    is_below_bb_lower: bool


def calculate_sma(series: List[float], period: int) -> Optional[float]:
    """Calculate Simple Moving Average for the latest window."""
    if len(series) < period or period <= 0:
        return None
    return sum(series[-period:]) / period


def calculate_ema(series: List[float], period: int) -> Optional[float]:
    """Calculate Exponential Moving Average for the latest window."""
    if len(series) < period or period <= 0:
        return None
    alpha = 2.0 / (period + 1.0)
    # Seed with SMA of the first period elements
    ema = sum(series[:period]) / period
    for price in series[period:]:
        ema = (price * alpha) + (ema * (1.0 - alpha))
    return ema


def calculate_rsi(series: List[float], period: int = 14) -> Optional[float]:
    """Calculate Relative Strength Index (RSI) using Wilder's smoothed moving average."""
    if len(series) < period + 1 or period <= 0:
        return None

    deltas = [series[i] - series[i - 1] for i in range(1, len(series))]
    gains = [max(0.0, d) for d in deltas]
    losses = [max(0.0, -d) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0.0:
        return 100.0 if avg_gain > 0 else 50.0

    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def calculate_bollinger_bands(
    series: List[float], period: int = 20, num_std: float = 2.0
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """Calculate Bollinger Bands (Upper, Middle/SMA, Lower)."""
    if len(series) < period or period <= 0:
        return None, None, None

    window = series[-period:]
    mid = sum(window) / period
    variance = sum((x - mid) ** 2 for x in window) / period
    std = math.sqrt(variance)

    upper = mid + num_std * std
    lower = mid - num_std * std
    return upper, mid, lower


def calculate_percentile_rank(series: List[float], value: float) -> Optional[float]:
    """Calculate percentile rank (0.0 to 100.0) of a value relative to series."""
    if not series:
        return None
    count_below = sum(1 for x in series if x < value)
    return (count_below / len(series)) * 100.0


def evaluate_indicators(
    current_price: float,
    chart_prices: List[float],
    weekly_closes: Optional[List[float]] = None,
    sma_period: int = 200,
    rsi_period: int = 14,
    rsi_oversold_threshold: float = 30.0,
    bb_period: int = 20,
    bb_std: float = 2.0,
) -> IndicatorResult:
    """Compute all indicators and determine basic threshold triggers.

    Note on 200-day SMA:
    If 200 daily points are available in chart_prices, use them.
    If weekly_closes is provided and has >= 40 bars, 40-week SMA is used
    as the standard industry equivalent for the 200-day trendline.
    """
    # 200-day SMA calculation
    sma_200: Optional[float] = None
    if len(chart_prices) >= sma_period:
        sma_200 = calculate_sma(chart_prices, sma_period)
    elif weekly_closes and len(weekly_closes) >= 40:
        # 40 weeks * 5 trading days = 200 trading days
        sma_200 = calculate_sma(weekly_closes, 40)
    elif len(chart_prices) >= 50:
        # Fallback to available sample period SMA
        sma_200 = calculate_sma(chart_prices, len(chart_prices))

    sma_200_diff_pct = None
    is_above_sma200 = False
    if sma_200 is not None and sma_200 > 0:
        sma_200_diff_pct = ((current_price - sma_200) / sma_200) * 100.0
        is_above_sma200 = current_price > sma_200

    # RSI-14
    rsi_14 = calculate_rsi(chart_prices, period=rsi_period)
    is_rsi_oversold = rsi_14 is not None and rsi_14 < rsi_oversold_threshold

    # Bollinger Bands (20, 2)
    bb_upper, bb_mid, bb_lower = calculate_bollinger_bands(
        chart_prices, period=bb_period, num_std=bb_std
    )

    is_below_bb_lower = False
    bb_pct_b = None
    if bb_upper is not None and bb_lower is not None:
        band_width = bb_upper - bb_lower
        if band_width > 0:
            bb_pct_b = (current_price - bb_lower) / band_width
        is_below_bb_lower = current_price < bb_lower

    return IndicatorResult(
        current_price=current_price,
        sma_200=sma_200,
        sma_200_diff_pct=sma_200_diff_pct,
        rsi_14=rsi_14,
        bb_upper=bb_upper,
        bb_mid=bb_mid,
        bb_lower=bb_lower,
        bb_pct_b=bb_pct_b,
        is_above_sma200=is_above_sma200,
        is_rsi_oversold=is_rsi_oversold,
        is_below_bb_lower=is_below_bb_lower,
    )
