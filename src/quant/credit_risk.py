"""
Revolution Alpha Engine - Credit Risk, VaR & XVA Module

Institutional-grade credit risk and market risk implementations:
- Value at Risk (VaR): Historical, Parametric, Monte Carlo
- Expected Shortfall (CVaR/ES)
- Credit Risk Models: Merton Structural, Reduced-Form
- Credit Default Swap (CDS) Pricing
- XVA Framework: CVA, DVA, FVA, MVA, KVA
- Credit Portfolio Models: Vasicek, CreditMetrics
- Probability of Default (PD) Estimation
- Loss Given Default (LGD) Modeling
"""

import numpy as np
from scipy import stats, optimize
from scipy.interpolate import interp1d
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Callable, Union
from enum import Enum
from abc import ABC, abstractmethod
import warnings


# =============================================================================
# Value at Risk (VaR) Models
# =============================================================================

class VaRMethod(Enum):
    """VaR calculation methods."""
    HISTORICAL = "historical"
    PARAMETRIC = "parametric"
    MONTE_CARLO = "monte_carlo"
    CORNISH_FISHER = "cornish_fisher"
    EWMA = "ewma"
    GARCH = "garch"


@dataclass
class VaRResult:
    """Value at Risk calculation result."""
    var: float
    confidence_level: float
    method: VaRMethod
    expected_shortfall: Optional[float] = None
    marginal_var: Optional[np.ndarray] = None
    component_var: Optional[np.ndarray] = None
    incremental_var: Optional[np.ndarray] = None


