"""
Revolution Alpha Engine - Advanced Scanner Models

Comprehensive output format and enhanced data models for the
institutional-grade market intelligence system.

Implements the standardized scan output with:
- Signal direction, strength, and confidence calibration
- Expected move, timeframe, and risk/reward
- Supporting/contradicting evidence tracking
- Historical accuracy and regime context
- Mathematical basis documentation
- Alpha decay and false positive rate tracking
"""

from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional, Literal, Any, Dict, List
from enum import Enum
import numpy as np


# =============================================================================
# Extended Enumerations
# =============================================================================

class ScanCategory(str, Enum):
    """Scan categories A-J as defined in the taxonomy."""
    PRICE_ACTION = "A"
    OPTIONS = "B"
    MARKET_INTERNALS = "C"
    INSTITUTIONAL = "D"
    MACHINE_LEARNING = "E"
    ADVANCED_MATH = "F"
    MACRO_REGIME = "G"
    EXECUTION = "H"
    RISK_MANAGEMENT = "I"
    PROPRIETARY = "J"


class RegimeContext(str, Enum):
    """Market regime context for signal."""
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    RANGING = "RANGING"
    VOLATILE = "VOLATILE"
    QUIET = "QUIET"
    CRISIS = "CRISIS"
    RECOVERY = "RECOVERY"
    TRANSITION = "TRANSITION"


class ExpectedTimeframe(str, Enum):
    """Expected timeframe for the signal to play out."""
    SCALP = "SCALP"        # Minutes
    INTRADAY = "1D"
    SWING = "1W"
    POSITION = "1M"
    INVESTMENT = "3M"


class VolatilityRegime(str, Enum):
    """Volatility regime classification."""
    ULTRA_LOW = "ultra_low"
    LOW = "low"
    NORMAL = "normal"
    ELEVATED = "elevated"
    HIGH = "high"
    EXTREME = "extreme"


class TrendPhase(str, Enum):
    """Trend phase within a move."""
    ACCUMULATION = "accumulation"
    MARKUP = "markup"
    DISTRIBUTION = "distribution"
    MARKDOWN = "markdown"
    RE_ACCUMULATION = "re_accumulation"
    RE_DISTRIBUTION = "re_distribution"


# =============================================================================
# Advanced Scan Output Format
# =============================================================================

class AdvancedScanResult(BaseModel):
    """
    Comprehensive scan result matching the institutional output specification.

    Every scan in the system produces this standardized output format,
    enabling uniform processing, aggregation, and backtesting.
    """
    # Identification
    scan_id: str = Field(..., description="Unique scan identifier")
    scan_name: str = Field(..., description="Human-readable scan name")
    category: ScanCategory = Field(..., description="A-J scan category")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="ISO 8601 timestamp")
    symbol: str = Field(..., description="Ticker symbol")

    # Signal Core
    signal_direction: Literal["BULLISH", "BEARISH", "NEUTRAL"] = Field(
        ..., description="Primary signal direction"
    )
    signal_strength: float = Field(
        ..., ge=0.0, le=1.0, description="Signal strength 0.0-1.0"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Calibrated confidence 0.0-1.0"
    )

    # Expected Outcome
    expected_move_pct: float = Field(
        default=0.0, description="Expected price move percentage"
    )
    expected_timeframe: ExpectedTimeframe = Field(
        default=ExpectedTimeframe.SWING, description="Expected timeframe"
    )
    risk_reward_ratio: float = Field(
        default=0.0, ge=0.0, description="Risk/reward ratio"
    )

    # Trade Levels
    entry_price: Optional[float] = Field(None, description="Suggested entry price")
    stop_loss_level: float = Field(default=0.0, description="Stop loss level")
    target_level: float = Field(default=0.0, description="Primary target level")
    secondary_targets: List[float] = Field(
        default_factory=list, description="Additional price targets"
    )

    # Evidence
    supporting_evidence: List[str] = Field(
        default_factory=list, description="List of confirming signals"
    )
    contradicting_evidence: List[str] = Field(
        default_factory=list, description="List of opposing signals"
    )

    # Quality Metrics
    historical_accuracy: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Historical hit rate"
    )
    regime_context: RegimeContext = Field(
        default=RegimeContext.RANGING, description="Current market regime"
    )
    mathematical_basis: str = Field(
        default="", description="Brief mathematical description"
    )
    false_positive_rate: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Estimated FP rate"
    )
    decay_halflife_days: int = Field(
        default=0, ge=0, description="Signal alpha decay halflife"
    )

    # Extended Metadata
    information_coefficient: Optional[float] = Field(
        None, description="Estimated IC of the signal"
    )
    signal_to_noise: Optional[float] = Field(
        None, description="Signal-to-noise ratio"
    )
    transaction_cost_adjusted: bool = Field(
        default=False, description="Whether signal survives t-cost adjustment"
    )
    volatility_regime: Optional[VolatilityRegime] = Field(
        None, description="Current volatility regime"
    )
    trend_phase: Optional[TrendPhase] = Field(
        None, description="Current trend phase"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional scan-specific data"
    )

    @field_validator('signal_strength', 'confidence')
    @classmethod
    def clamp_zero_one(cls, v: float) -> float:
        return round(max(0.0, min(1.0, v)), 4)


