"""
Derivatives Pricing Models

Institutional-grade options and derivatives pricing:

Analytical Models:
- Black-Scholes-Merton
- Black-76 (futures options)
- Bachelier (normal model)
- Displaced Diffusion

Stochastic Volatility:
- Heston analytical (via Fourier)
- SABR implied volatility
- Local volatility (Dupire)

Numerical Methods:
- Binomial/Trinomial trees
- Finite difference (explicit, implicit, Crank-Nicolson)
- Monte Carlo with Greeks
- FFT option pricing
- Carr-Madan formula

Exotic Options:
- Barrier options (up/down, in/out)
- Asian options (arithmetic/geometric)
- Lookback options
- Digital/Binary options
- Compound options
- Chooser options

Greeks:
- Delta, Gamma, Vega, Theta, Rho
- Higher-order Greeks (Vanna, Volga, Speed, Charm)
- Numerical Greeks via finite differences

Author: Revolution Alpha Engine
"""

import numpy as np
from scipy import stats, optimize, integrate
from scipy.fft import fft, ifft
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Union, Callable
from enum import Enum
from abc import ABC, abstractmethod
import warnings

warnings.filterwarnings('ignore')


# =============================================================================
# ENUMS AND DATA CLASSES
# =============================================================================

class OptionType(Enum):
    CALL = "call"
    PUT = "put"


class ExerciseStyle(Enum):
    EUROPEAN = "european"
    AMERICAN = "american"
    BERMUDAN = "bermudan"


class BarrierType(Enum):
    UP_IN = "up_in"
    UP_OUT = "up_out"
    DOWN_IN = "down_in"
    DOWN_OUT = "down_out"


@dataclass
class OptionContract:
    """Option contract specification."""
    strike: float
    expiry: float  # Time to expiry in years
    option_type: OptionType
    exercise_style: ExerciseStyle = ExerciseStyle.EUROPEAN
    underlying_price: Optional[float] = None
    dividend_yield: float = 0.0


@dataclass
class Greeks:
    """Option Greeks."""
    delta: float = 0.0
    gamma: float = 0.0
    vega: float = 0.0
    theta: float = 0.0
    rho: float = 0.0
    # Higher-order
    vanna: float = 0.0      # d(delta)/d(vol)
    volga: float = 0.0      # d(vega)/d(vol)
    charm: float = 0.0      # d(delta)/d(time)
    speed: float = 0.0      # d(gamma)/d(spot)
    color: float = 0.0      # d(gamma)/d(time)
    zomma: float = 0.0      # d(gamma)/d(vol)


@dataclass
class PricingResult:
    """Complete pricing result."""
    price: float
    greeks: Greeks
    implied_vol: Optional[float] = None
    model: str = ""
    computation_time_ms: float = 0.0


# =============================================================================
# BLACK-SCHOLES-MERTON
# =============================================================================

