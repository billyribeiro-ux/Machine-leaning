"""
SCANIFY SPX 0DTE Options Day Trading Scanner -- Market Replay Engine
=====================================================================

Provides a market replay / simulation engine for the SCANIFY 0DTE SPX Scanner.
Allows replaying historical trading days tick-by-tick for training, testing,
and strategy development.  Also includes synthetic scenario generation for
stress testing, live session recording for later replay, and pattern-discovery
analytics across multiple sessions.

Classes
-------
MarketReplayEngine
    Replays historical market data tick-by-tick for simulation and training.
ScenarioGenerator
    Generates synthetic market scenarios (flash crashes, gamma squeezes,
    FOMC reactions, trending / range days, VIX spikes, pin-to-strike) for
    deterministic stress testing.
SessionRecorder
    Records live market sessions to disk for later replay.
ReplayAnalyzer
    Analyses replayed sessions to discover gamma squeezes, VIX spikes,
    gamma flips, intraday patterns, and time-zone-specific statistics.

Dependencies
------------
numpy, pandas, asyncio, pathlib, json, gzip

Author: SCANIFY Engine
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
import math
import os
import time as _time_mod
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .constants import (
    INTRADAY_ZONE_SCHEDULE,
    TRADING_MINUTES_PER_DAY,
    TRADING_DAYS_PER_YEAR,
    IntradayZone,
    ZONE_BOUNDARIES,
)
from .models import (
    CrossAssetData,
    DirectionScore,
    GEXProfile,
    GEXSignal,
    MarketInternals,
    OptionsChain,
    OptionQuote,
    OptionSide,
    SessionType,
    StrikeGEX,
    TimeZoneType,
    TradeDirection,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

_MARKET_OPEN: time = time(9, 30)
_MARKET_CLOSE: time = time(16, 0)
_DEFAULT_TICK_INTERVAL_SECONDS: int = 30
_SPX_MULTIPLIER: float = 100.0
_ES_POINT_VALUE: float = 50.0
_EPSILON: float = 1e-12


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _time_to_seconds(t: time) -> int:
    """Convert a ``datetime.time`` to seconds since midnight."""
    return t.hour * 3600 + t.minute * 60 + t.second


def _seconds_to_time(s: int) -> time:
    """Convert seconds since midnight to ``datetime.time``."""
    s = max(0, min(s, 86399))
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    return time(h, m, sec)


def _time_to_minutes(t: time) -> float:
    """Convert a ``datetime.time`` to fractional minutes since midnight."""
    return t.hour * 60.0 + t.minute + t.second / 60.0


def _minutes_to_time(m: float) -> time:
    """Convert fractional minutes since midnight to ``datetime.time``."""
    total_sec = int(m * 60)
    total_sec = max(0, min(total_sec, 86399))
    h = total_sec // 3600
    mi = (total_sec % 3600) // 60
    s = total_sec % 60
    return time(h, mi, s)


def _lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation between *a* and *b* at parameter *t* in [0, 1]."""
    return a + (b - a) * max(0.0, min(1.0, t))


def _classify_session_type(
    spx_range: float,
    avg_vix: float,
    total_volume: int,
) -> SessionType:
    """Heuristic session type classification from summary statistics."""
    if avg_vix > 25:
        return SessionType.VOLATILE
    if spx_range > 50:
        return SessionType.TRENDING
    if spx_range < 15:
        return SessionType.RANGE
    return SessionType.TRENDING if total_volume > 2_000_000 else SessionType.RANGE


def _get_time_zone_for(t: time) -> TimeZoneType:
    """Map a wall-clock time to the appropriate ``TimeZoneType``."""
    t_sec = _time_to_seconds(t)
    for boundary in INTRADAY_ZONE_SCHEDULE:
        if _time_to_seconds(boundary.start) <= t_sec < _time_to_seconds(boundary.end):
            return TimeZoneType(boundary.zone.name)
    if t_sec < _time_to_seconds(time(9, 30)):
        return TimeZoneType.PRE_MARKET
    return TimeZoneType.SETTLEMENT_WINDOW


# =========================================================================
# 1. MarketReplayEngine
# =========================================================================


