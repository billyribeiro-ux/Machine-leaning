"""
SCANIFY — 0DTE SPX OTM Options Day Trading Scanner + Gamma Exposure (GEX) Scanner

A precision-engineered 0DTE SPX intraday trading system built on quantifiable
dealer mechanics, mathematical properties of options at expiration, and
empirical market data.

Components:
    - config: All configurable parameters and enums
    - data_feeds: Data feed interfaces, VIX1D analyzer, expected move calculations
    - gex_engine: Gamma Exposure computation with dealer positioning
    - market_internals: Multi-factor composite direction scoring
    - pre_market: Pre-market session setup and classification
    - directional: Core Scan #1 — Directional OTM Scanner
    - premium_seller: Core Scan #2 — Premium Selling Scanner (Credit Spreads/Iron Condors)
    - gamma_scalp: Core Scan #3 — Gamma Scalp / Acceleration Scanner
    - exit_manager: Position and exit management
    - trade_logger: Trade logging and self-learning calibration
    - orchestrator: Master controller tying all components together
"""

import logging
import warnings

__version__ = "1.0.0"

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# config — All configurable parameters and enums
# ---------------------------------------------------------------------------
try:
    from .config import (
        SessionType,
        TimeZone,
        ScanType,
        SignalDirection,
        ExitReason,
        GEXSignalType,
        ScanifyConfig,
        DirectionalScanConfig,
        PremiumSellConfig,
        GammaScalpConfig,
        GEXConfig,
        ExitConfig,
        CalibrationConfig,
        RiskConfig,
        SPXContractSpec,
    )
except ImportError as exc:
    _logger.warning("Failed to import scanify.config: %s", exc)
    warnings.warn(
        f"scanify.config could not be imported: {exc}",
        ImportWarning,
        stacklevel=2,
    )

# ---------------------------------------------------------------------------
# data_feeds — Data feed interfaces, VIX1D analyzer, expected move calcs
# ---------------------------------------------------------------------------
try:
    from .data_feeds import (
        OptionType,
        ImpactLevel,
        OptionQuote,
        OptionsChain,
        MarketInternalsData,
        FuturesData,
        VIXData,
        EconomicEvent,
        PriorSessionData,
        SPXPriceBar,
        CrossAssetData,
        VIX1DAnalyzer,
        DataFeedManager,
    )
except ImportError as exc:
    _logger.warning("Failed to import scanify.data_feeds: %s", exc)
    warnings.warn(
        f"scanify.data_feeds could not be imported: {exc}",
        ImportWarning,
        stacklevel=2,
    )

# ---------------------------------------------------------------------------
# gex_engine — Gamma Exposure computation with dealer positioning
# ---------------------------------------------------------------------------
try:
    from .gex_engine import (
        GEXResult,
        GEXSignal,
        GEXEngine,
    )
except ImportError as exc:
    _logger.warning("Failed to import scanify.gex_engine: %s", exc)
    warnings.warn(
        f"scanify.gex_engine could not be imported: {exc}",
        ImportWarning,
        stacklevel=2,
    )

# ---------------------------------------------------------------------------
# market_internals — Multi-factor composite direction scoring
# ---------------------------------------------------------------------------
try:
    from .market_internals import (
        InternalsScore,
        FlowScore,
        PriceActionScore,
        GEXStructuralScore,
        CrossAssetScore,
        CompositeDirectionScore,
        MarketInternalsScorer,
    )
except ImportError as exc:
    _logger.warning("Failed to import scanify.market_internals: %s", exc)
    warnings.warn(
        f"scanify.market_internals could not be imported: {exc}",
        ImportWarning,
        stacklevel=2,
    )

# ---------------------------------------------------------------------------
# pre_market — Pre-market session setup and classification
# ---------------------------------------------------------------------------
try:
    from .pre_market import (
        GapClassification,
        GapAnalysis,
        ExpectedMove,
        KeyLevels,
        EventRisk,
        SessionSetup,
        PreMarketScanner,
    )
except ImportError as exc:
    _logger.warning("Failed to import scanify.pre_market: %s", exc)
    warnings.warn(
        f"scanify.pre_market could not be imported: {exc}",
        ImportWarning,
        stacklevel=2,
    )

# ---------------------------------------------------------------------------
# directional — Core Scan #1: Directional OTM Scanner
# ---------------------------------------------------------------------------
try:
    from .directional import (
        StrikeSelection,
        EntrySignal,
        DirectionalScanner,
    )
except ImportError as exc:
    _logger.warning("Failed to import scanify.directional: %s", exc)
    warnings.warn(
        f"scanify.directional could not be imported: {exc}",
        ImportWarning,
        stacklevel=2,
    )

