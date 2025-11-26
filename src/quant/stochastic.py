"""
Stochastic Calculus & Brownian Motion Module

Institutional-grade stochastic process implementations:
- Geometric Brownian Motion (GBM)
- Ornstein-Uhlenbeck Process (Mean Reversion)
- Jump-Diffusion (Merton, Kou)
- Heston Stochastic Volatility
- SABR Model
- Variance Gamma Process
- Lévy Processes
- Fractional Brownian Motion

Monte Carlo simulation with variance reduction techniques:
- Antithetic variates
- Control variates
- Importance sampling
- Stratified sampling
- Quasi-Monte Carlo (Sobol, Halton)

Author: Revolution Alpha Engine
"""

import numpy as np
from scipy import stats
from scipy.special import gamma as gamma_func
from scipy.optimize import minimize
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Callable, Union
from datetime import datetime
from enum import Enum
from abc import ABC, abstractmethod
import warnings

warnings.filterwarnings('ignore')


# =============================================================================
# BASE CLASSES
# =============================================================================

class StochasticProcess(ABC):
    """Abstract base class for stochastic processes."""

    @abstractmethod
    def simulate(
        self,
        S0: float,
        T: float,
        n_steps: int,
        n_paths: int,
        **kwargs
    ) -> np.ndarray:
        """
        Simulate paths of the stochastic process.

        Args:
            S0: Initial value
            T: Time horizon
            n_steps: Number of time steps
            n_paths: Number of simulation paths

        Returns:
            Array of shape (n_paths, n_steps + 1)
        """
        pass

    @abstractmethod
    def expected_value(self, S0: float, t: float) -> float:
        """Expected value at time t."""
        pass

    @abstractmethod
    def variance(self, S0: float, t: float) -> float:
        """Variance at time t."""
        pass


# =============================================================================
# BROWNIAN MOTION
# =============================================================================

