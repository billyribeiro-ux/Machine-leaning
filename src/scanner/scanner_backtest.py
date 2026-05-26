"""
Revolution Alpha Engine - Universal Scanner Backtest Framework.

Every scanner. Every timeframe. From 1-minute to 30 years.
We see the move BEFORE the move. Complete win rate tracking,
performance attribution, regime analysis, and confidence calibration
for ALL scanner models.
"""

import math
import uuid
import logging
import numpy as np
from enum import Enum
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field, asdict
from typing import (
    Optional, Dict, List, Tuple, Any, Sequence, Union
)
from collections import defaultdict, deque

from .base import BaseScanner, ScannerConfig, ScanContext
from .models import ScanResult, MarketData, SignalDirection
from .advanced_models import (
    AdvancedScanResult,
    ScanCategory,
    RegimeContext,
    ExpectedTimeframe,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

_RISK_FREE_RATE: float = 0.045
"""Annualized risk-free rate used for Sharpe / Sortino calculations."""

_WILSON_Z: float = 1.96
"""Z-value for 95 % Wilson confidence interval."""

_DEFAULT_ROLLING_WINDOW: int = 50
"""Default number of trades for rolling win-rate computation."""

_CONFIDENCE_BUCKETS: List[Tuple[float, float]] = [
    (0.0, 20.0),
    (20.0, 40.0),
    (40.0, 60.0),
    (60.0, 80.0),
    (80.0, 100.0),
]
"""Confidence bucket boundaries used in win-rate breakdowns."""

_DECAY_MULTIPLES: List[int] = [1, 2, 3, 5, 10]
"""Multiples of expected holding period used in signal-decay analysis."""


# =============================================================================
# Enumerations
# =============================================================================

class BacktestTimeframe(Enum):
    """
    Universal timeframe enumeration covering the full spectrum from
    one-minute scalps to multi-decade investment horizons.

    Each member is a tuple of (label, minutes).
    """

    M1 = ("1m", 1)
    M5 = ("5m", 5)
    M15 = ("15m", 15)
    M30 = ("30m", 30)
    H1 = ("1h", 60)
    H4 = ("4h", 240)
    D1 = ("1d", 1440)
    W1 = ("1w", 10080)
    MN1 = ("1mo", 43200)
    Q1 = ("1q", 129600)
    Y1 = ("1y", 525600)
    Y5 = ("5y", 2628000)
    Y10 = ("10y", 5256000)
    Y30 = ("30y", 15768000)

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    @property
    def label(self) -> str:
        """Human-readable label such as '1m' or '30y'."""
        return self.value[0]

    @property
    def minutes(self) -> int:
        """Duration expressed in minutes."""
        return self.value[1]

    @property
    def periods_per_year(self) -> float:
        """
        Number of periods that fit within one calendar year.

        Used for annualising Sharpe, Sortino, and Calmar ratios.
        """
        minutes_per_year = 525600.0
        return minutes_per_year / self.minutes

    @classmethod
    def from_label(cls, label: str) -> "BacktestTimeframe":
        """Look up a timeframe by its human-readable label."""
        for member in cls:
            if member.label == label:
                return member
        raise ValueError(f"Unknown timeframe label: {label}")


class TradeDirection(str, Enum):
    """Direction of an individual simulated trade."""

    LONG = "LONG"
    SHORT = "SHORT"


class TradeOutcome(str, Enum):
    """Categorical outcome of a closed trade."""

    WIN = "WIN"
    LOSS = "LOSS"
    BREAKEVEN = "BREAKEVEN"
    STOPPED_OUT = "STOPPED_OUT"
    TARGET_HIT = "TARGET_HIT"
    TIME_EXIT = "TIME_EXIT"


# =============================================================================
# Data-classes  (trade records, backtest results)
# =============================================================================

@dataclass
class SimulatedBar:
    """
    A single price bar used inside the backtest engine.

    Mirrors the fields of ``MarketData`` but kept lightweight so that
    tens of millions of bars can sit in memory without overhead.
    """

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int = 0
    atr: Optional[float] = None

    @property
    def mid(self) -> float:
        """Mid-point of the bar range."""
        return (self.high + self.low) / 2.0

    @property
    def range_abs(self) -> float:
        """Absolute range of the bar."""
        return self.high - self.low

    @classmethod
    def from_market_data(cls, md: MarketData) -> "SimulatedBar":
        """Convert a ``MarketData`` instance to a ``SimulatedBar``."""
        return cls(
            timestamp=md.timestamp,
            open=md.open,
            high=md.high,
            low=md.low,
            close=md.close,
            volume=md.volume,
            atr=md.atr,
        )


@dataclass
class TradeRecord:
    """
    Complete record of a single simulated trade.

    Every field that downstream analytics need is stored here so that
    the metrics layer never has to re-derive anything from raw bars.
    """

    trade_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str = ""
    direction: TradeDirection = TradeDirection.LONG
    entry_price: float = 0.0
    exit_price: float = 0.0
    stop_loss: float = 0.0
    target_price: float = 0.0
    entry_time: Optional[datetime] = None
    exit_time: Optional[datetime] = None
    bars_held: int = 0
    return_pct: float = 0.0
    return_dollars: float = 0.0
    outcome: TradeOutcome = TradeOutcome.BREAKEVEN
    mfe_pct: float = 0.0
    mae_pct: float = 0.0
    signal_confidence: float = 0.0
    regime_at_entry: RegimeContext = RegimeContext.RANGING
    slippage_cost: float = 0.0
    commission_cost: float = 0.0
    scanner_name: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_winner(self) -> bool:
        """Return True when the trade closed in profit."""
        return self.return_pct > 0.0

    @property
    def is_loser(self) -> bool:
        """Return True when the trade closed at a loss."""
        return self.return_pct < 0.0

    @property
    def risk_multiple(self) -> float:
        """Return achieved in multiples of initial risk (R)."""
        risk = abs(self.entry_price - self.stop_loss)
        if risk == 0.0:
            return 0.0
        reward = self.exit_price - self.entry_price
        if self.direction == TradeDirection.SHORT:
            reward = self.entry_price - self.exit_price
        return reward / risk

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dictionary."""
        d = asdict(self)
        d["direction"] = self.direction.value
        d["outcome"] = self.outcome.value
        d["regime_at_entry"] = self.regime_at_entry.value
        if self.entry_time:
            d["entry_time"] = self.entry_time.isoformat()
        if self.exit_time:
            d["exit_time"] = self.exit_time.isoformat()
        return d


@dataclass
class ScannerBacktestResult:
    """
    Comprehensive backtest output produced by ``ScannerBacktestEngine``.

    Contains every metric needed for performance attribution, regime
    analysis, confidence calibration, and report generation.
    """

    # Identification
    scanner_name: str = ""
    timeframe: str = ""
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    # Core counts
    total_signals: int = 0
    total_trades: int = 0

    # Win / loss
    win_rate: float = 0.0
    loss_rate: float = 0.0
    breakeven_rate: float = 0.0

    # Average returns
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    avg_trade_pct: float = 0.0
    median_trade_pct: float = 0.0

    # Risk-adjusted
    profit_factor: float = 0.0
    expectancy: float = 0.0
    expectancy_per_dollar: float = 0.0

    # Drawdown
    max_drawdown_pct: float = 0.0
    max_drawdown_duration_bars: int = 0
    avg_drawdown_pct: float = 0.0

    # Streaks
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0

    # Ratios
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0

    # Holding period
    avg_holding_period_bars: float = 0.0
    median_holding_period_bars: float = 0.0

    # Extremes
    best_trade_pct: float = 0.0
    worst_trade_pct: float = 0.0
    best_trade_id: str = ""
    worst_trade_id: str = ""

    # Direction breakdown
    trades_by_direction: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Monthly returns
    monthly_returns: List[float] = field(default_factory=list)

    # Regime breakdown
    win_rate_by_regime: Dict[str, float] = field(default_factory=dict)

    # Confidence calibration
    win_rate_by_confidence: Dict[str, float] = field(default_factory=dict)

    # Signal decay
    signal_decay_curve: List[float] = field(default_factory=list)

    # Rolling win rate
    rolling_win_rate: List[float] = field(default_factory=list)

    # Statistical
    wilson_lower: float = 0.0
    wilson_upper: float = 0.0
    kelly_fraction: float = 0.0
    half_kelly: float = 0.0

    # Equity curve
    equity_curve: List[float] = field(default_factory=list)

    # Totals
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    net_profit: float = 0.0
    total_commissions: float = 0.0
    total_slippage: float = 0.0

    # MFE / MAE
    avg_mfe_pct: float = 0.0
    avg_mae_pct: float = 0.0

    # Tail
    skewness: float = 0.0
    kurtosis: float = 0.0
    tail_ratio: float = 0.0

    # Metadata
    backtest_run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Serialise every metric to a JSON-compatible dictionary."""
        d: Dict[str, Any] = {
            "backtest_run_id": self.backtest_run_id,
            "scanner_name": self.scanner_name,
            "timeframe": self.timeframe,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "generated_at": self.generated_at.isoformat(),
            "total_signals": self.total_signals,
            "total_trades": self.total_trades,
            "win_rate": round(self.win_rate, 6),
            "loss_rate": round(self.loss_rate, 6),
            "breakeven_rate": round(self.breakeven_rate, 6),
            "avg_win_pct": round(self.avg_win_pct, 6),
            "avg_loss_pct": round(self.avg_loss_pct, 6),
            "avg_trade_pct": round(self.avg_trade_pct, 6),
            "median_trade_pct": round(self.median_trade_pct, 6),
            "profit_factor": round(self.profit_factor, 4),
            "expectancy": round(self.expectancy, 6),
            "expectancy_per_dollar": round(self.expectancy_per_dollar, 6),
            "max_drawdown_pct": round(self.max_drawdown_pct, 6),
            "max_drawdown_duration_bars": self.max_drawdown_duration_bars,
            "avg_drawdown_pct": round(self.avg_drawdown_pct, 6),
            "max_consecutive_wins": self.max_consecutive_wins,
            "max_consecutive_losses": self.max_consecutive_losses,
            "sharpe_ratio": round(self.sharpe_ratio, 6),
            "sortino_ratio": round(self.sortino_ratio, 6),
            "calmar_ratio": round(self.calmar_ratio, 6),
            "avg_holding_period_bars": round(self.avg_holding_period_bars, 2),
            "median_holding_period_bars": round(self.median_holding_period_bars, 2),
            "best_trade_pct": round(self.best_trade_pct, 6),
            "worst_trade_pct": round(self.worst_trade_pct, 6),
            "best_trade_id": self.best_trade_id,
            "worst_trade_id": self.worst_trade_id,
            "trades_by_direction": self.trades_by_direction,
            "monthly_returns": [round(r, 6) for r in self.monthly_returns],
            "win_rate_by_regime": {
                k: round(v, 6) for k, v in self.win_rate_by_regime.items()
            },
            "win_rate_by_confidence": {
                k: round(v, 6) for k, v in self.win_rate_by_confidence.items()
            },
            "signal_decay_curve": [round(v, 6) for v in self.signal_decay_curve],
            "rolling_win_rate": [round(v, 6) for v in self.rolling_win_rate],
            "wilson_lower": round(self.wilson_lower, 6),
            "wilson_upper": round(self.wilson_upper, 6),
            "kelly_fraction": round(self.kelly_fraction, 6),
            "half_kelly": round(self.half_kelly, 6),
            "equity_curve": [round(v, 4) for v in self.equity_curve],
            "gross_profit": round(self.gross_profit, 4),
            "gross_loss": round(self.gross_loss, 4),
            "net_profit": round(self.net_profit, 4),
            "total_commissions": round(self.total_commissions, 4),
            "total_slippage": round(self.total_slippage, 4),
            "avg_mfe_pct": round(self.avg_mfe_pct, 6),
            "avg_mae_pct": round(self.avg_mae_pct, 6),
            "skewness": round(self.skewness, 6),
            "kurtosis": round(self.kurtosis, 6),
            "tail_ratio": round(self.tail_ratio, 4),
        }
        return d


# =============================================================================
# Helper: normalise signals coming from either ScanResult or AdvancedScanResult
# =============================================================================

@dataclass
class NormalisedSignal:
    """
    Internal normalised signal representation that abstracts away the
    difference between ``ScanResult`` and ``AdvancedScanResult``.
    """

    signal_id: str = ""
    symbol: str = ""
    direction: TradeDirection = TradeDirection.LONG
    confidence: float = 0.0
    entry_price: float = 0.0
    stop_loss: float = 0.0
    target_price: float = 0.0
    secondary_targets: List[float] = field(default_factory=list)
    timestamp: Optional[datetime] = None
    regime: RegimeContext = RegimeContext.RANGING
    expected_bars: int = 10
    scanner_name: str = ""
    raw: Any = None


def _normalise_signal(
    signal: Union[ScanResult, AdvancedScanResult, Dict[str, Any]],
) -> NormalisedSignal:
    """
    Convert any supported signal type into a ``NormalisedSignal``.

    Handles ``ScanResult`` (confidence 0-100, direction enum),
    ``AdvancedScanResult`` (confidence 0-1, literal direction strings),
    and plain dictionaries.
    """
    ns = NormalisedSignal(raw=signal)

    if isinstance(signal, AdvancedScanResult):
        ns.signal_id = signal.scan_id
        ns.symbol = signal.symbol
        ns.confidence = signal.confidence * 100.0
        ns.entry_price = signal.entry_price or 0.0
        ns.stop_loss = signal.stop_loss_level
        ns.target_price = signal.target_level
        ns.secondary_targets = list(signal.secondary_targets)
        ns.timestamp = signal.timestamp
        ns.regime = signal.regime_context
        ns.scanner_name = signal.scan_name

        if signal.signal_direction == "BULLISH":
            ns.direction = TradeDirection.LONG
        elif signal.signal_direction == "BEARISH":
            ns.direction = TradeDirection.SHORT
        else:
            ns.direction = TradeDirection.LONG

        _tf_bars_map = {
            ExpectedTimeframe.SCALP: 5,
            ExpectedTimeframe.INTRADAY: 78,
            ExpectedTimeframe.SWING: 20,
            ExpectedTimeframe.POSITION: 60,
            ExpectedTimeframe.INVESTMENT: 180,
        }
        ns.expected_bars = _tf_bars_map.get(signal.expected_timeframe, 20)

    elif isinstance(signal, ScanResult):
        ns.signal_id = str(uuid.uuid4())
        ns.symbol = signal.symbol
        ns.confidence = signal.confidence
        ns.entry_price = signal.entry_price or 0.0
        ns.stop_loss = signal.stop_loss or 0.0
        ns.target_price = signal.targets[0] if signal.targets else 0.0
        ns.secondary_targets = list(signal.targets[1:]) if len(signal.targets) > 1 else []
        ns.timestamp = signal.timestamp
        ns.scanner_name = signal.scanner_type

        if signal.direction == SignalDirection.LONG:
            ns.direction = TradeDirection.LONG
        elif signal.direction == SignalDirection.SHORT:
            ns.direction = TradeDirection.SHORT
        else:
            ns.direction = TradeDirection.LONG

        ns.expected_bars = 20

    elif isinstance(signal, dict):
        ns.signal_id = signal.get("signal_id", str(uuid.uuid4()))
        ns.symbol = signal.get("symbol", "")
        ns.confidence = float(signal.get("confidence", 0.0))
        ns.entry_price = float(signal.get("entry_price", 0.0))
        ns.stop_loss = float(signal.get("stop_loss", 0.0))
        ns.target_price = float(signal.get("target_price", 0.0))
        ns.secondary_targets = list(signal.get("secondary_targets", []))
        ns.timestamp = signal.get("timestamp")
        ns.scanner_name = signal.get("scanner_name", "")
        ns.expected_bars = int(signal.get("expected_bars", 20))

        raw_dir = str(signal.get("direction", "LONG")).upper()
        if raw_dir in ("SHORT", "BEARISH"):
            ns.direction = TradeDirection.SHORT
        else:
            ns.direction = TradeDirection.LONG

        raw_regime = signal.get("regime", "RANGING")
        try:
            ns.regime = RegimeContext(raw_regime)
        except ValueError:
            ns.regime = RegimeContext.RANGING

    return ns


# =============================================================================
# 3. TradeSimulator
# =============================================================================

class TradeSimulator:
    """
    Realistic trade simulation engine.

    Models slippage, commissions, partial profits, and trailing stops
    to produce trade records that faithfully represent real execution.
    """

    def __init__(
        self,
        default_slippage_pct: float = 0.01,
        default_commission_per_share: float = 0.005,
        default_position_size: float = 10000.0,
        random_seed: Optional[int] = None,
    ):
        """
        Initialise the trade simulator.

        Args:
            default_slippage_pct: Baseline slippage as a percentage of price.
            default_commission_per_share: Per-share commission in dollars.
            default_position_size: Notional position size in dollars.
            random_seed: Optional seed for reproducible slippage randomness.
        """
        self.default_slippage_pct = default_slippage_pct
        self.default_commission_per_share = default_commission_per_share
        self.default_position_size = default_position_size
        self._rng = np.random.RandomState(random_seed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def simulate_trade(
        self,
        signal: NormalisedSignal,
        bars: List[SimulatedBar],
        timeframe: BacktestTimeframe = BacktestTimeframe.D1,
        slippage: Optional[float] = None,
        commission: Optional[float] = None,
    ) -> Optional[TradeRecord]:
        """
        Execute a single trade using the signal's entry, stop-loss, and
        target against the supplied bar data.

        The simulation walks forward bar-by-bar, checking whether the
        stop-loss or target is hit within each bar's range.  If neither
        level is reached by the final bar, the trade exits at the close
        of the last bar (time-based exit).

        Args:
            signal: Normalised signal containing entry, SL, and target.
            bars: Forward-looking bars starting from the signal bar.
            timeframe: Backtest timeframe (used for cost scaling).
            slippage: Override slippage percentage.  ``None`` uses default.
            commission: Override per-share commission.  ``None`` uses default.

        Returns:
            A ``TradeRecord`` or ``None`` if the trade cannot be simulated
            (e.g. missing entry price or empty bars).
        """
        if not bars or signal.entry_price <= 0.0:
            return None

        atr_est = bars[0].atr if bars[0].atr else bars[0].range_abs
        entry = self.apply_slippage(
            signal.entry_price, signal.direction, atr_est, slippage
        )
        if entry <= 0.0:
            return None

        sl = signal.stop_loss if signal.stop_loss > 0.0 else self._auto_stop(
            entry, signal.direction, atr_est
        )
        tp = signal.target_price if signal.target_price > 0.0 else self._auto_target(
            entry, sl, signal.direction
        )

        shares = self.default_position_size / entry if entry > 0 else 0
        comm = self.apply_commission(shares, commission)

        mfe, mae = self.compute_mfe_mae(bars, entry, signal.direction)

        exit_price = entry
        exit_time = bars[0].timestamp
        bars_held = 0
        outcome = TradeOutcome.BREAKEVEN

        for i, bar in enumerate(bars):
            bars_held = i + 1

            if signal.direction == TradeDirection.LONG:
                if bar.low <= sl:
                    exit_price = sl
                    exit_time = bar.timestamp
                    outcome = TradeOutcome.STOPPED_OUT
                    break
                if bar.high >= tp:
                    exit_price = tp
                    exit_time = bar.timestamp
                    outcome = TradeOutcome.TARGET_HIT
                    break
            else:
                if bar.high >= sl:
                    exit_price = sl
                    exit_time = bar.timestamp
                    outcome = TradeOutcome.STOPPED_OUT
                    break
                if bar.low <= tp:
                    exit_price = tp
                    exit_time = bar.timestamp
                    outcome = TradeOutcome.TARGET_HIT
                    break
        else:
            exit_price = bars[-1].close
            exit_time = bars[-1].timestamp
            outcome = TradeOutcome.TIME_EXIT

        if signal.direction == TradeDirection.LONG:
            ret_pct = ((exit_price - entry) / entry) * 100.0
        else:
            ret_pct = ((entry - exit_price) / entry) * 100.0

        ret_dollars = (ret_pct / 100.0) * self.default_position_size
        slip_cost = abs(signal.entry_price - entry) * shares

        if ret_pct > 0.0:
            final_outcome = TradeOutcome.WIN if outcome == TradeOutcome.TIME_EXIT else outcome
        elif ret_pct < 0.0:
            final_outcome = TradeOutcome.LOSS if outcome == TradeOutcome.TIME_EXIT else outcome
        else:
            final_outcome = TradeOutcome.BREAKEVEN

        return TradeRecord(
            symbol=signal.symbol,
            direction=signal.direction,
            entry_price=entry,
            exit_price=exit_price,
            stop_loss=sl,
            target_price=tp,
            entry_time=signal.timestamp,
            exit_time=exit_time,
            bars_held=bars_held,
            return_pct=ret_pct,
            return_dollars=ret_dollars,
            outcome=final_outcome,
            mfe_pct=mfe,
            mae_pct=mae,
            signal_confidence=signal.confidence,
            regime_at_entry=signal.regime,
            slippage_cost=slip_cost,
            commission_cost=comm,
            scanner_name=signal.scanner_name,
        )

    def apply_slippage(
        self,
        price: float,
        direction: TradeDirection,
        atr: float,
        override_pct: Optional[float] = None,
    ) -> float:
        """
        Apply realistic slippage to a fill price.

        Model: base slippage of 0.01 % plus a random component scaled
        to half the ATR.  Long entries slip upward; short entries slip
        upward (worse fill).

        Args:
            price: Intended fill price.
            direction: Trade direction.
            atr: Average True Range estimate for randomness scaling.
            override_pct: If provided, replaces the default base slippage.

        Returns:
            Adjusted fill price after slippage.
        """
        if price <= 0.0:
            return price

        base_pct = override_pct if override_pct is not None else self.default_slippage_pct
        random_component = self._rng.uniform(0.0, 0.5 * atr / price) if atr > 0 and price > 0 else 0.0
        total_slip_pct = (base_pct / 100.0) + random_component

        if direction == TradeDirection.LONG:
            return price * (1.0 + total_slip_pct)
        else:
            return price * (1.0 - total_slip_pct)

    def apply_commission(
        self,
        shares: float,
        override_per_share: Optional[float] = None,
    ) -> float:
        """
        Compute round-trip commission using a per-share model.

        Args:
            shares: Number of shares (fractional allowed).
            override_per_share: If provided, replaces the default rate.

        Returns:
            Total round-trip commission in dollars.
        """
        rate = override_per_share if override_per_share is not None else self.default_commission_per_share
        return abs(shares) * rate * 2.0

    def compute_mfe_mae(
        self,
        bars: List[SimulatedBar],
        entry: float,
        direction: TradeDirection,
    ) -> Tuple[float, float]:
        """
        Maximum Favourable Excursion and Maximum Adverse Excursion.

        Args:
            bars: Bars during the trade's lifetime.
            entry: Trade entry price.
            direction: Trade direction.

        Returns:
            Tuple of (MFE %, MAE %) relative to entry.
        """
        if not bars or entry <= 0.0:
            return 0.0, 0.0

        best = 0.0
        worst = 0.0

        for bar in bars:
            if direction == TradeDirection.LONG:
                fav = ((bar.high - entry) / entry) * 100.0
                adv = ((bar.low - entry) / entry) * 100.0
            else:
                fav = ((entry - bar.low) / entry) * 100.0
                adv = ((entry - bar.high) / entry) * 100.0

            best = max(best, fav)
            worst = min(worst, adv)

        return best, worst

    def partial_profit_simulation(
        self,
        signal: NormalisedSignal,
        bars: List[SimulatedBar],
    ) -> Optional[TradeRecord]:
        """
        Simulate taking 50 % off at the first target and letting the
        remainder run to the second target or stop-loss.

        If only one target is available, falls back to the standard
        ``simulate_trade`` path.

        Args:
            signal: Normalised signal with at least two targets.
            bars: Forward-looking bars for simulation.

        Returns:
            Blended ``TradeRecord`` or ``None``.
        """
        if not signal.secondary_targets or not bars:
            return self.simulate_trade(signal, bars)

        if signal.entry_price <= 0.0:
            return None

        entry = signal.entry_price
        sl = signal.stop_loss if signal.stop_loss > 0 else self._auto_stop(
            entry, signal.direction, bars[0].range_abs
        )
        tp1 = signal.target_price
        tp2 = signal.secondary_targets[0] if signal.secondary_targets else tp1

        portion_1_pct = 0.0
        portion_2_pct = 0.0
        portion_1_filled = False
        exit_time = bars[-1].timestamp if bars else signal.timestamp
        total_bars = 0
        outcome = TradeOutcome.TIME_EXIT

        for i, bar in enumerate(bars):
            total_bars = i + 1

            if signal.direction == TradeDirection.LONG:
                if bar.low <= sl:
                    if not portion_1_filled:
                        portion_1_pct = ((sl - entry) / entry) * 100.0
                    portion_2_pct = ((sl - entry) / entry) * 100.0
                    exit_time = bar.timestamp
                    outcome = TradeOutcome.STOPPED_OUT
                    break

                if not portion_1_filled and bar.high >= tp1:
                    portion_1_pct = ((tp1 - entry) / entry) * 100.0
                    portion_1_filled = True
                    sl = entry

                if portion_1_filled and bar.high >= tp2:
                    portion_2_pct = ((tp2 - entry) / entry) * 100.0
                    exit_time = bar.timestamp
                    outcome = TradeOutcome.TARGET_HIT
                    break
            else:
                if bar.high >= sl:
                    if not portion_1_filled:
                        portion_1_pct = ((entry - sl) / entry) * 100.0
                    portion_2_pct = ((entry - sl) / entry) * 100.0
                    exit_time = bar.timestamp
                    outcome = TradeOutcome.STOPPED_OUT
                    break

                if not portion_1_filled and bar.low <= tp1:
                    portion_1_pct = ((entry - tp1) / entry) * 100.0
                    portion_1_filled = True
                    sl = entry

                if portion_1_filled and bar.low <= tp2:
                    portion_2_pct = ((entry - tp2) / entry) * 100.0
                    exit_time = bar.timestamp
                    outcome = TradeOutcome.TARGET_HIT
                    break
        else:
            final_close = bars[-1].close
            if signal.direction == TradeDirection.LONG:
                if not portion_1_filled:
                    portion_1_pct = ((final_close - entry) / entry) * 100.0
                portion_2_pct = ((final_close - entry) / entry) * 100.0
            else:
                if not portion_1_filled:
                    portion_1_pct = ((entry - final_close) / entry) * 100.0
                portion_2_pct = ((entry - final_close) / entry) * 100.0

        blended_return = 0.5 * portion_1_pct + 0.5 * portion_2_pct
        mfe, mae = self.compute_mfe_mae(bars[:total_bars], entry, signal.direction)

        return TradeRecord(
            symbol=signal.symbol,
            direction=signal.direction,
            entry_price=entry,
            exit_price=0.0,
            stop_loss=signal.stop_loss,
            target_price=tp1,
            entry_time=signal.timestamp,
            exit_time=exit_time,
            bars_held=total_bars,
            return_pct=blended_return,
            return_dollars=(blended_return / 100.0) * self.default_position_size,
            outcome=outcome,
            mfe_pct=mfe,
            mae_pct=mae,
            signal_confidence=signal.confidence,
            regime_at_entry=signal.regime,
            scanner_name=signal.scanner_name,
            metadata={"partial_profit": True, "tp1": tp1, "tp2": tp2},
        )

    def trailing_stop_simulation(
        self,
        signal: NormalisedSignal,
        bars: List[SimulatedBar],
        trail_atr: float = 2.0,
    ) -> Optional[TradeRecord]:
        """
        Simulate a trailing stop that follows the price by ``trail_atr``
        multiples of the current ATR.

        The trailing stop only moves in the favourable direction and
        never retreats.

        Args:
            signal: Normalised signal.
            bars: Forward-looking bars.
            trail_atr: ATR multiple for the trailing distance.

        Returns:
            ``TradeRecord`` or ``None``.
        """
        if not bars or signal.entry_price <= 0.0:
            return None

        entry = signal.entry_price
        direction = signal.direction

        if direction == TradeDirection.LONG:
            trailing_stop = entry - trail_atr * (bars[0].atr or bars[0].range_abs)
        else:
            trailing_stop = entry + trail_atr * (bars[0].atr or bars[0].range_abs)

        exit_price = entry
        exit_time = bars[-1].timestamp
        bars_held = 0
        outcome = TradeOutcome.TIME_EXIT

        for i, bar in enumerate(bars):
            bars_held = i + 1
            atr_val = bar.atr if bar.atr else bar.range_abs
            if atr_val <= 0:
                atr_val = abs(bar.close - bar.open) or 0.01

            if direction == TradeDirection.LONG:
                if bar.low <= trailing_stop:
                    exit_price = trailing_stop
                    exit_time = bar.timestamp
                    outcome = TradeOutcome.STOPPED_OUT
                    break
                new_stop = bar.high - trail_atr * atr_val
                trailing_stop = max(trailing_stop, new_stop)
            else:
                if bar.high >= trailing_stop:
                    exit_price = trailing_stop
                    exit_time = bar.timestamp
                    outcome = TradeOutcome.STOPPED_OUT
                    break
                new_stop = bar.low + trail_atr * atr_val
                trailing_stop = min(trailing_stop, new_stop)
        else:
            exit_price = bars[-1].close

        if direction == TradeDirection.LONG:
            ret_pct = ((exit_price - entry) / entry) * 100.0
        else:
            ret_pct = ((entry - exit_price) / entry) * 100.0

        mfe, mae = self.compute_mfe_mae(bars[:bars_held], entry, direction)

        return TradeRecord(
            symbol=signal.symbol,
            direction=direction,
            entry_price=entry,
            exit_price=exit_price,
            stop_loss=trailing_stop,
            target_price=signal.target_price,
            entry_time=signal.timestamp,
            exit_time=exit_time,
            bars_held=bars_held,
            return_pct=ret_pct,
            return_dollars=(ret_pct / 100.0) * self.default_position_size,
            outcome=outcome,
            mfe_pct=mfe,
            mae_pct=mae,
            signal_confidence=signal.confidence,
            regime_at_entry=signal.regime,
            scanner_name=signal.scanner_name,
            metadata={"trailing_stop": True, "trail_atr": trail_atr},
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _auto_stop(
        self, entry: float, direction: TradeDirection, atr: float
    ) -> float:
        """Generate a default stop-loss at 2x ATR from entry."""
        dist = max(atr * 2.0, entry * 0.02)
        if direction == TradeDirection.LONG:
            return entry - dist
        return entry + dist

    def _auto_target(
        self, entry: float, stop_loss: float, direction: TradeDirection
    ) -> float:
        """Generate a default target at 2:1 risk-reward."""
        risk = abs(entry - stop_loss)
        if direction == TradeDirection.LONG:
            return entry + risk * 2.0
        return entry - risk * 2.0


# =============================================================================
# 4. ScannerBacktestEngine
# =============================================================================

class ScannerBacktestEngine:
    """
    Core backtest engine that evaluates ANY scanner across ANY timeframe.

    Accepts a list of signals and corresponding historical bars,
    simulates every trade, and computes the full suite of performance
    metrics collected in ``ScannerBacktestResult``.
    """

    def __init__(
        self,
        scanner_name: str,
        timeframe: BacktestTimeframe = BacktestTimeframe.D1,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        position_size: float = 10000.0,
        slippage_pct: float = 0.01,
        commission_per_share: float = 0.005,
        max_bars_per_trade: int = 100,
        random_seed: Optional[int] = None,
    ):
        """
        Configure the backtest engine.

        Args:
            scanner_name: Name of the scanner being tested.
            timeframe: Bar timeframe for the backtest.
            start_date: Inclusive start boundary.
            end_date: Inclusive end boundary.
            position_size: Notional dollars per trade.
            slippage_pct: Baseline slippage percentage.
            commission_per_share: Per-share commission.
            max_bars_per_trade: Maximum holding period in bars.
            random_seed: Seed for reproducible simulations.
        """
        self.scanner_name = scanner_name
        self.timeframe = timeframe
        self.start_date = start_date
        self.end_date = end_date
        self.position_size = position_size
        self.max_bars_per_trade = max_bars_per_trade

        self._simulator = TradeSimulator(
            default_slippage_pct=slippage_pct,
            default_commission_per_share=commission_per_share,
            default_position_size=position_size,
            random_seed=random_seed,
        )
        self._logger = logging.getLogger(f"{__name__}.{scanner_name}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_backtest(
        self,
        signals: List[Union[ScanResult, AdvancedScanResult, Dict[str, Any]]],
        historical_bars: List[SimulatedBar],
    ) -> ScannerBacktestResult:
        """
        Execute a full backtest.

        Args:
            signals: Signal list (any supported format).
            historical_bars: Complete bar history sorted by timestamp
                ascending.

        Returns:
            Fully populated ``ScannerBacktestResult``.
        """
        self._logger.info(
            "Starting backtest for %s | tf=%s | signals=%d | bars=%d",
            self.scanner_name,
            self.timeframe.label,
            len(signals),
            len(historical_bars),
        )

        normalised = [_normalise_signal(s) for s in signals]

        if self.start_date:
            normalised = [
                s for s in normalised
                if s.timestamp is None or s.timestamp >= self.start_date
            ]
        if self.end_date:
            normalised = [
                s for s in normalised
                if s.timestamp is None or s.timestamp <= self.end_date
            ]

        aligned = self._align_signals_to_bars(
            normalised, historical_bars, self.timeframe
        )

        trades: List[TradeRecord] = []
        for sig, forward_bars in aligned:
            trade = self._simulator.simulate_trade(
                sig, forward_bars, self.timeframe
            )
            if trade is not None:
                trades.append(trade)

        result = self._compute_metrics(trades)
        result.scanner_name = self.scanner_name
        result.timeframe = self.timeframe.label
        result.start_date = self.start_date
        result.end_date = self.end_date
        result.total_signals = len(normalised)

        self._logger.info(
            "Backtest complete | trades=%d | win_rate=%.2f%% | sharpe=%.3f",
            result.total_trades,
            result.win_rate * 100.0,
            result.sharpe_ratio,
        )
        return result

    # ------------------------------------------------------------------
    # Signal alignment
    # ------------------------------------------------------------------

    def _align_signals_to_bars(
        self,
        signals: List[NormalisedSignal],
        bars: List[SimulatedBar],
        timeframe: BacktestTimeframe,
    ) -> List[Tuple[NormalisedSignal, List[SimulatedBar]]]:
        """
        Match each signal to the bar data beginning at or after the
        signal's timestamp and return a list of (signal, forward_bars)
        pairs.

        Args:
            signals: Normalised signals sorted by timestamp.
            bars: Complete bar history sorted ascending.
            timeframe: Timeframe for context (used to cap look-ahead).

        Returns:
            List of tuples pairing each signal with its forward bars.
        """
        if not bars:
            return []

        bar_timestamps = [b.timestamp for b in bars]
        result: List[Tuple[NormalisedSignal, List[SimulatedBar]]] = []

        for sig in signals:
            if sig.timestamp is None:
                idx = 0
            else:
                idx = self._bisect_left_dt(bar_timestamps, sig.timestamp)

            if idx >= len(bars):
                continue

            end_idx = min(idx + self.max_bars_per_trade, len(bars))
            forward = bars[idx:end_idx]

            if forward:
                result.append((sig, forward))

        return result

    @staticmethod
    def _bisect_left_dt(
        timestamps: List[datetime], target: datetime
    ) -> int:
        """Binary search for the leftmost bar at or after ``target``."""
        lo, hi = 0, len(timestamps)
        while lo < hi:
            mid = (lo + hi) // 2
            if timestamps[mid] < target:
                lo = mid + 1
            else:
                hi = mid
        return lo

    # ------------------------------------------------------------------
    # Metrics computation
    # ------------------------------------------------------------------

    def _compute_metrics(self, trades: List[TradeRecord]) -> ScannerBacktestResult:
        """
        Calculate the full suite of performance metrics from closed trades.

        Args:
            trades: List of completed ``TradeRecord`` instances.

        Returns:
            Populated ``ScannerBacktestResult``.
        """
        res = ScannerBacktestResult()
        res.total_trades = len(trades)

        if not trades:
            return res

        returns = np.array([t.return_pct for t in trades])
        winners = [t for t in trades if t.is_winner]
        losers = [t for t in trades if t.is_loser]
        win_returns = np.array([t.return_pct for t in winners]) if winners else np.array([])
        loss_returns = np.array([t.return_pct for t in losers]) if losers else np.array([])

        # Win / loss rates
        res.win_rate = len(winners) / len(trades) if trades else 0.0
        res.loss_rate = len(losers) / len(trades) if trades else 0.0
        res.breakeven_rate = 1.0 - res.win_rate - res.loss_rate

        # Average returns
        res.avg_win_pct = float(np.mean(win_returns)) if len(win_returns) > 0 else 0.0
        res.avg_loss_pct = float(np.mean(loss_returns)) if len(loss_returns) > 0 else 0.0
        res.avg_trade_pct = float(np.mean(returns))
        res.median_trade_pct = float(np.median(returns))

        # Gross / net
        res.gross_profit = float(np.sum(win_returns)) if len(win_returns) > 0 else 0.0
        res.gross_loss = float(np.sum(loss_returns)) if len(loss_returns) > 0 else 0.0
        res.total_commissions = sum(t.commission_cost for t in trades)
        res.total_slippage = sum(t.slippage_cost for t in trades)
        res.net_profit = res.gross_profit + res.gross_loss

        # Profit factor
        res.profit_factor = self._compute_profit_factor(
            win_returns.tolist() if len(win_returns) > 0 else [],
            loss_returns.tolist() if len(loss_returns) > 0 else [],
        )

        # Expectancy
        res.expectancy = self._compute_expectancy(
            res.win_rate, res.avg_win_pct, res.avg_loss_pct
        )
        avg_loss_abs = abs(res.avg_loss_pct) if res.avg_loss_pct != 0 else 1.0
        res.expectancy_per_dollar = res.expectancy / avg_loss_abs if avg_loss_abs > 0 else 0.0

        # Equity curve and drawdown
        res.equity_curve = self._build_equity_curve(trades)
        dd_pct, dd_dur, avg_dd = self._compute_drawdown(res.equity_curve)
        res.max_drawdown_pct = dd_pct
        res.max_drawdown_duration_bars = dd_dur
        res.avg_drawdown_pct = avg_dd

        # Streaks
        res.max_consecutive_wins, res.max_consecutive_losses = self._compute_streaks(
            trades
        )

        # Ratios
        res.sharpe_ratio = self._compute_sharpe(returns)
        res.sortino_ratio = self._compute_sortino(returns)
        res.calmar_ratio = self._compute_calmar(returns, res.max_drawdown_pct)

        # Holding period
        hold_periods = [t.bars_held for t in trades]
        res.avg_holding_period_bars = float(np.mean(hold_periods))
        res.median_holding_period_bars = float(np.median(hold_periods))

        # Extremes
        best_idx = int(np.argmax(returns))
        worst_idx = int(np.argmin(returns))
        res.best_trade_pct = float(returns[best_idx])
        res.worst_trade_pct = float(returns[worst_idx])
        res.best_trade_id = trades[best_idx].trade_id
        res.worst_trade_id = trades[worst_idx].trade_id

        # Direction breakdown
        res.trades_by_direction = self._direction_breakdown(trades)

        # Monthly returns
        res.monthly_returns = self._monthly_returns(trades)

        # Regime win rate
        res.win_rate_by_regime = self._win_rate_by_regime(trades)

        # Confidence calibration
        res.win_rate_by_confidence = self._win_rate_by_confidence_bucket(trades)

        # Signal decay
        res.signal_decay_curve = self._signal_decay_analysis(trades, _DECAY_MULTIPLES)

        # Rolling win rate
        res.rolling_win_rate = self._rolling_win_rate(trades, _DEFAULT_ROLLING_WINDOW)

        # Wilson score interval
        res.wilson_lower, res.wilson_upper = self._wilson_score(
            res.win_rate, len(trades)
        )

        # Kelly criterion
        res.kelly_fraction = self._kelly_criterion(
            res.win_rate, res.avg_win_pct, res.avg_loss_pct
        )
        res.half_kelly = res.kelly_fraction / 2.0

        # MFE / MAE
        mfe_vals = [t.mfe_pct for t in trades]
        mae_vals = [t.mae_pct for t in trades]
        res.avg_mfe_pct = float(np.mean(mfe_vals)) if mfe_vals else 0.0
        res.avg_mae_pct = float(np.mean(mae_vals)) if mae_vals else 0.0

        # Distribution shape
        if len(returns) >= 3:
            res.skewness = float(self._skewness(returns))
            res.kurtosis = float(self._kurtosis(returns))
        res.tail_ratio = self._tail_ratio(returns)

        return res

    # ------------------------------------------------------------------
    # Individual metric methods
    # ------------------------------------------------------------------

    def _compute_sharpe(self, returns: np.ndarray) -> float:
        """
        Annualised Sharpe ratio.

        Formula:
            Sharpe = (mean(R) - Rf_per_period) / std(R) * sqrt(N)
        where N = periods per year for the given timeframe.

        Args:
            returns: Array of per-trade return percentages.

        Returns:
            Annualised Sharpe ratio. Returns 0 when std is zero.
        """
        if len(returns) < 2:
            return 0.0
        n = self.timeframe.periods_per_year
        rf_per_period = (_RISK_FREE_RATE * 100.0) / n
        excess = returns - rf_per_period
        std = float(np.std(excess, ddof=1))
        if std == 0.0:
            return 0.0
        return float(np.mean(excess)) / std * math.sqrt(n)

    def _compute_sortino(self, returns: np.ndarray) -> float:
        """
        Annualised Sortino ratio.

        Formula:
            Sortino = (mean(R) - Rf_per_period) / downside_std * sqrt(N)

        Downside deviation considers only returns below zero.

        Args:
            returns: Array of per-trade return percentages.

        Returns:
            Annualised Sortino ratio.
        """
        if len(returns) < 2:
            return 0.0
        n = self.timeframe.periods_per_year
        rf_per_period = (_RISK_FREE_RATE * 100.0) / n
        excess = returns - rf_per_period
        downside = excess[excess < 0.0]
        if len(downside) == 0:
            return 0.0
        downside_std = float(np.std(downside, ddof=1))
        if downside_std == 0.0:
            return 0.0
        return float(np.mean(excess)) / downside_std * math.sqrt(n)

    def _compute_calmar(
        self, returns: np.ndarray, max_dd: float
    ) -> float:
        """
        Calmar ratio.

        Formula:
            Calmar = annualised_return / abs(max_drawdown)

        Args:
            returns: Per-trade return percentages.
            max_dd: Maximum drawdown percentage (negative value).

        Returns:
            Calmar ratio.  Returns 0 if max drawdown is zero.
        """
        if abs(max_dd) < 1e-12 or len(returns) == 0:
            return 0.0
        total_return = float(np.sum(returns))
        n = self.timeframe.periods_per_year
        num_periods = len(returns)
        annualised = total_return * (n / num_periods) if num_periods > 0 else 0.0
        return annualised / abs(max_dd)

    @staticmethod
    def _compute_drawdown(
        equity_curve: List[float],
    ) -> Tuple[float, int, float]:
        """
        Maximum drawdown percentage, duration (in bars), and average
        drawdown from an equity curve.

        Args:
            equity_curve: Cumulative equity values.

        Returns:
            Tuple of (max_drawdown_pct, max_duration_bars, avg_drawdown_pct).
        """
        if not equity_curve:
            return 0.0, 0, 0.0

        curve = np.array(equity_curve)
        running_max = np.maximum.accumulate(curve)
        safe_max = np.where(running_max == 0, 1.0, running_max)
        drawdowns = (curve - running_max) / safe_max * 100.0

        max_dd = float(np.min(drawdowns))

        duration = 0
        max_dur = 0
        for i in range(len(drawdowns)):
            if drawdowns[i] < 0:
                duration += 1
                max_dur = max(max_dur, duration)
            else:
                duration = 0

        neg_dd = drawdowns[drawdowns < 0]
        avg_dd = float(np.mean(neg_dd)) if len(neg_dd) > 0 else 0.0

        return max_dd, max_dur, avg_dd

    @staticmethod
    def _compute_profit_factor(
        wins: List[float], losses: List[float]
    ) -> float:
        """
        Profit factor = gross_profit / abs(gross_loss).

        Args:
            wins: Positive return percentages.
            losses: Negative return percentages.

        Returns:
            Profit factor. Returns ``float('inf')`` when there are no losses.
        """
        gross_profit = sum(wins) if wins else 0.0
        gross_loss = abs(sum(losses)) if losses else 0.0
        if gross_loss == 0.0:
            return float("inf") if gross_profit > 0 else 0.0
        return gross_profit / gross_loss

    @staticmethod
    def _compute_expectancy(
        win_rate: float, avg_win: float, avg_loss: float
    ) -> float:
        """
        Mathematical expectancy per trade.

        Formula:
            E = P(win) * avg_win - P(loss) * abs(avg_loss)

        Args:
            win_rate: Probability of winning (0-1).
            avg_win: Average winning return percentage.
            avg_loss: Average losing return percentage (typically negative).

        Returns:
            Expected return per trade in percentage points.
        """
        return win_rate * avg_win - (1.0 - win_rate) * abs(avg_loss)

    @staticmethod
    def _rolling_win_rate(
        trades: List[TradeRecord], window: int = 50
    ) -> List[float]:
        """
        Compute a rolling win-rate series over a sliding window of N trades.

        Args:
            trades: Chronological list of trade records.
            window: Number of trades in the rolling window.

        Returns:
            List of rolling win-rate values (one per trade after the
            initial window is filled).
        """
        if len(trades) < window:
            if not trades:
                return []
            wins_so_far = 0
            result = []
            for i, t in enumerate(trades):
                if t.is_winner:
                    wins_so_far += 1
                result.append(wins_so_far / (i + 1))
            return result

        result: List[float] = []
        win_deque: deque = deque()
        wins = 0

        for i, t in enumerate(trades):
            is_w = 1 if t.is_winner else 0
            win_deque.append(is_w)
            wins += is_w
            if len(win_deque) > window:
                wins -= win_deque.popleft()
            if i >= window - 1:
                result.append(wins / window)

        return result

    @staticmethod
    def _win_rate_by_regime(
        trades: List[TradeRecord],
    ) -> Dict[str, float]:
        """
        Break down win rate by the market regime at entry.

        Args:
            trades: Trade records with ``regime_at_entry`` populated.

        Returns:
            Mapping of ``RegimeContext`` value to win rate.
        """
        buckets: Dict[str, List[bool]] = defaultdict(list)
        for t in trades:
            buckets[t.regime_at_entry.value].append(t.is_winner)
        return {
            regime: (sum(wins) / len(wins) if wins else 0.0)
            for regime, wins in buckets.items()
        }

    @staticmethod
    def _win_rate_by_confidence_bucket(
        trades: List[TradeRecord],
    ) -> Dict[str, float]:
        """
        Break down win rate by signal confidence buckets.

        Buckets: 0-20, 20-40, 40-60, 60-80, 80-100.

        Args:
            trades: Trade records with ``signal_confidence`` (0-100).

        Returns:
            Mapping of bucket label to win rate.
        """
        buckets: Dict[str, List[bool]] = defaultdict(list)
        for t in trades:
            for lo, hi in _CONFIDENCE_BUCKETS:
                if lo <= t.signal_confidence < hi or (hi == 100.0 and t.signal_confidence == 100.0):
                    label = f"{int(lo)}-{int(hi)}"
                    buckets[label].append(t.is_winner)
                    break
        return {
            label: (sum(wins) / len(wins) if wins else 0.0)
            for label, wins in buckets.items()
        }

    @staticmethod
    def _signal_decay_analysis(
        trades: List[TradeRecord],
        multiples: List[int],
    ) -> List[float]:
        """
        Signal decay analysis: average return at 1x, 2x, 3x, 5x, 10x
        the expected holding period.

        Approximated by bucketing trades by how long they were held
        relative to the median holding period.

        Args:
            trades: Trade records.
            multiples: Multiples of the median holding period to examine.

        Returns:
            Average return at each multiple.  Missing buckets return 0.
        """
        if not trades:
            return [0.0] * len(multiples)

        hold_bars = [t.bars_held for t in trades]
        median_hold = float(np.median(hold_bars)) if hold_bars else 1.0
        if median_hold < 1.0:
            median_hold = 1.0

        result: List[float] = []
        for mult in multiples:
            target = median_hold * mult
            lower = target * 0.5
            upper = target * 1.5
            bucket = [
                t.return_pct for t in trades if lower <= t.bars_held <= upper
            ]
            result.append(float(np.mean(bucket)) if bucket else 0.0)

        return result

    # ------------------------------------------------------------------
    # Statistical helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _wilson_score(
        p_hat: float, n: int, z: float = _WILSON_Z
    ) -> Tuple[float, float]:
        """
        Wilson score confidence interval for a binomial proportion.

        Formula:
            lower, upper = (p_hat + z^2/(2n) -/+ z*sqrt(p_hat*(1-p_hat)/n
                            + z^2/(4n^2))) / (1 + z^2/n)

        Args:
            p_hat: Observed proportion (win rate).
            n: Sample size (number of trades).
            z: Z-value for the desired confidence level.

        Returns:
            Tuple of (lower_bound, upper_bound).
        """
        if n == 0:
            return 0.0, 0.0
        z2 = z * z
        denom = 1.0 + z2 / n
        centre = p_hat + z2 / (2.0 * n)
        spread = z * math.sqrt(p_hat * (1.0 - p_hat) / n + z2 / (4.0 * n * n))
        lower = (centre - spread) / denom
        upper = (centre + spread) / denom
        return max(0.0, lower), min(1.0, upper)

    @staticmethod
    def _kelly_criterion(
        win_rate: float, avg_win: float, avg_loss: float
    ) -> float:
        """
        Kelly criterion for optimal bet sizing.

        Formula:
            f = (b*p - q) / b
        where b = avg_win / abs(avg_loss), p = win_rate, q = 1 - p.

        Args:
            win_rate: Probability of winning.
            avg_win: Average winning return.
            avg_loss: Average losing return (negative).

        Returns:
            Kelly fraction (can be negative, meaning do not bet).
        """
        if avg_loss == 0.0 or win_rate <= 0.0:
            return 0.0
        b = abs(avg_win / avg_loss) if avg_loss != 0.0 else 0.0
        if b == 0.0:
            return 0.0
        p = win_rate
        q = 1.0 - p
        return (b * p - q) / b

    @staticmethod
    def _skewness(arr: np.ndarray) -> float:
        """Sample skewness (Fisher definition)."""
        n = len(arr)
        if n < 3:
            return 0.0
        mean = float(np.mean(arr))
        std = float(np.std(arr, ddof=1))
        if std == 0.0:
            return 0.0
        m3 = float(np.mean((arr - mean) ** 3))
        return m3 / (std ** 3)

    @staticmethod
    def _kurtosis(arr: np.ndarray) -> float:
        """Excess kurtosis (Fisher definition)."""
        n = len(arr)
        if n < 4:
            return 0.0
        mean = float(np.mean(arr))
        std = float(np.std(arr, ddof=1))
        if std == 0.0:
            return 0.0
        m4 = float(np.mean((arr - mean) ** 4))
        return m4 / (std ** 4) - 3.0

    @staticmethod
    def _tail_ratio(returns: np.ndarray) -> float:
        """
        Tail ratio = abs(95th percentile) / abs(5th percentile).

        A ratio > 1 indicates the right tail is fatter (good skew).
        """
        if len(returns) < 5:
            return 0.0
        p95 = float(np.percentile(returns, 95))
        p5 = float(np.percentile(returns, 5))
        if abs(p5) < 1e-12:
            return 0.0
        return abs(p95) / abs(p5)

    # ------------------------------------------------------------------
    # Equity curve and streaks
    # ------------------------------------------------------------------

    @staticmethod
    def _build_equity_curve(trades: List[TradeRecord]) -> List[float]:
        """Build cumulative equity curve starting at 10000."""
        equity = 10000.0
        curve = [equity]
        for t in trades:
            equity *= (1.0 + t.return_pct / 100.0)
            curve.append(equity)
        return curve

    @staticmethod
    def _compute_streaks(
        trades: List[TradeRecord],
    ) -> Tuple[int, int]:
        """Return (max_consecutive_wins, max_consecutive_losses)."""
        max_w = 0
        max_l = 0
        cur_w = 0
        cur_l = 0
        for t in trades:
            if t.is_winner:
                cur_w += 1
                cur_l = 0
                max_w = max(max_w, cur_w)
            elif t.is_loser:
                cur_l += 1
                cur_w = 0
                max_l = max(max_l, cur_l)
            else:
                cur_w = 0
                cur_l = 0
        return max_w, max_l

    @staticmethod
    def _direction_breakdown(
        trades: List[TradeRecord],
    ) -> Dict[str, Dict[str, Any]]:
        """Win rate, count, and avg return by LONG / SHORT."""
        breakdown: Dict[str, Dict[str, Any]] = {}
        for direction in TradeDirection:
            subset = [t for t in trades if t.direction == direction]
            if not subset:
                breakdown[direction.value] = {
                    "count": 0,
                    "win_rate": 0.0,
                    "avg_return_pct": 0.0,
                }
                continue
            wins = sum(1 for t in subset if t.is_winner)
            breakdown[direction.value] = {
                "count": len(subset),
                "win_rate": wins / len(subset),
                "avg_return_pct": float(
                    np.mean([t.return_pct for t in subset])
                ),
            }
        return breakdown

    @staticmethod
    def _monthly_returns(trades: List[TradeRecord]) -> List[float]:
        """
        Aggregate per-trade returns into calendar-month return buckets.

        Returns:
            List of monthly return percentages (compounded within month).
        """
        if not trades:
            return []

        month_map: Dict[str, float] = {}
        for t in trades:
            if t.exit_time:
                key = t.exit_time.strftime("%Y-%m")
            elif t.entry_time:
                key = t.entry_time.strftime("%Y-%m")
            else:
                continue
            if key not in month_map:
                month_map[key] = 0.0
            month_map[key] += t.return_pct

        sorted_keys = sorted(month_map.keys())
        return [month_map[k] for k in sorted_keys]


# =============================================================================
# 5. MultiTimeframeBacktest
# =============================================================================

class MultiTimeframeBacktest:
    """
    Run the same scanner across every available timeframe and identify
    the optimal operating frequency.
    """

    def __init__(
        self,
        position_size: float = 10000.0,
        slippage_pct: float = 0.01,
        commission_per_share: float = 0.005,
        max_bars_per_trade: int = 100,
        random_seed: Optional[int] = None,
    ):
        """
        Initialise the multi-timeframe harness.

        Args:
            position_size: Notional dollars per trade.
            slippage_pct: Baseline slippage.
            commission_per_share: Per-share commission.
            max_bars_per_trade: Max bars before time exit.
            random_seed: Reproducibility seed.
        """
        self.position_size = position_size
        self.slippage_pct = slippage_pct
        self.commission_per_share = commission_per_share
        self.max_bars_per_trade = max_bars_per_trade
        self.random_seed = random_seed
        self._logger = logging.getLogger(f"{__name__}.MultiTF")

    def run_all_timeframes(
        self,
        scanner_name: str,
        signals: List[Union[ScanResult, AdvancedScanResult, Dict[str, Any]]],
        bars_by_tf: Dict[BacktestTimeframe, List[SimulatedBar]],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[BacktestTimeframe, ScannerBacktestResult]:
        """
        Run a full backtest at every timeframe that has bar data.

        Args:
            scanner_name: Scanner identifier.
            signals: Signal list.
            bars_by_tf: Mapping of timeframe to bar list.
            start_date: Optional start filter.
            end_date: Optional end filter.

        Returns:
            Mapping of timeframe to backtest result.
        """
        results: Dict[BacktestTimeframe, ScannerBacktestResult] = {}

        for tf, bars in bars_by_tf.items():
            self._logger.info(
                "Running %s backtest on %s (%d bars)",
                scanner_name,
                tf.label,
                len(bars),
            )
            engine = ScannerBacktestEngine(
                scanner_name=scanner_name,
                timeframe=tf,
                start_date=start_date,
                end_date=end_date,
                position_size=self.position_size,
                slippage_pct=self.slippage_pct,
                commission_per_share=self.commission_per_share,
                max_bars_per_trade=self.max_bars_per_trade,
                random_seed=self.random_seed,
            )
            results[tf] = engine.run_backtest(signals, bars)

        return results

    @staticmethod
    def compare_timeframes(
        results: Dict[BacktestTimeframe, ScannerBacktestResult],
    ) -> Dict[str, Any]:
        """
        Rank timeframes by Sharpe, win rate, and profit factor.

        Args:
            results: Per-timeframe backtest results.

        Returns:
            Dictionary with ``best_by_sharpe``, ``best_by_win_rate``,
            ``best_by_profit_factor``, and a ``rankings`` list.
        """
        if not results:
            return {
                "best_by_sharpe": None,
                "best_by_win_rate": None,
                "best_by_profit_factor": None,
                "rankings": [],
            }

        ranking = []
        for tf, res in results.items():
            ranking.append({
                "timeframe": tf.label,
                "sharpe": res.sharpe_ratio,
                "win_rate": res.win_rate,
                "profit_factor": res.profit_factor,
                "total_trades": res.total_trades,
                "max_drawdown_pct": res.max_drawdown_pct,
                "expectancy": res.expectancy,
            })

        by_sharpe = sorted(ranking, key=lambda x: x["sharpe"], reverse=True)
        by_wr = sorted(ranking, key=lambda x: x["win_rate"], reverse=True)
        by_pf = sorted(ranking, key=lambda x: x["profit_factor"], reverse=True)

        return {
            "best_by_sharpe": by_sharpe[0]["timeframe"] if by_sharpe else None,
            "best_by_win_rate": by_wr[0]["timeframe"] if by_wr else None,
            "best_by_profit_factor": by_pf[0]["timeframe"] if by_pf else None,
            "rankings": by_sharpe,
        }

    @staticmethod
    def optimal_timeframe_selection(
        results: Dict[BacktestTimeframe, ScannerBacktestResult],
        sharpe_weight: float = 0.40,
        win_rate_weight: float = 0.25,
        profit_factor_weight: float = 0.20,
        drawdown_weight: float = 0.15,
    ) -> Optional[BacktestTimeframe]:
        """
        Select the best timeframe using a weighted composite score.

        The composite normalises each metric across timeframes, then
        applies the supplied weights.  Max drawdown is inverted so that
        smaller drawdowns score higher.

        Args:
            results: Per-timeframe backtest results.
            sharpe_weight: Weight for Sharpe ratio component.
            win_rate_weight: Weight for win-rate component.
            profit_factor_weight: Weight for profit factor component.
            drawdown_weight: Weight for (inverted) max-drawdown component.

        Returns:
            The ``BacktestTimeframe`` with the highest composite score,
            or ``None`` if no results are available.
        """
        if not results:
            return None

        entries: List[Tuple[BacktestTimeframe, float, float, float, float]] = []
        for tf, res in results.items():
            pf = res.profit_factor if not math.isinf(res.profit_factor) else 10.0
            entries.append((
                tf,
                res.sharpe_ratio,
                res.win_rate,
                pf,
                abs(res.max_drawdown_pct),
            ))

        def _normalise(values: List[float]) -> List[float]:
            mn, mx = min(values), max(values)
            rng = mx - mn
            if rng < 1e-12:
                return [0.5] * len(values)
            return [(v - mn) / rng for v in values]

        sharpes = _normalise([e[1] for e in entries])
        wrs = _normalise([e[2] for e in entries])
        pfs = _normalise([e[3] for e in entries])
        dds_raw = [e[4] for e in entries]
        dds = _normalise(dds_raw)
        dds_inv = [1.0 - d for d in dds]

        best_tf = None
        best_score = -float("inf")
        for i, (tf, *_) in enumerate(entries):
            score = (
                sharpe_weight * sharpes[i]
                + win_rate_weight * wrs[i]
                + profit_factor_weight * pfs[i]
                + drawdown_weight * dds_inv[i]
            )
            if score > best_score:
                best_score = score
                best_tf = tf

        return best_tf


# =============================================================================
# 6. ScannerPerformanceTracker
# =============================================================================

@dataclass
class LiveSignalRecord:
    """Internal record for a tracked live signal."""
    signal_id: str = ""
    signal: Optional[NormalisedSignal] = None
    registered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    outcome_return_pct: Optional[float] = None
    outcome_recorded_at: Optional[datetime] = None
    is_resolved: bool = False


class ScannerPerformanceTracker:
    """
    Live performance tracking for deployed scanners.

    Collects signals as they fire and records their actual outcomes,
    enabling real-time comparison against historical backtest baselines.
    """

    def __init__(self, scanner_name: str = ""):
        """
        Initialise the live performance tracker.

        Args:
            scanner_name: Name of the scanner being tracked.
        """
        self.scanner_name = scanner_name
        self._signals: Dict[str, LiveSignalRecord] = {}
        self._logger = logging.getLogger(
            f"{__name__}.LiveTracker.{scanner_name}"
        )

    # ------------------------------------------------------------------
    # Signal registration
    # ------------------------------------------------------------------

    def register_signal(
        self,
        signal: Union[ScanResult, AdvancedScanResult, Dict[str, Any]],
    ) -> str:
        """
        Register a new live signal for tracking.

        Args:
            signal: Any supported signal type.

        Returns:
            The signal ID assigned to this signal for later updates.
        """
        ns = _normalise_signal(signal)
        rec = LiveSignalRecord(
            signal_id=ns.signal_id,
            signal=ns,
        )
        self._signals[ns.signal_id] = rec
        self._logger.debug("Registered signal %s", ns.signal_id)
        return ns.signal_id

    def update_signal_outcome(
        self,
        signal_id: str,
        outcome_return_pct: float,
    ) -> bool:
        """
        Record the actual outcome of a previously registered signal.

        Args:
            signal_id: Signal ID returned by ``register_signal``.
            outcome_return_pct: Realised return percentage.

        Returns:
            ``True`` if the signal was found and updated, ``False`` otherwise.
        """
        rec = self._signals.get(signal_id)
        if rec is None:
            self._logger.warning("Signal %s not found", signal_id)
            return False
        rec.outcome_return_pct = outcome_return_pct
        rec.outcome_recorded_at = datetime.now(timezone.utc)
        rec.is_resolved = True
        return True

    # ------------------------------------------------------------------
    # Live statistics
    # ------------------------------------------------------------------

    def compute_live_stats(self) -> Dict[str, Any]:
        """
        Compute real-time performance statistics from resolved signals.

        Returns:
            Dictionary with ``total_signals``, ``resolved``, ``win_rate``,
            ``avg_return_pct``, ``sharpe_estimate``, ``current_drawdown_pct``,
            and ``max_drawdown_pct``.
        """
        resolved = [
            r for r in self._signals.values() if r.is_resolved
        ]
        total = len(self._signals)
        n_resolved = len(resolved)

        if n_resolved == 0:
            return {
                "total_signals": total,
                "resolved": 0,
                "win_rate": 0.0,
                "avg_return_pct": 0.0,
                "sharpe_estimate": 0.0,
                "current_drawdown_pct": 0.0,
                "max_drawdown_pct": 0.0,
            }

        returns = np.array([r.outcome_return_pct for r in resolved])
        wins = int(np.sum(returns > 0))
        wr = wins / n_resolved

        avg_ret = float(np.mean(returns))
        std_ret = float(np.std(returns, ddof=1)) if n_resolved > 1 else 1.0
        sharpe_est = (avg_ret / std_ret) * math.sqrt(252) if std_ret > 0 else 0.0

        equity = 10000.0
        peak = equity
        max_dd = 0.0
        for r in resolved:
            equity *= (1.0 + r.outcome_return_pct / 100.0)
            peak = max(peak, equity)
            dd = (equity - peak) / peak * 100.0 if peak > 0 else 0.0
            max_dd = min(max_dd, dd)

        cur_dd = (equity - peak) / peak * 100.0 if peak > 0 else 0.0

        return {
            "total_signals": total,
            "resolved": n_resolved,
            "win_rate": wr,
            "avg_return_pct": avg_ret,
            "sharpe_estimate": sharpe_est,
            "current_drawdown_pct": cur_dd,
            "max_drawdown_pct": max_dd,
        }

    def compare_live_vs_backtest(
        self,
        live_stats: Dict[str, Any],
        backtest_stats: ScannerBacktestResult,
    ) -> Dict[str, Any]:
        """
        Compare live performance against the historical backtest.

        Flags potential overfitting when live performance is materially
        below the backtest baseline.

        Args:
            live_stats: Output from ``compute_live_stats()``.
            backtest_stats: Historical backtest result to compare against.

        Returns:
            Dictionary with per-metric comparisons and a summary
            ``degradation_detected`` flag.
        """
        live_wr = live_stats.get("win_rate", 0.0)
        bt_wr = backtest_stats.win_rate
        live_sharpe = live_stats.get("sharpe_estimate", 0.0)
        bt_sharpe = backtest_stats.sharpe_ratio

        wr_delta = live_wr - bt_wr
        sharpe_delta = live_sharpe - bt_sharpe

        wr_degraded = wr_delta < -0.10
        sharpe_degraded = bt_sharpe > 0 and live_sharpe < bt_sharpe * 0.5

        return {
            "live_win_rate": live_wr,
            "backtest_win_rate": bt_wr,
            "win_rate_delta": wr_delta,
            "live_sharpe": live_sharpe,
            "backtest_sharpe": bt_sharpe,
            "sharpe_delta": sharpe_delta,
            "win_rate_degraded": wr_degraded,
            "sharpe_degraded": sharpe_degraded,
            "degradation_detected": wr_degraded or sharpe_degraded,
            "overfitting_warning": (
                "Live performance significantly below backtest. "
                "Possible overfitting or regime change."
                if wr_degraded or sharpe_degraded
                else "Performance within expected range."
            ),
        }

    def confidence_calibration_check(
        self,
        signals: Optional[List[Union[ScanResult, AdvancedScanResult, Dict[str, Any]]]] = None,
        outcomes: Optional[List[float]] = None,
    ) -> Dict[str, Dict[str, float]]:
        """
        Test whether high-confidence signals actually win more often.

        An 80 % confidence signal should win approximately 80 % of the
        time.  This method checks calibration across the standard
        confidence buckets.

        Args:
            signals: Optional external signal list.  When ``None``, uses
                internally tracked signals.
            outcomes: Corresponding return percentages (same length as
                ``signals``).  Ignored when using internal signals.

        Returns:
            Per-bucket mapping of ``expected_win_rate`` (bucket midpoint)
            and ``actual_win_rate``.
        """
        pairs: List[Tuple[float, bool]] = []

        if signals is not None and outcomes is not None:
            for sig, ret in zip(signals, outcomes):
                ns = _normalise_signal(sig)
                pairs.append((ns.confidence, ret > 0))
        else:
            for rec in self._signals.values():
                if rec.is_resolved and rec.signal is not None:
                    pairs.append((
                        rec.signal.confidence,
                        (rec.outcome_return_pct or 0.0) > 0,
                    ))

        if not pairs:
            return {}

        result: Dict[str, Dict[str, float]] = {}
        for lo, hi in _CONFIDENCE_BUCKETS:
            label = f"{int(lo)}-{int(hi)}"
            bucket_wins = [
                w for c, w in pairs if lo <= c < hi or (hi == 100 and c == 100)
            ]
            if not bucket_wins:
                continue
            result[label] = {
                "expected_win_rate": (lo + hi) / 200.0,
                "actual_win_rate": sum(bucket_wins) / len(bucket_wins),
                "sample_size": float(len(bucket_wins)),
                "calibration_error": abs(
                    (lo + hi) / 200.0 - sum(bucket_wins) / len(bucket_wins)
                ),
            }

        return result

    def regime_performance_monitor(
        self,
        signals: Optional[List[Union[ScanResult, AdvancedScanResult, Dict[str, Any]]]] = None,
        outcomes: Optional[List[float]] = None,
        regime_history: Optional[List[RegimeContext]] = None,
    ) -> Dict[str, Dict[str, float]]:
        """
        Identify which regimes the scanner is failing in.

        Args:
            signals: Optional external signal list.
            outcomes: Corresponding return percentages.
            regime_history: Regime at the time of each signal.

        Returns:
            Per-regime breakdown of win rate, average return, and count.
        """
        triples: List[Tuple[RegimeContext, float, bool]] = []

        if signals is not None and outcomes is not None and regime_history is not None:
            for sig, ret, reg in zip(signals, outcomes, regime_history):
                triples.append((reg, ret, ret > 0))
        else:
            for rec in self._signals.values():
                if rec.is_resolved and rec.signal is not None:
                    triples.append((
                        rec.signal.regime,
                        rec.outcome_return_pct or 0.0,
                        (rec.outcome_return_pct or 0.0) > 0,
                    ))

        if not triples:
            return {}

        buckets: Dict[str, List[Tuple[float, bool]]] = defaultdict(list)
        for reg, ret, win in triples:
            buckets[reg.value].append((ret, win))

        result: Dict[str, Dict[str, float]] = {}
        for regime, data in buckets.items():
            returns = [d[0] for d in data]
            wins = [d[1] for d in data]
            result[regime] = {
                "count": float(len(data)),
                "win_rate": sum(wins) / len(wins) if wins else 0.0,
                "avg_return_pct": float(np.mean(returns)) if returns else 0.0,
                "total_return_pct": float(np.sum(returns)) if returns else 0.0,
            }

        return result


# =============================================================================
# 7. BacktestReportGenerator
# =============================================================================

class BacktestReportGenerator:
    """
    Generate structured reports, equity curves, heatmaps, and comparison
    tables from backtest results.
    """

    def __init__(self):
        """Initialise the report generator."""
        self._logger = logging.getLogger(f"{__name__}.ReportGen")

    def generate_report(
        self, result: ScannerBacktestResult
    ) -> Dict[str, Any]:
        """
        Produce a full backtest report as a nested dictionary suitable
        for JSON serialisation or rendering.

        Args:
            result: A completed backtest result.

        Returns:
            Hierarchically organised report dictionary.
        """
        report: Dict[str, Any] = {
            "meta": {
                "backtest_run_id": result.backtest_run_id,
                "scanner_name": result.scanner_name,
                "timeframe": result.timeframe,
                "start_date": result.start_date.isoformat() if result.start_date else None,
                "end_date": result.end_date.isoformat() if result.end_date else None,
                "generated_at": result.generated_at.isoformat(),
            },
            "overview": {
                "total_signals": result.total_signals,
                "total_trades": result.total_trades,
                "win_rate": round(result.win_rate * 100, 2),
                "loss_rate": round(result.loss_rate * 100, 2),
                "breakeven_rate": round(result.breakeven_rate * 100, 2),
                "profit_factor": round(result.profit_factor, 3),
                "expectancy_pct": round(result.expectancy, 4),
                "net_profit_pct": round(result.net_profit, 4),
            },
            "risk_adjusted": {
                "sharpe_ratio": round(result.sharpe_ratio, 4),
                "sortino_ratio": round(result.sortino_ratio, 4),
                "calmar_ratio": round(result.calmar_ratio, 4),
                "max_drawdown_pct": round(result.max_drawdown_pct, 4),
                "max_drawdown_duration_bars": result.max_drawdown_duration_bars,
                "avg_drawdown_pct": round(result.avg_drawdown_pct, 4),
            },
            "returns": {
                "avg_win_pct": round(result.avg_win_pct, 4),
                "avg_loss_pct": round(result.avg_loss_pct, 4),
                "avg_trade_pct": round(result.avg_trade_pct, 4),
                "median_trade_pct": round(result.median_trade_pct, 4),
                "best_trade_pct": round(result.best_trade_pct, 4),
                "worst_trade_pct": round(result.worst_trade_pct, 4),
                "gross_profit_pct": round(result.gross_profit, 4),
                "gross_loss_pct": round(result.gross_loss, 4),
            },
            "streaks": {
                "max_consecutive_wins": result.max_consecutive_wins,
                "max_consecutive_losses": result.max_consecutive_losses,
            },
            "holding_period": {
                "avg_bars": round(result.avg_holding_period_bars, 2),
                "median_bars": round(result.median_holding_period_bars, 2),
            },
            "statistical": {
                "wilson_lower": round(result.wilson_lower, 4),
                "wilson_upper": round(result.wilson_upper, 4),
                "kelly_fraction": round(result.kelly_fraction, 4),
                "half_kelly": round(result.half_kelly, 4),
                "skewness": round(result.skewness, 4),
                "kurtosis": round(result.kurtosis, 4),
                "tail_ratio": round(result.tail_ratio, 4),
            },
            "costs": {
                "total_commissions": round(result.total_commissions, 4),
                "total_slippage": round(result.total_slippage, 4),
            },
            "excursion": {
                "avg_mfe_pct": round(result.avg_mfe_pct, 4),
                "avg_mae_pct": round(result.avg_mae_pct, 4),
            },
            "direction_breakdown": result.trades_by_direction,
            "regime_breakdown": result.win_rate_by_regime,
            "confidence_calibration": result.win_rate_by_confidence,
            "signal_decay": result.signal_decay_curve,
            "rolling_win_rate": result.rolling_win_rate,
            "monthly_returns": result.monthly_returns,
        }
        return report

    def generate_comparison_report(
        self,
        results_by_scanner: Dict[str, ScannerBacktestResult],
    ) -> Dict[str, Any]:
        """
        Compare multiple scanners side-by-side.

        Args:
            results_by_scanner: Mapping of scanner name to its backtest
                result.

        Returns:
            Comparison report with per-scanner rows and overall rankings.
        """
        rows: List[Dict[str, Any]] = []
        for name, res in results_by_scanner.items():
            rows.append({
                "scanner": name,
                "timeframe": res.timeframe,
                "total_trades": res.total_trades,
                "win_rate": round(res.win_rate, 4),
                "profit_factor": round(res.profit_factor, 4),
                "sharpe": round(res.sharpe_ratio, 4),
                "sortino": round(res.sortino_ratio, 4),
                "calmar": round(res.calmar_ratio, 4),
                "max_drawdown_pct": round(res.max_drawdown_pct, 4),
                "expectancy": round(res.expectancy, 4),
                "kelly": round(res.kelly_fraction, 4),
                "avg_holding_bars": round(res.avg_holding_period_bars, 2),
                "best_trade_pct": round(res.best_trade_pct, 4),
                "worst_trade_pct": round(res.worst_trade_pct, 4),
                "net_profit_pct": round(res.net_profit, 4),
            })

        by_sharpe = sorted(rows, key=lambda r: r["sharpe"], reverse=True)
        by_wr = sorted(rows, key=lambda r: r["win_rate"], reverse=True)
        by_pf = sorted(rows, key=lambda r: r["profit_factor"], reverse=True)
        by_calmar = sorted(rows, key=lambda r: r["calmar"], reverse=True)

        return {
            "scanners": rows,
            "rankings": {
                "by_sharpe": [r["scanner"] for r in by_sharpe],
                "by_win_rate": [r["scanner"] for r in by_wr],
                "by_profit_factor": [r["scanner"] for r in by_pf],
                "by_calmar": [r["scanner"] for r in by_calmar],
            },
            "best_overall": by_sharpe[0]["scanner"] if by_sharpe else None,
        }

    @staticmethod
    def equity_curve(
        trades: List[TradeRecord],
        starting_equity: float = 10000.0,
    ) -> List[Dict[str, Any]]:
        """
        Generate equity curve data points from a list of trade records.

        Args:
            trades: Chronological trade list.
            starting_equity: Initial equity value.

        Returns:
            List of dicts with ``index``, ``equity``, ``trade_id``, and
            ``return_pct`` for each point.
        """
        equity = starting_equity
        curve: List[Dict[str, Any]] = [
            {"index": 0, "equity": equity, "trade_id": None, "return_pct": 0.0}
        ]
        for i, t in enumerate(trades):
            equity *= (1.0 + t.return_pct / 100.0)
            curve.append({
                "index": i + 1,
                "equity": round(equity, 4),
                "trade_id": t.trade_id,
                "return_pct": round(t.return_pct, 6),
                "timestamp": t.exit_time.isoformat() if t.exit_time else None,
            })
        return curve

    @staticmethod
    def monthly_return_heatmap(
        trades: List[TradeRecord],
    ) -> Dict[str, Dict[str, float]]:
        """
        Build a month x year heatmap of compounded returns.

        Args:
            trades: Trade records with timestamps.

        Returns:
            Nested dict ``{year: {month_name: return_pct}}``.
        """
        month_names = [
            "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
        ]
        grid: Dict[str, Dict[str, float]] = defaultdict(
            lambda: {m: 0.0 for m in month_names}
        )

        for t in trades:
            dt = t.exit_time or t.entry_time
            if dt is None:
                continue
            year_str = str(dt.year)
            month_str = month_names[dt.month - 1]
            grid[year_str][month_str] += t.return_pct

        return {
            year: dict(months) for year, months in sorted(grid.items())
        }

    @staticmethod
    def drawdown_chart_data(
        equity_curve: List[float],
    ) -> List[Dict[str, Any]]:
        """
        Compute drawdown percentage at every point on the equity curve.

        Args:
            equity_curve: Cumulative equity values (e.g. from
                ``ScannerBacktestResult.equity_curve``).

        Returns:
            List of dicts with ``index``, ``equity``, ``peak``, and
            ``drawdown_pct``.
        """
        if not equity_curve:
            return []

        curve = np.array(equity_curve)
        running_max = np.maximum.accumulate(curve)

        points: List[Dict[str, Any]] = []
        for i in range(len(curve)):
            peak = running_max[i]
            dd = ((curve[i] - peak) / peak * 100.0) if peak > 0 else 0.0
            points.append({
                "index": i,
                "equity": round(float(curve[i]), 4),
                "peak": round(float(peak), 4),
                "drawdown_pct": round(float(dd), 4),
            })
        return points


# =============================================================================
# Module-level convenience functions
# =============================================================================

def quick_backtest(
    scanner_name: str,
    signals: List[Union[ScanResult, AdvancedScanResult, Dict[str, Any]]],
    bars: List[SimulatedBar],
    timeframe: BacktestTimeframe = BacktestTimeframe.D1,
    position_size: float = 10000.0,
) -> ScannerBacktestResult:
    """
    One-liner convenience function for running a backtest.

    Args:
        scanner_name: Scanner identifier.
        signals: Signal list.
        bars: Bar data.
        timeframe: Timeframe.
        position_size: Notional per trade.

    Returns:
        Complete ``ScannerBacktestResult``.
    """
    engine = ScannerBacktestEngine(
        scanner_name=scanner_name,
        timeframe=timeframe,
        position_size=position_size,
    )
    return engine.run_backtest(signals, bars)


def quick_multi_timeframe(
    scanner_name: str,
    signals: List[Union[ScanResult, AdvancedScanResult, Dict[str, Any]]],
    bars_by_tf: Dict[BacktestTimeframe, List[SimulatedBar]],
) -> Tuple[Dict[BacktestTimeframe, ScannerBacktestResult], Optional[BacktestTimeframe]]:
    """
    Run backtests at all available timeframes and return the optimal one.

    Args:
        scanner_name: Scanner identifier.
        signals: Signal list.
        bars_by_tf: Bar data per timeframe.

    Returns:
        Tuple of (results dict, optimal timeframe).
    """
    mtf = MultiTimeframeBacktest()
    results = mtf.run_all_timeframes(scanner_name, signals, bars_by_tf)
    best = mtf.optimal_timeframe_selection(results)
    return results, best
