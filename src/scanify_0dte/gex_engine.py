"""
SCANIFY SPX 0DTE Scanner -- Gamma Exposure (GEX) Calculation Engine
====================================================================

Core analytical engine that computes dealer gamma exposure across all strikes
and derives key structural levels (gamma flip, call/put walls, transition
zones, charm flow, vanna exposure).

The engine implements three dealer-positioning models:

* **Simple (OI-based)** -- classical Cboe-validated assumption that customers
  are net buyers of puts and net sellers of calls.
* **Flow-based** -- tracks real-time trade direction to adjust dealer position
  estimates intraday.
* **Hybrid (default)** -- blends OI-based and flow-based models (60/40).

Refresh cadence: every 60 seconds on the full options chain.

Depends on
----------
- ``greeks_engine``  : BlackScholes0DTE, GreeksCalculator, annualized_time,
                       normal_pdf
- ``models``         : StrikeGEX, GEXProfile, GEXSignal, GEXSignalType,
                       OptionQuote, OptionsChain, OptionSide

References
----------
- Cboe GEX White Paper (2022)
- SqueezeMetrics Gamma Exposure methodology
- Volland (2019), *Dealer Gamma Positioning in Index Options Markets*
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np

from .greeks_engine import (
    BlackScholes0DTE,
    GreeksCalculator,
    annualized_time,
    normal_pdf,
)
from .models import (
    GEXProfile,
    GEXSignal,
    GEXSignalType,
    OptionQuote,
    OptionsChain,
    OptionSide,
    StrikeGEX,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_CONTRACT_MULTIPLIER: int = 100  # SPX option contract multiplier
_ES_MULTIPLIER: float = 50.0    # E-mini S&P 500 futures point value

_EPSILON: float = 1e-12  # Guard against division by zero
_MAX_GAMMA_CAP: float = 5.0  # Cap extreme near-expiry gamma values
_MAX_SPEED_CAP: float = 1.0  # Cap extreme near-expiry speed (dGamma/dSpot) values
_MIN_MINUTES_FOR_GREEKS: int = 1  # Floor for time input


def _safe_divide(numerator: float, denominator: float) -> float:
    """Return *numerator / denominator*, or 0.0 when *denominator* ~ 0."""
    if abs(denominator) < _EPSILON:
        return 0.0
    return numerator / denominator


def _clamp_gamma(raw_gamma: float) -> float:
    """Clamp gamma to a sane range for 0DTE (avoids blow-up near expiry)."""
    return max(-_MAX_GAMMA_CAP, min(_MAX_GAMMA_CAP, raw_gamma))


def _clamp_speed(raw_speed: float) -> float:
    """Clamp speed (dGamma/dSpot) to a sane range for 0DTE.

    Speed is the third-order Greek and blows up even more violently than
    gamma near expiry.  Without clamping, extreme values propagate into
    net_speed on StrikeGEX and corrupt downstream GEX profile analysis.
    """
    return max(-_MAX_SPEED_CAP, min(_MAX_SPEED_CAP, raw_speed))


# =========================================================================
# 1. GEXEngine -- core computation
# =========================================================================

class GEXEngine:
    """Core GEX computation engine.  Must run every 60 seconds on full chain.

    Parameters
    ----------
    bs_calculator : BlackScholes0DTE
        Pre-configured Black-Scholes calculator tuned for 0DTE options.
    dealer_model : str
        One of ``"simple"``, ``"flow"``, or ``"hybrid"`` (default).
    oi_weight : float
        Weight assigned to the OI-based model when *dealer_model* is
        ``"hybrid"`` (default 0.6).
    flow_weight : float
        Weight assigned to the flow-based model when *dealer_model* is
        ``"hybrid"`` (default 0.4).
    """

    # Supported model identifiers
    _VALID_MODELS = frozenset({"simple", "flow", "hybrid"})

    def __init__(
        self,
        bs_calculator: BlackScholes0DTE,
        dealer_model: str = "hybrid",
        oi_weight: float = 0.6,
        flow_weight: float = 0.4,
    ) -> None:
        if dealer_model not in self._VALID_MODELS:
            raise ValueError(
                f"dealer_model must be one of {self._VALID_MODELS}, "
                f"got {dealer_model!r}"
            )
        if not math.isclose(oi_weight + flow_weight, 1.0, abs_tol=1e-6):
            raise ValueError(
                f"oi_weight ({oi_weight}) + flow_weight ({flow_weight}) "
                f"must sum to 1.0"
            )

        self.bs_calculator: BlackScholes0DTE = bs_calculator
        self.dealer_model: str = dealer_model
        self.oi_weight: float = oi_weight
        self.flow_weight: float = flow_weight

        # Cumulative intraday flow tracking: strike -> net dealer gamma adjustment.
        # Positive means dealers have accumulated long gamma at that strike.
        self.cumulative_flow: Dict[float, float] = defaultdict(float)

    # ------------------------------------------------------------------
    # a) Single-strike GEX
    # ------------------------------------------------------------------

    def compute_strike_gex(
        self,
        spot: float,
        strike: float,
        call_iv: float,
        put_iv: float,
        call_oi: int,
        put_oi: int,
        call_volume: int,
        put_volume: int,
        minutes_remaining: int,
        r: float,
        q: float,
        call_flow_direction: float = 0.0,
        put_flow_direction: float = 0.0,
    ) -> StrikeGEX:
        """Compute GEX for a single strike using the configured dealer model.

        Dealer Position Assumption (standard for index options, validated by
        Cboe):

        * Customers are net **buyers** of puts (hedging) -- dealers are
          **short** puts -- dealers have **positive** gamma from puts.
        * Customers are net **sellers** of calls (overwriting) -- dealers
          are **long** calls -- dealers have **negative** gamma from calls.

        Simple model (OI-based)::

            Dealer_Gamma_Call(K) = -1 * Gamma(K) * OI_call * 100 * S
            Dealer_Gamma_Put(K)  = +1 * Gamma(K) * OI_put  * 100 * S
            Net_GEX(K) = Dealer_Gamma_Call(K) + Dealer_Gamma_Put(K)

        Enhanced model (flow-based)::

            Adjusts dealer position sign using tracked trade direction.

        Hybrid model (recommended)::

            60 % OI-based + 40 % flow-adjusted.

        Parameters
        ----------
        spot : float
            Current SPX price.
        strike : float
            Strike price.
        call_iv, put_iv : float
            Implied volatility (annualised, as decimal e.g. 0.18).
        call_oi, put_oi : int
            Open interest for calls and puts at this strike.
        call_volume, put_volume : int
            Intraday volume for calls and puts.
        minutes_remaining : int
            Minutes until settlement.
        r : float
            Risk-free rate (annualised).
        q : float
            Continuous dividend yield (annualised).
        call_flow_direction : float
            Net customer flow direction for calls at this strike.
            Positive = net customer buying; negative = net selling.
        put_flow_direction : float
            Net customer flow direction for puts at this strike.

        Returns
        -------
        StrikeGEX
        """
        # Floor minutes to avoid singularities
        minutes_remaining = max(minutes_remaining, _MIN_MINUTES_FOR_GREEKS)
        t = annualized_time(minutes_remaining)

        # Use average IV for gamma (gamma is nearly identical for C/P by
        # put-call parity), but keep separate IVs for charm/vanna.
        avg_iv = 0.5 * (call_iv + put_iv) if (call_iv > 0 and put_iv > 0) else max(call_iv, put_iv, 0.01)

        # Raw gamma (same for call and put in BS)
        raw_gamma = self.bs_calculator.gamma(spot, strike, t, avg_iv, r, q)
        gamma = _clamp_gamma(raw_gamma)

        # ---- Simple (OI-based) model ----
        # Convention: dollar gamma per 1-point move in underlying
        simple_call_gex = -1.0 * gamma * call_oi * _CONTRACT_MULTIPLIER * spot
        simple_put_gex = +1.0 * gamma * put_oi * _CONTRACT_MULTIPLIER * spot

        # ---- Flow-based model ----
        # Flow direction encodes net customer buying (+) or selling (-).
        # Customer buy call  -> dealer short call gamma -> negative gamma
        # Customer sell call -> dealer long  call gamma -> positive gamma
        # Customer buy put   -> dealer short put gamma  -> negative gamma (but
        #   puts have inverted sign in hedging, so net = positive for dealer)
        # We scale the flow direction into a [-1, +1] sign multiplier.
        flow_call_sign = -1.0  # Default: customers sell calls
        flow_put_sign = +1.0   # Default: customers buy puts

        if abs(call_flow_direction) > _EPSILON:
            # Positive flow_direction means customers buying -> dealer short -> negative gamma
            flow_call_sign = -np.sign(call_flow_direction)
        if abs(put_flow_direction) > _EPSILON:
            # Positive flow_direction means customers buying puts -> dealer short puts
            # Dealer short puts = positive gamma for dealer (they hedge by buying)
            flow_put_sign = np.sign(put_flow_direction)

        # Include cumulative flow adjustment from update_flow_model()
        cumulative_adj = self.cumulative_flow.get(strike, 0.0)

        flow_call_gex = flow_call_sign * gamma * call_oi * _CONTRACT_MULTIPLIER * spot
        flow_put_gex = flow_put_sign * gamma * put_oi * _CONTRACT_MULTIPLIER * spot
        flow_net = flow_call_gex + flow_put_gex + cumulative_adj

        # ---- Select model ----
        if self.dealer_model == "simple":
            call_gex = simple_call_gex
            put_gex = simple_put_gex
        elif self.dealer_model == "flow":
            call_gex = flow_call_gex
            put_gex = flow_put_gex
        else:
            # Hybrid: blend
            call_gex = self.oi_weight * simple_call_gex + self.flow_weight * flow_call_gex
            put_gex = self.oi_weight * simple_put_gex + self.flow_weight * flow_put_gex

        net_gex = call_gex + put_gex
        if self.dealer_model == "hybrid":
            net_gex += self.flow_weight * cumulative_adj
        elif self.dealer_model == "flow":
            net_gex += cumulative_adj

        # ---- Higher-order dealer Greeks ----
        # Charm (dDelta/dTime) -- calls and puts have different charm
        call_charm = self.bs_calculator.charm(spot, strike, t, call_iv, r, q, "call") if call_iv > 0 else 0.0
        put_charm = self.bs_calculator.charm(spot, strike, t, put_iv, r, q, "put") if put_iv > 0 else 0.0

        # Net charm: dealer position mirrors customer position
        net_charm = (
            -1.0 * call_charm * call_oi * _CONTRACT_MULTIPLIER
            + 1.0 * put_charm * put_oi * _CONTRACT_MULTIPLIER
        )

        # Vanna (dDelta/dVol) -- same magnitude for C/P, sign differs by convention
        call_vanna = self.bs_calculator.vanna(spot, strike, t, call_iv, r, q) if call_iv > 0 else 0.0
        put_vanna = self.bs_calculator.vanna(spot, strike, t, put_iv, r, q) if put_iv > 0 else 0.0

        net_vanna = (
            -1.0 * call_vanna * call_oi * _CONTRACT_MULTIPLIER
            + 1.0 * put_vanna * put_oi * _CONTRACT_MULTIPLIER
        )

        # Speed (dGamma/dSpot)
        raw_speed = self.bs_calculator.speed(spot, strike, t, avg_iv, r, q)
        speed = _clamp_speed(raw_speed)
        net_speed = (
            -1.0 * speed * call_oi * _CONTRACT_MULTIPLIER * spot
            + 1.0 * speed * put_oi * _CONTRACT_MULTIPLIER * spot
        )

        return StrikeGEX(
            strike=strike,
            call_gex=call_gex,
            put_gex=put_gex,
            net_gex=net_gex,
            call_oi=call_oi,
            put_oi=put_oi,
            call_volume=call_volume,
            put_volume=put_volume,
            call_iv=call_iv,
            put_iv=put_iv,
            gamma=gamma,
            net_charm=net_charm,
            net_vanna=net_vanna,
            net_speed=net_speed,
        )

    # ------------------------------------------------------------------
    # b) Full GEX profile
    # ------------------------------------------------------------------

    def compute_full_gex_profile(
        self,
        chain: OptionsChain,
        minutes_remaining: int,
        r: float = 0.05,
        q: float = 0.015,
    ) -> GEXProfile:
        """Compute the complete GEX profile across all strikes.

        Parameters
        ----------
        chain : OptionsChain
            Full options chain (calls + puts).
        minutes_remaining : int
            Minutes until settlement.
        r : float
            Risk-free rate.
        q : float
            Continuous dividend yield.

        Returns
        -------
        GEXProfile
            Profile with all strike-level GEX objects and derived levels:
            total_net_gex, gamma_flip_level, call_wall, put_wall, max_pain,
            plus_gex, minus_gex, transition_zone_upper/lower, vol_trigger,
            charm_net_es_contracts, vanna_net_exposure.
        """
        spot = chain.spot

        if not chain.quotes:
            logger.warning("Empty options chain -- returning default GEXProfile")
            return GEXProfile(
                strikes_gex=[],
                total_net_gex=0.0,
                gamma_flip_level=spot,
                call_wall=spot,
                put_wall=spot,
                max_pain=spot,
                plus_gex=spot,
                minus_gex=spot,
                transition_zone_upper=spot,
                transition_zone_lower=spot,
                vol_trigger=spot,
                charm_net_es_contracts=0.0,
                vanna_net_exposure=0.0,
                timestamp=datetime.now(timezone.utc),
            )

        # Group quotes by strike
        strike_map: Dict[float, Dict[str, OptionQuote]] = defaultdict(dict)
        for quote in chain.quotes:
            side_key = "call" if quote.option_type == OptionSide.CALL else "put"
            strike_map[quote.strike][side_key] = quote

        # Compute per-strike GEX
        strikes_gex: List[StrikeGEX] = []
        for strike in sorted(strike_map.keys()):
            data = strike_map[strike]
            cq: Optional[OptionQuote] = data.get("call")
            pq: Optional[OptionQuote] = data.get("put")

            call_iv = cq.implied_vol if cq is not None else 0.0
            put_iv = pq.implied_vol if pq is not None else 0.0
            call_oi = cq.open_interest if cq is not None else 0
            put_oi = pq.open_interest if pq is not None else 0
            call_vol = cq.volume if cq is not None else 0
            put_vol = pq.volume if pq is not None else 0

            call_flow = getattr(cq, "flow_direction", 0.0) if cq is not None else 0.0
            put_flow = getattr(pq, "flow_direction", 0.0) if pq is not None else 0.0

            # Skip strikes with zero OI on both sides (no dealer exposure)
            if call_oi == 0 and put_oi == 0:
                continue

            sg = self.compute_strike_gex(
                spot=spot,
                strike=strike,
                call_iv=call_iv,
                put_iv=put_iv,
                call_oi=call_oi,
                put_oi=put_oi,
                call_volume=call_vol,
                put_volume=put_vol,
                minutes_remaining=minutes_remaining,
                r=r,
                q=q,
                call_flow_direction=call_flow,
                put_flow_direction=put_flow,
            )
            strikes_gex.append(sg)

        if not strikes_gex:
            logger.warning("No strikes with OI found -- returning default GEXProfile")
            return GEXProfile(
                strikes_gex=[],
                total_net_gex=0.0,
                gamma_flip_level=spot,
                call_wall=spot,
                put_wall=spot,
                max_pain=spot,
                plus_gex=spot,
                minus_gex=spot,
                transition_zone_upper=spot,
                transition_zone_lower=spot,
                vol_trigger=spot,
                charm_net_es_contracts=0.0,
                vanna_net_exposure=0.0,
                timestamp=datetime.now(timezone.utc),
            )

        # --- Derived levels ---
        total_net_gex = sum(sg.net_gex for sg in strikes_gex)

        # Gamma flip
        gamma_flip_level = self.find_gamma_flip(strikes_gex, spot)

        # Call wall: strike with highest call OI
        call_wall = max(strikes_gex, key=lambda sg: sg.call_oi).strike

        # Put wall: strike with highest put OI
        put_wall = max(strikes_gex, key=lambda sg: sg.put_oi).strike

        # Max pain
        max_pain = self.find_max_pain(chain)

        # +GEX: strike with maximum positive (most positive) net GEX
        plus_gex = max(strikes_gex, key=lambda sg: sg.net_gex).strike

        # -GEX: strike with maximum negative (most negative) net GEX
        minus_gex = min(strikes_gex, key=lambda sg: sg.net_gex).strike

        # Transition zone
        tz_lower, tz_upper = self.compute_transition_zone(strikes_gex, spot)

        # Vol trigger: strike where gamma * OI * IV peaks
        def _vol_trigger_score(sg: StrikeGEX) -> float:
            total_oi = sg.call_oi + sg.put_oi
            avg_iv = 0.5 * (sg.call_iv + sg.put_iv) if sg.call_iv > 0 and sg.put_iv > 0 else max(sg.call_iv, sg.put_iv)
            return abs(sg.gamma) * total_oi * avg_iv

        vol_trigger = max(strikes_gex, key=_vol_trigger_score).strike

        # Charm: net ES contract equivalents
        charm_es = self.compute_charm_flow(strikes_gex, spot)

        # Vanna: total net exposure
        vanna_net = sum(sg.net_vanna for sg in strikes_gex)

        return GEXProfile(
            strikes_gex=strikes_gex,
            total_net_gex=total_net_gex,
            gamma_flip_level=gamma_flip_level,
            call_wall=call_wall,
            put_wall=put_wall,
            max_pain=max_pain,
            plus_gex=plus_gex,
            minus_gex=minus_gex,
            transition_zone_upper=tz_upper,
            transition_zone_lower=tz_lower,
            vol_trigger=vol_trigger,
            charm_net_es_contracts=charm_es,
            vanna_net_exposure=vanna_net,
            timestamp=datetime.now(timezone.utc),
        )

    # ------------------------------------------------------------------
    # c) Gamma flip
    # ------------------------------------------------------------------

    def find_gamma_flip(
        self,
        strikes_gex: List[StrikeGEX],
        spot: float,
    ) -> float:
        """Find the price level where cumulative GEX changes sign.

        The method sorts strikes by price, walks the cumulative GEX curve,
        and uses linear interpolation between the two strikes that straddle
        the zero-crossing closest to *spot*.

        Parameters
        ----------
        strikes_gex : list[StrikeGEX]
            Per-strike GEX data (need not be sorted).
        spot : float
            Current underlying price (used as fallback and tie-breaker).

        Returns
        -------
        float
            Interpolated price where cumulative dealer GEX equals zero.
        """
        if not strikes_gex:
            return spot

        sorted_sg = sorted(strikes_gex, key=lambda sg: sg.strike)

        # Build cumulative GEX from lowest strike upward
        cum_gex: List[float] = []
        running = 0.0
        for sg in sorted_sg:
            running += sg.net_gex
            cum_gex.append(running)

        # Find zero-crossings; pick the one closest to spot
        crossings: List[float] = []
        for i in range(len(cum_gex) - 1):
            if cum_gex[i] * cum_gex[i + 1] < 0:
                # Linear interpolation
                k1 = sorted_sg[i].strike
                k2 = sorted_sg[i + 1].strike
                g1 = cum_gex[i]
                g2 = cum_gex[i + 1]
                flip = k1 + (k2 - k1) * abs(g1) / (abs(g1) + abs(g2) + _EPSILON)
                crossings.append(flip)

        if not crossings:
            # No sign change -- return spot as fallback
            return spot

        # Closest crossing to current spot
        return min(crossings, key=lambda x: abs(x - spot))

    # ------------------------------------------------------------------
    # d) Max pain
    # ------------------------------------------------------------------

    def find_max_pain(self, chain: OptionsChain) -> float:
        """Calculate the max-pain strike.

        Max pain is the strike at which the total dollar value of all
        in-the-money options is minimised -- equivalently, the strike where
        the maximum amount of open interest expires worthless.

        For each candidate settlement strike *K_s*, the total ITM value is::

            Sum over all calls with strike K < K_s: (K_s - K) * OI_call(K)
            + Sum over all puts with strike K > K_s: (K - K_s) * OI_put(K)

        Parameters
        ----------
        chain : OptionsChain
            Full options chain.

        Returns
        -------
        float
            The max-pain strike price.
        """
        spot = chain.spot

        if not chain.quotes:
            return spot

        # Collect OI by strike and side
        call_oi_map: Dict[float, int] = defaultdict(int)
        put_oi_map: Dict[float, int] = defaultdict(int)

        for quote in chain.quotes:
            if quote.option_type == OptionSide.CALL:
                call_oi_map[quote.strike] += quote.open_interest
            else:
                put_oi_map[quote.strike] += quote.open_interest

        all_strikes = sorted(set(call_oi_map.keys()) | set(put_oi_map.keys()))
        if not all_strikes:
            return spot

        # Vectorised calculation using numpy
        strikes_arr = np.array(all_strikes, dtype=np.float64)
        call_oi_arr = np.array(
            [call_oi_map.get(k, 0) for k in all_strikes], dtype=np.float64
        )
        put_oi_arr = np.array(
            [put_oi_map.get(k, 0) for k in all_strikes], dtype=np.float64
        )

        best_strike = all_strikes[0]
        min_pain = np.inf

        for idx, ks in enumerate(strikes_arr):
            # Calls ITM when strike < ks  ->  payout = (ks - strike) * call_oi
            call_itm = np.maximum(ks - strikes_arr, 0.0) * call_oi_arr
            # Puts ITM when strike > ks   ->  payout = (strike - ks) * put_oi
            put_itm = np.maximum(strikes_arr - ks, 0.0) * put_oi_arr
            total_pain = call_itm.sum() + put_itm.sum()

            if total_pain < min_pain:
                min_pain = total_pain
                best_strike = float(ks)

        return best_strike

    # ------------------------------------------------------------------
    # e) Transition zone
    # ------------------------------------------------------------------

    def compute_transition_zone(
        self,
        strikes_gex: List[StrikeGEX],
        spot: float,
    ) -> Tuple[float, float]:
        """Find the transition zone boundaries.

        * **Upper bound**: first strike *above* spot where call gamma
          exceeds 2x put gamma.
        * **Lower bound**: first strike *below* spot where put gamma
          exceeds 2x call gamma.

        Parameters
        ----------
        strikes_gex : list[StrikeGEX]
            Per-strike GEX data.
        spot : float
            Current underlying price.

        Returns
        -------
        tuple[float, float]
            ``(lower_bound, upper_bound)``.
        """
        if not strikes_gex:
            return (spot, spot)

        sorted_sg = sorted(strikes_gex, key=lambda sg: sg.strike)

        upper = spot
        lower = spot

        # Walk upward from spot for upper bound
        for sg in sorted_sg:
            if sg.strike <= spot:
                continue
            abs_call = abs(sg.call_gex)
            abs_put = abs(sg.put_gex)
            if abs_put > _EPSILON and abs_call > 2.0 * abs_put:
                upper = sg.strike
                break
        else:
            # No strike qualifies -- use the highest strike as a fallback
            upper = sorted_sg[-1].strike

        # Walk downward from spot for lower bound
        for sg in reversed(sorted_sg):
            if sg.strike >= spot:
                continue
            abs_call = abs(sg.call_gex)
            abs_put = abs(sg.put_gex)
            if abs_call > _EPSILON and abs_put > 2.0 * abs_call:
                lower = sg.strike
                break
        else:
            lower = sorted_sg[0].strike

        return (lower, upper)

    # ------------------------------------------------------------------
    # f) GEX momentum
    # ------------------------------------------------------------------

    @staticmethod
    def compute_gex_momentum(
        current_gex: float,
        gex_history: List[Tuple[datetime, float]],
    ) -> float:
        """Track rate of GEX change over time.

        Returns dGEX/dt expressed as change-per-minute.  Uses the two most
        recent history entries (or current vs. last) to compute a simple
        finite difference.

        Parameters
        ----------
        current_gex : float
            Latest total net GEX value.
        gex_history : list[tuple[datetime, float]]
            Historical ``(timestamp, total_net_gex)`` pairs, ordered by
            time ascending.

        Returns
        -------
        float
            GEX momentum (change per minute).  Positive means GEX is
            increasing (becoming more positive / less negative).
        """
        if not gex_history:
            return 0.0

        last_ts, last_gex = gex_history[-1]
        now = datetime.now(timezone.utc)
        dt_minutes = (now - last_ts).total_seconds() / 60.0

        if dt_minutes < _EPSILON:
            return 0.0

        return (current_gex - last_gex) / dt_minutes

    # ------------------------------------------------------------------
    # g) Charm flow
    # ------------------------------------------------------------------

    @staticmethod
    def compute_charm_flow(
        strikes_gex: List[StrikeGEX],
        es_price: float,
    ) -> float:
        """Calculate net charm-driven ES futures contract equivalents.

        ::

            ES_contracts = Net_Charm_$ / (ES_price * 50)

        Positive result means dealers need to **buy** futures as the day
        progresses (supportive).  Negative means dealers need to **sell**
        futures (pressuring).

        Parameters
        ----------
        strikes_gex : list[StrikeGEX]
            Per-strike GEX data with ``net_charm`` populated.
        es_price : float
            Current E-mini S&P 500 futures price.

        Returns
        -------
        float
            Net ES-contract equivalents driven by charm.
        """
        if not strikes_gex or es_price <= 0:
            return 0.0

        total_charm_dollars = sum(sg.net_charm for sg in strikes_gex)
        return _safe_divide(total_charm_dollars, es_price * _ES_MULTIPLIER)

    # ------------------------------------------------------------------
    # h) Update flow model
    # ------------------------------------------------------------------

    def update_flow_model(
        self,
        strike: float,
        option_type: str,
        trade_size: int,
        is_customer_buy: bool,
    ) -> None:
        """Update the flow-based dealer position model with a new trade.

        Customer buy = dealer short that option:
        * For **calls**: dealer short call -> dealer has **negative** gamma.
        * For **puts**: dealer short put  -> dealer has **positive** gamma
          (dealers hedge short puts by buying, generating positive gamma).

        Customer sell = dealer long that option:
        * For **calls**: dealer long call  -> dealer has **positive** gamma
          (but in the index convention this is actually negative; see below).
        * For **puts**: dealer long put   -> dealer has **negative** gamma.

        We track the cumulative flow adjustment as a *dollar gamma* delta
        that gets added to the flow model.

        Parameters
        ----------
        strike : float
            Strike price of the traded option.
        option_type : str
            ``"call"`` or ``"put"`` (case-insensitive).
        trade_size : int
            Number of contracts traded.
        is_customer_buy : bool
            True if the customer is buying; False if selling.
        """
        opt = option_type.strip().lower()
        if opt not in ("call", "put"):
            logger.warning("update_flow_model: invalid option_type %r", option_type)
            return
        if trade_size <= 0:
            return

        # Compute a gamma adjustment proportional to trade size.
        # The actual gamma value is not available here (we do not have
        # spot/IV/time), so we store a contract-count-based adjustment
        # that will be scaled by gamma at profile-computation time.
        # We use _CONTRACT_MULTIPLIER so the units match compute_strike_gex.

        adjustment = float(trade_size) * _CONTRACT_MULTIPLIER

        if opt == "call":
            if is_customer_buy:
                # Customer bought calls -> dealer short calls -> negative gamma
                adjustment = -adjustment
            else:
                # Customer sold calls -> dealer long calls -> positive gamma
                # (standard index convention: dealers long calls = negative dealer gamma
                # because they are already assumed short calls from OI model;
                # selling *more* to dealers partially offsets that short)
                adjustment = +adjustment
        else:  # put
            if is_customer_buy:
                # Customer bought puts -> dealer short puts -> positive gamma
                adjustment = +adjustment
            else:
                # Customer sold puts -> dealer long puts -> negative gamma
                adjustment = -adjustment

        self.cumulative_flow[strike] += adjustment
        logger.debug(
            "Flow update: strike=%.1f type=%s size=%d cust_buy=%s adj=%.0f cum=%.0f",
            strike, opt, trade_size, is_customer_buy, adjustment,
            self.cumulative_flow[strike],
        )


# =========================================================================
# 2. GEXSignalGenerator -- trading signals
# =========================================================================

class GEXSignalGenerator:
    """Generates the six GEX-based trading signals.

    Signals
    -------
    1. Gamma Flip Crossover
    2. Gamma Wall Approach
    3. Transition Zone Breakout
    4. GEX Collapse (Pre-Expiration Unpin)
    5. Charm-Driven Flow Prediction
    6. Vanna Amplification

    Parameters
    ----------
    gex_engine : GEXEngine
        Configured GEX computation engine.
    gex_history : list[GEXProfile]
        Rolling window of recent GEX profiles (used for collapse detection
        and momentum tracking).
    signal_history : list[GEXSignal]
        Previously emitted signals (used for de-duplication / cooldown).
    """

    # Cooldown: minimum seconds between duplicate signal types
    _SIGNAL_COOLDOWN_SECONDS: int = 120

    def __init__(
        self,
        gex_engine: GEXEngine,
        gex_history: Optional[List[GEXProfile]] = None,
        signal_history: Optional[List[GEXSignal]] = None,
    ) -> None:
        self.gex_engine = gex_engine
        self.gex_history: List[GEXProfile] = gex_history if gex_history is not None else []
        self.signal_history: List[GEXSignal] = signal_history if signal_history is not None else []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_on_cooldown(self, signal_type: GEXSignalType) -> bool:
        """Return True if a signal of this type was emitted recently."""
        now = datetime.now(timezone.utc)
        for sig in reversed(self.signal_history):
            if sig.signal_type == signal_type:
                elapsed = (now - sig.timestamp).total_seconds()
                if elapsed < self._SIGNAL_COOLDOWN_SECONDS:
                    return True
                break  # Only check the most recent of this type
        return False

    def _record(self, signal: GEXSignal) -> GEXSignal:
        """Append a signal to history and return it."""
        self.signal_history.append(signal)
        return signal

    # ------------------------------------------------------------------
    # a) Signal 1: Gamma Flip Crossover
    # ------------------------------------------------------------------

    def check_gamma_flip_crossover(
        self,
        current_profile: GEXProfile,
        spot: float,
        prior_spot: float,
    ) -> Optional[GEXSignal]:
        """SIGNAL 1 -- Gamma Flip Crossover.

        Trigger: SPX crosses the gamma-flip level since the last observation.

        * Crossing from **below** (prior_spot < flip <= spot) -- entering
          positive-gamma territory -- **BULLISH** (confidence ~65-70 %).
        * Crossing from **above** (prior_spot > flip >= spot) -- entering
          negative-gamma territory -- **BEARISH**.

        Parameters
        ----------
        current_profile : GEXProfile
        spot : float
            Current SPX price.
        prior_spot : float
            SPX price at previous observation.

        Returns
        -------
        GEXSignal or None
        """
        if self._is_on_cooldown(GEXSignalType.GAMMA_FLIP_CROSSOVER):
            return None

        flip = current_profile.gamma_flip_level
        if flip <= 0:
            return None

        crossed_up = prior_spot < flip <= spot
        crossed_down = prior_spot > flip >= spot

        if not (crossed_up or crossed_down):
            return None

        if crossed_up:
            direction = "bullish"
            confidence = 67.5
            description = (
                f"SPX crossed ABOVE gamma flip at {flip:.1f} "
                f"(from {prior_spot:.1f} to {spot:.1f}). "
                "Entering positive-gamma zone -- dealers will sell rallies "
                "and buy dips, supportive of mean-reversion / range-bound action."
            )
            target = current_profile.call_wall
            stop = flip - 2.0  # Re-entry below flip invalidates
        else:
            direction = "bearish"
            confidence = 67.5
            description = (
                f"SPX crossed BELOW gamma flip at {flip:.1f} "
                f"(from {prior_spot:.1f} to {spot:.1f}). "
                "Entering negative-gamma zone -- dealers will buy rallies "
                "and sell dips, amplifying directional moves."
            )
            target = current_profile.put_wall
            stop = flip + 2.0

        signal = GEXSignal(
            signal_type=GEXSignalType.GAMMA_FLIP_CROSSOVER,
            direction=direction,
            confidence=confidence,
            description=description,
            trigger_level=flip,
            target=target,
            stop=stop,
            timestamp=datetime.now(timezone.utc),
            metadata={
                "spot": spot,
                "prior_spot": prior_spot,
                "gamma_flip": flip,
                "total_net_gex": current_profile.total_net_gex,
            },
        )
        return self._record(signal)

    # ------------------------------------------------------------------
    # b) Signal 2: Gamma Wall Approach
    # ------------------------------------------------------------------

    def check_gamma_wall_approach(
        self,
        current_profile: GEXProfile,
        spot: float,
    ) -> Optional[GEXSignal]:
        """SIGNAL 2 -- Gamma Wall Approach.

        Trigger: SPX is within 3 points of the Call Wall or Put Wall.

        * **Call Wall**: strong RESISTANCE -- dealers must sell to hedge,
          creating selling pressure (confidence ~60-65 %).
        * **Put Wall**: strong SUPPORT -- dealers must buy to hedge.
        * If the wall is **breached**, expect ACCELERATION (gamma squeeze).

        Parameters
        ----------
        current_profile : GEXProfile
        spot : float

        Returns
        -------
        GEXSignal or None
        """
        if self._is_on_cooldown(GEXSignalType.GAMMA_WALL_APPROACH):
            return None

        approach_distance = 3.0  # SPX points

        call_wall = current_profile.call_wall
        put_wall = current_profile.put_wall
        dist_to_call = abs(spot - call_wall)
        dist_to_put = abs(spot - put_wall)

        # Check call wall approach
        if dist_to_call <= approach_distance and spot <= call_wall:
            breached = spot >= call_wall
            confidence = 62.5
            direction = "bearish" if not breached else "bullish"
            if breached:
                description = (
                    f"SPX BREACHED call wall at {call_wall:.0f}! "
                    "Gamma squeeze likely -- move may ACCELERATE higher."
                )
                confidence = 70.0
                target = call_wall + 10.0
                stop = call_wall - 2.0
            else:
                description = (
                    f"SPX approaching call wall at {call_wall:.0f} "
                    f"(distance: {dist_to_call:.1f} pts). "
                    "Expect RESISTANCE -- dealers will sell into the rally."
                )
                target = call_wall - 5.0
                stop = call_wall + 3.0

            signal = GEXSignal(
                signal_type=GEXSignalType.GAMMA_WALL_APPROACH,
                direction=direction,
                confidence=confidence,
                description=description,
                trigger_level=call_wall,
                target=target,
                stop=stop,
                timestamp=datetime.now(timezone.utc),
                metadata={
                    "wall_type": "call",
                    "wall_strike": call_wall,
                    "distance": dist_to_call,
                    "breached": breached,
                },
            )
            return self._record(signal)

        # Check put wall approach
        if dist_to_put <= approach_distance and spot >= put_wall:
            breached = spot <= put_wall
            confidence = 62.5
            direction = "bullish" if not breached else "bearish"
            if breached:
                description = (
                    f"SPX BREACHED put wall at {put_wall:.0f}! "
                    "Gamma squeeze likely -- move may ACCELERATE lower."
                )
                confidence = 70.0
                target = put_wall - 10.0
                stop = put_wall + 2.0
            else:
                description = (
                    f"SPX approaching put wall at {put_wall:.0f} "
                    f"(distance: {dist_to_put:.1f} pts). "
                    "Expect SUPPORT -- dealers will buy into the decline."
                )
                target = put_wall + 5.0
                stop = put_wall - 3.0

            signal = GEXSignal(
                signal_type=GEXSignalType.GAMMA_WALL_APPROACH,
                direction=direction,
                confidence=confidence,
                description=description,
                trigger_level=put_wall,
                target=target,
                stop=stop,
                timestamp=datetime.now(timezone.utc),
                metadata={
                    "wall_type": "put",
                    "wall_strike": put_wall,
                    "distance": dist_to_put,
                    "breached": breached,
                },
            )
            return self._record(signal)

        return None

    # ------------------------------------------------------------------
    # c) Signal 3: Transition Zone Breakout
    # ------------------------------------------------------------------

    def check_transition_zone_breakout(
        self,
        current_profile: GEXProfile,
        spot: float,
        minutes_outside: int,
    ) -> Optional[GEXSignal]:
        """SIGNAL 3 -- Transition Zone Breakout.

        Trigger: SPX breaks above upper TZ boundary or below lower TZ
        boundary, with at least 2 minutes of confirmation outside the zone.

        * Upside breakout target: +GEX strike.
        * Downside breakout target: -GEX strike.
        * Stop: re-entry into the transition zone.

        Parameters
        ----------
        current_profile : GEXProfile
        spot : float
        minutes_outside : int
            Number of consecutive minutes SPX has been outside the
            transition zone.

        Returns
        -------
        GEXSignal or None
        """
        if self._is_on_cooldown(GEXSignalType.TRANSITION_ZONE_BREAKOUT):
            return None

        tz_upper = current_profile.transition_zone_upper
        tz_lower = current_profile.transition_zone_lower

        # Require confirmation: at least 2 minutes outside
        if minutes_outside < 2:
            return None

        if spot > tz_upper:
            direction = "bullish"
            confidence = 60.0 + min(minutes_outside * 2.0, 15.0)  # Up to 75%
            description = (
                f"SPX broke above transition zone upper bound ({tz_upper:.0f}) "
                f"and held for {minutes_outside} minutes. "
                f"Target: +GEX at {current_profile.plus_gex:.0f}. "
                f"Stop: re-entry below {tz_upper:.0f}."
            )
            target = current_profile.plus_gex
            stop = tz_upper
        elif spot < tz_lower:
            direction = "bearish"
            confidence = 60.0 + min(minutes_outside * 2.0, 15.0)
            description = (
                f"SPX broke below transition zone lower bound ({tz_lower:.0f}) "
                f"and held for {minutes_outside} minutes. "
                f"Target: -GEX at {current_profile.minus_gex:.0f}. "
                f"Stop: re-entry above {tz_lower:.0f}."
            )
            target = current_profile.minus_gex
            stop = tz_lower
        else:
            return None  # Inside transition zone

        signal = GEXSignal(
            signal_type=GEXSignalType.TRANSITION_ZONE_BREAKOUT,
            direction=direction,
            confidence=min(confidence, 80.0),
            description=description,
            trigger_level=tz_upper if direction == "bullish" else tz_lower,
            target=target,
            stop=stop,
            timestamp=datetime.now(timezone.utc),
            metadata={
                "tz_upper": tz_upper,
                "tz_lower": tz_lower,
                "minutes_outside": minutes_outside,
                "plus_gex": current_profile.plus_gex,
                "minus_gex": current_profile.minus_gex,
            },
        )
        return self._record(signal)

    # ------------------------------------------------------------------
    # d) Signal 4: GEX Collapse
    # ------------------------------------------------------------------

    def check_gex_collapse(
        self,
        current_profile: GEXProfile,
    ) -> Optional[GEXSignal]:
        """SIGNAL 4 -- GEX Collapse (Pre-Expiration Unpin).

        Trigger: total GEX drops > 30 % within the last 15 minutes
        (typically occurs 3:15--3:45 PM as large OI expires / rolls).

        Effect: price becomes *unshackled* from gamma walls -- expect
        **extreme** volatility.

        Parameters
        ----------
        current_profile : GEXProfile

        Returns
        -------
        GEXSignal or None
        """
        if self._is_on_cooldown(GEXSignalType.GEX_COLLAPSE):
            return None

        if len(self.gex_history) < 2:
            return None

        current_gex = current_profile.total_net_gex

        # Look back ~15 minutes in history.  Profiles are assumed to be
        # appended every 60 seconds, so 15 entries = ~15 min.
        lookback = min(15, len(self.gex_history))
        reference_profile = self.gex_history[-lookback]
        reference_gex = reference_profile.total_net_gex

        if abs(reference_gex) < _EPSILON:
            return None

        pct_change = (current_gex - reference_gex) / abs(reference_gex)

        # We care about a *drop* in absolute GEX magnitude
        abs_current = abs(current_gex)
        abs_reference = abs(reference_gex)

        if abs_reference < _EPSILON:
            return None

        abs_drop_pct = (abs_reference - abs_current) / abs_reference

        if abs_drop_pct < 0.30:
            return None  # Not a collapse

        direction = "neutral"  # GEX collapse is volatility, not directional
        confidence = 55.0 + min(abs_drop_pct * 50.0, 25.0)

        description = (
            f"GEX COLLAPSE detected: total |GEX| dropped {abs_drop_pct:.0%} "
            f"in ~{lookback} minutes "
            f"(from {abs_reference:,.0f} to {abs_current:,.0f}). "
            "Gamma walls dissolving -- price is becoming unshackled. "
            "EXTREME volatility expected.  Consider reducing position size."
        )

        signal = GEXSignal(
            signal_type=GEXSignalType.GEX_COLLAPSE,
            direction=direction,
            confidence=min(confidence, 85.0),
            description=description,
            trigger_level=current_gex,
            target=None,
            stop=None,
            timestamp=datetime.now(timezone.utc),
            metadata={
                "current_gex": current_gex,
                "reference_gex": reference_gex,
                "abs_drop_pct": abs_drop_pct,
                "lookback_minutes": lookback,
                "pct_change": pct_change,
            },
        )
        return self._record(signal)

    # ------------------------------------------------------------------
    # e) Signal 5: Charm-Driven Flow
    # ------------------------------------------------------------------

    def check_charm_driven_flow(
        self,
        current_profile: GEXProfile,
    ) -> Optional[GEXSignal]:
        """SIGNAL 5 -- Charm-Driven Flow Prediction.

        Trigger: net charm exposure implies > 5,000 ES-contract equivalents
        of flow.

        The effect builds throughout the day and is strongest from
        2:00--4:00 PM ET.

        Confidence: Medium (~55-65 %).

        Parameters
        ----------
        current_profile : GEXProfile

        Returns
        -------
        GEXSignal or None
        """
        if self._is_on_cooldown(GEXSignalType.CHARM_DRIVEN_FLOW):
            return None

        es_contracts = current_profile.charm_net_es_contracts
        threshold = 5000  # ES contract equivalents

        if abs(es_contracts) < threshold:
            return None

        if es_contracts > 0:
            direction = "bullish"
            description = (
                f"Charm-driven flow predicts dealers need to BUY "
                f"~{es_contracts:,.0f} ES contract equivalents as 0DTE "
                "options decay.  This creates supportive buying pressure, "
                "strongest into the close."
            )
        else:
            direction = "bearish"
            description = (
                f"Charm-driven flow predicts dealers need to SELL "
                f"~{abs(es_contracts):,.0f} ES contract equivalents as 0DTE "
                "options decay.  This creates selling pressure, "
                "strongest into the close."
            )

        confidence = 55.0 + min(abs(es_contracts) / threshold * 5.0, 15.0)

        signal = GEXSignal(
            signal_type=GEXSignalType.CHARM_DRIVEN_FLOW,
            direction=direction,
            confidence=min(confidence, 70.0),
            description=description,
            trigger_level=es_contracts,
            target=None,
            stop=None,
            timestamp=datetime.now(timezone.utc),
            metadata={
                "es_contracts": es_contracts,
                "vanna_net": current_profile.vanna_net_exposure,
            },
        )
        return self._record(signal)

    # ------------------------------------------------------------------
    # f) Signal 6: Vanna Amplification
    # ------------------------------------------------------------------

    def check_vanna_amplification(
        self,
        current_profile: GEXProfile,
        vix1d_change_pct: float,
    ) -> Optional[GEXSignal]:
        """SIGNAL 6 -- Vanna Amplification.

        Trigger: VIX1D changing > 10 % AND net vanna exposure is large.

        Mechanics:

        * VIX **up** + negative net vanna = dealers must SELL delta
          (bearish amplification).
        * VIX **down** + positive net vanna = dealers must BUY delta
          (bullish amplification).

        Parameters
        ----------
        current_profile : GEXProfile
        vix1d_change_pct : float
            Intraday percentage change in VIX1D (e.g. 12.0 means +12 %).

        Returns
        -------
        GEXSignal or None
        """
        if self._is_on_cooldown(GEXSignalType.VANNA_AMPLIFICATION):
            return None

        vanna_net = current_profile.vanna_net_exposure

        # Both conditions must be met
        if abs(vix1d_change_pct) < 10.0:
            return None

        # Define "large" vanna: use a relative threshold vs total GEX
        total_gex_abs = abs(current_profile.total_net_gex)
        vanna_threshold = max(total_gex_abs * 0.05, 1e6)  # At least 5% of GEX or 1M

        if abs(vanna_net) < vanna_threshold:
            return None

        vix_up = vix1d_change_pct > 0
        vanna_negative = vanna_net < 0

        if vix_up and vanna_negative:
            direction = "bearish"
            description = (
                f"Vanna amplification: VIX1D up {vix1d_change_pct:+.1f}% "
                f"with large negative vanna ({vanna_net:,.0f}). "
                "Dealers must SELL delta hedges, amplifying the down move. "
                "Bearish feedback loop in effect."
            )
        elif (not vix_up) and (not vanna_negative):
            direction = "bullish"
            description = (
                f"Vanna amplification: VIX1D down {vix1d_change_pct:+.1f}% "
                f"with large positive vanna ({vanna_net:,.0f}). "
                "Dealers must BUY delta hedges, amplifying the up move. "
                "Bullish feedback loop in effect."
            )
        else:
            # VIX up + positive vanna or VIX down + negative vanna:
            # opposing forces -- no clear amplification signal
            return None

        confidence = 55.0 + min(abs(vix1d_change_pct) * 0.5, 15.0)

        signal = GEXSignal(
            signal_type=GEXSignalType.VANNA_AMPLIFICATION,
            direction=direction,
            confidence=min(confidence, 75.0),
            description=description,
            trigger_level=vanna_net,
            target=None,
            stop=None,
            timestamp=datetime.now(timezone.utc),
            metadata={
                "vix1d_change_pct": vix1d_change_pct,
                "vanna_net": vanna_net,
                "total_net_gex": current_profile.total_net_gex,
                "vanna_threshold_used": vanna_threshold,
            },
        )
        return self._record(signal)

    # ------------------------------------------------------------------
    # g) Generate all signals
    # ------------------------------------------------------------------

    def generate_all_signals(
        self,
        current_profile: GEXProfile,
        spot: float,
        prior_spot: float,
        vix1d_change_pct: float,
        minutes_outside_tz: int = 0,
    ) -> List[GEXSignal]:
        """Run all six signal checks and return active signals.

        Parameters
        ----------
        current_profile : GEXProfile
            Latest GEX profile.
        spot : float
            Current SPX price.
        prior_spot : float
            SPX price at the previous observation (~60 s ago).
        vix1d_change_pct : float
            Intraday VIX1D percentage change.
        minutes_outside_tz : int
            Consecutive minutes SPX has been outside the transition zone
            (for Signal 3).

        Returns
        -------
        list[GEXSignal]
            All signals that fired this cycle (may be empty).
        """
        signals: List[GEXSignal] = []

        # Signal 1: Gamma Flip Crossover
        try:
            sig = self.check_gamma_flip_crossover(current_profile, spot, prior_spot)
            if sig is not None:
                signals.append(sig)
        except Exception:
            logger.exception("Error in check_gamma_flip_crossover")

        # Signal 2: Gamma Wall Approach
        try:
            sig = self.check_gamma_wall_approach(current_profile, spot)
            if sig is not None:
                signals.append(sig)
        except Exception:
            logger.exception("Error in check_gamma_wall_approach")

        # Signal 3: Transition Zone Breakout
        try:
            sig = self.check_transition_zone_breakout(
                current_profile, spot, minutes_outside_tz
            )
            if sig is not None:
                signals.append(sig)
        except Exception:
            logger.exception("Error in check_transition_zone_breakout")

        # Signal 4: GEX Collapse
        try:
            sig = self.check_gex_collapse(current_profile)
            if sig is not None:
                signals.append(sig)
        except Exception:
            logger.exception("Error in check_gex_collapse")

        # Signal 5: Charm-Driven Flow
        try:
            sig = self.check_charm_driven_flow(current_profile)
            if sig is not None:
                signals.append(sig)
        except Exception:
            logger.exception("Error in check_charm_driven_flow")

        # Signal 6: Vanna Amplification
        try:
            sig = self.check_vanna_amplification(current_profile, vix1d_change_pct)
            if sig is not None:
                signals.append(sig)
        except Exception:
            logger.exception("Error in check_vanna_amplification")

        # Append the current profile to rolling history
        self.gex_history.append(current_profile)

        return signals
