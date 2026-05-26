"""
Revolution Alpha Engine - Risk Management

Professional risk management for institutional trading:
- Kelly Criterion for optimal position sizing
- Value at Risk (VaR) calculations
- Expected Shortfall (CVaR)
- Position sizing with risk constraints
- Drawdown monitoring and control
- Real-time risk alerts
"""

from .management import (
    RiskManager,
    KellyCriterion,
    VaRCalculator,
    PositionSizer,
    DrawdownMonitor,
)

__all__ = [
    "RiskManager",
    "KellyCriterion",
    "VaRCalculator",
    "PositionSizer",
    "DrawdownMonitor",
]

__version__ = "0.1.0"
