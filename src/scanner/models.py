"""
Revolution Alpha Engine - Scanner Data Models

Institutional-grade data models for real-time market scanning system.
Supports options flow, squeeze detection, momentum, and reversal patterns.
"""

from pydantic import BaseModel, Field, field_validator
from datetime import datetime, timezone
from typing import Optional, Literal, Any
from enum import Enum


class ScanMode(str, Enum):
    """Available scanner modes for different trading strategies."""
    OPTIONS_DAY = "options_day"
    OPTIONS_SWING = "options_swing"
    SQUEEZE = "squeeze"
    REVERSAL = "reversal"
    MOMENTUM = "momentum"
    BREAKOUT = "breakout"
    MEAN_REVERSION = "mean_reversion"
    ALL = "all"


class SignalDirection(str, Enum):
    """Trade direction signals."""
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"


class SqueezeType(str, Enum):
    """Types of squeeze patterns detected."""
    SHORT = "short_squeeze"
    GAMMA = "gamma_squeeze"
    DELTA = "delta_squeeze"
    COMBINED = "combined_squeeze"


class SignalStrength(str, Enum):
    """Signal strength classification."""
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    EXTREME = "extreme"


class TimeFrame(str, Enum):
    """Supported timeframes for scanning."""
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"


class MarketRegime(str, Enum):
    """Current market regime classification."""
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    BREAKOUT = "breakout"


# =============================================================================
# Base Scan Results
# =============================================================================

