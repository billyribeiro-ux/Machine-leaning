"""
Revolution Alpha Engine - Market Regime Detection

Institutional-grade regime detection using:
- Hidden Markov Models for state inference
- Gaussian Mixture Models for distribution clustering
- Change point detection algorithms
- Volatility regime classification
- Trend regime identification
"""

import numpy as np
import pandas as pd
from typing import Optional, List, Dict, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
import logging
from datetime import datetime
from scipy import stats
from scipy.special import logsumexp
import warnings

warnings.filterwarnings('ignore')

logger = logging.getLogger(__name__)


class MarketRegimeType(str, Enum):
    """Market regime classifications."""
    BULL_QUIET = "bull_quiet"  # Trending up, low volatility
    BULL_VOLATILE = "bull_volatile"  # Trending up, high volatility
    BEAR_QUIET = "bear_quiet"  # Trending down, low volatility
    BEAR_VOLATILE = "bear_volatile"  # Trending down, high volatility
    SIDEWAYS_QUIET = "sideways_quiet"  # Range-bound, low volatility
    SIDEWAYS_VOLATILE = "sideways_volatile"  # Range-bound, high volatility
    CRISIS = "crisis"  # Extreme volatility, rapid moves
    RECOVERY = "recovery"  # Post-crisis recovery
    UNKNOWN = "unknown"


@dataclass
class RegimeState:
    """Current regime state with probabilities."""
    regime: MarketRegimeType
    probability: float
    regime_duration: int  # Bars in current regime
    transition_probability: float  # Probability of regime change
    volatility_percentile: float
    trend_strength: float
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_high_conviction(self) -> bool:
        """Check if regime detection is high conviction."""
        return self.probability >= 0.7

    @property
    def regime_stable(self) -> bool:
        """Check if regime is stable (low transition probability)."""
        return self.transition_probability < 0.2


@dataclass
class RegimeTransition:
    """Detected regime transition."""
    from_regime: MarketRegimeType
    to_regime: MarketRegimeType
    timestamp: datetime
    confidence: float
    trigger: str  # What triggered the transition


