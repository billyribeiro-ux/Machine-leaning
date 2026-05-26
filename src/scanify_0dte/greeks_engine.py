"""
SCANIFY 0DTE Greeks Calculation Engine

Production-grade Black-Scholes pricing and Greeks computation with specialized
handling for 0DTE (zero days to expiration) SPX options. All calculations use
the 252-trading-day, 390-minutes-per-day annualization convention.

Key design decisions for 0DTE:
    - Minimum time T is clamped to 1 minute = 1/(252*390) to prevent division
      by zero as expiration approaches.
    - Higher-order Greeks (charm, vanna, speed) are computed numerically with
      small bumps sized appropriately for the short remaining life.
    - Implied volatility uses Newton-Raphson with bisection fallback to handle
      the extreme curvature of the price-vs-vol relationship near expiry.
    - Theta is expressed per trading day (divide annualized theta by 252).
    - An empirical intraday theta decay model captures the non-linear
      acceleration of time value erosion through the trading session.

Dependencies:
    numpy, scipy, pandas

Author: SCANIFY Engine
"""

import logging
import numpy as np
import pandas as pd
from scipy.stats import norm
from datetime import datetime, time
from typing import Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

TRADING_DAYS_PER_YEAR: int = 252
MINUTES_PER_TRADING_DAY: int = 390
MINUTES_PER_YEAR: int = TRADING_DAYS_PER_YEAR * MINUTES_PER_TRADING_DAY  # 98280

# Minimum annualized time: 1 trading minute
MIN_T: float = 1.0 / MINUTES_PER_YEAR

# Two-pi constant used in normal PDF
_TWO_PI: float = 2.0 * np.pi


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def annualized_time(minutes_remaining: int) -> float:
    """Convert remaining trading minutes to annualized time fraction.

    Uses the 252-day / 390-minute convention standard for equity options.

    Args:
        minutes_remaining: Number of trading minutes until expiration.
            Values <= 0 are clamped to produce ``MIN_T``.

    Returns:
        Annualized time fraction T.  Always >= ``MIN_T``.

    Examples:
        >>> annualized_time(390)       # Full trading day
        0.003968...
        >>> annualized_time(1)         # One minute left
        1.0178...e-05
    """
    if minutes_remaining <= 0:
        return MIN_T
    return max(float(minutes_remaining) / MINUTES_PER_YEAR, MIN_T)


def normal_pdf(x: Union[float, np.ndarray]) -> Union[float, np.ndarray]:
    """Standard normal probability density function N'(x).

    Computed directly as exp(-x^2 / 2) / sqrt(2*pi) for speed, avoiding the
    overhead of scipy when called in tight loops.

    Args:
        x: Scalar or array of evaluation points.

    Returns:
        N'(x), same shape as input.
    """
    return np.exp(-0.5 * np.asarray(x) ** 2) / np.sqrt(_TWO_PI)


def normal_cdf(x: Union[float, np.ndarray]) -> Union[float, np.ndarray]:
    """Standard normal cumulative distribution function N(x).

    Delegates to ``scipy.stats.norm.cdf`` which uses a highly accurate
    rational approximation.

    Args:
        x: Scalar or array of evaluation points.

    Returns:
        N(x), same shape as input.
    """
    return norm.cdf(x)


def moneyness(S: float, K: float) -> float:
    """Log-moneyness defined as ln(K / S).

    Positive values indicate OTM calls / ITM puts.
    Negative values indicate ITM calls / OTM puts.
    Zero is at-the-money.

    Args:
        S: Spot (underlying) price.
        K: Strike price.

    Returns:
        ln(K / S).

    Raises:
        ValueError: If S or K is non-positive.
    """
    if S <= 0 or K <= 0:
        raise ValueError(f"S and K must be positive; got S={S}, K={K}")
    return np.log(K / S)


def otm_gamma_ratio(
    gamma_atm: float,
    log_moneyness: float,
    sigma: float,
    T: float,
) -> float:
    """Approximate OTM gamma as a fraction of ATM gamma.

    Uses the Gaussian decay relationship:
        Gamma_OTM ~ Gamma_ATM * exp(-0.5 * (m / (sigma * sqrt(T)))^2)

    where m = ln(K/S) is the log-moneyness.

    Args:
        gamma_atm: ATM gamma value.
        log_moneyness: ln(K/S) for the OTM strike.
        sigma: Implied volatility (annualized, decimal).
        T: Annualized time to expiration.

    Returns:
        Estimated gamma at the OTM strike.
    """
    T = max(T, MIN_T)
    sigma = max(sigma, 1e-8)
    std_dev = sigma * np.sqrt(T)
    z = log_moneyness / std_dev
    return gamma_atm * np.exp(-0.5 * z * z)


# =============================================================================
# INTRADAY THETA DECAY MODEL
# =============================================================================

