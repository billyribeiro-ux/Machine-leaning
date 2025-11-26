"""
Tests for scanner data models.
"""

import pytest
from datetime import datetime, timedelta

from src.scanner.models import (
    ScanMode,
    SignalDirection,
    SqueezeType,
    SignalStrength,
    TimeFrame,
    MarketRegime,
    ScanResult,
    OptionsScanResult,
    SqueezeScanResult,
    MomentumScanResult,
    ReversalScanResult,
    BreakoutScanResult,
    ScannerConfig,
    OptionsFilterConfig,
    SqueezeFilterConfig,
    AlertPriority,
    ScanAlert,
    ScannerSummary,
    ScannerBatchResult,
)


class TestScanResult:
    """Tests for ScanResult model."""

    def test_basic_creation(self):
        """Test basic scan result creation."""
        result = ScanResult(
            symbol="AAPL",
            scanner_type="test",
            direction=SignalDirection.LONG,
            confidence=75.5,
            timestamp=datetime.utcnow(),
        )

        assert result.symbol == "AAPL"
        assert result.scanner_type == "test"
        assert result.direction == SignalDirection.LONG
        assert result.confidence == 75.5

    def test_confidence_validation(self):
        """Test confidence is clamped to 0-100."""
        result = ScanResult(
            symbol="AAPL",
            scanner_type="test",
            direction=SignalDirection.LONG,
            confidence=150.0,  # Should be clamped to 100
        )
        assert result.confidence == 100.0

        result2 = ScanResult(
            symbol="AAPL",
            scanner_type="test",
            direction=SignalDirection.LONG,
            confidence=-50.0,  # Should be clamped to 0
        )
        assert result2.confidence == 0.0

    def test_signal_strength_property(self):
        """Test signal strength classification."""
        # Extreme
        result = ScanResult(
            symbol="AAPL",
            scanner_type="test",
            direction=SignalDirection.LONG,
            confidence=90.0,
        )
        assert result.signal_strength == SignalStrength.EXTREME

        # Strong
        result = ScanResult(
            symbol="AAPL",
            scanner_type="test",
            direction=SignalDirection.LONG,
            confidence=75.0,
        )
        assert result.signal_strength == SignalStrength.STRONG

        # Moderate
        result = ScanResult(
            symbol="AAPL",
            scanner_type="test",
            direction=SignalDirection.LONG,
            confidence=55.0,
        )
        assert result.signal_strength == SignalStrength.MODERATE

        # Weak
        result = ScanResult(
            symbol="AAPL",
            scanner_type="test",
            direction=SignalDirection.LONG,
            confidence=40.0,
        )
        assert result.signal_strength == SignalStrength.WEAK

    def test_is_actionable_property(self):
        """Test actionable signal detection."""
        # Actionable: high confidence + entry price
        result = ScanResult(
            symbol="AAPL",
            scanner_type="test",
            direction=SignalDirection.LONG,
            confidence=70.0,
            entry_price=150.0,
        )
        assert result.is_actionable is True

        # Not actionable: low confidence
        result = ScanResult(
            symbol="AAPL",
            scanner_type="test",
            direction=SignalDirection.LONG,
            confidence=50.0,
            entry_price=150.0,
        )
        assert result.is_actionable is False

        # Not actionable: no entry price
        result = ScanResult(
            symbol="AAPL",
            scanner_type="test",
            direction=SignalDirection.LONG,
            confidence=70.0,
        )
        assert result.is_actionable is False


