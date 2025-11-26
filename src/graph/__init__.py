"""
Revolution Alpha Engine - Graph Neural Networks for Markets

Model complex market relationships:
- Stock correlations and lead-lag
- Sector/industry hierarchies
- Supply chain dependencies
- Ownership networks
- ETF creation/redemption flows
"""

from .market_graph import (
    MarketGraphEngine,
    MarketGraphNN,
    MarketGraphBuilder,
    GraphAttentionLayer,
    TemporalGraphConv,
    RelationType,
    MarketNode,
    MarketEdge,
    GraphPrediction,
    create_market_graph_engine,
)

__all__ = [
    "MarketGraphEngine",
    "MarketGraphNN",
    "MarketGraphBuilder",
    "GraphAttentionLayer",
    "TemporalGraphConv",
    "RelationType",
    "MarketNode",
    "MarketEdge",
    "GraphPrediction",
    "create_market_graph_engine",
]

__version__ = "0.1.0"
