#!/usr/bin/env python3
"""
SCANIFY 0DTE SPX Scanner - Terminal Dashboard
===============================================

A terminal-based monitoring dashboard for the SCANIFY system.  Uses basic
ANSI escape codes and print formatting -- no external TUI libraries required.

Sections:
    1. Header       -- System title, session type, time zone, countdown
    2. Price Bar    -- SPX, ES, VIX, VIX1D real-time prices
    3. Expected Move -- 1-sigma and 2-sigma implied move boundaries
    4. Key Levels   -- Gamma flip, call wall, put wall, max pain
    5. Direction    -- Composite direction score with sub-factor breakdown
    6. Signals      -- Active scan signals table
    7. Positions    -- Active positions with live P&L
    8. GEX Signals  -- Dealer gamma-exposure driven signals
    9. Daily P&L    -- Running total, win/loss count, win rate
   10. Alerts       -- Recent system alerts and warnings

Refresh:  1-5 seconds (configurable via --refresh).

Usage:
    python scripts/scanify_dashboard.py [options]

    Options:
      --provider polygon|alpaca|mock  Data provider (default: mock)
      --mode paper|live               Trading mode (default: paper)
      --api-key KEY                   API key for data provider
      --risk-budget AMOUNT            Daily risk budget (default: 10000)
      --log-dir DIR                   Log directory (default: logs/scanify)
      --refresh SECONDS               Refresh interval (default: 3)
      --verbose                       Enable verbose logging

Author: Revolution Alpha Engine - SCANIFY Division
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
import time as time_mod
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))
sys.path.insert(0, str(_PROJECT_ROOT))

logger = logging.getLogger("scanify.dashboard")

# ---------------------------------------------------------------------------
# ANSI escape codes
# ---------------------------------------------------------------------------
_USE_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")


class _A:
    """ANSI escape sequences."""
    RESET      = "\033[0m"  if _USE_COLOR else ""
    BOLD       = "\033[1m"  if _USE_COLOR else ""
    DIM        = "\033[2m"  if _USE_COLOR else ""
    UNDERLINE  = "\033[4m"  if _USE_COLOR else ""
    BLINK      = "\033[5m"  if _USE_COLOR else ""
    REVERSE    = "\033[7m"  if _USE_COLOR else ""

    # Foreground
    BLACK      = "\033[30m" if _USE_COLOR else ""
    RED        = "\033[91m" if _USE_COLOR else ""
    GREEN      = "\033[92m" if _USE_COLOR else ""
    YELLOW     = "\033[93m" if _USE_COLOR else ""
    BLUE       = "\033[94m" if _USE_COLOR else ""
    MAGENTA    = "\033[95m" if _USE_COLOR else ""
    CYAN       = "\033[96m" if _USE_COLOR else ""
    WHITE      = "\033[97m" if _USE_COLOR else ""

    # Background
    BG_RED     = "\033[41m" if _USE_COLOR else ""
    BG_GREEN   = "\033[42m" if _USE_COLOR else ""
    BG_YELLOW  = "\033[43m" if _USE_COLOR else ""
    BG_BLUE    = "\033[44m" if _USE_COLOR else ""
    BG_MAGENTA = "\033[45m" if _USE_COLOR else ""
    BG_CYAN    = "\033[46m" if _USE_COLOR else ""
    BG_WHITE   = "\033[47m" if _USE_COLOR else ""

    # Screen control
    CLEAR      = "\033[2J"  if _USE_COLOR else ""
    HOME       = "\033[H"   if _USE_COLOR else ""
    HIDE_CURSOR = "\033[?25l" if _USE_COLOR else ""
    SHOW_CURSOR = "\033[?25h" if _USE_COLOR else ""


# ---------------------------------------------------------------------------
# Terminal width helper
# ---------------------------------------------------------------------------

def _term_width() -> int:
    """Get terminal width, default to 100."""
    try:
        return os.get_terminal_size().columns
    except (OSError, ValueError):
        return 100


# ---------------------------------------------------------------------------
# Eastern-time helpers
# ---------------------------------------------------------------------------

_ET_OFFSET_EST = timezone(timedelta(hours=-5))
_ET_OFFSET_EDT = timezone(timedelta(hours=-4))


def _is_dst_approx(dt: datetime) -> bool:
    """Approximate US Eastern DST check."""
    year = dt.year
    march_start = datetime(year, 3, 8, tzinfo=timezone.utc)
    while march_start.weekday() != 6:
        march_start += timedelta(days=1)
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


def _classify_time_zone(current_time: time) -> str:
    """Map a time-of-day to an intraday zone label."""
    if current_time < time(9, 30):
        return "PRE_MARKET"
    elif current_time < time(9, 45):
        return "OPENING_AUCTION"
    elif current_time < time(11, 30):
        return "MORNING_SESSION"
    elif current_time < time(13, 30):
        return "MIDDAY_LULL"
    elif current_time < time(15, 0):
        return "AFTERNOON_ACCEL"
    elif current_time < time(15, 45):
        return "POWER_HOUR"
    elif current_time < time(16, 0):
        return "SETTLEMENT_WINDOW"
    else:
        return "AFTER_HOURS"


def _minutes_until_close() -> int:
    """Minutes remaining until market close (4:00 PM ET)."""
    now = _get_et_now()
    close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    remaining = (close - now).total_seconds() / 60
    return max(0, int(remaining))


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _pnl_color(value: float) -> str:
    """Return colored string for a P&L value."""
    if value > 0:
        return f"{_A.GREEN}${value:+,.2f}{_A.RESET}"
    elif value < 0:
        return f"{_A.RED}${value:+,.2f}{_A.RESET}"
    return f"${value:,.2f}"


def _direction_color(direction: str) -> str:
    """Return colored string for a direction label."""
    d = direction.upper()
    if "BULL" in d:
        return f"{_A.GREEN}{_A.BOLD}{direction}{_A.RESET}"
    elif "BEAR" in d:
        return f"{_A.RED}{_A.BOLD}{direction}{_A.RESET}"
    return f"{_A.YELLOW}{direction}{_A.RESET}"


def _score_color(score: float) -> str:
    """Return colored string for a direction score."""
    if score >= 40:
        return f"{_A.GREEN}{_A.BOLD}{score:+.0f}{_A.RESET}"
    elif score <= -40:
        return f"{_A.RED}{_A.BOLD}{score:+.0f}{_A.RESET}"
    elif abs(score) >= 20:
        return f"{_A.YELLOW}{score:+.0f}{_A.RESET}"
    return f"{_A.DIM}{score:+.0f}{_A.RESET}"


def _priority_color(priority: str) -> str:
    """Return colored string for an alert priority."""
    p = priority.upper()
    if p == "CRITICAL":
        return f"{_A.BG_RED}{_A.WHITE}{_A.BOLD} {priority} {_A.RESET}"
    elif p == "HIGH":
        return f"{_A.YELLOW}{_A.BOLD}{priority}{_A.RESET}"
    return f"{_A.DIM}{priority}{_A.RESET}"


def _hline(char: str = "-", width: Optional[int] = None) -> str:
    """Horizontal line."""
    w = width or _term_width()
    return char * w


def _center(text: str, width: Optional[int] = None) -> str:
    """Center text within the terminal width (accounts for ANSI codes)."""
    w = width or _term_width()
    # Strip ANSI for length calculation
    import re
    stripped = re.sub(r'\033\[[0-9;]*m', '', text)
    padding = max(0, (w - len(stripped)) // 2)
    return " " * padding + text


def _pad_right(text: str, target_len: int) -> str:
    """Pad text to target length (accounts for ANSI codes)."""
    import re
    stripped = re.sub(r'\033\[[0-9;]*m', '', text)
    pad = max(0, target_len - len(stripped))
    return text + " " * pad


# ============================================================================
# Dashboard Renderer
# ============================================================================

class ScanifyDashboard:
    """Terminal-based dashboard for monitoring the SCANIFY system.

    Connects to a running ScanifyOrchestrator (or creates one in mock mode)
    and periodically refreshes the terminal display with live system data.

    Parameters
    ----------
    provider : str
        Data provider name (``"polygon"``, ``"alpaca"``, ``"mock"``).
    api_key : str
        API key for the data provider.
    mode : str
        Trading mode (``"paper"`` or ``"live"``).
    risk_budget : float
        Daily risk budget in dollars.
    log_dir : str
        Log directory path.
    refresh_interval : float
        Seconds between display refreshes.
    """

    def __init__(
        self,
        provider: str = "mock",
        api_key: str = "",
        mode: str = "paper",
        risk_budget: float = 10_000.0,
        log_dir: str = "logs/scanify",
        refresh_interval: float = 3.0,
    ) -> None:
        self._provider = provider
        self._api_key = api_key
        self._mode = mode
        self._risk_budget = risk_budget
        self._log_dir = log_dir
        self._refresh_interval = max(1.0, min(refresh_interval, 30.0))
        self._running = False
        self._orchestrator = None
        self._frame_count = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Initialize the orchestrator and start the dashboard loop."""
        from src.scanify_0dte.orchestrator import create_scanify_system

        config = {
            "data_provider": self._provider,
            "api_key": self._api_key or os.environ.get("SCANIFY_API_KEY", ""),
            "risk_budget": self._risk_budget,
            "paper_trade": self._mode == "paper",
            "log_dir": self._log_dir,
        }

        self._orchestrator = create_scanify_system(config)

        try:
            await self._orchestrator.initialize()
        except Exception as exc:
            logger.warning("Orchestrator initialization issue (continuing): %s", exc)

        self._running = True

        # Hide cursor for cleaner display
        sys.stdout.write(_A.HIDE_CURSOR)
        sys.stdout.flush()

        # Start the session in the background and run dashboard concurrently
        session_task = asyncio.create_task(self._run_session_background())
        dashboard_task = asyncio.create_task(self._dashboard_loop())

        try:
            await asyncio.gather(dashboard_task, session_task)
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False
            sys.stdout.write(_A.SHOW_CURSOR)
            sys.stdout.flush()

    async def _run_session_background(self) -> None:
        """Run the scanning session in the background."""
        if self._orchestrator is None:
            return
        try:
            await self._orchestrator.run_full_session()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Background session error.")

    async def _dashboard_loop(self) -> None:
        """Main rendering loop -- clears and redraws the terminal."""
        while self._running:
            try:
                self._render_frame()
                self._frame_count += 1
            except Exception:
                logger.exception("Render error.")
            await asyncio.sleep(self._refresh_interval)

    def stop(self) -> None:
        """Stop the dashboard loop."""
        self._running = False
        if self._orchestrator is not None:
            self._orchestrator._shutdown_event.set()

    # ------------------------------------------------------------------
    # Data Retrieval
    # ------------------------------------------------------------------

    def _get_data(self) -> Dict[str, Any]:
        """Get comprehensive data from the orchestrator."""
        if self._orchestrator is None:
            return {}
        try:
            return self._orchestrator.get_dashboard_data()
        except Exception:
            return self._orchestrator.get_status()

    def _get_status(self) -> Dict[str, Any]:
        """Get system status from the orchestrator."""
        if self._orchestrator is None:
            return {}
        try:
            return self._orchestrator.get_status()
        except Exception:
            return {}

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render_frame(self) -> None:
        """Render a single frame of the dashboard."""
        data = self._get_data()
        status = self._get_status()
        w = _term_width()

        lines: List[str] = []
        lines.append(_A.CLEAR + _A.HOME)

        # 1. Header
        lines.extend(self._render_header(data, status, w))
        lines.append("")

        # 2. Price Bar
        lines.extend(self._render_price_bar(data, w))
        lines.append("")

        # 3. Expected Move
        lines.extend(self._render_expected_move(data, w))
        lines.append("")

        # 4. Key Levels
        lines.extend(self._render_key_levels(data, w))
        lines.append("")

        # 5. Direction Score
        lines.extend(self._render_direction_score(data, w))
        lines.append("")

        # 6. Active Signals
        lines.extend(self._render_signals(data, w))
        lines.append("")

        # 7. Positions
        lines.extend(self._render_positions(data, w))
        lines.append("")

        # 8. GEX Signals
        lines.extend(self._render_gex_signals(data, w))
        lines.append("")

        # 9. Daily P&L
        lines.extend(self._render_daily_pnl(data, status, w))
        lines.append("")

        # 10. Alerts
        lines.extend(self._render_alerts(status, w))

        # Footer
        lines.append("")
        lines.append(
            f"  {_A.DIM}Refresh: {self._refresh_interval:.0f}s  |  "
            f"Frame: {self._frame_count}  |  "
            f"Press Ctrl+C to exit{_A.RESET}"
        )

        # Write all at once to minimize flicker
        output = "\n".join(lines)
        sys.stdout.write(output)
        sys.stdout.flush()

    # ------------------------------------------------------------------
    # Section Renderers
    # ------------------------------------------------------------------

    def _render_header(self, data: Dict, status: Dict, w: int) -> List[str]:
        """Render the header section."""
        now = _get_et_now()
        zone = _classify_time_zone(now.time())
        minutes_left = _minutes_until_close()
        session_type = status.get("session_type", data.get("session_classification", {}).get("type", "---"))
        mode_str = f"{_A.YELLOW}PAPER{_A.RESET}" if self._mode == "paper" else f"{_A.RED}{_A.BOLD}LIVE{_A.RESET}"
        is_running = status.get("is_running", False)
        status_str = f"{_A.GREEN}RUNNING{_A.RESET}" if is_running else f"{_A.DIM}IDLE{_A.RESET}"
        data_str = (
            f"{_A.GREEN}CONNECTED{_A.RESET}"
            if status.get("data_connected", False)
            else f"{_A.RED}DISCONNECTED{_A.RESET}"
        )

        lines = []
        lines.append(f"  {_A.BOLD}{_A.CYAN}{_hline('=', w - 4)}{_A.RESET}")
        lines.append(
            f"  {_A.BOLD}{_A.CYAN}  SCANIFY 0DTE SPX Scanner{_A.RESET}"
            f"  {_A.DIM}|{_A.RESET}  "
            f"Session: {_A.BOLD}{session_type}{_A.RESET}"
            f"  {_A.DIM}|{_A.RESET}  "
            f"Zone: {_A.BOLD}{zone}{_A.RESET}"
            f"  {_A.DIM}|{_A.RESET}  "
            f"Minutes Left: {_A.BOLD}{minutes_left}{_A.RESET}"
        )
        lines.append(
            f"  {_A.DIM}  "
            f"{now.strftime('%Y-%m-%d %H:%M:%S ET')}"
            f"  |  Mode: {mode_str}"
            f"  |  Status: {status_str}"
            f"  |  Data: {data_str}"
            f"  |  Provider: {self._provider}"
            f"{_A.RESET}"
        )
        lines.append(f"  {_A.BOLD}{_A.CYAN}{_hline('=', w - 4)}{_A.RESET}")

        return lines

    def _render_price_bar(self, data: Dict, w: int) -> List[str]:
        """Render the price bar section."""
        spx = data.get("spx_price", 0.0)
        gex = data.get("gex_profile", {})
        session = data.get("session_classification", {})
        em = data.get("expected_move", {})

        es = gex.get("spx_price", spx)  # ES usually close to SPX
        vix = session.get("vix1d", 0.0)
        vix1d = session.get("vix1d", 0.0)

        # Try to get VIX from status data
        cross = data.get("cross_asset", {})
        if isinstance(cross, dict):
            vix = cross.get("vix", vix)
            vix1d = cross.get("vix1d", vix1d)

        vol_regime = em.get("vol_regime", "---")

        lines = []
        lines.append(f"  {_A.BOLD}  PRICE BAR{_A.RESET}")
        lines.append(f"  {_hline('-', w - 4)}")

        price_line = (
            f"    SPX: {_A.BOLD}{_A.WHITE}{spx:,.2f}{_A.RESET}"
            f"    {_A.DIM}|{_A.RESET}"
            f"    ES: {_A.BOLD}{es:,.2f}{_A.RESET}"
            f"    {_A.DIM}|{_A.RESET}"
            f"    VIX: {_A.BOLD}{vix:.1f}{_A.RESET}"
            f"    {_A.DIM}|{_A.RESET}"
            f"    VIX1D: {_A.BOLD}{vix1d:.1f}{_A.RESET}"
            f"    {_A.DIM}|{_A.RESET}"
            f"    Vol Regime: {_A.BOLD}{vol_regime}{_A.RESET}"
        )
        lines.append(price_line)

        return lines

    def _render_expected_move(self, data: Dict, w: int) -> List[str]:
        """Render the expected move section."""
        em = data.get("expected_move", {})
        spx = data.get("spx_price", 0.0)

        upper_1s = em.get("upper_1sigma", 0.0)
        lower_1s = em.get("lower_1sigma", 0.0)
        upper_2s = em.get("upper_2sigma", 0.0)
        lower_2s = em.get("lower_2sigma", 0.0)
        em_val = em.get("em_composite", 0.0)
        iv_rv = em.get("iv_rv_ratio", 1.0)

        # If absolute values aren't set, compute from composite
        if upper_1s == 0.0 and em_val > 0 and spx > 0:
            upper_1s = spx + em_val
            lower_1s = spx - em_val
            upper_2s = spx + em_val * 2
            lower_2s = spx - em_val * 2

        # Show as offsets from current price
        off_1s = em_val if em_val > 0 else abs(upper_1s - spx) if upper_1s > 0 else 0
        off_2s = off_1s * 2 if off_1s > 0 else 0

        lines = []
        lines.append(f"  {_A.BOLD}  EXPECTED MOVE{_A.RESET}")
        lines.append(f"  {_hline('-', w - 4)}")

        if off_1s > 0:
            lines.append(
                f"    1-sigma: [{_A.RED}-{off_1s:.1f}{_A.RESET}, "
                f"{_A.GREEN}+{off_1s:.1f}{_A.RESET}]  "
                f"({_A.DIM}{lower_1s:.1f} - {upper_1s:.1f}{_A.RESET})"
                f"    {_A.DIM}|{_A.RESET}    "
                f"2-sigma: [{_A.RED}-{off_2s:.1f}{_A.RESET}, "
                f"{_A.GREEN}+{off_2s:.1f}{_A.RESET}]  "
                f"({_A.DIM}{lower_2s:.1f} - {upper_2s:.1f}{_A.RESET})"
                f"    {_A.DIM}|{_A.RESET}    "
                f"IV/RV: {_A.BOLD}{iv_rv:.2f}{_A.RESET}"
            )
        else:
            lines.append(f"    {_A.DIM}No expected move data available{_A.RESET}")

        return lines

    def _render_key_levels(self, data: Dict, w: int) -> List[str]:
        """Render the key GEX levels section."""
        gex = data.get("gex_profile", {})
        kl = data.get("key_levels", {})

        gamma_flip = gex.get("gamma_flip_level", 0.0)
        call_wall = gex.get("call_wall", 0.0)
        put_wall = gex.get("put_wall", 0.0)
        max_pain = gex.get("max_pain", 0.0)
        vol_trigger = gex.get("vol_trigger", 0.0)
        net_gex = gex.get("net_gex", 0.0)

        gex_regime = f"{_A.GREEN}POSITIVE (dampening){_A.RESET}" if net_gex > 0 else f"{_A.RED}NEGATIVE (amplifying){_A.RESET}"

        lines = []
        lines.append(f"  {_A.BOLD}  KEY LEVELS{_A.RESET}")
        lines.append(f"  {_hline('-', w - 4)}")

        if gamma_flip > 0:
            lines.append(
                f"    Gamma Flip: {_A.BOLD}{_A.MAGENTA}{gamma_flip:,.0f}{_A.RESET}"
                f"    {_A.DIM}|{_A.RESET}"
                f"    Call Wall: {_A.GREEN}{call_wall:,.0f}{_A.RESET}"
                f"    {_A.DIM}|{_A.RESET}"
                f"    Put Wall: {_A.RED}{put_wall:,.0f}{_A.RESET}"
                f"    {_A.DIM}|{_A.RESET}"
                f"    Max Pain: {_A.YELLOW}{max_pain:,.0f}{_A.RESET}"
                f"    {_A.DIM}|{_A.RESET}"
                f"    Vol Trigger: {_A.CYAN}{vol_trigger:,.0f}{_A.RESET}"
            )
            lines.append(
                f"    GEX Regime: {gex_regime}"
                f"    {_A.DIM}|{_A.RESET}"
                f"    Net GEX: {_A.BOLD}{net_gex:,.0f}{_A.RESET}"
            )
        else:
            lines.append(f"    {_A.DIM}No GEX level data available{_A.RESET}")

        return lines

    def _render_direction_score(self, data: Dict, w: int) -> List[str]:
        """Render the composite direction score section."""
        ds = data.get("direction_score", {})

        total = ds.get("total_score", 0.0)
        internals = ds.get("market_internals_score", 0.0)
        flow = ds.get("options_flow_score", 0.0)
        price = ds.get("price_action_score", 0.0)
        gex = ds.get("gex_structure_score", 0.0)
        cross = ds.get("cross_asset_score", 0.0)
        signal_dir = ds.get("signal", "NEUTRAL")
        confidence = ds.get("confidence", 0.0)
        factors_agreeing = ds.get("factors_agreeing", 0)

        lines = []
        lines.append(f"  {_A.BOLD}  DIRECTION SCORE{_A.RESET}")
        lines.append(f"  {_hline('-', w - 4)}")

        if ds:
            # Score bar visualization
            bar_width = 40
            bar_pos = int((total + 100) / 200 * bar_width)
            bar_pos = max(0, min(bar_width, bar_pos))
            bar = ""
            for i in range(bar_width):
                if i == bar_width // 2:
                    bar += "|"
                elif i == bar_pos:
                    bar += f"{_A.BOLD}X{_A.RESET}"
                elif i < bar_width // 2:
                    bar += f"{_A.RED}.{_A.RESET}" if i < bar_pos else " "
                else:
                    bar += f"{_A.GREEN}.{_A.RESET}" if i < bar_pos else " "

            direction_str = _direction_color(signal_dir)
            lines.append(
                f"    [{_score_color(total)}] {direction_str}"
                f"    Confidence: {_A.BOLD}{confidence:.0f}%{_A.RESET}"
                f"    Factors: {_A.BOLD}{factors_agreeing}/5{_A.RESET}"
            )
            lines.append(
                f"    {_A.RED}-100{_A.RESET} [{bar}] {_A.GREEN}+100{_A.RESET}"
            )
            lines.append(
                f"    Internals: {_score_color(internals)}"
                f"  {_A.DIM}|{_A.RESET}"
                f"  Flow: {_score_color(flow)}"
                f"  {_A.DIM}|{_A.RESET}"
                f"  Price: {_score_color(price)}"
                f"  {_A.DIM}|{_A.RESET}"
                f"  GEX: {_score_color(gex)}"
                f"  {_A.DIM}|{_A.RESET}"
                f"  Cross: {_score_color(cross)}"
            )
        else:
            lines.append(f"    {_A.DIM}Awaiting first scan cycle...{_A.RESET}")

        return lines

    def _render_signals(self, data: Dict, w: int) -> List[str]:
        """Render the active signals table."""
        signals = data.get("recent_signals", [])

        lines = []
        lines.append(f"  {_A.BOLD}  ACTIVE SIGNALS{_A.RESET}")
        lines.append(f"  {_hline('-', w - 4)}")

        if signals:
            # Header row
            lines.append(
                f"    {_A.UNDERLINE}"
                f"{'#':>3}  "
                f"{'Direction':<10}  "
                f"{'Type':<14}  "
                f"{'Entry':>8}  "
                f"{'Confidence':>10}  "
                f"{'Signal ID':<20}"
                f"{_A.RESET}"
            )
            for i, sig in enumerate(signals[-8:], 1):
                direction = str(sig.get("direction", "N/A"))
                scan_type = str(sig.get("scan_type", "N/A"))
                entry = sig.get("entry_price", 0.0)
                confidence = sig.get("confidence", 0.0)
                sig_id = str(sig.get("signal_id", "N/A"))[:20]

                dir_str = _direction_color(direction)
                lines.append(
                    f"    {i:>3}  "
                    f"{_pad_right(dir_str, 10)}  "
                    f"{scan_type:<14}  "
                    f"${entry:>7.2f}  "
                    f"{confidence:>9.0f}%  "
                    f"{sig_id:<20}"
                )
        else:
            lines.append(f"    {_A.DIM}No active signals{_A.RESET}")

        return lines

    def _render_positions(self, data: Dict, w: int) -> List[str]:
        """Render the active positions table."""
        positions = data.get("active_positions", [])

        lines = []
        lines.append(f"  {_A.BOLD}  POSITIONS{_A.RESET}")
        lines.append(f"  {_hline('-', w - 4)}")

        if positions:
            # Header row
            lines.append(
                f"    {_A.UNDERLINE}"
                f"{'#':>3}  "
                f"{'Direction':<10}  "
                f"{'Strategy':<14}  "
                f"{'Entry':>8}  "
                f"{'Size':>5}  "
                f"{'P&L':>10}  "
                f"{'Status':<8}  "
                f"{'Signal ID':<16}"
                f"{_A.RESET}"
            )
            for i, pos in enumerate(positions[-8:], 1):
                direction = str(pos.get("direction", "N/A"))
                strategy = str(pos.get("strategy", "N/A"))
                entry = pos.get("entry_price", 0.0)
                size = pos.get("size", 0)
                pnl = pos.get("pnl", 0.0)
                pos_status = str(pos.get("status", "OPEN"))
                sig_id = str(pos.get("signal_id", "N/A"))[:16]

                dir_str = _direction_color(direction)
                pnl_str = _pnl_color(pnl)

                lines.append(
                    f"    {i:>3}  "
                    f"{_pad_right(dir_str, 10)}  "
                    f"{strategy:<14}  "
                    f"${entry:>7.2f}  "
                    f"{size:>5}  "
                    f"{_pad_right(pnl_str, 10)}  "
                    f"{pos_status:<8}  "
                    f"{sig_id:<16}"
                )
        else:
            lines.append(f"    {_A.DIM}No active positions{_A.RESET}")

        return lines

    def _render_gex_signals(self, data: Dict, w: int) -> List[str]:
        """Render the GEX signals list."""
        gex_signals = data.get("gex_signals", [])

        lines = []
        lines.append(f"  {_A.BOLD}  GEX SIGNALS{_A.RESET}")
        lines.append(f"  {_hline('-', w - 4)}")

        if gex_signals:
            for gs in gex_signals[-5:]:
                sig_type = str(gs.get("signal_type", "UNKNOWN"))
                description = str(gs.get("description", ""))[:60]
                timestamp = str(gs.get("timestamp", ""))[:19]

                type_color = _A.MAGENTA
                if "FLIP" in sig_type.upper():
                    type_color = _A.RED + _A.BOLD
                elif "WALL" in sig_type.upper():
                    type_color = _A.YELLOW
                elif "COLLAPSE" in sig_type.upper():
                    type_color = _A.RED

                lines.append(
                    f"    {_A.DIM}{timestamp}{_A.RESET}  "
                    f"{type_color}{sig_type}{_A.RESET}  "
                    f"{_A.DIM}{description}{_A.RESET}"
                )
        else:
            lines.append(f"    {_A.DIM}No GEX signals active{_A.RESET}")

        return lines

    def _render_daily_pnl(self, data: Dict, status: Dict, w: int) -> List[str]:
        """Render the daily P&L summary."""
        total = status.get("total_pnl", 0.0)
        realized = status.get("realized_pnl", 0.0)
        unrealized = status.get("unrealized_pnl", 0.0)
        budget_remaining = status.get("risk_budget_remaining", self._risk_budget)

        # Count wins/losses from orchestrator
        wins = 0
        losses = 0
        if self._orchestrator is not None:
            wins = len([p for p in self._orchestrator._closed_positions if p.get("pnl", 0) > 0])
            losses = len([p for p in self._orchestrator._closed_positions if p.get("pnl", 0) <= 0])

        total_trades = wins + losses
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0

        lines = []
        lines.append(f"  {_A.BOLD}  DAILY P&L{_A.RESET}")
        lines.append(f"  {_hline('-', w - 4)}")

        total_str = _pnl_color(total)
        realized_str = _pnl_color(realized)
        unrealized_str = _pnl_color(unrealized)

        lines.append(
            f"    Total: {_A.BOLD}{total_str}{_A.RESET}"
            f"    {_A.DIM}|{_A.RESET}"
            f"    Realized: {realized_str}"
            f"    {_A.DIM}|{_A.RESET}"
            f"    Unrealized: {unrealized_str}"
            f"    {_A.DIM}|{_A.RESET}"
            f"    Budget Remaining: {_A.BOLD}${budget_remaining:,.0f}{_A.RESET}"
        )
        lines.append(
            f"    Wins: {_A.GREEN}{wins}{_A.RESET}"
            f"    {_A.DIM}|{_A.RESET}"
            f"    Losses: {_A.RED}{losses}{_A.RESET}"
            f"    {_A.DIM}|{_A.RESET}"
            f"    Win Rate: {_A.BOLD}{win_rate:.1f}%{_A.RESET}"
            f"    {_A.DIM}|{_A.RESET}"
            f"    Total Trades: {_A.BOLD}{total_trades}{_A.RESET}"
            f"    {_A.DIM}|{_A.RESET}"
            f"    Scans: {_A.BOLD}{status.get('scan_count', 0)}{_A.RESET}"
        )

        # Simple P&L bar
        bar_width = 40
        max_val = max(abs(total), self._risk_budget * 0.06, 1.0)
        bar_pos = int((total / max_val + 1) / 2 * bar_width)
        bar_pos = max(0, min(bar_width, bar_pos))
        center = bar_width // 2
        bar = ""
        for i in range(bar_width):
            if i == center:
                bar += "|"
            elif center < bar_pos and center < i <= bar_pos:
                bar += f"{_A.GREEN}#{_A.RESET}"
            elif bar_pos < center and bar_pos <= i < center:
                bar += f"{_A.RED}#{_A.RESET}"
            else:
                bar += " "
        lines.append(
            f"    {_A.RED}-max{_A.RESET} [{bar}] {_A.GREEN}+max{_A.RESET}"
        )

        return lines

    def _render_alerts(self, status: Dict, w: int) -> List[str]:
        """Render the recent alerts section."""
        alerts = status.get("recent_alerts", [])

        lines = []
        lines.append(f"  {_A.BOLD}  ALERTS{_A.RESET}")
        lines.append(f"  {_hline('-', w - 4)}")

        if alerts:
            for alert in alerts[-8:]:
                ts = str(alert.get("timestamp", ""))[:19]
                alert_type = str(alert.get("type", "INFO"))
                message = str(alert.get("message", ""))
                priority = str(alert.get("priority", "INFO"))

                prio_str = _priority_color(priority)

                # Color the alert type
                type_color = _A.DIM
                if alert_type in ("TRADE", "GEX"):
                    type_color = _A.CYAN
                elif alert_type in ("RISK", "ERROR"):
                    type_color = _A.RED
                elif alert_type == "PHASE":
                    type_color = _A.YELLOW

                lines.append(
                    f"    {_A.DIM}{ts}{_A.RESET}  "
                    f"{prio_str}  "
                    f"{type_color}{alert_type:8s}{_A.RESET}  "
                    f"{message}"
                )
        else:
            lines.append(f"    {_A.DIM}No recent alerts{_A.RESET}")

        return lines


