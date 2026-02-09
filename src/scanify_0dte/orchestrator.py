"""
SCANIFY SPX 0DTE Options Day Trading Scanner - Main Orchestrator

Ties together ALL components and runs the complete scanning pipeline in
real-time.  This module is the single entry point for the entire SCANIFY
system -- from pre-market analysis at 9:00 AM ET through post-market
calibration after the close.

Component Lifecycle
-------------------
    1. ``initialize()``     -- connect data feeds, load calibration state
    2. ``run_pre_market_phase()``  -- 9:00 AM pre-market scan
    3. ``run_full_session()``      -- continuous scan cycles 9:30 - 4:00
    4. ``run_post_market()``       -- P&L, calibration, reporting
    5. ``shutdown()``              -- disconnect, persist state

Scan Cycle Cadence by Time Zone
--------------------------------
    OPENING_AUCTION  (9:30 - 9:45)  : NO scanning.  Data collection only.
    MORNING_SESSION  (9:45 - 11:30) : Directional scanner every 60 s.
    MIDDAY_LULL      (11:30 - 1:30) : Premium + directional every 300 s.
    AFTERNOON_ACCEL  (1:30 - 3:00)  : Directional + gamma scalp prep every 60 s.
    POWER_HOUR       (3:00 - 3:45)  : Gamma scalp (30 s) + directional (60 s).
    SETTLEMENT       (3:45 - 4:00)  : EXIT ONLY.  No new positions.

Dependencies:
    asyncio, logging, argparse, signal, json, pathlib, datetime
    Internal: models, data_pipeline, greeks_engine, gex_engine,
              pre_market_scanner, directional_scanner, premium_scanner,
              gamma_scalp_scanner, exit_manager, calibration

Author: SCANIFY Engine
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import traceback
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import (
    SessionSetup,
    ScanSignal,
    ScanType,
    SessionType,
    TimeZoneType,
    TradeDirection,
    GEXProfile,
    GEXSignal,
)
from .data_pipeline import DataFeedManager
from .greeks_engine import BlackScholes0DTE, GreeksCalculator
from .gex_engine import GEXEngine, GEXSignalGenerator
from .pre_market_scanner import PreMarketScanner
from .directional_scanner import DirectionalOTMScanner
from .premium_scanner import PremiumSellingScanner
from .gamma_scalp_scanner import GammaScalpScanner
from .exit_manager import ExitManager
from .calibration import TradeLogger, DailyCalibrator, CalibrationState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Eastern-time helpers (mirrors data_pipeline but kept local for isolation)
# ---------------------------------------------------------------------------

_ET_OFFSET_EST = timezone(timedelta(hours=-5))
_ET_OFFSET_EDT = timezone(timedelta(hours=-4))


def _is_dst_approx(dt: datetime) -> bool:
    """Approximate US Eastern DST check (second Sunday in March to first
    Sunday in November)."""
    year = dt.year
    # Second Sunday of March
    march_start = datetime(year, 3, 8, tzinfo=timezone.utc)
    while march_start.weekday() != 6:
        march_start += timedelta(days=1)
    # First Sunday of November
    nov_start = datetime(year, 11, 1, tzinfo=timezone.utc)
    while nov_start.weekday() != 6:
        nov_start += timedelta(days=1)
    d = dt.date() if isinstance(dt, datetime) else dt
    return march_start.date() <= d < nov_start.date()


def _get_et_now() -> datetime:
    """Return the current time in US Eastern."""
    utc_now = datetime.now(timezone.utc)
    offset = _ET_OFFSET_EDT if _is_dst_approx(utc_now) else _ET_OFFSET_EST
    return utc_now.astimezone(offset)


# ---------------------------------------------------------------------------
# Scan interval constants (seconds)
# ---------------------------------------------------------------------------

_DIRECTIONAL_INTERVAL: float = 60.0       # 1 minute
_PREMIUM_INTERVAL: float = 300.0           # 5 minutes
_GAMMA_SCALP_INTERVAL: float = 30.0        # 30 seconds
_GEX_REFRESH_INTERVAL: float = 60.0        # 1 minute
_EXIT_CHECK_INTERVAL: float = 15.0         # 15 seconds

# Time-zone boundaries (Eastern Time)
_OPENING_AUCTION_START = time(9, 30)
_OPENING_AUCTION_END = time(9, 45)
_MORNING_SESSION_END = time(11, 30)
_MIDDAY_LULL_END = time(13, 30)
_AFTERNOON_ACCEL_END = time(15, 0)
_POWER_HOUR_END = time(15, 45)
_SETTLEMENT_END = time(16, 0)
_POST_MARKET_TIME = time(16, 15)
_PRE_MARKET_SCAN_TIME = time(9, 0)


# ============================================================================
# ScanifyOrchestrator
# ============================================================================

class ScanifyOrchestrator:
    """Main orchestrator that runs the complete SCANIFY SPX 0DTE scanning pipeline.

    This is the entry point for the entire system. It:
    - Manages the data feed lifecycle
    - Runs pre-market analysis
    - Orchestrates all three scanners based on time zone and session type
    - Manages GEX signal generation
    - Handles exit management for all positions
    - Runs calibration after market close
    - Provides real-time status and alerts

    Parameters
    ----------
    data_provider : str
        Data vendor name (``"polygon"``, ``"alpaca"``, ``"cboe"``,
        ``"mock"``).  Default ``"polygon"``.
    api_key : str
        API key for the chosen data vendor.
    risk_budget : float
        Daily risk budget in dollars.  Default ``10000.0``.
    paper_trade : bool
        If ``True`` (default), simulates fills rather than routing to an
        execution engine.
    calibration_state : CalibrationState, optional
        Pre-loaded calibration state.  If ``None`` the orchestrator
        attempts to load from disk.
    log_dir : str
        Directory for trade logs, calibration snapshots, and daily
        reports.  Default ``"logs/scanify"``.

    Examples
    --------
    ::

        orch = ScanifyOrchestrator(
            data_provider="mock",
            paper_trade=True,
            risk_budget=10_000.0,
        )
        await orch.initialize()
        report = await orch.run_full_session()
        await orch.shutdown()
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        data_provider: str = "polygon",
        api_key: str = "",
        risk_budget: float = 10_000.0,
        paper_trade: bool = True,
        calibration_state: Optional[CalibrationState] = None,
        log_dir: str = "logs/scanify",
    ) -> None:
        # Configuration
        self._data_provider = data_provider
        self._api_key = api_key
        self._risk_budget = risk_budget
        self.paper_trade = paper_trade
        self._log_dir = Path(log_dir)

        # -- Component instances --
        self.data_feed = DataFeedManager(
            data_provider=data_provider,
            api_key=api_key,
        )
        self.bs_calc = BlackScholes0DTE()
        self.greeks_calc = GreeksCalculator(self.bs_calc)
        self.gex_engine = GEXEngine()
        self.gex_signal_gen = GEXSignalGenerator()
        self.pre_market = PreMarketScanner(
            bs_calc=self.bs_calc,
            gex_engine=self.gex_engine,
        )
        self.directional = DirectionalOTMScanner()
        self.premium = PremiumSellingScanner()
        self.gamma_scalp = GammaScalpScanner()
        self.exit_mgr = ExitManager()
        self.trade_logger = TradeLogger()
        self.calibrator = DailyCalibrator()

        # -- Calibration state --
        if calibration_state is not None:
            self._calibration_state = calibration_state
        else:
            self._calibration_state = self.load_state()

        # -- Session state --
        self.session_setup: Optional[SessionSetup] = None
        self.current_gex: Optional[GEXProfile] = None
        self.active_signals: List[ScanSignal] = []
        self.gex_signals: List[GEXSignal] = []
        self.is_running: bool = False
        self.scan_count: int = 0
        self.last_scan_time: Optional[datetime] = None
        self.alerts: List[Dict[str, Any]] = []

        # -- Internal bookkeeping --
        self._active_positions: List[Dict[str, Any]] = []
        self._closed_positions: List[Dict[str, Any]] = []
        self._daily_pnl: float = 0.0
        self._intraday_pnl_curve: List[Dict[str, Any]] = []
        self._shutdown_event: asyncio.Event = asyncio.Event()

        logger.info(
            "ScanifyOrchestrator created: provider=%s, paper=%s, budget=%.0f",
            data_provider,
            paper_trade,
            risk_budget,
        )

    # ------------------------------------------------------------------
    # (a) initialize
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Initialize all components and data feeds.

        Connects to the data provider, loads calibration state from disk
        (if not already provided at construction), and ensures the log
        directory exists.

        Raises
        ------
        ConnectionError
            If the data feed connection fails.
        """
        logger.info("Initializing SCANIFY system...")

        # Ensure log directory
        self._log_dir.mkdir(parents=True, exist_ok=True)

        # Connect data feeds
        await self.data_feed.connect()
        logger.info("Data feed connected.")

        # Load calibration state if not present
        if self._calibration_state is None:
            self._calibration_state = self.load_state()
            if self._calibration_state is not None:
                logger.info("Calibration state loaded from disk.")
            else:
                logger.info("No prior calibration state found; starting fresh.")

        self.is_running = True
        logger.info("SCANIFY system initialized and ready.")

    # ------------------------------------------------------------------
    # (b) shutdown
    # ------------------------------------------------------------------

    async def shutdown(self) -> None:
        """Gracefully shut down all components.

        Closes any remaining open positions (using market exits), stops
        data feed streaming, disconnects from the provider, and persists
        state to disk.
        """
        logger.info("Initiating SCANIFY shutdown sequence...")
        self.is_running = False
        self._shutdown_event.set()

        # Close remaining positions
        if self._active_positions:
            logger.warning(
                "Closing %d remaining position(s) during shutdown.",
                len(self._active_positions),
            )
            for pos in list(self._active_positions):
                try:
                    await self._close_position(pos, reason="SYSTEM_SHUTDOWN")
                except Exception:
                    logger.exception(
                        "Error closing position %s during shutdown.",
                        pos.get("signal_id", "UNKNOWN"),
                    )

        # Disconnect data feeds
        try:
            await self.data_feed.disconnect()
        except Exception:
            logger.exception("Error disconnecting data feeds.")

        # Save state
        try:
            self.save_state()
        except Exception:
            logger.exception("Error saving state during shutdown.")

        logger.info("SCANIFY shutdown complete.")

    # ------------------------------------------------------------------
    # (c) run_pre_market_phase
    # ------------------------------------------------------------------

    async def run_pre_market_phase(self) -> SessionSetup:
        """Run at 9:00 AM ET.  Execute full pre-market analysis.

        Steps
        -----
        1. Fetch all pre-market data (prior session, options chain,
           economic calendar, cross-asset data, VIX).
        2. Run pre-market scanner (gap, expected move, GEX, key levels,
           economic risk, session classification).
        3. Store the resulting ``SessionSetup`` for downstream scanners.
        4. Log the session setup and add an alert.

        Returns
        -------
        SessionSetup
            Fully-populated session setup for the day.
        """
        logger.info("===== Running Pre-Market Phase =====")
        self.add_alert("PHASE", "Pre-market analysis started", "INFO")

        try:
            # Fetch baseline data
            snapshot = await self.data_feed.get_snapshot()
            spx_price = snapshot.get("spx_price", 0.0)
            es_price = snapshot.get("es_price", spx_price)
            prior_session = snapshot.get("prior_session", {})
            economic_events = snapshot.get("economic_events", [])

            # Fetch options chain if not yet available
            chain = snapshot.get("options_chain")
            if chain is None:
                chain = await self.data_feed.fetch_options_chain()

            # Fetch cross-asset for VIX1D
            cross = snapshot.get("cross_asset_data")
            if cross is None:
                cross = await self.data_feed.fetch_cross_asset_data()

            vix1d = getattr(cross, "vix1d", 15.0) if cross else 15.0
            prior_close = prior_session.get("close", spx_price)
            rv_20day = prior_session.get("rv_20day", 0.15)

            overnight_data = {
                "high": prior_session.get("overnight_high", es_price + 5.0),
                "low": prior_session.get("overnight_low", es_price - 5.0),
            }

            # Market internals (may not be available pre-market)
            internals_obj = snapshot.get("market_internals")
            market_internals = None
            if internals_obj is not None:
                market_internals = {
                    "tick": getattr(internals_obj, "nyse_tick", 0),
                    "advance_decline_ratio": getattr(
                        internals_obj, "advance_decline_ratio", 1.0
                    ),
                    "up_volume_ratio": getattr(
                        internals_obj, "up_volume_ratio", 0.5
                    ),
                    "directional_alignment": False,
                }

            # Run the pre-market scanner
            session_setup = self.pre_market.run_pre_market_scan(
                es_premarket=es_price,
                spx_prior_close=prior_close,
                prior_20day_rv=rv_20day,
                spx_price=spx_price,
                vix1d=vix1d,
                chain=chain,
                prior_session=prior_session,
                overnight_data=overnight_data,
                economic_events=economic_events,
                market_internals=market_internals,
            )

            self.session_setup = session_setup

            # Initial GEX profile
            self.current_gex = getattr(session_setup, "gex_profile", None)

            session_type_name = (
                session_setup.session_type.name
                if hasattr(session_setup.session_type, "name")
                else str(session_setup.session_type)
            )

            logger.info(
                "Pre-market phase complete: session_type=%s, spx=%.2f, "
                "vix1d=%.1f",
                session_type_name,
                spx_price,
                vix1d,
            )
            self.add_alert(
                "SESSION",
                f"Session classified as {session_type_name} | SPX {spx_price:.0f} | "
                f"VIX1D {vix1d:.1f}",
                "HIGH",
            )

            return session_setup

        except Exception as exc:
            logger.exception("Pre-market phase failed: %s", exc)
            self.add_alert("ERROR", f"Pre-market phase failed: {exc}", "CRITICAL")
            raise

    # ------------------------------------------------------------------
    # (d) run_scan_cycle
    # ------------------------------------------------------------------

    async def run_scan_cycle(self) -> List[ScanSignal]:
        """Execute one complete scan cycle.

        Based on the current intraday time zone, runs the appropriate
        combination of scanners.  Also runs GEX signal generation and
        exit management every cycle.

        Time Zone Behaviour
        -------------------
        OPENING_AUCTION  (9:30 - 9:45)  : NO scanning. Collect data only.
        MORNING_SESSION  (9:45 - 11:30) : Directional every 60 s.
        MIDDAY_LULL      (11:30 - 1:30) : Premium (300 s) + directional.
        AFTERNOON_ACCEL  (1:30 - 3:00)  : Directional + gamma scalp prep.
        POWER_HOUR       (3:00 - 3:45)  : Gamma scalp (30 s) + directional.
        SETTLEMENT       (3:45 - 4:00)  : EXIT ONLY.  No new positions.

        Returns
        -------
        list[ScanSignal]
            New signals generated during this cycle (may be empty).
        """
        cycle_start = _get_et_now()
        current_time = cycle_start.time()
        new_signals: List[ScanSignal] = []

        try:
            # Refresh market data snapshot
            snapshot = await self.data_feed.get_snapshot()
            spx_price = snapshot.get("spx_price", 0.0)

            if spx_price <= 0:
                logger.warning("SPX price unavailable; skipping scan cycle.")
                return new_signals

            # Determine current time zone
            zone = self._classify_time_zone(current_time)

            # ---- GEX refresh (every cycle) ----
            try:
                await self.update_gex_profile()
            except Exception:
                logger.exception("GEX profile update failed during scan cycle.")

            # ---- GEX signal check ----
            try:
                gex_sigs = await self.check_gex_signals()
                if gex_sigs:
                    self.gex_signals.extend(gex_sigs)
                    for gs in gex_sigs:
                        sig_name = getattr(gs, "signal_type", "GEX_SIGNAL")
                        self.add_alert(
                            "GEX",
                            f"GEX signal: {sig_name}",
                            "HIGH",
                        )
            except Exception:
                logger.exception("GEX signal check failed during scan cycle.")

            # ---- Exit management (every cycle) ----
            try:
                await self.manage_positions()
            except Exception:
                logger.exception("Exit management failed during scan cycle.")

            # ---- Scanner execution by zone ----
            if current_time < _OPENING_AUCTION_END:
                # OPENING AUCTION -- data collection only
                logger.debug(
                    "Opening auction: collecting data, no scanning."
                )

            elif current_time < _MORNING_SESSION_END:
                # MORNING SESSION -- directional scanner
                dir_signals = await self._run_directional_scan(snapshot)
                new_signals.extend(dir_signals)

            elif current_time < _MIDDAY_LULL_END:
                # MIDDAY LULL -- premium selling + directional
                prem_signals = await self._run_premium_scan(snapshot)
                dir_signals = await self._run_directional_scan(snapshot)
                new_signals.extend(prem_signals)
                new_signals.extend(dir_signals)

            elif current_time < _AFTERNOON_ACCEL_END:
                # AFTERNOON ACCELERATION -- directional + gamma scalp prep
                dir_signals = await self._run_directional_scan(snapshot)
                new_signals.extend(dir_signals)
                # Gamma scalp preparation (lighter scan)
                try:
                    gs_signals = await self._run_gamma_scalp_scan(
                        snapshot, prep_only=True
                    )
                    new_signals.extend(gs_signals)
                except Exception:
                    logger.exception("Gamma scalp prep failed.")

            elif current_time < _POWER_HOUR_END:
                # POWER HOUR -- gamma scalp + directional
                gs_signals = await self._run_gamma_scalp_scan(snapshot)
                dir_signals = await self._run_directional_scan(snapshot)
                new_signals.extend(gs_signals)
                new_signals.extend(dir_signals)

            elif current_time < _SETTLEMENT_END:
                # SETTLEMENT -- exit only, no new positions
                logger.info(
                    "Settlement window: exit-only mode, no new positions."
                )
                self.add_alert(
                    "PHASE",
                    "Settlement window entered -- exit-only mode",
                    "HIGH",
                )
            else:
                logger.debug("After-hours: no scanning.")

            # ---- Process new signals ----
            for sig in new_signals:
                try:
                    trade = await self.process_signal(sig)
                    if trade is not None:
                        logger.info(
                            "Signal processed -> trade: %s",
                            trade.get("signal_id", "N/A"),
                        )
                except Exception:
                    logger.exception(
                        "Error processing signal %s",
                        getattr(sig, "signal_id", "UNKNOWN"),
                    )

            # Book-keeping
            self.active_signals.extend(new_signals)
            self.scan_count += 1
            self.last_scan_time = _get_et_now()

            # Record intraday P&L point
            self._record_pnl_snapshot()

            if new_signals:
                logger.info(
                    "Scan cycle #%d complete: %d new signal(s) in zone %s.",
                    self.scan_count,
                    len(new_signals),
                    zone,
                )
            else:
                logger.debug(
                    "Scan cycle #%d complete: no new signals (zone=%s).",
                    self.scan_count,
                    zone,
                )

        except Exception as exc:
            logger.exception("Scan cycle error: %s", exc)
            self.add_alert("ERROR", f"Scan cycle error: {exc}", "CRITICAL")

        return new_signals

    # ------------------------------------------------------------------
    # (e) update_gex_profile
    # ------------------------------------------------------------------

    async def update_gex_profile(self) -> GEXProfile:
        """Recompute GEX profile from the current options chain.

        Called every 60 seconds during active scanning.  Updates
        ``self.current_gex`` in place.

        Returns
        -------
        GEXProfile
            The freshly computed gamma exposure profile.

        Raises
        ------
        RuntimeError
            If no options chain is available.
        """
        chain = self.data_feed.options_chain
        if chain is None:
            chain = await self.data_feed.fetch_options_chain()

        spx_price = self.data_feed.spx_price
        if spx_price <= 0:
            raise RuntimeError(
                "Cannot compute GEX profile: SPX price unavailable."
            )

        profile = self.gex_engine.compute_profile(chain, spx_price)
        self.current_gex = profile

        logger.debug(
            "GEX profile updated: net_gex=%.0f, flip=%.2f, call_wall=%.2f, "
            "put_wall=%.2f",
            getattr(profile, "net_gex", 0.0),
            getattr(profile, "gamma_flip_level", 0.0),
            getattr(profile, "call_wall", 0.0),
            getattr(profile, "put_wall", 0.0),
        )
        return profile

    # ------------------------------------------------------------------
    # (f) check_gex_signals
    # ------------------------------------------------------------------

    async def check_gex_signals(self) -> List[GEXSignal]:
        """Run all six GEX signal checks against the current profile.

        Signal Types
        ------------
        1. GEX Shift -- sudden change in total gamma exposure
        2. Charm Exposure -- large net charm flow
        3. Gamma Wall Approach -- price nearing major gamma concentration
        4. GEX Flip -- crossing from positive to negative gamma territory
        5. GEX Collapse -- structural gamma drop (options expiring)
        6. Transition Zone -- entering call/put gamma transition zone

        Returns
        -------
        list[GEXSignal]
            Active GEX signals (may be empty if nothing is firing).
        """
        if self.current_gex is None:
            logger.debug("No GEX profile available; skipping signal check.")
            return []

        spx_price = self.data_feed.spx_price
        if spx_price <= 0:
            return []

        try:
            signals = self.gex_signal_gen.check_all_signals(
                gex_profile=self.current_gex,
                spx_price=spx_price,
            )
        except Exception:
            logger.exception("GEX signal generation failed.")
            signals = []

        if signals:
            logger.info("%d GEX signal(s) detected.", len(signals))
        return signals

    # ------------------------------------------------------------------
    # (g) manage_positions
    # ------------------------------------------------------------------

    async def manage_positions(self) -> List[Dict[str, Any]]:
        """Run exit management for all active positions.

        Delegates to the ``ExitManager`` which evaluates profit targets,
        stop losses, time stops, trailing stops, and settlement-window
        forced exits for each open position.

        Returns
        -------
        list[dict]
            Exit actions taken this cycle.  Each dict describes the
            position closed and the reason for exit.
        """
        if not self._active_positions:
            return []

        exit_actions: List[Dict[str, Any]] = []
        now = _get_et_now()
        current_time = now.time()
        spx_price = self.data_feed.spx_price

        for pos in list(self._active_positions):
            try:
                action = self.exit_mgr.evaluate_exit(
                    position=pos,
                    current_price=spx_price,
                    current_time=current_time,
                    gex_profile=self.current_gex,
                )
                if action is not None and action.get("exit", False):
                    await self._close_position(
                        pos,
                        reason=action.get("reason", "EXIT_MANAGER"),
                        exit_price=action.get("exit_price", spx_price),
                    )
                    exit_actions.append(action)
            except Exception:
                logger.exception(
                    "Exit management error for position %s.",
                    pos.get("signal_id", "UNKNOWN"),
                )

        if exit_actions:
            logger.info(
                "%d position(s) closed by exit manager.", len(exit_actions)
            )

        return exit_actions

    # ------------------------------------------------------------------
    # (h) process_signal
    # ------------------------------------------------------------------

    async def process_signal(
        self, signal: ScanSignal
    ) -> Optional[Dict[str, Any]]:
        """Process a scan signal: validate, size, and enter a position.

        Validation
        ----------
        - Rejects if daily loss limit breached.
        - Rejects if max concurrent positions reached.
        - Rejects if signal has stale data.
        - Rejects if we are in the settlement window.

        In ``paper_trade`` mode, the fill is simulated at the signal's
        suggested entry price.  In live mode, the order would be routed
        to the execution engine (not yet implemented).

        Parameters
        ----------
        signal : ScanSignal
            The scan signal to process.

        Returns
        -------
        dict or None
            Trade entry details (``signal_id``, ``entry_price``,
            ``size``, ``direction``, ``strategy``, ``timestamp``, etc.)
            or ``None`` if the signal was rejected.
        """
        # --- Validation ---
        now = _get_et_now()

        # Settlement window: no new entries
        if now.time() >= _POWER_HOUR_END:
            logger.info(
                "Signal rejected (settlement window): %s",
                getattr(signal, "signal_id", "N/A"),
            )
            return None

        # Max concurrent positions
        from .constants import RISK_MANAGEMENT

        max_positions = RISK_MANAGEMENT.max_concurrent_positions
        if len(self._active_positions) >= max_positions:
            logger.info(
                "Signal rejected (max positions %d reached): %s",
                max_positions,
                getattr(signal, "signal_id", "N/A"),
            )
            return None

        # Daily loss limit
        max_daily_loss = self._risk_budget * RISK_MANAGEMENT.max_daily_loss_pct
        if self._daily_pnl <= -max_daily_loss:
            logger.warning(
                "Signal rejected (daily loss limit %.2f breached): %s",
                max_daily_loss,
                getattr(signal, "signal_id", "N/A"),
            )
            self.add_alert(
                "RISK",
                f"Daily loss limit breached (${abs(self._daily_pnl):.0f})",
                "CRITICAL",
            )
            return None

        # --- Position sizing ---
        max_risk_per_trade = (
            self._risk_budget * RISK_MANAGEMENT.max_risk_per_trade_pct
        )
        entry_price = getattr(signal, "entry_price", 0.0)
        stop_price = getattr(signal, "stop_loss", 0.0)
        risk_per_contract = abs(entry_price - stop_price) * 100.0 if stop_price else max_risk_per_trade
        if risk_per_contract <= 0:
            risk_per_contract = max_risk_per_trade
        size = max(1, int(max_risk_per_trade / risk_per_contract))

        # --- Build trade entry ---
        signal_id = getattr(signal, "signal_id", f"SIG-{self.scan_count}-{now.strftime('%H%M%S')}")
        direction = getattr(signal, "direction", "UNKNOWN")
        strategy = getattr(signal, "scan_type", "UNKNOWN")

        trade: Dict[str, Any] = {
            "signal_id": signal_id,
            "entry_price": entry_price,
            "stop_loss": stop_price,
            "take_profit": getattr(signal, "take_profit", 0.0),
            "size": size,
            "direction": str(direction),
            "strategy": str(strategy),
            "entry_time": now.isoformat(),
            "paper_trade": self.paper_trade,
            "pnl": 0.0,
            "max_pnl": 0.0,
            "status": "OPEN",
        }

        if self.paper_trade:
            # Simulate fill at the signal's entry price
            trade["fill_price"] = entry_price
            trade["fill_time"] = now.isoformat()
            logger.info(
                "[PAPER] Entered %s %s @ %.2f x%d (signal %s)",
                direction,
                strategy,
                entry_price,
                size,
                signal_id,
            )
        else:
            # Live execution placeholder
            logger.info(
                "[LIVE] Order routed: %s %s @ %.2f x%d (signal %s)",
                direction,
                strategy,
                entry_price,
                size,
                signal_id,
            )
            trade["fill_price"] = entry_price  # placeholder
            trade["fill_time"] = now.isoformat()

        self._active_positions.append(trade)
        self.trade_logger.log_entry(trade)

        self.add_alert(
            "TRADE",
            f"{'PAPER ' if self.paper_trade else ''}ENTRY: {direction} {strategy} "
            f"@ {entry_price:.2f} x{size}",
            "HIGH",
        )

        return trade

    # ------------------------------------------------------------------
    # (i) run_post_market
    # ------------------------------------------------------------------

    async def run_post_market(
        self, target_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """Run after market close (4:15 PM ET).

        Steps
        -----
        1. Close any remaining open positions.
        2. Generate daily P&L summary.
        3. Run daily calibration (update factor weights, thresholds).
        4. Update calibration state.
        5. Save state to disk.
        6. Generate and return a daily report.

        Parameters
        ----------
        target_date : date, optional
            The trading date.  Defaults to today.

        Returns
        -------
        dict
            Daily report containing P&L breakdown, trade log, calibration
            adjustments, and system metrics.
        """
        logger.info("===== Running Post-Market Phase =====")
        self.add_alert("PHASE", "Post-market analysis started", "INFO")

        if target_date is None:
            target_date = _get_et_now().date()

        # 1. Close remaining positions
        for pos in list(self._active_positions):
            try:
                await self._close_position(pos, reason="MARKET_CLOSE")
            except Exception:
                logger.exception(
                    "Error closing position %s at market close.",
                    pos.get("signal_id", "UNKNOWN"),
                )

        # 2. Daily P&L summary
        total_pnl = sum(p.get("pnl", 0.0) for p in self._closed_positions)
        winning_trades = [
            p for p in self._closed_positions if p.get("pnl", 0.0) > 0
        ]
        losing_trades = [
            p for p in self._closed_positions if p.get("pnl", 0.0) <= 0
        ]
        win_rate = (
            len(winning_trades) / len(self._closed_positions)
            if self._closed_positions
            else 0.0
        )
        avg_win = (
            sum(p["pnl"] for p in winning_trades) / len(winning_trades)
            if winning_trades
            else 0.0
        )
        avg_loss = (
            sum(p["pnl"] for p in losing_trades) / len(losing_trades)
            if losing_trades
            else 0.0
        )

        pnl_summary = {
            "date": target_date.isoformat(),
            "total_pnl": total_pnl,
            "total_trades": len(self._closed_positions),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": (
                abs(avg_win * len(winning_trades))
                / max(abs(avg_loss * len(losing_trades)), 1e-9)
            ),
            "max_drawdown": self._compute_max_drawdown(),
        }

        logger.info(
            "Daily P&L: $%.2f | Trades: %d | Win rate: %.1f%%",
            total_pnl,
            len(self._closed_positions),
            win_rate * 100,
        )

        # 3. Run daily calibration
        calibration_result: Dict[str, Any] = {}
        try:
            calibration_result = self.calibrator.run_daily_calibration(
                trades=self._closed_positions,
                pnl_summary=pnl_summary,
                session_setup=self.session_setup,
                calibration_state=self._calibration_state,
            )
            logger.info(
                "Daily calibration complete: %s",
                calibration_result.get("summary", "OK"),
            )
        except Exception:
            logger.exception("Daily calibration failed.")
            calibration_result = {"summary": "FAILED", "error": traceback.format_exc()}

        # 4. Update calibration state
        new_state = calibration_result.get("updated_state")
        if new_state is not None:
            self._calibration_state = new_state

        # 5. Save state to disk
        self.save_state()

        # 6. Build daily report
        session_type_name = "UNKNOWN"
        if self.session_setup is not None:
            st = getattr(self.session_setup, "session_type", None)
            session_type_name = st.name if hasattr(st, "name") else str(st)

        report: Dict[str, Any] = {
            "date": target_date.isoformat(),
            "session_type": session_type_name,
            "pnl_summary": pnl_summary,
            "trades": [
                {
                    "signal_id": t.get("signal_id"),
                    "direction": t.get("direction"),
                    "strategy": t.get("strategy"),
                    "entry_price": t.get("entry_price"),
                    "exit_price": t.get("exit_price"),
                    "pnl": t.get("pnl"),
                    "entry_time": t.get("entry_time"),
                    "exit_time": t.get("exit_time"),
                    "exit_reason": t.get("exit_reason"),
                }
                for t in self._closed_positions
            ],
            "gex_signals": [
                {
                    "signal_type": getattr(gs, "signal_type", "UNKNOWN"),
                    "timestamp": str(getattr(gs, "timestamp", "")),
                }
                for gs in self.gex_signals
            ],
            "scan_count": self.scan_count,
            "calibration": calibration_result,
            "alerts": self.alerts[-50:],  # Last 50 alerts
            "intraday_pnl_curve": self._intraday_pnl_curve,
        }

        # Persist report to disk
        report_path = self._log_dir / f"report_{target_date.isoformat()}.json"
        try:
            with open(report_path, "w") as f:
                json.dump(report, f, indent=2, default=str)
            logger.info("Daily report saved to %s", report_path)
        except Exception:
            logger.exception("Failed to save daily report.")

        self.add_alert(
            "REPORT",
            f"Daily report: P&L ${total_pnl:+.0f} | "
            f"{len(self._closed_positions)} trades | "
            f"{win_rate * 100:.0f}% win rate",
            "HIGH",
        )

        return report

    # ------------------------------------------------------------------
    # (j) run_full_session
    # ------------------------------------------------------------------

    async def run_full_session(self) -> Dict[str, Any]:
        """Run the COMPLETE trading session from pre-market to post-market.

        Timeline
        --------
        09:00 AM  : Pre-market scan
        09:30 AM  : Market open, begin data collection (streaming)
        09:45 AM  : Begin scanning cycles
        ...       : Continuous scanning based on time zone
        03:45 PM  : Stop scanning, exit all positions
        04:00 PM  : Market close
        04:15 PM  : Post-market analysis and calibration

        The method uses an asyncio event loop with scheduled intervals.
        It blocks until the full session completes or ``shutdown()`` is
        called (e.g. via a SIGINT handler).

        Returns
        -------
        dict
            The daily report produced by ``run_post_market()``.
        """
        logger.info("===== Starting Full SCANIFY Session =====")
        self.add_alert("PHASE", "Full session started", "HIGH")

        # Reset session state
        self.active_signals.clear()
        self.gex_signals.clear()
        self._active_positions.clear()
        self._closed_positions.clear()
        self._daily_pnl = 0.0
        self._intraday_pnl_curve.clear()
        self.scan_count = 0
        self.alerts.clear()

        # ---- Wait for pre-market time (9:00 AM ET) ----
        await self._wait_until_time(_PRE_MARKET_SCAN_TIME, label="pre-market")

        if self._shutdown_event.is_set():
            return {"status": "SHUTDOWN_BEFORE_PREMARKET"}

        # ---- Pre-market phase ----
        try:
            await self.run_pre_market_phase()
        except Exception:
            logger.exception("Pre-market phase failed; continuing with defaults.")

        # ---- Wait for market open (9:30 AM ET) ----
        await self._wait_until_time(_OPENING_AUCTION_START, label="market open")

        if self._shutdown_event.is_set():
            return {"status": "SHUTDOWN_BEFORE_OPEN"}

        # ---- Start data feed streaming ----
        try:
            await self.data_feed.start_streaming()
        except Exception:
            logger.exception("Failed to start data streaming.")

        # ---- Main scanning loop ----
        logger.info("Entering main scanning loop.")
        last_directional_scan = datetime.min.replace(tzinfo=timezone.utc)
        last_premium_scan = datetime.min.replace(tzinfo=timezone.utc)
        last_gamma_scan = datetime.min.replace(tzinfo=timezone.utc)
        last_gex_refresh = datetime.min.replace(tzinfo=timezone.utc)
        last_exit_check = datetime.min.replace(tzinfo=timezone.utc)

        while not self._shutdown_event.is_set():
            now = _get_et_now()
            current_time = now.time()

            # Past settlement window -- stop scanning
            if current_time >= _SETTLEMENT_END:
                logger.info("Market close reached. Exiting scan loop.")
                break

            # Determine cycle interval based on time zone
            zone = self._classify_time_zone(current_time)
            cycle_interval = self._get_cycle_interval(zone)

            # Run scan cycle
            try:
                await self.run_scan_cycle()
            except Exception:
                logger.exception("Scan cycle raised an unhandled exception.")

            # Sleep for the appropriate interval (or until shutdown)
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=cycle_interval,
                )
                # Shutdown event was set
                break
            except asyncio.TimeoutError:
                # Normal: interval elapsed
                pass

        # ---- Stop streaming ----
        try:
            await self.data_feed.stop_streaming()
        except Exception:
            logger.exception("Error stopping data streams.")

        # ---- Wait for post-market time (4:15 PM ET) ----
        await self._wait_until_time(_POST_MARKET_TIME, label="post-market")

        # ---- Post-market phase ----
        report: Dict[str, Any] = {}
        try:
            report = await self.run_post_market()
        except Exception:
            logger.exception("Post-market phase failed.")
            report = {"status": "POST_MARKET_FAILED"}

        logger.info("===== SCANIFY Session Complete =====")
        return report

    # ------------------------------------------------------------------
    # (k) get_status
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Get current system status for the dashboard.

        Returns
        -------
        dict
            Keys:
            - ``session_type`` : str
            - ``time_zone`` : str
            - ``minutes_remaining`` : int
            - ``active_positions`` : int
            - ``total_pnl`` : float
            - ``current_gex_summary`` : dict
            - ``recent_signals`` : list (last 10)
            - ``recent_alerts`` : list (last 20)
            - ``scan_count`` : int
            - ``last_scan_time`` : str or None
            - ``is_running`` : bool
            - ``paper_trade`` : bool
            - ``data_connected`` : bool
            - ``risk_budget_remaining`` : float
        """
        now = _get_et_now()
        current_time = now.time()
        zone = self._classify_time_zone(current_time)
        minutes_remaining = self.data_feed.get_minutes_remaining()

        session_type = "UNKNOWN"
        if self.session_setup is not None:
            st = getattr(self.session_setup, "session_type", None)
            session_type = st.name if hasattr(st, "name") else str(st)

        # GEX summary
        gex_summary: Dict[str, Any] = {}
        if self.current_gex is not None:
            gex_summary = {
                "net_gex": getattr(self.current_gex, "net_gex", 0.0),
                "gamma_flip_level": getattr(
                    self.current_gex, "gamma_flip_level", 0.0
                ),
                "call_wall": getattr(self.current_gex, "call_wall", 0.0),
                "put_wall": getattr(self.current_gex, "put_wall", 0.0),
                "max_pain": getattr(self.current_gex, "max_pain", 0.0),
            }

        # Unrealized P&L
        unrealized = sum(p.get("pnl", 0.0) for p in self._active_positions)
        realized = sum(p.get("pnl", 0.0) for p in self._closed_positions)
        total_pnl = realized + unrealized

        return {
            "session_type": session_type,
            "time_zone": zone,
            "minutes_remaining": minutes_remaining,
            "active_positions": len(self._active_positions),
            "total_pnl": total_pnl,
            "realized_pnl": realized,
            "unrealized_pnl": unrealized,
            "current_gex_summary": gex_summary,
            "recent_signals": [
                {
                    "signal_id": getattr(s, "signal_id", "N/A"),
                    "scan_type": str(getattr(s, "scan_type", "N/A")),
                    "direction": str(getattr(s, "direction", "N/A")),
                    "entry_price": getattr(s, "entry_price", 0.0),
                }
                for s in self.active_signals[-10:]
            ],
            "recent_alerts": self.alerts[-20:],
            "scan_count": self.scan_count,
            "last_scan_time": (
                self.last_scan_time.isoformat()
                if self.last_scan_time
                else None
            ),
            "is_running": self.is_running,
            "paper_trade": self.paper_trade,
            "data_connected": self.data_feed.is_connected,
            "risk_budget_remaining": max(
                0.0, self._risk_budget + self._daily_pnl
            ),
        }

    # ------------------------------------------------------------------
    # (l) get_dashboard_data
    # ------------------------------------------------------------------

    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get comprehensive data package for the frontend dashboard.

        Returns
        -------
        dict
            Keys:
            - ``spx_price`` : float
            - ``expected_move`` : dict (upper/lower 1-sigma / 2-sigma)
            - ``gex_profile`` : dict (bar chart data by strike)
            - ``key_levels`` : dict
            - ``active_positions`` : list[dict]
            - ``direction_score`` : dict
            - ``recent_signals`` : list[dict]
            - ``gex_signals`` : list[dict]
            - ``intraday_pnl_curve`` : list[dict]
            - ``session_classification`` : dict
            - ``status`` : dict (from ``get_status()``)
        """
        spx_price = self.data_feed.spx_price

        # Expected move boundaries
        em_data: Dict[str, Any] = {}
        if self.session_setup is not None:
            em = getattr(self.session_setup, "expected_move", None)
            if em is not None:
                em_data = {
                    "upper_1sigma": getattr(em, "upper_1sigma", 0.0),
                    "lower_1sigma": getattr(em, "lower_1sigma", 0.0),
                    "upper_2sigma": getattr(em, "upper_2sigma", 0.0),
                    "lower_2sigma": getattr(em, "lower_2sigma", 0.0),
                    "em_composite": getattr(em, "em_composite", 0.0),
                    "iv_rv_ratio": getattr(em, "iv_rv_ratio", 1.0),
                    "vol_regime": getattr(em, "vol_regime", "normal"),
                }

        # GEX profile bar chart data
        gex_chart: Dict[str, Any] = {}
        if self.current_gex is not None:
            gex_chart = {
                "net_gex": getattr(self.current_gex, "net_gex", 0.0),
                "gamma_flip_level": getattr(
                    self.current_gex, "gamma_flip_level", 0.0
                ),
                "call_wall": getattr(self.current_gex, "call_wall", 0.0),
                "put_wall": getattr(self.current_gex, "put_wall", 0.0),
                "max_pain": getattr(self.current_gex, "max_pain", 0.0),
                "vol_trigger": getattr(self.current_gex, "vol_trigger", 0.0),
                "spx_price": getattr(self.current_gex, "spx_price", spx_price),
            }

        # Key levels
        key_levels: Dict[str, Any] = {}
        if self.session_setup is not None:
            kl = getattr(self.session_setup, "key_levels", None)
            if kl is not None:
                key_levels = {
                    "options_levels": getattr(kl, "options_levels", {}),
                    "price_action_levels": getattr(
                        kl, "price_action_levels", {}
                    ),
                    "round_numbers": getattr(kl, "round_numbers", []),
                    "moving_averages": getattr(kl, "moving_averages", {}),
                    "market_profile_levels": getattr(
                        kl, "market_profile_levels", {}
                    ),
                }

        # Active positions with P&L
        positions = [
            {
                "signal_id": p.get("signal_id"),
                "direction": p.get("direction"),
                "strategy": p.get("strategy"),
                "entry_price": p.get("entry_price"),
                "size": p.get("size"),
                "pnl": p.get("pnl", 0.0),
                "status": p.get("status"),
            }
            for p in self._active_positions
        ]

        # Session classification
        session_info: Dict[str, Any] = {}
        if self.session_setup is not None:
            st = getattr(self.session_setup, "session_type", None)
            gap = getattr(self.session_setup, "gap_analysis", None)
            session_info = {
                "type": st.name if hasattr(st, "name") else str(st),
                "gap_direction": getattr(gap, "gap_direction", "FLAT") if gap else "FLAT",
                "gap_sigma": getattr(gap, "gap_size_sigma", 0.0) if gap else 0.0,
                "gap_classification": (
                    getattr(gap, "gap_classification", "MICRO") if gap else "MICRO"
                ),
                "vix1d": getattr(self.session_setup, "vix1d", 0.0),
            }

        return {
            "spx_price": spx_price,
            "expected_move": em_data,
            "gex_profile": gex_chart,
            "key_levels": key_levels,
            "active_positions": positions,
            "direction_score": {},  # Populated by directional scanner state
            "recent_signals": [
                {
                    "signal_id": getattr(s, "signal_id", "N/A"),
                    "scan_type": str(getattr(s, "scan_type", "N/A")),
                    "direction": str(getattr(s, "direction", "N/A")),
                    "entry_price": getattr(s, "entry_price", 0.0),
                    "confidence": getattr(s, "confidence", 0.0),
                }
                for s in self.active_signals[-20:]
            ],
            "gex_signals": [
                {
                    "signal_type": getattr(gs, "signal_type", "UNKNOWN"),
                    "description": getattr(gs, "description", ""),
                    "timestamp": str(getattr(gs, "timestamp", "")),
                }
                for gs in self.gex_signals[-10:]
            ],
            "intraday_pnl_curve": self._intraday_pnl_curve,
            "session_classification": session_info,
            "status": self.get_status(),
        }

    # ------------------------------------------------------------------
    # (m) add_alert
    # ------------------------------------------------------------------

    def add_alert(
        self,
        alert_type: str,
        message: str,
        priority: str = "INFO",
    ) -> None:
        """Add an alert to the alert queue for dashboard display.

        Parameters
        ----------
        alert_type : str
            Category of the alert (e.g. ``"TRADE"``, ``"GEX"``,
            ``"RISK"``, ``"PHASE"``, ``"ERROR"``).
        message : str
            Human-readable alert message.
        priority : str
            Priority level: ``"INFO"``, ``"HIGH"``, or ``"CRITICAL"``.
        """
        alert = {
            "type": alert_type,
            "message": message,
            "priority": priority,
            "timestamp": _get_et_now().isoformat(),
        }
        self.alerts.append(alert)

        # Cap alert history at 500 entries
        if len(self.alerts) > 500:
            self.alerts = self.alerts[-500:]

        if priority == "CRITICAL":
            logger.critical("[ALERT] %s: %s", alert_type, message)
        elif priority == "HIGH":
            logger.warning("[ALERT] %s: %s", alert_type, message)
        else:
            logger.info("[ALERT] %s: %s", alert_type, message)

    # ------------------------------------------------------------------
    # (n) save_state
    # ------------------------------------------------------------------

    def save_state(self) -> None:
        """Save current calibration state and configuration to disk.

        Persists to ``<log_dir>/calibration_state.json``.
        """
        state_path = self._log_dir / "calibration_state.json"
        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)

            state_data: Dict[str, Any] = {
                "saved_at": _get_et_now().isoformat(),
                "risk_budget": self._risk_budget,
                "paper_trade": self.paper_trade,
                "data_provider": self._data_provider,
                "scan_count": self.scan_count,
            }

            if self._calibration_state is not None:
                # Serialize calibration state -- attempt to use its own
                # serialization if available, otherwise fall back to __dict__
                if hasattr(self._calibration_state, "to_dict"):
                    state_data["calibration"] = self._calibration_state.to_dict()
                elif hasattr(self._calibration_state, "__dict__"):
                    state_data["calibration"] = {
                        k: v
                        for k, v in self._calibration_state.__dict__.items()
                        if not k.startswith("_")
                    }
                else:
                    state_data["calibration"] = str(self._calibration_state)

            with open(state_path, "w") as f:
                json.dump(state_data, f, indent=2, default=str)

            logger.info("State saved to %s", state_path)
        except Exception:
            logger.exception("Failed to save state to %s", state_path)

    # ------------------------------------------------------------------
    # (o) load_state
    # ------------------------------------------------------------------

    def load_state(self) -> Optional[CalibrationState]:
        """Load calibration state from disk.

        Reads from ``<log_dir>/calibration_state.json``.

        Returns
        -------
        CalibrationState or None
            The loaded state, or ``None`` if no state file exists or
            loading fails.
        """
        state_path = self._log_dir / "calibration_state.json"

        if not state_path.exists():
            logger.debug("No state file found at %s", state_path)
            return None

        try:
            with open(state_path, "r") as f:
                state_data = json.load(f)

            calibration_data = state_data.get("calibration")
            if calibration_data is None:
                logger.info("State file exists but contains no calibration data.")
                return None

            # Reconstruct CalibrationState -- attempt from_dict first
            if hasattr(CalibrationState, "from_dict"):
                cal_state = CalibrationState.from_dict(calibration_data)
            else:
                cal_state = CalibrationState(**calibration_data)

            logger.info(
                "Calibration state loaded from %s (saved at %s).",
                state_path,
                state_data.get("saved_at", "unknown"),
            )
            return cal_state

        except Exception:
            logger.exception("Failed to load state from %s", state_path)
            return None

    # ==================================================================
    # Private helpers
    # ==================================================================

    @staticmethod
    def _classify_time_zone(current_time: time) -> str:
        """Map a time-of-day to an intraday zone label."""
        if current_time < _OPENING_AUCTION_START:
            return "PRE_MARKET"
        elif current_time < _OPENING_AUCTION_END:
            return "OPENING_AUCTION"
        elif current_time < _MORNING_SESSION_END:
            return "MORNING_SESSION"
        elif current_time < _MIDDAY_LULL_END:
            return "MIDDAY_LULL"
        elif current_time < _AFTERNOON_ACCEL_END:
            return "AFTERNOON_ACCEL"
        elif current_time < _POWER_HOUR_END:
            return "POWER_HOUR"
        elif current_time < _SETTLEMENT_END:
            return "SETTLEMENT_WINDOW"
        else:
            return "AFTER_HOURS"

    @staticmethod
    def _get_cycle_interval(zone: str) -> float:
        """Return the scan cycle sleep interval (seconds) for a zone."""
        intervals = {
            "PRE_MARKET": 60.0,
            "OPENING_AUCTION": 5.0,        # Fast data collection, no scanning
            "MORNING_SESSION": _DIRECTIONAL_INTERVAL,
            "MIDDAY_LULL": _DIRECTIONAL_INTERVAL,  # Scanners internally throttle
            "AFTERNOON_ACCEL": _DIRECTIONAL_INTERVAL,
            "POWER_HOUR": _GAMMA_SCALP_INTERVAL,
            "SETTLEMENT_WINDOW": _EXIT_CHECK_INTERVAL,
            "AFTER_HOURS": 300.0,
        }
        return intervals.get(zone, 60.0)

    async def _run_directional_scan(
        self, snapshot: Dict[str, Any]
    ) -> List[ScanSignal]:
        """Execute the directional OTM scanner."""
        try:
            signals = self.directional.scan(
                snapshot=snapshot,
                session_setup=self.session_setup,
                gex_profile=self.current_gex,
            )
            if signals:
                logger.info(
                    "Directional scanner produced %d signal(s).", len(signals)
                )
            return signals if signals else []
        except Exception:
            logger.exception("Directional scanner error.")
            return []

    async def _run_premium_scan(
        self, snapshot: Dict[str, Any]
    ) -> List[ScanSignal]:
        """Execute the premium selling scanner."""
        try:
            signals = self.premium.scan(
                snapshot=snapshot,
                session_setup=self.session_setup,
                gex_profile=self.current_gex,
            )
            if signals:
                logger.info(
                    "Premium scanner produced %d signal(s).", len(signals)
                )
            return signals if signals else []
        except Exception:
            logger.exception("Premium scanner error.")
            return []

    async def _run_gamma_scalp_scan(
        self,
        snapshot: Dict[str, Any],
        prep_only: bool = False,
    ) -> List[ScanSignal]:
        """Execute the gamma scalp scanner.

        Parameters
        ----------
        prep_only : bool
            If ``True``, run in preparation mode (lighter scan for
            pre-positioning).
        """
        try:
            signals = self.gamma_scalp.scan(
                snapshot=snapshot,
                session_setup=self.session_setup,
                gex_profile=self.current_gex,
                prep_only=prep_only,
            )
            if signals:
                mode = "prep" if prep_only else "active"
                logger.info(
                    "Gamma scalp scanner (%s) produced %d signal(s).",
                    mode,
                    len(signals),
                )
            return signals if signals else []
        except Exception:
            logger.exception("Gamma scalp scanner error.")
            return []

    async def _close_position(
        self,
        position: Dict[str, Any],
        reason: str = "UNKNOWN",
        exit_price: Optional[float] = None,
    ) -> None:
        """Close a single position and move it to the closed list."""
        if exit_price is None:
            exit_price = self.data_feed.spx_price

        now = _get_et_now()
        entry_price = position.get("entry_price", 0.0)
        size = position.get("size", 1)
        direction = position.get("direction", "UNKNOWN")

        # P&L calculation (simplified: long profits when price goes up)
        if direction.upper() in ("LONG", "BULLISH", "CALL"):
            pnl = (exit_price - entry_price) * size * 100.0
        elif direction.upper() in ("SHORT", "BEARISH", "PUT"):
            pnl = (entry_price - exit_price) * size * 100.0
        else:
            # Credit spread / premium selling
            pnl = (entry_price - exit_price) * size * 100.0

        position["exit_price"] = exit_price
        position["exit_time"] = now.isoformat()
        position["exit_reason"] = reason
        position["pnl"] = pnl
        position["status"] = "CLOSED"

        # Move from active to closed
        if position in self._active_positions:
            self._active_positions.remove(position)
        self._closed_positions.append(position)
        self._daily_pnl += pnl

        # Log the exit
        self.trade_logger.log_exit(position)

        logger.info(
            "Position closed: %s %s | P&L: $%.2f | Reason: %s",
            direction,
            position.get("signal_id", "N/A"),
            pnl,
            reason,
        )
        self.add_alert(
            "TRADE",
            f"EXIT ({reason}): {direction} {position.get('signal_id', '')} "
            f"P&L ${pnl:+.0f}",
            "HIGH" if abs(pnl) > 100 else "INFO",
        )

    def _record_pnl_snapshot(self) -> None:
        """Record a point on the intraday P&L curve."""
        now = _get_et_now()
        unrealized = sum(p.get("pnl", 0.0) for p in self._active_positions)
        realized = sum(p.get("pnl", 0.0) for p in self._closed_positions)
        self._intraday_pnl_curve.append(
            {
                "time": now.strftime("%H:%M:%S"),
                "realized": realized,
                "unrealized": unrealized,
                "total": realized + unrealized,
            }
        )

    def _compute_max_drawdown(self) -> float:
        """Compute the maximum drawdown from the intraday P&L curve."""
        if not self._intraday_pnl_curve:
            return 0.0

        peak = 0.0
        max_dd = 0.0
        for point in self._intraday_pnl_curve:
            total = point.get("total", 0.0)
            if total > peak:
                peak = total
            dd = peak - total
            if dd > max_dd:
                max_dd = dd

        return max_dd

    async def _wait_until_time(
        self,
        target: time,
        label: str = "",
    ) -> None:
        """Sleep until the given Eastern Time, checking for shutdown.

        If the current time is already past ``target``, returns
        immediately.  Checks for the shutdown event every 5 seconds.

        Parameters
        ----------
        target : time
            The target time of day (Eastern).
        label : str
            Label for logging.
        """
        while not self._shutdown_event.is_set():
            now = _get_et_now()
            if now.time() >= target:
                return

            # Compute remaining seconds
            target_dt = now.replace(
                hour=target.hour,
                minute=target.minute,
                second=target.second,
                microsecond=0,
            )
            remaining = (target_dt - now).total_seconds()
            if remaining <= 0:
                return

            if remaining > 60:
                logger.info(
                    "Waiting for %s (%s): %.0f seconds remaining.",
                    label,
                    target.strftime("%H:%M"),
                    remaining,
                )

            # Sleep in 5-second increments to stay responsive
            wait_time = min(5.0, remaining)
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=wait_time,
                )
                return  # Shutdown requested
            except asyncio.TimeoutError:
                pass


# ============================================================================
# Factory Function
# ============================================================================

def create_scanify_system(
    config: Optional[Dict[str, Any]] = None,
) -> ScanifyOrchestrator:
    """Factory function to create and configure the complete SCANIFY system.

    Accepts an optional configuration dictionary to override defaults.
    Returns a fully configured ``ScanifyOrchestrator`` ready to
    ``initialize()`` and ``run_full_session()``.

    Parameters
    ----------
    config : dict, optional
        Configuration overrides.  Recognised keys:
        - ``data_provider`` (str): Data vendor name.
        - ``api_key`` (str): API key.
        - ``risk_budget`` (float): Daily risk budget ($).
        - ``paper_trade`` (bool): Paper trading mode.
        - ``log_dir`` (str): Log directory path.
        - ``calibration_state`` (CalibrationState): Pre-loaded state.

    Returns
    -------
    ScanifyOrchestrator
        Configured orchestrator instance.

    Examples
    --------
    ::

        system = create_scanify_system({
            "data_provider": "mock",
            "paper_trade": True,
            "risk_budget": 10000,
        })
        await system.initialize()
        report = await system.run_full_session()
        await system.shutdown()
    """
    if config is None:
        config = {}

    orchestrator = ScanifyOrchestrator(
        data_provider=config.get("data_provider", "polygon"),
        api_key=config.get("api_key", os.environ.get("SCANIFY_API_KEY", "")),
        risk_budget=config.get("risk_budget", 10_000.0),
        paper_trade=config.get("paper_trade", True),
        calibration_state=config.get("calibration_state"),
        log_dir=config.get("log_dir", "logs/scanify"),
    )

    logger.info(
        "SCANIFY system created via factory: provider=%s, paper=%s",
        config.get("data_provider", "polygon"),
        config.get("paper_trade", True),
    )

    return orchestrator


# ============================================================================
# CLI Entry Point
# ============================================================================

async def main() -> None:
    """Entry point for running SCANIFY from the command line.

    Usage::

        python -m src.scanify_0dte.orchestrator [--mode paper|live] \\
            [--provider polygon|mock] [--api-key KEY] \\
            [--budget 10000] [--log-dir logs/scanify] [--verbose]

    Parses command-line arguments, creates the system, installs signal
    handlers for graceful shutdown, and runs the full session.
    """
    parser = argparse.ArgumentParser(
        prog="scanify-0dte",
        description=(
            "SCANIFY SPX 0DTE Options Day Trading Scanner. "
            "Runs the complete scanning pipeline from pre-market "
            "through post-market."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=["paper", "live"],
        default="paper",
        help="Trading mode: 'paper' for simulated fills, 'live' for real execution (default: paper).",
    )
    parser.add_argument(
        "--provider",
        choices=["polygon", "alpaca", "cboe", "mock"],
        default="polygon",
        help="Data provider (default: polygon).",
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="API key for the data provider (or set SCANIFY_API_KEY env var).",
    )
    parser.add_argument(
        "--budget",
        type=float,
        default=10_000.0,
        help="Daily risk budget in dollars (default: 10000).",
    )
    parser.add_argument(
        "--log-dir",
        default="logs/scanify",
        help="Directory for logs and reports (default: logs/scanify).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG-level) logging.",
    )

    args = parser.parse_args()

    # ---- Logging setup ----
    log_level = logging.DEBUG if args.verbose else logging.INFO
    log_format = (
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )
    logging.basicConfig(
        level=log_level,
        format=log_format,
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(
                os.path.join(args.log_dir, "scanify.log"),
                mode="a",
            ),
        ],
    )

    # Ensure log directory exists for file handler
    Path(args.log_dir).mkdir(parents=True, exist_ok=True)

    api_key = args.api_key or os.environ.get("SCANIFY_API_KEY", "")

    logger.info("=" * 72)
    logger.info("SCANIFY SPX 0DTE Scanner -- Starting")
    logger.info("=" * 72)
    logger.info("  Mode:     %s", args.mode)
    logger.info("  Provider: %s", args.provider)
    logger.info("  Budget:   $%.0f", args.budget)
    logger.info("  Log dir:  %s", args.log_dir)
    logger.info("  Verbose:  %s", args.verbose)
    logger.info("=" * 72)

    # ---- Create system ----
    system = create_scanify_system(
        {
            "data_provider": args.provider,
            "api_key": api_key,
            "risk_budget": args.budget,
            "paper_trade": args.mode == "paper",
            "log_dir": args.log_dir,
        }
    )

    # ---- Signal handling for graceful shutdown ----
    loop = asyncio.get_running_loop()

    def _signal_handler(sig: int) -> None:
        sig_name = signal.Signals(sig).name
        logger.warning(
            "Received %s -- initiating graceful shutdown...", sig_name
        )
        system.add_alert(
            "SYSTEM",
            f"Shutdown signal received ({sig_name})",
            "CRITICAL",
        )
        # Set the shutdown event so the main loop exits gracefully
        system._shutdown_event.set()

    for sig_num in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig_num, _signal_handler, sig_num)
        except NotImplementedError:
            # Windows does not support add_signal_handler for all signals
            signal.signal(sig_num, lambda s, _f: _signal_handler(s))

    # ---- Initialize and run ----
    try:
        await system.initialize()
        report = await system.run_full_session()

        # Print summary
        pnl_summary = report.get("pnl_summary", {})
        logger.info("=" * 72)
        logger.info("SESSION COMPLETE")
        logger.info(
            "  Total P&L:    $%.2f",
            pnl_summary.get("total_pnl", 0.0),
        )
        logger.info(
            "  Trades:       %d", pnl_summary.get("total_trades", 0)
        )
        logger.info(
            "  Win Rate:     %.1f%%",
            pnl_summary.get("win_rate", 0.0) * 100,
        )
        logger.info(
            "  Max Drawdown: $%.2f",
            pnl_summary.get("max_drawdown", 0.0),
        )
        logger.info("=" * 72)

    except KeyboardInterrupt:
        logger.warning("KeyboardInterrupt received.")
    except Exception:
        logger.exception("Fatal error in SCANIFY session.")
    finally:
        await system.shutdown()
        logger.info("SCANIFY process exiting.")


# ============================================================================
# Module-level execution
# ============================================================================

if __name__ == "__main__":
    asyncio.run(main())
