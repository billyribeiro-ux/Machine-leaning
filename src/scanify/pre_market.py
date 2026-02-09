"""
SCANIFY Pre-Market Scanner and Session Classifier for the 0DTE SPX system.

Runs at 9:00 AM ET to set up the session before market open. Performs:
  - Overnight gap analysis (ES pre-market vs prior SPX close)
  - Blended expected-move envelope calculation (VIX1D, straddle, RV-adjusted)
  - Key support/resistance level identification (prior session, overnight, GEX placeholders)
  - Economic event risk assessment with suspend-window scheduling
  - Session type classification (TRENDING / RANGE / VOLATILE / SQUEEZE / EVENT)

The resulting :class:`SessionSetup` is consumed by downstream scanners, the
GEX engine, and the risk manager for the remainder of the trading day.
"""

from dataclasses import dataclass, field
from datetime import datetime, time
from enum import Enum
from typing import Dict, List, Optional, Tuple
import math
import numpy as np

from .config import SessionType, ScanifyConfig, TimeZone
from .data_feeds import (
    OptionsChain, PriorSessionData, VIXData, EconomicEvent,
    SPXPriceBar, VIX1DAnalyzer, ImpactLevel
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class GapClassification(Enum):
    """Overnight gap size classification based on sigma-normalised magnitude.

    Boundaries (absolute gap in standard deviations of daily realised vol):
        MICRO  — < 0.3 sigma
        SMALL  — 0.3 to 0.7 sigma
        MEDIUM — 0.7 to 1.5 sigma
        LARGE  — 1.5 to 2.5 sigma
        MEGA   — > 2.5 sigma
    """
    MICRO = "micro"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    MEGA = "mega"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class GapAnalysis:
    """Result of overnight gap analysis relative to the prior SPX close.

    Attributes:
        gap_pct: Gap expressed as a percentage of the prior close.
        gap_points: Raw gap in SPX index points (ES pre-market minus SPX close).
        gap_sigma: Gap normalised by the 1-day realised-vol standard deviation.
        classification: Gap size bucket as a GapClassification enum value.
        gap_fill_probability: Estimated cumulative probability that the gap
            fills by the indicated time, keyed by ``"11AM"``, ``"1PM"``,
            ``"3PM"``, and ``"close"``.
        direction: Direction of the gap: ``"up"`` or ``"down"``.
    """
    gap_pct: float
    gap_points: float
    gap_sigma: float
    classification: GapClassification
    gap_fill_probability: Dict[str, float] = field(default_factory=dict)
    direction: str = "up"


@dataclass
class ExpectedMove:
    """Blended expected-move envelope for the session.

    Contains the composite 1-sigma and 2-sigma boundaries as well as the
    individual method contributions and supporting volatility metrics.

    Attributes:
        em_1sigma: Blended 1-sigma expected move in SPX points (plus/minus).
        em_2sigma: Blended 2-sigma expected move in SPX points (plus/minus).
        upper_1sigma: Absolute SPX price at +1 sigma.
        lower_1sigma: Absolute SPX price at -1 sigma.
        upper_2sigma: Absolute SPX price at +2 sigma.
        lower_2sigma: Absolute SPX price at -2 sigma.
        method_vix1d: VIX1D-derived 1-sigma expected move (Method 1).
        method_straddle: ATM straddle-derived expected move (Method 2).
        method_rv_adjusted: Realised-vol-adjusted expected move (Method 3).
        iv_rv_ratio: Current implied-volatility / realised-volatility ratio.
        vol_regime: Volatility regime label from VIX1DAnalyzer (e.g. ``"normal"``).
    """
    em_1sigma: float
    em_2sigma: float
    upper_1sigma: float
    lower_1sigma: float
    upper_2sigma: float
    lower_2sigma: float
    method_vix1d: float
    method_straddle: float
    method_rv_adjusted: float
    iv_rv_ratio: float
    vol_regime: str


@dataclass
class KeyLevels:
    """Composite map of options-structure and price-action reference levels.

    GEX-derived levels (max_pain through transition_zone) are initialised to
    placeholder values (0.0) by the pre-market scanner and are expected to be
    populated later by the GEX engine once the full chain is available.

    Attributes:
        max_pain: Strike where aggregate open-interest expires with maximum loss.
        plus_gex: Strike with the largest positive dealer gamma above spot.
        minus_gex: Strike with the largest negative dealer gamma below spot.
        call_wall: Strike with the highest call open interest.
        put_wall: Strike with the highest put open interest.
        gamma_flip: Interpolated level where net dealer gamma crosses zero.
        transition_zone: Lower and upper bounds of the balanced gamma band.
        prior_high: Prior session SPX high.
        prior_low: Prior session SPX low.
        prior_close: Prior session SPX close.
        prior_vwap: Prior session volume-weighted average price.
        overnight_high: Overnight ES futures session high.
        overnight_low: Overnight ES futures session low.
        round_levels: Nearest SPX round-number levels at $50 and $100 increments.
        value_area_high: Upper boundary of the prior session's value area.
        value_area_low: Lower boundary of the prior session's value area.
    """
    max_pain: float
    plus_gex: float
    minus_gex: float
    call_wall: float
    put_wall: float
    gamma_flip: float
    transition_zone: Tuple[float, float]
    prior_high: float
    prior_low: float
    prior_close: float
    prior_vwap: float
    overnight_high: float
    overnight_low: float
    round_levels: List[float] = field(default_factory=list)
    value_area_high: float = 0.0
    value_area_low: float = 0.0


@dataclass
class EventRisk:
    """Scheduled economic-event risk assessment for the session.

    Attributes:
        events_today: Full economic calendar for the day.
        high_impact_events: Subset of events with HIGH impact level.
        is_fomc_day: True when an FOMC announcement is scheduled.
        is_cpi_day: True when CPI data is released today.
        is_nfp_day: True when Non-Farm Payrolls data is released today.
        suspend_windows: Time windows during which signal generation should
            be paused, each as ``(start_time, end_time)`` in Eastern time.
        risk_level: Overall session risk classification
            (``"low"`` / ``"medium"`` / ``"high"`` / ``"extreme"``).
    """
    events_today: List[EconomicEvent] = field(default_factory=list)
    high_impact_events: List[EconomicEvent] = field(default_factory=list)
    is_fomc_day: bool = False
    is_cpi_day: bool = False
    is_nfp_day: bool = False
    suspend_windows: List[Tuple[time, time]] = field(default_factory=list)
    risk_level: str = "low"


@dataclass
class SessionSetup:
    """Complete pre-market session setup produced at 9:00 AM ET.

    This is the primary output of :meth:`PreMarketScanner.run_pre_market_scan`
    and is consumed by the downstream intraday scanners and the risk manager.

    Attributes:
        timestamp: Time the setup was generated.
        session_type: Classified session regime.
        gap_analysis: Overnight gap analysis results.
        expected_move: Blended expected-move envelope.
        key_levels: Composite support/resistance map.
        event_risk: Economic event risk assessment.
        scanner_mode: Recommended scanner operating mode description.
        notes: List of human-readable session notes and recommendations.
    """
    timestamp: datetime
    session_type: SessionType
    gap_analysis: GapAnalysis
    expected_move: ExpectedMove
    key_levels: KeyLevels
    event_risk: EventRisk
    scanner_mode: str = "NEUTRAL"
    notes: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Gap fill probability model — historical base rates by classification
# ---------------------------------------------------------------------------

# Cumulative gap-fill probabilities at (11AM, 1PM, 3PM, close).
# Derived from historical SPX gap-fill studies. Smaller gaps fill with much
# higher frequency; probability accumulates throughout the session.

_GAP_FILL_PROBABILITIES: Dict[GapClassification, Tuple[float, float, float, float]] = {
    GapClassification.MICRO:  (0.80, 0.85, 0.90, 0.92),
    GapClassification.SMALL:  (0.65, 0.72, 0.78, 0.82),
    GapClassification.MEDIUM: (0.45, 0.55, 0.62, 0.68),
    GapClassification.LARGE:  (0.25, 0.35, 0.42, 0.50),
    GapClassification.MEGA:   (0.10, 0.18, 0.25, 0.32),
}

_GAP_FILL_TIME_KEYS: Tuple[str, str, str, str] = ("11AM", "1PM", "3PM", "close")


# ---------------------------------------------------------------------------
# PreMarketScanner
# ---------------------------------------------------------------------------

class PreMarketScanner:
    """Runs the full pre-market analysis suite at 9:00 AM ET.

    Produces a :class:`SessionSetup` that classifies the upcoming trading day
    and initialises key reference levels for the intraday scanners.

    Parameters
    ----------
    config : ScanifyConfig
        Master SCANIFY configuration instance.
    """

    def __init__(self, config: ScanifyConfig) -> None:
        self.config = config
        self._vix1d_analyzer = VIX1DAnalyzer()

    # ------------------------------------------------------------------
    # Gap analysis
    # ------------------------------------------------------------------

    def analyze_gap(
        self,
        es_premarket_price: float,
        prior_session: PriorSessionData,
    ) -> GapAnalysis:
        """Analyse the overnight gap between ES pre-market and the prior SPX close.

        Gap sigma is computed as::

            gap_sigma = |gap_points| / (prior_rv_20d * SPX_close / sqrt(252))

        Classification boundaries (from ScanifyConfig):
            - MICRO:  < 0.3 sigma
            - SMALL:  0.3 - 0.7 sigma
            - MEDIUM: 0.7 - 1.5 sigma
            - LARGE:  1.5 - 2.5 sigma
            - MEGA:   > 2.5 sigma

        Gap fill probabilities are drawn from historical base rates that
        vary by classification and accumulate through the session.

        Parameters
        ----------
        es_premarket_price : float
            Current E-mini S&P 500 futures price observed pre-market.
        prior_session : PriorSessionData
            Reference levels from the prior trading session.

        Returns
        -------
        GapAnalysis
            Fully populated gap analysis with classification, fill
            probabilities, and direction.
        """
        spx_close = prior_session.spx_close

        # Raw gap in points and percentage
        gap_points = es_premarket_price - spx_close
        gap_pct = (gap_points / spx_close) * 100.0 if spx_close > 0 else 0.0

        # Compute daily 1-sigma in index points from 20-day realised vol
        rv_20d = prior_session.realized_vol_20d
        if rv_20d > 0 and spx_close > 0:
            daily_sigma_points = rv_20d * spx_close / math.sqrt(252)
        else:
            # Fallback: assume ~1% annualised daily vol for the index
            daily_sigma_points = (
                spx_close * 0.01 / math.sqrt(252) if spx_close > 0 else 1.0
            )

        # Normalise gap to sigma units
        gap_sigma = (
            abs(gap_points) / daily_sigma_points
            if daily_sigma_points > 0
            else 0.0
        )

        # Classify
        classification = self._classify_gap_sigma(gap_sigma)

        # Gap fill probabilities from the historical model
        base_rates = _GAP_FILL_PROBABILITIES.get(
            classification, _GAP_FILL_PROBABILITIES[GapClassification.MICRO]
        )
        gap_fill_probability = {
            k: round(v, 2)
            for k, v in zip(_GAP_FILL_TIME_KEYS, base_rates)
        }

        # Direction
        direction = "up" if gap_points >= 0 else "down"

        return GapAnalysis(
            gap_pct=round(gap_pct, 4),
            gap_points=round(gap_points, 2),
            gap_sigma=round(gap_sigma, 4),
            classification=classification,
            gap_fill_probability=gap_fill_probability,
            direction=direction,
        )

    def _classify_gap_sigma(self, gap_sigma: float) -> GapClassification:
        """Map absolute gap sigma to a GapClassification enum value.

        Boundaries are sourced from ``ScanifyConfig``:
            MICRO  — < gap_micro_sigma  (default 0.3)
            SMALL  — gap_micro_sigma to gap_small_sigma  (0.3 - 0.7)
            MEDIUM — gap_small_sigma to gap_medium_sigma (0.7 - 1.5)
            LARGE  — gap_medium_sigma to gap_large_sigma (1.5 - 2.5)
            MEGA   — > gap_large_sigma  (> 2.5)

        Parameters
        ----------
        gap_sigma : float
            Absolute gap magnitude in standard deviations.

        Returns
        -------
        GapClassification
        """
        if gap_sigma < self.config.gap_micro_sigma:
            return GapClassification.MICRO
        elif gap_sigma < self.config.gap_small_sigma:
            return GapClassification.SMALL
        elif gap_sigma < self.config.gap_medium_sigma:
            return GapClassification.MEDIUM
        elif gap_sigma < self.config.gap_large_sigma:
            return GapClassification.LARGE
        else:
            return GapClassification.MEGA

    # ------------------------------------------------------------------
    # Expected move
    # ------------------------------------------------------------------

    def calculate_expected_move(
        self,
        spx_price: float,
        vix_data: VIXData,
        chain: OptionsChain,
        prior: PriorSessionData,
    ) -> ExpectedMove:
        """Compute the blended expected-move envelope for the session.

        Combines three methods via :class:`VIX1DAnalyzer`:

        1. **VIX1D** — ``EM = SPX * (VIX1D / 100) / sqrt(252)``
        2. **Straddle** — ``EM = 0.85 * ATM_straddle_price``
        3. **RV-adjusted** — scales Method 1 by IV/RV ratio

        The blend weights default to 40% / 40% / 20% and are sourced from
        ``ScanifyConfig.em_weight_*``.

        Parameters
        ----------
        spx_price : float
            Current SPX price (or ES proxy pre-open).
        vix_data : VIXData
            Current VIX family snapshot.
        chain : OptionsChain
            0DTE options chain for ATM straddle pricing.
        prior : PriorSessionData
            Prior session data for realised-vol reference.

        Returns
        -------
        ExpectedMove
            Fully populated expected-move envelope with all boundaries
            and method breakdowns.
        """
        vix1d = vix_data.vix1d
        rv_20d = prior.realized_vol_20d

        # Method 1: VIX1D-derived expected move
        m1_result = self._vix1d_analyzer.calculate_expected_move(spx_price, vix1d)
        method_vix1d = m1_result["em_1sigma"]

        # Method 2: ATM straddle-derived expected move
        atm_straddle = self._get_atm_straddle_price(chain)
        m2_result = self._vix1d_analyzer.calculate_straddle_expected_move(
            atm_straddle
        )
        method_straddle = m2_result["em_straddle"]

        # Method 3: Realised-vol-adjusted expected move
        m3_result = self._vix1d_analyzer.calculate_rv_adjusted_expected_move(
            spx_price, vix1d, rv_20d,
        )
        method_rv_adjusted = m3_result["em_rv_adjusted"]
        iv_rv_ratio = m3_result["iv_rv_ratio"]

        # Blended expected move using configurable weights
        weights = (
            self.config.em_weight_vix1d,
            self.config.em_weight_straddle,
            self.config.em_weight_rv_adjusted,
        )
        blended = self._vix1d_analyzer.calculate_blended_expected_move(
            spx_price, vix1d, atm_straddle, rv_20d, weights,
        )
        em_1sigma = blended["blended_em"]
        em_2sigma = round(em_1sigma * 2.0, 2)

        # Volatility regime classification
        vol_regime_info = self._vix1d_analyzer.assess_vol_regime(vix1d)
        vol_regime = vol_regime_info["regime"]

        return ExpectedMove(
            em_1sigma=em_1sigma,
            em_2sigma=em_2sigma,
            upper_1sigma=round(spx_price + em_1sigma, 2),
            lower_1sigma=round(spx_price - em_1sigma, 2),
            upper_2sigma=round(spx_price + em_2sigma, 2),
            lower_2sigma=round(spx_price - em_2sigma, 2),
            method_vix1d=method_vix1d,
            method_straddle=method_straddle,
            method_rv_adjusted=method_rv_adjusted,
            iv_rv_ratio=iv_rv_ratio,
            vol_regime=vol_regime,
        )

    @staticmethod
    def _get_atm_straddle_price(chain: OptionsChain) -> float:
        """Extract the ATM straddle mid-price from the options chain.

        Finds the call and put whose strikes are nearest to the underlying
        price and sums their mid-prices. Returns a reasonable fallback when
        the chain is empty or underlying price is unavailable.

        Parameters
        ----------
        chain : OptionsChain
            0DTE options chain snapshot.

        Returns
        -------
        float
            ATM straddle mid-price (call mid + put mid).
        """
        underlying = chain.underlying_price
        if not chain.quotes or underlying <= 0:
            # Rough approximation: ~0.6% of SPX for a typical 0DTE straddle
            return underlying * 0.006 if underlying > 0 else 30.0

        from .data_feeds import OptionType

        best_call_mid: Optional[float] = None
        best_put_mid: Optional[float] = None
        best_call_dist = float("inf")
        best_put_dist = float("inf")

        for q in chain.quotes:
            dist = abs(q.strike - underlying)
            if q.option_type == OptionType.CALL and dist < best_call_dist:
                best_call_dist = dist
                best_call_mid = q.mid
            elif q.option_type == OptionType.PUT and dist < best_put_dist:
                best_put_dist = dist
                best_put_mid = q.mid

        call_mid = best_call_mid if best_call_mid is not None else 0.0
        put_mid = best_put_mid if best_put_mid is not None else 0.0
        straddle = call_mid + put_mid

        # Ensure a non-zero straddle price for downstream calculations
        if straddle <= 0:
            return underlying * 0.006 if underlying > 0 else 30.0

        return straddle

    # ------------------------------------------------------------------
    # Key levels
    # ------------------------------------------------------------------

    def identify_key_levels(
        self,
        spx_price: float,
        prior: PriorSessionData,
        chain: OptionsChain,
        overnight_high: float,
        overnight_low: float,
    ) -> KeyLevels:
        """Build the composite key-levels map from price-action and options data.

        GEX-derived levels (max_pain, plus_gex, minus_gex, call_wall, put_wall,
        gamma_flip, transition_zone) are set to placeholder values of 0.0.
        These will be populated by the GEX engine once the full chain is
        processed during the intraday session.

        Round levels include the nearest $50 and $100 strikes above and below
        the current SPX price.

        Value area boundaries are estimated from the prior session's VWAP
        and the high/low range using a 70% value-area approximation.

        Parameters
        ----------
        spx_price : float
            Current SPX price (or ES proxy).
        prior : PriorSessionData
            Prior session reference levels.
        chain : OptionsChain
            0DTE options chain (used for max-pain calculation when available).
        overnight_high : float
            Overnight ES futures session high.
        overnight_low : float
            Overnight ES futures session low.

        Returns
        -------
        KeyLevels
            Composite key-levels map with GEX placeholders and populated
            price-action levels.
        """
        # Round-number levels: nearest $50 and $100 above and below
        round_levels = self._compute_round_levels(spx_price)

        # Value area estimation from the prior session.
        # The value area typically contains ~70% of the session's volume.
        # We approximate it as the middle 70% of the prior session range
        # centred on the VWAP.
        value_area_high, value_area_low = self._estimate_value_area(prior)

        # GEX levels are placeholders — filled by the GEX engine later.
        # NOTE: These are intentionally set to 0.0. The GEX engine will
        # overwrite them once it computes the full gamma exposure surface.
        return KeyLevels(
            max_pain=0.0,
            plus_gex=0.0,
            minus_gex=0.0,
            call_wall=0.0,
            put_wall=0.0,
            gamma_flip=0.0,
            transition_zone=(0.0, 0.0),
            prior_high=prior.spx_high,
            prior_low=prior.spx_low,
            prior_close=prior.spx_close,
            prior_vwap=prior.spx_vwap,
            overnight_high=overnight_high,
            overnight_low=overnight_low,
            round_levels=round_levels,
            value_area_high=value_area_high,
            value_area_low=value_area_low,
        )

    @staticmethod
    def _compute_round_levels(spx_price: float) -> List[float]:
        """Compute the nearest round-number SPX levels at $50 and $100 intervals.

        Returns the two nearest $50 levels above and below, plus the two
        nearest $100 levels above and below, sorted and deduplicated.

        Parameters
        ----------
        spx_price : float
            Current SPX price.

        Returns
        -------
        list of float
            Sorted, deduplicated list of nearby round-number levels.
        """
        if spx_price <= 0:
            return []

        levels = set()

        # Nearest $50 levels: two below and two above
        base_50 = math.floor(spx_price / 50.0) * 50.0
        for offset in (-1, 0, 1, 2):
            levels.add(base_50 + offset * 50.0)

        # Nearest $100 levels: two below and two above
        base_100 = math.floor(spx_price / 100.0) * 100.0
        for offset in (-1, 0, 1, 2):
            levels.add(base_100 + offset * 100.0)

        return sorted(levels)

    @staticmethod
    def _estimate_value_area(
        prior: PriorSessionData,
    ) -> Tuple[float, float]:
        """Estimate the prior session's value area from VWAP and range.

        Uses the 70% rule: the value area encompasses approximately 70%
        of the session's price range, centred on the VWAP. When the VWAP
        is not centred in the range, the boundaries are clamped to the
        actual high/low.

        Parameters
        ----------
        prior : PriorSessionData
            Prior session reference levels.

        Returns
        -------
        tuple of (float, float)
            (value_area_high, value_area_low)
        """
        session_range = prior.spx_high - prior.spx_low
        if session_range <= 0:
            return (prior.spx_vwap, prior.spx_vwap)

        # 70% of the range, centred on VWAP
        half_va = session_range * 0.35
        va_high = min(prior.spx_vwap + half_va, prior.spx_high)
        va_low = max(prior.spx_vwap - half_va, prior.spx_low)

        return (round(va_high, 2), round(va_low, 2))

    # ------------------------------------------------------------------
    # Event risk
    # ------------------------------------------------------------------

    def assess_event_risk(
        self,
        calendar: List[EconomicEvent],
    ) -> EventRisk:
        """Assess the session's economic-event risk profile.

        Scans the calendar for FOMC, CPI, and NFP keywords and builds
        time windows during which signal generation should be suspended.

        Suspend-window rules:
            - Standard high-impact event: ``[event_time - 15 min, event_time + 30 min]``
            - FOMC day: ``[13:30 ET, 15:15 ET]`` (overrides individual windows)
            - CPI / NFP: flagged for wider strike selection in downstream scanners

        Risk-level classification:
            - ``"extreme"`` — FOMC day
            - ``"high"``    — CPI or NFP day, or any high-impact event
            - ``"medium"``  — at least one low/medium-impact event present
            - ``"low"``     — no events at all

        Parameters
        ----------
        calendar : list of EconomicEvent
            Today's economic event calendar.

        Returns
        -------
        EventRisk
            Fully populated event risk assessment.
        """
        high_impact = [
            e for e in calendar if e.impact_level == ImpactLevel.HIGH
        ]

        # Detect special event types by keyword matching on event names
        all_names_lower = [e.name.lower() for e in calendar]

        is_fomc = any("fomc" in name for name in all_names_lower)
        is_cpi = any("cpi" in name for name in all_names_lower)
        is_nfp = any(
            ("nonfarm" in name or "non-farm" in name or "nfp" in name
             or "payroll" in name)
            for name in all_names_lower
        )

        # Build suspend windows
        suspend_windows: List[Tuple[time, time]] = []

        if is_fomc:
            # FOMC override: suspend from 1:30 PM to 3:15 PM ET
            suspend_windows.append((time(13, 30), time(15, 15)))
        else:
            # Standard high-impact windows: event_time - 15min to event_time + 30min
            for event in high_impact:
                evt_dt = event.time
                total_minutes = evt_dt.hour * 60 + evt_dt.minute

                start_minutes = max(total_minutes - 15, 0)
                end_minutes = min(total_minutes + 30, 23 * 60 + 59)

                start_h, start_m = divmod(start_minutes, 60)
                end_h, end_m = divmod(end_minutes, 60)

                suspend_windows.append(
                    (time(start_h, start_m), time(min(end_h, 23), end_m))
                )

        # Risk level classification
        if is_fomc:
            risk_level = "extreme"
        elif is_cpi or is_nfp or len(high_impact) > 0:
            risk_level = "high"
        elif len(calendar) > 0:
            risk_level = "medium"
        else:
            risk_level = "low"

        return EventRisk(
            events_today=list(calendar),
            high_impact_events=high_impact,
            is_fomc_day=is_fomc,
            is_cpi_day=is_cpi,
            is_nfp_day=is_nfp,
            suspend_windows=suspend_windows,
            risk_level=risk_level,
        )

    # ------------------------------------------------------------------
    # Session classification
    # ------------------------------------------------------------------

    def classify_session(
        self,
        gap: GapAnalysis,
        em: ExpectedMove,
        event_risk: EventRisk,
        vix_data: VIXData,
        net_gex_positive: bool,
    ) -> SessionType:
        """Classify the upcoming session into a regime type.

        Decision tree (evaluated in priority order):

        1. **EVENT** — FOMC, CPI, or NFP day (any major scheduled release).
        2. **VOLATILE** — VIX1D > 20 OR gap > 1 sigma OR high-impact event
           present.
        3. **TRENDING** — gap > 0.7 sigma AND no conflicting events.
        4. **SQUEEZE** — VIX1D < 14 AND net GEX is positive (dealers long
           gamma, suppressing realised vol).
        5. **RANGE** — default: gap < 0.3 sigma AND VIX1D < 18 AND no
           catalyst. Falls through as the catch-all.

        Parameters
        ----------
        gap : GapAnalysis
            Overnight gap analysis results.
        em : ExpectedMove
            Blended expected-move envelope.
        event_risk : EventRisk
            Economic event risk assessment.
        vix_data : VIXData
            Current VIX family snapshot.
        net_gex_positive : bool
            True if net dealer gamma exposure is positive (dealers long gamma).

        Returns
        -------
        SessionType
            The classified session regime.
        """
        vix1d = vix_data.vix1d

        # 1. EVENT: FOMC / CPI / NFP day
        if event_risk.is_fomc_day or event_risk.is_cpi_day or event_risk.is_nfp_day:
            return SessionType.EVENT

        # 2. VOLATILE: elevated vol or large gap or high-impact event
        if vix1d > 20.0 or gap.gap_sigma > 1.0 or len(event_risk.high_impact_events) > 0:
            return SessionType.VOLATILE

        # 3. TRENDING: meaningful directional gap without conflicting events
        if gap.gap_sigma > 0.7:
            return SessionType.TRENDING

        # 4. SQUEEZE: suppressed vol with positive dealer gamma
        if vix1d < 14.0 and net_gex_positive:
            return SessionType.SQUEEZE

        # 5. RANGE: default balanced session
        return SessionType.RANGE

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run_pre_market_scan(
        self,
        es_price: float,
        prior: PriorSessionData,
        vix_data: VIXData,
        chain: OptionsChain,
        calendar: List[EconomicEvent],
        overnight_high: float,
        overnight_low: float,
        net_gex_positive: bool,
    ) -> SessionSetup:
        """Run the complete pre-market analysis and produce a session setup.

        This is the primary entry point, intended to be called at 9:00 AM ET.
        It orchestrates all sub-analyses in sequence:

        1. Gap analysis (ES pre-market vs prior SPX close)
        2. Expected-move calculation (blended 3-method approach)
        3. Key-level identification (prior session, overnight, GEX placeholders)
        4. Event-risk assessment (calendar scan, suspend windows)
        5. Session classification (TRENDING / RANGE / VOLATILE / SQUEEZE / EVENT)
        6. Scanner-mode recommendation
        7. Session notes generation

        Parameters
        ----------
        es_price : float
            Current E-mini S&P 500 futures price (pre-market).
        prior : PriorSessionData
            Reference levels from the prior trading session.
        vix_data : VIXData
            Current VIX family snapshot (VIX, VIX1D, VIX9D).
        chain : OptionsChain
            0DTE SPX options chain snapshot.
        calendar : list of EconomicEvent
            Today's economic event calendar.
        overnight_high : float
            Overnight ES futures session high.
        overnight_low : float
            Overnight ES futures session low.
        net_gex_positive : bool
            True if net dealer gamma exposure is positive (dealers long gamma).

        Returns
        -------
        SessionSetup
            Complete session setup consumed by the intraday scanners.
        """
        # Use SPX underlying from chain if available, otherwise fall back to ES
        spx_price = (
            chain.underlying_price
            if chain.underlying_price > 0
            else es_price
        )

        # --- 1. Gap analysis -----------------------------------------------
        gap = self.analyze_gap(es_price, prior)

        # --- 2. Expected move ----------------------------------------------
        em = self.calculate_expected_move(spx_price, vix_data, chain, prior)

        # --- 3. Key levels -------------------------------------------------
        key_levels = self.identify_key_levels(
            spx_price, prior, chain, overnight_high, overnight_low,
        )

        # --- 4. Event risk -------------------------------------------------
        event_risk = self.assess_event_risk(calendar)

        # --- 5. Session classification -------------------------------------
        session_type = self.classify_session(
            gap, em, event_risk, vix_data, net_gex_positive,
        )

        # --- 6. Scanner mode -----------------------------------------------
        scanner_mode = self._determine_scanner_mode(session_type, gap, em)

        # --- 7. Session notes ----------------------------------------------
        notes = self._generate_session_notes(
            session_type, gap, em, event_risk, vix_data, key_levels,
        )

        return SessionSetup(
            timestamp=datetime.now(),
            session_type=session_type,
            gap_analysis=gap,
            expected_move=em,
            key_levels=key_levels,
            event_risk=event_risk,
            scanner_mode=scanner_mode,
            notes=notes,
        )

    # ------------------------------------------------------------------
    # Scanner mode mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _determine_scanner_mode(
        session_type: SessionType,
        gap: GapAnalysis,
        em: ExpectedMove,
    ) -> str:
        """Map session type and context to a scanner operating mode description.

        Modes:
            - ``"DIRECTIONAL"``    — trending session; favour momentum entries.
            - ``"NEUTRAL"``        — range-bound; favour premium selling.
            - ``"VOLATILITY"``     — elevated vol; wider strikes, tighter stops.
            - ``"MEAN-REVERSION"`` — squeeze; fade extremes near GEX walls.
            - ``"EVENT"``          — event-driven; suspend around releases.

        Parameters
        ----------
        session_type : SessionType
            Classified session regime.
        gap : GapAnalysis
            Overnight gap analysis (for directional context).
        em : ExpectedMove
            Expected-move envelope (for vol-regime context).

        Returns
        -------
        str
            Scanner mode description string.
        """
        if session_type == SessionType.EVENT:
            return "EVENT"
        elif session_type == SessionType.VOLATILE:
            return "VOLATILITY"
        elif session_type == SessionType.TRENDING:
            return "DIRECTIONAL"
        elif session_type == SessionType.SQUEEZE:
            return "MEAN-REVERSION"
        else:
            return "NEUTRAL"

    # ------------------------------------------------------------------
    # Session notes generation
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_session_notes(
        session_type: SessionType,
        gap: GapAnalysis,
        em: ExpectedMove,
        event_risk: EventRisk,
        vix_data: VIXData,
        key_levels: KeyLevels,
    ) -> List[str]:
        """Generate human-readable session notes and recommendations.

        These notes are consumed by the dashboard and alert system to help
        traders contextualise the automated setup.

        Parameters
        ----------
        session_type : SessionType
        gap : GapAnalysis
        em : ExpectedMove
        event_risk : EventRisk
        vix_data : VIXData
        key_levels : KeyLevels

        Returns
        -------
        list of str
            Session notes and actionable recommendations.
        """
        notes: List[str] = []

        # Session type headline
        notes.append(
            f"Session classified as {session_type.value.upper()}."
        )

        # Gap commentary
        gap_class_name = (
            gap.classification.value
            if isinstance(gap.classification, GapClassification)
            else str(gap.classification)
        )
        if gap.classification in (GapClassification.LARGE, GapClassification.MEGA):
            fill_pct = gap.gap_fill_probability.get("close", 0)
            notes.append(
                f"Large overnight gap {gap.direction} of "
                f"{gap.gap_points:+.1f} pts ({gap.gap_sigma:.2f} sigma). "
                f"Gap fill probability by close: {fill_pct:.0%}."
            )
        elif gap.classification == GapClassification.MEDIUM:
            notes.append(
                f"Medium gap {gap.direction} of {gap.gap_points:+.1f} pts "
                f"({gap.gap_sigma:.2f} sigma). Watch for gap-fill into "
                f"the morning session."
            )
        elif gap.classification == GapClassification.SMALL:
            notes.append(
                f"Small gap {gap.direction} of {gap.gap_points:+.1f} pts "
                f"({gap.gap_sigma:.2f} sigma). High probability of gap fill."
            )

        # Volatility regime
        notes.append(
            f"Vol regime: {em.vol_regime}. VIX1D at {vix_data.vix1d:.1f}, "
            f"IV/RV ratio {em.iv_rv_ratio:.2f}."
        )

        # Expected move boundaries
        notes.append(
            f"Blended 1-sigma expected move: +/-{em.em_1sigma:.1f} pts "
            f"({em.lower_1sigma:.0f} - {em.upper_1sigma:.0f})."
        )
        notes.append(
            f"Blended 2-sigma expected move: +/-{em.em_2sigma:.1f} pts "
            f"({em.lower_2sigma:.0f} - {em.upper_2sigma:.0f})."
        )

        # Method breakdown
        notes.append(
            f"EM breakdown: VIX1D={em.method_vix1d:.1f}, "
            f"Straddle={em.method_straddle:.1f}, "
            f"RV-adj={em.method_rv_adjusted:.1f}."
        )

        # Key reference levels
        notes.append(
            f"Prior session: high={key_levels.prior_high:.0f}, "
            f"low={key_levels.prior_low:.0f}, "
            f"close={key_levels.prior_close:.0f}, "
            f"VWAP={key_levels.prior_vwap:.0f}."
        )
        notes.append(
            f"Overnight range: {key_levels.overnight_low:.0f} - "
            f"{key_levels.overnight_high:.0f}."
        )

        # GEX placeholder reminder
        notes.append(
            "GEX levels (max pain, gamma flip, walls) are placeholders "
            "and will be computed by the GEX engine at market open."
        )

        # Event risk warnings
        if event_risk.risk_level == "extreme":
            notes.append(
                "EXTREME event risk (FOMC day). Scanning will be suspended "
                "13:30-15:15 ET. Reduce position sizing by 50%."
            )
        elif event_risk.risk_level == "high":
            event_names = ", ".join(
                e.name for e in event_risk.high_impact_events
            )
            if event_risk.is_cpi_day or event_risk.is_nfp_day:
                notes.append(
                    f"HIGH event risk: {event_names}. Use wider strike "
                    f"selection and respect suspend windows."
                )
            else:
                notes.append(
                    f"HIGH event risk: {event_names}. Tighten stops and "
                    f"respect suspend windows."
                )
        elif event_risk.risk_level == "medium":
            notes.append(
                "MEDIUM event risk. Monitor upcoming releases and "
                "adjust sizing accordingly."
            )

        if event_risk.suspend_windows:
            windows_str = ", ".join(
                f"{w[0].strftime('%H:%M')}-{w[1].strftime('%H:%M')}"
                for w in event_risk.suspend_windows
            )
            notes.append(f"Suspend windows: {windows_str} ET.")

        # Session-type specific guidance
        if session_type == SessionType.TRENDING:
            dir_label = gap.direction
            notes.append(
                f"Trending session favours directional scans "
                f"({dir_label} bias). Target delta 0.25-0.40."
            )
        elif session_type == SessionType.RANGE:
            notes.append(
                "Range session favours premium selling. "
                "Target credit spreads outside 1-sigma."
            )
        elif session_type == SessionType.SQUEEZE:
            notes.append(
                "Squeeze conditions detected. Premiums are thin; "
                "watch for a vol expansion breakout."
            )
        elif session_type == SessionType.VOLATILE:
            notes.append(
                "Volatile session — widen strike selection, "
                "reduce size by 50%, and use tighter time stops."
            )
        elif session_type == SessionType.EVENT:
            notes.append(
                "Event-driven session. Defer new entries until after "
                "the scheduled release, then reassess conditions."
            )

        return notes
