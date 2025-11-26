"""
Revolution Alpha Engine - Ultra-Accurate Scalper Machine

Maximum accuracy scalping system:
- Multiple confirmation signals (6+ required)
- Strict entry criteria (85%+ confidence)
- Precise timing
- Advanced filtering
- Risk-adjusted position sizing
"""

from .scalper_machine import (
    ScalperMachine,
    ScalperConfig,
    ScalpSignal,
    ScalpDirection,
    SignalStrength,
    TechnicalAnalyzer,
    ConfirmationEngine,
    PrecisionEntryTimer,
    create_scalper,
    create_ultra_accurate_scalper,
)

__all__ = [
    "ScalperMachine",
    "ScalperConfig",
    "ScalpSignal",
    "ScalpDirection",
    "SignalStrength",
    "TechnicalAnalyzer",
    "ConfirmationEngine",
    "PrecisionEntryTimer",
    "create_scalper",
    "create_ultra_accurate_scalper",
]

__version__ = "0.1.0"
