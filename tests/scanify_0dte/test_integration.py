"""
SCANIFY 0DTE Integration Layer & WebSocket Handler Tests
=========================================================

Comprehensive tests covering:

1. Integration layer (ScanifyIntegration, ScanifyConfigAdapter,
   ScanifyDataBridge, ScanifyAlertBridge)
2. API routes (GET/POST endpoints under /api/scanify)
3. WebSocket streaming handler (ScanifyStreamManager)

Uses pytest, httpx (TestClient), and pytest-asyncio.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Patch the broken scanner package __init__.py before any import triggers it.
# The ``src.scanner.__init__`` tries to import ``MTFConfig`` from
# ``src.scanner.mtf_scanner`` which does not exist, causing an ImportError.
# We pre-load ``src.scanner.models`` directly (bypassing __init__) and
# install a lightweight shim so that downstream ``from ..scanner.models``
# style imports resolve correctly.
# ---------------------------------------------------------------------------
import importlib.util
import sys
from unittest.mock import MagicMock as _MagicMock

if "src.scanner" not in sys.modules:
    # 1. Load src.scanner.models directly from file
    _spec = importlib.util.spec_from_file_location(
        "src.scanner.models",
        "src/scanner/models.py",
    )
    _scanner_models = importlib.util.module_from_spec(_spec)
    sys.modules["src.scanner.models"] = _scanner_models
    _spec.loader.exec_module(_scanner_models)

    # 2. Build a thin shim for the scanner package that exposes models + stubs
    _scanner_pkg = _MagicMock()
    _scanner_pkg.__path__ = ["src/scanner"]
    _scanner_pkg.__package__ = "src.scanner"
    _scanner_pkg.__name__ = "src.scanner"
    _scanner_pkg.models = _scanner_models

    # Re-export key names that downstream code expects on the package
    for _attr in dir(_scanner_models):
        if not _attr.startswith("_"):
            setattr(_scanner_pkg, _attr, getattr(_scanner_models, _attr))

    sys.modules["src.scanner"] = _scanner_pkg

# ---------------------------------------------------------------------------

import asyncio
import json
import os
import tempfile
import time
import uuid
from datetime import datetime, date, timezone, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

# -- SCANIFY models --------------------------------------------------------
from src.scanify_0dte.models import (
    CalibrationState,
    DirectionScore,
    GEXProfile,
    GEXSignal,
    GEXSignalType,
    OptionSide,
    PositionType,
    ScanSignal,
    ScanType,
    SessionType,
    StrikeGEX,
    StrikeSelection,
    TimeZoneType,
    TradeDirection,
)

# -- Integration layer under test ------------------------------------------
from src.scanify_0dte.integration import (
    ScanifyAlertBridge,
    ScanifyConfigAdapter,
    ScanifyDataBridge,
    ScanifyIntegration,
)

# -- Engine scanner models -------------------------------------------------
from src.scanner.models import (
    AlertPriority,
    ScanResult,
    SignalDirection,
    TimeFrame,
)

# -- Core config -----------------------------------------------------------
from src.core.config import Config, RiskConfig, set_config

# -- API routes under test -------------------------------------------------
from src.api.routes import scanify as scanify_routes
from src.api.routes.scanify import router as scanify_router

# -- API auth helpers ------------------------------------------------------
from src.api.auth.jwt import (
    SECRET_KEY,
    ALGORITHM,
    User,
    create_access_token,
)
from src.api.auth.tiers import SubscriptionTier

# -- WebSocket handler under test ------------------------------------------
from src.api.websocket.scanify_ws import (
    ALL_CHANNELS,
    CHANNEL_CONFIG,
    ChannelRateLimiter,
    ScanifyChannel,
    ScanifyConnection,
    ScanifyDataProvider,
    ScanifyMessageType,
    ScanifyStreamManager,
    _build_message,
    _serialize,
)


# ===========================================================================
# Shared fixtures
# ===========================================================================


def _make_direction_score(**overrides) -> DirectionScore:
    """Factory for a minimal valid DirectionScore."""
    defaults = dict(
        total_score=55.0,
        market_internals_score=60.0,
        options_flow_score=50.0,
        price_action_score=55.0,
        gex_structure_score=65.0,
        cross_asset_score=45.0,
        factors_agreeing=4,
        has_opposing_factor=True,
        signal=TradeDirection.BULL,
        confidence=72.0,
    )
    defaults.update(overrides)
    return DirectionScore(**defaults)


def _make_strike_selection(**overrides) -> StrikeSelection:
    """Factory for a minimal valid StrikeSelection."""
    defaults = dict(
        strike=5300.0,
        option_type=OptionSide.CALL,
        delta=0.30,
        gamma=0.02,
        theta=-1.50,
        iv=0.18,
        bid=3.20,
        ask=3.60,
        mid=3.40,
        spread_width=0.40,
        oi=5000,
        volume=1200,
        is_liquid=True,
        distance_from_spot=50.0,
        moneyness=1.01,
    )
    defaults.update(overrides)
    return StrikeSelection(**defaults)


def _make_scan_signal(**overrides) -> ScanSignal:
    """Factory for a minimal valid ScanSignal."""
    defaults = dict(
        scan_type=ScanType.DIRECTIONAL,
        direction=TradeDirection.BULL,
        strike_selection=_make_strike_selection(),
        direction_score=_make_direction_score(),
        entry_price=5250.0,
        stop_loss=5220.0,
        profit_target=5310.0,
        position_type=PositionType.SINGLE_LONG,
        contracts=2,
        max_risk=600.0,
        expected_reward=1200.0,
        risk_reward_ratio=2.0,
        time_zone=TimeZoneType.MORNING_SESSION,
        session_type=SessionType.TRENDING,
        metadata={"extra": "info"},
    )
    defaults.update(overrides)
    return ScanSignal(**defaults)


def _make_gex_signal(**overrides) -> GEXSignal:
    """Factory for a minimal valid GEXSignal."""
    defaults = dict(
        signal_type=GEXSignalType.GAMMA_FLIP_CROSSOVER,
        direction=TradeDirection.BULL,
        confidence=80.0,
        description="SPX crossed above gamma flip at 5250",
        trigger_price=5250.0,
        target_price=5300.0,
        metadata={"gex_extra": "data"},
    )
    defaults.update(overrides)
    return GEXSignal(**defaults)


def _make_gex_profile(**overrides) -> GEXProfile:
    """Factory for a minimal valid GEXProfile."""
    defaults = dict(
        total_net_gex=1_500_000.0,
        gamma_flip_level=5250.0,
        call_wall=5350.0,
        put_wall=5150.0,
        max_pain=5250.0,
        plus_gex=5300.0,
        minus_gex=5200.0,
        transition_zone_upper=5280.0,
        transition_zone_lower=5220.0,
        vol_trigger=5260.0,
        strikes=[],
    )
    defaults.update(overrides)
    return GEXProfile(**defaults)


@pytest.fixture
def config():
    """Return a fresh Config with default values for tests."""
    cfg = Config()
    set_config(cfg)
    return cfg


@pytest.fixture
def integration(config):
    """Return a fresh ScanifyIntegration instance."""
    return ScanifyIntegration(config=config)


@pytest.fixture
def scan_signal():
    return _make_scan_signal()


@pytest.fixture
def gex_signal():
    return _make_gex_signal()


@pytest.fixture
def gex_profile():
    return _make_gex_profile()


# ===========================================================================
# 1. INTEGRATION LAYER TESTS
# ===========================================================================


class TestScanifyIntegrationSignalConversion:
    """Tests for ScanifyIntegration.convert_signal_to_scan_result."""

    def test_converts_scan_signal_to_scan_result(self, integration, scan_signal):
        """ScanSignal should be converted to a ScanResult with correct fields."""
        result = integration.convert_signal_to_scan_result(scan_signal)

        assert isinstance(result, ScanResult)
        assert result.symbol == "SPX"
        assert result.scanner_type == "scanify_0dte_directional"
        assert result.direction == SignalDirection.LONG
        assert result.confidence == 72.0
        assert result.entry_price == 5250.0
        assert result.stop_loss == 5220.0
        assert result.targets == [5310.0]
        assert result.risk_reward == 2.0

    def test_direction_mapping_bull(self, integration):
        sig = _make_scan_signal(direction=TradeDirection.BULL)
        result = integration.convert_signal_to_scan_result(sig)
        assert result.direction == SignalDirection.LONG

    def test_direction_mapping_bear(self, integration):
        sig = _make_scan_signal(direction=TradeDirection.BEAR)
        result = integration.convert_signal_to_scan_result(sig)
        assert result.direction == SignalDirection.SHORT

    def test_direction_mapping_neutral(self, integration):
        sig = _make_scan_signal(
            direction=TradeDirection.NEUTRAL,
            direction_score=_make_direction_score(
                signal=TradeDirection.NEUTRAL, total_score=5.0
            ),
        )
        result = integration.convert_signal_to_scan_result(sig)
        assert result.direction == SignalDirection.NEUTRAL

    def test_scan_type_label_mapping(self, integration):
        for scan_type, expected_label in [
            (ScanType.DIRECTIONAL, "scanify_0dte_directional"),
            (ScanType.PREMIUM_SELL, "scanify_0dte_premium"),
            (ScanType.GAMMA_SCALP, "scanify_0dte_gamma_scalp"),
        ]:
            sig = _make_scan_signal(scan_type=scan_type)
            result = integration.convert_signal_to_scan_result(sig)
            assert result.scanner_type == expected_label

    def test_timezone_to_timeframe_mapping(self, integration):
        sig = _make_scan_signal(time_zone=TimeZoneType.POWER_HOUR)
        result = integration.convert_signal_to_scan_result(sig)
        assert result.timeframe == TimeFrame.M1

        sig2 = _make_scan_signal(time_zone=TimeZoneType.MIDDAY_LULL)
        result2 = integration.convert_signal_to_scan_result(sig2)
        assert result2.timeframe == TimeFrame.M15

    def test_metadata_includes_scanify_fields(self, integration, scan_signal):
        result = integration.convert_signal_to_scan_result(scan_signal)
        md = result.metadata

        assert md["scanify_scan_type"] == "DIRECTIONAL"
        assert md["scanify_session_type"] == "TRENDING"
        assert md["scanify_time_zone"] == "MORNING_SESSION"
        assert md["scanify_contracts"] == 2
        assert md["scanify_max_risk"] == 600.0
        assert md["scanify_direction_score"] == 55.0
        assert md["scanify_factors_agreeing"] == 4
        assert md["scanify_confidence"] == 72.0

    def test_metadata_includes_strike_selection_details(self, integration, scan_signal):
        result = integration.convert_signal_to_scan_result(scan_signal)
        md = result.metadata

        assert md["strike"] == 5300.0
        assert md["option_type"] == "CALL"
        assert md["delta"] == 0.30
        assert md["gamma"] == 0.02
        assert md["iv"] == 0.18
        assert md["is_liquid"] is True

    def test_metadata_merges_signal_extra_metadata(self, integration, scan_signal):
        result = integration.convert_signal_to_scan_result(scan_signal)
        assert result.metadata["extra"] == "info"

    def test_signal_without_strike_selection(self, integration):
        sig = _make_scan_signal(strike_selection=None)
        result = integration.convert_signal_to_scan_result(sig)

        assert isinstance(result, ScanResult)
        assert "strike" not in result.metadata

    def test_conversion_count_increments(self, integration, scan_signal):
        assert integration.stats["conversion_count"] == 0

        integration.convert_signal_to_scan_result(scan_signal)
        assert integration.stats["conversion_count"] == 1

        integration.convert_signal_to_scan_result(scan_signal)
        assert integration.stats["conversion_count"] == 2


class TestScanifyIntegrationOptionsResult:
    """Tests for ScanifyIntegration.convert_signal_to_options_result."""

    def test_converts_to_options_scan_result(self, integration, scan_signal):
        from src.scanner.models import OptionsScanResult

        result = integration.convert_signal_to_options_result(scan_signal)

        assert isinstance(result, OptionsScanResult)
        assert result.symbol == "SPX"
        assert result.strike == 5300.0
        assert result.option_type == "CALL"
        assert result.greeks["delta"] == 0.30
        assert result.greeks["gamma"] == 0.02
        assert result.greeks["theta"] == -1.50
        assert result.greeks["iv"] == 0.18
        assert result.bid == 3.20
        assert result.ask == 3.60
        assert result.volume == 1200
        assert result.open_interest == 5000
        assert result.underlying_price == 5250.0
        assert result.expiration.date() == date.today()

    def test_options_result_without_strike_selection(self, integration):
        sig = _make_scan_signal(strike_selection=None)
        result = integration.convert_signal_to_options_result(sig)

        assert result.strike == sig.entry_price
        assert result.option_type == "CALL"
        assert result.greeks == {}
        assert result.bid is None


class TestScanifyIntegrationGEXConversion:
    """Tests for ScanifyIntegration.convert_gex_signal_to_scan_result."""

    def test_converts_gex_signal_to_scan_result(self, integration, gex_signal):
        result = integration.convert_gex_signal_to_scan_result(gex_signal)

        assert isinstance(result, ScanResult)
        assert result.symbol == "SPX"
        assert result.scanner_type == "scanify_0dte_gex"
        assert result.direction == SignalDirection.LONG
        assert result.confidence == 80.0
        assert result.entry_price == 5250.0
        assert result.stop_loss is None
        assert result.targets == [5300.0]
        assert result.risk_reward is None
        assert result.timeframe == TimeFrame.M1

    def test_gex_signal_metadata(self, integration, gex_signal):
        result = integration.convert_gex_signal_to_scan_result(gex_signal)
        md = result.metadata

        assert md["gex_signal_type"] == "GAMMA_FLIP_CROSSOVER"
        assert md["gex_trigger_price"] == 5250.0
        assert md["gex_target_price"] == 5300.0
        assert md["gex_description"] == "SPX crossed above gamma flip at 5250"
        assert md["gex_extra"] == "data"

    def test_gex_signal_no_target(self, integration):
        sig = _make_gex_signal(target_price=None)
        result = integration.convert_gex_signal_to_scan_result(sig)
        assert result.targets == []

    def test_gex_signal_bear_direction(self, integration):
        sig = _make_gex_signal(direction=TradeDirection.BEAR)
        result = integration.convert_gex_signal_to_scan_result(sig)
        assert result.direction == SignalDirection.SHORT


class TestScanifyIntegrationEngineRegistration:
    """Tests for ScanifyIntegration.register_with_engine."""

    def test_register_with_register_scanner_interface(self, integration):
        engine = MagicMock()
        engine.register_scanner = MagicMock()

        integration.register_with_engine(engine)

        assert engine.register_scanner.call_count == 4
        assert integration._registered is True

        # Verify the scanner keys
        keys = [call.args[0] for call in engine.register_scanner.call_args_list]
        assert "scanify_0dte_directional" in keys
        assert "scanify_0dte_premium" in keys
        assert "scanify_0dte_gamma_scalp" in keys
        assert "scanify_0dte_gex" in keys

    def test_register_with_add_scanner_interface(self, integration):
        engine = MagicMock(spec=[])
        engine.add_scanner = MagicMock()

        integration.register_with_engine(engine)

        assert engine.add_scanner.call_count == 4
        assert integration._registered is True

    def test_register_with_scanners_dict_interface(self, integration):
        engine = MagicMock(spec=[])
        engine.scanners = {}

        integration.register_with_engine(engine)

        assert len(engine.scanners) == 4
        assert "scanify_0dte_directional" in engine.scanners
        assert integration._registered is True

    def test_register_with_unsupported_engine_raises(self, integration):
        engine = object()
        # Should not raise but should log errors and increment error count
        integration.register_with_engine(engine)
        assert integration._error_count == 4


class TestScanifyIntegrationRiskBudget:
    """Tests for ScanifyIntegration.get_risk_budget_from_manager."""

    def test_strategy1_available_capital(self, integration):
        rm = MagicMock()
        rm.get_available_capital.return_value = 100_000.0

        budget = integration.get_risk_budget_from_manager(rm)

        # max_position_risk_pct default is 0.5, so 100_000 * 0.5 / 100 = 500
        assert budget == 500.0

    def test_strategy2_portfolio_risk(self, integration):
        rm = MagicMock(spec=[])
        rm.portfolio_risk = MagicMock()
        rm.portfolio_risk.total_value = 200_000.0
        rm.portfolio_risk.current_drawdown = 0.0

        budget = integration.get_risk_budget_from_manager(rm)

        # min(max_portfolio_risk_pct/100, max_position_risk_pct/100) = min(0.02, 0.005) = 0.005
        expected = 200_000.0 * 0.005
        assert budget == expected

    def test_strategy2_with_elevated_drawdown(self, integration):
        rm = MagicMock(spec=[])
        rm.portfolio_risk = MagicMock()
        rm.portfolio_risk.total_value = 200_000.0
        rm.portfolio_risk.current_drawdown = 0.10  # 10% drawdown

        budget = integration.get_risk_budget_from_manager(rm)

        base = 200_000.0 * 0.005
        reduction = min(0.10 * 2.0, 0.8)  # 0.2
        expected = base * (1.0 - reduction)
        assert budget == pytest.approx(expected, abs=0.01)

    def test_strategy3_risk_manager_config(self, integration):
        rm = MagicMock(spec=[])
        rm.config = MagicMock()
        rm.config.total_capital = 300_000.0
        rm.config.max_position_risk_pct = 1.0

        budget = integration.get_risk_budget_from_manager(rm)

        assert budget == 3000.0

    def test_fallback_budget(self, integration):
        rm = object()  # no attributes at all
        budget = integration.get_risk_budget_from_manager(rm)

        # 500_000 * 0.5 / 100 = 2500
        assert budget == 2500.0


class TestScanifyIntegrationExecution:
    """Tests for ScanifyIntegration.send_signal_to_execution."""

    def test_submit_order_interface(self, integration, scan_signal):
        exec_engine = MagicMock()
        exec_engine.submit_order.return_value = {"status": "submitted"}

        result = integration.send_signal_to_execution(scan_signal, exec_engine)

        assert result["status"] == "submitted"
        assert "order_id" in result
        assert "submitted_at" in result
        exec_engine.submit_order.assert_called_once()

    def test_create_order_interface(self, integration, scan_signal):
        exec_engine = MagicMock(spec=[])
        exec_engine.create_order = MagicMock(return_value={"status": "created"})

        result = integration.send_signal_to_execution(scan_signal, exec_engine)
        assert result["status"] == "created"

    def test_place_order_interface(self, integration, scan_signal):
        exec_engine = MagicMock(spec=[])
        exec_engine.place_order = MagicMock(return_value={"status": "placed"})

        result = integration.send_signal_to_execution(scan_signal, exec_engine)
        assert result["status"] == "placed"

    def test_unsupported_execution_engine(self, integration, scan_signal):
        exec_engine = object()
        result = integration.send_signal_to_execution(scan_signal, exec_engine)
        assert result["status"] == "unsupported"
        assert result["error"] is not None

    def test_execution_error_handling(self, integration, scan_signal):
        exec_engine = MagicMock()
        exec_engine.submit_order.side_effect = RuntimeError("Connection lost")

        result = integration.send_signal_to_execution(scan_signal, exec_engine)
        assert result["status"] == "error"
        assert "Connection lost" in result["error"]
        assert integration._error_count == 1


# ---------------------------------------------------------------------------
# ScanifyConfigAdapter tests
# ---------------------------------------------------------------------------


class TestScanifyConfigAdapter:
    """Tests for ScanifyConfigAdapter."""

    def test_load_from_yaml_with_real_file(self, tmp_path):
        config_data = {
            "scanner": {"min_confidence": 70.0},
            "risk": {"max_daily_loss_pct": 3.0},
            "api": {"primary_data_provider": "alpaca"},
            "scanify_0dte": {
                "enabled": True,
                "data_provider": "alpaca",
                "risk_budget": 15_000.0,
                "max_daily_trades": 25,
            },
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_data))

        adapter = ScanifyConfigAdapter(str(config_file))
        result = adapter.load_from_yaml()

        assert result["scanify_0dte"]["enabled"] is True
        assert result["scanify_0dte"]["data_provider"] == "alpaca"
        assert result["scanify_0dte"]["risk_budget"] == 15_000.0
        assert result["scanify_0dte"]["max_daily_trades"] == 25

    def test_load_from_yaml_missing_file_uses_defaults(self, tmp_path):
        adapter = ScanifyConfigAdapter(str(tmp_path / "nonexistent.yaml"))
        result = adapter.load_from_yaml()

        assert result["scanify_0dte"]["enabled"] is True
        assert result["scanify_0dte"]["risk_budget"] == 10_000.0
        assert result["scanify_0dte"]["paper_trade"] is True

    def test_defaults_merged_for_missing_keys(self, tmp_path):
        config_data = {
            "scanify_0dte": {"enabled": False},
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_data))

        adapter = ScanifyConfigAdapter(str(config_file))
        result = adapter.load_from_yaml()

        assert result["scanify_0dte"]["enabled"] is False
        assert result["scanify_0dte"]["risk_budget"] == 10_000.0
        assert result["scanify_0dte"]["max_daily_trades"] == 20

    def test_get_scanner_config(self, tmp_path):
        config_data = {
            "scanner": {"min_confidence": 75.0},
            "scanify_0dte": {"min_confidence": 65.0, "scan_interval_directional": 120},
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_data))

        adapter = ScanifyConfigAdapter(str(config_file))
        scanner_cfg = adapter.get_scanner_config()

        assert "scanify_0dte" in scanner_cfg
        assert scanner_cfg["min_confidence"] == 75.0  # from base scanner section
        assert scanner_cfg["scanify_0dte"]["min_confidence"] == 65.0

    def test_get_risk_config(self, tmp_path):
        config_data = {
            "risk": {"max_daily_loss_pct": 5.0},
            "scanify_0dte": {"risk_budget": 20_000.0, "max_daily_trades": 30},
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_data))

        adapter = ScanifyConfigAdapter(str(config_file))
        risk_cfg = adapter.get_risk_config()

        assert risk_cfg["scanify_risk_budget"] == 20_000.0
        assert risk_cfg["scanify_max_daily_trades"] == 30
        assert risk_cfg["max_daily_loss_pct"] == 5.0

    def test_get_data_config(self, tmp_path):
        config_data = {
            "api": {"primary_data_provider": "polygon"},
            "scanify_0dte": {"data_provider": "alpaca", "paper_trade": False},
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_data))

        adapter = ScanifyConfigAdapter(str(config_file))
        data_cfg = adapter.get_data_config()

        assert data_cfg["scanify_data_provider"] == "alpaca"
        assert data_cfg["scanify_paper_trade"] is False

    def test_auto_loads_on_first_access(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({"scanify_0dte": {"enabled": True}}))

        adapter = ScanifyConfigAdapter(str(config_file))
        assert adapter._loaded is False

        # Calling get_scanner_config auto-loads
        adapter.get_scanner_config()
        assert adapter._loaded is True


# ---------------------------------------------------------------------------
# ScanifyDataBridge tests
# ---------------------------------------------------------------------------


class TestScanifyDataBridge:
    """Tests for ScanifyDataBridge."""

    def test_create_from_existing_adapter_vendor_attr(self, config):
        bridge = ScanifyDataBridge(config=config)

        adapter = MagicMock()
        adapter.vendor = "polygon"
        adapter.api_key = "test_key_123"

        with patch("src.scanify_0dte.integration.DataFeedManager") as MockFeed:
            mock_feed = MagicMock()
            MockFeed.return_value = mock_feed

            result = bridge.create_from_existing_adapter(adapter)

            MockFeed.assert_called_once_with(
                data_provider="polygon",
                api_key="test_key_123",
            )
            assert result is mock_feed

    def test_create_from_existing_adapter_vendor_enum(self, config):
        bridge = ScanifyDataBridge(config=config)

        class FakeVendor:
            value = "alpaca"

        adapter = MagicMock()
        adapter.vendor = FakeVendor()
        adapter.api_key = "alpaca_key"

        with patch("src.scanify_0dte.integration.DataFeedManager") as MockFeed:
            bridge.create_from_existing_adapter(adapter)
            MockFeed.assert_called_once_with(
                data_provider="alpaca",
                api_key="alpaca_key",
            )

    def test_create_from_adapter_config_dict(self, config):
        bridge = ScanifyDataBridge(config=config)

        adapter = MagicMock(spec=[])
        adapter.config = {"api_key": "from_config"}

        with patch("src.scanify_0dte.integration.DataFeedManager") as MockFeed:
            bridge.create_from_existing_adapter(adapter)
            call_kwargs = MockFeed.call_args
            assert call_kwargs[1]["api_key"] == "from_config"

    def test_shared_symbols_initially_empty(self, config):
        bridge = ScanifyDataBridge(config=config)
        assert bridge.shared_symbols == []

    def test_share_market_data_via_on_data(self, config):
        bridge = ScanifyDataBridge(config=config)

        existing_feed = MagicMock()
        scanify_feed = MagicMock(spec=["_latest_data"])
        scanify_feed._latest_data = {}

        bridge.share_market_data(existing_feed, scanify_feed)

        # Verify on_data was registered
        existing_feed.on_data.assert_called_once()

        # Simulate a data callback
        callback = existing_feed.on_data.call_args[0][0]
        data = MagicMock()
        data.symbol = "SPX"
        callback(data)

        assert "SPX" in bridge.shared_symbols
        assert scanify_feed._latest_data["SPX"] is data

    def test_share_market_data_filters_non_scanify_symbols(self, config):
        bridge = ScanifyDataBridge(config=config)

        existing_feed = MagicMock()
        scanify_feed = MagicMock(spec=["_latest_data"])
        scanify_feed._latest_data = {}

        bridge.share_market_data(existing_feed, scanify_feed)
        callback = existing_feed.on_data.call_args[0][0]

        # Non-SCANIFY symbol should be ignored
        data = MagicMock()
        data.symbol = "AAPL"
        callback(data)

        assert "AAPL" not in bridge.shared_symbols


# ---------------------------------------------------------------------------
# ScanifyAlertBridge tests
# ---------------------------------------------------------------------------


class TestScanifyAlertBridge:
    """Tests for ScanifyAlertBridge."""

    def test_convert_alert_basic(self):
        bridge = ScanifyAlertBridge()
        alert = {
            "type": "SIGNAL",
            "level": "SIGNAL",
            "message": "New directional signal detected",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        result = bridge.convert_alert(alert)

        assert "alert_id" in result
        assert result["priority"] == AlertPriority.HIGH
        assert "[SCANIFY 0DTE]" in result["message"]
        assert result["source"] == "scanify_0dte"
        assert result["acknowledged"] is False
        assert "expires_at" in result

    def test_convert_alert_priority_mapping(self):
        bridge = ScanifyAlertBridge()

        mapping = {
            "INFO": AlertPriority.LOW,
            "WARNING": AlertPriority.MEDIUM,
            "SIGNAL": AlertPriority.HIGH,
            "CRITICAL": AlertPriority.CRITICAL,
            "GEX": AlertPriority.HIGH,
            "EXIT": AlertPriority.HIGH,
            "RISK": AlertPriority.CRITICAL,
            "PHASE": AlertPriority.LOW,
        }

        for level, expected_priority in mapping.items():
            alert = {"type": level, "level": level, "message": f"Test {level}"}
            result = bridge.convert_alert(alert)
            assert result["priority"] == expected_priority, f"Failed for level={level}"

    def test_convert_alert_with_signal_attachment(self):
        bridge = ScanifyAlertBridge()
        alert = {
            "type": "SIGNAL",
            "message": "Signal with attachment",
            "signal": {"confidence": 85.0},
        }

        result = bridge.convert_alert(alert)
        assert result["scan_result"] is not None
        assert result["scan_result"]["confidence"] == 85.0

    def test_convert_alert_with_datetime_timestamp(self):
        bridge = ScanifyAlertBridge()
        ts = datetime(2025, 3, 15, 14, 30, tzinfo=timezone.utc)
        alert = {"type": "INFO", "message": "test", "timestamp": ts}

        result = bridge.convert_alert(alert)
        assert result["created_at"] == ts

    def test_convert_alert_with_invalid_timestamp_string(self):
        bridge = ScanifyAlertBridge()
        alert = {"type": "INFO", "message": "test", "timestamp": "not-a-date"}

        result = bridge.convert_alert(alert)
        assert isinstance(result["created_at"], datetime)

    def test_send_to_alert_system_add_alert(self):
        bridge = ScanifyAlertBridge()
        alert = {"message": "test alert"}

        manager = MagicMock()
        manager.add_alert = MagicMock()

        bridge.send_to_alert_system(alert, manager)
        manager.add_alert.assert_called_once_with(alert)

    def test_send_to_alert_system_alerts_list_fallback(self):
        bridge = ScanifyAlertBridge()
        alert = {"message": "test alert"}

        manager = MagicMock(spec=[])
        manager.alerts = []

        bridge.send_to_alert_system(alert, manager)
        assert alert in manager.alerts

    def test_create_webhook_payload_scan_signal(self):
        bridge = ScanifyAlertBridge()
        sig = _make_scan_signal()

        payload = bridge.create_webhook_payload(sig)

        assert payload["event"] == "scanify_0dte_signal"
        assert payload["source"] == "scanify_0dte"
        assert "timestamp" in payload
        assert payload["data"]["scan_type"] == "DIRECTIONAL"
        assert payload["data"]["direction"] == "BULL"
        assert payload["data"]["entry_price"] == 5250.0
        assert payload["data"]["confidence"] == 72.0
        assert payload["data"]["strike"] == 5300.0
        assert payload["data"]["option_type"] == "CALL"

    def test_create_webhook_payload_gex_signal(self):
        bridge = ScanifyAlertBridge()
        sig = _make_gex_signal()

        payload = bridge.create_webhook_payload(sig)

        assert payload["event"] == "scanify_0dte_gex_signal"
        assert payload["data"]["signal_type"] == "GAMMA_FLIP_CROSSOVER"
        assert payload["data"]["confidence"] == 80.0

    def test_create_webhook_payload_dict(self):
        bridge = ScanifyAlertBridge()
        raw = {"custom": "data", "value": 42}

        payload = bridge.create_webhook_payload(raw)

        assert payload["event"] == "scanify_0dte_raw"
        assert payload["data"]["custom"] == "data"

    def test_webhook_count_increments(self):
        bridge = ScanifyAlertBridge()
        assert bridge.stats["webhooks_created"] == 0

        bridge.create_webhook_payload(_make_scan_signal())
        assert bridge.stats["webhooks_created"] == 1

    def test_alert_count_increments(self):
        bridge = ScanifyAlertBridge()
        assert bridge.stats["alerts_converted"] == 0

        bridge.convert_alert({"type": "INFO", "message": "test"})
        assert bridge.stats["alerts_converted"] == 1


# ===========================================================================
# 2. API ROUTE TESTS
# ===========================================================================


def _create_test_token(tier: SubscriptionTier = SubscriptionTier.PRO) -> str:
    """Create a valid JWT token for test requests."""
    return create_access_token(
        user_id="test-user-123",
        email="test@example.com",
        tier=tier,
    )


def _make_mock_orchestrator(**overrides) -> MagicMock:
    """Create a mock orchestrator with sensible defaults."""
    orch = MagicMock()
    orch.is_running = overrides.get("is_running", True)
    orch.scan_count = overrides.get("scan_count", 10)
    orch.paper_trade = overrides.get("paper_trade", True)
    orch.active_signals = overrides.get("active_signals", [])
    orch.gex_signals = overrides.get("gex_signals", [])
    orch.current_gex = overrides.get("current_gex", None)
    orch.session_setup = overrides.get("session_setup", None)
    orch._active_positions = overrides.get("active_positions", [])
    orch._closed_positions = overrides.get("closed_positions", [])
    orch._daily_pnl = overrides.get("daily_pnl", 0.0)
    orch._intraday_pnl_curve = overrides.get("pnl_curve", [])
    orch._calibration_state = overrides.get("calibration_state", None)
    orch._gex_history = overrides.get("gex_history", [])

    orch.get_status = MagicMock(return_value={
        "is_running": orch.is_running,
        "session_type": "TRENDING",
        "time_zone": "MORNING_SESSION",
        "scan_count": orch.scan_count,
        "last_scan_time": None,
        "active_positions": len(orch._active_positions),
        "total_pnl": 150.0,
        "realized_pnl": 100.0,
        "unrealized_pnl": 50.0,
        "paper_trade": True,
        "data_connected": True,
        "risk_budget_remaining": 8000.0,
        "minutes_remaining": 120,
        "recent_alerts": [],
    })

    orch.get_dashboard_data = MagicMock(return_value={
        "spx_price": 5250.0,
        "status": {
            "is_running": True,
            "session_type": "TRENDING",
            "time_zone": "MORNING_SESSION",
            "scan_count": 10,
            "active_positions": 0,
            "total_pnl": 0.0,
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "paper_trade": True,
            "data_connected": True,
            "risk_budget_remaining": 10000.0,
            "minutes_remaining": 120,
        },
        "expected_move": {},
        "gex_profile": {},
        "key_levels": {},
        "active_positions": [],
        "direction_score": {},
        "recent_signals": [],
        "gex_signals": [],
        "intraday_pnl_curve": [],
        "session_classification": {},
    })

    orch.alerts = overrides.get("alerts", [])
    orch.initialize = AsyncMock()
    orch.shutdown = AsyncMock()

    return orch


@pytest.fixture
def app_with_routes():
    """Create a FastAPI app with scanify routes and a mock orchestrator."""
    app = FastAPI()
    app.include_router(scanify_router)
    return app


@pytest.fixture
def mock_orchestrator():
    return _make_mock_orchestrator()


@pytest.fixture
def authed_client(app_with_routes, mock_orchestrator):
    """Return a TestClient with auth overrides and mock orchestrator set."""
    # Set orchestrator at module level
    scanify_routes._orchestrator = mock_orchestrator

    token = _create_test_token(SubscriptionTier.PRO)

    client = TestClient(app_with_routes)
    client.headers = {"Authorization": f"Bearer {token}"}

    yield client

    # Cleanup
    scanify_routes._orchestrator = None


class TestScanifyStatusEndpoint:
    """Tests for GET /api/scanify/status."""

    def test_status_returns_valid_response(self, authed_client, mock_orchestrator):
        resp = authed_client.get("/api/scanify/status")
        assert resp.status_code == 200

        data = resp.json()
        assert data["is_running"] is True
        assert data["session_type"] == "TRENDING"
        assert data["scan_count"] == 10
        assert data["paper_trade"] is True
        assert data["data_connected"] is True

    def test_status_returns_503_when_no_orchestrator(self, app_with_routes):
        scanify_routes._orchestrator = None
        token = _create_test_token()

        client = TestClient(app_with_routes)
        resp = client.get(
            "/api/scanify/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 503

    def test_status_requires_authentication(self, app_with_routes, mock_orchestrator):
        scanify_routes._orchestrator = mock_orchestrator
        client = TestClient(app_with_routes)
        resp = client.get("/api/scanify/status")
        assert resp.status_code in (401, 403)
        scanify_routes._orchestrator = None


class TestGEXProfileEndpoint:
    """Tests for GET /api/scanify/gex/profile."""

    def test_gex_profile_returns_data(self, authed_client, mock_orchestrator):
        mock_orchestrator.current_gex = _make_gex_profile()

        resp = authed_client.get("/api/scanify/gex/profile")
        assert resp.status_code == 200

        data = resp.json()
        assert data["total_net_gex"] == 1_500_000.0
        assert data["gamma_flip_level"] == 5250.0
        assert data["call_wall"] == 5350.0
        assert data["put_wall"] == 5150.0

    def test_gex_profile_returns_404_when_none(self, authed_client, mock_orchestrator):
        mock_orchestrator.current_gex = None
        resp = authed_client.get("/api/scanify/gex/profile")
        assert resp.status_code == 404


class TestGEXLevelsEndpoint:
    """Tests for GET /api/scanify/gex/levels."""

    def test_gex_levels_returns_key_levels(self, authed_client, mock_orchestrator):
        mock_orchestrator.current_gex = _make_gex_profile()

        resp = authed_client.get("/api/scanify/gex/levels")
        assert resp.status_code == 200

        data = resp.json()
        assert data["gamma_flip"] == 5250.0
        assert data["call_wall"] == 5350.0
        assert data["put_wall"] == 5150.0
        assert data["max_pain"] == 5250.0
        assert data["vol_trigger"] == 5260.0
        assert "is_positive_gamma_regime" in data

    def test_gex_levels_returns_404_when_no_gex(self, authed_client, mock_orchestrator):
        mock_orchestrator.current_gex = None
        resp = authed_client.get("/api/scanify/gex/levels")
        assert resp.status_code == 404


class TestSignalsEndpoint:
    """Tests for GET /api/scanify/signals."""

    def test_signals_returns_empty_list(self, authed_client, mock_orchestrator):
        mock_orchestrator.active_signals = []

        resp = authed_client.get("/api/scanify/signals")
        assert resp.status_code == 200

        data = resp.json()
        assert data["total"] == 0
        assert data["signals"] == []

    def test_signals_returns_active_signals(self, authed_client, mock_orchestrator):
        mock_orchestrator.active_signals = [_make_scan_signal()]

        resp = authed_client.get("/api/scanify/signals")
        assert resp.status_code == 200

        data = resp.json()
        assert data["total"] == 1
        assert data["signals"][0]["scan_type"] == "DIRECTIONAL"
        assert data["signals"][0]["direction"] == "BULL"
        assert data["signals"][0]["entry_price"] == 5250.0


class TestPositionsEndpoint:
    """Tests for GET /api/scanify/positions."""

    def test_positions_returns_empty_list(self, authed_client, mock_orchestrator):
        resp = authed_client.get("/api/scanify/positions")
        assert resp.status_code == 200

        data = resp.json()
        assert data["total"] == 0
        assert data["positions"] == []

    def test_positions_returns_active_positions(self, authed_client, mock_orchestrator):
        mock_orchestrator._active_positions = [
            {
                "signal_id": "pos-001",
                "direction": "BULL",
                "strategy": "DIRECTIONAL",
                "entry_price": 5250.0,
                "stop_loss": 5220.0,
                "take_profit": 5300.0,
                "size": 2,
                "pnl": 150.0,
                "max_pnl": 200.0,
                "entry_time": "2025-03-15T14:30:00",
                "status": "OPEN",
                "paper_trade": True,
            }
        ]

        resp = authed_client.get("/api/scanify/positions")
        assert resp.status_code == 200

        data = resp.json()
        assert data["total"] == 1
        assert data["positions"][0]["signal_id"] == "pos-001"
        assert data["total_unrealized_pnl"] == 150.0


class TestPnLEndpoint:
    """Tests for GET /api/scanify/pnl."""

    def test_pnl_returns_summary(self, authed_client, mock_orchestrator):
        mock_orchestrator._closed_positions = [
            {"pnl": 200.0, "strategy": "DIRECTIONAL"},
            {"pnl": -50.0, "strategy": "PREMIUM_SELL"},
            {"pnl": 100.0, "strategy": "DIRECTIONAL"},
        ]
        mock_orchestrator._active_positions = [
            {"pnl": 30.0},
        ]

        resp = authed_client.get("/api/scanify/pnl")
        assert resp.status_code == 200

        data = resp.json()
        assert data["total_trades"] == 3
        assert data["winning_trades"] == 2
        assert data["losing_trades"] == 1
        assert data["realized_pnl"] == 250.0
        assert data["unrealized_pnl"] == 30.0
        assert data["total_pnl"] == 280.0
        assert data["win_rate"] == pytest.approx(2 / 3, abs=0.01)

    def test_pnl_zero_trades(self, authed_client, mock_orchestrator):
        mock_orchestrator._closed_positions = []
        mock_orchestrator._active_positions = []

        resp = authed_client.get("/api/scanify/pnl")
        assert resp.status_code == 200

        data = resp.json()
        assert data["total_trades"] == 0
        assert data["win_rate"] == 0.0


class TestDashboardEndpoint:
    """Tests for GET /api/scanify/dashboard."""

    def test_dashboard_returns_complete_data(self, authed_client, mock_orchestrator):
        resp = authed_client.get("/api/scanify/dashboard")
        assert resp.status_code == 200

        data = resp.json()
        assert data["spx_price"] == 5250.0
        assert "status" in data
        assert data["status"]["is_running"] is True
        assert "expected_move" in data
        assert "gex_profile" in data
        assert "active_positions" in data
        assert "intraday_pnl_curve" in data


class TestStartStopEndpoints:
    """Tests for POST /api/scanify/start and /api/scanify/stop."""

    def test_start_scanner(self, authed_client, mock_orchestrator):
        mock_orchestrator.is_running = False

        resp = authed_client.post("/api/scanify/start")
        assert resp.status_code == 200

        data = resp.json()
        assert data["action"] == "start"
        assert data["success"] is True
        mock_orchestrator.initialize.assert_called_once()

    def test_start_scanner_already_running(self, authed_client, mock_orchestrator):
        mock_orchestrator.is_running = True

        resp = authed_client.post("/api/scanify/start")
        assert resp.status_code == 200

        data = resp.json()
        assert data["success"] is False
        assert "already running" in data["message"]

    def test_stop_scanner(self, authed_client, mock_orchestrator):
        mock_orchestrator.is_running = True

        resp = authed_client.post("/api/scanify/stop")
        assert resp.status_code == 200

        data = resp.json()
        assert data["action"] == "stop"
        assert data["success"] is True
        mock_orchestrator.shutdown.assert_called_once()

    def test_stop_scanner_not_running(self, authed_client, mock_orchestrator):
        mock_orchestrator.is_running = False

        resp = authed_client.post("/api/scanify/stop")
        assert resp.status_code == 200

        data = resp.json()
        assert data["success"] is False
        assert "not running" in data["message"]


class TestErrorHandling:
    """Tests for error handling in API routes."""

    def test_invalid_token_returns_401(self, app_with_routes, mock_orchestrator):
        scanify_routes._orchestrator = mock_orchestrator
        client = TestClient(app_with_routes)

        resp = client.get(
            "/api/scanify/status",
            headers={"Authorization": "Bearer invalid-token-garbage"},
        )
        assert resp.status_code == 401
        scanify_routes._orchestrator = None

    def test_insufficient_tier_for_start(self, app_with_routes, mock_orchestrator):
        scanify_routes._orchestrator = mock_orchestrator
        token = _create_test_token(SubscriptionTier.BASIC)

        client = TestClient(app_with_routes)
        resp = client.post(
            "/api/scanify/start",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403
        scanify_routes._orchestrator = None

    def test_orchestrator_error_returns_500(self, authed_client, mock_orchestrator):
        mock_orchestrator.get_status.side_effect = RuntimeError("Internal error")

        resp = authed_client.get("/api/scanify/status")
        assert resp.status_code == 500

    def test_health_check_no_auth_required(self, app_with_routes):
        scanify_routes._orchestrator = None
        client = TestClient(app_with_routes)

        resp = client.get("/api/scanify/health")
        assert resp.status_code == 200

        data = resp.json()
        assert data["status"] == "down"
        assert data["is_running"] is False


# ===========================================================================
# 3. WEBSOCKET TESTS
# ===========================================================================


class TestChannelRateLimiter:
    """Tests for the token-bucket rate limiter."""

    def test_allows_up_to_max_tokens(self):
        limiter = ChannelRateLimiter(max_per_minute=5)

        for _ in range(5):
            assert limiter.consume() is True

        assert limiter.consume() is False

    def test_refills_over_time(self):
        limiter = ChannelRateLimiter(max_per_minute=60)

        # Consume all tokens
        for _ in range(60):
            limiter.consume()

        assert limiter.consume() is False

        # Simulate 1 second passing (should refill 1 token)
        limiter.last_refill -= 1.0
        assert limiter.consume() is True


class TestScanifyConnectionModel:
    """Tests for the ScanifyConnection dataclass."""

    def test_init_rate_limiters(self):
        conn = ScanifyConnection()
        conn.init_rate_limiters()

        for ch in ScanifyChannel:
            assert ch.value in conn.rate_limiters
            assert isinstance(conn.rate_limiters[ch.value], ChannelRateLimiter)

    def test_next_sequence_increments(self):
        conn = ScanifyConnection()
        assert conn.next_sequence() == 1
        assert conn.next_sequence() == 2
        assert conn.next_sequence() == 3


class TestSerializationHelpers:
    """Tests for _serialize and _build_message helpers."""

    def test_serialize_pydantic_model(self):
        gex = _make_gex_signal()
        result = _serialize(gex)
        assert isinstance(result, dict)
        assert result["signal_type"] == "GAMMA_FLIP_CROSSOVER"

    def test_serialize_enum(self):
        assert _serialize(TradeDirection.BULL) == "BULL"
        assert _serialize(ScanifyChannel.GEX_PROFILE) == "gex_profile"

    def test_serialize_datetime(self):
        dt = datetime(2025, 3, 15, 14, 30, tzinfo=timezone.utc)
        result = _serialize(dt)
        assert "2025-03-15" in result

    def test_serialize_none(self):
        assert _serialize(None) is None

    def test_serialize_primitives(self):
        assert _serialize(42) == 42
        assert _serialize(3.14) == 3.14
        assert _serialize("hello") == "hello"
        assert _serialize(True) is True

    def test_serialize_dict(self):
        result = _serialize({"key": TradeDirection.BULL})
        assert result["key"] == "BULL"

    def test_serialize_list(self):
        result = _serialize([1, TradeDirection.BEAR, "three"])
        assert result == [1, "BEAR", "three"]

    def test_build_message_format(self):
        msg = _build_message(
            channel="gex_profile",
            data={"test": "data"},
            sequence=42,
        )

        assert msg["type"] == "data"
        assert msg["channel"] == "gex_profile"
        assert msg["sequence"] == 42
        assert "timestamp" in msg
        assert msg["data"]["test"] == "data"

    def test_build_message_heartbeat_type(self):
        msg = _build_message(
            channel="_system",
            data={"pong": True},
            sequence=1,
            msg_type=ScanifyMessageType.HEARTBEAT,
        )
        assert msg["type"] == "heartbeat"


class TestScanifyStreamManagerSubscription:
    """Tests for ScanifyStreamManager subscription management."""

    def test_subscribe_to_valid_channels(self):
        manager = ScanifyStreamManager()

        conn = ScanifyConnection(
            tier=SubscriptionTier.PRO,
        )
        conn.init_rate_limiters()

        result = manager._subscribe(conn, ["gex_profile", "scan_signals"])

        assert "gex_profile" in result["subscribed"]
        assert "scan_signals" in result["subscribed"]
        assert len(result["errors"]) == 0
        assert "gex_profile" in conn.subscriptions
        assert conn.connection_id in manager._channel_subscribers["gex_profile"]

    def test_subscribe_to_unknown_channel(self):
        manager = ScanifyStreamManager()

        conn = ScanifyConnection(tier=SubscriptionTier.PRO)
        conn.init_rate_limiters()

        result = manager._subscribe(conn, ["nonexistent_channel"])

        assert len(result["subscribed"]) == 0
        assert len(result["errors"]) == 1
        assert result["errors"][0]["error"] == "unknown_channel"

    def test_unsubscribe_from_channels(self):
        manager = ScanifyStreamManager()

        conn = ScanifyConnection(tier=SubscriptionTier.PRO)
        conn.init_rate_limiters()

        manager._subscribe(conn, ["gex_profile", "scan_signals"])
        result = manager._unsubscribe(conn, ["gex_profile"])

        assert "gex_profile" in result["unsubscribed"]
        assert "gex_profile" not in conn.subscriptions
        assert "scan_signals" in conn.subscriptions

    def test_unsubscribe_from_non_subscribed_channel(self):
        manager = ScanifyStreamManager()

        conn = ScanifyConnection(tier=SubscriptionTier.PRO)
        conn.init_rate_limiters()

        result = manager._unsubscribe(conn, ["gex_profile"])
        assert result["unsubscribed"] == []


class TestScanifyStreamManagerMessageHandling:
    """Tests for ScanifyStreamManager.handle_message (async)."""

    @pytest.mark.asyncio
    async def test_handle_subscribe_message(self):
        manager = ScanifyStreamManager()

        ws = AsyncMock()
        conn = ScanifyConnection(
            websocket=ws,
            tier=SubscriptionTier.PRO,
        )
        conn.init_rate_limiters()
        manager._connections[conn.connection_id] = conn

        message = json.dumps({
            "action": "subscribe",
            "channels": ["gex_profile", "dashboard"],
        })

        await manager.handle_message(conn, message)

        assert "gex_profile" in conn.subscriptions
        assert "dashboard" in conn.subscriptions
        # Should have sent an ACK
        ws.send_json.assert_called()
        sent = ws.send_json.call_args[0][0]
        assert sent["type"] == "ack"

    @pytest.mark.asyncio
    async def test_handle_unsubscribe_message(self):
        manager = ScanifyStreamManager()

        ws = AsyncMock()
        conn = ScanifyConnection(
            websocket=ws,
            tier=SubscriptionTier.PRO,
        )
        conn.init_rate_limiters()
        manager._connections[conn.connection_id] = conn

        manager._subscribe(conn, ["gex_profile", "dashboard"])

        message = json.dumps({
            "action": "unsubscribe",
            "channels": ["gex_profile"],
        })

        await manager.handle_message(conn, message)

        assert "gex_profile" not in conn.subscriptions
        assert "dashboard" in conn.subscriptions

    @pytest.mark.asyncio
    async def test_handle_ping_message(self):
        manager = ScanifyStreamManager()

        ws = AsyncMock()
        conn = ScanifyConnection(
            websocket=ws,
            tier=SubscriptionTier.PRO,
        )
        conn.init_rate_limiters()
        manager._connections[conn.connection_id] = conn

        before = conn.last_heartbeat
        message = json.dumps({"action": "ping"})

        await manager.handle_message(conn, message)

        # Last heartbeat should be updated
        assert conn.last_heartbeat >= before
        # Should send heartbeat response
        ws.send_json.assert_called()
        sent = ws.send_json.call_args[0][0]
        assert sent["type"] == "heartbeat"
        assert sent["data"]["pong"] is True

    @pytest.mark.asyncio
    async def test_handle_invalid_json(self):
        manager = ScanifyStreamManager()

        ws = AsyncMock()
        conn = ScanifyConnection(
            websocket=ws,
            tier=SubscriptionTier.PRO,
        )
        conn.init_rate_limiters()
        manager._connections[conn.connection_id] = conn

        await manager.handle_message(conn, "not valid json {{{")

        ws.send_json.assert_called()
        sent = ws.send_json.call_args[0][0]
        assert sent["type"] == "error"
        assert sent["data"]["error"] == "invalid_json"

    @pytest.mark.asyncio
    async def test_handle_unknown_action(self):
        manager = ScanifyStreamManager()

        ws = AsyncMock()
        conn = ScanifyConnection(
            websocket=ws,
            tier=SubscriptionTier.PRO,
        )
        conn.init_rate_limiters()
        manager._connections[conn.connection_id] = conn

        message = json.dumps({"action": "foobar"})
        await manager.handle_message(conn, message)

        ws.send_json.assert_called()
        sent = ws.send_json.call_args[0][0]
        assert sent["type"] == "error"
        assert sent["data"]["error"] == "unknown_action"

    @pytest.mark.asyncio
    async def test_handle_shorthand_subscribe(self):
        """Test the flat {"subscribe": [...]} format without action key."""
        manager = ScanifyStreamManager()

        ws = AsyncMock()
        conn = ScanifyConnection(
            websocket=ws,
            tier=SubscriptionTier.PRO,
        )
        conn.init_rate_limiters()
        manager._connections[conn.connection_id] = conn

        message = json.dumps({"subscribe": ["market_data", "alerts"]})
        await manager.handle_message(conn, message)

        assert "market_data" in conn.subscriptions
        assert "alerts" in conn.subscriptions


class TestScanifyStreamManagerMessageFormat:
    """Tests verifying correct JSON message format from the stream manager."""

    @pytest.mark.asyncio
    async def test_message_has_required_fields(self):
        """Every data message must have type, channel, sequence, timestamp, data."""
        manager = ScanifyStreamManager()

        ws = AsyncMock()
        conn = ScanifyConnection(
            websocket=ws,
            tier=SubscriptionTier.PRO,
        )
        conn.init_rate_limiters()
        manager._connections[conn.connection_id] = conn
        manager._subscribe(conn, ["gex_signals"])

        await manager.emit_gex_signal({"test": "signal"})

        ws.send_json.assert_called()
        sent = ws.send_json.call_args[0][0]

        assert "type" in sent
        assert "channel" in sent
        assert "sequence" in sent
        assert "timestamp" in sent
        assert "data" in sent

    @pytest.mark.asyncio
    async def test_message_timestamp_is_iso_format(self):
        manager = ScanifyStreamManager()

        ws = AsyncMock()
        conn = ScanifyConnection(
            websocket=ws,
            tier=SubscriptionTier.PRO,
        )
        conn.init_rate_limiters()
        manager._connections[conn.connection_id] = conn
        manager._subscribe(conn, ["scan_signals"])

        await manager.emit_scan_signal({"signal": "data"})

        sent = ws.send_json.call_args[0][0]
        # Should be parseable as ISO datetime
        ts = datetime.fromisoformat(sent["timestamp"])
        assert ts.tzinfo is not None

    @pytest.mark.asyncio
    async def test_message_channel_matches_subscription(self):
        manager = ScanifyStreamManager()

        ws = AsyncMock()
        conn = ScanifyConnection(
            websocket=ws,
            tier=SubscriptionTier.PRO,
        )
        conn.init_rate_limiters()
        manager._connections[conn.connection_id] = conn
        manager._subscribe(conn, ["alerts"])

        await manager.emit_alert({"alert": "test"})

        sent = ws.send_json.call_args[0][0]
        assert sent["channel"] == "alerts"

    @pytest.mark.asyncio
    async def test_sequence_numbers_monotonically_increase(self):
        manager = ScanifyStreamManager()

        ws = AsyncMock()
        conn = ScanifyConnection(
            websocket=ws,
            tier=SubscriptionTier.PRO,
        )
        conn.init_rate_limiters()
        manager._connections[conn.connection_id] = conn
        manager._subscribe(conn, ["scan_signals"])

        await manager.emit_scan_signal({"s": 1})
        await manager.emit_scan_signal({"s": 2})
        await manager.emit_scan_signal({"s": 3})

        sequences = [
            call[0][0]["sequence"]
            for call in ws.send_json.call_args_list
        ]
        assert sequences == sorted(sequences)
        assert len(set(sequences)) == len(sequences)  # all unique


class TestScanifyStreamManagerHeartbeat:
    """Tests for the heartbeat mechanism."""

    @pytest.mark.asyncio
    async def test_heartbeat_response_to_ping(self):
        manager = ScanifyStreamManager()

        ws = AsyncMock()
        conn = ScanifyConnection(
            websocket=ws,
            tier=SubscriptionTier.PRO,
        )
        conn.init_rate_limiters()
        manager._connections[conn.connection_id] = conn

        message = json.dumps({"action": "heartbeat"})
        await manager.handle_message(conn, message)

        ws.send_json.assert_called()
        sent = ws.send_json.call_args[0][0]
        assert sent["type"] == "heartbeat"
        assert sent["data"]["pong"] is True

    @pytest.mark.asyncio
    async def test_heartbeat_updates_last_heartbeat(self):
        manager = ScanifyStreamManager()

        ws = AsyncMock()
        conn = ScanifyConnection(
            websocket=ws,
            tier=SubscriptionTier.PRO,
        )
        conn.init_rate_limiters()
        manager._connections[conn.connection_id] = conn

        old_heartbeat = conn.last_heartbeat

        message = json.dumps({"action": "ping"})
        await manager.handle_message(conn, message)

        assert conn.last_heartbeat >= old_heartbeat


class TestScanifyStreamManagerEventEmitters:
    """Tests for event-driven emit methods."""

    @pytest.mark.asyncio
    async def test_emit_gex_signal_to_subscribers(self):
        manager = ScanifyStreamManager()

        ws = AsyncMock()
        conn = ScanifyConnection(
            websocket=ws,
            tier=SubscriptionTier.PRO,
        )
        conn.init_rate_limiters()
        manager._connections[conn.connection_id] = conn
        manager._subscribe(conn, ["gex_signals"])

        count = await manager.emit_gex_signal({"type": "flip"})
        assert count == 1

    @pytest.mark.asyncio
    async def test_emit_scan_signal_to_subscribers(self):
        manager = ScanifyStreamManager()

        ws = AsyncMock()
        conn = ScanifyConnection(
            websocket=ws,
            tier=SubscriptionTier.PRO,
        )
        conn.init_rate_limiters()
        manager._connections[conn.connection_id] = conn
        manager._subscribe(conn, ["scan_signals"])

        count = await manager.emit_scan_signal({"signal": "directional"})
        assert count == 1

    @pytest.mark.asyncio
    async def test_emit_alert_to_subscribers(self):
        manager = ScanifyStreamManager()

        ws = AsyncMock()
        conn = ScanifyConnection(
            websocket=ws,
            tier=SubscriptionTier.PRO,
        )
        conn.init_rate_limiters()
        manager._connections[conn.connection_id] = conn
        manager._subscribe(conn, ["alerts"])

        count = await manager.emit_alert({"alert": "vix_spike"})
        assert count == 1

    @pytest.mark.asyncio
    async def test_emit_to_unsubscribed_channel_returns_zero(self):
        manager = ScanifyStreamManager()

        ws = AsyncMock()
        conn = ScanifyConnection(
            websocket=ws,
            tier=SubscriptionTier.PRO,
        )
        conn.init_rate_limiters()
        manager._connections[conn.connection_id] = conn
        # Not subscribed to gex_signals
        manager._subscribe(conn, ["dashboard"])

        count = await manager.emit_gex_signal({"type": "flip"})
        assert count == 0

    @pytest.mark.asyncio
    async def test_emit_position_update(self):
        manager = ScanifyStreamManager()

        ws = AsyncMock()
        conn = ScanifyConnection(
            websocket=ws,
            tier=SubscriptionTier.PRO,
        )
        conn.init_rate_limiters()
        manager._connections[conn.connection_id] = conn
        manager._subscribe(conn, ["positions"])

        count = await manager.emit_position_update([{"pnl": 100}])
        assert count == 1


class TestScanifyStreamManagerDisconnect:
    """Tests for disconnect handling."""

    @pytest.mark.asyncio
    async def test_disconnect_removes_from_all_tracking(self):
        manager = ScanifyStreamManager()

        ws = AsyncMock()
        conn = ScanifyConnection(
            websocket=ws,
            user_id="user-1",
            tier=SubscriptionTier.PRO,
        )
        conn.init_rate_limiters()
        manager._connections[conn.connection_id] = conn
        manager._user_connections["user-1"].append(conn.connection_id)
        manager._subscribe(conn, ["gex_profile", "scan_signals"])

        await manager.disconnect(conn)

        assert conn.connection_id not in manager._connections
        assert conn.connection_id not in manager._channel_subscribers["gex_profile"]
        assert conn.connection_id not in manager._channel_subscribers["scan_signals"]
        assert conn._closed is True

    @pytest.mark.asyncio
    async def test_double_disconnect_is_safe(self):
        manager = ScanifyStreamManager()

        ws = AsyncMock()
        conn = ScanifyConnection(
            websocket=ws,
            user_id="user-1",
            tier=SubscriptionTier.PRO,
        )
        manager._connections[conn.connection_id] = conn
        manager._user_connections["user-1"].append(conn.connection_id)

        await manager.disconnect(conn)
        await manager.disconnect(conn)  # Should not raise

    @pytest.mark.asyncio
    async def test_emit_skips_closed_connections(self):
        manager = ScanifyStreamManager()

        ws = AsyncMock()
        conn = ScanifyConnection(
            websocket=ws,
            tier=SubscriptionTier.PRO,
        )
        conn.init_rate_limiters()
        conn._closed = True
        manager._connections[conn.connection_id] = conn
        manager._channel_subscribers["alerts"].add(conn.connection_id)

        count = await manager.emit_alert({"test": True})
        assert count == 0


class TestScanifyStreamManagerLifecycle:
    """Tests for start/shutdown lifecycle."""

    @pytest.mark.asyncio
    async def test_start_creates_background_tasks(self):
        manager = ScanifyStreamManager()
        await manager.start()

        assert manager._running is True
        assert len(manager._tasks) > 0

        # Cleanup
        await manager.shutdown()

    @pytest.mark.asyncio
    async def test_double_start_is_safe(self):
        manager = ScanifyStreamManager()
        await manager.start()
        task_count = len(manager._tasks)

        await manager.start()
        assert len(manager._tasks) == task_count

        await manager.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_clears_tasks(self):
        manager = ScanifyStreamManager()
        await manager.start()
        await manager.shutdown()

        assert manager._running is False
        assert len(manager._tasks) == 0

    @pytest.mark.asyncio
    async def test_get_stats_returns_valid_structure(self):
        manager = ScanifyStreamManager()

        stats = manager.get_stats()

        assert "total_connections" in stats
        assert "unique_users" in stats
        assert "by_tier" in stats
        assert "channel_subscribers" in stats
        assert "running" in stats
        assert stats["total_connections"] == 0
        assert stats["running"] is False


class TestScanifyStreamManagerDataProvider:
    """Tests for the data provider interface."""

    @pytest.mark.asyncio
    async def test_default_provider_returns_none(self):
        provider = ScanifyDataProvider()

        assert await provider.get_gex_profile() is None
        assert await provider.get_direction_score() is None
        assert await provider.get_positions() is None
        assert await provider.get_market_data() is None
        assert await provider.get_dashboard() is None

    def test_set_data_provider(self):
        manager = ScanifyStreamManager()
        new_provider = ScanifyDataProvider()

        manager.set_data_provider(new_provider)
        assert manager.data_provider is new_provider


class TestScanifyStreamManagerMultipleConnections:
    """Tests for multiple simultaneous connections."""

    @pytest.mark.asyncio
    async def test_broadcast_to_multiple_subscribers(self):
        manager = ScanifyStreamManager()

        connections = []
        for i in range(3):
            ws = AsyncMock()
            conn = ScanifyConnection(
                websocket=ws,
                user_id=f"user-{i}",
                tier=SubscriptionTier.PRO,
            )
            conn.init_rate_limiters()
            manager._connections[conn.connection_id] = conn
            manager._user_connections[f"user-{i}"].append(conn.connection_id)
            manager._subscribe(conn, ["scan_signals"])
            connections.append(conn)

        count = await manager.emit_scan_signal({"signal": "test"})
        assert count == 3

        for conn in connections:
            conn.websocket.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_selective_channel_delivery(self):
        """Only subscribers of a channel receive its messages."""
        manager = ScanifyStreamManager()

        ws1 = AsyncMock()
        conn1 = ScanifyConnection(websocket=ws1, tier=SubscriptionTier.PRO)
        conn1.init_rate_limiters()
        manager._connections[conn1.connection_id] = conn1
        manager._subscribe(conn1, ["gex_signals"])

        ws2 = AsyncMock()
        conn2 = ScanifyConnection(websocket=ws2, tier=SubscriptionTier.PRO)
        conn2.init_rate_limiters()
        manager._connections[conn2.connection_id] = conn2
        manager._subscribe(conn2, ["alerts"])

        await manager.emit_gex_signal({"type": "flip"})

        ws1.send_json.assert_called_once()
        ws2.send_json.assert_not_called()


class TestChannelConfig:
    """Tests for channel configuration constants."""

    def test_all_channels_defined_in_config(self):
        for ch in ScanifyChannel:
            assert ch in CHANNEL_CONFIG

    def test_all_channels_in_all_channels_set(self):
        for ch in ScanifyChannel:
            assert ch.value in ALL_CHANNELS

    def test_channel_config_has_required_keys(self):
        for ch, config in CHANNEL_CONFIG.items():
            assert "interval_seconds" in config
            assert "description" in config
            assert "min_tier" in config
            assert "rate_limit_per_minute" in config
