"""
Predictive Order Book Model.

State-of-the-art limit order book (LOB) modeling:
- Deep learning for order book dynamics
- Price impact prediction
- Queue position modeling
- Market maker behavior prediction
- Liquidity forecasting
- Adverse selection detection

Used by HFT firms and market makers to predict
short-term price movements from microstructure.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from collections import deque
from enum import Enum
import logging


logger = logging.getLogger(__name__)


class OrderBookSide(Enum):
    """Order book side."""
    BID = "bid"
    ASK = "ask"


@dataclass
class OrderBookLevel:
    """Single price level in order book."""
    price: float
    size: int
    order_count: int
    timestamp: datetime


@dataclass
class OrderBookSnapshot:
    """Complete order book snapshot."""
    symbol: str
    timestamp: datetime
    bids: List[OrderBookLevel]
    asks: List[OrderBookLevel]
    mid_price: float = 0.0
    spread: float = 0.0
    imbalance: float = 0.0

    def __post_init__(self):
        if self.bids and self.asks:
            self.mid_price = (self.bids[0].price + self.asks[0].price) / 2
            self.spread = self.asks[0].price - self.bids[0].price
            bid_vol = sum(l.size for l in self.bids[:5])
            ask_vol = sum(l.size for l in self.asks[:5])
            self.imbalance = (bid_vol - ask_vol) / (bid_vol + ask_vol + 1)


@dataclass
class LOBPrediction:
    """Prediction from LOB model."""
    symbol: str
    timestamp: datetime
    predicted_mid_change: float  # Expected mid price change
    predicted_direction: int  # -1, 0, 1
    confidence: float
    predicted_spread_change: float
    predicted_volatility: float
    queue_prediction: Dict[str, float]  # Predicted fills
    features: Dict[str, float] = field(default_factory=dict)


@dataclass
class TradeFlow:
    """Aggregated trade flow."""
    buy_volume: int
    sell_volume: int
    buy_trades: int
    sell_trades: int
    net_flow: int
    vwap: float
    aggressiveness: float  # % of trades that crossed spread


class OrderBookEncoder(nn.Module):
    """
    Encode order book state using attention mechanism.

    Learns which price levels are most informative.
    """

    def __init__(
        self,
        n_levels: int = 10,
        level_features: int = 4,  # price, size, order_count, time
        hidden_dim: int = 64,
        n_heads: int = 4,
    ):
        super().__init__()

        self.n_levels = n_levels

        # Level embedding
        self.level_embed = nn.Linear(level_features, hidden_dim)

        # Position encoding for price levels
        self.position_embed = nn.Parameter(
            torch.randn(1, n_levels * 2, hidden_dim) * 0.02
        )

        # Side embedding (bid vs ask)
        self.side_embed = nn.Embedding(2, hidden_dim)

        # Self-attention
        self.attention = nn.MultiheadAttention(
            hidden_dim, n_heads, batch_first=True, dropout=0.1
        )

        # Output projection
        self.output = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.ReLU(),
        )

    def forward(
        self,
        bids: torch.Tensor,
        asks: torch.Tensor,
    ) -> torch.Tensor:
        """
        Encode order book.

        Args:
            bids: Bid levels [batch, n_levels, features]
            asks: Ask levels [batch, n_levels, features]
        """
        batch_size = bids.size(0)

        # Embed levels
        bid_embed = self.level_embed(bids)  # [batch, n_levels, hidden]
        ask_embed = self.level_embed(asks)

        # Add side embeddings
        bid_side = self.side_embed(torch.zeros(batch_size, self.n_levels, dtype=torch.long, device=bids.device))
        ask_side = self.side_embed(torch.ones(batch_size, self.n_levels, dtype=torch.long, device=bids.device))

        bid_embed = bid_embed + bid_side
        ask_embed = ask_embed + ask_side

        # Concatenate bid and ask sides
        x = torch.cat([bid_embed, ask_embed], dim=1)  # [batch, 2*n_levels, hidden]

        # Add position encoding
        x = x + self.position_embed[:, :x.size(1), :]

        # Self-attention
        attn_out, _ = self.attention(x, x, x)
        x = x + attn_out

        # Global pooling
        x = x.mean(dim=1)  # [batch, hidden]

        return self.output(x)


class TemporalLOBModel(nn.Module):
    """
    Temporal model for order book sequences.

    Captures how order book evolves over time.
    """

    def __init__(
        self,
        hidden_dim: int = 64,
        n_layers: int = 2,
        seq_len: int = 100,
    ):
        super().__init__()

        self.seq_len = seq_len

        # LSTM for temporal modeling
        self.lstm = nn.LSTM(
            hidden_dim, hidden_dim,
            num_layers=n_layers,
            batch_first=True,
            dropout=0.1 if n_layers > 1 else 0,
            bidirectional=False,
        )

        # Attention over time
        self.temporal_attention = nn.MultiheadAttention(
            hidden_dim, num_heads=4, batch_first=True
        )

        # Output
        self.output = nn.Linear(hidden_dim, hidden_dim)

    def forward(
        self,
        x: torch.Tensor,
        hidden: Optional[Tuple[torch.Tensor, torch.Tensor]] = None,
    ) -> Tuple[torch.Tensor, Tuple[torch.Tensor, torch.Tensor]]:
        """
        Process sequence of order book encodings.

        Args:
            x: Sequence [batch, seq_len, hidden]
            hidden: Optional LSTM hidden state
        """
        # LSTM
        lstm_out, hidden = self.lstm(x, hidden)

        # Temporal attention
        attn_out, _ = self.temporal_attention(lstm_out, lstm_out, lstm_out)
        lstm_out = lstm_out + attn_out

        # Use last output
        out = self.output(lstm_out[:, -1, :])

        return out, hidden


class TradeFlowEncoder(nn.Module):
    """Encode trade flow information."""

    def __init__(self, input_dim: int = 8, hidden_dim: int = 32):
        super().__init__()

        self.encoder = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.encoder(x)


class DeepLOBModel(nn.Module):
    """
    Deep Learning model for Limit Order Book.

    Combines:
    - CNN for spatial patterns in order book
    - Attention for level importance
    - LSTM for temporal dynamics
    - Trade flow features
    """

    def __init__(
        self,
        n_levels: int = 10,
        level_features: int = 4,
        hidden_dim: int = 128,
        seq_len: int = 100,
        n_horizons: int = 5,  # Multiple prediction horizons
    ):
        super().__init__()

        self.n_levels = n_levels
        self.n_horizons = n_horizons

        # Order book encoder
        self.ob_encoder = OrderBookEncoder(
            n_levels=n_levels,
            level_features=level_features,
            hidden_dim=hidden_dim // 2,
        )

        # Trade flow encoder
        self.flow_encoder = TradeFlowEncoder(
            input_dim=8, hidden_dim=hidden_dim // 4
        )

        # Temporal model
        combined_dim = hidden_dim // 2 + hidden_dim // 4
        self.temporal = TemporalLOBModel(
            hidden_dim=combined_dim,
            seq_len=seq_len,
        )

        # Prediction heads
        self.direction_head = nn.Sequential(
            nn.Linear(combined_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden_dim // 2, 3 * n_horizons),  # 3 classes per horizon
        )

        self.magnitude_head = nn.Sequential(
            nn.Linear(combined_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden_dim // 2, n_horizons),
        )

        self.volatility_head = nn.Sequential(
            nn.Linear(combined_dim, hidden_dim // 4),
            nn.ReLU(),
            nn.Linear(hidden_dim // 4, n_horizons),
            nn.Softplus(),
        )

        self.spread_head = nn.Sequential(
            nn.Linear(combined_dim, hidden_dim // 4),
            nn.ReLU(),
            nn.Linear(hidden_dim // 4, n_horizons),
        )

    def forward(
        self,
        bids: torch.Tensor,
        asks: torch.Tensor,
        trade_flow: torch.Tensor,
        hidden: Optional[Tuple] = None,
    ) -> Dict[str, torch.Tensor]:
        """
        Forward pass.

        Args:
            bids: [batch, seq_len, n_levels, features]
            asks: [batch, seq_len, n_levels, features]
            trade_flow: [batch, seq_len, flow_features]
            hidden: Optional LSTM hidden state
        """
        batch_size, seq_len = bids.shape[:2]

        # Encode each timestep
        ob_encodings = []
        for t in range(seq_len):
            ob_enc = self.ob_encoder(bids[:, t], asks[:, t])
            ob_encodings.append(ob_enc)

        ob_seq = torch.stack(ob_encodings, dim=1)  # [batch, seq, hidden]

        # Encode trade flow
        flow_enc = self.flow_encoder(trade_flow)  # [batch, seq, hidden]

        # Combine
        combined = torch.cat([ob_seq, flow_enc], dim=-1)

        # Temporal processing
        temporal_out, new_hidden = self.temporal(combined, hidden)

        # Predictions
        direction_logits = self.direction_head(temporal_out)
        direction_logits = direction_logits.view(batch_size, self.n_horizons, 3)

        magnitude = self.magnitude_head(temporal_out)
        volatility = self.volatility_head(temporal_out)
        spread_change = self.spread_head(temporal_out)

        return {
            "direction_logits": direction_logits,  # [batch, horizons, 3]
            "magnitude": magnitude,  # [batch, horizons]
            "volatility": volatility,  # [batch, horizons]
            "spread_change": spread_change,  # [batch, horizons]
            "hidden": new_hidden,
        }


class QueuePositionModel(nn.Module):
    """
    Model for predicting queue position and fill probability.

    Essential for market makers to know if their orders will execute.
    """

    def __init__(
        self,
        hidden_dim: int = 64,
    ):
        super().__init__()

        # Input: queue position, order size, price level, spread, volatility, etc.
        self.encoder = nn.Sequential(
            nn.Linear(10, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
        )

        # Fill probability prediction
        self.fill_prob_head = nn.Sequential(
            nn.Linear(hidden_dim, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
            nn.Sigmoid(),
        )

        # Time to fill prediction
        self.time_to_fill_head = nn.Sequential(
            nn.Linear(hidden_dim, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
            nn.Softplus(),
        )

        # Adverse selection probability
        self.adverse_selection_head = nn.Sequential(
            nn.Linear(hidden_dim, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
            nn.Sigmoid(),
        )

    def forward(
        self,
        queue_features: torch.Tensor,
    ) -> Dict[str, torch.Tensor]:
        """
        Predict queue-related metrics.

        Args:
            queue_features: [batch, 10] - position, size, level, etc.
        """
        encoded = self.encoder(queue_features)

        return {
            "fill_probability": self.fill_prob_head(encoded).squeeze(-1),
            "time_to_fill": self.time_to_fill_head(encoded).squeeze(-1),
            "adverse_selection": self.adverse_selection_head(encoded).squeeze(-1),
        }


class LOBFeatureExtractor:
    """
    Extract features from order book for ML models.
    """

    def __init__(self, n_levels: int = 10):
        self.n_levels = n_levels

    def extract(self, snapshot: OrderBookSnapshot) -> Dict[str, np.ndarray]:
        """Extract features from snapshot."""
        features = {}

        # Basic features
        features["mid_price"] = snapshot.mid_price
        features["spread"] = snapshot.spread
        features["spread_bps"] = snapshot.spread / snapshot.mid_price * 10000

        # Level features
        bid_prices = np.array([l.price for l in snapshot.bids[:self.n_levels]])
        bid_sizes = np.array([l.size for l in snapshot.bids[:self.n_levels]])
        ask_prices = np.array([l.price for l in snapshot.asks[:self.n_levels]])
        ask_sizes = np.array([l.size for l in snapshot.asks[:self.n_levels]])

        # Pad if needed
        if len(bid_prices) < self.n_levels:
            bid_prices = np.pad(bid_prices, (0, self.n_levels - len(bid_prices)))
            bid_sizes = np.pad(bid_sizes, (0, self.n_levels - len(bid_sizes)))
        if len(ask_prices) < self.n_levels:
            ask_prices = np.pad(ask_prices, (0, self.n_levels - len(ask_prices)))
            ask_sizes = np.pad(ask_sizes, (0, self.n_levels - len(ask_sizes)))

        features["bid_prices"] = bid_prices
        features["bid_sizes"] = bid_sizes
        features["ask_prices"] = ask_prices
        features["ask_sizes"] = ask_sizes

        # Imbalance features
        features["imbalance_1"] = self._imbalance(bid_sizes[:1], ask_sizes[:1])
        features["imbalance_5"] = self._imbalance(bid_sizes[:5], ask_sizes[:5])
        features["imbalance_10"] = self._imbalance(bid_sizes, ask_sizes)

        # Weighted imbalance
        weights = np.exp(-np.arange(self.n_levels) * 0.3)
        features["weighted_imbalance"] = self._imbalance(
            bid_sizes * weights, ask_sizes * weights
        )

        # Depth features
        features["total_bid_depth"] = bid_sizes.sum()
        features["total_ask_depth"] = ask_sizes.sum()
        features["depth_ratio"] = features["total_bid_depth"] / (features["total_ask_depth"] + 1)

        # Price level features
        features["bid_slope"] = self._calculate_slope(bid_prices, bid_sizes)
        features["ask_slope"] = self._calculate_slope(ask_prices, ask_sizes)

        return features

    def _imbalance(self, bid_vol: np.ndarray, ask_vol: np.ndarray) -> float:
        """Calculate volume imbalance."""
        total = bid_vol.sum() + ask_vol.sum()
        if total == 0:
            return 0.0
        return (bid_vol.sum() - ask_vol.sum()) / total

    def _calculate_slope(self, prices: np.ndarray, sizes: np.ndarray) -> float:
        """Calculate price-size slope."""
        if len(prices) < 2:
            return 0.0

        # Linear regression of size on price distance
        price_dist = np.abs(prices - prices[0])
        if price_dist[1:].sum() == 0:
            return 0.0

        return np.corrcoef(price_dist[1:], sizes[1:])[0, 1]


class OrderBookPredictor:
    """
    Main predictor for order book dynamics.

    Integrates all LOB models and feature extraction.
    """

    def __init__(
        self,
        n_levels: int = 10,
        seq_len: int = 100,
        device: str = "cpu",
    ):
        self.device = device
        self.n_levels = n_levels
        self.seq_len = seq_len

        self.feature_extractor = LOBFeatureExtractor(n_levels)

        self.model = DeepLOBModel(
            n_levels=n_levels,
            seq_len=seq_len,
        ).to(device)

        self.queue_model = QueuePositionModel().to(device)

        self.optimizer = torch.optim.Adam(
            list(self.model.parameters()) + list(self.queue_model.parameters()),
            lr=1e-4,
        )

        # History for temporal model
        self.snapshot_history: deque = deque(maxlen=seq_len)
        self.flow_history: deque = deque(maxlen=seq_len)

        # Hidden state
        self.hidden: Optional[Tuple] = None

        logger.info("OrderBookPredictor initialized")

    def update(
        self,
        snapshot: OrderBookSnapshot,
        trade_flow: Optional[TradeFlow] = None,
    ):
        """Update with new order book snapshot."""
        features = self.feature_extractor.extract(snapshot)
        self.snapshot_history.append(features)

        if trade_flow:
            flow_features = np.array([
                trade_flow.buy_volume,
                trade_flow.sell_volume,
                trade_flow.buy_trades,
                trade_flow.sell_trades,
                trade_flow.net_flow,
                trade_flow.vwap,
                trade_flow.aggressiveness,
                snapshot.mid_price,
            ])
        else:
            flow_features = np.zeros(8)

        self.flow_history.append(flow_features)

    def predict(self) -> Optional[LOBPrediction]:
        """Generate prediction from current state."""
        if len(self.snapshot_history) < 10:
            return None

        self.model.eval()

        # Prepare tensors
        bids_list = []
        asks_list = []

        for features in self.snapshot_history:
            # Create level tensor [n_levels, 4]
            bid_levels = np.stack([
                features["bid_prices"],
                features["bid_sizes"],
                np.zeros(self.n_levels),  # order count placeholder
                np.zeros(self.n_levels),  # time placeholder
            ], axis=1)

            ask_levels = np.stack([
                features["ask_prices"],
                features["ask_sizes"],
                np.zeros(self.n_levels),
                np.zeros(self.n_levels),
            ], axis=1)

            bids_list.append(bid_levels)
            asks_list.append(ask_levels)

        bids = torch.tensor(np.array(bids_list), dtype=torch.float32).unsqueeze(0).to(self.device)
        asks = torch.tensor(np.array(asks_list), dtype=torch.float32).unsqueeze(0).to(self.device)
        flows = torch.tensor(np.array(list(self.flow_history)), dtype=torch.float32).unsqueeze(0).to(self.device)

        with torch.no_grad():
            outputs = self.model(bids, asks, flows, self.hidden)
            self.hidden = outputs["hidden"]

        # Get predictions for first horizon
        direction_probs = F.softmax(outputs["direction_logits"][0, 0], dim=0)
        predicted_direction = direction_probs.argmax().item() - 1  # Map to -1, 0, 1

        latest_features = list(self.snapshot_history)[-1]

        return LOBPrediction(
            symbol="",
            timestamp=datetime.now(timezone.utc),
            predicted_mid_change=outputs["magnitude"][0, 0].item(),
            predicted_direction=predicted_direction,
            confidence=direction_probs.max().item(),
            predicted_spread_change=outputs["spread_change"][0, 0].item(),
            predicted_volatility=outputs["volatility"][0, 0].item(),
            queue_prediction={},
            features={
                "imbalance": latest_features.get("imbalance_5", 0),
                "spread_bps": latest_features.get("spread_bps", 0),
                "depth_ratio": latest_features.get("depth_ratio", 1),
            },
        )

    def predict_queue(
        self,
        queue_position: int,
        order_size: int,
        price_level: int,
        side: OrderBookSide,
    ) -> Dict[str, float]:
        """Predict queue-related metrics."""
        if len(self.snapshot_history) == 0:
            return {"fill_probability": 0.5, "time_to_fill": 60.0, "adverse_selection": 0.1}

        latest = list(self.snapshot_history)[-1]

        # Build feature vector
        features = torch.tensor([
            queue_position,
            order_size,
            price_level,
            1 if side == OrderBookSide.BID else 0,
            latest.get("spread_bps", 10),
            latest.get("imbalance_5", 0),
            latest.get("total_bid_depth", 10000),
            latest.get("total_ask_depth", 10000),
            latest.get("bid_slope", 0),
            latest.get("ask_slope", 0),
        ], dtype=torch.float32).unsqueeze(0).to(self.device)

        self.queue_model.eval()

        with torch.no_grad():
            outputs = self.queue_model(features)

        return {
            "fill_probability": outputs["fill_probability"].item(),
            "time_to_fill": outputs["time_to_fill"].item(),
            "adverse_selection": outputs["adverse_selection"].item(),
        }

    def train_step(
        self,
        actual_direction: int,
        actual_magnitude: float,
    ) -> Dict[str, float]:
        """Single training step."""
        if len(self.snapshot_history) < self.seq_len:
            return {}

        self.model.train()

        # Prepare data (same as predict)
        bids_list = []
        asks_list = []

        for features in self.snapshot_history:
            bid_levels = np.stack([
                features["bid_prices"],
                features["bid_sizes"],
                np.zeros(self.n_levels),
                np.zeros(self.n_levels),
            ], axis=1)

            ask_levels = np.stack([
                features["ask_prices"],
                features["ask_sizes"],
                np.zeros(self.n_levels),
                np.zeros(self.n_levels),
            ], axis=1)

            bids_list.append(bid_levels)
            asks_list.append(ask_levels)

        bids = torch.tensor(np.array(bids_list), dtype=torch.float32).unsqueeze(0).to(self.device)
        asks = torch.tensor(np.array(asks_list), dtype=torch.float32).unsqueeze(0).to(self.device)
        flows = torch.tensor(np.array(list(self.flow_history)), dtype=torch.float32).unsqueeze(0).to(self.device)

        # Forward pass
        outputs = self.model(bids, asks, flows)

        # Calculate loss
        direction_target = torch.tensor([actual_direction + 1], device=self.device)
        direction_loss = F.cross_entropy(
            outputs["direction_logits"][:, 0, :],
            direction_target,
        )

        magnitude_target = torch.tensor([[actual_magnitude]], device=self.device)
        magnitude_loss = F.mse_loss(outputs["magnitude"][:, :1], magnitude_target)

        total_loss = direction_loss + magnitude_loss

        # Backward pass
        self.optimizer.zero_grad()
        total_loss.backward()
        torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
        self.optimizer.step()

        return {
            "total_loss": total_loss.item(),
            "direction_loss": direction_loss.item(),
            "magnitude_loss": magnitude_loss.item(),
        }


def create_orderbook_predictor(device: str = "cpu") -> OrderBookPredictor:
    """Create order book predictor."""
    return OrderBookPredictor(device=device)
