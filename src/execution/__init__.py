"""
Revolution Alpha Engine - Professional Execution Algorithms

Institutional-grade order execution:
- TWAP (Time-Weighted Average Price)
- VWAP (Volume-Weighted Average Price)
- Implementation Shortfall (Almgren-Chriss)
- Adaptive execution
- Smart order routing
"""

from .algorithms import (
    ExecutionEngine,
    TWAPAlgorithm,
    VWAPAlgorithm,
    ImplementationShortfallAlgorithm,
    AdaptiveAlgorithm,
    SmartOrderRouter,
    VolumeProfile,
    ExecutionAlgorithm,
    OrderSide,
    OrderType,
    ExecutionStrategy,
    ExecutionVenue,
    SliceOrder,
    ExecutionPlan,
    ExecutionReport,
    MarketMicrostructure,
    create_twap_algorithm,
    create_vwap_algorithm,
    create_is_algorithm,
    create_execution_engine,
)

__all__ = [
    "ExecutionEngine",
    "TWAPAlgorithm",
    "VWAPAlgorithm",
    "ImplementationShortfallAlgorithm",
    "AdaptiveAlgorithm",
    "SmartOrderRouter",
    "VolumeProfile",
    "ExecutionAlgorithm",
    "OrderSide",
    "OrderType",
    "ExecutionStrategy",
    "ExecutionVenue",
    "SliceOrder",
    "ExecutionPlan",
    "ExecutionReport",
    "MarketMicrostructure",
    "create_twap_algorithm",
    "create_vwap_algorithm",
    "create_is_algorithm",
    "create_execution_engine",
]

__version__ = "0.1.0"
