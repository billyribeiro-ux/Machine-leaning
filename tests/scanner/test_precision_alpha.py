"""
Tests for PrecisionAlphaScanner — unit tests and backtest integration.
"""

import pytest
import uuid
from datetime import datetime, timedelta, timezone

from src.scanner.precision_alpha import (
    PrecisionAlphaScanner,
    PrecisionAlphaResult,
    DimensionScore,
    OptionRecommendation,
    SIGNAL_THRESHOLD,
    HIGH_CONVICTION,
    WEIGHTS_LOW_VOL,
    WEIGHTS_NORMAL,
    WEIGHTS_HIGH_VOL,
    WEIGHTS_TRENDING,
    WEIGHTS_MEAN_REV,
    DIM_NAMES,
    _clamp,
    _z_score,
    _ema,
    _rsi,
    _macd,
    _adx,
    _atr,
    _vwap,
)
from src.scanner.base import (
    ScanContext,
    MarketData,
    HistoricalData,
    ScannerConfig,
)
from src.scanner.models import (
    ScanMode,
    ScanResult,
    SignalDirection,
    TimeFrame,
    MarketRegime,
)
from src.scanner.scanner_backtest import (
    ScannerBacktestEngine,
    ScannerBacktestResult,
    BacktestTimeframe,
    TradeSimulator,
    SimulatedBar,
    BacktestReportGenerator,
)


# ---------------------------------------------------------------------------
# Fixtures — synthetic market data
# ---------------------------------------------------------------------------

def _make_bars(n: int = 60, base_price: float = 150.0,
               trend: float = 0.1) -> list[MarketData]:
    """Generate synthetic OHLCV bars for testing."""
    bars = []
    price = base_price
    t = datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc)
    for i in range(n):
        o = price
        h = price + abs(trend) * 2 + 0.5
        l = price - abs(trend) * 1.5 - 0.3
        c = price + trend
        vol = 500_000 + i * 10_000
        bars.append(MarketData(
            symbol="SYN",
            timestamp=t + timedelta(minutes=i),
            open=round(o, 2),
            high=round(h, 2),
            low=round(l, 2),
            close=round(c, 2),
            volume=vol,
        ))
        price = c
    return bars


def _make_market_data(symbol: str = "AAPL", close: float = 155.0) -> MarketData:
    return MarketData(
        symbol=symbol,
        timestamp=datetime(2026, 1, 5, 10, 30, tzinfo=timezone.utc),
        open=154.0,
        high=156.0,
        low=153.5,
        close=close,
        volume=2_000_000,
        bid=close - 0.01,
        ask=close + 0.01,
        bid_size=500,
        ask_size=400,
        relative_volume=2.5,
        atr=1.8,
        vwap=close - 0.20,
    )


def _make_context(symbols: list[str] | None = None) -> ScanContext:
    symbols = symbols or ["AAPL", "TSLA"]
    md = {}
    hd = {}
    for sym in symbols:
        base = 155.0 if sym == "AAPL" else 250.0
        md[sym] = _make_market_data(sym, base)
        hd[sym] = HistoricalData(
            symbol=sym,
            timeframe=TimeFrame.M1,
            bars=_make_bars(60, base - 5.0),
        )
    return ScanContext(
        scan_id="test-ctx",
        timestamp=datetime(2026, 1, 5, 10, 30, tzinfo=timezone.utc),
        market_regime=MarketRegime.RANGING,
        config=ScannerConfig(),
        universe=symbols,
        market_data=md,
        historical_data=hd,
        metadata={},
    )


def _make_simulated_bars(n: int = 50, base: float = 155.0,
                         trend: float = 0.1) -> list[SimulatedBar]:
    """Create SimulatedBar list for backtest engine."""
    bars = []
    price = base
    t = datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc)
    for i in range(n):
        h = price + 1.5
        l = price - 1.0
        c = price + trend
        bars.append(SimulatedBar(
            timestamp=t + timedelta(minutes=i),
            open=round(price, 2),
            high=round(h, 2),
            low=round(l, 2),
            close=round(c, 2),
            volume=500_000 + i * 5_000,
            atr=1.5,
        ))
        price = c
    return bars