class ValueAtRisk:
    """
    Comprehensive Value at Risk calculator.

    Implements multiple VaR methodologies:
    - Historical simulation
    - Parametric (variance-covariance)
    - Monte Carlo simulation
    - Cornish-Fisher expansion (for non-normal returns)
    - EWMA volatility
    """

    def __init__(self, confidence_level: float = 0.99):
        """
        Initialize VaR calculator.

        Args:
            confidence_level: Confidence level (e.g., 0.95, 0.99)
        """
        self.confidence_level = confidence_level

    def historical_var(
        self,
        returns: np.ndarray,
        portfolio_value: float = 1.0,
        holding_period: int = 1
    ) -> VaRResult:
        """
        Calculate VaR using historical simulation.

        Args:
            returns: Historical returns array
            portfolio_value: Current portfolio value
            holding_period: Holding period in days

        Returns:
            VaRResult with historical VaR
        """
        if holding_period > 1:
            # Aggregate returns over holding period
            n_periods = len(returns) // holding_period
            aggregated = np.array([
                np.sum(returns[i*holding_period:(i+1)*holding_period])
                for i in range(n_periods)
            ])
            returns = aggregated

        # Calculate VaR as percentile
        alpha = 1 - self.confidence_level
        var_pct = np.percentile(returns, alpha * 100)
        var = -var_pct * portfolio_value

        # Expected Shortfall (average of losses beyond VaR)
        es_returns = returns[returns <= var_pct]
        es = -np.mean(es_returns) * portfolio_value if len(es_returns) > 0 else var

        return VaRResult(
            var=var,
            confidence_level=self.confidence_level,
            method=VaRMethod.HISTORICAL,
            expected_shortfall=es
        )

    def parametric_var(
        self,
        returns: np.ndarray,
        portfolio_value: float = 1.0,
        holding_period: int = 1
    ) -> VaRResult:
        """
        Calculate VaR using parametric (variance-covariance) method.

        Assumes returns are normally distributed.

        Args:
            returns: Historical returns array
            portfolio_value: Current portfolio value
            holding_period: Holding period in days

        Returns:
            VaRResult with parametric VaR
        """
        mu = np.mean(returns)
        sigma = np.std(returns, ddof=1)

        # Scale for holding period (square root of time)
        mu_scaled = mu * holding_period
        sigma_scaled = sigma * np.sqrt(holding_period)

        # VaR using inverse normal CDF
        alpha = 1 - self.confidence_level
        z_alpha = stats.norm.ppf(alpha)
        var = -(mu_scaled + z_alpha * sigma_scaled) * portfolio_value

        # Expected Shortfall for normal distribution
        es_multiplier = stats.norm.pdf(z_alpha) / alpha
        es = -(mu_scaled - es_multiplier * sigma_scaled) * portfolio_value

        return VaRResult(
            var=var,
            confidence_level=self.confidence_level,
            method=VaRMethod.PARAMETRIC,
            expected_shortfall=es
        )

    def monte_carlo_var(
        self,
        returns: np.ndarray,
        portfolio_value: float = 1.0,
        holding_period: int = 1,
        n_simulations: int = 100000,
        use_garch: bool = False
    ) -> VaRResult:
        """
        Calculate VaR using Monte Carlo simulation.

        Args:
            returns: Historical returns array
            portfolio_value: Current portfolio value
            holding_period: Holding period in days
            n_simulations: Number of Monte Carlo simulations
            use_garch: Whether to use GARCH for volatility dynamics

        Returns:
            VaRResult with Monte Carlo VaR
        """
        mu = np.mean(returns)
        sigma = np.std(returns, ddof=1)

        if use_garch:
            # Simple GARCH(1,1) estimation
            omega, alpha, beta = self._fit_garch(returns)
            current_var = returns[-1]**2

            # Simulate GARCH paths
            simulated_returns = np.zeros((n_simulations, holding_period))
            variances = np.zeros((n_simulations, holding_period))
            variances[:, 0] = omega + alpha * current_var + beta * sigma**2

            for t in range(holding_period):
                z = np.random.standard_normal(n_simulations)
                simulated_returns[:, t] = mu + np.sqrt(variances[:, t]) * z
                if t < holding_period - 1:
                    variances[:, t+1] = (omega +
                                         alpha * simulated_returns[:, t]**2 +
                                         beta * variances[:, t])

            total_returns = np.sum(simulated_returns, axis=1)
        else:
            # Simple simulation assuming normal distribution
            simulated = np.random.normal(
                mu * holding_period,
                sigma * np.sqrt(holding_period),
                n_simulations
            )
            total_returns = simulated

        # Calculate VaR from simulated distribution
        alpha = 1 - self.confidence_level
        var_pct = np.percentile(total_returns, alpha * 100)
        var = -var_pct * portfolio_value

        # Expected Shortfall
        es_returns = total_returns[total_returns <= var_pct]
        es = -np.mean(es_returns) * portfolio_value

        return VaRResult(
            var=var,
            confidence_level=self.confidence_level,
            method=VaRMethod.MONTE_CARLO,
            expected_shortfall=es
        )

    def cornish_fisher_var(
        self,
        returns: np.ndarray,
        portfolio_value: float = 1.0,
        holding_period: int = 1
    ) -> VaRResult:
        """
        Calculate VaR using Cornish-Fisher expansion.

        Accounts for skewness and kurtosis in returns distribution.

        Args:
            returns: Historical returns array
            portfolio_value: Current portfolio value
            holding_period: Holding period in days

        Returns:
            VaRResult with Cornish-Fisher adjusted VaR
        """
        mu = np.mean(returns)
        sigma = np.std(returns, ddof=1)
        skew = stats.skew(returns)
        kurt = stats.kurtosis(returns)  # Excess kurtosis

        # Scale for holding period
        mu_scaled = mu * holding_period
        sigma_scaled = sigma * np.sqrt(holding_period)

        # Cornish-Fisher expansion
        alpha = 1 - self.confidence_level
        z = stats.norm.ppf(alpha)

        # Cornish-Fisher adjusted quantile
        z_cf = (z +
                (z**2 - 1) * skew / 6 +
                (z**3 - 3*z) * kurt / 24 -
                (2*z**3 - 5*z) * skew**2 / 36)

        var = -(mu_scaled + z_cf * sigma_scaled) * portfolio_value

        # Approximate ES using numerical integration
        def cf_quantile(p):
            z = stats.norm.ppf(p)
            return (z +
                    (z**2 - 1) * skew / 6 +
                    (z**3 - 3*z) * kurt / 24 -
                    (2*z**3 - 5*z) * skew**2 / 36)

        # Numerical integration for ES
        p_values = np.linspace(0.0001, alpha, 100)
        quantiles = [cf_quantile(p) for p in p_values]
        es_quantile = np.mean(quantiles)
        es = -(mu_scaled + es_quantile * sigma_scaled) * portfolio_value

        return VaRResult(
            var=var,
            confidence_level=self.confidence_level,
            method=VaRMethod.CORNISH_FISHER,
            expected_shortfall=es
        )

    def ewma_var(
        self,
        returns: np.ndarray,
        portfolio_value: float = 1.0,
        holding_period: int = 1,
        decay_factor: float = 0.94
    ) -> VaRResult:
        """
        Calculate VaR using EWMA (Exponentially Weighted Moving Average) volatility.

        RiskMetrics methodology with lambda = 0.94 for daily data.

        Args:
            returns: Historical returns array
            portfolio_value: Current portfolio value
            holding_period: Holding period in days
            decay_factor: EWMA decay factor (lambda)

        Returns:
            VaRResult with EWMA VaR
        """
        # Calculate EWMA variance
        weights = np.array([(1 - decay_factor) * decay_factor**i
                          for i in range(len(returns))])[::-1]
        weights = weights / np.sum(weights)

        mu = np.mean(returns)
        ewma_var = np.sum(weights * (returns - mu)**2)
        ewma_vol = np.sqrt(ewma_var)

        # Scale for holding period
        mu_scaled = mu * holding_period
        sigma_scaled = ewma_vol * np.sqrt(holding_period)

        # VaR calculation
        alpha = 1 - self.confidence_level
        z_alpha = stats.norm.ppf(alpha)
        var = -(mu_scaled + z_alpha * sigma_scaled) * portfolio_value

        # Expected Shortfall
        es_multiplier = stats.norm.pdf(z_alpha) / alpha
        es = -(mu_scaled - es_multiplier * sigma_scaled) * portfolio_value

        return VaRResult(
            var=var,
            confidence_level=self.confidence_level,
            method=VaRMethod.EWMA,
            expected_shortfall=es
        )

    def portfolio_var(
        self,
        returns_matrix: np.ndarray,
        weights: np.ndarray,
        portfolio_value: float = 1.0,
        method: VaRMethod = VaRMethod.PARAMETRIC
    ) -> VaRResult:
        """
        Calculate portfolio VaR with component and marginal VaR.

        Args:
            returns_matrix: Returns matrix (n_obs x n_assets)
            weights: Portfolio weights
            portfolio_value: Current portfolio value
            method: VaR calculation method

        Returns:
            VaRResult with portfolio VaR and risk decomposition
        """
        weights = np.array(weights)

        # Portfolio returns
        portfolio_returns = returns_matrix @ weights

        # Calculate portfolio VaR
        if method == VaRMethod.HISTORICAL:
            result = self.historical_var(portfolio_returns, portfolio_value)
        elif method == VaRMethod.PARAMETRIC:
            result = self.parametric_var(portfolio_returns, portfolio_value)
        else:
            result = self.monte_carlo_var(portfolio_returns, portfolio_value)

        # Covariance matrix
        cov_matrix = np.cov(returns_matrix, rowvar=False)
        portfolio_vol = np.sqrt(weights @ cov_matrix @ weights)

        # Marginal VaR: derivative of VaR w.r.t. weights
        alpha = 1 - self.confidence_level
        z_alpha = -stats.norm.ppf(alpha)
        marginal_var = z_alpha * (cov_matrix @ weights) / portfolio_vol * portfolio_value

        # Component VaR: weight * marginal VaR
        component_var = weights * marginal_var

        result.marginal_var = marginal_var
        result.component_var = component_var

        return result

    def _fit_garch(
        self,
        returns: np.ndarray,
        p: int = 1,
        q: int = 1
    ) -> Tuple[float, float, float]:
        """
        Fit GARCH(p,q) model using MLE.

        Returns omega, alpha, beta parameters.
        """
        def neg_log_likelihood(params):
            omega, alpha, beta = params
            if omega <= 0 or alpha < 0 or beta < 0 or alpha + beta >= 1:
                return 1e10

            n = len(returns)
            sigma2 = np.zeros(n)
            sigma2[0] = np.var(returns)

            for t in range(1, n):
                sigma2[t] = omega + alpha * returns[t-1]**2 + beta * sigma2[t-1]

            # Log-likelihood
            ll = -0.5 * np.sum(np.log(2 * np.pi * sigma2) + returns**2 / sigma2)
            return -ll

        # Initial guess
        var_init = np.var(returns)
        x0 = [var_init * 0.1, 0.1, 0.85]

        # Optimize
        result = optimize.minimize(
            neg_log_likelihood,
            x0,
            method='Nelder-Mead',
            options={'maxiter': 1000}
        )

        return result.x


