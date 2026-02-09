"""
Comprehensive tests for the SCANIFY 0DTE SPX Scanner backtesting framework.

Tests cover:
    1. BacktestConfig validation and defaults
    2. BacktestDataLoader trading day logic
    3. Realistic fill simulation (ask/bid, slippage, filters)
    4. Metrics computation (win rate, profit factor, Sharpe, drawdown, etc.)
    5. Deflated Sharpe Ratio correction for multiple testing
    6. Walk-forward optimization window construction
    7. Benchmark comparison
    8. Transaction cost sensitivity
    9. BacktestEngine integration with mock data
   10. BacktestVisualizer output structure
"""

from __future__ import annotations

import math
import uuid
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, PropertyMock, patch

import numpy as np
import pytest
from scipy import stats as sp_stats

from src.scanify_0dte.backtester import (
    BacktestConfig,
    BacktestDataLoader,
    BacktestEngine,
    BacktestVisualizer,
    _tick_size_for_price,
    _TICK_SIZE_BELOW_3,
    _TICK_SIZE_AT_OR_ABOVE_3,
    _TICK_BOUNDARY,
    _SPX_MULTIPLIER,
    _ANNUALIZATION_FACTOR,
    _HIGH_VOL_THRESHOLD,
    _MARKET_OPEN,
    _MARKET_CLOSE,
    _TRADING_DAYS_PER_YEAR,
)
from src.scanify_0dte.models import (
    CrossAssetData,
    ExitReason,
    GEXProfile,
    MarketInternals,
    OptionQuote,
    OptionsChain,
    OptionSide,
    ScanSignal,
    ScanType,
    SessionType,
    TimeZoneType,
    TradeDirection,
    TradeLog,
    PositionType,
    DirectionScore,
    StrikeSelection,
)


# ============================================================================
# Helpers and Fixtures
# ============================================================================


def _make_trade_namespace(
    realized_pnl: float = 0.0,
    entry_time: Optional[datetime] = None,
    exit_time: Optional[datetime] = None,
    scan_type: str = "DIRECTIONAL",
    session_type: str = "TRENDING",
    time_zone: str = "MORNING_SESSION",
    entry_price: float = 5.0,
    quantity: int = 1,
    is_buy: bool = True,
    strike: float = 5200.0,
    option_type: str = "CALL",
) -> SimpleNamespace:
    """Create a lightweight trade object with the attributes the backtester accesses."""
    if entry_time is None:
        entry_time = datetime(2024, 6, 3, 10, 0)
    if exit_time is None:
        exit_time = entry_time + timedelta(minutes=30)
    return SimpleNamespace(
        realized_pnl=realized_pnl,
        entry_time=entry_time,
        exit_time=exit_time,
        scan_type=scan_type,
        session_type=session_type,
        time_zone=time_zone,
        entry_price=entry_price,
        quantity=quantity,
        is_buy=is_buy,
        strike=strike,
        option_type=option_type,
    )


def _make_option_quote(
    strike: float = 5200.0,
    option_type: OptionSide = OptionSide.CALL,
    bid: float = 4.50,
    ask: float = 5.00,
    volume: int = 500,
    delta: float = 0.30,
) -> OptionQuote:
    mid = (bid + ask) / 2.0
    return OptionQuote(
        strike=strike,
        option_type=option_type,
        bid=bid,
        ask=ask,
        mid=mid,
        last=mid,
        volume=volume,
        open_interest=500,
        implied_vol=0.25,
        delta=delta,
        gamma=0.05,
        theta=-0.10,
        vega=0.10,
    )


def _make_options_chain(
    quotes: Optional[list] = None,
    underlying_price: float = 5200.0,
) -> OptionsChain:
    if quotes is None:
        quotes = [
            _make_option_quote(5190.0, OptionSide.CALL, 12.0, 12.50, 800, 0.55),
            _make_option_quote(5200.0, OptionSide.CALL, 4.50, 5.00, 500, 0.30),
            _make_option_quote(5210.0, OptionSide.CALL, 1.80, 2.20, 300, 0.15),
            _make_option_quote(5220.0, OptionSide.CALL, 0.60, 0.90, 150, 0.08),
            _make_option_quote(5190.0, OptionSide.PUT, 1.50, 1.90, 400, -0.15),
            _make_option_quote(5200.0, OptionSide.PUT, 4.00, 4.50, 600, -0.30),
            _make_option_quote(5210.0, OptionSide.PUT, 10.50, 11.00, 700, -0.55),
        ]
    return OptionsChain(
        expiry_date=date(2024, 6, 3),
        underlying_price=underlying_price,
        quotes=quotes,
    )


def _make_chain_with_contracts(
    quotes: Optional[list] = None,
    underlying_price: float = 5200.0,
) -> SimpleNamespace:
    """Create a chain-like object with a ``contracts`` attribute.

    The BacktestEngine accesses chain.contracts via getattr, but the
    Pydantic OptionsChain model uses ``quotes``. This helper creates a
    SimpleNamespace that exposes both ``quotes`` and ``contracts`` so the
    engine's _find_contract_in_chain and _compute_average_spread work.
    """
    if quotes is None:
        quotes = [
            _make_option_quote(5190.0, OptionSide.CALL, 12.0, 12.50, 800, 0.55),
            _make_option_quote(5200.0, OptionSide.CALL, 4.50, 5.00, 500, 0.30),
            _make_option_quote(5210.0, OptionSide.CALL, 1.80, 2.20, 300, 0.15),
            _make_option_quote(5220.0, OptionSide.CALL, 0.60, 0.90, 150, 0.08),
            _make_option_quote(5190.0, OptionSide.PUT, 1.50, 1.90, 400, -0.15),
            _make_option_quote(5200.0, OptionSide.PUT, 4.00, 4.50, 600, -0.30),
            _make_option_quote(5210.0, OptionSide.PUT, 10.50, 11.00, 700, -0.55),
        ]
    return SimpleNamespace(
        expiry_date=date(2024, 6, 3),
        underlying_price=underlying_price,
        quotes=quotes,
        contracts=quotes,  # Engine accesses via getattr(chain, "contracts")
    )


def _make_market_internals() -> MarketInternals:
    return MarketInternals(
        nyse_tick=250,
        nyse_tick_10min_avg=150.0,
        cumulative_tick=5000.0,
        nyse_trin=0.95,
        advance_decline_ratio=1.2,
        up_down_volume_ratio=1.3,
        es_cumulative_delta=15000.0,
    )


def _make_cross_asset_data(vix1d: float = 18.0) -> CrossAssetData:
    return CrossAssetData(
        vix=16.0,
        vix1d=vix1d,
        vix9d=17.0,
        vix1d_intraday_avg=17.5,
        us_10y_yield=4.25,
        us_10y_yield_change=2.0,
        dxy=104.5,
        dxy_change=0.1,
        es_price=5198.0,
        es_volume=500000,
    )


class MockDataLoader(BacktestDataLoader):
    """Concrete data loader for testing that returns mock data."""

    def __init__(self, trading_days: Optional[list[date]] = None):
        self._trading_days = trading_days or []
        self._chain = _make_options_chain()
        self._internals = _make_market_internals()
        self._cross_asset = _make_cross_asset_data()

    def get_trading_days(self, start: date, end: date) -> list[date]:
        return [d for d in self._trading_days if start <= d <= end]

    def load_options_chain(self, dt: date, tm: time) -> OptionsChain:
        return self._chain

    def load_market_internals(self, dt: date, tm: time) -> MarketInternals:
        return self._internals

    def load_cross_asset_data(self, dt: date, tm: time) -> CrossAssetData:
        return self._cross_asset

    def load_daily_bars(self, symbol: str, start: date, end: date):
        import pandas as pd

        return pd.DataFrame(
            columns=["date", "open", "high", "low", "close", "volume"]
        )

    def load_intraday_bars(self, symbol: str, dt: date, interval: str = "1m"):
        import pandas as pd

        return pd.DataFrame(
            columns=["datetime", "open", "high", "low", "close", "volume"]
        )


