"""
SCANIFY Gamma Scalp / Acceleration Scanner — Core Scan #3.

The most aggressive and highest-risk scan in SCANIFY.  Operates exclusively
in the final 105 minutes of the session (14:00 - 15:45 ET), exploiting
gamma-driven acceleration dynamics:

    1. **Gamma Squeeze** — Price approaches a high-negative-gamma strike while
       volume spikes and directional momentum aligns.  Dealer delta-hedging
       creates a positive feedback loop that accelerates price away from the
       strike, producing rapid directional moves of 5-15+ SPX points.

    2. **Gamma Unpin** — After extended pinning at max-pain or max-OI, charm
       flows and MOC imbalances overwhelm the pin gravity and release price
       into a fast end-of-day move.

.. warning::

   This scanner targets the most volatile and least predictable portion of
   the 0DTE session.  Signals carry extreme execution risk:

   * Spreads widen dramatically in the final hour.
   * Theta decay is measured in seconds, not minutes.
   * False starts and reversals are common.
   * Losses can be total within minutes.

   Always use hard stop-losses and the absolute exit time.  Position sizing
   should be the smallest of any scanner.
"""

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Dict, List, Optional, Tuple
import math
import numpy as np

from .config import (
    GammaScalpConfig, ScanifyConfig, SignalDirection,
    ScanType, TimeZone
)
from .data_feeds import (
    OptionsChain, OptionQuote, FuturesData, VIXData,
    SPXPriceBar, OptionType
)
from .gex_engine import GEXResult, GEXEngine
from .market_internals import CompositeDirectionScore


# ---------------------------------------------------------------------------
# Data classes — Gamma Squeeze Setup
# ---------------------------------------------------------------------------

@dataclass
class GammaSqueezeSetup:
    """Describes a detected gamma-squeeze opportunity.

    A gamma squeeze occurs when price approaches a strike with large negative
    dealer gamma.  As price moves toward the strike, dealers must delta-hedge
    in the *same* direction as the move (buying into a rally, selling into a
    decline), creating a self-reinforcing acceleration loop.

    Attributes:
        trigger_strike: The strike with large negative gamma acting as the
            squeeze catalyst.
        current_distance: Distance in SPX points between spot and the
            trigger strike.
        dealer_gamma_at_strike: Net dealer gamma exposure at the trigger
            strike (negative values indicate short-gamma positioning).
        is_negative_gamma: True when the trigger strike carries negative
            dealer gamma (expected for a valid squeeze).
        volume_spike: True when ES futures volume exceeds the configured
            spike multiple (default 2x average).
        direction: Directional lean of the squeeze (BULLISH if price is
            approaching from below, BEARISH from above).
        squeeze_strength: Composite strength score (0-100) based on gamma
            magnitude, volume intensity, and momentum alignment.
    """

    trigger_strike: float
    current_distance: float
    dealer_gamma_at_strike: float
    is_negative_gamma: bool
    volume_spike: bool
    direction: SignalDirection
    squeeze_strength: float


# ---------------------------------------------------------------------------
# Data classes — Gamma Unpin Setup
# ---------------------------------------------------------------------------

@dataclass
class GammaUnpinSetup:
    """Describes a detected gamma-unpin opportunity.

    An unpin occurs when price has been magnetically pinned to a strike with
    high open interest (often max pain) for an extended period, and
    accumulating forces — charm-driven hedging flows and market-on-close
    (MOC) imbalances — finally overcome the pin gravity and release price
    into a fast end-of-day move.

    Attributes:
        pin_strike: The strike where price has been pinned.
        pin_duration_minutes: How long (in minutes) price has been within
            the pin range.
        pin_range: Width of the pin band in SPX points (how tightly price
            has been held).
        expected_release_direction: Anticipated direction of the unpin move
            based on charm flows and MOC imbalance.
        moc_imbalance_direction: Market-on-close imbalance direction
            (``"buy"`` or ``"sell"``), or None if unavailable.
        charm_flow_direction: Direction of charm-driven delta-hedging flow
            from the GEX engine.
        unpin_confidence: Composite confidence score (0-100) based on pin
            duration, charm magnitude, and proximity to settlement.
    """

    pin_strike: float
    pin_duration_minutes: int
    pin_range: float
    expected_release_direction: SignalDirection
    moc_imbalance_direction: Optional[str]
    charm_flow_direction: SignalDirection
    unpin_confidence: float


