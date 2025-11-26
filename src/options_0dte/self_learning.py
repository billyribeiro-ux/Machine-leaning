"""
Revolution Alpha Engine - Self-Learning Neural Network for 0DTE Options
State-of-the-art adaptive learning system that continuously improves from market data.

This module provides:
- Deep neural network for pattern recognition
- Online learning with experience replay
- Adaptive feature extraction
- Market regime classification
- Continuous model improvement
- Pattern memory and recall
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Callable
from enum import Enum
from datetime import datetime, timedelta
from collections import deque
import json
import pickle
import hashlib
from abc import ABC, abstractmethod


class LearningMode(Enum):
    """Learning mode for the neural network."""
    SUPERVISED = "supervised"
    REINFORCEMENT = "reinforcement"
    ONLINE = "online"
    TRANSFER = "transfer"


class PatternType(Enum):
    """Types of patterns the system can learn."""
    MOMENTUM = "momentum"
    REVERSAL = "reversal"
    BREAKOUT = "breakout"
    BREAKDOWN = "breakdown"
    GAMMA_SQUEEZE = "gamma_squeeze"
    PIN_ACTION = "pin_action"
    VOL_EXPANSION = "vol_expansion"
    VOL_COMPRESSION = "vol_compression"
    OPEN_DRIVE = "open_drive"
    POWER_HOUR = "power_hour"
    MEAN_REVERSION = "mean_reversion"


@dataclass
class LearningConfig:
    """Configuration for the self-learning system."""
    # Network architecture
    hidden_layers: List[int] = field(default_factory=lambda: [256, 128, 64, 32])
    activation: str = "relu"
    dropout_rate: float = 0.2

    # Learning parameters
    learning_rate: float = 0.001
    batch_size: int = 32
    memory_size: int = 10000
    min_samples_to_train: int = 100

    # Online learning
    online_learning_rate: float = 0.0001
    adaptation_rate: float = 0.01

    # Feature extraction
    lookback_periods: List[int] = field(default_factory=lambda: [5, 10, 20, 50])
    use_greeks: bool = True
    use_flow: bool = True
    use_gex: bool = True

    # Pattern recognition
    pattern_similarity_threshold: float = 0.85
    min_pattern_occurrences: int = 5


@dataclass
class PatternMemory:
    """Stores learned patterns for recall."""
    pattern_id: str
    pattern_type: PatternType
    features: np.ndarray
    outcome: str  # 'win', 'loss', 'scratch'
    profit_pct: float
    occurrences: int = 1
    last_seen: datetime = field(default_factory=datetime.now)
    confidence: float = 0.5
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            'pattern_id': self.pattern_id,
            'pattern_type': self.pattern_type.value,
            'features': self.features.tolist(),
            'outcome': self.outcome,
            'profit_pct': self.profit_pct,
            'occurrences': self.occurrences,
            'last_seen': self.last_seen.isoformat(),
            'confidence': self.confidence,
            'context': self.context
        }


class NeuralLayer:
    """Simple neural network layer implementation."""

    def __init__(
        self,
        input_size: int,
        output_size: int,
        activation: str = "relu"
    ):
        self.input_size = input_size
        self.output_size = output_size
        self.activation = activation

        # Initialize weights (Xavier initialization)
        self.weights = np.random.randn(input_size, output_size) * np.sqrt(2.0 / input_size)
        self.bias = np.zeros(output_size)

        # For Adam optimizer
        self.m_w = np.zeros_like(self.weights)
        self.v_w = np.zeros_like(self.weights)
        self.m_b = np.zeros_like(self.bias)
        self.v_b = np.zeros_like(self.bias)

        # Cache for backprop
        self.input_cache = None
        self.output_cache = None

    def _activate(self, x: np.ndarray) -> np.ndarray:
        """Apply activation function."""
        if self.activation == "relu":
            return np.maximum(0, x)
        elif self.activation == "sigmoid":
            return 1 / (1 + np.exp(-np.clip(x, -500, 500)))
        elif self.activation == "tanh":
            return np.tanh(x)
        elif self.activation == "softmax":
            exp_x = np.exp(x - np.max(x, axis=-1, keepdims=True))
            return exp_x / np.sum(exp_x, axis=-1, keepdims=True)
        else:
            return x

    def _activate_derivative(self, x: np.ndarray) -> np.ndarray:
        """Derivative of activation function."""
        if self.activation == "relu":
            return (x > 0).astype(float)
        elif self.activation == "sigmoid":
            s = self._activate(x)
            return s * (1 - s)
        elif self.activation == "tanh":
            return 1 - np.tanh(x) ** 2
        else:
            return np.ones_like(x)

    def forward(self, x: np.ndarray, training: bool = True) -> np.ndarray:
        """Forward pass through the layer."""
        self.input_cache = x
        z = np.dot(x, self.weights) + self.bias
        self.output_cache = self._activate(z)
        return self.output_cache

    def backward(
        self,
        grad_output: np.ndarray,
        learning_rate: float = 0.001
    ) -> np.ndarray:
        """Backward pass with gradient descent."""
        batch_size = grad_output.shape[0] if len(grad_output.shape) > 1 else 1

        # Gradient of activation
        z = np.dot(self.input_cache, self.weights) + self.bias
        grad_activation = grad_output * self._activate_derivative(z)

        # Gradients for weights and bias
        grad_weights = np.dot(self.input_cache.T, grad_activation) / batch_size
        grad_bias = np.mean(grad_activation, axis=0) if len(grad_activation.shape) > 1 else grad_activation

        # Adam optimizer
        beta1, beta2, epsilon = 0.9, 0.999, 1e-8
        self.m_w = beta1 * self.m_w + (1 - beta1) * grad_weights
        self.v_w = beta2 * self.v_w + (1 - beta2) * (grad_weights ** 2)
        self.m_b = beta1 * self.m_b + (1 - beta1) * grad_bias
        self.v_b = beta2 * self.v_b + (1 - beta2) * (grad_bias ** 2)

        # Update weights
        self.weights -= learning_rate * self.m_w / (np.sqrt(self.v_w) + epsilon)
        self.bias -= learning_rate * self.m_b / (np.sqrt(self.v_b) + epsilon)

        # Return gradient for previous layer
        return np.dot(grad_activation, self.weights.T)


class DropoutLayer:
    """Dropout layer for regularization."""

    def __init__(self, dropout_rate: float = 0.2):
        self.dropout_rate = dropout_rate
        self.mask = None

    def forward(self, x: np.ndarray, training: bool = True) -> np.ndarray:
        if training and self.dropout_rate > 0:
            self.mask = np.random.binomial(1, 1 - self.dropout_rate, x.shape) / (1 - self.dropout_rate)
            return x * self.mask
        return x

    def backward(self, grad_output: np.ndarray, learning_rate: float = 0.001) -> np.ndarray:
        if self.mask is not None:
            return grad_output * self.mask
        return grad_output


class SelfLearningNetwork:
    """
    Deep neural network for 0DTE options pattern learning.

    Features:
    - Adaptive learning from market data
    - Online learning capability
    - Pattern memory and recall
    - Continuous improvement
    """

    def __init__(self, config: Optional[LearningConfig] = None):
        self.config = config or LearningConfig()

        # Network layers (will be initialized on first forward pass)
        self.layers: List[Any] = []
        self.input_size: Optional[int] = None
        self.output_size: int = 3  # BUY, SELL, HOLD

        # Experience replay buffer
        self.memory: deque = deque(maxlen=self.config.memory_size)

        # Pattern memory
        self.pattern_memory: Dict[str, PatternMemory] = {}

        # Training statistics
        self.training_history: List[Dict] = []
        self.total_samples_seen: int = 0
        self.epochs_trained: int = 0

        # Feature statistics for normalization
        self.feature_mean: Optional[np.ndarray] = None
        self.feature_std: Optional[np.ndarray] = None

    def _build_network(self, input_size: int):
        """Build the neural network architecture."""
        self.input_size = input_size
        self.layers = []

        prev_size = input_size
        for i, hidden_size in enumerate(self.config.hidden_layers):
            self.layers.append(NeuralLayer(prev_size, hidden_size, self.config.activation))
            self.layers.append(DropoutLayer(self.config.dropout_rate))
            prev_size = hidden_size

        # Output layer with softmax
        self.layers.append(NeuralLayer(prev_size, self.output_size, "softmax"))

    def _normalize_features(self, features: np.ndarray) -> np.ndarray:
        """Normalize features using running statistics."""
        if self.feature_mean is None:
            return features

        return (features - self.feature_mean) / (self.feature_std + 1e-8)

    def _update_normalization(self, features: np.ndarray):
        """Update running normalization statistics."""
        if self.feature_mean is None:
            self.feature_mean = np.mean(features, axis=0) if len(features.shape) > 1 else features
            self.feature_std = np.std(features, axis=0) if len(features.shape) > 1 else np.ones_like(features)
        else:
            # Exponential moving average update
            alpha = self.config.adaptation_rate
            current_mean = np.mean(features, axis=0) if len(features.shape) > 1 else features
            current_std = np.std(features, axis=0) if len(features.shape) > 1 else np.ones_like(features)
            self.feature_mean = (1 - alpha) * self.feature_mean + alpha * current_mean
            self.feature_std = (1 - alpha) * self.feature_std + alpha * current_std

    def forward(self, features: np.ndarray, training: bool = True) -> np.ndarray:
        """Forward pass through the network."""
        if self.input_size is None:
            self._build_network(features.shape[-1])

        x = self._normalize_features(features)

        for layer in self.layers:
            x = layer.forward(x, training)

        return x

    def backward(self, loss_gradient: np.ndarray):
        """Backward pass for training."""
        grad = loss_gradient
        for layer in reversed(self.layers):
            grad = layer.backward(grad, self.config.learning_rate)

    def predict(self, features: np.ndarray) -> Tuple[int, float]:
        """
        Make a prediction.

        Returns:
            Tuple of (action, confidence)
            action: 0=HOLD, 1=BUY, 2=SELL
        """
        probs = self.forward(features, training=False)

        if len(probs.shape) > 1:
            probs = probs[0]

        action = np.argmax(probs)
        confidence = probs[action]

        return int(action), float(confidence)

    def add_experience(
        self,
        features: np.ndarray,
        action: int,
        reward: float,
        next_features: Optional[np.ndarray] = None,
        done: bool = False
    ):
        """Add experience to replay buffer."""
        experience = {
            'features': features,
            'action': action,
            'reward': reward,
            'next_features': next_features,
            'done': done,
            'timestamp': datetime.now()
        }
        self.memory.append(experience)
        self.total_samples_seen += 1
        self._update_normalization(features)

    def train_batch(self, batch_size: Optional[int] = None) -> float:
        """Train on a batch from experience replay."""
        batch_size = batch_size or self.config.batch_size

        if len(self.memory) < self.config.min_samples_to_train:
            return 0.0

        # Sample random batch
        indices = np.random.choice(len(self.memory), min(batch_size, len(self.memory)), replace=False)
        batch = [self.memory[i] for i in indices]

        features = np.array([exp['features'] for exp in batch])
        actions = np.array([exp['action'] for exp in batch])
        rewards = np.array([exp['reward'] for exp in batch])

        # Forward pass
        predictions = self.forward(features, training=True)

        # Create target
        targets = predictions.copy()
        for i, (action, reward) in enumerate(zip(actions, rewards)):
            # TD-like update
            targets[i, action] = np.clip(predictions[i, action] + 0.1 * reward, 0, 1)

        # Normalize targets
        targets = targets / (np.sum(targets, axis=1, keepdims=True) + 1e-8)

        # Cross-entropy loss gradient
        loss = -np.mean(np.sum(targets * np.log(predictions + 1e-8), axis=1))
        loss_gradient = predictions - targets

        # Backward pass
        self.backward(loss_gradient)

        self.epochs_trained += 1
        self.training_history.append({
            'epoch': self.epochs_trained,
            'loss': loss,
            'batch_size': len(batch),
            'timestamp': datetime.now()
        })

        return float(loss)

    def online_update(
        self,
        features: np.ndarray,
        action: int,
        reward: float
    ):
        """Perform online learning update from single experience."""
        # Forward pass
        predictions = self.forward(features.reshape(1, -1), training=True)

        # Create target
        target = predictions.copy()
        target[0, action] = np.clip(predictions[0, action] + 0.1 * reward, 0, 1)
        target = target / (np.sum(target) + 1e-8)

        # Loss gradient
        loss_gradient = predictions - target

        # Backward with smaller learning rate
        for layer in reversed(self.layers):
            loss_gradient = layer.backward(loss_gradient, self.config.online_learning_rate)


class FeatureExtractor:
    """
    Extract features from market data for the neural network.

    Creates a comprehensive feature vector from:
    - Price action
    - Greeks
    - Options flow
    - GEX
    - Volatility surface
    - Time features
    """

    def __init__(self, config: Optional[LearningConfig] = None):
        self.config = config or LearningConfig()

    def extract_features(
        self,
        price_data: pd.DataFrame,
        greeks: Optional[Dict] = None,
        flow_data: Optional[Dict] = None,
        gex_data: Optional[Dict] = None,
        vol_surface: Optional[Dict] = None,
        current_time: Optional[datetime] = None
    ) -> np.ndarray:
        """Extract features from all data sources."""
        features = []

        # Price action features
        features.extend(self._extract_price_features(price_data))

        # Greeks features
        if greeks and self.config.use_greeks:
            features.extend(self._extract_greeks_features(greeks))

        # Flow features
        if flow_data and self.config.use_flow:
            features.extend(self._extract_flow_features(flow_data))

        # GEX features
        if gex_data and self.config.use_gex:
            features.extend(self._extract_gex_features(gex_data))

        # Volatility surface features
        if vol_surface:
            features.extend(self._extract_vol_features(vol_surface))

        # Time features
        features.extend(self._extract_time_features(current_time))

        return np.array(features, dtype=np.float32)

    def _extract_price_features(self, data: pd.DataFrame) -> List[float]:
        """Extract price action features."""
        features = []

        if data.empty or 'close' not in data.columns:
            return [0.0] * 20  # Return zeros if no data

        close = data['close'].values
        high = data['high'].values if 'high' in data.columns else close
        low = data['low'].values if 'low' in data.columns else close
        volume = data['volume'].values if 'volume' in data.columns else np.ones_like(close)

        # Returns at different lookbacks
        for period in self.config.lookback_periods:
            if len(close) > period:
                ret = (close[-1] / close[-period] - 1) * 100
                features.append(ret)
            else:
                features.append(0.0)

        # Volatility at different lookbacks
        for period in self.config.lookback_periods:
            if len(close) > period:
                vol = np.std(np.diff(np.log(close[-period:]))) * np.sqrt(252) * 100
                features.append(vol)
            else:
                features.append(0.0)

        # Price relative to range
        if len(high) > 20:
            range_high = np.max(high[-20:])
            range_low = np.min(low[-20:])
            if range_high != range_low:
                features.append((close[-1] - range_low) / (range_high - range_low))
            else:
                features.append(0.5)
        else:
            features.append(0.5)

        # Volume profile
        if len(volume) > 20:
            features.append(volume[-1] / np.mean(volume[-20:]))  # Relative volume
        else:
            features.append(1.0)

        # Momentum indicators
        if len(close) > 14:
            # RSI
            deltas = np.diff(close[-15:])
            gains = np.where(deltas > 0, deltas, 0)
            losses = np.where(deltas < 0, -deltas, 0)
            avg_gain = np.mean(gains)
            avg_loss = np.mean(losses)
            if avg_loss != 0:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))
            else:
                rsi = 100
            features.append(rsi / 100)  # Normalize to 0-1
        else:
            features.append(0.5)

        # Trend strength
        if len(close) > 20:
            sma_20 = np.mean(close[-20:])
            features.append((close[-1] - sma_20) / sma_20 * 100)
        else:
            features.append(0.0)

        return features

    def _extract_greeks_features(self, greeks: Dict) -> List[float]:
        """Extract features from options Greeks."""
        return [
            greeks.get('delta', 0.0),
            greeks.get('gamma', 0.0) * 100,  # Scale up gamma
            greeks.get('theta', 0.0) * 10,  # Scale theta
            greeks.get('vega', 0.0),
            greeks.get('charm', 0.0) * 100,
            greeks.get('vanna', 0.0),
            greeks.get('volga', 0.0),
        ]

    def _extract_flow_features(self, flow_data: Dict) -> List[float]:
        """Extract features from options flow."""
        total_call = flow_data.get('total_call_volume', 0) + 1
        total_put = flow_data.get('total_put_volume', 0) + 1

        return [
            np.log(flow_data.get('put_call_ratio', 1.0) + 0.01),
            flow_data.get('call_premium', 0) / 1e6,  # Scale to millions
            flow_data.get('put_premium', 0) / 1e6,
            len(flow_data.get('sweep_orders', [])) / 10,  # Normalize
            len(flow_data.get('block_trades', [])) / 5,
            1.0 if flow_data.get('institutional_bias') == 'bullish' else (
                -1.0 if flow_data.get('institutional_bias') == 'bearish' else 0.0
            ),
        ]

    def _extract_gex_features(self, gex_data: Dict) -> List[float]:
        """Extract features from GEX data."""
        return [
            gex_data.get('net_gex', 0) / 1e10,  # Scale down
            1.0 if gex_data.get('dealer_position') == 'long_gamma' else (
                -1.0 if gex_data.get('dealer_position') == 'short_gamma' else 0.0
            ),
            len(gex_data.get('pin_risk_strikes', [])) / 5,
        ]

    def _extract_vol_features(self, vol_surface: Dict) -> List[float]:
        """Extract features from volatility surface."""
        return [
            vol_surface.get('atm_iv', 20) / 100,  # Normalize IV
            vol_surface.get('iv_skew', 0),
            vol_surface.get('iv_percentile', 50) / 100,
            vol_surface.get('rv_vs_iv', 0) / 10,
            vol_surface.get('vix_level', 20) / 100,
        ]

    def _extract_time_features(self, current_time: Optional[datetime] = None) -> List[float]:
        """Extract time-based features."""
        current_time = current_time or datetime.now()

        # Time of day (normalized to trading hours)
        hour = current_time.hour
        minute = current_time.minute
        market_minutes = (hour - 9) * 60 + minute - 30  # Minutes since market open
        market_minutes = max(0, min(390, market_minutes))  # 0-390 minutes

        # Day of week
        day_of_week = current_time.weekday()

        # Time periods
        is_open_drive = 1.0 if 0 <= market_minutes < 30 else 0.0
        is_morning = 1.0 if 30 <= market_minutes < 120 else 0.0
        is_lunch = 1.0 if 120 <= market_minutes < 210 else 0.0
        is_afternoon = 1.0 if 210 <= market_minutes < 330 else 0.0
        is_power_hour = 1.0 if market_minutes >= 330 else 0.0

        # Minutes to close
        minutes_to_close = max(0, 390 - market_minutes)

        return [
            market_minutes / 390,  # Normalized time
            minutes_to_close / 390,  # Time remaining
            day_of_week / 4,  # Monday=0, Friday=4
            is_open_drive,
            is_morning,
            is_lunch,
            is_afternoon,
            is_power_hour,
        ]


class PatternRecognizer:
    """
    Recognizes and learns market patterns for 0DTE trading.

    Uses similarity matching and clustering to identify
    profitable patterns from historical data.
    """

    def __init__(self, config: Optional[LearningConfig] = None):
        self.config = config or LearningConfig()
        self.patterns: Dict[str, PatternMemory] = {}

    def _compute_pattern_hash(self, features: np.ndarray) -> str:
        """Compute a hash for pattern matching."""
        # Discretize features for hashing
        discretized = np.round(features * 10) / 10
        return hashlib.md5(discretized.tobytes()).hexdigest()[:16]

    def _compute_similarity(self, features1: np.ndarray, features2: np.ndarray) -> float:
        """Compute cosine similarity between feature vectors."""
        norm1 = np.linalg.norm(features1)
        norm2 = np.linalg.norm(features2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(np.dot(features1, features2) / (norm1 * norm2))

    def find_similar_patterns(
        self,
        features: np.ndarray,
        top_k: int = 5
    ) -> List[Tuple[PatternMemory, float]]:
        """Find most similar patterns from memory."""
        similarities = []

        for pattern_id, pattern in self.patterns.items():
            sim = self._compute_similarity(features, pattern.features)
            if sim >= self.config.pattern_similarity_threshold:
                similarities.append((pattern, sim))

        # Sort by similarity
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:top_k]

    def add_pattern(
        self,
        features: np.ndarray,
        pattern_type: PatternType,
        outcome: str,
        profit_pct: float,
        context: Optional[Dict] = None
    ):
        """Add or update a pattern in memory."""
        pattern_hash = self._compute_pattern_hash(features)

        if pattern_hash in self.patterns:
            # Update existing pattern
            pattern = self.patterns[pattern_hash]
            pattern.occurrences += 1
            pattern.last_seen = datetime.now()

            # Update confidence based on outcome
            if outcome == 'win':
                pattern.confidence = min(0.99, pattern.confidence + 0.05)
            elif outcome == 'loss':
                pattern.confidence = max(0.01, pattern.confidence - 0.05)

            # Exponential moving average of profit
            pattern.profit_pct = 0.8 * pattern.profit_pct + 0.2 * profit_pct
        else:
            # Create new pattern
            self.patterns[pattern_hash] = PatternMemory(
                pattern_id=pattern_hash,
                pattern_type=pattern_type,
                features=features.copy(),
                outcome=outcome,
                profit_pct=profit_pct,
                confidence=0.5,
                context=context or {}
            )

    def get_pattern_prediction(
        self,
        features: np.ndarray
    ) -> Tuple[Optional[PatternType], float, float]:
        """
        Get prediction based on pattern matching.

        Returns:
            Tuple of (pattern_type, confidence, expected_profit_pct)
        """
        similar = self.find_similar_patterns(features)

        if not similar:
            return None, 0.0, 0.0

        # Weighted average of predictions
        total_weight = 0.0
        weighted_confidence = 0.0
        weighted_profit = 0.0
        pattern_votes: Dict[PatternType, float] = {}

        for pattern, similarity in similar:
            weight = similarity * pattern.confidence
            total_weight += weight
            weighted_confidence += pattern.confidence * weight
            weighted_profit += pattern.profit_pct * weight

            if pattern.pattern_type not in pattern_votes:
                pattern_votes[pattern.pattern_type] = 0
            pattern_votes[pattern.pattern_type] += weight

        if total_weight == 0:
            return None, 0.0, 0.0

        # Most voted pattern type
        best_pattern = max(pattern_votes.items(), key=lambda x: x[1])[0]

        return (
            best_pattern,
            weighted_confidence / total_weight,
            weighted_profit / total_weight
        )

    def get_pattern_stats(self) -> Dict:
        """Get statistics about learned patterns."""
        if not self.patterns:
            return {'total_patterns': 0}

        wins = sum(1 for p in self.patterns.values() if p.outcome == 'win')
        losses = sum(1 for p in self.patterns.values() if p.outcome == 'loss')

        pattern_type_counts = {}
        for p in self.patterns.values():
            pt = p.pattern_type.value
            pattern_type_counts[pt] = pattern_type_counts.get(pt, 0) + 1

        return {
            'total_patterns': len(self.patterns),
            'wins': wins,
            'losses': losses,
            'win_rate': wins / (wins + losses) if (wins + losses) > 0 else 0,
            'avg_confidence': np.mean([p.confidence for p in self.patterns.values()]),
            'avg_profit_pct': np.mean([p.profit_pct for p in self.patterns.values()]),
            'pattern_types': pattern_type_counts,
            'total_occurrences': sum(p.occurrences for p in self.patterns.values())
        }


class SelfLearningSystem:
    """
    Complete self-learning system for 0DTE options trading.

    Combines:
    - Neural network for predictions
    - Feature extraction
    - Pattern recognition
    - Online learning
    - Continuous improvement
    """

    def __init__(self, config: Optional[LearningConfig] = None):
        self.config = config or LearningConfig()

        # Components
        self.network = SelfLearningNetwork(self.config)
        self.feature_extractor = FeatureExtractor(self.config)
        self.pattern_recognizer = PatternRecognizer(self.config)

        # State
        self.is_trained = False
        self.last_prediction: Optional[Dict] = None

        # Performance tracking
        self.predictions_made: int = 0
        self.correct_predictions: int = 0

    def extract_features(
        self,
        price_data: pd.DataFrame,
        greeks: Optional[Dict] = None,
        flow_data: Optional[Dict] = None,
        gex_data: Optional[Dict] = None,
        vol_surface: Optional[Dict] = None
    ) -> np.ndarray:
        """Extract features from all data sources."""
        return self.feature_extractor.extract_features(
            price_data=price_data,
            greeks=greeks,
            flow_data=flow_data,
            gex_data=gex_data,
            vol_surface=vol_surface
        )

    def predict(
        self,
        features: np.ndarray,
        use_patterns: bool = True
    ) -> Dict[str, Any]:
        """
        Make a prediction using all available methods.

        Returns:
            Dict with prediction details
        """
        # Neural network prediction
        nn_action, nn_confidence = self.network.predict(features)

        # Pattern matching prediction
        pattern_type, pattern_conf, pattern_profit = None, 0.0, 0.0
        if use_patterns:
            pattern_type, pattern_conf, pattern_profit = self.pattern_recognizer.get_pattern_prediction(features)

        # Combine predictions
        combined_confidence = nn_confidence
        if pattern_conf > 0:
            combined_confidence = 0.6 * nn_confidence + 0.4 * pattern_conf

        # Map action to direction
        action_map = {0: 'HOLD', 1: 'BUY', 2: 'SELL'}
        direction = action_map.get(nn_action, 'HOLD')

        prediction = {
            'direction': direction,
            'action': nn_action,
            'confidence': float(combined_confidence),
            'nn_confidence': float(nn_confidence),
            'pattern_type': pattern_type.value if pattern_type else None,
            'pattern_confidence': float(pattern_conf),
            'expected_profit_pct': float(pattern_profit),
            'timestamp': datetime.now(),
            'features_used': len(features)
        }

        self.last_prediction = prediction
        self.predictions_made += 1

        return prediction

    def learn_from_outcome(
        self,
        features: np.ndarray,
        action: int,
        profit_pct: float,
        pattern_type: Optional[PatternType] = None
    ):
        """Learn from trade outcome."""
        # Determine outcome
        if profit_pct > 1.0:
            outcome = 'win'
            reward = 1.0
        elif profit_pct < -1.0:
            outcome = 'loss'
            reward = -1.0
        else:
            outcome = 'scratch'
            reward = 0.0

        # Update neural network
        self.network.add_experience(features, action, reward)
        self.network.online_update(features, action, reward)

        # Update pattern memory
        if pattern_type:
            self.pattern_recognizer.add_pattern(
                features=features,
                pattern_type=pattern_type,
                outcome=outcome,
                profit_pct=profit_pct
            )

        # Track accuracy
        if self.last_prediction:
            expected_profitable = self.last_prediction['direction'] != 'HOLD'
            actually_profitable = profit_pct > 0
            if expected_profitable == actually_profitable:
                self.correct_predictions += 1

    def train(self, epochs: int = 10) -> List[float]:
        """Train the neural network on accumulated experience."""
        losses = []
        for _ in range(epochs):
            loss = self.network.train_batch()
            losses.append(loss)

        self.is_trained = True
        return losses

    def get_accuracy(self) -> float:
        """Get prediction accuracy."""
        if self.predictions_made == 0:
            return 0.0
        return self.correct_predictions / self.predictions_made

    def get_stats(self) -> Dict:
        """Get system statistics."""
        return {
            'is_trained': self.is_trained,
            'predictions_made': self.predictions_made,
            'correct_predictions': self.correct_predictions,
            'accuracy': self.get_accuracy(),
            'samples_in_memory': len(self.network.memory),
            'epochs_trained': self.network.epochs_trained,
            'pattern_stats': self.pattern_recognizer.get_pattern_stats()
        }

    def save(self, filepath: str):
        """Save the learning system state."""
        state = {
            'config': self.config,
            'network_weights': [(l.weights.tolist(), l.bias.tolist()) if hasattr(l, 'weights') else None
                               for l in self.network.layers],
            'feature_mean': self.network.feature_mean.tolist() if self.network.feature_mean is not None else None,
            'feature_std': self.network.feature_std.tolist() if self.network.feature_std is not None else None,
            'patterns': {k: v.to_dict() for k, v in self.pattern_recognizer.patterns.items()},
            'stats': self.get_stats()
        }
        with open(filepath, 'w') as f:
            json.dump(state, f, indent=2, default=str)
        print(f"Learning system saved to {filepath}")

    def load(self, filepath: str):
        """Load the learning system state."""
        with open(filepath, 'r') as f:
            state = json.load(f)

        if state.get('feature_mean'):
            self.network.feature_mean = np.array(state['feature_mean'])
            self.network.feature_std = np.array(state['feature_std'])

        # Rebuild network and load weights
        if state.get('network_weights'):
            for i, weights in enumerate(state['network_weights']):
                if weights and i < len(self.network.layers):
                    layer = self.network.layers[i]
                    if hasattr(layer, 'weights'):
                        layer.weights = np.array(weights[0])
                        layer.bias = np.array(weights[1])

        print(f"Learning system loaded from {filepath}")


# Convenience functions
def create_self_learning_system(config: Optional[Dict] = None) -> SelfLearningSystem:
    """Create a configured self-learning system."""
    if config:
        learning_config = LearningConfig(**config)
    else:
        learning_config = LearningConfig()
    return SelfLearningSystem(learning_config)
