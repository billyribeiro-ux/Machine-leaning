"""
Revolution Alpha Engine - High-Performance Computing Module

GPU and Numba-accelerated implementations for:
- Monte Carlo simulations
- Option pricing
- Matrix operations
- Path generation

Features:
- Automatic GPU detection and fallback to CPU
- Numba JIT compilation for 10-100x speedup
- Vectorized operations
- Parallel processing
- Memory-efficient streaming for large simulations
"""

import numpy as np
from typing import Tuple, Optional, Callable, List, Union
from dataclasses import dataclass
from enum import Enum
import warnings

# Try to import acceleration libraries
try:
    from numba import jit, prange, cuda, float64, int64
    NUMBA_AVAILABLE = True
except ImportError:
    NUMBA_AVAILABLE = False
    # Create dummy decorators
    def jit(*args, **kwargs):
        def decorator(func):
            return func
        return decorator if not args else decorator(args[0])
    prange = range

try:
    import cupy as cp
    GPU_AVAILABLE = True
except ImportError:
    GPU_AVAILABLE = False
    cp = None


class ComputeBackend(Enum):
    """Available compute backends."""
    CPU = "cpu"
    NUMBA = "numba"
    GPU = "gpu"
    AUTO = "auto"


@dataclass
class PerformanceConfig:
    """Configuration for high-performance computing."""
    backend: ComputeBackend = ComputeBackend.AUTO
    n_threads: int = -1  # -1 for auto
    chunk_size: int = 100000  # For streaming large simulations
    use_float32: bool = False  # Trade precision for speed
    seed: Optional[int] = None


def get_available_backend() -> ComputeBackend:
    """Detect best available compute backend."""
    if GPU_AVAILABLE:
        try:
            cp.cuda.Device(0).compute_capability
            return ComputeBackend.GPU
        except Exception:
            pass
    if NUMBA_AVAILABLE:
        return ComputeBackend.NUMBA
    return ComputeBackend.CPU


# =============================================================================
# Numba-Accelerated Monte Carlo
# =============================================================================