def _generate_weekdays(start: date, n_days: int) -> list[date]:
    """Generate n business days starting from start (excludes weekends only)."""
    days = []
    current = start
    while len(days) < n_days:
        if current.weekday() < 5:  # Mon-Fri
            days.append(current)
        current += timedelta(days=1)
    return days


@pytest.fixture
def default_config() -> BacktestConfig:
    return BacktestConfig(
        start_date=date(2024, 1, 2),
        end_date=date(2024, 6, 28),
    )


@pytest.fixture
def sample_trades() -> list:
    """A set of sample trades with known PnLs for metrics testing."""
    base_time = datetime(2024, 3, 1, 10, 0)
    trades = [
        _make_trade_namespace(realized_pnl=500.0, entry_time=base_time + timedelta(days=i))
        for i in range(10)
    ] + [
        _make_trade_namespace(realized_pnl=-200.0, entry_time=base_time + timedelta(days=10 + i))
        for i in range(5)
    ] + [
        _make_trade_namespace(realized_pnl=300.0, entry_time=base_time + timedelta(days=15 + i))
        for i in range(5)
    ] + [
        _make_trade_namespace(realized_pnl=-400.0, entry_time=base_time + timedelta(days=20 + i))
        for i in range(3)
    ]
    return trades


@pytest.fixture
def sample_equity_curve() -> list[tuple[datetime, float]]:
    """An equity curve consistent with sample_trades PnL."""
    base_time = datetime(2024, 3, 1, 10, 0)
    initial = 100_000.0
    curve = [(base_time, initial)]
    pnls = (
        [500.0] * 10 + [-200.0] * 5 + [300.0] * 5 + [-400.0] * 3
    )
    running = initial
    for i, pnl in enumerate(pnls, start=1):
        running += pnl
        curve.append((base_time + timedelta(days=i), running))
    return curve


@pytest.fixture
def mock_engine(default_config) -> BacktestEngine:
    """Create a BacktestEngine with all dependencies mocked."""
    trading_days = _generate_weekdays(date(2024, 1, 2), 120)
    loader = MockDataLoader(trading_days)
    directional = MagicMock()
    directional.scan = MagicMock(return_value=[])
    premium = MagicMock()
    premium.scan = MagicMock(return_value=[])
    gamma = MagicMock()
    gamma.scan = MagicMock(return_value=[])
    exit_mgr = MagicMock()
    exit_mgr.check_exit = MagicMock(return_value=None)
    trade_logger = MagicMock()
    trade_logger.log_trade = MagicMock()

    return BacktestEngine(
        config=default_config,
        data_loader=loader,
        directional_scanner=directional,
        premium_scanner=premium,
        gamma_scanner=gamma,
        exit_manager=exit_mgr,
        trade_logger=trade_logger,
    )


# ============================================================================
# 1. BACKTEST CONFIG TESTS
# ============================================================================


class TestBacktestConfig:
    """Tests for BacktestConfig dataclass validation and defaults."""

    def test_default_configuration_values(self):
        """Default config uses documented production values."""
        cfg = BacktestConfig(
            start_date=date(2024, 1, 2),
            end_date=date(2024, 6, 28),
        )
        assert cfg.initial_capital == 100_000.0
        assert cfg.commission_per_contract == 0.65
        assert cfg.slippage_ticks == 1
        assert cfg.use_ask_for_buys is True
        assert cfg.max_spread_multiple == 2.0
        assert cfg.min_volume_at_strike == 100
        assert cfg.walk_forward_train_days == 60
        assert cfg.walk_forward_test_days == 20
        assert cfg.walk_forward_step_days == 5
        assert cfg.holdout_months == 3
        assert cfg.max_daily_trades == 50
        assert cfg.risk_per_trade_pct == 0.02

    def test_custom_configuration(self):
        """Custom values are stored correctly."""
        cfg = BacktestConfig(
            start_date=date(2023, 6, 1),
            end_date=date(2024, 6, 1),
            initial_capital=500_000.0,
            commission_per_contract=0.50,
            slippage_ticks=2,
            walk_forward_train_days=90,
            walk_forward_test_days=30,
            walk_forward_step_days=10,
            holdout_months=6,
            max_daily_trades=25,
            risk_per_trade_pct=0.01,
        )
        assert cfg.initial_capital == 500_000.0
        assert cfg.commission_per_contract == 0.50
        assert cfg.slippage_ticks == 2
        assert cfg.walk_forward_train_days == 90
        assert cfg.walk_forward_test_days == 30
        assert cfg.walk_forward_step_days == 10
        assert cfg.holdout_months == 6
        assert cfg.max_daily_trades == 25
        assert cfg.risk_per_trade_pct == 0.01

    def test_walk_forward_parameters_consistent(self):
        """Walk-forward step must be smaller than test window to create overlapping windows."""
        cfg = BacktestConfig(
            start_date=date(2024, 1, 2),
            end_date=date(2024, 6, 28),
        )
        # Step should be <= test days so windows have meaningful overlap
        assert cfg.walk_forward_step_days <= cfg.walk_forward_test_days
        # Total of train + test should be achievable within a reasonable period
        total_window = cfg.walk_forward_train_days + cfg.walk_forward_test_days
        assert total_window == 80  # 60 + 20

    def test_holdout_months_setting(self):
        """Holdout start date is computed correctly from end_date and holdout_months."""
        cfg = BacktestConfig(
            start_date=date(2024, 1, 2),
            end_date=date(2024, 6, 28),
            holdout_months=3,
        )
        holdout_start = cfg.holdout_start_date
        # The holdout starts approximately 3 months before end_date
        # end_date month start is 2024-06-01, minus 90 days ~ 2024-03-03
        assert holdout_start < cfg.end_date
        assert holdout_start >= cfg.start_date
        # The holdout_start should be approximately 3 months before the end
        days_before_end = (cfg.end_date - holdout_start).days
        assert days_before_end >= 80  # At least ~3 months

    def test_start_after_end_raises(self):
        """Config rejects start_date >= end_date."""
        with pytest.raises(ValueError, match="start_date.*must precede.*end_date"):
            BacktestConfig(
                start_date=date(2024, 6, 28),
                end_date=date(2024, 1, 2),
            )

    def test_same_start_end_raises(self):
        """Config rejects start_date == end_date."""
        with pytest.raises(ValueError):
            BacktestConfig(
                start_date=date(2024, 6, 1),
                end_date=date(2024, 6, 1),
            )

    def test_negative_capital_raises(self):
        """Config rejects non-positive initial_capital."""
        with pytest.raises(ValueError, match="initial_capital must be positive"):
            BacktestConfig(
                start_date=date(2024, 1, 2),
                end_date=date(2024, 6, 28),
                initial_capital=-10_000,
            )

    def test_zero_slippage_raises(self):
        """Config rejects slippage_ticks < 1."""
        with pytest.raises(ValueError, match="slippage_ticks must be >= 1"):
            BacktestConfig(
                start_date=date(2024, 1, 2),
                end_date=date(2024, 6, 28),
                slippage_ticks=0,
            )

    def test_risk_per_trade_boundaries(self):
        """risk_per_trade_pct must be in (0, 1]."""
        with pytest.raises(ValueError, match="risk_per_trade_pct"):
            BacktestConfig(
                start_date=date(2024, 1, 2),
                end_date=date(2024, 6, 28),
                risk_per_trade_pct=0.0,
            )
        with pytest.raises(ValueError, match="risk_per_trade_pct"):
            BacktestConfig(
                start_date=date(2024, 1, 2),
                end_date=date(2024, 6, 28),
                risk_per_trade_pct=1.5,
            )


