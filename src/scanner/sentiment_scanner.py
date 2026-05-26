"""
Revolution Alpha Engine - Sentiment Alpha Scanner

Wraps the alternative-data sentiment analysis pipeline as a BaseScanner
subclass.  Falls back to a pseudo-sentiment approach (derived from
price-action, volume, and volatility) when live NLP feeds are unavailable.

The composite score blends NLP-derived sentiment (when present) with
pseudo-sentiment into a single [-1, +1] value.  Signals are emitted as
AdvancedScanResult when the composite exceeds +/-0.5.
"""

from __future__ import annotations

import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np

from .base import BaseScanner, ScanContext, HistoricalData, MarketData
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

# Graceful import -- fall back to pseudo-sentiment when unavailable.
_HAS_ALTERNATIVE_DATA = False
AlternativeDataEngine = None  # type: ignore[assignment]
SentimentAnalyzer = None  # type: ignore[assignment]

try:
    from src.alpha.alternative_data import (
        AlternativeDataEngine as _ADE,
        SentimentAnalyzer as _SA,
    )
    AlternativeDataEngine = _ADE  # type: ignore[assignment]
    SentimentAnalyzer = _SA  # type: ignore[assignment]
    _HAS_ALTERNATIVE_DATA = True
except Exception:  # pragma: no cover
    pass

logger = logging.getLogger(__name__)

_EPS = 1e-15


def _safe_div(num: float, den: float) -> float:
    if abs(den) < _EPS:
        return 0.0
    return num / den


# ============================================================================
# PseudoSentimentEngine
# ============================================================================

