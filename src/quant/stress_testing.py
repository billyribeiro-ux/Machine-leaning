"""
Revolution Alpha Engine - Stress Testing & Scenario Analysis Framework

Comprehensive risk analysis tools:
- Historical scenario replay
- Hypothetical stress scenarios
- Sensitivity analysis (Greeks-based)
- Reverse stress testing
- Macro factor shocks
- Liquidity stress
- Correlation breakdown scenarios
- Extreme value analysis
"""

import numpy as np
from scipy import stats, optimize
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Callable, Union
from enum import Enum
from abc import ABC, abstractmethod
import warnings


# =============================================================================
# Data Classes and Enums
# =============================================================================

class ScenarioType(Enum):
    """Types of stress scenarios."""
    HISTORICAL = "historical"
    HYPOTHETICAL = "hypothetical"
    SENSITIVITY = "sensitivity"
    REVERSE = "reverse"
    MACRO = "macro"
    LIQUIDITY = "liquidity"
    CORRELATION = "correlation"


@dataclass
class Scenario:
    """Definition of a stress scenario."""
    name: str
    scenario_type: ScenarioType
    shocks: Dict[str, float]  # risk_factor -> shock_size
    description: str = ""
    probability: Optional[float] = None
    historical_date: Optional[str] = None


@dataclass
class StressResult:
    """Result of stress test."""
    scenario: Scenario
    base_value: float
    stressed_value: float
    pnl_impact: float
    pnl_percent: float
    risk_factor_contributions: Dict[str, float]
    var_impact: Optional[float] = None
    es_impact: Optional[float] = None


@dataclass
class PortfolioPosition:
    """Single portfolio position."""
    instrument_id: str
    instrument_type: str  # 'equity', 'option', 'bond', etc.
    quantity: float
    market_value: float
    delta: float = 0.0
    gamma: float = 0.0
    vega: float = 0.0
    theta: float = 0.0
    rho: float = 0.0
    credit_delta: float = 0.0
    ir_delta: float = 0.0
    underlying: Optional[str] = None


@dataclass
class Portfolio:
    """Portfolio for stress testing."""
    positions: List[PortfolioPosition]
    base_currency: str = "USD"
    total_value: Optional[float] = None

    def __post_init__(self):
        if self.total_value is None:
            self.total_value = sum(p.market_value for p in self.positions)


# =============================================================================
# Historical Scenarios
# =============================================================================

