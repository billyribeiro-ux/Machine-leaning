"""
SCANIFY Configuration — 0DTE SPX OTM Options Scanner + GEX Scanner

All configurable parameters for the SCANIFY system with validated defaults
derived from empirical data and academic research.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class SessionType(Enum):
    """Market session classification."""
    TRENDING = "trending"
    RANGE = "range"
    VOLATILE = "volatile"
    SQUEEZE = "squeeze"
    EVENT = "event"


class TimeZone(Enum):
    """Intraday time zones with distinct market characteristics."""
    PRE_MARKET = "pre_market"              # 7:00 - 9:30
    OPENING_AUCTION = "opening_auction"    # 9:30 - 9:45
    MORNING_SESSION = "morning_session"    # 9:45 - 11:30
    MIDDAY_LULL = "midday_lull"            # 11:30 - 13:30
    AFTERNOON_ACCEL = "afternoon_accel"    # 13:30 - 15:00
    POWER_HOUR = "power_hour"             # 15:00 - 15:45
    SETTLEMENT = "settlement"             # 15:45 - 16:00


class ScanType(Enum):
    """Scanner types available in the system."""
    DIRECTIONAL = "directional"
    PREMIUM_SELL = "premium_sell"
    GAMMA_SCALP = "gamma_scalp"


class SignalDirection(Enum):
    """Trade direction signals."""
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class ExitReason(Enum):
    """Reason for trade exit."""
    PROFIT_TARGET = "profit_target"
    STOP_LOSS = "stop_loss"
    TIME_STOP = "time_stop"
    SIGNAL_REVERSAL = "signal_reversal"
    GEX_FLIP = "gex_flip"
    VIX_SPIKE = "vix_spike"
    TRAILING_STOP = "trailing_stop"
    BREAK_EVEN = "break_even"
    MANUAL = "manual"
    SETTLEMENT_CLOSE = "settlement_close"


class GEXSignalType(Enum):
    """GEX-derived signal types."""
    GAMMA_FLIP_CROSSOVER = "gamma_flip_crossover"
    GAMMA_WALL_APPROACH = "gamma_wall_approach"
    TRANSITION_ZONE_BREAKOUT = "transition_zone_breakout"
    GEX_COLLAPSE = "gex_collapse"
    CHARM_DRIVEN_FLOW = "charm_driven_flow"
    VANNA_AMPLIFICATION = "vanna_amplification"


@dataclass
class SPXContractSpec:
    """Immutable SPX 0DTE contract specifications."""
    symbol: str = "SPXW"
    underlying: str = "SPX"
    settlement: str = "PM"  # P.M. settlement
    settlement_type: str = "cash"  # Cash-settled European
    multiplier: float = 100.0
    tick_size_under_3: float = 0.05
    tick_size_over_3: float = 0.10
    trading_hours_start: str = "09:30"
    trading_hours_end: str = "16:15"
    settlement_time: str = "16:00"
    strike_interval_atm: float = 5.0
    strike_interval_otm: float = 25.0


@dataclass
class DirectionalScanConfig:
    """Configuration for directional OTM scanner (Core Scan #1)."""
    # Factor weights (must sum to 1.0)
    weight_market_internals: float = 0.30
    weight_options_flow: float = 0.25
    weight_price_action: float = 0.20
    weight_gex_structure: float = 0.15
    weight_cross_asset: float = 0.10

    # Signal thresholds
    signal_threshold: float = 40.0
    strong_signal_threshold: float = 65.0
    min_factors_agreeing: int = 3
    max_opposing_factor_score: float = 30.0

    # Strike selection
    moderate_delta_min: float = 0.15
    moderate_delta_max: float = 0.25
    strong_delta_min: float = 0.25
    strong_delta_max: float = 0.40

    # Time-of-day delta adjustments
    delta_adjust_midday: float = 0.05
    delta_adjust_afternoon: float = 0.10

    # VIX1D adjustments
    vix1d_high_threshold: float = 25.0
    vix1d_low_threshold: float = 12.0
    vix1d_strike_adjust: float = 5.0  # points

    # Spread filters
    max_spread_under_5: float = 0.50
    max_spread_5_to_20: float = 1.00
    max_spread_over_20: float = 2.00

    # Liquidity filters
    min_open_interest: int = 500
    min_volume: int = 200

    # Entry timing
    max_slippage: float = 0.20
    fill_timeout_seconds: int = 60

    # Scan window
    scan_start: str = "09:45"
    scan_end: str = "15:00"
    scan_interval_seconds: int = 60


@dataclass
class PremiumSellConfig:
    """Configuration for premium selling scanner (Core Scan #2)."""
    # Entry conditions
    vix1d_min: float = 10.0
    vix1d_max: float = 22.0
    max_vwap_distance_sigma: float = 0.5
    min_iv_rv_ratio: float = 1.1
    tick_range_min: float = -500.0
    tick_range_max: float = 500.0

    # Strike selection
    spread_width: float = 5.0  # points
    min_credit: float = 0.50
    target_credit_pct: float = 0.30  # 30% of spread width
    min_prob_otm: float = 0.80

    # Exit management
    close_at_profit_pct: float = 0.50  # 50% of max profit
    close_late_profit_pct: float = 0.80  # 80% after 2:30 PM
    max_hold_time: str = "15:30"

    # Scan window
    scan_start: str = "10:00"
    scan_end: str = "14:00"
    scan_interval_seconds: int = 300


@dataclass
class GammaScalpConfig:
    """Configuration for gamma scalp / acceleration scanner (Core Scan #3)."""
    # Entry conditions
    min_direction_score: float = 50.0
    approach_distance_points: float = 3.0
    volume_spike_multiple: float = 2.0

    # Gamma squeeze detection
    squeeze_gamma_threshold: float = 0.05
    pin_duration_minutes: int = 30
    pin_range_points: float = 3.0

    # Exit management
    profit_target_pct_min: float = 0.50
    profit_target_pct_max: float = 1.00
    stop_loss_pct: float = 0.30
    absolute_exit_time: str = "15:50"

    # Scan window
    scan_start: str = "14:00"
    scan_end: str = "15:45"
    scan_interval_seconds: int = 30


@dataclass
class GEXConfig:
    """Configuration for Gamma Exposure engine."""
    # Computation
    update_interval_seconds: int = 60
    min_time_remaining_minutes: float = 1.0
    iv_extrapolation_threshold: float = 0.10  # options < $0.10

    # Dealer position model
    oi_weight: float = 0.60
    flow_weight: float = 0.40

    # Signal thresholds
    gamma_flip_confidence: float = 0.65
    wall_hold_rate: float = 0.62
    transition_zone_confirm_minutes: int = 2
    gex_collapse_threshold_pct: float = 0.30
    charm_flow_threshold_contracts: int = 5000
    vanna_vix_change_threshold_pct: float = 0.10
    gex_shift_alert_pct: float = 0.20


@dataclass
class ExitConfig:
    """Exit management configuration."""
    # Profit targets by time zone
    profit_target_morning: tuple = (1.00, 2.00)
    profit_target_midday: tuple = (0.75, 1.50)
    profit_target_afternoon: tuple = (0.50, 1.00)
    profit_target_power_hour: tuple = (0.30, 0.50)

    # Trailing stops by time zone
    trail_stop_morning: float = 0.50
    trail_stop_midday: float = 0.40
    trail_stop_afternoon: float = 0.30

    # Stop losses
    initial_stop_pct: float = 0.50
    time_based_stop_pct: float = 0.30
    time_based_stop_minutes: int = 30
    vix_spike_stop_pct: float = 0.25
    absolute_exit_time: str = "15:45"

    # Break-even management
    move_to_be_at_pct: float = 0.50
    take_partial_at_pct: float = 1.00
    partial_close_fraction: float = 0.50


@dataclass
class CalibrationConfig:
    """Self-learning calibration configuration."""
    # Daily calibration
    weight_ema_alpha: float = 0.05  # 0.95 * old + 0.05 * new
    max_single_factor_weight: float = 0.40
    min_single_factor_weight: float = 0.05
    threshold_adjust_step: float = 2.0
    target_adjust_rate: float = 0.05  # 5% per day

    # GEX calibration
    gex_accuracy_window_days: int = 20
    gex_high_accuracy_threshold: float = 0.70
    gex_low_accuracy_threshold: float = 0.55

    # Regime detection
    regime_lookback_days: int = 20
    regime_min_trades_new: int = 50
    regime_size_reduction: float = 0.50

    # Weekly/monthly
    weekly_backtest_weeks: int = 4
    monthly_backtest_months: int = 3
    min_significance_p: float = 0.05
    min_trades_for_ml_exit: int = 1000


@dataclass
class RiskConfig:
    """Risk management for SCANIFY."""
    max_risk_per_trade_pct: float = 0.02  # 2% of daily budget
    max_concurrent_positions: int = 5
    max_daily_loss_pct: float = 0.05  # 5% of capital
    no_naked_shorts: bool = True
    event_buffer_minutes: int = 15
    fomc_suspend_start: str = "13:30"
    fomc_suspend_end: str = "15:15"


@dataclass
class CredentialsConfig:
    """API key management configuration."""
    credentials_file: str = "~/.scanify/credentials.json"
    master_key_env_var: str = "SCANIFY_MASTER_KEY"
    admin_token_env_var: str = "SCANIFY_ADMIN_TOKEN"
    api_host: str = "0.0.0.0"
    api_port: int = 8000


@dataclass
class ScanifyConfig:
    """Master SCANIFY configuration."""
    # Sub-configs
    contract: SPXContractSpec = field(default_factory=SPXContractSpec)
    directional: DirectionalScanConfig = field(default_factory=DirectionalScanConfig)
    premium_sell: PremiumSellConfig = field(default_factory=PremiumSellConfig)
    gamma_scalp: GammaScalpConfig = field(default_factory=GammaScalpConfig)
    gex: GEXConfig = field(default_factory=GEXConfig)
    exit: ExitConfig = field(default_factory=ExitConfig)
    calibration: CalibrationConfig = field(default_factory=CalibrationConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    credentials: CredentialsConfig = field(default_factory=CredentialsConfig)

    # Expected move weights
    em_weight_vix1d: float = 0.40
    em_weight_straddle: float = 0.40
    em_weight_rv_adjusted: float = 0.20

    # Session classification thresholds
    gap_micro_sigma: float = 0.3
    gap_small_sigma: float = 0.7
    gap_medium_sigma: float = 1.5
    gap_large_sigma: float = 2.5

    # Data persistence
    trade_log_path: str = "data/scanify/trades.jsonl"
    calibration_path: str = "data/scanify/calibration.json"
    gex_snapshot_path: str = "data/scanify/gex_snapshots/"

    def to_dict(self) -> Dict:
        """Serialize config to dictionary."""
        import dataclasses
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> "ScanifyConfig":
        """Create config from dictionary with nested sub-configs."""
        config = cls()
        for key, value in d.items():
            if hasattr(config, key):
                attr = getattr(config, key)
                if hasattr(attr, '__dataclass_fields__') and isinstance(value, dict):
                    for sub_key, sub_value in value.items():
                        if hasattr(attr, sub_key):
                            setattr(attr, sub_key, sub_value)
                else:
                    setattr(config, key, value)
        return config