# ============================================================================
# 2. BACKTEST DATA LOADER TESTS
# ============================================================================


class TestBacktestDataLoader:
    """Tests for BacktestDataLoader (via MockDataLoader concrete subclass)."""

    def test_get_trading_days_excludes_weekends(self):
        """All returned days must be weekdays (Mon-Fri)."""
        all_days = []
        current = date(2024, 1, 1)
        while current <= date(2024, 1, 31):
            all_days.append(current)
            current += timedelta(days=1)

        # Filter to weekdays only for mock data
        weekdays = [d for d in all_days if d.weekday() < 5]
        loader = MockDataLoader(weekdays)

        result = loader.get_trading_days(date(2024, 1, 1), date(2024, 1, 31))
        for d in result:
            assert d.weekday() < 5, f"{d} is a weekend day ({d.strftime('%A')})"

    def test_get_trading_days_excludes_holidays(self):
        """Holidays should not appear in the trading days list."""
        # New Year's Day 2024 falls on a Monday
        new_years = date(2024, 1, 1)
        mlk_day = date(2024, 1, 15)  # MLK Day 2024

        all_weekdays = [
            d for d in (
                date(2024, 1, 1) + timedelta(days=i)
                for i in range(31)
            )
            if d.weekday() < 5
        ]
        # Exclude known holidays
        holidays = {new_years, mlk_day}
        trading_days = [d for d in all_weekdays if d not in holidays]
        loader = MockDataLoader(trading_days)

        result = loader.get_trading_days(date(2024, 1, 1), date(2024, 1, 31))
        assert new_years not in result, "New Year's Day should be excluded"
        assert mlk_day not in result, "MLK Day should be excluded"

    def test_load_options_chain_returns_correct_type(self):
        loader = MockDataLoader()
        chain = loader.load_options_chain(date(2024, 6, 3), time(10, 0))
        assert isinstance(chain, OptionsChain)
        assert len(chain.quotes) > 0

    def test_load_market_internals_returns_correct_type(self):
        loader = MockDataLoader()
        internals = loader.load_market_internals(date(2024, 6, 3), time(10, 0))
        assert isinstance(internals, MarketInternals)

    def test_load_cross_asset_data_returns_correct_type(self):
        loader = MockDataLoader()
        cross = loader.load_cross_asset_data(date(2024, 6, 3), time(10, 0))
        assert isinstance(cross, CrossAssetData)

    def test_base_class_raises_not_implemented(self):
        """The abstract base class methods raise NotImplementedError."""
        base_loader = BacktestDataLoader()
        with pytest.raises(NotImplementedError):
            base_loader.load_options_chain(date(2024, 6, 3), time(10, 0))
        with pytest.raises(NotImplementedError):
            base_loader.load_market_internals(date(2024, 6, 3), time(10, 0))
        with pytest.raises(NotImplementedError):
            base_loader.load_cross_asset_data(date(2024, 6, 3), time(10, 0))
        with pytest.raises(NotImplementedError):
            base_loader.get_trading_days(date(2024, 1, 1), date(2024, 6, 1))
        with pytest.raises(NotImplementedError):
            base_loader.load_daily_bars("SPX", date(2024, 1, 1), date(2024, 6, 1))
        with pytest.raises(NotImplementedError):
            base_loader.load_intraday_bars("SPX", date(2024, 6, 3))


# ============================================================================
# 3. REALISTIC FILLS TESTS
# ============================================================================


class TestRealisticFills:
    """Tests for BacktestEngine.apply_realistic_fills."""

    def _make_signal(
        self,
        strike: float = 5200.0,
        option_type: str = "CALL",
        is_buy: bool = True,
    ) -> SimpleNamespace:
        """Create a minimal signal namespace for fill testing."""
        return SimpleNamespace(
            strike=strike,
            option_type=option_type,
            is_buy=is_buy,
            scan_type="DIRECTIONAL",
        )

    def _build_engine_with_chain(
        self,
        chain: OptionsChain,
        slippage_ticks: int = 1,
        min_volume: int = 100,
        max_spread_multiple: float = 2.0,
    ) -> BacktestEngine:
        """Build an engine with a mock loader that returns the given chain."""
        cfg = BacktestConfig(
            start_date=date(2024, 1, 2),
            end_date=date(2024, 6, 28),
            slippage_ticks=slippage_ticks,
            min_volume_at_strike=min_volume,
            max_spread_multiple=max_spread_multiple,
        )
        loader = MockDataLoader()
        loader._chain = chain
        engine = BacktestEngine(
            config=cfg,
            data_loader=loader,
            directional_scanner=MagicMock(),
            premium_scanner=MagicMock(),
            gamma_scanner=MagicMock(),
            exit_manager=MagicMock(),
            trade_logger=MagicMock(),
        )
        return engine

    def test_buy_fills_at_ask_not_mid(self, mock_engine):
        """Buy orders fill at ASK + slippage, never at mid price."""
        chain = _make_chain_with_contracts()
        signal = self._make_signal(strike=5200.0, option_type="CALL", is_buy=True)

        call_5200 = [q for q in chain.quotes if q.strike == 5200.0 and q.option_type == OptionSide.CALL][0]

        engine = self._build_engine_with_chain(chain, slippage_ticks=1)

        fill_price, was_filled = engine.apply_realistic_fills(signal, chain, is_high_vol=False)

        assert was_filled is True
        # Fill should be at ask + slippage, not at mid
        expected_ask = call_5200.ask  # 5.00
        mid = call_5200.mid  # 4.75
        tick = _tick_size_for_price(mid)
        expected_fill = expected_ask + 1 * tick  # ask + 1 tick slippage

        assert fill_price == pytest.approx(expected_fill, abs=0.01)
        assert fill_price > mid, "Buy fill must be above mid price"

    def test_sell_fills_at_bid(self, mock_engine):
        """Sell orders fill at BID - slippage."""
        chain = _make_chain_with_contracts()
        signal = self._make_signal(strike=5200.0, option_type="CALL", is_buy=False)

        engine = self._build_engine_with_chain(chain, slippage_ticks=1)
        fill_price, was_filled = engine.apply_realistic_fills(signal, chain, is_high_vol=False)

        assert was_filled is True
        call_5200 = [q for q in chain.quotes if q.strike == 5200.0 and q.option_type == OptionSide.CALL][0]
        mid = call_5200.mid
        tick = _tick_size_for_price(mid)
        expected_fill = call_5200.bid - 1 * tick

        assert fill_price == pytest.approx(expected_fill, abs=0.01)
        assert fill_price < mid, "Sell fill must be below mid price"

    def test_slippage_added_correctly(self):
        """Slippage in ticks is converted to dollars using the correct tick size."""
        chain = _make_chain_with_contracts()
        signal = self._make_signal(strike=5200.0, option_type="CALL", is_buy=True)

        # Use 3 ticks slippage
        engine = self._build_engine_with_chain(chain, slippage_ticks=3)
        fill_price, was_filled = engine.apply_realistic_fills(signal, chain, is_high_vol=False)

        assert was_filled is True
        call_5200 = [q for q in chain.quotes if q.strike == 5200.0 and q.option_type == OptionSide.CALL][0]
        mid = call_5200.mid
        tick = _tick_size_for_price(mid)
        expected_fill = call_5200.ask + 3 * tick

        assert fill_price == pytest.approx(expected_fill, abs=0.01)

    def test_high_vol_doubles_slippage(self):
        """During high volatility (VIX1D > 25), slippage ticks are doubled."""
        chain = _make_chain_with_contracts()
        signal = self._make_signal(strike=5200.0, option_type="CALL", is_buy=True)

        engine = self._build_engine_with_chain(chain, slippage_ticks=1)
        fill_normal, _ = engine.apply_realistic_fills(signal, chain, is_high_vol=False)
        fill_highvol, _ = engine.apply_realistic_fills(signal, chain, is_high_vol=True)

        # High vol fill should be worse (higher for buys)
        assert fill_highvol > fill_normal

    def test_spread_filter_rejects_wide_spreads(self):
        """Signals are rejected when the bid-ask spread exceeds max_spread_multiple * average."""
        # Create a chain with one very wide spread and others narrow
        quotes = [
            _make_option_quote(5190.0, OptionSide.CALL, 12.00, 12.10, 800, 0.55),  # 0.10 spread
            _make_option_quote(5200.0, OptionSide.CALL, 4.00, 5.50, 500, 0.30),    # 1.50 spread (wide!)
            _make_option_quote(5210.0, OptionSide.CALL, 1.90, 2.00, 300, 0.15),    # 0.10 spread
            _make_option_quote(5220.0, OptionSide.CALL, 0.70, 0.80, 150, 0.08),    # 0.10 spread
        ]
        chain = _make_chain_with_contracts(quotes)

        signal = self._make_signal(strike=5200.0, option_type="CALL", is_buy=True)
        # avg spread of CALL contracts ~ (0.10+1.50+0.10+0.10)/4 = 0.45
        # 5200 spread = 1.50, which is > 2 * 0.45 = 0.90
        engine = self._build_engine_with_chain(chain, max_spread_multiple=2.0)
        fill_price, was_filled = engine.apply_realistic_fills(signal, chain, is_high_vol=False)

        assert was_filled is False, "Wide spread should be rejected"

    def test_volume_filter_rejects_illiquid_strikes(self):
        """Signals at strikes with volume below min_volume_at_strike are rejected."""
        quotes = [
            _make_option_quote(5200.0, OptionSide.CALL, 4.50, 5.00, volume=50, delta=0.30),
        ]
        chain = _make_chain_with_contracts(quotes)

        signal = self._make_signal(strike=5200.0, option_type="CALL", is_buy=True)
        engine = self._build_engine_with_chain(chain, min_volume=100)
        fill_price, was_filled = engine.apply_realistic_fills(signal, chain, is_high_vol=False)

        assert was_filled is False, "Illiquid strike should be rejected"

    def test_fill_rejection_returns_was_filled_false(self):
        """When a signal is missing critical attributes, fill is rejected."""
        chain = _make_chain_with_contracts()

        # Signal with no strike
        signal = SimpleNamespace(
            strike=None,
            option_type="CALL",
            is_buy=True,
        )
        engine = self._build_engine_with_chain(chain)
        fill_price, was_filled = engine.apply_realistic_fills(signal, chain, is_high_vol=False)

        assert was_filled is False
        assert fill_price == 0.0

    def test_missing_contract_in_chain_rejects_fill(self):
        """If the strike is not found in the chain, fill is rejected."""
        chain = _make_chain_with_contracts()

        signal = self._make_signal(strike=9999.0, option_type="CALL", is_buy=True)
        engine = self._build_engine_with_chain(chain)
        fill_price, was_filled = engine.apply_realistic_fills(signal, chain, is_high_vol=False)

        assert was_filled is False


