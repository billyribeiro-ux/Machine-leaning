"""
Revolution Alpha Engine - Extreme Value Theory Scanner

Tail risk analysis and extreme event modeling using:
- Generalized Extreme Value (GEV) distribution for block maxima
- Generalized Pareto Distribution (GPD) for peaks over threshold
- Expected Shortfall (CVaR) estimation
- Tail dependence coefficient for co-crash risk
- Return level estimation for N-year events
- EVT-based Value at Risk

Category F5 from the scan taxonomy.
"""

import numpy as np
from scipy import stats
from scipy.optimize import minimize
from typing import Optional, List, Dict, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
import logging
import uuid

from .base import BaseScanner, ScanContext, MarketData, HistoricalData
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
)

logger = logging.getLogger(__name__)


# =============================================================================
# Generalized Pareto Distribution (GPD) for Peaks Over Threshold
# =============================================================================

class GPDFitter:
    """
    Fit Generalized Pareto Distribution to exceedances over a threshold.

    The GPD models the distribution of excesses over a high threshold u:
    F_u(y) = P(X - u ≤ y | X > u)

    GPD PDF: f(y; ξ, σ) = (1/σ)(1 + ξy/σ)^{-(1/ξ + 1)}

    Parameters:
    - ξ (shape): > 0 heavy tail (Fréchet), = 0 exponential, < 0 bounded tail (Weibull)
    - σ (scale): > 0
    """

    def __init__(self):
        self.shape: float = 0.0   # ξ (xi)
        self.scale: float = 1.0   # σ (sigma)
        self.threshold: float = 0.0
        self.n_exceedances: int = 0
        self.n_total: int = 0
        self._fitted: bool = False

    def fit(
        self,
        data: np.ndarray,
        threshold: Optional[float] = None,
        quantile: float = 0.95,
    ) -> 'GPDFitter':
        """
        Fit GPD to exceedances over threshold using MLE.

        Args:
            data: Full data series (losses, positive = bad)
            threshold: Explicit threshold. If None, use quantile.
            quantile: Quantile to use as threshold (default 95th percentile)

        Returns:
            self (fitted)
        """
        self.n_total = len(data)

        if threshold is None:
            threshold = float(np.quantile(data, quantile))
        self.threshold = threshold

        exceedances = data[data > threshold] - threshold
        self.n_exceedances = len(exceedances)

        if self.n_exceedances < 10:
            self.shape = 0.0
            self.scale = float(np.mean(exceedances)) if self.n_exceedances > 0 else 1.0
            self._fitted = True
            return self

        def neg_log_likelihood(params):
            xi, sigma = params
            if sigma <= 0:
                return 1e10
            n = len(exceedances)
            y = exceedances / sigma

            if abs(xi) < 1e-6:
                return n * np.log(sigma) + np.sum(y)

            term = 1 + xi * y
            if np.any(term <= 0):
                return 1e10

            return n * np.log(sigma) + (1 + 1 / xi) * np.sum(np.log(term))

        sigma0 = float(np.std(exceedances))
        xi0 = 0.1

        result = minimize(
            neg_log_likelihood,
            x0=[xi0, sigma0],
            method='Nelder-Mead',
            options={'maxiter': 1000, 'xatol': 1e-8, 'fatol': 1e-8},
        )

        if result.success:
            self.shape = float(result.x[0])
            self.scale = float(max(result.x[1], 1e-10))
        else:
            self.shape = 0.0
            self.scale = float(np.mean(exceedances))

        self._fitted = True
        return self

    def var(self, alpha: float = 0.99) -> float:
        """
        Compute EVT-based Value at Risk.

        VaR_α = u + (σ/ξ) × [(n/N_u × (1-α))^{-ξ} - 1]

        Args:
            alpha: Confidence level (e.g., 0.99 for 99% VaR)

        Returns:
            VaR estimate
        """
        if not self._fitted or self.n_exceedances == 0:
            return 0.0

        p = 1 - alpha
        exceedance_rate = self.n_exceedances / max(1, self.n_total)

        if abs(self.shape) < 1e-6:
            return self.threshold + self.scale * np.log(exceedance_rate / p)

        return self.threshold + (self.scale / self.shape) * (
            (exceedance_rate / p) ** self.shape - 1
        )

    def expected_shortfall(self, alpha: float = 0.99) -> float:
        """
        Compute Expected Shortfall (CVaR) using EVT.

        ES_α = VaR_α / (1-ξ) + (σ - ξ·u) / (1-ξ)

        This is a coherent risk measure (unlike VaR).
        """
        if not self._fitted:
            return 0.0

        var_alpha = self.var(alpha)

        if self.shape >= 1.0:
            return float('inf')

        es = var_alpha / (1 - self.shape) + (self.scale - self.shape * self.threshold) / (1 - self.shape)
        return es

    def return_level(self, return_period: float) -> float:
        """
        Estimate the N-period return level.

        The level expected to be exceeded once every `return_period` periods.

        Args:
            return_period: Return period (e.g., 250 for ~1 year of trading days)

        Returns:
            Return level
        """
        if not self._fitted or self.n_exceedances == 0:
            return 0.0

        exceedance_rate = self.n_exceedances / max(1, self.n_total)
        p = 1.0 / return_period

        if abs(self.shape) < 1e-6:
            y_p = -np.log(p * exceedance_rate) if p * exceedance_rate > 0 else 0
        else:
            ratio = exceedance_rate / p if p > 0 else 1
            y_p = (ratio ** self.shape - 1) / self.shape

        return self.threshold + self.scale * y_p

    def tail_probability(self, x: float) -> float:
        """Compute P(X > x) using the fitted GPD."""
        if not self._fitted or x <= self.threshold:
            return 1.0

        exceedance_rate = self.n_exceedances / max(1, self.n_total)
        y = (x - self.threshold) / self.scale

        if abs(self.shape) < 1e-6:
            return exceedance_rate * np.exp(-y)

        term = 1 + self.shape * y
        if term <= 0:
            return 0.0

        return exceedance_rate * term ** (-1 / self.shape)


