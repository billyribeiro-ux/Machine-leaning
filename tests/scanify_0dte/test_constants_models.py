"""
Comprehensive tests for SCANIFY 0DTE SPX Scanner constants and models modules.

Covers:
  - SPX contract specifications
  - Intraday time zone definitions and ordering
  - Greeks behaviour constants (gamma, theta, delta)
  - VIX1D regime thresholds and ordering
  - Direction score thresholds
  - Factor weight defaults and validation
  - Strike selection constants
  - Exit management constants
  - Premium selling constants
  - GEX scanner constants
  - Self-learning constants
  - Risk management constants
  - All Pydantic / dataclass models: enums, validators, properties, edge cases
"""

from __future__ import annotations

import math
import uuid
from datetime import date, datetime, time
from typing import Any

import pytest
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Constants imports
# ---------------------------------------------------------------------------
from src.scanify_0dte.constants import (
    CALENDAR_DAYS_PER_YEAR,
    DEFAULT_FACTOR_WEIGHTS,
    DELTA_DECAY,
    DIRECTION_THRESHOLDS,
    EXIT_MANAGEMENT,
    GAMMA_RANGES,
    GEX_SCANNER,
    INTRADAY_ZONE_SCHEDULE,
    PREMIUM_SELLING,
    RISK_MANAGEMENT,
    SELF_LEARNING,
    SPX_CONTRACT,
    STRIKE_SELECTION,
    THETA_DECAY_CURVE,
    TRADING_DAYS_PER_YEAR,
    TRADING_MINUTES_PER_DAY,
    TRADING_SECONDS_PER_DAY,
    VIX1D,
    VIX1D_REGIME_THRESHOLDS,
    ZONE_BOUNDARIES,
    ContractSpec,
    DeltaDecayConstants,
    DeltaRange,
    DirectionFactor,
    DirectionScoreThresholds,
    ExitManagementConstants,
    FactorWeightDefaults,
    GEXScannerConstants,
    GammaRangeSnapshot,
    IntradayZone,
    PremiumSellingConstants,
    ProfitTargetByZone,
    RiskManagementConstants,
    SelfLearningConstants,
    StrikeSelectionConstants,
    ThetaDecayPoint,
    TimeZoneBoundary,
    VIX1DConstants,
    VIX1DRegime,
    VIX1DRegimeThreshold,
)

# ---------------------------------------------------------------------------
# Models imports
# ---------------------------------------------------------------------------
from src.scanify_0dte.models import (
    CalibrationState,
    CreditSpread,
    CrossAssetData,
    DirectionScore,
    EconomicEvent,
    ESOrderBook,
    ExitReason,
    ExpectedMove,
    FactorWeights,
    GapAnalysis,
    GapClassification,
    GEXProfile,
    GEXSignal,
    GEXSignalType,
    ImpactLevel,
    IronCondor,
    KeyLevels,
    LegSide,
    MarketInternals,
    OptionQuote,
    OptionSide,
    OptionsChain,
    PositionType,
    ScanSignal,
    ScanType,
    SessionSetup,
    SessionType,
    SpreadLeg,
    StrikeGEX,
    StrikeSelection,
    TimeZoneType,
    TradeDirection,
    TradeLog,
)


# ============================================================================
#  HELPERS / FIXTURES
# ============================================================================


def _make_option_quote(**overrides: Any) -> OptionQuote:
    """Build a valid OptionQuote with sensible defaults, allowing field overrides."""
    defaults: dict[str, Any] = dict(
        strike=5200.0,
        option_type=OptionSide.CALL,
        bid=3.50,
        ask=3.80,
        mid=3.65,
        last=3.70,
        volume=1500,
        open_interest=8000,
        implied_vol=0.18,
        delta=0.35,
        gamma=0.12,
        theta=-0.45,
        vega=0.08,
    )
    defaults.update(overrides)
    return OptionQuote(**defaults)


def _make_spread_leg(
    strike: float = 5200.0,
    option_type: OptionSide = OptionSide.PUT,
    side: LegSide = LegSide.SELL,
    price: float = 2.50,
    delta: float = -0.30,
    gamma: float = 0.10,
    theta: float = -0.35,
) -> SpreadLeg:
    """Build a valid SpreadLeg."""
    return SpreadLeg(
        strike=strike,
        option_type=option_type,
        side=side,
        price=price,
        delta=delta,
        gamma=gamma,
        theta=theta,
    )


def _make_credit_spread(**overrides: Any) -> CreditSpread:
    """Build a valid CreditSpread with sensible defaults."""
    defaults: dict[str, Any] = dict(
        short_leg=_make_spread_leg(
            strike=5200.0, option_type=OptionSide.PUT, side=LegSide.SELL,
            price=2.50, delta=-0.30, gamma=0.10, theta=-0.35,
        ),
        long_leg=_make_spread_leg(
            strike=5190.0, option_type=OptionSide.PUT, side=LegSide.BUY,
            price=1.20, delta=-0.20, gamma=0.08, theta=-0.25,
        ),
        credit_received=1.30,
        max_loss=8.70,
        width=10.0,
        probability_otm=0.78,
        break_even=5198.70,
    )
    defaults.update(overrides)
    return CreditSpread(**defaults)


def _make_direction_score(**overrides: Any) -> DirectionScore:
    """Build a valid DirectionScore with sensible defaults."""
    defaults: dict[str, Any] = dict(
        total_score=55.0,
        market_internals_score=60.0,
        options_flow_score=50.0,
        price_action_score=55.0,
        gex_structure_score=40.0,
        cross_asset_score=45.0,
        factors_agreeing=5,
        has_opposing_factor=False,
        signal=TradeDirection.BULL,
        confidence=72.5,
    )
    defaults.update(overrides)
    return DirectionScore(**defaults)


def _make_key_levels(**overrides: Any) -> KeyLevels:
    """Build a valid KeyLevels instance."""
    defaults: dict[str, Any] = dict(
        max_pain=5200.0,
        plus_gex=5220.0,
        minus_gex=5170.0,
        call_wall=5250.0,
        put_wall=5150.0,
        gamma_flip=5205.0,
        vol_trigger=5230.0,
        transition_zone_upper=5215.0,
        transition_zone_lower=5195.0,
        prior_high=5240.0,
        prior_low=5160.0,
        prior_close=5210.0,
        prior_vwap=5205.0,
        overnight_high=5225.0,
        overnight_low=5185.0,
    )
    defaults.update(overrides)
    return KeyLevels(**defaults)


# ============================================================================
#  PART 1 -- CONSTANTS TESTS
# ============================================================================


class TestContractSpec:
    """Tests for the SPX 0DTE contract specification constants."""

    def test_symbol_is_spxw(self) -> None:
        """Contract symbol must be SPXW (SPX Weeklys)."""
        assert SPX_CONTRACT.symbol == "SPXW"

    def test_underlying_ticker_is_spx(self) -> None:
        """Underlying ticker must be SPX."""
        assert SPX_CONTRACT.underlying_ticker == "SPX"

    def test_settlement_type_is_pm(self) -> None:
        """SPX 0DTE weeklys use PM settlement."""
        assert SPX_CONTRACT.settlement_type == "PM"

    def test_exercise_style_is_european(self) -> None:
        """SPX options are European-style (no early exercise)."""
        assert SPX_CONTRACT.exercise_style == "European"

    def test_cash_settled(self) -> None:
        """SPX options are cash-settled."""
        assert SPX_CONTRACT.cash_settled is True

    def test_daily_expiration_enabled(self) -> None:
        """0DTE requires daily expiration support."""
        assert SPX_CONTRACT.daily_expiration is True

    def test_expiration_days_covers_full_week(self) -> None:
        """Must have all five weekdays for 0DTE availability."""
        assert len(SPX_CONTRACT.expiration_days) == 5
        expected = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday"}
        assert set(SPX_CONTRACT.expiration_days) == expected

    def test_market_open_is_930(self) -> None:
        """Market open must be 9:30 AM ET."""
        assert SPX_CONTRACT.market_open == time(9, 30)

    def test_market_close_is_415(self) -> None:
        """SPX options can trade until 4:15 PM ET."""
        assert SPX_CONTRACT.market_close == time(16, 15)

    def test_settlement_time_is_400(self) -> None:
        """Settlement (SOQ) is at 4:00 PM ET."""
        assert SPX_CONTRACT.settlement_time == time(16, 0)

    def test_tick_size_below_3(self) -> None:
        """Tick size for options priced below $3 is $0.05."""
        assert SPX_CONTRACT.tick_size_below_3 == 0.05

    def test_tick_size_at_or_above_3(self) -> None:
        """Tick size for options priced >= $3 is $0.10."""
        assert SPX_CONTRACT.tick_size_at_or_above_3 == 0.10

    def test_tick_price_boundary(self) -> None:
        """Tick boundary is at $3.00."""
        assert SPX_CONTRACT.tick_price_boundary == 3.00

    def test_multiplier_is_100(self) -> None:
        """SPX contract multiplier is $100."""
        assert SPX_CONTRACT.multiplier == 100.0

    def test_strike_interval_near_atm(self) -> None:
        """Near-ATM strike interval is $5."""
        assert SPX_CONTRACT.strike_interval_near_atm == 5

    def test_strike_interval_far_otm(self) -> None:
        """Far OTM strike interval is $25."""
        assert SPX_CONTRACT.strike_interval_far_otm == 25

    def test_far_otm_threshold_points(self) -> None:
        """Far OTM threshold is 100 points from ATM."""
        assert SPX_CONTRACT.far_otm_threshold_points == 100

    def test_contract_spec_is_frozen(self) -> None:
        """ContractSpec should be immutable (frozen dataclass)."""
        with pytest.raises(AttributeError):
            SPX_CONTRACT.symbol = "XYZ"  # type: ignore[misc]


class TestIntradayZones:
    """Tests for intraday time zone definitions and schedule."""

    def test_zone_count(self) -> None:
        """There must be exactly 7 intraday zones."""
        assert len(IntradayZone) == 7

    def test_zone_ordering(self) -> None:
        """Zone numeric values must be strictly increasing from PRE_MARKET to SETTLEMENT_WINDOW."""
        zones = list(IntradayZone)
        for i in range(len(zones) - 1):
            assert zones[i].value < zones[i + 1].value, (
                f"{zones[i].name} ({zones[i].value}) should be < "
                f"{zones[i + 1].name} ({zones[i + 1].value})"
            )

    def test_schedule_has_all_zones(self) -> None:
        """INTRADAY_ZONE_SCHEDULE must include all 7 zones."""
        assert len(INTRADAY_ZONE_SCHEDULE) == 7

    def test_schedule_boundaries_are_contiguous(self) -> None:
        """Each zone's end time must equal the next zone's start time."""
        for i in range(len(INTRADAY_ZONE_SCHEDULE) - 1):
            current = INTRADAY_ZONE_SCHEDULE[i]
            nxt = INTRADAY_ZONE_SCHEDULE[i + 1]
            assert current.end == nxt.start, (
                f"{current.zone.name} ends at {current.end}, "
                f"but {nxt.zone.name} starts at {nxt.start}"
            )

    def test_schedule_start_end_valid(self) -> None:
        """Each zone must have start strictly before end."""
        for tz in INTRADAY_ZONE_SCHEDULE:
            assert tz.start < tz.end, (
                f"{tz.zone.name}: start {tz.start} must be before end {tz.end}"
            )

    def test_schedule_descriptions_non_empty(self) -> None:
        """Every zone must have a non-empty description string."""
        for tz in INTRADAY_ZONE_SCHEDULE:
            assert len(tz.description) > 0, (
                f"{tz.zone.name} has an empty description"
            )

    def test_zone_boundaries_lookup_complete(self) -> None:
        """ZONE_BOUNDARIES must contain an entry for every IntradayZone."""
        for zone in IntradayZone:
            assert zone in ZONE_BOUNDARIES, f"Missing boundary for {zone.name}"

    def test_pre_market_starts_at_7am(self) -> None:
        """Pre-market zone starts at 7:00 AM ET."""
        assert ZONE_BOUNDARIES[IntradayZone.PRE_MARKET].start == time(7, 0)

    def test_settlement_window_ends_at_4pm(self) -> None:
        """Settlement window ends at 4:00 PM ET."""
        assert ZONE_BOUNDARIES[IntradayZone.SETTLEMENT_WINDOW].end == time(16, 0)


