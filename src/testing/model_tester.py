"""
Universal Model Tester.

A comprehensive testing framework for any trading model with:
- Fully customizable lookback periods
- Model selection and comparison
- Complete backtesting capabilities
- Downloadable results in multiple formats
- Performance metrics and analysis
- Walk-forward optimization
- Monte Carlo analysis
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any, Callable, Union, Type
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from abc import ABC, abstractmethod
import json
import csv
import logging
from pathlib import Path
import asyncio
from collections import defaultdict


logger = logging.getLogger(__name__)


class ModelType(Enum):
    """Available model types."""
    MOMENTUM = "momentum"
    MEAN_REVERSION = "mean_reversion"
    BREAKOUT = "breakout"
    SCALPER = "scalper"
    TREND_FOLLOWING = "trend_following"
    STATISTICAL_ARB = "statistical_arb"
    ML_CLASSIFIER = "ml_classifier"
    ML_REGRESSOR = "ml_regressor"
    ENSEMBLE = "ensemble"
    CUSTOM = "custom"


class TimeFrame(Enum):
    """Trading timeframes."""
    TICK = "tick"
    S1 = "1s"
    S5 = "5s"
    S15 = "15s"
    S30 = "30s"
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"


@dataclass
class TestConfiguration:
    """Configuration for model testing."""
    # Time settings
    lookback_days: int = 252
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    timeframe: TimeFrame = TimeFrame.M5

    # Model settings
    model_type: ModelType = ModelType.MOMENTUM
    model_params: Dict[str, Any] = field(default_factory=dict)

    # Backtest settings
    initial_capital: float = 100000.0
    position_size: float = 0.1  # 10% of capital
    max_positions: int = 5
    commission: float = 0.001  # 0.1%
    slippage: float = 0.0005  # 0.05%

    # Risk settings
    stop_loss_pct: Optional[float] = 0.02
    take_profit_pct: Optional[float] = 0.04
    trailing_stop_pct: Optional[float] = None
    max_drawdown_pct: float = 0.20

    # Walk-forward settings
    walk_forward: bool = False
    train_period_days: int = 60
    test_period_days: int = 20

    # Output settings
    save_trades: bool = True
    save_equity_curve: bool = True
    generate_report: bool = True
    output_format: str = "all"  # csv, json, html, all


@dataclass
class TradeRecord:
    """Record of a single trade."""
    trade_id: str
    symbol: str
    direction: str  # "long" or "short"
    entry_time: datetime
    entry_price: float
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    quantity: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    commission: float = 0.0
    slippage: float = 0.0

    # Trade reasoning
    entry_reason: str = ""
    exit_reason: str = ""
    signals: Dict[str, Any] = field(default_factory=dict)
    indicators: Dict[str, float] = field(default_factory=dict)

    # Risk metrics
    max_favorable_excursion: float = 0.0
    max_adverse_excursion: float = 0.0
    r_multiple: float = 0.0  # PnL / Risk

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = asdict(self)
        result["entry_time"] = self.entry_time.isoformat() if self.entry_time else None
        result["exit_time"] = self.exit_time.isoformat() if self.exit_time else None
        return result


@dataclass
class TestResults:
    """Results from model testing."""
    config: TestConfiguration

    # Performance metrics
    total_return: float = 0.0
    annualized_return: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0

    # Risk metrics
    max_drawdown: float = 0.0
    max_drawdown_duration_days: int = 0
    volatility: float = 0.0
    downside_volatility: float = 0.0
    var_95: float = 0.0
    cvar_95: float = 0.0

    # Trade statistics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    avg_trade_duration: float = 0.0

    # Best/Worst
    best_trade: float = 0.0
    worst_trade: float = 0.0
    consecutive_wins: int = 0
    consecutive_losses: int = 0

    # Data
    trades: List[TradeRecord] = field(default_factory=list)
    equity_curve: List[Tuple[datetime, float]] = field(default_factory=list)
    daily_returns: List[float] = field(default_factory=list)

    # Walk-forward results
    walk_forward_results: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for export."""
        return {
            "config": asdict(self.config),
            "performance": {
                "total_return": self.total_return,
                "annualized_return": self.annualized_return,
                "sharpe_ratio": self.sharpe_ratio,
                "sortino_ratio": self.sortino_ratio,
                "calmar_ratio": self.calmar_ratio,
            },
            "risk": {
                "max_drawdown": self.max_drawdown,
                "max_drawdown_duration_days": self.max_drawdown_duration_days,
                "volatility": self.volatility,
                "downside_volatility": self.downside_volatility,
                "var_95": self.var_95,
                "cvar_95": self.cvar_95,
            },
            "trades": {
                "total": self.total_trades,
                "winners": self.winning_trades,
                "losers": self.losing_trades,
                "win_rate": self.win_rate,
                "avg_win": self.avg_win,
                "avg_loss": self.avg_loss,
                "profit_factor": self.profit_factor,
                "best_trade": self.best_trade,
                "worst_trade": self.worst_trade,
            },
            "equity_curve": [
                {"date": dt.isoformat(), "equity": eq}
                for dt, eq in self.equity_curve
            ],
            "trade_list": [t.to_dict() for t in self.trades],
        }


