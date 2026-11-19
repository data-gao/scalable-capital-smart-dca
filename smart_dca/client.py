"""Client interface wrapping the official Scalable Capital CLI (`sc`).

Handles execution, JSON parsing, error checks, and preview/confirmation workflows.
"""

from dataclasses import dataclass
import json
import logging
import os
import shutil
import subprocess
from typing import Any, Dict, List, Optional

logger = logging.getLogger("smart_dca.client")


class ScalableCLIError(Exception):
    """Exception raised when an `sc` command fails."""

    def __init__(self, message: str, code: Optional[str] = None, hints: Optional[List[str]] = None):
        super().__init__(message)
        self.code = code
        self.hints = hints or []


@dataclass
class QuoteData:
    isin: str
    name: str
    mid_price: float
    ask_price: float
    bid_price: float
    currency: str
    timestamp_utc: str


@dataclass
class SavingsPlanItem:
    isin: str
    name: str
    amount: float
    day_of_month: int
    frequency: str
    payment_method: str
    next_execution_date: str


class ScalableClient:
    """Wrapper around `sc` command line."""

    def __init__(self, binary_path: Optional[str] = None):
        self.binary = binary_path or shutil.which("sc") or "/opt/homebrew/bin/sc"
        if not os.path.exists(self.binary):
            raise FileNotFoundError(f"Scalable CLI binary not found at '{self.binary}'. Please install scalable-cli.")

    def run_sc(self, args: List[str], timeout: int = 30) -> Dict[str, Any]:
        """Execute `sc` command with `--json` flag and parse output."""
        cmd = [self.binary] + args
        if "--json" not in cmd:
            cmd.append("--json")

        logger.debug(f"Executing: {' '.join(cmd)}")
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as e:
            raise ScalableCLIError(f"Command timed out after {timeout}s: {' '.join(cmd)}") from e
        except Exception as e:
            raise ScalableCLIError(f"Failed to spawn command '{' '.join(cmd)}': {str(e)}") from e

        raw_output = res.stdout.strip()
        if not raw_output and res.stderr:
            raise ScalableCLIError(f"Command produced no stdout. Error: {res.stderr.strip()}")

        try:
            data = json.loads(raw_output)
        except json.JSONDecodeError:
            raise ScalableCLIError(
                f"Failed to parse JSON response: {raw_output[:200]}... (stderr: {res.stderr.strip()})"
            )

        if not data.get("ok", False):
            err_obj = data.get("error", {})
            err_msg = err_obj.get("message", "Unknown error from sc CLI")
            err_code = err_obj.get("code")
            hints = data.get("hints", [])
            raise ScalableCLIError(err_msg, code=err_code, hints=hints)

        return data.get("data", {})

    def get_quote(self, isin: str) -> QuoteData:
        """Fetch latest live quote for an ISIN."""
        data = self.run_sc(["broker", "quote", "--isin", isin])
        res = data.get("result", {})
        return QuoteData(
            isin=res.get("isin", isin),
            name=res.get("name", "Unknown"),
            mid_price=float(res.get("quote_mid_price", 0.0)),
            ask_price=float(res.get("quote_ask_price", 0.0)),
            bid_price=float(res.get("quote_bid_price", 0.0)),
            currency=res.get("quote_currency", "EUR"),
            timestamp_utc=res.get("quote_timestamp_utc", ""),
        )

    def get_candlesticks(self, isin: str, timeframe: str = "one_year") -> List[Dict[str, Any]]:
        """Fetch historical candlesticks."""
        data = self.run_sc(["broker", "candlesticks", "--isin", isin, "--timeframe", timeframe])
        return data.get("candlesticks", [])

    def get_chart(self, isin: str, timeframe: str = "1y") -> List[Dict[str, Any]]:
        """Fetch historical chart data points (typically daily/bi-daily mid prices)."""
        data = self.run_sc(["broker", "chart", "--isin", isin, "--timeframe", timeframe])
        return data.get("data_points", [])

    def get_savings_plans(self) -> List[SavingsPlanItem]:
        """Fetch all existing savings plans for the active portfolio context."""
        data = self.run_sc(["broker", "savings-plans"])
        items = data.get("result", {}).get("items", [])
        plans = []
        for it in items:
            plans.append(
                SavingsPlanItem(
                    isin=it.get("isin", ""),
                    name=it.get("name", ""),
                    amount=float(it.get("amount", 0.0)),
                    day_of_month=int(it.get("day_of_month", 0)),
                    frequency=it.get("frequency", "MONTHLY"),
                    payment_method=it.get("payment_method", "REFERENCE_ACCOUNT"),
                    next_execution_date=it.get("next_execution_date", ""),
                )
            )
        return plans

    def preview_savings_plan(
        self,
        isin: str,
        amount: float,
        frequency: Optional[str] = None,
        day_of_month: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Run Phase 1 preview for creating or updating a savings plan."""
        args = ["broker", "savings-plans", "add", "--isin", isin, "--amount", str(amount)]
        if frequency:
            args.extend(["--frequency", frequency])
        if day_of_month is not None:
            args.extend(["--day-of-month", str(day_of_month)])
        return self.run_sc(args)

    def confirm_savings_plan(
        self,
        isin: str,
        amount: float,
        confirmation_id: str,
        frequency: Optional[str] = None,
        day_of_month: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Run Phase 2 confirmation to actually commit savings plan change."""
        args = [
            "broker",
            "savings-plans",
            "add",
            "--isin",
            isin,
            "--amount",
            str(amount),
            "--confirm",
            confirmation_id,
        ]
        if frequency:
            args.extend(["--frequency", frequency])
        if day_of_month is not None:
            args.extend(["--day-of-month", str(day_of_month)])
        return self.run_sc(args)

    def preview_trade_buy(
        self,
        isin: str,
        amount: Optional[float] = None,
        shares: Optional[int] = None,
        order_type: str = "market",
        limit_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Run Phase 1 preview for an opportunistic one-off buy trade."""
        args = ["broker", "trade", "buy", "--isin", isin, "--order-type", order_type]
        if amount is not None:
            args.extend(["--amount", str(amount)])
        elif shares is not None:
            args.extend(["--shares", str(shares)])
        else:
            raise ValueError("Either amount or shares must be specified for trade buy.")

        if limit_price is not None:
            args.extend(["--limit-price", str(limit_price)])

        return self.run_sc(args)

    def confirm_trade_buy(
        self,
        isin: str,
        confirmation_id: str,
        amount: Optional[float] = None,
        shares: Optional[int] = None,
        order_type: str = "market",
        limit_price: Optional[float] = None,
        acknowledge_appropriateness: bool = False,
    ) -> Dict[str, Any]:
        """Run Phase 2 confirmation to execute the one-off buy trade."""
        args = [
            "broker",
            "trade",
            "buy",
            "--isin",
            isin,
            "--order-type",
            order_type,
            "--confirm",
            confirmation_id,
        ]
        if amount is not None:
            args.extend(["--amount", str(amount)])
        elif shares is not None:
            args.extend(["--shares", str(shares)])

        if limit_price is not None:
            args.extend(["--limit-price", str(limit_price)])

        if acknowledge_appropriateness:
            args.append("--acknowledge-appropriateness-warning")

        return self.run_sc(args)
