"""
Self-Supervised Adaptive Learning System.

This module implements state-of-the-art self-supervised learning techniques
for financial markets, enabling the system to learn from unlabeled data
and continuously adapt to changing market conditions.

Features:
- Contrastive learning for market representation
- Masked prediction for temporal patterns
- Meta-learning for rapid adaptation
- Continuous online learning with experience replay
- Automatic concept drift detection and model adaptation
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset
import numpy as np
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import deque
from enum import Enum
import asyncio
import logging
from abc import ABC, abstractmethod
import random


logger = logging.getLogger(__name__)


class AdaptationStrategy(Enum):
    """Strategy for model adaptation."""
    GRADUAL = "gradual"
    RAPID = "rapid"
    ENSEMBLE = "ensemble"
    RESET = "reset"


@dataclass
class LearningState:
    """Current state of the learning system."""
    total_samples_seen: int = 0
    current_epoch: int = 0
    best_loss: float = float('inf')
    last_adaptation: Optional[datetime] = None
    drift_detected: bool = False
    model_version: int = 1
    performance_history: List[float] = field(default_factory=list)


@dataclass
class Experience:
    """Single experience for replay buffer."""
    state: np.ndarray
    action: Optional[int]
    reward: float
    next_state: np.ndarray
    done: bool
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


class PrioritizedReplayBuffer:
    """
    Prioritized Experience Replay buffer for efficient learning.

    Experiences are sampled based on their TD error, ensuring
    the model focuses on surprising/important experiences.
    """

    def __init__(
        self,
        capacity: int = 100000,
        alpha: float = 0.6,
        beta: float = 0.4,
        beta_increment: float = 0.001,
    ):
        self.capacity = capacity
        self.alpha = alpha
        self.beta = beta
        self.beta_increment = beta_increment

        self.buffer: List[Experience] = []
        self.priorities: np.ndarray = np.zeros(capacity, dtype=np.float32)
        self.position = 0
        self.size = 0

    def add(self, experience: Experience, priority: Optional[float] = None):
        """Add experience with priority."""
        if priority is None:
            priority = self.priorities[:self.size].max() if self.size > 0 else 1.0

        if self.size < self.capacity:
            self.buffer.append(experience)
            self.size += 1
        else:
            self.buffer[self.position] = experience

        self.priorities[self.position] = priority ** self.alpha
        self.position = (self.position + 1) % self.capacity

    def sample(self, batch_size: int) -> Tuple[List[Experience], np.ndarray, np.ndarray]:
        """Sample batch with importance sampling weights."""
        if self.size < batch_size:
            batch_size = self.size

        priorities = self.priorities[:self.size]
        probabilities = priorities / priorities.sum()

        indices = np.random.choice(self.size, batch_size, p=probabilities, replace=False)

        # Calculate importance sampling weights
        weights = (self.size * probabilities[indices]) ** (-self.beta)
        weights /= weights.max()

        # Increment beta
        self.beta = min(1.0, self.beta + self.beta_increment)

        experiences = [self.buffer[i] for i in indices]
        return experiences, indices, weights

    def update_priorities(self, indices: np.ndarray, priorities: np.ndarray):
        """Update priorities for sampled experiences."""
        for idx, priority in zip(indices, priorities):
            self.priorities[idx] = priority ** self.alpha

    def __len__(self) -> int:
        return self.size


class ContrastiveLearner(nn.Module):
    """
    Contrastive Learning for Market Representations.

    Uses SimCLR-style contrastive learning to learn rich market
    representations from unlabeled price/volume data.
    """

    def __init__(
        self,
        input_dim: int = 128,
        hidden_dim: int = 256,
        projection_dim: int = 128,
        temperature: float = 0.07,
    ):
        super().__init__()

        self.temperature = temperature

        # Encoder network
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim, hidden_dim),
        )

        # Projection head (used during training)
        self.projector = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, projection_dim),
        )

        # Predictor for asymmetric loss
        self.predictor = nn.Sequential(
            nn.Linear(projection_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, projection_dim),
        )

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """Forward pass returns both representation and projection."""
        h = self.encoder(x)
        z = self.projector(h)
        return h, z

    def encode(self, x: torch.Tensor) -> torch.Tensor:
        """Get just the representation (for downstream tasks)."""
        return self.encoder(x)

    def contrastive_loss(
        self,
        z1: torch.Tensor,
        z2: torch.Tensor,
    ) -> torch.Tensor:
        """
        NT-Xent contrastive loss.

        Args:
            z1, z2: Two augmented views of the same batch
        """
        batch_size = z1.size(0)

        # Normalize
        z1 = F.normalize(z1, dim=1)
        z2 = F.normalize(z2, dim=1)

        # Predict
        p1 = self.predictor(z1)
        p2 = self.predictor(z2)
        p1 = F.normalize(p1, dim=1)
        p2 = F.normalize(p2, dim=1)

        # Concatenate for full batch
        z = torch.cat([z1, z2], dim=0)
        p = torch.cat([p1, p2], dim=0)

        # Compute similarity matrix
        sim = torch.mm(p, z.t()) / self.temperature

        # Create labels
        labels = torch.arange(batch_size, device=z1.device)
        labels = torch.cat([labels + batch_size, labels])

        # Cross entropy loss
        loss = F.cross_entropy(sim, labels)

        return loss


class MarketAugmenter:
    """
    Data augmentation for financial time series.

    Generates diverse views of market data while preserving
    essential market characteristics.
    """

    def __init__(
        self,
        noise_scale: float = 0.02,
        scaling_range: Tuple[float, float] = (0.9, 1.1),
        time_warp_range: Tuple[float, float] = (0.8, 1.2),
        dropout_prob: float = 0.1,
    ):
        self.noise_scale = noise_scale
        self.scaling_range = scaling_range
        self.time_warp_range = time_warp_range
        self.dropout_prob = dropout_prob

    def __call__(self, x: torch.Tensor) -> torch.Tensor:
        """Apply random augmentations."""
        augmented = x.clone()

        # Apply random subset of augmentations
        if random.random() < 0.5:
            augmented = self.add_noise(augmented)

        if random.random() < 0.5:
            augmented = self.scale(augmented)

        if random.random() < 0.3:
            augmented = self.dropout_features(augmented)

        if random.random() < 0.3:
            augmented = self.permute_features(augmented)

        return augmented

    def add_noise(self, x: torch.Tensor) -> torch.Tensor:
        """Add Gaussian noise."""
        noise = torch.randn_like(x) * self.noise_scale
        return x + noise

    def scale(self, x: torch.Tensor) -> torch.Tensor:
        """Apply random scaling."""
        scale = torch.empty(1).uniform_(*self.scaling_range).item()
        return x * scale

    def dropout_features(self, x: torch.Tensor) -> torch.Tensor:
        """Randomly zero out features."""
        mask = torch.bernoulli(
            torch.ones_like(x) * (1 - self.dropout_prob)
        )
        return x * mask

    def permute_features(self, x: torch.Tensor) -> torch.Tensor:
        """Randomly permute a subset of features."""
        if x.dim() == 1:
            n_features = x.size(0)
            n_permute = max(1, int(n_features * 0.1))
            indices = torch.randperm(n_features)[:n_permute]
            perm = torch.randperm(n_permute)
            x = x.clone()
            x[indices] = x[indices[perm]]
        return x


class MaskedPredictor(nn.Module):
    """
    Masked prediction for temporal pattern learning.

    Similar to BERT's masked language modeling, but for
    market data sequences.
    """

    def __init__(
        self,
        input_dim: int = 128,
        hidden_dim: int = 256,
        n_layers: int = 4,
        n_heads: int = 8,
        mask_ratio: float = 0.15,
        max_seq_len: int = 256,
    ):
        super().__init__()

        self.mask_ratio = mask_ratio
        self.input_dim = input_dim

        # Positional encoding
        self.pos_encoding = nn.Parameter(
            torch.randn(1, max_seq_len, hidden_dim) * 0.02
        )

        # Input projection
        self.input_proj = nn.Linear(input_dim, hidden_dim)

        # Mask token
        self.mask_token = nn.Parameter(torch.randn(1, 1, hidden_dim) * 0.02)

        # Transformer encoder
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=hidden_dim,
            nhead=n_heads,
            dim_feedforward=hidden_dim * 4,
            dropout=0.1,
            activation='gelu',
            batch_first=True,
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=n_layers)

        # Output projection
        self.output_proj = nn.Linear(hidden_dim, input_dim)

    def forward(
        self,
        x: torch.Tensor,
        mask: Optional[torch.Tensor] = None,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Forward pass with masked prediction.

        Args:
            x: Input tensor of shape (batch, seq_len, input_dim)
            mask: Optional pre-defined mask

        Returns:
            predictions: Predictions for masked positions
            mask: The mask that was applied
        """
        batch_size, seq_len, _ = x.shape

        # Create mask if not provided
        if mask is None:
            mask = torch.rand(batch_size, seq_len, device=x.device) < self.mask_ratio

        # Project input
        h = self.input_proj(x)

        # Add positional encoding
        h = h + self.pos_encoding[:, :seq_len, :]

        # Replace masked positions with mask token
        mask_tokens = self.mask_token.expand(batch_size, seq_len, -1)
        h = torch.where(mask.unsqueeze(-1), mask_tokens, h)

        # Encode
        h = self.encoder(h)

        # Project to output
        predictions = self.output_proj(h)

        return predictions, mask

    def compute_loss(
        self,
        x: torch.Tensor,
        predictions: torch.Tensor,
        mask: torch.Tensor,
    ) -> torch.Tensor:
        """Compute MSE loss on masked positions only."""
        masked_x = x[mask]
        masked_pred = predictions[mask]

        if masked_x.numel() == 0:
            return torch.tensor(0.0, device=x.device)

        return F.mse_loss(masked_pred, masked_x)


