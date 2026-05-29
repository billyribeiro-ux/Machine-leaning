"""
Revolution Alpha Engine - Cross-Asset Intelligence Scanner

BaseScanner wrapper around the institutional CrossAssetIntelligence engine.
Detects inter-market signals via correlation breakdowns, lead-lag relationships,
and risk-on/risk-off regime shifts across equities, bonds, commodities,
currencies, and volatility indices.

Author: Revolution Alpha Engine
"""

from datetime import datetime
from typing import Optional, Dict, List, Any
import logging
import uuid

import numpy as np
import pandas as pd

from .base import BaseScanner, ScanContext
from .models import ScanResult, ScanMode, SignalDirection, ScannerConfig, TimeFrame
from .advanced_models import (
    AdvancedScanResult, ScanCategory, RegimeContext, ExpectedTimeframe,
)

logger = logging.getLogger(__name__)

try:
    from src.institutional.cross_asset_intelligence import CrossAssetIntelligence
except ImportError:
    try:
        from institutional.cross_asset_intelligence import CrossAssetIntelligence
    except ImportError:
        CrossAssetIntelligence = None  # type: ignore[assignment,misc]
        logger.warning(
            "CrossAssetIntelligence not available -- "
            "cross_asset_scanner will produce no signals"
        )

# Key asset pairs for correlation-breakdown scanning
_KEY_PAIRS: List[Dict[str, str]] = [
    {"a": "SPY", "b": "TLT", "label": "stock_bond", "desc": "Stock-bond correlation"},
    {"a": "SPY", "b": "VIX", "label": "equity_vol", "desc": "Equity-volatility"},
    {"a": "GLD", "b": "UUP", "label": "gold_dollar", "desc": "Gold-dollar inverse"},
    {"a": "HYG", "b": "TLT", "label": "credit_spread", "desc": "Credit-spread proxy"},
    {"a": "EEM", "b": "SPY", "label": "em_developed", "desc": "EM vs developed equity"},
    {"a": "USO", "b": "UUP", "label": "oil_dollar", "desc": "Oil-dollar inverse"},
    {"a": "TLT", "b": "TIP", "label": "inflation_exp", "desc": "Inflation expectations"},
    {"a": "XLY", "b": "XLP", "label": "cyclical_defensive", "desc": "Cyclical vs defensive"},
]

_MIN_BARS = 60  # Minimum daily bars for meaningful analysis

_REGIME_MAP = {
    "trending_up": RegimeContext.TRENDING_UP,
    "trending_down": RegimeContext.TRENDING_DOWN,
    "ranging": RegimeContext.RANGING,
    "high_volatility": RegimeContext.VOLATILE,
    "low_volatility": RegimeContext.QUIET,
    "breakout": RegimeContext.TRANSITION,
}


