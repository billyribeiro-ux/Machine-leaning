"""
SCANIFY SPX 0DTE Options Day Trading Scanner + GEX Scanner - Constants Module

Immutable constants, contract specifications, time zone definitions, thresholds,
and configuration defaults for the SCANIFY 0DTE trading system.

All values in this module are treated as read-only. Runtime-tunable parameters
belong in the configuration layer; only fixed market structure, regulatory, and
mathematically-derived constants live here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import time, timedelta
from enum import Enum, IntEnum, unique
from typing import Dict, FrozenSet, List, NamedTuple, Tuple


# ---------------------------------------------------------------------------
# 1. SPX 0DTE CONTRACT SPECIFICATIONS
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ContractSpec:
    """Immutable SPX Weekly (SPXW) 0DTE contract specification."""

    symbol: str = "SPXW"
    underlying: str = "S&P 500 Index"
    underlying_ticker: str = "SPX"

    # Settlement
    settlement_type: str = "PM"  # P.M. settlement at 4:00 PM ET closing price
    exercise_style: str = "European"  # Cash-settled, no early exercise
    cash_settled: bool = True

    # Expiration cadence
    daily_expiration: bool = True  # Mon-Fri weeklys
    expiration_days: Tuple[str, ...] = (
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
    )

    # Trading hours (Eastern Time)
    market_open: time = time(9, 30)
    market_close: time = time(16, 15)  # Options can trade until 4:15 PM ET
    settlement_time: time = time(16, 0)  # SOQ at 4:00 PM ET

    # Tick sizes
    tick_size_below_3: float = 0.05  # Options priced < $3.00
    tick_size_at_or_above_3: float = 0.10  # Options priced >= $3.00
    tick_price_boundary: float = 3.00

    # Contract multiplier
    multiplier: float = 100.0  # $100 per index point

    # Strike intervals
    strike_interval_near_atm: int = 5  # $5 strikes near ATM
    strike_interval_far_otm: int = 25  # $25 strikes further OTM
    far_otm_threshold_points: int = 100  # Distance from ATM where $25 interval begins


SPX_CONTRACT = ContractSpec()


# ---------------------------------------------------------------------------
# 2. INTRADAY TIME ZONES
# ---------------------------------------------------------------------------

@unique
class IntradayZone(IntEnum):
    """
    Enumeration of intraday time zones for 0DTE trading.

    The numeric values encode ordering and can be used for comparisons
    (earlier zones have smaller values).
    """

    PRE_MARKET = 0
    OPENING_AUCTION = 1
    MORNING_SESSION = 2
    MIDDAY_LULL = 3
    AFTERNOON_ACCEL = 4
    POWER_HOUR = 5
    SETTLEMENT_WINDOW = 6


class TimeZoneBoundary(NamedTuple):
    """Start and end times for an intraday time zone."""

    zone: IntradayZone
    start: time
    end: time
    description: str


INTRADAY_ZONE_SCHEDULE: Tuple[TimeZoneBoundary, ...] = (
    TimeZoneBoundary(
        zone=IntradayZone.PRE_MARKET,
        start=time(7, 0),
        end=time(9, 30),
        description="Pre-market: futures-driven positioning, no SPX options trading",
    ),
    TimeZoneBoundary(
        zone=IntradayZone.OPENING_AUCTION,
        start=time(9, 30),
        end=time(9, 45),
        description="Opening auction: high volatility, wide spreads, price discovery",
    ),
    TimeZoneBoundary(
        zone=IntradayZone.MORNING_SESSION,
        start=time(9, 45),
        end=time(11, 30),
        description="Morning session: highest liquidity, trend establishment",
    ),
    TimeZoneBoundary(
        zone=IntradayZone.MIDDAY_LULL,
        start=time(11, 30),
        end=time(13, 30),
        description="Midday lull: reduced volume, mean-reversion dominant",
    ),
    TimeZoneBoundary(
        zone=IntradayZone.AFTERNOON_ACCEL,
        start=time(13, 30),
        end=time(15, 0),
        description="Afternoon acceleration: institutional flow resumes, gamma rising",
    ),
    TimeZoneBoundary(
        zone=IntradayZone.POWER_HOUR,
        start=time(15, 0),
        end=time(15, 45),
        description="Power hour: extreme gamma, delta hedging dominates tape",
    ),
    TimeZoneBoundary(
        zone=IntradayZone.SETTLEMENT_WINDOW,
        start=time(15, 45),
        end=time(16, 0),
        description="Settlement window: pin risk, final gamma collapse, exit all",
    ),
)

# Convenience lookup: zone -> boundary
ZONE_BOUNDARIES: Dict[IntradayZone, TimeZoneBoundary] = {
    tz.zone: tz for tz in INTRADAY_ZONE_SCHEDULE
}


# ---------------------------------------------------------------------------
# 3. GREEKS BEHAVIOR CONSTANTS
# ---------------------------------------------------------------------------

TRADING_MINUTES_PER_DAY: int = 390  # 9:30 AM - 4:00 PM = 390 minutes
TRADING_SECONDS_PER_DAY: int = TRADING_MINUTES_PER_DAY * 60
CALENDAR_DAYS_PER_YEAR: float = 365.25
TRADING_DAYS_PER_YEAR: float = 252.0


@dataclass(frozen=True)
class GammaRangeSnapshot:
    """
    ATM gamma magnitude (per 1-point move in SPX) at a specific time of day.

    Values represent the typical gamma for a near-ATM 0DTE option expressed
    as a fraction of the multiplier.  These are order-of-magnitude reference
    points, not exact figures -- actual gamma depends on IV and moneyness.
    """

    label: str
    reference_time: time
    atm_gamma_low: float
    atm_gamma_high: float


GAMMA_RANGES: Tuple[GammaRangeSnapshot, ...] = (
    GammaRangeSnapshot(
        label="open",
        reference_time=time(9, 30),
        atm_gamma_low=0.03,
        atm_gamma_high=0.08,
    ),
    GammaRangeSnapshot(
        label="2pm",
        reference_time=time(14, 0),
        atm_gamma_low=0.08,
        atm_gamma_high=0.20,
    ),
    GammaRangeSnapshot(
        label="3:30pm",
        reference_time=time(15, 30),
        atm_gamma_low=0.20,
        atm_gamma_high=0.50,
    ),
    GammaRangeSnapshot(
        label="3:55pm",
        reference_time=time(15, 55),
        atm_gamma_low=0.50,
        atm_gamma_high=1.50,
    ),
)


class ThetaDecayPoint(NamedTuple):
    """Non-linear theta decay percentage at a given intraday zone."""

    zone: IntradayZone
    cumulative_decay_pct: float  # Cumulative % of daily theta realized by zone end
    marginal_decay_pct: float  # Marginal % of daily theta realized within this zone


# Non-linear theta decay curve for 0DTE options.
# Decay accelerates sharply after 2:00 PM as T -> 0.
THETA_DECAY_CURVE: Tuple[ThetaDecayPoint, ...] = (
    ThetaDecayPoint(
        zone=IntradayZone.OPENING_AUCTION,
        cumulative_decay_pct=3.0,
        marginal_decay_pct=3.0,
    ),
    ThetaDecayPoint(
        zone=IntradayZone.MORNING_SESSION,
        cumulative_decay_pct=15.0,
        marginal_decay_pct=12.0,
    ),
    ThetaDecayPoint(
        zone=IntradayZone.MIDDAY_LULL,
        cumulative_decay_pct=35.0,
        marginal_decay_pct=20.0,
    ),
    ThetaDecayPoint(
        zone=IntradayZone.AFTERNOON_ACCEL,
        cumulative_decay_pct=60.0,
        marginal_decay_pct=25.0,
    ),
    ThetaDecayPoint(
        zone=IntradayZone.POWER_HOUR,
        cumulative_decay_pct=85.0,
        marginal_decay_pct=25.0,
    ),
    ThetaDecayPoint(
        zone=IntradayZone.SETTLEMENT_WINDOW,
        cumulative_decay_pct=100.0,
        marginal_decay_pct=15.0,
    ),
)


@dataclass(frozen=True)
class DeltaDecayConstants:
    """
    Constants governing delta behaviour as expiration approaches.

    For 0DTE options, delta becomes increasingly binary (approaching 0 or 1)
    as time-to-expiry shrinks.  These constants parameterise that transition.
    """

    # Speed at which ATM delta collapses/expands near expiry (dimensionless)
    atm_delta_steepening_rate: float = 2.5

    # Minutes before expiry at which delta behaviour becomes discontinuous
    discontinuity_threshold_minutes: int = 15

    # Minimum time-to-expiry (in years) used in Greeks calculations to
    # avoid division-by-zero; corresponds to ~1 minute
    min_tte_years: float = 1.0 / (TRADING_DAYS_PER_YEAR * TRADING_MINUTES_PER_DAY)

    # Delta at which an option is considered deep ITM for hedging purposes
    deep_itm_delta: float = 0.90

    # Delta at which an option is considered deep OTM (negligible gamma)
    deep_otm_delta: float = 0.05


DELTA_DECAY = DeltaDecayConstants()


# ---------------------------------------------------------------------------
# 4. VIX1D CONSTANTS
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VIX1DConstants:
    """Constants related to the CBOE 1-Day Volatility Index (VIX1D)."""

    # Risk premium: realized vol typically undershoots VIX1D by this fraction
    risk_premium_adjustment: float = 0.16

    # Intraday VIX1D pattern multipliers (relative to daily average).
    # Indexed by IntradayZone value.
    intraday_pattern: Dict[int, float] = field(default_factory=lambda: {
        IntradayZone.OPENING_AUCTION: 1.15,   # Elevated at open
        IntradayZone.MORNING_SESSION: 1.05,    # Slightly above average
        IntradayZone.MIDDAY_LULL: 0.90,        # Compressed midday
        IntradayZone.AFTERNOON_ACCEL: 1.00,    # Return to average
        IntradayZone.POWER_HOUR: 1.10,         # Rising into close
        IntradayZone.SETTLEMENT_WINDOW: 1.20,  # Spike near settlement
    })

    # VIX1D spike threshold: intraday increase percentage that qualifies
    # as a "spike" event warranting defensive posture
    spike_threshold_pct: float = 0.30  # 30% intraday increase


VIX1D = VIX1DConstants()


@unique
class VIX1DRegime(Enum):
    """VIX1D regime classification."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    EXTREME = "extreme"