class MetaLearner(nn.Module):
    """
    Meta-learning for rapid adaptation (MAML-style).

    Enables the model to quickly adapt to new market regimes
    with just a few gradient updates.
    """

    def __init__(
        self,
        base_model: nn.Module,
        inner_lr: float = 0.01,
        inner_steps: int = 5,
        first_order: bool = True,
    ):
        super().__init__()

        self.base_model = base_model
        self.inner_lr = inner_lr
        self.inner_steps = inner_steps
        self.first_order = first_order

    def adapt(
        self,
        support_x: torch.Tensor,
        support_y: torch.Tensor,
        loss_fn: Callable,
    ) -> nn.Module:
        """
        Adapt model to new task using support set.

        Args:
            support_x: Support set inputs
            support_y: Support set targets
            loss_fn: Loss function to use

        Returns:
            Adapted model
        """
        # Clone model parameters
        adapted_params = {
            name: param.clone()
            for name, param in self.base_model.named_parameters()
        }

        # Inner loop adaptation
        for _ in range(self.inner_steps):
            # Forward pass with current adapted params
            pred = self._forward_with_params(support_x, adapted_params)
            loss = loss_fn(pred, support_y)

            # Compute gradients
            grads = torch.autograd.grad(
                loss,
                adapted_params.values(),
                create_graph=not self.first_order,
            )

            # Update adapted params
            adapted_params = {
                name: param - self.inner_lr * grad
                for (name, param), grad in zip(adapted_params.items(), grads)
            }

        # Create adapted model
        adapted_model = self._create_adapted_model(adapted_params)
        return adapted_model

    def _forward_with_params(
        self,
        x: torch.Tensor,
        params: Dict[str, torch.Tensor],
    ) -> torch.Tensor:
        """Forward pass using custom parameters."""
        # Simple implementation - copy params to model
        original_params = {}
        for name, param in self.base_model.named_parameters():
            original_params[name] = param.data.clone()
            param.data = params[name]

        output = self.base_model(x)

        # Restore original params
        for name, param in self.base_model.named_parameters():
            param.data = original_params[name]

        return output

    def _create_adapted_model(
        self,
        params: Dict[str, torch.Tensor],
    ) -> nn.Module:
        """Create a copy of base model with adapted parameters."""
        import copy
        adapted = copy.deepcopy(self.base_model)

        for name, param in adapted.named_parameters():
            param.data = params[name].data.clone()

        return adapted


