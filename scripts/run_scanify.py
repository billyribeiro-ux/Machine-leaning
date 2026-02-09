#!/usr/bin/env python3
"""
SCANIFY 0DTE SPX Scanner - Command-Line Runner
================================================

Production command-line interface for the SCANIFY SPX 0DTE Options Day Trading
Scanner + GEX Scanner system.  Provides commands for live scanning, backtesting,
calibration, status inspection, and launching the terminal dashboard.

Usage:
    python scripts/run_scanify.py live [options]        Run live scanner session
    python scripts/run_scanify.py backtest [options]    Run backtesting
    python scripts/run_scanify.py calibrate [options]   Run calibration manually
    python scripts/run_scanify.py status [options]      Show system status
    python scripts/run_scanify.py dashboard [options]   Launch dashboard view

Examples:
    python scripts/run_scanify.py live --mode paper --provider mock
    python scripts/run_scanify.py live --mode paper --provider polygon --api-key YOUR_KEY
    python scripts/run_scanify.py backtest --start-date 2024-01-01 --end-date 2024-12-31
    python scripts/run_scanify.py calibrate --verbose
    python scripts/run_scanify.py status
    python scripts/run_scanify.py dashboard --provider mock

Author: Revolution Alpha Engine - SCANIFY Division
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import time as time_mod
import traceback
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Path setup -- ensure src/ is importable
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))
sys.path.insert(0, str(_PROJECT_ROOT))

logger = logging.getLogger("scanify.runner")

# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------
__version__ = "1.0.0"

# ---------------------------------------------------------------------------
# ASCII Banner
# ---------------------------------------------------------------------------
SCANIFY_BANNER = r"""
 ___  ___   _   _  _ ___ _____   __
