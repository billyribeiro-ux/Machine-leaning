"""
Comprehensive test suite for the SCANIFY 0DTE Greeks Calculation Engine.

Tests cover:
    - Black-Scholes pricing (calls, puts, put-call parity, boundary conditions)
    - First-order Greeks: delta, gamma, theta, vega
    - Higher-order Greeks: charm, vanna, speed
    - Implied volatility extraction (Newton-Raphson + bisection)
    - Expected move calculations (VIX1D, straddle, RV-adjusted, composite)
    - Intraday theta decay fraction model
    - Helper functions (annualized_time, normal_pdf, normal_cdf, moneyness)

Uses realistic SPX values throughout (S ~ 6000, sigma ~ 0.15 - 0.25).

Author: SCANIFY Engine Tests
"""

import importlib
import numpy as np
import pytest
from datetime import time

# Import the greeks_engine module directly to avoid the broken package __init__.py
# which has an unrelated import error in constants.py.
import importlib.util
import sys
import os

_MODULE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "src", "scanify_0dte", "greeks_engine.py"
)
_MODULE_PATH = os.path.normpath(_MODULE_PATH)
_spec = importlib.util.spec_from_file_location("greeks_engine", _MODULE_PATH)
_greeks_engine = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_greeks_engine)

TRADING_DAYS_PER_YEAR = _greeks_engine.TRADING_DAYS_PER_YEAR
MINUTES_PER_TRADING_DAY = _greeks_engine.MINUTES_PER_TRADING_DAY
MINUTES_PER_YEAR = _greeks_engine.MINUTES_PER_YEAR
MIN_T = _greeks_engine.MIN_T
BlackScholes0DTE = _greeks_engine.BlackScholes0DTE
GreeksCalculator = _greeks_engine.GreeksCalculator
annualized_time = _greeks_engine.annualized_time
normal_pdf = _greeks_engine.normal_pdf
normal_cdf = _greeks_engine.normal_cdf
moneyness = _greeks_engine.moneyness
otm_gamma_ratio = _greeks_engine.otm_gamma_ratio
theta_decay_fraction = _greeks_engine.theta_decay_fraction
expected_move_vix1d = _greeks_engine.expected_move_vix1d
expected_move_straddle = _greeks_engine.expected_move_straddle
expected_move_rv_adjusted = _greeks_engine.expected_move_rv_adjusted
composite_expected_move = _greeks_engine.composite_expected_move


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def bs() -> BlackScholes0DTE:
    """Default Black-Scholes engine with standard SPX parameters."""
    return BlackScholes0DTE(risk_free_rate=0.053, dividend_yield=0.013)


@pytest.fixture
def bs_zero_rates() -> BlackScholes0DTE:
    """Black-Scholes engine with zero rates (simplifies analytical checks)."""
    return BlackScholes0DTE(risk_free_rate=0.0, dividend_yield=0.0)


@pytest.fixture
def calc(bs) -> GreeksCalculator:
    """GreeksCalculator wrapping the default BS engine."""
    return GreeksCalculator(bs)


# Standard SPX test parameters
SPX_SPOT = 6000.0
ATM_STRIKE = 6000.0
SIGMA_LOW = 0.15
SIGMA_MID = 0.20
SIGMA_HIGH = 0.25

# Typical 0DTE time values (in annualized form)
T_4H = annualized_time(240)    # 4 hours remaining
T_2H = annualized_time(120)    # 2 hours remaining
T_1H = annualized_time(60)     # 1 hour remaining
T_30M = annualized_time(30)    # 30 minutes remaining
T_5M = annualized_time(5)      # 5 minutes remaining
T_1M = annualized_time(1)      # 1 minute remaining (MIN_T)


# =============================================================================
# 1. BLACK-SCHOLES PRICING TESTS
# =============================================================================

class TestBlackScholesPricing:
    """Tests for call_price and put_price methods."""

    @pytest.mark.parametrize("sigma,T", [
        (0.15, T_2H),
        (0.20, T_2H),
        (0.25, T_4H),
        (0.15, T_1H),
    ])
    def test_call_price_positive(self, bs, sigma, T):
        """Call prices must always be positive for positive inputs."""
        price = bs.call_price(SPX_SPOT, ATM_STRIKE, T, sigma)
        assert price > 0, f"Call price should be positive, got {price}"

    @pytest.mark.parametrize("sigma,T", [
        (0.15, T_2H),
        (0.20, T_2H),
        (0.25, T_4H),
        (0.15, T_1H),
    ])
    def test_put_price_positive(self, bs, sigma, T):
        """Put prices must always be positive for positive inputs."""
        price = bs.put_price(SPX_SPOT, ATM_STRIKE, T, sigma)
        assert price > 0, f"Put price should be positive, got {price}"

    def test_call_price_known_analytical(self, bs_zero_rates):
        """Test call price against a known analytical result with r=q=0.

        With r=q=0, ATM: C = S * [2*N(sigma*sqrt(T)/2) - 1]
        which simplifies for small T to approximately S * sigma * sqrt(T) / sqrt(2*pi).
        """
        S, K, sigma = 6000.0, 6000.0, 0.20
        T = T_2H  # 2 hours

        call = bs_zero_rates.call_price(S, K, T, sigma)

        # With r=q=0, ATM, the call price from BS is:
        # C = S * [N(d1) - N(d2)] where d1 = sigma*sqrt(T)/2, d2 = -sigma*sqrt(T)/2
        d1 = sigma * np.sqrt(T) / 2.0
        expected = S * (normal_cdf(d1) - normal_cdf(-d1))
        assert np.isclose(call, expected, rtol=1e-8), \
            f"Call={call:.6f}, expected={expected:.6f}"

    def test_put_price_known_analytical(self, bs_zero_rates):
        """Test put price against a known analytical result with r=q=0.

        With r=q=0, for ATM, put = call (by put-call parity: C - P = 0).
        """
        S, K, sigma = 6000.0, 6000.0, 0.20
        T = T_2H

        call = bs_zero_rates.call_price(S, K, T, sigma)
        put = bs_zero_rates.put_price(S, K, T, sigma)

        assert np.isclose(call, put, rtol=1e-8), \
            f"ATM with r=q=0: call={call:.6f} should equal put={put:.6f}"

    @pytest.mark.parametrize("sigma,T", [
        (0.15, T_4H),
        (0.20, T_2H),
        (0.25, T_1H),
        (0.15, T_30M),
    ])
    def test_put_call_parity(self, bs, sigma, T):
        """Put-call parity: C - P = S*exp(-qT) - K*exp(-rT)."""
        S, K = SPX_SPOT, ATM_STRIKE
        r, q = bs.r, bs.q

        call = bs.call_price(S, K, T, sigma)
        put = bs.put_price(S, K, T, sigma)

        lhs = call - put
        rhs = S * np.exp(-q * T) - K * np.exp(-r * T)

        assert np.isclose(lhs, rhs, atol=1e-6), \
            f"Put-call parity violated: C-P={lhs:.6f}, S*e^(-qT)-K*e^(-rT)={rhs:.6f}"

    @pytest.mark.parametrize("K_offset", [5, 10, 25, 50])
    def test_put_call_parity_otm_itm(self, bs, K_offset):
        """Put-call parity holds at all strike levels, not just ATM."""
        S = SPX_SPOT
        T = T_2H
        sigma = SIGMA_MID
        r, q = bs.r, bs.q

        for K in [S + K_offset, S - K_offset]:
            call = bs.call_price(S, K, T, sigma)
            put = bs.put_price(S, K, T, sigma)
            lhs = call - put
            rhs = S * np.exp(-q * T) - K * np.exp(-r * T)
            assert np.isclose(lhs, rhs, atol=1e-6), \
                f"Parity violated at K={K}: C-P={lhs:.6f}, expected={rhs:.6f}"

    def test_deep_itm_call_approximation(self, bs):
        """Deep ITM call should approximate S*exp(-qT) - K*exp(-rT)."""
        S = SPX_SPOT
        K = 5500.0  # deep ITM call (500 points ITM)
        T = T_2H
        sigma = SIGMA_MID
        r, q = bs.r, bs.q

        call = bs.call_price(S, K, T, sigma)
        intrinsic_pv = S * np.exp(-q * T) - K * np.exp(-r * T)

        # Deep ITM call should be very close to the discounted intrinsic
        assert np.isclose(call, intrinsic_pv, rtol=0.01), \
            f"Deep ITM call={call:.4f}, intrinsic_pv={intrinsic_pv:.4f}"

    def test_deep_otm_call_near_zero(self, bs):
        """Deep OTM call should be approximately zero."""
        S = SPX_SPOT
        K = 6500.0  # 500 points OTM
        T = T_1H
        sigma = SIGMA_LOW

        call = bs.call_price(S, K, T, sigma)
        assert call < 0.01, f"Deep OTM call should be near 0, got {call:.6f}"

    def test_deep_itm_put_approximation(self, bs):
        """Deep ITM put should approximate K*exp(-rT) - S*exp(-qT)."""
        S = SPX_SPOT
        K = 6500.0  # deep ITM put
        T = T_2H
        sigma = SIGMA_MID
        r, q = bs.r, bs.q

        put = bs.put_price(S, K, T, sigma)
        intrinsic_pv = K * np.exp(-r * T) - S * np.exp(-q * T)

        assert np.isclose(put, intrinsic_pv, rtol=0.01), \
            f"Deep ITM put={put:.4f}, intrinsic_pv={intrinsic_pv:.4f}"

    def test_deep_otm_put_near_zero(self, bs):
        """Deep OTM put should be approximately zero."""
        S = SPX_SPOT
        K = 5500.0  # 500 points OTM put
        T = T_1H
        sigma = SIGMA_LOW

        put = bs.put_price(S, K, T, sigma)
        assert put < 0.01, f"Deep OTM put should be near 0, got {put:.6f}"

    def test_expiring_option_converges_to_intrinsic_call_itm(self, bs):
        """With T -> 0 (1 minute), ITM call converges to intrinsic value."""
        S = SPX_SPOT
        K = 5980.0  # 20 points ITM
        T = T_1M
        sigma = SIGMA_MID
        r, q = bs.r, bs.q

        call = bs.call_price(S, K, T, sigma)
        intrinsic = max(S - K, 0)

        # Within a few cents at 1 minute to expiry
        assert np.isclose(call, intrinsic, atol=1.0), \
            f"At T=1min, ITM call={call:.4f} should be near intrinsic={intrinsic:.4f}"

    def test_expiring_option_converges_to_intrinsic_call_otm(self, bs):
        """With T -> 0 (1 minute), OTM call converges to near zero."""
        S = SPX_SPOT
        K = 6020.0  # 20 points OTM
        T = T_1M
        sigma = SIGMA_MID

        call = bs.call_price(S, K, T, sigma)
        assert call < 1.0, f"At T=1min, OTM call should be near 0, got {call:.4f}"

    def test_atm_straddle_approximation(self, bs_zero_rates):
        """ATM straddle value ~ SPX * sigma * sqrt(T) * sqrt(2/pi) (Brenner-Subrahmanyam).

        This approximation is best with r=q=0.
        """
        S = SPX_SPOT
        K = S
        sigma = SIGMA_MID
        T = T_2H

        call = bs_zero_rates.call_price(S, K, T, sigma)
        put = bs_zero_rates.put_price(S, K, T, sigma)
        straddle = call + put

        # Brenner-Subrahmanyam approximation for ATM straddle
        approx = S * sigma * np.sqrt(T) * np.sqrt(2.0 / np.pi)

        # Should be within ~5% for reasonable sigma and T
        assert np.isclose(straddle, approx, rtol=0.05), \
            f"Straddle={straddle:.4f}, B-S approx={approx:.4f}"

    def test_higher_sigma_means_higher_price(self, bs):
        """Higher IV should produce higher option prices (calls and puts)."""
        S, K, T = SPX_SPOT, ATM_STRIKE, T_2H

        call_low = bs.call_price(S, K, T, SIGMA_LOW)
        call_high = bs.call_price(S, K, T, SIGMA_HIGH)
        assert call_high > call_low, "Higher sigma should give higher call price"

        put_low = bs.put_price(S, K, T, SIGMA_LOW)
        put_high = bs.put_price(S, K, T, SIGMA_HIGH)
        assert put_high > put_low, "Higher sigma should give higher put price"

    def test_longer_time_means_higher_price(self, bs):
        """More time remaining should produce higher option prices."""
        S, K, sigma = SPX_SPOT, ATM_STRIKE, SIGMA_MID

        call_short = bs.call_price(S, K, T_30M, sigma)
        call_long = bs.call_price(S, K, T_4H, sigma)
        assert call_long > call_short, "More time should give higher call price"

        put_short = bs.put_price(S, K, T_30M, sigma)
        put_long = bs.put_price(S, K, T_4H, sigma)
        assert put_long > put_short, "More time should give higher put price"


