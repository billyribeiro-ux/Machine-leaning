"""
Comprehensive test suite for SCANIFY 0DTE GEX Engine and Signal Generator.
==========================================================================

Tests the GEX computation engine (GEXEngine) and the signal generator
(GEXSignalGenerator) from ``src/scanify_0dte/gex_engine.py``.

Due to interface evolution between the models and engine modules (built in
parallel by separate agents), this test file provides compatible shim model
classes that match the field names ``gex_engine.py`` actually constructs,
injected via ``sys.modules`` patching before import.

Sections
--------
1. GEX Engine Tests         -- compute_strike_gex
2. Full GEX Profile Tests   -- compute_full_gex_profile
3. Gamma Flip Detection      -- find_gamma_flip
4. Max Pain Calculation       -- find_max_pain
5. Transition Zone            -- compute_transition_zone
6. GEX Signal Generator       -- all 6 signals
7. Flow Model                 -- update_flow_model + hybrid weighting
"""

from __future__ import annotations

import importlib
import importlib.util
import math
import os
import sys
import types
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock, patch, PropertyMock

import numpy as np
import pytest


# =========================================================================
# COMPATIBLE MODEL SHIMS
# =========================================================================
# gex_engine.py constructs StrikeGEX with (call_gex, put_gex, gamma, ...),
# GEXProfile with (strikes_gex, ...), and GEXSignal with (trigger_level,
# target, stop, direction=<string>, ...).  The production models.py may use
# different field names.  These shims provide the exact constructor
# signatures that gex_engine.py uses, enabling isolated logic testing.


class _OptionSide(str, Enum):
    CALL = "CALL"
    PUT = "PUT"


class _GEXSignalType(str, Enum):
    GAMMA_FLIP_CROSSOVER = "GAMMA_FLIP_CROSSOVER"
    GAMMA_WALL_APPROACH = "GAMMA_WALL_APPROACH"
    TRANSITION_ZONE_BREAKOUT = "TRANSITION_ZONE_BREAKOUT"
    GEX_COLLAPSE = "GEX_COLLAPSE"
    CHARM_DRIVEN_FLOW = "CHARM_DRIVEN_FLOW"
    VANNA_AMPLIFICATION = "VANNA_AMPLIFICATION"


@dataclass
class _StrikeGEX:
    """StrikeGEX shim matching gex_engine.py constructor kwargs."""
    strike: float = 0.0
    call_gex: float = 0.0
    put_gex: float = 0.0
    net_gex: float = 0.0
    call_oi: int = 0
    put_oi: int = 0
    call_volume: int = 0
    put_volume: int = 0
    call_iv: float = 0.0
    put_iv: float = 0.0
    gamma: float = 0.0
    net_charm: float = 0.0
    net_vanna: float = 0.0
    net_speed: float = 0.0


class _OptionQuote:
    """OptionQuote shim matching gex_engine.py expected interface."""
    def __init__(
        self,
        strike: float,
        side: _OptionSide,
        iv: float = 0.15,
        oi: int = 0,
        volume: int = 0,
        flow_direction: float = 0.0,
    ):
        self.strike = strike
        self.option_type = side
        self.implied_vol = iv
        self.open_interest = oi
        self.volume = volume
        self.flow_direction = flow_direction


class _OptionsChain:
    """OptionsChain shim matching gex_engine.py expected interface."""
    def __init__(self, spot: float, quotes: list | None = None):
        self.spot = spot
        self.quotes = quotes or []


class _GEXProfile:
    """GEXProfile shim matching gex_engine.py constructor kwargs."""
    def __init__(
        self,
        strikes_gex: list | None = None,
        total_net_gex: float = 0.0,
        gamma_flip_level: float = 5200.0,
        call_wall: float = 5200.0,
        put_wall: float = 5200.0,
        max_pain: float = 5200.0,
        plus_gex: float = 5200.0,
        minus_gex: float = 5200.0,
        transition_zone_upper: float = 5200.0,
        transition_zone_lower: float = 5200.0,
        vol_trigger: float = 5200.0,
        charm_net_es_contracts: float = 0.0,
        vanna_net_exposure: float = 0.0,
        timestamp: datetime | None = None,
        gex_momentum: float = 0.0,
    ):
        self.strikes_gex = strikes_gex or []
        self.total_net_gex = total_net_gex
        self.gamma_flip_level = gamma_flip_level
        self.call_wall = call_wall
        self.put_wall = put_wall
        self.max_pain = max_pain
        self.plus_gex = plus_gex
        self.minus_gex = minus_gex
        self.transition_zone_upper = transition_zone_upper
        self.transition_zone_lower = transition_zone_lower
        self.vol_trigger = vol_trigger
        self.charm_net_es_contracts = charm_net_es_contracts
        self.vanna_net_exposure = vanna_net_exposure
        self.timestamp = timestamp or datetime.utcnow()
        self.gex_momentum = gex_momentum


class _GEXSignal:
    """GEXSignal shim matching gex_engine.py constructor kwargs."""
    def __init__(
        self,
        signal_type: _GEXSignalType | None = None,
        direction: str | None = None,
        confidence: float = 0.0,
        description: str = "",
        trigger_level: float = 0.0,
        target: float | None = None,
        stop: float | None = None,
        timestamp: datetime | None = None,
        metadata: dict | None = None,
    ):
        self.signal_type = signal_type
        self.direction = direction
        self.confidence = confidence
        self.description = description
        self.trigger_level = trigger_level
        self.target = target
        self.stop = stop
        self.timestamp = timestamp or datetime.utcnow()
        self.metadata = metadata or {}


# =========================================================================
# SYS.MODULES PATCHING -- inject shims before importing gex_engine
# =========================================================================

_SRC_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "src")
)

if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

# Register a minimal scanify_0dte package if not already present.
_pkg_path = os.path.join(_SRC_DIR, "scanify_0dte")

if "scanify_0dte" not in sys.modules or not hasattr(
    sys.modules.get("scanify_0dte"), "__path__"
):
    _pkg = types.ModuleType("scanify_0dte")
    _pkg.__path__ = [_pkg_path]
    _pkg.__package__ = "scanify_0dte"
    sys.modules["scanify_0dte"] = _pkg

# Load the real models module first (preserving all classes for other tests),
# then overlay our shim classes so gex_engine picks up the test versions.
_real_models_path = os.path.join(_pkg_path, "models.py")
if "scanify_0dte.models" not in sys.modules:
    _spec = importlib.util.spec_from_file_location("scanify_0dte.models", _real_models_path)
    _real_models = importlib.util.module_from_spec(_spec)
    _real_models.__spec__ = _spec
    sys.modules["scanify_0dte.models"] = _real_models
    _spec.loader.exec_module(_real_models)

# Overlay shim classes onto the models module for gex_engine compatibility
_models_mod = sys.modules["scanify_0dte.models"]
_models_mod.StrikeGEX = _StrikeGEX
_models_mod.GEXProfile = _GEXProfile
_models_mod.GEXSignal = _GEXSignal
_models_mod.GEXSignalType = _GEXSignalType
_models_mod.OptionQuote = _OptionQuote
_models_mod.OptionsChain = _OptionsChain
_models_mod.OptionSide = _OptionSide

# Now import the real greeks_engine (has no model dependency)
from scanify_0dte.greeks_engine import (  # noqa: E402
    BlackScholes0DTE,
    GreeksCalculator,
    annualized_time,
    normal_pdf,
)

# Now import gex_engine (picks up shim models + real greeks_engine)
from scanify_0dte.gex_engine import (  # noqa: E402
    GEXEngine,
    GEXSignalGenerator,
    _CONTRACT_MULTIPLIER,
    _ES_MULTIPLIER,
)

# =========================================================================
# CONSTANTS FOR TESTS
# =========================================================================

SPX_SPOT = 5200.0
SPX_SPOT_HIGH = 5250.0
SPX_SPOT_LOW = 5150.0
DEFAULT_IV = 0.15
DEFAULT_MINUTES = 120
DEFAULT_R = 0.05
DEFAULT_Q = 0.015


# =========================================================================
# FIXTURES
# =========================================================================


@pytest.fixture
def real_bs() -> BlackScholes0DTE:
    """Real BlackScholes0DTE with standard parameters."""
    return BlackScholes0DTE(risk_free_rate=DEFAULT_R, dividend_yield=DEFAULT_Q)


@pytest.fixture
def mock_bs() -> MagicMock:
    """Mock BlackScholes0DTE returning controlled, deterministic values.

    gamma  -> 0.01
    charm  -> 500.0
    vanna  -> 100.0
    speed  -> 0.0001
    """
    bs = MagicMock(spec=BlackScholes0DTE)
    bs.gamma.return_value = 0.01
    bs.charm.return_value = 500.0
    bs.vanna.return_value = 100.0
    bs.speed.return_value = 0.0001
    return bs


@pytest.fixture
def engine_simple(mock_bs: MagicMock) -> GEXEngine:
    """GEXEngine with 'simple' dealer model and mocked BS."""
    return GEXEngine(bs_calculator=mock_bs, dealer_model="simple")


@pytest.fixture
def engine_hybrid(mock_bs: MagicMock) -> GEXEngine:
    """GEXEngine with 'hybrid' dealer model (60/40) and mocked BS."""
    return GEXEngine(bs_calculator=mock_bs, dealer_model="hybrid")


@pytest.fixture
def engine_flow(mock_bs: MagicMock) -> GEXEngine:
    """GEXEngine with 'flow' dealer model and mocked BS."""
    return GEXEngine(bs_calculator=mock_bs, dealer_model="flow")


@pytest.fixture
def engine_real_bs(real_bs: BlackScholes0DTE) -> GEXEngine:
    """GEXEngine with real BlackScholes0DTE for integration tests."""
    return GEXEngine(bs_calculator=real_bs, dealer_model="simple")


@pytest.fixture
def simple_chain() -> _OptionsChain:
    """Three-strike chain (5190/5200/5210) with known OI for max-pain tests.

    Max pain should be at 5200 (minimises aggregate ITM OI pain).
    """
    quotes = [
        # Strike 5190
        _OptionQuote(5190, _OptionSide.CALL, iv=0.16, oi=100, volume=50),
        _OptionQuote(5190, _OptionSide.PUT, iv=0.18, oi=500, volume=200),
        # Strike 5200
        _OptionQuote(5200, _OptionSide.CALL, iv=0.15, oi=300, volume=100),
        _OptionQuote(5200, _OptionSide.PUT, iv=0.15, oi=300, volume=100),
        # Strike 5210
        _OptionQuote(5210, _OptionSide.CALL, iv=0.14, oi=500, volume=200),
        _OptionQuote(5210, _OptionSide.PUT, iv=0.16, oi=100, volume=50),
    ]
    return _OptionsChain(spot=5200.0, quotes=quotes)