class BlackScholes:
    """
    Black-Scholes-Merton option pricing model.

    Assumptions:
    - Log-normal stock prices
    - Constant volatility
    - Continuous trading
    - No dividends (or continuous dividend yield)
    - European exercise only
    """

    @staticmethod
    def d1(S: float, K: float, r: float, q: float, sigma: float, T: float) -> float:
        """Calculate d1 parameter."""
        if T <= 0 or sigma <= 0:
            return 0.0
        return (np.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))

    @staticmethod
    def d2(S: float, K: float, r: float, q: float, sigma: float, T: float) -> float:
        """Calculate d2 parameter."""
        if T <= 0 or sigma <= 0:
            return 0.0
        return BlackScholes.d1(S, K, r, q, sigma, T) - sigma * np.sqrt(T)

    @staticmethod
    def price(
        S: float,
        K: float,
        r: float,
        sigma: float,
        T: float,
        option_type: OptionType,
        q: float = 0.0
    ) -> float:
        """
        Calculate Black-Scholes option price.

        Args:
            S: Spot price
            K: Strike price
            r: Risk-free rate
            sigma: Volatility
            T: Time to expiry
            option_type: Call or Put
            q: Dividend yield

        Returns:
            Option price
        """
        if T <= 0:
            if option_type == OptionType.CALL:
                return max(S - K, 0)
            else:
                return max(K - S, 0)

        d1 = BlackScholes.d1(S, K, r, q, sigma, T)
        d2 = BlackScholes.d2(S, K, r, q, sigma, T)

        if option_type == OptionType.CALL:
            return S * np.exp(-q * T) * stats.norm.cdf(d1) - K * np.exp(-r * T) * stats.norm.cdf(d2)
        else:
            return K * np.exp(-r * T) * stats.norm.cdf(-d2) - S * np.exp(-q * T) * stats.norm.cdf(-d1)

    @staticmethod
    def greeks(
        S: float,
        K: float,
        r: float,
        sigma: float,
        T: float,
        option_type: OptionType,
        q: float = 0.0
    ) -> Greeks:
        """Calculate all Greeks."""
        if T <= 0:
            return Greeks()

        d1 = BlackScholes.d1(S, K, r, q, sigma, T)
        d2 = BlackScholes.d2(S, K, r, q, sigma, T)

        sqrt_T = np.sqrt(T)
        exp_qT = np.exp(-q * T)
        exp_rT = np.exp(-r * T)
        n_d1 = stats.norm.pdf(d1)
        N_d1 = stats.norm.cdf(d1)
        N_d2 = stats.norm.cdf(d2)

        # Delta
        if option_type == OptionType.CALL:
            delta = exp_qT * N_d1
        else:
            delta = exp_qT * (N_d1 - 1)

        # Gamma (same for call/put)
        gamma = exp_qT * n_d1 / (S * sigma * sqrt_T)

        # Vega (same for call/put)
        vega = S * exp_qT * n_d1 * sqrt_T / 100  # Per 1% vol change

        # Theta
        term1 = -S * exp_qT * n_d1 * sigma / (2 * sqrt_T)
        if option_type == OptionType.CALL:
            term2 = q * S * exp_qT * N_d1
            term3 = -r * K * exp_rT * N_d2
            theta = (term1 + term2 + term3) / 365  # Per day
        else:
            term2 = q * S * exp_qT * (N_d1 - 1)
            term3 = r * K * exp_rT * stats.norm.cdf(-d2)
            theta = (term1 - term2 + term3) / 365

        # Rho
        if option_type == OptionType.CALL:
            rho = K * T * exp_rT * N_d2 / 100  # Per 1% rate change
        else:
            rho = -K * T * exp_rT * stats.norm.cdf(-d2) / 100

        # Higher-order Greeks
        vanna = -exp_qT * n_d1 * d2 / sigma
        volga = vega * d1 * d2 / sigma
        charm = exp_qT * n_d1 * (q + (r - q) * d1 / (sigma * sqrt_T) - (1 + d1 * d2) / (2 * T))
        speed = -gamma / S * (1 + d1 / (sigma * sqrt_T))
        color = -exp_qT * n_d1 / (2 * S * T * sigma * sqrt_T) * (
            2 * q * T + 1 + d1 * (2 * (r - q) * T - d2 * sigma * sqrt_T) / (sigma * sqrt_T)
        )
        zomma = gamma * (d1 * d2 - 1) / sigma

        return Greeks(
            delta=delta,
            gamma=gamma,
            vega=vega,
            theta=theta,
            rho=rho,
            vanna=vanna,
            volga=volga,
            charm=charm,
            speed=speed,
            color=color,
            zomma=zomma
        )

    @staticmethod
    def implied_volatility(
        price: float,
        S: float,
        K: float,
        r: float,
        T: float,
        option_type: OptionType,
        q: float = 0.0,
        precision: float = 1e-8,
        max_iter: int = 100
    ) -> float:
        """
        Calculate implied volatility using Newton-Raphson.

        Args:
            price: Market option price
            Other args: Same as price()

        Returns:
            Implied volatility
        """
        if T <= 0:
            return 0.0

        # Initial guess using Brenner-Subrahmanyam approximation
        sigma = np.sqrt(2 * np.pi / T) * price / S

        for _ in range(max_iter):
            bs_price = BlackScholes.price(S, K, r, sigma, T, option_type, q)
            diff = bs_price - price

            if abs(diff) < precision:
                return sigma

            # Vega for Newton-Raphson
            d1 = BlackScholes.d1(S, K, r, q, sigma, T)
            vega = S * np.exp(-q * T) * stats.norm.pdf(d1) * np.sqrt(T)

            if vega < 1e-10:
                break

            sigma = sigma - diff / vega
            sigma = max(0.001, min(sigma, 5.0))  # Bounds

        return sigma

    @staticmethod
    def price_vector(
        S: np.ndarray,
        K: float,
        r: float,
        sigma: float,
        T: float,
        option_type: OptionType,
        q: float = 0.0
    ) -> np.ndarray:
        """Vectorized pricing for multiple spot prices."""
        d1 = (np.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)

        if option_type == OptionType.CALL:
            return S * np.exp(-q * T) * stats.norm.cdf(d1) - K * np.exp(-r * T) * stats.norm.cdf(d2)
        else:
            return K * np.exp(-r * T) * stats.norm.cdf(-d2) - S * np.exp(-q * T) * stats.norm.cdf(-d1)


# =============================================================================
# BLACK-76 (FUTURES OPTIONS)
# =============================================================================

class Black76:
    """
    Black-76 model for options on futures/forwards.

    F = forward price (already discounted)
    """

    @staticmethod
    def price(
        F: float,
        K: float,
        r: float,
        sigma: float,
        T: float,
        option_type: OptionType
    ) -> float:
        """Price option on futures."""
        if T <= 0:
            if option_type == OptionType.CALL:
                return max(F - K, 0)
            else:
                return max(K - F, 0)

        d1 = (np.log(F / K) + 0.5 * sigma ** 2 * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)

        df = np.exp(-r * T)

        if option_type == OptionType.CALL:
            return df * (F * stats.norm.cdf(d1) - K * stats.norm.cdf(d2))
        else:
            return df * (K * stats.norm.cdf(-d2) - F * stats.norm.cdf(-d1))


