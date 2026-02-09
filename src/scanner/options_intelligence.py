"""
Revolution Alpha Engine - Advanced Options Intelligence Scanner

Institutional-grade options intelligence providing:
- IV surface construction and regime classification
- Gamma exposure mapping with pin prediction
- Vanna/charm flow estimation for mechanical hedging flows
- Max pain calculation with convergence probability
- Options flow classification (smart money, whale detection)
- Integrated scanner producing AdvancedScanResult signals

Mathematical foundations:
- Black-Scholes Greeks approximation for missing data
- GEX = gamma x OI x 100 x spot^2 x 0.01 (dealer perspective)
- Vanna = dDelta/dVol, Charm = dDelta/dTime (second-order Greeks)
- IV rank/percentile for contextualizing current volatility
"""

import numpy as np
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple, Any, Literal
from dataclasses import dataclass, field
import math

from .base import BaseScanner, ScanContext, MarketData
from .models import (
    ScanResult,
    ScanMode,
    SignalDirection,
    ScannerConfig,
)
from .advanced_models import (
    AdvancedScanResult,
    ScanCategory,
    RegimeContext,
    ExpectedTimeframe,
    IVSurface,
    IVSurfacePoint,
    GreeksExposure,
)
from .options_scanner import OptionContract, OptionsChain

logger = logging.getLogger(__name__)


# =============================================================================
# Black-Scholes Utilities
# =============================================================================

def _norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function approximation."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    """Standard normal probability density function."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _bs_d1(spot: float, strike: float, t: float, r: float, sigma: float) -> float:
    """Calculate Black-Scholes d1 parameter.

    Args:
        spot: Underlying price.
        strike: Option strike price.
        t: Time to expiration in years.
        r: Risk-free interest rate.
        sigma: Implied volatility.

    Returns:
        d1 value, or 0.0 if inputs are degenerate.
    """
    if t <= 0 or sigma <= 0 or spot <= 0 or strike <= 0:
        return 0.0
    return (math.log(spot / strike) + (r + 0.5 * sigma ** 2) * t) / (sigma * math.sqrt(t))


def _bs_d2(d1: float, sigma: float, t: float) -> float:
    """Calculate Black-Scholes d2 parameter."""
    if t <= 0 or sigma <= 0:
        return 0.0
    return d1 - sigma * math.sqrt(t)


def estimate_delta(
    spot: float, strike: float, t: float, sigma: float,
    option_type: str, r: float = 0.05
) -> float:
    """Estimate option delta using Black-Scholes.

    Args:
        spot: Underlying price.
        strike: Option strike price.
        t: Time to expiration in years.
        sigma: Implied volatility.
        option_type: 'CALL' or 'PUT'.
        r: Risk-free rate (default 5%).

    Returns:
        Estimated delta.
    """
    if t <= 0:
        if option_type == "CALL":
            return 1.0 if spot > strike else 0.0
        else:
            return -1.0 if spot < strike else 0.0

    d1 = _bs_d1(spot, strike, t, r, sigma)
    if option_type == "CALL":
        return _norm_cdf(d1)
    else:
        return _norm_cdf(d1) - 1.0


def estimate_gamma(
    spot: float, strike: float, t: float, sigma: float, r: float = 0.05
) -> float:
    """Estimate option gamma using Black-Scholes.

    Args:
        spot: Underlying price.
        strike: Option strike price.
        t: Time to expiration in years.
        sigma: Implied volatility.
        r: Risk-free rate.

    Returns:
        Estimated gamma per share.
    """
    if t <= 0 or sigma <= 0 or spot <= 0:
        return 0.0
    d1 = _bs_d1(spot, strike, t, r, sigma)
    return _norm_pdf(d1) / (spot * sigma * math.sqrt(t))


def estimate_vanna(
    spot: float, strike: float, t: float, sigma: float, r: float = 0.05
) -> float:
    """Estimate option vanna (dDelta/dVol) using Black-Scholes.

    Vanna = -d2 * N'(d1) / (spot * sigma * sqrt(t))
    Equivalent to: -N'(d1) * d2 / sigma

    Args:
        spot: Underlying price.
        strike: Option strike price.
        t: Time to expiration in years.
        sigma: Implied volatility.
        r: Risk-free rate.

    Returns:
        Estimated vanna.
    """
    if t <= 0 or sigma <= 0 or spot <= 0:
        return 0.0
    d1 = _bs_d1(spot, strike, t, r, sigma)
    d2 = _bs_d2(d1, sigma, t)
    return -_norm_pdf(d1) * d2 / sigma


def estimate_charm(
    spot: float, strike: float, t: float, sigma: float,
    option_type: str, r: float = 0.05
) -> float:
    """Estimate option charm (dDelta/dTime, also called delta decay).

    For calls: charm = -N'(d1) * (2*r*t - d2*sigma*sqrt(t)) / (2*t*sigma*sqrt(t))
    Negative charm means delta is increasing as time passes (for OTM calls).

    Args:
        spot: Underlying price.
        strike: Option strike price.
        t: Time to expiration in years.
        sigma: Implied volatility.
        option_type: 'CALL' or 'PUT'.
        r: Risk-free rate.

    Returns:
        Estimated charm (dDelta/dTime) per day.
    """
    if t <= 1e-6 or sigma <= 0 or spot <= 0:
        return 0.0
    d1 = _bs_d1(spot, strike, t, r, sigma)
    d2 = _bs_d2(d1, sigma, t)
    sqrt_t = math.sqrt(t)

    # Charm for a call
    numerator = 2.0 * r * t - d2 * sigma * sqrt_t
    denominator = 2.0 * t * sigma * sqrt_t
    charm_call = -_norm_pdf(d1) * numerator / denominator

    if option_type == "CALL":
        return charm_call / 365.0  # Per day
    else:
        # Put charm = call charm + r * exp(-r*t) (via put-call parity)
        return (charm_call + r * math.exp(-r * t)) / 365.0


def _get_contract_tte(contract: OptionContract) -> float:
    """Get time to expiration in years for a contract."""
    dte = max(1, contract.days_to_expiry)
    return dte / 365.0


def _ensure_greeks(
    contract: OptionContract, underlying_price: float
) -> Tuple[float, float, float, float]:
    """Ensure delta and gamma are available, estimating via BS if missing.

    Args:
        contract: The option contract.
        underlying_price: Current underlying price.

    Returns:
        Tuple of (delta, gamma, vanna, charm).
    """
    t = _get_contract_tte(contract)
    sigma = contract.implied_volatility if contract.implied_volatility > 0 else 0.30

    delta = contract.delta
    if delta is None:
        delta = estimate_delta(
            underlying_price, contract.strike, t, sigma, contract.option_type
        )

    gamma = contract.gamma
    if gamma is None:
        gamma = estimate_gamma(underlying_price, contract.strike, t, sigma)

    vanna_val = estimate_vanna(underlying_price, contract.strike, t, sigma)
    charm_val = estimate_charm(
        underlying_price, contract.strike, t, sigma, contract.option_type
    )

    return delta, gamma, vanna_val, charm_val


# =============================================================================
# IV Surface Analyzer
# =============================================================================