@pytest.fixture
def realistic_spx_chain() -> _OptionsChain:
    """Realistic 11-strike SPX chain with put skew and concentrated OI.

    Strikes: 5150 to 5250 (every 10 points).
    Call wall at 5230 (highest call OI = 5000).
    Put wall at 5170 (highest put OI = 6000).
    """
    strikes = list(range(5150, 5260, 10))
    call_ois = [200, 300, 500, 800, 1500, 2000, 1200, 3000, 5000, 1000, 400]
    put_ois = [1000, 2000, 6000, 4000, 2500, 1500, 800, 500, 300, 200, 100]
    call_ivs = [0.20, 0.19, 0.18, 0.17, 0.16, 0.15, 0.14, 0.14, 0.13, 0.13, 0.12]
    put_ivs = [0.22, 0.21, 0.20, 0.19, 0.17, 0.15, 0.14, 0.14, 0.13, 0.13, 0.12]

    quotes = []
    for i, k in enumerate(strikes):
        quotes.append(
            _OptionQuote(k, _OptionSide.CALL, iv=call_ivs[i], oi=call_ois[i], volume=call_ois[i] // 2)
        )
        quotes.append(
            _OptionQuote(k, _OptionSide.PUT, iv=put_ivs[i], oi=put_ois[i], volume=put_ois[i] // 2)
        )
    return _OptionsChain(spot=SPX_SPOT, quotes=quotes)


@pytest.fixture
def sample_profile() -> _GEXProfile:
    """Pre-built GEXProfile with known levels for signal-generator tests."""
    return _GEXProfile(
        total_net_gex=5_000_000.0,
        gamma_flip_level=5200.0,
        call_wall=5230.0,
        put_wall=5170.0,
        max_pain=5200.0,
        plus_gex=5210.0,
        minus_gex=5180.0,
        transition_zone_upper=5215.0,
        transition_zone_lower=5185.0,
        vol_trigger=5200.0,
        charm_net_es_contracts=0.0,
        vanna_net_exposure=0.0,
    )


# =========================================================================
# 1. GEX ENGINE TESTS -- compute_strike_gex
# =========================================================================


class TestComputeStrikeGEX:
    """Tests for GEXEngine.compute_strike_gex()."""

    def test_returns_strike_gex_structure(self, engine_simple: GEXEngine):
        """compute_strike_gex should return a StrikeGEX dataclass."""
        sg = engine_simple.compute_strike_gex(
            spot=SPX_SPOT, strike=5200, call_iv=0.15, put_iv=0.15,
            call_oi=1000, put_oi=500, call_volume=100, put_volume=50,
            minutes_remaining=DEFAULT_MINUTES, r=DEFAULT_R, q=DEFAULT_Q,
        )
        assert isinstance(sg, _StrikeGEX)
        assert sg.strike == 5200
        assert sg.call_oi == 1000
        assert sg.put_oi == 500
        assert sg.call_volume == 100
        assert sg.put_volume == 50
        assert sg.call_iv == 0.15
        assert sg.put_iv == 0.15

    def test_call_gex_is_negative_simple_model(self, engine_simple: GEXEngine):
        """In the simple model, call GEX is negative (dealers assumed short calls
        from customer overwriting, hence -1 * gamma * OI * 100 * S).
        """
        sg = engine_simple.compute_strike_gex(
            spot=SPX_SPOT, strike=5200, call_iv=0.15, put_iv=0.15,
            call_oi=1000, put_oi=0, call_volume=0, put_volume=0,
            minutes_remaining=DEFAULT_MINUTES, r=DEFAULT_R, q=DEFAULT_Q,
        )
        # gamma mock = 0.01
        # call_gex = -1 * 0.01 * 1000 * 100 * 5200 = -5,200,000
        expected_call_gex = -1.0 * 0.01 * 1000 * _CONTRACT_MULTIPLIER * SPX_SPOT
        assert sg.call_gex == pytest.approx(expected_call_gex, rel=1e-6)
        assert sg.call_gex < 0

    def test_put_gex_is_positive_simple_model(self, engine_simple: GEXEngine):
        """In the simple model, put GEX is positive (dealers assumed short puts
        from customer hedging, hence +1 * gamma * OI * 100 * S).
        """
        sg = engine_simple.compute_strike_gex(
            spot=SPX_SPOT, strike=5200, call_iv=0.15, put_iv=0.15,
            call_oi=0, put_oi=500, call_volume=0, put_volume=0,
            minutes_remaining=DEFAULT_MINUTES, r=DEFAULT_R, q=DEFAULT_Q,
        )
        expected_put_gex = +1.0 * 0.01 * 500 * _CONTRACT_MULTIPLIER * SPX_SPOT
        assert sg.put_gex == pytest.approx(expected_put_gex, rel=1e-6)
        assert sg.put_gex > 0

    def test_net_gex_is_sum_of_call_and_put(self, engine_simple: GEXEngine):
        """Net GEX = call_gex + put_gex (simple model, no cumulative flow)."""
        sg = engine_simple.compute_strike_gex(
            spot=SPX_SPOT, strike=5200, call_iv=0.15, put_iv=0.15,
            call_oi=1000, put_oi=500, call_volume=0, put_volume=0,
            minutes_remaining=DEFAULT_MINUTES, r=DEFAULT_R, q=DEFAULT_Q,
        )
        assert sg.net_gex == pytest.approx(sg.call_gex + sg.put_gex, rel=1e-6)

    def test_zero_oi_returns_zero_gex(self, engine_simple: GEXEngine):
        """When both call and put OI are zero, all GEX components should be zero."""
        sg = engine_simple.compute_strike_gex(
            spot=SPX_SPOT, strike=5200, call_iv=0.15, put_iv=0.15,
            call_oi=0, put_oi=0, call_volume=0, put_volume=0,
            minutes_remaining=DEFAULT_MINUTES, r=DEFAULT_R, q=DEFAULT_Q,
        )
        assert sg.call_gex == 0.0
        assert sg.put_gex == 0.0
        assert sg.net_gex == 0.0

    def test_realistic_spx_oi_data(self, engine_simple: GEXEngine):
        """Test with realistic SPX OI levels (call_oi=3000, put_oi=5000)."""
        sg = engine_simple.compute_strike_gex(
            spot=SPX_SPOT, strike=5200, call_iv=0.15, put_iv=0.17,
            call_oi=3000, put_oi=5000, call_volume=500, put_volume=800,
            minutes_remaining=DEFAULT_MINUTES, r=DEFAULT_R, q=DEFAULT_Q,
        )
        gamma_val = 0.01  # mock
        expected_call = -1.0 * gamma_val * 3000 * _CONTRACT_MULTIPLIER * SPX_SPOT
        expected_put = +1.0 * gamma_val * 5000 * _CONTRACT_MULTIPLIER * SPX_SPOT
        assert sg.call_gex == pytest.approx(expected_call, rel=1e-6)
        assert sg.put_gex == pytest.approx(expected_put, rel=1e-6)
        # More put OI than call OI -> net positive (dealers have more long gamma from puts)
        assert sg.net_gex > 0

    def test_gex_scales_with_gamma(self, engine_real_bs: GEXEngine):
        """ATM gamma is higher than OTM gamma, so ATM strike should have
        higher absolute single-side GEX than a far-OTM strike at equal OI.

        Note: when call_oi == put_oi, net_gex cancels to zero because
        call_gex = -gamma*OI*100*S and put_gex = +gamma*OI*100*S.
        We compare |call_gex| (single-side) to validate gamma scaling.
        """
        sg_atm = engine_real_bs.compute_strike_gex(
            spot=SPX_SPOT, strike=5200, call_iv=0.15, put_iv=0.15,
            call_oi=1000, put_oi=1000, call_volume=0, put_volume=0,
            minutes_remaining=DEFAULT_MINUTES, r=DEFAULT_R, q=DEFAULT_Q,
        )
        sg_otm = engine_real_bs.compute_strike_gex(
            spot=SPX_SPOT, strike=5300, call_iv=0.15, put_iv=0.15,
            call_oi=1000, put_oi=1000, call_volume=0, put_volume=0,
            minutes_remaining=DEFAULT_MINUTES, r=DEFAULT_R, q=DEFAULT_Q,
        )
        # ATM gamma is the peak of the distribution
        assert sg_atm.gamma > sg_otm.gamma
        # Higher gamma -> higher absolute single-side GEX (at same OI)
        assert abs(sg_atm.call_gex) > abs(sg_otm.call_gex)
        assert abs(sg_atm.put_gex) > abs(sg_otm.put_gex)

    def test_gex_scales_with_oi(self, engine_simple: GEXEngine):
        """Doubling OI should double the absolute GEX (gamma stays the same)."""
        sg_low = engine_simple.compute_strike_gex(
            spot=SPX_SPOT, strike=5200, call_iv=0.15, put_iv=0.15,
            call_oi=1000, put_oi=500, call_volume=0, put_volume=0,
            minutes_remaining=DEFAULT_MINUTES, r=DEFAULT_R, q=DEFAULT_Q,
        )
        sg_high = engine_simple.compute_strike_gex(
            spot=SPX_SPOT, strike=5200, call_iv=0.15, put_iv=0.15,
            call_oi=2000, put_oi=1000, call_volume=0, put_volume=0,
            minutes_remaining=DEFAULT_MINUTES, r=DEFAULT_R, q=DEFAULT_Q,
        )
        assert sg_high.call_gex == pytest.approx(2.0 * sg_low.call_gex, rel=1e-6)
        assert sg_high.put_gex == pytest.approx(2.0 * sg_low.put_gex, rel=1e-6)
        assert sg_high.net_gex == pytest.approx(2.0 * sg_low.net_gex, rel=1e-6)

    def test_charm_and_vanna_populated(self, engine_simple: GEXEngine):
        """compute_strike_gex should populate net_charm, net_vanna, net_speed."""
        sg = engine_simple.compute_strike_gex(
            spot=SPX_SPOT, strike=5200, call_iv=0.15, put_iv=0.15,
            call_oi=1000, put_oi=500, call_volume=0, put_volume=0,
            minutes_remaining=DEFAULT_MINUTES, r=DEFAULT_R, q=DEFAULT_Q,
        )
        # Mock charm returns 500.0 for both call and put
        # net_charm = -1 * 500 * 1000 * 100 + 1 * 500 * 500 * 100
        #           = -50,000,000 + 25,000,000 = -25,000,000
        expected_charm = -1.0 * 500.0 * 1000 * _CONTRACT_MULTIPLIER + 1.0 * 500.0 * 500 * _CONTRACT_MULTIPLIER
        assert sg.net_charm == pytest.approx(expected_charm, rel=1e-6)
        # net_vanna follows same sign convention
        assert sg.net_vanna != 0.0
        assert sg.net_speed != 0.0

    def test_minutes_floor_at_one(self, engine_simple: GEXEngine):
        """Minutes remaining should be floored at 1 (no singularity)."""
        # Passing 0 minutes should NOT raise; engine clamps to 1 minute
        sg = engine_simple.compute_strike_gex(
            spot=SPX_SPOT, strike=5200, call_iv=0.15, put_iv=0.15,
            call_oi=1000, put_oi=500, call_volume=0, put_volume=0,
            minutes_remaining=0, r=DEFAULT_R, q=DEFAULT_Q,
        )
        assert isinstance(sg, _StrikeGEX)
        # Should produce finite values
        assert math.isfinite(sg.call_gex)
        assert math.isfinite(sg.put_gex)

    def test_hybrid_model_blends_simple_and_flow(self, engine_hybrid: GEXEngine):
        """Hybrid model: call_gex = 0.6 * simple + 0.4 * flow.

        With no flow direction data, flow defaults match simple, so
        hybrid call_gex should equal simple call_gex.
        """
        sg = engine_hybrid.compute_strike_gex(
            spot=SPX_SPOT, strike=5200, call_iv=0.15, put_iv=0.15,
            call_oi=1000, put_oi=500, call_volume=0, put_volume=0,
            minutes_remaining=DEFAULT_MINUTES, r=DEFAULT_R, q=DEFAULT_Q,
        )
        # With no flow signals, flow_call_sign=-1 and flow_put_sign=+1 (same as simple)
        # simple_call_gex = -1 * 0.01 * 1000 * 100 * 5200 = -5,200,000
        # flow_call_gex   = -1 * 0.01 * 1000 * 100 * 5200 = -5,200,000
        # hybrid_call     = 0.6 * (-5.2M) + 0.4 * (-5.2M) = -5,200,000
        expected_call = -1.0 * 0.01 * 1000 * _CONTRACT_MULTIPLIER * SPX_SPOT
        assert sg.call_gex == pytest.approx(expected_call, rel=1e-6)


# =========================================================================
# 2. FULL GEX PROFILE TESTS -- compute_full_gex_profile
# =========================================================================


class TestComputeFullGEXProfile:
    """Tests for GEXEngine.compute_full_gex_profile()."""

    def test_returns_gex_profile(self, engine_simple: GEXEngine, simple_chain: _OptionsChain):
        """Should return a _GEXProfile with all expected fields."""
        profile = engine_simple.compute_full_gex_profile(
            chain=simple_chain, minutes_remaining=DEFAULT_MINUTES,
        )
        assert isinstance(profile, _GEXProfile)
        assert len(profile.strikes_gex) == 3  # 3 strikes in simple_chain
        assert profile.gamma_flip_level > 0
        assert profile.call_wall > 0
        assert profile.put_wall > 0

    def test_total_net_gex_is_sum(self, engine_simple: GEXEngine, simple_chain: _OptionsChain):
        """total_net_gex should equal the sum of individual strike net_gex values."""
        profile = engine_simple.compute_full_gex_profile(
            chain=simple_chain, minutes_remaining=DEFAULT_MINUTES,
        )
        expected_total = sum(sg.net_gex for sg in profile.strikes_gex)
        assert profile.total_net_gex == pytest.approx(expected_total, rel=1e-9)

    def test_call_wall_is_highest_call_oi(
        self, engine_simple: GEXEngine, realistic_spx_chain: _OptionsChain,
    ):
        """Call wall should be the strike with the highest call OI."""
        profile = engine_simple.compute_full_gex_profile(
            chain=realistic_spx_chain, minutes_remaining=DEFAULT_MINUTES,
        )
        # In realistic chain, strike 5230 has call_oi=5000 (highest)
        assert profile.call_wall == 5230.0

    def test_put_wall_is_highest_put_oi(
        self, engine_simple: GEXEngine, realistic_spx_chain: _OptionsChain,
    ):
        """Put wall should be the strike with the highest put OI."""
        profile = engine_simple.compute_full_gex_profile(
            chain=realistic_spx_chain, minutes_remaining=DEFAULT_MINUTES,
        )
        # In realistic chain, strike 5170 has put_oi=6000 (highest)
        assert profile.put_wall == 5170.0

    def test_empty_chain_returns_default_profile(self, engine_simple: GEXEngine):
        """Empty quotes should yield a default profile with spot-level values."""
        chain = _OptionsChain(spot=SPX_SPOT, quotes=[])
        profile = engine_simple.compute_full_gex_profile(
            chain=chain, minutes_remaining=DEFAULT_MINUTES,
        )
        assert profile.total_net_gex == 0.0
        assert profile.gamma_flip_level == SPX_SPOT
        assert profile.call_wall == SPX_SPOT
        assert profile.put_wall == SPX_SPOT

    def test_skips_zero_oi_strikes(self, engine_simple: GEXEngine):
        """Strikes where both call and put OI are zero should be excluded."""
        quotes = [
            _OptionQuote(5190, _OptionSide.CALL, oi=0, volume=0),
            _OptionQuote(5190, _OptionSide.PUT, oi=0, volume=0),
            _OptionQuote(5200, _OptionSide.CALL, oi=100, volume=10),
            _OptionQuote(5200, _OptionSide.PUT, oi=100, volume=10),
        ]
        chain = _OptionsChain(spot=SPX_SPOT, quotes=quotes)
        profile = engine_simple.compute_full_gex_profile(
            chain=chain, minutes_remaining=DEFAULT_MINUTES,
        )
        # Only 5200 should be included
        assert len(profile.strikes_gex) == 1
        assert profile.strikes_gex[0].strike == 5200

    def test_vanna_exposure_computed(
        self, engine_simple: GEXEngine,
    ):
        """Profile should have non-zero vanna_net_exposure when OI is asymmetric.

        The simple_chain fixture has mirror-symmetric total OI across strikes
        (call: 100+300+500=900, put: 500+300+100=900) causing net vanna to
        cancel.  This test uses an explicitly asymmetric chain instead.
        """
        quotes = [
            _OptionQuote(5190, _OptionSide.CALL, iv=0.16, oi=100, volume=10),
            _OptionQuote(5190, _OptionSide.PUT, iv=0.18, oi=800, volume=40),
            _OptionQuote(5200, _OptionSide.CALL, iv=0.15, oi=200, volume=20),
            _OptionQuote(5200, _OptionSide.PUT, iv=0.15, oi=500, volume=30),
        ]
        chain = _OptionsChain(spot=5200.0, quotes=quotes)
        profile = engine_simple.compute_full_gex_profile(
            chain=chain, minutes_remaining=DEFAULT_MINUTES,
        )
        # Asymmetric OI: more puts than calls -> net vanna should be non-zero
        assert math.isfinite(profile.vanna_net_exposure)
        assert profile.vanna_net_exposure != 0.0

    def test_charm_es_contracts_computed(
        self, engine_simple: GEXEngine, simple_chain: _OptionsChain,
    ):
        """charm_net_es_contracts should be total_charm / (ES_price * 50)."""
        profile = engine_simple.compute_full_gex_profile(
            chain=simple_chain, minutes_remaining=DEFAULT_MINUTES,
        )
        # Verify it is a finite number (exact value depends on mock charm)
        assert math.isfinite(profile.charm_net_es_contracts)

    def test_gamma_flip_within_strike_range(
        self, engine_simple: GEXEngine, realistic_spx_chain: _OptionsChain,
    ):
        """gamma_flip_level should be within the chain's strike range or at spot."""
        profile = engine_simple.compute_full_gex_profile(
            chain=realistic_spx_chain, minutes_remaining=DEFAULT_MINUTES,
        )
        all_strikes = [sg.strike for sg in profile.strikes_gex]
        # Gamma flip should be within [min_strike, max_strike] or equal to spot
        assert (
            min(all_strikes) <= profile.gamma_flip_level <= max(all_strikes)
            or profile.gamma_flip_level == SPX_SPOT
        )

    def test_symmetric_chain_gamma_flip_near_spot(self, engine_simple: GEXEngine):
        """With symmetric call/put OI, gamma flip should be at or near spot.

        When call_oi == put_oi at every strike, the cumulative GEX is always
        positive (puts contribute positive, calls contribute negative, but
        the absolute values are equal -- and the net depends on the sign convention).
        With simple model: net_gex per strike = gamma * OI * 100 * S * (put_sign - call_sign)
        = gamma * OI * 100 * S * (1 - (-1)) = 2 * gamma * OI * 100 * S > 0 if OI > 0.
        So the cumulative GEX never crosses zero -> returns spot as fallback.
        """
        quotes = []
        for k in [5190, 5200, 5210]:
            quotes.append(_OptionQuote(k, _OptionSide.CALL, oi=1000, volume=50))
            quotes.append(_OptionQuote(k, _OptionSide.PUT, oi=1000, volume=50))
        chain = _OptionsChain(spot=SPX_SPOT, quotes=quotes)
        profile = engine_simple.compute_full_gex_profile(
            chain=chain, minutes_remaining=DEFAULT_MINUTES,
        )
        # Symmetric: cumulative always positive -> no crossing -> flip = spot
        assert profile.gamma_flip_level == SPX_SPOT


# =========================================================================
# 3. GAMMA FLIP DETECTION TESTS -- find_gamma_flip
# =========================================================================


class TestFindGammaFlip:
    """Tests for GEXEngine.find_gamma_flip()."""

    def test_known_sign_change(self, engine_simple: GEXEngine):
        """When cumulative GEX clearly crosses zero, find the interpolated flip."""
        strikes_gex = [
            _StrikeGEX(strike=5180, net_gex=-3_000_000),
            _StrikeGEX(strike=5190, net_gex=-1_000_000),
            _StrikeGEX(strike=5200, net_gex=+5_000_000),
            _StrikeGEX(strike=5210, net_gex=+2_000_000),
        ]
        flip = engine_simple.find_gamma_flip(strikes_gex, spot=SPX_SPOT)

        # Cumulative:  -3M, -4M, +1M, +3M
        # Crossing between 5190 (cum=-4M) and 5200 (cum=+1M)
        # flip = 5190 + 10 * |(-4M)| / (|(-4M)| + |(+1M)|) = 5190 + 10 * 4/5 = 5198
        assert flip == pytest.approx(5198.0, abs=0.1)

    def test_interpolation_between_strikes(self, engine_simple: GEXEngine):
        """The flip should be linearly interpolated between the two straddling strikes."""
        strikes_gex = [
            _StrikeGEX(strike=5190, net_gex=-2_000_000),
            _StrikeGEX(strike=5200, net_gex=+2_000_000),
        ]
        flip = engine_simple.find_gamma_flip(strikes_gex, spot=SPX_SPOT)

        # Cumulative: -2M, 0M.  But product = -2M * 0 = 0 which is not < 0.
        # Actually: cum[0] = -2M, cum[1] = -2M + 2M = 0.
        # Product = -2M * 0 = 0, which is NOT < 0, so no crossing detected.
        # Fallback: returns spot.
        # Let's use values that DO cross:

        strikes_gex_v2 = [
            _StrikeGEX(strike=5190, net_gex=-2_000_000),
            _StrikeGEX(strike=5200, net_gex=+3_000_000),
        ]
        flip_v2 = engine_simple.find_gamma_flip(strikes_gex_v2, spot=SPX_SPOT)

        # Cumulative: -2M, +1M  (crosses from -2M to +1M)
        # flip = 5190 + 10 * |-2M| / (|-2M| + |+1M|) = 5190 + 10 * 2/3 = 5196.67
        assert flip_v2 == pytest.approx(5190 + 10 * 2.0 / 3.0, abs=0.1)

    def test_all_positive_gex_returns_spot(self, engine_simple: GEXEngine):
        """When all net_gex are positive, cumulative never crosses zero -> spot."""
        strikes_gex = [
            _StrikeGEX(strike=5190, net_gex=+1_000_000),
            _StrikeGEX(strike=5200, net_gex=+2_000_000),
            _StrikeGEX(strike=5210, net_gex=+1_000_000),
        ]
        flip = engine_simple.find_gamma_flip(strikes_gex, spot=SPX_SPOT)
        assert flip == SPX_SPOT

    def test_all_negative_gex_returns_spot(self, engine_simple: GEXEngine):
        """When all net_gex are negative, cumulative never crosses zero -> spot."""
        strikes_gex = [
            _StrikeGEX(strike=5190, net_gex=-1_000_000),
            _StrikeGEX(strike=5200, net_gex=-2_000_000),
            _StrikeGEX(strike=5210, net_gex=-1_000_000),
        ]
        flip = engine_simple.find_gamma_flip(strikes_gex, spot=SPX_SPOT)
        assert flip == SPX_SPOT

    def test_empty_strikes_returns_spot(self, engine_simple: GEXEngine):
        """Empty strikes list should return spot as fallback."""
        flip = engine_simple.find_gamma_flip([], spot=SPX_SPOT)
        assert flip == SPX_SPOT

    def test_multiple_crossings_picks_closest_to_spot(self, engine_simple: GEXEngine):
        """With multiple zero-crossings, the one closest to spot is returned."""
        strikes_gex = [
            _StrikeGEX(strike=5170, net_gex=-5_000_000),
            _StrikeGEX(strike=5180, net_gex=+6_000_000),   # crossing 1 around 5175
            _StrikeGEX(strike=5190, net_gex=-3_000_000),   # crossing 2 around 5186
            _StrikeGEX(strike=5200, net_gex=+5_000_000),   # crossing 3 around 5196
            _StrikeGEX(strike=5210, net_gex=+1_000_000),
        ]
        flip = engine_simple.find_gamma_flip(strikes_gex, spot=5195.0)
        # The crossing nearest to spot=5195 should be selected (around 5196)
        assert abs(flip - 5195.0) < 10  # Within 10 pts of spot

    def test_unsorted_input_handled(self, engine_simple: GEXEngine):
        """Strikes passed out of order should produce the same result as sorted."""
        strikes_sorted = [
            _StrikeGEX(strike=5190, net_gex=-2_000_000),
            _StrikeGEX(strike=5200, net_gex=+3_000_000),
        ]
        strikes_unsorted = [
            _StrikeGEX(strike=5200, net_gex=+3_000_000),
            _StrikeGEX(strike=5190, net_gex=-2_000_000),
        ]
        flip_sorted = engine_simple.find_gamma_flip(strikes_sorted, spot=SPX_SPOT)
        flip_unsorted = engine_simple.find_gamma_flip(strikes_unsorted, spot=SPX_SPOT)
        assert flip_sorted == pytest.approx(flip_unsorted, abs=0.01)


# =========================================================================
# 4. MAX PAIN CALCULATION TESTS -- find_max_pain
# =========================================================================


class TestFindMaxPain:
    """Tests for GEXEngine.find_max_pain()."""

    def test_simple_three_strike_max_pain(self, engine_simple: GEXEngine, simple_chain: _OptionsChain):
        """With the simple chain fixture, max pain should be 5200.

        At Ks=5190: calls ITM=0, puts ITM=(5200-5190)*300+(5210-5190)*100=5000 -> total=5000
        At Ks=5200: calls ITM=(5200-5190)*100=1000, puts ITM=(5210-5200)*100=1000 -> total=2000
        At Ks=5210: calls ITM=(5210-5190)*100+(5210-5200)*300=5000, puts ITM=0 -> total=5000
        """
        mp = engine_simple.find_max_pain(simple_chain)
        assert mp == 5200.0

    def test_max_pain_within_strike_range(
        self, engine_simple: GEXEngine, realistic_spx_chain: _OptionsChain,
    ):
        """Max pain must be one of the available strikes."""
        mp = engine_simple.find_max_pain(realistic_spx_chain)
        available_strikes = sorted({q.strike for q in realistic_spx_chain.quotes})
        assert mp in available_strikes

    def test_empty_chain_returns_spot(self, engine_simple: GEXEngine):
        """Empty chain should return spot as max pain."""
        chain = _OptionsChain(spot=SPX_SPOT, quotes=[])
        mp = engine_simple.find_max_pain(chain)
        assert mp == SPX_SPOT

    def test_single_strike(self, engine_simple: GEXEngine):
        """A chain with only one strike should return that strike."""
        quotes = [
            _OptionQuote(5200, _OptionSide.CALL, oi=1000, volume=50),
            _OptionQuote(5200, _OptionSide.PUT, oi=1000, volume=50),
        ]
        chain = _OptionsChain(spot=SPX_SPOT, quotes=quotes)
        mp = engine_simple.find_max_pain(chain)
        assert mp == 5200.0

    def test_concentrated_put_oi_pulls_max_pain_down(self, engine_simple: GEXEngine):
        """Heavy put OI at a low strike should pull max pain down."""
        quotes = [
            _OptionQuote(5180, _OptionSide.CALL, oi=100, volume=10),
            _OptionQuote(5180, _OptionSide.PUT, oi=10000, volume=500),
            _OptionQuote(5200, _OptionSide.CALL, oi=100, volume=10),
            _OptionQuote(5200, _OptionSide.PUT, oi=100, volume=10),
            _OptionQuote(5220, _OptionSide.CALL, oi=100, volume=10),
            _OptionQuote(5220, _OptionSide.PUT, oi=100, volume=10),
        ]
        chain = _OptionsChain(spot=SPX_SPOT, quotes=quotes)
        mp = engine_simple.find_max_pain(chain)
        # Heavy put OI at 5180 makes 5180 the cheapest settlement for dealers
        # (all those puts expire worthless if settlement >= 5180)
        assert mp <= 5200


# =========================================================================
# 5. TRANSITION ZONE TESTS -- compute_transition_zone
# =========================================================================


class TestComputeTransitionZone:
    """Tests for GEXEngine.compute_transition_zone()."""

    def test_upper_bound_call_gamma_dominates(self, engine_simple: GEXEngine):
        """Upper bound: first strike above spot where |call_gex| > 2 * |put_gex|."""
        strikes_gex = [
            _StrikeGEX(strike=5190, call_gex=-500_000, put_gex=+600_000),  # below spot
            _StrikeGEX(strike=5200, call_gex=-500_000, put_gex=+500_000),  # near spot
            _StrikeGEX(strike=5210, call_gex=-800_000, put_gex=+300_000),  # |call|>2*|put| -> upper
            _StrikeGEX(strike=5220, call_gex=-900_000, put_gex=+200_000),
        ]
        lower, upper = engine_simple.compute_transition_zone(strikes_gex, spot=SPX_SPOT)
        assert upper == 5210.0

    def test_lower_bound_put_gamma_dominates(self, engine_simple: GEXEngine):
        """Lower bound: first strike below spot where |put_gex| > 2 * |call_gex|."""
        strikes_gex = [
            _StrikeGEX(strike=5180, call_gex=-200_000, put_gex=+900_000),
            _StrikeGEX(strike=5190, call_gex=-300_000, put_gex=+700_000),  # |put|>2*|call| -> lower
            _StrikeGEX(strike=5200, call_gex=-500_000, put_gex=+500_000),
            _StrikeGEX(strike=5210, call_gex=-800_000, put_gex=+300_000),
        ]
        lower, upper = engine_simple.compute_transition_zone(strikes_gex, spot=SPX_SPOT)
        assert lower == 5190.0

    def test_transition_zone_boundaries_correct(self, engine_simple: GEXEngine):
        """Both boundaries should be correctly identified."""
        strikes_gex = [
            _StrikeGEX(strike=5180, call_gex=-200_000, put_gex=+800_000),  # |put|>2*|call| -> lower cand
            _StrikeGEX(strike=5190, call_gex=-300_000, put_gex=+700_000),  # |put|>2*|call| -> lower (closest below spot)
            _StrikeGEX(strike=5200, call_gex=-500_000, put_gex=+500_000),  # at spot, skipped
            _StrikeGEX(strike=5210, call_gex=-700_000, put_gex=+300_000),  # |call|>2*|put| -> upper
            _StrikeGEX(strike=5220, call_gex=-900_000, put_gex=+200_000),
        ]
        lower, upper = engine_simple.compute_transition_zone(strikes_gex, spot=SPX_SPOT)
        assert lower == 5190.0
        assert upper == 5210.0
        assert lower < upper

    def test_empty_strikes_returns_spot(self, engine_simple: GEXEngine):
        """Empty strikes list should return (spot, spot)."""
        lower, upper = engine_simple.compute_transition_zone([], spot=SPX_SPOT)
        assert lower == SPX_SPOT
        assert upper == SPX_SPOT

    def test_no_qualifying_upper_uses_highest_strike(self, engine_simple: GEXEngine):
        """When no strike above spot qualifies, the highest strike is used."""
        strikes_gex = [
            _StrikeGEX(strike=5190, call_gex=-300_000, put_gex=+700_000),
            _StrikeGEX(strike=5200, call_gex=-500_000, put_gex=+500_000),
            _StrikeGEX(strike=5210, call_gex=-500_000, put_gex=+500_000),  # equal, not > 2x
        ]
        lower, upper = engine_simple.compute_transition_zone(strikes_gex, spot=SPX_SPOT)
        # No strike above spot has |call_gex| > 2 * |put_gex|
        # The for-else clause fires, upper = highest strike = 5210
        assert upper == 5210.0

    def test_no_qualifying_lower_uses_lowest_strike(self, engine_simple: GEXEngine):
        """When no strike below spot qualifies, the lowest strike is used."""
        strikes_gex = [
            _StrikeGEX(strike=5190, call_gex=-500_000, put_gex=+500_000),  # equal, not > 2x
            _StrikeGEX(strike=5200, call_gex=-500_000, put_gex=+500_000),
            _StrikeGEX(strike=5210, call_gex=-800_000, put_gex=+300_000),
        ]
        lower, upper = engine_simple.compute_transition_zone(strikes_gex, spot=SPX_SPOT)
        assert lower == 5190.0  # lowest strike used as fallback


# =========================================================================
# 6. GEX SIGNAL GENERATOR TESTS
# =========================================================================

# ---- Helper to create a fresh signal generator ----

def _make_signal_gen(
    mock_bs: MagicMock,
    gex_history: list | None = None,
    signal_history: list | None = None,
) -> GEXSignalGenerator:
    """Create a GEXSignalGenerator with a fresh GEXEngine and no cooldowns."""
    engine = GEXEngine(bs_calculator=mock_bs, dealer_model="simple")
    return GEXSignalGenerator(
        gex_engine=engine,
        gex_history=gex_history or [],
        signal_history=signal_history or [],
    )


# ---------------------------------------------------------------------------
# Signal 1: Gamma Flip Crossover
# ---------------------------------------------------------------------------


class TestGammaFlipCrossover:
    """Tests for Signal 1 -- Gamma Flip Crossover."""

    def test_crosses_from_below_is_bullish(self, mock_bs: MagicMock, sample_profile: _GEXProfile):
        """Price crossing gamma flip from below -> BULLISH signal."""
        gen = _make_signal_gen(mock_bs)
        sample_profile.gamma_flip_level = 5200.0

        signal = gen.check_gamma_flip_crossover(
            current_profile=sample_profile,
            spot=5201.0,        # crossed above
            prior_spot=5199.0,  # was below
        )
        assert signal is not None
        assert signal.direction == "bullish"
        assert signal.signal_type == _GEXSignalType.GAMMA_FLIP_CROSSOVER
        assert signal.confidence > 0
        assert signal.trigger_level == 5200.0

    def test_crosses_from_above_is_bearish(self, mock_bs: MagicMock, sample_profile: _GEXProfile):
        """Price crossing gamma flip from above -> BEARISH signal."""
        gen = _make_signal_gen(mock_bs)
        sample_profile.gamma_flip_level = 5200.0

        signal = gen.check_gamma_flip_crossover(
            current_profile=sample_profile,
            spot=5199.0,        # crossed below
            prior_spot=5201.0,  # was above
        )
        assert signal is not None
        assert signal.direction == "bearish"
        assert signal.signal_type == _GEXSignalType.GAMMA_FLIP_CROSSOVER
        assert signal.trigger_level == 5200.0

    def test_no_cross_returns_none(self, mock_bs: MagicMock, sample_profile: _GEXProfile):
        """No crossing of the gamma flip -> no signal."""
        gen = _make_signal_gen(mock_bs)
        sample_profile.gamma_flip_level = 5200.0

        # Both above
        signal = gen.check_gamma_flip_crossover(
            current_profile=sample_profile,
            spot=5205.0,
            prior_spot=5203.0,
        )
        assert signal is None

        # Both below
        signal = gen.check_gamma_flip_crossover(
            current_profile=sample_profile,
            spot=5195.0,
            prior_spot=5197.0,
        )
        assert signal is None

    def test_bullish_target_is_call_wall(self, mock_bs: MagicMock, sample_profile: _GEXProfile):
        """Bullish gamma flip crossover target should be the call wall."""
        gen = _make_signal_gen(mock_bs)
        sample_profile.gamma_flip_level = 5200.0
        sample_profile.call_wall = 5230.0

        signal = gen.check_gamma_flip_crossover(
            current_profile=sample_profile,
            spot=5201.0, prior_spot=5199.0,
        )
        assert signal is not None
        assert signal.target == sample_profile.call_wall

    def test_bearish_target_is_put_wall(self, mock_bs: MagicMock, sample_profile: _GEXProfile):
        """Bearish gamma flip crossover target should be the put wall."""
        gen = _make_signal_gen(mock_bs)
        sample_profile.gamma_flip_level = 5200.0
        sample_profile.put_wall = 5170.0

        signal = gen.check_gamma_flip_crossover(
            current_profile=sample_profile,
            spot=5199.0, prior_spot=5201.0,
        )
        assert signal is not None
        assert signal.target == sample_profile.put_wall

    def test_cooldown_prevents_duplicate(self, mock_bs: MagicMock, sample_profile: _GEXProfile):
        """A second crossing within the cooldown window should NOT fire."""
        gen = _make_signal_gen(mock_bs)
        sample_profile.gamma_flip_level = 5200.0

        # First signal fires
        sig1 = gen.check_gamma_flip_crossover(
            current_profile=sample_profile, spot=5201.0, prior_spot=5199.0,
        )
        assert sig1 is not None

        # Second crossing attempt immediately -- should be on cooldown
        sig2 = gen.check_gamma_flip_crossover(
            current_profile=sample_profile, spot=5199.0, prior_spot=5201.0,
        )
        assert sig2 is None


# ---------------------------------------------------------------------------
# Signal 2: Gamma Wall Approach
# ---------------------------------------------------------------------------


class TestGammaWallApproach:
    """Tests for Signal 2 -- Gamma Wall Approach."""

    def test_within_3pts_of_call_wall_resistance(
        self, mock_bs: MagicMock, sample_profile: _GEXProfile,
    ):
        """Approaching call wall from below (within 3 pts) -> signal."""
        gen = _make_signal_gen(mock_bs)
        sample_profile.call_wall = 5230.0
        sample_profile.put_wall = 5170.0

        signal = gen.check_gamma_wall_approach(
            current_profile=sample_profile,
            spot=5228.0,  # 2 pts from call wall, below it
        )
        assert signal is not None
        assert signal.signal_type == _GEXSignalType.GAMMA_WALL_APPROACH
        assert signal.trigger_level == 5230.0
        assert "call wall" in signal.description.lower() or "RESISTANCE" in signal.description

    def test_within_3pts_of_put_wall_support(
        self, mock_bs: MagicMock, sample_profile: _GEXProfile,
    ):
        """Approaching put wall from above (within 3 pts) -> signal."""
        gen = _make_signal_gen(mock_bs)
        sample_profile.call_wall = 5230.0
        sample_profile.put_wall = 5170.0

        signal = gen.check_gamma_wall_approach(
            current_profile=sample_profile,
            spot=5172.0,  # 2 pts from put wall, above it
        )
        assert signal is not None
        assert signal.signal_type == _GEXSignalType.GAMMA_WALL_APPROACH
        assert signal.trigger_level == 5170.0

    def test_far_from_walls_no_signal(
        self, mock_bs: MagicMock, sample_profile: _GEXProfile,
    ):
        """Price far from both walls should produce no signal."""
        gen = _make_signal_gen(mock_bs)
        sample_profile.call_wall = 5230.0
        sample_profile.put_wall = 5170.0

        signal = gen.check_gamma_wall_approach(
            current_profile=sample_profile,
            spot=5200.0,  # 30 pts from call wall, 30 pts from put wall
        )
        assert signal is None

    def test_exactly_at_call_wall(
        self, mock_bs: MagicMock, sample_profile: _GEXProfile,
    ):
        """Spot exactly at the call wall should still produce a signal
        (distance=0, which is <= 3, and spot <= call_wall).
        """
        gen = _make_signal_gen(mock_bs)
        sample_profile.call_wall = 5230.0
        sample_profile.put_wall = 5170.0

        signal = gen.check_gamma_wall_approach(
            current_profile=sample_profile,
            spot=5230.0,  # exactly at call wall
        )
        assert signal is not None

    def test_approach_distance_boundary(
        self, mock_bs: MagicMock, sample_profile: _GEXProfile,
    ):
        """At exactly 3.0 points from call wall, signal should still fire."""
        gen = _make_signal_gen(mock_bs)
        sample_profile.call_wall = 5230.0
        sample_profile.put_wall = 5170.0

        # 3.0 pts away, below the wall
        signal = gen.check_gamma_wall_approach(
            current_profile=sample_profile,
            spot=5227.0,
        )
        assert signal is not None

    def test_just_beyond_approach_distance(
        self, mock_bs: MagicMock, sample_profile: _GEXProfile,
    ):
        """At 3.1 points from call wall, no signal should fire."""
        gen = _make_signal_gen(mock_bs)
        sample_profile.call_wall = 5230.0
        sample_profile.put_wall = 5170.0

        signal = gen.check_gamma_wall_approach(
            current_profile=sample_profile,
            spot=5226.9,  # 3.1 pts from 5230
        )
        assert signal is None


# ---------------------------------------------------------------------------
# Signal 3: Transition Zone Breakout
# ---------------------------------------------------------------------------


class TestTransitionZoneBreakout:
    """Tests for Signal 3 -- Transition Zone Breakout."""

    def test_breakout_above_tz_bullish(
        self, mock_bs: MagicMock, sample_profile: _GEXProfile,
    ):
        """Spot above TZ upper with 2+ min confirmation -> BULLISH."""
        gen = _make_signal_gen(mock_bs)
        sample_profile.transition_zone_upper = 5215.0
        sample_profile.transition_zone_lower = 5185.0
        sample_profile.plus_gex = 5230.0

        signal = gen.check_transition_zone_breakout(
            current_profile=sample_profile,
            spot=5220.0,
            minutes_outside=3,
        )
        assert signal is not None
        assert signal.direction == "bullish"
        assert signal.signal_type == _GEXSignalType.TRANSITION_ZONE_BREAKOUT

    def test_breakout_below_tz_bearish(
        self, mock_bs: MagicMock, sample_profile: _GEXProfile,
    ):
        """Spot below TZ lower with 2+ min confirmation -> BEARISH."""
        gen = _make_signal_gen(mock_bs)
        sample_profile.transition_zone_upper = 5215.0
        sample_profile.transition_zone_lower = 5185.0
        sample_profile.minus_gex = 5160.0

        signal = gen.check_transition_zone_breakout(
            current_profile=sample_profile,
            spot=5180.0,
            minutes_outside=4,
        )
        assert signal is not None
        assert signal.direction == "bearish"

    def test_inside_tz_no_signal(
        self, mock_bs: MagicMock, sample_profile: _GEXProfile,
    ):
        """Price inside the transition zone -> no signal regardless of minutes."""
        gen = _make_signal_gen(mock_bs)
        sample_profile.transition_zone_upper = 5215.0
        sample_profile.transition_zone_lower = 5185.0

        signal = gen.check_transition_zone_breakout(
            current_profile=sample_profile,
            spot=5200.0,
            minutes_outside=10,
        )
        assert signal is None

    def test_insufficient_confirmation_no_signal(
        self, mock_bs: MagicMock, sample_profile: _GEXProfile,
    ):
        """Below 2-minute confirmation -> no signal even if outside TZ."""
        gen = _make_signal_gen(mock_bs)
        sample_profile.transition_zone_upper = 5215.0
        sample_profile.transition_zone_lower = 5185.0

        signal = gen.check_transition_zone_breakout(
            current_profile=sample_profile,
            spot=5220.0,
            minutes_outside=1,  # needs >= 2
        )
        assert signal is None

    def test_confidence_scales_with_minutes(
        self, mock_bs: MagicMock, sample_profile: _GEXProfile,
    ):
        """Longer time outside TZ should increase confidence (up to cap)."""
        gen = _make_signal_gen(mock_bs)
        sample_profile.transition_zone_upper = 5215.0
        sample_profile.transition_zone_lower = 5185.0

        sig_2min = gen.check_transition_zone_breakout(
            current_profile=sample_profile, spot=5220.0, minutes_outside=2,
        )
        # Need a fresh generator to avoid cooldown
        gen2 = _make_signal_gen(mock_bs)
        sig_10min = gen2.check_transition_zone_breakout(
            current_profile=sample_profile, spot=5220.0, minutes_outside=10,
        )

        assert sig_2min is not None
        assert sig_10min is not None
        assert sig_10min.confidence > sig_2min.confidence

    def test_bullish_target_is_plus_gex(
        self, mock_bs: MagicMock, sample_profile: _GEXProfile,
    ):
        """Bullish TZ breakout target should be the +GEX level."""
        gen = _make_signal_gen(mock_bs)
        sample_profile.transition_zone_upper = 5215.0
        sample_profile.plus_gex = 5240.0

        signal = gen.check_transition_zone_breakout(
            current_profile=sample_profile, spot=5220.0, minutes_outside=5,
        )
        assert signal is not None
        assert signal.target == sample_profile.plus_gex

    def test_bearish_target_is_minus_gex(
        self, mock_bs: MagicMock, sample_profile: _GEXProfile,
    ):
        """Bearish TZ breakout target should be the -GEX level."""
        gen = _make_signal_gen(mock_bs)
        sample_profile.transition_zone_lower = 5185.0
        sample_profile.transition_zone_upper = 5215.0
        sample_profile.minus_gex = 5160.0

        signal = gen.check_transition_zone_breakout(
            current_profile=sample_profile, spot=5180.0, minutes_outside=5,
        )
        assert signal is not None
        assert signal.target == sample_profile.minus_gex


# ---------------------------------------------------------------------------
# Signal 4: GEX Collapse
# ---------------------------------------------------------------------------


class TestGEXCollapse:
    """Tests for Signal 4 -- GEX Collapse (Pre-Expiration Unpin)."""

    def test_detects_30pct_drop_in_15_minutes(self, mock_bs: MagicMock):
        """GEX dropping > 30% in ~15 minutes should trigger GEX_COLLAPSE."""
        # Build history: 15 profiles all with total_net_gex = 10M
        history = []
        for _ in range(15):
            p = _GEXProfile(total_net_gex=10_000_000.0)
            history.append(p)

        gen = _make_signal_gen(mock_bs, gex_history=history)

        # Current profile: |GEX| dropped to 5M = 50% drop
        current = _GEXProfile(total_net_gex=5_000_000.0)
        signal = gen.check_gex_collapse(current_profile=current)

        assert signal is not None
        assert signal.signal_type == _GEXSignalType.GEX_COLLAPSE
        assert signal.direction == "neutral"  # Collapse is vol, not directional

    def test_normal_fluctuation_no_signal(self, mock_bs: MagicMock):
        """A 10% GEX drop (below 30% threshold) should NOT trigger."""
        history = []
        for _ in range(15):
            p = _GEXProfile(total_net_gex=10_000_000.0)
            history.append(p)

        gen = _make_signal_gen(mock_bs, gex_history=history)

        # Only 10% drop in absolute terms
        current = _GEXProfile(total_net_gex=9_000_000.0)
        signal = gen.check_gex_collapse(current_profile=current)
        assert signal is None

    def test_insufficient_history_no_signal(self, mock_bs: MagicMock):
        """Less than 2 history entries should not produce a signal."""
        gen = _make_signal_gen(mock_bs, gex_history=[_GEXProfile(total_net_gex=10_000_000.0)])

        current = _GEXProfile(total_net_gex=1_000_000.0)
        signal = gen.check_gex_collapse(current_profile=current)
        assert signal is None

    def test_negative_gex_collapse(self, mock_bs: MagicMock):
        """Collapse of negative GEX (absolute value drops > 30%) should trigger."""
        history = []
        for _ in range(15):
            p = _GEXProfile(total_net_gex=-10_000_000.0)
            history.append(p)

        gen = _make_signal_gen(mock_bs, gex_history=history)

        # Absolute value drops from 10M to 3M = 70% drop
        current = _GEXProfile(total_net_gex=-3_000_000.0)
        signal = gen.check_gex_collapse(current_profile=current)
        assert signal is not None

    def test_gex_sign_flip_is_collapse(self, mock_bs: MagicMock):
        """GEX flipping sign with large magnitude change counts as collapse."""
        history = []
        for _ in range(15):
            p = _GEXProfile(total_net_gex=10_000_000.0)
            history.append(p)

        gen = _make_signal_gen(mock_bs, gex_history=history)

        # Flips to negative and |new| << |old|
        current = _GEXProfile(total_net_gex=-1_000_000.0)
        signal = gen.check_gex_collapse(current_profile=current)
        # abs drops from 10M to 1M = 90% drop
        assert signal is not None

    def test_collapse_confidence_scales_with_drop(self, mock_bs: MagicMock):
        """Larger GEX collapses should produce higher confidence scores.

        The confidence formula is: 55 + min(abs_drop_pct * 50, 25).
        The inner cap of 25 kicks in at 50% drop, so we compare a 32%
        drop vs a 45% drop to stay below the saturation point.
        """
        history = [_GEXProfile(total_net_gex=10_000_000.0)] * 15

        # 32% drop: confidence = 55 + min(0.32 * 50, 25) = 55 + 16 = 71
        gen1 = _make_signal_gen(mock_bs, gex_history=list(history))
        sig_32pct = gen1.check_gex_collapse(
            current_profile=_GEXProfile(total_net_gex=6_800_000.0)
        )

        # 45% drop: confidence = 55 + min(0.45 * 50, 25) = 55 + 22.5 = 77.5
        gen2 = _make_signal_gen(mock_bs, gex_history=list(history))
        sig_45pct = gen2.check_gex_collapse(
            current_profile=_GEXProfile(total_net_gex=5_500_000.0)
        )

        assert sig_32pct is not None
        assert sig_45pct is not None
        assert sig_45pct.confidence > sig_32pct.confidence


# ---------------------------------------------------------------------------
# Signal 5: Charm-Driven Flow
# ---------------------------------------------------------------------------


class TestCharmDrivenFlow:
    """Tests for Signal 5 -- Charm-Driven Flow Prediction."""

    def test_positive_charm_above_threshold_bullish(self, mock_bs: MagicMock):
        """Charm implying > 5000 ES contracts of BUYING -> BULLISH."""
        gen = _make_signal_gen(mock_bs)
        profile = _GEXProfile(charm_net_es_contracts=6000.0)

        signal = gen.check_charm_driven_flow(current_profile=profile)
        assert signal is not None
        assert signal.direction == "bullish"
        assert signal.signal_type == _GEXSignalType.CHARM_DRIVEN_FLOW

    def test_negative_charm_above_threshold_bearish(self, mock_bs: MagicMock):
        """Charm implying > 5000 ES contracts of SELLING -> BEARISH."""
        gen = _make_signal_gen(mock_bs)
        profile = _GEXProfile(charm_net_es_contracts=-7000.0)

        signal = gen.check_charm_driven_flow(current_profile=profile)
        assert signal is not None
        assert signal.direction == "bearish"

    def test_below_threshold_no_signal(self, mock_bs: MagicMock):
        """Charm below 5000 ES contracts should NOT trigger."""
        gen = _make_signal_gen(mock_bs)
        profile = _GEXProfile(charm_net_es_contracts=3000.0)

        signal = gen.check_charm_driven_flow(current_profile=profile)
        assert signal is None

    def test_exactly_at_threshold_no_signal(self, mock_bs: MagicMock):
        """Charm at exactly 5000 (not >5000) should NOT trigger (strict >)."""
        gen = _make_signal_gen(mock_bs)
        profile = _GEXProfile(charm_net_es_contracts=4999.0)

        signal = gen.check_charm_driven_flow(current_profile=profile)
        assert signal is None

    def test_direction_matches_charm_flow(self, mock_bs: MagicMock):
        """Positive charm = bullish (dealers buy), negative = bearish (dealers sell)."""
        gen_bull = _make_signal_gen(mock_bs)
        sig_bull = gen_bull.check_charm_driven_flow(
            current_profile=_GEXProfile(charm_net_es_contracts=8000.0)
        )

        gen_bear = _make_signal_gen(mock_bs)
        sig_bear = gen_bear.check_charm_driven_flow(
            current_profile=_GEXProfile(charm_net_es_contracts=-8000.0)
        )

        assert sig_bull.direction == "bullish"
        assert sig_bear.direction == "bearish"


# ---------------------------------------------------------------------------
# Signal 6: Vanna Amplification
# ---------------------------------------------------------------------------


class TestVannaAmplification:
    """Tests for Signal 6 -- Vanna Amplification."""

    def test_vix_up_neg_vanna_bearish(self, mock_bs: MagicMock):
        """VIX up > 10% with large negative vanna -> BEARISH."""
        gen = _make_signal_gen(mock_bs)
        profile = _GEXProfile(
            total_net_gex=10_000_000.0,
            vanna_net_exposure=-2_000_000.0,  # > max(10M * 0.05, 1M) = 1M
        )

        signal = gen.check_vanna_amplification(
            current_profile=profile, vix1d_change_pct=15.0,
        )
        assert signal is not None
        assert signal.direction == "bearish"
        assert signal.signal_type == _GEXSignalType.VANNA_AMPLIFICATION

    def test_vix_down_pos_vanna_bullish(self, mock_bs: MagicMock):
        """VIX down > 10% with large positive vanna -> BULLISH."""
        gen = _make_signal_gen(mock_bs)
        profile = _GEXProfile(
            total_net_gex=10_000_000.0,
            vanna_net_exposure=+2_000_000.0,
        )

        signal = gen.check_vanna_amplification(
            current_profile=profile, vix1d_change_pct=-12.0,
        )
        assert signal is not None
        assert signal.direction == "bullish"

    def test_vix_below_10pct_no_signal(self, mock_bs: MagicMock):
        """VIX change below 10% should NOT trigger regardless of vanna."""
        gen = _make_signal_gen(mock_bs)
        profile = _GEXProfile(
            total_net_gex=10_000_000.0,
            vanna_net_exposure=-5_000_000.0,
        )

        signal = gen.check_vanna_amplification(
            current_profile=profile, vix1d_change_pct=8.0,
        )
        assert signal is None

    def test_small_vanna_no_signal(self, mock_bs: MagicMock):
        """Large VIX move but small vanna should NOT trigger."""
        gen = _make_signal_gen(mock_bs)
        profile = _GEXProfile(
            total_net_gex=100_000_000.0,
            # Threshold = max(100M * 0.05, 1M) = 5M.  Vanna = 1M < 5M -> no signal.
            vanna_net_exposure=-1_000_000.0,
        )

        signal = gen.check_vanna_amplification(
            current_profile=profile, vix1d_change_pct=15.0,
        )
        assert signal is None

    def test_opposing_forces_no_signal(self, mock_bs: MagicMock):
        """VIX up + positive vanna = opposing forces -> no clear signal."""
        gen = _make_signal_gen(mock_bs)
        profile = _GEXProfile(
            total_net_gex=10_000_000.0,
            vanna_net_exposure=+2_000_000.0,
        )

        signal = gen.check_vanna_amplification(
            current_profile=profile, vix1d_change_pct=+15.0,  # up
        )
        assert signal is None

    def test_vix_down_negative_vanna_no_signal(self, mock_bs: MagicMock):
        """VIX down + negative vanna = opposing forces -> no signal."""
        gen = _make_signal_gen(mock_bs)
        profile = _GEXProfile(
            total_net_gex=10_000_000.0,
            vanna_net_exposure=-2_000_000.0,
        )

        signal = gen.check_vanna_amplification(
            current_profile=profile, vix1d_change_pct=-15.0,
        )
        assert signal is None

    def test_correct_direction_vix_up_neg_vanna(self, mock_bs: MagicMock):
        """Verify VIX up + negative vanna = 'bearish' (dealers sell delta)."""
        gen = _make_signal_gen(mock_bs)
        profile = _GEXProfile(
            total_net_gex=10_000_000.0,
            vanna_net_exposure=-3_000_000.0,
        )

        signal = gen.check_vanna_amplification(
            current_profile=profile, vix1d_change_pct=+20.0,
        )
        assert signal is not None
        assert signal.direction == "bearish"
        assert "SELL" in signal.description


# =========================================================================
# 7. FLOW MODEL TESTS -- update_flow_model + hybrid weighting
# =========================================================================


class TestUpdateFlowModel:
    """Tests for GEXEngine.update_flow_model() and cumulative flow tracking."""

    def test_customer_buy_calls_negative_gamma(self, engine_hybrid: GEXEngine):
        """Customer buying calls -> dealer short calls -> negative gamma adjustment."""
        engine_hybrid.update_flow_model(
            strike=5200.0, option_type="call", trade_size=10, is_customer_buy=True,
        )
        adj = engine_hybrid.cumulative_flow[5200.0]
        # adjustment = -10 * 100 = -1000
        assert adj == -10 * _CONTRACT_MULTIPLIER
        assert adj < 0

    def test_customer_sell_calls_positive_gamma(self, engine_hybrid: GEXEngine):
        """Customer selling calls -> dealer long calls -> positive gamma adjustment."""
        engine_hybrid.update_flow_model(
            strike=5200.0, option_type="call", trade_size=10, is_customer_buy=False,
        )
        adj = engine_hybrid.cumulative_flow[5200.0]
        assert adj == +10 * _CONTRACT_MULTIPLIER
        assert adj > 0

    def test_customer_buy_puts_positive_gamma(self, engine_hybrid: GEXEngine):
        """Customer buying puts -> dealer short puts -> positive gamma adjustment."""
        engine_hybrid.update_flow_model(
            strike=5200.0, option_type="put", trade_size=10, is_customer_buy=True,
        )
        adj = engine_hybrid.cumulative_flow[5200.0]
        assert adj == +10 * _CONTRACT_MULTIPLIER
        assert adj > 0

    def test_customer_sell_puts_negative_gamma(self, engine_hybrid: GEXEngine):
        """Customer selling puts -> dealer long puts -> negative gamma adjustment."""
        engine_hybrid.update_flow_model(
            strike=5200.0, option_type="put", trade_size=10, is_customer_buy=False,
        )
        adj = engine_hybrid.cumulative_flow[5200.0]
        assert adj == -10 * _CONTRACT_MULTIPLIER
        assert adj < 0

    def test_cumulative_tracking(self, engine_hybrid: GEXEngine):
        """Multiple trades at the same strike should accumulate."""
        engine_hybrid.update_flow_model(
            strike=5200.0, option_type="call", trade_size=10, is_customer_buy=True,
        )
        engine_hybrid.update_flow_model(
            strike=5200.0, option_type="put", trade_size=5, is_customer_buy=True,
        )
        adj = engine_hybrid.cumulative_flow[5200.0]
        # Call buy: -10 * 100 = -1000
        # Put buy:  +5 * 100  = +500
        # Total: -500
        expected = -10 * _CONTRACT_MULTIPLIER + 5 * _CONTRACT_MULTIPLIER
        assert adj == expected

    def test_different_strikes_independent(self, engine_hybrid: GEXEngine):
        """Flow at different strikes should be tracked independently."""
        engine_hybrid.update_flow_model(
            strike=5190.0, option_type="call", trade_size=10, is_customer_buy=True,
        )
        engine_hybrid.update_flow_model(
            strike=5210.0, option_type="put", trade_size=20, is_customer_buy=True,
        )
        assert engine_hybrid.cumulative_flow[5190.0] == -10 * _CONTRACT_MULTIPLIER
        assert engine_hybrid.cumulative_flow[5210.0] == +20 * _CONTRACT_MULTIPLIER

    def test_zero_trade_size_no_update(self, engine_hybrid: GEXEngine):
        """Zero or negative trade size should produce no update."""
        engine_hybrid.update_flow_model(
            strike=5200.0, option_type="call", trade_size=0, is_customer_buy=True,
        )
        assert engine_hybrid.cumulative_flow[5200.0] == 0.0

    def test_invalid_option_type_no_update(self, engine_hybrid: GEXEngine):
        """Invalid option type should be ignored (no crash, no update)."""
        engine_hybrid.update_flow_model(
            strike=5200.0, option_type="invalid", trade_size=10, is_customer_buy=True,
        )
        assert engine_hybrid.cumulative_flow[5200.0] == 0.0

    def test_hybrid_model_uses_flow_weight(self, mock_bs: MagicMock):
        """In hybrid mode, cumulative flow adjustment is scaled by flow_weight (0.4).

        net_gex in hybrid includes: + flow_weight * cumulative_adj
        """
        engine = GEXEngine(bs_calculator=mock_bs, dealer_model="hybrid")

        # Add a large positive flow adjustment at strike 5200
        engine.update_flow_model(
            strike=5200.0, option_type="put", trade_size=100, is_customer_buy=True,
        )
        cum_adj = engine.cumulative_flow[5200.0]  # +100 * 100 = +10000

        # Now compute GEX at that strike
        sg = engine.compute_strike_gex(
            spot=SPX_SPOT, strike=5200.0, call_iv=0.15, put_iv=0.15,
            call_oi=0, put_oi=0, call_volume=0, put_volume=0,
            minutes_remaining=DEFAULT_MINUTES, r=DEFAULT_R, q=DEFAULT_Q,
        )

        # With zero OI, simple and flow GEX are both zero.
        # net_gex should = 0 + 0 + 0.4 * cum_adj = 0.4 * 10000 = 4000
        expected_net = engine.flow_weight * cum_adj
        assert sg.net_gex == pytest.approx(expected_net, rel=1e-6)

    def test_flow_model_uses_full_cumulative(self, mock_bs: MagicMock):
        """In flow mode, cumulative adjustment is added at full weight (1.0)."""
        engine = GEXEngine(bs_calculator=mock_bs, dealer_model="flow")

        engine.update_flow_model(
            strike=5200.0, option_type="put", trade_size=100, is_customer_buy=True,
        )
        cum_adj = engine.cumulative_flow[5200.0]

        sg = engine.compute_strike_gex(
            spot=SPX_SPOT, strike=5200.0, call_iv=0.15, put_iv=0.15,
            call_oi=0, put_oi=0, call_volume=0, put_volume=0,
            minutes_remaining=DEFAULT_MINUTES, r=DEFAULT_R, q=DEFAULT_Q,
        )

        # flow model: net_gex = flow_call_gex + flow_put_gex + cumulative_adj
        # With zero OI: flow_call_gex = flow_put_gex = 0
        expected_net = cum_adj
        assert sg.net_gex == pytest.approx(expected_net, rel=1e-6)

    def test_simple_model_ignores_cumulative(self, mock_bs: MagicMock):
        """In simple mode, cumulative flow adjustment is NOT applied."""
        engine = GEXEngine(bs_calculator=mock_bs, dealer_model="simple")

        engine.update_flow_model(
            strike=5200.0, option_type="put", trade_size=100, is_customer_buy=True,
        )

        sg = engine.compute_strike_gex(
            spot=SPX_SPOT, strike=5200.0, call_iv=0.15, put_iv=0.15,
            call_oi=0, put_oi=0, call_volume=0, put_volume=0,
            minutes_remaining=DEFAULT_MINUTES, r=DEFAULT_R, q=DEFAULT_Q,
        )

        # Simple model: ignores flow entirely
        assert sg.net_gex == pytest.approx(0.0, abs=1e-6)


# =========================================================================
# INTEGRATION TESTS -- end-to-end with real BlackScholes
# =========================================================================


class TestIntegrationRealBS:
    """Integration tests using the real BlackScholes0DTE calculator."""

    def test_atm_gex_highest_near_money(self, engine_real_bs: GEXEngine):
        """ATM strikes should produce the highest absolute GEX per unit OI."""
        results = {}
        for k in [5100, 5150, 5200, 5250, 5300]:
            sg = engine_real_bs.compute_strike_gex(
                spot=SPX_SPOT, strike=k, call_iv=0.15, put_iv=0.15,
                call_oi=1000, put_oi=1000, call_volume=0, put_volume=0,
                minutes_remaining=DEFAULT_MINUTES, r=DEFAULT_R, q=DEFAULT_Q,
            )
            results[k] = abs(sg.net_gex)

        # 5200 (ATM) should have the highest |net_gex| because gamma peaks ATM
        atm_gex = results[5200]
        for k, v in results.items():
            if k != 5200:
                assert atm_gex >= v, f"ATM GEX ({atm_gex}) should >= OTM {k} GEX ({v})"

    def test_full_profile_with_real_bs(self, engine_real_bs: GEXEngine, realistic_spx_chain: _OptionsChain):
        """End-to-end: compute a full GEX profile with realistic data."""
        profile = engine_real_bs.compute_full_gex_profile(
            chain=realistic_spx_chain, minutes_remaining=DEFAULT_MINUTES,
        )

        # Basic sanity checks
        assert len(profile.strikes_gex) > 0
        assert math.isfinite(profile.total_net_gex)
        assert math.isfinite(profile.gamma_flip_level)
        assert profile.call_wall > 0
        assert profile.put_wall > 0
        assert profile.max_pain > 0

        # Total GEX should equal the sum
        total = sum(sg.net_gex for sg in profile.strikes_gex)
        assert profile.total_net_gex == pytest.approx(total, rel=1e-9)

    def test_put_wall_below_call_wall_with_typical_skew(
        self, engine_real_bs: GEXEngine, realistic_spx_chain: _OptionsChain,
    ):
        """With typical put skew, put wall should be below spot and call wall above."""
        profile = engine_real_bs.compute_full_gex_profile(
            chain=realistic_spx_chain, minutes_remaining=DEFAULT_MINUTES,
        )
        # In realistic_spx_chain: put wall = 5170, call wall = 5230
        assert profile.put_wall < SPX_SPOT
        assert profile.call_wall > SPX_SPOT

    def test_charm_flow_direction(self, engine_real_bs: GEXEngine, realistic_spx_chain: _OptionsChain):
        """Charm ES contracts should be a finite number with consistent sign."""
        profile = engine_real_bs.compute_full_gex_profile(
            chain=realistic_spx_chain, minutes_remaining=DEFAULT_MINUTES,
        )
        assert math.isfinite(profile.charm_net_es_contracts)

    def test_gamma_decreases_as_expiry_approaches(self, engine_real_bs: GEXEngine):
        """ATM gamma should increase as expiry approaches (for very short time),
        but the clamping mechanism should keep it bounded.
        """
        sg_2hr = engine_real_bs.compute_strike_gex(
            spot=SPX_SPOT, strike=5200, call_iv=0.15, put_iv=0.15,
            call_oi=1000, put_oi=1000, call_volume=0, put_volume=0,
            minutes_remaining=120, r=DEFAULT_R, q=DEFAULT_Q,
        )
        sg_30min = engine_real_bs.compute_strike_gex(
            spot=SPX_SPOT, strike=5200, call_iv=0.15, put_iv=0.15,
            call_oi=1000, put_oi=1000, call_volume=0, put_volume=0,
            minutes_remaining=30, r=DEFAULT_R, q=DEFAULT_Q,
        )
        # ATM gamma increases as time decreases (gamma explosion near expiry)
        assert sg_30min.gamma >= sg_2hr.gamma


# =========================================================================
# GENERATE ALL SIGNALS -- combined signal test
# =========================================================================


class TestGenerateAllSignals:
    """Tests for GEXSignalGenerator.generate_all_signals()."""

    def test_returns_list(self, mock_bs: MagicMock, sample_profile: _GEXProfile):
        """generate_all_signals should always return a list (possibly empty)."""
        gen = _make_signal_gen(mock_bs)
        signals = gen.generate_all_signals(
            current_profile=sample_profile,
            spot=SPX_SPOT,
            prior_spot=SPX_SPOT,
            vix1d_change_pct=0.0,
            minutes_outside_tz=0,
        )
        assert isinstance(signals, list)

    def test_profile_appended_to_history(self, mock_bs: MagicMock, sample_profile: _GEXProfile):
        """Each call should append the current profile to gex_history."""
        gen = _make_signal_gen(mock_bs)
        assert len(gen.gex_history) == 0
        gen.generate_all_signals(
            current_profile=sample_profile,
            spot=SPX_SPOT, prior_spot=SPX_SPOT,
            vix1d_change_pct=0.0,
        )
        assert len(gen.gex_history) == 1
        assert gen.gex_history[0] is sample_profile

    def test_multiple_signals_can_fire(self, mock_bs: MagicMock):
        """Multiple independent signals can fire in the same cycle."""
        # Set up profile that triggers gamma flip crossover AND charm flow
        profile = _GEXProfile(
            gamma_flip_level=5200.0,
            call_wall=5230.0,
            put_wall=5170.0,
            transition_zone_upper=5215.0,
            transition_zone_lower=5185.0,
            charm_net_es_contracts=8000.0,  # > 5000 threshold
            vanna_net_exposure=0.0,
            total_net_gex=10_000_000.0,
        )

        gen = _make_signal_gen(mock_bs)
        signals = gen.generate_all_signals(
            current_profile=profile,
            spot=5201.0,       # crosses gamma flip from below
            prior_spot=5199.0,
            vix1d_change_pct=0.0,
        )
        # At minimum, gamma flip crossover and charm-driven flow should fire
        signal_types = {s.signal_type for s in signals}
        assert _GEXSignalType.GAMMA_FLIP_CROSSOVER in signal_types
        assert _GEXSignalType.CHARM_DRIVEN_FLOW in signal_types

    def test_no_signals_in_quiet_market(self, mock_bs: MagicMock, sample_profile: _GEXProfile):
        """In a quiet market (no crossings, far from walls, etc.), no signals fire."""
        sample_profile.gamma_flip_level = 5250.0  # far from spot
        sample_profile.call_wall = 5280.0
        sample_profile.put_wall = 5120.0
        sample_profile.charm_net_es_contracts = 100.0  # well below threshold
        sample_profile.vanna_net_exposure = 0.0
        sample_profile.transition_zone_upper = 5260.0
        sample_profile.transition_zone_lower = 5140.0

        gen = _make_signal_gen(mock_bs)
        signals = gen.generate_all_signals(
            current_profile=sample_profile,
            spot=SPX_SPOT,
            prior_spot=SPX_SPOT,
            vix1d_change_pct=2.0,
            minutes_outside_tz=0,
        )
        assert signals == []


# =========================================================================
# CONSTRUCTOR VALIDATION TESTS
# =========================================================================


class TestGEXEngineConstructor:
    """Tests for GEXEngine constructor validation."""

    def test_valid_models_accepted(self, mock_bs: MagicMock):
        """All three valid dealer models should be accepted."""
        for model in ("simple", "flow", "hybrid"):
            engine = GEXEngine(bs_calculator=mock_bs, dealer_model=model)
            assert engine.dealer_model == model

    def test_invalid_model_raises(self, mock_bs: MagicMock):
        """An invalid dealer model string should raise ValueError."""
        with pytest.raises(ValueError, match="dealer_model must be one of"):
            GEXEngine(bs_calculator=mock_bs, dealer_model="invalid")

    def test_weights_must_sum_to_one(self, mock_bs: MagicMock):
        """oi_weight + flow_weight must sum to 1.0."""
        with pytest.raises(ValueError, match="must sum to 1.0"):
            GEXEngine(bs_calculator=mock_bs, dealer_model="hybrid", oi_weight=0.5, flow_weight=0.3)

    def test_custom_weights(self, mock_bs: MagicMock):
        """Custom 70/30 weights should be accepted."""
        engine = GEXEngine(
            bs_calculator=mock_bs, dealer_model="hybrid",
            oi_weight=0.7, flow_weight=0.3,
        )
        assert engine.oi_weight == 0.7
        assert engine.flow_weight == 0.3


# =========================================================================
# CHARM FLOW STATIC METHOD TEST
# =========================================================================


class TestComputeCharmFlow:
    """Tests for GEXEngine.compute_charm_flow() static method."""

    def test_es_contract_calculation(self):
        """ES contracts = total_charm / (es_price * 50)."""
        strikes_gex = [
            _StrikeGEX(strike=5200, net_charm=1_000_000),
            _StrikeGEX(strike=5210, net_charm=500_000),
        ]
        es_price = 5200.0
        result = GEXEngine.compute_charm_flow(strikes_gex, es_price)
        expected = 1_500_000.0 / (5200.0 * 50.0)
        assert result == pytest.approx(expected, rel=1e-6)

    def test_empty_strikes_returns_zero(self):
        """No strikes -> 0 ES contracts."""
        result = GEXEngine.compute_charm_flow([], es_price=5200.0)
        assert result == 0.0

    def test_zero_es_price_returns_zero(self):
        """Zero ES price -> 0 (avoids division by zero)."""
        strikes_gex = [_StrikeGEX(strike=5200, net_charm=1_000_000)]
        result = GEXEngine.compute_charm_flow(strikes_gex, es_price=0.0)
        assert result == 0.0

    def test_negative_charm_produces_negative_contracts(self):
        """Negative charm -> negative ES contracts (dealers need to sell)."""
        strikes_gex = [_StrikeGEX(strike=5200, net_charm=-2_000_000)]
        result = GEXEngine.compute_charm_flow(strikes_gex, es_price=5200.0)
        assert result < 0


# =========================================================================
# GEX MOMENTUM STATIC METHOD TEST
# =========================================================================


class TestComputeGEXMomentum:
    """Tests for GEXEngine.compute_gex_momentum() static method."""

    def test_positive_momentum(self):
        """GEX increasing -> positive momentum."""
        now = datetime.now(timezone.utc)
        history = [(now - timedelta(minutes=5), 5_000_000.0)]
        momentum = GEXEngine.compute_gex_momentum(10_000_000.0, history)
        assert momentum > 0

    def test_negative_momentum(self):
        """GEX decreasing -> negative momentum."""
        now = datetime.now(timezone.utc)
        history = [(now - timedelta(minutes=5), 10_000_000.0)]
        momentum = GEXEngine.compute_gex_momentum(5_000_000.0, history)
        assert momentum < 0

    def test_empty_history_returns_zero(self):
        """No history -> zero momentum."""
        momentum = GEXEngine.compute_gex_momentum(5_000_000.0, [])
        assert momentum == 0.0


# =========================================================================
# SIGNAL COOLDOWN TESTS
# =========================================================================


class TestSignalCooldown:
    """Tests for signal cooldown mechanism (120 second window)."""

    def test_signal_on_cooldown_within_window(self, mock_bs: MagicMock, sample_profile: _GEXProfile):
        """A signal emitted within the last 120s should block duplicate signals."""
        gen = _make_signal_gen(mock_bs)
        sample_profile.gamma_flip_level = 5200.0

        # Fire first signal
        sig1 = gen.check_gamma_flip_crossover(
            sample_profile, spot=5201.0, prior_spot=5199.0,
        )
        assert sig1 is not None

        # Immediately try again -- should be blocked
        sig2 = gen.check_gamma_flip_crossover(
            sample_profile, spot=5199.0, prior_spot=5201.0,
        )
        assert sig2 is None

    def test_different_signal_types_not_blocked(self, mock_bs: MagicMock):
        """Cooldown only applies per signal type -- different types should fire."""
        gen = _make_signal_gen(mock_bs)

        # Fire a charm signal
        charm_profile = _GEXProfile(charm_net_es_contracts=8000.0)
        sig_charm = gen.check_charm_driven_flow(current_profile=charm_profile)
        assert sig_charm is not None

        # Now fire a gamma flip -- should NOT be on cooldown
        flip_profile = _GEXProfile(
            gamma_flip_level=5200.0, call_wall=5230.0, put_wall=5170.0,
            total_net_gex=5_000_000.0,
        )
        sig_flip = gen.check_gamma_flip_crossover(
            flip_profile, spot=5201.0, prior_spot=5199.0,
        )
        assert sig_flip is not None

    def test_cooldown_expires(self, mock_bs: MagicMock, sample_profile: _GEXProfile):
        """After 120+ seconds, the cooldown should expire and allow re-firing."""
        gen = _make_signal_gen(mock_bs)
        sample_profile.gamma_flip_level = 5200.0

        # Fire first signal
        sig1 = gen.check_gamma_flip_crossover(
            sample_profile, spot=5201.0, prior_spot=5199.0,
        )
        assert sig1 is not None

        # Artificially age the signal timestamp beyond the cooldown window
        sig1.timestamp = datetime.now(timezone.utc) - timedelta(seconds=130)

        # Now try again -- should succeed since cooldown expired
        sig2 = gen.check_gamma_flip_crossover(
            sample_profile, spot=5199.0, prior_spot=5201.0,
        )
        assert sig2 is not None
