"""
Revolution Alpha Engine - Liquidity Shock Scanner

Institutional-grade scanner for detecting sudden liquidity changes and
shock events that precede large price moves. Monitors five distinct
liquidity anomalies:

1. Spread Shock       - Bid-ask spread widens beyond 2 sigma of its
                        rolling 20-bar average.
2. Volume Drought     - Volume collapses below 0.3x the 20-bar average,
                        signaling a potential liquidity vacuum.
3. Liquidity Vacuum   - Combined spread widening + volume drop + price
                        acceleration. The most dangerous condition.
4. Volume Spike       - Extremely high volume bar with small price change
   Absorption           indicating hidden resting liquidity.
5. Relative Volume    - Volume exceeding 3x the 20-bar average with
   Anomaly              directional bias from informed flow.

All calculations use only numpy (no external dependencies beyond the
standard scientific stack shipped with the engine).

Signals:
    NEUTRAL  - Spread shock / volume drought (warnings)
    BULLISH  - Absorption on buy side or upward relative volume anomaly
    BEARISH  - Absorption on sell side, downward relative volume anomaly,
               or liquidity vacuum with downward acceleration
"""

from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass, field
import logging
import uuid

import numpy as np

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
    TimeFrame,
)
from .advanced_models import (
    AdvancedScanResult,
    ScanCategory,
    RegimeContext,
    ExpectedTimeframe,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_LOOKBACK = 20          # Rolling window for averages / standard deviations
_MIN_BARS = 21          # Minimum bars required (lookback + 1 for current)
_SPREAD_ZSCORE_THRESHOLD = 2.0
_VOLUME_DROUGHT_RATIO = 0.3
_VOLUME_SPIKE_RATIO = 3.0
_ABSORPTION_BODY_PCT_MAX = 25.0   # Max candle body % of range for absorption
_ABSORPTION_VOLUME_RATIO = 3.0    # Min relative volume for absorption
_VACUUM_SPREAD_ZSCORE = 1.5       # Lower spread threshold when combined
_VACUUM_VOLUME_RATIO = 0.5        # Volume ratio threshold for vacuum
_VACUUM_ACCEL_THRESHOLD = 1.5     # Price acceleration threshold (sigma)


# ---------------------------------------------------------------------------
# Internal analysis container
# ---------------------------------------------------------------------------

@dataclass
class LiquidityAnalysis:
    """Intermediate container holding per-symbol liquidity analysis."""
    symbol: str

    # Spread metrics
    current_spread: float = 0.0
    avg_spread: float = 0.0
    spread_std: float = 0.0
    spread_zscore: float = 0.0
    has_spread_data: bool = False

    # Volume metrics
    current_volume: int = 0
    avg_volume: float = 0.0
    volume_ratio: float = 0.0

    # Price metrics
    current_close: float = 0.0
    price_change_pct: float = 0.0
    price_accel_zscore: float = 0.0
    bar_range: float = 0.0
    bar_body: float = 0.0
    body_pct_of_range: float = 0.0
    is_bullish_bar: bool = False

    # Recent extremes (for stops)
    recent_high: float = 0.0
    recent_low: float = 0.0
    avg_range: float = 0.0

    # Detected conditions
    spread_shock: bool = False
    volume_drought: bool = False
    liquidity_vacuum: bool = False
    volume_absorption: bool = False
    relative_volume_anomaly: bool = False

    # Evidence tracking
    supporting_evidence: list[str] = field(default_factory=list)
    contradicting_evidence: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Scanner implementation
# ---------------------------------------------------------------------------

class LiquidityShockScanner(BaseScanner[AdvancedScanResult]):
    """
    Detects sudden liquidity changes and shock events across the universe.

    Emits AdvancedScanResult with category EXECUTION for every symbol where
    at least one of the five liquidity anomalies is detected.
    """

    def __init__(self, config: Optional[ScannerConfig] = None) -> None:
        super().__init__(
            name="liquidity_shock_scanner",
            scan_mode=ScanMode.ALL,
            config=config,
        )

    # ------------------------------------------------------------------
    # Core scan loop
    # ------------------------------------------------------------------

    async def scan(self, context: ScanContext) -> list[AdvancedScanResult]:
        """
        Iterate over every symbol in the universe and run the full
        liquidity analysis pipeline.

        Args:
            context: Scan context with market data and historical bars.

        Returns:
            List of AdvancedScanResult for symbols with detected events.
        """
        results: list[AdvancedScanResult] = []

        for symbol in context.universe:
            try:
                result = self._scan_symbol(symbol, context)
                if result is not None:
                    results.append(result)
            except Exception as exc:
                self._logger.warning(
                    "Error scanning %s for liquidity shocks: %s", symbol, exc
                )

        return results

    # ------------------------------------------------------------------
    # Per-symbol pipeline
    # ------------------------------------------------------------------

    def _scan_symbol(
        self, symbol: str, context: ScanContext
    ) -> Optional[AdvancedScanResult]:
        """Run full liquidity analysis on a single symbol."""
        market_data = context.market_data.get(symbol)
        hist_data = context.historical_data.get(symbol)

        if market_data is None or hist_data is None:
            return None

        if not self.apply_filters(market_data):
            return None

        if len(hist_data.bars) < _MIN_BARS:
            return None

        analysis = self._compute_metrics(symbol, market_data, hist_data)
        self._detect_spread_shock(analysis)
        self._detect_volume_drought(analysis)
        self._detect_liquidity_vacuum(analysis)
        self._detect_volume_absorption(analysis)
        self._detect_relative_volume_anomaly(analysis)

        # Only emit a result when at least one condition is detected
        has_signal = (
            analysis.spread_shock
            or analysis.volume_drought
            or analysis.liquidity_vacuum
            or analysis.volume_absorption
            or analysis.relative_volume_anomaly
        )
        if not has_signal:
            return None

        return self._build_result(analysis, market_data, context)

    # ------------------------------------------------------------------
    # Metric computation
    # ------------------------------------------------------------------

    def _compute_metrics(
        self,
        symbol: str,
        market_data: MarketData,
        hist_data: HistoricalData,
    ) -> LiquidityAnalysis:
        """Extract all raw metrics required by the five detectors."""
        analysis = LiquidityAnalysis(symbol=symbol)

        bars = hist_data.bars
        lookback_bars = bars[-_LOOKBACK:]
        current_bar = bars[-1]

        # ----- Spread -----
        spreads: list[float] = []
        for bar in lookback_bars:
            if bar.bid is not None and bar.ask is not None and bar.bid > 0:
                spreads.append(bar.ask - bar.bid)

        if spreads and market_data.spread is not None:
            analysis.has_spread_data = True
            analysis.current_spread = market_data.spread
            spread_arr = np.array(spreads, dtype=np.float64)
            analysis.avg_spread = float(np.mean(spread_arr))
            analysis.spread_std = float(np.std(spread_arr, ddof=1)) if len(spread_arr) > 1 else 0.0
            if analysis.spread_std > 0:
                analysis.spread_zscore = (
                    (analysis.current_spread - analysis.avg_spread) / analysis.spread_std
                )

        # ----- Volume -----
        volumes = np.array([b.volume for b in lookback_bars], dtype=np.float64)
        analysis.current_volume = market_data.volume
        analysis.avg_volume = float(np.mean(volumes)) if len(volumes) > 0 else 0.0
        if analysis.avg_volume > 0:
            analysis.volume_ratio = market_data.volume / analysis.avg_volume

        # ----- Price dynamics -----
        analysis.current_close = market_data.close
        closes = np.array([b.close for b in lookback_bars], dtype=np.float64)

        if len(closes) >= 2:
            pct_changes = np.diff(closes) / closes[:-1] * 100.0
            analysis.price_change_pct = float(
                (market_data.close - closes[-1]) / closes[-1] * 100.0
            ) if closes[-1] > 0 else 0.0

            pct_std = float(np.std(pct_changes, ddof=1)) if len(pct_changes) > 1 else 0.0
            if pct_std > 0:
                analysis.price_accel_zscore = analysis.price_change_pct / pct_std

        # Bar geometry
        analysis.bar_range = market_data.high - market_data.low
        analysis.bar_body = abs(market_data.close - market_data.open)
        if analysis.bar_range > 0:
            analysis.body_pct_of_range = (analysis.bar_body / analysis.bar_range) * 100.0
        analysis.is_bullish_bar = market_data.close > market_data.open

        # Recent extremes (for stop placement)
        highs = np.array([b.high for b in lookback_bars], dtype=np.float64)
        lows = np.array([b.low for b in lookback_bars], dtype=np.float64)
        analysis.recent_high = float(np.max(highs))
        analysis.recent_low = float(np.min(lows))

        ranges = highs - lows
        analysis.avg_range = float(np.mean(ranges)) if len(ranges) > 0 else 0.0

        return analysis

    # ------------------------------------------------------------------
    # Detector 1: Spread Shock
    # ------------------------------------------------------------------

    def _detect_spread_shock(self, a: LiquidityAnalysis) -> None:
        """
        Detect a sudden widening of bid-ask spread beyond 2 sigma of
        the rolling 20-bar average.
        """
        if not a.has_spread_data:
            return
        if a.spread_zscore > _SPREAD_ZSCORE_THRESHOLD:
            a.spread_shock = True
            a.supporting_evidence.append(
                f"Spread shock: z-score={a.spread_zscore:.2f} "
                f"(current={a.current_spread:.4f}, "
                f"avg={a.avg_spread:.4f}, std={a.spread_std:.4f})"
            )

    # ------------------------------------------------------------------
    # Detector 2: Volume Drought
    # ------------------------------------------------------------------

    def _detect_volume_drought(self, a: LiquidityAnalysis) -> None:
        """
        Detect when volume drops below 0.3x the 20-bar average,
        indicating a potential liquidity vacuum before a large move.
        """
        if a.avg_volume <= 0:
            return
        if a.volume_ratio < _VOLUME_DROUGHT_RATIO:
            a.volume_drought = True
            a.supporting_evidence.append(
                f"Volume drought: ratio={a.volume_ratio:.2f}x "
                f"(current={a.current_volume:,}, avg={a.avg_volume:,.0f})"
            )

    # ------------------------------------------------------------------
    # Detector 3: Liquidity Vacuum
    # ------------------------------------------------------------------

    def _detect_liquidity_vacuum(self, a: LiquidityAnalysis) -> None:
        """
        Combined condition: spread widening + volume drop + price
        acceleration. This is the most dangerous liquidity event.
        Generates an alert regardless of direction.
        """
        spread_widening = a.has_spread_data and a.spread_zscore > _VACUUM_SPREAD_ZSCORE
        volume_drop = a.avg_volume > 0 and a.volume_ratio < _VACUUM_VOLUME_RATIO
        price_accel = abs(a.price_accel_zscore) > _VACUUM_ACCEL_THRESHOLD

        conditions_met = sum([spread_widening, volume_drop, price_accel])

        if conditions_met >= 2 and (spread_widening or volume_drop):
            a.liquidity_vacuum = True
            parts: list[str] = []
            if spread_widening:
                parts.append(f"spread z={a.spread_zscore:.2f}")
            if volume_drop:
                parts.append(f"vol ratio={a.volume_ratio:.2f}x")
            if price_accel:
                parts.append(f"price accel z={a.price_accel_zscore:.2f}")
            a.supporting_evidence.append(
                f"Liquidity vacuum ({' + '.join(parts)})"
            )

    # ------------------------------------------------------------------
    # Detector 4: Volume Spike Absorption
    # ------------------------------------------------------------------

    def _detect_volume_absorption(self, a: LiquidityAnalysis) -> None:
        """
        Extremely high volume bar with small price change indicates
        hidden liquidity (large resting orders absorbing flow).

        Directional logic:
            - If absorbed on the buy side (bullish bar) the large seller
              was absorbed -> bullish.
            - If absorbed on the sell side (bearish bar) the large buyer
              was absorbed -> bearish.
        """
        if a.avg_volume <= 0:
            return

        high_volume = a.volume_ratio >= _ABSORPTION_VOLUME_RATIO
        small_body = a.body_pct_of_range <= _ABSORPTION_BODY_PCT_MAX

        if high_volume and small_body:
            a.volume_absorption = True
            direction_word = "buy-side" if a.is_bullish_bar else "sell-side"
            a.supporting_evidence.append(
                f"Volume absorption on {direction_word}: "
                f"vol ratio={a.volume_ratio:.2f}x, "
                f"body={a.body_pct_of_range:.1f}% of range"
            )

    # ------------------------------------------------------------------
    # Detector 5: Relative Volume Anomaly
    # ------------------------------------------------------------------

    def _detect_relative_volume_anomaly(self, a: LiquidityAnalysis) -> None:
        """
        Volume exceeds 3x the 20-bar average with a directional bias.
        Compare price direction to determine if this is informed flow.
        """
        if a.avg_volume <= 0:
            return

        # Need high volume AND a meaningful price change (body > 25% of
        # range) to separate from absorption signals.
        if a.volume_ratio >= _VOLUME_SPIKE_RATIO and a.body_pct_of_range > _ABSORPTION_BODY_PCT_MAX:
            a.relative_volume_anomaly = True
            direction_word = "bullish" if a.is_bullish_bar else "bearish"
            a.supporting_evidence.append(
                f"Relative volume anomaly ({direction_word}): "
                f"vol ratio={a.volume_ratio:.2f}x, "
                f"price change={a.price_change_pct:+.2f}%"
            )

    # ------------------------------------------------------------------
    # Result construction
    # ------------------------------------------------------------------

    def _build_result(
        self,
        analysis: LiquidityAnalysis,
        market_data: MarketData,
        context: ScanContext,
    ) -> AdvancedScanResult:
        """
        Translate the detection flags into a single AdvancedScanResult.

        Priority ordering when multiple conditions fire simultaneously:
            1. Liquidity vacuum   (highest priority - most dangerous)
            2. Volume absorption  (directional, high confidence)
            3. Relative volume    (directional, moderate confidence)
            4. Spread shock       (warning, neutral)
            5. Volume drought     (warning, neutral)
        """
        direction, confidence, strength = self._resolve_signal(analysis)

        # Expected timeframe depends on the event type
        if analysis.liquidity_vacuum:
            expected_tf = ExpectedTimeframe.SCALP
        elif analysis.volume_absorption:
            expected_tf = ExpectedTimeframe.INTRADAY
        else:
            expected_tf = ExpectedTimeframe.INTRADAY

        # Trade levels
        entry_price = market_data.close
        atr_proxy = analysis.avg_range if analysis.avg_range > 0 else entry_price * 0.01

        stop_loss, target = self._compute_trade_levels(
            direction, entry_price, atr_proxy, analysis
        )

        risk = abs(entry_price - stop_loss)
        reward = abs(target - entry_price)
        rr_ratio = reward / risk if risk > 0 else 0.0

        expected_move_pct = (reward / entry_price * 100.0) if entry_price > 0 else 0.0

        # Regime context
        regime_context = self._determine_regime_context(analysis)

        # Mathematical basis
        math_parts: list[str] = []
        if analysis.spread_shock or analysis.liquidity_vacuum:
            math_parts.append(
                f"Spread z-score = (S - mu_S) / sigma_S; "
                f"z={analysis.spread_zscore:.2f}"
            )
        if analysis.volume_drought or analysis.liquidity_vacuum:
            math_parts.append(
                f"Volume ratio = V / EMA_20(V); "
                f"ratio={analysis.volume_ratio:.2f}"
            )
        if analysis.volume_absorption:
            math_parts.append(
                f"Absorption: |body|/range={analysis.body_pct_of_range:.1f}% "
                f"with RVOL={analysis.volume_ratio:.1f}x"
            )
        if analysis.relative_volume_anomaly:
            math_parts.append(
                f"RVOL anomaly: {analysis.volume_ratio:.1f}x 20-bar avg "
                f"with directional price change"
            )
        if analysis.liquidity_vacuum:
            math_parts.append(
                f"Price acceleration z={analysis.price_accel_zscore:.2f}"
            )
        mathematical_basis = "; ".join(math_parts)

        # Contradicting evidence
        contra = list(analysis.contradicting_evidence)
        if analysis.spread_shock and analysis.volume_ratio > 2.0:
            contra.append(
                "High volume accompanies spread shock (may be transient)"
            )
        if analysis.volume_drought and analysis.has_spread_data and analysis.spread_zscore < 0.5:
            contra.append(
                "Spread remains tight despite volume drought"
            )

        # Scan name reflects the primary condition
        scan_label = self._primary_condition_label(analysis)

        # Metadata
        metadata = self._build_metadata(analysis)

        # Signal direction string for AdvancedScanResult
        adv_direction = {
            SignalDirection.LONG: "BULLISH",
            SignalDirection.SHORT: "BEARISH",
            SignalDirection.NEUTRAL: "NEUTRAL",
        }[direction]

        return AdvancedScanResult(
            scan_id=str(uuid.uuid4()),
            scan_name=f"Liquidity Shock: {scan_label}",
            category=ScanCategory.EXECUTION,
            symbol=analysis.symbol,
            signal_direction=adv_direction,
            signal_strength=round(strength, 4),
            confidence=round(confidence, 4),
            expected_move_pct=round(expected_move_pct, 2),
            expected_timeframe=expected_tf,
            risk_reward_ratio=round(rr_ratio, 2),
            entry_price=round(entry_price, 2),
            stop_loss_level=round(stop_loss, 2),
            target_level=round(target, 2),
            supporting_evidence=analysis.supporting_evidence,
            contradicting_evidence=contra,
            regime_context=regime_context,
            mathematical_basis=mathematical_basis,
            false_positive_rate=round(max(0.0, 0.35 - confidence * 0.20), 4),
            decay_halflife_days=1 if analysis.liquidity_vacuum else 2,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Signal resolution helpers
    # ------------------------------------------------------------------

    def _resolve_signal(
        self, a: LiquidityAnalysis
    ) -> tuple[SignalDirection, float, float]:
        """
        Determine direction, confidence (0-1), and strength (0-1) from
        the combination of detected conditions.

        Returns:
            (direction, confidence, strength)
        """
        # Start from a neutral baseline
        direction = SignalDirection.NEUTRAL
        confidence = 0.0
        strength = 0.0

        # Liquidity vacuum is highest priority
        if a.liquidity_vacuum:
            # Direction follows price acceleration
            if a.price_accel_zscore > 0:
                direction = SignalDirection.LONG
            elif a.price_accel_zscore < 0:
                direction = SignalDirection.SHORT
            else:
                direction = SignalDirection.NEUTRAL
            confidence = min(1.0, 0.80 + abs(a.price_accel_zscore) * 0.05)
            strength = min(1.0, 0.75 + abs(a.price_accel_zscore) * 0.05)
            return direction, confidence, strength

        # Volume absorption
        if a.volume_absorption:
            direction = SignalDirection.LONG if a.is_bullish_bar else SignalDirection.SHORT
            # Scale confidence with volume ratio
            confidence = min(1.0, 0.55 + (a.volume_ratio - _ABSORPTION_VOLUME_RATIO) * 0.05)
            strength = min(1.0, 0.50 + (a.volume_ratio - _ABSORPTION_VOLUME_RATIO) * 0.05)
            # Boost if spread is also widening (more conviction)
            if a.spread_shock:
                confidence = min(1.0, confidence + 0.10)
                strength = min(1.0, strength + 0.10)
            return direction, confidence, strength

        # Relative volume anomaly
        if a.relative_volume_anomaly:
            direction = SignalDirection.LONG if a.is_bullish_bar else SignalDirection.SHORT
            # Confidence scales with volume magnitude
            magnitude_bonus = min(0.20, (a.volume_ratio - _VOLUME_SPIKE_RATIO) * 0.04)
            confidence = 0.50 + magnitude_bonus
            strength = 0.45 + magnitude_bonus
            return direction, confidence, strength

        # Spread shock (warning, neutral)
        if a.spread_shock:
            direction = SignalDirection.NEUTRAL
            confidence = min(1.0, 0.45 + (a.spread_zscore - _SPREAD_ZSCORE_THRESHOLD) * 0.08)
            strength = min(1.0, 0.40 + (a.spread_zscore - _SPREAD_ZSCORE_THRESHOLD) * 0.06)
            # Combine with drought for stronger warning
            if a.volume_drought:
                confidence = min(1.0, confidence + 0.10)
                strength = min(1.0, strength + 0.10)
            return direction, confidence, strength

        # Volume drought (warning, neutral)
        if a.volume_drought:
            direction = SignalDirection.NEUTRAL
            # Lower volume ratio -> higher concern
            drought_severity = max(0.0, (_VOLUME_DROUGHT_RATIO - a.volume_ratio))
            confidence = 0.40 + drought_severity * 0.5
            strength = 0.35 + drought_severity * 0.5
            return direction, confidence, strength

        return direction, confidence, strength

    def _compute_trade_levels(
        self,
        direction: SignalDirection,
        entry: float,
        atr_proxy: float,
        analysis: LiquidityAnalysis,
    ) -> tuple[float, float]:
        """
        Compute stop-loss and target levels.

        For directional signals, the stop goes beyond the recent extreme.
        Target is based on the measured average range.

        Returns:
            (stop_loss, target)
        """
        buffer = atr_proxy * 0.25  # small buffer beyond the extreme

        if direction == SignalDirection.LONG:
            stop_loss = max(analysis.recent_low - buffer, entry * 0.95)
            target = entry + atr_proxy * 2.0
        elif direction == SignalDirection.SHORT:
            stop_loss = min(analysis.recent_high + buffer, entry * 1.05)
            target = entry - atr_proxy * 2.0
        else:
            # Neutral warnings: symmetric levels around entry
            stop_loss = entry - atr_proxy * 1.5
            target = entry + atr_proxy * 1.5

        return round(stop_loss, 2), round(target, 2)

    def _primary_condition_label(self, a: LiquidityAnalysis) -> str:
        """Return a human-readable label for the most significant condition."""
        if a.liquidity_vacuum:
            return "Liquidity Vacuum"
        if a.volume_absorption:
            side = "Buy-Side" if a.is_bullish_bar else "Sell-Side"
            return f"Volume Absorption ({side})"
        if a.relative_volume_anomaly:
            return "Relative Volume Anomaly"
        if a.spread_shock:
            return "Spread Shock"
        if a.volume_drought:
            return "Volume Drought"
        return "Unknown"

    def _determine_regime_context(self, a: LiquidityAnalysis) -> RegimeContext:
        """Map the liquidity state to a RegimeContext enum value."""
        if a.liquidity_vacuum:
            return RegimeContext.CRISIS
        if a.volume_absorption:
            return RegimeContext.TRANSITION
        if a.relative_volume_anomaly:
            return RegimeContext.VOLATILE
        if a.spread_shock or a.volume_drought:
            return RegimeContext.QUIET
        return RegimeContext.RANGING

    def _build_metadata(self, a: LiquidityAnalysis) -> dict:
        """Assemble scanner-specific metadata for the result."""
        meta: dict = {
            "spread": {
                "current": round(a.current_spread, 6),
                "avg_20": round(a.avg_spread, 6),
                "std_20": round(a.spread_std, 6),
                "z_score": round(a.spread_zscore, 4),
                "has_data": a.has_spread_data,
            },
            "volume": {
                "current": a.current_volume,
                "avg_20": round(a.avg_volume, 0),
                "ratio": round(a.volume_ratio, 4),
            },
            "price": {
                "close": round(a.current_close, 4),
                "change_pct": round(a.price_change_pct, 4),
                "accel_zscore": round(a.price_accel_zscore, 4),
                "body_pct_of_range": round(a.body_pct_of_range, 2),
                "is_bullish": a.is_bullish_bar,
            },
            "levels": {
                "recent_high": round(a.recent_high, 4),
                "recent_low": round(a.recent_low, 4),
                "avg_range": round(a.avg_range, 4),
            },
            "conditions": {
                "spread_shock": a.spread_shock,
                "volume_drought": a.volume_drought,
                "liquidity_vacuum": a.liquidity_vacuum,
                "volume_absorption": a.volume_absorption,
                "relative_volume_anomaly": a.relative_volume_anomaly,
            },
        }
        return meta

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_signal(
        self, result: AdvancedScanResult, context: ScanContext
    ) -> bool:
        """
        Validate a liquidity shock signal against current conditions.

        Checks:
            - Minimum confidence threshold from config.
            - Spread-based signals require actual bid/ask data.
            - Volume-based signals require non-zero volume data.
            - At least one piece of supporting evidence exists.
        """
        # Confidence gate (config stores 0-100, result uses 0-1)
        if result.confidence < self.config.min_confidence / 100.0:
            return False

        if not result.supporting_evidence:
            return False

        conditions = result.metadata.get("conditions", {})

        # Spread signals require bid/ask data
        spread_related = conditions.get("spread_shock") or conditions.get("liquidity_vacuum")
        if spread_related:
            spread_meta = result.metadata.get("spread", {})
            if not spread_meta.get("has_data", False):
                self._logger.debug(
                    "Rejecting %s spread signal: no bid/ask data", result.symbol
                )
                return False

        # Volume signals require meaningful volume
        volume_related = (
            conditions.get("volume_drought")
            or conditions.get("volume_absorption")
            or conditions.get("relative_volume_anomaly")
        )
        if volume_related:
            vol_meta = result.metadata.get("volume", {})
            if vol_meta.get("current", 0) <= 0 or vol_meta.get("avg_20", 0) <= 0:
                self._logger.debug(
                    "Rejecting %s volume signal: insufficient volume data",
                    result.symbol,
                )
                return False

        return True
