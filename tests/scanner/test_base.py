"""
Tests for base scanner classes.
"""

import pytest
from datetime import datetime
from typing import Optional

from src.scanner.base import (
    BaseScanner,
    AsyncStreamingScanner,
    CompositeScanner,
    ScanContext,
    MarketData,
    HistoricalData,
)
from src.scanner.models import (
    ScanResult,
    ScanMode,
    SignalDirection,
    ScannerConfig,
    MarketRegime,
    TimeFrame,
)


class MockScanner(BaseScanner[ScanResult]):
    """Mock scanner for testing."""

    def __init__(self, results: list[ScanResult] = None, **kwargs):
        super().__init__(name="mock_scanner", scan_mode=ScanMode.MOMENTUM, **kwargs)
        self._mock_results = results or []

    async def scan(self, context: ScanContext) -> list[ScanResult]:
        return self._mock_results

    def validate_signal(self, result: ScanResult, context: ScanContext) -> bool:
        return result.confidence >= self.config.min_confidence


class MockStreamingScanner(AsyncStreamingScanner[ScanResult]):
    """Mock streaming scanner for testing."""

    def __init__(self, **kwargs):
        super().__init__(name="mock_streaming", scan_mode=ScanMode.MOMENTUM, **kwargs)

    async def scan_symbol(
        self,
        symbol: str,
        context: ScanContext
    ) -> Optional[ScanResult]:
        # Return a result for every symbol
        return ScanResult(
            symbol=symbol,
            scanner_type=self.name,
            direction=SignalDirection.LONG,
            confidence=75.0,
            entry_price=100.0,
        )

    def validate_signal(self, result: ScanResult, context: ScanContext) -> bool:
        return result.confidence >= self.config.min_confidence


class TestMarketData:
    """Tests for MarketData class."""

    def test_market_data_creation(self):
        """Test market data creation."""
        data = MarketData(
            symbol="AAPL",
            timestamp=datetime.utcnow(),
            open=150.0,
            high=155.0,
            low=148.0,
            close=153.0,
            volume=1000000,
        )

        assert data.symbol == "AAPL"
        assert data.close == 153.0
        assert data.volume == 1000000

    def test_spread_calculation(self):
        """Test bid-ask spread calculation."""
        data = MarketData(
            symbol="AAPL",
            timestamp=datetime.utcnow(),
            open=150.0,
            high=155.0,
            low=148.0,
            close=153.0,
            volume=1000000,
            bid=152.95,
            ask=153.05,
        )

        assert data.spread == pytest.approx(0.10, rel=0.01)
        assert data.mid_price == pytest.approx(153.0, rel=0.01)

    def test_range_calculation(self):
        """Test intraday range calculation."""
        data = MarketData(
            symbol="AAPL",
            timestamp=datetime.utcnow(),
            open=150.0,
            high=155.0,
            low=148.0,
            close=153.0,
            volume=1000000,
        )

        # (155-148)/148 * 100 = 4.73%
        assert data.range_pct == pytest.approx(4.73, rel=0.01)

    def test_bullish_candle(self):
        """Test bullish candle detection."""
        # Bullish
        data = MarketData(
            symbol="AAPL",
            timestamp=datetime.utcnow(),
            open=150.0,
            high=155.0,
            low=148.0,
            close=153.0,
            volume=1000000,
        )
        assert data.is_bullish_candle is True

        # Bearish
        data = MarketData(
            symbol="AAPL",
            timestamp=datetime.utcnow(),
            open=155.0,
            high=156.0,
            low=150.0,
            close=151.0,
            volume=1000000,
        )
        assert data.is_bullish_candle is False