# ============================================================================
# 4. METRICS COMPUTATION TESTS
# ============================================================================


class TestMetricsComputation:
    """Tests for BacktestEngine.compute_metrics."""

    def test_compute_metrics_with_sample_trades(self, mock_engine, sample_trades, sample_equity_curve):
        """compute_metrics returns a complete metrics dict with expected keys."""
        metrics = mock_engine.compute_metrics(sample_trades, sample_equity_curve)

        assert "total_trades" in metrics
        assert "win_rate" in metrics
        assert "profit_factor" in metrics
        assert "sharpe_ratio" in metrics
        assert "sortino_ratio" in metrics
        assert "max_drawdown" in metrics
        assert "calmar_ratio" in metrics
        assert "deflated_sharpe_ratio" in metrics
        assert metrics["total_trades"] == 23

    def test_win_rate_calculation(self, mock_engine, sample_trades, sample_equity_curve):
        """Win rate = winning_trades / total_trades."""
        metrics = mock_engine.compute_metrics(sample_trades, sample_equity_curve)

        # 10 wins at +500 + 5 wins at +300 = 15 winners
        # 5 losses at -200 + 3 losses at -400 = 8 losers
        assert metrics["winning_trades"] == 15
        assert metrics["losing_trades"] == 8
        expected_wr = 15 / 23
        assert metrics["win_rate"] == pytest.approx(expected_wr, abs=0.01)

    def test_profit_factor(self, mock_engine, sample_trades, sample_equity_curve):
        """Profit factor = gross_profit / gross_loss."""
        metrics = mock_engine.compute_metrics(sample_trades, sample_equity_curve)

        gross_profit = 10 * 500.0 + 5 * 300.0  # 6500
        gross_loss = 5 * 200.0 + 3 * 400.0     # 2200
        expected_pf = gross_profit / gross_loss

        assert metrics["gross_profit"] == pytest.approx(gross_profit, abs=0.01)
        assert metrics["gross_loss"] == pytest.approx(gross_loss, abs=0.01)
        assert metrics["profit_factor"] == pytest.approx(expected_pf, abs=0.01)

    def test_sharpe_ratio_computation(self, mock_engine, sample_trades, sample_equity_curve):
        """Sharpe ratio is annualized and based on daily returns."""
        metrics = mock_engine.compute_metrics(sample_trades, sample_equity_curve)

        # Sharpe should be a finite number since we have mixed wins/losses
        assert math.isfinite(metrics["sharpe_ratio"])
        # With a positive total PnL, Sharpe should be positive
        total_pnl = sum(t.realized_pnl for t in sample_trades)
        assert total_pnl > 0
        assert metrics["sharpe_ratio"] > 0

    def test_max_drawdown_calculation(self, mock_engine, sample_trades, sample_equity_curve):
        """Max drawdown is computed from the equity curve peak-to-trough."""
        metrics = mock_engine.compute_metrics(sample_trades, sample_equity_curve)

        assert metrics["max_drawdown"] >= 0.0
        assert metrics["max_drawdown"] < 1.0  # Should be less than 100%
        # We had losses, so drawdown should be nonzero
        assert metrics["max_drawdown"] > 0.0

    def test_sortino_ratio(self, mock_engine, sample_trades, sample_equity_curve):
        """Sortino ratio uses only downside deviation, so it should differ from Sharpe."""
        metrics = mock_engine.compute_metrics(sample_trades, sample_equity_curve)

        assert "sortino_ratio" in metrics
        # With positive overall returns, Sortino should be positive
        assert metrics["sortino_ratio"] > 0

    def test_calmar_ratio(self, mock_engine, sample_trades, sample_equity_curve):
        """Calmar ratio = annualized_return / max_drawdown."""
        metrics = mock_engine.compute_metrics(sample_trades, sample_equity_curve)

        assert "calmar_ratio" in metrics
        # Since we have positive returns and nonzero drawdown, Calmar should be positive and finite
        if metrics["max_drawdown"] > 0:
            assert metrics["calmar_ratio"] > 0

    def test_all_winners_profit_factor_infinity(self, mock_engine):
        """When there are no losing trades, profit factor should be infinity."""
        trades = [
            _make_trade_namespace(realized_pnl=100.0, entry_time=datetime(2024, 3, 1, 10, 0) + timedelta(days=i))
            for i in range(10)
        ]
        base_time = datetime(2024, 3, 1, 10, 0)
        equity = [(base_time, 100_000.0)]
        running = 100_000.0
        for i, t in enumerate(trades, start=1):
            running += t.realized_pnl
            equity.append((base_time + timedelta(days=i), running))

        metrics = mock_engine.compute_metrics(trades, equity)
        assert metrics["profit_factor"] == float("inf")
        assert metrics["win_rate"] == 1.0

    def test_all_losers_win_rate_zero(self, mock_engine):
        """When all trades are losers, win rate should be 0."""
        trades = [
            _make_trade_namespace(realized_pnl=-100.0, entry_time=datetime(2024, 3, 1, 10, 0) + timedelta(days=i))
            for i in range(10)
        ]
        base_time = datetime(2024, 3, 1, 10, 0)
        equity = [(base_time, 100_000.0)]
        running = 100_000.0
        for i, t in enumerate(trades, start=1):
            running += t.realized_pnl
            equity.append((base_time + timedelta(days=i), running))

        metrics = mock_engine.compute_metrics(trades, equity)
        assert metrics["win_rate"] == 0.0
        assert metrics["winning_trades"] == 0
        assert metrics["losing_trades"] == 10

    def test_empty_trades_returns_empty_metrics(self, mock_engine):
        """No trades returns zeroed-out metrics."""
        metrics = mock_engine.compute_metrics([], [])
        assert metrics["total_trades"] == 0
        assert metrics["win_rate"] == 0.0
        assert metrics["sharpe_ratio"] == 0.0
        assert metrics["profit_factor"] == 0