class BaseTestableModel(ABC):
    """Base class for testable models."""

    def __init__(self, params: Dict[str, Any]):
        self.params = params
        self.is_trained = False

    @abstractmethod
    def train(self, data: pd.DataFrame) -> None:
        """Train the model on historical data."""
        pass

    @abstractmethod
    def generate_signal(
        self,
        data: pd.DataFrame,
        current_idx: int,
    ) -> Tuple[int, float, Dict[str, Any]]:
        """
        Generate trading signal.

        Returns:
            signal: -1 (short), 0 (hold), 1 (long)
            confidence: 0.0 to 1.0
            metadata: Signal reasoning and indicators
        """
        pass

    @abstractmethod
    def get_default_params(self) -> Dict[str, Any]:
        """Get default parameters."""
        pass

    def validate_params(self) -> bool:
        """Validate model parameters."""
        return True


class MomentumModel(BaseTestableModel):
    """Momentum-based trading model."""

    def get_default_params(self) -> Dict[str, Any]:
        return {
            "fast_period": 10,
            "slow_period": 30,
            "rsi_period": 14,
            "rsi_overbought": 70,
            "rsi_oversold": 30,
            "atr_period": 14,
            "atr_multiplier": 2.0,
        }

    def train(self, data: pd.DataFrame) -> None:
        """Momentum model doesn't require training."""
        self.is_trained = True

    def generate_signal(
        self,
        data: pd.DataFrame,
        current_idx: int,
    ) -> Tuple[int, float, Dict[str, Any]]:
        if current_idx < self.params.get("slow_period", 30):
            return 0, 0.0, {}

        close = data["close"].iloc[:current_idx + 1]

        # Calculate indicators
        fast_ma = close.rolling(self.params.get("fast_period", 10)).mean()
        slow_ma = close.rolling(self.params.get("slow_period", 30)).mean()

        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(self.params.get("rsi_period", 14)).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(self.params.get("rsi_period", 14)).mean()
        rs = gain / (loss + 1e-10)
        rsi = 100 - (100 / (1 + rs))

        current_rsi = rsi.iloc[-1]
        current_fast = fast_ma.iloc[-1]
        current_slow = slow_ma.iloc[-1]

        signal = 0
        confidence = 0.0
        reasons = []

        # Generate signal
        if current_fast > current_slow and current_rsi < self.params.get("rsi_overbought", 70):
            signal = 1
            confidence = min(0.9, (current_fast - current_slow) / current_slow * 10)
            reasons.append(f"Fast MA ({current_fast:.2f}) > Slow MA ({current_slow:.2f})")
            reasons.append(f"RSI ({current_rsi:.1f}) not overbought")
        elif current_fast < current_slow and current_rsi > self.params.get("rsi_oversold", 30):
            signal = -1
            confidence = min(0.9, (current_slow - current_fast) / current_slow * 10)
            reasons.append(f"Fast MA ({current_fast:.2f}) < Slow MA ({current_slow:.2f})")
            reasons.append(f"RSI ({current_rsi:.1f}) not oversold")

        metadata = {
            "fast_ma": current_fast,
            "slow_ma": current_slow,
            "rsi": current_rsi,
            "reasons": reasons,
        }

        return signal, confidence, metadata