class IVSurfaceAnalyzer:
    """Constructs and analyzes the implied volatility surface.

    The IV surface maps implied volatility across strikes (moneyness) and
    expirations (term structure). Surface shape reveals market expectations
    about tail risk, event pricing, and overall fear/greed.
    """

    def build_surface(
        self,
        contracts: List[OptionContract],
        underlying_price: float,
    ) -> IVSurface:
        """Build an IV surface from an options chain.

        Args:
            contracts: List of option contracts with IV data.
            underlying_price: Current price of the underlying.

        Returns:
            Populated IVSurface model with analytics computed.
        """
        points: List[IVSurfacePoint] = []

        for c in contracts:
            if c.implied_volatility <= 0 or c.strike <= 0:
                continue
            moneyness = c.strike / underlying_price
            delta, _, _, _ = _ensure_greeks(c, underlying_price)

            points.append(IVSurfacePoint(
                strike=c.strike,
                expiration=c.expiration,
                iv=c.implied_volatility,
                delta=delta,
                moneyness=moneyness,
            ))

        if not points:
            # Return a minimal surface when no valid data exists
            return IVSurface(
                symbol=contracts[0].underlying if contracts else "UNKNOWN",
                underlying_price=underlying_price,
                points=[],
                atm_vol=0.0,
                skew_25d=0.0,
                butterfly_25d=0.0,
                term_structure_slope=0.0,
                iv_rank_30=50.0,
                iv_rank_252=50.0,
                iv_percentile_30=50.0,
                iv_percentile_252=50.0,
                surface_regime="normal",
            )

        # ATM vol: weighted average of near-ATM strikes
        atm_vol = self._compute_atm_vol(points, underlying_price)

        # Skew and butterfly for the nearest expiration
        skew_25d = self.calculate_skew(points)
        butterfly_25d = self.calculate_butterfly(points)
        term_slope = self.calculate_term_structure(points)

        regime = self.detect_surface_regime_from_metrics(
            skew_25d, butterfly_25d, atm_vol
        )

        symbol = contracts[0].underlying if contracts else "UNKNOWN"

        return IVSurface(
            symbol=symbol,
            underlying_price=underlying_price,
            points=points,
            atm_vol=atm_vol,
            skew_25d=skew_25d,
            butterfly_25d=butterfly_25d,
            term_structure_slope=term_slope,
            iv_rank_30=50.0,  # Requires historical data; set externally
            iv_rank_252=50.0,
            iv_percentile_30=50.0,
            iv_percentile_252=50.0,
            surface_regime=regime,
        )

    def _compute_atm_vol(
        self, points: List[IVSurfacePoint], underlying_price: float
    ) -> float:
        """Compute ATM implied volatility as a weighted average of near-money strikes."""
        if not points:
            return 0.0

        # Weight by inverse distance to ATM
        weights = []
        ivs = []
        for p in points:
            distance = abs(p.moneyness - 1.0)
            if distance < 0.15:  # Only consider strikes within 15% of ATM
                w = 1.0 / (distance + 0.01)
                weights.append(w)
                ivs.append(p.iv)

        if not weights:
            # Fallback: use the closest strike
            closest = min(points, key=lambda p: abs(p.moneyness - 1.0))
            return closest.iv

        w_arr = np.array(weights)
        iv_arr = np.array(ivs)
        return float(np.average(iv_arr, weights=w_arr))

    def calculate_skew(
        self,
        surface: List[IVSurfacePoint],
        delta_target: float = 0.25,
    ) -> float:
        """Calculate the 25-delta risk reversal (put skew).

        Risk Reversal = 25D Put IV - 25D Call IV.
        Positive values indicate demand for downside protection (fear).
        Negative values indicate demand for upside (greed).

        Args:
            surface: List of IV surface points.
            delta_target: Target absolute delta for wing options.

        Returns:
            Skew value in volatility points.
        """
        put_iv = self._find_iv_at_delta(surface, -delta_target, side="put")
        call_iv = self._find_iv_at_delta(surface, delta_target, side="call")

        if put_iv is None or call_iv is None:
            return 0.0

        return put_iv - call_iv

    def calculate_butterfly(
        self,
        surface: List[IVSurfacePoint],
        delta_target: float = 0.25,
    ) -> float:
        """Calculate the 25-delta butterfly spread (smile curvature).

        Butterfly = 0.5 * (25D Call IV + 25D Put IV) - ATM IV.
        Measures the convexity of the smile. High butterfly indicates
        demand for wing options (tail risk hedging or event pricing).

        Args:
            surface: List of IV surface points.
            delta_target: Target absolute delta for wing options.

        Returns:
            Butterfly value in volatility points.
        """
        put_iv = self._find_iv_at_delta(surface, -delta_target, side="put")
        call_iv = self._find_iv_at_delta(surface, delta_target, side="call")

        # ATM is approximately 50 delta
        atm_points = [p for p in surface if p.delta is not None and abs(abs(p.delta) - 0.50) < 0.15]
        if not atm_points:
            atm_points = [p for p in surface if abs(p.moneyness - 1.0) < 0.05]

        if put_iv is None or call_iv is None or not atm_points:
            return 0.0

        atm_iv = float(np.mean([p.iv for p in atm_points]))
        return 0.5 * (call_iv + put_iv) - atm_iv

    def calculate_term_structure(
        self, surface: List[IVSurfacePoint]
    ) -> float:
        """Calculate the slope of the IV term structure for ATM options.

        A positive slope (contango) is normal; backwardation signals
        near-term event risk or elevated short-dated demand.

        Args:
            surface: List of IV surface points.

        Returns:
            Slope of IV vs DTE regression (vol points per day).
        """
        # Filter to near-ATM options
        atm_points = [p for p in surface if abs(p.moneyness - 1.0) < 0.10]
        if len(atm_points) < 2:
            return 0.0

        now = datetime.utcnow()
        dtes = []
        ivs = []
        for p in atm_points:
            dte = max(1, (p.expiration - now).days)
            dtes.append(dte)
            ivs.append(p.iv)

        dtes_arr = np.array(dtes, dtype=float)
        ivs_arr = np.array(ivs, dtype=float)

        # Guard against all-same DTE
        if np.std(dtes_arr) < 1e-6:
            return 0.0

        # Linear regression slope
        coeffs = np.polyfit(dtes_arr, ivs_arr, 1)
        return float(coeffs[0])

    def detect_surface_regime(
        self, surface: IVSurface
    ) -> Literal["fear", "complacency", "uncertainty", "normal"]:
        """Classify the IV surface regime from a constructed IVSurface object.

        Args:
            surface: An IVSurface model instance.

        Returns:
            Surface regime classification string.
        """
        return self.detect_surface_regime_from_metrics(
            surface.skew_25d, surface.butterfly_25d, surface.atm_vol
        )

    def detect_surface_regime_from_metrics(
        self,
        skew: float,
        butterfly: float,
        atm_vol: float,
    ) -> Literal["fear", "complacency", "uncertainty", "normal"]:
        """Classify IV surface regime from computed metrics.

        Regime definitions:
        - Fear: steep put skew (>5 vol pts) + elevated ATM vol (>30%)
        - Complacency: flat skew (<2 vol pts) + low ATM vol (<15%)
        - Uncertainty: high butterfly (>3 vol pts), demand for tails
        - Normal: everything else

        Args:
            skew: 25-delta risk reversal.
            butterfly: 25-delta butterfly.
            atm_vol: ATM implied volatility.

        Returns:
            Regime classification.
        """
        if skew > 0.05 and atm_vol > 0.30:
            return "fear"
        if abs(skew) < 0.02 and atm_vol < 0.15:
            return "complacency"
        if butterfly > 0.03:
            return "uncertainty"
        return "normal"

    def detect_arbitrage(
        self, surface: List[IVSurfacePoint]
    ) -> List[Dict[str, Any]]:
        """Detect potential arbitrage violations on the IV surface.

        Checks for:
        1. Calendar spread violations: shorter DTE with higher IV than
           longer DTE at the same strike (in a risk-neutral world,
           IV should generally increase or be flat with maturity for
           the same moneyness).
        2. Butterfly violations: non-convex smile at a given expiration
           (IV should form a convex smile across strikes).

        Args:
            surface: List of IV surface points.

        Returns:
            List of arbitrage violation descriptions.
        """
        violations: List[Dict[str, Any]] = []

        # Group by strike for calendar checks
        by_strike: Dict[float, List[IVSurfacePoint]] = {}
        for p in surface:
            by_strike.setdefault(p.strike, []).append(p)

        now = datetime.utcnow()

        for strike, pts in by_strike.items():
            if len(pts) < 2:
                continue
            sorted_pts = sorted(pts, key=lambda x: (x.expiration - now).days)
            for i in range(len(sorted_pts) - 1):
                near = sorted_pts[i]
                far = sorted_pts[i + 1]
                near_dte = max(1, (near.expiration - now).days)
                far_dte = max(1, (far.expiration - now).days)
                # Total variance should increase with time
                near_var = near.iv ** 2 * (near_dte / 365.0)
                far_var = far.iv ** 2 * (far_dte / 365.0)
                if near_var > far_var * 1.02:  # 2% tolerance
                    violations.append({
                        "type": "calendar_spread",
                        "strike": strike,
                        "near_dte": near_dte,
                        "far_dte": far_dte,
                        "near_iv": near.iv,
                        "far_iv": far.iv,
                        "severity": (near_var - far_var) / far_var if far_var > 0 else 0,
                    })

        # Group by expiration for butterfly checks
        by_expiry: Dict[datetime, List[IVSurfacePoint]] = {}
        for p in surface:
            by_expiry.setdefault(p.expiration, []).append(p)

        for exp, pts in by_expiry.items():
            if len(pts) < 3:
                continue
            sorted_pts = sorted(pts, key=lambda x: x.strike)
            for i in range(1, len(sorted_pts) - 1):
                left = sorted_pts[i - 1]
                mid = sorted_pts[i]
                right = sorted_pts[i + 1]
                # Check convexity: mid IV should be <= average of neighbors
                wing_avg = 0.5 * (left.iv + right.iv)
                if mid.iv > wing_avg * 1.03:  # 3% tolerance
                    violations.append({
                        "type": "butterfly",
                        "expiration": exp.isoformat(),
                        "strikes": [left.strike, mid.strike, right.strike],
                        "ivs": [left.iv, mid.iv, right.iv],
                        "severity": (mid.iv - wing_avg) / wing_avg if wing_avg > 0 else 0,
                    })

        return violations

    @staticmethod
    def iv_rank(current_iv: float, historical_ivs: List[float]) -> float:
        """Calculate IV Rank: where current IV sits relative to its range.

        IV Rank = (Current IV - 52w Low IV) / (52w High IV - 52w Low IV) * 100

        Args:
            current_iv: Current implied volatility.
            historical_ivs: List of historical IV values.

        Returns:
            IV Rank as a percentage (0-100).
        """
        if not historical_ivs:
            return 50.0
        iv_min = min(historical_ivs)
        iv_max = max(historical_ivs)
        if iv_max == iv_min:
            return 50.0
        rank = ((current_iv - iv_min) / (iv_max - iv_min)) * 100.0
        return float(np.clip(rank, 0.0, 100.0))

    @staticmethod
    def iv_percentile(current_iv: float, historical_ivs: List[float]) -> float:
        """Calculate IV Percentile: percentage of days IV was lower.

        More robust than IV rank as it is not distorted by outliers.

        Args:
            current_iv: Current implied volatility.
            historical_ivs: List of historical IV values.

        Returns:
            IV Percentile as a percentage (0-100).
        """
        if not historical_ivs:
            return 50.0
        count_below = sum(1 for iv in historical_ivs if iv < current_iv)
        return (count_below / len(historical_ivs)) * 100.0

    def _find_iv_at_delta(
        self,
        points: List[IVSurfacePoint],
        target_delta: float,
        side: str = "call",
    ) -> Optional[float]:
        """Find IV at a target delta by interpolating nearby points.

        Args:
            points: Surface points with delta values.
            target_delta: Target delta value (negative for puts).
            side: 'call' or 'put' to filter option type.

        Returns:
            Interpolated IV or None if insufficient data.
        """
        # Filter by side using delta sign
        if side == "put":
            filtered = [p for p in points if p.delta is not None and p.delta < 0]
        else:
            filtered = [p for p in points if p.delta is not None and p.delta > 0]

        if not filtered:
            return None

        # Find the two closest points to the target delta
        sorted_by_delta = sorted(filtered, key=lambda p: abs(p.delta - target_delta))
        closest = sorted_by_delta[0]

        if len(sorted_by_delta) >= 2:
            second = sorted_by_delta[1]
            # Linear interpolation between two closest points
            d_diff = abs(closest.delta - second.delta)
            if d_diff > 1e-6:
                w1 = abs(second.delta - target_delta) / d_diff
                w2 = abs(closest.delta - target_delta) / d_diff
                return w1 * closest.iv + w2 * second.iv
            return closest.iv

        return closest.iv