class HistoricalScenarios:
    """
    Pre-defined historical stress scenarios.
    """

    # Major market crises
    SCENARIOS = {
        "black_monday_1987": Scenario(
            name="Black Monday 1987",
            scenario_type=ScenarioType.HISTORICAL,
            shocks={
                "equity": -0.226,  # S&P 500 dropped 22.6%
                "volatility": 1.5,  # VIX spike (multiplicative)
                "credit_spread": 0.005,  # 50 bps widening
                "rates_10y": -0.005,  # Flight to quality
            },
            description="October 19, 1987 stock market crash",
            historical_date="1987-10-19"
        ),

        "asian_crisis_1997": Scenario(
            name="Asian Financial Crisis 1997",
            scenario_type=ScenarioType.HISTORICAL,
            shocks={
                "equity": -0.15,
                "em_equity": -0.35,
                "volatility": 0.8,
                "fx_em": -0.25,
                "credit_spread": 0.015,
            },
            description="Asian currency and debt crisis",
            historical_date="1997-07-02"
        ),

        "ltcm_1998": Scenario(
            name="LTCM Crisis 1998",
            scenario_type=ScenarioType.HISTORICAL,
            shocks={
                "equity": -0.12,
                "volatility": 0.7,
                "credit_spread": 0.02,
                "liquidity": -0.5,
                "correlation": 0.3,  # Correlation increase
            },
            description="Long-Term Capital Management collapse",
            historical_date="1998-08-17"
        ),

        "dot_com_2000": Scenario(
            name="Dot-Com Crash 2000-2002",
            scenario_type=ScenarioType.HISTORICAL,
            shocks={
                "equity": -0.45,  # Peak to trough
                "tech_equity": -0.75,
                "volatility": 0.5,
                "credit_spread": 0.01,
            },
            description="Technology bubble burst",
            historical_date="2000-03-10"
        ),

        "gfc_2008": Scenario(
            name="Global Financial Crisis 2008",
            scenario_type=ScenarioType.HISTORICAL,
            shocks={
                "equity": -0.50,
                "volatility": 2.5,  # VIX hit 80
                "credit_spread": 0.06,  # 600 bps
                "rates_short": -0.03,
                "rates_10y": -0.015,
                "liquidity": -0.8,
                "correlation": 0.4,
            },
            description="Lehman Brothers collapse and credit crisis",
            historical_date="2008-09-15"
        ),

        "flash_crash_2010": Scenario(
            name="Flash Crash 2010",
            scenario_type=ScenarioType.HISTORICAL,
            shocks={
                "equity": -0.09,
                "volatility": 0.4,
                "liquidity": -0.9,
            },
            description="May 6, 2010 intraday crash",
            historical_date="2010-05-06"
        ),

        "covid_2020": Scenario(
            name="COVID-19 Crash 2020",
            scenario_type=ScenarioType.HISTORICAL,
            shocks={
                "equity": -0.34,
                "volatility": 2.8,  # VIX hit 82
                "credit_spread": 0.04,
                "oil": -0.70,  # Oil went negative
                "rates_short": -0.015,
                "correlation": 0.5,
            },
            description="COVID-19 pandemic market crash",
            historical_date="2020-03-16"
        ),

        "taper_tantrum_2013": Scenario(
            name="Taper Tantrum 2013",
            scenario_type=ScenarioType.HISTORICAL,
            shocks={
                "rates_10y": 0.013,  # 130 bps rise
                "em_equity": -0.15,
                "fx_em": -0.10,
                "credit_spread": 0.005,
            },
            description="Fed taper announcement",
            historical_date="2013-05-22"
        ),

        "vol_shock_2018": Scenario(
            name="Volmageddon 2018",
            scenario_type=ScenarioType.HISTORICAL,
            shocks={
                "equity": -0.10,
                "volatility": 1.5,
                "short_vol": -0.95,  # XIV collapse
            },
            description="February 2018 volatility spike",
            historical_date="2018-02-05"
        ),

        "svb_2023": Scenario(
            name="SVB Bank Crisis 2023",
            scenario_type=ScenarioType.HISTORICAL,
            shocks={
                "bank_equity": -0.25,
                "rates_2y": -0.01,
                "credit_spread": 0.015,
                "regional_bank": -0.40,
            },
            description="Silicon Valley Bank collapse",
            historical_date="2023-03-10"
        ),
    }

    @classmethod
    def get_scenario(cls, name: str) -> Scenario:
        """Get a pre-defined historical scenario."""
        if name not in cls.SCENARIOS:
            raise ValueError(f"Unknown scenario: {name}. Available: {list(cls.SCENARIOS.keys())}")
        return cls.SCENARIOS[name]

    @classmethod
    def list_scenarios(cls) -> List[str]:
        """List available historical scenarios."""
        return list(cls.SCENARIOS.keys())


# =============================================================================
# Stress Testing Engine
# =============================================================================