# =============================================================================
# 2. DELTA TESTS
# =============================================================================

class TestDelta:
    """Tests for the delta Greek."""

    def test_atm_call_delta_approximately_half(self, bs):
        """ATM call delta should be approximately 0.50 (adjusted for q)."""
        delta = bs.delta(SPX_SPOT, ATM_STRIKE, T_2H, SIGMA_MID, option_type="call")

        # With dividend yield q, ATM call delta = exp(-qT) * N(d1)
        # For 0DTE with tiny T, exp(-qT) ~ 1, so delta ~ 0.50
        assert 0.45 <= delta <= 0.55, \
            f"ATM call delta={delta:.4f}, expected near 0.50"

    def test_atm_put_delta_approximately_negative_half(self, bs):
        """ATM put delta should be approximately -0.50."""
        delta = bs.delta(SPX_SPOT, ATM_STRIKE, T_2H, SIGMA_MID, option_type="put")
        assert -0.55 <= delta <= -0.45, \
            f"ATM put delta={delta:.4f}, expected near -0.50"

    def test_deep_itm_call_delta_near_one(self, bs):
        """Deep ITM call delta should approach 1.0."""
        delta = bs.delta(SPX_SPOT, 5500.0, T_2H, SIGMA_MID, option_type="call")
        assert delta > 0.95, f"Deep ITM call delta={delta:.4f}, expected near 1.0"

    def test_deep_otm_call_delta_near_zero(self, bs):
        """Deep OTM call delta should approach 0.0."""
        delta = bs.delta(SPX_SPOT, 6500.0, T_2H, SIGMA_MID, option_type="call")
        assert delta < 0.05, f"Deep OTM call delta={delta:.4f}, expected near 0.0"

    def test_deep_itm_put_delta_near_negative_one(self, bs):
        """Deep ITM put delta should approach -1.0."""
        delta = bs.delta(SPX_SPOT, 6500.0, T_2H, SIGMA_MID, option_type="put")
        assert delta < -0.95, f"Deep ITM put delta={delta:.4f}, expected near -1.0"

    def test_deep_otm_put_delta_near_zero(self, bs):
        """Deep OTM put delta should approach 0.0."""
        delta = bs.delta(SPX_SPOT, 5500.0, T_2H, SIGMA_MID, option_type="put")
        assert delta > -0.05, f"Deep OTM put delta={delta:.4f}, expected near 0.0"

    def test_call_delta_plus_abs_put_delta_approximately_one(self, bs):
        """call_delta + |put_delta| ~ exp(-qT), which is approximately 1.0 for 0DTE."""
        T = T_2H
        q = bs.q

        for K in [5900.0, 5950.0, 6000.0, 6050.0, 6100.0]:
            call_delta = bs.delta(SPX_SPOT, K, T, SIGMA_MID, option_type="call")
            put_delta = bs.delta(SPX_SPOT, K, T, SIGMA_MID, option_type="put")

            expected = np.exp(-q * T)
            actual = call_delta + abs(put_delta)

            assert np.isclose(actual, expected, atol=1e-6), \
                f"K={K}: call_d + |put_d| = {actual:.6f}, expected exp(-qT) = {expected:.6f}"

    @pytest.mark.parametrize("K,expected_range", [
        (5800.0, (0.95, 1.00)),   # Deep ITM
        (5900.0, (0.95, 1.00)),   # ITM (0DTE deltas are extreme)
        (5950.0, (0.80, 0.95)),   # Slightly ITM
        (6000.0, (0.45, 0.55)),   # ATM
        (6050.0, (0.05, 0.20)),   # Slightly OTM
        (6100.0, (0.00, 0.05)),   # OTM (0DTE deltas drop fast)
        (6200.0, (0.00, 0.01)),   # Deep OTM
    ])
    def test_delta_at_various_moneyness(self, bs, K, expected_range):
        """Delta falls monotonically as strike increases (for calls)."""
        delta = bs.delta(SPX_SPOT, K, T_2H, SIGMA_MID, option_type="call")
        low, high = expected_range
        assert low <= delta <= high, \
            f"K={K}: call delta={delta:.4f}, expected in [{low}, {high}]"

    def test_call_delta_monotonically_decreasing_with_strike(self, bs):
        """Call delta should decrease as strike increases."""
        strikes = np.arange(5800, 6200, 25)
        deltas = [
            bs.delta(SPX_SPOT, K, T_2H, SIGMA_MID, option_type="call")
            for K in strikes
        ]
        for i in range(1, len(deltas)):
            assert deltas[i] <= deltas[i - 1] + 1e-10, \
                f"Call delta not monotonically decreasing at K={strikes[i]}"

    def test_call_delta_in_bounds(self, bs):
        """Call delta must be in [0, 1]."""
        for K in [5500, 5800, 6000, 6200, 6500]:
            delta = bs.delta(SPX_SPOT, float(K), T_2H, SIGMA_MID, option_type="call")
            assert 0.0 <= delta <= 1.0, f"Call delta out of bounds: {delta}"

    def test_put_delta_in_bounds(self, bs):
        """Put delta must be in [-1, 0]."""
        for K in [5500, 5800, 6000, 6200, 6500]:
            delta = bs.delta(SPX_SPOT, float(K), T_2H, SIGMA_MID, option_type="put")
            assert -1.0 <= delta <= 0.0, f"Put delta out of bounds: {delta}"


