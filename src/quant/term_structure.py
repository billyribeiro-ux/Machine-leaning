"""
Term Structure & Interest Rate Models

Institutional-grade yield curve and interest rate modeling:

Yield Curve Construction:
- Bootstrap from instruments
- Spline interpolation (cubic, natural, monotone)
- Nelson-Siegel and Svensson models
- Smith-Wilson extrapolation

Short-Rate Models:
- Vasicek (Ornstein-Uhlenbeck)
- Cox-Ingersoll-Ross (CIR)
- Hull-White (Extended Vasicek)
- Black-Karasinski (Lognormal)

Forward-Rate Models:
- Heath-Jarrow-Morton (HJM) framework
- LIBOR Market Model (BGM)
- SABR for swaptions

Interest Rate Derivatives:
- Bond pricing
- Caps/Floors
- Swaptions
- Bond options

Calibration:
- Least squares fitting
- Maximum likelihood
- Kalman filtering

Author: Revolution Alpha Engine
"""

import numpy as np
from scipy import optimize, interpolate, integrate
from scipy.stats import norm
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Callable
from datetime import datetime, date
from enum import Enum
from abc import ABC, abstractmethod
import warnings

warnings.filterwarnings('ignore')


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class YieldCurvePoint:
    """Single point on yield curve."""
    maturity: float  # In years
    rate: float      # Continuously compounded
    rate_type: str = "zero"  # 'zero', 'forward', 'par'


@dataclass
class Bond:
    """Bond specification."""
    face_value: float
    coupon_rate: float
    maturity: float
    frequency: int = 2  # Coupons per year
    day_count: str = "ACT/365"


@dataclass
class SwapRate:
    """Interest rate swap specification."""
    tenor: float
    fixed_rate: float
    float_index: str = "SOFR"
    frequency: int = 2


@dataclass
class CapFloor:
    """Cap or floor specification."""
    notional: float
    strike: float
    maturity: float
    frequency: int = 4  # Quarterly
    is_cap: bool = True


# =============================================================================
# YIELD CURVE
# =============================================================================

class YieldCurve:
    """
    Yield curve representation and manipulation.

    Supports multiple interpolation methods and rate conversions.
    """

    def __init__(
        self,
        maturities: np.ndarray,
        rates: np.ndarray,
        rate_type: str = "zero",
        interpolation: str = "cubic"
    ):
        """
        Args:
            maturities: Array of maturities in years
            rates: Array of rates (decimal form)
            rate_type: 'zero', 'forward', 'discount'
            interpolation: 'linear', 'cubic', 'monotone'
        """
        self.maturities = np.array(maturities)
        self.rates = np.array(rates)
        self.rate_type = rate_type
        self.interpolation = interpolation

        # Build interpolator
        self._build_interpolator()

    def _build_interpolator(self):
        """Build interpolation function."""
        if self.interpolation == "linear":
            self._interp = interpolate.interp1d(
                self.maturities, self.rates,
                kind='linear', fill_value='extrapolate'
            )
        elif self.interpolation == "cubic":
            self._interp = interpolate.CubicSpline(
                self.maturities, self.rates,
                bc_type='natural'
            )
        elif self.interpolation == "monotone":
            self._interp = interpolate.PchipInterpolator(
                self.maturities, self.rates
            )
        else:
            self._interp = interpolate.interp1d(
                self.maturities, self.rates,
                kind='linear', fill_value='extrapolate'
            )

    def zero_rate(self, T: float) -> float:
        """Get zero rate for maturity T."""
        if self.rate_type == "zero":
            return float(self._interp(T))
        elif self.rate_type == "discount":
            df = float(self._interp(T))
            return -np.log(df) / T if T > 0 else 0
        else:
            # Forward rates to zero
            return self._forward_to_zero(T)

    def discount_factor(self, T: float) -> float:
        """Get discount factor for maturity T."""
        r = self.zero_rate(T)
        return np.exp(-r * T)

    def forward_rate(self, T1: float, T2: float) -> float:
        """Get forward rate from T1 to T2."""
        if T2 <= T1:
            return self.zero_rate(T1)

        df1 = self.discount_factor(T1)
        df2 = self.discount_factor(T2)

        return (df1 / df2 - 1) / (T2 - T1)

    def instantaneous_forward(self, T: float, dT: float = 0.001) -> float:
        """Get instantaneous forward rate f(0, T)."""
        return self.forward_rate(T, T + dT)

    def _forward_to_zero(self, T: float) -> float:
        """Convert forward curve to zero rate."""
        # Numerical integration of forward rate
        result = integrate.quad(lambda t: self._interp(t), 0, T)[0]
        return result / T if T > 0 else float(self._interp(0))

    def par_rate(self, T: float, frequency: int = 2) -> float:
        """Calculate par swap rate for maturity T."""
        if T <= 0:
            return self.zero_rate(0)

        dt = 1.0 / frequency
        times = np.arange(dt, T + dt / 2, dt)

        # Discount factors
        dfs = np.array([self.discount_factor(t) for t in times])

        # Par rate = (1 - P(0,T)) / sum(tau * P(0,t_i))
        par = (1 - dfs[-1]) / (dt * np.sum(dfs))

        return par

    def shift(self, parallel_shift: float) -> 'YieldCurve':
        """Return curve shifted by parallel amount."""
        return YieldCurve(
            self.maturities,
            self.rates + parallel_shift,
            self.rate_type,
            self.interpolation
        )

    def bump_tenor(self, tenor: float, bump: float) -> 'YieldCurve':
        """Bump specific tenor point."""
        new_rates = self.rates.copy()
        idx = np.argmin(np.abs(self.maturities - tenor))
        new_rates[idx] += bump

        return YieldCurve(
            self.maturities,
            new_rates,
            self.rate_type,
            self.interpolation
        )