class VIX1DRegimeThreshold(NamedTuple):
    """Inclusive lower and exclusive upper bounds for a VIX1D regime."""

    regime: VIX1DRegime
    lower: float  # Inclusive
    upper: float  # Exclusive (use math.inf for unbounded)


VIX1D_REGIME_THRESHOLDS: Tuple[VIX1DRegimeThreshold, ...] = (
    VIX1DRegimeThreshold(regime=VIX1DRegime.LOW, lower=0.0, upper=12.0),
    VIX1DRegimeThreshold(regime=VIX1DRegime.NORMAL, lower=12.0, upper=18.0),
    VIX1DRegimeThreshold(regime=VIX1DRegime.HIGH, lower=18.0, upper=25.0),
    VIX1DRegimeThreshold(regime=VIX1DRegime.EXTREME, lower=25.0, upper=math.inf),
)


# ---------------------------------------------------------------------------
# 5. DIRECTION SCORE THRESHOLDS
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DirectionScoreThresholds:
    """
    Thresholds for the composite direction score (range: -100 to +100).

    The direction score aggregates multiple factors to produce a single
    directional conviction reading.
    """

    # Signal thresholds (trigger a trade recommendation)
    bullish: float = 40.0
    bearish: float = -40.0

    # Strong signal thresholds (higher conviction, wider strikes allowed)
    strong_bullish: float = 65.0
    strong_bearish: float = -65.0

    # Minimum number of factors (out of 5) that must agree in direction
    min_confluence_factors: int = 3
    total_factors: int = 5

    # Maximum allowable points from a single factor opposing the signal.
    # If any one opposing factor exceeds this, the signal is invalidated.
    max_opposing_factor_score: float = 30.0

    # Score bounds
    score_min: float = -100.0
    score_max: float = 100.0


