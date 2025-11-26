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
    # Engine
    "ScannerEngine",
    "EngineConfig",
    "EngineState",
    "ScannerStats",
    "create_options_engine",
    "create_squeeze_engine",
    "create_momentum_engine",
    "create_full_engine",
]

__version__ = "0.1.0"