class TestGreeksBehaviourConstants:
    """Tests for trading-time and Greeks-related constants."""

    def test_trading_minutes_per_day(self) -> None:
        """Regular session is 390 minutes (9:30-4:00)."""
        assert TRADING_MINUTES_PER_DAY == 390

    def test_trading_seconds_per_day(self) -> None:
        """Seconds must be minutes * 60."""
        assert TRADING_SECONDS_PER_DAY == TRADING_MINUTES_PER_DAY * 60

    def test_calendar_days_per_year(self) -> None:
        """Calendar days per year is 365.25 (accounting for leap years)."""
        assert CALENDAR_DAYS_PER_YEAR == 365.25

    def test_trading_days_per_year(self) -> None:
        """Standard 252 trading days per year."""
        assert TRADING_DAYS_PER_YEAR == 252.0

    def test_gamma_ranges_non_empty(self) -> None:
        """GAMMA_RANGES must be populated."""
        assert len(GAMMA_RANGES) >= 3

    def test_gamma_ranges_low_lt_high(self) -> None:
        """For each gamma snapshot, low must be less than high."""
        for snap in GAMMA_RANGES:
            assert snap.atm_gamma_low < snap.atm_gamma_high, (
                f"{snap.label}: low ({snap.atm_gamma_low}) >= high ({snap.atm_gamma_high})"
            )

    def test_gamma_ranges_increase_over_day(self) -> None:
        """Gamma ranges should generally increase as we approach expiry."""
        for i in range(len(GAMMA_RANGES) - 1):
            assert GAMMA_RANGES[i].atm_gamma_high <= GAMMA_RANGES[i + 1].atm_gamma_high, (
                f"Gamma high should increase: {GAMMA_RANGES[i].label} to {GAMMA_RANGES[i + 1].label}"
            )

    def test_theta_decay_curve_cumulative_monotonic(self) -> None:
        """Cumulative theta decay must be monotonically increasing."""
        for i in range(len(THETA_DECAY_CURVE) - 1):
            assert THETA_DECAY_CURVE[i].cumulative_decay_pct < THETA_DECAY_CURVE[i + 1].cumulative_decay_pct

    def test_theta_decay_curve_reaches_100(self) -> None:
        """Cumulative theta decay must reach 100% at settlement."""
        assert THETA_DECAY_CURVE[-1].cumulative_decay_pct == 100.0

    def test_theta_decay_marginal_sums_to_100(self) -> None:
        """Marginal decay percentages must sum to 100%."""
        total_marginal = sum(td.marginal_decay_pct for td in THETA_DECAY_CURVE)
        assert abs(total_marginal - 100.0) < 1e-9

    def test_theta_decay_marginal_positive(self) -> None:
        """All marginal theta decay values must be positive."""
        for td in THETA_DECAY_CURVE:
            assert td.marginal_decay_pct > 0, (
                f"Zone {td.zone.name} marginal decay must be > 0"
            )

    def test_delta_decay_min_tte_positive(self) -> None:
        """Minimum TTE in years must be a small positive value to prevent division by zero."""
        assert DELTA_DECAY.min_tte_years > 0

    def test_delta_decay_deep_itm_gt_deep_otm(self) -> None:
        """Deep ITM delta must be greater than deep OTM delta."""
        assert DELTA_DECAY.deep_itm_delta > DELTA_DECAY.deep_otm_delta

    def test_delta_decay_is_frozen(self) -> None:
        """DeltaDecayConstants should be immutable."""
        with pytest.raises(AttributeError):
            DELTA_DECAY.deep_itm_delta = 0.99  # type: ignore[misc]


class TestVIX1DConstants:
    """Tests for VIX1D regime thresholds and constants."""

    def test_vix1d_risk_premium_positive(self) -> None:
        """Risk premium adjustment must be positive (VIX1D typically overshoots realised)."""
        assert VIX1D.risk_premium_adjustment > 0

    def test_vix1d_intraday_pattern_has_six_zones(self) -> None:
        """Intraday pattern must cover the 6 trading zones (excludes PRE_MARKET)."""
        assert len(VIX1D.intraday_pattern) == 6

    def test_vix1d_spike_threshold_reasonable(self) -> None:
        """Spike threshold should be between 10% and 100%."""
        assert 0.10 <= VIX1D.spike_threshold_pct <= 1.0

    def test_regime_count(self) -> None:
        """There must be exactly 4 VIX1D regimes."""
        assert len(VIX1DRegime) == 4

    @pytest.mark.parametrize(
        "regime_name", ["LOW", "NORMAL", "HIGH", "EXTREME"],
    )
    def test_regime_members_exist(self, regime_name: str) -> None:
        """VIX1DRegime must contain the expected member."""
        assert hasattr(VIX1DRegime, regime_name)

    def test_regime_thresholds_ordered(self) -> None:
        """VIX1D regime thresholds must be ordered: each lower < upper and contiguous."""
        for i, threshold in enumerate(VIX1D_REGIME_THRESHOLDS):
            assert threshold.lower < threshold.upper, (
                f"{threshold.regime.name}: lower ({threshold.lower}) must be < upper ({threshold.upper})"
            )
            if i > 0:
                prev = VIX1D_REGIME_THRESHOLDS[i - 1]
                assert prev.upper == threshold.lower, (
                    f"Gap between {prev.regime.name} upper ({prev.upper}) "
                    f"and {threshold.regime.name} lower ({threshold.lower})"
                )

    def test_regime_thresholds_start_at_zero(self) -> None:
        """First regime lower bound must be 0."""
        assert VIX1D_REGIME_THRESHOLDS[0].lower == 0.0

    def test_regime_thresholds_end_at_inf(self) -> None:
        """Last regime upper bound must be infinity."""
        assert VIX1D_REGIME_THRESHOLDS[-1].upper == math.inf

    def test_regime_threshold_values(self) -> None:
        """Check specific boundary values for LOW/NORMAL/HIGH/EXTREME."""
        expected = [
            (VIX1DRegime.LOW, 0.0, 12.0),
            (VIX1DRegime.NORMAL, 12.0, 18.0),
            (VIX1DRegime.HIGH, 18.0, 25.0),
            (VIX1DRegime.EXTREME, 25.0, math.inf),
        ]
        for threshold, (regime, lo, hi) in zip(VIX1D_REGIME_THRESHOLDS, expected):
            assert threshold.regime == regime
            assert threshold.lower == lo
            assert threshold.upper == hi


class TestDirectionScoreThresholds:
    """Tests for the direction score threshold constants."""

    def test_bullish_positive(self) -> None:
        """Bullish threshold must be positive."""
        assert DIRECTION_THRESHOLDS.bullish > 0

    def test_bearish_negative(self) -> None:
        """Bearish threshold must be negative."""
        assert DIRECTION_THRESHOLDS.bearish < 0

    def test_strong_bullish_gt_bullish(self) -> None:
        """Strong bullish must exceed normal bullish."""
        assert DIRECTION_THRESHOLDS.strong_bullish > DIRECTION_THRESHOLDS.bullish

    def test_strong_bearish_lt_bearish(self) -> None:
        """Strong bearish must be more negative than normal bearish."""
        assert DIRECTION_THRESHOLDS.strong_bearish < DIRECTION_THRESHOLDS.bearish

    def test_symmetric_bounds(self) -> None:
        """Score bounds must be symmetric at -100 and +100."""
        assert DIRECTION_THRESHOLDS.score_min == -100.0
        assert DIRECTION_THRESHOLDS.score_max == 100.0

    def test_thresholds_within_bounds(self) -> None:
        """All thresholds must fall within score_min and score_max."""
        assert DIRECTION_THRESHOLDS.score_min <= DIRECTION_THRESHOLDS.strong_bearish
        assert DIRECTION_THRESHOLDS.strong_bullish <= DIRECTION_THRESHOLDS.score_max

    def test_min_confluence_factors_valid(self) -> None:
        """min_confluence must be between 1 and total_factors inclusive."""
        assert 1 <= DIRECTION_THRESHOLDS.min_confluence_factors <= DIRECTION_THRESHOLDS.total_factors

    def test_total_factors_is_five(self) -> None:
        """System uses exactly 5 directional factors."""
        assert DIRECTION_THRESHOLDS.total_factors == 5


class TestFactorWeights:
    """Tests for the default factor weight constants."""

    def test_default_weights_sum_to_one(self) -> None:
        """Default factor weights must sum to exactly 1.0 (within tolerance)."""
        assert DEFAULT_FACTOR_WEIGHTS.validate()

    def test_validate_method_returns_true(self) -> None:
        """The validate() helper must confirm the defaults pass."""
        assert DEFAULT_FACTOR_WEIGHTS.validate() is True

    def test_as_dict_has_five_entries(self) -> None:
        """as_dict() must return exactly 5 factor->weight mappings."""
        d = DEFAULT_FACTOR_WEIGHTS.as_dict()
        assert len(d) == 5

    def test_as_dict_keys_are_direction_factors(self) -> None:
        """Keys of as_dict() must be the DirectionFactor enum members."""
        d = DEFAULT_FACTOR_WEIGHTS.as_dict()
        for key in d:
            assert isinstance(key, DirectionFactor)

    def test_all_weights_positive(self) -> None:
        """Each individual weight must be positive."""
        d = DEFAULT_FACTOR_WEIGHTS.as_dict()
        for factor, weight in d.items():
            assert weight > 0, f"{factor.name} weight must be > 0"

    @pytest.mark.parametrize(
        "factor_name",
        ["MARKET_INTERNALS", "OPTIONS_FLOW", "PRICE_ACTION", "GEX_STRUCTURE", "CROSS_ASSET"],
    )
    def test_direction_factor_members(self, factor_name: str) -> None:
        """DirectionFactor enum must contain all five expected members."""
        assert hasattr(DirectionFactor, factor_name)

    def test_factor_weights_frozen(self) -> None:
        """FactorWeightDefaults must be immutable."""
        with pytest.raises(AttributeError):
            DEFAULT_FACTOR_WEIGHTS.market_internals = 0.99  # type: ignore[misc]

    def test_specific_default_values(self) -> None:
        """Verify exact default weight values."""
        assert DEFAULT_FACTOR_WEIGHTS.market_internals == 0.30
        assert DEFAULT_FACTOR_WEIGHTS.options_flow == 0.25
        assert DEFAULT_FACTOR_WEIGHTS.price_action == 0.20
        assert DEFAULT_FACTOR_WEIGHTS.gex_structure == 0.15
        assert DEFAULT_FACTOR_WEIGHTS.cross_asset == 0.10