class TestHistoricalData:
    """Tests for HistoricalData class."""

    def test_historical_data_creation(self):
        """Test historical data creation."""
        bars = [
            MarketData(
                symbol="AAPL",
                timestamp=datetime.utcnow(),
                open=150.0,
                high=155.0,
                low=148.0,
                close=153.0,
                volume=1000000,
            ),
            MarketData(
                symbol="AAPL",
                timestamp=datetime.utcnow(),
                open=153.0,
                high=157.0,
                low=152.0,
                close=156.0,
                volume=1200000,
            ),
        ]

        hist = HistoricalData(
            symbol="AAPL",
            timeframe=TimeFrame.D1,
            bars=bars,
        )

        assert hist.symbol == "AAPL"
        assert len(hist.bars) == 2
        assert hist.latest.close == 156.0

    def test_price_lists(self):
        """Test price list extraction."""
        bars = [
            MarketData(
                symbol="AAPL",
                timestamp=datetime.utcnow(),
                open=150.0,
                high=155.0,
                low=148.0,
                close=153.0,
                volume=1000000,
            ),
            MarketData(
                symbol="AAPL",
                timestamp=datetime.utcnow(),
                open=153.0,
                high=157.0,
                low=152.0,
                close=156.0,
                volume=1200000,
            ),
        ]

        hist = HistoricalData(
            symbol="AAPL",
            timeframe=TimeFrame.D1,
            bars=bars,
        )

        assert hist.closes == [153.0, 156.0]
        assert hist.highs == [155.0, 157.0]
        assert hist.lows == [148.0, 152.0]
        assert hist.volumes == [1000000, 1200000]

    def test_slice(self):
        """Test slice functionality."""
        bars = [
            MarketData(
                symbol="AAPL",
                timestamp=datetime.utcnow(),
                open=150.0 + i,
                high=155.0 + i,
                low=148.0 + i,
                close=153.0 + i,
                volume=1000000,
            )
            for i in range(10)
        ]

        hist = HistoricalData(
            symbol="AAPL",
            timeframe=TimeFrame.D1,
            bars=bars,
        )

        sliced = hist.slice(5)
        assert len(sliced.bars) == 5
        assert sliced.bars[0].open == 155.0  # 6th bar (index 5)


class TestScanContext:
    """Tests for ScanContext class."""

    def test_context_creation(self):
        """Test scan context creation."""
        config = ScannerConfig()
        universe = ["AAPL", "TSLA", "NVDA"]

        context = ScanContext.create(
            config=config,
            universe=universe,
            market_regime=MarketRegime.TRENDING_UP,
        )

        assert context.scan_id is not None
        assert len(context.universe) == 3
        assert context.market_regime == MarketRegime.TRENDING_UP


class TestBaseScanner:
    """Tests for BaseScanner class."""

    @pytest.mark.asyncio
    async def test_scanner_execution(self):
        """Test scanner execution with pre/post hooks."""
        results = [
            ScanResult(
                symbol="AAPL",
                scanner_type="mock_scanner",
                direction=SignalDirection.LONG,
                confidence=75.0,
            ),
        ]

        scanner = MockScanner(results=results)
        context = ScanContext.create(
            config=ScannerConfig(),
            universe=["AAPL"],
        )

        final_results, summary = await scanner.execute(context)

        assert len(final_results) == 1
        assert summary.scanner_name == "mock_scanner"
        assert summary.signals_found == 1

    @pytest.mark.asyncio
    async def test_confidence_filtering(self):
        """Test that results are filtered by minimum confidence."""
        results = [
            ScanResult(
                symbol="AAPL",
                scanner_type="mock_scanner",
                direction=SignalDirection.LONG,
                confidence=75.0,
            ),
            ScanResult(
                symbol="TSLA",
                scanner_type="mock_scanner",
                direction=SignalDirection.LONG,
                confidence=50.0,  # Below default threshold
            ),
        ]

        config = ScannerConfig(min_confidence=60.0)
        scanner = MockScanner(results=results, config=config)
        context = ScanContext.create(
            config=config,
            universe=["AAPL", "TSLA"],
        )

        final_results, summary = await scanner.execute(context)

        assert len(final_results) == 1
        assert final_results[0].symbol == "AAPL"

    def test_stop_loss_calculation(self):
        """Test stop loss calculation."""
        scanner = MockScanner()

        # Long with ATR
        stop = scanner.calculate_stop_loss(
            entry=100.0,
            direction=SignalDirection.LONG,
            atr=2.0,
            atr_multiplier=2.0,
        )
        assert stop == 96.0  # 100 - (2 * 2)

        # Short with ATR
        stop = scanner.calculate_stop_loss(
            entry=100.0,
            direction=SignalDirection.SHORT,
            atr=2.0,
            atr_multiplier=2.0,
        )
        assert stop == 104.0  # 100 + (2 * 2)

        # Percentage stop
        stop = scanner.calculate_stop_loss(
            entry=100.0,
            direction=SignalDirection.LONG,
            pct_stop=3.0,
        )
        assert stop == 97.0  # 100 - 3%

    def test_targets_calculation(self):
        """Test price targets calculation."""
        scanner = MockScanner()

        # Long targets
        targets = scanner.calculate_targets(
            entry=100.0,
            stop_loss=96.0,
            direction=SignalDirection.LONG,
            rr_ratios=[1.5, 2.0, 3.0],
        )

        risk = 100.0 - 96.0  # $4 risk
        assert targets[0] == 106.0  # 100 + (4 * 1.5)
        assert targets[1] == 108.0  # 100 + (4 * 2.0)
        assert targets[2] == 112.0  # 100 + (4 * 3.0)

        # Short targets
        targets = scanner.calculate_targets(
            entry=100.0,
            stop_loss=104.0,
            direction=SignalDirection.SHORT,
            rr_ratios=[1.5, 2.0, 3.0],
        )

        assert targets[0] == 94.0  # 100 - (4 * 1.5)
        assert targets[1] == 92.0  # 100 - (4 * 2.0)
        assert targets[2] == 88.0  # 100 - (4 * 3.0)

    def test_risk_reward_calculation(self):
        """Test risk/reward calculation."""
        scanner = MockScanner()

        rr = scanner.calculate_risk_reward(
            entry=100.0,
            stop_loss=96.0,
            target=108.0,
        )

        # Risk = 4, Reward = 8, RR = 2.0
        assert rr == 2.0

    def test_filters(self):
        """Test basic filters."""
        config = ScannerConfig(
            min_volume=100000,
            min_price=5.0,
            max_price=500.0,
        )
        scanner = MockScanner(config=config)

        # Passes filters
        data = MarketData(
            symbol="AAPL",
            timestamp=datetime.utcnow(),
            open=150.0,
            high=155.0,
            low=148.0,
            close=153.0,
            volume=200000,
        )
        assert scanner.apply_filters(data) is True

        # Fails volume filter
        data = MarketData(
            symbol="PENNY",
            timestamp=datetime.utcnow(),
            open=150.0,
            high=155.0,
            low=148.0,
            close=153.0,
            volume=50000,
        )
        assert scanner.apply_filters(data) is False

        # Fails price filter (too low)
        data = MarketData(
            symbol="PENNY",
            timestamp=datetime.utcnow(),
            open=2.0,
            high=2.5,
            low=1.8,
            close=2.3,
            volume=200000,
        )
        assert scanner.apply_filters(data) is False