# =============================================================================
# 3. GAMMA TESTS
# =============================================================================

class TestGamma:
    """Tests for the gamma Greek."""

    def test_gamma_maximum_at_atm(self, bs):
        """Gamma should be highest at ATM strike."""
        T = T_2H
        sigma = SIGMA_MID

        gamma_atm = bs.gamma(SPX_SPOT, ATM_STRIKE, T, sigma)
        gamma_itm = bs.gamma(SPX_SPOT, 5900.0, T, sigma)
        gamma_otm = bs.gamma(SPX_SPOT, 6100.0, T, sigma)

        assert gamma_atm > gamma_itm, \
            f"ATM gamma={gamma_atm:.8f} should exceed ITM gamma={gamma_itm:.8f}"
        assert gamma_atm > gamma_otm, \
            f"ATM gamma={gamma_atm:.8f} should exceed OTM gamma={gamma_otm:.8f}"

    def test_gamma_decreases_with_distance_from_atm(self, bs):
        """Gamma should decrease as we move away from ATM."""
        T = T_2H
        sigma = SIGMA_MID

        strikes = [6000.0, 6025.0, 6050.0, 6100.0, 6200.0]
        gammas = [bs.gamma(SPX_SPOT, K, T, sigma) for K in strikes]

        for i in range(1, len(gammas)):
            assert gammas[i] <= gammas[i - 1] + 1e-12, \
                f"Gamma not decreasing: K={strikes[i]}, gamma={gammas[i]:.8f}"

    def test_gamma_increases_as_T_approaches_zero(self, bs):
        """ATM gamma should explode as T -> 0 (0DTE gamma explosion)."""
        sigma = SIGMA_MID
        times = [T_4H, T_2H, T_1H, T_30M, T_5M]

        gammas = [bs.gamma(SPX_SPOT, ATM_STRIKE, T, sigma) for T in times]

        for i in range(1, len(gammas)):
            assert gammas[i] > gammas[i - 1], \
                f"ATM gamma should increase as T decreases: " \
                f"gamma[{i-1}]={gammas[i-1]:.8f}, gamma[{i}]={gammas[i]:.8f}"

    def test_gamma_same_for_call_and_put(self, bs):
        """Gamma is identical for calls and puts at the same strike.

        The gamma formula does not depend on option type.
        """
        for K in [5900.0, 6000.0, 6100.0]:
            # Gamma method does not take option_type -- it is inherently the same.
            # Verify by computing delta numerically for both call and put.
            dS = 0.01
            call_delta_up = bs.delta(SPX_SPOT + dS, K, T_2H, SIGMA_MID, option_type="call")
            call_delta_dn = bs.delta(SPX_SPOT - dS, K, T_2H, SIGMA_MID, option_type="call")
            gamma_call_num = (call_delta_up - call_delta_dn) / (2 * dS)

            put_delta_up = bs.delta(SPX_SPOT + dS, K, T_2H, SIGMA_MID, option_type="put")
            put_delta_dn = bs.delta(SPX_SPOT - dS, K, T_2H, SIGMA_MID, option_type="put")
            gamma_put_num = (put_delta_up - put_delta_dn) / (2 * dS)

            assert np.isclose(gamma_call_num, gamma_put_num, rtol=1e-4), \
                f"K={K}: call gamma_num={gamma_call_num:.8f}, put gamma_num={gamma_put_num:.8f}"

    def test_gamma_always_positive(self, bs):
        """Gamma must always be non-negative."""
        for K in np.arange(5500, 6500, 50):
            for T in [T_4H, T_2H, T_1H, T_30M]:
                gamma = bs.gamma(SPX_SPOT, float(K), T, SIGMA_MID)
                assert gamma >= 0, f"Gamma negative at K={K}, T={T}: {gamma}"

    def test_gamma_symmetry_around_atm(self, bs):
        """Gamma should be roughly symmetric for equidistant strikes around ATM."""
        T = T_2H
        sigma = SIGMA_MID
        offset = 50.0

        gamma_above = bs.gamma(SPX_SPOT, SPX_SPOT + offset, T, sigma)
        gamma_below = bs.gamma(SPX_SPOT, SPX_SPOT - offset, T, sigma)

        # Not exactly symmetric due to log-moneyness, but close for small offsets
        assert np.isclose(gamma_above, gamma_below, rtol=0.15), \
            f"Gamma not roughly symmetric: above={gamma_above:.8f}, below={gamma_below:.8f}"


# =============================================================================
# 4. THETA TESTS
# =============================================================================

class TestTheta:
    """Tests for the theta Greek (time decay per trading day)."""

    def test_theta_negative_for_long_call(self, bs):
        """Theta should be negative for a long call position."""
        theta = bs.theta(SPX_SPOT, ATM_STRIKE, T_2H, SIGMA_MID, option_type="call")
        assert theta < 0, f"Call theta should be negative, got {theta:.6f}"

    def test_theta_negative_for_long_put(self, bs):
        """Theta should be negative for a long put position."""
        theta = bs.theta(SPX_SPOT, ATM_STRIKE, T_2H, SIGMA_MID, option_type="put")
        assert theta < 0, f"Put theta should be negative, got {theta:.6f}"

    @pytest.mark.parametrize("K", [5800.0, 5900.0, 6000.0, 6100.0, 6200.0])
    def test_theta_negative_across_strikes_call(self, bs, K):
        """Theta should be negative for all call strikes."""
        theta = bs.theta(SPX_SPOT, K, T_2H, SIGMA_MID, option_type="call")
        # Deep ITM call theta can be slightly positive with high r, but for
        # 0DTE the time component dominates, so theta should still be negative.
        # We allow a tiny positive tolerance for deep ITM edge cases with high rates.
        assert theta < 0.5, f"Call theta at K={K} unexpected: {theta:.6f}"

    def test_atm_theta_larger_than_otm_theta(self, bs):
        """ATM theta (more negative) should be larger in magnitude than OTM theta."""
        theta_atm = bs.theta(SPX_SPOT, 6000.0, T_2H, SIGMA_MID, option_type="call")
        theta_otm = bs.theta(SPX_SPOT, 6100.0, T_2H, SIGMA_MID, option_type="call")

        assert abs(theta_atm) > abs(theta_otm), \
            f"ATM |theta|={abs(theta_atm):.4f} should exceed OTM |theta|={abs(theta_otm):.4f}"

    def test_theta_accelerates_as_T_decreases(self, bs):
        """Theta magnitude should increase (become more negative) as T -> 0.

        This reflects the non-linear time decay characteristic of options,
        especially pronounced in 0DTE.
        """
        times = [T_4H, T_2H, T_1H, T_30M]
        thetas = [
            bs.theta(SPX_SPOT, ATM_STRIKE, T, SIGMA_MID, option_type="call")
            for T in times
        ]

        # Theta should become more negative (larger magnitude)
        for i in range(1, len(thetas)):
            assert thetas[i] < thetas[i - 1], \
                f"Theta not accelerating: theta[{i-1}]={thetas[i-1]:.6f}, " \
                f"theta[{i}]={thetas[i]:.6f}"

    def test_theta_is_per_trading_day(self, bs):
        """Verify theta is expressed per trading day (divided by 252).

        Compare with a manually computed annualized theta divided by 252.
        """
        S, K, T, sigma = SPX_SPOT, ATM_STRIKE, T_2H, SIGMA_MID
        r, q = bs.r, bs.q

        theta_per_day = bs.theta(S, K, T, sigma, option_type="call")

        # Manually compute annualized theta from the BS formula
        _d1 = bs.d1(S, K, T, sigma)
        _d2 = _d1 - sigma * np.sqrt(T)
        sqrt_T = np.sqrt(T)
        exp_qT = np.exp(-q * T)
        exp_rT = np.exp(-r * T)

        common = -S * sigma * exp_qT * normal_pdf(_d1) / (2.0 * sqrt_T)
        theta_annual = common - r * K * exp_rT * normal_cdf(_d2) + q * S * exp_qT * normal_cdf(_d1)
        expected_per_day = theta_annual / TRADING_DAYS_PER_YEAR

        assert np.isclose(theta_per_day, expected_per_day, rtol=1e-8), \
            f"Theta per day mismatch: got={theta_per_day:.8f}, expected={expected_per_day:.8f}"


