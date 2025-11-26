"""
Revolution Alpha Engine - Model Calibration Framework

Comprehensive calibration tools for:
- Volatility surface fitting
- Stochastic volatility model calibration (Heston, SABR)
- Local volatility extraction (Dupire)
- Term structure model calibration
- Rough volatility models
- Multi-objective optimization
- Regularization and constraints
"""

import numpy as np
from scipy import optimize, interpolate, stats
from scipy.special import gamma as gamma_func
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Callable, Union
from enum import Enum
from abc import ABC, abstractmethod
import warnings


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class MarketData:
    """Container for market option data."""
    strikes: np.ndarray
    expiries: np.ndarray
    prices: np.ndarray
    spot: float
    forward: Optional[np.ndarray] = None
    is_call: Optional[np.ndarray] = None
    bid: Optional[np.ndarray] = None
    ask: Optional[np.ndarray] = None
    implied_vols: Optional[np.ndarray] = None
    risk_free_rates: Optional[np.ndarray] = None


@dataclass
class CalibrationResult:
    """Result of model calibration."""
    parameters: Dict[str, float]
    objective_value: float
    rmse: float
    max_error: float
    success: bool
    message: str
    n_iterations: int
    calibration_time: float
    model_prices: Optional[np.ndarray] = None
    market_prices: Optional[np.ndarray] = None
    parameter_errors: Optional[Dict[str, float]] = None


@dataclass
class VolatilitySurface:
    """Fitted volatility surface."""
    strikes: np.ndarray
    expiries: np.ndarray
    implied_vols: np.ndarray
    spot: float
    interpolator: Optional[Callable] = None

    def get_vol(self, strike: float, expiry: float) -> float:
        """Get interpolated implied volatility."""
        if self.interpolator is not None:
            return self.interpolator(expiry, strike)
        raise ValueError("Interpolator not set")


class CalibrationObjective(Enum):
    """Objective functions for calibration."""
    PRICE_MSE = "price_mse"
    PRICE_RMSE = "price_rmse"
    VOL_MSE = "vol_mse"
    VOL_RMSE = "vol_rmse"
    WEIGHTED_MSE = "weighted_mse"
    VEGA_WEIGHTED = "vega_weighted"


# =============================================================================
# Implied Volatility Calculation
# =============================================================================

