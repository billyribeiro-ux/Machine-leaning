"""
Revolution Alpha Engine - Institutional Intelligence Module

State-of-the-art institutional-grade market analysis systems:

1. VIX Institutional Tracker
   - Full VIX options chain analysis
   - Term structure analysis (contango/backwardation)
   - Crash/rally preparation detection
   - Unusual activity signals
   - Backtesting capabilities

2. Dark Pool Activity Detector
   - Tape reading with Lee-Ready classification
   - Iceberg order detection
   - Block trade identification
   - Volume anomaly detection
   - Short volume analysis

3. Smart Money Flow Tracker
   - Options sweep analysis
   - Sector rotation tracking
   - Risk-on/risk-off detection
   - Cross-symbol pattern detection
   - Institutional footprint analysis

4. Regime Change Detector
   - Hidden Markov Models for regime identification
   - Bayesian changepoint detection
   - Jump-diffusion analysis
   - Volatility clustering
   - Trading signal generation

5. Cross-Asset Intelligence Engine
   - Inter-market correlation analysis
   - Lead-lag detection
   - Cointegration analysis
   - Macro regime identification
   - Asset class rotation signals

6. Predictive Order Flow System
   - Order book imbalance modeling
   - VPIN (Volume-synchronized PIN)
   - Volume clock analysis
   - Aggressive order detection
   - ML-based flow prediction

7. Master Scanner Orchestrator
   - Unified signal generation
   - Confluence analysis
   - Risk management integration
   - Priority-based signal sorting
   - Position sizing recommendations

Author: Revolution Alpha Engine
"""

from .vix_tracker import (
    VIXInstitutionalTracker,
    StrikeAnalysis,
    ExpirationAnalysis,
    VIXTermStructure,
    InstitutionalAlert,
    create_vix_tracker
)

from .dark_pool_detector import (
    DarkPoolDetector,
    TapeReader,
    VolumeAnalyzer,
    DarkPoolSignal,
    create_dark_pool_detector
)

from .smart_money_tracker import (
    SmartMoneyTracker,
    OptionsFlowAnalyzer,
    SectorRotationTracker,
    SmartMoneySignal,
    create_smart_money_tracker
)

from .regime_detector import (
    RegimeChangeDetector,
    HiddenMarkovRegime,
    BayesianChangepoint,
    JumpDiffusionDetector,
    MarketRegime,
    RegimeState,
    RegimeChangeAlert,
    create_regime_detector
)

from .cross_asset_intelligence import (
    CrossAssetIntelligence,
    CorrelationAnalyzer,
    LeadLagDetector,
    CointegrationAnalyzer,
    RiskAppetiteIndicator,
    AssetClass,
    MacroRegime,
    AssetPair,
    CrossAssetSignal,
    GlobalMacroState,
    create_cross_asset_intelligence
)

from .predictive_order_flow import (
    PredictiveOrderFlow,
    TickClassifier,
    OrderBookImbalance,
    VPINCalculator,
    VolumeClock,
    AggressiveOrderDetector,
    InstitutionalFootprint,
    FlowPredictor,
    FlowDirection,
    OrderFlowState,
    FlowSignal,
    create_predictive_order_flow
)

from .master_orchestrator import (
    MasterOrchestrator,
    SignalAggregator,
    ConfluenceAnalyzer,
    RiskManager,
    SignalPriority,
    ConvictionLevel,
    UnifiedSignal,
    MarketContext,
    create_master_orchestrator
)


__all__ = [
    # VIX Tracker
    'VIXInstitutionalTracker',
    'StrikeAnalysis',
    'ExpirationAnalysis',
    'VIXTermStructure',
    'InstitutionalAlert',
    'create_vix_tracker',

    # Dark Pool
    'DarkPoolDetector',
    'TapeReader',
    'VolumeAnalyzer',
    'DarkPoolSignal',
    'create_dark_pool_detector',

    # Smart Money
    'SmartMoneyTracker',
    'OptionsFlowAnalyzer',
    'SectorRotationTracker',
    'SmartMoneySignal',
    'create_smart_money_tracker',

    # Regime Detector
    'RegimeChangeDetector',
    'HiddenMarkovRegime',
    'BayesianChangepoint',
    'JumpDiffusionDetector',
    'MarketRegime',
    'RegimeState',
    'RegimeChangeAlert',
    'create_regime_detector',

    # Cross-Asset
    'CrossAssetIntelligence',
    'CorrelationAnalyzer',
    'LeadLagDetector',
    'CointegrationAnalyzer',
    'RiskAppetiteIndicator',
    'AssetClass',
    'MacroRegime',
    'AssetPair',
    'CrossAssetSignal',
    'GlobalMacroState',
    'create_cross_asset_intelligence',

    # Order Flow
    'PredictiveOrderFlow',
    'TickClassifier',
    'OrderBookImbalance',
    'VPINCalculator',
    'VolumeClock',
    'AggressiveOrderDetector',
    'InstitutionalFootprint',
    'FlowPredictor',
    'FlowDirection',
    'OrderFlowState',
    'FlowSignal',
    'create_predictive_order_flow',

    # Master Orchestrator
    'MasterOrchestrator',
    'SignalAggregator',
    'ConfluenceAnalyzer',
    'RiskManager',
    'SignalPriority',
    'ConvictionLevel',
    'UnifiedSignal',
    'MarketContext',
    'create_master_orchestrator',
]


# Convenience function to create all scanners
def create_institutional_suite() -> dict:
    """
    Create a complete suite of institutional scanners.

    Returns:
        Dictionary with all scanner instances
    """
    return {
        'vix_tracker': create_vix_tracker(),
        'dark_pool': create_dark_pool_detector(),
        'smart_money': create_smart_money_tracker(),
        'regime_detector': create_regime_detector(),
        'cross_asset': create_cross_asset_intelligence(),
        'order_flow': create_predictive_order_flow(),
        'orchestrator': create_master_orchestrator()
    }