/ __|/ __| /_\ | \| |_ _|  ___| /  \ ___  ___ _____
\__ \ (__ / _ \| .` || || |_   | () |   \|   \_   _|
|___/\___/_/ \_\_|\_|___|_|    |_/\_\|_\_\___|___|_|

    SCANIFY 0DTE SPX Options Scanner + GEX Scanner  v{version}
    -------------------------------------------------------
    Institutional-Grade Intraday Options Intelligence
""".format(version=__version__)

# ---------------------------------------------------------------------------
# ANSI colour codes (disabled if NO_COLOR env var is set or not a TTY)
# ---------------------------------------------------------------------------
_USE_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")


class _C:
    """ANSI colour constants."""
    RESET  = "\033[0m"  if _USE_COLOR else ""
    BOLD   = "\033[1m"  if _USE_COLOR else ""
    DIM    = "\033[2m"  if _USE_COLOR else ""
    RED    = "\033[91m" if _USE_COLOR else ""
    GREEN  = "\033[92m" if _USE_COLOR else ""
    YELLOW = "\033[93m" if _USE_COLOR else ""
    BLUE   = "\033[94m" if _USE_COLOR else ""
    CYAN   = "\033[96m" if _USE_COLOR else ""
    WHITE  = "\033[97m" if _USE_COLOR else ""
    MAGENTA = "\033[95m" if _USE_COLOR else ""
    BG_RED = "\033[41m" if _USE_COLOR else ""
    BG_GREEN = "\033[42m" if _USE_COLOR else ""


def _ts() -> str:
    """Return a formatted timestamp string."""
    return datetime.now().strftime("%H:%M:%S")


def _print_status(message: str, level: str = "info") -> None:
    """Print a coloured status message to the console."""
    icons = {
        "info":     f"{_C.CYAN}[*]{_C.RESET}",
        "success":  f"{_C.GREEN}[+]{_C.RESET}",
        "warning":  f"{_C.YELLOW}[!]{_C.RESET}",
        "error":    f"{_C.RED}[X]{_C.RESET}",
        "critical": f"{_C.BG_RED}{_C.WHITE}[!!!]{_C.RESET}",
        "signal":   f"{_C.MAGENTA}[>>]{_C.RESET}",
        "trade":    f"{_C.GREEN}{_C.BOLD}[$]{_C.RESET}",
        "pnl":      f"{_C.BOLD}[P&L]{_C.RESET}",
    }
    icon = icons.get(level, icons["info"])
    print(f"  {_C.DIM}{_ts()}{_C.RESET} {icon} {message}")


def _print_signal(direction: str, scan_type: str, strike: float,
                  confidence: float, entry: float) -> None:
    """Print a formatted signal alert."""
    dir_color = _C.GREEN if "BULL" in direction.upper() else _C.RED
    print(f"\n  {_C.BOLD}{_C.MAGENTA}{'=' * 60}{_C.RESET}")
    print(f"  {_C.BOLD}  NEW SIGNAL{_C.RESET}")
    print(f"  {_C.DIM}  {_ts()}{_C.RESET}  "
          f"{dir_color}{_C.BOLD}{direction}{_C.RESET}  "
          f"{scan_type}  Strike: {strike:.0f}  "
          f"Confidence: {confidence:.0f}%  Entry: ${entry:.2f}")
    print(f"  {_C.BOLD}{_C.MAGENTA}{'=' * 60}{_C.RESET}\n")


def _print_pnl(realized: float, unrealized: float, total: float,
               wins: int, losses: int) -> None:
    """Print a formatted P&L summary line."""
    total_color = _C.GREEN if total >= 0 else _C.RED
    win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0.0
    print(
        f"  {_C.DIM}{_ts()}{_C.RESET} {_C.BOLD}[P&L]{_C.RESET} "
        f"Total: {total_color}${total:+,.2f}{_C.RESET}  "
        f"Realized: ${realized:+,.2f}  Unrealized: ${unrealized:+,.2f}  "
        f"W/L: {_C.GREEN}{wins}{_C.RESET}/{_C.RED}{losses}{_C.RESET} "
        f"({win_rate:.0f}%)"
    )


def _print_health(data_connected: bool, scan_count: int,
                  positions: int, zone: str, minutes_left: int) -> None:
    """Print a system health status line."""
    conn_str = f"{_C.GREEN}CONNECTED{_C.RESET}" if data_connected else f"{_C.RED}DISCONNECTED{_C.RESET}"
    print(
        f"  {_C.DIM}{_ts()}{_C.RESET} {_C.CYAN}[SYS]{_C.RESET} "
        f"Data: {conn_str}  Scans: {scan_count}  "
        f"Positions: {positions}  Zone: {_C.BOLD}{zone}{_C.RESET}  "
        f"Minutes Left: {minutes_left}"
    )


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def _setup_logging(log_dir: str, verbose: bool) -> None:
    """Configure logging for the SCANIFY runner."""
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    log_level = logging.DEBUG if verbose else logging.INFO
    log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

    handlers: List[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
    ]

    # File handler
    log_file = log_path / "scanify_runner.log"
    try:
        file_handler = logging.FileHandler(str(log_file), mode="a")
        file_handler.setLevel(log_level)
        file_handler.setFormatter(logging.Formatter(log_format, datefmt="%Y-%m-%d %H:%M:%S"))
        handlers.append(file_handler)
    except OSError as exc:
        print(f"  {_C.YELLOW}[!]{_C.RESET} Could not create log file {log_file}: {exc}")

    logging.basicConfig(
        level=log_level,
        format=log_format,
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
        force=True,
    )

    # Suppress noisy third-party loggers
    for noisy in ("urllib3", "asyncio", "websockets"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


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


# ============================================================================
# Command: live
# ============================================================================

async def _cmd_live(args: argparse.Namespace) -> int:
    """Run a live (or paper) scanning session."""
    from src.scanify_0dte.orchestrator import ScanifyOrchestrator, create_scanify_system

    paper = args.mode == "paper"
    mode_label = f"{_C.YELLOW}PAPER{_C.RESET}" if paper else f"{_C.RED}{_C.BOLD}LIVE{_C.RESET}"

    print(f"\n  Starting SCANIFY in {mode_label} mode")
    print(f"  Provider: {_C.BOLD}{args.provider}{_C.RESET}")
    print(f"  Risk Budget: {_C.BOLD}${args.risk_budget:,.0f}{_C.RESET}")
    if args.scan_types != "all":
        print(f"  Scan Types: {_C.BOLD}{args.scan_types}{_C.RESET}")
    print()

    # Build configuration
    config: Dict[str, Any] = {
        "data_provider": args.provider,
        "api_key": args.api_key or os.environ.get("SCANIFY_API_KEY", ""),
        "risk_budget": args.risk_budget,
        "paper_trade": paper,
        "log_dir": args.log_dir,
    }

    # Create system
    system = create_scanify_system(config)

    # ---- Signal handling for graceful shutdown ----
    shutdown_requested = False

    def _handle_shutdown(sig_num: int) -> None:
        nonlocal shutdown_requested
        sig_name = signal.Signals(sig_num).name
        if not shutdown_requested:
            shutdown_requested = True
            _print_status(
                f"Received {_C.BOLD}{sig_name}{_C.RESET} -- initiating graceful shutdown...",
                "warning",
            )
            system._shutdown_event.set()
        else:
            _print_status(
                f"Received {_C.BOLD}{sig_name}{_C.RESET} again -- forcing exit.",
                "critical",
            )
            sys.exit(1)

    loop = asyncio.get_running_loop()
    for sig_num in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig_num, _handle_shutdown, sig_num)
        except NotImplementedError:
            signal.signal(sig_num, lambda s, _f: _handle_shutdown(s))

    # ---- Initialize ----
    _print_status("Initializing SCANIFY system...", "info")
    try:
        await system.initialize()
        _print_status("System initialized successfully.", "success")
    except Exception as exc:
        _print_status(f"Initialization failed: {exc}", "error")
        logger.exception("Initialization failed.")
        return 1

    # ---- Monitoring task ----
    _last_signal_count = 0
    _last_pnl_report = 0.0

    async def _monitor_loop() -> None:
        """Periodically print status, P&L, and health to the console."""
        nonlocal _last_signal_count, _last_pnl_report
        interval = 30  # seconds between health prints
        pnl_interval = 60  # seconds between P&L prints

        last_health_time = 0.0
        last_pnl_time = 0.0

        while not system._shutdown_event.is_set():
            try:
                now = time_mod.time()

                # Check for new signals
                current_signal_count = len(system.active_signals)
                if current_signal_count > _last_signal_count:
                    for sig in system.active_signals[_last_signal_count:]:
                        direction = str(getattr(sig, "direction", "UNKNOWN"))
                        scan_type = str(getattr(sig, "scan_type", "UNKNOWN"))
                        strike = 0.0
                        ss = getattr(sig, "strike_selection", None)
                        if ss is not None:
                            strike = getattr(ss, "strike", 0.0)
                        confidence = getattr(
                            getattr(sig, "direction_score", None),
                            "confidence", 0.0,
                        )
                        entry = getattr(sig, "entry_price", 0.0)
                        _print_signal(direction, scan_type, strike, confidence, entry)
                    _last_signal_count = current_signal_count

                # Health check
                if now - last_health_time >= interval:
                    status = system.get_status()
                    _print_health(
                        data_connected=status.get("data_connected", False),
                        scan_count=status.get("scan_count", 0),
                        positions=status.get("active_positions", 0),
                        zone=status.get("time_zone", "UNKNOWN"),
                        minutes_left=status.get("minutes_remaining", 0),
                    )
                    last_health_time = now

                # P&L report
                if now - last_pnl_time >= pnl_interval:
                    status = system.get_status()
                    realized = status.get("realized_pnl", 0.0)
                    unrealized = status.get("unrealized_pnl", 0.0)
                    total = status.get("total_pnl", 0.0)
                    wins = len([p for p in system._closed_positions if p.get("pnl", 0) > 0])
                    losses = len([p for p in system._closed_positions if p.get("pnl", 0) <= 0])
                    if system._closed_positions or system._active_positions:
                        _print_pnl(realized, unrealized, total, wins, losses)
                    last_pnl_time = now

                # Print recent alerts
                recent_alerts = system.alerts[-5:]
                for alert in recent_alerts:
                    priority = alert.get("priority", "INFO")
                    if priority == "CRITICAL":
                        _print_status(
                            f"{_C.RED}{alert.get('type', 'ALERT')}: "
                            f"{alert.get('message', '')}{_C.RESET}",
                            "critical",
                        )
                    elif priority == "HIGH":
                        _print_status(
                            f"{alert.get('type', 'ALERT')}: {alert.get('message', '')}",
                            "warning",
                        )

                await asyncio.sleep(5)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Monitor loop error.")
                await asyncio.sleep(10)

    # ---- Run session with monitoring ----
    try:
        _print_status("Starting full trading session...", "info")
        monitor_task = asyncio.create_task(_monitor_loop())

        report = await system.run_full_session()

        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass

        # ---- Print final session summary ----
        pnl_summary = report.get("pnl_summary", {})
        total_pnl = pnl_summary.get("total_pnl", 0.0)
        total_trades = pnl_summary.get("total_trades", 0)
        win_rate = pnl_summary.get("win_rate", 0.0)
        max_dd = pnl_summary.get("max_drawdown", 0.0)
        profit_factor = pnl_summary.get("profit_factor", 0.0)

        pnl_color = _C.GREEN if total_pnl >= 0 else _C.RED
        print(f"\n  {_C.BOLD}{'=' * 60}{_C.RESET}")
        print(f"  {_C.BOLD}  SESSION COMPLETE{_C.RESET}")
        print(f"  {_C.BOLD}{'=' * 60}{_C.RESET}")
        print(f"    Date:           {report.get('date', 'N/A')}")
        print(f"    Session Type:   {_C.BOLD}{report.get('session_type', 'N/A')}{_C.RESET}")
        print(f"    Total P&L:      {pnl_color}{_C.BOLD}${total_pnl:+,.2f}{_C.RESET}")
        print(f"    Total Trades:   {total_trades}")
        print(f"    Win Rate:       {win_rate * 100:.1f}%")
        print(f"    Profit Factor:  {profit_factor:.2f}")
        print(f"    Max Drawdown:   ${max_dd:,.2f}")
        print(f"    Scan Cycles:    {report.get('scan_count', 0)}")
        print(f"  {_C.BOLD}{'=' * 60}{_C.RESET}\n")

        return 0

    except Exception as exc:
        _print_status(f"Session error: {exc}", "error")
        logger.exception("Fatal session error.")
        return 1
    finally:
        _print_status("Shutting down...", "warning")
        try:
            await system.shutdown()
        except Exception:
            logger.exception("Error during shutdown.")
        _print_status("Shutdown complete.", "success")


# ============================================================================
# Command: backtest
# ============================================================================

async def _cmd_backtest(args: argparse.Namespace) -> int:
    """Run backtesting over a historical date range."""
    from src.scanify_0dte.backtester import BacktestConfig, BacktestEngine
    from src.scanify_0dte.models import ScanType

    # Parse dates
    try:
        start = date.fromisoformat(args.start_date) if args.start_date else date(2024, 1, 1)
        end = date.fromisoformat(args.end_date) if args.end_date else date.today()
    except ValueError as exc:
        _print_status(f"Invalid date format: {exc}. Use YYYY-MM-DD.", "error")
        return 1

    # Parse scan types
    scan_type_filter: Optional[List[ScanType]] = None
    if args.scan_types != "all":
        type_map = {
            "directional": ScanType.DIRECTIONAL,
            "premium": ScanType.PREMIUM_SELL,
            "gamma": ScanType.GAMMA_SCALP,
        }
        scan_type_filter = []
        for t in args.scan_types.split(","):
            t = t.strip().lower()
            if t in type_map:
                scan_type_filter.append(type_map[t])
            else:
                _print_status(f"Unknown scan type '{t}'. Valid: directional, premium, gamma", "error")
                return 1

    print(f"\n  {_C.BOLD}SCANIFY Backtester{_C.RESET}")
    print(f"  Period:     {_C.BOLD}{start} -> {end}{_C.RESET}")
    print(f"  Scan Types: {_C.BOLD}{args.scan_types}{_C.RESET}")
    print(f"  Risk Budget: {_C.BOLD}${args.risk_budget:,.0f}{_C.RESET}")
    print()

    _print_status("Configuring backtest engine...", "info")

    try:
        config = BacktestConfig(
            start_date=start,
            end_date=end,
            initial_capital=args.risk_budget * 10,
        )
    except Exception as exc:
        _print_status(f"Failed to create backtest config: {exc}", "error")
        return 1

    try:
        engine = BacktestEngine(config=config)
    except Exception as exc:
        _print_status(f"Failed to create backtest engine: {exc}", "error")
        return 1

    _print_status("Running backtest (this may take a while)...", "info")
    start_time = time_mod.time()

    try:
        results = engine.run_backtest(scan_types=scan_type_filter)
    except Exception as exc:
        _print_status(f"Backtest failed: {exc}", "error")
        logger.exception("Backtest failed.")
        return 1

    elapsed = time_mod.time() - start_time
    _print_status(f"Backtest completed in {elapsed:.1f}s", "success")

    # Print results summary
    total_pnl = results.get("total_pnl", 0.0)
    total_trades = results.get("total_trades", 0)
    win_rate = results.get("win_rate", 0.0)
    sharpe = results.get("sharpe_ratio", 0.0)
    max_dd = results.get("max_drawdown", 0.0)
    profit_factor = results.get("profit_factor", 0.0)
    deflated_sharpe = results.get("deflated_sharpe", 0.0)

    pnl_color = _C.GREEN if total_pnl >= 0 else _C.RED
    print(f"\n  {_C.BOLD}{'=' * 60}{_C.RESET}")
    print(f"  {_C.BOLD}  BACKTEST RESULTS{_C.RESET}")
    print(f"  {_C.BOLD}{'=' * 60}{_C.RESET}")
    print(f"    Period:           {start} -> {end}")
    print(f"    Total P&L:        {pnl_color}{_C.BOLD}${total_pnl:+,.2f}{_C.RESET}")
    print(f"    Total Trades:     {total_trades}")
    print(f"    Win Rate:         {win_rate * 100:.1f}%")
    print(f"    Sharpe Ratio:     {sharpe:.3f}")
    print(f"    Deflated Sharpe:  {deflated_sharpe:.3f}")
    print(f"    Profit Factor:    {profit_factor:.2f}")
    print(f"    Max Drawdown:     ${max_dd:,.2f}")

    # Walk-forward results
    wf = results.get("walk_forward", {})
    if wf:
        print(f"\n    {_C.BOLD}Walk-Forward Analysis:{_C.RESET}")
        print(f"      In-Sample Sharpe:    {wf.get('is_sharpe', 0.0):.3f}")
        print(f"      Out-of-Sample Sharpe: {wf.get('oos_sharpe', 0.0):.3f}")
        print(f"      Efficiency Ratio:    {wf.get('efficiency', 0.0):.1f}%")

    # Statistical significance
    stats = results.get("statistics", {})
    if stats:
        print(f"\n    {_C.BOLD}Statistical Significance:{_C.RESET}")
        print(f"      P-value (vs zero):   {stats.get('p_value', 1.0):.4f}")
        print(f"      95% CI:              [{stats.get('ci_lower', 0.0):+,.2f}, "
              f"{stats.get('ci_upper', 0.0):+,.2f}]")

    print(f"  {_C.BOLD}{'=' * 60}{_C.RESET}\n")

    # Save results
    results_path = Path(args.log_dir) / f"backtest_{start}_{end}.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(results_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        _print_status(f"Results saved to {results_path}", "success")
    except Exception as exc:
        _print_status(f"Failed to save results: {exc}", "warning")

    return 0


# ============================================================================
# Command: calibrate
# ============================================================================

async def _cmd_calibrate(args: argparse.Namespace) -> int:
    """Run the calibration pipeline manually."""
    from src.scanify_0dte.calibration import DailyCalibrator, TradeLogger
    from src.scanify_0dte.orchestrator import ScanifyOrchestrator

    print(f"\n  {_C.BOLD}SCANIFY Calibration{_C.RESET}")
    print()

    _print_status("Loading trade history...", "info")

    # Create a minimal orchestrator to load state
    try:
        orch = ScanifyOrchestrator(
            data_provider="mock",
            paper_trade=True,
            log_dir=args.log_dir,
        )
    except Exception as exc:
        _print_status(f"Failed to create orchestrator: {exc}", "error")
        return 1

    # Load existing calibration state
    cal_state = orch.load_state()
    if cal_state is not None:
        _print_status("Loaded existing calibration state.", "success")
    else:
        _print_status("No existing calibration state found. Starting fresh.", "warning")

    # Run calibration
    _print_status("Running daily calibration...", "info")

    try:
        calibrator = DailyCalibrator()
        result = calibrator.run_daily_calibration(
            trades=orch._closed_positions,
            pnl_summary={},
            session_setup=orch.session_setup,
            calibration_state=cal_state,
        )
        _print_status("Calibration complete.", "success")
    except Exception as exc:
        _print_status(f"Calibration failed: {exc}", "error")
        logger.exception("Calibration failed.")
        return 1

    # Print calibration results
    summary = result.get("summary", "No summary available")
    print(f"\n  {_C.BOLD}{'=' * 60}{_C.RESET}")
    print(f"  {_C.BOLD}  CALIBRATION RESULTS{_C.RESET}")
    print(f"  {_C.BOLD}{'=' * 60}{_C.RESET}")
    print(f"    Summary: {summary}")

    updated_state = result.get("updated_state")
    if updated_state is not None:
        if hasattr(updated_state, "current_weights"):
            weights = updated_state.current_weights
            print(f"\n    {_C.BOLD}Updated Factor Weights:{_C.RESET}")
            if hasattr(weights, "as_dict"):
                for k, v in weights.as_dict().items():
                    print(f"      {k:20s}: {v:.4f}")
            elif hasattr(weights, "__dict__"):
                for k, v in weights.__dict__.items():
                    if not k.startswith("_"):
                        print(f"      {k:20s}: {v:.4f}")
        if hasattr(updated_state, "entry_threshold"):
            print(f"    Entry Threshold:   {updated_state.entry_threshold:.1f}")
        if hasattr(updated_state, "stop_loss_pct"):
            print(f"    Stop Loss:         {updated_state.stop_loss_pct:.1f}%")
        if hasattr(updated_state, "regime"):
            print(f"    Detected Regime:   {updated_state.regime}")

    print(f"  {_C.BOLD}{'=' * 60}{_C.RESET}\n")

    # Save updated state
    if updated_state is not None:
        orch._calibration_state = updated_state
        orch.save_state()
        _print_status("Updated state saved to disk.", "success")

    return 0


# ============================================================================
# Command: status
# ============================================================================

async def _cmd_status(args: argparse.Namespace) -> int:
    """Show current system status."""
    from src.scanify_0dte.orchestrator import ScanifyOrchestrator

    print(f"\n  {_C.BOLD}SCANIFY System Status{_C.RESET}")
    print()

    # Load state from disk
    log_dir = Path(args.log_dir)
    state_path = log_dir / "calibration_state.json"

    if state_path.exists():
        try:
            with open(state_path, "r") as f:
                state_data = json.load(f)

            print(f"  {_C.BOLD}Saved State:{_C.RESET}")
            print(f"    Last Saved:      {state_data.get('saved_at', 'N/A')}")
            print(f"    Data Provider:   {state_data.get('data_provider', 'N/A')}")
            print(f"    Paper Trade:     {state_data.get('paper_trade', 'N/A')}")
            print(f"    Risk Budget:     ${state_data.get('risk_budget', 0):,.0f}")
            print(f"    Scan Count:      {state_data.get('scan_count', 0)}")

            cal = state_data.get("calibration", {})
            if cal:
                print(f"\n  {_C.BOLD}Calibration State:{_C.RESET}")
                for k, v in cal.items():
                    if isinstance(v, dict):
                        print(f"    {k}:")
                        for sk, sv in v.items():
                            print(f"      {sk}: {sv}")
                    else:
                        print(f"    {k}: {v}")
        except Exception as exc:
            _print_status(f"Failed to read state: {exc}", "error")
            return 1
    else:
        _print_status("No state file found. System has not been run yet.", "warning")

    # Check for recent reports
    print(f"\n  {_C.BOLD}Recent Reports:{_C.RESET}")
    report_files = sorted(log_dir.glob("report_*.json"), reverse=True)[:5]
    if report_files:
        for rf in report_files:
            try:
                with open(rf, "r") as f:
                    report = json.load(f)
                pnl = report.get("pnl_summary", {})
                total_pnl = pnl.get("total_pnl", 0.0)
                trades = pnl.get("total_trades", 0)
                win_rate = pnl.get("win_rate", 0.0)
                pnl_color = _C.GREEN if total_pnl >= 0 else _C.RED
                print(
                    f"    {rf.stem:30s}  "
                    f"P&L: {pnl_color}${total_pnl:+,.2f}{_C.RESET}  "
                    f"Trades: {trades}  "
                    f"Win: {win_rate * 100:.0f}%"
                )
            except Exception:
                print(f"    {rf.stem:30s}  (error reading)")
    else:
        print("    No reports found.")

    # Check current market time
    now = _get_et_now()
    current_time = now.time()
    market_open = time(9, 30)
    market_close = time(16, 0)
    is_open = market_open <= current_time <= market_close and now.weekday() < 5

    print(f"\n  {_C.BOLD}Market Status:{_C.RESET}")
    print(f"    Current Time (ET): {now.strftime('%Y-%m-%d %H:%M:%S')}")
    market_str = f"{_C.GREEN}OPEN{_C.RESET}" if is_open else f"{_C.RED}CLOSED{_C.RESET}"
    print(f"    Market:            {market_str}")
    if is_open:
        close_dt = now.replace(hour=16, minute=0, second=0, microsecond=0)
        mins_left = int((close_dt - now).total_seconds() / 60)
        print(f"    Minutes to Close:  {mins_left}")

    print()
    return 0


# ============================================================================
# Command: dashboard
# ============================================================================

async def _cmd_dashboard(args: argparse.Namespace) -> int:
    """Launch the terminal dashboard."""
    # Import the dashboard script
    dashboard_script = _PROJECT_ROOT / "scripts" / "scanify_dashboard.py"
    if not dashboard_script.exists():
        _print_status(
            f"Dashboard script not found at {dashboard_script}",
            "error",
        )
        return 1

    # Build the command to run the dashboard
    cmd = [
        sys.executable,
        str(dashboard_script),
        "--provider", args.provider,
        "--mode", args.mode,
        "--risk-budget", str(args.risk_budget),
        "--log-dir", args.log_dir,
    ]
    if args.api_key:
        cmd.extend(["--api-key", args.api_key])
    if args.verbose:
        cmd.append("--verbose")

    _print_status("Launching SCANIFY dashboard...", "info")

    # Execute the dashboard as a subprocess
    import subprocess
    try:
        proc = subprocess.run(cmd)
        return proc.returncode
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        _print_status(f"Dashboard launch failed: {exc}", "error")
        return 1


# ============================================================================
# Argument Parser
# ============================================================================

def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="run_scanify",
        description=(
            "SCANIFY 0DTE SPX Options Scanner + GEX Scanner\n"
            "Institutional-Grade Intraday Options Intelligence"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/run_scanify.py live --mode paper --provider mock
  python scripts/run_scanify.py live --mode paper --provider polygon --api-key YOUR_KEY
  python scripts/run_scanify.py backtest --start-date 2024-01-01 --end-date 2024-12-31
  python scripts/run_scanify.py calibrate --verbose
  python scripts/run_scanify.py status
  python scripts/run_scanify.py dashboard --provider mock

Environment Variables:
  SCANIFY_API_KEY     API key for data provider (alternative to --api-key)
  NO_COLOR            Disable colored output when set
""",
    )

    parser.add_argument(
        "--version", "-V",
        action="version",
        version=f"SCANIFY 0DTE Scanner v{__version__}",
    )

    # ---- Global options ----
    global_group = parser.add_argument_group("Global Options")
    global_group.add_argument(
        "--mode",
        choices=["paper", "live"],
        default="paper",
        help="Trading mode (default: paper)",
    )
    global_group.add_argument(
        "--provider",
        choices=["polygon", "alpaca", "mock"],
        default="mock",
        help="Data provider (default: mock)",
    )
    global_group.add_argument(
        "--api-key",
        default="",
        help="API key for data provider (or set SCANIFY_API_KEY env var)",
    )
    global_group.add_argument(
        "--risk-budget",
        type=float,
        default=10000.0,
        help="Daily risk budget in dollars (default: 10000)",
    )
    global_group.add_argument(
        "--scan-types",
        default="all",
        help="Scanner types: directional,premium,gamma or 'all' (default: all)",
    )
    global_group.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose (DEBUG-level) logging",
    )
    global_group.add_argument(
        "--log-dir",
        default="logs/scanify",
        help="Log directory (default: logs/scanify)",
    )
    global_group.add_argument(
        "--config",
        default="config.yaml",
        help="Config file path (default: config.yaml)",
    )

    # ---- Subcommands ----
    subparsers = parser.add_subparsers(
        dest="command",
        title="Commands",
        description="Available commands",
    )

    # live
    live_parser = subparsers.add_parser(
        "live",
        help="Run live scanner session (paper or real)",
        description="Run the SCANIFY scanner in real-time mode.",
    )

    # backtest
    bt_parser = subparsers.add_parser(
        "backtest",
        help="Run backtesting",
        description="Run walk-forward backtesting over historical data.",
    )
    bt_parser.add_argument(
        "--start-date",
        default=None,
        help="Backtest start date (YYYY-MM-DD). Default: 2024-01-01",
    )
    bt_parser.add_argument(
        "--end-date",
        default=None,
        help="Backtest end date (YYYY-MM-DD). Default: today",
    )

    # calibrate
    cal_parser = subparsers.add_parser(
        "calibrate",
        help="Run calibration manually",
        description="Manually trigger the self-learning calibration pipeline.",
    )

    # status
    status_parser = subparsers.add_parser(
        "status",
        help="Show system status",
        description="Display current system state, recent reports, and market status.",
    )

    # dashboard
    dash_parser = subparsers.add_parser(
        "dashboard",
        help="Launch dashboard view",
        description="Launch the terminal-based SCANIFY monitoring dashboard.",
    )

    return parser


# ============================================================================
# Main entry point
# ============================================================================

async def _async_main() -> int:
    """Async main entry point."""
    parser = _build_parser()
    args = parser.parse_args()

    # Print banner
    print(f"{_C.BLUE}{SCANIFY_BANNER}{_C.RESET}")

    # Setup logging
    _setup_logging(args.log_dir, args.verbose)

    # Dispatch command
    if args.command == "live":
        return await _cmd_live(args)
    elif args.command == "backtest":
        return await _cmd_backtest(args)
    elif args.command == "calibrate":
        return await _cmd_calibrate(args)
    elif args.command == "status":
        return await _cmd_status(args)
    elif args.command == "dashboard":
        return await _cmd_dashboard(args)
    else:
        parser.print_help()
        return 0


def main() -> None:
    """Synchronous wrapper for the async main."""
    try:
        exit_code = asyncio.run(_async_main())
    except KeyboardInterrupt:
        _print_status("Interrupted by user.", "warning")
        exit_code = 130
    except Exception as exc:
        _print_status(f"Unhandled error: {exc}", "critical")
        logger.exception("Unhandled error in main.")
        exit_code = 1

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