class MarketReplayEngine:
    """Replays historical market data tick-by-tick for simulation and training.

    The engine loads serialised session data from disk (JSON / gzip-compressed
    JSON produced by :class:`SessionRecorder`) and plays it back at configurable
    speed, invoking a user-supplied callback at every tick with the full market
    snapshot.

    Parameters
    ----------
    data_dir : str
        Root directory containing replay session files organised as
        ``<data_dir>/<YYYY-MM-DD>/``.
    playback_speed : float
        Playback speed multiplier.  ``1.0`` is real-time (30-second ticks
        arrive every 30 seconds), ``10.0`` is 10x speed, ``0`` plays as fast
        as possible with no inter-tick delay.
    start_time : time
        Earliest wall-clock time to include in a replay (default 09:30).
    end_time : time
        Latest wall-clock time to include in a replay (default 16:00).
    tick_interval_seconds : int
        Nominal seconds between successive ticks in the stored data
        (default 30).

    Example
    -------
    >>> engine = MarketReplayEngine(data_dir="data/replay", playback_speed=0)
    >>> engine.load_session(date(2025, 1, 6))
    True
    >>> await engine.play(my_callback)
    """

    def __init__(
        self,
        data_dir: str = "data/replay",
        playback_speed: float = 1.0,
        start_time: time = time(9, 30),
        end_time: time = time(16, 0),
        tick_interval_seconds: int = _DEFAULT_TICK_INTERVAL_SECONDS,
    ) -> None:
        self._data_dir = Path(data_dir)
        self._playback_speed = max(0.0, playback_speed)
        self._start_time = start_time
        self._end_time = end_time
        self._tick_interval = tick_interval_seconds

        # Session state
        self._session_date: Optional[date] = None
        self._ticks: list[dict] = []
        self._current_index: int = 0
        self._is_paused: bool = False
        self._is_playing: bool = False
        self._pause_event: asyncio.Event = asyncio.Event()
        self._pause_event.set()  # Not paused initially

        logger.info(
            "MarketReplayEngine initialised: data_dir=%s speed=%.1fx "
            "window=%s-%s tick_interval=%ds",
            self._data_dir,
            self._playback_speed,
            self._start_time.isoformat(),
            self._end_time.isoformat(),
            self._tick_interval,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def session_date(self) -> Optional[date]:
        """Currently loaded session date, or ``None``."""
        return self._session_date

    @property
    def tick_count(self) -> int:
        """Total number of ticks in the loaded session."""
        return len(self._ticks)

    @property
    def current_index(self) -> int:
        """Index of the next tick to be played."""
        return self._current_index

    @property
    def is_playing(self) -> bool:
        """True while an async play loop is executing."""
        return self._is_playing

    @property
    def is_paused(self) -> bool:
        """True when playback is paused."""
        return self._is_paused

    @property
    def progress_pct(self) -> float:
        """Playback progress as a percentage (0-100)."""
        if not self._ticks:
            return 0.0
        return (self._current_index / len(self._ticks)) * 100.0

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def load_session(self, session_date: date) -> bool:
        """Load all historical data for a trading session.

        Searches for session files in ``<data_dir>/<YYYY-MM-DD>/`` and loads
        options chain snapshots, SPX prices, ES data, market internals, VIX
        data, and GEX profiles into an ordered tick timeline.

        Parameters
        ----------
        session_date : date
            The trading date to load.

        Returns
        -------
        bool
            ``True`` if data was loaded successfully, ``False`` otherwise.
        """
        session_dir = self._data_dir / session_date.isoformat()

        if not session_dir.exists():
            logger.warning(
                "Session directory not found: %s. Attempting consolidated file.",
                session_dir,
            )
            return self._load_consolidated(session_date)

        self._session_date = session_date
        self._ticks = []
        self._current_index = 0

        # Attempt to load individual data files
        loaded_any = False
        for file_path in sorted(session_dir.iterdir()):
            if file_path.suffix in (".json", ".gz"):
                try:
                    raw = self._read_file(file_path)
                    if isinstance(raw, list):
                        self._ticks.extend(raw)
                    elif isinstance(raw, dict) and "ticks" in raw:
                        self._ticks.extend(raw["ticks"])
                    elif isinstance(raw, dict):
                        self._ticks.append(raw)
                    loaded_any = True
                except Exception:
                    logger.exception("Failed to load file: %s", file_path)

        if not loaded_any:
            logger.error("No data files loaded for session %s", session_date)
            return False

        # Sort by timestamp and filter to session window
        self._ticks = self._sort_and_filter_ticks(self._ticks)

        logger.info(
            "Loaded session %s: %d ticks from %s to %s",
            session_date,
            len(self._ticks),
            self._ticks[0].get("timestamp", "?") if self._ticks else "N/A",
            self._ticks[-1].get("timestamp", "?") if self._ticks else "N/A",
        )
        return len(self._ticks) > 0

    def _load_consolidated(self, session_date: date) -> bool:
        """Load a single consolidated session file (fallback path).

        Looks for ``<data_dir>/session_<YYYY-MM-DD>.json[.gz]``.
        """
        for suffix in (".json.gz", ".json"):
            candidate = self._data_dir / f"session_{session_date.isoformat()}{suffix}"
            if candidate.exists():
                try:
                    raw = self._read_file(candidate)
                    ticks = raw if isinstance(raw, list) else raw.get("ticks", [])
                    self._session_date = session_date
                    self._ticks = self._sort_and_filter_ticks(ticks)
                    self._current_index = 0
                    logger.info(
                        "Loaded consolidated session %s: %d ticks",
                        session_date,
                        len(self._ticks),
                    )
                    return len(self._ticks) > 0
                except Exception:
                    logger.exception(
                        "Failed to load consolidated file: %s", candidate
                    )
        return False

    @staticmethod
    def _read_file(file_path: Path) -> Any:
        """Read a JSON or gzip-compressed JSON file and return parsed data."""
        if file_path.suffix == ".gz" or str(file_path).endswith(".json.gz"):
            with gzip.open(file_path, "rt", encoding="utf-8") as fh:
                return json.load(fh)
        with open(file_path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def _sort_and_filter_ticks(self, ticks: list[dict]) -> list[dict]:
        """Sort ticks chronologically and keep only those within the session window."""
        start_sec = _time_to_seconds(self._start_time)
        end_sec = _time_to_seconds(self._end_time)

        filtered: list[dict] = []
        for tick in ticks:
            ts = tick.get("timestamp")
            if ts is None:
                filtered.append(tick)
                continue
            try:
                if isinstance(ts, str):
                    dt = datetime.fromisoformat(ts)
                elif isinstance(ts, (int, float)):
                    dt = datetime.utcfromtimestamp(ts)
                else:
                    dt = ts
                tick_sec = _time_to_seconds(dt.time())
                if start_sec <= tick_sec <= end_sec:
                    tick["_parsed_dt"] = dt
                    filtered.append(tick)
            except (ValueError, TypeError, OSError):
                filtered.append(tick)

        filtered.sort(
            key=lambda t: t.get("_parsed_dt", datetime.min)
        )
        return filtered

    # ------------------------------------------------------------------
    # Playback control
    # ------------------------------------------------------------------

    async def play(self, callback: Callable) -> None:
        """Play the loaded session at the configured speed.

        At each tick the *callback* is invoked as::

            await callback(timestamp, market_snapshot)

        or called synchronously if the callback is not a coroutine.

        Parameters
        ----------
        callback : Callable
            Function receiving ``(datetime, dict)`` at each tick.

        Raises
        ------
        RuntimeError
            If no session data has been loaded.
        """
        if not self._ticks:
            raise RuntimeError("No session loaded. Call load_session() first.")

        await self.play_range(self._start_time, self._end_time, callback)

    async def play_range(
        self,
        start: time,
        end: time,
        callback: Callable,
    ) -> None:
        """Play only a specific time range within the loaded session.

        Parameters
        ----------
        start : time
            Start of the sub-range.
        end : time
            End of the sub-range.
        callback : Callable
            Function receiving ``(datetime, dict)`` at each tick.
        """
        if not self._ticks:
            raise RuntimeError("No session loaded. Call load_session() first.")

        start_sec = _time_to_seconds(start)
        end_sec = _time_to_seconds(end)

        self._is_playing = True
        logger.info(
            "Playback started: %s - %s (speed=%.1fx)",
            start.isoformat(),
            end.isoformat(),
            self._playback_speed,
        )

        prev_dt: Optional[datetime] = None

        try:
            while self._current_index < len(self._ticks):
                # Honour pause
                await self._pause_event.wait()

                tick = self._ticks[self._current_index]
                tick_dt = tick.get("_parsed_dt")

                if tick_dt is not None:
                    tick_sec = _time_to_seconds(tick_dt.time())
                    if tick_sec < start_sec:
                        self._current_index += 1
                        continue
                    if tick_sec > end_sec:
                        break

                # Compute inter-tick delay
                if (
                    self._playback_speed > 0
                    and prev_dt is not None
                    and tick_dt is not None
                ):
                    real_delta = (tick_dt - prev_dt).total_seconds()
                    if real_delta > 0:
                        sleep_time = real_delta / self._playback_speed
                        await asyncio.sleep(sleep_time)

                # Build snapshot and invoke callback
                snapshot = self._build_snapshot(tick)
                timestamp = tick_dt if tick_dt else datetime.utcnow()

                if asyncio.iscoroutinefunction(callback):
                    await callback(timestamp, snapshot)
                else:
                    callback(timestamp, snapshot)

                prev_dt = tick_dt
                self._current_index += 1

        finally:
            self._is_playing = False
            logger.info(
                "Playback finished at index %d / %d (%.1f%%)",
                self._current_index,
                len(self._ticks),
                self.progress_pct,
            )

    def pause(self) -> None:
        """Pause the active playback.

        Playback will resume from the same tick when :meth:`resume` is called.
        """
        if not self._is_paused:
            self._is_paused = True
            self._pause_event.clear()
            logger.info("Playback paused at index %d", self._current_index)

    def resume(self) -> None:
        """Resume playback after a :meth:`pause`."""
        if self._is_paused:
            self._is_paused = False
            self._pause_event.set()
            logger.info("Playback resumed at index %d", self._current_index)

    def seek(self, target_time: time) -> dict:
        """Jump to a specific time in the session and return the snapshot.

        Parameters
        ----------
        target_time : time
            Wall-clock time to seek to.

        Returns
        -------
        dict
            The market snapshot at or immediately before *target_time*.
        """
        target_sec = _time_to_seconds(target_time)
        best_idx = 0
        best_diff = float("inf")

        for idx, tick in enumerate(self._ticks):
            tick_dt = tick.get("_parsed_dt")
            if tick_dt is None:
                continue
            tick_sec = _time_to_seconds(tick_dt.time())
            diff = abs(tick_sec - target_sec)
            if diff < best_diff:
                best_diff = diff
                best_idx = idx
            # Optimisation: stop once we pass the target
            if tick_sec > target_sec and diff > best_diff:
                break

        self._current_index = best_idx
        tick = self._ticks[best_idx] if self._ticks else {}
        snapshot = self._build_snapshot(tick)
        logger.info(
            "Seeked to %s (index=%d, actual=%s)",
            target_time.isoformat(),
            best_idx,
            tick.get("_parsed_dt", "?"),
        )
        return snapshot

    def set_speed(self, speed: float) -> None:
        """Change the playback speed.

        Parameters
        ----------
        speed : float
            New playback speed multiplier (0 = as-fast-as-possible).
        """
        self._playback_speed = max(0.0, speed)
        logger.info("Playback speed set to %.1fx", self._playback_speed)

    # ------------------------------------------------------------------
    # Snapshot construction
    # ------------------------------------------------------------------

    def get_snapshot_at(self, target_time: time) -> dict:
        """Get a complete market snapshot at a specific time.

        Returns a dictionary with the following keys (when available):

        - ``spx_price``       : float
        - ``es_price``        : float
        - ``options_chain``   : dict
        - ``internals``       : dict
        - ``cross_asset``     : dict
        - ``gex_profile``     : dict
        - ``direction_score`` : dict
        - ``timestamp``       : str (ISO-8601)
        - ``time_zone``       : str
        - ``session_type``    : str

        Parameters
        ----------
        target_time : time
            Wall-clock time for which to retrieve the snapshot.

        Returns
        -------
        dict
            Complete market snapshot.
        """
        return self.seek(target_time)

    def _build_snapshot(self, tick: dict) -> dict:
        """Assemble a canonical market snapshot from a raw tick dict.

        Raw ticks may be stored in various layouts.  This method normalises
        the representation into a uniform dictionary consumed by callers.
        """
        tick_dt = tick.get("_parsed_dt")
        tick_time = tick_dt.time() if tick_dt else _MARKET_OPEN

        snapshot: dict[str, Any] = {
            "timestamp": tick_dt.isoformat() if tick_dt else None,
            "time_zone": _get_time_zone_for(tick_time).value,
        }

        # SPX / ES prices
        snapshot["spx_price"] = tick.get(
            "spx_price", tick.get("underlying_price", tick.get("price"))
        )
        snapshot["es_price"] = tick.get("es_price")

        # Options chain
        snapshot["options_chain"] = tick.get("options_chain", tick.get("chain"))

        # Market internals
        snapshot["internals"] = tick.get(
            "internals", tick.get("market_internals")
        )

        # Cross-asset data
        snapshot["cross_asset"] = tick.get(
            "cross_asset", tick.get("cross_asset_data")
        )

        # GEX profile
        snapshot["gex_profile"] = tick.get(
            "gex_profile", tick.get("gex")
        )

        # Direction score
        snapshot["direction_score"] = tick.get(
            "direction_score", tick.get("score")
        )

        # Session type (if recorded)
        snapshot["session_type"] = tick.get("session_type")

        return snapshot

    # ------------------------------------------------------------------
    # Session summary
    # ------------------------------------------------------------------

    def get_session_summary(self, session_date: date) -> dict:
        """Compute summary statistics for a historical session.

        If the requested date differs from the currently loaded session, the
        method will attempt to load it first.

        Parameters
        ----------
        session_date : date
            Trading date to summarise.

        Returns
        -------
        dict
            Summary containing:
            - ``date``            : str
            - ``tick_count``      : int
            - ``spx_open``        : float
            - ``spx_close``       : float
            - ``spx_high``        : float
            - ``spx_low``         : float
            - ``spx_range``       : float
            - ``avg_vix``         : float
            - ``avg_volume``      : float
            - ``session_type``    : str
            - ``notable_events``  : list[str]
            - ``time_zone_stats`` : dict
        """
        if self._session_date != session_date:
            loaded = self.load_session(session_date)
            if not loaded:
                logger.warning(
                    "Could not load session for summary: %s", session_date
                )
                return {"date": session_date.isoformat(), "error": "no_data"}

        spx_prices: list[float] = []
        vix_values: list[float] = []
        volumes: list[int] = []
        notable: list[str] = []
        zone_ticks: dict[str, int] = defaultdict(int)

        for tick in self._ticks:
            spx = tick.get("spx_price", tick.get("underlying_price"))
            if spx is not None:
                spx_prices.append(float(spx))

            cross = tick.get("cross_asset", tick.get("cross_asset_data", {}))
            if isinstance(cross, dict):
                vix_val = cross.get("vix")
                if vix_val is not None:
                    vix_values.append(float(vix_val))
                es_vol = cross.get("es_volume")
                if es_vol is not None:
                    volumes.append(int(es_vol))

            tick_dt = tick.get("_parsed_dt")
            if tick_dt is not None:
                zone_name = _get_time_zone_for(tick_dt.time()).value
                zone_ticks[zone_name] += 1

        # Detect notable events
        if spx_prices:
            max_drawdown = 0.0
            peak = spx_prices[0]
            for p in spx_prices:
                if p > peak:
                    peak = p
                dd = peak - p
                if dd > max_drawdown:
                    max_drawdown = dd
            if max_drawdown > 30:
                notable.append(
                    f"Large intraday drawdown: {max_drawdown:.1f} points"
                )

            # Check for V-shape recovery
            mid_idx = len(spx_prices) // 2
            if mid_idx > 0:
                first_half_low = min(spx_prices[:mid_idx])
                second_half_high = max(spx_prices[mid_idx:])
                if (
                    first_half_low < spx_prices[0] - 15
                    and second_half_high > first_half_low + 20
                ):
                    notable.append("V-shape recovery detected")

        if vix_values and max(vix_values) - min(vix_values) > 5:
            notable.append(
                f"VIX range: {min(vix_values):.1f} - {max(vix_values):.1f}"
            )

        spx_open = spx_prices[0] if spx_prices else 0.0
        spx_close = spx_prices[-1] if spx_prices else 0.0
        spx_high = max(spx_prices) if spx_prices else 0.0
        spx_low = min(spx_prices) if spx_prices else 0.0
        spx_range = spx_high - spx_low
        avg_vix = float(np.mean(vix_values)) if vix_values else 0.0
        avg_volume = float(np.mean(volumes)) if volumes else 0.0
        total_volume = sum(volumes) if volumes else 0

        session_type = _classify_session_type(spx_range, avg_vix, total_volume)

        return {
            "date": session_date.isoformat(),
            "tick_count": len(self._ticks),
            "spx_open": round(spx_open, 2),
            "spx_close": round(spx_close, 2),
            "spx_high": round(spx_high, 2),
            "spx_low": round(spx_low, 2),
            "spx_range": round(spx_range, 2),
            "avg_vix": round(avg_vix, 2),
            "avg_volume": round(avg_volume, 0),
            "session_type": session_type.value,
            "notable_events": notable,
            "time_zone_stats": dict(zone_ticks),
        }


# =========================================================================
# 2. ScenarioGenerator
# =========================================================================


class ScenarioGenerator:
    """Generate synthetic market scenarios for stress testing.

    Each generator method produces a list of tick dictionaries that simulate
    a specific market regime.  These ticks conform to the same schema
    consumed by :class:`MarketReplayEngine` and can be injected directly
    into the replay pipeline.

    All generated ticks use 30-second intervals spanning the standard
    session window (09:30 -- 16:00 ET) unless otherwise specified.

    Parameters
    ----------
    tick_interval_seconds : int
        Interval between synthetic ticks (default 30).
    random_seed : int or None
        Seed for the numpy RNG to ensure reproducibility (default ``None``).

    Example
    -------
    >>> gen = ScenarioGenerator(random_seed=42)
    >>> ticks = gen.generate_flash_crash(base_spx=6000, drop_pct=3.0)
    >>> len(ticks) > 0
    True
    """

    def __init__(
        self,
        tick_interval_seconds: int = _DEFAULT_TICK_INTERVAL_SECONDS,
        random_seed: Optional[int] = None,
    ) -> None:
        self._tick_interval = tick_interval_seconds
        self._rng = np.random.default_rng(random_seed)
        self._session_start = _MARKET_OPEN
        self._session_end = _MARKET_CLOSE
        logger.info(
            "ScenarioGenerator initialised: tick_interval=%ds seed=%s",
            self._tick_interval,
            random_seed,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _session_tick_times(self) -> list[time]:
        """Generate the full list of tick timestamps for a standard session."""
        start_sec = _time_to_seconds(self._session_start)
        end_sec = _time_to_seconds(self._session_end)
        times: list[time] = []
        s = start_sec
        while s <= end_sec:
            times.append(_seconds_to_time(s))
            s += self._tick_interval
        return times

    def _make_tick(
        self,
        t: time,
        spx: float,
        vix: float = 16.0,
        es_offset: float = -3.0,
        extra: Optional[dict] = None,
    ) -> dict:
        """Construct a single synthetic tick dictionary.

        Parameters
        ----------
        t : time
            Wall-clock time for the tick.
        spx : float
            SPX spot price.
        vix : float
            VIX level.
        es_offset : float
            ES futures offset from SPX (ES typically trades ~3 pts below SPX).
        extra : dict or None
            Additional key-value pairs merged into the tick.
        """
        dt = datetime(2025, 1, 6, t.hour, t.minute, t.second)
        tick: dict[str, Any] = {
            "timestamp": dt.isoformat(),
            "_parsed_dt": dt,
            "spx_price": round(spx, 2),
            "es_price": round(spx + es_offset, 2),
            "cross_asset": {
                "vix": round(vix, 2),
                "vix1d": round(vix * 1.05, 2),
                "vix9d": round(vix * 0.95, 2),
                "es_price": round(spx + es_offset, 2),
                "es_volume": int(self._rng.integers(50_000, 200_000)),
            },
            "internals": {
                "nyse_tick": int(self._rng.integers(-800, 800)),
                "nyse_tick_10min_avg": float(
                    self._rng.normal(0, 200)
                ),
                "cumulative_tick": float(self._rng.normal(0, 5000)),
                "nyse_trin": round(
                    max(0.3, float(self._rng.normal(1.0, 0.3))), 2
                ),
                "advance_decline_ratio": round(
                    max(0.1, float(self._rng.normal(1.0, 0.4))), 2
                ),
                "es_cumulative_delta": float(
                    self._rng.normal(0, 10000)
                ),
            },
            "time_zone": _get_time_zone_for(t).value,
        }
        if extra:
            tick.update(extra)
        return tick

    def _brownian_path(
        self,
        start: float,
        steps: int,
        drift: float = 0.0,
        vol: float = 0.5,
    ) -> np.ndarray:
        """Generate a geometric Brownian motion price path.

        Parameters
        ----------
        start : float
            Initial price.
        steps : int
            Number of time steps.
        drift : float
            Per-step drift (in points).
        vol : float
            Per-step volatility (in points).

        Returns
        -------
        np.ndarray
            Price path of length *steps*.
        """
        increments = self._rng.normal(drift, vol, size=steps)
        return start + np.cumsum(increments)

    # ------------------------------------------------------------------
    # Scenario generators
    # ------------------------------------------------------------------

    def generate_flash_crash(
        self,
        base_spx: float = 6000.0,
        drop_pct: float = 3.0,
        recovery_minutes: int = 15,
    ) -> list[dict]:
        """Generate a flash-crash scenario.

        Models a sudden SPX sell-off followed by a rapid recovery.  The crash
        occurs at approximately 10:30 AM, bottoms within 5 minutes, and
        recovers over *recovery_minutes*.

        Parameters
        ----------
        base_spx : float
            Pre-crash SPX price.
        drop_pct : float
            Maximum drawdown as a percentage of *base_spx*.
        recovery_minutes : int
            Minutes for the full recovery from the trough.

        Returns
        -------
        list[dict]
            Synthetic tick sequence.
        """
        times = self._session_tick_times()
        drop_points = base_spx * (drop_pct / 100.0)
        crash_start_sec = _time_to_seconds(time(10, 30))
        crash_bottom_sec = crash_start_sec + 5 * 60
        recovery_end_sec = crash_bottom_sec + recovery_minutes * 60

        ticks: list[dict] = []
        for t in times:
            t_sec = _time_to_seconds(t)

            if t_sec < crash_start_sec:
                # Pre-crash: gentle drift
                frac = (t_sec - _time_to_seconds(self._session_start)) / max(
                    1, crash_start_sec - _time_to_seconds(self._session_start)
                )
                noise = float(self._rng.normal(0, 0.5))
                spx = base_spx + frac * 3 + noise
                vix = 16.0 + float(self._rng.normal(0, 0.3))

            elif t_sec < crash_bottom_sec:
                # Crash descent
                frac = (t_sec - crash_start_sec) / max(
                    1, crash_bottom_sec - crash_start_sec
                )
                spx = base_spx - drop_points * frac + float(
                    self._rng.normal(0, 2)
                )
                vix = 16.0 + 20 * frac + float(self._rng.normal(0, 1))

            elif t_sec < recovery_end_sec:
                # Recovery
                frac = (t_sec - crash_bottom_sec) / max(
                    1, recovery_end_sec - crash_bottom_sec
                )
                spx = (base_spx - drop_points) + drop_points * 0.85 * frac + float(
                    self._rng.normal(0, 1.5)
                )
                vix = 36.0 - 15 * frac + float(self._rng.normal(0, 0.5))

            else:
                # Post-recovery drift
                recovered_level = base_spx - drop_points * 0.15
                elapsed = t_sec - recovery_end_sec
                noise = float(self._rng.normal(0, 0.8))
                spx = recovered_level + elapsed * 0.001 + noise
                vix = 21.0 + float(self._rng.normal(0, 0.5))

            ticks.append(self._make_tick(t, spx, vix))

        logger.info(
            "Generated flash crash: base=%.0f drop=%.1f%% recovery=%dmin ticks=%d",
            base_spx,
            drop_pct,
            recovery_minutes,
            len(ticks),
        )
        return ticks

    def generate_gamma_squeeze(
        self,
        base_spx: float = 6000.0,
        squeeze_points: float = 30.0,
        duration_minutes: int = 20,
    ) -> list[dict]:
        """Generate a gamma-squeeze scenario.

        Models a rapid, self-reinforcing upward move driven by dealer gamma
        hedging, starting at approximately 14:00 (when gamma exposure becomes
        significant for 0DTE).

        Parameters
        ----------
        base_spx : float
            SPX price before the squeeze.
        squeeze_points : float
            Total SPX points of upside during the squeeze.
        duration_minutes : int
            Duration of the squeeze phase.

        Returns
        -------
        list[dict]
            Synthetic tick sequence.
        """
        times = self._session_tick_times()
        squeeze_start_sec = _time_to_seconds(time(14, 0))
        squeeze_end_sec = squeeze_start_sec + duration_minutes * 60

        ticks: list[dict] = []
        pre_squeeze_price = base_spx

        for t in times:
            t_sec = _time_to_seconds(t)

            if t_sec < squeeze_start_sec:
                # Normal morning session with mild upside bias
                frac = (t_sec - _time_to_seconds(self._session_start)) / max(
                    1, squeeze_start_sec - _time_to_seconds(self._session_start)
                )
                noise = float(self._rng.normal(0, 0.6))
                spx = base_spx + frac * 5 + noise
                pre_squeeze_price = spx
                vix = 16.0 - frac * 2 + float(self._rng.normal(0, 0.2))

            elif t_sec < squeeze_end_sec:
                # Gamma squeeze: convex acceleration
                frac = (t_sec - squeeze_start_sec) / max(
                    1, squeeze_end_sec - squeeze_start_sec
                )
                # Convex (accelerating) path: frac^0.6
                move = squeeze_points * (frac ** 0.6)
                noise = float(self._rng.normal(0, 1.0))
                spx = pre_squeeze_price + move + noise
                # VIX rises modestly on rapid move
                vix = 14.0 + 4 * frac + float(self._rng.normal(0, 0.3))

            else:
                # Post-squeeze: elevated plateau with mild pullback
                post_frac = (t_sec - squeeze_end_sec) / max(
                    1,
                    _time_to_seconds(self._session_end) - squeeze_end_sec,
                )
                pullback = squeeze_points * 0.15 * post_frac
                noise = float(self._rng.normal(0, 0.5))
                spx = (
                    pre_squeeze_price + squeeze_points - pullback + noise
                )
                vix = 18.0 - 2 * post_frac + float(self._rng.normal(0, 0.2))

            ticks.append(
                self._make_tick(
                    t,
                    spx,
                    max(10.0, vix),
                    extra={"scenario": "gamma_squeeze"},
                )
            )

        logger.info(
            "Generated gamma squeeze: base=%.0f move=+%.0fpts "
            "duration=%dmin ticks=%d",
            base_spx,
            squeeze_points,
            duration_minutes,
            len(ticks),
        )
        return ticks

    def generate_fomc_reaction(
        self,
        base_spx: float = 6000.0,
        surprise_direction: str = "hawkish",
        magnitude: float = 2.0,
    ) -> list[dict]:
        """Generate an FOMC announcement reaction scenario.

        Models a quiet pre-announcement session, a sharp reaction at 14:00
        (FOMC release), followed by extended post-announcement volatility.

        Parameters
        ----------
        base_spx : float
            SPX price before the announcement.
        surprise_direction : str
            ``"hawkish"`` (bearish for equities) or ``"dovish"`` (bullish).
        magnitude : float
            Severity multiplier (1.0 = normal, 2.0 = strong surprise).

        Returns
        -------
        list[dict]
            Synthetic tick sequence.
        """
        times = self._session_tick_times()
        fomc_sec = _time_to_seconds(time(14, 0))
        direction_sign = -1.0 if surprise_direction.lower() == "hawkish" else 1.0
        initial_move = direction_sign * magnitude * 15.0  # points

        ticks: list[dict] = []
        pre_fomc_price = base_spx

        for t in times:
            t_sec = _time_to_seconds(t)

            if t_sec < fomc_sec:
                # Pre-FOMC: tight range, low vol anticipation
                noise = float(self._rng.normal(0, 0.3))
                spx = base_spx + noise
                pre_fomc_price = spx
                vix = 18.0 + float(self._rng.normal(0, 0.2))

            elif t_sec < fomc_sec + 120:
                # Initial reaction (2 minutes): sharp move
                frac = (t_sec - fomc_sec) / 120.0
                spx = pre_fomc_price + initial_move * frac + float(
                    self._rng.normal(0, 3)
                )
                vix = 18.0 + abs(initial_move) * 0.3 * frac + float(
                    self._rng.normal(0, 1)
                )

            elif t_sec < fomc_sec + 1800:
                # Post-reaction (30 minutes): whipsaw / digestion
                elapsed_min = (t_sec - fomc_sec - 120) / 60.0
                whipsaw = float(
                    self._rng.normal(0, magnitude * 3)
                )
                trend = initial_move * 0.5 * math.sin(
                    elapsed_min / 5.0
                )
                spx = pre_fomc_price + initial_move + trend + whipsaw
                vix = 22.0 + magnitude * 2 + float(
                    self._rng.normal(0, 1)
                )

            else:
                # Settling: gradual convergence to a new level
                settle_frac = (
                    t_sec - fomc_sec - 1800
                ) / max(
                    1,
                    _time_to_seconds(self._session_end) - fomc_sec - 1800,
                )
                final_move = initial_move * 0.7
                noise = float(self._rng.normal(0, 1.5 * (1 - settle_frac)))
                spx = pre_fomc_price + final_move + noise
                vix = 20.0 + magnitude - magnitude * settle_frac * 0.5 + float(
                    self._rng.normal(0, 0.5)
                )

            ticks.append(
                self._make_tick(
                    t,
                    spx,
                    max(10.0, vix),
                    extra={
                        "scenario": "fomc_reaction",
                        "surprise_direction": surprise_direction,
                    },
                )
            )

        logger.info(
            "Generated FOMC reaction: base=%.0f direction=%s "
            "magnitude=%.1f ticks=%d",
            base_spx,
            surprise_direction,
            magnitude,
            len(ticks),
        )
        return ticks

    def generate_trending_day(
        self,
        base_spx: float = 6000.0,
        direction: str = "up",
        total_move_points: float = 40.0,
    ) -> list[dict]:
        """Generate a trending session.

        Models a session with a clear directional bias from open to close,
        with orderly pullbacks along the way.

        Parameters
        ----------
        base_spx : float
            SPX opening price.
        direction : str
            ``"up"`` or ``"down"``.
        total_move_points : float
            Total SPX points moved by the close.

        Returns
        -------
        list[dict]
            Synthetic tick sequence.
        """
        times = self._session_tick_times()
        sign = 1.0 if direction.lower() == "up" else -1.0
        n_ticks = len(times)

        # Create a trending path with mild mean-reversion pullbacks
        base_trend = np.linspace(0, sign * total_move_points, n_ticks)
        noise = np.cumsum(self._rng.normal(0, 0.3, n_ticks))
        # Add periodic pullbacks (sine wave)
        pullback_amplitude = total_move_points * 0.08
        pullbacks = pullback_amplitude * np.sin(
            np.linspace(0, 6 * math.pi, n_ticks)
        )
        path = base_spx + base_trend + noise + pullbacks

        ticks: list[dict] = []
        for i, t in enumerate(times):
            spx = float(path[i])
            # VIX: slightly elevated on down days, compressed on up
            vix_base = 16.0 if sign > 0 else 19.0
            vix = vix_base + float(self._rng.normal(0, 0.3))
            ticks.append(
                self._make_tick(
                    t,
                    spx,
                    max(10.0, vix),
                    extra={"scenario": "trending", "direction": direction},
                )
            )

        logger.info(
            "Generated trending day: base=%.0f direction=%s "
            "move=%.0fpts ticks=%d",
            base_spx,
            direction,
            total_move_points,
            len(ticks),
        )
        return ticks

    def generate_range_day(
        self,
        base_spx: float = 6000.0,
        range_width: float = 15.0,
    ) -> list[dict]:
        """Generate a range-bound session.

        Models a low-directional session where SPX oscillates within a
        defined range, with mean-reversion dynamics dominating.

        Parameters
        ----------
        base_spx : float
            Mid-point of the range.
        range_width : float
            Total range (high - low) in SPX points.

        Returns
        -------
        list[dict]
            Synthetic tick sequence.
        """
        times = self._session_tick_times()
        n_ticks = len(times)
        half_range = range_width / 2.0

        # Ornstein-Uhlenbeck (mean-reverting) process
        theta = 0.15  # Mean-reversion speed
        sigma = 0.6   # Volatility of noise
        x = 0.0
        path: list[float] = []
        for _ in range(n_ticks):
            dx = -theta * x + sigma * float(self._rng.normal(0, 1))
            x += dx
            # Soft clamp to keep within range
            x = max(-half_range, min(half_range, x))
            path.append(base_spx + x)

        ticks: list[dict] = []
        for i, t in enumerate(times):
            vix = 13.0 + float(self._rng.normal(0, 0.3))
            ticks.append(
                self._make_tick(
                    t,
                    path[i],
                    max(10.0, vix),
                    extra={"scenario": "range_day"},
                )
            )

        logger.info(
            "Generated range day: base=%.0f range=%.0fpts ticks=%d",
            base_spx,
            range_width,
            len(ticks),
        )
        return ticks

    def generate_vix_spike(
        self,
        base_vix: float = 16.0,
        spike_to: float = 35.0,
        spike_minutes: int = 10,
    ) -> list[dict]:
        """Generate a VIX spike scenario.

        Models a session where VIX spikes sharply from *base_vix* to
        *spike_to* over *spike_minutes*, with corresponding SPX weakness.

        Parameters
        ----------
        base_vix : float
            Starting VIX level.
        spike_to : float
            Peak VIX during the spike.
        spike_minutes : int
            Duration of the spike (base to peak).

        Returns
        -------
        list[dict]
            Synthetic tick sequence.
        """
        times = self._session_tick_times()
        spike_start_sec = _time_to_seconds(time(11, 0))
        spike_peak_sec = spike_start_sec + spike_minutes * 60
        spike_settle_sec = spike_peak_sec + 45 * 60  # 45-min decay

        vix_delta = spike_to - base_vix
        base_spx = 6000.0

        ticks: list[dict] = []
        for t in times:
            t_sec = _time_to_seconds(t)

            if t_sec < spike_start_sec:
                vix = base_vix + float(self._rng.normal(0, 0.3))
                spx = base_spx + float(self._rng.normal(0, 0.5))

            elif t_sec < spike_peak_sec:
                frac = (t_sec - spike_start_sec) / max(
                    1, spike_peak_sec - spike_start_sec
                )
                vix = base_vix + vix_delta * frac + float(
                    self._rng.normal(0, 0.5)
                )
                # SPX drops proportionally to VIX rise
                spx_drop = (vix - base_vix) * 1.5
                spx = base_spx - spx_drop + float(self._rng.normal(0, 1))

            elif t_sec < spike_settle_sec:
                frac = (t_sec - spike_peak_sec) / max(
                    1, spike_settle_sec - spike_peak_sec
                )
                # Exponential decay
                decay = 1.0 - frac ** 0.5
                vix = base_vix + vix_delta * decay + float(
                    self._rng.normal(0, 0.5)
                )
                spx_drop = (vix - base_vix) * 1.2
                spx = base_spx - spx_drop + float(self._rng.normal(0, 0.8))

            else:
                vix = base_vix + vix_delta * 0.15 + float(
                    self._rng.normal(0, 0.3)
                )
                spx = base_spx - vix_delta * 0.2 + float(
                    self._rng.normal(0, 0.5)
                )

            ticks.append(
                self._make_tick(
                    t,
                    spx,
                    max(9.0, vix),
                    extra={"scenario": "vix_spike"},
                )
            )

        logger.info(
            "Generated VIX spike: base_vix=%.0f spike_to=%.0f "
            "duration=%dmin ticks=%d",
            base_vix,
            spike_to,
            spike_minutes,
            len(ticks),
        )
        return ticks

    def generate_pin_to_strike(
        self,
        base_spx: float = 6000.0,
        pin_strike: float = 6000.0,
        start_time: str = "14:00",
    ) -> list[dict]:
        """Generate a pin-to-strike scenario.

        Models a session where SPX is pulled toward a high-OI strike in the
        final hours as dealer gamma hedging creates a magnetic effect.

        Parameters
        ----------
        base_spx : float
            SPX price at the start of the session.
        pin_strike : float
            Strike price acting as a magnet.
        start_time : str
            Time (HH:MM) at which the pinning effect begins.

        Returns
        -------
        list[dict]
            Synthetic tick sequence.
        """
        times = self._session_tick_times()
        parts = start_time.split(":")
        pin_start = time(int(parts[0]), int(parts[1]))
        pin_start_sec = _time_to_seconds(pin_start)

        # Morning: normal drift potentially away from pin
        morning_drift = float(self._rng.choice([-8, -5, -3, 3, 5, 8]))

        ticks: list[dict] = []
        for t in times:
            t_sec = _time_to_seconds(t)

            if t_sec < pin_start_sec:
                # Pre-pin: normal drift
                morning_frac = (
                    t_sec - _time_to_seconds(self._session_start)
                ) / max(
                    1,
                    pin_start_sec - _time_to_seconds(self._session_start),
                )
                noise = float(self._rng.normal(0, 0.6))
                spx = base_spx + morning_drift * morning_frac + noise

            else:
                # Pinning: mean-revert to pin_strike with increasing strength
                total_pin_sec = (
                    _time_to_seconds(self._session_end) - pin_start_sec
                )
                pin_frac = (t_sec - pin_start_sec) / max(1, total_pin_sec)
                # The further into the session, the stronger the pin
                pin_strength = pin_frac ** 0.5
                current_base = base_spx + morning_drift
                target = pin_strike
                spx = _lerp(current_base, target, pin_strength) + float(
                    self._rng.normal(0, 0.8 * (1 - pin_strength) + 0.1)
                )

            vix = 14.0 + float(self._rng.normal(0, 0.3))
            ticks.append(
                self._make_tick(
                    t,
                    spx,
                    max(10.0, vix),
                    extra={
                        "scenario": "pin_to_strike",
                        "pin_strike": pin_strike,
                    },
                )
            )

        logger.info(
            "Generated pin-to-strike: base=%.0f pin=%.0f "
            "start=%s ticks=%d",
            base_spx,
            pin_strike,
            start_time,
            len(ticks),
        )
        return ticks


# =========================================================================
# 3. SessionRecorder
# =========================================================================


class SessionRecorder:
    """Records live market sessions for later replay.

    Captures market snapshots at regular intervals and persists them to disk
    in JSON (optionally gzip-compressed) or Parquet format for consumption
    by :class:`MarketReplayEngine`.

    Parameters
    ----------
    output_dir : str
        Root directory for session recordings.
    compress : bool
        If ``True``, session files are gzip-compressed (default ``True``).

    Example
    -------
    >>> recorder = SessionRecorder(output_dir="data/replay")
    >>> session_id = recorder.start_recording()
    >>> recorder.record_snapshot(datetime.utcnow(), {"spx_price": 6000.0})
    >>> path = recorder.stop_recording()
    """

    def __init__(
        self,
        output_dir: str = "data/replay",
        compress: bool = True,
    ) -> None:
        self._output_dir = Path(output_dir)
        self._compress = compress

        # Recording state
        self._is_recording: bool = False
        self._session_id: Optional[str] = None
        self._snapshots: list[dict] = []
        self._recording_start: Optional[datetime] = None
        self._recording_end: Optional[datetime] = None

        logger.info(
            "SessionRecorder initialised: output_dir=%s compress=%s",
            self._output_dir,
            self._compress,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_recording(self) -> bool:
        """True when a recording is active."""
        return self._is_recording

    @property
    def session_id(self) -> Optional[str]:
        """ID of the current recording session."""
        return self._session_id

    @property
    def snapshot_count(self) -> int:
        """Number of snapshots captured in the current recording."""
        return len(self._snapshots)

    # ------------------------------------------------------------------
    # Recording lifecycle
    # ------------------------------------------------------------------

    def start_recording(self, session_id: Optional[str] = None) -> str:
        """Begin a new recording session.

        Parameters
        ----------
        session_id : str or None
            Optional session identifier.  If ``None``, a UUID-based ID is
            generated automatically.

        Returns
        -------
        str
            The session identifier.

        Raises
        ------
        RuntimeError
            If a recording is already in progress.
        """
        if self._is_recording:
            raise RuntimeError(
                f"Recording already in progress: {self._session_id}. "
                "Call stop_recording() first."
            )

        self._session_id = session_id or f"session_{uuid.uuid4().hex[:12]}"
        self._snapshots = []
        self._recording_start = datetime.utcnow()
        self._recording_end = None
        self._is_recording = True

        logger.info("Recording started: session_id=%s", self._session_id)
        return self._session_id

    def record_snapshot(self, timestamp: datetime, data: dict) -> None:
        """Record a single market snapshot.

        Parameters
        ----------
        timestamp : datetime
            The timestamp for this snapshot.
        data : dict
            Arbitrary market data to record (SPX price, options chain,
            internals, GEX profile, etc.).

        Raises
        ------
        RuntimeError
            If no recording is currently active.
        """
        if not self._is_recording:
            raise RuntimeError(
                "No active recording. Call start_recording() first."
            )

        snapshot = {
            "timestamp": timestamp.isoformat(),
            **data,
        }
        self._snapshots.append(snapshot)

        if len(self._snapshots) % 100 == 0:
            logger.debug(
                "Recording %s: %d snapshots captured",
                self._session_id,
                len(self._snapshots),
            )

    def stop_recording(self) -> str:
        """Stop the current recording and persist to disk.

        Returns
        -------
        str
            Absolute path to the saved session file.

        Raises
        ------
        RuntimeError
            If no recording is currently active.
        """
        if not self._is_recording:
            raise RuntimeError("No active recording to stop.")

        self._recording_end = datetime.utcnow()
        self._is_recording = False

        # Determine output path
        session_date = self._recording_start.date() if self._recording_start else date.today()
        session_dir = self._output_dir / session_date.isoformat()
        session_dir.mkdir(parents=True, exist_ok=True)

        payload = {
            "session_id": self._session_id,
            "recording_start": (
                self._recording_start.isoformat()
                if self._recording_start
                else None
            ),
            "recording_end": self._recording_end.isoformat(),
            "tick_count": len(self._snapshots),
            "ticks": self._snapshots,
        }

        if self._compress:
            file_path = session_dir / f"{self._session_id}.json.gz"
            with gzip.open(file_path, "wt", encoding="utf-8") as fh:
                json.dump(payload, fh, default=str)
        else:
            file_path = session_dir / f"{self._session_id}.json"
            with open(file_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, default=str)

        logger.info(
            "Recording stopped: session_id=%s snapshots=%d path=%s",
            self._session_id,
            len(self._snapshots),
            file_path,
        )
        return str(file_path.resolve())

    def export_session(
        self,
        session_id: str,
        format: str = "parquet",
    ) -> str:
        """Export a previously recorded session in the specified format.

        Parameters
        ----------
        session_id : str
            Session identifier to export.
        format : str
            Output format: ``"parquet"`` (default) or ``"csv"``.

        Returns
        -------
        str
            Absolute path to the exported file.

        Raises
        ------
        FileNotFoundError
            If the session data cannot be found.
        ValueError
            If an unsupported format is requested.
        """
        if format not in ("parquet", "csv"):
            raise ValueError(
                f"Unsupported export format: {format!r}. "
                "Use 'parquet' or 'csv'."
            )

        # Locate the session file
        source_path = self._find_session_file(session_id)
        if source_path is None:
            raise FileNotFoundError(
                f"Session file not found for session_id={session_id!r}"
            )

        # Read session data
        raw = MarketReplayEngine._read_file(source_path)
        ticks = raw.get("ticks", raw) if isinstance(raw, dict) else raw

        # Build DataFrame
        rows: list[dict] = []
        for tick in ticks:
            flat: dict[str, Any] = {"timestamp": tick.get("timestamp")}
            flat["spx_price"] = tick.get(
                "spx_price", tick.get("underlying_price")
            )
            flat["es_price"] = tick.get("es_price")

            # Flatten cross-asset
            cross = tick.get("cross_asset", tick.get("cross_asset_data", {}))
            if isinstance(cross, dict):
                for k, v in cross.items():
                    flat[f"cross_{k}"] = v

            # Flatten internals
            internals = tick.get(
                "internals", tick.get("market_internals", {})
            )
            if isinstance(internals, dict):
                for k, v in internals.items():
                    flat[f"internals_{k}"] = v

            rows.append(flat)

        df = pd.DataFrame(rows)

        # Write to requested format
        export_dir = self._output_dir / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)

        if format == "parquet":
            out_path = export_dir / f"{session_id}.parquet"
            df.to_parquet(out_path, index=False, engine="pyarrow")
        else:
            out_path = export_dir / f"{session_id}.csv"
            df.to_csv(out_path, index=False)

        logger.info(
            "Exported session %s as %s: %s (%d rows)",
            session_id,
            format,
            out_path,
            len(df),
        )
        return str(out_path.resolve())

    def _find_session_file(self, session_id: str) -> Optional[Path]:
        """Search for a session file by session_id across all date directories."""
        if not self._output_dir.exists():
            return None

        # Search date subdirectories
        for date_dir in sorted(self._output_dir.iterdir()):
            if not date_dir.is_dir():
                continue
            for suffix in (".json.gz", ".json"):
                candidate = date_dir / f"{session_id}{suffix}"
                if candidate.exists():
                    return candidate

        # Search root directory (consolidated files)
        for suffix in (".json.gz", ".json"):
            candidate = self._output_dir / f"{session_id}{suffix}"
            if candidate.exists():
                return candidate

        return None


# =========================================================================
# 4. ReplayAnalyzer
# =========================================================================


class ReplayAnalyzer:
    """Analyse replay sessions for pattern discovery.

    Scans across multiple historical sessions to identify recurring patterns
    such as gamma squeezes, VIX spikes, gamma flips, and time-zone-specific
    behaviour.  Uses :class:`MarketReplayEngine` internally to load and
    iterate over session data.

    Parameters
    ----------
    data_dir : str
        Root directory containing replay session data.

    Example
    -------
    >>> analyzer = ReplayAnalyzer(data_dir="data/replay")
    >>> squeezes = analyzer.find_gamma_squeeze_instances(
    ...     [date(2025, 1, 6), date(2025, 1, 7)]
    ... )
    """

    def __init__(self, data_dir: str = "data/replay") -> None:
        self._data_dir = data_dir
        self._engine = MarketReplayEngine(data_dir=data_dir, playback_speed=0)
        logger.info("ReplayAnalyzer initialised: data_dir=%s", data_dir)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_session_prices(
        self, session_date: date
    ) -> list[Tuple[datetime, float]]:
        """Load SPX price series for a session.

        Returns a list of ``(datetime, spx_price)`` tuples.
        """
        if not self._engine.load_session(session_date):
            logger.warning("Could not load session: %s", session_date)
            return []

        prices: list[Tuple[datetime, float]] = []
        for tick in self._engine._ticks:
            tick_dt = tick.get("_parsed_dt")
            spx = tick.get("spx_price", tick.get("underlying_price"))
            if tick_dt is not None and spx is not None:
                prices.append((tick_dt, float(spx)))
        return prices

    def _load_session_vix(
        self, session_date: date
    ) -> list[Tuple[datetime, float]]:
        """Load VIX series for a session."""
        if not self._engine.load_session(session_date):
            return []

        series: list[Tuple[datetime, float]] = []
        for tick in self._engine._ticks:
            tick_dt = tick.get("_parsed_dt")
            cross = tick.get("cross_asset", tick.get("cross_asset_data", {}))
            if isinstance(cross, dict):
                vix = cross.get("vix")
                if tick_dt is not None and vix is not None:
                    series.append((tick_dt, float(vix)))
        return series

    def _load_session_gex(
        self, session_date: date
    ) -> list[Tuple[datetime, dict]]:
        """Load GEX profile series for a session."""
        if not self._engine.load_session(session_date):
            return []

        series: list[Tuple[datetime, dict]] = []
        for tick in self._engine._ticks:
            tick_dt = tick.get("_parsed_dt")
            gex = tick.get("gex_profile", tick.get("gex"))
            if tick_dt is not None and gex is not None and isinstance(gex, dict):
                series.append((tick_dt, gex))
        return series

    @staticmethod
    def _detect_rapid_move(
        prices: list[Tuple[datetime, float]],
        window_minutes: int,
        threshold_points: float,
        direction: str = "up",
    ) -> list[dict]:
        """Detect instances of a rapid price move over a rolling window.

        Parameters
        ----------
        prices : list of (datetime, float)
            Chronological price series.
        window_minutes : int
            Rolling window length in minutes.
        threshold_points : float
            Minimum move (in SPX points) to qualify.
        direction : str
            ``"up"`` for positive moves, ``"down"`` for negative.

        Returns
        -------
        list[dict]
            Detected instances with start/end times and magnitude.
        """
        if not prices:
            return []

        instances: list[dict] = []
        n = len(prices)
        window_td = timedelta(minutes=window_minutes)

        j = 0
        for i in range(n):
            while j < n - 1 and (prices[j + 1][0] - prices[i][0]) <= window_td:
                j += 1

            move = prices[j][1] - prices[i][1]

            if direction == "up" and move >= threshold_points:
                instances.append({
                    "start_time": prices[i][0].isoformat(),
                    "end_time": prices[j][0].isoformat(),
                    "start_price": prices[i][1],
                    "end_price": prices[j][1],
                    "move_points": round(move, 2),
                    "duration_minutes": (
                        prices[j][0] - prices[i][0]
                    ).total_seconds() / 60.0,
                })
            elif direction == "down" and move <= -threshold_points:
                instances.append({
                    "start_time": prices[i][0].isoformat(),
                    "end_time": prices[j][0].isoformat(),
                    "start_price": prices[i][1],
                    "end_price": prices[j][1],
                    "move_points": round(move, 2),
                    "duration_minutes": (
                        prices[j][0] - prices[i][0]
                    ).total_seconds() / 60.0,
                })

        # De-duplicate overlapping instances: keep the largest move
        if not instances:
            return instances

        deduped: list[dict] = [instances[0]]
        for inst in instances[1:]:
            prev = deduped[-1]
            if inst["start_time"] <= prev["end_time"]:
                # Overlapping -- keep the one with the larger move
                if abs(inst["move_points"]) > abs(prev["move_points"]):
                    deduped[-1] = inst
            else:
                deduped.append(inst)

        return deduped

    # ------------------------------------------------------------------
    # Pattern finders
    # ------------------------------------------------------------------

    def find_gamma_squeeze_instances(
        self, sessions: list[date]
    ) -> list[dict]:
        """Find gamma squeeze instances across multiple sessions.

        A gamma squeeze is defined as a rapid upward move of 20+ SPX points
        in under 30 minutes, typically occurring in the afternoon when dealer
        gamma hedging becomes self-reinforcing.

        Parameters
        ----------
        sessions : list[date]
            Trading dates to search.

        Returns
        -------
        list[dict]
            Detected squeeze instances, each containing:
            - ``date``             : str
            - ``start_time``       : str
            - ``end_time``         : str
            - ``start_price``      : float
            - ``end_price``        : float
            - ``move_points``      : float
            - ``duration_minutes`` : float
        """
        all_instances: list[dict] = []

        for session_date in sessions:
            prices = self._load_session_prices(session_date)
            if not prices:
                continue

            # Filter to afternoon (gamma squeezes most common 13:30-16:00)
            afternoon_prices = [
                (dt, p)
                for dt, p in prices
                if dt.time() >= time(13, 30)
            ]

            instances = self._detect_rapid_move(
                afternoon_prices,
                window_minutes=30,
                threshold_points=20.0,
                direction="up",
            )
            for inst in instances:
                inst["date"] = session_date.isoformat()
            all_instances.extend(instances)

        logger.info(
            "Found %d gamma squeeze instances across %d sessions",
            len(all_instances),
            len(sessions),
        )
        return all_instances

    def find_vix_spike_instances(
        self,
        sessions: list[date],
        threshold: float = 20.0,
    ) -> list[dict]:
        """Find VIX spike instances across multiple sessions.

        A VIX spike is defined as a rise exceeding *threshold* percent
        from the session's VIX low within a 30-minute window.

        Parameters
        ----------
        sessions : list[date]
            Trading dates to search.
        threshold : float
            Minimum VIX percentage increase to qualify as a spike.

        Returns
        -------
        list[dict]
            Detected VIX spike instances.
        """
        all_instances: list[dict] = []

        for session_date in sessions:
            vix_series = self._load_session_vix(session_date)
            if not vix_series:
                continue

            n = len(vix_series)
            window_td = timedelta(minutes=30)

            j = 0
            session_instances: list[dict] = []
            for i in range(n):
                while (
                    j < n - 1
                    and (vix_series[j + 1][0] - vix_series[i][0]) <= window_td
                ):
                    j += 1

                vix_start = vix_series[i][1]
                vix_end = vix_series[j][1]

                if vix_start > _EPSILON:
                    pct_change = ((vix_end - vix_start) / vix_start) * 100.0
                    if pct_change >= threshold:
                        session_instances.append({
                            "date": session_date.isoformat(),
                            "start_time": vix_series[i][0].isoformat(),
                            "end_time": vix_series[j][0].isoformat(),
                            "vix_start": round(vix_start, 2),
                            "vix_peak": round(vix_end, 2),
                            "pct_change": round(pct_change, 2),
                            "duration_minutes": (
                                vix_series[j][0] - vix_series[i][0]
                            ).total_seconds() / 60.0,
                        })

            # De-duplicate overlapping spikes
            if session_instances:
                deduped = [session_instances[0]]
                for inst in session_instances[1:]:
                    if inst["start_time"] <= deduped[-1]["end_time"]:
                        if inst["pct_change"] > deduped[-1]["pct_change"]:
                            deduped[-1] = inst
                    else:
                        deduped.append(inst)
                all_instances.extend(deduped)

        logger.info(
            "Found %d VIX spike instances (>%.0f%%) across %d sessions",
            len(all_instances),
            threshold,
            len(sessions),
        )
        return all_instances

    def find_gamma_flip_instances(
        self, sessions: list[date]
    ) -> list[dict]:
        """Find gamma flip (sign change) instances across sessions.

        A gamma flip occurs when the aggregate dealer gamma exposure
        transitions from positive to negative (or vice versa), as indicated
        by the ``total_net_gex`` field crossing zero.

        Parameters
        ----------
        sessions : list[date]
            Trading dates to search.

        Returns
        -------
        list[dict]
            Detected gamma flip instances.
        """
        all_instances: list[dict] = []

        for session_date in sessions:
            gex_series = self._load_session_gex(session_date)
            if len(gex_series) < 2:
                continue

            prev_dt, prev_gex = gex_series[0]
            prev_net = prev_gex.get("total_net_gex", 0.0)

            for curr_dt, curr_gex in gex_series[1:]:
                curr_net = curr_gex.get("total_net_gex", 0.0)

                if prev_net * curr_net < 0:
                    # Sign changed
                    flip_direction = (
                        "positive_to_negative"
                        if prev_net > 0
                        else "negative_to_positive"
                    )
                    spx_at_flip = curr_gex.get(
                        "gamma_flip_level",
                        curr_gex.get("spx_price"),
                    )
                    all_instances.append({
                        "date": session_date.isoformat(),
                        "timestamp": curr_dt.isoformat(),
                        "flip_direction": flip_direction,
                        "gex_before": round(prev_net, 2),
                        "gex_after": round(curr_net, 2),
                        "gamma_flip_level": spx_at_flip,
                    })

                prev_dt = curr_dt
                prev_net = curr_net

        logger.info(
            "Found %d gamma flip instances across %d sessions",
            len(all_instances),
            len(sessions),
        )
        return all_instances

    def compute_intraday_patterns(
        self, sessions: list[date]
    ) -> dict:
        """Compute average intraday price patterns across sessions.

        Normalises each session's price path to start at 0 and averages
        across all sessions to reveal systematic intraday behaviour.

        Parameters
        ----------
        sessions : list[date]
            Trading dates to analyse.

        Returns
        -------
        dict
            Dictionary containing:
            - ``avg_path``       : list[dict] -- average normalised path with
              time and mean/std of SPX change
            - ``morning_bias``   : float -- average SPX change 09:30-11:30
            - ``midday_bias``    : float -- average SPX change 11:30-13:30
            - ``afternoon_bias`` : float -- average SPX change 13:30-16:00
            - ``session_count``  : int
        """
        # Collect per-session normalised paths bucketed by minute
        minute_buckets: dict[int, list[float]] = defaultdict(list)
        session_count = 0

        for session_date in sessions:
            prices = self._load_session_prices(session_date)
            if not prices:
                continue

            base_price = prices[0][1]
            session_count += 1

            for dt, price in prices:
                minutes_since_open = int(
                    (dt - dt.replace(hour=9, minute=30, second=0)).total_seconds()
                    / 60
                )
                if 0 <= minutes_since_open <= TRADING_MINUTES_PER_DAY:
                    normalised_change = price - base_price
                    minute_buckets[minutes_since_open].append(normalised_change)

        if session_count == 0:
            return {
                "avg_path": [],
                "morning_bias": 0.0,
                "midday_bias": 0.0,
                "afternoon_bias": 0.0,
                "session_count": 0,
            }

        # Compute average path
        avg_path: list[dict] = []
        for minute in sorted(minute_buckets.keys()):
            values = minute_buckets[minute]
            avg_path.append({
                "minutes_since_open": minute,
                "time": _minutes_to_time(9 * 60 + 30 + minute).isoformat(),
                "mean_change": round(float(np.mean(values)), 3),
                "std_change": round(float(np.std(values)), 3),
                "sample_count": len(values),
            })

        # Compute period biases
        morning_vals = [
            v
            for m, vals in minute_buckets.items()
            if 0 <= m <= 120
            for v in vals
        ]
        midday_vals = [
            v
            for m, vals in minute_buckets.items()
            if 120 < m <= 240
            for v in vals
        ]
        afternoon_vals = [
            v
            for m, vals in minute_buckets.items()
            if 240 < m <= TRADING_MINUTES_PER_DAY
            for v in vals
        ]

        return {
            "avg_path": avg_path,
            "morning_bias": round(
                float(np.mean(morning_vals)) if morning_vals else 0.0, 3
            ),
            "midday_bias": round(
                float(np.mean(midday_vals)) if midday_vals else 0.0, 3
            ),
            "afternoon_bias": round(
                float(np.mean(afternoon_vals)) if afternoon_vals else 0.0, 3
            ),
            "session_count": session_count,
        }

    def compute_time_zone_statistics(
        self, sessions: list[date]
    ) -> dict:
        """Compute statistics by intraday time zone across sessions.

        For each time zone (Opening Auction, Morning Session, etc.), computes
        average price change, volatility, and directional bias.

        Parameters
        ----------
        sessions : list[date]
            Trading dates to analyse.

        Returns
        -------
        dict
            Keyed by ``TimeZoneType`` value, each containing:
            - ``avg_move``     : float -- average SPX point change
            - ``avg_volatility`` : float -- standard deviation of per-tick returns
            - ``up_pct``       : float -- percentage of ticks with positive change
            - ``down_pct``     : float -- percentage of ticks with negative change
            - ``avg_range``    : float -- average high-low range within the zone
            - ``tick_count``   : int   -- total ticks observed
        """
        zone_data: dict[str, dict[str, list[float]]] = {}
        for tz in TimeZoneType:
            zone_data[tz.value] = {
                "moves": [],
                "returns": [],
                "ranges_high": [],
                "ranges_low": [],
            }

        for session_date in sessions:
            prices = self._load_session_prices(session_date)
            if len(prices) < 2:
                continue

            # Group prices by time zone
            zone_prices: dict[str, list[float]] = defaultdict(list)
            for dt, price in prices:
                zone = _get_time_zone_for(dt.time()).value
                zone_prices[zone].append(price)

            # Compute per-zone statistics for this session
            for zone_name, price_list in zone_prices.items():
                if len(price_list) < 2:
                    continue
                move = price_list[-1] - price_list[0]
                zone_data[zone_name]["moves"].append(move)
                zone_data[zone_name]["ranges_high"].append(max(price_list))
                zone_data[zone_name]["ranges_low"].append(min(price_list))

                # Per-tick returns
                for k in range(1, len(price_list)):
                    ret = price_list[k] - price_list[k - 1]
                    zone_data[zone_name]["returns"].append(ret)

        # Aggregate
        result: dict[str, dict[str, Any]] = {}
        for zone_name, data in zone_data.items():
            moves = data["moves"]
            returns = data["returns"]
            highs = data["ranges_high"]
            lows = data["ranges_low"]

            n_returns = len(returns)
            up_count = sum(1 for r in returns if r > 0)
            down_count = sum(1 for r in returns if r < 0)

            avg_range = 0.0
            if highs and lows:
                ranges = [h - l for h, l in zip(highs, lows)]
                avg_range = float(np.mean(ranges))

            result[zone_name] = {
                "avg_move": round(float(np.mean(moves)), 3) if moves else 0.0,
                "avg_volatility": (
                    round(float(np.std(returns)), 3) if returns else 0.0
                ),
                "up_pct": round(
                    (up_count / n_returns * 100.0) if n_returns else 0.0, 1
                ),
                "down_pct": round(
                    (down_count / n_returns * 100.0) if n_returns else 0.0, 1
                ),
                "avg_range": round(avg_range, 3),
                "tick_count": n_returns,
            }

        logger.info(
            "Computed time zone statistics across %d sessions", len(sessions)
        )
        return result


# ---------------------------------------------------------------------------
# Module-level exports
# ---------------------------------------------------------------------------

__all__: list[str] = [
    "MarketReplayEngine",
    "ScenarioGenerator",
    "SessionRecorder",
    "ReplayAnalyzer",
]