class TestOptionsScanResult:
    """Tests for OptionsScanResult model."""

    def test_options_result_creation(self):
        """Test options scan result creation."""
        expiration = datetime.utcnow() + timedelta(days=30)

        result = OptionsScanResult(
            symbol="AAPL",
            scanner_type="options_flow",
            direction=SignalDirection.LONG,
            confidence=80.0,
            strike=150.0,
            expiration=expiration,
            option_type="CALL",
            underlying_price=148.0,
        )

        assert result.strike == 150.0
        assert result.option_type == "CALL"
        assert result.days_to_expiry > 0

    def test_spread_calculation(self):
        """Test bid-ask spread calculation."""
        result = OptionsScanResult(
            symbol="AAPL",
            scanner_type="options_flow",
            direction=SignalDirection.LONG,
            confidence=80.0,
            strike=150.0,
            expiration=datetime.utcnow() + timedelta(days=30),
            option_type="CALL",
            bid=2.50,
            ask=2.60,
        )

        assert result.spread == 0.10
        assert result.spread_pct == pytest.approx(4.0, rel=0.01)

    def test_itm_detection(self):
        """Test in-the-money detection."""
        # ITM Call
        result = OptionsScanResult(
            symbol="AAPL",
            scanner_type="options_flow",
            direction=SignalDirection.LONG,
            confidence=80.0,
            strike=145.0,
            expiration=datetime.utcnow() + timedelta(days=30),
            option_type="CALL",
            underlying_price=150.0,
        )
        assert result.is_itm is True

        # OTM Call
        result = OptionsScanResult(
            symbol="AAPL",
            scanner_type="options_flow",
            direction=SignalDirection.LONG,
            confidence=80.0,
            strike=155.0,
            expiration=datetime.utcnow() + timedelta(days=30),
            option_type="CALL",
            underlying_price=150.0,
        )
        assert result.is_itm is False

        # ITM Put
        result = OptionsScanResult(
            symbol="AAPL",
            scanner_type="options_flow",
            direction=SignalDirection.SHORT,
            confidence=80.0,
            strike=155.0,
            expiration=datetime.utcnow() + timedelta(days=30),
            option_type="PUT",
            underlying_price=150.0,
        )
        assert result.is_itm is True


class TestSqueezeScanResult:
    """Tests for SqueezeScanResult model."""

    def test_squeeze_result_creation(self):
        """Test squeeze scan result creation."""
        result = SqueezeScanResult(
            symbol="GME",
            scanner_type="short_squeeze",
            direction=SignalDirection.LONG,
            confidence=85.0,
            squeeze_type=SqueezeType.SHORT,
            squeeze_score=90.0,
            volume_ratio=5.0,
            short_interest=40.0,
            days_to_cover=5.0,
        )

        assert result.squeeze_type == SqueezeType.SHORT
        assert result.squeeze_score == 90.0
        assert result.short_interest == 40.0

    def test_critical_squeeze_detection(self):
        """Test critical squeeze condition detection."""
        # Critical squeeze
        result = SqueezeScanResult(
            symbol="GME",
            scanner_type="short_squeeze",
            direction=SignalDirection.LONG,
            confidence=85.0,
            squeeze_type=SqueezeType.SHORT,
            squeeze_score=85.0,
            volume_ratio=4.0,
        )
        assert result.is_critical_squeeze is True

        # Not critical (low score)
        result = SqueezeScanResult(
            symbol="GME",
            scanner_type="short_squeeze",
            direction=SignalDirection.LONG,
            confidence=85.0,
            squeeze_type=SqueezeType.SHORT,
            squeeze_score=70.0,
            volume_ratio=4.0,
        )
        assert result.is_critical_squeeze is False


class TestMomentumScanResult:
    """Tests for MomentumScanResult model."""

    def test_momentum_result_creation(self):
        """Test momentum scan result creation."""
        result = MomentumScanResult(
            symbol="NVDA",
            scanner_type="momentum",
            direction=SignalDirection.LONG,
            confidence=75.0,
            rsi=65.0,
            macd_histogram=0.5,
            adx=35.0,
            volume_surge=2.5,
        )

        assert result.rsi == 65.0
        assert result.adx == 35.0
        assert result.volume_surge == 2.5

    def test_overbought_oversold(self):
        """Test overbought/oversold detection."""
        # Overbought
        result = MomentumScanResult(
            symbol="NVDA",
            scanner_type="momentum",
            direction=SignalDirection.LONG,
            confidence=75.0,
            rsi=75.0,
        )
        assert result.is_overbought is True
        assert result.is_oversold is False

        # Oversold
        result = MomentumScanResult(
            symbol="NVDA",
            scanner_type="momentum",
            direction=SignalDirection.SHORT,
            confidence=75.0,
            rsi=25.0,
        )
        assert result.is_overbought is False
        assert result.is_oversold is True


