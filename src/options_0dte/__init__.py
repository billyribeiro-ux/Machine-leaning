"""
Revolution Alpha Engine - 0DTE SPX Options Trading System

State-of-the-art self-learning system for 0DTE SPX options trading.

This package provides:
- Complete Greeks analysis with higher-order sensitivities
- Gamma Exposure (GEX) calculations and dealer positioning
- Self-learning neural network for pattern recognition
- Institutional options flow detection
- Real-time opportunity scanner
- Complete trade diagnostics with full reasoning

Modules:
--------
spx_engine : Core 0DTE SPX options engine with Greeks, GEX, and signals
self_learning : Self-learning neural network and pattern recognition
flow_analyzer : Institutional options flow analysis
scanner : Real-time 0DTE opportunity scanner
trade_diagnostics : Complete trade reasoning and diagnostics

Example Usage:
--------------
```python
from src.options_0dte import (
    ZeroDTEEngine,
    SelfLearningSystem,
    InstitutionalFlowAnalyzer,
    ZeroDTEScanner,
    TradeDiagnosticsEngine
)

# Create the main engine
engine = ZeroDTEEngine()

# Generate a trading signal
signal = engine.generate_signal(
    spot_price=4500.0,
    options_chain=chain_df,
    flow_data=flow_df,
    daily_data=price_df
)

# Get full reasoning
print(signal.get_full_reasoning())

# Create self-learning system
learner = SelfLearningSystem()
features = learner.extract_features(price_data, greeks, flow, gex)
prediction = learner.predict(features)

# Create scanner
scanner = ZeroDTEScanner()
opportunities = scanner.scan(options_chain, underlying_price, flow_data, gex_data)

# Get complete diagnostics
diagnostics_engine = TradeDiagnosticsEngine()
diagnostics = diagnostics_engine.generate_diagnostics(
    trade_signal,
    market_internals,
    greeks,
    flow_data,
    gex_data
)
print(diagnostics.get_complete_report())
```

Classes:
--------
Core Engine:
    ZeroDTEEngine - Main 0DTE trading engine
    Greeks - Complete options Greeks with higher-order sensitivities
    GammaExposure - GEX analysis and dealer positioning
    VolatilitySurface - IV surface analysis
    ZeroDTESignal - Complete trading signal with full analysis
    BlackScholesCalculator - Options pricing and Greeks calculation

Self-Learning:
    SelfLearningSystem - Complete self-learning system
    SelfLearningNetwork - Deep neural network for pattern learning
    FeatureExtractor - Extract features from market data
    PatternRecognizer - Pattern memory and matching
    PatternMemory - Individual pattern storage

Flow Analysis:
    InstitutionalFlowAnalyzer - Analyze institutional flow
    OptionsOrder - Individual options order
    FlowSummary - Aggregated flow analysis
    DarkPoolEstimator - Estimate dark pool activity

Scanner:
    ZeroDTEScanner - Real-time opportunity scanner
    ScanResult - Individual scan result
    ScannerConfig - Scanner configuration
    ScannerDashboard - Terminal dashboard

Diagnostics:
    TradeDiagnosticsEngine - Generate complete diagnostics
    CompleteTradeDiagnostics - Full trade diagnostic report
    MarketInternalsReading - Market internals snapshot
    GreeksImpactAnalysis - Greeks impact projections
    FlowAttribution - Flow contribution analysis
    GEXAnalysis - GEX implications
"""

from .spx_engine import (
    # Enums
    OptionType,
    TradeDirection,
    MarketRegime,
    TimeOfDay,

    # Data classes
    Greeks,
    GammaExposure,
    OptionsFlow,
    VolatilitySurface,
    ZeroDTESignal,

    # Core classes
    BlackScholesCalculator,
    ZeroDTEEngine,

    # Factory functions
    create_0dte_engine
)

from .self_learning import (
    # Enums
    LearningMode,
    PatternType,

    # Data classes
    LearningConfig,
    PatternMemory,

    # Core classes
    SelfLearningNetwork,
    FeatureExtractor,
    PatternRecognizer,
    SelfLearningSystem,

    # Factory functions
    create_self_learning_system
)

from .flow_analyzer import (
    # Enums
    OrderType,
    OrderSide,
    FlowSentiment,

    # Data classes
    OptionsOrder,
    FlowSummary,

    # Core classes
    InstitutionalFlowAnalyzer,
    DarkPoolEstimator,

    # Factory functions
    create_flow_analyzer,
    create_options_order
)

from .scanner import (
    # Enums
    ScannerMode,
    OpportunityType,
    AlertPriority,

    # Data classes
    ScannerConfig,
    ScanResult,

    # Core classes
    ZeroDTEScanner,
    ScannerDashboard,

    # Factory functions
    create_scanner,
    create_scanner_dashboard
)

from .trade_diagnostics import (
    # Enums
    DiagnosticLevel,

    # Data classes
    MarketInternalsReading,
    GreeksImpactAnalysis,
    FlowAttribution,
    GEXAnalysis,
    CompleteTradeDiagnostics,

    # Core classes
    TradeDiagnosticsEngine,

    # Factory functions
    create_diagnostics_engine
)

__all__ = [
    # === SPX Engine ===
    # Enums
    'OptionType',
    'TradeDirection',
    'MarketRegime',
    'TimeOfDay',
    # Data classes
    'Greeks',
    'GammaExposure',
    'OptionsFlow',
    'VolatilitySurface',
    'ZeroDTESignal',
    # Core classes
    'BlackScholesCalculator',
    'ZeroDTEEngine',
    # Factory functions
    'create_0dte_engine',

    # === Self Learning ===
    # Enums
    'LearningMode',
    'PatternType',
    # Data classes
    'LearningConfig',
    'PatternMemory',
    # Core classes
    'SelfLearningNetwork',
    'FeatureExtractor',
    'PatternRecognizer',
    'SelfLearningSystem',
    # Factory functions
    'create_self_learning_system',

    # === Flow Analyzer ===
    # Enums
    'OrderType',
    'OrderSide',
    'FlowSentiment',
    # Data classes
    'OptionsOrder',
    'FlowSummary',
    # Core classes
    'InstitutionalFlowAnalyzer',
    'DarkPoolEstimator',
    # Factory functions
    'create_flow_analyzer',
    'create_options_order',

    # === Scanner ===
    # Enums
    'ScannerMode',
    'OpportunityType',
    'AlertPriority',
    # Data classes
    'ScannerConfig',
    'ScanResult',
    # Core classes
    'ZeroDTEScanner',
    'ScannerDashboard',
    # Factory functions
    'create_scanner',
    'create_scanner_dashboard',

    # === Diagnostics ===
    # Enums
    'DiagnosticLevel',
    # Data classes
    'MarketInternalsReading',
    'GreeksImpactAnalysis',
    'FlowAttribution',
    'GEXAnalysis',
    'CompleteTradeDiagnostics',
    # Core classes
    'TradeDiagnosticsEngine',
    # Factory functions
    'create_diagnostics_engine',
]

__version__ = '1.0.0'
__author__ = 'Revolution Alpha Engine'
