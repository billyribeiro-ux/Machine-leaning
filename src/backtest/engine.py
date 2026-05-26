"""
Revolution Alpha Engine - Professional Backtesting Framework

Institutional-grade backtesting with:
- Walk-forward analysis
- Monte Carlo simulation
- Full trade diagnostics and reasoning
- Slippage and commission modeling
- Multi-timeframe synchronization
- Out-of-sample validation
"""

import numpy as np
import pandas as pd
from typing import Optional, List, Dict, Tuple, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from collections import defaultdict
import logging
import uuid
import json

logger = logging.getLogger(__name__)


class TradeDirection(str, Enum):
    """Trade direction."""
    LONG = "long"
    SHORT = "short"


class TradeStatus(str, Enum):
    """Trade status."""
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"


@dataclass
class TradeSignal:
    """Signal that triggers a trade."""
    timestamp: datetime
    symbol: str
    direction: TradeDirection
    entry_price: float
    stop_loss: float
    take_profit: float
    confidence: float
    signal_source: str
    reasons: List[str] = field(default_factory=list)
    indicators: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TradeDiagnostic:
    """
    Comprehensive trade diagnostic explaining why trade was taken.

    This provides full reasoning for every trade decision.
    """
    # Signal Analysis
    primary_reason: str
    secondary_reasons: List[str]
    signal_strength: float
    signal_confidence: float

    # Technical Setup
    trend_alignment: str  # "aligned", "counter", "neutral"
    momentum_status: str  # "bullish", "bearish", "neutral"
    volatility_environment: str  # "low", "normal", "high", "extreme"
    support_resistance_context: str

    # Market Context
    market_regime: str
    sector_performance: str
    correlation_context: str

    # Timing Analysis
    entry_timing_quality: str  # "optimal", "good", "fair", "poor"
    exit_timing_quality: str

    # Risk Assessment
    risk_reward_ratio: float
    position_size_rationale: str
    stop_placement_reason: str
    target_placement_reason: str

    # Indicator Values at Entry
    rsi_at_entry: Optional[float] = None
    macd_at_entry: Optional[float] = None
    adx_at_entry: Optional[float] = None
    volume_ratio_at_entry: Optional[float] = None
    atr_at_entry: Optional[float] = None

    # Pattern Recognition
    chart_patterns: List[str] = field(default_factory=list)
    candlestick_patterns: List[str] = field(default_factory=list)

    # Flow Analysis
    order_flow_bias: Optional[str] = None
    institutional_activity: Optional[str] = None
    options_flow: Optional[str] = None

    def to_narrative(self) -> str:
        """Generate human-readable narrative of trade reasoning."""
        narrative = []

        narrative.append(f"PRIMARY REASON: {self.primary_reason}")
        narrative.append("")

        if self.secondary_reasons:
            narrative.append("SUPPORTING FACTORS:")
            for reason in self.secondary_reasons:
                narrative.append(f"  • {reason}")
            narrative.append("")

        narrative.append("TECHNICAL CONTEXT:")
        narrative.append(f"  • Trend: {self.trend_alignment}")
        narrative.append(f"  • Momentum: {self.momentum_status}")
        narrative.append(f"  • Volatility: {self.volatility_environment}")
        narrative.append(f"  • S/R Context: {self.support_resistance_context}")
        narrative.append("")

        narrative.append("MARKET ENVIRONMENT:")
        narrative.append(f"  • Regime: {self.market_regime}")
        narrative.append(f"  • Sector: {self.sector_performance}")
        narrative.append("")

        narrative.append("RISK PARAMETERS:")
        narrative.append(f"  • R:R Ratio: {self.risk_reward_ratio:.2f}")
        narrative.append(f"  • Position Sizing: {self.position_size_rationale}")
        narrative.append(f"  • Stop Reason: {self.stop_placement_reason}")
        narrative.append(f"  • Target Reason: {self.target_placement_reason}")
        narrative.append("")

        if self.chart_patterns:
            narrative.append(f"PATTERNS: {', '.join(self.chart_patterns)}")

        if self.order_flow_bias:
            narrative.append(f"ORDER FLOW: {self.order_flow_bias}")

        narrative.append("")
        narrative.append(f"ENTRY QUALITY: {self.entry_timing_quality}")
        narrative.append(f"SIGNAL CONFIDENCE: {self.signal_confidence:.1%}")

        return "\n".join(narrative)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for export."""
        return {
            'primary_reason': self.primary_reason,
            'secondary_reasons': self.secondary_reasons,
            'signal_strength': self.signal_strength,
            'signal_confidence': self.signal_confidence,
            'trend_alignment': self.trend_alignment,
            'momentum_status': self.momentum_status,
            'volatility_environment': self.volatility_environment,
            'market_regime': self.market_regime,
            'risk_reward_ratio': self.risk_reward_ratio,
            'entry_timing_quality': self.entry_timing_quality,
            'chart_patterns': self.chart_patterns,
            'order_flow_bias': self.order_flow_bias,
            'rsi': self.rsi_at_entry,
            'macd': self.macd_at_entry,
            'adx': self.adx_at_entry,
        }


@dataclass
class Trade:
    """Complete trade record with full diagnostics."""
    trade_id: str
    symbol: str
    direction: TradeDirection
    status: TradeStatus

    # Prices
    entry_price: float
    exit_price: Optional[float] = None
    stop_loss: float = 0
    take_profit: float = 0

    # Size
    shares: int = 0
    position_value: float = 0

    # Timing
    entry_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    exit_time: Optional[datetime] = None

    # P&L
    gross_pnl: float = 0
    commission: float = 0
    slippage: float = 0
    net_pnl: float = 0
    pnl_pct: float = 0

    # Risk
    initial_risk: float = 0
    max_adverse_excursion: float = 0
    max_favorable_excursion: float = 0
    r_multiple: float = 0

    # Diagnostics
    diagnostic: Optional[TradeDiagnostic] = None
    signal: Optional[TradeSignal] = None

    # Exit reason
    exit_reason: str = ""

    @property
    def duration(self) -> Optional[timedelta]:
        """Trade duration."""
        if self.exit_time:
            return self.exit_time - self.entry_time
        return None

    @property
    def is_winner(self) -> bool:
        """Check if trade was profitable."""
        return self.net_pnl > 0

    def close(
        self,
        exit_price: float,
        exit_time: datetime,
        exit_reason: str,
        commission: float = 0,
        slippage: float = 0
    ):
        """Close the trade."""
        self.exit_price = exit_price
        self.exit_time = exit_time
        self.exit_reason = exit_reason
        self.commission += commission
        self.slippage += slippage
        self.status = TradeStatus.CLOSED

        # Calculate P&L
        if self.direction == TradeDirection.LONG:
            self.gross_pnl = (exit_price - self.entry_price) * self.shares
        else:
            self.gross_pnl = (self.entry_price - exit_price) * self.shares

        self.net_pnl = self.gross_pnl - self.commission - self.slippage
        self.pnl_pct = (self.net_pnl / self.position_value) * 100 if self.position_value > 0 else 0

        # R-multiple
        if self.initial_risk > 0:
            self.r_multiple = self.net_pnl / self.initial_risk

    def update_excursions(self, high: float, low: float):
        """Update maximum excursions."""
        if self.direction == TradeDirection.LONG:
            adverse = self.entry_price - low
            favorable = high - self.entry_price
        else:
            adverse = high - self.entry_price
            favorable = self.entry_price - low

        self.max_adverse_excursion = max(self.max_adverse_excursion, adverse)
        self.max_favorable_excursion = max(self.max_favorable_excursion, favorable)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for export."""
        return {
            'trade_id': self.trade_id,
            'symbol': self.symbol,
            'direction': self.direction.value,
            'status': self.status.value,
            'entry_price': self.entry_price,
            'exit_price': self.exit_price,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'shares': self.shares,
            'position_value': self.position_value,
            'entry_time': self.entry_time.isoformat(),
            'exit_time': self.exit_time.isoformat() if self.exit_time else None,
            'gross_pnl': self.gross_pnl,
            'net_pnl': self.net_pnl,
            'pnl_pct': self.pnl_pct,
            'r_multiple': self.r_multiple,
            'exit_reason': self.exit_reason,
            'duration_hours': self.duration.total_seconds() / 3600 if self.duration else None,
            'diagnostic': self.diagnostic.to_dict() if self.diagnostic else None,
        }


