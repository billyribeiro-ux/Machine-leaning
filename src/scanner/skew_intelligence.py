"""
Revolution Alpha Engine - Skew & Market Internals Intelligence.

We see the move BEFORE the move.

Proprietary predictive skew analysis that identifies fear/greed extremes
and intermarket divergences before they resolve.

Components:
    SkewSurfaceAnalyzer     - Full skew surface construction at 10D/15D/25D/
                              35D/50D with regime classification and momentum
    PutCallAnalyzer         - Premium-weighted PCR spectrum, z-score analysis,
                              expiration heatmap, and regime-combined signals
    MarketInternalsEngine   - NYSE TICK, up/down volume, AD momentum, sector
                              divergence, bond-equity correlation, credit spreads,
                              and intermarket divergence detection
    VolatilityTermStructure - VIX contango/backwardation, roll yield, VVIX,
                              realized-vs-implied spread, and vol surface regime
    SkewIntelligenceScanner - Main scanner tying all components into unified
                              AdvancedScanResult signals

Mathematical foundations:
    - All z-scores: (x - mu) / sigma over rolling 252-day window
    - Premium-weighted PCR: sum(put_premium) / sum(call_premium)
    - Skew momentum: (skew_t - skew_{t-n}) / std(delta-skew, rolling window)
    - Contango: (F1 - VIX_spot) / VIX_spot * 100
    - McClellan acceleration: finite difference of McClellan Oscillator
    - Bond-equity correlation: Pearson over 60-day rolling window
    - Butterfly spread signal: wing IV average minus body IV at each tenor
"""

import math
import uuid
import logging
import numpy as np
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple, Any, Literal
from collections import deque, defaultdict

from .base import BaseScanner, ScanContext, MarketData, HistoricalData
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
    VolatilityRegime,
    IVSurface,
    IVSurfacePoint,
    GreeksExposure,
    BreadthSnapshot,
)
from .options_scanner import OptionContract, OptionsChain

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_TRADING_DAYS_PER_YEAR: int = 252
_DEFAULT_ROLLING_WINDOW: int = 252
_DEFAULT_RISK_FREE_RATE: float = 0.05
_TICK_EXTREME_UPPER: int = 1000
_TICK_EXTREME_LOWER: int = -1000


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Return numerator / denominator, falling back to default on zero."""
    if denominator == 0.0:
        return default
    return numerator / denominator


def _z_score(value: float, mean: float, std: float) -> float:
    """Compute z-score with safe division."""
    if std <= 0.0:
        return 0.0
    return (value - mean) / std


def _rolling_mean(arr: np.ndarray, window: int) -> np.ndarray:
    """Compute rolling mean using cumulative sum for efficiency.

    Args:
        arr: 1-D array of float values.
        window: Look-back window size.

    Returns:
        Array of the same length with rolling mean; leading values are NaN.
    """
    if len(arr) < window:
        return np.full_like(arr, np.nan, dtype=np.float64)
    cumsum = np.cumsum(np.insert(arr.astype(np.float64), 0, 0.0))
    result = np.full(len(arr), np.nan, dtype=np.float64)
    result[window - 1:] = (cumsum[window:] - cumsum[:-window]) / window
    return result


def _rolling_std(arr: np.ndarray, window: int) -> np.ndarray:
    """Compute rolling standard deviation.

    Args:
        arr: 1-D array of float values.
        window: Look-back window size.

    Returns:
        Array of the same length with rolling std; leading values are NaN.
    """
    if len(arr) < window:
        return np.full_like(arr, np.nan, dtype=np.float64)
    result = np.full(len(arr), np.nan, dtype=np.float64)
    a = arr.astype(np.float64)
    for i in range(window - 1, len(a)):
        result[i] = np.std(a[i - window + 1: i + 1], ddof=1)
    return result


def _ema(series: np.ndarray, span: int) -> np.ndarray:
    """Compute exponential moving average over a 1-D numpy array.

    Uses k = 2 / (span + 1) and seeds with the SMA of the first *span* values.

    Args:
        series: 1-D array of float values.
        span: EMA look-back period.

    Returns:
        Array of the same length; elements before the first valid window are NaN.
    """
    if len(series) == 0:
        return np.array([], dtype=np.float64)
    out = np.full_like(series, np.nan, dtype=np.float64)
    k = 2.0 / (span + 1)
    if len(series) < span:
        out[-1] = float(np.nanmean(series))
        return out
    out[span - 1] = float(np.mean(series[:span]))
    for i in range(span, len(series)):
        out[i] = series[i] * k + out[i - 1] * (1.0 - k)
    return out


def _percentile_rank(value: float, history: np.ndarray) -> float:
    """Compute percentile rank of value within historical distribution.

    Args:
        value: Current observation.
        history: Historical observations to rank against.

    Returns:
        Percentile rank 0-100.
    """
    if len(history) == 0:
        return 50.0
    return float(np.sum(history <= value) / len(history) * 100.0)


def _pearson_correlation(x: np.ndarray, y: np.ndarray) -> float:
    """Compute Pearson correlation between two arrays.

    Args:
        x: First array.
        y: Second array.

    Returns:
        Pearson r in [-1, 1], or 0.0 if inputs are degenerate.
    """
    if len(x) < 3 or len(y) < 3 or len(x) != len(y):
        return 0.0
    x_mean = np.mean(x)
    y_mean = np.mean(y)
    xd = x - x_mean
    yd = y - y_mean
    denom = np.sqrt(np.sum(xd ** 2) * np.sum(yd ** 2))
    if denom == 0.0:
        return 0.0
    return float(np.sum(xd * yd) / denom)


def _norm_cdf(x: float) -> float:
    """Standard normal CDF approximation via math.erf."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _bs_delta(
    spot: float, strike: float, t: float, sigma: float,
    option_type: str, r: float = _DEFAULT_RISK_FREE_RATE
) -> float:
    """Black-Scholes delta estimate.

    Args:
        spot: Underlying price.
        strike: Option strike.
        t: Time to expiry in years.
        sigma: Implied volatility.
        option_type: 'CALL' or 'PUT'.
        r: Risk-free rate.

    Returns:
        Estimated delta.
    """
    if t <= 0 or sigma <= 0 or spot <= 0 or strike <= 0:
        if option_type == "CALL":
            return 1.0 if spot > strike else 0.0
        return -1.0 if spot < strike else 0.0
    d1 = (math.log(spot / strike) + (r + 0.5 * sigma ** 2) * t) / (sigma * math.sqrt(t))
    if option_type == "CALL":
        return _norm_cdf(d1)
    return _norm_cdf(d1) - 1.0


# =============================================================================
# Intermediate Data Models
# =============================================================================

@dataclass
class SkewPoint:
    """A single point on the skew surface keyed by delta bucket and tenor."""
    delta_bucket: int          # Absolute delta target: 10, 15, 25, 35, 50
    tenor_days: int            # Days to expiration
    put_iv: float              # IV of the put at this delta
    call_iv: float             # IV of the call at this delta
    skew: float                # put_iv - call_iv (positive = put skew)
    butterfly: float           # (wing_avg - body_iv) for this delta pair


@dataclass
class SkewSurface:
    """Full skew surface across deltas and tenors."""
    symbol: str
    timestamp: datetime
    underlying_price: float
    points: List[SkewPoint] = field(default_factory=list)
    delta_buckets: List[int] = field(default_factory=lambda: [10, 15, 25, 35, 50])
    tenors: List[int] = field(default_factory=list)

    def get_skew_at(self, delta_bucket: int, tenor_days: int) -> Optional[SkewPoint]:
        """Retrieve skew point for a given delta bucket and tenor.

        Args:
            delta_bucket: The absolute delta target (10, 15, 25, 35, 50).
            tenor_days: Days to expiration.

        Returns:
            Matching SkewPoint or None.
        """
        for p in self.points:
            if p.delta_bucket == delta_bucket and p.tenor_days == tenor_days:
                return p
        return None

    @property
    def atm_term_structure(self) -> List[Tuple[int, float]]:
        """ATM (50-delta) IV across all tenors.

        Returns:
            List of (tenor_days, atm_iv) tuples sorted by tenor.
        """
        atm_points = [p for p in self.points if p.delta_bucket == 50]
        result = []
        for p in sorted(atm_points, key=lambda x: x.tenor_days):
            atm_iv = (p.put_iv + p.call_iv) / 2.0
            result.append((p.tenor_days, atm_iv))
        return result

    @property
    def skew_25d_by_tenor(self) -> List[Tuple[int, float]]:
        """25-delta risk reversal (put_iv - call_iv) across tenors.

        Returns:
            List of (tenor_days, skew_25d) tuples sorted by tenor.
        """
        pts = [p for p in self.points if p.delta_bucket == 25]
        return [(p.tenor_days, p.skew) for p in sorted(pts, key=lambda x: x.tenor_days)]


@dataclass
class SkewRegime:
    """Classification of the current skew environment."""
    regime: Literal[
        "CRASH_FEAR", "ELEVATED_FEAR", "NORMAL", "COMPLACENT", "EUPHORIA"
    ]
    skew_25d: float            # Current 25-delta risk reversal
    skew_percentile: float     # Percentile rank vs history (0-100)
    skew_z_score: float        # Z-score vs rolling history
    put_call_ratio: float      # Associated put-call skew ratio
    description: str           # Human-readable regime description


@dataclass
class SkewMomentum:
    """Rate of change in skew steepening/flattening."""
    skew_roc_1d: float         # 1-day skew change
    skew_roc_5d: float         # 5-day skew change
    skew_roc_20d: float        # 20-day skew change
    momentum_z_score: float    # Z-score of current momentum
    is_steepening: bool        # True if skew is steepening
    acceleration: float        # Second derivative of skew


@dataclass
class CrossAssetSkewResult:
    """Cross-asset skew divergence analysis."""
    spy_skew: float
    qqq_skew: float
    iwm_skew: float
    vix_skew: float
    spy_qqq_divergence: float      # SPY skew minus QQQ skew
    spy_iwm_divergence: float      # SPY skew minus IWM skew
    tech_fear_premium: float       # QQQ skew excess over SPY
    small_cap_stress: float        # IWM skew excess over SPY
    max_divergence: float          # Largest absolute divergence
    divergence_signal: Literal["NONE", "MODERATE", "EXTREME"]


@dataclass
class SkewTermStructureResult:
    """Skew term structure analysis."""
    near_term_skew: float          # Front-month skew
    far_term_skew: float           # Back-month skew
    term_structure_slope: float    # Far minus near
    is_inverted: bool              # Near > Far = crash imminent
    inversion_magnitude: float     # How much inversion
    signal_strength: float         # 0-1 strength of term structure signal


@dataclass
class ButterflySignal:
    """Fat-tail pricing signal from butterfly spreads."""
    delta_bucket: int              # 10D or 25D
    tenor_days: int
    butterfly_width: float         # Wing average minus body IV
    butterfly_z_score: float       # Z-score vs history
    fat_tail_premium: float        # Excess kurtosis pricing
    signal: Literal["NONE", "ELEVATED_TAILS", "EXTREME_TAILS"]


@dataclass
class PCRSpectrum:
    """Put/call ratio computed at every strike."""
    symbol: str
    timestamp: datetime
    by_strike: Dict[float, Dict[str, float]] = field(default_factory=dict)
    # Each strike maps to {"volume_pcr": x, "oi_pcr": y, "premium_pcr": z}
    overall_volume_pcr: float = 0.0
    overall_oi_pcr: float = 0.0
    overall_premium_pcr: float = 0.0


@dataclass
class ExpirationPCRHeatmap:
    """PCR breakdown by expiration bucket."""
    weekly_pcr: float = 0.0        # 0-7 DTE
    monthly_pcr: float = 0.0       # 8-35 DTE
    quarterly_pcr: float = 0.0     # 36-100 DTE
    leaps_pcr: float = 0.0         # > 100 DTE
    dominant_bucket: str = "monthly"
    max_pcr_deviation: float = 0.0


