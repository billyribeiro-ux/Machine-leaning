"""
Revolution Alpha Engine - Backtesting Framework

Professional backtesting with full trade diagnostics:
- High-fidelity market simulation
- Realistic transaction costs and slippage
- Complete trade reasoning and diagnostics
- Performance attribution
- Walk-forward optimization
- Monte Carlo analysis
"""

from .engine import (
    BacktestEngine,
    Trade,
    TradeDiagnostic,
    BacktestConfig,
)

from .validation import (
    BacktestValidator,
    WalkForwardOptimizer,
    PurgedKFoldCV,
    CombinatorialPurgedCV,
    TransactionCostModel,
    CrisisScenario,
    deflated_sharpe_ratio,
    probability_of_overfitting,
    minimum_backtest_length,
    bonferroni_correction,
    benjamini_hochberg,
    holm_correction,
)

__all__ = [
    "BacktestEngine",
    "Trade",
    "TradeDiagnostic",
    "BacktestConfig",
    # Validation framework
    "BacktestValidator",
    "WalkForwardOptimizer",
    "PurgedKFoldCV",
    "CombinatorialPurgedCV",
    "TransactionCostModel",
    "CrisisScenario",
    "deflated_sharpe_ratio",
    "probability_of_overfitting",
    "minimum_backtest_length",
    "bonferroni_correction",
    "benjamini_hochberg",
    "holm_correction",
]

__version__ = "0.1.0"
