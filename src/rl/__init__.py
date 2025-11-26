"""
Revolution Alpha Engine - Reinforcement Learning Trading Agents

State-of-the-art RL for adaptive trading:
- Soft Actor-Critic (SAC) for continuous actions
- Proximal Policy Optimization (PPO)
- Hierarchical RL for multi-timeframe decisions
- Risk-aware reward shaping
- Experience replay with prioritization
"""

from .trading_agent import (
    SoftActorCritic,
    PPOAgent,
    HierarchicalTradingAgent,
    TradingEnvironment,
    ActorNetwork,
    CriticNetwork,
    ValueNetwork,
    ReplayBuffer,
    PrioritizedReplayBuffer,
    ActionType,
    TradingState,
    TradingAction,
    Experience,
    create_sac_agent,
    create_ppo_agent,
    create_trading_env,
)

__all__ = [
    "SoftActorCritic",
    "PPOAgent",
    "HierarchicalTradingAgent",
    "TradingEnvironment",
    "ActorNetwork",
    "CriticNetwork",
    "ValueNetwork",
    "ReplayBuffer",
    "PrioritizedReplayBuffer",
    "ActionType",
    "TradingState",
    "TradingAction",
    "Experience",
    "create_sac_agent",
    "create_ppo_agent",
    "create_trading_env",
]

__version__ = "0.1.0"