# ===================================================================
# 1. Helper function tests
# ===================================================================

class TestHelpers:
    def test_clamp_within_range(self):
        assert _clamp(50.0) == 50.0

    def test_clamp_below(self):
        assert _clamp(-10.0) == 0.0

    def test_clamp_above(self):
        assert _clamp(120.0) == 100.0

    def test_z_score_normal(self):
        assert abs(_z_score(12.0, 10.0, 2.0) - 1.0) < 1e-9

    def test_z_score_zero_std(self):
        assert _z_score(5.0, 3.0, 0.0) == 0.0

    def test_ema_single(self):
        result = _ema([10.0], 5)
        assert result == [10.0]

    def test_ema_length(self):
        data = [float(i) for i in range(20)]
        result = _ema(data, 5)
        assert len(result) == 20

    def test_rsi_range(self):
        prices = [100 + i * 0.5 for i in range(30)]
        r = _rsi(prices)
        assert 0 <= r <= 100

    def test_macd_shape(self):
        prices = [100 + i * 0.3 for i in range(40)]
        line, signal, hist = _macd(prices)
        assert isinstance(line, float)
        assert isinstance(signal, float)
        assert isinstance(hist, float)

    def test_adx_non_negative(self):
        highs = [101 + i * 0.2 for i in range(30)]
        lows = [99 + i * 0.2 for i in range(30)]
        closes = [100 + i * 0.2 for i in range(30)]
        adx_val, plus_di, minus_di = _adx(highs, lows, closes)
        assert adx_val >= 0.0
        assert plus_di >= 0.0
        assert minus_di >= 0.0

    def test_atr_positive(self):
        highs = [102, 103, 104, 105]
        lows = [99, 100, 101, 102]
        closes = [101, 102, 103, 104]
        a = _atr(highs, lows, closes, period=3)
        assert a > 0.0

    def test_vwap_output(self):
        h = [102.0, 103.0, 104.0]
        l = [99.0, 100.0, 101.0]
        c = [101.0, 102.0, 103.0]
        v = [1000, 2000, 1500]
        vw = _vwap(h, l, c, v)
        assert 99.0 <= vw <= 105.0


# ===================================================================
# 2. Weight / constant tests
# ===================================================================

class TestWeightsAndConstants:
    def test_all_weight_presets_sum_to_one(self):
        for w in [WEIGHTS_LOW_VOL, WEIGHTS_NORMAL, WEIGHTS_HIGH_VOL,
                  WEIGHTS_TRENDING, WEIGHTS_MEAN_REV]:
            assert abs(sum(w) - 1.0) < 1e-6, f"Weights sum to {sum(w)}"

    def test_dim_names_count(self):
        assert len(DIM_NAMES) == 8

    def test_threshold_values(self):
        assert SIGNAL_THRESHOLD == 70
        assert HIGH_CONVICTION == 85


# ===================================================================
# 3. Data container tests
# ===================================================================

class TestDataContainers:
    def test_dimension_score_fields(self):
        ds = DimensionScore("tape_pressure", 82.0, 0.6, {"vpin": 0.45})
        assert ds.name == "tape_pressure"
        assert ds.score == 82.0
        assert ds.direction == 0.6
        assert ds.components["vpin"] == 0.45

    def test_option_recommendation_fields(self):
        rec = OptionRecommendation(
            option_type="CALL",
            strike=155.0,
            expiry_days=7,
            delta=0.55,
            estimated_premium=3.20,
            breakeven=158.20,
            max_risk=320.0,
            target_pnl_pct=50.0,
            greeks={"gamma": 0.05, "theta": -0.08, "vega": 0.12},
        )
        assert rec.option_type == "CALL"
        assert rec.delta == 0.55
        assert rec.greeks["gamma"] == 0.05

    def test_precision_alpha_result_fields(self):
        dims = [DimensionScore(n, 50.0, 0.0, {}) for n in DIM_NAMES]
        par = PrecisionAlphaResult(
            symbol="AAPL",
            composite_score=75.0,
            direction=SignalDirection.LONG,
            confidence=75.0,
            dimensions=dims,
            entry_price=155.0,
            stop_loss=152.0,
            targets=[157.0, 159.0],
            risk_reward=1.5,
            option_rec=None,
            regime="normal",
            weights_used=WEIGHTS_NORMAL,
            timestamp=datetime.now(timezone.utc),
        )
        assert par.symbol == "AAPL"
        assert len(par.dimensions) == 8
        assert par.regime == "normal"