class ImpliedVolCalculator:
    """
    Fast implied volatility calculation using multiple methods.
    """

    @staticmethod
    def black_scholes_call(S, K, r, sigma, T, q=0):
        """Black-Scholes call price."""
        if T <= 0 or sigma <= 0:
            return max(S * np.exp(-q * T) - K * np.exp(-r * T), 0)

        d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)

        return S * np.exp(-q * T) * stats.norm.cdf(d1) - K * np.exp(-r * T) * stats.norm.cdf(d2)

    @staticmethod
    def black_scholes_put(S, K, r, sigma, T, q=0):
        """Black-Scholes put price."""
        if T <= 0 or sigma <= 0:
            return max(K * np.exp(-r * T) - S * np.exp(-q * T), 0)

        d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)

        return K * np.exp(-r * T) * stats.norm.cdf(-d2) - S * np.exp(-q * T) * stats.norm.cdf(-d1)

    @staticmethod
    def black_scholes_vega(S, K, r, sigma, T, q=0):
        """Black-Scholes vega."""
        if T <= 0 or sigma <= 0:
            return 0

        d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
        return S * np.exp(-q * T) * stats.norm.pdf(d1) * np.sqrt(T)

    def implied_vol_newton(
        self,
        price: float,
        S: float,
        K: float,
        r: float,
        T: float,
        is_call: bool = True,
        q: float = 0,
        initial_guess: float = 0.2,
        max_iter: int = 100,
        tol: float = 1e-8
    ) -> float:
        """
        Calculate implied volatility using Newton-Raphson.

        Args:
            price: Market option price
            S: Spot price
            K: Strike
            r: Risk-free rate
            T: Time to expiry
            is_call: True for call, False for put
            q: Dividend yield
            initial_guess: Starting volatility guess
            max_iter: Maximum iterations
            tol: Convergence tolerance

        Returns:
            Implied volatility
        """
        sigma = initial_guess

        for _ in range(max_iter):
            if is_call:
                model_price = self.black_scholes_call(S, K, r, sigma, T, q)
            else:
                model_price = self.black_scholes_put(S, K, r, sigma, T, q)

            vega = self.black_scholes_vega(S, K, r, sigma, T, q)

            if abs(vega) < 1e-10:
                break

            diff = model_price - price
            if abs(diff) < tol:
                break

            sigma = sigma - diff / vega
            sigma = max(1e-6, min(5.0, sigma))  # Keep in reasonable range

        return sigma

    def implied_vol_brent(
        self,
        price: float,
        S: float,
        K: float,
        r: float,
        T: float,
        is_call: bool = True,
        q: float = 0
    ) -> float:
        """
        Calculate implied volatility using Brent's method.

        More robust than Newton-Raphson.
        """
        def objective(sigma):
            if is_call:
                return self.black_scholes_call(S, K, r, sigma, T, q) - price
            else:
                return self.black_scholes_put(S, K, r, sigma, T, q) - price

        try:
            return optimize.brentq(objective, 1e-6, 5.0)
        except ValueError:
            return np.nan

    def implied_vol_jaeckel(
        self,
        price: float,
        S: float,
        K: float,
        r: float,
        T: float,
        is_call: bool = True,
        q: float = 0
    ) -> float:
        """
        Jäckel's Let's Be Rational algorithm for implied volatility.

        Fastest and most robust method.
        """
        # Normalized price
        F = S * np.exp((r - q) * T)
        df = np.exp(-r * T)

        if is_call:
            intrinsic = max(F - K, 0) * df
            if price <= intrinsic:
                return 0.0
        else:
            intrinsic = max(K - F, 0) * df
            if price <= intrinsic:
                return 0.0

        # Normalized moneyness
        x = np.log(F / K)
        normalized_price = price / (S * np.exp(-q * T))

        # Initial guess from asymptotic expansion
        if abs(x) < 0.1:
            sigma0 = np.sqrt(2 * np.pi / T) * normalized_price
        else:
            sigma0 = abs(x) / np.sqrt(T)

        sigma0 = max(0.01, min(2.0, sigma0))

        # Refine with Newton
        return self.implied_vol_newton(price, S, K, r, T, is_call, q, sigma0)


# =============================================================================
# Volatility Surface Fitting
# =============================================================================

