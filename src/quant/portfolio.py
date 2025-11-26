"""
Revolution Alpha Engine - Portfolio Theory & Risk Modeling Module

Institutional-grade portfolio construction and risk management:
- Mean-Variance Optimization (Markowitz)
- Black-Litterman Model
- Risk Parity and Risk Budgeting
- Factor Models (CAPM, Fama-French, APT)
- Covariance Estimation (Shrinkage, Ledoit-Wolf)
- Risk Decomposition and Attribution
- Portfolio Performance Analytics
- Rebalancing Strategies
"""

import numpy as np
from scipy import optimize, stats
from scipy.linalg import sqrtm
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Callable, Union
from enum import Enum
from abc import ABC, abstractmethod
import warnings


# =============================================================================
# Data Classes and Enums
# =============================================================================

class OptimizationObjective(Enum):
    """Portfolio optimization objectives."""
    MIN_VARIANCE = "min_variance"
    MAX_SHARPE = "max_sharpe"
    MAX_RETURN = "max_return"
    RISK_PARITY = "risk_parity"
    MAX_DIVERSIFICATION = "max_diversification"
    MIN_CVAR = "min_cvar"


class RiskMeasure(Enum):
    """Risk measures for portfolio optimization."""
    VARIANCE = "variance"
    VOLATILITY = "volatility"
    VAR = "var"
    CVAR = "cvar"
    SEMI_VARIANCE = "semi_variance"
    MAX_DRAWDOWN = "max_drawdown"


@dataclass
class PortfolioWeights:
    """Portfolio allocation result."""
    weights: np.ndarray
    asset_names: List[str]
    expected_return: float
    volatility: float
    sharpe_ratio: float
    diversification_ratio: Optional[float] = None
    max_drawdown: Optional[float] = None


@dataclass
class RiskDecomposition:
    """Portfolio risk decomposition."""
    total_risk: float
    marginal_risk: np.ndarray
    component_risk: np.ndarray
    percentage_contribution: np.ndarray
    diversification_ratio: float


@dataclass
class FactorExposure:
    """Factor model exposure result."""
    alpha: float
    betas: Dict[str, float]
    r_squared: float
    residual_volatility: float
    factor_contribution: Dict[str, float]


@dataclass
class PerformanceMetrics:
    """Portfolio performance metrics."""
    total_return: float
    annualized_return: float
    volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown: float
    var_95: float
    cvar_95: float
    information_ratio: Optional[float] = None
    tracking_error: Optional[float] = None
    beta: Optional[float] = None
    alpha: Optional[float] = None


# =============================================================================
# Mean-Variance Optimization (Markowitz)
# =============================================================================