class PseudoSentimentEngine:
    """
    Derives sentiment-proxy scores from price-action and volume.

    Three sub-signals (each in [-1, +1]):
      1. Momentum sentiment -- returns normalised by volatility.
      2. Volume sentiment   -- volume-weighted directional pressure.
      3. RSI reversal       -- extreme RSI + volume divergence.
    """

    MOMENTUM_LOOKBACK = 10
    VOLUME_LOOKBACK = 20
    RSI_LOOKBACK = 14
    RSI_OVERBOUGHT = 70.0
    RSI_OVERSOLD = 30.0
    VOLATILITY_LOOKBACK = 20

    def compute(self, historical: HistoricalData,
                current: Optional[MarketData] = None) -> Dict[str, Any]:
        """Return composite and per-component pseudo-sentiment scores."""
        closes = np.array(historical.closes, dtype=np.float64)
        volumes = np.array(historical.volumes, dtype=np.float64)
        highs = np.array(historical.highs, dtype=np.float64)
        lows = np.array(historical.lows, dtype=np.float64)

        if len(closes) < max(self.RSI_LOOKBACK, self.VOLUME_LOOKBACK) + 1:
            return self._empty("insufficient data")

        mom, mom_d = self._momentum_sentiment(closes)
        vol, vol_d = self._volume_sentiment(closes, volumes)
        rsi, rsi_d = self._rsi_reversal_sentiment(closes, volumes, highs, lows)

        composite = float(np.clip(np.mean([mom, vol, rsi]), -1.0, 1.0))
        return {
            "composite": composite, "momentum": mom, "volume": vol,
            "rsi_reversal": rsi, "n_sources": 3,
            "details": {"momentum": mom_d, "volume": vol_d, "rsi_reversal": rsi_d},
        }

    # -- Momentum: strong up/down moves relative to vol = sentiment proxy --

    def _momentum_sentiment(self, closes: np.ndarray) -> tuple[float, Dict]:
        lookback = min(self.MOMENTUM_LOOKBACK, len(closes) - 1)
        if lookback < 2:
            return 0.0, {"reason": "insufficient bars"}

        returns = np.diff(np.log(np.maximum(closes, _EPS)))
        cum_ret = float(np.sum(returns[-lookback:]))
        vw = min(self.VOLATILITY_LOOKBACK, len(returns))
        vol = float(np.std(returns[-vw:], ddof=1)) if vw > 1 else _EPS

        z = _safe_div(cum_ret, vol * math.sqrt(lookback))
        score = float(np.tanh(z / 2.0))
        return score, {"cumulative_return": cum_ret, "realised_vol": vol, "z_score": z}

    # -- Volume: expanding volume in move direction = conviction proxy -----

    def _volume_sentiment(self, closes: np.ndarray,
                          volumes: np.ndarray) -> tuple[float, Dict]:
        lb = min(self.VOLUME_LOOKBACK, len(closes) - 1)
        if lb < 3:
            return 0.0, {"reason": "insufficient bars"}

        price_chg = np.diff(closes[-lb - 1:])
        recent_vol = volumes[-lb:]
        avg_vol = float(np.mean(recent_vol)) + _EPS
        rel_vol = recent_vol / avg_vol

        weighted = price_chg * rel_vol[:len(price_chg)]
        total_w = float(np.sum(rel_vol[:len(price_chg)])) + _EPS
        avg_abs = float(np.mean(np.abs(price_chg))) + _EPS
        norm = (float(np.sum(weighted)) / total_w) / avg_abs
        score = float(np.clip(np.tanh(norm / 2.0), -1.0, 1.0))

        return score, {
            "avg_volume": avg_vol,
            "recent_relative_volume": float(np.mean(rel_vol[-5:])),
            "normalised_vol_direction": norm,
        }

    # -- RSI reversal: extreme RSI + volume divergence = capitulation ------

    def _rsi_reversal_sentiment(self, closes: np.ndarray, volumes: np.ndarray,
                                highs: np.ndarray,
                                lows: np.ndarray) -> tuple[float, Dict]:
        rsi = self._compute_rsi(closes, self.RSI_LOOKBACK)
        if rsi is None:
            return 0.0, {"reason": "cannot compute RSI"}

        vw = volumes[-self.RSI_LOOKBACK:]
        if len(vw) < self.RSI_LOOKBACK:
            return 0.0, {"reason": "insufficient volume bars"}

        half = self.RSI_LOOKBACK // 2
        vol_expanding = float(np.mean(vw[half:])) > float(np.mean(vw[:half])) * 1.1

        score = 0.0
        detail: Dict[str, Any] = {"rsi": rsi, "volume_expanding": vol_expanding}

        if rsi >= self.RSI_OVERBOUGHT:
            extremity = (rsi - self.RSI_OVERBOUGHT) / (100.0 - self.RSI_OVERBOUGHT + _EPS)
            score = -extremity * (1.3 if not vol_expanding else 0.7)
            detail["signal"] = "overbought_reversal"
        elif rsi <= self.RSI_OVERSOLD:
            extremity = (self.RSI_OVERSOLD - rsi) / (self.RSI_OVERSOLD + _EPS)
            score = extremity * (1.3 if not vol_expanding else 0.7)
            detail["signal"] = "oversold_reversal"

        return float(np.clip(score, -1.0, 1.0)), detail

    @staticmethod
    def _compute_rsi(closes: np.ndarray, period: int) -> Optional[float]:
        """Wilder-smoothed RSI."""
        if len(closes) < period + 1:
            return None
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)
        avg_g = float(np.mean(gains[:period]))
        avg_l = float(np.mean(losses[:period]))
        for i in range(period, len(gains)):
            avg_g = (avg_g * (period - 1) + gains[i]) / period
            avg_l = (avg_l * (period - 1) + losses[i]) / period
        if avg_l < _EPS:
            return 100.0
        return 100.0 - 100.0 / (1.0 + avg_g / avg_l)

    @staticmethod
    def _empty(reason: str) -> Dict[str, Any]:
        return {"composite": 0.0, "momentum": 0.0, "volume": 0.0,
                "rsi_reversal": 0.0, "n_sources": 0, "details": {"reason": reason}}


# ============================================================================
# SentimentAlphaScanner
# ============================================================================

