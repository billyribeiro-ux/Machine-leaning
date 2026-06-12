"""
SCANIFY Orchestrator — Master Controller for 0DTE SPX Scanner System

Coordinates all scanner components, manages the scan loop, and handles
the lifecycle from pre-market setup through settlement close.

The orchestrator ties together:
    - Pre-market session setup (gap analysis, expected move, key levels)
    - GEX engine computation (gamma exposure surface, signals)
    - Three core scanners (directional, premium selling, gamma scalp)
    - Exit management for all open positions
    - Trade logging and persistence
    - Daily calibration (factor weights, thresholds, profit targets)

Typical lifecycle:
    1. ``run_pre_market()`` at 9:00 AM ET
    2. ``run_scan_cycle()`` every 30-60s from 9:45 to 15:45 ET
    3. ``run_end_of_day()`` after 15:45 ET
    4. ``reset_session()`` before next trading day
"""

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Tuple, Any
import logging
import math
import uuid

from .config import (
    ScanifyConfig, SessionType, TimeZone, ScanType,
    SignalDirection, ExitReason, GEXSignalType
)
from .data_feeds import (
    DataFeedManager, OptionsChain, MarketInternalsData, FuturesData,
    VIXData, EconomicEvent, PriorSessionData, SPXPriceBar,
    CrossAssetData, VIX1DAnalyzer
)
from .gex_engine import GEXEngine, GEXResult, GEXSignal
from .market_internals import MarketInternalsScorer, CompositeDirectionScore
from .pre_market import PreMarketScanner, SessionSetup
from .directional import DirectionalScanner, EntrySignal
from .premium_seller import PremiumSellingScanner, PremiumSellSignal
from .gamma_scalp import GammaScalpScanner, GammaScalpSignal
from .exit_manager import ExitManager, Position, ExitSignal
from .trade_logger import TradeLogger, TradeRecord, CalibrationEngine
from .gex_dashboard import GEXDashboard, GEXDashboardData

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Scan interval defaults (seconds) per scan type
# ---------------------------------------------------------------------------

_SCAN_INTERVALS: Dict[ScanType, int] = {
    ScanType.DIRECTIONAL: 60,
    ScanType.PREMIUM_SELL: 300,
    ScanType.GAMMA_SCALP: 30,
}

# SPX option contract multiplier.
_SPX_MULTIPLIER: float = 100.0


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ScanCycleResult:
    """Result of a single scan cycle executed by the orchestrator.

    Captures the outputs of every sub-system that ran during the cycle,
    including GEX computation, directional scoring, scanner signals, and
    exit signals.  This record is the primary output consumed by the
    dashboard and alert system.

    Attributes:
        timestamp: UTC time the cycle completed.
        cycle_number: Monotonically increasing cycle counter for the session.
        time_zone: Intraday time zone at cycle execution.
        session_type: Session regime from the pre-market setup.
        gex_result: GEX surface snapshot computed during this cycle, or
            None if GEX was not refreshed.
        gex_signals: GEX-derived signals detected this cycle.
        direction_score: Composite directional score, or None if the
            directional scorer did not run.
        directional_signal: Entry signal from the directional scanner, or
            None if no actionable signal was produced.
        premium_signal: Premium-selling signal, or None.
        gamma_signal: Gamma scalp signal, or None.
        exit_signals: Exit signals triggered for open positions this cycle.
        active_positions: Count of positions still open after the cycle.
        notes: Operational notes and diagnostic messages.
    """

    timestamp: datetime = field(default_factory=datetime.now)
    cycle_number: int = 0
    time_zone: TimeZone = TimeZone.PRE_MARKET
    session_type: SessionType = SessionType.RANGE
    gex_result: Optional[GEXResult] = None
    gex_signals: List[GEXSignal] = field(default_factory=list)
    direction_score: Optional[CompositeDirectionScore] = None
    directional_signal: Optional[EntrySignal] = None
    premium_signal: Optional[PremiumSellSignal] = None
    gamma_signal: Optional[GammaScalpSignal] = None
    exit_signals: List[ExitSignal] = field(default_factory=list)
    active_positions: int = 0
    notes: List[str] = field(default_factory=list)


