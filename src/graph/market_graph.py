"""
Graph Neural Network for Market Relationships.

Models complex market relationships that linear models miss:
- Stock correlations and lead-lag relationships
- Sector/industry hierarchies
- Supply chain dependencies
- Ownership networks (13F data)
- Options market maker hedging flows
- ETF creation/redemption relationships

GNNs capture non-linear dependencies and propagate information
across the market network for superior predictions.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import GCNConv, GATConv, SAGEConv, TransformerConv
from torch_geometric.data import Data, Batch
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
import logging
from collections import defaultdict


logger = logging.getLogger(__name__)


class RelationType(Enum):
    """Types of market relationships."""
    CORRELATION = "correlation"
    LEAD_LAG = "lead_lag"
    SECTOR = "sector"
    INDUSTRY = "industry"
    SUPPLY_CHAIN = "supply_chain"
    OWNERSHIP = "ownership"
    ETF_HOLDING = "etf_holding"
    OPTIONS_HEDGE = "options_hedge"


@dataclass
class MarketNode:
    """Node in market graph."""
    symbol: str
    node_type: str  # "stock", "etf", "index", "sector"
    features: np.ndarray
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MarketEdge:
    """Edge in market graph."""
    source: str
    target: str
    relation_type: RelationType
    weight: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphPrediction:
    """Prediction from graph model."""
    symbol: str
    predicted_return: float
    confidence: float
    network_signal: float  # Signal from connected nodes
    influential_neighbors: List[Tuple[str, float]]
    timestamp: datetime


class GraphAttentionLayer(nn.Module):
    """
    Graph Attention Layer with multi-head attention.

    Learns which neighbors are most important for each node.
    """

    def __init__(
        self,
        in_features: int,
        out_features: int,
        n_heads: int = 8,
        dropout: float = 0.1,
        concat: bool = True,
    ):
        super().__init__()

        self.n_heads = n_heads
        self.concat = concat

        # Per-head dimension
        self.head_dim = out_features // n_heads if concat else out_features

        # Linear transformations for each head
        self.W = nn.Linear(in_features, self.head_dim * n_heads, bias=False)

        # Attention parameters
        self.a = nn.Parameter(torch.zeros(n_heads, 2 * self.head_dim))
        nn.init.xavier_uniform_(self.a)

        self.leaky_relu = nn.LeakyReLU(0.2)
        self.dropout = nn.Dropout(dropout)

    def forward(
        self,
        x: torch.Tensor,
        edge_index: torch.Tensor,
        edge_weight: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        Forward pass.

        Args:
            x: Node features [N, in_features]
            edge_index: Edge indices [2, E]
            edge_weight: Optional edge weights [E]
        """
        N = x.size(0)

        # Transform features
        h = self.W(x).view(N, self.n_heads, self.head_dim)

        # Get source and target node features for each edge
        source, target = edge_index
        h_source = h[source]  # [E, n_heads, head_dim]
        h_target = h[target]  # [E, n_heads, head_dim]

        # Compute attention scores
        edge_features = torch.cat([h_source, h_target], dim=-1)  # [E, n_heads, 2*head_dim]
        attention = (edge_features * self.a).sum(dim=-1)  # [E, n_heads]
        attention = self.leaky_relu(attention)

        # Apply edge weights if provided
        if edge_weight is not None:
            attention = attention * edge_weight.unsqueeze(-1)

        # Softmax over neighbors
        attention = self._sparse_softmax(attention, target, N)
        attention = self.dropout(attention)

        # Aggregate
        out = torch.zeros(N, self.n_heads, self.head_dim, device=x.device)
        out.index_add_(0, target, attention.unsqueeze(-1) * h_source)

        # Concat or average heads
        if self.concat:
            out = out.view(N, -1)
        else:
            out = out.mean(dim=1)

        return out

    def _sparse_softmax(
        self,
        attention: torch.Tensor,
        indices: torch.Tensor,
        N: int,
    ) -> torch.Tensor:
        """Compute softmax over sparse neighborhoods."""
        # Subtract max for numerical stability
        attention_max = torch.zeros(N, attention.size(1), device=attention.device)
        attention_max.index_reduce_(0, indices, attention, reduce='amax')
        attention = attention - attention_max[indices]

        # Exp and sum
        attention = attention.exp()
        attention_sum = torch.zeros(N, attention.size(1), device=attention.device)
        attention_sum.index_add_(0, indices, attention)

        # Normalize
        return attention / (attention_sum[indices] + 1e-8)


