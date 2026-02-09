"""
SCANIFY GEX Engine — Core Gamma Exposure computation for 0DTE SPX scanner.

Implements the full GEX specification:
  - Black-Scholes Greeks with higher-order sensitivities (charm, vanna, speed)
  - Dealer gamma exposure estimation via Simple Model
  - Gamma flip level interpolation
  - Transition zone, vol trigger, max pain, call/put walls
  - Net charm / vanna / speed exposure aggregation
  - Six distinct GEX signal detectors
  - GEX momentum tracking over rolling history

Key formulas:
  T = minutes_remaining / (252 * 390)
  d1 = [ln(S/K) + (r - q + sigma^2/2) * T] / (sigma * sqrt(T))
  Gamma = e^(-qT) * N'(d1) / (S * sigma * sqrt(T))
  Dealer_Gamma_Call(K) = -1 * Gamma(K) * OI_call(K) * 100 * S
  Dealer_Gamma_Put(K)  = +1 * Gamma(K) * OI_put(K) * 100 * S
"""

import math
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import deque

from .config import GEXConfig, GEXSignalType, SignalDirection
from .data_feeds import OptionsChain, OptionQuote


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SQRT_2PI = math.sqrt(2.0 * math.pi)
_SQRT_2 = math.sqrt(2.0)

# Minimum time-to-expiry expressed in trading-year fractions.
# 1 minute = 1 / (252 * 390)
_MIN_T = 1.0 / (252.0 * 390.0)

# ES contract multiplier (used for charm -> ES equivalents conversion).
_ES_MULTIPLIER = 50.0

# SPX option contract multiplier.
_OPT_MULTIPLIER = 100.0

# Bump sizes for numerical greeks.
_SPOT_BUMP = 0.01          # 1 cent for speed / vanna bump
_VOL_BUMP = 0.001          # 0.1 vol-pt for vanna bump
_TIME_BUMP = _MIN_T        # 1 minute for charm bump


# ---------------------------------------------------------------------------
# Helper functions — standard normal CDF / PDF and d1
# ---------------------------------------------------------------------------

def norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function.

    Uses ``math.erfc`` for full double-precision accuracy.
    """
    return 0.5 * math.erfc(-x / _SQRT_2)


def norm_pdf(x: float) -> float:
    """Standard normal probability density function."""
    return math.exp(-0.5 * x * x) / _SQRT_2PI


def compute_d1(S: float, K: float, T: float, sigma: float,
               r: float, q: float) -> float:
    """Compute the Black-Scholes *d1* parameter.

    Parameters
    ----------
    S : spot price
    K : strike price
    T : time to expiry in trading-year fractions
    sigma : annualised implied volatility
    r : risk-free rate (annualised, continuous)
    q : continuous dividend yield
    """
    if T < _MIN_T:
        T = _MIN_T
    if sigma <= 0.0:
        sigma = 1e-6
    if K <= 0.0 or S <= 0.0:
        return 0.0
    sqrt_T = math.sqrt(T)
    return (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * sqrt_T)


# ---------------------------------------------------------------------------
# Full Greeks for a single strike
# ---------------------------------------------------------------------------

def compute_greeks_for_strike(
    S: float, K: float, T: float, sigma: float,
    r: float, q: float,
) -> dict:
    """Compute delta (call & put), gamma, theta, charm, vanna, and speed
    for a single strike.

    Charm, vanna and speed are obtained via *numerical central-difference
    bumping* so that the implementation stays robust for very small *T*.

    Returns
    -------
    dict with keys:
        delta_call, delta_put, gamma, theta,
        charm, vanna, speed
    """
    if T < _MIN_T:
        T = _MIN_T
    if sigma <= 0.0:
        sigma = 1e-6

    sqrt_T = math.sqrt(T)
    d1 = compute_d1(S, K, T, sigma, r, q)
    d2 = d1 - sigma * sqrt_T

    nd1 = norm_cdf(d1)
    npd1 = norm_pdf(d1)
    discount = math.exp(-q * T)

    delta_call = discount * nd1
    delta_put = delta_call - discount  # put-call parity

    gamma = discount * npd1 / (S * sigma * sqrt_T)

    # Theta (call)
    term1 = -(S * discount * npd1 * sigma) / (2.0 * sqrt_T)
    term2 = q * S * discount * nd1
    term3 = r * K * math.exp(-r * T) * norm_cdf(d2)
    theta = term1 + term2 - term3  # per-year; callers can divide by 252

    # --- Numerical charm: dDelta_call / dT via central difference ----------
    T_up = T + _TIME_BUMP
    T_dn = max(_MIN_T, T - _TIME_BUMP)
    d1_up = compute_d1(S, K, T_up, sigma, r, q)
    d1_dn = compute_d1(S, K, T_dn, sigma, r, q)
    delta_call_up = math.exp(-q * T_up) * norm_cdf(d1_up)
    delta_call_dn = math.exp(-q * T_dn) * norm_cdf(d1_dn)
    charm = (delta_call_up - delta_call_dn) / (T_up - T_dn)

    # --- Numerical vanna: dDelta_call / dSigma ---------
    sigma_up = sigma + _VOL_BUMP
    sigma_dn = max(1e-6, sigma - _VOL_BUMP)
    d1_sup = compute_d1(S, K, T, sigma_up, r, q)
    d1_sdn = compute_d1(S, K, T, sigma_dn, r, q)
    delta_call_sup = discount * norm_cdf(d1_sup)
    delta_call_sdn = discount * norm_cdf(d1_sdn)
    vanna = (delta_call_sup - delta_call_sdn) / (sigma_up - sigma_dn)

    # --- Numerical speed: dGamma / dS -----------------------------------
    dS = max(_SPOT_BUMP, S * 1e-4)
    S_up = S + dS
    S_dn = S - dS
    d1_gup = compute_d1(S_up, K, T, sigma, r, q)
    d1_gdn = compute_d1(S_dn, K, T, sigma, r, q)
    npd1_gup = norm_pdf(d1_gup)
    npd1_gdn = norm_pdf(d1_gdn)
    gamma_up = discount * npd1_gup / (S_up * sigma * sqrt_T)
    gamma_dn = discount * npd1_gdn / (S_dn * sigma * sqrt_T)
    speed = (gamma_up - gamma_dn) / (2.0 * dS)

    return {
        "delta_call": delta_call,
        "delta_put": delta_put,
        "gamma": gamma,
        "theta": theta,
        "charm": charm,
        "vanna": vanna,
        "speed": speed,
    }


# ---------------------------------------------------------------------------
# Data classes for results and signals
# ---------------------------------------------------------------------------

@dataclass
class GEXResult:
    """Snapshot of the full GEX surface at a point in time."""

    total_net_gex: float = 0.0
    gex_by_strike: Dict[float, float] = field(default_factory=dict)
    call_gex_by_strike: Dict[float, float] = field(default_factory=dict)
    put_gex_by_strike: Dict[float, float] = field(default_factory=dict)

    gamma_flip_level: float = 0.0
    plus_gex_strike: float = 0.0    # max positive gamma strike above spot
    minus_gex_strike: float = 0.0   # max negative gamma strike below spot

    call_wall: float = 0.0          # highest call OI strike
    put_wall: float = 0.0           # highest put OI strike
    max_pain: float = 0.0
    vol_trigger: float = 0.0

    transition_zone: Tuple[float, float] = (0.0, 0.0)

    net_charm_exposure: float = 0.0       # ES contract equivalents
    charm_direction: SignalDirection = SignalDirection.NEUTRAL
    net_vanna_exposure: float = 0.0
    net_speed_by_strike: Dict[float, float] = field(default_factory=dict)

    dealer_position: str = "long_gamma"   # "long_gamma" | "short_gamma"
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class GEXSignal:
    """A single GEX-derived trading signal."""

    signal_type: GEXSignalType = GEXSignalType.GAMMA_FLIP_CROSSOVER
    direction: SignalDirection = SignalDirection.NEUTRAL
    confidence: float = 0.0        # 0-1
    trigger_price: float = 0.0
    target_price: Optional[float] = None
    description: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# GEX Engine
# ---------------------------------------------------------------------------

class GEXEngine:
    """Core Gamma Exposure computation engine for 0DTE SPX.

    Maintains a rolling history of :class:`GEXResult` snapshots so that
    momentum and collapse signals can be computed across time.
    """

    def __init__(self, config: GEXConfig):
        self.config = config

        # Rolling history of GEX snapshots for momentum / collapse detection.
        # Store up to 480 snapshots (8 hours of 1-minute updates).
        self._history: deque = deque(maxlen=480)

    # ------------------------------------------------------------------
    # IV extraction
    # ------------------------------------------------------------------

    def compute_iv_from_price(
        self,
        market_price: float,
        S: float,
        K: float,
        T: float,
        r: float,
        q: float,
        option_type: str,
        max_iter: int = 50,
        tol: float = 1e-6,
    ) -> float:
        """Newton-Raphson implied-volatility extraction from mid-price.

        Parameters
        ----------
        market_price : observed (mid) option price
        option_type  : ``"call"`` or ``"put"``

        Returns
        -------
        float — annualised implied volatility, clamped to [0.01, 5.0].
        """
        if T < _MIN_T:
            T = _MIN_T
        if market_price <= 0.0:
            return 0.01

        # Initial guess via Brenner-Subrahmanyam approximation.
        sigma = math.sqrt(2.0 * math.pi / T) * market_price / S
        sigma = max(0.05, min(sigma, 3.0))

        for _ in range(max_iter):
            price = self._bs_price(S, K, T, sigma, r, q, option_type)
            vega = self._bs_vega(S, K, T, sigma, r, q)

            diff = price - market_price
            if abs(diff) < tol:
                return max(0.01, min(sigma, 5.0))

            if vega < 1e-12:
                break

            sigma -= diff / vega
            sigma = max(0.01, min(sigma, 5.0))

        return max(0.01, min(sigma, 5.0))

    # ------------------------------------------------------------------
    # Single-strike Greeks (public convenience wrapper)
    # ------------------------------------------------------------------

    def compute_strike_greeks(
        self,
        S: float, K: float, T: float, sigma: float,
        r: float, q: float,
    ) -> dict:
        """All greeks for a single strike including charm, vanna, speed
        (numerical bumping).  Thin wrapper around the module-level helper.
        """
        return compute_greeks_for_strike(S, K, T, sigma, r, q)

    # ------------------------------------------------------------------
    # Dealer position estimation (Simple Model)
    # ------------------------------------------------------------------

    def estimate_dealer_position(
        self,
        chain: OptionsChain,
        spot: float,
    ) -> Dict[float, dict]:
        """Estimate dealer gamma per strike via the Simple Model.

        Dealer_Gamma_Call(K) = -1 * Gamma(K) * OI_call(K) * 100 * S
        Dealer_Gamma_Put(K)  = +1 * Gamma(K) * OI_put(K) * 100 * S

        Returns
        -------
        Dict mapping strike -> {"call_gex", "put_gex", "net_gex"}.
        """
        result: Dict[float, dict] = {}
        T = self._time_to_expiry(chain)

        # Group quotes by strike.
        strike_map = self._group_by_strike(chain)

        for strike, quotes in strike_map.items():
            call_oi = 0
            put_oi = 0
            sigma = None

            for q_obj in quotes:
                if q_obj.option_type == "call":
                    call_oi = q_obj.open_interest
                else:
                    put_oi = q_obj.open_interest
                # Take any available IV; prefer call side.
                if q_obj.iv is not None and q_obj.iv > 0:
                    sigma = q_obj.iv

            if call_oi == 0 and put_oi == 0:
                continue

            if sigma is None or sigma <= 0:
                sigma = 0.20  # fallback

            greeks = compute_greeks_for_strike(spot, strike, T, sigma, 0.0, 0.0)
            gamma = greeks["gamma"]

            call_gex = -1.0 * gamma * call_oi * _OPT_MULTIPLIER * spot
            put_gex = 1.0 * gamma * put_oi * _OPT_MULTIPLIER * spot

            result[strike] = {
                "call_gex": call_gex,
                "put_gex": put_gex,
                "net_gex": call_gex + put_gex,
            }

        return result

    # ------------------------------------------------------------------
    # Full GEX computation
    # ------------------------------------------------------------------

    def compute_gex(
        self,
        chain: OptionsChain,
        spot: float,
        r: float = 0.0,
        q: float = 0.0,
    ) -> GEXResult:
        """Full GEX computation across the entire options chain.

        Steps
        -----
        1. For each strike compute IV (from mid-price or chain IV) and gamma.
        2. Estimate dealer position per strike.
        3. Aggregate to total net GEX.
        4. Interpolate gamma flip level (cumulative GEX zero-crossing).
        5. Identify +GEX / -GEX / call wall / put wall / max pain / vol
           trigger / transition zone.
        6. Compute net charm / vanna / speed exposures.
        """
        result = GEXResult(timestamp=datetime.utcnow())
        T = self._time_to_expiry(chain)
        strike_map = self._group_by_strike(chain)

        if not strike_map:
            self._history.append(result)
            return result

        # --- Per-strike computation ------------------------------------
        max_call_oi_strike = 0.0
        max_call_oi = 0
        max_put_oi_strike = 0.0
        max_put_oi = 0

        total_charm = 0.0
        total_vanna = 0.0

        for strike in sorted(strike_map.keys()):
            quotes = strike_map[strike]

            call_oi = 0
            put_oi = 0
            sigma = None

            for q_obj in quotes:
                if q_obj.option_type == "call":
                    call_oi = q_obj.open_interest
                    # Try to extract IV from market mid-price when chain IV
                    # is missing or unreliable.
                    if (q_obj.iv is None or q_obj.iv <= 0) and q_obj.bid is not None and q_obj.ask is not None:
                        mid = (q_obj.bid + q_obj.ask) / 2.0
                        if mid > self.config.iv_extrapolation_threshold:
                            sigma = self.compute_iv_from_price(
                                mid, spot, strike, T, r, q, "call"
                            )
                    elif q_obj.iv is not None and q_obj.iv > 0:
                        sigma = q_obj.iv
                else:
                    put_oi = q_obj.open_interest
                    if sigma is None:
                        if (q_obj.iv is None or q_obj.iv <= 0) and q_obj.bid is not None and q_obj.ask is not None:
                            mid = (q_obj.bid + q_obj.ask) / 2.0
                            if mid > self.config.iv_extrapolation_threshold:
                                sigma = self.compute_iv_from_price(
                                    mid, spot, strike, T, r, q, "put"
                                )
                        elif q_obj.iv is not None and q_obj.iv > 0:
                            sigma = q_obj.iv

            # Skip strikes with zero OI entirely.
            if call_oi == 0 and put_oi == 0:
                continue

            if sigma is None or sigma <= 0:
                sigma = 0.20

            greeks = compute_greeks_for_strike(spot, strike, T, sigma, r, q)
            gamma = greeks["gamma"]
            charm = greeks["charm"]
            vanna = greeks["vanna"]
            speed = greeks["speed"]

            # Dealer GEX (Simple Model).
            call_gex = -1.0 * gamma * call_oi * _OPT_MULTIPLIER * spot
            put_gex = 1.0 * gamma * put_oi * _OPT_MULTIPLIER * spot
            net_gex = call_gex + put_gex

            result.call_gex_by_strike[strike] = call_gex
            result.put_gex_by_strike[strike] = put_gex
            result.gex_by_strike[strike] = net_gex
            result.total_net_gex += net_gex

            # Net speed by strike.
            net_speed = speed * (call_oi + put_oi) * _OPT_MULTIPLIER * spot
            result.net_speed_by_strike[strike] = net_speed

            # Charm exposure: dealer_sign same convention as GEX.
            # Call side: dealer is short -> charm exposure = -charm * OI * 100
            # Put side: dealer is long  -> charm exposure = +charm * OI * 100
            charm_call = -1.0 * charm * call_oi * _OPT_MULTIPLIER
            charm_put = 1.0 * charm * put_oi * _OPT_MULTIPLIER
            total_charm += charm_call + charm_put

            # Vanna exposure (same sign convention).
            vanna_call = -1.0 * vanna * call_oi * _OPT_MULTIPLIER
            vanna_put = 1.0 * vanna * put_oi * _OPT_MULTIPLIER
            total_vanna += vanna_call + vanna_put

            # Track call / put walls.
            if call_oi > max_call_oi:
                max_call_oi = call_oi
                max_call_oi_strike = strike
            if put_oi > max_put_oi:
                max_put_oi = put_oi
                max_put_oi_strike = strike

        result.call_wall = max_call_oi_strike
        result.put_wall = max_put_oi_strike

        # --- Charm → ES contract equivalents ---------------------------
        # Net_Charm_$ / (ES_price * 50)
        es_price = spot  # ES ≈ SPX for estimation purposes.
        if es_price > 0:
            result.net_charm_exposure = total_charm / (es_price * _ES_MULTIPLIER)
        else:
            result.net_charm_exposure = 0.0

        if result.net_charm_exposure > 0:
            result.charm_direction = SignalDirection.BULLISH
        elif result.net_charm_exposure < 0:
            result.charm_direction = SignalDirection.BEARISH
        else:
            result.charm_direction = SignalDirection.NEUTRAL

        result.net_vanna_exposure = total_vanna

        # --- Gamma flip level (interpolation) --------------------------
        result.gamma_flip_level = self._interpolate_gamma_flip(
            result.gex_by_strike, spot
        )

        # --- +GEX / -GEX strikes --------------------------------------
        plus_gex_val = 0.0
        minus_gex_val = 0.0
        for strike, gex_val in result.gex_by_strike.items():
            if strike >= spot and gex_val > plus_gex_val:
                plus_gex_val = gex_val
                result.plus_gex_strike = strike
            if strike <= spot and gex_val < minus_gex_val:
                minus_gex_val = gex_val
                result.minus_gex_strike = strike

        # --- Dealer position -------------------------------------------
        if result.total_net_gex >= 0:
            result.dealer_position = "long_gamma"
        else:
            result.dealer_position = "short_gamma"

        # --- Vol trigger -----------------------------------------------
        # Vol trigger = the nearest strike to spot where net GEX flips
        # from positive to negative.  In practice it is close to the
        # gamma flip level but snapped to the nearest tradable strike.
        result.vol_trigger = self._snap_to_nearest_strike(
            result.gamma_flip_level, result.gex_by_strike
        )

        # --- Max pain --------------------------------------------------
        result.max_pain = self.compute_max_pain(chain)

        # --- Transition zone -------------------------------------------
        result.transition_zone = self.compute_transition_zone(
            result.gex_by_strike, spot,
            result.call_gex_by_strike, result.put_gex_by_strike,
        )

        # --- Persist to history ----------------------------------------
        self._history.append(result)

        return result

    # ------------------------------------------------------------------
    # Max pain
    # ------------------------------------------------------------------

    def compute_max_pain(self, chain: OptionsChain) -> float:
        """Strike where maximum open interest expires worthless.

        For each candidate strike *P*, compute the total dollar value of
        in-the-money contracts if SPX settles at *P*.  The max-pain strike
        minimises that total.
        """
        strike_map = self._group_by_strike(chain)
        if not strike_map:
            return 0.0

        # Collect OI by strike and side.
        call_oi_map: Dict[float, int] = {}
        put_oi_map: Dict[float, int] = {}
        for strike, quotes in strike_map.items():
            for q_obj in quotes:
                if q_obj.option_type == "call":
                    call_oi_map[strike] = q_obj.open_interest
                else:
                    put_oi_map[strike] = q_obj.open_interest

        all_strikes = sorted(strike_map.keys())
        if not all_strikes:
            return 0.0

        best_strike = all_strikes[0]
        best_pain = float("inf")

        for settle in all_strikes:
            total_pain = 0.0
            for k in all_strikes:
                c_oi = call_oi_map.get(k, 0)
                p_oi = put_oi_map.get(k, 0)
                # Calls ITM when settle > k
                if settle > k and c_oi > 0:
                    total_pain += (settle - k) * c_oi * _OPT_MULTIPLIER
                # Puts ITM when settle < k
                if settle < k and p_oi > 0:
                    total_pain += (k - settle) * p_oi * _OPT_MULTIPLIER
            if total_pain < best_pain:
                best_pain = total_pain
                best_strike = settle

        return best_strike

    # ------------------------------------------------------------------
    # Transition zone
    # ------------------------------------------------------------------

    def compute_transition_zone(
        self,
        gex_by_strike: Dict[float, float],
        spot: float,
        call_gex_by_strike: Optional[Dict[float, float]] = None,
        put_gex_by_strike: Optional[Dict[float, float]] = None,
    ) -> Tuple[float, float]:
        """Find range where call gamma ~ put gamma (neither dominates by 2x).

        The transition zone is the contiguous region around *spot* where
        ``|call_gex| / |put_gex| ∈ [0.5, 2.0]``.  Falls back to a symmetric
        range around the gamma-flip level if per-side data is unavailable.
        """
        if call_gex_by_strike is None or put_gex_by_strike is None:
            # Fallback: symmetric band around gamma flip.
            flip = self._interpolate_gamma_flip(gex_by_strike, spot)
            if flip <= 0:
                return (spot, spot)
            return (flip - 5.0, flip + 5.0)

        sorted_strikes = sorted(gex_by_strike.keys())
        if not sorted_strikes:
            return (spot, spot)

        lower = spot
        upper = spot

        for strike in sorted_strikes:
            abs_call = abs(call_gex_by_strike.get(strike, 0.0))
            abs_put = abs(put_gex_by_strike.get(strike, 0.0))
            denom = max(abs_put, 1e-12)
            ratio = abs_call / denom

            if 0.5 <= ratio <= 2.0:
                if strike < lower:
                    lower = strike
                if strike > upper:
                    upper = strike

        # Ensure the zone makes sense (at least the spot is inside).
        if lower > spot:
            lower = spot
        if upper < spot:
            upper = spot

        return (lower, upper)

    # ------------------------------------------------------------------
    # Signal detection
    # ------------------------------------------------------------------

    def detect_signals(
        self,
        current_gex: GEXResult,
        prior_gex: Optional[GEXResult],
        spot: float,
        vix1d: float = 0.0,
        vix1d_change_pct: float = 0.0,
    ) -> List[GEXSignal]:
        """Detect all six GEX signal types.

        1. GAMMA_FLIP_CROSSOVER  — spot crosses the gamma flip level.
        2. GAMMA_WALL_APPROACH   — spot within 3 pts of call / put wall.
        3. TRANSITION_ZONE_BREAKOUT — spot breaks above / below TZ.
        4. GEX_COLLAPSE          — total GEX drops >30 % since prior snapshot.
        5. CHARM_DRIVEN_FLOW     — net charm > threshold ES equivalents.
        6. VANNA_AMPLIFICATION   — VIX1D change >10 % and large vanna.
        """
        signals: List[GEXSignal] = []
        now = datetime.utcnow()

        # -------- 1. GAMMA_FLIP_CROSSOVER ------------------------------
        if prior_gex is not None and current_gex.gamma_flip_level > 0:
            flip = current_gex.gamma_flip_level
            prior_flip = prior_gex.gamma_flip_level if prior_gex.gamma_flip_level > 0 else flip

            # Check if spot has crossed the flip level between snapshots.
            # We use the prior GEX's flip for the "before" reference.
            crossed_up = (spot >= flip) and prior_gex.total_net_gex < 0 and current_gex.total_net_gex >= 0
            crossed_dn = (spot <= flip) and prior_gex.total_net_gex >= 0 and current_gex.total_net_gex < 0

            if crossed_up or crossed_dn:
                direction = SignalDirection.BULLISH if crossed_up else SignalDirection.BEARISH
                signals.append(GEXSignal(
                    signal_type=GEXSignalType.GAMMA_FLIP_CROSSOVER,
                    direction=direction,
                    confidence=self.config.gamma_flip_confidence,
                    trigger_price=flip,
                    target_price=current_gex.plus_gex_strike if crossed_up else current_gex.minus_gex_strike,
                    description=(
                        f"Spot {'crossed above' if crossed_up else 'crossed below'} "
                        f"gamma flip at {flip:.1f}. Dealer position now "
                        f"{current_gex.dealer_position}."
                    ),
                    timestamp=now,
                ))

        # -------- 2. GAMMA_WALL_APPROACH -------------------------------
        wall_distance = 3.0  # points
        if current_gex.call_wall > 0 and abs(spot - current_gex.call_wall) <= wall_distance:
            signals.append(GEXSignal(
                signal_type=GEXSignalType.GAMMA_WALL_APPROACH,
                direction=SignalDirection.BEARISH,  # call wall = resistance
                confidence=self.config.wall_hold_rate,
                trigger_price=current_gex.call_wall,
                target_price=current_gex.gamma_flip_level if current_gex.gamma_flip_level > 0 else None,
                description=(
                    f"Spot within {abs(spot - current_gex.call_wall):.1f} pts "
                    f"of call wall at {current_gex.call_wall:.0f}. "
                    f"Historical hold rate {self.config.wall_hold_rate:.0%}."
                ),
                timestamp=now,
            ))

        if current_gex.put_wall > 0 and abs(spot - current_gex.put_wall) <= wall_distance:
            signals.append(GEXSignal(
                signal_type=GEXSignalType.GAMMA_WALL_APPROACH,
                direction=SignalDirection.BULLISH,  # put wall = support
                confidence=self.config.wall_hold_rate,
                trigger_price=current_gex.put_wall,
                target_price=current_gex.gamma_flip_level if current_gex.gamma_flip_level > 0 else None,
                description=(
                    f"Spot within {abs(spot - current_gex.put_wall):.1f} pts "
                    f"of put wall at {current_gex.put_wall:.0f}. "
                    f"Historical hold rate {self.config.wall_hold_rate:.0%}."
                ),
                timestamp=now,
            ))

        # -------- 3. TRANSITION_ZONE_BREAKOUT --------------------------
        tz_lo, tz_hi = current_gex.transition_zone
        if tz_lo > 0 and tz_hi > 0 and tz_lo != tz_hi:
            if spot > tz_hi:
                signals.append(GEXSignal(
                    signal_type=GEXSignalType.TRANSITION_ZONE_BREAKOUT,
                    direction=SignalDirection.BULLISH,
                    confidence=0.60,
                    trigger_price=tz_hi,
                    target_price=current_gex.call_wall if current_gex.call_wall > 0 else None,
                    description=(
                        f"Spot broke above transition zone upper bound "
                        f"{tz_hi:.1f}. Dealers likely net short gamma."
                    ),
                    timestamp=now,
                ))
            elif spot < tz_lo:
                signals.append(GEXSignal(
                    signal_type=GEXSignalType.TRANSITION_ZONE_BREAKOUT,
                    direction=SignalDirection.BEARISH,
                    confidence=0.60,
                    trigger_price=tz_lo,
                    target_price=current_gex.put_wall if current_gex.put_wall > 0 else None,
                    description=(
                        f"Spot broke below transition zone lower bound "
                        f"{tz_lo:.1f}. Dealers likely net short gamma."
                    ),
                    timestamp=now,
                ))

        # -------- 4. GEX_COLLAPSE --------------------------------------
        if prior_gex is not None and abs(prior_gex.total_net_gex) > 1e-6:
            change_pct = (
                (current_gex.total_net_gex - prior_gex.total_net_gex)
                / abs(prior_gex.total_net_gex)
            )
            if change_pct < -self.config.gex_collapse_threshold_pct:
                signals.append(GEXSignal(
                    signal_type=GEXSignalType.GEX_COLLAPSE,
                    direction=SignalDirection.BEARISH,
                    confidence=min(1.0, abs(change_pct)),
                    trigger_price=spot,
                    description=(
                        f"Total GEX dropped {abs(change_pct):.0%} "
                        f"({prior_gex.total_net_gex:,.0f} -> "
                        f"{current_gex.total_net_gex:,.0f}). "
                        f"Volatility expansion likely."
                    ),
                    timestamp=now,
                ))

        # -------- 5. CHARM_DRIVEN_FLOW ---------------------------------
        charm_threshold = self.config.charm_flow_threshold_contracts
        if abs(current_gex.net_charm_exposure) > charm_threshold:
            direction = (
                SignalDirection.BULLISH
                if current_gex.net_charm_exposure > 0
                else SignalDirection.BEARISH
            )
            confidence = min(
                1.0,
                abs(current_gex.net_charm_exposure) / (charm_threshold * 2.0),
            )
            signals.append(GEXSignal(
                signal_type=GEXSignalType.CHARM_DRIVEN_FLOW,
                direction=direction,
                confidence=confidence,
                trigger_price=spot,
                description=(
                    f"Net charm exposure = {current_gex.net_charm_exposure:,.0f} "
                    f"ES equivalents ({direction.value}). "
                    f"Delta-hedging flow expected."
                ),
                timestamp=now,
            ))

        # -------- 6. VANNA_AMPLIFICATION -------------------------------
        vix_threshold = self.config.vanna_vix_change_threshold_pct
        if abs(vix1d_change_pct) > vix_threshold and abs(current_gex.net_vanna_exposure) > 0:
            # VIX dropping with positive vanna -> bullish
            # VIX rising with negative vanna -> bearish
            if vix1d_change_pct < 0 and current_gex.net_vanna_exposure > 0:
                direction = SignalDirection.BULLISH
            elif vix1d_change_pct > 0 and current_gex.net_vanna_exposure < 0:
                direction = SignalDirection.BEARISH
            elif vix1d_change_pct > 0 and current_gex.net_vanna_exposure > 0:
                direction = SignalDirection.BEARISH
            else:
                direction = SignalDirection.BULLISH

            confidence = min(
                1.0,
                abs(vix1d_change_pct) / (vix_threshold * 3.0),
            )
            signals.append(GEXSignal(
                signal_type=GEXSignalType.VANNA_AMPLIFICATION,
                direction=direction,
                confidence=confidence,
                trigger_price=spot,
                description=(
                    f"VIX1D moved {vix1d_change_pct:+.1%} "
                    f"(level {vix1d:.2f}). Net vanna exposure "
                    f"{current_gex.net_vanna_exposure:,.0f}. "
                    f"Vanna-driven hedging flow {direction.value}."
                ),
                timestamp=now,
            ))

        return signals

    # ------------------------------------------------------------------
    # GEX momentum
    # ------------------------------------------------------------------

    def get_gex_momentum(self, window_minutes: int = 15) -> float:
        """Rate of change of total net GEX over *window_minutes*.

        Returns
        -------
        float — GEX change per minute (positive = growing, negative =
        collapsing).  Returns 0.0 when insufficient history.
        """
        if len(self._history) < 2:
            return 0.0

        # Find the snapshot closest to `window_minutes` ago.
        now = self._history[-1].timestamp
        oldest_usable = None
        for snap in self._history:
            delta = (now - snap.timestamp).total_seconds()
            if delta <= window_minutes * 60.0:
                oldest_usable = snap
                break

        if oldest_usable is None or oldest_usable is self._history[-1]:
            return 0.0

        elapsed = (now - oldest_usable.timestamp).total_seconds() / 60.0
        if elapsed < 0.01:
            return 0.0

        return (self._history[-1].total_net_gex - oldest_usable.total_net_gex) / elapsed

    # ------------------------------------------------------------------
    # High-speed (gamma landmine) strikes
    # ------------------------------------------------------------------

    def get_high_speed_strikes(
        self,
        gex_result: GEXResult,
        spot: float,
        distance: float = 10.0,
    ) -> List[float]:
        """Strikes within *distance* of spot that have high speed (gamma
        landmines).

        A strike is considered a landmine when its absolute speed exposure
        is in the top quartile of all strikes within the distance window.

        Returns sorted list of landmine strikes.
        """
        candidates: List[Tuple[float, float]] = []
        for strike, spd in gex_result.net_speed_by_strike.items():
            if abs(strike - spot) <= distance:
                candidates.append((strike, abs(spd)))

        if not candidates:
            return []

        # Top-quartile threshold.
        speeds = [c[1] for c in candidates]
        speeds_arr = np.array(speeds)
        if len(speeds_arr) == 0:
            return []
        q75 = float(np.percentile(speeds_arr, 75))

        landmines = sorted(
            strike for strike, spd in candidates if spd >= q75
        )
        return landmines

    # ==================================================================
    # Private helpers
    # ==================================================================

    @staticmethod
    def _time_to_expiry(chain: OptionsChain) -> float:
        """Convert chain expiry to trading-year fraction ``T``.

        ``T = minutes_remaining / (252 * 390)``
        """
        now = datetime.utcnow()
        if chain.expiry is None:
            return _MIN_T

        remaining = (chain.expiry - now).total_seconds()
        if remaining <= 0:
            return _MIN_T

        minutes_remaining = remaining / 60.0
        T = minutes_remaining / (252.0 * 390.0)
        return max(T, _MIN_T)

    @staticmethod
    def _group_by_strike(chain: OptionsChain) -> Dict[float, List[OptionQuote]]:
        """Group chain quotes by strike price."""
        mapping: Dict[float, List[OptionQuote]] = {}
        for q_obj in chain.quotes:
            mapping.setdefault(q_obj.strike, []).append(q_obj)
        return mapping

    def _interpolate_gamma_flip(
        self,
        gex_by_strike: Dict[float, float],
        spot: float,
    ) -> float:
        """Interpolate where cumulative GEX crosses zero.

        Walk strikes from low to high, accumulate net GEX.  When the
        running sum changes sign, linearly interpolate the crossing point.
        If no crossing is found, return the spot price as a fallback.
        """
        sorted_strikes = sorted(gex_by_strike.keys())
        if len(sorted_strikes) < 2:
            return spot

        cumulative = 0.0
        prev_strike = sorted_strikes[0]
        prev_cum = gex_by_strike[prev_strike]
        cumulative = prev_cum

        for strike in sorted_strikes[1:]:
            gex_val = gex_by_strike[strike]
            new_cum = cumulative + gex_val

            # Check for a sign change in the cumulative sum.
            if cumulative * new_cum < 0:
                # Linear interpolation between prev_strike and strike.
                abs_prev = abs(cumulative)
                abs_curr = abs(new_cum)
                denom = abs_prev + abs_curr
                if denom > 0:
                    flip = prev_strike + (strike - prev_strike) * abs_prev / denom
                else:
                    flip = (prev_strike + strike) / 2.0
                return flip

            prev_strike = strike
            cumulative = new_cum

        # No crossing found — return spot.
        return spot

    @staticmethod
    def _snap_to_nearest_strike(
        value: float,
        gex_by_strike: Dict[float, float],
    ) -> float:
        """Return the strike closest to *value*."""
        if not gex_by_strike:
            return value
        return min(gex_by_strike.keys(), key=lambda k: abs(k - value))

    # ------------------------------------------------------------------
    # Black-Scholes primitives (for IV solver)
    # ------------------------------------------------------------------

    @staticmethod
    def _bs_price(
        S: float, K: float, T: float, sigma: float,
        r: float, q: float, option_type: str,
    ) -> float:
        """Black-Scholes European option price with continuous dividend."""
        if T < _MIN_T:
            T = _MIN_T
        if sigma <= 0:
            sigma = 1e-6

        sqrt_T = math.sqrt(T)
        d1 = compute_d1(S, K, T, sigma, r, q)
        d2 = d1 - sigma * sqrt_T

        disc_S = S * math.exp(-q * T)
        disc_K = K * math.exp(-r * T)

        if option_type == "call":
            return disc_S * norm_cdf(d1) - disc_K * norm_cdf(d2)
        else:
            return disc_K * norm_cdf(-d2) - disc_S * norm_cdf(-d1)

    @staticmethod
    def _bs_vega(
        S: float, K: float, T: float, sigma: float,
        r: float, q: float,
    ) -> float:
        """Black-Scholes vega (dPrice / dSigma)."""
        if T < _MIN_T:
            T = _MIN_T
        if sigma <= 0:
            sigma = 1e-6

        sqrt_T = math.sqrt(T)
        d1 = compute_d1(S, K, T, sigma, r, q)
        return S * math.exp(-q * T) * norm_pdf(d1) * sqrt_T
