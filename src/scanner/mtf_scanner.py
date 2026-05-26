"""
Revolution Alpha Engine - Multi-Timeframe Analysis Scanner

Institutional-grade MTF scanner providing:
- Multi-timeframe trend alignment
- Higher timeframe context for entries
- Time-synchronized signal generation
- MTF divergence detection
- Confluence scoring across timeframes
"""

import numpy as np
import pandas as pd
from typing import Optional, List, Dict, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
import logging
from collections import defaultdict

from .base import BaseScanner, ScanContext, MarketData, HistoricalData
from .models import (
    ScanResult,
    ScanMode,
    SignalDirection,
    ScannerConfig,
    TimeFrame,
    SignalStrength,
)

logger = logging.getLogger(__name__)


class TrendDirection(str, Enum):
    """Trend direction classification."""
    STRONG_UP = "strong_up"
    UP = "up"
    NEUTRAL = "neutral"
    DOWN = "down"
    STRONG_DOWN = "strong_down"


class MTFAlignment(str, Enum):
    """Multi-timeframe alignment status."""
    FULLY_ALIGNED = "fully_aligned"
    MOSTLY_ALIGNED = "mostly_aligned"
    MIXED = "mixed"
    CONFLICTING = "conflicting"


@dataclass
class TimeframeAnalysis:
    """Analysis for a single timeframe."""
    timeframe: TimeFrame
    trend: TrendDirection
    trend_strength: float  # 0-100
    momentum: float  # -100 to 100
    volatility_state: str  # "low", "normal", "high"
    key_level_distance: float  # Distance to nearest S/R
    rsi: float
    macd_histogram: float
    price_position: float  # 0-1, position in recent range

    @property
    def is_bullish(self) -> bool:
        return self.trend in [TrendDirection.UP, TrendDirection.STRONG_UP]

    @property
    def is_bearish(self) -> bool:
        return self.trend in [TrendDirection.DOWN, TrendDirection.STRONG_DOWN]


@dataclass
class MTFSignal:
    """Multi-timeframe signal with full context."""
    symbol: str
    timestamp: datetime

    # Direction and confidence
    direction: SignalDirection
    confidence: float
    signal_strength: SignalStrength

    # MTF Analysis
    alignment: MTFAlignment
    alignment_score: float  # 0-100
    primary_timeframe: TimeFrame
    timeframe_analyses: Dict[TimeFrame, TimeframeAnalysis]

    # Entry parameters
    entry_price: float
    stop_loss: float
    take_profit: float
    position_size_modifier: float  # 0.5-1.5 based on alignment

    # Context
    higher_tf_trend: TrendDirection
    higher_tf_momentum: float
    entry_tf_trend: TrendDirection
    entry_tf_momentum: float

    # Confluence factors
    confluence_score: float
    confluence_factors: List[str]

    # Risk
    risk_reward_ratio: float
    atr_stop_distance: float


@dataclass
class MTFScanResult(ScanResult):
    """Extended scan result with MTF data."""
    mtf_signal: Optional[MTFSignal] = None
    alignment: Optional[MTFAlignment] = None
    alignment_score: float = 0
    higher_tf_bias: Optional[str] = None
    confluence_factors: List[str] = field(default_factory=list)


class TimeframeConverter:
    """Convert between timeframes and resample data."""

    TIMEFRAME_MINUTES = {
        TimeFrame.M1: 1,
        TimeFrame.M5: 5,
        TimeFrame.M15: 15,
        TimeFrame.M30: 30,
        TimeFrame.H1: 60,
        TimeFrame.H4: 240,
        TimeFrame.D1: 1440,
        TimeFrame.W1: 10080,
    }

    @staticmethod
    def resample(
        data: pd.DataFrame,
        from_tf: TimeFrame,
        to_tf: TimeFrame
    ) -> pd.DataFrame:
        """Resample OHLCV data to higher timeframe."""
        from_mins = TimeframeConverter.TIMEFRAME_MINUTES[from_tf]
        to_mins = TimeframeConverter.TIMEFRAME_MINUTES[to_tf]

        if to_mins <= from_mins:
            return data

        rule = f'{to_mins}T'

        resampled = data.resample(rule).agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna()

        return resampled

    @staticmethod
    def get_higher_timeframes(tf: TimeFrame) -> List[TimeFrame]:
        """Get list of higher timeframes."""
        order = list(TimeFrame)
        current_idx = order.index(tf)
        return order[current_idx + 1:]