class ScanResult(BaseModel):
    """Base class for all scan results."""
    symbol: str = Field(..., description="Ticker symbol")
    scanner_type: str = Field(..., description="Type of scanner that generated this result")
    direction: SignalDirection = Field(..., description="Trade direction")
    confidence: float = Field(..., description="Confidence score 0-100")
    entry_price: Optional[float] = Field(None, gt=0, description="Suggested entry price")
    stop_loss: Optional[float] = Field(None, gt=0, description="Suggested stop loss")
    targets: list[float] = Field(default_factory=list, description="Price targets")
    risk_reward: Optional[float] = Field(None, description="Risk/reward ratio")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Scan timestamp")
    timeframe: TimeFrame = Field(default=TimeFrame.M5, description="Analysis timeframe")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    @field_validator('confidence')
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Ensure confidence is within valid range."""
        return round(max(0, min(100, v)), 2)

    @property
    def signal_strength(self) -> SignalStrength:
        """Classify signal strength based on confidence."""
        if self.confidence >= 85:
            return SignalStrength.EXTREME
        elif self.confidence >= 70:
            return SignalStrength.STRONG
        elif self.confidence >= 50:
            return SignalStrength.MODERATE
        return SignalStrength.WEAK

    @property
    def is_actionable(self) -> bool:
        """Check if signal meets minimum actionable threshold."""
        return self.confidence >= 60 and self.entry_price is not None


class OptionsScanResult(ScanResult):
    """Scan result for options-specific signals."""
    strike: float = Field(..., gt=0, description="Option strike price")
    expiration: datetime = Field(..., description="Option expiration date")
    option_type: Literal["CALL", "PUT"] = Field(..., description="Option type")
    greeks: dict[str, float] = Field(default_factory=dict, description="Option Greeks")
    iv_rank: Optional[float] = Field(None, ge=0, le=100, description="IV Rank 0-100")
    iv_percentile: Optional[float] = Field(None, ge=0, le=100, description="IV Percentile 0-100")
    bid: Optional[float] = Field(None, ge=0, description="Bid price")
    ask: Optional[float] = Field(None, ge=0, description="Ask price")
    volume: Optional[int] = Field(None, ge=0, description="Option volume")
    open_interest: Optional[int] = Field(None, ge=0, description="Open interest")
    underlying_price: Optional[float] = Field(None, gt=0, description="Underlying stock price")

    @property
    def spread(self) -> Optional[float]:
        """Calculate bid-ask spread."""
        if self.bid is not None and self.ask is not None:
            return self.ask - self.bid
        return None

    @property
    def spread_pct(self) -> Optional[float]:
        """Calculate bid-ask spread as percentage."""
        if self.bid is not None and self.ask is not None and self.bid > 0:
            return ((self.ask - self.bid) / self.bid) * 100
        return None

    @property
    def days_to_expiry(self) -> int:
        """Calculate days until expiration."""
        return max(0, (self.expiration - datetime.now(timezone.utc)).days)

    @property
    def is_itm(self) -> bool:
        """Check if option is in-the-money."""
        if self.underlying_price is None:
            return False
        if self.option_type == "CALL":
            return self.underlying_price > self.strike
        return self.underlying_price < self.strike


class SqueezeScanResult(ScanResult):
    """Scan result for squeeze detection."""
    squeeze_type: SqueezeType = Field(..., description="Type of squeeze detected")
    squeeze_score: float = Field(..., ge=0, le=100, description="Squeeze intensity score")
    gamma_walls: list[dict[str, Any]] = Field(default_factory=list, description="Gamma wall levels")
    key_levels: list[float] = Field(default_factory=list, description="Key price levels")
    volume_ratio: float = Field(..., gt=0, description="Volume vs average ratio")
    short_interest: Optional[float] = Field(None, ge=0, description="Short interest percentage")
    days_to_cover: Optional[float] = Field(None, ge=0, description="Days to cover shorts")
    cost_to_borrow: Optional[float] = Field(None, description="Cost to borrow percentage")
    ftd_count: Optional[int] = Field(None, ge=0, description="Fail-to-deliver count")

    @property
    def is_critical_squeeze(self) -> bool:
        """Check if squeeze conditions are critical."""
        return self.squeeze_score >= 80 and self.volume_ratio >= 3.0


class MomentumScanResult(ScanResult):
    """Scan result for momentum signals."""
    rsi: Optional[float] = Field(None, ge=0, le=100, description="RSI value")
    macd_histogram: Optional[float] = Field(None, description="MACD histogram value")
    macd_signal: Optional[float] = Field(None, description="MACD signal line")
    adx: Optional[float] = Field(None, ge=0, description="ADX value")
    volume_surge: float = Field(default=1.0, gt=0, description="Volume surge multiplier")
    price_momentum: Optional[float] = Field(None, description="Price momentum score")
    sector_momentum: Optional[float] = Field(None, description="Sector relative momentum")
    trend_strength: Optional[float] = Field(None, ge=0, le=100, description="Trend strength 0-100")

    @property
    def is_overbought(self) -> bool:
        """Check if RSI indicates overbought."""
        return self.rsi is not None and self.rsi >= 70

    @property
    def is_oversold(self) -> bool:
        """Check if RSI indicates oversold."""
        return self.rsi is not None and self.rsi <= 30


class ReversalScanResult(ScanResult):
    """Scan result for reversal pattern detection."""
    pattern_name: str = Field(..., description="Name of reversal pattern")
    pattern_confidence: float = Field(..., ge=0, le=100, description="Pattern confidence")
    support_level: Optional[float] = Field(None, gt=0, description="Nearest support")
    resistance_level: Optional[float] = Field(None, gt=0, description="Nearest resistance")
    divergence_type: Optional[str] = Field(None, description="Divergence type if present")
    volume_confirmation: bool = Field(default=False, description="Volume confirms pattern")
    prior_trend_strength: Optional[float] = Field(None, description="Strength of prior trend")

    @property
    def has_divergence(self) -> bool:
        """Check if divergence is present."""
        return self.divergence_type is not None


class BreakoutScanResult(ScanResult):
    """Scan result for breakout detection."""
    breakout_level: float = Field(..., gt=0, description="Breakout price level")
    breakout_type: Literal["resistance", "support", "channel", "pattern"] = Field(
        ..., description="Type of breakout"
    )
    volume_confirmation: bool = Field(default=False, description="Volume confirms breakout")
    retest_expected: bool = Field(default=False, description="Retest of level expected")
    consolidation_days: Optional[int] = Field(None, ge=0, description="Days in consolidation")
    atr_multiple: Optional[float] = Field(None, gt=0, description="Move as multiple of ATR")


# =============================================================================
# Scanner Configuration Models
# =============================================================================

class ScannerConfig(BaseModel):
    """Configuration for scanner parameters."""
    min_confidence: float = Field(default=60.0, ge=0, le=100, description="Minimum confidence threshold")
    min_volume: int = Field(default=100000, ge=0, description="Minimum volume filter")
    min_price: float = Field(default=5.0, ge=0, description="Minimum price filter")
    max_price: float = Field(default=500.0, ge=0, description="Maximum price filter")
    min_market_cap: Optional[float] = Field(None, ge=0, description="Minimum market cap")
    sectors: list[str] = Field(default_factory=list, description="Sectors to include")
    excluded_symbols: list[str] = Field(default_factory=list, description="Symbols to exclude")
    timeframes: list[TimeFrame] = Field(
        default_factory=lambda: [TimeFrame.M5, TimeFrame.M15],
        description="Timeframes to scan"
    )
    scan_modes: list[ScanMode] = Field(
        default_factory=lambda: [ScanMode.ALL],
        description="Scanner modes to run"
    )


class OptionsFilterConfig(BaseModel):
    """Configuration for options-specific filters."""
    min_dte: int = Field(default=7, ge=0, description="Minimum days to expiry")
    max_dte: int = Field(default=45, ge=0, description="Maximum days to expiry")
    min_volume: int = Field(default=100, ge=0, description="Minimum option volume")
    min_open_interest: int = Field(default=500, ge=0, description="Minimum open interest")
    max_spread_pct: float = Field(default=10.0, ge=0, description="Maximum spread percentage")
    min_iv_rank: float = Field(default=0, ge=0, le=100, description="Minimum IV rank")
    max_iv_rank: float = Field(default=100, ge=0, le=100, description="Maximum IV rank")
    delta_range: tuple[float, float] = Field(
        default=(-0.70, 0.70),
        description="Delta range filter"
    )


class SqueezeFilterConfig(BaseModel):
    """Configuration for squeeze scanner filters."""
    min_short_interest: float = Field(default=10.0, ge=0, description="Minimum short interest %")
    min_volume_ratio: float = Field(default=1.5, gt=0, description="Minimum volume ratio")
    min_squeeze_score: float = Field(default=50.0, ge=0, le=100, description="Minimum squeeze score")
    include_gamma_squeeze: bool = Field(default=True, description="Include gamma squeezes")
    include_short_squeeze: bool = Field(default=True, description="Include short squeezes")


# =============================================================================
# Alert and Notification Models
# =============================================================================

class AlertPriority(str, Enum):
    """Alert priority levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ScanAlert(BaseModel):
    """Alert generated from scan results."""
    alert_id: str = Field(..., description="Unique alert identifier")
    scan_result: ScanResult = Field(..., description="Associated scan result")
    priority: AlertPriority = Field(..., description="Alert priority")
    message: str = Field(..., description="Alert message")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    acknowledged: bool = Field(default=False, description="Whether alert was acknowledged")
    expires_at: Optional[datetime] = Field(None, description="Alert expiration time")

    @property
    def is_expired(self) -> bool:
        """Check if alert has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at


# =============================================================================
# Aggregated Results
# =============================================================================

class ScannerSummary(BaseModel):
    """Summary of scanner run results."""
    scanner_name: str = Field(..., description="Scanner name")
    scan_mode: ScanMode = Field(..., description="Scan mode used")
    symbols_scanned: int = Field(..., ge=0, description="Number of symbols scanned")
    signals_found: int = Field(..., ge=0, description="Number of signals found")
    high_confidence_signals: int = Field(..., ge=0, description="Signals with confidence >= 70")
    started_at: datetime = Field(..., description="Scan start time")
    completed_at: datetime = Field(..., description="Scan completion time")
    errors: list[str] = Field(default_factory=list, description="Errors encountered")

    @property
    def duration_seconds(self) -> float:
        """Calculate scan duration in seconds."""
        return (self.completed_at - self.started_at).total_seconds()

    @property
    def signals_per_second(self) -> float:
        """Calculate scanning rate."""
        if self.duration_seconds == 0:
            return 0
        return self.symbols_scanned / self.duration_seconds


class ScannerBatchResult(BaseModel):
    """Batch result containing multiple scan results."""
    batch_id: str = Field(..., description="Unique batch identifier")
    results: list[ScanResult] = Field(default_factory=list, description="Scan results")
    summaries: list[ScannerSummary] = Field(default_factory=list, description="Scanner summaries")
    market_regime: MarketRegime = Field(..., description="Detected market regime")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def total_signals(self) -> int:
        """Total number of signals in batch."""
        return len(self.results)

    @property
    def actionable_signals(self) -> list[ScanResult]:
        """Filter to only actionable signals."""
        return [r for r in self.results if r.is_actionable]

    def filter_by_direction(self, direction: SignalDirection) -> list[ScanResult]:
        """Filter results by direction."""
        return [r for r in self.results if r.direction == direction]

    def filter_by_confidence(self, min_confidence: float) -> list[ScanResult]:
        """Filter results by minimum confidence."""
        return [r for r in self.results if r.confidence >= min_confidence]

    def top_signals(self, n: int = 10) -> list[ScanResult]:
        """Get top N signals by confidence."""
        return sorted(self.results, key=lambda x: x.confidence, reverse=True)[:n]
