"""
Revolution Alpha Engine - Volatility Regime Scanner

Institutional-grade scanner for detecting volatility regime changes and
significant volatility events using multiple advanced estimators:

- Parkinson (1980) high-low range estimator
- Garman-Klass (1980) OHLC estimator
- Rogers-Satchell (1991) drift-independent estimator
- Yang-Zhang (2000) combined estimator (most efficient)
- GARCH(1,1) conditional volatility with MLE
- Markov regime-switching for regime detection
- Hawkes process for volatility clustering quantification
- Volatility cone for percentile ranking across horizons

Signals:
    BULLISH  - Volatility compression detected (breakout imminent)
    BEARISH  - Volatility expansion detected (risk-off regime)
    NEUTRAL  - No significant regime change
"""

from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field
import logging
import uuid

import numpy as np
from scipy.optimize import minimize
from scipy.stats import percentileofscore

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
    VolatilityEstimate,
    GARCHResult,
    VolatilityRegime,
    RegimeContext,
    ExpectedTimeframe,
)

logger = logging.getLogger(__name__)

# Annualization factor for daily returns
_TRADING_DAYS_PER_YEAR = 252
_ANNUALIZATION_FACTOR = np.sqrt(_TRADING_DAYS_PER_YEAR)

# Minimum number of bars required for various computations
_MIN_BARS_BASIC = 20
_MIN_BARS_GARCH = 60
_MIN_BARS_REGIME = 60
_MIN_BARS_CONE = 252


class VolatilityEstimators:
    """
    Collection of advanced volatility estimators.

    All estimators return annualized volatility (standard deviation) unless
    otherwise noted. Input arrays are expected to be numpy arrays of raw
    price values (not log prices). All computations are fully vectorized.
    """

    @staticmethod
    def parkinson(highs: np.ndarray, lows: np.ndarray) -> float:
        """
        Parkinson (1980) high-low range volatility estimator.

        More efficient than close-to-close because it uses intraday range
        information. Assumes no drift and continuous trading (no jumps).

        Formula:
            sigma^2 = (1 / (4 * n * ln2)) * sum( ln(H_i / L_i)^2 )

        Args:
            highs: Array of high prices.
            lows: Array of low prices.

        Returns:
            Annualized Parkinson volatility estimate.
        """
        highs = np.asarray(highs, dtype=np.float64)
        lows = np.asarray(lows, dtype=np.float64)

        # Guard against invalid prices
        valid = (highs > 0) & (lows > 0) & (highs >= lows)
        if valid.sum() < 2:
            return 0.0

        highs = highs[valid]
        lows = lows[valid]

        n = len(highs)
        log_hl = np.log(highs / lows)
        variance = np.sum(log_hl ** 2) / (4.0 * n * np.log(2.0))
        daily_vol = np.sqrt(variance)

        return float(daily_vol * _ANNUALIZATION_FACTOR)

    @staticmethod
    def garman_klass(
        opens: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
    ) -> float:
        """
        Garman-Klass (1980) OHLC volatility estimator.

        Utilizes full OHLC information for a more efficient estimate.
        Assumes no drift and continuous trading.

        Formula:
            sigma^2 = (1/n) * sum[ 0.5 * ln(H/L)^2 - (2*ln2 - 1) * ln(C/O)^2 ]

        Args:
            opens: Array of open prices.
            highs: Array of high prices.
            lows: Array of low prices.
            closes: Array of close prices.

        Returns:
            Annualized Garman-Klass volatility estimate.
        """
        opens = np.asarray(opens, dtype=np.float64)
        highs = np.asarray(highs, dtype=np.float64)
        lows = np.asarray(lows, dtype=np.float64)
        closes = np.asarray(closes, dtype=np.float64)

        valid = (opens > 0) & (highs > 0) & (lows > 0) & (closes > 0) & (highs >= lows)
        if valid.sum() < 2:
            return 0.0

        opens, highs, lows, closes = opens[valid], highs[valid], lows[valid], closes[valid]

        n = len(opens)
        log_hl = np.log(highs / lows)
        log_co = np.log(closes / opens)
        variance = np.sum(0.5 * log_hl ** 2 - (2.0 * np.log(2.0) - 1.0) * log_co ** 2) / n

        # Garman-Klass can produce small negative values due to the subtraction
        # term when the close-to-open component dominates. Clamp to zero.
        if variance <= 0.0:
            return 0.0

        daily_vol = np.sqrt(variance)
        return float(daily_vol * _ANNUALIZATION_FACTOR)

    @staticmethod
    def rogers_satchell(
        opens: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
    ) -> float:
        """
        Rogers-Satchell (1991) volatility estimator.

        Robust to drift (non-zero mean returns), making it suitable for
        trending markets. Does not account for opening jumps.

        Formula:
            sigma^2 = (1/n) * sum[ ln(H/C)*ln(H/O) + ln(L/C)*ln(L/O) ]

        Args:
            opens: Array of open prices.
            highs: Array of high prices.
            lows: Array of low prices.
            closes: Array of close prices.

        Returns:
            Annualized Rogers-Satchell volatility estimate.
        """
        opens = np.asarray(opens, dtype=np.float64)
        highs = np.asarray(highs, dtype=np.float64)
        lows = np.asarray(lows, dtype=np.float64)
        closes = np.asarray(closes, dtype=np.float64)

        valid = (opens > 0) & (highs > 0) & (lows > 0) & (closes > 0) & (highs >= lows)
        if valid.sum() < 2:
            return 0.0

        opens, highs, lows, closes = opens[valid], highs[valid], lows[valid], closes[valid]

        n = len(opens)
        log_hc = np.log(highs / closes)
        log_ho = np.log(highs / opens)
        log_lc = np.log(lows / closes)
        log_lo = np.log(lows / opens)

        variance = np.sum(log_hc * log_ho + log_lc * log_lo) / n

        if variance <= 0.0:
            return 0.0

        daily_vol = np.sqrt(variance)
        return float(daily_vol * _ANNUALIZATION_FACTOR)

    @staticmethod
    def yang_zhang(
        opens: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        period: int = 20,
    ) -> float:
        """
        Yang-Zhang (2000) combined volatility estimator.

        The most efficient estimator for OHLC data, combining:
        - Overnight volatility (close-to-open)
        - Open-to-close volatility
        - Rogers-Satchell estimator

        Handles both drift and opening jumps. Minimum variance estimator
        among all consistent estimators using OHLC.

        Args:
            opens: Array of open prices.
            highs: Array of high prices.
            lows: Array of low prices.
            closes: Array of close prices.
            period: Lookback period for computation.

        Returns:
            Annualized Yang-Zhang volatility estimate.
        """
        opens = np.asarray(opens, dtype=np.float64)
        highs = np.asarray(highs, dtype=np.float64)
        lows = np.asarray(lows, dtype=np.float64)
        closes = np.asarray(closes, dtype=np.float64)

        # Use the last 'period' bars but need at least period+1 for overnight returns
        n = min(period, len(opens))
        if n < 3:
            return 0.0

        opens = opens[-n:]
        highs = highs[-n:]
        lows = lows[-n:]
        closes = closes[-n:]

        valid = (opens > 0) & (highs > 0) & (lows > 0) & (closes > 0) & (highs >= lows)
        if valid.sum() < 3:
            return 0.0

        opens, highs, lows, closes = opens[valid], highs[valid], lows[valid], closes[valid]
        n = len(opens)
        if n < 3:
            return 0.0

        # Overnight returns: log(Open_t / Close_{t-1})
        # For the Yang-Zhang estimator we need overnight and open-to-close log returns.
        # Since the arrays already align by bar, we compute:
        #   overnight = log(Open[1:] / Close[:-1])
        #   open_close = log(Close[1:] / Open[1:])
        log_oc = np.log(opens[1:] / closes[:-1])  # overnight
        log_co = np.log(closes[1:] / opens[1:])    # open-to-close

        n_ret = len(log_oc)
        if n_ret < 2:
            return 0.0

        # Overnight variance
        mean_oc = np.mean(log_oc)
        sigma_open_sq = np.sum((log_oc - mean_oc) ** 2) / (n_ret - 1)

        # Close-to-open (open-to-close) variance
        mean_co = np.mean(log_co)
        sigma_close_sq = np.sum((log_co - mean_co) ** 2) / (n_ret - 1)

        # Rogers-Satchell variance on the aligned bars
        h = highs[1:]
        l = lows[1:]
        o = opens[1:]
        c = closes[1:]
        log_hc = np.log(h / c)
        log_ho = np.log(h / o)
        log_lc = np.log(l / c)
        log_lo = np.log(l / o)
        sigma_rs_sq = np.sum(log_hc * log_ho + log_lc * log_lo) / n_ret

        # Yang-Zhang optimal weighting factor
        k = 0.34 / (1.34 + (n_ret + 1) / (n_ret - 1))

        variance = sigma_open_sq + k * sigma_close_sq + (1.0 - k) * sigma_rs_sq

        if variance <= 0.0:
            return 0.0

        daily_vol = np.sqrt(variance)
        return float(daily_vol * _ANNUALIZATION_FACTOR)

    @staticmethod
    def realized_volatility(closes: np.ndarray, period: int = 20) -> float:
        """
        Standard close-to-close realized volatility.

        Computes the sample standard deviation of log returns, then
        annualizes by multiplying by sqrt(252).

        Args:
            closes: Array of closing prices.
            period: Number of most recent bars to use.

        Returns:
            Annualized realized volatility.
        """
        closes = np.asarray(closes, dtype=np.float64)
        n = min(period + 1, len(closes))
        if n < 3:
            return 0.0

        closes = closes[-n:]
        valid = closes > 0
        if valid.sum() < 3:
            return 0.0
        closes = closes[valid]

        log_returns = np.diff(np.log(closes))
        if len(log_returns) < 2:
            return 0.0

        daily_vol = np.std(log_returns, ddof=1)
        return float(daily_vol * _ANNUALIZATION_FACTOR)

    @staticmethod
    def volatility_cone(
        closes: np.ndarray,
        periods: list[int] | None = None,
    ) -> dict[int, dict[str, float]]:
        """
        Volatility cone: percentile rankings of current realized vol
        vs historical realized vol at multiple horizons.

        For each period, computes rolling realized volatility across the
        entire history and returns the current value's percentile rank
        along with key quantiles (min, 25th, 50th, 75th, max, current).

        Args:
            closes: Full array of closing prices.
            periods: List of lookback periods (in trading days).

        Returns:
            Dictionary keyed by period with sub-dictionary containing
            'current', 'percentile', 'min', 'p25', 'median', 'p75', 'max'.
        """
        if periods is None:
            periods = [5, 10, 20, 60, 120, 252]

        closes = np.asarray(closes, dtype=np.float64)
        valid = closes > 0
        if valid.sum() < 10:
            return {}

        closes = closes[valid]
        log_returns = np.diff(np.log(closes))
        if len(log_returns) < 10:
            return {}

        result: dict[int, dict[str, float]] = {}

        for period in periods:
            if len(log_returns) < period + 1:
                continue

            # Compute rolling realized vol for this period
            rolling_vols = []
            for i in range(period, len(log_returns) + 1):
                window = log_returns[i - period:i]
                vol = float(np.std(window, ddof=1) * _ANNUALIZATION_FACTOR)
                rolling_vols.append(vol)

            if len(rolling_vols) < 2:
                continue

            vols_arr = np.array(rolling_vols)
            current_vol = vols_arr[-1]

            result[period] = {
                "current": float(current_vol),
                "percentile": float(percentileofscore(vols_arr, current_vol, kind="rank")),
                "min": float(np.min(vols_arr)),
                "p25": float(np.percentile(vols_arr, 25)),
                "median": float(np.median(vols_arr)),
                "p75": float(np.percentile(vols_arr, 75)),
                "max": float(np.max(vols_arr)),
            }

        return result