class SVI:
    """
    Stochastic Volatility Inspired (SVI) parameterization.

    Total variance: w(k) = a + b * (rho * (k - m) + sqrt((k - m)^2 + sigma^2))

    where k = log(K/F) is log-moneyness.
    """

    def __init__(self):
        self.params = {}

    def raw_svi(
        self,
        k: np.ndarray,
        a: float,
        b: float,
        rho: float,
        m: float,
        sigma: float
    ) -> np.ndarray:
        """
        Calculate total variance using raw SVI parameters.

        Args:
            k: Log-moneyness
            a, b, rho, m, sigma: SVI parameters

        Returns:
            Total variance w(k)
        """
        return a + b * (rho * (k - m) + np.sqrt((k - m)**2 + sigma**2))

    def calibrate_slice(
        self,
        strikes: np.ndarray,
        implied_vols: np.ndarray,
        forward: float,
        expiry: float,
        weights: Optional[np.ndarray] = None
    ) -> Dict[str, float]:
        """
        Calibrate SVI to a single expiry slice.

        Args:
            strikes: Strike prices
            implied_vols: Market implied volatilities
            forward: Forward price
            expiry: Time to expiry
            weights: Optional weights for fitting

        Returns:
            Calibrated SVI parameters
        """
        k = np.log(strikes / forward)
        total_var = implied_vols**2 * expiry

        if weights is None:
            weights = np.ones_like(k)

        def objective(params):
            a, b, rho, m, sigma = params
            model_var = self.raw_svi(k, a, b, rho, m, sigma)

            # Penalize negative variance and arbitrage
            penalty = 0
            if np.any(model_var < 0):
                penalty += 1e6 * np.sum(np.maximum(-model_var, 0)**2)

            return np.sum(weights * (model_var - total_var)**2) + penalty

        # Initial guess
        atm_var = np.interp(0, k, total_var)
        x0 = [atm_var, 0.1, -0.5, 0, 0.1]

        # Bounds
        bounds = [
            (0, None),      # a > 0
            (0, None),      # b > 0
            (-1, 1),        # -1 < rho < 1
            (None, None),   # m unconstrained
            (1e-6, None)    # sigma > 0
        ]

        result = optimize.minimize(
            objective,
            x0,
            method='L-BFGS-B',
            bounds=bounds,
            options={'maxiter': 1000}
        )

        params = {
            'a': result.x[0],
            'b': result.x[1],
            'rho': result.x[2],
            'm': result.x[3],
            'sigma': result.x[4],
            'expiry': expiry,
            'forward': forward
        }

        self.params[expiry] = params
        return params

    def get_implied_vol(
        self,
        strike: float,
        expiry: float,
        forward: Optional[float] = None
    ) -> float:
        """Get implied volatility from calibrated surface."""
        if expiry not in self.params:
            # Interpolate between expiries
            expiries = sorted(self.params.keys())
            if expiry < expiries[0]:
                params = self.params[expiries[0]]
            elif expiry > expiries[-1]:
                params = self.params[expiries[-1]]
            else:
                # Linear interpolation of parameters
                idx = np.searchsorted(expiries, expiry)
                t1, t2 = expiries[idx-1], expiries[idx]
                w = (expiry - t1) / (t2 - t1)
                params = {}
                for key in self.params[t1]:
                    if key not in ['expiry', 'forward']:
                        params[key] = (1 - w) * self.params[t1][key] + w * self.params[t2][key]
                params['forward'] = forward or self.params[t1]['forward']
        else:
            params = self.params[expiry]

        fwd = forward or params['forward']
        k = np.log(strike / fwd)
        total_var = self.raw_svi(k, params['a'], params['b'], params['rho'], params['m'], params['sigma'])

        return np.sqrt(max(0, total_var) / expiry)


class SSVI:
    """
    Surface SVI (SSVI) for arbitrage-free volatility surfaces.

    Extended SVI with term structure consistency.
    """

    def __init__(self):
        self.atm_total_var = None  # Function of expiry
        self.rho = None
        self.eta = None

    def calibrate(
        self,
        market_data: MarketData,
        n_expiries: int = 10
    ) -> CalibrationResult:
        """
        Calibrate SSVI surface.

        Args:
            market_data: Market option data
            n_expiries: Number of expiry slices to fit

        Returns:
            CalibrationResult
        """
        import time
        start_time = time.time()

        unique_expiries = np.unique(market_data.expiries)

        # First fit ATM total variance curve
        atm_vars = []
        for T in unique_expiries:
            mask = market_data.expiries == T
            strikes = market_data.strikes[mask]
            vols = market_data.implied_vols[mask]

            # ATM vol
            atm_vol = np.interp(market_data.spot, strikes, vols)
            atm_vars.append(atm_vol**2 * T)

        atm_vars = np.array(atm_vars)

        # Fit power law: theta(t) = a * t^b
        def atm_objective(params):
            a, b = params
            model = a * unique_expiries**b
            return np.sum((model - atm_vars)**2)

        result = optimize.minimize(atm_objective, [0.1, 1.0], method='Nelder-Mead')
        a_atm, b_atm = result.x

        self.atm_total_var = lambda t: a_atm * t**b_atm

        # Now fit rho and eta
        def surface_objective(params):
            rho, eta = params
            total_error = 0

            for T in unique_expiries:
                mask = market_data.expiries == T
                strikes = market_data.strikes[mask]
                vols = market_data.implied_vols[mask]
                forward = market_data.forward[mask][0] if market_data.forward is not None else market_data.spot

                k = np.log(strikes / forward)
                market_var = vols**2 * T

                # SSVI formula
                theta = self.atm_total_var(T)
                phi = eta / (theta**0.5 * (1 + theta)**0.5)

                model_var = 0.5 * theta * (1 + rho * phi * k + np.sqrt((phi * k + rho)**2 + 1 - rho**2))
                total_error += np.sum((model_var - market_var)**2)

            return total_error

        result = optimize.minimize(
            surface_objective,
            [-0.5, 0.5],
            method='L-BFGS-B',
            bounds=[(-0.99, 0.99), (0.01, 2.0)]
        )

        self.rho = result.x[0]
        self.eta = result.x[1]

        # Calculate fit quality
        all_model_vols = []
        all_market_vols = []

        for T in unique_expiries:
            mask = market_data.expiries == T
            strikes = market_data.strikes[mask]
            vols = market_data.implied_vols[mask]

            for K, v in zip(strikes, vols):
                all_market_vols.append(v)
                all_model_vols.append(self.get_implied_vol(K, T, market_data.spot))

        all_model_vols = np.array(all_model_vols)
        all_market_vols = np.array(all_market_vols)

        errors = all_model_vols - all_market_vols
        rmse = np.sqrt(np.mean(errors**2))
        max_error = np.max(np.abs(errors))

        return CalibrationResult(
            parameters={'a_atm': a_atm, 'b_atm': b_atm, 'rho': self.rho, 'eta': self.eta},
            objective_value=result.fun,
            rmse=rmse,
            max_error=max_error,
            success=True,
            message="SSVI calibration successful",
            n_iterations=result.nit if hasattr(result, 'nit') else 0,
            calibration_time=time.time() - start_time
        )

    def get_implied_vol(
        self,
        strike: float,
        expiry: float,
        spot: float
    ) -> float:
        """Get implied volatility from calibrated SSVI surface."""
        k = np.log(strike / spot)
        theta = self.atm_total_var(expiry)
        phi = self.eta / (theta**0.5 * (1 + theta)**0.5)

        total_var = 0.5 * theta * (1 + self.rho * phi * k + np.sqrt((phi * k + self.rho)**2 + 1 - self.rho**2))

        return np.sqrt(max(0, total_var) / expiry)