class MTFAnalyzer:
    """
    Analyze market across multiple timeframes.

    Provides comprehensive MTF context for trading decisions.
    """

    def __init__(
        self,
        timeframes: List[TimeFrame] = None,
        trend_period: int = 20,
        momentum_period: int = 14
    ):
        self.timeframes = timeframes or [
            TimeFrame.M5, TimeFrame.M15, TimeFrame.H1, TimeFrame.H4, TimeFrame.D1
        ]
        self.trend_period = trend_period
        self.momentum_period = momentum_period

        self.converter = TimeframeConverter()

    def analyze(
        self,
        symbol: str,
        data: Dict[TimeFrame, pd.DataFrame]
    ) -> Dict[TimeFrame, TimeframeAnalysis]:
        """
        Analyze symbol across all timeframes.

        Args:
            symbol: Symbol to analyze
            data: Dictionary of timeframe -> OHLCV DataFrame

        Returns:
            Dictionary of timeframe -> analysis
        """
        analyses = {}

        for tf in self.timeframes:
            if tf in data and len(data[tf]) >= self.trend_period:
                analyses[tf] = self._analyze_timeframe(tf, data[tf])

        return analyses

    def _analyze_timeframe(
        self,
        tf: TimeFrame,
        data: pd.DataFrame
    ) -> TimeframeAnalysis:
        """Analyze a single timeframe."""
        close = data['close']
        high = data['high']
        low = data['low']

        # Trend analysis
        sma_fast = close.rolling(self.trend_period // 2).mean()
        sma_slow = close.rolling(self.trend_period).mean()
        sma_trend = close.rolling(self.trend_period * 2).mean()

        current_price = close.iloc[-1]
        fast_ma = sma_fast.iloc[-1]
        slow_ma = sma_slow.iloc[-1]
        trend_ma = sma_trend.iloc[-1] if len(close) >= self.trend_period * 2 else slow_ma

        # Determine trend direction
        if current_price > fast_ma > slow_ma > trend_ma:
            trend = TrendDirection.STRONG_UP
        elif current_price > slow_ma:
            trend = TrendDirection.UP
        elif current_price < fast_ma < slow_ma < trend_ma:
            trend = TrendDirection.STRONG_DOWN
        elif current_price < slow_ma:
            trend = TrendDirection.DOWN
        else:
            trend = TrendDirection.NEUTRAL

        # Trend strength (ADX approximation)
        tr = np.maximum(
            high - low,
            np.maximum(
                np.abs(high - close.shift(1)),
                np.abs(low - close.shift(1))
            )
        )
        atr = tr.rolling(self.momentum_period).mean().iloc[-1]

        price_range = high.rolling(self.trend_period).max().iloc[-1] - low.rolling(self.trend_period).min().iloc[-1]
        trend_strength = min(100, (atr / (price_range + 1e-10)) * 500) if price_range > 0 else 50

        # Momentum (RSI-based)
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(self.momentum_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(self.momentum_period).mean()
        rs = gain / (loss + 1e-10)
        rsi = (100 - (100 / (1 + rs))).iloc[-1]

        momentum = (rsi - 50) * 2  # Scale to -100 to 100

        # Volatility state
        historical_vol = close.pct_change().rolling(50).std().iloc[-1] if len(close) >= 50 else 0.02
        current_vol = close.pct_change().rolling(10).std().iloc[-1]
        vol_ratio = current_vol / (historical_vol + 1e-10)

        if vol_ratio < 0.7:
            vol_state = "low"
        elif vol_ratio > 1.5:
            vol_state = "high"
        else:
            vol_state = "normal"

        # Key level distance (simplified)
        recent_high = high.rolling(self.trend_period).max().iloc[-1]
        recent_low = low.rolling(self.trend_period).min().iloc[-1]
        range_size = recent_high - recent_low

        dist_to_high = (recent_high - current_price) / (range_size + 1e-10)
        dist_to_low = (current_price - recent_low) / (range_size + 1e-10)
        key_level_distance = min(dist_to_high, dist_to_low)

        # MACD histogram
        ema_12 = close.ewm(span=12, adjust=False).mean()
        ema_26 = close.ewm(span=26, adjust=False).mean()
        macd = ema_12 - ema_26
        signal = macd.ewm(span=9, adjust=False).mean()
        macd_hist = (macd - signal).iloc[-1]

        # Price position in range
        price_position = (current_price - recent_low) / (range_size + 1e-10)

        return TimeframeAnalysis(
            timeframe=tf,
            trend=trend,
            trend_strength=trend_strength,
            momentum=momentum,
            volatility_state=vol_state,
            key_level_distance=key_level_distance,
            rsi=rsi,
            macd_histogram=macd_hist,
            price_position=price_position
        )

    def calculate_alignment(
        self,
        analyses: Dict[TimeFrame, TimeframeAnalysis],
        direction: SignalDirection
    ) -> Tuple[MTFAlignment, float]:
        """
        Calculate MTF alignment for given direction.

        Returns:
            (alignment_status, alignment_score)
        """
        if not analyses:
            return MTFAlignment.MIXED, 50.0

        aligned_count = 0
        total_count = len(analyses)

        # Weight higher timeframes more
        weights = {
            TimeFrame.M1: 0.5,
            TimeFrame.M5: 0.6,
            TimeFrame.M15: 0.8,
            TimeFrame.M30: 0.9,
            TimeFrame.H1: 1.0,
            TimeFrame.H4: 1.2,
            TimeFrame.D1: 1.5,
            TimeFrame.W1: 2.0,
        }

        weighted_score = 0
        total_weight = 0

        for tf, analysis in analyses.items():
            weight = weights.get(tf, 1.0)
            total_weight += weight

            if direction == SignalDirection.LONG:
                if analysis.is_bullish:
                    weighted_score += weight
                    aligned_count += 1
                elif analysis.trend == TrendDirection.NEUTRAL:
                    weighted_score += weight * 0.5
            else:  # SHORT
                if analysis.is_bearish:
                    weighted_score += weight
                    aligned_count += 1
                elif analysis.trend == TrendDirection.NEUTRAL:
                    weighted_score += weight * 0.5

        alignment_score = (weighted_score / total_weight) * 100 if total_weight > 0 else 50

        # Determine alignment category
        if aligned_count == total_count:
            alignment = MTFAlignment.FULLY_ALIGNED
        elif aligned_count >= total_count * 0.75:
            alignment = MTFAlignment.MOSTLY_ALIGNED
        elif aligned_count >= total_count * 0.5:
            alignment = MTFAlignment.MIXED
        else:
            alignment = MTFAlignment.CONFLICTING

        return alignment, alignment_score


class MultiTimeframeScanner(BaseScanner[MTFScanResult]):
    """
    Multi-timeframe scanner for high-probability entries.

    Combines analysis from multiple timeframes to identify
    optimal entry points with strong confluence.
    """

    def __init__(
        self,
        config: Optional[ScannerConfig] = None,
        entry_timeframe: TimeFrame = TimeFrame.M15,
        context_timeframes: List[TimeFrame] = None
    ):
        super().__init__(
            name="mtf_scanner",
            scan_mode=ScanMode.ALL,
            config=config
        )

        self.entry_tf = entry_timeframe
        self.context_tfs = context_timeframes or [TimeFrame.H1, TimeFrame.H4, TimeFrame.D1]
        self.all_timeframes = [entry_timeframe] + self.context_tfs

        self.analyzer = MTFAnalyzer(self.all_timeframes)

    async def scan(self, context: ScanContext) -> List[MTFScanResult]:
        """Scan for MTF-aligned signals."""
        results = []

        for symbol in context.universe:
            # Get data for all timeframes
            tf_data = self._get_timeframe_data(symbol, context)

            if not tf_data or len(tf_data) < 2:
                continue

            # Analyze all timeframes
            analyses = self.analyzer.analyze(symbol, tf_data)

            if not analyses or self.entry_tf not in analyses:
                continue

            # Generate signal if conditions met
            signal = self._generate_signal(symbol, analyses, tf_data, context)

            if signal:
                results.append(signal)

        return results

    def _get_timeframe_data(
        self,
        symbol: str,
        context: ScanContext
    ) -> Dict[TimeFrame, pd.DataFrame]:
        """Get data for all required timeframes."""
        tf_data = {}

        # Get base data
        hist_data = context.historical_data.get(symbol)
        if not hist_data:
            return tf_data

        # Convert to DataFrame
        base_df = pd.DataFrame([
            {
                'timestamp': bar.timestamp,
                'open': bar.open,
                'high': bar.high,
                'low': bar.low,
                'close': bar.close,
                'volume': bar.volume
            }
            for bar in hist_data.bars
        ])

        if base_df.empty:
            return tf_data

        base_df.set_index('timestamp', inplace=True)

        # Get base timeframe
        base_tf = hist_data.timeframe
        tf_data[base_tf] = base_df

        # Resample to higher timeframes
        for tf in self.all_timeframes:
            if tf not in tf_data:
                resampled = self.analyzer.converter.resample(base_df, base_tf, tf)
                if not resampled.empty:
                    tf_data[tf] = resampled

        return tf_data

    def _generate_signal(
        self,
        symbol: str,
        analyses: Dict[TimeFrame, TimeframeAnalysis],
        tf_data: Dict[TimeFrame, pd.DataFrame],
        context: ScanContext
    ) -> Optional[MTFScanResult]:
        """Generate signal if MTF conditions are met."""
        entry_analysis = analyses[self.entry_tf]

        # Determine potential direction from entry timeframe
        if entry_analysis.momentum > 20 and entry_analysis.is_bullish:
            direction = SignalDirection.LONG
        elif entry_analysis.momentum < -20 and entry_analysis.is_bearish:
            direction = SignalDirection.SHORT
        else:
            return None  # No clear signal

        # Check higher timeframe alignment
        higher_tf_analyses = {tf: a for tf, a in analyses.items() if tf in self.context_tfs}
        alignment, alignment_score = self.analyzer.calculate_alignment(higher_tf_analyses, direction)

        # Require at least mostly aligned
        if alignment == MTFAlignment.CONFLICTING:
            return None

        # Calculate confluence factors
        confluence_factors = self._calculate_confluence(analyses, direction)
        confluence_score = len(confluence_factors) * 15  # Each factor adds points

        # Calculate confidence
        base_confidence = 50
        confidence = base_confidence + (alignment_score - 50) * 0.5 + confluence_score * 0.3
        confidence = min(95, max(40, confidence))

        if confidence < self.config.min_confidence:
            return None

        # Get entry data
        entry_data = tf_data[self.entry_tf]
        current_price = entry_data['close'].iloc[-1]

        # Calculate stops and targets
        atr = self._calculate_atr(entry_data)
        stop_distance = atr * 2

        if direction == SignalDirection.LONG:
            stop_loss = current_price - stop_distance
            take_profit = current_price + (stop_distance * 2.5)  # 2.5:1 R:R
        else:
            stop_loss = current_price + stop_distance
            take_profit = current_price - (stop_distance * 2.5)

        # Position size modifier based on alignment
        if alignment == MTFAlignment.FULLY_ALIGNED:
            size_modifier = 1.0
        elif alignment == MTFAlignment.MOSTLY_ALIGNED:
            size_modifier = 0.8
        else:
            size_modifier = 0.5

        # Higher TF context
        highest_tf = max(higher_tf_analyses.keys(), key=lambda x: TimeframeConverter.TIMEFRAME_MINUTES[x])
        higher_tf_analysis = higher_tf_analyses[highest_tf]

        # Create MTF signal
        mtf_signal = MTFSignal(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            direction=direction,
            confidence=confidence,
            signal_strength=self._classify_strength(confidence),
            alignment=alignment,
            alignment_score=alignment_score,
            primary_timeframe=self.entry_tf,
            timeframe_analyses=analyses,
            entry_price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size_modifier=size_modifier,
            higher_tf_trend=higher_tf_analysis.trend,
            higher_tf_momentum=higher_tf_analysis.momentum,
            entry_tf_trend=entry_analysis.trend,
            entry_tf_momentum=entry_analysis.momentum,
            confluence_score=confluence_score,
            confluence_factors=confluence_factors,
            risk_reward_ratio=2.5,
            atr_stop_distance=stop_distance / atr
        )

        return MTFScanResult(
            symbol=symbol,
            scanner_type=self.name,
            direction=direction,
            confidence=confidence,
            entry_price=current_price,
            stop_loss=stop_loss,
            targets=[take_profit],
            risk_reward=2.5,
            mtf_signal=mtf_signal,
            alignment=alignment,
            alignment_score=alignment_score,
            higher_tf_bias=higher_tf_analysis.trend.value,
            confluence_factors=confluence_factors,
            metadata={
                'entry_tf': self.entry_tf.value,
                'context_tfs': [tf.value for tf in self.context_tfs],
                'size_modifier': size_modifier,
                'atr': atr,
            }
        )

    def _calculate_confluence(
        self,
        analyses: Dict[TimeFrame, TimeframeAnalysis],
        direction: SignalDirection
    ) -> List[str]:
        """Calculate confluence factors supporting the signal."""
        factors = []

        # Count aligned timeframes
        aligned = sum(1 for a in analyses.values()
                     if (direction == SignalDirection.LONG and a.is_bullish) or
                        (direction == SignalDirection.SHORT and a.is_bearish))

        if aligned >= 3:
            factors.append(f"{aligned} timeframes aligned")

        # RSI confluence
        rsi_values = [a.rsi for a in analyses.values()]
        if direction == SignalDirection.LONG and all(r < 70 for r in rsi_values):
            if any(r < 40 for r in rsi_values):
                factors.append("RSI oversold on some timeframes")
        elif direction == SignalDirection.SHORT and all(r > 30 for r in rsi_values):
            if any(r > 60 for r in rsi_values):
                factors.append("RSI overbought on some timeframes")

        # MACD confluence
        macd_signs = [np.sign(a.macd_histogram) for a in analyses.values()]
        if direction == SignalDirection.LONG and all(s >= 0 for s in macd_signs):
            factors.append("MACD positive all timeframes")
        elif direction == SignalDirection.SHORT and all(s <= 0 for s in macd_signs):
            factors.append("MACD negative all timeframes")

        # Volatility
        vol_states = [a.volatility_state for a in analyses.values()]
        if "low" in vol_states:
            factors.append("Low volatility compression")

        # Strong higher timeframe trend
        for tf, analysis in analyses.items():
            if tf in [TimeFrame.H4, TimeFrame.D1]:
                if analysis.trend in [TrendDirection.STRONG_UP, TrendDirection.STRONG_DOWN]:
                    factors.append(f"Strong {tf.value} trend")
                    break

        return factors

    def _calculate_atr(self, data: pd.DataFrame, period: int = 14) -> float:
        """Calculate ATR."""
        high = data['high']
        low = data['low']
        close = data['close']

        tr = np.maximum(
            high - low,
            np.maximum(
                np.abs(high - close.shift(1)),
                np.abs(low - close.shift(1))
            )
        )

        return tr.rolling(period).mean().iloc[-1]

    def _classify_strength(self, confidence: float) -> SignalStrength:
        """Classify signal strength."""
        if confidence >= 85:
            return SignalStrength.EXTREME
        elif confidence >= 70:
            return SignalStrength.STRONG
        elif confidence >= 55:
            return SignalStrength.MODERATE
        return SignalStrength.WEAK

    def validate_signal(
        self,
        result: MTFScanResult,
        context: ScanContext
    ) -> bool:
        """Validate MTF signal."""
        if result.confidence < self.config.min_confidence:
            return False

        # Require at least mostly aligned
        if result.alignment == MTFAlignment.CONFLICTING:
            return False

        # Require minimum confluence
        if len(result.confluence_factors) < 2:
            return False

        return True