class TestStrikeSelection:
    """Tests for strike selection constants."""

    def test_delta_target_moderate_ordered(self) -> None:
        """Moderate delta range must have lower < upper."""
        r = STRIKE_SELECTION.delta_target_moderate
        assert r.lower < r.upper

    def test_delta_target_strong_ordered(self) -> None:
        """Strong delta range must have lower < upper."""
        r = STRIKE_SELECTION.delta_target_strong
        assert r.lower < r.upper

    def test_strong_includes_closer_atm(self) -> None:
        """Strong signals target higher delta (closer ATM) than moderate."""
        assert STRIKE_SELECTION.delta_target_strong.upper > STRIKE_SELECTION.delta_target_moderate.upper

    def test_spread_widths_ordered(self) -> None:
        """min < default < max for spread width."""
        assert STRIKE_SELECTION.min_spread_width < STRIKE_SELECTION.default_spread_width
        assert STRIKE_SELECTION.default_spread_width <= STRIKE_SELECTION.max_spread_width

    def test_liquidity_filters_positive(self) -> None:
        """Minimum OI, volume, and max spread percentage must be positive."""
        assert STRIKE_SELECTION.min_open_interest > 0
        assert STRIKE_SELECTION.min_volume > 0
        assert STRIKE_SELECTION.max_bid_ask_spread_pct > 0


class TestExitManagement:
    """Tests for exit management constants."""

    def test_profit_targets_decrease_over_day(self) -> None:
        """Profit targets should decrease as expiry approaches (take profits sooner)."""
        targets = EXIT_MANAGEMENT.profit_targets
        for i in range(len(targets) - 1):
            assert targets[i].target_pct >= targets[i + 1].target_pct, (
                f"{targets[i].zone.name} target ({targets[i].target_pct}) should be >= "
                f"{targets[i + 1].zone.name} target ({targets[i + 1].target_pct})"
            )

    def test_default_stop_loss_positive(self) -> None:
        """Default stop loss must be a positive fraction."""
        assert 0 < EXIT_MANAGEMENT.default_stop_loss_pct <= 1.0

    def test_absolute_time_stop_before_close(self) -> None:
        """Absolute time stop must be before market settlement."""
        assert EXIT_MANAGEMENT.absolute_time_stop < SPX_CONTRACT.settlement_time

    def test_breakeven_activation_positive(self) -> None:
        """Breakeven activation must be a positive profit percentage."""
        assert EXIT_MANAGEMENT.breakeven_activation_pct > 0

    def test_trailing_stop_positive(self) -> None:
        """Trailing stop must be a positive fraction."""
        assert 0 < EXIT_MANAGEMENT.trailing_stop_pct < 1.0

    def test_max_holding_minutes_reasonable(self) -> None:
        """Max holding period must be within a single trading day."""
        assert EXIT_MANAGEMENT.max_holding_minutes <= TRADING_MINUTES_PER_DAY


class TestPremiumSelling:
    """Tests for premium selling constants."""

    def test_vix1d_range_ordered(self) -> None:
        """VIX1D minimum must be less than maximum for premium selling."""
        assert PREMIUM_SELLING.vix1d_min < PREMIUM_SELLING.vix1d_max

    def test_tick_range_ordered(self) -> None:
        """NYSE TICK range must be ordered."""
        assert PREMIUM_SELLING.tick_range_min < PREMIUM_SELLING.tick_range_max

    def test_iv_rv_ratio_gt_one(self) -> None:
        """IV/RV ratio must be above 1 (premium exists to sell)."""
        assert PREMIUM_SELLING.iv_rv_ratio_min > 1.0

    def test_min_credit_positive(self) -> None:
        """Minimum credit must be positive."""
        assert PREMIUM_SELLING.min_credit > 0

    def test_prob_otm_above_half(self) -> None:
        """Probability OTM target should be above 50% (edge in selling)."""
        assert PREMIUM_SELLING.prob_otm_target > 0.50


class TestGEXScanner:
    """Tests for GEX scanner constants."""

    def test_shift_alert_threshold_positive(self) -> None:
        """GEX shift alert threshold must be a positive percentage."""
        assert GEX_SCANNER.shift_alert_threshold_pct > 0

    def test_collapse_threshold_gt_shift_threshold(self) -> None:
        """Collapse threshold should be more severe than shift alert."""
        assert GEX_SCANNER.collapse_threshold_pct > GEX_SCANNER.shift_alert_threshold_pct

    def test_recalculation_interval_positive(self) -> None:
        """Recalculation interval must be a positive number of seconds."""
        assert GEX_SCANNER.recalculation_interval_seconds > 0

    def test_min_meaningful_gex_positive(self) -> None:
        """Minimum meaningful GEX must be positive."""
        assert GEX_SCANNER.min_meaningful_gex > 0

    def test_flip_hysteresis_positive(self) -> None:
        """Flip hysteresis must be positive to prevent whipsaw."""
        assert GEX_SCANNER.flip_hysteresis_points > 0


class TestSelfLearning:
    """Tests for self-learning constants."""

    def test_ema_weight_between_zero_and_one(self) -> None:
        """EMA weight must be in (0, 1)."""
        assert 0 < SELF_LEARNING.ema_weight < 1

    def test_factor_weight_bounds_ordered(self) -> None:
        """Minimum factor weight must be less than maximum."""
        assert SELF_LEARNING.min_factor_weight < SELF_LEARNING.max_factor_weight

    def test_max_factor_weight_below_one(self) -> None:
        """Max factor weight must be less than 1.0 (no single factor dominance)."""
        assert SELF_LEARNING.max_factor_weight < 1.0

    def test_min_trades_for_learning_positive(self) -> None:
        """Cold-start guard requires at least some trades before learning."""
        assert SELF_LEARNING.min_trades_for_learning > 0

    def test_recalibration_milestones_sorted(self) -> None:
        """Recalibration milestones must be in ascending order."""
        milestones = SELF_LEARNING.recalibration_milestones
        for i in range(len(milestones) - 1):
            assert milestones[i] < milestones[i + 1]

    def test_learning_rate_decay_between_zero_and_one(self) -> None:
        """Learning rate decay must be in (0, 1)."""
        assert 0 < SELF_LEARNING.learning_rate_decay < 1


class TestRiskManagement:
    """Tests for hard risk management constants."""

    def test_no_naked_shorts(self) -> None:
        """CRITICAL: Naked short positions must NEVER be allowed."""
        assert RISK_MANAGEMENT.allow_naked_short is False

    def test_max_risk_per_trade_reasonable(self) -> None:
        """Max risk per trade must be a small fraction of daily budget."""
        assert 0 < RISK_MANAGEMENT.max_risk_per_trade_pct <= 0.10

    def test_max_daily_loss_reasonable(self) -> None:
        """Max daily loss must be a reasonable fraction."""
        assert 0 < RISK_MANAGEMENT.max_daily_loss_pct <= 0.20

    def test_max_concurrent_positions_bounded(self) -> None:
        """Maximum concurrent positions must be a positive small number."""
        assert 1 <= RISK_MANAGEMENT.max_concurrent_positions <= 20

    def test_permitted_order_types_limit_only(self) -> None:
        """Only LIMIT-type orders should be permitted (safety rail)."""
        for order_type in RISK_MANAGEMENT.permitted_order_types:
            assert "LIMIT" in order_type

    def test_min_account_equity_at_pdt_level(self) -> None:
        """Minimum equity must be at least the PDT threshold ($25,000)."""
        assert RISK_MANAGEMENT.min_account_equity >= 25_000.0

    def test_order_fill_timeout_positive(self) -> None:
        """Order fill timeout must be positive."""
        assert RISK_MANAGEMENT.order_fill_timeout_seconds > 0

    def test_risk_management_is_frozen(self) -> None:
        """Risk management constants must be immutable."""
        with pytest.raises(AttributeError):
            RISK_MANAGEMENT.allow_naked_short = True  # type: ignore[misc]


class TestAllConstantsDefined:
    """Verify that every exported constant is defined and non-None."""

    @pytest.mark.parametrize(
        "constant_name,constant_value",
        [
            ("SPX_CONTRACT", SPX_CONTRACT),
            ("INTRADAY_ZONE_SCHEDULE", INTRADAY_ZONE_SCHEDULE),
            ("ZONE_BOUNDARIES", ZONE_BOUNDARIES),
            ("TRADING_MINUTES_PER_DAY", TRADING_MINUTES_PER_DAY),
            ("TRADING_SECONDS_PER_DAY", TRADING_SECONDS_PER_DAY),
            ("CALENDAR_DAYS_PER_YEAR", CALENDAR_DAYS_PER_YEAR),
            ("TRADING_DAYS_PER_YEAR", TRADING_DAYS_PER_YEAR),
            ("GAMMA_RANGES", GAMMA_RANGES),
            ("THETA_DECAY_CURVE", THETA_DECAY_CURVE),
            ("DELTA_DECAY", DELTA_DECAY),
            ("VIX1D", VIX1D),
            ("VIX1D_REGIME_THRESHOLDS", VIX1D_REGIME_THRESHOLDS),
            ("DIRECTION_THRESHOLDS", DIRECTION_THRESHOLDS),
            ("DEFAULT_FACTOR_WEIGHTS", DEFAULT_FACTOR_WEIGHTS),
            ("STRIKE_SELECTION", STRIKE_SELECTION),
            ("EXIT_MANAGEMENT", EXIT_MANAGEMENT),
            ("PREMIUM_SELLING", PREMIUM_SELLING),
            ("GEX_SCANNER", GEX_SCANNER),
            ("SELF_LEARNING", SELF_LEARNING),
            ("RISK_MANAGEMENT", RISK_MANAGEMENT),
        ],
    )
    def test_constant_is_not_none(self, constant_name: str, constant_value: Any) -> None:
        """Exported constant must be defined and non-None."""
        assert constant_value is not None, f"{constant_name} is None"


# ============================================================================
#  PART 2 -- MODELS TESTS
# ============================================================================