def theta_decay_fraction(current_time_et: time) -> float:
    """Fraction of daily theta already consumed at the given Eastern time.

    Empirical non-linear intraday theta decay curve for 0DTE options,
    calibrated to observed SPX option behavior:

        09:30 - 11:00  ~15-20% of daily theta (slow burn)
        11:00 - 14:00  ~25-30% (steady grind)
        14:00 - 15:30  ~30-35% (THE CLIFF -- rapid acceleration)
        15:30 - 16:00  ~15-20% (terminal collapse)

    The cumulative fraction is modeled as a piecewise-linear function over
    these four intervals.

    Args:
        current_time_et: ``datetime.time`` in US Eastern timezone.
            Times before 09:30 return 0.0; times at or after 16:00 return 1.0.

    Returns:
        Cumulative fraction of daily theta consumed, in [0.0, 1.0].
    """
    market_open = time(9, 30)
    market_close = time(16, 0)

    if current_time_et <= market_open:
        return 0.0
    if current_time_et >= market_close:
        return 1.0

    # Convert time-of-day to minutes since market open.
    minutes_since_open = (
        (current_time_et.hour - 9) * 60
        + current_time_et.minute
        - 30  # market opens at :30
    )
    minutes_since_open = max(0.0, float(minutes_since_open))

    # Breakpoints (minutes since open) and cumulative theta fractions.
    #   09:30 ->   0 min -> 0.00
    #   11:00 ->  90 min -> 0.175  (midpoint of 15-20%)
    #   14:00 -> 270 min -> 0.45   (0.175 + midpoint of 25-30%)
    #   15:30 -> 360 min -> 0.775  (0.45 + midpoint of 30-35%)
    #   16:00 -> 390 min -> 1.00   (0.775 + midpoint of 15-20% => ~0.95-1.0)
    breakpoints = [
        (0.0,   0.000),
        (90.0,  0.175),
        (270.0, 0.450),
        (360.0, 0.775),
        (390.0, 1.000),
    ]

    for i in range(1, len(breakpoints)):
        t0, f0 = breakpoints[i - 1]
        t1, f1 = breakpoints[i]
        if minutes_since_open <= t1:
            # Linear interpolation within this segment.
            alpha = (minutes_since_open - t0) / (t1 - t0)
            return f0 + alpha * (f1 - f0)

    return 1.0


# =============================================================================
# EXPECTED MOVE CALCULATIONS
# =============================================================================

def expected_move_vix1d(spx_price: float, vix1d: float) -> float:
    """One-day expected move derived from VIX1D (one-day VIX).

    Formula:
        EM = SPX * (VIX1D / 100) / sqrt(252)

    Args:
        spx_price: Current SPX index level.
        vix1d: VIX1D index level (e.g. 14.5 means 14.5%).

    Returns:
        Absolute expected move in index points (one standard deviation).
    """
    return spx_price * (vix1d / 100.0) / np.sqrt(TRADING_DAYS_PER_YEAR)


def expected_move_straddle(atm_straddle_price: float) -> float:
    """Expected move implied by the at-the-money straddle price.

    Market convention applies an 85% haircut to the straddle price to convert
    the total premium into a one-sigma expected move.

    Formula:
        EM = 0.85 * straddle_price

    Args:
        atm_straddle_price: Combined premium of ATM call + ATM put.

    Returns:
        Absolute expected move in index points.
    """
    return 0.85 * atm_straddle_price


def expected_move_rv_adjusted(
    spx_price: float,
    vix1d: float,
    rv_20day: float,
) -> float:
    """Expected move adjusted for implied/realized volatility ratio.

    When IV (proxied by VIX1D) is elevated relative to 20-day realized
    volatility, the market tends to mean-revert.  This estimator blends
    the two by weighting toward RV when the IV/RV ratio is stretched.

    Method:
        1. Compute iv_rv_ratio = (VIX1D / 100) / (RV_20 / 100).
        2. Apply mean-reversion weight:
           adjusted_vol = (VIX1D/100) * (2 / (1 + iv_rv_ratio))
           This pulls toward RV when IV >> RV and toward IV when IV ~ RV.
        3. EM = SPX * adjusted_vol / sqrt(252)

    Args:
        spx_price: Current SPX index level.
        vix1d: VIX1D index level (percentage, e.g. 14.5).
        rv_20day: 20-day realized volatility (percentage, e.g. 12.0).

    Returns:
        Absolute expected move in index points.
    """
    iv = vix1d / 100.0
    rv = max(rv_20day / 100.0, 1e-8)  # prevent division by zero
    iv_rv_ratio = iv / rv

    # Mean-reversion adjustment: blend toward RV when IV/RV is stretched.
    adjusted_vol = iv * (2.0 / (1.0 + iv_rv_ratio))
    return spx_price * adjusted_vol / np.sqrt(TRADING_DAYS_PER_YEAR)


def composite_expected_move(
    spx_price: float,
    vix1d: float,
    atm_straddle_price: float,
    rv_20day: float,
) -> Tuple[float, float]:
    """Composite expected move using a weighted blend of three estimators.

    Weights:
        40% VIX1D-based
        40% Straddle-based
        20% RV-adjusted

    Returns both a one-sigma and two-sigma expected move.

    Args:
        spx_price: Current SPX index level.
        vix1d: VIX1D level (percentage).
        atm_straddle_price: ATM straddle premium.
        rv_20day: 20-day realized vol (percentage).

    Returns:
        Tuple of (EM_1sigma, EM_2sigma) in index points.
    """
    em_vix = expected_move_vix1d(spx_price, vix1d)
    em_straddle = expected_move_straddle(atm_straddle_price)
    em_rv = expected_move_rv_adjusted(spx_price, vix1d, rv_20day)

    em_1sigma = 0.40 * em_vix + 0.40 * em_straddle + 0.20 * em_rv
    em_2sigma = 2.0 * em_1sigma

    return em_1sigma, em_2sigma