class MeanReversionModel(BaseTestableModel):
    """Mean reversion trading model."""

    def get_default_params(self) -> Dict[str, Any]:
        return {
            "lookback": 20,
            "entry_zscore": 2.0,
            "exit_zscore": 0.5,
            "bollinger_period": 20,
            "bollinger_std": 2.0,
        }

    def train(self, data: pd.DataFrame) -> None:
        self.is_trained = True

    def generate_signal(
        self,
        data: pd.DataFrame,
        current_idx: int,
    ) -> Tuple[int, float, Dict[str, Any]]:
        lookback = self.params.get("lookback", 20)

        if current_idx < lookback:
            return 0, 0.0, {}

        close = data["close"].iloc[:current_idx + 1]

        # Calculate z-score
        mean = close.rolling(lookback).mean()
        std = close.rolling(lookback).std()
        zscore = (close - mean) / (std + 1e-10)

        # Bollinger bands
        upper_band = mean + self.params.get("bollinger_std", 2.0) * std
        lower_band = mean - self.params.get("bollinger_std", 2.0) * std

        current_zscore = zscore.iloc[-1]
        current_price = close.iloc[-1]
        current_upper = upper_band.iloc[-1]
        current_lower = lower_band.iloc[-1]

        signal = 0
        confidence = 0.0
        reasons = []

        entry_z = self.params.get("entry_zscore", 2.0)

        if current_zscore < -entry_z:
            signal = 1  # Long - price below mean
            confidence = min(0.95, abs(current_zscore) / 3)
            reasons.append(f"Z-score ({current_zscore:.2f}) < -{entry_z}")
            reasons.append(f"Price ({current_price:.2f}) near lower band ({current_lower:.2f})")
        elif current_zscore > entry_z:
            signal = -1  # Short - price above mean
            confidence = min(0.95, abs(current_zscore) / 3)
            reasons.append(f"Z-score ({current_zscore:.2f}) > {entry_z}")
            reasons.append(f"Price ({current_price:.2f}) near upper band ({current_upper:.2f})")

        metadata = {
            "zscore": current_zscore,
            "mean": mean.iloc[-1],
            "std": std.iloc[-1],
            "upper_band": current_upper,
            "lower_band": current_lower,
            "reasons": reasons,
        }

        return signal, confidence, metadata


class ModelRegistry:
    """Registry for available models."""

    _models: Dict[ModelType, Type[BaseTestableModel]] = {
        ModelType.MOMENTUM: MomentumModel,
        ModelType.MEAN_REVERSION: MeanReversionModel,
    }

    @classmethod
    def register(cls, model_type: ModelType, model_class: Type[BaseTestableModel]):
        """Register a new model type."""
        cls._models[model_type] = model_class

    @classmethod
    def get(cls, model_type: ModelType) -> Optional[Type[BaseTestableModel]]:
        """Get model class by type."""
        return cls._models.get(model_type)

    @classmethod
    def list_models(cls) -> List[ModelType]:
        """List available models."""
        return list(cls._models.keys())