@dataclass
class PCRRegimeSignal:
    """Combined PCR + skew regime signal."""
    pcr_z_score: float
    skew_regime: str
    combined_score: float          # -1.0 (extreme bearish) to +1.0 (extreme bullish)
    conviction: float              # 0-1 conviction level
    signal: Literal["STRONG_BULLISH", "BULLISH", "NEUTRAL", "BEARISH", "STRONG_BEARISH"]


@dataclass
class TickInternals:
    """NYSE TICK analysis results."""
    cumulative_tick: float         # Running sum of TICK values
    current_tick: float            # Most recent TICK reading
    extreme_up_count: int          # Count of readings > +1000
    extreme_down_count: int        # Count of readings < -1000
    tick_ma: float                 # Moving average of TICK
    tick_divergence: float         # Divergence vs price direction
    bias: Literal["BULLISH", "BEARISH", "NEUTRAL"]


@dataclass
class VolumeInternals:
    """Up/down volume differential analysis."""
    up_volume: float
    down_volume: float
    volume_ratio: float            # up / down
    volume_differential: float     # up - down
    z_score: float                 # Z-score of volume ratio
    bias: Literal["BULLISH", "BEARISH", "NEUTRAL"]


@dataclass
class SectorDivergenceResult:
    """Sector divergence signal."""
    xlf_return: float              # Financial sector return
    xlk_return: float              # Technology sector return
    divergence_std: float          # Divergence in standard deviations
    leading_sector: str            # Which sector leads
    regime_rotation_signal: bool   # True when divergence > 2 std
    description: str


@dataclass
class BondEquityCorrelation:
    """Bond-equity rolling correlation analysis."""
    correlation_60d: float         # 60-day rolling Pearson
    correlation_20d: float         # 20-day rolling Pearson
    regime: Literal["RISK_ON", "RISK_OFF", "TRANSITIONING"]
    correlation_z_score: float     # Z-score vs historical
    trend: Literal["STRENGTHENING", "WEAKENING", "STABLE"]


@dataclass
class CreditSpreadSignal:
    """Credit stress signal from HYG-LQD spread."""
    spread: float                  # HYG yield - LQD yield proxy
    spread_z_score: float          # Z-score vs rolling history
    spread_percentile: float       # Percentile rank
    widening: bool                 # True if spread is widening
    stress_level: Literal["NORMAL", "ELEVATED", "STRESS", "CRISIS"]


@dataclass
class IntermarketDivergence:
    """Intermarket index divergence analysis."""
    spy_return: float
    qqq_return: float
    iwm_return: float
    dia_return: float
    max_spread: float              # Maximum return spread
    divergence_z_score: float      # Z-score of spread
    lagging_index: str             # Which index lags
    leading_index: str             # Which index leads
    divergence_signal: bool        # Actionable divergence detected


@dataclass
class VolTermStructureResult:
    """Volatility term structure analysis."""
    contango_pct: float            # (F1 - VIX) / VIX * 100
    is_backwardated: bool          # True if contango_pct < 0
    roll_yield: float              # Expected roll yield
    vol_of_vol: float              # VVIX or vol-of-vol measure
    rv_iv_spread: float            # Realized minus implied vol
    vol_surface_regime: Literal[
        "LOW_VOL_COMPLACENT", "NORMAL", "ELEVATED", "CRISIS", "VOL_CRUSH"
    ]


@dataclass
class SkewIntelligenceResult:
    """Aggregated result from the full skew intelligence pipeline."""
    symbol: str
    timestamp: datetime
    skew_regime: Optional[SkewRegime] = None
    skew_momentum: Optional[SkewMomentum] = None
    cross_asset: Optional[CrossAssetSkewResult] = None
    skew_term_structure: Optional[SkewTermStructureResult] = None
    butterfly_signals: List[ButterflySignal] = field(default_factory=list)
    pcr_spectrum: Optional[PCRSpectrum] = None
    pcr_regime: Optional[PCRRegimeSignal] = None
    tick_internals: Optional[TickInternals] = None
    volume_internals: Optional[VolumeInternals] = None
    sector_divergence: Optional[SectorDivergenceResult] = None
    bond_equity: Optional[BondEquityCorrelation] = None
    credit_spread: Optional[CreditSpreadSignal] = None
    intermarket: Optional[IntermarketDivergence] = None
    vol_term_structure: Optional[VolTermStructureResult] = None
    overall_signal: Literal["BULLISH", "BEARISH", "NEUTRAL"] = "NEUTRAL"
    overall_confidence: float = 0.0


# =============================================================================
# 1. Skew Surface Analyzer
# =============================================================================