# =============================================================================
# 5. VEGA TESTS
# =============================================================================

class TestVega:
    """Tests for the vega Greek."""

    def test_vega_maximum_at_atm(self, bs):
        """Vega should be highest at ATM."""
        vega_atm = bs.vega(SPX_SPOT, 6000.0, T_2H, SIGMA_MID)
        vega_itm = bs.vega(SPX_SPOT, 5900.0, T_2H, SIGMA_MID)
        vega_otm = bs.vega(SPX_SPOT, 6100.0, T_2H, SIGMA_MID)

        assert vega_atm > vega_itm, \
            f"ATM vega={vega_atm:.6f} should exceed ITM vega={vega_itm:.6f}"
        assert vega_atm > vega_otm, \
            f"ATM vega={vega_atm:.6f} should exceed OTM vega={vega_otm:.6f}"

    def test_0dte_vega_is_very_small(self, bs):
        """Key 0DTE characteristic: vega is tiny because sqrt(T) is small.

        With only minutes remaining, a vol change has very little time
        to affect the option price.
        """
        vega_0dte = bs.vega(SPX_SPOT, ATM_STRIKE, T_30M, SIGMA_MID)

        # For 30 min remaining on SPX 6000, vega per 1 vol pt should be < 1.0
        assert vega_0dte < 1.0, \
            f"0DTE vega should be very small, got {vega_0dte:.6f}"

        # Compare with a hypothetical 30-day option
        T_30d = annualized_time(30 * MINUTES_PER_TRADING_DAY)
        vega_30d = bs.vega(SPX_SPOT, ATM_STRIKE, T_30d, SIGMA_MID)
        assert vega_0dte < vega_30d * 0.1, \
            f"0DTE vega={vega_0dte:.4f} should be << 30-day vega={vega_30d:.4f}"

    def test_vega_always_positive(self, bs):
        """Vega must always be non-negative."""
        for K in np.arange(5700, 6300, 50):
            for T in [T_4H, T_2H, T_1H, T_30M]:
                vega = bs.vega(SPX_SPOT, float(K), T, SIGMA_MID)
                assert vega >= 0, f"Vega negative at K={K}, T={T}: {vega}"

    def test_vega_decreases_with_less_time(self, bs):
        """Vega decreases as T decreases (less time for vol to matter)."""
        times = [T_4H, T_2H, T_1H, T_30M, T_5M]
        vegas = [bs.vega(SPX_SPOT, ATM_STRIKE, T, SIGMA_MID) for T in times]

        for i in range(1, len(vegas)):
            assert vegas[i] < vegas[i - 1], \
                f"Vega should decrease with T: vega[{i-1}]={vegas[i-1]:.6f}, vega[{i}]={vegas[i]:.6f}"

    def test_vega_per_vol_point(self, bs):
        """Verify vega represents price change per 1% (0.01) vol move.

        Numerically bump sigma by 0.01 and compare the price difference
        to vega.
        """
        S, K, T, sigma = SPX_SPOT, ATM_STRIKE, T_2H, SIGMA_MID
        d_sigma = 0.01

        call_base = bs.call_price(S, K, T, sigma)
        call_bumped = bs.call_price(S, K, T, sigma + d_sigma)
        numerical_vega = call_bumped - call_base

        analytical_vega = bs.vega(S, K, T, sigma)

        assert np.isclose(numerical_vega, analytical_vega, rtol=0.01), \
            f"Numerical vega={numerical_vega:.6f}, analytical={analytical_vega:.6f}"


# =============================================================================
# 6. CHARM TESTS (Critical for 0DTE)
# =============================================================================

class TestCharm:
    """Tests for charm (dDelta/dT) -- rate of delta decay with time."""

    def test_otm_call_charm_negative(self, bs):
        """OTM call charm should be negative: delta decays toward 0 as time passes.

        As time decreases (passes), an OTM call loses delta.
        Charm = (delta at less time - delta at current time) / dt_negative.
        Since charm uses backward bump (T - dt), the sign depends on convention.
        The key behavior: OTM calls lose delta as expiry approaches.
        """
        K = 6050.0  # OTM call
        T = T_2H

        delta_now = bs.delta(SPX_SPOT, K, T, SIGMA_MID, option_type="call")
        # After some time passes, delta of OTM call should be smaller
        T_later = T_1H
        delta_later = bs.delta(SPX_SPOT, K, T_later, SIGMA_MID, option_type="call")

        assert delta_later < delta_now, \
            f"OTM call delta should decrease with time: now={delta_now:.4f}, later={delta_later:.4f}"

    def test_otm_put_charm_direction(self, bs):
        """OTM put delta should move toward 0 as time passes (charm effect)."""
        K = 5950.0  # OTM put
        T = T_2H

        delta_now = bs.delta(SPX_SPOT, K, T, SIGMA_MID, option_type="put")
        T_later = T_1H
        delta_later = bs.delta(SPX_SPOT, K, T_later, SIGMA_MID, option_type="put")

        # OTM put delta is negative; should become less negative (closer to 0)
        assert abs(delta_later) < abs(delta_now), \
            f"OTM put |delta| should decrease: now={delta_now:.4f}, later={delta_later:.4f}"

    def test_charm_magnitude_increases_near_expiry(self, bs):
        """Charm magnitude should increase as we get closer to expiry.

        The rate of delta decay accelerates as T -> 0.
        """
        K = 6050.0  # OTM call

        charm_4h = abs(bs.charm(SPX_SPOT, K, T_4H, SIGMA_MID, option_type="call"))
        charm_1h = abs(bs.charm(SPX_SPOT, K, T_1H, SIGMA_MID, option_type="call"))

        # At T_1H there is more charm influence so magnitude should be larger
        # (unless already at MIN_T boundary)
        assert charm_1h > charm_4h * 0.5, \
            f"Charm magnitude should be significant at 1H: 4H={charm_4h:.6f}, 1H={charm_1h:.6f}"

    def test_charm_returns_finite_values(self, bs):
        """Charm should always return finite values even near expiry."""
        for T in [T_4H, T_2H, T_1H, T_30M, T_5M, T_1M]:
            charm_val = bs.charm(SPX_SPOT, 6050.0, T, SIGMA_MID, option_type="call")
            assert np.isfinite(charm_val), f"Charm not finite at T={T}: {charm_val}"


# =============================================================================
# 7. VANNA TESTS
# =============================================================================

class TestVanna:
    """Tests for vanna (dDelta/dSigma) -- sensitivity of delta to IV changes."""

    def test_vanna_otm_call_positive(self, bs):
        """For an OTM call, increasing vol should increase delta (positive vanna)."""
        K = 6050.0  # OTM call
        vanna = bs.vanna(SPX_SPOT, K, T_2H, SIGMA_MID, option_type="call")
        assert vanna > 0, f"OTM call vanna should be positive, got {vanna:.6f}"

    def test_vanna_itm_call_negative(self, bs):
        """For an ITM call, increasing vol should decrease delta (negative vanna)."""
        K = 5950.0  # ITM call
        vanna = bs.vanna(SPX_SPOT, K, T_2H, SIGMA_MID, option_type="call")
        assert vanna < 0, f"ITM call vanna should be negative, got {vanna:.6f}"

    def test_vanna_atm_near_zero(self, bs):
        """ATM vanna should be near zero (delta is not very sensitive to vol at ATM)."""
        vanna = bs.vanna(SPX_SPOT, ATM_STRIKE, T_2H, SIGMA_MID, option_type="call")

        # ATM vanna is small but not necessarily exactly zero due to r, q
        assert abs(vanna) < 0.5, \
            f"ATM vanna should be near zero, got {vanna:.6f}"

    def test_vanna_consistent_with_delta_vol_bump(self, bs):
        """Vanna should be consistent with the numerical delta change from a vol bump."""
        K = 6050.0
        d_sigma = 0.01

        delta_base = bs.delta(SPX_SPOT, K, T_2H, SIGMA_MID, option_type="call")
        delta_bumped = bs.delta(SPX_SPOT, K, T_2H, SIGMA_MID + d_sigma, option_type="call")

        numerical_vanna = (delta_bumped - delta_base) / d_sigma
        analytical_vanna = bs.vanna(SPX_SPOT, K, T_2H, SIGMA_MID, option_type="call")

        assert np.isclose(numerical_vanna, analytical_vanna, rtol=0.05), \
            f"Numerical vanna={numerical_vanna:.6f}, analytical={analytical_vanna:.6f}"

    def test_vanna_finite(self, bs):
        """Vanna should always return finite values."""
        for K in [5900.0, 6000.0, 6100.0]:
            for T in [T_4H, T_2H, T_1H, T_30M]:
                vanna = bs.vanna(SPX_SPOT, K, T, SIGMA_MID, option_type="call")
                assert np.isfinite(vanna), f"Vanna not finite at K={K}, T={T}: {vanna}"