# ---------------------------------------------------------------------------
# Data classes — Gamma Scalp Signal
# ---------------------------------------------------------------------------

@dataclass
class GammaScalpSignal:
    """Actionable signal produced by the gamma scalp scanner.

    .. warning::

       Gamma scalp signals represent the highest-risk opportunities in
       SCANIFY.  The profit_target_pct and stop_loss_pct are deliberately
       tight, and the absolute_exit_time must be honoured without exception.
       Do not hold positions past the stated exit time.

    Attributes:
        timestamp: Time the signal was generated.
        scan_type: Always ``ScanType.GAMMA_SCALP``.
        signal_subtype: Either ``"gamma_squeeze"`` or ``"gamma_unpin"``.
        direction: Trade direction (BULLISH or BEARISH).
        strike: Recommended option strike price.
        option_type: CALL or PUT.
        entry_price: Suggested entry price (mid-market at signal time).
        bid: Current best bid on the recommended strike.
        ask: Current best ask on the recommended strike.
        delta: Option delta at the recommended strike.
        gamma: Option gamma at the recommended strike.
        profit_target_pct: Target profit as a percentage of entry price
            (typical range 0.50-1.00 — i.e. 50-100%).
        stop_loss_pct: Maximum acceptable loss as a percentage of entry
            price (typical 0.30 — i.e. 30%).
        absolute_exit_time: Hard time-stop in HH:MM format (default
            ``"15:50"``).  All positions must be closed by this time
            regardless of profit or loss.
        squeeze_setup: Detailed squeeze setup if subtype is
            ``"gamma_squeeze"``, else None.
        unpin_setup: Detailed unpin setup if subtype is
            ``"gamma_unpin"``, else None.
        reasons: List of human-readable reasons supporting the signal.
        warnings: List of risk warnings specific to this signal.
        confidence: Overall signal confidence score (0-100).
    """

    timestamp: datetime
    scan_type: ScanType = ScanType.GAMMA_SCALP
    signal_subtype: str = "gamma_squeeze"
    direction: SignalDirection = SignalDirection.NEUTRAL
    strike: float = 0.0
    option_type: OptionType = OptionType.CALL
    entry_price: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    delta: float = 0.0
    gamma: float = 0.0
    profit_target_pct: float = 0.50
    stop_loss_pct: float = 0.30
    absolute_exit_time: str = "15:50"
    squeeze_setup: Optional[GammaSqueezeSetup] = None
    unpin_setup: Optional[GammaUnpinSetup] = None
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    confidence: float = 0.0


# ---------------------------------------------------------------------------
# Gamma Scalp Scanner
# ---------------------------------------------------------------------------