class GARCH11:
    """
    GARCH(1,1) model for conditional volatility estimation and forecasting.

    Model specification:
        r_t = mu + epsilon_t
        epsilon_t = sigma_t * z_t,  z_t ~ N(0,1)
        sigma_t^2 = omega + alpha * epsilon_{t-1}^2 + beta * sigma_{t-1}^2

    Constraints:
        omega > 0, alpha > 0, beta > 0, alpha + beta < 1
    """

    def __init__(self) -> None:
        self.omega: float = 0.0
        self.alpha: float = 0.0
        self.beta: float = 0.0
        self.mu: float = 0.0
        self.log_likelihood: float = 0.0
        self._fitted: bool = False
        self._returns: np.ndarray = np.array([])
        self._conditional_variances: np.ndarray = np.array([])

    def fit(self, returns: np.ndarray) -> Optional[GARCHResult]:
        """
        Fit GARCH(1,1) to the return series using MLE.

        The log-likelihood for a Gaussian GARCH(1,1) is:
            L = -0.5 * sum[ log(2*pi) + log(sigma_t^2) + epsilon_t^2 / sigma_t^2 ]

        Optimization uses L-BFGS-B with analytical parameter bounds.

        Args:
            returns: Array of log returns (not percentage returns).

        Returns:
            GARCHResult with fitted parameters and forecasts,
            or None if fitting fails.
        """
        returns = np.asarray(returns, dtype=np.float64)

        # Remove NaN/Inf
        valid = np.isfinite(returns)
        returns = returns[valid]

        if len(returns) < _MIN_BARS_GARCH:
            logger.debug("Insufficient data for GARCH fitting: %d bars", len(returns))
            return None

        self._returns = returns
        self.mu = float(np.mean(returns))
        residuals = returns - self.mu

        # Initial parameter guesses from unconditional variance
        sample_var = float(np.var(residuals))
        if sample_var <= 0:
            return None

        # Starting values: alpha=0.05, beta=0.90, omega derived from unconditional
        alpha_init = 0.05
        beta_init = 0.90
        omega_init = sample_var * (1.0 - alpha_init - beta_init)

        x0 = np.array([omega_init, alpha_init, beta_init])

        # Bounds: omega > 1e-10, alpha in (1e-6, 0.5), beta in (1e-6, 0.999)
        bounds = [
            (1e-10, 10.0 * sample_var),
            (1e-6, 0.5),
            (1e-6, 0.9999),
        ]

        def neg_log_likelihood(params: np.ndarray) -> float:
            """Negative log-likelihood for minimization."""
            omega, alpha, beta = params

            # Stationarity constraint
            if alpha + beta >= 1.0:
                return 1e10

            n = len(residuals)
            sigma2 = np.empty(n)
            sigma2[0] = sample_var

            for t in range(1, n):
                sigma2[t] = omega + alpha * residuals[t - 1] ** 2 + beta * sigma2[t - 1]
                # Numerical floor to prevent log(0)
                if sigma2[t] < 1e-20:
                    sigma2[t] = 1e-20

            # Log-likelihood (drop constant -0.5*n*log(2*pi) since it does not
            # affect optimization)
            ll = -0.5 * np.sum(np.log(sigma2) + residuals ** 2 / sigma2)

            if not np.isfinite(ll):
                return 1e10

            return -ll

        # Stationarity constraint: alpha + beta < 1
        constraint = {
            "type": "ineq",
            "fun": lambda p: 0.9999 - p[1] - p[2],
        }

        try:
            result = minimize(
                neg_log_likelihood,
                x0,
                method="L-BFGS-B",
                bounds=bounds,
                options={"maxiter": 500, "ftol": 1e-10},
            )

            # If L-BFGS-B fails, fall back to Nelder-Mead with constraint check
            if not result.success:
                result = minimize(
                    neg_log_likelihood,
                    x0,
                    method="SLSQP",
                    bounds=bounds,
                    constraints=[constraint],
                    options={"maxiter": 500, "ftol": 1e-10},
                )

        except Exception as exc:
            logger.debug("GARCH optimization failed: %s", exc)
            return None

        omega_fit, alpha_fit, beta_fit = result.x
        persistence = alpha_fit + beta_fit

        # Verify stationarity
        if persistence >= 1.0:
            logger.debug("GARCH fit non-stationary: alpha+beta=%.4f", persistence)
            return None

        self.omega = float(omega_fit)
        self.alpha = float(alpha_fit)
        self.beta = float(beta_fit)
        self.log_likelihood = float(-result.fun)
        self._fitted = True

        # Recompute conditional variances with fitted parameters
        n = len(residuals)
        sigma2 = np.empty(n)
        sigma2[0] = sample_var
        for t in range(1, n):
            sigma2[t] = self.omega + self.alpha * residuals[t - 1] ** 2 + self.beta * sigma2[t - 1]
            if sigma2[t] < 1e-20:
                sigma2[t] = 1e-20
        self._conditional_variances = sigma2

        # Unconditional (long-run) variance
        unconditional_var = self.omega / (1.0 - persistence)
        unconditional_vol = float(np.sqrt(unconditional_var) * _ANNUALIZATION_FACTOR)

        # Current conditional volatility
        current_var = sigma2[-1]
        current_vol = float(np.sqrt(current_var) * _ANNUALIZATION_FACTOR)

        # Multi-step forecasts
        forecast_1d = self.forecast(1)
        forecast_5d = self.forecast(5)
        forecast_20d = self.forecast(20)

        # Information criteria
        k = 3  # number of parameters
        n_obs = len(returns)
        aic = -2.0 * self.log_likelihood + 2.0 * k
        bic = -2.0 * self.log_likelihood + k * np.log(n_obs)

        return GARCHResult(
            omega=self.omega,
            alpha=self.alpha,
            beta=self.beta,
            persistence=float(persistence),
            unconditional_vol=unconditional_vol,
            current_vol=current_vol,
            forecast_1d=forecast_1d,
            forecast_5d=forecast_5d,
            forecast_20d=forecast_20d,
            log_likelihood=self.log_likelihood,
            aic=float(aic),
            bic=float(bic),
        )

    def forecast(self, horizon: int) -> float:
        """
        Multi-step ahead volatility forecast.

        The h-step ahead conditional variance forecast for GARCH(1,1) is:
            sigma^2_{t+h|t} = V_L + (alpha + beta)^{h-1} * (sigma^2_{t+1|t} - V_L)
        where V_L = omega / (1 - alpha - beta) is unconditional variance.

        Args:
            horizon: Number of steps ahead (in trading days).

        Returns:
            Annualized volatility forecast for the given horizon.
        """
        if not self._fitted or len(self._conditional_variances) == 0:
            return 0.0

        persistence = self.alpha + self.beta
        if persistence >= 1.0:
            # Non-stationary: return current vol
            current_var = self._conditional_variances[-1]
            return float(np.sqrt(current_var) * _ANNUALIZATION_FACTOR)

        unconditional_var = self.omega / (1.0 - persistence)

        # One-step-ahead forecast
        last_var = self._conditional_variances[-1]
        last_resid = self._returns[-1] - self.mu
        one_step_var = self.omega + self.alpha * last_resid ** 2 + self.beta * last_var

        if horizon <= 1:
            return float(np.sqrt(max(one_step_var, 0.0)) * _ANNUALIZATION_FACTOR)

        # Multi-step: average variance over the forecast horizon
        # sigma^2_{t+h} = V_L + (alpha+beta)^(h-1) * (sigma^2_{t+1} - V_L)
        total_var = 0.0
        for h in range(1, horizon + 1):
            step_var = unconditional_var + persistence ** (h - 1) * (one_step_var - unconditional_var)
            total_var += step_var

        avg_var = total_var / horizon
        return float(np.sqrt(max(avg_var, 0.0)) * _ANNUALIZATION_FACTOR)