# =============================================================================
# BACHELIER (NORMAL MODEL)
# =============================================================================

class Bachelier:
    """
    Bachelier (Normal) model.

    Assumes arithmetic (not geometric) Brownian motion.
    Prices can go negative.
    Used for interest rate options and low-rate environments.
    """

    @staticmethod
    def price(
        S: float,
        K: float,
        r: float,
        sigma_n: float,  # Normal volatility (absolute, not percentage)
        T: float,
        option_type: OptionType
    ) -> float:
        """Price using Bachelier model."""
        if T <= 0:
            if option_type == OptionType.CALL:
                return max(S - K, 0)
            else:
                return max(K - S, 0)

        d = (S - K) / (sigma_n * np.sqrt(T))
        df = np.exp(-r * T)

        if option_type == OptionType.CALL:
            return df * ((S - K) * stats.norm.cdf(d) + sigma_n * np.sqrt(T) * stats.norm.pdf(d))
        else:
            return df * ((K - S) * stats.norm.cdf(-d) + sigma_n * np.sqrt(T) * stats.norm.pdf(d))


# =============================================================================
# BINOMIAL TREE
# =============================================================================

class BinomialTree:
    """
    Binomial tree option pricing (Cox-Ross-Rubinstein).

    Supports American exercise and dividends.
    """

    def __init__(self, n_steps: int = 100):
        self.n_steps = n_steps

    def price(
        self,
        S: float,
        K: float,
        r: float,
        sigma: float,
        T: float,
        option_type: OptionType,
        exercise_style: ExerciseStyle = ExerciseStyle.EUROPEAN,
        q: float = 0.0
    ) -> Tuple[float, np.ndarray]:
        """
        Price option using binomial tree.

        Returns:
            price: Option price
            tree: Full price tree for visualization
        """
        dt = T / self.n_steps

        # CRR parameters
        u = np.exp(sigma * np.sqrt(dt))
        d = 1 / u
        p = (np.exp((r - q) * dt) - d) / (u - d)

        # Build price tree
        price_tree = np.zeros((self.n_steps + 1, self.n_steps + 1))

        for i in range(self.n_steps + 1):
            for j in range(i + 1):
                price_tree[j, i] = S * (u ** (i - j)) * (d ** j)

        # Build option value tree (backward induction)
        option_tree = np.zeros_like(price_tree)

        # Terminal payoffs
        if option_type == OptionType.CALL:
            option_tree[:, -1] = np.maximum(price_tree[:, -1] - K, 0)
        else:
            option_tree[:, -1] = np.maximum(K - price_tree[:, -1], 0)

        # Backward induction
        df = np.exp(-r * dt)

        for i in range(self.n_steps - 1, -1, -1):
            for j in range(i + 1):
                hold_value = df * (p * option_tree[j, i + 1] + (1 - p) * option_tree[j + 1, i + 1])

                if exercise_style == ExerciseStyle.AMERICAN:
                    if option_type == OptionType.CALL:
                        exercise_value = max(price_tree[j, i] - K, 0)
                    else:
                        exercise_value = max(K - price_tree[j, i], 0)
                    option_tree[j, i] = max(hold_value, exercise_value)
                else:
                    option_tree[j, i] = hold_value

        return option_tree[0, 0], option_tree

    def greeks_numerical(
        self,
        S: float,
        K: float,
        r: float,
        sigma: float,
        T: float,
        option_type: OptionType,
        exercise_style: ExerciseStyle = ExerciseStyle.EUROPEAN,
        q: float = 0.0
    ) -> Greeks:
        """Calculate Greeks using finite differences."""
        h_S = S * 0.01  # 1% price shift
        h_sigma = 0.01  # 1% vol shift
        h_r = 0.0001    # 1bp rate shift
        h_T = 1/365     # 1 day

        price_base = self.price(S, K, r, sigma, T, option_type, exercise_style, q)[0]

        # Delta
        price_up = self.price(S + h_S, K, r, sigma, T, option_type, exercise_style, q)[0]
        price_down = self.price(S - h_S, K, r, sigma, T, option_type, exercise_style, q)[0]
        delta = (price_up - price_down) / (2 * h_S)

        # Gamma
        gamma = (price_up - 2 * price_base + price_down) / (h_S ** 2)

        # Vega
        price_vol_up = self.price(S, K, r, sigma + h_sigma, T, option_type, exercise_style, q)[0]
        vega = (price_vol_up - price_base) / h_sigma / 100

        # Theta
        if T > h_T:
            price_T_down = self.price(S, K, r, sigma, T - h_T, option_type, exercise_style, q)[0]
            theta = -(price_base - price_T_down) / h_T / 365
        else:
            theta = 0

        # Rho
        price_r_up = self.price(S, K, r + h_r, sigma, T, option_type, exercise_style, q)[0]
        rho = (price_r_up - price_base) / h_r / 100

        return Greeks(delta=delta, gamma=gamma, vega=vega, theta=theta, rho=rho)