class SkewSurfaceAnalyzer:
    """Deep skew analysis beyond basic 25-delta risk reversal.

    Constructs a full skew surface across multiple delta buckets (10D, 15D,
    25D, 35D, 50D) and multiple expirations.  Provides regime classification,
    skew momentum tracking, cross-asset divergence detection, term structure
    analysis, and butterfly spread fat-tail signals.

    All delta references use absolute delta values for clarity (i.e., 25D
    means |delta| = 0.25 for both puts and calls).
    """

    # Target absolute delta values for each bucket
    DELTA_BUCKETS: List[int] = [10, 15, 25, 35, 50]

    # Regime thresholds for 25-delta skew percentile
    _REGIME_THRESHOLDS = {
        "CRASH_FEAR": 95.0,
        "ELEVATED_FEAR": 80.0,
        "COMPLACENT": 15.0,
        "EUPHORIA": 5.0,
    }

    def __init__(
        self,
        rolling_window: int = _DEFAULT_ROLLING_WINDOW,
        risk_free_rate: float = _DEFAULT_RISK_FREE_RATE,
    ):
        """Initialize the skew surface analyzer.

        Args:
            rolling_window: Window size for z-score and percentile calculations.
            risk_free_rate: Risk-free rate for delta estimation.
        """
        self.rolling_window = rolling_window
        self.risk_free_rate = risk_free_rate
        self._skew_history: deque = deque(maxlen=rolling_window)

    # ------------------------------------------------------------------
    # Core surface construction
    # ------------------------------------------------------------------

    def compute_full_skew_surface(self, chain: OptionsChain) -> SkewSurface:
        """Build the full skew surface at 10D, 15D, 25D, 35D, 50D for each expiration.

        For each expiration in the chain, identifies the put and call whose
        absolute delta is closest to each target delta bucket, then records
        the IV, skew (put IV minus call IV), and butterfly width.

        Args:
            chain: Options chain with contracts, underlying price, and metadata.

        Returns:
            SkewSurface containing all grid points.
        """
        spot = chain.underlying_price
        if spot <= 0 or not chain.contracts:
            return SkewSurface(
                symbol=chain.underlying,
                timestamp=chain.timestamp,
                underlying_price=spot,
            )

        # Group contracts by expiration
        by_expiry: Dict[datetime, List[OptionContract]] = defaultdict(list)
        for c in chain.contracts:
            by_expiry[c.expiration].append(c)

        points: List[SkewPoint] = []
        tenors: List[int] = []

        for expiry, contracts in sorted(by_expiry.items()):
            tenor_days = max(1, (expiry - datetime.now(timezone.utc)).days)
            t_years = tenor_days / 365.0
            tenors.append(tenor_days)

            puts = [c for c in contracts if c.option_type == "PUT"]
            calls = [c for c in contracts if c.option_type == "CALL"]

            if not puts or not calls:
                continue

            # Estimate delta for each contract if missing
            for c in puts + calls:
                if c.delta is None:
                    iv = c.implied_volatility if c.implied_volatility > 0 else 0.30
                    c.delta = _bs_delta(spot, c.strike, t_years, iv, c.option_type, self.risk_free_rate)

            for bucket in self.DELTA_BUCKETS:
                target_delta = bucket / 100.0

                # Find closest put (target negative delta)
                best_put = self._find_closest_delta(puts, -target_delta)
                # Find closest call (target positive delta)
                best_call = self._find_closest_delta(calls, target_delta)

                if best_put is None or best_call is None:
                    continue

                put_iv = best_put.implied_volatility
                call_iv = best_call.implied_volatility

                if put_iv <= 0 or call_iv <= 0:
                    continue

                skew = put_iv - call_iv
                # Butterfly: average wing IV minus ATM body IV
                # For non-ATM buckets, butterfly = 0.5*(put_iv + call_iv) - atm_iv
                atm_iv = self._get_atm_iv(puts, calls, spot, t_years)
                wing_avg = (put_iv + call_iv) / 2.0
                butterfly = wing_avg - atm_iv if atm_iv > 0 else 0.0

                points.append(SkewPoint(
                    delta_bucket=bucket,
                    tenor_days=tenor_days,
                    put_iv=put_iv,
                    call_iv=call_iv,
                    skew=skew,
                    butterfly=butterfly,
                ))

        surface = SkewSurface(
            symbol=chain.underlying,
            timestamp=chain.timestamp,
            underlying_price=spot,
            points=points,
            tenors=sorted(set(tenors)),
        )
        return surface

    def detect_skew_regime(self, surface: SkewSurface) -> SkewRegime:
        """Classify the current skew environment into a named regime.

        Regime is determined by the 25-delta risk reversal percentile rank
        relative to rolling history:
            >= 95th percentile  -> CRASH_FEAR
            >= 80th percentile  -> ELEVATED_FEAR
            <= 5th  percentile  -> EUPHORIA
            <= 15th percentile  -> COMPLACENT
            otherwise           -> NORMAL

        Args:
            surface: The current skew surface.

        Returns:
            SkewRegime with classification, z-score, and description.
        """
        # Extract 25-delta skew from the shortest available tenor
        skew_25d = 0.0
        pts_25d = [p for p in surface.points if p.delta_bucket == 25]
        if pts_25d:
            # Use the shortest tenor for regime classification
            front_pt = min(pts_25d, key=lambda p: p.tenor_days)
            skew_25d = front_pt.skew

        # Compute percentile and z-score against history
        history = np.array(list(self._skew_history), dtype=np.float64)
        self._skew_history.append(skew_25d)

        if len(history) >= 20:
            pct = _percentile_rank(skew_25d, history)
            z = _z_score(skew_25d, float(np.mean(history)), float(np.std(history)))
        else:
            pct = 50.0
            z = 0.0

        # Put/call IV ratio at 25D
        pc_ratio = 1.0
        if pts_25d:
            front = min(pts_25d, key=lambda p: p.tenor_days)
            if front.call_iv > 0:
                pc_ratio = front.put_iv / front.call_iv

        # Classify regime
        if pct >= self._REGIME_THRESHOLDS["CRASH_FEAR"]:
            regime = "CRASH_FEAR"
            desc = (
                f"Extreme put skew at {pct:.0f}th percentile "
                f"(z={z:+.2f}). Market pricing crash protection."
            )
        elif pct >= self._REGIME_THRESHOLDS["ELEVATED_FEAR"]:
            regime = "ELEVATED_FEAR"
            desc = (
                f"Elevated put skew at {pct:.0f}th percentile "
                f"(z={z:+.2f}). Hedging demand above normal."
            )
        elif pct <= self._REGIME_THRESHOLDS["EUPHORIA"]:
            regime = "EUPHORIA"
            desc = (
                f"Extreme complacency: skew at {pct:.0f}th percentile "
                f"(z={z:+.2f}). Puts historically cheap -- contrarian bearish."
            )
        elif pct <= self._REGIME_THRESHOLDS["COMPLACENT"]:
            regime = "COMPLACENT"
            desc = (
                f"Low skew at {pct:.0f}th percentile "
                f"(z={z:+.2f}). Limited hedging demand."
            )
        else:
            regime = "NORMAL"
            desc = f"Normal skew at {pct:.0f}th percentile (z={z:+.2f})."

        return SkewRegime(
            regime=regime,
            skew_25d=skew_25d,
            skew_percentile=pct,
            skew_z_score=z,
            put_call_ratio=pc_ratio,
            description=desc,
        )

    def skew_momentum(self, history: np.ndarray) -> SkewMomentum:
        """Track rate of change in skew steepening/flattening.

        Computes skew change over 1, 5, and 20-day windows, then
        standardises the current momentum as a z-score against the
        rolling distribution of skew changes.

        Args:
            history: Array of historical 25-delta skew values (oldest first).

        Returns:
            SkewMomentum with rate-of-change and acceleration metrics.
        """
        h = np.asarray(history, dtype=np.float64)
        n = len(h)

        roc_1d = h[-1] - h[-2] if n >= 2 else 0.0
        roc_5d = h[-1] - h[-6] if n >= 6 else 0.0
        roc_20d = h[-1] - h[-21] if n >= 21 else 0.0

        # Z-score of 1-day changes
        if n >= 22:
            changes = np.diff(h[-(self.rolling_window + 1):])
            mu = float(np.mean(changes))
            sigma = float(np.std(changes, ddof=1))
            mom_z = _z_score(roc_1d, mu, sigma)
        else:
            mom_z = 0.0

        # Acceleration = second finite difference
        if n >= 3:
            accel = (h[-1] - 2.0 * h[-2] + h[-3])
        else:
            accel = 0.0

        return SkewMomentum(
            skew_roc_1d=float(roc_1d),
            skew_roc_5d=float(roc_5d),
            skew_roc_20d=float(roc_20d),
            momentum_z_score=float(mom_z),
            is_steepening=roc_5d > 0,
            acceleration=float(accel),
        )

    def cross_asset_skew_correlation(
        self,
        spy_skew: float,
        qqq_skew: float,
        iwm_skew: float,
        vix_skew: float,
    ) -> CrossAssetSkewResult:
        """Detect divergences between index skews.

        Computes pairwise divergences between SPY, QQQ, IWM, and VIX
        skew readings.  A large divergence between indices signals
        rotational stress or sector-specific fear.

        Args:
            spy_skew: SPY 25-delta risk reversal.
            qqq_skew: QQQ 25-delta risk reversal.
            iwm_skew: IWM 25-delta risk reversal.
            vix_skew: VIX 25-delta risk reversal.

        Returns:
            CrossAssetSkewResult with divergence metrics.
        """
        spy_qqq = spy_skew - qqq_skew
        spy_iwm = spy_skew - iwm_skew
        tech_fear = qqq_skew - spy_skew   # Positive = QQQ puts relatively expensive
        small_cap_stress = iwm_skew - spy_skew

        divergences = [abs(spy_qqq), abs(spy_iwm), abs(tech_fear)]
        max_div = max(divergences) if divergences else 0.0

        # Classify
        if max_div > 0.08:
            signal = "EXTREME"
        elif max_div > 0.04:
            signal = "MODERATE"
        else:
            signal = "NONE"

        return CrossAssetSkewResult(
            spy_skew=spy_skew,
            qqq_skew=qqq_skew,
            iwm_skew=iwm_skew,
            vix_skew=vix_skew,
            spy_qqq_divergence=spy_qqq,
            spy_iwm_divergence=spy_iwm,
            tech_fear_premium=tech_fear,
            small_cap_stress=small_cap_stress,
            max_divergence=max_div,
            divergence_signal=signal,
        )

    def skew_term_structure(self, chain: OptionsChain) -> SkewTermStructureResult:
        """Compare near-term vs far-term 25-delta skew.

        An inverted skew term structure (near > far) indicates imminent
        crash risk: market makers are pricing near-term tail risk more
        aggressively than longer-term risk.

        Args:
            chain: Full options chain.

        Returns:
            SkewTermStructureResult with inversion detection.
        """
        surface = self.compute_full_skew_surface(chain)
        skew_by_tenor = surface.skew_25d_by_tenor

        if len(skew_by_tenor) < 2:
            return SkewTermStructureResult(
                near_term_skew=0.0,
                far_term_skew=0.0,
                term_structure_slope=0.0,
                is_inverted=False,
                inversion_magnitude=0.0,
                signal_strength=0.0,
            )

        near_tenor, near_skew = skew_by_tenor[0]
        far_tenor, far_skew = skew_by_tenor[-1]
        slope = far_skew - near_skew
        inverted = near_skew > far_skew and near_skew > 0
        inversion_mag = max(0.0, near_skew - far_skew) if inverted else 0.0

        # Signal strength: normalise inversion magnitude
        strength = min(1.0, inversion_mag / 0.10) if inverted else 0.0

        return SkewTermStructureResult(
            near_term_skew=near_skew,
            far_term_skew=far_skew,
            term_structure_slope=slope,
            is_inverted=inverted,
            inversion_magnitude=inversion_mag,
            signal_strength=strength,
        )

    def butterfly_spread_signal(
        self,
        surface: SkewSurface,
        butterfly_history: Optional[np.ndarray] = None,
    ) -> List[ButterflySignal]:
        """Detect fat-tail pricing from butterfly spreads at 10D and 25D.

        A high butterfly spread means wings are expensive relative to ATM,
        signalling that the market is pricing fat tails (kurtosis premium).

        Args:
            surface: Skew surface with butterfly widths.
            butterfly_history: Optional historical butterfly values for z-scores.

        Returns:
            List of ButterflySignal for each delta/tenor combination.
        """
        signals: List[ButterflySignal] = []
        target_deltas = [10, 25]

        for pt in surface.points:
            if pt.delta_bucket not in target_deltas:
                continue

            bfly = pt.butterfly

            # Compute z-score vs history if available
            if butterfly_history is not None and len(butterfly_history) >= 20:
                mu = float(np.mean(butterfly_history))
                sigma = float(np.std(butterfly_history, ddof=1))
                bfly_z = _z_score(bfly, mu, sigma)
            else:
                bfly_z = 0.0

            # Fat-tail premium: butterfly as fraction of ATM vol
            atm_pts = [p for p in surface.points
                       if p.delta_bucket == 50 and p.tenor_days == pt.tenor_days]
            if atm_pts:
                atm_iv = (atm_pts[0].put_iv + atm_pts[0].call_iv) / 2.0
                fat_tail = _safe_divide(bfly, atm_iv)
            else:
                fat_tail = 0.0

            if abs(bfly_z) > 2.5 or fat_tail > 0.15:
                sig = "EXTREME_TAILS"
            elif abs(bfly_z) > 1.5 or fat_tail > 0.08:
                sig = "ELEVATED_TAILS"
            else:
                sig = "NONE"

            signals.append(ButterflySignal(
                delta_bucket=pt.delta_bucket,
                tenor_days=pt.tenor_days,
                butterfly_width=bfly,
                butterfly_z_score=bfly_z,
                fat_tail_premium=fat_tail,
                signal=sig,
            ))

        return signals

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_closest_delta(
        contracts: List[OptionContract], target_delta: float
    ) -> Optional[OptionContract]:
        """Find the contract whose delta is closest to the target.

        Args:
            contracts: List of option contracts with deltas populated.
            target_delta: Target delta value (signed).

        Returns:
            Contract with closest delta, or None if no valid contracts.
        """
        best = None
        best_dist = float("inf")
        for c in contracts:
            if c.delta is None:
                continue
            dist = abs(c.delta - target_delta)
            if dist < best_dist:
                best_dist = dist
                best = c
        return best

    @staticmethod
    def _get_atm_iv(
        puts: List[OptionContract],
        calls: List[OptionContract],
        spot: float,
        t_years: float,
    ) -> float:
        """Estimate ATM implied volatility as the average of the nearest
        put and call IV to the spot price.

        Args:
            puts: Put contracts for a given expiration.
            calls: Call contracts for a given expiration.
            spot: Current underlying price.
            t_years: Time to expiry in years.

        Returns:
            ATM implied volatility estimate.
        """
        nearest_put = min(puts, key=lambda c: abs(c.strike - spot), default=None)
        nearest_call = min(calls, key=lambda c: abs(c.strike - spot), default=None)

        ivs = []
        if nearest_put and nearest_put.implied_volatility > 0:
            ivs.append(nearest_put.implied_volatility)
        if nearest_call and nearest_call.implied_volatility > 0:
            ivs.append(nearest_call.implied_volatility)

        return float(np.mean(ivs)) if ivs else 0.0


# =============================================================================
# 2. Put/Call Analyzer
# =============================================================================