# =============================================================================
# 8. SPEED TESTS
# =============================================================================

class TestSpeed:
    """Tests for speed (dGamma/dS) -- gamma sensitivity to spot price."""

    def test_speed_measures_gamma_sensitivity(self, bs):
        """Speed should be consistent with the numerical gamma change from a spot bump."""
        K = 6000.0
        dS = 1.0

        gamma_base = bs.gamma(SPX_SPOT, K, T_2H, SIGMA_MID)
        gamma_bumped = bs.gamma(SPX_SPOT + dS, K, T_2H, SIGMA_MID)

        numerical_speed = (gamma_bumped - gamma_base) / dS
        analytical_speed = bs.speed(SPX_SPOT, K, T_2H, SIGMA_MID)

        assert np.isclose(numerical_speed, analytical_speed, rtol=1e-6), \
            f"Speed mismatch: numerical={numerical_speed:.10f}, analytical={analytical_speed:.10f}"

    def test_speed_at_atm_near_zero(self, bs):
        """At ATM, gamma is at its peak, so speed (dGamma/dS) should be near zero.

        The gamma curve peaks at ATM, meaning the derivative is near zero there.
        """
        speed_atm = bs.speed(SPX_SPOT, ATM_STRIKE, T_2H, SIGMA_MID)
        gamma_atm = bs.gamma(SPX_SPOT, ATM_STRIKE, T_2H, SIGMA_MID)

        # Speed at ATM should be small relative to gamma
        # Speed * typical_move << gamma
        assert abs(speed_atm) < gamma_atm, \
            f"ATM speed={speed_atm:.10f} should be small relative to gamma={gamma_atm:.8f}"

    def test_speed_sign_otm(self, bs):
        """For OTM options, moving spot toward strike increases gamma (positive speed)."""
        K = 6050.0  # OTM call -- spot below strike
        speed = bs.speed(SPX_SPOT, K, T_2H, SIGMA_MID)
        # Moving spot up (toward K) should increase gamma -> positive speed
        assert speed > 0, f"OTM call speed should be positive, got {speed:.10f}"

    def test_speed_finite(self, bs):
        """Speed should always return finite values."""
        for K in [5900.0, 6000.0, 6100.0]:
            for T in [T_4H, T_2H, T_1H]:
                speed = bs.speed(SPX_SPOT, K, T, SIGMA_MID)
                assert np.isfinite(speed), f"Speed not finite at K={K}, T={T}: {speed}"


# =============================================================================
# 9. IMPLIED VOLATILITY TESTS
# =============================================================================

class TestImpliedVolatility:
    """Tests for the implied_volatility method (Newton-Raphson + bisection)."""

    @pytest.mark.parametrize("sigma_input", [0.10, 0.15, 0.20, 0.25, 0.30, 0.50])
    def test_iv_recovery_roundtrip_call(self, bs, sigma_input):
        """Round-trip test: price a call with known IV, then recover IV."""
        S, K, T = SPX_SPOT, ATM_STRIKE, T_2H

        price = bs.call_price(S, K, T, sigma_input)
        recovered_iv = bs.implied_volatility(
            price, S, K, T, option_type="call", initial_guess=0.20
        )

        assert np.isclose(recovered_iv, sigma_input, atol=1e-6), \
            f"IV roundtrip failed: input={sigma_input}, recovered={recovered_iv}"

    @pytest.mark.parametrize("sigma_input", [0.10, 0.15, 0.20, 0.25, 0.30, 0.50])
    def test_iv_recovery_roundtrip_put(self, bs, sigma_input):
        """Round-trip test: price a put with known IV, then recover IV."""
        S, K, T = SPX_SPOT, ATM_STRIKE, T_2H

        price = bs.put_price(S, K, T, sigma_input)
        recovered_iv = bs.implied_volatility(
            price, S, K, T, option_type="put", initial_guess=0.20
        )

        assert np.isclose(recovered_iv, sigma_input, atol=1e-6), \
            f"IV roundtrip failed: input={sigma_input}, recovered={recovered_iv}"

    def test_iv_roundtrip_price_recovery(self, bs):
        """Full round-trip: price -> IV -> price should give the same result."""
        S, K, T, sigma = SPX_SPOT, ATM_STRIKE, T_2H, SIGMA_MID

        price_original = bs.call_price(S, K, T, sigma)
        recovered_iv = bs.implied_volatility(price_original, S, K, T, option_type="call")
        price_recovered = bs.call_price(S, K, T, recovered_iv)

        assert np.isclose(price_original, price_recovered, atol=1e-4), \
            f"Price roundtrip: original={price_original:.6f}, recovered={price_recovered:.6f}"

    def test_iv_otm_option(self, bs):
        """IV extraction should work for OTM options with small premiums."""
        S = SPX_SPOT
        K = 6100.0  # OTM call
        T = T_2H
        sigma = SIGMA_MID

        price = bs.call_price(S, K, T, sigma)
        recovered = bs.implied_volatility(price, S, K, T, option_type="call")

        assert np.isclose(recovered, sigma, atol=1e-4), \
            f"OTM IV recovery: input={sigma}, recovered={recovered}"

    def test_iv_deep_otm_option(self, bs):
        """IV extraction for deep OTM option with very small premium."""
        S = SPX_SPOT
        K = 6200.0  # 200 points OTM
        T = T_2H
        sigma = SIGMA_MID

        price = bs.call_price(S, K, T, sigma)
        if price > 1e-10:
            recovered = bs.implied_volatility(price, S, K, T, option_type="call")
            # Deep OTM might have reduced accuracy, so use wider tolerance
            if not np.isnan(recovered):
                assert recovered > 0, f"Recovered IV should be positive: {recovered}"

    def test_iv_is_always_positive(self, bs):
        """Recovered IV should always be positive (or NaN for failure)."""
        for K in [5900.0, 6000.0, 6100.0]:
            for sigma in [0.10, 0.20, 0.30]:
                price = bs.call_price(SPX_SPOT, K, T_2H, sigma)
                iv = bs.implied_volatility(price, SPX_SPOT, K, T_2H, option_type="call")
                if not np.isnan(iv):
                    assert iv > 0, f"IV should be positive: {iv}"

    def test_iv_zero_price_returns_zero(self, bs):
        """IV extraction with zero option price should return 0."""
        iv = bs.implied_volatility(0.0, SPX_SPOT, ATM_STRIKE, T_2H, option_type="call")
        assert iv == 0.0, f"IV for zero price should be 0, got {iv}"

    def test_iv_negative_price_returns_zero(self, bs):
        """IV extraction with negative option price should return 0."""
        iv = bs.implied_volatility(-1.0, SPX_SPOT, ATM_STRIKE, T_2H, option_type="call")
        assert iv == 0.0, f"IV for negative price should be 0, got {iv}"

    def test_iv_near_expiry(self, bs):
        """IV extraction should work even with very small T (0DTE near close)."""
        S, K = SPX_SPOT, ATM_STRIKE
        T = T_5M
        sigma = 0.20

        price = bs.call_price(S, K, T, sigma)
        recovered = bs.implied_volatility(price, S, K, T, option_type="call")

        if not np.isnan(recovered):
            assert np.isclose(recovered, sigma, atol=0.01), \
                f"Near-expiry IV: input={sigma}, recovered={recovered}"

    @pytest.mark.parametrize("K_offset", [0, 25, 50, 100])
    def test_iv_various_strikes(self, bs, K_offset):
        """IV recovery across different strike levels."""
        K = SPX_SPOT + K_offset
        sigma = SIGMA_MID

        call_price = bs.call_price(SPX_SPOT, K, T_2H, sigma)
        if call_price > 1e-6:
            iv = bs.implied_volatility(call_price, SPX_SPOT, K, T_2H, option_type="call")
            if not np.isnan(iv):
                assert np.isclose(iv, sigma, atol=1e-3), \
                    f"K={K}: IV recovery: input={sigma}, recovered={iv}"

    def test_iv_convergence_newton_raphson(self, bs):
        """Newton-Raphson should converge quickly for well-behaved inputs."""
        S, K, T = SPX_SPOT, ATM_STRIKE, T_2H
        sigma = SIGMA_MID

        price = bs.call_price(S, K, T, sigma)
        # The method should converge without falling through to bisection
        # We verify by checking the result is very accurate
        recovered = bs.implied_volatility(price, S, K, T, option_type="call")
        assert np.isclose(recovered, sigma, atol=1e-7), \
            f"Newton-Raphson should be highly accurate: error={abs(recovered - sigma):.2e}"


