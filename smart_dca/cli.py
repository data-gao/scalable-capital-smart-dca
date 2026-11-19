"""Command-line interface for Smart / Value-Averaging DCA.

Usage:
  python3 -m smart_dca status
  python3 -m smart_dca run [--dry-run | --preview | --live]
  python3 -m smart_dca plans
  python3 -m smart_dca backtest [--isin <ISIN>]
"""

import argparse
import logging
import sys
from typing import List, Optional

from smart_dca.backtest import run_backtest_simulation
from smart_dca.client import ScalableClient, ScalableCLIError
from smart_dca.config import AppConfig, TargetAssetConfig, load_config
from smart_dca.executor import DCAExecutor, ExecutionResult
from smart_dca.indicators import evaluate_indicators
from smart_dca.reporter import print_execution_summary, print_status_dashboard
from smart_dca.strategy import StrategyDecision, evaluate_asset_strategy

logger = logging.getLogger("smart_dca")


def collect_target_decisions(
    config: AppConfig, client: ScalableClient
) -> List[StrategyDecision]:
    """Fetch quotes, candles, and evaluate strategy for all configured targets."""
    # Fetch existing savings plans to know current amount
    try:
        active_plans = {p.isin: p for p in client.get_savings_plans()}
    except Exception as e:
        logger.warning(f"Could not fetch existing savings plans: {e}")
        active_plans = {}

    decisions: List[StrategyDecision] = []

    for target in config.targets:
        try:
            quote = client.get_quote(target.isin)
            candles_1y = client.get_candlesticks(target.isin, timeframe="one_year")
            chart_1y = client.get_chart(target.isin, timeframe="1y")

            chart_prices = [p["mid_price"] for p in chart_1y] if chart_1y else []
            weekly_closes = [float(c["close"]) for c in candles_1y] if candles_1y else []

            # If chart_prices is empty, fallback to weekly closes
            if not chart_prices and weekly_closes:
                chart_prices = weekly_closes

            indicators = evaluate_indicators(
                current_price=quote.mid_price,
                chart_prices=chart_prices,
                weekly_closes=weekly_closes,
                sma_period=target.overvalued_rule.sma_period,
                rsi_period=target.oversold_rule.rsi_period,
                rsi_oversold_threshold=target.oversold_rule.rsi_threshold,
                bb_period=target.oversold_rule.bollinger_period,
                bb_std=target.oversold_rule.bollinger_std,
            )

            # Match with existing plan
            curr_plan = active_plans.get(target.isin)
            curr_amount = curr_plan.amount if curr_plan else None

            # Fallback to configured execution day if not set
            if curr_plan and target.execution_day_of_month is None:
                target.execution_day_of_month = curr_plan.day_of_month

            decision = evaluate_asset_strategy(
                target=target,
                indicators=indicators,
                current_plan_amount=curr_amount,
            )
            decisions.append(decision)

        except Exception as e:
            print(f"\033[91m[ERROR]\033[0m Failed analyzing target {target.name} ({target.isin}): {e}")

    return decisions


def cmd_status(args: argparse.Namespace, config: AppConfig, client: ScalableClient) -> int:
    """Print market indicators and strategic signals."""
    decisions = collect_target_decisions(config, client)
    if not decisions:
        print("No valid target assets analyzed.")
        return 1

    print_status_dashboard(decisions, mode=config.mode)
    return 0


def cmd_run(args: argparse.Namespace, config: AppConfig, client: ScalableClient) -> int:
    """Run strategy and execute plan adjustments / opportunistic buys."""
    if args.dry_run:
        config.mode = "dry-run"
    elif args.preview:
        config.mode = "preview"
    elif args.live:
        config.mode = "live"

    decisions = collect_target_decisions(config, client)
    if not decisions:
        print("No targets found to execute.")
        return 1

    print_status_dashboard(decisions, mode=config.mode)

    executor = DCAExecutor(config, client)
    results: List[ExecutionResult] = []

    for d in decisions:
        # 1. Savings plan adjustment
        plan_res = executor.execute_plan_adjustment(d)
        results.append(plan_res)

        # 2. Opportunistic buy (if dip triggered and configured)
        if d.opportunistic_buy_amount:
            buy_res = executor.execute_opportunistic_buy(d)
            results.append(buy_res)

    print_execution_summary(results)
    return 0