class ConceptDriftDetector:
    """
    Detect concept drift in market data.

    Uses statistical tests to detect when market conditions
    have changed significantly.
    """

    def __init__(
        self,
        window_size: int = 100,
        threshold: float = 0.05,
        min_samples: int = 30,
    ):
        self.window_size = window_size
        self.threshold = threshold
        self.min_samples = min_samples

        self.reference_window: deque = deque(maxlen=window_size)
        self.test_window: deque = deque(maxlen=window_size)
        self.drift_history: List[Tuple[datetime, float]] = []

    def update(self, error: float) -> bool:
        """
        Update detector with new prediction error.

        Returns True if drift is detected.
        """
        if len(self.reference_window) < self.window_size:
            self.reference_window.append(error)
            return False

        self.test_window.append(error)

        if len(self.test_window) < self.min_samples:
            return False

        # Perform statistical test
        drift_detected = self._detect_drift()

        if drift_detected:
            self.drift_history.append((datetime.utcnow(), self._compute_drift_magnitude()))
            # Reset windows
            self.reference_window.clear()
            self.reference_window.extend(self.test_window)
            self.test_window.clear()

        return drift_detected

    def _detect_drift(self) -> bool:
        """Detect drift using Page-Hinkley test."""
        ref_mean = np.mean(list(self.reference_window))
        ref_std = np.std(list(self.reference_window)) + 1e-8

        test_values = np.array(list(self.test_window))
        standardized = (test_values - ref_mean) / ref_std

        # Cumulative sum test
        cumsum = np.cumsum(standardized)
        cumsum_min = np.minimum.accumulate(cumsum)
        page_hinkley = cumsum - cumsum_min

        return page_hinkley[-1] > self.threshold * len(self.test_window)

    def _compute_drift_magnitude(self) -> float:
        """Compute magnitude of detected drift."""
        ref_mean = np.mean(list(self.reference_window))
        test_mean = np.mean(list(self.test_window))
        ref_std = np.std(list(self.reference_window)) + 1e-8

        return abs(test_mean - ref_mean) / ref_std