class TestEnums:
    """Tests for all enum classes in the models module."""

    @pytest.mark.parametrize(
        "member", ["TRENDING", "RANGE", "VOLATILE", "SQUEEZE", "EVENT"],
    )
    def test_session_type_members(self, member: str) -> None:
        """SessionType must contain the expected member."""
        assert hasattr(SessionType, member)
        assert SessionType[member].value == member

    @pytest.mark.parametrize(
        "member", ["DIRECTIONAL", "PREMIUM_SELL", "GAMMA_SCALP"],
    )
    def test_scan_type_members(self, member: str) -> None:
        """ScanType must contain the expected member."""
        assert hasattr(ScanType, member)
        assert ScanType[member].value == member

    @pytest.mark.parametrize(
        "member", ["BULL", "BEAR", "NEUTRAL"],
    )
    def test_trade_direction_members(self, member: str) -> None:
        """TradeDirection must contain the expected member."""
        assert hasattr(TradeDirection, member)

    @pytest.mark.parametrize(
        "member",
        [
            "PROFIT_TARGET", "STOP_LOSS", "TIME_STOP", "SIGNAL_REVERSAL",
            "GEX_FLIP", "VIX_SPIKE", "MANUAL", "BREAK_EVEN",
        ],
    )
    def test_exit_reason_members(self, member: str) -> None:
        """ExitReason must contain the expected member."""
        assert hasattr(ExitReason, member)

    @pytest.mark.parametrize(
        "member",
        [
            "PRE_MARKET", "OPENING_AUCTION", "MORNING_SESSION",
            "MIDDAY_LULL", "AFTERNOON_ACCEL", "POWER_HOUR", "SETTLEMENT_WINDOW",
        ],
    )
    def test_time_zone_type_members(self, member: str) -> None:
        """TimeZoneType must contain the expected member."""
        assert hasattr(TimeZoneType, member)

    @pytest.mark.parametrize(
        "member",
        [
            "GAMMA_FLIP_CROSSOVER", "GAMMA_WALL_APPROACH",
            "TRANSITION_ZONE_BREAKOUT", "GEX_COLLAPSE",
            "CHARM_DRIVEN_FLOW", "VANNA_AMPLIFICATION",
        ],
    )
    def test_gex_signal_type_members(self, member: str) -> None:
        """GEXSignalType must contain the expected member."""
        assert hasattr(GEXSignalType, member)

    @pytest.mark.parametrize("member", ["CALL", "PUT"])
    def test_option_side_members(self, member: str) -> None:
        """OptionSide must contain CALL and PUT."""
        assert hasattr(OptionSide, member)

    @pytest.mark.parametrize(
        "member", ["SINGLE_LONG", "DEBIT_SPREAD", "CREDIT_SPREAD", "IRON_CONDOR"],
    )
    def test_position_type_members(self, member: str) -> None:
        """PositionType must contain the expected member."""
        assert hasattr(PositionType, member)

    @pytest.mark.parametrize("member", ["LOW", "MED", "HIGH"])
    def test_impact_level_members(self, member: str) -> None:
        """ImpactLevel must contain LOW, MED, HIGH."""
        assert hasattr(ImpactLevel, member)

    @pytest.mark.parametrize(
        "member", ["MICRO", "SMALL", "MEDIUM", "LARGE", "MEGA"],
    )
    def test_gap_classification_members(self, member: str) -> None:
        """GapClassification must contain all five size categories."""
        assert hasattr(GapClassification, member)

    @pytest.mark.parametrize("member", ["BUY", "SELL"])
    def test_leg_side_members(self, member: str) -> None:
        """LegSide must contain BUY and SELL."""
        assert hasattr(LegSide, member)

    def test_str_enums_are_strings(self) -> None:
        """All str-mixin enums must be usable as plain strings."""
        assert SessionType.TRENDING == "TRENDING"
        assert ScanType.DIRECTIONAL == "DIRECTIONAL"
        assert TradeDirection.BULL == "BULL"
        assert ExitReason.STOP_LOSS == "STOP_LOSS"
        assert OptionSide.CALL == "CALL"


class TestOptionQuote:
    """Tests for the OptionQuote Pydantic model."""

    def test_creation_with_valid_data(self) -> None:
        """A well-formed OptionQuote must be constructible without error."""
        q = _make_option_quote()
        assert q.strike == 5200.0
        assert q.option_type == OptionSide.CALL

    def test_reject_negative_strike(self) -> None:
        """Strike must be positive (gt=0)."""
        with pytest.raises(ValidationError):
            _make_option_quote(strike=-100.0)

    def test_reject_zero_strike(self) -> None:
        """Strike of zero is not allowed (gt=0)."""
        with pytest.raises(ValidationError):
            _make_option_quote(strike=0)

    def test_reject_negative_bid(self) -> None:
        """Bid must be >= 0."""
        with pytest.raises(ValidationError):
            _make_option_quote(bid=-1.0)

    def test_reject_negative_ask(self) -> None:
        """Ask must be >= 0."""
        with pytest.raises(ValidationError):
            _make_option_quote(ask=-1.0)

    def test_reject_ask_below_bid(self) -> None:
        """Ask must be >= bid (validated by ask_gte_bid)."""
        with pytest.raises(ValidationError):
            _make_option_quote(bid=5.00, ask=4.00)

    def test_ask_equals_bid_is_ok(self) -> None:
        """Ask == bid is acceptable (locked market)."""
        q = _make_option_quote(bid=3.50, ask=3.50, mid=3.50)
        assert q.ask == q.bid

    def test_reject_negative_volume(self) -> None:
        """Volume must be >= 0."""
        with pytest.raises(ValidationError):
            _make_option_quote(volume=-1)

    def test_reject_negative_open_interest(self) -> None:
        """Open interest must be >= 0."""
        with pytest.raises(ValidationError):
            _make_option_quote(open_interest=-1)

    def test_reject_negative_implied_vol(self) -> None:
        """Implied vol must be >= 0."""
        with pytest.raises(ValidationError):
            _make_option_quote(implied_vol=-0.01)

    def test_reject_delta_out_of_range(self) -> None:
        """Delta must be between -1 and +1."""
        with pytest.raises(ValidationError):
            _make_option_quote(delta=1.5)
        with pytest.raises(ValidationError):
            _make_option_quote(delta=-1.5)

    def test_reject_positive_theta(self) -> None:
        """Theta must be <= 0 for long options."""
        with pytest.raises(ValidationError):
            _make_option_quote(theta=0.1)

    def test_reject_negative_gamma(self) -> None:
        """Gamma must be >= 0."""
        with pytest.raises(ValidationError):
            _make_option_quote(gamma=-0.01)

    def test_reject_negative_vega(self) -> None:
        """Vega must be >= 0."""
        with pytest.raises(ValidationError):
            _make_option_quote(vega=-0.01)

    def test_spread_width_property(self) -> None:
        """spread_width must equal ask - bid."""
        q = _make_option_quote(bid=3.50, ask=3.80)
        assert abs(q.spread_width - 0.30) < 1e-9

    def test_spread_pct_property(self) -> None:
        """spread_pct must be (ask-bid)/mid * 100."""
        q = _make_option_quote(bid=3.50, ask=3.80, mid=3.65)
        expected = 0.30 / 3.65 * 100.0
        assert abs(q.spread_pct - expected) < 1e-6

    def test_spread_pct_zero_mid(self) -> None:
        """spread_pct returns 0 when mid is 0."""
        q = _make_option_quote(bid=0.0, ask=0.0, mid=0.0, last=0.0, implied_vol=0.0, delta=0.0, gamma=0.0, theta=0.0, vega=0.0)
        assert q.spread_pct == 0.0

    def test_is_liquid_true(self) -> None:
        """Quote with high OI and tight spread should be liquid."""
        q = _make_option_quote(open_interest=500, bid=3.50, ask=3.60, mid=3.55)
        assert q.is_liquid is True

    def test_is_liquid_false_low_oi(self) -> None:
        """Quote with very low OI should not be liquid."""
        q = _make_option_quote(open_interest=50)
        assert q.is_liquid is False

    def test_is_liquid_false_wide_spread(self) -> None:
        """Quote with a very wide spread should not be liquid."""
        q = _make_option_quote(bid=1.00, ask=2.00, mid=1.50, open_interest=1000)
        # spread_pct = 1.0/1.50*100 = 66.67% > 25%
        assert q.is_liquid is False

    def test_charm_vanna_speed_defaults(self) -> None:
        """Charm, vanna, and speed should default to 0."""
        q = _make_option_quote()
        assert q.charm == 0.0
        assert q.vanna == 0.0
        assert q.speed == 0.0

    def test_timestamp_auto_populated(self) -> None:
        """Timestamp should be auto-populated when not provided."""
        q = _make_option_quote()
        assert q.timestamp is not None
        assert isinstance(q.timestamp, datetime)


class TestOptionsChain:
    """Tests for the OptionsChain Pydantic model."""

    def test_creation_empty_chain(self) -> None:
        """An empty options chain should be valid."""
        chain = OptionsChain(
            expiry_date=date(2025, 5, 15),
            underlying_price=5200.0,
        )
        assert chain.quotes == []
        assert chain.strikes == []

    def test_calls_property(self) -> None:
        """calls property must filter to only CALL quotes."""
        call = _make_option_quote(strike=5200.0, option_type=OptionSide.CALL)
        put = _make_option_quote(strike=5200.0, option_type=OptionSide.PUT, delta=-0.35)
        chain = OptionsChain(
            expiry_date=date(2025, 5, 15),
            underlying_price=5200.0,
            quotes=[call, put],
        )
        assert len(chain.calls) == 1
        assert chain.calls[0].option_type == OptionSide.CALL

    def test_puts_property(self) -> None:
        """puts property must filter to only PUT quotes."""
        call = _make_option_quote(strike=5200.0, option_type=OptionSide.CALL)
        put = _make_option_quote(strike=5200.0, option_type=OptionSide.PUT, delta=-0.35)
        chain = OptionsChain(
            expiry_date=date(2025, 5, 15),
            underlying_price=5200.0,
            quotes=[call, put],
        )
        assert len(chain.puts) == 1
        assert chain.puts[0].option_type == OptionSide.PUT

    def test_strikes_sorted_unique(self) -> None:
        """strikes property must return sorted unique values."""
        q1 = _make_option_quote(strike=5200.0, option_type=OptionSide.CALL)
        q2 = _make_option_quote(strike=5200.0, option_type=OptionSide.PUT, delta=-0.35)
        q3 = _make_option_quote(strike=5210.0, option_type=OptionSide.CALL)
        chain = OptionsChain(
            expiry_date=date(2025, 5, 15),
            underlying_price=5200.0,
            quotes=[q1, q2, q3],
        )
        assert chain.strikes == [5200.0, 5210.0]

    def test_get_by_strike(self) -> None:
        """get_by_strike must return all quotes at that strike."""
        q1 = _make_option_quote(strike=5200.0, option_type=OptionSide.CALL)
        q2 = _make_option_quote(strike=5200.0, option_type=OptionSide.PUT, delta=-0.35)
        q3 = _make_option_quote(strike=5210.0, option_type=OptionSide.CALL)
        chain = OptionsChain(
            expiry_date=date(2025, 5, 15),
            underlying_price=5200.0,
            quotes=[q1, q2, q3],
        )
        result = chain.get_by_strike(5200.0)
        assert len(result) == 2

    def test_atm_strike_nearest(self) -> None:
        """atm_strike must return the strike nearest to underlying price."""
        q1 = _make_option_quote(strike=5190.0, option_type=OptionSide.CALL)
        q2 = _make_option_quote(strike=5200.0, option_type=OptionSide.CALL)
        q3 = _make_option_quote(strike=5210.0, option_type=OptionSide.CALL)
        chain = OptionsChain(
            expiry_date=date(2025, 5, 15),
            underlying_price=5198.0,
            quotes=[q1, q2, q3],
        )
        assert chain.atm_strike() == 5200.0

    def test_atm_strike_empty_chain(self) -> None:
        """atm_strike with no quotes returns underlying_price."""
        chain = OptionsChain(
            expiry_date=date(2025, 5, 15),
            underlying_price=5200.0,
        )
        assert chain.atm_strike() == 5200.0

    def test_reject_zero_underlying(self) -> None:
        """underlying_price must be > 0."""
        with pytest.raises(ValidationError):
            OptionsChain(expiry_date=date(2025, 5, 15), underlying_price=0)


class TestMarketInternals:
    """Tests for the MarketInternals model."""

    def _make(self, **overrides: Any) -> MarketInternals:
        """Build a valid MarketInternals with defaults."""
        defaults: dict[str, Any] = dict(
            nyse_tick=250,
            nyse_tick_10min_avg=180.5,
            cumulative_tick=45000.0,
            nyse_trin=1.05,
            advance_decline_ratio=1.20,
            up_down_volume_ratio=1.15,
            es_cumulative_delta=12000.0,
        )
        defaults.update(overrides)
        return MarketInternals(**defaults)

    def test_creation_with_realistic_values(self) -> None:
        """Construct with typical NYSE breadth values."""
        mi = self._make()
        assert mi.nyse_tick == 250
        assert mi.nyse_trin == 1.05

    def test_reject_zero_trin(self) -> None:
        """TRIN must be > 0."""
        with pytest.raises(ValidationError):
            self._make(nyse_trin=0)

    def test_reject_negative_trin(self) -> None:
        """TRIN must be > 0."""
        with pytest.raises(ValidationError):
            self._make(nyse_trin=-0.5)

    def test_tick_extreme_bullish(self) -> None:
        """TICK >= 800 is extreme bullish."""
        mi = self._make(nyse_tick=900)
        assert mi.tick_is_extreme_bullish is True
        assert mi.tick_is_extreme_bearish is False

    def test_tick_extreme_bearish(self) -> None:
        """TICK <= -800 is extreme bearish."""
        mi = self._make(nyse_tick=-850)
        assert mi.tick_is_extreme_bearish is True
        assert mi.tick_is_extreme_bullish is False

    def test_tick_neutral(self) -> None:
        """TICK in normal range is neither extreme."""
        mi = self._make(nyse_tick=100)
        assert mi.tick_is_extreme_bullish is False
        assert mi.tick_is_extreme_bearish is False

    def test_trin_bullish(self) -> None:
        """TRIN below 0.80 indicates bullish breadth."""
        mi = self._make(nyse_trin=0.70)
        assert mi.trin_bullish is True
        assert mi.trin_bearish is False

    def test_trin_bearish(self) -> None:
        """TRIN above 1.20 indicates bearish breadth."""
        mi = self._make(nyse_trin=1.50)
        assert mi.trin_bearish is True
        assert mi.trin_bullish is False


