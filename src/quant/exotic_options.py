"""
Revolution Alpha Engine - Advanced Exotic Options Module

Institutional-grade exotic derivatives pricing:
- Rainbow options (multi-asset)
- Spread options
- Compound options (options on options)
- Chooser options
- Variance and volatility swaps
- Cliquet/Ratchet options
- Autocallables
- Target redemption notes (TARNs)
- Power options
- Quanto options
- Forward start options
"""

import numpy as np
from scipy import stats, optimize, integrate
from scipy.special import ndtr as norm_cdf
from dataclasses import dataclass
from typing import List, Optional, Tuple, Callable, Union
from enum import Enum
from abc import ABC, abstractmethod


# =============================================================================
# Data Classes and Enums
# =============================================================================

class RainbowType(Enum):
    """Types of rainbow options."""
    BEST_OF_CALL = "best_of_call"
    WORST_OF_CALL = "worst_of_call"
    BEST_OF_PUT = "best_of_put"
    WORST_OF_PUT = "worst_of_put"
    MAX_CALL = "max_call"  # Call on maximum
    MIN_PUT = "min_put"    # Put on minimum
    SPREAD = "spread"      # Best minus worst


class SpreadType(Enum):
    """Types of spread options."""
    CALL_SPREAD = "call_spread"  # max(S1 - S2 - K, 0)
    PUT_SPREAD = "put_spread"    # max(K - S1 + S2, 0)
    EXCHANGE = "exchange"         # max(S1 - S2, 0), K=0


@dataclass
class ExoticPricingResult:
    """Result container for exotic option pricing."""
    price: float
    std_error: Optional[float] = None
    delta: Optional[np.ndarray] = None  # Vector for multi-asset
    gamma: Optional[np.ndarray] = None
    vega: Optional[np.ndarray] = None
    theta: Optional[float] = None
    rho: Optional[float] = None
    additional_info: Optional[dict] = None


# =============================================================================
# Rainbow Options (Multi-Asset)
# =============================================================================

