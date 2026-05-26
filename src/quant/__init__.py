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

6. High-Performance Computing
   - GPU acceleration (CuPy)
   - Numba JIT compilation
   - Parallel Monte Carlo
   - Streaming for large simulations

7. Exotic Options
   - Rainbow options (multi-asset)
   - Spread options
   - Compound options
   - Chooser options
   - Variance and volatility swaps
   - Cliquet/Ratchet options
   - Autocallables
   - Forward start options

8. Model Calibration
   - SVI/SSVI volatility surface fitting
   - Heston model calibration
   - SABR calibration
   - Rough volatility models
   - Local volatility extraction

9. Stress Testing & Scenario Analysis
   - Historical scenarios
   - Hypothetical stress tests
   - Reverse stress testing
   - Macro-economic scenarios
   - Extreme value analysis

10. Backtesting Framework
    - Event-driven backtesting
    - Walk-forward optimization
    - Monte Carlo simulation
    - Transaction cost modeling
    - Statistical significance testing

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
        MeanVarianceOptimizer, BlackLittermanModel, RiskParityOptimizer,

        # High performance
        HighPerformanceMC, create_high_performance_mc,

        # Exotic options
        RainbowOption, SpreadOption, VarianceSwap, Autocallable,

        # Calibration
        HestonCalibrator, SABRCalibrator, SVI, SSVI,

        # Stress testing
        StressTestEngine, HistoricalScenarios, MacroStressFramework,

        # Backtesting
        BacktestEngine, WalkForwardOptimizer, MonteCarloBacktest
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

    # Market models
    LIBORMarketModel,

    # IR derivatives
    InterestRateDerivatives,

    # Data classes
    SwapRate,

    # Factory functions
    create_yield_curve,
    create_vasicek,
    create_hull_white,
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

# =============================================================================
# High-Performance Computing
# =============================================================================
from .performance import (
    # Main classes
    HighPerformanceMC,
    StreamingMC,
    GPUAccelerator,

    # Configuration
    PerformanceConfig,
    ComputeBackend,

    # Factory functions
    create_high_performance_mc,
    benchmark_backends,
    get_system_info,
    get_available_backend,

    # Numba-accelerated functions (internal)
    NUMBA_AVAILABLE,
    GPU_AVAILABLE,
)

# =============================================================================
# Exotic Options
# =============================================================================
from .exotic_options import (
    # Multi-asset options
    RainbowOption,
    RainbowType,

    # Spread options
    SpreadOption,
    SpreadType,

    # Compound and chooser
    CompoundOption,
    ChooserOption,

    # Variance/volatility
    VarianceSwap,
    VolatilitySwap,

    # Structured products
    CliquetOption,
    Autocallable,
    ForwardStartOption,
    PowerOption,

    # Results
    ExoticPricingResult,

    # Factory functions
    create_rainbow_option,
    create_spread_option,
    create_variance_swap,
    create_autocallable,
)

# =============================================================================
# Model Calibration
# =============================================================================
from .calibration import (
    # Volatility surfaces
    SVI,
    SSVI,
    VolatilitySurface,

    # Model calibrators
    HestonCalibrator,
    SABRCalibrator,
    LocalVolCalibrator,
    RoughBergomiCalibrator,

    # Implied vol
    ImpliedVolCalculator,

    # Data classes
    MarketData,
    CalibrationResult,
    CalibrationObjective,

    # Factory functions
    create_heston_calibrator,
    create_sabr_calibrator,
    create_svi_fitter,
    create_ssvi_fitter,
    calibrate_volatility_surface,
)

# =============================================================================
# Stress Testing & Scenario Analysis
# =============================================================================
from .stress_testing import (
    # Main engine
    StressTestEngine,

    # Scenarios
    Scenario,
    ScenarioType,
    HistoricalScenarios,
    ScenarioGenerator,

    # Macro framework
    MacroStressFramework,

    # EVT
    ExtremeValueAnalysis,

    # Portfolio
    Portfolio,
    PortfolioPosition,

    # Results
    StressResult,
    StressTestReport,

    # Factory functions
    create_stress_test_engine,
    create_macro_framework,
    run_standard_stress_tests,
)