class ExpectedShortfall:
    """
    Expected Shortfall (CVaR) calculator.

    ES is a coherent risk measure that captures tail risk
    better than VaR.
    """

    def __init__(self, confidence_level: float = 0.99):
        self.confidence_level = confidence_level

    def calculate(
        self,
        returns: np.ndarray,
        portfolio_value: float = 1.0
    ) -> float:
        """Calculate Expected Shortfall."""
        alpha = 1 - self.confidence_level
        var_threshold = np.percentile(returns, alpha * 100)
        tail_returns = returns[returns <= var_threshold]

        if len(tail_returns) == 0:
            return -var_threshold * portfolio_value

        return -np.mean(tail_returns) * portfolio_value

    def parametric(
        self,
        mu: float,
        sigma: float,
        portfolio_value: float = 1.0
    ) -> float:
        """Calculate parametric ES assuming normality."""
        alpha = 1 - self.confidence_level
        z_alpha = stats.norm.ppf(alpha)
        es_multiplier = stats.norm.pdf(z_alpha) / alpha
        return (es_multiplier * sigma - mu) * portfolio_value


# =============================================================================
# Credit Risk Models
# =============================================================================

@dataclass
class CreditRiskMetrics:
    """Credit risk metrics container."""
    probability_of_default: float
    loss_given_default: float
    exposure_at_default: float
    expected_loss: float
    unexpected_loss: float
    credit_var: float
    distance_to_default: Optional[float] = None
    credit_spread: Optional[float] = None


class MertonModel:
    """
    Merton Structural Credit Risk Model.

    Models firm's equity as a call option on its assets,
    with default occurring when asset value falls below debt.
    """

    def __init__(
        self,
        asset_value: float,
        debt_face_value: float,
        asset_volatility: float,
        risk_free_rate: float,
        maturity: float = 1.0
    ):
        """
        Initialize Merton model.

        Args:
            asset_value: Current firm asset value
            debt_face_value: Face value of debt (default barrier)
            asset_volatility: Annualized asset volatility
            risk_free_rate: Risk-free interest rate
            maturity: Time to maturity of debt in years
        """
        self.V = asset_value
        self.D = debt_face_value
        self.sigma_V = asset_volatility
        self.r = risk_free_rate
        self.T = maturity

    def distance_to_default(self) -> float:
        """
        Calculate distance to default (DD).

        DD = (ln(V/D) + (r - 0.5*sigma^2)*T) / (sigma * sqrt(T))
        """
        numerator = (np.log(self.V / self.D) +
                    (self.r - 0.5 * self.sigma_V**2) * self.T)
        denominator = self.sigma_V * np.sqrt(self.T)
        return numerator / denominator

    def probability_of_default(self) -> float:
        """
        Calculate probability of default under risk-neutral measure.

        PD = N(-DD)
        """
        dd = self.distance_to_default()
        return stats.norm.cdf(-dd)

    def physical_probability_of_default(
        self,
        asset_drift: float
    ) -> float:
        """
        Calculate probability of default under physical measure.

        Uses actual asset drift instead of risk-free rate.
        """
        numerator = (np.log(self.V / self.D) +
                    (asset_drift - 0.5 * self.sigma_V**2) * self.T)
        denominator = self.sigma_V * np.sqrt(self.T)
        dd_physical = numerator / denominator
        return stats.norm.cdf(-dd_physical)

    def equity_value(self) -> float:
        """
        Calculate equity value as call option on assets.

        E = V*N(d1) - D*exp(-r*T)*N(d2)
        """
        dd = self.distance_to_default()
        d1 = dd + self.sigma_V * np.sqrt(self.T)
        d2 = dd

        equity = (self.V * stats.norm.cdf(d1) -
                 self.D * np.exp(-self.r * self.T) * stats.norm.cdf(d2))
        return equity

    def debt_value(self) -> float:
        """Calculate risky debt value."""
        return self.V - self.equity_value()

    def credit_spread(self) -> float:
        """
        Calculate credit spread over risk-free rate.

        spread = -ln(D_risky / D_riskfree) / T
        """
        debt_risky = self.debt_value()
        debt_riskfree = self.D * np.exp(-self.r * self.T)

        if debt_risky <= 0:
            return np.inf

        return -np.log(debt_risky / debt_riskfree) / self.T

    def expected_loss_given_default(self) -> float:
        """Calculate expected loss given default (LGD)."""
        pd = self.probability_of_default()
        if pd < 1e-10:
            return 0.0

        # Expected asset value given default
        dd = self.distance_to_default()
        d1 = dd + self.sigma_V * np.sqrt(self.T)

        # E[V | V < D] using truncated normal
        expected_V_given_default = (
            self.V * np.exp(self.r * self.T) *
            stats.norm.cdf(-d1) / stats.norm.cdf(-dd)
        )

        lgd = 1 - expected_V_given_default / self.D
        return max(0, min(1, lgd))

    def calibrate_from_equity(
        self,
        equity_value: float,
        equity_volatility: float
    ) -> Tuple[float, float]:
        """
        Calibrate asset value and volatility from observable equity data.

        Uses iterative procedure solving:
        1. E = V*N(d1) - D*exp(-r*T)*N(d2)
        2. sigma_E * E = N(d1) * sigma_V * V

        Returns:
            Tuple of (asset_value, asset_volatility)
        """
        def equations(params):
            V, sigma_V = params
            if V <= 0 or sigma_V <= 0:
                return [1e10, 1e10]

            d1 = (np.log(V / self.D) +
                  (self.r + 0.5 * sigma_V**2) * self.T) / (sigma_V * np.sqrt(self.T))
            d2 = d1 - sigma_V * np.sqrt(self.T)

            # Equity value equation
            E_calc = V * stats.norm.cdf(d1) - self.D * np.exp(-self.r * self.T) * stats.norm.cdf(d2)
            eq1 = E_calc - equity_value

            # Equity volatility equation
            sigma_E_calc = stats.norm.cdf(d1) * sigma_V * V / equity_value
            eq2 = sigma_E_calc - equity_volatility

            return [eq1, eq2]

        # Initial guess
        V0 = equity_value + self.D * np.exp(-self.r * self.T)
        sigma_V0 = equity_volatility * equity_value / V0

        solution = optimize.fsolve(equations, [V0, sigma_V0], full_output=True)
        V_calibrated, sigma_V_calibrated = solution[0]

        self.V = V_calibrated
        self.sigma_V = sigma_V_calibrated

        return V_calibrated, sigma_V_calibrated