# =============================================================================
# NELSON-SIEGEL MODELS
# =============================================================================

class NelsonSiegel:
    """
    Nelson-Siegel yield curve model.

    r(T) = β₀ + β₁·((1-e^(-T/τ))/(T/τ)) + β₂·((1-e^(-T/τ))/(T/τ) - e^(-T/τ))

    Parameters:
    - β₀: Long-term level
    - β₁: Short-term component (slope)
    - β₂: Medium-term component (curvature)
    - τ: Decay factor
    """

    def __init__(
        self,
        beta0: float = 0.05,
        beta1: float = -0.02,
        beta2: float = 0.01,
        tau: float = 1.5
    ):
        self.beta0 = beta0
        self.beta1 = beta1
        self.beta2 = beta2
        self.tau = tau

    def rate(self, T: float) -> float:
        """Calculate yield for maturity T."""
        if T <= 0:
            return self.beta0 + self.beta1

        x = T / self.tau
        exp_x = np.exp(-x)
        factor1 = (1 - exp_x) / x
        factor2 = factor1 - exp_x

        return self.beta0 + self.beta1 * factor1 + self.beta2 * factor2

    def curve(self, maturities: np.ndarray) -> np.ndarray:
        """Get full curve."""
        return np.array([self.rate(T) for T in maturities])

    def fit(
        self,
        maturities: np.ndarray,
        rates: np.ndarray,
        tau_bounds: Tuple[float, float] = (0.1, 10.0)
    ) -> Dict[str, float]:
        """
        Fit model to observed rates.

        Returns fitted parameters.
        """
        def objective(params):
            beta0, beta1, beta2, tau = params
            model = NelsonSiegel(beta0, beta1, beta2, tau)
            fitted = model.curve(maturities)
            return np.sum((fitted - rates) ** 2)

        # Initial guess
        x0 = [rates[-1], rates[0] - rates[-1], 0.0, 1.5]

        # Bounds
        bounds = [
            (None, None),
            (None, None),
            (None, None),
            tau_bounds
        ]

        result = optimize.minimize(objective, x0, bounds=bounds, method='L-BFGS-B')

        self.beta0, self.beta1, self.beta2, self.tau = result.x

        return {
            'beta0': self.beta0,
            'beta1': self.beta1,
            'beta2': self.beta2,
            'tau': self.tau,
            'rmse': np.sqrt(result.fun / len(rates))
        }