class TestAsyncStreamingScanner:
    """Tests for AsyncStreamingScanner class."""

    @pytest.mark.asyncio
    async def test_streaming_scan(self):
        """Test streaming scanner execution."""
        scanner = MockStreamingScanner()
        context = ScanContext.create(
            config=ScannerConfig(),
            universe=["AAPL", "TSLA", "NVDA"],
        )

        results, summary = await scanner.execute(context)

        # Should have results for all symbols
        assert len(results) == 3
        assert summary.symbols_scanned == 3

    @pytest.mark.asyncio
    async def test_streaming_with_batches(self):
        """Test streaming with batch processing."""
        scanner = MockStreamingScanner(batch_size=2)
        context = ScanContext.create(
            config=ScannerConfig(),
            universe=["A", "B", "C", "D", "E"],  # 5 symbols
        )

        results = []
        async for result in scanner.stream_scan(context):
            results.append(result)

        assert len(results) == 5


class TestCompositeScanner:
    """Tests for CompositeScanner class."""

    @pytest.mark.asyncio
    async def test_composite_aggregation(self):
        """Test composite scanner result aggregation."""
        # Scanner 1 results
        scanner1_results = [
            ScanResult(
                symbol="AAPL",
                scanner_type="scanner1",
                direction=SignalDirection.LONG,
                confidence=70.0,
            ),
        ]

        # Scanner 2 results (same symbol, should boost confidence)
        scanner2_results = [
            ScanResult(
                symbol="AAPL",
                scanner_type="scanner2",
                direction=SignalDirection.LONG,
                confidence=75.0,
            ),
        ]

        scanner1 = MockScanner(results=scanner1_results)
        scanner2 = MockScanner(results=scanner2_results)

        composite = CompositeScanner(
            name="composite",
            scanners=[scanner1, scanner2],
            min_scanner_agreement=2,
        )

        context = ScanContext.create(
            config=ScannerConfig(),
            universe=["AAPL"],
        )

        results, _ = await composite.execute(context)

        # Should have 1 aggregated result with boosted confidence
        assert len(results) == 1
        assert results[0].symbol == "AAPL"
        # Confidence should be boosted: 75 + 10 (agreement bonus) = 85
        assert results[0].confidence == 85.0

    @pytest.mark.asyncio
    async def test_composite_minimum_agreement(self):
        """Test minimum scanner agreement filter."""
        # Only one scanner finds AAPL
        scanner1_results = [
            ScanResult(
                symbol="AAPL",
                scanner_type="scanner1",
                direction=SignalDirection.LONG,
                confidence=70.0,
            ),
        ]

        scanner1 = MockScanner(results=scanner1_results)
        scanner2 = MockScanner(results=[])

        composite = CompositeScanner(
            name="composite",
            scanners=[scanner1, scanner2],
            min_scanner_agreement=2,  # Require 2 scanners to agree
        )

        context = ScanContext.create(
            config=ScannerConfig(),
            universe=["AAPL"],
        )

        results, _ = await composite.execute(context)

        # Should have no results since only 1 scanner found AAPL
        assert len(results) == 0