# =============================================================================
# Gamma Exposure Mapper
# =============================================================================

class GammaExposureMapper:
    """Maps dealer gamma exposure across strikes to identify key levels.

    Market makers who sell options to customers must continuously delta-hedge.
    When dealers are long gamma, they buy dips and sell rips (stabilizing).
    When dealers are short gamma, they sell dips and buy rips (destabilizing).

    The gamma flip level and gamma walls are critical for understanding
    intraday price dynamics and expected pinning behavior.
    """

    def calculate_gex(
        self,
        contracts: List[OptionContract],
        underlying_price: float,
    ) -> Dict[float, float]:
        """Calculate Gamma Exposure (GEX) at each strike.

        GEX = gamma x OI x 100 x spot^2 x 0.01

        Convention: dealers are assumed to be short options that customers
        buy. Customer call buying means dealers are short calls (negative
        gamma from dealer perspective, but the standard GEX convention
        counts call GEX as positive because dealers hedge by buying the
        underlying as price rises). Put GEX is negative because as price
        falls, dealers who are short puts must sell the underlying.

        Args:
            contracts: List of option contracts.
            underlying_price: Current underlying price.

        Returns:
            Dictionary mapping strike -> net GEX in dollar terms.
        """
        gex_by_strike: Dict[float, float] = {}

        for c in contracts:
            if c.open_interest <= 0:
                continue

            _, gamma, _, _ = _ensure_greeks(c, underlying_price)
            if gamma <= 0:
                continue

            # GEX formula: gamma * OI * 100 shares * spot^2 * 0.01
            raw_gex = gamma * c.open_interest * 100 * (underlying_price ** 2) * 0.01

            # Sign convention: calls positive, puts negative (dealer perspective)
            if c.option_type == "PUT":
                raw_gex = -raw_gex

            strike = c.strike
            gex_by_strike[strike] = gex_by_strike.get(strike, 0.0) + raw_gex

        return gex_by_strike

    def find_gamma_flip(
        self,
        gex_by_strike: Dict[float, float],
        underlying_price: float,
    ) -> Optional[float]:
        """Find the price level where cumulative GEX flips sign.

        Above the gamma flip, dealers are long gamma (stabilizing).
        Below the gamma flip, dealers are short gamma (destabilizing).
        The flip level acts as a regime boundary for intraday behavior.

        Args:
            gex_by_strike: GEX values by strike price.
            underlying_price: Current underlying price.

        Returns:
            Gamma flip strike price, or None if not found.
        """
        if not gex_by_strike:
            return None

        strikes = sorted(gex_by_strike.keys())

        # Calculate cumulative GEX from below
        cumulative = 0.0
        prev_strike = None
        prev_cum = None

        for strike in strikes:
            cumulative += gex_by_strike[strike]

            # Detect sign change in cumulative GEX
            if prev_cum is not None and prev_cum * cumulative < 0:
                # Linear interpolation to find exact flip point
                if abs(cumulative - prev_cum) > 1e-10:
                    frac = abs(prev_cum) / abs(cumulative - prev_cum)
                    flip = prev_strike + frac * (strike - prev_strike)
                    return round(flip, 2)

            prev_strike = strike
            prev_cum = cumulative

        return None

    def find_gamma_walls(
        self,
        gex_by_strike: Dict[float, float],
        threshold_percentile: float = 90.0,
    ) -> List[Dict[str, Any]]:
        """Identify strikes with massive GEX concentrations (gamma walls).

        Gamma walls act as strong support/resistance. Price tends to be
        attracted toward large positive GEX strikes (pinning) and repelled
        from large negative GEX strikes.

        Args:
            gex_by_strike: GEX values by strike price.
            threshold_percentile: Percentile threshold for wall detection.

        Returns:
            List of gamma wall descriptors sorted by absolute GEX.
        """
        if not gex_by_strike:
            return []

        abs_values = [abs(v) for v in gex_by_strike.values()]
        threshold = float(np.percentile(abs_values, threshold_percentile))

        walls: List[Dict[str, Any]] = []
        for strike, gex in gex_by_strike.items():
            if abs(gex) >= threshold and threshold > 0:
                walls.append({
                    "strike": strike,
                    "gex": round(gex, 2),
                    "type": "call_wall" if gex > 0 else "put_wall",
                    "role": "resistance" if gex > 0 else "support",
                    "strength": round(abs(gex) / threshold, 2),
                })

        walls.sort(key=lambda w: abs(w["gex"]), reverse=True)
        return walls

    def predict_pin(
        self,
        gex_by_strike: Dict[float, float],
        max_pain: Optional[float],
    ) -> Optional[float]:
        """Predict the most likely expiration pin level.

        Combines the strike with peak positive GEX (maximum pinning force)
        and max pain level. The pin prediction is a weighted average
        of these two forces.

        Args:
            gex_by_strike: GEX values by strike.
            max_pain: Max pain strike if calculated.

        Returns:
            Predicted pin level or None.
        """
        if not gex_by_strike:
            return max_pain

        # Find strike with maximum positive GEX (strongest pinning)
        positive_gex = {k: v for k, v in gex_by_strike.items() if v > 0}
        if not positive_gex:
            return max_pain

        max_gex_strike = max(positive_gex, key=positive_gex.get)

        if max_pain is None:
            return max_gex_strike

        # Weighted average: GEX pin gets 60% weight, max pain 40%
        return round(0.6 * max_gex_strike + 0.4 * max_pain, 2)