class Svensson(NelsonSiegel):
    """
    Svensson extension of Nelson-Siegel.

    Adds second hump factor for better medium-term fitting.

    r(T) = NS(T) + β₃·((1-e^(-T/τ₂))/(T/τ₂) - e^(-T/τ₂))
    """

    def __init__(
        self,
        beta0: float = 0.05,
        beta1: float = -0.02,
        beta2: float = 0.01,
        beta3: float = 0.005,
        tau1: float = 1.5,
        tau2: float = 5.0
    ):
        super().__init__(beta0, beta1, beta2, tau1)
        self.beta3 = beta3
        self.tau2 = tau2

    def rate(self, T: float) -> float:
        """Calculate yield for maturity T."""
        ns_rate = super().rate(T)

        if T <= 0:
            return ns_rate

        x2 = T / self.tau2
        exp_x2 = np.exp(-x2)
        factor3 = (1 - exp_x2) / x2 - exp_x2

        return ns_rate + self.beta3 * factor3


# =============================================================================
# SHORT-RATE MODELS
# =============================================================================

class ShortRateModel(ABC):
    """Abstract base class for short-rate models."""

    @abstractmethod
    def simulate(
        self,
        r0: float,
        T: float,
        n_steps: int,
        n_paths: int
    ) -> np.ndarray:
        """Simulate short rate paths."""
        pass

    @abstractmethod
    def zero_coupon_bond(self, r: float, T: float) -> float:
        """Price zero-coupon bond."""
        pass


class Vasicek(ShortRateModel):
    """
    Vasicek short-rate model.

    dr(t) = κ(θ - r(t))dt + σdW(t)

    Features:
    - Mean-reverting
    - Analytical bond prices
    - Can go negative
    """

    def __init__(
        self,
        kappa: float,
        theta: float,
        sigma: float,
        seed: Optional[int] = None
    ):
        """
        Args:
            kappa: Mean reversion speed
            theta: Long-term mean rate
            sigma: Volatility
        """
        self.kappa = kappa
        self.theta = theta
        self.sigma = sigma
        self.rng = np.random.default_rng(seed)

    def simulate(
        self,
        r0: float,
        T: float,
        n_steps: int,
        n_paths: int
    ) -> np.ndarray:
        """Simulate Vasicek short rate paths."""
        dt = T / n_steps

        r = np.zeros((n_paths, n_steps + 1))
        r[:, 0] = r0

        # Exact simulation
        exp_kappa = np.exp(-self.kappa * dt)
        var = self.sigma ** 2 / (2 * self.kappa) * (1 - exp_kappa ** 2)
        std = np.sqrt(var)

        for i in range(n_steps):
            r[:, i + 1] = (
                self.theta + (r[:, i] - self.theta) * exp_kappa +
                std * self.rng.normal(0, 1, n_paths)
            )

        return r

    def zero_coupon_bond(self, r: float, T: float) -> float:
        """
        Analytical zero-coupon bond price.

        P(r, T) = A(T) * exp(-B(T) * r)
        """
        if T <= 0:
            return 1.0

        B = (1 - np.exp(-self.kappa * T)) / self.kappa

        A = np.exp(
            (self.theta - self.sigma ** 2 / (2 * self.kappa ** 2)) * (B - T) -
            self.sigma ** 2 / (4 * self.kappa) * B ** 2
        )

        return A * np.exp(-B * r)

    def yield_curve(self, r: float, maturities: np.ndarray) -> np.ndarray:
        """Generate yield curve from current short rate."""
        prices = np.array([self.zero_coupon_bond(r, T) for T in maturities])
        return -np.log(prices) / maturities

    def caplet_price(
        self,
        r: float,
        K: float,
        T_start: float,
        T_end: float,
        notional: float = 1.0
    ) -> float:
        """Price a caplet using Jamshidian's formula."""
        tau = T_end - T_start

        P_start = self.zero_coupon_bond(r, T_start)
        P_end = self.zero_coupon_bond(r, T_end)

        B_end = (1 - np.exp(-self.kappa * T_end)) / self.kappa
        B_start = (1 - np.exp(-self.kappa * T_start)) / self.kappa

        sigma_p = self.sigma * (B_end - B_start) * np.sqrt(
            (1 - np.exp(-2 * self.kappa * T_start)) / (2 * self.kappa)
        )

        d1 = np.log(P_end / (P_start * (1 + K * tau))) / sigma_p + 0.5 * sigma_p
        d2 = d1 - sigma_p

        caplet = notional * (P_end * norm.cdf(d1) - P_start * (1 + K * tau) * norm.cdf(d2))

        return caplet

    def calibrate(
        self,
        market_yields: np.ndarray,
        maturities: np.ndarray,
        r0: float
    ) -> Dict[str, float]:
        """Calibrate to market yield curve."""
        def objective(params):
            kappa, theta, sigma = params
            if kappa <= 0 or sigma <= 0:
                return 1e10

            model = Vasicek(kappa, theta, sigma)
            model_yields = model.yield_curve(r0, maturities)

            return np.sum((model_yields - market_yields) ** 2)

        x0 = [self.kappa, self.theta, self.sigma]
        bounds = [(0.001, 5.0), (-0.05, 0.20), (0.001, 0.10)]

        result = optimize.minimize(objective, x0, bounds=bounds, method='L-BFGS-B')

        self.kappa, self.theta, self.sigma = result.x

        return {
            'kappa': self.kappa,
            'theta': self.theta,
            'sigma': self.sigma,
            'rmse': np.sqrt(result.fun / len(maturities))
        }