class StressTestEngine:
    """
    Main stress testing engine.

    Applies scenarios to portfolios and calculates P&L impacts.
    """

    def __init__(
        self,
        portfolio: Portfolio,
        risk_factor_mappings: Optional[Dict[str, str]] = None
    ):
        """
        Initialize stress test engine.

        Args:
            portfolio: Portfolio to stress test
            risk_factor_mappings: Map instrument types to risk factors
        """
        self.portfolio = portfolio
        self.risk_factor_mappings = risk_factor_mappings or self._default_mappings()

    def _default_mappings(self) -> Dict[str, str]:
        """Default risk factor mappings."""
        return {
            "equity": "equity",
            "option": "equity",  # Options mapped to underlying
            "bond": "rates_10y",
            "fx": "fx",
            "commodity": "commodity",
            "credit": "credit_spread",
        }

    def apply_scenario(
        self,
        scenario: Scenario,
        full_revaluation: bool = False
    ) -> StressResult:
        """
        Apply a stress scenario to the portfolio.

        Args:
            scenario: Scenario to apply
            full_revaluation: Whether to do full repricing (vs Greeks approximation)

        Returns:
            StressResult with P&L impact
        """
        base_value = self.portfolio.total_value
        risk_factor_contributions = {}

        if full_revaluation:
            stressed_value = self._full_revaluation(scenario)
        else:
            stressed_value = self._greeks_approximation(scenario, risk_factor_contributions)

        pnl_impact = stressed_value - base_value
        pnl_percent = pnl_impact / base_value if base_value != 0 else 0

        return StressResult(
            scenario=scenario,
            base_value=base_value,
            stressed_value=stressed_value,
            pnl_impact=pnl_impact,
            pnl_percent=pnl_percent,
            risk_factor_contributions=risk_factor_contributions
        )

    def _greeks_approximation(
        self,
        scenario: Scenario,
        contributions: Dict[str, float]
    ) -> float:
        """
        Calculate stressed value using Greeks approximation.

        Taylor expansion: dV ≈ Delta*dS + 0.5*Gamma*dS^2 + Vega*dσ + ...
        """
        total_pnl = 0

        for position in self.portfolio.positions:
            position_pnl = 0

            # Equity shock
            if "equity" in scenario.shocks:
                equity_shock = scenario.shocks["equity"]

                # Delta P&L
                delta_pnl = position.delta * equity_shock * position.market_value
                position_pnl += delta_pnl

                # Gamma P&L (second order)
                gamma_pnl = 0.5 * position.gamma * (equity_shock**2) * position.market_value
                position_pnl += gamma_pnl

                contributions["equity_delta"] = contributions.get("equity_delta", 0) + delta_pnl
                contributions["equity_gamma"] = contributions.get("equity_gamma", 0) + gamma_pnl

            # Volatility shock
            if "volatility" in scenario.shocks:
                vol_shock = scenario.shocks["volatility"]
                # Vega is per 1% vol change, shock is multiplicative
                vega_pnl = position.vega * vol_shock * 100
                position_pnl += vega_pnl
                contributions["vega"] = contributions.get("vega", 0) + vega_pnl

            # Interest rate shock
            if "rates_10y" in scenario.shocks:
                rate_shock = scenario.shocks["rates_10y"]
                rho_pnl = position.rho * rate_shock * 100  # Per 1% rate change
                position_pnl += rho_pnl
                contributions["rho"] = contributions.get("rho", 0) + rho_pnl

            # Credit spread shock
            if "credit_spread" in scenario.shocks:
                credit_shock = scenario.shocks["credit_spread"]
                credit_pnl = position.credit_delta * credit_shock * 10000  # Per bp
                position_pnl += credit_pnl
                contributions["credit"] = contributions.get("credit", 0) + credit_pnl

            # Theta (time decay - optional)
            if "time" in scenario.shocks:
                time_shock = scenario.shocks["time"]  # In days
                theta_pnl = position.theta * time_shock
                position_pnl += theta_pnl
                contributions["theta"] = contributions.get("theta", 0) + theta_pnl

            total_pnl += position_pnl

        return self.portfolio.total_value + total_pnl

    def _full_revaluation(self, scenario: Scenario) -> float:
        """
        Full repricing under stressed parameters.

        Requires pricing functions for each instrument type.
        """
        # Placeholder for full revaluation
        # In practice, would call instrument-specific pricing models
        return self._greeks_approximation(scenario, {})

    def run_all_historical(self) -> List[StressResult]:
        """Run all historical scenarios."""
        results = []
        for name in HistoricalScenarios.list_scenarios():
            scenario = HistoricalScenarios.get_scenario(name)
            result = self.apply_scenario(scenario)
            results.append(result)
        return sorted(results, key=lambda x: x.pnl_impact)

    def sensitivity_analysis(
        self,
        risk_factor: str,
        shock_range: Tuple[float, float] = (-0.20, 0.20),
        n_points: int = 21
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Run sensitivity analysis for a single risk factor.

        Args:
            risk_factor: Risk factor to shock
            shock_range: Range of shocks to apply
            n_points: Number of shock points

        Returns:
            Tuple of (shock_values, pnl_values)
        """
        shocks = np.linspace(shock_range[0], shock_range[1], n_points)
        pnl_values = []

        for shock in shocks:
            scenario = Scenario(
                name=f"{risk_factor}_shock_{shock:.2%}",
                scenario_type=ScenarioType.SENSITIVITY,
                shocks={risk_factor: shock}
            )
            result = self.apply_scenario(scenario)
            pnl_values.append(result.pnl_impact)

        return shocks, np.array(pnl_values)

    def reverse_stress_test(
        self,
        target_loss: float,
        risk_factors: List[str],
        max_iterations: int = 100
    ) -> Scenario:
        """
        Find scenario that produces target loss.

        Args:
            target_loss: Target P&L loss (negative number)
            risk_factors: Risk factors to vary
            max_iterations: Maximum optimization iterations

        Returns:
            Scenario that produces the target loss
        """
        def objective(shocks):
            scenario = Scenario(
                name="reverse_stress",
                scenario_type=ScenarioType.REVERSE,
                shocks=dict(zip(risk_factors, shocks))
            )
            result = self.apply_scenario(scenario)
            return (result.pnl_impact - target_loss)**2

        # Initial guess
        x0 = np.zeros(len(risk_factors))

        # Bounds (reasonable shock ranges)
        bounds = [(-0.5, 0.5) for _ in risk_factors]

        result = optimize.minimize(
            objective,
            x0,
            method='L-BFGS-B',
            bounds=bounds,
            options={'maxiter': max_iterations}
        )

        return Scenario(
            name="reverse_stress_result",
            scenario_type=ScenarioType.REVERSE,
            shocks=dict(zip(risk_factors, result.x)),
            description=f"Scenario producing {target_loss:,.0f} loss"
        )


# =============================================================================
# Scenario Generator
# =============================================================================

class ScenarioGenerator:
    """
    Generate hypothetical stress scenarios.
    """

    @staticmethod
    def create_parallel_shift(
        factor: str,
        magnitude: float,
        name: Optional[str] = None
    ) -> Scenario:
        """Create simple parallel shift scenario."""
        return Scenario(
            name=name or f"{factor}_{magnitude:+.1%}",
            scenario_type=ScenarioType.HYPOTHETICAL,
            shocks={factor: magnitude}
        )

    @staticmethod
    def create_multi_factor(
        shocks: Dict[str, float],
        name: str,
        description: str = ""
    ) -> Scenario:
        """Create multi-factor stress scenario."""
        return Scenario(
            name=name,
            scenario_type=ScenarioType.HYPOTHETICAL,
            shocks=shocks,
            description=description
        )

    @staticmethod
    def create_correlation_stress(
        base_scenario: Scenario,
        correlation_increase: float = 0.3
    ) -> Scenario:
        """
        Create scenario with correlation breakdown.

        During stress, correlations typically increase.
        """
        new_shocks = base_scenario.shocks.copy()
        new_shocks["correlation"] = correlation_increase

        return Scenario(
            name=f"{base_scenario.name}_correlation_stress",
            scenario_type=ScenarioType.CORRELATION,
            shocks=new_shocks,
            description=f"{base_scenario.description} with correlation increase"
        )

    @staticmethod
    def create_liquidity_stress(
        market_impact: float = 0.1,
        bid_ask_widening: float = 3.0
    ) -> Scenario:
        """Create liquidity stress scenario."""
        return Scenario(
            name="liquidity_crisis",
            scenario_type=ScenarioType.LIQUIDITY,
            shocks={
                "liquidity": -0.5,
                "market_impact": market_impact,
                "bid_ask_spread": bid_ask_widening,
            },
            description="Severe liquidity crisis"
        )

    @staticmethod
    def create_monte_carlo_scenarios(
        mean_returns: np.ndarray,
        covariance: np.ndarray,
        factor_names: List[str],
        n_scenarios: int = 1000,
        confidence: float = 0.99,
        seed: Optional[int] = None
    ) -> List[Scenario]:
        """
        Generate Monte Carlo stress scenarios.

        Args:
            mean_returns: Expected returns for each factor
            covariance: Covariance matrix of factors
            factor_names: Names of risk factors
            n_scenarios: Number of scenarios to generate
            confidence: Confidence level for tail scenarios
            seed: Random seed

        Returns:
            List of stress scenarios (tail scenarios)
        """
        if seed is not None:
            np.random.seed(seed)

        # Generate correlated returns
        scenarios_data = np.random.multivariate_normal(mean_returns, covariance, n_scenarios)

        # Calculate portfolio-level impact (simple sum for now)
        portfolio_impacts = np.sum(scenarios_data, axis=1)

        # Find tail scenarios
        tail_threshold = np.percentile(portfolio_impacts, (1 - confidence) * 100)
        tail_indices = np.where(portfolio_impacts <= tail_threshold)[0]

        scenarios = []
        for idx in tail_indices:
            shocks = dict(zip(factor_names, scenarios_data[idx]))
            scenarios.append(Scenario(
                name=f"mc_tail_{idx}",
                scenario_type=ScenarioType.HYPOTHETICAL,
                shocks=shocks,
                probability=1 / n_scenarios
            ))

        return scenarios


# =============================================================================
# Extreme Value Analysis
# =============================================================================

class ExtremeValueAnalysis:
    """
    Extreme value theory for tail risk analysis.
    """

    def __init__(self, returns: np.ndarray):
        """
        Initialize EVA with historical returns.

        Args:
            returns: Historical return series
        """
        self.returns = returns
        self.losses = -returns  # Convention: positive losses
        self.gev_params = None
        self.gpd_params = None

    def fit_gev(self, block_size: int = 21) -> Dict[str, float]:
        """
        Fit Generalized Extreme Value distribution.

        Uses block maxima approach.

        Args:
            block_size: Block size (e.g., 21 for monthly)

        Returns:
            GEV parameters (shape, loc, scale)
        """
        n_blocks = len(self.losses) // block_size
        block_maxima = []

        for i in range(n_blocks):
            block = self.losses[i*block_size:(i+1)*block_size]
            block_maxima.append(np.max(block))

        block_maxima = np.array(block_maxima)

        # Fit GEV
        shape, loc, scale = stats.genextreme.fit(block_maxima)

        self.gev_params = {
            'shape': shape,
            'loc': loc,
            'scale': scale
        }

        return self.gev_params

    def fit_gpd(self, threshold_quantile: float = 0.95) -> Dict[str, float]:
        """
        Fit Generalized Pareto Distribution.

        Peaks over threshold approach.

        Args:
            threshold_quantile: Threshold as quantile

        Returns:
            GPD parameters (shape, loc, scale)
        """
        threshold = np.quantile(self.losses, threshold_quantile)
        exceedances = self.losses[self.losses > threshold] - threshold

        if len(exceedances) < 10:
            warnings.warn("Few exceedances, GPD fit may be unreliable")

        # Fit GPD
        shape, loc, scale = stats.genpareto.fit(exceedances, floc=0)

        self.gpd_params = {
            'shape': shape,
            'scale': scale,
            'threshold': threshold,
            'n_exceedances': len(exceedances),
            'exceedance_rate': len(exceedances) / len(self.losses)
        }

        return self.gpd_params

    def var_evt(self, confidence: float = 0.99) -> float:
        """
        Calculate VaR using EVT (GPD).

        Args:
            confidence: Confidence level

        Returns:
            VaR estimate
        """
        if self.gpd_params is None:
            self.fit_gpd()

        u = self.gpd_params['threshold']
        xi = self.gpd_params['shape']
        sigma = self.gpd_params['scale']
        n_u = self.gpd_params['n_exceedances']
        n = len(self.losses)

        # VaR formula for GPD
        p = 1 - confidence
        if xi != 0:
            var = u + sigma / xi * ((n / n_u * p)**(-xi) - 1)
        else:
            var = u - sigma * np.log(n / n_u * p)

        return var

    def es_evt(self, confidence: float = 0.99) -> float:
        """
        Calculate Expected Shortfall using EVT.

        Args:
            confidence: Confidence level

        Returns:
            ES estimate
        """
        var = self.var_evt(confidence)

        xi = self.gpd_params['shape']
        sigma = self.gpd_params['scale']
        u = self.gpd_params['threshold']

        if xi < 1:
            es = var / (1 - xi) + (sigma - xi * u) / (1 - xi)
        else:
            es = np.inf

        return es

    def return_level(self, return_period: float) -> float:
        """
        Calculate return level for given return period.

        Args:
            return_period: Return period in same units as data frequency

        Returns:
            Return level (loss that occurs once per return_period)
        """
        if self.gpd_params is None:
            self.fit_gpd()

        u = self.gpd_params['threshold']
        xi = self.gpd_params['shape']
        sigma = self.gpd_params['scale']
        zeta = self.gpd_params['exceedance_rate']

        m = return_period
        if xi != 0:
            z_m = u + sigma / xi * ((m * zeta)**xi - 1)
        else:
            z_m = u + sigma * np.log(m * zeta)

        return z_m


# =============================================================================
# Macro Stress Framework
# =============================================================================

class MacroStressFramework:
    """
    Macro-economic stress testing framework.

    Links macro variables to financial risk factors.
    """

    # Default factor sensitivities to macro variables
    DEFAULT_SENSITIVITIES = {
        # GDP shock of -1% impacts:
        "gdp": {
            "equity": -0.05,  # 5% equity drop per 1% GDP drop
            "credit_spread": 0.002,  # 20 bps widening
            "volatility": 0.2,  # 20% vol increase
        },
        # Inflation shock of +1%:
        "inflation": {
            "rates_10y": 0.008,  # 80 bps rate increase
            "equity": -0.02,
            "tips_breakeven": 0.007,
        },
        # Unemployment shock of +1%:
        "unemployment": {
            "equity": -0.03,
            "credit_spread": 0.003,
            "consumer_discretionary": -0.05,
        },
        # Oil price shock of +10%:
        "oil": {
            "inflation": 0.002,
            "energy_equity": 0.08,
            "transportation": -0.03,
        },
    }

    def __init__(
        self,
        sensitivities: Optional[Dict[str, Dict[str, float]]] = None
    ):
        """
        Initialize macro stress framework.

        Args:
            sensitivities: Custom sensitivities (macro_var -> {risk_factor: sensitivity})
        """
        self.sensitivities = sensitivities or self.DEFAULT_SENSITIVITIES

    def create_macro_scenario(
        self,
        macro_shocks: Dict[str, float],
        name: str
    ) -> Scenario:
        """
        Create financial scenario from macro shocks.

        Args:
            macro_shocks: Macro variable shocks (e.g., {"gdp": -0.02})
            name: Scenario name

        Returns:
            Financial market scenario
        """
        risk_factor_shocks = {}

        for macro_var, shock in macro_shocks.items():
            if macro_var in self.sensitivities:
                for risk_factor, sensitivity in self.sensitivities[macro_var].items():
                    current = risk_factor_shocks.get(risk_factor, 0)
                    risk_factor_shocks[risk_factor] = current + sensitivity * shock * 100

        return Scenario(
            name=name,
            scenario_type=ScenarioType.MACRO,
            shocks=risk_factor_shocks,
            description=f"Macro scenario: {macro_shocks}"
        )

    def recession_scenario(self, severity: str = "moderate") -> Scenario:
        """
        Pre-built recession scenario.

        Args:
            severity: "mild", "moderate", or "severe"

        Returns:
            Recession scenario
        """
        severities = {
            "mild": {"gdp": -0.01, "unemployment": 0.02},
            "moderate": {"gdp": -0.025, "unemployment": 0.04},
            "severe": {"gdp": -0.05, "unemployment": 0.08}
        }

        macro_shocks = severities.get(severity, severities["moderate"])
        return self.create_macro_scenario(
            macro_shocks,
            f"recession_{severity}"
        )

    def inflation_scenario(self, severity: str = "moderate") -> Scenario:
        """Pre-built inflation shock scenario."""
        severities = {
            "mild": {"inflation": 0.02},
            "moderate": {"inflation": 0.04},
            "severe": {"inflation": 0.08}  # Stagflation
        }

        macro_shocks = severities.get(severity, severities["moderate"])
        return self.create_macro_scenario(
            macro_shocks,
            f"inflation_{severity}"
        )

    def stagflation_scenario(self) -> Scenario:
        """Combined high inflation and recession."""
        return self.create_macro_scenario(
            {"gdp": -0.03, "inflation": 0.06, "unemployment": 0.05},
            "stagflation"
        )


# =============================================================================
# Stress Test Report Generator
# =============================================================================

class StressTestReport:
    """
    Generate comprehensive stress test reports.
    """

    def __init__(self, results: List[StressResult]):
        """
        Initialize report generator.

        Args:
            results: List of stress test results
        """
        self.results = results

    def summary_statistics(self) -> Dict:
        """Generate summary statistics."""
        pnl_impacts = [r.pnl_impact for r in self.results]

        return {
            "n_scenarios": len(self.results),
            "worst_case": min(pnl_impacts),
            "best_case": max(pnl_impacts),
            "average_impact": np.mean(pnl_impacts),
            "median_impact": np.median(pnl_impacts),
            "std_impact": np.std(pnl_impacts),
            "worst_scenario": self.results[np.argmin(pnl_impacts)].scenario.name,
        }

    def worst_scenarios(self, n: int = 5) -> List[StressResult]:
        """Get n worst scenarios by P&L impact."""
        return sorted(self.results, key=lambda x: x.pnl_impact)[:n]

    def risk_factor_attribution(self) -> Dict[str, float]:
        """Aggregate risk factor contributions across scenarios."""
        attribution = {}

        for result in self.results:
            for factor, contribution in result.risk_factor_contributions.items():
                attribution[factor] = attribution.get(factor, 0) + contribution

        return attribution

    def generate_text_report(self) -> str:
        """Generate text report."""
        summary = self.summary_statistics()
        worst = self.worst_scenarios(5)

        report = []
        report.append("=" * 60)
        report.append("STRESS TEST REPORT")
        report.append("=" * 60)
        report.append("")
        report.append("SUMMARY STATISTICS")
        report.append("-" * 40)
        report.append(f"Number of scenarios: {summary['n_scenarios']}")
        report.append(f"Worst case P&L: {summary['worst_case']:,.0f}")
        report.append(f"Best case P&L: {summary['best_case']:,.0f}")
        report.append(f"Average impact: {summary['average_impact']:,.0f}")
        report.append(f"Worst scenario: {summary['worst_scenario']}")
        report.append("")
        report.append("TOP 5 WORST SCENARIOS")
        report.append("-" * 40)

        for i, result in enumerate(worst, 1):
            report.append(f"{i}. {result.scenario.name}")
            report.append(f"   P&L Impact: {result.pnl_impact:,.0f} ({result.pnl_percent:.2%})")

        report.append("")
        report.append("RISK FACTOR ATTRIBUTION")
        report.append("-" * 40)
        attribution = self.risk_factor_attribution()
        for factor, total in sorted(attribution.items(), key=lambda x: x[1]):
            report.append(f"{factor}: {total:,.0f}")

        return "\n".join(report)


# =============================================================================
# Factory Functions
# =============================================================================

def create_stress_test_engine(portfolio: Portfolio) -> StressTestEngine:
    """Create stress test engine for portfolio."""
    return StressTestEngine(portfolio)


def create_macro_framework(
    custom_sensitivities: Optional[Dict] = None
) -> MacroStressFramework:
    """Create macro stress framework."""
    return MacroStressFramework(custom_sensitivities)


def run_standard_stress_tests(portfolio: Portfolio) -> StressTestReport:
    """
    Run standard suite of stress tests.

    Args:
        portfolio: Portfolio to stress test

    Returns:
        StressTestReport with all results
    """
    engine = StressTestEngine(portfolio)

    results = []

    # Historical scenarios
    for name in HistoricalScenarios.list_scenarios():
        scenario = HistoricalScenarios.get_scenario(name)
        result = engine.apply_scenario(scenario)
        results.append(result)

    # Hypothetical scenarios
    generator = ScenarioGenerator()

    # Simple shocks
    for factor in ["equity", "volatility", "rates_10y", "credit_spread"]:
        for magnitude in [-0.10, -0.20, -0.30]:
            scenario = generator.create_parallel_shift(factor, magnitude)
            result = engine.apply_scenario(scenario)
            results.append(result)

    # Macro scenarios
    macro = MacroStressFramework()
    for severity in ["mild", "moderate", "severe"]:
        scenario = macro.recession_scenario(severity)
        result = engine.apply_scenario(scenario)
        results.append(result)

    return StressTestReport(results)
