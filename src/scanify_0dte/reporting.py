"""
SCANIFY SPX 0DTE Options Day Trading Scanner + GEX Scanner -- Reporting Module

Comprehensive performance reporting for the SCANIFY 0DTE SPX Scanner.
Generates daily, weekly, and monthly reports with full P&L breakdowns,
risk metrics, statistical analysis, and multi-format output (text, JSON, HTML).

Classes:

    DailyReport          End-of-day performance report with session summary,
                         P&L breakdowns by scanner/time-zone, GEX accuracy,
                         factor scores, and calibration changes.
    WeeklyReport         Weekly aggregation with win-rate trends, scanner
                         comparisons, and statistical significance testing.
    MonthlyReport        Monthly summary with Sharpe/Sortino/Calmar ratios,
                         drawdown analysis, benchmark comparisons, and
                         confidence intervals.
    TradeJournal         Persistent trade journal with search, lessons learned,
                         and markdown/JSON export.
    ReportScheduler      Schedules and dispatches reports on daily, weekly,
                         and monthly cadences to configurable channels.

All monetary values are in USD.  All timestamps are timezone-aware or UTC.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Optional, Sequence

import numpy as np
from scipy import stats as sp_stats

from .models import (
    CalibrationState,
    ExitReason,
    FactorWeights,
    ScanType,
    SessionSetup,
    SessionType,
    TimeZoneType,
    TradeDirection,
    TradeLog,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------
_ANNUALISATION_FACTOR: float = math.sqrt(252.0)
_MIN_TRADES_FOR_STATS: int = 5
_RISK_FREE_RATE: float = 0.05  # Annual risk-free rate for ratio calculations
_DAILY_RISK_FREE: float = _RISK_FREE_RATE / 252.0
_CONFIDENCE_LEVEL: float = 0.95

_FACTOR_NAMES: tuple[str, ...] = (
    "market_internals",
    "options_flow",
    "price_action",
    "gex_structure",
    "cross_asset",
)

_SCANNER_LABELS: dict[str, str] = {
    ScanType.DIRECTIONAL.value: "Directional",
    ScanType.PREMIUM_SELL.value: "Premium Selling",
    ScanType.GAMMA_SCALP.value: "Gamma Scalp",
}

_TIMEZONE_LABELS: dict[str, str] = {
    TimeZoneType.PRE_MARKET.value: "Pre-Market",
    TimeZoneType.OPENING_AUCTION.value: "Opening Auction",
    TimeZoneType.MORNING_SESSION.value: "Morning Session",
    TimeZoneType.MIDDAY_LULL.value: "Midday Lull",
    TimeZoneType.AFTERNOON_ACCEL.value: "Afternoon Acceleration",
    TimeZoneType.POWER_HOUR.value: "Power Hour",
    TimeZoneType.SETTLEMENT_WINDOW.value: "Settlement Window",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Return numerator / denominator or default when denominator is zero."""
    if denominator == 0.0:
        return default
    return numerator / denominator


def _closed_trades(trades: list[TradeLog]) -> list[TradeLog]:
    """Filter to closed trades with non-null PnL."""
    return [t for t in trades if t.pnl_dollars is not None and not t.is_open]


def _pnl_array(trades: list[TradeLog]) -> np.ndarray:
    """Extract PnL values from closed trades as a numpy array."""
    closed = _closed_trades(trades)
    if not closed:
        return np.array([], dtype=np.float64)
    return np.array([t.pnl_dollars for t in closed], dtype=np.float64)


def _win_rate(trades: list[TradeLog]) -> float:
    """Compute win rate from a list of trades."""
    closed = _closed_trades(trades)
    if not closed:
        return 0.0
    winners = sum(1 for t in closed if t.is_winner)
    return winners / len(closed) * 100.0


def _max_drawdown(pnl_series: np.ndarray) -> tuple[float, int]:
    """Compute maximum drawdown and its duration in trade count.

    Returns (max_drawdown_dollars, duration_in_trades).
    """
    if len(pnl_series) == 0:
        return 0.0, 0

    cumulative = np.cumsum(pnl_series)
    running_max = np.maximum.accumulate(cumulative)
    drawdowns = cumulative - running_max

    max_dd = float(np.min(drawdowns))
    if max_dd == 0.0:
        return 0.0, 0

    # Find duration: longest stretch below previous peak
    dd_idx = int(np.argmin(drawdowns))
    peak_idx = int(np.argmax(cumulative[:dd_idx + 1])) if dd_idx > 0 else 0
    duration = dd_idx - peak_idx

    return max_dd, duration


def _sharpe_ratio(pnl_series: np.ndarray) -> float:
    """Annualised Sharpe ratio from a PnL series."""
    if len(pnl_series) < _MIN_TRADES_FOR_STATS:
        return 0.0
    mean_ret = float(np.mean(pnl_series))
    std_ret = float(np.std(pnl_series, ddof=1))
    if std_ret == 0.0:
        return 0.0
    daily_sharpe = (mean_ret - _DAILY_RISK_FREE) / std_ret
    return daily_sharpe * _ANNUALISATION_FACTOR


def _sortino_ratio(pnl_series: np.ndarray) -> float:
    """Annualised Sortino ratio (downside deviation only)."""
    if len(pnl_series) < _MIN_TRADES_FOR_STATS:
        return 0.0
    mean_ret = float(np.mean(pnl_series))
    downside = pnl_series[pnl_series < 0]
    if len(downside) == 0:
        return float("inf") if mean_ret > 0 else 0.0
    downside_std = float(np.std(downside, ddof=1))
    if downside_std == 0.0:
        return 0.0
    return ((mean_ret - _DAILY_RISK_FREE) / downside_std) * _ANNUALISATION_FACTOR


def _calmar_ratio(pnl_series: np.ndarray) -> float:
    """Calmar ratio: annualised return / max drawdown."""
    if len(pnl_series) < _MIN_TRADES_FOR_STATS:
        return 0.0
    total_return = float(np.sum(pnl_series))
    max_dd, _ = _max_drawdown(pnl_series)
    if max_dd == 0.0:
        return float("inf") if total_return > 0 else 0.0
    annualised_return = total_return * (252.0 / len(pnl_series))
    return abs(annualised_return / max_dd)


def _profit_factor(pnl_series: np.ndarray) -> float:
    """Gross profits / gross losses."""
    gross_profit = float(np.sum(pnl_series[pnl_series > 0]))
    gross_loss = float(np.abs(np.sum(pnl_series[pnl_series < 0])))
    return _safe_div(gross_profit, gross_loss, default=float("inf") if gross_profit > 0 else 0.0)


def _format_currency(value: float) -> str:
    """Format a dollar value with sign and commas."""
    if value >= 0:
        return f"+${value:,.2f}"
    return f"-${abs(value):,.2f}"


def _format_pct(value: float, decimals: int = 1) -> str:
    """Format a percentage value."""
    return f"{value:.{decimals}f}%"


def _format_ratio(value: float, decimals: int = 2) -> str:
    """Format a ratio value."""
    if value == float("inf"):
        return "INF"
    if value == float("-inf"):
        return "-INF"
    return f"{value:.{decimals}f}"