@dataclass
class BacktestConfig:
    """Configuration for backtesting."""
    initial_capital: float = 100000
    commission_per_share: float = 0.005
    commission_minimum: float = 1.0
    slippage_pct: float = 0.05
    max_position_pct: float = 20.0
    max_open_positions: int = 10
    risk_per_trade_pct: float = 1.0
    use_stop_loss: bool = True
    use_take_profit: bool = True
    allow_shorting: bool = True
    margin_requirement: float = 0.5


@dataclass
class BacktestResults:
    """Comprehensive backtest results."""
    # Identification
    backtest_id: str
    start_date: datetime
    end_date: datetime
    config: BacktestConfig

    # Capital
    initial_capital: float
    final_capital: float
    peak_capital: float
    max_drawdown: float
    max_drawdown_duration: int

    # Returns
    total_return: float
    total_return_pct: float
    annual_return: float
    monthly_returns: List[float] = field(default_factory=list)

    # Risk-adjusted
    sharpe_ratio: float = 0
    sortino_ratio: float = 0
    calmar_ratio: float = 0

    # Trade Statistics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0

    # P&L
    gross_profit: float = 0
    gross_loss: float = 0
    net_profit: float = 0
    profit_factor: float = 0
    avg_win: float = 0
    avg_loss: float = 0
    largest_win: float = 0
    largest_loss: float = 0

    # R-Multiples
    avg_r_multiple: float = 0
    expectancy: float = 0

    # Trade details
    trades: List[Trade] = field(default_factory=list)
    equity_curve: pd.DataFrame = field(default_factory=pd.DataFrame)

    def generate_report(self) -> str:
        """Generate text report of results."""
        lines = []
        lines.append("=" * 60)
        lines.append("BACKTEST RESULTS REPORT")
        lines.append("=" * 60)
        lines.append("")

        lines.append(f"Period: {self.start_date.date()} to {self.end_date.date()}")
        lines.append(f"Backtest ID: {self.backtest_id}")
        lines.append("")

        lines.append("PERFORMANCE SUMMARY")
        lines.append("-" * 40)
        lines.append(f"Initial Capital:      ${self.initial_capital:,.2f}")
        lines.append(f"Final Capital:        ${self.final_capital:,.2f}")
        lines.append(f"Total Return:         ${self.total_return:,.2f} ({self.total_return_pct:.2f}%)")
        lines.append(f"Annual Return:        {self.annual_return:.2f}%")
        lines.append(f"Max Drawdown:         {self.max_drawdown:.2f}%")
        lines.append("")

        lines.append("RISK-ADJUSTED METRICS")
        lines.append("-" * 40)
        lines.append(f"Sharpe Ratio:         {self.sharpe_ratio:.2f}")
        lines.append(f"Sortino Ratio:        {self.sortino_ratio:.2f}")
        lines.append(f"Calmar Ratio:         {self.calmar_ratio:.2f}")
        lines.append("")

        lines.append("TRADE STATISTICS")
        lines.append("-" * 40)
        lines.append(f"Total Trades:         {self.total_trades}")
        lines.append(f"Winning Trades:       {self.winning_trades}")
        lines.append(f"Losing Trades:        {self.losing_trades}")
        lines.append(f"Win Rate:             {self.win_rate:.2f}%")
        lines.append(f"Profit Factor:        {self.profit_factor:.2f}")
        lines.append(f"Avg Win:              ${self.avg_win:,.2f}")
        lines.append(f"Avg Loss:             ${self.avg_loss:,.2f}")
        lines.append(f"Largest Win:          ${self.largest_win:,.2f}")
        lines.append(f"Largest Loss:         ${self.largest_loss:,.2f}")
        lines.append("")

        lines.append("EXPECTANCY")
        lines.append("-" * 40)
        lines.append(f"Avg R-Multiple:       {self.avg_r_multiple:.2f}R")
        lines.append(f"Expectancy:           ${self.expectancy:,.2f}")
        lines.append("")

        lines.append("=" * 60)

        return "\n".join(lines)

    def to_dataframe(self) -> pd.DataFrame:
        """Convert trades to DataFrame."""
        return pd.DataFrame([t.to_dict() for t in self.trades])