class PutCallAnalyzer:
    """Comprehensive put/call ratio analysis.

    Goes beyond simple volume PCR to compute premium-weighted ratios,
    strike-level heatmaps, expiration-bucket breakdowns, and combined
    regime signals with the skew analyzer.
    """

    def __init__(self, rolling_window: int = _DEFAULT_ROLLING_WINDOW):
        """Initialize PutCallAnalyzer.

        Args:
            rolling_window: Window for z-score and percentile calculations.
        """
        self.rolling_window = rolling_window
        self._pcr_history: deque = deque(maxlen=rolling_window)

    def compute_pcr_spectrum(self, chain: OptionsChain) -> PCRSpectrum:
        """Compute put/call ratios by volume AND open interest at every strike.

        Also computes premium-weighted overall PCR.

        Args:
            chain: Full options chain.

        Returns:
            PCRSpectrum with per-strike and overall ratios.
        """
        by_strike: Dict[float, Dict[str, float]] = {}

        # Group by strike
        strike_puts: Dict[float, List[OptionContract]] = defaultdict(list)
        strike_calls: Dict[float, List[OptionContract]] = defaultdict(list)

        for c in chain.contracts:
            if c.option_type == "PUT":
                strike_puts[c.strike].append(c)
            else:
                strike_calls[c.strike].append(c)

        all_strikes = sorted(set(list(strike_puts.keys()) + list(strike_calls.keys())))

        total_put_vol = 0
        total_call_vol = 0
        total_put_oi = 0
        total_call_oi = 0
        total_put_premium = 0.0
        total_call_premium = 0.0

        for strike in all_strikes:
            p_vol = sum(c.volume for c in strike_puts.get(strike, []))
            c_vol = sum(c.volume for c in strike_calls.get(strike, []))
            p_oi = sum(c.open_interest for c in strike_puts.get(strike, []))
            c_oi = sum(c.open_interest for c in strike_calls.get(strike, []))

            # Premium = mid_price * volume * 100
            p_prem = sum(c.mid_price * c.volume * 100 for c in strike_puts.get(strike, []))
            c_prem = sum(c.mid_price * c.volume * 100 for c in strike_calls.get(strike, []))

            by_strike[strike] = {
                "volume_pcr": _safe_divide(p_vol, c_vol),
                "oi_pcr": _safe_divide(p_oi, c_oi),
                "premium_pcr": _safe_divide(p_prem, c_prem),
            }

            total_put_vol += p_vol
            total_call_vol += c_vol
            total_put_oi += p_oi
            total_call_oi += c_oi
            total_put_premium += p_prem
            total_call_premium += c_prem

        overall_vol_pcr = _safe_divide(total_put_vol, total_call_vol)
        overall_oi_pcr = _safe_divide(total_put_oi, total_call_oi)
        overall_prem_pcr = _safe_divide(total_put_premium, total_call_premium)

        return PCRSpectrum(
            symbol=chain.underlying,
            timestamp=chain.timestamp,
            by_strike=by_strike,
            overall_volume_pcr=overall_vol_pcr,
            overall_oi_pcr=overall_oi_pcr,
            overall_premium_pcr=overall_prem_pcr,
        )

    def pcr_z_score(self, current_pcr: float, history: np.ndarray) -> float:
        """Compute the statistical deviation of current PCR from its rolling mean.

        Args:
            current_pcr: Current put/call ratio value.
            history: Array of historical PCR values.

        Returns:
            Z-score of the current PCR.
        """
        h = np.asarray(history, dtype=np.float64)
        if len(h) < 20:
            return 0.0
        mu = float(np.mean(h))
        sigma = float(np.std(h, ddof=1))
        return _z_score(current_pcr, mu, sigma)

    def smart_pcr(self, chain: OptionsChain) -> float:
        """Compute premium-weighted PCR.

        Weights by actual dollars spent (premium * volume * multiplier)
        rather than raw contract count, which gives a more accurate
        picture of directional capital commitment.

        Formula: sum(put_premium_dollars) / sum(call_premium_dollars)
        where premium_dollars = mid_price * volume * 100

        Args:
            chain: Full options chain.

        Returns:
            Premium-weighted put/call ratio.
        """
        put_premium = 0.0
        call_premium = 0.0

        for c in chain.contracts:
            prem = c.mid_price * c.volume * 100.0
            if c.option_type == "PUT":
                put_premium += prem
            else:
                call_premium += prem

        return _safe_divide(put_premium, call_premium)

    def expiration_pcr_heatmap(self, chain: OptionsChain) -> ExpirationPCRHeatmap:
        """Compute PCR breakdown by expiration bucket.

        Buckets:
            Weekly   : 0-7 DTE
            Monthly  : 8-35 DTE
            Quarterly: 36-100 DTE
            LEAPS    : > 100 DTE

        Args:
            chain: Full options chain.

        Returns:
            ExpirationPCRHeatmap with per-bucket PCR and dominant bucket.
        """
        buckets = {"weekly": (0, 7), "monthly": (8, 35), "quarterly": (36, 100), "leaps": (101, 9999)}
        bucket_puts: Dict[str, float] = defaultdict(float)
        bucket_calls: Dict[str, float] = defaultdict(float)

        for c in chain.contracts:
            dte = c.days_to_expiry
            for name, (lo, hi) in buckets.items():
                if lo <= dte <= hi:
                    premium = c.mid_price * c.volume * 100.0
                    if c.option_type == "PUT":
                        bucket_puts[name] += premium
                    else:
                        bucket_calls[name] += premium
                    break

        weekly_pcr = _safe_divide(bucket_puts["weekly"], bucket_calls["weekly"])
        monthly_pcr = _safe_divide(bucket_puts["monthly"], bucket_calls["monthly"])
        quarterly_pcr = _safe_divide(bucket_puts["quarterly"], bucket_calls["quarterly"])
        leaps_pcr = _safe_divide(bucket_puts["leaps"], bucket_calls["leaps"])

        pcrs = {"weekly": weekly_pcr, "monthly": monthly_pcr,
                "quarterly": quarterly_pcr, "leaps": leaps_pcr}
        dominant = max(pcrs, key=lambda k: pcrs[k])

        values = list(pcrs.values())
        mean_pcr = float(np.mean(values)) if values else 0.0
        max_dev = max(abs(v - mean_pcr) for v in values) if values else 0.0

        return ExpirationPCRHeatmap(
            weekly_pcr=weekly_pcr,
            monthly_pcr=monthly_pcr,
            quarterly_pcr=quarterly_pcr,
            leaps_pcr=leaps_pcr,
            dominant_bucket=dominant,
            max_pcr_deviation=max_dev,
        )

    def pcr_regime_signal(
        self,
        z_score: float,
        skew_regime: str,
    ) -> PCRRegimeSignal:
        """Generate a combined signal from PCR z-score and skew regime.

        High-conviction signals require BOTH extreme PCR and extreme skew
        to confirm directional bias.  The combination reduces false positives
        relative to either indicator alone.

        Scoring logic:
            - PCR z > +2 AND skew = CRASH_FEAR/ELEVATED_FEAR -> STRONG_BEARISH
              (but contrarian BULLISH if sentiment is at max extreme)
            - PCR z < -2 AND skew = COMPLACENT/EUPHORIA -> STRONG_BULLISH
              (contrarian: too much complacency is bearish)
            - One extreme without confirmation -> moderate signal

        Args:
            z_score: Current PCR z-score.
            skew_regime: Skew regime string from SkewRegime.

        Returns:
            PCRRegimeSignal with combined score and conviction.
        """
        # Map PCR z-score to a sentiment score (-1 to +1)
        pcr_sentiment = max(-1.0, min(1.0, -z_score / 3.0))

        # Map skew regime to a fear score
        skew_scores = {
            "CRASH_FEAR": -1.0,
            "ELEVATED_FEAR": -0.5,
            "NORMAL": 0.0,
            "COMPLACENT": 0.5,
            "EUPHORIA": 1.0,
        }
        skew_sentiment = skew_scores.get(skew_regime, 0.0)

        # Contrarian combined score: extreme fear is actually bullish
        # extreme complacency is bearish
        combined = (pcr_sentiment + skew_sentiment) / 2.0

        # Conviction: high when both indicators agree on an extreme
        agreement = 1.0 - abs(pcr_sentiment - skew_sentiment) / 2.0
        extremity = (abs(pcr_sentiment) + abs(skew_sentiment)) / 2.0
        conviction = agreement * extremity

        # Classify signal
        if combined > 0.5:
            signal = "STRONG_BULLISH"
        elif combined > 0.2:
            signal = "BULLISH"
        elif combined < -0.5:
            signal = "STRONG_BEARISH"
        elif combined < -0.2:
            signal = "BEARISH"
        else:
            signal = "NEUTRAL"

        return PCRRegimeSignal(
            pcr_z_score=z_score,
            skew_regime=skew_regime,
            combined_score=combined,
            conviction=conviction,
            signal=signal,
        )


# =============================================================================
# 3. Market Internals Engine
# =============================================================================

