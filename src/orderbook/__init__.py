"""
Revolution Alpha Engine - Predictive Order Book Modeling

Deep learning for limit order book dynamics:
- Price impact prediction
- Queue position modeling
- Market maker behavior
- Liquidity forecasting
- Adverse selection detection
"""

from .predictor import (
    OrderBookPredictor,
    DeepLOBModel,
    OrderBookEncoder,
    TemporalLOBModel,
    QueuePositionModel,
    LOBFeatureExtractor,
    TradeFlowEncoder,
    OrderBookSide,
    OrderBookLevel,
    OrderBookSnapshot,
    LOBPrediction,
    TradeFlow,
    create_orderbook_predictor,
)

__all__ = [
    "OrderBookPredictor",
    "DeepLOBModel",
    "OrderBookEncoder",
    "TemporalLOBModel",
    "QueuePositionModel",
    "LOBFeatureExtractor",
    "TradeFlowEncoder",
    "OrderBookSide",
    "OrderBookLevel",
    "OrderBookSnapshot",
    "LOBPrediction",
    "TradeFlow",
    "create_orderbook_predictor",
]

__version__ = "0.1.0"
