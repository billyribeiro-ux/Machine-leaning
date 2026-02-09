"""
SCANIFY Directional OTM Scanner — Core Scan #1

Implements the directional out-of-the-money options scanner for 0DTE SPX.
This scanner fuses five market-factor scores into a composite directional
signal, selects an appropriate OTM strike based on signal strength and
time-of-day, and emits an ``EntrySignal`` when all gating criteria are met.

Scan cadence: every 60 seconds during the valid window (09:45 - 15:00 ET).

Factor weights (default):
    1. Market Internals  — 30 %
    2. Options Flow       — 25 %
    3. Price Action        — 20 %
    4. GEX Structure       — 15 %
    5. Cross-Asset         — 10 %

Strike selection follows a two-step process:
    * Determine a target delta range from composite score magnitude, VIX1D,
      and time-of-day adjustments.
    * Walk the chain for the closest option matching the target delta that
      passes spread and liquidity filters; fall back one strike toward ATM
      if the initial candidate fails.

Exit parameters (profit target, stop loss) are calibrated by time zone and
returned within the signal for consumption by the exit manager.
"""

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Dict, List, Optional, Tuple
import math
import numpy as np

from .config import (
    DirectionalScanConfig, ScanifyConfig, SignalDirection,
    ScanType, TimeZone, SessionType
)
from .data_feeds import (
    OptionsChain, OptionQuote, MarketInternalsData, FuturesData,
    VIXData, SPXPriceBar, CrossAssetData, OptionType
)
from .market_internals import (
    MarketInternalsScorer, CompositeDirectionScore
)
from .gex_engine import GEXResult, GEXEngine
from .pre_market import SessionSetup, ExpectedMove


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class StrikeSelection:
    """Represents a fully validated strike chosen for a directional trade.

    Captures both the option's market data and the results of spread /
    liquidity filter checks so that downstream consumers can log the
    selection rationale.

    Attributes:
        strike: The selected strike price.
        option_type: CALL for bullish signals, PUT for bearish signals.
        delta: Absolute option delta at the time of selection.
        gamma: Option gamma.
        theta: Option theta (daily decay, negative for long positions).
        iv: Annualised implied volatility (decimal).
        bid: Current best bid price.
        ask: Current best ask price.
        mid: Mid-market price ((bid + ask) / 2).
        volume: Session cumulative volume at this strike.
        open_interest: Open interest at start of day.
        spread: Bid-ask spread in dollar terms (ask - bid).
        spread_ok: True when the spread passes the price-tier filter.
        liquidity_ok: True when both OI >= 500 and volume >= 200.
    """

    strike: float
    option_type: OptionType
    delta: float
    gamma: float
    theta: float
    iv: float
    bid: float
    ask: float
    mid: float
    volume: int
    open_interest: int
    spread: float
    spread_ok: bool
    liquidity_ok: bool


@dataclass
class EntrySignal:
    """Complete entry signal emitted by the directional scanner.

    Bundles the directional conviction, selected strike, risk parameters,
    and supporting metadata into a single record for consumption by the
    order-execution engine and dashboard alert system.

    Attributes:
        timestamp: UTC time the signal was generated.
        scan_type: Always ``ScanType.DIRECTIONAL`` for this scanner.
        direction: BULLISH or BEARISH.
        composite_score: Full composite score with per-factor breakdown.
        selected_strike: The strike that passed all filters.
        entry_price: Mid-price of the selected option (indicative fill).
        max_loss: Maximum loss per contract — equal to the premium paid
            for long OTM options.
        risk_reward_estimate: Ratio of profit target to stop loss.
        profit_target_pct: Profit target expressed as a multiple of
            premium paid (e.g. 1.5 = 150 % gain on premium).
        stop_loss_pct: Stop loss expressed as a fraction of premium
            (e.g. 0.50 = exit when 50 % of premium is lost).
        time_zone: Current intraday time zone at signal generation.
        session_type: Session regime from the pre-market setup.
        vix1d: VIX1D level at signal time.
        reasons: Human-readable list of factors supporting the signal.
        warnings: Any cautionary notes (borderline factors, time
            concerns, approaching event windows, etc.).
        confidence: Numeric confidence score mapped from the composite
            magnitude, range 0 - 100.
    """

    timestamp: datetime
    scan_type: ScanType = ScanType.DIRECTIONAL
    direction: SignalDirection = SignalDirection.NEUTRAL
    composite_score: CompositeDirectionScore = field(
        default_factory=CompositeDirectionScore
    )
    selected_strike: Optional[StrikeSelection] = None
    entry_price: float = 0.0
    max_loss: float = 0.0
    risk_reward_estimate: float = 0.0
    profit_target_pct: float = 0.0
    stop_loss_pct: float = 0.0
    time_zone: TimeZone = TimeZone.MORNING_SESSION
    session_type: SessionType = SessionType.RANGE
    vix1d: float = 0.0
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    confidence: float = 0.0


# ---------------------------------------------------------------------------
# Directional Scanner
# ---------------------------------------------------------------------------