# =============================================================================
# Tail Dependence Analysis
# =============================================================================

class TailDependenceAnalyzer:
    """
    Estimate tail dependence between two assets.

    The tail dependence coefficient λ measures the probability
    of joint extreme moves:
    λ_L = lim_{q→0} P(X < F_X^{-1}(q) | Y < F_Y^{-1}(q))
    λ_U = lim_{q→1} P(X > F_X^{-1}(q) | Y > F_Y^{-1}(q))
    """

    @staticmethod
    def lower_tail_dependence(
        x: np.ndarray,
        y: np.ndarray,
        quantiles: Optional[np.ndarray] = None,
    ) -> float:
        """
        Estimate lower tail dependence coefficient.

        Uses the empirical copula approach.

        Args:
            x: First return series
            y: Second return series
            quantiles: Quantile levels to use for estimation

        Returns:
            Estimated λ_L ∈ [0, 1]
        """
        n = min(len(x), len(y))
        if n < 30:
            return 0.0

        x = x[:n]
        y = y[:n]

        rank_x = stats.rankdata(x) / (n + 1)
        rank_y = stats.rankdata(y) / (n + 1)

        if quantiles is None:
            quantiles = np.array([0.01, 0.02, 0.05, 0.10])

        lambdas = []
        for q in quantiles:
            joint = np.sum((rank_x <= q) & (rank_y <= q))
            marginal = np.sum(rank_x <= q)
            if marginal > 0:
                lambdas.append(joint / marginal)

        if not lambdas:
            return 0.0

        return float(np.mean(lambdas))

    @staticmethod
    def upper_tail_dependence(
        x: np.ndarray,
        y: np.ndarray,
        quantiles: Optional[np.ndarray] = None,
    ) -> float:
        """Estimate upper tail dependence coefficient."""
        n = min(len(x), len(y))
        if n < 30:
            return 0.0

        x = x[:n]
        y = y[:n]

        rank_x = stats.rankdata(x) / (n + 1)
        rank_y = stats.rankdata(y) / (n + 1)

        if quantiles is None:
            quantiles = np.array([0.90, 0.95, 0.98, 0.99])

        lambdas = []
        for q in quantiles:
            joint = np.sum((rank_x >= q) & (rank_y >= q))
            marginal = np.sum(rank_x >= q)
            if marginal > 0:
                lambdas.append(joint / marginal)

        if not lambdas:
            return 0.0

        return float(np.mean(lambdas))


# =============================================================================
# Hill Estimator for Tail Index
# =============================================================================