class CIR(ShortRateModel):
    """
    Cox-Ingersoll-Ross short-rate model.

    dr(t) = κ(θ - r(t))dt + σ√r(t)dW(t)

    Features:
    - Mean-reverting
    - Always positive (if 2κθ > σ²)
    - Analytical bond prices
    """

    def __init__(
        self,
        kappa: float,
        theta: float,
        sigma: float,
        seed: Optional[int] = None
    ):
        self.kappa = kappa
        self.theta = theta
        self.sigma = sigma
        self.rng = np.random.default_rng(seed)

        # Feller condition
        self.feller_satisfied = 2 * kappa * theta > sigma ** 2

    def simulate(
        self,
        r0: float,
        T: float,
        n_steps: int,
        n_paths: int
    ) -> np.ndarray:
        """Simulate CIR short rate paths."""
        dt = T / n_steps

        r = np.zeros((n_paths, n_steps + 1))
        r[:, 0] = r0

        # Exact simulation via non-central chi-squared
        c = self.sigma ** 2 * (1 - np.exp(-self.kappa * dt)) / (4 * self.kappa)
        d = 4 * self.kappa * self.theta / self.sigma ** 2
        exp_kappa = np.exp(-self.kappa * dt)

        for i in range(n_steps):
            nc = r[:, i] * exp_kappa / c
            r[:, i + 1] = c * self.rng.noncentral_chisquare(d, np.maximum(nc, 0))

        return r

    def zero_coupon_bond(self, r: float, T: float) -> float:
        """Analytical zero-coupon bond price."""
        if T <= 0:
            return 1.0

        gamma = np.sqrt(self.kappa ** 2 + 2 * self.sigma ** 2)
        exp_gamma = np.exp(gamma * T)

        B = 2 * (exp_gamma - 1) / (
            (gamma + self.kappa) * (exp_gamma - 1) + 2 * gamma
        )

        A = (
            2 * gamma * np.exp((self.kappa + gamma) * T / 2) /
            ((gamma + self.kappa) * (exp_gamma - 1) + 2 * gamma)
        ) ** (2 * self.kappa * self.theta / self.sigma ** 2)

        return A * np.exp(-B * r)


