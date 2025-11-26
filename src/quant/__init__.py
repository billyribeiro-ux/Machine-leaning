"""
Revolution Alpha Engine - Quantitative Finance Module

Comprehensive institutional-grade quantitative finance library:

1. Stochastic Calculus & Brownian Motion
   - Geometric Brownian Motion (GBM)
   - Ornstein-Uhlenbeck process
   - Cox-Ingersoll-Ross (CIR) process
   - Heston stochastic volatility
   - Jump-diffusion models (Merton, Kou)
   - SABR model
   - Variance Gamma process
   - Fractional Brownian Motion
   - Monte Carlo simulation engines

2. Derivatives Pricing Models
   - Black-Scholes model
   - Black-76 (futures/commodities)
   - Bachelier model
   - Binomial trees (CRR, Jarrow-Rudd)
   - Finite difference methods (explicit, implicit, Crank-Nicolson)
   - Heston analytical (FFT/Carr-Madan)
   - Barrier options
   - Asian options
   - Lookback options
   - Local volatility (Dupire)

3. Term Structure & Interest Rate Models
   - Yield curve construction
   - Nelson-Siegel and Svensson models
   - Short-rate models (Vasicek, CIR, Hull-White)
   - LIBOR Market Model (BGM)
   - Interest rate derivatives (caps, floors, swaptions)

4. Credit Risk, VaR & XVA
   - Value at Risk (Historical, Parametric, Monte Carlo, EWMA, GARCH)
   - Expected Shortfall (CVaR)
   - Merton structural credit model
   - Reduced-form (intensity) models
   - CDS pricing
   - XVA framework (CVA, DVA, FVA, MVA, KVA)
   - Credit portfolio models (Vasicek, CreditMetrics)

5. Portfolio Theory & Risk Modeling
   - Mean-Variance Optimization (Markowitz)
   - Black-Litterman model
   - Risk Parity and Hierarchical Risk Parity
   - Factor models (CAPM, Fama-French)
   - Covariance estimation (shrinkage, Ledoit-Wolf)
   - Risk decomposition and attribution
   - Performance analytics
   - Rebalancing strategies

Usage:
    from src.quant import (
        # Stochastic processes
        GeometricBrownianMotion, HestonModel, MertonJumpDiffusion,

        # Derivatives pricing
        BlackScholes, BinomialTree, FiniteDifference,

        # Term structure
        YieldCurve, NelsonSiegel, HullWhite,

        # Credit risk
        ValueAtRisk, MertonModel, CDSPricer, XVACalculator,

        # Portfolio
        MeanVarianceOptimizer, BlackLittermanModel, RiskParityOptimizer
    )
"""

# =============================================================================
# Stochastic Calculus & Brownian Motion
# =============================================================================
from .stochastic import (
    # Core processes
    BrownianMotion,
    GeometricBrownianMotion,
    OrnsteinUhlenbeck,
    CIRProcess,

    # Jump-diffusion models
    MertonJumpDiffusion,
    KouJumpDiffusion,

    # Stochastic volatility
    HestonModel,
    SABRModel,

    # Other processes
    VarianceGammaProcess,
    FractionalBrownianMotion,

    # Monte Carlo
    MonteCarloEngine,
    VarianceReduction,

    # Factory functions
    create_gbm,
    create_ou,
    create_cir,
    create_heston,
    create_merton_jd,
    create_sabr,
    create_variance_gamma,
    create_fbm,
)

# =============================================================================
# Derivatives Pricing Models
# =============================================================================
from .derivatives import (
    # Closed-form models
    BlackScholes,
    Black76,
    Bachelier,

    # Numerical methods
    BinomialTree,
    FiniteDifference,
    TreeMethod,
    FDMethod,

    # Stochastic vol pricing
    HestonAnalytical,

    # Exotic options
    BarrierOption,
    AsianOption,
    LookbackOption,
    BarrierType,

    # Local volatility
    LocalVolatility,

    # Enums and data classes
    OptionType,
    ExerciseStyle,
    GreeksResult,
    PricingResult,

    # Factory functions
    price_european_option,
    price_american_option,
    calculate_implied_vol,
)

# =============================================================================
# Term Structure & Interest Rate Models
# =============================================================================
from .term_structure import (
    # Yield curves
    YieldCurve,
    NelsonSiegel,
    Svensson,
    CurveInterpolation,

    # Short-rate models
    VasicekModel,
    CIRModel,
    HullWhiteModel,

    # Market models
    LIBORMarketModel,

    # IR derivatives
    InterestRateDerivatives,

    # Data classes
    ForwardRate,
    SwapRate,
    CapFloorPrice,

    # Factory functions
    create_yield_curve,
    create_vasicek,
    create_cir_model,
    create_hull_white,
    bootstrap_curve,
)

