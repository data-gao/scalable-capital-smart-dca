"""Backtest simulator comparing Smart / Value-Averaging DCA against Standard Fixed DCA.

Uses historical candlestick data points from Scalable Capital.
"""

from dataclasses import dataclass
from typing import Any, Dict, List
from smart_dca.indicators import calculate_bollinger_bands, calculate_rsi, calculate_sma


@dataclass
class BacktestResult:
    isin: str
    periods: int
    standard_total_invested: float
    standard_shares: float
    standard_final_value: float
    standard_return_pct: float
    standard_avg_cost: float

    smart_total_invested: float
    smart_shares: float
    smart_final_value: float
    smart_return_pct: float
    smart_avg_cost: float

    outperformance_pct: float


def run_backtest_simulation(
    isin: str,
    candles: List[Dict[str, Any]],
    base_amount: float = 400.0,
    trim_multiplier: float = 0.70,
    scale_multiplier: float = 1.30,
    sma_period: int = 40,  # 40 weekly bars ~ 200 trading days
) -> BacktestResult:
    """Run historical simulation on weekly candlestick bars."""
    closes = [float(c["close"]) for c in candles]
    if len(closes) < 20:
        raise ValueError("Not enough candlestick data points to backtest.")

    std_invested = 0.0
    std_shares = 0.0

    smart_invested = 0.0
    smart_shares = 0.0

    # Start simulation once we have enough bars for indicators
    start_idx = min(20, len(closes) // 2)

    for i in range(start_idx, len(closes)):
        price = closes[i]
        hist = closes[: i + 1]

        # Standard DCA: invest base_amount every period
        std_invested += base_amount
        std_shares += base_amount / price

        # Smart DCA evaluation
        sma = calculate_sma(hist, min(sma_period, len(hist)))
        rsi = calculate_rsi(hist, period=14)
        bb_upper, bb_mid, bb_lower = calculate_bollinger_bands(hist, period=20, num_std=2.0)

        is_dip = False
        if bb_lower and price < bb_lower:
            is_dip = True
        if rsi and rsi < 30.0:
            is_dip = True

        is_overvalued = sma is not None and price > sma

        if is_dip:
            invest = base_amount * scale_multiplier
        elif is_overvalued:
            invest = base_amount * trim_multiplier
        else:
            invest = base_amount

        smart_invested += invest
        smart_shares += invest / price

    last_price = closes[-1]
    std_final_val = std_shares * last_price
    std_return_pct = ((std_final_val - std_invested) / std_invested * 100.0) if std_invested > 0 else 0.0
    std_avg_cost = std_invested / std_shares if std_shares > 0 else 0.0

    smart_final_val = smart_shares * last_price
    smart_return_pct = ((smart_final_val - smart_invested) / smart_invested * 100.0) if smart_invested > 0 else 0.0
    smart_avg_cost = smart_invested / smart_shares if smart_shares > 0 else 0.0

    outperformance = smart_return_pct - std_return_pct

    return BacktestResult(
        isin=isin,
        periods=len(closes) - start_idx,
        standard_total_invested=std_invested,
        standard_shares=std_shares,
        standard_final_value=std_final_val,
        standard_return_pct=std_return_pct,
        standard_avg_cost=std_avg_cost,
        smart_total_invested=smart_invested,
        smart_shares=smart_shares,
        smart_final_value=smart_final_val,
        smart_return_pct=smart_return_pct,
        smart_avg_cost=smart_avg_cost,
        outperformance_pct=outperformance,
    )