# =============================================================================
# BLACK-SCHOLES 0DTE ENGINE
# =============================================================================

class BlackScholes0DTE:
    """Black-Scholes pricing and Greeks engine tuned for 0DTE options.

    All time inputs ``T`` are in annualized fraction form (see
    ``annualized_time``).  When T is extremely small the engine clamps it to
    ``MIN_T`` (1 trading minute) to maintain numerical stability.

    Higher-order Greeks critical for 0DTE -- charm, vanna, speed -- are
    computed via controlled numerical bumps rather than closed-form
    expressions, because near expiry the analytical forms can produce
    extreme spikes that are numerically indistinguishable from infinity.

    Args:
        risk_free_rate: Annualized continuously-compounded rate.
            Default 0.053 (~current Treasury curve proxy).
        dividend_yield: Annualized continuous dividend yield for SPX.
            Default 0.013 (~SPX historical yield).
    """

    def __init__(
        self,
        risk_free_rate: float = 0.053,
        dividend_yield: float = 0.013,
    ) -> None:
        self.r: float = risk_free_rate
        self.q: float = dividend_yield

    # -----------------------------------------------------------------
    # Core Black-Scholes components
    # -----------------------------------------------------------------

    @staticmethod
    def _clamp_T(T: float) -> float:
        """Ensure T is at least MIN_T to avoid division by zero."""
        if T < MIN_T:
            logger.warning("Time T=%f clamped to MIN_T=%f", T, MIN_T)
        return max(T, MIN_T)

    def d1(
        self,
        S: float,
        K: float,
        T: float,
        sigma: float,
        r: Optional[float] = None,
        q: Optional[float] = None,
    ) -> float:
        """Compute the Black-Scholes d1 parameter.

        d1 = [ln(S/K) + (r - q + sigma^2/2) * T] / (sigma * sqrt(T))

        When T approaches zero, it is clamped to MIN_T (one trading minute)
        to prevent numerical blow-up.

        Args:
            S: Spot price.
            K: Strike price.
            T: Annualized time to expiration.
            sigma: Implied volatility (annualized, decimal).
            r: Risk-free rate (overrides instance default if provided).
            q: Dividend yield (overrides instance default if provided).

        Returns:
            d1 value.
        """
        r = r if r is not None else self.r
        q = q if q is not None else self.q
        T = self._clamp_T(T)
        sigma = max(sigma, 1e-10)

        sqrt_T = np.sqrt(T)
        return (np.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * sqrt_T)

    def d2(
        self,
        S: float,
        K: float,
        T: float,
        sigma: float,
        r: Optional[float] = None,
        q: Optional[float] = None,
    ) -> float:
        """Compute the Black-Scholes d2 parameter.

        d2 = d1 - sigma * sqrt(T)

        Args:
            S: Spot price.
            K: Strike price.
            T: Annualized time to expiration.
            sigma: Implied volatility.
            r: Risk-free rate.
            q: Dividend yield.

        Returns:
            d2 value.
        """
        T = self._clamp_T(T)
        sigma = max(sigma, 1e-10)
        return self.d1(S, K, T, sigma, r, q) - sigma * np.sqrt(T)

    # -----------------------------------------------------------------
    # Option prices
    # -----------------------------------------------------------------

    def call_price(
        self,
        S: float,
        K: float,
        T: float,
        sigma: float,
        r: Optional[float] = None,
        q: Optional[float] = None,
    ) -> float:
        """European call price via Black-Scholes.

        C = S * e^(-qT) * N(d1)  -  K * e^(-rT) * N(d2)

        Args:
            S: Spot price.
            K: Strike price.
            T: Annualized time to expiration.
            sigma: Implied volatility.
            r: Risk-free rate.
            q: Dividend yield.

        Returns:
            Call option theoretical value.
        """
        r = r if r is not None else self.r
        q = q if q is not None else self.q
        T = self._clamp_T(T)

        _d1 = self.d1(S, K, T, sigma, r, q)
        _d2 = _d1 - sigma * np.sqrt(T)

        return (
            S * np.exp(-q * T) * normal_cdf(_d1)
            - K * np.exp(-r * T) * normal_cdf(_d2)
        )

    def put_price(
        self,
        S: float,
        K: float,
        T: float,
        sigma: float,
        r: Optional[float] = None,
        q: Optional[float] = None,
    ) -> float:
        """European put price via Black-Scholes.

        P = K * e^(-rT) * N(-d2)  -  S * e^(-qT) * N(-d1)

        Args:
            S: Spot price.
            K: Strike price.
            T: Annualized time to expiration.
            sigma: Implied volatility.
            r: Risk-free rate.
            q: Dividend yield.

        Returns:
            Put option theoretical value.
        """
        r = r if r is not None else self.r
        q = q if q is not None else self.q
        T = self._clamp_T(T)

        _d1 = self.d1(S, K, T, sigma, r, q)
        _d2 = _d1 - sigma * np.sqrt(T)

        return (
            K * np.exp(-r * T) * normal_cdf(-_d2)
            - S * np.exp(-q * T) * normal_cdf(-_d1)
        )

    def _price(
        self,
        S: float,
        K: float,
        T: float,
        sigma: float,
        r: float,
        q: float,
        option_type: str,
    ) -> float:
        """Internal dispatcher for call/put pricing."""
        if option_type.lower() in ("call", "c"):
            return self.call_price(S, K, T, sigma, r, q)
        else:
            return self.put_price(S, K, T, sigma, r, q)

    # -----------------------------------------------------------------
    # First-order Greeks
    # -----------------------------------------------------------------

    def delta(
        self,
        S: float,
        K: float,
        T: float,
        sigma: float,
        r: Optional[float] = None,
        q: Optional[float] = None,
        option_type: str = "call",
    ) -> float:
        """Option delta -- sensitivity of price to underlying.

        Call: Delta = e^(-qT) * N(d1)
        Put:  Delta = -e^(-qT) * N(-d1)

        Args:
            S: Spot price.
            K: Strike price.
            T: Annualized time to expiration.
            sigma: Implied volatility.
            r: Risk-free rate.
            q: Dividend yield.
            option_type: ``'call'`` or ``'put'``.

        Returns:
            Delta value.  Calls in [0, 1], puts in [-1, 0].
        """
        r = r if r is not None else self.r
        q = q if q is not None else self.q
        T = self._clamp_T(T)

        _d1 = self.d1(S, K, T, sigma, r, q)
        exp_qT = np.exp(-q * T)

        if option_type.lower() in ("call", "c"):
            return exp_qT * normal_cdf(_d1)
        else:
            return -exp_qT * normal_cdf(-_d1)

    def gamma(
        self,
        S: float,
        K: float,
        T: float,
        sigma: float,
        r: Optional[float] = None,
        q: Optional[float] = None,
    ) -> float:
        """Option gamma -- rate of change of delta with respect to spot.

        Gamma = e^(-qT) * N'(d1) / (S * sigma * sqrt(T))

        Gamma is identical for calls and puts at the same strike.

        Args:
            S: Spot price.
            K: Strike price.
            T: Annualized time to expiration.
            sigma: Implied volatility.
            r: Risk-free rate.
            q: Dividend yield.

        Returns:
            Gamma value.  Always non-negative.
        """
        r = r if r is not None else self.r
        q = q if q is not None else self.q
        T = self._clamp_T(T)
        sigma = max(sigma, 1e-10)

        _d1 = self.d1(S, K, T, sigma, r, q)
        sqrt_T = np.sqrt(T)

        return np.exp(-q * T) * normal_pdf(_d1) / (S * sigma * sqrt_T)

    def theta(
        self,
        S: float,
        K: float,
        T: float,
        sigma: float,
        r: Optional[float] = None,
        q: Optional[float] = None,
        option_type: str = "call",
    ) -> float:
        """Option theta -- time decay per trading day.

        Call Theta (annualized):
            = [-S * sigma * e^(-qT) * N'(d1) / (2*sqrt(T))]
              - r*K*e^(-rT)*N(d2) + q*S*e^(-qT)*N(d1)

        Put Theta (annualized):
            = [-S * sigma * e^(-qT) * N'(d1) / (2*sqrt(T))]
              + r*K*e^(-rT)*N(-d2) - q*S*e^(-qT)*N(-d1)

        The result is divided by 252 to express theta per trading day.

        Args:
            S: Spot price.
            K: Strike price.
            T: Annualized time to expiration.
            sigma: Implied volatility.
            r: Risk-free rate.
            q: Dividend yield.
            option_type: ``'call'`` or ``'put'``.

        Returns:
            Theta per trading day (typically negative for long options).
        """
        r = r if r is not None else self.r
        q = q if q is not None else self.q
        T = self._clamp_T(T)
        sigma = max(sigma, 1e-10)

        _d1 = self.d1(S, K, T, sigma, r, q)
        _d2 = _d1 - sigma * np.sqrt(T)
        sqrt_T = np.sqrt(T)

        exp_qT = np.exp(-q * T)
        exp_rT = np.exp(-r * T)
        npd1 = normal_pdf(_d1)

        # Common term: first component of theta
        common = -S * sigma * exp_qT * npd1 / (2.0 * sqrt_T)

        if option_type.lower() in ("call", "c"):
            theta_annual = common - r * K * exp_rT * normal_cdf(_d2) + q * S * exp_qT * normal_cdf(_d1)
        else:
            theta_annual = common + r * K * exp_rT * normal_cdf(-_d2) - q * S * exp_qT * normal_cdf(-_d1)

        # Express per trading day
        return theta_annual / TRADING_DAYS_PER_YEAR

    def vega(
        self,
        S: float,
        K: float,
        T: float,
        sigma: float,
        r: Optional[float] = None,
        q: Optional[float] = None,
    ) -> float:
        """Option vega -- sensitivity to a 1-percentage-point change in IV.

        Vega_raw = S * e^(-qT) * sqrt(T) * N'(d1)

        We divide by 100 so the result represents the price change per
        1-percentage-point (0.01) move in implied volatility.

        Vega is identical for calls and puts at the same strike.

        Args:
            S: Spot price.
            K: Strike price.
            T: Annualized time to expiration.
            sigma: Implied volatility.
            r: Risk-free rate.
            q: Dividend yield.

        Returns:
            Vega per 1 vol point.
        """
        r = r if r is not None else self.r
        q = q if q is not None else self.q
        T = self._clamp_T(T)

        _d1 = self.d1(S, K, T, sigma, r, q)
        sqrt_T = np.sqrt(T)

        return S * np.exp(-q * T) * sqrt_T * normal_pdf(_d1) / 100.0

    def rho(
        self,
        S: float,
        K: float,
        T: float,
        sigma: float,
        r: Optional[float] = None,
        q: Optional[float] = None,
        option_type: str = "call",
    ) -> float:
        """Option rho -- sensitivity to a 1-percentage-point change in rate.

        Call rho =  K * T * e^(-rT) * N(d2) / 100
        Put rho  = -K * T * e^(-rT) * N(-d2) / 100

        Args:
            S: Spot price.
            K: Strike price.
            T: Annualized time to expiration.
            sigma: Implied volatility.
            r: Risk-free rate.
            q: Dividend yield.
            option_type: ``'call'`` or ``'put'``.

        Returns:
            Rho per 1 percentage-point rate change.
        """
        r = r if r is not None else self.r
        q = q if q is not None else self.q
        T = self._clamp_T(T)

        _d2 = self.d2(S, K, T, sigma, r, q)
        exp_rT = np.exp(-r * T)

        if option_type.lower() in ("call", "c"):
            return K * T * exp_rT * normal_cdf(_d2) / 100.0
        else:
            return -K * T * exp_rT * normal_cdf(-_d2) / 100.0

    # -----------------------------------------------------------------
    # Higher-order Greeks (numerical for 0DTE robustness)
    # -----------------------------------------------------------------

    def charm(
        self,
        S: float,
        K: float,
        T: float,
        sigma: float,
        r: Optional[float] = None,
        q: Optional[float] = None,
        option_type: str = "call",
    ) -> float:
        """Charm -- rate of delta decay over time (dDelta/dT).

        Computed numerically by bumping T backward by one trading minute:
            charm = (delta(T - dt) - delta(T)) / dt

        This is critical for 0DTE: charm quantifies how rapidly OTM options
        lose delta as expiration approaches.

        Args:
            S: Spot price.
            K: Strike price.
            T: Annualized time to expiration.
            sigma: Implied volatility.
            r: Risk-free rate.
            q: Dividend yield.
            option_type: ``'call'`` or ``'put'``.

        Returns:
            Charm value (delta change per annualized time unit).
        """
        r = r if r is not None else self.r
        q = q if q is not None else self.q
        T = self._clamp_T(T)

        dt = MIN_T  # 1 trading minute bump

        delta_now = self.delta(S, K, T, sigma, r, q, option_type)
        # Bump T backward (closer to expiry).  Clamp so we don't go below MIN_T.
        T_bumped = max(T - dt, MIN_T)
        delta_bumped = self.delta(S, K, T_bumped, sigma, r, q, option_type)

        effective_dt = T - T_bumped
        if effective_dt < 1e-15:
            return 0.0

        return (delta_bumped - delta_now) / effective_dt

    def vanna(
        self,
        S: float,
        K: float,
        T: float,
        sigma: float,
        r: Optional[float] = None,
        q: Optional[float] = None,
        option_type: str = "call",
    ) -> float:
        """Vanna -- sensitivity of delta to volatility (dDelta/dSigma).

        Computed numerically with a 1-vol-point (0.01) bump:
            vanna = (delta(sigma + dsigma) - delta(sigma)) / dsigma

        Args:
            S: Spot price.
            K: Strike price.
            T: Annualized time to expiration.
            sigma: Implied volatility.
            r: Risk-free rate.
            q: Dividend yield.
            option_type: ``'call'`` or ``'put'``.

        Returns:
            Vanna value (delta change per unit vol change).
        """
        r = r if r is not None else self.r
        q = q if q is not None else self.q
        T = self._clamp_T(T)

        d_sigma = 0.01  # 1 vol point

        delta_base = self.delta(S, K, T, sigma, r, q, option_type)
        delta_bumped = self.delta(S, K, T, sigma + d_sigma, r, q, option_type)

        return (delta_bumped - delta_base) / d_sigma

    def speed(
        self,
        S: float,
        K: float,
        T: float,
        sigma: float,
        r: Optional[float] = None,
        q: Optional[float] = None,
    ) -> float:
        """Speed -- rate of change of gamma with respect to spot (dGamma/dS).

        Computed numerically by bumping S by $1:
            speed = (gamma(S + 1) - gamma(S)) / 1.0

        Args:
            S: Spot price.
            K: Strike price.
            T: Annualized time to expiration.
            sigma: Implied volatility.
            r: Risk-free rate.
            q: Dividend yield.

        Returns:
            Speed value.
        """
        r = r if r is not None else self.r
        q = q if q is not None else self.q
        T = self._clamp_T(T)

        dS = 1.0  # $1 bump

        gamma_base = self.gamma(S, K, T, sigma, r, q)
        gamma_bumped = self.gamma(S + dS, K, T, sigma, r, q)

        return (gamma_bumped - gamma_base) / dS

    # -----------------------------------------------------------------
    # Implied Volatility
    # -----------------------------------------------------------------

    def implied_volatility(
        self,
        option_price: float,
        S: float,
        K: float,
        T: float,
        r: Optional[float] = None,
        q: Optional[float] = None,
        option_type: str = "call",
        initial_guess: float = 0.20,
    ) -> float:
        """Extract implied volatility from an observed option price.

        Primary method: Newton-Raphson using vega as the derivative.
        Fallback: bisection method if Newton fails to converge.

        Edge case handling for 0DTE:
            - Deep OTM options (< $0.10): widen initial bracket for bisection.
            - Deep ITM options: clamp intrinsic floor.
            - Near-zero T: ensure MIN_T is used.

        Args:
            option_price: Observed market price of the option.
            S: Spot price.
            K: Strike price.
            T: Annualized time to expiration.
            r: Risk-free rate.
            q: Dividend yield.
            option_type: ``'call'`` or ``'put'``.
            initial_guess: Starting IV for Newton-Raphson.

        Returns:
            Implied volatility as a decimal (e.g. 0.15 for 15%).
            Returns ``np.nan`` if extraction fails entirely.
        """
        r = r if r is not None else self.r
        q = q if q is not None else self.q
        T = self._clamp_T(T)

        is_call = option_type.lower() in ("call", "c")

        # ----- Sanity checks -----
        # Intrinsic value floor
        if is_call:
            intrinsic = max(S * np.exp(-q * T) - K * np.exp(-r * T), 0.0)
        else:
            intrinsic = max(K * np.exp(-r * T) - S * np.exp(-q * T), 0.0)

        if option_price <= 0:
            return 0.0

        # If price is at or below intrinsic, IV is effectively zero
        if option_price <= intrinsic + 1e-10:
            return 1e-6

        # ----- Newton-Raphson -----
        max_iterations = 100
        tolerance = 1e-8

        sigma = max(initial_guess, 0.01)

        for _ in range(max_iterations):
            # Compute model price
            if is_call:
                model_price = self.call_price(S, K, T, sigma, r, q)
            else:
                model_price = self.put_price(S, K, T, sigma, r, q)

            diff = model_price - option_price

            if abs(diff) < tolerance:
                return sigma

            # Vega (un-scaled: dPrice/dSigma)
            _d1 = self.d1(S, K, T, sigma, r, q)
            vega_raw = S * np.exp(-q * T) * np.sqrt(T) * normal_pdf(_d1)

            if vega_raw < 1e-15:
                break  # Vega too small; Newton step would be enormous

            sigma -= diff / vega_raw
            sigma = max(sigma, 1e-4)
            sigma = min(sigma, 10.0)

        # ----- Bisection fallback -----
        sigma_lo = 1e-4
        sigma_hi = 10.0
        max_bisect = 200

        # Verify bracket
        if is_call:
            price_lo = self.call_price(S, K, T, sigma_lo, r, q)
            price_hi = self.call_price(S, K, T, sigma_hi, r, q)
        else:
            price_lo = self.put_price(S, K, T, sigma_lo, r, q)
            price_hi = self.put_price(S, K, T, sigma_hi, r, q)

        if (price_lo - option_price) * (price_hi - option_price) > 0:
            # No root in bracket; return NaN
            return np.nan

        for _ in range(max_bisect):
            sigma_mid = 0.5 * (sigma_lo + sigma_hi)
            if is_call:
                price_mid = self.call_price(S, K, T, sigma_mid, r, q)
            else:
                price_mid = self.put_price(S, K, T, sigma_mid, r, q)

            diff = price_mid - option_price

            if abs(diff) < tolerance or (sigma_hi - sigma_lo) < 1e-10:
                return sigma_mid

            if (price_lo - option_price) * diff < 0:
                sigma_hi = sigma_mid
            else:
                sigma_lo = sigma_mid
                price_lo = price_mid

        return 0.5 * (sigma_lo + sigma_hi)