class ReducedFormModel:
    """
    Reduced-Form (Intensity-Based) Credit Model.

    Models default as the first jump of a Poisson process
    with stochastic intensity (hazard rate).
    """

    def __init__(
        self,
        hazard_rate: Union[float, Callable],
        recovery_rate: float = 0.4,
        risk_free_rate: float = 0.05
    ):
        """
        Initialize reduced-form model.

        Args:
            hazard_rate: Constant hazard rate or callable h(t)
            recovery_rate: Expected recovery rate (1 - LGD)
            risk_free_rate: Risk-free interest rate
        """
        if callable(hazard_rate):
            self.hazard_rate = hazard_rate
        else:
            self.hazard_rate = lambda t: hazard_rate

        self.recovery_rate = recovery_rate
        self.r = risk_free_rate

    def survival_probability(self, t: float, n_steps: int = 100) -> float:
        """
        Calculate survival probability to time t.

        Q(t) = exp(-integral_0^t h(s) ds)
        """
        if t <= 0:
            return 1.0

        # Numerical integration
        dt = t / n_steps
        integral = sum(self.hazard_rate(i * dt) * dt for i in range(n_steps))
        return np.exp(-integral)

    def default_probability(self, t: float) -> float:
        """Calculate cumulative default probability to time t."""
        return 1 - self.survival_probability(t)

    def marginal_default_probability(
        self,
        t1: float,
        t2: float
    ) -> float:
        """Calculate default probability between t1 and t2."""
        return self.survival_probability(t1) - self.survival_probability(t2)

    def risky_bond_price(
        self,
        face_value: float,
        maturity: float,
        coupon_rate: float = 0.0,
        coupon_frequency: int = 2
    ) -> float:
        """
        Price a risky zero-coupon or coupon bond.

        Args:
            face_value: Bond face value
            maturity: Time to maturity
            coupon_rate: Annual coupon rate
            coupon_frequency: Coupons per year

        Returns:
            Bond price
        """
        price = 0.0

        if coupon_rate > 0:
            # Coupon payments
            coupon_payment = face_value * coupon_rate / coupon_frequency
            coupon_times = np.arange(
                1/coupon_frequency, maturity + 1/coupon_frequency, 1/coupon_frequency
            )

            for t in coupon_times:
                if t <= maturity:
                    # Discounted expected coupon
                    discount = np.exp(-self.r * t)
                    survival = self.survival_probability(t)
                    price += coupon_payment * discount * survival

        # Principal payment at maturity
        discount = np.exp(-self.r * maturity)
        survival = self.survival_probability(maturity)
        price += face_value * discount * survival

        # Recovery value (expected recovery if default)
        # Simplified: recovery at maturity if default
        default_prob = 1 - survival
        price += face_value * self.recovery_rate * discount * default_prob

        return price

    def credit_spread(self, maturity: float) -> float:
        """
        Calculate credit spread for given maturity.

        spread ≈ (1 - R) * h for constant hazard rate
        """
        if callable(self.hazard_rate):
            # Average hazard rate
            n_steps = 100
            dt = maturity / n_steps
            avg_h = sum(self.hazard_rate(i * dt) for i in range(n_steps)) / n_steps
        else:
            avg_h = self.hazard_rate(0)

        return (1 - self.recovery_rate) * avg_h


# =============================================================================
# Credit Default Swap (CDS) Pricing
# =============================================================================

@dataclass
class CDSContract:
    """Credit Default Swap contract specification."""
    notional: float
    spread: float  # Annual spread in decimal
    maturity: float  # Years
    recovery_rate: float = 0.4
    payment_frequency: int = 4  # Quarterly


class CDSPricer:
    """
    Credit Default Swap pricer using reduced-form model.
    """

    def __init__(
        self,
        hazard_rate: Union[float, Callable],
        risk_free_curve: Optional[Callable] = None
    ):
        """
        Initialize CDS pricer.

        Args:
            hazard_rate: Hazard rate function h(t) or constant
            risk_free_curve: Risk-free discount curve D(t) or constant rate
        """
        if callable(hazard_rate):
            self.hazard_rate = hazard_rate
        else:
            self.hazard_rate = lambda t: hazard_rate

        if risk_free_curve is None:
            self.discount = lambda t: np.exp(-0.05 * t)
        elif callable(risk_free_curve):
            self.discount = risk_free_curve
        else:
            self.discount = lambda t: np.exp(-risk_free_curve * t)

    def survival_probability(self, t: float, n_steps: int = 100) -> float:
        """Calculate survival probability to time t."""
        if t <= 0:
            return 1.0
        dt = t / n_steps
        integral = sum(self.hazard_rate(i * dt) * dt for i in range(n_steps))
        return np.exp(-integral)

    def premium_leg_pv(self, contract: CDSContract) -> float:
        """
        Calculate present value of premium leg.

        PV_premium = S * sum_i(Delta_i * D(t_i) * Q(t_i))
        where S is spread, Delta_i is day count fraction
        """
        payment_times = np.arange(
            1/contract.payment_frequency,
            contract.maturity + 1/contract.payment_frequency,
            1/contract.payment_frequency
        )

        pv = 0.0
        delta = 1 / contract.payment_frequency

        for t in payment_times:
            if t <= contract.maturity:
                pv += delta * self.discount(t) * self.survival_probability(t)

        return contract.spread * contract.notional * pv

    def protection_leg_pv(self, contract: CDSContract) -> float:
        """
        Calculate present value of protection leg.

        PV_protection = (1-R) * integral_0^T D(t) * h(t) * Q(t) dt
        """
        n_steps = int(contract.maturity * 100)
        dt = contract.maturity / n_steps

        pv = 0.0
        for i in range(n_steps):
            t = (i + 0.5) * dt
            h_t = self.hazard_rate(t)
            Q_t = self.survival_probability(t)
            D_t = self.discount(t)
            pv += h_t * Q_t * D_t * dt

        return (1 - contract.recovery_rate) * contract.notional * pv

    def price(self, contract: CDSContract) -> float:
        """
        Calculate CDS mark-to-market value.

        MTM = PV_protection - PV_premium (protection buyer's perspective)
        """
        return self.protection_leg_pv(contract) - self.premium_leg_pv(contract)

    def fair_spread(
        self,
        maturity: float,
        recovery_rate: float = 0.4,
        notional: float = 1e6
    ) -> float:
        """
        Calculate fair (par) CDS spread.

        Set PV_premium = PV_protection and solve for S.
        """
        contract = CDSContract(
            notional=notional,
            spread=0.01,  # Initial guess
            maturity=maturity,
            recovery_rate=recovery_rate
        )

        protection_pv = self.protection_leg_pv(contract)

        # Risky annuity (premium leg without spread)
        contract.spread = 1.0
        risky_annuity = self.premium_leg_pv(contract) / notional

        if risky_annuity < 1e-10:
            return np.inf

        return protection_pv / (notional * risky_annuity)

    def hazard_rate_from_spread(
        self,
        spread: float,
        recovery_rate: float = 0.4
    ) -> float:
        """
        Bootstrap constant hazard rate from CDS spread.

        h ≈ s / (1 - R) for flat hazard rate
        """
        return spread / (1 - recovery_rate)

    def dv01(self, contract: CDSContract) -> float:
        """
        Calculate spread DV01 (dollar value of 1 bp spread change).
        """
        bump = 0.0001  # 1 bp

        original_spread = contract.spread

        contract.spread = original_spread + bump
        price_up = self.price(contract)

        contract.spread = original_spread - bump
        price_down = self.price(contract)

        contract.spread = original_spread

        return (price_up - price_down) / 2


