"""
Revolution Alpha Engine - Advanced ML Core

Institutional-grade machine learning infrastructure featuring:
- Temporal Fusion Transformers for time series prediction
- Ensemble methods with meta-learning
- Online learning for real-time adaptation
- Neural attention mechanisms for feature importance
- Uncertainty quantification with Monte Carlo dropout
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset
import numpy as np
from typing import Optional, Tuple, List, Dict, Any, Union
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
import logging
from datetime import datetime
import math

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class ModelConfig:
    """Configuration for ML models."""
    # Architecture
    input_dim: int = 128
    hidden_dim: int = 256
    num_layers: int = 4
    num_heads: int = 8
    dropout: float = 0.1

    # Training
    learning_rate: float = 1e-4
    weight_decay: float = 1e-5
    batch_size: int = 64
    max_epochs: int = 100
    early_stopping_patience: int = 10

    # Sequence
    sequence_length: int = 60
    prediction_horizon: int = 5

    # Uncertainty
    mc_dropout_samples: int = 100

    # Device
    device: str = "cuda" if torch.cuda.is_available() else "cpu"


# =============================================================================
# Positional Encoding
# =============================================================================

class PositionalEncoding(nn.Module):
    """Sinusoidal positional encoding for transformer."""

    def __init__(self, d_model: int, max_len: int = 5000, dropout: float = 0.1):
        super().__init__()
        self.dropout = nn.Dropout(p=dropout)

        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(
            torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model)
        )
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0)
        self.register_buffer('pe', pe)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x + self.pe[:, :x.size(1)]
        return self.dropout(x)


# =============================================================================
# Attention Mechanisms
# =============================================================================

class MultiHeadAttention(nn.Module):
    """Multi-head self-attention with interpretable attention weights."""

    def __init__(
        self,
        d_model: int,
        num_heads: int,
        dropout: float = 0.1,
        bias: bool = True
    ):
        super().__init__()
        assert d_model % num_heads == 0

        self.d_model = d_model
        self.num_heads = num_heads
        self.head_dim = d_model // num_heads
        self.scale = self.head_dim ** -0.5

        self.q_proj = nn.Linear(d_model, d_model, bias=bias)
        self.k_proj = nn.Linear(d_model, d_model, bias=bias)
        self.v_proj = nn.Linear(d_model, d_model, bias=bias)
        self.out_proj = nn.Linear(d_model, d_model, bias=bias)

        self.dropout = nn.Dropout(dropout)
        self._attention_weights = None

    def forward(
        self,
        query: torch.Tensor,
        key: torch.Tensor,
        value: torch.Tensor,
        mask: Optional[torch.Tensor] = None,
        return_attention: bool = False
    ) -> Union[torch.Tensor, Tuple[torch.Tensor, torch.Tensor]]:
        batch_size, seq_len, _ = query.shape

        # Project and reshape
        q = self.q_proj(query).view(batch_size, seq_len, self.num_heads, self.head_dim).transpose(1, 2)
        k = self.k_proj(key).view(batch_size, -1, self.num_heads, self.head_dim).transpose(1, 2)
        v = self.v_proj(value).view(batch_size, -1, self.num_heads, self.head_dim).transpose(1, 2)

        # Attention scores
        attn = torch.matmul(q, k.transpose(-2, -1)) * self.scale

        if mask is not None:
            attn = attn.masked_fill(mask == 0, float('-inf'))

        attn = F.softmax(attn, dim=-1)
        self._attention_weights = attn.detach()
        attn = self.dropout(attn)

        # Apply attention to values
        out = torch.matmul(attn, v)
        out = out.transpose(1, 2).contiguous().view(batch_size, seq_len, self.d_model)
        out = self.out_proj(out)

        if return_attention:
            return out, self._attention_weights
        return out

    @property
    def attention_weights(self) -> Optional[torch.Tensor]:
        """Get last computed attention weights for interpretability."""
        return self._attention_weights


class TemporalAttention(nn.Module):
    """
    Temporal attention for capturing time-varying importance.
    Used to weight different time steps based on their relevance.
    """

    def __init__(self, hidden_dim: int):
        super().__init__()
        self.attention = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.Tanh(),
            nn.Linear(hidden_dim // 2, 1),
        )

    def forward(self, x: torch.Tensor, mask: Optional[torch.Tensor] = None) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            x: (batch, seq_len, hidden_dim)
            mask: (batch, seq_len) boolean mask

        Returns:
            context: (batch, hidden_dim) weighted sum
            weights: (batch, seq_len) attention weights
        """
        scores = self.attention(x).squeeze(-1)  # (batch, seq_len)

        if mask is not None:
            scores = scores.masked_fill(~mask, float('-inf'))

        weights = F.softmax(scores, dim=-1)
        context = torch.bmm(weights.unsqueeze(1), x).squeeze(1)

        return context, weights