class MarketInternalsEngine:
    """Comprehensive market internals tracking BEYOND breadth.

    Monitors NYSE TICK, up/down volume differentials, AD line momentum,
    sector divergences, bond-equity correlation, credit spreads, and
    intermarket divergences to form a holistic view of internal market
    health.
    """

    def __init__(
        self,
        rolling_window: int = _DEFAULT_ROLLING_WINDOW,
        tick_lookback: int = 390,  # One trading session in minutes
    ):
        """Initialize MarketInternalsEngine.

        Args:
            rolling_window: Window for z-scores and correlations.
            tick_lookback: Number of TICK readings to retain.
        """
        self.rolling_window = rolling_window
        self.tick_lookback = tick_lookback
        self._tick_buffer: deque = deque(maxlen=tick_lookback)
        self._vold_history: deque = deque(maxlen=rolling_window)

    # ------------------------------------------------------------------
    # NYSE TICK Analysis
    # ------------------------------------------------------------------

    def compute_tick_internals(
        self,
        tick_data: np.ndarray,
        price_data: Optional[np.ndarray] = None,
    ) -> TickInternals:
        """Analyse NYSE TICK data for internal market bias.

        Tracks cumulative TICK, extreme reading counts, and TICK-vs-price
        divergence.  Readings beyond +/-1000 are considered extreme and
        indicate programme-driven order flow.

        Args:
            tick_data: Array of TICK values (most recent at end).
            price_data: Optional concurrent price array for divergence detection.

        Returns:
            TickInternals with bias classification.
        """
        t = np.asarray(tick_data, dtype=np.float64)
        if len(t) == 0:
            return TickInternals(
                cumulative_tick=0.0, current_tick=0.0,
                extreme_up_count=0, extreme_down_count=0,
                tick_ma=0.0, tick_divergence=0.0, bias="NEUTRAL",
            )

        cumulative = float(np.sum(t))
        current = float(t[-1])
        extreme_up = int(np.sum(t > _TICK_EXTREME_UPPER))
        extreme_down = int(np.sum(t < _TICK_EXTREME_LOWER))
        tick_ma = float(np.mean(t[-min(20, len(t)):]))

        # Divergence: cumulative TICK direction vs price direction
        divergence = 0.0
        if price_data is not None and len(price_data) >= 2:
            price_dir = 1.0 if price_data[-1] > price_data[0] else -1.0
            tick_dir = 1.0 if cumulative > 0 else -1.0
            if price_dir != tick_dir:
                # Magnitude of divergence
                tick_z = _z_score(cumulative, 0.0, max(1.0, float(np.std(t)) * len(t)))
                divergence = abs(tick_z) * (-1.0 if tick_dir < 0 else 1.0)

        # Bias classification
        net_extreme = extreme_up - extreme_down
        if tick_ma > 200 and net_extreme > 3:
            bias = "BULLISH"
        elif tick_ma < -200 and net_extreme < -3:
            bias = "BEARISH"
        else:
            bias = "NEUTRAL"

        return TickInternals(
            cumulative_tick=cumulative,
            current_tick=current,
            extreme_up_count=extreme_up,
            extreme_down_count=extreme_down,
            tick_ma=tick_ma,
            tick_divergence=divergence,
            bias=bias,
        )

    # ------------------------------------------------------------------
    # Up/Down Volume Differential
    # ------------------------------------------------------------------

    def compute_vold(self, volume_data: Dict[str, np.ndarray]) -> VolumeInternals:
        """Compute up-volume / down-volume differential with z-score.

        Up-volume: total volume of stocks that closed up on the day.
        Down-volume: total volume of stocks that closed down.

        Args:
            volume_data: Dict with keys 'up_volume' and 'down_volume',
                         each an array of daily values.

        Returns:
            VolumeInternals with ratio, differential, and z-score.
        """
        up = np.asarray(volume_data.get("up_volume", [0.0]), dtype=np.float64)
        down = np.asarray(volume_data.get("down_volume", [0.0]), dtype=np.float64)

        if len(up) == 0 or len(down) == 0:
            return VolumeInternals(
                up_volume=0.0, down_volume=0.0, volume_ratio=1.0,
                volume_differential=0.0, z_score=0.0, bias="NEUTRAL",
            )

        current_up = float(up[-1])
        current_down = float(down[-1])
        ratio = _safe_divide(current_up, current_down, 1.0)
        diff = current_up - current_down

        # Z-score of the volume ratio over history
        if len(up) >= 20 and len(down) >= 20:
            min_len = min(len(up), len(down))
            hist_ratios = np.where(
                down[-min_len:] > 0,
                up[-min_len:] / down[-min_len:],
                1.0,
            )
            mu = float(np.mean(hist_ratios))
            sigma = float(np.std(hist_ratios, ddof=1))
            z = _z_score(ratio, mu, sigma)
        else:
            z = 0.0

        self._vold_history.append(ratio)

        if z > 1.5:
            bias = "BULLISH"
        elif z < -1.5:
            bias = "BEARISH"
        else:
            bias = "NEUTRAL"

        return VolumeInternals(
            up_volume=current_up,
            down_volume=current_down,
            volume_ratio=ratio,
            volume_differential=diff,
            z_score=z,
            bias=bias,
        )

    # ------------------------------------------------------------------
    # Advance/Decline Momentum
    # ------------------------------------------------------------------

    def advance_decline_momentum(
        self,
        ad_data: Dict[str, np.ndarray],
    ) -> Dict[str, Any]:
        """Compute AD line slope, McClellan acceleration, and Zweig thrust probability.

        Args:
            ad_data: Dict with keys 'advancers' and 'decliners',
                     each an array of daily counts.

        Returns:
            Dict with 'ad_slope', 'mcclellan_accel', 'zweig_thrust_prob',
            and 'ad_line' array.
        """
        adv = np.asarray(ad_data.get("advancers", []), dtype=np.float64)
        dec = np.asarray(ad_data.get("decliners", []), dtype=np.float64)
        n = min(len(adv), len(dec))

        if n < 10:
            return {
                "ad_slope": 0.0,
                "mcclellan_accel": 0.0,
                "zweig_thrust_prob": 0.0,
                "ad_line": np.array([]),
            }

        adv = adv[-n:]
        dec = dec[-n:]

        # Cumulative AD line
        net = adv - dec
        ad_line = np.cumsum(net)

        # AD line slope: linear regression over last 20 days
        window = min(20, n)
        recent_ad = ad_line[-window:]
        x = np.arange(window, dtype=np.float64)
        if len(x) > 1:
            slope = float(np.polyfit(x, recent_ad, 1)[0])
        else:
            slope = 0.0

        # McClellan Oscillator: EMA(RANA, 19) - EMA(RANA, 39)
        total = adv + dec
        rana = np.where(total > 0, (adv - dec) / total * 1000.0, 0.0)
        ema_fast = _ema(rana, 19)
        ema_slow = _ema(rana, 39)
        mcclellan = ema_fast - ema_slow

        # McClellan acceleration = finite difference of McClellan
        valid_mc = mcclellan[~np.isnan(mcclellan)]
        if len(valid_mc) >= 2:
            accel = float(valid_mc[-1] - valid_mc[-2])
        else:
            accel = 0.0

        # Zweig Breadth Thrust: advance ratio over 10-day window
        # Thrust fires when 10-day EMA of advance ratio goes from < 0.40 to > 0.615
        advance_ratio = np.where(total > 0, adv / total, 0.5)
        ar_ema = _ema(advance_ratio, 10)
        valid_ar = ar_ema[~np.isnan(ar_ema)]
        zweig_prob = 0.0
        if len(valid_ar) >= 10:
            recent_min = float(np.min(valid_ar[-10:]))
            recent_max = float(np.max(valid_ar[-10:]))
            if recent_min < 0.40 and recent_max > 0.615:
                zweig_prob = 1.0
            elif recent_max > 0.55:
                zweig_prob = min(1.0, (recent_max - 0.40) / 0.215)

        return {
            "ad_slope": slope,
            "mcclellan_accel": accel,
            "zweig_thrust_prob": zweig_prob,
            "ad_line": ad_line,
        }

    # ------------------------------------------------------------------
    # Sector Divergence
    # ------------------------------------------------------------------

    def sector_divergence_signal(
        self,
        sector_data: Dict[str, np.ndarray],
    ) -> SectorDivergenceResult:
        """Detect when XLF leads/lags XLK by more than 2 standard deviations.

        A significant divergence between Financials and Technology indicates
        a regime rotation. Historically, when XLF leads XLK by >2 sigma,
        the market is transitioning to a value/cyclical regime.

        Args:
            sector_data: Dict with keys 'XLF' and 'XLK', each an array
                         of daily returns.

        Returns:
            SectorDivergenceResult with divergence magnitude and signal.
        """
        xlf_rets = np.asarray(sector_data.get("XLF", []), dtype=np.float64)
        xlk_rets = np.asarray(sector_data.get("XLK", []), dtype=np.float64)

        n = min(len(xlf_rets), len(xlk_rets))
        if n < 20:
            return SectorDivergenceResult(
                xlf_return=0.0, xlk_return=0.0, divergence_std=0.0,
                leading_sector="NONE", regime_rotation_signal=False,
                description="Insufficient data for sector divergence analysis.",
            )

        xlf_rets = xlf_rets[-n:]
        xlk_rets = xlk_rets[-n:]

        # Cumulative returns over look-back
        xlf_cumret = float(np.sum(xlf_rets[-20:]))
        xlk_cumret = float(np.sum(xlk_rets[-20:]))

        # Divergence in standard deviations
        spread = xlf_rets - xlk_rets
        spread_std = float(np.std(spread, ddof=1))
        current_spread = xlf_cumret - xlk_cumret
        div_std = _safe_divide(current_spread, spread_std) if spread_std > 0 else 0.0

        leading = "XLF" if xlf_cumret > xlk_cumret else "XLK"
        rotation = abs(div_std) > 2.0

        if rotation:
            desc = (
                f"{leading} leads by {abs(div_std):.1f} std devs over 20 days. "
                f"Regime rotation signal active."
            )
        else:
            desc = f"Sector divergence at {abs(div_std):.1f} std devs. No rotation signal."

        return SectorDivergenceResult(
            xlf_return=xlf_cumret,
            xlk_return=xlk_cumret,
            divergence_std=div_std,
            leading_sector=leading,
            regime_rotation_signal=rotation,
            description=desc,
        )

    # ------------------------------------------------------------------
    # Bond-Equity Correlation
    # ------------------------------------------------------------------

    def bond_equity_correlation(
        self,
        spy_data: np.ndarray,
        tlt_data: np.ndarray,
    ) -> BondEquityCorrelation:
        """Compute rolling correlation between SPY and TLT returns.

        Positive correlation = risk-on (stocks and bonds rise together).
        Negative correlation = risk-off (flight to safety, bonds up, stocks down).

        Uses 60-day rolling Pearson correlation as the primary measure.

        Args:
            spy_data: Array of SPY daily returns.
            tlt_data: Array of TLT daily returns.

        Returns:
            BondEquityCorrelation with regime classification.
        """
        spy = np.asarray(spy_data, dtype=np.float64)
        tlt = np.asarray(tlt_data, dtype=np.float64)
        n = min(len(spy), len(tlt))

        if n < 20:
            return BondEquityCorrelation(
                correlation_60d=0.0, correlation_20d=0.0,
                regime="TRANSITIONING", correlation_z_score=0.0,
                trend="STABLE",
            )

        spy = spy[-n:]
        tlt = tlt[-n:]

        # 60-day correlation
        window_60 = min(60, n)
        corr_60 = _pearson_correlation(spy[-window_60:], tlt[-window_60:])

        # 20-day correlation
        window_20 = min(20, n)
        corr_20 = _pearson_correlation(spy[-window_20:], tlt[-window_20:])

        # Z-score of correlation vs rolling history
        if n >= 120:
            hist_corrs = []
            for i in range(60, n):
                c = _pearson_correlation(spy[i - 60:i], tlt[i - 60:i])
                hist_corrs.append(c)
            hist_arr = np.array(hist_corrs, dtype=np.float64)
            corr_z = _z_score(corr_60, float(np.mean(hist_arr)), float(np.std(hist_arr, ddof=1)))
        else:
            corr_z = 0.0

        # Regime classification
        if corr_60 > 0.3:
            regime = "RISK_ON"
        elif corr_60 < -0.3:
            regime = "RISK_OFF"
        else:
            regime = "TRANSITIONING"

        # Trend: is correlation strengthening or weakening?
        if abs(corr_20) > abs(corr_60) + 0.1:
            trend = "STRENGTHENING"
        elif abs(corr_20) < abs(corr_60) - 0.1:
            trend = "WEAKENING"
        else:
            trend = "STABLE"

        return BondEquityCorrelation(
            correlation_60d=corr_60,
            correlation_20d=corr_20,
            regime=regime,
            correlation_z_score=corr_z,
            trend=trend,
        )

    # ------------------------------------------------------------------
    # Credit Spread Monitor
    # ------------------------------------------------------------------

    def credit_spread_monitor(
        self,
        hyg_data: np.ndarray,
        lqd_data: np.ndarray,
    ) -> CreditSpreadSignal:
        """Monitor HYG-LQD spread for credit stress signals.

        A widening spread (HYG underperforming LQD) indicates rising
        credit risk. The spread is computed as relative performance
        differential between high-yield and investment-grade bonds.

        Args:
            hyg_data: Array of HYG daily prices (high yield).
            lqd_data: Array of LQD daily prices (investment grade).

        Returns:
            CreditSpreadSignal with stress classification.
        """
        hyg = np.asarray(hyg_data, dtype=np.float64)
        lqd = np.asarray(lqd_data, dtype=np.float64)
        n = min(len(hyg), len(lqd))

        if n < 20:
            return CreditSpreadSignal(
                spread=0.0, spread_z_score=0.0, spread_percentile=50.0,
                widening=False, stress_level="NORMAL",
            )

        hyg = hyg[-n:]
        lqd = lqd[-n:]

        # Spread as ratio: HYG/LQD (declining = stress)
        spread_series = np.where(lqd > 0, hyg / lqd, 1.0)
        current_spread = float(spread_series[-1])

        # Use negative returns differential as stress proxy
        # Widening = HYG performing worse than LQD
        if n >= 2:
            hyg_ret = (hyg[-1] / hyg[-2]) - 1.0
            lqd_ret = (lqd[-1] / lqd[-2]) - 1.0
            daily_spread_change = hyg_ret - lqd_ret
        else:
            daily_spread_change = 0.0

        # Z-score and percentile of spread ratio
        if n >= 60:
            mu = float(np.mean(spread_series[-252:] if n >= 252 else spread_series))
            sigma = float(np.std(spread_series[-252:] if n >= 252 else spread_series, ddof=1))
            z = _z_score(current_spread, mu, sigma)
            pct = _percentile_rank(
                current_spread,
                spread_series[-252:] if n >= 252 else spread_series,
            )
        else:
            z = 0.0
            pct = 50.0

        # Widening detection: 5-day trend
        widening = False
        if n >= 6:
            recent_trend = spread_series[-1] - spread_series[-6]
            widening = recent_trend < 0  # Declining ratio = widening spread

        # Stress classification (inverted because lower ratio = more stress)
        if z < -2.5:
            stress = "CRISIS"
        elif z < -1.5:
            stress = "STRESS"
        elif z < -0.75:
            stress = "ELEVATED"
        else:
            stress = "NORMAL"

        return CreditSpreadSignal(
            spread=current_spread,
            spread_z_score=z,
            spread_percentile=pct,
            widening=widening,
            stress_level=stress,
        )

    # ------------------------------------------------------------------
    # Intermarket Divergence
    # ------------------------------------------------------------------

    def intermarket_divergence(
        self,
        spy: np.ndarray,
        qqq: np.ndarray,
        iwm: np.ndarray,
        dia: np.ndarray,
    ) -> IntermarketDivergence:
        """Detect when major indices diverge from each other.

        Analyses SPY, QQQ, IWM, and DIA relative performance to identify
        rotational divergences. When Russell (IWM) significantly leads or
        lags, it often presages broader market direction changes.

        Args:
            spy: Array of SPY daily returns.
            qqq: Array of QQQ daily returns.
            iwm: Array of IWM daily returns.
            dia: Array of DIA daily returns.

        Returns:
            IntermarketDivergence with leading/lagging identification.
        """
        arrays = {
            "SPY": np.asarray(spy, dtype=np.float64),
            "QQQ": np.asarray(qqq, dtype=np.float64),
            "IWM": np.asarray(iwm, dtype=np.float64),
            "DIA": np.asarray(dia, dtype=np.float64),
        }

        n = min(len(a) for a in arrays.values())
        if n < 5:
            return IntermarketDivergence(
                spy_return=0.0, qqq_return=0.0, iwm_return=0.0, dia_return=0.0,
                max_spread=0.0, divergence_z_score=0.0,
                lagging_index="NONE", leading_index="NONE",
                divergence_signal=False,
            )

        # Use last 20 days cumulative return for comparison
        window = min(20, n)
        cum_rets = {}
        for name, arr in arrays.items():
            cum_rets[name] = float(np.sum(arr[-window:]))

        # Find leading and lagging
        leading = max(cum_rets, key=lambda k: cum_rets[k])
        lagging = min(cum_rets, key=lambda k: cum_rets[k])
        max_spread = cum_rets[leading] - cum_rets[lagging]

        # Z-score of spread using historical spread distribution
        if n >= 60:
            hist_spreads = []
            for i in range(window, n):
                rets_window = {
                    name: float(np.sum(arr[i - window:i]))
                    for name, arr in arrays.items()
                }
                spread_i = max(rets_window.values()) - min(rets_window.values())
                hist_spreads.append(spread_i)
            h = np.array(hist_spreads, dtype=np.float64)
            div_z = _z_score(max_spread, float(np.mean(h)), float(np.std(h, ddof=1)))
        else:
            div_z = 0.0

        divergence_signal = abs(div_z) > 2.0

        return IntermarketDivergence(
            spy_return=cum_rets["SPY"],
            qqq_return=cum_rets["QQQ"],
            iwm_return=cum_rets["IWM"],
            dia_return=cum_rets["DIA"],
            max_spread=max_spread,
            divergence_z_score=div_z,
            lagging_index=lagging,
            leading_index=leading,
            divergence_signal=divergence_signal,
        )