def cmd_plans(args: argparse.Namespace, config: AppConfig, client: ScalableClient) -> int:
    """List active savings plans in Scalable Capital account."""
    plans = client.get_savings_plans()
    print(f"\nActive Savings Plans in Scalable Capital ({len(plans)} plans):")
    print(f"{'ISIN':<15} {'Name':<35} {'Amount':<10} {'Day':<6} {'Freq':<10} {'Next Execution'}")
    print("-" * 90)
    for p in plans:
        print(f"{p.isin:<15} {p.name[:33]:<35} €{p.amount:<9.2f} {p.day_of_month:<6} {p.frequency:<10} {p.next_execution_date}")
    print("-" * 90)
    total = sum(p.amount for p in plans)
    print(f"Total Monthly Savings Volume: €{total:.2f}\n")
    return 0


def cmd_backtest(args: argparse.Namespace, config: AppConfig, client: ScalableClient) -> int:
    """Run backtest comparison."""
    target_isins = [args.isin] if args.isin else [t.isin for t in config.targets]
    print(f"\nRunning Backtest Simulation (Smart DCA vs Standard DCA)...")
    print("=" * 80)

    for isin in target_isins:
        try:
            quote = client.get_quote(isin)
            candles = client.get_candlesticks(isin, timeframe="one_year")
            res = run_backtest_simulation(isin=isin, candles=candles)

            print(f"\n  Asset: {quote.name} ({isin}) - {res.periods} Weekly Periods")
            print(f"  -------------------------------------------------------------")
            print(f"  Standard DCA: Total €{res.standard_total_invested:.2f} | Shares: {res.standard_shares:.4f} | Avg Cost: €{res.standard_avg_cost:.2f} | Return: {res.standard_return_pct:+.2f}%")
            print(f"  Smart DCA:    Total €{res.smart_total_invested:.2f} | Shares: {res.smart_shares:.4f} | Avg Cost: €{res.smart_avg_cost:.2f} | Return: {res.smart_return_pct:+.2f}%")
            diff_color = "\033[92m" if res.outperformance_pct >= 0 else "\033[91m"
            print(f"  Alpha / Outperformance: {diff_color}{res.outperformance_pct:+.2f}%\033[0m")
        except Exception as e:
            print(f"Failed backtest for {isin}: {e}")

    print("=" * 80 + "\n")
    return 0


def cmd_dashboard(args: argparse.Namespace, config: AppConfig, client: ScalableClient) -> int:
    """Open or serve the interactive Strategy Studio & Backtest Dashboard."""
    import os
    import webbrowser
    from pathlib import Path

    dashboard_file = Path(__file__).resolve().parent.parent / "dashboard" / "index.html"
    if not dashboard_file.exists():
        print(f"\033[91m[ERROR]\033[0m Dashboard file not found at {dashboard_file}")
        return 1

    file_url = f"file://{dashboard_file}"
    print(f"\nOpening Interactive Dashboard in browser: {file_url}")
    webbrowser.open(file_url)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scalable Capital Smart / Value-Averaging DCA",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-c", "--config", default="config.toml", help="Path to config file (default: config.toml)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose debug logging")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # status / check
    status_parser = subparsers.add_parser("status", aliases=["check"], help="Check indicators and signals")

    # run
    run_parser = subparsers.add_parser("run", help="Run strategy evaluation and executions")
    run_group = run_parser.add_mutually_exclusive_group()
    run_group.add_argument("--dry-run", action="store_true", help="Dry-run mode (simulation only, default)")
    run_group.add_argument("--preview", action="store_true", help="Preview mode (runs Phase 1 preview and cost disclosure)")
    run_group.add_argument("--live", action="store_true", help="Live execution mode (executes orders/plan changes)")

    # plans
    plans_parser = subparsers.add_parser("plans", help="List active savings plans")

    # backtest
    backtest_parser = subparsers.add_parser("backtest", help="Simulate historical performance vs standard DCA")
    backtest_parser.add_argument("--isin", help="Specific ISIN to backtest")

    # dashboard
    dashboard_parser = subparsers.add_parser("dashboard", help="Open interactive strategy studio & backtest dashboard")

    args = parser.parse_args()

    # Logging setup
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    try:
        config = load_config(args.config)
        client = ScalableClient(config.sc_binary)
    except Exception as e:
        print(f"\033[91m[INIT ERROR]\033[0m {e}")
        return 1

    if args.command in ["status", "check"]:
        return cmd_status(args, config, client)
    elif args.command == "run":
        return cmd_run(args, config, client)
    elif args.command == "plans":
        return cmd_plans(args, config, client)
    elif args.command == "backtest":
        return cmd_backtest(args, config, client)
    elif args.command == "dashboard":
        return cmd_dashboard(args, config, client)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
