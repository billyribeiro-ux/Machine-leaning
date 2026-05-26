"""
Revolution Alpha Engine - Market Microstructure Analysis

Institutional-grade order flow and market microstructure analysis:
- VPIN (Volume-Synchronized Probability of Informed Trading)
- Trade classification (Lee-Ready, BVC, EMO)
- Smart money detection
- Institutional flow identification
- Dark pool activity monitoring
"""

from .order_flow import (
    VPINCalculator,
    TradeClassifier,
    SmartMoneyDetector,
    OrderFlowAnalyzer,
    OrderFlowMetrics,
)

__all__ = [
    "VPINCalculator",
    "TradeClassifier",
    "SmartMoneyDetector",
    "OrderFlowAnalyzer",
    "OrderFlowMetrics",
]

__version__ = "0.1.0"