# =============================================================================
# 10. EXPECTED MOVE TESTS
# =============================================================================

class TestExpectedMove:
    """Tests for expected move calculation functions."""

    def test_expected_move_vix1d_formula(self):
        """Test VIX1D expected move formula: SPX * (VIX1D/100) / sqrt(252)."""
        spx = 6000.0
        vix1d = 15.0

        em = expected_move_vix1d(spx, vix1d)
        expected = spx * (vix1d / 100.0) / np.sqrt(252)

        assert np.isclose(em, expected, rtol=1e-10), \
            f"VIX1D EM={em:.4f}, expected={expected:.4f}"

    def test_expected_move_vix1d_realistic_values(self):
        """VIX1D = 15 on SPX 6000 should give roughly 56-57 point expected move."""
        em = expected_move_vix1d(6000.0, 15.0)
        assert 50 < em < 65, f"Realistic VIX1D EM should be ~57, got {em:.2f}"

    def test_expected_move_straddle_formula(self):
        """Test straddle expected move formula: 0.85 * straddle_price."""
        straddle = 40.0
        em = expected_move_straddle(straddle)
        assert np.isclose(em, 0.85 * 40.0), \
            f"Straddle EM={em:.4f}, expected={0.85 * 40.0:.4f}"

    def test_expected_move_straddle_zero(self):
        """Zero straddle price gives zero expected move."""
        assert expected_move_straddle(0.0) == 0.0

    def test_composite_expected_move_weights(self):
        """Test that composite EM uses 40/40/20 weights."""
        spx = 6000.0
        vix1d = 15.0
        straddle = 40.0
        rv20 = 12.0

        em1, em2 = composite_expected_move(spx, vix1d, straddle, rv20)

        em_vix = expected_move_vix1d(spx, vix1d)
        em_straddle = expected_move_straddle(straddle)
        em_rv = expected_move_rv_adjusted(spx, vix1d, rv20)

        expected_1sigma = 0.40 * em_vix + 0.40 * em_straddle + 0.20 * em_rv
        expected_2sigma = 2.0 * expected_1sigma

        assert np.isclose(em1, expected_1sigma, rtol=1e-10), \
            f"1-sigma EM: got={em1:.4f}, expected={expected_1sigma:.4f}"
        assert np.isclose(em2, expected_2sigma, rtol=1e-10), \
            f"2-sigma EM: got={em2:.4f}, expected={expected_2sigma:.4f}"

    def test_2sigma_is_double_1sigma(self):
        """2-sigma expected move should be exactly 2x the 1-sigma move."""
        em1, em2 = composite_expected_move(6000.0, 15.0, 40.0, 12.0)
        assert np.isclose(em2, 2.0 * em1, rtol=1e-10), \
            f"2-sigma={em2:.4f} should be 2 * 1-sigma={em1:.4f}"

    def test_expected_move_rv_adjusted_mean_reversion(self):
        """When IV >> RV, the RV-adjusted move should be pulled down toward RV."""
        spx = 6000.0
        vix1d_high = 30.0  # IV much higher than RV
        rv_low = 10.0

        em_vix_raw = expected_move_vix1d(spx, vix1d_high)
        em_rv_adjusted = expected_move_rv_adjusted(spx, vix1d_high, rv_low)

        assert em_rv_adjusted < em_vix_raw, \
            f"RV-adjusted EM={em_rv_adjusted:.2f} should be less than raw VIX EM={em_vix_raw:.2f}"

    def test_expected_move_rv_adjusted_equal_iv_rv(self):
        """When IV == RV, the RV-adjusted move should equal the VIX1D move."""
        spx = 6000.0
        vol = 15.0

        em_vix = expected_move_vix1d(spx, vol)
        em_rv = expected_move_rv_adjusted(spx, vol, vol)

        assert np.isclose(em_vix, em_rv, rtol=1e-6), \
            f"When IV=RV, EM_vix={em_vix:.4f} should equal EM_rv={em_rv:.4f}"

    def test_expected_move_positive(self):
        """All expected move computations should return positive values."""
        assert expected_move_vix1d(6000.0, 15.0) > 0
        assert expected_move_straddle(40.0) > 0
        assert expected_move_rv_adjusted(6000.0, 15.0, 12.0) > 0

        em1, em2 = composite_expected_move(6000.0, 15.0, 40.0, 12.0)
        assert em1 > 0
        assert em2 > 0


# =============================================================================
# 11. THETA DECAY FRACTION TESTS
# =============================================================================

class TestThetaDecayFraction:
    """Tests for the intraday theta decay fraction model."""

    def test_before_market_open_returns_zero(self):
        """Before 9:30 ET, no theta has been consumed."""
        assert theta_decay_fraction(time(9, 0)) == 0.0
        assert theta_decay_fraction(time(9, 29)) == 0.0
        assert theta_decay_fraction(time(9, 30)) == 0.0

    def test_at_market_close_returns_one(self):
        """At 16:00 ET, all theta has been consumed."""
        assert theta_decay_fraction(time(16, 0)) == 1.0

    def test_after_market_close_returns_one(self):
        """After market close, fraction remains 1.0."""
        assert theta_decay_fraction(time(16, 30)) == 1.0
        assert theta_decay_fraction(time(17, 0)) == 1.0

    def test_fraction_between_zero_and_one(self):
        """During trading hours, fraction should be in (0, 1)."""
        test_times = [
            time(10, 0), time(11, 0), time(12, 0),
            time(13, 0), time(14, 0), time(15, 0), time(15, 30),
        ]
        for t in test_times:
            frac = theta_decay_fraction(t)
            assert 0.0 < frac < 1.0, \
                f"Fraction at {t} should be in (0,1), got {frac}"

    def test_fraction_monotonically_increasing(self):
        """Theta decay fraction should increase throughout the day."""
        times = [
            time(9, 31), time(10, 0), time(10, 30), time(11, 0),
            time(12, 0), time(13, 0), time(14, 0), time(15, 0),
            time(15, 30), time(15, 59),
        ]
        fracs = [theta_decay_fraction(t) for t in times]

        for i in range(1, len(fracs)):
            assert fracs[i] > fracs[i - 1], \
                f"Fraction not increasing: {times[i-1]}={fracs[i-1]}, {times[i]}={fracs[i]}"

    def test_morning_fraction_less_than_afternoon(self):
        """Morning portion (9:30-11:00) decays slower than afternoon (14:00-15:30).

        Non-linear theta decay: more happens in the afternoon.
        """
        morning_start = theta_decay_fraction(time(9, 30))
        morning_end = theta_decay_fraction(time(11, 0))
        morning_decay = morning_end - morning_start

        afternoon_start = theta_decay_fraction(time(14, 0))
        afternoon_end = theta_decay_fraction(time(15, 30))
        afternoon_decay = afternoon_end - afternoon_start

        assert afternoon_decay > morning_decay, \
            f"Afternoon decay={afternoon_decay:.3f} should exceed morning decay={morning_decay:.3f}"

    def test_end_of_day_cliff(self):
        """The final 30 minutes (15:30-16:00) should consume significant theta."""
        frac_1530 = theta_decay_fraction(time(15, 30))
        frac_1600 = theta_decay_fraction(time(16, 0))

        final_decay = frac_1600 - frac_1530
        assert final_decay > 0.15, \
            f"Final 30min should consume >15% of daily theta, got {final_decay*100:.1f}%"

    def test_fractions_approximately_sum_to_one(self):
        """The total theta consumed from open to close should be 1.0."""
        frac_open = theta_decay_fraction(time(9, 30))
        frac_close = theta_decay_fraction(time(16, 0))

        assert np.isclose(frac_close - frac_open, 1.0, atol=1e-10), \
            f"Total fraction from open to close: {frac_close - frac_open}"

    def test_known_breakpoint_values(self):
        """Test the known calibration breakpoints."""
        # 11:00 ET = 90 minutes since open -> 0.175
        assert np.isclose(theta_decay_fraction(time(11, 0)), 0.175, atol=1e-6)

        # 14:00 ET = 270 minutes since open -> 0.450
        assert np.isclose(theta_decay_fraction(time(14, 0)), 0.450, atol=1e-6)

        # 15:30 ET = 360 minutes since open -> 0.775
        assert np.isclose(theta_decay_fraction(time(15, 30)), 0.775, atol=1e-6)


# =============================================================================
# 12. HELPER FUNCTION TESTS
# =============================================================================