class DirectionalScanner:
    """Core Scan #1 — Directional OTM Scanner for 0DTE SPX.

    Orchestrates the five-factor scoring pipeline, strike selection, and
    risk-parameter calculation to produce actionable ``EntrySignal``
    objects.

    The scanner maintains a ``MarketInternalsScorer`` instance for
    per-factor scoring and delegates composite computation to it.

    Parameters
    ----------
    config : ScanifyConfig
        Master SCANIFY configuration containing ``DirectionalScanConfig``
        and all related sub-configs.

    Usage
    -----
    >>> scanner = DirectionalScanner(config)
    >>> signal = scanner.scan(
    ...     chain, internals, flow_data, futures, gex,
    ...     cross_asset, vix_data, session_setup, price_bars,
    ...     tick_history,
    ... )
    >>> if signal is not None:
    ...     # route to order manager
    ...     pass
    """

    def __init__(self, config: ScanifyConfig) -> None:
        """Initialise the directional scanner.

        Args:
            config: Master SCANIFY configuration instance.  The
                ``directional``, ``exit``, and ``risk`` sub-configs
                drive all scanner behaviour.
        """
        self.config = config
        self._scorer = MarketInternalsScorer()

    # ------------------------------------------------------------------
    # Time zone mapping
    # ------------------------------------------------------------------

    @staticmethod
    def get_current_timezone(dt: datetime) -> TimeZone:
        """Map a datetime to the corresponding intraday TimeZone enum.

        Time boundaries (Eastern Time):
            * PRE_MARKET:       07:00 - 09:30
            * OPENING_AUCTION:  09:30 - 09:45
            * MORNING_SESSION:  09:45 - 11:30
            * MIDDAY_LULL:      11:30 - 13:30
            * AFTERNOON_ACCEL:  13:30 - 15:00
            * POWER_HOUR:       15:00 - 15:45
            * SETTLEMENT:       15:45 - 16:00

        If the time falls outside all defined windows (e.g. after 16:00
        or before 07:00), ``PRE_MARKET`` or ``SETTLEMENT`` is returned
        as a conservative fallback.

        Args:
            dt: Datetime whose time component is used for classification.
                Assumed to be in Eastern Time.

        Returns:
            The matching ``TimeZone`` enum member.
        """
        t = dt.time()

        if t < time(7, 0):
            return TimeZone.PRE_MARKET
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
        if t < time(16, 0):
            return TimeZone.SETTLEMENT

        # After market close — conservative fallback.
        return TimeZone.SETTLEMENT

    # ------------------------------------------------------------------
    # Scan window validation
    # ------------------------------------------------------------------

    def is_valid_scan_window(
        self,
        dt: datetime,
        session_setup: SessionSetup,
    ) -> Tuple[bool, str]:
        """Determine whether the current time is a valid scanning window.

        A scan is valid when **all** of the following hold:

        1. The time is within the configured scan window
           (default 09:45 - 15:00 ET).
        2. The time is not inside the opening auction (09:30 - 09:45).
        3. The time does not fall within any event-driven suspend window
           from the session setup's ``EventRisk``.

        Args:
            dt: Current datetime (assumed Eastern Time).
            session_setup: Pre-market session setup containing event risk
                windows.

        Returns:
            A ``(valid, reason)`` tuple.  ``valid`` is True when scanning
            may proceed; ``reason`` provides a human-readable explanation
            when scanning is blocked.
        """
        t = dt.time()
        dc = self.config.directional

        # Parse configured scan boundaries.
        scan_start_parts = dc.scan_start.split(":")
        scan_end_parts = dc.scan_end.split(":")
        scan_start = time(int(scan_start_parts[0]), int(scan_start_parts[1]))
        scan_end = time(int(scan_end_parts[0]), int(scan_end_parts[1]))

        # 1. Check overall scan window.
        if t < scan_start:
            return False, f"Before scan window (starts at {dc.scan_start})"
        if t >= scan_end:
            return False, f"After scan window (ends at {dc.scan_end})"

        # 2. Opening auction block.
        if time(9, 30) <= t < time(9, 45):
            return False, "Inside opening auction (09:30-09:45)"

        # 3. Event suspend windows.
        for sw_start, sw_end in session_setup.event_risk.suspend_windows:
            if sw_start <= t < sw_end:
                return (
                    False,
                    f"Inside event suspend window "
                    f"({sw_start.strftime('%H:%M')}-"
                    f"{sw_end.strftime('%H:%M')})",
                )

        return True, "Scan window valid"

    # ------------------------------------------------------------------
    # Composite direction scoring
    # ------------------------------------------------------------------

    def compute_direction(
        self,
        internals: MarketInternalsData,
        flow_data: dict,
        spx_price: float,
        vwap: float,
        em: ExpectedMove,
        futures: FuturesData,
        gex: GEXResult,
        cross_asset: CrossAssetData,
        vix_data: VIXData,
        tick_history: list,
    ) -> CompositeDirectionScore:
        """Orchestrate all five factor scores and produce a composite signal.

        Extracts the required parameters from each data structure and
        delegates to the ``MarketInternalsScorer`` methods for per-factor
        scoring, then combines them via ``compute_composite_score``.

        Factor scoring details:

        1. **Market Internals** — TICK 10-min average, cumulative TICK,
           TRIN, A/D ratio, up/down volume from ``internals`` and
           ``tick_history``.
        2. **Options Flow** — P/C ratio, net premium flow, block
           direction, sweep direction from ``flow_data``.
        3. **Price Action** — SPX vs VWAP, expected-move boundaries,
           ES cumulative delta and book imbalance, 5-min momentum.
        4. **GEX Structure** — net GEX sign, gamma-flip position,
           movement toward +GEX, transition zone breakout.
        5. **Cross-Asset** — VIX direction (vs VIX9D proxy), VIX1D
           vs average, yields, DXY.

        Args:
            internals: Current NYSE breadth data.
            flow_data: Options flow dictionary with keys:
                ``put_call_ratio`` (float), ``net_premium_flow`` (float),
                ``net_block_direction`` (1 / -1 / 0),
                ``sweep_direction`` (1 / -1 / 0).
            spx_price: Current SPX cash index price.
            vwap: Session VWAP.
            em: Expected-move envelope from the pre-market setup.
            futures: ES futures data (for cumulative delta and book).
            gex: Current GEX snapshot.
            cross_asset: Cross-asset context (yields, DXY).
            vix_data: VIX family snapshot.
            tick_history: Recent TICK readings for the rolling average.

        Returns:
            A ``CompositeDirectionScore`` with validity gating applied.
        """
        dc = self.config.directional

        # ----- 1. Market Internals -----
        internals_score = self._scorer.score_market_internals(
            internals, tick_history,
        )

        # ----- 2. Options Flow -----
        flow_score = self._scorer.score_options_flow(
            put_call_ratio=flow_data.get("put_call_ratio", 1.0),
            net_premium_flow=flow_data.get("net_premium_flow", 0.0),
            net_block_direction=flow_data.get("net_block_direction", 0.0),
            sweep_direction=flow_data.get("sweep_direction", 0.0),
        )

        # ----- 3. Price Action -----
        # Compute 5-minute momentum from TICK history and VWAP.
        momentum_5min = self._compute_momentum(tick_history, spx_price, vwap)

        # ES cumulative delta and direction from market internals.
        es_cum_delta = internals.cumulative_delta
        # Simplified heuristic: rising if delta is positive.
        es_cum_delta_rising = es_cum_delta > 0

        # ES order-book imbalance: total bid depth / total ask depth.
        es_book_imbalance = self._compute_book_imbalance(futures)

        price_action_score = self._scorer.score_price_action(
            spx_price=spx_price,
            vwap=vwap,
            em_upper=em.upper_1sigma,
            em_lower=em.lower_1sigma,
            es_cum_delta=es_cum_delta,
            es_cum_delta_rising=es_cum_delta_rising,
            es_book_imbalance=es_book_imbalance,
            momentum_5min=momentum_5min,
        )

        # ----- 4. GEX Structure -----
        net_gex_positive = gex.total_net_gex >= 0
        above_gamma_flip = (
            spx_price >= gex.gamma_flip_level
            if gex.gamma_flip_level > 0
            else True
        )

        # Movement toward positive gamma: price is rising toward (or staying
        # above) the gamma flip level, or heading toward the +GEX strike.
        moving_toward_plus_gex = (
            (spx_price > vwap and spx_price < gex.plus_gex_strike)
            if gex.plus_gex_strike > 0
            else (spx_price > vwap)
        )

        tz_lo, tz_hi = gex.transition_zone
        in_transition_zone = (
            tz_lo > 0 and tz_hi > 0 and tz_lo <= spx_price <= tz_hi
        )
        breaking_above_tz = (
            tz_hi > 0 and spx_price > tz_hi and momentum_5min > 0
        )
        breaking_below_tz = (
            tz_lo > 0 and spx_price < tz_lo and momentum_5min < 0
        )

        gex_score = self._scorer.score_gex_structure(
            net_gex_positive=net_gex_positive,
            above_gamma_flip=above_gamma_flip,
            moving_toward_plus_gex=moving_toward_plus_gex,
            in_transition_zone=in_transition_zone,
            breaking_above_tz=breaking_above_tz,
            breaking_below_tz=breaking_below_tz,
        )

        # ----- 5. Cross-Asset -----
        # VIX direction: compare current VIX to VIX9D as a proxy for the
        # recent average.  VIX < VIX9D suggests implied vol is declining.
        vix_falling = vix_data.vix < vix_data.vix9d
        spx_rising = spx_price > vwap

        # VIX1D relative to its average: VIX9D serves as a medium-term
        # anchor.  Positive difference means VIX1D is above average
        # (bearish signal).
        vix1d_vs_avg = vix_data.vix1d - vix_data.vix9d

        # Yields: use the intraday change (in bps).
        yield_falling = cross_asset.us_10y_yield_change < -2.0
        yield_rising_sharply = cross_asset.us_10y_yield_change > 5.0

        # DXY: percentage change thresholds.
        dxy_falling = cross_asset.dxy_change < -0.10
        dxy_rising_sharply = cross_asset.dxy_change > 0.30

        cross_asset_score = self._scorer.score_cross_asset(
            vix_falling=vix_falling,
            spx_rising=spx_rising,
            vix1d_vs_avg=vix1d_vs_avg,
            yield_falling=yield_falling,
            yield_rising_sharply=yield_rising_sharply,
            dxy_falling=dxy_falling,
            dxy_rising_sharply=dxy_rising_sharply,
        )

        # ----- Composite -----
        weights = {
            "market_internals": dc.weight_market_internals,
            "options_flow": dc.weight_options_flow,
            "price_action": dc.weight_price_action,
            "gex_structure": dc.weight_gex_structure,
            "cross_asset": dc.weight_cross_asset,
        }

        composite = self._scorer.compute_composite_score(
            internals=internals_score,
            flow=flow_score,
            price_action=price_action_score,
            gex=gex_score,
            cross_asset=cross_asset_score,
            weights=weights,
            signal_threshold=dc.signal_threshold,
            min_factors_agreeing=dc.min_factors_agreeing,
            max_opposing_factor_score=dc.max_opposing_factor_score,
        )

        return composite

    # ------------------------------------------------------------------
    # Strike selection
    # ------------------------------------------------------------------

    def select_strike(
        self,
        chain: OptionsChain,
        direction: SignalDirection,
        score_magnitude: float,
        vix1d: float,
        timezone: TimeZone,
        config: DirectionalScanConfig,
    ) -> Optional[StrikeSelection]:
        """Select the optimal OTM strike for a directional trade.

        The selection process follows three steps:

        **Step 1 — Target delta range.**
        Base deltas are chosen from the score magnitude:
            * Moderate signal (40-65): delta 0.15 - 0.25
            * Strong signal (>65):     delta 0.25 - 0.40

        Time-of-day adjustments shift the target closer to ATM (higher
        delta) during midday and afternoon to compensate for faster
        theta decay:
            * MIDDAY_LULL:      +0.05
            * AFTERNOON_ACCEL:  +0.10
            * POWER_HOUR:       +0.10
            * SETTLEMENT:       +0.10

        VIX1D adjustments:
            * VIX1D > 25: lower delta targets by 0.05 (move further OTM
              for cheaper premium).
            * VIX1D < 12: raise delta targets by 0.05 (move closer to ATM
              for sufficient gamma).

        **Step 2 — Filter for option type.**
        Calls for BULLISH, puts for BEARISH.

        **Step 3 — Walk candidates.**
        Sort eligible options by proximity to target delta midpoint.  For
        each candidate check:
            * Spread filter (price-tier based max spread).
            * Liquidity filter (min OI 500, min volume 200).
        If the best-delta candidate fails, move one strike closer to ATM
        and recheck.

        Args:
            chain: Current 0DTE options chain.
            direction: BULLISH or BEARISH.
            score_magnitude: Absolute value of the composite weighted score.
            vix1d: Current VIX1D level.
            timezone: Current intraday time zone.
            config: Directional scan configuration.

        Returns:
            A ``StrikeSelection`` if a valid strike is found, else None.
        """
        if not chain.quotes:
            return None

        if direction == SignalDirection.NEUTRAL:
            return None

        # ----- Step 1: target delta range -----
        if score_magnitude >= config.strong_signal_threshold:
            target_delta_min = config.strong_delta_min
            target_delta_max = config.strong_delta_max
        else:
            target_delta_min = config.moderate_delta_min
            target_delta_max = config.moderate_delta_max

        # Time-of-day adjustment (shift toward ATM = higher delta).
        tod_adjust = 0.0
        if timezone == TimeZone.MIDDAY_LULL:
            tod_adjust = config.delta_adjust_midday
        elif timezone in (
            TimeZone.AFTERNOON_ACCEL,
            TimeZone.POWER_HOUR,
            TimeZone.SETTLEMENT,
        ):
            tod_adjust = config.delta_adjust_afternoon

        target_delta_min += tod_adjust
        target_delta_max += tod_adjust

        # VIX1D adjustment on delta targets.
        if vix1d > config.vix1d_high_threshold:
            # High VIX: move further OTM (lower delta) for cheaper premium.
            target_delta_min = max(0.05, target_delta_min - 0.05)
            target_delta_max = max(0.10, target_delta_max - 0.05)
        elif vix1d < config.vix1d_low_threshold:
            # Low VIX: move closer to ATM (higher delta) for more gamma.
            target_delta_min = min(0.45, target_delta_min + 0.05)
            target_delta_max = min(0.50, target_delta_max + 0.05)

        target_delta_mid = (target_delta_min + target_delta_max) / 2.0

        # ----- Step 2: filter for option type -----
        desired_type = (
            OptionType.CALL if direction == SignalDirection.BULLISH
            else OptionType.PUT
        )

        candidates: List[OptionQuote] = [
            q for q in chain.quotes
            if q.option_type == desired_type and q.bid > 0 and q.ask > 0
        ]

        if not candidates:
            return None

        # ----- Step 3: sort by delta proximity and walk -----
        # Use absolute delta so that both calls (positive delta) and puts
        # (negative delta) are compared uniformly.
        candidates.sort(
            key=lambda q: abs(abs(q.delta) - target_delta_mid)
        )

        # Build a map of all strikes for the desired type to enable the
        # "move one strike closer to ATM" fallback.
        all_strikes_for_type: Dict[float, OptionQuote] = {
            q.strike: q for q in candidates
        }
        sorted_strikes = sorted(all_strikes_for_type.keys())
        underlying = chain.underlying_price

        for candidate in candidates:
            selection = self._evaluate_candidate(candidate, config)
            if selection is not None and selection.spread_ok and selection.liquidity_ok:
                return selection

            # Fallback: move one strike closer to ATM and recheck.
            fallback_strike = self._get_one_strike_closer_to_atm(
                candidate.strike, sorted_strikes, underlying, desired_type,
            )
            if (
                fallback_strike is not None
                and fallback_strike in all_strikes_for_type
            ):
                fb_quote = all_strikes_for_type[fallback_strike]
                fb_selection = self._evaluate_candidate(fb_quote, config)
                if (
                    fb_selection is not None
                    and fb_selection.spread_ok
                    and fb_selection.liquidity_ok
                ):
                    return fb_selection

        return None

    # ------------------------------------------------------------------
    # Profit target / stop loss / risk-reward
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_profit_target(timezone: TimeZone) -> float:
        """Determine the profit target as a multiple of premium paid.

        Profit targets decrease through the day as theta decay
        accelerates and the option's remaining gamma diminishes:

            * MORNING_SESSION (before 11:00):  1.0x - 2.0x  -> use 1.5x
            * MIDDAY_LULL    (11:00 - 14:00):  0.75x - 1.5x -> use 1.0x
            * AFTERNOON_ACCEL (14:00 - 15:00): 0.5x - 1.0x  -> use 0.75x
            * POWER_HOUR / SETTLEMENT (after 15:00):
              0.3x - 0.5x -> use 0.4x

        Args:
            timezone: Current intraday time zone.

        Returns:
            Profit target as a decimal multiple of entry premium.
        """
        if timezone == TimeZone.MORNING_SESSION:
            return 1.50
        elif timezone == TimeZone.MIDDAY_LULL:
            return 1.00
        elif timezone == TimeZone.AFTERNOON_ACCEL:
            return 0.75
        else:
            # POWER_HOUR, SETTLEMENT, or any late-session fallback.
            return 0.40

    @staticmethod
    def calculate_stop_loss(timezone: TimeZone) -> float:
        """Determine the initial stop loss as a fraction of premium paid.

        The stop loss is set at 50 % of the entry premium across all
        time zones.  This means the position is exited when 50 % of the
        premium has been lost, providing a consistent 2:1 or better
        risk-reward ratio during the morning session and tapering through
        the day.

        Args:
            timezone: Current intraday time zone (reserved for future
                time-adaptive stops; currently uniform at 0.50).

        Returns:
            Stop loss fraction (0.50 = exit at 50 % premium loss).
        """
        return 0.50

    @staticmethod
    def estimate_risk_reward(
        entry_price: float,
        profit_target_pct: float,
        stop_loss_pct: float,
    ) -> float:
        """Estimate the reward-to-risk ratio for a long option trade.

        Reward is defined as ``entry_price * profit_target_pct`` (the
        dollar gain at the target).  Risk is ``entry_price *
        stop_loss_pct`` (the dollar amount lost at the stop).

        The ratio is simply ``profit_target_pct / stop_loss_pct`` since
        the entry_price cancels.

        Args:
            entry_price: Mid-price premium paid per contract.
            profit_target_pct: Profit target as a multiple of premium.
            stop_loss_pct: Stop loss as a fraction of premium.

        Returns:
            Reward-to-risk ratio (profit_target / stop_loss).  Returns
            0.0 when stop_loss_pct is zero or negative.
        """
        if stop_loss_pct <= 0.0:
            return 0.0
        return profit_target_pct / stop_loss_pct

    # ------------------------------------------------------------------
    # Main scan method
    # ------------------------------------------------------------------

    def scan(
        self,
        chain: OptionsChain,
        internals: MarketInternalsData,
        flow_data: dict,
        futures: FuturesData,
        gex: GEXResult,
        cross_asset: CrossAssetData,
        vix_data: VIXData,
        session_setup: SessionSetup,
        price_bars: List[SPXPriceBar],
        tick_history: list,
    ) -> Optional[EntrySignal]:
        """Execute one scan cycle of the Directional OTM Scanner.

        This is the primary entry point, intended to be called every 60
        seconds by the scan scheduler.  It performs the full pipeline:

        1. **Validate scan window** — reject if outside 09:45 - 15:00,
           inside an event suspend window, or during the opening auction.
        2. **Compute VWAP** from intraday price bars (falls back to the
           pre-market setup reference if no bars are available).
        3. **Compute composite direction score** via all five factors.
        4. **Gate check** — return None if the composite signal is not
           valid (threshold, factor agreement, opposition).
        5. **Select strike** — find the best OTM option matching the
           signal direction, adjusted for score magnitude, VIX1D, and
           time of day.
        6. **If no valid strike** — return None.
        7. **Calculate risk parameters** — profit target, stop loss,
           risk-reward ratio.
        8. **Build reasons list** from composite score details.
        9. **Build warnings** (borderline factors, time concerns, etc.).
        10. **Compute confidence** — map composite score magnitude to
            0-100.
        11. **Return EntrySignal**.

        Args:
            chain: Current 0DTE SPX options chain.
            internals: NYSE market-breadth internals snapshot.
            flow_data: Real-time options flow data dict with keys:
                ``put_call_ratio``, ``net_premium_flow``,
                ``net_block_direction``, ``sweep_direction``.
            futures: ES futures data.
            gex: Current GEX snapshot.
            cross_asset: Cross-asset context data.
            vix_data: VIX / VIX1D / VIX9D snapshot.
            session_setup: Pre-market session setup.
            price_bars: Chronological list of 1-minute SPX price bars.
            tick_history: Recent NYSE TICK readings.

        Returns:
            An ``EntrySignal`` when all conditions are met, or None
            when the scan does not produce an actionable signal.
        """
        now = datetime.now()
        dc = self.config.directional

        # ---- 1. Validate scan window ----
        valid, reason = self.is_valid_scan_window(now, session_setup)
        if not valid:
            return None

        # ---- 2. Compute VWAP ----
        vwap = self._compute_vwap(price_bars)
        if vwap is None:
            # Fallback: use prior session VWAP from the setup.
            vwap = session_setup.key_levels.prior_vwap
        if vwap is None or vwap <= 0:
            # Final fallback: use the underlying price.
            vwap = (
                chain.underlying_price
                if chain.underlying_price > 0
                else 0.0
            )
        if vwap <= 0:
            return None

        spx_price = (
            chain.underlying_price
            if chain.underlying_price > 0
            else vwap
        )

        # ---- 3. Compute composite direction score ----
        composite = self.compute_direction(
            internals=internals,
            flow_data=flow_data,
            spx_price=spx_price,
            vwap=vwap,
            em=session_setup.expected_move,
            futures=futures,
            gex=gex,
            cross_asset=cross_asset,
            vix_data=vix_data,
            tick_history=tick_history,
        )

        # ---- 4. Gate check ----
        if not composite.signal_valid:
            return None

        direction = composite.direction
        if direction == SignalDirection.NEUTRAL:
            return None

        # ---- 5. Select strike ----
        timezone = self.get_current_timezone(now)
        score_magnitude = abs(composite.weighted_score)

        selected = self.select_strike(
            chain=chain,
            direction=direction,
            score_magnitude=score_magnitude,
            vix1d=vix_data.vix1d,
            timezone=timezone,
            config=dc,
        )

        # ---- 6. No valid strike ----
        if selected is None:
            return None

        # ---- 7. Calculate risk parameters ----
        entry_price = selected.mid
        if entry_price <= 0:
            return None

        max_loss = entry_price  # Long option: max loss = premium paid.
        profit_target_pct = self.calculate_profit_target(timezone)
        stop_loss_pct = self.calculate_stop_loss(timezone)
        risk_reward = self.estimate_risk_reward(
            entry_price, profit_target_pct, stop_loss_pct,
        )

        # ---- 8. Build reasons ----
        reasons = self._build_reasons(composite, selected, timezone)

        # ---- 9. Build warnings ----
        warnings = self._build_warnings(
            composite, selected, timezone, vix_data, session_setup,
        )

        # ---- 10. Compute confidence ----
        confidence = self._compute_confidence(composite)

        # ---- 11. Assemble and return EntrySignal ----
        return EntrySignal(
            timestamp=now,
            scan_type=ScanType.DIRECTIONAL,
            direction=direction,
            composite_score=composite,
            selected_strike=selected,
            entry_price=entry_price,
            max_loss=max_loss,
            risk_reward_estimate=round(risk_reward, 2),
            profit_target_pct=profit_target_pct,
            stop_loss_pct=stop_loss_pct,
            time_zone=timezone,
            session_type=session_setup.session_type,
            vix1d=vix_data.vix1d,
            reasons=reasons,
            warnings=warnings,
            confidence=round(confidence, 1),
        )

    # ==================================================================
    # Private helpers
    # ==================================================================

    @staticmethod
    def _compute_vwap(price_bars: List[SPXPriceBar]) -> Optional[float]:
        """Compute the session VWAP from 1-minute price bars.

        Uses the typical price ``(high + low + close) / 3`` weighted by
        bar volume.

        Args:
            price_bars: Chronologically ordered 1-minute bars.

        Returns:
            VWAP as a float, or None if no usable bars exist.
        """
        if not price_bars:
            return None

        prices = np.array(
            [(b.high + b.low + b.close) / 3.0 for b in price_bars],
            dtype=np.float64,
        )
        volumes = np.array(
            [b.volume for b in price_bars],
            dtype=np.float64,
        )

        total_volume = volumes.sum()
        if total_volume == 0:
            return None

        vwap = float(np.dot(prices, volumes) / total_volume)
        return round(vwap, 2)

    @staticmethod
    def _compute_momentum(
        tick_history: list,
        spx_price: float,
        vwap: float,
    ) -> float:
        """Estimate 5-minute price momentum from TICK history and VWAP.

        Uses a blended heuristic: the normalised mean of recent TICK
        readings (capturing short-term buying/selling pressure) combined
        with the SPX-to-VWAP displacement (capturing medium-term trend).

        The TICK component is weighted 70 % and the VWAP displacement
        30 %, producing a momentum proxy suitable for the price-action
        scorer's ``momentum_5min`` parameter.

        Args:
            tick_history: Recent TICK readings (floats).
            spx_price: Current SPX price.
            vwap: Session VWAP.

        Returns:
            A momentum estimate (positive = bullish acceleration,
            negative = bearish acceleration, near-zero = deceleration).
        """
        if not tick_history:
            # Fall back to simple VWAP displacement.
            if vwap > 0:
                return (spx_price - vwap) / vwap
            return 0.0

        recent = tick_history[-10:] if len(tick_history) >= 10 else tick_history
        tick_arr = np.array(recent, dtype=np.float64)
        tick_mean = float(tick_arr.mean())

        # Normalise TICK mean to a [-1, +1]-ish range.
        normalized_tick = tick_mean / 1000.0

        # VWAP displacement (small magnitude).
        vwap_disp = (spx_price - vwap) / vwap if vwap > 0 else 0.0

        return normalized_tick * 0.7 + vwap_disp * 0.3

    @staticmethod
    def _compute_book_imbalance(futures: FuturesData) -> float:
        """Compute the ES order-book bid/ask size imbalance.

        Returns the ratio of total bid depth size to total ask depth
        size.  A ratio > 1 indicates bid-heavy (bullish), < 1 indicates
        ask-heavy (bearish).

        Args:
            futures: ES futures data with bid_depth and ask_depth.

        Returns:
            Bid-to-ask imbalance ratio; defaults to 1.0 (balanced) when
            depth data is unavailable.
        """
        if not futures.bid_depth or not futures.ask_depth:
            return 1.0

        total_bid = sum(size for _, size in futures.bid_depth)
        total_ask = sum(size for _, size in futures.ask_depth)

        if total_ask <= 0:
            return 1.0

        return total_bid / total_ask

    def _evaluate_candidate(
        self,
        quote: OptionQuote,
        config: DirectionalScanConfig,
    ) -> Optional[StrikeSelection]:
        """Build a ``StrikeSelection`` from a candidate quote and run filters.

        Evaluates both the spread filter (tiered by option price) and
        the liquidity filter (minimum OI and volume).  Both filter
        outcomes are recorded in the result so callers can decide whether
        to accept or reject the candidate.

        Args:
            quote: The option quote to evaluate.
            config: Directional scan configuration for filter thresholds.

        Returns:
            A ``StrikeSelection`` with ``spread_ok`` and ``liquidity_ok``
            flags set, or None if the quote has invalid pricing (zero or
            negative bid/ask).
        """
        if quote.bid <= 0 or quote.ask <= 0:
            return None

        spread = quote.ask - quote.bid
        mid = quote.mid if quote.mid > 0 else (quote.bid + quote.ask) / 2.0

        # Spread filter: tiered by option mid-price.
        if mid < 5.0:
            max_spread = config.max_spread_under_5
        elif mid < 20.0:
            max_spread = config.max_spread_5_to_20
        else:
            max_spread = config.max_spread_over_20

        spread_ok = spread <= max_spread

        # Liquidity filter.
        liquidity_ok = (
            quote.open_interest >= config.min_open_interest
            and quote.volume >= config.min_volume
        )

        return StrikeSelection(
            strike=quote.strike,
            option_type=quote.option_type,
            delta=abs(quote.delta),
            gamma=quote.gamma,
            theta=quote.theta,
            iv=quote.implied_vol,
            bid=quote.bid,
            ask=quote.ask,
            mid=mid,
            volume=quote.volume,
            open_interest=quote.open_interest,
            spread=round(spread, 2),
            spread_ok=spread_ok,
            liquidity_ok=liquidity_ok,
        )

    @staticmethod
    def _get_one_strike_closer_to_atm(
        current_strike: float,
        sorted_strikes: List[float],
        underlying: float,
        option_type: OptionType,
    ) -> Optional[float]:
        """Return the next strike one step closer to ATM.

        For calls (OTM = above underlying), "closer to ATM" means a
        lower strike.  For puts (OTM = below underlying), "closer to
        ATM" means a higher strike.

        Args:
            current_strike: The strike that failed filters.
            sorted_strikes: All available strikes in ascending order.
            underlying: Current underlying price.
            option_type: CALL or PUT.

        Returns:
            The adjacent strike closer to ATM, or None if already at ATM
            or no adjacent strike exists.
        """
        if current_strike not in sorted_strikes:
            return None

        idx = sorted_strikes.index(current_strike)

        if option_type == OptionType.CALL:
            # OTM calls are above the underlying; closer to ATM = lower strike.
            if idx > 0:
                return sorted_strikes[idx - 1]
        else:
            # OTM puts are below the underlying; closer to ATM = higher strike.
            if idx < len(sorted_strikes) - 1:
                return sorted_strikes[idx + 1]

        return None

    @staticmethod
    def _build_reasons(
        composite: CompositeDirectionScore,
        selected: StrikeSelection,
        timezone: TimeZone,
    ) -> List[str]:
        """Build a human-readable reasons list from the composite score.

        Summarises which factors contributed to the signal, the magnitude
        of each, and the strike selection rationale.

        Args:
            composite: The composite directional score.
            selected: The selected strike.
            timezone: Current intraday time zone.

        Returns:
            List of concise reason strings.
        """
        reasons: List[str] = []

        direction_label = composite.direction.value.upper()
        reasons.append(
            f"{direction_label} signal: composite score "
            f"{composite.weighted_score:+.1f} "
            f"({composite.factors_agreeing}/5 factors agreeing)"
        )

        # Per-factor summaries.
        mi = composite.market_internals
        if mi.total_score != 0:
            reasons.append(
                f"Market internals: {mi.total_score:+.1f}"
            )

        of = composite.options_flow
        if of.total_score != 0:
            reasons.append(
                f"Options flow: {of.total_score:+.1f}"
            )

        pa = composite.price_action
        if pa.total_score != 0:
            reasons.append(
                f"Price action: {pa.total_score:+.1f}"
            )

        gx = composite.gex_structure
        if gx.total_score != 0:
            reasons.append(
                f"GEX structure: {gx.total_score:+.1f} "
                f"(modifier {gx.net_gex_modifier:+.0%})"
            )

        ca = composite.cross_asset
        if ca.total_score != 0:
            reasons.append(
                f"Cross-asset: {ca.total_score:+.1f}"
            )

        # Strike rationale.
        type_label = selected.option_type.value.upper()
        reasons.append(
            f"Selected {selected.strike:.0f} {type_label} "
            f"(delta {selected.delta:.2f}, IV {selected.iv:.1%}, "
            f"mid ${selected.mid:.2f})"
        )

        reasons.append(f"Time zone: {timezone.value}")

        return reasons

    @staticmethod
    def _build_warnings(
        composite: CompositeDirectionScore,
        selected: StrikeSelection,
        timezone: TimeZone,
        vix_data: VIXData,
        session_setup: SessionSetup,
    ) -> List[str]:
        """Build a list of cautionary warnings for the signal.

        Flags borderline factors, adverse time conditions, wide spreads,
        event proximity, and VIX regime concerns.

        Args:
            composite: The composite directional score.
            selected: The selected strike.
            timezone: Current intraday time zone.
            vix_data: VIX family snapshot.
            session_setup: Pre-market session setup.

        Returns:
            List of warning strings (may be empty).
        """
        warnings: List[str] = []

        # Borderline score (close to threshold of 40).
        if abs(composite.weighted_score) < 50.0:
            warnings.append(
                f"Composite score {composite.weighted_score:+.1f} is "
                f"borderline (barely above 40 threshold)"
            )

        # Only minimum factor agreement.
        if composite.factors_agreeing == 3:
            warnings.append(
                "Only 3 of 5 factors agree — minimum threshold"
            )

        # Late in the day: reduced profit opportunity.
        if timezone in (TimeZone.POWER_HOUR, TimeZone.SETTLEMENT):
            warnings.append(
                "Late-day scan: reduced profit potential and "
                "accelerating theta decay"
            )
        elif timezone == TimeZone.AFTERNOON_ACCEL:
            warnings.append(
                "Afternoon session: lower profit targets apply"
            )

        # Notable spread (even if within filter).
        if selected.spread > 0.50:
            warnings.append(
                f"Spread ${selected.spread:.2f} is notable — "
                f"watch for slippage"
            )

        # Modest volume (even if above minimum).
        if selected.volume < 500:
            warnings.append(
                f"Volume {selected.volume} is modest — "
                f"fills may be slow"
            )

        # Elevated VIX1D.
        if vix_data.vix1d > 25.0:
            warnings.append(
                f"VIX1D at {vix_data.vix1d:.1f} — elevated vol, "
                f"wider moves expected"
            )

        # Event risk.
        if session_setup.event_risk.risk_level in ("high", "extreme"):
            warnings.append(
                f"Event risk is "
                f"{session_setup.event_risk.risk_level.upper()} "
                f"— monitor for suspend windows"
            )

        # Strong opposition from at least one factor.
        if composite.has_strong_opposition:
            warnings.append(
                "Strong opposition detected in at least one factor"
            )

        # Volatile session regime.
        if session_setup.session_type == SessionType.VOLATILE:
            warnings.append(
                "Session classified as VOLATILE — consider reducing "
                "position size by 50%"
            )

        return warnings

    @staticmethod
    def _compute_confidence(composite: CompositeDirectionScore) -> float:
        """Map the composite score magnitude to a 0-100 confidence scale.

        The mapping is linear between the signal threshold (40) and a
        maximum practical score (100):

        * ``|score| <= 40``  -> confidence 0  (should not occur when
          ``signal_valid`` is True, but handled defensively).
        * ``|score| == 70``  -> confidence ~50.
        * ``|score| >= 100`` -> confidence 100.

        Args:
            composite: The composite directional score.

        Returns:
            Confidence value in the range [0, 100].
        """
        magnitude = abs(composite.weighted_score)

        # Below threshold: 0 confidence.
        if magnitude <= 40.0:
            return 0.0

        # Linear scale: 40 -> 0, 100 -> 100.
        confidence = ((magnitude - 40.0) / 60.0) * 100.0
        return max(0.0, min(100.0, confidence))