# =============================================================================
# Volatility Scanner Models
# =============================================================================

class VolatilityEstimate(BaseModel):
    """Advanced volatility estimate using multiple estimators."""
    symbol: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Estimators
    close_to_close: float = Field(description="Simple close-to-close vol")
    parkinson: float = Field(description="Parkinson high-low estimator")
    garman_klass: float = Field(description="Garman-Klass estimator")
    rogers_satchell: float = Field(description="Rogers-Satchell estimator")
    yang_zhang: float = Field(description="Yang-Zhang estimator")
    garch_forecast: Optional[float] = Field(None, description="GARCH(1,1) forecast")

    # Regime
    volatility_regime: VolatilityRegime = Field(description="Current vol regime")
    vol_percentile: float = Field(ge=0, le=100, description="Vol percentile rank")
    vol_z_score: float = Field(description="Vol z-score vs history")

    # Term structure
    short_term_vol: float = Field(description="5-day realized vol")
    medium_term_vol: float = Field(description="20-day realized vol")
    long_term_vol: float = Field(description="60-day realized vol")
    vol_term_structure: Literal["contango", "backwardation", "flat"] = Field(
        description="Vol term structure shape"
    )

    @property
    def best_estimate(self) -> float:
        """Return the most robust volatility estimate (Yang-Zhang)."""
        return self.yang_zhang

    @property
    def vol_compression(self) -> bool:
        """Detect volatility compression (short << long)."""
        return self.short_term_vol < self.long_term_vol * 0.6


class GARCHResult(BaseModel):
    """GARCH model estimation result."""
    omega: float = Field(description="GARCH omega (constant)")
    alpha: float = Field(description="GARCH alpha (ARCH term)")
    beta: float = Field(description="GARCH beta (GARCH term)")
    persistence: float = Field(description="alpha + beta (persistence)")
    unconditional_vol: float = Field(description="Long-run volatility")
    current_vol: float = Field(description="Current conditional volatility")
    forecast_1d: float = Field(description="1-day ahead vol forecast")
    forecast_5d: float = Field(description="5-day ahead vol forecast")
    forecast_20d: float = Field(description="20-day ahead vol forecast")
    log_likelihood: float = Field(description="Log-likelihood of fit")
    aic: float = Field(description="Akaike Information Criterion")
    bic: float = Field(description="Bayesian Information Criterion")


# =============================================================================
# Market Structure Models
# =============================================================================

class StructureBreak(BaseModel):
    """Break of Structure (BOS) or Change of Character (CHoCH) detection."""
    break_type: Literal["BOS", "CHoCH"] = Field(description="Type of structure break")
    direction: Literal["bullish", "bearish"] = Field(description="Break direction")
    price_level: float = Field(description="Price level of the break")
    timestamp: datetime = Field(description="When break occurred")
    confidence: float = Field(ge=0, le=1, description="Detection confidence")
    swing_high: Optional[float] = Field(None, description="Related swing high")
    swing_low: Optional[float] = Field(None, description="Related swing low")
    confirmed: bool = Field(default=False, description="Candle close confirmation")