DIRECTION_THRESHOLDS = DirectionScoreThresholds()


# ---------------------------------------------------------------------------
# 6. FACTOR WEIGHTS (Defaults)
# ---------------------------------------------------------------------------

@unique
class DirectionFactor(Enum):
    """Factors that contribute to the composite direction score."""

    MARKET_INTERNALS = "market_internals"
    OPTIONS_FLOW = "options_flow"
    PRICE_ACTION = "price_action"
    GEX_STRUCTURE = "gex_structure"
    CROSS_ASSET = "cross_asset"


@dataclass(frozen=True)
class FactorWeightDefaults:
    """
    Default weights for each factor in the direction score computation.

    Weights are expressed as fractions (0.0-1.0) and must sum to 1.0.
    The self-learning module may adjust these at runtime within the
    bounds defined in SELF_LEARNING constants.
    """

    market_internals: float = 0.30
    options_flow: float = 0.25
    price_action: float = 0.20
    gex_structure: float = 0.15
    cross_asset: float = 0.10

    def as_dict(self) -> Dict[DirectionFactor, float]:
        """Return weights keyed by DirectionFactor enum."""
        return {
            DirectionFactor.MARKET_INTERNALS: self.market_internals,
            DirectionFactor.OPTIONS_FLOW: self.options_flow,
            DirectionFactor.PRICE_ACTION: self.price_action,
            DirectionFactor.GEX_STRUCTURE: self.gex_structure,
            DirectionFactor.CROSS_ASSET: self.cross_asset,
        }

    def validate(self) -> bool:
        """Check that weights sum to 1.0 (within floating-point tolerance)."""
        return abs(sum(self.as_dict().values()) - 1.0) < 1e-9