class TestCrossAssetData:
    """Tests for the CrossAssetData model."""

    def _make(self, **overrides: Any) -> CrossAssetData:
        defaults: dict[str, Any] = dict(
            vix=16.5,
            vix1d=14.2,
            vix9d=15.8,
            vix1d_intraday_avg=14.0,
            us_10y_yield=4.35,
            us_10y_yield_change=-2.5,
            dxy=104.2,
            dxy_change=-0.15,
            es_price=5215.50,
            es_volume=850000,
        )
        defaults.update(overrides)
        return CrossAssetData(**defaults)

    def test_creation_valid(self) -> None:
        """Construct with typical cross-asset data."""
        ca = self._make()
        assert ca.vix == 16.5
        assert ca.es_price == 5215.50

    def test_vix_term_structure_inverted(self) -> None:
        """VIX1D > VIX signals near-term fear spike."""
        ca = self._make(vix=16.0, vix1d=18.0)
        assert ca.vix_term_structure_inverted is True

    def test_vix_term_structure_normal(self) -> None:
        """VIX1D <= VIX is normal term structure."""
        ca = self._make(vix=18.0, vix1d=14.0)
        assert ca.vix_term_structure_inverted is False

    @pytest.mark.parametrize(
        "vix_value,expected_regime",
        [
            (10.0, "LOW"),
            (15.0, "NORMAL"),
            (25.0, "ELEVATED"),
            (35.0, "EXTREME"),
        ],
    )
    def test_vix_regime(self, vix_value: float, expected_regime: str) -> None:
        """vix_regime property must return the correct regime string."""
        ca = self._make(vix=vix_value)
        assert ca.vix_regime == expected_regime

    def test_reject_negative_vix(self) -> None:
        """VIX must be >= 0."""
        with pytest.raises(ValidationError):
            self._make(vix=-1.0)

    def test_reject_zero_dxy(self) -> None:
        """DXY must be > 0."""
        with pytest.raises(ValidationError):
            self._make(dxy=0)

    def test_reject_zero_es_price(self) -> None:
        """ES price must be > 0."""
        with pytest.raises(ValidationError):
            self._make(es_price=0)


class TestStrikeGEX:
    """Tests for the StrikeGEX dataclass."""

    def _make(self, **overrides: Any) -> StrikeGEX:
        defaults: dict[str, Any] = dict(
            strike=5200.0,
            call_gamma=0.05,
            put_gamma=0.04,
            call_oi=10000,
            put_oi=8000,
            dealer_gamma_call=50000.0,
            dealer_gamma_put=-30000.0,
            net_gex=20000.0,
            net_charm=1500.0,
            net_vanna=500.0,
            net_speed=10.0,
        )
        defaults.update(overrides)
        return StrikeGEX(**defaults)

    def test_creation(self) -> None:
        """StrikeGEX should be constructible with valid data."""
        sg = self._make()
        assert sg.strike == 5200.0

    def test_total_oi(self) -> None:
        """total_oi must equal call_oi + put_oi."""
        sg = self._make(call_oi=10000, put_oi=8000)
        assert sg.total_oi == 18000

    def test_dealer_net_gamma(self) -> None:
        """dealer_net_gamma must equal dealer_gamma_call + dealer_gamma_put."""
        sg = self._make(dealer_gamma_call=50000.0, dealer_gamma_put=-30000.0)
        assert sg.dealer_net_gamma == 20000.0


class TestGEXProfile:
    """Tests for the GEXProfile model."""

    def _make(self, **overrides: Any) -> GEXProfile:
        defaults: dict[str, Any] = dict(
            total_net_gex=500000.0,
            gamma_flip_level=5200.0,
            call_wall=5250.0,
            put_wall=5150.0,
            max_pain=5200.0,
            plus_gex=5220.0,
            minus_gex=5180.0,
            transition_zone_upper=5215.0,
            transition_zone_lower=5195.0,
            vol_trigger=5230.0,
        )
        defaults.update(overrides)
        return GEXProfile(**defaults)

    def test_creation_valid(self) -> None:
        """GEXProfile with valid data should be constructible."""
        gp = self._make()
        assert gp.total_net_gex == 500000.0

    def test_positive_gamma_regime(self) -> None:
        """Positive total_net_gex indicates positive gamma regime."""
        gp = self._make(total_net_gex=100.0)
        assert gp.is_positive_gamma_regime is True

    def test_negative_gamma_regime(self) -> None:
        """Negative total_net_gex indicates negative gamma regime."""
        gp = self._make(total_net_gex=-100.0)
        assert gp.is_positive_gamma_regime is False

    def test_transition_zone_width(self) -> None:
        """Transition zone width must equal upper - lower."""
        gp = self._make(transition_zone_upper=5215.0, transition_zone_lower=5195.0)
        assert abs(gp.transition_zone_width - 20.0) < 1e-9

    def test_reject_inverted_transition_zone(self) -> None:
        """Lower bound must not exceed upper bound."""
        with pytest.raises(ValidationError):
            self._make(transition_zone_upper=5190.0, transition_zone_lower=5210.0)

    def test_reject_zero_gamma_flip(self) -> None:
        """gamma_flip_level must be > 0."""
        with pytest.raises(ValidationError):
            self._make(gamma_flip_level=0)


class TestDirectionScore:
    """Tests for the DirectionScore model."""

    def test_creation_valid(self) -> None:
        """A well-formed DirectionScore must be constructible."""
        ds = _make_direction_score()
        assert ds.total_score == 55.0

    def test_reject_score_above_100(self) -> None:
        """total_score must be <= 100."""
        with pytest.raises(ValidationError):
            _make_direction_score(total_score=101.0)

    def test_reject_score_below_minus_100(self) -> None:
        """total_score must be >= -100."""
        with pytest.raises(ValidationError):
            _make_direction_score(total_score=-101.0)

    def test_boundary_score_100(self) -> None:
        """Score of exactly +100 must be accepted."""
        ds = _make_direction_score(total_score=100.0)
        assert ds.total_score == 100.0

    def test_boundary_score_minus_100(self) -> None:
        """Score of exactly -100 must be accepted."""
        ds = _make_direction_score(total_score=-100.0)
        assert ds.total_score == -100.0

    @pytest.mark.parametrize(
        "field_name",
        [
            "market_internals_score",
            "options_flow_score",
            "price_action_score",
            "gex_structure_score",
            "cross_asset_score",
        ],
    )
    def test_sub_score_clamped_to_range(self, field_name: str) -> None:
        """Each sub-score must reject values outside [-100, +100]."""
        with pytest.raises(ValidationError):
            _make_direction_score(**{field_name: 101.0})
        with pytest.raises(ValidationError):
            _make_direction_score(**{field_name: -101.0})

    def test_is_high_conviction(self) -> None:
        """High conviction requires |score| >= 60 and factors_agreeing >= 4."""
        ds = _make_direction_score(total_score=70.0, factors_agreeing=4)
        assert ds.is_high_conviction is True

    def test_not_high_conviction_low_score(self) -> None:
        """Low score should not be high conviction."""
        ds = _make_direction_score(total_score=30.0, factors_agreeing=4)
        assert ds.is_high_conviction is False

    def test_not_high_conviction_low_agreement(self) -> None:
        """Strong score but low agreement is not high conviction."""
        ds = _make_direction_score(total_score=70.0, factors_agreeing=2)
        assert ds.is_high_conviction is False

    def test_is_conflicted(self) -> None:
        """Opposing factor with low net score should be conflicted."""
        ds = _make_direction_score(
            total_score=20.0, has_opposing_factor=True,
        )
        assert ds.is_conflicted is True

    def test_not_conflicted_strong_score(self) -> None:
        """Opposing factor with strong net score is not conflicted."""
        ds = _make_direction_score(
            total_score=50.0, has_opposing_factor=True,
        )
        assert ds.is_conflicted is False

    def test_confidence_rounded(self) -> None:
        """Confidence should be rounded to 2 decimal places."""
        ds = _make_direction_score(confidence=72.5678)
        assert ds.confidence == 72.57

    def test_reject_confidence_above_100(self) -> None:
        """Confidence above 100 is invalid."""
        with pytest.raises(ValidationError):
            _make_direction_score(confidence=101.0)

    def test_reject_confidence_below_zero(self) -> None:
        """Confidence below 0 is invalid."""
        with pytest.raises(ValidationError):
            _make_direction_score(confidence=-1.0)


class TestStrikeSelectionModel:
    """Tests for the StrikeSelection Pydantic model."""

    def _make(self, **overrides: Any) -> StrikeSelection:
        defaults: dict[str, Any] = dict(
            strike=5220.0,
            option_type=OptionSide.CALL,
            delta=0.35,
            gamma=0.10,
            theta=-0.40,
            iv=0.18,
            bid=3.20,
            ask=3.50,
            mid=3.35,
            spread_width=0.30,
            oi=5000,
            volume=1200,
            is_liquid=True,
            distance_from_spot=20.0,
            moneyness=1.004,
        )
        defaults.update(overrides)
        return StrikeSelection(**defaults)

    def test_creation_valid(self) -> None:
        """Valid StrikeSelection should construct without error."""
        ss = self._make()
        assert ss.strike == 5220.0

    def test_is_otm_call(self) -> None:
        """OTM call has positive distance_from_spot."""
        ss = self._make(option_type=OptionSide.CALL, distance_from_spot=20.0)
        assert ss.is_otm is True

    def test_itm_call(self) -> None:
        """ITM call has negative distance_from_spot."""
        ss = self._make(option_type=OptionSide.CALL, distance_from_spot=-10.0)
        assert ss.is_otm is False

    def test_is_otm_put(self) -> None:
        """OTM put has negative distance_from_spot."""
        ss = self._make(option_type=OptionSide.PUT, distance_from_spot=-20.0, delta=-0.25)
        assert ss.is_otm is True

    def test_itm_put(self) -> None:
        """ITM put has positive distance_from_spot."""
        ss = self._make(option_type=OptionSide.PUT, distance_from_spot=10.0, delta=-0.65)
        assert ss.is_otm is False

    def test_cost_per_point_normal(self) -> None:
        """cost_per_point should be mid / |delta|."""
        ss = self._make(mid=3.35, delta=0.35)
        expected = 3.35 / 0.35
        assert abs(ss.cost_per_point - expected) < 1e-6

    def test_cost_per_point_near_zero_delta(self) -> None:
        """cost_per_point returns inf when delta is negligible."""
        ss = self._make(delta=0.005)
        assert ss.cost_per_point == float("inf")

    def test_reject_zero_strike(self) -> None:
        """Strike must be > 0."""
        with pytest.raises(ValidationError):
            self._make(strike=0)

    def test_liquidity_flag(self) -> None:
        """is_liquid field is just a boolean flag, no validation beyond that."""
        ss_liq = self._make(is_liquid=True)
        ss_illiq = self._make(is_liquid=False)
        assert ss_liq.is_liquid is True
        assert ss_illiq.is_liquid is False