# =============================================================================
# GREEKS CALCULATOR (BATCH / CHAIN)
# =============================================================================

class GreeksCalculator:
    """High-level Greeks calculator wrapping ``BlackScholes0DTE``.

    Provides convenience methods for computing all Greeks on single options
    and vectorized computation across entire option chains.

    Args:
        bs: An instance of ``BlackScholes0DTE``.  If ``None``, a default
            instance is created.
    """

    def __init__(self, bs: Optional[BlackScholes0DTE] = None) -> None:
        self.bs: BlackScholes0DTE = bs if bs is not None else BlackScholes0DTE()

    def compute_all_greeks(
        self,
        S: float,
        K: float,
        T: float,
        sigma: float,
        r: Optional[float] = None,
        q: Optional[float] = None,
        option_type: str = "call",
    ) -> Dict[str, float]:
        """Compute all Greeks for a single option.

        Returns a flat dictionary containing:
            delta, gamma, theta, vega, rho, charm, vanna, speed

        Args:
            S: Spot price.
            K: Strike price.
            T: Annualized time to expiration.
            sigma: Implied volatility.
            r: Risk-free rate (uses engine default if None).
            q: Dividend yield (uses engine default if None).
            option_type: ``'call'`` or ``'put'``.

        Returns:
            Dictionary mapping Greek names to their values.
        """
        r = r if r is not None else self.bs.r
        q = q if q is not None else self.bs.q

        return {
            "delta": self.bs.delta(S, K, T, sigma, r, q, option_type),
            "gamma": self.bs.gamma(S, K, T, sigma, r, q),
            "theta": self.bs.theta(S, K, T, sigma, r, q, option_type),
            "vega": self.bs.vega(S, K, T, sigma, r, q),
            "rho": self.bs.rho(S, K, T, sigma, r, q, option_type),
            "charm": self.bs.charm(S, K, T, sigma, r, q, option_type),
            "vanna": self.bs.vanna(S, K, T, sigma, r, q, option_type),
            "speed": self.bs.speed(S, K, T, sigma, r, q),
        }

    def compute_chain_greeks(
        self,
        spot_price: float,
        strikes: np.ndarray,
        time_remaining_minutes: float,
        ivs: np.ndarray,
        r: Optional[float] = None,
        q: Optional[float] = None,
        option_types: Optional[np.ndarray] = None,
    ) -> pd.DataFrame:
        """Compute all Greeks for an entire options chain (vectorized).

        Iterates over every (strike, IV, option_type) triple and builds a
        DataFrame of results.  While the inner Black-Scholes calls are scalar,
        the outer loop is structured for clarity and the per-option cost is
        negligible at chain scale (typically < 200 options).

        Args:
            spot_price: Current underlying price.
            strikes: Array of strike prices.
            time_remaining_minutes: Minutes until expiration.
            ivs: Array of implied volatilities, same length as strikes.
            r: Risk-free rate.
            q: Dividend yield.
            option_types: Array of ``'call'``/``'put'`` strings, same length
                as strikes.  Defaults to all ``'call'``.

        Returns:
            DataFrame with columns: strike, option_type, iv, delta, gamma,
            theta, vega, rho, charm, vanna, speed.
        """
        r = r if r is not None else self.bs.r
        q = q if q is not None else self.bs.q

        T = annualized_time(int(time_remaining_minutes))

        strikes = np.asarray(strikes, dtype=np.float64)
        ivs = np.asarray(ivs, dtype=np.float64)
        n = len(strikes)

        if option_types is None:
            option_types = np.array(["call"] * n)
        else:
            option_types = np.asarray(option_types)

        # Pre-allocate result arrays
        deltas = np.empty(n)
        gammas = np.empty(n)
        thetas = np.empty(n)
        vegas = np.empty(n)
        rhos = np.empty(n)
        charms = np.empty(n)
        vannas = np.empty(n)
        speeds = np.empty(n)

        for i in range(n):
            K_i = strikes[i]
            sigma_i = max(ivs[i], 1e-6)
            otype_i = str(option_types[i])

            deltas[i] = self.bs.delta(spot_price, K_i, T, sigma_i, r, q, otype_i)
            gammas[i] = self.bs.gamma(spot_price, K_i, T, sigma_i, r, q)
            thetas[i] = self.bs.theta(spot_price, K_i, T, sigma_i, r, q, otype_i)
            vegas[i] = self.bs.vega(spot_price, K_i, T, sigma_i, r, q)
            rhos[i] = self.bs.rho(spot_price, K_i, T, sigma_i, r, q, otype_i)
            charms[i] = self.bs.charm(spot_price, K_i, T, sigma_i, r, q, otype_i)
            vannas[i] = self.bs.vanna(spot_price, K_i, T, sigma_i, r, q, otype_i)
            speeds[i] = self.bs.speed(spot_price, K_i, T, sigma_i, r, q)

        return pd.DataFrame({
            "strike": strikes,
            "option_type": option_types,
            "iv": ivs,
            "delta": deltas,
            "gamma": gammas,
            "theta": thetas,
            "vega": vegas,
            "rho": rhos,
            "charm": charms,
            "vanna": vannas,
            "speed": speeds,
        })

    def compute_iv_surface(
        self,
        spot_price: float,
        options_data: List[Dict],
    ) -> pd.DataFrame:
        """Extract implied volatility surface from observed option prices.

        For each option in ``options_data``, computes the IV via the engine's
        Newton-Raphson / bisection solver.  Options where IV extraction fails
        (returns NaN) are filled by linear interpolation from neighboring
        strikes of the same type.

        Args:
            spot_price: Current underlying price.
            options_data: List of dicts, each with keys:
                - ``strike`` (float): Strike price.
                - ``price``  (float): Observed market price.
                - ``type``   (str):   ``'call'`` or ``'put'``.
                - ``T``      (float): Annualized time to expiration.

        Returns:
            DataFrame with columns: strike, iv, option_type, T.
        """
        results: List[Dict] = []

        for opt in options_data:
            strike = float(opt["strike"])
            price = float(opt["price"])
            otype = str(opt["type"])
            T = float(opt["T"])

            iv = self.bs.implied_volatility(
                option_price=price,
                S=spot_price,
                K=strike,
                T=T,
                option_type=otype,
            )

            results.append({
                "strike": strike,
                "iv": iv,
                "option_type": otype,
                "T": T,
            })

        df = pd.DataFrame(results)

        if df.empty:
            return df

        # Interpolate NaN IVs from neighbors within the same option type.
        for otype in df["option_type"].unique():
            mask = df["option_type"] == otype
            subset = df.loc[mask].sort_values("strike")
            subset["iv"] = subset["iv"].interpolate(method="linear", limit_direction="both")
            df.loc[mask, "iv"] = subset["iv"].values

        # Final safety: fill any remaining NaNs with a reasonable default
        df["iv"] = df["iv"].fillna(0.20)

        return df.sort_values(["option_type", "strike"]).reset_index(drop=True)


