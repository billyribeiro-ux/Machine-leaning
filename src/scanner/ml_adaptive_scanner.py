"""
Revolution Alpha Engine - Self-Learning Adaptive ML Framework

Institutional-grade adaptive scanning system that learns from its own
performance and dynamically adjusts scan weights, detects concept drift,
and combines signals via meta-learning ensembles.

Core components:
    - ConceptDriftDetector: ADWIN, Page-Hinkley, and CUSUM change-point detection
    - OnlineLearner: Online gradient descent with exponential weighting
    - ThompsonSamplingBandit: Multi-armed bandit for scan arm selection
    - ScanPerformanceMonitor: Rolling accuracy, Sharpe, and alpha decay tracking
    - EnsembleAdapter: Bayesian model averaging and Hedge algorithm
    - MetaLearner: Regime-scan performance matrix with few-shot adaptation
    - AdaptiveScannerFramework: Orchestrator extending BaseScanner

Mathematical foundations:
    - ADWIN: Bifet & Gavalda (2007) adaptive windowing
    - Page-Hinkley: Sequential change-point detection (Page 1954)
    - CUSUM: Cumulative sum control chart (Page 1961)
    - Thompson Sampling: Bayesian bandit (Thompson 1933)
    - Hedge / Exponential Weights: Freund & Schapire (1997)
    - Bayesian Model Averaging: Hoeting et al. (1999)
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy import stats as sp_stats

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
    ScanPerformanceTracker,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Numerical stability helpers
# ---------------------------------------------------------------------------

_EPS = 1e-15  # Machine-epsilon guard for divisions
_LOG_EPS = 1e-300  # Guard for log(0)


def _safe_div(numerator: float, denominator: float) -> float:
    """Division that returns 0.0 when the denominator is negligible."""
    if abs(denominator) < _EPS:
        return 0.0
    return numerator / denominator


def _safe_log(x: float) -> float:
    """Logarithm guarded against log(0)."""
    return np.log(max(x, _LOG_EPS))


def _softmax(x: np.ndarray) -> np.ndarray:
    """Numerically stable softmax."""
    shifted = x - np.max(x)
    exp_x = np.exp(shifted)
    return exp_x / (np.sum(exp_x) + _EPS)


# ============================================================================
# 1. ConceptDriftDetector
# ============================================================================

class ConceptDriftDetector:
    """
    Detects distributional shifts (concept drift) in streaming data.

    Implements three classical change-point detection algorithms used in
    online learning to determine when a scanner's predictive distribution
    has shifted and retraining / weight adjustment is warranted.
    """

    # ------------------------------------------------------------------
    # ADWIN  (Adaptive Windowing)
    # ------------------------------------------------------------------

    @staticmethod
    def adwin(
        stream: np.ndarray,
        delta: float = 0.002,
    ) -> Tuple[bool, int, float]:
        """
        ADWIN (Adaptive Windowing) drift detector.

        Maintains a variable-length window of recent observations. At each
        step the window is partitioned into two sub-windows and a
        statistical test checks whether their means differ significantly.
        When drift is detected the window shrinks to the most recent
        segment.

        Parameters
        ----------
        stream : np.ndarray
            1-D array of sequential observations (e.g. rolling accuracy).
        delta : float, optional
            Confidence parameter for the Hoeffding bound (default 0.002).
            Smaller values make the test more conservative.

        Returns
        -------
        drift_detected : bool
            True if a statistically significant distributional change was
            found anywhere in *stream*.
        drift_point : int
            Index in *stream* where the drift was detected (-1 if none).
        magnitude : float
            Absolute difference in sub-window means at the drift point
            (0.0 if no drift).
        """
        stream = np.asarray(stream, dtype=np.float64)
        n = len(stream)

        if n < 4:
            return False, -1, 0.0

        best_drift_point = -1
        best_magnitude = 0.0

        # Slide a cut point through the window and test each partition.
        for cut in range(2, n - 1):
            left = stream[:cut]
            right = stream[cut:]

            n_left = len(left)
            n_right = len(right)
            n_total = n_left + n_right

            mean_left = np.mean(left)
            mean_right = np.mean(right)
            diff = abs(mean_left - mean_right)

            # Hoeffding-style bound for bounded [0, 1] random variables.
            # For unbounded data we normalise to [0, 1] using the window
            # range, falling back to the raw Hoeffding bound when the
            # range is negligible.
            m = 1.0 / (1.0 / n_left + 1.0 / n_right)
            range_val = np.ptp(stream)
            if range_val < _EPS:
                # Constant stream -- no drift possible.
                continue
            normalised_diff = diff / range_val

            epsilon_cut = np.sqrt(
                (1.0 / (2.0 * m)) * _safe_log(4.0 * n_total / delta)
            )

            if normalised_diff >= epsilon_cut and diff > best_magnitude:
                best_magnitude = diff
                best_drift_point = cut

        drift_detected = best_drift_point >= 0
        return drift_detected, best_drift_point, best_magnitude

    # ------------------------------------------------------------------
    # Page-Hinkley test
    # ------------------------------------------------------------------

    @staticmethod
    def page_hinkley(
        stream: np.ndarray,
        delta: float = 0.005,
        threshold: float = 50.0,
    ) -> Tuple[bool, int]:
        """
        Page-Hinkley change-point detection test.

        A cumulative-sum method that monitors the deviation of
        observations from their running mean. An alarm is raised when
        the monitored statistic exceeds *threshold*.

        Parameters
        ----------
        stream : np.ndarray
            1-D array of sequential observations.
        delta : float, optional
            Magnitude tolerance; observations must deviate by more than
            *delta* from the running mean to accumulate evidence
            (default 0.005).
        threshold : float, optional
            Alarm threshold for the Page-Hinkley statistic (default 50).

        Returns
        -------
        alarm : bool
            True if the test triggers an alarm.
        alarm_point : int
            Index where the alarm was first raised (-1 if no alarm).
        """
        stream = np.asarray(stream, dtype=np.float64)
        n = len(stream)

        if n < 2:
            return False, -1

        cumulative_sum = 0.0
        running_sum = 0.0
        min_cumulative = 0.0

        for t in range(n):
            running_sum += stream[t]
            running_mean = running_sum / (t + 1)

            cumulative_sum += stream[t] - running_mean - delta
            min_cumulative = min(min_cumulative, cumulative_sum)

            ph_statistic = cumulative_sum - min_cumulative
            if ph_statistic > threshold:
                return True, t

        return False, -1

    # ------------------------------------------------------------------
    # CUSUM (Cumulative Sum)
    # ------------------------------------------------------------------

    @staticmethod
    def cusum(
        stream: np.ndarray,
        threshold: float = 5.0,
        drift: float = 0.0,
    ) -> Tuple[bool, int, str]:
        """
        CUSUM (Cumulative Sum) change-point detection.

        Tracks two one-sided cumulative sums (positive and negative
        deviations from the target mean). Signals when either sum
        exceeds *threshold*.

        Parameters
        ----------
        stream : np.ndarray
            1-D array of sequential observations.
        threshold : float, optional
            Decision threshold for the cumulative sums (default 5).
        drift : float, optional
            Known or estimated mean of the in-control process.  When 0
            (default), the grand mean of *stream* is used as reference.

        Returns
        -------
        alarm : bool
            True if either cumulative sum breaches the threshold.
        alarm_point : int
            First index at which the threshold was exceeded (-1 if none).
        direction : str
            ``"positive"`` if the upward CUSUM triggered, ``"negative"``
            if the downward CUSUM triggered, or ``""`` if no alarm.
        """
        stream = np.asarray(stream, dtype=np.float64)
        n = len(stream)

        if n < 2:
            return False, -1, ""

        target = drift if drift != 0.0 else np.mean(stream)

        s_pos = 0.0  # Upward CUSUM
        s_neg = 0.0  # Downward CUSUM

        for t in range(n):
            deviation = stream[t] - target
            s_pos = max(0.0, s_pos + deviation)
            s_neg = max(0.0, s_neg - deviation)

            if s_pos > threshold:
                return True, t, "positive"
            if s_neg > threshold:
                return True, t, "negative"

        return False, -1, ""


# ============================================================================
# 2. OnlineLearner
# ============================================================================

class OnlineLearner:
    """
    Online (streaming) linear learner using stochastic gradient descent.

    Suitable for continuously updating a predictive model as new market
    observations arrive, without storing the full dataset in memory.

    Attributes
    ----------
    n_features : int
        Dimensionality of the feature space.
    weights : np.ndarray
        Current weight vector of shape ``(n_features,)``.
    bias : float
        Intercept term.
    l2_lambda : float
        L2 regularisation coefficient.
    n_updates : int
        Total number of gradient updates applied so far.
    """

    def __init__(
        self,
        n_features: int,
        learning_rate: float = 0.01,
        l2_lambda: float = 1e-4,
    ):
        """
        Parameters
        ----------
        n_features : int
            Number of input features.
        learning_rate : float
            Base learning rate for SGD (default 0.01).
        l2_lambda : float
            L2 regularisation strength (default 1e-4).
        """
        self.n_features = n_features
        self.learning_rate = learning_rate
        self.l2_lambda = l2_lambda

        # Initialise weights near zero with small random perturbation for
        # symmetry breaking.
        rng = np.random.default_rng(42)
        self.weights: np.ndarray = rng.normal(0, 0.01, size=n_features)
        self.bias: float = 0.0

        self.n_updates: int = 0
        self._exp_accuracy: float = 0.5  # Exponentially weighted accuracy

        # Running statistics for feature normalisation (Welford's algorithm).
        self._running_mean = np.zeros(n_features, dtype=np.float64)
        self._running_var = np.ones(n_features, dtype=np.float64)
        self._running_count: int = 0

    # ------------------------------------------------------------------
    # Core SGD update
    # ------------------------------------------------------------------

    def online_gradient_descent(
        self,
        features: np.ndarray,
        target: float,
        learning_rate: Optional[float] = None,
    ) -> float:
        """
        Perform a single SGD weight update.

        Uses MSE loss:  L = 0.5 * (prediction - target)^2

        Update rule with L2 regularisation::

            w <- w - lr * (grad + lambda * w)
            b <- b - lr * error

        Parameters
        ----------
        features : np.ndarray
            Feature vector of shape ``(n_features,)``.
        target : float
            True label / target value.
        learning_rate : float, optional
            Override the base learning rate for this step.

        Returns
        -------
        loss : float
            MSE loss *before* the update (for monitoring).
        """
        features = np.asarray(features, dtype=np.float64).ravel()
        if features.shape[0] != self.n_features:
            raise ValueError(
                f"Expected {self.n_features} features, got {features.shape[0]}"
            )

        lr = learning_rate if learning_rate is not None else self.learning_rate

        # Adaptive learning rate: decay by 1/sqrt(t+1) to satisfy
        # Robbins-Monro conditions.
        effective_lr = lr / np.sqrt(self.n_updates + 1)

        # Normalise features using running stats.
        features_normed = self._normalise(features)

        # Forward pass.
        prediction = float(np.dot(self.weights, features_normed) + self.bias)
        error = prediction - target
        loss = 0.5 * error ** 2

        # Gradient of MSE + L2.
        grad_w = error * features_normed + self.l2_lambda * self.weights
        grad_b = error

        # Update.
        self.weights -= effective_lr * grad_w
        self.bias -= effective_lr * grad_b

        self.n_updates += 1
        self._update_running_stats(features)

        return loss

    # ------------------------------------------------------------------
    # Exponentially weighted accuracy
    # ------------------------------------------------------------------

    def exponential_weighting(
        self,
        predictions: np.ndarray,
        actuals: np.ndarray,
        decay: float = 0.95,
    ) -> float:
        """
        Compute exponentially weighted accuracy over a history of predictions.

        More recent predictions are weighted more heavily.

        Parameters
        ----------
        predictions : np.ndarray
            Array of predicted values (or binary 0/1 correct flags).
        actuals : np.ndarray
            Array of actual values (same length as *predictions*).
        decay : float
            Decay factor in (0, 1). Closer to 1 gives more weight to
            older observations; closer to 0 emphasises recent ones.

        Returns
        -------
        ewa : float
            Exponentially weighted accuracy in [0, 1].
        """
        predictions = np.asarray(predictions, dtype=np.float64)
        actuals = np.asarray(actuals, dtype=np.float64)
        n = len(predictions)

        if n == 0:
            return 0.5  # Uninformative prior

        # Binary correctness: prediction within tolerance of actual.
        # For continuous targets, use a tolerance of 1% of the actual's
        # absolute value (minimum tolerance 0.01).
        tolerance = np.maximum(np.abs(actuals) * 0.01, 0.01)
        correct = (np.abs(predictions - actuals) <= tolerance).astype(np.float64)

        # Exponential weights (most recent observation at index n-1).
        indices = np.arange(n, dtype=np.float64)
        weights = decay ** (n - 1 - indices)
        total_weight = np.sum(weights)

        if total_weight < _EPS:
            return 0.5

        ewa = float(np.dot(weights, correct) / total_weight)
        self._exp_accuracy = ewa
        return ewa

    # ------------------------------------------------------------------
    # High-level convenience API
    # ------------------------------------------------------------------

    def update(self, new_data_point: Dict[str, Any]) -> float:
        """
        Process a single new observation.

        Expects a dict with keys ``"features"`` (array-like) and
        ``"target"`` (float).

        Parameters
        ----------
        new_data_point : dict
            Must contain ``features`` and ``target``.

        Returns
        -------
        loss : float
            Loss for this observation.
        """
        features = np.asarray(new_data_point["features"], dtype=np.float64)
        target = float(new_data_point["target"])
        return self.online_gradient_descent(features, target)

    def predict(self, features: np.ndarray) -> float:
        """
        Make a prediction with the current weight vector.

        Parameters
        ----------
        features : np.ndarray
            Feature vector of shape ``(n_features,)``.

        Returns
        -------
        prediction : float
        """
        features = np.asarray(features, dtype=np.float64).ravel()
        if features.shape[0] != self.n_features:
            raise ValueError(
                f"Expected {self.n_features} features, got {features.shape[0]}"
            )
        features_normed = self._normalise(features)
        return float(np.dot(self.weights, features_normed) + self.bias)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _normalise(self, features: np.ndarray) -> np.ndarray:
        """Standardise features using Welford running mean/var."""
        std = np.sqrt(self._running_var + _EPS)
        return (features - self._running_mean) / std

    def _update_running_stats(self, features: np.ndarray) -> None:
        """Welford online update for mean and variance."""
        self._running_count += 1
        n = self._running_count
        delta = features - self._running_mean
        self._running_mean += delta / n
        delta2 = features - self._running_mean
        self._running_var = (
            (self._running_var * (n - 1) + delta * delta2) / n
        )


# ============================================================================
# 3. ThompsonSamplingBandit
# ============================================================================

class ThompsonSamplingBandit:
    """
    Multi-armed bandit using Thompson Sampling with Beta-Bernoulli priors.

    Each *arm* represents a registered scanner. The bandit selects arms
    (scanners) to emphasise based on their posterior success probability,
    balancing exploration and exploitation.

    Attributes
    ----------
    n_arms : int
        Number of arms (scanners).
    alphas : np.ndarray
        Alpha parameters of the Beta distributions (successes + 1).
    betas : np.ndarray
        Beta parameters of the Beta distributions (failures + 1).
    """

    def __init__(self, n_arms: int):
        """
        Initialise with uniform Beta(1,1) priors for each arm.

        Parameters
        ----------
        n_arms : int
            Number of bandit arms.
        """
        if n_arms < 1:
            raise ValueError("n_arms must be >= 1")

        self.n_arms = n_arms
        self.alphas = np.ones(n_arms, dtype=np.float64)  # successes + 1
        self.betas = np.ones(n_arms, dtype=np.float64)   # failures + 1
        self._rng = np.random.default_rng()
        self._total_pulls: np.ndarray = np.zeros(n_arms, dtype=np.int64)

    def select_arm(self) -> int:
        """
        Select an arm via Thompson Sampling.

        Sample from each arm's Beta posterior and return the arm with
        the highest sample.

        Returns
        -------
        arm : int
            Index of the selected arm.
        """
        samples = self._rng.beta(self.alphas, self.betas)
        return int(np.argmax(samples))

    def update(self, arm: int, reward: float) -> None:
        """
        Update the Beta posterior for *arm* given a reward.

        Parameters
        ----------
        arm : int
            Index of the pulled arm.
        reward : float
            Observed reward. Interpreted as a Bernoulli outcome:
            reward > 0.5 counts as a success, otherwise failure.
            Fractional rewards are supported via proportional updates.
        """
        if arm < 0 or arm >= self.n_arms:
            raise IndexError(f"arm {arm} out of range [0, {self.n_arms})")

        # Clip reward to [0, 1] for valid Beta updates.
        reward = float(np.clip(reward, 0.0, 1.0))

        self.alphas[arm] += reward
        self.betas[arm] += 1.0 - reward
        self._total_pulls[arm] += 1

    def get_arm_stats(self) -> List[Dict[str, float]]:
        """
        Return current statistics for every arm.

        Returns
        -------
        stats : list[dict]
            Each dict contains ``alpha``, ``beta``, ``expected_value``,
            ``total_pulls``, and ``uncertainty`` (posterior std dev).
        """
        stats: List[Dict[str, float]] = []
        for i in range(self.n_arms):
            a, b = self.alphas[i], self.betas[i]
            ev = _safe_div(a, a + b)
            var = _safe_div(a * b, (a + b) ** 2 * (a + b + 1))
            stats.append({
                "alpha": float(a),
                "beta": float(b),
                "expected_value": float(ev),
                "total_pulls": int(self._total_pulls[i]),
                "uncertainty": float(np.sqrt(var)),
            })
        return stats


# ============================================================================
# 4. ScanPerformanceMonitor
# ============================================================================

class ScanPerformanceMonitor:
    """
    Tracks the live performance of each registered scanner over time.

    Records signal predictions against realised outcomes and computes
    rolling accuracy, rolling Sharpe, alpha decay, and dynamic weights.
    """

    def __init__(self, min_observations: int = 30):
        """
        Parameters
        ----------
        min_observations : int
            Minimum number of recorded signals before performance
            statistics are considered reliable (default 30).
        """
        self.min_observations = min_observations

        # scan_name -> list of (prediction, actual) tuples
        self._records: Dict[str, List[Tuple[float, float]]] = defaultdict(list)
        # scan_name -> list of datetime stamps
        self._timestamps: Dict[str, List[datetime]] = defaultdict(list)
        # scan_name -> retired flag
        self._retired: Dict[str, bool] = defaultdict(lambda: False)
        # scan_name -> regime -> list of (prediction, actual)
        self._regime_records: Dict[str, Dict[str, List[Tuple[float, float]]]] = (
            defaultdict(lambda: defaultdict(list))
        )

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_signal(
        self,
        scan_name: str,
        prediction: float,
        actual_outcome: float,
        regime: Optional[str] = None,
    ) -> None:
        """
        Record a signal prediction and its realised outcome.

        Parameters
        ----------
        scan_name : str
            Name of the scanner that produced the signal.
        prediction : float
            Predicted value (e.g. expected return direction +1/-1 or
            expected return magnitude).
        actual_outcome : float
            Realised value corresponding to the prediction.
        regime : str, optional
            Market regime label at the time the signal was generated.
        """
        self._records[scan_name].append((prediction, actual_outcome))
        self._timestamps[scan_name].append(datetime.now(timezone.utc))
        if regime is not None:
            self._regime_records[scan_name][regime].append(
                (prediction, actual_outcome)
            )

    # ------------------------------------------------------------------
    # Rolling accuracy
    # ------------------------------------------------------------------

    def get_rolling_accuracy(
        self,
        scan_name: str,
        window: int = 100,
    ) -> float:
        """
        Compute the rolling hit rate over the most recent *window*
        observations.

        A signal is considered *correct* when prediction and actual
        have the same sign (both positive or both negative).

        Parameters
        ----------
        scan_name : str
        window : int

        Returns
        -------
        accuracy : float
            Rolling accuracy in [0, 1] (0.5 returned during cold start).
        """
        records = self._records.get(scan_name, [])
        if len(records) < self.min_observations:
            return 0.5  # Uninformative prior during cold start

        recent = records[-window:]
        correct = sum(
            1 for pred, actual in recent
            if (pred > 0 and actual > 0) or (pred < 0 and actual < 0) or
               (pred == 0 and actual == 0)
        )
        return _safe_div(correct, len(recent))

    # ------------------------------------------------------------------
    # Rolling Sharpe
    # ------------------------------------------------------------------

    def get_rolling_sharpe(
        self,
        scan_name: str,
        returns: np.ndarray,
        window: int = 252,
    ) -> float:
        """
        Compute an annualised rolling Sharpe ratio.

        Parameters
        ----------
        scan_name : str
            Scanner name (used only for logging / bookkeeping).
        returns : np.ndarray
            1-D array of period returns attributed to this scanner.
        window : int
            Look-back window in periods (default 252 for daily data).

        Returns
        -------
        sharpe : float
            Annualised Sharpe ratio (0.0 during cold start).
        """
        returns = np.asarray(returns, dtype=np.float64)
        if len(returns) < self.min_observations:
            return 0.0

        recent = returns[-window:]
        mu = np.mean(recent)
        sigma = np.std(recent, ddof=1)

        if sigma < _EPS:
            return 0.0

        # Annualise assuming daily periods.
        return float((mu / sigma) * np.sqrt(252))

    # ------------------------------------------------------------------
    # Alpha decay detection
    # ------------------------------------------------------------------

    def detect_alpha_decay(self, scan_name: str) -> Dict[str, Any]:
        """
        Detect whether a scanner's signal is losing predictive power.

        Compares the hit rate in the first half of the observation
        history against the second half. A statistically significant
        decline (one-tailed z-test at 5% level) indicates alpha decay.

        Parameters
        ----------
        scan_name : str

        Returns
        -------
        result : dict
            Keys: ``decay_detected`` (bool), ``first_half_accuracy``,
            ``second_half_accuracy``, ``p_value``, ``magnitude``.
        """
        records = self._records.get(scan_name, [])

        if len(records) < self.min_observations * 2:
            return {
                "decay_detected": False,
                "first_half_accuracy": 0.5,
                "second_half_accuracy": 0.5,
                "p_value": 1.0,
                "magnitude": 0.0,
            }

        mid = len(records) // 2
        first_half = records[:mid]
        second_half = records[mid:]

        def _hit_rate(recs: list) -> float:
            correct = sum(
                1 for p, a in recs
                if (p > 0 and a > 0) or (p < 0 and a < 0)
            )
            return _safe_div(correct, len(recs))

        acc1 = _hit_rate(first_half)
        acc2 = _hit_rate(second_half)
        n1 = len(first_half)
        n2 = len(second_half)

        # Pooled two-proportion z-test (one-tailed: acc1 > acc2).
        pooled = _safe_div(acc1 * n1 + acc2 * n2, n1 + n2)
        se = np.sqrt(pooled * (1 - pooled) * (1.0 / n1 + 1.0 / n2) + _EPS)
        z = _safe_div(acc1 - acc2, se)

        # One-tailed p-value (testing if first half > second half).
        p_value = float(1.0 - sp_stats.norm.cdf(z))

        decay_detected = p_value < 0.05 and acc1 > acc2

        return {
            "decay_detected": decay_detected,
            "first_half_accuracy": acc1,
            "second_half_accuracy": acc2,
            "p_value": p_value,
            "magnitude": acc1 - acc2,
        }

    # ------------------------------------------------------------------
    # Dynamic weight
    # ------------------------------------------------------------------

    def get_effective_weight(
        self,
        scan_name: str,
        regime: str,
    ) -> float:
        """
        Compute a dynamic weight for *scan_name* given the current
        market regime.

        The weight combines three components:
        1. Rolling accuracy (performance component)
        2. Regime-specific accuracy (regime component)
        3. Alpha-remaining factor (decay component)

        Parameters
        ----------
        scan_name : str
        regime : str
            Current market regime label.

        Returns
        -------
        weight : float
            Effective weight in (0, 2], with 1.0 being the neutral
            baseline.
        """
        if self._retired.get(scan_name, False):
            return 0.0

        # 1. Performance component: rolling accuracy rescaled.
        rolling_acc = self.get_rolling_accuracy(scan_name)
        perf_component = rolling_acc / 0.5  # 1.0 at 50% accuracy, 2.0 at 100%

        # 2. Regime component.
        regime_recs = self._regime_records.get(scan_name, {}).get(regime, [])
        if len(regime_recs) >= self.min_observations:
            correct = sum(
                1 for p, a in regime_recs
                if (p > 0 and a > 0) or (p < 0 and a < 0)
            )
            regime_acc = _safe_div(correct, len(regime_recs))
        else:
            regime_acc = 0.5  # Uninformative
        regime_component = regime_acc / 0.5

        # 3. Decay component.
        decay_info = self.detect_alpha_decay(scan_name)
        if decay_info["decay_detected"]:
            alpha_remaining = max(0.1, 1.0 - decay_info["magnitude"])
        else:
            alpha_remaining = 1.0

        weight = perf_component * 0.4 + regime_component * 0.4 + alpha_remaining * 0.2
        return float(np.clip(weight, 0.0, 2.0))

    # ------------------------------------------------------------------
    # Retirement
    # ------------------------------------------------------------------

    def retire_scan(self, scan_name: str) -> Dict[str, Any]:
        """
        Flag a scanner for retirement if it is consistently
        underperforming.

        Retirement criteria (all must hold):
        - At least ``2 * min_observations`` signals recorded.
        - Rolling accuracy below 45%.
        - Alpha decay detected.

        Parameters
        ----------
        scan_name : str

        Returns
        -------
        result : dict
            ``retired`` (bool), ``reason`` (str), ``final_accuracy``.
        """
        records = self._records.get(scan_name, [])
        rolling_acc = self.get_rolling_accuracy(scan_name)
        decay_info = self.detect_alpha_decay(scan_name)

        reasons: List[str] = []

        if len(records) < self.min_observations * 2:
            return {
                "retired": False,
                "reason": "insufficient data for retirement decision",
                "final_accuracy": rolling_acc,
            }

        if rolling_acc < 0.45:
            reasons.append(f"rolling accuracy {rolling_acc:.3f} < 0.45")

        if decay_info["decay_detected"]:
            reasons.append(
                f"alpha decay detected (magnitude {decay_info['magnitude']:.3f})"
            )

        should_retire = len(reasons) >= 2
        if should_retire:
            self._retired[scan_name] = True

        return {
            "retired": should_retire,
            "reason": "; ".join(reasons) if reasons else "performance acceptable",
            "final_accuracy": rolling_acc,
        }


# ============================================================================
# 5. EnsembleAdapter
# ============================================================================

class EnsembleAdapter:
    """
    Dynamically combines scan signals using adaptive weighting.

    Implements Bayesian Model Averaging and the Hedge (exponential
    weight) algorithm for online aggregation of heterogeneous scanner
    outputs.
    """

    def __init__(self, n_models: int):
        """
        Parameters
        ----------
        n_models : int
            Number of models (scanners) in the ensemble.
        """
        self.n_models = n_models
        # Uniform initial weights.
        self.weights = np.ones(n_models, dtype=np.float64) / max(n_models, 1)
        # Loss history per model (list of floats per model index).
        self._loss_history: List[List[float]] = [[] for _ in range(n_models)]
        self._cumulative_loss = np.zeros(n_models, dtype=np.float64)

    # ------------------------------------------------------------------
    # Bayesian Model Averaging
    # ------------------------------------------------------------------

    def bayesian_model_average(
        self,
        predictions: np.ndarray,
        weights: Optional[np.ndarray] = None,
        prior_accuracy: Optional[np.ndarray] = None,
    ) -> float:
        """
        Bayesian Model Averaging.

        Posterior weight of model k:
            P(M_k | D) proportional to P(D | M_k) * P(M_k)

        Combined prediction:
            sum_k  w_k * prediction_k

        Parameters
        ----------
        predictions : np.ndarray
            Prediction from each model, shape ``(n_models,)``.
        weights : np.ndarray, optional
            Prior weights. Uses internal weights if not provided.
        prior_accuracy : np.ndarray, optional
            Historical accuracy of each model (used as likelihood
            proxy).  If not provided, uniform likelihoods are assumed.

        Returns
        -------
        combined : float
            BMA combined prediction.
        """
        predictions = np.asarray(predictions, dtype=np.float64)
        n = len(predictions)

        if n == 0:
            return 0.0

        if weights is None:
            w = self.weights[:n].copy()
        else:
            w = np.asarray(weights, dtype=np.float64)[:n]

        # Likelihood proxy from historical accuracy.
        if prior_accuracy is not None:
            likelihood = np.asarray(prior_accuracy, dtype=np.float64)[:n]
            # Avoid zero likelihoods.
            likelihood = np.clip(likelihood, _EPS, 1.0)
        else:
            likelihood = np.ones(n, dtype=np.float64)

        # Posterior proportional to prior * likelihood.
        posterior = w * likelihood
        total = np.sum(posterior)
        if total < _EPS:
            posterior = np.ones(n, dtype=np.float64) / n
        else:
            posterior /= total

        return float(np.dot(posterior, predictions))

    # ------------------------------------------------------------------
    # Hedge / Exponential Weights
    # ------------------------------------------------------------------

    def exponential_weight_average(
        self,
        predictions: np.ndarray,
        losses: np.ndarray,
        eta: float = 0.1,
    ) -> float:
        """
        Hedge algorithm (exponential weight update).

        Update rule::

            w_k(t+1) = w_k(t) * exp(-eta * loss_k(t)) / Z

        where Z is the normalisation constant.

        Parameters
        ----------
        predictions : np.ndarray
            Predictions from each model, shape ``(n_models,)``.
        losses : np.ndarray
            Loss of each model for the *current* round, shape
            ``(n_models,)``.
        eta : float
            Learning rate / temperature parameter (default 0.1).

        Returns
        -------
        combined : float
            Weighted combination of predictions using the *updated*
            weights.
        """
        predictions = np.asarray(predictions, dtype=np.float64)
        losses = np.asarray(losses, dtype=np.float64)
        n = min(len(predictions), self.n_models)

        if n == 0:
            return 0.0

        # Multiplicative weight update (numerically stable).
        log_weights = np.log(self.weights[:n] + _EPS) - eta * losses[:n]
        # Normalise in log-space.
        log_weights -= np.max(log_weights)  # shift for stability
        new_weights = np.exp(log_weights)
        total = np.sum(new_weights)
        if total < _EPS:
            new_weights = np.ones(n, dtype=np.float64) / n
        else:
            new_weights /= total

        self.weights[:n] = new_weights

        # Record losses.
        for i in range(n):
            self._loss_history[i].append(float(losses[i]))
            self._cumulative_loss[i] += float(losses[i])

        return float(np.dot(new_weights, predictions[:n]))

    # ------------------------------------------------------------------
    # Weight update from outcomes
    # ------------------------------------------------------------------

    def update_weights(
        self,
        actual_outcomes: np.ndarray,
        predictions: Optional[np.ndarray] = None,
        eta: float = 0.1,
    ) -> np.ndarray:
        """
        Update ensemble weights based on realised outcomes.

        If *predictions* are provided, per-model losses are computed as
        squared error. Otherwise, only the cumulative loss history is
        used for re-normalisation.

        Parameters
        ----------
        actual_outcomes : np.ndarray
            True outcomes (1-D array with one entry per model's last
            predicted instance, or a scalar broadcast to all models).
        predictions : np.ndarray, optional
            Predictions that each model made, shape ``(n_models,)``.
        eta : float
            Learning rate for exponential weight update.

        Returns
        -------
        updated_weights : np.ndarray
            New weight vector of shape ``(n_models,)``.
        """
        actual_outcomes = np.asarray(actual_outcomes, dtype=np.float64)

        if predictions is not None:
            predictions = np.asarray(predictions, dtype=np.float64)
            n = min(len(predictions), self.n_models)
            # Per-model squared error loss.
            if actual_outcomes.ndim == 0:
                actual_outcomes = np.full(n, float(actual_outcomes))
            losses = (predictions[:n] - actual_outcomes[:n]) ** 2
        else:
            n = self.n_models
            # Fallback: use inverse cumulative loss for re-weighting.
            inv_loss = 1.0 / (self._cumulative_loss[:n] + 1.0)
            self.weights[:n] = inv_loss / (np.sum(inv_loss) + _EPS)
            return self.weights.copy()

        # Hedge-style multiplicative update.
        log_weights = np.log(self.weights[:n] + _EPS) - eta * losses
        log_weights -= np.max(log_weights)
        new_weights = np.exp(log_weights)
        total = np.sum(new_weights)
        if total < _EPS:
            new_weights = np.ones(n, dtype=np.float64) / n
        else:
            new_weights /= total

        self.weights[:n] = new_weights

        for i in range(n):
            self._loss_history[i].append(float(losses[i]))
            self._cumulative_loss[i] += float(losses[i])

        return self.weights.copy()


# ============================================================================
# 6. MetaLearner
# ============================================================================

class MetaLearner:
    """
    Learns which scanners work best in which market regimes.

    Maintains a regime-scan performance matrix and provides optimal
    scan allocations conditioned on the current regime. Supports
    few-shot adaptation for novel or transitional regimes.

    Attributes
    ----------
    n_scans : int
        Number of registered scanners.
    n_regimes : int
        Number of distinct market regimes.
    performance_matrix : np.ndarray
        Shape ``(n_regimes, n_scans)`` tracking the running mean
        performance of each scanner within each regime.
    count_matrix : np.ndarray
        Same shape, tracking the number of observations per cell.
    """

    def __init__(self, n_scans: int, n_regimes: int):
        """
        Parameters
        ----------
        n_scans : int
            Number of scanners.
        n_regimes : int
            Number of market regimes.
        """
        if n_scans < 1 or n_regimes < 1:
            raise ValueError("n_scans and n_regimes must be >= 1")

        self.n_scans = n_scans
        self.n_regimes = n_regimes

        # Initialise with optimistic prior (0.5 accuracy for all cells).
        self.performance_matrix = np.full(
            (n_regimes, n_scans), 0.5, dtype=np.float64
        )
        self.count_matrix = np.ones(
            (n_regimes, n_scans), dtype=np.float64
        )

        # Variance matrix for UCB-style exploration bonus.
        self._m2_matrix = np.zeros(
            (n_regimes, n_scans), dtype=np.float64
        )

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(
        self,
        regime: int,
        scan_performances: np.ndarray,
    ) -> None:
        """
        Update the performance matrix with a new vector of scan results
        for a given regime.

        Uses Welford's online mean/variance algorithm per cell.

        Parameters
        ----------
        regime : int
            Index of the market regime (0-indexed).
        scan_performances : np.ndarray
            Performance score for each scanner, shape ``(n_scans,)``.
            Values should be in [0, 1] (e.g. accuracy).
        """
        scan_performances = np.asarray(scan_performances, dtype=np.float64)

        if regime < 0 or regime >= self.n_regimes:
            logger.warning(
                "MetaLearner.update: regime %d out of range [0, %d)",
                regime, self.n_regimes,
            )
            return

        n_perf = min(len(scan_performances), self.n_scans)

        for s in range(n_perf):
            x = scan_performances[s]
            n = self.count_matrix[regime, s]
            old_mean = self.performance_matrix[regime, s]
            new_count = n + 1
            delta = x - old_mean
            new_mean = old_mean + delta / new_count
            delta2 = x - new_mean
            self._m2_matrix[regime, s] += delta * delta2
            self.performance_matrix[regime, s] = new_mean
            self.count_matrix[regime, s] = new_count

    # ------------------------------------------------------------------
    # Allocation
    # ------------------------------------------------------------------

    def get_scan_allocation(
        self,
        current_regime: int,
        exploration_bonus: float = 0.1,
    ) -> np.ndarray:
        """
        Return optimal scan weight allocation for the current regime.

        Uses a softmax over performance scores plus a UCB-style
        exploration bonus for under-sampled scanner-regime pairs.

        Parameters
        ----------
        current_regime : int
            Index of the current market regime.
        exploration_bonus : float
            Scale of the exploration bonus (default 0.1).

        Returns
        -------
        weights : np.ndarray
            Normalised scan weights summing to 1, shape ``(n_scans,)``.
        """
        if current_regime < 0 or current_regime >= self.n_regimes:
            # Fallback: uniform
            return np.ones(self.n_scans, dtype=np.float64) / self.n_scans

        perf = self.performance_matrix[current_regime].copy()
        counts = self.count_matrix[current_regime]

        # UCB exploration term: c * sqrt(ln(total) / n_i).
        total_counts = np.sum(counts)
        ucb = exploration_bonus * np.sqrt(
            _safe_log(total_counts + 1.0) / (counts + _EPS)
        )

        scores = perf + ucb
        return _softmax(scores * 5.0)  # Temperature-scaled softmax

    # ------------------------------------------------------------------
    # Few-shot adaptation
    # ------------------------------------------------------------------

    def few_shot_adapt(
        self,
        new_regime_data: List[np.ndarray],
        n_shots: int = 10,
    ) -> np.ndarray:
        """
        Quickly adapt to a new or unseen regime with minimal data.

        Uses the available *n_shots* observations to compute a
        preliminary allocation, blending with the mean of all existing
        regimes (knowledge transfer).

        Parameters
        ----------
        new_regime_data : list[np.ndarray]
            List of scan-performance vectors observed in the new regime
            (each of shape ``(n_scans,)``). Up to *n_shots* are used.
        n_shots : int
            Maximum number of observations to consume (default 10).

        Returns
        -------
        adapted_weights : np.ndarray
            Scan allocation for the new regime, shape ``(n_scans,)``.
        """
        shots = new_regime_data[:n_shots]

        if len(shots) == 0:
            # No data at all -- use average across all known regimes.
            avg_perf = np.mean(self.performance_matrix, axis=0)
            return _softmax(avg_perf * 5.0)

        # Empirical mean from few-shot data.
        shot_matrix = np.array(
            [np.asarray(s, dtype=np.float64)[:self.n_scans] for s in shots]
        )
        empirical_mean = np.mean(shot_matrix, axis=0)

        # Prior: mean across all regimes.
        prior_mean = np.mean(self.performance_matrix, axis=0)

        # Blend empirical with prior.  Weight the prior inversely with
        # the number of shots available.
        alpha = len(shots) / (len(shots) + n_shots)  # 0.5 at n_shots observations
        blended = alpha * empirical_mean + (1.0 - alpha) * prior_mean

        return _softmax(blended * 5.0)


# ============================================================================
# 7. AdaptiveScannerFramework
# ============================================================================

class AdaptiveScannerFramework(BaseScanner[AdvancedScanResult]):
    """
    Orchestrator that wraps multiple scanners with self-learning
    adaptive intelligence.

    This scanner:
    1. Runs all registered child scanners.
    2. Monitors each scanner's live performance.
    3. Detects concept drift in scanner effectiveness.
    4. Dynamically adjusts scanner weights via Thompson Sampling.
    5. Combines signals using an adaptive ensemble.
    6. Produces ``AdvancedScanResult`` objects enriched with meta-learning
       context and performance tracking.

    Attributes
    ----------
    category : ScanCategory
        Always ``ScanCategory.MACHINE_LEARNING``.
    """

    category: ScanCategory = ScanCategory.MACHINE_LEARNING

    def __init__(
        self,
        config: Optional[ScannerConfig] = None,
        n_regimes: int = 8,
    ):
        """
        Parameters
        ----------
        config : ScannerConfig, optional
        n_regimes : int
            Number of distinct market regimes the meta-learner should
            track (default 8, matching ``RegimeContext``).
        """
        super().__init__(
            name="adaptive_ml",
            scan_mode=ScanMode.ALL,
            config=config,
        )

        self._registered_scans: Dict[str, BaseScanner] = {}
        self._scan_names: List[str] = []

        # Internal components (lazily resized on first scan).
        self._n_regimes = n_regimes
        self._bandit: Optional[ThompsonSamplingBandit] = None
        self._ensemble: Optional[EnsembleAdapter] = None
        self._meta_learner: Optional[MetaLearner] = None
        self._performance_monitor = ScanPerformanceMonitor()
        self._drift_detector = ConceptDriftDetector()
        self._online_learner: Optional[OnlineLearner] = None

        # Performance tracker objects per scan.
        self._trackers: Dict[str, ScanPerformanceTracker] = {}

        # History for drift detection: scan_name -> list of accuracy scores.
        self._accuracy_history: Dict[str, List[float]] = defaultdict(list)

        # Regime mapping.
        self._regime_to_idx: Dict[str, int] = {
            rc.value: i for i, rc in enumerate(RegimeContext)
        }

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_scan(self, name: str, scanner: BaseScanner) -> None:
        """
        Register a scanner for adaptive monitoring and weighting.

        Parameters
        ----------
        name : str
            Unique name for the scanner.
        scanner : BaseScanner
            Scanner instance.
        """
        if name in self._registered_scans:
            self._logger.warning("Scanner '%s' already registered; overwriting.", name)

        self._registered_scans[name] = scanner
        self._scan_names = list(self._registered_scans.keys())

        # Create a performance tracker.
        self._trackers[name] = ScanPerformanceTracker(
            scan_name=name,
            category=self.category,
        )

        # Rebuild internal components to match the new scanner count.
        n = len(self._scan_names)
        self._bandit = ThompsonSamplingBandit(n_arms=n)
        self._ensemble = EnsembleAdapter(n_models=n)
        self._meta_learner = MetaLearner(n_scans=n, n_regimes=self._n_regimes)
        self._online_learner = OnlineLearner(n_features=n)

    # ------------------------------------------------------------------
    # Main scan entry point
    # ------------------------------------------------------------------

    async def scan(self, context: ScanContext) -> List[AdvancedScanResult]:
        """
        Execute the full adaptive scan pipeline.

        Steps:
            a. Run all registered child scanners.
            b. Monitor each scanner's performance.
            c. Detect concept drift in scan effectiveness.
            d. Adjust scan weights via Thompson Sampling.
            e. Combine signals with the adaptive ensemble.
            f. Generate ``AdvancedScanResult`` objects.

        Parameters
        ----------
        context : ScanContext

        Returns
        -------
        results : list[AdvancedScanResult]
        """
        if not self._registered_scans:
            self._logger.warning("No scanners registered; returning empty results.")
            return []

        n_scans = len(self._scan_names)

        # (a) Run all registered scanners concurrently. -----------------
        child_results: Dict[str, List[ScanResult]] = {}
        tasks = {
            name: asyncio.create_task(self._safe_execute(name, scanner, context))
            for name, scanner in self._registered_scans.items()
        }

        for name, task in tasks.items():
            results_list = await task
            child_results[name] = results_list

        # (b) Monitor performance. -------------------------------------
        scan_accuracies = np.zeros(n_scans, dtype=np.float64)
        for idx, name in enumerate(self._scan_names):
            acc = self._performance_monitor.get_rolling_accuracy(name)
            scan_accuracies[idx] = acc
            self._accuracy_history[name].append(acc)

            # Update tracker.
            tracker = self._trackers[name]
            tracker.current_accuracy = acc
            tracker.last_updated = datetime.now(timezone.utc)

        # (c) Detect concept drift. ------------------------------------
        for idx, name in enumerate(self._scan_names):
            history = self._accuracy_history[name]
            if len(history) >= 20:
                stream = np.array(history[-200:], dtype=np.float64)
                drift_detected, drift_point, magnitude = (
                    self._drift_detector.adwin(stream)
                )
                tracker = self._trackers[name]
                tracker.drift_detected = drift_detected
                tracker.drift_magnitude = magnitude
                tracker.last_drift_check = datetime.now(timezone.utc)

                if drift_detected:
                    self._logger.info(
                        "Concept drift detected in '%s' at point %d "
                        "(magnitude %.4f)",
                        name, drift_point, magnitude,
                    )

        # (d) Adjust scan weights via Thompson Sampling. ---------------
        if self._bandit is not None:
            selected_arm = self._bandit.select_arm()
            # Update bandit with rolling accuracies as rewards.
            for idx in range(n_scans):
                self._bandit.update(idx, scan_accuracies[idx])

        # Meta-learner update.
        regime_str = self._resolve_regime(context)
        regime_idx = self._regime_to_idx.get(regime_str, 0)
        if self._meta_learner is not None:
            self._meta_learner.update(regime_idx, scan_accuracies)
            meta_weights = self._meta_learner.get_scan_allocation(regime_idx)
        else:
            meta_weights = np.ones(n_scans, dtype=np.float64) / n_scans

        # Performance-monitor weights.
        monitor_weights = np.array([
            self._performance_monitor.get_effective_weight(
                name, regime_str
            )
            for name in self._scan_names
        ], dtype=np.float64)

        # Blend bandit expected values, meta-learner, and monitor weights.
        if self._bandit is not None:
            bandit_stats = self._bandit.get_arm_stats()
            bandit_ev = np.array(
                [s["expected_value"] for s in bandit_stats], dtype=np.float64
            )
        else:
            bandit_ev = np.ones(n_scans, dtype=np.float64) * 0.5

        combined_weights = (
            0.35 * _softmax(bandit_ev * 5.0)
            + 0.35 * meta_weights
            + 0.30 * _softmax(monitor_weights * 2.0)
        )
        combined_weights /= np.sum(combined_weights) + _EPS

        # Store effective weights in trackers.
        for idx, name in enumerate(self._scan_names):
            tracker = self._trackers[name]
            tracker.performance_weight = float(monitor_weights[idx])
            tracker.regime_weight = float(meta_weights[idx])
            tracker.effective_weight = float(combined_weights[idx])
            tracker.update_weight()

        # (e) Combine signals using adaptive ensemble. -----------------
        # Aggregate child results per symbol.
        symbol_signals: Dict[str, List[Tuple[str, ScanResult, float]]] = (
            defaultdict(list)
        )
        for idx, name in enumerate(self._scan_names):
            weight = combined_weights[idx]
            for result in child_results.get(name, []):
                symbol_signals[result.symbol].append((name, result, weight))

        # (f) Generate AdvancedScanResults. ----------------------------
        advanced_results: List[AdvancedScanResult] = []

        for symbol, signals in symbol_signals.items():
            advanced_result = self._build_advanced_result(
                symbol=symbol,
                signals=signals,
                context=context,
                regime_str=regime_str,
                combined_weights=combined_weights,
            )
            if advanced_result is not None:
                advanced_results.append(advanced_result)

        # Sort by confidence descending.
        advanced_results.sort(key=lambda r: r.confidence, reverse=True)
        return advanced_results

    # ------------------------------------------------------------------
    # Signal validation
    # ------------------------------------------------------------------

    def validate_signal(
        self,
        result: AdvancedScanResult,
        context: ScanContext,
    ) -> bool:
        """Validate an adaptive scan result."""
        if result.confidence < (self.config.min_confidence / 100.0):
            return False
        if result.signal_strength < 0.1:
            return False
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _safe_execute(
        self,
        name: str,
        scanner: BaseScanner,
        context: ScanContext,
    ) -> List[ScanResult]:
        """Execute a child scanner, catching exceptions."""
        try:
            results, _summary = await scanner.execute(context)
            return results
        except Exception as exc:
            self._logger.warning(
                "Child scanner '%s' raised %s: %s", name, type(exc).__name__, exc
            )
            return []

    def _resolve_regime(self, context: ScanContext) -> str:
        """Map ``ScanContext.market_regime`` to a ``RegimeContext`` value."""
        regime_map = {
            "trending_up": RegimeContext.TRENDING_UP.value,
            "trending_down": RegimeContext.TRENDING_DOWN.value,
            "ranging": RegimeContext.RANGING.value,
            "high_volatility": RegimeContext.VOLATILE.value,
            "low_volatility": RegimeContext.QUIET.value,
            "breakout": RegimeContext.TRANSITION.value,
        }
        return regime_map.get(
            context.market_regime.value, RegimeContext.RANGING.value
        )

    def _build_advanced_result(
        self,
        symbol: str,
        signals: List[Tuple[str, ScanResult, float]],
        context: ScanContext,
        regime_str: str,
        combined_weights: np.ndarray,
    ) -> Optional[AdvancedScanResult]:
        """
        Combine multiple child signals for a single symbol into one
        ``AdvancedScanResult``.
        """
        if not signals:
            return None

        # Weighted vote for direction.
        direction_scores: Dict[str, float] = defaultdict(float)
        weighted_confidence = 0.0
        total_weight = 0.0

        supporting: List[str] = []
        contradicting: List[str] = []

        best_result: Optional[ScanResult] = None
        best_weight: float = -1.0

        for name, result, weight in signals:
            dir_key = result.direction.value
            direction_scores[dir_key] += weight * (result.confidence / 100.0)
            weighted_confidence += weight * (result.confidence / 100.0)
            total_weight += weight

            if weight > best_weight:
                best_weight = weight
                best_result = result

        if best_result is None or total_weight < _EPS:
            return None

        # Determine dominant direction.
        dominant_dir = max(direction_scores, key=direction_scores.get)  # type: ignore[arg-type]
        direction_map = {
            SignalDirection.LONG.value: "BULLISH",
            SignalDirection.SHORT.value: "BEARISH",
            SignalDirection.NEUTRAL.value: "NEUTRAL",
        }
        signal_direction = direction_map.get(dominant_dir, "NEUTRAL")

        # Classify supporting vs contradicting scanners.
        for name, result, weight in signals:
            label = f"{name} (conf={result.confidence:.0f}%, w={weight:.3f})"
            if result.direction.value == dominant_dir:
                supporting.append(label)
            else:
                contradicting.append(label)

        # Combined confidence: weighted average, clipped to [0, 1].
        confidence = float(np.clip(weighted_confidence / total_weight, 0.0, 1.0))

        # Signal strength: proportion of total weight supporting the
        # dominant direction.
        dominant_weight = direction_scores.get(dominant_dir, 0.0)
        signal_strength = float(np.clip(dominant_weight / total_weight, 0.0, 1.0))

        # If ensemble produces conflicting / neutral result, skip.
        if signal_direction == "NEUTRAL" and confidence < 0.3:
            return None

        # Use ensemble output for BMA if we have the adapter.
        if self._ensemble is not None and len(signals) > 1:
            predictions = np.array(
                [r.confidence / 100.0 for _, r, _ in signals], dtype=np.float64
            )
            prior_acc = np.array(
                [w for _, _, w in signals], dtype=np.float64
            )
            bma_confidence = self._ensemble.bayesian_model_average(
                predictions, prior_acc, prior_acc
            )
            # Blend BMA with direct weighted average.
            confidence = 0.6 * confidence + 0.4 * float(bma_confidence)
            confidence = float(np.clip(confidence, 0.0, 1.0))

        # Build trade levels from the best child result.
        entry_price = best_result.entry_price
        stop_loss_level = best_result.stop_loss or 0.0
        targets = best_result.targets or []
        target_level = targets[0] if targets else 0.0
        secondary_targets = targets[1:] if len(targets) > 1 else []

        # Risk/reward.
        if entry_price and stop_loss_level > 0 and target_level > 0:
            risk = abs(entry_price - stop_loss_level)
            reward = abs(target_level - entry_price)
            rr = _safe_div(reward, risk)
        else:
            rr = 0.0

        # Expected move.
        if entry_price and target_level > 0:
            expected_move_pct = ((target_level - entry_price) / entry_price) * 100.0
        else:
            expected_move_pct = 0.0

        # Historical accuracy from monitor.
        historical_acc = float(np.mean([
            self._performance_monitor.get_rolling_accuracy(name)
            for name, _, _ in signals
        ]))

        # Determine false positive rate from inverse accuracy.
        false_positive_rate = float(np.clip(1.0 - historical_acc, 0.0, 1.0))

        # Build regime context enum.
        try:
            regime_context = RegimeContext(regime_str)
        except ValueError:
            regime_context = RegimeContext.RANGING

        # Bandit stats for metadata.
        bandit_meta = {}
        if self._bandit is not None:
            bandit_meta = {
                "arm_stats": self._bandit.get_arm_stats(),
                "scan_weights": combined_weights.tolist(),
            }

        # Drift information.
        drift_info = {}
        for name, _, _ in signals:
            tracker = self._trackers.get(name)
            if tracker and tracker.drift_detected:
                drift_info[name] = {
                    "drift_magnitude": tracker.drift_magnitude,
                }

        return AdvancedScanResult(
            scan_id=str(uuid.uuid4()),
            scan_name=self.name,
            category=self.category,
            symbol=symbol,
            signal_direction=signal_direction,
            signal_strength=signal_strength,
            confidence=confidence,
            expected_move_pct=expected_move_pct,
            expected_timeframe=ExpectedTimeframe.SWING,
            risk_reward_ratio=rr,
            entry_price=entry_price,
            stop_loss_level=stop_loss_level,
            target_level=target_level,
            secondary_targets=secondary_targets,
            supporting_evidence=supporting,
            contradicting_evidence=contradicting,
            historical_accuracy=historical_acc,
            regime_context=regime_context,
            mathematical_basis=(
                "Adaptive ensemble: Thompson Sampling bandit for exploration/"
                "exploitation + Bayesian Model Averaging + Hedge exponential "
                "weights. Concept drift monitored via ADWIN."
            ),
            false_positive_rate=false_positive_rate,
            decay_halflife_days=30,
            information_coefficient=float(np.clip(
                2.0 * (historical_acc - 0.5), -1.0, 1.0
            )),
            signal_to_noise=_safe_div(signal_strength, 1.0 - signal_strength + _EPS),
            metadata={
                "adaptive_framework": True,
                "n_child_scanners": len(signals),
                "scanner_names": [name for name, _, _ in signals],
                "bandit": bandit_meta,
                "drift_info": drift_info,
                "trackers": {
                    name: {
                        "effective_weight": self._trackers[name].effective_weight,
                        "drift_detected": self._trackers[name].drift_detected,
                        "current_accuracy": self._trackers[name].current_accuracy,
                    }
                    for name in self._scan_names
                    if name in self._trackers
                },
            },
        )

    # ------------------------------------------------------------------
    # Public accessors for monitoring / debugging
    # ------------------------------------------------------------------

    @property
    def registered_scans(self) -> Dict[str, BaseScanner]:
        """Return a copy of the registered scanner mapping."""
        return dict(self._registered_scans)

    @property
    def trackers(self) -> Dict[str, ScanPerformanceTracker]:
        """Return the live performance trackers."""
        return dict(self._trackers)

    @property
    def performance_monitor(self) -> ScanPerformanceMonitor:
        """Access the underlying performance monitor."""
        return self._performance_monitor

    @property
    def drift_detector(self) -> ConceptDriftDetector:
        """Access the concept drift detector."""
        return self._drift_detector

    @property
    def bandit(self) -> Optional[ThompsonSamplingBandit]:
        """Access the Thompson Sampling bandit."""
        return self._bandit

    @property
    def ensemble(self) -> Optional[EnsembleAdapter]:
        """Access the ensemble adapter."""
        return self._ensemble

    @property
    def meta_learner_instance(self) -> Optional[MetaLearner]:
        """Access the meta-learner."""
        return self._meta_learner

    def record_outcome(
        self,
        scan_name: str,
        prediction: float,
        actual_outcome: float,
        regime: Optional[str] = None,
    ) -> None:
        """
        Record a realised outcome for a scanner signal.

        This feeds the performance monitor and updates the ensemble /
        bandit weights over time.

        Parameters
        ----------
        scan_name : str
        prediction : float
        actual_outcome : float
        regime : str, optional
        """
        self._performance_monitor.record_signal(
            scan_name, prediction, actual_outcome, regime
        )

        # Update tracker counters.
        if scan_name in self._trackers:
            tracker = self._trackers[scan_name]
            tracker.total_signals += 1
            same_sign = (
                (prediction > 0 and actual_outcome > 0)
                or (prediction < 0 and actual_outcome < 0)
            )
            if same_sign:
                tracker.correct_signals += 1

        # Update ensemble with outcome.
        if self._ensemble is not None and self._scan_names:
            idx = self._scan_names.index(scan_name) if scan_name in self._scan_names else -1
            if idx >= 0:
                outcome_arr = np.zeros(len(self._scan_names), dtype=np.float64)
                outcome_arr[idx] = actual_outcome
                pred_arr = np.zeros(len(self._scan_names), dtype=np.float64)
                pred_arr[idx] = prediction
                self._ensemble.update_weights(outcome_arr, pred_arr)

    def get_scan_diagnostics(self) -> Dict[str, Any]:
        """
        Return a diagnostic summary of the adaptive framework state.

        Returns
        -------
        diagnostics : dict
        """
        diag: Dict[str, Any] = {
            "n_registered_scans": len(self._scan_names),
            "scan_names": list(self._scan_names),
            "trackers": {},
        }

        for name in self._scan_names:
            tracker = self._trackers.get(name)
            if tracker:
                decay_info = self._performance_monitor.detect_alpha_decay(name)
                retire_info = self._performance_monitor.retire_scan(name)
                diag["trackers"][name] = {
                    "total_signals": tracker.total_signals,
                    "correct_signals": tracker.correct_signals,
                    "hit_rate": tracker.hit_rate,
                    "current_accuracy": tracker.current_accuracy,
                    "effective_weight": tracker.effective_weight,
                    "drift_detected": tracker.drift_detected,
                    "drift_magnitude": tracker.drift_magnitude,
                    "alpha_decay": decay_info,
                    "retirement": retire_info,
                }

        if self._bandit is not None:
            diag["bandit_stats"] = self._bandit.get_arm_stats()

        if self._meta_learner is not None:
            diag["meta_learner"] = {
                "performance_matrix": self._meta_learner.performance_matrix.tolist(),
                "count_matrix": self._meta_learner.count_matrix.tolist(),
            }

        return diag