class GammaScalpScanner:
    """Core Scan #3 — Gamma Scalp / Acceleration Scanner.

    Scans for gamma-driven acceleration setups in the final portion of the
    0DTE trading session.  Two sub-strategies are monitored:

    1. **Gamma Squeeze**: Detects when price is approaching a high-negative-
       gamma strike with volume confirmation and directional alignment.
    2. **Gamma Unpin**: Detects when a prolonged pin at max-pain / max-OI
       is likely to release into a fast end-of-day move.

    The scanner runs every 30 seconds between 14:00 and 15:45 ET and
    produces at most one :class:`GammaScalpSignal` per scan cycle.

    .. warning::

       This is the most advanced and highest-risk scanner in SCANIFY.
       Signals generated here target fast, volatile moves in the final
       session period where theta decay is extreme, spreads are wide,
       and reversals are sudden.  Use minimum position sizes and always
       enforce the absolute exit time.

    Parameters
    ----------
    config : ScanifyConfig
        Master SCANIFY configuration (gamma scalp settings are read from
        ``config.gamma_scalp``).
    """

    # Scan window boundaries (Eastern Time).
    _SCAN_START = time(14, 0)
    _SCAN_END = time(15, 45)

    # Unpin detection is only valid in the final 15 minutes of the window.
    _UNPIN_EARLIEST = time(15, 30)

    def __init__(self, config: ScanifyConfig) -> None:
        self._config = config
        self._gs_config: GammaScalpConfig = config.gamma_scalp

        # Rolling price history used for pin detection.
        # Stores (timestamp, close_price) tuples from SPXPriceBar inputs.
        self._price_history: List[Tuple[datetime, float]] = []

        # Recent ES volume readings for spike detection.
        # Stores (timestamp, volume) tuples; capped at 120 entries (~2 hrs
        # at 1-minute intervals).
        self._volume_history: List[Tuple[datetime, int]] = []
        self._max_volume_history: int = 120

        # Previous VIX1D reading for trend detection.
        self._prev_vix1d: Optional[float] = None

    # ------------------------------------------------------------------
    # Time window validation
    # ------------------------------------------------------------------

    def is_valid_scan_window(self, dt: datetime) -> Tuple[bool, str]:
        """Check whether the current time falls within the scan window.

        The gamma scalp scanner is active only between 14:00 and 15:45 ET.
        Outside this window the gamma-acceleration dynamics that underpin
        the strategy are unreliable.

        Parameters
        ----------
        dt : datetime
            Current timestamp (assumed Eastern Time).

        Returns
        -------
        tuple[bool, str]
            ``(True, "")`` when inside the window, or
            ``(False, reason)`` with a human-readable explanation.
        """
        current_time = dt.time()

        if current_time < self._SCAN_START:
            return (
                False,
                f"Before scan window: {current_time.strftime('%H:%M')} < "
                f"{self._SCAN_START.strftime('%H:%M')}. "
                f"Gamma acceleration dynamics are not yet dominant."
            )

        if current_time > self._SCAN_END:
            return (
                False,
                f"After scan window: {current_time.strftime('%H:%M')} > "
                f"{self._SCAN_END.strftime('%H:%M')}. "
                f"Too close to settlement — execution risk is extreme and "
                f"spreads are unreliable."
            )

        return (True, "")

    # ------------------------------------------------------------------
    # Volume tracking helpers
    # ------------------------------------------------------------------

    def _update_volume_history(self, futures: FuturesData) -> None:
        """Append the latest ES volume reading to the rolling history."""
        self._volume_history.append((futures.timestamp, futures.volume))
        if len(self._volume_history) > self._max_volume_history:
            self._volume_history = self._volume_history[-self._max_volume_history:]

    def _get_average_volume(self) -> float:
        """Compute the mean ES volume across stored history.

        Returns 0.0 when fewer than 2 readings are available to avoid
        meaningless spike detection.
        """
        if len(self._volume_history) < 2:
            return 0.0
        volumes = [v for _, v in self._volume_history]
        return float(np.mean(volumes))

    # ------------------------------------------------------------------
    # Gamma squeeze detection
    # ------------------------------------------------------------------

    def detect_gamma_squeeze(
        self,
        spot: float,
        gex: GEXResult,
        direction_score: float,
        futures: FuturesData,
        vix_data: VIXData,
        config: GammaScalpConfig,
    ) -> Optional[GammaSqueezeSetup]:
        """Detect a gamma-squeeze setup from the current market state.

        A valid squeeze requires all of the following conditions:

        1. Price is within ``config.approach_distance_points`` (default 3
           pts) of a strike that carries high negative dealer gamma.
        2. ES futures volume is spiking — current volume exceeds
           ``config.volume_spike_multiple`` times the rolling average.
        3. The composite directional score exceeds
           ``config.min_direction_score`` (default 50) in magnitude, and
           its sign aligns with the squeeze direction.
        4. VIX1D is declining (vol compression during squeeze — dealers are
           unwinding hedges into the move).

        Parameters
        ----------
        spot : float
            Current SPX cash index price.
        gex : GEXResult
            Latest GEX surface snapshot from the GEX engine.
        direction_score : float
            Composite directional score (positive = bullish).
        futures : FuturesData
            Current ES futures data (used for volume spike detection).
        vix_data : VIXData
            Current VIX family data (used for VIX1D trend check).
        config : GammaScalpConfig
            Scanner parameters.

        Returns
        -------
        GammaSqueezeSetup or None
            A squeeze setup if all conditions are met; None otherwise.
        """
        # Update volume tracking.
        self._update_volume_history(futures)

        # ----- Identify the nearest high-negative-gamma strike -----
        best_strike: Optional[float] = None
        best_distance: float = float("inf")
        best_gamma: float = 0.0

        for strike, gex_val in gex.gex_by_strike.items():
            distance = abs(spot - strike)
            if distance <= config.approach_distance_points and gex_val < 0:
                if abs(gex_val) > abs(best_gamma):
                    best_strike = strike
                    best_distance = distance
                    best_gamma = gex_val

        if best_strike is None:
            return None

        # Verify negative gamma magnitude exceeds threshold.
        if abs(best_gamma) < config.squeeze_gamma_threshold:
            return None

        # ----- Volume spike check -----
        avg_volume = self._get_average_volume()
        has_volume_spike = False
        if avg_volume > 0:
            current_volume = futures.volume
            if current_volume >= avg_volume * config.volume_spike_multiple:
                has_volume_spike = True

        if not has_volume_spike:
            return None

        # ----- Directional score check -----
        if abs(direction_score) < config.min_direction_score:
            return None

        # Determine squeeze direction from price vs strike.
        if spot < best_strike:
            # Price approaching from below — bullish squeeze.
            squeeze_direction = SignalDirection.BULLISH
        elif spot > best_strike:
            # Price approaching from above — bearish squeeze.
            squeeze_direction = SignalDirection.BEARISH
        else:
            # Sitting right on the strike — use directional score.
            squeeze_direction = (
                SignalDirection.BULLISH if direction_score > 0
                else SignalDirection.BEARISH
            )

        # Verify directional score aligns with the squeeze direction.
        if squeeze_direction == SignalDirection.BULLISH and direction_score < 0:
            return None
        if squeeze_direction == SignalDirection.BEARISH and direction_score > 0:
            return None

        # ----- VIX1D declining check (vol compression) -----
        vix1d_declining = False
        if self._prev_vix1d is not None:
            if vix_data.vix1d < self._prev_vix1d:
                vix1d_declining = True
        else:
            # First reading — cannot confirm decline; be lenient and allow.
            vix1d_declining = True

        # Update stored VIX1D for next cycle.
        self._prev_vix1d = vix_data.vix1d

        if not vix1d_declining:
            return None

        # ----- Compute squeeze strength (0-100) -----
        # Three components weighted equally:
        #   1. Gamma magnitude (capped contribution).
        #   2. Volume spike intensity.
        #   3. Directional momentum alignment.

        # Gamma component: scale |gamma| relative to threshold.
        # At 5x threshold, maxes out at ~33.
        gamma_ratio = min(abs(best_gamma) / config.squeeze_gamma_threshold, 5.0)
        gamma_component = (gamma_ratio / 5.0) * 33.3

        # Volume component: scale volume spike relative to multiple.
        volume_ratio = (
            (futures.volume / avg_volume) / config.volume_spike_multiple
            if avg_volume > 0 else 1.0
        )
        volume_component = min(volume_ratio, 3.0) / 3.0 * 33.3

        # Momentum component: scale direction score relative to 100.
        momentum_component = (
            min(abs(direction_score), 100.0) / 100.0 * 33.4
        )

        squeeze_strength = min(
            gamma_component + volume_component + momentum_component,
            100.0,
        )

        return GammaSqueezeSetup(
            trigger_strike=best_strike,
            current_distance=best_distance,
            dealer_gamma_at_strike=best_gamma,
            is_negative_gamma=(best_gamma < 0),
            volume_spike=has_volume_spike,
            direction=squeeze_direction,
            squeeze_strength=round(squeeze_strength, 1),
        )

    # ------------------------------------------------------------------
    # Gamma unpin detection
    # ------------------------------------------------------------------

    def detect_gamma_unpin(
        self,
        spot: float,
        gex: GEXResult,
        price_bars: List[SPXPriceBar],
        charm_direction: SignalDirection,
        moc_direction: Optional[str],
        config: GammaScalpConfig,
    ) -> Optional[GammaUnpinSetup]:
        """Detect a gamma-unpin setup from price history and flow data.

        An unpin is valid when:

        1. Price has remained within ``config.pin_range_points`` (default 3
           pts) of the max-pain or max-OI strike for at least
           ``config.pin_duration_minutes`` (default 30 min), as verified
           from the supplied price bars.
        2. Charm flows and/or MOC imbalance indicate a directional release.
        3. The setup is only evaluated after 15:30 ET (checked by the
           caller in ``scan()``).

        Parameters
        ----------
        spot : float
            Current SPX cash index price.
        gex : GEXResult
            Latest GEX surface snapshot.
        price_bars : list[SPXPriceBar]
            Recent 1-minute SPX price bars (used to verify pin history).
        charm_direction : SignalDirection
            Direction of charm-driven delta-hedging flow from the GEX engine.
        moc_direction : str or None
            Market-on-close imbalance direction (``"buy"`` or ``"sell"``),
            or None if unavailable.
        config : GammaScalpConfig
            Scanner parameters.

        Returns
        -------
        GammaUnpinSetup or None
            An unpin setup if all conditions are met; None otherwise.
        """
        # ----- Identify the pin strike (max-pain or highest-OI strike) -----
        pin_strike = gex.max_pain
        if pin_strike <= 0:
            return None

        # Also consider call wall and put wall as potential pin magnets.
        # Use whichever is closest to spot if it has higher gravity.
        candidates = [gex.max_pain]
        if gex.call_wall > 0:
            candidates.append(gex.call_wall)
        if gex.put_wall > 0:
            candidates.append(gex.put_wall)

        # Choose the candidate closest to current spot.
        pin_strike = min(candidates, key=lambda s: abs(spot - s))

        # Verify current spot is within pin range.
        if abs(spot - pin_strike) > config.pin_range_points:
            return None

        # ----- Check pin duration from price bars -----
        if not price_bars:
            return None

        # Walk backwards through bars to find how long price has been
        # within the pin range.
        pin_minutes = 0
        pin_range = config.pin_range_points
        for bar in reversed(price_bars):
            bar_midpoint = (bar.high + bar.low) / 2.0
            if abs(bar_midpoint - pin_strike) <= pin_range:
                pin_minutes += 1  # Each bar is ~1 minute.
            else:
                break  # Contiguous pin broken; stop counting.

        if pin_minutes < config.pin_duration_minutes:
            return None

        # ----- Determine expected release direction -----
        # Priority: MOC imbalance direction, then charm flow direction.
        if moc_direction == "buy":
            release_direction = SignalDirection.BULLISH
        elif moc_direction == "sell":
            release_direction = SignalDirection.BEARISH
        elif charm_direction != SignalDirection.NEUTRAL:
            release_direction = charm_direction
        else:
            # Cannot determine direction — no valid unpin signal.
            return None

        # Actual measured pin range: how tightly was price held?
        recent_bars = price_bars[-pin_minutes:] if pin_minutes > 0 else []
        if recent_bars:
            highs = [b.high for b in recent_bars]
            lows = [b.low for b in recent_bars]
            actual_pin_range = max(highs) - min(lows)
        else:
            actual_pin_range = pin_range

        # ----- Compute unpin confidence (0-100) -----
        # Three components:
        #   1. Pin duration (longer pin = more stored energy for release).
        #   2. Charm strength (stronger charm = more hedging flow on release).
        #   3. Time proximity to 15:50 (closer = more forced unwinding).

        # Duration component: scales linearly from threshold to 2x threshold.
        duration_ratio = min(
            pin_minutes / config.pin_duration_minutes, 2.0
        )
        duration_component = (duration_ratio / 2.0) * 30.0

        # Charm component: based on magnitude of net charm exposure.
        charm_abs = abs(gex.net_charm_exposure)
        # Normalize against a reference of 5000 ES-equivalents.
        charm_ratio = min(charm_abs / 5000.0, 1.0) if charm_abs > 0 else 0.0
        charm_component = charm_ratio * 30.0

        # Time component: scales with proximity to 15:50 ET.
        # At 15:30 → ~0.5, at 15:45 → ~1.0.
        if price_bars:
            latest_time = price_bars[-1].timestamp.time()
            minutes_to_exit = max(
                0,
                (15 * 60 + 50) - (latest_time.hour * 60 + latest_time.minute),
            )
            # 20 minutes before exit → max; 30+ minutes → low.
            if minutes_to_exit <= 20:
                time_component = (1.0 - minutes_to_exit / 20.0) * 40.0
            else:
                time_component = 0.0
        else:
            time_component = 0.0

        # MOC confirmation bonus.
        moc_bonus = 0.0
        if moc_direction is not None:
            if (moc_direction == "buy"
                    and release_direction == SignalDirection.BULLISH):
                moc_bonus = 10.0
            elif (moc_direction == "sell"
                  and release_direction == SignalDirection.BEARISH):
                moc_bonus = 10.0

        unpin_confidence = min(
            duration_component + charm_component + time_component + moc_bonus,
            100.0,
        )

        return GammaUnpinSetup(
            pin_strike=pin_strike,
            pin_duration_minutes=pin_minutes,
            pin_range=round(actual_pin_range, 2),
            expected_release_direction=release_direction,
            moc_imbalance_direction=moc_direction,
            charm_flow_direction=charm_direction,
            unpin_confidence=round(unpin_confidence, 1),
        )

    # ------------------------------------------------------------------
    # Strike selection
    # ------------------------------------------------------------------

    def select_strike_for_signal(
        self,
        chain: OptionsChain,
        direction: SignalDirection,
        target_strike: float,
    ) -> Optional[dict]:
        """Find the nearest liquid option to the target strike.

        Given the late-day timing, the scanner prefers ATM or one-strike
        OTM options which retain meaningful delta and have the tightest
        spreads.  Deep OTM contracts are rejected because their spreads
        are typically too wide in the final session hours.

        Parameters
        ----------
        chain : OptionsChain
            Current 0DTE options chain snapshot.
        direction : SignalDirection
            Trade direction — determines whether we look for calls
            (BULLISH) or puts (BEARISH).
        target_strike : float
            The strike price we ideally want to trade (e.g. the squeeze
            trigger strike or pin strike).

        Returns
        -------
        dict or None
            A dictionary with keys ``strike``, ``bid``, ``ask``, ``mid``,
            ``delta``, ``gamma``, ``volume``, ``oi``, ``option_type`` if a
            suitable quote is found; None otherwise.
        """
        if direction == SignalDirection.NEUTRAL:
            return None

        desired_type = (
            OptionType.CALL if direction == SignalDirection.BULLISH
            else OptionType.PUT
        )

        # Filter quotes to the desired option type.
        candidates: List[OptionQuote] = [
            q for q in chain.quotes
            if q.option_type == desired_type
        ]

        if not candidates:
            return None

        # Sort by distance from target strike.
        candidates.sort(key=lambda q: abs(q.strike - target_strike))

        # Evaluate in order of proximity.  Accept the first that passes
        # basic liquidity and spread filters.
        for quote in candidates:
            # Skip quotes with zero bid (likely illiquid or worthless).
            if quote.bid <= 0:
                continue

            # Skip quotes with excessively wide spreads relative to mid.
            spread = quote.ask - quote.bid
            mid = (quote.bid + quote.ask) / 2.0
            if mid > 0 and spread / mid > 1.0:
                # Spread wider than 100% of mid — too wide for late-day.
                continue

            # Skip deep OTM with negligible delta.
            if abs(quote.delta) < 0.05:
                continue

            # Prefer ATM or 1-strike OTM.  Reject strikes more than 2
            # intervals away from the target.
            strike_interval = self._config.contract.strike_interval_atm
            if abs(quote.strike - target_strike) > 2 * strike_interval:
                continue

            return {
                "strike": quote.strike,
                "bid": quote.bid,
                "ask": quote.ask,
                "mid": round(mid, 2),
                "delta": quote.delta,
                "gamma": quote.gamma,
                "volume": quote.volume,
                "oi": quote.open_interest,
                "option_type": desired_type,
            }

        return None

    # ------------------------------------------------------------------
    # Main scan entry point
    # ------------------------------------------------------------------

    def scan(
        self,
        chain: OptionsChain,
        gex: GEXResult,
        direction_score: float,
        futures: FuturesData,
        vix_data: VIXData,
        price_bars: List[SPXPriceBar],
        charm_direction: SignalDirection,
        moc_direction: Optional[str],
    ) -> Optional[GammaScalpSignal]:
        """Execute one scan cycle of the gamma scalp scanner.

        This is the main entry point, intended to be called every 30
        seconds during the scan window (14:00-15:45 ET).

        Algorithm
        ---------
        1. Validate that the current time is within the scan window.
        2. Verify net GEX is negative (required for gamma amplification).
        3. Verify directional score exceeds +/-50 (clear bias needed).
        4. Attempt gamma-squeeze detection.
        5. If no squeeze and time >= 15:30, attempt gamma-unpin detection.
        6. If neither sub-strategy triggers, return None.
        7. Select the best available strike from the options chain.
        8. Build the signal with tight exit parameters and safety warnings.

        Parameters
        ----------
        chain : OptionsChain
            Current 0DTE options chain snapshot.
        gex : GEXResult
            Latest GEX surface snapshot.
        direction_score : float
            Composite directional score (positive = bullish, negative =
            bearish).  Typically the ``weighted_score`` from
            :class:`CompositeDirectionScore`.
        futures : FuturesData
            Current ES futures data.
        vix_data : VIXData
            Current VIX family snapshot.
        price_bars : list[SPXPriceBar]
            Rolling 1-minute SPX price bars.
        charm_direction : SignalDirection
            Charm-flow direction from the GEX engine.
        moc_direction : str or None
            Market-on-close imbalance direction (``"buy"`` or ``"sell"``).

        Returns
        -------
        GammaScalpSignal or None
            A fully-populated signal when conditions are met; None if no
            actionable setup is found.

        .. warning::

           Even when a signal is returned, the ``warnings`` field will
           contain multiple risk advisories.  The caller should surface
           all warnings to the user prominently.
        """
        now = datetime.now()
        config = self._gs_config
        spot = chain.underlying_price

        # ----- 1. Validate time window -----
        valid, reason = self.is_valid_scan_window(now)
        if not valid:
            return None

        # ----- 2. Require negative net GEX (short-gamma environment) -----
        if gex.total_net_gex >= 0:
            return None

        # ----- 3. Require meaningful directional bias -----
        if abs(direction_score) < config.min_direction_score:
            return None

        # ----- 4. Attempt gamma squeeze detection -----
        squeeze_setup: Optional[GammaSqueezeSetup] = None
        unpin_setup: Optional[GammaUnpinSetup] = None
        signal_subtype = ""
        setup_direction = SignalDirection.NEUTRAL
        target_strike = 0.0
        setup_confidence = 0.0

        squeeze_setup = self.detect_gamma_squeeze(
            spot=spot,
            gex=gex,
            direction_score=direction_score,
            futures=futures,
            vix_data=vix_data,
            config=config,
        )

        if squeeze_setup is not None:
            signal_subtype = "gamma_squeeze"
            setup_direction = squeeze_setup.direction
            target_strike = squeeze_setup.trigger_strike
            setup_confidence = squeeze_setup.squeeze_strength

        # ----- 5. Attempt gamma unpin (only after 15:30 and no squeeze) -----
        if squeeze_setup is None and now.time() >= self._UNPIN_EARLIEST:
            unpin_setup = self.detect_gamma_unpin(
                spot=spot,
                gex=gex,
                price_bars=price_bars,
                charm_direction=charm_direction,
                moc_direction=moc_direction,
                config=config,
            )

            if unpin_setup is not None:
                signal_subtype = "gamma_unpin"
                setup_direction = unpin_setup.expected_release_direction
                target_strike = unpin_setup.pin_strike
                setup_confidence = unpin_setup.unpin_confidence

        # ----- 6. No setup found -----
        if squeeze_setup is None and unpin_setup is None:
            return None

        # ----- 7. Select the best strike from the chain -----
        strike_info = self.select_strike_for_signal(
            chain=chain,
            direction=setup_direction,
            target_strike=target_strike,
        )

        if strike_info is None:
            return None

        # ----- 8. Build the signal -----
        reasons: List[str] = []
        warnings: List[str] = []

        if squeeze_setup is not None:
            reasons.append(
                f"Gamma squeeze detected at strike {squeeze_setup.trigger_strike:.0f} "
                f"with {squeeze_setup.current_distance:.1f} pts distance."
            )
            reasons.append(
                f"Dealer gamma at trigger: {squeeze_setup.dealer_gamma_at_strike:,.0f} "
                f"(negative = self-reinforcing hedging)."
            )
            reasons.append(
                f"ES volume spike confirmed "
                f"({config.volume_spike_multiple:.0f}x+ average)."
            )
            reasons.append(
                f"Directional score {direction_score:+.1f} aligns with "
                f"{setup_direction.value} squeeze."
            )
            reasons.append(
                f"VIX1D declining — vol compression supports acceleration."
            )
            reasons.append(
                f"Squeeze strength: {squeeze_setup.squeeze_strength:.0f}/100."
            )

        if unpin_setup is not None:
            reasons.append(
                f"Gamma unpin detected at strike {unpin_setup.pin_strike:.0f} "
                f"after {unpin_setup.pin_duration_minutes} minutes of pinning."
            )
            reasons.append(
                f"Pin range: {unpin_setup.pin_range:.1f} pts — tight pin "
                f"suggests strong magnetic pull."
            )
            reasons.append(
                f"Charm flow direction: {unpin_setup.charm_flow_direction.value}."
            )
            if unpin_setup.moc_imbalance_direction is not None:
                reasons.append(
                    f"MOC imbalance direction: {unpin_setup.moc_imbalance_direction} "
                    f"— confirms release direction."
                )
            reasons.append(
                f"Expected release direction: "
                f"{unpin_setup.expected_release_direction.value}."
            )
            reasons.append(
                f"Unpin confidence: {unpin_setup.unpin_confidence:.0f}/100."
            )

        # Net GEX context.
        reasons.append(
            f"Net GEX is negative ({gex.total_net_gex:,.0f}) — "
            f"dealer short-gamma amplifies moves."
        )

        # --- Safety warnings (always included) ---
        warnings.append(
            "EXTREME RISK: This is a late-session gamma acceleration trade. "
            "Losses can be total within minutes."
        )
        warnings.append(
            f"Hard exit at {config.absolute_exit_time} ET — no exceptions. "
            f"Do NOT hold past this time."
        )
        warnings.append(
            "Theta decay is measured in seconds at this point in the session. "
            "Even correct-direction trades lose value rapidly if the move stalls."
        )
        warnings.append(
            "Bid-ask spreads are typically 2-5x wider than morning levels. "
            "Market orders will suffer significant slippage."
        )
        warnings.append(
            "Use minimum position size. This trade has the lowest expected "
            "win rate and the highest variance in the SCANIFY system."
        )
        warnings.append(
            "Reversal risk is elevated: a gamma squeeze can unwind as fast as "
            "it develops, producing violent mean-reversion."
        )

        if signal_subtype == "gamma_unpin":
            warnings.append(
                "Unpin trades are particularly sensitive to timing. "
                "A false unpin can re-pin quickly, trapping the position."
            )

        current_time = now.time()
        if current_time >= time(15, 30):
            warnings.append(
                "Inside final 30 minutes — liquidity is deteriorating rapidly. "
                "Consider reducing size by an additional 50%."
            )

        # ----- Profit target scaling -----
        # Scale profit target within [min, max] based on setup confidence.
        # Higher confidence → target closer to max.
        confidence_ratio = setup_confidence / 100.0
        profit_target_pct = (
            config.profit_target_pct_min
            + (config.profit_target_pct_max - config.profit_target_pct_min)
            * confidence_ratio
        )
        profit_target_pct = round(profit_target_pct, 2)

        return GammaScalpSignal(
            timestamp=now,
            scan_type=ScanType.GAMMA_SCALP,
            signal_subtype=signal_subtype,
            direction=setup_direction,
            strike=strike_info["strike"],
            option_type=strike_info["option_type"],
            entry_price=strike_info["mid"],
            bid=strike_info["bid"],
            ask=strike_info["ask"],
            delta=strike_info["delta"],
            gamma=strike_info["gamma"],
            profit_target_pct=profit_target_pct,
            stop_loss_pct=config.stop_loss_pct,
            absolute_exit_time=config.absolute_exit_time,
            squeeze_setup=squeeze_setup,
            unpin_setup=unpin_setup,
            reasons=reasons,
            warnings=warnings,
            confidence=round(setup_confidence, 1),
        )
