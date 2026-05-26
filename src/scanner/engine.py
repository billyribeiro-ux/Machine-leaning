"""
Revolution Alpha Engine - Scanner Engine

Central orchestration engine for running multiple scanners concurrently.
Provides unified interface, result aggregation, alerting, and caching.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Callable, Awaitable, Any
from dataclasses import dataclass, field
from collections import defaultdict
import asyncio
import logging
import uuid
from enum import Enum
from concurrent.futures import ThreadPoolExecutor

from .base import (
    BaseScanner,
    ScanContext,
    MarketData,
    HistoricalData,
    CompositeScanner,
)
from .models import (
    ScanResult,
    ScannerBatchResult,
    ScannerSummary,
    ScanMode,
    ScannerConfig,
    MarketRegime,
    SignalDirection,
    AlertPriority,
    ScanAlert,
    TimeFrame,
)
from .options_scanner import (
    OptionsFlowScanner,
    OptionsSwingScanner,
    GammaExposureScanner,
)
from .squeeze_scanner import (
    ShortSqueezeScanner,
    GammaSqueezeScanner,
    CombinedSqueezeScanner,
)
from .momentum_scanner import (
    MomentumScanner,
    ReversalScanner,
    BreakoutScanner,
)

# Advanced scanners (Phase 2 expansion)
from .volatility_scanner import VolatilityRegimeScanner
from .market_structure_scanner import MarketStructureScanner
from .options_intelligence import OptionsIntelligenceScanner
from .fractal_scanner import FractalInformationScanner
from .breadth_scanner import MarketBreadthScanner
from .wavelet_scanner import WaveletFourierScanner
from .extreme_value_scanner import ExtremeValueScanner
from .composite_alpha import CompositeAlphaScanner
from .ml_adaptive_scanner import AdaptiveScannerFramework

# Phase 3 scanners
from .skew_intelligence import SkewIntelligenceScanner
from .vix_intelligence import VIXDeepIntelligenceScanner
from .gaps_power_scanner import GapsPowerScanner

# Phase 4 scanners — institutional integration + new SOTA
from .mtf_scanner import MultiTimeframeScanner
from .dark_pool_scanner import DarkPoolScanner
from .order_flow_scanner import OrderFlowImbalanceScanner
from .cross_asset_scanner import CrossAssetScanner
from .sentiment_scanner import SentimentAlphaScanner
from .vwap_scanner import VWAPDeviationScanner
from .liquidity_scanner import LiquidityShockScanner
from .precision_alpha import PrecisionAlphaScanner

logger = logging.getLogger(__name__)


class EngineState(str, Enum):
    """Scanner engine states."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class ScannerStats:
    """Statistics for a scanner's performance."""
    scanner_name: str
    total_scans: int = 0
    total_signals: int = 0
    high_confidence_signals: int = 0
    avg_scan_time_ms: float = 0
    error_count: int = 0
    last_scan_time: Optional[datetime] = None

    def update(self, summary: ScannerSummary):
        """Update stats from scanner summary."""
        self.total_scans += 1
        self.total_signals += summary.signals_found
        self.high_confidence_signals += summary.high_confidence_signals
        self.error_count += len(summary.errors)
        self.last_scan_time = summary.completed_at

        # Rolling average of scan time
        scan_time_ms = summary.duration_seconds * 1000
        self.avg_scan_time_ms = (
            (self.avg_scan_time_ms * (self.total_scans - 1) + scan_time_ms)
            / self.total_scans
        )


@dataclass
class EngineConfig:
    """Configuration for the scanner engine."""
    max_concurrent_scanners: int = 5
    scan_interval_seconds: int = 60
    alert_cooldown_seconds: int = 300
    cache_ttl_seconds: int = 30
    enable_alerting: bool = True
    min_alert_confidence: float = 70.0
    dedup_window_seconds: int = 600