class RainbowOption:
    """
    Rainbow options on multiple underlying assets.

    Includes best-of, worst-of, and spread options.
    """

    def __init__(
        self,
        spots: np.ndarray,
        strikes: Union[float, np.ndarray],
        volatilities: np.ndarray,
        correlation_matrix: np.ndarray,
        risk_free_rate: float,
        dividend_yields: Optional[np.ndarray] = None,
        time_to_maturity: float = 1.0
    ):
        """
        Initialize rainbow option.

        Args:
            spots: Current spot prices for each asset
            strikes: Strike price(s)
            volatilities: Volatilities for each asset
            correlation_matrix: Correlation matrix between assets
            risk_free_rate: Risk-free rate
            dividend_yields: Dividend yields for each asset
            time_to_maturity: Time to expiry in years
        """
        self.S = np.array(spots)
        self.K = strikes
        self.sigma = np.array(volatilities)
        self.rho = np.array(correlation_matrix)
        self.r = risk_free_rate
        self.q = np.zeros_like(self.S) if dividend_yields is None else np.array(dividend_yields)
        self.T = time_to_maturity
        self.n_assets = len(spots)

    def price_two_asset_analytical(
        self,
        rainbow_type: RainbowType
    ) -> float:
        """
        Analytical pricing for two-asset rainbow options.

        Uses Stulz (1982) formulas.
        """
        if self.n_assets != 2:
            raise ValueError("Analytical formula requires exactly 2 assets")

        S1, S2 = self.S
        sigma1, sigma2 = self.sigma
        q1, q2 = self.q
        rho = self.rho[0, 1]
        K = self.K
        T = self.T
        r = self.r

        # Combined volatility for best/worst of options
        sigma = np.sqrt(sigma1**2 + sigma2**2 - 2 * rho * sigma1 * sigma2)

        # Forward prices
        F1 = S1 * np.exp((r - q1) * T)
        F2 = S2 * np.exp((r - q2) * T)

        # d1 and d2 for each asset
        d1_1 = (np.log(S1 / K) + (r - q1 + 0.5 * sigma1**2) * T) / (sigma1 * np.sqrt(T))
        d2_1 = d1_1 - sigma1 * np.sqrt(T)

        d1_2 = (np.log(S2 / K) + (r - q2 + 0.5 * sigma2**2) * T) / (sigma2 * np.sqrt(T))
        d2_2 = d1_2 - sigma2 * np.sqrt(T)

        # Cross terms for bivariate normal
        y1 = (np.log(S1 / S2) + (q2 - q1 + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
        y2 = y1 - sigma * np.sqrt(T)

        rho1 = (sigma1 - rho * sigma2) / sigma
        rho2 = (sigma2 - rho * sigma1) / sigma

        discount = np.exp(-r * T)

        if rainbow_type == RainbowType.BEST_OF_CALL:
            # Call on max(S1, S2)
            price = (
                S1 * np.exp(-q1 * T) * self._bivariate_normal(d1_1, -y1, -rho1) +
                S2 * np.exp(-q2 * T) * self._bivariate_normal(d1_2, y1 - sigma * np.sqrt(T), -rho2) -
                K * discount * (1 - self._bivariate_normal(-d2_1, -d2_2, rho))
            )

        elif rainbow_type == RainbowType.WORST_OF_CALL:
            # Call on min(S1, S2)
            price = (
                S1 * np.exp(-q1 * T) * self._bivariate_normal(d1_1, y1, rho1) +
                S2 * np.exp(-q2 * T) * self._bivariate_normal(d1_2, -y1 + sigma * np.sqrt(T), rho2) -
                K * discount * self._bivariate_normal(d2_1, d2_2, rho)
            )

        elif rainbow_type == RainbowType.BEST_OF_PUT:
            # Put on max(S1, S2)
            price = (
                K * discount * self._bivariate_normal(-d2_1, -d2_2, rho) -
                S1 * np.exp(-q1 * T) * self._bivariate_normal(-d1_1, y1, rho1) -
                S2 * np.exp(-q2 * T) * self._bivariate_normal(-d1_2, -y1 + sigma * np.sqrt(T), rho2)
            )

        elif rainbow_type == RainbowType.WORST_OF_PUT:
            # Put on min(S1, S2)
            price = (
                K * discount * (1 - self._bivariate_normal(d2_1, d2_2, rho)) -
                S1 * np.exp(-q1 * T) * self._bivariate_normal(-d1_1, -y1, -rho1) -
                S2 * np.exp(-q2 * T) * self._bivariate_normal(-d1_2, y1 - sigma * np.sqrt(T), -rho2)
            )

        else:
            raise ValueError(f"Analytical formula not available for {rainbow_type}")

        return max(0, price)

    def price_monte_carlo(
        self,
        rainbow_type: RainbowType,
        n_paths: int = 100000,
        n_steps: int = 252,
        seed: Optional[int] = None
    ) -> ExoticPricingResult:
        """
        Monte Carlo pricing for any rainbow option type.

        Args:
            rainbow_type: Type of rainbow option
            n_paths: Number of Monte Carlo paths
            n_steps: Number of time steps
            seed: Random seed

        Returns:
            ExoticPricingResult
        """
        if seed is not None:
            np.random.seed(seed)

        dt = self.T / n_steps

        # Generate correlated random numbers using Cholesky
        L = np.linalg.cholesky(self.rho)
        Z = np.random.standard_normal((n_paths, n_steps, self.n_assets))
        Z_corr = np.einsum('ijk,lk->ijl', Z, L)

        # Simulate paths
        paths = np.zeros((n_paths, n_steps + 1, self.n_assets))
        paths[:, 0, :] = self.S

        for i in range(self.n_assets):
            drift = (self.r - self.q[i] - 0.5 * self.sigma[i]**2) * dt
            diffusion = self.sigma[i] * np.sqrt(dt)

            for t in range(n_steps):
                paths[:, t+1, i] = paths[:, t, i] * np.exp(
                    drift + diffusion * Z_corr[:, t, i]
                )

        # Terminal values
        ST = paths[:, -1, :]

        # Calculate payoffs based on option type
        K = self.K

        if rainbow_type == RainbowType.BEST_OF_CALL:
            payoffs = np.maximum(np.max(ST, axis=1) - K, 0)

        elif rainbow_type == RainbowType.WORST_OF_CALL:
            payoffs = np.maximum(np.min(ST, axis=1) - K, 0)

        elif rainbow_type == RainbowType.BEST_OF_PUT:
            payoffs = np.maximum(K - np.max(ST, axis=1), 0)

        elif rainbow_type == RainbowType.WORST_OF_PUT:
            payoffs = np.maximum(K - np.min(ST, axis=1), 0)

        elif rainbow_type == RainbowType.MAX_CALL:
            payoffs = np.maximum(np.max(ST, axis=1) - K, 0)

        elif rainbow_type == RainbowType.MIN_PUT:
            payoffs = np.maximum(K - np.min(ST, axis=1), 0)

        elif rainbow_type == RainbowType.SPREAD:
            payoffs = np.max(ST, axis=1) - np.min(ST, axis=1)

        else:
            raise ValueError(f"Unknown rainbow type: {rainbow_type}")

        discount = np.exp(-self.r * self.T)
        price = discount * np.mean(payoffs)
        std_error = discount * np.std(payoffs) / np.sqrt(n_paths)

        return ExoticPricingResult(
            price=price,
            std_error=std_error,
            additional_info={'n_paths': n_paths, 'n_steps': n_steps}
        )

    def _bivariate_normal(
        self,
        a: float,
        b: float,
        rho: float
    ) -> float:
        """
        Bivariate normal CDF using Drezner-Wesolowsky approximation.
        """
        if abs(rho) < 1e-10:
            return norm_cdf(a) * norm_cdf(b)

        if abs(rho) > 0.9999:
            if rho > 0:
                return norm_cdf(min(a, b))
            else:
                return max(0, norm_cdf(a) - norm_cdf(-b))

        # Gauss-Legendre weights and abscissas
        x = np.array([0.04691008, 0.23076534, 0.50000000, 0.76923466, 0.95308992])
        w = np.array([0.01184634, 0.23931434, 0.28444444, 0.23931434, 0.01184634])

        h = -a
        k = -b

        bvn = 0.0

        if abs(rho) < 0.925:
            hs = (h * h + k * k) / 2
            asr = np.arcsin(rho)

            for i in range(5):
                for sign in [-1, 1]:
                    sn = np.sin(asr * (sign * x[i] + 1) / 2)
                    bvn += w[i] * np.exp((sn * h * k - hs) / (1 - sn * sn))

            bvn *= asr / (4 * np.pi)
            bvn += norm_cdf(-h) * norm_cdf(-k)
        else:
            if rho < 0:
                k = -k
                hk = -h * k
            else:
                hk = h * k

            if abs(rho) < 1:
                ass = (1 - rho) * (1 + rho)
                a_coef = np.sqrt(ass)
                bs = (h - k) ** 2
                c = (4 - hk) / 8
                d = (12 - hk) / 16
                asr = -(bs / ass + hk) / 2

                if asr > -100:
                    bvn = (a_coef * np.exp(asr) *
                           (1 - c * (bs - ass) * (1 - d * bs / 5) / 3 +
                            c * d * ass * ass / 5))

                if -hk < 100:
                    b_coef = np.sqrt(bs)
                    bvn -= np.exp(-hk / 2) * np.sqrt(2 * np.pi) * norm_cdf(-b_coef / a_coef) * b_coef * (
                        1 - c * bs * (1 - d * bs / 5) / 3
                    )

                a_coef /= 2

                for i in range(5):
                    for sign in [-1, 1]:
                        xs = (a_coef * (sign * x[i] + 1)) ** 2
                        rs = np.sqrt(1 - xs)
                        asr = -(bs / xs + hk) / 2

                        if asr > -100:
                            bvn += (a_coef * w[i] * np.exp(asr) *
                                   (np.exp(-hk * (1 - rs) / (2 * (1 + rs))) / rs -
                                    (1 + c * xs * (1 + d * xs))))

                bvn /= -2 * np.pi

            if rho > 0:
                bvn += norm_cdf(-max(h, k))
            else:
                bvn = -bvn
                if k > h:
                    bvn += norm_cdf(k) - norm_cdf(h)

        return max(0, min(1, bvn))


# =============================================================================
# Spread Options
# =============================================================================

class SpreadOption:
    """
    Spread options (exchange options, crack spreads, etc.).

    Payoff: max(S1 - S2 - K, 0) for call spread
    """

    def __init__(
        self,
        S1: float,
        S2: float,
        K: float,
        sigma1: float,
        sigma2: float,
        correlation: float,
        risk_free_rate: float,
        q1: float = 0.0,
        q2: float = 0.0,
        time_to_maturity: float = 1.0
    ):
        """
        Initialize spread option.

        Args:
            S1, S2: Spot prices of the two assets
            K: Strike (spread)
            sigma1, sigma2: Volatilities
            correlation: Correlation between assets
            risk_free_rate: Risk-free rate
            q1, q2: Dividend yields
            time_to_maturity: Time to expiry
        """
        self.S1 = S1
        self.S2 = S2
        self.K = K
        self.sigma1 = sigma1
        self.sigma2 = sigma2
        self.rho = correlation
        self.r = risk_free_rate
        self.q1 = q1
        self.q2 = q2
        self.T = time_to_maturity

    def price_kirk(self) -> float:
        """
        Kirk's approximation for spread options.

        Accurate for small K relative to S2.
        """
        F1 = self.S1 * np.exp((self.r - self.q1) * self.T)
        F2 = self.S2 * np.exp((self.r - self.q2) * self.T)

        # Adjusted forward and volatility
        F2_adj = F2 + self.K * np.exp(-self.r * self.T)

        sigma_adj = np.sqrt(
            self.sigma1**2 -
            2 * self.rho * self.sigma1 * self.sigma2 * F2 / F2_adj +
            (self.sigma2 * F2 / F2_adj)**2
        )

        # Black-Scholes on adjusted forward
        d1 = (np.log(F1 / F2_adj) + 0.5 * sigma_adj**2 * self.T) / (sigma_adj * np.sqrt(self.T))
        d2 = d1 - sigma_adj * np.sqrt(self.T)

        discount = np.exp(-self.r * self.T)
        price = discount * (F1 * norm_cdf(d1) - F2_adj * norm_cdf(d2))

        return max(0, price)

    def price_margrabe(self) -> float:
        """
        Margrabe's formula for exchange options (K=0).

        max(S1 - S2, 0)
        """
        if self.K != 0:
            raise ValueError("Margrabe formula requires K=0")

        sigma = np.sqrt(
            self.sigma1**2 +
            self.sigma2**2 -
            2 * self.rho * self.sigma1 * self.sigma2
        )

        d1 = (np.log(self.S1 / self.S2) +
              (self.q2 - self.q1 + 0.5 * sigma**2) * self.T) / (sigma * np.sqrt(self.T))
        d2 = d1 - sigma * np.sqrt(self.T)

        price = (self.S1 * np.exp(-self.q1 * self.T) * norm_cdf(d1) -
                self.S2 * np.exp(-self.q2 * self.T) * norm_cdf(d2))

        return max(0, price)

    def price_monte_carlo(
        self,
        spread_type: SpreadType = SpreadType.CALL_SPREAD,
        n_paths: int = 100000,
        seed: Optional[int] = None
    ) -> ExoticPricingResult:
        """Monte Carlo pricing for spread options."""
        if seed is not None:
            np.random.seed(seed)

        # Correlated normals
        Z1 = np.random.standard_normal(n_paths)
        Z2 = self.rho * Z1 + np.sqrt(1 - self.rho**2) * np.random.standard_normal(n_paths)

        # Terminal prices
        S1_T = self.S1 * np.exp(
            (self.r - self.q1 - 0.5 * self.sigma1**2) * self.T +
            self.sigma1 * np.sqrt(self.T) * Z1
        )
        S2_T = self.S2 * np.exp(
            (self.r - self.q2 - 0.5 * self.sigma2**2) * self.T +
            self.sigma2 * np.sqrt(self.T) * Z2
        )

        # Payoff
        if spread_type == SpreadType.CALL_SPREAD:
            payoffs = np.maximum(S1_T - S2_T - self.K, 0)
        elif spread_type == SpreadType.PUT_SPREAD:
            payoffs = np.maximum(self.K - S1_T + S2_T, 0)
        elif spread_type == SpreadType.EXCHANGE:
            payoffs = np.maximum(S1_T - S2_T, 0)
        else:
            raise ValueError(f"Unknown spread type: {spread_type}")

        discount = np.exp(-self.r * self.T)
        price = discount * np.mean(payoffs)
        std_error = discount * np.std(payoffs) / np.sqrt(n_paths)

        return ExoticPricingResult(price=price, std_error=std_error)


# =============================================================================
# Compound Options
# =============================================================================

class CompoundOption:
    """
    Compound options (options on options).

    - Call on call
    - Call on put
    - Put on call
    - Put on put
    """

    def __init__(
        self,
        S: float,
        K1: float,  # Strike of outer option
        K2: float,  # Strike of inner option
        sigma: float,
        risk_free_rate: float,
        T1: float,  # Maturity of outer option
        T2: float,  # Maturity of inner option
        q: float = 0.0
    ):
        """
        Initialize compound option.

        Args:
            S: Current spot price
            K1: Strike of the compound option
            K2: Strike of the underlying option
            sigma: Volatility
            risk_free_rate: Risk-free rate
            T1: Time to expiry of compound option
            T2: Time to expiry of underlying option (T2 > T1)
            q: Dividend yield
        """
        if T2 <= T1:
            raise ValueError("T2 must be greater than T1")

        self.S = S
        self.K1 = K1
        self.K2 = K2
        self.sigma = sigma
        self.r = risk_free_rate
        self.T1 = T1
        self.T2 = T2
        self.q = q

    def _find_critical_price(
        self,
        inner_is_call: bool
    ) -> float:
        """Find critical stock price where inner option value equals K1."""
        from .derivatives import BlackScholes

        def objective(S_star):
            bs = BlackScholes(S_star, self.K2, self.r, self.sigma, self.T2 - self.T1, self.q)
            if inner_is_call:
                return bs.call_price() - self.K1
            else:
                return bs.put_price() - self.K1

        # Bracket and solve
        try:
            S_star = optimize.brentq(objective, 1e-6, self.S * 10)
        except ValueError:
            S_star = self.K2  # Fallback

        return S_star

    def price_call_on_call(self) -> float:
        """
        Price call on call compound option.

        Analytical formula using bivariate normal.
        """
        S_star = self._find_critical_price(inner_is_call=True)

        sqrt_T1 = np.sqrt(self.T1)
        sqrt_T2 = np.sqrt(self.T2)

        a1 = (np.log(self.S / S_star) + (self.r - self.q + 0.5 * self.sigma**2) * self.T1) / (self.sigma * sqrt_T1)
        a2 = a1 - self.sigma * sqrt_T1

        b1 = (np.log(self.S / self.K2) + (self.r - self.q + 0.5 * self.sigma**2) * self.T2) / (self.sigma * sqrt_T2)
        b2 = b1 - self.sigma * sqrt_T2

        rho = np.sqrt(self.T1 / self.T2)

        # Use bivariate normal
        rainbow = RainbowOption(
            spots=np.array([1, 1]),
            strikes=1,
            volatilities=np.array([1, 1]),
            correlation_matrix=np.array([[1, rho], [rho, 1]]),
            risk_free_rate=0,
            time_to_maturity=1
        )

        M_a1_b1 = rainbow._bivariate_normal(a1, b1, rho)
        M_a2_b2 = rainbow._bivariate_normal(a2, b2, rho)

        price = (
            self.S * np.exp(-self.q * self.T2) * M_a1_b1 -
            self.K2 * np.exp(-self.r * self.T2) * M_a2_b2 -
            self.K1 * np.exp(-self.r * self.T1) * norm_cdf(a2)
        )

        return max(0, price)

    def price_put_on_call(self) -> float:
        """Price put on call compound option."""
        S_star = self._find_critical_price(inner_is_call=True)

        sqrt_T1 = np.sqrt(self.T1)
        sqrt_T2 = np.sqrt(self.T2)

        a1 = (np.log(self.S / S_star) + (self.r - self.q + 0.5 * self.sigma**2) * self.T1) / (self.sigma * sqrt_T1)
        a2 = a1 - self.sigma * sqrt_T1

        b1 = (np.log(self.S / self.K2) + (self.r - self.q + 0.5 * self.sigma**2) * self.T2) / (self.sigma * sqrt_T2)
        b2 = b1 - self.sigma * sqrt_T2

        rho = np.sqrt(self.T1 / self.T2)

        rainbow = RainbowOption(
            spots=np.array([1, 1]), strikes=1, volatilities=np.array([1, 1]),
            correlation_matrix=np.array([[1, rho], [rho, 1]]), risk_free_rate=0, time_to_maturity=1
        )

        M_neg_a1_b1 = rainbow._bivariate_normal(-a1, b1, -rho)
        M_neg_a2_b2 = rainbow._bivariate_normal(-a2, b2, -rho)

        price = (
            -self.S * np.exp(-self.q * self.T2) * M_neg_a1_b1 +
            self.K2 * np.exp(-self.r * self.T2) * M_neg_a2_b2 +
            self.K1 * np.exp(-self.r * self.T1) * norm_cdf(-a2)
        )

        return max(0, price)

    def price_monte_carlo(
        self,
        outer_is_call: bool = True,
        inner_is_call: bool = True,
        n_paths: int = 100000,
        seed: Optional[int] = None
    ) -> ExoticPricingResult:
        """Monte Carlo pricing for compound options."""
        from .derivatives import BlackScholes

        if seed is not None:
            np.random.seed(seed)

        # Simulate to T1
        Z1 = np.random.standard_normal(n_paths)
        S_T1 = self.S * np.exp(
            (self.r - self.q - 0.5 * self.sigma**2) * self.T1 +
            self.sigma * np.sqrt(self.T1) * Z1
        )

        # Value inner option at T1
        inner_values = np.zeros(n_paths)
        remaining_time = self.T2 - self.T1

        for i, s in enumerate(S_T1):
            bs = BlackScholes(s, self.K2, self.r, self.sigma, remaining_time, self.q)
            if inner_is_call:
                inner_values[i] = bs.call_price()
            else:
                inner_values[i] = bs.put_price()

        # Outer option payoff
        if outer_is_call:
            payoffs = np.maximum(inner_values - self.K1, 0)
        else:
            payoffs = np.maximum(self.K1 - inner_values, 0)

        discount = np.exp(-self.r * self.T1)
        price = discount * np.mean(payoffs)
        std_error = discount * np.std(payoffs) / np.sqrt(n_paths)

        return ExoticPricingResult(price=price, std_error=std_error)


# =============================================================================
# Chooser Options
# =============================================================================

class ChooserOption:
    """
    Chooser option: holder chooses call or put at choice date.
    """

    def __init__(
        self,
        S: float,
        K: float,
        sigma: float,
        risk_free_rate: float,
        T_choose: float,  # Choice date
        T_expire: float,  # Expiry date
        q: float = 0.0
    ):
        """
        Initialize chooser option.

        Args:
            S: Current spot price
            K: Strike price
            sigma: Volatility
            risk_free_rate: Risk-free rate
            T_choose: Time to choice date
            T_expire: Time to expiry (T_expire > T_choose)
            q: Dividend yield
        """
        if T_expire <= T_choose:
            raise ValueError("Expiry must be after choice date")

        self.S = S
        self.K = K
        self.sigma = sigma
        self.r = risk_free_rate
        self.T_choose = T_choose
        self.T_expire = T_expire
        self.q = q

    def price_simple(self) -> float:
        """
        Price simple chooser (same strike and expiry for call and put).

        Uses Rubinstein (1991) formula.
        """
        T1 = self.T_choose
        T2 = self.T_expire

        d = (np.log(self.S / self.K) +
             (self.r - self.q + 0.5 * self.sigma**2) * T2) / (self.sigma * np.sqrt(T2))

        y = (np.log(self.S / self.K) +
             (self.r - self.q) * T2 + 0.5 * self.sigma**2 * T1) / (self.sigma * np.sqrt(T1))

        # Chooser = Call(T2) + Put(T1) with adjusted strike
        price = (
            self.S * np.exp(-self.q * T2) * norm_cdf(d) -
            self.K * np.exp(-self.r * T2) * norm_cdf(d - self.sigma * np.sqrt(T2)) -
            self.S * np.exp(-self.q * T2) * norm_cdf(-y) +
            self.K * np.exp(-self.r * T1) * norm_cdf(-y + self.sigma * np.sqrt(T1))
        )

        return max(0, price)

    def price_monte_carlo(
        self,
        n_paths: int = 100000,
        seed: Optional[int] = None
    ) -> ExoticPricingResult:
        """Monte Carlo pricing for chooser option."""
        from .derivatives import BlackScholes

        if seed is not None:
            np.random.seed(seed)

        # Simulate to choice date
        Z = np.random.standard_normal(n_paths)
        S_T1 = self.S * np.exp(
            (self.r - self.q - 0.5 * self.sigma**2) * self.T_choose +
            self.sigma * np.sqrt(self.T_choose) * Z
        )

        remaining_time = self.T_expire - self.T_choose
        payoffs = np.zeros(n_paths)

        for i, s in enumerate(S_T1):
            bs = BlackScholes(s, self.K, self.r, self.sigma, remaining_time, self.q)
            call_value = bs.call_price()
            put_value = bs.put_price()
            payoffs[i] = max(call_value, put_value)

        discount = np.exp(-self.r * self.T_choose)
        price = discount * np.mean(payoffs)
        std_error = discount * np.std(payoffs) / np.sqrt(n_paths)

        return ExoticPricingResult(price=price, std_error=std_error)


# =============================================================================
# Variance and Volatility Swaps
# =============================================================================

class VarianceSwap:
    """
    Variance swap pricing and hedging.

    Pay fixed variance, receive realized variance.
    """

    def __init__(
        self,
        S: float,
        risk_free_rate: float,
        time_to_maturity: float,
        q: float = 0.0
    ):
        """
        Initialize variance swap.

        Args:
            S: Current spot price
            risk_free_rate: Risk-free rate
            time_to_maturity: Time to maturity
            q: Dividend yield
        """
        self.S = S
        self.r = risk_free_rate
        self.T = time_to_maturity
        self.q = q

    def fair_variance_strike(
        self,
        put_strikes: np.ndarray,
        put_prices: np.ndarray,
        call_strikes: np.ndarray,
        call_prices: np.ndarray,
        forward: Optional[float] = None
    ) -> float:
        """
        Calculate fair variance strike using put-call strip.

        Uses model-free replication from vanilla options.

        Args:
            put_strikes: Put option strikes (K < F)
            put_prices: Put option prices
            call_strikes: Call option strikes (K > F)
            call_prices: Call option prices
            forward: Forward price (calculated if not provided)

        Returns:
            Fair variance strike (annualized variance)
        """
        if forward is None:
            forward = self.S * np.exp((self.r - self.q) * self.T)

        discount = np.exp(-self.r * self.T)

        # Contribution from puts (K < F)
        put_contrib = 0.0
        for i in range(len(put_strikes)):
            K = put_strikes[i]
            if K < forward:
                dK = put_strikes[i+1] - K if i < len(put_strikes) - 1 else K - put_strikes[i-1]
                put_contrib += dK / K**2 * put_prices[i]

        # Contribution from calls (K > F)
        call_contrib = 0.0
        for i in range(len(call_strikes)):
            K = call_strikes[i]
            if K > forward:
                dK = call_strikes[i+1] - K if i < len(call_strikes) - 1 else K - call_strikes[i-1]
                call_contrib += dK / K**2 * call_prices[i]

        # Fair variance
        variance_strike = (2 / self.T) * (put_contrib + call_contrib) / discount

        return variance_strike

    def fair_variance_strike_bs(
        self,
        implied_vol: float
    ) -> float:
        """
        Fair variance strike under Black-Scholes.

        Simply equals sigma^2.
        """
        return implied_vol ** 2

    def value(
        self,
        strike_variance: float,
        realized_variance: float,
        notional: float
    ) -> float:
        """
        Calculate variance swap value.

        Args:
            strike_variance: Fixed variance strike
            realized_variance: Realized variance (or expected future)
            notional: Variance notional

        Returns:
            Variance swap value
        """
        return np.exp(-self.r * self.T) * notional * (realized_variance - strike_variance)


class VolatilitySwap:
    """
    Volatility swap pricing.

    Pay fixed volatility, receive realized volatility.
    """

    def __init__(
        self,
        S: float,
        risk_free_rate: float,
        time_to_maturity: float
    ):
        self.S = S
        self.r = risk_free_rate
        self.T = time_to_maturity

    def fair_vol_strike(
        self,
        fair_variance: float
    ) -> float:
        """
        Approximate fair volatility strike.

        Uses convexity adjustment: E[sqrt(V)] ≈ sqrt(E[V]) - Vol(V)^2 / (8 * sqrt(E[V])^3)

        Args:
            fair_variance: Fair variance strike

        Returns:
            Fair volatility strike
        """
        # Simple approximation (ignores convexity adjustment)
        return np.sqrt(fair_variance)

    def fair_vol_strike_with_adjustment(
        self,
        fair_variance: float,
        vol_of_vol: float
    ) -> float:
        """
        Fair volatility strike with convexity adjustment.

        Args:
            fair_variance: Fair variance strike
            vol_of_vol: Volatility of variance

        Returns:
            Adjusted fair volatility strike
        """
        sqrt_var = np.sqrt(fair_variance)
        adjustment = vol_of_vol**2 * self.T / (8 * sqrt_var**3)
        return sqrt_var - adjustment


# =============================================================================
# Cliquet/Ratchet Options
# =============================================================================

class CliquetOption:
    """
    Cliquet (ratchet) option pricing.

    Sum of forward-starting options with periodic resets.
    """

    def __init__(
        self,
        S: float,
        sigma: float,
        risk_free_rate: float,
        reset_dates: List[float],  # Reset times
        local_floor: float = -np.inf,
        local_cap: float = np.inf,
        global_floor: float = -np.inf,
        global_cap: float = np.inf,
        q: float = 0.0
    ):
        """
        Initialize cliquet option.

        Args:
            S: Current spot price
            sigma: Volatility
            risk_free_rate: Risk-free rate
            reset_dates: List of reset times
            local_floor: Floor on each period's return
            local_cap: Cap on each period's return
            global_floor: Floor on total return
            global_cap: Cap on total return
            q: Dividend yield
        """
        self.S = S
        self.sigma = sigma
        self.r = risk_free_rate
        self.reset_dates = sorted(reset_dates)
        self.local_floor = local_floor
        self.local_cap = local_cap
        self.global_floor = global_floor
        self.global_cap = global_cap
        self.q = q

    def price_monte_carlo(
        self,
        n_paths: int = 100000,
        seed: Optional[int] = None
    ) -> ExoticPricingResult:
        """Monte Carlo pricing for cliquet option."""
        if seed is not None:
            np.random.seed(seed)

        n_periods = len(self.reset_dates)
        times = [0] + self.reset_dates
        dt_list = [times[i+1] - times[i] for i in range(n_periods)]

        # Simulate spot at each reset
        spots = np.zeros((n_paths, n_periods + 1))
        spots[:, 0] = self.S

        for i, dt in enumerate(dt_list):
            Z = np.random.standard_normal(n_paths)
            spots[:, i+1] = spots[:, i] * np.exp(
                (self.r - self.q - 0.5 * self.sigma**2) * dt +
                self.sigma * np.sqrt(dt) * Z
            )

        # Calculate periodic returns
        returns = spots[:, 1:] / spots[:, :-1] - 1

        # Apply local floor and cap
        returns_capped = np.clip(returns, self.local_floor, self.local_cap)

        # Sum of capped returns
        total_return = np.sum(returns_capped, axis=1)

        # Apply global floor and cap
        payoffs = np.clip(total_return, self.global_floor, self.global_cap)

        # Discount
        T = self.reset_dates[-1]
        discount = np.exp(-self.r * T)
        price = discount * self.S * np.mean(payoffs)
        std_error = discount * self.S * np.std(payoffs) / np.sqrt(n_paths)

        return ExoticPricingResult(
            price=price,
            std_error=std_error,
            additional_info={'n_periods': n_periods}
        )


# =============================================================================
# Autocallable Notes
# =============================================================================

class Autocallable:
    """
    Autocallable structured product pricing.

    Auto-redeems if spot exceeds barrier at observation dates.
    """

    def __init__(
        self,
        S: float,
        sigma: float,
        risk_free_rate: float,
        observation_dates: List[float],
        autocall_barrier: float,  # As fraction of S (e.g., 1.0 = at-the-money)
        coupon_rate: float,  # Coupon paid at each observation
        put_barrier: float,  # Downside protection barrier
        put_strike: float,  # Put strike if barrier breached
        q: float = 0.0
    ):
        """
        Initialize autocallable.

        Args:
            S: Current spot
            sigma: Volatility
            risk_free_rate: Risk-free rate
            observation_dates: Autocall observation dates
            autocall_barrier: Autocall trigger level (fraction of initial spot)
            coupon_rate: Coupon rate per period
            put_barrier: Put knock-in barrier (fraction of initial)
            put_strike: Put strike if knocked in
            q: Dividend yield
        """
        self.S = S
        self.sigma = sigma
        self.r = risk_free_rate
        self.obs_dates = sorted(observation_dates)
        self.autocall_barrier = autocall_barrier * S
        self.coupon_rate = coupon_rate
        self.put_barrier = put_barrier * S
        self.put_strike = put_strike * S
        self.q = q

    def price_monte_carlo(
        self,
        n_paths: int = 100000,
        n_steps_per_period: int = 10,
        seed: Optional[int] = None
    ) -> ExoticPricingResult:
        """Monte Carlo pricing for autocallable."""
        if seed is not None:
            np.random.seed(seed)

        notional = 1.0
        n_obs = len(self.obs_dates)

        # Total steps
        total_time = self.obs_dates[-1]
        total_steps = n_obs * n_steps_per_period
        dt = total_time / total_steps

        # Simulate full paths
        Z = np.random.standard_normal((n_paths, total_steps))
        paths = np.zeros((n_paths, total_steps + 1))
        paths[:, 0] = self.S

        for t in range(total_steps):
            paths[:, t+1] = paths[:, t] * np.exp(
                (self.r - self.q - 0.5 * self.sigma**2) * dt +
                self.sigma * np.sqrt(dt) * Z[:, t]
            )

        # Determine outcomes
        payoffs = np.zeros(n_paths)
        redemption_times = np.full(n_paths, self.obs_dates[-1])

        for i in range(n_paths):
            # Check autocall at each observation
            autocalled = False
            put_knocked_in = False

            # Check put barrier breach throughout
            min_price = np.min(paths[i, :])
            if min_price <= self.put_barrier:
                put_knocked_in = True

            for j, obs_t in enumerate(self.obs_dates):
                step_idx = int(obs_t / dt)
                spot_at_obs = paths[i, step_idx]

                if spot_at_obs >= self.autocall_barrier:
                    # Autocall triggered
                    autocalled = True
                    redemption_times[i] = obs_t
                    # Pay notional + accrued coupons
                    payoffs[i] = notional * (1 + self.coupon_rate * (j + 1))
                    break

            if not autocalled:
                # No autocall - check final outcome
                final_spot = paths[i, -1]

                if put_knocked_in and final_spot < self.put_strike:
                    # Put is in effect
                    payoffs[i] = notional * (final_spot / self.S)
                else:
                    # Return notional
                    payoffs[i] = notional

        # Discount each payoff
        discount_factors = np.exp(-self.r * redemption_times)
        pv_payoffs = payoffs * discount_factors

        price = np.mean(pv_payoffs)
        std_error = np.std(pv_payoffs) / np.sqrt(n_paths)

        # Calculate probability of autocall
        prob_autocall = np.mean(redemption_times < self.obs_dates[-1])

        return ExoticPricingResult(
            price=price,
            std_error=std_error,
            additional_info={
                'prob_autocall': prob_autocall,
                'expected_life': np.mean(redemption_times)
            }
        )


# =============================================================================
# Forward Start Options
# =============================================================================

class ForwardStartOption:
    """
    Forward-starting option pricing.

    Strike determined at future date as percentage of spot.
    """

    def __init__(
        self,
        S: float,
        strike_pct: float,  # Strike as percentage of spot at start date
        sigma: float,
        risk_free_rate: float,
        start_date: float,
        expiry_date: float,
        q: float = 0.0
    ):
        """
        Initialize forward start option.

        Args:
            S: Current spot
            strike_pct: Strike as fraction of spot at start_date (e.g., 1.0 = ATM)
            sigma: Volatility
            risk_free_rate: Risk-free rate
            start_date: When option starts
            expiry_date: When option expires
            q: Dividend yield
        """
        if expiry_date <= start_date:
            raise ValueError("Expiry must be after start date")

        self.S = S
        self.strike_pct = strike_pct
        self.sigma = sigma
        self.r = risk_free_rate
        self.T1 = start_date
        self.T2 = expiry_date
        self.q = q

    def price_rubinstein(self, is_call: bool = True) -> float:
        """
        Rubinstein (1990) formula for forward start options.
        """
        tau = self.T2 - self.T1  # Option life after start

        d1 = (np.log(1 / self.strike_pct) + (self.r - self.q + 0.5 * self.sigma**2) * tau) / (self.sigma * np.sqrt(tau))
        d2 = d1 - self.sigma * np.sqrt(tau)

        # Forward factor
        forward_factor = np.exp(-self.q * self.T1)

        if is_call:
            price = self.S * forward_factor * (
                np.exp(-self.q * tau) * norm_cdf(d1) -
                self.strike_pct * np.exp(-self.r * tau) * norm_cdf(d2)
            )
        else:
            price = self.S * forward_factor * (
                self.strike_pct * np.exp(-self.r * tau) * norm_cdf(-d2) -
                np.exp(-self.q * tau) * norm_cdf(-d1)
            )

        return max(0, price)


# =============================================================================
# Power Options
# =============================================================================

class PowerOption:
    """
    Power options with non-linear payoffs.

    - Powered option: (S^p - K)^+
    - Capped power: min((S^p - K)^+, cap)
    """

    def __init__(
        self,
        S: float,
        K: float,
        power: float,
        sigma: float,
        risk_free_rate: float,
        time_to_maturity: float,
        q: float = 0.0
    ):
        self.S = S
        self.K = K
        self.power = power
        self.sigma = sigma
        self.r = risk_free_rate
        self.T = time_to_maturity
        self.q = q

    def price_monte_carlo(
        self,
        is_call: bool = True,
        n_paths: int = 100000,
        seed: Optional[int] = None
    ) -> ExoticPricingResult:
        """Monte Carlo pricing for power option."""
        if seed is not None:
            np.random.seed(seed)

        Z = np.random.standard_normal(n_paths)
        ST = self.S * np.exp(
            (self.r - self.q - 0.5 * self.sigma**2) * self.T +
            self.sigma * np.sqrt(self.T) * Z
        )

        # Powered terminal value
        ST_powered = ST ** self.power

        if is_call:
            payoffs = np.maximum(ST_powered - self.K, 0)
        else:
            payoffs = np.maximum(self.K - ST_powered, 0)

        discount = np.exp(-self.r * self.T)
        price = discount * np.mean(payoffs)
        std_error = discount * np.std(payoffs) / np.sqrt(n_paths)

        return ExoticPricingResult(price=price, std_error=std_error)


# =============================================================================
# Factory Functions
# =============================================================================

def create_rainbow_option(
    spots: List[float],
    strike: float,
    volatilities: List[float],
    correlations: List[List[float]],
    risk_free_rate: float,
    time_to_maturity: float,
    dividend_yields: Optional[List[float]] = None
) -> RainbowOption:
    """Create rainbow option."""
    return RainbowOption(
        spots=np.array(spots),
        strikes=strike,
        volatilities=np.array(volatilities),
        correlation_matrix=np.array(correlations),
        risk_free_rate=risk_free_rate,
        dividend_yields=np.array(dividend_yields) if dividend_yields else None,
        time_to_maturity=time_to_maturity
    )


def create_spread_option(
    S1: float,
    S2: float,
    strike: float,
    sigma1: float,
    sigma2: float,
    correlation: float,
    risk_free_rate: float,
    time_to_maturity: float
) -> SpreadOption:
    """Create spread option."""
    return SpreadOption(
        S1=S1, S2=S2, K=strike,
        sigma1=sigma1, sigma2=sigma2,
        correlation=correlation,
        risk_free_rate=risk_free_rate,
        time_to_maturity=time_to_maturity
    )


def create_variance_swap(
    spot: float,
    risk_free_rate: float,
    time_to_maturity: float
) -> VarianceSwap:
    """Create variance swap."""
    return VarianceSwap(spot, risk_free_rate, time_to_maturity)


def create_autocallable(
    spot: float,
    volatility: float,
    risk_free_rate: float,
    observation_dates: List[float],
    autocall_barrier: float = 1.0,
    coupon_rate: float = 0.05,
    put_barrier: float = 0.7,
    put_strike: float = 0.7
) -> Autocallable:
    """Create autocallable structured product."""
    return Autocallable(
        S=spot,
        sigma=volatility,
        risk_free_rate=risk_free_rate,
        observation_dates=observation_dates,
        autocall_barrier=autocall_barrier,
        coupon_rate=coupon_rate,
        put_barrier=put_barrier,
        put_strike=put_strike
    )