DEFAULT_FACTOR_WEIGHTS = FactorWeightDefaults()


# ---------------------------------------------------------------------------
# 7. STRIKE SELECTION CONSTANTS
# ---------------------------------------------------------------------------

class DeltaRange(NamedTuple):
    """Inclusive lower and upper delta bounds for strike selection."""

    lower: float
    upper: float


@dataclass(frozen=True)
class StrikeSelectionConstants:
    """Constants governing automatic strike selection."""

    # Delta targets by signal strength
    delta_target_moderate: DeltaRange = DeltaRange(lower=0.15, upper=0.25)
    delta_target_strong: DeltaRange = DeltaRange(lower=0.25, upper=0.40)

    # Time-of-day delta adjustments (additive shift to target delta).
    # Positive = move closer to ATM; negative = move further OTM.
    time_delta_adjustments: Dict[int, float] = field(default_factory=lambda: {
        IntradayZone.OPENING_AUCTION: -0.05,   # Wider OTM at open (uncertainty)
        IntradayZone.MORNING_SESSION: 0.00,     # Baseline
        IntradayZone.MIDDAY_LULL: -0.03,        # Slightly more OTM (low vol)
        IntradayZone.AFTERNOON_ACCEL: 0.03,     # Slightly closer ATM (gamma)
        IntradayZone.POWER_HOUR: 0.05,          # Closer ATM (gamma explosion)
        IntradayZone.SETTLEMENT_WINDOW: -0.10,  # Far OTM only (risk reduction)
    })

    # VIX1D-based delta adjustments (additive shift)
    vix1d_delta_adjustments: Dict[str, float] = field(default_factory=lambda: {
        VIX1DRegime.LOW.value: 0.05,       # Move closer ATM in low vol
        VIX1DRegime.NORMAL.value: 0.00,    # Baseline
        VIX1DRegime.HIGH.value: -0.05,     # Move further OTM in high vol
        VIX1DRegime.EXTREME.value: -0.10,  # Significantly further OTM
    })

    # Spread width limits (in strike points)
    min_spread_width: int = 5
    max_spread_width: int = 25
    default_spread_width: int = 10

    # Liquidity filters
    min_open_interest: int = 500
    min_volume: int = 200
    max_bid_ask_spread_pct: float = 0.15  # 15% of mid price


STRIKE_SELECTION = StrikeSelectionConstants()


# ---------------------------------------------------------------------------
# 8. EXIT MANAGEMENT CONSTANTS
# ---------------------------------------------------------------------------

class ProfitTargetByZone(NamedTuple):
    """Profit target as a fraction of initial premium, by intraday zone."""

    zone: IntradayZone
    target_pct: float  # e.g. 0.50 = 50% of premium received/paid