class MarkovRegimeSwitcher:
    """
    Two-state Markov regime-switching model for volatility regime detection.

    Assumes returns are drawn from one of two normal distributions
    (low-volatility and high-volatility regimes), with regime transitions
    governed by a 2x2 transition probability matrix.

    Estimation is performed using the Expectation-Maximization (EM) algorithm
    (Hamilton filter + Baum-Welch smoothing).
    """

    def __init__(self, max_iter: int = 200, tol: float = 1e-6) -> None:
        self.max_iter = max_iter
        self.tol = tol

        # Model parameters (initialized on fit)
        self.means: np.ndarray = np.zeros(2)
        self.variances: np.ndarray = np.ones(2)
        self.transition_matrix: np.ndarray = np.array([[0.95, 0.05], [0.10, 0.90]])
        self.steady_state_probs: np.ndarray = np.array([0.5, 0.5])
        self._fitted: bool = False

    def _gaussian_pdf(self, x: np.ndarray, mu: float, sigma2: float) -> np.ndarray:
        """Evaluate Gaussian density, numerically stabilized."""
        sigma2 = max(sigma2, 1e-20)
        return np.exp(-0.5 * (x - mu) ** 2 / sigma2) / np.sqrt(2.0 * np.pi * sigma2)

    def detect_regime(
        self, returns: np.ndarray
    ) -> Optional[dict]:
        """
        Detect the current volatility regime via EM on a 2-state model.

        Args:
            returns: Array of log returns.

        Returns:
            Dictionary with:
                'regime': 0 (low-vol) or 1 (high-vol)
                'regime_probability': probability of current regime
                'transition_matrix': 2x2 transition matrix
                'means': [mu_low, mu_high]
                'volatilities': [sigma_low_ann, sigma_high_ann]
                'smoothed_probs': (T, 2) array of smoothed state probabilities
            or None if estimation fails.
        """
        returns = np.asarray(returns, dtype=np.float64)
        valid = np.isfinite(returns)
        returns = returns[valid]

        if len(returns) < _MIN_BARS_REGIME:
            return None

        T = len(returns)

        # Initialize parameters using simple k-means-like heuristic
        median_abs = np.median(np.abs(returns - np.mean(returns)))
        sorted_abs = np.sort(np.abs(returns - np.mean(returns)))
        threshold = sorted_abs[int(0.7 * len(sorted_abs))]

        low_mask = np.abs(returns - np.mean(returns)) <= threshold
        high_mask = ~low_mask

        if low_mask.sum() < 5 or high_mask.sum() < 5:
            # Fallback: split by median
            low_mask = np.abs(returns - np.mean(returns)) <= median_abs
            high_mask = ~low_mask

        mu = np.array([
            np.mean(returns[low_mask]) if low_mask.sum() > 0 else np.mean(returns),
            np.mean(returns[high_mask]) if high_mask.sum() > 0 else np.mean(returns),
        ])
        sigma2 = np.array([
            max(np.var(returns[low_mask]), 1e-10) if low_mask.sum() > 1 else np.var(returns),
            max(np.var(returns[high_mask]), 1e-10) if high_mask.sum() > 1 else np.var(returns) * 2.0,
        ])

        # Ensure state 0 is low-vol, state 1 is high-vol
        if sigma2[0] > sigma2[1]:
            mu = mu[::-1]
            sigma2 = sigma2[::-1]

        # Transition matrix initialization
        P = np.array([[0.95, 0.05], [0.10, 0.90]])

        # Steady-state (ergodic) probabilities
        pi_ss = np.array([P[1, 0] / (P[0, 1] + P[1, 0]), P[0, 1] / (P[0, 1] + P[1, 0])])

        prev_ll = -np.inf

        for iteration in range(self.max_iter):
            # ============= E-step: Hamilton filter (forward) =============
            # Filtered probabilities: P(S_t = j | y_1, ..., y_t)
            filtered = np.zeros((T, 2))
            predictive = np.zeros((T, 2))
            ll = 0.0

            # t = 0
            eta = np.array([
                self._gaussian_pdf(returns[0:1], mu[0], sigma2[0])[0],
                self._gaussian_pdf(returns[0:1], mu[1], sigma2[1])[0],
            ])
            joint = pi_ss * eta
            f_sum = joint.sum()
            if f_sum < 1e-300:
                f_sum = 1e-300
            filtered[0] = joint / f_sum
            predictive[0] = pi_ss
            ll += np.log(f_sum)

            for t in range(1, T):
                # Predict: P(S_t = j | y_{1:t-1}) = sum_i P(S_{t-1}=i|y_{1:t-1}) * P_{ij}
                pred = filtered[t - 1] @ P
                pred = np.maximum(pred, 1e-300)
                predictive[t] = pred

                # Update
                eta = np.array([
                    self._gaussian_pdf(returns[t:t + 1], mu[0], sigma2[0])[0],
                    self._gaussian_pdf(returns[t:t + 1], mu[1], sigma2[1])[0],
                ])
                joint = pred * eta
                f_sum = joint.sum()
                if f_sum < 1e-300:
                    f_sum = 1e-300
                filtered[t] = joint / f_sum
                ll += np.log(f_sum)

            # Check convergence
            if np.isfinite(ll) and abs(ll - prev_ll) < self.tol:
                break
            if not np.isfinite(ll):
                logger.debug("Markov regime EM: log-likelihood became non-finite at iter %d", iteration)
                break
            prev_ll = ll

            # ============= E-step: Kim smoother (backward) =============
            smoothed = np.zeros((T, 2))
            smoothed[T - 1] = filtered[T - 1]

            for t in range(T - 2, -1, -1):
                for i in range(2):
                    s = 0.0
                    for j in range(2):
                        pred_j = predictive[t + 1][j]
                        if pred_j < 1e-300:
                            pred_j = 1e-300
                        s += P[i, j] * smoothed[t + 1][j] / pred_j
                    smoothed[t][i] = filtered[t][i] * s

                sm_sum = smoothed[t].sum()
                if sm_sum > 0:
                    smoothed[t] /= sm_sum

            # ============= M-step =============
            # Expected joint probabilities for transition matrix
            xi_sum = np.zeros((2, 2))
            for t in range(T - 1):
                for i in range(2):
                    for j in range(2):
                        pred_j = predictive[t + 1][j]
                        if pred_j < 1e-300:
                            pred_j = 1e-300
                        xi_sum[i, j] += (
                            filtered[t][i] * P[i, j]
                            * self._gaussian_pdf(returns[t + 1:t + 2], mu[j], sigma2[j])[0]
                            * smoothed[t + 1][j] / pred_j
                        )

            # Normalize transition matrix rows
            for i in range(2):
                row_sum = xi_sum[i].sum()
                if row_sum > 0:
                    P[i] = xi_sum[i] / row_sum
                # Ensure no zeros
                P[i] = np.maximum(P[i], 1e-6)
                P[i] /= P[i].sum()

            # Update means and variances
            for j in range(2):
                gamma_j = smoothed[:, j]
                gamma_sum = gamma_j.sum()
                if gamma_sum < 1e-10:
                    continue
                mu[j] = np.sum(gamma_j * returns) / gamma_sum
                sigma2[j] = np.sum(gamma_j * (returns - mu[j]) ** 2) / gamma_sum
                sigma2[j] = max(sigma2[j], 1e-10)

            # Enforce ordering: state 0 = low-vol, state 1 = high-vol
            if sigma2[0] > sigma2[1]:
                mu = mu[::-1]
                sigma2 = sigma2[::-1]
                P = P[::-1, ::-1]
                smoothed = smoothed[:, ::-1]
                filtered = filtered[:, ::-1]

            # Update steady-state
            denom = P[0, 1] + P[1, 0]
            if denom > 0:
                pi_ss = np.array([P[1, 0] / denom, P[0, 1] / denom])
            else:
                pi_ss = np.array([0.5, 0.5])

        # Store fitted parameters
        self.means = mu
        self.variances = sigma2
        self.transition_matrix = P
        self.steady_state_probs = pi_ss
        self._fitted = True

        # Current regime (last time step)
        current_probs = smoothed[-1]
        current_regime = int(np.argmax(current_probs))
        regime_prob = float(current_probs[current_regime])

        ann_vols = np.sqrt(sigma2) * _ANNUALIZATION_FACTOR

        return {
            "regime": current_regime,
            "regime_probability": regime_prob,
            "transition_matrix": P.tolist(),
            "means": mu.tolist(),
            "volatilities": ann_vols.tolist(),
            "smoothed_probs": smoothed,
        }


