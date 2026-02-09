"""
SCANIFY Exit Manager — 0DTE SPX Options Exit Management System

Manages position lifecycle from entry through exit, including dynamic
profit targets, trailing stops, break-even management, and time-based
exits calibrated to intraday time zones. All exit logic is evaluated
in strict priority order to ensure the most critical conditions
(settlement close, VIX spikes) always take precedence.
"""

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Tuple
import math

from .config import ExitConfig, ScanifyConfig, TimeZone, ExitReason, ScanType


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Position:
    """Represents an open or recently closed options position.

    Tracks all state required for exit management including high-water
    marks for trailing stop computation and flags for break-even /
    partial close logic.

    Attributes:
        position_id: Unique identifier for this position.
        scan_type: Which scanner originated this trade.
        direction: Trade structure — one of ``long_call``, ``long_put``,
            ``bull_put_spread``, ``bear_call_spread``, or ``iron_condor``.
        entry_time: Timestamp when the position was opened.
        entry_price: Fill price at entry (per-contract premium).
        current_price: Most recent mark / mid price.
        max_price_seen: Highest price observed since entry.
        min_price_seen: Lowest price observed since entry.
        contracts: Number of contracts held.
        strike: Primary strike price of the position.
        stop_loss_price: Current hard stop-loss level.
        profit_target_price: Current profit target level.
        trailing_stop_active: Whether trailing stop logic is engaged.
        break_even_stop_active: Whether the stop has been moved to
            break-even.
        partial_taken: Whether a partial close has already been executed.
        is_open: ``True`` while the position is live.
    """

    position_id: str
    scan_type: ScanType
    direction: str
    entry_time: datetime
    entry_price: float
    current_price: float
    max_price_seen: float
    min_price_seen: float
    contracts: int
    strike: float
    stop_loss_price: float
    profit_target_price: float
    trailing_stop_active: bool = False
    break_even_stop_active: bool = False
    partial_taken: bool = False
    is_open: bool = True


@dataclass
class ExitSignal:
    """Describes a completed (or triggered) exit from a position.

    Contains full P&L accounting as well as an efficiency metric
    indicating how close the realised exit was to the best possible
    exit during the position's lifetime.

    Attributes:
        position_id: Position this exit applies to.
        reason: Catalogued reason for exit.
        exit_price: Price at which the exit was (or should be) filled.
        pnl_pct: Percentage return relative to entry price.
        pnl_dollars: Dollar P&L (premium x contracts x multiplier).
        hold_time_minutes: Duration from entry to exit in minutes.
        was_optimal: ``True`` if the exit captured >= 90 % of the
            maximum gain available during the trade.
        max_gain_pct: Best percentage gain observed during the trade.
        left_on_table_pct: Percentage points of gain forfeited relative
            to the peak.
        timestamp: Time at which the exit was generated.
    """

    position_id: str
    reason: ExitReason
    exit_price: float
    pnl_pct: float
    pnl_dollars: float
    hold_time_minutes: float
    was_optimal: bool
    max_gain_pct: float
    left_on_table_pct: float
    timestamp: datetime


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SPX_MULTIPLIER: float = 100.0

# Optimality threshold — if the exit captures at least this fraction of
# the max gain observed, the exit is classified as "optimal".
_OPTIMAL_CAPTURE_THRESHOLD: float = 0.90


# ---------------------------------------------------------------------------
# ExitManager
# ---------------------------------------------------------------------------