@dataclass(frozen=True)
class ExitManagementConstants:
    """Constants governing position exit logic."""

    # Profit targets by intraday zone (fraction of entry premium)
    profit_targets: Tuple[ProfitTargetByZone, ...] = (
        ProfitTargetByZone(zone=IntradayZone.OPENING_AUCTION, target_pct=1.00),
        ProfitTargetByZone(zone=IntradayZone.MORNING_SESSION, target_pct=0.75),
        ProfitTargetByZone(zone=IntradayZone.MIDDAY_LULL, target_pct=0.60),
        ProfitTargetByZone(zone=IntradayZone.AFTERNOON_ACCEL, target_pct=0.50),
        ProfitTargetByZone(zone=IntradayZone.POWER_HOUR, target_pct=0.40),
        ProfitTargetByZone(zone=IntradayZone.SETTLEMENT_WINDOW, target_pct=0.25),
    )

    # Stop loss: maximum acceptable loss as a fraction of premium paid/received
    default_stop_loss_pct: float = 0.50  # 50% of premium

    # Time-based stop: if position is down this much after this many minutes,
    # exit regardless of other conditions
    time_stop_loss_pct: float = 0.30  # 30% loss
    time_stop_minutes: int = 30  # After 30 minutes in the trade

    # Break-even management: once profit reaches this threshold, move stop
    # to break-even (entry price)
    breakeven_activation_pct: float = 0.30  # Activate at 30% profit
    breakeven_buffer_pct: float = 0.02  # Allow 2% slippage below entry

    # Trailing stop: activated after breakeven, trails by this fraction of
    # the maximum profit achieved
    trailing_stop_pct: float = 0.40  # Trail 40% below peak profit

    # Absolute time stop: close ALL positions by this time regardless
    absolute_time_stop: time = time(15, 45)  # 3:45 PM ET

    # Maximum holding period (minutes) -- safety net
    max_holding_minutes: int = 180


EXIT_MANAGEMENT = ExitManagementConstants()


# ---------------------------------------------------------------------------
# 9. PREMIUM SELLING CONSTANTS
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PremiumSellingConstants:
    """
    Constants for credit-spread / premium-selling strategies.

    Premium selling is favoured when implied volatility is rich relative
    to realized, the VIX1D is within a stable range, and breadth (TICK)
    is not extreme.
    """

    # VIX1D range in which premium selling is considered appropriate
    vix1d_min: float = 10.0
    vix1d_max: float = 22.0

    # NYSE TICK range for premium selling suitability
    tick_range_min: int = -500
    tick_range_max: int = 500

    # Minimum implied-vol to realized-vol ratio to justify selling premium
    iv_rv_ratio_min: float = 1.1

    # Minimum credit received per spread (in dollars)
    min_credit: float = 0.50

    # Target credit as a fraction of spread width (in dollar terms)
    target_credit_pct: float = 0.30  # 30% of spread width

    # Minimum probability of expiring out-of-the-money (from delta proxy)
    prob_otm_target: float = 0.80  # 80%

    # Maximum acceptable loss on a credit spread (as multiple of credit)
    max_loss_multiple: float = 3.0

    # Minimum days of VIX1D data required before enabling premium selling
    min_vix1d_lookback_days: int = 5


PREMIUM_SELLING = PremiumSellingConstants()


# ---------------------------------------------------------------------------
# 10. GEX SCANNER CONSTANTS
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GEXScannerConstants:
    """
    Constants for the Gamma Exposure (GEX) scanner.

    The GEX scanner monitors real-time changes in dealer gamma positioning
    to detect regime shifts, charm flow, and gamma-wall interactions.
    """

    # GEX shift alert: minimum percentage change in total GEX within the
    # observation window to trigger an alert
    shift_alert_threshold_pct: float = 0.20  # 20% change
    shift_alert_window_minutes: int = 5

    # Charm exposure threshold: net charm flow in ES-contract-equivalent
    # notional that triggers a charm-driven alert
    charm_exposure_threshold_contracts: int = 5_000

    # Gamma wall approach: distance in SPX points from the nearest major
    # gamma concentration level at which an approach alert fires
    gamma_wall_approach_distance: float = 3.0  # 3 SPX points

    # Transition zone: ratio of call gamma to put gamma that indicates
    # a flip from positive to negative gamma territory (or vice versa)
    transition_zone_call_put_ratio: float = 2.0  # 2x call/put gamma ratio

    # GEX collapse: percentage drop in aggregate GEX within the observation
    # window that signals a structural gamma event (e.g. options expiring)
    collapse_threshold_pct: float = 0.30  # 30% drop
    collapse_window_minutes: int = 15

    # GEX flip level tolerance: number of SPX points of hysteresis
    # around the zero-gamma level to prevent whipsaw flip signals
    flip_hysteresis_points: float = 2.0

    # Minimum aggregate GEX (in $ gamma-per-point) to consider the reading
    # statistically meaningful
    min_meaningful_gex: float = 1_000_000.0

    # Refresh interval for GEX recalculation (seconds)
    recalculation_interval_seconds: int = 30


