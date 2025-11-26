"""
Revolution Alpha Engine - Momentum & Pattern Scanners

Institutional-grade scanners for detecting:
- Momentum breakouts and continuations
- Reversal patterns with divergence
- Breakout setups from consolidation
- Mean reversion opportunities
"""

from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field
import logging
import math

from .base import (
    AsyncStreamingScanner,
    BaseScanner,
    ScanContext,
    MarketData,
    HistoricalData,
)
from .models import (
    MomentumScanResult,
    ReversalScanResult,
    BreakoutScanResult,
    ScanResult,
    ScanMode,
    SignalDirection,
    ScannerConfig,
    TimeFrame,
    SignalStrength,
)

logger = logging.getLogger(__name__)


@dataclass
class MomentumMetrics:
    """Calculated momentum metrics for a symbol."""
    symbol: str
    rsi: float
    macd: float
    macd_signal: float
    macd_histogram: float
    adx: float
    plus_di: float
    minus_di: float
    stochastic_k: float
    stochastic_d: float
    cci: float
    mfi: float
    roc: float  # Rate of change

    @property
    def is_bullish_momentum(self) -> bool:
        """Check for bullish momentum alignment."""
        return (
            self.macd_histogram > 0 and
            self.rsi > 50 and self.rsi < 70 and
            self.adx > 20 and
            self.plus_di > self.minus_di
        )

    @property
    def is_bearish_momentum(self) -> bool:
        """Check for bearish momentum alignment."""
        return (
            self.macd_histogram < 0 and
            self.rsi < 50 and self.rsi > 30 and
            self.adx > 20 and
            self.minus_di > self.plus_di
        )

    @property
    def momentum_score(self) -> float:
        """Calculate overall momentum score (-100 to 100)."""
        score = 0.0

        # RSI component
        if self.rsi > 50:
            score += (self.rsi - 50) * 0.5
        else:
            score -= (50 - self.rsi) * 0.5

        # MACD component
        if self.macd_histogram > 0:
            score += min(25, abs(self.macd_histogram) * 100)
        else:
            score -= min(25, abs(self.macd_histogram) * 100)

        # ADX/DI component
        if self.adx > 20:
            di_diff = self.plus_di - self.minus_di
            score += di_diff * 0.5

        # Stochastic component
        if self.stochastic_k > 50:
            score += (self.stochastic_k - 50) * 0.3
        else:
            score -= (50 - self.stochastic_k) * 0.3

        return max(-100, min(100, score))


@dataclass
class PatternMatch:
    """Represents a detected chart pattern."""
    pattern_name: str
    pattern_type: str  # "continuation", "reversal"
    direction: SignalDirection
    confidence: float
    entry_trigger: float
    invalidation_level: float
    target: float
    supporting_indicators: list[str] = field(default_factory=list)