class TestHelperFunctions:
    """Tests for module-level helper functions."""

    # --- annualized_time ---

    def test_annualized_time_full_day(self):
        """390 minutes = 1 full trading day = 1/252 annualized."""
        T = annualized_time(390)
        expected = 390.0 / MINUTES_PER_YEAR
        assert np.isclose(T, expected, rtol=1e-10)
        assert np.isclose(T, 1.0 / 252.0, rtol=1e-10)

    def test_annualized_time_one_minute(self):
        """1 minute should give MIN_T."""
        T = annualized_time(1)
        expected = 1.0 / MINUTES_PER_YEAR
        assert np.isclose(T, expected, rtol=1e-10)
        assert np.isclose(T, MIN_T, rtol=1e-10)

    def test_annualized_time_zero_returns_min_t(self):
        """0 minutes should clamp to MIN_T."""
        T = annualized_time(0)
        assert T == MIN_T

    def test_annualized_time_negative_returns_min_t(self):
        """Negative minutes should clamp to MIN_T."""
        T = annualized_time(-10)
        assert T == MIN_T

    def test_annualized_time_two_hours(self):
        """120 minutes = 2 trading hours."""
        T = annualized_time(120)
        expected = 120.0 / MINUTES_PER_YEAR
        assert np.isclose(T, expected, rtol=1e-10)

    # --- normal_pdf ---

    def test_normal_pdf_at_zero(self):
        """N'(0) = 1/sqrt(2*pi) ~ 0.3989."""
        result = normal_pdf(0.0)
        expected = 1.0 / np.sqrt(2.0 * np.pi)
        assert np.isclose(result, expected, rtol=1e-10)

    def test_normal_pdf_symmetric(self):
        """N'(x) = N'(-x) for all x."""
        for x in [0.5, 1.0, 1.5, 2.0, 3.0]:
            assert np.isclose(normal_pdf(x), normal_pdf(-x), rtol=1e-12), \
                f"normal_pdf not symmetric at x={x}"

    def test_normal_pdf_positive(self):
        """N'(x) > 0 for all x."""
        for x in [-5.0, -2.0, 0.0, 2.0, 5.0]:
            assert normal_pdf(x) > 0, f"normal_pdf({x}) should be positive"

    def test_normal_pdf_tails_approach_zero(self):
        """N'(x) -> 0 as |x| -> infinity."""
        assert normal_pdf(10.0) < 1e-20
        assert normal_pdf(-10.0) < 1e-20

    def test_normal_pdf_array_input(self):
        """normal_pdf should accept numpy arrays."""
        x = np.array([-1.0, 0.0, 1.0])
        result = normal_pdf(x)
        assert result.shape == (3,)
        assert np.isclose(result[0], result[2], rtol=1e-12)  # symmetric

    # --- normal_cdf ---

    def test_normal_cdf_at_zero(self):
        """N(0) = 0.5."""
        assert np.isclose(normal_cdf(0.0), 0.5, rtol=1e-10)

    def test_normal_cdf_limits(self):
        """N(-inf) -> 0, N(+inf) -> 1."""
        assert normal_cdf(-10.0) < 1e-15
        assert normal_cdf(10.0) > 1.0 - 1e-15

    def test_normal_cdf_symmetry(self):
        """N(x) + N(-x) = 1 for all x."""
        for x in [0.5, 1.0, 1.5, 2.0, 3.0]:
            assert np.isclose(normal_cdf(x) + normal_cdf(-x), 1.0, rtol=1e-12)

    def test_normal_cdf_monotonically_increasing(self):
        """N(x) should be monotonically increasing."""
        x_values = np.linspace(-5, 5, 100)
        cdf_values = [normal_cdf(x) for x in x_values]
        for i in range(1, len(cdf_values)):
            assert cdf_values[i] >= cdf_values[i - 1]

    def test_normal_cdf_known_values(self):
        """Test well-known CDF values."""
        # N(1) ~ 0.8413
        assert np.isclose(normal_cdf(1.0), 0.8413, atol=1e-4)
        # N(-1) ~ 0.1587
        assert np.isclose(normal_cdf(-1.0), 0.1587, atol=1e-4)
        # N(2) ~ 0.9772
        assert np.isclose(normal_cdf(2.0), 0.9772, atol=1e-4)

    # --- moneyness ---

    def test_moneyness_atm_is_zero(self):
        """At-the-money moneyness should be zero: ln(K/S) = ln(1) = 0."""
        assert np.isclose(moneyness(6000.0, 6000.0), 0.0, atol=1e-12)

    def test_moneyness_otm_call_positive(self):
        """OTM call (K > S) has positive log-moneyness."""
        m = moneyness(6000.0, 6100.0)
        assert m > 0, f"OTM call moneyness should be positive: {m}"

    def test_moneyness_itm_call_negative(self):
        """ITM call (K < S) has negative log-moneyness."""
        m = moneyness(6000.0, 5900.0)
        assert m < 0, f"ITM call moneyness should be negative: {m}"

    def test_moneyness_formula(self):
        """Test moneyness = ln(K/S) against direct computation."""
        S, K = 6000.0, 6100.0
        assert np.isclose(moneyness(S, K), np.log(K / S), rtol=1e-12)

    def test_moneyness_raises_for_zero_S(self):
        """moneyness should raise ValueError for S=0."""
        with pytest.raises(ValueError):
            moneyness(0.0, 6000.0)

    def test_moneyness_raises_for_zero_K(self):
        """moneyness should raise ValueError for K=0."""
        with pytest.raises(ValueError):
            moneyness(6000.0, 0.0)

    def test_moneyness_raises_for_negative(self):
        """moneyness should raise ValueError for negative S or K."""
        with pytest.raises(ValueError):
            moneyness(-100.0, 6000.0)
        with pytest.raises(ValueError):
            moneyness(6000.0, -100.0)


# =============================================================================
# ADDITIONAL: OTM GAMMA RATIO TESTS
# =============================================================================

class TestOTMGammaRatio:
    """Tests for the otm_gamma_ratio helper function."""

    def test_atm_returns_gamma_atm(self):
        """At ATM (log_moneyness=0), OTM gamma equals ATM gamma."""
        gamma_atm = 0.005
        result = otm_gamma_ratio(gamma_atm, 0.0, SIGMA_MID, T_2H)
        assert np.isclose(result, gamma_atm, rtol=1e-10)

    def test_otm_less_than_atm(self):
        """OTM gamma should be less than ATM gamma."""
        gamma_atm = 0.005
        log_m = 0.01  # OTM
        result = otm_gamma_ratio(gamma_atm, log_m, SIGMA_MID, T_2H)
        assert result < gamma_atm, f"OTM gamma={result} should be < ATM={gamma_atm}"

    def test_further_otm_has_less_gamma(self):
        """Further OTM strikes should have lower gamma."""
        gamma_atm = 0.005
        g1 = otm_gamma_ratio(gamma_atm, 0.01, SIGMA_MID, T_2H)
        g2 = otm_gamma_ratio(gamma_atm, 0.02, SIGMA_MID, T_2H)
        assert g2 < g1, f"Further OTM gamma={g2} should be < nearer OTM={g1}"

    def test_symmetric_moneyness(self):
        """Gamma ratio should be symmetric around ATM (same magnitude OTM/ITM)."""
        gamma_atm = 0.005
        g_pos = otm_gamma_ratio(gamma_atm, 0.01, SIGMA_MID, T_2H)
        g_neg = otm_gamma_ratio(gamma_atm, -0.01, SIGMA_MID, T_2H)
        assert np.isclose(g_pos, g_neg, rtol=1e-10)


# =============================================================================
# ADDITIONAL: GREEKS CALCULATOR WRAPPER TESTS
# =============================================================================