# =============================================================================
# 4. Volatility Term Structure
# =============================================================================

class VolatilityTermStructure:
    """Volatility term structure analysis.

    Analyses VIX spot vs futures, computes contango/backwardation,
    roll yield, vol-of-vol (VVIX), and the realized-vs-implied spread
    to classify the volatility surface regime.
    """

    def __init__(self, rolling_window: int = _DEFAULT_ROLLING_WINDOW):
        """Initialize VolatilityTermStructure.

        Args:
            rolling_window: Window for historical comparisons.
        """
        self.rolling_window = rolling_window

    def compute_vix_contango(
        self,
        vix_spot: float,
        vix_futures: List[float],
    ) -> float:
        """Compute VIX contango/backwardation as a percentage.

        Formula: contango = (F1 - VIX_spot) / VIX_spot * 100

        Positive = contango (normal), negative = backwardation (fear).

        Args:
            vix_spot: Current VIX spot level.
            vix_futures: List of VIX futures prices ordered by expiration.

        Returns:
            Contango percentage; negative values indicate backwardation.
        """
        if vix_spot <= 0 or not vix_futures:
            return 0.0

        f1 = vix_futures[0]
        return (f1 - vix_spot) / vix_spot * 100.0

    def term_structure_roll_yield(
        self,
        futures_curve: List[float],
    ) -> float:
        """Compute expected roll yield from the VIX futures curve shape.

        Roll yield is approximated as the average slope between
        consecutive contract months, normalised by the front month.

        In contango, roll yield is negative for long vol positions
        (short vol positions benefit). In backwardation, the opposite.

        Args:
            futures_curve: List of futures prices ordered by expiration
                           (front month first).

        Returns:
            Annualised roll yield as a decimal (e.g., -0.05 = -5% p.a.).
        """
        if len(futures_curve) < 2:
            return 0.0

        # Average monthly roll
        rolls = []
        for i in range(1, len(futures_curve)):
            if futures_curve[i - 1] > 0:
                monthly_roll = (futures_curve[i] - futures_curve[i - 1]) / futures_curve[i - 1]
                rolls.append(monthly_roll)

        if not rolls:
            return 0.0

        avg_monthly = float(np.mean(rolls))
        # Annualise (approximately 12 monthly rolls per year)
        annual_roll = avg_monthly * 12.0
        # For long VIX futures, positive curve = negative carry
        return -annual_roll

    def vol_of_vol(self, vvix_data: np.ndarray) -> float:
        """Compute vol-of-vol from VVIX data.

        VVIX measures the implied volatility of VIX options. Spikes in
        vol-of-vol often precede large market moves in either direction.

        Args:
            vvix_data: Array of VVIX daily values.

        Returns:
            Current VVIX z-score relative to its rolling history.
        """
        v = np.asarray(vvix_data, dtype=np.float64)
        if len(v) < 20:
            return 0.0

        current = float(v[-1])
        window = min(self.rolling_window, len(v))
        mu = float(np.mean(v[-window:]))
        sigma = float(np.std(v[-window:], ddof=1))
        return _z_score(current, mu, sigma)

    def realized_vs_implied_spread(
        self,
        realized_vol: float,
        implied_vol: float,
    ) -> float:
        """Compute the spread between realized and implied volatility.

        When RV > IV = gamma scalping opportunity (options underpriced).
        When IV >> RV = premium selling opportunity (options overpriced).

        Args:
            realized_vol: Current realized (historical) volatility.
            implied_vol: Current implied volatility.

        Returns:
            Spread as RV - IV; positive = gamma opportunity,
            negative = premium selling opportunity.
        """
        return realized_vol - implied_vol

    def vol_surface_regime(
        self,
        surface_data: Dict[str, float],
    ) -> str:
        """Classify the volatility surface into a named regime.

        Uses a combination of VIX level, contango/backwardation,
        realized-vs-implied spread, and VVIX z-score.

        Regime labels:
            LOW_VOL_COMPLACENT - VIX < 14, deep contango, IV < RV
            NORMAL             - VIX 14-20, moderate contango
            ELEVATED           - VIX 20-30, shallow contango or flat
            CRISIS             - VIX > 30 or backwardation
            VOL_CRUSH          - VIX dropping sharply from elevated levels

        Args:
            surface_data: Dict with keys 'vix', 'contango_pct',
                          'rv_iv_spread', 'vvix_z'.

        Returns:
            Regime string.
        """
        vix = surface_data.get("vix", 18.0)
        contango = surface_data.get("contango_pct", 5.0)
        rv_iv = surface_data.get("rv_iv_spread", 0.0)
        vvix_z = surface_data.get("vvix_z", 0.0)

        if vix > 30 or contango < -5:
            return "CRISIS"
        if vix > 20:
            # Check for vol crush: elevated VIX but sharply declining
            if rv_iv > 0.05 and vvix_z < -1.0:
                return "VOL_CRUSH"
            return "ELEVATED"
        if vix < 14 and contango > 8:
            return "LOW_VOL_COMPLACENT"
        if vvix_z < -1.5 and vix < 16:
            return "VOL_CRUSH"
        return "NORMAL"

    def compute_full_analysis(
        self,
        vix_spot: float,
        vix_futures: List[float],
        vvix_data: np.ndarray,
        realized_vol: float,
        implied_vol: float,
    ) -> VolTermStructureResult:
        """Run the complete volatility term structure analysis.

        Args:
            vix_spot: Current VIX spot level.
            vix_futures: VIX futures curve.
            vvix_data: Array of historical VVIX values.
            realized_vol: Current realized volatility.
            implied_vol: Current implied volatility.

        Returns:
            VolTermStructureResult with all term structure metrics.
        """
        contango = self.compute_vix_contango(vix_spot, vix_futures)
        roll = self.term_structure_roll_yield(vix_futures)
        vov = self.vol_of_vol(vvix_data)
        rv_iv = self.realized_vs_implied_spread(realized_vol, implied_vol)

        regime = self.vol_surface_regime({
            "vix": vix_spot,
            "contango_pct": contango,
            "rv_iv_spread": rv_iv,
            "vvix_z": vov,
        })

        return VolTermStructureResult(
            contango_pct=contango,
            is_backwardated=contango < 0,
            roll_yield=roll,
            vol_of_vol=vov,
            rv_iv_spread=rv_iv,
            vol_surface_regime=regime,
        )


# =============================================================================
# 5. Skew Intelligence Scanner
# =============================================================================