class FairValueGap(BaseModel):
    """Fair Value Gap / Imbalance detection."""
    gap_type: Literal["bullish", "bearish"] = Field(description="FVG direction")
    upper_bound: float = Field(description="Upper bound of the gap")
    lower_bound: float = Field(description="Lower bound of the gap")
    midpoint: float = Field(description="Midpoint (CE) of the gap")
    size_pct: float = Field(description="Gap size as % of price")
    timestamp: datetime = Field(description="When gap formed")
    filled: bool = Field(default=False, description="Whether gap has been filled")
    fill_percentage: float = Field(default=0.0, description="How much has been filled")


class OrderBlock(BaseModel):
    """Order block identification."""
    block_type: Literal["bullish", "bearish"] = Field(description="OB direction")
    upper_bound: float = Field(description="Upper bound of order block")
    lower_bound: float = Field(description="Lower bound of order block")
    timestamp: datetime = Field(description="When OB formed")
    strength: float = Field(ge=0, le=1, description="OB strength score")
    tested: bool = Field(default=False, description="Has price tested this OB")
    mitigated: bool = Field(default=False, description="Has OB been mitigated")
    volume_confirmation: bool = Field(default=False, description="Volume confirms OB")


class LiquiditySweep(BaseModel):
    """Liquidity trap detection — predictive reversal zone."""
    sweep_type: Literal["buy_side", "sell_side"] = Field(description="Type of sweep")
    level_swept: float = Field(description="Price level that was swept")
    sweep_depth: float = Field(description="How far past the level")
    recovery_speed: float = Field(description="Speed of price recovery")
    timestamp: datetime = Field(description="When sweep occurred")
    volume_spike: bool = Field(default=False, description="Accompanied by volume spike")


# =============================================================================
# Options Intelligence Models
# =============================================================================

class IVSurfacePoint(BaseModel):
    """Single point on the implied volatility surface."""
    strike: float
    expiration: datetime
    iv: float
    delta: Optional[float] = None
    moneyness: float = Field(description="Strike / Spot ratio")


class IVSurface(BaseModel):
    """Full implied volatility surface."""
    symbol: str
    underlying_price: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    points: List[IVSurfacePoint] = Field(default_factory=list)

    # Surface analytics
    atm_vol: float = Field(description="ATM implied volatility")
    skew_25d: float = Field(description="25-delta risk reversal (put skew)")
    butterfly_25d: float = Field(description="25-delta butterfly (smile)")
    term_structure_slope: float = Field(description="IV term structure slope")

    # Rankings
    iv_rank_30: float = Field(description="30-day IV rank")
    iv_rank_252: float = Field(description="252-day IV rank")
    iv_percentile_30: float = Field(description="30-day IV percentile")
    iv_percentile_252: float = Field(description="252-day IV percentile")

    # Surface regime
    surface_regime: Literal["fear", "complacency", "uncertainty", "normal"] = Field(
        description="IV surface regime classification"
    )


class GreeksExposure(BaseModel):
    """Aggregate Greeks exposure at a price level or for the market."""
    symbol: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Net exposures
    net_gamma: float = Field(description="Net gamma exposure in $")
    net_delta: float = Field(description="Net delta exposure in shares")
    net_vanna: float = Field(description="Net vanna exposure")
    net_charm: float = Field(description="Net charm exposure")

    # Key levels
    gamma_flip_level: Optional[float] = Field(
        None, description="Price where gamma flips sign"
    )
    max_gamma_strike: float = Field(description="Strike with max gamma")
    gamma_walls: List[Dict[str, Any]] = Field(
        default_factory=list, description="Significant gamma levels"
    )

    # Regime
    gamma_regime: Literal["long_gamma", "short_gamma", "neutral"] = Field(
        description="Dealer gamma positioning"
    )
    expected_pin: Optional[float] = Field(
        None, description="Expected pinning level"
    )


# =============================================================================
# Fractal & Information Theory Models
# =============================================================================

class FractalAnalysis(BaseModel):
    """Fractal analysis results."""
    symbol: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Hurst exponent
    hurst_exponent: float = Field(description="Hurst exponent (0-1)")
    hurst_interpretation: Literal[
        "anti_persistent", "random_walk", "persistent"
    ] = Field(description="Hurst interpretation")

    # Fractal dimension
    fractal_dimension: float = Field(description="Estimated fractal dimension")

    # Entropy measures
    shannon_entropy: float = Field(description="Shannon entropy")
    permutation_entropy: float = Field(description="Permutation entropy")
    sample_entropy: float = Field(description="Sample entropy")

    # Complexity
    complexity_score: float = Field(
        ge=0, le=1, description="Market complexity 0-1"
    )

    @property
    def is_trending(self) -> bool:
        """Hurst > 0.5 indicates trending (persistent) behavior."""
        return self.hurst_exponent > 0.55

    @property
    def is_mean_reverting(self) -> bool:
        """Hurst < 0.5 indicates mean-reverting (anti-persistent) behavior."""
        return self.hurst_exponent < 0.45


