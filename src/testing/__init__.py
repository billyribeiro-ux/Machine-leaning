"""
Revolution Alpha Engine - Universal Model Testing Framework

Comprehensive testing for any trading model:
- Fully customizable lookback periods
- Model selection and comparison
- Complete backtesting
- Downloadable results (CSV, JSON, HTML)
- Walk-forward optimization
- Monte Carlo analysis
"""

from .model_tester import (
    UniversalModelTester,
    TestConfiguration,
    TestResults,
    TradeRecord,
    BaseTestableModel,
    MomentumModel,
    MeanReversionModel,
    ModelRegistry,
    ModelType,
    TimeFrame,
    create_model_tester,
    quick_backtest,
)

__all__ = [
    "UniversalModelTester",
    "TestConfiguration",
    "TestResults",
    "TradeRecord",
    "BaseTestableModel",
    "MomentumModel",
    "MeanReversionModel",
    "ModelRegistry",
    "ModelType",
    "TimeFrame",
    "create_model_tester",
    "quick_backtest",
]

__version__ = "0.1.0"
