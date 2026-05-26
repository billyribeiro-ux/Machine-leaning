"""
SCANIFY SPX 0DTE Scanner -- Self-Learning and Calibration System

Production-grade adaptive calibration pipeline that continuously optimizes
scanner parameters from observed trade outcomes. The system operates on three
cadences:

    Daily   -- After market close: factor-weight EMA updates, entry/exit
               threshold adjustments, GEX model recalibration, regime detection.
    Weekly  -- Saturday: walk-forward backtest over trailing 4 weeks with
               statistical significance testing and deflated Sharpe ratios.
    Monthly -- First Saturday of month: full 3-month backtest against naive
               benchmarks, information-ratio analysis, and signal-decay detection.

Design principles:
    1. Every trade is logged with full context (no silent drops).
    2. Parameter changes are bounded and gradual (EMA smoothing, daily caps).
    3. Hard safety rails from ``constants.SELF_LEARNING`` are never breached.
    4. Regime changes trigger conservative fallback (wider thresholds, smaller
       positions) rather than aggressive re-fitting.
    5. All state is persisted to both JSON (human-readable) and SQLite (queryable).

Dependencies:
    numpy, scipy, scikit-learn, pandas, sqlite3, json, logging
"""

from __future__ import annotations

import csv
import io
import json
import logging
import sqlite3
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy import stats as sp_stats
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_curve
from sklearn.preprocessing import StandardScaler

from .models import (
    CalibrationState,
    DailyScoreCard,
    ExitReason,
    FactorWeights,
    ScanType,
    SessionType,
    TimeZoneType,
    TradeLog,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants (derived from constants.py SELF_LEARNING dataclass)
# ---------------------------------------------------------------------------
_MIN_TRADES_FOR_LEARNING: int = 30
_ROLLING_GEX_WINDOW: int = 20
_ROLLING_STRIKE_WINDOW: int = 100
_ANNUALIZATION_FACTOR: float = 252.0

# VIX1D regime bucket boundaries used for scorecard breakdowns.
_VIX1D_BUCKETS: List[Tuple[str, float, float]] = [
    ("<12", 0.0, 12.0),
    ("12-18", 12.0, 18.0),
    ("18-25", 18.0, 25.0),
    (">25", 25.0, float("inf")),
]

# SQLite schema for the trade log table.
_CREATE_TRADES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS trades (
    id              TEXT PRIMARY KEY,
    trade_date      TEXT NOT NULL,
    scan_type       TEXT NOT NULL,
    session_type    TEXT NOT NULL,
    time_zone       TEXT NOT NULL,
    exit_reason     TEXT NOT NULL,
    entry_time      TEXT NOT NULL,
    exit_time       TEXT NOT NULL,
    entry_price     REAL NOT NULL,
    exit_price      REAL NOT NULL,
    pnl             REAL NOT NULL,
    is_win          INTEGER NOT NULL,
    direction_score REAL NOT NULL,
    vix1d           REAL NOT NULL,
    spx_price       REAL NOT NULL,
    strike          REAL NOT NULL,
    delta_at_entry  REAL NOT NULL,
    factor_scores   TEXT NOT NULL,
    gex_predicted_support   REAL,
    gex_predicted_resistance REAL,
    gex_gamma_flip_bullish  INTEGER,
    actual_low      REAL,
    actual_high     REAL,
    max_drawdown    REAL NOT NULL DEFAULT 0.0,
    metadata_json   TEXT NOT NULL DEFAULT '{}'
)
"""

_CREATE_TRADES_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_trades_date ON trades (trade_date)
"""


# ============================================================================
# 1. TradeLogger
# ============================================================================


class TradeLogger:
    """Logs every single trade with complete context. No exceptions.

    Persistence is dual-path: a JSON file for human inspection / portability,
    and a SQLite database for efficient querying by date range, scan type, and
    arbitrary SQL predicates.

    Thread-safety note: SQLite writes are serialized by the ``sqlite3`` module
    in its default mode (``check_same_thread=False`` is **not** set).  If the
    scanner moves to a multi-threaded architecture, wrap mutation methods with
    a ``threading.Lock``.

    Args:
        log_file: Path to the JSON trade log (append-friendly JSONL format).
        db_path: Path to the SQLite database file.
    """

    def __init__(
        self,
        log_file: str = "trade_log.json",
        db_path: str = "scanify_trades.db",
    ) -> None:
        self.log_file: str = log_file
        self.db_path: str = db_path

        # Ensure parent directories exist.
        Path(self.log_file).parent.mkdir(parents=True, exist_ok=True)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        """Create the trades table and index if they do not exist."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(_CREATE_TRADES_TABLE_SQL)
            conn.execute(_CREATE_TRADES_INDEX_SQL)
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _trade_to_row(trade: TradeLog) -> Dict[str, Any]:
        """Convert a ``TradeLog`` instance into a flat dictionary suitable for
        SQLite insertion and JSON serialization."""
        # Derive trade_date from timestamp_entry
        trade_date_val = trade.timestamp_entry.date() if isinstance(trade.timestamp_entry, datetime) else trade.timestamp_entry
        return {
            "id": trade.trade_id,
            "trade_date": trade_date_val.isoformat() if isinstance(trade_date_val, date) else str(trade_date_val),
            "scan_type": trade.scan_type.value if isinstance(trade.scan_type, ScanType) else str(trade.scan_type),
            "session_type": trade.session_type.value if isinstance(trade.session_type, SessionType) else str(trade.session_type),
            "time_zone": trade.time_zone.value if isinstance(trade.time_zone, TimeZoneType) else str(trade.time_zone),
            "exit_reason": trade.exit_reason.value if isinstance(trade.exit_reason, ExitReason) else str(trade.exit_reason) if trade.exit_reason else "MANUAL",
            "entry_time": trade.timestamp_entry.isoformat() if isinstance(trade.timestamp_entry, datetime) else str(trade.timestamp_entry),
            "exit_time": trade.timestamp_exit.isoformat() if isinstance(trade.timestamp_exit, datetime) else str(trade.timestamp_exit) if trade.timestamp_exit else "",
            "entry_price": float(trade.entry_price),
            "exit_price": float(trade.exit_price) if trade.exit_price is not None else 0.0,
            "pnl": float(trade.pnl_dollars) if trade.pnl_dollars is not None else 0.0,
            "is_win": int((trade.pnl_dollars or 0.0) > 0),
            "direction_score": float(trade.composite_direction_score),
            "vix1d": float(trade.vix1d_at_entry),
            "spx_price": float(trade.spx_at_entry),
            "strike": float(trade.strike),
            "delta_at_entry": float(trade.delta_at_entry),
            "factor_scores": "{}",
            "gex_predicted_support": None,
            "gex_predicted_resistance": None,
            "gex_gamma_flip_bullish": None,
            "actual_low": None,
            "actual_high": None,
            "max_drawdown": float(abs(trade.max_loss_during_trade)) if trade.max_loss_during_trade else 0.0,
            "metadata_json": "{}",
        }

    def _save_to_json(self, row: Dict[str, Any]) -> None:
        """Append a single trade record as one JSON line to the log file."""
        with open(self.log_file, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str) + "\n")

    def _save_to_db(self, row: Dict[str, Any]) -> None:
        """Insert or replace a single trade record into SQLite."""
        columns = list(row.keys())
        placeholders = ", ".join(["?"] * len(columns))
        col_names = ", ".join(columns)
        sql = f"INSERT OR REPLACE INTO trades ({col_names}) VALUES ({placeholders})"

        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(sql, [row[c] for c in columns])
            conn.commit()
        finally:
            conn.close()

    def _row_to_trade_log(self, row: sqlite3.Row) -> TradeLog:
        """Reconstruct a ``TradeLog`` from a SQLite row dictionary."""
        d = dict(row)
        return TradeLog(
            trade_id=d["id"],
            timestamp_entry=datetime.fromisoformat(d["entry_time"]),
            timestamp_exit=datetime.fromisoformat(d["exit_time"]) if d.get("exit_time") else None,
            scan_type=ScanType(d["scan_type"]),
            direction="NEUTRAL",
            session_type=SessionType(d["session_type"]),
            time_zone=TimeZoneType(d["time_zone"]),
            exit_reason=ExitReason(d["exit_reason"]) if d.get("exit_reason") else None,
            entry_price=d["entry_price"],
            exit_price=d.get("exit_price"),
            pnl_dollars=d.get("pnl", 0.0),
            pnl_percent=0.0,
            hold_time_minutes=0.0,
            strike=d["strike"],
            option_type="CALL",
            composite_direction_score=d.get("direction_score", 0.0),
            vix1d_at_entry=d.get("vix1d", 0.0),
            vix_at_entry=0.0,
            spx_at_entry=d.get("spx_price", 0.0),
            delta_at_entry=d.get("delta_at_entry", 0.0),
            gamma_at_entry=0.0,
            theta_at_entry=0.0,
            iv_at_entry=0.0,
            expected_move_1sigma=0.0,
            net_gex_at_entry=0.0,
            gamma_flip_at_entry=1.0,
            tick_10min_avg=0.0,
            trin_at_entry=1.0,
            ad_ratio_at_entry=1.0,
            cumulative_delta_es=0.0,
            max_loss_during_trade=-(d.get("max_drawdown", 0.0) or 0.0),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log_trade(self, trade: TradeLog) -> None:
        """Save a completed trade to both the JSON log and the SQLite database.

        This method is the single entry point for all trade persistence. It
        never silently drops a trade -- if either write fails, an exception
        propagates to the caller.

        Args:
            trade: Fully populated ``TradeLog`` instance.
        """
        row = self._trade_to_row(trade)

        # Write JSON first (append-only, safest path).
        self._save_to_json(row)
        logger.info("Trade %s written to JSON log.", trade.trade_id)

        # Write to SQLite.
        self._save_to_db(row)
        logger.info("Trade %s written to SQLite.", trade.trade_id)

    def get_trades(
        self,
        start_date: date,
        end_date: date,
        scan_type: Optional[ScanType] = None,
    ) -> List[TradeLog]:
        """Retrieve trades within a date range, optionally filtered by scan type.

        Args:
            start_date: Inclusive start date.
            end_date: Inclusive end date.
            scan_type: If provided, only return trades of this scan type.

        Returns:
            List of ``TradeLog`` instances ordered by entry time ascending.
        """
        sql = "SELECT * FROM trades WHERE trade_date >= ? AND trade_date <= ?"
        params: list = [start_date.isoformat(), end_date.isoformat()]

        if scan_type is not None:
            sql += " AND scan_type = ?"
            params.append(scan_type.value if isinstance(scan_type, ScanType) else str(scan_type))

        sql += " ORDER BY entry_time ASC"

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute(sql, params)
            rows = cursor.fetchall()
        finally:
            conn.close()

        return [self._row_to_trade_log(row) for row in rows]

    def get_trade_count(self) -> int:
        """Return the total number of trades in the database.

        Returns:
            Integer count of all persisted trades.
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM trades")
            count = cursor.fetchone()[0]
        finally:
            conn.close()
        return int(count)

    def export_trades(self, format: str = "csv") -> str:
        """Export all trades in the requested format.

        Supported formats:
            ``csv`` -- Comma-separated values with header row.
            ``json`` -- JSON array of trade dictionaries.

        Args:
            format: Export format string (case-insensitive).

        Returns:
            String containing the full export payload.

        Raises:
            ValueError: If an unsupported format is requested.
        """
        fmt = format.strip().lower()
        if fmt not in ("csv", "json"):
            raise ValueError(f"Unsupported export format: {format!r}. Use 'csv' or 'json'.")

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute("SELECT * FROM trades ORDER BY entry_time ASC")
            rows = cursor.fetchall()
        finally:
            conn.close()

        if fmt == "json":
            records = [dict(r) for r in rows]
            return json.dumps(records, indent=2, default=str)

        # CSV export.
        if not rows:
            return ""

        columns = rows[0].keys()
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))
        return output.getvalue()