# ===================================================================
# 4. Scanner instantiation
# ===================================================================

class TestScannerInit:
    def test_default_init(self):
        scanner = PrecisionAlphaScanner()
        assert scanner.name == "precision_alpha"
        assert scanner.scan_mode == ScanMode.ALL

    def test_custom_config(self):
        cfg = ScannerConfig(min_confidence=80.0)
        scanner = PrecisionAlphaScanner(config=cfg)
        assert scanner.config.min_confidence == 80.0

    def test_validate_signal_accepts_high_confidence(self):
        scanner = PrecisionAlphaScanner()
        result = ScanResult(
            symbol="AAPL",
            scanner_type="precision_alpha",
            direction=SignalDirection.LONG,
            confidence=85.0,
            entry_price=155.0,
        )
        ctx = _make_context(["AAPL"])
        assert scanner.validate_signal(result, ctx) is True

    def test_validate_signal_rejects_low_confidence(self):
        scanner = PrecisionAlphaScanner()
        result = ScanResult(
            symbol="AAPL",
            scanner_type="precision_alpha",
            direction=SignalDirection.LONG,
            confidence=50.0,
            entry_price=155.0,
        )
        ctx = _make_context(["AAPL"])
        assert scanner.validate_signal(result, ctx) is False

    def test_validate_signal_rejects_neutral(self):
        scanner = PrecisionAlphaScanner()
        result = ScanResult(
            symbol="AAPL",
            scanner_type="precision_alpha",
            direction=SignalDirection.NEUTRAL,
            confidence=80.0,
            entry_price=155.0,
        )
        ctx = _make_context(["AAPL"])
        assert scanner.validate_signal(result, ctx) is False


# ===================================================================
# 5. Scan execution
# ===================================================================

class TestScan:
    @pytest.mark.asyncio
    async def test_scan_returns_list(self):
        scanner = PrecisionAlphaScanner()
        ctx = _make_context(["AAPL"])
        results = await scanner.scan(ctx)
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_scan_results_are_scan_result_type(self):
        scanner = PrecisionAlphaScanner()
        ctx = _make_context(["AAPL"])
        results = await scanner.scan(ctx)
        for r in results:
            assert isinstance(r, ScanResult)

    @pytest.mark.asyncio
    async def test_scan_result_has_metadata(self):
        scanner = PrecisionAlphaScanner()
        ctx = _make_context(["AAPL"])
        results = await scanner.scan(ctx)
        for r in results:
            assert "dimensions" in r.metadata
            assert "regime" in r.metadata
            assert "weights" in r.metadata

    @pytest.mark.asyncio
    async def test_scan_result_scanner_type(self):
        scanner = PrecisionAlphaScanner()
        ctx = _make_context(["AAPL"])
        results = await scanner.scan(ctx)
        for r in results:
            assert r.scanner_type == "precision_alpha"

    @pytest.mark.asyncio
    async def test_scan_multiple_symbols(self):
        scanner = PrecisionAlphaScanner()
        ctx = _make_context(["AAPL", "TSLA"])
        results = await scanner.scan(ctx)
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_scan_with_no_market_data(self):
        scanner = PrecisionAlphaScanner()
        ctx = ScanContext(
            scan_id="test-empty",
            timestamp=datetime(2026, 1, 5, 10, 30, tzinfo=timezone.utc),
            market_regime=MarketRegime.RANGING,
            config=ScannerConfig(),
            universe=["MISSING"],
            market_data={},
            historical_data={},
            metadata={},
        )
        results = await scanner.scan(ctx)
        assert results == []


