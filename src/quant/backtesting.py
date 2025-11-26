"""
Revolution Alpha Engine - Backtesting Framework

Comprehensive backtesting infrastructure:
- Event-driven backtesting engine
- Walk-forward optimization
- Monte Carlo simulation of strategies
- Transaction cost modeling
- Slippage and market impact
- Position sizing algorithms
- Risk management rules
- Performance attribution
- Statistical significance testing
"""

import numpy as np
from scipy import stats
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Callable, Any
from enum import Enum
from abc import ABC, abstractmethod
from datetime import datetime
import warnings


# =============================================================================
# Data Classes and Enums
# =============================================================================

class OrderType(Enum):
    """Order types."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderSide(Enum):
    """Order side."""
    BUY = "buy"
    SELL = "sell"


class PositionType(Enum):
    """Position type."""
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


@dataclass
class Bar:
    """OHLCV bar data."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    symbol: str = "DEFAULT"


@dataclass
class Order:
    """Order representation."""
    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType = OrderType.MARKET
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    timestamp: Optional[datetime] = None
    filled: bool = False
    fill_price: Optional[float] = None
    fill_timestamp: Optional[datetime] = None
    commission: float = 0.0
    slippage: float = 0.0


@dataclass
class Position:
    """Position representation."""
    symbol: str
    quantity: float
    entry_price: float
    entry_time: datetime
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0

    @property
    def position_type(self) -> PositionType:
        if self.quantity > 0:
            return PositionType.LONG
        elif self.quantity < 0:
            return PositionType.SHORT
        return PositionType.FLAT

    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price


@dataclass
class Trade:
    """Completed trade."""
    trade_id: str
    symbol: str
    side: OrderSide
    quantity: float
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime
    pnl: float
    pnl_percent: float
    commission: float
    slippage: float
    holding_period: float  # In days


@dataclass
class BacktestResult:
    """Complete backtest results."""
    # Returns
    total_return: float
    annualized_return: float
    benchmark_return: Optional[float] = None

    # Risk metrics
    volatility: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_duration: int = 0

    # Trade statistics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    avg_holding_period: float = 0.0

    # Cost analysis
    total_commission: float = 0.0
    total_slippage: float = 0.0

    # Time series
    equity_curve: Optional[np.ndarray] = None
    returns: Optional[np.ndarray] = None
    drawdown_curve: Optional[np.ndarray] = None
    trades: Optional[List[Trade]] = None


@dataclass
class StrategyConfig:
    """Strategy configuration."""
    name: str
    initial_capital: float = 100000.0
    position_size: float = 0.1  # Fraction of equity
    max_positions: int = 10
    commission_rate: float = 0.001  # 0.1%
    slippage_rate: float = 0.0005  # 0.05%
    risk_per_trade: float = 0.02  # 2% risk per trade
    use_stop_loss: bool = True
    stop_loss_pct: float = 0.05  # 5% stop loss
    use_take_profit: bool = False
    take_profit_pct: float = 0.10  # 10% take profit


# =============================================================================
# Transaction Cost Models
# =============================================================================

class TransactionCostModel(ABC):
    """Base class for transaction cost models."""

    @abstractmethod
    def calculate_cost(
        self,
        price: float,
        quantity: float,
        side: OrderSide
    ) -> Tuple[float, float]:
        """
        Calculate transaction costs.

        Returns:
            Tuple of (commission, slippage)
        """
        pass


class SimpleTransactionCost(TransactionCostModel):
    """Simple percentage-based transaction costs."""

    def __init__(
        self,
        commission_rate: float = 0.001,
        slippage_rate: float = 0.0005
    ):
        self.commission_rate = commission_rate
        self.slippage_rate = slippage_rate

    def calculate_cost(
        self,
        price: float,
        quantity: float,
        side: OrderSide
    ) -> Tuple[float, float]:
        notional = abs(price * quantity)
        commission = notional * self.commission_rate
        slippage = notional * self.slippage_rate
        return commission, slippage