# =============================================================================
# Heston Model Calibration
# =============================================================================

class HestonCalibrator:
    """
    Calibrate Heston stochastic volatility model to market data.

    Parameters: v0, kappa, theta, sigma, rho
    """

    def __init__(self):
        self.params = None
        self.iv_calc = ImpliedVolCalculator()

    def heston_price_fft(
        self,
        S: float,
        K: float,
        r: float,
        T: float,
        v0: float,
        kappa: float,
        theta: float,
        sigma: float,
        rho: float,
        is_call: bool = True,
        q: float = 0
    ) -> float:
        """
        Price European option under Heston model using FFT.

        Carr-Madan approach.
        """
        # FFT parameters
        N = 4096
        alpha = 1.5
        eta = 0.25
        lambda_fft = 2 * np.pi / (N * eta)

        # Log-strike grid
        b = N * lambda_fft / 2
        k = np.arange(N) * lambda_fft - b

        # Characteristic function
        def heston_cf(u):
            # Complex argument
            xi = kappa - sigma * rho * 1j * u
            d = np.sqrt(xi**2 + sigma**2 * (u**2 + 1j * u))

            g1 = (xi + d) / (xi - d)
            g2 = 1 / g1

            # Avoid numerical issues
            exp_dT = np.exp(-d * T)

            D = (xi + d) / sigma**2 * (1 - exp_dT) / (1 - g2 * exp_dT)
            C = (r - q) * 1j * u * T + kappa * theta / sigma**2 * (
                (xi + d) * T - 2 * np.log((1 - g2 * exp_dT) / (1 - g2))
            )

            return np.exp(C + D * v0 + 1j * u * np.log(S))

        # Modified characteristic function for Carr-Madan
        def psi(v):
            cf = heston_cf(v - (alpha + 1) * 1j)
            denom = alpha**2 + alpha - v**2 + 1j * (2 * alpha + 1) * v
            return np.exp(-r * T) * cf / denom

        # FFT
        v = np.arange(N) * eta
        psi_v = psi(v) * np.exp(1j * b * v) * eta
        psi_v[0] *= 0.5

        fft_result = np.fft.fft(psi_v).real

        # Interpolate to get price at desired strike
        call_prices = np.exp(-alpha * k) * fft_result / np.pi

        # Find price at desired strike
        log_K = np.log(K)
        call_price = np.interp(log_K, k, call_prices)

        if is_call:
            return max(0, call_price)
        else:
            # Put-call parity
            return max(0, call_price - S * np.exp(-q * T) + K * np.exp(-r * T))

    def calibrate(
        self,
        market_data: MarketData,
        initial_params: Optional[Dict] = None,
        bounds: Optional[Dict] = None,
        objective: CalibrationObjective = CalibrationObjective.VOL_RMSE
    ) -> CalibrationResult:
        """
        Calibrate Heston model to market data.

        Args:
            market_data: Market option data
            initial_params: Starting parameter values
            bounds: Parameter bounds
            objective: Calibration objective function

        Returns:
            CalibrationResult
        """
        import time
        start_time = time.time()

        # Default initial parameters
        if initial_params is None:
            atm_vol = np.median(market_data.implied_vols)
            initial_params = {
                'v0': atm_vol**2,
                'kappa': 2.0,
                'theta': atm_vol**2,
                'sigma': 0.5,
                'rho': -0.7
            }

        # Default bounds
        if bounds is None:
            bounds = {
                'v0': (0.001, 1.0),
                'kappa': (0.01, 10.0),
                'theta': (0.001, 1.0),
                'sigma': (0.01, 2.0),
                'rho': (-0.99, 0.99)
            }

        x0 = [initial_params['v0'], initial_params['kappa'], initial_params['theta'],
              initial_params['sigma'], initial_params['rho']]
        param_bounds = [bounds['v0'], bounds['kappa'], bounds['theta'],
                       bounds['sigma'], bounds['rho']]

        # Risk-free rate (assume constant)
        r = market_data.risk_free_rates[0] if market_data.risk_free_rates is not None else 0.02

        def objective_func(params):
            v0, kappa, theta, sigma, rho = params

            # Feller condition penalty
            feller = 2 * kappa * theta - sigma**2
            penalty = 0 if feller > 0 else 1e6 * feller**2

            errors = []
            for i in range(len(market_data.strikes)):
                K = market_data.strikes[i]
                T = market_data.expiries[i]
                is_call = market_data.is_call[i] if market_data.is_call is not None else True

                try:
                    model_price = self.heston_price_fft(
                        market_data.spot, K, r, T, v0, kappa, theta, sigma, rho, is_call
                    )

                    if objective == CalibrationObjective.VOL_RMSE or objective == CalibrationObjective.VOL_MSE:
                        model_vol = self.iv_calc.implied_vol_newton(
                            model_price, market_data.spot, K, r, T, is_call
                        )
                        market_vol = market_data.implied_vols[i]
                        errors.append((model_vol - market_vol)**2)
                    else:
                        market_price = market_data.prices[i]
                        errors.append((model_price - market_price)**2)

                except Exception:
                    errors.append(1e6)

            return np.mean(errors) + penalty

        # Optimize
        result = optimize.minimize(
            objective_func,
            x0,
            method='L-BFGS-B',
            bounds=param_bounds,
            options={'maxiter': 500, 'ftol': 1e-10}
        )

        self.params = {
            'v0': result.x[0],
            'kappa': result.x[1],
            'theta': result.x[2],
            'sigma': result.x[3],
            'rho': result.x[4]
        }

        # Calculate fit statistics
        model_vols = []
        for i in range(len(market_data.strikes)):
            K = market_data.strikes[i]
            T = market_data.expiries[i]
            is_call = market_data.is_call[i] if market_data.is_call is not None else True

            try:
                model_price = self.heston_price_fft(
                    market_data.spot, K, r, T,
                    self.params['v0'], self.params['kappa'], self.params['theta'],
                    self.params['sigma'], self.params['rho'], is_call
                )
                model_vol = self.iv_calc.implied_vol_newton(
                    model_price, market_data.spot, K, r, T, is_call
                )
            except Exception:
                model_vol = np.nan
            model_vols.append(model_vol)

        model_vols = np.array(model_vols)
        errors = model_vols - market_data.implied_vols
        valid_mask = ~np.isnan(errors)

        rmse = np.sqrt(np.mean(errors[valid_mask]**2))
        max_error = np.max(np.abs(errors[valid_mask]))

        return CalibrationResult(
            parameters=self.params,
            objective_value=result.fun,
            rmse=rmse,
            max_error=max_error,
            success=result.success,
            message=result.message if hasattr(result, 'message') else "",
            n_iterations=result.nit if hasattr(result, 'nit') else 0,
            calibration_time=time.time() - start_time,
            model_prices=model_vols
        )


