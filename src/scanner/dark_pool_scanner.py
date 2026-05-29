"""
Revolution Alpha Engine - Dark Pool Scanner

Wraps DarkPoolDetector as a BaseScanner subclass for the scanner engine.
Builds synthetic trade DataFrames from historical bars, runs dark-pool
detection, and converts alerts into AdvancedScanResult format.

Mathematical Basis:
    Volume-impact regression, Lee-Ready trade classification, iceberg
    detection via clip-size clustering, short-volume z-score anomaly.
"""

from __future__ import annotations

import logging
import uuid
from typing import Dict, List, Optional

import pandas as pd

from .base import BaseScanner, ScanContext
from .models import ScanMode, ScannerConfig, SignalDirection, TimeFrame
from .advanced_models import (
    AdvancedScanResult,
    ExpectedTimeframe,
    RegimeContext,
    ScanCategory,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Graceful import of DarkPoolDetector
# ---------------------------------------------------------------------------

_DETECTOR_AVAILABLE: bool = False

try:
    from src.institutional.dark_pool_detector import (
        DarkPoolDetector,
        DarkPoolAlert,
        DarkPoolSignal,
        ActivityLevel,
    )
    _DETECTOR_AVAILABLE = True
except ImportError:
    logger.warning(
        "DarkPoolDetector unavailable; DarkPoolScanner will return empty results."
    )
    DarkPoolDetector = None  # type: ignore[misc,assignment]
    DarkPoolAlert = None  # type: ignore[misc,assignment]
    DarkPoolSignal = None  # type: ignore[misc,assignment]
    ActivityLevel = None  # type: ignore[misc,assignment]

# ---------------------------------------------------------------------------
# Constants & mapping tables
# ---------------------------------------------------------------------------

_MIN_CONFIDENCE_THRESHOLD = 0.3

_SIGNAL_DIRECTION_MAP: Dict[str, str] = {
    "accumulation": "BULLISH",
    "block_buying": "BULLISH",
    "stealth_accumulation": "BULLISH",
    "distribution": "BEARISH",
    "block_selling": "BEARISH",
    "stealth_distribution": "BEARISH",
    "iceberg_order": "NEUTRAL",
    "institutional_pivot": "NEUTRAL",
}

_ACTIVITY_LEVEL_STRENGTH: Dict[str, float] = {
    "extreme": 1.0, "high": 0.80, "moderate": 0.55,
    "low": 0.35, "minimal": 0.15,
}

_EXPECTED_TIMEFRAME_MAP: Dict[str, ExpectedTimeframe] = {
    "Hours": ExpectedTimeframe.INTRADAY,
    "Hours to days": ExpectedTimeframe.SWING,
    "1-5 days": ExpectedTimeframe.SWING,
    "Days": ExpectedTimeframe.SWING,
    "Days to weeks": ExpectedTimeframe.POSITION,
}

_REGIME_MAP: Dict[str, RegimeContext] = {
    "trending_up": RegimeContext.TRENDING_UP,
    "trending_down": RegimeContext.TRENDING_DOWN,
    "ranging": RegimeContext.RANGING,
    "high_volatility": RegimeContext.VOLATILE,
    "low_volatility": RegimeContext.QUIET,
    "breakout": RegimeContext.TRANSITION,
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def dark_pool_signal_to_direction(signal: "DarkPoolSignal") -> str:
    """Convert a DarkPoolSignal enum to ``"BULLISH"``/``"BEARISH"``/``"NEUTRAL"``.

    ACCUMULATION / BLOCK_BUYING / STEALTH_ACCUMULATION -> BULLISH
    DISTRIBUTION / BLOCK_SELLING / STEALTH_DISTRIBUTION -> BEARISH
    ICEBERG_ORDER / INSTITUTIONAL_PIVOT -> NEUTRAL (resolved via estimated_direction)
    """
    if signal is None:
        return "NEUTRAL"
    return _SIGNAL_DIRECTION_MAP.get(signal.value, "NEUTRAL")


def _resolve_direction(alert: "DarkPoolAlert") -> str:
    """Determine signal direction, falling back to estimated_direction for
    ambiguous signal types."""
    direction = dark_pool_signal_to_direction(alert.signal_type)
    if direction == "NEUTRAL" and alert.estimated_direction:
        est = alert.estimated_direction.lower()
        if est == "buy":
            return "BULLISH"
        if est == "sell":
            return "BEARISH"
    return direction


def _activity_level_to_strength(level: "ActivityLevel") -> float:
    if level is None:
        return 0.5
    return _ACTIVITY_LEVEL_STRENGTH.get(level.value, 0.5)


def _map_expected_timeframe(raw: str) -> ExpectedTimeframe:
    return _EXPECTED_TIMEFRAME_MAP.get(raw, ExpectedTimeframe.SWING)


def _infer_regime(context: ScanContext) -> RegimeContext:
    return _REGIME_MAP.get(context.market_regime.value, RegimeContext.RANGING)


# ============================================================================
# DarkPoolScanner
# ============================================================================


class DarkPoolScanner(BaseScanner[AdvancedScanResult]):
    """BaseScanner wrapper around :class:`DarkPoolDetector`.

    Iterates the scan universe, builds synthetic trade/daily DataFrames from
    historical bars, runs detection, and emits AdvancedScanResult objects.
    """

    def __init__(
        self,
        config: Optional[ScannerConfig] = None,
        detector_config: Optional[Dict] = None,
    ):
        super().__init__(
            name="dark_pool_scanner",
            scan_mode=ScanMode.ALL,
            config=config,
        )
        self._detector_config = detector_config
        self.detector: Optional["DarkPoolDetector"] = None

    # ----------------------------------------------------------------- scan

    async def scan(self, context: ScanContext) -> List[AdvancedScanResult]:
        if not _DETECTOR_AVAILABLE:
            self._logger.error("DarkPoolDetector unavailable; returning empty.")
            return []

        results: List[AdvancedScanResult] = []
        for symbol in context.universe:
            try:
                results.extend(self._scan_symbol(symbol, context))
            except Exception:
                self._logger.exception("Error scanning %s", symbol)

        self._logger.info(
            "Dark pool scan complete: %d signals from %d symbols",
            len(results), len(context.universe),
        )
        return results

    # -------------------------------------------------------- per-symbol

    def _scan_symbol(
        self, symbol: str, context: ScanContext,
    ) -> List[AdvancedScanResult]:
        market_data = context.market_data.get(symbol)
        historical = context.historical_data.get(symbol)

        if market_data is None:
            self._logger.debug("No market data for %s — skipping", symbol)
            return []

        current_price = market_data.close
        trades_df = self._build_trades_df(market_data, historical)
        daily_df = self._build_daily_df(historical)

        # Fresh detector per symbol to avoid state bleed
        self.detector = DarkPoolDetector(config=self._detector_config)
        alerts: List["DarkPoolAlert"] = self.detector.analyze(
            symbol=symbol,
            current_price=current_price,
            trades=trades_df,
            daily_data=daily_df,
        )

        if not alerts:
            return []

        regime = _infer_regime(context)
        results: List[AdvancedScanResult] = []
        for alert in alerts:
            result = self._alert_to_result(alert, symbol, current_price, regime)
            if result is not None:
                results.append(result)
        return results

    # ----------------------------------------------------- DataFrame helpers

    @staticmethod
    def _build_trades_df(market_data, historical) -> pd.DataFrame:
        """Build synthetic trades DataFrame from historical + current bars."""
        records: List[Dict] = []

        if historical is not None and historical.bars:
            for bar in historical.bars:
                records.append({
                    "timestamp": bar.timestamp,
                    "price": bar.close,
                    "size": bar.volume,
                    "side": "buy" if bar.close >= bar.open else "sell",
                    "condition": "",
                    "exchange": "",
                })

        if market_data is not None:
            records.append({
                "timestamp": market_data.timestamp,
                "price": market_data.close,
                "size": market_data.volume,
                "side": "buy" if market_data.close >= market_data.open else "sell",
                "condition": "",
                "exchange": "",
            })

        cols = ["timestamp", "price", "size", "side", "condition", "exchange"]
        return pd.DataFrame(records, columns=cols) if records else pd.DataFrame(columns=cols)

    @staticmethod
    def _build_daily_df(historical) -> Optional[pd.DataFrame]:
        """Build daily OHLCV DataFrame from historical bars."""
        if historical is None or not historical.bars:
            return None
        return pd.DataFrame([
            {"open": b.open, "high": b.high, "low": b.low,
             "close": b.close, "volume": b.volume}
            for b in historical.bars
        ])

    # ----------------------------------------------------- alert conversion

    def _alert_to_result(
        self, alert: "DarkPoolAlert", symbol: str,
        current_price: float, regime: RegimeContext,
    ) -> Optional[AdvancedScanResult]:
        """Convert a DarkPoolAlert to an AdvancedScanResult."""
        # Normalise confidence to 0-1
        conf = alert.confidence / 100.0 if alert.confidence > 1.0 else alert.confidence

        if conf < _MIN_CONFIDENCE_THRESHOLD:
            self._logger.debug("Low confidence alert dropped for %s (%.2f)", symbol, conf)
            return None

        direction = _resolve_direction(alert)
        strength = _activity_level_to_strength(alert.activity_level)
        expected_tf = _map_expected_timeframe(alert.expected_timeframe)

        # Trade levels
        if direction == "BULLISH":
            stop_loss = round(current_price * 0.97, 2)
            target = round(current_price * 1.05, 2)
        elif direction == "BEARISH":
            stop_loss = round(current_price * 1.03, 2)
            target = round(current_price * 0.95, 2)
        else:
            stop_loss = round(current_price * 0.97, 2)
            target = round(current_price * 1.03, 2)

        risk = abs(current_price - stop_loss)
        reward = abs(target - current_price)
        rr = round(reward / risk, 2) if risk > 0 else 0.0
        move_pct = round(reward / (current_price + 1e-10) * 100, 2)

        # Evidence
        supporting = list(alert.evidence) if alert.evidence else []
        if alert.detection_method:
            supporting.insert(0, f"Detection: {alert.detection_method}")
        if alert.estimated_dark_volume > 0:
            supporting.append(f"Estimated dark volume: {alert.estimated_dark_volume:,}")
        if alert.estimated_size_millions > 0:
            supporting.append(f"Estimated size: ${alert.estimated_size_millions:.1f}M")

        contradicting: List[str] = []
        if direction == "NEUTRAL":
            contradicting.append("Ambiguous signal direction")
        if 0 < alert.relative_volume < 0.5:
            contradicting.append(f"Very low relative volume ({alert.relative_volume:.2f}x)")

        return AdvancedScanResult(
            scan_id=str(uuid.uuid4()),
            scan_name="dark_pool_scanner",
            category=ScanCategory.INSTITUTIONAL,
            symbol=symbol,
            signal_direction=direction,
            signal_strength=round(strength, 4),
            confidence=round(conf, 4),
            expected_move_pct=move_pct,
            expected_timeframe=expected_tf,
            risk_reward_ratio=rr,
            entry_price=round(current_price, 2),
            stop_loss_level=stop_loss,
            target_level=target,
            secondary_targets=[],
            supporting_evidence=supporting,
            contradicting_evidence=contradicting,
            regime_context=regime,
            mathematical_basis=(
                "Dark-pool inference via volume-impact regression, Lee-Ready "
                "trade classification, iceberg clip-size clustering, and "
                "short-volume z-score anomaly detection."
            ),
            false_positive_rate=round(1.0 - conf, 4),
            decay_halflife_days=7,
            metadata={
                "signal_type": alert.signal_type.value,
                "activity_level": alert.activity_level.value,
                "detection_method": alert.detection_method,
                "estimated_direction": alert.estimated_direction,
                "estimated_dark_volume": alert.estimated_dark_volume,
                "estimated_size_millions": alert.estimated_size_millions,
                "price_change_pct": alert.price_change_pct,
                "relative_volume": alert.relative_volume,
                "expected_price_impact": alert.expected_price_impact,
            },
        )

    # ------------------------------------------------ validation interface

    def validate_signal(
        self, result: AdvancedScanResult, context: ScanContext,
    ) -> bool:
        """Validate a dark-pool signal.

        Checks confidence > 0.3, valid entry price, supporting evidence,
        and directional alignment with estimated_direction metadata.
        """
        if result.confidence < _MIN_CONFIDENCE_THRESHOLD:
            self._logger.debug("Validation: low confidence for %s", result.symbol)
            return False

        if result.entry_price is None or result.entry_price <= 0:
            self._logger.debug("Validation: bad entry price for %s", result.symbol)
            return False

        if not result.supporting_evidence:
            self._logger.debug("Validation: no evidence for %s", result.symbol)
            return False

        # Direction alignment: estimated_direction must not contradict signal
        est = result.metadata.get("estimated_direction", "")
        if est and result.signal_direction != "NEUTRAL":
            est_lower = est.lower()
            if est_lower == "buy" and result.signal_direction == "BEARISH":
                self._logger.debug("Validation: buy vs BEARISH for %s", result.symbol)
                return False
            if est_lower == "sell" and result.signal_direction == "BULLISH":
                self._logger.debug("Validation: sell vs BULLISH for %s", result.symbol)
                return False

        return True