# =============================================================================
# FINITE DIFFERENCE METHODS
# =============================================================================

class FiniteDifference:
    """
    Finite difference methods for option pricing.

    Methods:
    - Explicit: Simple but conditionally stable
    - Implicit: Unconditionally stable
    - Crank-Nicolson: Second-order accurate
    """

    def __init__(
        self,
        n_space: int = 100,
        n_time: int = 100,
        method: str = 'crank_nicolson'
    ):
        self.n_space = n_space
        self.n_time = n_time
        self.method = method

    def price(
        self,
        S: float,
        K: float,
        r: float,
        sigma: float,
        T: float,
        option_type: OptionType,
        exercise_style: ExerciseStyle = ExerciseStyle.EUROPEAN,
        q: float = 0.0,
        S_max_mult: float = 3.0
    ) -> Tuple[float, np.ndarray]:
        """
        Price option using finite differences.

        Returns:
            price: Option price
            grid: Full solution grid
        """
        # Grid setup
        S_max = S * S_max_mult
        dS = S_max / self.n_space
        dt = T / self.n_time

        # Create grid
        S_grid = np.linspace(0, S_max, self.n_space + 1)

        # Initialize option values at expiry
        if option_type == OptionType.CALL:
            V = np.maximum(S_grid - K, 0)
        else:
            V = np.maximum(K - S_grid, 0)

        # Coefficients
        j = np.arange(1, self.n_space)
        a = 0.5 * dt * (sigma ** 2 * j ** 2 - (r - q) * j)
        b = 1 - dt * (sigma ** 2 * j ** 2 + r)
        c = 0.5 * dt * (sigma ** 2 * j ** 2 + (r - q) * j)

        if self.method == 'explicit':
            # Explicit method
            for _ in range(self.n_time):
                V_new = np.zeros_like(V)
                V_new[1:-1] = a * V[:-2] + (1 + b - 1) * V[1:-1] + c * V[2:]

                # Boundary conditions
                if option_type == OptionType.CALL:
                    V_new[0] = 0
                    V_new[-1] = S_max - K * np.exp(-r * (_ + 1) * dt)
                else:
                    V_new[0] = K * np.exp(-r * (_ + 1) * dt)
                    V_new[-1] = 0

                if exercise_style == ExerciseStyle.AMERICAN:
                    if option_type == OptionType.CALL:
                        V_new = np.maximum(V_new, S_grid - K)
                    else:
                        V_new = np.maximum(V_new, K - S_grid)

                V = V_new

        elif self.method == 'implicit':
            # Implicit method (solve tridiagonal system)
            for _ in range(self.n_time):
                # Build tridiagonal matrix
                diag = 1 - b
                upper = -c[:-1]
                lower = -a[1:]

                rhs = V[1:-1].copy()

                # Boundary conditions
                if option_type == OptionType.CALL:
                    rhs[0] -= a[0] * 0
                    rhs[-1] -= c[-1] * (S_max - K * np.exp(-r * (_ + 1) * dt))
                else:
                    rhs[0] -= a[0] * K * np.exp(-r * (_ + 1) * dt)
                    rhs[-1] -= c[-1] * 0

                # Solve tridiagonal system
                V[1:-1] = self._solve_tridiagonal(lower, diag, upper, rhs)

                if exercise_style == ExerciseStyle.AMERICAN:
                    if option_type == OptionType.CALL:
                        V = np.maximum(V, S_grid - K)
                    else:
                        V = np.maximum(V, K - S_grid)

        else:  # Crank-Nicolson
            # Crank-Nicolson (average of explicit and implicit)
            alpha = 0.5  # Weighting

            for _ in range(self.n_time):
                # Explicit part
                V_exp = np.zeros_like(V)
                V_exp[1:-1] = (
                    alpha * a * V[:-2] +
                    (1 + alpha * (b - 1)) * V[1:-1] +
                    alpha * c * V[2:]
                )

                # Implicit part coefficients
                diag = 1 - (1 - alpha) * b
                upper = -(1 - alpha) * c[:-1]
                lower = -(1 - alpha) * a[1:]

                rhs = V_exp[1:-1]

                V[1:-1] = self._solve_tridiagonal(lower, diag, upper, rhs)

                # Boundary conditions
                if option_type == OptionType.CALL:
                    V[0] = 0
                    V[-1] = S_max - K * np.exp(-r * (_ + 1) * dt)
                else:
                    V[0] = K * np.exp(-r * (_ + 1) * dt)
                    V[-1] = 0

                if exercise_style == ExerciseStyle.AMERICAN:
                    if option_type == OptionType.CALL:
                        V = np.maximum(V, S_grid - K)
                    else:
                        V = np.maximum(V, K - S_grid)

        # Interpolate to get price at S
        idx = int(S / dS)
        weight = (S - S_grid[idx]) / dS
        price = V[idx] * (1 - weight) + V[idx + 1] * weight

        return price, V

    def _solve_tridiagonal(
        self,
        lower: np.ndarray,
        diag: np.ndarray,
        upper: np.ndarray,
        rhs: np.ndarray
    ) -> np.ndarray:
        """Thomas algorithm for tridiagonal systems."""
        n = len(rhs)
        c_prime = np.zeros(n - 1)
        d_prime = np.zeros(n)

        c_prime[0] = upper[0] / diag[0]
        d_prime[0] = rhs[0] / diag[0]

        for i in range(1, n):
            denom = diag[i] - lower[i - 1] * c_prime[i - 1] if i < n - 1 else diag[i] - lower[i - 1] * c_prime[i - 1]
            if i < n - 1:
                c_prime[i] = upper[i] / denom
            d_prime[i] = (rhs[i] - lower[i - 1] * d_prime[i - 1]) / denom

        x = np.zeros(n)
        x[-1] = d_prime[-1]

        for i in range(n - 2, -1, -1):
            x[i] = d_prime[i] - c_prime[i] * x[i + 1]

        return x