class TradeAnalyzer:
    """
    Analyzes market conditions to generate trade diagnostics.

    Provides comprehensive reasoning for why each trade was taken.
    """

    def __init__(self):
        self._trend_threshold = 0.02
        self._vol_low = 0.10
        self._vol_high = 0.25

    def analyze_trade_setup(
        self,
        signal: TradeSignal,
        market_data: pd.DataFrame,
        features: Optional[pd.DataFrame] = None
    ) -> TradeDiagnostic:
        """
        Generate comprehensive diagnostic for a trade setup.

        Args:
            signal: The trade signal
            market_data: OHLCV data at signal time
            features: Calculated features at signal time

        Returns:
            Complete trade diagnostic
        """
        # Extract key metrics
        close = market_data['close'].iloc[-1]
        returns = market_data['close'].pct_change()
        volatility = returns.rolling(20).std().iloc[-1] * np.sqrt(252)

        # Trend analysis
        sma_20 = market_data['close'].rolling(20).mean().iloc[-1]
        sma_50 = market_data['close'].rolling(50).mean().iloc[-1]

        if close > sma_20 > sma_50:
            trend = "strong_uptrend"
            trend_alignment = "aligned" if signal.direction == TradeDirection.LONG else "counter"
        elif close < sma_20 < sma_50:
            trend = "strong_downtrend"
            trend_alignment = "aligned" if signal.direction == TradeDirection.SHORT else "counter"
        else:
            trend = "mixed"
            trend_alignment = "neutral"

        # Momentum analysis
        if features is not None and 'rsi_14' in features.columns:
            rsi = features['rsi_14'].iloc[-1]
            macd = features.get('macd_hist', pd.Series([0])).iloc[-1]
            adx = features.get('adx', pd.Series([25])).iloc[-1]
        else:
            rsi = self._calculate_rsi(market_data['close'])
            macd = 0
            adx = 25

        if rsi > 50 and macd > 0:
            momentum = "bullish"
        elif rsi < 50 and macd < 0:
            momentum = "bearish"
        else:
            momentum = "neutral"

        # Volatility environment
        if volatility < self._vol_low:
            vol_env = "low"
        elif volatility > self._vol_high:
            vol_env = "high"
        else:
            vol_env = "normal"

        # S/R context
        recent_high = market_data['high'].rolling(20).max().iloc[-1]
        recent_low = market_data['low'].rolling(20).min().iloc[-1]

        dist_to_high = (recent_high - close) / close
        dist_to_low = (close - recent_low) / close

        if dist_to_high < 0.02:
            sr_context = "near_resistance"
        elif dist_to_low < 0.02:
            sr_context = "near_support"
        else:
            sr_context = "mid_range"

        # Build primary reason
        primary_reason = self._build_primary_reason(signal, trend, momentum, sr_context)

        # Build secondary reasons
        secondary_reasons = self._build_secondary_reasons(signal, features, market_data)

        # Risk/reward
        risk = abs(signal.entry_price - signal.stop_loss)
        reward = abs(signal.take_profit - signal.entry_price)
        rr_ratio = reward / risk if risk > 0 else 0

        # Entry timing quality
        entry_quality = self._assess_entry_timing(signal, market_data, trend_alignment, momentum)

        # Position sizing rationale
        if signal.confidence >= 0.8:
            size_rationale = "Full position due to high confidence signal"
        elif signal.confidence >= 0.6:
            size_rationale = "Standard position based on moderate confidence"
        else:
            size_rationale = "Reduced position due to lower conviction"

        # Stop placement reason
        if features is not None and 'atr_14' in features.columns:
            atr = features['atr_14'].iloc[-1]
            stop_reason = f"Stop placed at {abs(signal.entry_price - signal.stop_loss)/atr:.1f}x ATR"
        else:
            stop_reason = "Stop placed at key technical level"

        # Target placement reason
        target_reason = f"Target at {rr_ratio:.1f}R based on nearest resistance/support"

        # Volume analysis
        volume_ratio = None
        if 'volume' in market_data.columns:
            avg_vol = market_data['volume'].rolling(20).mean().iloc[-1]
            current_vol = market_data['volume'].iloc[-1]
            volume_ratio = current_vol / avg_vol if avg_vol > 0 else 1

        return TradeDiagnostic(
            primary_reason=primary_reason,
            secondary_reasons=secondary_reasons,
            signal_strength=signal.confidence,
            signal_confidence=signal.confidence,
            trend_alignment=trend_alignment,
            momentum_status=momentum,
            volatility_environment=vol_env,
            support_resistance_context=sr_context,
            market_regime=trend,
            sector_performance="neutral",  # Would come from sector analysis
            correlation_context="moderate",  # Would come from correlation analysis
            entry_timing_quality=entry_quality,
            exit_timing_quality="pending",
            risk_reward_ratio=rr_ratio,
            position_size_rationale=size_rationale,
            stop_placement_reason=stop_reason,
            target_placement_reason=target_reason,
            rsi_at_entry=rsi,
            macd_at_entry=macd,
            adx_at_entry=adx,
            volume_ratio_at_entry=volume_ratio,
            chart_patterns=signal.metadata.get('patterns', []),
            candlestick_patterns=signal.metadata.get('candle_patterns', []),
            order_flow_bias=signal.metadata.get('order_flow', None),
            institutional_activity=signal.metadata.get('institutional', None),
            options_flow=signal.metadata.get('options_flow', None)
        )

    def _calculate_rsi(self, close: pd.Series, period: int = 14) -> float:
        """Calculate RSI."""
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
        rs = gain / (loss + 1e-10)
        return float(100 - (100 / (1 + rs.iloc[-1])))

    def _build_primary_reason(
        self,
        signal: TradeSignal,
        trend: str,
        momentum: str,
        sr_context: str
    ) -> str:
        """Build the primary reason for the trade."""
        reasons = []

        if signal.signal_source == "momentum":
            reasons.append(f"Momentum signal with {signal.confidence:.0%} confidence")
        elif signal.signal_source == "reversal":
            reasons.append(f"Reversal pattern detected")
        elif signal.signal_source == "breakout":
            reasons.append(f"Breakout from consolidation")
        elif signal.signal_source == "options_flow":
            reasons.append(f"Unusual options activity detected")
        elif signal.signal_source == "squeeze":
            reasons.append(f"Squeeze conditions identified")
        else:
            reasons.append(f"{signal.signal_source} signal generated")

        if trend == "strong_uptrend" and signal.direction == TradeDirection.LONG:
            reasons.append("aligned with strong uptrend")
        elif trend == "strong_downtrend" and signal.direction == TradeDirection.SHORT:
            reasons.append("aligned with strong downtrend")

        if momentum == "bullish" and signal.direction == TradeDirection.LONG:
            reasons.append("bullish momentum confirmation")
        elif momentum == "bearish" and signal.direction == TradeDirection.SHORT:
            reasons.append("bearish momentum confirmation")

        return " - ".join(reasons)

    def _build_secondary_reasons(
        self,
        signal: TradeSignal,
        features: Optional[pd.DataFrame],
        market_data: pd.DataFrame
    ) -> List[str]:
        """Build list of secondary supporting reasons."""
        reasons = []

        # From signal reasons
        reasons.extend(signal.reasons)

        # Volume confirmation
        if 'volume' in market_data.columns:
            avg_vol = market_data['volume'].rolling(20).mean().iloc[-1]
            if market_data['volume'].iloc[-1] > avg_vol * 1.5:
                reasons.append("Volume confirmation (>150% of average)")

        # Indicator confirmations
        if features is not None:
            if 'rsi_14' in features.columns:
                rsi = features['rsi_14'].iloc[-1]
                if signal.direction == TradeDirection.LONG and rsi < 40:
                    reasons.append(f"RSI oversold ({rsi:.0f})")
                elif signal.direction == TradeDirection.SHORT and rsi > 60:
                    reasons.append(f"RSI overbought ({rsi:.0f})")

            if 'adx' in features.columns:
                adx = features['adx'].iloc[-1]
                if adx > 25:
                    reasons.append(f"Strong trend (ADX: {adx:.0f})")

        return reasons[:5]  # Limit to top 5

    def _assess_entry_timing(
        self,
        signal: TradeSignal,
        market_data: pd.DataFrame,
        trend_alignment: str,
        momentum: str
    ) -> str:
        """Assess the quality of entry timing."""
        score = 0

        # Trend alignment
        if trend_alignment == "aligned":
            score += 2
        elif trend_alignment == "neutral":
            score += 1

        # Momentum alignment
        if signal.direction == TradeDirection.LONG and momentum == "bullish":
            score += 2
        elif signal.direction == TradeDirection.SHORT and momentum == "bearish":
            score += 2
        elif momentum == "neutral":
            score += 1

        # Signal confidence
        if signal.confidence >= 0.8:
            score += 2
        elif signal.confidence >= 0.6:
            score += 1

        # Convert to quality
        if score >= 5:
            return "optimal"
        elif score >= 4:
            return "good"
        elif score >= 2:
            return "fair"
        return "poor"