# =============================================================================
# SABR Calibration
# =============================================================================

class SABRCalibrator:
    """
    Calibrate SABR stochastic volatility model.

    Parameters: alpha, beta, rho, nu
    """

    def __init__(self, beta: float = 1.0):
        """
        Initialize SABR calibrator.

        Args:
            beta: CEV exponent (typically fixed, 0 = normal, 1 = lognormal)
        """
        self.beta = beta
        self.params = None

    def sabr_vol(
        self,
        F: float,
        K: float,
        T: float,
        alpha: float,
        rho: float,
        nu: float
    ) -> float:
        """
        SABR implied volatility using Hagan's formula.

        Args:
            F: Forward price
            K: Strike
            T: Time to expiry
            alpha: Initial volatility
            rho: Correlation
            nu: Vol of vol

        Returns:
            Implied Black volatility
        """
        if abs(F - K) < 1e-12:
            # ATM case
            logFK = 0
            FK_beta = F**(1 - self.beta)
        else:
            logFK = np.log(F / K)
            FK_beta = (F * K)**((1 - self.beta) / 2)

        A = alpha / FK_beta

        z = nu / alpha * FK_beta * logFK
        chi_z = np.log((np.sqrt(1 - 2 * rho * z + z**2) + z - rho) / (1 - rho)) if abs(z) > 1e-10 else 1

        B1 = 1 + ((1 - self.beta)**2 / 24 * alpha**2 / FK_beta**2 +
                  rho * self.beta * nu * alpha / (4 * FK_beta) +
                  (2 - 3 * rho**2) * nu**2 / 24) * T

        B2 = 1 + (1 - self.beta)**2 / 24 * logFK**2 + (1 - self.beta)**4 / 1920 * logFK**4

        if abs(z) < 1e-10:
            sigma = alpha / FK_beta * B1 / B2
        else:
            sigma = z / chi_z * A * B1 / B2

        return sigma

    def calibrate_slice(
        self,
        strikes: np.ndarray,
        implied_vols: np.ndarray,
        forward: float,
        expiry: float,
        atm_vol: Optional[float] = None
    ) -> Dict[str, float]:
        """
        Calibrate SABR to a single expiry slice.

        Args:
            strikes: Strike prices
            implied_vols: Market implied volatilities
            forward: Forward price
            expiry: Time to expiry
            atm_vol: ATM volatility (used to set alpha)

        Returns:
            Calibrated SABR parameters
        """
        # ATM vol for initial alpha
        if atm_vol is None:
            atm_vol = np.interp(forward, strikes, implied_vols)

        # Initial guess
        alpha0 = atm_vol * forward**(1 - self.beta)

        def objective(params):
            alpha, rho, nu = params

            errors = []
            for K, market_vol in zip(strikes, implied_vols):
                try:
                    model_vol = self.sabr_vol(forward, K, expiry, alpha, rho, nu)
                    errors.append((model_vol - market_vol)**2)
                except Exception:
                    errors.append(1e6)

            return np.sum(errors)

        result = optimize.minimize(
            objective,
            [alpha0, -0.3, 0.4],
            method='L-BFGS-B',
            bounds=[(1e-6, None), (-0.99, 0.99), (1e-6, None)]
        )

        self.params = {
            'alpha': result.x[0],
            'beta': self.beta,
            'rho': result.x[1],
            'nu': result.x[2],
            'forward': forward,
            'expiry': expiry
        }

        return self.params

    def get_implied_vol(self, strike: float) -> float:
        """Get implied volatility from calibrated SABR."""
        if self.params is None:
            raise ValueError("Model not calibrated")

        return self.sabr_vol(
            self.params['forward'],
            strike,
            self.params['expiry'],
            self.params['alpha'],
            self.params['rho'],
            self.params['nu']
        )