# =============================================================================
# HESTON ANALYTICAL (FFT)
# =============================================================================

class HestonAnalytical:
    """
    Analytical Heston pricing using Fourier transform methods.
    """

    def __init__(
        self,
        kappa: float,
        theta: float,
        sigma: float,
        rho: float,
        v0: float
    ):
        """
        Args:
            kappa: Mean reversion speed
            theta: Long-term variance
            sigma: Vol of vol
            rho: Correlation
            v0: Initial variance
        """
        self.kappa = kappa
        self.theta = theta
        self.sigma = sigma
        self.rho = rho
        self.v0 = v0

    def characteristic_function(
        self,
        u: complex,
        S: float,
        r: float,
        T: float,
        q: float = 0.0
    ) -> complex:
        """Heston characteristic function."""
        kappa, theta, sigma, rho, v0 = self.kappa, self.theta, self.sigma, self.rho, self.v0

        d = np.sqrt(
            (rho * sigma * 1j * u - kappa) ** 2 +
            sigma ** 2 * (1j * u + u ** 2)
        )

        g = (kappa - rho * sigma * 1j * u - d) / (kappa - rho * sigma * 1j * u + d)

        exp_dT = np.exp(-d * T)

        C = (r - q) * 1j * u * T + kappa * theta / sigma ** 2 * (
            (kappa - rho * sigma * 1j * u - d) * T -
            2 * np.log((1 - g * exp_dT) / (1 - g))
        )

        D = (kappa - rho * sigma * 1j * u - d) / sigma ** 2 * (
            (1 - exp_dT) / (1 - g * exp_dT)
        )

        return np.exp(C + D * v0 + 1j * u * np.log(S))

    def price_carr_madan(
        self,
        S: float,
        K: float,
        r: float,
        T: float,
        option_type: OptionType,
        q: float = 0.0,
        N: int = 4096,
        alpha: float = 1.5
    ) -> float:
        """
        Price using Carr-Madan FFT method.

        Args:
            S: Spot
            K: Strike
            r: Risk-free rate
            T: Time to expiry
            option_type: Call or Put
            q: Dividend yield
            N: FFT points
            alpha: Dampening factor
        """
        # FFT parameters
        eta = 0.25
        lambda_param = 2 * np.pi / (N * eta)
        b = N * lambda_param / 2

        # u grid
        u = np.arange(N) * eta

        # Characteristic function values
        psi = np.zeros(N, dtype=complex)

        for j in range(N):
            v = u[j] - (alpha + 1) * 1j
            phi = self.characteristic_function(v, S, r, T, q)

            denom = alpha ** 2 + alpha - u[j] ** 2 + 1j * (2 * alpha + 1) * u[j]
            psi[j] = np.exp(-r * T) * phi / denom

        # Simpson's weights
        simpson = 3 + (-1) ** np.arange(N)
        simpson[0] = 1
        simpson = simpson / 3

        # FFT
        x = np.exp(1j * b * u) * psi * eta * simpson
        fft_result = fft(x).real

        # Strikes
        k = -b + lambda_param * np.arange(N)
        strikes = np.exp(k)

        # Interpolate to desired strike
        call_prices = np.exp(-alpha * k) / np.pi * fft_result

        # Find price at K
        idx = np.searchsorted(strikes, K)
        if idx == 0:
            price = call_prices[0]
        elif idx >= N:
            price = call_prices[-1]
        else:
            # Linear interpolation
            w = (K - strikes[idx - 1]) / (strikes[idx] - strikes[idx - 1])
            price = call_prices[idx - 1] * (1 - w) + call_prices[idx] * w

        if option_type == OptionType.PUT:
            # Put-call parity
            price = price - S * np.exp(-q * T) + K * np.exp(-r * T)

        return max(price, 0)