class MomentumScanner(AsyncStreamingScanner[MomentumScanResult]):
    """
    Scanner for detecting momentum-based trading opportunities.

    Uses RSI, MACD, ADX, and volume analysis to identify
    high-probability momentum continuations.
    """

    def __init__(
        self,
        config: Optional[ScannerConfig] = None
    ):
        super().__init__(
            name="momentum",
            scan_mode=ScanMode.MOMENTUM,
            config=config
        )

        # Momentum thresholds
        self.min_adx = 20  # Minimum ADX for trending market
        self.rsi_oversold = 30
        self.rsi_overbought = 70
        self.min_volume_ratio = 1.5

    async def scan_symbol(
        self,
        symbol: str,
        context: ScanContext
    ) -> Optional[MomentumScanResult]:
        """Scan single symbol for momentum signals."""
        try:
            market_data = context.market_data.get(symbol)
            if not market_data:
                return None

            if not self.apply_filters(market_data):
                return None

            # Calculate momentum metrics
            metrics = self._calculate_momentum_metrics(symbol, market_data, context)
            if not metrics:
                return None

            # Check for actionable momentum
            direction, confidence = self._evaluate_momentum(metrics, market_data)
            if direction == SignalDirection.NEUTRAL:
                return None

            if confidence < self.config.min_confidence:
                return None

            # Generate signal
            return self._generate_signal(symbol, metrics, market_data, direction, confidence, context)

        except Exception as e:
            self._logger.warning(f"Error scanning {symbol}: {e}")
            return None

    def _calculate_momentum_metrics(
        self,
        symbol: str,
        market_data: MarketData,
        context: ScanContext
    ) -> Optional[MomentumMetrics]:
        """Calculate momentum indicators from market data."""
        # Use pre-calculated indicators from market_data if available
        if market_data.rsi is None or market_data.macd is None:
            return None

        hist_data = context.historical_data.get(symbol)
        if not hist_data or len(hist_data.bars) < 14:
            return None

        # Extract indicators (some may need to be calculated from historical data)
        return MomentumMetrics(
            symbol=symbol,
            rsi=market_data.rsi or 50,
            macd=market_data.macd or 0,
            macd_signal=market_data.macd_signal or 0,
            macd_histogram=market_data.macd_histogram or 0,
            adx=market_data.adx or 0,
            plus_di=self._calculate_plus_di(hist_data),
            minus_di=self._calculate_minus_di(hist_data),
            stochastic_k=self._calculate_stochastic_k(hist_data),
            stochastic_d=self._calculate_stochastic_d(hist_data),
            cci=self._calculate_cci(hist_data),
            mfi=self._calculate_mfi(hist_data),
            roc=self._calculate_roc(hist_data),
        )

    def _calculate_plus_di(self, hist_data: HistoricalData, period: int = 14) -> float:
        """Calculate +DI indicator."""
        if len(hist_data.bars) < period + 1:
            return 0

        plus_dm_sum = 0
        tr_sum = 0

        for i in range(-period, 0):
            high_diff = hist_data.bars[i].high - hist_data.bars[i - 1].high
            low_diff = hist_data.bars[i - 1].low - hist_data.bars[i].low

            plus_dm = high_diff if high_diff > low_diff and high_diff > 0 else 0
            plus_dm_sum += plus_dm

            tr = max(
                hist_data.bars[i].high - hist_data.bars[i].low,
                abs(hist_data.bars[i].high - hist_data.bars[i - 1].close),
                abs(hist_data.bars[i].low - hist_data.bars[i - 1].close)
            )
            tr_sum += tr

        if tr_sum == 0:
            return 0

        return (plus_dm_sum / tr_sum) * 100

    def _calculate_minus_di(self, hist_data: HistoricalData, period: int = 14) -> float:
        """Calculate -DI indicator."""
        if len(hist_data.bars) < period + 1:
            return 0

        minus_dm_sum = 0
        tr_sum = 0

        for i in range(-period, 0):
            high_diff = hist_data.bars[i].high - hist_data.bars[i - 1].high
            low_diff = hist_data.bars[i - 1].low - hist_data.bars[i].low

            minus_dm = low_diff if low_diff > high_diff and low_diff > 0 else 0
            minus_dm_sum += minus_dm

            tr = max(
                hist_data.bars[i].high - hist_data.bars[i].low,
                abs(hist_data.bars[i].high - hist_data.bars[i - 1].close),
                abs(hist_data.bars[i].low - hist_data.bars[i - 1].close)
            )
            tr_sum += tr

        if tr_sum == 0:
            return 0

        return (minus_dm_sum / tr_sum) * 100

    def _calculate_stochastic_k(self, hist_data: HistoricalData, period: int = 14) -> float:
        """Calculate Stochastic %K."""
        if len(hist_data.bars) < period:
            return 50

        recent = hist_data.bars[-period:]
        high = max(bar.high for bar in recent)
        low = min(bar.low for bar in recent)
        close = recent[-1].close

        if high == low:
            return 50

        return ((close - low) / (high - low)) * 100

    def _calculate_stochastic_d(self, hist_data: HistoricalData, period: int = 3) -> float:
        """Calculate Stochastic %D (SMA of %K)."""
        # Simplified - just use current %K
        return self._calculate_stochastic_k(hist_data)

    def _calculate_cci(self, hist_data: HistoricalData, period: int = 20) -> float:
        """Calculate Commodity Channel Index."""
        if len(hist_data.bars) < period:
            return 0

        recent = hist_data.bars[-period:]

        # Calculate typical prices
        typical_prices = [(bar.high + bar.low + bar.close) / 3 for bar in recent]

        # Calculate SMA of typical prices
        sma = sum(typical_prices) / period

        # Calculate mean deviation
        mean_dev = sum(abs(tp - sma) for tp in typical_prices) / period

        if mean_dev == 0:
            return 0

        current_tp = typical_prices[-1]
        return (current_tp - sma) / (0.015 * mean_dev)

    def _calculate_mfi(self, hist_data: HistoricalData, period: int = 14) -> float:
        """Calculate Money Flow Index."""
        if len(hist_data.bars) < period + 1:
            return 50

        positive_flow = 0
        negative_flow = 0

        for i in range(-period, 0):
            current = hist_data.bars[i]
            prev = hist_data.bars[i - 1]

            typical_price = (current.high + current.low + current.close) / 3
            prev_typical = (prev.high + prev.low + prev.close) / 3

            money_flow = typical_price * current.volume

            if typical_price > prev_typical:
                positive_flow += money_flow
            else:
                negative_flow += money_flow

        if negative_flow == 0:
            return 100

        money_ratio = positive_flow / negative_flow
        return 100 - (100 / (1 + money_ratio))

    def _calculate_roc(self, hist_data: HistoricalData, period: int = 10) -> float:
        """Calculate Rate of Change."""
        if len(hist_data.bars) < period:
            return 0

        current_close = hist_data.bars[-1].close
        past_close = hist_data.bars[-period].close

        if past_close == 0:
            return 0

        return ((current_close - past_close) / past_close) * 100

    def _evaluate_momentum(
        self,
        metrics: MomentumMetrics,
        market_data: MarketData
    ) -> tuple[SignalDirection, float]:
        """Evaluate momentum and return direction with confidence."""
        score = metrics.momentum_score

        # Volume confirmation
        volume_multiplier = 1.0
        if market_data.relative_volume:
            if market_data.relative_volume >= 2:
                volume_multiplier = 1.2
            elif market_data.relative_volume >= 1.5:
                volume_multiplier = 1.1

        # ADX filter - require trending market
        if metrics.adx < self.min_adx:
            return SignalDirection.NEUTRAL, 0

        # Determine direction and confidence
        if score > 30:
            direction = SignalDirection.LONG
            confidence = min(95, 50 + score * 0.5 * volume_multiplier)
        elif score < -30:
            direction = SignalDirection.SHORT
            confidence = min(95, 50 + abs(score) * 0.5 * volume_multiplier)
        else:
            return SignalDirection.NEUTRAL, 0

        return direction, confidence

    def _generate_signal(
        self,
        symbol: str,
        metrics: MomentumMetrics,
        market_data: MarketData,
        direction: SignalDirection,
        confidence: float,
        context: ScanContext
    ) -> MomentumScanResult:
        """Generate momentum scan result."""
        entry_price = market_data.close

        stop_loss = self.calculate_stop_loss(
            entry_price, direction, market_data.atr, atr_multiplier=2.0
        )

        targets = self.calculate_targets(
            entry_price, stop_loss, direction,
            rr_ratios=[1.5, 2.0, 3.0]
        )

        return MomentumScanResult(
            symbol=symbol,
            scanner_type=self.name,
            direction=direction,
            confidence=confidence,
            entry_price=entry_price,
            stop_loss=stop_loss,
            targets=targets,
            risk_reward=self.calculate_risk_reward(entry_price, stop_loss, targets[1]) if targets else None,
            rsi=metrics.rsi,
            macd_histogram=metrics.macd_histogram,
            macd_signal=metrics.macd_signal,
            adx=metrics.adx,
            volume_surge=market_data.relative_volume or 1.0,
            price_momentum=metrics.momentum_score,
            trend_strength=min(100, metrics.adx * 2),
            metadata={
                "plus_di": metrics.plus_di,
                "minus_di": metrics.minus_di,
                "stochastic_k": metrics.stochastic_k,
                "cci": metrics.cci,
                "mfi": metrics.mfi,
                "roc": metrics.roc,
            }
        )

    def validate_signal(
        self,
        result: MomentumScanResult,
        context: ScanContext
    ) -> bool:
        """Validate momentum signal."""
        if result.confidence < self.config.min_confidence:
            return False

        # ADX must indicate trending
        if result.adx and result.adx < self.min_adx:
            return False

        return True


