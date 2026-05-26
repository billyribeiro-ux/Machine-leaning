"""
SCANIFY SPX 0DTE Options Day Trading Scanner -- Exit Management System

Exit management is where 90% of 0DTE traders fail.  This module enforces
disciplined, systematic exits through a layered priority system:

    1. Absolute time stop (3:45 PM ET -- non-negotiable)
    2. VIX1D spike stop (> 25% in 5 minutes -- exit ALL)
    3. GEX flip stop (price crosses gamma flip against position)
    4. Signal reversal stop (composite direction score flipped sign)
    5. Stop loss (initial 50% or time-based 30% after 30 min)
    6. Profit target / trailing stop (time-scaled, zone-aware)
    7. Break-even management (protect gains, reduce risk)

Every position gets a complete TradeLog on close, capturing P&L,
hold time, optimal exit (hindsight), and left-on-table metrics for
the self-learning feedback loop.

CRITICAL SAFETY RULES:
    - NO NAKED SHORT POSITIONS. EVER.
    - ALL positions closed by 3:45 PM ET.
    - Max risk per trade: 2% of daily risk budget.
    - VIX spike = immediate full liquidation.

Author: SCANIFY Engine
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Tuple

from .models import (
    DirectionScore,
    ExitReason,
    GEXProfile,
    ScanSignal,
    ScanType,
    SessionType,
    TimeZoneType,
    TradeDirection,
    TradeLog,
)

# ---------------------------------------------------------------------------
# Module-level logger
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (local to exit manager; structural constants live in constants.py)
# ---------------------------------------------------------------------------

# SPX option multiplier -- $100 per index point
_MULTIPLIER: float = 100.0

# Time boundaries used for profit-target scaling (Eastern Time)
_MORNING_END: time = time(11, 0)
_MIDDAY_END: time = time(14, 0)
_AFTERNOON_END: time = time(15, 0)

# Absolute exit deadline
_ABSOLUTE_EXIT_TIME: time = time(15, 45)

# VIX1D spike threshold (fraction, e.g. 0.25 = 25%)
_VIX_SPIKE_THRESHOLD: float = 0.25

# Time-based stop parameters
_TIME_BASED_STOP_MINUTES: int = 30


# ============================================================================
# Position
# ============================================================================

@dataclass
class Position:
    """Represents an active trading position in a 0DTE SPX option or spread.

    Tracks entry parameters, real-time mark-to-market, high/low watermarks,
    and all exit management state (break-even flag, trailing stop, targets).

    Attributes:
        position_id: Unique identifier (UUID4 hex string).
        scan_signal: The ``ScanSignal`` that generated this trade entry.
        entry_price: Fill price per contract (option premium in dollars).
        entry_time: Timestamp of the fill (timezone-aware preferred).
        contracts: Number of contracts held.  Always >= 1.
        current_price: Most recent mark-to-market price per contract.
        max_price: Highest price observed since entry (for trailing stop).
        min_price: Lowest price observed since entry (for analytics).
        unrealized_pnl: Current unrealized P&L in dollars across all contracts.
        unrealized_pnl_pct: Current unrealized P&L as a fraction of entry cost.
        is_break_even_set: Whether the stop has been moved to break-even.
        trailing_stop: Current trailing stop price level, or ``None`` if
            trailing has not been activated.
        profit_target: Target exit price (adjusted dynamically by time zone).
        stop_loss: Current stop loss price level.
        time_stop: Absolute time at which this position must be closed.
            Defaults to 3:45 PM ET for all 0DTE positions.
    """

    position_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    scan_signal: ScanSignal = field(default=None)  # type: ignore[assignment]
    entry_price: float = 0.0
    entry_time: datetime = field(default_factory=datetime.now)
    contracts: int = 1
    current_price: float = 0.0
    max_price: float = 0.0
    min_price: float = float("inf")
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    is_break_even_set: bool = False
    trailing_stop: Optional[float] = None
    profit_target: float = 0.0
    stop_loss: float = 0.0
    time_stop: datetime = field(default_factory=lambda: datetime.now().replace(
        hour=15, minute=45, second=0, microsecond=0,
    ))

    # -- internal bookkeeping (not part of public interface) -----------------
    _initial_contracts: int = field(default=0, repr=False)
    _half_off_taken: bool = field(default=False, repr=False)


# ============================================================================
# ExitManager
# ============================================================================

class ExitManager:
    """Manages exits for all active positions with time-scaled profit targets,
    stop losses, and break-even management.

    The exit manager is the single source of truth for position lifecycle
    after entry.  It evaluates a strict priority chain of exit conditions
    on every update tick and produces ``TradeLog`` records on close for
    downstream analytics and self-learning.

    Args:
        risk_budget_daily: Total dollar risk budget for the trading day.
        max_risk_per_trade_pct: Maximum fraction of daily budget risked on
            a single trade (default 2%).
        initial_stop_pct: Initial stop loss as a fraction of premium paid
            (default 50% -- lose half the premium, get out).
        time_based_stop_pct: Loss threshold that triggers an exit if the
            position has been held for more than 30 minutes (default 30%).
        break_even_trigger_pct: Profit level (as fraction of entry) at
            which the stop is moved to break-even (default 50%).
        half_off_trigger_pct: Profit level at which 50% of contracts are
            closed and the remainder rides with a trailing stop (default 100%).
        absolute_exit_time: Hard deadline for closing ALL positions.
            Default 3:45 PM ET.  This is non-negotiable.
    """

    def __init__(
        self,
        risk_budget_daily: float = 10_000.0,
        max_risk_per_trade_pct: float = 0.02,
        initial_stop_pct: float = 0.50,
        time_based_stop_pct: float = 0.30,
        break_even_trigger_pct: float = 0.50,
        half_off_trigger_pct: float = 1.00,
        absolute_exit_time: time = time(15, 45),
    ) -> None:
        # Configuration
        self.risk_budget_daily: float = risk_budget_daily
        self.max_risk_per_trade_pct: float = max_risk_per_trade_pct
        self.initial_stop_pct: float = initial_stop_pct
        self.time_based_stop_pct: float = time_based_stop_pct
        self.break_even_trigger_pct: float = break_even_trigger_pct
        self.half_off_trigger_pct: float = half_off_trigger_pct
        self.absolute_exit_time: time = absolute_exit_time

        # State
        self.active_positions: Dict[str, Position] = {}
        self.closed_positions: List[TradeLog] = []
        self.daily_pnl: float = 0.0
        self.daily_trade_count: int = 0

        logger.info(
            "ExitManager initialized | daily_budget=$%.2f | max_risk_per_trade=%.1f%% "
            "| initial_stop=%.0f%% | time_stop=%.0f%% | BE_trigger=%.0f%% "
            "| half_off=%.0f%% | hard_exit=%s",
            risk_budget_daily,
            max_risk_per_trade_pct * 100,
            initial_stop_pct * 100,
            time_based_stop_pct * 100,
            break_even_trigger_pct * 100,
            half_off_trigger_pct * 100,
            absolute_exit_time.strftime("%H:%M"),
        )

    # -----------------------------------------------------------------------
    # Position opening
    # -----------------------------------------------------------------------

    def open_position(
        self,
        signal: ScanSignal,
        fill_price: float,
        contracts: int,
    ) -> Position:
        """Open a new position from a scan signal.

        Position sizing is governed by the risk budget:
            max loss per trade = ``max_risk_per_trade_pct`` x ``risk_budget_daily``

        For single long options the maximum loss equals the premium paid
        (``fill_price * contracts * 100``).  For defined-risk spreads the
        maximum loss equals ``(spread_width - credit_received) * contracts * 100``.

        **NO NAKED SHORT POSITIONS. EVER.**  This method will refuse to open
        a position if the signal's scan type implies undefined risk.

        Args:
            signal: The ``ScanSignal`` that generated this trade entry.
            fill_price: Actual fill price per contract (premium in dollars).
            contracts: Number of contracts to open.

        Returns:
            A fully initialized ``Position`` with stop, target, and time stop set.

        Raises:
            ValueError: If the signal implies a naked short position or if
                ``fill_price`` or ``contracts`` is invalid.
        """
        # ------------------------------------------------------------------
        # Safety: reject naked shorts
        # ------------------------------------------------------------------
        _naked_types = {ScanType.NAKED_CALL, ScanType.NAKED_PUT}
        if hasattr(signal, "scan_type") and signal.scan_type in _naked_types:
            msg = (
                f"REJECTED: naked short position ({signal.scan_type}) is "
                "NEVER permitted. All short options must be part of a "
                "defined-risk spread."
            )
            logger.critical(msg)
            raise ValueError(msg)

        if fill_price <= 0:
            raise ValueError(f"fill_price must be positive; got {fill_price}")
        if contracts < 1:
            raise ValueError(f"contracts must be >= 1; got {contracts}")

        now = datetime.now()

        # Initial stop loss: 50% of premium
        stop_loss = fill_price * (1.0 - self.initial_stop_pct)

        # Initial profit target: 100% gain (will be adjusted by time zone)
        profit_target = fill_price * 2.0

        # Time stop: 3:45 PM ET today
        time_stop = now.replace(
            hour=self.absolute_exit_time.hour,
            minute=self.absolute_exit_time.minute,
            second=0,
            microsecond=0,
        )

        position = Position(
            position_id=uuid.uuid4().hex,
            scan_signal=signal,
            entry_price=fill_price,
            entry_time=now,
            contracts=contracts,
            current_price=fill_price,
            max_price=fill_price,
            min_price=fill_price,
            unrealized_pnl=0.0,
            unrealized_pnl_pct=0.0,
            is_break_even_set=False,
            trailing_stop=None,
            profit_target=profit_target,
            stop_loss=stop_loss,
            time_stop=time_stop,
        )
        position._initial_contracts = contracts
        position._half_off_taken = False

        self.active_positions[position.position_id] = position
        self.daily_trade_count += 1

        logger.info(
            "OPENED position %s | %s %s | entry=$%.2f | contracts=%d "
            "| stop=$%.2f | target=$%.2f | time_stop=%s",
            position.position_id[:8],
            getattr(signal, "direction", "N/A"),
            getattr(signal, "scan_type", "N/A"),
            fill_price,
            contracts,
            stop_loss,
            profit_target,
            time_stop.strftime("%H:%M"),
        )

        return position

    # -----------------------------------------------------------------------
    # Position updates
    # -----------------------------------------------------------------------

    def update_position(
        self,
        position_id: str,
        current_price: float,
        current_time: datetime,
    ) -> None:
        """Update a position with the current market price.

        Recalculates:
            - ``current_price``
            - ``max_price`` / ``min_price`` watermarks
            - ``unrealized_pnl`` (dollars)
            - ``unrealized_pnl_pct`` (fraction of entry cost)

        Args:
            position_id: UUID of the position to update.
            current_price: Latest option premium (mid-price) in dollars.
            current_time: Current timestamp.

        Raises:
            KeyError: If ``position_id`` is not found in active positions.
        """
        if position_id not in self.active_positions:
            raise KeyError(
                f"Position {position_id} not found in active positions."
            )

        pos = self.active_positions[position_id]
        pos.current_price = current_price

        # Watermark tracking
        if current_price > pos.max_price:
            pos.max_price = current_price
        if current_price < pos.min_price:
            pos.min_price = current_price

        # P&L computation
        # For long positions: P&L = (current - entry) * contracts * multiplier
        price_change = current_price - pos.entry_price
        pos.unrealized_pnl = price_change * pos.contracts * _MULTIPLIER

        if pos.entry_price > 0:
            pos.unrealized_pnl_pct = price_change / pos.entry_price
        else:
            pos.unrealized_pnl_pct = 0.0

        logger.debug(
            "UPDATE %s | price=$%.2f | max=$%.2f | min=$%.2f | pnl=$%.2f (%.1f%%)",
            position_id[:8],
            current_price,
            pos.max_price,
            pos.min_price,
            pos.unrealized_pnl,
            pos.unrealized_pnl_pct * 100,
        )

    # -----------------------------------------------------------------------
    # Exit condition checks
    # -----------------------------------------------------------------------

    def check_profit_target(
        self,
        position: Position,
        time_zone: str,
    ) -> Tuple[bool, float]:
        """Check if the profit target is hit, scaled to time of day.

        Profit targets decrease as the trading day progresses because theta
        decay accelerates and the probability of large directional moves
        declines.  Trailing stops also tighten with time.

        Time-zone profit target schedule:
            Before 11:00 AM:   Target 100-200% gain, trail at 50% of max gain.
            11:00 AM - 2:00 PM: Target 75-150% gain, trail at 40% of max gain.
            2:00 PM - 3:00 PM:  Target 50-100% gain, trail at 30% of max gain.
            After 3:00 PM:      Target 30-50% gain, NO trailing -- hard target
                                 and exit.

        Args:
            position: The position to evaluate.
            time_zone: Current intraday time zone label. One of
                ``'morning'``, ``'midday'``, ``'afternoon'``, ``'power_hour'``,
                or a recognized ``IntradayZone`` name.

        Returns:
            Tuple of ``(should_exit, exit_price)`` where ``exit_price`` is
            the recommended exit level.
        """
        entry = position.entry_price
        current = position.current_price
        gain_pct = (current - entry) / entry if entry > 0 else 0.0

        # Determine target and trail parameters based on current time
        current_time_obj = self._extract_time(position)

        if current_time_obj < _MORNING_END:
            # Before 11 AM: aggressive targets
            target_low, target_high = 1.00, 2.00
            trail_pct = 0.50
            use_trailing = True
        elif current_time_obj < _MIDDAY_END:
            # 11 AM - 2 PM: moderate targets
            target_low, target_high = 0.75, 1.50
            trail_pct = 0.40
            use_trailing = True
        elif current_time_obj < _AFTERNOON_END:
            # 2 PM - 3 PM: reduced targets
            target_low, target_high = 0.50, 1.00
            trail_pct = 0.30
            use_trailing = True
        else:
            # After 3 PM: power hour -- hard targets, no trailing
            target_low, target_high = 0.30, 0.50
            trail_pct = 0.0
            use_trailing = False

        # Dynamic target: use the lower bound as the minimum acceptable gain
        target_gain = target_low

        # Update the position's profit target
        position.profit_target = entry * (1.0 + target_gain)

        # Check hard profit target
        if gain_pct >= target_high:
            exit_price = current
            logger.info(
                "PROFIT TARGET HIT (hard) %s | gain=%.1f%% >= target=%.1f%%",
                position.position_id[:8],
                gain_pct * 100,
                target_high * 100,
            )
            return True, exit_price

        # Check trailing stop (only if trailing is active and we've exceeded
        # the lower target at some point)
        if use_trailing and position.trailing_stop is not None:
            if current <= position.trailing_stop:
                logger.info(
                    "TRAILING STOP HIT %s | price=$%.2f <= trail=$%.2f",
                    position.position_id[:8],
                    current,
                    position.trailing_stop,
                )
                return True, current

        # Check minimum target
        if gain_pct >= target_low:
            if not use_trailing:
                # Power hour: no trailing, exit at target
                logger.info(
                    "PROFIT TARGET HIT (power hour) %s | gain=%.1f%% >= %.1f%%",
                    position.position_id[:8],
                    gain_pct * 100,
                    target_low * 100,
                )
                return True, current

            # If trailing is enabled, update the trailing stop but don't exit
            self._update_trailing_stop(position, trail_pct)

        return False, 0.0

    def check_stop_loss(
        self,
        position: Position,
    ) -> Tuple[bool, ExitReason]:
        """Check all stop loss conditions.

        Three stop loss layers are evaluated in order:

        1. **Initial stop**: If the position has lost more than
           ``initial_stop_pct`` (default 50%) of the premium paid, exit.
        2. **Time-based stop**: If the position has been open for more than
           30 minutes AND is down more than ``time_based_stop_pct`` (default
           30%), exit.  The rationale: if it hasn't worked in 30 minutes of
           0DTE, theta is eating you alive.
        3. **Break-even stop**: If the break-even stop was activated (position
           was once up 50%+) and the price has fallen back below entry, exit
           to preserve capital.

        Args:
            position: The position to evaluate.

        Returns:
            Tuple of ``(should_exit, exit_reason)``.  If ``should_exit`` is
            ``False``, ``exit_reason`` is ``ExitReason.NONE`` (or a sentinel).
        """
        entry = position.entry_price
        current = position.current_price
        loss_pct = (entry - current) / entry if entry > 0 else 0.0

        # Layer 1: Initial stop -- 50% of premium lost
        if loss_pct >= self.initial_stop_pct:
            logger.warning(
                "INITIAL STOP LOSS %s | loss=%.1f%% >= threshold=%.1f%%",
                position.position_id[:8],
                loss_pct * 100,
                self.initial_stop_pct * 100,
            )
            return True, ExitReason.STOP_LOSS

        # Layer 2: Time-based stop -- down > 30% after 30 minutes
        hold_minutes = self._hold_time_minutes(position)
        if hold_minutes >= _TIME_BASED_STOP_MINUTES:
            if loss_pct >= self.time_based_stop_pct:
                logger.warning(
                    "TIME-BASED STOP %s | held=%d min | loss=%.1f%% >= %.1f%%",
                    position.position_id[:8],
                    hold_minutes,
                    loss_pct * 100,
                    self.time_based_stop_pct * 100,
                )
                return True, ExitReason.TIME_STOP

        # Layer 3: Break-even stop
        if position.is_break_even_set and current < entry:
            logger.warning(
                "BREAK-EVEN STOP %s | price=$%.2f < entry=$%.2f",
                position.position_id[:8],
                current,
                entry,
            )
            return True, ExitReason.BREAK_EVEN_STOP

        return False, ExitReason.NONE

    def check_signal_reversal(
        self,
        position: Position,
        current_direction_score: DirectionScore,
    ) -> bool:
        """Check if the composite direction score has flipped sign.

        If the signal that generated the entry was bullish (positive score)
        and the current direction score is now bearish (negative), or vice
        versa, the thesis is invalidated and the position should be closed.

        Args:
            position: The position to evaluate.
            current_direction_score: The latest ``DirectionScore`` reading.

        Returns:
            ``True`` if the direction score has reversed against the position.
        """
        signal = position.scan_signal
        entry_direction = getattr(signal, "direction", None)
        current_score = getattr(current_direction_score, "composite_score", 0.0)

        if entry_direction is None:
            return False

        # Bullish entry requires positive score to persist
        if entry_direction == TradeDirection.BULLISH and current_score < 0:
            logger.warning(
                "SIGNAL REVERSAL %s | was BULLISH, score now %.1f",
                position.position_id[:8],
                current_score,
            )
            return True

        # Bearish entry requires negative score to persist
        if entry_direction == TradeDirection.BEARISH and current_score > 0:
            logger.warning(
                "SIGNAL REVERSAL %s | was BEARISH, score now %.1f",
                position.position_id[:8],
                current_score,
            )
            return True

        return False

    def check_gex_flip(
        self,
        position: Position,
        gex_profile: GEXProfile,
        spx_price: float,
    ) -> bool:
        """Check if SPX price has crossed the gamma flip level against position.

        The gamma flip level is the strike at which dealer gamma exposure
        transitions from positive (stabilizing) to negative (amplifying).
        Crossing this level against the position direction signals a regime
        change that invalidates the trade thesis.

        Rules:
            - Long call and price drops below gamma flip level: EXIT.
            - Long put and price rises above gamma flip level: EXIT.

        Args:
            position: The position to evaluate.
            gex_profile: Current ``GEXProfile`` with the gamma flip level.
            spx_price: Current SPX index price.

        Returns:
            ``True`` if the gamma flip level has been breached against
            the position direction.
        """
        gamma_flip = getattr(gex_profile, "gamma_flip_level", None)
        if gamma_flip is None or gamma_flip <= 0:
            return False

        signal = position.scan_signal
        entry_direction = getattr(signal, "direction", None)
        scan_type = getattr(signal, "scan_type", None)

        # Long call / bullish trades: exit if price drops below gamma flip
        if entry_direction == TradeDirection.BULLISH:
            if spx_price < gamma_flip:
                logger.warning(
                    "GEX FLIP %s | BULLISH but SPX $%.2f < gamma_flip $%.2f",
                    position.position_id[:8],
                    spx_price,
                    gamma_flip,
                )
                return True

        # Long put / bearish trades: exit if price rises above gamma flip
        if entry_direction == TradeDirection.BEARISH:
            if spx_price > gamma_flip:
                logger.warning(
                    "GEX FLIP %s | BEARISH but SPX $%.2f > gamma_flip $%.2f",
                    position.position_id[:8],
                    spx_price,
                    gamma_flip,
                )
                return True

        return False

    def check_vix_spike(
        self,
        vix1d: float,
        vix1d_5min_ago: float,
    ) -> bool:
        """Check if VIX1D has spiked more than 25% in 5 minutes.

        A VIX1D spike of this magnitude indicates a structural volatility
        event (flash crash, surprise headline, liquidity withdrawal).  In
        this scenario ALL positions should be closed immediately -- there
        is no edge in holding through a vol explosion in 0DTE.

        Args:
            vix1d: Current VIX1D reading.
            vix1d_5min_ago: VIX1D reading from 5 minutes ago.

        Returns:
            ``True`` if VIX1D has spiked > 25% in the last 5 minutes.
        """
        if vix1d_5min_ago <= 0:
            logger.warning(
                "VIX spike check: vix1d_5min_ago is non-positive (%.4f); "
                "skipping check.",
                vix1d_5min_ago,
            )
            return False

        spike_pct = (vix1d - vix1d_5min_ago) / vix1d_5min_ago

        if spike_pct > _VIX_SPIKE_THRESHOLD:
            logger.critical(
                "VIX1D SPIKE DETECTED | current=%.2f | 5min_ago=%.2f | "
                "spike=%.1f%% > threshold=%.1f%% | LIQUIDATING ALL POSITIONS",
                vix1d,
                vix1d_5min_ago,
                spike_pct * 100,
                _VIX_SPIKE_THRESHOLD * 100,
            )
            return True

        return False

    def check_time_stop(
        self,
        position: Position,
        current_time: datetime,
    ) -> bool:
        """Check the absolute time stop: ALL positions must be closed by 3:45 PM ET.

        This is the single most important risk rule for 0DTE trading.  After
        3:45 PM, gamma becomes extreme and pin risk makes option pricing
        unreliable.  No position is worth holding through the final 15 minutes.

        Args:
            position: The position to evaluate.
            current_time: Current timestamp (should be Eastern Time).

        Returns:
            ``True`` if the current time is at or past the absolute exit time.
        """
        current_time_only = current_time.time()

        if current_time_only >= self.absolute_exit_time:
            logger.warning(
                "TIME STOP %s | current=%s >= deadline=%s",
                position.position_id[:8],
                current_time_only.strftime("%H:%M:%S"),
                self.absolute_exit_time.strftime("%H:%M"),
            )
            return True

        return False

    # -----------------------------------------------------------------------
    # Break-even and trailing stop management
    # -----------------------------------------------------------------------

    def manage_break_even(self, position: Position) -> None:
        """Break-even management logic.

        Two-stage process:
            1. **Move to break-even**: Once the position is up by
               ``break_even_trigger_pct`` (default 50%), move the stop loss
               to the entry price.  This guarantees at worst a scratch trade.
            2. **Take half off**: Once the position is up by
               ``half_off_trigger_pct`` (default 100%), close 50% of the
               contracts and let the rest ride with a trailing stop.

        This method updates state in-place.  It does NOT close the position;
        that decision is made by ``evaluate_all_exits``.

        Args:
            position: The position to manage.
        """
        if position.entry_price <= 0:
            return

        gain_pct = (position.current_price - position.entry_price) / position.entry_price

        # Stage 1: Move stop to break-even at 50% profit
        if not position.is_break_even_set and gain_pct >= self.break_even_trigger_pct:
            position.is_break_even_set = True
            position.stop_loss = position.entry_price
            logger.info(
                "BREAK-EVEN SET %s | gain=%.1f%% | stop moved to entry=$%.2f",
                position.position_id[:8],
                gain_pct * 100,
                position.entry_price,
            )

        # Stage 2: Take half off at 100% profit
        if (
            not position._half_off_taken
            and gain_pct >= self.half_off_trigger_pct
            and position.contracts >= 2
        ):
            contracts_to_close = position.contracts // 2
            position.contracts -= contracts_to_close
            position._half_off_taken = True

            # Realize partial P&L
            partial_pnl = (
                (position.current_price - position.entry_price)
                * contracts_to_close
                * _MULTIPLIER
            )
            self.daily_pnl += partial_pnl

            logger.info(
                "HALF OFF %s | closed %d of %d contracts at $%.2f | "
                "partial_pnl=$%.2f | remaining=%d contracts trailing",
                position.position_id[:8],
                contracts_to_close,
                position._initial_contracts,
                position.current_price,
                partial_pnl,
                position.contracts,
            )

    def compute_trailing_stop(
        self,
        position: Position,
        time_zone: str,
    ) -> float:
        """Compute the trailing stop level based on the current time zone.

        The trail percentage tightens as the day progresses:
            - Morning (before 11 AM): 50% trail from max price.
            - Midday (11 AM - 2 PM): 40% trail from max price.
            - Afternoon (2 PM - 3 PM): 30% trail from max price.
            - Power hour (after 3 PM): 0% -- no trailing, use hard target.

        Formula:
            ``trail_level = max_price * (1 - trail_pct)``

        Args:
            position: The position to compute the trail for.
            time_zone: Current intraday time zone label.

        Returns:
            The trailing stop price level.
        """
        current_time_obj = self._extract_time(position)

        if current_time_obj < _MORNING_END:
            trail_pct = 0.50
        elif current_time_obj < _MIDDAY_END:
            trail_pct = 0.40
        elif current_time_obj < _AFTERNOON_END:
            trail_pct = 0.30
        else:
            # Power hour: no trailing
            trail_pct = 0.0
            return 0.0

        trail_level = position.max_price * (1.0 - trail_pct)

        logger.debug(
            "TRAILING STOP computed %s | max=$%.2f | trail_pct=%.0f%% | level=$%.2f",
            position.position_id[:8],
            position.max_price,
            trail_pct * 100,
            trail_level,
        )

        return trail_level

    # -----------------------------------------------------------------------
    # Master exit evaluation
    # -----------------------------------------------------------------------

    def evaluate_all_exits(
        self,
        current_time: datetime,
        time_zone: str,
        direction_score: DirectionScore,
        gex_profile: GEXProfile,
        spx_price: float,
        vix1d: float,
        vix1d_5min_ago: float,
    ) -> List[Tuple[str, ExitReason, float]]:
        """Evaluate exit conditions for ALL active positions.

        Checks are performed in strict priority order.  Once a higher-priority
        exit condition triggers, lower-priority checks are skipped for that
        position.  This prevents conflicting signals and ensures the most
        critical risk controls always dominate.

        Priority order:
            1. Time stop (absolute -- 3:45 PM ET)
            2. VIX spike stop (> 25% in 5 min -- exit ALL)
            3. GEX flip stop (gamma regime change)
            4. Signal reversal stop (direction score flipped)
            5. Stop loss (initial 50% or time-based 30%)
            6. Profit target / trailing stop
            7. Break-even management (update state, don't necessarily exit)

        Args:
            current_time: Current timestamp (Eastern Time).
            time_zone: Current intraday time zone label.
            direction_score: Latest composite ``DirectionScore``.
            gex_profile: Latest ``GEXProfile`` snapshot.
            spx_price: Current SPX index price.
            vix1d: Current VIX1D level.
            vix1d_5min_ago: VIX1D level from 5 minutes ago.

        Returns:
            List of ``(position_id, exit_reason, exit_price)`` tuples for
            all positions that should be closed.  Empty list if no exits
            are triggered.
        """
        exits: List[Tuple[str, ExitReason, float]] = []

        # Pre-check: VIX spike applies to ALL positions simultaneously
        vix_spike = self.check_vix_spike(vix1d, vix1d_5min_ago)

        # Iterate over a snapshot of position IDs (dict may be modified)
        position_ids = list(self.active_positions.keys())

        for pid in position_ids:
            if pid not in self.active_positions:
                continue  # Position may have been closed by a prior iteration

            position = self.active_positions[pid]

            # Update mark-to-market before checking exits
            # (caller is expected to have called update_position already,
            #  but we ensure watermarks are current)

            # ---- Priority 1: Time stop (absolute) ----
            if self.check_time_stop(position, current_time):
                exits.append((pid, ExitReason.TIME_STOP, position.current_price))
                continue

            # ---- Priority 2: VIX spike (exit ALL) ----
            if vix_spike:
                exits.append((pid, ExitReason.VIX_SPIKE, position.current_price))
                continue

            # ---- Priority 3: GEX flip ----
            if self.check_gex_flip(position, gex_profile, spx_price):
                exits.append((pid, ExitReason.GEX_FLIP, position.current_price))
                continue

            # ---- Priority 4: Signal reversal ----
            if self.check_signal_reversal(position, direction_score):
                exits.append((pid, ExitReason.SIGNAL_REVERSAL, position.current_price))
                continue

            # ---- Priority 5: Stop loss ----
            should_stop, stop_reason = self.check_stop_loss(position)
            if should_stop:
                exits.append((pid, stop_reason, position.current_price))
                continue

            # ---- Priority 6: Profit target / trailing stop ----
            should_take_profit, exit_price = self.check_profit_target(
                position, time_zone,
            )
            if should_take_profit:
                exits.append((pid, ExitReason.PROFIT_TARGET, exit_price))
                continue

            # ---- Priority 7: Break-even management (update, may not exit) ----
            self.manage_break_even(position)

            # Update trailing stop for positions that have passed the
            # break-even threshold
            if position.is_break_even_set:
                new_trail = self.compute_trailing_stop(position, time_zone)
                if new_trail > 0:
                    # Only ratchet the trail upward (never lower it)
                    if position.trailing_stop is None or new_trail > position.trailing_stop:
                        position.trailing_stop = new_trail

        if exits:
            logger.info(
                "EXIT EVALUATION complete | %d position(s) flagged for exit",
                len(exits),
            )
        else:
            logger.debug(
                "EXIT EVALUATION complete | all %d positions held",
                len(self.active_positions),
            )

        return exits

    # -----------------------------------------------------------------------
    # Position closing
    # -----------------------------------------------------------------------

    def close_position(
        self,
        position_id: str,
        exit_price: float,
        exit_reason: ExitReason,
        current_time: datetime,
    ) -> TradeLog:
        """Close a position and generate a complete TradeLog entry.

        Computes all analytics required by the self-learning system:
            - P&L in dollars and as a percentage of entry cost.
            - Hold time in minutes.
            - Optimal exit price (hindsight: the max_price for long positions).
            - Left-on-table percentage (how much gain was unrealized at exit
              relative to the optimal exit).
            - Whether the position was stopped prematurely (exited at a loss
              but would have been profitable at max_price).

        The ``TradeLog`` is appended to ``closed_positions`` for end-of-day
        summary and self-learning ingestion.

        Args:
            position_id: UUID of the position to close.
            exit_price: Actual exit fill price per contract.
            exit_reason: The ``ExitReason`` that triggered the close.
            current_time: Timestamp of the close.

        Returns:
            A fully populated ``TradeLog`` entry.

        Raises:
            KeyError: If ``position_id`` is not found in active positions.
        """
        if position_id not in self.active_positions:
            raise KeyError(
                f"Position {position_id} not found in active positions. "
                "It may have already been closed."
            )

        position = self.active_positions.pop(position_id)

        # ------------------------------------------------------------------
        # P&L calculations
        # ------------------------------------------------------------------
        pnl_per_contract = exit_price - position.entry_price
        total_pnl = pnl_per_contract * position.contracts * _MULTIPLIER

        pnl_pct = (
            pnl_per_contract / position.entry_price
            if position.entry_price > 0
            else 0.0
        )

        # ------------------------------------------------------------------
        # Hold time
        # ------------------------------------------------------------------
        hold_delta = current_time - position.entry_time
        hold_minutes = hold_delta.total_seconds() / 60.0

        # ------------------------------------------------------------------
        # Optimal exit analysis (hindsight)
        # ------------------------------------------------------------------
        # For long positions, the optimal exit was at max_price.
        optimal_exit_price = position.max_price
        optimal_pnl_per_contract = optimal_exit_price - position.entry_price
        optimal_pnl = (
            optimal_pnl_per_contract * position._initial_contracts * _MULTIPLIER
        )

        # Left on table: fraction of optimal gain not captured
        if optimal_pnl_per_contract > 0:
            left_on_table_pct = (
                (optimal_exit_price - exit_price) / optimal_pnl_per_contract
            )
        else:
            left_on_table_pct = 0.0

        # Stopped prematurely: exited at a loss but max_price shows profit
        stopped_prematurely = (
            pnl_per_contract < 0 and optimal_pnl_per_contract > 0
        )

        # ------------------------------------------------------------------
        # Update daily P&L
        # ------------------------------------------------------------------
        self.daily_pnl += total_pnl

        # ------------------------------------------------------------------
        # Build TradeLog
        # ------------------------------------------------------------------
        # Extract market context from the scan signal
        signal = position.scan_signal

        # Compute max gain/loss during trade in dollar terms
        max_gain_during = (position.max_price - position.entry_price) * position._initial_contracts * _MULTIPLIER
        max_loss_during = (position.min_price - position.entry_price) * position._initial_contracts * _MULTIPLIER

        trade_log = TradeLog(
            timestamp_entry=position.entry_time,
            timestamp_exit=current_time,
            scan_type=getattr(signal, "scan_type", None) if signal else ScanType.DIRECTIONAL,
            direction=getattr(signal, "direction", None) if signal else TradeDirection.NEUTRAL,
            strike=getattr(signal, "strike_selection", None) and getattr(signal.strike_selection, "strike", 0.0) or getattr(signal, "entry_price", 0.0) if signal else 0.0,
            option_type=getattr(signal, "strike_selection", None) and getattr(signal.strike_selection, "option_type", "CALL") or "CALL" if signal else "CALL",
            entry_price=position.entry_price,
            exit_price=exit_price,
            pnl_dollars=total_pnl,
            pnl_percent=pnl_pct * 100.0,
            hold_time_minutes=hold_minutes,
            max_gain_during_trade=max(max_gain_during, 0.0),
            max_loss_during_trade=min(max_loss_during, 0.0),
            exit_reason=exit_reason,
            optimal_exit_price=optimal_exit_price,
            left_on_table_pct=left_on_table_pct * 100.0 if left_on_table_pct > 0 else 0.0,
            was_stopped_prematurely=stopped_prematurely,
            session_type=getattr(signal, "session_type", None) if signal else SessionType.RANGE,
            time_zone=getattr(signal, "time_zone", None) if signal else TimeZoneType.MORNING_SESSION,
            spx_at_entry=getattr(signal, "entry_price", 0.0) if signal else 0.0,
            vix1d_at_entry=0.0,
            vix_at_entry=0.0,
            expected_move_1sigma=0.0,
            composite_direction_score=getattr(getattr(signal, "direction_score", None), "total_score", 0.0) if signal else 0.0,
            net_gex_at_entry=0.0,
            gamma_flip_at_entry=1.0,
            delta_at_entry=getattr(getattr(signal, "strike_selection", None), "delta", 0.0) if signal else 0.0,
            gamma_at_entry=getattr(getattr(signal, "strike_selection", None), "gamma", 0.0) if signal else 0.0,
            theta_at_entry=getattr(getattr(signal, "strike_selection", None), "theta", 0.0) if signal else 0.0,
            iv_at_entry=getattr(getattr(signal, "strike_selection", None), "iv", 0.0) if signal else 0.0,
            tick_10min_avg=0.0,
            trin_at_entry=1.0,
            ad_ratio_at_entry=1.0,
            cumulative_delta_es=0.0,
        )

        self.closed_positions.append(trade_log)

        logger.info(
            "CLOSED %s | reason=%s | entry=$%.2f | exit=$%.2f | "
            "pnl=$%.2f (%.1f%%) | held=%.1f min | optimal=$%.2f | "
            "left_on_table=%.1f%% | premature_stop=%s",
            position.position_id[:8],
            exit_reason.value if hasattr(exit_reason, "value") else exit_reason,
            position.entry_price,
            exit_price,
            total_pnl,
            pnl_pct * 100,
            hold_minutes,
            optimal_exit_price,
            left_on_table_pct * 100,
            stopped_prematurely,
        )

        return trade_log

    # -----------------------------------------------------------------------
    # Daily summary
    # -----------------------------------------------------------------------

    def get_daily_summary(self) -> Dict:
        """Get a summary of daily trading performance.

        Returns a dictionary containing:
            - ``total_pnl``: Net P&L for the day in dollars.
            - ``trade_count``: Total number of trades taken.
            - ``closed_count``: Number of positions closed so far.
            - ``open_count``: Number of positions still active.
            - ``win_count``: Number of trades with positive P&L.
            - ``loss_count``: Number of trades with non-positive P&L.
            - ``win_rate``: Win count / closed count (0 if no closed trades).
            - ``avg_win``: Average P&L of winning trades (dollars).
            - ``avg_loss``: Average P&L of losing trades (dollars).
            - ``profit_factor``: Gross wins / abs(gross losses).
            - ``avg_hold_time_min``: Average hold time in minutes.
            - ``best_trade``: Largest single-trade P&L (dollars).
            - ``worst_trade``: Smallest (most negative) single-trade P&L.
            - ``premature_stops``: Count of trades stopped that later showed profit.
            - ``avg_left_on_table_pct``: Average percentage of optimal gain not captured.

        Returns:
            Summary dictionary.
        """
        closed = self.closed_positions

        if not closed:
            return {
                "total_pnl": self.daily_pnl,
                "trade_count": self.daily_trade_count,
                "closed_count": 0,
                "open_count": len(self.active_positions),
                "win_count": 0,
                "loss_count": 0,
                "win_rate": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "profit_factor": 0.0,
                "avg_hold_time_min": 0.0,
                "best_trade": 0.0,
                "worst_trade": 0.0,
                "premature_stops": 0,
                "avg_left_on_table_pct": 0.0,
            }

        pnls = [t.pnl_dollars for t in closed]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        gross_wins = sum(wins) if wins else 0.0
        gross_losses = abs(sum(losses)) if losses else 0.0

        hold_times = [t.hold_time_minutes for t in closed]
        left_on_table = [t.left_on_table_pct for t in closed]
        premature_count = sum(1 for t in closed if t.was_stopped_prematurely)

        closed_count = len(closed)

        return {
            "total_pnl": self.daily_pnl,
            "trade_count": self.daily_trade_count,
            "closed_count": closed_count,
            "open_count": len(self.active_positions),
            "win_count": len(wins),
            "loss_count": len(losses),
            "win_rate": len(wins) / closed_count if closed_count > 0 else 0.0,
            "avg_win": gross_wins / len(wins) if wins else 0.0,
            "avg_loss": -gross_losses / len(losses) if losses else 0.0,
            "profit_factor": (
                gross_wins / gross_losses if gross_losses > 0 else float("inf")
            ),
            "avg_hold_time_min": (
                sum(hold_times) / len(hold_times) if hold_times else 0.0
            ),
            "best_trade": max(pnls) if pnls else 0.0,
            "worst_trade": min(pnls) if pnls else 0.0,
            "premature_stops": premature_count,
            "avg_left_on_table_pct": (
                sum(left_on_table) / len(left_on_table) if left_on_table else 0.0
            ),
        }

    # -----------------------------------------------------------------------
    # Position sizing
    # -----------------------------------------------------------------------

    def compute_position_size(
        self,
        signal: ScanSignal,
        account_risk: float,
    ) -> int:
        """Compute the optimal number of contracts based on the risk budget.

        Position sizing rule:
            max_risk = ``max_risk_per_trade_pct`` x ``account_risk``

        For long single options:
            ``contracts = floor(max_risk / (entry_price * 100))``

        For defined-risk spreads:
            ``contracts = floor(max_risk / (max_loss_per_spread * 100))``
            where ``max_loss_per_spread = spread_width - credit_received``

        Always returns at least 1 contract.

        Args:
            signal: The ``ScanSignal`` with entry price and spread details.
            account_risk: The total risk capital available (typically
                ``risk_budget_daily``).

        Returns:
            Number of contracts to trade (minimum 1).
        """
        max_risk = self.max_risk_per_trade_pct * account_risk

        # Extract entry price from the signal
        entry_price = getattr(signal, "entry_price", 0.0)
        if entry_price is None or entry_price <= 0:
            entry_price = getattr(signal, "premium", 0.0)
        if entry_price is None or entry_price <= 0:
            logger.warning(
                "Cannot determine entry price from signal; defaulting to 1 contract."
            )
            return 1

        scan_type = getattr(signal, "scan_type", None)

        # Determine max loss per contract
        spread_width = getattr(signal, "spread_width", None)
        credit_received = getattr(signal, "credit_received", None)

        if spread_width is not None and credit_received is not None and spread_width > 0:
            # Defined-risk spread: max loss = width - credit
            max_loss_per_contract = (spread_width - credit_received) * _MULTIPLIER
        else:
            # Single option: max loss = full premium
            max_loss_per_contract = entry_price * _MULTIPLIER

        if max_loss_per_contract <= 0:
            logger.warning(
                "max_loss_per_contract is non-positive ($%.2f); "
                "defaulting to 1 contract.",
                max_loss_per_contract,
            )
            return 1

        contracts = int(max_risk / max_loss_per_contract)

        # Enforce minimum of 1 contract
        contracts = max(contracts, 1)

        logger.info(
            "POSITION SIZE | max_risk=$%.2f | max_loss/contract=$%.2f | "
            "contracts=%d",
            max_risk,
            max_loss_per_contract,
            contracts,
        )

        return contracts

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _hold_time_minutes(position: Position) -> float:
        """Compute how many minutes a position has been held.

        Args:
            position: The position to measure.

        Returns:
            Hold time in minutes (float).
        """
        delta = datetime.now() - position.entry_time
        return delta.total_seconds() / 60.0

    @staticmethod
    def _extract_time(position: Position) -> time:
        """Extract the current wall-clock time for time-zone decisions.

        Uses ``datetime.now()`` which should be in Eastern Time for
        production deployments.  In testing, override via dependency
        injection or mock.

        Args:
            position: The position (unused; included for interface symmetry
                with potential timezone-aware overrides).

        Returns:
            Current time-of-day as a ``datetime.time`` object.
        """
        return datetime.now().time()

    def _update_trailing_stop(
        self,
        position: Position,
        trail_pct: float,
    ) -> None:
        """Update the position's trailing stop to a new level.

        The trail only ratchets upward -- it never moves down.

        Args:
            position: The position to update.
            trail_pct: Trail percentage (fraction below max_price).
        """
        if trail_pct <= 0:
            return

        new_trail = position.max_price * (1.0 - trail_pct)

        if position.trailing_stop is None or new_trail > position.trailing_stop:
            position.trailing_stop = new_trail
            logger.debug(
                "TRAILING STOP updated %s | max=$%.2f × (1-%.0f%%) = $%.2f",
                position.position_id[:8],
                position.max_price,
                trail_pct * 100,
                new_trail,
            )


# ============================================================================
# Module exports
# ============================================================================

__all__: List[str] = [
    "Position",
    "ExitManager",
]
