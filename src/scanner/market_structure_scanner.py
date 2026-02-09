"""
Revolution Alpha Engine - Predictive Structure Intelligence Scanner

Revolution Alpha's proprietary market structure detection system.
We see the move BEFORE the move. We are ahead of institutions.

Detects predictive price structure using:
- Structure Shift Detection (SSD) — trend continuation & reversal breaks
- Price Imbalance Zones (PIZ) — gaps left by aggressive momentum
- Demand/Supply Accumulation Zones (DSAZ) — with volume confirmation
- Liquidity Trap Detection (LTD) — false breakout / trap identification
- Value Zone classification — overextended vs. discounted pricing

Mathematical Basis:
    Grounded in auction market theory and statistical price behavior.
    Price moves from efficiency (fair value) to inefficiency (imbalances).
    Accumulation/distribution zones form before explosive directional moves.
    Liquidity traps reveal exhaustion and set up high-probability reversals.

References:
    - Auction Market Theory (Steidlmayer)
    - Wyckoff methodology (accumulation, distribution phases)
    - Revolution Alpha proprietary research
"""

import numpy as np
from typing import Optional, List, Tuple, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging
import uuid

from .base import (
    BaseScanner,
    ScanContext,
    MarketData,
    HistoricalData,
)
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
    StructureBreak,
    FairValueGap,
    OrderBlock,
    LiquiditySweep,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MIN_BARS_FOR_STRUCTURE = 30
"""Minimum number of bars required for meaningful structure analysis."""

_EQUAL_LEVEL_TOLERANCE = 0.001
"""Relative tolerance (0.1%) for identifying equal highs/lows."""

_FVG_MIN_SIZE_PCT = 0.0005
"""Minimum FVG size as a fraction of price to be considered significant."""

_OB_IMPULSE_ATR_MULTIPLE = 2.0
"""Minimum impulse move in ATR multiples to qualify an order block."""

_SWEEP_REVERSAL_BARS = 3
"""Number of bars to look ahead for price reversal after a sweep."""

_SWEEP_MIN_DEPTH_PCT = 0.0001
"""Minimum depth past the swept level as a fraction of price."""


# ============================================================================
# Data Structures
# ============================================================================

class SwingType(str, Enum):
    """Classification of a swing point."""
    HIGH = "high"
    LOW = "low"


@dataclass(frozen=True)
class SwingPoint:
    """Immutable representation of a swing high or swing low.

    Attributes:
        index: Bar index within the price array where the swing occurred.
        price: Price level of the swing point.
        swing_type: Whether this is a swing high or swing low.
    """
    index: int
    price: float
    swing_type: SwingType

    def as_tuple(self) -> Tuple[int, float, str]:
        """Return the legacy (index, price, type_str) tuple."""
        return (self.index, self.price, self.swing_type.value)


@dataclass
class StructureContext:
    """Aggregated market-structure context for a single symbol.

    Populated by the scanner and used to determine the composite signal.
    """
    swings: List[SwingPoint] = field(default_factory=list)
    structure_breaks: List[StructureBreak] = field(default_factory=list)
    fair_value_gaps: List[FairValueGap] = field(default_factory=list)
    order_blocks: List[OrderBlock] = field(default_factory=list)
    liquidity_sweeps: List[LiquiditySweep] = field(default_factory=list)
    premium_discount: str = "equilibrium"
    dealing_range_high: float = 0.0
    dealing_range_low: float = 0.0


# ============================================================================
# 1. SwingDetector
# ============================================================================

class SwingDetector:
    """Detect swing highs and swing lows from OHLC arrays.

    A swing high at index *i* is confirmed when the high at *i* is strictly
    greater than the highs of the surrounding ``lookback`` bars on each side.
    Symmetrically, a swing low at *i* requires the low at *i* to be strictly
    less than the lows on both sides.

    Parameters
    ----------
    lookback : int, default 5
        Number of bars on each side required to confirm a swing.
    """

    def __init__(self, lookback: int = 5):
        if lookback < 1:
            raise ValueError("lookback must be >= 1")
        self.lookback = lookback

    def detect_swings(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        lookback: Optional[int] = None,
    ) -> List[SwingPoint]:
        """Identify swing highs and swing lows.

        Parameters
        ----------
        highs : np.ndarray
            Array of high prices.
        lows : np.ndarray
            Array of low prices.
        closes : np.ndarray
            Array of close prices (used for tie-breaking / context).
        lookback : int or None
            Override instance lookback if provided.

        Returns
        -------
        list[SwingPoint]
            Swing points sorted by index, each carrying its type.
        """
        highs = np.asarray(highs, dtype=np.float64)
        lows = np.asarray(lows, dtype=np.float64)
        closes = np.asarray(closes, dtype=np.float64)

        n = len(highs)
        lb = lookback if lookback is not None else self.lookback

        if n < 2 * lb + 1:
            return []

        swings: List[SwingPoint] = []

        for i in range(lb, n - lb):
            # --- Swing High ---
            left_highs = highs[i - lb:i]
            right_highs = highs[i + 1:i + 1 + lb]

            if np.all(highs[i] > left_highs) and np.all(highs[i] > right_highs):
                swings.append(SwingPoint(index=i, price=float(highs[i]), swing_type=SwingType.HIGH))

            # --- Swing Low ---
            left_lows = lows[i - lb:i]
            right_lows = lows[i + 1:i + 1 + lb]

            if np.all(lows[i] < left_lows) and np.all(lows[i] < right_lows):
                swings.append(SwingPoint(index=i, price=float(lows[i]), swing_type=SwingType.LOW))

        # Sort by index (should already be, but enforce)
        swings.sort(key=lambda s: s.index)
        return swings


# ============================================================================
# 2. MarketStructureAnalyzer
# ============================================================================

