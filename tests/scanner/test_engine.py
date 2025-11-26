"""
Tests for scanner engine.
"""

import pytest
from datetime import datetime
from typing import Optional

from src.scanner.engine import (
    ScannerEngine,
    EngineConfig,
    EngineState,
    ScannerStats,
    create_options_engine,
    create_squeeze_engine,
    create_momentum_engine,
    create_full_engine,
)
from src.scanner.base import (
    BaseScanner,
    ScanContext,
    MarketData,
)
from src.scanner.models import (
    ScanResult,
    ScanMode,
    SignalDirection,
    ScannerConfig,
    MarketRegime,
    AlertPriority,
)


class MockDataScanner(BaseScanner[ScanResult]):
    """Mock scanner that uses market data."""

    def __init__(self, **kwargs):
        super().__init__(name="mock_data_scanner", scan_mode=ScanMode.MOMENTUM, **kwargs)

    async def scan(self, context: ScanContext) -> list[ScanResult]:
        results = []
        for symbol in context.universe:
            data = context.market_data.get(symbol)
            if data and data.close > 100:  # Simple condition
                results.append(ScanResult(
                    symbol=symbol,
                    scanner_type=self.name,
                    direction=SignalDirection.LONG,
                    confidence=75.0,
                    entry_price=data.close,
                ))
        return results

    def validate_signal(self, result: ScanResult, context: ScanContext) -> bool:
        return result.confidence >= self.config.min_confidence


class TestEngineConfig:
    """Tests for EngineConfig."""

    def test_default_config(self):
        """Test default engine configuration."""
        config = EngineConfig()

        assert config.max_concurrent_scanners == 5
        assert config.scan_interval_seconds == 60
        assert config.enable_alerting is True
        assert config.min_alert_confidence == 70.0

    def test_custom_config(self):
        """Test custom engine configuration."""
        config = EngineConfig(
            max_concurrent_scanners=3,
            scan_interval_seconds=30,
            min_alert_confidence=80.0,
        )

        assert config.max_concurrent_scanners == 3
        assert config.scan_interval_seconds == 30
        assert config.min_alert_confidence == 80.0


class TestScannerStats:
    """Tests for ScannerStats."""

    def test_stats_update(self):
        """Test stats update from summary."""
        from src.scanner.models import ScannerSummary

        stats = ScannerStats(scanner_name="test")

        summary = ScannerSummary(
            scanner_name="test",
            scan_mode=ScanMode.MOMENTUM,
            symbols_scanned=100,
            signals_found=10,
            high_confidence_signals=3,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )

        stats.update(summary)

        assert stats.total_scans == 1
        assert stats.total_signals == 10
        assert stats.high_confidence_signals == 3