# =============================================================================
# XVA Framework
# =============================================================================

@dataclass
class XVAResult:
    """XVA calculation results."""
    cva: float  # Credit Value Adjustment
    dva: float  # Debit Value Adjustment
    fva: float  # Funding Value Adjustment
    mva: float  # Margin Value Adjustment
    kva: float  # Capital Value Adjustment
    total_xva: float
    bilateral_cva: float  # CVA - DVA


class XVACalculator:
    """
    Comprehensive XVA (X-Value Adjustment) calculator.

    Implements:
    - CVA: Credit Value Adjustment
    - DVA: Debit Value Adjustment
    - FVA: Funding Value Adjustment
    - MVA: Margin Value Adjustment
    - KVA: Capital Value Adjustment
    """

    def __init__(
        self,
        counterparty_hazard_rate: float,
        own_hazard_rate: float,
        counterparty_recovery: float = 0.4,
        own_recovery: float = 0.4,
        funding_spread: float = 0.01,
        risk_free_rate: float = 0.05
    ):
        """
        Initialize XVA calculator.

        Args:
            counterparty_hazard_rate: Counterparty default intensity
            own_hazard_rate: Own default intensity
            counterparty_recovery: Counterparty recovery rate
            own_recovery: Own recovery rate
            funding_spread: Funding spread over risk-free
            risk_free_rate: Risk-free rate
        """
        self.h_c = counterparty_hazard_rate
        self.h_b = own_hazard_rate
        self.R_c = counterparty_recovery
        self.R_b = own_recovery
        self.s_f = funding_spread
        self.r = risk_free_rate

    def calculate_cva(
        self,
        expected_positive_exposure: np.ndarray,
        time_grid: np.ndarray
    ) -> float:
        """
        Calculate Credit Value Adjustment (CVA).

        CVA = (1 - R_c) * integral_0^T D(t) * h_c * Q_c(t) * EPE(t) dt

        Args:
            expected_positive_exposure: EPE profile over time
            time_grid: Time points corresponding to EPE

        Returns:
            CVA value (always positive, subtracted from value)
        """
        cva = 0.0

        for i in range(len(time_grid) - 1):
            t = time_grid[i]
            dt = time_grid[i + 1] - time_grid[i]

            # Survival probability and discount factor
            Q_c = np.exp(-self.h_c * t)
            D_t = np.exp(-self.r * t)

            # EPE at this time
            EPE_t = expected_positive_exposure[i]

            cva += (1 - self.R_c) * D_t * self.h_c * Q_c * EPE_t * dt

        return cva

    def calculate_dva(
        self,
        expected_negative_exposure: np.ndarray,
        time_grid: np.ndarray
    ) -> float:
        """
        Calculate Debit Value Adjustment (DVA).

        DVA = (1 - R_b) * integral_0^T D(t) * h_b * Q_b(t) * ENE(t) dt

        Note: DVA is typically shown as positive (benefit to us)
        """
        dva = 0.0

        for i in range(len(time_grid) - 1):
            t = time_grid[i]
            dt = time_grid[i + 1] - time_grid[i]

            Q_b = np.exp(-self.h_b * t)
            D_t = np.exp(-self.r * t)
            ENE_t = expected_negative_exposure[i]

            dva += (1 - self.R_b) * D_t * self.h_b * Q_b * ENE_t * dt

        return dva

    def calculate_fva(
        self,
        expected_funding_exposure: np.ndarray,
        time_grid: np.ndarray
    ) -> float:
        """
        Calculate Funding Value Adjustment (FVA).

        FVA = integral_0^T D(t) * s_f * EFE(t) dt

        Where EFE is expected funding exposure.
        """
        fva = 0.0

        for i in range(len(time_grid) - 1):
            t = time_grid[i]
            dt = time_grid[i + 1] - time_grid[i]

            D_t = np.exp(-self.r * t)
            EFE_t = expected_funding_exposure[i]

            fva += D_t * self.s_f * EFE_t * dt

        return fva

    def calculate_mva(
        self,
        expected_margin: np.ndarray,
        time_grid: np.ndarray,
        margin_funding_spread: float = 0.005
    ) -> float:
        """
        Calculate Margin Value Adjustment (MVA).

        Cost of posting initial margin.
        """
        mva = 0.0

        for i in range(len(time_grid) - 1):
            t = time_grid[i]
            dt = time_grid[i + 1] - time_grid[i]

            D_t = np.exp(-self.r * t)
            margin_t = expected_margin[i]

            mva += D_t * margin_funding_spread * margin_t * dt

        return mva

    def calculate_kva(
        self,
        expected_capital: np.ndarray,
        time_grid: np.ndarray,
        hurdle_rate: float = 0.10
    ) -> float:
        """
        Calculate Capital Value Adjustment (KVA).

        Cost of holding regulatory capital.
        """
        kva = 0.0

        for i in range(len(time_grid) - 1):
            t = time_grid[i]
            dt = time_grid[i + 1] - time_grid[i]

            D_t = np.exp(-self.r * t)
            capital_t = expected_capital[i]

            # KVA as present value of capital costs above risk-free
            kva += D_t * (hurdle_rate - self.r) * capital_t * dt

        return max(0, kva)

    def calculate_all_xva(
        self,
        expected_positive_exposure: np.ndarray,
        expected_negative_exposure: np.ndarray,
        time_grid: np.ndarray,
        expected_margin: Optional[np.ndarray] = None,
        expected_capital: Optional[np.ndarray] = None
    ) -> XVAResult:
        """
        Calculate all XVA components.

        Args:
            expected_positive_exposure: EPE profile
            expected_negative_exposure: ENE profile (absolute values)
            time_grid: Time points
            expected_margin: Expected initial margin profile
            expected_capital: Expected regulatory capital profile

        Returns:
            XVAResult with all components
        """
        cva = self.calculate_cva(expected_positive_exposure, time_grid)
        dva = self.calculate_dva(expected_negative_exposure, time_grid)

        # FVA on net exposure (positive = we fund, negative = they fund)
        net_exposure = expected_positive_exposure - expected_negative_exposure
        fva = self.calculate_fva(net_exposure, time_grid)

        mva = 0.0
        if expected_margin is not None:
            mva = self.calculate_mva(expected_margin, time_grid)

        kva = 0.0
        if expected_capital is not None:
            kva = self.calculate_kva(expected_capital, time_grid)

        bilateral_cva = cva - dva
        total_xva = cva - dva + fva + mva + kva

        return XVAResult(
            cva=cva,
            dva=dva,
            fva=fva,
            mva=mva,
            kva=kva,
            total_xva=total_xva,
            bilateral_cva=bilateral_cva
        )