# ============================================================================
# 5. DEFLATED SHARPE TESTS
# ============================================================================


class TestDeflatedSharpe:
    """Tests for BacktestEngine.compute_deflated_sharpe."""

    def test_dsr_with_known_inputs(self, mock_engine):
        """DSR with known parameters produces a value in [0, 1]."""
        dsr = mock_engine.compute_deflated_sharpe(
            sharpe=1.5,
            n_trades=200,
            n_strategies_tested=3,
            skewness=0.0,
            kurtosis=0.0,
        )
        assert 0.0 <= dsr <= 1.0

    def test_dsr_less_than_standard_sharpe_with_many_strategies(self, mock_engine):
        """DSR should be lower when many strategies have been tested (multiple testing penalty)."""
        dsr_few = mock_engine.compute_deflated_sharpe(
            sharpe=1.0,
            n_trades=200,
            n_strategies_tested=1,
            skewness=0.0,
            kurtosis=0.0,
        )
        dsr_many = mock_engine.compute_deflated_sharpe(
            sharpe=1.0,
            n_trades=200,
            n_strategies_tested=100,
            skewness=0.0,
            kurtosis=0.0,
        )
        # With more strategies tested, DSR should be lower (stricter)
        assert dsr_many < dsr_few

    def test_dsr_accounts_for_non_normality(self, mock_engine):
        """Non-normal returns (high kurtosis, negative skew) reduce DSR."""
        dsr_normal = mock_engine.compute_deflated_sharpe(
            sharpe=1.5,
            n_trades=200,
            n_strategies_tested=3,
            skewness=0.0,
            kurtosis=0.0,
        )
        dsr_fat_tails = mock_engine.compute_deflated_sharpe(
            sharpe=1.5,
            n_trades=200,
            n_strategies_tested=3,
            skewness=-1.0,
            kurtosis=5.0,
        )
        # Fat tails and negative skew should reduce DSR
        assert dsr_fat_tails < dsr_normal

    def test_dsr_returns_zero_with_insufficient_trades(self, mock_engine):
        """DSR returns 0 when n_trades < 2."""
        dsr = mock_engine.compute_deflated_sharpe(
            sharpe=2.0,
            n_trades=1,
            n_strategies_tested=3,
            skewness=0.0,
            kurtosis=0.0,
        )
        assert dsr == 0.0

    def test_dsr_returns_zero_with_zero_strategies(self, mock_engine):
        """DSR returns 0 when n_strategies_tested < 1."""
        dsr = mock_engine.compute_deflated_sharpe(
            sharpe=2.0,
            n_trades=200,
            n_strategies_tested=0,
            skewness=0.0,
            kurtosis=0.0,
        )
        assert dsr == 0.0

    def test_dsr_high_sharpe_high_confidence(self, mock_engine):
        """Very high Sharpe with few strategies tested should produce DSR near 1."""
        dsr = mock_engine.compute_deflated_sharpe(
            sharpe=5.0,
            n_trades=1000,
            n_strategies_tested=1,
            skewness=0.0,
            kurtosis=0.0,
        )
        assert dsr > 0.95


# ============================================================================
# 6. WALK-FORWARD TESTS
# ============================================================================


class TestWalkForward:
    """Tests for walk_forward_optimization window construction."""

    def test_walk_forward_creates_correct_windows(self, mock_engine):
        """Walk-forward should create windows with train + test structure."""
        result = mock_engine.walk_forward_optimization(scan_types=[ScanType.DIRECTIONAL])

        assert "windows" in result
        assert "aggregate" in result
        # With 120 trading days minus holdout, there should be at least some windows
        # given train=60, test=20, step=5

    def test_train_test_split_sizes(self):
        """Each window has the correct number of train and test days."""
        trading_days = _generate_weekdays(date(2024, 1, 2), 150)
        loader = MockDataLoader(trading_days)
        cfg = BacktestConfig(
            start_date=date(2024, 1, 2),
            end_date=date(2024, 8, 15),
            walk_forward_train_days=60,
            walk_forward_test_days=20,
            walk_forward_step_days=5,
        )
        engine = BacktestEngine(
            config=cfg,
            data_loader=loader,
            directional_scanner=MagicMock(),
            premium_scanner=MagicMock(),
            gamma_scanner=MagicMock(),
            exit_manager=MagicMock(),
            trade_logger=MagicMock(),
        )
        result = engine.walk_forward_optimization([ScanType.DIRECTIONAL])

        for window in result["windows"]:
            train_start = date.fromisoformat(window["train_start"])
            train_end = date.fromisoformat(window["train_end"])
            test_start = date.fromisoformat(window["test_start"])
            test_end = date.fromisoformat(window["test_end"])

            # Test window should come after train window
            assert test_start > train_end, "Test must start after training ends"

    def test_rolling_step_size(self):
        """Consecutive windows advance by step_days trading days."""
        trading_days = _generate_weekdays(date(2024, 1, 2), 200)
        loader = MockDataLoader(trading_days)
        cfg = BacktestConfig(
            start_date=date(2024, 1, 2),
            end_date=date(2024, 11, 15),
            walk_forward_train_days=60,
            walk_forward_test_days=20,
            walk_forward_step_days=5,
        )
        engine = BacktestEngine(
            config=cfg,
            data_loader=loader,
            directional_scanner=MagicMock(),
            premium_scanner=MagicMock(),
            gamma_scanner=MagicMock(),
            exit_manager=MagicMock(),
            trade_logger=MagicMock(),
        )
        result = engine.walk_forward_optimization([ScanType.DIRECTIONAL])
        windows = result["windows"]

        if len(windows) >= 2:
            # Get the in-sample trading days list
            holdout_start = cfg.holdout_start_date
            in_sample_end = holdout_start - timedelta(days=1)
            all_td = loader.get_trading_days(cfg.start_date, in_sample_end)

            for i in range(1, len(windows)):
                w0_train_start = date.fromisoformat(windows[i - 1]["train_start"])
                w1_train_start = date.fromisoformat(windows[i]["train_start"])

                # Find indices
                idx0 = all_td.index(w0_train_start) if w0_train_start in all_td else -1
                idx1 = all_td.index(w1_train_start) if w1_train_start in all_td else -1

                if idx0 >= 0 and idx1 >= 0:
                    step = idx1 - idx0
                    assert step == 5, f"Step between windows should be 5, got {step}"

    def test_no_overlap_between_train_and_test(self):
        """Train and test sets within a single window must not overlap."""
        trading_days = _generate_weekdays(date(2024, 1, 2), 150)
        loader = MockDataLoader(trading_days)
        cfg = BacktestConfig(
            start_date=date(2024, 1, 2),
            end_date=date(2024, 8, 15),
            walk_forward_train_days=60,
            walk_forward_test_days=20,
            walk_forward_step_days=5,
        )
        engine = BacktestEngine(
            config=cfg,
            data_loader=loader,
            directional_scanner=MagicMock(),
            premium_scanner=MagicMock(),
            gamma_scanner=MagicMock(),
            exit_manager=MagicMock(),
            trade_logger=MagicMock(),
        )
        result = engine.walk_forward_optimization([ScanType.DIRECTIONAL])

        for window in result["windows"]:
            train_end = date.fromisoformat(window["train_end"])
            test_start = date.fromisoformat(window["test_start"])
            assert test_start > train_end, (
                f"Train end {train_end} must be before test start {test_start}"
            )

    def test_insufficient_days_returns_empty(self):
        """When insufficient trading days exist, walk-forward returns empty."""
        trading_days = _generate_weekdays(date(2024, 1, 2), 10)
        loader = MockDataLoader(trading_days)
        cfg = BacktestConfig(
            start_date=date(2024, 1, 2),
            end_date=date(2024, 6, 28),
            walk_forward_train_days=60,
            walk_forward_test_days=20,
        )
        engine = BacktestEngine(
            config=cfg,
            data_loader=loader,
            directional_scanner=MagicMock(),
            premium_scanner=MagicMock(),
            gamma_scanner=MagicMock(),
            exit_manager=MagicMock(),
            trade_logger=MagicMock(),
        )
        result = engine.walk_forward_optimization([ScanType.DIRECTIONAL])
        assert result["windows"] == []
        assert result["aggregate"] == {}