class TestScannerEngine:
    """Tests for ScannerEngine."""

    def test_engine_creation(self):
        """Test engine creation with default scanners."""
        engine = ScannerEngine()

        assert engine.state == EngineState.IDLE
        assert len(engine.scanners) > 0

    def test_scanner_registration(self):
        """Test scanner registration and unregistration."""
        engine = ScannerEngine()
        initial_count = len(engine.scanners)

        # Register new scanner
        scanner = MockDataScanner()
        engine.register_scanner(scanner)
        assert len(engine.scanners) == initial_count + 1
        assert "mock_data_scanner" in engine.scanners

        # Unregister scanner
        result = engine.unregister_scanner("mock_data_scanner")
        assert result is True
        assert len(engine.scanners) == initial_count
        assert "mock_data_scanner" not in engine.scanners

        # Unregister non-existent
        result = engine.unregister_scanner("non_existent")
        assert result is False

    def test_universe_setting(self):
        """Test setting scan universe."""
        engine = ScannerEngine()

        engine.set_universe(["AAPL", "TSLA", "NVDA", "AAPL"])  # Duplicate

        # Duplicates should be removed
        assert len(engine._universe) == 3

    @pytest.mark.asyncio
    async def test_engine_start_stop(self):
        """Test engine start and stop."""
        engine = ScannerEngine()
        engine.set_universe(["AAPL"])

        # Mock market data provider
        async def mock_provider(symbols):
            return {
                "AAPL": MarketData(
                    symbol="AAPL",
                    timestamp=datetime.utcnow(),
                    open=150.0,
                    high=155.0,
                    low=148.0,
                    close=153.0,
                    volume=1000000,
                )
            }

        engine.set_market_data_provider(mock_provider)

        # Start engine (non-continuous)
        await engine.start(continuous=False)
        assert engine.state == EngineState.RUNNING or engine.state == EngineState.IDLE

        # Stop engine
        await engine.stop()
        assert engine.state == EngineState.STOPPED

    @pytest.mark.asyncio
    async def test_pause_resume(self):
        """Test engine pause and resume."""
        engine = ScannerEngine()

        # Manually set running state
        engine._state = EngineState.RUNNING

        await engine.pause()
        assert engine.state == EngineState.PAUSED

        await engine.resume()
        assert engine.state == EngineState.RUNNING

        await engine.stop()

    @pytest.mark.asyncio
    async def test_scan_with_data(self):
        """Test scanning with market data."""
        engine = ScannerEngine()

        # Clear default scanners and add mock
        for name in list(engine.scanners.keys()):
            engine.unregister_scanner(name)

        engine.register_scanner(MockDataScanner())
        engine.set_universe(["AAPL", "TSLA"])

        # Mock provider
        async def mock_provider(symbols):
            return {
                "AAPL": MarketData(
                    symbol="AAPL",
                    timestamp=datetime.utcnow(),
                    open=150.0,
                    high=155.0,
                    low=148.0,
                    close=153.0,  # > 100, should generate signal
                    volume=1000000,
                ),
                "TSLA": MarketData(
                    symbol="TSLA",
                    timestamp=datetime.utcnow(),
                    open=90.0,
                    high=95.0,
                    low=88.0,
                    close=92.0,  # < 100, no signal
                    volume=1000000,
                ),
            }

        engine.set_market_data_provider(mock_provider)

        await engine.start(continuous=False)

        results = engine.last_results
        assert results is not None
        assert len(results.results) == 1
        assert results.results[0].symbol == "AAPL"

    @pytest.mark.asyncio
    async def test_alert_processing(self):
        """Test alert callback processing."""
        alerts_received = []

        async def alert_callback(alert):
            alerts_received.append(alert)

        engine = ScannerEngine(
            config=EngineConfig(
                enable_alerting=True,
                min_alert_confidence=70.0,
            )
        )

        # Clear default scanners and add mock
        for name in list(engine.scanners.keys()):
            engine.unregister_scanner(name)

        # Custom scanner that returns high confidence
        class HighConfScanner(BaseScanner[ScanResult]):
            def __init__(self):
                super().__init__(name="high_conf", scan_mode=ScanMode.MOMENTUM)

            async def scan(self, context: ScanContext) -> list[ScanResult]:
                return [
                    ScanResult(
                        symbol="AAPL",
                        scanner_type="high_conf",
                        direction=SignalDirection.LONG,
                        confidence=85.0,  # Above alert threshold
                    )
                ]

            def validate_signal(self, result, context):
                return True

        engine.register_scanner(HighConfScanner())
        engine.set_universe(["AAPL"])
        engine.add_alert_callback(alert_callback)

        await engine.start(continuous=False)

        assert len(alerts_received) == 1
        assert alerts_received[0].priority == AlertPriority.HIGH

    def test_engine_summary(self):
        """Test engine summary generation."""
        engine = ScannerEngine()
        engine.set_universe(["AAPL", "TSLA"])

        summary = engine.get_summary()

        assert summary["state"] == "idle"
        assert summary["registered_scanners"] > 0
        assert summary["universe_size"] == 2
        assert "scanner_stats" in summary

    @pytest.mark.asyncio
    async def test_scan_single(self):
        """Test scanning single symbol."""
        engine = ScannerEngine()

        # Clear default scanners
        for name in list(engine.scanners.keys()):
            engine.unregister_scanner(name)

        engine.register_scanner(MockDataScanner())

        async def mock_provider(symbols):
            return {
                s: MarketData(
                    symbol=s,
                    timestamp=datetime.utcnow(),
                    open=150.0,
                    high=155.0,
                    low=148.0,
                    close=153.0,
                    volume=1000000,
                )
                for s in symbols
            }

        engine.set_market_data_provider(mock_provider)
        engine.set_universe(["AAPL", "TSLA", "NVDA"])

        results = await engine.scan_single("AAPL")

        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_scan_with_mode(self):
        """Test scanning with specific mode."""
        engine = ScannerEngine()

        async def mock_provider(symbols):
            return {}

        engine.set_market_data_provider(mock_provider)
        engine.set_universe(["AAPL"])

        result = await engine.scan_with_mode(ScanMode.MOMENTUM, ["TSLA"])

        assert result is not None
        assert result.batch_id is not None


class TestFactoryFunctions:
    """Tests for engine factory functions."""

    def test_create_options_engine(self):
        """Test options engine factory."""
        engine = create_options_engine()

        assert engine is not None
        # Should only have options-related scanners
        for name in engine.scanners:
            assert "options" in name or "gamma" in name

    def test_create_squeeze_engine(self):
        """Test squeeze engine factory."""
        engine = create_squeeze_engine()

        assert engine is not None
        # Should only have squeeze-related scanners
        for name in engine.scanners:
            assert "squeeze" in name

    def test_create_momentum_engine(self):
        """Test momentum engine factory."""
        engine = create_momentum_engine()

        assert engine is not None
        # Should have momentum-related scanners
        scanner_names = set(engine.scanners.keys())
        assert scanner_names <= {"momentum", "reversal", "breakout"}

    def test_create_full_engine(self):
        """Test full engine factory."""
        engine = create_full_engine()

        assert engine is not None
        # Should have all scanners
        assert len(engine.scanners) > 5


class TestResultCaching:
    """Tests for result caching."""

    def test_cache_operations(self):
        """Test cache update and retrieval."""
        engine = ScannerEngine(
            config=EngineConfig(cache_ttl_seconds=60)
        )

        result = ScanResult(
            symbol="AAPL",
            scanner_type="test",
            direction=SignalDirection.LONG,
            confidence=80.0,
        )

        engine._update_cache([result])

        # Retrieve from cache
        cached = engine.get_cached_result("AAPL")
        assert cached is not None
        assert cached.symbol == "AAPL"

        # Non-existent symbol
        cached = engine.get_cached_result("TSLA")
        assert cached is None