# =============================================================================
# Transformer Encoder Block
# =============================================================================

class TransformerEncoderBlock(nn.Module):
    """Single transformer encoder block with pre-norm."""

    def __init__(
        self,
        d_model: int,
        num_heads: int,
        dim_feedforward: int,
        dropout: float = 0.1
    ):
        super().__init__()

        self.norm1 = nn.LayerNorm(d_model)
        self.norm2 = nn.LayerNorm(d_model)

        self.self_attn = MultiHeadAttention(d_model, num_heads, dropout)

        self.ffn = nn.Sequential(
            nn.Linear(d_model, dim_feedforward),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(dim_feedforward, d_model),
            nn.Dropout(dropout),
        )

        self.dropout = nn.Dropout(dropout)

    def forward(
        self,
        x: torch.Tensor,
        mask: Optional[torch.Tensor] = None
    ) -> torch.Tensor:
        # Pre-norm self-attention
        residual = x
        x = self.norm1(x)
        x = self.self_attn(x, x, x, mask)
        x = self.dropout(x) + residual

        # Pre-norm feedforward
        residual = x
        x = self.norm2(x)
        x = self.ffn(x) + residual

        return x


# =============================================================================
# Variable Selection Network
# =============================================================================

class GatedResidualNetwork(nn.Module):
    """
    Gated Residual Network (GRN) from Temporal Fusion Transformer.
    Provides flexible nonlinear processing with skip connections.
    """

    def __init__(
        self,
        input_dim: int,
        hidden_dim: int,
        output_dim: int,
        dropout: float = 0.1,
        context_dim: Optional[int] = None
    ):
        super().__init__()

        self.input_dim = input_dim
        self.output_dim = output_dim
        self.context_dim = context_dim

        # Primary pathway
        self.fc1 = nn.Linear(input_dim, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, output_dim)

        # Context pathway
        if context_dim is not None:
            self.context_fc = nn.Linear(context_dim, hidden_dim, bias=False)

        # Gating
        self.gate = nn.Linear(hidden_dim, output_dim)

        # Skip connection
        if input_dim != output_dim:
            self.skip = nn.Linear(input_dim, output_dim)
        else:
            self.skip = None

        self.norm = nn.LayerNorm(output_dim)
        self.dropout = nn.Dropout(dropout)
        self.elu = nn.ELU()

    def forward(
        self,
        x: torch.Tensor,
        context: Optional[torch.Tensor] = None
    ) -> torch.Tensor:
        # Primary pathway
        hidden = self.fc1(x)

        # Add context if provided
        if context is not None and self.context_dim is not None:
            hidden = hidden + self.context_fc(context)

        hidden = self.elu(hidden)
        hidden = self.fc2(hidden)
        hidden = self.dropout(hidden)

        # Gating mechanism
        gate = torch.sigmoid(self.gate(self.elu(self.fc1(x))))
        hidden = gate * hidden

        # Skip connection
        if self.skip is not None:
            skip = self.skip(x)
        else:
            skip = x

        return self.norm(skip + hidden)