# ---------------------------------------------------------------------------
# premium_seller — Core Scan #2: Premium Selling Scanner
# ---------------------------------------------------------------------------
try:
    from .premium_seller import (
        SpreadLeg,
        CreditSpread,
        IronCondor,
        PremiumSellSignal,
        PremiumSellingScanner,
    )
except ImportError as exc:
    _logger.warning("Failed to import scanify.premium_seller: %s", exc)
    warnings.warn(
        f"scanify.premium_seller could not be imported: {exc}",
        ImportWarning,
        stacklevel=2,
    )

# ---------------------------------------------------------------------------
# gamma_scalp — Core Scan #3: Gamma Scalp / Acceleration Scanner
# ---------------------------------------------------------------------------
try:
    from .gamma_scalp import (
        GammaSqueezeSetup,
        GammaUnpinSetup,
        GammaScalpSignal,
        GammaScalpScanner,
    )
except ImportError as exc:
    _logger.warning("Failed to import scanify.gamma_scalp: %s", exc)
    warnings.warn(
        f"scanify.gamma_scalp could not be imported: {exc}",
        ImportWarning,
        stacklevel=2,
    )

# ---------------------------------------------------------------------------
# exit_manager — Position and exit management
# ---------------------------------------------------------------------------
try:
    from .exit_manager import (
        Position,
        ExitSignal,
        ExitManager,
    )
except ImportError as exc:
    _logger.warning("Failed to import scanify.exit_manager: %s", exc)
    warnings.warn(
        f"scanify.exit_manager could not be imported: {exc}",
        ImportWarning,
        stacklevel=2,
    )

# ---------------------------------------------------------------------------
# trade_logger — Trade logging and self-learning calibration
# ---------------------------------------------------------------------------
try:
    from .trade_logger import (
        TradeRecord,
        DailyScoreCard,
        CalibrationResult,
        TradeLogger,
        CalibrationEngine,
    )
except ImportError as exc:
    _logger.warning("Failed to import scanify.trade_logger: %s", exc)
    warnings.warn(
        f"scanify.trade_logger could not be imported: {exc}",
        ImportWarning,
        stacklevel=2,
    )

# ---------------------------------------------------------------------------
# orchestrator — Master controller tying all components together
# ---------------------------------------------------------------------------
try:
    from .orchestrator import (
        ScanCycleResult,
        SessionState,
        ScanifyOrchestrator,
    )
except ImportError as exc:
    _logger.warning("Failed to import scanify.orchestrator: %s", exc)
    warnings.warn(
        f"scanify.orchestrator could not be imported: {exc}",
        ImportWarning,
        stacklevel=2,
    )

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
__all__ = [
    # version
    "__version__",
    # config
    "SessionType",
    "TimeZone",
    "ScanType",
    "SignalDirection",
    "ExitReason",
    "GEXSignalType",
    "ScanifyConfig",
    "DirectionalScanConfig",
    "PremiumSellConfig",
    "GammaScalpConfig",
    "GEXConfig",
    "ExitConfig",
    "CalibrationConfig",
    "RiskConfig",
    "SPXContractSpec",
    # data_feeds
    "OptionType",
    "ImpactLevel",
    "OptionQuote",
    "OptionsChain",
    "MarketInternalsData",
    "FuturesData",
    "VIXData",
    "EconomicEvent",
    "PriorSessionData",
    "SPXPriceBar",
    "CrossAssetData",
    "VIX1DAnalyzer",
    "DataFeedManager",
    # gex_engine
    "GEXResult",
    "GEXSignal",
    "GEXEngine",
    # market_internals
    "InternalsScore",
    "FlowScore",
    "PriceActionScore",
    "GEXStructuralScore",
    "CrossAssetScore",
    "CompositeDirectionScore",
    "MarketInternalsScorer",
    # pre_market
    "GapClassification",
    "GapAnalysis",
    "ExpectedMove",
    "KeyLevels",
    "EventRisk",
    "SessionSetup",
    "PreMarketScanner",
    # directional
    "StrikeSelection",
    "EntrySignal",
    "DirectionalScanner",
    # premium_seller
    "SpreadLeg",
    "CreditSpread",
    "IronCondor",
    "PremiumSellSignal",
    "PremiumSellingScanner",
    # gamma_scalp
    "GammaSqueezeSetup",
    "GammaUnpinSetup",
    "GammaScalpSignal",
    "GammaScalpScanner",
    # exit_manager
    "Position",
    "ExitSignal",
    "ExitManager",
    # trade_logger
    "TradeRecord",
    "DailyScoreCard",
    "CalibrationResult",
    "TradeLogger",
    "CalibrationEngine",
    # orchestrator
    "ScanCycleResult",
    "SessionState",
    "ScanifyOrchestrator",
]