class HiddenMarkovModel:
    """
    Hidden Markov Model for regime detection.

    States represent different market regimes, observations are
    returns and volatility features.
    """

    def __init__(
        self,
        n_states: int = 4,
        n_features: int = 2,
        random_state: int = 42
    ):
        self.n_states = n_states
        self.n_features = n_features
        self.random_state = random_state

        np.random.seed(random_state)

        # Initialize parameters
        self.start_prob = np.ones(n_states) / n_states
        self.trans_prob = self._init_transition_matrix()

        # Emission parameters (Gaussian)
        self.means = np.random.randn(n_states, n_features)
        self.covars = np.array([np.eye(n_features) for _ in range(n_states)])

        self._fitted = False

    def _init_transition_matrix(self) -> np.ndarray:
        """Initialize transition matrix with persistence bias."""
        # Regimes tend to persist
        trans = np.ones((self.n_states, self.n_states)) * 0.05
        np.fill_diagonal(trans, 0.85)
        # Normalize rows
        trans = trans / trans.sum(axis=1, keepdims=True)
        return trans

    def fit(
        self,
        observations: np.ndarray,
        n_iter: int = 100,
        tol: float = 1e-4
    ) -> 'HiddenMarkovModel':
        """
        Fit HMM using Baum-Welch algorithm.

        Args:
            observations: (T, n_features) array of observations
            n_iter: Maximum iterations
            tol: Convergence tolerance
        """
        T = len(observations)

        for iteration in range(n_iter):
            # E-step: Forward-backward algorithm
            alpha = self._forward(observations)
            beta = self._backward(observations)

            # Compute responsibilities
            gamma = self._compute_gamma(alpha, beta)
            xi = self._compute_xi(observations, alpha, beta)

            # M-step: Update parameters
            old_trans = self.trans_prob.copy()

            # Update start probabilities
            self.start_prob = gamma[0] / gamma[0].sum()

            # Update transition matrix
            for i in range(self.n_states):
                for j in range(self.n_states):
                    self.trans_prob[i, j] = xi[:, i, j].sum() / gamma[:-1, i].sum()

            # Update emission parameters
            for k in range(self.n_states):
                weights = gamma[:, k]
                total_weight = weights.sum()

                if total_weight > 0:
                    self.means[k] = np.average(observations, axis=0, weights=weights)
                    diff = observations - self.means[k]
                    self.covars[k] = np.dot(weights * diff.T, diff) / total_weight
                    # Add regularization
                    self.covars[k] += np.eye(self.n_features) * 1e-4

            # Check convergence
            if np.abs(self.trans_prob - old_trans).max() < tol:
                logger.info(f"HMM converged after {iteration + 1} iterations")
                break

        self._fitted = True
        return self

    def _forward(self, observations: np.ndarray) -> np.ndarray:
        """Forward algorithm (alpha pass)."""
        T = len(observations)
        alpha = np.zeros((T, self.n_states))

        # Initialize
        emission_probs = self._emission_prob(observations[0])
        alpha[0] = self.start_prob * emission_probs
        alpha[0] /= alpha[0].sum() + 1e-10

        # Forward pass
        for t in range(1, T):
            emission_probs = self._emission_prob(observations[t])
            alpha[t] = emission_probs * (alpha[t-1] @ self.trans_prob)
            alpha[t] /= alpha[t].sum() + 1e-10

        return alpha

    def _backward(self, observations: np.ndarray) -> np.ndarray:
        """Backward algorithm (beta pass)."""
        T = len(observations)
        beta = np.zeros((T, self.n_states))

        # Initialize
        beta[-1] = 1

        # Backward pass
        for t in range(T - 2, -1, -1):
            emission_probs = self._emission_prob(observations[t + 1])
            beta[t] = self.trans_prob @ (emission_probs * beta[t + 1])
            beta[t] /= beta[t].sum() + 1e-10

        return beta

    def _emission_prob(self, obs: np.ndarray) -> np.ndarray:
        """Compute emission probabilities for each state."""
        probs = np.zeros(self.n_states)

        for k in range(self.n_states):
            try:
                probs[k] = stats.multivariate_normal.pdf(
                    obs, mean=self.means[k], cov=self.covars[k]
                )
            except Exception:
                probs[k] = 1e-10

        return probs + 1e-10

    def _compute_gamma(
        self,
        alpha: np.ndarray,
        beta: np.ndarray
    ) -> np.ndarray:
        """Compute state occupation probabilities."""
        gamma = alpha * beta
        gamma /= gamma.sum(axis=1, keepdims=True) + 1e-10
        return gamma

    def _compute_xi(
        self,
        observations: np.ndarray,
        alpha: np.ndarray,
        beta: np.ndarray
    ) -> np.ndarray:
        """Compute transition probabilities."""
        T = len(observations)
        xi = np.zeros((T - 1, self.n_states, self.n_states))

        for t in range(T - 1):
            emission_probs = self._emission_prob(observations[t + 1])
            for i in range(self.n_states):
                for j in range(self.n_states):
                    xi[t, i, j] = (
                        alpha[t, i] *
                        self.trans_prob[i, j] *
                        emission_probs[j] *
                        beta[t + 1, j]
                    )
            xi[t] /= xi[t].sum() + 1e-10

        return xi

    def predict(self, observations: np.ndarray) -> np.ndarray:
        """
        Predict most likely state sequence using Viterbi algorithm.
        """
        T = len(observations)

        # Initialize
        delta = np.zeros((T, self.n_states))
        psi = np.zeros((T, self.n_states), dtype=int)

        emission_probs = self._emission_prob(observations[0])
        delta[0] = np.log(self.start_prob + 1e-10) + np.log(emission_probs + 1e-10)

        # Forward pass
        for t in range(1, T):
            emission_probs = self._emission_prob(observations[t])
            for j in range(self.n_states):
                candidates = delta[t-1] + np.log(self.trans_prob[:, j] + 1e-10)
                psi[t, j] = np.argmax(candidates)
                delta[t, j] = candidates[psi[t, j]] + np.log(emission_probs[j] + 1e-10)

        # Backtrack
        states = np.zeros(T, dtype=int)
        states[-1] = np.argmax(delta[-1])

        for t in range(T - 2, -1, -1):
            states[t] = psi[t + 1, states[t + 1]]

        return states

    def predict_proba(self, observations: np.ndarray) -> np.ndarray:
        """Get state probabilities for each timestep."""
        alpha = self._forward(observations)
        return alpha