AlertCallback = Callable[[ScanAlert], Awaitable[None]]
DataProvider = Callable[[list[str]], Awaitable[dict[str, MarketData]]]
HistoricalDataProvider = Callable[[list[str], TimeFrame], Awaitable[dict[str, HistoricalData]]]
OptionsDataProvider = Callable[[list[str]], Awaitable[dict[str, dict]]]


class ScannerEngine:
    """
    Central scanner orchestration engine.

    Manages multiple scanners, coordinates execution, aggregates results,
    and handles alerting for high-confidence signals.
    """

    def __init__(
        self,
        config: Optional[EngineConfig] = None,
        scanner_config: Optional[ScannerConfig] = None
    ):
        self.config = config or EngineConfig()
        self.scanner_config = scanner_config or ScannerConfig()

        # Scanner registry
        self._scanners: dict[str, BaseScanner] = {}
        self._scanner_stats: dict[str, ScannerStats] = {}

        # State
        self._state = EngineState.IDLE
        self._scan_task: Optional[asyncio.Task] = None
        self._last_scan_results: Optional[ScannerBatchResult] = None

        # Data providers
        self._market_data_provider: Optional[DataProvider] = None
        self._historical_data_provider: Optional[HistoricalDataProvider] = None
        self._options_data_provider: Optional[OptionsDataProvider] = None

        # Alert handling
        self._alert_callbacks: list[AlertCallback] = []
        self._alert_history: dict[str, datetime] = {}  # symbol -> last alert time
        self._recent_alerts: list[ScanAlert] = []

        # Result cache
        self._result_cache: dict[str, tuple[ScanResult, datetime]] = {}

        # Universe
        self._universe: list[str] = []

        # Logger
        self._logger = logging.getLogger(f"{__name__}.ScannerEngine")

        # Initialize default scanners
        self._register_default_scanners()

    def _register_default_scanners(self):
        """Register default scanner instances."""
        # Options scanners
        self.register_scanner(OptionsFlowScanner(config=self.scanner_config))
        self.register_scanner(OptionsSwingScanner(config=self.scanner_config))
        self.register_scanner(GammaExposureScanner(config=self.scanner_config))

        # Squeeze scanners
        self.register_scanner(ShortSqueezeScanner(config=self.scanner_config))
        self.register_scanner(GammaSqueezeScanner(config=self.scanner_config))
        self.register_scanner(CombinedSqueezeScanner(config=self.scanner_config))

        # Momentum/Pattern scanners
        self.register_scanner(MomentumScanner(config=self.scanner_config))
        self.register_scanner(ReversalScanner(config=self.scanner_config))
        self.register_scanner(BreakoutScanner(config=self.scanner_config))

        # Advanced scanners (Phase 2)
        self.register_scanner(VolatilityRegimeScanner(config=self.scanner_config))
        self.register_scanner(MarketStructureScanner(config=self.scanner_config))
        self.register_scanner(OptionsIntelligenceScanner(config=self.scanner_config))
        self.register_scanner(FractalInformationScanner(config=self.scanner_config))
        self.register_scanner(MarketBreadthScanner(config=self.scanner_config))
        self.register_scanner(WaveletFourierScanner(config=self.scanner_config))
        self.register_scanner(ExtremeValueScanner(config=self.scanner_config))

        # Phase 3 scanners
        self.register_scanner(SkewIntelligenceScanner(config=self.scanner_config))
        self.register_scanner(VIXDeepIntelligenceScanner(config=self.scanner_config))
        self.register_scanner(GapsPowerScanner(config=self.scanner_config))

        # Phase 4 — Institutional integration + SOTA scanners
        self.register_scanner(MultiTimeframeScanner(config=self.scanner_config))
        self.register_scanner(DarkPoolScanner(config=self.scanner_config))
        self.register_scanner(OrderFlowImbalanceScanner(config=self.scanner_config))
        self.register_scanner(CrossAssetScanner(config=self.scanner_config))
        self.register_scanner(SentimentAlphaScanner(config=self.scanner_config))
        self.register_scanner(VWAPDeviationScanner(config=self.scanner_config))
        self.register_scanner(LiquidityShockScanner(config=self.scanner_config))

        # Phase 5 — Precision Alpha (unified 8-dimension day-trading engine)
        self.register_scanner(PrecisionAlphaScanner(config=self.scanner_config))

        # Meta-scanners (combine signals from above)
        composite = CompositeAlphaScanner(config=self.scanner_config)
        for name, scanner in list(self._scanners.items()):
            composite.register_sub_scanner(scanner)
        self.register_scanner(composite)

    @property
    def state(self) -> EngineState:
        """Get current engine state."""
        return self._state

    @property
    def is_running(self) -> bool:
        """Check if engine is actively running."""
        return self._state == EngineState.RUNNING

    @property
    def scanners(self) -> dict[str, BaseScanner]:
        """Get registered scanners."""
        return self._scanners.copy()

    @property
    def stats(self) -> dict[str, ScannerStats]:
        """Get scanner statistics."""
        return self._scanner_stats.copy()

    @property
    def last_results(self) -> Optional[ScannerBatchResult]:
        """Get results from last scan."""
        return self._last_scan_results

    @property
    def recent_alerts(self) -> list[ScanAlert]:
        """Get recent alerts."""
        return self._recent_alerts.copy()

    def register_scanner(self, scanner: BaseScanner) -> None:
        """Register a scanner with the engine."""
        self._scanners[scanner.name] = scanner
        self._scanner_stats[scanner.name] = ScannerStats(scanner_name=scanner.name)
        self._logger.info(f"Registered scanner: {scanner.name}")

    def unregister_scanner(self, name: str) -> bool:
        """Unregister a scanner by name."""
        if name in self._scanners:
            del self._scanners[name]
            del self._scanner_stats[name]
            self._logger.info(f"Unregistered scanner: {name}")
            return True
        return False

    def set_universe(self, symbols: list[str]) -> None:
        """Set the universe of symbols to scan."""
        self._universe = list(set(symbols))
        self._logger.info(f"Universe set to {len(self._universe)} symbols")

    def set_market_data_provider(self, provider: DataProvider) -> None:
        """Set the market data provider function."""
        self._market_data_provider = provider

    def set_historical_data_provider(self, provider: HistoricalDataProvider) -> None:
        """Set the historical data provider function."""
        self._historical_data_provider = provider

    def set_options_data_provider(self, provider: OptionsDataProvider) -> None:
        """Set the options data provider function."""
        self._options_data_provider = provider

    def add_alert_callback(self, callback: AlertCallback) -> None:
        """Add a callback for alerts."""
        self._alert_callbacks.append(callback)

    async def start(self, continuous: bool = False) -> None:
        """
        Start the scanner engine.

        Args:
            continuous: If True, run scans continuously at configured interval
        """
        if self._state == EngineState.RUNNING:
            self._logger.warning("Engine already running")
            return

        self._state = EngineState.RUNNING
        self._logger.info("Scanner engine started")

        if continuous:
            self._scan_task = asyncio.create_task(self._continuous_scan_loop())
        else:
            await self._run_scan_cycle()

    async def stop(self) -> None:
        """Stop the scanner engine."""
        self._state = EngineState.STOPPED

        if self._scan_task:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
            self._scan_task = None

        self._logger.info("Scanner engine stopped")

    async def pause(self) -> None:
        """Pause the scanner engine."""
        if self._state == EngineState.RUNNING:
            self._state = EngineState.PAUSED
            self._logger.info("Scanner engine paused")

    async def resume(self) -> None:
        """Resume the scanner engine."""
        if self._state == EngineState.PAUSED:
            self._state = EngineState.RUNNING
            self._logger.info("Scanner engine resumed")

    async def _continuous_scan_loop(self) -> None:
        """Continuous scanning loop."""
        while self._state in (EngineState.RUNNING, EngineState.PAUSED):
            if self._state == EngineState.RUNNING:
                try:
                    await self._run_scan_cycle()
                except Exception as e:
                    self._logger.error(f"Scan cycle error: {e}", exc_info=True)
                    self._state = EngineState.ERROR

            await asyncio.sleep(self.config.scan_interval_seconds)

    async def _run_scan_cycle(self) -> ScannerBatchResult:
        """Run a complete scan cycle with all enabled scanners."""
        start_time = datetime.now(timezone.utc)
        batch_id = str(uuid.uuid4())

        self._logger.info(f"Starting scan cycle {batch_id}")

        # Build scan context
        context = await self._build_scan_context()

        # Run all scanners
        all_results: list[ScanResult] = []
        all_summaries: list[ScannerSummary] = []

        # Group scanners by mode for parallel execution
        scanner_tasks = []
        for name, scanner in self._scanners.items():
            if self._should_run_scanner(scanner, context):
                scanner_tasks.append(self._run_scanner(scanner, context))

        # Execute scanners with concurrency limit
        semaphore = asyncio.Semaphore(self.config.max_concurrent_scanners)

        async def run_with_semaphore(task):
            async with semaphore:
                return await task

        results_list = await asyncio.gather(
            *[run_with_semaphore(task) for task in scanner_tasks],
            return_exceptions=True
        )

        # Process results
        for result in results_list:
            if isinstance(result, Exception):
                self._logger.warning(f"Scanner execution error: {result}")
                continue

            results, summary = result
            all_results.extend(results)
            all_summaries.append(summary)

            # Update stats
            if summary.scanner_name in self._scanner_stats:
                self._scanner_stats[summary.scanner_name].update(summary)

        # Detect market regime
        market_regime = self._detect_market_regime(context, all_results)

        # Deduplicate and rank results
        deduped_results = self._deduplicate_results(all_results)
        ranked_results = self._rank_results(deduped_results)

        # Create batch result
        batch_result = ScannerBatchResult(
            batch_id=batch_id,
            results=ranked_results,
            summaries=all_summaries,
            market_regime=market_regime,
            timestamp=start_time,
        )

        self._last_scan_results = batch_result

        # Process alerts
        if self.config.enable_alerting:
            await self._process_alerts(batch_result)

        # Update cache
        self._update_cache(ranked_results)

        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        self._logger.info(
            f"Scan cycle {batch_id} complete: "
            f"{len(ranked_results)} signals in {elapsed:.2f}s"
        )

        return batch_result

    async def _build_scan_context(self) -> ScanContext:
        """Build scan context with market data."""
        context = ScanContext.create(
            config=self.scanner_config,
            universe=self._universe,
        )

        # Fetch market data
        if self._market_data_provider and self._universe:
            try:
                context.market_data = await self._market_data_provider(self._universe)
            except Exception as e:
                self._logger.error(f"Failed to fetch market data: {e}")

        # Fetch historical data
        if self._historical_data_provider and self._universe:
            try:
                for timeframe in self.scanner_config.timeframes:
                    hist_data = await self._historical_data_provider(self._universe, timeframe)
                    context.historical_data.update(hist_data)
            except Exception as e:
                self._logger.error(f"Failed to fetch historical data: {e}")

        # Fetch options data
        if self._options_data_provider and self._universe:
            try:
                context.options_data = await self._options_data_provider(self._universe)
            except Exception as e:
                self._logger.error(f"Failed to fetch options data: {e}")

        return context

    def _should_run_scanner(self, scanner: BaseScanner, context: ScanContext) -> bool:
        """Check if scanner should run based on config and context."""
        # Check scan modes
        if ScanMode.ALL not in self.scanner_config.scan_modes:
            if scanner.scan_mode not in self.scanner_config.scan_modes:
                return False

        return True

    async def _run_scanner(
        self,
        scanner: BaseScanner,
        context: ScanContext
    ) -> tuple[list[ScanResult], ScannerSummary]:
        """Run a single scanner and return results."""
        try:
            return await scanner.execute(context)
        except Exception as e:
            self._logger.error(f"Scanner {scanner.name} failed: {e}", exc_info=True)
            # Return empty result with error summary
            return [], ScannerSummary(
                scanner_name=scanner.name,
                scan_mode=scanner.scan_mode,
                symbols_scanned=len(context.universe),
                signals_found=0,
                high_confidence_signals=0,
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                errors=[str(e)]
            )

    def _detect_market_regime(
        self,
        context: ScanContext,
        results: list[ScanResult]
    ) -> MarketRegime:
        """Detect current market regime based on context and results."""
        # Simple regime detection based on signal direction bias
        if not results:
            return MarketRegime.RANGING

        long_count = sum(1 for r in results if r.direction == SignalDirection.LONG)
        short_count = sum(1 for r in results if r.direction == SignalDirection.SHORT)
        total = len(results)

        if long_count / total > 0.7:
            return MarketRegime.TRENDING_UP
        elif short_count / total > 0.7:
            return MarketRegime.TRENDING_DOWN

        # Check volatility from market data
        high_vol_count = 0
        for symbol, data in context.market_data.items():
            if data.atr and data.close:
                atr_pct = (data.atr / data.close) * 100
                if atr_pct > 3:  # High volatility threshold
                    high_vol_count += 1

        if high_vol_count > len(context.market_data) * 0.5:
            return MarketRegime.HIGH_VOLATILITY

        return MarketRegime.RANGING

    def _deduplicate_results(self, results: list[ScanResult]) -> list[ScanResult]:
        """Deduplicate results by symbol, keeping highest confidence."""
        by_symbol: dict[str, ScanResult] = {}

        for result in results:
            key = f"{result.symbol}_{result.direction}"
            if key not in by_symbol or result.confidence > by_symbol[key].confidence:
                by_symbol[key] = result

        return list(by_symbol.values())

    def _rank_results(self, results: list[ScanResult]) -> list[ScanResult]:
        """Rank results by confidence and other factors."""
        def score(result: ScanResult) -> float:
            score_val = result.confidence

            # Boost for risk/reward
            if result.risk_reward and result.risk_reward >= 2:
                score_val += 5
            if result.risk_reward and result.risk_reward >= 3:
                score_val += 5

            return score_val

        return sorted(results, key=score, reverse=True)

    async def _process_alerts(self, batch_result: ScannerBatchResult) -> None:
        """Process results and generate alerts for high-confidence signals."""
        now = datetime.now(timezone.utc)

        for result in batch_result.results:
            # Check confidence threshold
            if result.confidence < self.config.min_alert_confidence:
                continue

            # Check alert cooldown
            last_alert = self._alert_history.get(result.symbol)
            if last_alert:
                elapsed = (now - last_alert).total_seconds()
                if elapsed < self.config.alert_cooldown_seconds:
                    continue

            # Determine priority
            if result.confidence >= 90:
                priority = AlertPriority.CRITICAL
            elif result.confidence >= 80:
                priority = AlertPriority.HIGH
            elif result.confidence >= 70:
                priority = AlertPriority.MEDIUM
            else:
                priority = AlertPriority.LOW

            # Create alert
            alert = ScanAlert(
                alert_id=str(uuid.uuid4()),
                scan_result=result,
                priority=priority,
                message=self._format_alert_message(result),
                created_at=now,
                expires_at=now + timedelta(hours=1)
            )

            # Update history
            self._alert_history[result.symbol] = now
            self._recent_alerts.append(alert)

            # Trim recent alerts
            if len(self._recent_alerts) > 100:
                self._recent_alerts = self._recent_alerts[-100:]

            # Fire callbacks
            for callback in self._alert_callbacks:
                try:
                    await callback(alert)
                except Exception as e:
                    self._logger.error(f"Alert callback error: {e}")

    def _format_alert_message(self, result: ScanResult) -> str:
        """Format alert message from scan result."""
        direction = "LONG" if result.direction == SignalDirection.LONG else "SHORT"
        message = (
            f"[{result.scanner_type.upper()}] {result.symbol} - {direction} "
            f"| Confidence: {result.confidence:.1f}%"
        )

        if result.entry_price:
            message += f" | Entry: ${result.entry_price:.2f}"

        if result.stop_loss:
            message += f" | Stop: ${result.stop_loss:.2f}"

        if result.targets:
            message += f" | Target: ${result.targets[0]:.2f}"

        if result.risk_reward:
            message += f" | R:R {result.risk_reward:.1f}"

        return message

    def _update_cache(self, results: list[ScanResult]) -> None:
        """Update result cache."""
        now = datetime.now(timezone.utc)
        ttl = timedelta(seconds=self.config.cache_ttl_seconds)

        # Add new results
        for result in results:
            self._result_cache[result.symbol] = (result, now)

        # Clean expired entries
        expired = [
            symbol for symbol, (_, timestamp) in self._result_cache.items()
            if now - timestamp > ttl
        ]
        for symbol in expired:
            del self._result_cache[symbol]

    def get_cached_result(self, symbol: str) -> Optional[ScanResult]:
        """Get cached result for a symbol."""
        if symbol in self._result_cache:
            result, timestamp = self._result_cache[symbol]
            ttl = timedelta(seconds=self.config.cache_ttl_seconds)
            if datetime.now(timezone.utc) - timestamp <= ttl:
                return result
        return None

    async def scan_single(self, symbol: str) -> list[ScanResult]:
        """Run all scanners on a single symbol."""
        # Check cache first
        cached = self.get_cached_result(symbol)
        if cached:
            return [cached]

        # Build minimal context
        original_universe = self._universe
        self._universe = [symbol]

        try:
            batch = await self._run_scan_cycle()
            return batch.results
        finally:
            self._universe = original_universe

    async def scan_with_mode(
        self,
        mode: ScanMode,
        symbols: Optional[list[str]] = None
    ) -> ScannerBatchResult:
        """Run scan with specific mode."""
        # Store original config
        original_modes = self.scanner_config.scan_modes
        original_universe = self._universe

        try:
            self.scanner_config.scan_modes = [mode]
            if symbols:
                self._universe = symbols

            return await self._run_scan_cycle()
        finally:
            self.scanner_config.scan_modes = original_modes
            self._universe = original_universe

    def get_summary(self) -> dict[str, Any]:
        """Get engine summary statistics."""
        total_scans = sum(s.total_scans for s in self._scanner_stats.values())
        total_signals = sum(s.total_signals for s in self._scanner_stats.values())
        total_errors = sum(s.error_count for s in self._scanner_stats.values())

        return {
            "state": self._state.value,
            "registered_scanners": len(self._scanners),
            "universe_size": len(self._universe),
            "total_scans": total_scans,
            "total_signals": total_signals,
            "total_errors": total_errors,
            "cached_results": len(self._result_cache),
            "recent_alerts": len(self._recent_alerts),
            "scanner_stats": {
                name: {
                    "total_scans": stats.total_scans,
                    "total_signals": stats.total_signals,
                    "avg_scan_time_ms": round(stats.avg_scan_time_ms, 2),
                    "error_rate": (
                        stats.error_count / stats.total_scans
                        if stats.total_scans > 0 else 0
                    ),
                }
                for name, stats in self._scanner_stats.items()
            }
        }