class MarketStructureAnalyzer:
    """Detect Structure Shifts — trend continuations and reversals.

    The analyser tracks whether the market is making higher-highs /
    higher-lows (uptrend) or lower-highs / lower-lows (downtrend) and
    flags transitions between the two states.

    * **Continuation Break (BOS)** -- price breaks the most recent swing
      extreme in the direction of the established trend.
    * **Reversal Break (CHoCH)** -- price breaks a swing extreme *against*
      the established trend, signalling a predictive shift.
    """

    @staticmethod
    def _determine_trend(
        swing_highs: List[SwingPoint],
        swing_lows: List[SwingPoint],
    ) -> str:
        """Infer the prevailing trend from the most recent swing sequence.

        Returns one of ``"uptrend"``, ``"downtrend"``, or ``"undefined"``.
        """
        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return "undefined"

        hh = swing_highs[-1].price > swing_highs[-2].price
        hl = swing_lows[-1].price > swing_lows[-2].price
        lh = swing_highs[-1].price < swing_highs[-2].price
        ll = swing_lows[-1].price < swing_lows[-2].price

        if hh and hl:
            return "uptrend"
        if lh and ll:
            return "downtrend"
        return "undefined"

    def detect_bos(
        self,
        swings: List[SwingPoint],
        closes: np.ndarray,
    ) -> List[StructureBreak]:
        """Detect Continuation Breaks (trend-confirming structure shifts).

        A **bullish continuation** occurs when, in an established uptrend,
        the close breaks above the most recent swing high — confirming
        trend persistence.

        A **bearish continuation** occurs when, in an established downtrend,
        the close breaks below the most recent swing low.

        Parameters
        ----------
        swings : list[SwingPoint]
            Swing points (must be sorted by index).
        closes : np.ndarray
            Close prices aligned with the same bar indexing.

        Returns
        -------
        list[StructureBreak]
        """
        closes = np.asarray(closes, dtype=np.float64)
        results: List[StructureBreak] = []

        swing_highs = [s for s in swings if s.swing_type == SwingType.HIGH]
        swing_lows = [s for s in swings if s.swing_type == SwingType.LOW]

        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return results

        trend = self._determine_trend(swing_highs, swing_lows)

        if trend == "uptrend":
            # Bullish BOS: close breaks above the most recent swing high
            target_level = swing_highs[-1].price
            search_start = swing_highs[-1].index + 1
            for idx in range(search_start, len(closes)):
                if closes[idx] > target_level:
                    # Confidence is higher when the break is decisive
                    break_margin = (closes[idx] - target_level) / (target_level + 1e-10)
                    confidence = min(1.0, 0.5 + break_margin * 10)
                    results.append(StructureBreak(
                        break_type="BOS",
                        direction="bullish",
                        price_level=float(closes[idx]),
                        timestamp=datetime.utcnow(),
                        confidence=round(confidence, 4),
                        swing_high=target_level,
                        swing_low=swing_lows[-1].price if swing_lows else None,
                        confirmed=True,
                    ))
                    break

        elif trend == "downtrend":
            # Bearish BOS: close breaks below the most recent swing low
            target_level = swing_lows[-1].price
            search_start = swing_lows[-1].index + 1
            for idx in range(search_start, len(closes)):
                if closes[idx] < target_level:
                    break_margin = (target_level - closes[idx]) / (target_level + 1e-10)
                    confidence = min(1.0, 0.5 + break_margin * 10)
                    results.append(StructureBreak(
                        break_type="BOS",
                        direction="bearish",
                        price_level=float(closes[idx]),
                        timestamp=datetime.utcnow(),
                        confidence=round(confidence, 4),
                        swing_high=swing_highs[-1].price if swing_highs else None,
                        swing_low=target_level,
                        confirmed=True,
                    ))
                    break

        return results

    def detect_choch(
        self,
        swings: List[SwingPoint],
        closes: np.ndarray,
    ) -> List[StructureBreak]:
        """Detect Reversal Breaks (predictive structure shifts).

        A **bullish reversal** occurs in a downtrend (lower-lows,
        lower-highs) when price breaks above the most recent swing high
        — signalling a predictive shift to the upside.

        A **bearish reversal** occurs in an uptrend (higher-highs,
        higher-lows) when price breaks below the most recent swing low
        — signalling a predictive shift to the downside.

        Parameters
        ----------
        swings : list[SwingPoint]
            Swing points sorted by index.
        closes : np.ndarray
            Close prices.

        Returns
        -------
        list[StructureBreak]
        """
        closes = np.asarray(closes, dtype=np.float64)
        results: List[StructureBreak] = []

        swing_highs = [s for s in swings if s.swing_type == SwingType.HIGH]
        swing_lows = [s for s in swings if s.swing_type == SwingType.LOW]

        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return results

        trend = self._determine_trend(swing_highs, swing_lows)

        if trend == "downtrend":
            # Bullish CHoCH: in a downtrend, close breaks above the last swing high
            target_level = swing_highs[-1].price
            search_start = swing_highs[-1].index + 1
            for idx in range(search_start, len(closes)):
                if closes[idx] > target_level:
                    break_margin = (closes[idx] - target_level) / (target_level + 1e-10)
                    confidence = min(1.0, 0.6 + break_margin * 8)
                    results.append(StructureBreak(
                        break_type="CHoCH",
                        direction="bullish",
                        price_level=float(closes[idx]),
                        timestamp=datetime.utcnow(),
                        confidence=round(confidence, 4),
                        swing_high=target_level,
                        swing_low=swing_lows[-1].price if swing_lows else None,
                        confirmed=True,
                    ))
                    break

        elif trend == "uptrend":
            # Bearish CHoCH: in an uptrend, close breaks below the last swing low
            target_level = swing_lows[-1].price
            search_start = swing_lows[-1].index + 1
            for idx in range(search_start, len(closes)):
                if closes[idx] < target_level:
                    break_margin = (target_level - closes[idx]) / (target_level + 1e-10)
                    confidence = min(1.0, 0.6 + break_margin * 8)
                    results.append(StructureBreak(
                        break_type="CHoCH",
                        direction="bearish",
                        price_level=float(closes[idx]),
                        timestamp=datetime.utcnow(),
                        confidence=round(confidence, 4),
                        swing_high=swing_highs[-1].price if swing_highs else None,
                        swing_low=target_level,
                        confirmed=True,
                    ))
                    break

        return results


# ============================================================================
# 3. FVGDetector
# ============================================================================

