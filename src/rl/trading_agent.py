"""
Deep Reinforcement Learning Trading Agent.

State-of-the-art RL agents for adaptive trading:
- Proximal Policy Optimization (PPO)
- Soft Actor-Critic (SAC)
- Multi-agent systems for portfolio optimization
- Hierarchical RL for multi-timeframe decisions
- Risk-aware reward shaping
- Market-adaptive exploration

These agents learn optimal trading strategies through
interaction with the market environment.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Normal, Categorical
import numpy as np
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass, field
from datetime import datetime
from collections import deque
from enum import Enum
import asyncio
import logging
from abc import ABC, abstractmethod
import random
import copy


logger = logging.getLogger(__name__)


class ActionType(Enum):
    """Trading action types."""
    HOLD = 0
    BUY = 1
    SELL = 2
    CLOSE = 3


@dataclass
class TradingState:
    """Market state representation for RL agent."""
    # Price features
    prices: np.ndarray  # OHLCV history
    returns: np.ndarray  # Return history
    volatility: float

    # Technical features
    technical_features: np.ndarray

    # Position info
    position: float  # Current position size
    entry_price: float  # Average entry price
    unrealized_pnl: float

    # Account info
    cash: float
    equity: float

    # Market context
    market_regime: int
    time_features: np.ndarray

    def to_tensor(self) -> torch.Tensor:
        """Convert state to tensor."""
        flat = np.concatenate([
            self.prices.flatten()[-100:],  # Last 100 prices
            self.returns.flatten()[-50:],
            [self.volatility],
            self.technical_features.flatten()[-50:],
            [self.position, self.entry_price, self.unrealized_pnl],
            [self.cash, self.equity],
            [self.market_regime],
            self.time_features.flatten(),
        ])
        return torch.tensor(flat, dtype=torch.float32)


@dataclass
class TradingAction:
    """Trading action from RL agent."""
    action_type: ActionType
    size: float  # Position size (0-1 of available capital)
    confidence: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Experience:
    """Single experience tuple for replay."""
    state: torch.Tensor
    action: torch.Tensor
    reward: float
    next_state: torch.Tensor
    done: bool
    info: Dict[str, Any] = field(default_factory=dict)


class ReplayBuffer:
    """Experience replay buffer for off-policy learning."""

    def __init__(self, capacity: int = 100000):
        self.buffer: deque = deque(maxlen=capacity)

    def push(self, experience: Experience):
        """Add experience to buffer."""
        self.buffer.append(experience)

    def sample(self, batch_size: int) -> List[Experience]:
        """Sample random batch."""
        return random.sample(self.buffer, min(batch_size, len(self.buffer)))

    def __len__(self) -> int:
        return len(self.buffer)


class PrioritizedReplayBuffer:
    """Prioritized experience replay with importance sampling."""

    def __init__(
        self,
        capacity: int = 100000,
        alpha: float = 0.6,
        beta_start: float = 0.4,
        beta_frames: int = 100000,
    ):
        self.capacity = capacity
        self.alpha = alpha
        self.beta_start = beta_start
        self.beta_frames = beta_frames
        self.frame = 1

        self.buffer: List[Experience] = []
        self.priorities = np.zeros(capacity, dtype=np.float32)
        self.position = 0
        self.size = 0

    @property
    def beta(self) -> float:
        """Annealed beta for importance sampling."""
        return min(1.0, self.beta_start + self.frame * (1.0 - self.beta_start) / self.beta_frames)

    def push(self, experience: Experience, priority: Optional[float] = None):
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

    def sample(
        self,
        batch_size: int,
    ) -> Tuple[List[Experience], np.ndarray, np.ndarray]:
        """Sample with priorities and importance weights."""
        if self.size < batch_size:
            batch_size = self.size

        priorities = self.priorities[:self.size]
        probabilities = priorities / priorities.sum()

        indices = np.random.choice(self.size, batch_size, p=probabilities, replace=False)

        # Importance sampling weights
        weights = (self.size * probabilities[indices]) ** (-self.beta)
        weights /= weights.max()

        self.frame += 1

        return [self.buffer[i] for i in indices], indices, weights

    def update_priorities(self, indices: np.ndarray, priorities: np.ndarray):
        """Update priorities for sampled experiences."""
        for idx, priority in zip(indices, priorities):
            self.priorities[idx] = priority ** self.alpha

    def __len__(self) -> int:
        return self.size


class ActorNetwork(nn.Module):
    """
    Actor network for continuous action spaces.

    Outputs mean and std for Gaussian policy.
    """

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        hidden_dims: List[int] = [256, 256],
        log_std_min: float = -20,
        log_std_max: float = 2,
    ):
        super().__init__()

        self.log_std_min = log_std_min
        self.log_std_max = log_std_max

        # Build network
        layers = []
        prev_dim = state_dim

        for hidden_dim in hidden_dims:
            layers.extend([
                nn.Linear(prev_dim, hidden_dim),
                nn.LayerNorm(hidden_dim),
                nn.ReLU(),
            ])
            prev_dim = hidden_dim

        self.features = nn.Sequential(*layers)

        # Separate heads for mean and log_std
        self.mean_head = nn.Linear(prev_dim, action_dim)
        self.log_std_head = nn.Linear(prev_dim, action_dim)

    def forward(self, state: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """Forward pass returns mean and log_std."""
        features = self.features(state)
        mean = self.mean_head(features)
        log_std = self.log_std_head(features)
        log_std = torch.clamp(log_std, self.log_std_min, self.log_std_max)

        return mean, log_std

    def sample(
        self,
        state: torch.Tensor,
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Sample action and compute log probability."""
        mean, log_std = self(state)
        std = log_std.exp()

        # Reparameterization trick
        normal = Normal(mean, std)
        x_t = normal.rsample()

        # Apply tanh squashing
        action = torch.tanh(x_t)

        # Compute log probability with correction for tanh
        log_prob = normal.log_prob(x_t)
        log_prob -= torch.log(1 - action.pow(2) + 1e-6)
        log_prob = log_prob.sum(-1, keepdim=True)

        return action, log_prob, mean

    def get_action(self, state: torch.Tensor, deterministic: bool = False) -> torch.Tensor:
        """Get action for execution."""
        mean, log_std = self(state)

        if deterministic:
            return torch.tanh(mean)

        std = log_std.exp()
        normal = Normal(mean, std)
        action = torch.tanh(normal.sample())

        return action