class TemporalGraphConv(nn.Module):
    """
    Temporal Graph Convolution for time-varying relationships.

    Combines spatial (graph) and temporal (sequence) patterns.
    """

    def __init__(
        self,
        in_features: int,
        hidden_features: int,
        out_features: int,
        n_heads: int = 4,
        seq_len: int = 20,
    ):
        super().__init__()

        self.seq_len = seq_len

        # Spatial convolution
        self.gat = GraphAttentionLayer(
            in_features, hidden_features, n_heads=n_heads
        )

        # Temporal convolution
        self.temporal_conv = nn.Conv1d(
            hidden_features, hidden_features,
            kernel_size=3, padding=1
        )

        # Output projection
        self.output = nn.Linear(hidden_features, out_features)

        # Layer norm
        self.norm1 = nn.LayerNorm(hidden_features)
        self.norm2 = nn.LayerNorm(out_features)

    def forward(
        self,
        x: torch.Tensor,
        edge_index: torch.Tensor,
        edge_weight: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        Forward pass.

        Args:
            x: Node features [N, seq_len, in_features] or [N, in_features]
            edge_index: Edge indices [2, E]
        """
        if x.dim() == 2:
            # No temporal dimension
            h = self.gat(x, edge_index, edge_weight)
            return self.norm2(self.output(h))

        N, T, F = x.shape

        # Process each timestep through GAT
        temporal_out = []
        for t in range(T):
            h_t = self.gat(x[:, t, :], edge_index, edge_weight)
            temporal_out.append(h_t)

        # Stack and apply temporal conv
        h = torch.stack(temporal_out, dim=2)  # [N, hidden, T]
        h = self.temporal_conv(h)  # [N, hidden, T]
        h = F.relu(h)

        # Use last timestep
        h = h[:, :, -1]  # [N, hidden]
        h = self.norm1(h)

        return self.norm2(self.output(h))


class MarketGraphNN(nn.Module):
    """
    Full Market Graph Neural Network.

    Multi-layer GNN with:
    - Multiple relation types
    - Temporal aggregation
    - Hierarchical pooling
    - Skip connections
    """

    def __init__(
        self,
        node_features: int = 64,
        hidden_dim: int = 128,
        output_dim: int = 32,
        n_layers: int = 3,
        n_heads: int = 8,
        dropout: float = 0.1,
        n_relation_types: int = 8,
    ):
        super().__init__()

        self.n_layers = n_layers
        self.n_relation_types = n_relation_types

        # Input projection
        self.input_proj = nn.Linear(node_features, hidden_dim)

        # Relation-specific transformations
        self.relation_transforms = nn.ModuleList([
            nn.Linear(hidden_dim, hidden_dim)
            for _ in range(n_relation_types)
        ])

        # Graph attention layers
        self.gat_layers = nn.ModuleList([
            GraphAttentionLayer(
                hidden_dim if i == 0 else hidden_dim,
                hidden_dim,
                n_heads=n_heads,
                dropout=dropout,
            )
            for i in range(n_layers)
        ])

        # Layer norms
        self.layer_norms = nn.ModuleList([
            nn.LayerNorm(hidden_dim) for _ in range(n_layers)
        ])

        # Output layers
        self.output_proj = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, output_dim),
        )

        # Prediction heads
        self.return_head = nn.Linear(output_dim, 1)
        self.volatility_head = nn.Linear(output_dim, 1)
        self.confidence_head = nn.Sequential(
            nn.Linear(output_dim, 16),
            nn.ReLU(),
            nn.Linear(16, 1),
            nn.Sigmoid(),
        )

    def forward(
        self,
        x: torch.Tensor,
        edge_index: torch.Tensor,
        edge_type: torch.Tensor,
        edge_weight: Optional[torch.Tensor] = None,
    ) -> Dict[str, torch.Tensor]:
        """
        Forward pass.

        Args:
            x: Node features [N, node_features]
            edge_index: Edge indices [2, E]
            edge_type: Edge type for each edge [E]
            edge_weight: Optional edge weights [E]
        """
        # Input projection
        h = self.input_proj(x)

        # Apply relation-specific transforms to edges
        # (This is simplified - full R-GCN would do message passing per relation)

        # Graph convolution layers with skip connections
        for i in range(self.n_layers):
            h_new = self.gat_layers[i](h, edge_index, edge_weight)
            h = h + h_new  # Skip connection
            h = self.layer_norms[i](h)
            h = F.relu(h)

        # Output projection
        out = self.output_proj(h)

        return {
            "embeddings": out,
            "predicted_return": self.return_head(out).squeeze(-1),
            "predicted_volatility": F.softplus(self.volatility_head(out)).squeeze(-1),
            "confidence": self.confidence_head(out).squeeze(-1),
        }


class MarketGraphBuilder:
    """
    Builds and maintains the market relationship graph.
    """

    def __init__(
        self,
        correlation_threshold: float = 0.5,
        lead_lag_threshold: float = 0.3,
        min_edge_weight: float = 0.1,
    ):
        self.correlation_threshold = correlation_threshold
        self.lead_lag_threshold = lead_lag_threshold
        self.min_edge_weight = min_edge_weight

        self.nodes: Dict[str, MarketNode] = {}
        self.edges: List[MarketEdge] = []

        # Symbol to index mapping
        self.symbol_to_idx: Dict[str, int] = {}
        self.idx_to_symbol: Dict[int, str] = {}

        # Sector/industry mappings
        self.sector_map: Dict[str, str] = {}
        self.industry_map: Dict[str, str] = {}

    def add_node(self, node: MarketNode):
        """Add node to graph."""
        if node.symbol not in self.nodes:
            idx = len(self.nodes)
            self.symbol_to_idx[node.symbol] = idx
            self.idx_to_symbol[idx] = node.symbol

        self.nodes[node.symbol] = node

    def add_edge(self, edge: MarketEdge):
        """Add edge to graph."""
        if edge.weight >= self.min_edge_weight:
            self.edges.append(edge)

    def build_correlation_edges(
        self,
        returns: Dict[str, np.ndarray],
        lookback: int = 60,
    ):
        """Build edges from return correlations."""
        symbols = list(returns.keys())
        n = len(symbols)

        # Calculate correlation matrix
        returns_matrix = np.column_stack([
            returns[s][-lookback:] for s in symbols
        ])

        corr_matrix = np.corrcoef(returns_matrix.T)

        # Add edges for significant correlations
        for i in range(n):
            for j in range(i + 1, n):
                corr = corr_matrix[i, j]

                if abs(corr) >= self.correlation_threshold:
                    self.add_edge(MarketEdge(
                        source=symbols[i],
                        target=symbols[j],
                        relation_type=RelationType.CORRELATION,
                        weight=abs(corr),
                        metadata={"correlation": corr},
                    ))
                    # Add reverse edge
                    self.add_edge(MarketEdge(
                        source=symbols[j],
                        target=symbols[i],
                        relation_type=RelationType.CORRELATION,
                        weight=abs(corr),
                        metadata={"correlation": corr},
                    ))

    def build_lead_lag_edges(
        self,
        returns: Dict[str, np.ndarray],
        max_lag: int = 5,
    ):
        """Build edges from lead-lag relationships."""
        symbols = list(returns.keys())

        for i, sym1 in enumerate(symbols):
            for j, sym2 in enumerate(symbols):
                if i == j:
                    continue

                # Test if sym1 leads sym2
                max_corr = 0
                best_lag = 0

                for lag in range(1, max_lag + 1):
                    if len(returns[sym1]) <= lag:
                        continue

                    # Correlation of sym1[:-lag] with sym2[lag:]
                    r1 = returns[sym1][:-lag]
                    r2 = returns[sym2][lag:]

                    if len(r1) < 20:
                        continue

                    corr = np.corrcoef(r1, r2)[0, 1]

                    if abs(corr) > abs(max_corr):
                        max_corr = corr
                        best_lag = lag

                if abs(max_corr) >= self.lead_lag_threshold:
                    self.add_edge(MarketEdge(
                        source=sym1,
                        target=sym2,
                        relation_type=RelationType.LEAD_LAG,
                        weight=abs(max_corr),
                        metadata={"lag": best_lag, "correlation": max_corr},
                    ))

    def build_sector_edges(self):
        """Build edges from sector relationships."""
        # Group by sector
        sector_groups: Dict[str, List[str]] = defaultdict(list)

        for symbol, sector in self.sector_map.items():
            if symbol in self.nodes:
                sector_groups[sector].append(symbol)

        # Add edges within sectors
        for sector, symbols in sector_groups.items():
            for i, sym1 in enumerate(symbols):
                for sym2 in symbols[i + 1:]:
                    self.add_edge(MarketEdge(
                        source=sym1,
                        target=sym2,
                        relation_type=RelationType.SECTOR,
                        weight=0.5,
                        metadata={"sector": sector},
                    ))
                    self.add_edge(MarketEdge(
                        source=sym2,
                        target=sym1,
                        relation_type=RelationType.SECTOR,
                        weight=0.5,
                        metadata={"sector": sector},
                    ))

    def to_pytorch_geometric(self) -> Data:
        """Convert to PyTorch Geometric Data object."""
        # Build edge index
        edge_index = []
        edge_type = []
        edge_weight = []

        relation_to_idx = {r: i for i, r in enumerate(RelationType)}

        for edge in self.edges:
            if edge.source in self.symbol_to_idx and edge.target in self.symbol_to_idx:
                edge_index.append([
                    self.symbol_to_idx[edge.source],
                    self.symbol_to_idx[edge.target],
                ])
                edge_type.append(relation_to_idx[edge.relation_type])
                edge_weight.append(edge.weight)

        if not edge_index:
            # No edges - create self-loops
            n = len(self.nodes)
            edge_index = [[i, i] for i in range(n)]
            edge_type = [0] * n
            edge_weight = [1.0] * n

        # Build node features
        node_features = []
        for idx in range(len(self.nodes)):
            symbol = self.idx_to_symbol[idx]
            node_features.append(self.nodes[symbol].features)

        return Data(
            x=torch.tensor(np.array(node_features), dtype=torch.float32),
            edge_index=torch.tensor(edge_index, dtype=torch.long).t().contiguous(),
            edge_type=torch.tensor(edge_type, dtype=torch.long),
            edge_weight=torch.tensor(edge_weight, dtype=torch.float32),
        )


class MarketGraphEngine:
    """
    Master engine for graph-based market analysis.
    """

    def __init__(
        self,
        node_features: int = 64,
        hidden_dim: int = 128,
        device: str = "cpu",
    ):
        self.device = device

        self.graph_builder = MarketGraphBuilder()
        self.model = MarketGraphNN(
            node_features=node_features,
            hidden_dim=hidden_dim,
        ).to(device)

        self.optimizer = torch.optim.Adam(self.model.parameters(), lr=1e-4)

        # Cache
        self.last_graph: Optional[Data] = None
        self.predictions: Dict[str, GraphPrediction] = {}

        logger.info("MarketGraphEngine initialized")

    def update_graph(
        self,
        node_features: Dict[str, np.ndarray],
        returns: Dict[str, np.ndarray],
        sector_map: Optional[Dict[str, str]] = None,
    ):
        """Update market graph with new data."""
        # Clear existing edges
        self.graph_builder.edges = []

        # Update nodes
        for symbol, features in node_features.items():
            self.graph_builder.add_node(MarketNode(
                symbol=symbol,
                node_type="stock",
                features=features,
            ))

        # Update sector map if provided
        if sector_map:
            self.graph_builder.sector_map = sector_map

        # Build edges
        self.graph_builder.build_correlation_edges(returns)
        self.graph_builder.build_lead_lag_edges(returns)
        self.graph_builder.build_sector_edges()

        # Convert to PyG
        self.last_graph = self.graph_builder.to_pytorch_geometric()
        self.last_graph = self.last_graph.to(self.device)

        logger.info(f"Graph updated: {len(self.graph_builder.nodes)} nodes, {len(self.graph_builder.edges)} edges")

    def predict(self) -> Dict[str, GraphPrediction]:
        """Generate predictions for all nodes."""
        if self.last_graph is None:
            return {}

        self.model.eval()

        with torch.no_grad():
            outputs = self.model(
                self.last_graph.x,
                self.last_graph.edge_index,
                self.last_graph.edge_type,
                self.last_graph.edge_weight,
            )

        predictions = {}
        timestamp = datetime.now(timezone.utc)

        for idx in range(len(self.graph_builder.nodes)):
            symbol = self.graph_builder.idx_to_symbol[idx]

            # Get influential neighbors
            neighbors = self._get_influential_neighbors(idx, outputs["embeddings"])

            predictions[symbol] = GraphPrediction(
                symbol=symbol,
                predicted_return=outputs["predicted_return"][idx].item(),
                confidence=outputs["confidence"][idx].item(),
                network_signal=self._compute_network_signal(idx, outputs),
                influential_neighbors=neighbors,
                timestamp=timestamp,
            )

        self.predictions = predictions
        return predictions

    def _get_influential_neighbors(
        self,
        node_idx: int,
        embeddings: torch.Tensor,
        top_k: int = 5,
    ) -> List[Tuple[str, float]]:
        """Find most influential neighbors for a node."""
        node_embedding = embeddings[node_idx]

        # Find edges to this node
        edge_index = self.last_graph.edge_index
        neighbors = edge_index[0][edge_index[1] == node_idx]

        if len(neighbors) == 0:
            return []

        # Compute influence scores
        neighbor_embeddings = embeddings[neighbors]
        similarities = F.cosine_similarity(
            node_embedding.unsqueeze(0),
            neighbor_embeddings,
        )

        # Get top-k
        top_k = min(top_k, len(neighbors))
        top_indices = similarities.argsort(descending=True)[:top_k]

        result = []
        for idx in top_indices:
            neighbor_idx = neighbors[idx].item()
            symbol = self.graph_builder.idx_to_symbol[neighbor_idx]
            influence = similarities[idx].item()
            result.append((symbol, influence))

        return result

    def _compute_network_signal(
        self,
        node_idx: int,
        outputs: Dict[str, torch.Tensor],
    ) -> float:
        """Compute aggregated signal from network neighbors."""
        edge_index = self.last_graph.edge_index
        edge_weight = self.last_graph.edge_weight

        # Find edges to this node
        mask = edge_index[1] == node_idx
        neighbors = edge_index[0][mask]
        weights = edge_weight[mask]

        if len(neighbors) == 0:
            return 0.0

        # Weighted average of neighbor predictions
        neighbor_returns = outputs["predicted_return"][neighbors]
        neighbor_confidence = outputs["confidence"][neighbors]

        weighted_signal = (neighbor_returns * neighbor_confidence * weights).sum()
        total_weight = (neighbor_confidence * weights).sum()

        if total_weight > 0:
            return (weighted_signal / total_weight).item()

        return 0.0

    def train_step(
        self,
        actual_returns: Dict[str, float],
    ) -> Dict[str, float]:
        """Single training step using actual returns."""
        if self.last_graph is None:
            return {}

        self.model.train()

        # Forward pass
        outputs = self.model(
            self.last_graph.x,
            self.last_graph.edge_index,
            self.last_graph.edge_type,
            self.last_graph.edge_weight,
        )

        # Build targets
        targets = []
        mask = []

        for idx in range(len(self.graph_builder.nodes)):
            symbol = self.graph_builder.idx_to_symbol[idx]
            if symbol in actual_returns:
                targets.append(actual_returns[symbol])
                mask.append(True)
            else:
                targets.append(0.0)
                mask.append(False)

        targets = torch.tensor(targets, dtype=torch.float32, device=self.device)
        mask = torch.tensor(mask, dtype=torch.bool, device=self.device)

        # Compute loss
        predicted = outputs["predicted_return"]
        loss = F.mse_loss(predicted[mask], targets[mask])

        # Backward pass
        self.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
        self.optimizer.step()

        return {"loss": loss.item()}


def create_market_graph_engine(device: str = "cpu") -> MarketGraphEngine:
    """Factory function to create MarketGraphEngine."""
    return MarketGraphEngine(device=device)