class TieredCommission(TransactionCostModel):
    """Tiered commission structure based on volume."""

    def __init__(
        self,
        tiers: List[Tuple[float, float]],  # (volume_threshold, rate)
        slippage_rate: float = 0.0005
    ):
        """
        Initialize tiered commission.

        Args:
            tiers: List of (volume_threshold, commission_rate)
                   e.g., [(10000, 0.001), (100000, 0.0008), (np.inf, 0.0005)]
        """
        self.tiers = sorted(tiers, key=lambda x: x[0])
        self.slippage_rate = slippage_rate

    def calculate_cost(
        self,
        price: float,
        quantity: float,
        side: OrderSide
    ) -> Tuple[float, float]:
        notional = abs(price * quantity)

        # Find applicable tier
        rate = self.tiers[-1][1]
        for threshold, tier_rate in self.tiers:
            if notional <= threshold:
                rate = tier_rate
                break

        commission = notional * rate
        slippage = notional * self.slippage_rate
        return commission, slippage


class MarketImpactModel(TransactionCostModel):
    """
    Market impact model based on participation rate.

    Impact = alpha * (volume / ADV)^beta * sigma
    """

    def __init__(
        self,
        alpha: float = 0.1,
        beta: float = 0.5,
        commission_rate: float = 0.001
    ):
        self.alpha = alpha
        self.beta = beta
        self.commission_rate = commission_rate
        self.adv_cache = {}  # symbol -> average daily volume
        self.volatility_cache = {}  # symbol -> volatility

    def set_market_data(
        self,
        symbol: str,
        adv: float,
        volatility: float
    ):
        """Set market data for impact calculation."""
        self.adv_cache[symbol] = adv
        self.volatility_cache[symbol] = volatility

    def calculate_cost(
        self,
        price: float,
        quantity: float,
        side: OrderSide,
        symbol: str = "DEFAULT"
    ) -> Tuple[float, float]:
        notional = abs(price * quantity)
        commission = notional * self.commission_rate

        # Market impact
        adv = self.adv_cache.get(symbol, 1e6)
        sigma = self.volatility_cache.get(symbol, 0.02)

        participation = abs(quantity * price) / adv
        impact = self.alpha * (participation ** self.beta) * sigma
        slippage = notional * impact

        return commission, slippage


# =============================================================================
# Position Sizing
# =============================================================================

class PositionSizer(ABC):
    """Base class for position sizing algorithms."""

    @abstractmethod
    def calculate_size(
        self,
        capital: float,
        price: float,
        signal_strength: float = 1.0,
        volatility: Optional[float] = None
    ) -> float:
        """Calculate position size in shares/contracts."""
        pass


class FixedFractionSizer(PositionSizer):
    """Fixed fraction of equity position sizing."""

    def __init__(self, fraction: float = 0.1):
        self.fraction = fraction

    def calculate_size(
        self,
        capital: float,
        price: float,
        signal_strength: float = 1.0,
        volatility: Optional[float] = None
    ) -> float:
        position_value = capital * self.fraction * signal_strength
        return position_value / price


class VolatilityTargetSizer(PositionSizer):
    """Position sizing targeting specific volatility contribution."""

    def __init__(
        self,
        target_volatility: float = 0.10,
        portfolio_volatility: float = 0.15
    ):
        self.target_vol = target_volatility
        self.port_vol = portfolio_volatility

    def calculate_size(
        self,
        capital: float,
        price: float,
        signal_strength: float = 1.0,
        volatility: Optional[float] = None
    ) -> float:
        if volatility is None or volatility < 0.001:
            volatility = self.port_vol

        # Target notional based on volatility
        target_notional = capital * (self.target_vol / volatility) * signal_strength
        return target_notional / price


