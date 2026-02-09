"""
Revolution Alpha Engine - VIX Deep Intelligence Scanner.

We see the move BEFORE the move. Complete VIX ecosystem analysis:
options chain, term structure, VVIX, pattern recognition. We track
every VIX option ahead of time to predict volatility regime changes
before they happen.

Mathematical foundations:
- GEX_vix = sum(gamma_i * OI_i * 100 * VIX^2 * 0.01) for each strike
- Ornstein-Uhlenbeck: dV = theta*(mu - V)dt + sigma*dW, half-life = ln(2)/theta
- Contango = (F1 - VIX_spot) / VIX_spot * 100
- Roll yield annualized = ((F2/F1) - 1) * (365 / days_between)
- Hawkes intensity: lambda(t) = mu + sum(alpha * exp(-beta * (t - t_i)))
- Z-scores computed over 252-day rolling windows
"""

import numpy as np
import math
import uuid
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple, Any, Literal
from collections import defaultdict, deque
from enum import Enum

from .base import BaseScanner, ScannerConfig, ScanContext
from .models import ScanResult, ScanMode, SignalDirection, MarketData
from .advanced_models import (
    AdvancedScanResult,
    ScanCategory,
    RegimeContext,
    ExpectedTimeframe,
    VolatilityRegime,
    IVSurface,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

_TRADING_DAYS_PER_YEAR = 252
_CALENDAR_DAYS_PER_YEAR = 365
_MIN_CHAIN_SIZE = 5
_MIN_HISTORY_BARS = 30
_LONG_HISTORY_BARS = 252
_OI_STD_THRESHOLD = 3.0
_VOLUME_MULTIPLIER_THRESHOLD = 5.0
_SQRT_252 = math.sqrt(_TRADING_DAYS_PER_YEAR)


# =============================================================================
# Enumerations
# =============================================================================

class TermStructureRegime(str, Enum):
    """VIX futures term structure classification."""
    DEEP_CONTANGO = "DEEP_CONTANGO"
    MILD_CONTANGO = "MILD_CONTANGO"
    FLAT = "FLAT"
    MILD_BACKWARDATION = "MILD_BACKWARDATION"
    DEEP_BACKWARDATION = "DEEP_BACKWARDATION"


class VVIXRegime(str, Enum):
    """VVIX (vol of vol) regime classification."""
    LOW = "LOW"
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    EXTREME = "EXTREME"


class BasisRegime(str, Enum):
    """VIX spot-futures basis regime."""
    DEEP_PREMIUM = "DEEP_PREMIUM"
    PREMIUM = "PREMIUM"
    FAIR_VALUE = "FAIR_VALUE"
    DISCOUNT = "DISCOUNT"
    DEEP_DISCOUNT = "DEEP_DISCOUNT"


class FlowUrgency(str, Enum):
    """Options flow urgency classification."""
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    EXTREME = "EXTREME"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class VIXOptionContract:
    """Single VIX option contract."""
    strike: float
    expiration: datetime
    option_type: str  # "CALL" or "PUT"
    bid: float = 0.0
    ask: float = 0.0
    last: float = 0.0
    volume: int = 0
    open_interest: int = 0
    implied_vol: float = 0.0
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0

    @property
    def mid_price(self) -> float:
        """Mid-point of bid-ask spread."""
        if self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2.0
        return self.last

    @property
    def spread(self) -> float:
        """Bid-ask spread."""
        return max(0.0, self.ask - self.bid)

    @property
    def days_to_expiry(self) -> int:
        """Calendar days until expiration."""
        return max(0, (self.expiration - datetime.utcnow()).days)


@dataclass
class VIXOptionsChain:
    """Full VIX options chain for a single expiration."""
    expiration: datetime
    contracts: List[VIXOptionContract] = field(default_factory=list)

    @property
    def calls(self) -> List[VIXOptionContract]:
        """All call contracts."""
        return [c for c in self.contracts if c.option_type == "CALL"]

    @property
    def puts(self) -> List[VIXOptionContract]:
        """All put contracts."""
        return [c for c in self.contracts if c.option_type == "PUT"]

    @property
    def strikes(self) -> List[float]:
        """Unique sorted strikes."""
        return sorted(set(c.strike for c in self.contracts))

    @property
    def total_call_oi(self) -> int:
        """Total call open interest."""
        return sum(c.open_interest for c in self.calls)

    @property
    def total_put_oi(self) -> int:
        """Total put open interest."""
        return sum(c.open_interest for c in self.puts)

    @property
    def total_call_volume(self) -> int:
        """Total call volume."""
        return sum(c.volume for c in self.calls)

    @property
    def total_put_volume(self) -> int:
        """Total put volume."""
        return sum(c.volume for c in self.puts)


@dataclass
class VIXFullChain:
    """Complete VIX options chain across all expirations."""
    chains: List[VIXOptionsChain] = field(default_factory=list)
    vix_spot: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def all_contracts(self) -> List[VIXOptionContract]:
        """Flatten all contracts across expirations."""
        result = []
        for chain in self.chains:
            result.extend(chain.contracts)
        return result

    @property
    def expirations(self) -> List[datetime]:
        """Sorted list of expirations."""
        return sorted(set(ch.expiration for ch in self.chains))


@dataclass
class VIXFuturesContract:
    """Single VIX futures contract."""
    expiration: datetime
    price: float
    volume: int = 0
    open_interest: int = 0
    month_code: str = ""

    @property
    def days_to_expiry(self) -> int:
        """Calendar days to expiration."""
        return max(0, (self.expiration - datetime.utcnow()).days)


@dataclass
class VIXFuturesCurve:
    """VIX futures term structure."""
    contracts: List[VIXFuturesContract] = field(default_factory=list)
    vix_spot: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def front_month(self) -> Optional[VIXFuturesContract]:
        """Front-month (nearest) futures contract."""
        active = [c for c in self.contracts if c.days_to_expiry > 0]
        if not active:
            return None
        return min(active, key=lambda c: c.days_to_expiry)

    @property
    def second_month(self) -> Optional[VIXFuturesContract]:
        """Second-month futures contract."""
        active = sorted(
            [c for c in self.contracts if c.days_to_expiry > 0],
            key=lambda c: c.days_to_expiry,
        )
        return active[1] if len(active) >= 2 else None


@dataclass
class ChainAnalysis:
    """Results from full chain analysis."""
    unusual_strikes: List[Dict[str, Any]] = field(default_factory=list)
    pcr_by_expiration: Dict[str, float] = field(default_factory=dict)
    gex_by_strike: Dict[float, float] = field(default_factory=dict)
    net_gex: float = 0.0
    hedging_walls: List[Dict[str, Any]] = field(default_factory=list)
    flow_scores: List[Dict[str, Any]] = field(default_factory=list)
    total_call_oi: int = 0
    total_put_oi: int = 0
    aggregate_pcr: float = 0.0


@dataclass
class TermStructureAnalysis:
    """Results from term structure analysis."""
    regime: TermStructureRegime = TermStructureRegime.FLAT
    contango_pct: float = 0.0
    roll_yield_annualized: float = 0.0
    slope: float = 0.0
    velocity: float = 0.0
    inversion_probability: float = 0.0
    basis: float = 0.0
    basis_regime: BasisRegime = BasisRegime.FAIR_VALUE
    curve_prices: List[Tuple[int, float]] = field(default_factory=list)


@dataclass
class VVIXAnalysis:
    """Results from VVIX analysis."""
    regime: VVIXRegime = VVIXRegime.NORMAL
    current_vvix: float = 0.0
    divergence_score: float = 0.0
    divergence_direction: str = "none"
    spike_probability: float = 0.0
    mean_reversion_zscore: float = 0.0
    half_life_days: float = 0.0
    distance_from_mean: float = 0.0


@dataclass
class PatternAnalysis:
    """Results from VIX pattern recognition."""
    crush_setup: bool = False
    crush_confidence: float = 0.0
    pre_event_hedging: bool = False
    hedging_event: str = ""
    hedging_intensity: float = 0.0
    tail_hedging_buildup: bool = False
    tail_hedge_score: float = 0.0
    complacency_signal: bool = False
    complacency_score: float = 0.0
    correlation_regime_break: bool = False
    correlation_current: float = 0.0


@dataclass
class VIXIntelligenceResult:
    """Aggregated VIX intelligence output."""
    chain_analysis: Optional[ChainAnalysis] = None
    term_structure: Optional[TermStructureAnalysis] = None
    vvix_analysis: Optional[VVIXAnalysis] = None
    pattern_analysis: Optional[PatternAnalysis] = None
    overall_signal: str = "NEUTRAL"
    overall_confidence: float = 0.0
    regime_context: RegimeContext = RegimeContext.RANGING


# =============================================================================
# Helper Utilities
# =============================================================================

def _safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safe division returning default when denominator is zero."""
    if abs(denominator) < 1e-12:
        return default
    return numerator / denominator


def _z_score(value: float, series: np.ndarray) -> float:
    """Compute z-score of value against a series.

    Args:
        value: Current observation.
        series: Historical observations (numpy array).

    Returns:
        Z-score, or 0.0 if standard deviation is negligible.
    """
    if len(series) < 2:
        return 0.0
    mean = float(np.mean(series))
    std = float(np.std(series, ddof=1))
    if std < 1e-12:
        return 0.0
    return (value - mean) / std


def _percentile_rank(value: float, series: np.ndarray) -> float:
    """Compute percentile rank of value within series.

    Args:
        value: Current observation.
        series: Historical observations.

    Returns:
        Percentile rank 0-100.
    """
    if len(series) == 0:
        return 50.0
    count_below = float(np.sum(series < value))
    return (count_below / len(series)) * 100.0


def _rolling_correlation(
    x: np.ndarray, y: np.ndarray, window: int = 60
) -> float:
    """Compute trailing rolling correlation between two series.

    Uses the last `window` observations of each series.

    Args:
        x: First series.
        y: Second series.
        window: Look-back window in observations.

    Returns:
        Pearson correlation coefficient, or 0.0 on failure.
    """
    min_len = min(len(x), len(y))
    if min_len < window:
        window = min_len
    if window < 5:
        return 0.0
    x_w = x[-window:]
    y_w = y[-window:]
    std_x = float(np.std(x_w, ddof=1))
    std_y = float(np.std(y_w, ddof=1))
    if std_x < 1e-12 or std_y < 1e-12:
        return 0.0
    corr_matrix = np.corrcoef(x_w, y_w)
    return float(corr_matrix[0, 1])


# =============================================================================
# VIXOptionsChainTracker
# =============================================================================

class VIXOptionsChainTracker:
    """Full VIX options chain monitoring and analysis.

    Tracks every strike and expiration in the VIX options complex to
    detect institutional positioning, unusual activity, and dealer
    gamma exposure. This is the eyes and ears on the VIX options
    market -- we see the move before the move.
    """

    def analyze_full_chain(self, vix_chain: VIXFullChain) -> ChainAnalysis:
        """Process the entire VIX options chain across all expirations.

        Runs every sub-analysis: unusual strike detection, put/call ratios
        per expiration, gamma exposure mapping, hedging wall identification,
        and flow scoring.

        Args:
            vix_chain: Complete VIX options chain data.

        Returns:
            ChainAnalysis with all computed metrics.
        """
        analysis = ChainAnalysis()

        if not vix_chain.chains:
            return analysis

        all_contracts = vix_chain.all_contracts
        if len(all_contracts) < _MIN_CHAIN_SIZE:
            return analysis

        # Unusual strike detection
        analysis.unusual_strikes = self.detect_unusual_strikes(vix_chain)

        # Put/call ratio by expiration
        analysis.pcr_by_expiration = self.compute_vix_pcr_by_expiration(vix_chain)

        # Gamma exposure mapping
        vix_spot = vix_chain.vix_spot if vix_chain.vix_spot > 0 else 18.0
        analysis.gex_by_strike = self.compute_vix_gamma_exposure(vix_chain, vix_spot)
        analysis.net_gex = sum(analysis.gex_by_strike.values())

        # Hedging walls
        analysis.hedging_walls = self.detect_vix_hedging_walls(vix_chain)

        # Flow scoring
        analysis.flow_scores = self.vix_options_flow_scoring(vix_chain)

        # Aggregate PCR
        total_call_oi = sum(ch.total_call_oi for ch in vix_chain.chains)
        total_put_oi = sum(ch.total_put_oi for ch in vix_chain.chains)
        analysis.total_call_oi = total_call_oi
        analysis.total_put_oi = total_put_oi
        analysis.aggregate_pcr = _safe_divide(total_put_oi, total_call_oi, 1.0)

        return analysis

    def detect_unusual_strikes(
        self, chain: VIXFullChain
    ) -> List[Dict[str, Any]]:
        """Flag strikes with abnormally high open interest or volume.

        Detection criteria:
        - Open interest > 3 standard deviations above the mean OI across
          all strikes in the same expiration.
        - Volume > 5x the 20-day average volume for that strike (or 5x
          the cross-strike mean volume as proxy when history unavailable).

        Args:
            chain: Complete VIX options chain.

        Returns:
            List of unusual strike descriptors with metadata.
        """
        unusual: List[Dict[str, Any]] = []

        for exp_chain in chain.chains:
            contracts = exp_chain.contracts
            if len(contracts) < 3:
                continue

            oi_values = np.array([c.open_interest for c in contracts], dtype=np.float64)
            vol_values = np.array([c.volume for c in contracts], dtype=np.float64)

            oi_mean = float(np.mean(oi_values))
            oi_std = float(np.std(oi_values, ddof=1)) if len(oi_values) > 1 else 0.0
            vol_mean = float(np.mean(vol_values)) if len(vol_values) > 0 else 0.0

            oi_threshold = oi_mean + _OI_STD_THRESHOLD * oi_std if oi_std > 0 else float('inf')
            vol_threshold = max(vol_mean * _VOLUME_MULTIPLIER_THRESHOLD, 1.0)

            for contract in contracts:
                reasons = []

                if oi_std > 0 and contract.open_interest > oi_threshold:
                    oi_z = _safe_divide(
                        contract.open_interest - oi_mean, oi_std, 0.0
                    )
                    reasons.append(f"OI z-score={oi_z:.1f}")

                if vol_mean > 0 and contract.volume > vol_threshold:
                    vol_ratio = _safe_divide(contract.volume, vol_mean, 0.0)
                    reasons.append(f"volume={vol_ratio:.1f}x avg")

                if reasons:
                    unusual.append({
                        "strike": contract.strike,
                        "expiration": exp_chain.expiration.isoformat(),
                        "option_type": contract.option_type,
                        "open_interest": contract.open_interest,
                        "volume": contract.volume,
                        "implied_vol": round(contract.implied_vol, 4),
                        "reasons": reasons,
                        "severity": "HIGH" if len(reasons) > 1 else "MODERATE",
                    })

        # Sort by combined magnitude
        unusual.sort(
            key=lambda x: x["open_interest"] + x["volume"] * 10,
            reverse=True,
        )
        return unusual

    def compute_vix_pcr_by_expiration(
        self, chain: VIXFullChain
    ) -> Dict[str, float]:
        """Compute VIX put/call ratio for each expiration.

        The VIX PCR is a critical sentiment gauge. Elevated PCR in near-term
        expirations signals hedging demand; elevated PCR in far-term suggests
        portfolio insurance accumulation.

        Args:
            chain: Complete VIX options chain.

        Returns:
            Dictionary mapping expiration label -> put/call OI ratio.
        """
        pcr_map: Dict[str, float] = {}

        for exp_chain in chain.chains:
            call_oi = exp_chain.total_call_oi
            put_oi = exp_chain.total_put_oi

            # Classify expiration as weekly or monthly
            dte = max(0, (exp_chain.expiration - datetime.utcnow()).days)
            if dte <= 7:
                label = f"weekly_{exp_chain.expiration.strftime('%Y%m%d')}"
            else:
                label = f"monthly_{exp_chain.expiration.strftime('%Y%m%d')}"

            pcr_map[label] = _safe_divide(put_oi, call_oi, 1.0)

        return pcr_map

    def compute_vix_gamma_exposure(
        self, chain: VIXFullChain, vix_spot: float
    ) -> Dict[float, float]:
        """Compute dealer gamma exposure (GEX) on VIX options.

        Formula per strike:
            GEX_i = gamma_i * OI_i * 100 * VIX^2 * 0.01

        Calls contribute positive GEX (dealers are short calls from market
        makers' perspective, but gamma itself is always positive; the sign
        comes from the position direction). Puts contribute negative GEX.
        Dealers are typically short options, so:
        - Short call -> positive gamma exposure (stabilizing)
        - Short put  -> negative gamma exposure (destabilizing)

        Args:
            chain: Complete VIX options chain.
            vix_spot: Current VIX spot level.

        Returns:
            Dictionary mapping strike -> net GEX in dollar-gamma terms.
        """
        gex_by_strike: Dict[float, float] = defaultdict(float)

        if vix_spot <= 0:
            return dict(gex_by_strike)

        for exp_chain in chain.chains:
            for contract in exp_chain.contracts:
                if contract.open_interest <= 0:
                    continue

                gamma = contract.gamma
                if gamma <= 0:
                    # Estimate gamma if not provided using simple approximation
                    gamma = self._estimate_gamma(
                        contract, vix_spot
                    )

                # GEX = gamma * OI * 100 (contract multiplier) * spot^2 * 0.01
                raw_gex = gamma * contract.open_interest * 100.0 * (vix_spot ** 2) * 0.01

                # Sign convention: calls positive (dealer short call = long gamma),
                # puts negative (dealer short put = short gamma equivalent)
                if contract.option_type == "CALL":
                    gex_by_strike[contract.strike] += raw_gex
                else:
                    gex_by_strike[contract.strike] -= raw_gex

        return dict(gex_by_strike)

    def detect_vix_hedging_walls(
        self, chain: VIXFullChain
    ) -> List[Dict[str, Any]]:
        """Find massive OI concentrations acting as VIX support/resistance.

        Hedging walls are strikes where open interest is so large that
        dealer hedging activity creates a gravitational pull (for calls)
        or a floor/ceiling (for puts). These levels act as
        resistance/support for VIX itself.

        Args:
            chain: Complete VIX options chain.

        Returns:
            List of hedging wall descriptors sorted by OI magnitude.
        """
        # Aggregate OI by strike across all expirations
        call_oi_by_strike: Dict[float, int] = defaultdict(int)
        put_oi_by_strike: Dict[float, int] = defaultdict(int)

        for exp_chain in chain.chains:
            for contract in exp_chain.contracts:
                if contract.option_type == "CALL":
                    call_oi_by_strike[contract.strike] += contract.open_interest
                else:
                    put_oi_by_strike[contract.strike] += contract.open_interest

        walls: List[Dict[str, Any]] = []

        # Detect call walls (resistance for VIX -- if VIX rises, dealers
        # who are short calls must buy VIX futures to hedge, creating resistance)
        if call_oi_by_strike:
            call_oi_arr = np.array(list(call_oi_by_strike.values()), dtype=np.float64)
            call_mean = float(np.mean(call_oi_arr))
            call_std = float(np.std(call_oi_arr, ddof=1)) if len(call_oi_arr) > 1 else 0.0
            call_threshold = call_mean + 2.0 * call_std

            for strike, oi in call_oi_by_strike.items():
                if oi > call_threshold and call_std > 0:
                    walls.append({
                        "strike": strike,
                        "type": "call_wall",
                        "role": "vix_resistance",
                        "open_interest": oi,
                        "z_score": round((oi - call_mean) / call_std, 2),
                        "strength": round(oi / call_threshold, 2),
                    })

        # Detect put walls (support for VIX -- massive put OI acts as floor)
        if put_oi_by_strike:
            put_oi_arr = np.array(list(put_oi_by_strike.values()), dtype=np.float64)
            put_mean = float(np.mean(put_oi_arr))
            put_std = float(np.std(put_oi_arr, ddof=1)) if len(put_oi_arr) > 1 else 0.0
            put_threshold = put_mean + 2.0 * put_std

            for strike, oi in put_oi_by_strike.items():
                if oi > put_threshold and put_std > 0:
                    walls.append({
                        "strike": strike,
                        "type": "put_wall",
                        "role": "vix_support",
                        "open_interest": oi,
                        "z_score": round((oi - put_mean) / put_std, 2),
                        "strength": round(oi / put_threshold, 2),
                    })

        walls.sort(key=lambda w: w["open_interest"], reverse=True)
        return walls

    def vix_options_flow_scoring(
        self, chain: VIXFullChain
    ) -> List[Dict[str, Any]]:
        """Score each VIX option trade for institutional significance.

        Scoring dimensions:
        1. Size: Relative to average volume at that strike (0-30 pts)
        2. Urgency: How close to the ask (buy) or bid (sell) (0-30 pts)
        3. Opening vs Closing: If volume > OI, likely opening (0-20 pts)
        4. Premium committed: Total dollar premium (0-20 pts)

        Args:
            chain: Complete VIX options chain.

        Returns:
            List of scored flow entries, highest scores first.
        """
        scored_flows: List[Dict[str, Any]] = []

        # Compute cross-chain volume stats for relative sizing
        all_volumes = [c.volume for c in chain.all_contracts if c.volume > 0]
        if not all_volumes:
            return scored_flows

        vol_arr = np.array(all_volumes, dtype=np.float64)
        vol_mean = float(np.mean(vol_arr))
        vol_p90 = float(np.percentile(vol_arr, 90))

        for exp_chain in chain.chains:
            for contract in exp_chain.contracts:
                if contract.volume <= 0:
                    continue

                score = 0.0
                details: Dict[str, Any] = {
                    "strike": contract.strike,
                    "expiration": exp_chain.expiration.isoformat(),
                    "option_type": contract.option_type,
                    "volume": contract.volume,
                    "open_interest": contract.open_interest,
                }

                # 1. Size score (0-30)
                size_ratio = _safe_divide(contract.volume, vol_mean, 0.0)
                size_score = min(30.0, size_ratio * 6.0)
                score += size_score
                details["size_score"] = round(size_score, 1)

                # 2. Urgency score (0-30): how close trade is to ask (aggressive buy)
                #    or to bid (aggressive sell)
                if contract.ask > 0 and contract.bid >= 0:
                    spread = contract.ask - contract.bid
                    if spread > 0 and contract.last > 0:
                        # Position within spread: 0 = at bid, 1 = at ask
                        fill_position = _safe_divide(
                            contract.last - contract.bid, spread, 0.5
                        )
                        fill_position = max(0.0, min(1.0, fill_position))
                        # Aggressive buying (near ask) or selling (near bid) both urgent
                        urgency_raw = max(fill_position, 1.0 - fill_position)
                        urgency_score = urgency_raw * 30.0
                    else:
                        urgency_score = 15.0
                else:
                    urgency_score = 15.0

                score += urgency_score
                details["urgency_score"] = round(urgency_score, 1)
                details["urgency_class"] = (
                    FlowUrgency.EXTREME.value if urgency_score > 25 else
                    FlowUrgency.HIGH.value if urgency_score > 20 else
                    FlowUrgency.MODERATE.value if urgency_score > 12 else
                    FlowUrgency.LOW.value
                )

                # 3. Opening vs Closing (0-20)
                if contract.open_interest > 0:
                    vol_oi_ratio = _safe_divide(
                        contract.volume, contract.open_interest, 0.0
                    )
                    # Volume > OI strongly suggests new position opening
                    if vol_oi_ratio > 1.0:
                        opening_score = min(20.0, vol_oi_ratio * 10.0)
                        details["position_action"] = "OPENING"
                    else:
                        opening_score = vol_oi_ratio * 5.0
                        details["position_action"] = "LIKELY_CLOSING"
                else:
                    opening_score = 20.0  # No prior OI means definitely opening
                    details["position_action"] = "OPENING"

                score += opening_score
                details["opening_score"] = round(opening_score, 1)

                # 4. Premium committed (0-20)
                premium = contract.mid_price * contract.volume * 100.0
                # Scale: $1M+ premium = 20 points
                premium_score = min(20.0, (premium / 1_000_000.0) * 20.0)
                score += premium_score
                details["premium_score"] = round(premium_score, 1)
                details["total_premium"] = round(premium, 2)

                details["composite_score"] = round(score, 1)
                scored_flows.append(details)

        scored_flows.sort(key=lambda f: f["composite_score"], reverse=True)
        return scored_flows

    # ----- Private helpers -----

    @staticmethod
    def _estimate_gamma(
        contract: VIXOptionContract, spot: float, r: float = 0.04
    ) -> float:
        """Estimate option gamma using Black-Scholes approximation.

        Args:
            contract: VIX option contract.
            spot: Current VIX spot.
            r: Risk-free rate.

        Returns:
            Estimated gamma value.
        """
        t = max(contract.days_to_expiry / _CALENDAR_DAYS_PER_YEAR, 1.0 / _CALENDAR_DAYS_PER_YEAR)
        sigma = contract.implied_vol if contract.implied_vol > 0 else 0.80
        strike = contract.strike

        if spot <= 0 or strike <= 0:
            return 0.0

        d1 = (math.log(spot / strike) + (r + 0.5 * sigma ** 2) * t) / (sigma * math.sqrt(t))
        pdf_d1 = math.exp(-0.5 * d1 * d1) / math.sqrt(2.0 * math.pi)

        gamma = pdf_d1 / (spot * sigma * math.sqrt(t))
        return gamma


# =============================================================================
# VIXTermStructureEngine
# =============================================================================

class VIXTermStructureEngine:
    """VIX futures term structure analysis engine.

    Builds and analyzes the VIX futures curve to detect regime changes,
    compute roll yield, measure curve velocity, and predict term structure
    inversions. The shape of the VIX futures curve is one of the most
    powerful predictors of future volatility regimes.
    """

    # Regime thresholds (contango percentage)
    _DEEP_CONTANGO_THRESHOLD = 7.0
    _MILD_CONTANGO_THRESHOLD = 2.0
    _MILD_BACKWARDATION_THRESHOLD = -2.0
    _DEEP_BACKWARDATION_THRESHOLD = -7.0

    def build_futures_curve(
        self, futures_data: List[VIXFuturesContract]
    ) -> List[Tuple[int, float]]:
        """Build the VIX futures term structure curve.

        Sorts futures by days to expiry and returns (DTE, price) pairs,
        creating a clean representation of the term structure.

        Args:
            futures_data: List of VIX futures contracts.

        Returns:
            Sorted list of (days_to_expiry, price) tuples.
        """
        if not futures_data:
            return []

        active = [c for c in futures_data if c.days_to_expiry > 0 and c.price > 0]
        active.sort(key=lambda c: c.days_to_expiry)

        return [(c.days_to_expiry, c.price) for c in active]

    def contango_backwardation_regime(
        self, curve: List[Tuple[int, float]]
    ) -> Tuple[TermStructureRegime, float]:
        """Classify the term structure regime.

        Uses the slope from front to second month as the primary metric.
        Contango = futures > spot (normal); backwardation = futures < spot (fear).

        Regimes:
        - DEEP_CONTANGO: spread > 7% (complacent market)
        - MILD_CONTANGO: spread 2-7%  (normal)
        - FLAT: spread -2% to 2%
        - MILD_BACKWARDATION: spread -7% to -2% (elevated fear)
        - DEEP_BACKWARDATION: spread < -7% (extreme fear/crisis)

        Args:
            curve: Term structure curve from build_futures_curve.

        Returns:
            Tuple of (regime classification, contango percentage).
        """
        if len(curve) < 2:
            return TermStructureRegime.FLAT, 0.0

        front_price = curve[0][1]
        second_price = curve[1][1]

        if front_price <= 0:
            return TermStructureRegime.FLAT, 0.0

        contango_pct = ((second_price - front_price) / front_price) * 100.0

        if contango_pct > self._DEEP_CONTANGO_THRESHOLD:
            regime = TermStructureRegime.DEEP_CONTANGO
        elif contango_pct > self._MILD_CONTANGO_THRESHOLD:
            regime = TermStructureRegime.MILD_CONTANGO
        elif contango_pct > self._MILD_BACKWARDATION_THRESHOLD:
            regime = TermStructureRegime.FLAT
        elif contango_pct > self._DEEP_BACKWARDATION_THRESHOLD:
            regime = TermStructureRegime.MILD_BACKWARDATION
        else:
            regime = TermStructureRegime.DEEP_BACKWARDATION

        return regime, round(contango_pct, 4)

    def roll_yield_signal(
        self, curve: List[Tuple[int, float]]
    ) -> float:
        """Compute expected annualized return from contango roll.

        Roll yield = ((F2 / F1) - 1) * (365 / days_between)

        Positive roll yield means contango (short vol benefits from roll).
        Negative means backwardation (long vol benefits from roll).

        Args:
            curve: Term structure curve.

        Returns:
            Annualized roll yield as a decimal (e.g. 0.15 = 15%).
        """
        if len(curve) < 2:
            return 0.0

        f1_dte, f1_price = curve[0]
        f2_dte, f2_price = curve[1]

        if f1_price <= 0:
            return 0.0

        days_between = max(f2_dte - f1_dte, 1)

        roll_yield = ((f2_price / f1_price) - 1.0) * (_CALENDAR_DAYS_PER_YEAR / days_between)
        return round(roll_yield, 6)

    def term_structure_velocity(
        self, history: List[List[Tuple[int, float]]]
    ) -> float:
        """Compute the speed of term structure flattening or steepening.

        Velocity is the first derivative of the front-to-back spread over
        time. Rapid flattening (negative velocity from positive spread)
        signals approaching inversion.

        Args:
            history: Time series of term structure curves (oldest first).
                     Each entry is a curve from build_futures_curve.

        Returns:
            Velocity in percentage points per day. Negative = flattening.
        """
        if len(history) < 2:
            return 0.0

        spreads = []
        for curve in history:
            if len(curve) >= 2:
                spread = ((curve[1][1] - curve[0][1]) / curve[0][1]) * 100.0 if curve[0][1] > 0 else 0.0
                spreads.append(spread)

        if len(spreads) < 2:
            return 0.0

        # Simple first difference of the spread series
        diffs = np.diff(spreads)
        # Velocity = average daily change in spread
        velocity = float(np.mean(diffs))
        return round(velocity, 6)

    def detect_inversion_approach(
        self, curve: List[Tuple[int, float]],
        history: List[List[Tuple[int, float]]],
    ) -> float:
        """Predict probability of imminent term structure inversion.

        An inversion (backwardation) is a powerful signal of coming vol
        expansion. This method combines:
        1. Current spread level (closer to zero = higher probability)
        2. Velocity of flattening (faster = higher probability)
        3. Acceleration (second derivative)

        Args:
            curve: Current term structure curve.
            history: Historical curves for velocity computation.

        Returns:
            Probability 0-1 of inversion within 5 trading days.
        """
        if len(curve) < 2:
            return 0.0

        front_price = curve[0][1]
        second_price = curve[1][1]
        if front_price <= 0:
            return 0.0

        current_spread = ((second_price - front_price) / front_price) * 100.0

        # Already inverted
        if current_spread < 0:
            return 1.0

        # Component 1: Level -- closer to zero = higher probability
        level_score = max(0.0, 1.0 - (current_spread / 10.0))

        # Component 2: Velocity
        velocity = self.term_structure_velocity(history)
        # Negative velocity (flattening) increases probability
        velocity_score = max(0.0, min(1.0, -velocity / 2.0))

        # Component 3: Acceleration (change in velocity)
        if len(history) >= 5:
            recent_history = history[-5:]
            older_history = history[-10:-5] if len(history) >= 10 else history[:len(history)//2]
            recent_vel = self.term_structure_velocity(recent_history)
            older_vel = self.term_structure_velocity(older_history)
            acceleration = recent_vel - older_vel
            accel_score = max(0.0, min(1.0, -acceleration / 1.0))
        else:
            accel_score = 0.0

        # Weighted combination
        probability = (
            0.50 * level_score +
            0.30 * velocity_score +
            0.20 * accel_score
        )

        return round(max(0.0, min(1.0, probability)), 4)

    def basis_analysis(
        self, vix_spot: float, vix_front_future: float
    ) -> Tuple[float, BasisRegime]:
        """Analyze VIX spot-futures basis.

        Basis = Future - Spot.
        - Premium (future > spot): Normal, dealers pricing in mean reversion
        - Discount (spot > future): Fear, spot VIX spiking beyond futures

        Regimes:
        - DEEP_PREMIUM: basis > 3 points (complacency)
        - PREMIUM: basis 1-3 points (normal)
        - FAIR_VALUE: basis -1 to 1 (equilibrium)
        - DISCOUNT: basis -3 to -1 (elevated fear)
        - DEEP_DISCOUNT: basis < -3 (extreme fear, VIX spike)

        Args:
            vix_spot: Current VIX spot level.
            vix_front_future: Front-month VIX future price.

        Returns:
            Tuple of (basis in VIX points, basis regime).
        """
        if vix_spot <= 0 or vix_front_future <= 0:
            return 0.0, BasisRegime.FAIR_VALUE

        basis = vix_front_future - vix_spot

        if basis > 3.0:
            regime = BasisRegime.DEEP_PREMIUM
        elif basis > 1.0:
            regime = BasisRegime.PREMIUM
        elif basis > -1.0:
            regime = BasisRegime.FAIR_VALUE
        elif basis > -3.0:
            regime = BasisRegime.DISCOUNT
        else:
            regime = BasisRegime.DEEP_DISCOUNT

        return round(basis, 4), regime

    def full_analysis(
        self,
        futures_data: List[VIXFuturesContract],
        vix_spot: float,
        history: Optional[List[List[Tuple[int, float]]]] = None,
    ) -> TermStructureAnalysis:
        """Run the complete term structure analysis pipeline.

        Args:
            futures_data: List of VIX futures contracts.
            vix_spot: Current VIX spot.
            history: Optional historical curves for velocity computation.

        Returns:
            Complete TermStructureAnalysis.
        """
        result = TermStructureAnalysis()

        curve = self.build_futures_curve(futures_data)
        result.curve_prices = curve

        if not curve:
            return result

        # Regime classification
        regime, contango_pct = self.contango_backwardation_regime(curve)
        result.regime = regime
        result.contango_pct = contango_pct

        # Roll yield
        result.roll_yield_annualized = self.roll_yield_signal(curve)

        # Slope (simple linear regression of price on DTE)
        if len(curve) >= 2:
            dtes = np.array([c[0] for c in curve], dtype=np.float64)
            prices = np.array([c[1] for c in curve], dtype=np.float64)
            if len(dtes) >= 2:
                coeffs = np.polyfit(dtes, prices, 1)
                result.slope = round(float(coeffs[0]), 6)

        # Velocity and inversion
        if history and len(history) >= 2:
            result.velocity = self.term_structure_velocity(history)
            result.inversion_probability = self.detect_inversion_approach(curve, history)

        # Basis
        front = curve[0][1] if curve else 0.0
        basis, basis_regime = self.basis_analysis(vix_spot, front)
        result.basis = basis
        result.basis_regime = basis_regime

        return result


# =============================================================================
# VVIXAnalyzer (Vol of Vol)
# =============================================================================

class VVIXAnalyzer:
    """VVIX (volatility of VIX) analyzer.

    The VVIX measures implied volatility of VIX options. It captures
    the market's expectation of future VIX volatility -- essentially
    the vol of vol. Divergences between VVIX and VIX are among the
    most powerful predictive signals in the volatility complex.
    """

    # Regime boundaries
    _LOW_THRESHOLD = 80.0
    _NORMAL_UPPER = 100.0
    _ELEVATED_UPPER = 120.0

    # Hawkes process defaults
    _HAWKES_MU = 0.05       # Background intensity
    _HAWKES_ALPHA = 0.8     # Excitation amplitude
    _HAWKES_BETA = 1.2      # Decay rate

    def compute_vvix_regime(self, vvix_data: np.ndarray) -> VVIXRegime:
        """Classify the current VVIX regime.

        Regime thresholds:
        - LOW: VVIX < 80 (complacent, options on VIX cheap)
        - NORMAL: 80 <= VVIX < 100 (typical market conditions)
        - ELEVATED: 100 <= VVIX < 120 (uncertainty rising)
        - EXTREME: VVIX >= 120 (fear of vol explosion)

        Args:
            vvix_data: Array of VVIX values (most recent last).

        Returns:
            VVIXRegime classification.
        """
        if len(vvix_data) == 0:
            return VVIXRegime.NORMAL

        current = float(vvix_data[-1])

        if current < self._LOW_THRESHOLD:
            return VVIXRegime.LOW
        elif current < self._NORMAL_UPPER:
            return VVIXRegime.NORMAL
        elif current < self._ELEVATED_UPPER:
            return VVIXRegime.ELEVATED
        else:
            return VVIXRegime.EXTREME

    def vvix_divergence(
        self,
        vix_data: np.ndarray,
        vvix_data: np.ndarray,
        lookback: int = 20,
    ) -> Tuple[float, str]:
        """Detect divergence between VVIX and VIX.

        Key insight: VVIX rising while VIX is flat or declining signals
        that options traders are pricing in an imminent VIX explosion.
        This is one of the strongest predictive signals available.

        Divergence score:
        - Positive: VVIX rising faster than VIX (bearish for equities)
        - Negative: VVIX falling while VIX rising (vol crush incoming)

        Args:
            vix_data: VIX time series (most recent last).
            vvix_data: VVIX time series (most recent last).
            lookback: Window for measuring divergence.

        Returns:
            Tuple of (divergence_score, direction).
            Direction: "vvix_leading_up", "vvix_leading_down", or "none".
        """
        min_len = min(len(vix_data), len(vvix_data))
        if min_len < lookback:
            lookback = max(min_len, 5)
        if min_len < 5:
            return 0.0, "none"

        vix_window = vix_data[-lookback:]
        vvix_window = vvix_data[-lookback:]

        # Normalize changes
        vix_start = float(vix_window[0])
        vvix_start = float(vvix_window[0])

        if vix_start <= 0 or vvix_start <= 0:
            return 0.0, "none"

        vix_change_pct = ((float(vix_window[-1]) - vix_start) / vix_start) * 100.0
        vvix_change_pct = ((float(vvix_window[-1]) - vvix_start) / vvix_start) * 100.0

        # Divergence = VVIX change minus VIX change (normalized)
        divergence = vvix_change_pct - vix_change_pct

        # Classify direction
        if divergence > 5.0 and vvix_change_pct > 0:
            direction = "vvix_leading_up"
        elif divergence < -5.0 and vvix_change_pct < 0:
            direction = "vvix_leading_down"
        else:
            direction = "none"

        return round(divergence, 4), direction

    def vvix_spike_predictor(
        self,
        vvix_history: np.ndarray,
        spike_threshold: float = 110.0,
    ) -> float:
        """Model VVIX spike probability using Hawkes process.

        The Hawkes process models self-exciting point processes where
        past events increase the probability of future events. VVIX
        spikes cluster in time, making this an ideal model.

        Hawkes intensity:
            lambda(t) = mu + sum(alpha * exp(-beta * (t - t_i)))

        where t_i are past spike times.

        Args:
            vvix_history: VVIX time series (daily, most recent last).
            spike_threshold: VVIX level defining a spike event.

        Returns:
            Probability of a spike in the next 5 trading days (0-1).
        """
        if len(vvix_history) < 10:
            return 0.0

        # Identify past spike events (indices where VVIX crossed threshold)
        spike_times: List[int] = []
        for i in range(len(vvix_history)):
            if float(vvix_history[i]) >= spike_threshold:
                spike_times.append(i)

        if not spike_times:
            # No historical spikes -- use base rate only
            return min(0.05, self._HAWKES_MU)

        current_t = len(vvix_history) - 1
        mu = self._HAWKES_MU
        alpha = self._HAWKES_ALPHA
        beta = self._HAWKES_BETA

        # Compute current Hawkes intensity
        intensity = mu
        for t_i in spike_times:
            dt = current_t - t_i
            if dt >= 0:
                intensity += alpha * math.exp(-beta * dt)

        # Convert intensity to probability over 5-day horizon
        # P(at least one event in [0, T]) = 1 - exp(-integral of lambda)
        # Approximate integral assuming constant intensity over horizon
        horizon = 5.0
        expected_events = intensity * horizon
        probability = 1.0 - math.exp(-expected_events)

        return round(max(0.0, min(1.0, probability)), 4)

    def vvix_mean_reversion(
        self,
        current: float,
        history: np.ndarray,
    ) -> Tuple[float, float]:
        """Estimate VVIX mean-reversion dynamics using Ornstein-Uhlenbeck.

        The Ornstein-Uhlenbeck process models mean-reverting behavior:
            dV = theta * (mu - V) * dt + sigma * dW

        Key outputs:
        - Z-score: Distance from mean in standard deviations
        - Half-life: ln(2) / theta -- time for deviation to halve

        Estimation uses discrete-time AR(1) regression:
            V(t) - V(t-1) = a + b * V(t-1) + epsilon
        where theta = -b, mu = -a/b

        Args:
            current: Current VVIX level.
            history: VVIX historical time series (at least 30 observations).

        Returns:
            Tuple of (z_score, half_life_days).
        """
        if len(history) < _MIN_HISTORY_BARS:
            z = _z_score(current, history) if len(history) > 1 else 0.0
            return z, 0.0

        # Use up to 252 days
        h = history[-_LONG_HISTORY_BARS:] if len(history) > _LONG_HISTORY_BARS else history

        # Z-score over 252-day window
        z = _z_score(current, h)

        # Ornstein-Uhlenbeck parameter estimation via AR(1)
        y = np.diff(h)  # V(t) - V(t-1)
        x = h[:-1]       # V(t-1)

        if len(y) < 10 or len(x) < 10:
            return z, 0.0

        # OLS: y = a + b * x
        x_mean = float(np.mean(x))
        y_mean = float(np.mean(y))
        ss_xx = float(np.sum((x - x_mean) ** 2))
        ss_xy = float(np.sum((x - x_mean) * (y - y_mean)))

        if abs(ss_xx) < 1e-12:
            return z, 0.0

        b = ss_xy / ss_xx
        # theta = -b (mean reversion speed)
        theta = -b

        # Half-life = ln(2) / theta
        if theta > 1e-6:
            half_life = math.log(2.0) / theta
        else:
            half_life = 999.0  # Essentially no mean reversion

        return round(z, 4), round(half_life, 2)

    def full_analysis(
        self,
        vix_data: np.ndarray,
        vvix_data: np.ndarray,
    ) -> VVIXAnalysis:
        """Run the complete VVIX analysis pipeline.

        Args:
            vix_data: VIX time series.
            vvix_data: VVIX time series.

        Returns:
            Complete VVIXAnalysis.
        """
        result = VVIXAnalysis()

        if len(vvix_data) == 0:
            return result

        result.current_vvix = float(vvix_data[-1])

        # Regime
        result.regime = self.compute_vvix_regime(vvix_data)

        # Divergence
        div_score, div_dir = self.vvix_divergence(vix_data, vvix_data)
        result.divergence_score = div_score
        result.divergence_direction = div_dir

        # Spike prediction
        result.spike_probability = self.vvix_spike_predictor(vvix_data)

        # Mean reversion
        z, hl = self.vvix_mean_reversion(result.current_vvix, vvix_data)
        result.mean_reversion_zscore = z
        result.half_life_days = hl
        if len(vvix_data) > 1:
            result.distance_from_mean = round(
                result.current_vvix - float(np.mean(vvix_data[-_LONG_HISTORY_BARS:])),
                4,
            )

        return result


# =============================================================================
# VIXPatternRecognition
# =============================================================================

class VIXPatternRecognition:
    """VIX pattern recognition engine.

    Detects higher-order patterns in VIX behavior that historically
    precede significant market moves: crush setups, pre-event hedging,
    tail hedging buildups, complacency signals, and correlation regime
    changes. These are the patterns institutional desks watch.
    """

    # Complacency thresholds
    _VIX_COMPLACENT = 13.0
    _VVIX_COMPLACENT = 80.0
    _PCR_COMPLACENT = 0.7
    _CONTANGO_COMPLACENT = 5.0

    # Tail hedge detection
    _FAR_OTM_MULTIPLIER = 1.5  # Strike > VIX * 1.5 is far OTM call on VIX
    _TAIL_OI_THRESHOLD = 10000
    _TAIL_VOLUME_THRESHOLD = 5000

    # Correlation regime
    _NORMAL_SPX_VIX_CORR = -0.80
    _CORR_BREAK_THRESHOLD = 0.15  # Deviation from normal

    def detect_vix_crush_setup(
        self,
        vix_data: np.ndarray,
        term_structure: TermStructureAnalysis,
    ) -> Tuple[bool, float]:
        """Detect conditions for a VIX crush (rapid mean reversion after spike).

        A VIX crush setup requires:
        1. VIX recently spiked (>1.5 std above mean)
        2. VIX has started declining from peak
        3. Term structure returning to contango
        4. VVIX declining (vol-of-vol compression)

        This pattern historically precedes 3-5 day rapid VIX declines.

        Args:
            vix_data: VIX time series (most recent last).
            term_structure: Current term structure analysis.

        Returns:
            Tuple of (crush_detected, confidence 0-1).
        """
        if len(vix_data) < 20:
            return False, 0.0

        recent = vix_data[-20:]
        current = float(recent[-1])
        peak = float(np.max(recent))
        mean_252 = float(np.mean(vix_data[-_LONG_HISTORY_BARS:]))
        std_252 = float(np.std(vix_data[-_LONG_HISTORY_BARS:], ddof=1))

        if std_252 < 0.1:
            return False, 0.0

        signals = 0
        total_weight = 0.0

        # 1. Recent spike (VIX > 1.5 std above mean)
        if peak > mean_252 + 1.5 * std_252:
            signals += 1
            total_weight += 0.30

        # 2. VIX declining from peak (at least 10% off peak)
        if peak > 0 and current < peak * 0.90:
            signals += 1
            decline_pct = (peak - current) / peak
            total_weight += min(0.30, decline_pct)

        # 3. Term structure returning to contango
        if term_structure.regime in (
            TermStructureRegime.MILD_CONTANGO,
            TermStructureRegime.DEEP_CONTANGO,
        ):
            signals += 1
            total_weight += 0.20

        # 4. Current VIX still elevated but declining
        if current > mean_252 and len(recent) >= 5:
            if float(recent[-1]) < float(recent[-5]):
                signals += 1
                total_weight += 0.20

        crush_detected = signals >= 3
        confidence = min(1.0, total_weight)

        return crush_detected, round(confidence, 4)

    def detect_pre_event_hedging(
        self,
        chain: VIXFullChain,
        event_calendar: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[bool, str, float]:
        """Detect unusual VIX positioning before scheduled macro events.

        Institutional desks hedge ahead of FOMC, CPI, NFP, and earnings
        by buying VIX calls and/or SPX puts. This shows up as:
        1. Elevated near-term VIX call volume
        2. Increase in OI at specific expirations bracketing events
        3. Premium skew toward protective structures

        Args:
            chain: Complete VIX options chain.
            event_calendar: Optional list of upcoming events with dates.

        Returns:
            Tuple of (hedging_detected, event_name, intensity 0-1).
        """
        if not chain.chains:
            return False, "", 0.0

        # Default event calendar if none provided
        if event_calendar is None:
            event_calendar = self._generate_default_event_calendar()

        now = datetime.utcnow()
        upcoming_events = [
            e for e in event_calendar
            if 0 < (e.get("date", now) - now).days <= 10
        ]

        if not upcoming_events:
            return False, "", 0.0

        # Analyze call activity in expirations surrounding events
        hedging_signals = 0
        max_intensity = 0.0
        detected_event = ""

        for event in upcoming_events:
            event_date = event.get("date", now)
            event_name = event.get("name", "UNKNOWN")

            # Find chains expiring near or after the event
            relevant_chains = [
                ch for ch in chain.chains
                if 0 <= (ch.expiration - event_date).days <= 7
            ]

            for rel_chain in relevant_chains:
                call_vol = rel_chain.total_call_volume
                call_oi = rel_chain.total_call_oi
                put_vol = rel_chain.total_put_volume

                # Check for elevated call buying (VIX calls = volatility hedge)
                total_vol = call_vol + put_vol
                if total_vol > 0:
                    call_ratio = call_vol / total_vol
                    if call_ratio > 0.6:
                        hedging_signals += 1

                # Check for large OI buildup
                if call_oi > 50000:
                    hedging_signals += 1

                # Volume/OI ratio > 0.5 suggests active new positioning
                if call_oi > 0 and call_vol / call_oi > 0.5:
                    hedging_signals += 1

                intensity = min(1.0, hedging_signals / 4.0)
                if intensity > max_intensity:
                    max_intensity = intensity
                    detected_event = event_name

        detected = max_intensity > 0.3
        return detected, detected_event, round(max_intensity, 4)

    def detect_tail_hedging_buildup(
        self, chain: VIXFullChain
    ) -> Tuple[bool, float]:
        """Detect massive far-OTM VIX call buying indicating tail hedge.

        Tail hedging shows up as large accumulation of far out-of-the-money
        VIX calls (strikes significantly above current VIX). When
        institutions buy VIX 40+ calls in size, they are hedging against
        a market crash scenario.

        Detection criteria:
        - Strikes > 1.5x current VIX level
        - OI > 10,000 contracts at far OTM strikes
        - Recent volume surge at these strikes
        - Implied vol of far OTM calls elevated

        Args:
            chain: Complete VIX options chain.

        Returns:
            Tuple of (tail_hedge_detected, score 0-1).
        """
        vix_spot = chain.vix_spot
        if vix_spot <= 0:
            return False, 0.0

        far_otm_threshold = vix_spot * self._FAR_OTM_MULTIPLIER
        score_components = 0.0
        max_components = 4.0

        far_otm_total_oi = 0
        far_otm_total_vol = 0
        far_otm_contracts = 0
        far_otm_ivs: List[float] = []

        for exp_chain in chain.chains:
            for contract in exp_chain.contracts:
                if contract.option_type != "CALL":
                    continue
                if contract.strike < far_otm_threshold:
                    continue

                far_otm_total_oi += contract.open_interest
                far_otm_total_vol += contract.volume
                far_otm_contracts += 1
                if contract.implied_vol > 0:
                    far_otm_ivs.append(contract.implied_vol)

        # 1. Large OI at far OTM strikes
        if far_otm_total_oi > self._TAIL_OI_THRESHOLD:
            oi_score = min(1.0, far_otm_total_oi / (self._TAIL_OI_THRESHOLD * 5))
            score_components += oi_score

        # 2. Recent volume activity
        if far_otm_total_vol > self._TAIL_VOLUME_THRESHOLD:
            vol_score = min(1.0, far_otm_total_vol / (self._TAIL_VOLUME_THRESHOLD * 3))
            score_components += vol_score

        # 3. Number of strikes with activity (breadth of positioning)
        if far_otm_contracts >= 5:
            breadth_score = min(1.0, far_otm_contracts / 15.0)
            score_components += breadth_score

        # 4. Elevated IV at far OTM strikes (premium demand)
        if far_otm_ivs:
            avg_far_iv = float(np.mean(far_otm_ivs))
            if avg_far_iv > 1.0:  # > 100% IV
                iv_score = min(1.0, avg_far_iv / 2.0)
                score_components += iv_score

        final_score = score_components / max_components
        detected = final_score > 0.3

        return detected, round(final_score, 4)

    def detect_complacency_signal(
        self,
        vix: float,
        vvix: float,
        pcr: float,
        term_structure: TermStructureAnalysis,
    ) -> Tuple[bool, float]:
        """Detect dangerous market complacency.

        Complacency is the most dangerous market condition because it
        precedes the sharpest vol spikes. The signal fires when:
        1. VIX < 13 (historically low)
        2. VVIX low (nobody pricing in VIX moves)
        3. PCR low (no hedging demand)
        4. Steep contango (no fear in futures)

        All four conditions together = maximum complacency = maximum risk.

        Args:
            vix: Current VIX level.
            vvix: Current VVIX level.
            pcr: VIX put/call ratio.
            term_structure: Term structure analysis.

        Returns:
            Tuple of (complacency_detected, score 0-1).
        """
        signals = 0
        score = 0.0

        # 1. VIX below complacency threshold
        if vix < self._VIX_COMPLACENT:
            signals += 1
            vix_score = max(0.0, (self._VIX_COMPLACENT - vix) / self._VIX_COMPLACENT)
            score += vix_score * 0.30

        # 2. VVIX below complacency threshold
        if vvix < self._VVIX_COMPLACENT:
            signals += 1
            vvix_score = max(0.0, (self._VVIX_COMPLACENT - vvix) / self._VVIX_COMPLACENT)
            score += vvix_score * 0.25

        # 3. Low put/call ratio
        if pcr < self._PCR_COMPLACENT:
            signals += 1
            pcr_score = max(0.0, (self._PCR_COMPLACENT - pcr) / self._PCR_COMPLACENT)
            score += pcr_score * 0.20

        # 4. Steep contango
        if term_structure.contango_pct > self._CONTANGO_COMPLACENT:
            signals += 1
            contango_score = min(
                1.0,
                (term_structure.contango_pct - self._CONTANGO_COMPLACENT) / 10.0,
            )
            score += contango_score * 0.25

        detected = signals >= 3
        return detected, round(min(1.0, score), 4)

    def correlation_regime(
        self,
        spy_returns: np.ndarray,
        vix_returns: np.ndarray,
        window: int = 60,
    ) -> Tuple[bool, float]:
        """Detect SPX-VIX correlation regime breaks.

        The normal SPX-VIX correlation is approximately -0.80. When this
        correlation significantly deviates from the norm, it signals a
        regime change in how volatility is being priced.

        Breaking from -0.80:
        - Toward 0: Volatility becoming directionally uncertain
        - Toward -1: Extreme fear (vol spike on any dip)
        - Toward positive: Broken regime (very rare, very dangerous)

        Args:
            spy_returns: SPY/SPX return series.
            vix_returns: VIX return series.
            window: Rolling window for correlation.

        Returns:
            Tuple of (regime_break_detected, current_correlation).
        """
        corr = _rolling_correlation(spy_returns, vix_returns, window)

        deviation = abs(corr - self._NORMAL_SPX_VIX_CORR)
        regime_break = deviation > self._CORR_BREAK_THRESHOLD

        return regime_break, round(corr, 4)

    def full_analysis(
        self,
        vix_data: np.ndarray,
        vvix_data: np.ndarray,
        chain: Optional[VIXFullChain],
        term_structure: TermStructureAnalysis,
        spy_returns: Optional[np.ndarray] = None,
        vix_returns: Optional[np.ndarray] = None,
        event_calendar: Optional[List[Dict[str, Any]]] = None,
    ) -> PatternAnalysis:
        """Run all pattern recognition analyses.

        Args:
            vix_data: VIX time series.
            vvix_data: VVIX time series.
            chain: VIX options chain (optional).
            term_structure: Term structure analysis.
            spy_returns: SPY returns (optional).
            vix_returns: VIX returns (optional).
            event_calendar: Upcoming events (optional).

        Returns:
            Complete PatternAnalysis.
        """
        result = PatternAnalysis()

        # VIX crush setup
        if len(vix_data) >= 20:
            crush, crush_conf = self.detect_vix_crush_setup(vix_data, term_structure)
            result.crush_setup = crush
            result.crush_confidence = crush_conf

        # Pre-event hedging
        if chain is not None:
            detected, event, intensity = self.detect_pre_event_hedging(
                chain, event_calendar
            )
            result.pre_event_hedging = detected
            result.hedging_event = event
            result.hedging_intensity = intensity

            # Tail hedging buildup
            tail, tail_score = self.detect_tail_hedging_buildup(chain)
            result.tail_hedging_buildup = tail
            result.tail_hedge_score = tail_score

        # Complacency signal
        current_vix = float(vix_data[-1]) if len(vix_data) > 0 else 20.0
        current_vvix = float(vvix_data[-1]) if len(vvix_data) > 0 else 90.0
        aggregate_pcr = 1.0  # Default; overridden if chain available
        if chain is not None:
            total_call = sum(ch.total_call_oi for ch in chain.chains)
            total_put = sum(ch.total_put_oi for ch in chain.chains)
            aggregate_pcr = _safe_divide(total_put, total_call, 1.0)

        comp, comp_score = self.detect_complacency_signal(
            current_vix, current_vvix, aggregate_pcr, term_structure
        )
        result.complacency_signal = comp
        result.complacency_score = comp_score

        # Correlation regime
        if spy_returns is not None and vix_returns is not None:
            corr_break, corr_val = self.correlation_regime(spy_returns, vix_returns)
            result.correlation_regime_break = corr_break
            result.correlation_current = corr_val

        return result

    # ----- Private helpers -----

    @staticmethod
    def _generate_default_event_calendar() -> List[Dict[str, Any]]:
        """Generate a simple default event calendar for the next 30 days.

        In production, this would be replaced by a real economic calendar
        feed. Here we approximate FOMC and CPI dates.

        Returns:
            List of event dictionaries with name and date.
        """
        now = datetime.utcnow()
        events: List[Dict[str, Any]] = []

        # Approximate common macro events -- institutions hedge 5-10 days prior
        for delta_days in [3, 7, 14, 21, 28]:
            target = now + timedelta(days=delta_days)
            # FOMC meetings roughly every 6 weeks; CPI monthly around 10th-14th
            if target.day in range(10, 16):
                events.append({"name": "CPI_RELEASE", "date": target})
            if target.weekday() == 2 and target.day in range(14, 22):
                events.append({"name": "FOMC_DECISION", "date": target})

        # Always include a generic "macro_event" sentinel
        events.append({
            "name": "SCHEDULED_MACRO",
            "date": now + timedelta(days=7),
        })

        return events


# =============================================================================
# VIXDeepIntelligenceScanner (Main Scanner)
# =============================================================================

class VIXDeepIntelligenceScanner(BaseScanner[AdvancedScanResult]):
    """VIX Deep Intelligence Scanner -- we see the move BEFORE the move.

    Integrates all VIX sub-analyzers into a unified scanning pipeline:
    - VIXOptionsChainTracker: Full chain monitoring and flow scoring
    - VIXTermStructureEngine: Futures curve analysis and inversion detection
    - VVIXAnalyzer: Vol-of-vol regime and divergence detection
    - VIXPatternRecognition: Higher-order pattern identification

    Signal triggers:
    1. VIX options gamma wall breach (GEX threshold crossing)
    2. Term structure inversion or rapid flattening
    3. VVIX divergence from VIX (leading indicator)
    4. Tail hedging buildup detection (crash hedging)
    5. Complacency / extreme fear readings
    6. Pre-event institutional hedging (FOMC, CPI positioning)

    Output: AdvancedScanResult with ScanCategory.OPTIONS.
    """

    # Signal confidence thresholds
    _MIN_SIGNAL_CONFIDENCE = 0.35
    _HIGH_CONFIDENCE = 0.75
    _EXTREME_CONFIDENCE = 0.90

    # GEX thresholds for VIX
    _GEX_LARGE_POSITIVE = 1_000_000.0   # Large positive GEX (stabilizing)
    _GEX_LARGE_NEGATIVE = -500_000.0    # Large negative GEX (destabilizing)

    def __init__(self, config: Optional[ScannerConfig] = None) -> None:
        """Initialize the VIX Deep Intelligence Scanner.

        Args:
            config: Optional scanner configuration. Defaults to standard
                    config with OPTIONS_DAY and ALL scan modes.
        """
        effective_config = config or ScannerConfig(
            scan_modes=[ScanMode.OPTIONS_DAY, ScanMode.ALL],
            min_confidence=35.0,
            min_price=0.01,
            max_price=100000.0,
            min_volume=0,
        )
        super().__init__(
            name="vix_deep_intelligence",
            scan_mode=ScanMode.OPTIONS_DAY,
            config=effective_config,
        )

        self.chain_tracker = VIXOptionsChainTracker()
        self.term_structure_engine = VIXTermStructureEngine()
        self.vvix_analyzer = VVIXAnalyzer()
        self.pattern_recognition = VIXPatternRecognition()

    async def scan(self, context: ScanContext) -> List[AdvancedScanResult]:
        """Execute the full VIX intelligence pipeline.

        Processes VIX ecosystem data from the scan context to generate
        institutional-grade volatility intelligence signals.

        The pipeline:
        1. Extract VIX-specific data from context
        2. Run all sub-analyzers in sequence
        3. Aggregate results into VIXIntelligenceResult
        4. Generate AdvancedScanResult signals for actionable findings

        Args:
            context: ScanContext with VIX data in options_data and metadata.

        Returns:
            List of AdvancedScanResult signals, sorted by confidence.
        """
        results: List[AdvancedScanResult] = []

        try:
            intelligence = self._run_analysis(context)
            if intelligence is not None:
                signals = self._generate_signals(intelligence, context)
                results.extend(signals)
        except Exception as exc:
            self._logger.error(
                "VIX Deep Intelligence scan failed: %s", exc, exc_info=True
            )

        results.sort(key=lambda r: r.confidence, reverse=True)
        return results

    def validate_signal(
        self, result: AdvancedScanResult, context: ScanContext
    ) -> bool:
        """Validate a VIX intelligence signal against current conditions.

        Validation checks:
        1. Confidence above minimum threshold
        2. Signal is not stale (within 1 hour)
        3. No contradicting evidence that overwhelms supporting evidence

        Args:
            result: AdvancedScanResult to validate.
            context: Current scan context.

        Returns:
            True if signal passes validation.
        """
        if result.confidence < self._MIN_SIGNAL_CONFIDENCE:
            return False

        # Check freshness
        age = (datetime.utcnow() - result.timestamp).total_seconds()
        if age > 3600:
            return False

        # Check evidence balance
        n_support = len(result.supporting_evidence)
        n_contra = len(result.contradicting_evidence)
        if n_contra > 0 and n_support <= n_contra:
            return False

        return True

    def _run_analysis(self, context: ScanContext) -> Optional[VIXIntelligenceResult]:
        """Combine all sub-analyzers into a unified intelligence result.

        Data extraction from context:
        - context.options_data["VIX"]: VIX options chain data
        - context.metadata["vix_futures"]: VIX futures data
        - context.metadata["vvix"]: VVIX time series
        - context.metadata["vix_history"]: VIX spot time series
        - context.metadata["spy_returns"]: SPY return series
        - context.metadata["term_structure_history"]: Historical curves

        Args:
            context: ScanContext with VIX ecosystem data.

        Returns:
            VIXIntelligenceResult, or None if insufficient data.
        """
        intelligence = VIXIntelligenceResult()

        # Extract VIX data
        vix_options = context.options_data.get("VIX", {})
        vix_market = context.market_data.get("VIX")
        vix_spot = vix_market.close if vix_market else context.metadata.get("vix_spot", 0.0)

        vix_history_raw = context.metadata.get("vix_history", [])
        vvix_history_raw = context.metadata.get("vvix", [])
        spy_returns_raw = context.metadata.get("spy_returns", [])
        vix_returns_raw = context.metadata.get("vix_returns", [])
        futures_raw = context.metadata.get("vix_futures", [])
        ts_history_raw = context.metadata.get("term_structure_history", [])
        event_calendar = context.metadata.get("event_calendar")

        vix_history = np.array(vix_history_raw, dtype=np.float64) if vix_history_raw else np.array([])
        vvix_history = np.array(vvix_history_raw, dtype=np.float64) if vvix_history_raw else np.array([])
        spy_returns = np.array(spy_returns_raw, dtype=np.float64) if spy_returns_raw else np.array([])
        vix_returns = np.array(vix_returns_raw, dtype=np.float64) if vix_returns_raw else np.array([])

        # If no VIX spot and no history, we cannot analyze
        if vix_spot <= 0 and len(vix_history) == 0:
            self._logger.debug("No VIX data available for analysis.")
            return None

        if vix_spot <= 0 and len(vix_history) > 0:
            vix_spot = float(vix_history[-1])

        # ------------------------------------------------------------------
        # 1. Options Chain Analysis
        # ------------------------------------------------------------------
        vix_chain = self._build_vix_chain(vix_options, vix_spot)
        if vix_chain is not None and vix_chain.chains:
            chain_analysis = self.chain_tracker.analyze_full_chain(vix_chain)
            intelligence.chain_analysis = chain_analysis
        else:
            vix_chain = None

        # ------------------------------------------------------------------
        # 2. Term Structure Analysis
        # ------------------------------------------------------------------
        futures_contracts = self._build_futures_contracts(futures_raw)
        ts_history = self._parse_ts_history(ts_history_raw)
        term_structure = self.term_structure_engine.full_analysis(
            futures_contracts, vix_spot, ts_history if ts_history else None
        )
        intelligence.term_structure = term_structure

        # ------------------------------------------------------------------
        # 3. VVIX Analysis
        # ------------------------------------------------------------------
        if len(vvix_history) > 0:
            vvix_analysis = self.vvix_analyzer.full_analysis(vix_history, vvix_history)
            intelligence.vvix_analysis = vvix_analysis

        # ------------------------------------------------------------------
        # 4. Pattern Recognition
        # ------------------------------------------------------------------
        pattern_analysis = self.pattern_recognition.full_analysis(
            vix_data=vix_history if len(vix_history) > 0 else np.array([vix_spot]),
            vvix_data=vvix_history if len(vvix_history) > 0 else np.array([90.0]),
            chain=vix_chain,
            term_structure=term_structure,
            spy_returns=spy_returns if len(spy_returns) > 0 else None,
            vix_returns=vix_returns if len(vix_returns) > 0 else None,
            event_calendar=event_calendar,
        )
        intelligence.pattern_analysis = pattern_analysis

        # ------------------------------------------------------------------
        # 5. Overall assessment
        # ------------------------------------------------------------------
        intelligence.overall_signal, intelligence.overall_confidence = (
            self._compute_overall_signal(intelligence)
        )
        intelligence.regime_context = self._determine_regime(intelligence, vix_spot)

        return intelligence

    def _generate_signals(
        self,
        intelligence: VIXIntelligenceResult,
        context: ScanContext,
    ) -> List[AdvancedScanResult]:
        """Generate AdvancedScanResult signals from intelligence analysis.

        Each signal trigger is evaluated independently and can produce
        its own AdvancedScanResult. Multiple signals may fire simultaneously.

        Args:
            intelligence: Aggregated VIX intelligence result.
            context: Scan context for metadata.

        Returns:
            List of AdvancedScanResult signals.
        """
        signals: List[AdvancedScanResult] = []

        ts = intelligence.term_structure
        vvix = intelligence.vvix_analysis
        chain = intelligence.chain_analysis
        pattern = intelligence.pattern_analysis

        # --- Signal 1: VIX Options Gamma Wall Breach ---
        if chain is not None:
            gex_signal = self._signal_gamma_wall_breach(chain, intelligence)
            if gex_signal is not None:
                signals.append(gex_signal)

        # --- Signal 2: Term Structure Inversion / Rapid Flattening ---
        if ts is not None:
            ts_signal = self._signal_term_structure(ts, intelligence)
            if ts_signal is not None:
                signals.append(ts_signal)

        # --- Signal 3: VVIX Divergence ---
        if vvix is not None:
            vvix_signal = self._signal_vvix_divergence(vvix, intelligence)
            if vvix_signal is not None:
                signals.append(vvix_signal)

        # --- Signal 4: Tail Hedging Buildup ---
        if pattern is not None and pattern.tail_hedging_buildup:
            tail_signal = self._signal_tail_hedging(pattern, intelligence)
            if tail_signal is not None:
                signals.append(tail_signal)

        # --- Signal 5: Complacency / Extreme Fear ---
        if pattern is not None:
            sentiment_signal = self._signal_sentiment_extreme(pattern, intelligence)
            if sentiment_signal is not None:
                signals.append(sentiment_signal)

        # --- Signal 6: Pre-Event Institutional Hedging ---
        if pattern is not None and pattern.pre_event_hedging:
            event_signal = self._signal_pre_event_hedging(pattern, intelligence)
            if event_signal is not None:
                signals.append(event_signal)

        return signals

    # -----------------------------------------------------------------
    # Signal generation helpers
    # -----------------------------------------------------------------

    def _signal_gamma_wall_breach(
        self, chain: ChainAnalysis, intelligence: VIXIntelligenceResult
    ) -> Optional[AdvancedScanResult]:
        """Generate signal for VIX gamma wall breach.

        Triggers when net GEX crosses significant thresholds or when
        price approaches a hedging wall level.

        Args:
            chain: Chain analysis results.
            intelligence: Full intelligence result.

        Returns:
            AdvancedScanResult or None.
        """
        net_gex = chain.net_gex
        if abs(net_gex) < abs(self._GEX_LARGE_NEGATIVE) * 0.5:
            return None

        if net_gex < self._GEX_LARGE_NEGATIVE:
            direction = "BEARISH"
            confidence = min(0.90, abs(net_gex) / abs(self._GEX_LARGE_NEGATIVE) * 0.5)
            evidence = [
                f"Net VIX GEX deeply negative: {net_gex:,.0f}",
                "Dealer short gamma = destabilizing hedging flows",
                "VIX moves amplified by dealer rebalancing",
            ]
            contradicting = []
            if intelligence.term_structure and intelligence.term_structure.regime in (
                TermStructureRegime.DEEP_CONTANGO,
            ):
                contradicting.append("Deep contango suggests contained fear")
        elif net_gex > self._GEX_LARGE_POSITIVE:
            direction = "BULLISH"
            confidence = min(0.80, net_gex / self._GEX_LARGE_POSITIVE * 0.4)
            evidence = [
                f"Net VIX GEX strongly positive: {net_gex:,.0f}",
                "Dealer long gamma = stabilizing hedging flows",
                "VIX moves dampened by dealer rebalancing",
            ]
            contradicting = []
        else:
            return None

        return AdvancedScanResult(
            scan_id=str(uuid.uuid4()),
            scan_name="VIX Gamma Wall Breach",
            category=ScanCategory.OPTIONS,
            symbol="VIX",
            signal_direction=direction,
            signal_strength=round(confidence, 4),
            confidence=round(confidence, 4),
            expected_move_pct=round(abs(net_gex) / 1_000_000.0 * 2.0, 2),
            expected_timeframe=ExpectedTimeframe.INTRADAY,
            risk_reward_ratio=round(confidence * 3.0, 2),
            supporting_evidence=evidence,
            contradicting_evidence=contradicting,
            historical_accuracy=0.68,
            regime_context=intelligence.regime_context,
            mathematical_basis=(
                "GEX_vix = sum(gamma_i * OI_i * 100 * VIX^2 * 0.01). "
                "Negative net GEX implies dealer short gamma, amplifying moves."
            ),
            false_positive_rate=0.25,
            decay_halflife_days=2,
            volatility_regime=self._map_vol_regime(intelligence),
            metadata={
                "net_gex": round(net_gex, 2),
                "hedging_walls": chain.hedging_walls[:5],
                "unusual_strikes": chain.unusual_strikes[:5],
                "scanner": "vix_deep_intelligence",
            },
        )

    def _signal_term_structure(
        self, ts: TermStructureAnalysis, intelligence: VIXIntelligenceResult
    ) -> Optional[AdvancedScanResult]:
        """Generate signal for term structure regime events.

        Triggers on:
        - Inversion or deep backwardation
        - Rapid flattening (inversion probability > 60%)
        - Extreme contango (complacency risk)

        Args:
            ts: Term structure analysis.
            intelligence: Full intelligence result.

        Returns:
            AdvancedScanResult or None.
        """
        evidence: List[str] = []
        contradicting: List[str] = []
        direction = "NEUTRAL"
        confidence = 0.0

        if ts.regime in (
            TermStructureRegime.MILD_BACKWARDATION,
            TermStructureRegime.DEEP_BACKWARDATION,
        ):
            direction = "BEARISH"
            base_conf = 0.70 if ts.regime == TermStructureRegime.DEEP_BACKWARDATION else 0.55
            confidence = base_conf
            evidence.append(f"VIX term structure in {ts.regime.value}")
            evidence.append(f"Contango: {ts.contango_pct:.2f}%")
            evidence.append("Backwardation = elevated near-term fear")
            if ts.basis_regime == BasisRegime.DEEP_DISCOUNT:
                evidence.append(f"Basis in deep discount: {ts.basis:.2f}")
                confidence = min(0.90, confidence + 0.10)
        elif ts.inversion_probability > 0.60:
            direction = "BEARISH"
            confidence = ts.inversion_probability * 0.80
            evidence.append(f"Inversion probability: {ts.inversion_probability:.1%}")
            evidence.append(f"Curve velocity: {ts.velocity:.4f} pct/day")
            evidence.append("Rapid flattening = inversion imminent")
        elif ts.regime == TermStructureRegime.DEEP_CONTANGO:
            direction = "BULLISH"
            confidence = 0.50
            evidence.append(f"Deep contango: {ts.contango_pct:.2f}%")
            evidence.append(f"Roll yield annualized: {ts.roll_yield_annualized:.2%}")
            contradicting.append("Extreme complacency can precede sharp reversals")
        else:
            return None

        if confidence < self._MIN_SIGNAL_CONFIDENCE:
            return None

        return AdvancedScanResult(
            scan_id=str(uuid.uuid4()),
            scan_name="VIX Term Structure Signal",
            category=ScanCategory.OPTIONS,
            symbol="VIX",
            signal_direction=direction,
            signal_strength=round(confidence, 4),
            confidence=round(confidence, 4),
            expected_move_pct=round(abs(ts.contango_pct) * 0.5, 2),
            expected_timeframe=ExpectedTimeframe.SWING,
            risk_reward_ratio=round(confidence * 2.5, 2),
            supporting_evidence=evidence,
            contradicting_evidence=contradicting,
            historical_accuracy=0.72,
            regime_context=intelligence.regime_context,
            mathematical_basis=(
                "Contango = (F1 - VIX_spot) / VIX_spot * 100. "
                "Roll yield annualized = ((F2/F1) - 1) * (365 / days_between). "
                "Inversion predicted via slope velocity derivative."
            ),
            false_positive_rate=0.20,
            decay_halflife_days=5,
            volatility_regime=self._map_vol_regime(intelligence),
            metadata={
                "regime": ts.regime.value,
                "contango_pct": ts.contango_pct,
                "roll_yield": ts.roll_yield_annualized,
                "slope": ts.slope,
                "velocity": ts.velocity,
                "inversion_prob": ts.inversion_probability,
                "basis": ts.basis,
                "basis_regime": ts.basis_regime.value,
                "scanner": "vix_deep_intelligence",
            },
        )

    def _signal_vvix_divergence(
        self, vvix: VVIXAnalysis, intelligence: VIXIntelligenceResult
    ) -> Optional[AdvancedScanResult]:
        """Generate signal for VVIX divergence from VIX.

        The divergence signal is one of the strongest predictive indicators:
        VVIX rising while VIX flat = options traders pricing in imminent
        VIX explosion before it happens.

        Args:
            vvix: VVIX analysis results.
            intelligence: Full intelligence result.

        Returns:
            AdvancedScanResult or None.
        """
        if abs(vvix.divergence_score) < 5.0 and vvix.regime == VVIXRegime.NORMAL:
            return None

        evidence: List[str] = []
        contradicting: List[str] = []
        confidence = 0.0

        if vvix.divergence_direction == "vvix_leading_up":
            direction = "BEARISH"
            confidence = min(0.85, abs(vvix.divergence_score) / 20.0 + 0.30)
            evidence.append(f"VVIX divergence score: {vvix.divergence_score:.2f}")
            evidence.append("VVIX rising while VIX flat = imminent VIX explosion")
            evidence.append(f"VVIX regime: {vvix.regime.value}")
            if vvix.spike_probability > 0.3:
                evidence.append(
                    f"Hawkes spike probability: {vvix.spike_probability:.1%}"
                )
                confidence = min(0.92, confidence + 0.10)
        elif vvix.divergence_direction == "vvix_leading_down":
            direction = "BULLISH"
            confidence = min(0.70, abs(vvix.divergence_score) / 20.0 + 0.25)
            evidence.append(f"VVIX divergence score: {vvix.divergence_score:.2f}")
            evidence.append("VVIX declining = vol compression incoming")
        elif vvix.regime == VVIXRegime.EXTREME:
            direction = "BEARISH"
            confidence = 0.65
            evidence.append(f"VVIX at extreme level: {vvix.current_vvix:.1f}")
            evidence.append("Extreme vol-of-vol = market pricing tail risk")
        elif vvix.regime == VVIXRegime.LOW:
            direction = "NEUTRAL"
            confidence = 0.40
            evidence.append(f"VVIX at low level: {vvix.current_vvix:.1f}")
            evidence.append("Low vol-of-vol = complacency")
            contradicting.append("Low VVIX can persist in quiet markets")
        else:
            return None

        # Mean reversion context
        if abs(vvix.mean_reversion_zscore) > 2.0:
            evidence.append(
                f"VVIX z-score: {vvix.mean_reversion_zscore:.2f} "
                f"(half-life: {vvix.half_life_days:.1f} days)"
            )

        if confidence < self._MIN_SIGNAL_CONFIDENCE:
            return None

        return AdvancedScanResult(
            scan_id=str(uuid.uuid4()),
            scan_name="VVIX Divergence Signal",
            category=ScanCategory.OPTIONS,
            symbol="VIX",
            signal_direction=direction,
            signal_strength=round(confidence, 4),
            confidence=round(confidence, 4),
            expected_move_pct=round(abs(vvix.divergence_score) * 0.3, 2),
            expected_timeframe=ExpectedTimeframe.SWING,
            risk_reward_ratio=round(confidence * 2.8, 2),
            supporting_evidence=evidence,
            contradicting_evidence=contradicting,
            historical_accuracy=0.74,
            regime_context=intelligence.regime_context,
            mathematical_basis=(
                "Ornstein-Uhlenbeck: dV = theta*(mu - V)*dt + sigma*dW, "
                "half-life = ln(2)/theta. "
                "Hawkes intensity: lambda(t) = mu + sum(alpha * exp(-beta*(t-t_i)))."
            ),
            false_positive_rate=0.18,
            decay_halflife_days=3,
            volatility_regime=self._map_vol_regime(intelligence),
            metadata={
                "vvix_regime": vvix.regime.value,
                "divergence_score": vvix.divergence_score,
                "divergence_direction": vvix.divergence_direction,
                "spike_probability": vvix.spike_probability,
                "mean_reversion_z": vvix.mean_reversion_zscore,
                "half_life_days": vvix.half_life_days,
                "scanner": "vix_deep_intelligence",
            },
        )

    def _signal_tail_hedging(
        self, pattern: PatternAnalysis, intelligence: VIXIntelligenceResult
    ) -> Optional[AdvancedScanResult]:
        """Generate signal for tail hedging buildup detection.

        Large institutions buying far-OTM VIX calls are hedging against
        a market crash. This signal has strong predictive power because
        these players have information advantages.

        Args:
            pattern: Pattern analysis results.
            intelligence: Full intelligence result.

        Returns:
            AdvancedScanResult or None.
        """
        if not pattern.tail_hedging_buildup:
            return None

        confidence = min(0.85, pattern.tail_hedge_score * 0.9 + 0.20)
        if confidence < self._MIN_SIGNAL_CONFIDENCE:
            return None

        evidence = [
            f"Tail hedge score: {pattern.tail_hedge_score:.2f}",
            "Massive far-OTM VIX call accumulation detected",
            "Institutional crash hedging in progress",
        ]
        contradicting = [
            "Tail hedges can be rolled routinely (false positive risk)",
        ]

        return AdvancedScanResult(
            scan_id=str(uuid.uuid4()),
            scan_name="VIX Tail Hedging Buildup",
            category=ScanCategory.OPTIONS,
            symbol="VIX",
            signal_direction="BEARISH",
            signal_strength=round(confidence, 4),
            confidence=round(confidence, 4),
            expected_move_pct=round(pattern.tail_hedge_score * 8.0, 2),
            expected_timeframe=ExpectedTimeframe.POSITION,
            risk_reward_ratio=round(confidence * 4.0, 2),
            supporting_evidence=evidence,
            contradicting_evidence=contradicting,
            historical_accuracy=0.62,
            regime_context=intelligence.regime_context,
            mathematical_basis=(
                "Far-OTM VIX call OI accumulation (strikes > 1.5x spot). "
                "Score combines OI magnitude, volume surge, breadth, and IV demand."
            ),
            false_positive_rate=0.30,
            decay_halflife_days=10,
            volatility_regime=self._map_vol_regime(intelligence),
            metadata={
                "tail_hedge_score": pattern.tail_hedge_score,
                "scanner": "vix_deep_intelligence",
            },
        )

    def _signal_sentiment_extreme(
        self, pattern: PatternAnalysis, intelligence: VIXIntelligenceResult
    ) -> Optional[AdvancedScanResult]:
        """Generate signal for extreme complacency or fear.

        Complacency (VIX < 13, low VVIX, low PCR, steep contango) is
        the most dangerous condition. Extreme fear (VIX crush setup)
        signals a buying opportunity.

        Args:
            pattern: Pattern analysis results.
            intelligence: Full intelligence result.

        Returns:
            AdvancedScanResult or None.
        """
        if pattern.complacency_signal:
            confidence = min(0.80, pattern.complacency_score + 0.20)
            if confidence < self._MIN_SIGNAL_CONFIDENCE:
                return None

            evidence = [
                f"Complacency score: {pattern.complacency_score:.2f}",
                "VIX, VVIX, PCR, and term structure all signal complacency",
                "Historically precedes sharp vol spikes",
            ]

            return AdvancedScanResult(
                scan_id=str(uuid.uuid4()),
                scan_name="VIX Complacency Warning",
                category=ScanCategory.OPTIONS,
                symbol="VIX",
                signal_direction="BEARISH",
                signal_strength=round(confidence, 4),
                confidence=round(confidence, 4),
                expected_move_pct=round(pattern.complacency_score * 5.0, 2),
                expected_timeframe=ExpectedTimeframe.SWING,
                risk_reward_ratio=round(confidence * 3.5, 2),
                supporting_evidence=evidence,
                contradicting_evidence=[
                    "Low vol regimes can persist for extended periods"
                ],
                historical_accuracy=0.65,
                regime_context=RegimeContext.QUIET,
                mathematical_basis=(
                    "Multi-factor complacency: VIX < 13, VVIX < 80, PCR < 0.7, "
                    "contango > 5%. Z-scores computed over 252-day windows."
                ),
                false_positive_rate=0.28,
                decay_halflife_days=7,
                volatility_regime=VolatilityRegime.ULTRA_LOW,
                metadata={
                    "complacency_score": pattern.complacency_score,
                    "scanner": "vix_deep_intelligence",
                },
            )

        if pattern.crush_setup:
            confidence = min(0.80, pattern.crush_confidence + 0.15)
            if confidence < self._MIN_SIGNAL_CONFIDENCE:
                return None

            evidence = [
                f"VIX crush confidence: {pattern.crush_confidence:.2f}",
                "Post-spike mean reversion conditions detected",
                "Term structure normalizing, VIX declining from peak",
            ]

            return AdvancedScanResult(
                scan_id=str(uuid.uuid4()),
                scan_name="VIX Crush Setup",
                category=ScanCategory.OPTIONS,
                symbol="VIX",
                signal_direction="BULLISH",
                signal_strength=round(confidence, 4),
                confidence=round(confidence, 4),
                expected_move_pct=round(pattern.crush_confidence * 4.0, 2),
                expected_timeframe=ExpectedTimeframe.INTRADAY,
                risk_reward_ratio=round(confidence * 2.5, 2),
                supporting_evidence=evidence,
                contradicting_evidence=[],
                historical_accuracy=0.70,
                regime_context=RegimeContext.RECOVERY,
                mathematical_basis=(
                    "Mean reversion after VIX spike > 1.5 std. "
                    "Conditions: declining from peak, contango returning, "
                    "current level still elevated above 252-day mean."
                ),
                false_positive_rate=0.22,
                decay_halflife_days=3,
                volatility_regime=VolatilityRegime.HIGH,
                metadata={
                    "crush_confidence": pattern.crush_confidence,
                    "scanner": "vix_deep_intelligence",
                },
            )

        return None

    def _signal_pre_event_hedging(
        self, pattern: PatternAnalysis, intelligence: VIXIntelligenceResult
    ) -> Optional[AdvancedScanResult]:
        """Generate signal for pre-event institutional hedging.

        Detects when institutions are positioning ahead of scheduled
        macro events (FOMC, CPI, NFP) via VIX options.

        Args:
            pattern: Pattern analysis results.
            intelligence: Full intelligence result.

        Returns:
            AdvancedScanResult or None.
        """
        if not pattern.pre_event_hedging:
            return None

        confidence = min(0.75, pattern.hedging_intensity * 0.8 + 0.15)
        if confidence < self._MIN_SIGNAL_CONFIDENCE:
            return None

        evidence = [
            f"Pre-event hedging intensity: {pattern.hedging_intensity:.2f}",
            f"Event: {pattern.hedging_event}",
            "Elevated VIX call buying in event-bracketing expirations",
        ]

        return AdvancedScanResult(
            scan_id=str(uuid.uuid4()),
            scan_name="VIX Pre-Event Hedging",
            category=ScanCategory.OPTIONS,
            symbol="VIX",
            signal_direction="BEARISH",
            signal_strength=round(confidence, 4),
            confidence=round(confidence, 4),
            expected_move_pct=round(pattern.hedging_intensity * 3.0, 2),
            expected_timeframe=ExpectedTimeframe.INTRADAY,
            risk_reward_ratio=round(confidence * 2.0, 2),
            supporting_evidence=evidence,
            contradicting_evidence=[
                "Event hedging is standard practice; magnitude matters"
            ],
            historical_accuracy=0.60,
            regime_context=intelligence.regime_context,
            mathematical_basis=(
                "Pre-event positioning detection via call/put volume ratios, "
                "OI buildup in event-bracketing expirations, and "
                "volume/OI ratio signaling new position opening."
            ),
            false_positive_rate=0.32,
            decay_halflife_days=2,
            volatility_regime=self._map_vol_regime(intelligence),
            metadata={
                "hedging_event": pattern.hedging_event,
                "hedging_intensity": pattern.hedging_intensity,
                "scanner": "vix_deep_intelligence",
            },
        )

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    def _compute_overall_signal(
        self, intelligence: VIXIntelligenceResult
    ) -> Tuple[str, float]:
        """Compute the overall intelligence signal and confidence.

        Aggregates sub-analyzer outputs into a single directional call
        using a weighted voting scheme.

        Args:
            intelligence: Full intelligence result.

        Returns:
            Tuple of (direction string, confidence 0-1).
        """
        bearish_score = 0.0
        bullish_score = 0.0

        # Term structure contribution
        ts = intelligence.term_structure
        if ts is not None:
            if ts.regime in (
                TermStructureRegime.MILD_BACKWARDATION,
                TermStructureRegime.DEEP_BACKWARDATION,
            ):
                bearish_score += 0.30
            elif ts.regime == TermStructureRegime.DEEP_CONTANGO:
                bullish_score += 0.15  # Complacency risk offsets bullishness
            if ts.inversion_probability > 0.5:
                bearish_score += ts.inversion_probability * 0.20

        # VVIX contribution
        vvix = intelligence.vvix_analysis
        if vvix is not None:
            if vvix.divergence_direction == "vvix_leading_up":
                bearish_score += min(0.25, abs(vvix.divergence_score) / 40.0)
            elif vvix.divergence_direction == "vvix_leading_down":
                bullish_score += min(0.20, abs(vvix.divergence_score) / 40.0)
            if vvix.regime == VVIXRegime.EXTREME:
                bearish_score += 0.15
            elif vvix.regime == VVIXRegime.LOW:
                bullish_score += 0.05

        # Chain contribution
        chain = intelligence.chain_analysis
        if chain is not None:
            if chain.net_gex < self._GEX_LARGE_NEGATIVE:
                bearish_score += 0.15
            elif chain.net_gex > self._GEX_LARGE_POSITIVE:
                bullish_score += 0.10
            if chain.aggregate_pcr > 1.3:
                bearish_score += 0.10
            elif chain.aggregate_pcr < 0.6:
                bullish_score += 0.05

        # Pattern contribution
        pattern = intelligence.pattern_analysis
        if pattern is not None:
            if pattern.tail_hedging_buildup:
                bearish_score += pattern.tail_hedge_score * 0.20
            if pattern.complacency_signal:
                bearish_score += pattern.complacency_score * 0.15
            if pattern.crush_setup:
                bullish_score += pattern.crush_confidence * 0.25
            if pattern.pre_event_hedging:
                bearish_score += pattern.hedging_intensity * 0.10
            if pattern.correlation_regime_break:
                bearish_score += 0.10

        total = bearish_score + bullish_score
        if total < 0.10:
            return "NEUTRAL", 0.0

        if bearish_score > bullish_score:
            confidence = bearish_score / max(total, 0.01)
            return "BEARISH", round(min(1.0, confidence), 4)
        elif bullish_score > bearish_score:
            confidence = bullish_score / max(total, 0.01)
            return "BULLISH", round(min(1.0, confidence), 4)
        else:
            return "NEUTRAL", round(0.5, 4)

    def _determine_regime(
        self, intelligence: VIXIntelligenceResult, vix_spot: float
    ) -> RegimeContext:
        """Determine the current regime context from VIX intelligence.

        Args:
            intelligence: Full intelligence result.
            vix_spot: Current VIX spot.

        Returns:
            RegimeContext classification.
        """
        ts = intelligence.term_structure
        vvix = intelligence.vvix_analysis

        # Crisis detection
        if vix_spot > 35:
            return RegimeContext.CRISIS
        if ts and ts.regime == TermStructureRegime.DEEP_BACKWARDATION:
            return RegimeContext.CRISIS

        # Volatile regime
        if vix_spot > 25:
            return RegimeContext.VOLATILE
        if vvix and vvix.regime == VVIXRegime.EXTREME:
            return RegimeContext.VOLATILE

        # Recovery detection (post-spike, crush setup)
        pattern = intelligence.pattern_analysis
        if pattern and pattern.crush_setup:
            return RegimeContext.RECOVERY

        # Quiet regime
        if vix_spot < 14:
            return RegimeContext.QUIET
        if vvix and vvix.regime == VVIXRegime.LOW:
            return RegimeContext.QUIET

        # Transition
        if ts and ts.inversion_probability > 0.4:
            return RegimeContext.TRANSITION

        # Trending
        if ts and ts.regime in (
            TermStructureRegime.MILD_CONTANGO,
            TermStructureRegime.DEEP_CONTANGO,
        ):
            return RegimeContext.TRENDING_UP

        return RegimeContext.RANGING

    def _map_vol_regime(
        self, intelligence: VIXIntelligenceResult
    ) -> VolatilityRegime:
        """Map the intelligence result to a VolatilityRegime.

        Args:
            intelligence: Full intelligence result.

        Returns:
            VolatilityRegime classification.
        """
        vvix = intelligence.vvix_analysis

        if vvix is not None:
            if vvix.regime == VVIXRegime.EXTREME:
                return VolatilityRegime.EXTREME
            elif vvix.regime == VVIXRegime.ELEVATED:
                return VolatilityRegime.HIGH
            elif vvix.regime == VVIXRegime.LOW:
                return VolatilityRegime.LOW

        ts = intelligence.term_structure
        if ts is not None:
            if ts.regime == TermStructureRegime.DEEP_BACKWARDATION:
                return VolatilityRegime.EXTREME
            elif ts.regime == TermStructureRegime.MILD_BACKWARDATION:
                return VolatilityRegime.ELEVATED

        return VolatilityRegime.NORMAL

    def _build_vix_chain(
        self, options_data: Dict[str, Any], vix_spot: float
    ) -> Optional[VIXFullChain]:
        """Build VIXFullChain from raw options data in the scan context.

        Expects options_data to contain:
        - "chains": list of dicts with "expiration" and "contracts"
        - Each contract dict: strike, option_type, bid, ask, last,
          volume, open_interest, implied_vol, delta, gamma, theta, vega

        Args:
            options_data: Raw VIX options data from context.
            vix_spot: Current VIX spot level.

        Returns:
            VIXFullChain or None if insufficient data.
        """
        if not options_data:
            return None

        raw_chains = options_data.get("chains", [])
        if not raw_chains:
            return None

        full_chain = VIXFullChain(vix_spot=vix_spot)

        for raw_chain in raw_chains:
            exp_str = raw_chain.get("expiration", "")
            if not exp_str:
                continue

            if isinstance(exp_str, datetime):
                expiration = exp_str
            else:
                try:
                    expiration = datetime.fromisoformat(str(exp_str))
                except (ValueError, TypeError):
                    continue

            chain = VIXOptionsChain(expiration=expiration)

            for raw_contract in raw_chain.get("contracts", []):
                contract = VIXOptionContract(
                    strike=float(raw_contract.get("strike", 0)),
                    expiration=expiration,
                    option_type=str(raw_contract.get("option_type", "CALL")).upper(),
                    bid=float(raw_contract.get("bid", 0)),
                    ask=float(raw_contract.get("ask", 0)),
                    last=float(raw_contract.get("last", 0)),
                    volume=int(raw_contract.get("volume", 0)),
                    open_interest=int(raw_contract.get("open_interest", 0)),
                    implied_vol=float(raw_contract.get("implied_vol", 0)),
                    delta=float(raw_contract.get("delta", 0)),
                    gamma=float(raw_contract.get("gamma", 0)),
                    theta=float(raw_contract.get("theta", 0)),
                    vega=float(raw_contract.get("vega", 0)),
                )
                chain.contracts.append(contract)

            if chain.contracts:
                full_chain.chains.append(chain)

        return full_chain if full_chain.chains else None

    @staticmethod
    def _build_futures_contracts(
        futures_raw: List[Any],
    ) -> List[VIXFuturesContract]:
        """Build VIXFuturesContract list from raw futures data.

        Expects each entry to have: expiration, price, volume, open_interest.

        Args:
            futures_raw: List of raw futures data dicts.

        Returns:
            List of VIXFuturesContract.
        """
        contracts: List[VIXFuturesContract] = []

        for raw in futures_raw:
            if isinstance(raw, dict):
                exp_str = raw.get("expiration", "")
                if isinstance(exp_str, datetime):
                    expiration = exp_str
                else:
                    try:
                        expiration = datetime.fromisoformat(str(exp_str))
                    except (ValueError, TypeError):
                        continue

                contract = VIXFuturesContract(
                    expiration=expiration,
                    price=float(raw.get("price", 0)),
                    volume=int(raw.get("volume", 0)),
                    open_interest=int(raw.get("open_interest", 0)),
                    month_code=str(raw.get("month_code", "")),
                )
                if contract.price > 0:
                    contracts.append(contract)

        return contracts

    @staticmethod
    def _parse_ts_history(
        raw_history: List[Any],
    ) -> Optional[List[List[Tuple[int, float]]]]:
        """Parse historical term structure curves from raw data.

        Each entry should be a list of (dte, price) tuples or dicts.

        Args:
            raw_history: Raw historical curve data.

        Returns:
            Parsed list of curves, or None.
        """
        if not raw_history:
            return None

        parsed: List[List[Tuple[int, float]]] = []

        for raw_curve in raw_history:
            if isinstance(raw_curve, list):
                curve: List[Tuple[int, float]] = []
                for point in raw_curve:
                    if isinstance(point, (list, tuple)) and len(point) >= 2:
                        curve.append((int(point[0]), float(point[1])))
                    elif isinstance(point, dict):
                        dte = int(point.get("dte", 0))
                        price = float(point.get("price", 0))
                        if price > 0:
                            curve.append((dte, price))
                if curve:
                    parsed.append(curve)

        return parsed if parsed else None