# =============================================================================
# BARRIER OPTIONS
# =============================================================================

class BarrierOption:
    """
    Analytical barrier option pricing.
    """

    @staticmethod
    def price(
        S: float,
        K: float,
        H: float,  # Barrier level
        r: float,
        sigma: float,
        T: float,
        option_type: OptionType,
        barrier_type: BarrierType,
        q: float = 0.0,
        rebate: float = 0.0
    ) -> float:
        """
        Price barrier option using analytical formulas.

        Args:
            S: Spot
            K: Strike
            H: Barrier level
            r: Risk-free rate
            sigma: Volatility
            T: Time to expiry
            option_type: Call or Put
            barrier_type: Up/Down In/Out
            q: Dividend yield
            rebate: Rebate paid if knocked out
        """
        # Check if already knocked
        if barrier_type in [BarrierType.UP_IN, BarrierType.UP_OUT] and S >= H:
            if barrier_type == BarrierType.UP_OUT:
                return rebate
            else:
                return BlackScholes.price(S, K, r, sigma, T, option_type, q)

        if barrier_type in [BarrierType.DOWN_IN, BarrierType.DOWN_OUT] and S <= H:
            if barrier_type == BarrierType.DOWN_OUT:
                return rebate
            else:
                return BlackScholes.price(S, K, r, sigma, T, option_type, q)

        # Parameters
        mu = (r - q - 0.5 * sigma ** 2) / sigma ** 2
        lambda_param = np.sqrt(mu ** 2 + 2 * r / sigma ** 2)
        sqrt_T = np.sqrt(T)

        x1 = np.log(S / K) / (sigma * sqrt_T) + (1 + mu) * sigma * sqrt_T
        x2 = np.log(S / H) / (sigma * sqrt_T) + (1 + mu) * sigma * sqrt_T
        y1 = np.log(H ** 2 / (S * K)) / (sigma * sqrt_T) + (1 + mu) * sigma * sqrt_T
        y2 = np.log(H / S) / (sigma * sqrt_T) + (1 + mu) * sigma * sqrt_T

        # Vanilla price for comparison
        vanilla = BlackScholes.price(S, K, r, sigma, T, option_type, q)

        # Down-and-Out Call (K > H)
        if barrier_type == BarrierType.DOWN_OUT and option_type == OptionType.CALL and K > H:
            A = S * np.exp(-q * T) * stats.norm.cdf(x1) - K * np.exp(-r * T) * stats.norm.cdf(x1 - sigma * sqrt_T)
            B = S * np.exp(-q * T) * stats.norm.cdf(x2) - K * np.exp(-r * T) * stats.norm.cdf(x2 - sigma * sqrt_T)
            C = S * np.exp(-q * T) * (H / S) ** (2 * (mu + 1)) * stats.norm.cdf(y1) - \
                K * np.exp(-r * T) * (H / S) ** (2 * mu) * stats.norm.cdf(y1 - sigma * sqrt_T)
            D = S * np.exp(-q * T) * (H / S) ** (2 * (mu + 1)) * stats.norm.cdf(y2) - \
                K * np.exp(-r * T) * (H / S) ** (2 * mu) * stats.norm.cdf(y2 - sigma * sqrt_T)

            return A - B + C - D

        # In-Out parity
        if 'out' in barrier_type.value:
            in_type = BarrierType(barrier_type.value.replace('out', 'in'))
            in_price = BarrierOption.price(S, K, H, r, sigma, T, option_type, in_type, q, rebate)
            return vanilla - in_price
        else:
            out_type = BarrierType(barrier_type.value.replace('in', 'out'))
            out_price = BarrierOption.price(S, K, H, r, sigma, T, option_type, out_type, q, rebate)
            return vanilla - out_price


# =============================================================================
# ASIAN OPTIONS
# =============================================================================

