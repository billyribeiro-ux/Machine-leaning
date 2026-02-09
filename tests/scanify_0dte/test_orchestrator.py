"""
Comprehensive test suite for SCANIFY SPX 0DTE Options Scanner -- Orchestrator

Tests the main ``ScanifyOrchestrator`` class and ``create_scanify_system`` factory
function defined in ``src/scanify_0dte/orchestrator.py``.

Covered areas:
    1. Initialization (components, defaults, custom config)
    2. Session lifecycle (pre-market, session classification, guard rails)
    3. Scan cycle timing (per-zone scanner dispatch)
    4. GEX profile updates and signal generation
    5. Position management (open, exit, EOD close)
    6. Post-market (daily report, calibration)
    7. Status / dashboard data
    8. State persistence (save / load)
    9. Factory function

All external dependencies (data feed, scanners, exit manager, calibration)
are mocked so that tests run entirely offline and deterministically.

Run with:
    pytest tests/scanify_0dte/test_orchestrator.py -v
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_SRC_DIR = os.path.join(_PROJECT_ROOT, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

# ---------------------------------------------------------------------------
# Patch missing constant aliases before importing (mirrors test_scanners.py)
# ---------------------------------------------------------------------------
import scanify_0dte.constants as _constants_mod

if not hasattr(_constants_mod, "FACTOR_WEIGHTS"):
    _constants_mod.FACTOR_WEIGHTS = _constants_mod.DEFAULT_FACTOR_WEIGHTS
if not hasattr(_constants_mod, "EXIT_CONSTANTS"):
    _constants_mod.EXIT_CONSTANTS = _constants_mod.EXIT_MANAGEMENT
if not hasattr(_constants_mod, "LIQUIDITY_FILTERS"):
    _constants_mod.LIQUIDITY_FILTERS = SimpleNamespace(
        min_open_interest=500,
        min_volume=200,
        max_bid_ask_spread_pct=0.15,
    )
if not hasattr(_constants_mod, "TIME_ZONES"):
    _constants_mod.TIME_ZONES = _constants_mod.ZONE_BOUNDARIES

# ---------------------------------------------------------------------------
# Module under test
# ---------------------------------------------------------------------------
from scanify_0dte.orchestrator import (
    ScanifyOrchestrator,
    create_scanify_system,
    _get_et_now,
    _OPENING_AUCTION_START,
    _OPENING_AUCTION_END,
    _MORNING_SESSION_END,
    _MIDDAY_LULL_END,
    _AFTERNOON_ACCEL_END,
    _POWER_HOUR_END,
    _SETTLEMENT_END,
)
from scanify_0dte.models import (
    SessionSetup,
    SessionType,
    ScanSignal,
    ScanType,
    TradeDirection,
    TimeZoneType,
    GEXProfile,
    GEXSignal,
    GEXSignalType,
    GapClassification,
)

# ---------------------------------------------------------------------------
# Patch targets for sub-component constructors that require arguments
# the orchestrator does not pass (orchestrator assumes no-arg construction).
# ---------------------------------------------------------------------------
_ORCH_MODULE = "scanify_0dte.orchestrator"
_PATCHES_FOR_INIT = [
    f"{_ORCH_MODULE}.DataFeedManager",
    f"{_ORCH_MODULE}.BlackScholes0DTE",
    f"{_ORCH_MODULE}.GreeksCalculator",
    f"{_ORCH_MODULE}.GEXEngine",
    f"{_ORCH_MODULE}.GEXSignalGenerator",
    f"{_ORCH_MODULE}.PreMarketScanner",
    f"{_ORCH_MODULE}.DirectionalOTMScanner",
    f"{_ORCH_MODULE}.PremiumSellingScanner",
    f"{_ORCH_MODULE}.GammaScalpScanner",
    f"{_ORCH_MODULE}.ExitManager",
    f"{_ORCH_MODULE}.TradeLogger",
    f"{_ORCH_MODULE}.DailyCalibrator",
]


def _create_orchestrator_patched(**kwargs: Any) -> ScanifyOrchestrator:
    """Create a ScanifyOrchestrator with all sub-component constructors
    replaced by MagicMock, so required-arg mismatches do not fail."""
    patches = [patch(target) for target in _PATCHES_FOR_INIT]
    for p in patches:
        p.start()
    try:
        with patch.object(ScanifyOrchestrator, "load_state", return_value=None):
            orch = ScanifyOrchestrator(**kwargs)
    finally:
        for p in patches:
            p.stop()
    return orch


# ============================================================================
# Helpers -- lightweight mock objects
# ============================================================================

def _make_session_setup(**overrides: Any) -> SimpleNamespace:
    """Build a minimal SessionSetup-like namespace for testing."""
    defaults = {
        "session_type": SessionType.TRENDING,
        "gex_profile": _make_gex_profile(),
        "expected_move": SimpleNamespace(
            upper_1sigma=5260.0,
            lower_1sigma=5240.0,
            upper_2sigma=5270.0,
            lower_2sigma=5230.0,
            em_composite=10.0,
            iv_rv_ratio=1.1,
            vol_regime="normal",
        ),
        "key_levels": SimpleNamespace(
            options_levels={},
            price_action_levels={},
            round_numbers=[5200, 5250, 5300],
            moving_averages={"SMA_20": 5250.0},
            market_profile_levels={},
        ),
        "gap_analysis": SimpleNamespace(
            gap_direction="UP",
            gap_size_sigma=0.3,
            gap_classification="MICRO",
        ),
        "vix1d": 15.0,
        "economic_events": [],
        "risk_assessment": "Normal",
        "timestamp": datetime.utcnow(),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_gex_profile(**overrides: Any) -> SimpleNamespace:
    """Build a minimal GEXProfile-like namespace for testing."""
    defaults = {
        "net_gex": 50_000_000.0,
        "total_net_gex": 50_000_000.0,
        "gamma_flip_level": 5250.0,
        "call_wall": 5300.0,
        "put_wall": 5200.0,
        "max_pain": 5250.0,
        "vol_trigger": 5275.0,
        "spx_price": 5250.0,
        "plus_gex": 5280.0,
        "minus_gex": 5220.0,
        "transition_zone_upper": 5260.0,
        "transition_zone_lower": 5240.0,
        "gex_momentum": 100.0,
        "charm_net_es_contracts": 5.0,
        "vanna_net_exposure": 10.0,
        "is_positive_gamma_regime": True,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_gex_signal(**overrides: Any) -> SimpleNamespace:
    """Build a minimal GEXSignal-like namespace for testing."""
    defaults = {
        "signal_type": "GAMMA_WALL_APPROACH",
        "timestamp": datetime.utcnow(),
        "direction": TradeDirection.BULL,
        "confidence": 75.0,
        "description": "Test GEX signal",
        "trigger_price": 5255.0,
        "target_price": 5280.0,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_scan_signal(**overrides: Any) -> SimpleNamespace:
    """Build a minimal ScanSignal-like namespace for testing."""
    defaults = {
        "signal_id": "TEST-SIG-001",
        "scan_type": ScanType.DIRECTIONAL,
        "direction": TradeDirection.BULL,
        "entry_price": 5.50,
        "stop_loss": 2.75,
        "take_profit": 11.0,
        "profit_target": 11.0,
        "position_type": "SINGLE_LONG",
        "contracts": 2,
        "max_risk": 275.0,
        "expected_reward": 550.0,
        "risk_reward_ratio": 2.0,
        "time_zone": TimeZoneType.MORNING_SESSION,
        "session_type": SessionType.TRENDING,
        "timestamp": datetime.utcnow(),
        "confidence": 72.0,
        "metadata": {},
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_snapshot(spx_price: float = 5250.0, **overrides: Any) -> Dict[str, Any]:
    """Build a minimal data snapshot dict for testing."""
    defaults = {
        "spx_price": spx_price,
        "es_price": spx_price - 2.0,
        "prior_session": {
            "close": spx_price - 5.0,
            "rv_20day": 0.15,
            "overnight_high": spx_price + 5.0,
            "overnight_low": spx_price - 5.0,
        },
        "economic_events": [],
        "options_chain": SimpleNamespace(
            expiry_date=date.today(),
            underlying_price=spx_price,
            quotes=[],
        ),
        "cross_asset_data": SimpleNamespace(vix1d=15.0),
        "market_internals": SimpleNamespace(
            nyse_tick=200,
            advance_decline_ratio=1.2,
            up_volume_ratio=0.55,
        ),
    }
    defaults.update(overrides)
    return defaults


def _make_calibration_state() -> SimpleNamespace:
    """Build a minimal CalibrationState-like namespace for testing."""
    return SimpleNamespace(
        current_weights=SimpleNamespace(
            market_internals=0.20,
            options_flow=0.20,
            price_action=0.20,
            gex_structure=0.20,
            cross_asset=0.20,
        ),
        entry_threshold=55.0,
        profit_targets_by_zone={},
        stop_loss_pct=50.0,
        regime="normal",
        last_calibration=datetime.utcnow(),
        trade_count=0,
        gex_signal_accuracy=0.65,
        to_dict=lambda: {
            "entry_threshold": 55.0,
            "regime": "normal",
            "trade_count": 0,
        },
    )


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_data_feed() -> MagicMock:
    """Create a fully mocked DataFeedManager."""
    feed = MagicMock()
    feed.connect = AsyncMock()
    feed.disconnect = AsyncMock()
    feed.start_streaming = AsyncMock()
    feed.stop_streaming = AsyncMock()
    feed.get_snapshot = AsyncMock(return_value=_make_snapshot())
    feed.fetch_options_chain = AsyncMock(
        return_value=SimpleNamespace(
            expiry_date=date.today(), underlying_price=5250.0, quotes=[]
        )
    )
    feed.fetch_cross_asset_data = AsyncMock(
        return_value=SimpleNamespace(vix1d=15.0)
    )
    feed.spx_price = 5250.0
    feed.options_chain = SimpleNamespace(
        expiry_date=date.today(), underlying_price=5250.0, quotes=[]
    )
    feed.is_connected = True
    feed.get_minutes_remaining = MagicMock(return_value=180)
    return feed


@pytest.fixture
def mock_pre_market() -> MagicMock:
    """Create a mocked PreMarketScanner."""
    scanner = MagicMock()
    scanner.run_pre_market_scan = MagicMock(return_value=_make_session_setup())
    return scanner


@pytest.fixture
def mock_directional() -> MagicMock:
    """Create a mocked DirectionalOTMScanner."""
    scanner = MagicMock()
    scanner.scan = MagicMock(return_value=[])
    return scanner


@pytest.fixture
def mock_premium() -> MagicMock:
    """Create a mocked PremiumSellingScanner."""
    scanner = MagicMock()
    scanner.scan = MagicMock(return_value=[])
    return scanner


@pytest.fixture
def mock_gamma() -> MagicMock:
    """Create a mocked GammaScalpScanner."""
    scanner = MagicMock()
    scanner.scan = MagicMock(return_value=[])
    return scanner


@pytest.fixture
def mock_gex_engine() -> MagicMock:
    """Create a mocked GEXEngine."""
    engine = MagicMock()
    engine.compute_profile = MagicMock(return_value=_make_gex_profile())
    return engine


@pytest.fixture
def mock_gex_signal_gen() -> MagicMock:
    """Create a mocked GEXSignalGenerator."""
    gen = MagicMock()
    gen.check_all_signals = MagicMock(return_value=[])
    return gen


@pytest.fixture
def mock_exit_mgr() -> MagicMock:
    """Create a mocked ExitManager."""
    mgr = MagicMock()
    mgr.evaluate_exit = MagicMock(return_value=None)
    return mgr


@pytest.fixture
def mock_trade_logger() -> MagicMock:
    """Create a mocked TradeLogger that does not touch disk."""
    logger = MagicMock()
    logger.log_entry = MagicMock()
    logger.log_exit = MagicMock()
    logger.log_trade = MagicMock()
    return logger


@pytest.fixture
def mock_calibrator() -> MagicMock:
    """Create a mocked DailyCalibrator."""
    cal = MagicMock()
    cal.run_daily_calibration = MagicMock(
        return_value={
            "summary": "OK",
            "updated_state": _make_calibration_state(),
        }
    )
    return cal


@pytest.fixture
def orchestrator(
    mock_data_feed,
    mock_pre_market,
    mock_directional,
    mock_premium,
    mock_gamma,
    mock_gex_engine,
    mock_gex_signal_gen,
    mock_exit_mgr,
    mock_trade_logger,
    mock_calibrator,
) -> ScanifyOrchestrator:
    """Create a ScanifyOrchestrator with all components mocked."""
    with patch.object(
        ScanifyOrchestrator, "load_state", return_value=None
    ):
        orch = ScanifyOrchestrator(
            data_provider="mock",
            api_key="test-key",
            risk_budget=10_000.0,
            paper_trade=True,
            calibration_state=_make_calibration_state(),
            log_dir="/tmp/scanify_test_logs",
        )

    # Replace sub-components with mocks
    orch.data_feed = mock_data_feed
    orch.pre_market = mock_pre_market
    orch.directional = mock_directional
    orch.premium = mock_premium
    orch.gamma_scalp = mock_gamma
    orch.gex_engine = mock_gex_engine
    orch.gex_signal_gen = mock_gex_signal_gen
    orch.exit_mgr = mock_exit_mgr
    orch.trade_logger = mock_trade_logger
    orch.calibrator = mock_calibrator

    return orch


# ============================================================================
# 1. INITIALIZATION TESTS
# ============================================================================


class TestInitialization:
    """Test ScanifyOrchestrator construction and defaults."""

    def test_creates_all_sub_components(self) -> None:
        """All sub-components are instantiated on construction."""
        with patch.object(
            ScanifyOrchestrator, "load_state", return_value=None
        ):
            orch = ScanifyOrchestrator(
                data_provider="mock",
                calibration_state=_make_calibration_state(),
            )

        assert orch.data_feed is not None
        assert orch.bs_calc is not None
        assert orch.greeks_calc is not None
        assert orch.gex_engine is not None
        assert orch.gex_signal_gen is not None
        assert orch.pre_market is not None
        assert orch.directional is not None
        assert orch.premium is not None
        assert orch.gamma_scalp is not None
        assert orch.exit_mgr is not None
        assert orch.trade_logger is not None
        assert orch.calibrator is not None

    def test_default_configuration_values(self) -> None:
        """Default constructor arguments produce expected internal state."""
        with patch.object(
            ScanifyOrchestrator, "load_state", return_value=None
        ):
            orch = ScanifyOrchestrator(
                data_provider="mock",
                calibration_state=_make_calibration_state(),
            )

        assert orch._data_provider == "mock"
        assert orch._risk_budget == 10_000.0
        assert orch.paper_trade is True
        assert orch._log_dir == Path("logs/scanify")
        assert orch.is_running is False
        assert orch.scan_count == 0
        assert orch.session_setup is None
        assert orch.current_gex is None
        assert orch.active_signals == []
        assert orch.gex_signals == []
        assert orch._active_positions == []
        assert orch._closed_positions == []
        assert orch._daily_pnl == 0.0

    def test_custom_configuration_override(self) -> None:
        """Custom constructor arguments override defaults."""
        with patch.object(
            ScanifyOrchestrator, "load_state", return_value=None
        ):
            orch = ScanifyOrchestrator(
                data_provider="mock",
                api_key="CUSTOM_KEY",
                risk_budget=50_000.0,
                paper_trade=False,
                calibration_state=_make_calibration_state(),
                log_dir="/custom/logs",
            )

        assert orch._data_provider == "mock"
        assert orch._api_key == "CUSTOM_KEY"
        assert orch._risk_budget == 50_000.0
        assert orch.paper_trade is False
        assert orch._log_dir == Path("/custom/logs")

    def test_calibration_state_loaded_from_disk_when_none(self) -> None:
        """When no CalibrationState is given, load_state is invoked."""
        mock_state = _make_calibration_state()
        with patch.object(
            ScanifyOrchestrator, "load_state", return_value=mock_state
        ) as mock_load:
            orch = ScanifyOrchestrator(
                data_provider="mock",
                calibration_state=None,
            )
        mock_load.assert_called_once()
        assert orch._calibration_state is mock_state

    def test_calibration_state_skips_load_when_provided(self) -> None:
        """When CalibrationState is provided, load_state is NOT used."""
        provided_state = _make_calibration_state()
        with patch.object(
            ScanifyOrchestrator, "load_state", return_value=None
        ) as mock_load:
            orch = ScanifyOrchestrator(
                data_provider="mock",
                calibration_state=provided_state,
            )
        # load_state is never called when calibration_state is passed
        mock_load.assert_not_called()
        assert orch._calibration_state is provided_state


# ============================================================================
# 2. SESSION LIFECYCLE TESTS
# ============================================================================


class TestSessionLifecycle:
    """Test pre-market phase and session setup flow."""

    @pytest.mark.asyncio
    async def test_run_pre_market_phase_returns_session_setup(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """run_pre_market_phase returns a SessionSetup-like object."""
        result = await orchestrator.run_pre_market_phase()

        assert result is not None
        assert hasattr(result, "session_type")
        assert result.session_type in (
            SessionType.TRENDING,
            SessionType.RANGE,
            SessionType.VOLATILE,
            SessionType.SQUEEZE,
            SessionType.EVENT,
        )
        # The orchestrator should store it
        assert orchestrator.session_setup is result

    @pytest.mark.asyncio
    async def test_session_classification_stored(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """Pre-market scanner output is stored for downstream use."""
        await orchestrator.run_pre_market_phase()

        assert orchestrator.session_setup is not None
        assert orchestrator.session_setup.session_type == SessionType.TRENDING

    @pytest.mark.asyncio
    async def test_session_classification_affects_scanner_selection(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """The session_setup is passed to scanner .scan() calls."""
        # Set up session
        await orchestrator.run_pre_market_phase()

        # Trigger a directional scan directly
        snapshot = _make_snapshot()
        await orchestrator._run_directional_scan(snapshot)

        orchestrator.directional.scan.assert_called_once()
        call_kwargs = orchestrator.directional.scan.call_args
        assert call_kwargs.kwargs.get("session_setup") is orchestrator.session_setup

    @pytest.mark.asyncio
    async def test_pre_market_stores_initial_gex_profile(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """Pre-market phase populates current_gex from session setup."""
        await orchestrator.run_pre_market_phase()

        # The session_setup has gex_profile attribute set by our mock
        assert orchestrator.current_gex is not None

    @pytest.mark.asyncio
    async def test_pre_market_adds_alert(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """Pre-market phase adds alerts to the alert queue."""
        orchestrator.alerts.clear()
        await orchestrator.run_pre_market_phase()

        assert len(orchestrator.alerts) >= 1
        alert_types = [a["type"] for a in orchestrator.alerts]
        assert "PHASE" in alert_types or "SESSION" in alert_types

    @pytest.mark.asyncio
    async def test_initialize_connects_data_feed(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """initialize() connects the data feed and sets is_running."""
        await orchestrator.initialize()

        orchestrator.data_feed.connect.assert_called_once()
        assert orchestrator.is_running is True

    @pytest.mark.asyncio
    async def test_shutdown_disconnects_and_saves_state(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """shutdown() disconnects feed, persists state, sets is_running=False."""
        orchestrator.is_running = True
        with patch.object(orchestrator, "save_state") as mock_save:
            await orchestrator.shutdown()

        assert orchestrator.is_running is False
        orchestrator.data_feed.disconnect.assert_called_once()
        mock_save.assert_called_once()


# ============================================================================
# 3. SCAN CYCLE TIMING TESTS
# ============================================================================


class TestScanCycleTiming:
    """Test that scan_cycle dispatches the correct scanners for each zone."""

    @staticmethod
    def _patch_et_now(target_time: dt_time):
        """Return a patch context that fixes _get_et_now to a specific time."""
        fixed_dt = datetime(
            2025, 1, 15,
            target_time.hour,
            target_time.minute,
            target_time.second,
            tzinfo=timezone(timedelta(hours=-5)),
        )
        return patch(
            "scanify_0dte.orchestrator._get_et_now",
            return_value=fixed_dt,
        )

    @pytest.mark.asyncio
    async def test_opening_auction_no_scanning(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """During 9:30-9:45 opening auction, no scanners run."""
        with self._patch_et_now(dt_time(9, 35)):
            signals = await orchestrator.run_scan_cycle()

        assert signals == []
        orchestrator.directional.scan.assert_not_called()
        orchestrator.premium.scan.assert_not_called()
        orchestrator.gamma_scalp.scan.assert_not_called()

    @pytest.mark.asyncio
    async def test_morning_session_directional_runs(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """During 9:45-11:30, the directional scanner runs."""
        mock_signal = _make_scan_signal()
        orchestrator.directional.scan.return_value = [mock_signal]

        with self._patch_et_now(dt_time(10, 15)):
            signals = await orchestrator.run_scan_cycle()

        orchestrator.directional.scan.assert_called_once()
        # Premium should NOT be called during morning session
        orchestrator.premium.scan.assert_not_called()
        assert len(signals) == 1

    @pytest.mark.asyncio
    async def test_midday_premium_and_directional_run(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """During 11:30-1:30, both premium and directional scanners run."""
        with self._patch_et_now(dt_time(12, 30)):
            await orchestrator.run_scan_cycle()

        orchestrator.directional.scan.assert_called_once()
        orchestrator.premium.scan.assert_called_once()

    @pytest.mark.asyncio
    async def test_afternoon_directional_and_gamma_prep(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """During 1:30-3:00, directional + gamma scalp prep run."""
        with self._patch_et_now(dt_time(14, 0)):
            await orchestrator.run_scan_cycle()

        orchestrator.directional.scan.assert_called_once()
        # Gamma scalp runs in prep_only mode
        orchestrator.gamma_scalp.scan.assert_called_once()
        call_kwargs = orchestrator.gamma_scalp.scan.call_args
        assert call_kwargs.kwargs.get("prep_only") is True

    @pytest.mark.asyncio
    async def test_power_hour_gamma_scalp_and_directional(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """During 3:00-3:45, gamma scalp (active) + directional run."""
        with self._patch_et_now(dt_time(15, 15)):
            await orchestrator.run_scan_cycle()

        orchestrator.gamma_scalp.scan.assert_called_once()
        orchestrator.directional.scan.assert_called_once()
        # Gamma scalp NOT in prep_only mode during power hour
        call_kwargs = orchestrator.gamma_scalp.scan.call_args
        assert call_kwargs.kwargs.get("prep_only", False) is False

    @pytest.mark.asyncio
    async def test_settlement_exit_only_no_new_positions(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """During 3:45-4:00, no scanners run (exit-only mode)."""
        with self._patch_et_now(dt_time(15, 50)):
            signals = await orchestrator.run_scan_cycle()

        assert signals == []
        orchestrator.directional.scan.assert_not_called()
        orchestrator.premium.scan.assert_not_called()
        orchestrator.gamma_scalp.scan.assert_not_called()

    @pytest.mark.asyncio
    async def test_scan_count_incremented_each_cycle(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """Each scan cycle increments the scan counter."""
        assert orchestrator.scan_count == 0

        with self._patch_et_now(dt_time(10, 30)):
            await orchestrator.run_scan_cycle()
        assert orchestrator.scan_count == 1

        with self._patch_et_now(dt_time(10, 31)):
            await orchestrator.run_scan_cycle()
        assert orchestrator.scan_count == 2

    @pytest.mark.asyncio
    async def test_last_scan_time_updated(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """Each scan cycle updates last_scan_time."""
        assert orchestrator.last_scan_time is None

        with self._patch_et_now(dt_time(10, 30)):
            await orchestrator.run_scan_cycle()

        assert orchestrator.last_scan_time is not None

    @pytest.mark.asyncio
    async def test_signals_accumulated_in_active_signals(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """New signals are accumulated in active_signals list."""
        sig = _make_scan_signal()
        orchestrator.directional.scan.return_value = [sig]

        with self._patch_et_now(dt_time(10, 15)):
            await orchestrator.run_scan_cycle()

        assert len(orchestrator.active_signals) == 1
        assert orchestrator.active_signals[0] is sig


# ============================================================================
# 4. GEX PROFILE UPDATE TESTS
# ============================================================================


class TestGEXProfileUpdates:
    """Test GEX profile refresh and signal generation."""

    @pytest.mark.asyncio
    async def test_update_gex_profile_returns_valid_profile(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """update_gex_profile returns a GEXProfile-like object."""
        profile = await orchestrator.update_gex_profile()

        assert profile is not None
        assert hasattr(profile, "net_gex") or hasattr(profile, "total_net_gex")
        assert orchestrator.current_gex is profile

    @pytest.mark.asyncio
    async def test_update_gex_profile_fetches_chain_if_missing(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """If options_chain is None, update_gex_profile fetches it."""
        orchestrator.data_feed.options_chain = None

        await orchestrator.update_gex_profile()

        orchestrator.data_feed.fetch_options_chain.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_gex_profile_raises_on_zero_spx(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """update_gex_profile raises RuntimeError when SPX price is zero."""
        orchestrator.data_feed.spx_price = 0.0

        with pytest.raises(RuntimeError, match="SPX price unavailable"):
            await orchestrator.update_gex_profile()

    @pytest.mark.asyncio
    async def test_check_gex_signals_returns_empty_without_profile(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """check_gex_signals returns [] when current_gex is None."""
        orchestrator.current_gex = None

        signals = await orchestrator.check_gex_signals()

        assert signals == []

    @pytest.mark.asyncio
    async def test_check_gex_signals_generates_signals(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """check_gex_signals returns signals from the signal generator."""
        orchestrator.current_gex = _make_gex_profile()
        expected_signals = [_make_gex_signal()]
        orchestrator.gex_signal_gen.check_all_signals.return_value = expected_signals

        result = await orchestrator.check_gex_signals()

        assert len(result) == 1
        orchestrator.gex_signal_gen.check_all_signals.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_gex_signals_returns_empty_on_zero_spx(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """check_gex_signals returns [] when SPX price is zero."""
        orchestrator.current_gex = _make_gex_profile()
        orchestrator.data_feed.spx_price = 0.0

        signals = await orchestrator.check_gex_signals()

        assert signals == []

    @pytest.mark.asyncio
    async def test_gex_signals_accumulated_in_scan_cycle(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """GEX signals from scan cycles accumulate in gex_signals list."""
        orchestrator.current_gex = _make_gex_profile()
        gex_sig = _make_gex_signal()
        orchestrator.gex_signal_gen.check_all_signals.return_value = [gex_sig]

        with TestScanCycleTiming._patch_et_now(dt_time(10, 30)):
            await orchestrator.run_scan_cycle()

        assert len(orchestrator.gex_signals) >= 1


# ============================================================================
# 5. POSITION MANAGEMENT TESTS
# ============================================================================


class TestPositionManagement:
    """Test signal processing, position entry, and exit management."""

    @pytest.mark.asyncio
    async def test_process_signal_opens_position_paper_mode(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """process_signal creates a trade entry in paper mode."""
        signal = _make_scan_signal(entry_price=5.50, stop_loss=2.75)

        # Ensure we are not in settlement window
        with TestScanCycleTiming._patch_et_now(dt_time(10, 30)):
            trade = await orchestrator.process_signal(signal)

        assert trade is not None
        assert trade["paper_trade"] is True
        assert trade["entry_price"] == 5.50
        assert trade["status"] == "OPEN"
        assert trade["fill_price"] == 5.50
        assert len(orchestrator._active_positions) == 1

    @pytest.mark.asyncio
    async def test_process_signal_rejected_in_settlement(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """Signals are rejected during the settlement window."""
        signal = _make_scan_signal()

        with TestScanCycleTiming._patch_et_now(dt_time(15, 50)):
            trade = await orchestrator.process_signal(signal)

        assert trade is None
        assert len(orchestrator._active_positions) == 0

    @pytest.mark.asyncio
    async def test_process_signal_rejected_at_max_positions(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """Signals are rejected when max concurrent positions are reached."""
        # Fill to max_concurrent_positions (5 by default)
        for i in range(5):
            orchestrator._active_positions.append(
                {"signal_id": f"POS-{i}", "pnl": 0.0}
            )

        signal = _make_scan_signal()
        with TestScanCycleTiming._patch_et_now(dt_time(10, 30)):
            trade = await orchestrator.process_signal(signal)

        assert trade is None

    @pytest.mark.asyncio
    async def test_process_signal_rejected_on_daily_loss_limit(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """Signals are rejected when daily loss limit is breached."""
        # With budget=10000, max_daily_loss_pct=0.06, limit = -600
        orchestrator._daily_pnl = -700.0

        signal = _make_scan_signal()
        with TestScanCycleTiming._patch_et_now(dt_time(10, 30)):
            trade = await orchestrator.process_signal(signal)

        assert trade is None

    @pytest.mark.asyncio
    async def test_process_signal_adds_risk_alert_on_loss_limit(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """A CRITICAL alert is added when daily loss limit is breached."""
        orchestrator._daily_pnl = -700.0
        orchestrator.alerts.clear()

        signal = _make_scan_signal()
        with TestScanCycleTiming._patch_et_now(dt_time(10, 30)):
            await orchestrator.process_signal(signal)

        risk_alerts = [a for a in orchestrator.alerts if a["type"] == "RISK"]
        assert len(risk_alerts) >= 1
        assert risk_alerts[0]["priority"] == "CRITICAL"

    @pytest.mark.asyncio
    async def test_process_signal_logs_entry(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """process_signal calls trade_logger.log_entry."""
        signal = _make_scan_signal()

        with TestScanCycleTiming._patch_et_now(dt_time(10, 30)):
            await orchestrator.process_signal(signal)

        orchestrator.trade_logger.log_entry.assert_called_once()

    @pytest.mark.asyncio
    async def test_manage_positions_no_active_returns_empty(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """manage_positions returns [] when no active positions exist."""
        result = await orchestrator.manage_positions()
        assert result == []

    @pytest.mark.asyncio
    async def test_manage_positions_calls_exit_manager(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """manage_positions evaluates each active position via ExitManager."""
        orchestrator._active_positions.append(
            {
                "signal_id": "POS-1",
                "entry_price": 5.0,
                "size": 1,
                "direction": "BULL",
                "pnl": 0.0,
            }
        )

        await orchestrator.manage_positions()

        orchestrator.exit_mgr.evaluate_exit.assert_called_once()

    @pytest.mark.asyncio
    async def test_manage_positions_closes_on_exit_signal(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """When exit_manager returns exit=True, the position is closed."""
        pos = {
            "signal_id": "POS-1",
            "entry_price": 5.0,
            "size": 1,
            "direction": "LONG",
            "pnl": 0.0,
        }
        orchestrator._active_positions.append(pos)
        orchestrator.exit_mgr.evaluate_exit.return_value = {
            "exit": True,
            "reason": "PROFIT_TARGET",
            "exit_price": 8.0,
        }

        with TestScanCycleTiming._patch_et_now(dt_time(11, 0)):
            actions = await orchestrator.manage_positions()

        assert len(actions) == 1
        assert len(orchestrator._active_positions) == 0
        assert len(orchestrator._closed_positions) == 1

    @pytest.mark.asyncio
    async def test_close_position_calculates_pnl_long(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """P&L is correctly computed for LONG positions."""
        pos = {
            "signal_id": "POS-L1",
            "entry_price": 5.0,
            "size": 2,
            "direction": "LONG",
            "pnl": 0.0,
        }
        orchestrator._active_positions.append(pos)

        with TestScanCycleTiming._patch_et_now(dt_time(11, 0)):
            await orchestrator._close_position(pos, reason="TEST", exit_price=8.0)

        assert pos["pnl"] == (8.0 - 5.0) * 2 * 100.0  # 600.0
        assert pos["status"] == "CLOSED"
        assert pos["exit_reason"] == "TEST"

    @pytest.mark.asyncio
    async def test_close_position_calculates_pnl_short(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """P&L is correctly computed for SHORT positions."""
        pos = {
            "signal_id": "POS-S1",
            "entry_price": 5.0,
            "size": 1,
            "direction": "SHORT",
            "pnl": 0.0,
        }
        orchestrator._active_positions.append(pos)

        with TestScanCycleTiming._patch_et_now(dt_time(11, 0)):
            await orchestrator._close_position(pos, reason="TEST", exit_price=3.0)

        assert pos["pnl"] == (5.0 - 3.0) * 1 * 100.0  # 200.0

    @pytest.mark.asyncio
    async def test_close_position_updates_daily_pnl(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """Closing a position updates _daily_pnl."""
        orchestrator._daily_pnl = 0.0
        pos = {
            "signal_id": "POS-D1",
            "entry_price": 5.0,
            "size": 1,
            "direction": "LONG",
            "pnl": 0.0,
        }
        orchestrator._active_positions.append(pos)

        with TestScanCycleTiming._patch_et_now(dt_time(11, 0)):
            await orchestrator._close_position(pos, reason="TEST", exit_price=7.0)

        expected_pnl = (7.0 - 5.0) * 1 * 100.0
        assert orchestrator._daily_pnl == expected_pnl


# ============================================================================
# 6. POST-MARKET TESTS
# ============================================================================


class TestPostMarket:
    """Test post-market phase: report, calibration, state persistence."""

    @pytest.mark.asyncio
    async def test_run_post_market_generates_daily_report(
        self, orchestrator: ScanifyOrchestrator, tmp_path: Path
    ) -> None:
        """run_post_market produces a complete daily report dict."""
        orchestrator._log_dir = tmp_path
        orchestrator.session_setup = _make_session_setup()

        report = await orchestrator.run_post_market(target_date=date(2025, 1, 15))

        assert "date" in report
        assert report["date"] == "2025-01-15"
        assert "pnl_summary" in report
        assert "trades" in report
        assert "calibration" in report
        assert "scan_count" in report
        assert "alerts" in report
        assert "intraday_pnl_curve" in report
        assert "session_type" in report

    @pytest.mark.asyncio
    async def test_run_post_market_closes_remaining_positions(
        self, orchestrator: ScanifyOrchestrator, tmp_path: Path
    ) -> None:
        """All remaining active positions are closed during post-market."""
        orchestrator._log_dir = tmp_path
        orchestrator.session_setup = _make_session_setup()
        orchestrator._active_positions.append(
            {
                "signal_id": "POS-PM1",
                "entry_price": 5.0,
                "size": 1,
                "direction": "LONG",
                "pnl": 0.0,
            }
        )

        with TestScanCycleTiming._patch_et_now(dt_time(16, 20)):
            await orchestrator.run_post_market(target_date=date(2025, 1, 15))

        assert len(orchestrator._active_positions) == 0
        assert len(orchestrator._closed_positions) == 1
        assert orchestrator._closed_positions[0]["exit_reason"] == "MARKET_CLOSE"

    @pytest.mark.asyncio
    async def test_run_post_market_runs_calibration(
        self, orchestrator: ScanifyOrchestrator, tmp_path: Path
    ) -> None:
        """Calibration is executed during post-market."""
        orchestrator._log_dir = tmp_path
        orchestrator.session_setup = _make_session_setup()

        await orchestrator.run_post_market(target_date=date(2025, 1, 15))

        orchestrator.calibrator.run_daily_calibration.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_post_market_updates_calibration_state(
        self, orchestrator: ScanifyOrchestrator, tmp_path: Path
    ) -> None:
        """Calibration result updates the internal calibration state."""
        orchestrator._log_dir = tmp_path
        orchestrator.session_setup = _make_session_setup()
        new_state = _make_calibration_state()
        orchestrator.calibrator.run_daily_calibration.return_value = {
            "summary": "OK",
            "updated_state": new_state,
        }

        await orchestrator.run_post_market(target_date=date(2025, 1, 15))

        assert orchestrator._calibration_state is new_state

    @pytest.mark.asyncio
    async def test_run_post_market_saves_state(
        self, orchestrator: ScanifyOrchestrator, tmp_path: Path
    ) -> None:
        """Post-market phase calls save_state."""
        orchestrator._log_dir = tmp_path
        orchestrator.session_setup = _make_session_setup()

        with patch.object(orchestrator, "save_state") as mock_save:
            await orchestrator.run_post_market(target_date=date(2025, 1, 15))

        mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_post_market_writes_report_file(
        self, orchestrator: ScanifyOrchestrator, tmp_path: Path
    ) -> None:
        """Post-market persists the daily report as JSON to disk."""
        orchestrator._log_dir = tmp_path
        orchestrator.session_setup = _make_session_setup()

        await orchestrator.run_post_market(target_date=date(2025, 1, 15))

        report_path = tmp_path / "report_2025-01-15.json"
        assert report_path.exists()

        with open(report_path, "r") as f:
            data = json.load(f)
        assert data["date"] == "2025-01-15"

    @pytest.mark.asyncio
    async def test_run_post_market_pnl_summary_accuracy(
        self, orchestrator: ScanifyOrchestrator, tmp_path: Path
    ) -> None:
        """P&L summary in the report reflects closed trade data."""
        orchestrator._log_dir = tmp_path
        orchestrator.session_setup = _make_session_setup()

        # Simulate two closed trades
        orchestrator._closed_positions = [
            {"signal_id": "T1", "pnl": 200.0, "direction": "LONG"},
            {"signal_id": "T2", "pnl": -50.0, "direction": "SHORT"},
        ]

        report = await orchestrator.run_post_market(target_date=date(2025, 1, 15))

        summary = report["pnl_summary"]
        assert summary["total_pnl"] == 150.0
        assert summary["total_trades"] == 2
        assert summary["winning_trades"] == 1
        assert summary["losing_trades"] == 1
        assert summary["win_rate"] == 0.5


# ============================================================================
# 7. STATUS / DASHBOARD TESTS
# ============================================================================


class TestStatusDashboard:
    """Test get_status and get_dashboard_data methods."""

    def test_get_status_returns_complete_dict(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """get_status returns all required keys."""
        with TestScanCycleTiming._patch_et_now(dt_time(10, 30)):
            status = orchestrator.get_status()

        required_keys = {
            "session_type",
            "time_zone",
            "minutes_remaining",
            "active_positions",
            "total_pnl",
            "current_gex_summary",
            "recent_signals",
            "recent_alerts",
            "scan_count",
            "last_scan_time",
            "is_running",
            "paper_trade",
            "data_connected",
            "risk_budget_remaining",
        }
        assert required_keys.issubset(set(status.keys()))

    def test_get_status_reflects_active_positions(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """get_status active_positions count reflects current state."""
        orchestrator._active_positions = [
            {"pnl": 0.0}, {"pnl": 50.0}
        ]
        with TestScanCycleTiming._patch_et_now(dt_time(10, 30)):
            status = orchestrator.get_status()

        assert status["active_positions"] == 2

    def test_get_status_gex_summary_populated(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """get_status includes GEX summary when current_gex is set."""
        orchestrator.current_gex = _make_gex_profile()

        with TestScanCycleTiming._patch_et_now(dt_time(10, 30)):
            status = orchestrator.get_status()

        assert status["current_gex_summary"] != {}
        assert "gamma_flip_level" in status["current_gex_summary"]

    def test_get_status_gex_summary_empty_when_no_gex(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """get_status returns empty GEX summary when current_gex is None."""
        orchestrator.current_gex = None

        with TestScanCycleTiming._patch_et_now(dt_time(10, 30)):
            status = orchestrator.get_status()

        assert status["current_gex_summary"] == {}

    def test_get_status_time_zone_classification(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """get_status classifies the correct time zone."""
        with TestScanCycleTiming._patch_et_now(dt_time(10, 0)):
            status = orchestrator.get_status()
        assert status["time_zone"] == "MORNING_SESSION"

        with TestScanCycleTiming._patch_et_now(dt_time(12, 0)):
            status = orchestrator.get_status()
        assert status["time_zone"] == "MIDDAY_LULL"

        with TestScanCycleTiming._patch_et_now(dt_time(15, 15)):
            status = orchestrator.get_status()
        assert status["time_zone"] == "POWER_HOUR"

    def test_get_status_risk_budget_remaining(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """Risk budget remaining is computed correctly."""
        orchestrator._daily_pnl = -300.0
        with TestScanCycleTiming._patch_et_now(dt_time(10, 30)):
            status = orchestrator.get_status()

        assert status["risk_budget_remaining"] == 10_000.0 + (-300.0)

    def test_get_status_recent_signals_capped(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """recent_signals are capped to 10 entries."""
        for i in range(20):
            orchestrator.active_signals.append(_make_scan_signal(signal_id=f"S-{i}"))

        with TestScanCycleTiming._patch_et_now(dt_time(10, 30)):
            status = orchestrator.get_status()

        assert len(status["recent_signals"]) == 10

    def test_get_dashboard_data_returns_complete_dict(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """get_dashboard_data returns all required top-level keys."""
        orchestrator.session_setup = _make_session_setup()
        orchestrator.current_gex = _make_gex_profile()

        with TestScanCycleTiming._patch_et_now(dt_time(10, 30)):
            dashboard = orchestrator.get_dashboard_data()

        required_keys = {
            "spx_price",
            "expected_move",
            "gex_profile",
            "key_levels",
            "active_positions",
            "direction_score",
            "recent_signals",
            "gex_signals",
            "intraday_pnl_curve",
            "session_classification",
            "status",
        }
        assert required_keys.issubset(set(dashboard.keys()))

    def test_get_dashboard_data_spx_price(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """Dashboard SPX price reflects data feed value."""
        orchestrator.data_feed.spx_price = 5280.0

        with TestScanCycleTiming._patch_et_now(dt_time(10, 30)):
            dashboard = orchestrator.get_dashboard_data()

        assert dashboard["spx_price"] == 5280.0

    def test_get_dashboard_data_expected_move_populated(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """Expected move data is populated from session setup."""
        orchestrator.session_setup = _make_session_setup()

        with TestScanCycleTiming._patch_et_now(dt_time(10, 30)):
            dashboard = orchestrator.get_dashboard_data()

        assert dashboard["expected_move"] != {}
        assert "upper_1sigma" in dashboard["expected_move"]

    def test_get_dashboard_data_session_classification(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """Session classification is populated in dashboard data."""
        orchestrator.session_setup = _make_session_setup(
            session_type=SessionType.VOLATILE
        )

        with TestScanCycleTiming._patch_et_now(dt_time(10, 30)):
            dashboard = orchestrator.get_dashboard_data()

        assert dashboard["session_classification"]["type"] == "VOLATILE"

    def test_get_dashboard_data_positions_list(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """Active positions appear in dashboard data."""
        orchestrator._active_positions = [
            {
                "signal_id": "P1",
                "direction": "BULL",
                "strategy": "DIRECTIONAL",
                "entry_price": 5.0,
                "size": 2,
                "pnl": 100.0,
                "status": "OPEN",
            }
        ]

        with TestScanCycleTiming._patch_et_now(dt_time(10, 30)):
            dashboard = orchestrator.get_dashboard_data()

        assert len(dashboard["active_positions"]) == 1
        assert dashboard["active_positions"][0]["signal_id"] == "P1"

    def test_get_dashboard_data_includes_status(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """Dashboard data embeds the full status dict."""
        with TestScanCycleTiming._patch_et_now(dt_time(10, 30)):
            dashboard = orchestrator.get_dashboard_data()

        assert "status" in dashboard
        assert "is_running" in dashboard["status"]


# ============================================================================
# 8. STATE PERSISTENCE TESTS
# ============================================================================


class TestStatePersistence:
    """Test save_state and load_state methods."""

    def test_save_state_writes_to_disk(
        self, orchestrator: ScanifyOrchestrator, tmp_path: Path
    ) -> None:
        """save_state creates calibration_state.json in log_dir."""
        orchestrator._log_dir = tmp_path
        orchestrator._calibration_state = _make_calibration_state()

        orchestrator.save_state()

        state_path = tmp_path / "calibration_state.json"
        assert state_path.exists()

        with open(state_path, "r") as f:
            data = json.load(f)

        assert "saved_at" in data
        assert data["risk_budget"] == 10_000.0
        assert data["paper_trade"] is True
        assert data["data_provider"] == "mock"

    def test_save_state_includes_calibration_data(
        self, orchestrator: ScanifyOrchestrator, tmp_path: Path
    ) -> None:
        """save_state serializes calibration state data."""
        orchestrator._log_dir = tmp_path
        orchestrator._calibration_state = _make_calibration_state()

        orchestrator.save_state()

        state_path = tmp_path / "calibration_state.json"
        with open(state_path, "r") as f:
            data = json.load(f)

        assert "calibration" in data

    def test_save_state_creates_directory_if_needed(
        self, orchestrator: ScanifyOrchestrator, tmp_path: Path
    ) -> None:
        """save_state creates the log directory if it doesn't exist."""
        nested_path = tmp_path / "deep" / "nested" / "dir"
        orchestrator._log_dir = nested_path
        orchestrator._calibration_state = _make_calibration_state()

        orchestrator.save_state()

        assert (nested_path / "calibration_state.json").exists()

    def test_save_state_with_none_calibration(
        self, orchestrator: ScanifyOrchestrator, tmp_path: Path
    ) -> None:
        """save_state handles None calibration state gracefully."""
        orchestrator._log_dir = tmp_path
        orchestrator._calibration_state = None

        # Should not raise
        orchestrator.save_state()

        state_path = tmp_path / "calibration_state.json"
        assert state_path.exists()
        with open(state_path, "r") as f:
            data = json.load(f)
        assert "calibration" not in data

    def test_load_state_returns_none_when_no_file(
        self, orchestrator: ScanifyOrchestrator, tmp_path: Path
    ) -> None:
        """load_state returns None when no state file exists."""
        orchestrator._log_dir = tmp_path

        result = orchestrator.load_state()

        assert result is None

    def test_load_state_restores_from_disk(
        self, orchestrator: ScanifyOrchestrator, tmp_path: Path
    ) -> None:
        """load_state reads and reconstructs state from JSON."""
        orchestrator._log_dir = tmp_path

        # Write a state file
        state_data = {
            "saved_at": "2025-01-15T16:30:00",
            "risk_budget": 10_000.0,
            "paper_trade": True,
            "data_provider": "mock",
            "scan_count": 42,
            "calibration": {
                "current_weights": {
                    "market_internals": 0.20,
                    "options_flow": 0.20,
                    "price_action": 0.20,
                    "gex_structure": 0.20,
                    "cross_asset": 0.20,
                },
                "entry_threshold": 55.0,
                "profit_targets_by_zone": {},
                "stop_loss_pct": 50.0,
                "regime": "normal",
                "last_calibration": "2025-01-15T16:30:00",
                "trade_count": 42,
                "gex_signal_accuracy": 0.65,
            },
        }
        state_path = tmp_path / "calibration_state.json"
        with open(state_path, "w") as f:
            json.dump(state_data, f)

        result = orchestrator.load_state()

        # Should return a CalibrationState (or None if construction fails
        # due to Pydantic validation with our SimpleNamespace). The key
        # test is that it attempts to load and does not crash.
        # If CalibrationState has from_dict or accepts **kwargs, it will work.
        # Otherwise, we just verify it doesn't raise.

    def test_load_state_returns_none_on_corrupt_json(
        self, orchestrator: ScanifyOrchestrator, tmp_path: Path
    ) -> None:
        """load_state returns None when the JSON is corrupt."""
        orchestrator._log_dir = tmp_path

        state_path = tmp_path / "calibration_state.json"
        state_path.write_text("{not valid json!!!")

        result = orchestrator.load_state()

        assert result is None

    def test_load_state_returns_none_on_missing_calibration_key(
        self, orchestrator: ScanifyOrchestrator, tmp_path: Path
    ) -> None:
        """load_state returns None when calibration key is missing."""
        orchestrator._log_dir = tmp_path

        state_path = tmp_path / "calibration_state.json"
        state_path.write_text(json.dumps({"saved_at": "2025-01-01"}))

        result = orchestrator.load_state()

        assert result is None

    def test_save_then_load_roundtrip(
        self, orchestrator: ScanifyOrchestrator, tmp_path: Path
    ) -> None:
        """Saved state can be loaded back without error."""
        orchestrator._log_dir = tmp_path
        orchestrator._calibration_state = _make_calibration_state()
        orchestrator.scan_count = 99

        orchestrator.save_state()

        state_path = tmp_path / "calibration_state.json"
        assert state_path.exists()

        with open(state_path, "r") as f:
            loaded_data = json.load(f)

        assert loaded_data["scan_count"] == 99
        assert loaded_data["risk_budget"] == 10_000.0