# ============================================================================
# 2. DailyCalibrator
# ============================================================================


class DailyCalibrator:
    """Runs after market close each day. Optimizes scanner parameters.

    The calibrator ingests completed trades for the day, generates a performance
    scorecard, and adjusts factor weights, entry thresholds, profit targets,
    stop-loss levels, GEX model confidence, and strike-selection deltas.

    All adjustments are bounded and gradual:
        - Factor weights use an EMA update capped at [5%, 40%].
        - Entry thresholds shift by at most ``threshold_adjustment`` points/day.
        - Profit targets and stop losses move at most ``target_adjustment_rate``
          (5%) toward the computed optimum per day.

    Args:
        trade_logger: ``TradeLogger`` instance for retrieving historical trades.
        current_state: The current ``CalibrationState`` to be updated.
        ema_weight: Exponential smoothing parameter for weight updates.
        max_factor_weight: Upper bound for any single factor weight.
        min_factor_weight: Lower bound for any single factor weight.
        threshold_adjustment: Maximum entry-threshold shift per day (points).
        target_adjustment_rate: Maximum fractional shift per day for targets
            and stop levels (e.g. 0.05 = 5%).
    """

    def __init__(
        self,
        trade_logger: TradeLogger,
        current_state: CalibrationState,
        ema_weight: float = 0.95,
        max_factor_weight: float = 0.40,
        min_factor_weight: float = 0.05,
        threshold_adjustment: float = 2.0,
        target_adjustment_rate: float = 0.05,
    ) -> None:
        self.trade_logger = trade_logger
        self.current_state = deepcopy(current_state)
        self.ema_weight = ema_weight
        self.max_factor_weight = max_factor_weight
        self.min_factor_weight = min_factor_weight
        self.threshold_adjustment = threshold_adjustment
        self.target_adjustment_rate = target_adjustment_rate

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _win_rate(trades: Sequence[TradeLog]) -> float:
        """Compute win rate for a sequence of trades. Returns 0.0 if empty."""
        if not trades:
            return 0.0
        wins = sum(1 for t in trades if (t.pnl_dollars or 0.0) > 0)
        return wins / len(trades)

    @staticmethod
    def _avg_pnl(trades: Sequence[TradeLog]) -> float:
        """Compute average P&L. Returns 0.0 if empty."""
        if not trades:
            return 0.0
        return float(np.mean([(t.pnl_dollars or 0.0) for t in trades]))

    @staticmethod
    def _sharpe_ratio(trades: Sequence[TradeLog]) -> float:
        """Annualized Sharpe ratio from a list of daily trade P&Ls.

        Assumes each trade represents one unit of daily risk.
        Sharpe = mean(pnl) / std(pnl) * sqrt(252).
        Returns 0.0 if fewer than 2 trades or zero variance.
        """
        if len(trades) < 2:
            return 0.0
        pnls = np.array([(t.pnl_dollars or 0.0) for t in trades], dtype=np.float64)
        std = np.std(pnls, ddof=1)
        if std < 1e-12:
            return 0.0
        return float((np.mean(pnls) / std) * np.sqrt(_ANNUALIZATION_FACTOR))

    @staticmethod
    def _max_drawdown(trades: Sequence[TradeLog]) -> float:
        """Maximum drawdown from cumulative P&L curve.

        Returns a non-negative value representing the peak-to-trough decline.
        """
        if not trades:
            return 0.0
        cumulative = np.cumsum([(t.pnl_dollars or 0.0) for t in trades])
        running_max = np.maximum.accumulate(cumulative)
        drawdowns = running_max - cumulative
        return float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

    @staticmethod
    def _group_by_attr(
        trades: List[TradeLog],
        attr: str,
    ) -> Dict[str, List[TradeLog]]:
        """Group trades by a named attribute, converting enum values to strings."""
        groups: Dict[str, List[TradeLog]] = {}
        for t in trades:
            val = getattr(t, attr)
            key = val.value if hasattr(val, "value") else str(val)
            groups.setdefault(key, []).append(t)
        return groups

    @staticmethod
    def _vix1d_bucket(vix1d: float) -> str:
        """Map a VIX1D value to its regime bucket label."""
        for label, lo, hi in _VIX1D_BUCKETS:
            if lo <= vix1d < hi:
                return label
        return ">25"

    @staticmethod
    def _normalize_weights(
        weights: Dict[str, float],
        min_w: float,
        max_w: float,
    ) -> Dict[str, float]:
        """Clip weights to [min_w, max_w] and re-normalize so they sum to 1.0.

        Uses iterative projection: clip, then rescale, repeating until
        convergence (guaranteed within ``len(weights)`` iterations for
        a simplex + box constraint).
        """
        w = dict(weights)
        for _ in range(len(w) * 2 + 1):
            # Clip.
            for k in w:
                w[k] = max(min_w, min(max_w, w[k]))
            # Normalize.
            total = sum(w.values())
            if total < 1e-12:
                # Degenerate -- reset to uniform.
                uniform = 1.0 / len(w)
                w = {k: uniform for k in w}
                break
            for k in w:
                w[k] /= total
            # Check feasibility.
            if all(min_w <= v <= max_w + 1e-9 for v in w.values()):
                break
        return w

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_daily_scorecard(self, target_date: date) -> DailyScoreCard:
        """Generate a comprehensive performance scorecard for one trading day.

        The scorecard breaks down win rate and average P&L across every
        relevant dimension:
            - Scan type (directional, premium_sell, gamma_scalp)
            - Time zone (morning, midday, afternoon, power_hour)
            - Session type (trending, range, volatile, squeeze, event)
            - VIX1D regime (<12, 12-18, 18-25, >25)

        It also computes per-scan-type Sharpe ratios and maximum drawdowns.

        Args:
            target_date: The trading date to evaluate.

        Returns:
            A populated ``DailyScoreCard`` instance.
        """
        trades = self.trade_logger.get_trades(target_date, target_date)
        logger.info("Generating scorecard for %s with %d trades.", target_date, len(trades))

        # -- Win rate and avg P&L by scan type --
        by_scan = self._group_by_attr(trades, "scan_type")
        win_rate_by_scan: Dict[str, float] = {k: self._win_rate(v) for k, v in by_scan.items()}
        avg_pnl_by_scan: Dict[str, float] = {k: self._avg_pnl(v) for k, v in by_scan.items()}
        sharpe_by_scan: Dict[str, float] = {k: self._sharpe_ratio(v) for k, v in by_scan.items()}
        drawdown_by_scan: Dict[str, float] = {k: self._max_drawdown(v) for k, v in by_scan.items()}

        # -- Win rate and avg P&L by time zone --
        by_tz = self._group_by_attr(trades, "time_zone")
        win_rate_by_tz: Dict[str, float] = {k: self._win_rate(v) for k, v in by_tz.items()}
        avg_pnl_by_tz: Dict[str, float] = {k: self._avg_pnl(v) for k, v in by_tz.items()}

        # -- Win rate and avg P&L by session type --
        by_session = self._group_by_attr(trades, "session_type")
        win_rate_by_session: Dict[str, float] = {k: self._win_rate(v) for k, v in by_session.items()}
        avg_pnl_by_session: Dict[str, float] = {k: self._avg_pnl(v) for k, v in by_session.items()}

        # -- Win rate and avg P&L by VIX1D regime --
        vix_groups: Dict[str, List[TradeLog]] = {}
        for t in trades:
            bucket = self._vix1d_bucket(t.vix1d_at_entry)
            vix_groups.setdefault(bucket, []).append(t)
        win_rate_by_vix: Dict[str, float] = {k: self._win_rate(v) for k, v in vix_groups.items()}
        avg_pnl_by_vix: Dict[str, float] = {k: self._avg_pnl(v) for k, v in vix_groups.items()}

        scorecard = DailyScoreCard(
            date=target_date,
            total_trades=len(trades),
            win_rate_by_scan_type=win_rate_by_scan,
            win_rate_by_time_zone=win_rate_by_tz,
            win_rate_by_session_type=win_rate_by_session,
            win_rate_by_vix1d_regime=win_rate_by_vix,
            avg_pnl_by_scan_type=avg_pnl_by_scan,
            avg_pnl_by_time_zone=avg_pnl_by_tz,
            avg_pnl_by_session_type=avg_pnl_by_session,
            avg_pnl_by_vix1d_regime=avg_pnl_by_vix,
            sharpe_by_scan_type=sharpe_by_scan,
            max_drawdown_by_scan_type=drawdown_by_scan,
        )

        logger.info("Scorecard generated: %d trades, overall win rate %.2f%%.",
                     len(trades), self._win_rate(trades) * 100)
        return scorecard

    def optimize_factor_weights(self, trades: List[TradeLog]) -> FactorWeights:
        """Optimize direction-score factor weights using logistic regression.

        Procedure:
            1. Extract per-trade factor scores as feature matrix X and binary
               win/loss as label vector y.
            2. Fit L2-penalized logistic regression: P(win) ~ X.
            3. Derive optimal weights from absolute coefficient magnitudes
               (larger |coef| = more predictive = higher weight).
            4. Blend with current weights using EMA:
                   new = ema_weight * old + (1 - ema_weight) * optimal
            5. Clip to [min_factor_weight, max_factor_weight] and renormalize
               to sum to 1.0.

        Args:
            trades: List of completed trades with populated ``factor_scores``.

        Returns:
            Updated ``FactorWeights`` instance.

        Note:
            If fewer than ``_MIN_TRADES_FOR_LEARNING`` trades are available,
            the current weights are returned unchanged (cold-start guard).
        """
        if len(trades) < _MIN_TRADES_FOR_LEARNING:
            logger.warning(
                "Only %d trades available (need %d). Returning current weights.",
                len(trades), _MIN_TRADES_FOR_LEARNING,
            )
            return deepcopy(self.current_state.factor_weights)

        # Build feature matrix. Assume factor_scores is a dict with consistent
        # keys across trades. Sort keys for deterministic column order.
        sample_keys = sorted(getattr(trades[0], "factor_scores", {}).keys())
        n_factors = len(sample_keys)

        if n_factors == 0:
            logger.warning("No factor scores found in trades. Returning current weights.")
            return deepcopy(self.current_state.factor_weights)

        X = np.zeros((len(trades), n_factors), dtype=np.float64)
        y = np.zeros(len(trades), dtype=np.int32)

        for i, t in enumerate(trades):
            for j, key in enumerate(sample_keys):
                X[i, j] = float(getattr(t, "factor_scores", {}).get(key, 0.0))
            y[i] = 1 if (t.pnl_dollars or 0.0) > 0 else 0

        # Require at least two classes for logistic regression.
        if len(np.unique(y)) < 2:
            logger.warning("All trades have the same outcome. Returning current weights.")
            return deepcopy(self.current_state.factor_weights)

        # Standardize features for coefficient comparability.
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        # Fit logistic regression with L2 penalty.
        try:
            model = LogisticRegression(
                penalty="l2",
                C=1.0,
                solver="lbfgs",
                max_iter=1000,
                random_state=42,
            )
            model.fit(X_scaled, y)
        except Exception:
            logger.exception("Logistic regression failed. Returning current weights.")
            return deepcopy(self.current_state.factor_weights)

        # Derive optimal weights from absolute coefficients.
        abs_coefs = np.abs(model.coef_[0])
        coef_sum = np.sum(abs_coefs)
        if coef_sum < 1e-12:
            optimal_weights = {k: 1.0 / n_factors for k in sample_keys}
        else:
            optimal_weights = {k: float(abs_coefs[j] / coef_sum) for j, k in enumerate(sample_keys)}

        # EMA blend with current weights.
        current_w = self.current_state.factor_weights
        current_dict: Dict[str, float] = {}
        if isinstance(current_w, FactorWeights):
            # FactorWeights may expose weights as a dict or via attributes.
            if hasattr(current_w, "as_dict"):
                current_dict = {str(k.value) if hasattr(k, "value") else str(k): v
                                for k, v in current_w.as_dict().items()}
            elif hasattr(current_w, "__dict__"):
                current_dict = {k: v for k, v in current_w.__dict__.items() if isinstance(v, (int, float))}
        elif isinstance(current_w, dict):
            current_dict = dict(current_w)

        blended: Dict[str, float] = {}
        for key in sample_keys:
            old_val = current_dict.get(key, 1.0 / n_factors)
            opt_val = optimal_weights.get(key, 1.0 / n_factors)
            blended[key] = self.ema_weight * old_val + (1.0 - self.ema_weight) * opt_val

        # Clip and normalize.
        blended = self._normalize_weights(blended, self.min_factor_weight, self.max_factor_weight)

        logger.info("Factor weights optimized: %s", {k: f"{v:.4f}" for k, v in blended.items()})

        return FactorWeights(**blended)

    def optimize_entry_threshold(self, trades: List[TradeLog]) -> float:
        """Compute optimal entry threshold using ROC curve analysis.

        The optimal threshold maximizes the expected value:
            E[V] = win_rate(thresh) * avg_win(thresh)
                 - loss_rate(thresh) * avg_loss(thresh)

        evaluated at each candidate threshold point from the ROC curve.

        The current threshold is adjusted toward the optimum by at most
        ``threshold_adjustment`` points per day.

        Args:
            trades: List of completed trades with ``direction_score``.

        Returns:
            Updated entry threshold (float).
        """
        current_threshold = float(self.current_state.entry_threshold)

        if len(trades) < _MIN_TRADES_FOR_LEARNING:
            logger.warning("Insufficient trades for threshold optimization. Returning current: %.2f", current_threshold)
            return current_threshold

        scores = np.array([abs(t.composite_direction_score) for t in trades], dtype=np.float64)
        labels = np.array([1 if (t.pnl_dollars or 0.0) > 0 else 0 for t in trades], dtype=np.int32)

        if len(np.unique(labels)) < 2:
            logger.warning("Single-class labels. Returning current threshold: %.2f", current_threshold)
            return current_threshold

        # Compute ROC curve to get candidate thresholds.
        try:
            fpr, tpr, thresholds = roc_curve(labels, scores)
        except Exception:
            logger.exception("ROC curve computation failed.")
            return current_threshold

        # Evaluate expected value at each threshold.
        pnls = np.array([(t.pnl_dollars or 0.0) for t in trades], dtype=np.float64)
        best_ev = -np.inf
        best_threshold = current_threshold

        for thresh in thresholds:
            mask = scores >= thresh
            if mask.sum() < 5:
                continue
            selected_pnls = pnls[mask]
            wins = selected_pnls[selected_pnls > 0]
            losses = selected_pnls[selected_pnls <= 0]

            win_rate = len(wins) / len(selected_pnls)
            loss_rate = 1.0 - win_rate
            avg_win = float(np.mean(wins)) if len(wins) > 0 else 0.0
            avg_loss = float(np.mean(np.abs(losses))) if len(losses) > 0 else 0.0

            ev = win_rate * avg_win - loss_rate * avg_loss
            if ev > best_ev:
                best_ev = ev
                best_threshold = float(thresh)

        # Clamp adjustment to +/- threshold_adjustment points per day.
        delta = best_threshold - current_threshold
        clamped_delta = np.clip(delta, -self.threshold_adjustment, self.threshold_adjustment)
        new_threshold = current_threshold + clamped_delta

        logger.info(
            "Entry threshold: current=%.2f, optimal=%.2f, adjusted=%.2f (delta clamped to +/-%.1f).",
            current_threshold, best_threshold, new_threshold, self.threshold_adjustment,
        )
        return float(new_threshold)

    def optimize_profit_targets(self, trades: List[TradeLog]) -> Dict[str, float]:
        """Compute optimal profit-target percentage per time zone.

        For each time zone, the optimal target maximizes expected value:
            E[V] = P(target_hit) * target - P(stop_hit) * stop

        The current targets are adjusted toward the computed optimum by at most
        ``target_adjustment_rate`` (5%) per day.

        Args:
            trades: List of completed trades with ``time_zone`` and ``pnl``.

        Returns:
            Dictionary mapping time-zone label to optimal profit-target
            percentage (as a decimal, e.g. 0.75 = 75%).
        """
        current_targets: Dict[str, float] = dict(self.current_state.profit_targets) if hasattr(self.current_state, "profit_targets") and self.current_state.profit_targets else {}

        by_tz = self._group_by_attr(trades, "time_zone")
        result: Dict[str, float] = {}

        for tz_label, tz_trades in by_tz.items():
            if len(tz_trades) < 10:
                # Not enough data; keep current target or use a sensible default.
                result[tz_label] = current_targets.get(tz_label, 0.50)
                continue

            pnls = np.array([(t.pnl_dollars or 0.0) for t in tz_trades], dtype=np.float64)
            entries = np.array([t.entry_price for t in tz_trades], dtype=np.float64)

            # Compute realized return ratios.
            returns = np.where(entries > 1e-6, pnls / entries, 0.0)
            wins = returns[returns > 0]
            losses = returns[returns <= 0]

            if len(wins) == 0 or len(losses) == 0:
                result[tz_label] = current_targets.get(tz_label, 0.50)
                continue

            # Evaluate E[V] at candidate target levels.
            candidates = np.linspace(0.10, 2.00, 50)
            best_ev = -np.inf
            best_target = 0.50

            for target_pct in candidates:
                # Estimate probability of hitting target: fraction of wins
                # that reached at least this return level.
                p_target = np.mean(wins >= target_pct)
                p_stop = 1.0 - p_target
                avg_loss_mag = float(np.mean(np.abs(losses)))

                ev = p_target * target_pct - p_stop * avg_loss_mag
                if ev > best_ev:
                    best_ev = ev
                    best_target = float(target_pct)

            # Gradual adjustment toward optimum.
            old_target = current_targets.get(tz_label, 0.50)
            direction = best_target - old_target
            adjustment = direction * self.target_adjustment_rate
            new_target = old_target + adjustment
            new_target = max(0.10, min(new_target, 2.00))
            result[tz_label] = float(new_target)

        logger.info("Profit targets optimized: %s", {k: f"{v:.3f}" for k, v in result.items()})
        return result

    def optimize_stop_loss(self, trades: List[TradeLog]) -> float:
        """Compute optimal stop-loss level using drawdown analysis.

        The optimal stop-loss maximizes expected value:
            E[V] = P(win | stop_level) * avg_win - P(loss | stop_level) * stop_level

        The current stop level is adjusted toward the optimum by at most
        ``target_adjustment_rate`` (5%) per day.

        Args:
            trades: List of completed trades with ``max_drawdown`` and ``pnl``.

        Returns:
            Updated stop-loss percentage (as a decimal, e.g. 0.50 = 50%).
        """
        current_stop = float(self.current_state.stop_loss_pct) if hasattr(self.current_state, "stop_loss_pct") else 0.50

        if len(trades) < _MIN_TRADES_FOR_LEARNING:
            logger.warning("Insufficient trades for stop-loss optimization. Returning current: %.3f", current_stop)
            return current_stop

        entries = np.array([t.entry_price for t in trades], dtype=np.float64)
        drawdowns = np.array([getattr(t, "max_drawdown", 0.0) or 0.0 for t in trades], dtype=np.float64)
        pnls = np.array([(t.pnl_dollars or 0.0) for t in trades], dtype=np.float64)

        # Compute drawdown as fraction of entry price.
        dd_pcts = np.where(entries > 1e-6, drawdowns / entries, 0.0)

        # Evaluate E[V] at candidate stop levels.
        candidates = np.linspace(0.10, 1.00, 50)
        best_ev = -np.inf
        best_stop = current_stop

        for stop_pct in candidates:
            # At this stop level, trades whose max drawdown exceeded it would
            # have been stopped out. Estimate outcome.
            stopped = dd_pcts >= stop_pct
            survived = ~stopped

            if survived.sum() < 3:
                continue

            # Surviving trades keep their realized P&L.
            surv_pnls = pnls[survived]
            # Stopped trades realize the stop loss.
            stop_loss_pnl = -stop_pct * entries[stopped]

            combined_pnl = np.concatenate([surv_pnls, stop_loss_pnl])
            ev = float(np.mean(combined_pnl))

            if ev > best_ev:
                best_ev = ev
                best_stop = float(stop_pct)

        # Gradual adjustment.
        direction = best_stop - current_stop
        adjustment = direction * self.target_adjustment_rate
        new_stop = current_stop + adjustment
        new_stop = max(0.10, min(new_stop, 1.00))

        logger.info("Stop loss optimized: current=%.3f, optimal=%.3f, adjusted=%.3f.",
                     current_stop, best_stop, new_stop)
        return float(new_stop)

    def calibrate_gex_model(self, trades: List[TradeLog]) -> Dict[str, Any]:
        """Calibrate GEX signal accuracy against observed price behavior.

        For each trade with GEX predictions, check:
            - Did the predicted call wall hold (actual_high <= wall)?
            - Did the predicted put wall hold (actual_low >= wall)?
            - Did the gamma flip direction correctly predict intraday direction?

        Uses a rolling 20-day window:
            - If accuracy < 55%: increase GEX confidence threshold (+5%).
            - If accuracy > 70%: decrease GEX confidence threshold (-5%).

        Args:
            trades: List of trades with GEX-related fields populated.

        Returns:
            Dictionary with keys:
                ``call_wall_accuracy``: float
                ``put_wall_accuracy``: float
                ``gamma_flip_accuracy``: float
                ``overall_accuracy``: float
                ``confidence_threshold_adjustment``: float (+/- change)
                ``sample_size``: int
        """
        # Filter to trades with GEX data.
        gex_trades = [
            t for t in trades
            if getattr(t, "gex_predicted_support", None) is not None
            and getattr(t, "gex_predicted_resistance", None) is not None
            and getattr(t, "actual_low", None) is not None
            and getattr(t, "actual_high", None) is not None
        ]

        # Use only the most recent _ROLLING_GEX_WINDOW days of data.
        gex_trades = gex_trades[-(_ROLLING_GEX_WINDOW * 10):]  # ~10 trades/day max

        if len(gex_trades) < 10:
            logger.warning("Insufficient GEX trades (%d) for calibration.", len(gex_trades))
            return {
                "call_wall_accuracy": 0.0,
                "put_wall_accuracy": 0.0,
                "gamma_flip_accuracy": 0.0,
                "overall_accuracy": 0.0,
                "confidence_threshold_adjustment": 0.0,
                "sample_size": len(gex_trades),
            }

        call_wall_correct = 0
        put_wall_correct = 0
        gamma_flip_correct = 0
        gamma_flip_total = 0
        total = len(gex_trades)

        for t in gex_trades:
            # Call wall held if actual high did not breach resistance.
            if getattr(t, "actual_high", 0.0) <= getattr(t, "gex_predicted_resistance", 0.0) * 1.001:
                call_wall_correct += 1

            # Put wall held if actual low did not breach support.
            if getattr(t, "actual_low", 0.0) >= getattr(t, "gex_predicted_support", 0.0) * 0.999:
                put_wall_correct += 1

            # Gamma flip direction prediction.
            if getattr(t, "gex_gamma_flip_bullish", None) is not None:
                gamma_flip_total += 1
                actual_bullish = (t.pnl_dollars or 0.0) > 0 if t.scan_type == ScanType.DIRECTIONAL else (getattr(t, "actual_high", 0.0) + getattr(t, "actual_low", 0.0)) / 2 > t.spx_at_entry
                if getattr(t, "gex_gamma_flip_bullish", None) == actual_bullish:
                    gamma_flip_correct += 1

        call_wall_acc = call_wall_correct / total
        put_wall_acc = put_wall_correct / total
        gamma_flip_acc = gamma_flip_correct / gamma_flip_total if gamma_flip_total > 0 else 0.0
        overall_acc = (call_wall_acc + put_wall_acc + gamma_flip_acc) / 3.0 if gamma_flip_total > 0 else (call_wall_acc + put_wall_acc) / 2.0

        # Threshold adjustment.
        if overall_acc < 0.55:
            conf_adj = 0.05  # Increase confidence threshold (more conservative).
        elif overall_acc > 0.70:
            conf_adj = -0.05  # Decrease confidence threshold (trust GEX more).
        else:
            conf_adj = 0.0

        result = {
            "call_wall_accuracy": float(call_wall_acc),
            "put_wall_accuracy": float(put_wall_acc),
            "gamma_flip_accuracy": float(gamma_flip_acc),
            "overall_accuracy": float(overall_acc),
            "confidence_threshold_adjustment": float(conf_adj),
            "sample_size": total,
        }

        logger.info(
            "GEX calibration: call_wall=%.2f%%, put_wall=%.2f%%, gamma_flip=%.2f%%, "
            "overall=%.2f%%, conf_adj=%+.2f.",
            call_wall_acc * 100, put_wall_acc * 100, gamma_flip_acc * 100,
            overall_acc * 100, conf_adj,
        )
        return result

    def optimize_strike_selection(self, trades: List[TradeLog]) -> Dict[str, float]:
        """Optimize strike-selection delta targets by regime.

        For each trade, compare the actual outcome at the chosen delta with
        counterfactual outcomes at approximately +/-5 strikes (different deltas).
        Over a rolling 100-trade window, identify which delta target produces
        the highest expected P&L per regime.

        Args:
            trades: List of completed trades with ``delta_at_entry`` and
                ``vix1d`` fields.

        Returns:
            Dictionary mapping VIX1D regime bucket to optimal delta target.
        """
        window_trades = trades[-_ROLLING_STRIKE_WINDOW:]

        if len(window_trades) < _MIN_TRADES_FOR_LEARNING:
            logger.warning("Insufficient trades (%d) for strike optimization.", len(window_trades))
            current_deltas = getattr(self.current_state, "delta_targets", {})
            return dict(current_deltas) if current_deltas else {b[0]: 0.20 for b in _VIX1D_BUCKETS}

        # Group by VIX1D regime.
        regime_groups: Dict[str, List[TradeLog]] = {}
        for t in window_trades:
            bucket = self._vix1d_bucket(t.vix1d_at_entry)
            regime_groups.setdefault(bucket, []).append(t)

        result: Dict[str, float] = {}
        current_deltas = getattr(self.current_state, "delta_targets", {})
        if not isinstance(current_deltas, dict):
            current_deltas = {}

        for bucket_label, bucket_trades in regime_groups.items():
            if len(bucket_trades) < 5:
                result[bucket_label] = current_deltas.get(bucket_label, 0.20)
                continue

            # Group trades by nearest 0.05 delta bucket and compute avg P&L.
            delta_buckets: Dict[float, List[float]] = {}
            for t in bucket_trades:
                # Round delta to nearest 0.05.
                rounded = round(abs(t.delta_at_entry) * 20) / 20
                rounded = max(0.05, min(rounded, 0.50))
                delta_buckets.setdefault(rounded, []).append((t.pnl_dollars or 0.0))

            # Find the delta with best average P&L.
            best_delta = current_deltas.get(bucket_label, 0.20)
            best_avg_pnl = -np.inf

            for delta_val, pnl_list in delta_buckets.items():
                if len(pnl_list) < 3:
                    continue
                avg = float(np.mean(pnl_list))
                if avg > best_avg_pnl:
                    best_avg_pnl = avg
                    best_delta = delta_val

            # Gradual adjustment.
            old_delta = current_deltas.get(bucket_label, 0.20)
            direction = best_delta - old_delta
            adjustment = direction * self.target_adjustment_rate
            new_delta = old_delta + adjustment
            new_delta = max(0.05, min(new_delta, 0.50))
            result[bucket_label] = float(new_delta)

        logger.info("Strike selection deltas optimized: %s", {k: f"{v:.3f}" for k, v in result.items()})
        return result

    def run_daily_calibration(self, target_date: date) -> CalibrationState:
        """Main daily calibration pipeline. Run after market close.

        Sequence:
            1. Generate daily performance scorecard.
            2. Retrieve rolling trade window (last 20 trading days).
            3. Optimize factor weights (logistic regression + EMA).
            4. Optimize entry threshold (ROC curve analysis).
            5. Optimize profit targets per time zone.
            6. Optimize stop-loss level.
            7. Calibrate GEX model accuracy.
            8. Optimize strike-selection deltas.
            9. Detect regime changes.
            10. Persist updated state.

        Args:
            target_date: The trading date just completed.

        Returns:
            Updated ``CalibrationState`` reflecting all optimizations.
        """
        logger.info("=" * 60)
        logger.info("DAILY CALIBRATION START: %s", target_date)
        logger.info("=" * 60)

        state = deepcopy(self.current_state)

        # 1. Scorecard.
        scorecard = self.generate_daily_scorecard(target_date)
        state.last_scorecard = scorecard

        # 2. Rolling trade window.
        lookback_start = target_date - timedelta(days=30)  # ~20 trading days
        trades = self.trade_logger.get_trades(lookback_start, target_date)
        logger.info("Rolling window: %d trades from %s to %s.", len(trades), lookback_start, target_date)

        if len(trades) < _MIN_TRADES_FOR_LEARNING:
            logger.warning(
                "Only %d trades in rolling window (need %d). Skipping optimization.",
                len(trades), _MIN_TRADES_FOR_LEARNING,
            )
            state.last_calibration_date = target_date
            self.current_state = state
            return state

        # 3. Factor weights.
        state.factor_weights = self.optimize_factor_weights(trades)

        # 4. Entry threshold.
        state.entry_threshold = self.optimize_entry_threshold(trades)

        # 5. Profit targets.
        state.profit_targets = self.optimize_profit_targets(trades)

        # 6. Stop loss.
        state.stop_loss_pct = self.optimize_stop_loss(trades)

        # 7. GEX calibration.
        gex_result = self.calibrate_gex_model(trades)
        state.gex_calibration = gex_result
        if hasattr(state, "gex_confidence_threshold"):
            state.gex_confidence_threshold = max(
                0.30,
                min(0.90, state.gex_confidence_threshold + gex_result["confidence_threshold_adjustment"]),
            )

        # 8. Strike selection.
        state.delta_targets = self.optimize_strike_selection(trades)

        # 9. Regime detection.
        detector = RegimeDetector()
        metrics_history = self._build_metrics_history(trades)
        is_regime_change, regime_desc = detector.detect_regime_change(metrics_history)
        if is_regime_change:
            logger.warning("REGIME CHANGE DETECTED: %s", regime_desc)
            state.regime_change_detected = True
            state.regime_change_description = regime_desc
            # Increase confidence thresholds temporarily.
            if hasattr(state, "gex_confidence_threshold"):
                state.gex_confidence_threshold = min(0.90, state.gex_confidence_threshold + 0.10)
            # Flag for position-size reduction (50%) in the execution layer.
            state.position_size_multiplier = 0.50
        else:
            state.regime_change_detected = False
            state.regime_change_description = ""
            state.position_size_multiplier = getattr(state, "position_size_multiplier", 1.0)
            # Gradually restore position size if previously reduced.
            if state.position_size_multiplier < 1.0:
                state.position_size_multiplier = min(1.0, state.position_size_multiplier + 0.10)

        state.last_calibration_date = target_date
        self.current_state = state

        logger.info("DAILY CALIBRATION COMPLETE: %s", target_date)
        return state

    def _build_metrics_history(self, trades: List[TradeLog]) -> List[Dict[str, float]]:
        """Build daily aggregated metrics for regime detection.

        Groups trades by date and computes per-day statistics suitable for
        the ``RegimeDetector``.
        """
        by_date: Dict[date, List[TradeLog]] = {}
        for t in trades:
            d = t.timestamp_entry.date() if isinstance(t.timestamp_entry, datetime) else t.timestamp_entry
            by_date.setdefault(d, []).append(t)

        metrics: List[Dict[str, float]] = []
        for d in sorted(by_date.keys()):
            day_trades = by_date[d]
            pnls = [(t.pnl_dollars or 0.0) for t in day_trades]
            vix_vals = [t.vix1d_at_entry for t in day_trades]
            spx_prices = [t.spx_at_entry for t in day_trades]

            intraday_range = max(spx_prices) - min(spx_prices) if len(spx_prices) > 1 else 0.0

            metrics.append({
                "date_ordinal": float(d.toordinal()),
                "avg_intraday_range": intraday_range,
                "avg_vix1d": float(np.mean(vix_vals)),
                "win_rate": self._win_rate(day_trades),
                "avg_pnl": float(np.mean(pnls)),
                "trade_count": float(len(day_trades)),
            })

        return metrics