class FVGDetector:
    """Detect Price Imbalance Zones (PIZ) in price action.

    A **bullish imbalance** forms when ``candle[i-1].high < candle[i+1].low``,
    leaving a gap that price has not efficiently traded through.

    A **bearish imbalance** forms when ``candle[i-1].low > candle[i+1].high``.

    Parameters
    ----------
    min_gap_pct : float
        Minimum gap size as a percentage of the midpoint price.
        Gaps smaller than this are ignored to filter noise.
    """

    def __init__(self, min_gap_pct: float = _FVG_MIN_SIZE_PCT):
        self.min_gap_pct = min_gap_pct

    def detect_fvg(
        self,
        opens: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
    ) -> List[FairValueGap]:
        """Scan for Price Imbalance Zones across the bar series.

        Parameters
        ----------
        opens, highs, lows, closes : np.ndarray
            OHLC arrays of equal length.

        Returns
        -------
        list[FairValueGap]
            Detected FVGs with fill-status tracking.
        """
        opens = np.asarray(opens, dtype=np.float64)
        highs = np.asarray(highs, dtype=np.float64)
        lows = np.asarray(lows, dtype=np.float64)
        closes = np.asarray(closes, dtype=np.float64)

        n = len(highs)
        if n < 3:
            return []

        gaps: List[FairValueGap] = []

        for i in range(1, n - 1):
            prev_high = highs[i - 1]
            next_low = lows[i + 1]
            prev_low = lows[i - 1]
            next_high = highs[i + 1]

            # --- Bullish FVG ---
            if prev_high < next_low:
                upper = float(next_low)
                lower = float(prev_high)
                midpoint = (upper + lower) / 2.0
                size_pct = (upper - lower) / (midpoint + 1e-10)

                if size_pct < self.min_gap_pct:
                    continue

                # Check fill status from bars after the gap
                filled, fill_pct = self._check_fill(
                    lows[i + 1:], upper, lower, gap_type="bullish"
                )

                gaps.append(FairValueGap(
                    gap_type="bullish",
                    upper_bound=upper,
                    lower_bound=lower,
                    midpoint=round(midpoint, 6),
                    size_pct=round(size_pct * 100, 4),
                    timestamp=datetime.utcnow(),
                    filled=filled,
                    fill_percentage=round(fill_pct, 2),
                ))

            # --- Bearish FVG ---
            if prev_low > next_high:
                upper = float(prev_low)
                lower = float(next_high)
                midpoint = (upper + lower) / 2.0
                size_pct = (upper - lower) / (midpoint + 1e-10)

                if size_pct < self.min_gap_pct:
                    continue

                filled, fill_pct = self._check_fill(
                    highs[i + 1:], upper, lower, gap_type="bearish"
                )

                gaps.append(FairValueGap(
                    gap_type="bearish",
                    upper_bound=upper,
                    lower_bound=lower,
                    midpoint=round(midpoint, 6),
                    size_pct=round(size_pct * 100, 4),
                    timestamp=datetime.utcnow(),
                    filled=filled,
                    fill_percentage=round(fill_pct, 2),
                ))

        return gaps

    @staticmethod
    def _check_fill(
        prices_after: np.ndarray,
        upper: float,
        lower: float,
        gap_type: str,
    ) -> Tuple[bool, float]:
        """Determine how much of a gap has been filled.

        For a **bullish** FVG the gap sits *below* price, so price must
        retrace *down* into the gap to fill it -- we check subsequent lows.

        For a **bearish** FVG the gap sits *above* price, so price must
        rally *up* into the gap to fill it -- we check subsequent highs.

        Returns
        -------
        (fully_filled, fill_percentage)
        """
        gap_size = upper - lower
        if gap_size <= 0 or len(prices_after) == 0:
            return False, 0.0

        if gap_type == "bullish":
            # Price must come down into gap. The deepest low penetration
            # into the gap tells us fill depth.
            min_price = float(np.min(prices_after))
            if min_price >= upper:
                return False, 0.0
            penetration = upper - max(min_price, lower)
            fill_pct = (penetration / gap_size) * 100.0
            return fill_pct >= 100.0, min(fill_pct, 100.0)
        else:
            # Bearish gap: price must rally up into the gap.
            max_price = float(np.max(prices_after))
            if max_price <= lower:
                return False, 0.0
            penetration = min(max_price, upper) - lower
            fill_pct = (penetration / gap_size) * 100.0
            return fill_pct >= 100.0, min(fill_pct, 100.0)


# ============================================================================
# 4. OrderBlockDetector
# ============================================================================