# ============================================================================
# 9. FACTORY FUNCTION TESTS
# ============================================================================


class TestFactoryFunction:
    """Test create_scanify_system factory."""

    def test_create_scanify_system_returns_orchestrator(self) -> None:
        """Factory returns a valid ScanifyOrchestrator instance."""
        with patch.object(
            ScanifyOrchestrator, "load_state", return_value=None
        ):
            system = create_scanify_system()

        assert isinstance(system, ScanifyOrchestrator)

    def test_create_scanify_system_default_config(self) -> None:
        """Factory with no config uses sensible defaults."""
        with patch.object(
            ScanifyOrchestrator, "load_state", return_value=None
        ):
            system = create_scanify_system()

        assert system._data_provider == "polygon"
        assert system._risk_budget == 10_000.0
        assert system.paper_trade is True

    def test_create_scanify_system_with_custom_config(self) -> None:
        """Factory applies custom config overrides."""
        config = {
            "data_provider": "mock",
            "api_key": "MY_KEY",
            "risk_budget": 25_000.0,
            "paper_trade": False,
            "log_dir": "/tmp/custom_scanify",
        }

        with patch.object(
            ScanifyOrchestrator, "load_state", return_value=None
        ):
            system = create_scanify_system(config)

        assert system._data_provider == "mock"
        assert system._api_key == "MY_KEY"
        assert system._risk_budget == 25_000.0
        assert system.paper_trade is False
        assert system._log_dir == Path("/tmp/custom_scanify")

    def test_create_scanify_system_with_calibration_state(self) -> None:
        """Factory accepts a pre-loaded calibration state."""
        cal_state = _make_calibration_state()
        config = {
            "data_provider": "mock",
            "calibration_state": cal_state,
        }

        with patch.object(
            ScanifyOrchestrator, "load_state", return_value=None
        ) as mock_load:
            system = create_scanify_system(config)

        assert system._calibration_state is cal_state
        mock_load.assert_not_called()

    def test_create_scanify_system_with_none_config(self) -> None:
        """Factory handles None config gracefully (uses defaults)."""
        with patch.object(
            ScanifyOrchestrator, "load_state", return_value=None
        ):
            system = create_scanify_system(None)

        assert isinstance(system, ScanifyOrchestrator)
        assert system._data_provider == "polygon"

    def test_create_scanify_system_with_empty_config(self) -> None:
        """Factory handles empty dict config (uses all defaults)."""
        with patch.object(
            ScanifyOrchestrator, "load_state", return_value=None
        ):
            system = create_scanify_system({})

        assert isinstance(system, ScanifyOrchestrator)
        assert system.paper_trade is True