GEX_SCANNER = GEXScannerConstants()


# ---------------------------------------------------------------------------
# 11. SELF-LEARNING CONSTANTS
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SelfLearningConstants:
    """
    Constants for the adaptive self-learning / self-calibration module.

    The self-learning system adjusts factor weights, thresholds, and targets
    over time based on observed trade outcomes, using exponential moving
    averages and bounded optimisation.
    """

    # Exponential moving average weight for factor-weight adjustment.
    # Higher values mean slower adaptation (more weight on history).
    ema_weight: float = 0.95

    # Hard bounds on individual factor weights (prevents any single
    # factor from dominating or becoming negligible)
    max_factor_weight: float = 0.40  # 40%
    min_factor_weight: float = 0.05  # 5%

    # Maximum adjustment to any threshold per calibration cycle (points)
    calibration_threshold_adjustment: float = 2.0

    # Daily target adjustment rate: how quickly profit targets and stop
    # levels adapt to recent performance
    target_adjustment_rate: float = 0.05  # 5% per day

    # Regime detection rolling window (trading days)
    regime_detection_window_days: int = 20

    # Trade-count milestones at which the system performs a full
    # recalibration of all parameters
    recalibration_milestones: Tuple[int, ...] = (100, 500, 1000)

    # Minimum number of trades before any self-learning adjustments
    # are applied (cold-start guard)
    min_trades_for_learning: int = 30

    # Maximum cumulative drift from default weights before a hard reset
    # to defaults is considered (L1 norm across all factors)
    max_cumulative_drift: float = 0.50

    # Learning rate decay: factor by which the learning rate is multiplied
    # at each recalibration milestone
    learning_rate_decay: float = 0.90


SELF_LEARNING = SelfLearningConstants()


# ---------------------------------------------------------------------------
# 12. RISK MANAGEMENT CONSTANTS
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RiskManagementConstants:
    """
    Hard risk limits that CANNOT be overridden by self-learning or
    configuration.  These are safety rails.
    """

    # Maximum risk per trade as a fraction of the daily trading budget
    max_risk_per_trade_pct: float = 0.02  # 2% of daily budget

    # CRITICAL SAFETY RULE: Naked short positions are NEVER permitted.
    # All short options must be part of a defined-risk spread.
    allow_naked_short: bool = False  # NO NAKED SHORT POSITIONS

    # Maximum tolerable slippage per leg (dollars)
    max_slippage_tolerance: float = 0.20  # $0.20

    # Maximum number of concurrent open positions
    max_concurrent_positions: int = 5

    # Maximum daily loss before trading is halted (fraction of daily budget)
    max_daily_loss_pct: float = 0.06  # 6% of daily budget

    # Maximum single-trade notional as fraction of account equity
    max_single_trade_notional_pct: float = 0.10  # 10%

    # Minimum account equity required to trade (dollars)
    min_account_equity: float = 25_000.0

    # Order types permitted (limit-only for safety)
    permitted_order_types: FrozenSet[str] = frozenset({"LIMIT", "LIMIT_ON_CLOSE"})

    # Fill-or-kill timeout (seconds) for limit orders
    order_fill_timeout_seconds: int = 30


RISK_MANAGEMENT = RiskManagementConstants()


# ---------------------------------------------------------------------------
# CONVENIENCE ALIASES -- alternate names used by __init__.py and scanners
# ---------------------------------------------------------------------------

# Trading hours extracted from the contract spec for convenient access
@dataclass(frozen=True)
class TradingHoursSpec:
    """Trading hours for SPX options."""
    market_open: time = SPX_CONTRACT.market_open
    market_close: time = SPX_CONTRACT.market_close
    settlement_time: time = SPX_CONTRACT.settlement_time

TRADING_HOURS = TradingHoursSpec()

# Tick sizes extracted from the contract spec
@dataclass(frozen=True)
class TickSizesSpec:
    """Tick size rules for SPX options."""
    below_boundary: float = SPX_CONTRACT.tick_size_below_3
    at_or_above_boundary: float = SPX_CONTRACT.tick_size_at_or_above_3
    boundary: float = SPX_CONTRACT.tick_price_boundary