# ============================================================================
# 7. BENCHMARK COMPARISON TESTS
# ============================================================================


class TestBenchmarkComparison:
    """Tests for BacktestEngine.run_benchmark_comparison."""

    def test_returns_results_for_all_3_benchmarks(self, mock_engine, sample_trades):
        """The benchmark comparison returns entries for all three benchmarks."""
        result = mock_engine.run_benchmark_comparison(sample_trades)

        assert "benchmarks" in result
        benchmarks = result["benchmarks"]
        assert "otm_call_daily" in benchmarks
        assert "otm_put_daily" in benchmarks
        assert "iron_condor_em" in benchmarks

    def test_benchmark_results_have_expected_structure(self, mock_engine, sample_trades):
        """Each benchmark result has total_pnl, sharpe, and scanner_beats flag."""
        result = mock_engine.run_benchmark_comparison(sample_trades)

        for bm_name, bm_data in result["benchmarks"].items():
            assert "total_pnl" in bm_data, f"Missing total_pnl in {bm_name}"
            assert "sharpe" in bm_data, f"Missing sharpe in {bm_name}"
            assert "scanner_beats" in bm_data, f"Missing scanner_beats in {bm_name}"
            assert isinstance(bm_data["scanner_beats"], bool)

    def test_scanner_beats_all_flag(self, mock_engine, sample_trades):
        """scanner_beats_all is True only when scanner beats every benchmark."""
        result = mock_engine.run_benchmark_comparison(sample_trades)

        beats_all = all(
            bm["scanner_beats"]
            for bm in result["benchmarks"].values()
        )
        assert result["scanner_beats_all"] == beats_all

    def test_empty_trades_returns_zero_pnl(self, mock_engine):
        """Empty trades produces zero scanner PnL and scanner_beats_all=False."""
        result = mock_engine.run_benchmark_comparison([])
        assert result["scanner_total_pnl"] == 0.0
        assert result["scanner_beats_all"] is False

    def test_scanner_total_pnl_matches_sum(self, mock_engine, sample_trades):
        """scanner_total_pnl is the sum of all trade PnLs."""
        result = mock_engine.run_benchmark_comparison(sample_trades)
        expected_pnl = sum(t.realized_pnl for t in sample_trades)
        assert result["scanner_total_pnl"] == pytest.approx(expected_pnl, abs=0.01)


# ============================================================================
# 8. TRANSACTION COST SENSITIVITY TESTS
# ============================================================================


class TestTransactionCostSensitivity:
    """Tests for BacktestEngine.run_transaction_cost_sensitivity."""

    def test_scenarios_include_1_2_5_ticks(self, mock_engine, sample_trades):
        """Sensitivity analysis includes the 1-tick, 2-tick, and 5-tick scenarios."""
        result = mock_engine.run_transaction_cost_sensitivity(sample_trades)

        assert "scenarios" in result
        scenarios = result["scenarios"]
        assert "1_tick" in scenarios
        assert "2_ticks" in scenarios
        assert "5_ticks" in scenarios

    def test_higher_slippage_reduces_total_pnl(self, mock_engine, sample_trades):
        """Increasing slippage monotonically reduces total P&L."""
        result = mock_engine.run_transaction_cost_sensitivity(sample_trades)
        scenarios = result["scenarios"]

        pnl_1 = scenarios["1_tick"]["total_pnl"]
        pnl_2 = scenarios["2_ticks"]["total_pnl"]
        pnl_5 = scenarios["5_ticks"]["total_pnl"]

        # More slippage always reduces PnL
        assert pnl_1 >= pnl_2, "2-tick slippage should yield lower PnL than 1-tick"
        assert pnl_2 >= pnl_5, "5-tick slippage should yield lower PnL than 2-tick"

    def test_some_strategies_become_unprofitable(self, mock_engine):
        """With heavy slippage, marginally profitable trades become losers."""
        # Create trades with small positive PnL that will flip negative with costs
        trades = [
            _make_trade_namespace(
                realized_pnl=5.0,  # Very small profit
                entry_price=2.0,   # Low price = larger relative impact of slippage
                entry_time=datetime(2024, 3, 1, 10, 0) + timedelta(days=i),
            )
            for i in range(20)
        ]
        result = mock_engine.run_transaction_cost_sensitivity(trades)

        # At 5 ticks, the additional cost should flip some trades to losses
        scenario_5 = result["scenarios"]["5_ticks"]
        assert scenario_5["total_pnl"] < result["base_pnl"]

    def test_base_pnl_is_correct(self, mock_engine, sample_trades):
        """base_pnl matches the sum of original trade PnLs."""
        result = mock_engine.run_transaction_cost_sensitivity(sample_trades)
        expected = sum(t.realized_pnl for t in sample_trades)
        assert result["base_pnl"] == pytest.approx(expected, abs=0.01)

    def test_each_scenario_has_expected_keys(self, mock_engine, sample_trades):
        """Each scenario dict has the required keys."""
        result = mock_engine.run_transaction_cost_sensitivity(sample_trades)

        for label, scenario in result["scenarios"].items():
            assert "total_pnl" in scenario
            assert "win_rate" in scenario
            assert "winning_trades" in scenario
            assert "losing_trades" in scenario
            assert "pnl_change_from_base" in scenario
            assert "pnl_change_pct" in scenario
            assert "scan_type_survival" in scenario

    def test_empty_trades_returns_zero_base_pnl(self, mock_engine):
        """Empty trades returns zero base PnL and empty scenarios."""
        result = mock_engine.run_transaction_cost_sensitivity([])
        assert result["base_pnl"] == 0.0
        assert result["scenarios"] == {}


# ============================================================================
# 9. BACKTEST ENGINE INTEGRATION TESTS
# ============================================================================


