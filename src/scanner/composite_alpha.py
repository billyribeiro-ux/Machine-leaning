"""
Revolution Alpha Engine - Composite Alpha Scanner

Multi-signal fusion engine that combines all scan categories using:
- Bayesian Model Averaging for signal combination
- Dynamic regime-aware weighting
- Confidence calibration using isotonic regression
- Alpha decay management with automatic signal retirement
- Cross-signal correlation analysis for redundancy detection

This is the J2 "Composite Alpha Scanner" from the taxonomy -
the meta-scanner that orchestrates all other scans into a unified
high-conviction signal.
"""

import numpy as np
from typing import Optional, List, Dict, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import logging
import uuid

from .base import BaseScanner, ScanContext, MarketData, HistoricalData
from .models import (
    ScanResult,
    ScanMode,
    SignalDirection,
    ScannerConfig,
    MarketRegime,
    TimeFrame,
)
from .advanced_models import (
    AdvancedScanResult,
    ScanCategory,
    RegimeContext,
    ExpectedTimeframe,
    VolatilityRegime,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Signal Correlation & Redundancy Analysis
# =============================================================================

class SignalCorrelationAnalyzer:
    """
    Analyze cross-signal correlations to detect redundancy.

    Two signals that are highly correlated provide less marginal
    information than two uncorrelated signals. This analyzer
    penalizes redundant signals in the ensemble.
    """

    def __init__(self, lookback: int = 100):
        self.lookback = lookback
        self._signal_history: Dict[str, List[float]] = defaultdict(list)

    def record_signal(self, scan_name: str, signal_value: float):
        """Record a signal value for correlation tracking."""
        self._signal_history[scan_name].append(signal_value)
        if len(self._signal_history[scan_name]) > self.lookback:
            self._signal_history[scan_name] = self._signal_history[scan_name][-self.lookback:]

    def compute_correlation_matrix(self) -> Tuple[np.ndarray, List[str]]:
        """Compute pairwise Spearman rank correlation between signals."""
        names = sorted(self._signal_history.keys())
        n = len(names)

        if n < 2:
            return np.eye(n), names

        min_len = min(len(self._signal_history[name]) for name in names)
        if min_len < 10:
            return np.eye(n), names

        matrix = np.zeros((n, n))
        for i in range(n):
            for j in range(n):
                if i == j:
                    matrix[i, j] = 1.0
                elif i < j:
                    x = np.array(self._signal_history[names[i]][-min_len:])
                    y = np.array(self._signal_history[names[j]][-min_len:])
                    corr = _spearman_correlation(x, y)
                    matrix[i, j] = corr
                    matrix[j, i] = corr

        return matrix, names

    def get_redundancy_penalties(self) -> Dict[str, float]:
        """
        Compute redundancy penalties for each signal.

        A signal highly correlated with many others gets penalized
        more heavily. Returns weights in [0.5, 1.0] where 1.0 = no penalty.
        """
        corr_matrix, names = self.compute_correlation_matrix()
        n = len(names)
        penalties = {}

        for i, name in enumerate(names):
            if n <= 1:
                penalties[name] = 1.0
                continue

            avg_abs_corr = np.mean(np.abs(corr_matrix[i, :][corr_matrix[i, :] != 1.0]))
            penalty = max(0.5, 1.0 - avg_abs_corr * 0.5)
            penalties[name] = penalty

        return penalties


def _spearman_correlation(x: np.ndarray, y: np.ndarray) -> float:
    """Compute Spearman rank correlation between two arrays."""
    n = len(x)
    if n < 3:
        return 0.0

    rank_x = np.argsort(np.argsort(x)).astype(float)
    rank_y = np.argsort(np.argsort(y)).astype(float)

    d = rank_x - rank_y
    d_sq_sum = np.sum(d ** 2)

    rho = 1.0 - (6.0 * d_sq_sum) / (n * (n ** 2 - 1))
    return np.clip(rho, -1.0, 1.0)


# =============================================================================
# Confidence Calibration
# =============================================================================

class ConfidenceCalibrator:
    """
    Calibrate predicted confidence to match empirical hit rates.

    Uses isotonic regression (pool adjacent violators algorithm)
    to map raw confidence scores to calibrated probabilities.
    """

    def __init__(self, n_bins: int = 20):
        self.n_bins = n_bins
        self._predictions: List[float] = []
        self._outcomes: List[int] = []  # 1 = correct, 0 = incorrect
        self._calibration_map: Optional[np.ndarray] = None

    def record(self, predicted_confidence: float, was_correct: bool):
        """Record a prediction and its outcome."""
        self._predictions.append(predicted_confidence)
        self._outcomes.append(1 if was_correct else 0)

    def fit(self):
        """Fit the calibration curve using isotonic regression."""
        if len(self._predictions) < self.n_bins * 2:
            self._calibration_map = None
            return

        predictions = np.array(self._predictions)
        outcomes = np.array(self._outcomes)

        sorted_idx = np.argsort(predictions)
        predictions = predictions[sorted_idx]
        outcomes = outcomes[sorted_idx]

        self._calibration_map = _isotonic_regression(outcomes)

    def calibrate(self, raw_confidence: float) -> float:
        """Map raw confidence to calibrated probability."""
        if self._calibration_map is None or len(self._predictions) < 20:
            return raw_confidence

        predictions = np.array(sorted(self._predictions))
        idx = np.searchsorted(predictions, raw_confidence)
        idx = min(idx, len(self._calibration_map) - 1)
        return float(self._calibration_map[idx])

    def calibration_error(self) -> float:
        """Compute Expected Calibration Error (ECE)."""
        if len(self._predictions) < self.n_bins:
            return 0.0

        predictions = np.array(self._predictions)
        outcomes = np.array(self._outcomes)

        bin_edges = np.linspace(0, 1, self.n_bins + 1)
        ece = 0.0
        total = len(predictions)

        for i in range(self.n_bins):
            mask = (predictions >= bin_edges[i]) & (predictions < bin_edges[i + 1])
            if np.sum(mask) == 0:
                continue
            bin_acc = np.mean(outcomes[mask])
            bin_conf = np.mean(predictions[mask])
            ece += np.sum(mask) / total * abs(bin_acc - bin_conf)

        return ece


def _isotonic_regression(y: np.ndarray) -> np.ndarray:
    """Pool Adjacent Violators algorithm for isotonic regression."""
    n = len(y)
    result = y.astype(float).copy()

    blocks = list(range(n))
    values = result.copy()
    weights = np.ones(n)

    i = 0
    while i < len(values) - 1:
        if values[i] > values[i + 1]:
            merged_value = (values[i] * weights[i] + values[i + 1] * weights[i + 1]) / (
                weights[i] + weights[i + 1]
            )
            merged_weight = weights[i] + weights[i + 1]
            values[i] = merged_value
            weights[i] = merged_weight
            values = np.delete(values, i + 1)
            weights = np.delete(weights, i + 1)

            while i > 0 and values[i - 1] > values[i]:
                merged_value = (values[i - 1] * weights[i - 1] + values[i] * weights[i]) / (
                    weights[i - 1] + weights[i]
                )
                merged_weight = weights[i - 1] + weights[i]
                values[i - 1] = merged_value
                weights[i - 1] = merged_weight
                values = np.delete(values, i)
                weights = np.delete(weights, i)
                i -= 1
        else:
            i += 1

    output = np.zeros(n)
    idx = 0
    for val, w in zip(values, weights):
        w_int = int(w)
        output[idx:idx + w_int] = val
        idx += w_int

    return output


# =============================================================================
# Alpha Decay Manager
# =============================================================================

class AlphaDecayManager:
    """
    Track and manage alpha decay across signals.

    Monitors the information coefficient (IC) of each signal over time
    and estimates the decay rate to predict when a signal will lose value.
    """

    def __init__(self, decay_window: int = 252):
        self.decay_window = decay_window
        self._ic_history: Dict[str, List[Tuple[datetime, float]]] = defaultdict(list)

    def record_ic(self, scan_name: str, ic: float, timestamp: Optional[datetime] = None):
        """Record an information coefficient observation."""
        ts = timestamp or datetime.now(timezone.utc)
        self._ic_history[scan_name].append((ts, ic))
        if len(self._ic_history[scan_name]) > self.decay_window:
            self._ic_history[scan_name] = self._ic_history[scan_name][-self.decay_window:]

    def estimate_halflife(self, scan_name: str) -> Optional[float]:
        """
        Estimate alpha decay halflife in days.

        Fits exponential decay: IC(t) = IC(0) * exp(-λt)
        Halflife = ln(2) / λ
        """
        history = self._ic_history.get(scan_name, [])
        if len(history) < 20:
            return None

        ics = np.array([ic for _, ic in history])
        n = len(ics)
        t = np.arange(n, dtype=float)

        abs_ics = np.abs(ics)
        abs_ics = np.maximum(abs_ics, 1e-10)
        log_ics = np.log(abs_ics)

        valid = np.isfinite(log_ics)
        if np.sum(valid) < 10:
            return None

        t_valid = t[valid]
        log_valid = log_ics[valid]

        n_valid = len(t_valid)
        t_mean = np.mean(t_valid)
        log_mean = np.mean(log_valid)

        numerator = np.sum((t_valid - t_mean) * (log_valid - log_mean))
        denominator = np.sum((t_valid - t_mean) ** 2)

        if abs(denominator) < 1e-10:
            return None

        slope = numerator / denominator  # This is -λ

        if slope >= 0:
            return None  # Not decaying

        lam = -slope
        halflife = np.log(2) / lam

        return max(1.0, halflife)

    def get_alpha_remaining(self, scan_name: str) -> float:
        """
        Estimate fraction of original alpha remaining.

        Returns value in [0, 1] where 1.0 = full alpha.
        """
        halflife = self.estimate_halflife(scan_name)
        if halflife is None:
            return 1.0

        history = self._ic_history.get(scan_name, [])
        if len(history) < 2:
            return 1.0

        elapsed = len(history)
        decay_factor = np.exp(-np.log(2) * elapsed / halflife)
        return float(np.clip(decay_factor, 0.0, 1.0))

    def should_retire(self, scan_name: str, threshold: float = 0.1) -> bool:
        """Check if signal should be retired (alpha exhausted)."""
        return self.get_alpha_remaining(scan_name) < threshold


# =============================================================================
# Bayesian Signal Combiner
# =============================================================================

class BayesianSignalCombiner:
    """
    Combine multiple scan signals using Bayesian Model Averaging.

    P(Y|D) = Σ_k P(Y|M_k, D) × P(M_k|D)

    where P(M_k|D) is the posterior model probability based on
    each scan's historical performance.
    """

    def __init__(self):
        self._model_performance: Dict[str, List[float]] = defaultdict(list)
        self._model_priors: Dict[str, float] = {}

    def update_performance(self, scan_name: str, log_likelihood: float):
        """Update model performance with new log-likelihood."""
        self._model_performance[scan_name].append(log_likelihood)
        if len(self._model_performance[scan_name]) > 500:
            self._model_performance[scan_name] = self._model_performance[scan_name][-500:]

    def set_prior(self, scan_name: str, prior: float):
        """Set prior probability for a model."""
        self._model_priors[scan_name] = prior

    def compute_posterior_weights(self) -> Dict[str, float]:
        """
        Compute posterior model probabilities.

        Uses BIC approximation: P(M_k|D) ∝ exp(-BIC_k/2) × P(M_k)
        """
        if not self._model_performance:
            return {}

        log_weights = {}
        for name, lls in self._model_performance.items():
            if not lls:
                continue
            avg_ll = np.mean(lls[-50:])
            prior = self._model_priors.get(name, 1.0 / len(self._model_performance))
            log_weights[name] = avg_ll + np.log(max(prior, 1e-10))

        if not log_weights:
            return {}

        max_log = max(log_weights.values())
        weights = {name: np.exp(lw - max_log) for name, lw in log_weights.items()}

        total = sum(weights.values())
        if total > 0:
            weights = {name: w / total for name, w in weights.items()}
        else:
            n = len(weights)
            weights = {name: 1.0 / n for name in weights}

        return weights

    def combine_signals(
        self,
        signals: Dict[str, Tuple[float, float]],  # scan_name -> (direction_score, confidence)
        weights: Optional[Dict[str, float]] = None,
    ) -> Tuple[float, float]:
        """
        Combine signals into a single direction score and confidence.

        Args:
            signals: Dict mapping scan name to (direction_score [-1,1], confidence [0,1])
            weights: Optional override weights

        Returns:
            (combined_direction_score, combined_confidence)
        """
        if not signals:
            return 0.0, 0.0

        if weights is None:
            weights = self.compute_posterior_weights()

        if not weights:
            weights = {name: 1.0 / len(signals) for name in signals}

        total_weight = 0.0
        weighted_direction = 0.0
        weighted_confidence = 0.0

        for name, (direction, confidence) in signals.items():
            w = weights.get(name, 0.0)
            weighted_direction += w * direction * confidence
            weighted_confidence += w * confidence
            total_weight += w

        if total_weight > 0:
            combined_direction = weighted_direction / total_weight
            combined_confidence = weighted_confidence / total_weight
        else:
            combined_direction = 0.0
            combined_confidence = 0.0

        return combined_direction, combined_confidence


# =============================================================================
# Composite Alpha Scanner
# =============================================================================

class CompositeAlphaScanner(BaseScanner):
    """
    The meta-scanner: combines all scan categories into unified
    high-conviction signals using Bayesian model averaging,
    adaptive weighting, and confidence calibration.

    This is Category J2 - the Composite Alpha Scanner that orchestrates
    the entire scanning intelligence system.
    """

    def __init__(self, config: Optional[ScannerConfig] = None):
        super().__init__(
            name="composite_alpha",
            scan_mode=ScanMode.ALL,
            config=config,
        )

        self.signal_combiner = BayesianSignalCombiner()
        self.calibrator = ConfidenceCalibrator()
        self.alpha_manager = AlphaDecayManager()
        self.correlation_analyzer = SignalCorrelationAnalyzer()

        self._registered_scanners: Dict[str, BaseScanner] = {}
        self._scan_results_buffer: Dict[str, List[ScanResult]] = defaultdict(list)
        self._min_confluence = 2

    def register_sub_scanner(self, scanner: BaseScanner):
        """Register a sub-scanner for composite analysis."""
        self._registered_scanners[scanner.name] = scanner
        self.signal_combiner.set_prior(scanner.name, 1.0 / max(1, len(self._registered_scanners)))

    async def scan(self, context: ScanContext) -> List[AdvancedScanResult]:
        """
        Run composite alpha scan across all registered sub-scanners.

        Aggregates signals per symbol, applies Bayesian weighting,
        calibrates confidence, and produces unified signals.
        """
        results: List[AdvancedScanResult] = []

        all_sub_results: Dict[str, List[Tuple[str, ScanResult]]] = defaultdict(list)

        for scanner_name, scanner in self._registered_scanners.items():
            try:
                sub_results, _ = await scanner.execute(context)
                for result in sub_results:
                    all_sub_results[result.symbol].append((scanner_name, result))
                    direction_score = 1.0 if result.direction == SignalDirection.LONG else (
                        -1.0 if result.direction == SignalDirection.SHORT else 0.0
                    )
                    self.correlation_analyzer.record_signal(
                        scanner_name, direction_score * result.confidence / 100.0
                    )
            except Exception as e:
                self._logger.warning(f"Sub-scanner {scanner_name} failed: {e}")

        redundancy_penalties = self.correlation_analyzer.get_redundancy_penalties()
        posterior_weights = self.signal_combiner.compute_posterior_weights()

        for symbol, scan_signals in all_sub_results.items():
            if len(scan_signals) < self._min_confluence:
                continue

            try:
                result = self._synthesize_signal(
                    symbol, scan_signals, posterior_weights,
                    redundancy_penalties, context
                )
                if result is not None:
                    results.append(result)
            except Exception as e:
                self._logger.warning(f"Signal synthesis failed for {symbol}: {e}")

        results.sort(key=lambda x: x.confidence, reverse=True)
        return results

    def _synthesize_signal(
        self,
        symbol: str,
        scan_signals: List[Tuple[str, ScanResult]],
        weights: Dict[str, float],
        redundancy_penalties: Dict[str, float],
        context: ScanContext,
    ) -> Optional[AdvancedScanResult]:
        """Synthesize a composite signal from multiple scan results."""
        signals_for_combiner: Dict[str, Tuple[float, float]] = {}
        supporting = []
        contradicting = []

        for scanner_name, result in scan_signals:
            direction_score = 1.0 if result.direction == SignalDirection.LONG else (
                -1.0 if result.direction == SignalDirection.SHORT else 0.0
            )
            confidence = result.confidence / 100.0

            alpha_remaining = self.alpha_manager.get_alpha_remaining(scanner_name)
            redundancy_pen = redundancy_penalties.get(scanner_name, 1.0)
            adjusted_confidence = confidence * alpha_remaining * redundancy_pen

            signals_for_combiner[scanner_name] = (direction_score, adjusted_confidence)

        combined_direction, combined_confidence = self.signal_combiner.combine_signals(
            signals_for_combiner, weights
        )

        if abs(combined_direction) < 0.1:
            return None

        if combined_direction > 0:
            signal_direction = "BULLISH"
            direction_enum = SignalDirection.LONG
        elif combined_direction < 0:
            signal_direction = "BEARISH"
            direction_enum = SignalDirection.SHORT
        else:
            return None

        for scanner_name, result in scan_signals:
            if result.direction == direction_enum:
                supporting.append(f"[{scanner_name}] conf={result.confidence:.0f}%")
            elif result.direction != SignalDirection.NEUTRAL:
                contradicting.append(f"[{scanner_name}] conf={result.confidence:.0f}%")

        calibrated_confidence = self.calibrator.calibrate(combined_confidence)
        calibrated_confidence = max(0.0, min(1.0, calibrated_confidence))

        if calibrated_confidence < 0.3:
            return None

        best_result = max(scan_signals, key=lambda x: x[1].confidence)[1]
        entry_price = best_result.entry_price
        stop_loss = best_result.stop_loss or 0.0
        targets = best_result.targets

        risk_reward = 0.0
        if entry_price and stop_loss and targets:
            risk = abs(entry_price - stop_loss)
            if risk > 0:
                reward = abs(targets[0] - entry_price)
                risk_reward = reward / risk

        regime = self._determine_regime(context)

        return AdvancedScanResult(
            scan_id=str(uuid.uuid4()),
            scan_name="Composite Alpha Signal",
            category=ScanCategory.PROPRIETARY,
            symbol=symbol,
            signal_direction=signal_direction,
            signal_strength=abs(combined_direction),
            confidence=calibrated_confidence,
            expected_move_pct=abs(combined_direction) * 5.0,
            expected_timeframe=ExpectedTimeframe.SWING,
            risk_reward_ratio=risk_reward,
            entry_price=entry_price,
            stop_loss_level=stop_loss,
            target_level=targets[0] if targets else 0.0,
            secondary_targets=targets[1:] if len(targets) > 1 else [],
            supporting_evidence=supporting,
            contradicting_evidence=contradicting,
            historical_accuracy=self.calibrator.calibration_error(),
            regime_context=regime,
            mathematical_basis=(
                f"Bayesian Model Average of {len(scan_signals)} scanners. "
                f"Posterior weights computed via BIC approximation. "
                f"Confidence calibrated via isotonic regression. "
                f"Redundancy-adjusted using Spearman correlation penalties."
            ),
            false_positive_rate=1.0 - calibrated_confidence,
            decay_halflife_days=0,
            information_coefficient=abs(combined_direction) * calibrated_confidence,
            signal_to_noise=abs(combined_direction) / max(0.01, 1.0 - abs(combined_direction)),
            transaction_cost_adjusted=False,
            metadata={
                "n_scanners": len(scan_signals),
                "n_supporting": len(supporting),
                "n_contradicting": len(contradicting),
                "posterior_weights": {k: round(v, 4) for k, v in weights.items() if k in dict(scan_signals).keys()} if weights else {},
                "raw_combined_direction": combined_direction,
                "raw_combined_confidence": combined_confidence,
            },
        )

    def _determine_regime(self, context: ScanContext) -> RegimeContext:
        """Map scan context regime to RegimeContext."""
        regime_map = {
            MarketRegime.TRENDING_UP: RegimeContext.TRENDING_UP,
            MarketRegime.TRENDING_DOWN: RegimeContext.TRENDING_DOWN,
            MarketRegime.RANGING: RegimeContext.RANGING,
            MarketRegime.HIGH_VOLATILITY: RegimeContext.VOLATILE,
            MarketRegime.LOW_VOLATILITY: RegimeContext.QUIET,
        }
        return regime_map.get(context.market_regime, RegimeContext.RANGING)

    def validate_signal(self, result, context: ScanContext) -> bool:
        """Validate composite signal."""
        if not isinstance(result, AdvancedScanResult):
            return False
        if result.confidence < 0.3:
            return False
        n_supporting = len(result.supporting_evidence)
        n_contradicting = len(result.contradicting_evidence)
        if n_contradicting >= n_supporting:
            return False
        return True