class HillEstimator:
    """
    Hill estimator for the tail index of heavy-tailed distributions.

    The Hill estimator is: α̂ = [1/k × Σ_{i=1}^{k} ln(X_{(n-i+1)} / X_{(n-k)})]^{-1}

    where X_{(i)} are order statistics and k is the number of upper order
    statistics used.
    """

    @staticmethod
    def estimate(
        data: np.ndarray,
        k: Optional[int] = None,
    ) -> Tuple[float, float]:
        """
        Estimate tail index using Hill estimator.

        Args:
            data: Positive data (e.g., absolute returns)
            k: Number of upper order statistics. If None, use sqrt(n).

        Returns:
            (alpha_hat, standard_error)
        """
        data = data[data > 0]
        n = len(data)

        if n < 20:
            return 2.0, 1.0

        if k is None:
            k = int(np.sqrt(n))

        k = min(k, n - 1)
        k = max(k, 5)

        sorted_data = np.sort(data)[::-1]

        threshold = sorted_data[k]
        if threshold <= 0:
            return 2.0, 1.0

        log_ratios = np.log(sorted_data[:k] / threshold)
        hill_mean = np.mean(log_ratios)

        if hill_mean <= 0:
            return 2.0, 1.0

        alpha = 1.0 / hill_mean
        se = alpha / np.sqrt(k)

        return float(alpha), float(se)

    @staticmethod
    def hill_plot_data(
        data: np.ndarray,
        k_range: Optional[Tuple[int, int]] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Generate Hill plot data (alpha estimates vs k).

        Useful for selecting the optimal k where the estimate stabilizes.
        """
        data = data[data > 0]
        n = len(data)

        if k_range is None:
            k_range = (10, min(n // 2, 500))

        k_values = np.arange(k_range[0], k_range[1] + 1)
        alphas = np.zeros(len(k_values))

        for i, k in enumerate(k_values):
            alpha, _ = HillEstimator.estimate(data, int(k))
            alphas[i] = alpha

        return k_values, alphas


# =============================================================================
# EVT Scanner
# =============================================================================

class ExtremeValueScanner(BaseScanner):
    """
    Scanner for extreme value analysis and tail risk assessment.

    Identifies:
    - Abnormally fat tails (elevated crash/melt-up risk)
    - Tail risk regime changes
    - Co-crash risk with market (tail dependence)
    - Extreme return levels approaching historical crisis thresholds
    - VaR/CVaR breaches relative to position sizing

    Category F5 from the scan taxonomy.
    """

    def __init__(self, config: Optional[ScannerConfig] = None):
        super().__init__(
            name="extreme_value",
            scan_mode=ScanMode.ALL,
            config=config,
        )
        self.var_confidence = 0.99
        self.lookback = 252
        self.tail_quantile = 0.95

    async def scan(self, context: ScanContext) -> List[AdvancedScanResult]:
        """Scan universe for tail risk signals."""
        results: List[AdvancedScanResult] = []

        for symbol in context.universe:
            try:
                result = self._analyze_tail_risk(symbol, context)
                if result is not None:
                    results.append(result)
            except Exception as e:
                self._logger.warning(f"EVT analysis failed for {symbol}: {e}")

        return results

    def _analyze_tail_risk(
        self,
        symbol: str,
        context: ScanContext,
    ) -> Optional[AdvancedScanResult]:
        """Comprehensive tail risk analysis for a symbol."""
        hist = context.historical_data.get(symbol)
        if not hist or len(hist.bars) < 60:
            return None

        closes = np.array(hist.closes, dtype=float)
        returns = np.diff(np.log(np.maximum(closes, 1e-10)))

        if len(returns) < 30:
            return None

        losses = -returns

        gpd_left = GPDFitter()
        gpd_left.fit(losses, quantile=self.tail_quantile)

        gpd_right = GPDFitter()
        gpd_right.fit(returns, quantile=self.tail_quantile)

        var_99 = gpd_left.var(self.var_confidence)
        cvar_99 = gpd_left.expected_shortfall(self.var_confidence)

        one_year_loss = gpd_left.return_level(252)
        five_year_loss = gpd_left.return_level(252 * 5)

        abs_returns = np.abs(returns)
        tail_index, tail_se = HillEstimator.estimate(abs_returns)

        recent_returns = returns[-20:]
        recent_max_loss = np.max(-recent_returns) if len(recent_returns) > 0 else 0
        loss_exceedance_prob = gpd_left.tail_probability(recent_max_loss)

        signals = []
        supporting = []
        contradicting = []

        if tail_index < 3.0:
            signals.append(("fat_tail", -0.6))
            supporting.append(
                f"Very fat tails detected (α={tail_index:.2f}±{tail_se:.2f}). "
                f"Infinite variance territory. Extreme moves more likely than normal."
            )
        elif tail_index < 4.0:
            signals.append(("heavy_tail", -0.3))
            supporting.append(
                f"Heavy tails (α={tail_index:.2f}). Finite variance but infinite kurtosis."
            )
        else:
            contradicting.append(f"Moderate tails (α={tail_index:.2f}), lower tail risk")

        if recent_max_loss > var_99:
            signals.append(("var_breach", -0.8))
            supporting.append(
                f"Recent loss ({recent_max_loss*100:.1f}%) breached 99% VaR ({var_99*100:.1f}%). "
                f"Tail event probability: {loss_exceedance_prob:.4f}"
            )

        lookback_half = len(returns) // 2
        if lookback_half >= 30:
            old_losses = -returns[:lookback_half]
            new_losses = -returns[lookback_half:]

            old_gpd = GPDFitter()
            old_gpd.fit(old_losses, quantile=self.tail_quantile)
            old_var = old_gpd.var(self.var_confidence)

            new_gpd = GPDFitter()
            new_gpd.fit(new_losses, quantile=self.tail_quantile)
            new_var = new_gpd.var(self.var_confidence)

            if old_var > 0 and new_var / old_var > 1.5:
                signals.append(("tail_expansion", -0.5))
                supporting.append(
                    f"Tail risk expanding: VaR increased {(new_var/old_var - 1)*100:.0f}% "
                    f"(old={old_var*100:.1f}%, new={new_var*100:.1f}%)"
                )
            elif old_var > 0 and new_var / old_var < 0.6:
                signals.append(("tail_compression", 0.3))
                supporting.append(
                    f"Tail risk compressing: VaR decreased {(1-new_var/old_var)*100:.0f}%"
                )

        upside_potential = gpd_right.return_level(20)
        downside_risk = gpd_left.return_level(20)
        if downside_risk > 0:
            asymmetry = upside_potential / downside_risk
            if asymmetry > 1.5:
                signals.append(("positive_asymmetry", 0.4))
                supporting.append(f"Positive tail asymmetry ({asymmetry:.2f}x): upside > downside")
            elif asymmetry < 0.6:
                signals.append(("negative_asymmetry", -0.4))
                supporting.append(f"Negative tail asymmetry ({asymmetry:.2f}x): downside > upside")

        if not signals:
            return None

        combined_score = sum(s[1] for s in signals) / len(signals)

        if abs(combined_score) < 0.1:
            return None

        direction = "BEARISH" if combined_score < 0 else "BULLISH"
        confidence = min(0.90, abs(combined_score) * 0.7 + 0.2)

        current_price = closes[-1]
        market_data = context.market_data.get(symbol)
        atr = market_data.atr if market_data and market_data.atr else current_price * 0.02

        if direction == "BEARISH":
            stop_loss = current_price + 1.5 * atr
            target = current_price - var_99 * current_price
        else:
            stop_loss = current_price - 1.5 * atr
            target = current_price + upside_potential * current_price

        risk = abs(current_price - stop_loss)
        reward = abs(target - current_price)
        rr = reward / risk if risk > 0 else 0

        return AdvancedScanResult(
            scan_id=str(uuid.uuid4()),
            scan_name="Extreme Value Theory Analysis",
            category=ScanCategory.RISK_MANAGEMENT,
            symbol=symbol,
            signal_direction=direction,
            signal_strength=abs(combined_score),
            confidence=confidence,
            expected_move_pct=abs(combined_score) * var_99 * 100,
            expected_timeframe=ExpectedTimeframe.SWING,
            risk_reward_ratio=rr,
            entry_price=current_price,
            stop_loss_level=stop_loss,
            target_level=target,
            supporting_evidence=supporting,
            contradicting_evidence=contradicting,
            regime_context=RegimeContext.VOLATILE if var_99 > 0.03 else RegimeContext.QUIET,
            mathematical_basis=(
                f"GPD fit: ξ={gpd_left.shape:.3f}, σ={gpd_left.scale:.4f}. "
                f"Hill tail index α={tail_index:.2f}. "
                f"VaR(99%)={var_99*100:.2f}%, CVaR(99%)={cvar_99*100:.2f}%. "
                f"1Y return level={one_year_loss*100:.1f}%, "
                f"5Y return level={five_year_loss*100:.1f}%."
            ),
            false_positive_rate=max(0.05, 1.0 - confidence),
            decay_halflife_days=60,
            metadata={
                "gpd_shape": gpd_left.shape,
                "gpd_scale": gpd_left.scale,
                "var_99": var_99,
                "cvar_99": cvar_99,
                "tail_index": tail_index,
                "tail_index_se": tail_se,
                "return_level_1y": one_year_loss,
                "return_level_5y": five_year_loss,
                "n_exceedances": gpd_left.n_exceedances,
                "threshold": gpd_left.threshold,
                "signal_components": [(name, round(score, 3)) for name, score in signals],
            },
        )

    def validate_signal(self, result, context: ScanContext) -> bool:
        """Validate EVT signal."""
        if not isinstance(result, AdvancedScanResult):
            return False
        if result.confidence < 0.3:
            return False
        return True