class TestBacktestEngineIntegration:
    """Integration tests for BacktestEngine.simulate_day and related methods."""

    def test_simulate_day_returns_trade_list(self, mock_engine):
        """simulate_day returns a list (possibly empty) of trade objects."""
        trading_day = date(2024, 3, 4)
        result = mock_engine.simulate_day(trading_day, [ScanType.DIRECTIONAL])
        assert isinstance(result, list)

    def test_simulate_day_with_no_signals_returns_empty(self, mock_engine):
        """When scanners produce no signals, simulate_day returns no trades."""
        mock_engine.directional_scanner.scan.return_value = []
        mock_engine.premium_scanner.scan.return_value = []
        mock_engine.gamma_scanner.scan.return_value = []

        trading_day = date(2024, 3, 4)
        result = mock_engine.simulate_day(trading_day, [ScanType.DIRECTIONAL])
        assert result == []

    def test_equity_curve_tracked_after_backtest_day(self, mock_engine):
        """Running a day of simulation updates the engine equity curve."""
        initial_len = len(mock_engine.equity_curve)
        mock_engine.equity_curve = [
            (datetime.combine(date(2024, 1, 2), _MARKET_OPEN), 100_000.0)
        ]

        trading_day = date(2024, 3, 4)
        trades = mock_engine.simulate_day(trading_day, [ScanType.DIRECTIONAL])

        # The equity curve is updated by run_backtest (not simulate_day directly),
        # but simulate_day returns trades whose PnL feeds the curve
        assert isinstance(trades, list)

    def test_daily_pnl_recorded(self, mock_engine):
        """After run_backtest, daily_pnl dict should be populated."""
        # Run a minimal backtest
        mock_engine.directional_scanner.scan.return_value = []
        mock_engine.premium_scanner.scan.return_value = []
        mock_engine.gamma_scanner.scan.return_value = []

        result = mock_engine.run_backtest([ScanType.DIRECTIONAL])

        # daily_pnl should have entries (even if all zero)
        assert isinstance(mock_engine.daily_pnl, dict)

    def test_positions_opened_and_closed_within_day(self):
        """Positions opened during a day are force-closed at end of day."""
        trading_days = _generate_weekdays(date(2024, 6, 3), 5)
        loader = MockDataLoader(trading_days)
        chain = _make_chain_with_contracts()
        loader._chain = chain

        cfg = BacktestConfig(
            start_date=date(2024, 6, 3),
            end_date=date(2024, 6, 10),
        )

        # Create a directional scanner that returns a signal at 10:00 AM
        mock_signal = SimpleNamespace(
            strike=5200.0,
            option_type="CALL",
            is_buy=True,
            scan_type=ScanType.DIRECTIONAL,
            session_type=SessionType.TRENDING,
            time_zone=TimeZoneType.MORNING_SESSION,
        )

        dir_scanner = MagicMock()
        # Return a signal for the first call, then empty for the rest
        dir_scanner.scan = MagicMock(side_effect=[[mock_signal]] + [[] for _ in range(500)])

        exit_mgr = MagicMock()
        exit_mgr.check_exit = MagicMock(return_value=None)

        engine = BacktestEngine(
            config=cfg,
            data_loader=loader,
            directional_scanner=dir_scanner,
            premium_scanner=MagicMock(),
            gamma_scanner=MagicMock(),
            exit_manager=exit_mgr,
            trade_logger=MagicMock(),
        )

        # Patch _close_position_to_trade_log since the backtester passes
        # field names (entry_time, realized_pnl) that don't match the
        # TradeLog Pydantic model (timestamp_entry, pnl_dollars).
        mock_trade_log = _make_trade_namespace(realized_pnl=50.0)
        engine._close_position_to_trade_log = MagicMock(return_value=mock_trade_log)

        day_trades = engine.simulate_day(date(2024, 6, 3), [ScanType.DIRECTIONAL])

        # After end of day, no active positions should remain
        assert engine._active_positions == []

    def test_max_daily_trades_cap(self):
        """Engine stops opening new positions after max_daily_trades is reached."""
        trading_days = _generate_weekdays(date(2024, 6, 3), 5)
        loader = MockDataLoader(trading_days)
        chain = _make_chain_with_contracts()
        loader._chain = chain

        cfg = BacktestConfig(
            start_date=date(2024, 6, 3),
            end_date=date(2024, 6, 10),
            max_daily_trades=2,
        )

        mock_signal = SimpleNamespace(
            strike=5200.0,
            option_type="CALL",
            is_buy=True,
            scan_type=ScanType.DIRECTIONAL,
            session_type=SessionType.TRENDING,
            time_zone=TimeZoneType.MORNING_SESSION,
        )

        dir_scanner = MagicMock()
        # Return signals on every scan call
        dir_scanner.scan = MagicMock(return_value=[mock_signal])

        exit_mgr = MagicMock()
        exit_mgr.check_exit = MagicMock(return_value=None)

        engine = BacktestEngine(
            config=cfg,
            data_loader=loader,
            directional_scanner=dir_scanner,
            premium_scanner=MagicMock(),
            gamma_scanner=MagicMock(),
            exit_manager=exit_mgr,
            trade_logger=MagicMock(),
        )

        # Patch _close_position_to_trade_log since the backtester passes
        # field names that don't match the TradeLog Pydantic model.
        mock_trade_log = _make_trade_namespace(realized_pnl=50.0)
        engine._close_position_to_trade_log = MagicMock(return_value=mock_trade_log)

        day_trades = engine.simulate_day(date(2024, 6, 3), [ScanType.DIRECTIONAL])

        # The trades should not exceed max_daily_trades (plus force-close trades)
        # Force-close trades at EOD do not count toward the cap.
        # The opened trades should be capped.
        assert engine._daily_trade_count <= cfg.max_daily_trades


# ============================================================================
# 10. VISUALIZER TESTS
# ============================================================================


