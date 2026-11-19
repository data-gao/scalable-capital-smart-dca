"""Strategy logic for Smart / Value-Averaging DCA.

Evaluates indicators against target asset rules and produces structured decisions.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from smart_dca.config import TargetAssetConfig
from smart_dca.indicators import IndicatorResult


class SignalType(str, Enum):
    OVERVALUED = "OVERVALUED"         # Price > SMA200 -> Trim to 70%
    OVERSOLD_DIP = "OVERSOLD_DIP"     # Price < BB lower OR RSI < 30 -> Scale up or buy dip
    NEUTRAL = "NEUTRAL"               # Normal range -> Base 100%


@dataclass
class StrategyDecision:
    target: TargetAssetConfig
    indicators: IndicatorResult
    signal: SignalType
    current_plan_amount: Optional[float]
    recommended_plan_amount: float
    plan_action_needed: bool
    plan_action_description: str
    opportunistic_buy_amount: Optional[float]
    opportunistic_buy_shares: Optional[int]
    reasons: List[str]


def evaluate_asset_strategy(
    target: TargetAssetConfig,
    indicators: IndicatorResult,
    current_plan_amount: Optional[float] = None,
) -> StrategyDecision:
    """Evaluate target asset indicators against configured strategy rules."""
    reasons: List[str] = []
    signal: SignalType = SignalType.NEUTRAL

    # Check Rule 1: Oversold / Dip condition (High priority buying opportunity)
    # Trigger: Price < Bollinger Lower Band OR RSI < 30
    is_dip = False
    dip_reasons = []
    if target.oversold_rule.enabled:
        if indicators.is_below_bb_lower:
            is_dip = True
            diff_bb = (
                (indicators.current_price - indicators.bb_lower) / indicators.bb_lower * 100.0
                if indicators.bb_lower
                else 0.0
            )
            dip_reasons.append(
                f"Price ({indicators.current_price:.2f}) broke below Bollinger lower band ({indicators.bb_lower:.2f}, {diff_bb:.1f}%)"
            )

        if indicators.is_rsi_oversold:
            is_dip = True
            dip_reasons.append(
                f"RSI-14 ({indicators.rsi_14:.1f}) is oversold (< {target.oversold_rule.rsi_threshold:.1f})"
            )

    # Check Rule 2: Overvalued condition
    # Trigger: Price > 200-day SMA
    is_overvalued = False
    overvalued_reasons = []
    if target.overvalued_rule.enabled and indicators.is_above_sma200:
        is_overvalued = True
        diff_sma = indicators.sma_200_diff_pct if indicators.sma_200_diff_pct is not None else 0.0
        overvalued_reasons.append(
            f"Price ({indicators.current_price:.2f}) is above 200 SMA ({indicators.sma_200:.2f}, +{diff_sma:.1f}%)"
        )

    # Resolve signals and amounts
    recommended_plan_amount = target.base_amount
    opportunistic_buy_amount: Optional[float] = None
    opportunistic_buy_shares: Optional[int] = None

    if is_dip:
        signal = SignalType.OVERSOLD_DIP
        reasons.extend(dip_reasons)
        action_type = target.oversold_rule.action_type

        # Sizing for savings plan scale-up
        if action_type in ["scale_up_savings_plan", "both"]:
            scale_mult = target.oversold_rule.savings_plan_multiplier
            recommended_plan_amount = round(target.base_amount * scale_mult, 2)
            reasons.append(
                f"Dip detected: Scaling savings plan from {target.base_amount:.2f} to {recommended_plan_amount:.2f} (x{scale_mult:.2f})"
            )

        # Sizing for opportunistic trade buy
        if action_type in ["opportunistic_trade_buy", "both"]:
            # If explicit amount is set, use it; otherwise default to 1 share or ~50% base amount
            buy_amt = target.oversold_rule.trade_buy_amount
            if buy_amt is None or buy_amt <= 0:
                # Need at least 1 whole share for `sc broker trade buy`
                buy_amt = max(target.base_amount * 0.5, indicators.current_price * 1.02)
            # Ensure order amount >= current ask/mid price (Scalable rule: min 1 share)
            if buy_amt < indicators.current_price:
                buy_amt = round(indicators.current_price * 1.02, 2)
            opportunistic_buy_amount = round(buy_amt, 2)
            reasons.append(f"Dip detected: Recommending opportunistic buy order of €{opportunistic_buy_amount:.2f}")

    elif is_overvalued:
        signal = SignalType.OVERVALUED
        reasons.extend(overvalued_reasons)
        trim_mult = target.overvalued_rule.amount_multiplier
        recommended_plan_amount = round(target.base_amount * trim_mult, 2)
        reasons.append(
            f"Overvalued: Trimming savings plan from {target.base_amount:.2f} to {recommended_plan_amount:.2f} (x{trim_mult:.2f})"
        )

    else:
        signal = SignalType.NEUTRAL
        recommended_plan_amount = round(target.base_amount * target.neutral_multiplier, 2)
        reasons.append(f"Neutral zone: Maintaining base savings plan of €{recommended_plan_amount:.2f}")

    # Determine if savings plan adjustment is required
    plan_action_needed = False
    plan_action_desc = "No change needed"
    if current_plan_amount is not None:
        # Check if difference is greater than 1 EUR
        if abs(current_plan_amount - recommended_plan_amount) >= 1.0:
            plan_action_needed = True
            plan_action_desc = f"Adjust savings plan: €{current_plan_amount:.2f} -> €{recommended_plan_amount:.2f}"
    else:
        plan_action_needed = True
        plan_action_desc = f"Create new savings plan with €{recommended_plan_amount:.2f}"

    return StrategyDecision(
        target=target,
        indicators=indicators,
        signal=signal,
        current_plan_amount=current_plan_amount,
        recommended_plan_amount=recommended_plan_amount,
        plan_action_needed=plan_action_needed,
        plan_action_description=plan_action_desc,
        opportunistic_buy_amount=opportunistic_buy_amount,
        opportunistic_buy_shares=opportunistic_buy_shares,
        reasons=reasons,
    )