# =============================================================================
# Credit Portfolio Models
# =============================================================================

class VasicekPortfolioModel:
    """
    Vasicek (Asymptotic Single Risk Factor) Portfolio Model.

    Foundation of IRB approach in Basel II/III.
    Models portfolio loss distribution using a single systematic factor.
    """

    def __init__(
        self,
        probability_of_default: float,
        loss_given_default: float,
        asset_correlation: float
    ):
        """
        Initialize Vasicek model.

        Args:
            probability_of_default: Individual PD
            loss_given_default: Loss given default
            asset_correlation: Asset correlation (rho)
        """
        self.pd = probability_of_default
        self.lgd = loss_given_default
        self.rho = asset_correlation

    def conditional_pd(self, systematic_factor: float) -> float:
        """
        Calculate conditional PD given systematic factor.

        PD(Z) = N((N^{-1}(PD) - sqrt(rho)*Z) / sqrt(1-rho))
        """
        z_pd = stats.norm.ppf(self.pd)
        numerator = z_pd - np.sqrt(self.rho) * systematic_factor
        denominator = np.sqrt(1 - self.rho)
        return stats.norm.cdf(numerator / denominator)

    def loss_distribution_quantile(self, confidence: float) -> float:
        """
        Calculate loss distribution quantile.

        L(alpha) = LGD * N((N^{-1}(PD) + sqrt(rho)*N^{-1}(alpha)) / sqrt(1-rho))
        """
        z_pd = stats.norm.ppf(self.pd)
        z_alpha = stats.norm.ppf(confidence)

        numerator = z_pd + np.sqrt(self.rho) * z_alpha
        denominator = np.sqrt(1 - self.rho)

        return self.lgd * stats.norm.cdf(numerator / denominator)

    def expected_loss(self) -> float:
        """Calculate expected loss = PD * LGD."""
        return self.pd * self.lgd

    def unexpected_loss(self, confidence: float = 0.999) -> float:
        """Calculate unexpected loss at given confidence."""
        var = self.loss_distribution_quantile(confidence)
        el = self.expected_loss()
        return var - el

    def economic_capital(self, confidence: float = 0.999) -> float:
        """Calculate economic capital (same as unexpected loss)."""
        return self.unexpected_loss(confidence)

    def regulatory_capital_irb(
        self,
        maturity: float = 2.5,
        firm_size_adjustment: float = 0.0
    ) -> float:
        """
        Calculate Basel IRB regulatory capital.

        K = LGD * (N((N^{-1}(PD) + sqrt(rho)*N^{-1}(0.999))/(sqrt(1-rho))) - PD) * MA

        where MA is maturity adjustment.
        """
        # Correlation adjustment for firm size (Basel formula)
        rho_adjusted = self.rho * (1 - firm_size_adjustment)

        # Capital requirement before maturity adjustment
        z_pd = stats.norm.ppf(self.pd)
        z_999 = stats.norm.ppf(0.999)

        numerator = z_pd + np.sqrt(rho_adjusted) * z_999
        denominator = np.sqrt(1 - rho_adjusted)

        k_base = self.lgd * (stats.norm.cdf(numerator / denominator) - self.pd)

        # Maturity adjustment
        b = (0.11852 - 0.05478 * np.log(self.pd))**2
        ma = (1 + (maturity - 2.5) * b) / (1 - 1.5 * b)

        return k_base * ma