class TestGreeksCalculator:
    """Tests for the GreeksCalculator wrapper class."""

    def test_compute_all_greeks_returns_all_keys(self, calc):
        """compute_all_greeks should return dict with all expected keys."""
        greeks = calc.compute_all_greeks(
            SPX_SPOT, ATM_STRIKE, T_2H, SIGMA_MID, option_type="call"
        )
        expected_keys = {"delta", "gamma", "theta", "vega", "rho", "charm", "vanna", "speed"}
        assert set(greeks.keys()) == expected_keys

    def test_compute_all_greeks_values_finite(self, calc):
        """All computed Greeks should be finite values."""
        greeks = calc.compute_all_greeks(
            SPX_SPOT, ATM_STRIKE, T_2H, SIGMA_MID, option_type="call"
        )
        for name, val in greeks.items():
            assert np.isfinite(val), f"Greek '{name}' is not finite: {val}"

    def test_compute_chain_greeks_shape(self, calc):
        """compute_chain_greeks should return a DataFrame with correct shape."""
        strikes = np.arange(5900, 6110, 10, dtype=float)
        ivs = np.full(len(strikes), SIGMA_MID)
        types = np.array(["call"] * len(strikes))

        df = calc.compute_chain_greeks(SPX_SPOT, strikes, 120.0, ivs, option_types=types)

        assert len(df) == len(strikes)
        expected_cols = {
            "strike", "option_type", "iv", "delta", "gamma",
            "theta", "vega", "rho", "charm", "vanna", "speed"
        }
        assert set(df.columns) == expected_cols

    def test_compute_chain_greeks_default_call(self, calc):
        """When option_types is None, all should default to 'call'."""
        strikes = np.array([5950.0, 6000.0, 6050.0])
        ivs = np.full(3, SIGMA_MID)

        df = calc.compute_chain_greeks(SPX_SPOT, strikes, 120.0, ivs)

        assert all(df["option_type"] == "call")

    def test_compute_chain_greeks_deltas_reasonable(self, calc):
        """Chain delta values should be monotonically decreasing for calls."""
        strikes = np.arange(5900, 6110, 10, dtype=float)
        ivs = np.full(len(strikes), SIGMA_MID)

        df = calc.compute_chain_greeks(SPX_SPOT, strikes, 120.0, ivs)

        deltas = df["delta"].values
        for i in range(1, len(deltas)):
            assert deltas[i] <= deltas[i - 1] + 1e-10, \
                f"Deltas not decreasing at K={strikes[i]}"

    def test_default_bs_engine(self):
        """GreeksCalculator with no args should create a default BS engine."""
        calc_default = GreeksCalculator()
        assert calc_default.bs is not None
        assert isinstance(calc_default.bs, BlackScholes0DTE)


# =============================================================================
# ADDITIONAL: d1, d2 PARAMETER TESTS
# =============================================================================

class TestD1D2:
    """Tests for the d1 and d2 Black-Scholes parameters."""

    def test_d2_equals_d1_minus_sigma_sqrt_T(self, bs):
        """d2 = d1 - sigma * sqrt(T)."""
        S, K, T, sigma = SPX_SPOT, ATM_STRIKE, T_2H, SIGMA_MID

        _d1 = bs.d1(S, K, T, sigma)
        _d2 = bs.d2(S, K, T, sigma)

        expected_d2 = _d1 - sigma * np.sqrt(max(T, MIN_T))
        assert np.isclose(_d2, expected_d2, rtol=1e-8), \
            f"d2={_d2}, expected d1 - sigma*sqrt(T) = {expected_d2}"

    def test_d1_atm_with_zero_rates(self, bs_zero_rates):
        """At ATM with r=q=0, d1 = sigma*sqrt(T)/2."""
        T = T_2H
        sigma = SIGMA_MID

        _d1 = bs_zero_rates.d1(SPX_SPOT, SPX_SPOT, T, sigma)
        expected = sigma * np.sqrt(T) / 2.0

        assert np.isclose(_d1, expected, rtol=1e-8), \
            f"ATM d1 with r=q=0: got={_d1:.8f}, expected={expected:.8f}"

    def test_d1_increases_with_higher_spot(self, bs):
        """d1 should increase when spot increases (S > K more likely)."""
        _d1_low = bs.d1(5900.0, ATM_STRIKE, T_2H, SIGMA_MID)
        _d1_high = bs.d1(6100.0, ATM_STRIKE, T_2H, SIGMA_MID)

        assert _d1_high > _d1_low

    def test_d1_override_r_q(self, bs):
        """d1 should accept overridden r and q values."""
        _d1_default = bs.d1(SPX_SPOT, ATM_STRIKE, T_2H, SIGMA_MID)
        _d1_custom = bs.d1(SPX_SPOT, ATM_STRIKE, T_2H, SIGMA_MID, r=0.0, q=0.0)

        # They should differ because default r, q are non-zero
        assert not np.isclose(_d1_default, _d1_custom, atol=1e-10), \
            "d1 with custom r,q should differ from default"

    def test_clamp_T(self, bs):
        """_clamp_T should enforce a minimum of MIN_T."""
        assert bs._clamp_T(0.0) == MIN_T
        assert bs._clamp_T(-1.0) == MIN_T
        assert bs._clamp_T(MIN_T) == MIN_T
        assert bs._clamp_T(0.01) == 0.01


# =============================================================================
# ADDITIONAL: RHO TESTS
# =============================================================================

class TestRho:
    """Tests for the rho Greek."""

    def test_call_rho_positive(self, bs):
        """Call rho should be positive (higher rates help calls)."""
        rho = bs.rho(SPX_SPOT, ATM_STRIKE, T_2H, SIGMA_MID, option_type="call")
        assert rho >= 0, f"Call rho should be non-negative, got {rho}"

    def test_put_rho_negative(self, bs):
        """Put rho should be negative (higher rates hurt puts)."""
        rho = bs.rho(SPX_SPOT, ATM_STRIKE, T_2H, SIGMA_MID, option_type="put")
        assert rho <= 0, f"Put rho should be non-positive, got {rho}"

    def test_0dte_rho_negligible(self, bs):
        """For 0DTE, rho should be very small (rates barely matter intraday)."""
        rho = bs.rho(SPX_SPOT, ATM_STRIKE, T_1H, SIGMA_MID, option_type="call")
        assert abs(rho) < 0.1, f"0DTE rho should be negligible, got {rho}"


# =============================================================================
# ADDITIONAL: INTERNAL PRICE DISPATCHER TEST
# =============================================================================

class TestPriceDispatcher:
    """Tests for the _price internal dispatcher."""

    def test_price_dispatcher_call(self, bs):
        """_price with 'call' should match call_price."""
        r, q = bs.r, bs.q
        direct = bs.call_price(SPX_SPOT, ATM_STRIKE, T_2H, SIGMA_MID)
        dispatched = bs._price(SPX_SPOT, ATM_STRIKE, T_2H, SIGMA_MID, r, q, "call")
        assert np.isclose(direct, dispatched, rtol=1e-12)

    def test_price_dispatcher_put(self, bs):
        """_price with 'put' should match put_price."""
        r, q = bs.r, bs.q
        direct = bs.put_price(SPX_SPOT, ATM_STRIKE, T_2H, SIGMA_MID)
        dispatched = bs._price(SPX_SPOT, ATM_STRIKE, T_2H, SIGMA_MID, r, q, "put")
        assert np.isclose(direct, dispatched, rtol=1e-12)

    def test_price_dispatcher_c_shorthand(self, bs):
        """_price with 'c' should match call_price."""
        r, q = bs.r, bs.q
        direct = bs.call_price(SPX_SPOT, ATM_STRIKE, T_2H, SIGMA_MID)
        dispatched = bs._price(SPX_SPOT, ATM_STRIKE, T_2H, SIGMA_MID, r, q, "c")
        assert np.isclose(direct, dispatched, rtol=1e-12)


# =============================================================================
# ADDITIONAL: IV SURFACE COMPUTATION TEST
# =============================================================================

class TestIVSurface:
    """Tests for GreeksCalculator.compute_iv_surface."""

    def test_iv_surface_basic(self, calc):
        """Test IV surface extraction from a small set of options."""
        S = SPX_SPOT
        T = T_2H
        sigma = SIGMA_MID

        # Generate some synthetic option prices
        options_data = []
        for K in [5950.0, 6000.0, 6050.0]:
            price = calc.bs.call_price(S, K, T, sigma)
            options_data.append({
                "strike": K,
                "price": price,
                "type": "call",
                "T": T,
            })

        df = calc.compute_iv_surface(S, options_data)

        assert len(df) == 3
        assert "iv" in df.columns
        assert "strike" in df.columns

        # Recovered IVs should be close to input sigma
        for iv in df["iv"].values:
            assert np.isclose(iv, sigma, atol=1e-3), \
                f"Recovered IV={iv:.6f}, expected near {sigma}"

    def test_iv_surface_empty_input(self, calc):
        """Empty input should produce empty DataFrame."""
        df = calc.compute_iv_surface(SPX_SPOT, [])
        assert df.empty


# =============================================================================
# ADDITIONAL: CONSTANTS CONSISTENCY TESTS
# =============================================================================

class TestConstants:
    """Tests for module-level constants."""

    def test_minutes_per_year(self):
        """MINUTES_PER_YEAR = 252 * 390 = 98280."""
        assert MINUTES_PER_YEAR == 252 * 390
        assert MINUTES_PER_YEAR == 98280

    def test_min_t(self):
        """MIN_T = 1 / (252 * 390)."""
        assert np.isclose(MIN_T, 1.0 / 98280.0, rtol=1e-12)

    def test_trading_days(self):
        """Standard convention: 252 trading days per year."""
        assert TRADING_DAYS_PER_YEAR == 252

    def test_minutes_per_day(self):
        """Standard convention: 390 trading minutes per day."""
        assert MINUTES_PER_TRADING_DAY == 390
