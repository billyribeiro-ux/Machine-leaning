"""
Revolution Alpha Engine - Index Model (SPY/QQQ)

Specialized model for index trading with full market internals:
- TRIN (Arms Index)
- TICK
- ADD (Advance/Decline)
- UVOL/DVOL (Up Volume/Down Volume)
- VIX analysis
- SKEW
- Put/Call ratio
- Sector rotation

Every trade shows complete reasoning with all readings.
"""

from .spy_qqq_model import (
    IndexModel,
    IndexSymbol,
    MarketBias,
    MarketInternals,
    IndexTradeSignal,
    MarketInternalsAnalyzer,
    IndexTechnicalAnalyzer,
    create_spy_model,
    create_qqq_model,
    create_index_model,
)

__all__ = [
    "IndexModel",
    "IndexSymbol",
    "MarketBias",
    "MarketInternals",
    "IndexTradeSignal",
    "MarketInternalsAnalyzer",
    "IndexTechnicalAnalyzer",
    "create_spy_model",
    "create_qqq_model",
    "create_index_model",
]

__version__ = "0.1.0"
