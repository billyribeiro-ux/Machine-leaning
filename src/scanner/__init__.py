"""
Revolution Alpha Engine - Scanner System

Institutional-grade real-time market scanner for detecting:
- Options flow and unusual activity
- Short squeeze and gamma squeeze conditions
- Momentum breakouts and continuations
- Reversal patterns with divergence
- Breakout setups from consolidation

Usage:
    from src.scanner import ScannerEngine, ScannerConfig, ScanMode

    # Create engine with default configuration
    engine = ScannerEngine()

    # Set universe
    engine.set_universe(["AAPL", "TSLA", "NVDA", "AMD", "SPY"])

    # Set data providers
    engine.set_market_data_provider(your_market_data_function)
    engine.set_options_data_provider(your_options_data_function)

    # Run scan
    await engine.start()
    results = engine.last_results
"""

# Models
from .models import (
    ScanMode,
    SignalDirection,
    SqueezeType,
    SignalStrength,
    TimeFrame,
    MarketRegime,
    ScanResult,
    OptionsScanResult,
    SqueezeScanResult,
    MomentumScanResult,
    ReversalScanResult,
    BreakoutScanResult,
    ScannerConfig,
    OptionsFilterConfig,
    SqueezeFilterConfig,
    AlertPriority,
    ScanAlert,
    ScannerSummary,
    ScannerBatchResult,
)

# Base classes
from .base import (
    BaseScanner,
    AsyncStreamingScanner,
    CompositeScanner,
    ScanContext,
    MarketData,
    HistoricalData,
)

# Scanners
from .options_scanner import (
    OptionsFlowScanner,
    OptionsSwingScanner,
    GammaExposureScanner,
    OptionContract,
    OptionsChain,
    UnusualActivity,
)

from .squeeze_scanner import (
    ShortSqueezeScanner,
    GammaSqueezeScanner,
    CombinedSqueezeScanner,
    ShortInterestData,
    GammaExposureData,
    SqueezeConditions,
)

from .momentum_scanner import (
    MomentumScanner,
    ReversalScanner,
    BreakoutScanner,
    MomentumMetrics,
    PatternMatch,
)

# Multi-Timeframe Scanner
from .mtf_scanner import (
    MultiTimeframeScanner,
    MTFAnalyzer,
    TimeframeConverter,
    MTFSignal,
    MTFScanResult,
    TimeframeAnalysis,
)

# Engine
from .engine import (
    ScannerEngine,
    EngineConfig,
    EngineState,
    ScannerStats,
    create_options_engine,
    create_squeeze_engine,
    create_momentum_engine,
    create_full_engine,
    create_advanced_engine,
)

# Advanced Models
from .advanced_models import (
    AdvancedScanResult,
    ScanCategory,
    RegimeContext,
    ExpectedTimeframe,
    VolatilityRegime,
    TrendPhase,
    VolatilityEstimate,
    GARCHResult,
    StructureBreak,
    FairValueGap,
    OrderBlock,
    LiquiditySweep,
    IVSurface,
    IVSurfacePoint,
    GreeksExposure,
    FractalAnalysis,
    BreadthSnapshot,
    BacktestValidation,
    ScanPerformanceTracker,
)

# Advanced Scanners
from .volatility_scanner import VolatilityRegimeScanner
from .market_structure_scanner import MarketStructureScanner
from .options_intelligence import OptionsIntelligenceScanner
from .fractal_scanner import FractalInformationScanner
from .breadth_scanner import MarketBreadthScanner
from .wavelet_scanner import WaveletFourierScanner
from .extreme_value_scanner import ExtremeValueScanner
from .composite_alpha import CompositeAlphaScanner
from .ml_adaptive_scanner import AdaptiveScannerFramework

# Phase 3 Scanners
from .skew_intelligence import SkewIntelligenceScanner
from .vix_intelligence import VIXDeepIntelligenceScanner
from .gaps_power_scanner import GapsPowerScanner

# Phase 4 — Institutional Integration + SOTA Scanners
from .dark_pool_scanner import DarkPoolScanner
from .order_flow_scanner import OrderFlowImbalanceScanner
from .cross_asset_scanner import CrossAssetScanner
from .sentiment_scanner import SentimentAlphaScanner
from .vwap_scanner import VWAPDeviationScanner
from .liquidity_scanner import LiquidityShockScanner
from .scanner_backtest import (
    ScannerBacktestEngine,
    ScannerBacktestResult,
    BacktestTimeframe,
    TradeSimulator,
    MultiTimeframeBacktest,
    ScannerPerformanceTracker,
    BacktestReportGenerator,
)