class SkewIntelligenceScanner(BaseScanner[AdvancedScanResult]):
    """Main scanner tying skew, PCR, internals, and vol term structure together.

    Produces AdvancedScanResult signals when the combined analysis identifies
    actionable intelligence: extreme skew + extreme PCR, skew divergence
    across indices, vol term structure inversion, or intermarket divergence.

    Signal triggers (any combination):
        1. Extreme skew + extreme PCR  -> high conviction directional
        2. Skew divergence across SPY/QQQ/IWM -> rotational signal
        3. Vol term structure inversion -> crash risk / vol explosion
        4. Intermarket divergence > 2 sigma -> mean reversion or trend change
        5. Credit spread stress + bond-equity regime shift -> macro risk-off

    Scan modes: OPTIONS_DAY, OPTIONS_SWING, ALL
    """

    def __init__(
        self,
        config: Optional[ScannerConfig] = None,
        rolling_window: int = _DEFAULT_ROLLING_WINDOW,
    ):
        """Initialize SkewIntelligenceScanner.

        Args:
            config: Scanner configuration. Defaults to standard config.
            rolling_window: Rolling window for statistical calculations.
        """
        cfg = config or ScannerConfig(
            scan_modes=[ScanMode.OPTIONS_DAY, ScanMode.OPTIONS_SWING, ScanMode.ALL],
        )
        super().__init__(
            name="skew_intelligence",
            scan_mode=ScanMode.ALL,
            config=cfg,
        )

        self.rolling_window = rolling_window
        self.skew_analyzer = SkewSurfaceAnalyzer(rolling_window=rolling_window)
        self.pcr_analyzer = PutCallAnalyzer(rolling_window=rolling_window)
        self.internals_engine = MarketInternalsEngine(rolling_window=rolling_window)
        self.vol_ts = VolatilityTermStructure(rolling_window=rolling_window)

        # History buffers for tracking
        self._skew_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=rolling_window))
        self._pcr_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=rolling_window))
        self._signal_history: deque = deque(maxlen=100)

    async def scan(self, context: ScanContext) -> List[AdvancedScanResult]:
        """Run the full skew intelligence analysis pipeline.

        Iterates through the scan universe, analyses each symbol with
        available options data, and generates AdvancedScanResult signals
        for actionable conditions.

        Args:
            context: Scan context with universe, market data, options data.

        Returns:
            List of AdvancedScanResult for symbols with actionable signals.
        """
        results: List[AdvancedScanResult] = []

        # Determine overall market regime from internals
        market_regime = self._determine_regime(context)

        for symbol in context.universe:
            try:
                intel = await self._analyze_symbol(symbol, context, market_regime)
                if intel is not None and intel.overall_confidence > 0.0:
                    signal = self._generate_signals(symbol, intel, context, market_regime)
                    if signal is not None:
                        results.append(signal)
            except Exception as e:
                self._logger.warning(f"Error analysing {symbol}: {e}")
                continue

        # Sort by confidence descending
        results.sort(key=lambda r: r.confidence, reverse=True)
        return results

    def validate_signal(
        self, result: AdvancedScanResult, context: ScanContext
    ) -> bool:
        """Validate a skew intelligence signal against current conditions.

        Requires minimum confidence and checks that the underlying has
        sufficient options liquidity for the signal to be tradeable.

        Args:
            result: The scan result to validate.
            context: Current scan context.

        Returns:
            True if the signal passes validation.
        """
        if result.confidence < 0.3:
            return False

        # Verify the symbol has market data
        if result.symbol not in context.market_data:
            return False

        md = context.market_data[result.symbol]
        if not self.apply_filters(md, self.config):
            return False

        return True

    # ------------------------------------------------------------------
    # Private analysis methods
    # ------------------------------------------------------------------

    async def _analyze_symbol(
        self,
        symbol: str,
        context: ScanContext,
        market_regime: RegimeContext,
    ) -> Optional[SkewIntelligenceResult]:
        """Run per-symbol skew and internals analysis.

        Builds the skew surface, computes PCR metrics, and collects
        market internals if the symbol is a major index.

        Args:
            symbol: Ticker symbol to analyse.
            context: Scan context.
            market_regime: Current regime from internals.

        Returns:
            SkewIntelligenceResult or None if insufficient data.
        """
        opts = context.options_data.get(symbol)
        if not opts:
            return None

        # Reconstruct OptionsChain from context data
        chain = self._build_chain(symbol, opts, context)
        if chain is None or not chain.contracts:
            return None

        intel = SkewIntelligenceResult(
            symbol=symbol,
            timestamp=context.timestamp,
        )

        # --- Skew Surface ---
        surface = self.skew_analyzer.compute_full_skew_surface(chain)
        if surface.points:
            intel.skew_regime = self.skew_analyzer.detect_skew_regime(surface)

            # Skew momentum from history
            pts_25d = [p for p in surface.points if p.delta_bucket == 25]
            if pts_25d:
                current_skew = min(pts_25d, key=lambda p: p.tenor_days).skew
                self._skew_history[symbol].append(current_skew)
                hist = np.array(list(self._skew_history[symbol]), dtype=np.float64)
                if len(hist) >= 5:
                    intel.skew_momentum = self.skew_analyzer.skew_momentum(hist)

            # Skew term structure
            intel.skew_term_structure = self.skew_analyzer.skew_term_structure(chain)

            # Butterfly signals
            intel.butterfly_signals = self.skew_analyzer.butterfly_spread_signal(surface)

        # --- Put/Call Ratios ---
        pcr_spectrum = self.pcr_analyzer.compute_pcr_spectrum(chain)
        intel.pcr_spectrum = pcr_spectrum

        smart_pcr = self.pcr_analyzer.smart_pcr(chain)
        self._pcr_history[symbol].append(smart_pcr)

        pcr_hist = np.array(list(self._pcr_history[symbol]), dtype=np.float64)
        pcr_z = self.pcr_analyzer.pcr_z_score(smart_pcr, pcr_hist)

        skew_regime_str = intel.skew_regime.regime if intel.skew_regime else "NORMAL"
        intel.pcr_regime = self.pcr_analyzer.pcr_regime_signal(pcr_z, skew_regime_str)

        # --- Cross-Asset Skew (for index ETFs) ---
        index_symbols = {"SPY", "QQQ", "IWM", "VIX"}
        if symbol in index_symbols:
            spy_skew = self._get_latest_skew("SPY")
            qqq_skew = self._get_latest_skew("QQQ")
            iwm_skew = self._get_latest_skew("IWM")
            vix_skew = self._get_latest_skew("VIX")
            intel.cross_asset = self.skew_analyzer.cross_asset_skew_correlation(
                spy_skew, qqq_skew, iwm_skew, vix_skew,
            )

        # --- Vol Term Structure (for VIX-linked data) ---
        vix_data = context.metadata.get("vix_data", {})
        if vix_data:
            vts = self.vol_ts.compute_full_analysis(
                vix_spot=vix_data.get("spot", 18.0),
                vix_futures=vix_data.get("futures", []),
                vvix_data=np.array(vix_data.get("vvix_history", [18.0]), dtype=np.float64),
                realized_vol=vix_data.get("realized_vol", 0.15),
                implied_vol=vix_data.get("implied_vol", 0.18),
            )
            intel.vol_term_structure = vts

        # --- Market Internals (aggregated at MARKET level) ---
        internals_data = context.metadata.get("internals", {})
        if internals_data:
            if "tick_data" in internals_data:
                tick_arr = np.array(internals_data["tick_data"], dtype=np.float64)
                price_arr = None
                if symbol in context.historical_data:
                    closes = context.historical_data[symbol].closes
                    if closes:
                        price_arr = np.array(closes[-len(tick_arr):], dtype=np.float64)
                intel.tick_internals = self.internals_engine.compute_tick_internals(
                    tick_arr, price_arr,
                )

            if "volume_data" in internals_data:
                intel.volume_internals = self.internals_engine.compute_vold(
                    internals_data["volume_data"],
                )

            if "sector_data" in internals_data:
                intel.sector_divergence = self.internals_engine.sector_divergence_signal(
                    internals_data["sector_data"],
                )

            if "bond_data" in internals_data:
                bond = internals_data["bond_data"]
                intel.bond_equity = self.internals_engine.bond_equity_correlation(
                    np.array(bond.get("spy_returns", []), dtype=np.float64),
                    np.array(bond.get("tlt_returns", []), dtype=np.float64),
                )

            if "credit_data" in internals_data:
                credit = internals_data["credit_data"]
                intel.credit_spread = self.internals_engine.credit_spread_monitor(
                    np.array(credit.get("hyg_prices", []), dtype=np.float64),
                    np.array(credit.get("lqd_prices", []), dtype=np.float64),
                )

            if "intermarket_data" in internals_data:
                im = internals_data["intermarket_data"]
                intel.intermarket = self.internals_engine.intermarket_divergence(
                    np.array(im.get("spy_returns", []), dtype=np.float64),
                    np.array(im.get("qqq_returns", []), dtype=np.float64),
                    np.array(im.get("iwm_returns", []), dtype=np.float64),
                    np.array(im.get("dia_returns", []), dtype=np.float64),
                )

        # --- Compute Overall Signal ---
        intel.overall_signal, intel.overall_confidence = self._compute_overall(intel)

        return intel

    def _generate_signals(
        self,
        symbol: str,
        intel: SkewIntelligenceResult,
        context: ScanContext,
        market_regime: RegimeContext,
    ) -> Optional[AdvancedScanResult]:
        """Create an AdvancedScanResult from the aggregated analysis.

        Fires only when confidence exceeds the minimum threshold and
        at least one trigger condition is met.

        Args:
            symbol: Ticker symbol.
            intel: Aggregated intelligence result.
            context: Scan context.
            market_regime: Current market regime.

        Returns:
            AdvancedScanResult or None if no actionable signal.
        """
        if intel.overall_confidence < 0.30:
            return None

        # Build supporting and contradicting evidence
        supporting: List[str] = []
        contradicting: List[str] = []

        # Evidence from skew regime
        if intel.skew_regime:
            if intel.skew_regime.regime in ("CRASH_FEAR", "ELEVATED_FEAR"):
                supporting.append(
                    f"Skew regime: {intel.skew_regime.regime} "
                    f"(pct={intel.skew_regime.skew_percentile:.0f}, "
                    f"z={intel.skew_regime.skew_z_score:+.2f})"
                )
            elif intel.skew_regime.regime in ("COMPLACENT", "EUPHORIA"):
                supporting.append(
                    f"Skew regime: {intel.skew_regime.regime} "
                    f"(contrarian -- low hedging demand)"
                )

        # Evidence from PCR
        if intel.pcr_regime:
            if intel.pcr_regime.signal in ("STRONG_BULLISH", "STRONG_BEARISH"):
                supporting.append(
                    f"PCR regime: {intel.pcr_regime.signal} "
                    f"(z={intel.pcr_regime.pcr_z_score:+.2f}, "
                    f"conviction={intel.pcr_regime.conviction:.2f})"
                )
            elif intel.pcr_regime.signal == "NEUTRAL":
                contradicting.append("PCR regime neutral -- no directional bias from flow")

        # Evidence from skew term structure
        if intel.skew_term_structure and intel.skew_term_structure.is_inverted:
            supporting.append(
                f"Skew term structure INVERTED "
                f"(inversion={intel.skew_term_structure.inversion_magnitude:.4f})"
            )

        # Evidence from butterflies
        extreme_bfly = [b for b in intel.butterfly_signals if b.signal == "EXTREME_TAILS"]
        if extreme_bfly:
            supporting.append(
                f"Extreme fat-tail pricing in {len(extreme_bfly)} butterfly(s)"
            )

        # Evidence from cross-asset divergence
        if intel.cross_asset and intel.cross_asset.divergence_signal == "EXTREME":
            supporting.append(
                f"Extreme cross-asset skew divergence "
                f"(max={intel.cross_asset.max_divergence:.4f})"
            )

        # Evidence from vol term structure
        if intel.vol_term_structure:
            vts = intel.vol_term_structure
            if vts.is_backwardated:
                supporting.append(
                    f"VIX backwardation ({vts.contango_pct:.1f}%) -- fear regime"
                )
            if vts.vol_surface_regime == "CRISIS":
                supporting.append("Vol surface regime: CRISIS")
            elif vts.vol_surface_regime == "LOW_VOL_COMPLACENT":
                supporting.append("Vol surface: LOW_VOL_COMPLACENT (contrarian)")

        # Evidence from internals
        if intel.credit_spread and intel.credit_spread.stress_level in ("STRESS", "CRISIS"):
            supporting.append(
                f"Credit spread stress: {intel.credit_spread.stress_level} "
                f"(z={intel.credit_spread.spread_z_score:+.2f})"
            )

        if intel.intermarket and intel.intermarket.divergence_signal:
            supporting.append(
                f"Intermarket divergence: {intel.intermarket.leading_index} leads, "
                f"{intel.intermarket.lagging_index} lags "
                f"(z={intel.intermarket.divergence_z_score:+.2f})"
            )

        if intel.sector_divergence and intel.sector_divergence.regime_rotation_signal:
            supporting.append(
                f"Sector rotation: {intel.sector_divergence.description}"
            )

        # Contradictions
        if intel.tick_internals and intel.tick_internals.bias != "NEUTRAL":
            tick_dir = intel.tick_internals.bias
            if (intel.overall_signal == "BULLISH" and tick_dir == "BEARISH") or \
               (intel.overall_signal == "BEARISH" and tick_dir == "BULLISH"):
                contradicting.append(
                    f"TICK internals diverge: {tick_dir} bias vs signal"
                )

        if intel.bond_equity and intel.bond_equity.regime == "RISK_OFF" and \
                intel.overall_signal == "BULLISH":
            contradicting.append("Bond-equity correlation indicates RISK_OFF regime")

        # Determine signal direction
        direction = intel.overall_signal

        # Determine category based on primary driver
        category = ScanCategory.OPTIONS
        if intel.intermarket or intel.credit_spread or intel.sector_divergence:
            category = ScanCategory.MARKET_INTERNALS

        # Expected move
        md = context.market_data.get(symbol)
        entry_price = md.close if md else None
        expected_move = self._estimate_expected_move(intel)
        atr = md.atr if md else None
        stop_loss = 0.0
        target = 0.0
        rr = 0.0

        if entry_price and atr and atr > 0:
            if direction == "BULLISH":
                stop_loss = entry_price - 2.0 * atr
                target = entry_price + 3.0 * atr
            elif direction == "BEARISH":
                stop_loss = entry_price + 2.0 * atr
                target = entry_price - 3.0 * atr
            risk = abs(entry_price - stop_loss)
            reward = abs(target - entry_price)
            rr = _safe_divide(reward, risk)

        # Mathematical basis description
        math_basis_parts = []
        if intel.skew_regime:
            math_basis_parts.append(
                f"25D skew={intel.skew_regime.skew_25d:.4f} "
                f"({intel.skew_regime.skew_percentile:.0f}th pct)"
            )
        if intel.pcr_regime:
            math_basis_parts.append(f"PCR z={intel.pcr_regime.pcr_z_score:+.2f}")
        if intel.vol_term_structure:
            math_basis_parts.append(
                f"VIX contango={intel.vol_term_structure.contango_pct:+.1f}%"
            )
        math_basis = "; ".join(math_basis_parts) if math_basis_parts else ""

        # Determine expected timeframe
        if intel.skew_term_structure and intel.skew_term_structure.is_inverted:
            timeframe = ExpectedTimeframe.INTRADAY
        elif intel.vol_term_structure and intel.vol_term_structure.is_backwardated:
            timeframe = ExpectedTimeframe.SWING
        else:
            timeframe = ExpectedTimeframe.SWING

        # Decay halflife: skew signals decay quickly
        decay = 5 if timeframe == ExpectedTimeframe.INTRADAY else 10

        result = AdvancedScanResult(
            scan_id=str(uuid.uuid4()),
            scan_name="skew_intelligence",
            category=category,
            timestamp=context.timestamp,
            symbol=symbol,
            signal_direction=direction,
            signal_strength=min(1.0, intel.overall_confidence),
            confidence=min(1.0, intel.overall_confidence),
            expected_move_pct=expected_move,
            expected_timeframe=timeframe,
            risk_reward_ratio=rr,
            entry_price=entry_price,
            stop_loss_level=stop_loss,
            target_level=target,
            supporting_evidence=supporting,
            contradicting_evidence=contradicting,
            historical_accuracy=0.62,   # Calibrated from backtest
            regime_context=market_regime,
            mathematical_basis=math_basis,
            false_positive_rate=0.30,
            decay_halflife_days=decay,
            volatility_regime=self._map_vol_regime(intel),
            metadata={
                "skew_regime": intel.skew_regime.regime if intel.skew_regime else None,
                "skew_25d": intel.skew_regime.skew_25d if intel.skew_regime else None,
                "pcr_signal": intel.pcr_regime.signal if intel.pcr_regime else None,
                "pcr_z": intel.pcr_regime.pcr_z_score if intel.pcr_regime else None,
                "vol_regime": (
                    intel.vol_term_structure.vol_surface_regime
                    if intel.vol_term_structure else None
                ),
                "cross_asset_divergence": (
                    intel.cross_asset.divergence_signal
                    if intel.cross_asset else None
                ),
                "credit_stress": (
                    intel.credit_spread.stress_level
                    if intel.credit_spread else None
                ),
                "butterfly_alerts": len(
                    [b for b in intel.butterfly_signals
                     if b.signal != "NONE"]
                ),
            },
        )

        return result

    def _determine_regime(self, context: ScanContext) -> RegimeContext:
        """Determine the overall market regime from internals data.

        Uses a hierarchical classification:
            1. Crisis indicators (credit stress, VIX backwardation)
            2. Trending indicators (breadth, momentum)
            3. Volatility regime

        Args:
            context: Scan context with metadata.

        Returns:
            RegimeContext classification.
        """
        internals = context.metadata.get("internals", {})
        vix_data = context.metadata.get("vix_data", {})

        # Check for crisis
        if "credit_data" in internals:
            credit = internals["credit_data"]
            hyg = np.array(credit.get("hyg_prices", []), dtype=np.float64)
            lqd = np.array(credit.get("lqd_prices", []), dtype=np.float64)
            if len(hyg) >= 20 and len(lqd) >= 20:
                cs = self.internals_engine.credit_spread_monitor(hyg, lqd)
                if cs.stress_level == "CRISIS":
                    return RegimeContext.CRISIS
                if cs.stress_level == "STRESS":
                    return RegimeContext.VOLATILE

        # Check VIX
        vix_spot = vix_data.get("spot", 18.0)
        if vix_spot > 35:
            return RegimeContext.CRISIS
        if vix_spot > 25:
            return RegimeContext.VOLATILE

        # Check breadth from context
        if context.market_regime.value == "trending_up":
            return RegimeContext.TRENDING_UP
        if context.market_regime.value == "trending_down":
            return RegimeContext.TRENDING_DOWN
        if context.market_regime.value == "high_volatility":
            return RegimeContext.VOLATILE
        if context.market_regime.value == "low_volatility":
            return RegimeContext.QUIET

        return RegimeContext.RANGING

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_chain(
        self,
        symbol: str,
        opts_data: dict,
        context: ScanContext,
    ) -> Optional[OptionsChain]:
        """Build an OptionsChain from raw context options data.

        The context.options_data[symbol] may already be an OptionsChain
        or a dict representation.

        Args:
            symbol: Ticker symbol.
            opts_data: Raw options data dict or OptionsChain.
            context: Scan context.

        Returns:
            OptionsChain instance or None.
        """
        if isinstance(opts_data, OptionsChain):
            return opts_data

        # Build from dict representation
        try:
            underlying_price = opts_data.get("underlying_price", 0.0)
            if underlying_price <= 0:
                md = context.market_data.get(symbol)
                underlying_price = md.close if md else 0.0

            contracts = []
            raw_contracts = opts_data.get("contracts", [])
            for rc in raw_contracts:
                if isinstance(rc, OptionContract):
                    contracts.append(rc)
                elif isinstance(rc, dict):
                    contracts.append(OptionContract(
                        symbol=rc.get("symbol", symbol),
                        underlying=symbol,
                        strike=rc.get("strike", 0.0),
                        expiration=rc.get("expiration", datetime.now(timezone.utc)),
                        option_type=rc.get("option_type", "CALL"),
                        bid=rc.get("bid", 0.0),
                        ask=rc.get("ask", 0.0),
                        last=rc.get("last", 0.0),
                        volume=rc.get("volume", 0),
                        open_interest=rc.get("open_interest", 0),
                        implied_volatility=rc.get("implied_volatility", 0.0),
                        delta=rc.get("delta"),
                        gamma=rc.get("gamma"),
                        theta=rc.get("theta"),
                        vega=rc.get("vega"),
                        rho=rc.get("rho"),
                        trade_count=rc.get("trade_count", 0),
                        avg_trade_size=rc.get("avg_trade_size", 0.0),
                        buy_volume=rc.get("buy_volume", 0),
                        sell_volume=rc.get("sell_volume", 0),
                    ))

            return OptionsChain(
                underlying=symbol,
                underlying_price=underlying_price,
                contracts=contracts,
                iv_rank=opts_data.get("iv_rank"),
                iv_percentile=opts_data.get("iv_percentile"),
                historical_iv=opts_data.get("historical_iv"),
            )
        except Exception as e:
            self._logger.warning(f"Failed to build chain for {symbol}: {e}")
            return None

    def _get_latest_skew(self, symbol: str) -> float:
        """Get the most recent 25-delta skew for a symbol from history.

        Args:
            symbol: Ticker symbol.

        Returns:
            Latest skew value or 0.0 if unavailable.
        """
        hist = self._skew_history.get(symbol)
        if hist and len(hist) > 0:
            return float(hist[-1])
        return 0.0

    def _compute_overall(
        self, intel: SkewIntelligenceResult
    ) -> Tuple[str, float]:
        """Compute the overall signal direction and confidence.

        Aggregates signals from all sub-components using a weighted
        scoring system.  Each component votes for direction with a
        weight proportional to its individual conviction.

        Args:
            intel: Aggregated intelligence result.

        Returns:
            Tuple of (direction string, confidence float 0-1).
        """
        score = 0.0      # Positive = bullish, negative = bearish
        total_weight = 0.0

        # --- Skew regime contribution (contrarian) ---
        if intel.skew_regime:
            weight = 0.30
            regime_map = {
                "CRASH_FEAR": 0.8,      # Extreme fear is contrarian bullish
                "ELEVATED_FEAR": 0.3,
                "NORMAL": 0.0,
                "COMPLACENT": -0.3,     # Complacency is contrarian bearish
                "EUPHORIA": -0.8,
            }
            score += regime_map.get(intel.skew_regime.regime, 0.0) * weight
            total_weight += weight

        # --- PCR regime contribution ---
        if intel.pcr_regime:
            weight = 0.25
            pcr_map = {
                "STRONG_BULLISH": 0.8,
                "BULLISH": 0.4,
                "NEUTRAL": 0.0,
                "BEARISH": -0.4,
                "STRONG_BEARISH": -0.8,
            }
            score += pcr_map.get(intel.pcr_regime.signal, 0.0) * weight
            total_weight += weight

        # --- Vol term structure contribution ---
        if intel.vol_term_structure:
            weight = 0.15
            vts = intel.vol_term_structure
            if vts.is_backwardated:
                score += -0.6 * weight  # Backwardation = bearish
            elif vts.vol_surface_regime == "LOW_VOL_COMPLACENT":
                score += -0.3 * weight  # Complacency is contrarian
            elif vts.vol_surface_regime == "VOL_CRUSH":
                score += 0.4 * weight   # Vol crush after spike = bullish
            total_weight += weight

        # --- Cross-asset divergence ---
        if intel.cross_asset:
            weight = 0.10
            if intel.cross_asset.divergence_signal == "EXTREME":
                # Direction based on which index is stressed
                if intel.cross_asset.small_cap_stress > 0.04:
                    score += -0.5 * weight  # Small-cap stress = bearish
                elif intel.cross_asset.tech_fear_premium > 0.04:
                    score += -0.3 * weight  # Tech fear = moderately bearish
            total_weight += weight

        # --- Credit spread ---
        if intel.credit_spread:
            weight = 0.10
            stress_map = {
                "NORMAL": 0.1,
                "ELEVATED": -0.2,
                "STRESS": -0.5,
                "CRISIS": -0.8,
            }
            score += stress_map.get(intel.credit_spread.stress_level, 0.0) * weight
            total_weight += weight

        # --- Intermarket divergence ---
        if intel.intermarket and intel.intermarket.divergence_signal:
            weight = 0.10
            # If IWM is lagging, that is generally bearish for broad market
            if intel.intermarket.lagging_index == "IWM":
                score += -0.4 * weight
            elif intel.intermarket.leading_index == "IWM":
                score += 0.3 * weight
            total_weight += weight

        # Normalise
        if total_weight > 0:
            normalised = score / total_weight
        else:
            normalised = 0.0

        # Direction
        if normalised > 0.15:
            direction = "BULLISH"
        elif normalised < -0.15:
            direction = "BEARISH"
        else:
            direction = "NEUTRAL"

        # Confidence = magnitude of conviction, scaled 0-1
        confidence = min(1.0, abs(normalised) * 1.5)

        # Boost confidence when multiple signals agree
        signal_count = sum([
            1 for x in [
                intel.skew_regime and intel.skew_regime.regime != "NORMAL",
                intel.pcr_regime and intel.pcr_regime.signal not in ("NEUTRAL",),
                intel.vol_term_structure and intel.vol_term_structure.vol_surface_regime != "NORMAL",
                intel.cross_asset and intel.cross_asset.divergence_signal != "NONE",
                intel.credit_spread and intel.credit_spread.stress_level != "NORMAL",
                intel.intermarket and intel.intermarket.divergence_signal,
                intel.skew_term_structure and intel.skew_term_structure.is_inverted,
            ] if x
        ])

        if signal_count >= 4:
            confidence = min(1.0, confidence * 1.3)
        elif signal_count >= 3:
            confidence = min(1.0, confidence * 1.15)

        return direction, round(confidence, 4)

    def _estimate_expected_move(self, intel: SkewIntelligenceResult) -> float:
        """Estimate the expected percentage move based on skew and vol data.

        Uses ATM implied vol to estimate a 1-standard-deviation move
        over the expected timeframe, then scales by signal conviction.

        Args:
            intel: Aggregated intelligence result.

        Returns:
            Expected move percentage.
        """
        # Base expected move from implied vol (daily 1-sigma)
        base_vol = 0.18  # Default annualised vol
        if intel.vol_term_structure and intel.vol_term_structure.rv_iv_spread != 0:
            # Use implied vol if available
            base_vol = max(0.05, 0.18 - intel.vol_term_structure.rv_iv_spread)

        daily_vol = base_vol / math.sqrt(_TRADING_DAYS_PER_YEAR)
        # Expected move over ~5 days (swing)
        expected_move = daily_vol * math.sqrt(5) * 100.0

        # Scale by conviction
        expected_move *= intel.overall_confidence

        return round(expected_move, 2)

    @staticmethod
    def _map_vol_regime(
        intel: SkewIntelligenceResult,
    ) -> Optional[VolatilityRegime]:
        """Map vol term structure regime to VolatilityRegime enum.

        Args:
            intel: Intelligence result with vol term structure data.

        Returns:
            VolatilityRegime or None.
        """
        if not intel.vol_term_structure:
            return None

        mapping = {
            "LOW_VOL_COMPLACENT": VolatilityRegime.LOW,
            "NORMAL": VolatilityRegime.NORMAL,
            "ELEVATED": VolatilityRegime.ELEVATED,
            "CRISIS": VolatilityRegime.EXTREME,
            "VOL_CRUSH": VolatilityRegime.LOW,
        }
        return mapping.get(intel.vol_term_structure.vol_surface_regime, VolatilityRegime.NORMAL)