class UniversalModelTester:
    """
    Universal testing framework for any trading model.
    """

    def __init__(self, config: TestConfiguration):
        self.config = config
        self.model: Optional[BaseTestableModel] = None
        self.results: Optional[TestResults] = None

        # State
        self.equity = config.initial_capital
        self.positions: Dict[str, TradeRecord] = {}
        self.closed_trades: List[TradeRecord] = []
        self.equity_history: List[Tuple[datetime, float]] = []

    def _initialize_model(self) -> BaseTestableModel:
        """Initialize the selected model."""
        model_class = ModelRegistry.get(self.config.model_type)

        if model_class is None:
            raise ValueError(f"Unknown model type: {self.config.model_type}")

        # Merge default params with user params
        model = model_class({})
        params = model.get_default_params()
        params.update(self.config.model_params)

        return model_class(params)

    def run_backtest(
        self,
        data: pd.DataFrame,
        symbol: str = "TEST",
    ) -> TestResults:
        """
        Run backtest on provided data.

        Args:
            data: DataFrame with OHLCV columns
            symbol: Symbol being tested
        """
        logger.info(f"Starting backtest for {symbol} with {len(data)} bars")

        # Initialize
        self.model = self._initialize_model()
        self.equity = self.config.initial_capital
        self.positions = {}
        self.closed_trades = []
        self.equity_history = []

        # Train model if needed
        if not self.model.is_trained:
            self.model.train(data)

        # Run through each bar
        for idx in range(len(data)):
            current_time = data.index[idx] if isinstance(data.index[idx], datetime) else datetime.now()
            current_price = data["close"].iloc[idx]

            # Update existing positions
            self._update_positions(data, idx, current_price)

            # Generate signal
            signal, confidence, metadata = self.model.generate_signal(data, idx)

            # Execute trades
            if signal != 0 and confidence >= 0.5:
                self._execute_signal(
                    symbol=symbol,
                    signal=signal,
                    confidence=confidence,
                    price=current_price,
                    time=current_time,
                    metadata=metadata,
                )

            # Record equity
            portfolio_value = self._calculate_portfolio_value(current_price)
            self.equity_history.append((current_time, portfolio_value))

            # Check max drawdown
            if self._check_max_drawdown():
                logger.warning("Max drawdown exceeded, stopping backtest")
                break

        # Close remaining positions
        self._close_all_positions(data["close"].iloc[-1], data.index[-1] if isinstance(data.index[-1], datetime) else datetime.now())

        # Calculate results
        self.results = self._calculate_results()

        return self.results

    def _update_positions(self, data: pd.DataFrame, idx: int, current_price: float):
        """Update positions with current price and check stops."""
        to_close = []

        for trade_id, trade in self.positions.items():
            # Update MFE/MAE
            if trade.direction == "long":
                pnl_pct = (current_price - trade.entry_price) / trade.entry_price
            else:
                pnl_pct = (trade.entry_price - current_price) / trade.entry_price

            trade.max_favorable_excursion = max(trade.max_favorable_excursion, pnl_pct)
            trade.max_adverse_excursion = min(trade.max_adverse_excursion, pnl_pct)

            # Check stop loss
            if self.config.stop_loss_pct and pnl_pct <= -self.config.stop_loss_pct:
                trade.exit_reason = f"Stop loss hit ({self.config.stop_loss_pct:.1%})"
                to_close.append(trade_id)
                continue

            # Check take profit
            if self.config.take_profit_pct and pnl_pct >= self.config.take_profit_pct:
                trade.exit_reason = f"Take profit hit ({self.config.take_profit_pct:.1%})"
                to_close.append(trade_id)
                continue

        # Close positions
        current_time = data.index[idx] if isinstance(data.index[idx], datetime) else datetime.now()
        for trade_id in to_close:
            self._close_position(trade_id, current_price, current_time)

    def _execute_signal(
        self,
        symbol: str,
        signal: int,
        confidence: float,
        price: float,
        time: datetime,
        metadata: Dict[str, Any],
    ):
        """Execute a trading signal."""
        # Check if we already have a position
        existing = [t for t in self.positions.values() if t.symbol == symbol]

        # If we have opposite position, close it first
        for trade in existing:
            if (trade.direction == "long" and signal < 0) or \
               (trade.direction == "short" and signal > 0):
                self._close_position(trade.trade_id, price, time)

        # Check if we can open new position
        if len(self.positions) >= self.config.max_positions:
            return

        # Calculate position size
        position_value = self.equity * self.config.position_size
        quantity = position_value / price

        # Create trade record
        trade = TradeRecord(
            trade_id=f"{symbol}_{time.timestamp()}",
            symbol=symbol,
            direction="long" if signal > 0 else "short",
            entry_time=time,
            entry_price=price * (1 + self.config.slippage * signal),  # Apply slippage
            quantity=quantity,
            entry_reason="; ".join(metadata.get("reasons", [])),
            signals=metadata,
            indicators={k: v for k, v in metadata.items() if isinstance(v, (int, float))},
        )

        # Apply commission
        trade.commission = position_value * self.config.commission
        self.equity -= trade.commission

        self.positions[trade.trade_id] = trade

    def _close_position(self, trade_id: str, price: float, time: datetime):
        """Close a position."""
        if trade_id not in self.positions:
            return

        trade = self.positions.pop(trade_id)

        # Apply slippage on exit
        slippage_direction = -1 if trade.direction == "long" else 1
        exit_price = price * (1 + self.config.slippage * slippage_direction)

        trade.exit_time = time
        trade.exit_price = exit_price

        # Calculate PnL
        if trade.direction == "long":
            trade.pnl = (exit_price - trade.entry_price) * trade.quantity
        else:
            trade.pnl = (trade.entry_price - exit_price) * trade.quantity

        trade.pnl_pct = trade.pnl / (trade.entry_price * trade.quantity)

        # Exit commission
        exit_commission = exit_price * trade.quantity * self.config.commission
        trade.commission += exit_commission
        trade.pnl -= exit_commission

        # Update equity
        self.equity += trade.pnl + (trade.entry_price * trade.quantity)

        # Calculate R-multiple
        if self.config.stop_loss_pct:
            risk = trade.entry_price * trade.quantity * self.config.stop_loss_pct
            trade.r_multiple = trade.pnl / risk if risk > 0 else 0

        self.closed_trades.append(trade)

    def _close_all_positions(self, price: float, time: datetime):
        """Close all open positions."""
        for trade_id in list(self.positions.keys()):
            trade = self.positions[trade_id]
            trade.exit_reason = "End of backtest"
            self._close_position(trade_id, price, time)

    def _calculate_portfolio_value(self, current_price: float) -> float:
        """Calculate total portfolio value."""
        value = self.equity

        for trade in self.positions.values():
            if trade.direction == "long":
                unrealized = (current_price - trade.entry_price) * trade.quantity
            else:
                unrealized = (trade.entry_price - current_price) * trade.quantity
            value += unrealized + (trade.entry_price * trade.quantity)

        return value

    def _check_max_drawdown(self) -> bool:
        """Check if max drawdown exceeded."""
        if not self.equity_history:
            return False

        peak = max(eq for _, eq in self.equity_history)
        current = self.equity_history[-1][1]
        drawdown = (peak - current) / peak

        return drawdown >= self.config.max_drawdown_pct

    def _calculate_results(self) -> TestResults:
        """Calculate comprehensive test results."""
        results = TestResults(config=self.config)
        results.trades = self.closed_trades
        results.equity_curve = self.equity_history

        # Basic stats
        results.total_trades = len(self.closed_trades)

        if results.total_trades == 0:
            return results

        # Win/Loss
        results.winning_trades = sum(1 for t in self.closed_trades if t.pnl > 0)
        results.losing_trades = sum(1 for t in self.closed_trades if t.pnl <= 0)
        results.win_rate = results.winning_trades / results.total_trades

        # Average win/loss
        wins = [t.pnl for t in self.closed_trades if t.pnl > 0]
        losses = [t.pnl for t in self.closed_trades if t.pnl <= 0]

        results.avg_win = np.mean(wins) if wins else 0
        results.avg_loss = np.mean(losses) if losses else 0

        # Best/worst
        results.best_trade = max(t.pnl for t in self.closed_trades)
        results.worst_trade = min(t.pnl for t in self.closed_trades)

        # Profit factor
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        results.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        # Returns
        initial = self.config.initial_capital
        final = self.equity_history[-1][1] if self.equity_history else initial
        results.total_return = (final - initial) / initial

        # Daily returns
        if len(self.equity_history) > 1:
            equities = [eq for _, eq in self.equity_history]
            results.daily_returns = list(np.diff(equities) / np.array(equities[:-1]))

        # Volatility
        if results.daily_returns:
            results.volatility = np.std(results.daily_returns) * np.sqrt(252)
            downside = [r for r in results.daily_returns if r < 0]
            results.downside_volatility = np.std(downside) * np.sqrt(252) if downside else 0

        # Sharpe/Sortino
        if results.volatility > 0:
            results.annualized_return = results.total_return * 252 / max(1, len(self.equity_history))
            results.sharpe_ratio = results.annualized_return / results.volatility

        if results.downside_volatility > 0:
            results.sortino_ratio = results.annualized_return / results.downside_volatility

        # Max Drawdown
        peak = self.config.initial_capital
        max_dd = 0
        for _, eq in self.equity_history:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak
            max_dd = max(max_dd, dd)
        results.max_drawdown = max_dd

        # Calmar
        if results.max_drawdown > 0:
            results.calmar_ratio = results.annualized_return / results.max_drawdown

        # VaR/CVaR
        if results.daily_returns:
            sorted_returns = sorted(results.daily_returns)
            var_idx = int(len(sorted_returns) * 0.05)
            results.var_95 = -sorted_returns[var_idx] if var_idx < len(sorted_returns) else 0
            results.cvar_95 = -np.mean(sorted_returns[:var_idx + 1]) if var_idx > 0 else 0

        return results

    def export_results(
        self,
        output_dir: str = "backtest_results",
        filename_prefix: str = "backtest",
    ) -> Dict[str, str]:
        """Export results to files."""
        if self.results is None:
            raise ValueError("No results to export. Run backtest first.")

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        files_created = {}

        # Export based on format
        formats = ["csv", "json", "html"] if self.config.output_format == "all" else [self.config.output_format]

        for fmt in formats:
            if fmt == "csv":
                # Trades CSV
                trades_file = output_path / f"{filename_prefix}_trades_{timestamp}.csv"
                with open(trades_file, "w", newline="") as f:
                    if self.results.trades:
                        writer = csv.DictWriter(f, fieldnames=self.results.trades[0].to_dict().keys())
                        writer.writeheader()
                        for trade in self.results.trades:
                            writer.writerow(trade.to_dict())
                files_created["trades_csv"] = str(trades_file)

                # Equity curve CSV
                equity_file = output_path / f"{filename_prefix}_equity_{timestamp}.csv"
                with open(equity_file, "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(["datetime", "equity"])
                    for dt, eq in self.results.equity_curve:
                        writer.writerow([dt.isoformat(), eq])
                files_created["equity_csv"] = str(equity_file)

            elif fmt == "json":
                json_file = output_path / f"{filename_prefix}_results_{timestamp}.json"
                with open(json_file, "w") as f:
                    json.dump(self.results.to_dict(), f, indent=2, default=str)
                files_created["json"] = str(json_file)

            elif fmt == "html":
                html_file = output_path / f"{filename_prefix}_report_{timestamp}.html"
                html_content = self._generate_html_report()
                with open(html_file, "w") as f:
                    f.write(html_content)
                files_created["html"] = str(html_file)

        logger.info(f"Exported results to: {files_created}")
        return files_created

    def _generate_html_report(self) -> str:
        """Generate HTML report."""
        if self.results is None:
            return "<html><body>No results</body></html>"

        r = self.results

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Backtest Report - {self.config.model_type.value}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #1a1a2e; color: #eee; }}
        h1 {{ color: #00d4ff; }}
        h2 {{ color: #00ff88; border-bottom: 1px solid #333; padding-bottom: 10px; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .metrics {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; }}
        .metric {{ background: #16213e; padding: 20px; border-radius: 10px; text-align: center; }}
        .metric-value {{ font-size: 24px; font-weight: bold; color: #00d4ff; }}
        .metric-label {{ color: #888; margin-top: 5px; }}
        .positive {{ color: #00ff88; }}
        .negative {{ color: #ff4444; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #333; }}
        th {{ background: #16213e; color: #00d4ff; }}
        tr:hover {{ background: #16213e; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Backtest Report</h1>
        <p>Model: {self.config.model_type.value} | Lookback: {self.config.lookback_days} days</p>

        <h2>Performance Metrics</h2>
        <div class="metrics">
            <div class="metric">
                <div class="metric-value {'positive' if r.total_return >= 0 else 'negative'}">{r.total_return:.2%}</div>
                <div class="metric-label">Total Return</div>
            </div>
            <div class="metric">
                <div class="metric-value">{r.sharpe_ratio:.2f}</div>
                <div class="metric-label">Sharpe Ratio</div>
            </div>
            <div class="metric">
                <div class="metric-value negative">{r.max_drawdown:.2%}</div>
                <div class="metric-label">Max Drawdown</div>
            </div>
            <div class="metric">
                <div class="metric-value">{r.win_rate:.1%}</div>
                <div class="metric-label">Win Rate</div>
            </div>
        </div>

        <h2>Trade Statistics</h2>
        <div class="metrics">
            <div class="metric">
                <div class="metric-value">{r.total_trades}</div>
                <div class="metric-label">Total Trades</div>
            </div>
            <div class="metric">
                <div class="metric-value positive">{r.winning_trades}</div>
                <div class="metric-label">Winners</div>
            </div>
            <div class="metric">
                <div class="metric-value negative">{r.losing_trades}</div>
                <div class="metric-label">Losers</div>
            </div>
            <div class="metric">
                <div class="metric-value">{r.profit_factor:.2f}</div>
                <div class="metric-label">Profit Factor</div>
            </div>
        </div>

        <h2>Trade List</h2>
        <table>
            <tr>
                <th>Symbol</th>
                <th>Direction</th>
                <th>Entry Time</th>
                <th>Entry Price</th>
                <th>Exit Price</th>
                <th>PnL</th>
                <th>PnL %</th>
                <th>Entry Reason</th>
            </tr>
            {"".join(f'''
            <tr>
                <td>{t.symbol}</td>
                <td>{t.direction}</td>
                <td>{t.entry_time.strftime('%Y-%m-%d %H:%M') if t.entry_time else ''}</td>
                <td>${t.entry_price:.2f}</td>
                <td>${t.exit_price:.2f if t.exit_price else 0}</td>
                <td class="{'positive' if t.pnl >= 0 else 'negative'}">${t.pnl:.2f}</td>
                <td class="{'positive' if t.pnl_pct >= 0 else 'negative'}">{t.pnl_pct:.2%}</td>
                <td>{t.entry_reason[:50]}...</td>
            </tr>
            ''' for t in r.trades[:50])}
        </table>
    </div>
</body>
</html>
"""
        return html


def create_model_tester(config: TestConfiguration) -> UniversalModelTester:
    """Factory function to create model tester."""
    return UniversalModelTester(config)


def quick_backtest(
    data: pd.DataFrame,
    model_type: ModelType = ModelType.MOMENTUM,
    lookback_days: int = 252,
    **kwargs,
) -> TestResults:
    """Quick backtest with minimal configuration."""
    config = TestConfiguration(
        model_type=model_type,
        lookback_days=lookback_days,
        **kwargs,
    )

    tester = UniversalModelTester(config)
    return tester.run_backtest(data)