class TestScanSignal:
    """Tests for the ScanSignal top-level trade recommendation model."""

    def _make(self, **overrides: Any) -> ScanSignal:
        defaults: dict[str, Any] = dict(
            scan_type=ScanType.DIRECTIONAL,
            direction=TradeDirection.BULL,
            direction_score=_make_direction_score(),
            entry_price=3.50,
            stop_loss=1.75,
            profit_target=5.25,
            position_type=PositionType.DEBIT_SPREAD,
            contracts=2,
            max_risk=350.0,
            expected_reward=525.0,
            risk_reward_ratio=1.5,
            time_zone=TimeZoneType.MORNING_SESSION,
            session_type=SessionType.TRENDING,
        )
        defaults.update(overrides)
        return ScanSignal(**defaults)

    def test_creation_valid(self) -> None:
        """A complete ScanSignal should be constructible."""
        sig = self._make()
        assert sig.scan_type == ScanType.DIRECTIONAL

    def test_is_favorable_rr_true(self) -> None:
        """Risk/reward >= 1.5 is favorable."""
        sig = self._make(risk_reward_ratio=2.0)
        assert sig.is_favorable_rr is True

    def test_is_favorable_rr_false(self) -> None:
        """Risk/reward < 1.5 is not favorable."""
        sig = self._make(risk_reward_ratio=1.0)
        assert sig.is_favorable_rr is False

    def test_dollar_risk_per_contract(self) -> None:
        """dollar_risk_per_contract should be max_risk / contracts."""
        sig = self._make(max_risk=500.0, contracts=5)
        assert sig.dollar_risk_per_contract == 100.0

    def test_reject_zero_entry_price(self) -> None:
        """Entry price must be > 0."""
        with pytest.raises(ValidationError):
            self._make(entry_price=0)

    def test_reject_zero_contracts(self) -> None:
        """Must have at least 1 contract."""
        with pytest.raises(ValidationError):
            self._make(contracts=0)

    def test_strike_selection_optional(self) -> None:
        """strike_selection can be None (for spread-only signals)."""
        sig = self._make(strike_selection=None)
        assert sig.strike_selection is None


class TestCreditSpread:
    """Tests for the CreditSpread model."""

    def test_creation_valid(self) -> None:
        """A valid bull put credit spread should construct without error."""
        cs = _make_credit_spread()
        assert cs.credit_received == 1.30

    def test_risk_reward_ratio(self) -> None:
        """risk_reward_ratio should be credit / max_loss."""
        cs = _make_credit_spread(credit_received=1.30, max_loss=8.70)
        expected = 1.30 / 8.70
        assert abs(cs.risk_reward_ratio - expected) < 1e-6

    def test_return_on_risk(self) -> None:
        """return_on_risk should be credit / max_loss * 100."""
        cs = _make_credit_spread(credit_received=1.30, max_loss=8.70)
        expected = 1.30 / 8.70 * 100.0
        assert abs(cs.return_on_risk - expected) < 1e-6

    def test_reject_mismatched_option_types(self) -> None:
        """Both legs must share the same option type."""
        with pytest.raises(ValidationError):
            _make_credit_spread(
                short_leg=_make_spread_leg(option_type=OptionSide.PUT, side=LegSide.SELL),
                long_leg=_make_spread_leg(option_type=OptionSide.CALL, side=LegSide.BUY),
            )

    def test_reject_short_leg_not_sell(self) -> None:
        """Short leg must have side=SELL."""
        with pytest.raises(ValidationError):
            _make_credit_spread(
                short_leg=_make_spread_leg(side=LegSide.BUY),
            )

    def test_reject_long_leg_not_buy(self) -> None:
        """Long leg must have side=BUY."""
        with pytest.raises(ValidationError):
            _make_credit_spread(
                long_leg=_make_spread_leg(side=LegSide.SELL),
            )

    def test_reject_zero_credit(self) -> None:
        """credit_received must be > 0."""
        with pytest.raises(ValidationError):
            _make_credit_spread(credit_received=0)

    def test_reject_zero_width(self) -> None:
        """width must be > 0."""
        with pytest.raises(ValidationError):
            _make_credit_spread(width=0)

    def test_probability_otm_bounds(self) -> None:
        """probability_otm must be between 0 and 1."""
        with pytest.raises(ValidationError):
            _make_credit_spread(probability_otm=1.5)
        with pytest.raises(ValidationError):
            _make_credit_spread(probability_otm=-0.1)


class TestIronCondor:
    """Tests for the IronCondor model."""

    def _make(self, **overrides: Any) -> IronCondor:
        put_spread = _make_credit_spread(
            short_leg=_make_spread_leg(
                strike=5150.0, option_type=OptionSide.PUT, side=LegSide.SELL,
                price=1.80, delta=-0.15, gamma=0.06, theta=-0.20,
            ),
            long_leg=_make_spread_leg(
                strike=5140.0, option_type=OptionSide.PUT, side=LegSide.BUY,
                price=1.00, delta=-0.10, gamma=0.04, theta=-0.15,
            ),
            credit_received=0.80,
            max_loss=9.20,
            width=10.0,
            probability_otm=0.85,
            break_even=5149.20,
        )
        call_spread = _make_credit_spread(
            short_leg=_make_spread_leg(
                strike=5250.0, option_type=OptionSide.CALL, side=LegSide.SELL,
                price=1.60, delta=0.15, gamma=0.06, theta=-0.20,
            ),
            long_leg=_make_spread_leg(
                strike=5260.0, option_type=OptionSide.CALL, side=LegSide.BUY,
                price=0.90, delta=0.10, gamma=0.04, theta=-0.15,
            ),
            credit_received=0.70,
            max_loss=9.30,
            width=10.0,
            probability_otm=0.87,
            break_even=5250.70,
        )
        defaults: dict[str, Any] = dict(
            put_spread=put_spread,
            call_spread=call_spread,
            total_credit=1.50,
            max_loss=8.50,
            break_even_lower=5148.50,
            break_even_upper=5251.50,
            probability_profit=0.72,
        )
        defaults.update(overrides)
        return IronCondor(**defaults)

    def test_creation_valid(self) -> None:
        """A valid IronCondor should construct without error."""
        ic = self._make()
        assert ic.total_credit == 1.50

    def test_profit_zone_width(self) -> None:
        """profit_zone_width should be upper break-even minus lower."""
        ic = self._make(break_even_lower=5148.50, break_even_upper=5251.50)
        assert abs(ic.profit_zone_width - 103.0) < 1e-9

    def test_return_on_risk(self) -> None:
        """return_on_risk should be total_credit / max_loss * 100."""
        ic = self._make(total_credit=1.50, max_loss=8.50)
        expected = 1.50 / 8.50 * 100.0
        assert abs(ic.return_on_risk - expected) < 1e-6

    def test_reject_inverted_break_evens(self) -> None:
        """break_even_lower must be less than break_even_upper."""
        with pytest.raises(ValidationError):
            self._make(break_even_lower=5260.0, break_even_upper=5140.0)

    def test_reject_put_strike_above_call_strike(self) -> None:
        """Put spread short strike must sit below call spread short strike."""
        # Create an IC where put short strike >= call short strike
        put_spread = _make_credit_spread(
            short_leg=_make_spread_leg(
                strike=5260.0, option_type=OptionSide.PUT, side=LegSide.SELL,
                price=1.80, delta=-0.15, gamma=0.06, theta=-0.20,
            ),
            long_leg=_make_spread_leg(
                strike=5250.0, option_type=OptionSide.PUT, side=LegSide.BUY,
                price=1.00, delta=-0.10, gamma=0.04, theta=-0.15,
            ),
            credit_received=0.80, max_loss=9.20, width=10.0,
            probability_otm=0.85, break_even=5259.20,
        )
        call_spread = _make_credit_spread(
            short_leg=_make_spread_leg(
                strike=5250.0, option_type=OptionSide.CALL, side=LegSide.SELL,
                price=1.60, delta=0.15, gamma=0.06, theta=-0.20,
            ),
            long_leg=_make_spread_leg(
                strike=5260.0, option_type=OptionSide.CALL, side=LegSide.BUY,
                price=0.90, delta=0.10, gamma=0.04, theta=-0.15,
            ),
            credit_received=0.70, max_loss=9.30, width=10.0,
            probability_otm=0.87, break_even=5250.70,
        )
        with pytest.raises(ValidationError):
            IronCondor(
                put_spread=put_spread,
                call_spread=call_spread,
                total_credit=1.50,
                max_loss=8.50,
                break_even_lower=5148.50,
                break_even_upper=5251.50,
                probability_profit=0.72,
            )

    def test_probability_profit_bounds(self) -> None:
        """probability_profit must be between 0 and 1."""
        with pytest.raises(ValidationError):
            self._make(probability_profit=1.5)
        with pytest.raises(ValidationError):
            self._make(probability_profit=-0.1)