class CreditMetrics:
    """
    CreditMetrics-style credit portfolio model.

    Uses transition matrices and Monte Carlo simulation
    for portfolio credit risk.
    """

    # Standard transition matrix (investment grade simplified)
    DEFAULT_TRANSITION_MATRIX = np.array([
        [0.9081, 0.0833, 0.0068, 0.0006, 0.0012, 0.0000, 0.0000, 0.0000],  # AAA
        [0.0070, 0.9065, 0.0779, 0.0064, 0.0006, 0.0014, 0.0002, 0.0000],  # AA
        [0.0009, 0.0227, 0.9105, 0.0552, 0.0074, 0.0026, 0.0001, 0.0006],  # A
        [0.0002, 0.0033, 0.0595, 0.8693, 0.0530, 0.0117, 0.0012, 0.0018],  # BBB
        [0.0003, 0.0014, 0.0067, 0.0773, 0.8053, 0.0884, 0.0100, 0.0106],  # BB
        [0.0000, 0.0011, 0.0024, 0.0043, 0.0648, 0.8346, 0.0407, 0.0521],  # B
        [0.0022, 0.0000, 0.0022, 0.0130, 0.0238, 0.1124, 0.6486, 0.1978],  # CCC
        [0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 1.0000],  # Default
    ])

    RATING_LABELS = ['AAA', 'AA', 'A', 'BBB', 'BB', 'B', 'CCC', 'D']

    def __init__(
        self,
        transition_matrix: Optional[np.ndarray] = None,
        asset_correlation: float = 0.3
    ):
        """
        Initialize CreditMetrics model.

        Args:
            transition_matrix: 8x8 rating transition matrix
            asset_correlation: Inter-obligor asset correlation
        """
        self.transition_matrix = (
            transition_matrix if transition_matrix is not None
            else self.DEFAULT_TRANSITION_MATRIX
        )
        self.rho = asset_correlation
        self.n_ratings = len(self.RATING_LABELS)

        # Calculate rating thresholds from transition probs
        self._calculate_thresholds()

    def _calculate_thresholds(self):
        """Calculate asset value thresholds for rating transitions."""
        self.thresholds = {}

        for i, rating in enumerate(self.RATING_LABELS[:-1]):  # Exclude Default
            probs = self.transition_matrix[i]
            cum_probs = np.cumsum(probs[::-1])[::-1]  # Reverse cumulative

            # Thresholds are inverse normal of cumulative probs
            thresholds = []
            for cp in cum_probs[1:]:  # Skip first (always 1)
                if cp > 0 and cp < 1:
                    thresholds.append(stats.norm.ppf(cp))
                elif cp >= 1:
                    thresholds.append(-np.inf)
                else:
                    thresholds.append(np.inf)

            self.thresholds[rating] = thresholds

    def simulate_portfolio(
        self,
        exposures: np.ndarray,
        initial_ratings: List[str],
        n_simulations: int = 10000,
        correlation_matrix: Optional[np.ndarray] = None
    ) -> np.ndarray:
        """
        Simulate portfolio loss distribution.

        Args:
            exposures: Array of exposure amounts
            initial_ratings: Initial ratings for each obligor
            n_simulations: Number of Monte Carlo simulations
            correlation_matrix: Optional correlation matrix

        Returns:
            Array of portfolio losses
        """
        n_obligors = len(exposures)

        # Generate correlated asset returns
        if correlation_matrix is None:
            # Assume uniform correlation
            correlation_matrix = np.full(
                (n_obligors, n_obligors), self.rho
            )
            np.fill_diagonal(correlation_matrix, 1.0)

        # Cholesky decomposition
        try:
            L = np.linalg.cholesky(correlation_matrix)
        except np.linalg.LinAlgError:
            # Make positive definite
            eigenvalues, eigenvectors = np.linalg.eigh(correlation_matrix)
            eigenvalues = np.maximum(eigenvalues, 1e-6)
            correlation_matrix = eigenvectors @ np.diag(eigenvalues) @ eigenvectors.T
            L = np.linalg.cholesky(correlation_matrix)

        # Generate correlated normals
        Z = np.random.standard_normal((n_simulations, n_obligors))
        asset_returns = Z @ L.T

        # Determine final ratings and losses
        losses = np.zeros(n_simulations)

        for i, (exposure, rating) in enumerate(zip(exposures, initial_ratings)):
            if rating == 'D':
                # Already defaulted
                losses += exposure
                continue

            rating_idx = self.RATING_LABELS.index(rating)
            thresholds = self.thresholds.get(rating, [])

            if not thresholds:
                continue

            # Determine final rating for each simulation
            for sim in range(n_simulations):
                asset_value = asset_returns[sim, i]

                # Find which rating bucket the asset value falls into
                final_rating_idx = self.n_ratings - 1  # Default
                for j, thresh in enumerate(thresholds):
                    if asset_value > thresh:
                        final_rating_idx = j
                        break

                # If defaulted, add to loss
                if final_rating_idx == self.n_ratings - 1:
                    losses[sim] += exposure

        return losses

    def portfolio_var(
        self,
        exposures: np.ndarray,
        initial_ratings: List[str],
        confidence: float = 0.99,
        n_simulations: int = 50000
    ) -> Tuple[float, float]:
        """
        Calculate portfolio VaR and ES.

        Returns:
            Tuple of (VaR, Expected Shortfall)
        """
        losses = self.simulate_portfolio(
            exposures, initial_ratings, n_simulations
        )

        var = np.percentile(losses, confidence * 100)
        es = np.mean(losses[losses >= var])

        return var, es


# =============================================================================
# Probability of Default Models
# =============================================================================

class PDModel:
    """
    Probability of Default estimation models.

    Includes:
    - Logistic regression approach
    - Merton-based approach
    - Historical default rates
    """

    @staticmethod
    def logistic_pd(
        features: np.ndarray,
        coefficients: np.ndarray,
        intercept: float
    ) -> np.ndarray:
        """
        Calculate PD using logistic regression.

        PD = 1 / (1 + exp(-(intercept + features @ coefficients)))
        """
        linear = intercept + features @ coefficients
        return 1 / (1 + np.exp(-linear))

    @staticmethod
    def merton_pd(
        equity_value: float,
        equity_volatility: float,
        debt: float,
        risk_free_rate: float,
        maturity: float = 1.0
    ) -> float:
        """
        Calculate PD using Merton model.

        First calibrates asset value and volatility from equity,
        then calculates distance to default.
        """
        model = MertonModel(
            asset_value=equity_value + debt,  # Initial guess
            debt_face_value=debt,
            asset_volatility=equity_volatility,  # Initial guess
            risk_free_rate=risk_free_rate,
            maturity=maturity
        )

        model.calibrate_from_equity(equity_value, equity_volatility)
        return model.probability_of_default()

    @staticmethod
    def through_the_cycle_pd(
        point_in_time_pd: float,
        current_cycle_position: float,
        cycle_amplitude: float = 0.5
    ) -> float:
        """
        Convert point-in-time PD to through-the-cycle PD.

        Args:
            point_in_time_pd: Current PD estimate
            current_cycle_position: Position in credit cycle (-1 to 1)
            cycle_amplitude: Amplitude of cycle effect

        Returns:
            Through-the-cycle PD
        """
        # Adjust PD for cycle position
        cycle_factor = 1 + cycle_amplitude * current_cycle_position
        ttc_pd = point_in_time_pd / cycle_factor
        return np.clip(ttc_pd, 0, 1)

    @staticmethod
    def forward_pd(
        current_pd: float,
        hazard_rate_growth: float,
        horizon: float
    ) -> float:
        """
        Calculate forward PD for future period.

        Uses hazard rate model with potential growth.
        """
        # Extract hazard rate from current PD
        if current_pd >= 1:
            return 1.0
        h0 = -np.log(1 - current_pd)

        # Forward hazard rate
        h_forward = h0 * np.exp(hazard_rate_growth * horizon)

        # Forward PD
        return 1 - np.exp(-h_forward)


# =============================================================================
# Loss Given Default Models
# =============================================================================