# ============================================================================
# Argument Parser
# ============================================================================

def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the dashboard."""
    parser = argparse.ArgumentParser(
        prog="scanify_dashboard",
        description="SCANIFY 0DTE SPX Scanner - Terminal Dashboard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/scanify_dashboard.py --provider mock
  python scripts/scanify_dashboard.py --provider polygon --api-key YOUR_KEY
  python scripts/scanify_dashboard.py --refresh 1 --verbose
""",
    )

    parser.add_argument(
        "--provider",
        choices=["polygon", "alpaca", "mock"],
        default="mock",
        help="Data provider (default: mock)",
    )
    parser.add_argument(
        "--mode",
        choices=["paper", "live"],
        default="paper",
        help="Trading mode (default: paper)",
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="API key for data provider",
    )
    parser.add_argument(
        "--risk-budget",
        type=float,
        default=10000.0,
        help="Daily risk budget in dollars (default: 10000)",
    )
    parser.add_argument(
        "--log-dir",
        default="logs/scanify",
        help="Log directory (default: logs/scanify)",
    )
    parser.add_argument(
        "--refresh",
        type=float,
        default=3.0,
        help="Refresh interval in seconds (default: 3)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    return parser


# ============================================================================
# Main entry point
# ============================================================================

async def _async_main() -> int:
    """Async main entry point."""
    parser = _build_parser()
    args = parser.parse_args()

    # Setup logging (minimal -- dashboard owns the screen)
    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    log_level = logging.DEBUG if args.verbose else logging.WARNING
    log_file = log_dir / "scanify_dashboard.log"
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(str(log_file), mode="a"),
        ],
        force=True,
    )

    # Create dashboard
    dashboard = ScanifyDashboard(
        provider=args.provider,
        api_key=args.api_key,
        mode=args.mode,
        risk_budget=args.risk_budget,
        log_dir=args.log_dir,
        refresh_interval=args.refresh,
    )

    # Signal handling
    def _handle_shutdown(sig_num: int) -> None:
        dashboard.stop()

    loop = asyncio.get_running_loop()
    for sig_num in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig_num, _handle_shutdown, sig_num)
        except NotImplementedError:
            signal.signal(sig_num, lambda s, _f: _handle_shutdown(s))

    # Run the dashboard
    try:
        await dashboard.start()
    except asyncio.CancelledError:
        pass
    except KeyboardInterrupt:
        pass
    finally:
        # Restore terminal
        sys.stdout.write(_A.SHOW_CURSOR)
        sys.stdout.write("\n")
        sys.stdout.flush()

    return 0


def main() -> None:
    """Synchronous wrapper."""
    try:
        exit_code = asyncio.run(_async_main())
    except KeyboardInterrupt:
        sys.stdout.write(_A.SHOW_CURSOR + "\n")
        sys.stdout.flush()
        exit_code = 0
    except Exception as exc:
        sys.stdout.write(_A.SHOW_CURSOR + "\n")
        sys.stdout.flush()
        print(f"Fatal error: {exc}", file=sys.stderr)
        exit_code = 1

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