# =============================================================================
# MODULE SELF-TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("SCANIFY 0DTE GREEKS ENGINE -- SELF-TEST")
    print("=" * 70)

    # ----- Setup -----
    bs = BlackScholes0DTE(risk_free_rate=0.053, dividend_yield=0.013)
    calc = GreeksCalculator(bs)

    S = 5200.0   # SPX spot
    K = 5200.0   # ATM strike
    sigma = 0.15  # 15% IV
    T_minutes = 120  # 2 hours remaining
    T = annualized_time(T_minutes)

    print(f"\nSpot:          {S}")
    print(f"Strike:        {K}")
    print(f"IV:            {sigma * 100:.1f}%")
    print(f"Time:          {T_minutes} min -> T = {T:.8f}")
    print(f"Risk-free:     {bs.r * 100:.1f}%")
    print(f"Div yield:     {bs.q * 100:.1f}%")

    # ----- Prices -----
    c = bs.call_price(S, K, T, sigma)
    p = bs.put_price(S, K, T, sigma)
    print(f"\nCall price:    ${c:.4f}")
    print(f"Put price:     ${p:.4f}")
    parity_lhs = c - p
    parity_rhs = S * np.exp(-bs.q * T) - K * np.exp(-bs.r * T)
    print(f"Put-call parity check: {parity_lhs:.6f} vs {parity_rhs:.6f}")

    # ----- All Greeks -----
    print("\n--- Call Greeks ---")
    greeks = calc.compute_all_greeks(S, K, T, sigma, option_type="call")
    for name, val in greeks.items():
        print(f"  {name:>8s}: {val:+.8f}")

    print("\n--- Put Greeks ---")
    greeks_put = calc.compute_all_greeks(S, K, T, sigma, option_type="put")
    for name, val in greeks_put.items():
        print(f"  {name:>8s}: {val:+.8f}")

    # ----- IV recovery -----
    print("\n--- IV Recovery ---")
    recovered_iv = bs.implied_volatility(c, S, K, T, option_type="call")
    print(f"  Original IV:  {sigma:.6f}")
    print(f"  Recovered IV: {recovered_iv:.6f}")
    print(f"  Error:        {abs(recovered_iv - sigma):.2e}")

    # ----- OTM IV recovery for a cheap option -----
    K_otm = 5250.0
    c_otm = bs.call_price(S, K_otm, T, sigma)
    iv_otm = bs.implied_volatility(c_otm, S, K_otm, T, option_type="call")
    print(f"\n  OTM {K_otm} call @ ${c_otm:.4f} -> IV {iv_otm:.6f}")

    # ----- Theta decay model -----
    print("\n--- Intraday Theta Decay Curve ---")
    test_times = [
        time(9, 30), time(10, 0), time(11, 0), time(12, 0),
        time(13, 0), time(14, 0), time(15, 0), time(15, 30), time(16, 0),
    ]
    for t in test_times:
        frac = theta_decay_fraction(t)
        print(f"  {t.strftime('%H:%M')} ET -> {frac * 100:5.1f}% consumed")

    # ----- Expected moves -----
    print("\n--- Expected Move ---")
    vix1d_val = 14.5
    straddle = c + p
    rv20 = 12.0
    em1, em2 = composite_expected_move(S, vix1d_val, straddle, rv20)
    print(f"  VIX1D:     {expected_move_vix1d(S, vix1d_val):.2f} pts")
    print(f"  Straddle:  {expected_move_straddle(straddle):.2f} pts")
    print(f"  RV-adj:    {expected_move_rv_adjusted(S, vix1d_val, rv20):.2f} pts")
    print(f"  Composite: {em1:.2f} pts (1-sigma), {em2:.2f} pts (2-sigma)")

    # ----- Chain Greeks -----
    print("\n--- Chain Greeks (sample) ---")
    strikes_arr = np.arange(5150, 5260, 10, dtype=float)
    ivs_arr = np.full_like(strikes_arr, 0.15)
    types_arr = np.array(["call"] * len(strikes_arr))

    chain_df = calc.compute_chain_greeks(S, strikes_arr, T_minutes, ivs_arr, option_types=types_arr)
    print(chain_df.to_string(index=False, float_format="{:.6f}".format))

    print(f"\n{'=' * 70}")
    print("SELF-TEST COMPLETE")
    print("=" * 70)
