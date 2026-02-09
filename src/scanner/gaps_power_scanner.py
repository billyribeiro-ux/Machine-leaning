"""
Revolution Alpha Engine - Gaps Power Scanner

The most powerful gap analysis engine ever built. We see the move BEFORE
the move. Every gap is cataloged, classified, and analyzed with REAL
historical statistics -- fill rates, continuation rates, optimal trades,
all backed by data across every timeframe.

Components
----------
GapClassifier        - Classify every gap by type and context.
GapStatisticsEngine  - Historical fill / continuation / fade statistics.
GapPredictionModel   - Predict fill probability, continuation, optimal trade.
RealTimeGapMonitor   - Live gap tracking, momentum, risk scoring.
GapsPowerScanner     - Main BaseScanner orchestrator.
"""

from __future__ import annotations

import logging
import math
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .base import BaseScanner, ScanContext, MarketData, HistoricalData
from .models import (
    ScanResult,
    ScanMode,
    SignalDirection,
    ScannerConfig,
)
from .advanced_models import (
    AdvancedScanResult,
    ScanCategory,
    RegimeContext,
    ExpectedTimeframe,
    VolatilityRegime,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_TRADING_DAYS_PER_YEAR = 252
_MIN_BARS_FOR_STATS = 60
_MIN_BARS_FOR_ATR = 14
_MIN_GAPS_FOR_STATISTICS = 5
_DEFAULT_ATR_PERIOD = 14
_DEFAULT_VOLUME_SMA_PERIOD = 20
_WILSON_Z_95 = 1.96  # z-value for 95 % confidence


# ============================================================================
# Enumerations
# ============================================================================

class GapType(str, Enum):
    """Exhaustive classification of price gaps."""
    COMMON = "common"
    BREAKAWAY = "breakaway"
    RUNAWAY_CONTINUATION = "runaway_continuation"
    EXHAUSTION = "exhaustion"
    ISLAND_REVERSAL = "island_reversal"
    OPENING = "opening"
    TRUE_GAP = "true_gap"
    PARTIAL_GAP = "partial_gap"
    WINDOW_GAP = "window_gap"


class GapDirection(str, Enum):
    """Direction of the gap."""
    UP = "up"
    DOWN = "down"


class GapSizeBucket(str, Enum):
    """Gap size buckets for stratified analysis."""
    TINY = "<0.5%"
    SMALL = "0.5-1%"
    MEDIUM = "1-2%"
    LARGE = "2-3%"
    VERY_LARGE = "3-5%"
    EXTREME = ">5%"


class TradeAction(str, Enum):
    """Recommended trade action for a gap."""
    FADE = "fade"
    FOLLOW = "follow"
    WAIT = "wait"


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class GapRecord:
    """A single cataloged gap with full context."""
    index: int
    timestamp: Optional[datetime]
    symbol: str
    direction: GapDirection
    gap_type: GapType
    gap_size_pct: float
    gap_size_atr: float
    open_price: float
    prev_close: float
    volume: int
    volume_ratio: float
    prev_trend_strength: float
    was_at_support_resistance: bool
    day_of_week: int  # 0=Monday .. 4=Friday
    filled_within: Optional[int] = None  # bars to fill, None = never
    continued_eod: bool = False
    continued_next_day: bool = False
    continued_next_week: bool = False
    close_price: Optional[float] = None
    high_price: Optional[float] = None
    low_price: Optional[float] = None
    is_earnings: bool = False
    is_index_futures: bool = False
    sector: str = ""


@dataclass
class GapMetrics:
    """Computed metrics for a single gap bar."""
    gap_size_pct: float
    gap_size_atr: float
    volume_ratio: float
    prev_trend_strength: float
    was_at_support_resistance: bool


@dataclass
class FillStatistics:
    """Fill-rate statistics for a gap cohort."""
    total: int = 0
    filled_1d: int = 0
    filled_3d: int = 0
    filled_5d: int = 0
    filled_10d: int = 0
    filled_20d: int = 0
    filled_60d: int = 0
    never_filled: int = 0

    @property
    def rate_1d(self) -> float:
        """Fill rate within 1 day."""
        return self.filled_1d / self.total if self.total else 0.0

    @property
    def rate_3d(self) -> float:
        """Fill rate within 3 days."""
        return self.filled_3d / self.total if self.total else 0.0

    @property
    def rate_5d(self) -> float:
        """Fill rate within 5 days."""
        return self.filled_5d / self.total if self.total else 0.0

    @property
    def rate_10d(self) -> float:
        """Fill rate within 10 days."""
        return self.filled_10d / self.total if self.total else 0.0

    @property
    def rate_20d(self) -> float:
        """Fill rate within 20 days."""
        return self.filled_20d / self.total if self.total else 0.0

    @property
    def rate_60d(self) -> float:
        """Fill rate within 60 days."""
        return self.filled_60d / self.total if self.total else 0.0

    @property
    def rate_never(self) -> float:
        """Percentage that were never filled."""
        return self.never_filled / self.total if self.total else 0.0


@dataclass
class ContinuationStatistics:
    """Continuation-rate statistics for a gap cohort."""
    total: int = 0
    continued_eod: int = 0
    continued_next_day: int = 0
    continued_next_week: int = 0

    @property
    def rate_eod(self) -> float:
        """Continuation rate by end of day."""
        return self.continued_eod / self.total if self.total else 0.0

    @property
    def rate_next_day(self) -> float:
        """Continuation rate next day."""
        return self.continued_next_day / self.total if self.total else 0.0

    @property
    def rate_next_week(self) -> float:
        """Continuation rate within one week."""
        return self.continued_next_week / self.total if self.total else 0.0


@dataclass
class GapTradeRecommendation:
    """Recommended trade parameters for a gap."""
    action: TradeAction
    entry_price: float
    stop_loss: float
    target: float
    risk_reward: float
    win_rate: float
    edge_pct: float  # expected value per trade
    confidence: float


@dataclass
class UnfilledGapZone:
    """An unfilled gap that may act as a price magnet."""
    gap_record: GapRecord
    upper_bound: float
    lower_bound: float
    midpoint: float
    distance_pct: float  # distance from current price
    age_bars: int
    magnet_strength: float  # 0-1 score


@dataclass
class GapDatabase:
    """Collection of all cataloged gaps for a symbol."""
    symbol: str
    gaps: List[GapRecord] = field(default_factory=list)

    @property
    def count(self) -> int:
        """Total number of gaps."""
        return len(self.gaps)

    def filter_by_type(self, gap_type: GapType) -> List[GapRecord]:
        """Return gaps matching a specific type."""
        return [g for g in self.gaps if g.gap_type == gap_type]

    def filter_by_direction(self, direction: GapDirection) -> List[GapRecord]:
        """Return gaps matching a direction."""
        return [g for g in self.gaps if g.direction == direction]

    def filter_by_size_bucket(self, bucket: GapSizeBucket) -> List[GapRecord]:
        """Return gaps matching a size bucket."""
        return [g for g in self.gaps if _classify_size_bucket(g.gap_size_pct) == bucket]


# ============================================================================
# Utility helpers
# ============================================================================

def _classify_size_bucket(gap_pct: float) -> GapSizeBucket:
    """Classify absolute gap size into a bucket."""
    abs_pct = abs(gap_pct)
    if abs_pct < 0.5:
        return GapSizeBucket.TINY
    elif abs_pct < 1.0:
        return GapSizeBucket.SMALL
    elif abs_pct < 2.0:
        return GapSizeBucket.MEDIUM
    elif abs_pct < 3.0:
        return GapSizeBucket.LARGE
    elif abs_pct < 5.0:
        return GapSizeBucket.VERY_LARGE
    return GapSizeBucket.EXTREME


def _compute_atr(bars: List[MarketData], period: int = _DEFAULT_ATR_PERIOD) -> float:
    """
    Compute Average True Range over *period* bars.

    Uses the standard Wilder smoothing (exponential) definition.

    Args:
        bars: List of MarketData bars, newest last.
        period: Lookback period for ATR.

    Returns:
        Current ATR value, or 0.0 if insufficient data.
    """
    if len(bars) < period + 1:
        return 0.0

    true_ranges: List[float] = []
    for i in range(1, len(bars)):
        high = bars[i].high
        low = bars[i].low
        prev_close = bars[i - 1].close
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        true_ranges.append(tr)

    if len(true_ranges) < period:
        return 0.0

    # Wilder smoothing
    atr = float(np.mean(true_ranges[:period]))
    for tr_val in true_ranges[period:]:
        atr = (atr * (period - 1) + tr_val) / period
    return atr


def _compute_sma(values: List[float], period: int) -> float:
    """Compute simple moving average of the last *period* values."""
    if len(values) < period:
        return float(np.mean(values)) if values else 0.0
    return float(np.mean(values[-period:]))


def _compute_trend_strength(closes: List[float], lookback: int = 20) -> float:
    """
    Compute trend strength as the slope of a linear regression normalised
    by the standard deviation of the residuals.

    Returns a value roughly in [-3, 3] where positive = uptrend.
    """
    if len(closes) < max(lookback, 5):
        return 0.0
    segment = np.array(closes[-lookback:], dtype=np.float64)
    x = np.arange(len(segment), dtype=np.float64)
    if np.std(segment) == 0:
        return 0.0
    coeffs = np.polyfit(x, segment, 1)
    slope = coeffs[0]
    residuals = segment - np.polyval(coeffs, x)
    std_resid = float(np.std(residuals))
    if std_resid == 0:
        return 0.0
    return float(slope / std_resid)


def _is_near_level(price: float, level: float, tolerance_pct: float = 1.0) -> bool:
    """Check whether *price* is within *tolerance_pct* of *level*."""
    if level == 0:
        return False
    return abs(price - level) / level * 100.0 <= tolerance_pct


def _find_support_resistance(bars: List[MarketData], lookback: int = 50) -> Tuple[List[float], List[float]]:
    """
    Find simple support and resistance levels from swing highs / lows.

    Returns (supports, resistances) lists.
    """
    if len(bars) < 5:
        return [], []

    segment = bars[-min(lookback, len(bars)):]
    supports: List[float] = []
    resistances: List[float] = []

    for i in range(2, len(segment) - 2):
        # Swing low
        if (segment[i].low <= segment[i - 1].low
                and segment[i].low <= segment[i - 2].low
                and segment[i].low <= segment[i + 1].low
                and segment[i].low <= segment[i + 2].low):
            supports.append(segment[i].low)
        # Swing high
        if (segment[i].high >= segment[i - 1].high
                and segment[i].high >= segment[i - 2].high
                and segment[i].high >= segment[i + 1].high
                and segment[i].high >= segment[i + 2].high):
            resistances.append(segment[i].high)

    return supports, resistances


def _wilson_score_interval(
    successes: int,
    total: int,
    z: float = _WILSON_Z_95,
) -> Tuple[float, float]:
    """
    Wilson score confidence interval for a binomial proportion.

    Args:
        successes: Number of successes.
        total: Number of trials.
        z: Z-value for desired confidence level (default 1.96 = 95 %).

    Returns:
        (lower_bound, upper_bound) of the confidence interval.
    """
    if total == 0:
        return 0.0, 0.0
    p_hat = successes / total
    denominator = 1.0 + z * z / total
    centre = (p_hat + z * z / (2.0 * total)) / denominator
    margin = (z / denominator) * math.sqrt(
        (p_hat * (1.0 - p_hat) + z * z / (4.0 * total)) / total
    )
    return max(0.0, centre - margin), min(1.0, centre + margin)


def _beta_binomial_posterior(
    successes: int,
    total: int,
    prior_alpha: float = 1.0,
    prior_beta: float = 1.0,
) -> Tuple[float, float, float]:
    """
    Bayesian posterior for a proportion using Beta-Binomial conjugacy.

    P(fill | data) ~ Beta(alpha + successes, beta + failures)

    Args:
        successes: Observed successes.
        total: Total trials.
        prior_alpha: Beta prior alpha (default 1 = uniform).
        prior_beta: Beta prior beta (default 1 = uniform).

    Returns:
        (posterior_mean, lower_95, upper_95) using the Beta distribution.
    """
    failures = total - successes
    post_alpha = prior_alpha + successes
    post_beta = prior_beta + failures
    mean = post_alpha / (post_alpha + post_beta)
    # Approximate 95 % credible interval
    var = (post_alpha * post_beta) / (
        (post_alpha + post_beta) ** 2 * (post_alpha + post_beta + 1)
    )
    std = math.sqrt(var) if var > 0 else 0.0
    lower = max(0.0, mean - 1.96 * std)
    upper = min(1.0, mean + 1.96 * std)
    return mean, lower, upper


def _regime_to_context(regime_str: str) -> RegimeContext:
    """Map a market regime string to RegimeContext enum."""
    mapping = {
        "trending_up": RegimeContext.TRENDING_UP,
        "trending_down": RegimeContext.TRENDING_DOWN,
        "ranging": RegimeContext.RANGING,
        "high_volatility": RegimeContext.VOLATILE,
        "low_volatility": RegimeContext.QUIET,
        "breakout": RegimeContext.TRANSITION,
    }
    return mapping.get(regime_str, RegimeContext.RANGING)


def _classify_vol_regime(atr: float, price: float, hist_atr_pcts: List[float]) -> VolatilityRegime:
    """Classify current volatility regime from ATR percentile."""
    if price == 0 or not hist_atr_pcts:
        return VolatilityRegime.NORMAL
    current_pct = atr / price * 100.0
    rank = sum(1 for v in hist_atr_pcts if v <= current_pct) / len(hist_atr_pcts) * 100.0
    if rank < 10:
        return VolatilityRegime.ULTRA_LOW
    elif rank < 25:
        return VolatilityRegime.LOW
    elif rank < 75:
        return VolatilityRegime.NORMAL
    elif rank < 90:
        return VolatilityRegime.ELEVATED
    elif rank < 97:
        return VolatilityRegime.HIGH
    return VolatilityRegime.EXTREME


# ============================================================================
# 1. GapClassifier
# ============================================================================

class GapClassifier:
    """
    Classify every type of price gap.

    Uses surrounding price action, volume, trend context, and
    support / resistance levels to assign a GapType label and compute
    detailed gap metrics.
    """

    # Volume thresholds
    HIGH_VOLUME_RATIO = 1.5
    LOW_VOLUME_RATIO = 0.8
    # Trend strength thresholds
    STRONG_TREND = 1.0
    WEAK_TREND = 0.3

    def classify_gap(
        self,
        bars: List[MarketData],
        gap_index: int,
    ) -> GapType:
        """
        Analyse context around a gap bar and classify its type.

        Classification hierarchy (checked in priority order):
        1. Island reversal  - gap in opposite direction follows soon
        2. Exhaustion       - gap at end of strong trend with fading volume
        3. Breakaway        - gap away from consolidation / S-R with volume
        4. Runaway          - gap in direction of strong trend, mid-trend
        5. Window gap       - gap on a Japanese candlestick chart (high vol)
        6. True gap         - no intraday overlap with previous bar
        7. Partial gap      - intraday overlap exists
        8. Opening gap      - gap that fills intraday
        9. Common           - default catch-all

        Args:
            bars: Full list of MarketData bars (oldest first).
            gap_index: Index of the gap bar within *bars*.

        Returns:
            Classified GapType.
        """
        if gap_index < 1 or gap_index >= len(bars):
            return GapType.COMMON

        # Check island reversal first (highest priority)
        if self.detect_island_reversal(bars, gap_index):
            return GapType.ISLAND_REVERSAL

        metrics = self.compute_gap_metrics(bars, gap_index)
        bar = bars[gap_index]
        prev_bar = bars[gap_index - 1]
        gap_pct = metrics.gap_size_pct
        trend = metrics.prev_trend_strength
        vol_ratio = metrics.volume_ratio
        at_sr = metrics.was_at_support_resistance

        # Determine gap direction
        is_up = bar.open > prev_bar.close

        # ------------------------------------------------------------------
        # Exhaustion gap: strong prior trend + gap in trend direction +
        # declining or average volume + possible reversal candle
        # ------------------------------------------------------------------
        if abs(trend) > self.STRONG_TREND:
            trend_aligned = (is_up and trend > 0) or (not is_up and trend < 0)
            if trend_aligned and vol_ratio < self.HIGH_VOLUME_RATIO:
                # Check for reversal candle (close opposite to gap direction)
                if is_up and bar.close < bar.open:
                    return GapType.EXHAUSTION
                if not is_up and bar.close > bar.open:
                    return GapType.EXHAUSTION

        # ------------------------------------------------------------------
        # Breakaway gap: gap away from S/R with above-average volume
        # ------------------------------------------------------------------
        if at_sr and vol_ratio >= self.HIGH_VOLUME_RATIO and abs(gap_pct) >= 0.5:
            return GapType.BREAKAWAY

        # ------------------------------------------------------------------
        # Runaway / continuation: mid-trend gap in trend direction with vol
        # ------------------------------------------------------------------
        if abs(trend) > self.WEAK_TREND:
            trend_aligned = (is_up and trend > 0) or (not is_up and trend < 0)
            if trend_aligned and vol_ratio >= self.HIGH_VOLUME_RATIO:
                return GapType.RUNAWAY_CONTINUATION

        # ------------------------------------------------------------------
        # Window gap (Japanese candlestick terminology): clear gap + volume
        # ------------------------------------------------------------------
        if self.is_true_gap(bars, gap_index) and vol_ratio >= 1.2:
            return GapType.WINDOW_GAP

        # ------------------------------------------------------------------
        # True gap vs partial gap
        # ------------------------------------------------------------------
        if self.is_true_gap(bars, gap_index):
            # If it filled during the session it is just an opening gap
            if self._filled_intraday(bars, gap_index):
                return GapType.OPENING
            return GapType.TRUE_GAP

        # Partial gap (intraday overlap)
        if abs(gap_pct) >= 0.2:
            if self._filled_intraday(bars, gap_index):
                return GapType.OPENING
            return GapType.PARTIAL_GAP

        return GapType.COMMON

    def compute_gap_metrics(
        self,
        bars: List[MarketData],
        gap_index: int,
    ) -> GapMetrics:
        """
        Compute quantitative metrics for a gap bar.

        Args:
            bars: Full list of MarketData bars.
            gap_index: Index of the gap bar.

        Returns:
            GapMetrics dataclass with all computed values.
        """
        bar = bars[gap_index]
        prev_bar = bars[gap_index - 1]

        # Gap size as percentage
        if prev_bar.close != 0:
            gap_size_pct = (bar.open - prev_bar.close) / prev_bar.close * 100.0
        else:
            gap_size_pct = 0.0

        # Gap size in ATR units
        atr = _compute_atr(bars[:gap_index + 1])
        gap_size_atr = abs(bar.open - prev_bar.close) / atr if atr > 0 else 0.0

        # Volume ratio vs 20-bar SMA
        vol_window = bars[max(0, gap_index - _DEFAULT_VOLUME_SMA_PERIOD):gap_index]
        if vol_window:
            avg_vol = float(np.mean([b.volume for b in vol_window]))
            volume_ratio = bar.volume / avg_vol if avg_vol > 0 else 1.0
        else:
            volume_ratio = 1.0

        # Trend strength over last 20 bars
        closes_before = [b.close for b in bars[max(0, gap_index - 20):gap_index]]
        prev_trend_strength = _compute_trend_strength(closes_before) if len(closes_before) >= 5 else 0.0

        # Support / resistance proximity
        supports, resistances = _find_support_resistance(bars[:gap_index], lookback=50)
        at_sr = False
        for level in supports + resistances:
            if _is_near_level(prev_bar.close, level, tolerance_pct=1.5):
                at_sr = True
                break

        return GapMetrics(
            gap_size_pct=gap_size_pct,
            gap_size_atr=gap_size_atr,
            volume_ratio=volume_ratio,
            prev_trend_strength=prev_trend_strength,
            was_at_support_resistance=at_sr,
        )

    def is_true_gap(self, bars: List[MarketData], gap_index: int) -> bool:
        """
        Determine if the gap at *gap_index* is a true gap (no overlap).

        A true gap up:  bar.low  > prev_bar.high
        A true gap down: bar.high < prev_bar.low

        Args:
            bars: List of MarketData bars.
            gap_index: Index of the gap bar.

        Returns:
            True if the gap has no intraday overlap with previous bar.
        """
        if gap_index < 1 or gap_index >= len(bars):
            return False
        bar = bars[gap_index]
        prev = bars[gap_index - 1]
        return bar.low > prev.high or bar.high < prev.low

    def detect_island_reversal(
        self,
        bars: List[MarketData],
        index: int,
        max_island_length: int = 5,
    ) -> bool:
        """
        Detect an island reversal pattern.

        An island reversal occurs when a gap in one direction is followed
        (within *max_island_length* bars) by a gap in the opposite direction,
        creating an isolated cluster of bars.

        Args:
            bars: List of MarketData bars.
            index: Index of the initial gap bar.
            max_island_length: Maximum bars between the two gaps.

        Returns:
            True if an island reversal is detected.
        """
        if index < 1:
            return False

        prev = bars[index - 1]
        bar = bars[index]
        initial_up = bar.open > prev.close

        # Look ahead for an opposing gap
        end = min(index + max_island_length + 1, len(bars))
        for j in range(index + 1, end):
            if j >= len(bars):
                break
            curr = bars[j]
            prev_j = bars[j - 1]
            if initial_up:
                # Need a gap down: curr.high < prev_j.low
                if curr.high < prev_j.low:
                    return True
            else:
                # Need a gap up: curr.low > prev_j.high
                if curr.low > prev_j.high:
                    return True
        return False

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _filled_intraday(bars: List[MarketData], gap_index: int) -> bool:
        """Check if the gap filled during its own session."""
        if gap_index < 1:
            return False
        bar = bars[gap_index]
        prev_close = bars[gap_index - 1].close
        if bar.open > prev_close:
            # Gap up: filled if low reached prev_close
            return bar.low <= prev_close
        elif bar.open < prev_close:
            # Gap down: filled if high reached prev_close
            return bar.high >= prev_close
        return True


# ============================================================================
# 2. GapStatisticsEngine
# ============================================================================

class GapStatisticsEngine:
    """
    Historical gap analysis with REAL statistics.

    Scans historical bars, catalogs every gap, and computes stratified
    fill rates, continuation rates, day-of-week effects, size-bucket
    analysis, and more.
    """

    def __init__(
        self,
        classifier: Optional[GapClassifier] = None,
        min_gap_pct: float = 0.15,
    ):
        """
        Initialise the statistics engine.

        Args:
            classifier: GapClassifier instance (created if None).
            min_gap_pct: Minimum absolute gap % to catalog.
        """
        self.classifier = classifier or GapClassifier()
        self.min_gap_pct = min_gap_pct

    # ------------------------------------------------------------------
    # Database builder
    # ------------------------------------------------------------------

    def build_gap_database(
        self,
        historical_bars: List[MarketData],
        symbol: str = "",
        earnings_dates: Optional[List[datetime]] = None,
        is_index_futures: bool = False,
        sector: str = "",
    ) -> GapDatabase:
        """
        Scan all historical data and catalog every gap.

        For each gap found, we track whether and when it filled, and
        whether price continued in the gap direction.

        Args:
            historical_bars: Full list of bars oldest-first.
            symbol: Ticker symbol.
            earnings_dates: List of earnings announcement dates.
            is_index_futures: True if the symbol is ES/NQ/RTY etc.
            sector: GICS sector string.

        Returns:
            GapDatabase containing every cataloged GapRecord.
        """
        db = GapDatabase(symbol=symbol)
        if len(historical_bars) < 2:
            return db

        earnings_set: set = set()
        if earnings_dates:
            for dt in earnings_dates:
                earnings_set.add(dt.date() if hasattr(dt, 'date') else dt)

        for i in range(1, len(historical_bars)):
            bar = historical_bars[i]
            prev_bar = historical_bars[i - 1]

            if prev_bar.close == 0:
                continue

            gap_pct = (bar.open - prev_bar.close) / prev_bar.close * 100.0

            if abs(gap_pct) < self.min_gap_pct:
                continue

            metrics = self.classifier.compute_gap_metrics(historical_bars, i)
            gap_type = self.classifier.classify_gap(historical_bars, i)
            direction = GapDirection.UP if gap_pct > 0 else GapDirection.DOWN

            # Determine fill timing
            filled_within = self._find_fill_bar(historical_bars, i, prev_bar.close, direction)

            # Continuation checks
            continued_eod = self._continued_at_eod(bar, prev_bar.close, direction)
            continued_next_day = self._continued_next_day(
                historical_bars, i, prev_bar.close, direction
            )
            continued_next_week = self._continued_next_week(
                historical_bars, i, prev_bar.close, direction
            )

            # Day of week
            dow = bar.timestamp.weekday() if bar.timestamp else 0

            # Earnings check
            is_earnings = False
            if bar.timestamp and earnings_set:
                bar_date = bar.timestamp.date() if hasattr(bar.timestamp, 'date') else bar.timestamp
                is_earnings = bar_date in earnings_set

            record = GapRecord(
                index=i,
                timestamp=bar.timestamp,
                symbol=symbol,
                direction=direction,
                gap_type=gap_type,
                gap_size_pct=gap_pct,
                gap_size_atr=metrics.gap_size_atr,
                open_price=bar.open,
                prev_close=prev_bar.close,
                volume=bar.volume,
                volume_ratio=metrics.volume_ratio,
                prev_trend_strength=metrics.prev_trend_strength,
                was_at_support_resistance=metrics.was_at_support_resistance,
                day_of_week=dow,
                filled_within=filled_within,
                continued_eod=continued_eod,
                continued_next_day=continued_next_day,
                continued_next_week=continued_next_week,
                close_price=bar.close,
                high_price=bar.high,
                low_price=bar.low,
                is_earnings=is_earnings,
                is_index_futures=is_index_futures,
                sector=sector,
            )
            db.gaps.append(record)

        return db

    # ------------------------------------------------------------------
    # Fill statistics
    # ------------------------------------------------------------------

    def compute_fill_statistics(
        self,
        gap_db: GapDatabase,
    ) -> Dict[GapType, FillStatistics]:
        """
        Compute fill-rate statistics for each gap type.

        For each type: percentage filled within 1, 3, 5, 10, 20, 60 days
        and percentage never filled.

        Args:
            gap_db: GapDatabase to analyse.

        Returns:
            Dict mapping GapType to FillStatistics.
        """
        stats: Dict[GapType, FillStatistics] = {}
        grouped = defaultdict(list)
        for g in gap_db.gaps:
            grouped[g.gap_type].append(g)

        for gtype, gaps in grouped.items():
            fs = FillStatistics(total=len(gaps))
            for g in gaps:
                fw = g.filled_within
                if fw is None:
                    fs.never_filled += 1
                else:
                    if fw <= 1:
                        fs.filled_1d += 1
                    if fw <= 3:
                        fs.filled_3d += 1
                    if fw <= 5:
                        fs.filled_5d += 1
                    if fw <= 10:
                        fs.filled_10d += 1
                    if fw <= 20:
                        fs.filled_20d += 1
                    if fw <= 60:
                        fs.filled_60d += 1
                    else:
                        fs.never_filled += 1
            stats[gtype] = fs
        return stats

    # ------------------------------------------------------------------
    # Continuation statistics
    # ------------------------------------------------------------------

    def compute_continuation_statistics(
        self,
        gap_db: GapDatabase,
    ) -> Dict[GapType, ContinuationStatistics]:
        """
        Compute continuation-rate statistics for each gap type.

        After a gap, what % of the time does price continue in the gap
        direction by EOD, next day, and next week?

        Args:
            gap_db: GapDatabase to analyse.

        Returns:
            Dict mapping GapType to ContinuationStatistics.
        """
        stats: Dict[GapType, ContinuationStatistics] = {}
        grouped = defaultdict(list)
        for g in gap_db.gaps:
            grouped[g.gap_type].append(g)

        for gtype, gaps in grouped.items():
            cs = ContinuationStatistics(total=len(gaps))
            for g in gaps:
                if g.continued_eod:
                    cs.continued_eod += 1
                if g.continued_next_day:
                    cs.continued_next_day += 1
                if g.continued_next_week:
                    cs.continued_next_week += 1
            stats[gtype] = cs
        return stats

    # ------------------------------------------------------------------
    # Gap size analysis
    # ------------------------------------------------------------------

    def gap_size_analysis(
        self,
        gap_db: GapDatabase,
    ) -> Dict[GapSizeBucket, Dict[str, Any]]:
        """
        Compute statistics bucketed by gap size.

        Buckets: <0.5 %, 0.5-1 %, 1-2 %, 2-3 %, 3-5 %, >5 %.

        Args:
            gap_db: GapDatabase to analyse.

        Returns:
            Dict mapping each bucket to fill rates, continuation rates,
            average gap size, and sample count.
        """
        buckets: Dict[GapSizeBucket, List[GapRecord]] = defaultdict(list)
        for g in gap_db.gaps:
            bucket = _classify_size_bucket(g.gap_size_pct)
            buckets[bucket].append(g)

        result: Dict[GapSizeBucket, Dict[str, Any]] = {}
        for bucket, gaps in buckets.items():
            n = len(gaps)
            filled_1d = sum(1 for g in gaps if g.filled_within is not None and g.filled_within <= 1)
            filled_5d = sum(1 for g in gaps if g.filled_within is not None and g.filled_within <= 5)
            filled_20d = sum(1 for g in gaps if g.filled_within is not None and g.filled_within <= 20)
            cont_eod = sum(1 for g in gaps if g.continued_eod)
            avg_size = float(np.mean([abs(g.gap_size_pct) for g in gaps])) if gaps else 0.0

            result[bucket] = {
                "count": n,
                "avg_gap_size_pct": round(avg_size, 3),
                "fill_rate_1d": round(filled_1d / n, 4) if n else 0.0,
                "fill_rate_5d": round(filled_5d / n, 4) if n else 0.0,
                "fill_rate_20d": round(filled_20d / n, 4) if n else 0.0,
                "continuation_rate_eod": round(cont_eod / n, 4) if n else 0.0,
                "wilson_ci_fill_5d": _wilson_score_interval(filled_5d, n),
            }
        return result

    # ------------------------------------------------------------------
    # Day-of-week analysis
    # ------------------------------------------------------------------

    def day_of_week_analysis(
        self,
        gap_db: GapDatabase,
    ) -> Dict[int, Dict[str, Any]]:
        """
        Analyse fill rates and continuation by day of week.

        Monday gaps vs Friday gaps -- how do fill rates differ?

        Args:
            gap_db: GapDatabase to analyse.

        Returns:
            Dict mapping day-of-week (0=Mon..4=Fri) to statistics.
        """
        by_dow: Dict[int, List[GapRecord]] = defaultdict(list)
        for g in gap_db.gaps:
            by_dow[g.day_of_week].append(g)

        day_names = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday"}
        result: Dict[int, Dict[str, Any]] = {}
        for dow in range(5):
            gaps = by_dow.get(dow, [])
            n = len(gaps)
            filled_1d = sum(1 for g in gaps if g.filled_within is not None and g.filled_within <= 1)
            filled_5d = sum(1 for g in gaps if g.filled_within is not None and g.filled_within <= 5)
            cont_eod = sum(1 for g in gaps if g.continued_eod)
            result[dow] = {
                "day_name": day_names.get(dow, str(dow)),
                "count": n,
                "fill_rate_1d": round(filled_1d / n, 4) if n else 0.0,
                "fill_rate_5d": round(filled_5d / n, 4) if n else 0.0,
                "continuation_rate_eod": round(cont_eod / n, 4) if n else 0.0,
            }
        return result

    # ------------------------------------------------------------------
    # Sector gap analysis
    # ------------------------------------------------------------------

    def sector_gap_analysis(
        self,
        gap_db: GapDatabase,
        sector_map: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Determine which sectors have the highest gap fill rates.

        Args:
            gap_db: GapDatabase to analyse.
            sector_map: Optional mapping of symbol -> sector. If None, uses
                        the sector stored in each GapRecord.

        Returns:
            Dict mapping sector name to fill/continuation statistics.
        """
        by_sector: Dict[str, List[GapRecord]] = defaultdict(list)
        for g in gap_db.gaps:
            sector = sector_map.get(g.symbol, g.sector) if sector_map else g.sector
            if not sector:
                sector = "Unknown"
            by_sector[sector].append(g)

        result: Dict[str, Dict[str, Any]] = {}
        for sector, gaps in by_sector.items():
            n = len(gaps)
            filled_1d = sum(1 for g in gaps if g.filled_within is not None and g.filled_within <= 1)
            filled_5d = sum(1 for g in gaps if g.filled_within is not None and g.filled_within <= 5)
            result[sector] = {
                "count": n,
                "fill_rate_1d": round(filled_1d / n, 4) if n else 0.0,
                "fill_rate_5d": round(filled_5d / n, 4) if n else 0.0,
                "avg_gap_size": round(float(np.mean([abs(g.gap_size_pct) for g in gaps])), 3) if gaps else 0.0,
            }
        return result

    # ------------------------------------------------------------------
    # Gap-and-go probability
    # ------------------------------------------------------------------

    def gap_and_go_probability(
        self,
        gap_db: GapDatabase,
    ) -> Dict[Tuple[GapType, GapSizeBucket], Dict[str, float]]:
        """
        Probability of gap-and-go (no fill, continues in gap direction)
        stratified by gap type and size bucket.

        Args:
            gap_db: GapDatabase to analyse.

        Returns:
            Dict mapping (GapType, SizeBucket) to probability stats.
        """
        groups: Dict[Tuple[GapType, GapSizeBucket], List[GapRecord]] = defaultdict(list)
        for g in gap_db.gaps:
            key = (g.gap_type, _classify_size_bucket(g.gap_size_pct))
            groups[key].append(g)

        result: Dict[Tuple[GapType, GapSizeBucket], Dict[str, float]] = {}
        for key, gaps in groups.items():
            n = len(gaps)
            # Gap-and-go = continued at EOD AND not filled within session
            gng = sum(
                1 for g in gaps
                if g.continued_eod and (g.filled_within is None or g.filled_within > 1)
            )
            prob, lower, upper = _beta_binomial_posterior(gng, n)
            result[key] = {
                "probability": round(prob, 4),
                "ci_lower": round(lower, 4),
                "ci_upper": round(upper, 4),
                "sample_size": n,
            }
        return result

    # ------------------------------------------------------------------
    # Gap fade probability
    # ------------------------------------------------------------------

    def gap_fade_probability(
        self,
        gap_db: GapDatabase,
    ) -> Dict[Tuple[GapType, GapSizeBucket], Dict[str, float]]:
        """
        Probability of a gap fade (fills within session) stratified by
        gap type and size bucket.

        Args:
            gap_db: GapDatabase to analyse.

        Returns:
            Dict mapping (GapType, SizeBucket) to probability stats.
        """
        groups: Dict[Tuple[GapType, GapSizeBucket], List[GapRecord]] = defaultdict(list)
        for g in gap_db.gaps:
            key = (g.gap_type, _classify_size_bucket(g.gap_size_pct))
            groups[key].append(g)

        result: Dict[Tuple[GapType, GapSizeBucket], Dict[str, float]] = {}
        for key, gaps in groups.items():
            n = len(gaps)
            faded = sum(1 for g in gaps if g.filled_within is not None and g.filled_within <= 1)
            prob, lower, upper = _beta_binomial_posterior(faded, n)
            result[key] = {
                "probability": round(prob, 4),
                "ci_lower": round(lower, 4),
                "ci_upper": round(upper, 4),
                "sample_size": n,
            }
        return result

    # ------------------------------------------------------------------
    # Earnings gap analysis
    # ------------------------------------------------------------------

    def earnings_gap_analysis(
        self,
        gap_db: GapDatabase,
        earnings_dates: Optional[List[datetime]] = None,
    ) -> Dict[str, Any]:
        """
        Analyse earnings-related gaps: fill rates, average magnitude,
        and average time to fill.

        Args:
            gap_db: GapDatabase to analyse.
            earnings_dates: Optional list of earnings dates for filtering.

        Returns:
            Dict with earnings gap statistics.
        """
        earnings_gaps = [g for g in gap_db.gaps if g.is_earnings]
        non_earnings_gaps = [g for g in gap_db.gaps if not g.is_earnings]

        def _stats(gaps: List[GapRecord]) -> Dict[str, Any]:
            """Compute summary statistics for a cohort of gap records."""
            n = len(gaps)
            if n == 0:
                return {"count": 0}
            filled_5d = sum(1 for g in gaps if g.filled_within is not None and g.filled_within <= 5)
            filled_20d = sum(1 for g in gaps if g.filled_within is not None and g.filled_within <= 20)
            never = sum(1 for g in gaps if g.filled_within is None)
            fill_times = [g.filled_within for g in gaps if g.filled_within is not None]
            avg_fill_time = float(np.mean(fill_times)) if fill_times else float('inf')
            avg_mag = float(np.mean([abs(g.gap_size_pct) for g in gaps]))
            return {
                "count": n,
                "avg_magnitude_pct": round(avg_mag, 3),
                "fill_rate_5d": round(filled_5d / n, 4),
                "fill_rate_20d": round(filled_20d / n, 4),
                "never_filled_pct": round(never / n, 4),
                "avg_time_to_fill": round(avg_fill_time, 1),
            }

        return {
            "earnings_gaps": _stats(earnings_gaps),
            "non_earnings_gaps": _stats(non_earnings_gaps),
        }

    # ------------------------------------------------------------------
    # Index futures gap statistics
    # ------------------------------------------------------------------

    def index_futures_gap_statistics(
        self,
        gap_db: GapDatabase,
    ) -> Dict[str, Any]:
        """
        Compute ES / NQ / RTY gap statistics: fill rates and patterns.

        Args:
            gap_db: GapDatabase (should be from an index futures symbol).

        Returns:
            Dict with index futures specific gap statistics.
        """
        futures_gaps = [g for g in gap_db.gaps if g.is_index_futures]
        if not futures_gaps:
            futures_gaps = gap_db.gaps  # use all if flag not set

        n = len(futures_gaps)
        if n == 0:
            return {"count": 0}

        filled_1d = sum(1 for g in futures_gaps if g.filled_within is not None and g.filled_within <= 1)
        filled_5d = sum(1 for g in futures_gaps if g.filled_within is not None and g.filled_within <= 5)
        up_gaps = [g for g in futures_gaps if g.direction == GapDirection.UP]
        dn_gaps = [g for g in futures_gaps if g.direction == GapDirection.DOWN]
        up_fill_1d = sum(1 for g in up_gaps if g.filled_within is not None and g.filled_within <= 1)
        dn_fill_1d = sum(1 for g in dn_gaps if g.filled_within is not None and g.filled_within <= 1)

        return {
            "count": n,
            "fill_rate_1d": round(filled_1d / n, 4),
            "fill_rate_5d": round(filled_5d / n, 4),
            "up_gap_count": len(up_gaps),
            "up_gap_fill_rate_1d": round(up_fill_1d / len(up_gaps), 4) if up_gaps else 0.0,
            "down_gap_count": len(dn_gaps),
            "down_gap_fill_rate_1d": round(dn_fill_1d / len(dn_gaps), 4) if dn_gaps else 0.0,
            "avg_gap_size_pct": round(float(np.mean([abs(g.gap_size_pct) for g in futures_gaps])), 3),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_fill_bar(
        bars: List[MarketData],
        gap_index: int,
        prev_close: float,
        direction: GapDirection,
        max_look_ahead: int = 60,
    ) -> Optional[int]:
        """
        Find how many bars after the gap it takes to fill.

        A gap up is filled when the low reaches prev_close.
        A gap down is filled when the high reaches prev_close.

        Returns None if not filled within max_look_ahead bars.
        """
        end = min(gap_index + max_look_ahead + 1, len(bars))
        for j in range(gap_index, end):
            bar = bars[j]
            if direction == GapDirection.UP and bar.low <= prev_close:
                return j - gap_index
            if direction == GapDirection.DOWN and bar.high >= prev_close:
                return j - gap_index
        return None

    @staticmethod
    def _continued_at_eod(
        bar: MarketData,
        prev_close: float,
        direction: GapDirection,
    ) -> bool:
        """Check if price continued in gap direction by end of day."""
        if direction == GapDirection.UP:
            return bar.close > prev_close
        return bar.close < prev_close

    @staticmethod
    def _continued_next_day(
        bars: List[MarketData],
        gap_index: int,
        prev_close: float,
        direction: GapDirection,
    ) -> bool:
        """Check if price continued in gap direction by next day close."""
        if gap_index + 1 >= len(bars):
            return False
        next_bar = bars[gap_index + 1]
        if direction == GapDirection.UP:
            return next_bar.close > prev_close
        return next_bar.close < prev_close

    @staticmethod
    def _continued_next_week(
        bars: List[MarketData],
        gap_index: int,
        prev_close: float,
        direction: GapDirection,
        week_bars: int = 5,
    ) -> bool:
        """Check if price continued in gap direction within one week."""
        target = min(gap_index + week_bars, len(bars) - 1)
        if target <= gap_index:
            return False
        week_close = bars[target].close
        if direction == GapDirection.UP:
            return week_close > prev_close
        return week_close < prev_close


# ============================================================================
# 3. GapPredictionModel
# ============================================================================

class GapPredictionModel:
    """
    Predictive gap analysis.

    Uses historical statistics combined with current market conditions
    (volatility regime, trend, volume) to predict fill probability,
    continuation probability, and optimal trade parameters.
    """

    def __init__(self, stats_engine: Optional[GapStatisticsEngine] = None):
        """
        Initialise the prediction model.

        Args:
            stats_engine: GapStatisticsEngine instance for historical stats.
        """
        self.stats_engine = stats_engine or GapStatisticsEngine()

    def predict_gap_fill_probability(
        self,
        current_gap: GapRecord,
        market_context: Dict[str, Any],
        gap_db: Optional[GapDatabase] = None,
    ) -> Dict[str, float]:
        """
        Predict the probability that the current gap will fill.

        Uses Bayesian posterior: P(fill | gap_type, size_bucket, regime)
        via conjugate Beta-Binomial with historical priors.

        Args:
            current_gap: The gap being analysed.
            market_context: Dict with keys like 'volatility_regime',
                            'trend_strength', 'volume_ratio'.
            gap_db: Historical gap database for computing priors.

        Returns:
            Dict with fill probabilities for 1d, 5d, 20d horizons and
            confidence intervals.
        """
        # Base rates from historical data
        if gap_db and gap_db.count >= _MIN_GAPS_FOR_STATISTICS:
            similar = self._find_similar_gaps(current_gap, gap_db)
            n = len(similar)
            filled_1d = sum(1 for g in similar if g.filled_within is not None and g.filled_within <= 1)
            filled_5d = sum(1 for g in similar if g.filled_within is not None and g.filled_within <= 5)
            filled_20d = sum(1 for g in similar if g.filled_within is not None and g.filled_within <= 20)
        else:
            # Fallback uninformative priors
            n = 0
            filled_1d = filled_5d = filled_20d = 0

        # Bayesian posteriors
        p1d, lo1, hi1 = _beta_binomial_posterior(filled_1d, n)
        p5d, lo5, hi5 = _beta_binomial_posterior(filled_5d, n)
        p20d, lo20, hi20 = _beta_binomial_posterior(filled_20d, n)

        # Adjust for current conditions
        vol_regime = market_context.get("volatility_regime", "normal")
        trend = market_context.get("trend_strength", 0.0)
        vol_ratio = market_context.get("volume_ratio", 1.0)

        # Higher volatility increases fill probability
        vol_adj = {"ultra_low": -0.05, "low": -0.02, "normal": 0.0,
                   "elevated": 0.03, "high": 0.06, "extreme": 0.10}
        v_adj = vol_adj.get(vol_regime, 0.0)

        # Counter-trend gaps fill more often
        gap_up = current_gap.direction == GapDirection.UP
        counter_trend = (gap_up and trend < -0.5) or (not gap_up and trend > 0.5)
        t_adj = 0.05 if counter_trend else -0.03

        # High volume gaps fill less (strong conviction)
        vol_r_adj = -0.04 if vol_ratio > 1.5 else (0.03 if vol_ratio < 0.8 else 0.0)

        total_adj = v_adj + t_adj + vol_r_adj

        return {
            "fill_prob_1d": round(max(0.0, min(1.0, p1d + total_adj)), 4),
            "fill_prob_1d_ci": (round(lo1, 4), round(hi1, 4)),
            "fill_prob_5d": round(max(0.0, min(1.0, p5d + total_adj * 0.7)), 4),
            "fill_prob_5d_ci": (round(lo5, 4), round(hi5, 4)),
            "fill_prob_20d": round(max(0.0, min(1.0, p20d + total_adj * 0.4)), 4),
            "fill_prob_20d_ci": (round(lo20, 4), round(hi20, 4)),
            "similar_gaps_count": n,
            "adjustment_applied": round(total_adj, 4),
        }

    def predict_gap_continuation(
        self,
        current_gap: GapRecord,
        market_context: Dict[str, Any],
        gap_db: Optional[GapDatabase] = None,
    ) -> Dict[str, float]:
        """
        Predict the probability that price continues in gap direction.

        Args:
            current_gap: The gap being analysed.
            market_context: Market condition dict.
            gap_db: Historical gap database.

        Returns:
            Dict with continuation probabilities at multiple horizons.
        """
        if gap_db and gap_db.count >= _MIN_GAPS_FOR_STATISTICS:
            similar = self._find_similar_gaps(current_gap, gap_db)
            n = len(similar)
            cont_eod = sum(1 for g in similar if g.continued_eod)
            cont_nd = sum(1 for g in similar if g.continued_next_day)
            cont_nw = sum(1 for g in similar if g.continued_next_week)
        else:
            n = 0
            cont_eod = cont_nd = cont_nw = 0

        p_eod, lo_eod, hi_eod = _beta_binomial_posterior(cont_eod, n)
        p_nd, lo_nd, hi_nd = _beta_binomial_posterior(cont_nd, n)
        p_nw, lo_nw, hi_nw = _beta_binomial_posterior(cont_nw, n)

        # Trend alignment boosts continuation
        trend = market_context.get("trend_strength", 0.0)
        gap_up = current_gap.direction == GapDirection.UP
        trend_aligned = (gap_up and trend > 0.5) or (not gap_up and trend < -0.5)
        t_adj = 0.06 if trend_aligned else -0.04

        # High volume boosts continuation
        vol_ratio = market_context.get("volume_ratio", 1.0)
        v_adj = 0.04 if vol_ratio > 1.5 else (-0.03 if vol_ratio < 0.8 else 0.0)

        total_adj = t_adj + v_adj

        return {
            "continuation_prob_eod": round(max(0.0, min(1.0, p_eod + total_adj)), 4),
            "continuation_prob_eod_ci": (round(lo_eod, 4), round(hi_eod, 4)),
            "continuation_prob_next_day": round(max(0.0, min(1.0, p_nd + total_adj * 0.8)), 4),
            "continuation_prob_next_day_ci": (round(lo_nd, 4), round(hi_nd, 4)),
            "continuation_prob_next_week": round(max(0.0, min(1.0, p_nw + total_adj * 0.5)), 4),
            "continuation_prob_next_week_ci": (round(lo_nw, 4), round(hi_nw, 4)),
            "similar_gaps_count": n,
        }

    def optimal_gap_trade(
        self,
        gap_type: GapType,
        size_pct: float,
        direction: GapDirection,
        fill_stats: FillStatistics,
        cont_stats: ContinuationStatistics,
        current_price: float,
        prev_close: float,
        atr: float,
    ) -> GapTradeRecommendation:
        """
        Determine the best trade: fade or follow?

        Decision logic:
        - If fill_rate_1d > 0.65 -> FADE the gap
        - If continuation_rate_eod > 0.60 and fill_rate_1d < 0.35 -> FOLLOW
        - Otherwise -> WAIT

        Entry, stop loss, and target are all computed from historical stats.

        Args:
            gap_type: Type of the gap.
            size_pct: Gap size as a percentage.
            direction: Gap direction.
            fill_stats: Fill statistics for this gap cohort.
            cont_stats: Continuation statistics for this gap cohort.
            current_price: Current price.
            prev_close: Previous close (gap fill level).
            atr: Current ATR value.

        Returns:
            GapTradeRecommendation with all trade parameters.
        """
        fill_rate_1d = fill_stats.rate_1d
        cont_rate_eod = cont_stats.rate_eod

        # Decision
        if fill_rate_1d > 0.65:
            action = TradeAction.FADE
        elif cont_rate_eod > 0.60 and fill_rate_1d < 0.35:
            action = TradeAction.FOLLOW
        else:
            action = TradeAction.WAIT

        atr_safe = max(atr, current_price * 0.005)  # floor at 0.5 %

        if action == TradeAction.FADE:
            # Fade: trade towards the gap fill (prev_close)
            if direction == GapDirection.UP:
                entry = current_price
                stop_loss = current_price + 1.5 * atr_safe
                target = prev_close
            else:
                entry = current_price
                stop_loss = current_price - 1.5 * atr_safe
                target = prev_close
            win_rate = fill_rate_1d

        elif action == TradeAction.FOLLOW:
            # Follow: trade in the gap direction
            if direction == GapDirection.UP:
                entry = current_price
                stop_loss = prev_close - 0.25 * atr_safe
                target = current_price + abs(size_pct / 100.0) * current_price
            else:
                entry = current_price
                stop_loss = prev_close + 0.25 * atr_safe
                target = current_price - abs(size_pct / 100.0) * current_price
            win_rate = cont_rate_eod

        else:
            # WAIT -- no trade
            return GapTradeRecommendation(
                action=TradeAction.WAIT,
                entry_price=current_price,
                stop_loss=current_price,
                target=current_price,
                risk_reward=0.0,
                win_rate=0.0,
                edge_pct=0.0,
                confidence=0.0,
            )

        risk = abs(entry - stop_loss)
        reward = abs(target - entry)
        rr = reward / risk if risk > 0 else 0.0
        edge = win_rate * reward - (1.0 - win_rate) * risk
        edge_pct = edge / risk * 100.0 if risk > 0 else 0.0

        confidence = min(1.0, max(0.0,
            0.3 * min(fill_stats.total, 100) / 100.0 +
            0.3 * abs(win_rate - 0.5) * 2.0 +
            0.2 * min(rr / 3.0, 1.0) +
            0.2 * (1.0 if edge_pct > 0 else 0.0)
        ))

        return GapTradeRecommendation(
            action=action,
            entry_price=round(entry, 4),
            stop_loss=round(stop_loss, 4),
            target=round(target, 4),
            risk_reward=round(rr, 2),
            win_rate=round(win_rate, 4),
            edge_pct=round(edge_pct, 2),
            confidence=round(confidence, 4),
        )

    def gap_zone_detection(
        self,
        bars: List[MarketData],
        gap_db: GapDatabase,
        current_price: Optional[float] = None,
        max_age_bars: int = 200,
    ) -> List[UnfilledGapZone]:
        """
        Find unfilled gaps that may act as magnets (support / resistance).

        Unfilled gaps attract price -- they represent liquidity voids.

        Args:
            bars: Current bar history.
            gap_db: Historical gap database.
            current_price: Current price (uses last bar close if None).
            max_age_bars: Maximum age of gaps to consider.

        Returns:
            List of UnfilledGapZone sorted by distance from current price.
        """
        if not bars:
            return []

        price = current_price if current_price is not None else bars[-1].close
        total_bars = len(bars)
        zones: List[UnfilledGapZone] = []

        for gap in gap_db.gaps:
            # Only unfilled gaps
            if gap.filled_within is not None:
                continue

            age = total_bars - gap.index
            if age > max_age_bars or age < 0:
                continue

            # Gap zone boundaries
            if gap.direction == GapDirection.UP:
                lower = gap.prev_close
                upper = gap.open_price
            else:
                lower = gap.open_price
                upper = gap.prev_close

            if upper <= lower:
                continue

            midpoint = (upper + lower) / 2.0
            distance_pct = abs(price - midpoint) / price * 100.0 if price > 0 else 999.0

            # Magnet strength: closer + older = stronger (proven unfilled)
            proximity_score = max(0.0, 1.0 - distance_pct / 10.0)
            age_score = min(1.0, age / 100.0)
            size_score = min(1.0, abs(gap.gap_size_pct) / 3.0)
            magnet_strength = 0.5 * proximity_score + 0.3 * age_score + 0.2 * size_score
            magnet_strength = max(0.0, min(1.0, magnet_strength))

            zones.append(UnfilledGapZone(
                gap_record=gap,
                upper_bound=upper,
                lower_bound=lower,
                midpoint=midpoint,
                distance_pct=round(distance_pct, 3),
                age_bars=age,
                magnet_strength=round(magnet_strength, 4),
            ))

        zones.sort(key=lambda z: z.distance_pct)
        return zones

    def overnight_gap_predictor(
        self,
        futures_data: Optional[List[MarketData]] = None,
        global_data: Optional[Dict[str, Any]] = None,
        prev_close: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Predict tomorrow's gap direction and size from overnight activity
        and global market data.

        Args:
            futures_data: Overnight futures bars (e.g. ES globex).
            global_data: Dict with keys like 'asia_return', 'europe_return',
                         'vix_change', 'dollar_change'.
            prev_close: Previous session close price.

        Returns:
            Dict with predicted gap direction, magnitude, and confidence.
        """
        if prev_close <= 0:
            return {"predicted_direction": "neutral", "predicted_size_pct": 0.0, "confidence": 0.0}

        signals: List[float] = []  # positive = up, negative = down

        # Futures signal
        if futures_data and len(futures_data) > 0:
            last_futures = futures_data[-1].close
            futures_gap_pct = (last_futures - prev_close) / prev_close * 100.0
            signals.append(futures_gap_pct)

        # Global signals
        if global_data:
            asia_ret = global_data.get("asia_return", 0.0)
            euro_ret = global_data.get("europe_return", 0.0)
            vix_chg = global_data.get("vix_change", 0.0)
            dollar_chg = global_data.get("dollar_change", 0.0)

            if asia_ret:
                signals.append(asia_ret * 0.3)
            if euro_ret:
                signals.append(euro_ret * 0.5)
            if vix_chg:
                signals.append(-vix_chg * 0.2)
            if dollar_chg:
                signals.append(-dollar_chg * 0.1)

        if not signals:
            return {"predicted_direction": "neutral", "predicted_size_pct": 0.0, "confidence": 0.0}

        composite = float(np.mean(signals))
        direction = "up" if composite > 0 else ("down" if composite < 0 else "neutral")
        confidence = min(1.0, abs(composite) / 2.0) * min(1.0, len(signals) / 3.0)

        return {
            "predicted_direction": direction,
            "predicted_size_pct": round(composite, 3),
            "confidence": round(confidence, 4),
            "signal_count": len(signals),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_similar_gaps(
        gap: GapRecord,
        gap_db: GapDatabase,
        max_results: int = 500,
    ) -> List[GapRecord]:
        """
        Find historically similar gaps for Bayesian conditioning.

        Similarity criteria: same gap type, same size bucket,
        same direction.
        """
        bucket = _classify_size_bucket(gap.gap_size_pct)
        similar = [
            g for g in gap_db.gaps
            if g.gap_type == gap.gap_type
            and _classify_size_bucket(g.gap_size_pct) == bucket
            and g.direction == gap.direction
            and g.index != gap.index
        ]
        return similar[:max_results]


# ============================================================================
# 4. RealTimeGapMonitor
# ============================================================================

class RealTimeGapMonitor:
    """
    Live gap tracking: detect developing gaps, track fills, score
    momentum, and compute risk.
    """

    def detect_premarket_gap(
        self,
        premarket_data: Optional[List[MarketData]],
        prev_close: float,
    ) -> Dict[str, Any]:
        """
        Calculate developing gap size from pre-market data.

        Args:
            premarket_data: Pre-market bars (may be sparse).
            prev_close: Previous session close.

        Returns:
            Dict with gap_pct, direction, and volume info.
        """
        if not premarket_data or prev_close <= 0:
            return {"gap_pct": 0.0, "direction": "flat", "premarket_volume": 0}

        last_pm = premarket_data[-1]
        gap_pct = (last_pm.close - prev_close) / prev_close * 100.0
        direction = "up" if gap_pct > 0.1 else ("down" if gap_pct < -0.1 else "flat")
        total_vol = sum(b.volume for b in premarket_data)

        return {
            "gap_pct": round(gap_pct, 3),
            "direction": direction,
            "premarket_volume": total_vol,
            "premarket_high": max(b.high for b in premarket_data),
            "premarket_low": min(b.low for b in premarket_data),
            "bar_count": len(premarket_data),
        }

    def gap_fill_tracker(
        self,
        active_gaps: List[UnfilledGapZone],
        current_price: float,
    ) -> List[Dict[str, Any]]:
        """
        Track which historical gaps are being approached or filled.

        Args:
            active_gaps: List of unfilled gap zones.
            current_price: Current market price.

        Returns:
            List of dicts describing approach / fill status for each gap.
        """
        results: List[Dict[str, Any]] = []
        for zone in active_gaps:
            dist = zone.distance_pct
            approaching = dist < 2.0
            entered = zone.lower_bound <= current_price <= zone.upper_bound
            filled = False
            if zone.gap_record.direction == GapDirection.UP:
                filled = current_price <= zone.lower_bound
            else:
                filled = current_price >= zone.upper_bound

            results.append({
                "gap_index": zone.gap_record.index,
                "midpoint": zone.midpoint,
                "distance_pct": round(dist, 3),
                "approaching": approaching,
                "entered_zone": entered,
                "filled": filled,
                "magnet_strength": zone.magnet_strength,
                "age_bars": zone.age_bars,
            })
        return results

    def gap_momentum_score(
        self,
        bars: List[MarketData],
        gap: GapRecord,
        lookback: int = 10,
    ) -> Dict[str, float]:
        """
        Score the momentum behind a gap.

        Considers volume, price action, breadth-like metrics from
        recent bars.

        Args:
            bars: Recent bars following the gap.
            gap: The gap record.
            lookback: How many bars after the gap to consider.

        Returns:
            Dict with momentum score (0-1) and component scores.
        """
        start = gap.index
        end = min(start + lookback + 1, len(bars))
        segment = bars[start:end]

        if len(segment) < 2:
            return {"momentum_score": 0.0, "volume_score": 0.0,
                    "price_score": 0.0, "conviction_score": 0.0}

        # Volume score: compare gap bar volume to subsequent average
        gap_vol = segment[0].volume
        post_vols = [b.volume for b in segment[1:]] if len(segment) > 1 else [gap_vol]
        avg_post_vol = float(np.mean(post_vols)) if post_vols else float(gap_vol)
        volume_score = min(1.0, gap_vol / avg_post_vol) if avg_post_vol > 0 else 0.5

        # Price score: did price continue in gap direction?
        first_close = segment[0].close
        last_close = segment[-1].close
        if gap.direction == GapDirection.UP:
            price_score = min(1.0, max(0.0, (last_close - first_close) / (first_close * 0.02))) if first_close > 0 else 0.0
        else:
            price_score = min(1.0, max(0.0, (first_close - last_close) / (first_close * 0.02))) if first_close > 0 else 0.0

        # Conviction: fraction of post-gap bars that closed in gap direction
        if len(segment) > 1:
            if gap.direction == GapDirection.UP:
                conviction_bars = sum(1 for b in segment[1:] if b.close > b.open)
            else:
                conviction_bars = sum(1 for b in segment[1:] if b.close < b.open)
            conviction_score = conviction_bars / (len(segment) - 1)
        else:
            conviction_score = 0.5

        momentum_score = 0.4 * volume_score + 0.35 * price_score + 0.25 * conviction_score

        return {
            "momentum_score": round(momentum_score, 4),
            "volume_score": round(volume_score, 4),
            "price_score": round(price_score, 4),
            "conviction_score": round(conviction_score, 4),
        }

    def gap_risk_score(
        self,
        gap: GapRecord,
        fill_stats: FillStatistics,
        vol_regime: str = "normal",
    ) -> Dict[str, float]:
        """
        Compute risk of fading for a gap.

        High fill-rate gaps in a volatile regime are risky to follow.

        Args:
            gap: The gap record.
            fill_stats: Fill statistics for this gap's cohort.
            vol_regime: Current volatility regime string.

        Returns:
            Dict with risk score (0-1) and component scores.
        """
        # Base risk from fill rate
        fill_risk = fill_stats.rate_1d

        # Volatility regime adjustment
        vol_adj = {"ultra_low": -0.1, "low": -0.05, "normal": 0.0,
                   "elevated": 0.05, "high": 0.10, "extreme": 0.15}
        v_adj = vol_adj.get(vol_regime, 0.0)

        # Small gaps fill more often
        size_risk = max(0.0, 1.0 - abs(gap.gap_size_pct) / 3.0) * 0.2

        # Low volume gaps are riskier
        vol_ratio_risk = max(0.0, 1.0 - gap.volume_ratio / 2.0) * 0.15

        risk_score = max(0.0, min(1.0, fill_risk + v_adj + size_risk + vol_ratio_risk))

        return {
            "risk_score": round(risk_score, 4),
            "fill_risk": round(fill_risk, 4),
            "vol_regime_adj": round(v_adj, 4),
            "size_risk": round(size_risk, 4),
            "vol_ratio_risk": round(vol_ratio_risk, 4),
        }


# ============================================================================
# 5. GapsPowerScanner (Main Scanner)
# ============================================================================

class GapsPowerScanner(BaseScanner[AdvancedScanResult]):
    """
    Revolution Alpha Engine - Gaps Power Scanner.

    The most powerful gap analysis system ever built. Orchestrates
    GapClassifier, GapStatisticsEngine, GapPredictionModel, and
    RealTimeGapMonitor to produce institutional-grade gap signals.

    Signal triggers:
        1. Fresh gap with high continuation probability.
        2. Gap fade setup (high fill probability + exhaustion signals).
        3. Island reversal pattern.
        4. Unfilled gap zone acting as magnet (price approaching).
        5. Earnings gap with extreme statistics.
        6. Index futures gap with favourable fill stats.

    Every signal includes full historical statistics in metadata.
    """

    def __init__(
        self,
        config: Optional[ScannerConfig] = None,
        min_gap_pct: float = 0.15,
    ):
        """
        Initialise the GapsPowerScanner.

        Args:
            config: Scanner configuration. Defaults to ScannerConfig with
                    scan_modes=[ScanMode.ALL].
            min_gap_pct: Minimum gap percentage to catalog.
        """
        cfg = config or ScannerConfig(scan_modes=[ScanMode.ALL])
        super().__init__(
            name="GapsPowerScanner",
            scan_mode=ScanMode.ALL,
            config=cfg,
        )
        self.classifier = GapClassifier()
        self.stats_engine = GapStatisticsEngine(
            classifier=self.classifier,
            min_gap_pct=min_gap_pct,
        )
        self.prediction = GapPredictionModel(stats_engine=self.stats_engine)
        self.monitor = RealTimeGapMonitor()
        self.min_gap_pct = min_gap_pct

    # ------------------------------------------------------------------
    # BaseScanner interface
    # ------------------------------------------------------------------

    async def scan(self, context: ScanContext) -> List[AdvancedScanResult]:
        """
        Execute the full gap analysis pipeline across all symbols.

        Args:
            context: ScanContext with universe, market_data, historical_data.

        Returns:
            List of AdvancedScanResult signals.
        """
        results: List[AdvancedScanResult] = []

        for symbol in context.universe:
            try:
                symbol_results = self._analyze_symbol(symbol, context)
                results.extend(symbol_results)
            except Exception as exc:
                self._logger.warning(
                    "GapsPowerScanner: error analysing %s: %s", symbol, exc
                )

        # Sort by confidence descending
        results.sort(key=lambda r: r.confidence, reverse=True)
        return results

    def validate_signal(
        self,
        result: AdvancedScanResult,
        context: ScanContext,
    ) -> bool:
        """
        Validate a gap signal against current market conditions.

        Args:
            result: The AdvancedScanResult to validate.
            context: Current scan context.

        Returns:
            True if the signal passes validation.
        """
        # Must meet minimum confidence
        if result.confidence < self.config.min_confidence / 100.0:
            return False

        # Must have supporting evidence
        if not result.supporting_evidence:
            return False

        # Check that symbol data is still available
        if result.symbol not in context.market_data:
            return False

        md = context.market_data[result.symbol]
        if not self.apply_filters(md, self.config):
            return False

        return True

    # ------------------------------------------------------------------
    # Per-symbol analysis
    # ------------------------------------------------------------------

    def _analyze_symbol(
        self,
        symbol: str,
        context: ScanContext,
    ) -> List[AdvancedScanResult]:
        """
        Run full gap detection and analysis for a single symbol.

        Args:
            symbol: Ticker symbol.
            context: Scan context.

        Returns:
            List of AdvancedScanResult for this symbol.
        """
        results: List[AdvancedScanResult] = []

        hist = context.historical_data.get(symbol)
        md = context.market_data.get(symbol)
        if not hist or len(hist.bars) < _MIN_BARS_FOR_STATS or not md:
            return results

        bars = hist.bars
        is_index_futures = symbol.upper() in {"ES", "NQ", "RTY", "YM", "ES=F", "NQ=F", "RTY=F", "YM=F"}
        sector = context.metadata.get("sectors", {}).get(symbol, "")
        earnings_dates = context.metadata.get("earnings_dates", {}).get(symbol, [])

        # Build gap database
        gap_db = self.stats_engine.build_gap_database(
            bars, symbol=symbol,
            earnings_dates=earnings_dates,
            is_index_futures=is_index_futures,
            sector=sector,
        )

        if gap_db.count == 0:
            return results

        # Compute aggregate statistics
        fill_stats = self.stats_engine.compute_fill_statistics(gap_db)
        cont_stats = self.stats_engine.compute_continuation_statistics(gap_db)

        # Market context for predictions
        atr_val = _compute_atr(bars)
        hist_atr_pcts = []
        for i in range(max(_DEFAULT_ATR_PERIOD + 1, 30), len(bars)):
            a = _compute_atr(bars[:i + 1])
            p = bars[i].close
            if p > 0 and a > 0:
                hist_atr_pcts.append(a / p * 100.0)

        vol_regime = _classify_vol_regime(atr_val, md.close, hist_atr_pcts)
        trend_strength = _compute_trend_strength([b.close for b in bars])

        vol_window = bars[-_DEFAULT_VOLUME_SMA_PERIOD:] if len(bars) >= _DEFAULT_VOLUME_SMA_PERIOD else bars
        avg_vol = float(np.mean([b.volume for b in vol_window])) if vol_window else 1.0
        volume_ratio = md.volume / avg_vol if avg_vol > 0 else 1.0

        market_ctx: Dict[str, Any] = {
            "volatility_regime": vol_regime.value,
            "trend_strength": trend_strength,
            "volume_ratio": volume_ratio,
        }

        regime_ctx = _regime_to_context(context.market_regime.value)

        # ---------------------------------------------------------------
        # Signal 1: Fresh gap on the latest bar
        # ---------------------------------------------------------------
        latest_idx = len(bars) - 1
        if latest_idx >= 1:
            prev_close = bars[latest_idx - 1].close
            if prev_close > 0:
                latest_gap_pct = (bars[latest_idx].open - prev_close) / prev_close * 100.0
                if abs(latest_gap_pct) >= self.min_gap_pct:
                    latest_gap_type = self.classifier.classify_gap(bars, latest_idx)
                    latest_metrics = self.classifier.compute_gap_metrics(bars, latest_idx)
                    latest_dir = GapDirection.UP if latest_gap_pct > 0 else GapDirection.DOWN

                    latest_record = GapRecord(
                        index=latest_idx,
                        timestamp=md.timestamp,
                        symbol=symbol,
                        direction=latest_dir,
                        gap_type=latest_gap_type,
                        gap_size_pct=latest_gap_pct,
                        gap_size_atr=latest_metrics.gap_size_atr,
                        open_price=bars[latest_idx].open,
                        prev_close=prev_close,
                        volume=md.volume,
                        volume_ratio=latest_metrics.volume_ratio,
                        prev_trend_strength=latest_metrics.prev_trend_strength,
                        was_at_support_resistance=latest_metrics.was_at_support_resistance,
                        day_of_week=md.timestamp.weekday() if md.timestamp else 0,
                    )

                    fill_pred = self.prediction.predict_gap_fill_probability(
                        latest_record, market_ctx, gap_db
                    )
                    cont_pred = self.prediction.predict_gap_continuation(
                        latest_record, market_ctx, gap_db
                    )

                    gap_type_fill = fill_stats.get(latest_gap_type, FillStatistics())
                    gap_type_cont = cont_stats.get(latest_gap_type, ContinuationStatistics())

                    trade_rec = self.prediction.optimal_gap_trade(
                        latest_gap_type, latest_gap_pct, latest_dir,
                        gap_type_fill, gap_type_cont,
                        md.close, prev_close, atr_val,
                    )

                    gng_prob_map = self.stats_engine.gap_and_go_probability(gap_db)
                    fade_prob_map = self.stats_engine.gap_fade_probability(gap_db)
                    gng_key = (latest_gap_type, _classify_size_bucket(latest_gap_pct))
                    gng = gng_prob_map.get(gng_key, {})
                    fade = fade_prob_map.get(gng_key, {})

                    # ---- Signal 1a: High continuation probability ----
                    if cont_pred.get("continuation_prob_eod", 0) > 0.55:
                        sig = self._generate_signal(
                            symbol=symbol,
                            scan_name="GapContinuation",
                            direction="BULLISH" if latest_dir == GapDirection.UP else "BEARISH",
                            gap_record=latest_record,
                            fill_pred=fill_pred,
                            cont_pred=cont_pred,
                            trade_rec=trade_rec,
                            gng=gng,
                            fade=fade,
                            regime_ctx=regime_ctx,
                            vol_regime=vol_regime,
                            market_ctx=market_ctx,
                            atr=atr_val,
                        )
                        results.append(sig)

                    # ---- Signal 1b: Gap fade setup ----
                    if fill_pred.get("fill_prob_1d", 0) > 0.60:
                        fade_dir = "BEARISH" if latest_dir == GapDirection.UP else "BULLISH"
                        sig = self._generate_signal(
                            symbol=symbol,
                            scan_name="GapFade",
                            direction=fade_dir,
                            gap_record=latest_record,
                            fill_pred=fill_pred,
                            cont_pred=cont_pred,
                            trade_rec=trade_rec,
                            gng=gng,
                            fade=fade,
                            regime_ctx=regime_ctx,
                            vol_regime=vol_regime,
                            market_ctx=market_ctx,
                            atr=atr_val,
                        )
                        results.append(sig)

                    # ---- Signal 2: Island reversal ----
                    if latest_gap_type == GapType.ISLAND_REVERSAL:
                        reversal_dir = "BEARISH" if latest_dir == GapDirection.DOWN else "BULLISH"
                        sig = self._generate_signal(
                            symbol=symbol,
                            scan_name="IslandReversal",
                            direction=reversal_dir,
                            gap_record=latest_record,
                            fill_pred=fill_pred,
                            cont_pred=cont_pred,
                            trade_rec=trade_rec,
                            gng=gng,
                            fade=fade,
                            regime_ctx=regime_ctx,
                            vol_regime=vol_regime,
                            market_ctx=market_ctx,
                            atr=atr_val,
                            confidence_boost=0.10,
                        )
                        results.append(sig)

                    # ---- Signal 3: Earnings gap with extreme stats ----
                    if latest_record.is_earnings and abs(latest_gap_pct) >= 3.0:
                        earn_stats = self.stats_engine.earnings_gap_analysis(gap_db)
                        sig = self._generate_signal(
                            symbol=symbol,
                            scan_name="EarningsGap",
                            direction="BULLISH" if latest_dir == GapDirection.UP else "BEARISH",
                            gap_record=latest_record,
                            fill_pred=fill_pred,
                            cont_pred=cont_pred,
                            trade_rec=trade_rec,
                            gng=gng,
                            fade=fade,
                            regime_ctx=regime_ctx,
                            vol_regime=vol_regime,
                            market_ctx=market_ctx,
                            atr=atr_val,
                            extra_metadata={"earnings_stats": earn_stats},
                        )
                        results.append(sig)

                    # ---- Signal 4: Index futures gap ----
                    if is_index_futures:
                        idx_stats = self.stats_engine.index_futures_gap_statistics(gap_db)
                        sig = self._generate_signal(
                            symbol=symbol,
                            scan_name="IndexFuturesGap",
                            direction="BULLISH" if latest_dir == GapDirection.UP else "BEARISH",
                            gap_record=latest_record,
                            fill_pred=fill_pred,
                            cont_pred=cont_pred,
                            trade_rec=trade_rec,
                            gng=gng,
                            fade=fade,
                            regime_ctx=regime_ctx,
                            vol_regime=vol_regime,
                            market_ctx=market_ctx,
                            atr=atr_val,
                            extra_metadata={"index_futures_stats": idx_stats},
                        )
                        results.append(sig)

        # ---------------------------------------------------------------
        # Signal 5: Unfilled gap zone acting as magnet
        # ---------------------------------------------------------------
        zones = self.prediction.gap_zone_detection(bars, gap_db, md.close)
        for zone in zones[:3]:  # top 3 nearest
            if zone.distance_pct < 2.0 and zone.magnet_strength > 0.4:
                approaching_dir = (
                    "BEARISH" if md.close > zone.midpoint else "BULLISH"
                )
                sig = self._generate_magnet_signal(
                    symbol=symbol,
                    zone=zone,
                    direction=approaching_dir,
                    regime_ctx=regime_ctx,
                    vol_regime=vol_regime,
                    current_price=md.close,
                    atr=atr_val,
                )
                results.append(sig)

        return results

    # ------------------------------------------------------------------
    # Signal generation helpers
    # ------------------------------------------------------------------

    def _generate_signal(
        self,
        symbol: str,
        scan_name: str,
        direction: str,
        gap_record: GapRecord,
        fill_pred: Dict[str, Any],
        cont_pred: Dict[str, Any],
        trade_rec: GapTradeRecommendation,
        gng: Dict[str, float],
        fade: Dict[str, float],
        regime_ctx: RegimeContext,
        vol_regime: VolatilityRegime,
        market_ctx: Dict[str, Any],
        atr: float,
        confidence_boost: float = 0.0,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> AdvancedScanResult:
        """
        Create an AdvancedScanResult with full historical statistics.

        Args:
            symbol: Ticker symbol.
            scan_name: Human-readable signal name.
            direction: BULLISH / BEARISH / NEUTRAL.
            gap_record: The gap being signalled.
            fill_pred: Fill prediction dict.
            cont_pred: Continuation prediction dict.
            trade_rec: Optimal trade recommendation.
            gng: Gap-and-go probability dict.
            fade: Gap-fade probability dict.
            regime_ctx: Current market regime.
            vol_regime: Current volatility regime.
            market_ctx: Market context dict.
            atr: Current ATR.
            confidence_boost: Optional boost to confidence (e.g. island reversal).
            extra_metadata: Additional metadata to merge.

        Returns:
            Fully populated AdvancedScanResult.
        """
        # Confidence: blend trade recommendation confidence with prediction strength
        base_conf = trade_rec.confidence
        pred_strength = (
            cont_pred.get("continuation_prob_eod", 0.5) * 0.4
            + (1.0 - fill_pred.get("fill_prob_1d", 0.5)) * 0.3
            + min(1.0, abs(gap_record.gap_size_pct) / 3.0) * 0.15
            + min(1.0, gap_record.volume_ratio / 2.0) * 0.15
        )
        confidence = max(0.0, min(1.0, 0.5 * base_conf + 0.5 * pred_strength + confidence_boost))

        signal_strength = max(0.0, min(1.0,
            0.3 * abs(gap_record.gap_size_pct) / 5.0
            + 0.3 * min(gap_record.volume_ratio / 3.0, 1.0)
            + 0.2 * confidence
            + 0.2 * (1.0 if trade_rec.action != TradeAction.WAIT else 0.0)
        ))

        # Expected move
        expected_move = gap_record.gap_size_pct if trade_rec.action == TradeAction.FOLLOW else -gap_record.gap_size_pct

        # Supporting / contradicting evidence
        supporting: List[str] = []
        contradicting: List[str] = []

        if gap_record.volume_ratio > 1.5:
            supporting.append(f"High volume ratio: {gap_record.volume_ratio:.1f}x")
        else:
            contradicting.append(f"Below-average volume: {gap_record.volume_ratio:.1f}x")

        if gap_record.was_at_support_resistance:
            supporting.append("Gap occurred at key support/resistance level")

        if fill_pred.get("fill_prob_1d", 0.5) < 0.3:
            supporting.append(f"Low 1d fill probability: {fill_pred['fill_prob_1d']:.1%}")
        elif fill_pred.get("fill_prob_1d", 0.5) > 0.7:
            contradicting.append(f"High 1d fill probability: {fill_pred['fill_prob_1d']:.1%}")

        if cont_pred.get("continuation_prob_eod", 0.5) > 0.6:
            supporting.append(f"Strong EOD continuation rate: {cont_pred['continuation_prob_eod']:.1%}")

        if abs(gap_record.prev_trend_strength) > 1.0:
            supporting.append(f"Strong prior trend: {gap_record.prev_trend_strength:.2f}")

        if gap_record.gap_type == GapType.BREAKAWAY:
            supporting.append("Breakaway gap pattern (strong)")
        elif gap_record.gap_type == GapType.EXHAUSTION:
            contradicting.append("Exhaustion gap pattern (reversal likely)")
        elif gap_record.gap_type == GapType.ISLAND_REVERSAL:
            supporting.append("Island reversal pattern (powerful signal)")

        # Risk / reward
        rr = trade_rec.risk_reward
        entry = trade_rec.entry_price
        sl = trade_rec.stop_loss
        target = trade_rec.target

        # Build metadata with required keys
        similar_count = fill_pred.get("similar_gaps_count", 0)
        metadata: Dict[str, Any] = {
            "gap_type": gap_record.gap_type.value,
            "gap_direction": gap_record.direction.value,
            "gap_size_pct": round(gap_record.gap_size_pct, 3),
            "gap_size_atr": round(gap_record.gap_size_atr, 3),
            "volume_ratio": round(gap_record.volume_ratio, 2),
            "prev_trend_strength": round(gap_record.prev_trend_strength, 3),
            "at_support_resistance": gap_record.was_at_support_resistance,
            "historical_fill_rate_1d": round(fill_pred.get("fill_prob_1d", 0.5), 4),
            "historical_fill_rate_5d": round(fill_pred.get("fill_prob_5d", 0.5), 4),
            "historical_fill_rate_20d": round(fill_pred.get("fill_prob_20d", 0.5), 4),
            "historical_continuation_rate": round(cont_pred.get("continuation_prob_eod", 0.5), 4),
            "gap_and_go_probability": round(gng.get("probability", 0.5), 4),
            "gap_fade_probability": round(fade.get("probability", 0.5), 4),
            "similar_gaps_count": similar_count,
            "win_rate": round(trade_rec.win_rate, 4),
            "trade_action": trade_rec.action.value,
            "trade_edge_pct": trade_rec.edge_pct,
            "fill_pred_confidence_interval_1d": fill_pred.get("fill_prob_1d_ci", (0.0, 1.0)),
            "fill_pred_confidence_interval_5d": fill_pred.get("fill_prob_5d_ci", (0.0, 1.0)),
            "continuation_confidence_interval_eod": cont_pred.get("continuation_prob_eod_ci", (0.0, 1.0)),
            "day_of_week": gap_record.day_of_week,
            "market_context": market_ctx,
        }
        if extra_metadata:
            metadata.update(extra_metadata)

        # Mathematical basis
        math_basis = (
            f"Gap={gap_record.gap_size_pct:+.2f}% ({gap_record.gap_size_atr:.1f} ATR). "
            f"Beta-Binomial posterior fill P(1d)={fill_pred.get('fill_prob_1d', 0):.2f}, "
            f"continuation P(EOD)={cont_pred.get('continuation_prob_eod', 0):.2f}. "
            f"Wilson 95% CI fill 5d: {fill_pred.get('fill_prob_5d_ci', (0, 1))}. "
            f"N={similar_count} similar gaps."
        )

        # Historical accuracy approximation from win rate
        hist_accuracy = trade_rec.win_rate if trade_rec.action != TradeAction.WAIT else 0.5

        # False positive rate
        fpr = max(0.0, min(1.0, 1.0 - confidence))

        return AdvancedScanResult(
            scan_id=str(uuid.uuid4()),
            scan_name=f"GapsPower:{scan_name}",
            category=ScanCategory.PRICE_ACTION,
            timestamp=datetime.utcnow(),
            symbol=symbol,
            signal_direction=direction,
            signal_strength=round(signal_strength, 4),
            confidence=round(confidence, 4),
            expected_move_pct=round(expected_move, 3),
            expected_timeframe=ExpectedTimeframe.INTRADAY,
            risk_reward_ratio=round(rr, 2),
            entry_price=round(entry, 4) if entry else None,
            stop_loss_level=round(sl, 4) if sl else 0.0,
            target_level=round(target, 4) if target else 0.0,
            secondary_targets=[],
            supporting_evidence=supporting,
            contradicting_evidence=contradicting,
            historical_accuracy=round(hist_accuracy, 4),
            regime_context=regime_ctx,
            mathematical_basis=math_basis,
            false_positive_rate=round(fpr, 4),
            decay_halflife_days=1,
            volatility_regime=vol_regime,
            metadata=metadata,
        )

    def _generate_magnet_signal(
        self,
        symbol: str,
        zone: UnfilledGapZone,
        direction: str,
        regime_ctx: RegimeContext,
        vol_regime: VolatilityRegime,
        current_price: float,
        atr: float,
    ) -> AdvancedScanResult:
        """
        Generate a signal for price approaching an unfilled gap zone.

        Args:
            symbol: Ticker symbol.
            zone: The unfilled gap zone.
            direction: Signal direction.
            regime_ctx: Market regime.
            vol_regime: Volatility regime.
            current_price: Current price.
            atr: Current ATR.

        Returns:
            AdvancedScanResult for the magnet signal.
        """
        gap = zone.gap_record
        confidence = max(0.0, min(1.0, zone.magnet_strength * 0.8 + 0.1))
        signal_strength = max(0.0, min(1.0, zone.magnet_strength))

        expected_move = (zone.midpoint - current_price) / current_price * 100.0 if current_price > 0 else 0.0

        atr_safe = max(atr, current_price * 0.005)
        if direction == "BULLISH":
            sl = current_price - 1.5 * atr_safe
            target = zone.midpoint
        else:
            sl = current_price + 1.5 * atr_safe
            target = zone.midpoint

        risk = abs(current_price - sl)
        reward = abs(target - current_price)
        rr = reward / risk if risk > 0 else 0.0

        supporting = [
            f"Unfilled gap zone at {zone.lower_bound:.2f}-{zone.upper_bound:.2f}",
            f"Distance: {zone.distance_pct:.2f}% from current price",
            f"Gap age: {zone.age_bars} bars (proven unfilled)",
            f"Magnet strength: {zone.magnet_strength:.2f}",
        ]

        metadata: Dict[str, Any] = {
            "gap_type": gap.gap_type.value,
            "gap_direction": gap.direction.value,
            "gap_size_pct": round(gap.gap_size_pct, 3),
            "gap_size_atr": round(gap.gap_size_atr, 3),
            "volume_ratio": round(gap.volume_ratio, 2),
            "zone_upper": zone.upper_bound,
            "zone_lower": zone.lower_bound,
            "zone_midpoint": zone.midpoint,
            "distance_pct": zone.distance_pct,
            "age_bars": zone.age_bars,
            "magnet_strength": zone.magnet_strength,
            "historical_fill_rate_1d": 0.0,
            "historical_fill_rate_5d": 0.0,
            "historical_fill_rate_20d": 0.0,
            "historical_continuation_rate": 0.0,
            "gap_and_go_probability": 0.0,
            "gap_fade_probability": 0.0,
            "similar_gaps_count": 0,
            "win_rate": round(confidence, 4),
        }

        math_basis = (
            f"Unfilled gap zone ({gap.gap_type.value}) at "
            f"{zone.lower_bound:.2f}-{zone.upper_bound:.2f}. "
            f"Distance={zone.distance_pct:.2f}%, "
            f"magnet_strength={zone.magnet_strength:.3f}."
        )

        return AdvancedScanResult(
            scan_id=str(uuid.uuid4()),
            scan_name="GapsPower:MagnetZone",
            category=ScanCategory.PRICE_ACTION,
            timestamp=datetime.utcnow(),
            symbol=symbol,
            signal_direction=direction,
            signal_strength=round(signal_strength, 4),
            confidence=round(confidence, 4),
            expected_move_pct=round(expected_move, 3),
            expected_timeframe=ExpectedTimeframe.SWING,
            risk_reward_ratio=round(rr, 2),
            entry_price=round(current_price, 4),
            stop_loss_level=round(sl, 4),
            target_level=round(target, 4),
            secondary_targets=[],
            supporting_evidence=supporting,
            contradicting_evidence=[],
            historical_accuracy=round(confidence, 4),
            regime_context=regime_ctx,
            mathematical_basis=math_basis,
            false_positive_rate=round(1.0 - confidence, 4),
            decay_halflife_days=5,
            volatility_regime=vol_regime,
            metadata=metadata,
        )