# =============================================================================
# Market Breadth Models
# =============================================================================

class BreadthSnapshot(BaseModel):
    """Market breadth snapshot."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Advance/Decline
    advancers: int = Field(description="Number of advancing issues")
    decliners: int = Field(description="Number of declining issues")
    unchanged: int = Field(description="Number of unchanged issues")
    ad_ratio: float = Field(description="Advance/decline ratio")
    ad_line: float = Field(description="Cumulative AD line value")
    mcclellan_oscillator: float = Field(description="McClellan oscillator")
    mcclellan_summation: float = Field(description="McClellan summation index")

    # Breadth measures
    pct_above_sma20: float = Field(description="% above 20-day SMA")
    pct_above_sma50: float = Field(description="% above 50-day SMA")
    pct_above_sma200: float = Field(description="% above 200-day SMA")

    # New highs/lows
    new_highs: int = Field(description="52-week new highs")
    new_lows: int = Field(description="52-week new lows")
    nh_nl_diff: int = Field(description="New highs minus new lows")

    # Breadth thrust
    thrust_signal: Optional[Literal["bullish", "bearish"]] = Field(
        None, description="Breadth thrust signal if triggered"
    )
    breadth_regime: Literal["healthy", "deteriorating", "weak", "recovering"] = Field(
        description="Breadth regime"
    )


# =============================================================================
# Backtesting Validation Models
# =============================================================================

class BacktestValidation(BaseModel):
    """Backtesting validation results."""
    scan_name: str
    test_period_start: datetime
    test_period_end: datetime

    # Performance
    total_signals: int
    winning_signals: int
    losing_signals: int
    win_rate: float
    avg_return: float
    sharpe_ratio: float
    max_drawdown: float
    profit_factor: float

    # Validation
    deflated_sharpe: float = Field(description="Sharpe adjusted for multiple testing")
    probability_of_overfitting: float = Field(description="PBO estimate")
    minimum_backtest_length: int = Field(description="MBL in trading days")
    out_of_sample_sharpe: float = Field(description="OOS Sharpe ratio")

    # Statistical tests
    p_value: float = Field(description="Statistical significance p-value")
    multiple_testing_adjusted_p: float = Field(
        description="Bonferroni/BH adjusted p-value"
    )
    is_statistically_significant: bool = Field(
        description="Passes significance at 5% level"
    )

    # Regime performance
    performance_by_regime: Dict[str, float] = Field(
        default_factory=dict, description="Sharpe by regime"
    )

    # Transaction costs
    gross_sharpe: float = Field(description="Sharpe before costs")
    net_sharpe: float = Field(description="Sharpe after realistic costs")
    breakeven_cost_bps: float = Field(description="Breakeven transaction cost in bps")


# =============================================================================
# Self-Learning Framework Models
# =============================================================================

class ScanPerformanceTracker(BaseModel):
    """Track individual scan performance over time."""
    scan_name: str
    category: ScanCategory
    total_signals: int = 0
    correct_signals: int = 0
    current_accuracy: float = 0.0
    rolling_sharpe: float = 0.0
    alpha_remaining: float = 1.0  # 1.0 = full alpha, decaying
    last_updated: datetime = Field(default_factory=datetime.utcnow)

    # Adaptive weight
    base_weight: float = 1.0
    regime_weight: float = 1.0
    performance_weight: float = 1.0
    effective_weight: float = 1.0

    # Drift detection
    drift_detected: bool = False
    drift_magnitude: float = 0.0
    last_drift_check: datetime = Field(default_factory=datetime.utcnow)

    @property
    def hit_rate(self) -> float:
        if self.total_signals == 0:
            return 0.0
        return self.correct_signals / self.total_signals

    def update_weight(self):
        """Calculate effective weight from components."""
        self.effective_weight = (
            self.base_weight *
            self.regime_weight *
            self.performance_weight *
            self.alpha_remaining
        )
