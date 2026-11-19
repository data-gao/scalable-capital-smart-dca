"""Configuration management for Smart / Value-Averaging DCA.

Loads settings from TOML, JSON, or YAML with full typing and default fallbacks.
"""

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import tomllib  # Python 3.11+ standard library
except ImportError:
    tomllib = None  # type: ignore

try:
    import yaml  # optional PyYAML
except ImportError:
    yaml = None  # type: ignore


@dataclass
class OvervaluedRuleConfig:
    enabled: bool = True
    condition: str = "price_above_sma"  # price_above_sma
    sma_period: int = 200
    amount_multiplier: float = 0.70  # Trim to 70% of base amount


@dataclass
class OversoldRuleConfig:
    enabled: bool = True
    condition: str = "bollinger_lower_or_rsi_oversold"
    rsi_period: int = 14
    rsi_threshold: float = 30.0
    bollinger_period: int = 20
    bollinger_std: float = 2.0
    action_type: str = "scale_up_savings_plan"  # "scale_up_savings_plan", "opportunistic_trade_buy", or "both"
    savings_plan_multiplier: float = 1.30  # Scale up to 130% of base amount
    trade_buy_amount: Optional[float] = None  # If trade buy is chosen, fixed EUR amount (or calculated)


@dataclass
class TargetAssetConfig:
    isin: str
    name: str
    base_amount: float
    execution_day_of_month: Optional[int] = None
    overvalued_rule: OvervaluedRuleConfig = field(default_factory=OvervaluedRuleConfig)
    oversold_rule: OversoldRuleConfig = field(default_factory=OversoldRuleConfig)
    neutral_multiplier: float = 1.0


@dataclass
class SafetyConfig:
    max_monthly_budget: float = 2000.0  # Max total savings plan budget across all assets
    max_single_trade_amount: float = 500.0  # Max for opportunistic dip buy
    opportunistic_buy_cooldown_days: int = 7  # Cooldown between one-off buy orders per asset


@dataclass
class AppConfig:
    mode: str = "dry-run"  # "dry-run", "preview", "live"
    sc_binary: Optional[str] = None
    state_file: str = ".smart_dca_state.json"
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    targets: List[TargetAssetConfig] = field(default_factory=list)


def parse_dict_to_config(data: Dict[str, Any]) -> AppConfig:
    """Parse raw dictionary into AppConfig."""
    app_data = data.get("app", {})
    mode = app_data.get("mode", data.get("mode", "dry-run"))
    sc_bin = app_data.get("sc_binary", data.get("sc_binary"))
    state_file = app_data.get("state_file", data.get("state_file", ".smart_dca_state.json"))

    safety_data = data.get("safety", {})
    safety = SafetyConfig(
        max_monthly_budget=float(safety_data.get("max_monthly_budget", 2000.0)),
        max_single_trade_amount=float(safety_data.get("max_single_trade_amount", 500.0)),
        opportunistic_buy_cooldown_days=int(safety_data.get("opportunistic_buy_cooldown_days", 7)),
    )

    targets_raw = data.get("targets", [])
    targets: List[TargetAssetConfig] = []

    for t in targets_raw:
        ov_raw = t.get("overvalued_rule", {})
        ov_rule = OvervaluedRuleConfig(
            enabled=bool(ov_raw.get("enabled", True)),
            condition=str(ov_raw.get("condition", "price_above_sma")),
            sma_period=int(ov_raw.get("sma_period", 200)),
            amount_multiplier=float(ov_raw.get("amount_multiplier", 0.70)),
        )

        os_raw = t.get("oversold_rule", {})
        os_rule = OversoldRuleConfig(
            enabled=bool(os_raw.get("enabled", True)),
            condition=str(os_raw.get("condition", "bollinger_lower_or_rsi_oversold")),
            rsi_period=int(os_raw.get("rsi_period", 14)),
            rsi_threshold=float(os_raw.get("rsi_threshold", 30.0)),
            bollinger_period=int(os_raw.get("bollinger_period", 20)),
            bollinger_std=float(os_raw.get("bollinger_std", 2.0)),
            action_type=str(os_raw.get("action_type", "scale_up_savings_plan")),
            savings_plan_multiplier=float(os_raw.get("savings_plan_multiplier", 1.30)),
            trade_buy_amount=float(os_raw["trade_buy_amount"]) if os_raw.get("trade_buy_amount") else None,
        )

        target = TargetAssetConfig(
            isin=str(t["isin"]).strip(),
            name=str(t.get("name", t["isin"])),
            base_amount=float(t["base_amount"]),
            execution_day_of_month=t.get("execution_day_of_month"),
            overvalued_rule=ov_rule,
            oversold_rule=os_rule,
            neutral_multiplier=float(t.get("neutral_multiplier", 1.0)),
        )
        targets.append(target)

    return AppConfig(
        mode=mode,
        sc_binary=sc_bin,
        state_file=state_file,
        safety=safety,
        targets=targets,
    )


def load_config(path: str = "config.toml") -> AppConfig:
    """Load configuration file from TOML, JSON, or YAML."""
    p = Path(path)
    if not p.exists():
        # Fallbacks to check
        for candidate in ["config.toml", "config.json", "config.yaml", "config.yml"]:
            if Path(candidate).exists():
                p = Path(candidate)
                break

    if not p.exists():
        raise FileNotFoundError(f"Configuration file not found at '{path}'. Please create 'config.toml'.")

    suffix = p.suffix.lower()
    content = p.read_text(encoding="utf-8")

    if suffix == ".toml":
        if tomllib is None:
            raise RuntimeError("Python 3.11+ is required for built-in TOML support.")
        data = tomllib.loads(content)
    elif suffix == ".json":
        data = json.loads(content)
    elif suffix in [".yaml", ".yml"]:
        if yaml is None:
            raise RuntimeError("PyYAML is not installed. Please use .toml or .json config, or run 'pip install pyyaml'.")
        data = yaml.safe_load(content)
    else:
        # Default try TOML, then JSON
        try:
            data = tomllib.loads(content) if tomllib else json.loads(content)
        except Exception:
            data = json.loads(content)

    return parse_dict_to_config(data)