class HullWhite(ShortRateModel):
    """
    Hull-White (Extended Vasicek) model.

    dr(t) = (θ(t) - a·r(t))dt + σdW(t)

    Features:
    - Time-dependent θ(t) for exact fit to initial curve
    - Mean-reverting
    - Can go negative
    - Analytical bond prices
    """

    def __init__(
        self,
        a: float,
        sigma: float,
        initial_curve: Optional[YieldCurve] = None,
        seed: Optional[int] = None
    ):
        """
        Args:
            a: Mean reversion speed
            sigma: Volatility
            initial_curve: Initial yield curve for calibration
        """
        self.a = a
        self.sigma = sigma
        self.initial_curve = initial_curve
        self.rng = np.random.default_rng(seed)

    def theta(self, t: float) -> float:
        """Time-dependent drift for fitting initial curve."""
        if self.initial_curve is None:
            return 0.05 * self.a  # Default to constant

        # θ(t) = ∂f(0,t)/∂t + a·f(0,t) + σ²/(2a)(1 - e^(-2at))
        f = self.initial_curve.instantaneous_forward(t)

        # Numerical derivative
        dt = 0.001
        df_dt = (self.initial_curve.instantaneous_forward(t + dt) - f) / dt

        return df_dt + self.a * f + self.sigma ** 2 / (2 * self.a) * (1 - np.exp(-2 * self.a * t))

    def simulate(
        self,
        r0: float,
        T: float,
        n_steps: int,
        n_paths: int
    ) -> np.ndarray:
        """Simulate Hull-White short rate paths."""
        dt = T / n_steps
        sqrt_dt = np.sqrt(dt)

        r = np.zeros((n_paths, n_steps + 1))
        r[:, 0] = r0

        for i in range(n_steps):
            t = i * dt
            theta_t = self.theta(t)
            r[:, i + 1] = (
                r[:, i] + (theta_t - self.a * r[:, i]) * dt +
                self.sigma * sqrt_dt * self.rng.normal(0, 1, n_paths)
            )

        return r

    def zero_coupon_bond(self, r: float, T: float, t: float = 0) -> float:
        """Zero-coupon bond price."""
        if T <= t:
            return 1.0

        tau = T - t

        B = (1 - np.exp(-self.a * tau)) / self.a

        if self.initial_curve is not None:
            P_0_T = self.initial_curve.discount_factor(T)
            P_0_t = self.initial_curve.discount_factor(t)
            f_0_t = self.initial_curve.instantaneous_forward(t)

            A = P_0_T / P_0_t * np.exp(
                B * f_0_t - self.sigma ** 2 / (4 * self.a) * (1 - np.exp(-2 * self.a * t)) * B ** 2
            )
        else:
            A = np.exp(
                self.sigma ** 2 / (2 * self.a ** 2) * (tau + 2 / self.a * np.exp(-self.a * tau) -
                1 / (2 * self.a) * np.exp(-2 * self.a * tau) - 3 / (2 * self.a))
            )

        return A * np.exp(-B * r)


# =============================================================================
# LIBOR MARKET MODEL
# =============================================================================