class MeanVarianceOptimizer:
    """
    Classical Markowitz Mean-Variance Optimization.

    Implements efficient frontier calculation and various
    optimization objectives.
    """

    def __init__(
        self,
        expected_returns: np.ndarray,
        covariance_matrix: np.ndarray,
        asset_names: Optional[List[str]] = None,
        risk_free_rate: float = 0.02
    ):
        """
        Initialize optimizer.

        Args:
            expected_returns: Expected returns for each asset
            covariance_matrix: Covariance matrix of returns
            asset_names: Names of assets
            risk_free_rate: Risk-free rate for Sharpe calculation
        """
        self.mu = np.array(expected_returns)
        self.sigma = np.array(covariance_matrix)
        self.n_assets = len(expected_returns)
        self.asset_names = asset_names or [f"Asset_{i}" for i in range(self.n_assets)]
        self.rf = risk_free_rate

        # Validate covariance matrix
        self._validate_inputs()

    def _validate_inputs(self):
        """Validate input matrices."""
        if len(self.mu) != self.n_assets:
            raise ValueError("Expected returns length must match number of assets")

        if self.sigma.shape != (self.n_assets, self.n_assets):
            raise ValueError("Covariance matrix dimensions must match number of assets")

        # Check positive semi-definiteness
        eigenvalues = np.linalg.eigvalsh(self.sigma)
        if np.min(eigenvalues) < -1e-8:
            warnings.warn("Covariance matrix is not positive semi-definite")

    def portfolio_return(self, weights: np.ndarray) -> float:
        """Calculate portfolio expected return."""
        return weights @ self.mu

    def portfolio_volatility(self, weights: np.ndarray) -> float:
        """Calculate portfolio volatility."""
        return np.sqrt(weights @ self.sigma @ weights)

    def portfolio_sharpe(self, weights: np.ndarray) -> float:
        """Calculate portfolio Sharpe ratio."""
        ret = self.portfolio_return(weights)
        vol = self.portfolio_volatility(weights)
        if vol < 1e-10:
            return 0.0
        return (ret - self.rf) / vol

    def minimum_variance(
        self,
        constraints: Optional[Dict] = None,
        bounds: Optional[Tuple] = None
    ) -> PortfolioWeights:
        """
        Find minimum variance portfolio.

        Args:
            constraints: Additional constraints
            bounds: Weight bounds (min, max) for each asset

        Returns:
            Optimal portfolio weights
        """
        def objective(w):
            return self.portfolio_volatility(w)**2

        return self._optimize(objective, constraints, bounds)

    def maximum_sharpe(
        self,
        constraints: Optional[Dict] = None,
        bounds: Optional[Tuple] = None
    ) -> PortfolioWeights:
        """
        Find maximum Sharpe ratio portfolio (tangency portfolio).

        Args:
            constraints: Additional constraints
            bounds: Weight bounds

        Returns:
            Optimal portfolio weights
        """
        def objective(w):
            return -self.portfolio_sharpe(w)

        return self._optimize(objective, constraints, bounds)

    def target_return(
        self,
        target: float,
        constraints: Optional[Dict] = None,
        bounds: Optional[Tuple] = None
    ) -> PortfolioWeights:
        """
        Find minimum variance portfolio for target return.

        Args:
            target: Target expected return
            constraints: Additional constraints
            bounds: Weight bounds

        Returns:
            Optimal portfolio weights
        """
        def objective(w):
            return self.portfolio_volatility(w)**2

        # Add return constraint
        if constraints is None:
            constraints = {}
        constraints['target_return'] = target

        return self._optimize(objective, constraints, bounds)

    def target_volatility(
        self,
        target: float,
        constraints: Optional[Dict] = None,
        bounds: Optional[Tuple] = None
    ) -> PortfolioWeights:
        """
        Find maximum return portfolio for target volatility.

        Args:
            target: Target volatility
            constraints: Additional constraints
            bounds: Weight bounds

        Returns:
            Optimal portfolio weights
        """
        def objective(w):
            return -self.portfolio_return(w)

        if constraints is None:
            constraints = {}
        constraints['target_volatility'] = target

        return self._optimize(objective, constraints, bounds)

    def efficient_frontier(
        self,
        n_points: int = 50,
        bounds: Optional[Tuple] = None
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Calculate efficient frontier.

        Args:
            n_points: Number of points on frontier
            bounds: Weight bounds

        Returns:
            Tuple of (returns, volatilities, weights_array)
        """
        # Find min and max return portfolios
        min_var = self.minimum_variance(bounds=bounds)
        max_ret = self._optimize(
            lambda w: -self.portfolio_return(w),
            constraints=None,
            bounds=bounds
        )

        min_ret = min_var.expected_return
        max_ret_val = max_ret.expected_return

        # Generate target returns
        target_returns = np.linspace(min_ret, max_ret_val, n_points)

        returns = []
        volatilities = []
        weights_list = []

        for target in target_returns:
            try:
                result = self.target_return(target, bounds=bounds)
                returns.append(result.expected_return)
                volatilities.append(result.volatility)
                weights_list.append(result.weights)
            except Exception:
                continue

        return (
            np.array(returns),
            np.array(volatilities),
            np.array(weights_list)
        )

    def _optimize(
        self,
        objective: Callable,
        constraints: Optional[Dict] = None,
        bounds: Optional[Tuple] = None
    ) -> PortfolioWeights:
        """
        General optimization routine.

        Args:
            objective: Objective function to minimize
            constraints: Constraint dictionary
            bounds: Weight bounds

        Returns:
            Optimal portfolio
        """
        # Initial guess (equal weights)
        w0 = np.ones(self.n_assets) / self.n_assets

        # Set bounds
        if bounds is None:
            bounds = [(0, 1) for _ in range(self.n_assets)]
        elif isinstance(bounds, tuple) and len(bounds) == 2:
            bounds = [bounds for _ in range(self.n_assets)]

        # Constraints
        cons = [{'type': 'eq', 'fun': lambda w: np.sum(w) - 1}]  # Sum to 1

        if constraints:
            if 'target_return' in constraints:
                target = constraints['target_return']
                cons.append({
                    'type': 'eq',
                    'fun': lambda w, t=target: self.portfolio_return(w) - t
                })

            if 'target_volatility' in constraints:
                target = constraints['target_volatility']
                cons.append({
                    'type': 'eq',
                    'fun': lambda w, t=target: self.portfolio_volatility(w) - t
                })

            if 'max_weight' in constraints:
                max_w = constraints['max_weight']
                bounds = [(b[0], min(b[1], max_w)) for b in bounds]

            if 'min_weight' in constraints:
                min_w = constraints['min_weight']
                bounds = [(max(b[0], min_w), b[1]) for b in bounds]

        # Optimize
        result = optimize.minimize(
            objective,
            w0,
            method='SLSQP',
            bounds=bounds,
            constraints=cons,
            options={'ftol': 1e-10, 'maxiter': 1000}
        )

        if not result.success:
            warnings.warn(f"Optimization may not have converged: {result.message}")

        weights = result.x
        weights = np.maximum(weights, 0)  # Ensure non-negative
        weights = weights / np.sum(weights)  # Normalize

        return PortfolioWeights(
            weights=weights,
            asset_names=self.asset_names,
            expected_return=self.portfolio_return(weights),
            volatility=self.portfolio_volatility(weights),
            sharpe_ratio=self.portfolio_sharpe(weights)
        )


# =============================================================================
# Black-Litterman Model
# =============================================================================

class BlackLittermanModel:
    """
    Black-Litterman Asset Allocation Model.

    Combines equilibrium market returns with investor views
    to produce posterior expected returns.
    """

    def __init__(
        self,
        market_caps: np.ndarray,
        covariance_matrix: np.ndarray,
        asset_names: Optional[List[str]] = None,
        risk_aversion: float = 2.5,
        risk_free_rate: float = 0.02,
        tau: float = 0.05
    ):
        """
        Initialize Black-Litterman model.

        Args:
            market_caps: Market capitalizations
            covariance_matrix: Covariance matrix
            asset_names: Asset names
            risk_aversion: Risk aversion parameter (delta)
            risk_free_rate: Risk-free rate
            tau: Scaling factor for uncertainty in equilibrium returns
        """
        self.market_caps = np.array(market_caps)
        self.sigma = np.array(covariance_matrix)
        self.n_assets = len(market_caps)
        self.asset_names = asset_names or [f"Asset_{i}" for i in range(self.n_assets)]
        self.delta = risk_aversion
        self.rf = risk_free_rate
        self.tau = tau

        # Market weights
        self.w_mkt = self.market_caps / np.sum(self.market_caps)

        # Equilibrium excess returns (reverse optimization)
        self.pi = self.delta * self.sigma @ self.w_mkt

    def implied_returns(self) -> np.ndarray:
        """Get implied equilibrium excess returns."""
        return self.pi

    def add_absolute_view(
        self,
        asset: Union[int, str],
        view_return: float,
        confidence: float = 0.5
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Add absolute view on single asset.

        Args:
            asset: Asset index or name
            view_return: Expected return view
            confidence: Confidence in view (0 to 1)

        Returns:
            Tuple of (P, Q, Omega) for the view
        """
        if isinstance(asset, str):
            asset = self.asset_names.index(asset)

        P = np.zeros((1, self.n_assets))
        P[0, asset] = 1

        Q = np.array([view_return])

        # Uncertainty in view (inversely proportional to confidence)
        var_view = (1 / confidence - 1) * self.tau * self.sigma[asset, asset]
        Omega = np.array([[var_view]])

        return P, Q, Omega

    def add_relative_view(
        self,
        long_asset: Union[int, str],
        short_asset: Union[int, str],
        view_spread: float,
        confidence: float = 0.5
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Add relative view (long-short).

        Args:
            long_asset: Asset expected to outperform
            short_asset: Asset expected to underperform
            view_spread: Expected return spread
            confidence: Confidence in view

        Returns:
            Tuple of (P, Q, Omega) for the view
        """
        if isinstance(long_asset, str):
            long_asset = self.asset_names.index(long_asset)
        if isinstance(short_asset, str):
            short_asset = self.asset_names.index(short_asset)

        P = np.zeros((1, self.n_assets))
        P[0, long_asset] = 1
        P[0, short_asset] = -1

        Q = np.array([view_spread])

        # Variance of the spread
        var_spread = (self.sigma[long_asset, long_asset] +
                     self.sigma[short_asset, short_asset] -
                     2 * self.sigma[long_asset, short_asset])
        var_view = (1 / confidence - 1) * self.tau * var_spread
        Omega = np.array([[var_view]])

        return P, Q, Omega

    def posterior_returns(
        self,
        P: np.ndarray,
        Q: np.ndarray,
        Omega: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Calculate posterior expected returns.

        Args:
            P: View matrix (K x N)
            Q: View vector (K,)
            Omega: View uncertainty matrix (K x K)

        Returns:
            Tuple of (posterior_mu, posterior_sigma)
        """
        tau_sigma = self.tau * self.sigma

        # Posterior covariance
        M = np.linalg.inv(
            np.linalg.inv(tau_sigma) +
            P.T @ np.linalg.inv(Omega) @ P
        )

        # Posterior mean
        posterior_mu = M @ (
            np.linalg.inv(tau_sigma) @ self.pi +
            P.T @ np.linalg.inv(Omega) @ Q
        )

        # Posterior covariance of returns
        posterior_sigma = self.sigma + M

        return posterior_mu, posterior_sigma

    def optimal_weights(
        self,
        views: List[Dict],
        bounds: Optional[Tuple] = None
    ) -> PortfolioWeights:
        """
        Calculate optimal weights given views.

        Args:
            views: List of view dictionaries
                   {'type': 'absolute'/'relative', 'assets': ..., 'return': ..., 'confidence': ...}
            bounds: Weight bounds

        Returns:
            Optimal portfolio weights
        """
        # Combine all views
        P_list, Q_list, Omega_list = [], [], []

        for view in views:
            if view['type'] == 'absolute':
                p, q, omega = self.add_absolute_view(
                    view['asset'],
                    view['return'],
                    view.get('confidence', 0.5)
                )
            else:  # relative
                p, q, omega = self.add_relative_view(
                    view['long_asset'],
                    view['short_asset'],
                    view['return'],
                    view.get('confidence', 0.5)
                )
            P_list.append(p)
            Q_list.append(q)
            Omega_list.append(omega)

        if not P_list:
            # No views, use equilibrium
            posterior_mu = self.pi
            posterior_sigma = self.sigma
        else:
            P = np.vstack(P_list)
            Q = np.concatenate(Q_list)
            Omega = np.zeros((len(Q), len(Q)))
            idx = 0
            for o in Omega_list:
                size = o.shape[0]
                Omega[idx:idx+size, idx:idx+size] = o
                idx += size

            posterior_mu, posterior_sigma = self.posterior_returns(P, Q, Omega)

        # Optimize with posterior estimates
        optimizer = MeanVarianceOptimizer(
            expected_returns=posterior_mu,
            covariance_matrix=posterior_sigma,
            asset_names=self.asset_names,
            risk_free_rate=self.rf
        )

        return optimizer.maximum_sharpe(bounds=bounds)


# =============================================================================
# Risk Parity
# =============================================================================

class RiskParityOptimizer:
    """
    Risk Parity Portfolio Optimization.

    Allocates risk equally across assets rather than capital.
    """

    def __init__(
        self,
        covariance_matrix: np.ndarray,
        asset_names: Optional[List[str]] = None,
        expected_returns: Optional[np.ndarray] = None
    ):
        """
        Initialize risk parity optimizer.

        Args:
            covariance_matrix: Covariance matrix
            asset_names: Asset names
            expected_returns: Optional expected returns
        """
        self.sigma = np.array(covariance_matrix)
        self.n_assets = self.sigma.shape[0]
        self.asset_names = asset_names or [f"Asset_{i}" for i in range(self.n_assets)]
        self.mu = expected_returns

    def equal_risk_contribution(
        self,
        risk_budget: Optional[np.ndarray] = None
    ) -> PortfolioWeights:
        """
        Calculate equal risk contribution portfolio.

        Args:
            risk_budget: Risk budget per asset (sums to 1)
                        If None, uses equal budgets

        Returns:
            Risk parity portfolio
        """
        if risk_budget is None:
            risk_budget = np.ones(self.n_assets) / self.n_assets

        def objective(w):
            # Portfolio volatility
            port_vol = np.sqrt(w @ self.sigma @ w)
            if port_vol < 1e-10:
                return 1e10

            # Marginal risk contribution
            mrc = self.sigma @ w / port_vol

            # Risk contribution
            rc = w * mrc

            # Target risk contribution
            target_rc = risk_budget * port_vol

            # Sum of squared differences
            return np.sum((rc - target_rc)**2)

        # Initial guess
        w0 = np.ones(self.n_assets) / self.n_assets

        # Bounds (positive weights)
        bounds = [(1e-5, 1) for _ in range(self.n_assets)]

        # Sum to 1 constraint
        cons = [{'type': 'eq', 'fun': lambda w: np.sum(w) - 1}]

        result = optimize.minimize(
            objective,
            w0,
            method='SLSQP',
            bounds=bounds,
            constraints=cons,
            options={'ftol': 1e-12, 'maxiter': 1000}
        )

        weights = result.x
        weights = weights / np.sum(weights)

        vol = np.sqrt(weights @ self.sigma @ weights)
        ret = weights @ self.mu if self.mu is not None else 0.0
        sharpe = (ret / vol) if vol > 0 and self.mu is not None else 0.0

        return PortfolioWeights(
            weights=weights,
            asset_names=self.asset_names,
            expected_return=ret,
            volatility=vol,
            sharpe_ratio=sharpe
        )

    def inverse_volatility(self) -> PortfolioWeights:
        """
        Simple inverse volatility weighting.

        Returns:
            Inverse volatility weighted portfolio
        """
        vols = np.sqrt(np.diag(self.sigma))
        inv_vols = 1 / vols
        weights = inv_vols / np.sum(inv_vols)

        vol = np.sqrt(weights @ self.sigma @ weights)
        ret = weights @ self.mu if self.mu is not None else 0.0
        sharpe = (ret / vol) if vol > 0 and self.mu is not None else 0.0

        return PortfolioWeights(
            weights=weights,
            asset_names=self.asset_names,
            expected_return=ret,
            volatility=vol,
            sharpe_ratio=sharpe
        )

    def hierarchical_risk_parity(
        self,
        returns: np.ndarray
    ) -> PortfolioWeights:
        """
        Hierarchical Risk Parity (HRP) using clustering.

        Args:
            returns: Historical returns matrix (T x N)

        Returns:
            HRP portfolio weights
        """
        # Correlation matrix
        corr = np.corrcoef(returns.T)

        # Distance matrix
        dist = np.sqrt((1 - corr) / 2)

        # Simple hierarchical clustering (single linkage)
        n = self.n_assets
        clusters = [[i] for i in range(n)]
        cluster_dist = dist.copy()

        # Agglomerative clustering
        order = list(range(n))

        while len(clusters) > 1:
            # Find closest clusters
            min_dist = np.inf
            min_i, min_j = 0, 1

            for i in range(len(clusters)):
                for j in range(i + 1, len(clusters)):
                    d = np.min([dist[a, b] for a in clusters[i] for b in clusters[j]])
                    if d < min_dist:
                        min_dist = d
                        min_i, min_j = i, j

            # Merge clusters
            clusters[min_i] = clusters[min_i] + clusters[min_j]
            clusters.pop(min_j)

        # Quasi-diagonalization order
        order = clusters[0]

        # Recursive bisection
        weights = self._recursive_bisection(order, self.sigma)

        vol = np.sqrt(weights @ self.sigma @ weights)
        ret = weights @ self.mu if self.mu is not None else 0.0
        sharpe = (ret / vol) if vol > 0 and self.mu is not None else 0.0

        return PortfolioWeights(
            weights=weights,
            asset_names=self.asset_names,
            expected_return=ret,
            volatility=vol,
            sharpe_ratio=sharpe
        )

    def _recursive_bisection(
        self,
        order: List[int],
        cov: np.ndarray
    ) -> np.ndarray:
        """Recursive bisection for HRP."""
        weights = np.zeros(self.n_assets)

        def recurse(indices: List[int], weight: float):
            if len(indices) == 1:
                weights[indices[0]] = weight
                return

            # Split in half
            mid = len(indices) // 2
            left = indices[:mid]
            right = indices[mid:]

            # Inverse variance allocation between clusters
            var_left = self._cluster_variance(left, cov)
            var_right = self._cluster_variance(right, cov)

            alpha = 1 - var_left / (var_left + var_right)

            recurse(left, weight * alpha)
            recurse(right, weight * (1 - alpha))

        recurse(order, 1.0)
        return weights

    def _cluster_variance(
        self,
        indices: List[int],
        cov: np.ndarray
    ) -> float:
        """Calculate variance of inverse-vol weighted cluster."""
        sub_cov = cov[np.ix_(indices, indices)]
        inv_var = 1 / np.diag(sub_cov)
        w = inv_var / np.sum(inv_var)
        return w @ sub_cov @ w


# =============================================================================
# Factor Models
# =============================================================================

class FactorModel:
    """
    Factor model for return decomposition and risk analysis.

    Supports CAPM, Fama-French, and custom factor models.
    """

    def __init__(
        self,
        factor_returns: np.ndarray,
        factor_names: List[str]
    ):
        """
        Initialize factor model.

        Args:
            factor_returns: Factor returns (T x K)
            factor_names: Names of factors
        """
        self.factor_returns = np.array(factor_returns)
        self.factor_names = factor_names
        self.n_factors = len(factor_names)

    def fit(
        self,
        asset_returns: np.ndarray,
        risk_free: Optional[np.ndarray] = None
    ) -> FactorExposure:
        """
        Fit factor model to asset returns.

        Args:
            asset_returns: Asset excess returns (T,)
            risk_free: Risk-free rate series (optional)

        Returns:
            Factor exposure results
        """
        if risk_free is not None:
            y = asset_returns - risk_free
        else:
            y = asset_returns

        # Add constant for alpha
        X = np.column_stack([np.ones(len(y)), self.factor_returns])

        # OLS regression
        beta_hat = np.linalg.lstsq(X, y, rcond=None)[0]

        alpha = beta_hat[0]
        betas = dict(zip(self.factor_names, beta_hat[1:]))

        # R-squared
        y_pred = X @ beta_hat
        ss_res = np.sum((y - y_pred)**2)
        ss_tot = np.sum((y - np.mean(y))**2)
        r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0

        # Residual volatility
        residuals = y - y_pred
        residual_vol = np.std(residuals, ddof=len(beta_hat))

        # Factor contribution to variance
        factor_cov = np.cov(self.factor_returns, rowvar=False)
        if self.n_factors == 1:
            factor_cov = np.array([[factor_cov]])

        beta_vec = beta_hat[1:]
        total_var = np.var(y)
        factor_var = beta_vec @ factor_cov @ beta_vec

        factor_contribution = {}
        for i, name in enumerate(self.factor_names):
            contrib = beta_vec[i]**2 * factor_cov[i, i] / total_var if total_var > 0 else 0
            factor_contribution[name] = contrib

        return FactorExposure(
            alpha=alpha,
            betas=betas,
            r_squared=r_squared,
            residual_volatility=residual_vol,
            factor_contribution=factor_contribution
        )

    def expected_return(
        self,
        betas: Dict[str, float],
        factor_premia: Dict[str, float],
        alpha: float = 0.0
    ) -> float:
        """
        Calculate expected return from factor exposures.

        Args:
            betas: Factor betas
            factor_premia: Expected factor risk premia
            alpha: Alpha (intercept)

        Returns:
            Expected return
        """
        expected = alpha
        for factor, beta in betas.items():
            if factor in factor_premia:
                expected += beta * factor_premia[factor]
        return expected

    def covariance_matrix(
        self,
        betas: np.ndarray,
        residual_variances: np.ndarray
    ) -> np.ndarray:
        """
        Build covariance matrix from factor model.

        Sigma = B * F * B' + D

        Args:
            betas: Factor loadings (N x K)
            residual_variances: Idiosyncratic variances (N,)

        Returns:
            Covariance matrix (N x N)
        """
        factor_cov = np.cov(self.factor_returns, rowvar=False)
        if self.n_factors == 1:
            factor_cov = np.array([[factor_cov]])

        systematic = betas @ factor_cov @ betas.T
        idiosyncratic = np.diag(residual_variances)

        return systematic + idiosyncratic


class FamaFrenchModel(FactorModel):
    """
    Fama-French factor model implementation.

    Supports FF3 and FF5 factor models.
    """

    def __init__(
        self,
        market_returns: np.ndarray,
        smb_returns: np.ndarray,
        hml_returns: np.ndarray,
        rmw_returns: Optional[np.ndarray] = None,
        cma_returns: Optional[np.ndarray] = None
    ):
        """
        Initialize Fama-French model.

        Args:
            market_returns: Market excess returns
            smb_returns: Small minus big returns
            hml_returns: High minus low (value) returns
            rmw_returns: Robust minus weak (profitability) - FF5
            cma_returns: Conservative minus aggressive (investment) - FF5
        """
        factors = [market_returns, smb_returns, hml_returns]
        names = ['Mkt-RF', 'SMB', 'HML']

        if rmw_returns is not None:
            factors.append(rmw_returns)
            names.append('RMW')

        if cma_returns is not None:
            factors.append(cma_returns)
            names.append('CMA')

        factor_returns = np.column_stack(factors)
        super().__init__(factor_returns, names)


# =============================================================================
# Covariance Estimation
# =============================================================================

class CovarianceEstimator:
    """
    Advanced covariance matrix estimation methods.

    Implements shrinkage estimators for better stability.
    """

    @staticmethod
    def sample_covariance(returns: np.ndarray) -> np.ndarray:
        """Simple sample covariance matrix."""
        return np.cov(returns, rowvar=False)

    @staticmethod
    def ledoit_wolf(returns: np.ndarray) -> Tuple[np.ndarray, float]:
        """
        Ledoit-Wolf shrinkage estimator.

        Shrinks toward scaled identity matrix.

        Args:
            returns: Returns matrix (T x N)

        Returns:
            Tuple of (shrunk covariance, shrinkage intensity)
        """
        T, N = returns.shape

        # Sample covariance
        sample_cov = np.cov(returns, rowvar=False)

        # Target: scaled identity
        mu = np.trace(sample_cov) / N
        target = mu * np.eye(N)

        # Shrinkage intensity (simplified Ledoit-Wolf formula)
        # Delta
        delta = sample_cov - target
        delta_sq = delta @ delta

        # Compute shrinkage intensity
        X = returns - np.mean(returns, axis=0)
        y = X**2

        phi_mat = (y.T @ y) / T - 2 * (X.T @ X) * sample_cov / T + sample_cov**2
        phi = np.sum(phi_mat)

        gamma = np.linalg.norm(delta, 'fro')**2

        kappa = (phi - gamma) / T
        shrinkage = max(0, min(1, kappa / gamma)) if gamma > 0 else 1

        # Shrunk covariance
        shrunk_cov = shrinkage * target + (1 - shrinkage) * sample_cov

        return shrunk_cov, shrinkage

    @staticmethod
    def ledoit_wolf_constant_correlation(
        returns: np.ndarray
    ) -> Tuple[np.ndarray, float]:
        """
        Ledoit-Wolf shrinkage toward constant correlation matrix.

        Args:
            returns: Returns matrix (T x N)

        Returns:
            Tuple of (shrunk covariance, shrinkage intensity)
        """
        T, N = returns.shape

        sample_cov = np.cov(returns, rowvar=False)
        sample_corr = np.corrcoef(returns, rowvar=False)

        # Average correlation (excluding diagonal)
        sum_corr = np.sum(sample_corr) - N
        avg_corr = sum_corr / (N * (N - 1))

        # Target: constant correlation matrix
        std_devs = np.sqrt(np.diag(sample_cov))
        target_corr = np.full((N, N), avg_corr)
        np.fill_diagonal(target_corr, 1.0)
        target = np.outer(std_devs, std_devs) * target_corr

        # Simplified shrinkage intensity
        X = returns - np.mean(returns, axis=0)

        # Compute pi, rho, gamma for shrinkage
        y = X / std_devs

        # Variance of sample correlation
        var_corr = 0
        for i in range(N):
            for j in range(N):
                if i != j:
                    var_corr += np.var(y[:, i] * y[:, j])

        gamma = np.linalg.norm(sample_cov - target, 'fro')**2

        shrinkage = min(1, max(0, var_corr / (T * gamma))) if gamma > 0 else 0

        shrunk_cov = shrinkage * target + (1 - shrinkage) * sample_cov

        return shrunk_cov, shrinkage

    @staticmethod
    def exponential_weighted(
        returns: np.ndarray,
        decay_factor: float = 0.94
    ) -> np.ndarray:
        """
        Exponentially weighted covariance matrix (EWMA).

        Args:
            returns: Returns matrix (T x N)
            decay_factor: Decay factor (lambda)

        Returns:
            EWMA covariance matrix
        """
        T, N = returns.shape

        # Center returns
        returns_centered = returns - np.mean(returns, axis=0)

        # Weights
        weights = np.array([
            (1 - decay_factor) * decay_factor**(T - 1 - t)
            for t in range(T)
        ])
        weights = weights / np.sum(weights)

        # Weighted covariance
        cov = np.zeros((N, N))
        for t in range(T):
            cov += weights[t] * np.outer(
                returns_centered[t], returns_centered[t]
            )

        return cov

    @staticmethod
    def factor_model_covariance(
        returns: np.ndarray,
        factor_returns: np.ndarray,
        shrink_residuals: bool = True
    ) -> np.ndarray:
        """
        Covariance from factor model (statistical factor model).

        Args:
            returns: Asset returns (T x N)
            factor_returns: Factor returns (T x K)
            shrink_residuals: Whether to shrink residual covariance

        Returns:
            Factor-model implied covariance
        """
        T, N = returns.shape
        K = factor_returns.shape[1]

        # Regress returns on factors
        X = np.column_stack([np.ones(T), factor_returns])
        betas = np.zeros((N, K))
        alphas = np.zeros(N)
        residuals = np.zeros((T, N))

        for i in range(N):
            coef = np.linalg.lstsq(X, returns[:, i], rcond=None)[0]
            alphas[i] = coef[0]
            betas[i] = coef[1:]
            residuals[:, i] = returns[:, i] - X @ coef

        # Factor covariance
        factor_cov = np.cov(factor_returns, rowvar=False)
        if K == 1:
            factor_cov = np.array([[factor_cov]])

        # Systematic covariance
        systematic = betas @ factor_cov @ betas.T

        # Residual covariance
        if shrink_residuals:
            residual_cov, _ = CovarianceEstimator.ledoit_wolf(residuals)
        else:
            residual_cov = np.cov(residuals, rowvar=False)

        # Total covariance
        return systematic + residual_cov


# =============================================================================
# Risk Decomposition
# =============================================================================

class RiskDecomposer:
    """
    Portfolio risk decomposition and attribution.
    """

    def __init__(
        self,
        weights: np.ndarray,
        covariance_matrix: np.ndarray,
        asset_names: Optional[List[str]] = None
    ):
        """
        Initialize risk decomposer.

        Args:
            weights: Portfolio weights
            covariance_matrix: Covariance matrix
            asset_names: Asset names
        """
        self.w = np.array(weights)
        self.sigma = np.array(covariance_matrix)
        self.n_assets = len(weights)
        self.asset_names = asset_names or [f"Asset_{i}" for i in range(self.n_assets)]

    def decompose(self) -> RiskDecomposition:
        """
        Perform full risk decomposition.

        Returns:
            RiskDecomposition with all metrics
        """
        # Portfolio volatility
        port_var = self.w @ self.sigma @ self.w
        port_vol = np.sqrt(port_var)

        # Marginal risk contribution: d(sigma_p)/d(w_i)
        marginal = self.sigma @ self.w / port_vol

        # Risk contribution: w_i * marginal_i
        component = self.w * marginal

        # Percentage contribution
        pct_contrib = component / port_vol

        # Diversification ratio
        individual_vols = np.sqrt(np.diag(self.sigma))
        weighted_vols = self.w @ individual_vols
        div_ratio = weighted_vols / port_vol

        return RiskDecomposition(
            total_risk=port_vol,
            marginal_risk=marginal,
            component_risk=component,
            percentage_contribution=pct_contrib,
            diversification_ratio=div_ratio
        )

    def factor_risk_decomposition(
        self,
        factor_betas: np.ndarray,
        factor_covariance: np.ndarray,
        residual_variances: np.ndarray
    ) -> Dict[str, float]:
        """
        Decompose risk by factors.

        Args:
            factor_betas: Factor loadings (N x K)
            factor_covariance: Factor covariance (K x K)
            residual_variances: Idiosyncratic variances

        Returns:
            Dictionary of risk contributions by factor
        """
        # Portfolio factor exposure
        port_betas = factor_betas.T @ self.w

        # Factor contribution to portfolio variance
        factor_var = port_betas @ factor_covariance @ port_betas

        # Idiosyncratic contribution
        idio_var = self.w**2 @ residual_variances

        # Total variance
        total_var = factor_var + idio_var

        # Individual factor contributions
        K = factor_covariance.shape[0]
        factor_contrib = {}

        for k in range(K):
            contrib = port_betas[k]**2 * factor_covariance[k, k]
            factor_contrib[f"Factor_{k}"] = contrib / total_var

        factor_contrib["Idiosyncratic"] = idio_var / total_var

        return factor_contrib


# =============================================================================
# Performance Analytics
# =============================================================================

class PerformanceAnalyzer:
    """
    Portfolio performance analysis and metrics.
    """

    def __init__(
        self,
        returns: np.ndarray,
        risk_free_rate: float = 0.02,
        periods_per_year: int = 252
    ):
        """
        Initialize performance analyzer.

        Args:
            returns: Portfolio returns
            risk_free_rate: Annual risk-free rate
            periods_per_year: Trading periods per year
        """
        self.returns = np.array(returns)
        self.rf = risk_free_rate
        self.periods = periods_per_year

    def calculate_metrics(
        self,
        benchmark_returns: Optional[np.ndarray] = None
    ) -> PerformanceMetrics:
        """
        Calculate comprehensive performance metrics.

        Args:
            benchmark_returns: Optional benchmark returns

        Returns:
            PerformanceMetrics object
        """
        # Basic returns
        total_ret = np.prod(1 + self.returns) - 1
        ann_ret = (1 + total_ret)**(self.periods / len(self.returns)) - 1

        # Volatility
        vol = np.std(self.returns, ddof=1) * np.sqrt(self.periods)

        # Risk-free rate per period
        rf_period = self.rf / self.periods

        # Sharpe ratio
        excess_returns = self.returns - rf_period
        sharpe = np.mean(excess_returns) / np.std(excess_returns, ddof=1) * np.sqrt(self.periods)

        # Sortino ratio (downside deviation)
        downside_returns = self.returns[self.returns < rf_period]
        downside_std = np.std(downside_returns, ddof=1) if len(downside_returns) > 0 else 0.01
        sortino = np.mean(excess_returns) / downside_std * np.sqrt(self.periods)

        # Maximum drawdown
        cumulative = np.cumprod(1 + self.returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdowns = (cumulative - running_max) / running_max
        max_dd = np.min(drawdowns)

        # Calmar ratio
        calmar = ann_ret / abs(max_dd) if max_dd != 0 else np.inf

        # VaR and CVaR
        var_95 = -np.percentile(self.returns, 5)
        cvar_95 = -np.mean(self.returns[self.returns <= -var_95])

        result = PerformanceMetrics(
            total_return=total_ret,
            annualized_return=ann_ret,
            volatility=vol,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            max_drawdown=max_dd,
            var_95=var_95,
            cvar_95=cvar_95
        )

        # Benchmark-relative metrics
        if benchmark_returns is not None:
            benchmark_returns = np.array(benchmark_returns)

            # Tracking error
            active_returns = self.returns - benchmark_returns
            tracking_error = np.std(active_returns, ddof=1) * np.sqrt(self.periods)

            # Information ratio
            info_ratio = np.mean(active_returns) / np.std(active_returns, ddof=1) * np.sqrt(self.periods)

            # Beta
            cov_with_bench = np.cov(self.returns, benchmark_returns)[0, 1]
            bench_var = np.var(benchmark_returns, ddof=1)
            beta = cov_with_bench / bench_var if bench_var > 0 else 1.0

            # Alpha (CAPM)
            bench_excess = benchmark_returns - rf_period
            alpha = (np.mean(excess_returns) -
                    beta * np.mean(bench_excess)) * self.periods

            result.tracking_error = tracking_error
            result.information_ratio = info_ratio
            result.beta = beta
            result.alpha = alpha

        return result

    def rolling_metrics(
        self,
        window: int = 60
    ) -> Dict[str, np.ndarray]:
        """
        Calculate rolling performance metrics.

        Args:
            window: Rolling window size

        Returns:
            Dictionary of rolling metrics
        """
        n = len(self.returns)
        if n < window:
            raise ValueError("Not enough data for rolling calculation")

        rolling_ret = np.zeros(n - window + 1)
        rolling_vol = np.zeros(n - window + 1)
        rolling_sharpe = np.zeros(n - window + 1)
        rolling_dd = np.zeros(n - window + 1)

        rf_period = self.rf / self.periods

        for i in range(n - window + 1):
            window_returns = self.returns[i:i+window]

            # Return
            rolling_ret[i] = np.mean(window_returns) * self.periods

            # Volatility
            rolling_vol[i] = np.std(window_returns, ddof=1) * np.sqrt(self.periods)

            # Sharpe
            excess = window_returns - rf_period
            rolling_sharpe[i] = (
                np.mean(excess) / np.std(excess, ddof=1) * np.sqrt(self.periods)
                if np.std(excess, ddof=1) > 0 else 0
            )

            # Max drawdown
            cum = np.cumprod(1 + window_returns)
            running_max = np.maximum.accumulate(cum)
            dd = (cum - running_max) / running_max
            rolling_dd[i] = np.min(dd)

        return {
            'rolling_return': rolling_ret,
            'rolling_volatility': rolling_vol,
            'rolling_sharpe': rolling_sharpe,
            'rolling_max_drawdown': rolling_dd
        }


# =============================================================================
# Rebalancing
# =============================================================================

class RebalancingStrategy:
    """
    Portfolio rebalancing strategies.
    """

    @staticmethod
    def calendar_rebalance(
        current_weights: np.ndarray,
        target_weights: np.ndarray,
        rebalance: bool
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Calendar-based rebalancing.

        Args:
            current_weights: Current portfolio weights
            target_weights: Target weights
            rebalance: Whether to rebalance

        Returns:
            Tuple of (new_weights, trades)
        """
        if rebalance:
            trades = target_weights - current_weights
            return target_weights.copy(), trades
        return current_weights.copy(), np.zeros_like(current_weights)

    @staticmethod
    def threshold_rebalance(
        current_weights: np.ndarray,
        target_weights: np.ndarray,
        threshold: float = 0.05
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Threshold-based rebalancing.

        Rebalance if any weight deviates more than threshold.

        Args:
            current_weights: Current weights
            target_weights: Target weights
            threshold: Deviation threshold

        Returns:
            Tuple of (new_weights, trades)
        """
        deviations = np.abs(current_weights - target_weights)

        if np.any(deviations > threshold):
            trades = target_weights - current_weights
            return target_weights.copy(), trades
        return current_weights.copy(), np.zeros_like(current_weights)

    @staticmethod
    def band_rebalance(
        current_weights: np.ndarray,
        target_weights: np.ndarray,
        band_width: float = 0.05
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Band rebalancing (partial rebalance to band edges).

        Args:
            current_weights: Current weights
            target_weights: Target weights
            band_width: Width of tolerance band

        Returns:
            Tuple of (new_weights, trades)
        """
        new_weights = current_weights.copy()
        trades = np.zeros_like(current_weights)

        for i in range(len(current_weights)):
            upper = target_weights[i] + band_width
            lower = target_weights[i] - band_width

            if current_weights[i] > upper:
                # Rebalance down to upper band
                new_weights[i] = upper
                trades[i] = upper - current_weights[i]
            elif current_weights[i] < lower:
                # Rebalance up to lower band
                new_weights[i] = lower
                trades[i] = lower - current_weights[i]

        # Normalize if needed
        total = np.sum(new_weights)
        if abs(total - 1.0) > 1e-6:
            new_weights = new_weights / total

        return new_weights, trades

    @staticmethod
    def optimal_rebalance(
        current_weights: np.ndarray,
        target_weights: np.ndarray,
        transaction_costs: np.ndarray,
        lambda_tc: float = 1.0
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Optimal rebalancing considering transaction costs.

        Minimizes tracking error minus transaction costs.

        Args:
            current_weights: Current weights
            target_weights: Target weights
            transaction_costs: Transaction cost per asset (bps)
            lambda_tc: Transaction cost penalty

        Returns:
            Tuple of (new_weights, trades)
        """
        def objective(w):
            tracking = np.sum((w - target_weights)**2)
            trades = np.abs(w - current_weights)
            tc_cost = np.sum(trades * transaction_costs) * lambda_tc
            return tracking + tc_cost

        bounds = [(0, 1) for _ in range(len(current_weights))]
        cons = [{'type': 'eq', 'fun': lambda w: np.sum(w) - 1}]

        result = optimize.minimize(
            objective,
            current_weights,
            method='SLSQP',
            bounds=bounds,
            constraints=cons
        )

        new_weights = result.x
        trades = new_weights - current_weights

        return new_weights, trades


# =============================================================================
# Factory Functions
# =============================================================================

def create_mean_variance_optimizer(
    expected_returns: np.ndarray,
    covariance_matrix: np.ndarray,
    asset_names: Optional[List[str]] = None,
    risk_free_rate: float = 0.02
) -> MeanVarianceOptimizer:
    """Create mean-variance optimizer."""
    return MeanVarianceOptimizer(
        expected_returns=expected_returns,
        covariance_matrix=covariance_matrix,
        asset_names=asset_names,
        risk_free_rate=risk_free_rate
    )


def create_black_litterman(
    market_caps: np.ndarray,
    covariance_matrix: np.ndarray,
    asset_names: Optional[List[str]] = None,
    risk_aversion: float = 2.5,
    risk_free_rate: float = 0.02
) -> BlackLittermanModel:
    """Create Black-Litterman model."""
    return BlackLittermanModel(
        market_caps=market_caps,
        covariance_matrix=covariance_matrix,
        asset_names=asset_names,
        risk_aversion=risk_aversion,
        risk_free_rate=risk_free_rate
    )


def create_risk_parity_optimizer(
    covariance_matrix: np.ndarray,
    asset_names: Optional[List[str]] = None,
    expected_returns: Optional[np.ndarray] = None
) -> RiskParityOptimizer:
    """Create risk parity optimizer."""
    return RiskParityOptimizer(
        covariance_matrix=covariance_matrix,
        asset_names=asset_names,
        expected_returns=expected_returns
    )


def create_performance_analyzer(
    returns: np.ndarray,
    risk_free_rate: float = 0.02,
    periods_per_year: int = 252
) -> PerformanceAnalyzer:
    """Create performance analyzer."""
    return PerformanceAnalyzer(
        returns=returns,
        risk_free_rate=risk_free_rate,
        periods_per_year=periods_per_year
    )


def optimize_portfolio(
    returns: np.ndarray,
    objective: OptimizationObjective = OptimizationObjective.MAX_SHARPE,
    asset_names: Optional[List[str]] = None,
    risk_free_rate: float = 0.02,
    bounds: Optional[Tuple] = None,
    use_shrinkage: bool = True
) -> PortfolioWeights:
    """
    Quick portfolio optimization function.

    Args:
        returns: Historical returns matrix (T x N)
        objective: Optimization objective
        asset_names: Asset names
        risk_free_rate: Risk-free rate
        bounds: Weight bounds
        use_shrinkage: Whether to use Ledoit-Wolf shrinkage

    Returns:
        Optimal portfolio weights
    """
    # Estimate parameters
    expected_returns = np.mean(returns, axis=0) * 252

    if use_shrinkage:
        cov_matrix, _ = CovarianceEstimator.ledoit_wolf(returns)
        cov_matrix = cov_matrix * 252
    else:
        cov_matrix = np.cov(returns, rowvar=False) * 252

    n_assets = returns.shape[1]
    asset_names = asset_names or [f"Asset_{i}" for i in range(n_assets)]

    if objective == OptimizationObjective.RISK_PARITY:
        optimizer = RiskParityOptimizer(
            covariance_matrix=cov_matrix,
            asset_names=asset_names,
            expected_returns=expected_returns
        )
        return optimizer.equal_risk_contribution()
    else:
        optimizer = MeanVarianceOptimizer(
            expected_returns=expected_returns,
            covariance_matrix=cov_matrix,
            asset_names=asset_names,
            risk_free_rate=risk_free_rate
        )

        if objective == OptimizationObjective.MIN_VARIANCE:
            return optimizer.minimum_variance(bounds=bounds)
        elif objective == OptimizationObjective.MAX_SHARPE:
            return optimizer.maximum_sharpe(bounds=bounds)
        else:
            return optimizer.maximum_sharpe(bounds=bounds)