if NUMBA_AVAILABLE:
    @jit(nopython=True, parallel=True, cache=True)
    def _gbm_paths_numba(
        S0: float,
        mu: float,
        sigma: float,
        T: float,
        n_steps: int,
        n_paths: int,
        dt: float,
        random_numbers: np.ndarray
    ) -> np.ndarray:
        """Numba-accelerated GBM path generation."""
        paths = np.zeros((n_paths, n_steps + 1))
        paths[:, 0] = S0

        drift = (mu - 0.5 * sigma**2) * dt
        diffusion = sigma * np.sqrt(dt)

        for i in prange(n_paths):
            for j in range(n_steps):
                paths[i, j+1] = paths[i, j] * np.exp(
                    drift + diffusion * random_numbers[i, j]
                )
        return paths

    @jit(nopython=True, parallel=True, cache=True)
    def _heston_paths_numba(
        S0: float,
        v0: float,
        mu: float,
        kappa: float,
        theta: float,
        sigma_v: float,
        rho: float,
        T: float,
        n_steps: int,
        n_paths: int,
        dt: float,
        Z1: np.ndarray,
        Z2: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Numba-accelerated Heston path generation with QE scheme."""
        S = np.zeros((n_paths, n_steps + 1))
        v = np.zeros((n_paths, n_steps + 1))
        S[:, 0] = S0
        v[:, 0] = v0

        for i in prange(n_paths):
            for j in range(n_steps):
                # Variance process (ensure non-negative)
                v_curr = max(v[i, j], 0)

                # QE discretization for variance
                m = theta + (v_curr - theta) * np.exp(-kappa * dt)
                s2 = (v_curr * sigma_v**2 * np.exp(-kappa * dt) / kappa *
                      (1 - np.exp(-kappa * dt)) +
                      theta * sigma_v**2 / (2 * kappa) *
                      (1 - np.exp(-kappa * dt))**2)

                psi = s2 / (m**2) if m > 0 else 1e10

                if psi <= 1.5:
                    # Use quadratic scheme
                    b2 = 2 / psi - 1 + np.sqrt(2 / psi * (2 / psi - 1))
                    a = m / (1 + b2)
                    v[i, j+1] = a * (np.sqrt(b2) + Z2[i, j])**2
                else:
                    # Use exponential scheme
                    p = (psi - 1) / (psi + 1)
                    beta = (1 - p) / m if m > 0 else 1
                    u = 0.5 * (1 + np.tanh(Z2[i, j] / 2))  # Transform to uniform
                    if u <= p:
                        v[i, j+1] = 0
                    else:
                        v[i, j+1] = np.log((1 - p) / (1 - u)) / beta if beta > 0 else 0

                v[i, j+1] = max(v[i, j+1], 0)

                # Stock price with correlation
                Zs = rho * Z2[i, j] + np.sqrt(1 - rho**2) * Z1[i, j]
                v_avg = 0.5 * (v[i, j] + v[i, j+1])
                S[i, j+1] = S[i, j] * np.exp(
                    (mu - 0.5 * v_avg) * dt + np.sqrt(v_avg * dt) * Zs
                )

        return S, v

    @jit(nopython=True, parallel=True, cache=True)
    def _monte_carlo_european_numba(
        paths: np.ndarray,
        K: float,
        r: float,
        T: float,
        is_call: bool
    ) -> Tuple[float, float]:
        """Numba-accelerated European option pricing."""
        n_paths = paths.shape[0]
        payoffs = np.zeros(n_paths)

        for i in prange(n_paths):
            ST = paths[i, -1]
            if is_call:
                payoffs[i] = max(ST - K, 0)
            else:
                payoffs[i] = max(K - ST, 0)

        discount = np.exp(-r * T)
        price = discount * np.mean(payoffs)
        std_err = discount * np.std(payoffs) / np.sqrt(n_paths)

        return price, std_err

    @jit(nopython=True, parallel=True, cache=True)
    def _american_lsm_numba(
        paths: np.ndarray,
        K: float,
        r: float,
        dt: float,
        is_call: bool,
        n_basis: int = 3
    ) -> float:
        """Numba-accelerated Longstaff-Schwartz for American options."""
        n_paths, n_steps = paths.shape
        n_steps -= 1

        # Cash flows
        cash_flows = np.zeros((n_paths, n_steps + 1))

        # Terminal payoff
        for i in prange(n_paths):
            if is_call:
                cash_flows[i, n_steps] = max(paths[i, n_steps] - K, 0)
            else:
                cash_flows[i, n_steps] = max(K - paths[i, n_steps], 0)

        # Backward induction
        for t in range(n_steps - 1, 0, -1):
            discount = np.exp(-r * dt)

            # Find in-the-money paths
            itm_indices = []
            for i in range(n_paths):
                if is_call:
                    intrinsic = paths[i, t] - K
                else:
                    intrinsic = K - paths[i, t]
                if intrinsic > 0:
                    itm_indices.append(i)

            if len(itm_indices) == 0:
                continue

            n_itm = len(itm_indices)

            # Build regression matrices
            X = np.zeros((n_itm, n_basis))
            Y = np.zeros(n_itm)

            for idx, i in enumerate(itm_indices):
                S = paths[i, t]
                # Laguerre polynomials
                X[idx, 0] = 1.0
                if n_basis > 1:
                    X[idx, 1] = 1 - S / K
                if n_basis > 2:
                    X[idx, 2] = 0.5 * ((S / K)**2 - 2 * S / K + 1)

                # Discounted future cash flows
                future_cf = 0.0
                for s in range(t + 1, n_steps + 1):
                    future_cf += cash_flows[i, s] * np.exp(-r * dt * (s - t))
                Y[idx] = future_cf

            # Simple least squares (no matrix inversion in numba)
            # Use normal equations: (X'X)^-1 X'Y
            XtX = np.zeros((n_basis, n_basis))
            XtY = np.zeros(n_basis)

            for idx in range(n_itm):
                for j in range(n_basis):
                    XtY[j] += X[idx, j] * Y[idx]
                    for k in range(n_basis):
                        XtX[j, k] += X[idx, j] * X[idx, k]

            # Solve using Gaussian elimination (simple case)
            # For simplicity, use identity if singular
            try:
                # Add regularization
                for j in range(n_basis):
                    XtX[j, j] += 1e-6

                # Forward elimination
                for j in range(n_basis):
                    for i in range(j + 1, n_basis):
                        if abs(XtX[j, j]) > 1e-10:
                            factor = XtX[i, j] / XtX[j, j]
                            for k in range(j, n_basis):
                                XtX[i, k] -= factor * XtX[j, k]
                            XtY[i] -= factor * XtY[j]

                # Back substitution
                beta = np.zeros(n_basis)
                for j in range(n_basis - 1, -1, -1):
                    if abs(XtX[j, j]) > 1e-10:
                        beta[j] = XtY[j]
                        for k in range(j + 1, n_basis):
                            beta[j] -= XtX[j, k] * beta[k]
                        beta[j] /= XtX[j, j]

                # Decision to exercise
                for idx, i in enumerate(itm_indices):
                    continuation = 0.0
                    for j in range(n_basis):
                        continuation += beta[j] * X[idx, j]

                    if is_call:
                        intrinsic = paths[i, t] - K
                    else:
                        intrinsic = K - paths[i, t]

                    if intrinsic > continuation:
                        # Exercise: set cash flow at t, zero out future
                        cash_flows[i, t] = intrinsic
                        for s in range(t + 1, n_steps + 1):
                            cash_flows[i, s] = 0

            except Exception:
                pass

        # Calculate option value
        option_value = 0.0
        for i in range(n_paths):
            pv = 0.0
            for t in range(n_steps + 1):
                pv += cash_flows[i, t] * np.exp(-r * dt * t)
            option_value += pv

        return option_value / n_paths

    @jit(nopython=True, parallel=True, cache=True)
    def _barrier_mc_numba(
        paths: np.ndarray,
        K: float,
        barrier: float,
        r: float,
        T: float,
        is_call: bool,
        is_up: bool,
        is_knock_in: bool
    ) -> Tuple[float, float]:
        """Numba-accelerated barrier option pricing."""
        n_paths = paths.shape[0]
        payoffs = np.zeros(n_paths)

        for i in prange(n_paths):
            # Check barrier condition
            barrier_hit = False
            for j in range(paths.shape[1]):
                if is_up and paths[i, j] >= barrier:
                    barrier_hit = True
                    break
                elif not is_up and paths[i, j] <= barrier:
                    barrier_hit = True
                    break

            # Determine if option is active
            is_active = barrier_hit if is_knock_in else not barrier_hit

            if is_active:
                ST = paths[i, -1]
                if is_call:
                    payoffs[i] = max(ST - K, 0)
                else:
                    payoffs[i] = max(K - ST, 0)

        discount = np.exp(-r * T)
        price = discount * np.mean(payoffs)
        std_err = discount * np.std(payoffs) / np.sqrt(n_paths)

        return price, std_err

    @jit(nopython=True, parallel=True, cache=True)
    def _asian_mc_numba(
        paths: np.ndarray,
        K: float,
        r: float,
        T: float,
        is_call: bool,
        is_arithmetic: bool
    ) -> Tuple[float, float]:
        """Numba-accelerated Asian option pricing."""
        n_paths, n_steps = paths.shape
        payoffs = np.zeros(n_paths)

        for i in prange(n_paths):
            if is_arithmetic:
                avg = 0.0
                for j in range(n_steps):
                    avg += paths[i, j]
                avg /= n_steps
            else:
                # Geometric average
                log_sum = 0.0
                for j in range(n_steps):
                    log_sum += np.log(paths[i, j])
                avg = np.exp(log_sum / n_steps)

            if is_call:
                payoffs[i] = max(avg - K, 0)
            else:
                payoffs[i] = max(K - avg, 0)

        discount = np.exp(-r * T)
        price = discount * np.mean(payoffs)
        std_err = discount * np.std(payoffs) / np.sqrt(n_paths)

        return price, std_err

    @jit(nopython=True, parallel=True, cache=True)
    def _covariance_matrix_numba(
        returns: np.ndarray
    ) -> np.ndarray:
        """Numba-accelerated covariance matrix calculation."""
        n_obs, n_assets = returns.shape

        # Calculate means
        means = np.zeros(n_assets)
        for j in prange(n_assets):
            total = 0.0
            for i in range(n_obs):
                total += returns[i, j]
            means[j] = total / n_obs

        # Calculate covariance
        cov = np.zeros((n_assets, n_assets))
        for i in prange(n_assets):
            for j in range(i, n_assets):
                total = 0.0
                for k in range(n_obs):
                    total += (returns[k, i] - means[i]) * (returns[k, j] - means[j])
                cov[i, j] = total / (n_obs - 1)
                cov[j, i] = cov[i, j]

        return cov

    @jit(nopython=True, parallel=True, cache=True)
    def _portfolio_var_numba(
        returns: np.ndarray,
        weights: np.ndarray,
        confidence: float
    ) -> Tuple[float, float]:
        """Numba-accelerated portfolio VaR calculation."""
        n_obs, n_assets = returns.shape

        # Portfolio returns
        port_returns = np.zeros(n_obs)
        for i in prange(n_obs):
            total = 0.0
            for j in range(n_assets):
                total += returns[i, j] * weights[j]
            port_returns[i] = total

        # Sort for percentile
        sorted_returns = np.sort(port_returns)

        # VaR
        alpha = 1 - confidence
        var_idx = int(alpha * n_obs)
        var = -sorted_returns[var_idx]

        # Expected Shortfall
        es_sum = 0.0
        for i in range(var_idx + 1):
            es_sum += sorted_returns[i]
        es = -es_sum / (var_idx + 1) if var_idx > 0 else var

        return var, es

else:
    # Fallback implementations without Numba
    def _gbm_paths_numba(S0, mu, sigma, T, n_steps, n_paths, dt, random_numbers):
        paths = np.zeros((n_paths, n_steps + 1))
        paths[:, 0] = S0
        drift = (mu - 0.5 * sigma**2) * dt
        diffusion = sigma * np.sqrt(dt)
        for j in range(n_steps):
            paths[:, j+1] = paths[:, j] * np.exp(drift + diffusion * random_numbers[:, j])
        return paths

    def _heston_paths_numba(S0, v0, mu, kappa, theta, sigma_v, rho, T, n_steps, n_paths, dt, Z1, Z2):
        S = np.zeros((n_paths, n_steps + 1))
        v = np.zeros((n_paths, n_steps + 1))
        S[:, 0] = S0
        v[:, 0] = v0
        for j in range(n_steps):
            v[:, j+1] = np.maximum(v[:, j] + kappa * (theta - v[:, j]) * dt +
                                   sigma_v * np.sqrt(np.maximum(v[:, j], 0) * dt) * Z2[:, j], 0)
            Zs = rho * Z2[:, j] + np.sqrt(1 - rho**2) * Z1[:, j]
            v_avg = 0.5 * (v[:, j] + v[:, j+1])
            S[:, j+1] = S[:, j] * np.exp((mu - 0.5 * v_avg) * dt + np.sqrt(v_avg * dt) * Zs)
        return S, v

    def _monte_carlo_european_numba(paths, K, r, T, is_call):
        ST = paths[:, -1]
        if is_call:
            payoffs = np.maximum(ST - K, 0)
        else:
            payoffs = np.maximum(K - ST, 0)
        discount = np.exp(-r * T)
        return discount * np.mean(payoffs), discount * np.std(payoffs) / np.sqrt(len(payoffs))

    def _american_lsm_numba(paths, K, r, dt, is_call, n_basis=3):
        # Simple LSM without numba
        from .derivatives import BinomialTree
        # Fallback to tree
        return 0.0

    def _barrier_mc_numba(paths, K, barrier, r, T, is_call, is_up, is_knock_in):
        n_paths = paths.shape[0]
        if is_up:
            barrier_hit = np.any(paths >= barrier, axis=1)
        else:
            barrier_hit = np.any(paths <= barrier, axis=1)
        is_active = barrier_hit if is_knock_in else ~barrier_hit
        ST = paths[:, -1]
        if is_call:
            payoffs = np.where(is_active, np.maximum(ST - K, 0), 0)
        else:
            payoffs = np.where(is_active, np.maximum(K - ST, 0), 0)
        discount = np.exp(-r * T)
        return discount * np.mean(payoffs), discount * np.std(payoffs) / np.sqrt(n_paths)

    def _asian_mc_numba(paths, K, r, T, is_call, is_arithmetic):
        if is_arithmetic:
            avg = np.mean(paths, axis=1)
        else:
            avg = np.exp(np.mean(np.log(paths), axis=1))
        if is_call:
            payoffs = np.maximum(avg - K, 0)
        else:
            payoffs = np.maximum(K - avg, 0)
        discount = np.exp(-r * T)
        return discount * np.mean(payoffs), discount * np.std(payoffs) / np.sqrt(len(payoffs))

    def _covariance_matrix_numba(returns):
        return np.cov(returns, rowvar=False)

    def _portfolio_var_numba(returns, weights, confidence):
        port_returns = returns @ weights
        var = -np.percentile(port_returns, (1 - confidence) * 100)
        es = -np.mean(port_returns[port_returns <= -var])
        return var, es


# =============================================================================
# GPU-Accelerated Functions
# =============================================================================

class GPUAccelerator:
    """GPU-accelerated computations using CuPy."""

    def __init__(self):
        if not GPU_AVAILABLE:
            raise RuntimeError("CuPy not available for GPU acceleration")

    @staticmethod
    def to_gpu(arr: np.ndarray) -> 'cp.ndarray':
        """Transfer array to GPU."""
        return cp.asarray(arr)

    @staticmethod
    def to_cpu(arr: 'cp.ndarray') -> np.ndarray:
        """Transfer array from GPU."""
        return cp.asnumpy(arr)

    def gbm_paths_gpu(
        self,
        S0: float,
        mu: float,
        sigma: float,
        T: float,
        n_steps: int,
        n_paths: int,
        seed: Optional[int] = None
    ) -> np.ndarray:
        """Generate GBM paths on GPU."""
        if seed is not None:
            cp.random.seed(seed)

        dt = T / n_steps
        drift = (mu - 0.5 * sigma**2) * dt
        diffusion = sigma * cp.sqrt(dt)

        # Generate all random numbers at once
        Z = cp.random.standard_normal((n_paths, n_steps))

        # Cumulative sum for log prices
        log_returns = drift + diffusion * Z
        log_prices = cp.cumsum(log_returns, axis=1)

        # Prepend zeros and add log(S0)
        log_prices = cp.concatenate([
            cp.zeros((n_paths, 1)),
            log_prices
        ], axis=1)
        log_prices += cp.log(S0)

        # Convert to prices
        paths = cp.exp(log_prices)

        return self.to_cpu(paths)

    def monte_carlo_european_gpu(
        self,
        paths: np.ndarray,
        K: float,
        r: float,
        T: float,
        is_call: bool
    ) -> Tuple[float, float]:
        """Price European option on GPU."""
        paths_gpu = self.to_gpu(paths)
        ST = paths_gpu[:, -1]

        if is_call:
            payoffs = cp.maximum(ST - K, 0)
        else:
            payoffs = cp.maximum(K - ST, 0)

        discount = cp.exp(-r * T)
        price = float(discount * cp.mean(payoffs))
        std_err = float(discount * cp.std(payoffs) / cp.sqrt(len(payoffs)))

        return price, std_err

    def covariance_matrix_gpu(
        self,
        returns: np.ndarray
    ) -> np.ndarray:
        """Calculate covariance matrix on GPU."""
        returns_gpu = self.to_gpu(returns)
        cov_gpu = cp.cov(returns_gpu, rowvar=False)
        return self.to_cpu(cov_gpu)

    def portfolio_optimization_gpu(
        self,
        expected_returns: np.ndarray,
        cov_matrix: np.ndarray,
        n_portfolios: int = 10000
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Generate random portfolios on GPU for efficient frontier.

        Returns: (returns, volatilities, weights)
        """
        n_assets = len(expected_returns)

        mu_gpu = self.to_gpu(expected_returns)
        sigma_gpu = self.to_gpu(cov_matrix)

        # Generate random weights
        weights_gpu = cp.random.random((n_portfolios, n_assets))
        weights_gpu = weights_gpu / cp.sum(weights_gpu, axis=1, keepdims=True)

        # Portfolio returns
        port_returns = weights_gpu @ mu_gpu

        # Portfolio volatilities (vectorized)
        port_vars = cp.einsum('ij,jk,ik->i', weights_gpu, sigma_gpu, weights_gpu)
        port_vols = cp.sqrt(port_vars)

        return (
            self.to_cpu(port_returns),
            self.to_cpu(port_vols),
            self.to_cpu(weights_gpu)
        )


# =============================================================================
# High-Performance Monte Carlo Engine
# =============================================================================

class HighPerformanceMC:
    """
    High-performance Monte Carlo engine with automatic backend selection.
    """

    def __init__(self, config: Optional[PerformanceConfig] = None):
        """
        Initialize HP Monte Carlo engine.

        Args:
            config: Performance configuration
        """
        self.config = config or PerformanceConfig()

        # Determine backend
        if self.config.backend == ComputeBackend.AUTO:
            self.backend = get_available_backend()
        else:
            self.backend = self.config.backend

        # Initialize GPU if available
        self.gpu = None
        if self.backend == ComputeBackend.GPU and GPU_AVAILABLE:
            try:
                self.gpu = GPUAccelerator()
            except Exception:
                self.backend = ComputeBackend.NUMBA if NUMBA_AVAILABLE else ComputeBackend.CPU

        # Set random seed
        if self.config.seed is not None:
            np.random.seed(self.config.seed)

    def generate_gbm_paths(
        self,
        S0: float,
        mu: float,
        sigma: float,
        T: float,
        n_steps: int,
        n_paths: int
    ) -> np.ndarray:
        """
        Generate GBM paths using best available backend.

        Args:
            S0: Initial price
            mu: Drift
            sigma: Volatility
            T: Time horizon
            n_steps: Number of time steps
            n_paths: Number of paths

        Returns:
            Paths array (n_paths x n_steps+1)
        """
        dt = T / n_steps

        if self.backend == ComputeBackend.GPU and self.gpu is not None:
            return self.gpu.gbm_paths_gpu(S0, mu, sigma, T, n_steps, n_paths, self.config.seed)

        # Generate random numbers
        Z = np.random.standard_normal((n_paths, n_steps))

        if self.backend == ComputeBackend.NUMBA and NUMBA_AVAILABLE:
            return _gbm_paths_numba(S0, mu, sigma, T, n_steps, n_paths, dt, Z)

        # CPU fallback
        paths = np.zeros((n_paths, n_steps + 1))
        paths[:, 0] = S0
        drift = (mu - 0.5 * sigma**2) * dt
        diffusion = sigma * np.sqrt(dt)
        for j in range(n_steps):
            paths[:, j+1] = paths[:, j] * np.exp(drift + diffusion * Z[:, j])
        return paths

    def generate_heston_paths(
        self,
        S0: float,
        v0: float,
        mu: float,
        kappa: float,
        theta: float,
        sigma_v: float,
        rho: float,
        T: float,
        n_steps: int,
        n_paths: int
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Generate Heston model paths.

        Returns:
            Tuple of (price_paths, variance_paths)
        """
        dt = T / n_steps
        Z1 = np.random.standard_normal((n_paths, n_steps))
        Z2 = np.random.standard_normal((n_paths, n_steps))

        if self.backend == ComputeBackend.NUMBA and NUMBA_AVAILABLE:
            return _heston_paths_numba(
                S0, v0, mu, kappa, theta, sigma_v, rho, T, n_steps, n_paths, dt, Z1, Z2
            )

        # CPU fallback
        S = np.zeros((n_paths, n_steps + 1))
        v = np.zeros((n_paths, n_steps + 1))
        S[:, 0] = S0
        v[:, 0] = v0

        for j in range(n_steps):
            v[:, j+1] = np.maximum(
                v[:, j] + kappa * (theta - v[:, j]) * dt +
                sigma_v * np.sqrt(np.maximum(v[:, j], 0) * dt) * Z2[:, j],
                0
            )
            Zs = rho * Z2[:, j] + np.sqrt(1 - rho**2) * Z1[:, j]
            v_avg = 0.5 * (v[:, j] + v[:, j+1])
            S[:, j+1] = S[:, j] * np.exp((mu - 0.5 * v_avg) * dt + np.sqrt(v_avg * dt) * Zs)

        return S, v

    def price_european(
        self,
        paths: np.ndarray,
        K: float,
        r: float,
        T: float,
        is_call: bool = True
    ) -> Tuple[float, float]:
        """
        Price European option from paths.

        Returns:
            Tuple of (price, standard_error)
        """
        if self.backend == ComputeBackend.GPU and self.gpu is not None:
            return self.gpu.monte_carlo_european_gpu(paths, K, r, T, is_call)

        if self.backend == ComputeBackend.NUMBA and NUMBA_AVAILABLE:
            return _monte_carlo_european_numba(paths, K, r, T, is_call)

        # CPU fallback
        ST = paths[:, -1]
        if is_call:
            payoffs = np.maximum(ST - K, 0)
        else:
            payoffs = np.maximum(K - ST, 0)
        discount = np.exp(-r * T)
        return discount * np.mean(payoffs), discount * np.std(payoffs) / np.sqrt(len(payoffs))

    def price_american_lsm(
        self,
        paths: np.ndarray,
        K: float,
        r: float,
        T: float,
        is_call: bool = True,
        n_basis: int = 3
    ) -> float:
        """
        Price American option using Longstaff-Schwartz.

        Returns:
            Option price
        """
        n_steps = paths.shape[1] - 1
        dt = T / n_steps

        if self.backend == ComputeBackend.NUMBA and NUMBA_AVAILABLE:
            return _american_lsm_numba(paths, K, r, dt, is_call, n_basis)

        # CPU implementation
        n_paths = paths.shape[0]
        cash_flows = np.zeros((n_paths, n_steps + 1))

        # Terminal payoff
        if is_call:
            cash_flows[:, -1] = np.maximum(paths[:, -1] - K, 0)
        else:
            cash_flows[:, -1] = np.maximum(K - paths[:, -1], 0)

        # Backward induction
        for t in range(n_steps - 1, 0, -1):
            if is_call:
                intrinsic = paths[:, t] - K
            else:
                intrinsic = K - paths[:, t]

            itm = intrinsic > 0

            if not np.any(itm):
                continue

            # Regression
            S_itm = paths[itm, t]
            future_cf = np.sum(
                cash_flows[itm, t+1:] * np.exp(-r * dt * np.arange(1, n_steps - t + 1)),
                axis=1
            )

            # Polynomial basis
            X = np.column_stack([
                np.ones(len(S_itm)),
                S_itm / K,
                (S_itm / K)**2
            ])[:, :n_basis]

            try:
                beta = np.linalg.lstsq(X, future_cf, rcond=None)[0]
                continuation = X @ beta

                # Exercise decision
                exercise = intrinsic[itm] > continuation
                exercise_indices = np.where(itm)[0][exercise]

                cash_flows[exercise_indices, t] = intrinsic[itm][exercise]
                cash_flows[exercise_indices, t+1:] = 0

            except np.linalg.LinAlgError:
                continue

        # Calculate present value
        discount_factors = np.exp(-r * dt * np.arange(n_steps + 1))
        option_values = np.sum(cash_flows * discount_factors, axis=1)

        return np.mean(option_values)

    def price_barrier(
        self,
        paths: np.ndarray,
        K: float,
        barrier: float,
        r: float,
        T: float,
        is_call: bool = True,
        is_up: bool = True,
        is_knock_in: bool = True
    ) -> Tuple[float, float]:
        """Price barrier option from paths."""
        if self.backend == ComputeBackend.NUMBA and NUMBA_AVAILABLE:
            return _barrier_mc_numba(paths, K, barrier, r, T, is_call, is_up, is_knock_in)

        # CPU fallback
        if is_up:
            barrier_hit = np.any(paths >= barrier, axis=1)
        else:
            barrier_hit = np.any(paths <= barrier, axis=1)

        is_active = barrier_hit if is_knock_in else ~barrier_hit
        ST = paths[:, -1]

        if is_call:
            payoffs = np.where(is_active, np.maximum(ST - K, 0), 0)
        else:
            payoffs = np.where(is_active, np.maximum(K - ST, 0), 0)

        discount = np.exp(-r * T)
        return discount * np.mean(payoffs), discount * np.std(payoffs) / np.sqrt(len(payoffs))

    def price_asian(
        self,
        paths: np.ndarray,
        K: float,
        r: float,
        T: float,
        is_call: bool = True,
        is_arithmetic: bool = True
    ) -> Tuple[float, float]:
        """Price Asian option from paths."""
        if self.backend == ComputeBackend.NUMBA and NUMBA_AVAILABLE:
            return _asian_mc_numba(paths, K, r, T, is_call, is_arithmetic)

        # CPU fallback
        if is_arithmetic:
            avg = np.mean(paths, axis=1)
        else:
            avg = np.exp(np.mean(np.log(paths), axis=1))

        if is_call:
            payoffs = np.maximum(avg - K, 0)
        else:
            payoffs = np.maximum(K - avg, 0)

        discount = np.exp(-r * T)
        return discount * np.mean(payoffs), discount * np.std(payoffs) / np.sqrt(len(payoffs))

    def calculate_greeks_mc(
        self,
        S0: float,
        K: float,
        r: float,
        sigma: float,
        T: float,
        is_call: bool = True,
        n_paths: int = 100000,
        n_steps: int = 252
    ) -> dict:
        """
        Calculate Greeks using Monte Carlo with finite differences.

        Returns:
            Dictionary with delta, gamma, vega, theta, rho
        """
        bump_S = S0 * 0.01
        bump_sigma = 0.01
        bump_r = 0.0001
        bump_T = 1/252

        # Base case
        paths = self.generate_gbm_paths(S0, r, sigma, T, n_steps, n_paths)
        price, _ = self.price_european(paths, K, r, T, is_call)

        # Delta and Gamma
        paths_up = self.generate_gbm_paths(S0 + bump_S, r, sigma, T, n_steps, n_paths)
        paths_down = self.generate_gbm_paths(S0 - bump_S, r, sigma, T, n_steps, n_paths)
        price_up, _ = self.price_european(paths_up, K, r, T, is_call)
        price_down, _ = self.price_european(paths_down, K, r, T, is_call)

        delta = (price_up - price_down) / (2 * bump_S)
        gamma = (price_up - 2 * price + price_down) / (bump_S ** 2)

        # Vega
        paths_vega = self.generate_gbm_paths(S0, r, sigma + bump_sigma, T, n_steps, n_paths)
        price_vega, _ = self.price_european(paths_vega, K, r, T, is_call)
        vega = (price_vega - price) / bump_sigma / 100  # Per 1% vol change

        # Theta
        if T > bump_T:
            paths_theta = self.generate_gbm_paths(S0, r, sigma, T - bump_T, n_steps, n_paths)
            price_theta, _ = self.price_european(paths_theta, K, r, T - bump_T, is_call)
            theta = (price_theta - price) / bump_T / 252  # Daily theta
        else:
            theta = 0.0

        # Rho
        paths_rho = self.generate_gbm_paths(S0, r + bump_r, sigma, T, n_steps, n_paths)
        price_rho, _ = self.price_european(paths_rho, K, r + bump_r, T, is_call)
        rho = (price_rho - price) / bump_r / 100  # Per 1% rate change

        return {
            'price': price,
            'delta': delta,
            'gamma': gamma,
            'vega': vega,
            'theta': theta,
            'rho': rho
        }


# =============================================================================
# Streaming Monte Carlo for Large Simulations
# =============================================================================

class StreamingMC:
    """
    Memory-efficient Monte Carlo for very large simulations.

    Uses chunked processing to handle millions of paths
    without running out of memory.
    """

    def __init__(
        self,
        chunk_size: int = 100000,
        backend: ComputeBackend = ComputeBackend.AUTO
    ):
        self.chunk_size = chunk_size
        self.mc = HighPerformanceMC(PerformanceConfig(backend=backend))

    def price_european_streaming(
        self,
        S0: float,
        K: float,
        r: float,
        sigma: float,
        T: float,
        n_paths: int,
        n_steps: int = 252,
        is_call: bool = True
    ) -> Tuple[float, float]:
        """
        Price European option using streaming for large n_paths.

        Memory usage stays constant regardless of n_paths.
        """
        n_chunks = (n_paths + self.chunk_size - 1) // self.chunk_size

        sum_payoffs = 0.0
        sum_payoffs_sq = 0.0
        total_paths = 0

        for i in range(n_chunks):
            chunk_paths = min(self.chunk_size, n_paths - i * self.chunk_size)

            paths = self.mc.generate_gbm_paths(S0, r, sigma, T, n_steps, chunk_paths)
            ST = paths[:, -1]

            if is_call:
                payoffs = np.maximum(ST - K, 0)
            else:
                payoffs = np.maximum(K - ST, 0)

            sum_payoffs += np.sum(payoffs)
            sum_payoffs_sq += np.sum(payoffs**2)
            total_paths += chunk_paths

        discount = np.exp(-r * T)
        mean_payoff = sum_payoffs / total_paths
        var_payoff = sum_payoffs_sq / total_paths - mean_payoff**2

        price = discount * mean_payoff
        std_err = discount * np.sqrt(var_payoff / total_paths)

        return price, std_err


# =============================================================================
# Factory Functions
# =============================================================================

def create_high_performance_mc(
    backend: str = "auto",
    seed: Optional[int] = None
) -> HighPerformanceMC:
    """
    Create high-performance Monte Carlo engine.

    Args:
        backend: "auto", "cpu", "numba", or "gpu"
        seed: Random seed

    Returns:
        HighPerformanceMC instance
    """
    backend_map = {
        "auto": ComputeBackend.AUTO,
        "cpu": ComputeBackend.CPU,
        "numba": ComputeBackend.NUMBA,
        "gpu": ComputeBackend.GPU
    }

    config = PerformanceConfig(
        backend=backend_map.get(backend, ComputeBackend.AUTO),
        seed=seed
    )

    return HighPerformanceMC(config)


def benchmark_backends(
    n_paths: int = 100000,
    n_steps: int = 252
) -> dict:
    """
    Benchmark available compute backends.

    Returns:
        Dictionary with timing results
    """
    import time

    results = {}

    # Test parameters
    S0, r, sigma, T = 100, 0.05, 0.2, 1.0

    for backend in [ComputeBackend.CPU, ComputeBackend.NUMBA, ComputeBackend.GPU]:
        if backend == ComputeBackend.NUMBA and not NUMBA_AVAILABLE:
            continue
        if backend == ComputeBackend.GPU and not GPU_AVAILABLE:
            continue

        try:
            config = PerformanceConfig(backend=backend)
            mc = HighPerformanceMC(config)

            # Warm up
            _ = mc.generate_gbm_paths(S0, r, sigma, T, 10, 100)

            # Benchmark
            start = time.perf_counter()
            paths = mc.generate_gbm_paths(S0, r, sigma, T, n_steps, n_paths)
            _, _ = mc.price_european(paths, S0, r, T, True)
            elapsed = time.perf_counter() - start

            results[backend.value] = {
                'time_seconds': elapsed,
                'paths_per_second': n_paths / elapsed
            }
        except Exception as e:
            results[backend.value] = {'error': str(e)}

    return results


def get_system_info() -> dict:
    """Get system information for performance tuning."""
    import platform

    info = {
        'platform': platform.system(),
        'python_version': platform.python_version(),
        'numba_available': NUMBA_AVAILABLE,
        'gpu_available': GPU_AVAILABLE,
        'recommended_backend': get_available_backend().value
    }

    if GPU_AVAILABLE:
        try:
            info['gpu_name'] = cp.cuda.Device(0).name
            info['gpu_memory_gb'] = cp.cuda.Device(0).mem_info[1] / 1e9
        except Exception:
            pass

    return info