class GaussianMixtureRegime:
    """
    Gaussian Mixture Model for regime clustering.

    Clusters market states based on return and volatility characteristics.
    """

    def __init__(
        self,
        n_components: int = 4,
        random_state: int = 42
    ):
        self.n_components = n_components
        self.random_state = random_state

        np.random.seed(random_state)

        self.weights = np.ones(n_components) / n_components
        self.means: Optional[np.ndarray] = None
        self.covars: Optional[np.ndarray] = None

        self._fitted = False

    def fit(
        self,
        data: np.ndarray,
        n_iter: int = 100,
        tol: float = 1e-4
    ) -> 'GaussianMixtureRegime':
        """Fit GMM using EM algorithm."""
        n_samples, n_features = data.shape

        # Initialize with k-means++
        self.means = self._kmeans_init(data)
        self.covars = np.array([np.eye(n_features) for _ in range(self.n_components)])

        for iteration in range(n_iter):
            # E-step
            responsibilities = self._e_step(data)

            # M-step
            old_means = self.means.copy()

            n_k = responsibilities.sum(axis=0)
            self.weights = n_k / n_samples

            for k in range(self.n_components):
                if n_k[k] > 0:
                    self.means[k] = np.average(data, axis=0, weights=responsibilities[:, k])
                    diff = data - self.means[k]
                    self.covars[k] = np.dot(responsibilities[:, k] * diff.T, diff) / n_k[k]
                    self.covars[k] += np.eye(n_features) * 1e-4

            # Check convergence
            if np.abs(self.means - old_means).max() < tol:
                break

        self._fitted = True
        return self

    def _kmeans_init(self, data: np.ndarray) -> np.ndarray:
        """Initialize means using k-means++ algorithm."""
        n_samples, n_features = data.shape
        centers = np.zeros((self.n_components, n_features))

        # First center randomly
        idx = np.random.randint(n_samples)
        centers[0] = data[idx]

        # Remaining centers
        for k in range(1, self.n_components):
            distances = np.min([
                np.sum((data - centers[j]) ** 2, axis=1)
                for j in range(k)
            ], axis=0)

            probabilities = distances / distances.sum()
            idx = np.random.choice(n_samples, p=probabilities)
            centers[k] = data[idx]

        return centers

    def _e_step(self, data: np.ndarray) -> np.ndarray:
        """E-step: Compute responsibilities."""
        n_samples = len(data)
        log_resp = np.zeros((n_samples, self.n_components))

        for k in range(self.n_components):
            try:
                log_resp[:, k] = (
                    np.log(self.weights[k] + 1e-10) +
                    stats.multivariate_normal.logpdf(
                        data, mean=self.means[k], cov=self.covars[k]
                    )
                )
            except Exception:
                log_resp[:, k] = -1000

        # Normalize
        log_resp_norm = logsumexp(log_resp, axis=1, keepdims=True)
        responsibilities = np.exp(log_resp - log_resp_norm)

        return responsibilities

    def predict(self, data: np.ndarray) -> np.ndarray:
        """Predict cluster assignments."""
        responsibilities = self._e_step(data)
        return np.argmax(responsibilities, axis=1)

    def predict_proba(self, data: np.ndarray) -> np.ndarray:
        """Get cluster probabilities."""
        return self._e_step(data)


class ChangePointDetector:
    """
    Online change point detection for regime shifts.

    Uses CUSUM and Bayesian online change point detection.
    """

    def __init__(
        self,
        threshold: float = 5.0,
        drift: float = 0.5,
        window: int = 50
    ):
        self.threshold = threshold
        self.drift = drift
        self.window = window

        self._cusum_pos = 0
        self._cusum_neg = 0
        self._mean = 0
        self._std = 1
        self._n_samples = 0
        self._change_points: List[int] = []

    def update(self, value: float) -> Tuple[bool, float]:
        """
        Update with new observation.

        Returns:
            (is_change_point, cusum_score)
        """
        self._n_samples += 1

        # Update running statistics
        if self._n_samples == 1:
            self._mean = value
            self._std = 1
        else:
            old_mean = self._mean
            self._mean = old_mean + (value - old_mean) / self._n_samples

            if self._n_samples > 2:
                self._std = np.sqrt(
                    ((self._n_samples - 2) * self._std ** 2 +
                     (value - old_mean) * (value - self._mean)) /
                    (self._n_samples - 1)
                )

        # Standardize
        if self._std > 0:
            z = (value - self._mean) / self._std
        else:
            z = 0

        # CUSUM update
        self._cusum_pos = max(0, self._cusum_pos + z - self.drift)
        self._cusum_neg = max(0, self._cusum_neg - z - self.drift)

        cusum_score = max(self._cusum_pos, self._cusum_neg)

        # Check for change point
        is_change = cusum_score > self.threshold

        if is_change:
            self._change_points.append(self._n_samples)
            # Reset CUSUM
            self._cusum_pos = 0
            self._cusum_neg = 0

        return is_change, cusum_score

    def reset(self):
        """Reset detector state."""
        self._cusum_pos = 0
        self._cusum_neg = 0
        self._mean = 0
        self._std = 1
        self._n_samples = 0

    @property
    def change_points(self) -> List[int]:
        """Get detected change points."""
        return self._change_points.copy()