TICK_SIZES = TickSizesSpec()

# Contract multiplier shortcut
MULTIPLIER: float = SPX_CONTRACT.multiplier

# Intraday zone schedule aliases
TIME_ZONES = INTRADAY_ZONE_SCHEDULE
TimeZoneConfig = TimeZoneBoundary

# Factor weights aliases (used by __init__.py and directional_scanner.py)
FACTOR_WEIGHTS_DEFAULT = DEFAULT_FACTOR_WEIGHTS
FACTOR_WEIGHTS = DEFAULT_FACTOR_WEIGHTS

# Exit management alias
EXIT_CONSTANTS = EXIT_MANAGEMENT

# Liquidity filters extracted from strike selection constants
@dataclass(frozen=True)
class LiquidityFiltersSpec:
    """Minimum liquidity thresholds for options."""
    min_open_interest: int = STRIKE_SELECTION.min_open_interest
    min_volume: int = STRIKE_SELECTION.min_volume
    max_bid_ask_spread_pct: float = STRIKE_SELECTION.max_bid_ask_spread_pct

LIQUIDITY_FILTERS = LiquidityFiltersSpec()

# Section aliases for downstream consumers
PREMIUM_SELLING_CONSTANTS = PREMIUM_SELLING
GEX_CONSTANTS = GEX_SCANNER
CALIBRATION_CONSTANTS = SELF_LEARNING
RISK_CONSTANTS = RISK_MANAGEMENT
VIX1D_CONSTANTS = VIX1D


# ---------------------------------------------------------------------------
# AGGREGATE EXPORT -- single namespace for downstream imports
# ---------------------------------------------------------------------------

__all__: List[str] = [
    # Section 1 - Contract
    "ContractSpec",
    "SPX_CONTRACT",
    # Section 2 - Intraday Zones
    "IntradayZone",
    "TimeZoneBoundary",
    "INTRADAY_ZONE_SCHEDULE",
    "ZONE_BOUNDARIES",
    # Section 3 - Greeks
    "TRADING_MINUTES_PER_DAY",
    "TRADING_SECONDS_PER_DAY",
    "CALENDAR_DAYS_PER_YEAR",
    "TRADING_DAYS_PER_YEAR",
    "GammaRangeSnapshot",
    "GAMMA_RANGES",
    "ThetaDecayPoint",
    "THETA_DECAY_CURVE",
    "DeltaDecayConstants",
    "DELTA_DECAY",
    # Section 4 - VIX1D
    "VIX1DConstants",
    "VIX1D",
    "VIX1DRegime",
    "VIX1DRegimeThreshold",
    "VIX1D_REGIME_THRESHOLDS",
    # Section 5 - Direction Score
    "DirectionScoreThresholds",
    "DIRECTION_THRESHOLDS",
    # Section 6 - Factor Weights
    "DirectionFactor",
    "FactorWeightDefaults",
    "DEFAULT_FACTOR_WEIGHTS",
    # Section 7 - Strike Selection
    "DeltaRange",
    "StrikeSelectionConstants",
    "STRIKE_SELECTION",
    # Section 8 - Exit Management
    "ProfitTargetByZone",
    "ExitManagementConstants",
    "EXIT_MANAGEMENT",
    # Section 9 - Premium Selling
    "PremiumSellingConstants",
    "PREMIUM_SELLING",
    # Section 10 - GEX Scanner
    "GEXScannerConstants",
    "GEX_SCANNER",
    # Section 11 - Self-Learning
    "SelfLearningConstants",
    "SELF_LEARNING",
    # Section 12 - Risk Management
    "RiskManagementConstants",
    "RISK_MANAGEMENT",
    # Convenience aliases
    "TradingHoursSpec",
    "TRADING_HOURS",
    "TickSizesSpec",
    "TICK_SIZES",
    "MULTIPLIER",
    "TIME_ZONES",
    "TimeZoneConfig",
    "FACTOR_WEIGHTS_DEFAULT",
    "FACTOR_WEIGHTS",
    "EXIT_CONSTANTS",
    "LiquidityFiltersSpec",
    "LIQUIDITY_FILTERS",
    "PREMIUM_SELLING_CONSTANTS",
    "GEX_CONSTANTS",
    "CALIBRATION_CONSTANTS",
    "RISK_CONSTANTS",
    "VIX1D_CONSTANTS",
]