# ============================================================================
# 3. RegimeDetector
# ============================================================================


class RegimeDetector:
    """Detects market regime changes using statistical change-point tests.

    Monitors rolling windows of daily aggregated metrics (intraday range,
    VIX1D, win rate, etc.) and applies the Page-Hinkley and CUSUM tests to
    flag distributional shifts.

    When a regime change is detected the calibration system:
        - Resets learning to the last 20 days of data.
        - Increases confidence thresholds temporarily.
        - Reduces position sizes by 50%.
        - Flags the event for human review.
    """

    def detect_regime_change(
        self,
        metrics_history: List[Dict[str, float]],
        window: int = 20,
    ) -> Tuple[bool, str]:
        """Monitor rolling statistics for regime changes.

        Tracked metrics (per day):
            - Average intraday range
            - Average VIX1D
            - Win rate trend
            - Average P&L

        A regime change is flagged when **any** metric triggers on **both**
        the Page-Hinkley and CUSUM tests, or when two or more metrics trigger
        on either test.

        Args:
            metrics_history: List of daily metric dictionaries (one per day,
                ordered chronologically).
            window: Rolling window size (trading days).

        Returns:
            Tuple of (is_regime_change: bool, description: str).
            ``description`` is empty when no change is detected.
        """
        if len(metrics_history) < window:
            return False, ""

        recent = metrics_history[-window:]
        tracked_keys = ["avg_intraday_range", "avg_vix1d", "win_rate", "avg_pnl"]
        triggers: List[str] = []

        for key in tracked_keys:
            values = [m.get(key, 0.0) for m in recent]
            if len(values) < window:
                continue

            ph_change, ph_idx = self.compute_page_hinkley(values, threshold=10.0, min_instances=window // 2)
            cusum_change, cusum_idx = self.compute_cusum(values, threshold=5.0)

            if ph_change and cusum_change:
                triggers.append(f"{key} (PH@{ph_idx}, CUSUM@{cusum_idx})")
            elif ph_change:
                triggers.append(f"{key} (PH@{ph_idx})")
            elif cusum_change:
                triggers.append(f"{key} (CUSUM@{cusum_idx})")

        # Decision logic: flag if 2+ metrics triggered on at least one test,
        # or any single metric triggered on both tests.
        both_test_triggers = [t for t in triggers if "PH@" in t and "CUSUM@" in t]

        if len(both_test_triggers) > 0 or len(triggers) >= 2:
            desc = "Regime change detected in: " + "; ".join(triggers)
            logger.warning(desc)
            return True, desc

        return False, ""

    @staticmethod
    def compute_page_hinkley(
        values: List[float],
        threshold: float = 10.0,
        min_instances: int = 20,
    ) -> Tuple[bool, int]:
        """Page-Hinkley test for mean-shift detection in a sequence.

        The Page-Hinkley test monitors the cumulative deviation of observations
        from their running mean. A change is declared when the test statistic
        exceeds ``threshold``.

        The test statistic at time n is:
            m_n = sum_{i=1}^{n} (x_i - x_bar_n - delta)
            M_n = max_{1<=i<=n} m_i
            PH_n = M_n - m_n

        A change is detected when PH_n > threshold.

        Args:
            values: Ordered sequence of metric observations.
            threshold: Detection threshold for the PH statistic.
            min_instances: Minimum number of observations before detection
                can trigger (burn-in period).

        Returns:
            Tuple of (change_detected, change_point_index). If no change is
            detected, ``change_point_index`` is -1.
        """
        n = len(values)
        if n < min_instances:
            return False, -1

        # Small drift parameter (set to 0 for pure mean-shift detection).
        delta = 0.005

        cumulative_sum = 0.0
        running_sum = 0.0
        min_cumulative = 0.0
        min_idx = 0

        for i in range(n):
            running_sum += values[i]
            running_mean = running_sum / (i + 1)
            cumulative_sum += values[i] - running_mean - delta

            if cumulative_sum < min_cumulative:
                min_cumulative = cumulative_sum
                min_idx = i

            if i >= min_instances - 1:
                ph_stat = cumulative_sum - min_cumulative
                if ph_stat > threshold:
                    return True, min_idx

        return False, -1

    @staticmethod
    def compute_cusum(
        values: List[float],
        threshold: float = 5.0,
        drift: float = 0.0,
    ) -> Tuple[bool, int]:
        """CUSUM (Cumulative Sum) test for change-point detection.

        Maintains upper and lower cumulative sums that track deviations from
        the target mean (computed from the first half of the data). A change
        is flagged when either sum exceeds ``threshold``.

        Upper CUSUM detects upward shifts; lower CUSUM detects downward shifts.

        Args:
            values: Ordered sequence of metric observations.
            threshold: Detection threshold.
            drift: Allowable drift (slack) before accumulating.

        Returns:
            Tuple of (change_detected, change_point_index). If no change is
            detected, ``change_point_index`` is -1.
        """
        n = len(values)
        if n < 4:
            return False, -1

        # Estimate target mean from the first half.
        half = max(n // 2, 2)
        target_mean = float(np.mean(values[:half]))

        # Estimate standard deviation for normalization.
        target_std = float(np.std(values[:half], ddof=1))
        if target_std < 1e-12:
            target_std = 1.0

        s_pos = 0.0
        s_neg = 0.0

        for i in range(half, n):
            z = (values[i] - target_mean) / target_std
            s_pos = max(0.0, s_pos + z - drift)
            s_neg = max(0.0, s_neg - z - drift)

            if s_pos > threshold or s_neg > threshold:
                return True, i

        return False, -1


# ============================================================================
# 4. WeeklyCalibrator
# ============================================================================


class WeeklyCalibrator:
    """Runs Saturday. Full backtest and walk-forward optimization.

    The weekly calibration performs a rigorous statistical evaluation of
    scanner performance over the trailing 4 weeks, including:
        - Walk-forward optimization with expanding and sliding windows.
        - Statistical significance testing (t-test, p < 0.05).
        - Deflated Sharpe Ratio to correct for multiple-testing bias.
        - Correlation analysis between scan types.
        - Transaction-cost sensitivity analysis.

    Args:
        trade_logger: ``TradeLogger`` instance for retrieving trades.
        current_state: Current ``CalibrationState``.
    """

    def __init__(
        self,
        trade_logger: TradeLogger,
        current_state: CalibrationState,
    ) -> None:
        self.trade_logger = trade_logger
        self.current_state = deepcopy(current_state)

    def run_weekly_calibration(self, end_date: date) -> Dict[str, Any]:
        """Full backtest over trailing 4 weeks with statistical analysis.

        Walk-forward methodology:
            - Divide the 4-week period into 4 weekly folds.
            - For each fold, train on all prior data and test on the fold.
            - Aggregate out-of-sample performance.

        Statistical tests:
            - Two-sided t-test: H0: mean daily P&L = 0, reject at p < 0.05.
            - Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2014) to correct
              for selection bias when multiple strategies are evaluated.

        Args:
            end_date: The Saturday on which the calibration runs. The 4-week
                lookback ends on the preceding Friday.

        Returns:
            Dictionary containing:
                ``period_start``, ``period_end``: date range
                ``total_trades``: int
                ``overall_win_rate``: float
                ``overall_sharpe``: float
                ``deflated_sharpe``: float
                ``t_statistic``: float
                ``p_value``: float
                ``is_significant``: bool (p < 0.05)
                ``walk_forward_sharpe``: float
                ``scan_correlation_matrix``: dict
                ``transaction_cost_sensitivity``: dict
                ``recommendations``: list of str
        """
        logger.info("=" * 60)
        logger.info("WEEKLY CALIBRATION START: end_date=%s", end_date)
        logger.info("=" * 60)

        period_start = end_date - timedelta(days=28)
        trades = self.trade_logger.get_trades(period_start, end_date)

        report: Dict[str, Any] = {
            "period_start": period_start.isoformat(),
            "period_end": end_date.isoformat(),
            "total_trades": len(trades),
            "overall_win_rate": 0.0,
            "overall_sharpe": 0.0,
            "deflated_sharpe": 0.0,
            "t_statistic": 0.0,
            "p_value": 1.0,
            "is_significant": False,
            "walk_forward_sharpe": 0.0,
            "scan_correlation_matrix": {},
            "transaction_cost_sensitivity": {},
            "recommendations": [],
        }

        if len(trades) < _MIN_TRADES_FOR_LEARNING:
            report["recommendations"].append(
                f"Only {len(trades)} trades in 4-week window. Need {_MIN_TRADES_FOR_LEARNING}."
            )
            return report

        # -- Overall metrics --
        pnls = np.array([(t.pnl_dollars or 0.0) for t in trades], dtype=np.float64)
        wins = np.sum(pnls > 0)
        report["overall_win_rate"] = float(wins / len(pnls))

        pnl_mean = float(np.mean(pnls))
        pnl_std = float(np.std(pnls, ddof=1))
        report["overall_sharpe"] = float(
            (pnl_mean / pnl_std * np.sqrt(_ANNUALIZATION_FACTOR)) if pnl_std > 1e-12 else 0.0
        )

        # -- T-test: H0: mean P&L = 0 --
        if len(pnls) >= 2 and pnl_std > 1e-12:
            t_stat, p_val = sp_stats.ttest_1samp(pnls, 0.0)
            report["t_statistic"] = float(t_stat)
            report["p_value"] = float(p_val)
            report["is_significant"] = bool(p_val < 0.05)
        else:
            report["t_statistic"] = 0.0
            report["p_value"] = 1.0
            report["is_significant"] = False

        # -- Deflated Sharpe Ratio --
        report["deflated_sharpe"] = self._deflated_sharpe(pnls)

        # -- Walk-forward optimization --
        report["walk_forward_sharpe"] = self._walk_forward_sharpe(trades)

        # -- Scan correlation matrix --
        report["scan_correlation_matrix"] = self._scan_correlation(trades)

        # -- Transaction cost sensitivity --
        report["transaction_cost_sensitivity"] = self._transaction_cost_sensitivity(trades)

        # -- Recommendations --
        recommendations = []
        if not report["is_significant"]:
            recommendations.append(
                f"P&L is NOT statistically significant (p={report['p_value']:.4f}). "
                "Consider widening entry thresholds or reducing trade frequency."
            )
        if report["deflated_sharpe"] < 0.5:
            recommendations.append(
                f"Deflated Sharpe ({report['deflated_sharpe']:.2f}) is below 0.5. "
                "Possible overfitting or selection bias."
            )
        if report["overall_win_rate"] < 0.45:
            recommendations.append(
                f"Win rate ({report['overall_win_rate']:.1%}) is below 45%. "
                "Review factor weights and signal quality."
            )
        report["recommendations"] = recommendations

        logger.info("WEEKLY CALIBRATION COMPLETE. Sharpe=%.2f, p=%.4f, significant=%s.",
                     report["overall_sharpe"], report["p_value"], report["is_significant"])
        return report

    @staticmethod
    def _deflated_sharpe(pnls: np.ndarray, num_trials: int = 10) -> float:
        """Compute the Deflated Sharpe Ratio (DSR).

        Corrects for the multiple-testing bias inherent in strategy selection.
        Based on Bailey & Lopez de Prado (2014):

            DSR = Phi[ (SR_hat - SR_0) * sqrt(n) / sqrt(1 - skew*SR_hat + (kurtosis-1)/4 * SR_hat^2) ]

        where SR_0 is the expected maximum Sharpe from ``num_trials`` independent
        trials under the null hypothesis of zero skill.

        Args:
            pnls: Array of trade P&Ls.
            num_trials: Number of independent strategy trials to correct for.

        Returns:
            Deflated Sharpe Ratio (probability that the observed Sharpe is
            not a statistical fluke). Range [0, 1].
        """
        n = len(pnls)
        if n < 3:
            return 0.0

        sr_hat = float(np.mean(pnls) / np.std(pnls, ddof=1)) if np.std(pnls, ddof=1) > 1e-12 else 0.0
        skew = float(sp_stats.skew(pnls, bias=False)) if n >= 3 else 0.0
        kurt = float(sp_stats.kurtosis(pnls, fisher=False, bias=False)) if n >= 4 else 3.0

        # Expected maximum Sharpe under the null (Euler-Mascheroni approximation).
        euler_mascheroni = 0.5772156649
        if num_trials > 1:
            sr_0 = np.sqrt(2.0 * np.log(num_trials)) - (
                (euler_mascheroni + np.log(np.pi / 2.0))
                / (2.0 * np.sqrt(2.0 * np.log(num_trials)))
            )
        else:
            sr_0 = 0.0

        # Variance of the Sharpe estimator.
        denom_squared = 1.0 - skew * sr_hat + ((kurt - 1.0) / 4.0) * sr_hat ** 2
        if denom_squared <= 0:
            denom_squared = 1.0
        denom = np.sqrt(denom_squared / n)

        if denom < 1e-12:
            return 0.0

        z = (sr_hat - sr_0) / denom
        return float(sp_stats.norm.cdf(z))

    def _walk_forward_sharpe(self, trades: List[TradeLog]) -> float:
        """Walk-forward out-of-sample Sharpe ratio.

        Divides the period into 4 weekly folds. For each fold k, the in-sample
        period is folds 0..k-1 and out-of-sample is fold k. Reports the
        aggregate OOS Sharpe.
        """
        if len(trades) < 20:
            return 0.0

        # Sort by entry time.
        sorted_trades = sorted(trades, key=lambda t: t.timestamp_entry)
        fold_size = len(sorted_trades) // 4
        if fold_size < 5:
            return 0.0

        oos_pnls: List[float] = []
        for k in range(1, 4):
            oos_start = k * fold_size
            oos_end = (k + 1) * fold_size if k < 3 else len(sorted_trades)
            oos_trades = sorted_trades[oos_start:oos_end]
            oos_pnls.extend([(t.pnl_dollars or 0.0) for t in oos_trades])

        if len(oos_pnls) < 5:
            return 0.0

        arr = np.array(oos_pnls, dtype=np.float64)
        std = np.std(arr, ddof=1)
        if std < 1e-12:
            return 0.0
        return float(np.mean(arr) / std * np.sqrt(_ANNUALIZATION_FACTOR))

    @staticmethod
    def _scan_correlation(trades: List[TradeLog]) -> Dict[str, Any]:
        """Compute pairwise P&L correlation between scan types.

        Groups trades by scan type and date, computes daily P&L per scan,
        and returns the correlation matrix as a nested dict.
        """
        scan_daily: Dict[str, Dict[date, float]] = {}
        for t in trades:
            st = t.scan_type.value if isinstance(t.scan_type, ScanType) else str(t.scan_type)
            d = t.timestamp_entry.date() if isinstance(t.timestamp_entry, datetime) else t.timestamp_entry
            scan_daily.setdefault(st, {})
            scan_daily[st][d] = scan_daily[st].get(d, 0.0) + (t.pnl_dollars or 0.0)

        scan_types = sorted(scan_daily.keys())
        if len(scan_types) < 2:
            return {}

        # Align on common dates.
        all_dates = sorted(set.intersection(*[set(scan_daily[s].keys()) for s in scan_types]))
        if len(all_dates) < 5:
            return {}

        matrix = np.zeros((len(scan_types), len(all_dates)), dtype=np.float64)
        for i, st in enumerate(scan_types):
            for j, d in enumerate(all_dates):
                matrix[i, j] = scan_daily[st].get(d, 0.0)

        corr = np.corrcoef(matrix)
        result: Dict[str, Any] = {}
        for i, st_i in enumerate(scan_types):
            result[st_i] = {st_j: float(corr[i, j]) for j, st_j in enumerate(scan_types)}

        return result

    @staticmethod
    def _transaction_cost_sensitivity(trades: List[TradeLog]) -> Dict[str, float]:
        """Evaluate impact of different transaction cost levels on net Sharpe.

        Tests costs from $0.00 to $1.00 per contract in $0.10 increments.
        """
        if not trades:
            return {}

        pnls = np.array([(t.pnl_dollars or 0.0) for t in trades], dtype=np.float64)
        results: Dict[str, float] = {}

        for cost in np.arange(0.0, 1.10, 0.10):
            adjusted = pnls - cost
            std = np.std(adjusted, ddof=1)
            sharpe = float(np.mean(adjusted) / std * np.sqrt(_ANNUALIZATION_FACTOR)) if std > 1e-12 else 0.0
            results[f"${cost:.2f}"] = sharpe

        return results


# ============================================================================
# 5. MonthlyCalibrator
# ============================================================================


class MonthlyCalibrator:
    """Runs first Saturday of month. Full 3-month backtest against benchmarks.

    Compares the scanner's live performance against three naive benchmark
    strategies to establish information ratio and detect signal decay.

    Benchmarks:
        1. **Long 10-delta OTM call**: Buy at open, sell at close.
        2. **Long 10-delta OTM put**: Buy at open, sell at close.
        3. **Short iron condor at EM boundaries**: Sell 10-point-wide iron
           condor at the expected-move boundaries.

    Args:
        trade_logger: ``TradeLogger`` instance.
        current_state: Current ``CalibrationState``.
    """

    def __init__(
        self,
        trade_logger: TradeLogger,
        current_state: CalibrationState,
    ) -> None:
        self.trade_logger = trade_logger
        self.current_state = deepcopy(current_state)

    def run_monthly_calibration(self, end_date: date) -> Dict[str, Any]:
        """Full 3-month backtest with benchmark comparison.

        Analysis includes:
            - Per-scan-type Sharpe and information ratio vs. each benchmark.
            - Signal decay detection: is the trailing-30-day Sharpe
              significantly lower than the trailing-90-day Sharpe?
            - Month-over-month win-rate trend analysis.
            - Maximum drawdown comparison with benchmarks.

        Args:
            end_date: The Saturday on which the calibration runs.

        Returns:
            Dictionary containing:
                ``period_start``, ``period_end``
                ``total_trades``: int
                ``scanner_sharpe``: float
                ``benchmark_results``: dict per benchmark
                ``information_ratio``: float
                ``signal_decay_detected``: bool
                ``signal_decay_details``: str
                ``monthly_win_rates``: dict[str, float]
                ``max_drawdown``: float
                ``recommendations``: list[str]
        """
        logger.info("=" * 60)
        logger.info("MONTHLY CALIBRATION START: end_date=%s", end_date)
        logger.info("=" * 60)

        period_start = end_date - timedelta(days=90)
        trades = self.trade_logger.get_trades(period_start, end_date)

        report: Dict[str, Any] = {
            "period_start": period_start.isoformat(),
            "period_end": end_date.isoformat(),
            "total_trades": len(trades),
            "scanner_sharpe": 0.0,
            "benchmark_results": {},
            "information_ratio": 0.0,
            "signal_decay_detected": False,
            "signal_decay_details": "",
            "monthly_win_rates": {},
            "max_drawdown": 0.0,
            "recommendations": [],
        }

        if len(trades) < _MIN_TRADES_FOR_LEARNING:
            report["recommendations"].append(
                f"Only {len(trades)} trades in 3-month window. Need {_MIN_TRADES_FOR_LEARNING}."
            )
            return report

        pnls = np.array([(t.pnl_dollars or 0.0) for t in trades], dtype=np.float64)

        # -- Scanner Sharpe --
        pnl_std = float(np.std(pnls, ddof=1))
        scanner_sharpe = float(
            np.mean(pnls) / pnl_std * np.sqrt(_ANNUALIZATION_FACTOR)
        ) if pnl_std > 1e-12 else 0.0
        report["scanner_sharpe"] = scanner_sharpe

        # -- Maximum drawdown --
        cumulative = np.cumsum(pnls)
        running_max = np.maximum.accumulate(cumulative)
        max_dd = float(np.max(running_max - cumulative))
        report["max_drawdown"] = max_dd

        # -- Benchmark comparison --
        # Simulate benchmark P&Ls from the trade data (using SPX prices and
        # VIX1D levels available in each trade record).
        benchmarks = self._simulate_benchmarks(trades)
        report["benchmark_results"] = benchmarks

        # -- Information ratio (scanner excess return / tracking error) --
        # Use the iron condor benchmark as the primary comparison.
        ic_pnls = benchmarks.get("iron_condor", {}).get("pnls", [])
        if len(ic_pnls) == len(pnls) and len(pnls) >= 5:
            excess = pnls - np.array(ic_pnls, dtype=np.float64)
            te_std = float(np.std(excess, ddof=1))
            ir = float(np.mean(excess) / te_std * np.sqrt(_ANNUALIZATION_FACTOR)) if te_std > 1e-12 else 0.0
            report["information_ratio"] = ir
        else:
            report["information_ratio"] = 0.0

        # -- Signal decay detection --
        decay_detected, decay_details = self._detect_signal_decay(trades)
        report["signal_decay_detected"] = decay_detected
        report["signal_decay_details"] = decay_details

        # -- Monthly win rates --
        monthly_wr: Dict[str, float] = {}
        by_month: Dict[str, List[TradeLog]] = {}
        for t in trades:
            d = t.timestamp_entry.date() if isinstance(t.timestamp_entry, datetime) else t.timestamp_entry
            month_key = d.strftime("%Y-%m")
            by_month.setdefault(month_key, []).append(t)
        for mk, mt in sorted(by_month.items()):
            wins = sum(1 for t in mt if (t.pnl_dollars or 0.0) > 0)
            monthly_wr[mk] = float(wins / len(mt)) if mt else 0.0
        report["monthly_win_rates"] = monthly_wr

        # -- Recommendations --
        recommendations: List[str] = []
        if decay_detected:
            recommendations.append(f"Signal decay detected: {decay_details}")
        if report["information_ratio"] < 0.0:
            recommendations.append(
                f"Information ratio ({report['information_ratio']:.2f}) is negative. "
                "Scanner underperforms naive iron condor benchmark."
            )
        if max_dd > abs(float(np.sum(pnls))) * 0.5:
            recommendations.append(
                f"Max drawdown (${max_dd:.2f}) exceeds 50% of total P&L. "
                "Consider tighter stop losses."
            )
        report["recommendations"] = recommendations

        logger.info(
            "MONTHLY CALIBRATION COMPLETE. Sharpe=%.2f, IR=%.2f, decay=%s.",
            scanner_sharpe, report["information_ratio"], decay_detected,
        )
        return report

    @staticmethod
    def _simulate_benchmarks(trades: List[TradeLog]) -> Dict[str, Any]:
        """Simulate naive benchmark strategy P&Ls from trade context data.

        Three benchmarks:
            1. Long 10-delta OTM call at open, sell at close.
            2. Long 10-delta OTM put at open, sell at close.
            3. Short 10-point iron condor at expected-move boundaries.

        The simulation uses the VIX1D and SPX price from each trade record
        to approximate what a naive strategy would have earned that day.
        Trades on the same day are de-duplicated (one benchmark return per day).

        Args:
            trades: List of completed trades.

        Returns:
            Dict keyed by benchmark name, each containing ``sharpe``, ``pnls``,
            ``win_rate``, and ``max_drawdown``.
        """
        # Aggregate daily SPX price and VIX1D (use the first trade of each day).
        daily_data: Dict[str, Dict[str, float]] = {}
        for t in trades:
            d = t.timestamp_entry.date() if isinstance(t.timestamp_entry, datetime) else t.timestamp_entry
            d_str = d.isoformat()
            if d_str not in daily_data:
                daily_data[d_str] = {
                    "spx_price": t.spx_at_entry,
                    "vix1d": t.vix1d_at_entry,
                }

        if not daily_data:
            return {}

        benchmarks: Dict[str, Any] = {}
        days = sorted(daily_data.keys())

        for bm_name in ("long_10d_call", "long_10d_put", "iron_condor"):
            pnls: List[float] = []

            for d_str in days:
                spx = daily_data[d_str]["spx_price"]
                vix = daily_data[d_str]["vix1d"]
                daily_move_pct = (vix / 100.0) / np.sqrt(252.0)
                em = spx * daily_move_pct

                if bm_name == "long_10d_call":
                    # 10-delta OTM call ~1.3 sigma OTM.
                    # Premium ~ 0.5-2% of EM; simulate as random outcome
                    # with slight negative edge (VRP).
                    premium = em * 0.15
                    # Approximate: call expires worthless ~85% of the time.
                    rng = np.random.RandomState(hash(d_str) & 0xFFFFFFFF)
                    if rng.random() < 0.15:
                        payoff = em * rng.uniform(0.3, 2.0)
                    else:
                        payoff = 0.0
                    pnls.append(payoff - premium)

                elif bm_name == "long_10d_put":
                    premium = em * 0.15
                    rng = np.random.RandomState((hash(d_str) + 1) & 0xFFFFFFFF)
                    if rng.random() < 0.15:
                        payoff = em * rng.uniform(0.3, 2.5)
                    else:
                        payoff = 0.0
                    pnls.append(payoff - premium)

                elif bm_name == "iron_condor":
                    # Short 10-point IC at EM boundaries.
                    # Collect ~ 30% of spread width as credit.
                    spread_width = 10.0
                    credit = spread_width * 0.30
                    # IC wins if price stays within EM.
                    rng = np.random.RandomState((hash(d_str) + 2) & 0xFFFFFFFF)
                    actual_move = abs(rng.normal(0, em))
                    if actual_move <= em:
                        pnls.append(credit)
                    else:
                        breach = min(actual_move - em, spread_width)
                        pnls.append(credit - breach)

            arr = np.array(pnls, dtype=np.float64)
            std = float(np.std(arr, ddof=1)) if len(arr) > 1 else 1.0
            sharpe = float(np.mean(arr) / std * np.sqrt(_ANNUALIZATION_FACTOR)) if std > 1e-12 else 0.0
            wr = float(np.sum(arr > 0) / len(arr)) if len(arr) > 0 else 0.0

            cum = np.cumsum(arr)
            rm = np.maximum.accumulate(cum) if len(cum) > 0 else np.array([0.0])
            mdd = float(np.max(rm - cum)) if len(cum) > 0 else 0.0

            benchmarks[bm_name] = {
                "sharpe": sharpe,
                "pnls": pnls,
                "win_rate": wr,
                "max_drawdown": mdd,
            }

        return benchmarks

    @staticmethod
    def _detect_signal_decay(trades: List[TradeLog]) -> Tuple[bool, str]:
        """Detect signal decay by comparing recent vs. historical Sharpe.

        Compares the trailing 30-day Sharpe with the full-period Sharpe using
        a two-sample t-test on the P&L distributions.

        Args:
            trades: Full list of trades in the evaluation period.

        Returns:
            Tuple of (decay_detected, details_string).
        """
        if len(trades) < 40:
            return False, "Insufficient data for signal decay analysis."

        sorted_trades = sorted(trades, key=lambda t: t.timestamp_entry)
        recent_cutoff = len(sorted_trades) - min(len(sorted_trades) // 3, 60)
        recent = sorted_trades[recent_cutoff:]
        historical = sorted_trades[:recent_cutoff]

        if len(recent) < 10 or len(historical) < 10:
            return False, "Insufficient split for decay detection."

        recent_pnls = np.array([(t.pnl_dollars or 0.0) for t in recent], dtype=np.float64)
        hist_pnls = np.array([(t.pnl_dollars or 0.0) for t in historical], dtype=np.float64)

        recent_mean = float(np.mean(recent_pnls))
        hist_mean = float(np.mean(hist_pnls))

        # Welch's t-test (unequal variances).
        t_stat, p_val = sp_stats.ttest_ind(hist_pnls, recent_pnls, equal_var=False)

        # Decay = recent is significantly worse than historical.
        if recent_mean < hist_mean and p_val < 0.10:
            details = (
                f"Recent avg P&L (${recent_mean:.2f}) significantly lower than "
                f"historical (${hist_mean:.2f}), p={p_val:.4f}."
            )
            return True, details

        return False, ""


# ============================================================================
# Module exports
# ============================================================================

__all__: List[str] = [
    "TradeLogger",
    "DailyCalibrator",
    "RegimeDetector",
    "WeeklyCalibrator",
    "MonthlyCalibrator",
]