class VariableSelectionNetwork(nn.Module):
    """
    Variable Selection Network from Temporal Fusion Transformer.
    Learns to select relevant input variables.
    """

    def __init__(
        self,
        input_dim: int,
        num_inputs: int,
        hidden_dim: int,
        dropout: float = 0.1,
        context_dim: Optional[int] = None
    ):
        super().__init__()

        self.num_inputs = num_inputs
        self.hidden_dim = hidden_dim

        # Individual variable GRNs
        self.var_grns = nn.ModuleList([
            GatedResidualNetwork(input_dim, hidden_dim, hidden_dim, dropout)
            for _ in range(num_inputs)
        ])

        # Variable selection weights
        self.selection_grn = GatedResidualNetwork(
            num_inputs * hidden_dim,
            hidden_dim,
            num_inputs,
            dropout,
            context_dim
        )

        self.softmax = nn.Softmax(dim=-1)

    def forward(
        self,
        inputs: List[torch.Tensor],
        context: Optional[torch.Tensor] = None
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            inputs: List of (batch, seq_len, input_dim) tensors
            context: Optional (batch, context_dim) context tensor

        Returns:
            output: (batch, seq_len, hidden_dim) selected features
            weights: (batch, seq_len, num_inputs) selection weights
        """
        # Process each variable
        var_outputs = []
        for i, (var_input, grn) in enumerate(zip(inputs, self.var_grns)):
            var_outputs.append(grn(var_input))

        var_outputs = torch.stack(var_outputs, dim=-1)  # (batch, seq_len, hidden_dim, num_inputs)

        # Flatten for selection
        batch_size, seq_len, hidden_dim, num_inputs = var_outputs.shape
        flat_inputs = torch.cat([grn(inp) for inp, grn in zip(inputs, self.var_grns)], dim=-1)

        # Compute selection weights
        if context is not None:
            context = context.unsqueeze(1).expand(-1, seq_len, -1)

        weights = self.selection_grn(flat_inputs, context)
        weights = self.softmax(weights)  # (batch, seq_len, num_inputs)

        # Weighted combination
        weights_expanded = weights.unsqueeze(2)  # (batch, seq_len, 1, num_inputs)
        output = (var_outputs * weights_expanded).sum(dim=-1)  # (batch, seq_len, hidden_dim)

        return output, weights


# =============================================================================
# Temporal Fusion Transformer
# =============================================================================

class TemporalFusionTransformer(nn.Module):
    """
    Temporal Fusion Transformer for multi-horizon time series forecasting.

    This is a state-of-the-art architecture that combines:
    - Variable selection for feature importance
    - Gated residual connections
    - Temporal self-attention
    - Multi-horizon prediction

    Reference: https://arxiv.org/abs/1912.09363
    """

    def __init__(self, config: ModelConfig):
        super().__init__()
        self.config = config

        # Input projection
        self.input_projection = nn.Linear(config.input_dim, config.hidden_dim)

        # Positional encoding
        self.pos_encoding = PositionalEncoding(
            config.hidden_dim,
            config.sequence_length + config.prediction_horizon,
            config.dropout
        )

        # Encoder (historical)
        self.encoder_layers = nn.ModuleList([
            TransformerEncoderBlock(
                config.hidden_dim,
                config.num_heads,
                config.hidden_dim * 4,
                config.dropout
            )
            for _ in range(config.num_layers)
        ])

        # Temporal attention for aggregation
        self.temporal_attention = TemporalAttention(config.hidden_dim)

        # Output layers
        self.output_norm = nn.LayerNorm(config.hidden_dim)

        # Multi-horizon outputs
        self.output_layers = nn.ModuleList([
            nn.Linear(config.hidden_dim, 3)  # mean, lower, upper quantiles
            for _ in range(config.prediction_horizon)
        ])

        # Uncertainty estimation
        self.uncertainty_head = nn.Sequential(
            nn.Linear(config.hidden_dim, config.hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(config.hidden_dim // 2, 1),
            nn.Softplus()  # Ensure positive variance
        )

        self._init_weights()

    def _init_weights(self):
        """Initialize weights with Xavier uniform."""
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.xavier_uniform_(module.weight)
                if module.bias is not None:
                    nn.init.zeros_(module.bias)

    def forward(
        self,
        x: torch.Tensor,
        mask: Optional[torch.Tensor] = None
    ) -> Dict[str, torch.Tensor]:
        """
        Args:
            x: (batch, seq_len, input_dim) input features
            mask: Optional attention mask

        Returns:
            Dictionary containing:
            - predictions: (batch, horizon, 3) quantile predictions
            - uncertainty: (batch, horizon) uncertainty estimates
            - attention_weights: attention weights for interpretability
        """
        batch_size, seq_len, _ = x.shape

        # Project and add positional encoding
        x = self.input_projection(x)
        x = self.pos_encoding(x)

        # Encode
        for encoder in self.encoder_layers:
            x = encoder(x, mask)

        # Temporal aggregation
        context, temporal_weights = self.temporal_attention(x)

        # Generate multi-horizon predictions
        x = self.output_norm(x)

        predictions = []
        uncertainties = []

        # Use last hidden states for prediction
        last_hidden = x[:, -1, :]  # (batch, hidden_dim)

        for horizon_layer in self.output_layers:
            pred = horizon_layer(last_hidden)  # (batch, 3) - quantiles
            predictions.append(pred)

            unc = self.uncertainty_head(last_hidden)
            uncertainties.append(unc)

        predictions = torch.stack(predictions, dim=1)  # (batch, horizon, 3)
        uncertainties = torch.cat(uncertainties, dim=1)  # (batch, horizon)

        return {
            'predictions': predictions,
            'uncertainty': uncertainties,
            'attention_weights': temporal_weights,
            'context': context,
        }

    def predict_with_uncertainty(
        self,
        x: torch.Tensor,
        num_samples: int = 100
    ) -> Dict[str, torch.Tensor]:
        """
        Monte Carlo dropout for uncertainty estimation.
        """
        self.train()  # Enable dropout

        predictions = []
        for _ in range(num_samples):
            with torch.no_grad():
                out = self.forward(x)
                predictions.append(out['predictions'])

        predictions = torch.stack(predictions, dim=0)  # (samples, batch, horizon, 3)

        mean = predictions.mean(dim=0)
        std = predictions.std(dim=0)

        self.eval()

        return {
            'mean': mean,
            'std': std,
            'lower_95': mean - 1.96 * std,
            'upper_95': mean + 1.96 * std,
        }


# =============================================================================
# Ensemble Methods
# =============================================================================

class EnsembleModel(nn.Module):
    """
    Ensemble of diverse models with learned weighting.
    Combines multiple architectures for robust predictions.
    """

    def __init__(
        self,
        models: List[nn.Module],
        hidden_dim: int,
        learnable_weights: bool = True
    ):
        super().__init__()
        self.models = nn.ModuleList(models)
        self.num_models = len(models)

        if learnable_weights:
            # Meta-learner to combine predictions
            self.meta_learner = nn.Sequential(
                nn.Linear(self.num_models * 3, hidden_dim),
                nn.ReLU(),
                nn.Dropout(0.1),
                nn.Linear(hidden_dim, hidden_dim // 2),
                nn.ReLU(),
                nn.Linear(hidden_dim // 2, 3),  # Final prediction
            )

            # Confidence weights for each model
            self.confidence_net = nn.Sequential(
                nn.Linear(self.num_models * 3, self.num_models),
                nn.Softmax(dim=-1)
            )
        else:
            self.meta_learner = None
            self.register_buffer(
                'weights',
                torch.ones(self.num_models) / self.num_models
            )

    def forward(self, x: torch.Tensor) -> Dict[str, torch.Tensor]:
        """
        Forward pass through ensemble.
        """
        all_predictions = []
        all_uncertainties = []

        for model in self.models:
            out = model(x)
            all_predictions.append(out['predictions'][:, 0, :])  # First horizon
            if 'uncertainty' in out:
                all_uncertainties.append(out['uncertainty'][:, 0:1])

        # Stack predictions
        stacked = torch.cat(all_predictions, dim=-1)  # (batch, num_models * 3)

        if self.meta_learner is not None:
            # Learned combination
            final_pred = self.meta_learner(stacked)
            weights = self.confidence_net(stacked)
        else:
            # Simple average
            preds = torch.stack(all_predictions, dim=1)  # (batch, num_models, 3)
            final_pred = (preds * self.weights.view(1, -1, 1)).sum(dim=1)
            weights = self.weights.expand(x.shape[0], -1)

        return {
            'predictions': final_pred,
            'individual_predictions': all_predictions,
            'model_weights': weights,
            'disagreement': torch.stack(all_predictions).std(dim=0).mean(dim=-1),
        }


# =============================================================================
# Online Learning Module
# =============================================================================

class OnlineLearner:
    """
    Online learning wrapper for continuous model adaptation.
    Implements experience replay and adaptive learning rates.
    """

    def __init__(
        self,
        model: nn.Module,
        config: ModelConfig,
        buffer_size: int = 10000
    ):
        self.model = model
        self.config = config
        self.device = config.device

        # Optimizer with adaptive learning rate
        self.optimizer = torch.optim.AdamW(
            model.parameters(),
            lr=config.learning_rate,
            weight_decay=config.weight_decay
        )

        # Learning rate scheduler
        self.scheduler = torch.optim.lr_scheduler.CosineAnnealingWarmRestarts(
            self.optimizer,
            T_0=100,
            T_mult=2
        )

        # Experience replay buffer
        self.buffer_size = buffer_size
        self.buffer: List[Tuple[torch.Tensor, torch.Tensor]] = []
        self.buffer_idx = 0

        # Performance tracking
        self.recent_losses: List[float] = []
        self.adaptation_rate = 1.0

        # Loss function
        self.criterion = nn.HuberLoss()

    def update(
        self,
        features: torch.Tensor,
        targets: torch.Tensor,
        importance: float = 1.0
    ) -> float:
        """
        Online update with single sample or mini-batch.
        """
        self.model.train()

        features = features.to(self.device)
        targets = targets.to(self.device)

        # Add to replay buffer
        self._add_to_buffer(features, targets)

        # Forward pass
        self.optimizer.zero_grad()
        outputs = self.model(features)

        # Compute loss
        pred = outputs['predictions'][:, 0, 1]  # Median prediction
        loss = self.criterion(pred, targets) * importance

        # Backward pass
        loss.backward()

        # Gradient clipping
        torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)

        self.optimizer.step()
        self.scheduler.step()

        # Track loss
        loss_val = loss.item()
        self.recent_losses.append(loss_val)
        if len(self.recent_losses) > 100:
            self.recent_losses.pop(0)

        return loss_val

    def replay_update(self, batch_size: int = 32) -> Optional[float]:
        """
        Update from replay buffer for stability.
        """
        if len(self.buffer) < batch_size:
            return None

        # Sample from buffer
        indices = np.random.choice(len(self.buffer), batch_size, replace=False)

        features = torch.cat([self.buffer[i][0] for i in indices], dim=0)
        targets = torch.cat([self.buffer[i][1] for i in indices], dim=0)

        return self.update(features, targets, importance=0.5)

    def _add_to_buffer(self, features: torch.Tensor, targets: torch.Tensor):
        """Add experience to replay buffer."""
        if len(self.buffer) < self.buffer_size:
            self.buffer.append((features.detach().cpu(), targets.detach().cpu()))
        else:
            self.buffer[self.buffer_idx] = (features.detach().cpu(), targets.detach().cpu())
            self.buffer_idx = (self.buffer_idx + 1) % self.buffer_size

    def get_adaptation_status(self) -> Dict[str, float]:
        """Get current adaptation metrics."""
        if not self.recent_losses:
            return {'avg_loss': 0, 'loss_trend': 0, 'lr': self.optimizer.param_groups[0]['lr']}

        avg_loss = np.mean(self.recent_losses)

        # Calculate trend
        if len(self.recent_losses) >= 10:
            recent = np.mean(self.recent_losses[-10:])
            older = np.mean(self.recent_losses[:-10]) if len(self.recent_losses) > 10 else recent
            trend = (older - recent) / (older + 1e-8)  # Positive = improving
        else:
            trend = 0

        return {
            'avg_loss': avg_loss,
            'loss_trend': trend,
            'lr': self.optimizer.param_groups[0]['lr'],
            'buffer_size': len(self.buffer),
        }


# =============================================================================
# Feature Importance
# =============================================================================

class InterpretableAttention(nn.Module):
    """
    Attention mechanism that provides interpretable feature importance.
    """

    def __init__(self, input_dim: int, hidden_dim: int):
        super().__init__()

        self.query = nn.Linear(input_dim, hidden_dim)
        self.key = nn.Linear(input_dim, hidden_dim)
        self.value = nn.Linear(input_dim, hidden_dim)

        self.feature_importance = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.Tanh(),
            nn.Linear(hidden_dim, 1),
        )

        self._importance_scores = None

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            x: (batch, seq_len, input_dim)

        Returns:
            output: (batch, seq_len, hidden_dim)
            importance: (batch, input_dim) feature importance scores
        """
        # Standard attention
        q = self.query(x)
        k = self.key(x)
        v = self.value(x)

        attn = torch.softmax(torch.bmm(q, k.transpose(1, 2)) / math.sqrt(q.size(-1)), dim=-1)
        output = torch.bmm(attn, v)

        # Feature importance (average over sequence)
        importance = self.feature_importance(x).squeeze(-1)  # (batch, seq_len)
        importance = torch.softmax(importance, dim=-1)

        # Weighted average importance per feature
        self._importance_scores = importance

        return output, importance

    def get_feature_importance(self) -> Optional[torch.Tensor]:
        """Get last computed feature importance scores."""
        return self._importance_scores