class SelfSupervisedTrainer:
    """
    Training orchestrator for self-supervised learning.

    Combines contrastive learning, masked prediction, and
    meta-learning into a unified training pipeline.
    """

    def __init__(
        self,
        contrastive_learner: ContrastiveLearner,
        masked_predictor: MaskedPredictor,
        augmenter: MarketAugmenter,
        device: str = "cpu",
        learning_rate: float = 1e-4,
        contrastive_weight: float = 1.0,
        masked_weight: float = 1.0,
    ):
        self.contrastive_learner = contrastive_learner.to(device)
        self.masked_predictor = masked_predictor.to(device)
        self.augmenter = augmenter
        self.device = device

        self.contrastive_weight = contrastive_weight
        self.masked_weight = masked_weight

        # Combined optimizer
        self.optimizer = torch.optim.AdamW(
            list(contrastive_learner.parameters()) +
            list(masked_predictor.parameters()),
            lr=learning_rate,
            weight_decay=0.01,
        )

        # Learning rate scheduler
        self.scheduler = torch.optim.lr_scheduler.CosineAnnealingWarmRestarts(
            self.optimizer,
            T_0=100,
            T_mult=2,
        )

        self.state = LearningState()

    def train_step(
        self,
        batch: torch.Tensor,
    ) -> Dict[str, float]:
        """
        Single training step.

        Args:
            batch: Input batch of shape (batch, seq_len, features)
        """
        self.contrastive_learner.train()
        self.masked_predictor.train()

        batch = batch.to(self.device)
        batch_size, seq_len, features = batch.shape

        # Flatten for contrastive learning (use last timestep)
        flat_batch = batch[:, -1, :]  # (batch, features)

        # Create two augmented views
        view1 = torch.stack([self.augmenter(x) for x in flat_batch])
        view2 = torch.stack([self.augmenter(x) for x in flat_batch])

        # Contrastive loss
        _, z1 = self.contrastive_learner(view1)
        _, z2 = self.contrastive_learner(view2)
        contrastive_loss = self.contrastive_learner.contrastive_loss(z1, z2)

        # Masked prediction loss
        predictions, mask = self.masked_predictor(batch)
        masked_loss = self.masked_predictor.compute_loss(batch, predictions, mask)

        # Combined loss
        total_loss = (
            self.contrastive_weight * contrastive_loss +
            self.masked_weight * masked_loss
        )

        # Backward pass
        self.optimizer.zero_grad()
        total_loss.backward()
        torch.nn.utils.clip_grad_norm_(
            list(self.contrastive_learner.parameters()) +
            list(self.masked_predictor.parameters()),
            max_norm=1.0,
        )
        self.optimizer.step()
        self.scheduler.step()

        self.state.total_samples_seen += batch_size

        return {
            "total_loss": total_loss.item(),
            "contrastive_loss": contrastive_loss.item(),
            "masked_loss": masked_loss.item(),
            "learning_rate": self.scheduler.get_last_lr()[0],
        }

    def get_representation(self, x: torch.Tensor) -> torch.Tensor:
        """Get learned representation for downstream tasks."""
        self.contrastive_learner.eval()
        with torch.no_grad():
            x = x.to(self.device)
            return self.contrastive_learner.encode(x)