class OrderBlockDetector:
    """Detect Demand/Supply Accumulation Zones (DSAZ).

    A **bullish accumulation zone** is the last bearish candle before a
    significant bullish impulse move (> ``impulse_atr_mult`` x ATR).

    A **bearish distribution zone** is the last bullish candle before a
    significant bearish impulse move.

    Parameters
    ----------
    impulse_atr_mult : float
        Minimum impulse size as a multiple of the ATR.
    atr_period : int
        Lookback period for the ATR calculation.
    """

    def __init__(
        self,
        impulse_atr_mult: float = _OB_IMPULSE_ATR_MULTIPLE,
        atr_period: int = 14,
    ):
        self.impulse_atr_mult = impulse_atr_mult
        self.atr_period = atr_period

    def detect_order_blocks(
        self,
        opens: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        volumes: np.ndarray,
    ) -> List[OrderBlock]:
        """Scan for order blocks across the price series.

        Parameters
        ----------
        opens, highs, lows, closes : np.ndarray
            OHLC arrays of equal length.
        volumes : np.ndarray
            Volume array of equal length.

        Returns
        -------
        list[OrderBlock]
        """
        opens = np.asarray(opens, dtype=np.float64)
        highs = np.asarray(highs, dtype=np.float64)
        lows = np.asarray(lows, dtype=np.float64)
        closes = np.asarray(closes, dtype=np.float64)
        volumes = np.asarray(volumes, dtype=np.float64)

        n = len(opens)
        if n < self.atr_period + 2:
            return []

        # Compute ATR using vectorised True Range
        tr = self._compute_true_range(highs, lows, closes)
        atr = self._rolling_mean(tr, self.atr_period)

        # Average volume for relative-volume scoring
        avg_volume = self._rolling_mean(volumes, self.atr_period)

        is_bullish_candle = closes > opens
        is_bearish_candle = closes < opens

        order_blocks: List[OrderBlock] = []

        # We need at least atr_period bars before we start, plus room for
        # the impulse candle after the candidate.
        start = self.atr_period
        for i in range(start, n - 1):
            current_atr = atr[i]
            if current_atr <= 0:
                continue

            impulse_size = abs(closes[i + 1] - opens[i + 1])

            # --- Bullish OB: bearish candle *i* followed by bullish impulse ---
            if is_bearish_candle[i] and is_bullish_candle[i + 1]:
                if impulse_size >= current_atr * self.impulse_atr_mult:
                    strength = self._score_order_block(
                        impulse_size, current_atr,
                        volumes[i], avg_volume[i],
                        closes, i, direction="bullish",
                    )
                    vol_confirm = bool(
                        avg_volume[i] > 0 and volumes[i] > avg_volume[i] * 1.2
                    )
                    tested, mitigated = self._check_ob_status(
                        lows[i + 2:] if i + 2 < n else np.array([]),
                        float(lows[i]), float(highs[i]),
                        direction="bullish",
                    )
                    order_blocks.append(OrderBlock(
                        block_type="bullish",
                        upper_bound=float(highs[i]),
                        lower_bound=float(lows[i]),
                        timestamp=datetime.utcnow(),
                        strength=round(strength, 4),
                        tested=tested,
                        mitigated=mitigated,
                        volume_confirmation=vol_confirm,
                    ))

            # --- Bearish OB: bullish candle *i* followed by bearish impulse ---
            if is_bullish_candle[i] and is_bearish_candle[i + 1]:
                if impulse_size >= current_atr * self.impulse_atr_mult:
                    strength = self._score_order_block(
                        impulse_size, current_atr,
                        volumes[i], avg_volume[i],
                        closes, i, direction="bearish",
                    )
                    vol_confirm = bool(
                        avg_volume[i] > 0 and volumes[i] > avg_volume[i] * 1.2
                    )
                    tested, mitigated = self._check_ob_status(
                        highs[i + 2:] if i + 2 < n else np.array([]),
                        float(lows[i]), float(highs[i]),
                        direction="bearish",
                    )
                    order_blocks.append(OrderBlock(
                        block_type="bearish",
                        upper_bound=float(highs[i]),
                        lower_bound=float(lows[i]),
                        timestamp=datetime.utcnow(),
                        strength=round(strength, 4),
                        tested=tested,
                        mitigated=mitigated,
                        volume_confirmation=vol_confirm,
                    ))

        return order_blocks

    # -- helper methods --

    @staticmethod
    def _compute_true_range(
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
    ) -> np.ndarray:
        """Vectorised True Range computation."""
        prev_close = np.roll(closes, 1)
        prev_close[0] = closes[0]
        tr = np.maximum(
            highs - lows,
            np.maximum(
                np.abs(highs - prev_close),
                np.abs(lows - prev_close),
            ),
        )
        return tr

    @staticmethod
    def _rolling_mean(arr: np.ndarray, window: int) -> np.ndarray:
        """Simple rolling mean; first ``window-1`` values use expanding mean."""
        out = np.empty_like(arr, dtype=np.float64)
        cumsum = np.cumsum(arr)
        out[:window] = cumsum[:window] / np.arange(1, window + 1)
        out[window:] = (cumsum[window:] - cumsum[:-window]) / window
        return out

    @staticmethod
    def _score_order_block(
        impulse_size: float,
        atr: float,
        ob_volume: float,
        avg_volume: float,
        closes: np.ndarray,
        ob_index: int,
        direction: str,
    ) -> float:
        """Score an order block on [0, 1] based on multiple factors.

        Factors
        -------
        1. Impulse strength (how many ATRs the move covers).
        2. Relative volume at the OB candle.
        3. Subsequent confirmation (did price continue in the impulse
           direction over the next few bars?).
        """
        score = 0.0

        # 1. Impulse strength (0 - 0.4)
        atr_ratio = impulse_size / (atr + 1e-10)
        score += min(0.4, (atr_ratio - _OB_IMPULSE_ATR_MULTIPLE) * 0.1 + 0.2)

        # 2. Relative volume (0 - 0.3)
        if avg_volume > 0:
            rvol = ob_volume / avg_volume
            score += min(0.3, max(0.0, (rvol - 1.0) * 0.15))

        # 3. Subsequent confirmation (0 - 0.3)
        confirm_window = min(5, len(closes) - ob_index - 2)
        if confirm_window > 0:
            subsequent = closes[ob_index + 2: ob_index + 2 + confirm_window]
            if len(subsequent) > 0:
                if direction == "bullish":
                    # Price should stay above OB or move higher
                    pct_above = np.mean(subsequent > closes[ob_index + 1])
                    score += float(pct_above) * 0.3
                else:
                    pct_below = np.mean(subsequent < closes[ob_index + 1])
                    score += float(pct_below) * 0.3

        return min(1.0, max(0.0, score))

    @staticmethod
    def _check_ob_status(
        prices_after: np.ndarray,
        ob_low: float,
        ob_high: float,
        direction: str,
    ) -> Tuple[bool, bool]:
        """Check whether an order block has been tested or mitigated.

        * **Tested**: price has returned to the OB zone.
        * **Mitigated**: price has traded *through* the entire OB zone.
        """
        if len(prices_after) == 0:
            return False, False

        if direction == "bullish":
            # For a bullish OB price needs to retrace down to it
            min_after = float(np.min(prices_after))
            tested = min_after <= ob_high
            mitigated = min_after < ob_low
        else:
            max_after = float(np.max(prices_after))
            tested = max_after >= ob_low
            mitigated = max_after > ob_high

        return tested, mitigated


# ============================================================================
# 5. LiquiditySweepDetector
# ============================================================================