class KellyCriterionSizer(PositionSizer):
    """Kelly criterion position sizing."""

    def __init__(
        self,
        win_rate: float = 0.55,
        win_loss_ratio: float = 1.5,
        kelly_fraction: float = 0.25  # Fractional Kelly
    ):
        self.win_rate = win_rate
        self.wl_ratio = win_loss_ratio
        self.kelly_fraction = kelly_fraction

    def calculate_size(
        self,
        capital: float,
        price: float,
        signal_strength: float = 1.0,
        volatility: Optional[float] = None
    ) -> float:
        # Full Kelly: f* = (p * b - q) / b
        # where p = win_rate, q = 1 - p, b = win/loss ratio
        p = self.win_rate
        q = 1 - p
        b = self.wl_ratio

        kelly = (p * b - q) / b
        kelly = max(0, kelly)  # No shorting based on Kelly

        # Apply fractional Kelly
        position_fraction = kelly * self.kelly_fraction * signal_strength

        position_value = capital * position_fraction
        return position_value / price


class RiskParitySizer(PositionSizer):
    """Equal risk contribution sizing."""

    def __init__(
        self,
        risk_budget: float = 0.02,  # 2% risk per position
        max_positions: int = 10
    ):
        self.risk_budget = risk_budget
        self.max_positions = max_positions

    def calculate_size(
        self,
        capital: float,
        price: float,
        signal_strength: float = 1.0,
        volatility: Optional[float] = None
    ) -> float:
        if volatility is None:
            volatility = 0.20  # Default assumption

        # Risk budget per position
        risk_per_position = self.risk_budget / self.max_positions

        # Position size to achieve target risk
        position_notional = (capital * risk_per_position) / volatility
        position_notional *= signal_strength

        return position_notional / price


# =============================================================================
# Strategy Base Class
# =============================================================================

class Strategy(ABC):
    """Base class for trading strategies."""

    def __init__(self, config: StrategyConfig):
        self.config = config
        self.positions: Dict[str, Position] = {}
        self.orders: List[Order] = []
        self.trades: List[Trade] = []
        self.equity = config.initial_capital
        self.cash = config.initial_capital

    @abstractmethod
    def on_bar(self, bar: Bar) -> Optional[Order]:
        """
        Process new bar data and generate orders.

        Args:
            bar: New OHLCV bar

        Returns:
            Optional order to execute
        """
        pass

    def on_fill(self, order: Order):
        """Handle order fill."""
        pass

    def on_trade_close(self, trade: Trade):
        """Handle trade closure."""
        pass

    def get_signal(self, bar: Bar) -> float:
        """
        Generate trading signal.

        Returns:
            Signal strength: positive for long, negative for short, 0 for flat
        """
        return 0.0


# =============================================================================
# Backtesting Engine
# =============================================================================