# =============================================================================
# Credit Risk, VaR & XVA
# =============================================================================
from .credit_risk import (
    # VaR models
    ValueAtRisk,
    ExpectedShortfall,
    VaRMethod,
    VaRResult,

    # Credit risk models
    MertonModel,
    ReducedFormModel,
    CreditRiskMetrics,

    # CDS pricing
    CDSPricer,
    CDSContract,

    # XVA
    XVACalculator,
    XVAResult,

    # Portfolio credit models
    VasicekPortfolioModel,
    CreditMetrics,

    # PD and LGD models
    PDModel,
    LGDModel,

    # Factory functions
    create_var_calculator,
    create_merton_model,
    create_reduced_form_model,
    create_cds_pricer,
    create_xva_calculator,
    create_vasicek_model,
    create_credit_metrics,
    calculate_credit_var,
)

# =============================================================================
# Portfolio Theory & Risk Modeling
# =============================================================================
from .portfolio import (
    # Optimizers
    MeanVarianceOptimizer,
    BlackLittermanModel,
    RiskParityOptimizer,

    # Factor models
    FactorModel,
    FamaFrenchModel,

    # Covariance estimation
    CovarianceEstimator,

    # Risk decomposition
    RiskDecomposer,
    RiskDecomposition,

    # Performance
    PerformanceAnalyzer,
    PerformanceMetrics,

    # Rebalancing
    RebalancingStrategy,

    # Enums and data classes
    OptimizationObjective,
    RiskMeasure,
    PortfolioWeights,
    FactorExposure,

    # Factory functions
    create_mean_variance_optimizer,
    create_black_litterman,
    create_risk_parity_optimizer,
    create_performance_analyzer,
    optimize_portfolio,
)

__all__ = [
    # Stochastic Calculus
    "BrownianMotion",
    "GeometricBrownianMotion",
    "OrnsteinUhlenbeck",
    "CIRProcess",
    "MertonJumpDiffusion",
    "KouJumpDiffusion",
    "HestonModel",
    "SABRModel",
    "VarianceGammaProcess",
    "FractionalBrownianMotion",
    "MonteCarloEngine",
    "VarianceReduction",
    "create_gbm",
    "create_ou",
    "create_cir",
    "create_heston",
    "create_merton_jd",
    "create_sabr",
    "create_variance_gamma",
    "create_fbm",

    # Derivatives Pricing
    "BlackScholes",
    "Black76",
    "Bachelier",
    "BinomialTree",
    "FiniteDifference",
    "TreeMethod",
    "FDMethod",
    "HestonAnalytical",
    "BarrierOption",
    "AsianOption",
    "LookbackOption",
    "BarrierType",
    "LocalVolatility",
    "OptionType",
    "ExerciseStyle",
    "GreeksResult",
    "PricingResult",
    "price_european_option",
    "price_american_option",
    "calculate_implied_vol",

    # Term Structure
    "YieldCurve",
    "NelsonSiegel",
    "Svensson",
    "CurveInterpolation",
    "VasicekModel",
    "CIRModel",
    "HullWhiteModel",
    "LIBORMarketModel",
    "InterestRateDerivatives",
    "ForwardRate",
    "SwapRate",
    "CapFloorPrice",
    "create_yield_curve",
    "create_vasicek",
    "create_cir_model",
    "create_hull_white",
    "bootstrap_curve",

    # Credit Risk & VaR
    "ValueAtRisk",
    "ExpectedShortfall",
    "VaRMethod",
    "VaRResult",
    "MertonModel",
    "ReducedFormModel",
    "CreditRiskMetrics",
    "CDSPricer",
    "CDSContract",
    "XVACalculator",
    "XVAResult",
    "VasicekPortfolioModel",
    "CreditMetrics",
    "PDModel",
    "LGDModel",
    "create_var_calculator",
    "create_merton_model",
    "create_reduced_form_model",
    "create_cds_pricer",
    "create_xva_calculator",
    "create_vasicek_model",
    "create_credit_metrics",
    "calculate_credit_var",

    # Portfolio Theory
    "MeanVarianceOptimizer",
    "BlackLittermanModel",
    "RiskParityOptimizer",
    "FactorModel",
    "FamaFrenchModel",
    "CovarianceEstimator",
    "RiskDecomposer",
    "RiskDecomposition",
    "PerformanceAnalyzer",
    "PerformanceMetrics",
    "RebalancingStrategy",
    "OptimizationObjective",
    "RiskMeasure",
    "PortfolioWeights",
    "FactorExposure",
    "create_mean_variance_optimizer",
    "create_black_litterman",
    "create_risk_parity_optimizer",
    "create_performance_analyzer",
    "optimize_portfolio",
]

__version__ = "0.1.0"