# =============================================================================
# Vanna/Charm Mapper
# =============================================================================

class VannaCharmMapper:
    """Estimates mechanical hedging flows from vanna and charm exposure.

    Vanna (dDelta/dVol): When IV drops, positive vanna positions
    lose delta, forcing dealers to buy the underlying. This creates a
    tailwind during vol compression and a headwind during vol expansion.

    Charm (dDelta/dTime): As time passes, OTM option deltas decay
    toward zero and ITM option deltas decay toward 1 (or -1 for puts).
    This creates predictable end-of-day hedging flows.
    """

    def calculate_vanna_exposure(
        self,
        contracts: List[OptionContract],
        underlying_price: float,
    ) -> Dict[float, float]:
        """Calculate aggregate vanna exposure by strike.

        Positive net vanna means a vol decline forces dealers to buy
        stock (bullish flow). Negative net vanna means vol decline
        forces selling.

        Args:
            contracts: List of option contracts.
            underlying_price: Current underlying price.

        Returns:
            Dictionary mapping strike -> net vanna exposure.
        """
        vanna_by_strike: Dict[float, float] = {}

        for c in contracts:
            if c.open_interest <= 0:
                continue

            _, _, vanna_val, _ = _ensure_greeks(c, underlying_price)

            # Scale by OI and contract multiplier
            # Dealer is short the option, so their vanna is negated
            net_vanna = -vanna_val * c.open_interest * 100

            strike = c.strike
            vanna_by_strike[strike] = vanna_by_strike.get(strike, 0.0) + net_vanna

        return vanna_by_strike

    def calculate_charm_exposure(
        self,
        contracts: List[OptionContract],
        underlying_price: float,
    ) -> Dict[float, float]:
        """Calculate aggregate charm exposure by strike.

        Charm tells us how delta changes with the passage of time.
        Positive net charm at a strike means delta is increasing as
        expiration approaches, requiring dealers to sell underlying.

        Args:
            contracts: List of option contracts.
            underlying_price: Current underlying price.

        Returns:
            Dictionary mapping strike -> net charm exposure.
        """
        charm_by_strike: Dict[float, float] = {}

        for c in contracts:
            if c.open_interest <= 0:
                continue

            _, _, _, charm_val = _ensure_greeks(c, underlying_price)

            # Dealer is short the option; their charm exposure is negated
            net_charm = -charm_val * c.open_interest * 100

            strike = c.strike
            charm_by_strike[strike] = charm_by_strike.get(strike, 0.0) + net_charm

        return charm_by_strike

    def predict_eod_flow(
        self, charm_by_strike: Dict[float, float]
    ) -> Dict[str, Any]:
        """Predict end-of-day hedging direction from charm exposure.

        Aggregate charm across all strikes to determine net directional
        pressure from delta decay hedging at market close.

        Args:
            charm_by_strike: Charm exposure by strike.

        Returns:
            Dictionary with flow prediction details.
        """
        if not charm_by_strike:
            return {
                "direction": "neutral",
                "magnitude": 0.0,
                "net_charm": 0.0,
                "description": "Insufficient charm data",
            }

        net_charm = sum(charm_by_strike.values())
        magnitude = abs(net_charm)

        # Positive net charm = dealers need to buy stock into close
        # Negative net charm = dealers need to sell stock into close
        if net_charm > 0:
            direction = "bullish"
            description = (
                f"Charm-driven EOD buying pressure: dealers need to buy "
                f"~{magnitude:,.0f} delta shares as time decay shifts positioning"
            )
        elif net_charm < 0:
            direction = "bearish"
            description = (
                f"Charm-driven EOD selling pressure: dealers need to sell "
                f"~{magnitude:,.0f} delta shares as time decay shifts positioning"
            )
        else:
            direction = "neutral"
            description = "Charm exposure is balanced; no significant EOD flow expected"

        return {
            "direction": direction,
            "magnitude": magnitude,
            "net_charm": net_charm,
            "description": description,
        }


# =============================================================================
# Max Pain Calculator
# =============================================================================

class MaxPainCalculator:
    """Calculates the maximum pain strike for option expiration.

    Max pain is the strike price where the total dollar value of
    outstanding options would cause the greatest financial loss to
    option holders (and thus maximum profit for option writers/dealers).

    Price tends to gravitate toward max pain near expiration due to
    dealer hedging dynamics (gamma pinning).
    """

    def calculate_max_pain(
        self,
        calls_oi: Dict[float, int],
        puts_oi: Dict[float, int],
        strikes: List[float],
    ) -> Optional[float]:
        """Find the strike where total option holder losses are maximized.

        At each candidate strike, calculate:
        - Call holder losses: sum of max(0, strike_i - candidate) * call_OI_i
          for each call strike_i < candidate
        - Put holder losses: sum of max(0, candidate - strike_j) * put_OI_j
          for each put strike_j > candidate

        The max pain strike minimizes total option holder value (ITM amount).

        Args:
            calls_oi: Dictionary mapping strike -> call open interest.
            puts_oi: Dictionary mapping strike -> put open interest.
            strikes: List of all strike prices to evaluate.

        Returns:
            Max pain strike price, or None if insufficient data.
        """
        if not strikes or (not calls_oi and not puts_oi):
            return None

        sorted_strikes = sorted(set(strikes))
        min_pain = float('inf')
        max_pain_strike = sorted_strikes[0]

        for candidate in sorted_strikes:
            total_pain = 0.0

            # Pain from calls: value for call holders if underlying at candidate
            for strike, oi in calls_oi.items():
                if candidate > strike:
                    total_pain += (candidate - strike) * oi * 100

            # Pain from puts: value for put holders if underlying at candidate
            for strike, oi in puts_oi.items():
                if candidate < strike:
                    total_pain += (strike - candidate) * oi * 100

            if total_pain < min_pain:
                min_pain = total_pain
                max_pain_strike = candidate

        return max_pain_strike

    def pin_probability(
        self,
        max_pain: float,
        current_price: float,
        days_to_expiry: int,
        iv: float,
    ) -> float:
        """Estimate the probability of price converging to max pain.

        Uses a simplified model based on the distance to max pain
        relative to expected move (IV-derived) and time remaining.
        Pin probability increases as expiration approaches and as
        the distance to max pain decreases.

        Args:
            max_pain: Max pain strike price.
            current_price: Current underlying price.
            days_to_expiry: Trading days until expiration.
            iv: Annualized implied volatility.

        Returns:
            Estimated pin probability as a percentage (0-100).
        """
        if current_price <= 0 or iv <= 0 or days_to_expiry <= 0:
            return 0.0

        # Expected move = spot * IV * sqrt(DTE/252)
        expected_move = current_price * iv * math.sqrt(days_to_expiry / 252.0)

        if expected_move <= 0:
            return 0.0

        distance = abs(current_price - max_pain)
        distance_ratio = distance / expected_move

        # Base probability decays with distance
        # At 0 distance: ~60% pin probability
        # At 1 expected move: ~15% pin probability
        base_prob = 60.0 * math.exp(-2.0 * distance_ratio)

        # Time adjustment: higher probability closer to expiration
        if days_to_expiry <= 1:
            time_factor = 1.5
        elif days_to_expiry <= 3:
            time_factor = 1.2
        elif days_to_expiry <= 5:
            time_factor = 1.0
        elif days_to_expiry <= 10:
            time_factor = 0.7
        else:
            time_factor = 0.4

        probability = base_prob * time_factor
        return float(np.clip(probability, 0.0, 95.0))


# =============================================================================
# Options Flow Classifier
# =============================================================================

@dataclass
class ClassifiedTrade:
    """A classified options trade with intent analysis."""
    contract: OptionContract
    premium: float
    is_opening: bool
    is_buyer_initiated: bool
    is_institutional: bool
    smart_money_score: float
    classification: str  # "opening_buy", "opening_sell", "closing_buy", "closing_sell"