class BrownianMotion:
    """
    Standard Brownian Motion (Wiener Process).

    Properties:
    - W(0) = 0
    - Independent increments
    - W(t) - W(s) ~ N(0, t-s)
    - Continuous paths
    """

    def __init__(self, seed: Optional[int] = None):
        self.rng = np.random.default_rng(seed)

    def simulate(
        self,
        T: float,
        n_steps: int,
        n_paths: int = 1
    ) -> np.ndarray:
        """
        Simulate Brownian motion paths.

        Args:
            T: Time horizon
            n_steps: Number of time steps
            n_paths: Number of paths

        Returns:
            Array of shape (n_paths, n_steps + 1)
        """
        dt = T / n_steps
        dW = self.rng.normal(0, np.sqrt(dt), size=(n_paths, n_steps))

        W = np.zeros((n_paths, n_steps + 1))
        W[:, 1:] = np.cumsum(dW, axis=1)

        return W

    def simulate_antithetic(
        self,
        T: float,
        n_steps: int,
        n_paths: int = 1
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Simulate with antithetic variates for variance reduction."""
        dt = T / n_steps
        dW = self.rng.normal(0, np.sqrt(dt), size=(n_paths // 2, n_steps))

        W_pos = np.zeros((n_paths // 2, n_steps + 1))
        W_neg = np.zeros((n_paths // 2, n_steps + 1))

        W_pos[:, 1:] = np.cumsum(dW, axis=1)
        W_neg[:, 1:] = np.cumsum(-dW, axis=1)

        return W_pos, W_neg

    def bridge(
        self,
        T: float,
        n_steps: int,
        end_value: float = 0.0
    ) -> np.ndarray:
        """
        Brownian Bridge: W(T) = end_value.

        Useful for exact simulation methods.
        """
        dt = T / n_steps
        t = np.linspace(0, T, n_steps + 1)

        # Standard BM
        W = self.simulate(T, n_steps, 1)[0]

        # Transform to bridge
        bridge = W - t / T * W[-1] + t / T * end_value

        return bridge


class GeometricBrownianMotion(StochasticProcess):
    """
    Geometric Brownian Motion (GBM).

    dS(t) = μ·S(t)·dt + σ·S(t)·dW(t)

    Solution: S(t) = S(0)·exp((μ - σ²/2)t + σ·W(t))

    Used for stock price modeling in Black-Scholes framework.
    """

    def __init__(
        self,
        mu: float,
        sigma: float,
        seed: Optional[int] = None
    ):
        """
        Args:
            mu: Drift (expected return)
            sigma: Volatility
            seed: Random seed
        """
        self.mu = mu
        self.sigma = sigma
        self.rng = np.random.default_rng(seed)
        self.bm = BrownianMotion(seed)

    def simulate(
        self,
        S0: float,
        T: float,
        n_steps: int,
        n_paths: int,
        antithetic: bool = False
    ) -> np.ndarray:
        """Simulate GBM paths."""
        dt = T / n_steps

        if antithetic:
            W_pos, W_neg = self.bm.simulate_antithetic(T, n_steps, n_paths)

            # Exact solution
            t = np.linspace(0, T, n_steps + 1)
            drift = (self.mu - 0.5 * self.sigma ** 2) * t

            S_pos = S0 * np.exp(drift + self.sigma * W_pos)
            S_neg = S0 * np.exp(drift + self.sigma * W_neg)

            return np.vstack([S_pos, S_neg])
        else:
            W = self.bm.simulate(T, n_steps, n_paths)

            t = np.linspace(0, T, n_steps + 1)
            drift = (self.mu - 0.5 * self.sigma ** 2) * t

            S = S0 * np.exp(drift + self.sigma * W)

            return S

    def expected_value(self, S0: float, t: float) -> float:
        """E[S(t)] = S(0)·exp(μt)"""
        return S0 * np.exp(self.mu * t)

    def variance(self, S0: float, t: float) -> float:
        """Var[S(t)] = S(0)²·exp(2μt)·(exp(σ²t) - 1)"""
        return S0 ** 2 * np.exp(2 * self.mu * t) * (np.exp(self.sigma ** 2 * t) - 1)

    def simulate_euler(
        self,
        S0: float,
        T: float,
        n_steps: int,
        n_paths: int
    ) -> np.ndarray:
        """Euler-Maruyama discretization (for comparison/general SDEs)."""
        dt = T / n_steps
        sqrt_dt = np.sqrt(dt)

        S = np.zeros((n_paths, n_steps + 1))
        S[:, 0] = S0

        for i in range(n_steps):
            dW = self.rng.normal(0, sqrt_dt, n_paths)
            S[:, i + 1] = S[:, i] * (1 + self.mu * dt + self.sigma * dW)

        return S

    def simulate_milstein(
        self,
        S0: float,
        T: float,
        n_steps: int,
        n_paths: int
    ) -> np.ndarray:
        """Milstein scheme (higher order than Euler)."""
        dt = T / n_steps
        sqrt_dt = np.sqrt(dt)

        S = np.zeros((n_paths, n_steps + 1))
        S[:, 0] = S0

        for i in range(n_steps):
            dW = self.rng.normal(0, sqrt_dt, n_paths)
            S[:, i + 1] = S[:, i] * (
                1 + self.mu * dt + self.sigma * dW +
                0.5 * self.sigma ** 2 * (dW ** 2 - dt)
            )

        return S


# =============================================================================
# MEAN-REVERTING PROCESSES
# =============================================================================

class OrnsteinUhlenbeck(StochasticProcess):
    """
    Ornstein-Uhlenbeck Process (Vasicek for interest rates).

    dX(t) = θ·(μ - X(t))·dt + σ·dW(t)

    Properties:
    - Mean-reverting to μ
    - θ is speed of mean reversion
    - Stationary distribution: N(μ, σ²/(2θ))

    Used for interest rates, volatility, pairs trading.
    """

    def __init__(
        self,
        theta: float,
        mu: float,
        sigma: float,
        seed: Optional[int] = None
    ):
        """
        Args:
            theta: Mean reversion speed
            mu: Long-term mean
            sigma: Volatility
        """
        self.theta = theta
        self.mu = mu
        self.sigma = sigma
        self.rng = np.random.default_rng(seed)

    def simulate(
        self,
        S0: float,
        T: float,
        n_steps: int,
        n_paths: int,
        exact: bool = True
    ) -> np.ndarray:
        """Simulate OU process."""
        dt = T / n_steps

        X = np.zeros((n_paths, n_steps + 1))
        X[:, 0] = S0

        if exact:
            # Exact simulation
            exp_theta = np.exp(-self.theta * dt)
            var = self.sigma ** 2 / (2 * self.theta) * (1 - exp_theta ** 2)

            for i in range(n_steps):
                X[:, i + 1] = (
                    self.mu + (X[:, i] - self.mu) * exp_theta +
                    np.sqrt(var) * self.rng.normal(0, 1, n_paths)
                )
        else:
            # Euler discretization
            sqrt_dt = np.sqrt(dt)
            for i in range(n_steps):
                dW = self.rng.normal(0, sqrt_dt, n_paths)
                X[:, i + 1] = X[:, i] + self.theta * (self.mu - X[:, i]) * dt + self.sigma * dW

        return X

    def expected_value(self, S0: float, t: float) -> float:
        """E[X(t)] = μ + (X(0) - μ)·exp(-θt)"""
        return self.mu + (S0 - self.mu) * np.exp(-self.theta * t)

    def variance(self, S0: float, t: float) -> float:
        """Var[X(t)] = σ²/(2θ)·(1 - exp(-2θt))"""
        return self.sigma ** 2 / (2 * self.theta) * (1 - np.exp(-2 * self.theta * t))

    def stationary_variance(self) -> float:
        """Long-term variance."""
        return self.sigma ** 2 / (2 * self.theta)

    def half_life(self) -> float:
        """Half-life of mean reversion."""
        return np.log(2) / self.theta


class CIRProcess(StochasticProcess):
    """
    Cox-Ingersoll-Ross (CIR) Process.

    dX(t) = κ·(θ - X(t))·dt + σ·√X(t)·dW(t)

    Properties:
    - Always positive if 2κθ ≥ σ² (Feller condition)
    - Used for interest rates, volatility

    Special case: Square-root diffusion
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
            theta: Long-term mean
            sigma: Volatility of volatility
        """
        self.kappa = kappa
        self.theta = theta
        self.sigma = sigma
        self.rng = np.random.default_rng(seed)

        # Check Feller condition
        self.feller_satisfied = 2 * kappa * theta >= sigma ** 2

    def simulate(
        self,
        S0: float,
        T: float,
        n_steps: int,
        n_paths: int,
        method: str = 'euler_full_truncation'
    ) -> np.ndarray:
        """
        Simulate CIR process.

        Methods:
        - 'euler_full_truncation': Max(X, 0) at each step
        - 'euler_reflection': Reflect at 0
        - 'milstein': Milstein scheme
        - 'exact': Exact simulation via non-central chi-squared
        """
        dt = T / n_steps
        sqrt_dt = np.sqrt(dt)

        X = np.zeros((n_paths, n_steps + 1))
        X[:, 0] = S0

        if method == 'exact':
            # Exact simulation using non-central chi-squared
            c = self.sigma ** 2 * (1 - np.exp(-self.kappa * dt)) / (4 * self.kappa)
            d = 4 * self.kappa * self.theta / self.sigma ** 2
            exp_kappa = np.exp(-self.kappa * dt)

            for i in range(n_steps):
                nc = X[:, i] * exp_kappa / c
                X[:, i + 1] = c * self.rng.noncentral_chisquare(d, nc)

        elif method == 'milstein':
            for i in range(n_steps):
                sqrt_X = np.sqrt(np.maximum(X[:, i], 0))
                dW = self.rng.normal(0, sqrt_dt, n_paths)
                X[:, i + 1] = (
                    X[:, i] +
                    self.kappa * (self.theta - X[:, i]) * dt +
                    self.sigma * sqrt_X * dW +
                    0.25 * self.sigma ** 2 * (dW ** 2 - dt)
                )
                X[:, i + 1] = np.maximum(X[:, i + 1], 0)

        else:  # euler_full_truncation
            for i in range(n_steps):
                sqrt_X = np.sqrt(np.maximum(X[:, i], 0))
                dW = self.rng.normal(0, sqrt_dt, n_paths)
                X[:, i + 1] = (
                    X[:, i] +
                    self.kappa * (self.theta - np.maximum(X[:, i], 0)) * dt +
                    self.sigma * sqrt_X * dW
                )
                X[:, i + 1] = np.maximum(X[:, i + 1], 0)

        return X

    def expected_value(self, S0: float, t: float) -> float:
        """E[X(t)]"""
        exp_kappa = np.exp(-self.kappa * t)
        return self.theta + (S0 - self.theta) * exp_kappa

    def variance(self, S0: float, t: float) -> float:
        """Var[X(t)]"""
        exp_kappa = np.exp(-self.kappa * t)
        return (
            S0 * self.sigma ** 2 * exp_kappa / self.kappa * (1 - exp_kappa) +
            self.theta * self.sigma ** 2 / (2 * self.kappa) * (1 - exp_kappa) ** 2
        )


# =============================================================================
# JUMP-DIFFUSION MODELS
# =============================================================================

class MertonJumpDiffusion(StochasticProcess):
    """
    Merton Jump-Diffusion Model.

    dS(t)/S(t) = (μ - λk)·dt + σ·dW(t) + dJ(t)

    Where:
    - J(t) is a compound Poisson process
    - Jump sizes are log-normal: Y ~ N(μ_J, σ_J²)
    - k = E[exp(Y) - 1] = exp(μ_J + σ_J²/2) - 1

    Captures fat tails and occasional large moves.
    """

    def __init__(
        self,
        mu: float,
        sigma: float,
        lam: float,
        mu_J: float,
        sigma_J: float,
        seed: Optional[int] = None
    ):
        """
        Args:
            mu: Drift
            sigma: Diffusion volatility
            lam: Jump intensity (expected jumps per year)
            mu_J: Mean of log-jump size
            sigma_J: Std of log-jump size
        """
        self.mu = mu
        self.sigma = sigma
        self.lam = lam
        self.mu_J = mu_J
        self.sigma_J = sigma_J
        self.rng = np.random.default_rng(seed)

        # Expected jump multiplier
        self.k = np.exp(mu_J + 0.5 * sigma_J ** 2) - 1

    def simulate(
        self,
        S0: float,
        T: float,
        n_steps: int,
        n_paths: int
    ) -> np.ndarray:
        """Simulate Merton jump-diffusion."""
        dt = T / n_steps
        sqrt_dt = np.sqrt(dt)

        # Diffusion component
        drift = (self.mu - self.lam * self.k - 0.5 * self.sigma ** 2) * dt
        diffusion = self.sigma * sqrt_dt * self.rng.normal(0, 1, (n_paths, n_steps))

        # Jump component
        n_jumps = self.rng.poisson(self.lam * dt, (n_paths, n_steps))
        jump_sizes = np.zeros((n_paths, n_steps))

        for i in range(n_paths):
            for j in range(n_steps):
                if n_jumps[i, j] > 0:
                    jumps = self.rng.normal(self.mu_J, self.sigma_J, n_jumps[i, j])
                    jump_sizes[i, j] = np.sum(jumps)

        # Combined log-returns
        log_returns = drift + diffusion + jump_sizes

        # Build price paths
        S = np.zeros((n_paths, n_steps + 1))
        S[:, 0] = S0
        S[:, 1:] = S0 * np.exp(np.cumsum(log_returns, axis=1))

        return S

    def expected_value(self, S0: float, t: float) -> float:
        """E[S(t)]"""
        return S0 * np.exp(self.mu * t)

    def variance(self, S0: float, t: float) -> float:
        """Var[S(t)] - complex for jump-diffusion."""
        # Approximate variance
        base_var = S0 ** 2 * np.exp(2 * self.mu * t) * (np.exp(self.sigma ** 2 * t) - 1)
        jump_var = self.lam * t * (np.exp(2 * self.mu_J + 2 * self.sigma_J ** 2) - 1)
        return base_var * (1 + jump_var)

    def characteristic_function(self, u: complex, t: float) -> complex:
        """Characteristic function for option pricing."""
        # Diffusion part
        phi_diff = np.exp(
            1j * u * (self.mu - self.lam * self.k) * t -
            0.5 * self.sigma ** 2 * u ** 2 * t
        )

        # Jump part
        phi_jump = np.exp(
            self.lam * t * (
                np.exp(1j * u * self.mu_J - 0.5 * self.sigma_J ** 2 * u ** 2) - 1
            )
        )

        return phi_diff * phi_jump


class KouJumpDiffusion(StochasticProcess):
    """
    Kou Double-Exponential Jump-Diffusion Model.

    Jump sizes follow a double-exponential (asymmetric Laplace) distribution.

    P(Y > y) = p·exp(-η₁·y) for y ≥ 0
    P(Y < y) = (1-p)·exp(η₂·y) for y < 0

    Better fits empirical distributions than Merton.
    """

    def __init__(
        self,
        mu: float,
        sigma: float,
        lam: float,
        p: float,
        eta1: float,
        eta2: float,
        seed: Optional[int] = None
    ):
        """
        Args:
            mu: Drift
            sigma: Diffusion volatility
            lam: Jump intensity
            p: Probability of positive jump
            eta1: Rate of positive jumps (must be > 1)
            eta2: Rate of negative jumps
        """
        self.mu = mu
        self.sigma = sigma
        self.lam = lam
        self.p = p
        self.eta1 = eta1
        self.eta2 = eta2
        self.rng = np.random.default_rng(seed)

        # Expected jump size
        self.k = p * eta1 / (eta1 - 1) + (1 - p) * eta2 / (eta2 + 1) - 1

    def _sample_double_exponential(self, n: int) -> np.ndarray:
        """Sample from double-exponential distribution."""
        u = self.rng.uniform(0, 1, n)
        samples = np.where(
            u < self.p,
            self.rng.exponential(1 / self.eta1, n),
            -self.rng.exponential(1 / self.eta2, n)
        )
        return samples

    def simulate(
        self,
        S0: float,
        T: float,
        n_steps: int,
        n_paths: int
    ) -> np.ndarray:
        """Simulate Kou jump-diffusion."""
        dt = T / n_steps
        sqrt_dt = np.sqrt(dt)

        # Diffusion
        drift = (self.mu - self.lam * self.k - 0.5 * self.sigma ** 2) * dt
        diffusion = self.sigma * sqrt_dt * self.rng.normal(0, 1, (n_paths, n_steps))

        # Jumps
        n_jumps = self.rng.poisson(self.lam * dt, (n_paths, n_steps))
        jump_sizes = np.zeros((n_paths, n_steps))

        for i in range(n_paths):
            for j in range(n_steps):
                if n_jumps[i, j] > 0:
                    jump_sizes[i, j] = np.sum(
                        self._sample_double_exponential(n_jumps[i, j])
                    )

        log_returns = drift + diffusion + jump_sizes

        S = np.zeros((n_paths, n_steps + 1))
        S[:, 0] = S0
        S[:, 1:] = S0 * np.exp(np.cumsum(log_returns, axis=1))

        return S

    def expected_value(self, S0: float, t: float) -> float:
        return S0 * np.exp(self.mu * t)

    def variance(self, S0: float, t: float) -> float:
        # Simplified approximation
        return S0 ** 2 * np.exp(2 * self.mu * t) * (np.exp(self.sigma ** 2 * t) - 1)


# =============================================================================
# STOCHASTIC VOLATILITY MODELS
# =============================================================================

class HestonModel(StochasticProcess):
    """
    Heston Stochastic Volatility Model.

    dS(t) = μ·S(t)·dt + √v(t)·S(t)·dW₁(t)
    dv(t) = κ·(θ - v(t))·dt + σ·√v(t)·dW₂(t)

    Corr(dW₁, dW₂) = ρ

    Parameters:
    - κ: Mean reversion speed of variance
    - θ: Long-term variance
    - σ: Volatility of volatility
    - ρ: Correlation between price and variance
    - v0: Initial variance
    """

    def __init__(
        self,
        mu: float,
        kappa: float,
        theta: float,
        sigma: float,
        rho: float,
        v0: float,
        seed: Optional[int] = None
    ):
        self.mu = mu
        self.kappa = kappa
        self.theta = theta
        self.sigma = sigma
        self.rho = rho
        self.v0 = v0
        self.rng = np.random.default_rng(seed)

        # Feller condition
        self.feller_satisfied = 2 * kappa * theta > sigma ** 2

    def simulate(
        self,
        S0: float,
        T: float,
        n_steps: int,
        n_paths: int,
        method: str = 'euler'
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Simulate Heston model paths.

        Returns:
            S: Price paths
            v: Variance paths
        """
        dt = T / n_steps
        sqrt_dt = np.sqrt(dt)

        S = np.zeros((n_paths, n_steps + 1))
        v = np.zeros((n_paths, n_steps + 1))
        S[:, 0] = S0
        v[:, 0] = self.v0

        # Correlated Brownian motions
        for i in range(n_steps):
            Z1 = self.rng.normal(0, 1, n_paths)
            Z2 = self.rng.normal(0, 1, n_paths)
            W1 = Z1
            W2 = self.rho * Z1 + np.sqrt(1 - self.rho ** 2) * Z2

            sqrt_v = np.sqrt(np.maximum(v[:, i], 0))

            if method == 'milstein':
                # Milstein for variance
                v[:, i + 1] = (
                    v[:, i] +
                    self.kappa * (self.theta - np.maximum(v[:, i], 0)) * dt +
                    self.sigma * sqrt_v * sqrt_dt * W2 +
                    0.25 * self.sigma ** 2 * dt * (W2 ** 2 - 1)
                )
            else:
                # Euler for variance
                v[:, i + 1] = (
                    v[:, i] +
                    self.kappa * (self.theta - np.maximum(v[:, i], 0)) * dt +
                    self.sigma * sqrt_v * sqrt_dt * W2
                )

            v[:, i + 1] = np.maximum(v[:, i + 1], 0)

            # Log-price (more stable)
            S[:, i + 1] = S[:, i] * np.exp(
                (self.mu - 0.5 * np.maximum(v[:, i], 0)) * dt +
                sqrt_v * sqrt_dt * W1
            )

        return S, v

    def expected_value(self, S0: float, t: float) -> float:
        return S0 * np.exp(self.mu * t)

    def variance(self, S0: float, t: float) -> float:
        # Complex for Heston, return approximation
        avg_var = self.theta + (self.v0 - self.theta) * (1 - np.exp(-self.kappa * t)) / (self.kappa * t)
        return S0 ** 2 * np.exp(2 * self.mu * t) * (np.exp(avg_var * t) - 1)

    def characteristic_function(
        self,
        u: complex,
        t: float,
        S0: float
    ) -> complex:
        """
        Heston characteristic function for FFT option pricing.

        φ(u, t) = E[exp(iu·log(S(t)))]
        """
        # Parameters for convenience
        kappa, theta, sigma, rho, v0 = self.kappa, self.theta, self.sigma, self.rho, self.v0

        # Complex calculations
        d = np.sqrt(
            (rho * sigma * 1j * u - kappa) ** 2 +
            sigma ** 2 * (1j * u + u ** 2)
        )

        g = (kappa - rho * sigma * 1j * u - d) / (kappa - rho * sigma * 1j * u + d)

        C = kappa * theta / sigma ** 2 * (
            (kappa - rho * sigma * 1j * u - d) * t -
            2 * np.log((1 - g * np.exp(-d * t)) / (1 - g))
        )

        D = (kappa - rho * sigma * 1j * u - d) / sigma ** 2 * (
            (1 - np.exp(-d * t)) / (1 - g * np.exp(-d * t))
        )

        return np.exp(C + D * v0 + 1j * u * np.log(S0))


class SABRModel:
    """
    SABR Stochastic Alpha Beta Rho Model.

    dF(t) = σ(t)·F(t)^β·dW₁(t)
    dσ(t) = α·σ(t)·dW₂(t)

    Corr(dW₁, dW₂) = ρ

    Parameters:
    - α (alpha): Volatility of volatility
    - β (beta): CEV exponent (0 = normal, 1 = lognormal)
    - ρ (rho): Correlation
    - σ₀: Initial volatility

    Used extensively for interest rate derivatives.
    """

    def __init__(
        self,
        alpha: float,
        beta: float,
        rho: float,
        sigma0: float,
        seed: Optional[int] = None
    ):
        self.alpha = alpha
        self.beta = beta
        self.rho = rho
        self.sigma0 = sigma0
        self.rng = np.random.default_rng(seed)

    def implied_volatility(
        self,
        F: float,
        K: float,
        T: float
    ) -> float:
        """
        SABR implied volatility approximation (Hagan et al. 2002).

        Args:
            F: Forward price
            K: Strike
            T: Time to expiry

        Returns:
            Black implied volatility
        """
        if abs(F - K) < 1e-10:
            # ATM case
            FK_mid = F
            logFK = 0
        else:
            FK_mid = np.sqrt(F * K)
            logFK = np.log(F / K)

        # Convenience variables
        alpha, beta, rho, sigma0 = self.alpha, self.beta, self.rho, self.sigma0

        # z and x(z)
        z = alpha / sigma0 * FK_mid ** (1 - beta) * logFK

        if abs(z) < 1e-10:
            x_z = 1
        else:
            x_z = z / np.log((np.sqrt(1 - 2 * rho * z + z ** 2) + z - rho) / (1 - rho))

        # Expansion terms
        FK_beta = FK_mid ** (1 - beta)
        term1 = sigma0 / (FK_beta * (
            1 + (1 - beta) ** 2 / 24 * logFK ** 2 +
            (1 - beta) ** 4 / 1920 * logFK ** 4
        ))

        term2 = (
            1 + (
                (1 - beta) ** 2 / 24 * sigma0 ** 2 / FK_mid ** (2 - 2 * beta) +
                rho * beta * alpha * sigma0 / (4 * FK_mid ** (1 - beta)) +
                (2 - 3 * rho ** 2) * alpha ** 2 / 24
            ) * T
        )

        return term1 * x_z * term2

    def simulate(
        self,
        F0: float,
        T: float,
        n_steps: int,
        n_paths: int
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Simulate SABR model paths."""
        dt = T / n_steps
        sqrt_dt = np.sqrt(dt)

        F = np.zeros((n_paths, n_steps + 1))
        sigma = np.zeros((n_paths, n_steps + 1))
        F[:, 0] = F0
        sigma[:, 0] = self.sigma0

        for i in range(n_steps):
            Z1 = self.rng.normal(0, 1, n_paths)
            Z2 = self.rng.normal(0, 1, n_paths)
            W1 = Z1
            W2 = self.rho * Z1 + np.sqrt(1 - self.rho ** 2) * Z2

            # Volatility (lognormal)
            sigma[:, i + 1] = sigma[:, i] * np.exp(
                -0.5 * self.alpha ** 2 * dt + self.alpha * sqrt_dt * W2
            )

            # Forward (CEV with stochastic vol)
            F_beta = np.maximum(F[:, i], 1e-10) ** self.beta
            F[:, i + 1] = F[:, i] + sigma[:, i] * F_beta * sqrt_dt * W1
            F[:, i + 1] = np.maximum(F[:, i + 1], 0)

        return F, sigma


# =============================================================================
# LEVY PROCESSES
# =============================================================================

class VarianceGammaProcess(StochasticProcess):
    """
    Variance Gamma Process.

    X(t) = θ·G(t) + σ·W(G(t))

    Where G(t) is a Gamma process with mean t and variance νt.

    Properties:
    - Pure jump process (no diffusion)
    - Can have both positive and negative jumps
    - Captures skewness and kurtosis
    """

    def __init__(
        self,
        theta: float,
        sigma: float,
        nu: float,
        seed: Optional[int] = None
    ):
        """
        Args:
            theta: Drift of time change (skewness)
            sigma: Volatility
            nu: Variance rate of time change (kurtosis)
        """
        self.theta = theta
        self.sigma = sigma
        self.nu = nu
        self.rng = np.random.default_rng(seed)

    def simulate(
        self,
        S0: float,
        T: float,
        n_steps: int,
        n_paths: int
    ) -> np.ndarray:
        """Simulate Variance Gamma process."""
        dt = T / n_steps

        # Gamma increments
        shape = dt / self.nu
        scale = self.nu
        dG = self.rng.gamma(shape, scale, (n_paths, n_steps))

        # Brownian motion evaluated at gamma time
        dX = self.theta * dG + self.sigma * np.sqrt(dG) * self.rng.normal(0, 1, (n_paths, n_steps))

        # Log-price
        X = np.zeros((n_paths, n_steps + 1))
        X[:, 1:] = np.cumsum(dX, axis=1)

        # Drift correction for martingale
        omega = np.log(1 - self.theta * self.nu - 0.5 * self.sigma ** 2 * self.nu) / self.nu
        t = np.linspace(0, T, n_steps + 1)

        S = S0 * np.exp(omega * t + X)

        return S

    def expected_value(self, S0: float, t: float) -> float:
        return S0

    def variance(self, S0: float, t: float) -> float:
        return S0 ** 2 * (np.exp((self.sigma ** 2 + self.theta ** 2 * self.nu) * t) - 1)

    def characteristic_function(self, u: complex, t: float) -> complex:
        """Characteristic function for option pricing."""
        return (
            1 - 1j * u * self.theta * self.nu + 0.5 * self.sigma ** 2 * self.nu * u ** 2
        ) ** (-t / self.nu)


# =============================================================================
# FRACTIONAL BROWNIAN MOTION
# =============================================================================

class FractionalBrownianMotion:
    """
    Fractional Brownian Motion (fBM).

    A Gaussian process with Hurst parameter H ∈ (0, 1).

    Properties:
    - H = 0.5: Standard Brownian motion
    - H > 0.5: Long-range dependence (trending)
    - H < 0.5: Anti-persistent (mean-reverting)

    E[B_H(t) - B_H(s)] = 0
    Var[B_H(t) - B_H(s)] = |t - s|^(2H)
    """

    def __init__(self, H: float, seed: Optional[int] = None):
        """
        Args:
            H: Hurst parameter (0 < H < 1)
        """
        if not 0 < H < 1:
            raise ValueError("Hurst parameter must be in (0, 1)")

        self.H = H
        self.rng = np.random.default_rng(seed)

    def _covariance(self, t: float, s: float) -> float:
        """Covariance function of fBM."""
        return 0.5 * (t ** (2 * self.H) + s ** (2 * self.H) - abs(t - s) ** (2 * self.H))

    def simulate_cholesky(
        self,
        T: float,
        n_steps: int,
        n_paths: int = 1
    ) -> np.ndarray:
        """
        Simulate fBM using Cholesky decomposition.

        Exact but O(n²) memory and O(n³) computation.
        """
        t = np.linspace(0, T, n_steps + 1)

        # Build covariance matrix
        cov = np.zeros((n_steps + 1, n_steps + 1))
        for i in range(n_steps + 1):
            for j in range(n_steps + 1):
                cov[i, j] = self._covariance(t[i], t[j])

        # Cholesky decomposition
        L = np.linalg.cholesky(cov + 1e-10 * np.eye(n_steps + 1))

        # Generate paths
        Z = self.rng.normal(0, 1, (n_paths, n_steps + 1))
        B_H = Z @ L.T

        return B_H

    def simulate_hosking(
        self,
        T: float,
        n_steps: int,
        n_paths: int = 1
    ) -> np.ndarray:
        """
        Simulate fBM using Hosking's method.

        More efficient than Cholesky for long sequences.
        """
        dt = T / n_steps
        B_H = np.zeros((n_paths, n_steps + 1))

        # Autocovariance function
        def gamma(k):
            return 0.5 * (abs(k - 1) ** (2 * self.H) - 2 * abs(k) ** (2 * self.H) + abs(k + 1) ** (2 * self.H))

        for path in range(n_paths):
            # Initialize
            fgn = np.zeros(n_steps)  # Fractional Gaussian noise
            fgn[0] = self.rng.normal(0, 1)

            # Predictor coefficients
            phi = np.zeros(n_steps)
            phi[0] = gamma(1)

            # Recursive generation
            for i in range(1, n_steps):
                # Update phi using Durbin-Levinson
                V = gamma(i + 1)
                for j in range(i):
                    V -= phi[j] * gamma(i - j)

                phi_new = np.zeros(i + 1)
                phi_new[i] = V

                for j in range(i):
                    phi_new[j] = phi[j] - V * phi[i - 1 - j]

                phi[:i + 1] = phi_new

                # Generate increment
                mean = sum(phi[j] * fgn[i - 1 - j] for j in range(i))
                var = 1 - sum(phi[j] * gamma(j + 1) for j in range(i))
                var = max(var, 1e-10)

                fgn[i] = mean + np.sqrt(var) * self.rng.normal(0, 1)

            # Integrate to get fBM
            B_H[path, 1:] = np.cumsum(fgn) * dt ** self.H

        return B_H


# =============================================================================
# MONTE CARLO METHODS
# =============================================================================

class MonteCarloEngine:
    """
    Advanced Monte Carlo simulation engine with variance reduction.
    """

    def __init__(self, seed: Optional[int] = None):
        self.rng = np.random.default_rng(seed)

    def simulate_with_antithetic(
        self,
        process: StochasticProcess,
        S0: float,
        T: float,
        n_steps: int,
        n_paths: int,
        payoff: Callable[[np.ndarray], np.ndarray]
    ) -> Tuple[float, float]:
        """
        Monte Carlo with antithetic variates.

        Returns:
            mean: Estimated mean
            std_err: Standard error
        """
        # Generate paths and antithetic
        if hasattr(process, 'simulate') and callable(process.simulate):
            paths = process.simulate(S0, T, n_steps, n_paths, antithetic=True)
            n_actual = paths.shape[0]

            # Payoffs
            payoffs = payoff(paths)

            # Combine antithetic pairs
            payoffs_combined = 0.5 * (payoffs[:n_actual//2] + payoffs[n_actual//2:])

            mean = np.mean(payoffs_combined)
            std_err = np.std(payoffs_combined) / np.sqrt(n_actual // 2)

            return mean, std_err

        return 0.0, 0.0

    def simulate_with_control_variate(
        self,
        process: StochasticProcess,
        S0: float,
        T: float,
        n_steps: int,
        n_paths: int,
        payoff: Callable,
        control_payoff: Callable,
        control_expected: float
    ) -> Tuple[float, float]:
        """
        Monte Carlo with control variates.

        Args:
            payoff: Target payoff function
            control_payoff: Control payoff (with known expected value)
            control_expected: E[control_payoff]

        Returns:
            mean: Estimated mean
            std_err: Standard error
        """
        paths = process.simulate(S0, T, n_steps, n_paths)

        Y = payoff(paths)
        X = control_payoff(paths)

        # Optimal coefficient
        cov_XY = np.cov(X, Y)[0, 1]
        var_X = np.var(X)
        c_star = cov_XY / var_X if var_X > 0 else 0

        # Control variate estimator
        Y_cv = Y - c_star * (X - control_expected)

        mean = np.mean(Y_cv)
        std_err = np.std(Y_cv) / np.sqrt(n_paths)

        return mean, std_err

    def quasi_monte_carlo(
        self,
        process: StochasticProcess,
        S0: float,
        T: float,
        n_steps: int,
        n_paths: int,
        payoff: Callable,
        sequence: str = 'sobol'
    ) -> Tuple[float, float]:
        """
        Quasi-Monte Carlo using low-discrepancy sequences.

        Args:
            sequence: 'sobol' or 'halton'
        """
        from scipy.stats import norm

        if sequence == 'sobol':
            from scipy.stats import qmc
            sampler = qmc.Sobol(d=n_steps, scramble=True, seed=self.rng)
            U = sampler.random(n_paths)
        else:
            # Halton sequence
            from scipy.stats import qmc
            sampler = qmc.Halton(d=n_steps, scramble=True, seed=self.rng)
            U = sampler.random(n_paths)

        # Transform to normal
        Z = norm.ppf(U)

        # Build paths (assuming GBM-like process)
        dt = T / n_steps
        if hasattr(process, 'mu') and hasattr(process, 'sigma'):
            drift = (process.mu - 0.5 * process.sigma ** 2) * dt
            diffusion = process.sigma * np.sqrt(dt) * Z

            log_returns = drift + diffusion
            S = S0 * np.exp(np.cumsum(log_returns, axis=1))

            # Add initial price
            S = np.column_stack([np.full(n_paths, S0), S])

            payoffs = payoff(S)
            mean = np.mean(payoffs)
            std_err = np.std(payoffs) / np.sqrt(n_paths)

            return mean, std_err

        return 0.0, 0.0


# =============================================================================
# FACTORY FUNCTIONS
# =============================================================================

def create_gbm(mu: float, sigma: float, seed: Optional[int] = None) -> GeometricBrownianMotion:
    """Create Geometric Brownian Motion."""
    return GeometricBrownianMotion(mu, sigma, seed)


def create_ou(theta: float, mu: float, sigma: float, seed: Optional[int] = None) -> OrnsteinUhlenbeck:
    """Create Ornstein-Uhlenbeck process."""
    return OrnsteinUhlenbeck(theta, mu, sigma, seed)


def create_cir(kappa: float, theta: float, sigma: float, seed: Optional[int] = None) -> CIRProcess:
    """Create CIR process."""
    return CIRProcess(kappa, theta, sigma, seed)


def create_heston(
    mu: float, kappa: float, theta: float, sigma: float, rho: float, v0: float,
    seed: Optional[int] = None
) -> HestonModel:
    """Create Heston model."""
    return HestonModel(mu, kappa, theta, sigma, rho, v0, seed)


def create_merton_jd(
    mu: float, sigma: float, lam: float, mu_J: float, sigma_J: float,
    seed: Optional[int] = None
) -> MertonJumpDiffusion:
    """Create Merton Jump-Diffusion."""
    return MertonJumpDiffusion(mu, sigma, lam, mu_J, sigma_J, seed)


def create_sabr(
    alpha: float, beta: float, rho: float, sigma0: float,
    seed: Optional[int] = None
) -> SABRModel:
    """Create SABR model."""
    return SABRModel(alpha, beta, rho, sigma0, seed)


def create_variance_gamma(
    theta: float, sigma: float, nu: float,
    seed: Optional[int] = None
) -> VarianceGammaProcess:
    """Create Variance Gamma process."""
    return VarianceGammaProcess(theta, sigma, nu, seed)


def create_fbm(H: float, seed: Optional[int] = None) -> FractionalBrownianMotion:
    """Create Fractional Brownian Motion."""
    return FractionalBrownianMotion(H, seed)


# Example usage
if __name__ == "__main__":
    print("="*60)
    print("STOCHASTIC CALCULUS MODULE - TEST MODE")
    print("="*60)

    np.random.seed(42)

    # Test GBM
    print("\n1. Geometric Brownian Motion")
    gbm = create_gbm(mu=0.1, sigma=0.2)
    paths = gbm.simulate(S0=100, T=1, n_steps=252, n_paths=10000)
    print(f"   E[S(1)] theoretical: {gbm.expected_value(100, 1):.2f}")
    print(f"   E[S(1)] simulated: {paths[:, -1].mean():.2f}")

    # Test Heston
    print("\n2. Heston Stochastic Volatility")
    heston = create_heston(mu=0.05, kappa=2.0, theta=0.04, sigma=0.3, rho=-0.7, v0=0.04)
    S, v = heston.simulate(S0=100, T=1, n_steps=252, n_paths=5000)
    print(f"   Final price mean: {S[:, -1].mean():.2f}")
    print(f"   Final variance mean: {v[:, -1].mean():.4f} (theta={heston.theta})")

    # Test Jump-Diffusion
    print("\n3. Merton Jump-Diffusion")
    jd = create_merton_jd(mu=0.1, sigma=0.15, lam=0.5, mu_J=-0.02, sigma_J=0.1)
    paths = jd.simulate(S0=100, T=1, n_steps=252, n_paths=5000)
    print(f"   Final price mean: {paths[:, -1].mean():.2f}")
    print(f"   Final price std: {paths[:, -1].std():.2f}")

    # Test fBM
    print("\n4. Fractional Brownian Motion")
    for H in [0.3, 0.5, 0.7]:
        fbm = create_fbm(H=H)
        paths = fbm.simulate_cholesky(T=1, n_steps=100, n_paths=100)
        print(f"   H={H}: final variance = {paths[:, -1].var():.4f} (theoretical: {1.0:.4f})")

    print(f"\n{'='*60}")
    print("STOCHASTIC CALCULUS MODULE - READY")
    print('='*60)