class BacktestEngine:
    """
    Event-driven backtesting engine.
    """

    def __init__(
        self,
        strategy: Strategy,
        transaction_costs: Optional[TransactionCostModel] = None,
        position_sizer: Optional[PositionSizer] = None
    ):
        """
        Initialize backtest engine.

        Args:
            strategy: Trading strategy to test
            transaction_costs: Transaction cost model
            position_sizer: Position sizing algorithm
        """
        self.strategy = strategy
        self.costs = transaction_costs or SimpleTransactionCost(
            strategy.config.commission_rate,
            strategy.config.slippage_rate
        )
        self.sizer = position_sizer or FixedFractionSizer(
            strategy.config.position_size
        )

        # State
        self.equity_curve = []
        self.returns = []
        self.timestamps = []
        self.order_id_counter = 0

    def run(
        self,
        bars: List[Bar],
        benchmark_returns: Optional[np.ndarray] = None
    ) -> BacktestResult:
        """
        Run backtest on historical data.

        Args:
            bars: List of OHLCV bars
            benchmark_returns: Optional benchmark returns for comparison

        Returns:
            BacktestResult with all metrics
        """
        self._reset()

        for bar in bars:
            # Update positions with current price
            self._update_positions(bar)

            # Record equity
            equity = self._calculate_equity()
            self.equity_curve.append(equity)
            self.timestamps.append(bar.timestamp)

            # Calculate return
            if len(self.equity_curve) > 1:
                ret = (self.equity_curve[-1] / self.equity_curve[-2]) - 1
                self.returns.append(ret)

            # Check stop loss / take profit
            self._check_risk_management(bar)

            # Generate and process orders
            order = self.strategy.on_bar(bar)
            if order is not None:
                self._process_order(order, bar)

        # Calculate results
        return self._calculate_results(benchmark_returns)

    def _reset(self):
        """Reset engine state."""
        self.strategy.equity = self.strategy.config.initial_capital
        self.strategy.cash = self.strategy.config.initial_capital
        self.strategy.positions = {}
        self.strategy.trades = []
        self.equity_curve = []
        self.returns = []
        self.timestamps = []
        self.order_id_counter = 0

    def _update_positions(self, bar: Bar):
        """Update position prices."""
        if bar.symbol in self.strategy.positions:
            pos = self.strategy.positions[bar.symbol]
            pos.current_price = bar.close
            pos.unrealized_pnl = (bar.close - pos.entry_price) * pos.quantity

    def _calculate_equity(self) -> float:
        """Calculate total equity."""
        position_value = sum(
            pos.market_value for pos in self.strategy.positions.values()
        )
        return self.strategy.cash + position_value

    def _check_risk_management(self, bar: Bar):
        """Check and execute risk management rules."""
        if bar.symbol not in self.strategy.positions:
            return

        pos = self.strategy.positions[bar.symbol]
        config = self.strategy.config

        # Stop loss
        if config.use_stop_loss:
            if pos.position_type == PositionType.LONG:
                stop_price = pos.entry_price * (1 - config.stop_loss_pct)
                if bar.low <= stop_price:
                    self._close_position(bar.symbol, bar, "stop_loss")
            elif pos.position_type == PositionType.SHORT:
                stop_price = pos.entry_price * (1 + config.stop_loss_pct)
                if bar.high >= stop_price:
                    self._close_position(bar.symbol, bar, "stop_loss")

        # Take profit
        if config.use_take_profit and bar.symbol in self.strategy.positions:
            pos = self.strategy.positions[bar.symbol]
            if pos.position_type == PositionType.LONG:
                target_price = pos.entry_price * (1 + config.take_profit_pct)
                if bar.high >= target_price:
                    self._close_position(bar.symbol, bar, "take_profit")
            elif pos.position_type == PositionType.SHORT:
                target_price = pos.entry_price * (1 - config.take_profit_pct)
                if bar.low <= target_price:
                    self._close_position(bar.symbol, bar, "take_profit")

    def _process_order(self, order: Order, bar: Bar):
        """Process and fill order."""
        # Simple market order fill at close
        if order.order_type == OrderType.MARKET:
            fill_price = bar.close

            # Calculate costs
            commission, slippage = self.costs.calculate_cost(
                fill_price, order.quantity, order.side
            )

            # Apply slippage
            if order.side == OrderSide.BUY:
                fill_price *= (1 + slippage / (fill_price * order.quantity))
            else:
                fill_price *= (1 - slippage / (fill_price * order.quantity))

            order.filled = True
            order.fill_price = fill_price
            order.fill_timestamp = bar.timestamp
            order.commission = commission
            order.slippage = slippage

            # Update position
            self._execute_fill(order, bar)

    def _execute_fill(self, order: Order, bar: Bar):
        """Execute order fill and update positions."""
        symbol = order.symbol
        quantity = order.quantity if order.side == OrderSide.BUY else -order.quantity

        if symbol in self.strategy.positions:
            pos = self.strategy.positions[symbol]
            old_quantity = pos.quantity

            # Check if closing position
            if (old_quantity > 0 and quantity < 0) or (old_quantity < 0 and quantity > 0):
                # Close or reduce position
                close_quantity = min(abs(old_quantity), abs(quantity))
                self._record_trade(pos, order, close_quantity)

                new_quantity = old_quantity + quantity
                if abs(new_quantity) < 1e-10:
                    del self.strategy.positions[symbol]
                else:
                    pos.quantity = new_quantity
            else:
                # Add to position
                total_cost = pos.entry_price * pos.quantity + order.fill_price * quantity
                pos.quantity += quantity
                pos.entry_price = total_cost / pos.quantity
        else:
            # New position
            self.strategy.positions[symbol] = Position(
                symbol=symbol,
                quantity=quantity,
                entry_price=order.fill_price,
                entry_time=bar.timestamp,
                current_price=order.fill_price
            )

        # Update cash
        trade_value = order.fill_price * abs(order.quantity)
        if order.side == OrderSide.BUY:
            self.strategy.cash -= trade_value + order.commission
        else:
            self.strategy.cash += trade_value - order.commission

    def _close_position(self, symbol: str, bar: Bar, reason: str):
        """Close position."""
        if symbol not in self.strategy.positions:
            return

        pos = self.strategy.positions[symbol]
        side = OrderSide.SELL if pos.quantity > 0 else OrderSide.BUY

        order = Order(
            order_id=self._next_order_id(),
            symbol=symbol,
            side=side,
            quantity=abs(pos.quantity),
            order_type=OrderType.MARKET
        )

        self._process_order(order, bar)

    def _record_trade(self, pos: Position, order: Order, quantity: float):
        """Record completed trade."""
        if pos.quantity > 0:
            pnl = (order.fill_price - pos.entry_price) * quantity
        else:
            pnl = (pos.entry_price - order.fill_price) * quantity

        pnl -= order.commission

        holding_period = (order.fill_timestamp - pos.entry_time).total_seconds() / 86400

        trade = Trade(
            trade_id=f"T{len(self.strategy.trades)+1}",
            symbol=pos.symbol,
            side=OrderSide.BUY if pos.quantity > 0 else OrderSide.SELL,
            quantity=quantity,
            entry_price=pos.entry_price,
            exit_price=order.fill_price,
            entry_time=pos.entry_time,
            exit_time=order.fill_timestamp,
            pnl=pnl,
            pnl_percent=pnl / (pos.entry_price * quantity),
            commission=order.commission,
            slippage=order.slippage,
            holding_period=holding_period
        )

        self.strategy.trades.append(trade)
        self.strategy.on_trade_close(trade)

    def _next_order_id(self) -> str:
        """Generate next order ID."""
        self.order_id_counter += 1
        return f"O{self.order_id_counter}"

    def _calculate_results(
        self,
        benchmark_returns: Optional[np.ndarray]
    ) -> BacktestResult:
        """Calculate backtest results."""
        equity = np.array(self.equity_curve)
        returns = np.array(self.returns) if self.returns else np.array([0])
        trades = self.strategy.trades

        # Returns
        total_return = (equity[-1] / equity[0]) - 1 if len(equity) > 0 else 0
        n_periods = len(returns)
        annualized_return = (1 + total_return) ** (252 / max(n_periods, 1)) - 1

        # Risk metrics
        volatility = np.std(returns) * np.sqrt(252) if len(returns) > 1 else 0
        rf_rate = 0.02 / 252  # Daily risk-free rate

        excess_returns = returns - rf_rate
        sharpe = (np.mean(excess_returns) / np.std(returns) * np.sqrt(252)
                 if np.std(returns) > 0 else 0)

        # Sortino (downside deviation)
        downside_returns = returns[returns < rf_rate]
        downside_std = np.std(downside_returns) if len(downside_returns) > 0 else 0.01
        sortino = np.mean(excess_returns) / downside_std * np.sqrt(252)

        # Drawdown
        cumulative = np.cumprod(1 + returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = np.min(drawdown)

        # Max drawdown duration
        dd_duration = 0
        current_duration = 0
        for dd in drawdown:
            if dd < 0:
                current_duration += 1
                dd_duration = max(dd_duration, current_duration)
            else:
                current_duration = 0

        # Calmar
        calmar = annualized_return / abs(max_drawdown) if max_drawdown != 0 else 0

        # Trade statistics
        n_trades = len(trades)
        if n_trades > 0:
            pnls = [t.pnl for t in trades]
            winning = [t for t in trades if t.pnl > 0]
            losing = [t for t in trades if t.pnl <= 0]

            win_rate = len(winning) / n_trades
            avg_win = np.mean([t.pnl for t in winning]) if winning else 0
            avg_loss = np.mean([t.pnl for t in losing]) if losing else 0

            gross_profit = sum(t.pnl for t in winning)
            gross_loss = abs(sum(t.pnl for t in losing))
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else np.inf

            largest_win = max(pnls) if pnls else 0
            largest_loss = min(pnls) if pnls else 0
            avg_holding = np.mean([t.holding_period for t in trades])

            total_commission = sum(t.commission for t in trades)
            total_slippage = sum(t.slippage for t in trades)
        else:
            win_rate = 0
            avg_win = avg_loss = 0
            profit_factor = 0
            largest_win = largest_loss = 0
            avg_holding = 0
            total_commission = total_slippage = 0

        return BacktestResult(
            total_return=total_return,
            annualized_return=annualized_return,
            benchmark_return=np.sum(benchmark_returns) if benchmark_returns is not None else None,
            volatility=volatility,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            max_drawdown=max_drawdown,
            max_drawdown_duration=dd_duration,
            total_trades=n_trades,
            winning_trades=len([t for t in trades if t.pnl > 0]),
            losing_trades=len([t for t in trades if t.pnl <= 0]),
            win_rate=win_rate,
            profit_factor=profit_factor,
            avg_win=avg_win,
            avg_loss=avg_loss,
            largest_win=largest_win,
            largest_loss=largest_loss,
            avg_holding_period=avg_holding,
            total_commission=total_commission,
            total_slippage=total_slippage,
            equity_curve=equity,
            returns=returns,
            drawdown_curve=drawdown,
            trades=trades
        )


# =============================================================================
# Walk-Forward Optimization
# =============================================================================

class WalkForwardOptimizer:
    """
    Walk-forward analysis for strategy optimization.
    """

    def __init__(
        self,
        strategy_factory: Callable[[Dict], Strategy],
        parameter_space: Dict[str, List],
        in_sample_periods: int = 252,
        out_sample_periods: int = 63,
        n_splits: int = 4
    ):
        """
        Initialize walk-forward optimizer.

        Args:
            strategy_factory: Function that creates strategy from parameters
            parameter_space: Parameter grid to search
            in_sample_periods: In-sample period length (bars)
            out_sample_periods: Out-of-sample period length
            n_splits: Number of walk-forward splits
        """
        self.strategy_factory = strategy_factory
        self.param_space = parameter_space
        self.is_periods = in_sample_periods
        self.oos_periods = out_sample_periods
        self.n_splits = n_splits

    def optimize(
        self,
        bars: List[Bar],
        metric: str = "sharpe_ratio"
    ) -> Tuple[Dict, List[BacktestResult]]:
        """
        Run walk-forward optimization.

        Args:
            bars: Full bar history
            metric: Optimization metric

        Returns:
            Tuple of (best_params, out_of_sample_results)
        """
        total_len = len(bars)
        split_size = self.is_periods + self.oos_periods

        if total_len < split_size:
            raise ValueError("Not enough data for walk-forward analysis")

        oos_results = []
        all_best_params = []

        for split in range(self.n_splits):
            start_idx = split * self.oos_periods
            is_end = start_idx + self.is_periods
            oos_end = is_end + self.oos_periods

            if oos_end > total_len:
                break

            is_bars = bars[start_idx:is_end]
            oos_bars = bars[is_end:oos_end]

            # Optimize on in-sample
            best_params, _ = self._grid_search(is_bars, metric)
            all_best_params.append(best_params)

            # Test on out-of-sample
            strategy = self.strategy_factory(best_params)
            engine = BacktestEngine(strategy)
            result = engine.run(oos_bars)
            oos_results.append(result)

        # Aggregate best parameters
        final_params = self._aggregate_params(all_best_params)

        return final_params, oos_results

    def _grid_search(
        self,
        bars: List[Bar],
        metric: str
    ) -> Tuple[Dict, float]:
        """Run grid search on parameter space."""
        best_params = None
        best_value = -np.inf

        # Generate parameter combinations
        param_names = list(self.param_space.keys())
        param_values = list(self.param_space.values())

        from itertools import product
        for combination in product(*param_values):
            params = dict(zip(param_names, combination))

            try:
                strategy = self.strategy_factory(params)
                engine = BacktestEngine(strategy)
                result = engine.run(bars)

                value = getattr(result, metric)
                if value > best_value:
                    best_value = value
                    best_params = params
            except Exception:
                continue

        return best_params or {}, best_value

    def _aggregate_params(self, params_list: List[Dict]) -> Dict:
        """Aggregate parameters across splits."""
        if not params_list:
            return {}

        # Use mode for each parameter
        aggregated = {}
        for key in params_list[0].keys():
            values = [p[key] for p in params_list]
            if isinstance(values[0], (int, float)):
                aggregated[key] = np.median(values)
            else:
                # Mode for categorical
                aggregated[key] = max(set(values), key=values.count)

        return aggregated


# =============================================================================
# Monte Carlo Simulation
# =============================================================================

class MonteCarloBacktest:
    """
    Monte Carlo simulation for strategy robustness testing.
    """

    def __init__(self, base_result: BacktestResult):
        """
        Initialize Monte Carlo backtester.

        Args:
            base_result: Results from initial backtest
        """
        self.base_result = base_result

    def bootstrap_returns(
        self,
        n_simulations: int = 1000,
        confidence: float = 0.95
    ) -> Dict:
        """
        Bootstrap returns to estimate confidence intervals.

        Args:
            n_simulations: Number of bootstrap samples
            confidence: Confidence level

        Returns:
            Dictionary with confidence intervals for key metrics
        """
        returns = self.base_result.returns
        n = len(returns)

        bootstrap_metrics = {
            'total_return': [],
            'sharpe_ratio': [],
            'max_drawdown': [],
            'volatility': []
        }

        for _ in range(n_simulations):
            # Resample with replacement
            sample_idx = np.random.choice(n, size=n, replace=True)
            sample_returns = returns[sample_idx]

            # Calculate metrics
            total_ret = np.prod(1 + sample_returns) - 1
            vol = np.std(sample_returns) * np.sqrt(252)
            sharpe = np.mean(sample_returns) / np.std(sample_returns) * np.sqrt(252) if np.std(sample_returns) > 0 else 0

            cumulative = np.cumprod(1 + sample_returns)
            running_max = np.maximum.accumulate(cumulative)
            max_dd = np.min((cumulative - running_max) / running_max)

            bootstrap_metrics['total_return'].append(total_ret)
            bootstrap_metrics['sharpe_ratio'].append(sharpe)
            bootstrap_metrics['max_drawdown'].append(max_dd)
            bootstrap_metrics['volatility'].append(vol)

        # Calculate confidence intervals
        alpha = 1 - confidence
        results = {}

        for metric, values in bootstrap_metrics.items():
            values = np.array(values)
            results[metric] = {
                'mean': np.mean(values),
                'std': np.std(values),
                'lower': np.percentile(values, alpha/2 * 100),
                'upper': np.percentile(values, (1 - alpha/2) * 100),
                'median': np.median(values)
            }

        return results

    def shuffle_trades(
        self,
        n_simulations: int = 1000
    ) -> Dict:
        """
        Shuffle trade sequence to test path dependency.

        Returns:
            Distribution of equity curves from shuffled trades
        """
        trades = self.base_result.trades
        if not trades:
            return {}

        final_equities = []
        trade_pnls = [t.pnl for t in trades]

        for _ in range(n_simulations):
            shuffled_pnls = np.random.permutation(trade_pnls)
            equity = self.base_result.equity_curve[0]
            for pnl in shuffled_pnls:
                equity += pnl
            final_equities.append(equity)

        return {
            'mean_final_equity': np.mean(final_equities),
            'std_final_equity': np.std(final_equities),
            'percentile_5': np.percentile(final_equities, 5),
            'percentile_95': np.percentile(final_equities, 95),
            'worst_case': np.min(final_equities),
            'best_case': np.max(final_equities)
        }


# =============================================================================
# Statistical Significance Testing
# =============================================================================

class SignificanceTester:
    """
    Test statistical significance of strategy performance.
    """

    @staticmethod
    def sharpe_ratio_test(
        returns: np.ndarray,
        null_sharpe: float = 0.0,
        confidence: float = 0.95
    ) -> Dict:
        """
        Test if Sharpe ratio is significantly different from null.

        Uses Lo (2002) adjustment for autocorrelation.
        """
        n = len(returns)
        sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252)

        # Standard error (assuming IID)
        se_iid = np.sqrt((1 + 0.5 * sharpe**2) / n) * np.sqrt(252)

        # Adjust for autocorrelation (Newey-West style)
        max_lag = min(int(np.sqrt(n)), 10)
        autocov_adj = 0
        for lag in range(1, max_lag + 1):
            weight = 1 - lag / (max_lag + 1)
            autocov = np.corrcoef(returns[:-lag], returns[lag:])[0, 1]
            autocov_adj += 2 * weight * autocov

        se_adjusted = se_iid * np.sqrt(1 + autocov_adj)

        # t-statistic
        t_stat = (sharpe - null_sharpe) / se_adjusted
        p_value = 2 * (1 - stats.t.cdf(abs(t_stat), n - 1))

        z_crit = stats.norm.ppf(1 - (1 - confidence) / 2)
        ci_lower = sharpe - z_crit * se_adjusted
        ci_upper = sharpe + z_crit * se_adjusted

        return {
            'sharpe_ratio': sharpe,
            'standard_error': se_adjusted,
            't_statistic': t_stat,
            'p_value': p_value,
            'significant': p_value < (1 - confidence),
            'confidence_interval': (ci_lower, ci_upper)
        }

    @staticmethod
    def performance_persistence_test(
        returns: np.ndarray,
        split_point: float = 0.5
    ) -> Dict:
        """
        Test if performance persists across time periods.
        """
        n = len(returns)
        split_idx = int(n * split_point)

        returns_1 = returns[:split_idx]
        returns_2 = returns[split_idx:]

        sharpe_1 = np.mean(returns_1) / np.std(returns_1) * np.sqrt(252)
        sharpe_2 = np.mean(returns_2) / np.std(returns_2) * np.sqrt(252)

        # Test for difference
        mean_diff = np.mean(returns_1) - np.mean(returns_2)
        pooled_std = np.sqrt(np.var(returns_1)/len(returns_1) + np.var(returns_2)/len(returns_2))
        t_stat = mean_diff / pooled_std
        p_value = 2 * (1 - stats.t.cdf(abs(t_stat), n - 2))

        return {
            'sharpe_first_half': sharpe_1,
            'sharpe_second_half': sharpe_2,
            'sharpe_difference': sharpe_1 - sharpe_2,
            't_statistic': t_stat,
            'p_value': p_value,
            'consistent': p_value > 0.05  # Not significantly different
        }


# =============================================================================
# Factory Functions
# =============================================================================

def create_backtest_engine(
    strategy: Strategy,
    commission_rate: float = 0.001,
    slippage_rate: float = 0.0005
) -> BacktestEngine:
    """Create backtest engine with transaction costs."""
    costs = SimpleTransactionCost(commission_rate, slippage_rate)
    return BacktestEngine(strategy, costs)


def create_walk_forward_optimizer(
    strategy_factory: Callable,
    parameter_space: Dict,
    is_periods: int = 252,
    oos_periods: int = 63
) -> WalkForwardOptimizer:
    """Create walk-forward optimizer."""
    return WalkForwardOptimizer(
        strategy_factory,
        parameter_space,
        is_periods,
        oos_periods
    )


def run_quick_backtest(
    strategy: Strategy,
    bars: List[Bar]
) -> BacktestResult:
    """Quick backtest with default settings."""
    engine = BacktestEngine(strategy)
    return engine.run(bars)