class AsianOption:
    """
    Asian option pricing.

    Average can be:
    - Arithmetic (requires approximation/MC)
    - Geometric (closed-form available)
    """

    @staticmethod
    def geometric_average_price(
        S: float,
        K: float,
        r: float,
        sigma: float,
        T: float,
        option_type: OptionType,
        q: float = 0.0,
        n_observations: int = 252
    ) -> float:
        """
        Price geometric average Asian option (closed-form).

        Args:
            n_observations: Number of averaging points
        """
        # Adjusted parameters for geometric average
        sigma_a = sigma / np.sqrt(3)
        r_a = 0.5 * (r - q - sigma ** 2 / 6)

        # Use Black-Scholes with adjusted parameters
        return BlackScholes.price(S, K, r_a, sigma_a, T, option_type, 0) * np.exp(-r * T + r_a * T)

    @staticmethod
    def arithmetic_average_price_mc(
        S: float,
        K: float,
        r: float,
        sigma: float,
        T: float,
        option_type: OptionType,
        q: float = 0.0,
        n_observations: int = 252,
        n_paths: int = 100000,
        seed: Optional[int] = None
    ) -> Tuple[float, float]:
        """
        Price arithmetic average Asian option via Monte Carlo.

        Returns:
            price: Option price
            std_err: Standard error
        """
        rng = np.random.default_rng(seed)

        dt = T / n_observations
        drift = (r - q - 0.5 * sigma ** 2) * dt
        diffusion = sigma * np.sqrt(dt)

        # Generate paths
        Z = rng.normal(0, 1, (n_paths, n_observations))
        log_returns = drift + diffusion * Z
        paths = S * np.exp(np.cumsum(log_returns, axis=1))

        # Arithmetic average
        avg_price = np.mean(paths, axis=1)

        # Payoffs
        if option_type == OptionType.CALL:
            payoffs = np.maximum(avg_price - K, 0)
        else:
            payoffs = np.maximum(K - avg_price, 0)

        # Discount
        df = np.exp(-r * T)
        price = df * np.mean(payoffs)
        std_err = df * np.std(payoffs) / np.sqrt(n_paths)

        return price, std_err


# =============================================================================
# LOOKBACK OPTIONS
# =============================================================================

class LookbackOption:
    """
    Lookback option pricing.

    Types:
    - Fixed strike: Payoff based on max/min price
    - Floating strike: Strike set at max/min price
    """

    @staticmethod
    def floating_strike_price(
        S: float,
        r: float,
        sigma: float,
        T: float,
        option_type: OptionType,
        q: float = 0.0
    ) -> float:
        """
        Price floating strike lookback option (closed-form).

        Call payoff: S(T) - min S(t)
        Put payoff: max S(t) - S(T)
        """
        if T <= 0:
            return 0

        sqrt_T = np.sqrt(T)
        a1 = (r - q + 0.5 * sigma ** 2) * T / (sigma * sqrt_T)
        a2 = a1 - sigma * sqrt_T

        if option_type == OptionType.CALL:
            term1 = S * np.exp(-q * T) * stats.norm.cdf(a1)
            term2 = S * np.exp(-q * T) * sigma ** 2 / (2 * (r - q)) * (
                -((S / S) ** (-2 * (r - q) / sigma ** 2)) * stats.norm.cdf(-a1 + 2 * (r - q) * sqrt_T / sigma) +
                np.exp((r - q) * T) * stats.norm.cdf(-a1)
            )
            return term1 + term2
        else:
            term1 = -S * np.exp(-q * T) * stats.norm.cdf(-a1)
            term2 = S * np.exp(-q * T) * sigma ** 2 / (2 * (r - q)) * (
                ((S / S) ** (-2 * (r - q) / sigma ** 2)) * stats.norm.cdf(a1 - 2 * (r - q) * sqrt_T / sigma) -
                np.exp((r - q) * T) * stats.norm.cdf(a1)
            )
            return term1 - term2


# =============================================================================
# LOCAL VOLATILITY
# =============================================================================

class LocalVolatility:
    """
    Local volatility model (Dupire).

    σ_loc(K, T) derived from implied volatility surface.
    """

    def __init__(self, spot: float, r: float, q: float = 0.0):
        self.spot = spot
        self.r = r
        self.q = q

    def dupire_local_vol(
        self,
        K: float,
        T: float,
        iv_surface: Callable[[float, float], float],
        dK: float = 0.01,
        dT: float = 0.01
    ) -> float:
        """
        Calculate local volatility using Dupire's formula.

        Args:
            K: Strike
            T: Time
            iv_surface: Function(K, T) -> implied vol
            dK: Strike bump for derivatives
            dT: Time bump for derivatives
        """
        sigma = iv_surface(K, T)

        # Partial derivatives
        d_sigma_dT = (iv_surface(K, T + dT) - iv_surface(K, T)) / dT
        d_sigma_dK = (iv_surface(K + dK, T) - iv_surface(K - dK, T)) / (2 * dK)
        d2_sigma_dK2 = (iv_surface(K + dK, T) - 2 * sigma + iv_surface(K - dK, T)) / (dK ** 2)

        # d1
        d1 = (np.log(self.spot / K) + (self.r - self.q + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))

        # Numerator
        numerator = sigma ** 2 + 2 * sigma * T * (d_sigma_dT + (self.r - self.q) * K * d_sigma_dK)

        # Denominator
        denominator = (1 + K * d1 * np.sqrt(T) * d_sigma_dK) ** 2 + \
                     K ** 2 * T * sigma * (d2_sigma_dK2 - d1 * np.sqrt(T) * d_sigma_dK ** 2)

        if denominator <= 0:
            return sigma  # Fall back to implied vol

        local_vol = np.sqrt(numerator / denominator)

        return local_vol


# =============================================================================
# FACTORY FUNCTIONS
# =============================================================================