class ReversalScanner(BaseScanner[ReversalScanResult]):
    """
    Scanner for detecting reversal patterns and divergences.

    Identifies potential trend reversals using price patterns,
    RSI divergence, and volume analysis.
    """

    def __init__(
        self,
        config: Optional[ScannerConfig] = None
    ):
        super().__init__(
            name="reversal",
            scan_mode=ScanMode.REVERSAL,
            config=config
        )

    async def scan(self, context: ScanContext) -> list[ReversalScanResult]:
        """Scan for reversal patterns."""
        results: list[ReversalScanResult] = []

        for symbol in context.universe:
            market_data = context.market_data.get(symbol)
            hist_data = context.historical_data.get(symbol)

            if not market_data or not hist_data:
                continue

            if not self.apply_filters(market_data):
                continue

            result = await self._analyze_reversal(symbol, market_data, hist_data, context)
            if result:
                results.append(result)

        return results

    async def _analyze_reversal(
        self,
        symbol: str,
        market_data: MarketData,
        hist_data: HistoricalData,
        context: ScanContext
    ) -> Optional[ReversalScanResult]:
        """Analyze symbol for reversal setup."""
        if len(hist_data.bars) < 20:
            return None

        # Check for divergence
        divergence = self._detect_divergence(market_data, hist_data)

        # Check for reversal patterns
        pattern = self._detect_reversal_pattern(hist_data)

        if not divergence and not pattern:
            return None

        # Determine direction based on divergence or pattern
        if divergence:
            direction = SignalDirection.LONG if "bullish" in divergence else SignalDirection.SHORT
            pattern_name = divergence
            pattern_confidence = 70
        else:
            direction = pattern.direction
            pattern_name = pattern.pattern_name
            pattern_confidence = pattern.confidence

        # Find support/resistance
        support, resistance = self._find_sr_levels(hist_data, market_data.close)

        # Calculate entry/stop/targets
        entry_price = market_data.close
        stop_loss = self.calculate_stop_loss(
            entry_price, direction, market_data.atr, atr_multiplier=2.5
        )

        if direction == SignalDirection.LONG:
            targets = [resistance] if resistance else self.calculate_targets(
                entry_price, stop_loss, direction
            )
        else:
            targets = [support] if support else self.calculate_targets(
                entry_price, stop_loss, direction
            )

        # Volume confirmation
        volume_confirms = market_data.relative_volume and market_data.relative_volume >= 1.5

        # Calculate final confidence
        confidence = pattern_confidence
        if volume_confirms:
            confidence = min(95, confidence + 10)
        if divergence and pattern:
            confidence = min(95, confidence + 10)  # Both divergence and pattern

        if confidence < self.config.min_confidence:
            return None

        # Prior trend strength
        prior_trend = self._calculate_prior_trend(hist_data)

        return ReversalScanResult(
            symbol=symbol,
            scanner_type=self.name,
            direction=direction,
            confidence=confidence,
            entry_price=entry_price,
            stop_loss=stop_loss,
            targets=targets,
            risk_reward=self.calculate_risk_reward(entry_price, stop_loss, targets[0]) if targets else None,
            pattern_name=pattern_name,
            pattern_confidence=pattern_confidence,
            support_level=support,
            resistance_level=resistance,
            divergence_type=divergence,
            volume_confirmation=volume_confirms,
            prior_trend_strength=prior_trend,
            metadata={
                "has_divergence": divergence is not None,
                "has_pattern": pattern is not None,
            }
        )

    def _detect_divergence(
        self,
        market_data: MarketData,
        hist_data: HistoricalData
    ) -> Optional[str]:
        """Detect RSI divergence."""
        if len(hist_data.bars) < 14 or market_data.rsi is None:
            return None

        # Get recent price lows/highs
        recent_bars = hist_data.bars[-14:]
        prices = [bar.close for bar in recent_bars]

        # Simple divergence detection
        # Bullish divergence: price making lower lows, RSI making higher lows
        price_low_idx = prices.index(min(prices))
        if price_low_idx < len(prices) - 5:  # Low was recent but not current
            recent_price_low = min(prices[-5:])
            if recent_price_low < prices[price_low_idx]:  # Lower low in price
                if market_data.rsi > 30 and market_data.rsi < 50:  # RSI not making new low
                    return "bullish_divergence"

        # Bearish divergence: price making higher highs, RSI making lower highs
        price_high_idx = prices.index(max(prices))
        if price_high_idx < len(prices) - 5:
            recent_price_high = max(prices[-5:])
            if recent_price_high > prices[price_high_idx]:  # Higher high in price
                if market_data.rsi < 70 and market_data.rsi > 50:  # RSI not making new high
                    return "bearish_divergence"

        return None

    def _detect_reversal_pattern(
        self,
        hist_data: HistoricalData
    ) -> Optional[PatternMatch]:
        """Detect reversal candlestick patterns."""
        if len(hist_data.bars) < 3:
            return None

        recent = hist_data.bars[-3:]

        # Hammer pattern (bullish reversal)
        last = recent[-1]
        if last.close > last.open:  # Bullish candle
            body = last.close - last.open
            lower_wick = last.open - last.low
            upper_wick = last.high - last.close

            if lower_wick > body * 2 and upper_wick < body * 0.5:
                return PatternMatch(
                    pattern_name="hammer",
                    pattern_type="reversal",
                    direction=SignalDirection.LONG,
                    confidence=65,
                    entry_trigger=last.high,
                    invalidation_level=last.low,
                    target=last.high + (last.high - last.low) * 2,
                )

        # Shooting star (bearish reversal)
        if last.close < last.open:  # Bearish candle
            body = last.open - last.close
            upper_wick = last.high - last.open
            lower_wick = last.close - last.low

            if upper_wick > body * 2 and lower_wick < body * 0.5:
                return PatternMatch(
                    pattern_name="shooting_star",
                    pattern_type="reversal",
                    direction=SignalDirection.SHORT,
                    confidence=65,
                    entry_trigger=last.low,
                    invalidation_level=last.high,
                    target=last.low - (last.high - last.low) * 2,
                )

        # Engulfing patterns
        prev = recent[-2]

        # Bullish engulfing
        if prev.close < prev.open and last.close > last.open:
            if last.open <= prev.close and last.close >= prev.open:
                return PatternMatch(
                    pattern_name="bullish_engulfing",
                    pattern_type="reversal",
                    direction=SignalDirection.LONG,
                    confidence=70,
                    entry_trigger=last.high,
                    invalidation_level=last.low,
                    target=last.high + (last.high - last.low),
                )

        # Bearish engulfing
        if prev.close > prev.open and last.close < last.open:
            if last.open >= prev.close and last.close <= prev.open:
                return PatternMatch(
                    pattern_name="bearish_engulfing",
                    pattern_type="reversal",
                    direction=SignalDirection.SHORT,
                    confidence=70,
                    entry_trigger=last.low,
                    invalidation_level=last.high,
                    target=last.low - (last.high - last.low),
                )

        return None

    def _find_sr_levels(
        self,
        hist_data: HistoricalData,
        current_price: float
    ) -> tuple[Optional[float], Optional[float]]:
        """Find nearest support and resistance levels."""
        if len(hist_data.bars) < 20:
            return None, None

        highs = [bar.high for bar in hist_data.bars[-20:]]
        lows = [bar.low for bar in hist_data.bars[-20:]]

        # Find resistance (highs above current price)
        resistance_levels = sorted([h for h in highs if h > current_price])
        resistance = resistance_levels[0] if resistance_levels else None

        # Find support (lows below current price)
        support_levels = sorted([l for l in lows if l < current_price], reverse=True)
        support = support_levels[0] if support_levels else None

        return support, resistance

    def _calculate_prior_trend(self, hist_data: HistoricalData) -> float:
        """Calculate strength of the prior trend."""
        if len(hist_data.bars) < 20:
            return 0

        closes = [bar.close for bar in hist_data.bars[-20:]]
        start_price = closes[0]
        end_price = closes[-1]

        if start_price == 0:
            return 0

        change_pct = ((end_price - start_price) / start_price) * 100
        return min(100, abs(change_pct) * 5)  # Scale to 0-100

    def validate_signal(
        self,
        result: ReversalScanResult,
        context: ScanContext
    ) -> bool:
        """Validate reversal signal."""
        if result.confidence < self.config.min_confidence:
            return False

        # Must have either divergence or pattern
        if not result.has_divergence and result.pattern_confidence < 60:
            return False

        return True