class TestTradeLog:
    """Tests for the TradeLog complete schema."""

    def _make(self, **overrides: Any) -> TradeLog:
        now = datetime.utcnow()
        defaults: dict[str, Any] = dict(
            timestamp_entry=now,
            scan_type=ScanType.DIRECTIONAL,
            direction=TradeDirection.BULL,
            strike=5200.0,
            option_type=OptionSide.CALL,
            entry_price=3.50,
            spx_at_entry=5195.0,
            vix1d_at_entry=14.5,
            vix_at_entry=16.0,
            expected_move_1sigma=15.0,
            composite_direction_score=55.0,
            session_type=SessionType.TRENDING,
            net_gex_at_entry=500000.0,
            gamma_flip_at_entry=5200.0,
            time_zone=TimeZoneType.MORNING_SESSION,
            delta_at_entry=0.35,
            gamma_at_entry=0.10,
            theta_at_entry=-0.40,
            iv_at_entry=0.18,
            tick_10min_avg=180.0,
            trin_at_entry=1.05,
            ad_ratio_at_entry=1.20,
            cumulative_delta_es=12000.0,
        )
        defaults.update(overrides)
        return TradeLog(**defaults)

    def test_creation_valid(self) -> None:
        """A complete TradeLog should construct without error."""
        tl = self._make()
        assert tl.strike == 5200.0

    def test_auto_uuid_generation(self) -> None:
        """trade_id must be auto-generated as a valid UUID4 string."""
        tl = self._make()
        # Should be parseable as a UUID
        parsed = uuid.UUID(tl.trade_id)
        assert parsed.version == 4

    def test_unique_trade_ids(self) -> None:
        """Each TradeLog instance must get a unique trade_id."""
        t1 = self._make()
        t2 = self._make()
        assert t1.trade_id != t2.trade_id

    def test_is_open_when_no_exit(self) -> None:
        """Trade with no exit timestamp is considered open."""
        tl = self._make(timestamp_exit=None)
        assert tl.is_open is True

    def test_not_open_when_exited(self) -> None:
        """Trade with exit timestamp is considered closed."""
        tl = self._make(timestamp_exit=datetime.utcnow())
        assert tl.is_open is False

    def test_is_winner_positive_pnl(self) -> None:
        """Positive realised PnL means a winning trade."""
        tl = self._make(pnl_dollars=150.0)
        assert tl.is_winner is True

    def test_is_not_winner_negative_pnl(self) -> None:
        """Negative realised PnL means a losing trade."""
        tl = self._make(pnl_dollars=-100.0)
        assert tl.is_winner is False

    def test_is_not_winner_when_none(self) -> None:
        """When pnl_dollars is None, trade is not classified as a winner."""
        tl = self._make(pnl_dollars=None)
        assert tl.is_winner is False

    def test_edge_ratio_with_drawdown(self) -> None:
        """edge_ratio = max_gain / abs(max_loss) when there is a drawdown."""
        tl = self._make(max_gain_during_trade=300.0, max_loss_during_trade=-100.0)
        assert tl.edge_ratio == 3.0

    def test_edge_ratio_none_when_no_drawdown(self) -> None:
        """edge_ratio is None when max_loss is zero (no drawdown)."""
        tl = self._make(max_gain_during_trade=200.0, max_loss_during_trade=0.0)
        assert tl.edge_ratio is None

    def test_reject_zero_strike(self) -> None:
        """Strike must be > 0."""
        with pytest.raises(ValidationError):
            self._make(strike=0)

    def test_reject_zero_entry_price(self) -> None:
        """entry_price must be > 0."""
        with pytest.raises(ValidationError):
            self._make(entry_price=0)

    def test_reject_direction_score_out_of_range(self) -> None:
        """composite_direction_score must be within [-100, +100]."""
        with pytest.raises(ValidationError):
            self._make(composite_direction_score=101.0)
        with pytest.raises(ValidationError):
            self._make(composite_direction_score=-101.0)

    def test_exit_reason_optional(self) -> None:
        """exit_reason can be None for open trades."""
        tl = self._make(exit_reason=None)
        assert tl.exit_reason is None

    @pytest.mark.parametrize(
        "reason",
        [
            ExitReason.PROFIT_TARGET,
            ExitReason.STOP_LOSS,
            ExitReason.TIME_STOP,
            ExitReason.SIGNAL_REVERSAL,
            ExitReason.GEX_FLIP,
            ExitReason.VIX_SPIKE,
            ExitReason.MANUAL,
            ExitReason.BREAK_EVEN,
        ],
    )
    def test_all_exit_reasons_accepted(self, reason: ExitReason) -> None:
        """Every ExitReason value must be accepted by TradeLog."""
        tl = self._make(exit_reason=reason)
        assert tl.exit_reason == reason


class TestFactorWeightsModel:
    """Tests for the FactorWeights Pydantic model (not the constants default)."""

    def test_valid_weights_sum_to_one(self) -> None:
        """Weights that sum to 1.0 should pass validation."""
        fw = FactorWeights(
            market_internals=0.30,
            options_flow=0.25,
            price_action=0.20,
            gex_structure=0.15,
            cross_asset=0.10,
        )
        assert abs(
            fw.market_internals + fw.options_flow + fw.price_action
            + fw.gex_structure + fw.cross_asset - 1.0
        ) < 1e-6

    def test_reject_weights_not_summing_to_one(self) -> None:
        """Weights not summing to 1.0 must raise ValidationError."""
        with pytest.raises(ValidationError):
            FactorWeights(
                market_internals=0.30,
                options_flow=0.25,
                price_action=0.20,
                gex_structure=0.15,
                cross_asset=0.15,  # Total = 1.05
            )

    def test_reject_negative_weight(self) -> None:
        """Negative weights must be rejected (ge=0)."""
        with pytest.raises(ValidationError):
            FactorWeights(
                market_internals=-0.10,
                options_flow=0.30,
                price_action=0.30,
                gex_structure=0.25,
                cross_asset=0.25,
            )

    def test_reject_weight_above_one(self) -> None:
        """Weight above 1.0 must be rejected (le=1.0)."""
        with pytest.raises(ValidationError):
            FactorWeights(
                market_internals=1.10,
                options_flow=0.0,
                price_action=0.0,
                gex_structure=0.0,
                cross_asset=0.0,
            )

    def test_as_dict_returns_five_keys(self) -> None:
        """as_dict() must return a dict with all five factor keys."""
        fw = FactorWeights(
            market_internals=0.20,
            options_flow=0.20,
            price_action=0.20,
            gex_structure=0.20,
            cross_asset=0.20,
        )
        d = fw.as_dict()
        assert len(d) == 5
        assert "market_internals" in d

    def test_equal_weights(self) -> None:
        """Five equal weights of 0.20 each should be valid."""
        fw = FactorWeights(
            market_internals=0.20,
            options_flow=0.20,
            price_action=0.20,
            gex_structure=0.20,
            cross_asset=0.20,
        )
        assert abs(sum(fw.as_dict().values()) - 1.0) < 1e-9


class TestCalibrationState:
    """Tests for the CalibrationState model."""

    def _make(self, **overrides: Any) -> CalibrationState:
        defaults: dict[str, Any] = dict(
            current_weights=FactorWeights(
                market_internals=0.30,
                options_flow=0.25,
                price_action=0.20,
                gex_structure=0.15,
                cross_asset=0.10,
            ),
            entry_threshold=40.0,
            stop_loss_pct=50.0,
            regime="NORMAL",
            last_calibration=datetime.utcnow(),
            trade_count=150,
            gex_signal_accuracy=0.65,
        )
        defaults.update(overrides)
        return CalibrationState(**defaults)

    def test_creation_valid(self) -> None:
        """CalibrationState should construct with valid inputs."""
        cs = self._make()
        assert cs.entry_threshold == 40.0

    def test_entry_threshold_bounds(self) -> None:
        """entry_threshold must be in [0, 100]."""
        with pytest.raises(ValidationError):
            self._make(entry_threshold=-1.0)
        with pytest.raises(ValidationError):
            self._make(entry_threshold=101.0)

    def test_stop_loss_positive(self) -> None:
        """stop_loss_pct must be > 0."""
        with pytest.raises(ValidationError):
            self._make(stop_loss_pct=0)

    def test_gex_signal_accuracy_bounds(self) -> None:
        """gex_signal_accuracy must be in [0, 1]."""
        with pytest.raises(ValidationError):
            self._make(gex_signal_accuracy=1.5)
        with pytest.raises(ValidationError):
            self._make(gex_signal_accuracy=-0.1)

    def test_trade_count_non_negative(self) -> None:
        """trade_count must be >= 0."""
        with pytest.raises(ValidationError):
            self._make(trade_count=-1)

    def test_regime_non_empty(self) -> None:
        """regime must be a non-empty string."""
        with pytest.raises(ValidationError):
            self._make(regime="")

    def test_profit_targets_by_zone_optional(self) -> None:
        """profit_targets_by_zone defaults to empty dict."""
        cs = self._make()
        assert cs.profit_targets_by_zone == {}

    def test_profit_targets_by_zone_populated(self) -> None:
        """profit_targets_by_zone can be populated with zone targets."""
        targets = {"MORNING_SESSION": 0.75, "POWER_HOUR": 0.40}
        cs = self._make(profit_targets_by_zone=targets)
        assert cs.profit_targets_by_zone["MORNING_SESSION"] == 0.75


class TestGapAnalysis:
    """Tests for the GapAnalysis model."""

    def _make(self, **overrides: Any) -> GapAnalysis:
        defaults: dict[str, Any] = dict(
            gap_pct=0.35,
            gap_points=18.2,
            gap_sigma=0.72,
            classification=GapClassification.SMALL,
        )
        defaults.update(overrides)
        return GapAnalysis(**defaults)

    def test_creation_valid(self) -> None:
        """Valid GapAnalysis should construct without error."""
        ga = self._make()
        assert ga.gap_pct == 0.35

    def test_is_gap_up(self) -> None:
        """Positive gap_points indicates a gap up."""
        ga = self._make(gap_points=18.0)
        assert ga.is_gap_up is True
        assert ga.is_gap_down is False

    def test_is_gap_down(self) -> None:
        """Negative gap_points indicates a gap down."""
        ga = self._make(gap_points=-12.0)
        assert ga.is_gap_down is True
        assert ga.is_gap_up is False

    def test_is_large_gap_true(self) -> None:
        """Gap exceeding 1 sigma is classified as large."""
        ga = self._make(gap_sigma=1.5)
        assert ga.is_large_gap is True

    def test_is_large_gap_false(self) -> None:
        """Gap within 1 sigma is not classified as large."""
        ga = self._make(gap_sigma=0.8)
        assert ga.is_large_gap is False

    def test_is_large_gap_negative_sigma(self) -> None:
        """Large gap detection works for negative sigma (gap down)."""
        ga = self._make(gap_sigma=-1.3)
        assert ga.is_large_gap is True

    @pytest.mark.parametrize(
        "classification",
        [
            GapClassification.MICRO,
            GapClassification.SMALL,
            GapClassification.MEDIUM,
            GapClassification.LARGE,
            GapClassification.MEGA,
        ],
    )
    def test_all_classifications_accepted(self, classification: GapClassification) -> None:
        """Every GapClassification value must be accepted."""
        ga = self._make(classification=classification)
        assert ga.classification == classification

    def test_gap_fill_probability_dict(self) -> None:
        """gap_fill_probability can hold horizon-keyed probabilities."""
        fills = {"30min": 0.45, "60min": 0.60, "eod": 0.78}
        ga = self._make(gap_fill_probability=fills)
        assert ga.gap_fill_probability["eod"] == 0.78


class TestExpectedMove:
    """Tests for the ExpectedMove model."""

    def _make(self, **overrides: Any) -> ExpectedMove:
        defaults: dict[str, Any] = dict(
            method1_vix1d=15.5,
            method2_straddle=16.2,
            method3_rv_adjusted=14.8,
            final_1sigma=15.5,
            final_2sigma=31.0,
            iv_rv_ratio=1.15,
            vol_regime="NORMAL",
        )
        defaults.update(overrides)
        return ExpectedMove(**defaults)

    def test_creation_valid(self) -> None:
        """ExpectedMove should construct with valid inputs."""
        em = self._make()
        assert em.final_1sigma == 15.5

    def test_2sigma_roughly_double_1sigma(self) -> None:
        """The 2-sigma move should be approximately 2x the 1-sigma move."""
        em = self._make(final_1sigma=15.0, final_2sigma=30.0)
        assert abs(em.final_2sigma / em.final_1sigma - 2.0) < 0.01

    def test_has_significant_iv_premium(self) -> None:
        """IV premium significant when iv_rv_ratio > 1.25."""
        em = self._make(iv_rv_ratio=1.35)
        assert em.has_significant_iv_premium is True

    def test_no_significant_iv_premium(self) -> None:
        """IV premium not significant when iv_rv_ratio <= 1.25."""
        em = self._make(iv_rv_ratio=1.10)
        assert em.has_significant_iv_premium is False

    def test_is_vol_compressed(self) -> None:
        """Vol compressed when iv_rv_ratio < 0.85."""
        em = self._make(iv_rv_ratio=0.80)
        assert em.is_vol_compressed is True

    def test_not_vol_compressed(self) -> None:
        """Not compressed when iv_rv_ratio >= 0.85."""
        em = self._make(iv_rv_ratio=0.90)
        assert em.is_vol_compressed is False

    def test_reject_negative_method_values(self) -> None:
        """Method values must be >= 0."""
        with pytest.raises(ValidationError):
            self._make(method1_vix1d=-1.0)

    def test_reject_zero_iv_rv_ratio(self) -> None:
        """iv_rv_ratio must be > 0."""
        with pytest.raises(ValidationError):
            self._make(iv_rv_ratio=0)

    def test_reject_empty_vol_regime(self) -> None:
        """vol_regime must be non-empty."""
        with pytest.raises(ValidationError):
            self._make(vol_regime="")


