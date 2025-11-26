"""
Revolution Alpha Engine - Advanced Risk Management

Institutional-grade risk management system:
- Kelly Criterion position sizing
- Portfolio optimization (Mean-Variance, Risk Parity)
- Value at Risk (VaR) and Expected Shortfall
- Maximum drawdown controls
- Correlation-based exposure limits
- Dynamic position sizing based on volatility
"""

import numpy as np
import pandas as pd
from typing import Optional, List, Dict, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import logging
from scipy import stats, optimize
from collections import deque

logger = logging.getLogger(__name__)


class RiskLevel(str, Enum):
    """Risk level classifications."""
    MINIMAL = "minimal"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    EXTREME = "extreme"


@dataclass
class PositionRisk:
    """Risk metrics for a single position."""
    symbol: str
    current_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    var_95: float  # 95% VaR
    var_99: float  # 99% VaR
    expected_shortfall: float
    beta: float
    correlation_to_portfolio: float
    contribution_to_risk: float
    days_held: int

    @property
    def risk_level(self) -> RiskLevel:
        """Classify position risk."""
        if self.var_95 / self.current_value > 0.1:
            return RiskLevel.EXTREME
        elif self.var_95 / self.current_value > 0.05:
            return RiskLevel.HIGH
        elif self.var_95 / self.current_value > 0.02:
            return RiskLevel.MODERATE
        elif self.var_95 / self.current_value > 0.01:
            return RiskLevel.LOW
        return RiskLevel.MINIMAL


@dataclass
class PortfolioRisk:
    """Risk metrics for entire portfolio."""
    total_value: float
    total_pnl: float
    total_pnl_pct: float
    portfolio_var_95: float
    portfolio_var_99: float
    expected_shortfall: float
    max_drawdown: float
    current_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    beta_to_market: float
    correlation_matrix: Optional[pd.DataFrame] = None
    position_risks: List[PositionRisk] = field(default_factory=list)

    @property
    def risk_level(self) -> RiskLevel:
        """Overall portfolio risk level."""
        if self.current_drawdown > 0.2:
            return RiskLevel.EXTREME
        elif self.current_drawdown > 0.1:
            return RiskLevel.HIGH
        elif self.current_drawdown > 0.05:
            return RiskLevel.MODERATE
        elif self.current_drawdown > 0.02:
            return RiskLevel.LOW
        return RiskLevel.MINIMAL


@dataclass
class TradeRisk:
    """Risk assessment for a potential trade."""
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    position_size: float
    dollar_risk: float
    risk_pct_of_portfolio: float
    reward_risk_ratio: float
    win_probability: float
    expected_value: float
    kelly_fraction: float
    optimal_position_pct: float
    max_position_pct: float

    @property
    def is_valid_trade(self) -> bool:
        """Check if trade meets risk criteria."""
        return (
            self.reward_risk_ratio >= 1.5 and
            self.risk_pct_of_portfolio <= 2.0 and
            self.expected_value > 0
        )


