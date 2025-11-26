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
    BacktestResult,
    BacktestConfig,
    PerformanceMetrics,
    DrawdownAnalysis,
    create_backtest_engine,
)

__all__ = [
    "BacktestEngine",
    "Trade",
    "TradeDiagnostic",
    "BacktestResult",
    "BacktestConfig",
    "PerformanceMetrics",
    "DrawdownAnalysis",
    "create_backtest_engine",
]

__version__ = "0.1.0"