class OptionsFlowClassifier:
    """Classifies individual options trades to determine intent.

    Analyzes trade execution relative to bid/ask, size relative to
    normal flow, and volume vs. open interest to determine:
    - Opening vs. closing position
    - Buyer vs. seller initiated
    - Institutional vs. retail sizing
    """

    def classify_trade(
        self,
        volume: int,
        open_interest: int,
        price_vs_bid_ask: float,
        trade_size: int,
    ) -> Dict[str, Any]:
        """Classify a single trade based on execution characteristics.

        Args:
            volume: Total volume for the contract today.
            open_interest: Prior day open interest.
            price_vs_bid_ask: Trade price position in bid-ask range.
                0.0 = at bid, 0.5 = mid, 1.0 = at ask.
            trade_size: Number of contracts in this trade.

        Returns:
            Dictionary with classification details.
        """
        # Opening vs. closing
        # If volume exceeds OI, new positions are being opened
        is_opening = volume > open_interest * 0.5

        # Buyer vs. seller initiated
        # Trades above mid are buyer-initiated, below mid are seller-initiated
        is_buyer_initiated = price_vs_bid_ask > 0.5

        # Institutional vs. retail
        # Institutional trades tend to be larger blocks
        is_institutional = trade_size >= 50

        # Determine classification string
        open_close = "opening" if is_opening else "closing"
        buy_sell = "buy" if is_buyer_initiated else "sell"
        classification = f"{open_close}_{buy_sell}"

        # Calculate a conviction score
        conviction = 0.0

        # Strong buyer: at or above ask
        if price_vs_bid_ask >= 0.8:
            conviction += 30.0
        elif price_vs_bid_ask >= 0.6:
            conviction += 15.0
        # Strong seller: at or below bid
        elif price_vs_bid_ask <= 0.2:
            conviction += 30.0
        elif price_vs_bid_ask <= 0.4:
            conviction += 15.0

        # Size contribution
        if trade_size >= 500:
            conviction += 30.0
        elif trade_size >= 100:
            conviction += 20.0
        elif trade_size >= 50:
            conviction += 10.0

        # Opening positions are more informative than closing
        if is_opening:
            conviction += 20.0

        # Volume surge relative to OI
        if open_interest > 0:
            vol_oi = volume / open_interest
            if vol_oi > 2.0:
                conviction += 20.0
            elif vol_oi > 1.0:
                conviction += 10.0

        conviction = min(100.0, conviction)

        return {
            "is_opening": is_opening,
            "is_buyer_initiated": is_buyer_initiated,
            "is_institutional": is_institutional,
            "classification": classification,
            "conviction": conviction,
        }

    def calculate_smart_money_score(
        self, trades: List[ClassifiedTrade]
    ) -> float:
        """Calculate an aggregate smart money score from classified trades.

        Weights institutional opening trades higher. Buyer-initiated
        trades above the ask receive extra weight. The score reflects
        the degree to which informed, directional money is entering.

        Args:
            trades: List of classified trades.

        Returns:
            Smart money score from 0.0 to 100.0.
        """
        if not trades:
            return 0.0

        total_premium = sum(t.premium for t in trades)
        if total_premium <= 0:
            return 0.0

        weighted_score = 0.0
        for t in trades:
            weight = t.premium / total_premium

            base = t.smart_money_score

            # Institutional opening trades are highest signal
            if t.is_institutional and t.is_opening:
                base *= 1.5

            # Buyer-initiated adds conviction
            if t.is_buyer_initiated:
                base *= 1.2

            weighted_score += base * weight

        return float(np.clip(weighted_score, 0.0, 100.0))

    def detect_whale_activity(
        self,
        trades: List[ClassifiedTrade],
        threshold: int = 1_000_000,
    ) -> List[Dict[str, Any]]:
        """Flag large premium trades that indicate whale/institutional activity.

        Args:
            trades: List of classified trades.
            threshold: Minimum premium in dollars to flag as whale activity.

        Returns:
            List of whale trade descriptors.
        """
        whales: List[Dict[str, Any]] = []

        for t in trades:
            if t.premium >= threshold:
                whales.append({
                    "symbol": t.contract.underlying,
                    "strike": t.contract.strike,
                    "expiration": t.contract.expiration.isoformat(),
                    "option_type": t.contract.option_type,
                    "premium": round(t.premium, 2),
                    "classification": t.classification,
                    "is_institutional": t.is_institutional,
                    "is_opening": t.is_opening,
                    "is_buyer_initiated": t.is_buyer_initiated,
                    "smart_money_score": round(t.smart_money_score, 2),
                    "alert_level": (
                        "critical" if t.premium >= threshold * 5
                        else "high" if t.premium >= threshold * 2
                        else "elevated"
                    ),
                })

        whales.sort(key=lambda w: w["premium"], reverse=True)
        return whales


# =============================================================================
# Options Intelligence Scanner
# =============================================================================