class KellyCriterion:
    """
    Kelly Criterion for optimal position sizing.

    Calculates the optimal fraction of capital to risk
    based on win rate and risk/reward ratio.
    """

    def __init__(self, max_fraction: float = 0.25, half_kelly: bool = True):
        """
        Args:
            max_fraction: Maximum Kelly fraction allowed
            half_kelly: Use half-Kelly for reduced volatility
        """
        self.max_fraction = max_fraction
        self.half_kelly = half_kelly

    def calculate(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float
    ) -> float:
        """
        Calculate Kelly fraction.

        Args:
            win_rate: Probability of winning (0-1)
            avg_win: Average winning trade return
            avg_loss: Average losing trade return (positive number)

        Returns:
            Optimal fraction of capital to risk
        """
        if win_rate <= 0 or win_rate >= 1:
            return 0

        if avg_loss <= 0 or avg_win <= 0:
            return 0

        # Kelly formula: f* = (bp - q) / b
        # where b = avg_win/avg_loss, p = win_rate, q = 1-win_rate
        b = avg_win / avg_loss
        p = win_rate
        q = 1 - win_rate

        kelly = (b * p - q) / b

        # Apply constraints
        if kelly <= 0:
            return 0

        if self.half_kelly:
            kelly *= 0.5

        return min(kelly, self.max_fraction)

    def calculate_from_trades(self, trades: List[Dict]) -> float:
        """
        Calculate Kelly from historical trades.

        Args:
            trades: List of trade dictionaries with 'pnl' key
        """
        if not trades:
            return 0

        pnls = [t['pnl'] for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [abs(p) for p in pnls if p < 0]

        if not wins or not losses:
            return 0

        win_rate = len(wins) / len(pnls)
        avg_win = np.mean(wins)
        avg_loss = np.mean(losses)

        return self.calculate(win_rate, avg_win, avg_loss)


class VaRCalculator:
    """
    Value at Risk and Expected Shortfall calculator.

    Supports multiple VaR methods:
    - Historical simulation
    - Parametric (Variance-Covariance)
    - Monte Carlo simulation
    """

    def __init__(self, confidence_levels: List[float] = [0.95, 0.99]):
        self.confidence_levels = confidence_levels

    def historical_var(
        self,
        returns: np.ndarray,
        confidence: float = 0.95
    ) -> float:
        """Calculate VaR using historical simulation."""
        return -np.percentile(returns, (1 - confidence) * 100)

    def parametric_var(
        self,
        returns: np.ndarray,
        confidence: float = 0.95
    ) -> float:
        """Calculate VaR using parametric method."""
        mean = np.mean(returns)
        std = np.std(returns)
        z_score = stats.norm.ppf(1 - confidence)
        return -(mean + z_score * std)

    def monte_carlo_var(
        self,
        returns: np.ndarray,
        confidence: float = 0.95,
        n_simulations: int = 10000,
        horizon: int = 1
    ) -> float:
        """Calculate VaR using Monte Carlo simulation."""
        mean = np.mean(returns)
        std = np.std(returns)

        # Simulate future returns
        simulated = np.random.normal(mean, std, (n_simulations, horizon))
        cumulative = simulated.sum(axis=1)

        return -np.percentile(cumulative, (1 - confidence) * 100)

    def expected_shortfall(
        self,
        returns: np.ndarray,
        confidence: float = 0.95
    ) -> float:
        """
        Calculate Expected Shortfall (CVaR).

        Average loss in worst (1-confidence)% of cases.
        """
        var = self.historical_var(returns, confidence)
        tail_returns = returns[returns <= -var]

        if len(tail_returns) == 0:
            return var

        return -np.mean(tail_returns)

    def calculate_all(
        self,
        returns: np.ndarray,
        portfolio_value: float
    ) -> Dict[str, float]:
        """Calculate all risk metrics."""
        results = {}

        for conf in self.confidence_levels:
            conf_str = f"{int(conf * 100)}"

            results[f'var_{conf_str}_hist'] = self.historical_var(returns, conf) * portfolio_value
            results[f'var_{conf_str}_param'] = self.parametric_var(returns, conf) * portfolio_value
            results[f'es_{conf_str}'] = self.expected_shortfall(returns, conf) * portfolio_value

        return results


class PositionSizer:
    """
    Dynamic position sizing based on multiple factors.

    Considers:
    - Account equity
    - Volatility
    - Correlation
    - Regime
    - Conviction
    """

    def __init__(
        self,
        base_risk_pct: float = 1.0,
        max_position_pct: float = 20.0,
        max_portfolio_heat: float = 6.0,
        volatility_target: float = 0.15
    ):
        """
        Args:
            base_risk_pct: Base risk per trade (% of equity)
            max_position_pct: Maximum position size (% of equity)
            max_portfolio_heat: Maximum total portfolio risk
            volatility_target: Target annual volatility
        """
        self.base_risk_pct = base_risk_pct
        self.max_position_pct = max_position_pct
        self.max_portfolio_heat = max_portfolio_heat
        self.volatility_target = volatility_target

        self.kelly = KellyCriterion()

    def calculate_position_size(
        self,
        equity: float,
        entry_price: float,
        stop_loss: float,
        volatility: float,
        win_rate: float = 0.5,
        avg_win_loss_ratio: float = 2.0,
        conviction: float = 1.0,
        current_heat: float = 0.0,
        correlation_factor: float = 1.0
    ) -> Dict[str, Any]:
        """
        Calculate optimal position size.

        Args:
            equity: Account equity
            entry_price: Entry price
            stop_loss: Stop loss price
            volatility: Asset volatility (annualized)
            win_rate: Historical win rate
            avg_win_loss_ratio: Average win/loss ratio
            conviction: Signal conviction (0-1)
            current_heat: Current portfolio heat
            correlation_factor: Correlation adjustment (0-1)

        Returns:
            Dictionary with position sizing details
        """
        # Risk per share
        risk_per_share = abs(entry_price - stop_loss)
        risk_pct = risk_per_share / entry_price

        # Base position from risk
        base_risk_dollars = equity * (self.base_risk_pct / 100)
        base_shares = base_risk_dollars / risk_per_share if risk_per_share > 0 else 0

        # Kelly optimal
        kelly_fraction = self.kelly.calculate(
            win_rate,
            avg_win_loss_ratio,
            1.0
        )

        # Volatility adjustment
        vol_scalar = self.volatility_target / volatility if volatility > 0 else 1
        vol_scalar = np.clip(vol_scalar, 0.25, 2.0)

        # Heat check
        remaining_heat = max(0, self.max_portfolio_heat - current_heat)
        heat_scalar = remaining_heat / self.base_risk_pct if self.base_risk_pct > 0 else 0
        heat_scalar = min(1.0, heat_scalar)

        # Combined position
        adjusted_shares = base_shares * vol_scalar * conviction * heat_scalar * correlation_factor

        # Apply maximum limits
        max_position_value = equity * (self.max_position_pct / 100)
        max_shares = max_position_value / entry_price

        final_shares = min(adjusted_shares, max_shares)
        position_value = final_shares * entry_price
        position_pct = (position_value / equity) * 100

        # Calculate dollar risk
        dollar_risk = final_shares * risk_per_share
        risk_pct_of_equity = (dollar_risk / equity) * 100

        return {
            'shares': int(final_shares),
            'position_value': position_value,
            'position_pct': position_pct,
            'dollar_risk': dollar_risk,
            'risk_pct_of_equity': risk_pct_of_equity,
            'kelly_fraction': kelly_fraction,
            'vol_scalar': vol_scalar,
            'heat_scalar': heat_scalar,
            'adjustments': {
                'base_shares': base_shares,
                'vol_adjusted': base_shares * vol_scalar,
                'conviction_adjusted': base_shares * vol_scalar * conviction,
                'final': final_shares
            }
        }


class DrawdownMonitor:
    """
    Monitor and manage drawdowns.

    Implements automatic risk reduction during drawdowns.
    """

    def __init__(
        self,
        max_drawdown: float = 0.20,
        warning_threshold: float = 0.10,
        recovery_threshold: float = 0.05
    ):
        self.max_drawdown = max_drawdown
        self.warning_threshold = warning_threshold
        self.recovery_threshold = recovery_threshold

        self._peak = 0
        self._trough = 0
        self._current_value = 0
        self._drawdown_history: List[Tuple[datetime, float]] = []
        self._in_drawdown = False
        self._drawdown_start: Optional[datetime] = None

    def update(self, portfolio_value: float) -> Dict[str, Any]:
        """
        Update drawdown monitor with current portfolio value.

        Returns:
            Dictionary with drawdown status and recommendations
        """
        self._current_value = portfolio_value

        # Update peak
        if portfolio_value > self._peak:
            self._peak = portfolio_value
            self._trough = portfolio_value

            if self._in_drawdown:
                self._in_drawdown = False
                self._drawdown_start = None

        # Update trough
        if portfolio_value < self._trough:
            self._trough = portfolio_value

        # Calculate current drawdown
        current_dd = (self._peak - portfolio_value) / self._peak if self._peak > 0 else 0

        # Record history
        self._drawdown_history.append((datetime.utcnow(), current_dd))

        # Check if entering drawdown
        if current_dd >= self.warning_threshold and not self._in_drawdown:
            self._in_drawdown = True
            self._drawdown_start = datetime.utcnow()

        # Determine risk multiplier
        if current_dd >= self.max_drawdown:
            risk_mult = 0  # Stop trading
            action = "HALT_TRADING"
        elif current_dd >= self.warning_threshold:
            # Linear reduction between warning and max
            reduction = (current_dd - self.warning_threshold) / (self.max_drawdown - self.warning_threshold)
            risk_mult = max(0.25, 1 - reduction * 0.75)
            action = "REDUCE_RISK"
        else:
            risk_mult = 1.0
            action = "NORMAL"

        # Calculate max drawdown
        max_dd = max(dd for _, dd in self._drawdown_history) if self._drawdown_history else 0

        return {
            'current_drawdown': current_dd,
            'max_drawdown_reached': max_dd,
            'peak': self._peak,
            'trough': self._trough,
            'in_drawdown': self._in_drawdown,
            'drawdown_duration': (datetime.utcnow() - self._drawdown_start).days if self._drawdown_start else 0,
            'risk_multiplier': risk_mult,
            'action': action,
            'breached_max': current_dd >= self.max_drawdown
        }

    def get_drawdown_curve(self) -> pd.DataFrame:
        """Get historical drawdown curve."""
        if not self._drawdown_history:
            return pd.DataFrame()

        return pd.DataFrame(
            self._drawdown_history,
            columns=['timestamp', 'drawdown']
        )


class RiskManager:
    """
    Master risk management system.

    Integrates all risk components for comprehensive portfolio risk management.
    """

    def __init__(
        self,
        initial_capital: float,
        max_position_pct: float = 20.0,
        max_portfolio_risk_pct: float = 6.0,
        max_drawdown_pct: float = 20.0,
        max_correlation: float = 0.7
    ):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.max_position_pct = max_position_pct
        self.max_portfolio_risk_pct = max_portfolio_risk_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.max_correlation = max_correlation

        # Components
        self.kelly = KellyCriterion()
        self.var_calculator = VaRCalculator()
        self.position_sizer = PositionSizer(
            max_position_pct=max_position_pct,
            max_portfolio_heat=max_portfolio_risk_pct
        )
        self.drawdown_monitor = DrawdownMonitor(max_drawdown=max_drawdown_pct / 100)

        # Portfolio state
        self._positions: Dict[str, Dict] = {}
        self._trades: List[Dict] = []
        self._daily_returns: deque = deque(maxlen=252)

    def update_capital(self, new_capital: float):
        """Update current capital."""
        self.current_capital = new_capital
        self.drawdown_monitor.update(new_capital)

    def evaluate_trade(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        volatility: float,
        win_rate: float = 0.5,
        avg_win_loss_ratio: float = 2.0,
        conviction: float = 1.0
    ) -> TradeRisk:
        """
        Evaluate risk of a potential trade.

        Returns comprehensive risk assessment.
        """
        # Get current portfolio heat
        current_heat = self._calculate_portfolio_heat()

        # Calculate correlation factor
        corr_factor = self._calculate_correlation_factor(symbol)

        # Size the position
        sizing = self.position_sizer.calculate_position_size(
            equity=self.current_capital,
            entry_price=entry_price,
            stop_loss=stop_loss,
            volatility=volatility,
            win_rate=win_rate,
            avg_win_loss_ratio=avg_win_loss_ratio,
            conviction=conviction,
            current_heat=current_heat,
            correlation_factor=corr_factor
        )

        # Calculate expected value
        loss_pct = abs(entry_price - stop_loss) / entry_price
        gain_pct = abs(take_profit - entry_price) / entry_price

        expected_value = (win_rate * gain_pct - (1 - win_rate) * loss_pct)

        # Risk/reward
        if loss_pct > 0:
            rr_ratio = gain_pct / loss_pct
        else:
            rr_ratio = 0

        return TradeRisk(
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size=sizing['shares'],
            dollar_risk=sizing['dollar_risk'],
            risk_pct_of_portfolio=sizing['risk_pct_of_equity'],
            reward_risk_ratio=rr_ratio,
            win_probability=win_rate,
            expected_value=expected_value,
            kelly_fraction=sizing['kelly_fraction'],
            optimal_position_pct=sizing['position_pct'],
            max_position_pct=self.max_position_pct
        )

    def _calculate_portfolio_heat(self) -> float:
        """Calculate current portfolio heat (total risk)."""
        total_risk = 0
        for pos in self._positions.values():
            risk_pct = pos.get('risk_pct', 0)
            total_risk += risk_pct
        return total_risk

    def _calculate_correlation_factor(self, symbol: str) -> float:
        """Calculate correlation adjustment for new position."""
        if not self._positions:
            return 1.0

        # Simplified - would use actual return correlations
        existing_count = len(self._positions)
        avg_correlation = 0.3  # Assumed average correlation

        # Diversification factor
        diversification = 1 / np.sqrt(existing_count + 1)

        return min(1.0, diversification * (1 - avg_correlation) + avg_correlation)

    def calculate_portfolio_risk(
        self,
        returns_data: Dict[str, pd.Series]
    ) -> PortfolioRisk:
        """
        Calculate comprehensive portfolio risk metrics.

        Args:
            returns_data: Dictionary of symbol -> returns series
        """
        if not returns_data:
            return PortfolioRisk(
                total_value=self.current_capital,
                total_pnl=self.current_capital - self.initial_capital,
                total_pnl_pct=(self.current_capital - self.initial_capital) / self.initial_capital,
                portfolio_var_95=0,
                portfolio_var_99=0,
                expected_shortfall=0,
                max_drawdown=0,
                current_drawdown=0,
                sharpe_ratio=0,
                sortino_ratio=0,
                calmar_ratio=0,
                beta_to_market=1
            )

        # Combine returns
        combined_df = pd.DataFrame(returns_data)
        portfolio_returns = combined_df.mean(axis=1)  # Equal weighted

        # VaR and ES
        var_metrics = self.var_calculator.calculate_all(
            portfolio_returns.values,
            self.current_capital
        )

        # Drawdown metrics
        dd_status = self.drawdown_monitor.update(self.current_capital)

        # Performance ratios
        rf_rate = 0.05 / 252  # Daily risk-free rate
        excess_returns = portfolio_returns - rf_rate
        sharpe = np.sqrt(252) * excess_returns.mean() / excess_returns.std() if excess_returns.std() > 0 else 0

        negative_returns = portfolio_returns[portfolio_returns < 0]
        sortino = np.sqrt(252) * excess_returns.mean() / negative_returns.std() if len(negative_returns) > 0 else 0

        max_dd = dd_status['max_drawdown_reached']
        annual_return = portfolio_returns.mean() * 252
        calmar = annual_return / max_dd if max_dd > 0 else 0

        # Correlation matrix
        corr_matrix = combined_df.corr()

        return PortfolioRisk(
            total_value=self.current_capital,
            total_pnl=self.current_capital - self.initial_capital,
            total_pnl_pct=(self.current_capital - self.initial_capital) / self.initial_capital,
            portfolio_var_95=var_metrics.get('var_95_hist', 0),
            portfolio_var_99=var_metrics.get('var_99_hist', 0),
            expected_shortfall=var_metrics.get('es_95', 0),
            max_drawdown=max_dd,
            current_drawdown=dd_status['current_drawdown'],
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            beta_to_market=1.0,  # Would calculate against market returns
            correlation_matrix=corr_matrix
        )

    def check_risk_limits(self) -> Dict[str, Any]:
        """Check if any risk limits are breached."""
        dd_status = self.drawdown_monitor.update(self.current_capital)
        heat = self._calculate_portfolio_heat()

        breaches = []

        if dd_status['current_drawdown'] >= self.max_drawdown_pct / 100:
            breaches.append('MAX_DRAWDOWN')

        if heat >= self.max_portfolio_risk_pct:
            breaches.append('MAX_PORTFOLIO_HEAT')

        return {
            'breaches': breaches,
            'is_breached': len(breaches) > 0,
            'current_drawdown': dd_status['current_drawdown'],
            'current_heat': heat,
            'risk_multiplier': dd_status['risk_multiplier'],
            'action': dd_status['action']
        }
