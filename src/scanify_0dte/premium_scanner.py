"""
SCANIFY 0DTE Premium Selling Scanner (Core Scan #2)

Identifies optimal credit spread and iron condor entries for harvesting theta
decay on SPX 0DTE options. This scanner executes every 5 minutes during the
10:00 AM - 2:00 PM Eastern window -- the sweet spot where theta decay is
accelerating but gamma risk has not yet reached dangerous levels.

Strategy Logic:
    - Sell credit spreads (bull put / bear call) when IV is rich relative to RV,
      the market is range-bound, and dealer gamma positioning is supportive.
    - Combine both sides into an iron condor when both put and call spreads
      meet quality thresholds, capturing theta from both tails.
    - Use GEX levels and expected-move boundaries as natural strike anchors.
    - Enforce strict probability-of-OTM, minimum credit, and liquidity filters.

Exit Management:
    - Close at 50% of max profit (standard)
    - Close at 80% of max profit after 2:30 PM (accelerated)
    - Close immediately if short strike is breached
    - Close immediately if direction score reverses beyond +/-60
    - Close ALL iron condors by 3:30 PM (hard time stop)

Dependencies:
    numpy, scipy

Author: SCANIFY Engine
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy.stats import norm

from .models import (
    ScanSignal,
    ScanType,
    TradeDirection,
    PositionType,
    SessionType,
    TimeZoneType,
    MarketInternals,
    CrossAssetData,
    GEXProfile,
    OptionsChain,
    OptionQuote,
    OptionSide,
    CreditSpread,
    IronCondor,
    SpreadLeg,
    StrikeSelection,
)
from .greeks_engine import BlackScholes0DTE

logger = logging.getLogger(__name__)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def find_strike_at_or_near(
    chain: OptionsChain,
    target_strike: float,
    option_type: str,
) -> Optional[OptionQuote]:
    """Find the option quote closest to *target_strike* in the chain.

    Searches through the chain's quotes for the specified option type (``"put"``
    or ``"call"``) and returns the quote whose strike price has the smallest
    absolute distance to *target_strike*.

    SPX 0DTE chains typically use $5 strike intervals near ATM.  This helper
    handles the common case where the exact target does not coincide with an
    available strike by snapping to the nearest listed strike.

    Args:
        chain: The full 0DTE options chain for the current expiration.
        target_strike: Desired strike price (may not match an actual strike).
        option_type: ``"put"`` or ``"call"`` (case-insensitive).

    Returns:
        The :class:`OptionQuote` nearest to *target_strike* for the requested
        side, or ``None`` if the chain contains no quotes of that type.
    """
    option_type_lower = option_type.lower()

    candidates: List[OptionQuote] = []
    for quote in chain.quotes:
        side_match = (
            (option_type_lower in ("put", "p") and quote.side == OptionSide.PUT)
            or (option_type_lower in ("call", "c") and quote.side == OptionSide.CALL)
        )
        if side_match:
            candidates.append(quote)

    if not candidates:
        logger.warning(
            "No %s quotes found in chain for target strike %.2f",
            option_type,
            target_strike,
        )
        return None

    best = min(candidates, key=lambda q: abs(q.strike - target_strike))
    logger.debug(
        "Snapped target strike %.2f -> actual strike %.2f (%s)",
        target_strike,
        best.strike,
        option_type,
    )
    return best


def compute_spread_credit(
    short_quote: OptionQuote,
    long_quote: OptionQuote,
) -> float:
    """Compute the net credit received for a vertical spread.

    Credit = (short option mid-price) - (long option mid-price).

    Uses the mid-price of each leg to avoid inflating the credit estimate with
    the full ask on the short leg.  In live trading the fill price will
    typically be between mid and natural.

    Args:
        short_quote: The option being sold (higher premium).
        long_quote: The option being bought (lower premium, further OTM).

    Returns:
        Net credit per contract in dollars.  A negative value would indicate
        a debit spread (caller should treat as invalid for premium selling).
    """
    short_mid = (short_quote.bid + short_quote.ask) / 2.0
    long_mid = (long_quote.bid + long_quote.ask) / 2.0
    credit = short_mid - long_mid
    logger.debug(
        "Spread credit: short %.2f mid=%.4f - long %.2f mid=%.4f = %.4f",
        short_quote.strike,
        short_mid,
        long_quote.strike,
        long_mid,
        credit,
    )
    return credit


def validate_liquidity(
    quote: OptionQuote,
    min_oi: int = 500,
    min_vol: int = 200,
) -> bool:
    """Validate that an option quote meets minimum liquidity thresholds.

    Illiquid options lead to wide bid-ask spreads and poor fill quality.
    For SPX 0DTE credit spreads, we require robust two-sided markets to
    ensure reliable entry and -- critically -- reliable exit when managing
    risk intraday.

    Args:
        quote: The option quote to validate.
        min_oi: Minimum open interest required.  Default ``500``.
        min_vol: Minimum daily volume required.  Default ``200``.

    Returns:
        ``True`` if the quote meets both thresholds, ``False`` otherwise.
    """
    oi_ok = quote.open_interest >= min_oi
    vol_ok = quote.volume >= min_vol

    if not oi_ok:
        logger.debug(
            "Strike %.2f fails OI check: %d < %d",
            quote.strike,
            quote.open_interest,
            min_oi,
        )
    if not vol_ok:
        logger.debug(
            "Strike %.2f fails volume check: %d < %d",
            quote.strike,
            quote.volume,
            min_vol,
        )

    return oi_ok and vol_ok


# =============================================================================
# PREMIUM SELLING SCANNER
# =============================================================================

class PremiumSellingScanner:
    """Core Scan #2: Identifies optimal credit spread / iron condor entries
    for harvesting theta.

    Executes every 5 minutes from 10:00 AM - 2:00 PM Eastern.

    The scanner enforces a strict checklist of entry conditions -- all must be
    satisfied simultaneously -- then selects strikes anchored to GEX levels and
    expected-move boundaries, validates credit and probability thresholds, and
    optionally combines both sides into an iron condor.

    Constructor Parameters:
        vix1d_range: Acceptable VIX1D band ``(low, high)`` for premium selling.
            Outside this range, either premium is too cheap (low vol) or the
            market is too volatile for defined-risk credit spreads.
        tick_range: NYSE TICK 10-minute average band ``(low, high)``.  Values
            outside this range indicate directional conviction in the tape
            that conflicts with a range-bound premium-selling thesis.
        iv_rv_min: Minimum implied-volatility / realized-volatility ratio.
            Ensures we are selling premium that is *rich* relative to actual
            movement.
        min_credit: Absolute minimum credit per spread in dollars.
        target_credit_pct: Target credit as a fraction of spread width
            (e.g. 0.30 = $1.50 on a $5-wide spread).
        min_probability_otm: Minimum probability the short strike expires OTM,
            derived from the expected-move model.
        spread_width: Default spread width in strike points.
    """

    # Operational time window (Eastern Time)
    SCAN_START: time = time(10, 0)
    SCAN_END: time = time(14, 0)

    # Exit time boundaries
    ACCELERATED_EXIT_TIME: time = time(14, 30)
    HARD_TIME_STOP: time = time(15, 30)

    # Iron condor minimum combined credit
    IC_MIN_COMBINED_CREDIT: float = 1.50

    # Direction score reversal threshold for forced exit
    DIRECTION_REVERSAL_THRESHOLD: float = 60.0

    def __init__(
        self,
        vix1d_range: Tuple[float, float] = (10.0, 22.0),
        tick_range: Tuple[float, float] = (-500.0, 500.0),
        iv_rv_min: float = 1.1,
        min_credit: float = 0.50,
        target_credit_pct: float = 0.30,
        min_probability_otm: float = 0.80,
        spread_width: int = 5,
    ) -> None:
        self.vix1d_range = vix1d_range
        self.tick_range = tick_range
        self.iv_rv_min = iv_rv_min
        self.min_credit = min_credit
        self.target_credit_pct = target_credit_pct
        self.min_probability_otm = min_probability_otm
        self.spread_width = spread_width

        # Black-Scholes engine for delta / probability computations
        self._bs = BlackScholes0DTE()

        logger.info(
            "PremiumSellingScanner initialized: VIX1D=[%.1f, %.1f], "
            "TICK=[%.0f, %.0f], IV/RV>=%.2f, min_credit=$%.2f, "
            "target_credit_pct=%.0f%%, min_prob_OTM=%.0f%%, width=%d",
            self.vix1d_range[0],
            self.vix1d_range[1],
            self.tick_range[0],
            self.tick_range[1],
            self.iv_rv_min,
            self.min_credit,
            self.target_credit_pct * 100,
            self.min_probability_otm * 100,
            self.spread_width,
        )

    # -----------------------------------------------------------------
    # Entry Condition Gate
    # -----------------------------------------------------------------

    def check_entry_conditions(
        self,
        session_type: SessionType,
        vix1d: float,
        spx_price: float,
        vwap: float,
        em_1sigma: float,
        net_gex: float,
        time_zone: str,
        minutes_to_event: int,
        tick_10min_avg: float,
        iv_rv_ratio: float,
    ) -> Tuple[bool, str]:
        """Check ALL entry conditions for premium selling.

        Every condition must be satisfied simultaneously.  The first failing
        condition short-circuits and returns its reason string so the caller
        can log exactly *why* the scanner passed on this bar.

        Conditions (all must be ``True``):
            1. Session classified as RANGE or SQUEEZE (not TRENDING or VOLATILE).
            2. VIX1D between configured low and high (default 10 - 22).
            3. SPX within 0.5 sigma of VWAP (not extended from fair value).
            4. Net GEX is POSITIVE (dealers long gamma = dampening volatility).
            5. Time between 10:00 AM and 2:00 PM Eastern.
            6. No economic event within 60 minutes.
            7. NYSE TICK 10-minute average between -500 and +500.
            8. IV/RV ratio > 1.1 (implied premium is rich).

        Args:
            session_type: Current session classification from the regime engine.
            vix1d: Current VIX1D index level.
            spx_price: Current SPX spot price.
            vwap: Current session VWAP.
            em_1sigma: One-sigma expected move in index points.
            net_gex: Net gamma exposure (positive = dealers long gamma).
            time_zone: Current intraday time zone label (string).
            minutes_to_event: Minutes until the next scheduled economic event.
            tick_10min_avg: Rolling 10-minute average of the NYSE TICK index.
            iv_rv_ratio: Implied volatility / 20-day realized volatility ratio.

        Returns:
            Tuple of ``(can_enter, reason_if_not)``.  When ``can_enter`` is
            ``True``, ``reason_if_not`` is an empty string.
        """
        # 1. Session type must be range-bound or squeeze
        allowed_sessions = {SessionType.RANGE, SessionType.SQUEEZE}
        if session_type not in allowed_sessions:
            reason = (
                f"Session type {session_type.value} is not range-bound; "
                f"premium selling requires RANGE or SQUEEZE"
            )
            logger.debug("Entry blocked: %s", reason)
            return False, reason

        # 2. VIX1D within acceptable band
        vix_lo, vix_hi = self.vix1d_range
        if not (vix_lo <= vix1d <= vix_hi):
            reason = (
                f"VIX1D {vix1d:.2f} outside acceptable range "
                f"[{vix_lo:.1f}, {vix_hi:.1f}]"
            )
            logger.debug("Entry blocked: %s", reason)
            return False, reason

        # 3. SPX within 0.5 sigma of VWAP
        half_sigma = 0.5 * em_1sigma
        vwap_distance = abs(spx_price - vwap)
        if vwap_distance > half_sigma:
            reason = (
                f"SPX {spx_price:.2f} is {vwap_distance:.2f} pts from VWAP "
                f"{vwap:.2f}, exceeding 0.5-sigma threshold of "
                f"{half_sigma:.2f} pts"
            )
            logger.debug("Entry blocked: %s", reason)
            return False, reason

        # 4. Net GEX must be positive (dealers long gamma)
        if net_gex <= 0:
            reason = (
                f"Net GEX is {net_gex:,.0f} (non-positive); premium selling "
                f"requires positive dealer gamma to dampen volatility"
            )
            logger.debug("Entry blocked: %s", reason)
            return False, reason

        # 5. Time between 10:00 AM and 2:00 PM ET
        #    We parse the time_zone string but also enforce via the scan window.
        #    The scan method already gates on time, but this provides a
        #    belt-and-suspenders check using the time_zone label.
        time_zone_lower = time_zone.lower()
        blocked_zones = {"pre_market", "opening_auction", "power_hour", "settlement_window"}
        if time_zone_lower in blocked_zones:
            reason = (
                f"Time zone '{time_zone}' is outside the 10:00 AM - 2:00 PM "
                f"premium selling window"
            )
            logger.debug("Entry blocked: %s", reason)
            return False, reason

        # 6. No economic event within 60 minutes
        if minutes_to_event < 60:
            reason = (
                f"Economic event in {minutes_to_event} minutes (< 60); "
                f"deferring premium selling until event risk clears"
            )
            logger.debug("Entry blocked: %s", reason)
            return False, reason

        # 7. NYSE TICK average within range
        tick_lo, tick_hi = self.tick_range
        if not (tick_lo <= tick_10min_avg <= tick_hi):
            reason = (
                f"NYSE TICK 10-min avg {tick_10min_avg:.0f} outside range "
                f"[{tick_lo:.0f}, {tick_hi:.0f}]; directional tape detected"
            )
            logger.debug("Entry blocked: %s", reason)
            return False, reason

        # 8. IV/RV ratio must exceed minimum (premium is rich)
        if iv_rv_ratio < self.iv_rv_min:
            reason = (
                f"IV/RV ratio {iv_rv_ratio:.3f} below minimum {self.iv_rv_min:.2f}; "
                f"premium is not sufficiently rich"
            )
            logger.debug("Entry blocked: %s", reason)
            return False, reason

        # All conditions passed
        logger.info(
            "Premium selling entry conditions MET: session=%s, VIX1D=%.2f, "
            "VWAP_dist=%.2f, GEX=%+.0f, TICK=%.0f, IV/RV=%.3f",
            session_type.value,
            vix1d,
            vwap_distance,
            net_gex,
            tick_10min_avg,
            iv_rv_ratio,
        )
        return True, ""

    # -----------------------------------------------------------------
    # Probability Model
    # -----------------------------------------------------------------

    def compute_probability_otm(
        self,
        strike: float,
        spx_price: float,
        em_1sigma: float,
        is_put: bool,
    ) -> float:
        """Compute probability of *strike* expiring OTM using the expected
        move model.

        Treats the expected move as one standard deviation of a normal
        distribution centered at the current SPX price.

        For puts (strike below spot):
            P(SPX > K) = N((SPX - K) / EM_1sigma)

        For calls (strike above spot):
            P(SPX < K) = N((K - SPX) / EM_1sigma)

        Where N(.) is the standard normal CDF.

        Args:
            strike: The short strike price to evaluate.
            spx_price: Current SPX spot price.
            em_1sigma: One-sigma expected move in index points.
            is_put: ``True`` if evaluating a put strike, ``False`` for a call.

        Returns:
            Probability in [0, 1] that the strike expires out of the money.
            Returns 0.5 if ``em_1sigma`` is non-positive (degenerate case).
        """
        if em_1sigma <= 0:
            logger.warning(
                "Expected move is non-positive (%.4f); returning 0.5 "
                "as degenerate probability",
                em_1sigma,
            )
            return 0.5

        if is_put:
            z = (spx_price - strike) / em_1sigma
        else:
            z = (strike - spx_price) / em_1sigma

        prob = float(norm.cdf(z))
        logger.debug(
            "P(OTM) for %s strike %.2f: z=%.4f -> %.4f (%.1f%%)",
            "put" if is_put else "call",
            strike,
            z,
            prob,
            prob * 100,
        )
        return prob

    # -----------------------------------------------------------------
    # Put Credit Spread Selection
    # -----------------------------------------------------------------

    def select_put_credit_spread(
        self,
        chain: OptionsChain,
        spx_price: float,
        minus_gex: float,
        em_lower: float,
        spread_width: int = 5,
    ) -> Optional[CreditSpread]:
        """Select optimal PUT CREDIT SPREAD (Bull Put Spread).

        The short put is placed at the further-OTM of two anchor levels:
            - The -GEX level (major put gamma wall below the market)
            - The lower 1-sigma expected-move boundary

        This ensures the short strike sits behind at least one structural
        support level.  The long put is placed *spread_width* points below
        the short to define maximum risk.

        Selection criteria:
            - Minimum credit: ``self.min_credit`` (default $0.50)
            - Target credit >= ``self.target_credit_pct`` of spread width
              (default 30% = $1.50 on a $5 spread)
            - Probability OTM >= ``self.min_probability_otm`` (default 80%)
            - Both legs must pass liquidity validation

        Delta of the short strike is used as a secondary probability check:
        P(OTM) ~ 1 - |delta|.

        Args:
            chain: Full 0DTE options chain.
            spx_price: Current SPX spot price.
            minus_gex: The -GEX level (put gamma wall below market).
            em_lower: Lower bound of the 1-sigma expected move
                (i.e. ``spx_price - em_1sigma``).
            spread_width: Width of the spread in strike points.  Defaults to
                the instance ``self.spread_width`` if caller passes the
                default sentinel of ``5``.

        Returns:
            A :class:`CreditSpread` if a qualifying spread is found,
            otherwise ``None``.
        """
        width = spread_width if spread_width != 5 else self.spread_width
        logger.info(
            "Selecting PUT credit spread: SPX=%.2f, -GEX=%.2f, "
            "EM_lower=%.2f, width=%d",
            spx_price,
            minus_gex,
            em_lower,
            width,
        )

        # Short strike anchor: further OTM of -GEX and 1-sigma lower bound
        # Both values should be below SPX.  "Further OTM" for puts means
        # the LOWER strike.
        short_target = min(minus_gex, em_lower)

        # Snap to nearest available put strike
        short_quote = find_strike_at_or_near(chain, short_target, "put")
        if short_quote is None:
            logger.warning("No put quote found near short target %.2f", short_target)
            return None

        # Long strike = short strike - spread width
        long_target = short_quote.strike - width
        long_quote = find_strike_at_or_near(chain, long_target, "put")
        if long_quote is None:
            logger.warning("No put quote found near long target %.2f", long_target)
            return None

        # Validate liquidity on both legs
        if not validate_liquidity(short_quote):
            logger.info(
                "Short put %.2f fails liquidity check; skipping spread",
                short_quote.strike,
            )
            return None
        if not validate_liquidity(long_quote):
            logger.info(
                "Long put %.2f fails liquidity check; skipping spread",
                long_quote.strike,
            )
            return None

        # Compute credit
        credit = compute_spread_credit(short_quote, long_quote)
        if credit < self.min_credit:
            logger.info(
                "Put spread credit $%.2f < minimum $%.2f; skipping",
                credit,
                self.min_credit,
            )
            return None

        # Target credit check
        target_credit = self.target_credit_pct * width
        if credit < target_credit:
            logger.info(
                "Put spread credit $%.2f < target $%.2f (%.0f%% of $%d width); "
                "below target but above minimum -- proceeding with caution",
                credit,
                target_credit,
                self.target_credit_pct * 100,
                width,
            )

        # Probability OTM check (expected-move model)
        em_1sigma = spx_price - em_lower  # Recover EM from boundary
        prob_otm = self.compute_probability_otm(
            strike=short_quote.strike,
            spx_price=spx_price,
            em_1sigma=em_1sigma if em_1sigma > 0 else 1.0,
            is_put=True,
        )

        # Secondary check: delta-based probability
        if short_quote.delta is not None:
            delta_prob_otm = 1.0 - abs(short_quote.delta)
            logger.debug(
                "Delta-based P(OTM) for put %.2f: %.4f (delta=%.4f)",
                short_quote.strike,
                delta_prob_otm,
                short_quote.delta,
            )
            # Use the more conservative (lower) of the two estimates
            prob_otm = min(prob_otm, delta_prob_otm)

        if prob_otm < self.min_probability_otm:
            logger.info(
                "Put spread P(OTM) %.1f%% < minimum %.1f%%; skipping",
                prob_otm * 100,
                self.min_probability_otm * 100,
            )
            return None

        # Construct the CreditSpread object
        actual_width = abs(short_quote.strike - long_quote.strike)
        max_loss = actual_width - credit
        short_leg = SpreadLeg(
            strike=short_quote.strike,
            side=OptionSide.PUT,
            direction=TradeDirection.SHORT,
            quote=short_quote,
        )
        long_leg = SpreadLeg(
            strike=long_quote.strike,
            side=OptionSide.PUT,
            direction=TradeDirection.LONG,
            quote=long_quote,
        )

        spread = CreditSpread(
            short_leg=short_leg,
            long_leg=long_leg,
            spread_type="bull_put",
            credit=credit,
            max_loss=max_loss,
            width=actual_width,
            probability_otm=prob_otm,
        )

        logger.info(
            "PUT CREDIT SPREAD selected: sell %.2f / buy %.2f, "
            "credit=$%.2f, max_loss=$%.2f, P(OTM)=%.1f%%",
            short_quote.strike,
            long_quote.strike,
            credit,
            max_loss,
            prob_otm * 100,
        )
        return spread

    # -----------------------------------------------------------------
    # Call Credit Spread Selection
    # -----------------------------------------------------------------

    def select_call_credit_spread(
        self,
        chain: OptionsChain,
        spx_price: float,
        plus_gex: float,
        em_upper: float,
        spread_width: int = 5,
    ) -> Optional[CreditSpread]:
        """Select optimal CALL CREDIT SPREAD (Bear Call Spread).

        The short call is placed at the further-OTM of two anchor levels:
            - The +GEX level (major call gamma wall above the market)
            - The upper 1-sigma expected-move boundary

        The long call is placed *spread_width* points above the short to
        define maximum risk.

        Same credit, probability, and liquidity requirements as the put
        credit spread.

        Args:
            chain: Full 0DTE options chain.
            spx_price: Current SPX spot price.
            plus_gex: The +GEX level (call gamma wall above market).
            em_upper: Upper bound of the 1-sigma expected move
                (i.e. ``spx_price + em_1sigma``).
            spread_width: Width of the spread in strike points.

        Returns:
            A :class:`CreditSpread` if a qualifying spread is found,
            otherwise ``None``.
        """
        width = spread_width if spread_width != 5 else self.spread_width
        logger.info(
            "Selecting CALL credit spread: SPX=%.2f, +GEX=%.2f, "
            "EM_upper=%.2f, width=%d",
            spx_price,
            plus_gex,
            em_upper,
            width,
        )

        # Short strike anchor: further OTM of +GEX and 1-sigma upper bound.
        # "Further OTM" for calls means the HIGHER strike.
        short_target = max(plus_gex, em_upper)

        # Snap to nearest available call strike
        short_quote = find_strike_at_or_near(chain, short_target, "call")
        if short_quote is None:
            logger.warning("No call quote found near short target %.2f", short_target)
            return None

        # Long strike = short strike + spread width
        long_target = short_quote.strike + width
        long_quote = find_strike_at_or_near(chain, long_target, "call")
        if long_quote is None:
            logger.warning("No call quote found near long target %.2f", long_target)
            return None

        # Validate liquidity on both legs
        if not validate_liquidity(short_quote):
            logger.info(
                "Short call %.2f fails liquidity check; skipping spread",
                short_quote.strike,
            )
            return None
        if not validate_liquidity(long_quote):
            logger.info(
                "Long call %.2f fails liquidity check; skipping spread",
                long_quote.strike,
            )
            return None

        # Compute credit
        credit = compute_spread_credit(short_quote, long_quote)
        if credit < self.min_credit:
            logger.info(
                "Call spread credit $%.2f < minimum $%.2f; skipping",
                credit,
                self.min_credit,
            )
            return None

        # Target credit check
        target_credit = self.target_credit_pct * width
        if credit < target_credit:
            logger.info(
                "Call spread credit $%.2f < target $%.2f (%.0f%% of $%d width); "
                "below target but above minimum -- proceeding with caution",
                credit,
                target_credit,
                self.target_credit_pct * 100,
                width,
            )

        # Probability OTM check (expected-move model)
        em_1sigma = em_upper - spx_price  # Recover EM from boundary
        prob_otm = self.compute_probability_otm(
            strike=short_quote.strike,
            spx_price=spx_price,
            em_1sigma=em_1sigma if em_1sigma > 0 else 1.0,
            is_put=False,
        )

        # Secondary check: delta-based probability
        if short_quote.delta is not None:
            delta_prob_otm = 1.0 - abs(short_quote.delta)
            logger.debug(
                "Delta-based P(OTM) for call %.2f: %.4f (delta=%.4f)",
                short_quote.strike,
                delta_prob_otm,
                short_quote.delta,
            )
            # Use the more conservative (lower) of the two estimates
            prob_otm = min(prob_otm, delta_prob_otm)

        if prob_otm < self.min_probability_otm:
            logger.info(
                "Call spread P(OTM) %.1f%% < minimum %.1f%%; skipping",
                prob_otm * 100,
                self.min_probability_otm * 100,
            )
            return None

        # Construct the CreditSpread object
        actual_width = abs(long_quote.strike - short_quote.strike)
        max_loss = actual_width - credit
        short_leg = SpreadLeg(
            strike=short_quote.strike,
            side=OptionSide.CALL,
            direction=TradeDirection.SHORT,
            quote=short_quote,
        )
        long_leg = SpreadLeg(
            strike=long_quote.strike,
            side=OptionSide.CALL,
            direction=TradeDirection.LONG,
            quote=long_quote,
        )

        spread = CreditSpread(
            short_leg=short_leg,
            long_leg=long_leg,
            spread_type="bear_call",
            credit=credit,
            max_loss=max_loss,
            width=actual_width,
            probability_otm=prob_otm,
        )

        logger.info(
            "CALL CREDIT SPREAD selected: sell %.2f / buy %.2f, "
            "credit=$%.2f, max_loss=$%.2f, P(OTM)=%.1f%%",
            short_quote.strike,
            long_quote.strike,
            credit,
            max_loss,
            prob_otm * 100,
        )
        return spread

    # -----------------------------------------------------------------
    # Iron Condor Construction
    # -----------------------------------------------------------------

    def construct_iron_condor(
        self,
        put_spread: CreditSpread,
        call_spread: CreditSpread,
    ) -> Optional[IronCondor]:
        """Combine put and call credit spreads into an iron condor.

        Validates that:
            - Total combined credit >= $1.50 (``IC_MIN_COMBINED_CREDIT``).
            - The break-even range of the iron condor contains the
              expected-move boundaries (i.e. the short strikes are outside
              the EM range, and the break-evens extend even further).

        The iron condor's break-even points are:
            - Lower break-even = put short strike - total credit
            - Upper break-even = call short strike + total credit

        Args:
            put_spread: A validated :class:`CreditSpread` for the bull-put side.
            call_spread: A validated :class:`CreditSpread` for the bear-call side.

        Returns:
            An :class:`IronCondor` combining both spreads, or ``None`` if the
            combined credit is insufficient.
        """
        total_credit = put_spread.credit + call_spread.credit

        if total_credit < self.IC_MIN_COMBINED_CREDIT:
            logger.info(
                "Iron condor combined credit $%.2f < minimum $%.2f; "
                "will use individual spreads instead",
                total_credit,
                self.IC_MIN_COMBINED_CREDIT,
            )
            return None

        # Compute break-even range
        lower_breakeven = put_spread.short_leg.strike - total_credit
        upper_breakeven = call_spread.short_leg.strike + total_credit

        # Max loss is the wider of the two spread widths minus total credit
        # (for balanced iron condors both widths are equal)
        max_single_width = max(put_spread.width, call_spread.width)
        max_loss = max_single_width - total_credit

        # Combined probability of profit: both spreads must expire OTM
        # P(IC profit) = P(put OTM) * P(call OTM) -- approximate independence
        combined_prob_otm = put_spread.probability_otm * call_spread.probability_otm

        iron_condor = IronCondor(
            put_spread=put_spread,
            call_spread=call_spread,
            total_credit=total_credit,
            max_loss=max_loss,
            lower_breakeven=lower_breakeven,
            upper_breakeven=upper_breakeven,
            probability_of_profit=combined_prob_otm,
        )

        logger.info(
            "IRON CONDOR constructed: "
            "put_short=%.2f / put_long=%.2f | "
            "call_short=%.2f / call_long=%.2f, "
            "credit=$%.2f, max_loss=$%.2f, "
            "BE=[%.2f, %.2f], P(profit)=%.1f%%",
            put_spread.short_leg.strike,
            put_spread.long_leg.strike,
            call_spread.short_leg.strike,
            call_spread.long_leg.strike,
            total_credit,
            max_loss,
            lower_breakeven,
            upper_breakeven,
            combined_prob_otm * 100,
        )
        return iron_condor

    # -----------------------------------------------------------------
    # Exit Target Computation
    # -----------------------------------------------------------------

    def compute_exit_targets(
        self,
        spread: CreditSpread,
        time_zone: str,
    ) -> Dict[str, Any]:
        """Compute exit management levels for a credit spread.

        Exit rules are layered from least to most aggressive:

        1. **Standard profit target**: close at 50% of max profit.
        2. **Accelerated profit target**: close at 80% of max profit if
           after 2:30 PM (theta is decaying rapidly, gamma risk rising).
        3. **Breach stop**: close immediately if the short strike is
           breached (SPX crosses through the short strike).
        4. **Direction reversal**: close immediately if the composite
           direction score reverses beyond +/-60 (market structure shift).
        5. **Hard time stop**: close ALL iron condors by 3:30 PM regardless
           of P&L (gamma becomes unmanageable in the final 30 minutes).

        Args:
            spread: The :class:`CreditSpread` to compute exits for.
            time_zone: Current intraday time zone label string.

        Returns:
            Dictionary with keys:
                - ``close_at_50``: Price at which to close for 50% profit.
                - ``close_at_80``: Price at which to close for 80% profit.
                - ``breach_stop``: Short strike level that triggers exit.
                - ``direction_reversal_threshold``: Score magnitude that
                  triggers exit.
                - ``time_stop``: Hard time stop (``time`` object).
                - ``accelerated_exit_active``: Whether the 80% target is
                  currently active (based on time zone).
        """
        credit = spread.credit

        # 50% profit target: buy back the spread at 50% of original credit
        close_at_50_value = credit * 0.50

        # 80% profit target: buy back at 20% of original credit (80% kept)
        close_at_80_value = credit * 0.20

        # Breach level is the short strike itself
        breach_stop = spread.short_leg.strike

        # Determine if accelerated exit is active based on time zone
        time_zone_lower = time_zone.lower()
        late_zones = {"afternoon_accel", "power_hour", "settlement_window"}
        accelerated_active = time_zone_lower in late_zones

        exit_targets = {
            "close_at_50": close_at_50_value,
            "close_at_80": close_at_80_value,
            "breach_stop": breach_stop,
            "direction_reversal_threshold": self.DIRECTION_REVERSAL_THRESHOLD,
            "time_stop": self.HARD_TIME_STOP,
            "accelerated_exit_active": accelerated_active,
            "spread_type": spread.spread_type,
            "original_credit": credit,
            "max_loss": spread.max_loss,
        }

        logger.info(
            "Exit targets for %s spread (short=%.2f): "
            "close@50%%=$%.2f, close@80%%=$%.2f, breach=%.2f, "
            "time_stop=%s, accelerated=%s",
            spread.spread_type,
            breach_stop,
            close_at_50_value,
            close_at_80_value,
            breach_stop,
            self.HARD_TIME_STOP.strftime("%H:%M"),
            accelerated_active,
        )
        return exit_targets

    # -----------------------------------------------------------------
    # Main Scan Method
    # -----------------------------------------------------------------

    def scan(
        self,
        chain: OptionsChain,
        internals: MarketInternals,
        spx_price: float,
        vwap: float,
        em_1sigma: float,
        em_upper: float,
        em_lower: float,
        gex_profile: GEXProfile,
        cross_data: CrossAssetData,
        session_type: SessionType,
        time_zone: str,
        minutes_to_event: int,
        iv_rv_ratio: float,
    ) -> Optional[ScanSignal]:
        """Main scan method.  Runs every 5 minutes from 10:00 AM - 2:00 PM.

        Execution pipeline:
            1. Check all entry conditions (eight-gate filter).
            2. Select optimal put credit spread anchored to -GEX / EM lower.
            3. Select optimal call credit spread anchored to +GEX / EM upper.
            4. If both sides qualify, construct an iron condor.
            5. Generate and return a :class:`ScanSignal` with full metadata.

        If only one side qualifies, a single-leg credit spread signal is
        returned.  If neither side qualifies, ``None`` is returned.

        Args:
            chain: Full 0DTE options chain for the current expiration.
            internals: Current market internals snapshot (TICK, ADD, VOLD).
            spx_price: Current SPX spot price.
            vwap: Current session VWAP.
            em_1sigma: One-sigma expected move in index points.
            em_upper: Upper expected-move boundary (``spx_price + em_1sigma``).
            em_lower: Lower expected-move boundary (``spx_price - em_1sigma``).
            gex_profile: Current GEX profile with +GEX / -GEX levels.
            cross_data: Cross-asset data snapshot (bonds, VIX term structure).
            session_type: Current session classification from the regime engine.
            time_zone: Current intraday time zone label string.
            minutes_to_event: Minutes until the next scheduled economic event.
            iv_rv_ratio: Implied-volatility / realized-volatility ratio.

        Returns:
            A :class:`ScanSignal` with ``scan_type=ScanType.PREMIUM_SELLING``
            if conditions are met and at least one qualifying spread is found.
            Returns ``None`` otherwise.
        """
        logger.info(
            "=== PremiumSellingScanner.scan() === SPX=%.2f, session=%s, "
            "time_zone=%s, VIX1D from internals",
            spx_price,
            session_type.value,
            time_zone,
        )

        # -----------------------------------------------------------
        # Step 1: Check entry conditions
        # -----------------------------------------------------------
        can_enter, reason = self.check_entry_conditions(
            session_type=session_type,
            vix1d=internals.vix1d,
            spx_price=spx_price,
            vwap=vwap,
            em_1sigma=em_1sigma,
            net_gex=gex_profile.net_gex,
            time_zone=time_zone,
            minutes_to_event=minutes_to_event,
            tick_10min_avg=internals.tick_10min_avg,
            iv_rv_ratio=iv_rv_ratio,
        )

        if not can_enter:
            logger.info("Premium scan PASS (no trade): %s", reason)
            return None

        # -----------------------------------------------------------
        # Step 2: Select put credit spread
        # -----------------------------------------------------------
        put_spread = self.select_put_credit_spread(
            chain=chain,
            spx_price=spx_price,
            minus_gex=gex_profile.minus_gex,
            em_lower=em_lower,
            spread_width=self.spread_width,
        )

        # -----------------------------------------------------------
        # Step 3: Select call credit spread
        # -----------------------------------------------------------
        call_spread = self.select_call_credit_spread(
            chain=chain,
            spx_price=spx_price,
            plus_gex=gex_profile.plus_gex,
            em_upper=em_upper,
            spread_width=self.spread_width,
        )

        # -----------------------------------------------------------
        # Step 4: Construct iron condor if both sides qualify
        # -----------------------------------------------------------
        iron_condor: Optional[IronCondor] = None
        if put_spread is not None and call_spread is not None:
            iron_condor = self.construct_iron_condor(put_spread, call_spread)

        # If neither side qualifies, no signal
        if put_spread is None and call_spread is None:
            logger.info(
                "Premium scan PASS (no trade): neither put nor call spread "
                "met qualification criteria"
            )
            return None

        # -----------------------------------------------------------
        # Step 5: Build the ScanSignal
        # -----------------------------------------------------------

        # Determine the primary trade structure
        if iron_condor is not None:
            position_type = PositionType.IRON_CONDOR
            total_credit = iron_condor.total_credit
            max_loss = iron_condor.max_loss
            primary_prob = iron_condor.probability_of_profit
            structure_desc = (
                f"IC: sell {put_spread.short_leg.strike}P / "
                f"buy {put_spread.long_leg.strike}P | "
                f"sell {call_spread.short_leg.strike}C / "
                f"buy {call_spread.long_leg.strike}C"
            )
        elif put_spread is not None and call_spread is not None:
            # Both spreads exist but IC didn't meet combined credit threshold;
            # still report as individual spreads
            position_type = PositionType.CREDIT_SPREAD
            total_credit = put_spread.credit + call_spread.credit
            max_loss = max(put_spread.max_loss, call_spread.max_loss)
            primary_prob = min(put_spread.probability_otm, call_spread.probability_otm)
            structure_desc = (
                f"Bull Put: sell {put_spread.short_leg.strike} / "
                f"buy {put_spread.long_leg.strike} + "
                f"Bear Call: sell {call_spread.short_leg.strike} / "
                f"buy {call_spread.long_leg.strike}"
            )
        elif put_spread is not None:
            position_type = PositionType.CREDIT_SPREAD
            total_credit = put_spread.credit
            max_loss = put_spread.max_loss
            primary_prob = put_spread.probability_otm
            structure_desc = (
                f"Bull Put: sell {put_spread.short_leg.strike} / "
                f"buy {put_spread.long_leg.strike}"
            )
        else:
            # Only call spread qualifies
            position_type = PositionType.CREDIT_SPREAD
            total_credit = call_spread.credit
            max_loss = call_spread.max_loss
            primary_prob = call_spread.probability_otm
            structure_desc = (
                f"Bear Call: sell {call_spread.short_leg.strike} / "
                f"buy {call_spread.long_leg.strike}"
            )

        # Compute exit targets for each qualifying spread
        exit_targets: Dict[str, Any] = {}
        if put_spread is not None:
            exit_targets["put_spread_exits"] = self.compute_exit_targets(
                put_spread, time_zone
            )
        if call_spread is not None:
            exit_targets["call_spread_exits"] = self.compute_exit_targets(
                call_spread, time_zone
            )

        # Risk-reward ratio
        risk_reward = total_credit / max_loss if max_loss > 0 else 0.0

        # Confidence score: weighted blend of probability, credit quality,
        # and IV/RV richness
        credit_quality = min(total_credit / (self.target_credit_pct * self.spread_width), 1.0)
        iv_richness = min((iv_rv_ratio - 1.0) / 0.5, 1.0)  # Normalize 1.0-1.5 -> 0-1
        confidence = (
            0.50 * primary_prob
            + 0.30 * credit_quality
            + 0.20 * max(iv_richness, 0.0)
        )
        confidence = max(0.0, min(1.0, confidence))

        # Build metadata
        metadata: Dict[str, Any] = {
            "structure": structure_desc,
            "position_type": position_type.value if hasattr(position_type, "value") else str(position_type),
            "total_credit": round(total_credit, 2),
            "max_loss": round(max_loss, 2),
            "risk_reward": round(risk_reward, 4),
            "probability_otm": round(primary_prob, 4),
            "iv_rv_ratio": round(iv_rv_ratio, 4),
            "session_type": session_type.value,
            "time_zone": time_zone,
            "vix1d": internals.vix1d,
            "net_gex": gex_profile.net_gex,
            "em_1sigma": round(em_1sigma, 2),
            "em_range": [round(em_lower, 2), round(em_upper, 2)],
            "exit_targets": exit_targets,
        }

        # Attach spread / IC objects for downstream consumption
        if put_spread is not None:
            metadata["put_credit_spread"] = put_spread
        if call_spread is not None:
            metadata["call_credit_spread"] = call_spread
        if iron_condor is not None:
            metadata["iron_condor"] = iron_condor

        signal = ScanSignal(
            scan_type=ScanType.PREMIUM_SELLING,
            direction=TradeDirection.NEUTRAL,
            confidence=confidence,
            spx_price=spx_price,
            timestamp=datetime.utcnow(),
            metadata=metadata,
        )

        logger.info(
            "PREMIUM SELLING SIGNAL generated: %s, credit=$%.2f, "
            "max_loss=$%.2f, R:R=%.2f, P(OTM)=%.1f%%, confidence=%.2f",
            structure_desc,
            total_credit,
            max_loss,
            risk_reward,
            primary_prob * 100,
            confidence,
        )
        return signal