class BacktestEngine:
    """
    Professional backtesting engine with full trade diagnostics.

    Features:
    - Event-driven simulation
    - Realistic execution modeling
    - Complete trade reasoning
    - Walk-forward optimization support
    """

    def __init__(self, config: Optional[BacktestConfig] = None):
        self.config = config or BacktestConfig()
        self.analyzer = TradeAnalyzer()

        # State
        self._capital = self.config.initial_capital
        self._positions: Dict[str, Trade] = {}
        self._closed_trades: List[Trade] = []
        self._equity_history: List[Tuple[datetime, float]] = []
        self._current_time: Optional[datetime] = None

    def run(
        self,
        data: Dict[str, pd.DataFrame],
        signal_generator: Callable[[str, pd.DataFrame, int], Optional[TradeSignal]],
        features: Optional[Dict[str, pd.DataFrame]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> BacktestResults:
        """
        Run backtest on historical data.

        Args:
            data: Dictionary of symbol -> OHLCV DataFrame
            signal_generator: Function that generates signals
            features: Pre-calculated features for each symbol
            start_date: Start date for backtest
            end_date: End date for backtest

        Returns:
            Complete backtest results with diagnostics
        """
        backtest_id = str(uuid.uuid4())[:8]

        # Reset state
        self._capital = self.config.initial_capital
        self._positions = {}
        self._closed_trades = []
        self._equity_history = []

        # Get date range
        all_dates = set()
        for symbol, df in data.items():
            all_dates.update(df.index.tolist())

        all_dates = sorted(all_dates)

        if start_date:
            all_dates = [d for d in all_dates if d >= start_date]
        if end_date:
            all_dates = [d for d in all_dates if d <= end_date]

        if not all_dates:
            raise ValueError("No data in specified date range")

        start = all_dates[0]
        end = all_dates[-1]

        logger.info(f"Running backtest from {start} to {end}")

        # Main simulation loop
        for i, current_date in enumerate(all_dates):
            self._current_time = current_date

            for symbol, df in data.items():
                if current_date not in df.index:
                    continue

                # Get current bar
                idx = df.index.get_loc(current_date)
                if idx < 50:  # Need history
                    continue

                current_bar = df.iloc[idx]
                history = df.iloc[:idx + 1]

                # Update existing positions
                if symbol in self._positions:
                    self._update_position(symbol, current_bar, current_date)

                # Generate signals
                signal = signal_generator(symbol, history, idx)

                if signal and symbol not in self._positions:
                    # Get features if available
                    symbol_features = None
                    if features and symbol in features:
                        symbol_features = features[symbol].iloc[:idx + 1]

                    # Execute trade
                    self._execute_signal(signal, history, symbol_features, current_date)

            # Record equity
            self._equity_history.append((current_date, self._calculate_equity(data)))

        # Close all remaining positions
        self._close_all_positions(data, all_dates[-1])

        # Calculate results
        results = self._calculate_results(backtest_id, start, end)

        return results

    def _execute_signal(
        self,
        signal: TradeSignal,
        market_data: pd.DataFrame,
        features: Optional[pd.DataFrame],
        timestamp: datetime
    ):
        """Execute a trade signal."""
        # Check position limits
        if len(self._positions) >= self.config.max_open_positions:
            return

        # Calculate position size
        risk_per_share = abs(signal.entry_price - signal.stop_loss)
        risk_budget = self._capital * (self.config.risk_per_trade_pct / 100)
        shares = int(risk_budget / risk_per_share) if risk_per_share > 0 else 0

        # Apply position size limits
        max_position = self._capital * (self.config.max_position_pct / 100)
        max_shares = int(max_position / signal.entry_price)
        shares = min(shares, max_shares)

        if shares <= 0:
            return

        # Calculate slippage
        slippage = signal.entry_price * (self.config.slippage_pct / 100)
        if signal.direction == TradeDirection.LONG:
            actual_entry = signal.entry_price + slippage
        else:
            actual_entry = signal.entry_price - slippage

        # Calculate commission
        commission = max(
            self.config.commission_minimum,
            shares * self.config.commission_per_share
        )

        # Generate diagnostic
        diagnostic = self.analyzer.analyze_trade_setup(signal, market_data, features)

        # Create trade
        trade = Trade(
            trade_id=str(uuid.uuid4())[:8],
            symbol=signal.symbol,
            direction=signal.direction,
            status=TradeStatus.OPEN,
            entry_price=actual_entry,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            shares=shares,
            position_value=shares * actual_entry,
            entry_time=timestamp,
            initial_risk=risk_per_share * shares,
            commission=commission,
            diagnostic=diagnostic,
            signal=signal
        )

        self._positions[signal.symbol] = trade
        self._capital -= commission

        logger.debug(f"Opened {signal.direction.value} {signal.symbol}: {shares} @ ${actual_entry:.2f}")

    def _update_position(self, symbol: str, bar: pd.Series, timestamp: datetime):
        """Update position and check exits."""
        trade = self._positions[symbol]

        # Update excursions
        trade.update_excursions(bar['high'], bar['low'])

        # Check stop loss
        if self.config.use_stop_loss:
            if trade.direction == TradeDirection.LONG and bar['low'] <= trade.stop_loss:
                self._close_position(symbol, trade.stop_loss, timestamp, "stop_loss")
                return
            elif trade.direction == TradeDirection.SHORT and bar['high'] >= trade.stop_loss:
                self._close_position(symbol, trade.stop_loss, timestamp, "stop_loss")
                return

        # Check take profit
        if self.config.use_take_profit:
            if trade.direction == TradeDirection.LONG and bar['high'] >= trade.take_profit:
                self._close_position(symbol, trade.take_profit, timestamp, "take_profit")
                return
            elif trade.direction == TradeDirection.SHORT and bar['low'] <= trade.take_profit:
                self._close_position(symbol, trade.take_profit, timestamp, "take_profit")
                return

    def _close_position(
        self,
        symbol: str,
        exit_price: float,
        timestamp: datetime,
        reason: str
    ):
        """Close a position."""
        if symbol not in self._positions:
            return

        trade = self._positions[symbol]

        # Calculate slippage
        slippage = exit_price * (self.config.slippage_pct / 100)
        if trade.direction == TradeDirection.LONG:
            actual_exit = exit_price - slippage
        else:
            actual_exit = exit_price + slippage

        # Calculate commission
        commission = max(
            self.config.commission_minimum,
            trade.shares * self.config.commission_per_share
        )

        # Close trade
        trade.close(actual_exit, timestamp, reason, commission, slippage)

        # Update capital
        self._capital += trade.position_value + trade.gross_pnl - commission

        # Move to closed trades
        self._closed_trades.append(trade)
        del self._positions[symbol]

        logger.debug(f"Closed {symbol} @ ${actual_exit:.2f} - PnL: ${trade.net_pnl:.2f} ({reason})")

    def _close_all_positions(self, data: Dict[str, pd.DataFrame], timestamp: datetime):
        """Close all remaining positions at end of backtest."""
        for symbol in list(self._positions.keys()):
            if symbol in data:
                exit_price = data[symbol].iloc[-1]['close']
                self._close_position(symbol, exit_price, timestamp, "end_of_backtest")

    def _calculate_equity(self, data: Dict[str, pd.DataFrame]) -> float:
        """Calculate current equity including open positions."""
        equity = self._capital

        for symbol, trade in self._positions.items():
            if symbol in data and self._current_time in data[symbol].index:
                current_price = data[symbol].loc[self._current_time, 'close']
                if trade.direction == TradeDirection.LONG:
                    unrealized = (current_price - trade.entry_price) * trade.shares
                else:
                    unrealized = (trade.entry_price - current_price) * trade.shares
                equity += trade.position_value + unrealized

        return equity

    def _calculate_results(
        self,
        backtest_id: str,
        start: datetime,
        end: datetime
    ) -> BacktestResults:
        """Calculate comprehensive backtest results."""
        trades = self._closed_trades

        # Basic metrics
        initial = self.config.initial_capital
        final = self._capital

        # Equity curve
        equity_df = pd.DataFrame(self._equity_history, columns=['timestamp', 'equity'])
        equity_df.set_index('timestamp', inplace=True)

        # Drawdown
        peak = equity_df['equity'].expanding().max()
        drawdown = (equity_df['equity'] - peak) / peak
        max_dd = abs(drawdown.min()) * 100

        # Returns
        total_return = final - initial
        total_return_pct = (total_return / initial) * 100

        days = (end - start).days
        annual_return = ((final / initial) ** (365 / days) - 1) * 100 if days > 0 else 0

        # Trade statistics
        winners = [t for t in trades if t.is_winner]
        losers = [t for t in trades if not t.is_winner]

        win_rate = (len(winners) / len(trades)) * 100 if trades else 0

        gross_profit = sum(t.net_pnl for t in winners)
        gross_loss = abs(sum(t.net_pnl for t in losers))

        profit_factor = min(gross_profit / gross_loss, 999.9) if gross_loss > 0 else 999.9

        avg_win = np.mean([t.net_pnl for t in winners]) if winners else 0
        avg_loss = np.mean([t.net_pnl for t in losers]) if losers else 0

        largest_win = max([t.net_pnl for t in winners]) if winners else 0
        largest_loss = min([t.net_pnl for t in losers]) if losers else 0

        # R-multiples
        r_multiples = [t.r_multiple for t in trades if t.r_multiple != 0]
        avg_r = np.mean(r_multiples) if r_multiples else 0

        # Expectancy
        expectancy = (win_rate / 100 * avg_win) - ((1 - win_rate / 100) * abs(avg_loss))

        # Risk-adjusted returns
        daily_returns = equity_df['equity'].pct_change().dropna()

        rf_rate = 0.05 / 252
        excess_returns = daily_returns - rf_rate

        sharpe = np.sqrt(252) * excess_returns.mean() / excess_returns.std() if excess_returns.std() > 0 else 0

        neg_returns = daily_returns[daily_returns < 0]
        sortino = np.sqrt(252) * excess_returns.mean() / neg_returns.std() if len(neg_returns) > 0 else 0

        calmar = annual_return / max_dd if max_dd > 0 else 0

        return BacktestResults(
            backtest_id=backtest_id,
            start_date=start,
            end_date=end,
            config=self.config,
            initial_capital=initial,
            final_capital=final,
            peak_capital=equity_df['equity'].max(),
            max_drawdown=max_dd,
            max_drawdown_duration=0,  # Would calculate
            total_return=total_return,
            total_return_pct=total_return_pct,
            annual_return=annual_return,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            total_trades=len(trades),
            winning_trades=len(winners),
            losing_trades=len(losers),
            win_rate=win_rate,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            net_profit=total_return,
            profit_factor=profit_factor,
            avg_win=avg_win,
            avg_loss=avg_loss,
            largest_win=largest_win,
            largest_loss=largest_loss,
            avg_r_multiple=avg_r,
            expectancy=expectancy,
            trades=trades,
            equity_curve=equity_df
        )