class ExitManager:
    """Manages exit logic for all active SCANIFY positions.

    The manager evaluates exit conditions in a strict priority order so
    that catastrophic-risk exits (settlement close, VIX spikes) always
    fire before softer signals (trailing stops, profit targets).

    Typical usage::

        mgr = ExitManager(config)
        mgr.register_position(pos)
        # On each tick / bar:
        mgr.update_price(pos.position_id, new_price, now)
        updated = mgr.manage_position(pos, new_price, now)
        signal = mgr.check_exits(updated, now, score, gex_flip, vix_spike)
        if signal:
            mgr.close_position(updated, signal.reason, signal.exit_price, now)

    Parameters:
        config: Master SCANIFY configuration instance.
    """

    def __init__(self, config: ScanifyConfig) -> None:
        self._config: ScanifyConfig = config
        self._exit_config: ExitConfig = config.exit
        self._positions: List[Position] = []
        self._position_map: Dict[str, Position] = {}

    # ------------------------------------------------------------------
    # Position registration & price updates
    # ------------------------------------------------------------------

    def register_position(self, position: Position) -> None:
        """Add a position to the active tracking list.

        Args:
            position: A newly opened ``Position`` to track.

        Raises:
            ValueError: If a position with the same ID is already
                registered and still open.
        """
        if position.position_id in self._position_map:
            existing = self._position_map[position.position_id]
            if existing.is_open:
                raise ValueError(
                    f"Position '{position.position_id}' is already registered "
                    f"and still open."
                )
        self._positions.append(position)
        self._position_map[position.position_id] = position

    def update_price(
        self,
        position_id: str,
        current_price: float,
        timestamp: datetime,
    ) -> None:
        """Update the market price for a tracked position.

        Also refreshes the high-water and low-water marks used for
        trailing stop and optimality calculations.

        Args:
            position_id: Unique position identifier.
            current_price: Latest mark / mid price.
            timestamp: Time associated with this price observation.

        Raises:
            KeyError: If the position ID is not found.
        """
        if position_id not in self._position_map:
            raise KeyError(f"Position '{position_id}' not found.")

        pos = self._position_map[position_id]
        if not pos.is_open:
            return

        pos.current_price = current_price
        if current_price > pos.max_price_seen:
            pos.max_price_seen = current_price
        if current_price < pos.min_price_seen:
            pos.min_price_seen = current_price

    # ------------------------------------------------------------------
    # Time zone helpers
    # ------------------------------------------------------------------

    @staticmethod
    def get_current_timezone(dt: datetime) -> TimeZone:
        """Map a datetime to the corresponding intraday ``TimeZone``.

        The boundaries mirror those defined in
        :class:`~scanify.config.TimeZone`:

        =================  ==============
        Time (ET)          TimeZone
        =================  ==============
        07:00 -- 09:30     PRE_MARKET
        09:30 -- 09:45     OPENING_AUCTION
        09:45 -- 11:30     MORNING_SESSION
        11:30 -- 13:30     MIDDAY_LULL
        13:30 -- 15:00     AFTERNOON_ACCEL
        15:00 -- 15:45     POWER_HOUR
        15:45 -- 16:00+    SETTLEMENT
        =================  ==============

        Args:
            dt: A timezone-aware or naive datetime assumed to be in
                Eastern Time.

        Returns:
            The ``TimeZone`` that *dt* falls within.
        """
        t = dt.time()

        if t < time(9, 30):
            return TimeZone.PRE_MARKET
        if t < time(9, 45):
            return TimeZone.OPENING_AUCTION
        if t < time(11, 30):
            return TimeZone.MORNING_SESSION
        if t < time(13, 30):
            return TimeZone.MIDDAY_LULL
        if t < time(15, 0):
            return TimeZone.AFTERNOON_ACCEL
        if t < time(15, 45):
            return TimeZone.POWER_HOUR
        return TimeZone.SETTLEMENT

    # ------------------------------------------------------------------
    # Exit condition checks
    # ------------------------------------------------------------------

    def check_exits(
        self,
        position: Position,
        current_time: datetime,
        composite_score: float,
        gex_flipped: bool,
        vix1d_spike: bool,
    ) -> Optional[ExitSignal]:
        """Evaluate all exit conditions for *position* in priority order.

        The conditions are checked from highest to lowest urgency:

        1. **Settlement close** — all positions must close by 15:45 ET.
        2. **VIX1D spike** — a > 25 % move in VIX1D within 5 min.
        3. **GEX flip** — gamma exposure has flipped against the trade.
        4. **Signal reversal** — the composite score has flipped sign
           against the position direction.
        5. **Stop loss** — price has breached the initial hard stop.
        6. **Time-based stop** — position is down > 30 % after 30 min.
        7. **Profit target** — price has reached the target.
        8. **Trailing stop** — trailing stop is active and breached.
        9. **Break-even stop** — break-even stop is active and breached.

        Args:
            position: The position to evaluate.
            current_time: Current timestamp (Eastern Time assumed).
            composite_score: Latest composite directional score
                (positive = bullish, negative = bearish).
            gex_flipped: ``True`` if GEX structure has flipped against
                the position since entry.
            vix1d_spike: ``True`` if VIX1D has spiked > 25 % in the
                last 5 minutes.

        Returns:
            An ``ExitSignal`` if any condition has triggered, otherwise
            ``None``.  Only the *first* (highest-priority) triggered
            condition is returned.
        """
        if not position.is_open:
            return None

        entry = position.entry_price
        if entry <= 0:
            return None

        current = position.current_price
        pnl_pct = (current - entry) / entry

        # Helper to build an ExitSignal from the current state.
        def _make_signal(reason: ExitReason) -> ExitSignal:
            return self._build_exit_signal(position, reason, current, current_time)

        # 1. Absolute time stop — settlement close by 15:45 ET
        absolute_exit = self._parse_time_str(self._exit_config.absolute_exit_time)
        if current_time.time() >= absolute_exit:
            return _make_signal(ExitReason.SETTLEMENT_CLOSE)

        # 2. VIX1D spike stop
        if vix1d_spike:
            return _make_signal(ExitReason.VIX_SPIKE)

        # 3. GEX flip stop
        if gex_flipped:
            return _make_signal(ExitReason.GEX_FLIP)

        # 4. Direction / signal reversal
        if self._is_direction_reversed(position, composite_score):
            return _make_signal(ExitReason.SIGNAL_REVERSAL)

        # 5. Hard stop loss
        stop_threshold = entry * (1.0 - self._exit_config.initial_stop_pct)
        if current <= stop_threshold:
            return _make_signal(ExitReason.STOP_LOSS)

        # 6. Time-based stop — down >30 % after 30 min
        hold_minutes = (current_time - position.entry_time).total_seconds() / 60.0
        if (
            hold_minutes >= self._exit_config.time_based_stop_minutes
            and pnl_pct <= -self._exit_config.time_based_stop_pct
        ):
            return _make_signal(ExitReason.STOP_LOSS)

        # 7. Profit target
        if current >= position.profit_target_price:
            return _make_signal(ExitReason.PROFIT_TARGET)

        # 8. Trailing stop
        if position.trailing_stop_active:
            tz = self.get_current_timezone(current_time)
            trail_pct = self.get_trailing_stop_pct(tz)
            if trail_pct > 0:
                trail_level = position.max_price_seen * (1.0 - trail_pct)
                if current <= trail_level:
                    return _make_signal(ExitReason.TRAILING_STOP)

        # 9. Break-even stop
        if position.break_even_stop_active:
            if current <= entry:
                return _make_signal(ExitReason.BREAK_EVEN)

        return None

    # ------------------------------------------------------------------
    # Position management (dynamic state updates)
    # ------------------------------------------------------------------

    def manage_position(
        self,
        position: Position,
        current_price: float,
        current_time: datetime,
    ) -> Position:
        """Update dynamic position state (stops, partials, trailing).

        This should be called on every tick / bar *before*
        :meth:`check_exits` so that the position flags are current.

        Rules applied:
        - If up >= 50 % from entry: activate break-even stop.
        - If up >= 100 % from entry and no partial has been taken:
          flag ``partial_taken`` for the caller to action.
        - Update the trailing-stop activation based on the current
          time zone.

        Args:
            position: The position to update (modified in place).
            current_price: Latest mark / mid price.
            current_time: Current timestamp.

        Returns:
            The same ``Position`` instance with updated fields.
        """
        if not position.is_open:
            return position

        entry = position.entry_price
        if entry <= 0:
            return position

        position.current_price = current_price
        if current_price > position.max_price_seen:
            position.max_price_seen = current_price
        if current_price < position.min_price_seen:
            position.min_price_seen = current_price

        gain_pct = (current_price - entry) / entry

        # Activate break-even stop once up >= 50 %
        if gain_pct >= self._exit_config.move_to_be_at_pct and not position.break_even_stop_active:
            position.break_even_stop_active = True

        # Flag for partial close once up >= 100 %
        if gain_pct >= self._exit_config.take_partial_at_pct and not position.partial_taken:
            position.partial_taken = True

        # Activate trailing stop when the position has moved enough and
        # the current time zone supports trailing (i.e. not POWER_HOUR).
        tz = self.get_current_timezone(current_time)
        trail_pct = self.get_trailing_stop_pct(tz)
        if trail_pct > 0 and gain_pct > 0:
            position.trailing_stop_active = True
        elif trail_pct == 0:
            # Power hour — disable trailing, rely on hard target.
            position.trailing_stop_active = False

        return position

    # ------------------------------------------------------------------
    # Profit target & trailing stop look-ups
    # ------------------------------------------------------------------

    def get_profit_target_for_timezone(
        self,
        timezone: TimeZone,
        scan_type: ScanType,
    ) -> float:
        """Return the profit target as a fraction of entry price.

        For directional and gamma-scalp trades the target decreases
        through the day as theta decay compresses available gains:

        ================  ==========
        TimeZone          Target
        ================  ==========
        MORNING_SESSION   1.50 (150 %)
        MIDDAY_LULL       1.00 (100 %)
        AFTERNOON_ACCEL   0.75 (75 %)
        POWER_HOUR        0.40 (40 %)
        ================  ==========

        For premium-sell trades the target is 50 % of the maximum
        credit received, tightening to 80 % after 14:30 ET.

        Args:
            timezone: Current intraday time zone.
            scan_type: The scan type that originated the trade.

        Returns:
            Target gain as a decimal fraction (e.g. 1.5 = 150 %).
        """
        if scan_type == ScanType.PREMIUM_SELL:
            # Premium-sell uses fixed fraction of max credit.
            if timezone in (TimeZone.AFTERNOON_ACCEL, TimeZone.POWER_HOUR, TimeZone.SETTLEMENT):
                return 0.80
            return 0.50

        # Directional / gamma-scalp targets.
        _targets = {
            TimeZone.PRE_MARKET: 1.50,
            TimeZone.OPENING_AUCTION: 1.50,
            TimeZone.MORNING_SESSION: 1.50,
            TimeZone.MIDDAY_LULL: 1.00,
            TimeZone.AFTERNOON_ACCEL: 0.75,
            TimeZone.POWER_HOUR: 0.40,
            TimeZone.SETTLEMENT: 0.40,
        }
        return _targets.get(timezone, 1.00)

    @staticmethod
    def get_trailing_stop_pct(timezone: TimeZone) -> float:
        """Return the trailing-stop percentage for the given time zone.

        The trailing distance tightens as the day progresses, and is
        disabled entirely during power hour where a hard profit target
        is preferred.

        ================  =====
        TimeZone          Trail
        ================  =====
        MORNING_SESSION   0.50
        MIDDAY_LULL       0.40
        AFTERNOON_ACCEL   0.30
        POWER_HOUR        0.00 (disabled)
        ================  =====

        Args:
            timezone: Current intraday time zone.

        Returns:
            Trailing-stop distance as a decimal fraction, or ``0.0`` if
            trailing is not used in the given zone.
        """
        _trails = {
            TimeZone.PRE_MARKET: 0.50,
            TimeZone.OPENING_AUCTION: 0.50,
            TimeZone.MORNING_SESSION: 0.50,
            TimeZone.MIDDAY_LULL: 0.40,
            TimeZone.AFTERNOON_ACCEL: 0.30,
            TimeZone.POWER_HOUR: 0.0,
            TimeZone.SETTLEMENT: 0.0,
        }
        return _trails.get(timezone, 0.40)

    # ------------------------------------------------------------------
    # Position close helpers
    # ------------------------------------------------------------------

    def close_position(
        self,
        position: Position,
        reason: ExitReason,
        exit_price: float,
        timestamp: datetime,
    ) -> ExitSignal:
        """Close a position and produce an ``ExitSignal`` with P&L.

        The position is marked as closed (``is_open = False``) and
        removed from the active tracking set.

        Args:
            position: The position to close.
            reason: Why the position is being closed.
            exit_price: Price at which the exit fill occurred.
            timestamp: Time of the exit.

        Returns:
            A fully populated ``ExitSignal``.

        Raises:
            ValueError: If the position is already closed.
        """
        if not position.is_open:
            raise ValueError(
                f"Position '{position.position_id}' is already closed."
            )

        signal = self._build_exit_signal(position, reason, exit_price, timestamp)
        position.is_open = False
        position.current_price = exit_price
        return signal

    def close_all_positions(
        self,
        current_prices: Dict[str, float],
        timestamp: datetime,
        reason: ExitReason = ExitReason.SETTLEMENT_CLOSE,
    ) -> List[ExitSignal]:
        """Emergency / end-of-day close of every open position.

        Args:
            current_prices: Mapping of ``position_id`` to the latest
                market price for each open position.
            timestamp: Time of the bulk close.
            reason: Exit reason applied to every position (defaults to
                ``SETTLEMENT_CLOSE``).

        Returns:
            A list of ``ExitSignal`` instances, one per closed position.
        """
        signals: List[ExitSignal] = []
        for pos in list(self._positions):
            if not pos.is_open:
                continue
            price = current_prices.get(pos.position_id, pos.current_price)
            try:
                sig = self.close_position(pos, reason, price, timestamp)
                signals.append(sig)
            except ValueError:
                # Position was already closed between iteration and
                # the close call — skip silently.
                continue
        return signals

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_active_positions(self) -> List[Position]:
        """Return a list of all currently open positions.

        Returns:
            List of ``Position`` instances with ``is_open == True``.
        """
        return [p for p in self._positions if p.is_open]

    def get_position_summary(self) -> Dict:
        """Aggregate statistics across all tracked positions.

        Returns:
            A dictionary with keys:

            - **num_open** (*int*) — number of currently open positions.
            - **total_pnl** (*float*) — sum of unrealised P&L dollars
              across open positions.
            - **best_position** (*Optional[str]*) — ``position_id`` of
              the open position with the highest percentage gain, or
              ``None`` if no positions are open.
            - **worst_position** (*Optional[str]*) — ``position_id`` of
              the open position with the lowest percentage gain, or
              ``None`` if no positions are open.
        """
        active = self.get_active_positions()

        if not active:
            return {
                "num_open": 0,
                "total_pnl": 0.0,
                "best_position": None,
                "worst_position": None,
            }

        total_pnl = 0.0
        best_id: Optional[str] = None
        worst_id: Optional[str] = None
        best_pct = -math.inf
        worst_pct = math.inf

        for pos in active:
            if pos.entry_price <= 0:
                continue
            pnl_pct = (pos.current_price - pos.entry_price) / pos.entry_price
            dollar_pnl = (pos.current_price - pos.entry_price) * pos.contracts * _SPX_MULTIPLIER
            total_pnl += dollar_pnl

            if pnl_pct > best_pct:
                best_pct = pnl_pct
                best_id = pos.position_id
            if pnl_pct < worst_pct:
                worst_pct = pnl_pct
                worst_id = pos.position_id

        return {
            "num_open": len(active),
            "total_pnl": round(total_pnl, 2),
            "best_position": best_id,
            "worst_position": worst_id,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_time_str(t_str: str) -> time:
        """Parse an ``"HH:MM"`` string into a :class:`datetime.time`.

        Args:
            t_str: Time string in 24-hour ``HH:MM`` format.

        Returns:
            Corresponding ``time`` object.
        """
        parts = t_str.split(":")
        return time(int(parts[0]), int(parts[1]))

    @staticmethod
    def _is_direction_reversed(position: Position, composite_score: float) -> bool:
        """Determine whether the composite score has flipped against the position.

        A *long_call* or *bull_put_spread* is bullish — a negative
        composite score signals reversal.  A *long_put* or
        *bear_call_spread* is bearish — a positive score signals
        reversal.  Iron condors are direction-neutral and never trigger
        a reversal signal.

        Args:
            position: The position to evaluate.
            composite_score: Current composite directional score.

        Returns:
            ``True`` if the score opposes the position direction.
        """
        bullish_directions = {"long_call", "bull_put_spread"}
        bearish_directions = {"long_put", "bear_call_spread"}

        if position.direction in bullish_directions and composite_score < 0:
            return True
        if position.direction in bearish_directions and composite_score > 0:
            return True

        # iron_condor or unknown — no directional reversal.
        return False

    def _build_exit_signal(
        self,
        position: Position,
        reason: ExitReason,
        exit_price: float,
        timestamp: datetime,
    ) -> ExitSignal:
        """Construct an ``ExitSignal`` with full P&L accounting.

        Args:
            position: The position being exited.
            reason: Exit reason.
            exit_price: Price at which the exit is marked.
            timestamp: Time of exit.

        Returns:
            A populated ``ExitSignal``.
        """
        entry = position.entry_price
        if entry <= 0:
            # Guard against division-by-zero for degenerate entries.
            pnl_pct = 0.0
            max_gain_pct = 0.0
        else:
            pnl_pct = (exit_price - entry) / entry
            max_gain_pct = (position.max_price_seen - entry) / entry

        pnl_dollars = (exit_price - entry) * position.contracts * _SPX_MULTIPLIER
        hold_minutes = (timestamp - position.entry_time).total_seconds() / 60.0

        left_on_table_pct = max(max_gain_pct - pnl_pct, 0.0)
        was_optimal = (
            max_gain_pct > 0
            and pnl_pct >= max_gain_pct * _OPTIMAL_CAPTURE_THRESHOLD
        )

        return ExitSignal(
            position_id=position.position_id,
            reason=reason,
            exit_price=exit_price,
            pnl_pct=round(pnl_pct, 6),
            pnl_dollars=round(pnl_dollars, 2),
            hold_time_minutes=round(hold_minutes, 2),
            was_optimal=was_optimal,
            max_gain_pct=round(max_gain_pct, 6),
            left_on_table_pct=round(left_on_table_pct, 6),
            timestamp=timestamp,
        )