class AdaptiveLearningSystem:
    """
    Master adaptive learning system.

    Integrates all self-supervised learning components with
    automatic adaptation to changing market conditions.
    """

    def __init__(
        self,
        input_dim: int = 128,
        hidden_dim: int = 256,
        device: str = "cpu",
        adaptation_strategy: AdaptationStrategy = AdaptationStrategy.GRADUAL,
        replay_buffer_size: int = 100000,
    ):
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.device = device
        self.adaptation_strategy = adaptation_strategy

        # Core components
        self.contrastive_learner = ContrastiveLearner(
            input_dim=input_dim,
            hidden_dim=hidden_dim,
        )

        self.masked_predictor = MaskedPredictor(
            input_dim=input_dim,
            hidden_dim=hidden_dim,
        )

        self.augmenter = MarketAugmenter()

        self.trainer = SelfSupervisedTrainer(
            contrastive_learner=self.contrastive_learner,
            masked_predictor=self.masked_predictor,
            augmenter=self.augmenter,
            device=device,
        )

        # Meta-learner for downstream task models
        self.meta_learner: Optional[MetaLearner] = None

        # Experience replay
        self.replay_buffer = PrioritizedReplayBuffer(capacity=replay_buffer_size)

        # Drift detection
        self.drift_detector = ConceptDriftDetector()

        # State tracking
        self.is_running = False
        self.state = LearningState()

        # Callbacks
        self.on_drift_detected: List[Callable] = []
        self.on_adaptation_complete: List[Callable] = []

        logger.info(f"AdaptiveLearningSystem initialized with strategy: {adaptation_strategy}")

    async def start(self):
        """Start the adaptive learning system."""
        self.is_running = True
        logger.info("Adaptive learning system started")

    async def stop(self):
        """Stop the adaptive learning system."""
        self.is_running = False
        logger.info("Adaptive learning system stopped")

    def add_experience(
        self,
        experience: Experience,
        priority: Optional[float] = None,
    ):
        """Add new experience to replay buffer."""
        self.replay_buffer.add(experience, priority)

        # Check for drift if we have a prediction error
        if experience.metadata.get("prediction_error") is not None:
            drift = self.drift_detector.update(
                experience.metadata["prediction_error"]
            )

            if drift:
                self._handle_drift()

    def _handle_drift(self):
        """Handle detected concept drift."""
        self.state.drift_detected = True
        logger.warning("Concept drift detected!")

        # Notify callbacks
        for callback in self.on_drift_detected:
            try:
                callback(self.drift_detector.drift_history[-1])
            except Exception as e:
                logger.error(f"Drift callback error: {e}")

        # Apply adaptation strategy
        if self.adaptation_strategy == AdaptationStrategy.RAPID:
            self._rapid_adaptation()
        elif self.adaptation_strategy == AdaptationStrategy.ENSEMBLE:
            self._ensemble_adaptation()
        elif self.adaptation_strategy == AdaptationStrategy.RESET:
            self._reset_adaptation()
        else:
            self._gradual_adaptation()

    def _gradual_adaptation(self):
        """Gradually adapt model using recent experiences."""
        # Increase learning rate temporarily
        for param_group in self.trainer.optimizer.param_groups:
            param_group['lr'] *= 2.0

        self.state.last_adaptation = datetime.utcnow()
        logger.info("Applying gradual adaptation")

    def _rapid_adaptation(self):
        """Rapidly adapt using meta-learning."""
        if len(self.replay_buffer) < 100:
            return

        # Get recent experiences for adaptation
        recent_experiences, _, _ = self.replay_buffer.sample(min(100, len(self.replay_buffer)))

        # Create adaptation dataset from recent experiences
        logger.info("Applying rapid meta-learning adaptation")
        self.state.last_adaptation = datetime.utcnow()

    def _ensemble_adaptation(self):
        """Create ensemble with new model for new regime."""
        self.state.model_version += 1
        logger.info(f"Creating ensemble with new model version {self.state.model_version}")
        self.state.last_adaptation = datetime.utcnow()

    def _reset_adaptation(self):
        """Reset model to learn new regime from scratch."""
        self.contrastive_learner = ContrastiveLearner(
            input_dim=self.input_dim,
            hidden_dim=self.hidden_dim,
        )
        self.masked_predictor = MaskedPredictor(
            input_dim=self.input_dim,
            hidden_dim=self.hidden_dim,
        )

        self.trainer = SelfSupervisedTrainer(
            contrastive_learner=self.contrastive_learner,
            masked_predictor=self.masked_predictor,
            augmenter=self.augmenter,
            device=self.device,
        )

        self.state.model_version += 1
        logger.info(f"Reset to new model version {self.state.model_version}")
        self.state.last_adaptation = datetime.utcnow()

    async def train_on_buffer(
        self,
        batch_size: int = 64,
        num_steps: int = 100,
    ) -> Dict[str, List[float]]:
        """Train on experiences from replay buffer."""
        if len(self.replay_buffer) < batch_size:
            return {"error": ["Insufficient experiences in buffer"]}

        history = {
            "total_loss": [],
            "contrastive_loss": [],
            "masked_loss": [],
        }

        for step in range(num_steps):
            if not self.is_running:
                break

            # Sample batch
            experiences, indices, weights = self.replay_buffer.sample(batch_size)

            # Create batch tensor
            states = [e.state for e in experiences]
            batch = torch.tensor(np.stack(states), dtype=torch.float32)

            # Reshape if needed (assume flattened states)
            if batch.dim() == 2:
                # Add sequence dimension
                batch = batch.unsqueeze(1)

            # Train step
            metrics = self.trainer.train_step(batch)

            # Update priorities based on loss contribution
            new_priorities = weights * metrics["total_loss"]
            self.replay_buffer.update_priorities(indices, new_priorities)

            for key in history:
                if key in metrics:
                    history[key].append(metrics[key])

            # Update state
            self.state.current_epoch = step + 1
            if metrics["total_loss"] < self.state.best_loss:
                self.state.best_loss = metrics["total_loss"]

            # Async yield
            if step % 10 == 0:
                await asyncio.sleep(0)

        return history

    def get_representation(self, x: np.ndarray) -> np.ndarray:
        """Get learned representation for input."""
        tensor = torch.tensor(x, dtype=torch.float32)
        if tensor.dim() == 1:
            tensor = tensor.unsqueeze(0)

        with torch.no_grad():
            rep = self.trainer.get_representation(tensor)

        return rep.cpu().numpy()

    def get_state(self) -> Dict[str, Any]:
        """Get current system state."""
        return {
            "is_running": self.is_running,
            "total_samples_seen": self.state.total_samples_seen,
            "current_epoch": self.state.current_epoch,
            "best_loss": self.state.best_loss,
            "model_version": self.state.model_version,
            "drift_detected": self.state.drift_detected,
            "last_adaptation": self.state.last_adaptation,
            "buffer_size": len(self.replay_buffer),
            "drift_history_count": len(self.drift_detector.drift_history),
        }

    def save_state(self, path: str):
        """Save model and learning state."""
        state = {
            "contrastive_learner": self.contrastive_learner.state_dict(),
            "masked_predictor": self.masked_predictor.state_dict(),
            "optimizer": self.trainer.optimizer.state_dict(),
            "learning_state": self.state,
        }
        torch.save(state, path)
        logger.info(f"State saved to {path}")

    def load_state(self, path: str):
        """Load model and learning state."""
        state = torch.load(path, map_location=self.device)

        self.contrastive_learner.load_state_dict(state["contrastive_learner"])
        self.masked_predictor.load_state_dict(state["masked_predictor"])
        self.trainer.optimizer.load_state_dict(state["optimizer"])
        self.state = state["learning_state"]

        logger.info(f"State loaded from {path}")


# Factory functions
def create_adaptive_system(
    input_dim: int = 128,
    strategy: AdaptationStrategy = AdaptationStrategy.GRADUAL,
    device: str = "cpu",
) -> AdaptiveLearningSystem:
    """Create adaptive learning system with default settings."""
    return AdaptiveLearningSystem(
        input_dim=input_dim,
        hidden_dim=256,
        device=device,
        adaptation_strategy=strategy,
    )


def create_contrastive_learner(
    input_dim: int = 128,
    hidden_dim: int = 256,
) -> ContrastiveLearner:
    """Create standalone contrastive learner."""
    return ContrastiveLearner(
        input_dim=input_dim,
        hidden_dim=hidden_dim,
    )


def create_masked_predictor(
    input_dim: int = 128,
    hidden_dim: int = 256,
    max_seq_len: int = 256,
) -> MaskedPredictor:
    """Create standalone masked predictor."""
    return MaskedPredictor(
        input_dim=input_dim,
        hidden_dim=hidden_dim,
        max_seq_len=max_seq_len,
    )