# Convenience factory functions

def create_options_engine(
    config: Optional[ScannerConfig] = None
) -> ScannerEngine:
    """Create engine configured for options scanning."""
    engine_config = EngineConfig(
        max_concurrent_scanners=3,
        scan_interval_seconds=30,
        min_alert_confidence=65.0,
    )

    scanner_config = config or ScannerConfig(
        scan_modes=[ScanMode.OPTIONS_DAY, ScanMode.OPTIONS_SWING],
        min_confidence=60.0,
    )

    engine = ScannerEngine(engine_config, scanner_config)

    # Remove non-options scanners
    for name in list(engine._scanners.keys()):
        if "options" not in name and "gamma" not in name:
            engine.unregister_scanner(name)

    return engine


def create_squeeze_engine(
    config: Optional[ScannerConfig] = None
) -> ScannerEngine:
    """Create engine configured for squeeze detection."""
    engine_config = EngineConfig(
        max_concurrent_scanners=3,
        scan_interval_seconds=60,
        min_alert_confidence=70.0,
    )

    scanner_config = config or ScannerConfig(
        scan_modes=[ScanMode.SQUEEZE],
        min_confidence=65.0,
    )

    engine = ScannerEngine(engine_config, scanner_config)

    # Remove non-squeeze scanners
    for name in list(engine._scanners.keys()):
        if "squeeze" not in name:
            engine.unregister_scanner(name)

    return engine