class HawkesProcess:
    """
    Univariate Hawkes process for detecting volatility clustering.

    The Hawkes process is a self-exciting point process where past events
    increase the intensity of future events. The conditional intensity is:

        lambda(t) = mu + sum_{t_i < t} alpha * exp(-beta * (t - t_i))

    where:
        mu    > 0  : baseline intensity
        alpha > 0  : excitation magnitude
        beta  > alpha : decay rate (ensures stationarity)

    Useful for quantifying how clustered volatility events are. A higher
    clustering score indicates stronger self-excitation (volatility begets
    volatility).
    """

    def __init__(self) -> None:
        self.mu: float = 0.0
        self.alpha: float = 0.0
        self.beta: float = 0.0
        self._fitted: bool = False
        self._event_times: np.ndarray = np.array([])

    def fit(self, event_times: np.ndarray) -> bool:
        """
        Estimate Hawkes process parameters via MLE.

        The log-likelihood for a Hawkes process on [0, T] is:
            L = sum_i log(lambda(t_i)) - integral_0^T lambda(s) ds

        The integral of lambda has a closed form for exponential kernels:
            integral = mu * T + (alpha / beta) * sum_i [1 - exp(-beta*(T - t_i))]

        Args:
            event_times: Sorted array of event occurrence times.

        Returns:
            True if fitting succeeded, False otherwise.
        """
        event_times = np.asarray(event_times, dtype=np.float64)
        event_times = np.sort(event_times)

        if len(event_times) < 10:
            logger.debug("Insufficient events for Hawkes fitting: %d", len(event_times))
            return False

        self._event_times = event_times
        T = event_times[-1] - event_times[0]
        if T <= 0:
            return False

        # Shift to start at 0
        times = event_times - event_times[0]
        n = len(times)
        T = times[-1]

        def neg_log_likelihood(params: np.ndarray) -> float:
            mu, alpha, beta = params

            # Stationarity: alpha < beta (branching ratio < 1)
            if alpha >= beta:
                return 1e10

            # Compute intensity at each event
            intensities = np.empty(n)
            # Use recursive computation for efficiency
            # A_i = sum_{j<i} exp(-beta*(t_i - t_j))
            # A_i = exp(-beta*(t_i - t_{i-1})) * (1 + A_{i-1})
            A = 0.0
            intensities[0] = mu
            for i in range(1, n):
                dt = times[i] - times[i - 1]
                A = np.exp(-beta * dt) * (1.0 + A)
                intensities[i] = mu + alpha * A

            # Log-likelihood
            # sum log(lambda(t_i))
            log_intensities = np.log(np.maximum(intensities, 1e-300))
            ll_events = np.sum(log_intensities)

            # Compensator: integral of lambda(t) over [0, T]
            # = mu * T + (alpha/beta) * sum_i [1 - exp(-beta*(T - t_i))]
            compensator = mu * T
            if beta > 0:
                compensator += (alpha / beta) * np.sum(1.0 - np.exp(-beta * (T - times)))

            ll = ll_events - compensator

            if not np.isfinite(ll):
                return 1e10

            return -ll

        # Initial guesses
        avg_rate = n / T
        mu0 = avg_rate * 0.5
        alpha0 = 0.2
        beta0 = 1.0

        bounds = [
            (1e-6, avg_rate * 5.0),
            (1e-6, 10.0),
            (1e-4, 50.0),
        ]

        try:
            result = minimize(
                neg_log_likelihood,
                np.array([mu0, alpha0, beta0]),
                method="L-BFGS-B",
                bounds=bounds,
                options={"maxiter": 300, "ftol": 1e-10},
            )
        except Exception as exc:
            logger.debug("Hawkes MLE failed: %s", exc)
            return False

        if not result.success:
            # Try alternative starting point
            try:
                result = minimize(
                    neg_log_likelihood,
                    np.array([avg_rate * 0.7, 0.5, 2.0]),
                    method="L-BFGS-B",
                    bounds=bounds,
                    options={"maxiter": 300, "ftol": 1e-10},
                )
            except Exception:
                return False

        self.mu = float(result.x[0])
        self.alpha = float(result.x[1])
        self.beta = float(result.x[2])
        self._fitted = True

        return True

    def clustering_score(self) -> float:
        """
        Compute a 0-1 clustering score based on the branching ratio.

        The branching ratio n* = alpha / beta gives the expected number of
        child events per parent event. Values close to 1 indicate strong
        clustering (critical process). Values close to 0 indicate a nearly
        Poisson (unclustered) process.

        Returns:
            Score in [0, 1] where 0 = no clustering, 1 = maximal clustering.
        """
        if not self._fitted or self.beta <= 0:
            return 0.0

        branching_ratio = self.alpha / self.beta
        # Clamp to [0, 1) since at branching_ratio >= 1 the process is non-stationary
        return float(min(max(branching_ratio, 0.0), 0.999))