class SentimentAlphaScanner(BaseScanner[AdvancedScanResult]):
    """
    Scanner that produces sentiment-driven alpha signals.

    Loops over context.universe, computes a composite sentiment score from
    NLP data (when present in context.metadata["sentiment_data"]) and
    quantitative pseudo-sentiment proxies, and emits AdvancedScanResult
    when |composite| >= threshold.
    """

    SCANNER_NAME = "sentiment_alpha_scanner"
    SCAN_MODE = ScanMode.ALL
    CATEGORY = ScanCategory.MACHINE_LEARNING

    def __init__(self, config: Optional[ScannerConfig] = None,
                 composite_threshold: float = 0.5,
                 nlp_weight: float = 0.4):
        super().__init__(name=self.SCANNER_NAME, scan_mode=self.SCAN_MODE, config=config)
        self.composite_threshold = composite_threshold
        self.nlp_weight = nlp_weight
        self._pseudo_engine = PseudoSentimentEngine()
        self._sentiment_analyzer: Optional[Any] = None

        if _HAS_ALTERNATIVE_DATA and SentimentAnalyzer is not None:
            try:
                self._sentiment_analyzer = SentimentAnalyzer()
                self._logger.info("SentimentAnalyzer loaded -- NLP available")
            except Exception as exc:
                self._logger.warning("SentimentAnalyzer init failed (%s); pseudo-only", exc)
        else:
            self._logger.info("alternative_data unavailable; pseudo-sentiment only")

    # -- BaseScanner.scan --------------------------------------------------

    async def scan(self, context: ScanContext) -> List[AdvancedScanResult]:
        results: List[AdvancedScanResult] = []
        for symbol in context.universe:
            try:
                r = self._scan_symbol(symbol, context)
                if r is not None:
                    results.append(r)
            except Exception as exc:
                self._logger.warning("Error scanning %s: %s", symbol, exc, exc_info=True)
        results.sort(key=lambda r: r.confidence, reverse=True)
        return results

    # -- BaseScanner.validate_signal ---------------------------------------

    def validate_signal(self, result: AdvancedScanResult,
                        context: ScanContext) -> bool:
        """Check minimum confidence and that not all evidence contradicts."""
        if result.confidence < self.config.min_confidence / 100.0:
            return False
        if result.contradicting_evidence and not result.supporting_evidence:
            return False
        return True

    # -- Per-symbol logic --------------------------------------------------

    def _scan_symbol(self, symbol: str,
                     context: ScanContext) -> Optional[AdvancedScanResult]:
        historical = context.historical_data.get(symbol)
        current = context.market_data.get(symbol)
        if historical is None or len(historical.bars) < 15:
            return None

        # NLP sentiment (optional, from context metadata).
        nlp_score, nlp_conf, nlp_detail = None, None, {}
        sym_sent = (context.metadata or {}).get("sentiment_data", {}).get(symbol)
        if sym_sent is not None:
            nlp_score, nlp_conf, nlp_detail = self._process_nlp(symbol, sym_sent)

        # Pseudo-sentiment from price/volume/volatility.
        pseudo = self._pseudo_engine.compute(historical, current)

        # Blend into composite.
        composite, n_conf, supporting, contradicting = self._blend(
            pseudo["composite"], pseudo, nlp_score, nlp_conf, nlp_detail,
        )

        if abs(composite) < self.composite_threshold:
            return None

        # Direction and confidence.
        direction = "BULLISH" if composite > 0 else "BEARISH"
        confidence = float(np.clip(abs(composite) * (0.5 + 0.1 * n_conf), 0.0, 1.0))
        strength = float(np.clip(abs(composite), 0.0, 1.0))

        # Trade levels.
        entry = current.close if current else historical.bars[-1].close
        atr = self._estimate_atr(historical)
        sign = 1.0 if direction == "BULLISH" else -1.0
        stop = entry - sign * 2.0 * atr
        tgt = entry + sign * 3.0 * atr
        risk = abs(entry - stop)
        rr = _safe_div(abs(tgt - entry), risk)
        exp_move = _safe_div(tgt - entry, entry) * 100.0

        return AdvancedScanResult(
            scan_id=str(uuid.uuid4()),
            scan_name=self.SCANNER_NAME,
            category=self.CATEGORY,
            symbol=symbol,
            signal_direction=direction,
            signal_strength=strength,
            confidence=confidence,
            expected_move_pct=exp_move,
            expected_timeframe=ExpectedTimeframe.SWING,
            risk_reward_ratio=rr,
            entry_price=entry,
            stop_loss_level=stop,
            target_level=tgt,
            secondary_targets=[entry + sign * 2.0 * atr, entry + sign * 4.0 * atr],
            supporting_evidence=supporting,
            contradicting_evidence=contradicting,
            historical_accuracy=0.0,
            regime_context=self._resolve_regime(context),
            mathematical_basis=(
                "Composite sentiment: blends NLP sentiment (when available) "
                "with pseudo-sentiment proxies (normalised momentum, "
                "volume-direction, RSI reversal) via tanh-mapped z-scores."
            ),
            false_positive_rate=float(np.clip(1.0 - confidence, 0.0, 1.0)),
            decay_halflife_days=14,
            metadata={
                "scanner": self.SCANNER_NAME,
                "composite_score": composite,
                "pseudo_sentiment": pseudo,
                "nlp_sentiment": nlp_detail or None,
                "nlp_available": nlp_score is not None,
                "n_confirming_sources": n_conf,
            },
        )

    # -- NLP sentiment parsing ---------------------------------------------

    def _process_nlp(self, symbol: str,
                     data: Any) -> tuple[Optional[float], Optional[float], Dict]:
        """Parse NLP sentiment from SentimentSignal, dict, or float."""
        try:
            if hasattr(data, "sentiment_score"):
                s = float(data.sentiment_score)
                c = float(getattr(data, "confidence", 0.5))
                return s, c, {"source": "SentimentSignal", "score": s, "confidence": c}
            if isinstance(data, dict):
                s = float(data.get("score", 0.0))
                c = float(data.get("confidence", 0.5))
                return s, c, {"source": "dict", "score": s, "confidence": c}
            if isinstance(data, (int, float)):
                s = float(data)
                return s, 0.5, {"source": "scalar", "score": s}
        except (TypeError, ValueError) as exc:
            self._logger.debug("Cannot parse NLP sentiment for %s: %s", symbol, exc)
        return None, None, {}

    # -- Blending ----------------------------------------------------------

    def _blend(self, pseudo_score: float, pseudo_detail: Dict,
               nlp_score: Optional[float], nlp_conf: Optional[float],
               nlp_detail: Dict) -> tuple[float, int, List[str], List[str]]:
        """Blend pseudo-sentiment and NLP into composite with evidence lists."""
        supporting: List[str] = []
        contradicting: List[str] = []
        components = {
            "momentum": pseudo_detail.get("momentum", 0.0),
            "volume": pseudo_detail.get("volume", 0.0),
            "rsi_reversal": pseudo_detail.get("rsi_reversal", 0.0),
        }

        if nlp_score is not None and nlp_conf is not None:
            ew = self.nlp_weight * nlp_conf
            composite = ew * nlp_score + (1.0 - ew) * pseudo_score
        else:
            composite = pseudo_score
        composite = float(np.clip(composite, -1.0, 1.0))

        dom = 1.0 if composite >= 0 else -1.0
        n_conf = 0
        for label, val in components.items():
            tag = f"pseudo:{label} ({val:+.3f})"
            if val * dom > 0:
                supporting.append(tag); n_conf += 1
            elif abs(val) > 0.05:
                contradicting.append(tag)
        if nlp_score is not None:
            tag = f"nlp_sentiment ({nlp_score:+.3f})"
            if nlp_score * dom > 0:
                supporting.append(tag); n_conf += 1
            elif abs(nlp_score) > 0.05:
                contradicting.append(tag)

        return composite, n_conf, supporting, contradicting

    # -- ATR estimation ----------------------------------------------------

    @staticmethod
    def _estimate_atr(historical: HistoricalData, period: int = 14) -> float:
        bars = historical.bars
        if len(bars) < 2:
            return max(bars[-1].close * 0.02, 0.01) if bars else 0.01
        trs = []
        for i in range(1, len(bars)):
            h, l, pc = bars[i].high, bars[i].low, bars[i - 1].close
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        if not trs:
            return max(bars[-1].close * 0.02, 0.01)
        ep = min(period, len(trs))
        atr = float(np.mean(trs[:ep]))
        for tr in trs[ep:]:
            atr = (atr * (ep - 1) + tr) / ep
        return max(atr, 0.01)

    # -- Regime mapping ----------------------------------------------------

    @staticmethod
    def _resolve_regime(context: ScanContext) -> RegimeContext:
        return {
            "trending_up": RegimeContext.TRENDING_UP,
            "trending_down": RegimeContext.TRENDING_DOWN,
            "ranging": RegimeContext.RANGING,
            "high_volatility": RegimeContext.VOLATILE,
            "low_volatility": RegimeContext.QUIET,
            "breakout": RegimeContext.TRANSITION,
        }.get(context.market_regime.value, RegimeContext.RANGING)