# =============================================================================
# Backtesting Framework
# =============================================================================
from .backtesting import (
    # Main engine
    BacktestEngine,

    # Strategy
    Strategy,
    StrategyConfig,

    # Orders and trades
    Order,
    OrderType,
    OrderSide,
    Trade,
    Position,
    PositionType,
    Bar,

    # Transaction costs
    TransactionCostModel,
    SimpleTransactionCost,
    TieredCommission,
    MarketImpactModel,

    # Position sizing
    PositionSizer,
    FixedFractionSizer,
    VolatilityTargetSizer,
    KellyCriterionSizer,
    RiskParitySizer,

    # Walk-forward
    WalkForwardOptimizer,

    # Monte Carlo
    MonteCarloBacktest,

    # Statistics
    SignificanceTester,

    # Results
    BacktestResult,

    # Factory functions
    create_backtest_engine,
    create_walk_forward_optimizer,
    run_quick_backtest,
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
    "HestonAnalytical",
    "BarrierOption",
    "AsianOption",
    "LookbackOption",
    "BarrierType",
    "LocalVolatility",
    "OptionType",
    "ExerciseStyle",
    "PricingResult",
    "price_european_option",
    "price_american_option",
    "calculate_implied_vol",

    # Term Structure
    "YieldCurve",
    "NelsonSiegel",
    "Svensson",
    "LIBORMarketModel",
    "InterestRateDerivatives",
    "SwapRate",
    "create_yield_curve",
    "create_vasicek",
    "create_hull_white",

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

    # High Performance
    "HighPerformanceMC",
    "StreamingMC",
    "GPUAccelerator",
    "PerformanceConfig",
    "ComputeBackend",
    "create_high_performance_mc",
    "benchmark_backends",
    "get_system_info",
    "get_available_backend",
    "NUMBA_AVAILABLE",
    "GPU_AVAILABLE",

    # Exotic Options
    "RainbowOption",
    "RainbowType",
    "SpreadOption",
    "SpreadType",
    "CompoundOption",
    "ChooserOption",
    "VarianceSwap",
    "VolatilitySwap",
    "CliquetOption",
    "Autocallable",
    "ForwardStartOption",
    "PowerOption",
    "ExoticPricingResult",
    "create_rainbow_option",
    "create_spread_option",
    "create_variance_swap",
    "create_autocallable",

    # Calibration
    "SVI",
    "SSVI",
    "VolatilitySurface",
    "HestonCalibrator",
    "SABRCalibrator",
    "LocalVolCalibrator",
    "RoughBergomiCalibrator",
    "ImpliedVolCalculator",
    "MarketData",
    "CalibrationResult",
    "CalibrationObjective",
    "create_heston_calibrator",
    "create_sabr_calibrator",
    "create_svi_fitter",
    "create_ssvi_fitter",
    "calibrate_volatility_surface",

    # Stress Testing
    "StressTestEngine",
    "Scenario",
    "ScenarioType",
    "HistoricalScenarios",
    "ScenarioGenerator",
    "MacroStressFramework",
    "ExtremeValueAnalysis",
    "Portfolio",
    "PortfolioPosition",
    "StressResult",
    "StressTestReport",
    "create_stress_test_engine",
    "create_macro_framework",
    "run_standard_stress_tests",

    # Backtesting
    "BacktestEngine",
    "Strategy",
    "StrategyConfig",
    "Order",
    "OrderType",
    "OrderSide",
    "Trade",
    "Position",
    "PositionType",
    "Bar",
    "TransactionCostModel",
    "SimpleTransactionCost",
    "TieredCommission",
    "MarketImpactModel",
    "PositionSizer",
    "FixedFractionSizer",
    "VolatilityTargetSizer",
    "KellyCriterionSizer",
    "RiskParitySizer",
    "WalkForwardOptimizer",
    "MonteCarloBacktest",
    "SignificanceTester",
    "BacktestResult",
    "create_backtest_engine",
    "create_walk_forward_optimizer",
    "run_quick_backtest",
]

__version__ = "0.2.0"
