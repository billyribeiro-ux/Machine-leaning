"""
SCANIFY SPX 0DTE Options Day Trading Scanner + GEX Scanner -- Persistence Layer

Production-grade SQLite persistence for scanner state, trades, calibration data,
GEX snapshots, signals, and daily performance metrics.  Provides local storage
with optional export to CSV/Parquet and schema migration support.

Tables
------
trades              Complete trade log (flat projection of TradeLog)
sessions            Daily pre-market session setup (JSON-serialised)
gex_snapshots       Per-minute GEX profile snapshots (JSON-serialised)
signals             All generated scan signals with optional outcomes
calibration_state   Current and historical calibration parameters
factor_weights      Historical factor weight evolution
daily_metrics       Aggregated daily performance metrics
regime_history      Regime classification history
alerts              Alert history

All timestamps are stored as ISO-8601 strings; dates as ``YYYY-MM-DD``.
Complex nested Pydantic models are stored as JSON text columns.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Generator, Optional

from .models import (
    CalibrationState,
    FactorWeights,
    GEXProfile,
    ScanSignal,
    SessionSetup,
    StrikeGEX,
    TradeLog,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema version -- bump when adding migrations
# ---------------------------------------------------------------------------
CURRENT_SCHEMA_VERSION: int = 1

# ---------------------------------------------------------------------------
# SQL DDL
# ---------------------------------------------------------------------------

_TRADES_DDL = """
CREATE TABLE IF NOT EXISTS trades (
    id                        INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id                  TEXT    NOT NULL UNIQUE,
    timestamp_entry           TEXT    NOT NULL,
    timestamp_exit            TEXT,
    scan_type                 TEXT    NOT NULL,
    direction                 TEXT    NOT NULL,
    strike                    REAL    NOT NULL,
    option_type               TEXT    NOT NULL,
    entry_price               REAL    NOT NULL,
    exit_price                REAL,
    max_gain_during_trade     REAL    NOT NULL DEFAULT 0.0,
    max_loss_during_trade     REAL    NOT NULL DEFAULT 0.0,
    pnl_dollars               REAL,
    pnl_percent               REAL,
    hold_time_minutes         REAL,
    spx_at_entry              REAL    NOT NULL,
    vix1d_at_entry            REAL    NOT NULL,
    vix_at_entry              REAL    NOT NULL,
    expected_move_1sigma      REAL    NOT NULL,
    composite_direction_score REAL    NOT NULL,
    session_type              TEXT    NOT NULL,
    net_gex_at_entry          REAL    NOT NULL,
    gamma_flip_at_entry       REAL    NOT NULL,
    time_zone                 TEXT    NOT NULL,
    delta_at_entry            REAL    NOT NULL,
    gamma_at_entry            REAL    NOT NULL,
    theta_at_entry            REAL    NOT NULL,
    iv_at_entry               REAL    NOT NULL,
    tick_10min_avg            REAL    NOT NULL,
    trin_at_entry             REAL    NOT NULL,
    ad_ratio_at_entry         REAL    NOT NULL,
    cumulative_delta_es       REAL    NOT NULL,
    exit_reason               TEXT,
    optimal_exit_price        REAL,
    optimal_exit_time         TEXT,
    left_on_table_pct         REAL,
    was_stopped_prematurely   INTEGER,
    counterfactual_notes      TEXT,
    created_at                TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_SESSIONS_DDL = """
CREATE TABLE IF NOT EXISTS sessions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_date   TEXT    NOT NULL UNIQUE,
    session_type   TEXT    NOT NULL,
    gap_pct        REAL    NOT NULL,
    gap_points     REAL    NOT NULL,
    gap_sigma      REAL    NOT NULL,
    gap_class      TEXT    NOT NULL,
    expected_1sig  REAL    NOT NULL,
    expected_2sig  REAL    NOT NULL,
    vol_regime     TEXT    NOT NULL,
    risk_assessment TEXT   NOT NULL,
    data_json      TEXT    NOT NULL,
    created_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_GEX_SNAPSHOTS_DDL = """
CREATE TABLE IF NOT EXISTS gex_snapshots (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date          TEXT    NOT NULL,
    timestamp              TEXT    NOT NULL,
    total_net_gex          REAL    NOT NULL,
    gamma_flip_level       REAL    NOT NULL,
    call_wall              REAL    NOT NULL,
    put_wall               REAL    NOT NULL,
    max_pain               REAL    NOT NULL,
    plus_gex               REAL    NOT NULL,
    minus_gex              REAL    NOT NULL,
    transition_zone_upper  REAL    NOT NULL,
    transition_zone_lower  REAL    NOT NULL,
    vol_trigger            REAL    NOT NULL,
    gex_momentum           REAL    NOT NULL DEFAULT 0.0,
    charm_net_es_contracts REAL    NOT NULL DEFAULT 0.0,
    vanna_net_exposure     REAL    NOT NULL DEFAULT 0.0,
    strikes_json           TEXT    NOT NULL,
    created_at             TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_SIGNALS_DDL = """
CREATE TABLE IF NOT EXISTS signals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_date     TEXT    NOT NULL,
    timestamp       TEXT    NOT NULL,
    scan_type       TEXT    NOT NULL,
    direction       TEXT    NOT NULL,
    entry_price     REAL    NOT NULL,
    stop_loss       REAL    NOT NULL,
    profit_target   REAL    NOT NULL,
    position_type   TEXT    NOT NULL,
    contracts       INTEGER NOT NULL,
    max_risk        REAL    NOT NULL,
    expected_reward REAL    NOT NULL,
    risk_reward     REAL    NOT NULL,
    time_zone       TEXT    NOT NULL,
    session_type    TEXT    NOT NULL,
    confidence      REAL    NOT NULL,
    signal_json     TEXT    NOT NULL,
    outcome_json    TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_CALIBRATION_STATE_DDL = """
CREATE TABLE IF NOT EXISTS calibration_state (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp            TEXT    NOT NULL,
    entry_threshold      REAL    NOT NULL,
    stop_loss_pct        REAL    NOT NULL,
    regime               TEXT    NOT NULL,
    trade_count          INTEGER NOT NULL,
    gex_signal_accuracy  REAL    NOT NULL,
    weights_json         TEXT    NOT NULL,
    targets_json         TEXT    NOT NULL,
    full_state_json      TEXT    NOT NULL,
    created_at           TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_FACTOR_WEIGHTS_DDL = """
CREATE TABLE IF NOT EXISTS factor_weights (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    weight_date       TEXT    NOT NULL,
    market_internals  REAL    NOT NULL,
    options_flow      REAL    NOT NULL,
    price_action      REAL    NOT NULL,
    gex_structure     REAL    NOT NULL,
    cross_asset       REAL    NOT NULL,
    created_at        TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_DAILY_METRICS_DDL = """
CREATE TABLE IF NOT EXISTS daily_metrics (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_date   TEXT    NOT NULL UNIQUE,
    metrics_json  TEXT    NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_REGIME_HISTORY_DDL = """
CREATE TABLE IF NOT EXISTS regime_history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     TEXT    NOT NULL,
    regime        TEXT    NOT NULL,
    metadata_json TEXT,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_ALERTS_DDL = """
CREATE TABLE IF NOT EXISTS alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_date  TEXT    NOT NULL,
    timestamp   TEXT    NOT NULL,
    level       TEXT    NOT NULL,
    category    TEXT,
    message     TEXT    NOT NULL,
    data_json   TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_SCHEMA_VERSION_DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

# ---------------------------------------------------------------------------
# Indexes for query performance
# ---------------------------------------------------------------------------

_INDEXES = [
    # trades
    "CREATE INDEX IF NOT EXISTS idx_trades_entry_ts ON trades (timestamp_entry);",
    "CREATE INDEX IF NOT EXISTS idx_trades_scan_type ON trades (scan_type);",
    "CREATE INDEX IF NOT EXISTS idx_trades_direction ON trades (direction);",
    "CREATE INDEX IF NOT EXISTS idx_trades_exit_reason ON trades (exit_reason);",
    "CREATE INDEX IF NOT EXISTS idx_trades_session_type ON trades (session_type);",
    "CREATE INDEX IF NOT EXISTS idx_trades_pnl ON trades (pnl_dollars);",
    # sessions
    "CREATE INDEX IF NOT EXISTS idx_sessions_date ON sessions (session_date);",
    # gex_snapshots
    "CREATE INDEX IF NOT EXISTS idx_gex_date ON gex_snapshots (snapshot_date);",
    "CREATE INDEX IF NOT EXISTS idx_gex_timestamp ON gex_snapshots (timestamp);",
    # signals
    "CREATE INDEX IF NOT EXISTS idx_signals_date ON signals (signal_date);",
    "CREATE INDEX IF NOT EXISTS idx_signals_scan_type ON signals (scan_type);",
    "CREATE INDEX IF NOT EXISTS idx_signals_direction ON signals (direction);",
    # calibration_state
    "CREATE INDEX IF NOT EXISTS idx_calib_ts ON calibration_state (timestamp);",
    # factor_weights
    "CREATE INDEX IF NOT EXISTS idx_fw_date ON factor_weights (weight_date);",
    # daily_metrics
    "CREATE INDEX IF NOT EXISTS idx_dm_date ON daily_metrics (metric_date);",
    # regime_history
    "CREATE INDEX IF NOT EXISTS idx_regime_ts ON regime_history (timestamp);",
    # alerts
    "CREATE INDEX IF NOT EXISTS idx_alerts_date ON alerts (alert_date);",
    "CREATE INDEX IF NOT EXISTS idx_alerts_level ON alerts (level);",
]


# ===========================================================================
# Helper utilities
# ===========================================================================

def _dt_to_iso(dt: Optional[datetime]) -> Optional[str]:
    """Convert a datetime to ISO-8601 string, preserving None."""
    return dt.isoformat() if dt is not None else None


def _iso_to_dt(s: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 string back to datetime, preserving None."""
    if s is None or s == "":
        return None
    return datetime.fromisoformat(s)


def _date_to_str(d: Optional[date]) -> Optional[str]:
    """Convert a date to YYYY-MM-DD string, preserving None."""
    return d.isoformat() if d is not None else None


def _str_to_date(s: Optional[str]) -> Optional[date]:
    """Parse YYYY-MM-DD string to date, preserving None."""
    if s is None or s == "":
        return None
    return date.fromisoformat(s)


def _bool_to_int(b: Optional[bool]) -> Optional[int]:
    """Convert bool to SQLite integer (0/1), preserving None."""
    return int(b) if b is not None else None


def _int_to_bool(i: Optional[int]) -> Optional[bool]:
    """Convert SQLite integer back to bool, preserving None."""
    return bool(i) if i is not None else None


# ===========================================================================
# ScanifyDatabase
# ===========================================================================

class ScanifyDatabase:
    """SQLite database for persisting scanner state, trades, and calibration data.

    Designed for local single-process usage.  All writes are serialised through
    SQLite's native locking.  The ``WAL`` journal mode is enabled for improved
    concurrent-read performance.

    Parameters
    ----------
    db_path : str
        Filesystem path for the SQLite database file.
    auto_create : bool
        When *True* (default), ``initialize()`` is called automatically in
        the constructor so all tables and indexes exist on first use.
    """

    def __init__(self, db_path: str = "data/scanify.db", auto_create: bool = True) -> None:
        self.db_path = db_path
        self._ensure_directory()
        self._conn: Optional[sqlite3.Connection] = None
        if auto_create:
            self.initialize()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _ensure_directory(self) -> None:
        """Create parent directories for the database file if they do not exist."""
        parent = Path(self.db_path).parent
        if not parent.exists():
            parent.mkdir(parents=True, exist_ok=True)
            logger.info("Created database directory: %s", parent)

    def _get_connection(self) -> sqlite3.Connection:
        """Return (and lazily create) the database connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(
                self.db_path,
                detect_types=sqlite3.PARSE_DECLTYPES,
                check_same_thread=False,
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA foreign_keys=ON;")
            self._conn.execute("PRAGMA busy_timeout=5000;")
        return self._conn

    @contextmanager
    def _cursor(self) -> Generator[sqlite3.Cursor, None, None]:
        """Context manager that yields a cursor and commits on success."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def close(self) -> None:
        """Close the underlying database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            logger.debug("Database connection closed: %s", self.db_path)

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Create all tables and indexes if they do not already exist.

        Tables
        ------
        trades, sessions, gex_snapshots, signals, calibration_state,
        factor_weights, daily_metrics, regime_history, alerts, schema_version.
        """
        ddl_statements = [
            _TRADES_DDL,
            _SESSIONS_DDL,
            _GEX_SNAPSHOTS_DDL,
            _SIGNALS_DDL,
            _CALIBRATION_STATE_DDL,
            _FACTOR_WEIGHTS_DDL,
            _DAILY_METRICS_DDL,
            _REGIME_HISTORY_DDL,
            _ALERTS_DDL,
            _SCHEMA_VERSION_DDL,
        ]
        with self._cursor() as cur:
            for ddl in ddl_statements:
                cur.execute(ddl)
            for idx_sql in _INDEXES:
                cur.execute(idx_sql)
            # Record initial schema version if table is empty
            cur.execute("SELECT COUNT(*) FROM schema_version;")
            if cur.fetchone()[0] == 0:
                cur.execute(
                    "INSERT INTO schema_version (version) VALUES (?);",
                    (CURRENT_SCHEMA_VERSION,),
                )
        logger.info(
            "Database initialised (v%d): %s", CURRENT_SCHEMA_VERSION, self.db_path
        )

    # ==================================================================
    # TRADES
    # ==================================================================

    def save_trade(self, trade: TradeLog) -> int:
        """Persist a TradeLog record.  Returns the SQLite row id.

        If a trade with the same ``trade_id`` already exists the row is
        updated (upsert semantics).
        """
        sql = """
            INSERT INTO trades (
                trade_id, timestamp_entry, timestamp_exit,
                scan_type, direction, strike, option_type,
                entry_price, exit_price,
                max_gain_during_trade, max_loss_during_trade,
                pnl_dollars, pnl_percent, hold_time_minutes,
                spx_at_entry, vix1d_at_entry, vix_at_entry,
                expected_move_1sigma, composite_direction_score,
                session_type, net_gex_at_entry, gamma_flip_at_entry,
                time_zone, delta_at_entry, gamma_at_entry,
                theta_at_entry, iv_at_entry,
                tick_10min_avg, trin_at_entry, ad_ratio_at_entry,
                cumulative_delta_es,
                exit_reason, optimal_exit_price, optimal_exit_time,
                left_on_table_pct, was_stopped_prematurely,
                counterfactual_notes
            ) VALUES (
                ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
            )
            ON CONFLICT(trade_id) DO UPDATE SET
                timestamp_exit          = excluded.timestamp_exit,
                exit_price              = excluded.exit_price,
                max_gain_during_trade   = excluded.max_gain_during_trade,
                max_loss_during_trade   = excluded.max_loss_during_trade,
                pnl_dollars             = excluded.pnl_dollars,
                pnl_percent             = excluded.pnl_percent,
                hold_time_minutes       = excluded.hold_time_minutes,
                exit_reason             = excluded.exit_reason,
                optimal_exit_price      = excluded.optimal_exit_price,
                optimal_exit_time       = excluded.optimal_exit_time,
                left_on_table_pct       = excluded.left_on_table_pct,
                was_stopped_prematurely = excluded.was_stopped_prematurely,
                counterfactual_notes    = excluded.counterfactual_notes;
        """
        params = (
            trade.trade_id,
            _dt_to_iso(trade.timestamp_entry),
            _dt_to_iso(trade.timestamp_exit),
            trade.scan_type.value,
            trade.direction.value,
            trade.strike,
            trade.option_type.value,
            trade.entry_price,
            trade.exit_price,
            trade.max_gain_during_trade,
            trade.max_loss_during_trade,
            trade.pnl_dollars,
            trade.pnl_percent,
            trade.hold_time_minutes,
            trade.spx_at_entry,
            trade.vix1d_at_entry,
            trade.vix_at_entry,
            trade.expected_move_1sigma,
            trade.composite_direction_score,
            trade.session_type.value,
            trade.net_gex_at_entry,
            trade.gamma_flip_at_entry,
            trade.time_zone.value,
            trade.delta_at_entry,
            trade.gamma_at_entry,
            trade.theta_at_entry,
            trade.iv_at_entry,
            trade.tick_10min_avg,
            trade.trin_at_entry,
            trade.ad_ratio_at_entry,
            trade.cumulative_delta_es,
            trade.exit_reason.value if trade.exit_reason else None,
            trade.optimal_exit_price,
            _dt_to_iso(trade.optimal_exit_time),
            trade.left_on_table_pct,
            _bool_to_int(trade.was_stopped_prematurely),
            trade.counterfactual_notes,
        )
        with self._cursor() as cur:
            cur.execute(sql, params)
            row_id: int = cur.lastrowid  # type: ignore[assignment]
        logger.debug("Saved trade %s (row %d)", trade.trade_id, row_id)
        return row_id

    def _row_to_trade(self, row: sqlite3.Row) -> TradeLog:
        """Reconstruct a TradeLog from a database row."""
        from .models import (
            ExitReason,
            OptionSide,
            ScanType,
            SessionType,
            TimeZoneType,
            TradeDirection,
        )

        return TradeLog(
            trade_id=row["trade_id"],
            timestamp_entry=datetime.fromisoformat(row["timestamp_entry"]),
            timestamp_exit=_iso_to_dt(row["timestamp_exit"]),
            scan_type=ScanType(row["scan_type"]),
            direction=TradeDirection(row["direction"]),
            strike=row["strike"],
            option_type=OptionSide(row["option_type"]),
            entry_price=row["entry_price"],
            exit_price=row["exit_price"],
            max_gain_during_trade=row["max_gain_during_trade"],
            max_loss_during_trade=row["max_loss_during_trade"],
            pnl_dollars=row["pnl_dollars"],
            pnl_percent=row["pnl_percent"],
            hold_time_minutes=row["hold_time_minutes"],
            spx_at_entry=row["spx_at_entry"],
            vix1d_at_entry=row["vix1d_at_entry"],
            vix_at_entry=row["vix_at_entry"],
            expected_move_1sigma=row["expected_move_1sigma"],
            composite_direction_score=row["composite_direction_score"],
            session_type=SessionType(row["session_type"]),
            net_gex_at_entry=row["net_gex_at_entry"],
            gamma_flip_at_entry=row["gamma_flip_at_entry"],
            time_zone=TimeZoneType(row["time_zone"]),
            delta_at_entry=row["delta_at_entry"],
            gamma_at_entry=row["gamma_at_entry"],
            theta_at_entry=row["theta_at_entry"],
            iv_at_entry=row["iv_at_entry"],
            tick_10min_avg=row["tick_10min_avg"],
            trin_at_entry=row["trin_at_entry"],
            ad_ratio_at_entry=row["ad_ratio_at_entry"],
            cumulative_delta_es=row["cumulative_delta_es"],
            exit_reason=ExitReason(row["exit_reason"]) if row["exit_reason"] else None,
            optimal_exit_price=row["optimal_exit_price"],
            optimal_exit_time=_iso_to_dt(row["optimal_exit_time"]),
            left_on_table_pct=row["left_on_table_pct"],
            was_stopped_prematurely=_int_to_bool(row["was_stopped_prematurely"]),
            counterfactual_notes=row["counterfactual_notes"],
        )

    def get_trades(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        scan_type: Optional[str] = None,
        direction: Optional[str] = None,
    ) -> list[TradeLog]:
        """Query trades with optional filtering.

        Parameters
        ----------
        start_date, end_date : date, optional
            Inclusive date range filter on ``timestamp_entry``.
        scan_type : str, optional
            Filter by ScanType value (e.g. ``"DIRECTIONAL"``).
        direction : str, optional
            Filter by TradeDirection value (e.g. ``"BULL"``).

        Returns
        -------
        list[TradeLog]
            Matching trades ordered by entry timestamp descending.
        """
        clauses: list[str] = []
        params: list[Any] = []

        if start_date is not None:
            clauses.append("DATE(timestamp_entry) >= ?")
            params.append(_date_to_str(start_date))
        if end_date is not None:
            clauses.append("DATE(timestamp_entry) <= ?")
            params.append(_date_to_str(end_date))
        if scan_type is not None:
            clauses.append("scan_type = ?")
            params.append(scan_type)
        if direction is not None:
            clauses.append("direction = ?")
            params.append(direction)

        where = " AND ".join(clauses) if clauses else "1=1"
        sql = f"SELECT * FROM trades WHERE {where} ORDER BY timestamp_entry DESC;"

        with self._cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [self._row_to_trade(r) for r in rows]

    def get_trade_by_id(self, trade_id: str) -> Optional[TradeLog]:
        """Retrieve a single trade by its UUID."""
        with self._cursor() as cur:
            cur.execute("SELECT * FROM trades WHERE trade_id = ?;", (trade_id,))
            row = cur.fetchone()
        return self._row_to_trade(row) if row else None

    # ==================================================================
    # SESSIONS
    # ==================================================================

    def save_session(self, setup: SessionSetup, session_date: date) -> int:
        """Persist a SessionSetup for the given date.  Returns row id.

        Uses upsert so re-saving the same date overwrites the previous record.
        """
        data_json = setup.model_dump_json()
        sql = """
            INSERT INTO sessions (
                session_date, session_type, gap_pct, gap_points, gap_sigma,
                gap_class, expected_1sig, expected_2sig, vol_regime,
                risk_assessment, data_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(session_date) DO UPDATE SET
                session_type    = excluded.session_type,
                gap_pct         = excluded.gap_pct,
                gap_points      = excluded.gap_points,
                gap_sigma       = excluded.gap_sigma,
                gap_class       = excluded.gap_class,
                expected_1sig   = excluded.expected_1sig,
                expected_2sig   = excluded.expected_2sig,
                vol_regime      = excluded.vol_regime,
                risk_assessment = excluded.risk_assessment,
                data_json       = excluded.data_json;
        """
        params = (
            _date_to_str(session_date),
            setup.session_type.value,
            setup.gap_analysis.gap_pct,
            setup.gap_analysis.gap_points,
            setup.gap_analysis.gap_sigma,
            setup.gap_analysis.classification.value,
            setup.expected_move.final_1sigma,
            setup.expected_move.final_2sigma,
            setup.expected_move.vol_regime,
            setup.risk_assessment,
            data_json,
        )
        with self._cursor() as cur:
            cur.execute(sql, params)
            row_id: int = cur.lastrowid  # type: ignore[assignment]
        logger.debug("Saved session for %s (row %d)", session_date, row_id)
        return row_id

    def _row_to_session(self, row: sqlite3.Row) -> SessionSetup:
        """Reconstruct a SessionSetup from the stored JSON column."""
        return SessionSetup.model_validate_json(row["data_json"])

    def get_session(self, session_date: date) -> Optional[SessionSetup]:
        """Retrieve the session setup for a specific date."""
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM sessions WHERE session_date = ?;",
                (_date_to_str(session_date),),
            )
            row = cur.fetchone()
        return self._row_to_session(row) if row else None

    def get_sessions(self, start_date: date, end_date: date) -> list[SessionSetup]:
        """Retrieve session setups for a date range (inclusive)."""
        sql = """
            SELECT * FROM sessions
            WHERE session_date >= ? AND session_date <= ?
            ORDER BY session_date ASC;
        """
        with self._cursor() as cur:
            cur.execute(sql, (_date_to_str(start_date), _date_to_str(end_date)))
            rows = cur.fetchall()
        return [self._row_to_session(r) for r in rows]

    # ==================================================================
    # GEX SNAPSHOTS
    # ==================================================================

    def save_gex_snapshot(self, profile: GEXProfile) -> int:
        """Persist a GEX profile snapshot.  Returns row id."""
        snapshot_date = profile.timestamp.date().isoformat()
        strikes_data = [
            {
                "strike": s.strike,
                "call_gamma": s.call_gamma,
                "put_gamma": s.put_gamma,
                "call_oi": s.call_oi,
                "put_oi": s.put_oi,
                "dealer_gamma_call": s.dealer_gamma_call,
                "dealer_gamma_put": s.dealer_gamma_put,
                "net_gex": s.net_gex,
                "net_charm": s.net_charm,
                "net_vanna": s.net_vanna,
                "net_speed": s.net_speed,
            }
            for s in profile.strikes
        ]
        sql = """
            INSERT INTO gex_snapshots (
                snapshot_date, timestamp, total_net_gex, gamma_flip_level,
                call_wall, put_wall, max_pain, plus_gex, minus_gex,
                transition_zone_upper, transition_zone_lower, vol_trigger,
                gex_momentum, charm_net_es_contracts, vanna_net_exposure,
                strikes_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);
        """
        params = (
            snapshot_date,
            _dt_to_iso(profile.timestamp),
            profile.total_net_gex,
            profile.gamma_flip_level,
            profile.call_wall,
            profile.put_wall,
            profile.max_pain,
            profile.plus_gex,
            profile.minus_gex,
            profile.transition_zone_upper,
            profile.transition_zone_lower,
            profile.vol_trigger,
            profile.gex_momentum,
            profile.charm_net_es_contracts,
            profile.vanna_net_exposure,
            json.dumps(strikes_data),
        )
        with self._cursor() as cur:
            cur.execute(sql, params)
            row_id: int = cur.lastrowid  # type: ignore[assignment]
        logger.debug("Saved GEX snapshot at %s (row %d)", profile.timestamp, row_id)
        return row_id

    def _row_to_gex_profile(self, row: sqlite3.Row) -> GEXProfile:
        """Reconstruct a GEXProfile from a database row."""
        strikes_data = json.loads(row["strikes_json"])
        strikes = [StrikeGEX(**s) for s in strikes_data]
        return GEXProfile(
            timestamp=datetime.fromisoformat(row["timestamp"]),
            strikes=strikes,
            total_net_gex=row["total_net_gex"],
            gamma_flip_level=row["gamma_flip_level"],
            call_wall=row["call_wall"],
            put_wall=row["put_wall"],
            max_pain=row["max_pain"],
            plus_gex=row["plus_gex"],
            minus_gex=row["minus_gex"],
            transition_zone_upper=row["transition_zone_upper"],
            transition_zone_lower=row["transition_zone_lower"],
            vol_trigger=row["vol_trigger"],
            gex_momentum=row["gex_momentum"],
            charm_net_es_contracts=row["charm_net_es_contracts"],
            vanna_net_exposure=row["vanna_net_exposure"],
        )

    def get_gex_snapshots(self, snapshot_date: date) -> list[GEXProfile]:
        """Retrieve all GEX snapshots for a given date, ordered chronologically."""
        sql = """
            SELECT * FROM gex_snapshots
            WHERE snapshot_date = ?
            ORDER BY timestamp ASC;
        """
        with self._cursor() as cur:
            cur.execute(sql, (_date_to_str(snapshot_date),))
            rows = cur.fetchall()
        return [self._row_to_gex_profile(r) for r in rows]

    def get_latest_gex(self) -> Optional[GEXProfile]:
        """Return the most recent GEX snapshot across all dates."""
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM gex_snapshots ORDER BY timestamp DESC LIMIT 1;"
            )
            row = cur.fetchone()
        return self._row_to_gex_profile(row) if row else None

    # ==================================================================
    # SIGNALS
    # ==================================================================

    def save_signal(self, signal: ScanSignal, outcome: Optional[dict] = None) -> int:
        """Persist a ScanSignal with an optional outcome dictionary.  Returns row id."""
        signal_date = signal.timestamp.date().isoformat()
        signal_json = signal.model_dump_json()
        outcome_json = json.dumps(outcome) if outcome is not None else None

        sql = """
            INSERT INTO signals (
                signal_date, timestamp, scan_type, direction,
                entry_price, stop_loss, profit_target, position_type,
                contracts, max_risk, expected_reward, risk_reward,
                time_zone, session_type, confidence,
                signal_json, outcome_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);
        """
        params = (
            signal_date,
            _dt_to_iso(signal.timestamp),
            signal.scan_type.value,
            signal.direction.value,
            signal.entry_price,
            signal.stop_loss,
            signal.profit_target,
            signal.position_type.value,
            signal.contracts,
            signal.max_risk,
            signal.expected_reward,
            signal.risk_reward_ratio,
            signal.time_zone.value,
            signal.session_type.value,
            signal.direction_score.confidence,
            signal_json,
            outcome_json,
        )
        with self._cursor() as cur:
            cur.execute(sql, params)
            row_id: int = cur.lastrowid  # type: ignore[assignment]
        logger.debug("Saved signal %s/%s (row %d)", signal.scan_type.value, signal.direction.value, row_id)
        return row_id

    def get_signals(
        self,
        signal_date: Optional[date] = None,
        scan_type: Optional[str] = None,
    ) -> list[dict]:
        """Query signals with optional date and scan-type filters.

        Returns a list of dictionaries containing the full signal payload
        (``signal``), the outcome (``outcome``), and row metadata.
        """
        clauses: list[str] = []
        params: list[Any] = []

        if signal_date is not None:
            clauses.append("signal_date = ?")
            params.append(_date_to_str(signal_date))
        if scan_type is not None:
            clauses.append("scan_type = ?")
            params.append(scan_type)

        where = " AND ".join(clauses) if clauses else "1=1"
        sql = f"SELECT * FROM signals WHERE {where} ORDER BY timestamp DESC;"

        with self._cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

        results: list[dict] = []
        for row in rows:
            results.append({
                "id": row["id"],
                "signal_date": row["signal_date"],
                "timestamp": row["timestamp"],
                "scan_type": row["scan_type"],
                "direction": row["direction"],
                "entry_price": row["entry_price"],
                "stop_loss": row["stop_loss"],
                "profit_target": row["profit_target"],
                "position_type": row["position_type"],
                "contracts": row["contracts"],
                "max_risk": row["max_risk"],
                "expected_reward": row["expected_reward"],
                "risk_reward": row["risk_reward"],
                "time_zone": row["time_zone"],
                "session_type": row["session_type"],
                "confidence": row["confidence"],
                "signal": json.loads(row["signal_json"]),
                "outcome": json.loads(row["outcome_json"]) if row["outcome_json"] else None,
            })
        return results

    # ==================================================================
    # CALIBRATION STATE
    # ==================================================================

    def save_calibration_state(self, state: CalibrationState) -> int:
        """Persist a calibration snapshot.  Returns row id.

        Every save appends a new row so the full calibration history is
        preserved for audit and analysis.
        """
        weights_json = json.dumps(state.current_weights.as_dict())
        targets_json = json.dumps(state.profit_targets_by_zone)
        full_state_json = state.model_dump_json()

        sql = """
            INSERT INTO calibration_state (
                timestamp, entry_threshold, stop_loss_pct, regime,
                trade_count, gex_signal_accuracy,
                weights_json, targets_json, full_state_json
            ) VALUES (?,?,?,?,?,?,?,?,?);
        """
        params = (
            _dt_to_iso(state.last_calibration),
            state.entry_threshold,
            state.stop_loss_pct,
            state.regime,
            state.trade_count,
            state.gex_signal_accuracy,
            weights_json,
            targets_json,
            full_state_json,
        )
        with self._cursor() as cur:
            cur.execute(sql, params)
            row_id: int = cur.lastrowid  # type: ignore[assignment]
        logger.debug("Saved calibration state (row %d)", row_id)
        return row_id

    def _row_to_calibration(self, row: sqlite3.Row) -> CalibrationState:
        """Reconstruct a CalibrationState from its stored JSON."""
        return CalibrationState.model_validate_json(row["full_state_json"])

    def get_calibration_state(self) -> Optional[CalibrationState]:
        """Return the most recent calibration state, or None if none exists."""
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM calibration_state ORDER BY id DESC LIMIT 1;"
            )
            row = cur.fetchone()
        return self._row_to_calibration(row) if row else None

    def get_calibration_history(self, days: int = 30) -> list[CalibrationState]:
        """Return calibration states from the last *days* calendar days.

        Results are ordered oldest-first.
        """
        cutoff = date.today().isoformat()
        sql = """
            SELECT * FROM calibration_state
            WHERE DATE(timestamp) >= DATE(?, '-' || ? || ' days')
            ORDER BY timestamp ASC;
        """
        with self._cursor() as cur:
            cur.execute(sql, (cutoff, days))
            rows = cur.fetchall()
        return [self._row_to_calibration(r) for r in rows]

    # ==================================================================
    # DAILY METRICS
    # ==================================================================

    def save_daily_metrics(self, metric_date: date, metrics: dict) -> int:
        """Persist aggregated daily performance metrics.  Returns row id.

        Upserts on ``metric_date`` so re-computation overwrites prior values.
        """
        sql = """
            INSERT INTO daily_metrics (metric_date, metrics_json)
            VALUES (?, ?)
            ON CONFLICT(metric_date) DO UPDATE SET
                metrics_json = excluded.metrics_json;
        """
        with self._cursor() as cur:
            cur.execute(sql, (_date_to_str(metric_date), json.dumps(metrics)))
            row_id: int = cur.lastrowid  # type: ignore[assignment]
        logger.debug("Saved daily metrics for %s (row %d)", metric_date, row_id)
        return row_id

    def get_daily_metrics(self, start_date: date, end_date: date) -> list[dict]:
        """Retrieve daily metrics for a date range (inclusive).

        Each entry contains ``date`` and ``metrics`` keys.
        """
        sql = """
            SELECT * FROM daily_metrics
            WHERE metric_date >= ? AND metric_date <= ?
            ORDER BY metric_date ASC;
        """
        with self._cursor() as cur:
            cur.execute(sql, (_date_to_str(start_date), _date_to_str(end_date)))
            rows = cur.fetchall()
        return [
            {
                "date": row["metric_date"],
                "metrics": json.loads(row["metrics_json"]),
            }
            for row in rows
        ]

    # ==================================================================
    # FACTOR WEIGHTS
    # ==================================================================

    def save_factor_weights(self, weights: FactorWeights, weight_date: date) -> int:
        """Persist a factor weight snapshot for the given date.  Returns row id."""
        sql = """
            INSERT INTO factor_weights (
                weight_date, market_internals, options_flow,
                price_action, gex_structure, cross_asset
            ) VALUES (?,?,?,?,?,?);
        """
        params = (
            _date_to_str(weight_date),
            weights.market_internals,
            weights.options_flow,
            weights.price_action,
            weights.gex_structure,
            weights.cross_asset,
        )
        with self._cursor() as cur:
            cur.execute(sql, params)
            row_id: int = cur.lastrowid  # type: ignore[assignment]
        logger.debug("Saved factor weights for %s (row %d)", weight_date, row_id)
        return row_id

    def get_factor_weight_history(self, days: int = 60) -> list[dict]:
        """Return factor weight snapshots from the last *days* calendar days.

        Each entry is a dictionary with ``date`` and individual weight keys.
        Results are ordered oldest-first.
        """
        cutoff = date.today().isoformat()
        sql = """
            SELECT * FROM factor_weights
            WHERE weight_date >= DATE(?, '-' || ? || ' days')
            ORDER BY weight_date ASC;
        """
        with self._cursor() as cur:
            cur.execute(sql, (cutoff, days))
            rows = cur.fetchall()
        return [
            {
                "date": row["weight_date"],
                "market_internals": row["market_internals"],
                "options_flow": row["options_flow"],
                "price_action": row["price_action"],
                "gex_structure": row["gex_structure"],
                "cross_asset": row["cross_asset"],
            }
            for row in rows
        ]

    # ==================================================================
    # ALERTS
    # ==================================================================

    def save_alert(self, alert: dict) -> int:
        """Persist an alert record.  Returns row id.

        Expected keys in *alert*: ``level``, ``message``.
        Optional keys: ``category``, ``timestamp``, ``data``.
        """
        ts = alert.get("timestamp", datetime.now(timezone.utc).isoformat())
        if isinstance(ts, datetime):
            ts = ts.isoformat()
        alert_date = ts[:10]  # YYYY-MM-DD prefix
        data_json = json.dumps(alert.get("data")) if "data" in alert else None

        sql = """
            INSERT INTO alerts (
                alert_date, timestamp, level, category, message, data_json
            ) VALUES (?,?,?,?,?,?);
        """
        params = (
            alert_date,
            ts,
            alert["level"],
            alert.get("category"),
            alert["message"],
            data_json,
        )
        with self._cursor() as cur:
            cur.execute(sql, params)
            row_id: int = cur.lastrowid  # type: ignore[assignment]
        logger.debug("Saved alert [%s] (row %d)", alert["level"], row_id)
        return row_id

    def get_alerts(
        self,
        alert_date: Optional[date] = None,
        level: Optional[str] = None,
    ) -> list[dict]:
        """Query alerts with optional date and severity filters."""
        clauses: list[str] = []
        params: list[Any] = []

        if alert_date is not None:
            clauses.append("alert_date = ?")
            params.append(_date_to_str(alert_date))
        if level is not None:
            clauses.append("level = ?")
            params.append(level)

        where = " AND ".join(clauses) if clauses else "1=1"
        sql = f"SELECT * FROM alerts WHERE {where} ORDER BY timestamp DESC;"

        with self._cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [
            {
                "id": row["id"],
                "alert_date": row["alert_date"],
                "timestamp": row["timestamp"],
                "level": row["level"],
                "category": row["category"],
                "message": row["message"],
                "data": json.loads(row["data_json"]) if row["data_json"] else None,
            }
            for row in rows
        ]

    # ==================================================================
    # MAINTENANCE
    # ==================================================================

    def vacuum(self) -> None:
        """Run ``VACUUM`` to reclaim space and defragment the database file."""
        conn = self._get_connection()
        conn.execute("VACUUM;")
        logger.info("Database vacuumed: %s", self.db_path)

    def backup(self, backup_path: str) -> str:
        """Create a physical copy of the database file.

        Parameters
        ----------
        backup_path : str
            Destination file path for the backup.

        Returns
        -------
        str
            The absolute path of the created backup file.
        """
        backup_dir = Path(backup_path).parent
        if not backup_dir.exists():
            backup_dir.mkdir(parents=True, exist_ok=True)

        # Use SQLite online backup API for a consistent snapshot
        conn = self._get_connection()
        dest = sqlite3.connect(backup_path)
        try:
            conn.backup(dest)
        finally:
            dest.close()

        abs_path = str(Path(backup_path).resolve())
        logger.info("Database backed up to %s", abs_path)
        return abs_path

    def get_database_stats(self) -> dict:
        """Return table row counts, schema version, and on-disk size.

        Returns
        -------
        dict
            Keys: ``tables`` (dict of table_name -> row_count),
            ``total_records``, ``schema_version``, ``disk_size_bytes``,
            ``disk_size_mb``.
        """
        tables = [
            "trades",
            "sessions",
            "gex_snapshots",
            "signals",
            "calibration_state",
            "factor_weights",
            "daily_metrics",
            "regime_history",
            "alerts",
        ]
        table_counts: dict[str, int] = {}
        total = 0

        with self._cursor() as cur:
            for table in tables:
                cur.execute(f"SELECT COUNT(*) FROM {table};")  # noqa: S608
                count = cur.fetchone()[0]
                table_counts[table] = count
                total += count

            cur.execute("SELECT MAX(version) FROM schema_version;")
            version_row = cur.fetchone()
            schema_ver = version_row[0] if version_row else 0

        disk_size = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0

        return {
            "tables": table_counts,
            "total_records": total,
            "schema_version": schema_ver,
            "disk_size_bytes": disk_size,
            "disk_size_mb": round(disk_size / (1024 * 1024), 3),
        }


# ===========================================================================
# DataExporter
# ===========================================================================

class DataExporter:
    """Export data from the SCANIFY database in various formats.

    Supports CSV, Parquet (via pandas), and combined backtest data bundles.

    Parameters
    ----------
    db : ScanifyDatabase
        An initialised database instance to read from.
    """

    def __init__(self, db: ScanifyDatabase) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # CSV export
    # ------------------------------------------------------------------

    def export_trades_csv(
        self, start_date: date, end_date: date, filepath: str
    ) -> str:
        """Export trades to a CSV file.  Returns the absolute file path."""
        import csv

        trades = self.db.get_trades(start_date=start_date, end_date=end_date)
        if not trades:
            logger.warning("No trades found for CSV export (%s - %s)", start_date, end_date)

        self._ensure_parent(filepath)

        fieldnames = [
            "trade_id", "timestamp_entry", "timestamp_exit",
            "scan_type", "direction", "strike", "option_type",
            "entry_price", "exit_price",
            "max_gain_during_trade", "max_loss_during_trade",
            "pnl_dollars", "pnl_percent", "hold_time_minutes",
            "spx_at_entry", "vix1d_at_entry", "vix_at_entry",
            "expected_move_1sigma", "composite_direction_score",
            "session_type", "net_gex_at_entry", "gamma_flip_at_entry",
            "time_zone", "delta_at_entry", "gamma_at_entry",
            "theta_at_entry", "iv_at_entry",
            "tick_10min_avg", "trin_at_entry", "ad_ratio_at_entry",
            "cumulative_delta_es",
            "exit_reason", "optimal_exit_price", "optimal_exit_time",
            "left_on_table_pct", "was_stopped_prematurely",
            "counterfactual_notes",
        ]

        with open(filepath, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for t in trades:
                row = {
                    "trade_id": t.trade_id,
                    "timestamp_entry": _dt_to_iso(t.timestamp_entry),
                    "timestamp_exit": _dt_to_iso(t.timestamp_exit),
                    "scan_type": t.scan_type.value,
                    "direction": t.direction.value,
                    "strike": t.strike,
                    "option_type": t.option_type.value,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "max_gain_during_trade": t.max_gain_during_trade,
                    "max_loss_during_trade": t.max_loss_during_trade,
                    "pnl_dollars": t.pnl_dollars,
                    "pnl_percent": t.pnl_percent,
                    "hold_time_minutes": t.hold_time_minutes,
                    "spx_at_entry": t.spx_at_entry,
                    "vix1d_at_entry": t.vix1d_at_entry,
                    "vix_at_entry": t.vix_at_entry,
                    "expected_move_1sigma": t.expected_move_1sigma,
                    "composite_direction_score": t.composite_direction_score,
                    "session_type": t.session_type.value,
                    "net_gex_at_entry": t.net_gex_at_entry,
                    "gamma_flip_at_entry": t.gamma_flip_at_entry,
                    "time_zone": t.time_zone.value,
                    "delta_at_entry": t.delta_at_entry,
                    "gamma_at_entry": t.gamma_at_entry,
                    "theta_at_entry": t.theta_at_entry,
                    "iv_at_entry": t.iv_at_entry,
                    "tick_10min_avg": t.tick_10min_avg,
                    "trin_at_entry": t.trin_at_entry,
                    "ad_ratio_at_entry": t.ad_ratio_at_entry,
                    "cumulative_delta_es": t.cumulative_delta_es,
                    "exit_reason": t.exit_reason.value if t.exit_reason else None,
                    "optimal_exit_price": t.optimal_exit_price,
                    "optimal_exit_time": _dt_to_iso(t.optimal_exit_time),
                    "left_on_table_pct": t.left_on_table_pct,
                    "was_stopped_prematurely": t.was_stopped_prematurely,
                    "counterfactual_notes": t.counterfactual_notes,
                }
                writer.writerow(row)

        abs_path = str(Path(filepath).resolve())
        logger.info("Exported %d trades to CSV: %s", len(trades), abs_path)
        return abs_path

    # ------------------------------------------------------------------
    # Parquet export
    # ------------------------------------------------------------------

    def export_trades_parquet(
        self, start_date: date, end_date: date, filepath: str
    ) -> str:
        """Export trades to a Parquet file via pandas.  Returns the absolute path.

        Raises ``ImportError`` if pandas or pyarrow are not installed.
        """
        try:
            import pandas as pd
        except ImportError as exc:
            raise ImportError(
                "pandas is required for Parquet export.  Install with: "
                "pip install pandas pyarrow"
            ) from exc

        trades = self.db.get_trades(start_date=start_date, end_date=end_date)
        if not trades:
            logger.warning("No trades found for Parquet export (%s - %s)", start_date, end_date)

        self._ensure_parent(filepath)

        records = []
        for t in trades:
            records.append({
                "trade_id": t.trade_id,
                "timestamp_entry": t.timestamp_entry,
                "timestamp_exit": t.timestamp_exit,
                "scan_type": t.scan_type.value,
                "direction": t.direction.value,
                "strike": t.strike,
                "option_type": t.option_type.value,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "max_gain_during_trade": t.max_gain_during_trade,
                "max_loss_during_trade": t.max_loss_during_trade,
                "pnl_dollars": t.pnl_dollars,
                "pnl_percent": t.pnl_percent,
                "hold_time_minutes": t.hold_time_minutes,
                "spx_at_entry": t.spx_at_entry,
                "vix1d_at_entry": t.vix1d_at_entry,
                "vix_at_entry": t.vix_at_entry,
                "expected_move_1sigma": t.expected_move_1sigma,
                "composite_direction_score": t.composite_direction_score,
                "session_type": t.session_type.value,
                "net_gex_at_entry": t.net_gex_at_entry,
                "gamma_flip_at_entry": t.gamma_flip_at_entry,
                "time_zone": t.time_zone.value,
                "delta_at_entry": t.delta_at_entry,
                "gamma_at_entry": t.gamma_at_entry,
                "theta_at_entry": t.theta_at_entry,
                "iv_at_entry": t.iv_at_entry,
                "tick_10min_avg": t.tick_10min_avg,
                "trin_at_entry": t.trin_at_entry,
                "ad_ratio_at_entry": t.ad_ratio_at_entry,
                "cumulative_delta_es": t.cumulative_delta_es,
                "exit_reason": t.exit_reason.value if t.exit_reason else None,
                "optimal_exit_price": t.optimal_exit_price,
                "optimal_exit_time": t.optimal_exit_time,
                "left_on_table_pct": t.left_on_table_pct,
                "was_stopped_prematurely": t.was_stopped_prematurely,
                "counterfactual_notes": t.counterfactual_notes,
            })

        df = pd.DataFrame(records)
        df.to_parquet(filepath, engine="pyarrow", index=False)

        abs_path = str(Path(filepath).resolve())
        logger.info("Exported %d trades to Parquet: %s", len(trades), abs_path)
        return abs_path

    # ------------------------------------------------------------------
    # GEX history export
    # ------------------------------------------------------------------

    def export_gex_history(self, gex_date: date, filepath: str) -> str:
        """Export all GEX snapshots for a date to a JSON file.  Returns the absolute path."""
        snapshots = self.db.get_gex_snapshots(gex_date)
        self._ensure_parent(filepath)

        data = []
        for profile in snapshots:
            entry = {
                "timestamp": _dt_to_iso(profile.timestamp),
                "total_net_gex": profile.total_net_gex,
                "gamma_flip_level": profile.gamma_flip_level,
                "call_wall": profile.call_wall,
                "put_wall": profile.put_wall,
                "max_pain": profile.max_pain,
                "plus_gex": profile.plus_gex,
                "minus_gex": profile.minus_gex,
                "transition_zone_upper": profile.transition_zone_upper,
                "transition_zone_lower": profile.transition_zone_lower,
                "vol_trigger": profile.vol_trigger,
                "gex_momentum": profile.gex_momentum,
                "charm_net_es_contracts": profile.charm_net_es_contracts,
                "vanna_net_exposure": profile.vanna_net_exposure,
                "num_strikes": len(profile.strikes),
            }
            data.append(entry)

        with open(filepath, "w", encoding="utf-8") as fh:
            json.dump(
                {"date": _date_to_str(gex_date), "snapshots": data},
                fh,
                indent=2,
            )

        abs_path = str(Path(filepath).resolve())
        logger.info("Exported %d GEX snapshots to %s", len(data), abs_path)
        return abs_path

    # ------------------------------------------------------------------
    # Calibration history export
    # ------------------------------------------------------------------

    def export_calibration_history(self, filepath: str) -> str:
        """Export the full calibration history to a JSON file.  Returns the absolute path."""
        # Fetch a generous window (10 years) to capture everything
        states = self.db.get_calibration_history(days=3650)
        self._ensure_parent(filepath)

        data = []
        for state in states:
            data.append({
                "last_calibration": _dt_to_iso(state.last_calibration),
                "entry_threshold": state.entry_threshold,
                "stop_loss_pct": state.stop_loss_pct,
                "regime": state.regime,
                "trade_count": state.trade_count,
                "gex_signal_accuracy": state.gex_signal_accuracy,
                "weights": state.current_weights.as_dict(),
                "profit_targets_by_zone": state.profit_targets_by_zone,
            })

        with open(filepath, "w", encoding="utf-8") as fh:
            json.dump({"calibration_history": data}, fh, indent=2)

        abs_path = str(Path(filepath).resolve())
        logger.info("Exported %d calibration states to %s", len(data), abs_path)
        return abs_path

    # ------------------------------------------------------------------
    # Full backtest bundle
    # ------------------------------------------------------------------

    def export_full_backtest_data(
        self, start_date: date, end_date: date, filepath: str
    ) -> str:
        """Export a comprehensive backtest data bundle as JSON.

        Combines trades, daily metrics, signals, and factor weight history
        for the specified date range into a single file.

        Returns the absolute file path.
        """
        trades = self.db.get_trades(start_date=start_date, end_date=end_date)
        metrics = self.db.get_daily_metrics(start_date=start_date, end_date=end_date)
        signals = self.db.get_signals()  # all signals
        weights = self.db.get_factor_weight_history(days=3650)

        self._ensure_parent(filepath)

        # Serialize trades
        trades_data = []
        for t in trades:
            trades_data.append(json.loads(t.model_dump_json()))

        # Filter signals to date range
        start_str = _date_to_str(start_date)
        end_str = _date_to_str(end_date)
        filtered_signals = [
            s for s in signals
            if start_str <= s["signal_date"] <= end_str
        ]

        bundle = {
            "export_metadata": {
                "start_date": start_str,
                "end_date": end_str,
                "export_timestamp": datetime.now(timezone.utc).isoformat(),
                "trade_count": len(trades_data),
                "signal_count": len(filtered_signals),
                "metric_days": len(metrics),
            },
            "trades": trades_data,
            "daily_metrics": metrics,
            "signals": filtered_signals,
            "factor_weights": weights,
        }

        with open(filepath, "w", encoding="utf-8") as fh:
            json.dump(bundle, fh, indent=2, default=str)

        abs_path = str(Path(filepath).resolve())
        logger.info(
            "Exported backtest bundle (%d trades, %d signals) to %s",
            len(trades_data),
            len(filtered_signals),
            abs_path,
        )
        return abs_path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_parent(filepath: str) -> None:
        """Create parent directories for an export file if needed."""
        parent = Path(filepath).parent
        if not parent.exists():
            parent.mkdir(parents=True, exist_ok=True)


# ===========================================================================
# DataMigrator
# ===========================================================================

# Migration registry: version -> (description, up_sql_statements)
_MIGRATIONS: dict[int, tuple[str, list[str]]] = {
    # Version 1 is the initial schema (created by initialize()).
    # Future migrations are appended here.  Example:
    #
    # 2: (
    #     "Add position_size column to trades",
    #     [
    #         "ALTER TABLE trades ADD COLUMN position_size REAL;",
    #         "CREATE INDEX IF NOT EXISTS idx_trades_position_size ON trades (position_size);",
    #     ],
    # ),
}


class DataMigrator:
    """Handle database schema migrations for the SCANIFY persistence layer.

    Migrations are defined as ordered SQL statement lists keyed by version
    number.  The ``schema_version`` table tracks which migrations have been
    applied.

    Parameters
    ----------
    db : ScanifyDatabase
        An initialised database instance whose schema to migrate.
    """

    def __init__(self, db: ScanifyDatabase) -> None:
        self.db = db

    def get_current_version(self) -> int:
        """Return the highest schema version that has been applied."""
        with self.db._cursor() as cur:
            cur.execute("SELECT MAX(version) FROM schema_version;")
            row = cur.fetchone()
        return row[0] if row and row[0] is not None else 0

    def get_pending_migrations(self) -> list[int]:
        """Return sorted list of migration versions that have not yet been applied."""
        current = self.get_current_version()
        return sorted(v for v in _MIGRATIONS if v > current)

    def migrate_to(self, version: int) -> bool:
        """Apply all migrations up to and including *version*.

        Parameters
        ----------
        version : int
            Target schema version.

        Returns
        -------
        bool
            *True* if any migrations were applied, *False* otherwise.
        """
        current = self.get_current_version()
        if version <= current:
            logger.info(
                "Already at version %d; nothing to migrate (target=%d).",
                current,
                version,
            )
            return False

        pending = sorted(v for v in _MIGRATIONS if current < v <= version)
        if not pending:
            logger.info("No migrations found between v%d and v%d.", current, version)
            return False

        for ver in pending:
            desc, statements = _MIGRATIONS[ver]
            logger.info("Applying migration v%d: %s", ver, desc)
            with self.db._cursor() as cur:
                for sql in statements:
                    cur.execute(sql)
                cur.execute(
                    "INSERT INTO schema_version (version) VALUES (?);", (ver,)
                )
            logger.info("Migration v%d applied successfully.", ver)

        return True

    def run_all_pending(self) -> int:
        """Apply every pending migration in order.

        Returns
        -------
        int
            Number of migrations applied.
        """
        pending = self.get_pending_migrations()
        if not pending:
            logger.info("No pending migrations.")
            return 0

        for ver in pending:
            desc, statements = _MIGRATIONS[ver]
            logger.info("Applying migration v%d: %s", ver, desc)
            with self.db._cursor() as cur:
                for sql in statements:
                    cur.execute(sql)
                cur.execute(
                    "INSERT INTO schema_version (version) VALUES (?);", (ver,)
                )
            logger.info("Migration v%d applied successfully.", ver)

        logger.info("Applied %d migration(s).", len(pending))
        return len(pending)