@dataclass
class VolatilityAnalysis:
    """Container for all volatility analysis results for a single symbol."""
    symbol: str
    parkinson_vol: float = 0.0
    garman_klass_vol: float = 0.0
    rogers_satchell_vol: float = 0.0
    yang_zhang_vol: float = 0.0
    realized_vol_5d: float = 0.0
    realized_vol_20d: float = 0.0
    realized_vol_60d: float = 0.0
    garch_result: Optional[GARCHResult] = None
    regime_info: Optional[dict] = None
    vol_cone: dict = field(default_factory=dict)
    hawkes_score: float = 0.0
    vol_percentile_20d: float = 50.0
    vol_z_score: float = 0.0
    vol_term_structure: str = "flat"
    is_compression: bool = False
    is_expansion: bool = False
    regime_change_detected: bool = False
    supporting_evidence: list[str] = field(default_factory=list)
    contradicting_evidence: list[str] = field(default_factory=list)


class VolatilityRegimeScanner(BaseScanner[AdvancedScanResult]):
    """
    Institutional-grade volatility regime scanner.

    Combines multiple volatility estimators, GARCH conditional volatility,
    Markov regime-switching, and Hawkes clustering detection to identify:
    - Volatility compression (precursor to breakout)
    - Volatility expansion (risk-off regime shift)
    - Regime transitions between low-vol and high-vol states
    - Vol term structure anomalies (contango / backwardation)

    Signals:
        BULLISH  - Vol compression detected (breakout expected, long vol)
        BEARISH  - Vol expansion / regime shift to high-vol (risk-off)
    """

    # Thresholds for signal generation
    _COMPRESSION_RATIO = 0.60     # short-term / long-term vol ratio threshold
    _EXPANSION_RATIO = 1.50       # short-term / long-term vol ratio threshold
    _REGIME_PROB_THRESHOLD = 0.70  # minimum probability for regime call
    _VOL_ZSCORE_COMPRESSION = -1.5
    _VOL_ZSCORE_EXPANSION = 1.5
    _VOL_PERCENTILE_LOW = 15.0
    _VOL_PERCENTILE_HIGH = 85.0
    _MIN_ESTIMATOR_AGREEMENT = 3  # minimum number of estimators agreeing

    def __init__(self, config: Optional[ScannerConfig] = None) -> None:
        super().__init__(
            name="volatility_regime",
            scan_mode=ScanMode.ALL,
            config=config,
        )
        self._estimators = VolatilityEstimators()
        self._garch = GARCH11()
        self._regime_switcher = MarkovRegimeSwitcher()
        self._hawkes = HawkesProcess()

    async def scan(self, context: ScanContext) -> list[AdvancedScanResult]:
        """
        Scan all symbols in the universe for volatility regime events.

        For each symbol:
            1. Compute all volatility estimators
            2. Fit GARCH(1,1) for conditional vol forecast
            3. Run Markov regime detection
            4. Assess vol compression / expansion
            5. Analyse vol term structure
            6. Detect vol clustering via Hawkes process
            7. Generate signal if regime change or significant event found

        Args:
            context: Scan context with market data and historical data.

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
                self._logger.warning("Error scanning %s for volatility: %s", symbol, exc)

        return results

    def _scan_symbol(
        self, symbol: str, context: ScanContext
    ) -> Optional[AdvancedScanResult]:
        """Run full volatility analysis on a single symbol."""
        market_data = context.market_data.get(symbol)
        hist_data = context.historical_data.get(symbol)

        if not market_data or not hist_data:
            return None

        if not self.apply_filters(market_data):
            return None

        if len(hist_data.bars) < _MIN_BARS_BASIC:
            return None

        # Extract OHLC arrays
        opens = np.array([b.open for b in hist_data.bars], dtype=np.float64)
        highs = np.array([b.high for b in hist_data.bars], dtype=np.float64)
        lows = np.array([b.low for b in hist_data.bars], dtype=np.float64)
        closes = np.array([b.close for b in hist_data.bars], dtype=np.float64)

        analysis = VolatilityAnalysis(symbol=symbol)

        # ------------------------------------------------------------------
        # 1. Compute all volatility estimators
        # ------------------------------------------------------------------
        analysis.parkinson_vol = VolatilityEstimators.parkinson(highs, lows)
        analysis.garman_klass_vol = VolatilityEstimators.garman_klass(opens, highs, lows, closes)
        analysis.rogers_satchell_vol = VolatilityEstimators.rogers_satchell(opens, highs, lows, closes)
        analysis.yang_zhang_vol = VolatilityEstimators.yang_zhang(opens, highs, lows, closes)

        # Multi-horizon realized vol
        analysis.realized_vol_5d = VolatilityEstimators.realized_volatility(closes, period=5)
        analysis.realized_vol_20d = VolatilityEstimators.realized_volatility(closes, period=20)
        analysis.realized_vol_60d = VolatilityEstimators.realized_volatility(closes, period=60)

        # ------------------------------------------------------------------
        # 2. Volatility cone for percentile ranking
        # ------------------------------------------------------------------
        if len(closes) >= 30:
            analysis.vol_cone = VolatilityEstimators.volatility_cone(closes)
            cone_20 = analysis.vol_cone.get(20)
            if cone_20:
                analysis.vol_percentile_20d = cone_20["percentile"]
                median_vol = cone_20["median"]
                p75 = cone_20["p75"]
                p25 = cone_20["p25"]
                iqr = p75 - p25
                if iqr > 0:
                    analysis.vol_z_score = (cone_20["current"] - median_vol) / (iqr / 1.35)
                else:
                    analysis.vol_z_score = 0.0

        # ------------------------------------------------------------------
        # 3. GARCH(1,1) fit and forecast
        # ------------------------------------------------------------------
        if len(closes) >= _MIN_BARS_GARCH + 1:
            log_returns = np.diff(np.log(closes[closes > 0]))
            valid_returns = log_returns[np.isfinite(log_returns)]
            if len(valid_returns) >= _MIN_BARS_GARCH:
                garch = GARCH11()
                analysis.garch_result = garch.fit(valid_returns)

        # ------------------------------------------------------------------
        # 4. Markov regime detection
        # ------------------------------------------------------------------
        if len(closes) >= _MIN_BARS_REGIME + 1:
            log_returns = np.diff(np.log(closes[closes > 0]))
            valid_returns = log_returns[np.isfinite(log_returns)]
            if len(valid_returns) >= _MIN_BARS_REGIME:
                switcher = MarkovRegimeSwitcher()
                analysis.regime_info = switcher.detect_regime(valid_returns)

        # ------------------------------------------------------------------
        # 5. Hawkes process for clustering
        # ------------------------------------------------------------------
        if len(closes) >= _MIN_BARS_GARCH + 1:
            log_returns = np.diff(np.log(closes[closes > 0]))
            valid_returns = log_returns[np.isfinite(log_returns)]
            if len(valid_returns) >= _MIN_BARS_GARCH:
                # Define "volatility events" as returns exceeding 1.5 sigma
                ret_std = np.std(valid_returns)
                if ret_std > 0:
                    threshold = 1.5 * ret_std
                    event_indices = np.where(np.abs(valid_returns) > threshold)[0]
                    if len(event_indices) >= 10:
                        hawkes = HawkesProcess()
                        event_times = event_indices.astype(np.float64)
                        if hawkes.fit(event_times):
                            analysis.hawkes_score = hawkes.clustering_score()

        # ------------------------------------------------------------------
        # 6. Vol compression / expansion detection
        # ------------------------------------------------------------------
        analysis = self._detect_vol_events(analysis)

        # ------------------------------------------------------------------
        # 7. Vol term structure
        # ------------------------------------------------------------------
        analysis.vol_term_structure = self._classify_term_structure(analysis)

        # ------------------------------------------------------------------
        # 8. Determine if we should emit a signal
        # ------------------------------------------------------------------
        return self._generate_result(analysis, market_data, context)

    def _detect_vol_events(self, analysis: VolatilityAnalysis) -> VolatilityAnalysis:
        """Detect vol compression, expansion, and regime changes."""
        evidence = []
        contra = []

        # --- Compression checks ---
        compression_count = 0

        # Check short-term / long-term ratio
        if analysis.realized_vol_60d > 0:
            ratio_5_60 = analysis.realized_vol_5d / analysis.realized_vol_60d
            ratio_20_60 = analysis.realized_vol_20d / analysis.realized_vol_60d

            if ratio_5_60 < self._COMPRESSION_RATIO:
                compression_count += 1
                evidence.append(
                    f"5d/60d vol ratio={ratio_5_60:.2f} below {self._COMPRESSION_RATIO}"
                )
            elif ratio_5_60 > self._EXPANSION_RATIO:
                evidence.append(
                    f"5d/60d vol ratio={ratio_5_60:.2f} above {self._EXPANSION_RATIO} (expansion)"
                )

            if ratio_20_60 < self._COMPRESSION_RATIO:
                compression_count += 1
                evidence.append(
                    f"20d/60d vol ratio={ratio_20_60:.2f} below {self._COMPRESSION_RATIO}"
                )

        # Check vol percentile
        if analysis.vol_percentile_20d < self._VOL_PERCENTILE_LOW:
            compression_count += 1
            evidence.append(
                f"Vol percentile={analysis.vol_percentile_20d:.0f}th (below {self._VOL_PERCENTILE_LOW:.0f}th)"
            )

        # Check vol z-score
        if analysis.vol_z_score < self._VOL_ZSCORE_COMPRESSION:
            compression_count += 1
            evidence.append(
                f"Vol z-score={analysis.vol_z_score:.2f} (compression)"
            )

        # Check GARCH: forecast vol < unconditional vol significantly
        if analysis.garch_result is not None:
            garch = analysis.garch_result
            if garch.unconditional_vol > 0:
                garch_ratio = garch.current_vol / garch.unconditional_vol
                if garch_ratio < 0.7:
                    compression_count += 1
                    evidence.append(
                        f"GARCH current/unconditional={garch_ratio:.2f} (below mean)"
                    )
                elif garch_ratio > 1.5:
                    evidence.append(
                        f"GARCH current/unconditional={garch_ratio:.2f} (above mean, expansion)"
                    )

        # Check Markov regime
        if analysis.regime_info is not None:
            regime = analysis.regime_info["regime"]
            prob = analysis.regime_info["regime_probability"]
            if regime == 0 and prob > self._REGIME_PROB_THRESHOLD:
                compression_count += 1
                evidence.append(
                    f"Markov regime=low-vol (p={prob:.2f})"
                )
            elif regime == 1 and prob > self._REGIME_PROB_THRESHOLD:
                evidence.append(
                    f"Markov regime=high-vol (p={prob:.2f})"
                )

        # --- Expansion checks ---
        expansion_count = 0

        if analysis.realized_vol_60d > 0:
            ratio_5_60 = analysis.realized_vol_5d / analysis.realized_vol_60d
            if ratio_5_60 > self._EXPANSION_RATIO:
                expansion_count += 1

        if analysis.vol_percentile_20d > self._VOL_PERCENTILE_HIGH:
            expansion_count += 1
            evidence.append(
                f"Vol percentile={analysis.vol_percentile_20d:.0f}th (above {self._VOL_PERCENTILE_HIGH:.0f}th)"
            )

        if analysis.vol_z_score > self._VOL_ZSCORE_EXPANSION:
            expansion_count += 1
            evidence.append(
                f"Vol z-score={analysis.vol_z_score:.2f} (expansion)"
            )

        if analysis.garch_result is not None:
            garch = analysis.garch_result
            if garch.unconditional_vol > 0 and garch.current_vol / garch.unconditional_vol > 1.5:
                expansion_count += 1

        if analysis.regime_info is not None:
            regime = analysis.regime_info["regime"]
            prob = analysis.regime_info["regime_probability"]
            if regime == 1 and prob > self._REGIME_PROB_THRESHOLD:
                expansion_count += 1

        # Hawkes clustering adds to expansion evidence
        if analysis.hawkes_score > 0.5:
            expansion_count += 1
            evidence.append(
                f"Hawkes clustering score={analysis.hawkes_score:.2f} (elevated)"
            )

        # Determine overall state
        analysis.is_compression = compression_count >= self._MIN_ESTIMATOR_AGREEMENT
        analysis.is_expansion = expansion_count >= self._MIN_ESTIMATOR_AGREEMENT

        # Regime change detection: check if recent regime differs from longer-term
        if analysis.regime_info is not None:
            smoothed = analysis.regime_info.get("smoothed_probs")
            if smoothed is not None and len(smoothed) >= 20:
                recent_regime = int(np.argmax(smoothed[-1]))
                lookback_regime = int(np.argmax(np.mean(smoothed[-20:-5], axis=0)))
                if recent_regime != lookback_regime:
                    analysis.regime_change_detected = True
                    evidence.append(
                        f"Regime transition detected: {'low->high' if recent_regime == 1 else 'high->low'}"
                    )

        # Contradicting evidence
        if analysis.is_compression and analysis.hawkes_score > 0.4:
            contra.append(
                f"Hawkes clustering={analysis.hawkes_score:.2f} despite compression"
            )
        if analysis.is_expansion and analysis.vol_percentile_20d < 50:
            contra.append(
                f"Vol percentile={analysis.vol_percentile_20d:.0f}th low despite expansion signals"
            )

        analysis.supporting_evidence = evidence
        analysis.contradicting_evidence = contra

        return analysis

    def _classify_term_structure(self, analysis: VolatilityAnalysis) -> str:
        """
        Classify the volatility term structure.

        Contango:        short-term < long-term (normal, calm market)
        Backwardation:   short-term > long-term (fear, hedging demand)
        Flat:            approximately equal
        """
        if analysis.realized_vol_60d <= 0 or analysis.realized_vol_5d <= 0:
            return "flat"

        ratio = analysis.realized_vol_5d / analysis.realized_vol_60d

        if ratio < 0.85:
            return "contango"
        elif ratio > 1.15:
            return "backwardation"
        return "flat"

    def _classify_vol_regime(self, analysis: VolatilityAnalysis) -> VolatilityRegime:
        """Map the quantitative vol analysis to a named regime."""
        pct = analysis.vol_percentile_20d

        if pct <= 5:
            return VolatilityRegime.ULTRA_LOW
        elif pct <= 20:
            return VolatilityRegime.LOW
        elif pct <= 50:
            return VolatilityRegime.NORMAL
        elif pct <= 75:
            return VolatilityRegime.ELEVATED
        elif pct <= 95:
            return VolatilityRegime.HIGH
        return VolatilityRegime.EXTREME

    def _determine_regime_context(self, analysis: VolatilityAnalysis) -> RegimeContext:
        """Map the volatility state to a RegimeContext enum."""
        if analysis.is_compression:
            return RegimeContext.QUIET
        if analysis.is_expansion:
            if analysis.vol_percentile_20d > 95:
                return RegimeContext.CRISIS
            return RegimeContext.VOLATILE
        if analysis.regime_change_detected:
            return RegimeContext.TRANSITION
        if analysis.vol_percentile_20d < 30:
            return RegimeContext.QUIET
        if analysis.vol_percentile_20d > 70:
            return RegimeContext.VOLATILE
        return RegimeContext.RANGING

    def _generate_result(
        self,
        analysis: VolatilityAnalysis,
        market_data: MarketData,
        context: ScanContext,
    ) -> Optional[AdvancedScanResult]:
        """
        Generate an AdvancedScanResult if a significant vol event is detected.

        Returns None if no actionable signal is present.
        """
        has_signal = (
            analysis.is_compression
            or analysis.is_expansion
            or analysis.regime_change_detected
        )

        if not has_signal:
            return None

        # Determine signal direction
        if analysis.is_compression:
            signal_direction = "BULLISH"
        elif analysis.is_expansion:
            signal_direction = "BEARISH"
        elif analysis.regime_change_detected and analysis.regime_info is not None:
            # Transition to high-vol = bearish; to low-vol = bullish
            if analysis.regime_info["regime"] == 1:
                signal_direction = "BEARISH"
            else:
                signal_direction = "BULLISH"
        else:
            signal_direction = "NEUTRAL"

        # Signal strength based on evidence count
        total_evidence = len(analysis.supporting_evidence)
        signal_strength = min(1.0, total_evidence * 0.15)

        # Confidence: higher with more agreement, lower with contradictions
        confidence = min(1.0, 0.3 + total_evidence * 0.10 - len(analysis.contradicting_evidence) * 0.05)
        confidence = max(0.1, confidence)

        # Expected move based on current vol
        best_vol = analysis.yang_zhang_vol if analysis.yang_zhang_vol > 0 else analysis.realized_vol_20d
        # Daily expected move (1-sigma) annualized vol / sqrt(252)
        daily_1sigma = best_vol / _ANNUALIZATION_FACTOR if best_vol > 0 else 0.02
        expected_move_pct = daily_1sigma * 100.0 * 5.0  # 5-day expected move

        if analysis.is_compression:
            # Compression: expect a larger breakout move
            expected_move_pct *= 1.5

        # Trade levels
        entry_price = market_data.close
        atr = market_data.atr if market_data.atr else entry_price * daily_1sigma
        stop_distance = atr * 2.0

        if signal_direction == "BULLISH":
            stop_loss = entry_price - stop_distance
            target = entry_price + stop_distance * 2.0
        elif signal_direction == "BEARISH":
            stop_loss = entry_price + stop_distance
            target = entry_price - stop_distance * 2.0
        else:
            stop_loss = entry_price - stop_distance
            target = entry_price + stop_distance

        risk = abs(entry_price - stop_loss)
        reward = abs(target - entry_price)
        rr_ratio = reward / risk if risk > 0 else 0.0

        # Regime context
        regime_context = self._determine_regime_context(analysis)
        vol_regime = self._classify_vol_regime(analysis)

        # Mathematical basis description
        math_basis_parts = [
            "Yang-Zhang combined OHLC estimator",
            "Parkinson high-low range estimator",
            "Garman-Klass OHLC estimator",
            "Rogers-Satchell drift-robust estimator",
        ]
        if analysis.garch_result is not None:
            math_basis_parts.append(
                f"GARCH(1,1) MLE (alpha={analysis.garch_result.alpha:.3f}, "
                f"beta={analysis.garch_result.beta:.3f}, "
                f"persistence={analysis.garch_result.persistence:.3f})"
            )
        if analysis.regime_info is not None:
            math_basis_parts.append(
                "2-state Markov regime-switching (Hamilton EM filter)"
            )
        if analysis.hawkes_score > 0:
            math_basis_parts.append(
                f"Hawkes self-exciting point process (clustering={analysis.hawkes_score:.2f})"
            )

        mathematical_basis = "; ".join(math_basis_parts)

        # Build metadata
        metadata: dict = {
            "parkinson_vol": round(analysis.parkinson_vol, 6),
            "garman_klass_vol": round(analysis.garman_klass_vol, 6),
            "rogers_satchell_vol": round(analysis.rogers_satchell_vol, 6),
            "yang_zhang_vol": round(analysis.yang_zhang_vol, 6),
            "realized_vol_5d": round(analysis.realized_vol_5d, 6),
            "realized_vol_20d": round(analysis.realized_vol_20d, 6),
            "realized_vol_60d": round(analysis.realized_vol_60d, 6),
            "vol_percentile_20d": round(analysis.vol_percentile_20d, 2),
            "vol_z_score": round(analysis.vol_z_score, 4),
            "vol_term_structure": analysis.vol_term_structure,
            "is_compression": analysis.is_compression,
            "is_expansion": analysis.is_expansion,
            "regime_change_detected": analysis.regime_change_detected,
            "hawkes_clustering_score": round(analysis.hawkes_score, 4),
        }

        if analysis.garch_result is not None:
            metadata["garch"] = {
                "omega": analysis.garch_result.omega,
                "alpha": analysis.garch_result.alpha,
                "beta": analysis.garch_result.beta,
                "persistence": analysis.garch_result.persistence,
                "unconditional_vol": analysis.garch_result.unconditional_vol,
                "current_vol": analysis.garch_result.current_vol,
                "forecast_1d": analysis.garch_result.forecast_1d,
                "forecast_5d": analysis.garch_result.forecast_5d,
                "forecast_20d": analysis.garch_result.forecast_20d,
            }

        if analysis.regime_info is not None:
            metadata["markov_regime"] = {
                "current_regime": analysis.regime_info["regime"],
                "regime_probability": analysis.regime_info["regime_probability"],
                "transition_matrix": analysis.regime_info["transition_matrix"],
                "means": analysis.regime_info["means"],
                "volatilities": analysis.regime_info["volatilities"],
            }

        if analysis.vol_cone:
            metadata["vol_cone"] = {
                str(k): {sk: round(sv, 6) for sk, sv in v.items()}
                for k, v in analysis.vol_cone.items()
            }

        return AdvancedScanResult(
            scan_id=str(uuid.uuid4()),
            scan_name="Volatility Regime Scanner",
            category=ScanCategory.PRICE_ACTION,
            symbol=analysis.symbol,
            signal_direction=signal_direction,
            signal_strength=signal_strength,
            confidence=confidence,
            expected_move_pct=round(expected_move_pct, 2),
            expected_timeframe=ExpectedTimeframe.SWING,
            risk_reward_ratio=round(rr_ratio, 2),
            entry_price=round(entry_price, 2),
            stop_loss_level=round(stop_loss, 2),
            target_level=round(target, 2),
            supporting_evidence=analysis.supporting_evidence,
            contradicting_evidence=analysis.contradicting_evidence,
            regime_context=regime_context,
            mathematical_basis=mathematical_basis,
            volatility_regime=vol_regime,
            false_positive_rate=round(max(0.0, 0.30 - confidence * 0.15), 4),
            decay_halflife_days=5 if analysis.is_compression else 3,
            metadata=metadata,
        )

    def validate_signal(
        self, result: AdvancedScanResult, context: ScanContext
    ) -> bool:
        """
        Validate a volatility regime signal against current conditions.

        Checks:
            - Minimum confidence threshold
            - At least some supporting evidence
            - Signal is not contradicted by overwhelming counter-evidence
        """
        if result.confidence < self.config.min_confidence / 100.0:
            return False

        if len(result.supporting_evidence) < 2:
            return False

        if len(result.contradicting_evidence) >= len(result.supporting_evidence):
            return False

        return True