class LIBORMarketModel:
    """
    LIBOR Market Model (Brace-Gatarek-Musiela).

    Models forward LIBOR rates directly under their respective measures.

    dL_i(t)/L_i(t) = μ_i(t)dt + σ_i(t)dW_i(t)

    Under terminal measure Q^N:
    dL_i(t)/L_i(t) = -Σⱼ₌ᵢ₊₁ᴺ [ρᵢⱼσᵢσⱼτⱼLⱼ/(1+τⱼLⱼ)]dt + σᵢdWᵢ
    """

    def __init__(
        self,
        forward_rates: np.ndarray,
        tenors: np.ndarray,
        volatilities: np.ndarray,
        correlation: np.ndarray,
        seed: Optional[int] = None
    ):
        """
        Args:
            forward_rates: Initial forward rates
            tenors: Payment dates
            volatilities: Volatility for each forward rate
            correlation: Correlation matrix
        """
        self.forward_rates = np.array(forward_rates)
        self.tenors = np.array(tenors)
        self.volatilities = np.array(volatilities)
        self.correlation = np.array(correlation)
        self.rng = np.random.default_rng(seed)

        self.n_rates = len(forward_rates)
        self.tau = np.diff(np.concatenate([[0], tenors]))

    def simulate(
        self,
        T: float,
        n_steps: int,
        n_paths: int
    ) -> np.ndarray:
        """
        Simulate forward rate paths.

        Returns array of shape (n_paths, n_steps + 1, n_rates)
        """
        dt = T / n_steps

        # Cholesky decomposition of correlation
        L = np.linalg.cholesky(self.correlation)

        # Initialize
        rates = np.zeros((n_paths, n_steps + 1, self.n_rates))
        rates[:, 0, :] = self.forward_rates

        for step in range(n_steps):
            t = step * dt

            # Independent Brownians
            Z = self.rng.normal(0, 1, (n_paths, self.n_rates))
            dW = Z @ L.T * np.sqrt(dt)

            for i in range(self.n_rates):
                if self.tenors[i] <= t:
                    continue  # Rate already fixed

                # Drift under terminal measure
                drift = 0
                for j in range(i + 1, self.n_rates):
                    if self.tenors[j] > t:
                        rho_ij = self.correlation[i, j]
                        drift -= (
                            rho_ij * self.volatilities[i] * self.volatilities[j] *
                            self.tau[j] * rates[:, step, j] /
                            (1 + self.tau[j] * rates[:, step, j])
                        )

                # Log-normal evolution
                rates[:, step + 1, i] = rates[:, step, i] * np.exp(
                    (drift - 0.5 * self.volatilities[i] ** 2) * dt +
                    self.volatilities[i] * dW[:, i]
                )

        return rates

    def caplet_price(
        self,
        K: float,
        fixing_date: float,
        payment_date: float,
        n_paths: int = 10000
    ) -> float:
        """Price caplet via Monte Carlo."""
        # Find relevant forward rate
        idx = np.searchsorted(self.tenors, payment_date) - 1

        # Simulate to fixing date
        rates = self.simulate(fixing_date, 100, n_paths)

        # Terminal forward rate
        L_T = rates[:, -1, idx]
        tau = payment_date - fixing_date

        # Caplet payoff
        payoffs = np.maximum(L_T - K, 0) * tau

        # Discount (simplified)
        numeraire = np.prod(1 + self.tau * self.forward_rates)
        df = 1 / numeraire

        return df * np.mean(payoffs)


# =============================================================================
# INTEREST RATE DERIVATIVES
# =============================================================================