class OptionsIntelligenceScanner(BaseScanner[AdvancedScanResult]):
    """Advanced options intelligence scanner producing institutional-grade signals.

    Integrates IV surface analysis, gamma exposure mapping, vanna/charm flow
    estimation, max pain calculation, and options flow classification into a
    unified scanner that produces AdvancedScanResult signals.

    Signal generation triggers:
    - Extreme skew detected (fear/greed pricing in options market)
    - Gamma squeeze setup (negative GEX + heavy call buying)
    - Significant vanna/charm mechanical flow expected
    - IV rank at extremes (>80 or <20)
    - Unusual whale activity detected
    """

    def __init__(self, config: Optional[ScannerConfig] = None):
        super().__init__(
            name="options_intelligence",
            scan_mode=ScanMode.OPTIONS_DAY,
            config=config,
        )
        self.iv_analyzer = IVSurfaceAnalyzer()
        self.gex_mapper = GammaExposureMapper()
        self.vanna_charm_mapper = VannaCharmMapper()
        self.max_pain_calc = MaxPainCalculator()
        self.flow_classifier = OptionsFlowClassifier()

    async def scan(self, context: ScanContext) -> List[AdvancedScanResult]:
        """Execute the full options intelligence scan across all symbols.

        For each symbol with options data, this method:
        1. Builds the IV surface and analyzes skew/term structure.
        2. Maps gamma exposure and identifies key levels.
        3. Calculates vanna/charm exposure for flow prediction.
        4. Calculates max pain.
        5. Classifies options flow for smart money detection.
        6. Generates AdvancedScanResult when actionable signals emerge.

        Args:
            context: ScanContext with market data, options data, and universe.

        Returns:
            List of AdvancedScanResult signals.
        """
        results: List[AdvancedScanResult] = []

        for symbol in context.universe:
            try:
                symbol_results = await self._scan_symbol(symbol, context)
                results.extend(symbol_results)
            except Exception as e:
                self._logger.warning(
                    f"Error scanning {symbol} for options intelligence: {e}",
                    exc_info=True,
                )

        # Sort by confidence descending
        results.sort(key=lambda r: r.confidence, reverse=True)
        return results

    async def _scan_symbol(
        self, symbol: str, context: ScanContext
    ) -> List[AdvancedScanResult]:
        """Run the full options intelligence pipeline for a single symbol.

        Args:
            symbol: Ticker symbol to analyze.
            context: Scan context.

        Returns:
            List of AdvancedScanResult (may be empty if no signals).
        """
        options_data = context.options_data.get(symbol)
        if not options_data:
            return []

        market_data = context.market_data.get(symbol)
        underlying_price = (
            market_data.close if market_data
            else options_data.get("underlying_price", 0)
        )
        if underlying_price <= 0:
            return []

        # Build options chain
        chain = self._build_chain(symbol, options_data, underlying_price)
        if not chain or not chain.contracts:
            return []

        # Step 1: IV Surface
        surface = self.iv_analyzer.build_surface(chain.contracts, underlying_price)

        # Compute IV rank/percentile if historical data available
        historical_ivs = options_data.get("historical_ivs", [])
        current_iv = surface.atm_vol
        iv_rank_val = IVSurfaceAnalyzer.iv_rank(current_iv, historical_ivs)
        iv_pct_val = IVSurfaceAnalyzer.iv_percentile(current_iv, historical_ivs)

        # Update surface with computed ranks
        surface.iv_rank_30 = iv_rank_val
        surface.iv_rank_252 = iv_rank_val
        surface.iv_percentile_30 = iv_pct_val
        surface.iv_percentile_252 = iv_pct_val

        # Step 2: Gamma Exposure
        gex_by_strike = self.gex_mapper.calculate_gex(chain.contracts, underlying_price)
        gamma_flip = self.gex_mapper.find_gamma_flip(gex_by_strike, underlying_price)
        gamma_walls = self.gex_mapper.find_gamma_walls(gex_by_strike)
        net_gex = sum(gex_by_strike.values()) if gex_by_strike else 0.0

        # Step 3: Vanna/Charm
        vanna_by_strike = self.vanna_charm_mapper.calculate_vanna_exposure(
            chain.contracts, underlying_price
        )
        charm_by_strike = self.vanna_charm_mapper.calculate_charm_exposure(
            chain.contracts, underlying_price
        )
        eod_flow = self.vanna_charm_mapper.predict_eod_flow(charm_by_strike)
        net_vanna = sum(vanna_by_strike.values()) if vanna_by_strike else 0.0
        net_charm = eod_flow.get("net_charm", 0.0)

        # Step 4: Max Pain
        calls_oi: Dict[float, int] = {}
        puts_oi: Dict[float, int] = {}
        all_strikes: List[float] = []

        for c in chain.contracts:
            all_strikes.append(c.strike)
            if c.option_type == "CALL":
                calls_oi[c.strike] = calls_oi.get(c.strike, 0) + c.open_interest
            else:
                puts_oi[c.strike] = puts_oi.get(c.strike, 0) + c.open_interest

        max_pain = self.max_pain_calc.calculate_max_pain(calls_oi, puts_oi, all_strikes)
        pin_prob = 0.0
        if max_pain is not None and current_iv > 0:
            nearest_dte = self._get_nearest_dte(chain.contracts)
            pin_prob = self.max_pain_calc.pin_probability(
                max_pain, underlying_price, nearest_dte, current_iv
            )

        # Predicted pin from GEX + max pain
        predicted_pin = self.gex_mapper.predict_pin(gex_by_strike, max_pain)

        # Step 5: Flow Classification
        classified_trades = self._classify_chain_flow(chain)
        smart_money_score = self.flow_classifier.calculate_smart_money_score(
            classified_trades
        )
        whale_trades = self.flow_classifier.detect_whale_activity(classified_trades)

        # Step 6: Build Greeks exposure model
        max_gex_strike = (
            max(gex_by_strike, key=lambda k: abs(gex_by_strike[k]))
            if gex_by_strike else underlying_price
        )

        gamma_regime: Literal["long_gamma", "short_gamma", "neutral"]
        if net_gex > 0:
            gamma_regime = "long_gamma"
        elif net_gex < 0:
            gamma_regime = "short_gamma"
        else:
            gamma_regime = "neutral"

        greeks_exposure = GreeksExposure(
            symbol=symbol,
            net_gamma=net_gex,
            net_delta=0.0,  # Would require full delta aggregation
            net_vanna=net_vanna,
            net_charm=net_charm,
            gamma_flip_level=gamma_flip,
            max_gamma_strike=max_gex_strike,
            gamma_walls=[w for w in gamma_walls[:5]],
            gamma_regime=gamma_regime,
            expected_pin=predicted_pin,
        )

        # Step 7: Signal Generation
        signals = self._generate_signals(
            symbol=symbol,
            underlying_price=underlying_price,
            surface=surface,
            iv_rank_val=iv_rank_val,
            iv_pct_val=iv_pct_val,
            gex_by_strike=gex_by_strike,
            net_gex=net_gex,
            gamma_flip=gamma_flip,
            gamma_walls=gamma_walls,
            greeks_exposure=greeks_exposure,
            eod_flow=eod_flow,
            net_vanna=net_vanna,
            max_pain=max_pain,
            pin_prob=pin_prob,
            predicted_pin=predicted_pin,
            smart_money_score=smart_money_score,
            whale_trades=whale_trades,
            chain=chain,
            context=context,
        )

        return signals

    def _generate_signals(
        self,
        symbol: str,
        underlying_price: float,
        surface: IVSurface,
        iv_rank_val: float,
        iv_pct_val: float,
        gex_by_strike: Dict[float, float],
        net_gex: float,
        gamma_flip: Optional[float],
        gamma_walls: List[Dict[str, Any]],
        greeks_exposure: GreeksExposure,
        eod_flow: Dict[str, Any],
        net_vanna: float,
        max_pain: Optional[float],
        pin_prob: float,
        predicted_pin: Optional[float],
        smart_money_score: float,
        whale_trades: List[Dict[str, Any]],
        chain: OptionsChain,
        context: ScanContext,
    ) -> List[AdvancedScanResult]:
        """Generate AdvancedScanResult signals based on options intelligence.

        Signal triggers:
        1. Extreme skew (fear/greed in options market)
        2. Gamma squeeze setup (negative GEX + call buying)
        3. Significant vanna/charm flow
        4. Extreme IV rank (>80 or <20)
        5. Unusual whale activity

        Args:
            All computed options intelligence metrics.

        Returns:
            List of generated signals.
        """
        signals: List[AdvancedScanResult] = []

        # Determine market regime context
        regime_context = self._determine_regime(context, surface)

        # Shared metadata
        base_metadata = {
            "iv_surface": {
                "atm_vol": round(surface.atm_vol, 4),
                "skew_25d": round(surface.skew_25d, 4),
                "butterfly_25d": round(surface.butterfly_25d, 4),
                "term_structure_slope": round(surface.term_structure_slope, 6),
                "surface_regime": surface.surface_regime,
            },
            "gamma_exposure": {
                "net_gex": round(net_gex, 2),
                "gamma_flip": gamma_flip,
                "gamma_walls_count": len(gamma_walls),
                "gamma_regime": greeks_exposure.gamma_regime,
                "predicted_pin": predicted_pin,
            },
            "flow": {
                "smart_money_score": round(smart_money_score, 2),
                "whale_count": len(whale_trades),
                "put_call_ratio": round(chain.put_call_ratio, 3),
            },
            "max_pain": max_pain,
            "pin_probability": round(pin_prob, 2),
            "eod_flow_direction": eod_flow.get("direction", "neutral"),
            "iv_rank": round(iv_rank_val, 2),
            "iv_percentile": round(iv_pct_val, 2),
        }

        # --- Signal 1: Extreme Skew ---
        if abs(surface.skew_25d) > 0.04:
            direction = "BEARISH" if surface.skew_25d > 0 else "BULLISH"
            confidence = min(0.85, 0.50 + abs(surface.skew_25d) * 3.0)
            strength = min(1.0, abs(surface.skew_25d) * 5.0)

            evidence_for = []
            evidence_against = []

            if surface.skew_25d > 0.05:
                evidence_for.append(
                    f"Steep put skew at {surface.skew_25d:.1%}: heavy downside protection demand"
                )
            elif surface.skew_25d < -0.04:
                evidence_for.append(
                    f"Inverted skew at {surface.skew_25d:.1%}: unusual call demand / complacency"
                )

            if surface.surface_regime == "fear":
                evidence_for.append("IV surface in FEAR regime")
            elif surface.surface_regime == "complacency":
                evidence_against.append("IV surface in COMPLACENCY regime")

            if gamma_flip and underlying_price < gamma_flip:
                evidence_for.append(
                    f"Price below gamma flip ({gamma_flip:.2f}): negative gamma zone"
                )

            entry = underlying_price
            atr = self._get_atr(context, symbol, underlying_price)
            stop_dist = atr * 2.0

            if direction == "BEARISH":
                stop_loss = entry + stop_dist
                target = entry - stop_dist * 2.5
            else:
                stop_loss = entry - stop_dist
                target = entry + stop_dist * 2.5

            rr = abs(target - entry) / abs(stop_loss - entry) if abs(stop_loss - entry) > 0 else 0

            signals.append(AdvancedScanResult(
                scan_id=str(uuid.uuid4()),
                scan_name="options_intelligence_skew",
                category=ScanCategory.OPTIONS,
                symbol=symbol,
                signal_direction=direction,
                signal_strength=strength,
                confidence=confidence,
                expected_move_pct=round(abs(surface.skew_25d) * 100, 2),
                expected_timeframe=ExpectedTimeframe.SWING,
                risk_reward_ratio=round(rr, 2),
                entry_price=entry,
                stop_loss_level=round(stop_loss, 2),
                target_level=round(target, 2),
                supporting_evidence=evidence_for,
                contradicting_evidence=evidence_against,
                regime_context=regime_context,
                mathematical_basis=(
                    f"25D Risk Reversal = {surface.skew_25d:.4f}, "
                    f"25D Butterfly = {surface.butterfly_25d:.4f}"
                ),
                false_positive_rate=0.35,
                decay_halflife_days=5,
                metadata={**base_metadata, "signal_type": "extreme_skew"},
            ))

        # --- Signal 2: Gamma Squeeze Setup ---
        if net_gex < 0 and chain.total_call_volume > chain.total_put_volume * 1.5:
            confidence = min(0.80, 0.45 + abs(net_gex) / (abs(net_gex) + 1e8) * 0.35)
            strength = min(1.0, abs(net_gex) / (abs(net_gex) + 5e7))

            evidence_for = [
                f"Negative net GEX ({net_gex:,.0f}): dealers short gamma",
                f"Call volume {chain.total_call_volume:,} > Put volume {chain.total_put_volume:,}",
            ]
            evidence_against = []

            if gamma_flip and underlying_price > gamma_flip:
                evidence_against.append(
                    f"Price above gamma flip ({gamma_flip:.2f}): may already be in positive gamma zone"
                )
            if iv_rank_val > 70:
                evidence_against.append(f"IV Rank at {iv_rank_val:.0f}%: options are expensive")
            if iv_rank_val < 30:
                evidence_for.append(f"Low IV Rank ({iv_rank_val:.0f}%): cheap call premiums fuel squeeze")

            entry = underlying_price
            atr = self._get_atr(context, symbol, underlying_price)
            stop_loss = entry - atr * 1.5
            target = entry + atr * 4.0
            rr = abs(target - entry) / abs(stop_loss - entry) if abs(stop_loss - entry) > 0 else 0

            signals.append(AdvancedScanResult(
                scan_id=str(uuid.uuid4()),
                scan_name="options_intelligence_gamma_squeeze",
                category=ScanCategory.OPTIONS,
                symbol=symbol,
                signal_direction="BULLISH",
                signal_strength=strength,
                confidence=confidence,
                expected_move_pct=round(atr / underlying_price * 400, 2),
                expected_timeframe=ExpectedTimeframe.INTRADAY,
                risk_reward_ratio=round(rr, 2),
                entry_price=entry,
                stop_loss_level=round(stop_loss, 2),
                target_level=round(target, 2),
                supporting_evidence=evidence_for,
                contradicting_evidence=evidence_against,
                regime_context=regime_context,
                mathematical_basis=(
                    f"Net GEX = {net_gex:,.0f}, "
                    f"Gamma Flip = {gamma_flip}, "
                    f"Call/Put Vol Ratio = {chain.total_call_volume / max(1, chain.total_put_volume):.2f}"
                ),
                false_positive_rate=0.40,
                decay_halflife_days=2,
                metadata={**base_metadata, "signal_type": "gamma_squeeze"},
            ))

        # --- Signal 3: Significant Vanna/Charm Flow ---
        eod_direction = eod_flow.get("direction", "neutral")
        eod_magnitude = eod_flow.get("magnitude", 0.0)

        # Only signal if magnitude is meaningful relative to typical volume
        avg_volume = (
            context.market_data[symbol].avg_volume_20
            if symbol in context.market_data and context.market_data[symbol].avg_volume_20
            else 1_000_000
        )
        flow_significance = eod_magnitude / avg_volume if avg_volume > 0 else 0

        if eod_direction != "neutral" and flow_significance > 0.01:
            direction = "BULLISH" if eod_direction == "bullish" else "BEARISH"
            confidence = min(0.70, 0.35 + flow_significance * 10.0)
            strength = min(1.0, flow_significance * 20.0)

            evidence_for = [
                f"Charm-driven EOD {eod_direction} flow: {eod_magnitude:,.0f} delta shares",
                eod_flow.get("description", ""),
            ]
            evidence_against = []

            if abs(net_vanna) > eod_magnitude * 0.5:
                vanna_dir = "buying" if net_vanna > 0 else "selling"
                evidence_for.append(
                    f"Vanna exposure supports {vanna_dir} pressure on vol moves"
                )

            entry = underlying_price
            atr = self._get_atr(context, symbol, underlying_price)
            if direction == "BULLISH":
                stop_loss = entry - atr
                target = entry + atr * 1.5
            else:
                stop_loss = entry + atr
                target = entry - atr * 1.5
            rr = abs(target - entry) / abs(stop_loss - entry) if abs(stop_loss - entry) > 0 else 0

            signals.append(AdvancedScanResult(
                scan_id=str(uuid.uuid4()),
                scan_name="options_intelligence_flow",
                category=ScanCategory.OPTIONS,
                symbol=symbol,
                signal_direction=direction,
                signal_strength=strength,
                confidence=confidence,
                expected_move_pct=round(atr / underlying_price * 150, 2),
                expected_timeframe=ExpectedTimeframe.INTRADAY,
                risk_reward_ratio=round(rr, 2),
                entry_price=entry,
                stop_loss_level=round(stop_loss, 2),
                target_level=round(target, 2),
                supporting_evidence=evidence_for,
                contradicting_evidence=evidence_against,
                regime_context=regime_context,
                mathematical_basis=(
                    f"Net Charm = {net_charm:,.0f}, "
                    f"Net Vanna = {net_vanna:,.0f}, "
                    f"Flow/Volume = {flow_significance:.4f}"
                ),
                false_positive_rate=0.45,
                decay_halflife_days=1,
                metadata={**base_metadata, "signal_type": "vanna_charm_flow"},
            ))

        # --- Signal 4: Extreme IV Rank ---
        if iv_rank_val > 80 or iv_rank_val < 20:
            if iv_rank_val > 80:
                # High IV rank: IV is elevated, expect mean reversion (sell vol)
                direction = "NEUTRAL"  # Sell premium strategies
                evidence_for = [
                    f"IV Rank at {iv_rank_val:.0f}%: historically elevated volatility",
                    f"IV Percentile at {iv_pct_val:.0f}%",
                    "Favorable for premium selling strategies (iron condors, strangles)",
                ]
                evidence_against = []
                if surface.surface_regime == "fear":
                    evidence_against.append(
                        "Surface in FEAR regime: elevated IV may persist"
                    )
            else:
                # Low IV rank: IV is depressed, expect vol expansion (buy vol)
                direction = "NEUTRAL"  # Buy premium strategies
                evidence_for = [
                    f"IV Rank at {iv_rank_val:.0f}%: historically depressed volatility",
                    f"IV Percentile at {iv_pct_val:.0f}%",
                    "Favorable for premium buying strategies (straddles, strangles)",
                ]
                evidence_against = []
                if surface.surface_regime == "complacency":
                    evidence_for.append(
                        "Surface in COMPLACENCY regime: vol expansion likely"
                    )

            confidence = min(0.75, 0.40 + abs(iv_rank_val - 50) / 100.0)
            strength = abs(iv_rank_val - 50) / 50.0

            entry = underlying_price
            atr = self._get_atr(context, symbol, underlying_price)

            signals.append(AdvancedScanResult(
                scan_id=str(uuid.uuid4()),
                scan_name="options_intelligence_iv_extreme",
                category=ScanCategory.OPTIONS,
                symbol=symbol,
                signal_direction=direction,
                signal_strength=min(1.0, strength),
                confidence=confidence,
                expected_move_pct=round(surface.atm_vol * 100 / math.sqrt(12), 2),
                expected_timeframe=ExpectedTimeframe.SWING,
                risk_reward_ratio=1.5,
                entry_price=entry,
                stop_loss_level=round(entry - atr * 2, 2),
                target_level=round(entry + atr * 3, 2),
                supporting_evidence=evidence_for,
                contradicting_evidence=evidence_against,
                regime_context=regime_context,
                mathematical_basis=(
                    f"IV Rank = {iv_rank_val:.1f}%, "
                    f"IV Percentile = {iv_pct_val:.1f}%, "
                    f"ATM Vol = {surface.atm_vol:.2%}"
                ),
                false_positive_rate=0.30,
                decay_halflife_days=10,
                metadata={**base_metadata, "signal_type": "iv_extreme"},
            ))

        # --- Signal 5: Whale Activity ---
        if whale_trades:
            total_whale_premium = sum(w["premium"] for w in whale_trades)
            bullish_whales = [w for w in whale_trades if "buy" in w["classification"]]
            bearish_whales = [w for w in whale_trades if "sell" in w["classification"]]

            bullish_premium = sum(w["premium"] for w in bullish_whales)
            bearish_premium = sum(w["premium"] for w in bearish_whales)

            if bullish_premium > bearish_premium * 1.5:
                direction = "BULLISH"
            elif bearish_premium > bullish_premium * 1.5:
                direction = "BEARISH"
            else:
                direction = "NEUTRAL"

            confidence = min(0.80, 0.45 + len(whale_trades) * 0.05 + smart_money_score / 200.0)
            strength = min(1.0, total_whale_premium / 5_000_000)

            evidence_for = [
                f"{len(whale_trades)} whale trades detected, total premium ${total_whale_premium:,.0f}",
                f"Smart money score: {smart_money_score:.0f}/100",
            ]
            evidence_against = []

            for w in whale_trades[:3]:
                evidence_for.append(
                    f"  {w['option_type']} ${w['strike']} {w['classification']}: "
                    f"${w['premium']:,.0f} ({w['alert_level']})"
                )

            entry = underlying_price
            atr = self._get_atr(context, symbol, underlying_price)
            if direction == "BULLISH":
                stop_loss = entry - atr * 2
                target = entry + atr * 3
            elif direction == "BEARISH":
                stop_loss = entry + atr * 2
                target = entry - atr * 3
            else:
                stop_loss = entry - atr * 2
                target = entry + atr * 2
            rr = abs(target - entry) / abs(stop_loss - entry) if abs(stop_loss - entry) > 0 else 0

            signals.append(AdvancedScanResult(
                scan_id=str(uuid.uuid4()),
                scan_name="options_intelligence_whale",
                category=ScanCategory.OPTIONS,
                symbol=symbol,
                signal_direction=direction,
                signal_strength=strength,
                confidence=confidence,
                expected_move_pct=round(atr / underlying_price * 300, 2),
                expected_timeframe=ExpectedTimeframe.SWING,
                risk_reward_ratio=round(rr, 2),
                entry_price=entry,
                stop_loss_level=round(stop_loss, 2),
                target_level=round(target, 2),
                supporting_evidence=evidence_for,
                contradicting_evidence=evidence_against,
                regime_context=regime_context,
                mathematical_basis=(
                    f"Whale Premium = ${total_whale_premium:,.0f}, "
                    f"Smart Money Score = {smart_money_score:.1f}, "
                    f"Bullish/Bearish Ratio = "
                    f"{bullish_premium / max(1, bearish_premium):.2f}"
                ),
                false_positive_rate=0.25,
                decay_halflife_days=7,
                metadata={
                    **base_metadata,
                    "signal_type": "whale_activity",
                    "whale_trades": whale_trades[:5],
                },
            ))

        return signals

    def validate_signal(
        self, result: AdvancedScanResult, context: ScanContext
    ) -> bool:
        """Validate an options intelligence signal.

        Args:
            result: The signal to validate.
            context: Current scan context.

        Returns:
            True if signal passes validation checks.
        """
        # Minimum confidence threshold (AdvancedScanResult uses 0-1 scale)
        min_conf = self.config.min_confidence / 100.0
        if result.confidence < min_conf:
            return False

        # Must have supporting evidence
        if not result.supporting_evidence:
            return False

        # Signal should not be overwhelmed by contradicting evidence
        if len(result.contradicting_evidence) > len(result.supporting_evidence):
            return False

        return True

    # ---- Internal Helpers ----

    def _build_chain(
        self, symbol: str, options_data: Dict, underlying_price: float
    ) -> Optional[OptionsChain]:
        """Build an OptionsChain from raw options data dictionary.

        Args:
            symbol: Ticker symbol.
            options_data: Raw options data dict from context.
            underlying_price: Current underlying price.

        Returns:
            OptionsChain or None if no valid contracts.
        """
        contracts: List[OptionContract] = []

        for cd in options_data.get("contracts", []):
            try:
                exp_str = cd.get("expiration", "")
                if isinstance(exp_str, datetime):
                    expiration = exp_str
                else:
                    expiration = datetime.fromisoformat(str(exp_str))

                contract = OptionContract(
                    symbol=cd.get("symbol", ""),
                    underlying=symbol,
                    strike=float(cd.get("strike", 0)),
                    expiration=expiration,
                    option_type=cd.get("option_type", "CALL"),
                    bid=float(cd.get("bid", 0)),
                    ask=float(cd.get("ask", 0)),
                    last=float(cd.get("last", 0)),
                    volume=int(cd.get("volume", 0)),
                    open_interest=int(cd.get("open_interest", 0)),
                    implied_volatility=float(cd.get("iv", cd.get("implied_volatility", 0))),
                    delta=cd.get("delta"),
                    gamma=cd.get("gamma"),
                    theta=cd.get("theta"),
                    vega=cd.get("vega"),
                    trade_count=int(cd.get("trade_count", 0)),
                    avg_trade_size=float(cd.get("avg_trade_size", 0)),
                    buy_volume=int(cd.get("buy_volume", 0)),
                    sell_volume=int(cd.get("sell_volume", 0)),
                )
                contracts.append(contract)
            except (KeyError, ValueError, TypeError) as e:
                self._logger.debug(f"Skipping invalid contract for {symbol}: {e}")
                continue

        if not contracts:
            return None

        return OptionsChain(
            underlying=symbol,
            underlying_price=underlying_price,
            contracts=contracts,
            iv_rank=options_data.get("iv_rank"),
            iv_percentile=options_data.get("iv_percentile"),
        )

    def _classify_chain_flow(
        self, chain: OptionsChain
    ) -> List[ClassifiedTrade]:
        """Classify all contracts in the chain as trades for flow analysis.

        Args:
            chain: Options chain with contract data.

        Returns:
            List of classified trades.
        """
        classified: List[ClassifiedTrade] = []

        for c in chain.contracts:
            if c.volume <= 0:
                continue

            premium = c.volume * c.mid_price * 100

            # Estimate price position in bid-ask range
            spread = c.ask - c.bid
            if spread > 0 and c.last > 0:
                price_position = (c.last - c.bid) / spread
                price_position = max(0.0, min(1.0, price_position))
            else:
                price_position = 0.5

            classification = self.flow_classifier.classify_trade(
                volume=c.volume,
                open_interest=c.open_interest,
                price_vs_bid_ask=price_position,
                trade_size=int(c.avg_trade_size) if c.avg_trade_size > 0 else c.volume,
            )

            smart_score = classification["conviction"]

            classified.append(ClassifiedTrade(
                contract=c,
                premium=premium,
                is_opening=classification["is_opening"],
                is_buyer_initiated=classification["is_buyer_initiated"],
                is_institutional=classification["is_institutional"],
                smart_money_score=smart_score,
                classification=classification["classification"],
            ))

        return classified

    def _get_atr(
        self, context: ScanContext, symbol: str, underlying_price: float
    ) -> float:
        """Get ATR for a symbol, falling back to a percentage estimate.

        Args:
            context: Scan context.
            symbol: Ticker symbol.
            underlying_price: Current price as fallback basis.

        Returns:
            ATR value.
        """
        market_data = context.market_data.get(symbol)
        if market_data and market_data.atr and market_data.atr > 0:
            return market_data.atr
        # Fallback: 2% of price
        return underlying_price * 0.02

    def _get_nearest_dte(self, contracts: List[OptionContract]) -> int:
        """Get the nearest DTE across all contracts.

        Args:
            contracts: List of option contracts.

        Returns:
            Minimum days to expiration found.
        """
        if not contracts:
            return 30
        dtes = [c.days_to_expiry for c in contracts if c.days_to_expiry > 0]
        return min(dtes) if dtes else 30

    def _determine_regime(
        self, context: ScanContext, surface: IVSurface
    ) -> RegimeContext:
        """Determine the RegimeContext from market and surface data.

        Args:
            context: Scan context with market regime.
            surface: IV surface for volatility context.

        Returns:
            RegimeContext enum value.
        """
        from .models import MarketRegime

        regime_map = {
            MarketRegime.TRENDING_UP: RegimeContext.TRENDING_UP,
            MarketRegime.TRENDING_DOWN: RegimeContext.TRENDING_DOWN,
            MarketRegime.RANGING: RegimeContext.RANGING,
            MarketRegime.HIGH_VOLATILITY: RegimeContext.VOLATILE,
            MarketRegime.LOW_VOLATILITY: RegimeContext.QUIET,
            MarketRegime.BREAKOUT: RegimeContext.TRANSITION,
        }

        base_regime = regime_map.get(context.market_regime, RegimeContext.RANGING)

        # Override with surface intelligence
        if surface.surface_regime == "fear" and surface.atm_vol > 0.40:
            return RegimeContext.CRISIS
        if surface.surface_regime == "complacency" and surface.atm_vol < 0.12:
            return RegimeContext.QUIET

        return base_regime
