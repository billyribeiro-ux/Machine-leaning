"""
Comprehensive test suite for SCANIFY 0DTE Visualization Module.
================================================================

Tests the data-preparation layer in ``src/scanify_0dte/visualization.py``
which transforms scanner, GEX engine, and calibration outputs into
chart-ready JSON-serialisable dictionaries consumed by the Next.js / Tauri
frontend.

Sections
--------
1. Helper Functions          -- format_currency, format_percentage,
                                color_for_value, generate_chart_colors,
                                time_axis_labels
2. GEX Visualization         -- gex_bar_chart, gex_heatmap,
                                gamma_flip_timeline, key_levels_diagram
3. Scanner Visualization      -- direction_score_gauge, signal_timeline,
                                factor_contribution_chart,
                                strike_selection_overlay
4. Performance Visualization  -- intraday_pnl_curve, pnl_distribution,
                                win_rate_by_category, equity_curve,
                                drawdown_chart
5. Calibration Visualization  -- weight_evolution, threshold_evolution,
                                regime_timeline, gex_accuracy_chart
6. JSON Serialisability       -- all outputs pass json.dumps without error
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta
from typing import Any, Optional

import pytest

from src.scanify_0dte.models import (
    DirectionScore,
    ExitReason,
    ExpectedMove,
    FactorWeights,
    GapAnalysis,
    GapClassification,
    GEXProfile,
    KeyLevels,
    OptionQuote,
    OptionsChain,
    OptionSide,
    PositionType,
    ScanSignal,
    ScanType,
    SessionSetup,
    SessionType,
    StrikeGEX,
    StrikeSelection,
    TimeZoneType,
    TradeDirection,
    TradeLog,
)
from src.scanify_0dte.visualization import (
    CalibrationVisualization,
    GEXVisualization,
    PerformanceVisualization,
    ScannerVisualization,
    color_for_value,
    format_currency,
    format_percentage,
    generate_chart_colors,
    time_axis_labels,
)


# =========================================================================
# FIXTURES -- Reusable mock data for all test sections
# =========================================================================


def _make_strike_gex(
    strike: float,
    dealer_gamma_call: float = 1.0,
    dealer_gamma_put: float = -0.5,
    net_gex: float = 0.5,
) -> StrikeGEX:
    """Factory for a minimal StrikeGEX dataclass instance."""
    return StrikeGEX(
        strike=strike,
        call_gamma=abs(dealer_gamma_call) * 0.01,
        put_gamma=abs(dealer_gamma_put) * 0.01,
        call_oi=5000,
        put_oi=4000,
        dealer_gamma_call=dealer_gamma_call,
        dealer_gamma_put=dealer_gamma_put,
        net_gex=net_gex,
        net_charm=0.01,
        net_vanna=0.02,
        net_speed=0.001,
    )


@pytest.fixture
def sample_strike_gex_list() -> list[StrikeGEX]:
    """Five strikes spanning 5200-5240 with varying GEX profiles."""
    return [
        _make_strike_gex(5200.0, 0.5, -1.5, -1.0),
        _make_strike_gex(5210.0, 1.0, -0.8, 0.2),
        _make_strike_gex(5220.0, 2.0, -0.5, 1.5),
        _make_strike_gex(5230.0, 3.0, -0.3, 2.7),
        _make_strike_gex(5240.0, 1.5, -0.2, 1.3),
    ]


@pytest.fixture
def sample_gex_profile(sample_strike_gex_list) -> GEXProfile:
    """A realistic GEX profile snapshot."""
    return GEXProfile(
        timestamp=datetime(2025, 5, 15, 10, 30, 0),
        strikes=sample_strike_gex_list,
        total_net_gex=4.7,
        gamma_flip_level=5215.0,
        call_wall=5230.0,
        put_wall=5200.0,
        max_pain=5220.0,
        plus_gex=5230.0,
        minus_gex=5200.0,
        transition_zone_upper=5220.0,
        transition_zone_lower=5210.0,
        vol_trigger=5225.0,
        gex_momentum=0.15,
        charm_net_es_contracts=12.5,
        vanna_net_exposure=-3.2,
    )


@pytest.fixture
def sample_gex_profiles_history(sample_strike_gex_list) -> list[GEXProfile]:
    """Three time-ordered GEX profile snapshots for heatmap / timeline tests."""
    profiles = []
    base_time = datetime(2025, 5, 15, 9, 30, 0)
    for i in range(3):
        ts = base_time + timedelta(minutes=30 * i)
        shift = i * 0.5
        strikes = [
            _make_strike_gex(5200.0 + j * 10, 0.5 + shift, -1.0 + shift * 0.3, -0.5 + shift + j * 0.3)
            for j in range(5)
        ]
        profiles.append(
            GEXProfile(
                timestamp=ts,
                strikes=strikes,
                total_net_gex=2.0 + i * 1.5,
                gamma_flip_level=5215.0 + i * 2,
                call_wall=5230.0 + i,
                put_wall=5200.0 - i,
                max_pain=5220.0,
                plus_gex=5230.0,
                minus_gex=5200.0,
                transition_zone_upper=5220.0,
                transition_zone_lower=5210.0,
                vol_trigger=5225.0,
            )
        )
    return profiles


@pytest.fixture
def sample_direction_score() -> DirectionScore:
    """A bullish DirectionScore with moderate conviction."""
    return DirectionScore(
        total_score=55.0,
        market_internals_score=60.0,
        options_flow_score=50.0,
        price_action_score=45.0,
        gex_structure_score=70.0,
        cross_asset_score=30.0,
        factors_agreeing=4,
        has_opposing_factor=True,
        signal=TradeDirection.BULL,
        confidence=72.0,
        timestamp=datetime(2025, 5, 15, 10, 30, 0),
    )


@pytest.fixture
def sample_bearish_direction_score() -> DirectionScore:
    """A bearish DirectionScore for colour-coding tests."""
    return DirectionScore(
        total_score=-62.0,
        market_internals_score=-55.0,
        options_flow_score=-70.0,
        price_action_score=-60.0,
        gex_structure_score=-45.0,
        cross_asset_score=-80.0,
        factors_agreeing=5,
        has_opposing_factor=False,
        signal=TradeDirection.BEAR,
        confidence=88.0,
        timestamp=datetime(2025, 5, 15, 11, 0, 0),
    )


@pytest.fixture
def sample_strike_selection() -> StrikeSelection:
    """A selected OTM call at 5230."""
    return StrikeSelection(
        strike=5230.0,
        option_type=OptionSide.CALL,
        delta=0.35,
        gamma=0.02,
        theta=-0.85,
        iv=0.18,
        bid=3.40,
        ask=3.80,
        mid=3.60,
        spread_width=0.40,
        oi=12000,
        volume=4500,
        is_liquid=True,
        distance_from_spot=10.0,
        moneyness=1.0019,
    )


@pytest.fixture
def sample_scan_signal(sample_direction_score, sample_strike_selection) -> ScanSignal:
    """A bullish directional scan signal."""
    return ScanSignal(
        scan_type=ScanType.DIRECTIONAL,
        direction=TradeDirection.BULL,
        strike_selection=sample_strike_selection,
        direction_score=sample_direction_score,
        entry_price=3.60,
        stop_loss=1.80,
        profit_target=7.20,
        position_type=PositionType.SINGLE_LONG,
        contracts=2,
        max_risk=360.0,
        expected_reward=720.0,
        risk_reward_ratio=2.0,
        time_zone=TimeZoneType.MORNING_SESSION,
        session_type=SessionType.TRENDING,
        timestamp=datetime(2025, 5, 15, 10, 30, 0),
    )


def _make_trade_log(
    pnl: float,
    scan_type: ScanType = ScanType.DIRECTIONAL,
    direction: TradeDirection = TradeDirection.BULL,
    time_zone: TimeZoneType = TimeZoneType.MORNING_SESSION,
    session_type: SessionType = SessionType.TRENDING,
    hold_minutes: float = 25.0,
    entry_offset_minutes: int = 0,
) -> TradeLog:
    """Factory for a closed TradeLog with specified P&L."""
    base_entry = datetime(2025, 5, 15, 10, 0, 0) + timedelta(minutes=entry_offset_minutes)
    base_exit = base_entry + timedelta(minutes=hold_minutes)
    return TradeLog(
        timestamp_entry=base_entry,
        timestamp_exit=base_exit,
        scan_type=scan_type,
        direction=direction,
        strike=5220.0,
        option_type=OptionSide.CALL,
        entry_price=4.00,
        exit_price=4.00 + pnl / 100.0,
        pnl_dollars=pnl,
        pnl_percent=(pnl / 400.0) * 100.0,
        hold_time_minutes=hold_minutes,
        max_gain_during_trade=max(pnl, 0.0) * 1.2,
        max_loss_during_trade=min(pnl, 0.0) * 1.1,
        spx_at_entry=5220.0,
        vix1d_at_entry=14.5,
        vix_at_entry=16.2,
        expected_move_1sigma=18.5,
        composite_direction_score=55.0 if direction == TradeDirection.BULL else -55.0,
        session_type=session_type,
        net_gex_at_entry=4.7,
        gamma_flip_at_entry=5215.0,
        time_zone=time_zone,
        delta_at_entry=0.35,
        gamma_at_entry=0.02,
        theta_at_entry=-0.85,
        iv_at_entry=0.18,
        tick_10min_avg=250.0,
        trin_at_entry=0.95,
        ad_ratio_at_entry=1.3,
        cumulative_delta_es=15000.0,
        exit_reason=ExitReason.PROFIT_TARGET if pnl > 0 else ExitReason.STOP_LOSS,
    )


@pytest.fixture
def sample_trades() -> list[TradeLog]:
    """A mix of winning and losing trades across categories."""
    return [
        # Directional wins
        _make_trade_log(150.0, ScanType.DIRECTIONAL, TradeDirection.BULL,
                        TimeZoneType.MORNING_SESSION, SessionType.TRENDING,
                        20.0, 0),
        _make_trade_log(200.0, ScanType.DIRECTIONAL, TradeDirection.BULL,
                        TimeZoneType.MORNING_SESSION, SessionType.TRENDING,
                        35.0, 30),
        # Directional loss
        _make_trade_log(-120.0, ScanType.DIRECTIONAL, TradeDirection.BEAR,
                        TimeZoneType.AFTERNOON_ACCEL, SessionType.VOLATILE,
                        15.0, 60),
        # Premium sell win
        _make_trade_log(80.0, ScanType.PREMIUM_SELL, TradeDirection.NEUTRAL,
                        TimeZoneType.MIDDAY_LULL, SessionType.RANGE,
                        45.0, 90),
        # Premium sell loss
        _make_trade_log(-200.0, ScanType.PREMIUM_SELL, TradeDirection.NEUTRAL,
                        TimeZoneType.POWER_HOUR, SessionType.VOLATILE,
                        10.0, 120),
        # Gamma scalp win
        _make_trade_log(300.0, ScanType.GAMMA_SCALP, TradeDirection.BULL,
                        TimeZoneType.POWER_HOUR, SessionType.VOLATILE,
                        8.0, 150),
        # Gamma scalp loss
        _make_trade_log(-50.0, ScanType.GAMMA_SCALP, TradeDirection.BEAR,
                        TimeZoneType.SETTLEMENT_WINDOW, SessionType.TRENDING,
                        5.0, 180),
    ]


@pytest.fixture
def sample_option_quotes() -> list[OptionQuote]:
    """Option quotes for an OptionsChain fixture."""
    base_ts = datetime(2025, 5, 15, 10, 30, 0)
    quotes = []
    for strike in [5210.0, 5220.0, 5230.0]:
        quotes.append(
            OptionQuote(
                strike=strike,
                option_type=OptionSide.CALL,
                bid=max(10.0 - (strike - 5210.0) * 0.3, 0.5),
                ask=max(10.0 - (strike - 5210.0) * 0.3 + 0.40, 0.9),
                mid=max(10.0 - (strike - 5210.0) * 0.3 + 0.20, 0.7),
                last=max(10.0 - (strike - 5210.0) * 0.3 + 0.15, 0.65),
                volume=3000,
                open_interest=15000,
                implied_vol=0.20,
                delta=max(0.6 - (strike - 5210.0) * 0.012, 0.1),
                gamma=0.015,
                theta=-0.90,
                vega=0.45,
                timestamp=base_ts,
            )
        )
        quotes.append(
            OptionQuote(
                strike=strike,
                option_type=OptionSide.PUT,
                bid=max(0.5 + (strike - 5210.0) * 0.2, 0.3),
                ask=max(0.5 + (strike - 5210.0) * 0.2 + 0.40, 0.7),
                mid=max(0.5 + (strike - 5210.0) * 0.2 + 0.20, 0.5),
                last=max(0.5 + (strike - 5210.0) * 0.2 + 0.15, 0.45),
                volume=2500,
                open_interest=12000,
                implied_vol=0.22,
                delta=-(0.4 + (strike - 5210.0) * 0.008),
                gamma=0.014,
                theta=-0.80,
                vega=0.40,
                timestamp=base_ts,
            )
        )
    return quotes


@pytest.fixture
def sample_options_chain(sample_option_quotes) -> OptionsChain:
    """An OptionsChain with 3 strikes (call + put each)."""
    return OptionsChain(
        expiry_date=date(2025, 5, 15),
        underlying_price=5220.0,
        quotes=sample_option_quotes,
        timestamp=datetime(2025, 5, 15, 10, 30, 0),
    )


@pytest.fixture
def sample_key_levels() -> KeyLevels:
    """Key levels for a SessionSetup fixture."""
    return KeyLevels(
        max_pain=5220.0,
        plus_gex=5230.0,
        minus_gex=5200.0,
        call_wall=5240.0,
        put_wall=5190.0,
        gamma_flip=5215.0,
        vol_trigger=5225.0,
        transition_zone_upper=5220.0,
        transition_zone_lower=5210.0,
        prior_high=5235.0,
        prior_low=5195.0,
        prior_close=5218.0,
        prior_vwap=5215.5,
        overnight_high=5228.0,
        overnight_low=5205.0,
        round_levels=[5200.0, 5250.0],
        moving_averages={"SMA_20": 5210.5, "EMA_9": 5222.0},
    )


@pytest.fixture
def sample_expected_move() -> ExpectedMove:
    return ExpectedMove(
        method1_vix1d=18.0,
        method2_straddle=20.0,
        method3_rv_adjusted=16.5,
        final_1sigma=18.5,
        final_2sigma=37.0,
        iv_rv_ratio=1.15,
        vol_regime="NORMAL",
    )


@pytest.fixture
def sample_gap_analysis() -> GapAnalysis:
    return GapAnalysis(
        gap_pct=0.12,
        gap_points=6.3,
        gap_sigma=0.34,
        classification=GapClassification.SMALL,
        gap_fill_probability={"30min": 0.45, "60min": 0.60, "eod": 0.78},
    )


@pytest.fixture
def sample_session_setup(
    sample_gap_analysis, sample_expected_move, sample_key_levels
) -> SessionSetup:
    return SessionSetup(
        gap_analysis=sample_gap_analysis,
        expected_move=sample_expected_move,
        key_levels=sample_key_levels,
        session_type=SessionType.TRENDING,
        economic_events=[],
        risk_assessment="Normal risk environment for 0DTE trading.",
        timestamp=datetime(2025, 5, 15, 9, 15, 0),
    )


@pytest.fixture
def sample_factor_weights_history() -> list[FactorWeights]:
    """Three calibration cycles of factor weight snapshots."""
    return [
        FactorWeights(
            market_internals=0.30,
            options_flow=0.25,
            price_action=0.20,
            gex_structure=0.15,
            cross_asset=0.10,
        ),
        FactorWeights(
            market_internals=0.28,
            options_flow=0.26,
            price_action=0.21,
            gex_structure=0.16,
            cross_asset=0.09,
        ),
        FactorWeights(
            market_internals=0.27,
            options_flow=0.27,
            price_action=0.22,
            gex_structure=0.15,
            cross_asset=0.09,
        ),
    ]


# =========================================================================
# 1. HELPER FUNCTIONS
# =========================================================================


class TestFormatCurrency:
    """Tests for format_currency()."""

    def test_positive_value(self):
        assert format_currency(1234.56) == "$1,234.56"

    def test_negative_value(self):
        assert format_currency(-42.10) == "-$42.10"

    def test_zero(self):
        assert format_currency(0.0) == "$0.00"

    def test_large_value(self):
        result = format_currency(1_000_000.99)
        assert result == "$1,000,000.99"

    def test_small_positive(self):
        assert format_currency(0.01) == "$0.01"

    def test_small_negative(self):
        assert format_currency(-0.01) == "-$0.01"

    def test_dollar_sign_present(self):
        result = format_currency(500.0)
        assert "$" in result

    def test_two_decimal_places(self):
        result = format_currency(100.1)
        # Should be $100.10
        assert result.endswith(".10")

    def test_thousands_separator(self):
        result = format_currency(9999.0)
        assert "," in result  # $9,999.00


class TestFormatPercentage:
    """Tests for format_percentage()."""

    def test_positive_value(self):
        result = format_percentage(42.5)
        assert result == "+42.50%"

    def test_negative_value(self):
        result = format_percentage(-3.12)
        assert result == "-3.12%"

    def test_zero(self):
        result = format_percentage(0.0)
        assert result == "0.00%"
        # Zero should have no sign prefix
        assert not result.startswith("+")

    def test_percent_sign_present(self):
        result = format_percentage(10.0)
        assert "%" in result

    def test_positive_sign_prefix(self):
        result = format_percentage(5.0)
        assert result.startswith("+")

    def test_two_decimal_places(self):
        result = format_percentage(1.1)
        assert result == "+1.10%"


class TestColorForValue:
    """Tests for color_for_value() -- red-amber-green interpolation."""

    def test_min_value_returns_red(self):
        result = color_for_value(0.0, 0.0, 100.0)
        assert result == "#ef4444"

    def test_max_value_returns_green(self):
        result = color_for_value(100.0, 0.0, 100.0)
        assert result == "#22c55e"

    def test_midpoint_returns_amber(self):
        result = color_for_value(50.0, 0.0, 100.0)
        assert result == "#f59e0b"

    def test_equal_min_max_returns_amber(self):
        result = color_for_value(5.0, 5.0, 5.0)
        assert result == "#f59e0b"

    def test_below_min_clamps_to_red(self):
        result = color_for_value(-50.0, 0.0, 100.0)
        assert result == "#ef4444"

    def test_above_max_clamps_to_green(self):
        result = color_for_value(200.0, 0.0, 100.0)
        assert result == "#22c55e"

    def test_returns_valid_hex_string(self):
        result = color_for_value(25.0, 0.0, 100.0)
        assert result.startswith("#")
        assert len(result) == 7
        # All characters after # should be valid hex
        int(result[1:], 16)

    def test_interpolation_between_red_and_amber(self):
        """A value at 25% should be between red and amber."""
        result = color_for_value(25.0, 0.0, 100.0)
        assert result.startswith("#")
        r = int(result[1:3], 16)
        # Red channel should be between 0xEF and 0xF5
        assert 0xEF <= r <= 0xF5

    def test_interpolation_between_amber_and_green(self):
        """A value at 75% should be between amber and green."""
        result = color_for_value(75.0, 0.0, 100.0)
        assert result.startswith("#")
        r = int(result[1:3], 16)
        # Red channel should be moving from 0xF5 toward 0x22
        assert r < 0xF5

    def test_negative_range(self):
        """Works with negative min/max values."""
        result = color_for_value(0.0, -100.0, 100.0)
        # 0.0 is the midpoint of [-100, 100], should be amber
        assert result == "#f59e0b"


class TestGenerateChartColors:
    """Tests for generate_chart_colors()."""

    def test_returns_correct_count(self):
        colors = generate_chart_colors(5)
        assert len(colors) == 5

    def test_returns_empty_for_zero(self):
        assert generate_chart_colors(0) == []

    def test_returns_empty_for_negative(self):
        assert generate_chart_colors(-1) == []

    def test_all_are_hex_strings(self):
        colors = generate_chart_colors(10)
        for c in colors:
            assert c.startswith("#")
            assert len(c) == 7
            int(c[1:], 16)

    def test_distinct_for_small_n(self):
        """For N <= palette size, all colors should be distinct."""
        colors = generate_chart_colors(8)
        assert len(set(colors)) == 8

    def test_wraps_beyond_palette_size(self):
        """For N > 16, colors should cycle."""
        colors = generate_chart_colors(20)
        assert len(colors) == 20
        assert colors[0] == colors[16]
        assert colors[1] == colors[17]

    def test_single_color(self):
        colors = generate_chart_colors(1)
        assert len(colors) == 1
        assert colors[0] == "#3b82f6"  # First palette entry is blue


class TestTimeAxisLabels:
    """Tests for time_axis_labels()."""

    def test_basic_formatting(self):
        timestamps = [datetime(2025, 5, 15, 9, 30), datetime(2025, 5, 15, 10, 0)]
        labels = time_axis_labels(timestamps)
        assert labels == ["09:30", "10:00"]

    def test_empty_list(self):
        assert time_axis_labels([]) == []

    def test_preserves_order(self):
        timestamps = [
            datetime(2025, 5, 15, 14, 0),
            datetime(2025, 5, 15, 9, 30),
        ]
        labels = time_axis_labels(timestamps)
        assert labels == ["14:00", "09:30"]


# =========================================================================
# 2. GEX VISUALIZATION
# =========================================================================


class TestGEXBarChart:
    """Tests for GEXVisualization.gex_bar_chart()."""

    def test_returns_correct_chart_type(self, sample_gex_profile):
        result = GEXVisualization.gex_bar_chart(sample_gex_profile, 5220.0)
        assert result["chart_type"] == "gex_bar"

    def test_strikes_sorted_ascending(self, sample_gex_profile):
        result = GEXVisualization.gex_bar_chart(sample_gex_profile, 5220.0)
        assert result["strikes"] == sorted(result["strikes"])

    def test_has_call_put_net_gex_series(self, sample_gex_profile):
        result = GEXVisualization.gex_bar_chart(sample_gex_profile, 5220.0)
        assert "call_gex" in result
        assert "put_gex" in result
        assert "net_gex" in result
        assert len(result["call_gex"]) == len(result["strikes"])
        assert len(result["put_gex"]) == len(result["strikes"])
        assert len(result["net_gex"]) == len(result["strikes"])

    def test_includes_spot_price(self, sample_gex_profile):
        result = GEXVisualization.gex_bar_chart(sample_gex_profile, 5220.0)
        assert result["spot"] == 5220.0

    def test_includes_gamma_flip(self, sample_gex_profile):
        result = GEXVisualization.gex_bar_chart(sample_gex_profile, 5220.0)
        assert result["gamma_flip"] == 5215.0

    def test_includes_walls(self, sample_gex_profile):
        result = GEXVisualization.gex_bar_chart(sample_gex_profile, 5220.0)
        assert result["call_wall"] == 5230.0
        assert result["put_wall"] == 5200.0

    def test_annotations_present(self, sample_gex_profile):
        result = GEXVisualization.gex_bar_chart(sample_gex_profile, 5220.0)
        annotations = result["annotations"]
        assert len(annotations) == 5
        labels = {a["label"] for a in annotations}
        assert "Gamma Flip" in labels
        assert "Call Wall" in labels
        assert "Put Wall" in labels
        assert "Max Pain" in labels
        assert "Vol Trigger" in labels

    def test_annotation_structure(self, sample_gex_profile):
        result = GEXVisualization.gex_bar_chart(sample_gex_profile, 5220.0)
        for ann in result["annotations"]:
            assert "strike" in ann
            assert "label" in ann
            assert "color" in ann
            assert isinstance(ann["strike"], float)

    def test_transition_zone_is_two_element_list(self, sample_gex_profile):
        result = GEXVisualization.gex_bar_chart(sample_gex_profile, 5220.0)
        tz = result["transition_zone"]
        assert isinstance(tz, list)
        assert len(tz) == 2
        assert tz[0] <= tz[1]

    def test_regime_field(self, sample_gex_profile):
        result = GEXVisualization.gex_bar_chart(sample_gex_profile, 5220.0)
        assert result["regime"] in ("positive", "negative")

    def test_colors_dict(self, sample_gex_profile):
        result = GEXVisualization.gex_bar_chart(sample_gex_profile, 5220.0)
        colors = result["colors"]
        assert colors["call_gex"] == "#22c55e"
        assert colors["put_gex"] == "#ef4444"
        assert colors["net_gex"] == "#3b82f6"

    def test_timestamp_is_iso_string(self, sample_gex_profile):
        result = GEXVisualization.gex_bar_chart(sample_gex_profile, 5220.0)
        assert isinstance(result["timestamp"], str)
        # Should parse without error
        datetime.fromisoformat(result["timestamp"])

    def test_total_net_gex_matches_profile(self, sample_gex_profile):
        result = GEXVisualization.gex_bar_chart(sample_gex_profile, 5220.0)
        assert result["total_net_gex"] == round(sample_gex_profile.total_net_gex, 4)


class TestGEXHeatmap:
    """Tests for GEXVisualization.gex_heatmap()."""

    def test_returns_correct_chart_type(self, sample_gex_profiles_history):
        result = GEXVisualization.gex_heatmap(sample_gex_profiles_history)
        assert result["chart_type"] == "gex_heatmap"

    def test_empty_input(self):
        result = GEXVisualization.gex_heatmap([])
        assert result["timestamps"] == []
        assert result["strikes"] == []
        assert result["values"] == []

    def test_2d_values_dimensions(self, sample_gex_profiles_history):
        result = GEXVisualization.gex_heatmap(sample_gex_profiles_history)
        num_strikes = len(result["strikes"])
        num_timestamps = len(result["timestamps"])
        values = result["values"]
        # rows = strikes, cols = timestamps
        assert len(values) == num_strikes
        for row in values:
            assert len(row) == num_timestamps

    def test_strikes_sorted(self, sample_gex_profiles_history):
        result = GEXVisualization.gex_heatmap(sample_gex_profiles_history)
        assert result["strikes"] == sorted(result["strikes"])

    def test_timestamps_match_input_count(self, sample_gex_profiles_history):
        result = GEXVisualization.gex_heatmap(sample_gex_profiles_history)
        assert len(result["timestamps"]) == len(sample_gex_profiles_history)

    def test_time_labels_present(self, sample_gex_profiles_history):
        result = GEXVisualization.gex_heatmap(sample_gex_profiles_history)
        assert "time_labels" in result
        assert len(result["time_labels"]) == len(result["timestamps"])

    def test_value_range_computed(self, sample_gex_profiles_history):
        result = GEXVisualization.gex_heatmap(sample_gex_profiles_history)
        assert "value_range" in result
        assert result["value_range"]["min"] <= result["value_range"]["max"]

    def test_color_scale_is_rdylgn(self, sample_gex_profiles_history):
        result = GEXVisualization.gex_heatmap(sample_gex_profiles_history)
        assert result["color_scale"] == "RdYlGn"


class TestGammaFlipTimeline:
    """Tests for GEXVisualization.gamma_flip_timeline()."""

    def test_tracks_gamma_flip_levels(self, sample_gex_profiles_history):
        result = GEXVisualization.gamma_flip_timeline(sample_gex_profiles_history)
        assert result["chart_type"] == "gamma_flip_timeline"
        assert len(result["gamma_flip"]) == len(sample_gex_profiles_history)
        # Gamma flip should be increasing per fixture construction
        for level in result["gamma_flip"]:
            assert isinstance(level, float)
            assert level > 0

    def test_with_spot_prices(self, sample_gex_profiles_history):
        spot_prices = [5218.0, 5220.0, 5222.0]
        result = GEXVisualization.gamma_flip_timeline(
            sample_gex_profiles_history, spot_prices
        )
        assert result["spot_price"] == [5218.0, 5220.0, 5222.0]

    def test_without_spot_prices(self, sample_gex_profiles_history):
        result = GEXVisualization.gamma_flip_timeline(sample_gex_profiles_history)
        # All entries should be None
        for sp in result["spot_price"]:
            assert sp is None

    def test_regime_series(self, sample_gex_profiles_history):
        result = GEXVisualization.gamma_flip_timeline(sample_gex_profiles_history)
        for regime in result["regime"]:
            assert regime in ("positive", "negative")

    def test_colors_include_gamma_flip_and_spot(self, sample_gex_profiles_history):
        result = GEXVisualization.gamma_flip_timeline(sample_gex_profiles_history)
        colors = result["colors"]
        assert "gamma_flip" in colors
        assert "spot_price" in colors
        assert "positive_regime" in colors
        assert "negative_regime" in colors

    def test_time_labels_present(self, sample_gex_profiles_history):
        result = GEXVisualization.gamma_flip_timeline(sample_gex_profiles_history)
        assert len(result["time_labels"]) == len(sample_gex_profiles_history)


class TestKeyLevelsDiagram:
    """Tests for GEXVisualization.key_levels_diagram()."""

    def test_includes_all_level_types(
        self, sample_gex_profile, sample_session_setup
    ):
        result = GEXVisualization.key_levels_diagram(
            sample_gex_profile, sample_session_setup, 5220.0
        )
        level_types = {lv["type"] for lv in result["levels"]}
        assert "gex" in level_types
        assert "expected_move" in level_types
        assert "prior_day" in level_types
        assert "overnight" in level_types

    def test_gex_levels_present(self, sample_gex_profile, sample_session_setup):
        result = GEXVisualization.key_levels_diagram(
            sample_gex_profile, sample_session_setup, 5220.0
        )
        gex_labels = {
            lv["label"] for lv in result["levels"] if lv["type"] == "gex"
        }
        assert "Gamma Flip" in gex_labels
        assert "Call Wall" in gex_labels
        assert "Put Wall" in gex_labels
        assert "Max Pain" in gex_labels
        assert "Vol Trigger" in gex_labels
        assert "+GEX" in gex_labels
        assert "-GEX" in gex_labels

    def test_expected_move_levels(
        self, sample_gex_profile, sample_session_setup
    ):
        result = GEXVisualization.key_levels_diagram(
            sample_gex_profile, sample_session_setup, 5220.0
        )
        em_labels = {
            lv["label"]
            for lv in result["levels"]
            if lv["type"] == "expected_move"
        }
        assert any("\u03c3" in label for label in em_labels)  # sigma symbol present

    def test_prior_day_levels(self, sample_gex_profile, sample_session_setup):
        result = GEXVisualization.key_levels_diagram(
            sample_gex_profile, sample_session_setup, 5220.0
        )
        prior_labels = {
            lv["label"]
            for lv in result["levels"]
            if lv["type"] == "prior_day"
        }
        assert "Prior High" in prior_labels
        assert "Prior Low" in prior_labels
        assert "Prior Close" in prior_labels
        assert "Prior VWAP" in prior_labels

    def test_overnight_levels(self, sample_gex_profile, sample_session_setup):
        result = GEXVisualization.key_levels_diagram(
            sample_gex_profile, sample_session_setup, 5220.0
        )
        overnight_labels = {
            lv["label"]
            for lv in result["levels"]
            if lv["type"] == "overnight"
        }
        assert "Overnight High" in overnight_labels
        assert "Overnight Low" in overnight_labels

    def test_technical_levels_from_moving_averages(
        self, sample_gex_profile, sample_session_setup
    ):
        result = GEXVisualization.key_levels_diagram(
            sample_gex_profile, sample_session_setup, 5220.0
        )
        tech_labels = {
            lv["label"]
            for lv in result["levels"]
            if lv["type"] == "technical"
        }
        assert "SMA_20" in tech_labels
        assert "EMA_9" in tech_labels

    def test_round_number_levels(
        self, sample_gex_profile, sample_session_setup
    ):
        result = GEXVisualization.key_levels_diagram(
            sample_gex_profile, sample_session_setup, 5220.0
        )
        round_labels = {
            lv["label"]
            for lv in result["levels"]
            if lv["type"] == "round_number"
        }
        assert "5200" in round_labels
        assert "5250" in round_labels

    def test_levels_sorted_by_price(
        self, sample_gex_profile, sample_session_setup
    ):
        result = GEXVisualization.key_levels_diagram(
            sample_gex_profile, sample_session_setup, 5220.0
        )
        prices = [lv["price"] for lv in result["levels"]]
        assert prices == sorted(prices)

    def test_level_structure_has_required_keys(
        self, sample_gex_profile, sample_session_setup
    ):
        result = GEXVisualization.key_levels_diagram(
            sample_gex_profile, sample_session_setup, 5220.0
        )
        for lv in result["levels"]:
            assert "price" in lv
            assert "label" in lv
            assert "type" in lv
            assert "color" in lv
            assert "style" in lv
            assert "importance" in lv

    def test_spot_price_in_output(
        self, sample_gex_profile, sample_session_setup
    ):
        result = GEXVisualization.key_levels_diagram(
            sample_gex_profile, sample_session_setup, 5220.0
        )
        assert result["spot"] == 5220.0

    def test_transition_zone_in_output(
        self, sample_gex_profile, sample_session_setup
    ):
        result = GEXVisualization.key_levels_diagram(
            sample_gex_profile, sample_session_setup, 5220.0
        )
        tz = result["transition_zone"]
        assert "upper" in tz
        assert "lower" in tz
        assert tz["lower"] <= tz["upper"]

    def test_gap_analysis_in_output(
        self, sample_gex_profile, sample_session_setup
    ):
        result = GEXVisualization.key_levels_diagram(
            sample_gex_profile, sample_session_setup, 5220.0
        )
        assert "gap_analysis" in result
        assert "gap_pct" in result["gap_analysis"]
        assert "classification" in result["gap_analysis"]


# =========================================================================
# 3. SCANNER VISUALIZATION
# =========================================================================


class TestDirectionScoreGauge:
    """Tests for ScannerVisualization.direction_score_gauge()."""

    def test_returns_correct_chart_type(self, sample_direction_score):
        result = ScannerVisualization.direction_score_gauge(sample_direction_score)
        assert result["chart_type"] == "direction_gauge"

    def test_range_is_minus100_to_plus100(self, sample_direction_score):
        result = ScannerVisualization.direction_score_gauge(sample_direction_score)
        assert result["range"]["min"] == -100
        assert result["range"]["max"] == 100

    def test_total_score_within_range(self, sample_direction_score):
        result = ScannerVisualization.direction_score_gauge(sample_direction_score)
        assert -100 <= result["total_score"] <= 100

    def test_bullish_color_is_green(self, sample_direction_score):
        """Bullish signal should produce green colour."""
        result = ScannerVisualization.direction_score_gauge(sample_direction_score)
        assert result["color"] == "#22c55e"

    def test_bearish_color_is_red(self, sample_bearish_direction_score):
        """Bearish signal should produce red colour."""
        result = ScannerVisualization.direction_score_gauge(
            sample_bearish_direction_score
        )
        assert result["color"] == "#ef4444"

    def test_factors_breakdown(self, sample_direction_score):
        result = ScannerVisualization.direction_score_gauge(sample_direction_score)
        factors = result["factors"]
        assert len(factors) == 5
        factor_names = {f["name"] for f in factors}
        assert "Market Internals" in factor_names
        assert "Options Flow" in factor_names
        assert "Price Action" in factor_names
        assert "GEX Structure" in factor_names
        assert "Cross-Asset" in factor_names

    def test_factor_has_score_weight_color(self, sample_direction_score):
        result = ScannerVisualization.direction_score_gauge(sample_direction_score)
        for factor in result["factors"]:
            assert "score" in factor
            assert "weight" in factor
            assert "color" in factor
            assert isinstance(factor["score"], float)
            assert isinstance(factor["weight"], float)

    def test_threshold_lines(self, sample_direction_score):
        result = ScannerVisualization.direction_score_gauge(sample_direction_score)
        assert result["threshold_lines"] == [-65, -40, 0, 40, 65]

    def test_zones_cover_full_range(self, sample_direction_score):
        result = ScannerVisualization.direction_score_gauge(sample_direction_score)
        zones = result["zones"]
        assert len(zones) == 6
        assert zones[0]["min"] == -100
        assert zones[-1]["max"] == 100

    def test_confidence_field(self, sample_direction_score):
        result = ScannerVisualization.direction_score_gauge(sample_direction_score)
        assert 0 <= result["confidence"] <= 100

    def test_conviction_flags(self, sample_direction_score):
        result = ScannerVisualization.direction_score_gauge(sample_direction_score)
        assert "is_high_conviction" in result
        assert "is_conflicted" in result
        assert isinstance(result["is_high_conviction"], bool)
        assert isinstance(result["is_conflicted"], bool)

    def test_signal_field_matches_direction(self, sample_direction_score):
        result = ScannerVisualization.direction_score_gauge(sample_direction_score)
        assert result["signal"] == "BULL"


class TestSignalTimeline:
    """Tests for ScannerVisualization.signal_timeline()."""

    def test_returns_correct_chart_type(self, sample_scan_signal):
        result = ScannerVisualization.signal_timeline([sample_scan_signal])
        assert result["chart_type"] == "signal_timeline"

    def test_events_include_entry_and_context(self, sample_scan_signal):
        result = ScannerVisualization.signal_timeline([sample_scan_signal])
        event = result["events"][0]
        assert "entry_price" in event
        assert "stop_loss" in event
        assert "profit_target" in event
        assert "risk_reward_ratio" in event
        assert "direction" in event
        assert "scan_type" in event

    def test_total_signals_count(self, sample_scan_signal):
        signals = [sample_scan_signal, sample_scan_signal]
        result = ScannerVisualization.signal_timeline(signals)
        assert result["total_signals"] == 2

    def test_scan_type_counts(self, sample_scan_signal):
        result = ScannerVisualization.signal_timeline([sample_scan_signal])
        assert "DIRECTIONAL" in result["scan_type_counts"]
        assert result["scan_type_counts"]["DIRECTIONAL"] == 1

    def test_direction_counts(self, sample_scan_signal):
        result = ScannerVisualization.signal_timeline([sample_scan_signal])
        assert "BULL" in result["direction_counts"]

    def test_strike_selection_in_event(self, sample_scan_signal):
        result = ScannerVisualization.signal_timeline([sample_scan_signal])
        event = result["events"][0]
        assert event["strike"] == 5230.0
        assert event["option_type"] == "CALL"
        assert "delta" in event
        assert "iv" in event

    def test_signal_without_strike_selection(self, sample_direction_score):
        """Signal with no strike_selection should omit strike fields."""
        sig = ScanSignal(
            scan_type=ScanType.PREMIUM_SELL,
            direction=TradeDirection.NEUTRAL,
            strike_selection=None,
            direction_score=sample_direction_score,
            entry_price=2.50,
            stop_loss=1.25,
            profit_target=5.00,
            position_type=PositionType.CREDIT_SPREAD,
            contracts=1,
            max_risk=250.0,
            expected_reward=250.0,
            risk_reward_ratio=1.0,
            time_zone=TimeZoneType.MIDDAY_LULL,
            session_type=SessionType.RANGE,
            timestamp=datetime(2025, 5, 15, 12, 0, 0),
        )
        result = ScannerVisualization.signal_timeline([sig])
        event = result["events"][0]
        assert "strike" not in event

    def test_empty_signals_list(self):
        result = ScannerVisualization.signal_timeline([])
        assert result["events"] == []
        assert result["total_signals"] == 0

    def test_colors_dict(self, sample_scan_signal):
        result = ScannerVisualization.signal_timeline([sample_scan_signal])
        assert "DIRECTIONAL" in result["colors"]
        assert "PREMIUM_SELL" in result["colors"]
        assert "GAMMA_SCALP" in result["colors"]

    def test_direction_color_in_event(self, sample_scan_signal):
        result = ScannerVisualization.signal_timeline([sample_scan_signal])
        event = result["events"][0]
        assert event["direction_color"] == "#22c55e"  # green for BULL


class TestFactorContributionChart:
    """Tests for ScannerVisualization.factor_contribution_chart()."""

    def test_returns_correct_chart_type(self, sample_direction_score):
        result = ScannerVisualization.factor_contribution_chart(
            [sample_direction_score]
        )
        assert result["chart_type"] == "factor_contribution"

    def test_series_count(self, sample_direction_score):
        result = ScannerVisualization.factor_contribution_chart(
            [sample_direction_score]
        )
        assert len(result["series"]) == 5

    def test_series_keys(self, sample_direction_score):
        result = ScannerVisualization.factor_contribution_chart(
            [sample_direction_score]
        )
        keys = {s["key"] for s in result["series"]}
        assert keys == {
            "market_internals",
            "options_flow",
            "price_action",
            "gex_structure",
            "cross_asset",
        }

    def test_total_series_present(self, sample_direction_score):
        result = ScannerVisualization.factor_contribution_chart(
            [sample_direction_score]
        )
        assert "total" in result
        assert len(result["total"]) == 1

    def test_data_points_count(self, sample_direction_score):
        scores = [sample_direction_score, sample_direction_score]
        result = ScannerVisualization.factor_contribution_chart(scores)
        assert result["data_points"] == 2

    def test_each_series_has_data_matching_timestamps(
        self, sample_direction_score
    ):
        scores = [sample_direction_score] * 3
        result = ScannerVisualization.factor_contribution_chart(scores)
        for series in result["series"]:
            assert len(series["data"]) == 3

    def test_series_has_color(self, sample_direction_score):
        result = ScannerVisualization.factor_contribution_chart(
            [sample_direction_score]
        )
        for series in result["series"]:
            assert "color" in series
            assert series["color"].startswith("#")

    def test_stacked_data_relation_to_total(self, sample_direction_score):
        """Individual factor scores should exist alongside total. The total
        is the weighted composite, not necessarily the raw sum."""
        result = ScannerVisualization.factor_contribution_chart(
            [sample_direction_score]
        )
        # Verify total equals the total_score from the input
        assert result["total"][0] == round(sample_direction_score.total_score, 2)

    def test_empty_input(self):
        result = ScannerVisualization.factor_contribution_chart([])
        assert result["timestamps"] == []
        assert result["data_points"] == 0


class TestStrikeSelectionOverlay:
    """Tests for ScannerVisualization.strike_selection_overlay()."""

    def test_returns_correct_chart_type(
        self, sample_options_chain, sample_strike_selection
    ):
        result = ScannerVisualization.strike_selection_overlay(
            sample_options_chain,
            sample_strike_selection,
            5220.0,
            5238.5,
            5201.5,
        )
        assert result["chart_type"] == "strike_selection"

    def test_chain_context_populated(
        self, sample_options_chain, sample_strike_selection
    ):
        result = ScannerVisualization.strike_selection_overlay(
            sample_options_chain,
            sample_strike_selection,
            5220.0,
            5238.5,
            5201.5,
        )
        assert len(result["chain"]) == len(sample_options_chain.quotes)
        for entry in result["chain"]:
            assert "strike" in entry
            assert "option_type" in entry
            assert "bid" in entry
            assert "ask" in entry
            assert "volume" in entry
            assert "iv" in entry
            assert "delta" in entry

    def test_selected_strike_highlighted(
        self, sample_options_chain, sample_strike_selection
    ):
        result = ScannerVisualization.strike_selection_overlay(
            sample_options_chain,
            sample_strike_selection,
            5220.0,
            5238.5,
            5201.5,
        )
        selected = result["selected"]
        assert selected["strike"] == 5230.0
        assert selected["option_type"] == "CALL"
        assert "delta" in selected
        assert "iv" in selected
        assert "color" in selected

    def test_overlays_include_spot_and_em(
        self, sample_options_chain, sample_strike_selection
    ):
        result = ScannerVisualization.strike_selection_overlay(
            sample_options_chain,
            sample_strike_selection,
            5220.0,
            5238.5,
            5201.5,
        )
        overlay_labels = {o["label"] for o in result["overlays"]}
        assert "Spot" in overlay_labels
        assert "EM Upper" in overlay_labels
        assert "EM Lower" in overlay_labels

    def test_with_key_levels(
        self, sample_options_chain, sample_strike_selection
    ):
        key_levels = {"Gamma Flip": 5215.0, "Call Wall": 5230.0}
        result = ScannerVisualization.strike_selection_overlay(
            sample_options_chain,
            sample_strike_selection,
            5220.0,
            5238.5,
            5201.5,
            key_levels=key_levels,
        )
        overlay_labels = {o["label"] for o in result["overlays"]}
        assert "Gamma Flip" in overlay_labels
        assert "Call Wall" in overlay_labels

    def test_total_strikes_count(
        self, sample_options_chain, sample_strike_selection
    ):
        result = ScannerVisualization.strike_selection_overlay(
            sample_options_chain,
            sample_strike_selection,
            5220.0,
            5238.5,
            5201.5,
        )
        assert result["total_strikes"] == len(sample_options_chain.strikes)

    def test_spot_and_em_in_top_level(
        self, sample_options_chain, sample_strike_selection
    ):
        result = ScannerVisualization.strike_selection_overlay(
            sample_options_chain,
            sample_strike_selection,
            5220.0,
            5238.5,
            5201.5,
        )
        assert result["spot"] == 5220.0
        assert result["em_upper"] == 5238.5
        assert result["em_lower"] == 5201.5


# =========================================================================
# 4. PERFORMANCE VISUALIZATION
# =========================================================================


class TestIntradayPnlCurve:
    """Tests for PerformanceVisualization.intraday_pnl_curve()."""

    def test_returns_correct_chart_type(self, sample_trades):
        result = PerformanceVisualization.intraday_pnl_curve(sample_trades)
        assert result["chart_type"] == "intraday_pnl"

    def test_cumulative_pnl_structure(self, sample_trades):
        result = PerformanceVisualization.intraday_pnl_curve(sample_trades)
        assert "cumulative_pnl" in result
        assert "trade_pnl" in result
        assert "timestamps" in result
        assert "time_labels" in result
        assert len(result["cumulative_pnl"]) == len(result["timestamps"])

    def test_cumulative_pnl_is_running_sum(self, sample_trades):
        result = PerformanceVisualization.intraday_pnl_curve(sample_trades)
        cumulative = result["cumulative_pnl"]
        trade_pnls = result["trade_pnl"]
        # Verify running sum (cumulative[i] = sum of trade_pnls[:i+1])
        running = 0.0
        for i, tp in enumerate(trade_pnls):
            running += tp
            assert abs(cumulative[i] - round(running, 2)) < 0.01

    def test_drawdown_series(self, sample_trades):
        result = PerformanceVisualization.intraday_pnl_curve(sample_trades)
        drawdown = result["drawdown"]
        assert len(drawdown) == len(result["cumulative_pnl"])
        # Drawdown should be <= 0
        for dd in drawdown:
            assert dd <= 0.0

    def test_max_drawdown(self, sample_trades):
        result = PerformanceVisualization.intraday_pnl_curve(sample_trades)
        assert result["max_drawdown"] <= 0.0
        assert result["max_drawdown"] == min(result["drawdown"])

    def test_final_pnl(self, sample_trades):
        result = PerformanceVisualization.intraday_pnl_curve(sample_trades)
        assert "final_pnl" in result
        assert "final_pnl_formatted" in result
        assert "$" in result["final_pnl_formatted"]

    def test_total_trades_count(self, sample_trades):
        result = PerformanceVisualization.intraday_pnl_curve(sample_trades)
        assert result["total_trades"] == len(sample_trades)

    def test_colors_dict(self, sample_trades):
        result = PerformanceVisualization.intraday_pnl_curve(sample_trades)
        assert "pnl_line" in result["colors"]
        assert "drawdown_fill" in result["colors"]

    def test_empty_trades(self):
        result = PerformanceVisualization.intraday_pnl_curve([])
        assert result["cumulative_pnl"] == []
        assert result["final_pnl"] == 0.0
        assert result["total_trades"] == 0

    def test_with_open_positions(self, sample_trades):
        positions = [
            {
                "timestamp": datetime(2025, 5, 15, 14, 0, 0),
                "unrealised_pnl": 50.0,
            }
        ]
        result = PerformanceVisualization.intraday_pnl_curve(
            sample_trades, positions=positions
        )
        # Should have one extra data point from the position
        assert len(result["cumulative_pnl"]) == len(sample_trades) + 1


class TestPnlDistribution:
    """Tests for PerformanceVisualization.pnl_distribution()."""

    def test_returns_correct_chart_type(self, sample_trades):
        result = PerformanceVisualization.pnl_distribution(sample_trades)
        assert result["chart_type"] == "pnl_distribution"

    def test_bins_are_list(self, sample_trades):
        result = PerformanceVisualization.pnl_distribution(sample_trades)
        assert isinstance(result["bins"], list)
        assert len(result["bins"]) > 0

    def test_bin_structure(self, sample_trades):
        result = PerformanceVisualization.pnl_distribution(sample_trades)
        for b in result["bins"]:
            assert "x_start" in b
            assert "x_end" in b
            assert "count" in b
            assert b["x_start"] <= b["x_end"]
            assert b["count"] >= 0

    def test_total_bin_counts_equal_trade_count(self, sample_trades):
        result = PerformanceVisualization.pnl_distribution(sample_trades)
        total_count = sum(b["count"] for b in result["bins"])
        pnl_count = sum(1 for t in sample_trades if t.pnl_dollars is not None)
        assert total_count == pnl_count

    def test_statistics_present(self, sample_trades):
        result = PerformanceVisualization.pnl_distribution(sample_trades)
        stats = result["statistics"]
        assert "mean" in stats
        assert "median" in stats
        assert "stdev" in stats
        assert "min" in stats
        assert "max" in stats
        assert "count" in stats
        assert "skew" in stats

    def test_percentiles(self, sample_trades):
        result = PerformanceVisualization.pnl_distribution(sample_trades)
        pctiles = result["statistics"]["percentiles"]
        assert "p5" in pctiles
        assert "p25" in pctiles
        assert "p75" in pctiles
        assert "p95" in pctiles
        assert pctiles["p5"] <= pctiles["p25"]
        assert pctiles["p25"] <= pctiles["p75"]
        assert pctiles["p75"] <= pctiles["p95"]

    def test_markers_present(self, sample_trades):
        result = PerformanceVisualization.pnl_distribution(sample_trades)
        markers = result["markers"]
        marker_labels = {m["label"] for m in markers}
        assert "Mean" in marker_labels
        assert "Median" in marker_labels

    def test_empty_trades(self):
        result = PerformanceVisualization.pnl_distribution([])
        assert result["bins"] == []
        assert result["statistics"] == {}

    def test_formatted_values(self, sample_trades):
        result = PerformanceVisualization.pnl_distribution(sample_trades)
        stats = result["statistics"]
        assert "$" in stats["mean_formatted"]
        assert "$" in stats["median_formatted"]


class TestWinRateByCategory:
    """Tests for PerformanceVisualization.win_rate_by_category()."""

    def test_returns_correct_chart_type(self, sample_trades):
        result = PerformanceVisualization.win_rate_by_category(sample_trades)
        assert result["chart_type"] == "win_rate_breakdown"

    def test_by_scan_type_present(self, sample_trades):
        result = PerformanceVisualization.win_rate_by_category(sample_trades)
        assert len(result["by_scan_type"]) > 0
        categories = {item["category"] for item in result["by_scan_type"]}
        assert "DIRECTIONAL" in categories

    def test_by_time_zone_present(self, sample_trades):
        result = PerformanceVisualization.win_rate_by_category(sample_trades)
        assert len(result["by_time_zone"]) > 0

    def test_by_session_type_present(self, sample_trades):
        result = PerformanceVisualization.win_rate_by_category(sample_trades)
        assert len(result["by_session_type"]) > 0

    def test_overall_stats(self, sample_trades):
        result = PerformanceVisualization.win_rate_by_category(sample_trades)
        overall = result["overall"]
        assert "win_rate" in overall
        assert "total" in overall
        assert "wins" in overall
        assert "losses" in overall
        assert overall["wins"] + overall["losses"] == overall["total"]
        assert 0 <= overall["win_rate"] <= 100

    def test_breakdown_item_structure(self, sample_trades):
        result = PerformanceVisualization.win_rate_by_category(sample_trades)
        for item in result["by_scan_type"]:
            assert "category" in item
            assert "label" in item
            assert "win_rate" in item
            assert "total" in item
            assert "wins" in item
            assert "losses" in item
            assert "avg_pnl" in item
            assert "color" in item
            assert item["wins"] + item["losses"] == item["total"]

    def test_win_rate_within_valid_range(self, sample_trades):
        result = PerformanceVisualization.win_rate_by_category(sample_trades)
        for breakdown_type in ["by_scan_type", "by_time_zone", "by_session_type"]:
            for item in result[breakdown_type]:
                assert 0 <= item["win_rate"] <= 100

    def test_empty_trades(self):
        result = PerformanceVisualization.win_rate_by_category([])
        assert result["by_scan_type"] == []
        assert result["overall"]["total"] == 0


class TestEquityCurve:
    """Tests for PerformanceVisualization.equity_curve()."""

    def test_returns_correct_chart_type(self):
        daily_pnl = {"2025-05-12": 150.0, "2025-05-13": -80.0, "2025-05-14": 200.0}
        result = PerformanceVisualization.equity_curve(daily_pnl)
        assert result["chart_type"] == "equity_curve"

    def test_cumulative_equity(self):
        daily_pnl = {"2025-05-12": 100.0, "2025-05-13": 50.0, "2025-05-14": -30.0}
        result = PerformanceVisualization.equity_curve(daily_pnl)
        assert result["cumulative_equity"] == [100.0, 150.0, 120.0]

    def test_rolling_sharpe_has_none_for_early_entries(self):
        """Rolling Sharpe uses window=20, so first 19 entries should be None."""
        daily_pnl = {f"2025-05-{i+1:02d}": float(i * 10 - 50) for i in range(25)}
        result = PerformanceVisualization.equity_curve(daily_pnl)
        sharpe = result["rolling_sharpe"]
        # First 19 entries (indices 0-18) should be None
        for i in range(19):
            assert sharpe[i] is None
        # Entry at index 19 should be a number (or None if stdev is 0)
        assert sharpe[19] is None or isinstance(sharpe[19], float)

    def test_rolling_sharpe_computed_correctly(self):
        """When enough data points exist, rolling Sharpe should be a float."""
        import random
        random.seed(42)
        daily_pnl = {
            f"2025-01-{i+1:02d}" if i < 28 else f"2025-02-{i-27:02d}": random.gauss(10, 50)
            for i in range(30)
        }
        result = PerformanceVisualization.equity_curve(daily_pnl)
        sharpe = result["rolling_sharpe"]
        # After window-1 entries, some should be non-None
        non_none = [s for s in sharpe if s is not None]
        assert len(non_none) > 0

    def test_drawdown_series(self):
        daily_pnl = {"2025-05-12": 100.0, "2025-05-13": -150.0, "2025-05-14": 200.0}
        result = PerformanceVisualization.equity_curve(daily_pnl)
        drawdown = result["drawdown"]
        assert len(drawdown) == 3
        # After day 2 cumulative is -50, peak was 100, so drawdown = -150
        assert drawdown[1] == -150.0

    def test_total_return_formatted(self):
        daily_pnl = {"2025-05-12": 500.0}
        result = PerformanceVisualization.equity_curve(daily_pnl)
        assert "$" in result["total_return"]

    def test_max_drawdown_formatted(self):
        daily_pnl = {"2025-05-12": 100.0, "2025-05-13": -200.0}
        result = PerformanceVisualization.equity_curve(daily_pnl)
        assert "$" in result["max_drawdown"]

    def test_trading_days_count(self):
        daily_pnl = {
            "2025-05-12": 100.0,
            "2025-05-13": 200.0,
            "2025-05-14": -50.0,
        }
        result = PerformanceVisualization.equity_curve(daily_pnl)
        assert result["trading_days"] == 3

    def test_colors_dict(self):
        daily_pnl = {"2025-05-12": 100.0}
        result = PerformanceVisualization.equity_curve(daily_pnl)
        assert "equity_line" in result["colors"]
        assert "sharpe_line" in result["colors"]
        assert "drawdown_fill" in result["colors"]

    def test_empty_input(self):
        result = PerformanceVisualization.equity_curve({})
        assert result["dates"] == []
        assert result["cumulative_equity"] == []
        assert result["rolling_sharpe"] == []

    def test_daily_pnl_formatted(self):
        daily_pnl = {"2025-05-12": 100.0, "2025-05-13": -50.0}
        result = PerformanceVisualization.equity_curve(daily_pnl)
        assert len(result["daily_pnl_formatted"]) == 2
        assert "$" in result["daily_pnl_formatted"][0]


class TestDrawdownChart:
    """Tests for PerformanceVisualization.drawdown_chart()."""

    def test_returns_correct_chart_type(self):
        result = PerformanceVisualization.drawdown_chart([100, 110, 90, 105, 80])
        assert result["chart_type"] == "drawdown"

    def test_identifies_max_drawdown(self):
        equity = [100.0, 120.0, 90.0, 110.0, 70.0]
        result = PerformanceVisualization.drawdown_chart(equity)
        # Max drawdown: peak=120, trough=70, dd=-50 (absolute)
        assert result["max_drawdown_abs"] == -50.0

    def test_drawdown_pct_series(self):
        equity = [100.0, 110.0, 90.0]
        result = PerformanceVisualization.drawdown_chart(equity)
        dd_pct = result["drawdown_pct"]
        assert len(dd_pct) == 3
        assert dd_pct[0] == 0.0  # First point is at peak
        # Third point: peak=110, value=90, dd_pct = (90-110)/110*100 = -18.1818
        assert dd_pct[2] < 0

    def test_drawdown_abs_series(self):
        equity = [100.0, 110.0, 90.0]
        result = PerformanceVisualization.drawdown_chart(equity)
        dd_abs = result["drawdown_abs"]
        assert dd_abs[0] == 0.0
        assert dd_abs[2] == -20.0  # 90 - 110 = -20

    def test_worst_periods_identified(self):
        equity = [100.0, 120.0, 80.0, 130.0, 70.0, 140.0]
        result = PerformanceVisualization.drawdown_chart(equity)
        periods = result["worst_periods"]
        assert len(periods) > 0
        # Each period should have required keys
        for period in periods:
            assert "start_idx" in period
            assert "trough_idx" in period
            assert "end_idx" in period
            assert "drawdown_abs" in period
            assert "drawdown_pct" in period

    def test_worst_periods_sorted_by_severity(self):
        equity = [100.0, 120.0, 80.0, 130.0, 50.0, 140.0]
        result = PerformanceVisualization.drawdown_chart(equity)
        periods = result["worst_periods"]
        if len(periods) >= 2:
            # Sorted by drawdown_abs ascending (most negative first)
            for i in range(len(periods) - 1):
                assert periods[i]["drawdown_abs"] <= periods[i + 1]["drawdown_abs"]

    def test_max_drawdown_formatted(self):
        equity = [100.0, 80.0]
        result = PerformanceVisualization.drawdown_chart(equity)
        assert "%" in result["max_drawdown_pct_formatted"]
        assert "$" in result["max_drawdown_abs_formatted"]

    def test_empty_input(self):
        result = PerformanceVisualization.drawdown_chart([])
        assert result["drawdown_pct"] == []
        assert result["max_drawdown_pct"] == 0.0
        assert result["max_drawdown_abs"] == 0.0

    def test_total_points(self):
        equity = [100.0, 110.0, 90.0, 120.0]
        result = PerformanceVisualization.drawdown_chart(equity)
        assert result["total_points"] == 4

    def test_colors_dict(self):
        result = PerformanceVisualization.drawdown_chart([100.0, 90.0])
        assert "drawdown_fill" in result["colors"]
        assert "recovery_line" in result["colors"]

    def test_no_drawdown_when_always_increasing(self):
        equity = [100.0, 110.0, 120.0, 130.0]
        result = PerformanceVisualization.drawdown_chart(equity)
        assert result["max_drawdown_abs"] == 0.0
        assert result["max_drawdown_pct"] == 0.0
        assert all(dd == 0.0 for dd in result["drawdown_abs"])


# =========================================================================
# 5. CALIBRATION VISUALIZATION
# =========================================================================


class TestWeightEvolution:
    """Tests for CalibrationVisualization.weight_evolution()."""

    def test_returns_correct_chart_type(self, sample_factor_weights_history):
        result = CalibrationVisualization.weight_evolution(
            sample_factor_weights_history
        )
        assert result["chart_type"] == "weight_evolution"

    def test_tracks_all_factor_weights(self, sample_factor_weights_history):
        result = CalibrationVisualization.weight_evolution(
            sample_factor_weights_history
        )
        series_keys = {s["key"] for s in result["series"]}
        assert series_keys == {
            "market_internals",
            "options_flow",
            "price_action",
            "gex_structure",
            "cross_asset",
        }

    def test_data_length_matches_input(self, sample_factor_weights_history):
        result = CalibrationVisualization.weight_evolution(
            sample_factor_weights_history
        )
        for series in result["series"]:
            assert len(series["data"]) == len(sample_factor_weights_history)

    def test_labels_are_cycle_numbered(self, sample_factor_weights_history):
        result = CalibrationVisualization.weight_evolution(
            sample_factor_weights_history
        )
        assert result["labels"] == ["Cycle 1", "Cycle 2", "Cycle 3"]

    def test_deltas_computed(self, sample_factor_weights_history):
        result = CalibrationVisualization.weight_evolution(
            sample_factor_weights_history
        )
        deltas = result["deltas"]
        assert "market_internals" in deltas
        # First market_internals=0.30, last=0.27, delta=-0.03
        assert abs(deltas["market_internals"] - (-0.03)) < 1e-4

    def test_current_weights(self, sample_factor_weights_history):
        result = CalibrationVisualization.weight_evolution(
            sample_factor_weights_history
        )
        cw = result["current_weights"]
        assert abs(cw["market_internals"] - 0.27) < 1e-4

    def test_data_points_count(self, sample_factor_weights_history):
        result = CalibrationVisualization.weight_evolution(
            sample_factor_weights_history
        )
        assert result["data_points"] == 3

    def test_empty_input(self):
        result = CalibrationVisualization.weight_evolution([])
        assert result["labels"] == []
        assert result["series"] == []
        assert result["data_points"] == 0

    def test_single_weight_snapshot(self):
        """Single snapshot should have no deltas."""
        single = [
            FactorWeights(
                market_internals=0.30,
                options_flow=0.25,
                price_action=0.20,
                gex_structure=0.15,
                cross_asset=0.10,
            )
        ]
        result = CalibrationVisualization.weight_evolution(single)
        assert result["deltas"] == {}
        assert result["data_points"] == 1


class TestThresholdEvolution:
    """Tests for CalibrationVisualization.threshold_evolution()."""

    def test_returns_correct_chart_type(self):
        history = [
            {
                "timestamp": datetime(2025, 5, 13),
                "entry_threshold": 40.0,
                "stop_loss_pct": 5.0,
            },
            {
                "timestamp": datetime(2025, 5, 14),
                "entry_threshold": 42.0,
                "stop_loss_pct": 4.5,
            },
        ]
        result = CalibrationVisualization.threshold_evolution(history)
        assert result["chart_type"] == "threshold_evolution"

    def test_tracks_entry_threshold_changes(self):
        history = [
            {"timestamp": datetime(2025, 5, 13), "entry_threshold": 40.0},
            {"timestamp": datetime(2025, 5, 14), "entry_threshold": 42.0},
            {"timestamp": datetime(2025, 5, 15), "entry_threshold": 38.0},
        ]
        result = CalibrationVisualization.threshold_evolution(history)
        assert result["entry_threshold"] == [40.0, 42.0, 38.0]

    def test_tracks_stop_loss_pct(self):
        history = [
            {
                "timestamp": datetime(2025, 5, 13),
                "entry_threshold": 40.0,
                "stop_loss_pct": 5.0,
            },
        ]
        result = CalibrationVisualization.threshold_evolution(history)
        assert result["stop_loss_pct"] == [5.0]

    def test_profit_targets_by_zone(self):
        history = [
            {
                "timestamp": datetime(2025, 5, 13),
                "entry_threshold": 40.0,
                "profit_targets_by_zone": {
                    "MORNING_SESSION": 3.0,
                    "POWER_HOUR": 2.0,
                },
            },
        ]
        result = CalibrationVisualization.threshold_evolution(history)
        assert "MORNING_SESSION" in result["profit_targets"]
        assert "POWER_HOUR" in result["profit_targets"]

    def test_data_points_count(self):
        history = [
            {"entry_threshold": 40.0},
            {"entry_threshold": 42.0},
        ]
        result = CalibrationVisualization.threshold_evolution(history)
        assert result["data_points"] == 2

    def test_current_values(self):
        history = [
            {
                "timestamp": datetime(2025, 5, 13),
                "entry_threshold": 40.0,
                "stop_loss_pct": 5.0,
            },
            {
                "timestamp": datetime(2025, 5, 14),
                "entry_threshold": 42.0,
                "stop_loss_pct": 4.5,
            },
        ]
        result = CalibrationVisualization.threshold_evolution(history)
        assert result["current"]["entry_threshold"] == 42.0
        assert result["current"]["stop_loss_pct"] == 4.5

    def test_labels_from_timestamps(self):
        history = [
            {"timestamp": datetime(2025, 5, 13), "entry_threshold": 40.0},
        ]
        result = CalibrationVisualization.threshold_evolution(history)
        # Labels should be ISO-8601 strings when timestamps are datetime
        assert len(result["labels"]) == 1
        datetime.fromisoformat(result["labels"][0])

    def test_labels_fallback_to_cycle_number(self):
        history = [{"entry_threshold": 40.0}]
        result = CalibrationVisualization.threshold_evolution(history)
        assert result["labels"] == ["Cycle 1"]

    def test_colors_dict(self):
        history = [{"entry_threshold": 40.0}]
        result = CalibrationVisualization.threshold_evolution(history)
        assert "entry_threshold" in result["colors"]
        assert "stop_loss_pct" in result["colors"]

    def test_empty_input(self):
        result = CalibrationVisualization.threshold_evolution([])
        assert result["labels"] == []
        assert result["data_points"] == 0


class TestRegimeTimeline:
    """Tests for CalibrationVisualization.regime_timeline()."""

    def test_returns_correct_chart_type(self):
        history = [
            {"timestamp": datetime(2025, 5, 15, 9, 30), "regime": "NORMAL"},
        ]
        result = CalibrationVisualization.regime_timeline(history)
        assert result["chart_type"] == "regime_timeline"

    def test_shows_classification_changes(self):
        history = [
            {"timestamp": datetime(2025, 5, 15, 9, 30), "regime": "NORMAL"},
            {"timestamp": datetime(2025, 5, 15, 10, 0), "regime": "ELEVATED"},
            {"timestamp": datetime(2025, 5, 15, 10, 30), "regime": "NORMAL"},
        ]
        result = CalibrationVisualization.regime_timeline(history)
        assert result["regimes"] == ["NORMAL", "ELEVATED", "NORMAL"]

    def test_regime_counts(self):
        history = [
            {"timestamp": datetime(2025, 5, 15, 9, 30), "regime": "NORMAL"},
            {"timestamp": datetime(2025, 5, 15, 10, 0), "regime": "NORMAL"},
            {"timestamp": datetime(2025, 5, 15, 10, 30), "regime": "ELEVATED"},
        ]
        result = CalibrationVisualization.regime_timeline(history)
        assert result["regime_counts"]["NORMAL"] == 2
        assert result["regime_counts"]["ELEVATED"] == 1

    def test_vix_and_gex_series(self):
        history = [
            {
                "timestamp": datetime(2025, 5, 15, 9, 30),
                "regime": "NORMAL",
                "vix": 16.5,
                "total_net_gex": 4.2,
            },
        ]
        result = CalibrationVisualization.regime_timeline(history)
        assert result["vix"] == [16.5]
        assert result["gex"] == [4.2]

    def test_regime_colors_mapping(self):
        history = [
            {"timestamp": datetime(2025, 5, 15, 9, 30), "regime": "LOW"},
            {"timestamp": datetime(2025, 5, 15, 10, 0), "regime": "EXTREME"},
        ]
        result = CalibrationVisualization.regime_timeline(history)
        assert result["regime_colors"][0] == "#22c55e"  # LOW = green
        assert result["regime_colors"][1] == "#ef4444"  # EXTREME = red

    def test_colors_dict_includes_all_regimes(self):
        result = CalibrationVisualization.regime_timeline([])
        colors = result["colors"]
        assert "LOW" in colors
        assert "NORMAL" in colors
        assert "ELEVATED" in colors
        assert "EXTREME" in colors

    def test_empty_input(self):
        result = CalibrationVisualization.regime_timeline([])
        assert result["timestamps"] == []
        assert result["regimes"] == []


class TestGEXAccuracyChart:
    """Tests for CalibrationVisualization.gex_accuracy_chart()."""

    def test_returns_correct_chart_type(self):
        history = [
            {"timestamp": datetime(2025, 5, 15, 10, 0), "accuracy": 0.72, "signal_count": 10},
        ]
        result = CalibrationVisualization.gex_accuracy_chart(history)
        assert result["chart_type"] == "gex_accuracy"

    def test_rolling_window_data(self):
        history = [
            {"timestamp": datetime(2025, 5, 15, 10, 0), "accuracy": 0.70, "signal_count": 10},
            {"timestamp": datetime(2025, 5, 15, 11, 0), "accuracy": 0.75, "signal_count": 12},
            {"timestamp": datetime(2025, 5, 15, 12, 0), "accuracy": 0.68, "signal_count": 8},
        ]
        result = CalibrationVisualization.gex_accuracy_chart(history)
        assert len(result["accuracy"]) == 3
        assert len(result["signal_counts"]) == 3
        assert result["accuracy"] == [0.70, 0.75, 0.68]

    def test_avg_accuracy(self):
        history = [
            {"timestamp": datetime(2025, 5, 15, 10, 0), "accuracy": 0.60},
            {"timestamp": datetime(2025, 5, 15, 11, 0), "accuracy": 0.80},
        ]
        result = CalibrationVisualization.gex_accuracy_chart(history)
        assert abs(result["avg_accuracy"] - 0.70) < 1e-4

    def test_avg_accuracy_formatted(self):
        history = [
            {"timestamp": datetime(2025, 5, 15, 10, 0), "accuracy": 0.72},
        ]
        result = CalibrationVisualization.gex_accuracy_chart(history)
        assert "%" in result["avg_accuracy_formatted"]

    def test_by_signal_type(self):
        history = [
            {"timestamp": datetime(2025, 5, 15, 10, 0), "accuracy": 0.80, "signal_type": "GAMMA_FLIP_CROSSOVER"},
            {"timestamp": datetime(2025, 5, 15, 11, 0), "accuracy": 0.60, "signal_type": "GAMMA_WALL_APPROACH"},
            {"timestamp": datetime(2025, 5, 15, 12, 0), "accuracy": 0.90, "signal_type": "GAMMA_FLIP_CROSSOVER"},
        ]
        result = CalibrationVisualization.gex_accuracy_chart(history)
        assert "GAMMA_FLIP_CROSSOVER" in result["by_signal_type"]
        assert "GAMMA_WALL_APPROACH" in result["by_signal_type"]
        # Average for GAMMA_FLIP_CROSSOVER = (0.80 + 0.90) / 2 = 0.85
        assert abs(result["by_signal_type"]["GAMMA_FLIP_CROSSOVER"] - 0.85) < 1e-4

    def test_threshold_line(self):
        history = [
            {"timestamp": datetime(2025, 5, 15, 10, 0), "accuracy": 0.72},
        ]
        result = CalibrationVisualization.gex_accuracy_chart(history)
        assert result["threshold_line"] == 0.6

    def test_data_points_count(self):
        history = [
            {"timestamp": datetime(2025, 5, 15, 10, 0), "accuracy": 0.70},
            {"timestamp": datetime(2025, 5, 15, 11, 0), "accuracy": 0.75},
        ]
        result = CalibrationVisualization.gex_accuracy_chart(history)
        assert result["data_points"] == 2

    def test_empty_input(self):
        result = CalibrationVisualization.gex_accuracy_chart([])
        assert result["accuracy"] == []
        assert result["avg_accuracy"] == 0.0
        assert result["data_points"] == 0

    def test_colors_dict(self):
        history = [{"timestamp": datetime(2025, 5, 15, 10, 0), "accuracy": 0.70}]
        result = CalibrationVisualization.gex_accuracy_chart(history)
        assert "accuracy_line" in result["colors"]
        assert "threshold" in result["colors"]


# =========================================================================
# 6. JSON SERIALISABILITY
# =========================================================================


class TestJSONSerialisability:
    """Verify all visualization outputs pass json.dumps without error.

    This guards against accidental inclusion of non-serialisable types
    (datetime objects, numpy arrays, custom classes, etc.) in the output.
    """

    def test_gex_bar_chart_serialisable(self, sample_gex_profile):
        result = GEXVisualization.gex_bar_chart(sample_gex_profile, 5220.0)
        serialised = json.dumps(result)
        assert isinstance(serialised, str)

    def test_gex_heatmap_serialisable(self, sample_gex_profiles_history):
        result = GEXVisualization.gex_heatmap(sample_gex_profiles_history)
        serialised = json.dumps(result)
        assert isinstance(serialised, str)

    def test_gamma_flip_timeline_serialisable(self, sample_gex_profiles_history):
        result = GEXVisualization.gamma_flip_timeline(
            sample_gex_profiles_history, [5218.0, 5220.0, 5222.0]
        )
        serialised = json.dumps(result)
        assert isinstance(serialised, str)

    def test_key_levels_diagram_serialisable(
        self, sample_gex_profile, sample_session_setup
    ):
        result = GEXVisualization.key_levels_diagram(
            sample_gex_profile, sample_session_setup, 5220.0
        )
        serialised = json.dumps(result)
        assert isinstance(serialised, str)

    def test_direction_score_gauge_serialisable(self, sample_direction_score):
        result = ScannerVisualization.direction_score_gauge(sample_direction_score)
        serialised = json.dumps(result)
        assert isinstance(serialised, str)

    def test_signal_timeline_serialisable(self, sample_scan_signal):
        result = ScannerVisualization.signal_timeline([sample_scan_signal])
        serialised = json.dumps(result)
        assert isinstance(serialised, str)

    def test_factor_contribution_serialisable(self, sample_direction_score):
        result = ScannerVisualization.factor_contribution_chart(
            [sample_direction_score]
        )
        serialised = json.dumps(result)
        assert isinstance(serialised, str)

    def test_strike_selection_overlay_serialisable(
        self, sample_options_chain, sample_strike_selection
    ):
        result = ScannerVisualization.strike_selection_overlay(
            sample_options_chain,
            sample_strike_selection,
            5220.0,
            5238.5,
            5201.5,
        )
        serialised = json.dumps(result)
        assert isinstance(serialised, str)

    def test_intraday_pnl_curve_serialisable(self, sample_trades):
        result = PerformanceVisualization.intraday_pnl_curve(sample_trades)
        serialised = json.dumps(result)
        assert isinstance(serialised, str)

    def test_pnl_distribution_serialisable(self, sample_trades):
        result = PerformanceVisualization.pnl_distribution(sample_trades)
        serialised = json.dumps(result)
        assert isinstance(serialised, str)

    def test_win_rate_by_category_serialisable(self, sample_trades):
        result = PerformanceVisualization.win_rate_by_category(sample_trades)
        serialised = json.dumps(result)
        assert isinstance(serialised, str)

    def test_equity_curve_serialisable(self):
        daily_pnl = {"2025-05-12": 100.0, "2025-05-13": -50.0}
        result = PerformanceVisualization.equity_curve(daily_pnl)
        serialised = json.dumps(result)
        assert isinstance(serialised, str)

    def test_drawdown_chart_serialisable(self):
        result = PerformanceVisualization.drawdown_chart([100.0, 90.0, 110.0])
        serialised = json.dumps(result)
        assert isinstance(serialised, str)

    def test_weight_evolution_serialisable(self, sample_factor_weights_history):
        result = CalibrationVisualization.weight_evolution(
            sample_factor_weights_history
        )
        serialised = json.dumps(result)
        assert isinstance(serialised, str)

    def test_threshold_evolution_serialisable(self):
        history = [
            {
                "timestamp": datetime(2025, 5, 13),
                "entry_threshold": 40.0,
                "stop_loss_pct": 5.0,
            },
        ]
        result = CalibrationVisualization.threshold_evolution(history)
        serialised = json.dumps(result)
        assert isinstance(serialised, str)

    def test_regime_timeline_serialisable(self):
        history = [
            {
                "timestamp": datetime(2025, 5, 15, 9, 30),
                "regime": "NORMAL",
                "vix": 16.5,
                "total_net_gex": 4.2,
            },
        ]
        result = CalibrationVisualization.regime_timeline(history)
        serialised = json.dumps(result)
        assert isinstance(serialised, str)

    def test_gex_accuracy_chart_serialisable(self):
        history = [
            {"timestamp": datetime(2025, 5, 15, 10, 0), "accuracy": 0.72, "signal_count": 10},
        ]
        result = CalibrationVisualization.gex_accuracy_chart(history)
        serialised = json.dumps(result)
        assert isinstance(serialised, str)

    def test_risk_metrics_cards_serialisable(self, sample_trades):
        result = PerformanceVisualization.risk_metrics_cards(sample_trades)
        serialised = json.dumps(result)
        assert isinstance(serialised, str)


# =========================================================================
# 7. EDGE CASES AND ADDITIONAL COVERAGE
# =========================================================================


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_gex_bar_chart_single_strike(self):
        """Bar chart with only one strike should still work."""
        profile = GEXProfile(
            timestamp=datetime(2025, 5, 15, 10, 0),
            strikes=[_make_strike_gex(5220.0)],
            total_net_gex=0.5,
            gamma_flip_level=5220.0,
            call_wall=5220.0,
            put_wall=5220.0,
            max_pain=5220.0,
            plus_gex=5220.0,
            minus_gex=5220.0,
            transition_zone_upper=5225.0,
            transition_zone_lower=5215.0,
            vol_trigger=5220.0,
        )
        result = GEXVisualization.gex_bar_chart(profile, 5220.0)
        assert len(result["strikes"]) == 1

    def test_pnl_distribution_single_trade(self):
        """Distribution with one trade should handle degenerate stats."""
        trade = _make_trade_log(100.0)
        result = PerformanceVisualization.pnl_distribution([trade])
        # With a single value, all bins should have count=1
        total = sum(b["count"] for b in result["bins"])
        assert total == 1

    def test_drawdown_chart_single_point(self):
        """Single equity point should return empty worst_periods."""
        result = PerformanceVisualization.drawdown_chart([100.0])
        assert result["worst_periods"] == []
        assert result["drawdown_abs"] == [0.0]

    def test_factor_weights_sum_preserved(self, sample_factor_weights_history):
        """Weight data in evolution should stay consistent."""
        result = CalibrationVisualization.weight_evolution(
            sample_factor_weights_history
        )
        # Check that each cycle's weights from the series sum to ~1.0
        for i in range(len(sample_factor_weights_history)):
            total = sum(
                series["data"][i] for series in result["series"]
            )
            assert abs(total - 1.0) < 0.01

    def test_color_for_value_many_values(self):
        """Ensure color_for_value returns valid hex for a range of inputs."""
        for v in range(-200, 300, 5):
            c = color_for_value(float(v), -100.0, 100.0)
            assert c.startswith("#")
            assert len(c) == 7
            int(c[1:], 16)

    def test_generate_chart_colors_large_n(self):
        """Large N should not crash and should wrap correctly."""
        colors = generate_chart_colors(100)
        assert len(colors) == 100
        for c in colors:
            assert c.startswith("#")

    def test_neutral_direction_color(self):
        """Neutral direction score should use amber colour."""
        score = DirectionScore(
            total_score=5.0,
            market_internals_score=10.0,
            options_flow_score=-5.0,
            price_action_score=8.0,
            gex_structure_score=3.0,
            cross_asset_score=-2.0,
            factors_agreeing=3,
            has_opposing_factor=True,
            signal=TradeDirection.NEUTRAL,
            confidence=30.0,
            timestamp=datetime(2025, 5, 15, 10, 0),
        )
        result = ScannerVisualization.direction_score_gauge(score)
        assert result["color"] == "#f59e0b"  # amber for NEUTRAL

    def test_all_winning_trades_win_rate(self):
        """100% win rate edge case."""
        trades = [_make_trade_log(100.0), _make_trade_log(200.0)]
        result = PerformanceVisualization.win_rate_by_category(trades)
        assert result["overall"]["win_rate"] == 100.0
        assert result["overall"]["losses"] == 0

    def test_all_losing_trades_win_rate(self):
        """0% win rate edge case."""
        trades = [_make_trade_log(-100.0), _make_trade_log(-200.0)]
        result = PerformanceVisualization.win_rate_by_category(trades)
        assert result["overall"]["win_rate"] == 0.0
        assert result["overall"]["wins"] == 0

    def test_risk_metrics_cards_structure(self, sample_trades):
        """Verify risk_metrics_cards returns proper card structure."""
        result = PerformanceVisualization.risk_metrics_cards(sample_trades)
        assert result["chart_type"] == "risk_metrics"
        assert len(result["cards"]) > 0
        for card in result["cards"]:
            assert "name" in card
            assert "value" in card
            assert "formatted" in card
            assert "description" in card
            assert "color" in card

    def test_risk_metrics_empty_trades(self):
        result = PerformanceVisualization.risk_metrics_cards([])
        assert result["cards"] == []
        assert result["summary"]["total_trades"] == 0

    def test_heatmap_single_profile(self):
        """Heatmap with a single snapshot should work."""
        profile = GEXProfile(
            timestamp=datetime(2025, 5, 15, 10, 0),
            strikes=[_make_strike_gex(5220.0, 1.0, -0.5, 0.5)],
            total_net_gex=0.5,
            gamma_flip_level=5220.0,
            call_wall=5220.0,
            put_wall=5220.0,
            max_pain=5220.0,
            plus_gex=5220.0,
            minus_gex=5220.0,
            transition_zone_upper=5225.0,
            transition_zone_lower=5215.0,
            vol_trigger=5220.0,
        )
        result = GEXVisualization.gex_heatmap([profile])
        assert len(result["timestamps"]) == 1
        assert len(result["strikes"]) == 1
        assert len(result["values"]) == 1
        assert len(result["values"][0]) == 1