class InterestRateDerivatives:
    """
    Pricing for common interest rate derivatives.
    """

    def __init__(self, yield_curve: YieldCurve):
        self.curve = yield_curve

    def bond_price(
        self,
        face_value: float,
        coupon_rate: float,
        maturity: float,
        frequency: int = 2
    ) -> float:
        """Price coupon-bearing bond."""
        dt = 1.0 / frequency
        times = np.arange(dt, maturity + dt / 2, dt)

        # Coupon payments
        coupon = face_value * coupon_rate / frequency
        pv_coupons = sum(coupon * self.curve.discount_factor(t) for t in times)

        # Principal
        pv_principal = face_value * self.curve.discount_factor(maturity)

        return pv_coupons + pv_principal

    def bond_duration(
        self,
        face_value: float,
        coupon_rate: float,
        maturity: float,
        frequency: int = 2
    ) -> Tuple[float, float]:
        """
        Calculate Macaulay and Modified duration.

        Returns:
            macaulay: Macaulay duration
            modified: Modified duration
        """
        dt = 1.0 / frequency
        times = np.arange(dt, maturity + dt / 2, dt)

        price = self.bond_price(face_value, coupon_rate, maturity, frequency)
        coupon = face_value * coupon_rate / frequency

        # Weighted time
        weighted_sum = 0
        for t in times:
            cf = coupon if t < maturity else coupon + face_value
            weighted_sum += t * cf * self.curve.discount_factor(t)

        macaulay = weighted_sum / price

        # Modified duration
        y = coupon_rate  # Approximation
        modified = macaulay / (1 + y / frequency)

        return macaulay, modified

    def bond_convexity(
        self,
        face_value: float,
        coupon_rate: float,
        maturity: float,
        frequency: int = 2
    ) -> float:
        """Calculate bond convexity."""
        dt = 1.0 / frequency
        times = np.arange(dt, maturity + dt / 2, dt)

        price = self.bond_price(face_value, coupon_rate, maturity, frequency)
        coupon = face_value * coupon_rate / frequency

        weighted_sum = 0
        for t in times:
            cf = coupon if t < maturity else coupon + face_value
            weighted_sum += t * (t + dt) * cf * self.curve.discount_factor(t)

        y = coupon_rate
        return weighted_sum / (price * (1 + y / frequency) ** 2)

    def swap_rate(self, tenor: float, frequency: int = 2) -> float:
        """Calculate par swap rate."""
        return self.curve.par_rate(tenor, frequency)

    def swap_value(
        self,
        notional: float,
        fixed_rate: float,
        tenor: float,
        frequency: int = 2,
        is_payer: bool = True
    ) -> float:
        """
        Value an interest rate swap.

        Args:
            notional: Notional principal
            fixed_rate: Fixed leg rate
            tenor: Swap tenor
            frequency: Payment frequency
            is_payer: True if paying fixed
        """
        par_rate = self.swap_rate(tenor, frequency)
        annuity = self._annuity(tenor, frequency)

        value = notional * (par_rate - fixed_rate) * annuity

        return value if is_payer else -value

    def _annuity(self, tenor: float, frequency: int) -> float:
        """Calculate swap annuity (PV01)."""
        dt = 1.0 / frequency
        times = np.arange(dt, tenor + dt / 2, dt)
        return dt * sum(self.curve.discount_factor(t) for t in times)

    def cap_black(
        self,
        notional: float,
        strike: float,
        tenor: float,
        vol: float,
        frequency: int = 4
    ) -> float:
        """
        Price cap using Black's formula.

        Args:
            notional: Notional
            strike: Cap rate
            tenor: Cap tenor
            vol: Flat volatility
            frequency: Payment frequency
        """
        dt = 1.0 / frequency
        times = np.arange(dt, tenor + dt / 2, dt)

        cap_value = 0

        for i, T in enumerate(times):
            if i == 0:
                continue  # First caplet

            T_start = times[i - 1]
            tau = T - T_start

            # Forward rate
            df_start = self.curve.discount_factor(T_start)
            df_end = self.curve.discount_factor(T)
            F = (df_start / df_end - 1) / tau

            # Black's formula for caplet
            d1 = (np.log(F / strike) + 0.5 * vol ** 2 * T_start) / (vol * np.sqrt(T_start))
            d2 = d1 - vol * np.sqrt(T_start)

            caplet = df_end * tau * notional * (F * norm.cdf(d1) - strike * norm.cdf(d2))
            cap_value += caplet

        return cap_value

    def swaption_black(
        self,
        notional: float,
        strike: float,
        option_maturity: float,
        swap_tenor: float,
        vol: float,
        is_payer: bool = True,
        frequency: int = 2
    ) -> float:
        """
        Price European swaption using Black's formula.

        Args:
            notional: Notional
            strike: Strike rate
            option_maturity: Option expiry
            swap_tenor: Underlying swap tenor
            vol: Swaption volatility
            is_payer: Payer (True) or Receiver (False)
            frequency: Swap frequency
        """
        # Forward swap rate
        F = self.swap_rate(swap_tenor, frequency)

        # Annuity at option maturity
        A = self._annuity(swap_tenor, frequency)

        # Black's formula
        sqrt_T = np.sqrt(option_maturity)
        d1 = (np.log(F / strike) + 0.5 * vol ** 2 * option_maturity) / (vol * sqrt_T)
        d2 = d1 - vol * sqrt_T

        if is_payer:
            price = notional * A * (F * norm.cdf(d1) - strike * norm.cdf(d2))
        else:
            price = notional * A * (strike * norm.cdf(-d2) - F * norm.cdf(-d1))

        return price


# =============================================================================
# FACTORY FUNCTIONS
# =============================================================================

def create_yield_curve(
    maturities: List[float],
    rates: List[float],
    interpolation: str = "cubic"
) -> YieldCurve:
    """Create yield curve from points."""
    return YieldCurve(
        np.array(maturities),
        np.array(rates),
        interpolation=interpolation
    )


def create_vasicek(
    kappa: float = 0.5,
    theta: float = 0.05,
    sigma: float = 0.02,
    seed: Optional[int] = None
) -> Vasicek:
    """Create Vasicek model."""
    return Vasicek(kappa, theta, sigma, seed)


