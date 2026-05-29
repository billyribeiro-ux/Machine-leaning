"""
Revolution Alpha Engine - Order Flow Imbalance Scanner

Wraps PredictiveOrderFlow as a BaseScanner subclass. Detects VPIN toxicity
spikes, extreme order imbalance (>2 std), and institutional footprints.

Mathematical Basis:
    VPIN (Easley, Lopez de Prado, O'Hara 2012) measures informed-trading
    probability via volume-synchronised buckets. Order imbalance z-scores
    flag extreme deviations. Trade-size distribution analysis identifies
    institutional participation.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np

from .base import BaseScanner, ScanContext, MarketData, HistoricalData
from .models import ScanResult, ScanMode, SignalDirection, ScannerConfig, TimeFrame
from .advanced_models import (
    AdvancedScanResult, ScanCategory, RegimeContext, ExpectedTimeframe,
)

logger = logging.getLogger(__name__)

# -- Graceful import of PredictiveOrderFlow ------------------------------------
try:
    from src.institutional.predictive_order_flow import PredictiveOrderFlow
    _HAS_POF = True
except ImportError:
    try:
        from institutional.predictive_order_flow import PredictiveOrderFlow
        _HAS_POF = True
    except ImportError:
        PredictiveOrderFlow = None  # type: ignore[assignment,misc]
        _HAS_POF = False
        logger.warning("PredictiveOrderFlow unavailable; OrderFlowImbalanceScanner disabled.")

# -- Constants -----------------------------------------------------------------
_VPIN_HIGH_TOXICITY = 0.7
_IMBALANCE_Z_THRESHOLD = 2.0
_INSTITUTIONAL_PROB_THRESHOLD = 0.6
_MIN_BARS = 20
_MIN_CONFIDENCE_FLOOR = 0.35
_FLOW_MAX_AGE_S = 300

_REGIME_MAP = {
    "trending_up": RegimeContext.TRENDING_UP,
    "trending_down": RegimeContext.TRENDING_DOWN,
    "ranging": RegimeContext.RANGING,
    "high_volatility": RegimeContext.VOLATILE,
    "low_volatility": RegimeContext.QUIET,
    "breakout": RegimeContext.TRANSITION,
}


class OrderFlowImbalanceScanner(BaseScanner[AdvancedScanResult]):
    """Scan for order flow imbalances via PredictiveOrderFlow.

    Triggers when VPIN > 0.7, imbalance z > 2, or institutional
    footprint > 0.6. Direction from net flow; confidence blended from
    VPIN, imbalance magnitude, and the engine's own confidence.
    """

    def __init__(
        self,
        config: Optional[ScannerConfig] = None,
        volume_per_bar: int = 100_000,
        vpin_bucket_size: int = 50_000,
        vpin_threshold: float = _VPIN_HIGH_TOXICITY,
        imbalance_z_threshold: float = _IMBALANCE_Z_THRESHOLD,
        institutional_threshold: float = _INSTITUTIONAL_PROB_THRESHOLD,
    ):
        super().__init__(name="order_flow_imbalance_scanner", scan_mode=ScanMode.ALL, config=config)
        self._vol_per_bar = volume_per_bar
        self._vpin_bucket = vpin_bucket_size
        self._vpin_thresh = vpin_threshold
        self._imb_z_thresh = imbalance_z_threshold
        self._inst_thresh = institutional_threshold
        self._engines: Dict[str, "PredictiveOrderFlow"] = {}

    # -- helpers ---------------------------------------------------------------

    def _get_engine(self, symbol: str) -> Optional["PredictiveOrderFlow"]:
        """Return (or create) a PredictiveOrderFlow for *symbol*."""
        if not _HAS_POF:
            return None
        if symbol not in self._engines:
            self._engines[symbol] = PredictiveOrderFlow(
                volume_per_bar=self._vol_per_bar, vpin_bucket_size=self._vpin_bucket,
            )
            self._logger.debug("Created flow engine for %s", symbol)
        return self._engines[symbol]

    # -- scan ------------------------------------------------------------------

    async def scan(self, context: ScanContext) -> List[AdvancedScanResult]:
        if not _HAS_POF:
            self._logger.error("PredictiveOrderFlow unavailable; scan aborted.")
            return []

        results: List[AdvancedScanResult] = []
        for symbol in context.universe:
            try:
                r = self._scan_symbol(symbol, context)
                if r is not None:
                    results.append(r)
            except Exception as exc:
                self._logger.warning("Error scanning %s: %s", symbol, exc, exc_info=True)

        self._logger.info("Order flow scan: %d signals / %d symbols", len(results), len(context.universe))
        return results

    def _scan_symbol(self, symbol: str, context: ScanContext) -> Optional[AdvancedScanResult]:
        """Run order-flow analysis for one symbol."""
        md = context.market_data.get(symbol)
        hd = context.historical_data.get(symbol)
        if not md or not hd:
            self._logger.debug("%s: missing data", symbol)
            return None
        if not self.apply_filters(md):
            return None
        if len(hd.bars) < _MIN_BARS:
            self._logger.debug("%s: only %d bars (need %d)", symbol, len(hd.bars), _MIN_BARS)
            return None

        engine = self._get_engine(symbol)
        if engine is None:
            return None

        # Reset engine for a clean pass over the window
        engine.classifier.reset()
        engine.vpin_calculator.reset()
        engine.volume_clock = type(engine.volume_clock)(volume_per_bar=self._vol_per_bar)
        engine.aggression_detector = type(engine.aggression_detector)()
        engine.trade_history, engine.imbalance_history = [], []
        engine.current_state, engine.signals = None, []

        # Feed bars as synthetic trades
        bid = md.bid or md.close * 0.9999
        ask = md.ask or md.close * 1.0001
        for bar in hd.bars:
            engine.process_trade(
                price=bar.close,
                size=max(bar.volume, 1),
                timestamp=getattr(bar, "timestamp", context.timestamp),
                bid=bar.bid or bid,
                ask=bar.ask or ask,
            )

        state = engine.analyze()
        if state is None:
            return None
        return self._evaluate_flow(symbol, md, state, engine, context)

    # -- signal evaluation -----------------------------------------------------

    def _evaluate_flow(self, symbol, md, state, engine, context) -> Optional[AdvancedScanResult]:
        vpin = state.toxicity
        imbalance = state.imbalance
        aggression = state.aggression_ratio
        inst_prob = state.institutional_probability

        # Imbalance z-score
        imb_hist = engine.imbalance_history
        if len(imb_hist) >= 10:
            arr = np.array(imb_hist[-50:])
            std = float(np.std(arr))
            imb_z = (imbalance - float(np.mean(arr))) / std if std > 1e-9 else 0.0
        else:
            imb_z = 0.0

        vpin_hit = vpin >= self._vpin_thresh
        imb_hit = abs(imb_z) >= self._imb_z_thresh
        inst_hit = inst_prob >= self._inst_thresh

        if not (vpin_hit or imb_hit or inst_hit):
            return None

        # Direction
        if imbalance > 0 or aggression > 0.1:
            direction = "BULLISH"
        elif imbalance < 0 or aggression < -0.1:
            direction = "BEARISH"
        else:
            direction = "NEUTRAL"

        # Confidence (0-1)
        parts: List[float] = []
        if vpin_hit:
            parts.append(min(vpin, 1.0))
        if imb_hit:
            parts.append(min(abs(imb_z) / 4.0, 1.0))
        if inst_hit:
            parts.append(inst_prob)
        raw_conf = float(np.mean(parts)) if parts else 0.0
        confidence = round(max(0.6 * raw_conf + 0.4 * state.confidence, _MIN_CONFIDENCE_FLOOR), 4)
        confidence = min(confidence, 1.0)

        # Signal strength
        strength = round(min(
            0.3 * min(vpin / self._vpin_thresh, 1.5)
            + 0.4 * min(abs(imb_z) / 3.0, 1.0)
            + 0.3 * inst_prob,
            1.0,
        ), 4)

        # Evidence
        supporting: List[str] = []
        contradicting: List[str] = []
        if vpin_hit:
            supporting.append(f"VPIN={vpin:.3f} exceeds toxicity threshold ({self._vpin_thresh})")
        if imb_hit:
            supporting.append(f"Order imbalance z={imb_z:.2f} (raw={imbalance:.3f})")
        if inst_hit:
            supporting.append(f"Institutional footprint prob={inst_prob:.2f}")
        if abs(aggression) > 0.2:
            supporting.append(f"Aggressive {'buy' if aggression > 0 else 'sell'} flow (ratio={aggression:.2f})")
        if vpin < 0.3:
            contradicting.append("Low VPIN — minimal informed trading")
        if abs(imb_z) < 1.0 and not imb_hit:
            contradicting.append("Imbalance within normal range")
        if direction == "NEUTRAL":
            contradicting.append("No clear directional bias")

        # Trade levels
        price = md.close
        atr = md.atr
        stop_dist = atr * 2.0 if atr and atr > 0 else price * 0.02
        sign = 1 if direction == "BULLISH" else -1
        if direction == "NEUTRAL":
            sign = 1

        stop_loss = round(price - sign * stop_dist, 2)
        target = round(price + sign * stop_dist * 2.0, 2)
        risk = abs(price - stop_loss)
        reward = abs(target - price)
        rr = round(reward / risk, 2) if risk > 0 else 0.0
        exp_move = round(reward / price * 100.0, 2) if price > 0 else 0.0

        regime = _REGIME_MAP.get(context.market_regime.value, RegimeContext.RANGING)

        self._logger.info(
            "%s: signal dir=%s conf=%.2f vpin=%.3f imb_z=%.2f inst=%.2f",
            symbol, direction, confidence, vpin, imb_z, inst_prob,
        )

        return AdvancedScanResult(
            scan_id=str(uuid.uuid4()),
            scan_name="order_flow_imbalance_scanner",
            category=ScanCategory.INSTITUTIONAL,
            timestamp=datetime.now(timezone.utc),
            symbol=symbol,
            signal_direction=direction,
            signal_strength=strength,
            confidence=confidence,
            expected_move_pct=exp_move,
            expected_timeframe=ExpectedTimeframe.INTRADAY,
            risk_reward_ratio=rr,
            entry_price=price,
            stop_loss_level=stop_loss,
            target_level=target,
            secondary_targets=[
                round(price + sign * stop_dist * 1.5, 2),
                round(price + sign * stop_dist * 3.0, 2),
            ],
            supporting_evidence=supporting,
            contradicting_evidence=contradicting,
            historical_accuracy=0.0,
            regime_context=regime,
            mathematical_basis=(
                "VPIN measures flow toxicity via volume-bucketed trade imbalance. "
                f"Imbalance z-scores flag deviations beyond {self._imb_z_thresh} sigma. "
                "Institutional footprint from trade-size distribution analysis."
            ),
            false_positive_rate=0.0,
            decay_halflife_days=1,
            metadata={
                "vpin": round(vpin, 4),
                "order_imbalance": round(imbalance, 4),
                "imbalance_z_score": round(imb_z, 4),
                "aggression_ratio": round(aggression, 4),
                "institutional_probability": round(inst_prob, 4),
                "flow_direction": state.direction.value,
                "predicted_direction": state.predicted_direction,
                "trades_processed": len(engine.trade_history),
                "volume_bars": len(engine.volume_clock.bars),
            },
        )

    # -- validate_signal -------------------------------------------------------

    def validate_signal(self, result: AdvancedScanResult, context: ScanContext) -> bool:
        """Validate an order-flow signal.

        Checks data recency, minimum confidence, valid entry price,
        and presence of supporting evidence.
        """
        # 1. Data recency
        age = abs((context.timestamp - result.timestamp).total_seconds())
        if age > _FLOW_MAX_AGE_S:
            self._logger.debug("%s: stale signal (%.0fs > %ds)", result.symbol, age, _FLOW_MAX_AGE_S)
            return False

        # 2. Confidence gate (AdvancedScanResult uses 0-1 scale)
        min_conf = self.config.min_confidence / 100.0
        if result.confidence < min_conf:
            self._logger.debug("%s: low confidence %.4f < %.4f", result.symbol, result.confidence, min_conf)
            return False

        # 3. Entry price
        if result.entry_price is None or result.entry_price <= 0:
            self._logger.debug("%s: invalid entry price", result.symbol)
            return False

        # 4. Must have supporting evidence
        if not result.supporting_evidence:
            self._logger.debug("%s: no supporting evidence", result.symbol)
            return False

        return True