@dataclass
class SessionState:
    """Mutable state tracking the current trading session.

    Maintained by the orchestrator across scan cycles and reset at the
    start of each new trading day via ``reset_session()``.

    Attributes:
        session_date: ISO date string for the current session (YYYY-MM-DD).
        session_setup: Pre-market session setup, or None before pre-market
            analysis has run.
        is_pre_market_done: True once ``run_pre_market()`` has completed.
        is_session_active: True between market open and settlement close.
        current_gex: Most recent GEX surface snapshot.
        prior_gex: GEX snapshot from the previous computation cycle, used
            for signal detection (flip, collapse).
        last_direction_score: Most recent composite directional score.
        total_trades_today: Number of trades opened during the session.
        total_pnl_today: Cumulative realised P&L for the session (dollars).
        cycle_count: Number of scan cycles executed today.
        last_scan_time: Timestamp of the most recent scan cycle.
        vix1d_history: Rolling VIX1D readings for spike detection.
        alerts: Accumulated alert messages for the session.
    """

    session_date: str = ""
    session_setup: Optional[SessionSetup] = None
    is_pre_market_done: bool = False
    is_session_active: bool = False
    current_gex: Optional[GEXResult] = None
    prior_gex: Optional[GEXResult] = None
    last_direction_score: Optional[CompositeDirectionScore] = None
    total_trades_today: int = 0
    total_pnl_today: float = 0.0
    cycle_count: int = 0
    last_scan_time: Optional[datetime] = None
    vix1d_history: List[float] = field(default_factory=list)
    alerts: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class ScanifyOrchestrator:
    """Master controller for the SCANIFY 0DTE SPX scanner system.

    The orchestrator initialises and coordinates every sub-component:

    - **PreMarketScanner** — gap analysis, expected move, session classification
    - **GEXEngine** — gamma exposure computation, signal detection
    - **DirectionalScanner** — five-factor directional OTM scanner
    - **PremiumSellingScanner** — credit spread / iron condor scanner
    - **GammaScalpScanner** — late-session gamma acceleration scanner
    - **ExitManager** — position lifecycle and exit logic
    - **TradeLogger** — trade persistence to JSONL
    - **CalibrationEngine** — nightly self-learning parameter tuning
    - **VIX1DAnalyzer** — expected-move and vol-regime calculations

    The three main entry points map to the trading day lifecycle:

    1. ``run_pre_market()`` — called once at ~9:00 AM ET.
    2. ``run_scan_cycle()`` — called on a timer (every 30-60s) from
       9:45 through 15:45 ET.
    3. ``run_end_of_day()`` — called after 15:45 ET to close positions,
       run calibration, and generate the daily scorecard.

    Parameters
    ----------
    config : ScanifyConfig or None
        Master configuration.  If ``None``, a default ``ScanifyConfig()``
        is used.
    """

    def __init__(self, config: Optional[ScanifyConfig] = None) -> None:
        """Initialise the orchestrator and all sub-components.

        Args:
            config: Master SCANIFY configuration.  When ``None`` the
                default configuration is used.
        """
        self.config: ScanifyConfig = config if config is not None else ScanifyConfig()

        # --- Sub-components ---
        self.data_feed_manager = DataFeedManager()
        self.gex_engine = GEXEngine(self.config.gex)
        self.pre_market_scanner = PreMarketScanner(self.config)
        self.directional_scanner = DirectionalScanner(self.config)
        self.premium_scanner = PremiumSellingScanner(self.config)
        self.gamma_scanner = GammaScalpScanner(self.config)
        self.exit_manager = ExitManager(self.config)
        self.trade_logger = TradeLogger(self.config)
        self.calibration_engine = CalibrationEngine(self.config)
        self.vix1d_analyzer = VIX1DAnalyzer()

        # --- Session state ---
        self._state = SessionState(
            session_date=datetime.now().strftime("%Y-%m-%d"),
        )

        # --- Scan timing ---
        # Tracks the last time each scan type was executed so that cadence
        # constraints (e.g. directional every 60s, premium every 300s) are
        # respected.
        self._last_scan_run: Dict[str, datetime] = {}

        logger.info(
            "ScanifyOrchestrator initialised for session %s.",
            self._state.session_date,
        )

    # ==================================================================
    # Pre-market
    # ==================================================================

    def run_pre_market(
        self,
        es_price: float,
        prior_session: PriorSessionData,
        vix_data: VIXData,
        chain: OptionsChain,
        calendar: List[EconomicEvent],
        overnight_high: float,
        overnight_low: float,
    ) -> SessionSetup:
        """Run the pre-market analysis suite and set up the session.

        This method should be called once per day, typically around
        9:00 AM ET, before the regular session opens.  It performs:

        1. An initial GEX computation to determine the net GEX sign
           (required for session classification).
        2. The full pre-market scan (gap analysis, expected move, key
           levels, event risk, session classification).
        3. Session state updates.
        4. Logging of the pre-market results.

        Args:
            es_price: Current E-mini S&P 500 futures price (pre-market).
            prior_session: Reference levels from the prior trading session.
            vix_data: Current VIX / VIX1D / VIX9D snapshot.
            chain: 0DTE SPX options chain snapshot.
            calendar: Today's economic event calendar.
            overnight_high: Overnight ES futures session high.
            overnight_low: Overnight ES futures session low.

        Returns:
            The fully populated ``SessionSetup`` consumed by all
            downstream scanners and the risk manager.
        """
        logger.info("Running pre-market analysis for %s.", self._state.session_date)

        # 1. Compute initial GEX to determine net GEX sign.
        spot = chain.underlying_price if chain.underlying_price > 0 else es_price
        initial_gex = self.gex_engine.compute_gex(chain, spot)
        net_gex_positive = initial_gex.total_net_gex >= 0
        self._state.current_gex = initial_gex

        logger.info(
            "Initial GEX computed: net_gex=%.0f (%s), gamma_flip=%.1f.",
            initial_gex.total_net_gex,
            "positive" if net_gex_positive else "negative",
            initial_gex.gamma_flip_level,
        )

        # 2. Run the full pre-market scan.
        session_setup = self.pre_market_scanner.run_pre_market_scan(
            es_price=es_price,
            prior=prior_session,
            vix_data=vix_data,
            chain=chain,
            calendar=calendar,
            overnight_high=overnight_high,
            overnight_low=overnight_low,
            net_gex_positive=net_gex_positive,
        )

        # 3. Update session state.
        self._state.session_setup = session_setup
        self._state.is_pre_market_done = True
        self._state.is_session_active = True
        self._state.vix1d_history.append(vix_data.vix1d)

        # 4. Log pre-market results.
        logger.info(
            "Pre-market complete: session_type=%s, scanner_mode=%s, "
            "gap=%+.1f pts (%s), EM_1sigma=%.1f pts, VIX1D=%.1f.",
            session_setup.session_type.value,
            session_setup.scanner_mode,
            session_setup.gap_analysis.gap_points,
            session_setup.gap_analysis.classification.value,
            session_setup.expected_move.em_1sigma,
            vix_data.vix1d,
        )

        for note in session_setup.notes:
            logger.info("  [Pre-market] %s", note)

        return session_setup

    # ==================================================================
    # Main scan cycle
    # ==================================================================

    def run_scan_cycle(
        self,
        chain: OptionsChain,
        internals: MarketInternalsData,
        futures: FuturesData,
        vix_data: VIXData,
        cross_asset: CrossAssetData,
        price_bars: List[SPXPriceBar],
        flow_data: Dict[str, Any],
        tick_history: List[float],
        moc_direction: Optional[str] = None,
    ) -> ScanCycleResult:
        """Execute a single scan cycle across all active scanners.

        This is the main entry point called by the scan scheduler on a
        timer (typically every 30-60 seconds) during the regular trading
        session.  It orchestrates the full pipeline:

        1. Verify that the session is active and pre-market is done.
        2. Determine the current intraday time zone.
        3. Compute GEX (if enough time has elapsed since the last
           computation, default 60 seconds).
        4. Detect GEX signals (gamma flip, wall approach, etc.).
        5. Compute the composite directional score.
        6. Run the directional scanner (09:45-15:00, every 60s).
        7. Run the premium selling scanner (10:00-14:00, every 5 min).
        8. Run the gamma scalp scanner (14:00-15:45, every 30s).
        9. Check exit conditions for all open positions.
        10. Process any new signals (register positions with the exit
            manager).
        11. Track VIX1D history for spike detection.
        12. Return the consolidated ``ScanCycleResult``.

        Args:
            chain: Current 0DTE SPX options chain snapshot.
            internals: NYSE market-breadth internals snapshot.
            futures: ES futures data.
            vix_data: VIX / VIX1D / VIX9D snapshot.
            cross_asset: Cross-asset context data (yields, DXY).
            price_bars: Chronological list of 1-minute SPX price bars.
            flow_data: Real-time options flow data dict with keys
                ``put_call_ratio``, ``net_premium_flow``,
                ``net_block_direction``, ``sweep_direction``.
            tick_history: Recent NYSE TICK readings.
            moc_direction: Market-on-close imbalance direction
                (``"buy"`` or ``"sell"``), or ``None`` if unavailable.

        Returns:
            A ``ScanCycleResult`` capturing everything that happened
            during this cycle.
        """
        now = datetime.now()
        notes: List[str] = []

        # ---- 1. Session guard checks ----
        if not self._state.is_pre_market_done:
            logger.warning("Scan cycle called before pre-market analysis. Skipping.")
            return ScanCycleResult(
                timestamp=now,
                notes=["Scan skipped: pre-market not complete."],
            )

        if not self._state.is_session_active:
            logger.debug("Session is not active. Skipping scan cycle.")
            return ScanCycleResult(
                timestamp=now,
                notes=["Scan skipped: session not active."],
            )

        session_setup = self._state.session_setup
        if session_setup is None:
            logger.warning("Session setup is None despite pre-market flag. Skipping.")
            return ScanCycleResult(
                timestamp=now,
                notes=["Scan skipped: session setup missing."],
            )

        # ---- 2. Determine current time zone ----
        current_tz = self.directional_scanner.get_current_timezone(now)
        spot = chain.underlying_price if chain.underlying_price > 0 else futures.price

        # Increment cycle counter.
        self._state.cycle_count += 1
        cycle_num = self._state.cycle_count

        logger.debug(
            "Scan cycle #%d: time_zone=%s, spot=%.2f, VIX1D=%.2f.",
            cycle_num, current_tz.value, spot, vix_data.vix1d,
        )

        # ---- 3. Compute GEX (every 60s) ----
        gex_result: Optional[GEXResult] = None
        gex_signals: List[GEXSignal] = []

        if self._should_run_scan(ScanType.DIRECTIONAL, now, self._last_scan_run):
            # Use the directional interval (60s) for GEX refresh cadence.
            self._state.prior_gex = self._state.current_gex
            gex_result = self.gex_engine.compute_gex(chain, spot)
            self._state.current_gex = gex_result

            logger.debug(
                "GEX computed: net_gex=%.0f, flip=%.1f, dealer=%s.",
                gex_result.total_net_gex,
                gex_result.gamma_flip_level,
                gex_result.dealer_position,
            )

        # Use the most recent GEX result for downstream scanners.
        effective_gex = self._state.current_gex
        if effective_gex is None:
            notes.append("No GEX data available yet.")
            return ScanCycleResult(
                timestamp=now,
                cycle_number=cycle_num,
                time_zone=current_tz,
                session_type=session_setup.session_type,
                notes=notes,
                active_positions=len(self.exit_manager.get_active_positions()),
            )

        # ---- 4. Detect GEX signals ----
        if gex_result is not None:
            # Compute VIX1D percentage change for vanna signal detection.
            vix1d_change_pct = 0.0
            if len(self._state.vix1d_history) >= 2:
                prev_vix1d = self._state.vix1d_history[-1]
                if prev_vix1d > 0:
                    vix1d_change_pct = (vix_data.vix1d - prev_vix1d) / prev_vix1d

            gex_signals = self.gex_engine.detect_signals(
                current_gex=gex_result,
                prior_gex=self._state.prior_gex,
                spot=spot,
                vix1d=vix_data.vix1d,
                vix1d_change_pct=vix1d_change_pct,
            )

            for sig in gex_signals:
                logger.info(
                    "GEX signal: %s — %s (confidence=%.2f) — %s",
                    sig.signal_type.value,
                    sig.direction.value,
                    sig.confidence,
                    sig.description,
                )
                notes.append(f"GEX: {sig.signal_type.value} — {sig.description}")

        # Determine if GEX has flipped since last cycle.
        gex_flipped = False
        if self._state.prior_gex is not None and gex_result is not None:
            prior_positive = self._state.prior_gex.total_net_gex >= 0
            current_positive = gex_result.total_net_gex >= 0
            if prior_positive != current_positive:
                gex_flipped = True
                notes.append(
                    f"GEX FLIPPED: {'positive->negative' if prior_positive else 'negative->positive'}."
                )
                logger.warning("GEX flipped: %s.", notes[-1])

        # ---- 5. Compute composite direction score ----
        direction_score: Optional[CompositeDirectionScore] = None
        try:
            direction_score = self.directional_scanner.compute_direction(
                internals=internals,
                flow_data=flow_data,
                spx_price=spot,
                vwap=self.data_feed_manager.get_vwap() or spot,
                em=session_setup.expected_move,
                futures=futures,
                gex=effective_gex,
                cross_asset=cross_asset,
                vix_data=vix_data,
                tick_history=tick_history,
            )
            self._state.last_direction_score = direction_score
        except Exception as exc:
            logger.error("Error computing direction score: %s", exc)
            notes.append(f"Direction score error: {exc}")

        # ---- 6. Run directional scanner (09:45-15:00, every 60s) ----
        directional_signal: Optional[EntrySignal] = None
        if self._should_run_scan(ScanType.DIRECTIONAL, now, self._last_scan_run):
            can_trade, risk_reason = self._check_risk_limits()
            if can_trade:
                try:
                    directional_signal = self.directional_scanner.scan(
                        chain=chain,
                        internals=internals,
                        flow_data=flow_data,
                        futures=futures,
                        gex=effective_gex,
                        cross_asset=cross_asset,
                        vix_data=vix_data,
                        session_setup=session_setup,
                        price_bars=price_bars,
                        tick_history=tick_history,
                    )
                except Exception as exc:
                    logger.error("Directional scanner error: %s", exc)
                    notes.append(f"Directional scan error: {exc}")
            else:
                notes.append(f"Directional scan skipped: {risk_reason}")

            self._last_scan_run[ScanType.DIRECTIONAL.value] = now

            if directional_signal is not None:
                logger.info(
                    "DIRECTIONAL SIGNAL: %s, strike=%.0f, confidence=%.1f.",
                    directional_signal.direction.value,
                    directional_signal.selected_strike.strike
                    if directional_signal.selected_strike else 0.0,
                    directional_signal.confidence,
                )
                notes.append(
                    f"Directional: {directional_signal.direction.value} "
                    f"signal (confidence={directional_signal.confidence:.1f})"
                )

        # ---- 7. Run premium selling scanner (10:00-14:00, every 5 min) ----
        premium_signal: Optional[PremiumSellSignal] = None
        if self._should_run_scan(ScanType.PREMIUM_SELL, now, self._last_scan_run):
            can_trade, risk_reason = self._check_risk_limits()
            if can_trade:
                try:
                    iv_rv_ratio = session_setup.expected_move.iv_rv_ratio
                    premium_signal = self.premium_scanner.scan(
                        chain=chain,
                        internals=internals,
                        vix_data=vix_data,
                        gex=effective_gex,
                        session_setup=session_setup,
                        price_bars=price_bars,
                        iv_rv_ratio=iv_rv_ratio,
                    )
                except Exception as exc:
                    logger.error("Premium scanner error: %s", exc)
                    notes.append(f"Premium scan error: {exc}")
            else:
                notes.append(f"Premium scan skipped: {risk_reason}")

            self._last_scan_run[ScanType.PREMIUM_SELL.value] = now

            if premium_signal is not None:
                logger.info(
                    "PREMIUM SIGNAL: type=%s, confidence=%.4f.",
                    premium_signal.trade_type,
                    premium_signal.confidence,
                )
                notes.append(
                    f"Premium: {premium_signal.trade_type} "
                    f"signal (confidence={premium_signal.confidence:.2f})"
                )

        # ---- 8. Run gamma scalp scanner (14:00-15:45, every 30s) ----
        gamma_signal: Optional[GammaScalpSignal] = None
        if self._should_run_scan(ScanType.GAMMA_SCALP, now, self._last_scan_run):
            can_trade, risk_reason = self._check_risk_limits()
            if can_trade:
                try:
                    composite_weighted = (
                        direction_score.weighted_score
                        if direction_score is not None else 0.0
                    )
                    charm_dir = effective_gex.charm_direction
                    gamma_signal = self.gamma_scanner.scan(
                        chain=chain,
                        gex=effective_gex,
                        direction_score=composite_weighted,
                        futures=futures,
                        vix_data=vix_data,
                        price_bars=price_bars,
                        charm_direction=charm_dir,
                        moc_direction=moc_direction,
                    )
                except Exception as exc:
                    logger.error("Gamma scalp scanner error: %s", exc)
                    notes.append(f"Gamma scalp error: {exc}")
            else:
                notes.append(f"Gamma scan skipped: {risk_reason}")

            self._last_scan_run[ScanType.GAMMA_SCALP.value] = now

            if gamma_signal is not None:
                logger.info(
                    "GAMMA SIGNAL: %s (%s), strike=%.0f, confidence=%.1f.",
                    gamma_signal.signal_subtype,
                    gamma_signal.direction.value,
                    gamma_signal.strike,
                    gamma_signal.confidence,
                )
                notes.append(
                    f"Gamma: {gamma_signal.signal_subtype} "
                    f"{gamma_signal.direction.value} "
                    f"(confidence={gamma_signal.confidence:.1f})"
                )

        # ---- 9. Check exits for all open positions ----
        vix1d_spike = self._detect_vix1d_spike(vix_data)
        composite_score_value = (
            direction_score.weighted_score
            if direction_score is not None else 0.0
        )

        exit_signals = self._check_all_exits(
            current_time=now,
            composite_score=composite_score_value,
            gex_flipped=gex_flipped,
            vix1d_spike=vix1d_spike,
        )

        if exit_signals:
            for esig in exit_signals:
                logger.info(
                    "EXIT: position=%s, reason=%s, pnl=$%.2f (%.2f%%).",
                    esig.position_id,
                    esig.reason.value,
                    esig.pnl_dollars,
                    esig.pnl_pct * 100.0,
                )
                notes.append(
                    f"Exit: {esig.position_id} — {esig.reason.value} "
                    f"(pnl=${esig.pnl_dollars:.2f})"
                )

        # ---- 10. Process new signals (register positions) ----
        if directional_signal is not None:
            try:
                pos = self._process_directional_signal(directional_signal)
                self._state.total_trades_today += 1
                notes.append(f"Opened directional position: {pos.position_id}")
            except Exception as exc:
                logger.error("Error processing directional signal: %s", exc)

        if premium_signal is not None:
            try:
                pos = self._process_premium_signal(premium_signal)
                self._state.total_trades_today += 1
                notes.append(f"Opened premium position: {pos.position_id}")
            except Exception as exc:
                logger.error("Error processing premium signal: %s", exc)

        if gamma_signal is not None:
            try:
                pos = self._process_gamma_signal(gamma_signal)
                self._state.total_trades_today += 1
                notes.append(f"Opened gamma scalp position: {pos.position_id}")
            except Exception as exc:
                logger.error("Error processing gamma signal: %s", exc)

        # ---- 11. Track VIX1D history ----
        self._state.vix1d_history.append(vix_data.vix1d)
        # Keep only the most recent 60 readings (~60 minutes at 1/min cadence).
        if len(self._state.vix1d_history) > 60:
            self._state.vix1d_history = self._state.vix1d_history[-60:]

        if vix1d_spike:
            notes.append(
                f"VIX1D SPIKE detected: current={vix_data.vix1d:.2f}."
            )
            logger.warning("VIX1D spike detected: %.2f.", vix_data.vix1d)

        # Update last scan time.
        self._state.last_scan_time = now

        active_count = len(self.exit_manager.get_active_positions())

        # ---- 12. Return consolidated result ----
        return ScanCycleResult(
            timestamp=now,
            cycle_number=cycle_num,
            time_zone=current_tz,
            session_type=session_setup.session_type,
            gex_result=gex_result,
            gex_signals=gex_signals,
            direction_score=direction_score,
            directional_signal=directional_signal,
            premium_signal=premium_signal,
            gamma_signal=gamma_signal,
            exit_signals=exit_signals,
            active_positions=active_count,
            notes=notes,
        )

    # ==================================================================
    # Scan cadence management
    # ==================================================================

    def _should_run_scan(
        self,
        scan_type: ScanType,
        current_time: datetime,
        last_run: Dict[str, datetime],
    ) -> bool:
        """Check whether enough time has elapsed to run a scan type.

        Each scan type has a minimum interval between executions:
            - DIRECTIONAL: 60 seconds
            - PREMIUM_SELL: 300 seconds (5 minutes)
            - GAMMA_SCALP: 30 seconds

        Args:
            scan_type: The scanner to check.
            current_time: Current timestamp.
            last_run: Dictionary mapping scan type value strings to the
                timestamp of their last execution.

        Returns:
            ``True`` if the scan should run this cycle.
        """
        key = scan_type.value
        interval = _SCAN_INTERVALS.get(scan_type, 60)

        last_time = last_run.get(key)
        if last_time is None:
            return True

        elapsed = (current_time - last_time).total_seconds()
        return elapsed >= interval

    # ==================================================================
    # Signal -> Position conversion
    # ==================================================================

    def _process_directional_signal(self, signal: EntrySignal) -> Position:
        """Convert an ``EntrySignal`` to a ``Position`` and register it.

        Creates a new position from the directional signal's strike
        selection, entry price, and risk parameters, then registers it
        with the exit manager for lifecycle tracking.

        Args:
            signal: The directional entry signal to process.

        Returns:
            The newly created and registered ``Position``.
        """
        position_id = f"DIR-{uuid.uuid4().hex[:8]}"

        direction_str = (
            "long_call" if signal.direction == SignalDirection.BULLISH
            else "long_put"
        )

        strike = (
            signal.selected_strike.strike
            if signal.selected_strike is not None else 0.0
        )

        # Compute profit target price from entry and target percentage.
        entry_price = signal.entry_price
        profit_target_price = entry_price * (1.0 + signal.profit_target_pct)
        stop_loss_price = entry_price * (1.0 - signal.stop_loss_pct)

        position = Position(
            position_id=position_id,
            scan_type=ScanType.DIRECTIONAL,
            direction=direction_str,
            entry_time=signal.timestamp,
            entry_price=entry_price,
            current_price=entry_price,
            max_price_seen=entry_price,
            min_price_seen=entry_price,
            contracts=1,
            strike=strike,
            stop_loss_price=stop_loss_price,
            profit_target_price=profit_target_price,
        )

        self.exit_manager.register_position(position)
        logger.info(
            "Registered directional position %s: %s strike=%.0f entry=$%.2f "
            "target=$%.2f stop=$%.2f.",
            position_id, direction_str, strike, entry_price,
            profit_target_price, stop_loss_price,
        )
        return position

    def _process_premium_signal(self, signal: PremiumSellSignal) -> Position:
        """Convert a ``PremiumSellSignal`` to a ``Position`` and register it.

        For premium-selling trades the entry price is the credit received
        (positive), and the profit target is a fraction of max profit
        (specified by ``close_target_pct``).

        Args:
            signal: The premium-selling signal to process.

        Returns:
            The newly created and registered ``Position``.
        """
        position_id = f"PRM-{uuid.uuid4().hex[:8]}"

        # Determine direction and credit from the signal.
        if signal.trade_type == "iron_condor" and signal.condor is not None:
            direction_str = "iron_condor"
            entry_price = signal.condor.total_credit
            strike = 0.0  # No single primary strike for a condor.
            max_profit = signal.condor.total_credit
            max_loss = signal.condor.total_max_loss
        elif signal.spread is not None:
            direction_str = signal.spread.spread_type
            entry_price = signal.spread.credit
            strike = signal.spread.short_leg.strike
            max_profit = signal.spread.max_profit
            max_loss = signal.spread.max_loss
        else:
            # Fallback: should not happen if signal is well-formed.
            direction_str = signal.trade_type
            entry_price = 0.0
            strike = 0.0
            max_profit = 0.0
            max_loss = 0.0

        # For credit trades, profit target = close_target_pct of max profit.
        # The "price" the exit manager tracks is the cost to close the spread.
        # Entry price is the credit received; target is to buy back at
        # (1 - close_target_pct) of the credit.
        profit_target_price = entry_price * (1.0 - signal.close_target_pct)
        stop_loss_price = entry_price + max_loss if max_loss > 0 else entry_price * 2.0

        position = Position(
            position_id=position_id,
            scan_type=ScanType.PREMIUM_SELL,
            direction=direction_str,
            entry_time=signal.timestamp,
            entry_price=entry_price,
            current_price=entry_price,
            max_price_seen=entry_price,
            min_price_seen=entry_price,
            contracts=1,
            strike=strike,
            stop_loss_price=stop_loss_price,
            profit_target_price=profit_target_price,
        )

        self.exit_manager.register_position(position)
        logger.info(
            "Registered premium position %s: %s credit=$%.2f "
            "target=$%.2f stop=$%.2f.",
            position_id, direction_str, entry_price,
            profit_target_price, stop_loss_price,
        )
        return position

    def _process_gamma_signal(self, signal: GammaScalpSignal) -> Position:
        """Convert a ``GammaScalpSignal`` to a ``Position`` and register it.

        Args:
            signal: The gamma scalp signal to process.

        Returns:
            The newly created and registered ``Position``.
        """
        position_id = f"GMA-{uuid.uuid4().hex[:8]}"

        direction_str = (
            "long_call" if signal.direction == SignalDirection.BULLISH
            else "long_put"
        )

        entry_price = signal.entry_price
        profit_target_price = entry_price * (1.0 + signal.profit_target_pct)
        stop_loss_price = entry_price * (1.0 - signal.stop_loss_pct)

        position = Position(
            position_id=position_id,
            scan_type=ScanType.GAMMA_SCALP,
            direction=direction_str,
            entry_time=signal.timestamp,
            entry_price=entry_price,
            current_price=entry_price,
            max_price_seen=entry_price,
            min_price_seen=entry_price,
            contracts=1,
            strike=signal.strike,
            stop_loss_price=stop_loss_price,
            profit_target_price=profit_target_price,
        )

        self.exit_manager.register_position(position)
        logger.info(
            "Registered gamma scalp position %s: %s (%s) strike=%.0f "
            "entry=$%.2f target=$%.2f stop=$%.2f.",
            position_id, signal.signal_subtype, direction_str,
            signal.strike, entry_price, profit_target_price, stop_loss_price,
        )
        return position

    # ==================================================================
    # Risk checks
    # ==================================================================

    def _check_risk_limits(self) -> Tuple[bool, str]:
        """Check whether a new trade can be opened under current risk limits.

        Evaluates:
            - Maximum concurrent positions (default 5).
            - Maximum daily loss (default 5% of capital, approximated by
              cumulative daily P&L).

        Returns:
            A ``(can_trade, reason_if_not)`` tuple.  ``can_trade`` is
            ``True`` when a new position may be opened; ``reason_if_not``
            contains a human-readable explanation when trading is blocked.
        """
        risk_cfg = self.config.risk
        active = self.exit_manager.get_active_positions()

        # Check max concurrent positions.
        if len(active) >= risk_cfg.max_concurrent_positions:
            reason = (
                f"Max concurrent positions reached "
                f"({len(active)}/{risk_cfg.max_concurrent_positions})."
            )
            logger.debug("Risk limit: %s", reason)
            return False, reason

        # Check max daily loss.
        # This is a simplified check using session P&L.  A production system
        # would reference actual capital.
        if self._state.total_pnl_today < 0:
            # Use an approximate daily budget of $10,000 for threshold calc.
            # In production this would come from account integration.
            daily_budget_approx = 10_000.0
            max_loss = daily_budget_approx * risk_cfg.max_daily_loss_pct
            if abs(self._state.total_pnl_today) >= max_loss:
                reason = (
                    f"Max daily loss reached: ${self._state.total_pnl_today:.2f} "
                    f"(limit: -${max_loss:.2f})."
                )
                logger.warning("Risk limit: %s", reason)
                return False, reason

        return True, ""

    # ==================================================================
    # VIX1D spike detection
    # ==================================================================

    def _detect_vix1d_spike(self, vix_data: VIXData) -> bool:
        """Check if VIX1D has spiked more than 25% in the last 5 minutes.

        Uses the rolling VIX1D history maintained in session state.  A
        spike is detected when the current VIX1D exceeds any reading from
        the last 5 entries (approximately 5 minutes at 60-second cadence)
        by more than 25%.

        Args:
            vix_data: Current VIX family snapshot.

        Returns:
            ``True`` if a VIX1D spike is detected.
        """
        history = self._state.vix1d_history
        if len(history) < 5:
            return False

        # Look at VIX1D readings from approximately 5 minutes ago.
        lookback = history[-5:]
        oldest_reading = lookback[0]

        if oldest_reading <= 0:
            return False

        change_pct = (vix_data.vix1d - oldest_reading) / oldest_reading

        if change_pct > 0.25:
            logger.warning(
                "VIX1D spike: %.2f -> %.2f (%.1f%% in ~5 min).",
                oldest_reading, vix_data.vix1d, change_pct * 100.0,
            )
            return True

        return False

    # ==================================================================
    # Exit management
    # ==================================================================

    def _check_all_exits(
        self,
        current_time: datetime,
        composite_score: float,
        gex_flipped: bool,
        vix1d_spike: bool,
    ) -> List[ExitSignal]:
        """Run exit checks on all active positions and close those that trigger.

        For each open position:
        1. Update dynamic state (trailing stops, break-even flags) via
           ``ExitManager.manage_position()``.
        2. Evaluate all exit conditions via ``ExitManager.check_exits()``.
        3. If an exit triggers, close the position and log the trade record.
        4. Accumulate the realised P&L into the session total.

        Args:
            current_time: Current timestamp for time-based checks.
            composite_score: Latest composite directional score value.
            gex_flipped: Whether GEX has flipped since last cycle.
            vix1d_spike: Whether a VIX1D spike was detected.

        Returns:
            List of ``ExitSignal`` instances for positions that were closed.
        """
        exit_signals: List[ExitSignal] = []
        active_positions = self.exit_manager.get_active_positions()

        for position in active_positions:
            # Update dynamic state.
            self.exit_manager.manage_position(
                position, position.current_price, current_time,
            )

            # Check exit conditions.
            exit_sig = self.exit_manager.check_exits(
                position=position,
                current_time=current_time,
                composite_score=composite_score,
                gex_flipped=gex_flipped,
                vix1d_spike=vix1d_spike,
            )

            if exit_sig is not None:
                # Close the position.
                try:
                    closed_sig = self.exit_manager.close_position(
                        position=position,
                        reason=exit_sig.reason,
                        exit_price=exit_sig.exit_price,
                        timestamp=current_time,
                    )
                    exit_signals.append(closed_sig)

                    # Update session P&L.
                    self._state.total_pnl_today += closed_sig.pnl_dollars

                    # Log the completed trade.
                    self._log_completed_trade(position, closed_sig, self._state)

                except ValueError as exc:
                    logger.error(
                        "Error closing position %s: %s",
                        position.position_id, exc,
                    )

        return exit_signals

    # ==================================================================
    # Trade logging
    # ==================================================================

    def _log_completed_trade(
        self,
        position: Position,
        exit_signal: ExitSignal,
        session_state: SessionState,
    ) -> TradeRecord:
        """Build a ``TradeRecord`` from a closed position and persist it.

        Populates all available fields from the position, exit signal,
        and session context.  The record is appended to the trade logger
        for JSONL persistence and subsequent calibration.

        Args:
            position: The closed position.
            exit_signal: The exit signal that triggered the close.
            session_state: Current session state for market context.

        Returns:
            The fully populated ``TradeRecord``.
        """
        # Derive option type from direction string.
        if "call" in position.direction:
            option_type = "call"
        elif "put" in position.direction:
            option_type = "put"
        else:
            option_type = "spread"

        # Determine direction from position.
        if position.direction in ("long_call", "bull_put_spread"):
            direction = SignalDirection.BULLISH.value
        elif position.direction in ("long_put", "bear_call_spread"):
            direction = SignalDirection.BEARISH.value
        else:
            direction = SignalDirection.NEUTRAL.value

        # Market context from session state.
        session_setup = session_state.session_setup
        gex = session_state.current_gex

        record = TradeRecord(
            trade_id=position.position_id,
            timestamp_entry=position.entry_time.isoformat(),
            timestamp_exit=exit_signal.timestamp.isoformat(),
            scan_type=position.scan_type.value,
            direction=direction,
            strike=position.strike,
            option_type=option_type,
            entry_price=position.entry_price,
            exit_price=exit_signal.exit_price,
            max_gain_during_trade=(
                (position.max_price_seen - position.entry_price)
                / position.entry_price
                if position.entry_price > 0 else 0.0
            ),
            max_loss_during_trade=(
                (position.entry_price - position.min_price_seen)
                / position.entry_price
                if position.entry_price > 0 else 0.0
            ),
            pnl_dollars=exit_signal.pnl_dollars,
            pnl_percent=exit_signal.pnl_pct,
            hold_time_minutes=exit_signal.hold_time_minutes,
            session_type=(
                session_setup.session_type.value if session_setup else ""
            ),
            net_gex_at_entry=gex.total_net_gex if gex else 0.0,
            gamma_flip_at_entry=gex.gamma_flip_level if gex else 0.0,
            exit_reason=exit_signal.reason.value,
            optimal_exit_price=position.max_price_seen,
            left_on_table_pct=exit_signal.left_on_table_pct,
            was_stopped_prematurely=(
                exit_signal.reason in (ExitReason.STOP_LOSS, ExitReason.TIME_STOP)
                and exit_signal.max_gain_pct > 0.1
            ),
        )

        self.trade_logger.log_trade(record)
        logger.debug("Trade record logged: %s.", record.trade_id)
        return record

    # ==================================================================
    # End of day
    # ==================================================================

    def run_end_of_day(self) -> Dict:
        """Run the end-of-day processing pipeline.

        Performs:
        1. Close any remaining open positions at settlement.
        2. Run daily calibration on the full trade history.
        3. Generate the daily scorecard.
        4. Save calibration results to disk.
        5. Return a summary dictionary with key metrics.

        Returns:
            A dictionary containing:

            - **session_date** — the trading date.
            - **total_trades** — number of trades executed.
            - **total_pnl** — total realised P&L in dollars.
            - **positions_closed** — number of positions closed at EOD.
            - **scorecard** — the daily scorecard object.
            - **calibration** — the calibration result object.
            - **notes** — diagnostic messages.
        """
        logger.info("Running end-of-day processing for %s.", self._state.session_date)
        notes: List[str] = []
        now = datetime.now()

        # 1. Close any remaining open positions at settlement.
        active = self.exit_manager.get_active_positions()
        settlement_signals: List[ExitSignal] = []

        if active:
            logger.info(
                "Closing %d remaining positions at settlement.", len(active),
            )
            current_prices = {
                pos.position_id: pos.current_price for pos in active
            }
            settlement_signals = self.exit_manager.close_all_positions(
                current_prices=current_prices,
                timestamp=now,
                reason=ExitReason.SETTLEMENT_CLOSE,
            )

            for sig in settlement_signals:
                self._state.total_pnl_today += sig.pnl_dollars
                # Find the position for trade logging.
                pos = self.exit_manager._position_map.get(sig.position_id)
                if pos is not None:
                    self._log_completed_trade(pos, sig, self._state)

                logger.info(
                    "Settlement close: %s pnl=$%.2f (%s).",
                    sig.position_id, sig.pnl_dollars, sig.reason.value,
                )

            notes.append(f"Closed {len(settlement_signals)} positions at settlement.")

        # Mark session as inactive.
        self._state.is_session_active = False

        # 2. Run daily calibration.
        all_trades = self.trade_logger.get_trades()
        calibration_result = self.calibration_engine.run_daily_calibration(all_trades)

        for cal_note in calibration_result.notes:
            logger.info("  [Calibration] %s", cal_note)
            notes.append(f"Calibration: {cal_note}")

        # 3. Generate daily scorecard.
        today_str = self._state.session_date
        today_trades = self.trade_logger.get_trades(
            start_date=today_str,
            end_date=today_str,
        )
        scorecard = self.calibration_engine.generate_daily_scorecard(today_trades)

        logger.info(
            "Daily scorecard: trades=%d, win_rate=%.2f%%, pnl=$%.2f, "
            "sharpe=%.2f, max_dd=$%.2f.",
            scorecard.total_trades,
            scorecard.win_rate * 100.0,
            scorecard.total_pnl,
            scorecard.sharpe_estimate,
            scorecard.max_drawdown,
        )

        # 4. Save calibration results.
        try:
            self.calibration_engine.save_calibration(
                calibration_result,
                self.config.calibration_path,
            )
            notes.append(f"Calibration saved to {self.config.calibration_path}.")
            logger.info(
                "Calibration saved to %s.", self.config.calibration_path,
            )
        except Exception as exc:
            logger.error("Failed to save calibration: %s", exc)
            notes.append(f"Calibration save error: {exc}")

        # 5. Return summary.
        summary = {
            "session_date": self._state.session_date,
            "total_trades": self._state.total_trades_today,
            "total_pnl": round(self._state.total_pnl_today, 2),
            "positions_closed_at_settlement": len(settlement_signals),
            "scorecard": scorecard,
            "calibration": calibration_result,
            "notes": notes,
        }

        logger.info(
            "End-of-day complete: %d trades, P&L=$%.2f.",
            self._state.total_trades_today,
            self._state.total_pnl_today,
        )

        return summary

    # ==================================================================
    # Status and diagnostics
    # ==================================================================

    def get_status(self) -> Dict:
        """Return the current system status for dashboard consumption.

        Provides a comprehensive snapshot of the orchestrator's state
        including session information, active positions, GEX summary,
        and recent scan metrics.

        Returns:
            Dictionary with keys:

            - **session_date** — current trading date.
            - **is_pre_market_done** — whether pre-market analysis ran.
            - **is_session_active** — whether the session is live.
            - **session_type** — classified session regime.
            - **scanner_mode** — recommended scanner operating mode.
            - **cycle_count** — number of scan cycles executed.
            - **last_scan_time** — timestamp of the most recent scan.
            - **active_positions** — number of open positions.
            - **position_summary** — aggregated position statistics.
            - **total_trades_today** — trade count for the session.
            - **total_pnl_today** — cumulative session P&L.
            - **gex_summary** — current GEX levels (if available).
            - **last_direction** — most recent directional score direction.
            - **alerts** — accumulated session alerts.
        """
        state = self._state
        pos_summary = self.exit_manager.get_position_summary()

        session_type = (
            state.session_setup.session_type.value
            if state.session_setup else "unknown"
        )
        scanner_mode = (
            state.session_setup.scanner_mode
            if state.session_setup else "unknown"
        )
        last_direction = (
            state.last_direction_score.direction.value
            if state.last_direction_score else "none"
        )

        return {
            "session_date": state.session_date,
            "is_pre_market_done": state.is_pre_market_done,
            "is_session_active": state.is_session_active,
            "session_type": session_type,
            "scanner_mode": scanner_mode,
            "cycle_count": state.cycle_count,
            "last_scan_time": (
                state.last_scan_time.isoformat()
                if state.last_scan_time else None
            ),
            "active_positions": pos_summary["num_open"],
            "position_summary": pos_summary,
            "total_trades_today": state.total_trades_today,
            "total_pnl_today": round(state.total_pnl_today, 2),
            "gex_summary": self.get_gex_summary(),
            "last_direction": last_direction,
            "alerts": list(state.alerts),
        }

    def get_gex_summary(self) -> Optional[Dict]:
        """Return the current GEX levels in a readable dictionary format.

        Returns:
            A dictionary with the key GEX levels and metrics, or ``None``
            if no GEX data is available.
        """
        gex = self._state.current_gex
        if gex is None:
            return None

        return {
            "total_net_gex": round(gex.total_net_gex, 0),
            "dealer_position": gex.dealer_position,
            "gamma_flip_level": round(gex.gamma_flip_level, 1),
            "call_wall": round(gex.call_wall, 0),
            "put_wall": round(gex.put_wall, 0),
            "max_pain": round(gex.max_pain, 0),
            "vol_trigger": round(gex.vol_trigger, 0),
            "transition_zone": (
                round(gex.transition_zone[0], 1),
                round(gex.transition_zone[1], 1),
            ),
            "plus_gex_strike": round(gex.plus_gex_strike, 0),
            "minus_gex_strike": round(gex.minus_gex_strike, 0),
            "net_charm_exposure": round(gex.net_charm_exposure, 0),
            "charm_direction": gex.charm_direction.value,
            "net_vanna_exposure": round(gex.net_vanna_exposure, 0),
            "timestamp": gex.timestamp.isoformat(),
        }

    # ==================================================================
    # GEX Dashboard rendering
    # ==================================================================

    def render_gex_dashboard(
        self,
        chain: Optional[OptionsChain] = None,
        console=None,
    ) -> None:
        """Render the SpotGamma-style GEX dashboard to the terminal.

        Uses the current session state (GEX result, signals, VIX1D, etc.)
        to populate and render the full GEX visualization.

        Parameters
        ----------
        chain : OptionsChain, optional
            Current options chain for per-strike OI detail.
        console : rich.Console, optional
            Custom console for rendering.  Uses a default if not provided.
        """
        gex = self._state.current_gex
        if gex is None:
            logger.warning("No GEX data available for dashboard rendering.")
            return

        setup = self._state.session_setup
        spot = chain.underlying_price if chain else 0.0
        if spot <= 0 and setup:
            spot = setup.expected_move.upper_1sigma - setup.expected_move.em_1sigma

        vix1d = self._state.vix1d_history[-1] if self._state.vix1d_history else 0.0

        gex_signals = self.gex_engine.detect_signals(
            gex, self._state.prior_gex, spot, vix1d
        )

        momentum = self.gex_engine.get_gex_momentum()
        high_speed = self.gex_engine.get_high_speed_strikes(gex, spot)

        tz_str = ""
        if setup:
            tz_str = setup.session_type.value
        session_str = self._state.session_setup.session_type.value if setup else ""

        data = GEXDashboardData(
            gex_result=gex,
            spot_price=spot,
            chain=chain,
            signals=gex_signals,
            gex_momentum=momentum,
            high_speed_strikes=high_speed,
            vix1d=vix1d,
            session_type=session_str,
            time_zone=tz_str,
        )

        dashboard = GEXDashboard(console=console)
        dashboard.render(data)

    # ==================================================================
    # Session reset
    # ==================================================================

    def reset_session(self) -> None:
        """Reset all state for a new trading day.

        Clears the session state, reinitialises the exit manager, and
        resets scan timing.  Sub-components that maintain internal history
        (GEX engine, gamma scanner) are not reset — their rolling buffers
        carry forward naturally.

        This should be called before ``run_pre_market()`` at the start of
        each new trading day.
        """
        old_date = self._state.session_date
        new_date = datetime.now().strftime("%Y-%m-%d")

        logger.info(
            "Resetting session: %s -> %s.", old_date, new_date,
        )

        self._state = SessionState(session_date=new_date)
        self._last_scan_run.clear()

        # Reinitialise the exit manager to clear any stale position state.
        self.exit_manager = ExitManager(self.config)

        logger.info("Session reset complete for %s.", new_date)
