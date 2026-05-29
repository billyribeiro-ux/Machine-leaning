"""
Revolution Alpha Engine - VWAP Deviation Scanner

Institutional-grade scanner for detecting mean-reversion opportunities
around Volume Weighted Average Price (VWAP).  Computes session VWAP with
standard deviation bands, z-scores, and volume-weighted momentum to
identify high-probability reversion setups.  Tracks anchored VWAPs from
session open, prior close, and weekly open.
"""

from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass, field
import logging
import uuid

import numpy as np

from .base import BaseScanner, ScanContext, MarketData, HistoricalData
from .models import ScanResult, ScanMode, SignalDirection, ScannerConfig, TimeFrame
from .advanced_models import (
    AdvancedScanResult, ScanCategory, RegimeContext, ExpectedTimeframe,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supporting dataclasses
# ---------------------------------------------------------------------------

@dataclass
class VWAPBands:
    """VWAP value and its standard-deviation bands."""
    vwap: float
    upper_1: float   # +1 sigma
    lower_1: float   # -1 sigma
    upper_2: float   # +2 sigma
    lower_2: float   # -2 sigma
    upper_3: float   # +3 sigma
    lower_3: float   # -3 sigma

@dataclass
class VWAPMetrics:
    """Full VWAP analytics for a single symbol."""
    symbol: str
    session_vwap: VWAPBands
    z_score: float
    volume_weighted_momentum: float
    mean_reversion_score: float
    anchored_vwaps: dict[str, float] = field(default_factory=dict)
    volume_exhaustion: bool = False
    vwap_reclaim: bool = False
    session_elapsed_pct: float = 0.0

    @property
    def is_extended(self) -> bool:
        return abs(self.z_score) >= 2.0

    @property
    def is_extreme(self) -> bool:
        return abs(self.z_score) >= 3.0

# Empirical mean-reversion rates indexed by absolute z-score bucket.
_REVERSION_TABLE: dict[tuple[float, float], float] = {
    (0.0, 1.0): 0.50, (1.0, 1.5): 0.55, (1.5, 2.0): 0.62,
    (2.0, 2.5): 0.70, (2.5, 3.0): 0.78, (3.0, 4.0): 0.85,
    (4.0, float("inf")): 0.90,
}

def _lookup_reversion_rate(abs_z: float) -> float:
    """Return the historical reversion probability for a given |z|."""
    for (lo, hi), rate in _REVERSION_TABLE.items():
        if lo <= abs_z < hi:
            return rate
    return 0.50

# ---------------------------------------------------------------------------
# VWAP Deviation Scanner
# ---------------------------------------------------------------------------

class VWAPDeviationScanner(BaseScanner[ScanResult]):
    """
    Detect mean-reversion opportunities around session VWAP.

    Calculates real-time VWAP and standard deviation bands from intraday
    bars, then identifies symbols whose price has deviated significantly
    while showing volume exhaustion -- conditions that historically
    precede a reversion to the mean.
    """

    def __init__(self, config: Optional[ScannerConfig] = None) -> None:
        super().__init__(
            name="vwap_deviation_scanner",
            scan_mode=ScanMode.MEAN_REVERSION,
            config=config,
        )
        self._min_z_score: float = 1.5
        self._volume_lookback: int = 5
        self._session_minutes: float = 390.0  # 6.5 hours regular session

    # -- Core scan --------------------------------------------------------

    async def scan(self, context: ScanContext) -> list[ScanResult]:
        """Scan the universe for VWAP mean-reversion setups."""
        results: list[ScanResult] = []
        for symbol in context.universe:
            try:
                result = self._scan_symbol(symbol, context)
                if result is not None:
                    results.append(result)
            except Exception as exc:
                self._logger.warning("Error scanning %s: %s", symbol, exc, exc_info=True)
        results.sort(key=lambda r: r.confidence, reverse=True)
        return results

    # -- Per-symbol analysis ----------------------------------------------

    def _scan_symbol(self, symbol: str, context: ScanContext) -> Optional[ScanResult]:
        hist = context.historical_data.get(symbol)
        market = context.market_data.get(symbol)
        if hist is None or market is None:
            return None
        if len(hist.bars) < 10:
            self._logger.debug("%s: insufficient bars (%d)", symbol, len(hist.bars))
            return None
        if not self.apply_filters(market):
            return None

        metrics = self._compute_metrics(symbol, hist, market)
        if metrics is None or abs(metrics.z_score) < self._min_z_score:
            return None

        direction = self._determine_direction(metrics)
        if direction == SignalDirection.NEUTRAL:
            return None

        confidence = self._compute_confidence(metrics)
        entry = market.close
        stop = self._compute_stop(metrics, direction, entry)
        target = self._compute_target(metrics)
        rr = self.calculate_risk_reward(entry, stop, target)
        supporting, contradicting = self._gather_evidence(metrics)
        urgency = self._time_weighted_urgency(metrics.session_elapsed_pct)

        return ScanResult(
            symbol=symbol, scanner_type=self.name, direction=direction,
            confidence=confidence, entry_price=entry, stop_loss=stop,
            targets=self._compute_targets(metrics, direction),
            risk_reward=rr, timeframe=TimeFrame.M5,
            metadata={
                "z_score": round(metrics.z_score, 4),
                "session_vwap": round(metrics.session_vwap.vwap, 4),
                "volume_weighted_momentum": round(metrics.volume_weighted_momentum, 4),
                "mean_reversion_score": round(metrics.mean_reversion_score, 4),
                "volume_exhaustion": metrics.volume_exhaustion,
                "vwap_reclaim": metrics.vwap_reclaim,
                "session_elapsed_pct": round(metrics.session_elapsed_pct, 4),
                "urgency": round(urgency, 4),
                "anchored_vwaps": {k: round(v, 4) for k, v in metrics.anchored_vwaps.items()},
                "supporting_evidence": supporting,
                "contradicting_evidence": contradicting,
            },
        )

    # -- VWAP computation -------------------------------------------------

    def _compute_metrics(self, symbol: str, hist: HistoricalData,
                         market: MarketData) -> Optional[VWAPMetrics]:
        """Compute all VWAP-related metrics from intraday bars."""
        bars = hist.bars
        if not bars:
            return None
        typical_prices = np.array(
            [(b.high + b.low + b.close) / 3.0 for b in bars], dtype=np.float64)
        volumes = np.array([float(b.volume) for b in bars], dtype=np.float64)
        cum_vol = np.cumsum(volumes)
        if cum_vol[-1] == 0:
            self._logger.debug("%s: zero cumulative volume", symbol)
            return None

        cum_tp_vol = np.cumsum(typical_prices * volumes)
        vwap_series = cum_tp_vol / cum_vol
        vwap_current = float(vwap_series[-1])

        # Volume-weighted standard deviation of typical price from VWAP
        sq_dev = (typical_prices - vwap_series) ** 2
        variance = float(np.sum(sq_dev * volumes) / cum_vol[-1])
        std_dev = float(np.sqrt(variance)) if variance > 0 else 1e-9

        bands = VWAPBands(
            vwap=vwap_current,
            upper_1=vwap_current + std_dev,     lower_1=vwap_current - std_dev,
            upper_2=vwap_current + 2 * std_dev, lower_2=vwap_current - 2 * std_dev,
            upper_3=vwap_current + 3 * std_dev, lower_3=vwap_current - 3 * std_dev,
        )
        z_score = (market.close - vwap_current) / std_dev if std_dev > 1e-9 else 0.0
        vol_exhaustion = self._detect_volume_exhaustion(bars, z_score)
        base_reversion = _lookup_reversion_rate(abs(z_score))
        reversion_score = min(1.0, max(0.0, base_reversion + (0.05 if vol_exhaustion else -0.05)))

        return VWAPMetrics(
            symbol=symbol, session_vwap=bands, z_score=z_score,
            volume_weighted_momentum=self._volume_weighted_momentum(bars, vwap_current),
            mean_reversion_score=reversion_score,
            anchored_vwaps=self._compute_anchored_vwaps(bars, volumes, typical_prices),
            volume_exhaustion=vol_exhaustion,
            vwap_reclaim=self._detect_vwap_reclaim(bars, vwap_current),
            session_elapsed_pct=min(1.0, len(bars) / (self._session_minutes / 5.0)),
        )

    # -- Anchored VWAPs ---------------------------------------------------

    @staticmethod
    def _compute_anchored_vwaps(bars: list[MarketData], volumes: np.ndarray,
                                typical_prices: np.ndarray) -> dict[str, float]:
        """Compute anchored VWAPs from session open, prior close, weekly open."""
        anchored: dict[str, float] = {}
        if len(bars) > 0 and volumes.sum() > 0:
            anchored["session_open"] = float(np.sum(typical_prices * volumes) / np.sum(volumes))
        if len(bars) > 1 and volumes[1:].sum() > 0:
            anchored["prior_close"] = float(
                np.sum(typical_prices[1:] * volumes[1:]) / np.sum(volumes[1:]))
        weekly_idx = max(1, len(bars) // 5)
        wk_tp, wk_vol = typical_prices[weekly_idx:], volumes[weekly_idx:]
        if len(wk_vol) > 0 and wk_vol.sum() > 0:
            anchored["weekly_open"] = float(np.sum(wk_tp * wk_vol) / np.sum(wk_vol))
        return anchored

    # -- Volume analysis --------------------------------------------------

    def _volume_weighted_momentum(self, bars: list[MarketData], vwap: float) -> float:
        """Volume-weighted momentum relative to VWAP.  Positive = buying pressure."""
        lookback = min(self._volume_lookback, len(bars))
        if lookback == 0:
            return 0.0
        recent = bars[-lookback:]
        total_vol = sum(float(b.volume) for b in recent)
        if total_vol == 0:
            return 0.0
        return sum((b.close - vwap) * float(b.volume) for b in recent) / total_vol

    def _detect_volume_exhaustion(self, bars: list[MarketData], z_score: float) -> bool:
        """Detect declining volume while price stays extended from VWAP."""
        lookback = min(self._volume_lookback, len(bars))
        if lookback < 3:
            return False
        recent_vols = [float(b.volume) for b in bars[-lookback:]]
        decline_count = sum(
            1 for i in range(1, len(recent_vols)) if recent_vols[i] < recent_vols[i - 1])
        declining = decline_count >= (len(recent_vols) - 2)
        if declining and abs(z_score) >= 1.5:
            return True
        avg_vol = float(np.mean(recent_vols[:-1])) if len(recent_vols) > 1 else recent_vols[0]
        if avg_vol > 0 and recent_vols[-1] < avg_vol * 0.6 and abs(z_score) >= 1.5:
            return True
        return False

    # -- VWAP reclaim detection -------------------------------------------

    @staticmethod
    def _detect_vwap_reclaim(bars: list[MarketData], vwap: float) -> bool:
        """Detect price crossing back through VWAP after deviation."""
        if len(bars) < 3:
            return False
        prev, curr = bars[-2].close, bars[-1].close
        return (prev < vwap <= curr) or (prev > vwap >= curr)

    # -- Signal direction, confidence, and trade levels -------------------

    def _determine_direction(self, metrics: VWAPMetrics) -> SignalDirection:
        z = metrics.z_score
        if z <= -2.0 and (metrics.volume_exhaustion or metrics.volume_weighted_momentum > -0.01):
            return SignalDirection.LONG
        if z >= 2.0 and (metrics.volume_exhaustion or metrics.volume_weighted_momentum < 0.01):
            return SignalDirection.SHORT
        return SignalDirection.NEUTRAL

    def _compute_confidence(self, metrics: VWAPMetrics) -> float:
        """
        Confidence 0-100.  Components: z-score magnitude (35), volume
        exhaustion (20), mean-reversion score (20), VWAP reclaim (10),
        session timing (15).
        """
        score = 0.0
        abs_z = abs(metrics.z_score)
        if abs_z >= 3.0:     score += 35.0
        elif abs_z >= 2.5:   score += 28.0
        elif abs_z >= 2.0:   score += 22.0
        elif abs_z >= 1.5:   score += 15.0
        if metrics.volume_exhaustion:
            score += 20.0
        score += metrics.mean_reversion_score * 20.0
        if metrics.vwap_reclaim:
            score += 10.0
        score += metrics.session_elapsed_pct * 15.0
        return min(100.0, max(0.0, round(score, 2)))

    def _compute_stop(self, metrics: VWAPMetrics, direction: SignalDirection,
                      entry: float = 0.0) -> float:
        """Place stop beyond the extreme (3-sigma) band.

        If price has already blown past the 3-sigma band, fall back to a
        percentage-based stop so the stop is always on the correct side.
        """
        bands = metrics.session_vwap
        fallback_pct = 0.02  # 2 % beyond entry
        if direction == SignalDirection.LONG:
            stop = bands.lower_3
            if entry > 0 and stop >= entry:
                stop = entry * (1.0 - fallback_pct)
            return round(stop, 2)
        if direction == SignalDirection.SHORT:
            stop = bands.upper_3
            if entry > 0 and stop <= entry:
                stop = entry * (1.0 + fallback_pct)
            return round(stop, 2)
        return round(bands.vwap, 2)

    @staticmethod
    def _compute_target(metrics: VWAPMetrics) -> float:
        """Primary target is VWAP itself (the mean)."""
        return round(metrics.session_vwap.vwap, 2)

    @staticmethod
    def _compute_targets(metrics: VWAPMetrics, direction: SignalDirection) -> list[float]:
        """Target ladder: VWAP, then the opposite 1-sigma band."""
        bands = metrics.session_vwap
        targets: list[float] = [round(bands.vwap, 2)]
        if direction == SignalDirection.LONG:
            targets.append(round(bands.upper_1, 2))
        elif direction == SignalDirection.SHORT:
            targets.append(round(bands.lower_1, 2))
        return targets

    # -- Time-weighted urgency --------------------------------------------

    @staticmethod
    def _time_weighted_urgency(session_elapsed_pct: float) -> float:
        """Later in session -> faster expected reversion.  Returns [1.0, 2.0]."""
        return 1.0 + session_elapsed_pct

    # -- Evidence gathering -----------------------------------------------

    @staticmethod
    def _gather_evidence(metrics: VWAPMetrics) -> tuple[list[str], list[str]]:
        supporting: list[str] = []
        contradicting: list[str] = []
        abs_z = abs(metrics.z_score)
        if abs_z >= 3.0:
            supporting.append(f"Extreme VWAP deviation: z-score {metrics.z_score:+.2f}")
        elif abs_z >= 2.0:
            supporting.append(f"Significant VWAP deviation: z-score {metrics.z_score:+.2f}")
        if metrics.volume_exhaustion:
            supporting.append("Volume exhaustion detected in direction of deviation")
        if metrics.mean_reversion_score >= 0.70:
            supporting.append(f"High historical reversion rate: {metrics.mean_reversion_score:.0%}")
        if metrics.vwap_reclaim:
            supporting.append("VWAP reclaim in progress")
        if metrics.session_elapsed_pct > 0.7:
            supporting.append("Late-session timing favours reversion")
        if not metrics.volume_exhaustion and abs_z < 3.0:
            contradicting.append("No volume exhaustion yet -- trend may persist")
        if abs(metrics.volume_weighted_momentum) > 0.5:
            contradicting.append(
                f"Strong volume-weighted momentum ({metrics.volume_weighted_momentum:+.2f})")
        if metrics.session_elapsed_pct < 0.2:
            contradicting.append("Early session -- reversion may take longer")
        return supporting, contradicting

    # -- Validation -------------------------------------------------------

    def validate_signal(self, result: ScanResult, context: ScanContext) -> bool:
        """
        Validate a VWAP mean-reversion signal.
        Checks: z-score > 1.5, stop-loss placed, volume data exists.
        """
        meta = result.metadata
        z_score = meta.get("z_score")
        if z_score is None or abs(z_score) < self._min_z_score:
            self._logger.debug(
                "%s: z-score %.4f below threshold", result.symbol,
                z_score if z_score is not None else 0.0)
            return False
        if result.stop_loss is None or result.stop_loss <= 0:
            self._logger.debug("%s: invalid stop-loss", result.symbol)
            return False
        market = context.market_data.get(result.symbol)
        if market is None or market.volume <= 0:
            self._logger.debug("%s: missing or zero volume data", result.symbol)
            return False
        return True

    # -- Advanced result builder ------------------------------------------

    def build_advanced_result(self, result: ScanResult,
                              context: ScanContext) -> AdvancedScanResult:
        """Promote a ScanResult to AdvancedScanResult for composite alpha."""
        meta = result.metadata
        z_score = meta.get("z_score", 0.0)
        abs_z = abs(z_score)
        regime_map = {
            "trending_up": RegimeContext.TRENDING_UP,
            "trending_down": RegimeContext.TRENDING_DOWN,
            "ranging": RegimeContext.RANGING,
            "high_volatility": RegimeContext.VOLATILE,
            "low_volatility": RegimeContext.QUIET,
        }
        regime = regime_map.get(context.market_regime.value, RegimeContext.RANGING)
        session_pct = meta.get("session_elapsed_pct", 0.5)
        if session_pct > 0.8:
            expected_tf = ExpectedTimeframe.SCALP
        elif session_pct > 0.4:
            expected_tf = ExpectedTimeframe.INTRADAY
        else:
            expected_tf = ExpectedTimeframe.SWING
        signal_dir = ("BULLISH" if result.direction == SignalDirection.LONG
                      else "BEARISH" if result.direction == SignalDirection.SHORT
                      else "NEUTRAL")
        return AdvancedScanResult(
            scan_id=str(uuid.uuid4()), scan_name=self.name,
            category=ScanCategory.PRICE_ACTION, symbol=result.symbol,
            signal_direction=signal_dir,
            signal_strength=min(1.0, abs_z / 4.0),
            confidence=result.confidence / 100.0,
            expected_move_pct=round(abs_z * 0.25, 2),
            expected_timeframe=expected_tf,
            risk_reward_ratio=result.risk_reward or 0.0,
            entry_price=result.entry_price,
            stop_loss_level=result.stop_loss or 0.0,
            target_level=result.targets[0] if result.targets else 0.0,
            secondary_targets=result.targets[1:] if len(result.targets) > 1 else [],
            supporting_evidence=meta.get("supporting_evidence", []),
            contradicting_evidence=meta.get("contradicting_evidence", []),
            historical_accuracy=meta.get("mean_reversion_score", 0.0),
            regime_context=regime,
            mathematical_basis=(
                "VWAP z-score mean reversion: P(revert | |z| > 2) estimated "
                "from cumulative volume-weighted price deviation bands"),
            false_positive_rate=max(0.0, 1.0 - meta.get("mean_reversion_score", 0.5)),
            decay_halflife_days=1,
            metadata={
                "z_score": z_score,
                "session_vwap": meta.get("session_vwap"),
                "volume_exhaustion": meta.get("volume_exhaustion"),
                "anchored_vwaps": meta.get("anchored_vwaps"),
            },
        )
