"""
Revolution Alpha Engine - Machine Learning Infrastructure

Advanced ML models for institutional-grade trading:
- Temporal Fusion Transformers for time series forecasting
- Ensemble models with learned weighting
- Online learning for continuous adaptation
- Self-supervised learning for market representation
- Meta-learning for rapid regime adaptation
"""

from .models import (
    TemporalFusionTransformer,
    VariableSelectionNetwork,
    GatedResidualNetwork,
    InterpretableAttention,
    EnsembleModel,
    OnlineLearner,
    create_tft_model,
    create_ensemble,
)

from .self_supervised import (
    AdaptiveLearningSystem,
    AdaptationStrategy,
    ContrastiveLearner,
    MaskedPredictor,
    MetaLearner,
    MarketAugmenter,
    ConceptDriftDetector,
    PrioritizedReplayBuffer,
    Experience,
    LearningState,
    SelfSupervisedTrainer,
    create_adaptive_system,
    create_contrastive_learner,
    create_masked_predictor,
)

from .data_pipeline import (
    MLDataPipeline,
    FeatureEngineer,
    FeatureConfig,
    DataStreamManager,
    DataStreamConfig,
    FeatureType,
    TimeFrame,
    create_feature_engineer,
    create_ml_pipeline,
    create_stream_manager,
)

__all__ = [
    # Models
    "TemporalFusionTransformer",
    "VariableSelectionNetwork",
    "GatedResidualNetwork",
    "InterpretableAttention",
    "EnsembleModel",
    "OnlineLearner",
    "create_tft_model",
    "create_ensemble",
    # Self-Supervised
    "AdaptiveLearningSystem",
    "AdaptationStrategy",
    "ContrastiveLearner",
    "MaskedPredictor",
    "MetaLearner",
    "MarketAugmenter",
    "ConceptDriftDetector",
    "PrioritizedReplayBuffer",
    "Experience",
    "LearningState",
    "SelfSupervisedTrainer",
    "create_adaptive_system",
    "create_contrastive_learner",
    "create_masked_predictor",
    # Data Pipeline
    "MLDataPipeline",
    "FeatureEngineer",
    "FeatureConfig",
    "DataStreamManager",
    "DataStreamConfig",
    "FeatureType",
    "TimeFrame",
    "create_feature_engineer",
    "create_ml_pipeline",
    "create_stream_manager",
]

__version__ = "0.1.0"