def create_momentum_engine(
    config: Optional[ScannerConfig] = None
) -> ScannerEngine:
    """Create engine configured for momentum/pattern scanning."""
    engine_config = EngineConfig(
        max_concurrent_scanners=3,
        scan_interval_seconds=60,
        min_alert_confidence=65.0,
    )

    scanner_config = config or ScannerConfig(
        scan_modes=[ScanMode.MOMENTUM, ScanMode.REVERSAL, ScanMode.BREAKOUT],
        min_confidence=60.0,
    )

    engine = ScannerEngine(engine_config, scanner_config)

    # Remove non-momentum scanners
    keep = {"momentum", "reversal", "breakout"}
    for name in list(engine._scanners.keys()):
        if name not in keep:
            engine.unregister_scanner(name)

    return engine


def create_full_engine(
    config: Optional[ScannerConfig] = None
) -> ScannerEngine:
    """Create engine with all scanners enabled."""
    engine_config = EngineConfig(
        max_concurrent_scanners=5,
        scan_interval_seconds=60,
        min_alert_confidence=70.0,
    )

    scanner_config = config or ScannerConfig(
        scan_modes=[ScanMode.ALL],
        min_confidence=60.0,
    )

    return ScannerEngine(engine_config, scanner_config)


def create_advanced_engine(
    config: Optional[ScannerConfig] = None
) -> ScannerEngine:
    """
    Create engine with all advanced scanners and the adaptive
    ML framework for self-learning signal combination.

    This is the ultimate configuration that includes:
    - All base scanners (options, squeeze, momentum)
    - Volatility regime detection (GARCH, regime-switching)
    - Predictive structure intelligence (continuation/reversal breaks, PIZ, DSAZ)
    - Advanced options intelligence (IV surface, GEX, vanna/charm)
    - Fractal & information theory (Hurst, entropy, transfer entropy)
    - Market breadth & internals (AD line, McClellan, breadth thrusts)
    - Wavelet & Fourier analysis (cycle detection, spectral entropy)
    - Extreme value theory (tail risk, VaR, CVaR)
    - Composite alpha scanner (Bayesian model averaging)
    - Self-learning adaptive framework (Thompson Sampling, drift detection)
    - Skew & market internals intelligence (deep skew, PCR, intermarket)
    - VIX deep intelligence (full VIX chain, VVIX, term structure, patterns)
    - Gaps power scanner (historical gap stats, fill rates, predictions)
    - Universal backtest framework (win rate tracking, 1m to 30yr timeframes)
    """
    engine_config = EngineConfig(
        max_concurrent_scanners=12,
        scan_interval_seconds=60,
        min_alert_confidence=65.0,
    )

    scanner_config = config or ScannerConfig(
        scan_modes=[ScanMode.ALL],
        min_confidence=55.0,
    )

    engine = ScannerEngine(engine_config, scanner_config)

    # Register adaptive framework wrapping all scanners
    adaptive = AdaptiveScannerFramework(config=scanner_config)
    for name, scanner in list(engine._scanners.items()):
        if name != "composite_alpha":
            adaptive.register_scan(name, scanner)
    engine.register_scanner(adaptive)

    return engine
