"""
SCANIFY SPX 0DTE Options Day Trading Scanner + GEX Scanner -- Data Models

Production-grade Pydantic and dataclass models for the full SCANIFY system,
covering market data ingestion, GEX profiling, directional scoring, scan
signals, spread construction, trade logging, calibration, and pre-market
session setup.

All monetary values are in USD.  All timestamps are timezone-aware or UTC.
Scores use the range explicitly documented on each field.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field as dc_field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


# =============================================================================
# 1. ENUMS
# =============================================================================


class SessionType(str, Enum):
    """Intraday market-regime classification for the current session."""

    TRENDING = "TRENDING"
    RANGE = "RANGE"
    VOLATILE = "VOLATILE"
    SQUEEZE = "SQUEEZE"
    EVENT = "EVENT"


class ScanType(str, Enum):
    """Strategy archetype the scanner is configured to detect."""

    DIRECTIONAL = "DIRECTIONAL"
    PREMIUM_SELL = "PREMIUM_SELL"
    GAMMA_SCALP = "GAMMA_SCALP"


class TradeDirection(str, Enum):
    """Directional bias produced by the composite scoring engine."""

    BULL = "BULL"
    BEAR = "BEAR"
    NEUTRAL = "NEUTRAL"


class ExitReason(str, Enum):
    """Reason a trade was closed -- used in post-trade diagnostics."""

    PROFIT_TARGET = "PROFIT_TARGET"
    STOP_LOSS = "STOP_LOSS"
    TIME_STOP = "TIME_STOP"
    SIGNAL_REVERSAL = "SIGNAL_REVERSAL"
    GEX_FLIP = "GEX_FLIP"
    VIX_SPIKE = "VIX_SPIKE"
    MANUAL = "MANUAL"
    BREAK_EVEN = "BREAK_EVEN"
    CIRCUIT_BREAKER = "CIRCUIT_BREAKER"
    EXPIRATION = "EXPIRATION"


class TimeZoneType(str, Enum):
    """Intraday time-of-day bucketing for regime-aware parameters."""

    PRE_MARKET = "PRE_MARKET"
    OPENING_AUCTION = "OPENING_AUCTION"
    MORNING_SESSION = "MORNING_SESSION"
    MIDDAY_LULL = "MIDDAY_LULL"
    AFTERNOON_ACCEL = "AFTERNOON_ACCEL"
    POWER_HOUR = "POWER_HOUR"
    SETTLEMENT_WINDOW = "SETTLEMENT_WINDOW"


class GEXSignalType(str, Enum):
    """Categorisation of gamma-exposure driven signals."""

    GAMMA_FLIP_CROSSOVER = "GAMMA_FLIP_CROSSOVER"
    GAMMA_WALL_APPROACH = "GAMMA_WALL_APPROACH"
    TRANSITION_ZONE_BREAKOUT = "TRANSITION_ZONE_BREAKOUT"
    GEX_COLLAPSE = "GEX_COLLAPSE"
    CHARM_DRIVEN_FLOW = "CHARM_DRIVEN_FLOW"
    VANNA_AMPLIFICATION = "VANNA_AMPLIFICATION"


class OptionSide(str, Enum):
    """Option contract side."""

    CALL = "CALL"
    PUT = "PUT"


class PositionType(str, Enum):
    """Position structure for the trade."""

    SINGLE_LONG = "SINGLE_LONG"
    DEBIT_SPREAD = "DEBIT_SPREAD"
    CREDIT_SPREAD = "CREDIT_SPREAD"
    IRON_CONDOR = "IRON_CONDOR"


class ImpactLevel(str, Enum):
    """Severity level for economic calendar events."""

    LOW = "LOW"
    MED = "MED"
    HIGH = "HIGH"


class GapClassification(str, Enum):
    """Overnight gap size classification."""

    MICRO = "MICRO"
    SMALL = "SMALL"
    MEDIUM = "MEDIUM"
    LARGE = "LARGE"
    MEGA = "MEGA"


class LegSide(str, Enum):
    """Whether a spread leg is bought or sold."""

    BUY = "BUY"
    SELL = "SELL"


# =============================================================================
# 2. MARKET DATA MODELS
# =============================================================================


class OptionQuote(BaseModel):
    """Single option contract quote with full Greeks surface."""

    strike: float = Field(..., gt=0, description="Strike price")
    option_type: OptionSide = Field(..., description="CALL or PUT")
    bid: float = Field(..., ge=0, description="National best bid")
    ask: float = Field(..., ge=0, description="National best ask")
    mid: float = Field(..., ge=0, description="Mid-market price (bid+ask)/2")
    last: float = Field(..., ge=0, description="Last traded price")
    volume: int = Field(..., ge=0, description="Intraday contract volume")
    open_interest: int = Field(..., ge=0, description="Open interest")
    implied_vol: float = Field(
        ..., ge=0, description="Implied volatility (annualised, decimal)"
    )
    delta: float = Field(..., ge=-1.0, le=1.0, description="Option delta")
    gamma: float = Field(..., ge=0, description="Option gamma")
    theta: float = Field(..., le=0, description="Option theta (always <= 0)")
    vega: float = Field(..., ge=0, description="Option vega")
    charm: float = Field(0.0, description="Delta decay (dDelta/dTime)")
    vanna: float = Field(0.0, description="dDelta/dVol cross-greek")
    speed: float = Field(0.0, description="dGamma/dSpot third-order greek")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Quote capture time"
    )

    @field_validator("ask")
    @classmethod
    def ask_gte_bid(cls, v: float, info: Any) -> float:
        """Ask must be greater than or equal to bid."""
        bid = info.data.get("bid")
        if bid is not None and v < bid:
            raise ValueError(f"ask ({v}) must be >= bid ({bid})")
        return v

    @property
    def spread_width(self) -> float:
        """Bid-ask spread in dollar terms."""
        return self.ask - self.bid

    @property
    def spread_pct(self) -> float:
        """Spread as a percentage of mid.  Returns 0 when mid is zero."""
        return (self.spread_width / self.mid * 100.0) if self.mid > 0 else 0.0

    @property
    def is_liquid(self) -> bool:
        """Heuristic liquidity check: OI >= 100 and spread <= 25% of mid."""
        return self.open_interest >= 100 and self.spread_pct <= 25.0


class OptionsChain(BaseModel):
    """Full options chain for a single expiration date."""

    expiry_date: date = Field(..., description="Options expiration date")
    underlying_price: float = Field(
        ..., gt=0, description="Current SPX spot price"
    )
    quotes: list[OptionQuote] = Field(
        default_factory=list, description="All option quotes for this expiry"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Snapshot capture time"
    )

    @property
    def calls(self) -> list[OptionQuote]:
        """Filter to call contracts only."""
        return [q for q in self.quotes if q.option_type == OptionSide.CALL]

    @property
    def puts(self) -> list[OptionQuote]:
        """Filter to put contracts only."""
        return [q for q in self.quotes if q.option_type == OptionSide.PUT]

    @property
    def strikes(self) -> list[float]:
        """Sorted unique strikes available in this chain."""
        return sorted({q.strike for q in self.quotes})

    def get_by_strike(self, strike: float) -> list[OptionQuote]:
        """Return call and put quotes at the given strike."""
        return [q for q in self.quotes if q.strike == strike]

    def atm_strike(self) -> float:
        """Return the strike nearest to the current underlying price."""
        if not self.quotes:
            return self.underlying_price
        return min(self.strikes, key=lambda s: abs(s - self.underlying_price))


class MarketInternals(BaseModel):
    """NYSE breadth and ES futures microstructure snapshot."""

    nyse_tick: int = Field(..., description="NYSE TICK (instantaneous)")
    nyse_tick_10min_avg: float = Field(
        ..., description="10-minute rolling average of TICK"
    )
    cumulative_tick: float = Field(
        ..., description="Session cumulative TICK sum"
    )
    nyse_trin: float = Field(
        ..., gt=0, description="NYSE TRIN (Arms Index)"
    )
    advance_decline_ratio: float = Field(
        ..., ge=0, description="Advancers / Decliners ratio"
    )
    up_down_volume_ratio: float = Field(
        ..., ge=0, description="Up volume / Down volume ratio"
    )
    es_cumulative_delta: float = Field(
        ...,
        description="ES futures cumulative delta (buys minus sells) on the day",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Capture time"
    )

    @property
    def tick_is_extreme_bullish(self) -> bool:
        """TICK above +800 signals aggressive buying."""
        return self.nyse_tick >= 800

    @property
    def tick_is_extreme_bearish(self) -> bool:
        """TICK below -800 signals aggressive selling."""
        return self.nyse_tick <= -800

    @property
    def trin_bullish(self) -> bool:
        """TRIN below 0.80 suggests bullish breadth."""
        return self.nyse_trin < 0.80

    @property
    def trin_bearish(self) -> bool:
        """TRIN above 1.20 suggests bearish breadth."""
        return self.nyse_trin > 1.20


class CrossAssetData(BaseModel):
    """Cross-asset snapshot used for macro regime confirmation."""

    vix: float = Field(..., ge=0, description="CBOE VIX index")
    vix1d: float = Field(..., ge=0, description="CBOE VIX1D (1-day VIX)")
    vix9d: float = Field(..., ge=0, description="CBOE VIX9D (9-day VIX)")
    vix1d_intraday_avg: float = Field(
        ..., ge=0, description="VIX1D session rolling average"
    )
    us_10y_yield: float = Field(
        ..., description="US 10-year Treasury yield (%)"
    )
    us_10y_yield_change: float = Field(
        ..., description="Intraday change in 10Y yield (bps)"
    )
    dxy: float = Field(..., gt=0, description="US Dollar Index (DXY)")
    dxy_change: float = Field(..., description="Intraday DXY change (%)")
    es_price: float = Field(
        ..., gt=0, description="E-mini S&P 500 futures price"
    )
    es_volume: int = Field(..., ge=0, description="ES session volume")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Capture time"
    )

    @property
    def vix_term_structure_inverted(self) -> bool:
        """VIX1D > VIX indicates near-term fear spike."""
        return self.vix1d > self.vix

    @property
    def vix_regime(self) -> str:
        """Coarse VIX regime bucket."""
        if self.vix < 13:
            return "LOW"
        elif self.vix < 20:
            return "NORMAL"
        elif self.vix < 30:
            return "ELEVATED"
        return "EXTREME"


class ESOrderBook(BaseModel):
    """E-mini S&P 500 Level-II order book summary."""

    bid_levels: list[tuple[float, int]] = Field(
        ..., description="List of (price, size) bid levels"
    )
    ask_levels: list[tuple[float, int]] = Field(
        ..., description="List of (price, size) ask levels"
    )
    bid_total: int = Field(..., ge=0, description="Total bid depth")
    ask_total: int = Field(..., ge=0, description="Total ask depth")
    imbalance_ratio: float = Field(
        ...,
        description="(bid_total - ask_total) / (bid_total + ask_total); >0 is bid-heavy",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Capture time"
    )

    @field_validator("imbalance_ratio")
    @classmethod
    def clamp_imbalance(cls, v: float) -> float:
        """Imbalance ratio must stay within [-1, +1]."""
        return max(-1.0, min(1.0, v))

    @property
    def is_bid_heavy(self) -> bool:
        """Imbalance strongly favours bids."""
        return self.imbalance_ratio > 0.25

    @property
    def is_ask_heavy(self) -> bool:
        """Imbalance strongly favours asks."""
        return self.imbalance_ratio < -0.25


class EconomicEvent(BaseModel):
    """Single economic calendar event."""

    time: datetime = Field(..., description="Scheduled release time (ET)")
    name: str = Field(..., min_length=1, description="Event name")
    impact_level: ImpactLevel = Field(
        ..., description="LOW / MED / HIGH impact classification"
    )
    expected_value: Optional[str] = Field(
        None, description="Consensus forecast (string to handle mixed types)"
    )
    previous_value: Optional[str] = Field(
        None, description="Prior release value"
    )
    actual_value: Optional[str] = Field(
        None, description="Actual release value (None before release)"
    )

    @property
    def is_released(self) -> bool:
        """Whether the actual value has been published."""
        return self.actual_value is not None

    @property
    def is_high_impact(self) -> bool:
        """Convenience flag for HIGH-impact events."""
        return self.impact_level == ImpactLevel.HIGH


# =============================================================================
# 3. GEX MODELS
# =============================================================================


@dataclass
class StrikeGEX:
    """Per-strike gamma exposure decomposition.

    All gamma values are denominated in *SPX index points* of dealer
    hedging flow per 1-point move in spot.
    """

    strike: float
    call_gamma: float
    put_gamma: float
    call_oi: int
    put_oi: int
    dealer_gamma_call: float
    dealer_gamma_put: float
    net_gex: float
    net_charm: float
    net_vanna: float
    net_speed: float

    @property
    def total_oi(self) -> int:
        """Combined call + put open interest at this strike."""
        return self.call_oi + self.put_oi

    @property
    def dealer_net_gamma(self) -> float:
        """Net dealer gamma across calls and puts at this strike."""
        return self.dealer_gamma_call + self.dealer_gamma_put


class GEXProfile(BaseModel):
    """Full gamma exposure profile for the current expiry surface.

    Captures the complete dealer-positioning landscape used to derive
    support/resistance levels and hedging-flow forecasts.
    """

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Profile computation time"
    )
    strikes: list[StrikeGEX] = Field(
        default_factory=list, description="Per-strike GEX breakdown"
    )
    total_net_gex: float = Field(
        ..., description="Aggregate net GEX across all strikes"
    )
    gamma_flip_level: float = Field(
        ...,
        gt=0,
        description="Price where aggregate dealer gamma changes sign",
    )
    call_wall: float = Field(
        ...,
        gt=0,
        description="Strike with highest absolute call gamma (resistance)",
    )
    put_wall: float = Field(
        ...,
        gt=0,
        description="Strike with highest absolute put gamma (support)",
    )
    max_pain: float = Field(
        ..., gt=0, description="Strike that minimises aggregate OI pain"
    )
    plus_gex: float = Field(
        ..., gt=0, description="Strike with highest positive net GEX"
    )
    minus_gex: float = Field(
        ..., gt=0, description="Strike with highest negative (most negative) net GEX"
    )
    transition_zone_upper: float = Field(
        ...,
        gt=0,
        description="Upper bound of the positive-to-negative gamma transition zone",
    )
    transition_zone_lower: float = Field(
        ...,
        gt=0,
        description="Lower bound of the positive-to-negative gamma transition zone",
    )
    vol_trigger: float = Field(
        ...,
        gt=0,
        description="Price level above which dealer hedging dampens vol",
    )
    gex_momentum: float = Field(
        0.0,
        description="Rate of change in total net GEX (positive = strengthening)",
    )
    charm_net_es_contracts: float = Field(
        0.0,
        description="Net charm exposure expressed as equivalent ES contract flow",
    )
    vanna_net_exposure: float = Field(
        0.0,
        description="Net vanna exposure (delta sensitivity to vol)",
    )

    @property
    def is_positive_gamma_regime(self) -> bool:
        """Market is above the gamma flip -- dealer hedging dampens moves."""
        return self.total_net_gex > 0

    @property
    def transition_zone_width(self) -> float:
        """Width of the gamma transition zone in index points."""
        return self.transition_zone_upper - self.transition_zone_lower

    @model_validator(mode="after")
    def validate_transition_zone(self) -> "GEXProfile":
        """Ensure the transition zone bounds are correctly ordered."""
        if self.transition_zone_lower > self.transition_zone_upper:
            raise ValueError(
                "transition_zone_lower must be <= transition_zone_upper"
            )
        return self


class GEXSignal(BaseModel):
    """Actionable signal derived from a change in the GEX profile."""

    signal_type: GEXSignalType = Field(
        ..., description="Category of the GEX signal"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Signal generation time"
    )
    direction: TradeDirection = Field(
        ..., description="Implied directional bias"
    )
    confidence: float = Field(
        ...,
        ge=0,
        le=100,
        description="Signal confidence score (0-100)",
    )
    description: str = Field(
        ..., min_length=1, description="Human-readable signal narrative"
    )
    trigger_price: float = Field(
        ..., gt=0, description="SPX price that activated this signal"
    )
    target_price: Optional[float] = Field(
        None, gt=0, description="Expected magnet / target price (if any)"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary signal-specific payload",
    )

    @field_validator("confidence")
    @classmethod
    def round_confidence(cls, v: float) -> float:
        """Keep confidence to two decimal places."""
        return round(v, 2)


# =============================================================================
# 4. SCAN RESULT MODELS
# =============================================================================


class DirectionScore(BaseModel):
    """Composite directional scoring output from the five-factor model.

    ``total_score`` ranges from -100 (maximum bearish conviction) to
    +100 (maximum bullish conviction).  Individual sub-scores use the
    same scale and are combined via the current ``FactorWeights``.
    """

    total_score: float = Field(
        ...,
        ge=-100,
        le=100,
        description="Net composite direction score (-100 .. +100)",
    )
    market_internals_score: float = Field(
        ...,
        ge=-100,
        le=100,
        description="NYSE breadth / TICK / TRIN sub-score",
    )
    options_flow_score: float = Field(
        ...,
        ge=-100,
        le=100,
        description="Options flow and OI sub-score",
    )
    price_action_score: float = Field(
        ...,
        ge=-100,
        le=100,
        description="ES / SPX price-action sub-score",
    )
    gex_structure_score: float = Field(
        ...,
        ge=-100,
        le=100,
        description="Gamma exposure structure sub-score",
    )
    cross_asset_score: float = Field(
        ...,
        ge=-100,
        le=100,
        description="VIX / rates / DXY cross-asset sub-score",
    )
    factors_agreeing: int = Field(
        ...,
        ge=0,
        le=5,
        description="Number of sub-scores aligned with the total direction",
    )
    has_opposing_factor: bool = Field(
        ...,
        description="True when at least one factor contradicts the majority",
    )
    signal: TradeDirection = Field(
        ..., description="Discrete directional signal"
    )
    confidence: float = Field(
        ...,
        ge=0,
        le=100,
        description="Confidence in the signal (0-100)",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Scoring time"
    )

    @field_validator("confidence")
    @classmethod
    def round_confidence(cls, v: float) -> float:
        return round(v, 2)

    @property
    def is_high_conviction(self) -> bool:
        """Score magnitude >= 60 and at least 4/5 factors agree."""
        return abs(self.total_score) >= 60 and self.factors_agreeing >= 4

    @property
    def is_conflicted(self) -> bool:
        """Opposing factor present and net score below 30."""
        return self.has_opposing_factor and abs(self.total_score) < 30


class StrikeSelection(BaseModel):
    """Detailed evaluation of a candidate option strike for trade entry."""

    strike: float = Field(..., gt=0, description="Strike price")
    option_type: OptionSide = Field(..., description="CALL or PUT")
    delta: float = Field(
        ..., ge=-1.0, le=1.0, description="Current delta"
    )
    gamma: float = Field(..., ge=0, description="Current gamma")
    theta: float = Field(..., le=0, description="Current theta")
    iv: float = Field(
        ..., ge=0, description="Implied volatility (annualised decimal)"
    )
    bid: float = Field(..., ge=0, description="Best bid")
    ask: float = Field(..., ge=0, description="Best ask")
    mid: float = Field(..., ge=0, description="Mid price")
    spread_width: float = Field(
        ..., ge=0, description="Bid-ask spread in dollars"
    )
    oi: int = Field(..., ge=0, description="Open interest")
    volume: int = Field(..., ge=0, description="Intraday volume")
    is_liquid: bool = Field(
        ..., description="Passes minimum liquidity threshold"
    )
    distance_from_spot: float = Field(
        ..., description="Signed distance: strike - spot"
    )
    moneyness: float = Field(
        ...,
        description="strike / spot ratio (>1 OTM call, <1 OTM put)",
    )

    @property
    def is_otm(self) -> bool:
        """Check if strike is out-of-the-money relative to distance sign."""
        if self.option_type == OptionSide.CALL:
            return self.distance_from_spot > 0
        return self.distance_from_spot < 0

    @property
    def cost_per_point(self) -> float:
        """Approximate premium per point of intrinsic value sensitivity."""
        return self.mid / abs(self.delta) if abs(self.delta) > 0.01 else float("inf")


class ScanSignal(BaseModel):
    """Top-level output of a single scan pass -- the trade recommendation."""

    scan_type: ScanType = Field(
        ..., description="Strategy archetype"
    )
    direction: TradeDirection = Field(
        ..., description="Directional bias"
    )
    strike_selection: Optional[StrikeSelection] = Field(
        None, description="Selected strike detail (None for spread-only)"
    )
    direction_score: DirectionScore = Field(
        ..., description="Full composite directional breakdown"
    )
    entry_price: float = Field(
        ..., gt=0, description="Recommended entry price"
    )
    stop_loss: float = Field(
        ..., ge=0, description="Recommended stop-loss price"
    )
    profit_target: float = Field(
        ..., gt=0, description="Recommended profit-target price"
    )
    position_type: PositionType = Field(
        ..., description="Recommended position structure"
    )
    contracts: int = Field(
        ..., ge=1, description="Recommended number of contracts"
    )
    max_risk: float = Field(
        ..., ge=0, description="Maximum dollar risk for this position"
    )
    expected_reward: float = Field(
        ..., ge=0, description="Expected dollar reward at target"
    )
    risk_reward_ratio: float = Field(
        ..., gt=0, description="Reward / Risk ratio"
    )
    time_zone: TimeZoneType = Field(
        ..., description="Current intraday time-zone bucket"
    )
    session_type: SessionType = Field(
        ..., description="Detected session regime"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Signal generation time"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary scanner-specific payload",
    )

    @property
    def is_favorable_rr(self) -> bool:
        """Risk/reward of at least 1.5 is considered favourable."""
        return self.risk_reward_ratio >= 1.5

    @property
    def dollar_risk_per_contract(self) -> float:
        """Per-contract dollar risk."""
        return self.max_risk / self.contracts if self.contracts else 0.0


# =============================================================================
# 5. SPREAD MODELS
# =============================================================================


class SpreadLeg(BaseModel):
    """Individual leg of a multi-leg options spread."""

    strike: float = Field(..., gt=0, description="Strike price")
    option_type: OptionSide = Field(..., description="CALL or PUT")
    side: LegSide = Field(..., description="BUY or SELL")
    price: float = Field(..., ge=0, description="Fill price of this leg")
    delta: float = Field(
        ..., ge=-1.0, le=1.0, description="Leg delta"
    )
    gamma: float = Field(..., ge=0, description="Leg gamma")
    theta: float = Field(..., le=0, description="Leg theta")

    @property
    def is_short(self) -> bool:
        """True if this leg is sold."""
        return self.side == LegSide.SELL


class CreditSpread(BaseModel):
    """Vertical credit spread (bull put or bear call)."""

    short_leg: SpreadLeg = Field(..., description="Short (sold) leg")
    long_leg: SpreadLeg = Field(..., description="Long (bought / hedge) leg")
    credit_received: float = Field(
        ..., gt=0, description="Net credit collected"
    )
    max_loss: float = Field(
        ..., gt=0, description="Maximum potential loss (width - credit)"
    )
    width: float = Field(
        ..., gt=0, description="Spread width in strike points"
    )
    probability_otm: float = Field(
        ...,
        ge=0,
        le=1.0,
        description="Probability both legs expire OTM (0-1)",
    )
    break_even: float = Field(
        ..., gt=0, description="Break-even price at expiration"
    )

    @model_validator(mode="after")
    def validate_legs(self) -> "CreditSpread":
        """Short and long legs must share the same option type."""
        if self.short_leg.option_type != self.long_leg.option_type:
            raise ValueError(
                "Both legs of a credit spread must be the same option type"
            )
        if self.short_leg.side != LegSide.SELL:
            raise ValueError("short_leg must have side=SELL")
        if self.long_leg.side != LegSide.BUY:
            raise ValueError("long_leg must have side=BUY")
        return self

    @property
    def risk_reward_ratio(self) -> float:
        """Reward (credit) to risk (max loss) ratio."""
        return self.credit_received / self.max_loss if self.max_loss else 0.0

    @property
    def return_on_risk(self) -> float:
        """Credit as a percentage of max loss."""
        return (self.credit_received / self.max_loss * 100.0) if self.max_loss else 0.0


class IronCondor(BaseModel):
    """Iron condor composed of a put credit spread and a call credit spread."""

    put_spread: CreditSpread = Field(
        ..., description="Bull put credit spread (lower strikes)"
    )
    call_spread: CreditSpread = Field(
        ..., description="Bear call credit spread (upper strikes)"
    )
    total_credit: float = Field(
        ..., gt=0, description="Combined net credit"
    )
    max_loss: float = Field(
        ..., gt=0, description="Maximum loss (wider wing width - total credit)"
    )
    break_even_lower: float = Field(
        ..., gt=0, description="Lower break-even price"
    )
    break_even_upper: float = Field(
        ..., gt=0, description="Upper break-even price"
    )
    probability_profit: float = Field(
        ...,
        ge=0,
        le=1.0,
        description="Probability of any profit at expiry (0-1)",
    )

    @model_validator(mode="after")
    def validate_structure(self) -> "IronCondor":
        """Put spread strikes must sit below call spread strikes."""
        if self.put_spread.short_leg.strike >= self.call_spread.short_leg.strike:
            raise ValueError(
                "Put spread short strike must be below call spread short strike"
            )
        if self.break_even_lower >= self.break_even_upper:
            raise ValueError(
                "break_even_lower must be less than break_even_upper"
            )
        return self

    @property
    def profit_zone_width(self) -> float:
        """Distance between the two break-even points."""
        return self.break_even_upper - self.break_even_lower

    @property
    def return_on_risk(self) -> float:
        """Total credit as a percentage of max loss."""
        return (self.total_credit / self.max_loss * 100.0) if self.max_loss else 0.0


# =============================================================================
# 6. TRADE LOG MODEL
# =============================================================================


class TradeLog(BaseModel):
    """Complete post-trade record for performance analytics and calibration.

    Every field in this model corresponds to a column in the persistent
    trade journal.  Nullable fields are populated asynchronously as
    counterfactual analysis completes.
    """

    trade_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique trade identifier (UUID4)",
    )

    # -- Timestamps -----------------------------------------------------------
    timestamp_entry: datetime = Field(
        ..., description="Position entry timestamp"
    )
    timestamp_exit: Optional[datetime] = Field(
        None, description="Position exit timestamp (None if still open)"
    )

    # -- Trade parameters -----------------------------------------------------
    scan_type: ScanType = Field(..., description="Strategy archetype")
    direction: TradeDirection = Field(
        ..., description="BULL / BEAR / NEUTRAL"
    )
    strike: float = Field(..., gt=0, description="Executed strike")
    option_type: OptionSide = Field(..., description="CALL or PUT")
    entry_price: float = Field(
        ..., gt=0, description="Fill price at entry"
    )
    exit_price: Optional[float] = Field(
        None, ge=0, description="Fill price at exit"
    )

    # -- PnL tracking --------------------------------------------------------
    max_gain_during_trade: float = Field(
        0.0, description="Peak unrealised gain ($)"
    )
    max_loss_during_trade: float = Field(
        0.0, description="Trough unrealised loss ($, negative)"
    )
    pnl_dollars: Optional[float] = Field(
        None, description="Realised PnL in dollars"
    )
    pnl_percent: Optional[float] = Field(
        None, description="Realised PnL as percentage of entry"
    )
    hold_time_minutes: Optional[float] = Field(
        None, ge=0, description="Duration the position was held"
    )

    # -- Market context at entry ----------------------------------------------
    spx_at_entry: float = Field(
        ..., gt=0, description="SPX spot at entry"
    )
    vix1d_at_entry: float = Field(
        ..., ge=0, description="VIX1D at entry"
    )
    vix_at_entry: float = Field(
        ..., ge=0, description="VIX at entry"
    )
    expected_move_1sigma: float = Field(
        ..., ge=0, description="1-sigma expected move (points)"
    )
    composite_direction_score: float = Field(
        ...,
        ge=-100,
        le=100,
        description="DirectionScore.total_score at entry",
    )
    session_type: SessionType = Field(
        ..., description="Detected session regime at entry"
    )
    net_gex_at_entry: float = Field(
        ..., description="Total net GEX at entry"
    )
    gamma_flip_at_entry: float = Field(
        ..., gt=0, description="Gamma flip level at entry"
    )
    time_zone: TimeZoneType = Field(
        ..., description="Intraday time-zone bucket at entry"
    )

    # -- Greeks at entry ------------------------------------------------------
    delta_at_entry: float = Field(
        ..., ge=-1.0, le=1.0, description="Option delta at entry"
    )
    gamma_at_entry: float = Field(
        ..., ge=0, description="Option gamma at entry"
    )
    theta_at_entry: float = Field(
        ..., le=0, description="Option theta at entry"
    )
    iv_at_entry: float = Field(
        ..., ge=0, description="Implied vol at entry"
    )

    # -- Internals at entry ---------------------------------------------------
    tick_10min_avg: float = Field(
        ..., description="10-min TICK average at entry"
    )
    trin_at_entry: float = Field(
        ..., gt=0, description="NYSE TRIN at entry"
    )
    ad_ratio_at_entry: float = Field(
        ..., ge=0, description="Advance/Decline ratio at entry"
    )
    cumulative_delta_es: float = Field(
        ..., description="ES cumulative delta at entry"
    )

    # -- Exit analysis --------------------------------------------------------
    exit_reason: Optional[ExitReason] = Field(
        None, description="Why the trade was closed"
    )
    optimal_exit_price: Optional[float] = Field(
        None,
        ge=0,
        description="Best obtainable exit price (hindsight)",
    )
    optimal_exit_time: Optional[datetime] = Field(
        None,
        description="Timestamp of the optimal exit (hindsight)",
    )
    left_on_table_pct: Optional[float] = Field(
        None,
        ge=0,
        description="Percentage of max gain not captured",
    )
    was_stopped_prematurely: Optional[bool] = Field(
        None,
        description="True if the stop triggered before the eventual target was hit",
    )
    counterfactual_notes: Optional[str] = Field(
        None,
        description="Free-form notes from the counterfactual engine",
    )

    @property
    def is_winner(self) -> bool:
        """True when realised PnL is positive."""
        return self.pnl_dollars is not None and self.pnl_dollars > 0

    @property
    def is_open(self) -> bool:
        """Trade has not been exited yet."""
        return self.timestamp_exit is None

    @property
    def edge_ratio(self) -> Optional[float]:
        """max_gain / abs(max_loss) during the trade.  None if no drawdown."""
        if self.max_loss_during_trade == 0:
            return None
        return self.max_gain_during_trade / abs(self.max_loss_during_trade)


# =============================================================================
# 7. CALIBRATION MODELS
# =============================================================================


class DailyScoreCard(BaseModel):
    """End-of-day performance summary sliced across multiple dimensions."""

    trading_date: date = Field(..., description="Trading date", alias="date")
    total_trades: int = Field(0, description="Total trades for the day")
    win_rate_by_scan_type: dict[str, float] = Field(
        default_factory=dict,
        description="Win rate keyed by ScanType value",
    )
    win_rate_by_time_zone: dict[str, float] = Field(
        default_factory=dict,
        description="Win rate keyed by TimeZoneType value",
    )
    win_rate_by_session_type: dict[str, float] = Field(
        default_factory=dict,
        description="Win rate keyed by SessionType value",
    )
    win_rate_by_vix1d_regime: dict[str, float] = Field(
        default_factory=dict,
        description="Win rate keyed by VIX1D regime label",
    )
    avg_pnl_by_scan_type: dict[str, float] = Field(
        default_factory=dict,
        description="Average PnL ($) keyed by ScanType value",
    )
    avg_pnl_by_time_zone: dict[str, float] = Field(
        default_factory=dict,
        description="Average PnL ($) keyed by TimeZoneType value",
    )
    avg_pnl_by_session_type: dict[str, float] = Field(
        default_factory=dict,
        description="Average PnL ($) keyed by SessionType value",
    )
    avg_pnl_by_vix1d_regime: dict[str, float] = Field(
        default_factory=dict,
        description="Average PnL ($) keyed by VIX1D regime label",
    )
    sharpe_by_scan_type: dict[str, float] = Field(
        default_factory=dict,
        description="Intraday Sharpe ratio keyed by ScanType value",
    )
    max_drawdown_by_scan_type: dict[str, float] = Field(
        default_factory=dict,
        description="Maximum drawdown ($) keyed by ScanType value",
    )

    model_config = ConfigDict(populate_by_name=True)


class FactorWeights(BaseModel):
    """Weights for the five sub-models in the composite direction scorer.

    The five weights must always sum to exactly 1.0 (within floating-point
    tolerance).
    """

    market_internals: float = Field(
        ..., ge=0, le=1.0, description="Weight for NYSE breadth factor"
    )
    options_flow: float = Field(
        ..., ge=0, le=1.0, description="Weight for options flow factor"
    )
    price_action: float = Field(
        ..., ge=0, le=1.0, description="Weight for price-action factor"
    )
    gex_structure: float = Field(
        ..., ge=0, le=1.0, description="Weight for GEX structure factor"
    )
    cross_asset: float = Field(
        ..., ge=0, le=1.0, description="Weight for cross-asset factor"
    )

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> "FactorWeights":
        """Ensure all five weights sum to 1.0 within tolerance."""
        total = (
            self.market_internals
            + self.options_flow
            + self.price_action
            + self.gex_structure
            + self.cross_asset
        )
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"Factor weights must sum to 1.0, got {total:.8f}"
            )
        return self

    def as_dict(self) -> dict[str, float]:
        """Return weights as a plain dictionary."""
        return {
            "market_internals": self.market_internals,
            "options_flow": self.options_flow,
            "price_action": self.price_action,
            "gex_structure": self.gex_structure,
            "cross_asset": self.cross_asset,
        }


class CalibrationState(BaseModel):
    """Persistent calibration state consumed by the live scanner.

    Updated nightly by the self-learning / auto-calibration pipeline.
    """

    current_weights: FactorWeights = Field(
        ..., description="Active factor weights for direction scoring"
    )
    entry_threshold: float = Field(
        ...,
        ge=0,
        le=100,
        description="Minimum composite score magnitude to trigger a trade",
    )
    profit_targets_by_zone: dict[str, float] = Field(
        default_factory=dict,
        description="Profit target (%) keyed by TimeZoneType value",
    )
    stop_loss_pct: float = Field(
        ...,
        gt=0,
        le=100,
        description="Default stop-loss percentage from entry",
    )
    regime: str = Field(
        ..., min_length=1, description="Current detected VIX / vol regime label"
    )
    last_calibration: datetime = Field(
        ..., description="Timestamp of the most recent calibration run"
    )
    trade_count: int = Field(
        ..., ge=0, description="Cumulative trades since last calibration"
    )
    gex_signal_accuracy: float = Field(
        ...,
        ge=0,
        le=1.0,
        description="Rolling accuracy of GEX-driven signals (0-1)",
    )


# =============================================================================
# 8. PRE-MARKET MODELS
# =============================================================================


class GapAnalysis(BaseModel):
    """Overnight gap characterisation computed during pre-market."""

    gap_pct: float = Field(..., description="Gap size as percentage of prior close")
    gap_points: float = Field(..., description="Gap size in SPX index points")
    gap_sigma: float = Field(
        ...,
        description="Gap normalised by the expected move (sigma units)",
    )
    classification: GapClassification = Field(
        ..., description="MICRO / SMALL / MEDIUM / LARGE / MEGA"
    )
    gap_fill_probability: dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Probability of gap fill keyed by intraday time horizon "
            "(e.g. '30min', '60min', '120min', 'eod')"
        ),
    )

    @property
    def is_gap_up(self) -> bool:
        """Positive gap (open above prior close)."""
        return self.gap_points > 0

    @property
    def is_gap_down(self) -> bool:
        """Negative gap (open below prior close)."""
        return self.gap_points < 0

    @property
    def is_large_gap(self) -> bool:
        """Gap exceeds 1 sigma of the expected move."""
        return abs(self.gap_sigma) > 1.0


class ExpectedMove(BaseModel):
    """Implied and realised-vol derived expected move for the session.

    Three independent methods produce an estimate; the ``final_*`` fields
    are the blended consensus.
    """

    method1_vix1d: float = Field(
        ..., ge=0, description="Expected move from VIX1D (annualised -> daily)"
    )
    method2_straddle: float = Field(
        ..., ge=0, description="Expected move from ATM straddle price"
    )
    method3_rv_adjusted: float = Field(
        ...,
        ge=0,
        description="Expected move from recent realised vol (5-day)",
    )
    final_1sigma: float = Field(
        ..., ge=0, description="Blended 1-sigma expected move (points)"
    )
    final_2sigma: float = Field(
        ..., ge=0, description="Blended 2-sigma expected move (points)"
    )
    iv_rv_ratio: float = Field(
        ...,
        gt=0,
        description="Implied vol / Realised vol ratio (>1 = IV premium)",
    )
    vol_regime: str = Field(
        ...,
        min_length=1,
        description="Descriptive vol regime (e.g. LOW, NORMAL, ELEVATED, EXTREME)",
    )

    @property
    def has_significant_iv_premium(self) -> bool:
        """IV meaningfully exceeds recent realised vol."""
        return self.iv_rv_ratio > 1.25

    @property
    def is_vol_compressed(self) -> bool:
        """Realised vol exceeds implied -- potential squeeze."""
        return self.iv_rv_ratio < 0.85


class KeyLevels(BaseModel):
    """Consolidated key price levels for the trading session.

    Merges GEX-derived levels, prior-session reference prices, and
    technically significant levels into a single lookup.
    """

    # -- GEX-derived levels ---------------------------------------------------
    max_pain: float = Field(..., gt=0, description="Max pain strike")
    plus_gex: float = Field(
        ..., gt=0, description="Highest positive net GEX strike"
    )
    minus_gex: float = Field(
        ..., gt=0, description="Most negative net GEX strike"
    )
    call_wall: float = Field(
        ..., gt=0, description="Strike with largest call gamma"
    )
    put_wall: float = Field(
        ..., gt=0, description="Strike with largest put gamma"
    )
    gamma_flip: float = Field(
        ..., gt=0, description="Gamma flip / zero-gamma crossover level"
    )
    vol_trigger: float = Field(
        ..., gt=0, description="Vol trigger level"
    )
    transition_zone_upper: float = Field(
        ..., gt=0, description="Upper transition zone bound"
    )
    transition_zone_lower: float = Field(
        ..., gt=0, description="Lower transition zone bound"
    )

    # -- Prior-session reference prices ---------------------------------------
    prior_high: float = Field(..., gt=0, description="Prior session high")
    prior_low: float = Field(..., gt=0, description="Prior session low")
    prior_close: float = Field(..., gt=0, description="Prior session close")
    prior_vwap: float = Field(
        ..., gt=0, description="Prior session VWAP"
    )

    # -- Overnight / globex reference -----------------------------------------
    overnight_high: float = Field(
        ..., gt=0, description="Globex / overnight session high"
    )
    overnight_low: float = Field(
        ..., gt=0, description="Globex / overnight session low"
    )

    # -- Technical levels -----------------------------------------------------
    round_levels: list[float] = Field(
        default_factory=list,
        description="Psychologically significant round numbers nearby",
    )
    moving_averages: dict[str, float] = Field(
        default_factory=dict,
        description="Key moving averages, e.g. {'SMA_20': 5210.5, 'EMA_9': 5215.0}",
    )

    @property
    def prior_range(self) -> float:
        """Prior session high-low range in points."""
        return self.prior_high - self.prior_low

    @property
    def overnight_range(self) -> float:
        """Overnight session high-low range in points."""
        return self.overnight_high - self.overnight_low

    def all_levels_sorted(self) -> list[float]:
        """Return every tracked level as a flat sorted list (deduped)."""
        levels = {
            self.max_pain,
            self.plus_gex,
            self.minus_gex,
            self.call_wall,
            self.put_wall,
            self.gamma_flip,
            self.vol_trigger,
            self.transition_zone_upper,
            self.transition_zone_lower,
            self.prior_high,
            self.prior_low,
            self.prior_close,
            self.prior_vwap,
            self.overnight_high,
            self.overnight_low,
        }
        levels.update(self.round_levels)
        levels.update(self.moving_averages.values())
        return sorted(levels)


class SessionSetup(BaseModel):
    """Aggregated pre-market analysis consumed by the live scanner at open.

    Produced by the pre-market pipeline and frozen for the trading day.
    """

    gap_analysis: GapAnalysis = Field(
        ..., description="Overnight gap characterisation"
    )
    expected_move: ExpectedMove = Field(
        ..., description="Session expected-move estimates"
    )
    key_levels: KeyLevels = Field(
        ..., description="Consolidated key levels for the session"
    )
    session_type: SessionType = Field(
        ..., description="Predicted session regime"
    )
    economic_events: list[EconomicEvent] = Field(
        default_factory=list,
        description="Today's economic calendar events",
    )
    risk_assessment: str = Field(
        ...,
        min_length=1,
        description="Free-form pre-market risk commentary",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Time this setup was generated",
    )

    @property
    def has_high_impact_events(self) -> bool:
        """True when at least one HIGH-impact event is on the calendar."""
        return any(e.is_high_impact for e in self.economic_events)

    @property
    def high_impact_event_count(self) -> int:
        """Number of HIGH-impact events scheduled today."""
        return sum(1 for e in self.economic_events if e.is_high_impact)

    @property
    def is_event_day(self) -> bool:
        """Session should be treated as an event day."""
        return self.session_type == SessionType.EVENT or self.has_high_impact_events