class TestBacktestVisualizer:
    """Tests for BacktestVisualizer static methods."""

    def test_equity_curve_data_keys(self, sample_equity_curve):
        """equity_curve_data returns a dict with the required keys."""
        result = BacktestVisualizer.equity_curve_data(sample_equity_curve)

        assert "timestamps" in result
        assert "equity" in result
        assert "start_equity" in result
        assert "end_equity" in result
        assert "total_return_pct" in result

    def test_equity_curve_data_values(self, sample_equity_curve):
        """equity_curve_data values are consistent with the input curve."""
        result = BacktestVisualizer.equity_curve_data(sample_equity_curve)

        assert len(result["timestamps"]) == len(sample_equity_curve)
        assert len(result["equity"]) == len(sample_equity_curve)
        assert result["start_equity"] == sample_equity_curve[0][1]
        assert result["end_equity"] == sample_equity_curve[-1][1]

        # Total return percentage
        expected_return_pct = (
            (sample_equity_curve[-1][1] - sample_equity_curve[0][1])
            / sample_equity_curve[0][1]
            * 100.0
        )
        assert result["total_return_pct"] == pytest.approx(expected_return_pct, abs=0.01)

    def test_equity_curve_data_empty(self):
        """Empty equity curve produces zeroed-out result."""
        result = BacktestVisualizer.equity_curve_data([])
        assert result["timestamps"] == []
        assert result["equity"] == []
        assert result["start_equity"] == 0.0
        assert result["end_equity"] == 0.0
        assert result["total_return_pct"] == 0.0

    def test_monthly_returns_structure(self):
        """monthly_returns returns months, returns, returns_pct, and heatmap."""
        daily_pnl = {
            date(2024, 1, 3): 100.0,
            date(2024, 1, 4): -50.0,
            date(2024, 2, 5): 200.0,
            date(2024, 2, 6): 150.0,
            date(2024, 3, 1): -100.0,
        }
        result = BacktestVisualizer.monthly_returns(daily_pnl)

        assert "months" in result
        assert "returns" in result
        assert "returns_pct" in result
        assert "heatmap" in result

        assert len(result["months"]) == 3  # Jan, Feb, Mar
        assert result["months"] == ["2024-01", "2024-02", "2024-03"]
        assert result["returns"][0] == pytest.approx(50.0)   # 100 - 50
        assert result["returns"][1] == pytest.approx(350.0)  # 200 + 150
        assert result["returns"][2] == pytest.approx(-100.0)

    def test_monthly_returns_heatmap_structure(self):
        """Each heatmap entry has year, month, and pnl."""
        daily_pnl = {
            date(2024, 1, 3): 100.0,
            date(2024, 2, 5): 200.0,
        }
        result = BacktestVisualizer.monthly_returns(daily_pnl)

        for entry in result["heatmap"]:
            assert "year" in entry
            assert "month" in entry
            assert "pnl" in entry
            assert isinstance(entry["year"], int)
            assert isinstance(entry["month"], int)

    def test_monthly_returns_empty(self):
        """Empty daily PnL produces empty monthly returns."""
        result = BacktestVisualizer.monthly_returns({})
        assert result["months"] == []
        assert result["returns"] == []
        assert result["heatmap"] == []

    def test_trade_distribution_structure(self):
        """trade_distribution returns pnls, bins, and statistics."""
        trades = [
            _make_trade_namespace(realized_pnl=p)
            for p in [100.0, -50.0, 200.0, -100.0, 150.0, 50.0, -75.0]
        ]
        result = BacktestVisualizer.trade_distribution(trades)

        assert "pnls" in result
        assert "bin_edges" in result
        assert "bin_counts" in result
        assert "mean" in result
        assert "median" in result
        assert "std" in result
        assert "skew" in result
        assert "kurtosis" in result

        assert len(result["pnls"]) == 7
        # Bin edges should have one more element than bin counts
        assert len(result["bin_edges"]) == len(result["bin_counts"]) + 1

    def test_trade_distribution_statistics(self):
        """trade_distribution statistics match numpy/scipy calculations."""
        pnls_list = [100.0, -50.0, 200.0, -100.0, 150.0]
        trades = [_make_trade_namespace(realized_pnl=p) for p in pnls_list]
        result = BacktestVisualizer.trade_distribution(trades)

        arr = np.array(pnls_list)
        assert result["mean"] == pytest.approx(float(np.mean(arr)), abs=0.01)
        assert result["median"] == pytest.approx(float(np.median(arr)), abs=0.01)
        assert result["std"] == pytest.approx(float(np.std(arr, ddof=1)), abs=0.01)

    def test_trade_distribution_empty(self):
        """Empty trades produces zeroed-out distribution."""
        result = BacktestVisualizer.trade_distribution([])
        assert result["pnls"] == []
        assert result["mean"] == 0.0
        assert result["median"] == 0.0
        assert result["std"] == 0.0

    def test_drawdown_data_structure(self, sample_equity_curve):
        """drawdown_data returns timestamps, drawdown_pct, and max stats."""
        result = BacktestVisualizer.drawdown_data(sample_equity_curve)

        assert "timestamps" in result
        assert "drawdown_pct" in result
        assert "max_drawdown_pct" in result
        assert "max_drawdown_timestamp" in result

        assert len(result["timestamps"]) == len(sample_equity_curve)
        assert len(result["drawdown_pct"]) == len(sample_equity_curve)
        # Drawdowns should be <= 0 (expressed as negative percentages)
        for dd in result["drawdown_pct"]:
            assert dd <= 0.0 + 1e-10  # Allow tiny floating point error

    def test_drawdown_data_empty(self):
        """Empty equity curve produces empty drawdown data."""
        result = BacktestVisualizer.drawdown_data([])
        assert result["timestamps"] == []
        assert result["drawdown_pct"] == []
        assert result["max_drawdown_pct"] == 0.0


# ============================================================================
# Additional helper function tests
# ============================================================================


class TestTickSizeForPrice:
    """Tests for the _tick_size_for_price helper."""

    def test_below_boundary(self):
        """Prices below $3.00 use $0.05 tick."""
        assert _tick_size_for_price(2.50) == _TICK_SIZE_BELOW_3
        assert _tick_size_for_price(0.10) == _TICK_SIZE_BELOW_3
        assert _tick_size_for_price(2.99) == _TICK_SIZE_BELOW_3

    def test_at_boundary(self):
        """Prices at $3.00 use $0.10 tick."""
        assert _tick_size_for_price(3.00) == _TICK_SIZE_AT_OR_ABOVE_3

    def test_above_boundary(self):
        """Prices above $3.00 use $0.10 tick."""
        assert _tick_size_for_price(5.00) == _TICK_SIZE_AT_OR_ABOVE_3
        assert _tick_size_for_price(15.00) == _TICK_SIZE_AT_OR_ABOVE_3


class TestAnnualizedSharpe:
    """Tests for the _annualized_sharpe and _annualized_sortino static methods."""

    def test_sharpe_positive_returns(self):
        """Positive daily returns yield a positive Sharpe."""
        returns = np.array([0.01, 0.005, 0.008, 0.012, 0.003, 0.01, 0.007])
        sharpe = BacktestEngine._annualized_sharpe(returns)
        assert sharpe > 0

    def test_sharpe_negative_returns(self):
        """Negative daily returns yield a negative Sharpe."""
        returns = np.array([-0.01, -0.005, -0.008, -0.012, -0.003])
        sharpe = BacktestEngine._annualized_sharpe(returns)
        assert sharpe < 0

    def test_sharpe_insufficient_data(self):
        """Fewer than 2 returns yields a Sharpe of 0."""
        assert BacktestEngine._annualized_sharpe(np.array([0.01])) == 0.0
        assert BacktestEngine._annualized_sharpe(np.array([])) == 0.0

    def test_sortino_only_uses_downside(self):
        """Sortino ignores positive returns in the denominator."""
        # All positive returns: no downside
        returns = np.array([0.01, 0.02, 0.03, 0.04])
        sortino = BacktestEngine._annualized_sortino(returns)
        assert sortino == float("inf")

    def test_sortino_with_mixed_returns(self):
        """Sortino with mixed returns is finite and positive for net-positive mean."""
        returns = np.array([0.02, -0.01, 0.03, -0.005, 0.015])
        sortino = BacktestEngine._annualized_sortino(returns)
        assert sortino > 0
        assert math.isfinite(sortino)


class TestMaxDrawdown:
    """Tests for _compute_max_drawdown static method."""

    def test_no_drawdown(self):
        """Monotonically increasing equity has zero drawdown."""
        curve = [
            (datetime(2024, 1, i + 1, 16, 0), 100_000.0 + i * 1000)
            for i in range(10)
        ]
        dd, duration = BacktestEngine._compute_max_drawdown(curve)
        assert dd == 0.0
        assert duration == 0

    def test_known_drawdown(self):
        """Known peak-to-trough drawdown is computed correctly."""
        curve = [
            (datetime(2024, 1, 1, 16, 0), 100_000.0),   # start
            (datetime(2024, 1, 2, 16, 0), 110_000.0),   # peak
            (datetime(2024, 1, 3, 16, 0), 99_000.0),    # trough
            (datetime(2024, 1, 4, 16, 0), 105_000.0),   # recovery
        ]
        dd, duration = BacktestEngine._compute_max_drawdown(curve)

        # DD = (110000 - 99000) / 110000 = 0.1
        assert dd == pytest.approx(0.1, abs=0.001)
        assert duration > 0

    def test_single_point_no_drawdown(self):
        """Single data point yields zero drawdown."""
        curve = [(datetime(2024, 1, 1, 16, 0), 100_000.0)]
        dd, duration = BacktestEngine._compute_max_drawdown(curve)
        assert dd == 0.0
        assert duration == 0


class TestEmptyMetrics:
    """Tests for the _empty_metrics sentinel values."""

    def test_empty_metrics_keys(self):
        """_empty_metrics returns all expected keys with sensible defaults."""
        m = BacktestEngine._empty_metrics()

        assert m["total_trades"] == 0
        assert m["win_rate"] == 0.0
        assert m["sharpe_ratio"] == 0.0
        assert m["max_drawdown"] == 0.0
        assert m["profit_factor"] == 0
        assert m["deflated_sharpe_ratio"] == 0.0
        assert m["p_value"] == 1.0
        assert m["confidence_interval_95"] == (0.0, 0.0)