# Data Integration
from .data_integration import (
    ScannerDataIntegration,
    UniversalScannerDataProvider,
    ScannerDataPackage,
    ScannerDataConfig,
    ScannerType,
    SCANNER_REQUIREMENTS,
    create_scanner_data_provider,
    create_scanner_integration,
    get_scanner_requirements,
)

__all__ = [
    # Models
    "ScanMode",
    "SignalDirection",
    "SqueezeType",
    "SignalStrength",
    "TimeFrame",
    "MarketRegime",
    "ScanResult",
    "OptionsScanResult",
    "SqueezeScanResult",
    "MomentumScanResult",
    "ReversalScanResult",
    "BreakoutScanResult",
    "ScannerConfig",
    "OptionsFilterConfig",
    "SqueezeFilterConfig",
    "AlertPriority",
    "ScanAlert",
    "ScannerSummary",
    "ScannerBatchResult",
    # Base
    "BaseScanner",
    "AsyncStreamingScanner",
    "CompositeScanner",
    "ScanContext",
    "MarketData",
    "HistoricalData",
    # Options
    "OptionsFlowScanner",
    "OptionsSwingScanner",
    "GammaExposureScanner",
    "OptionContract",
    "OptionsChain",
    "UnusualActivity",
    # Squeeze
    "ShortSqueezeScanner",
    "GammaSqueezeScanner",
    "CombinedSqueezeScanner",
    "ShortInterestData",
    "GammaExposureData",
    "SqueezeConditions",
    # Momentum
    "MomentumScanner",
    "ReversalScanner",
    "BreakoutScanner",
    "MomentumMetrics",
    "PatternMatch",
    # Multi-Timeframe
    "MultiTimeframeScanner",
    "MTFAnalyzer",
    "TimeframeConverter",
    "MTFSignal",
    "MTFScanResult",
    "TimeframeAnalysis",
    # Engine
    "ScannerEngine",
    "EngineConfig",
    "EngineState",
    "ScannerStats",
    "create_options_engine",
    "create_squeeze_engine",
    "create_momentum_engine",
    "create_full_engine",
    "create_advanced_engine",
    # Data Integration
    "ScannerDataIntegration",
    "UniversalScannerDataProvider",
    "ScannerDataPackage",
    "ScannerDataConfig",
    "ScannerType",
    "SCANNER_REQUIREMENTS",
    "create_scanner_data_provider",
    "create_scanner_integration",
    "get_scanner_requirements",
    # Advanced Models
    "AdvancedScanResult",
    "ScanCategory",
    "RegimeContext",
    "ExpectedTimeframe",
    "VolatilityRegime",
    "TrendPhase",
    "VolatilityEstimate",
    "GARCHResult",
    "StructureBreak",
    "FairValueGap",
    "OrderBlock",
    "LiquiditySweep",
    "IVSurface",
    "IVSurfacePoint",
    "GreeksExposure",
    "FractalAnalysis",
    "BreadthSnapshot",
    "BacktestValidation",
    "ScanPerformanceTracker",
    # Advanced Scanners
    "VolatilityRegimeScanner",
    "MarketStructureScanner",
    "OptionsIntelligenceScanner",
    "FractalInformationScanner",
    "MarketBreadthScanner",
    "WaveletFourierScanner",
    "ExtremeValueScanner",
    "CompositeAlphaScanner",
    "AdaptiveScannerFramework",
    # Phase 3 Scanners
    "SkewIntelligenceScanner",
    "VIXDeepIntelligenceScanner",
    "GapsPowerScanner",
    # Phase 4 — Institutional + SOTA Scanners
    "DarkPoolScanner",
    "OrderFlowImbalanceScanner",
    "CrossAssetScanner",
    "SentimentAlphaScanner",
    "VWAPDeviationScanner",
    "LiquidityShockScanner",
    # Universal Backtest Framework
    "ScannerBacktestEngine",
    "ScannerBacktestResult",
    "BacktestTimeframe",
    "TradeSimulator",
    "MultiTimeframeBacktest",
    "ScannerPerformanceTracker",
    "BacktestReportGenerator",
]

__version__ = "0.1.0"