class LiquiditySweepDetector:
    """Detect liquidity traps — predictive reversal zones.

    A **buy-side trap** occurs when price pokes above a prior swing high
    or pool of equal highs and then reverses back below within a few bars.

    A **sell-side trap** occurs when price pokes below a prior swing low
    or pool of equal lows and then reverses back above.

    Parameters
    ----------
    equal_level_tolerance : float
        Relative tolerance for grouping equal highs / equal lows.
    reversal_bars : int
        Number of subsequent bars to examine for reversal confirmation.
    """

    def __init__(
        self,
        equal_level_tolerance: float = _EQUAL_LEVEL_TOLERANCE,
        reversal_bars: int = _SWEEP_REVERSAL_BARS,
    ):
        self.equal_level_tolerance = equal_level_tolerance
        self.reversal_bars = reversal_bars

    def detect_sweeps(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        swing_highs: List[SwingPoint],
        swing_lows: List[SwingPoint],
    ) -> List[LiquiditySweep]:
        """Scan for liquidity sweeps.

        Parameters
        ----------
        highs, lows, closes : np.ndarray
            OHLC close/high/low arrays.
        swing_highs : list[SwingPoint]
            Previously detected swing highs.
        swing_lows : list[SwingPoint]
            Previously detected swing lows.

        Returns
        -------
        list[LiquiditySweep]
        """
        highs = np.asarray(highs, dtype=np.float64)
        lows = np.asarray(lows, dtype=np.float64)
        closes = np.asarray(closes, dtype=np.float64)
        n = len(highs)

        if n < 3:
            return []

        sweeps: List[LiquiditySweep] = []

        # Build liquidity pools from equal highs / equal lows
        eq_high_pools = self._find_equal_levels(
            [s.price for s in swing_highs]
        )
        eq_low_pools = self._find_equal_levels(
            [s.price for s in swing_lows]
        )

        # Combine individual swing levels with equal-level pools
        buy_side_levels = set(s.price for s in swing_highs) | set(eq_high_pools)
        sell_side_levels = set(s.price for s in swing_lows) | set(eq_low_pools)

        # Compute average volume for volume-spike detection
        avg_vol: Optional[np.ndarray] = None
        # Volume is not directly passed here; use close range as proxy
        # We flag volume spike based on candle range as heuristic
        candle_ranges = highs - lows
        avg_range = self._safe_rolling_mean(candle_ranges, 20)

        # --- Buy-side sweep ---
        for level in buy_side_levels:
            for i in range(1, n):
                if highs[i] > level and closes[i - 1] <= level:
                    # Price poked above the level
                    sweep_depth = float(highs[i] - level)
                    if sweep_depth / (level + 1e-10) < _SWEEP_MIN_DEPTH_PCT:
                        continue

                    # Check for reversal: close back below the level within
                    # reversal_bars bars
                    reversal_end = min(i + self.reversal_bars + 1, n)
                    reversed_bars = closes[i:reversal_end]
                    if len(reversed_bars) > 0 and np.any(reversed_bars < level):
                        # Measure recovery speed: how quickly did it reverse?
                        bars_to_reverse = int(np.argmax(reversed_bars < level)) + 1
                        recovery_speed = 1.0 / (bars_to_reverse + 1e-10)

                        vol_spike = bool(
                            avg_range[i] > 0 and candle_ranges[i] > avg_range[i] * 1.5
                        )

                        sweeps.append(LiquiditySweep(
                            sweep_type="buy_side",
                            level_swept=float(level),
                            sweep_depth=round(sweep_depth, 6),
                            recovery_speed=round(recovery_speed, 4),
                            timestamp=datetime.utcnow(),
                            volume_spike=vol_spike,
                        ))
                        break  # One sweep per level

        # --- Sell-side sweep ---
        for level in sell_side_levels:
            for i in range(1, n):
                if lows[i] < level and closes[i - 1] >= level:
                    sweep_depth = float(level - lows[i])
                    if sweep_depth / (level + 1e-10) < _SWEEP_MIN_DEPTH_PCT:
                        continue

                    reversal_end = min(i + self.reversal_bars + 1, n)
                    reversed_bars = closes[i:reversal_end]
                    if len(reversed_bars) > 0 and np.any(reversed_bars > level):
                        bars_to_reverse = int(np.argmax(reversed_bars > level)) + 1
                        recovery_speed = 1.0 / (bars_to_reverse + 1e-10)

                        vol_spike = bool(
                            avg_range[i] > 0 and candle_ranges[i] > avg_range[i] * 1.5
                        )

                        sweeps.append(LiquiditySweep(
                            sweep_type="sell_side",
                            level_swept=float(level),
                            sweep_depth=round(sweep_depth, 6),
                            recovery_speed=round(recovery_speed, 4),
                            timestamp=datetime.utcnow(),
                            volume_spike=vol_spike,
                        ))
                        break

        return sweeps

    def _find_equal_levels(self, prices: List[float]) -> List[float]:
        """Group prices within ``equal_level_tolerance`` and return midpoints.

        Equal highs / equal lows act as liquidity pools where resting
        stop-loss orders accumulate.
        """
        if len(prices) < 2:
            return []

        sorted_prices = sorted(prices)
        pools: List[float] = []
        cluster: List[float] = [sorted_prices[0]]

        for price in sorted_prices[1:]:
            ref = cluster[0]
            if ref == 0:
                cluster = [price]
                continue
            if abs(price - ref) / ref <= self.equal_level_tolerance:
                cluster.append(price)
            else:
                if len(cluster) >= 2:
                    pools.append(float(np.mean(cluster)))
                cluster = [price]

        # Final cluster
        if len(cluster) >= 2:
            pools.append(float(np.mean(cluster)))

        return pools

    @staticmethod
    def _safe_rolling_mean(arr: np.ndarray, window: int) -> np.ndarray:
        """Rolling mean that handles short arrays gracefully."""
        n = len(arr)
        if n == 0:
            return arr.copy()
        out = np.empty(n, dtype=np.float64)
        cumsum = np.cumsum(arr)
        effective_window = min(window, n)
        out[:effective_window] = cumsum[:effective_window] / np.arange(1, effective_window + 1)
        if n > window:
            out[window:] = (cumsum[window:] - cumsum[:-window]) / window
        return out


# ============================================================================
# 6. PremiumDiscountAnalyzer
# ============================================================================

class PremiumDiscountAnalyzer:
    """Classify current price within a dealing range.

    Given a swing high and swing low that define the dealing range:

    * **Premium zone**: price is above the 50% (equilibrium) level.
      Distribution pressure increases here.
    * **Discount zone**: price is below the 50% level.
      Accumulation pressure increases here.
    * **Equilibrium**: price is within a small tolerance band of 50%.

    Parameters
    ----------
    equilibrium_band : float
        Half-width of the equilibrium band as a fraction of the range
        (default 0.05 = +/- 5% of the range around the midpoint).
    """

    def __init__(self, equilibrium_band: float = 0.05):
        if equilibrium_band < 0 or equilibrium_band > 0.5:
            raise ValueError("equilibrium_band must be in [0, 0.5]")
        self.equilibrium_band = equilibrium_band

    def classify(
        self,
        current_price: float,
        swing_high: float,
        swing_low: float,
    ) -> str:
        """Classify the current price within the dealing range.

        Parameters
        ----------
        current_price : float
            The price to classify.
        swing_high : float
            Upper bound of the dealing range.
        swing_low : float
            Lower bound of the dealing range.

        Returns
        -------
        str
            One of ``"premium"``, ``"discount"``, or ``"equilibrium"``.
        """
        range_size = swing_high - swing_low
        if range_size <= 0:
            return "equilibrium"

        midpoint = swing_low + range_size * 0.5
        band = range_size * self.equilibrium_band

        if current_price > midpoint + band:
            return "premium"
        elif current_price < midpoint - band:
            return "discount"
        else:
            return "equilibrium"

    def get_position_pct(
        self,
        current_price: float,
        swing_high: float,
        swing_low: float,
    ) -> float:
        """Return the position as a percentage of the range.

        0% = at swing low, 100% = at swing high.
        Values outside [0, 100] indicate price is beyond the range.
        """
        range_size = swing_high - swing_low
        if range_size <= 0:
            return 50.0
        return ((current_price - swing_low) / range_size) * 100.0