class LGDModel:
    """
    Loss Given Default modeling.

    Includes various approaches:
    - Fixed LGD
    - Stochastic LGD (correlated with PD)
    - Downturn LGD
    - Collateral-based LGD
    """

    def __init__(
        self,
        mean_lgd: float = 0.45,
        lgd_volatility: float = 0.2,
        pd_lgd_correlation: float = 0.3
    ):
        """
        Initialize LGD model.

        Args:
            mean_lgd: Expected LGD
            lgd_volatility: Volatility of LGD
            pd_lgd_correlation: Correlation between PD and LGD
        """
        self.mean_lgd = mean_lgd
        self.lgd_vol = lgd_volatility
        self.rho_pd_lgd = pd_lgd_correlation

    def downturn_lgd(
        self,
        base_lgd: Optional[float] = None,
        economic_condition: float = 0.0
    ) -> float:
        """
        Calculate downturn LGD.

        Args:
            base_lgd: Base LGD (uses mean if not provided)
            economic_condition: Economic condition (-1 to 1, negative = downturn)

        Returns:
            Downturn-adjusted LGD
        """
        lgd = base_lgd if base_lgd is not None else self.mean_lgd

        # Increase LGD in downturns
        adjustment = -economic_condition * self.lgd_vol * 2
        downturn_lgd = lgd * (1 + adjustment)

        return np.clip(downturn_lgd, 0, 1)

    def stochastic_lgd(
        self,
        systematic_factor: float,
        idiosyncratic_factor: Optional[float] = None
    ) -> float:
        """
        Generate stochastic LGD correlated with systematic factor.

        Args:
            systematic_factor: Systematic risk factor
            idiosyncratic_factor: Idiosyncratic factor (random if not provided)

        Returns:
            Realized LGD
        """
        if idiosyncratic_factor is None:
            idiosyncratic_factor = np.random.standard_normal()

        # LGD factor (correlated with systematic)
        lgd_factor = (np.sqrt(self.rho_pd_lgd) * systematic_factor +
                     np.sqrt(1 - self.rho_pd_lgd) * idiosyncratic_factor)

        # Transform to beta distribution via normal CDF
        u = stats.norm.cdf(lgd_factor)

        # Beta parameters from mean and variance
        alpha = self.mean_lgd * (self.mean_lgd * (1 - self.mean_lgd) / self.lgd_vol**2 - 1)
        beta = (1 - self.mean_lgd) * (self.mean_lgd * (1 - self.mean_lgd) / self.lgd_vol**2 - 1)

        if alpha <= 0 or beta <= 0:
            return self.mean_lgd

        return stats.beta.ppf(u, alpha, beta)

    def collateralized_lgd(
        self,
        exposure: float,
        collateral_value: float,
        haircut: float = 0.2,
        cost_of_recovery: float = 0.1
    ) -> float:
        """
        Calculate LGD for collateralized exposure.

        Args:
            exposure: Exposure at default
            collateral_value: Current collateral value
            haircut: Haircut applied to collateral
            cost_of_recovery: Cost of recovery as fraction

        Returns:
            Collateralized LGD
        """
        # Haircut-adjusted collateral
        adjusted_collateral = collateral_value * (1 - haircut)

        # Recovery amount
        recovery = min(adjusted_collateral, exposure)
        recovery_net = recovery * (1 - cost_of_recovery)

        # LGD
        lgd = (exposure - recovery_net) / exposure
        return np.clip(lgd, 0, 1)


# =============================================================================
# Factory Functions
# =============================================================================

def create_var_calculator(
    confidence_level: float = 0.99
) -> ValueAtRisk:
    """Create VaR calculator with specified confidence level."""
    return ValueAtRisk(confidence_level)


def create_merton_model(
    asset_value: float,
    debt: float,
    volatility: float,
    risk_free_rate: float = 0.05,
    maturity: float = 1.0
) -> MertonModel:
    """Create Merton structural credit model."""
    return MertonModel(
        asset_value=asset_value,
        debt_face_value=debt,
        asset_volatility=volatility,
        risk_free_rate=risk_free_rate,
        maturity=maturity
    )


def create_reduced_form_model(
    hazard_rate: float,
    recovery_rate: float = 0.4,
    risk_free_rate: float = 0.05
) -> ReducedFormModel:
    """Create reduced-form credit model."""
    return ReducedFormModel(
        hazard_rate=hazard_rate,
        recovery_rate=recovery_rate,
        risk_free_rate=risk_free_rate
    )


def create_cds_pricer(
    hazard_rate: float,
    risk_free_rate: float = 0.05
) -> CDSPricer:
    """Create CDS pricer."""
    return CDSPricer(
        hazard_rate=hazard_rate,
        risk_free_curve=lambda t: np.exp(-risk_free_rate * t)
    )


def create_xva_calculator(
    counterparty_spread: float,
    own_spread: float,
    counterparty_recovery: float = 0.4,
    own_recovery: float = 0.4,
    funding_spread: float = 0.01,
    risk_free_rate: float = 0.05
) -> XVACalculator:
    """
    Create XVA calculator from credit spreads.

    Converts spreads to hazard rates using h ≈ s / (1 - R).
    """
    h_c = counterparty_spread / (1 - counterparty_recovery)
    h_b = own_spread / (1 - own_recovery)

    return XVACalculator(
        counterparty_hazard_rate=h_c,
        own_hazard_rate=h_b,
        counterparty_recovery=counterparty_recovery,
        own_recovery=own_recovery,
        funding_spread=funding_spread,
        risk_free_rate=risk_free_rate
    )


def create_vasicek_model(
    pd: float,
    lgd: float,
    correlation: float
) -> VasicekPortfolioModel:
    """Create Vasicek portfolio credit model."""
    return VasicekPortfolioModel(
        probability_of_default=pd,
        loss_given_default=lgd,
        asset_correlation=correlation
    )


def create_credit_metrics(
    correlation: float = 0.3,
    transition_matrix: Optional[np.ndarray] = None
) -> CreditMetrics:
    """Create CreditMetrics portfolio model."""
    return CreditMetrics(
        transition_matrix=transition_matrix,
        asset_correlation=correlation
    )


def calculate_credit_var(
    pd: float,
    lgd: float,
    exposure: float,
    correlation: float = 0.2,
    confidence: float = 0.99
) -> Dict[str, float]:
    """
    Quick credit VaR calculation using Vasicek model.

    Args:
        pd: Probability of default
        lgd: Loss given default
        exposure: Exposure at default
        correlation: Asset correlation
        confidence: Confidence level

    Returns:
        Dict with expected loss, unexpected loss, and credit VaR
    """
    model = VasicekPortfolioModel(pd, lgd, correlation)

    el = model.expected_loss() * exposure
    ul = model.unexpected_loss(confidence) * exposure
    credit_var = model.loss_distribution_quantile(confidence) * exposure

    return {
        'expected_loss': el,
        'unexpected_loss': ul,
        'credit_var': credit_var,
        'economic_capital': ul
    }