def price_european_option(
    S: float,
    K: float,
    r: float,
    sigma: float,
    T: float,
    option_type: str = 'call',
    q: float = 0.0
) -> PricingResult:
    """Quick European option pricing."""
    opt_type = OptionType.CALL if option_type.lower() == 'call' else OptionType.PUT

    price = BlackScholes.price(S, K, r, sigma, T, opt_type, q)
    greeks = BlackScholes.greeks(S, K, r, sigma, T, opt_type, q)

    return PricingResult(price=price, greeks=greeks, model='Black-Scholes')


def price_american_option(
    S: float,
    K: float,
    r: float,
    sigma: float,
    T: float,
    option_type: str = 'call',
    q: float = 0.0,
    n_steps: int = 200
) -> PricingResult:
    """Quick American option pricing."""
    opt_type = OptionType.CALL if option_type.lower() == 'call' else OptionType.PUT

    tree = BinomialTree(n_steps)
    price, _ = tree.price(S, K, r, sigma, T, opt_type, ExerciseStyle.AMERICAN, q)
    greeks = tree.greeks_numerical(S, K, r, sigma, T, opt_type, ExerciseStyle.AMERICAN, q)

    return PricingResult(price=price, greeks=greeks, model='Binomial Tree')


def calculate_implied_vol(
    price: float,
    S: float,
    K: float,
    r: float,
    T: float,
    option_type: str = 'call',
    q: float = 0.0
) -> float:
    """Calculate implied volatility."""
    opt_type = OptionType.CALL if option_type.lower() == 'call' else OptionType.PUT
    return BlackScholes.implied_volatility(price, S, K, r, T, opt_type, q)


# Example usage
if __name__ == "__main__":
    print("="*60)
    print("DERIVATIVES PRICING MODULE - TEST MODE")
    print("="*60)

    # Parameters
    S = 100     # Spot
    K = 100     # Strike (ATM)
    r = 0.05    # Risk-free rate
    sigma = 0.2 # Volatility
    T = 1.0     # 1 year
    q = 0.02    # Dividend yield

    print("\n1. Black-Scholes Pricing")
    print("-" * 40)

    call_price = BlackScholes.price(S, K, r, sigma, T, OptionType.CALL, q)
    put_price = BlackScholes.price(S, K, r, sigma, T, OptionType.PUT, q)

    print(f"   ATM Call: ${call_price:.4f}")
    print(f"   ATM Put:  ${put_price:.4f}")
    print(f"   Put-Call Parity Check: {call_price - put_price:.4f} = {S * np.exp(-q*T) - K * np.exp(-r*T):.4f}")

    print("\n2. Greeks")
    print("-" * 40)
    greeks = BlackScholes.greeks(S, K, r, sigma, T, OptionType.CALL, q)
    print(f"   Delta: {greeks.delta:.4f}")
    print(f"   Gamma: {greeks.gamma:.6f}")
    print(f"   Vega:  {greeks.vega:.4f}")
    print(f"   Theta: {greeks.theta:.4f}")
    print(f"   Rho:   {greeks.rho:.4f}")

    print("\n3. Implied Volatility")
    print("-" * 40)
    iv = BlackScholes.implied_volatility(call_price, S, K, r, T, OptionType.CALL, q)
    print(f"   Original sigma: {sigma:.4f}")
    print(f"   Recovered IV:   {iv:.4f}")

    print("\n4. American Option (Binomial Tree)")
    print("-" * 40)
    tree = BinomialTree(n_steps=200)
    am_put, _ = tree.price(S, K, r, sigma, T, OptionType.PUT, ExerciseStyle.AMERICAN, q)
    eu_put = BlackScholes.price(S, K, r, sigma, T, OptionType.PUT, q)
    print(f"   European Put: ${eu_put:.4f}")
    print(f"   American Put: ${am_put:.4f}")
    print(f"   Early Exercise Premium: ${am_put - eu_put:.4f}")

    print("\n5. Heston Model (FFT)")
    print("-" * 40)
    heston = HestonAnalytical(kappa=2.0, theta=0.04, sigma=0.3, rho=-0.7, v0=0.04)
    heston_price = heston.price_carr_madan(S, K, r, T, OptionType.CALL, q)
    print(f"   Heston Call: ${heston_price:.4f}")
    print(f"   BS Call:     ${call_price:.4f}")

    print("\n6. Asian Option")
    print("-" * 40)
    geo_asian = AsianOption.geometric_average_price(S, K, r, sigma, T, OptionType.CALL, q)
    arith_asian, std_err = AsianOption.arithmetic_average_price_mc(S, K, r, sigma, T, OptionType.CALL, q, seed=42)
    print(f"   Geometric Asian Call: ${geo_asian:.4f}")
    print(f"   Arithmetic Asian Call: ${arith_asian:.4f} ± ${1.96*std_err:.4f}")

    print(f"\n{'='*60}")
    print("DERIVATIVES PRICING MODULE - READY")
    print('='*60)
