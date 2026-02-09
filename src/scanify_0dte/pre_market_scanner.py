"""
SCANIFY SPX 0DTE Options Day Trading Scanner - Pre-Market Scanner Module

Runs at 9:00 AM ET before market open and computes ALL session setup data.
This module is the first stage of the daily scanning pipeline. It ingests
overnight futures data, the prior session's options chain, VIX1D, and the
economic calendar to produce a fully-populated ``SessionSetup`` object that
downstream real-time scanners consume throughout the trading day.

Key responsibilities:
    1. Overnight gap analysis (magnitude, sigma classification, fill probability)
    2. Expected move calculation (VIX1D, ATM straddle, RV-adjusted, composite)
    3. Key level identification (options structure, price action, market profile)
    4. Economic calendar risk assessment (buffer windows, FOMC/CPI/NFP handling)
    5. Session type classification (TRENDING, RANGE, VOLATILE, SQUEEZE, EVENT)
    6. Orchestration of the complete pre-market scan into ``SessionSetup``
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .constants import TRADING_DAYS_PER_YEAR, VIX1D_REGIME_THRESHOLDS, VIX1DRegime
from .gex_engine import GEXEngine
from .greeks_engine import (
    BlackScholes0DTE,
    composite_expected_move,
    expected_move_rv_adjusted,
    expected_move_straddle,
    expected_move_vix1d,
)
from .models import (
    EconomicEvent,
    ExpectedMove,
    GapAnalysis,
    GEXProfile,
    KeyLevels,
    OptionsChain,
    SessionSetup,
    SessionType,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Gap sigma classification thresholds
_GAP_SIGMA_MICRO: float = 0.3
_GAP_SIGMA_SMALL: float = 0.7
_GAP_SIGMA_MEDIUM: float = 1.5
_GAP_SIGMA_LARGE: float = 2.5

# Gap classification labels
GAP_MICRO: str = "MICRO"
GAP_SMALL: str = "SMALL"
GAP_MEDIUM: str = "MEDIUM"
GAP_LARGE: str = "LARGE"
GAP_MEGA: str = "MEGA"

# Gap fill probability time horizons (Eastern Time)
_GAP_FILL_HORIZONS: Tuple[time, ...] = (
    time(11, 0),   # 11:00 AM ET
    time(13, 0),   # 1:00 PM ET
    time(15, 0),   # 3:00 PM ET
    time(16, 0),   # 4:00 PM ET (close)
)

# Logistic regression coefficients for gap-fill probability model.
# Derived from historical SPX 0DTE gap analysis (2022-2024).
# Features: [intercept, gap_sigma, gap_sigma^2, day_of_week_encoded,
#            vix_level_norm, has_event_flag]
# Separate coefficient vectors per time horizon.
_GAP_FILL_LOGISTIC_COEFFICIENTS: Dict[str, List[float]] = {
    "11:00": [1.20, -1.80, 0.25, -0.05, -0.40, -0.30],
    "13:00": [1.80, -1.50, 0.20, -0.04, -0.35, -0.25],
    "15:00": [2.20, -1.30, 0.18, -0.03, -0.30, -0.20],
    "close": [2.50, -1.10, 0.15, -0.02, -0.25, -0.15],
}

# FOMC timing constants (Eastern Time)
_FOMC_ANNOUNCEMENT: time = time(14, 0)
_FOMC_PRESS_CONFERENCE: time = time(14, 30)
_FOMC_BLACKOUT_START: time = time(13, 30)
_FOMC_BLACKOUT_END: time = time(15, 15)

# CPI / NFP release time (Eastern Time)
_MACRO_RELEASE_TIME: time = time(8, 30)

# Event buffer windows (minutes)
_EVENT_BUFFER_BEFORE_MINUTES: int = 15
_EVENT_BUFFER_AFTER_MINUTES: int = 30

# Session classification thresholds
_VIX1D_VOLATILE_THRESHOLD: float = 20.0
_VIX1D_SQUEEZE_UPPER: float = 13.0
_GAP_TRENDING_SIGMA: float = 0.7
_GAP_VOLATILE_SIGMA: float = 1.0


def _sigmoid(x: float) -> float:
    """Numerically stable sigmoid function."""
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    else:
        z = math.exp(x)
        return z / (1.0 + z)


# ---------------------------------------------------------------------------
# Pre-Market Scanner
# ---------------------------------------------------------------------------


class PreMarketScanner:
    """Computes all pre-market analysis and classifies the session type.

    Runs at 9:00 AM ET. Ingests overnight futures data, the prior session's
    options chain, VIX1D, and the economic calendar to produce a
    ``SessionSetup`` that the real-time scanners consume throughout the day.

    Parameters
    ----------
    bs_calc : BlackScholes0DTE
        Black-Scholes calculator tuned for 0DTE time-to-expiry handling.
    gex_engine : GEXEngine
        Gamma-exposure computation engine for the SPX option chain.
    """

    def __init__(self, bs_calc: BlackScholes0DTE, gex_engine: GEXEngine) -> None:
        self.bs_calc = bs_calc
        self.gex_engine = gex_engine
        logger.info("PreMarketScanner initialised with BS calculator and GEX engine.")

    # ------------------------------------------------------------------
    # 1. Overnight Gap Analysis
    # ------------------------------------------------------------------

    def analyze_overnight_gap(
        self,
        es_premarket: float,
        spx_prior_close: float,
        prior_20day_rv: float,
        spx_price: float,
    ) -> GapAnalysis:
        """Compute overnight gap analysis.

        Gap metrics
        -----------
        Gap %    = (ES_premarket - SPX_prior_close) / SPX_prior_close * 100
        Gap size in sigma = gap_points / (prior_20day_RV * SPX / sqrt(252))

        Classification (by sigma magnitude)
        ------------------------------------
        MICRO  : < 0.3 sigma  -- Normal open, no special handling
        SMALL  : 0.3 - 0.7 sigma -- Slight directional bias
        MEDIUM : 0.7 - 1.5 sigma -- Strong directional bias, gap-fill possible
        LARGE  : 1.5 - 2.5 sigma -- Extreme, likely continuation
        MEGA   : > 2.5 sigma -- Event-driven, all bets off

        Gap Fill Probability
        --------------------
        Logistic-regression model fitted on historical gap characteristics.
        Returns fill probabilities by 11:00 AM, 1:00 PM, 3:00 PM, and close.

        Parameters
        ----------
        es_premarket : float
            Current E-mini S&P 500 futures price in pre-market.
        spx_prior_close : float
            Prior SPX cash session closing price.
        prior_20day_rv : float
            20-day realised volatility of SPX (annualised, as a decimal,
            e.g. 0.15 for 15%).
        spx_price : float
            Current reference SPX price (may equal ``es_premarket`` or a
            synthetic fair value estimate).

        Returns
        -------
        GapAnalysis
            Fully-populated gap analysis object.

        Raises
        ------
        ValueError
            If ``spx_prior_close`` or ``spx_price`` is non-positive.
        """
        if spx_prior_close <= 0:
            raise ValueError(
                f"spx_prior_close must be positive, got {spx_prior_close}"
            )
        if spx_price <= 0:
            raise ValueError(f"spx_price must be positive, got {spx_price}")

        # --- Core gap metrics ---
        gap_points: float = es_premarket - spx_prior_close
        gap_pct: float = (gap_points / spx_prior_close) * 100.0

        # Daily standard deviation in price points
        daily_sigma_points = self._daily_sigma_points(prior_20day_rv, spx_price)
        if daily_sigma_points <= 0:
            logger.warning(
                "Daily sigma is non-positive (%.6f); clamping to 1.0 to avoid "
                "division by zero.",
                daily_sigma_points,
            )
            daily_sigma_points = 1.0

        gap_size_sigma: float = abs(gap_points) / daily_sigma_points
        gap_direction: str = "UP" if gap_points >= 0 else "DOWN"

        # --- Classification ---
        gap_classification = self._classify_gap_sigma(gap_size_sigma)

        logger.info(
            "Overnight gap: %.2f pts (%.3f%%), %.2f sigma -> %s (%s)",
            gap_points,
            gap_pct,
            gap_size_sigma,
            gap_classification,
            gap_direction,
        )

        # --- Gap fill probabilities ---
        # Use current weekday (Monday=0 ... Friday=4) as a feature.
        day_of_week: int = datetime.now().weekday()
        gap_fill_probabilities = self._compute_gap_fill_probabilities(
            gap_size_sigma=gap_size_sigma,
            day_of_week=day_of_week,
            vix_level=prior_20day_rv * 100.0,  # Convert to VIX-style level
            has_economic_event=False,  # Caller can refine via economic risk
        )

        return GapAnalysis(
            gap_points=gap_points,
            gap_pct=gap_pct,
            gap_size_sigma=gap_size_sigma,
            gap_direction=gap_direction,
            gap_classification=gap_classification,
            daily_sigma_points=daily_sigma_points,
            gap_fill_probabilities=gap_fill_probabilities,
            es_premarket=es_premarket,
            spx_prior_close=spx_prior_close,
        )

    # ------------------------------------------------------------------
    # 2. Expected Move Computation
    # ------------------------------------------------------------------

    def compute_expected_move(
        self,
        spx_price: float,
        vix1d: float,
        atm_straddle_price: float,
        rv_20day: float,
    ) -> ExpectedMove:
        """Compute expected move using three methods and a weighted average.

        Method 1 -- VIX1D implied
            EM_vix1d = SPX * (VIX1D / 100) / sqrt(252)

        Method 2 -- ATM straddle implied
            EM_straddle = 0.85 * ATM_0DTE_straddle_price

        Method 3 -- Realised-volatility adjusted
            IV_RV_ratio = VIX1D / RV_20day
            EM_rv_adj   = EM_vix1d * (2 / (1 + IV_RV_ratio))

        Composite
            EM_final = 0.40 * EM_vix1d + 0.40 * EM_straddle + 0.20 * EM_rv_adj

        Parameters
        ----------
        spx_price : float
            Current SPX reference price.
        vix1d : float
            CBOE 1-Day Volatility Index value (e.g. 15.0 for 15%).
        atm_straddle_price : float
            Combined premium of the ATM 0DTE call + put.
        rv_20day : float
            20-day realised volatility (annualised, as a percentage,
            e.g. 14.0 for 14%).

        Returns
        -------
        ExpectedMove
            Object with 1-sigma and 2-sigma bounds, IV/RV ratio, and
            vol-regime classification.

        Raises
        ------
        ValueError
            If any numeric input is non-positive.
        """
        # --- Input validation ---
        if spx_price <= 0:
            raise ValueError(f"spx_price must be positive, got {spx_price}")
        if vix1d < 0:
            raise ValueError(f"vix1d must be non-negative, got {vix1d}")
        if atm_straddle_price < 0:
            raise ValueError(
                f"atm_straddle_price must be non-negative, got {atm_straddle_price}"
            )
        if rv_20day <= 0:
            raise ValueError(f"rv_20day must be positive, got {rv_20day}")

        # --- Method 1: VIX1D ---
        em_vix1d: float = expected_move_vix1d(spx_price, vix1d)
        logger.debug("EM Method 1 (VIX1D): %.2f pts", em_vix1d)

        # --- Method 2: ATM Straddle ---
        em_straddle: float = expected_move_straddle(atm_straddle_price)
        logger.debug("EM Method 2 (Straddle): %.2f pts", em_straddle)

        # --- Method 3: RV-Adjusted ---
        em_rv_adj: float = expected_move_rv_adjusted(
            spx_price, vix1d, rv_20day
        )
        logger.debug("EM Method 3 (RV-Adjusted): %.2f pts", em_rv_adj)

        # --- Composite ---
        em_composite: float = composite_expected_move(
            em_vix1d, em_straddle, em_rv_adj
        )
        logger.info("Composite Expected Move: %.2f pts", em_composite)

        # --- IV / RV ratio and vol regime ---
        iv_rv_ratio: float = vix1d / rv_20day
        vol_regime: str = self._classify_vol_regime(vix1d)

        # --- Build output ---
        upper_1sigma: float = spx_price + em_composite
        lower_1sigma: float = spx_price - em_composite
        upper_2sigma: float = spx_price + 2.0 * em_composite
        lower_2sigma: float = spx_price - 2.0 * em_composite

        logger.info(
            "EM bounds: 1-sigma [%.2f, %.2f], 2-sigma [%.2f, %.2f] | "
            "IV/RV=%.2f | Regime=%s",
            lower_1sigma,
            upper_1sigma,
            lower_2sigma,
            upper_2sigma,
            iv_rv_ratio,
            vol_regime,
        )

        return ExpectedMove(
            em_vix1d=em_vix1d,
            em_straddle=em_straddle,
            em_rv_adjusted=em_rv_adj,
            em_composite=em_composite,
            upper_1sigma=upper_1sigma,
            lower_1sigma=lower_1sigma,
            upper_2sigma=upper_2sigma,
            lower_2sigma=lower_2sigma,
            iv_rv_ratio=iv_rv_ratio,
            vol_regime=vol_regime,
            spx_price=spx_price,
        )

    # ------------------------------------------------------------------
    # 3. Key Level Identification
    # ------------------------------------------------------------------

    def identify_key_levels(
        self,
        chain: OptionsChain,
        gex_profile: GEXProfile,
        prior_session: dict,
        overnight_data: dict,
        spx_price: float,
    ) -> KeyLevels:
        """Identify all key levels from options structure, price action,
        and market profile.

        Sources
        -------
        Options Structure:
            Max Pain, +GEX, -GEX, Call Wall, Put Wall, Gamma Flip,
            Vol Trigger, Transition Zone

        Price Action:
            Prior session high / low / close / VWAP / POC
            Overnight high / low
            Round numbers (nearest $50, $100 SPX levels)
            Moving averages (5, 10, 20, 50-day)

        Market Profile:
            Value Area High (VAH) and Low (VAL)
            Initial Balance boundaries (placeholder for first 30 min)

        Parameters
        ----------
        chain : OptionsChain
            Current 0DTE options chain.
        gex_profile : GEXProfile
            Pre-computed gamma exposure profile.
        prior_session : dict
            Prior session data. Expected keys: ``high``, ``low``, ``close``,
            ``vwap``, ``poc``, ``vah``, ``val``.  Also optional:
            ``ma_5``, ``ma_10``, ``ma_20``, ``ma_50``.
        overnight_data : dict
            Overnight ES futures data. Expected keys: ``high``, ``low``.
        spx_price : float
            Current SPX reference price.

        Returns
        -------
        KeyLevels
            Aggregated key levels for the session.
        """
        if spx_price <= 0:
            raise ValueError(f"spx_price must be positive, got {spx_price}")

        logger.info("Identifying key levels around SPX %.2f", spx_price)

        # --- Options structure levels ---
        options_levels = self._extract_options_levels(gex_profile)

        # --- Price action levels ---
        price_action_levels = self._extract_price_action_levels(
            prior_session, overnight_data, spx_price
        )

        # --- Round numbers ---
        round_numbers = self._compute_round_numbers(spx_price)

        # --- Moving averages ---
        moving_averages = self._extract_moving_averages(prior_session)

        # --- Market profile levels ---
        market_profile_levels = self._extract_market_profile_levels(prior_session)

        logger.info(
            "Key levels identified: %d options, %d price-action, %d round, "
            "%d MA, %d profile",
            len(options_levels),
            len(price_action_levels),
            len(round_numbers),
            len(moving_averages),
            len(market_profile_levels),
        )

        return KeyLevels(
            options_levels=options_levels,
            price_action_levels=price_action_levels,
            round_numbers=round_numbers,
            moving_averages=moving_averages,
            market_profile_levels=market_profile_levels,
            spx_price=spx_price,
        )

    # ------------------------------------------------------------------
    # 4. Economic Risk Assessment
    # ------------------------------------------------------------------

    def assess_economic_risk(
        self,
        events: list[EconomicEvent],
    ) -> tuple[str, list[tuple]]:
        """Assess economic calendar risk for the trading session.

        For each event a buffer window is computed:
            [event_time - 15 min, event_time + 30 min]

        Special handling
        ~~~~~~~~~~~~~~~~
        * **FOMC day** -- 2:00 PM announcement + 2:30 PM press conference.
          Scans are suspended 1:30 PM - 3:15 PM.
        * **CPI / NFP day** -- 8:30 AM release. Massive gap expected;
          pre-market expected move should use a 2x buffer.

        Parameters
        ----------
        events : list[EconomicEvent]
            Economic events scheduled for the session.

        Returns
        -------
        tuple[str, list[tuple]]
            ``(risk_assessment_summary, buffer_windows)``
            where each buffer window is ``(label, start_time, end_time,
            risk_level)``.
        """
        if not events:
            logger.info("No economic events scheduled for the session.")
            return ("LOW -- No scheduled economic events.", [])

        buffer_windows: list[tuple] = []
        risk_factors: list[str] = []
        max_risk: str = "LOW"

        for event in events:
            event_name: str = getattr(event, "name", "UNKNOWN")
            event_time: Optional[time] = getattr(event, "time", None)
            event_importance: str = getattr(
                event, "importance", "medium"
            ).upper()

            logger.debug(
                "Processing economic event: %s at %s (importance=%s)",
                event_name,
                event_time,
                event_importance,
            )

            # --- FOMC special handling ---
            if self._is_fomc_event(event_name):
                fomc_windows = self._build_fomc_buffer_windows(event_name)
                buffer_windows.extend(fomc_windows)
                risk_factors.append(
                    f"FOMC: suspend scans {_FOMC_BLACKOUT_START.strftime('%H:%M')}"
                    f"-{_FOMC_BLACKOUT_END.strftime('%H:%M')}"
                )
                max_risk = "CRITICAL"
                logger.warning(
                    "FOMC day detected. Scans suspended %s-%s.",
                    _FOMC_BLACKOUT_START,
                    _FOMC_BLACKOUT_END,
                )
                continue

            # --- CPI / NFP special handling ---
            if self._is_cpi_or_nfp(event_name):
                cpi_nfp_windows = self._build_cpi_nfp_buffer_windows(event_name)
                buffer_windows.extend(cpi_nfp_windows)
                risk_factors.append(
                    f"{event_name}: 8:30 AM release, massive gap expected, "
                    f"EM buffer 2x"
                )
                max_risk = self._elevate_risk(max_risk, "HIGH")
                logger.warning(
                    "%s day detected. Pre-market EM should use 2x buffer.",
                    event_name,
                )
                continue

            # --- Generic event buffer ---
            if event_time is not None:
                window = self._build_generic_event_window(
                    event_name, event_time, event_importance
                )
                buffer_windows.append(window)
                risk_level = self._importance_to_risk(event_importance)
                risk_factors.append(
                    f"{event_name} at {event_time.strftime('%H:%M')}: "
                    f"risk={risk_level}"
                )
                max_risk = self._elevate_risk(max_risk, risk_level)
            else:
                logger.debug(
                    "Event '%s' has no scheduled time; skipping buffer window.",
                    event_name,
                )
                risk_factors.append(f"{event_name}: time unknown, monitor manually")

        summary = (
            f"{max_risk} -- {len(events)} event(s) scheduled. "
            + "; ".join(risk_factors)
        )
        logger.info("Economic risk assessment: %s", summary)
        return (summary, buffer_windows)

    # ------------------------------------------------------------------
    # 5. Session Classification
    # ------------------------------------------------------------------

    def classify_session(
        self,
        gap: GapAnalysis,
        expected_move: ExpectedMove,
        gex_profile: GEXProfile,
        events: list[EconomicEvent],
        vix1d: float,
        market_internals: dict | None = None,
    ) -> SessionType:
        """Classify the trading session type.

        This determines which scan modes the downstream scanner will activate.

        Classification rules
        --------------------
        **TRENDING**
            Gap > 0.7 sigma, early directional conviction, internals aligned.
            Scanner mode: DIRECTIONAL. Favor OTM calls OR puts, not both.

        **RANGE**
            Gap < 0.3 sigma, balanced internals, no catalyst.
            Scanner mode: NEUTRAL. Favor credit spreads, iron condors.

        **VOLATILE**
            Economic event, VIX1D > 20, gap > 1 sigma.
            Scanner mode: VOLATILITY. Wider strikes, smaller size, or sit out.

        **SQUEEZE**
            Low VIX1D, compressed range, GEX highly positive.
            Scanner mode: MEAN-REVERSION. Sell premium at EM boundaries.

        **EVENT**
            FOMC, CPI, NFP, earnings blackout.
            Scanner mode: EVENT. Special handling per event type.

        Parameters
        ----------
        gap : GapAnalysis
            Overnight gap analysis.
        expected_move : ExpectedMove
            Composite expected move output.
        gex_profile : GEXProfile
            Current gamma exposure profile.
        events : list[EconomicEvent]
            Economic events for the day.
        vix1d : float
            CBOE 1-Day Volatility Index value.
        market_internals : dict, optional
            Intraday breadth / internals data. Expected keys (all optional):
            ``tick``, ``advance_decline_ratio``, ``up_volume_ratio``,
            ``directional_alignment`` (bool).

        Returns
        -------
        SessionType
            Classified session type enum member.
        """
        internals = market_internals or {}

        logger.info(
            "Classifying session: gap_sigma=%.2f, vix1d=%.1f, "
            "events=%d, gex_net=%.0f",
            gap.gap_size_sigma,
            vix1d,
            len(events),
            getattr(gex_profile, "net_gex", 0.0),
        )

        # --- EVENT check first (highest priority) ---
        if self._has_major_event(events):
            logger.info("Session classified as EVENT (major macro event detected).")
            return SessionType.EVENT

        # --- VOLATILE ---
        is_volatile = (
            vix1d > _VIX1D_VOLATILE_THRESHOLD
            or gap.gap_size_sigma > _GAP_VOLATILE_SIGMA
        )
        has_economic_catalyst = any(
            getattr(e, "importance", "").upper() in ("HIGH", "CRITICAL")
            for e in events
        )
        if is_volatile and has_economic_catalyst:
            logger.info(
                "Session classified as VOLATILE (VIX1D=%.1f, gap_sigma=%.2f, "
                "economic catalyst present).",
                vix1d,
                gap.gap_size_sigma,
            )
            return SessionType.VOLATILE

        # Pure VIX1D spike without event still qualifies if extreme
        if vix1d > _VIX1D_VOLATILE_THRESHOLD and gap.gap_size_sigma > _GAP_VOLATILE_SIGMA:
            logger.info(
                "Session classified as VOLATILE (VIX1D=%.1f, gap_sigma=%.2f).",
                vix1d,
                gap.gap_size_sigma,
            )
            return SessionType.VOLATILE

        # --- TRENDING ---
        directional_alignment: bool = internals.get("directional_alignment", False)
        if gap.gap_size_sigma > _GAP_TRENDING_SIGMA:
            if directional_alignment or gap.gap_size_sigma > _GAP_SIGMA_MEDIUM:
                logger.info(
                    "Session classified as TRENDING (gap_sigma=%.2f, "
                    "aligned=%s).",
                    gap.gap_size_sigma,
                    directional_alignment,
                )
                return SessionType.TRENDING

        # --- SQUEEZE ---
        net_gex: float = getattr(gex_profile, "net_gex", 0.0)
        gex_is_positive = net_gex > 0
        if vix1d < _VIX1D_SQUEEZE_UPPER and gex_is_positive:
            logger.info(
                "Session classified as SQUEEZE (VIX1D=%.1f, net_gex=%.0f).",
                vix1d,
                net_gex,
            )
            return SessionType.SQUEEZE

        # --- RANGE (default) ---
        if gap.gap_size_sigma < _GAP_SIGMA_MICRO:
            logger.info(
                "Session classified as RANGE (gap_sigma=%.2f, no catalyst).",
                gap.gap_size_sigma,
            )
            return SessionType.RANGE

        # --- Fallback: use internals for tie-breaking ---
        tick = internals.get("tick")
        if tick is not None and abs(tick) > 500:
            logger.info(
                "Session classified as TRENDING (TICK=%d indicates directional "
                "pressure despite moderate gap).",
                tick,
            )
            return SessionType.TRENDING

        logger.info(
            "Session classified as RANGE (default; gap_sigma=%.2f, no "
            "overriding signals).",
            gap.gap_size_sigma,
        )
        return SessionType.RANGE

    # ------------------------------------------------------------------
    # 6. Main Entry Point
    # ------------------------------------------------------------------

    def run_pre_market_scan(
        self,
        es_premarket: float,
        spx_prior_close: float,
        prior_20day_rv: float,
        spx_price: float,
        vix1d: float,
        chain: OptionsChain,
        prior_session: dict,
        overnight_data: dict,
        economic_events: list[EconomicEvent],
        market_internals: dict | None = None,
    ) -> SessionSetup:
        """Run the complete pre-market scan and return a ``SessionSetup``.

        This is the main orchestration method. It invokes every sub-analysis
        in the correct order:

        1. Gap analysis
        2. Expected move calculation
        3. GEX profile computation
        4. Key level identification
        5. Economic risk assessment
        6. Session classification

        Parameters
        ----------
        es_premarket : float
            E-mini S&P 500 futures pre-market price.
        spx_prior_close : float
            Prior SPX cash session closing price.
        prior_20day_rv : float
            20-day realised volatility (annualised, decimal, e.g. 0.15).
        spx_price : float
            Current SPX reference price.
        vix1d : float
            CBOE 1-Day Volatility Index (e.g. 15.0).
        chain : OptionsChain
            Current 0DTE options chain snapshot.
        prior_session : dict
            Prior session price-action and market-profile data.
        overnight_data : dict
            Overnight ES futures high/low data.
        economic_events : list[EconomicEvent]
            Economic calendar events for the trading day.
        market_internals : dict, optional
            Pre-market or implied-open market internals.

        Returns
        -------
        SessionSetup
            Fully-populated session setup object for downstream consumption.
        """
        scan_start = datetime.now()
        logger.info(
            "===== Pre-Market Scan started at %s =====",
            scan_start.strftime("%Y-%m-%d %H:%M:%S"),
        )

        # ---- Step 1: Gap Analysis ----
        logger.info("[1/6] Computing overnight gap analysis...")
        try:
            gap = self.analyze_overnight_gap(
                es_premarket=es_premarket,
                spx_prior_close=spx_prior_close,
                prior_20day_rv=prior_20day_rv,
                spx_price=spx_price,
            )
        except Exception:
            logger.exception("Gap analysis failed; using fallback neutral gap.")
            gap = self._fallback_gap_analysis(
                es_premarket, spx_prior_close, spx_price
            )

        # ---- Step 2: Expected Move ----
        logger.info("[2/6] Computing expected move...")
        atm_straddle_price = self._compute_atm_straddle_price(chain, spx_price)
        rv_20day_pct = prior_20day_rv * 100.0  # Convert to percentage for EM calc

        try:
            expected_move = self.compute_expected_move(
                spx_price=spx_price,
                vix1d=vix1d,
                atm_straddle_price=atm_straddle_price,
                rv_20day=rv_20day_pct,
            )
        except Exception:
            logger.exception("Expected move calculation failed; using VIX1D fallback.")
            expected_move = self._fallback_expected_move(spx_price, vix1d)

        # ---- Step 3: GEX Profile ----
        logger.info("[3/6] Computing GEX profile...")
        try:
            gex_profile = self.gex_engine.compute_profile(chain, spx_price)
            logger.info(
                "GEX profile computed: net_gex=%.0f, flip_level=%.2f",
                getattr(gex_profile, "net_gex", 0.0),
                getattr(gex_profile, "gamma_flip_level", 0.0),
            )
        except Exception:
            logger.exception("GEX profile computation failed; using empty profile.")
            gex_profile = self._fallback_gex_profile(spx_price)

        # ---- Step 4: Key Levels ----
        logger.info("[4/6] Identifying key levels...")
        try:
            key_levels = self.identify_key_levels(
                chain=chain,
                gex_profile=gex_profile,
                prior_session=prior_session,
                overnight_data=overnight_data,
                spx_price=spx_price,
            )
        except Exception:
            logger.exception("Key level identification failed; using minimal levels.")
            key_levels = self._fallback_key_levels(spx_price, prior_session)

        # ---- Step 5: Economic Risk ----
        logger.info("[5/6] Assessing economic risk...")
        try:
            risk_summary, buffer_windows = self.assess_economic_risk(economic_events)
        except Exception:
            logger.exception("Economic risk assessment failed; assuming no events.")
            risk_summary = "UNKNOWN -- Economic risk assessment failed."
            buffer_windows = []

        # ---- Step 6: Session Classification ----
        logger.info("[6/6] Classifying session type...")
        try:
            session_type = self.classify_session(
                gap=gap,
                expected_move=expected_move,
                gex_profile=gex_profile,
                events=economic_events,
                vix1d=vix1d,
                market_internals=market_internals,
            )
        except Exception:
            logger.exception("Session classification failed; defaulting to RANGE.")
            session_type = SessionType.RANGE

        # ---- Adjust EM for CPI/NFP if needed ----
        if self._needs_em_buffer(economic_events):
            logger.warning(
                "CPI/NFP detected. Applying 2x buffer to expected move bounds."
            )
            expected_move = self._apply_em_buffer(expected_move, multiplier=2.0)

        # ---- Assemble SessionSetup ----
        scan_end = datetime.now()
        elapsed_ms = (scan_end - scan_start).total_seconds() * 1000.0

        session_setup = SessionSetup(
            scan_timestamp=scan_start,
            gap_analysis=gap,
            expected_move=expected_move,
            gex_profile=gex_profile,
            key_levels=key_levels,
            session_type=session_type,
            economic_risk_summary=risk_summary,
            economic_buffer_windows=buffer_windows,
            economic_events=economic_events,
            vix1d=vix1d,
            spx_price=spx_price,
            market_internals=market_internals or {},
        )

        logger.info(
            "===== Pre-Market Scan completed in %.1f ms. "
            "Session type: %s =====",
            elapsed_ms,
            session_type.name if hasattr(session_type, "name") else session_type,
        )

        return session_setup

    # ==================================================================
    # Private helper methods
    # ==================================================================

    @staticmethod
    def _daily_sigma_points(rv_annualised: float, spx_price: float) -> float:
        """Compute one daily standard deviation in SPX points.

        daily_sigma = RV_annualised * SPX / sqrt(252)
        """
        return rv_annualised * spx_price / math.sqrt(TRADING_DAYS_PER_YEAR)

    @staticmethod
    def _classify_gap_sigma(gap_sigma: float) -> str:
        """Return gap classification label from sigma magnitude."""
        if gap_sigma < _GAP_SIGMA_MICRO:
            return GAP_MICRO
        elif gap_sigma < _GAP_SIGMA_SMALL:
            return GAP_SMALL
        elif gap_sigma < _GAP_SIGMA_MEDIUM:
            return GAP_MEDIUM
        elif gap_sigma < _GAP_SIGMA_LARGE:
            return GAP_LARGE
        else:
            return GAP_MEGA

    @staticmethod
    def _compute_gap_fill_probabilities(
        gap_size_sigma: float,
        day_of_week: int,
        vix_level: float,
        has_economic_event: bool,
    ) -> dict[str, float]:
        """Compute gap-fill probability using logistic regression.

        Features: [1 (intercept), gap_sigma, gap_sigma^2,
                   day_of_week / 4.0, vix_level / 30.0, event_flag]

        Returns dict with keys '11:00', '13:00', '15:00', 'close'.
        """
        # Normalise features
        dow_norm: float = day_of_week / 4.0  # 0=Mon -> 0.0, 4=Fri -> 1.0
        vix_norm: float = vix_level / 30.0
        event_flag: float = 1.0 if has_economic_event else 0.0

        features: list[float] = [
            1.0,
            gap_size_sigma,
            gap_size_sigma ** 2,
            dow_norm,
            vix_norm,
            event_flag,
        ]

        probabilities: dict[str, float] = {}
        for horizon, coeffs in _GAP_FILL_LOGISTIC_COEFFICIENTS.items():
            if len(coeffs) != len(features):
                # Safety: coefficient/feature mismatch -- fall back to 0.5
                probabilities[horizon] = 0.5
                continue
            logit: float = sum(c * f for c, f in zip(coeffs, features))
            prob: float = _sigmoid(logit)
            # Clamp to [0.01, 0.99] to avoid degenerate values
            probabilities[horizon] = max(0.01, min(0.99, prob))

        return probabilities

    @staticmethod
    def _classify_vol_regime(vix1d: float) -> str:
        """Classify the volatility regime from VIX1D level."""
        for threshold in VIX1D_REGIME_THRESHOLDS:
            if threshold.lower <= vix1d < threshold.upper:
                return threshold.regime.value
        return VIX1DRegime.EXTREME.value

    # --- Options-structure level extraction ---

    @staticmethod
    def _extract_options_levels(gex_profile: GEXProfile) -> dict[str, float]:
        """Extract key levels from the GEX profile.

        Looks for standard attributes on the GEXProfile dataclass:
            max_pain, positive_gex_level, negative_gex_level, call_wall,
            put_wall, gamma_flip_level, vol_trigger, transition_zone_upper,
            transition_zone_lower.
        """
        level_attrs = [
            ("max_pain", "Max Pain"),
            ("positive_gex_level", "+GEX"),
            ("negative_gex_level", "-GEX"),
            ("call_wall", "Call Wall"),
            ("put_wall", "Put Wall"),
            ("gamma_flip_level", "Gamma Flip"),
            ("vol_trigger", "Vol Trigger"),
            ("transition_zone_upper", "Transition Zone Upper"),
            ("transition_zone_lower", "Transition Zone Lower"),
        ]

        levels: dict[str, float] = {}
        for attr, label in level_attrs:
            value = getattr(gex_profile, attr, None)
            if value is not None and isinstance(value, (int, float)) and value > 0:
                levels[label] = float(value)
        return levels

    @staticmethod
    def _extract_price_action_levels(
        prior_session: dict,
        overnight_data: dict,
        spx_price: float,
    ) -> dict[str, float]:
        """Extract price-action levels from prior session and overnight data."""
        levels: dict[str, float] = {}

        # Prior session levels
        for key, label in [
            ("high", "Prior High"),
            ("low", "Prior Low"),
            ("close", "Prior Close"),
            ("vwap", "Prior VWAP"),
            ("poc", "Prior POC"),
        ]:
            val = prior_session.get(key)
            if val is not None and isinstance(val, (int, float)):
                levels[label] = float(val)

        # Overnight levels
        for key, label in [
            ("high", "Overnight High"),
            ("low", "Overnight Low"),
        ]:
            val = overnight_data.get(key)
            if val is not None and isinstance(val, (int, float)):
                levels[label] = float(val)

        return levels

    @staticmethod
    def _compute_round_numbers(spx_price: float) -> list[float]:
        """Compute nearest round-number levels ($50 and $100 increments).

        Returns levels within +/- $200 of the current price.
        """
        levels: list[float] = []

        # $100 round numbers
        base_100 = math.floor(spx_price / 100.0) * 100.0
        for offset in range(-200, 300, 100):
            level = base_100 + offset
            if abs(level - spx_price) <= 200.0:
                levels.append(level)

        # $50 round numbers (that are not already $100 multiples)
        base_50 = math.floor(spx_price / 50.0) * 50.0
        for offset in range(-200, 250, 50):
            level = base_50 + offset
            if (
                abs(level - spx_price) <= 200.0
                and level % 100.0 != 0
                and level not in levels
            ):
                levels.append(level)

        return sorted(set(levels))

    @staticmethod
    def _extract_moving_averages(prior_session: dict) -> dict[str, float]:
        """Extract moving average values from prior session data."""
        ma_levels: dict[str, float] = {}
        for period in (5, 10, 20, 50):
            key = f"ma_{period}"
            val = prior_session.get(key)
            if val is not None and isinstance(val, (int, float)):
                ma_levels[f"{period}-day MA"] = float(val)
        return ma_levels

    @staticmethod
    def _extract_market_profile_levels(prior_session: dict) -> dict[str, float]:
        """Extract market-profile levels (VAH, VAL, IB boundaries)."""
        levels: dict[str, float] = {}
        for key, label in [
            ("vah", "Value Area High"),
            ("val", "Value Area Low"),
            ("ib_high", "Initial Balance High"),
            ("ib_low", "Initial Balance Low"),
        ]:
            val = prior_session.get(key)
            if val is not None and isinstance(val, (int, float)):
                levels[label] = float(val)
        return levels

    # --- Economic event helpers ---

    @staticmethod
    def _is_fomc_event(event_name: str) -> bool:
        """Check if the event name indicates an FOMC event."""
        normalised = event_name.upper()
        return "FOMC" in normalised or "FED DECISION" in normalised

    @staticmethod
    def _is_cpi_or_nfp(event_name: str) -> bool:
        """Check if the event is CPI or NFP."""
        normalised = event_name.upper()
        return any(
            keyword in normalised
            for keyword in ("CPI", "NFP", "NONFARM", "NON-FARM", "CONSUMER PRICE")
        )

    @staticmethod
    def _build_fomc_buffer_windows(event_name: str) -> list[tuple]:
        """Build FOMC-specific buffer windows."""
        return [
            (
                f"{event_name} - Full Blackout",
                _FOMC_BLACKOUT_START,
                _FOMC_BLACKOUT_END,
                "CRITICAL",
            ),
            (
                f"{event_name} - Announcement",
                _FOMC_ANNOUNCEMENT,
                _FOMC_PRESS_CONFERENCE,
                "CRITICAL",
            ),
            (
                f"{event_name} - Press Conference",
                _FOMC_PRESS_CONFERENCE,
                _FOMC_BLACKOUT_END,
                "CRITICAL",
            ),
        ]

    @staticmethod
    def _build_cpi_nfp_buffer_windows(event_name: str) -> list[tuple]:
        """Build CPI/NFP-specific buffer windows."""
        release_dt = datetime.combine(datetime.today(), _MACRO_RELEASE_TIME)
        buffer_start = (release_dt - timedelta(minutes=30)).time()
        buffer_end = (release_dt + timedelta(minutes=60)).time()
        return [
            (
                f"{event_name} - Pre-Release Buffer",
                buffer_start,
                _MACRO_RELEASE_TIME,
                "HIGH",
            ),
            (
                f"{event_name} - Post-Release Volatility",
                _MACRO_RELEASE_TIME,
                buffer_end,
                "HIGH",
            ),
        ]

    @staticmethod
    def _build_generic_event_window(
        event_name: str,
        event_time: time,
        importance: str,
    ) -> tuple:
        """Build a generic event buffer window.

        Window: [event_time - 15 min, event_time + 30 min]
        """
        event_dt = datetime.combine(datetime.today(), event_time)
        start = (event_dt - timedelta(minutes=_EVENT_BUFFER_BEFORE_MINUTES)).time()
        end = (event_dt + timedelta(minutes=_EVENT_BUFFER_AFTER_MINUTES)).time()
        risk_level = (
            "HIGH" if importance in ("HIGH", "CRITICAL") else "MEDIUM"
        )
        return (event_name, start, end, risk_level)

    @staticmethod
    def _importance_to_risk(importance: str) -> str:
        """Map event importance to risk level."""
        mapping = {
            "CRITICAL": "CRITICAL",
            "HIGH": "HIGH",
            "MEDIUM": "MEDIUM",
            "LOW": "LOW",
        }
        return mapping.get(importance, "MEDIUM")

    @staticmethod
    def _elevate_risk(current: str, new: str) -> str:
        """Return the higher of two risk levels."""
        hierarchy = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3, "UNKNOWN": 1}
        if hierarchy.get(new, 1) > hierarchy.get(current, 1):
            return new
        return current

    # --- Session classification helpers ---

    def _has_major_event(self, events: list[EconomicEvent]) -> bool:
        """Check if any event qualifies as a major session-defining event
        (FOMC, CPI, NFP, earnings blackout)."""
        for event in events:
            event_name = getattr(event, "name", "")
            if self._is_fomc_event(event_name):
                return True
            if self._is_cpi_or_nfp(event_name):
                return True
            normalised = event_name.upper()
            if "EARNINGS BLACKOUT" in normalised:
                return True
        return False

    @staticmethod
    def _needs_em_buffer(events: list[EconomicEvent]) -> bool:
        """Check if any event warrants a 2x EM buffer (CPI/NFP)."""
        for event in events:
            name = getattr(event, "name", "").upper()
            if any(
                kw in name
                for kw in ("CPI", "NFP", "NONFARM", "NON-FARM", "CONSUMER PRICE")
            ):
                return True
        return False

    @staticmethod
    def _apply_em_buffer(em: ExpectedMove, multiplier: float) -> ExpectedMove:
        """Return a new ExpectedMove with bounds scaled by ``multiplier``.

        The individual method EMs and composite are left unchanged; only the
        sigma bounds are widened so that downstream systems use appropriately
        wider risk buffers.
        """
        spx = em.spx_price
        width = em.em_composite * multiplier
        return ExpectedMove(
            em_vix1d=em.em_vix1d,
            em_straddle=em.em_straddle,
            em_rv_adjusted=em.em_rv_adjusted,
            em_composite=em.em_composite,
            upper_1sigma=spx + width,
            lower_1sigma=spx - width,
            upper_2sigma=spx + 2.0 * width,
            lower_2sigma=spx - 2.0 * width,
            iv_rv_ratio=em.iv_rv_ratio,
            vol_regime=em.vol_regime,
            spx_price=spx,
        )

    # --- ATM straddle price extraction ---

    @staticmethod
    def _compute_atm_straddle_price(
        chain: OptionsChain, spx_price: float
    ) -> float:
        """Extract the ATM 0DTE straddle price from the options chain.

        Finds the strike closest to ``spx_price`` and sums the mid-prices
        of the ATM call and ATM put. Falls back to 0.0 if the chain is
        empty or the data is unavailable.
        """
        contracts = getattr(chain, "contracts", None)
        if not contracts:
            logger.warning(
                "Options chain is empty; cannot compute ATM straddle price."
            )
            return 0.0

        # Find ATM strike
        strikes = sorted(set(getattr(c, "strike", 0.0) for c in contracts))
        if not strikes:
            return 0.0
        atm_strike = min(strikes, key=lambda s: abs(s - spx_price))

        atm_call_mid: float = 0.0
        atm_put_mid: float = 0.0

        for contract in contracts:
            strike = getattr(contract, "strike", None)
            if strike != atm_strike:
                continue
            option_type = getattr(contract, "option_type", "").upper()
            bid = getattr(contract, "bid", 0.0) or 0.0
            ask = getattr(contract, "ask", 0.0) or 0.0
            mid = (bid + ask) / 2.0

            if option_type == "CALL":
                atm_call_mid = mid
            elif option_type == "PUT":
                atm_put_mid = mid

        straddle_price = atm_call_mid + atm_put_mid
        logger.debug(
            "ATM strike=%.0f, call_mid=%.2f, put_mid=%.2f, straddle=%.2f",
            atm_strike,
            atm_call_mid,
            atm_put_mid,
            straddle_price,
        )
        return straddle_price

    # --- Fallback constructors for resilience ---

    @staticmethod
    def _fallback_gap_analysis(
        es_premarket: float,
        spx_prior_close: float,
        spx_price: float,
    ) -> GapAnalysis:
        """Return a neutral/minimal GapAnalysis when the primary path fails."""
        gap_points = es_premarket - spx_prior_close if spx_prior_close else 0.0
        gap_pct = (
            (gap_points / spx_prior_close * 100.0) if spx_prior_close else 0.0
        )
        return GapAnalysis(
            gap_points=gap_points,
            gap_pct=gap_pct,
            gap_size_sigma=0.0,
            gap_direction="FLAT",
            gap_classification=GAP_MICRO,
            daily_sigma_points=0.0,
            gap_fill_probabilities={
                "11:00": 0.5,
                "13:00": 0.5,
                "15:00": 0.5,
                "close": 0.5,
            },
            es_premarket=es_premarket,
            spx_prior_close=spx_prior_close,
        )

    @staticmethod
    def _fallback_expected_move(spx_price: float, vix1d: float) -> ExpectedMove:
        """Return a basic VIX1D-only ExpectedMove when the primary path fails."""
        em = spx_price * (vix1d / 100.0) / math.sqrt(TRADING_DAYS_PER_YEAR)
        return ExpectedMove(
            em_vix1d=em,
            em_straddle=0.0,
            em_rv_adjusted=0.0,
            em_composite=em,
            upper_1sigma=spx_price + em,
            lower_1sigma=spx_price - em,
            upper_2sigma=spx_price + 2.0 * em,
            lower_2sigma=spx_price - 2.0 * em,
            iv_rv_ratio=1.0,
            vol_regime="normal",
            spx_price=spx_price,
        )

    @staticmethod
    def _fallback_gex_profile(spx_price: float) -> GEXProfile:
        """Return a minimal GEXProfile when the engine fails.

        Creates an empty profile with zeroed-out GEX values so that
        downstream consumers do not crash.
        """
        return GEXProfile(
            net_gex=0.0,
            positive_gex_level=spx_price,
            negative_gex_level=spx_price,
            call_wall=spx_price,
            put_wall=spx_price,
            gamma_flip_level=spx_price,
            max_pain=spx_price,
            vol_trigger=spx_price,
            transition_zone_upper=spx_price,
            transition_zone_lower=spx_price,
            spx_price=spx_price,
        )

    @staticmethod
    def _fallback_key_levels(
        spx_price: float, prior_session: dict
    ) -> KeyLevels:
        """Return minimal KeyLevels when identification fails."""
        price_action: dict[str, float] = {}
        for key, label in [
            ("high", "Prior High"),
            ("low", "Prior Low"),
            ("close", "Prior Close"),
        ]:
            val = prior_session.get(key)
            if val is not None:
                price_action[label] = float(val)

        return KeyLevels(
            options_levels={},
            price_action_levels=price_action,
            round_numbers=[],
            moving_averages={},
            market_profile_levels={},
            spx_price=spx_price,
        )