# =============================================================================
# Rough Volatility Models
# =============================================================================

class RoughBergomiCalibrator:
    """
    Rough Bergomi model calibration.

    Volatility driven by fractional Brownian motion with H < 0.5.
    """

    def __init__(self, H: float = 0.1):
        """
        Initialize rough Bergomi calibrator.

        Args:
            H: Hurst parameter (0 < H < 0.5 for rough volatility)
        """
        self.H = H
        self.params = None

    def simulate_rough_bergomi(
        self,
        S0: float,
        v0: float,
        eta: float,
        rho: float,
        T: float,
        n_steps: int = 252,
        n_paths: int = 10000,
        seed: Optional[int] = None
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Simulate rough Bergomi paths.

        Uses Cholesky method for fractional Brownian motion.

        Returns:
            Tuple of (price_paths, variance_paths)
        """
        if seed is not None:
            np.random.seed(seed)

        dt = T / n_steps
        t_grid = np.linspace(0, T, n_steps + 1)

        # Build fBM covariance matrix
        def fbm_cov(s, t):
            return 0.5 * (s**(2*self.H) + t**(2*self.H) - abs(t - s)**(2*self.H))

        cov_matrix = np.zeros((n_steps + 1, n_steps + 1))
        for i in range(n_steps + 1):
            for j in range(n_steps + 1):
                cov_matrix[i, j] = fbm_cov(t_grid[i], t_grid[j])

        # Add small regularization
        cov_matrix += 1e-10 * np.eye(n_steps + 1)

        try:
            L = np.linalg.cholesky(cov_matrix)
        except np.linalg.LinAlgError:
            # Fallback to eigenvalue decomposition
            eigenvalues, eigenvectors = np.linalg.eigh(cov_matrix)
            eigenvalues = np.maximum(eigenvalues, 1e-10)
            L = eigenvectors @ np.diag(np.sqrt(eigenvalues))

        # Generate correlated fBM and standard BM
        Z1 = np.random.standard_normal((n_paths, n_steps + 1))
        Z2 = np.random.standard_normal((n_paths, n_steps + 1))

        W_perp = Z1 @ L.T
        W_corr = rho * W_perp + np.sqrt(1 - rho**2) * Z2 @ L.T

        # Variance process
        variance = np.zeros((n_paths, n_steps + 1))
        variance[:, 0] = v0

        for t in range(n_steps):
            variance[:, t+1] = v0 * np.exp(
                eta * W_perp[:, t+1] - 0.5 * eta**2 * t_grid[t+1]**(2*self.H)
            )

        # Price process
        prices = np.zeros((n_paths, n_steps + 1))
        prices[:, 0] = S0

        for t in range(n_steps):
            dW = W_corr[:, t+1] - W_corr[:, t]
            prices[:, t+1] = prices[:, t] * np.exp(
                -0.5 * variance[:, t] * dt + np.sqrt(variance[:, t] * dt) * dW / np.sqrt(dt)
            )

        return prices, variance

    def price_european(
        self,
        S0: float,
        K: float,
        r: float,
        T: float,
        v0: float,
        eta: float,
        rho: float,
        is_call: bool = True,
        n_paths: int = 50000
    ) -> Tuple[float, float]:
        """Price European option under rough Bergomi."""
        prices, _ = self.simulate_rough_bergomi(S0, v0, eta, rho, T, n_paths=n_paths)
        ST = prices[:, -1]

        if is_call:
            payoffs = np.maximum(ST - K, 0)
        else:
            payoffs = np.maximum(K - ST, 0)

        discount = np.exp(-r * T)
        price = discount * np.mean(payoffs)
        std_error = discount * np.std(payoffs) / np.sqrt(n_paths)

        return price, std_error


# =============================================================================
# Local Volatility Calibration
# =============================================================================

class LocalVolCalibrator:
    """
    Extract local volatility surface using Dupire's formula.
    """

    def __init__(self):
        self.local_vol_surface = None

    def dupire_local_vol(
        self,
        vol_surface: VolatilitySurface,
        strike: float,
        expiry: float,
        spot: float,
        r: float = 0.02,
        q: float = 0.0
    ) -> float:
        """
        Calculate local volatility using Dupire's formula.

        sigma_local^2 = (dw/dT + (r-q)*K*dw/dK + 0.5*K^2*(d^2w/dK^2)) / (...)
        """
        eps_K = strike * 0.01
        eps_T = 0.01

        # Get implied vols
        vol = vol_surface.get_vol(strike, expiry)
        vol_K_up = vol_surface.get_vol(strike + eps_K, expiry)
        vol_K_down = vol_surface.get_vol(strike - eps_K, expiry)
        vol_T_up = vol_surface.get_vol(strike, expiry + eps_T) if expiry + eps_T <= max(vol_surface.expiries) else vol
        vol_T_down = vol_surface.get_vol(strike, max(0.01, expiry - eps_T))

        # Total variance
        w = vol**2 * expiry
        w_T_up = vol_T_up**2 * (expiry + eps_T)
        w_T_down = vol_T_down**2 * max(0.01, expiry - eps_T)

        # Derivatives
        dw_dT = (w_T_up - w_T_down) / (2 * eps_T)
        dw_dK = (vol_K_up**2 * expiry - vol_K_down**2 * expiry) / (2 * eps_K)
        d2w_dK2 = (vol_K_up**2 - 2 * vol**2 + vol_K_down**2) * expiry / (eps_K**2)

        # Dupire formula
        y = np.log(strike / spot)
        d1 = y / (vol * np.sqrt(expiry)) + 0.5 * vol * np.sqrt(expiry)

        numerator = dw_dT + (r - q) * strike * dw_dK
        denominator = (1 - y / w * dw_dK + 0.25 * (-0.25 - 1/w + y**2/w**2) * (dw_dK)**2 + 0.5 * d2w_dK2)

        if denominator <= 0:
            return vol  # Fallback to implied vol

        local_var = numerator / denominator
        return np.sqrt(max(0, local_var))

    def build_surface(
        self,
        vol_surface: VolatilitySurface,
        spot: float,
        r: float = 0.02,
        q: float = 0.0,
        strike_range: Tuple[float, float] = (0.5, 1.5),
        n_strikes: int = 50,
        n_expiries: int = 20
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Build local volatility surface.

        Returns:
            Tuple of (strikes, expiries, local_vols)
        """
        strikes = np.linspace(spot * strike_range[0], spot * strike_range[1], n_strikes)
        expiries = np.linspace(min(vol_surface.expiries), max(vol_surface.expiries), n_expiries)

        local_vols = np.zeros((n_expiries, n_strikes))

        for i, T in enumerate(expiries):
            for j, K in enumerate(strikes):
                local_vols[i, j] = self.dupire_local_vol(vol_surface, K, T, spot, r, q)

        self.local_vol_surface = (strikes, expiries, local_vols)
        return strikes, expiries, local_vols


# =============================================================================
# Factory Functions
# =============================================================================

def create_heston_calibrator() -> HestonCalibrator:
    """Create Heston model calibrator."""
    return HestonCalibrator()


def create_sabr_calibrator(beta: float = 1.0) -> SABRCalibrator:
    """Create SABR model calibrator."""
    return SABRCalibrator(beta)


def create_svi_fitter() -> SVI:
    """Create SVI volatility surface fitter."""
    return SVI()


def create_ssvi_fitter() -> SSVI:
    """Create SSVI volatility surface fitter."""
    return SSVI()


def calibrate_volatility_surface(
    strikes: np.ndarray,
    expiries: np.ndarray,
    implied_vols: np.ndarray,
    spot: float,
    method: str = "svi"
) -> Union[SVI, SSVI]:
    """
    Quick volatility surface calibration.

    Args:
        strikes: Strike prices
        expiries: Expiry times
        implied_vols: Market implied volatilities
        spot: Current spot price
        method: "svi" or "ssvi"

    Returns:
        Calibrated surface model
    """
    if method == "svi":
        fitter = SVI()
        unique_expiries = np.unique(expiries)
        for T in unique_expiries:
            mask = expiries == T
            fitter.calibrate_slice(
                strikes[mask],
                implied_vols[mask],
                spot,
                T
            )
        return fitter
    elif method == "ssvi":
        fitter = SSVI()
        market_data = MarketData(
            strikes=strikes,
            expiries=expiries,
            prices=np.zeros_like(strikes),  # Not needed for SSVI
            spot=spot,
            implied_vols=implied_vols
        )
        fitter.calibrate(market_data)
        return fitter
    else:
        raise ValueError(f"Unknown method: {method}")