# ============================================================================
# 7. MarketStructureScanner
# ============================================================================

class MarketStructureScanner(BaseScanner[AdvancedScanResult]):
    """Revolution Alpha — Predictive Structure Intelligence Scanner.

    We see the move BEFORE the move. For each symbol this scanner:

    1. Detects swing highs and swing lows.
    2. Identifies Continuation Breaks and Reversal Breaks.
    3. Maps Price Imbalance Zones (PIZ).
    4. Detects Demand/Supply Accumulation Zones (DSAZ) with volume confirmation.
    5. Identifies Liquidity Traps — predictive reversal zones.
    6. Classifies the current price as premium or discount.
    7. Generates an :class:`AdvancedScanResult` when actionable structure
       is found.

    Signal Logic
    -------------
    * **Reversal Break + PIZ in discount** -- strong BULLISH signal.
    * **Reversal Break + PIZ in premium** -- strong BEARISH signal.
    * **Continuation Break + DSAZ retest** -- continuation signal.
    """

    def __init__(
        self,
        config: Optional[ScannerConfig] = None,
        swing_lookback: int = 5,
    ):
        super().__init__(
            name="market_structure",
            scan_mode=ScanMode.ALL,
            config=config,
        )
        self.swing_lookback = swing_lookback

        # Sub-components
        self._swing_detector = SwingDetector(lookback=swing_lookback)
        self._structure_analyzer = MarketStructureAnalyzer()
        self._fvg_detector = FVGDetector()
        self._ob_detector = OrderBlockDetector()
        self._sweep_detector = LiquiditySweepDetector()
        self._pd_analyzer = PremiumDiscountAnalyzer()

    # ------------------------------------------------------------------ scan

    async def scan(self, context: ScanContext) -> List[AdvancedScanResult]:
        """Execute the market-structure scan for all symbols in the universe.

        Parameters
        ----------
        context : ScanContext
            Contains universe, market data, and historical data.

        Returns
        -------
        list[AdvancedScanResult]
        """
        results: List[AdvancedScanResult] = []

        for symbol in context.universe:
            try:
                result = self._scan_symbol(symbol, context)
                if result is not None:
                    results.append(result)
            except Exception as exc:
                self._logger.warning(
                    "Error scanning %s for market structure: %s",
                    symbol, exc, exc_info=True,
                )

        return results

    # ------------------------------------------------- per-symbol processing

    def _scan_symbol(
        self,
        symbol: str,
        context: ScanContext,
    ) -> Optional[AdvancedScanResult]:
        """Run the full predictive structure analysis pipeline for a single symbol."""
        market_data = context.market_data.get(symbol)
        hist_data = context.historical_data.get(symbol)

        if not market_data or not hist_data:
            return None

        if not self.apply_filters(market_data):
            return None

        if len(hist_data.bars) < _MIN_BARS_FOR_STRUCTURE:
            self._logger.debug(
                "%s: insufficient bars (%d < %d)",
                symbol, len(hist_data.bars), _MIN_BARS_FOR_STRUCTURE,
            )
            return None

        # Convert to numpy arrays
        opens = np.array([b.open for b in hist_data.bars], dtype=np.float64)
        highs = np.array([b.high for b in hist_data.bars], dtype=np.float64)
        lows = np.array([b.low for b in hist_data.bars], dtype=np.float64)
        closes = np.array([b.close for b in hist_data.bars], dtype=np.float64)
        volumes = np.array([b.volume for b in hist_data.bars], dtype=np.float64)

        # Guard against flat / zero-variance data
        if np.ptp(closes) == 0:
            return None

        # (a) Detect swings
        swings = self._swing_detector.detect_swings(
            highs, lows, closes, lookback=self.swing_lookback,
        )
        if len(swings) < 4:
            return None

        swing_highs = [s for s in swings if s.swing_type == SwingType.HIGH]
        swing_lows = [s for s in swings if s.swing_type == SwingType.LOW]

        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return None

        # (b) Detect BOS / CHoCH
        bos_list = self._structure_analyzer.detect_bos(swings, closes)
        choch_list = self._structure_analyzer.detect_choch(swings, closes)
        structure_breaks = bos_list + choch_list

        # (c) Detect FVGs
        fvgs = self._fvg_detector.detect_fvg(opens, highs, lows, closes)

        # (d) Detect order blocks
        obs = self._ob_detector.detect_order_blocks(opens, highs, lows, closes, volumes)

        # (e) Detect liquidity sweeps
        sweeps = self._sweep_detector.detect_sweeps(
            highs, lows, closes, swing_highs, swing_lows,
        )

        # (f) Premium / Discount classification
        dealing_high = float(np.max([s.price for s in swing_highs[-3:]]))
        dealing_low = float(np.min([s.price for s in swing_lows[-3:]]))
        current_price = float(closes[-1])
        pd_zone = self._pd_analyzer.classify(current_price, dealing_high, dealing_low)

        # Build context bundle
        struct_ctx = StructureContext(
            swings=swings,
            structure_breaks=structure_breaks,
            fair_value_gaps=fvgs,
            order_blocks=obs,
            liquidity_sweeps=sweeps,
            premium_discount=pd_zone,
            dealing_range_high=dealing_high,
            dealing_range_low=dealing_low,
        )

        # (g) Determine if there is an actionable signal
        return self._evaluate_signal(symbol, market_data, struct_ctx, closes)

    # --------------------------------------------------- signal evaluation

    def _evaluate_signal(
        self,
        symbol: str,
        market_data: MarketData,
        ctx: StructureContext,
        closes: np.ndarray,
    ) -> Optional[AdvancedScanResult]:
        """Evaluate the composite structure and decide on a signal.

        Precedence:
        1. CHoCH + unfilled FVG in discount -> strong BULLISH
        2. CHoCH + unfilled FVG in premium  -> strong BEARISH
        3. BOS + order-block retest          -> continuation
        4. No actionable structure           -> None
        """
        current_price = float(closes[-1])
        supporting: List[str] = []
        contradicting: List[str] = []

        choch_breaks = [b for b in ctx.structure_breaks if b.break_type == "CHoCH"]
        bos_breaks = [b for b in ctx.structure_breaks if b.break_type == "BOS"]
        unfilled_fvgs = [g for g in ctx.fair_value_gaps if not g.filled]
        tested_obs = [o for o in ctx.order_blocks if o.tested and not o.mitigated]

        direction: Optional[str] = None
        confidence = 0.0
        signal_type = ""

        # ------- Signal 1: CHoCH + FVG in discount -> BULLISH -------
        bullish_choch = [b for b in choch_breaks if b.direction == "bullish"]
        bullish_fvg_discount = [
            g for g in unfilled_fvgs
            if g.gap_type == "bullish" and ctx.premium_discount == "discount"
        ]
        if bullish_choch and bullish_fvg_discount:
            direction = "BULLISH"
            confidence = self._compute_confidence(
                base=0.70,
                choch=bullish_choch[0],
                fvg=bullish_fvg_discount[0],
                obs=tested_obs,
                sweeps=ctx.liquidity_sweeps,
                pd_zone=ctx.premium_discount,
            )
            signal_type = "CHoCH_FVG_discount"
            supporting.append("Bullish CHoCH detected")
            supporting.append("Unfilled bullish FVG in discount zone")
            if any(s.sweep_type == "sell_side" for s in ctx.liquidity_sweeps):
                supporting.append("Sell-side liquidity swept before reversal")
                confidence = min(1.0, confidence + 0.05)

        # ------- Signal 2: CHoCH + FVG in premium -> BEARISH --------
        bearish_choch = [b for b in choch_breaks if b.direction == "bearish"]
        bearish_fvg_premium = [
            g for g in unfilled_fvgs
            if g.gap_type == "bearish" and ctx.premium_discount == "premium"
        ]
        if direction is None and bearish_choch and bearish_fvg_premium:
            direction = "BEARISH"
            confidence = self._compute_confidence(
                base=0.70,
                choch=bearish_choch[0],
                fvg=bearish_fvg_premium[0],
                obs=tested_obs,
                sweeps=ctx.liquidity_sweeps,
                pd_zone=ctx.premium_discount,
            )
            signal_type = "CHoCH_FVG_premium"
            supporting.append("Bearish CHoCH detected")
            supporting.append("Unfilled bearish FVG in premium zone")
            if any(s.sweep_type == "buy_side" for s in ctx.liquidity_sweeps):
                supporting.append("Buy-side liquidity swept before reversal")
                confidence = min(1.0, confidence + 0.05)

        # ------- Signal 3: BOS + OB retest -> continuation -----------
        if direction is None and bos_breaks and tested_obs:
            bos = bos_breaks[-1]
            matching_obs = [
                o for o in tested_obs if o.block_type == bos.direction
            ]
            if matching_obs:
                ob = matching_obs[-1]
                direction = "BULLISH" if bos.direction == "bullish" else "BEARISH"
                confidence = self._compute_confidence(
                    base=0.55,
                    choch=None,
                    fvg=None,
                    obs=[ob],
                    sweeps=ctx.liquidity_sweeps,
                    pd_zone=ctx.premium_discount,
                )
                signal_type = "BOS_OB_retest"
                supporting.append(f"{bos.direction.title()} BOS with OB retest")
                if ob.volume_confirmation:
                    supporting.append("Order block has volume confirmation")
                    confidence = min(1.0, confidence + 0.03)

        # No actionable signal
        if direction is None:
            return None

        # --- Build trade parameters ---
        atr_val = market_data.atr
        stop_loss = self._compute_stop_loss(
            current_price, direction, ctx, atr_val,
        )
        target = self._compute_target(
            current_price, stop_loss, direction, ctx,
        )
        rr_ratio = self._safe_risk_reward(current_price, stop_loss, target)

        # Contradicting evidence
        if ctx.premium_discount == "premium" and direction == "BULLISH":
            contradicting.append("Price in premium zone for bullish bias")
            confidence = max(0.0, confidence - 0.05)
        if ctx.premium_discount == "discount" and direction == "BEARISH":
            contradicting.append("Price in discount zone for bearish bias")
            confidence = max(0.0, confidence - 0.05)
        if any(g.filled for g in ctx.fair_value_gaps[-3:] if ctx.fair_value_gaps):
            contradicting.append("Recent FVGs have been filled")

        # Clamp final confidence
        confidence = round(max(0.0, min(1.0, confidence)), 4)

        # Determine regime context
        regime = self._infer_regime(ctx)

        return AdvancedScanResult(
            scan_id=str(uuid.uuid4()),
            scan_name="market_structure",
            category=ScanCategory.PRICE_ACTION,
            symbol=symbol,
            signal_direction=direction,
            signal_strength=round(confidence, 4),
            confidence=round(confidence, 4),
            expected_move_pct=round(abs(target - current_price) / (current_price + 1e-10) * 100, 2),
            expected_timeframe=ExpectedTimeframe.SWING,
            risk_reward_ratio=round(rr_ratio, 2),
            entry_price=round(current_price, 2),
            stop_loss_level=round(stop_loss, 2),
            target_level=round(target, 2),
            secondary_targets=self._secondary_targets(
                current_price, stop_loss, direction,
            ),
            supporting_evidence=supporting,
            contradicting_evidence=contradicting,
            regime_context=regime,
            mathematical_basis=(
                "Revolution Alpha predictive structure analysis: swing "
                "detection via N-bar fractal, continuation/reversal breaks "
                "from trend-state transitions, PIZ from 3-candle imbalance, "
                "DSAZ from impulse-preceded candle with volume confirmation."
            ),
            false_positive_rate=round(1.0 - confidence, 4),
            decay_halflife_days=5,
            metadata={
                "signal_type": signal_type,
                "premium_discount": ctx.premium_discount,
                "dealing_range_high": ctx.dealing_range_high,
                "dealing_range_low": ctx.dealing_range_low,
                "num_swings": len(ctx.swings),
                "num_fvgs": len(ctx.fair_value_gaps),
                "num_unfilled_fvgs": len(unfilled_fvgs),
                "num_order_blocks": len(ctx.order_blocks),
                "num_sweeps": len(ctx.liquidity_sweeps),
                "structure_breaks": [
                    {"type": b.break_type, "direction": b.direction}
                    for b in ctx.structure_breaks
                ],
            },
        )

    # ------------------------------------------------- helper utilities

    @staticmethod
    def _compute_confidence(
        base: float,
        choch: Optional[StructureBreak],
        fvg: Optional[FairValueGap],
        obs: List[OrderBlock],
        sweeps: List[LiquiditySweep],
        pd_zone: str,
    ) -> float:
        """Compute composite confidence from multiple structure factors."""
        conf = base

        if choch is not None:
            conf += choch.confidence * 0.10

        if fvg is not None:
            # Larger gaps carry more weight
            size_bonus = min(0.05, fvg.size_pct * 0.005)
            conf += size_bonus

        # Volume-confirmed OB boost
        for ob in obs:
            if ob.volume_confirmation:
                conf += 0.03
            conf += ob.strength * 0.05

        # Sweep adds confluence
        if sweeps:
            conf += 0.04

        # Premium/discount alignment
        if pd_zone in ("premium", "discount"):
            conf += 0.03

        return min(1.0, conf)

    def _compute_stop_loss(
        self,
        entry: float,
        direction: str,
        ctx: StructureContext,
        atr: Optional[float],
    ) -> float:
        """Determine stop-loss placement based on structure.

        Uses the nearest opposing structure level (swing low for bullish,
        swing high for bearish) with a small buffer. Falls back to
        ATR-based stop if no structure is available.
        """
        buffer_pct = 0.002  # 0.2% buffer past the level

        if direction == "BULLISH":
            # Place stop below the most recent swing low
            recent_lows = [
                s.price for s in ctx.swings
                if s.swing_type == SwingType.LOW
            ]
            if recent_lows:
                structure_stop = min(recent_lows[-2:]) * (1.0 - buffer_pct)
                return round(structure_stop, 2)
        else:
            recent_highs = [
                s.price for s in ctx.swings
                if s.swing_type == SwingType.HIGH
            ]
            if recent_highs:
                structure_stop = max(recent_highs[-2:]) * (1.0 + buffer_pct)
                return round(structure_stop, 2)

        # Fallback: ATR-based
        if atr is not None and atr > 0:
            distance = atr * 2.0
        else:
            distance = entry * 0.02

        if direction == "BULLISH":
            return round(entry - distance, 2)
        return round(entry + distance, 2)

    @staticmethod
    def _compute_target(
        entry: float,
        stop_loss: float,
        direction: str,
        ctx: StructureContext,
    ) -> float:
        """Determine primary target.

        Prefers opposing FVG midpoint or dealing-range boundary.
        Falls back to 2.5:1 risk-reward projection.
        """
        risk = abs(entry - stop_loss)

        if direction == "BULLISH":
            # Target: nearest unfilled bearish FVG above, or dealing range high
            targets_above = [
                g.midpoint for g in ctx.fair_value_gaps
                if g.gap_type == "bearish" and not g.filled and g.midpoint > entry
            ]
            if targets_above:
                return round(min(targets_above), 2)
            if ctx.dealing_range_high > entry:
                return round(ctx.dealing_range_high, 2)
            return round(entry + risk * 2.5, 2)
        else:
            targets_below = [
                g.midpoint for g in ctx.fair_value_gaps
                if g.gap_type == "bullish" and not g.filled and g.midpoint < entry
            ]
            if targets_below:
                return round(max(targets_below), 2)
            if ctx.dealing_range_low < entry:
                return round(ctx.dealing_range_low, 2)
            return round(entry - risk * 2.5, 2)

    @staticmethod
    def _safe_risk_reward(entry: float, stop: float, target: float) -> float:
        """Compute risk-reward, guarding against division by zero."""
        risk = abs(entry - stop)
        reward = abs(target - entry)
        if risk == 0:
            return 0.0
        return reward / risk

    @staticmethod
    def _secondary_targets(
        entry: float,
        stop_loss: float,
        direction: str,
    ) -> List[float]:
        """Generate secondary targets at 1.5R, 2R, and 3R."""
        risk = abs(entry - stop_loss)
        multipliers = [1.5, 2.0, 3.0]
        if direction == "BULLISH":
            return [round(entry + risk * m, 2) for m in multipliers]
        return [round(entry - risk * m, 2) for m in multipliers]

    @staticmethod
    def _infer_regime(ctx: StructureContext) -> RegimeContext:
        """Infer the market regime from detected structure."""
        choch = any(b.break_type == "CHoCH" for b in ctx.structure_breaks)
        bos_bullish = any(
            b.break_type == "BOS" and b.direction == "bullish"
            for b in ctx.structure_breaks
        )
        bos_bearish = any(
            b.break_type == "BOS" and b.direction == "bearish"
            for b in ctx.structure_breaks
        )

        if choch:
            return RegimeContext.TRANSITION
        if bos_bullish:
            return RegimeContext.TRENDING_UP
        if bos_bearish:
            return RegimeContext.TRENDING_DOWN
        return RegimeContext.RANGING

    # ---------------------------------------------- validation interface

    def validate_signal(
        self,
        result: AdvancedScanResult,
        context: ScanContext,
    ) -> bool:
        """Validate a market-structure signal against basic quality gates.

        Parameters
        ----------
        result : AdvancedScanResult
            The signal to validate.
        context : ScanContext
            Current scan context.

        Returns
        -------
        bool
            True if the signal passes validation.
        """
        # Minimum confidence (AdvancedScanResult uses 0-1 scale)
        min_conf = self.config.min_confidence / 100.0
        if result.confidence < min_conf:
            return False

        # Must have a valid entry price
        if result.entry_price is None or result.entry_price <= 0:
            return False

        # Risk-reward must be acceptable
        if result.risk_reward_ratio < 1.0:
            return False

        # Must have supporting evidence
        if len(result.supporting_evidence) == 0:
            return False

        return True