class TestScannerConfig:
    """Tests for ScannerConfig model."""

    def test_default_config(self):
        """Test default configuration values."""
        config = ScannerConfig()

        assert config.min_confidence == 60.0
        assert config.min_volume == 100000
        assert config.min_price == 5.0
        assert config.max_price == 500.0
        assert ScanMode.ALL in config.scan_modes

    def test_custom_config(self):
        """Test custom configuration."""
        config = ScannerConfig(
            min_confidence=70.0,
            min_volume=500000,
            sectors=["Technology", "Healthcare"],
            excluded_symbols=["PENNY"],
        )

        assert config.min_confidence == 70.0
        assert config.min_volume == 500000
        assert "Technology" in config.sectors
        assert "PENNY" in config.excluded_symbols


class TestScannerBatchResult:
    """Tests for ScannerBatchResult model."""

    def test_batch_result_creation(self):
        """Test batch result creation."""
        results = [
            ScanResult(
                symbol="AAPL",
                scanner_type="test",
                direction=SignalDirection.LONG,
                confidence=80.0,
                entry_price=150.0,
            ),
            ScanResult(
                symbol="TSLA",
                scanner_type="test",
                direction=SignalDirection.SHORT,
                confidence=70.0,
                entry_price=200.0,
            ),
        ]

        batch = ScannerBatchResult(
            batch_id="test-123",
            results=results,
            summaries=[],
            market_regime=MarketRegime.TRENDING_UP,
        )

        assert batch.total_signals == 2
        assert len(batch.actionable_signals) == 2

    def test_filtering_methods(self):
        """Test batch filtering methods."""
        results = [
            ScanResult(
                symbol="AAPL",
                scanner_type="test",
                direction=SignalDirection.LONG,
                confidence=90.0,
            ),
            ScanResult(
                symbol="TSLA",
                scanner_type="test",
                direction=SignalDirection.LONG,
                confidence=70.0,
            ),
            ScanResult(
                symbol="NVDA",
                scanner_type="test",
                direction=SignalDirection.SHORT,
                confidence=80.0,
            ),
        ]

        batch = ScannerBatchResult(
            batch_id="test-123",
            results=results,
            summaries=[],
            market_regime=MarketRegime.RANGING,
        )

        # Filter by direction
        longs = batch.filter_by_direction(SignalDirection.LONG)
        assert len(longs) == 2

        shorts = batch.filter_by_direction(SignalDirection.SHORT)
        assert len(shorts) == 1

        # Filter by confidence
        high_conf = batch.filter_by_confidence(80.0)
        assert len(high_conf) == 2

        # Top signals
        top = batch.top_signals(2)
        assert len(top) == 2
        assert top[0].confidence == 90.0


class TestScanAlert:
    """Tests for ScanAlert model."""

    def test_alert_creation(self):
        """Test alert creation."""
        result = ScanResult(
            symbol="AAPL",
            scanner_type="test",
            direction=SignalDirection.LONG,
            confidence=85.0,
        )

        alert = ScanAlert(
            alert_id="alert-123",
            scan_result=result,
            priority=AlertPriority.HIGH,
            message="Test alert",
        )

        assert alert.priority == AlertPriority.HIGH
        assert alert.acknowledged is False

    def test_alert_expiration(self):
        """Test alert expiration logic."""
        result = ScanResult(
            symbol="AAPL",
            scanner_type="test",
            direction=SignalDirection.LONG,
            confidence=85.0,
        )

        # Non-expired alert
        alert = ScanAlert(
            alert_id="alert-123",
            scan_result=result,
            priority=AlertPriority.HIGH,
            message="Test alert",
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        assert alert.is_expired is False

        # Expired alert
        alert = ScanAlert(
            alert_id="alert-124",
            scan_result=result,
            priority=AlertPriority.HIGH,
            message="Test alert",
            expires_at=datetime.utcnow() - timedelta(hours=1),
        )
        assert alert.is_expired is True


class TestScannerSummary:
    """Tests for ScannerSummary model."""

    def test_summary_creation(self):
        """Test summary creation."""
        start = datetime.utcnow()
        end = start + timedelta(seconds=5)

        summary = ScannerSummary(
            scanner_name="test_scanner",
            scan_mode=ScanMode.MOMENTUM,
            symbols_scanned=100,
            signals_found=10,
            high_confidence_signals=3,
            started_at=start,
            completed_at=end,
        )

        assert summary.duration_seconds == pytest.approx(5.0, rel=0.1)
        assert summary.signals_per_second == pytest.approx(20.0, rel=0.1)