class CriticNetwork(nn.Module):
    """
    Critic network for value estimation.

    Twin Q-networks for SAC-style learning.
    """

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        hidden_dims: List[int] = [256, 256],
    ):
        super().__init__()

        # Q1 network
        q1_layers = []
        prev_dim = state_dim + action_dim

        for hidden_dim in hidden_dims:
            q1_layers.extend([
                nn.Linear(prev_dim, hidden_dim),
                nn.LayerNorm(hidden_dim),
                nn.ReLU(),
            ])
            prev_dim = hidden_dim

        q1_layers.append(nn.Linear(prev_dim, 1))
        self.q1 = nn.Sequential(*q1_layers)

        # Q2 network (twin)
        q2_layers = []
        prev_dim = state_dim + action_dim

        for hidden_dim in hidden_dims:
            q2_layers.extend([
                nn.Linear(prev_dim, hidden_dim),
                nn.LayerNorm(hidden_dim),
                nn.ReLU(),
            ])
            prev_dim = hidden_dim

        q2_layers.append(nn.Linear(prev_dim, 1))
        self.q2 = nn.Sequential(*q2_layers)

    def forward(
        self,
        state: torch.Tensor,
        action: torch.Tensor,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """Forward pass returns both Q values."""
        x = torch.cat([state, action], dim=-1)
        return self.q1(x), self.q2(x)

    def q1_forward(self, state: torch.Tensor, action: torch.Tensor) -> torch.Tensor:
        """Forward through Q1 only."""
        x = torch.cat([state, action], dim=-1)
        return self.q1(x)


class ValueNetwork(nn.Module):
    """Value network for state value estimation."""

    def __init__(
        self,
        state_dim: int,
        hidden_dims: List[int] = [256, 256],
    ):
        super().__init__()

        layers = []
        prev_dim = state_dim

        for hidden_dim in hidden_dims:
            layers.extend([
                nn.Linear(prev_dim, hidden_dim),
                nn.LayerNorm(hidden_dim),
                nn.ReLU(),
            ])
            prev_dim = hidden_dim

        layers.append(nn.Linear(prev_dim, 1))
        self.network = nn.Sequential(*layers)

    def forward(self, state: torch.Tensor) -> torch.Tensor:
        """Forward pass returns value estimate."""
        return self.network(state)


class SoftActorCritic:
    """
    Soft Actor-Critic (SAC) agent for trading.

    Features:
    - Automatic entropy tuning
    - Twin Q-networks for stability
    - Soft value function
    - Risk-aware reward shaping
    """

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        hidden_dims: List[int] = [256, 256],
        lr: float = 3e-4,
        gamma: float = 0.99,
        tau: float = 0.005,
        alpha: float = 0.2,
        auto_entropy: bool = True,
        target_entropy: Optional[float] = None,
        device: str = "cpu",
    ):
        self.device = device
        self.gamma = gamma
        self.tau = tau
        self.alpha = alpha
        self.auto_entropy = auto_entropy

        # Networks
        self.actor = ActorNetwork(state_dim, action_dim, hidden_dims).to(device)
        self.critic = CriticNetwork(state_dim, action_dim, hidden_dims).to(device)
        self.critic_target = CriticNetwork(state_dim, action_dim, hidden_dims).to(device)
        self.critic_target.load_state_dict(self.critic.state_dict())

        # Optimizers
        self.actor_optimizer = torch.optim.Adam(self.actor.parameters(), lr=lr)
        self.critic_optimizer = torch.optim.Adam(self.critic.parameters(), lr=lr)

        # Entropy tuning
        if auto_entropy:
            self.target_entropy = target_entropy or -action_dim
            self.log_alpha = torch.zeros(1, requires_grad=True, device=device)
            self.alpha_optimizer = torch.optim.Adam([self.log_alpha], lr=lr)

        # Replay buffer
        self.replay_buffer = PrioritizedReplayBuffer()

        # Training stats
        self.total_steps = 0
        self.training_stats: Dict[str, List[float]] = {
            "actor_loss": [],
            "critic_loss": [],
            "alpha_loss": [],
            "alpha": [],
        }

        logger.info(f"SAC agent initialized with state_dim={state_dim}, action_dim={action_dim}")

    def select_action(
        self,
        state: torch.Tensor,
        deterministic: bool = False,
    ) -> torch.Tensor:
        """Select action given state."""
        if state.dim() == 1:
            state = state.unsqueeze(0)

        state = state.to(self.device)

        with torch.no_grad():
            action = self.actor.get_action(state, deterministic)

        return action.cpu()

    def update(self, batch_size: int = 256) -> Dict[str, float]:
        """Update networks from replay buffer."""
        if len(self.replay_buffer) < batch_size:
            return {}

        experiences, indices, weights = self.replay_buffer.sample(batch_size)

        # Prepare batch
        states = torch.stack([e.state for e in experiences]).to(self.device)
        actions = torch.stack([e.action for e in experiences]).to(self.device)
        rewards = torch.tensor([e.reward for e in experiences], dtype=torch.float32).to(self.device).unsqueeze(-1)
        next_states = torch.stack([e.next_state for e in experiences]).to(self.device)
        dones = torch.tensor([e.done for e in experiences], dtype=torch.float32).to(self.device).unsqueeze(-1)
        weights = torch.tensor(weights, dtype=torch.float32).to(self.device).unsqueeze(-1)

        # Update critic
        with torch.no_grad():
            next_actions, next_log_probs, _ = self.actor.sample(next_states)
            q1_next, q2_next = self.critic_target(next_states, next_actions)
            q_next = torch.min(q1_next, q2_next) - self.alpha * next_log_probs
            q_target = rewards + (1 - dones) * self.gamma * q_next

        q1, q2 = self.critic(states, actions)
        critic_loss = (weights * (F.mse_loss(q1, q_target, reduction='none') +
                                   F.mse_loss(q2, q_target, reduction='none'))).mean()

        self.critic_optimizer.zero_grad()
        critic_loss.backward()
        torch.nn.utils.clip_grad_norm_(self.critic.parameters(), 1.0)
        self.critic_optimizer.step()

        # Update actor
        new_actions, log_probs, _ = self.actor.sample(states)
        q1_new, q2_new = self.critic(states, new_actions)
        q_new = torch.min(q1_new, q2_new)
        actor_loss = (self.alpha * log_probs - q_new).mean()

        self.actor_optimizer.zero_grad()
        actor_loss.backward()
        torch.nn.utils.clip_grad_norm_(self.actor.parameters(), 1.0)
        self.actor_optimizer.step()

        # Update alpha
        alpha_loss = 0.0
        if self.auto_entropy:
            alpha_loss = -(self.log_alpha * (log_probs + self.target_entropy).detach()).mean()

            self.alpha_optimizer.zero_grad()
            alpha_loss.backward()
            self.alpha_optimizer.step()

            self.alpha = self.log_alpha.exp().item()

        # Soft update target
        self._soft_update()

        # Update priorities
        td_errors = torch.abs(q1 - q_target).detach().cpu().numpy().flatten()
        self.replay_buffer.update_priorities(indices, td_errors + 1e-6)

        self.total_steps += 1

        stats = {
            "critic_loss": critic_loss.item(),
            "actor_loss": actor_loss.item(),
            "alpha": self.alpha,
        }

        if self.auto_entropy:
            stats["alpha_loss"] = alpha_loss.item()

        for key, value in stats.items():
            self.training_stats[key].append(value)

        return stats

    def _soft_update(self):
        """Soft update target networks."""
        for param, target_param in zip(
            self.critic.parameters(),
            self.critic_target.parameters()
        ):
            target_param.data.copy_(
                self.tau * param.data + (1 - self.tau) * target_param.data
            )

    def add_experience(self, experience: Experience):
        """Add experience to replay buffer."""
        self.replay_buffer.push(experience)

    def save(self, path: str):
        """Save agent state."""
        state = {
            "actor": self.actor.state_dict(),
            "critic": self.critic.state_dict(),
            "critic_target": self.critic_target.state_dict(),
            "actor_optimizer": self.actor_optimizer.state_dict(),
            "critic_optimizer": self.critic_optimizer.state_dict(),
            "total_steps": self.total_steps,
        }

        if self.auto_entropy:
            state["log_alpha"] = self.log_alpha
            state["alpha_optimizer"] = self.alpha_optimizer.state_dict()

        torch.save(state, path)
        logger.info(f"SAC agent saved to {path}")

    def load(self, path: str):
        """Load agent state."""
        state = torch.load(path, map_location=self.device, weights_only=True)

        self.actor.load_state_dict(state["actor"])
        self.critic.load_state_dict(state["critic"])
        self.critic_target.load_state_dict(state["critic_target"])
        self.actor_optimizer.load_state_dict(state["actor_optimizer"])
        self.critic_optimizer.load_state_dict(state["critic_optimizer"])
        self.total_steps = state["total_steps"]

        if self.auto_entropy and "log_alpha" in state:
            self.log_alpha = state["log_alpha"]
            self.alpha_optimizer.load_state_dict(state["alpha_optimizer"])

        logger.info(f"SAC agent loaded from {path}")


