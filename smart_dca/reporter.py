"""Reporting and visualization module for Smart / Value-Averaging DCA.

Renders formatted terminal tables and status dashboards.
"""

from typing import List, Optional
from smart_dca.strategy import StrategyDecision, SignalType
from smart_dca.executor import ExecutionResult


def format_signal_badge(signal: SignalType) -> str:
    """Format signal badge with colors/emojis."""
    if signal == SignalType.OVERVALUED:
        return "\033[93m[OVERVALUED - TRIM 70%]\033[0m"
    elif signal == SignalType.OVERSOLD_DIP:
        return "\033[92m[DIP DETECTED - SCALE/BUY]\033[0m"
    else:
        return "\033[94m[NEUTRAL - 100% BASE]\033[0m"


def print_status_dashboard(decisions: List[StrategyDecision], mode: str) -> None:
    """Print an executive summary table of all tracked assets."""
    border = "=" * 80
    sub_border = "-" * 80

    print(f"\n{border}")
    print(f"  SCALABLE CAPITAL SMART / VALUE-AVERAGING DCA ENGINE (Mode: {mode.upper()})")
    print(f"{border}")

    for idx, d in enumerate(decisions, 1):
        target = d.target
        ind = d.indicators
        badge = format_signal_badge(d.signal)

        curr_price_str = f"€{ind.current_price:.2f}"
        sma_str = f"€{ind.sma_200:.2f}" if ind.sma_200 else "N/A"
        sma_diff_str = (
            f"({'+' if ind.sma_200_diff_pct and ind.sma_200_diff_pct > 0 else ''}{ind.sma_200_diff_pct:.1f}%)"
            if ind.sma_200_diff_pct is not None
            else ""
        )
        rsi_str = f"{ind.rsi_14:.1f}" if ind.rsi_14 is not None else "N/A"
        bb_str = (
            f"[{ind.bb_lower:.2f} ~ {ind.bb_upper:.2f}]"
            if ind.bb_lower and ind.bb_upper
            else "N/A"
        )

        curr_plan_str = f"€{d.current_plan_amount:.2f}" if d.current_plan_amount is not None else "None"
        rec_plan_str = f"€{d.recommended_plan_amount:.2f}"

        print(f"\n  #{idx}  {target.name} ({target.isin})")
        print(f"      Signal:         {badge}")
        print(f"      Current Price:  {curr_price_str}")
        print(f"      200-SMA:        {sma_str} {sma_diff_str}")
        print(f"      RSI-14:         {rsi_str}")
        print(f"      Bollinger (20): {bb_str}")
        print(f"      Savings Plan:   Current: {curr_plan_str}  -->  Recommended: \033[1m{rec_plan_str}\033[0m")
        if d.opportunistic_buy_amount:
            print(f"      Buy Order:      \033[92mRecommended Dip Buy: €{d.opportunistic_buy_amount:.2f}\033[0m")
        print("      Rationale:")
        for r in d.reasons:
            print(f"        • {r}")

    print(f"\n{sub_border}\n")


def print_execution_summary(results: List[ExecutionResult]) -> None:
    """Print results of the execution phase."""
    print("  EXECUTION ACTIONS SUMMARY:")
    for res in results:
        status_color = "\033[92m" if res.status in ["SUCCESS", "PREVIEWED", "SIMULATED"] else "\033[91m"
        print(
            f"    • {res.target_name} [{res.action_type}]: "
            f"{status_color}{res.status}\033[0m - {res.message}"
        )
    print("")
