"""
Shared pytest fixtures for SCANIFY 0DTE SPX Scanner test suite.

Provides reusable, realistically-valued fixtures for all test modules covering:
    - Market data (quotes, chains, internals, cross-asset, order book)
    - GEX profiles (per-strike and aggregate)
    - Scanner outputs (direction scores, strike selections, scan signals)
    - Trade logs (winning, losing, mixed)
    - Session setup (trending, range, economic events)
    - Engine instances (Black-Scholes, Greeks, GEX, mock data)
    - Configuration (factor weights, calibration state)

All SPX values anchored at S~6000, VIX~16, VIX1D~14 unless a fixture
explicitly documents a different regime.
"""

from __future__ import annotations

import random
import uuid
from datetime import date, datetime, timedelta
from typing import List

import pytest

from src.scanify_0dte.models import (
    CalibrationState,
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
    KeyLevels,
    MarketInternals,
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
from src.scanify_0dte.greeks_engine import BlackScholes0DTE, GreeksCalculator
from src.scanify_0dte.gex_engine import GEXEngine
from src.scanify_0dte.data_pipeline import MockDataProvider


# ============================================================================
# Constants used across fixtures
# ============================================================================

_SPX_SPOT: float = 6000.0
_VIX: float = 16.0
_VIX1D: float = 14.0
_VIX9D: float = 15.2
_ES_PRICE: float = 6002.50
_TODAY: date = date.today()
_NOW: datetime = datetime.utcnow()
_RISK_FREE_RATE: float = 0.053
_DIVIDEND_YIELD: float = 0.013


# ============================================================================
# 1. MARKET DATA FIXTURES
# ============================================================================


@pytest.fixture
def sample_option_quote() -> OptionQuote:
    """Single OptionQuote: slightly OTM SPX call at the 6010 strike.

    Realistic mid-session 0DTE values with ~4 hours to expiry.
    """
    return OptionQuote(
        strike=6010.0,
        option_type=OptionSide.CALL,
        bid=8.40,
        ask=8.80,
        mid=8.60,
        last=8.55,
        volume=3420,
        open_interest=1850,
        implied_vol=0.142,
        delta=0.42,
        gamma=0.0085,
        theta=-2.80,
        vega=0.95,
        charm=-0.0012,
        vanna=0.0045,
        speed=0.00003,
        timestamp=_NOW,
    )


def _build_chain_quotes(
    spot: float,
    strikes: List[float],
    timestamp: datetime,
) -> List[OptionQuote]:
    """Build paired call/put quotes for a list of strikes.

    IV follows a realistic 0DTE smile: OTM puts have higher IV, OTM calls
    have moderately elevated IV, ATM has the lowest IV.
    """
    quotes: List[OptionQuote] = []
    atm_iv = 0.138

    for strike in strikes:
        distance = strike - spot
        distance_pct = distance / spot

        # Skew: puts get more IV as they go OTM, calls get mild smile
        if distance < 0:
            # OTM put side -- skew steepens for further OTM
            iv_bump = abs(distance_pct) * 1.8
        else:
            # OTM call side -- mild upside smile
            iv_bump = abs(distance_pct) * 0.6

        strike_iv = atm_iv + iv_bump
        moneyness_ratio = strike / spot

        # --- Call ---
        call_delta = max(0.01, min(0.99, 0.50 - (distance / spot) * 5.0))
        call_gamma = max(0.0001, 0.009 * (1.0 - abs(distance_pct) * 8.0))
        call_theta = -max(0.10, 3.50 * call_gamma / 0.009)
        call_mid = max(0.15, (call_delta * 20.0))
        call_spread = max(0.10, call_mid * 0.04)

        call_quote = OptionQuote(
            strike=strike,
            option_type=OptionSide.CALL,
            bid=round(call_mid - call_spread / 2, 2),
            ask=round(call_mid + call_spread / 2, 2),
            mid=round(call_mid, 2),
            last=round(call_mid - 0.05, 2),
            volume=random.randint(800, 8000),
            open_interest=random.randint(500, 5000),
            implied_vol=round(strike_iv, 4),
            delta=round(call_delta, 4),
            gamma=round(call_gamma, 6),
            theta=round(call_theta, 4),
            vega=round(max(0.01, 1.2 * call_gamma / 0.009), 4),
            charm=round(-0.001 * call_delta, 6),
            vanna=round(0.004 * call_gamma / 0.009, 6),
            speed=round(0.00003, 8),
            timestamp=timestamp,
        )
        quotes.append(call_quote)

        # --- Put ---
        put_delta = -(1.0 - call_delta)
        put_gamma = call_gamma
        put_theta = call_theta - 0.05  # Slightly more theta on puts (skew)
        put_mid = max(0.15, abs(put_delta) * 20.0)
        put_spread = max(0.10, put_mid * 0.04)

        put_quote = OptionQuote(
            strike=strike,
            option_type=OptionSide.PUT,
            bid=round(put_mid - put_spread / 2, 2),
            ask=round(put_mid + put_spread / 2, 2),
            mid=round(put_mid, 2),
            last=round(put_mid + 0.03, 2),
            volume=random.randint(600, 7000),
            open_interest=random.randint(400, 4500),
            implied_vol=round(strike_iv, 4),
            delta=round(put_delta, 4),
            gamma=round(put_gamma, 6),
            theta=round(put_theta, 4),
            vega=round(max(0.01, 1.2 * put_gamma / 0.009), 4),
            charm=round(0.001 * abs(put_delta), 6),
            vanna=round(-0.004 * put_gamma / 0.009, 6),
            speed=round(0.00003, 8),
            timestamp=timestamp,
        )
        quotes.append(put_quote)

    return quotes


@pytest.fixture
def sample_options_chain() -> OptionsChain:
    """Complete 0DTE chain with ~20 strikes spanning 5975-6025.

    10 strikes at 5-point spacing: 5 OTM puts through ATM through 5 OTM calls.
    Each strike has a call and put quote (20 quotes total).
    """
    random.seed(42)
    strikes = [5975.0, 5980.0, 5985.0, 5990.0, 5995.0,
               6000.0, 6005.0, 6010.0, 6015.0, 6020.0]
    quotes = _build_chain_quotes(_SPX_SPOT, strikes, _NOW)

    return OptionsChain(
        expiry_date=_TODAY,
        underlying_price=_SPX_SPOT,
        quotes=quotes,
        timestamp=_NOW,
    )


@pytest.fixture
def sample_market_internals() -> MarketInternals:
    """MarketInternals with neutral/slightly-bullish realistic values."""
    return MarketInternals(
        nyse_tick=180,
        nyse_tick_10min_avg=95.0,
        cumulative_tick=12500.0,
        nyse_trin=0.92,
        advance_decline_ratio=1.15,
        up_down_volume_ratio=1.22,
        es_cumulative_delta=8500.0,
        timestamp=_NOW,
    )


@pytest.fixture
def bullish_market_internals() -> MarketInternals:
    """Strongly bullish internals: TICK > +500, TRIN < 0.75, heavy buying."""
    return MarketInternals(
        nyse_tick=680,
        nyse_tick_10min_avg=520.0,
        cumulative_tick=85000.0,
        nyse_trin=0.68,
        advance_decline_ratio=2.35,
        up_down_volume_ratio=2.80,
        es_cumulative_delta=42000.0,
        timestamp=_NOW,
    )


@pytest.fixture
def bearish_market_internals() -> MarketInternals:
    """Strongly bearish internals: TICK < -500, TRIN > 1.40, heavy selling."""
    return MarketInternals(
        nyse_tick=-620,
        nyse_tick_10min_avg=-480.0,
        cumulative_tick=-72000.0,
        nyse_trin=1.55,
        advance_decline_ratio=0.42,
        up_down_volume_ratio=0.38,
        es_cumulative_delta=-38000.0,
        timestamp=_NOW,
    )


@pytest.fixture
def sample_cross_asset_data() -> CrossAssetData:
    """CrossAssetData snapshot: normal VIX regime, stable rates."""
    return CrossAssetData(
        vix=_VIX,
        vix1d=_VIX1D,
        vix9d=_VIX9D,
        vix1d_intraday_avg=14.3,
        us_10y_yield=4.28,
        us_10y_yield_change=-1.5,
        dxy=104.35,
        dxy_change=-0.08,
        es_price=_ES_PRICE,
        es_volume=1_450_000,
        timestamp=_NOW,
    )


@pytest.fixture
def sample_es_order_book() -> ESOrderBook:
    """ESOrderBook with 10 bid/ask levels, slightly bid-heavy imbalance."""
    base_bid = _ES_PRICE - 0.25
    base_ask = _ES_PRICE + 0.25

    bid_levels = [
        (round(base_bid - i * 0.25, 2), random.randint(120, 450))
        for i in range(10)
    ]
    ask_levels = [
        (round(base_ask + i * 0.25, 2), random.randint(100, 400))
        for i in range(10)
    ]

    bid_total = sum(size for _, size in bid_levels)
    ask_total = sum(size for _, size in ask_levels)
    imbalance = (bid_total - ask_total) / (bid_total + ask_total)

    return ESOrderBook(
        bid_levels=bid_levels,
        ask_levels=ask_levels,
        bid_total=bid_total,
        ask_total=ask_total,
        imbalance_ratio=round(imbalance, 4),
        timestamp=_NOW,
    )


# ============================================================================
# 2. GEX FIXTURES
# ============================================================================


def _make_strike_gex(
    strike: float,
    net_gex: float,
    call_oi: int = 2500,
    put_oi: int = 2200,
) -> StrikeGEX:
    """Helper to create a single StrikeGEX with consistent decomposition."""
    # Decompose net_gex into call/put dealer components
    call_gamma = abs(net_gex) * 0.6 if net_gex > 0 else abs(net_gex) * 0.3
    put_gamma = abs(net_gex) * 0.4 if net_gex > 0 else abs(net_gex) * 0.7
    dealer_gamma_call = call_gamma * 0.8
    dealer_gamma_put = -put_gamma * 0.6

    return StrikeGEX(
        strike=strike,
        call_gamma=round(call_gamma, 4),
        put_gamma=round(put_gamma, 4),
        call_oi=call_oi,
        put_oi=put_oi,
        dealer_gamma_call=round(dealer_gamma_call, 4),
        dealer_gamma_put=round(dealer_gamma_put, 4),
        net_gex=round(net_gex, 4),
        net_charm=round(net_gex * -0.02, 6),
        net_vanna=round(net_gex * 0.015, 6),
        net_speed=round(net_gex * 0.0001, 8),
    )


@pytest.fixture
def sample_strike_gex() -> StrikeGEX:
    """Single StrikeGEX at the 6000 strike with moderate positive GEX."""
    return _make_strike_gex(
        strike=6000.0,
        net_gex=125_000.0,
        call_oi=4200,
        put_oi=3800,
    )


def _build_gex_profile(
    total_net_gex: float,
    gamma_flip: float,
    strikes_data: List[StrikeGEX],
) -> GEXProfile:
    """Helper to build a GEXProfile with consistent level derivation."""
    return GEXProfile(
        timestamp=_NOW,
        strikes=strikes_data,
        total_net_gex=total_net_gex,
        gamma_flip_level=gamma_flip,
        call_wall=6025.0,
        put_wall=5975.0,
        max_pain=6000.0,
        plus_gex=6005.0,
        minus_gex=5985.0,
        transition_zone_upper=gamma_flip + 5.0,
        transition_zone_lower=gamma_flip - 5.0,
        vol_trigger=6010.0,
        gex_momentum=total_net_gex * 0.002,
        charm_net_es_contracts=round(total_net_gex * -0.0001, 2),
        vanna_net_exposure=round(total_net_gex * 0.00015, 2),
    )


@pytest.fixture
def sample_gex_profile() -> GEXProfile:
    """Complete GEXProfile with 10 strikes, moderate positive net GEX.

    Gamma flip at 5998 (spot slightly above flip => positive gamma regime).
    """
    strikes = [5975.0, 5980.0, 5985.0, 5990.0, 5995.0,
               6000.0, 6005.0, 6010.0, 6015.0, 6020.0]
    gex_values = [-85_000, -60_000, -30_000, 10_000, 50_000,
                  125_000, 95_000, 60_000, 25_000, -5_000]
    strike_gex_list = [
        _make_strike_gex(s, g) for s, g in zip(strikes, gex_values)
    ]

    return _build_gex_profile(
        total_net_gex=185_000.0,
        gamma_flip=5998.0,
        strikes_data=strike_gex_list,
    )


@pytest.fixture
def positive_gex_profile() -> GEXProfile:
    """GEX profile where net GEX is strongly positive (stabilising).

    Spot well above gamma flip; dealer hedging dampens volatility.
    Total net GEX ~ +450,000.
    """
    strikes = [5975.0, 5980.0, 5985.0, 5990.0, 5995.0,
               6000.0, 6005.0, 6010.0, 6015.0, 6020.0]
    gex_values = [-20_000, -5_000, 25_000, 55_000, 80_000,
                  120_000, 90_000, 60_000, 35_000, 10_000]
    strike_gex_list = [
        _make_strike_gex(s, g) for s, g in zip(strikes, gex_values)
    ]

    return _build_gex_profile(
        total_net_gex=450_000.0,
        gamma_flip=5985.0,
        strikes_data=strike_gex_list,
    )


@pytest.fixture
def negative_gex_profile() -> GEXProfile:
    """GEX profile where net GEX is strongly negative (destabilising).

    Spot below gamma flip; dealer hedging amplifies moves.
    Total net GEX ~ -320,000.
    """
    strikes = [5975.0, 5980.0, 5985.0, 5990.0, 5995.0,
               6000.0, 6005.0, 6010.0, 6015.0, 6020.0]
    gex_values = [-150_000, -110_000, -80_000, -40_000, -10_000,
                  15_000, 20_000, 15_000, 10_000, 10_000]
    strike_gex_list = [
        _make_strike_gex(s, g) for s, g in zip(strikes, gex_values)
    ]

    return _build_gex_profile(
        total_net_gex=-320_000.0,
        gamma_flip=6008.0,
        strikes_data=strike_gex_list,
    )


# ============================================================================
# 3. SCANNER FIXTURES
# ============================================================================


@pytest.fixture
def sample_direction_score() -> DirectionScore:
    """DirectionScore with moderate bullish signal (+38).

    3/5 factors aligned, one opposing factor present.
    """
    return DirectionScore(
        total_score=38.0,
        market_internals_score=42.0,
        options_flow_score=35.0,
        price_action_score=45.0,
        gex_structure_score=22.0,
        cross_asset_score=-15.0,
        factors_agreeing=3,
        has_opposing_factor=True,
        signal=TradeDirection.BULL,
        confidence=62.0,
        timestamp=_NOW,
    )


@pytest.fixture
def strong_bullish_score() -> DirectionScore:
    """High-conviction bullish score (+72). 5/5 factors aligned."""
    return DirectionScore(
        total_score=72.0,
        market_internals_score=78.0,
        options_flow_score=68.0,
        price_action_score=75.0,
        gex_structure_score=65.0,
        cross_asset_score=58.0,
        factors_agreeing=5,
        has_opposing_factor=False,
        signal=TradeDirection.BULL,
        confidence=88.5,
        timestamp=_NOW,
    )


@pytest.fixture
def strong_bearish_score() -> DirectionScore:
    """High-conviction bearish score (-70). 5/5 factors aligned."""
    return DirectionScore(
        total_score=-70.0,
        market_internals_score=-72.0,
        options_flow_score=-65.0,
        price_action_score=-78.0,
        gex_structure_score=-62.0,
        cross_asset_score=-55.0,
        factors_agreeing=5,
        has_opposing_factor=False,
        signal=TradeDirection.BEAR,
        confidence=86.0,
        timestamp=_NOW,
    )


@pytest.fixture
def sample_strike_selection() -> StrikeSelection:
    """Valid StrikeSelection for a liquid OTM call at 6010."""
    return StrikeSelection(
        strike=6010.0,
        option_type=OptionSide.CALL,
        delta=0.42,
        gamma=0.0085,
        theta=-2.80,
        iv=0.142,
        bid=8.40,
        ask=8.80,
        mid=8.60,
        spread_width=0.40,
        oi=1850,
        volume=3420,
        is_liquid=True,
        distance_from_spot=10.0,
        moneyness=6010.0 / _SPX_SPOT,
    )


@pytest.fixture
def sample_scan_signal(
    sample_direction_score: DirectionScore,
    sample_strike_selection: StrikeSelection,
) -> ScanSignal:
    """Complete ScanSignal for a directional long call trade."""
    return ScanSignal(
        scan_type=ScanType.DIRECTIONAL,
        direction=TradeDirection.BULL,
        strike_selection=sample_strike_selection,
        direction_score=sample_direction_score,
        entry_price=8.60,
        stop_loss=4.30,
        profit_target=17.20,
        position_type=PositionType.SINGLE_LONG,
        contracts=2,
        max_risk=860.0,
        expected_reward=1720.0,
        risk_reward_ratio=2.0,
        time_zone=TimeZoneType.MORNING_SESSION,
        session_type=SessionType.TRENDING,
        timestamp=_NOW,
        metadata={
            "scanner_version": "1.0.0",
            "gex_regime": "positive",
        },
    )


# ============================================================================
# 4. TRADE FIXTURES
# ============================================================================


def _make_trade_log(
    *,
    direction: TradeDirection = TradeDirection.BULL,
    option_type: OptionSide = OptionSide.CALL,
    strike: float = 6010.0,
    entry_price: float = 8.60,
    exit_price: float | None = 12.90,
    pnl_dollars: float | None = 430.0,
    pnl_percent: float | None = 50.0,
    exit_reason: ExitReason = ExitReason.PROFIT_TARGET,
    hold_minutes: float = 45.0,
    session_type: SessionType = SessionType.TRENDING,
    time_zone: TimeZoneType = TimeZoneType.MORNING_SESSION,
    composite_score: float = 55.0,
    vix: float = _VIX,
    vix1d: float = _VIX1D,
    net_gex: float = 185_000.0,
) -> TradeLog:
    """Build a single TradeLog with sensible defaults."""
    entry_time = _NOW - timedelta(minutes=hold_minutes)
    return TradeLog(
        trade_id=str(uuid.uuid4()),
        timestamp_entry=entry_time,
        timestamp_exit=_NOW if exit_price is not None else None,
        scan_type=ScanType.DIRECTIONAL,
        direction=direction,
        strike=strike,
        option_type=option_type,
        entry_price=entry_price,
        exit_price=exit_price,
        max_gain_during_trade=max(0.0, (pnl_dollars or 0.0) * 1.2),
        max_loss_during_trade=min(0.0, -(entry_price * 100 * 0.15)),
        pnl_dollars=pnl_dollars,
        pnl_percent=pnl_percent,
        hold_time_minutes=hold_minutes,
        spx_at_entry=_SPX_SPOT,
        vix1d_at_entry=vix1d,
        vix_at_entry=vix,
        expected_move_1sigma=round(_SPX_SPOT * vix1d / 100.0 / 15.87, 2),
        composite_direction_score=composite_score,
        session_type=session_type,
        net_gex_at_entry=net_gex,
        gamma_flip_at_entry=5998.0,
        time_zone=time_zone,
        delta_at_entry=0.42,
        gamma_at_entry=0.0085,
        theta_at_entry=-2.80,
        iv_at_entry=0.142,
        tick_10min_avg=95.0,
        trin_at_entry=0.92,
        ad_ratio_at_entry=1.15,
        cumulative_delta_es=8500.0,
        exit_reason=exit_reason,
        optimal_exit_price=round(entry_price * 1.8, 2) if exit_price else None,
        optimal_exit_time=_NOW + timedelta(minutes=10) if exit_price else None,
        left_on_table_pct=15.0 if exit_price else None,
        was_stopped_prematurely=False,
        counterfactual_notes="Trade executed within expected parameters.",
    )


@pytest.fixture
def sample_trade_log() -> TradeLog:
    """Single complete TradeLog entry: winning directional call trade."""
    return _make_trade_log()


@pytest.fixture
def winning_trades() -> List[TradeLog]:
    """List of 10 winning trades with varied characteristics."""
    rng = random.Random(100)
    trades: List[TradeLog] = []

    for i in range(10):
        strike = 6005.0 + i * 5.0
        entry_px = round(rng.uniform(4.0, 14.0), 2)
        gain_pct = rng.uniform(20.0, 120.0)
        exit_px = round(entry_px * (1 + gain_pct / 100.0), 2)
        pnl = round((exit_px - entry_px) * 100, 2)
        hold = round(rng.uniform(15.0, 90.0), 1)

        direction = TradeDirection.BULL if i % 3 != 2 else TradeDirection.BEAR
        option_type = OptionSide.CALL if direction == TradeDirection.BULL else OptionSide.PUT
        delta_val = round(rng.uniform(0.30, 0.55), 4) if option_type == OptionSide.CALL else round(-rng.uniform(0.30, 0.55), 4)

        trade = _make_trade_log(
            direction=direction,
            option_type=option_type,
            strike=strike,
            entry_price=entry_px,
            exit_price=exit_px,
            pnl_dollars=pnl,
            pnl_percent=round(gain_pct, 2),
            exit_reason=ExitReason.PROFIT_TARGET,
            hold_minutes=hold,
            composite_score=round(rng.uniform(45.0, 85.0), 1),
        )
        trades.append(trade)

    return trades


@pytest.fixture
def losing_trades() -> List[TradeLog]:
    """List of 10 losing trades with varied characteristics."""
    rng = random.Random(200)
    trades: List[TradeLog] = []

    for i in range(10):
        strike = 5990.0 + i * 5.0
        entry_px = round(rng.uniform(5.0, 15.0), 2)
        loss_pct = rng.uniform(30.0, 80.0)
        exit_px = round(entry_px * (1 - loss_pct / 100.0), 2)
        pnl = round((exit_px - entry_px) * 100, 2)
        hold = round(rng.uniform(10.0, 60.0), 1)

        exit_reasons = [ExitReason.STOP_LOSS, ExitReason.TIME_STOP,
                        ExitReason.SIGNAL_REVERSAL, ExitReason.GEX_FLIP]
        exit_reason = exit_reasons[i % len(exit_reasons)]

        direction = TradeDirection.BULL if i % 2 == 0 else TradeDirection.BEAR
        option_type = OptionSide.CALL if direction == TradeDirection.BULL else OptionSide.PUT

        trade = _make_trade_log(
            direction=direction,
            option_type=option_type,
            strike=strike,
            entry_price=entry_px,
            exit_price=exit_px,
            pnl_dollars=pnl,
            pnl_percent=round(-loss_pct, 2),
            exit_reason=exit_reason,
            hold_minutes=hold,
            composite_score=round(rng.uniform(25.0, 55.0), 1),
        )
        trades.append(trade)

    return trades


@pytest.fixture
def mixed_trades() -> List[TradeLog]:
    """List of 50 mixed trades (roughly 55% winners) for calibration testing.

    Covers all session types, time zones, directions, and exit reasons.
    """
    rng = random.Random(300)
    trades: List[TradeLog] = []

    session_types = list(SessionType)
    time_zones = [
        TimeZoneType.OPENING_AUCTION,
        TimeZoneType.MORNING_SESSION,
        TimeZoneType.MIDDAY_LULL,
        TimeZoneType.AFTERNOON_ACCEL,
        TimeZoneType.POWER_HOUR,
    ]
    win_exit_reasons = [ExitReason.PROFIT_TARGET, ExitReason.SIGNAL_REVERSAL]
    loss_exit_reasons = [ExitReason.STOP_LOSS, ExitReason.TIME_STOP,
                         ExitReason.GEX_FLIP, ExitReason.VIX_SPIKE]

    for i in range(50):
        is_winner = rng.random() < 0.55
        direction = rng.choice([TradeDirection.BULL, TradeDirection.BEAR])
        option_type = OptionSide.CALL if direction == TradeDirection.BULL else OptionSide.PUT
        strike = round(rng.uniform(5980.0, 6020.0) / 5.0) * 5.0
        entry_px = round(rng.uniform(3.0, 18.0), 2)
        session = rng.choice(session_types)
        tz = rng.choice(time_zones)

        if is_winner:
            gain_pct = rng.uniform(15.0, 150.0)
            exit_px = round(entry_px * (1 + gain_pct / 100.0), 2)
            pnl = round((exit_px - entry_px) * 100, 2)
            exit_reason = rng.choice(win_exit_reasons)
        else:
            loss_pct = rng.uniform(20.0, 90.0)
            exit_px = round(entry_px * (1 - loss_pct / 100.0), 2)
            pnl = round((exit_px - entry_px) * 100, 2)
            gain_pct = -loss_pct
            exit_reason = rng.choice(loss_exit_reasons)

        hold = round(rng.uniform(8.0, 120.0), 1)
        score = round(rng.uniform(-80.0, 80.0), 1)
        vix_val = round(rng.uniform(12.0, 28.0), 1)
        net_gex_val = round(rng.uniform(-400_000, 500_000), 0)

        trade = _make_trade_log(
            direction=direction,
            option_type=option_type,
            strike=strike,
            entry_price=entry_px,
            exit_price=exit_px,
            pnl_dollars=pnl,
            pnl_percent=round(gain_pct, 2),
            exit_reason=exit_reason,
            hold_minutes=hold,
            session_type=session,
            time_zone=tz,
            composite_score=score,
            vix=vix_val,
            vix1d=round(vix_val * 0.88, 1),
            net_gex=net_gex_val,
        )
        trades.append(trade)

    return trades


# ============================================================================
# 5. SESSION FIXTURES
# ============================================================================


def _make_key_levels() -> KeyLevels:
    """Build a KeyLevels instance with realistic prior-session and GEX levels."""
    return KeyLevels(
        max_pain=6000.0,
        plus_gex=6005.0,
        minus_gex=5985.0,
        call_wall=6025.0,
        put_wall=5975.0,
        gamma_flip=5998.0,
        vol_trigger=6010.0,
        transition_zone_upper=6003.0,
        transition_zone_lower=5993.0,
        prior_high=6012.50,
        prior_low=5985.25,
        prior_close=5997.80,
        prior_vwap=5998.40,
        overnight_high=6008.75,
        overnight_low=5992.00,
        round_levels=[5950.0, 6000.0, 6050.0],
        moving_averages={
            "SMA_20": 5995.50,
            "EMA_9": 6001.25,
            "SMA_50": 5972.30,
        },
    )


def _make_gap_analysis(
    gap_pct: float = 0.12,
    gap_points: float = 7.2,
) -> GapAnalysis:
    """Build a GapAnalysis with configurable gap size."""
    gap_sigma = gap_points / 12.0  # ~12-point 1-sigma expected move
    classification = (
        GapClassification.MICRO if abs(gap_pct) < 0.15
        else GapClassification.SMALL if abs(gap_pct) < 0.35
        else GapClassification.MEDIUM if abs(gap_pct) < 0.65
        else GapClassification.LARGE if abs(gap_pct) < 1.0
        else GapClassification.MEGA
    )
    return GapAnalysis(
        gap_pct=gap_pct,
        gap_points=gap_points,
        gap_sigma=round(gap_sigma, 4),
        classification=classification,
        gap_fill_probability={
            "30min": 0.45,
            "60min": 0.58,
            "120min": 0.68,
            "eod": 0.72,
        },
    )


def _make_expected_move() -> ExpectedMove:
    """Build an ExpectedMove using VIX1D ~ 14 baseline."""
    # VIX1D-based: SPX * VIX1D / sqrt(252) => 6000 * 0.14 / 15.87 ~ 52.9
    # For 0DTE, 1-sigma ~ 12 points is more realistic intraday
    return ExpectedMove(
        method1_vix1d=12.4,
        method2_straddle=11.8,
        method3_rv_adjusted=10.5,
        final_1sigma=11.8,
        final_2sigma=23.6,
        iv_rv_ratio=1.12,
        vol_regime="NORMAL",
    )


@pytest.fixture
def trending_session() -> SessionSetup:
    """SessionSetup configured for a trending day with a moderate gap-up."""
    return SessionSetup(
        gap_analysis=_make_gap_analysis(gap_pct=0.35, gap_points=21.0),
        expected_move=_make_expected_move(),
        key_levels=_make_key_levels(),
        session_type=SessionType.TRENDING,
        economic_events=[],
        risk_assessment=(
            "Moderate gap-up with strong overnight internals. "
            "Trending day expected with momentum follow-through. "
            "Key resistance at call wall 6025; support at put wall 5975."
        ),
        timestamp=_NOW,
    )


@pytest.fixture
def range_session() -> SessionSetup:
    """SessionSetup configured for a range-bound day with a micro gap."""
    return SessionSetup(
        gap_analysis=_make_gap_analysis(gap_pct=0.05, gap_points=3.0),
        expected_move=_make_expected_move(),
        key_levels=_make_key_levels(),
        session_type=SessionType.RANGE,
        economic_events=[],
        risk_assessment=(
            "Micro gap with no directional conviction overnight. "
            "Range-bound session expected between 5990-6010. "
            "Mean reversion strategies favoured."
        ),
        timestamp=_NOW,
    )


@pytest.fixture
def sample_economic_events() -> List[EconomicEvent]:
    """List of economic events including HIGH, MED, and LOW impact."""
    base_date = _TODAY
    return [
        EconomicEvent(
            time=datetime(base_date.year, base_date.month, base_date.day, 8, 30),
            name="Nonfarm Payrolls",
            impact_level=ImpactLevel.HIGH,
            expected_value="180K",
            previous_value="216K",
            actual_value=None,
        ),
        EconomicEvent(
            time=datetime(base_date.year, base_date.month, base_date.day, 8, 30),
            name="Unemployment Rate",
            impact_level=ImpactLevel.HIGH,
            expected_value="3.8%",
            previous_value="3.7%",
            actual_value=None,
        ),
        EconomicEvent(
            time=datetime(base_date.year, base_date.month, base_date.day, 10, 0),
            name="ISM Services PMI",
            impact_level=ImpactLevel.MED,
            expected_value="52.5",
            previous_value="52.7",
            actual_value=None,
        ),
        EconomicEvent(
            time=datetime(base_date.year, base_date.month, base_date.day, 10, 0),
            name="Factory Orders",
            impact_level=ImpactLevel.LOW,
            expected_value="-0.5%",
            previous_value="0.2%",
            actual_value=None,
        ),
        EconomicEvent(
            time=datetime(base_date.year, base_date.month, base_date.day, 13, 0),
            name="Fed Speaker - Williams",
            impact_level=ImpactLevel.MED,
            expected_value=None,
            previous_value=None,
            actual_value=None,
        ),
    ]


# ============================================================================
# 6. ENGINE FIXTURES
# ============================================================================


@pytest.fixture
def bs_calculator() -> BlackScholes0DTE:
    """BlackScholes0DTE instance with default risk-free rate and dividend yield.

    r=0.053 (5.3%), q=0.013 (1.3%).
    """
    return BlackScholes0DTE(
        risk_free_rate=_RISK_FREE_RATE,
        dividend_yield=_DIVIDEND_YIELD,
    )


@pytest.fixture
def greeks_calculator(bs_calculator: BlackScholes0DTE) -> GreeksCalculator:
    """GreeksCalculator wrapping the shared BlackScholes0DTE instance."""
    return GreeksCalculator(bs=bs_calculator)


@pytest.fixture
def gex_engine(bs_calculator: BlackScholes0DTE) -> GEXEngine:
    """GEXEngine instance using hybrid dealer model (default 60/40 weighting)."""
    return GEXEngine(
        bs_calculator=bs_calculator,
        dealer_model="hybrid",
        oi_weight=0.6,
        flow_weight=0.4,
    )


@pytest.fixture
def mock_data_feed() -> MockDataProvider:
    """MockDataProvider in 'normal' scenario, base SPX=6000, VIX=16."""
    return MockDataProvider(
        scenario="normal",
        base_spx=_SPX_SPOT,
        base_vix=_VIX,
    )


# ============================================================================
# 7. CONFIGURATION FIXTURES
# ============================================================================


@pytest.fixture
def sample_factor_weights() -> FactorWeights:
    """Default FactorWeights (equal 20% weighting across all five factors)."""
    return FactorWeights(
        market_internals=0.20,
        options_flow=0.20,
        price_action=0.20,
        gex_structure=0.20,
        cross_asset=0.20,
    )


@pytest.fixture
def sample_calibration_state(
    sample_factor_weights: FactorWeights,
) -> CalibrationState:
    """Default CalibrationState with baseline parameters.

    Entry threshold at 40, stop-loss at 50%, normal VIX regime.
    """
    return CalibrationState(
        current_weights=sample_factor_weights,
        entry_threshold=40.0,
        profit_targets_by_zone={
            TimeZoneType.OPENING_AUCTION.value: 80.0,
            TimeZoneType.MORNING_SESSION.value: 60.0,
            TimeZoneType.MIDDAY_LULL.value: 40.0,
            TimeZoneType.AFTERNOON_ACCEL.value: 50.0,
            TimeZoneType.POWER_HOUR.value: 70.0,
            TimeZoneType.SETTLEMENT_WINDOW.value: 30.0,
        },
        stop_loss_pct=50.0,
        regime="NORMAL",
        last_calibration=_NOW - timedelta(hours=18),
        trade_count=127,
        gex_signal_accuracy=0.72,
    )