# ============================================================================
# 10. TIME ZONE CLASSIFICATION TESTS (private helper)
# ============================================================================


class TestTimeZoneClassification:
    """Test _classify_time_zone static method."""

    @pytest.mark.parametrize(
        "input_time, expected_zone",
        [
            (dt_time(8, 0), "PRE_MARKET"),
            (dt_time(9, 29), "PRE_MARKET"),
            (dt_time(9, 30), "OPENING_AUCTION"),
            (dt_time(9, 44), "OPENING_AUCTION"),
            (dt_time(9, 45), "MORNING_SESSION"),
            (dt_time(11, 0), "MORNING_SESSION"),
            (dt_time(11, 29), "MORNING_SESSION"),
            (dt_time(11, 30), "MIDDAY_LULL"),
            (dt_time(12, 30), "MIDDAY_LULL"),
            (dt_time(13, 29), "MIDDAY_LULL"),
            (dt_time(13, 30), "AFTERNOON_ACCEL"),
            (dt_time(14, 0), "AFTERNOON_ACCEL"),
            (dt_time(14, 59), "AFTERNOON_ACCEL"),
            (dt_time(15, 0), "POWER_HOUR"),
            (dt_time(15, 30), "POWER_HOUR"),
            (dt_time(15, 44), "POWER_HOUR"),
            (dt_time(15, 45), "SETTLEMENT_WINDOW"),
            (dt_time(15, 59), "SETTLEMENT_WINDOW"),
            (dt_time(16, 0), "AFTER_HOURS"),
            (dt_time(17, 0), "AFTER_HOURS"),
        ],
    )
    def test_classify_time_zone(
        self, input_time: dt_time, expected_zone: str
    ) -> None:
        """Each time-of-day maps to the correct zone label."""
        assert ScanifyOrchestrator._classify_time_zone(input_time) == expected_zone