class PPOAgent:
    """
    Proximal Policy Optimization agent for trading.

    Features:
    - Clipped objective for stable learning
    - Generalized advantage estimation (GAE)
    - Multiple epochs per update
    - Adaptive KL penalty
    """

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        hidden_dims: List[int] = [256, 256],
        lr: float = 3e-4,
        gamma: float = 0.99,
        gae_lambda: float = 0.95,
        clip_epsilon: float = 0.2,
        value_coef: float = 0.5,
        entropy_coef: float = 0.01,
        max_grad_norm: float = 0.5,
        n_epochs: int = 10,
        batch_size: int = 64,
        device: str = "cpu",
    ):
        self.device = device
        self.gamma = gamma
        self.gae_lambda = gae_lambda
        self.clip_epsilon = clip_epsilon
        self.value_coef = value_coef
        self.entropy_coef = entropy_coef
        self.max_grad_norm = max_grad_norm
        self.n_epochs = n_epochs
        self.batch_size = batch_size

        # Actor-Critic network
        self.actor = ActorNetwork(state_dim, action_dim, hidden_dims).to(device)
        self.critic = ValueNetwork(state_dim, hidden_dims).to(device)

        # Optimizer
        self.optimizer = torch.optim.Adam([
            {"params": self.actor.parameters(), "lr": lr},
            {"params": self.critic.parameters(), "lr": lr},
        ])

        # Rollout storage
        self.states: List[torch.Tensor] = []
        self.actions: List[torch.Tensor] = []
        self.log_probs: List[torch.Tensor] = []
        self.rewards: List[float] = []
        self.dones: List[bool] = []
        self.values: List[torch.Tensor] = []

        # Stats
        self.total_steps = 0

        logger.info(f"PPO agent initialized")

    def select_action(
        self,
        state: torch.Tensor,
        deterministic: bool = False,
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Select action and return action, log_prob, value."""
        if state.dim() == 1:
            state = state.unsqueeze(0)

        state = state.to(self.device)

        with torch.no_grad():
            if deterministic:
                mean, _ = self.actor(state)
                action = torch.tanh(mean)
                log_prob = torch.zeros(1)
            else:
                action, log_prob, _ = self.actor.sample(state)

            value = self.critic(state)

        return action.cpu(), log_prob.cpu(), value.cpu()

    def store_transition(
        self,
        state: torch.Tensor,
        action: torch.Tensor,
        log_prob: torch.Tensor,
        reward: float,
        done: bool,
        value: torch.Tensor,
    ):
        """Store transition for PPO update."""
        self.states.append(state)
        self.actions.append(action)
        self.log_probs.append(log_prob)
        self.rewards.append(reward)
        self.dones.append(done)
        self.values.append(value)

    def update(self, next_value: torch.Tensor) -> Dict[str, float]:
        """Update policy using collected rollout."""
        if len(self.states) == 0:
            return {}

        # Convert to tensors
        states = torch.stack(self.states).to(self.device)
        actions = torch.stack(self.actions).to(self.device)
        old_log_probs = torch.stack(self.log_probs).to(self.device)
        values = torch.stack(self.values).squeeze(-1).to(self.device)

        # Compute GAE
        advantages, returns = self._compute_gae(next_value)
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

        # PPO update for n_epochs
        total_actor_loss = 0
        total_critic_loss = 0
        total_entropy = 0

        dataset_size = len(self.states)

        for _ in range(self.n_epochs):
            indices = torch.randperm(dataset_size)

            for start in range(0, dataset_size, self.batch_size):
                end = start + self.batch_size
                batch_indices = indices[start:end]

                batch_states = states[batch_indices]
                batch_actions = actions[batch_indices]
                batch_old_log_probs = old_log_probs[batch_indices]
                batch_advantages = advantages[batch_indices]
                batch_returns = returns[batch_indices]

                # Get current policy outputs
                new_actions, new_log_probs, mean = self.actor.sample(batch_states)

                # Recalculate log probs for old actions
                mean_old, log_std = self.actor(batch_states)
                std = log_std.exp()
                dist = Normal(mean_old, std)
                new_log_probs_old = dist.log_prob(
                    torch.atanh(torch.clamp(batch_actions, -0.999, 0.999))
                )
                new_log_probs_old -= torch.log(1 - batch_actions.pow(2) + 1e-6)
                new_log_probs_old = new_log_probs_old.sum(-1, keepdim=True)

                # Policy loss with clipping
                ratio = (new_log_probs_old - batch_old_log_probs).exp()
                surr1 = ratio * batch_advantages.unsqueeze(-1)
                surr2 = torch.clamp(ratio, 1 - self.clip_epsilon, 1 + self.clip_epsilon) * batch_advantages.unsqueeze(-1)
                actor_loss = -torch.min(surr1, surr2).mean()

                # Value loss
                new_values = self.critic(batch_states)
                critic_loss = F.mse_loss(new_values.squeeze(-1), batch_returns)

                # Entropy bonus
                entropy = dist.entropy().mean()

                # Total loss
                loss = (
                    actor_loss +
                    self.value_coef * critic_loss -
                    self.entropy_coef * entropy
                )

                self.optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(
                    list(self.actor.parameters()) + list(self.critic.parameters()),
                    self.max_grad_norm
                )
                self.optimizer.step()

                total_actor_loss += actor_loss.item()
                total_critic_loss += critic_loss.item()
                total_entropy += entropy.item()

        # Clear rollout
        self._clear_rollout()

        n_updates = self.n_epochs * (dataset_size // self.batch_size + 1)

        return {
            "actor_loss": total_actor_loss / n_updates,
            "critic_loss": total_critic_loss / n_updates,
            "entropy": total_entropy / n_updates,
        }

    def _compute_gae(self, next_value: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """Compute Generalized Advantage Estimation."""
        rewards = torch.tensor(self.rewards, dtype=torch.float32).to(self.device)
        dones = torch.tensor(self.dones, dtype=torch.float32).to(self.device)
        values = torch.stack(self.values).squeeze(-1).to(self.device)

        # Append next_value for bootstrapping
        values = torch.cat([values, next_value.to(self.device).squeeze()])

        advantages = torch.zeros_like(rewards)
        last_gae = 0

        for t in reversed(range(len(rewards))):
            next_non_terminal = 1 - dones[t]
            delta = rewards[t] + self.gamma * values[t + 1] * next_non_terminal - values[t]
            advantages[t] = last_gae = delta + self.gamma * self.gae_lambda * next_non_terminal * last_gae

        returns = advantages + values[:-1]

        return advantages, returns

    def _clear_rollout(self):
        """Clear stored rollout."""
        self.states.clear()
        self.actions.clear()
        self.log_probs.clear()
        self.rewards.clear()
        self.dones.clear()
        self.values.clear()

    def save(self, path: str):
        """Save agent state."""
        state = {
            "actor": self.actor.state_dict(),
            "critic": self.critic.state_dict(),
            "optimizer": self.optimizer.state_dict(),
            "total_steps": self.total_steps,
        }
        torch.save(state, path)

    def load(self, path: str):
        """Load agent state."""
        state = torch.load(path, map_location=self.device, weights_only=True)
        self.actor.load_state_dict(state["actor"])
        self.critic.load_state_dict(state["critic"])
        self.optimizer.load_state_dict(state["optimizer"])
        self.total_steps = state["total_steps"]


class TradingEnvironment:
    """
    Trading environment for RL training.

    Features:
    - Realistic market simulation
    - Transaction costs
    - Slippage modeling
    - Position limits
    - Risk-aware reward shaping
    """

    def __init__(
        self,
        initial_capital: float = 100000,
        max_position: float = 1.0,
        transaction_cost: float = 0.001,
        slippage: float = 0.0005,
        risk_free_rate: float = 0.02,
        reward_scaling: float = 1.0,
    ):
        self.initial_capital = initial_capital
        self.max_position = max_position
        self.transaction_cost = transaction_cost
        self.slippage = slippage
        self.risk_free_rate = risk_free_rate / 252  # Daily
        self.reward_scaling = reward_scaling

        # State
        self.cash = initial_capital
        self.position = 0.0
        self.entry_price = 0.0
        self.current_step = 0

        # History
        self.equity_curve: List[float] = [initial_capital]
        self.trades: List[Dict] = []

        # Data
        self.prices: Optional[np.ndarray] = None
        self.features: Optional[np.ndarray] = None

    def reset(
        self,
        prices: np.ndarray,
        features: np.ndarray,
    ) -> TradingState:
        """Reset environment with new data."""
        self.prices = prices
        self.features = features

        self.cash = self.initial_capital
        self.position = 0.0
        self.entry_price = 0.0
        self.current_step = 0

        self.equity_curve = [self.initial_capital]
        self.trades = []

        return self._get_state()

    def step(self, action: torch.Tensor) -> Tuple[TradingState, float, bool, Dict]:
        """Execute action and return next state, reward, done, info."""
        # Parse action
        action_type = int((action[0].item() + 1) * 1.5)  # Map [-1,1] to [0,3]
        action_type = ActionType(min(action_type, 3))
        action_size = (action[1].item() + 1) / 2  # Map [-1,1] to [0,1]

        current_price = self.prices[self.current_step]
        prev_equity = self._get_equity(current_price)

        # Execute action
        if action_type == ActionType.BUY and self.position <= 0:
            self._execute_buy(current_price, action_size)
        elif action_type == ActionType.SELL and self.position >= 0:
            self._execute_sell(current_price, action_size)
        elif action_type == ActionType.CLOSE:
            self._close_position(current_price)

        # Move to next step
        self.current_step += 1
        done = self.current_step >= len(self.prices) - 1

        if not done:
            next_price = self.prices[self.current_step]
        else:
            next_price = current_price

        # Calculate reward
        new_equity = self._get_equity(next_price)
        reward = self._calculate_reward(prev_equity, new_equity, done)

        self.equity_curve.append(new_equity)

        # Get next state
        next_state = self._get_state()

        info = {
            "equity": new_equity,
            "position": self.position,
            "cash": self.cash,
            "n_trades": len(self.trades),
        }

        return next_state, reward, done, info

    def _execute_buy(self, price: float, size: float):
        """Execute buy order."""
        # Apply slippage
        execution_price = price * (1 + self.slippage)

        # Calculate position size
        available_capital = self.cash * self.max_position * size
        shares = available_capital / execution_price

        # Apply transaction cost
        cost = shares * execution_price * self.transaction_cost

        if self.position < 0:
            # Closing short first
            close_pnl = self.position * (self.entry_price - execution_price)
            self.cash += close_pnl - cost
            self.position = 0

        # Open long
        self.cash -= shares * execution_price + cost
        self.position += shares
        self.entry_price = execution_price

        self.trades.append({
            "step": self.current_step,
            "type": "BUY",
            "price": execution_price,
            "shares": shares,
            "cost": cost,
        })

    def _execute_sell(self, price: float, size: float):
        """Execute sell order."""
        execution_price = price * (1 - self.slippage)

        available_capital = self.cash * self.max_position * size
        shares = available_capital / execution_price

        cost = shares * execution_price * self.transaction_cost

        if self.position > 0:
            # Closing long first
            close_pnl = self.position * (execution_price - self.entry_price)
            self.cash += close_pnl - cost
            self.position = 0

        # Open short
        self.cash += shares * execution_price - cost
        self.position -= shares
        self.entry_price = execution_price

        self.trades.append({
            "step": self.current_step,
            "type": "SELL",
            "price": execution_price,
            "shares": shares,
            "cost": cost,
        })

    def _close_position(self, price: float):
        """Close current position."""
        if self.position == 0:
            return

        if self.position > 0:
            execution_price = price * (1 - self.slippage)
            pnl = self.position * (execution_price - self.entry_price)
        else:
            execution_price = price * (1 + self.slippage)
            pnl = -self.position * (self.entry_price - execution_price)

        cost = abs(self.position) * execution_price * self.transaction_cost
        self.cash += pnl - cost
        self.position = 0

        self.trades.append({
            "step": self.current_step,
            "type": "CLOSE",
            "price": execution_price,
            "pnl": pnl,
            "cost": cost,
        })

    def _get_equity(self, price: float) -> float:
        """Calculate current equity."""
        if self.position > 0:
            unrealized = self.position * (price - self.entry_price)
        elif self.position < 0:
            unrealized = -self.position * (self.entry_price - price)
        else:
            unrealized = 0

        return self.cash + unrealized

    def _calculate_reward(
        self,
        prev_equity: float,
        new_equity: float,
        done: bool,
    ) -> float:
        """Calculate risk-adjusted reward."""
        # Return-based reward
        returns = (new_equity - prev_equity) / prev_equity

        # Risk penalty (drawdown)
        max_equity = max(self.equity_curve)
        drawdown = (max_equity - new_equity) / max_equity
        drawdown_penalty = -drawdown * 0.5

        # Sharpe component (excess return over risk-free)
        excess_return = returns - self.risk_free_rate

        # Combine rewards
        reward = excess_return + drawdown_penalty

        # Scale reward
        reward *= self.reward_scaling

        # Terminal reward
        if done:
            # Final Sharpe-like bonus
            returns_array = np.diff(self.equity_curve) / np.array(self.equity_curve[:-1])
            if len(returns_array) > 1 and np.std(returns_array) > 0:
                sharpe = np.mean(returns_array) / np.std(returns_array) * np.sqrt(252)
                reward += sharpe * 0.1

        return float(reward)

    def _get_state(self) -> TradingState:
        """Get current state."""
        # Get price history
        lookback = min(100, self.current_step + 1)
        price_history = self.prices[max(0, self.current_step - lookback + 1):self.current_step + 1]

        # Pad if needed
        if len(price_history) < 100:
            price_history = np.pad(
                price_history,
                (100 - len(price_history), 0),
                mode='edge'
            )

        # Calculate returns
        returns = np.diff(price_history) / price_history[:-1]
        returns = np.pad(returns, (1, 0), mode='constant')

        # Volatility
        volatility = np.std(returns[-20:]) * np.sqrt(252) if len(returns) >= 20 else 0.2

        # Technical features
        if self.features is not None:
            tech_features = self.features[self.current_step]
        else:
            tech_features = np.zeros(50)

        # Current price for PnL
        current_price = self.prices[self.current_step]

        # Unrealized PnL
        if self.position != 0:
            if self.position > 0:
                unrealized_pnl = self.position * (current_price - self.entry_price)
            else:
                unrealized_pnl = -self.position * (self.entry_price - current_price)
        else:
            unrealized_pnl = 0

        # Time features (day of week, hour, etc.)
        time_features = np.array([
            (self.current_step % 252) / 252,  # Day of year proxy
            (self.current_step % 5) / 5,  # Day of week proxy
        ])

        return TradingState(
            prices=price_history,
            returns=returns,
            volatility=volatility,
            technical_features=tech_features,
            position=self.position,
            entry_price=self.entry_price,
            unrealized_pnl=unrealized_pnl,
            cash=self.cash,
            equity=self._get_equity(current_price),
            market_regime=0,
            time_features=time_features,
        )


class HierarchicalTradingAgent:
    """
    Hierarchical RL agent for multi-timeframe trading.

    High-level policy decides regime/direction.
    Low-level policy handles execution timing.
    """

    def __init__(
        self,
        state_dim: int,
        device: str = "cpu",
    ):
        self.device = device

        # High-level policy (macro decisions)
        self.high_level = SoftActorCritic(
            state_dim=state_dim,
            action_dim=3,  # [direction, size, horizon]
            hidden_dims=[256, 256],
            device=device,
        )

        # Low-level policy (execution)
        self.low_level = PPOAgent(
            state_dim=state_dim + 3,  # State + high-level action
            action_dim=2,  # [execute, timing]
            hidden_dims=[128, 128],
            device=device,
        )

        self.high_level_action: Optional[torch.Tensor] = None
        self.steps_since_high_level = 0
        self.high_level_horizon = 10  # Re-evaluate every N steps

        logger.info("Hierarchical trading agent initialized")

    def select_action(
        self,
        state: torch.Tensor,
        deterministic: bool = False,
    ) -> torch.Tensor:
        """Select action using hierarchical policy."""
        # Check if we need new high-level decision
        if (self.high_level_action is None or
            self.steps_since_high_level >= self.high_level_horizon):

            self.high_level_action = self.high_level.select_action(state, deterministic)
            self.steps_since_high_level = 0

            # Extract horizon from action
            horizon = int((self.high_level_action[0, 2].item() + 1) * 5) + 5
            self.high_level_horizon = horizon

        # Augment state with high-level action
        augmented_state = torch.cat([
            state.flatten(),
            self.high_level_action.flatten()
        ])

        # Get low-level action
        low_action, _, _ = self.low_level.select_action(augmented_state, deterministic)

        self.steps_since_high_level += 1

        # Combine into final action
        direction = self.high_level_action[0, 0]
        size = self.high_level_action[0, 1]
        execute = low_action[0, 0]

        # Only execute if low-level says so
        if execute < 0:
            return torch.tensor([[0.0, 0.0]])  # Hold

        return torch.tensor([[direction.item(), size.item()]])


def create_sac_agent(
    state_dim: int,
    action_dim: int = 2,
    device: str = "cpu",
) -> SoftActorCritic:
    """Create SAC trading agent."""
    return SoftActorCritic(
        state_dim=state_dim,
        action_dim=action_dim,
        device=device,
    )


def create_ppo_agent(
    state_dim: int,
    action_dim: int = 2,
    device: str = "cpu",
) -> PPOAgent:
    """Create PPO trading agent."""
    return PPOAgent(
        state_dim=state_dim,
        action_dim=action_dim,
        device=device,
    )


def create_trading_env(
    initial_capital: float = 100000,
) -> TradingEnvironment:
    """Create trading environment."""
    return TradingEnvironment(initial_capital=initial_capital)
