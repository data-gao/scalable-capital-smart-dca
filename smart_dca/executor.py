"""Execution engine with two-phase safety controls and budget constraints.

Executes savings plan updates and opportunistic trade buy orders.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from smart_dca.client import ScalableClient, ScalableCLIError
from smart_dca.config import AppConfig
from smart_dca.strategy import StrategyDecision

logger = logging.getLogger("smart_dca.executor")


@dataclass
class ExecutionResult:
    isin: str
    target_name: str
    action_type: str  # "savings_plan_update", "trade_buy", "skipped"
    status: str       # "SUCCESS", "PREVIEWED", "SIMULATED", "SKIPPED", "FAILED"
    amount: float
    confirmation_id: Optional[str] = None
    message: str = ""
    error: Optional[str] = None


class DCAExecutor:
    """Safely executes strategy decisions against Scalable Capital."""

    def __init__(self, config: AppConfig, client: Optional[ScalableClient] = None):
        self.config = config
        self.client = client or ScalableClient(config.sc_binary)
        self.state_file = Path(config.state_file)
        self.state = self._load_state()

    def _load_state(self) -> Dict[str, Any]:
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"Could not load state file {self.state_file}: {e}")
        return {"last_runs": {}, "opportunistic_buys": {}, "history": []}

    def _save_state(self) -> None:
        try:
            self.state_file.write_text(json.dumps(self.state, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save state file: {e}")

    def _check_cooldown(self, isin: str) -> bool:
        """Check if an opportunistic buy is in cooldown."""
        last_buy = self.state.get("opportunistic_buys", {}).get(isin)
        if not last_buy:
            return True
        last_dt = datetime.fromisoformat(last_buy)
        days_passed = (datetime.now(timezone.utc) - last_dt).total_seconds() / 86400.0
        return days_passed >= self.config.safety.opportunistic_buy_cooldown_days

    def execute_plan_adjustment(self, decision: StrategyDecision) -> ExecutionResult:
        """Adjust a savings plan according to strategy decision."""
        isin = decision.target.isin
        target_name = decision.target.name
        new_amount = decision.recommended_plan_amount
        mode = self.config.mode.lower()

        if not decision.plan_action_needed:
            return ExecutionResult(
                isin=isin,
                target_name=target_name,
                action_type="savings_plan_update",
                status="SKIPPED",
                amount=new_amount,
                message="Current plan amount already matches recommended amount.",
            )

        if mode == "dry-run":
            cmd = f"sc broker savings-plans add --isin {isin} --amount {new_amount}"
            return ExecutionResult(
                isin=isin,
                target_name=target_name,
                action_type="savings_plan_update",
                status="SIMULATED",
                amount=new_amount,
                message=f"[DRY-RUN] Would execute: {cmd}",
            )

        # Mode preview or live: Run Phase 1
        try:
            logger.info(f"Running Phase 1 preview for {target_name} ({isin}) with amount €{new_amount:.2f}")
            preview = self.client.preview_savings_plan(
                isin=isin,
                amount=new_amount,
                day_of_month=decision.target.execution_day_of_month,
            )
            conf_info = preview.get("confirmation", {})
            conf_id = conf_info.get("id")

            if mode == "preview":
                return ExecutionResult(
                    isin=isin,
                    target_name=target_name,
                    action_type="savings_plan_update",
                    status="PREVIEWED",
                    amount=new_amount,
                    confirmation_id=conf_id,
                    message=f"[PREVIEW] Cost disclosure validated. Confirmation ID: {conf_id}",
                )

            # Live mode: Phase 2 confirmation
            if not conf_id:
                raise ScalableCLIError("Phase 1 preview did not return a confirmation ID.")

            logger.info(f"Confirming Phase 2 for {target_name} with confirmation ID {conf_id}")
            confirm_res = self.client.confirm_savings_plan(
                isin=isin,
                amount=new_amount,
                confirmation_id=conf_id,
                day_of_month=decision.target.execution_day_of_month,
            )
            return ExecutionResult(
                isin=isin,
                target_name=target_name,
                action_type="savings_plan_update",
                status="SUCCESS",
                amount=new_amount,
                confirmation_id=conf_id,
                message=f"[LIVE] Savings plan successfully updated to €{new_amount:.2f}",
            )
        except ScalableCLIError as e:
            return ExecutionResult(
                isin=isin,
                target_name=target_name,
                action_type="savings_plan_update",
                status="FAILED",
                amount=new_amount,
                error=str(e),
                message=f"Failed to update savings plan: {e}",
            )

    def execute_opportunistic_buy(self, decision: StrategyDecision) -> ExecutionResult:
        """Execute a one-off trade buy when a dip is detected."""
        isin = decision.target.isin
        target_name = decision.target.name
        amount = decision.opportunistic_buy_amount or 0.0
        mode = self.config.mode.lower()

        if amount <= 0:
            return ExecutionResult(
                isin=isin,
                target_name=target_name,
                action_type="trade_buy",
                status="SKIPPED",
                amount=0.0,
                message="No opportunistic buy amount requested.",
            )

        # Check safety caps
        if amount > self.config.safety.max_single_trade_amount:
            return ExecutionResult(
                isin=isin,
                target_name=target_name,
                action_type="trade_buy",
                status="SKIPPED",
                amount=amount,
                message=f"Amount €{amount:.2f} exceeds safety max_single_trade_amount (€{self.config.safety.max_single_trade_amount:.2f}).",
            )

        # Check cooldown
        if not self._check_cooldown(isin):
            return ExecutionResult(
                isin=isin,
                target_name=target_name,
                action_type="trade_buy",
                status="SKIPPED",
                amount=amount,
                message=f"In cooldown period ({self.config.safety.opportunistic_buy_cooldown_days} days). Skipping buy.",
            )

        if mode == "dry-run":
            cmd = f"sc broker trade buy --isin {isin} --amount {amount:.2f}"
            return ExecutionResult(
                isin=isin,
                target_name=target_name,
                action_type="trade_buy",
                status="SIMULATED",
                amount=amount,
                message=f"[DRY-RUN] Would execute opportunistic buy: {cmd}",
            )

        # Preview or Live mode
        try:
            logger.info(f"Running Phase 1 preview for buy trade on {target_name} ({isin}) with amount €{amount:.2f}")
            preview = self.client.preview_trade_buy(isin=isin, amount=amount)
            conf_info = preview.get("confirmation", {})
            conf_id = conf_info.get("id")

            if mode == "preview":
                return ExecutionResult(
                    isin=isin,
                    target_name=target_name,
                    action_type="trade_buy",
                    status="PREVIEWED",
                    amount=amount,
                    confirmation_id=conf_id,
                    message=f"[PREVIEW] Pre-trade checks passed. Confirmation ID: {conf_id}",
                )

            # Live mode: Phase 2 confirmation
            if not conf_id:
                raise ScalableCLIError("Phase 1 preview did not return a confirmation ID.")

            logger.info(f"Confirming Phase 2 buy trade for {target_name} with confirmation ID {conf_id}")
            self.client.confirm_trade_buy(
                isin=isin,
                confirmation_id=conf_id,
                amount=amount,
            )

            # Record cooldown
            self.state.setdefault("opportunistic_buys", {})[isin] = datetime.now(timezone.utc).isoformat()
            self._save_state()

            return ExecutionResult(
                isin=isin,
                target_name=target_name,
                action_type="trade_buy",
                status="SUCCESS",
                amount=amount,
                confirmation_id=conf_id,
                message=f"[LIVE] Opportunistic buy order placed for €{amount:.2f}",
            )
        except ScalableCLIError as e:
            return ExecutionResult(
                isin=isin,
                target_name=target_name,
                action_type="trade_buy",
                status="FAILED",
                amount=amount,
                error=str(e),
                message=f"Failed to place opportunistic buy trade: {e}",
            )