class TestKeyLevels:
    """Tests for the KeyLevels model."""

    def test_creation_valid(self) -> None:
        """KeyLevels should construct with valid inputs."""
        kl = _make_key_levels()
        assert kl.max_pain == 5200.0

    def test_prior_range(self) -> None:
        """prior_range should be prior_high - prior_low."""
        kl = _make_key_levels(prior_high=5240.0, prior_low=5160.0)
        assert abs(kl.prior_range - 80.0) < 1e-9

    def test_overnight_range(self) -> None:
        """overnight_range should be overnight_high - overnight_low."""
        kl = _make_key_levels(overnight_high=5225.0, overnight_low=5185.0)
        assert abs(kl.overnight_range - 40.0) < 1e-9

    def test_all_levels_sorted(self) -> None:
        """all_levels_sorted must return a sorted, deduped list."""
        kl = _make_key_levels()
        levels = kl.all_levels_sorted()
        assert levels == sorted(levels)
        # No duplicates
        assert len(levels) == len(set(levels))

    def test_all_levels_includes_round_levels(self) -> None:
        """Round levels should be included in all_levels_sorted."""
        kl = _make_key_levels(round_levels=[5100.0, 5300.0])
        levels = kl.all_levels_sorted()
        assert 5100.0 in levels
        assert 5300.0 in levels

    def test_all_levels_includes_moving_averages(self) -> None:
        """Moving averages should be included in all_levels_sorted."""
        kl = _make_key_levels(moving_averages={"SMA_20": 5190.5})
        levels = kl.all_levels_sorted()
        assert 5190.5 in levels

    def test_reject_zero_price_levels(self) -> None:
        """All price levels must be > 0."""
        with pytest.raises(ValidationError):
            _make_key_levels(max_pain=0)
        with pytest.raises(ValidationError):
            _make_key_levels(prior_close=0)


class TestSessionSetup:
    """Tests for the SessionSetup composite model."""

    def _make(self, **overrides: Any) -> SessionSetup:
        gap = GapAnalysis(
            gap_pct=0.2, gap_points=10.0, gap_sigma=0.5,
            classification=GapClassification.SMALL,
        )
        em = ExpectedMove(
            method1_vix1d=15.0, method2_straddle=16.0, method3_rv_adjusted=14.0,
            final_1sigma=15.0, final_2sigma=30.0, iv_rv_ratio=1.15, vol_regime="NORMAL",
        )
        kl = _make_key_levels()
        defaults: dict[str, Any] = dict(
            gap_analysis=gap,
            expected_move=em,
            key_levels=kl,
            session_type=SessionType.TRENDING,
            risk_assessment="Normal risk day. No major events.",
        )
        defaults.update(overrides)
        return SessionSetup(**defaults)

    def test_creation_valid(self) -> None:
        """SessionSetup should construct with valid inputs."""
        ss = self._make()
        assert ss.session_type == SessionType.TRENDING

    def test_has_high_impact_events_false(self) -> None:
        """No economic events means no high-impact events."""
        ss = self._make(economic_events=[])
        assert ss.has_high_impact_events is False
        assert ss.high_impact_event_count == 0

    def test_has_high_impact_events_true(self) -> None:
        """A HIGH impact event should trigger has_high_impact_events."""
        event = EconomicEvent(
            time=datetime.utcnow(),
            name="FOMC Rate Decision",
            impact_level=ImpactLevel.HIGH,
        )
        ss = self._make(economic_events=[event])
        assert ss.has_high_impact_events is True
        assert ss.high_impact_event_count == 1

    def test_is_event_day_by_session_type(self) -> None:
        """EVENT session type should flag as event day."""
        ss = self._make(session_type=SessionType.EVENT)
        assert ss.is_event_day is True

    def test_is_event_day_by_high_impact(self) -> None:
        """High impact event flags event day even if session type is not EVENT."""
        event = EconomicEvent(
            time=datetime.utcnow(),
            name="CPI Release",
            impact_level=ImpactLevel.HIGH,
        )
        ss = self._make(
            session_type=SessionType.TRENDING,
            economic_events=[event],
        )
        assert ss.is_event_day is True

    def test_not_event_day(self) -> None:
        """Non-EVENT session with no high-impact events is not an event day."""
        low_event = EconomicEvent(
            time=datetime.utcnow(),
            name="Redbook Index",
            impact_level=ImpactLevel.LOW,
        )
        ss = self._make(
            session_type=SessionType.RANGE,
            economic_events=[low_event],
        )
        assert ss.is_event_day is False

    def test_risk_assessment_non_empty(self) -> None:
        """risk_assessment must be non-empty."""
        with pytest.raises(ValidationError):
            self._make(risk_assessment="")


class TestESOrderBook:
    """Tests for the ESOrderBook model."""

    def _make(self, **overrides: Any) -> ESOrderBook:
        defaults: dict[str, Any] = dict(
            bid_levels=[(5200.25, 150), (5200.00, 200)],
            ask_levels=[(5200.50, 120), (5200.75, 180)],
            bid_total=350,
            ask_total=300,
            imbalance_ratio=0.077,
        )
        defaults.update(overrides)
        return ESOrderBook(**defaults)

    def test_creation_valid(self) -> None:
        """ESOrderBook should construct with valid data."""
        ob = self._make()
        assert ob.bid_total == 350

    def test_imbalance_ratio_clamped_high(self) -> None:
        """Imbalance ratio above 1.0 should be clamped to 1.0."""
        ob = self._make(imbalance_ratio=1.5)
        assert ob.imbalance_ratio == 1.0

    def test_imbalance_ratio_clamped_low(self) -> None:
        """Imbalance ratio below -1.0 should be clamped to -1.0."""
        ob = self._make(imbalance_ratio=-1.5)
        assert ob.imbalance_ratio == -1.0

    def test_is_bid_heavy(self) -> None:
        """Imbalance > 0.25 is bid-heavy."""
        ob = self._make(imbalance_ratio=0.40)
        assert ob.is_bid_heavy is True
        assert ob.is_ask_heavy is False

    def test_is_ask_heavy(self) -> None:
        """Imbalance < -0.25 is ask-heavy."""
        ob = self._make(imbalance_ratio=-0.40)
        assert ob.is_ask_heavy is True
        assert ob.is_bid_heavy is False


class TestGEXSignal:
    """Tests for the GEXSignal model."""

    def _make(self, **overrides: Any) -> GEXSignal:
        defaults: dict[str, Any] = dict(
            signal_type=GEXSignalType.GAMMA_FLIP_CROSSOVER,
            direction=TradeDirection.BULL,
            confidence=75.0,
            description="Gamma flip crossover detected at 5205",
            trigger_price=5205.0,
        )
        defaults.update(overrides)
        return GEXSignal(**defaults)

    def test_creation_valid(self) -> None:
        """GEXSignal should construct with valid data."""
        gs = self._make()
        assert gs.signal_type == GEXSignalType.GAMMA_FLIP_CROSSOVER

    def test_confidence_rounded(self) -> None:
        """Confidence should be rounded to 2 decimal places."""
        gs = self._make(confidence=75.567)
        assert gs.confidence == 75.57

    def test_reject_confidence_above_100(self) -> None:
        """Confidence above 100 is invalid."""
        with pytest.raises(ValidationError):
            self._make(confidence=101.0)

    def test_reject_confidence_below_zero(self) -> None:
        """Confidence below 0 is invalid."""
        with pytest.raises(ValidationError):
            self._make(confidence=-1.0)

    def test_target_price_optional(self) -> None:
        """target_price can be None."""
        gs = self._make(target_price=None)
        assert gs.target_price is None

    def test_target_price_must_be_positive(self) -> None:
        """target_price, if set, must be > 0."""
        with pytest.raises(ValidationError):
            self._make(target_price=0)

    def test_metadata_default_empty(self) -> None:
        """metadata defaults to an empty dict."""
        gs = self._make()
        assert gs.metadata == {}


class TestSpreadLeg:
    """Tests for the SpreadLeg model."""

    def test_creation_valid(self) -> None:
        """A valid SpreadLeg should construct without error."""
        leg = _make_spread_leg()
        assert leg.strike == 5200.0

    def test_is_short_sell(self) -> None:
        """A SELL leg should be identified as short."""
        leg = _make_spread_leg(side=LegSide.SELL)
        assert leg.is_short is True

    def test_is_not_short_buy(self) -> None:
        """A BUY leg should not be identified as short."""
        leg = _make_spread_leg(side=LegSide.BUY)
        assert leg.is_short is False

    def test_reject_zero_strike(self) -> None:
        """Strike must be > 0."""
        with pytest.raises(ValidationError):
            _make_spread_leg(strike=0)

    def test_reject_negative_price(self) -> None:
        """Price must be >= 0."""
        with pytest.raises(ValidationError):
            _make_spread_leg(price=-1.0)

    def test_reject_positive_theta(self) -> None:
        """Theta must be <= 0."""
        with pytest.raises(ValidationError):
            _make_spread_leg(theta=0.1)


class TestEconomicEvent:
    """Tests for the EconomicEvent model."""

    def _make(self, **overrides: Any) -> EconomicEvent:
        defaults: dict[str, Any] = dict(
            time=datetime.utcnow(),
            name="Non-Farm Payrolls",
            impact_level=ImpactLevel.HIGH,
        )
        defaults.update(overrides)
        return EconomicEvent(**defaults)

    def test_creation_valid(self) -> None:
        """EconomicEvent should construct with valid inputs."""
        ee = self._make()
        assert ee.name == "Non-Farm Payrolls"

    def test_is_released_false(self) -> None:
        """Before release, actual_value is None."""
        ee = self._make(actual_value=None)
        assert ee.is_released is False

    def test_is_released_true(self) -> None:
        """After release, actual_value is populated."""
        ee = self._make(actual_value="256K")
        assert ee.is_released is True

    def test_is_high_impact(self) -> None:
        """HIGH impact events are flagged."""
        ee = self._make(impact_level=ImpactLevel.HIGH)
        assert ee.is_high_impact is True

    def test_is_not_high_impact(self) -> None:
        """LOW and MED are not high impact."""
        ee_low = self._make(impact_level=ImpactLevel.LOW)
        ee_med = self._make(impact_level=ImpactLevel.MED)
        assert ee_low.is_high_impact is False
        assert ee_med.is_high_impact is False

    def test_reject_empty_name(self) -> None:
        """Event name must be non-empty."""
        with pytest.raises(ValidationError):
            self._make(name="")


class TestDailyScoreCard:
    """Tests for the DailyScoreCard model."""

    def test_creation_with_defaults(self) -> None:
        """DailyScoreCard should accept just a trading_date."""
        from src.scanify_0dte.models import DailyScoreCard

        sc = DailyScoreCard(trading_date=date(2025, 5, 15))
        assert sc.trading_date == date(2025, 5, 15)
        assert sc.win_rate_by_scan_type == {}

    def test_populated_scorecard(self) -> None:
        """DailyScoreCard fields can be populated with dimensional data."""
        from src.scanify_0dte.models import DailyScoreCard

        sc = DailyScoreCard(
            trading_date=date(2025, 5, 15),
            win_rate_by_scan_type={"DIRECTIONAL": 0.65, "PREMIUM_SELL": 0.72},
            avg_pnl_by_scan_type={"DIRECTIONAL": 125.0, "PREMIUM_SELL": 85.0},
        )
        assert sc.win_rate_by_scan_type["DIRECTIONAL"] == 0.65
        assert sc.avg_pnl_by_scan_type["PREMIUM_SELL"] == 85.0
