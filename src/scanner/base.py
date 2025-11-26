"""
Revolution Alpha Engine - Base Scanner Classes

Abstract base classes and interfaces for the scanner system.
Provides the foundation for all specific scanner implementations.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, TypeVar, Generic, AsyncIterator
from dataclasses import dataclass, field
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
import uuid

from .models import (
    ScanResult,
    ScanMode,
    ScannerConfig,
    ScannerSummary,
    MarketRegime,
    TimeFrame,
    SignalDirection,
)

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=ScanResult)


@dataclass
class MarketData:
    """Container for market data used in scanning."""
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    bid_size: Optional[int] = None
    ask_size: Optional[int] = None

    # Technical indicators (computed)
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    ema_9: Optional[float] = None
    ema_21: Optional[float] = None
    rsi: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    bollinger_upper: Optional[float] = None
    bollinger_lower: Optional[float] = None
    bollinger_mid: Optional[float] = None
    atr: Optional[float] = None
    adx: Optional[float] = None

    # Additional context
    avg_volume_20: Optional[float] = None
    relative_volume: Optional[float] = None
    gap_percent: Optional[float] = None

    @property
    def spread(self) -> Optional[float]:
        """Calculate bid-ask spread."""
        if self.bid and self.ask:
            return self.ask - self.bid
        return None

    @property
    def mid_price(self) -> Optional[float]:
        """Calculate mid price."""
        if self.bid and self.ask:
            return (self.bid + self.ask) / 2
        return None

    @property
    def range_pct(self) -> float:
        """Calculate intraday range as percentage."""
        if self.low > 0:
            return ((self.high - self.low) / self.low) * 100
        return 0

    @property
    def body_pct(self) -> float:
        """Calculate candle body as percentage of range."""
        range_size = self.high - self.low
        if range_size > 0:
            body = abs(self.close - self.open)
            return (body / range_size) * 100
        return 0

    @property
    def is_bullish_candle(self) -> bool:
        """Check if candle is bullish."""
        return self.close > self.open


@dataclass
class HistoricalData:
    """Container for historical price data."""
    symbol: str
    timeframe: TimeFrame
    bars: list[MarketData] = field(default_factory=list)

    @property
    def latest(self) -> Optional[MarketData]:
        """Get most recent bar."""
        return self.bars[-1] if self.bars else None

    @property
    def closes(self) -> list[float]:
        """Get list of closing prices."""
        return [bar.close for bar in self.bars]

    @property
    def highs(self) -> list[float]:
        """Get list of high prices."""
        return [bar.high for bar in self.bars]

    @property
    def lows(self) -> list[float]:
        """Get list of low prices."""
        return [bar.low for bar in self.bars]

    @property
    def volumes(self) -> list[int]:
        """Get list of volumes."""
        return [bar.volume for bar in self.bars]

    def slice(self, n: int) -> 'HistoricalData':
        """Get last n bars."""
        return HistoricalData(
            symbol=self.symbol,
            timeframe=self.timeframe,
            bars=self.bars[-n:] if n < len(self.bars) else self.bars.copy()
        )


@dataclass
class ScanContext:
    """Context object passed to scanners during execution."""
    scan_id: str
    timestamp: datetime
    market_regime: MarketRegime
    config: ScannerConfig
    universe: list[str]  # Symbols to scan
    market_data: dict[str, MarketData] = field(default_factory=dict)
    historical_data: dict[str, HistoricalData] = field(default_factory=dict)
    options_data: dict[str, dict] = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        config: ScannerConfig,
        universe: list[str],
        market_regime: MarketRegime = MarketRegime.RANGING
    ) -> 'ScanContext':
        """Factory method to create a new scan context."""
        return cls(
            scan_id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            market_regime=market_regime,
            config=config,
            universe=universe
        )


class BaseScanner(ABC, Generic[T]):
    """
    Abstract base class for all scanners.

    Provides common functionality and enforces interface for scanner implementations.
    All scanners must implement the scan() method.
    """

    def __init__(
        self,
        name: str,
        scan_mode: ScanMode,
        config: Optional[ScannerConfig] = None
    ):
        self.name = name
        self.scan_mode = scan_mode
        self.config = config or ScannerConfig()
        self._is_running = False
        self._last_scan_time: Optional[datetime] = None
        self._scan_count = 0
        self._error_count = 0
        self._logger = logging.getLogger(f"{__name__}.{self.name}")

    @property
    def is_running(self) -> bool:
        """Check if scanner is currently running."""
        return self._is_running

    @property
    def last_scan_time(self) -> Optional[datetime]:
        """Get timestamp of last scan."""
        return self._last_scan_time

    @abstractmethod
    async def scan(self, context: ScanContext) -> list[T]:
        """
        Execute the scan and return results.

        Args:
            context: Scan context containing market data and configuration

        Returns:
            List of scan results matching the scanner type
        """
        pass

    @abstractmethod
    def validate_signal(self, result: T, context: ScanContext) -> bool:
        """
        Validate a scan result against current market conditions.

        Args:
            result: The scan result to validate
            context: Current scan context

        Returns:
            True if the signal is valid, False otherwise
        """
        pass

    async def pre_scan(self, context: ScanContext) -> None:
        """Hook called before scan execution. Override for custom logic."""
        self._is_running = True
        self._logger.debug(f"Starting scan for {len(context.universe)} symbols")

    async def post_scan(
        self,
        context: ScanContext,
        results: list[T]
    ) -> list[T]:
        """
        Hook called after scan execution.

        Override for custom post-processing logic.
        Default implementation filters by minimum confidence.
        """
        self._is_running = False
        self._last_scan_time = datetime.utcnow()
        self._scan_count += 1

        # Filter by minimum confidence
        filtered = [
            r for r in results
            if r.confidence >= self.config.min_confidence
        ]

        self._logger.debug(
            f"Scan complete: {len(results)} raw signals, "
            f"{len(filtered)} after filtering"
        )

        return filtered

    async def execute(self, context: ScanContext) -> tuple[list[T], ScannerSummary]:
        """
        Execute the scanner with pre/post hooks and generate summary.

        Args:
            context: Scan context

        Returns:
            Tuple of (results list, scanner summary)
        """
        start_time = datetime.utcnow()
        errors: list[str] = []
        results: list[T] = []

        try:
            await self.pre_scan(context)
            results = await self.scan(context)
            results = await self.post_scan(context, results)

            # Validate signals
            validated_results = []
            for result in results:
                try:
                    if self.validate_signal(result, context):
                        validated_results.append(result)
                except Exception as e:
                    self._logger.warning(f"Signal validation error: {e}")
                    errors.append(f"Validation error for {result.symbol}: {str(e)}")

            results = validated_results

        except Exception as e:
            self._error_count += 1
            self._logger.error(f"Scan execution error: {e}", exc_info=True)
            errors.append(str(e))
            self._is_running = False

        end_time = datetime.utcnow()

        summary = ScannerSummary(
            scanner_name=self.name,
            scan_mode=self.scan_mode,
            symbols_scanned=len(context.universe),
            signals_found=len(results),
            high_confidence_signals=sum(1 for r in results if r.confidence >= 70),
            started_at=start_time,
            completed_at=end_time,
            errors=errors
        )

        return results, summary

    def apply_filters(
        self,
        data: MarketData,
        config: Optional[ScannerConfig] = None
    ) -> bool:
        """
        Apply standard filters to market data.

        Args:
            data: Market data to filter
            config: Optional config override

        Returns:
            True if data passes all filters
        """
        cfg = config or self.config

        # Price filter
        if data.close < cfg.min_price or data.close > cfg.max_price:
            return False

        # Volume filter
        if data.volume < cfg.min_volume:
            return False

        return True

    def calculate_risk_reward(
        self,
        entry: float,
        stop_loss: float,
        target: float
    ) -> float:
        """Calculate risk/reward ratio."""
        risk = abs(entry - stop_loss)
        reward = abs(target - entry)

        if risk == 0:
            return 0

        return round(reward / risk, 2)

    def calculate_stop_loss(
        self,
        entry: float,
        direction: SignalDirection,
        atr: Optional[float] = None,
        atr_multiplier: float = 2.0,
        pct_stop: float = 2.0
    ) -> float:
        """
        Calculate stop loss based on ATR or percentage.

        Args:
            entry: Entry price
            direction: Trade direction
            atr: Average True Range (optional)
            atr_multiplier: Multiplier for ATR-based stop
            pct_stop: Percentage stop if ATR not available

        Returns:
            Stop loss price
        """
        if atr is not None:
            stop_distance = atr * atr_multiplier
        else:
            stop_distance = entry * (pct_stop / 100)

        if direction == SignalDirection.LONG:
            return round(entry - stop_distance, 2)
        elif direction == SignalDirection.SHORT:
            return round(entry + stop_distance, 2)

        return entry

    def calculate_targets(
        self,
        entry: float,
        stop_loss: float,
        direction: SignalDirection,
        rr_ratios: list[float] = [1.5, 2.0, 3.0]
    ) -> list[float]:
        """
        Calculate price targets based on risk/reward ratios.

        Args:
            entry: Entry price
            stop_loss: Stop loss price
            direction: Trade direction
            rr_ratios: List of R/R ratios for targets

        Returns:
            List of price targets
        """
        risk = abs(entry - stop_loss)
        targets = []

        for rr in rr_ratios:
            if direction == SignalDirection.LONG:
                target = entry + (risk * rr)
            elif direction == SignalDirection.SHORT:
                target = entry - (risk * rr)
            else:
                target = entry

            targets.append(round(target, 2))

        return targets


class AsyncStreamingScanner(BaseScanner[T]):
    """
    Base class for scanners that stream results as they're found.

    Useful for large universes where you want results as soon as available.
    """

    def __init__(
        self,
        name: str,
        scan_mode: ScanMode,
        config: Optional[ScannerConfig] = None,
        batch_size: int = 50
    ):
        super().__init__(name, scan_mode, config)
        self.batch_size = batch_size

    @abstractmethod
    async def scan_symbol(
        self,
        symbol: str,
        context: ScanContext
    ) -> Optional[T]:
        """
        Scan a single symbol.

        Args:
            symbol: Symbol to scan
            context: Scan context

        Returns:
            Scan result if signal found, None otherwise
        """
        pass

    async def scan(self, context: ScanContext) -> list[T]:
        """Execute scan by iterating through symbols."""
        results = []
        async for result in self.stream_scan(context):
            results.append(result)
        return results

    async def stream_scan(
        self,
        context: ScanContext
    ) -> AsyncIterator[T]:
        """
        Stream scan results as they're found.

        Yields:
            Scan results as they're discovered
        """
        await self.pre_scan(context)

        # Process in batches for efficiency
        for i in range(0, len(context.universe), self.batch_size):
            batch = context.universe[i:i + self.batch_size]

            # Process batch concurrently
            tasks = [
                self.scan_symbol(symbol, context)
                for symbol in batch
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    self._logger.warning(f"Symbol scan error: {result}")
                    continue

                if result is not None:
                    if result.confidence >= self.config.min_confidence:
                        yield result


class CompositeScanner(BaseScanner[ScanResult]):
    """
    Scanner that combines multiple scanners and aggregates results.

    Useful for running multiple scan strategies simultaneously.
    """

    def __init__(
        self,
        name: str,
        scanners: list[BaseScanner],
        config: Optional[ScannerConfig] = None,
        min_scanner_agreement: int = 1
    ):
        super().__init__(name, ScanMode.ALL, config)
        self.scanners = scanners
        self.min_scanner_agreement = min_scanner_agreement

    async def scan(self, context: ScanContext) -> list[ScanResult]:
        """Run all child scanners and aggregate results."""
        all_results: list[ScanResult] = []

        # Run all scanners concurrently
        tasks = [scanner.execute(context) for scanner in self.scanners]
        scanner_outputs = await asyncio.gather(*tasks, return_exceptions=True)

        for output in scanner_outputs:
            if isinstance(output, Exception):
                self._logger.warning(f"Child scanner error: {output}")
                continue

            results, _ = output
            all_results.extend(results)

        # Aggregate results by symbol
        return self._aggregate_results(all_results)

    def _aggregate_results(
        self,
        results: list[ScanResult]
    ) -> list[ScanResult]:
        """
        Aggregate results from multiple scanners.

        Combines signals for the same symbol and direction.
        """
        from collections import defaultdict

        # Group by symbol and direction
        grouped: dict[tuple[str, SignalDirection], list[ScanResult]] = defaultdict(list)

        for result in results:
            key = (result.symbol, result.direction)
            grouped[key].append(result)

        # Filter by minimum agreement and create aggregated results
        aggregated: list[ScanResult] = []

        for (symbol, direction), symbol_results in grouped.items():
            if len(symbol_results) >= self.min_scanner_agreement:
                # Take highest confidence result and boost confidence
                best = max(symbol_results, key=lambda x: x.confidence)

                # Boost confidence based on scanner agreement
                agreement_bonus = min(10 * (len(symbol_results) - 1), 20)
                boosted_confidence = min(100, best.confidence + agreement_bonus)

                # Create new result with boosted confidence
                aggregated.append(ScanResult(
                    symbol=symbol,
                    scanner_type=f"{self.name}_composite",
                    direction=direction,
                    confidence=boosted_confidence,
                    entry_price=best.entry_price,
                    stop_loss=best.stop_loss,
                    targets=best.targets,
                    risk_reward=best.risk_reward,
                    timestamp=datetime.utcnow(),
                    metadata={
                        "scanner_count": len(symbol_results),
                        "source_scanners": [r.scanner_type for r in symbol_results],
                        "original_confidence": best.confidence
                    }
                ))

        return sorted(aggregated, key=lambda x: x.confidence, reverse=True)

    def validate_signal(self, result: ScanResult, context: ScanContext) -> bool:
        """Validate aggregated signal."""
        # Require minimum confidence after aggregation
        return result.confidence >= self.config.min_confidence