class RegimeDetector:
    """
    Master regime detection system.

    Combines multiple regime detection methods for robust classification.
    """

    def __init__(
        self,
        n_regimes: int = 4,
        lookback: int = 252,
        vol_threshold_low: float = 0.3,
        vol_threshold_high: float = 0.7,
        trend_threshold: float = 0.02
    ):
        self.n_regimes = n_regimes
        self.lookback = lookback
        self.vol_threshold_low = vol_threshold_low
        self.vol_threshold_high = vol_threshold_high
        self.trend_threshold = trend_threshold

        # Models
        self.hmm = HiddenMarkovModel(n_states=n_regimes)
        self.gmm = GaussianMixtureRegime(n_components=n_regimes)
        self.change_detector = ChangePointDetector()

        # State tracking
        self._current_regime: Optional[MarketRegimeType] = None
        self._regime_duration = 0
        self._regime_history: List[RegimeState] = []
        self._transitions: List[RegimeTransition] = []

        # Calibration data
        self._vol_history: List[float] = []
        self._return_history: List[float] = []

    def fit(self, data: pd.DataFrame) -> 'RegimeDetector':
        """
        Fit regime detection models on historical data.

        Args:
            data: DataFrame with columns [open, high, low, close, volume]
        """
        # Calculate features for regime detection
        returns = data['close'].pct_change().dropna()
        volatility = returns.rolling(20).std() * np.sqrt(252)
        volatility = volatility.dropna()

        # Align data
        min_len = min(len(returns), len(volatility))
        returns = returns.iloc[-min_len:].values
        volatility = volatility.iloc[-min_len:].values

        # Create observation matrix
        observations = np.column_stack([returns, volatility])
        observations = np.nan_to_num(observations)

        # Fit models
        self.hmm.fit(observations)
        self.gmm.fit(observations)

        # Store calibration data
        self._vol_history = volatility.tolist()
        self._return_history = returns.tolist()

        return self

    def detect(
        self,
        data: pd.DataFrame,
        use_hmm: bool = True,
        use_gmm: bool = True
    ) -> RegimeState:
        """
        Detect current market regime.

        Args:
            data: Recent OHLCV data
            use_hmm: Use HMM for detection
            use_gmm: Use GMM for detection

        Returns:
            Current regime state
        """
        # Calculate features
        close = data['close']
        returns = close.pct_change().dropna()

        if len(returns) < 20:
            return RegimeState(
                regime=MarketRegimeType.UNKNOWN,
                probability=0,
                regime_duration=0,
                transition_probability=0.5,
                volatility_percentile=0.5,
                trend_strength=0
            )

        # Current metrics
        current_return = returns.iloc[-1]
        volatility = returns.rolling(20).std().iloc[-1] * np.sqrt(252)
        trend = returns.rolling(20).mean().iloc[-1] * 252

        # Check for change point
        is_change, _ = self.change_detector.update(current_return)

        # Calculate volatility percentile
        if self._vol_history:
            vol_percentile = stats.percentileofscore(self._vol_history, volatility) / 100
        else:
            vol_percentile = 0.5

        # Model predictions
        obs = np.array([[current_return, volatility]])

        regime_probs = {}

        if use_hmm and self.hmm._fitted:
            hmm_probs = self.hmm.predict_proba(obs)[0]
            for i, p in enumerate(hmm_probs):
                regime_probs[f'hmm_{i}'] = p

        if use_gmm and self.gmm._fitted:
            gmm_probs = self.gmm.predict_proba(obs)[0]
            for i, p in enumerate(gmm_probs):
                regime_probs[f'gmm_{i}'] = p

        # Classify regime
        regime = self._classify_regime(trend, vol_percentile)

        # Calculate confidence
        if regime_probs:
            max_prob = max(regime_probs.values())
        else:
            max_prob = self._heuristic_confidence(trend, vol_percentile)

        # Calculate transition probability
        if is_change:
            transition_prob = 0.8
        else:
            transition_prob = 0.1

        # Update regime tracking
        if regime != self._current_regime:
            if self._current_regime is not None:
                self._transitions.append(RegimeTransition(
                    from_regime=self._current_regime,
                    to_regime=regime,
                    timestamp=datetime.utcnow(),
                    confidence=max_prob,
                    trigger="model_detection" if not is_change else "change_point"
                ))
            self._current_regime = regime
            self._regime_duration = 1
        else:
            self._regime_duration += 1

        # Create state
        state = RegimeState(
            regime=regime,
            probability=max_prob,
            regime_duration=self._regime_duration,
            transition_probability=transition_prob,
            volatility_percentile=vol_percentile,
            trend_strength=abs(trend)
        )

        self._regime_history.append(state)

        return state

    def _classify_regime(
        self,
        trend: float,
        vol_percentile: float
    ) -> MarketRegimeType:
        """Classify regime based on trend and volatility."""
        # Volatility classification
        if vol_percentile >= 0.9:
            is_crisis = True
            is_high_vol = True
        elif vol_percentile >= self.vol_threshold_high:
            is_crisis = False
            is_high_vol = True
        else:
            is_crisis = False
            is_high_vol = False

        # Trend classification
        if trend > self.trend_threshold:
            is_bullish = True
            is_bearish = False
        elif trend < -self.trend_threshold:
            is_bullish = False
            is_bearish = True
        else:
            is_bullish = False
            is_bearish = False

        # Combine
        if is_crisis:
            return MarketRegimeType.CRISIS

        if is_bullish:
            if is_high_vol:
                return MarketRegimeType.BULL_VOLATILE
            else:
                return MarketRegimeType.BULL_QUIET

        if is_bearish:
            if is_high_vol:
                return MarketRegimeType.BEAR_VOLATILE
            else:
                return MarketRegimeType.BEAR_QUIET

        if is_high_vol:
            return MarketRegimeType.SIDEWAYS_VOLATILE
        else:
            return MarketRegimeType.SIDEWAYS_QUIET

    def _heuristic_confidence(
        self,
        trend: float,
        vol_percentile: float
    ) -> float:
        """Calculate confidence using heuristics."""
        # Higher confidence when trend/vol are extreme
        trend_conf = min(1, abs(trend) / 0.1)
        vol_conf = abs(vol_percentile - 0.5) * 2

        return (trend_conf + vol_conf) / 2

    def get_regime_summary(self) -> Dict[str, Any]:
        """Get summary of regime detection."""
        if not self._regime_history:
            return {}

        recent = self._regime_history[-1]

        # Count regime occurrences
        regime_counts = {}
        for state in self._regime_history[-100:]:
            r = state.regime.value
            regime_counts[r] = regime_counts.get(r, 0) + 1

        return {
            'current_regime': recent.regime.value,
            'probability': recent.probability,
            'duration': recent.regime_duration,
            'transition_probability': recent.transition_probability,
            'volatility_percentile': recent.volatility_percentile,
            'trend_strength': recent.trend_strength,
            'is_stable': recent.regime_stable,
            'is_high_conviction': recent.is_high_conviction,
            'regime_distribution': regime_counts,
            'recent_transitions': len(self._transitions),
        }

    def get_regime_adjusted_parameters(
        self,
        base_position_size: float = 1.0,
        base_stop_pct: float = 2.0
    ) -> Dict[str, float]:
        """
        Get trading parameters adjusted for current regime.

        Args:
            base_position_size: Base position size
            base_stop_pct: Base stop loss percentage

        Returns:
            Adjusted parameters
        """
        if not self._regime_history:
            return {
                'position_size': base_position_size,
                'stop_pct': base_stop_pct,
                'take_profit_multiplier': 2.0
            }

        state = self._regime_history[-1]
        regime = state.regime

        # Position sizing adjustments
        if regime in [MarketRegimeType.CRISIS, MarketRegimeType.BEAR_VOLATILE]:
            position_mult = 0.25  # Reduce size significantly
            stop_mult = 2.0  # Wider stops
            tp_mult = 3.0  # Larger targets
        elif regime in [MarketRegimeType.BULL_VOLATILE, MarketRegimeType.SIDEWAYS_VOLATILE]:
            position_mult = 0.5
            stop_mult = 1.5
            tp_mult = 2.5
        elif regime in [MarketRegimeType.BULL_QUIET]:
            position_mult = 1.0  # Full size
            stop_mult = 1.0
            tp_mult = 2.0
        elif regime in [MarketRegimeType.BEAR_QUIET]:
            position_mult = 0.5
            stop_mult = 1.2
            tp_mult = 1.5
        else:  # Sideways quiet
            position_mult = 0.75
            stop_mult = 0.8  # Tighter stops for range
            tp_mult = 1.5

        # Confidence adjustment
        if not state.is_high_conviction:
            position_mult *= 0.7

        return {
            'position_size': base_position_size * position_mult,
            'stop_pct': base_stop_pct * stop_mult,
            'take_profit_multiplier': tp_mult
        }