class BreakoutScanner(AsyncStreamingScanner[BreakoutScanResult]):
    """
    Scanner for detecting breakout setups from consolidation.

    Identifies price compression and potential breakout levels
    with volume confirmation.
    """

    def __init__(
        self,
        config: Optional[ScannerConfig] = None
    ):
        super().__init__(
            name="breakout",
            scan_mode=ScanMode.BREAKOUT,
            config=config
        )
        self.min_consolidation_days = 5
        self.max_consolidation_range_pct = 10  # Max 10% range for consolidation

    async def scan_symbol(
        self,
        symbol: str,
        context: ScanContext
    ) -> Optional[BreakoutScanResult]:
        """Scan single symbol for breakout setup."""
        try:
            market_data = context.market_data.get(symbol)
            hist_data = context.historical_data.get(symbol)

            if not market_data or not hist_data:
                return None

            if not self.apply_filters(market_data):
                return None

            return await self._analyze_breakout(symbol, market_data, hist_data, context)

        except Exception as e:
            self._logger.warning(f"Error scanning {symbol}: {e}")
            return None

    async def _analyze_breakout(
        self,
        symbol: str,
        market_data: MarketData,
        hist_data: HistoricalData,
        context: ScanContext
    ) -> Optional[BreakoutScanResult]:
        """Analyze symbol for breakout setup."""
        if len(hist_data.bars) < 20:
            return None

        # Detect consolidation
        consolidation = self._detect_consolidation(hist_data)
        if not consolidation:
            return None

        range_high, range_low, days = consolidation

        # Check if breaking out
        current_price = market_data.close
        breakout_level: Optional[float] = None
        direction: Optional[SignalDirection] = None
        breakout_type: str = "resistance"

        if current_price > range_high:
            breakout_level = range_high
            direction = SignalDirection.LONG
            breakout_type = "resistance"
        elif current_price < range_low:
            breakout_level = range_low
            direction = SignalDirection.SHORT
            breakout_type = "support"
        else:
            # Not breaking out yet, but may be setup
            # Return if close to breakout level
            distance_to_high = (range_high - current_price) / current_price * 100
            distance_to_low = (current_price - range_low) / current_price * 100

            if distance_to_high < 1:  # Within 1% of resistance
                breakout_level = range_high
                direction = SignalDirection.LONG
                breakout_type = "resistance"
            elif distance_to_low < 1:  # Within 1% of support
                breakout_level = range_low
                direction = SignalDirection.SHORT
                breakout_type = "support"
            else:
                return None  # Not near breakout

        # Volume confirmation
        volume_confirms = market_data.relative_volume and market_data.relative_volume >= 1.5

        # Calculate confidence
        confidence = 50
        confidence += min(20, days * 2)  # Longer consolidation = stronger breakout
        if volume_confirms:
            confidence += 15

        # Boost if actually breaking vs approaching
        if (direction == SignalDirection.LONG and current_price > range_high) or \
           (direction == SignalDirection.SHORT and current_price < range_low):
            confidence += 10

        if confidence < self.config.min_confidence:
            return None

        # Calculate entry/stop/targets
        entry_price = current_price

        if direction == SignalDirection.LONG:
            stop_loss = range_low * 0.99  # Just below consolidation low
        else:
            stop_loss = range_high * 1.01  # Just above consolidation high

        # Target based on consolidation range projected from breakout
        range_size = range_high - range_low

        if direction == SignalDirection.LONG:
            targets = [
                round(breakout_level + range_size, 2),
                round(breakout_level + range_size * 1.618, 2),
                round(breakout_level + range_size * 2, 2),
            ]
        else:
            targets = [
                round(breakout_level - range_size, 2),
                round(breakout_level - range_size * 1.618, 2),
                round(breakout_level - range_size * 2, 2),
            ]

        # ATR multiple for the move
        atr_multiple = None
        if market_data.atr and market_data.atr > 0:
            atr_multiple = abs(current_price - breakout_level) / market_data.atr

        return BreakoutScanResult(
            symbol=symbol,
            scanner_type=self.name,
            direction=direction,
            confidence=confidence,
            entry_price=entry_price,
            stop_loss=stop_loss,
            targets=targets,
            risk_reward=self.calculate_risk_reward(entry_price, stop_loss, targets[0]) if targets else None,
            breakout_level=breakout_level,
            breakout_type=breakout_type,
            volume_confirmation=volume_confirms,
            retest_expected=True,  # Often retests breakout level
            consolidation_days=days,
            atr_multiple=atr_multiple,
            metadata={
                "range_high": range_high,
                "range_low": range_low,
                "range_pct": ((range_high - range_low) / range_low) * 100,
            }
        )

    def _detect_consolidation(
        self,
        hist_data: HistoricalData
    ) -> Optional[tuple[float, float, int]]:
        """
        Detect if price is in consolidation.

        Returns: (range_high, range_low, consolidation_days) or None
        """
        if len(hist_data.bars) < self.min_consolidation_days:
            return None

        # Look at recent bars
        for lookback in range(self.min_consolidation_days, min(30, len(hist_data.bars))):
            recent = hist_data.bars[-lookback:]

            high = max(bar.high for bar in recent)
            low = min(bar.low for bar in recent)

            if low == 0:
                continue

            range_pct = ((high - low) / low) * 100

            if range_pct <= self.max_consolidation_range_pct:
                return high, low, lookback

        return None

    def validate_signal(
        self,
        result: BreakoutScanResult,
        context: ScanContext
    ) -> bool:
        """Validate breakout signal."""
        if result.confidence < self.config.min_confidence:
            return False

        # Consolidation must be significant
        if result.consolidation_days and result.consolidation_days < self.min_consolidation_days:
            return False

        return True