# ===================================================================
# 6. ScanResult ↔ Backtest integration
# ===================================================================

class TestBacktestIntegration:
    """Verify PrecisionAlpha ScanResults flow through ScannerBacktestEngine."""

    def _make_signals(self, n: int = 5) -> list[ScanResult]:
        """Generate synthetic PrecisionAlpha ScanResult signals."""
        signals = []
        base_time = datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc)
        for i in range(n):
            signals.append(ScanResult(
                symbol="AAPL",
                scanner_type="precision_alpha",
                direction=SignalDirection.LONG,
                confidence=75.0 + i * 2,
                entry_price=155.0 + i * 0.5,
                stop_loss=152.0 + i * 0.5,
                targets=[157.5 + i * 0.5, 160.0 + i * 0.5, 163.0 + i * 0.5],
                risk_reward=1.5 + i * 0.1,
                timeframe=TimeFrame.M1,
                timestamp=base_time + timedelta(minutes=i * 5),
                metadata={
                    "regime": "normal",
                    "weights": WEIGHTS_NORMAL,
                    "dimensions": {
                        name: {"score": 60 + i * 3, "direction": 0.3, "components": {}}
                        for name in DIM_NAMES
                    },
                    "option_recommendation": {
                        "type": "CALL",
                        "strike": 155.0,
                        "dte": 7,
                        "delta": 0.55,
                        "premium": 3.20,
                        "breakeven": 158.20,
                        "max_risk": 320.0,
                        "target_pnl_pct": 50.0,
                        "greeks": {"gamma": 0.05},
                    },
                },
            ))
        return signals

    def test_backtest_engine_accepts_precision_alpha_signals(self):
        engine = ScannerBacktestEngine(
            scanner_name="precision_alpha",
            timeframe=BacktestTimeframe.M1,
            position_size=10_000.0,
            random_seed=42,
        )
        signals = self._make_signals(5)
        bars = _make_simulated_bars(100, base=155.0, trend=0.1)

        result = engine.run_backtest(signals, bars)

        assert isinstance(result, ScannerBacktestResult)
        assert result.scanner_name == "precision_alpha"
        assert result.total_signals == 5

    def test_backtest_produces_metrics(self):
        engine = ScannerBacktestEngine(
            scanner_name="precision_alpha",
            timeframe=BacktestTimeframe.M1,
            position_size=10_000.0,
            random_seed=42,
        )
        signals = self._make_signals(10)
        bars = _make_simulated_bars(200, base=155.0, trend=0.1)

        result = engine.run_backtest(signals, bars)

        assert result.total_trades >= 0
        assert isinstance(result.win_rate, float)
        assert isinstance(result.sharpe_ratio, float)
        assert isinstance(result.profit_factor, float)
        assert isinstance(result.max_drawdown_pct, float)

    def test_backtest_result_serialises(self):
        engine = ScannerBacktestEngine(
            scanner_name="precision_alpha",
            timeframe=BacktestTimeframe.M1,
            random_seed=42,
        )
        signals = self._make_signals(3)
        bars = _make_simulated_bars(80, base=155.0)

        result = engine.run_backtest(signals, bars)
        d = result.to_dict()

        assert isinstance(d, dict)
        assert d["scanner_name"] == "precision_alpha"
        assert "win_rate" in d
        assert "sharpe_ratio" in d
        assert "equity_curve" in d

    def test_backtest_report_generator(self):
        engine = ScannerBacktestEngine(
            scanner_name="precision_alpha",
            timeframe=BacktestTimeframe.M5,
            random_seed=42,
        )
        signals = self._make_signals(8)
        bars = _make_simulated_bars(150, base=155.0, trend=0.15)

        bt_result = engine.run_backtest(signals, bars)
        gen = BacktestReportGenerator()
        report = gen.generate_report(bt_result)

        assert isinstance(report, dict)
        assert "meta" in report
        assert report["meta"]["scanner_name"] == "precision_alpha"
        assert "overview" in report
        assert "risk_adjusted" in report
        assert "statistical" in report

    def test_backtest_with_short_signals(self):
        signals = []
        base_time = datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc)
        for i in range(5):
            signals.append(ScanResult(
                symbol="TSLA",
                scanner_type="precision_alpha",
                direction=SignalDirection.SHORT,
                confidence=78.0,
                entry_price=250.0 - i * 0.5,
                stop_loss=253.0 - i * 0.5,
                targets=[247.0 - i * 0.5, 244.0 - i * 0.5],
                risk_reward=1.5,
                timeframe=TimeFrame.M1,
                timestamp=base_time + timedelta(minutes=i * 5),
                metadata={"regime": "high_vol", "dimensions": {}, "weights": WEIGHTS_HIGH_VOL},
            ))

        engine = ScannerBacktestEngine(
            scanner_name="precision_alpha",
            timeframe=BacktestTimeframe.M1,
            random_seed=42,
        )
        bars = _make_simulated_bars(100, base=250.0, trend=-0.1)
        result = engine.run_backtest(signals, bars)

        assert isinstance(result, ScannerBacktestResult)
        assert result.scanner_name == "precision_alpha"

    def test_backtest_with_date_filter(self):
        engine = ScannerBacktestEngine(
            scanner_name="precision_alpha",
            timeframe=BacktestTimeframe.M1,
            start_date=datetime(2026, 1, 5, 9, 35, tzinfo=timezone.utc),
            end_date=datetime(2026, 1, 5, 9, 50, tzinfo=timezone.utc),
            random_seed=42,
        )
        signals = self._make_signals(10)
        bars = _make_simulated_bars(200, base=155.0)

        result = engine.run_backtest(signals, bars)
        assert result.total_signals <= 10

    def test_trade_simulator_standalone(self):
        from src.scanner.scanner_backtest import NormalisedSignal, TradeDirection
        sim = TradeSimulator(
            default_slippage_pct=0.01,
            default_commission_per_share=0.005,
            default_position_size=10_000.0,
            random_seed=42,
        )
        ns = NormalisedSignal(
            signal_id="test-1",
            symbol="AAPL",
            direction=TradeDirection.LONG,
            confidence=80.0,
            entry_price=155.0,
            stop_loss=152.0,
            target_price=158.0,
            timestamp=datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc),
            scanner_name="precision_alpha",
        )
        bars = _make_simulated_bars(30, base=155.0, trend=0.2)
        trade = sim.simulate_trade(ns, bars)

        assert trade is not None
        assert trade.scanner_name == "precision_alpha"
        assert trade.entry_price > 0
        assert trade.exit_price > 0


# ===================================================================
# 7. End-to-end: scan → backtest
# ===================================================================

class TestEndToEnd:
    @pytest.mark.asyncio
    async def test_scan_then_backtest(self):
        """Run PrecisionAlphaScanner, then feed its results to the backtest engine."""
        scanner = PrecisionAlphaScanner()
        ctx = _make_context(["AAPL"])
        scan_results = await scanner.scan(ctx)

        engine = ScannerBacktestEngine(
            scanner_name="precision_alpha",
            timeframe=BacktestTimeframe.M1,
            random_seed=42,
        )
        bars = _make_simulated_bars(200, base=155.0, trend=0.1)
        bt_result = engine.run_backtest(scan_results, bars)

        assert isinstance(bt_result, ScannerBacktestResult)
        assert bt_result.scanner_name == "precision_alpha"
        assert bt_result.timeframe == "1m"