def _html_escape(text: str) -> str:
    """Minimal HTML escaping for report content."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# =============================================================================
# 1. DAILY REPORT
# =============================================================================


class DailyReport:
    """Generates end-of-day performance report.

    Produces a comprehensive dictionary summarising the trading day,
    including session context, P&L breakdowns by scanner type and time zone,
    GEX signal accuracy, factor score analysis, risk metrics, and calibration
    changes.  The report dictionary can be rendered into text, JSON, or HTML
    via the corresponding format methods.
    """

    # ------------------------------------------------------------------ #
    # Generation
    # ------------------------------------------------------------------ #

    @staticmethod
    def generate(
        trades: list[TradeLog],
        session_setup: SessionSetup,
        calibration_state: CalibrationState,
    ) -> dict:
        """Generate a complete daily performance report.

        Parameters
        ----------
        trades:
            All trades executed during the session (open or closed).
        session_setup:
            The pre-market ``SessionSetup`` used for the session.
        calibration_state:
            Current ``CalibrationState`` after end-of-day calibration.

        Returns
        -------
        dict
            Nested report dictionary with the following top-level keys:
            ``report_date``, ``session_summary``, ``trade_summary``,
            ``pnl_by_scanner``, ``pnl_by_timezone``, ``best_trade``,
            ``worst_trade``, ``gex_accuracy``, ``factor_scores``,
            ``direction_accuracy``, ``premium_selling``, ``gamma_scalp``,
            ``risk_metrics``, ``calibration``.
        """
        closed = _closed_trades(trades)
        pnl = _pnl_array(trades)
        today = date.today()

        report: dict[str, Any] = {
            "report_type": "daily",
            "report_date": today.isoformat(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        # -- Session summary --------------------------------------------------
        gap = session_setup.gap_analysis
        em = session_setup.expected_move
        actual_range = 0.0
        if closed:
            spx_prices = [t.spx_at_entry for t in closed]
            actual_range = max(spx_prices) - min(spx_prices)

        report["session_summary"] = {
            "session_type": session_setup.session_type.value,
            "gap_classification": gap.classification.value,
            "gap_pct": round(gap.gap_pct, 3),
            "gap_points": round(gap.gap_points, 2),
            "gap_sigma": round(gap.gap_sigma, 2),
            "expected_move_1sigma": round(em.final_1sigma, 2),
            "expected_move_2sigma": round(em.final_2sigma, 2),
            "actual_range": round(actual_range, 2),
            "range_vs_expected": round(
                _safe_div(actual_range, em.final_1sigma) * 100.0, 1
            ),
            "vol_regime": em.vol_regime,
            "iv_rv_ratio": round(em.iv_rv_ratio, 2),
            "high_impact_events": session_setup.high_impact_event_count,
            "risk_assessment": session_setup.risk_assessment,
        }

        # -- Trade summary ----------------------------------------------------
        winners = [t for t in closed if t.is_winner]
        losers = [t for t in closed if not t.is_winner]
        total_pnl = float(np.sum(pnl)) if len(pnl) > 0 else 0.0
        avg_winner = float(np.mean([t.pnl_dollars for t in winners])) if winners else 0.0
        avg_loser = float(np.mean([t.pnl_dollars for t in losers])) if losers else 0.0
        avg_hold = (
            float(np.mean([t.hold_time_minutes for t in closed if t.hold_time_minutes is not None]))
            if any(t.hold_time_minutes is not None for t in closed)
            else 0.0
        )

        report["trade_summary"] = {
            "total_trades": len(closed),
            "winners": len(winners),
            "losers": len(losers),
            "open_positions": sum(1 for t in trades if t.is_open),
            "win_rate": round(_win_rate(trades), 1),
            "total_pnl": round(total_pnl, 2),
            "avg_winner": round(avg_winner, 2),
            "avg_loser": round(avg_loser, 2),
            "avg_hold_minutes": round(avg_hold, 1),
            "profit_factor": round(_profit_factor(pnl), 2) if len(pnl) > 0 else 0.0,
            "expectancy": round(
                _safe_div(total_pnl, len(closed)), 2
            ) if closed else 0.0,
            "largest_win": round(max((t.pnl_dollars for t in winners), default=0.0), 2),
            "largest_loss": round(min((t.pnl_dollars for t in losers), default=0.0), 2),
        }

        # -- P&L by scanner type ----------------------------------------------
        pnl_by_scanner: dict[str, dict] = {}
        for scan_type in ScanType:
            st_trades = [t for t in closed if t.scan_type == scan_type]
            st_pnl = _pnl_array(st_trades) if st_trades else np.array([])
            pnl_by_scanner[scan_type.value] = {
                "trade_count": len(st_trades),
                "total_pnl": round(float(np.sum(st_pnl)), 2) if len(st_pnl) > 0 else 0.0,
                "win_rate": round(_win_rate(st_trades), 1),
                "avg_pnl": round(float(np.mean(st_pnl)), 2) if len(st_pnl) > 0 else 0.0,
            }
        report["pnl_by_scanner"] = pnl_by_scanner

        # -- P&L by time zone -------------------------------------------------
        pnl_by_tz: dict[str, dict] = {}
        for tz_type in TimeZoneType:
            tz_trades = [t for t in closed if t.time_zone == tz_type]
            tz_pnl = _pnl_array(tz_trades) if tz_trades else np.array([])
            pnl_by_tz[tz_type.value] = {
                "trade_count": len(tz_trades),
                "total_pnl": round(float(np.sum(tz_pnl)), 2) if len(tz_pnl) > 0 else 0.0,
                "win_rate": round(_win_rate(tz_trades), 1),
                "avg_pnl": round(float(np.mean(tz_pnl)), 2) if len(tz_pnl) > 0 else 0.0,
            }
        report["pnl_by_timezone"] = pnl_by_tz

        # -- Best / worst trade -----------------------------------------------
        report["best_trade"] = DailyReport._trade_summary(
            max(closed, key=lambda t: t.pnl_dollars or 0.0) if closed else None
        )
        report["worst_trade"] = DailyReport._trade_summary(
            min(closed, key=lambda t: t.pnl_dollars or 0.0) if closed else None
        )

        # -- GEX signal accuracy ----------------------------------------------
        report["gex_accuracy"] = {
            "rolling_accuracy": round(calibration_state.gex_signal_accuracy * 100.0, 1),
            "regime": calibration_state.regime,
        }

        # -- Factor scores analysis -------------------------------------------
        factor_totals: dict[str, list[float]] = {f: [] for f in _FACTOR_NAMES}
        for t in closed:
            factor_totals["market_internals"].append(t.tick_10min_avg)
            factor_totals["cross_asset"].append(t.vix_at_entry)
            factor_totals["gex_structure"].append(t.net_gex_at_entry)
            factor_totals["price_action"].append(t.spx_at_entry)
            factor_totals["options_flow"].append(t.iv_at_entry)

        weights = calibration_state.current_weights
        report["factor_scores"] = {
            "current_weights": weights.as_dict(),
            "factor_means": {
                f: round(float(np.mean(vals)), 4) if vals else 0.0
                for f, vals in factor_totals.items()
            },
        }

        # -- Direction score accuracy -----------------------------------------
        direction_correct = 0
        direction_total = 0
        for t in closed:
            direction_total += 1
            score = t.composite_direction_score
            if (score > 0 and t.is_winner and t.direction == TradeDirection.BULL) or \
               (score < 0 and t.is_winner and t.direction == TradeDirection.BEAR):
                direction_correct += 1
        report["direction_accuracy"] = {
            "correct": direction_correct,
            "total": direction_total,
            "accuracy_pct": round(
                _safe_div(direction_correct, direction_total) * 100.0, 1
            ),
            "avg_score_winners": round(
                float(np.mean([t.composite_direction_score for t in winners])), 1
            ) if winners else 0.0,
            "avg_score_losers": round(
                float(np.mean([t.composite_direction_score for t in losers])), 1
            ) if losers else 0.0,
        }

        # -- Premium selling results ------------------------------------------
        prem_trades = [t for t in closed if t.scan_type == ScanType.PREMIUM_SELL]
        prem_pnl = _pnl_array(prem_trades)
        report["premium_selling"] = {
            "trade_count": len(prem_trades),
            "total_pnl": round(float(np.sum(prem_pnl)), 2) if len(prem_pnl) > 0 else 0.0,
            "win_rate": round(_win_rate(prem_trades), 1),
            "avg_credit_captured_pct": round(
                float(np.mean([
                    _safe_div(t.pnl_dollars or 0.0, t.entry_price * 100.0) * 100.0
                    for t in prem_trades
                ])), 1
            ) if prem_trades else 0.0,
        }

        # -- Gamma scalp results ----------------------------------------------
        gs_trades = [t for t in closed if t.scan_type == ScanType.GAMMA_SCALP]
        gs_pnl = _pnl_array(gs_trades)
        report["gamma_scalp"] = {
            "trade_count": len(gs_trades),
            "total_pnl": round(float(np.sum(gs_pnl)), 2) if len(gs_pnl) > 0 else 0.0,
            "win_rate": round(_win_rate(gs_trades), 1),
            "avg_gamma_at_entry": round(
                float(np.mean([t.gamma_at_entry for t in gs_trades])), 6
            ) if gs_trades else 0.0,
        }

        # -- Risk metrics -----------------------------------------------------
        max_dd, dd_duration = _max_drawdown(pnl)
        max_exposure = (
            max(abs(t.entry_price * 100.0) for t in closed) if closed else 0.0
        )
        report["risk_metrics"] = {
            "max_drawdown": round(max_dd, 2),
            "drawdown_duration_trades": dd_duration,
            "max_single_loss": round(
                min((t.pnl_dollars for t in closed if t.pnl_dollars is not None), default=0.0), 2
            ),
            "max_exposure": round(max_exposure, 2),
            "sharpe_ratio": round(_sharpe_ratio(pnl), 2),
            "sortino_ratio": round(_sortino_ratio(pnl), 2),
            "profit_factor": round(_profit_factor(pnl), 2) if len(pnl) > 0 else 0.0,
        }

        # -- Calibration changes ----------------------------------------------
        report["calibration"] = {
            "regime": calibration_state.regime,
            "entry_threshold": calibration_state.entry_threshold,
            "stop_loss_pct": calibration_state.stop_loss_pct,
            "trade_count_since_calibration": calibration_state.trade_count,
            "last_calibration": calibration_state.last_calibration.isoformat(),
            "current_weights": weights.as_dict(),
            "profit_targets_by_zone": calibration_state.profit_targets_by_zone,
            "gex_signal_accuracy": round(
                calibration_state.gex_signal_accuracy * 100.0, 1
            ),
        }

        return report

    # ------------------------------------------------------------------ #
    # Formatting
    # ------------------------------------------------------------------ #

    @staticmethod
    def format_text(report: dict) -> str:
        """Render the daily report as a human-readable text string.

        Parameters
        ----------
        report:
            Dictionary produced by ``DailyReport.generate``.

        Returns
        -------
        str
            Multi-line plain-text report suitable for terminal or log output.
        """
        lines: list[str] = []
        sep = "=" * 72
        thin_sep = "-" * 72

        lines.append(sep)
        lines.append(f"  SCANIFY 0DTE SPX SCANNER -- DAILY REPORT")
        lines.append(f"  Date: {report['report_date']}")
        lines.append(sep)

        # Session summary
        ss = report["session_summary"]
        lines.append("")
        lines.append("SESSION SUMMARY")
        lines.append(thin_sep)
        lines.append(f"  Session Type:      {ss['session_type']}")
        lines.append(f"  Gap:               {ss['gap_classification']} "
                      f"({ss['gap_points']:+.2f} pts, {ss['gap_pct']:+.3f}%, "
                      f"{ss['gap_sigma']:+.2f} sigma)")
        lines.append(f"  Expected Move:     {ss['expected_move_1sigma']:.2f} pts (1-sigma), "
                      f"{ss['expected_move_2sigma']:.2f} pts (2-sigma)")
        lines.append(f"  Actual Range:      {ss['actual_range']:.2f} pts "
                      f"({ss['range_vs_expected']:.1f}% of expected)")
        lines.append(f"  Vol Regime:        {ss['vol_regime']} (IV/RV: {ss['iv_rv_ratio']:.2f})")
        lines.append(f"  High-Impact Events: {ss['high_impact_events']}")

        # Trade summary
        ts = report["trade_summary"]
        lines.append("")
        lines.append("TRADE SUMMARY")
        lines.append(thin_sep)
        lines.append(f"  Total Trades:      {ts['total_trades']}")
        lines.append(f"  Winners / Losers:  {ts['winners']} / {ts['losers']}")
        lines.append(f"  Open Positions:    {ts['open_positions']}")
        lines.append(f"  Win Rate:          {_format_pct(ts['win_rate'])}")
        lines.append(f"  Total P&L:         {_format_currency(ts['total_pnl'])}")
        lines.append(f"  Avg Winner:        {_format_currency(ts['avg_winner'])}")
        lines.append(f"  Avg Loser:         {_format_currency(ts['avg_loser'])}")
        lines.append(f"  Largest Win:       {_format_currency(ts['largest_win'])}")
        lines.append(f"  Largest Loss:      {_format_currency(ts['largest_loss'])}")
        lines.append(f"  Profit Factor:     {_format_ratio(ts['profit_factor'])}")
        lines.append(f"  Expectancy:        {_format_currency(ts['expectancy'])}")
        lines.append(f"  Avg Hold Time:     {ts['avg_hold_minutes']:.1f} min")

        # P&L by scanner
        lines.append("")
        lines.append("P&L BY SCANNER TYPE")
        lines.append(thin_sep)
        lines.append(f"  {'Scanner':<20} {'Trades':>7} {'P&L':>12} {'Win Rate':>10} {'Avg P&L':>12}")
        lines.append(f"  {'-' * 20} {'-' * 7} {'-' * 12} {'-' * 10} {'-' * 12}")
        for scan_key, scan_data in report["pnl_by_scanner"].items():
            label = _SCANNER_LABELS.get(scan_key, scan_key)
            lines.append(
                f"  {label:<20} {scan_data['trade_count']:>7} "
                f"{_format_currency(scan_data['total_pnl']):>12} "
                f"{_format_pct(scan_data['win_rate']):>10} "
                f"{_format_currency(scan_data['avg_pnl']):>12}"
            )

        # P&L by time zone
        lines.append("")
        lines.append("P&L BY TIME ZONE")
        lines.append(thin_sep)
        lines.append(f"  {'Time Zone':<25} {'Trades':>7} {'P&L':>12} {'Win Rate':>10}")
        lines.append(f"  {'-' * 25} {'-' * 7} {'-' * 12} {'-' * 10}")
        for tz_key, tz_data in report["pnl_by_timezone"].items():
            if tz_data["trade_count"] > 0:
                label = _TIMEZONE_LABELS.get(tz_key, tz_key)
                lines.append(
                    f"  {label:<25} {tz_data['trade_count']:>7} "
                    f"{_format_currency(tz_data['total_pnl']):>12} "
                    f"{_format_pct(tz_data['win_rate']):>10}"
                )

        # Best / Worst trade
        lines.append("")
        lines.append("NOTABLE TRADES")
        lines.append(thin_sep)
        best = report["best_trade"]
        worst = report["worst_trade"]
        if best:
            lines.append(f"  Best Trade:   {best['scan_type']} {best['direction']} "
                          f"| {_format_currency(best['pnl'])} "
                          f"| Hold: {best['hold_minutes']:.0f}m "
                          f"| Exit: {best['exit_reason']}")
        if worst:
            lines.append(f"  Worst Trade:  {worst['scan_type']} {worst['direction']} "
                          f"| {_format_currency(worst['pnl'])} "
                          f"| Hold: {worst['hold_minutes']:.0f}m "
                          f"| Exit: {worst['exit_reason']}")

        # GEX accuracy
        gex = report["gex_accuracy"]
        lines.append("")
        lines.append("GEX SIGNAL ACCURACY")
        lines.append(thin_sep)
        lines.append(f"  Rolling Accuracy:  {_format_pct(gex['rolling_accuracy'])}")
        lines.append(f"  Current Regime:    {gex['regime']}")

        # Direction accuracy
        da = report["direction_accuracy"]
        lines.append("")
        lines.append("DIRECTION SCORE ACCURACY")
        lines.append(thin_sep)
        lines.append(f"  Correct / Total:   {da['correct']} / {da['total']} "
                      f"({_format_pct(da['accuracy_pct'])})")
        lines.append(f"  Avg Score Winners: {da['avg_score_winners']:.1f}")
        lines.append(f"  Avg Score Losers:  {da['avg_score_losers']:.1f}")

        # Premium selling
        ps = report["premium_selling"]
        lines.append("")
        lines.append("PREMIUM SELLING RESULTS")
        lines.append(thin_sep)
        lines.append(f"  Trades:            {ps['trade_count']}")
        lines.append(f"  Total P&L:         {_format_currency(ps['total_pnl'])}")
        lines.append(f"  Win Rate:          {_format_pct(ps['win_rate'])}")

        # Gamma scalp
        gs = report["gamma_scalp"]
        lines.append("")
        lines.append("GAMMA SCALP RESULTS")
        lines.append(thin_sep)
        lines.append(f"  Trades:            {gs['trade_count']}")
        lines.append(f"  Total P&L:         {_format_currency(gs['total_pnl'])}")
        lines.append(f"  Win Rate:          {_format_pct(gs['win_rate'])}")

        # Risk metrics
        rm = report["risk_metrics"]
        lines.append("")
        lines.append("RISK METRICS")
        lines.append(thin_sep)
        lines.append(f"  Max Drawdown:      {_format_currency(rm['max_drawdown'])}")
        lines.append(f"  DD Duration:       {rm['drawdown_duration_trades']} trades")
        lines.append(f"  Max Single Loss:   {_format_currency(rm['max_single_loss'])}")
        lines.append(f"  Max Exposure:      {_format_currency(rm['max_exposure'])}")
        lines.append(f"  Sharpe Ratio:      {_format_ratio(rm['sharpe_ratio'])}")
        lines.append(f"  Sortino Ratio:     {_format_ratio(rm['sortino_ratio'])}")

        # Calibration
        cal = report["calibration"]
        lines.append("")
        lines.append("CALIBRATION STATE")
        lines.append(thin_sep)
        lines.append(f"  Regime:            {cal['regime']}")
        lines.append(f"  Entry Threshold:   {cal['entry_threshold']:.1f}")
        lines.append(f"  Stop Loss:         {_format_pct(cal['stop_loss_pct'])}")
        lines.append(f"  GEX Accuracy:      {_format_pct(cal['gex_signal_accuracy'])}")
        lines.append(f"  Last Calibration:  {cal['last_calibration']}")
        w = cal["current_weights"]
        lines.append(f"  Weights: MI={w['market_internals']:.3f}  "
                      f"OF={w['options_flow']:.3f}  "
                      f"PA={w['price_action']:.3f}  "
                      f"GX={w['gex_structure']:.3f}  "
                      f"CA={w['cross_asset']:.3f}")

        lines.append("")
        lines.append(sep)
        lines.append(f"  Generated: {report['generated_at']}")
        lines.append(sep)

        return "\n".join(lines)

    @staticmethod
    def format_json(report: dict) -> str:
        """Render the daily report as a formatted JSON string.

        Parameters
        ----------
        report:
            Dictionary produced by ``DailyReport.generate``.

        Returns
        -------
        str
            Pretty-printed JSON string.
        """
        return json.dumps(report, indent=2, default=str)

    @staticmethod
    def format_html(report: dict) -> str:
        """Render the daily report as an HTML email body.

        Parameters
        ----------
        report:
            Dictionary produced by ``DailyReport.generate``.

        Returns
        -------
        str
            Complete HTML document string suitable for email delivery.
        """
        ts = report["trade_summary"]
        ss = report["session_summary"]
        rm = report["risk_metrics"]
        total_pnl = ts["total_pnl"]
        pnl_color = "#2ecc71" if total_pnl >= 0 else "#e74c3c"

        html_parts: list[str] = []

        html_parts.append("<!DOCTYPE html>")
        html_parts.append('<html lang="en"><head><meta charset="UTF-8">')
        html_parts.append("<style>")
        html_parts.append("""
            body { font-family: 'Segoe UI', Tahoma, Geneva, sans-serif;
                   background: #1a1a2e; color: #e0e0e0; margin: 0; padding: 20px; }
            .container { max-width: 700px; margin: 0 auto;
                         background: #16213e; border-radius: 8px; padding: 24px; }
            h1 { color: #00d2ff; font-size: 22px; margin-bottom: 4px; }
            h2 { color: #a8d8ea; font-size: 16px; margin-top: 24px;
                 border-bottom: 1px solid #2a3a5c; padding-bottom: 6px; }
            .pnl-hero { font-size: 36px; font-weight: bold; margin: 16px 0; }
            .stat-grid { display: grid; grid-template-columns: 1fr 1fr;
                         gap: 8px 24px; margin: 12px 0; }
            .stat-label { color: #8899aa; font-size: 13px; }
            .stat-value { font-size: 15px; font-weight: 600; }
            table { width: 100%; border-collapse: collapse; margin: 12px 0; }
            th { text-align: left; color: #8899aa; font-size: 12px;
                 text-transform: uppercase; padding: 6px 8px;
                 border-bottom: 1px solid #2a3a5c; }
            td { padding: 6px 8px; font-size: 14px;
                 border-bottom: 1px solid #1a2a4c; }
            .positive { color: #2ecc71; }
            .negative { color: #e74c3c; }
            .neutral { color: #f39c12; }
            .footer { margin-top: 24px; text-align: center;
                      color: #556677; font-size: 11px; }
        """)
        html_parts.append("</style></head><body>")
        html_parts.append('<div class="container">')

        # Header
        html_parts.append(f"<h1>SCANIFY 0DTE Daily Report</h1>")
        html_parts.append(f"<p style='color:#8899aa;margin:0;'>{report['report_date']} | "
                          f"{ss['session_type']} Session | Vol: {ss['vol_regime']}</p>")

        # P&L Hero
        html_parts.append(f'<div class="pnl-hero" style="color:{pnl_color};">'
                          f'{_format_currency(total_pnl)}</div>')

        # Key stats grid
        html_parts.append('<div class="stat-grid">')
        stats = [
            ("Trades", f"{ts['total_trades']}"),
            ("Win Rate", _format_pct(ts["win_rate"])),
            ("Winners / Losers", f"{ts['winners']} / {ts['losers']}"),
            ("Profit Factor", _format_ratio(ts["profit_factor"])),
            ("Avg Winner", _format_currency(ts["avg_winner"])),
            ("Avg Loser", _format_currency(ts["avg_loser"])),
            ("Sharpe", _format_ratio(rm["sharpe_ratio"])),
            ("Max Drawdown", _format_currency(rm["max_drawdown"])),
        ]
        for label, value in stats:
            html_parts.append(f'<div><span class="stat-label">{label}</span><br>'
                              f'<span class="stat-value">{_html_escape(value)}</span></div>')
        html_parts.append("</div>")

        # Scanner breakdown table
        html_parts.append("<h2>P&amp;L by Scanner</h2>")
        html_parts.append("<table><tr><th>Scanner</th><th>Trades</th>"
                          "<th>P&amp;L</th><th>Win Rate</th></tr>")
        for scan_key, scan_data in report["pnl_by_scanner"].items():
            label = _SCANNER_LABELS.get(scan_key, scan_key)
            pnl_val = scan_data["total_pnl"]
            css_class = "positive" if pnl_val >= 0 else "negative"
            html_parts.append(
                f"<tr><td>{_html_escape(label)}</td>"
                f"<td>{scan_data['trade_count']}</td>"
                f'<td class="{css_class}">{_format_currency(pnl_val)}</td>'
                f"<td>{_format_pct(scan_data['win_rate'])}</td></tr>"
            )
        html_parts.append("</table>")

        # Time zone breakdown table
        html_parts.append("<h2>P&amp;L by Time Zone</h2>")
        html_parts.append("<table><tr><th>Time Zone</th><th>Trades</th>"
                          "<th>P&amp;L</th><th>Win Rate</th></tr>")
        for tz_key, tz_data in report["pnl_by_timezone"].items():
            if tz_data["trade_count"] > 0:
                label = _TIMEZONE_LABELS.get(tz_key, tz_key)
                pnl_val = tz_data["total_pnl"]
                css_class = "positive" if pnl_val >= 0 else "negative"
                html_parts.append(
                    f"<tr><td>{_html_escape(label)}</td>"
                    f"<td>{tz_data['trade_count']}</td>"
                    f'<td class="{css_class}">{_format_currency(pnl_val)}</td>'
                    f"<td>{_format_pct(tz_data['win_rate'])}</td></tr>"
                )
        html_parts.append("</table>")

        # GEX + Direction
        gex = report["gex_accuracy"]
        da = report["direction_accuracy"]
        html_parts.append("<h2>Signal Accuracy</h2>")
        html_parts.append('<div class="stat-grid">')
        html_parts.append(f'<div><span class="stat-label">GEX Rolling Accuracy</span><br>'
                          f'<span class="stat-value">{_format_pct(gex["rolling_accuracy"])}</span></div>')
        html_parts.append(f'<div><span class="stat-label">Direction Accuracy</span><br>'
                          f'<span class="stat-value">{_format_pct(da["accuracy_pct"])}</span></div>')
        html_parts.append("</div>")

        # Calibration
        cal = report["calibration"]
        html_parts.append("<h2>Calibration</h2>")
        html_parts.append('<div class="stat-grid">')
        html_parts.append(f'<div><span class="stat-label">Regime</span><br>'
                          f'<span class="stat-value">{_html_escape(cal["regime"])}</span></div>')
        html_parts.append(f'<div><span class="stat-label">Entry Threshold</span><br>'
                          f'<span class="stat-value">{cal["entry_threshold"]:.1f}</span></div>')
        html_parts.append("</div>")

        # Footer
        html_parts.append(f'<div class="footer">Generated {report["generated_at"]}</div>')
        html_parts.append("</div></body></html>")

        return "\n".join(html_parts)

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _trade_summary(trade: Optional[TradeLog]) -> Optional[dict]:
        """Extract a compact summary dict from a single trade."""
        if trade is None:
            return None
        return {
            "trade_id": trade.trade_id,
            "scan_type": trade.scan_type.value,
            "direction": trade.direction.value,
            "pnl": round(trade.pnl_dollars or 0.0, 2),
            "pnl_pct": round(trade.pnl_percent or 0.0, 2),
            "hold_minutes": round(trade.hold_time_minutes or 0.0, 1),
            "exit_reason": trade.exit_reason.value if trade.exit_reason else "OPEN",
            "strike": trade.strike,
            "entry_price": trade.entry_price,
            "exit_price": trade.exit_price or 0.0,
            "time_zone": trade.time_zone.value,
        }


# =============================================================================
# 2. WEEKLY REPORT
# =============================================================================


class WeeklyReport:
    """Generates weekly performance summary.

    Aggregates multiple daily reports and the full week's trades to produce
    a weekly overview including daily P&L breakdown, win-rate trends,
    scanner comparisons, factor weight evolution, regime analysis, and
    statistical significance of the trading edge.
    """

    @staticmethod
    def generate(
        daily_reports: list[dict],
        trades: list[TradeLog],
    ) -> dict:
        """Generate a comprehensive weekly performance report.

        Parameters
        ----------
        daily_reports:
            List of daily report dicts (from ``DailyReport.generate``),
            one per trading day in the week.
        trades:
            All trades executed during the week.

        Returns
        -------
        dict
            Weekly report dictionary with keys: ``week_pnl``,
            ``daily_breakdown``, ``win_rate_trend``, ``best_day``,
            ``worst_day``, ``scanner_comparison``, ``factor_weight_changes``,
            ``regime_analysis``, ``statistical_significance``.
        """
        closed = _closed_trades(trades)
        pnl = _pnl_array(trades)
        total_pnl = float(np.sum(pnl)) if len(pnl) > 0 else 0.0

        # Determine date range
        dates = [r["report_date"] for r in daily_reports]
        week_start = min(dates) if dates else date.today().isoformat()
        week_end = max(dates) if dates else date.today().isoformat()

        report: dict[str, Any] = {
            "report_type": "weekly",
            "week_start": week_start,
            "week_end": week_end,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        # -- Week P&L total ---------------------------------------------------
        report["week_pnl"] = {
            "total_pnl": round(total_pnl, 2),
            "total_trades": len(closed),
            "win_rate": round(_win_rate(trades), 1),
            "profit_factor": round(_profit_factor(pnl), 2) if len(pnl) > 0 else 0.0,
            "sharpe_ratio": round(_sharpe_ratio(pnl), 2),
            "sortino_ratio": round(_sortino_ratio(pnl), 2),
            "max_drawdown": round(_max_drawdown(pnl)[0], 2),
        }

        # -- Daily breakdown --------------------------------------------------
        daily_breakdown: list[dict] = []
        for dr in daily_reports:
            ts = dr.get("trade_summary", {})
            daily_breakdown.append({
                "date": dr["report_date"],
                "pnl": ts.get("total_pnl", 0.0),
                "trades": ts.get("total_trades", 0),
                "win_rate": ts.get("win_rate", 0.0),
                "profit_factor": ts.get("profit_factor", 0.0),
            })
        report["daily_breakdown"] = daily_breakdown

        # -- Win rate trend ---------------------------------------------------
        win_rates = [d["win_rate"] for d in daily_breakdown]
        report["win_rate_trend"] = {
            "daily_win_rates": win_rates,
            "trend_direction": "improving" if len(win_rates) >= 2 and win_rates[-1] > win_rates[0]
                               else "declining" if len(win_rates) >= 2 and win_rates[-1] < win_rates[0]
                               else "stable",
            "week_avg": round(float(np.mean(win_rates)), 1) if win_rates else 0.0,
            "week_std": round(float(np.std(win_rates)), 1) if win_rates else 0.0,
        }

        # -- Best / worst day -------------------------------------------------
        if daily_breakdown:
            best_day = max(daily_breakdown, key=lambda d: d["pnl"])
            worst_day = min(daily_breakdown, key=lambda d: d["pnl"])
            report["best_day"] = best_day
            report["worst_day"] = worst_day
        else:
            report["best_day"] = None
            report["worst_day"] = None

        # -- Scanner performance comparison -----------------------------------
        scanner_comp: dict[str, dict] = {}
        for scan_type in ScanType:
            st_trades = [t for t in closed if t.scan_type == scan_type]
            st_pnl = _pnl_array(st_trades)
            scanner_comp[scan_type.value] = {
                "trade_count": len(st_trades),
                "total_pnl": round(float(np.sum(st_pnl)), 2) if len(st_pnl) > 0 else 0.0,
                "win_rate": round(_win_rate(st_trades), 1),
                "avg_pnl": round(float(np.mean(st_pnl)), 2) if len(st_pnl) > 0 else 0.0,
                "sharpe": round(_sharpe_ratio(st_pnl), 2),
                "profit_factor": round(_profit_factor(st_pnl), 2) if len(st_pnl) > 0 else 0.0,
                "max_drawdown": round(_max_drawdown(st_pnl)[0], 2),
            }
        report["scanner_comparison"] = scanner_comp

        # -- Factor weight changes --------------------------------------------
        weight_history: list[dict[str, float]] = []
        for dr in daily_reports:
            cal = dr.get("calibration", {})
            w = cal.get("current_weights")
            if w:
                weight_history.append(w)

        if len(weight_history) >= 2:
            first = weight_history[0]
            last = weight_history[-1]
            weight_changes = {
                factor: round(last.get(factor, 0.0) - first.get(factor, 0.0), 4)
                for factor in _FACTOR_NAMES
            }
        else:
            weight_changes = {f: 0.0 for f in _FACTOR_NAMES}

        report["factor_weight_changes"] = {
            "start_weights": weight_history[0] if weight_history else {},
            "end_weights": weight_history[-1] if weight_history else {},
            "changes": weight_changes,
        }

        # -- Regime analysis --------------------------------------------------
        regime_counts: dict[str, int] = defaultdict(int)
        for dr in daily_reports:
            ss = dr.get("session_summary", {})
            session_type = ss.get("session_type", "UNKNOWN")
            regime_counts[session_type] += 1

        regime_pnl: dict[str, float] = defaultdict(float)
        for t in closed:
            regime_pnl[t.session_type.value] += (t.pnl_dollars or 0.0)

        report["regime_analysis"] = {
            "session_type_distribution": dict(regime_counts),
            "pnl_by_session_type": {
                k: round(v, 2) for k, v in regime_pnl.items()
            },
        }

        # -- Statistical significance ----------------------------------------
        report["statistical_significance"] = WeeklyReport._compute_significance(pnl)

        return report

    @staticmethod
    def format_text(report: dict) -> str:
        """Render the weekly report as human-readable text."""
        lines: list[str] = []
        sep = "=" * 72
        thin_sep = "-" * 72

        lines.append(sep)
        lines.append("  SCANIFY 0DTE SPX SCANNER -- WEEKLY REPORT")
        lines.append(f"  Week: {report['week_start']} to {report['week_end']}")
        lines.append(sep)

        wp = report["week_pnl"]
        lines.append("")
        lines.append("WEEK SUMMARY")
        lines.append(thin_sep)
        lines.append(f"  Total P&L:         {_format_currency(wp['total_pnl'])}")
        lines.append(f"  Total Trades:      {wp['total_trades']}")
        lines.append(f"  Win Rate:          {_format_pct(wp['win_rate'])}")
        lines.append(f"  Profit Factor:     {_format_ratio(wp['profit_factor'])}")
        lines.append(f"  Sharpe Ratio:      {_format_ratio(wp['sharpe_ratio'])}")
        lines.append(f"  Sortino Ratio:     {_format_ratio(wp['sortino_ratio'])}")
        lines.append(f"  Max Drawdown:      {_format_currency(wp['max_drawdown'])}")

        # Daily breakdown
        lines.append("")
        lines.append("DAILY BREAKDOWN")
        lines.append(thin_sep)
        lines.append(f"  {'Date':<12} {'P&L':>12} {'Trades':>7} {'Win Rate':>10}")
        lines.append(f"  {'-' * 12} {'-' * 12} {'-' * 7} {'-' * 10}")
        for d in report.get("daily_breakdown", []):
            lines.append(f"  {d['date']:<12} {_format_currency(d['pnl']):>12} "
                          f"{d['trades']:>7} {_format_pct(d['win_rate']):>10}")

        # Best / worst day
        best = report.get("best_day")
        worst = report.get("worst_day")
        if best:
            lines.append(f"\n  Best Day:  {best['date']} ({_format_currency(best['pnl'])})")
        if worst:
            lines.append(f"  Worst Day: {worst['date']} ({_format_currency(worst['pnl'])})")

        # Scanner comparison
        lines.append("")
        lines.append("SCANNER COMPARISON")
        lines.append(thin_sep)
        lines.append(f"  {'Scanner':<20} {'Trades':>7} {'P&L':>12} "
                      f"{'Win Rate':>10} {'Sharpe':>8}")
        lines.append(f"  {'-' * 20} {'-' * 7} {'-' * 12} {'-' * 10} {'-' * 8}")
        for scan_key, data in report.get("scanner_comparison", {}).items():
            label = _SCANNER_LABELS.get(scan_key, scan_key)
            lines.append(
                f"  {label:<20} {data['trade_count']:>7} "
                f"{_format_currency(data['total_pnl']):>12} "
                f"{_format_pct(data['win_rate']):>10} "
                f"{_format_ratio(data['sharpe']):>8}"
            )

        # Win rate trend
        wrt = report.get("win_rate_trend", {})
        lines.append("")
        lines.append(f"  Win Rate Trend:    {wrt.get('trend_direction', 'N/A')} "
                      f"(avg {_format_pct(wrt.get('week_avg', 0.0))})")

        # Statistical significance
        sig = report.get("statistical_significance", {})
        lines.append("")
        lines.append("STATISTICAL SIGNIFICANCE")
        lines.append(thin_sep)
        lines.append(f"  t-statistic:       {_format_ratio(sig.get('t_statistic', 0.0))}")
        lines.append(f"  p-value:           {sig.get('p_value', 1.0):.4f}")
        lines.append(f"  Significant:       {'YES' if sig.get('is_significant', False) else 'NO'}")

        lines.append("")
        lines.append(sep)
        lines.append(f"  Generated: {report['generated_at']}")
        lines.append(sep)

        return "\n".join(lines)

    @staticmethod
    def _compute_significance(pnl: np.ndarray) -> dict:
        """Run a one-sample t-test on PnL to assess edge significance."""
        if len(pnl) < _MIN_TRADES_FOR_STATS:
            return {
                "t_statistic": 0.0,
                "p_value": 1.0,
                "is_significant": False,
                "sample_size": int(len(pnl)),
                "confidence_interval": [0.0, 0.0],
                "note": f"Insufficient sample size (need >= {_MIN_TRADES_FOR_STATS})",
            }

        t_stat, p_value = sp_stats.ttest_1samp(pnl, 0.0)
        mean_pnl = float(np.mean(pnl))
        se = float(sp_stats.sem(pnl))
        ci_low = mean_pnl - sp_stats.t.ppf((1 + _CONFIDENCE_LEVEL) / 2, len(pnl) - 1) * se
        ci_high = mean_pnl + sp_stats.t.ppf((1 + _CONFIDENCE_LEVEL) / 2, len(pnl) - 1) * se

        return {
            "t_statistic": round(float(t_stat), 4),
            "p_value": round(float(p_value), 6),
            "is_significant": float(p_value) < (1.0 - _CONFIDENCE_LEVEL),
            "sample_size": int(len(pnl)),
            "mean_pnl": round(mean_pnl, 2),
            "std_pnl": round(float(np.std(pnl, ddof=1)), 2),
            "confidence_interval": [round(ci_low, 2), round(ci_high, 2)],
        }


# =============================================================================
# 3. MONTHLY REPORT
# =============================================================================


class MonthlyReport:
    """Generates monthly performance summary with benchmarks.

    Produces a comprehensive month-end report including risk-adjusted return
    ratios (Sharpe, Sortino, Calmar), detailed drawdown analysis, benchmark
    comparisons, scanner alpha attribution, regime performance breakdown,
    calibration evolution, and full statistical significance testing with
    confidence intervals.
    """

    @staticmethod
    def generate(
        weekly_reports: list[dict],
        trades: list[TradeLog],
    ) -> dict:
        """Generate a comprehensive monthly performance report.

        Parameters
        ----------
        weekly_reports:
            List of weekly report dicts (from ``WeeklyReport.generate``),
            typically 4-5 per month.
        trades:
            All trades executed during the month.

        Returns
        -------
        dict
            Monthly report dictionary with keys: ``total_pnl_and_returns``,
            ``risk_ratios``, ``drawdown_analysis``, ``benchmark_comparison``,
            ``scanner_alpha``, ``regime_breakdown``, ``calibration_evolution``,
            ``statistical_significance``.
        """
        closed = _closed_trades(trades)
        pnl = _pnl_array(trades)
        total_pnl = float(np.sum(pnl)) if len(pnl) > 0 else 0.0

        # Determine month range from weekly reports
        all_starts = [r.get("week_start", "") for r in weekly_reports]
        all_ends = [r.get("week_end", "") for r in weekly_reports]
        month_start = min(all_starts) if all_starts else date.today().isoformat()
        month_end = max(all_ends) if all_ends else date.today().isoformat()

        report: dict[str, Any] = {
            "report_type": "monthly",
            "month_start": month_start,
            "month_end": month_end,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        # -- Total P&L and returns --------------------------------------------
        trading_days = max(len(set(
            t.timestamp_entry.date() for t in closed
        )), 1)
        avg_daily_pnl = total_pnl / trading_days

        report["total_pnl_and_returns"] = {
            "total_pnl": round(total_pnl, 2),
            "total_trades": len(closed),
            "trading_days": trading_days,
            "avg_daily_pnl": round(avg_daily_pnl, 2),
            "win_rate": round(_win_rate(trades), 1),
            "profit_factor": round(_profit_factor(pnl), 2) if len(pnl) > 0 else 0.0,
            "expectancy": round(_safe_div(total_pnl, len(closed)), 2) if closed else 0.0,
            "avg_trades_per_day": round(len(closed) / trading_days, 1),
        }

        # -- Risk-adjusted ratios ---------------------------------------------
        sharpe = _sharpe_ratio(pnl)
        sortino = _sortino_ratio(pnl)
        calmar = _calmar_ratio(pnl)
        max_dd, dd_duration = _max_drawdown(pnl)

        report["risk_ratios"] = {
            "sharpe_ratio": round(sharpe, 3),
            "sortino_ratio": round(sortino, 3),
            "calmar_ratio": round(calmar, 3),
            "profit_factor": round(_profit_factor(pnl), 2) if len(pnl) > 0 else 0.0,
        }

        # -- Drawdown analysis ------------------------------------------------
        # Find all drawdown episodes
        dd_episodes: list[dict] = []
        if len(pnl) > 0:
            cumulative = np.cumsum(pnl)
            running_max = np.maximum.accumulate(cumulative)
            drawdowns = cumulative - running_max
            in_dd = False
            dd_start = 0
            for i, dd in enumerate(drawdowns):
                if dd < 0 and not in_dd:
                    in_dd = True
                    dd_start = i
                elif dd == 0 and in_dd:
                    in_dd = False
                    dd_episodes.append({
                        "start_trade": dd_start,
                        "end_trade": i,
                        "duration": i - dd_start,
                        "depth": round(float(np.min(drawdowns[dd_start:i + 1])), 2),
                    })
            if in_dd:
                dd_episodes.append({
                    "start_trade": dd_start,
                    "end_trade": len(pnl) - 1,
                    "duration": len(pnl) - 1 - dd_start,
                    "depth": round(float(np.min(drawdowns[dd_start:])), 2),
                    "ongoing": True,
                })

        report["drawdown_analysis"] = {
            "max_drawdown": round(max_dd, 2),
            "max_drawdown_duration": dd_duration,
            "total_dd_episodes": len(dd_episodes),
            "avg_dd_depth": round(
                float(np.mean([ep["depth"] for ep in dd_episodes])), 2
            ) if dd_episodes else 0.0,
            "avg_dd_duration": round(
                float(np.mean([ep["duration"] for ep in dd_episodes])), 1
            ) if dd_episodes else 0.0,
            "longest_dd_duration": max(
                (ep["duration"] for ep in dd_episodes), default=0
            ),
            "episodes": dd_episodes[:10],  # Top 10 drawdown episodes
        }

        # -- Benchmark comparison ---------------------------------------------
        # Compare against simple benchmarks (buy-and-hold SPX, random entry)
        benchmark: dict[str, Any] = {}
        if closed:
            spx_start = closed[0].spx_at_entry
            spx_end = closed[-1].spx_at_entry
            spx_return_pct = _safe_div(spx_end - spx_start, spx_start) * 100.0
            benchmark["spx_return_pct"] = round(spx_return_pct, 2)
            benchmark["scanner_vs_spx_bps"] = round(
                (_safe_div(total_pnl, abs(spx_start * 100.0)) * 10000.0), 1
            )
        else:
            benchmark["spx_return_pct"] = 0.0
            benchmark["scanner_vs_spx_bps"] = 0.0

        # Risk-free comparison
        rf_monthly = _RISK_FREE_RATE / 12.0
        benchmark["risk_free_monthly_pct"] = round(rf_monthly * 100.0, 3)
        benchmark["excess_return"] = round(total_pnl, 2)

        report["benchmark_comparison"] = benchmark

        # -- Scanner alpha attribution ----------------------------------------
        scanner_alpha: dict[str, dict] = {}
        for scan_type in ScanType:
            st_trades = [t for t in closed if t.scan_type == scan_type]
            st_pnl = _pnl_array(st_trades)
            if len(st_pnl) > 0:
                alpha_contribution = float(np.sum(st_pnl))
                alpha_pct = _safe_div(alpha_contribution, total_pnl) * 100.0 if total_pnl != 0 else 0.0
            else:
                alpha_contribution = 0.0
                alpha_pct = 0.0

            scanner_alpha[scan_type.value] = {
                "trade_count": len(st_trades),
                "total_pnl": round(alpha_contribution, 2),
                "pnl_contribution_pct": round(alpha_pct, 1),
                "win_rate": round(_win_rate(st_trades), 1),
                "sharpe": round(_sharpe_ratio(st_pnl), 2),
                "sortino": round(_sortino_ratio(st_pnl), 2),
                "max_drawdown": round(_max_drawdown(st_pnl)[0], 2),
                "avg_pnl": round(float(np.mean(st_pnl)), 2) if len(st_pnl) > 0 else 0.0,
            }
        report["scanner_alpha"] = scanner_alpha

        # -- Regime performance breakdown -------------------------------------
        regime_perf: dict[str, dict] = {}
        for session_type in SessionType:
            rt = [t for t in closed if t.session_type == session_type]
            rt_pnl = _pnl_array(rt)
            regime_perf[session_type.value] = {
                "trade_count": len(rt),
                "total_pnl": round(float(np.sum(rt_pnl)), 2) if len(rt_pnl) > 0 else 0.0,
                "win_rate": round(_win_rate(rt), 1),
                "avg_pnl": round(float(np.mean(rt_pnl)), 2) if len(rt_pnl) > 0 else 0.0,
                "sharpe": round(_sharpe_ratio(rt_pnl), 2),
            }
        report["regime_breakdown"] = regime_perf

        # -- Calibration evolution --------------------------------------------
        calibration_evo: list[dict] = []
        for wr in weekly_reports:
            fwc = wr.get("factor_weight_changes", {})
            end_weights = fwc.get("end_weights", {})
            calibration_evo.append({
                "week_end": wr.get("week_end", ""),
                "weights": end_weights,
            })
        report["calibration_evolution"] = {
            "weekly_snapshots": calibration_evo,
            "total_weight_drift": MonthlyReport._compute_weight_drift(calibration_evo),
        }

        # -- Statistical significance (p-values, confidence intervals) --------
        report["statistical_significance"] = MonthlyReport._compute_full_significance(pnl)

        return report

    @staticmethod
    def format_text(report: dict) -> str:
        """Render the monthly report as human-readable text."""
        lines: list[str] = []
        sep = "=" * 72
        thin_sep = "-" * 72

        lines.append(sep)
        lines.append("  SCANIFY 0DTE SPX SCANNER -- MONTHLY REPORT")
        lines.append(f"  Period: {report['month_start']} to {report['month_end']}")
        lines.append(sep)

        # Total P&L
        tpr = report["total_pnl_and_returns"]
        lines.append("")
        lines.append("RETURNS SUMMARY")
        lines.append(thin_sep)
        lines.append(f"  Total P&L:         {_format_currency(tpr['total_pnl'])}")
        lines.append(f"  Total Trades:      {tpr['total_trades']}")
        lines.append(f"  Trading Days:      {tpr['trading_days']}")
        lines.append(f"  Avg Daily P&L:     {_format_currency(tpr['avg_daily_pnl'])}")
        lines.append(f"  Win Rate:          {_format_pct(tpr['win_rate'])}")
        lines.append(f"  Profit Factor:     {_format_ratio(tpr['profit_factor'])}")
        lines.append(f"  Expectancy:        {_format_currency(tpr['expectancy'])}")

        # Risk ratios
        rr = report["risk_ratios"]
        lines.append("")
        lines.append("RISK-ADJUSTED RATIOS")
        lines.append(thin_sep)
        lines.append(f"  Sharpe Ratio:      {_format_ratio(rr['sharpe_ratio'], 3)}")
        lines.append(f"  Sortino Ratio:     {_format_ratio(rr['sortino_ratio'], 3)}")
        lines.append(f"  Calmar Ratio:      {_format_ratio(rr['calmar_ratio'], 3)}")

        # Drawdown
        dd = report["drawdown_analysis"]
        lines.append("")
        lines.append("DRAWDOWN ANALYSIS")
        lines.append(thin_sep)
        lines.append(f"  Max Drawdown:      {_format_currency(dd['max_drawdown'])}")
        lines.append(f"  Max DD Duration:   {dd['max_drawdown_duration']} trades")
        lines.append(f"  DD Episodes:       {dd['total_dd_episodes']}")
        lines.append(f"  Avg DD Depth:      {_format_currency(dd['avg_dd_depth'])}")

        # Benchmark comparison
        bc = report["benchmark_comparison"]
        lines.append("")
        lines.append("BENCHMARK COMPARISON")
        lines.append(thin_sep)
        lines.append(f"  SPX Return:        {_format_pct(bc['spx_return_pct'])}")
        lines.append(f"  Scanner vs SPX:    {bc['scanner_vs_spx_bps']:.1f} bps")

        # Scanner alpha
        lines.append("")
        lines.append("SCANNER ALPHA ATTRIBUTION")
        lines.append(thin_sep)
        lines.append(f"  {'Scanner':<20} {'Trades':>7} {'P&L':>12} "
                      f"{'Contrib%':>9} {'Sharpe':>8}")
        lines.append(f"  {'-' * 20} {'-' * 7} {'-' * 12} {'-' * 9} {'-' * 8}")
        for scan_key, data in report.get("scanner_alpha", {}).items():
            label = _SCANNER_LABELS.get(scan_key, scan_key)
            lines.append(
                f"  {label:<20} {data['trade_count']:>7} "
                f"{_format_currency(data['total_pnl']):>12} "
                f"{_format_pct(data['pnl_contribution_pct']):>9} "
                f"{_format_ratio(data['sharpe']):>8}"
            )

        # Regime breakdown
        lines.append("")
        lines.append("REGIME PERFORMANCE")
        lines.append(thin_sep)
        lines.append(f"  {'Regime':<15} {'Trades':>7} {'P&L':>12} "
                      f"{'Win Rate':>10} {'Sharpe':>8}")
        lines.append(f"  {'-' * 15} {'-' * 7} {'-' * 12} {'-' * 10} {'-' * 8}")
        for regime_key, data in report.get("regime_breakdown", {}).items():
            if data["trade_count"] > 0:
                lines.append(
                    f"  {regime_key:<15} {data['trade_count']:>7} "
                    f"{_format_currency(data['total_pnl']):>12} "
                    f"{_format_pct(data['win_rate']):>10} "
                    f"{_format_ratio(data['sharpe']):>8}"
                )

        # Statistical significance
        sig = report.get("statistical_significance", {})
        lines.append("")
        lines.append("STATISTICAL SIGNIFICANCE")
        lines.append(thin_sep)
        lines.append(f"  t-statistic:       {_format_ratio(sig.get('t_statistic', 0.0), 4)}")
        lines.append(f"  p-value:           {sig.get('p_value', 1.0):.6f}")
        lines.append(f"  Significant:       {'YES' if sig.get('is_significant', False) else 'NO'}")
        ci = sig.get("confidence_interval", [0.0, 0.0])
        lines.append(f"  95% CI:            [{_format_currency(ci[0])}, {_format_currency(ci[1])}]")
        if "skewness" in sig:
            lines.append(f"  Skewness:          {_format_ratio(sig['skewness'], 3)}")
            lines.append(f"  Kurtosis:          {_format_ratio(sig['kurtosis'], 3)}")
        if "jarque_bera_p" in sig:
            lines.append(f"  JB Normality p:    {sig['jarque_bera_p']:.6f}")

        lines.append("")
        lines.append(sep)
        lines.append(f"  Generated: {report['generated_at']}")
        lines.append(sep)

        return "\n".join(lines)

    @staticmethod
    def _compute_weight_drift(snapshots: list[dict]) -> dict[str, float]:
        """Compute total absolute drift in factor weights across snapshots."""
        if len(snapshots) < 2:
            return {f: 0.0 for f in _FACTOR_NAMES}
        first_w = snapshots[0].get("weights", {})
        last_w = snapshots[-1].get("weights", {})
        return {
            f: round(abs(last_w.get(f, 0.0) - first_w.get(f, 0.0)), 4)
            for f in _FACTOR_NAMES
        }

    @staticmethod
    def _compute_full_significance(pnl: np.ndarray) -> dict:
        """Full statistical significance analysis with distribution tests."""
        if len(pnl) < _MIN_TRADES_FOR_STATS:
            return {
                "t_statistic": 0.0,
                "p_value": 1.0,
                "is_significant": False,
                "sample_size": int(len(pnl)),
                "confidence_interval": [0.0, 0.0],
                "note": f"Insufficient sample size (need >= {_MIN_TRADES_FOR_STATS})",
            }

        mean_pnl = float(np.mean(pnl))
        std_pnl = float(np.std(pnl, ddof=1))
        se = float(sp_stats.sem(pnl))
        n = len(pnl)

        # One-sample t-test: is mean PnL significantly different from zero?
        t_stat, p_value = sp_stats.ttest_1samp(pnl, 0.0)

        # Confidence interval
        t_crit = sp_stats.t.ppf((1 + _CONFIDENCE_LEVEL) / 2, n - 1)
        ci_low = mean_pnl - t_crit * se
        ci_high = mean_pnl + t_crit * se

        result: dict[str, Any] = {
            "t_statistic": round(float(t_stat), 4),
            "p_value": round(float(p_value), 6),
            "is_significant": float(p_value) < (1.0 - _CONFIDENCE_LEVEL),
            "sample_size": n,
            "mean_pnl": round(mean_pnl, 2),
            "std_pnl": round(std_pnl, 2),
            "standard_error": round(se, 4),
            "confidence_interval": [round(ci_low, 2), round(ci_high, 2)],
        }

        # Distribution shape
        if n >= 8:
            result["skewness"] = round(float(sp_stats.skew(pnl)), 4)
            result["kurtosis"] = round(float(sp_stats.kurtosis(pnl)), 4)

        # Jarque-Bera normality test
        if n >= 20:
            jb_stat, jb_p = sp_stats.jarque_bera(pnl)
            result["jarque_bera_statistic"] = round(float(jb_stat), 4)
            result["jarque_bera_p"] = round(float(jb_p), 6)
            result["distribution_is_normal"] = float(jb_p) > 0.05

        # Wilcoxon signed-rank test (non-parametric alternative)
        if n >= 10:
            try:
                w_stat, w_p = sp_stats.wilcoxon(pnl)
                result["wilcoxon_statistic"] = round(float(w_stat), 4)
                result["wilcoxon_p"] = round(float(w_p), 6)
            except ValueError:
                # All values identical -- degenerate case
                result["wilcoxon_statistic"] = 0.0
                result["wilcoxon_p"] = 1.0

        return result


# =============================================================================
# 4. TRADE JOURNAL
# =============================================================================


class TradeJournal:
    """Maintains a detailed trade journal for review.

    Each journal entry pairs a ``TradeLog`` with the surrounding market
    context, the reasoning behind the trade, and optional post-trade
    annotations.  Entries are stored in memory and can be exported in
    markdown or JSON format.

    Parameters
    ----------
    entries:
        Optional pre-loaded list of journal entries (for persistence
        round-tripping).
    """

    def __init__(self, entries: Optional[list[dict]] = None) -> None:
        self._entries: list[dict] = entries or []
        self._lessons: list[dict] = []

    # ------------------------------------------------------------------ #
    # Core operations
    # ------------------------------------------------------------------ #

    def add_entry(
        self,
        trade: TradeLog,
        market_context: dict,
        reasoning: str,
    ) -> None:
        """Add a new journal entry.

        Parameters
        ----------
        trade:
            The completed ``TradeLog`` record.
        market_context:
            Snapshot of market conditions at the time of the trade
            (VIX levels, GEX profile summary, session type, etc.).
        reasoning:
            Free-form text explaining the rationale for the trade.
        """
        entry: dict[str, Any] = {
            "trade_id": trade.trade_id,
            "timestamp": (trade.timestamp_entry.isoformat()
                          if trade.timestamp_entry else datetime.now(timezone.utc).isoformat()),
            "trade_date": trade.timestamp_entry.date().isoformat()
                          if trade.timestamp_entry else date.today().isoformat(),
            "scan_type": trade.scan_type.value,
            "direction": trade.direction.value,
            "strike": trade.strike,
            "option_type": trade.option_type.value,
            "entry_price": trade.entry_price,
            "exit_price": trade.exit_price,
            "pnl_dollars": trade.pnl_dollars,
            "pnl_percent": trade.pnl_percent,
            "exit_reason": trade.exit_reason.value if trade.exit_reason else None,
            "hold_time_minutes": trade.hold_time_minutes,
            "session_type": trade.session_type.value,
            "time_zone": trade.time_zone.value,
            "composite_direction_score": trade.composite_direction_score,
            "is_winner": trade.is_winner,
            "market_context": market_context,
            "reasoning": reasoning,
            "annotations": [],
            "tags": [],
            "lesson_learned": None,
        }
        self._entries.append(entry)
        logger.info(
            "Journal entry added: trade_id=%s scan=%s pnl=%s",
            trade.trade_id,
            trade.scan_type.value,
            trade.pnl_dollars,
        )

    def annotate(self, trade_id: str, annotation: str) -> bool:
        """Add a post-trade annotation to an existing entry.

        Returns True if the entry was found and annotated.
        """
        for entry in self._entries:
            if entry["trade_id"] == trade_id:
                entry["annotations"].append({
                    "text": annotation,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                return True
        logger.warning("Journal entry not found for annotation: trade_id=%s", trade_id)
        return False

    def tag_entry(self, trade_id: str, tags: list[str]) -> bool:
        """Add tags to a journal entry for categorisation.

        Returns True if the entry was found and tagged.
        """
        for entry in self._entries:
            if entry["trade_id"] == trade_id:
                entry["tags"].extend(tags)
                entry["tags"] = sorted(set(entry["tags"]))
                return True
        return False

    def add_lesson(self, trade_id: str, lesson: str, category: str = "general") -> bool:
        """Record a lesson learned from a specific trade.

        Returns True if the entry was found and the lesson recorded.
        """
        for entry in self._entries:
            if entry["trade_id"] == trade_id:
                entry["lesson_learned"] = lesson
                self._lessons.append({
                    "trade_id": trade_id,
                    "lesson": lesson,
                    "category": category,
                    "trade_date": entry["trade_date"],
                    "scan_type": entry["scan_type"],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                return True
        return False

    # ------------------------------------------------------------------ #
    # Query methods
    # ------------------------------------------------------------------ #

    def get_entries(
        self,
        start_date: date,
        end_date: date,
    ) -> list[dict]:
        """Retrieve journal entries within a date range (inclusive).

        Parameters
        ----------
        start_date:
            Start of the date range.
        end_date:
            End of the date range.

        Returns
        -------
        list[dict]
            Journal entries whose trade date falls within the range,
            sorted by timestamp ascending.
        """
        start_str = start_date.isoformat()
        end_str = end_date.isoformat()
        results = [
            e for e in self._entries
            if start_str <= e["trade_date"] <= end_str
        ]
        results.sort(key=lambda e: e["timestamp"])
        return results

    def search_entries(self, query: str) -> list[dict]:
        """Search journal entries by keyword in reasoning, annotations, and tags.

        Parameters
        ----------
        query:
            Case-insensitive search string.

        Returns
        -------
        list[dict]
            Matching journal entries sorted by relevance (simple frequency).
        """
        query_lower = query.lower()
        results: list[tuple[int, dict]] = []

        for entry in self._entries:
            score = 0
            # Search in reasoning
            reasoning = (entry.get("reasoning") or "").lower()
            score += reasoning.count(query_lower) * 3

            # Search in annotations
            for ann in entry.get("annotations", []):
                ann_text = (ann.get("text") or "").lower()
                score += ann_text.count(query_lower) * 2

            # Search in tags
            for tag in entry.get("tags", []):
                if query_lower in tag.lower():
                    score += 5

            # Search in lesson learned
            lesson = (entry.get("lesson_learned") or "").lower()
            score += lesson.count(query_lower) * 2

            # Search in scan type and direction
            if query_lower in entry.get("scan_type", "").lower():
                score += 2
            if query_lower in entry.get("direction", "").lower():
                score += 2

            if score > 0:
                results.append((score, entry))

        results.sort(key=lambda x: x[0], reverse=True)
        return [r[1] for r in results]

    def get_lessons_learned(self, category: Optional[str] = None) -> list[str]:
        """Retrieve accumulated lessons learned.

        Parameters
        ----------
        category:
            Optional category filter. If None, returns all lessons.

        Returns
        -------
        list[str]
            List of lesson strings, most recent first.
        """
        if category is None:
            return [l["lesson"] for l in reversed(self._lessons)]
        return [
            l["lesson"] for l in reversed(self._lessons)
            if l["category"] == category
        ]

    # ------------------------------------------------------------------ #
    # Export
    # ------------------------------------------------------------------ #

    def export_journal(self, format: str = "markdown") -> str:
        """Export the full journal to a formatted string.

        Parameters
        ----------
        format:
            Output format: ``"markdown"`` or ``"json"``.

        Returns
        -------
        str
            Complete journal content in the requested format.

        Raises
        ------
        ValueError
            If the format is not supported.
        """
        if format == "json":
            return self._export_json()
        elif format == "markdown":
            return self._export_markdown()
        else:
            raise ValueError(f"Unsupported export format: {format!r}. Use 'markdown' or 'json'.")

    def _export_json(self) -> str:
        """Export journal as pretty-printed JSON."""
        payload = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "total_entries": len(self._entries),
            "total_lessons": len(self._lessons),
            "entries": self._entries,
            "lessons": self._lessons,
        }
        return json.dumps(payload, indent=2, default=str)

    def _export_markdown(self) -> str:
        """Export journal as a formatted Markdown document."""
        lines: list[str] = []
        lines.append("# SCANIFY 0DTE Trade Journal")
        lines.append("")
        lines.append(f"*Exported: {datetime.now(timezone.utc).isoformat()}*")
        lines.append(f"*Total Entries: {len(self._entries)}*")
        lines.append("")

        # Summary statistics
        if self._entries:
            winners = sum(1 for e in self._entries if e.get("is_winner"))
            total = len(self._entries)
            total_pnl = sum(e.get("pnl_dollars") or 0.0 for e in self._entries)
            lines.append("## Summary")
            lines.append("")
            lines.append(f"| Metric | Value |")
            lines.append(f"|--------|-------|")
            lines.append(f"| Total Trades | {total} |")
            lines.append(f"| Winners | {winners} |")
            lines.append(f"| Losers | {total - winners} |")
            lines.append(f"| Win Rate | {_format_pct(winners / total * 100.0 if total else 0.0)} |")
            lines.append(f"| Total P&L | {_format_currency(total_pnl)} |")
            lines.append("")

        # Individual entries grouped by date
        entries_by_date: dict[str, list[dict]] = defaultdict(list)
        for entry in self._entries:
            entries_by_date[entry["trade_date"]].append(entry)

        for trade_date in sorted(entries_by_date.keys(), reverse=True):
            day_entries = entries_by_date[trade_date]
            day_pnl = sum(e.get("pnl_dollars") or 0.0 for e in day_entries)
            lines.append(f"## {trade_date} ({_format_currency(day_pnl)})")
            lines.append("")

            for entry in day_entries:
                pnl = entry.get("pnl_dollars") or 0.0
                result = "WIN" if entry.get("is_winner") else "LOSS"
                lines.append(f"### Trade: {entry['scan_type']} {entry['direction']} "
                             f"({result}: {_format_currency(pnl)})")
                lines.append("")
                lines.append(f"- **Strike:** {entry['strike']} {entry['option_type']}")
                lines.append(f"- **Entry:** ${entry['entry_price']:.2f} | "
                             f"**Exit:** ${entry.get('exit_price') or 0.0:.2f}")
                lines.append(f"- **P&L:** {_format_currency(pnl)} "
                             f"({_format_pct(entry.get('pnl_percent') or 0.0)})")
                lines.append(f"- **Hold Time:** {entry.get('hold_time_minutes') or 0.0:.0f} min")
                lines.append(f"- **Exit Reason:** {entry.get('exit_reason', 'N/A')}")
                lines.append(f"- **Session:** {entry['session_type']} | "
                             f"**Time Zone:** {entry['time_zone']}")
                lines.append(f"- **Direction Score:** {entry['composite_direction_score']:.1f}")
                lines.append("")

                # Reasoning
                lines.append(f"**Reasoning:** {entry.get('reasoning', 'N/A')}")
                lines.append("")

                # Annotations
                annotations = entry.get("annotations", [])
                if annotations:
                    lines.append("**Annotations:**")
                    for ann in annotations:
                        lines.append(f"- [{ann['timestamp']}] {ann['text']}")
                    lines.append("")

                # Tags
                tags = entry.get("tags", [])
                if tags:
                    lines.append(f"**Tags:** {', '.join(tags)}")
                    lines.append("")

                # Lesson
                lesson = entry.get("lesson_learned")
                if lesson:
                    lines.append(f"**Lesson Learned:** {lesson}")
                    lines.append("")

                lines.append("---")
                lines.append("")

        # Lessons learned section
        if self._lessons:
            lines.append("## Lessons Learned")
            lines.append("")
            categories: dict[str, list[dict]] = defaultdict(list)
            for lesson in self._lessons:
                categories[lesson["category"]].append(lesson)
            for cat, cat_lessons in sorted(categories.items()):
                lines.append(f"### {cat.title()}")
                lines.append("")
                for l in cat_lessons:
                    lines.append(f"- [{l['trade_date']}] {l['lesson']}")
                lines.append("")

        return "\n".join(lines)

    @property
    def entry_count(self) -> int:
        """Total number of journal entries."""
        return len(self._entries)

    @property
    def lesson_count(self) -> int:
        """Total number of recorded lessons."""
        return len(self._lessons)


# =============================================================================
# 5. REPORT SCHEDULER
# =============================================================================


class ReportScheduler:
    """Schedules and dispatches reports on configurable cadences.

    The scheduler manages asyncio tasks for automatic report generation
    and delivery at the end of each trading day, week, and month.
    Reports can be dispatched to multiple channels: file system, webhook,
    or log output.

    Parameters
    ----------
    daily_generator:
        Callable that produces a daily report dict.
    weekly_generator:
        Callable that produces a weekly report dict.
    monthly_generator:
        Callable that produces a monthly report dict.
    output_dir:
        Directory path for file-based report output.
    """

    def __init__(
        self,
        daily_generator: Optional[Any] = None,
        weekly_generator: Optional[Any] = None,
        monthly_generator: Optional[Any] = None,
        output_dir: str = "./reports",
    ) -> None:
        self._daily_generator = daily_generator
        self._weekly_generator = weekly_generator
        self._monthly_generator = monthly_generator
        self._output_dir = output_dir
        self._scheduled_tasks: dict[str, asyncio.Task] = {}
        self._daily_time: time = time(16, 30)
        self._weekly_day: str = "saturday"
        self._monthly_day: int = 1
        self._channels: list[str] = ["file", "log"]
        self._webhook_url: Optional[str] = None
        self._running: bool = False

    # ------------------------------------------------------------------ #
    # Schedule configuration
    # ------------------------------------------------------------------ #

    def schedule_daily_report(self, report_time: time = time(16, 30)) -> None:
        """Schedule daily report generation.

        Parameters
        ----------
        report_time:
            Time of day (Eastern Time) to generate the daily report.
            Defaults to 4:30 PM ET (30 minutes after market close).
        """
        self._daily_time = report_time
        logger.info("Daily report scheduled at %s ET", report_time.strftime("%H:%M"))

    def schedule_weekly_report(self, day: str = "saturday") -> None:
        """Schedule weekly report generation.

        Parameters
        ----------
        day:
            Day of the week to generate the weekly report.
            Defaults to Saturday.
        """
        self._weekly_day = day.lower()
        logger.info("Weekly report scheduled for %s", self._weekly_day.title())

    def schedule_monthly_report(self, day_of_month: int = 1) -> None:
        """Schedule monthly report generation.

        Parameters
        ----------
        day_of_month:
            Day of the month to generate the monthly report.
            Defaults to the 1st.
        """
        self._monthly_day = max(1, min(28, day_of_month))
        logger.info("Monthly report scheduled for day %d of each month", self._monthly_day)

    def set_channels(self, channels: list[str]) -> None:
        """Configure dispatch channels.

        Parameters
        ----------
        channels:
            List of channel identifiers. Supported: ``"file"``, ``"log"``,
            ``"webhook"``.
        """
        valid = {"file", "log", "webhook"}
        self._channels = [c for c in channels if c in valid]
        logger.info("Report channels set: %s", self._channels)

    def set_webhook(self, url: str) -> None:
        """Set the webhook URL for report dispatch.

        Parameters
        ----------
        url:
            HTTP(S) endpoint that accepts POST requests with JSON body.
        """
        self._webhook_url = url
        if "webhook" not in self._channels:
            self._channels.append("webhook")
        logger.info("Webhook configured: %s", url[:50])

    # ------------------------------------------------------------------ #
    # Dispatch
    # ------------------------------------------------------------------ #

    async def dispatch_report(
        self,
        report: dict,
        channels: Optional[list[str]] = None,
    ) -> None:
        """Dispatch a report to the configured channels.

        Parameters
        ----------
        report:
            Report dictionary (from any of the report generators).
        channels:
            Override channel list. If None, uses the configured channels.
        """
        dispatch_channels = channels or self._channels
        report_type = report.get("report_type", "unknown")

        for channel in dispatch_channels:
            try:
                if channel == "file":
                    await self._dispatch_file(report, report_type)
                elif channel == "log":
                    self._dispatch_log(report, report_type)
                elif channel == "webhook":
                    await self._dispatch_webhook(report, report_type)
                else:
                    logger.warning("Unknown dispatch channel: %s", channel)
            except Exception:
                logger.exception(
                    "Failed to dispatch %s report to channel %s",
                    report_type,
                    channel,
                )

    async def _dispatch_file(self, report: dict, report_type: str) -> None:
        """Write report to file system as JSON and text."""
        import os

        os.makedirs(self._output_dir, exist_ok=True)

        report_date = report.get("report_date") or report.get(
            "week_end") or report.get("month_end") or date.today().isoformat()
        base_name = f"{report_type}_{report_date}"

        # JSON output
        json_path = os.path.join(self._output_dir, f"{base_name}.json")
        json_content = json.dumps(report, indent=2, default=str)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._write_file, json_path, json_content)

        # Text output
        text_content = ""
        if report_type == "daily":
            text_content = DailyReport.format_text(report)
        elif report_type == "weekly":
            text_content = WeeklyReport.format_text(report)
        elif report_type == "monthly":
            text_content = MonthlyReport.format_text(report)

        if text_content:
            text_path = os.path.join(self._output_dir, f"{base_name}.txt")
            await loop.run_in_executor(None, self._write_file, text_path, text_content)

        logger.info("Report written to %s", json_path)

    @staticmethod
    def _write_file(path: str, content: str) -> None:
        """Synchronous file write helper."""
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def _dispatch_log(self, report: dict, report_type: str) -> None:
        """Write report summary to the logger."""
        if report_type == "daily":
            ts = report.get("trade_summary", {})
            logger.info(
                "DAILY REPORT | Date: %s | P&L: %s | Trades: %d | Win Rate: %s",
                report.get("report_date"),
                _format_currency(ts.get("total_pnl", 0.0)),
                ts.get("total_trades", 0),
                _format_pct(ts.get("win_rate", 0.0)),
            )
        elif report_type == "weekly":
            wp = report.get("week_pnl", {})
            logger.info(
                "WEEKLY REPORT | %s to %s | P&L: %s | Trades: %d | Sharpe: %s",
                report.get("week_start"),
                report.get("week_end"),
                _format_currency(wp.get("total_pnl", 0.0)),
                wp.get("total_trades", 0),
                _format_ratio(wp.get("sharpe_ratio", 0.0)),
            )
        elif report_type == "monthly":
            tpr = report.get("total_pnl_and_returns", {})
            rr = report.get("risk_ratios", {})
            logger.info(
                "MONTHLY REPORT | %s to %s | P&L: %s | Sharpe: %s | Sortino: %s",
                report.get("month_start"),
                report.get("month_end"),
                _format_currency(tpr.get("total_pnl", 0.0)),
                _format_ratio(rr.get("sharpe_ratio", 0.0)),
                _format_ratio(rr.get("sortino_ratio", 0.0)),
            )

    async def _dispatch_webhook(self, report: dict, report_type: str) -> None:
        """Send report to a webhook endpoint via HTTP POST."""
        if not self._webhook_url:
            logger.warning("Webhook URL not configured; skipping webhook dispatch.")
            return

        try:
            import aiohttp
        except ImportError:
            logger.error("aiohttp is required for webhook dispatch.")
            return

        payload = {
            "report_type": report_type,
            "report": report,
            "dispatched_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self._webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30),
                    headers={"Content-Type": "application/json"},
                ) as resp:
                    if resp.status < 300:
                        logger.info(
                            "Webhook dispatch successful: %s report -> %d",
                            report_type,
                            resp.status,
                        )
                    else:
                        body = await resp.text()
                        logger.error(
                            "Webhook dispatch failed: %s report -> %d: %s",
                            report_type,
                            resp.status,
                            body[:200],
                        )
        except asyncio.TimeoutError:
            logger.error("Webhook dispatch timed out for %s report", report_type)
        except Exception:
            logger.exception("Webhook dispatch error for %s report", report_type)

    # ------------------------------------------------------------------ #
    # Runner
    # ------------------------------------------------------------------ #

    async def start(self) -> None:
        """Start the background scheduling loop.

        Spawns asyncio tasks that sleep until the configured report times
        and then invoke the corresponding generators and dispatchers.
        """
        self._running = True
        logger.info("ReportScheduler starting (daily=%s, weekly=%s, monthly=day %d)",
                     self._daily_time.strftime("%H:%M"),
                     self._weekly_day,
                     self._monthly_day)

        self._scheduled_tasks["daily"] = asyncio.create_task(
            self._daily_loop(), name="report_daily_loop"
        )
        self._scheduled_tasks["weekly"] = asyncio.create_task(
            self._weekly_loop(), name="report_weekly_loop"
        )
        self._scheduled_tasks["monthly"] = asyncio.create_task(
            self._monthly_loop(), name="report_monthly_loop"
        )

    async def stop(self) -> None:
        """Stop all scheduled report tasks."""
        self._running = False
        for name, task in self._scheduled_tasks.items():
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                logger.info("Cancelled %s report task", name)
        self._scheduled_tasks.clear()

    async def _daily_loop(self) -> None:
        """Background loop that triggers daily reports at the configured time."""
        while self._running:
            now = datetime.now(timezone.utc)
            # Compute seconds until next target time (simplified UTC scheduling)
            target = now.replace(
                hour=self._daily_time.hour,
                minute=self._daily_time.minute,
                second=0,
                microsecond=0,
            )
            if target <= now:
                target += timedelta(days=1)
            wait_seconds = (target - now).total_seconds()
            await asyncio.sleep(wait_seconds)

            if not self._running:
                break

            if self._daily_generator:
                try:
                    report = self._daily_generator()
                    await self.dispatch_report(report)
                except Exception:
                    logger.exception("Daily report generation failed")

    async def _weekly_loop(self) -> None:
        """Background loop that triggers weekly reports on the configured day."""
        day_map = {
            "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6,
        }
        target_dow = day_map.get(self._weekly_day, 5)

        while self._running:
            now = datetime.now(timezone.utc)
            days_ahead = (target_dow - now.weekday()) % 7
            if days_ahead == 0 and now.hour >= 12:
                days_ahead = 7
            target = (now + timedelta(days=days_ahead)).replace(
                hour=9, minute=0, second=0, microsecond=0
            )
            wait_seconds = max(0, (target - now).total_seconds())
            await asyncio.sleep(wait_seconds)

            if not self._running:
                break

            if self._weekly_generator:
                try:
                    report = self._weekly_generator()
                    await self.dispatch_report(report)
                except Exception:
                    logger.exception("Weekly report generation failed")

    async def _monthly_loop(self) -> None:
        """Background loop that triggers monthly reports on the configured day."""
        while self._running:
            now = datetime.now(timezone.utc)
            # Find next occurrence of the target day
            if now.day < self._monthly_day:
                target = now.replace(
                    day=self._monthly_day, hour=9, minute=0, second=0, microsecond=0
                )
            else:
                # Move to next month
                if now.month == 12:
                    target = now.replace(
                        year=now.year + 1, month=1,
                        day=self._monthly_day, hour=9,
                        minute=0, second=0, microsecond=0,
                    )
                else:
                    target = now.replace(
                        month=now.month + 1,
                        day=self._monthly_day, hour=9,
                        minute=0, second=0, microsecond=0,
                    )
            wait_seconds = max(0, (target - now).total_seconds())
            await asyncio.sleep(wait_seconds)

            if not self._running:
                break

            if self._monthly_generator:
                try:
                    report = self._monthly_generator()
                    await self.dispatch_report(report)
                except Exception:
                    logger.exception("Monthly report generation failed")