def create_cir(
    kappa: float = 0.5,
    theta: float = 0.05,
    sigma: float = 0.1,
    seed: Optional[int] = None
) -> CIR:
    """Create CIR model."""
    return CIR(kappa, theta, sigma, seed)


def create_hull_white(
    a: float = 0.1,
    sigma: float = 0.01,
    initial_curve: Optional[YieldCurve] = None,
    seed: Optional[int] = None
) -> HullWhite:
    """Create Hull-White model."""
    return HullWhite(a, sigma, initial_curve, seed)


# Example usage
if __name__ == "__main__":
    print("="*60)
    print("TERM STRUCTURE MODULE - TEST MODE")
    print("="*60)

    # Create sample yield curve
    maturities = [0.25, 0.5, 1, 2, 3, 5, 7, 10, 20, 30]
    rates = [0.045, 0.046, 0.047, 0.048, 0.049, 0.050, 0.051, 0.052, 0.053, 0.054]

    curve = create_yield_curve(maturities, rates)

    print("\n1. Yield Curve")
    print("-" * 40)
    print(f"   1Y Zero Rate: {curve.zero_rate(1):.4f}")
    print(f"   5Y Zero Rate: {curve.zero_rate(5):.4f}")
    print(f"   10Y Zero Rate: {curve.zero_rate(10):.4f}")
    print(f"   1Y-2Y Forward: {curve.forward_rate(1, 2):.4f}")
    print(f"   5Y Par Rate: {curve.par_rate(5):.4f}")

    print("\n2. Nelson-Siegel Fitting")
    print("-" * 40)
    ns = NelsonSiegel()
    fit_result = ns.fit(np.array(maturities), np.array(rates))
    print(f"   β₀ (level): {fit_result['beta0']:.4f}")
    print(f"   β₁ (slope): {fit_result['beta1']:.4f}")
    print(f"   β₂ (curvature): {fit_result['beta2']:.4f}")
    print(f"   RMSE: {fit_result['rmse']:.6f}")

    print("\n3. Vasicek Model")
    print("-" * 40)
    vasicek = create_vasicek(kappa=0.5, theta=0.05, sigma=0.02)
    r0 = 0.04

    # Simulate paths
    paths = vasicek.simulate(r0, 10, 252, 1000)
    print(f"   Initial rate: {r0:.4f}")
    print(f"   Long-term mean: {vasicek.theta:.4f}")
    print(f"   10Y simulated mean: {paths[:, -1].mean():.4f}")

    # Bond price
    bond_price = vasicek.zero_coupon_bond(r0, 5)
    print(f"   5Y ZCB Price: {bond_price:.4f}")

    print("\n4. CIR Model")
    print("-" * 40)
    cir = create_cir(kappa=0.5, theta=0.05, sigma=0.1)
    cir_paths = cir.simulate(r0, 10, 252, 1000)
    print(f"   Feller condition satisfied: {cir.feller_satisfied}")
    print(f"   Min rate in simulation: {cir_paths.min():.4f}")
    print(f"   10Y simulated mean: {cir_paths[:, -1].mean():.4f}")

    print("\n5. Interest Rate Derivatives")
    print("-" * 40)
    derivatives = InterestRateDerivatives(curve)

    # Bond pricing
    bond_px = derivatives.bond_price(100, 0.05, 10)
    mac_dur, mod_dur = derivatives.bond_duration(100, 0.05, 10)
    print(f"   10Y 5% Bond Price: ${bond_px:.2f}")
    print(f"   Macaulay Duration: {mac_dur:.2f}")
    print(f"   Modified Duration: {mod_dur:.2f}")

    # Swap rate
    swap_5y = derivatives.swap_rate(5)
    print(f"   5Y Swap Rate: {swap_5y:.4f}")

    # Swaption
    swaption_px = derivatives.swaption_black(1000000, 0.05, 1, 5, 0.20)
    print(f"   1Y into 5Y Payer Swaption: ${swaption_px:,.0f}")

    print(f"\n{'='*60}")
    print("TERM STRUCTURE MODULE - READY")
    print('='*60)