class CrossAssetScanner(BaseScanner[AdvancedScanResult]):
    """Wraps CrossAssetIntelligence as a BaseScanner subclass.

    Builds DataFrames from context.historical_data, feeds them to the engine,
    and emits AdvancedScanResult for correlation breakdowns, regime shifts,
    and lead-lag signals.
    """

    _CATEGORY = ScanCategory.MACRO_REGIME
    _ZSCORE_THRESHOLD = 2.0
    _MIN_CONFIDENCE = 0.40

    def __init__(self, config: Optional[ScannerConfig] = None):
        super().__init__(name="cross_asset_scanner", scan_mode=ScanMode.ALL, config=config)
        self._cross_asset: Optional[Any] = None
        if CrossAssetIntelligence is not None:
            self._cross_asset = CrossAssetIntelligence()
        else:
            self._logger.warning("CrossAssetIntelligence unavailable; scanner disabled")

    # ---- BaseScanner interface ------------------------------------------------

    async def scan(self, context: ScanContext) -> List[AdvancedScanResult]:
        """Run cross-asset analysis and return detected signals."""
        results: List[AdvancedScanResult] = []
        if self._cross_asset is None:
            return results

        asset_frames = self._build_dataframes(context)
        if len(asset_frames) < 2:
            self._logger.debug("Fewer than 2 assets (%d) -- skipping", len(asset_frames))
            return results

        try:
            self._cross_asset.load_data(asset_frames)
            relationships = self._cross_asset.analyze_all_relationships()
            macro_state = self._cross_asset.calculate_macro_regime()
        except Exception:
            self._logger.exception("Engine analysis failed")
            return results

        results.extend(self._detect_correlation_breakdowns(relationships, context))
        results.extend(self._detect_regime_shifts(macro_state, relationships, context))
        results.extend(self._detect_lead_lag_signals(relationships, context))

        self._logger.info(
            "Cross-asset scan: %d signals from %d relationships",
            len(results), len(relationships),
        )
        return results

    def validate_signal(self, result: AdvancedScanResult, context: ScanContext) -> bool:
        """Check z-score persistence and minimum confidence."""
        if result.confidence < self._MIN_CONFIDENCE:
            return False
        zscore = result.metadata.get("zscore")
        if zscore is not None and abs(zscore) < self._ZSCORE_THRESHOLD:
            return False
        return True

    # ---- Data preparation -----------------------------------------------------

    def _build_dataframes(self, context: ScanContext) -> Dict[str, pd.DataFrame]:
        """Convert context.historical_data to DataFrames with a 'close' column."""
        frames: Dict[str, pd.DataFrame] = {}
        for symbol, hist in context.historical_data.items():
            if not hist.bars or len(hist.bars) < _MIN_BARS:
                continue
            closes = [bar.close for bar in hist.bars]
            timestamps = [bar.timestamp for bar in hist.bars]
            frames[symbol] = pd.DataFrame({"close": closes}, index=timestamps)
        return frames

    # ---- Signal detection -----------------------------------------------------

    def _detect_correlation_breakdowns(
        self, relationships: Dict[str, Any], context: ScanContext,
    ) -> List[AdvancedScanResult]:
        """Emit signals for pairs whose correlation z-score exceeds threshold."""
        results: List[AdvancedScanResult] = []
        for pair_def in _KEY_PAIRS:
            label = pair_def["label"]
            if label not in relationships:
                continue
            pair = relationships[label]
            zscore = pair.correlation_zscore
            if abs(zscore) < self._ZSCORE_THRESHOLD:
                continue

            asset_a, asset_b = pair_def["a"], pair_def["b"]
            direction = "BEARISH" if zscore < -self._ZSCORE_THRESHOLD else "BULLISH"
            confidence = min(0.95, 0.50 + 0.10 * (abs(zscore) - 2.0))
            strength = min(1.0, abs(zscore) / 5.0)

            supporting = [
                f"{pair_def['desc']} z-score at {zscore:+.2f}",
                f"Current correlation: {pair.correlation:.3f}",
            ]
            if pair.is_cointegrated:
                supporting.append(f"Spread z-score: {pair.spread_zscore:.2f} (cointegrated)")
                confidence = min(0.95, confidence + 0.05)

            results.append(self._make_result(
                scan_name=f"correlation_breakdown_{label}",
                symbol=f"{asset_a}_{asset_b}_CORRELATION",
                direction=direction, strength=strength, confidence=confidence,
                expected_move_pct=round(float(np.clip(zscore * -1.5, -8.0, 8.0)), 1),
                timeframe=ExpectedTimeframe.SWING, supporting=supporting,
                contradicting=[],
                math_basis=f"Rolling corr z-score = (rho_short - mu_long)/sigma_long = {zscore:.2f}",
                metadata={
                    "zscore": zscore, "correlation": pair.correlation,
                    "pair_label": label, "asset_a": asset_a, "asset_b": asset_b,
                    "is_cointegrated": pair.is_cointegrated,
                    "spread_zscore": pair.spread_zscore,
                },
                context=context,
            ))
        return results

    def _detect_regime_shifts(
        self, macro_state: Any, relationships: Dict[str, Any], context: ScanContext,
    ) -> List[AdvancedScanResult]:
        """Emit a signal when a clear risk-on or risk-off regime is detected."""
        if macro_state is None or abs(macro_state.risk_appetite) < 20:
            return []

        risk_appetite = macro_state.risk_appetite
        regime_name = macro_state.regime.value
        is_risk_on = risk_appetite > 0
        direction = "BULLISH" if is_risk_on else "BEARISH"

        # Gather confirming pairs
        confirming: List[str] = []
        for pd_ in _KEY_PAIRS:
            if pd_["label"] in relationships:
                pair = relationships[pd_["label"]]
                if abs(pair.correlation_zscore) > 1.5:
                    confirming.append(f"{pd_['desc']}: z={pair.correlation_zscore:+.2f}")

        base_conf = min(0.90, 0.50 + abs(risk_appetite) / 200.0)
        confidence = min(0.95, base_conf + min(0.10, len(confirming) * 0.02))
        strength = min(1.0, abs(risk_appetite) / 80.0)

        supporting = [
            f"Macro regime: {regime_name}",
            f"Risk appetite: {risk_appetite:+.1f}",
            f"VIX regime: {macro_state.vix_regime}",
        ] + confirming

        contradicting: List[str] = []
        if macro_state.confidence < 0.5:
            contradicting.append(f"Low regime confidence ({macro_state.confidence:.2f})")

        return [self._make_result(
            scan_name=f"regime_shift_{regime_name}",
            symbol="RISK_ON_OFF_REGIME", direction=direction,
            strength=strength, confidence=confidence,
            expected_move_pct=3.0 if is_risk_on else -3.0,
            timeframe=ExpectedTimeframe.POSITION,
            supporting=supporting, contradicting=contradicting,
            math_basis=(
                "Composite risk-appetite: equity/bond, credit, "
                "cyclical/defensive, small/large, EM/DM, VIX"
            ),
            metadata={
                "risk_appetite": risk_appetite, "regime": regime_name,
                "vix_regime": macro_state.vix_regime,
                "macro_confidence": macro_state.confidence,
                "confirming_pairs": len(confirming),
            },
            context=context,
        )]

    def _detect_lead_lag_signals(
        self, relationships: Dict[str, Any], context: ScanContext,
    ) -> List[AdvancedScanResult]:
        """Emit signals when a clear lead-lag relationship is detected."""
        results: List[AdvancedScanResult] = []
        for pair_def in _KEY_PAIRS:
            label = pair_def["label"]
            if label not in relationships:
                continue
            pair = relationships[label]

            if pair.lead_lag_days == 0 or abs(pair.lead_lag_days) > 5:
                continue
            causality = pair.causality_direction
            if causality in ("no_causality", "bidirectional"):
                continue

            asset_a, asset_b = pair_def["a"], pair_def["b"]
            if causality == f"{asset_a}_leads":
                leader, follower = asset_a, asset_b
            else:
                leader, follower = asset_b, asset_a

            leader_ret = self._recent_return(leader, context)
            if leader_ret is None:
                continue

            direction = "BULLISH" if leader_ret > 0 else "BEARISH"
            confidence = min(0.80, 0.50 + pair.relationship_strength * 0.30)

            results.append(self._make_result(
                scan_name=f"lead_lag_{label}",
                symbol=f"{leader}_LEADS_{follower}",
                direction=direction,
                strength=min(1.0, pair.relationship_strength),
                confidence=confidence,
                expected_move_pct=1.5 if direction == "BULLISH" else -1.5,
                timeframe=ExpectedTimeframe.SWING,
                supporting=[
                    f"{leader} leads {follower} by {abs(pair.lead_lag_days)} day(s)",
                    f"Granger causality: {causality}",
                    f"Relationship strength: {pair.relationship_strength:.2f}",
                ],
                contradicting=[],
                math_basis=(
                    f"Cross-corr lag={pair.lead_lag_days}d; "
                    f"Granger F-test confirms {causality}"
                ),
                metadata={
                    "leader": leader, "follower": follower,
                    "lag_days": pair.lead_lag_days, "causality": causality,
                    "relationship_strength": pair.relationship_strength,
                    "pair_label": label,
                },
                context=context,
            ))
        return results

    # ---- Helpers --------------------------------------------------------------

    def _recent_return(
        self, symbol: str, context: ScanContext, lookback: int = 5,
    ) -> Optional[float]:
        """Average return over the last *lookback* bars for *symbol*."""
        hist = context.historical_data.get(symbol)
        if hist is None or len(hist.bars) < lookback + 1:
            return None
        closes = [bar.close for bar in hist.bars[-(lookback + 1):]]
        returns = np.diff(closes) / np.array(closes[:-1])
        return float(np.mean(returns))

    def _make_result(
        self, *, scan_name: str, symbol: str, direction: str,
        strength: float, confidence: float, expected_move_pct: float,
        timeframe: ExpectedTimeframe, supporting: List[str],
        contradicting: List[str], math_basis: str,
        metadata: Dict[str, Any], context: ScanContext,
    ) -> AdvancedScanResult:
        """Build an AdvancedScanResult with sensible defaults."""
        regime = _REGIME_MAP.get(context.market_regime.value, RegimeContext.RANGING)
        return AdvancedScanResult(
            scan_id=str(uuid.uuid4()),
            scan_name=scan_name,
            category=self._CATEGORY,
            timestamp=context.timestamp,
            symbol=symbol,
            signal_direction=direction,
            signal_strength=strength,
            confidence=confidence,
            expected_move_pct=expected_move_pct,
            expected_timeframe=timeframe,
            risk_reward_ratio=0.0,
            supporting_evidence=supporting,
            contradicting_evidence=contradicting,
            regime_context=regime,
            mathematical_basis=math_basis,
            historical_accuracy=0.0,
            false_positive_rate=0.0,
            decay_halflife_days=7,
            metadata=metadata,
        )