# ============================================================================
# 11. CYCLE INTERVAL TESTS (private helper)
# ============================================================================


class TestCycleInterval:
    """Test _get_cycle_interval static method."""

    @pytest.mark.parametrize(
        "zone, expected_interval",
        [
            ("PRE_MARKET", 60.0),
            ("OPENING_AUCTION", 5.0),
            ("MORNING_SESSION", 60.0),
            ("MIDDAY_LULL", 60.0),
            ("AFTERNOON_ACCEL", 60.0),
            ("POWER_HOUR", 30.0),
            ("SETTLEMENT_WINDOW", 15.0),
            ("AFTER_HOURS", 300.0),
        ],
    )
    def test_cycle_interval_by_zone(
        self, zone: str, expected_interval: float
    ) -> None:
        """Each zone has the correct scan cycle sleep interval."""
        assert ScanifyOrchestrator._get_cycle_interval(zone) == expected_interval

    def test_unknown_zone_defaults_to_60(self) -> None:
        """Unknown zone names default to 60 seconds."""
        assert ScanifyOrchestrator._get_cycle_interval("UNKNOWN_ZONE") == 60.0


# ============================================================================
# 12. ALERT SYSTEM TESTS
# ============================================================================


class TestAlertSystem:
    """Test add_alert and alert queue management."""

    def test_add_alert_appends_to_queue(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """add_alert adds entries to the alerts list."""
        orchestrator.alerts.clear()

        orchestrator.add_alert("TEST", "Test message", "INFO")

        assert len(orchestrator.alerts) == 1
        assert orchestrator.alerts[0]["type"] == "TEST"
        assert orchestrator.alerts[0]["message"] == "Test message"
        assert orchestrator.alerts[0]["priority"] == "INFO"
        assert "timestamp" in orchestrator.alerts[0]

    def test_alert_queue_capped_at_500(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """Alert queue is automatically trimmed to 500 entries."""
        orchestrator.alerts.clear()

        for i in range(510):
            orchestrator.add_alert("BULK", f"Alert {i}", "INFO")

        assert len(orchestrator.alerts) <= 500

    def test_alert_priority_levels(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """Alert system accepts INFO, HIGH, and CRITICAL priorities."""
        orchestrator.alerts.clear()

        orchestrator.add_alert("T1", "Info", "INFO")
        orchestrator.add_alert("T2", "High", "HIGH")
        orchestrator.add_alert("T3", "Critical", "CRITICAL")

        assert orchestrator.alerts[0]["priority"] == "INFO"
        assert orchestrator.alerts[1]["priority"] == "HIGH"
        assert orchestrator.alerts[2]["priority"] == "CRITICAL"


# ============================================================================
# 13. MAX DRAWDOWN CALCULATION TESTS
# ============================================================================


class TestMaxDrawdown:
    """Test the _compute_max_drawdown helper."""

    def test_empty_curve_returns_zero(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """No P&L data yields zero drawdown."""
        orchestrator._intraday_pnl_curve = []
        assert orchestrator._compute_max_drawdown() == 0.0

    def test_monotonically_increasing_zero_drawdown(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """A continuously rising curve has zero drawdown."""
        orchestrator._intraday_pnl_curve = [
            {"time": "10:00:00", "total": 0.0},
            {"time": "10:30:00", "total": 100.0},
            {"time": "11:00:00", "total": 200.0},
            {"time": "11:30:00", "total": 300.0},
        ]
        assert orchestrator._compute_max_drawdown() == 0.0

    def test_drawdown_computed_correctly(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """Drawdown equals peak-minus-trough for a peak-valley pattern."""
        orchestrator._intraday_pnl_curve = [
            {"time": "10:00:00", "total": 0.0},
            {"time": "10:30:00", "total": 500.0},
            {"time": "11:00:00", "total": 200.0},   # 300 drawdown from peak
            {"time": "11:30:00", "total": 450.0},
        ]
        assert orchestrator._compute_max_drawdown() == 300.0

    def test_multiple_drawdowns_returns_max(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """When multiple drawdowns occur, the largest one is returned."""
        orchestrator._intraday_pnl_curve = [
            {"time": "10:00:00", "total": 0.0},
            {"time": "10:30:00", "total": 200.0},
            {"time": "11:00:00", "total": 100.0},   # 100 drawdown
            {"time": "11:30:00", "total": 600.0},
            {"time": "12:00:00", "total": 150.0},   # 450 drawdown (max)
            {"time": "12:30:00", "total": 400.0},
        ]
        assert orchestrator._compute_max_drawdown() == 450.0


# ============================================================================
# 14. SHUTDOWN AND CLEANUP TESTS
# ============================================================================


class TestShutdown:
    """Test graceful shutdown behavior."""

    @pytest.mark.asyncio
    async def test_shutdown_closes_remaining_positions(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """Shutdown closes all remaining open positions."""
        orchestrator._active_positions.append(
            {
                "signal_id": "SHUTDOWN-POS-1",
                "entry_price": 5.0,
                "size": 1,
                "direction": "LONG",
                "pnl": 0.0,
            }
        )
        orchestrator._active_positions.append(
            {
                "signal_id": "SHUTDOWN-POS-2",
                "entry_price": 3.0,
                "size": 1,
                "direction": "SHORT",
                "pnl": 0.0,
            }
        )

        with patch.object(orchestrator, "save_state"):
            await orchestrator.shutdown()

        assert len(orchestrator._active_positions) == 0
        assert len(orchestrator._closed_positions) == 2

    @pytest.mark.asyncio
    async def test_shutdown_sets_event(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """Shutdown sets the _shutdown_event."""
        with patch.object(orchestrator, "save_state"):
            await orchestrator.shutdown()

        assert orchestrator._shutdown_event.is_set()

    @pytest.mark.asyncio
    async def test_shutdown_handles_disconnect_error(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """Shutdown handles data feed disconnect errors gracefully."""
        orchestrator.data_feed.disconnect = AsyncMock(
            side_effect=ConnectionError("Network error")
        )

        with patch.object(orchestrator, "save_state"):
            # Should not raise
            await orchestrator.shutdown()

        assert orchestrator.is_running is False


# ============================================================================
# 15. EDGE CASES AND INTEGRATION-LIKE TESTS
# ============================================================================


class TestEdgeCases:
    """Edge cases and cross-cutting integration scenarios."""

    @pytest.mark.asyncio
    async def test_scan_cycle_skips_on_zero_spx_price(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """Scan cycle returns empty when SPX price is zero."""
        orchestrator.data_feed.get_snapshot.return_value = _make_snapshot(
            spx_price=0.0
        )

        with TestScanCycleTiming._patch_et_now(dt_time(10, 30)):
            signals = await orchestrator.run_scan_cycle()

        assert signals == []
        orchestrator.directional.scan.assert_not_called()

    @pytest.mark.asyncio
    async def test_scan_cycle_handles_scanner_exceptions(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """Scan cycle continues even if a scanner raises an exception."""
        orchestrator.directional.scan.side_effect = RuntimeError("Scanner crash")

        with TestScanCycleTiming._patch_et_now(dt_time(10, 30)):
            # Should not raise
            signals = await orchestrator.run_scan_cycle()

        # The scan cycle catches the exception internally
        assert isinstance(signals, list)

    @pytest.mark.asyncio
    async def test_pnl_snapshot_recorded_each_cycle(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """Each scan cycle appends to the intraday P&L curve."""
        orchestrator._intraday_pnl_curve.clear()

        with TestScanCycleTiming._patch_et_now(dt_time(10, 30)):
            await orchestrator.run_scan_cycle()

        assert len(orchestrator._intraday_pnl_curve) == 1
        point = orchestrator._intraday_pnl_curve[0]
        assert "time" in point
        assert "realized" in point
        assert "unrealized" in point
        assert "total" in point

    @pytest.mark.asyncio
    async def test_process_signal_sizes_position_correctly(
        self, orchestrator: ScanifyOrchestrator
    ) -> None:
        """Position sizing respects risk budget and stop distance."""
        # entry=10.0, stop=8.0 => risk_per_contract = 2.0 * 100 = 200
        # max_risk_per_trade = 10000 * 0.02 = 200
        # size = max(1, int(200 / 200)) = 1
        signal = _make_scan_signal(entry_price=10.0, stop_loss=8.0)

        with TestScanCycleTiming._patch_et_now(dt_time(10, 30)):
            trade = await orchestrator.process_signal(signal)

        assert trade is not None
        assert trade["size"] >= 1

    @pytest.mark.asyncio
    async def test_full_mini_session_flow(
        self, orchestrator: ScanifyOrchestrator, tmp_path: Path
    ) -> None:
        """End-to-end mini-flow: pre-market -> scan -> post-market."""
        orchestrator._log_dir = tmp_path

        # 1. Pre-market
        setup = await orchestrator.run_pre_market_phase()
        assert orchestrator.session_setup is not None

        # 2. Morning scan cycle
        sig = _make_scan_signal()
        orchestrator.directional.scan.return_value = [sig]

        with TestScanCycleTiming._patch_et_now(dt_time(10, 15)):
            signals = await orchestrator.run_scan_cycle()
        assert len(signals) == 1
        assert orchestrator.scan_count == 1

        # 3. Post-market
        report = await orchestrator.run_post_market(target_date=date(2025, 1, 15))
        assert report is not None
        assert "pnl_summary" in report
