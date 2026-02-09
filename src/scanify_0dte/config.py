"""
SCANIFY SPX 0DTE Options Day Trading Scanner + GEX Scanner -- Configuration Module

Provides centralised configuration management, validation, persistence, and
live-reload capability for the entire SCANIFY 0DTE system.

Configuration is expressed as a Pydantic BaseModel (`ScanifyConfig`) with
comprehensive field-level and cross-field validators.  Values are loaded from
a YAML file (defaulting to ``config.yaml`` under the ``scanify`` section) and
fall back to sensible defaults sourced from the constants module.

Usage
-----
    from scanify_0dte.config import load_config, ScanifyConfig

    cfg = load_config("config.yaml")       # load from YAML
    cfg = ScanifyConfig()                   # all defaults
    cfg = merge_configs(cfg, overrides)     # patch at runtime

Runtime hot-reload is supported through ``ConfigWatcher``, which polls the
file for changes and invokes a user-supplied callback.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml
from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
)

from scanify_0dte.constants import (
    DEFAULT_FACTOR_WEIGHTS,
    DELTA_DECAY,
    DIRECTION_THRESHOLDS,
    EXIT_MANAGEMENT,
    GEX_SCANNER,
    PREMIUM_SELLING,
    RISK_MANAGEMENT,
    SELF_LEARNING,
    STRIKE_SELECTION,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Allowed values for constrained string fields
# ---------------------------------------------------------------------------
_ALLOWED_DATA_PROVIDERS = frozenset({"polygon", "alpaca", "cboe", "mock"})
_ALLOWED_GEX_DEALER_MODELS = frozenset({"simple", "flow", "hybrid"})
_ALLOWED_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})

# Regex for HH:MM time strings (00:00 through 23:59)
_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


# =============================================================================
# ScanifyConfig
# =============================================================================


class ScanifyConfig(BaseModel):
    """Complete configuration for the SCANIFY 0DTE SPX Scanner system.

    Every field carries a production-safe default so that
    ``ScanifyConfig()`` returns a valid, ready-to-run configuration.
    Validators enforce cross-field consistency, range constraints, and
    domain-specific invariants.
    """

    # -----------------------------------------------------------------------
    # Data Provider
    # -----------------------------------------------------------------------
    data_provider: str = Field(
        default="mock",
        description="Data provider backend: polygon, alpaca, cboe, or mock.",
    )
    api_key: str = Field(
        default="",
        description="API key for the selected data provider.",
    )
    data_update_interval: float = Field(
        default=1.0,
        gt=0,
        description="Seconds between market-data refresh cycles.",
    )
    vix_update_interval: float = Field(
        default=15.0,
        gt=0,
        description="Seconds between VIX1D data refreshes.",
    )

    # -----------------------------------------------------------------------
    # Trading Mode
    # -----------------------------------------------------------------------
    paper_trade: bool = Field(
        default=True,
        description="Run in paper-trading mode (no real orders).",
    )
    risk_budget_daily: float = Field(
        default=10_000.0,
        gt=0,
        description="Maximum daily risk budget in USD.",
    )
    max_risk_per_trade_pct: float = Field(
        default=RISK_MANAGEMENT.max_risk_per_trade_pct,
        ge=0,
        le=1,
        description="Maximum risk per trade as a fraction of the daily budget.",
    )
    max_daily_trades: int = Field(
        default=50,
        ge=1,
        description="Maximum number of trades allowed per day.",
    )
    max_concurrent_positions: int = Field(
        default=10,
        ge=1,
        description="Maximum number of simultaneously open positions.",
    )
    commission_per_contract: float = Field(
        default=0.65,
        ge=0,
        description="Commission per contract in USD.",
    )

    # -----------------------------------------------------------------------
    # Scanner Settings
    # -----------------------------------------------------------------------
    enable_directional: bool = Field(
        default=True,
        description="Enable the directional (5-factor) scanner.",
    )
    enable_premium_selling: bool = Field(
        default=True,
        description="Enable the credit-spread / premium-selling scanner.",
    )
    enable_gamma_scalp: bool = Field(
        default=True,
        description="Enable the gamma-scalp scanner (final 2 hours).",
    )
    directional_scan_interval: int = Field(
        default=60,
        ge=1,
        description="Directional scanner refresh interval in seconds.",
    )
    premium_scan_interval: int = Field(
        default=300,
        ge=1,
        description="Premium scanner refresh interval in seconds.",
    )
    gamma_scan_interval: int = Field(
        default=30,
        ge=1,
        description="Gamma-scalp scanner refresh interval in seconds.",
    )

    # -----------------------------------------------------------------------
    # Direction Score
    # -----------------------------------------------------------------------
    entry_threshold: float = Field(
        default=DIRECTION_THRESHOLDS.bullish,
        ge=0,
        le=100,
        description="Minimum absolute direction score to trigger a trade.",
    )
    strong_threshold: float = Field(
        default=DIRECTION_THRESHOLDS.strong_bullish,
        ge=0,
        le=100,
        description="Absolute score for a high-conviction signal.",
    )
    min_confluence_factors: int = Field(
        default=DIRECTION_THRESHOLDS.min_confluence_factors,
        ge=1,
        le=5,
        description="Minimum factors agreeing in direction to validate signal.",
    )
    max_opposing_factor: float = Field(
        default=DIRECTION_THRESHOLDS.max_opposing_factor_score,
        ge=0,
        le=100,
        description="Maximum single-factor opposing score before invalidation.",
    )

    # -----------------------------------------------------------------------
    # Factor Weights (must sum to 1.0)
    # -----------------------------------------------------------------------
    weight_market_internals: float = Field(
        default=DEFAULT_FACTOR_WEIGHTS.market_internals,
        ge=0,
        le=1,
        description="Weight for the market-internals factor.",
    )
    weight_options_flow: float = Field(
        default=DEFAULT_FACTOR_WEIGHTS.options_flow,
        ge=0,
        le=1,
        description="Weight for the options-flow factor.",
    )
    weight_price_action: float = Field(
        default=DEFAULT_FACTOR_WEIGHTS.price_action,
        ge=0,
        le=1,
        description="Weight for the price-action factor.",
    )
    weight_gex_structure: float = Field(
        default=DEFAULT_FACTOR_WEIGHTS.gex_structure,
        ge=0,
        le=1,
        description="Weight for the GEX-structure factor.",
    )
    weight_cross_asset: float = Field(
        default=DEFAULT_FACTOR_WEIGHTS.cross_asset,
        ge=0,
        le=1,
        description="Weight for the cross-asset factor.",
    )

    # -----------------------------------------------------------------------
    # Strike Selection
    # -----------------------------------------------------------------------
    moderate_delta_min: float = Field(
        default=STRIKE_SELECTION.delta_target_moderate.lower,
        ge=0,
        le=1,
        description="Lower delta bound for moderate-conviction strikes.",
    )
    moderate_delta_max: float = Field(
        default=STRIKE_SELECTION.delta_target_moderate.upper,
        ge=0,
        le=1,
        description="Upper delta bound for moderate-conviction strikes.",
    )
    strong_delta_min: float = Field(
        default=STRIKE_SELECTION.delta_target_strong.lower,
        ge=0,
        le=1,
        description="Lower delta bound for strong-conviction strikes.",
    )
    strong_delta_max: float = Field(
        default=STRIKE_SELECTION.delta_target_strong.upper,
        ge=0,
        le=1,
        description="Upper delta bound for strong-conviction strikes.",
    )
    min_strike_oi: int = Field(
        default=STRIKE_SELECTION.min_open_interest,
        ge=0,
        description="Minimum open interest for a strike to be considered.",
    )
    min_strike_volume: int = Field(
        default=STRIKE_SELECTION.min_volume,
        ge=0,
        description="Minimum volume for a strike to be considered.",
    )
    max_spread_ratio: float = Field(
        default=2.0,
        gt=0,
        description="Maximum bid-ask spread width ratio.",
    )

    # -----------------------------------------------------------------------
    # Exit Management
    # -----------------------------------------------------------------------
    initial_stop_pct: float = Field(
        default=EXIT_MANAGEMENT.default_stop_loss_pct,
        ge=0,
        le=1,
        description="Initial stop loss as fraction of premium.",
    )
    time_based_stop_pct: float = Field(
        default=EXIT_MANAGEMENT.time_stop_loss_pct,
        ge=0,
        le=1,
        description="Time-based stop loss as fraction of premium.",
    )
    break_even_trigger: float = Field(
        default=0.50,
        ge=0,
        le=1,
        description="Profit fraction that triggers break-even stop.",
    )
    half_off_trigger: float = Field(
        default=1.00,
        ge=0,
        description="Profit fraction that triggers half-position exit.",
    )
    absolute_exit_time: str = Field(
        default="15:45",
        description="Hard deadline to close all positions (HH:MM ET).",
    )

    # -----------------------------------------------------------------------
    # Premium Selling
    # -----------------------------------------------------------------------
    premium_vix1d_min: float = Field(
        default=PREMIUM_SELLING.vix1d_min,
        ge=0,
        description="Minimum VIX1D level for premium selling eligibility.",
    )
    premium_vix1d_max: float = Field(
        default=PREMIUM_SELLING.vix1d_max,
        ge=0,
        description="Maximum VIX1D level for premium selling eligibility.",
    )
    premium_min_credit: float = Field(
        default=PREMIUM_SELLING.min_credit,
        ge=0,
        description="Minimum credit to receive per spread (USD).",
    )
    premium_spread_width: int = Field(
        default=5,
        ge=1,
        description="Default credit-spread width in strike points.",
    )
    premium_target_credit_pct: float = Field(
        default=PREMIUM_SELLING.target_credit_pct,
        ge=0,
        le=1,
        description="Target credit as fraction of spread width.",
    )
    premium_min_prob_otm: float = Field(
        default=PREMIUM_SELLING.prob_otm_target,
        ge=0,
        le=1,
        description="Minimum probability of expiring OTM.",
    )

    # -----------------------------------------------------------------------
    # GEX Engine
    # -----------------------------------------------------------------------
    gex_dealer_model: str = Field(
        default="hybrid",
        description="Dealer gamma model: simple, flow, or hybrid.",
    )
    gex_oi_weight: float = Field(
        default=0.60,
        ge=0,
        le=1,
        description="Weight of OI-based gamma in hybrid model.",
    )
    gex_flow_weight: float = Field(
        default=0.40,
        ge=0,
        le=1,
        description="Weight of flow-based gamma in hybrid model.",
    )
    gex_shift_alert_threshold: float = Field(
        default=GEX_SCANNER.shift_alert_threshold_pct,
        ge=0,
        le=1,
        description="GEX shift percentage that triggers an alert.",
    )
    gex_collapse_threshold: float = Field(
        default=GEX_SCANNER.collapse_threshold_pct,
        ge=0,
        le=1,
        description="GEX collapse percentage that triggers an alert.",
    )
    charm_threshold_es_contracts: int = Field(
        default=GEX_SCANNER.charm_exposure_threshold_contracts,
        ge=0,
        description="Charm-flow threshold in ES-contract equivalents.",
    )

    # -----------------------------------------------------------------------
    # Calibration / Self-Learning
    # -----------------------------------------------------------------------
    enable_auto_calibration: bool = Field(
        default=True,
        description="Enable adaptive self-learning calibration.",
    )
    calibration_ema_weight: float = Field(
        default=SELF_LEARNING.ema_weight,
        ge=0,
        le=1,
        description="EMA weight for factor-weight adjustment.",
    )
    max_factor_weight: float = Field(
        default=SELF_LEARNING.max_factor_weight,
        ge=0,
        le=1,
        description="Upper bound for any single factor weight.",
    )
    min_factor_weight: float = Field(
        default=SELF_LEARNING.min_factor_weight,
        ge=0,
        le=1,
        description="Lower bound for any single factor weight.",
    )
    daily_threshold_adjustment: float = Field(
        default=SELF_LEARNING.calibration_threshold_adjustment,
        ge=0,
        description="Maximum threshold adjustment per calibration cycle (points).",
    )
    target_adjustment_rate: float = Field(
        default=SELF_LEARNING.target_adjustment_rate,
        ge=0,
        le=1,
        description="Daily target adjustment rate (fraction).",
    )
    regime_detection_window: int = Field(
        default=SELF_LEARNING.regime_detection_window_days,
        ge=1,
        description="Rolling window (trading days) for regime detection.",
    )

    # -----------------------------------------------------------------------
    # Logging
    # -----------------------------------------------------------------------
    log_dir: str = Field(
        default="logs/scanify",
        description="Directory for SCANIFY log files.",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL.",
    )
    trade_log_file: str = Field(
        default="trades.json",
        description="Filename for the JSON trade log.",
    )
    enable_trade_logging: bool = Field(
        default=True,
        description="Enable per-trade JSON logging.",
    )

    # -----------------------------------------------------------------------
    # Database
    # -----------------------------------------------------------------------
    db_path: str = Field(
        default="data/scanify.db",
        description="Path to the SQLite database.",
    )
    enable_gex_snapshots: bool = Field(
        default=True,
        description="Persist periodic GEX snapshots to database.",
    )
    gex_snapshot_interval: int = Field(
        default=60,
        ge=1,
        description="Seconds between GEX snapshots.",
    )

    # -----------------------------------------------------------------------
    # Notifications
    # -----------------------------------------------------------------------
    enable_alerts: bool = Field(
        default=True,
        description="Enable alert system (webhooks + sound).",
    )
    alert_webhook_urls: list[str] = Field(
        default_factory=list,
        description="Webhook URLs for alert delivery.",
    )
    enable_sound_alerts: bool = Field(
        default=True,
        description="Play audible alerts on signal events.",
    )

    # ------------------------------------------------------------------
    # Pydantic model configuration
    # ------------------------------------------------------------------

    model_config = {
        "validate_assignment": True,
        "extra": "ignore",
        "str_strip_whitespace": True,
    }

    # ==================================================================
    # Field-level validators
    # ==================================================================

    @field_validator("data_provider")
    @classmethod
    def _validate_data_provider(cls, v: str) -> str:
        v_lower = v.lower()
        if v_lower not in _ALLOWED_DATA_PROVIDERS:
            raise ValueError(
                f"data_provider must be one of {sorted(_ALLOWED_DATA_PROVIDERS)}, "
                f"got '{v}'"
            )
        return v_lower

    @field_validator("gex_dealer_model")
    @classmethod
    def _validate_gex_dealer_model(cls, v: str) -> str:
        v_lower = v.lower()
        if v_lower not in _ALLOWED_GEX_DEALER_MODELS:
            raise ValueError(
                f"gex_dealer_model must be one of "
                f"{sorted(_ALLOWED_GEX_DEALER_MODELS)}, got '{v}'"
            )
        return v_lower

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        v_upper = v.upper()
        if v_upper not in _ALLOWED_LOG_LEVELS:
            raise ValueError(
                f"log_level must be one of {sorted(_ALLOWED_LOG_LEVELS)}, "
                f"got '{v}'"
            )
        return v_upper

    @field_validator("absolute_exit_time")
    @classmethod
    def _validate_time_format(cls, v: str) -> str:
        if not _TIME_RE.match(v):
            raise ValueError(
                f"absolute_exit_time must be HH:MM (24-hour), got '{v}'"
            )
        return v

    # ==================================================================
    # Cross-field (model-level) validators
    # ==================================================================

    @model_validator(mode="after")
    def _validate_cross_fields(self) -> "ScanifyConfig":
        errors: list[str] = []

        # Factor weights must sum to 1.0
        weight_sum = (
            self.weight_market_internals
            + self.weight_options_flow
            + self.weight_price_action
            + self.weight_gex_structure
            + self.weight_cross_asset
        )
        if abs(weight_sum - 1.0) > 1e-6:
            raise ValueError(
                f"Factor weights must sum to 1.0, got {weight_sum:.6f}. "
                f"Weights: market_internals={self.weight_market_internals}, "
                f"options_flow={self.weight_options_flow}, "
                f"price_action={self.weight_price_action}, "
                f"gex_structure={self.weight_gex_structure}, "
                f"cross_asset={self.weight_cross_asset}"
            )

        # GEX weights must sum to 1.0
        gex_weight_sum = self.gex_oi_weight + self.gex_flow_weight
        if abs(gex_weight_sum - 1.0) > 1e-6:
            raise ValueError(
                f"GEX OI weight ({self.gex_oi_weight}) + flow weight "
                f"({self.gex_flow_weight}) must sum to 1.0, got {gex_weight_sum:.6f}"
            )

        # Delta range ordering
        if self.moderate_delta_min >= self.moderate_delta_max:
            raise ValueError(
                f"moderate_delta_min ({self.moderate_delta_min}) must be less than "
                f"moderate_delta_max ({self.moderate_delta_max})"
            )
        if self.strong_delta_min >= self.strong_delta_max:
            raise ValueError(
                f"strong_delta_min ({self.strong_delta_min}) must be less than "
                f"strong_delta_max ({self.strong_delta_max})"
            )

        # Entry threshold must be less than strong threshold
        if self.entry_threshold >= self.strong_threshold:
            raise ValueError(
                f"entry_threshold ({self.entry_threshold}) must be less than "
                f"strong_threshold ({self.strong_threshold})"
            )

        # Premium VIX1D range ordering
        if self.premium_vix1d_min >= self.premium_vix1d_max:
            raise ValueError(
                f"premium_vix1d_min ({self.premium_vix1d_min}) must be less than "
                f"premium_vix1d_max ({self.premium_vix1d_max})"
            )

        # Min factor weight must be less than max factor weight
        if self.min_factor_weight >= self.max_factor_weight:
            raise ValueError(
                f"min_factor_weight ({self.min_factor_weight}) must be less than "
                f"max_factor_weight ({self.max_factor_weight})"
            )

        return self

    # ==================================================================
    # Convenience helpers
    # ==================================================================

    def factor_weights_dict(self) -> Dict[str, float]:
        """Return factor weights as a dictionary keyed by factor name."""
        return {
            "market_internals": self.weight_market_internals,
            "options_flow": self.weight_options_flow,
            "price_action": self.weight_price_action,
            "gex_structure": self.weight_gex_structure,
            "cross_asset": self.weight_cross_asset,
        }

    def is_live_trading(self) -> bool:
        """Return ``True`` when configured for live (non-paper) execution."""
        return not self.paper_trade


# =============================================================================
# load_config
# =============================================================================


def load_config(
    config_path: str = "config.yaml",
    section: str = "scanify",
) -> ScanifyConfig:
    """Load SCANIFY configuration from a YAML file.

    Reads the YAML file at *config_path*, extracts the *section* key, and
    constructs a :class:`ScanifyConfig`.  Any keys missing from the YAML
    section are filled with the field defaults.

    Parameters
    ----------
    config_path:
        Path to the YAML configuration file.
    section:
        Top-level key in the YAML file that contains SCANIFY settings.

    Returns
    -------
    ScanifyConfig
        A fully validated configuration object.

    Raises
    ------
    FileNotFoundError
        If *config_path* does not exist.
    yaml.YAMLError
        If the YAML file is malformed.
    pydantic.ValidationError
        If the parsed values violate model constraints.
    """
    resolved_path = Path(config_path).resolve()

    if not resolved_path.is_file():
        logger.warning(
            "Configuration file '%s' not found; using all defaults.", resolved_path
        )
        return ScanifyConfig()

    logger.info("Loading configuration from '%s' (section='%s')", resolved_path, section)

    with open(resolved_path, "r", encoding="utf-8") as fh:
        raw: dict = yaml.safe_load(fh) or {}

    section_data: dict = raw.get(section, {})

    if not section_data:
        logger.warning(
            "Section '%s' not found or empty in '%s'; using all defaults.",
            section,
            resolved_path,
        )
        return ScanifyConfig()

    # Flatten nested dicts one level (e.g. scanify.weights.market_internals)
    flat: Dict[str, Any] = {}
    for key, value in section_data.items():
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                flat[f"{key}_{sub_key}"] = sub_value
        else:
            flat[key] = value

    config = ScanifyConfig(**flat)
    logger.info("Configuration loaded and validated successfully.")
    return config


# =============================================================================
# save_config
# =============================================================================


def save_config(
    config: ScanifyConfig,
    config_path: str = "config_scanify.yaml",
) -> None:
    """Save the current configuration to a YAML file.

    The configuration is serialised as a flat dictionary under a
    ``scanify`` top-level key.

    Parameters
    ----------
    config:
        The configuration object to persist.
    config_path:
        Destination file path.
    """
    resolved_path = Path(config_path).resolve()
    resolved_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {"scanify": config.model_dump(mode="json")}

    with open(resolved_path, "w", encoding="utf-8") as fh:
        yaml.dump(
            payload,
            fh,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )

    logger.info("Configuration saved to '%s'.", resolved_path)


# =============================================================================
# validate_config
# =============================================================================


def validate_config(config: ScanifyConfig) -> List[str]:
    """Run comprehensive validation and return a list of warnings.

    Unlike the Pydantic validators (which raise on hard errors), this
    function performs softer, advisory-level checks and returns human-
    readable warning strings.

    Parameters
    ----------
    config:
        The configuration to validate.

    Returns
    -------
    list[str]
        A list of warning/info messages.  An empty list means the
        configuration is clean.
    """
    warnings: List[str] = []

    # --- Data provider warnings ---
    if config.data_provider == "mock":
        warnings.append(
            "[INFO] data_provider is 'mock'. Switch to 'polygon', 'alpaca', or "
            "'cboe' for live market data."
        )

    if config.data_provider != "mock" and not config.api_key:
        warnings.append(
            f"[WARN] data_provider is '{config.data_provider}' but api_key is empty. "
            "Live data feed will fail without a valid API key."
        )

    # --- Trading mode warnings ---
    if not config.paper_trade:
        warnings.append(
            "[WARN] paper_trade is False. LIVE TRADING IS ENABLED. "
            "Ensure all risk parameters have been reviewed."
        )

    if config.risk_budget_daily < 1_000:
        warnings.append(
            f"[WARN] risk_budget_daily ({config.risk_budget_daily:.2f}) is unusually "
            "low. Consider increasing for meaningful position sizes."
        )

    if config.risk_budget_daily > 100_000:
        warnings.append(
            f"[WARN] risk_budget_daily ({config.risk_budget_daily:.2f}) is high. "
            "Verify this is intentional."
        )

    # --- Factor weight balance ---
    weights = config.factor_weights_dict()
    max_w = max(weights.values())
    min_w = min(weights.values())
    if max_w > 0.40:
        dominant = max(weights, key=weights.get)  # type: ignore[arg-type]
        warnings.append(
            f"[WARN] Factor '{dominant}' has weight {max_w:.2f} (> 0.40). "
            "A dominant factor may reduce diversification."
        )
    if min_w < 0.05:
        weakest = min(weights, key=weights.get)  # type: ignore[arg-type]
        warnings.append(
            f"[WARN] Factor '{weakest}' has weight {min_w:.2f} (< 0.05). "
            "Consider whether this factor contributes meaningfully."
        )

    # --- Scanner intervals ---
    if config.directional_scan_interval < 10:
        warnings.append(
            f"[WARN] directional_scan_interval ({config.directional_scan_interval}s) "
            "is very short. This may cause excessive API calls."
        )
    if config.gamma_scan_interval < 10:
        warnings.append(
            f"[WARN] gamma_scan_interval ({config.gamma_scan_interval}s) is very short. "
            "This may cause excessive API calls."
        )

    # --- Exit time validation ---
    hour, minute = map(int, config.absolute_exit_time.split(":"))
    if hour < 15 or (hour == 15 and minute < 30):
        warnings.append(
            f"[WARN] absolute_exit_time ({config.absolute_exit_time}) is before 15:30. "
            "Positions may be closed prematurely, missing power-hour opportunities."
        )
    if hour >= 16:
        warnings.append(
            f"[WARN] absolute_exit_time ({config.absolute_exit_time}) is at or after "
            "16:00 (market close). SPX PM settlement occurs at 16:00; "
            "ensure positions are closed before settlement."
        )

    # --- Premium selling range ---
    premium_range = config.premium_vix1d_max - config.premium_vix1d_min
    if premium_range < 5.0:
        warnings.append(
            f"[WARN] Premium-selling VIX1D window is narrow "
            f"({config.premium_vix1d_min}-{config.premium_vix1d_max}, "
            f"range={premium_range:.1f}). Few opportunities may qualify."
        )

    # --- GEX engine ---
    if config.gex_dealer_model == "simple":
        warnings.append(
            "[INFO] gex_dealer_model is 'simple'. The hybrid model provides more "
            "accurate gamma profiles at the cost of additional computation."
        )

    # --- Calibration ---
    if not config.enable_auto_calibration:
        warnings.append(
            "[INFO] Auto-calibration is disabled. Factor weights and thresholds "
            "will remain static."
        )
    if config.calibration_ema_weight < 0.80:
        warnings.append(
            f"[WARN] calibration_ema_weight ({config.calibration_ema_weight}) is low. "
            "The system will adapt very quickly, which may cause instability."
        )

    # --- Logging ---
    log_dir = Path(config.log_dir)
    if not log_dir.is_absolute() and not log_dir.exists():
        warnings.append(
            f"[INFO] log_dir '{config.log_dir}' does not exist yet. "
            "It will be created at runtime."
        )

    # --- Database ---
    db_dir = Path(config.db_path).parent
    if not db_dir.is_absolute() and not db_dir.exists():
        warnings.append(
            f"[INFO] Database directory '{db_dir}' does not exist yet. "
            "It will be created at runtime."
        )

    # --- Concurrent position vs daily trades sanity ---
    if config.max_concurrent_positions > config.max_daily_trades:
        warnings.append(
            f"[WARN] max_concurrent_positions ({config.max_concurrent_positions}) "
            f"exceeds max_daily_trades ({config.max_daily_trades}). "
            "This is logically inconsistent."
        )

    return warnings


# =============================================================================
# merge_configs
# =============================================================================


def merge_configs(
    base: ScanifyConfig,
    override: dict,
) -> ScanifyConfig:
    """Merge an override dictionary into a base configuration.

    Creates a new :class:`ScanifyConfig` by copying all fields from *base*
    and applying any matching keys from *override*.  Unknown keys in
    *override* are silently ignored (consistent with ``extra="ignore"``).

    Parameters
    ----------
    base:
        The starting configuration.
    override:
        Dictionary of field names to replacement values.

    Returns
    -------
    ScanifyConfig
        A new, fully-validated configuration with overrides applied.
    """
    base_data = base.model_dump()
    base_data.update(override)
    merged = ScanifyConfig(**base_data)
    logger.debug("Merged %d override keys into configuration.", len(override))
    return merged


# =============================================================================
# get_default_config
# =============================================================================


def get_default_config() -> ScanifyConfig:
    """Return a default configuration with all factory defaults.

    This is equivalent to ``ScanifyConfig()`` but reads more clearly at
    call sites and serves as the canonical entry point for downstream code
    that needs a known-good starting configuration.

    Returns
    -------
    ScanifyConfig
        A default-initialised configuration.
    """
    return ScanifyConfig()


# =============================================================================
# ConfigWatcher
# =============================================================================


class ConfigWatcher:
    """Watch a YAML configuration file for changes and reload on modification.

    The watcher runs as an ``asyncio.Task`` that polls the file's
    ``st_mtime`` at a configurable interval.  When a change is detected
    the file is re-loaded and the user-supplied callback is invoked with
    the new :class:`ScanifyConfig`.

    Usage
    -----
    ::

        watcher = ConfigWatcher()
        await watcher.start_watching("config.yaml", on_config_changed)
        ...
        await watcher.stop_watching()

    The callback receives a single positional argument: the new
    ``ScanifyConfig``.  If the reload fails (bad YAML, validation error),
    the callback is **not** invoked and a warning is logged.
    """

    def __init__(self, poll_interval: float = 5.0, section: str = "scanify") -> None:
        """Initialise the watcher.

        Parameters
        ----------
        poll_interval:
            Seconds between file-stat polls.
        section:
            YAML section to extract (forwarded to :func:`load_config`).
        """
        self._poll_interval = poll_interval
        self._section = section
        self._task: Optional[asyncio.Task] = None  # type: ignore[type-arg]
        self._stop_event: Optional[asyncio.Event] = None
        self._last_mtime: float = 0.0
        self._config_path: str = ""
        self._callback: Optional[Callable[[ScanifyConfig], Any]] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start_watching(
        self,
        config_path: str,
        callback: Callable[[ScanifyConfig], Any],
    ) -> None:
        """Begin polling *config_path* for changes.

        Parameters
        ----------
        config_path:
            Path to the YAML configuration file to watch.
        callback:
            Callable invoked with the new ``ScanifyConfig`` whenever
            the file changes.  May be a coroutine function.
        """
        if self._task is not None and not self._task.done():
            logger.warning("ConfigWatcher is already running; call stop_watching first.")
            return

        resolved = Path(config_path).resolve()
        if not resolved.is_file():
            raise FileNotFoundError(
                f"Cannot watch non-existent config file: {resolved}"
            )

        self._config_path = str(resolved)
        self._callback = callback
        self._last_mtime = os.path.getmtime(self._config_path)
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._poll_loop())

        logger.info(
            "ConfigWatcher started: polling '%s' every %.1fs.",
            self._config_path,
            self._poll_interval,
        )

    async def stop_watching(self) -> None:
        """Stop the polling loop and clean up."""
        if self._stop_event is not None:
            self._stop_event.set()

        if self._task is not None and not self._task.done():
            try:
                await asyncio.wait_for(self._task, timeout=self._poll_interval + 2.0)
            except asyncio.TimeoutError:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass

        self._task = None
        self._stop_event = None
        logger.info("ConfigWatcher stopped.")

    @property
    def is_watching(self) -> bool:
        """Return ``True`` if the watcher is currently active."""
        return self._task is not None and not self._task.done()

    # ------------------------------------------------------------------
    # Internal polling loop
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        """Background coroutine that checks for file changes."""
        assert self._stop_event is not None
        assert self._callback is not None

        while not self._stop_event.is_set():
            try:
                current_mtime = os.path.getmtime(self._config_path)
            except OSError as exc:
                logger.warning(
                    "ConfigWatcher: unable to stat '%s': %s", self._config_path, exc
                )
                await self._sleep_or_stop()
                continue

            if current_mtime != self._last_mtime:
                logger.info(
                    "ConfigWatcher: change detected in '%s', reloading...",
                    self._config_path,
                )
                self._last_mtime = current_mtime
                try:
                    new_config = load_config(self._config_path, section=self._section)
                except Exception as exc:
                    logger.error(
                        "ConfigWatcher: failed to reload configuration: %s", exc
                    )
                    await self._sleep_or_stop()
                    continue

                try:
                    result = self._callback(new_config)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as exc:
                    logger.error(
                        "ConfigWatcher: callback raised an exception: %s", exc
                    )

            await self._sleep_or_stop()

    async def _sleep_or_stop(self) -> None:
        """Sleep for the poll interval or return early if stop is requested."""
        assert self._stop_event is not None
        try:
            await asyncio.wait_for(
                self._stop_event.wait(), timeout=self._poll_interval
            )
        except asyncio.TimeoutError:
            pass  # Normal: stop_event was not set during the interval


# =============================================================================
# Module exports
# =============================================================================

__all__: List[str] = [
    "ScanifyConfig",
    "load_config",
    "save_config",
    "validate_config",
    "merge_configs",
    "get_default_config",
    "ConfigWatcher",
]
