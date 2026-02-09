"""
SCANIFY Trade Logger & Self-Learning Calibration Engine

Implements:
  - Trade logging with JSONL persistence
  - Daily scorecard generation with full metric breakdowns
  - Factor weight optimization via correlation-based EMA updates
  - Entry threshold optimization by maximizing expected value
  - Profit target tuning per time zone
  - GEX accuracy tracking
  - Regime change detection using CUSUM tests
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple
import json
import math
import os
import numpy as np

from .config import (
    CalibrationConfig, ScanifyConfig, ScanType, ExitReason,
    SessionType, TimeZone, SignalDirection
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class TradeRecord:
    """Complete record for a single 0DTE SPX trade.

    Captures entry/exit details, market context at entry, Greek exposures,
    market-internal readings, and post-hoc optimal-exit analysis used by
    the calibration engine.
    """

    # Identification
    trade_id: str = ""
    timestamp_entry: str = ""          # ISO-8601
    timestamp_exit: str = ""           # ISO-8601

    # Trade classification
    scan_type: str = ""                # ScanType value
    direction: str = ""                # SignalDirection value
    strike: float = 0.0
    option_type: str = ""              # 'call' or 'put'

    # Price and P&L
    entry_price: float = 0.0
    exit_price: float = 0.0
    max_gain_during_trade: float = 0.0
    max_loss_during_trade: float = 0.0
    pnl_dollars: float = 0.0
    pnl_percent: float = 0.0
    hold_time_minutes: float = 0.0

    # Market context at entry
    spx_at_entry: float = 0.0
    vix1d_at_entry: float = 0.0
    vix_at_entry: float = 0.0
    expected_move_1sigma: float = 0.0
    composite_direction_score: float = 0.0
    session_type: str = ""             # SessionType value
    net_gex_at_entry: float = 0.0
    gamma_flip_at_entry: float = 0.0
    time_zone: str = ""                # TimeZone value

    # Greeks at entry
    delta_at_entry: float = 0.0
    gamma_at_entry: float = 0.0
    theta_at_entry: float = 0.0
    iv_at_entry: float = 0.0

    # Market internals at entry
    tick_10min_avg: float = 0.0
    trin_at_entry: float = 0.0
    ad_ratio_at_entry: float = 0.0
    cumulative_delta_es: float = 0.0

    # Exit analysis
    exit_reason: str = ""              # ExitReason value
    optimal_exit_price: float = 0.0
    optimal_exit_time: str = ""        # ISO-8601
    left_on_table_pct: float = 0.0
    was_stopped_prematurely: bool = False


@dataclass
class DailyScoreCard:
    """Aggregated daily performance metrics across all trades.

    Breakdowns by scan type, time zone, session type, and VIX regime allow
    the calibration engine to pinpoint exactly where the system is strong
    or weak.
    """

    date: str = ""
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    avg_pnl_per_trade: float = 0.0
    max_win: float = 0.0
    max_loss: float = 0.0

    # Dimensional breakdowns
    by_scan_type: Dict[str, Dict] = field(default_factory=dict)
    by_time_zone: Dict[str, Dict] = field(default_factory=dict)
    by_session_type: Dict[str, Dict] = field(default_factory=dict)
    by_vix_regime: Dict[str, Dict] = field(default_factory=dict)

    # Risk-adjusted metrics
    sharpe_estimate: float = 0.0
    max_drawdown: float = 0.0


@dataclass
class CalibrationResult:
    """Output of a single calibration run.

    Contains every parameter update produced by the calibration engine
    together with diagnostic metadata (GEX accuracy, regime detection,
    human-readable notes).
    """

    timestamp: str = ""
    updated_weights: Dict[str, float] = field(default_factory=dict)
    updated_thresholds: Dict[str, float] = field(default_factory=dict)
    updated_profit_targets: Dict[str, float] = field(default_factory=dict)
    gex_accuracy: float = 0.0
    regime_detected: Optional[str] = None
    notes: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# TradeLogger — persistence layer
# ---------------------------------------------------------------------------

class TradeLogger:
    """Manages trade record persistence via in-memory cache + JSONL file.

    Parameters
    ----------
    config : ScanifyConfig
        Master configuration; ``config.trade_log_path`` determines where
        the JSONL file is written.
    """

    def __init__(self, config: ScanifyConfig) -> None:
        self._config = config
        self._trades: List[TradeRecord] = []
        self._filepath: str = config.trade_log_path

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log_trade(self, record: TradeRecord) -> None:
        """Append a trade to the in-memory list and persist to JSONL.

        Parameters
        ----------
        record : TradeRecord
            Fully populated trade record to log.
        """
        self._trades.append(record)
        self._append_to_file(record)

    def load_history(self, filepath: str) -> List[TradeRecord]:
        """Load trade records from a JSONL file.

        Each line in the file must be a valid JSON object whose keys
        match the ``TradeRecord`` field names.

        Parameters
        ----------
        filepath : str
            Path to a ``.jsonl`` file containing one trade per line.

        Returns
        -------
        List[TradeRecord]
            Deserialized trade records.
        """
        records: List[TradeRecord] = []
        if not os.path.isfile(filepath):
            return records
        with open(filepath, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                records.append(TradeRecord(**data))
        self._trades = records
        return records

    def get_trades(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        scan_type: Optional[str] = None,
    ) -> List[TradeRecord]:
        """Filter trades by date range and/or scan type.

        Parameters
        ----------
        start_date : str, optional
            Inclusive lower bound in ``YYYY-MM-DD`` format.
        end_date : str, optional
            Inclusive upper bound in ``YYYY-MM-DD`` format.
        scan_type : str, optional
            Only return trades matching this scan type value.

        Returns
        -------
        List[TradeRecord]
            Filtered subset of stored trades.
        """
        filtered = self._trades

        if start_date is not None:
            filtered = [
                t for t in filtered
                if t.timestamp_entry[:10] >= start_date
            ]

        if end_date is not None:
            filtered = [
                t for t in filtered
                if t.timestamp_entry[:10] <= end_date
            ]

        if scan_type is not None:
            filtered = [
                t for t in filtered
                if t.scan_type == scan_type
            ]

        return filtered

    def get_trade_count(self) -> int:
        """Return the number of trades currently stored in memory.

        Returns
        -------
        int
            Total trade count.
        """
        return len(self._trades)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _append_to_file(self, record: TradeRecord) -> None:
        """Serialize a single record to JSONL and append to disk."""
        dirpath = os.path.dirname(self._filepath)
        if dirpath and not os.path.isdir(dirpath):
            os.makedirs(dirpath, exist_ok=True)
        with open(self._filepath, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(record)) + "\n")


# ---------------------------------------------------------------------------
# CalibrationEngine — self-learning parameter tuning
# ---------------------------------------------------------------------------

class CalibrationEngine:
    """Nightly calibration engine for SCANIFY parameter optimization.

    Implements a conservative EMA-based update scheme so that parameter
    drift is gradual and reversible.  All optimizations require a minimum
    trade count before they take effect.

    Parameters
    ----------
    config : ScanifyConfig
        Master configuration providing calibration hyper-parameters and
        current factor weights / thresholds / targets.
    """

    _VIX_REGIME_BINS: List[Tuple[str, float, float]] = [
        ("low", 0.0, 12.0),
        ("normal", 12.0, 18.0),
        ("elevated", 18.0, 25.0),
        ("high", 25.0, float("inf")),
    ]

    def __init__(self, config: ScanifyConfig) -> None:
        self._config = config
        self._cal = config.calibration

        # Current factor weights keyed by name
        self._current_weights: Dict[str, float] = {
            "market_internals": config.directional.weight_market_internals,
            "options_flow": config.directional.weight_options_flow,
            "price_action": config.directional.weight_price_action,
            "gex_structure": config.directional.weight_gex_structure,
            "cross_asset": config.directional.weight_cross_asset,
        }

        # Current entry thresholds keyed by scan type
        self._current_thresholds: Dict[str, float] = {
            ScanType.DIRECTIONAL.value: config.directional.signal_threshold,
            ScanType.GAMMA_SCALP.value: config.gamma_scalp.min_direction_score,
        }

        # Current profit targets keyed by time zone value
        self._current_targets: Dict[str, float] = {
            TimeZone.MORNING_SESSION.value: config.exit.profit_target_morning[1],
            TimeZone.MIDDAY_LULL.value: config.exit.profit_target_midday[1],
            TimeZone.AFTERNOON_ACCEL.value: config.exit.profit_target_afternoon[1],
            TimeZone.POWER_HOUR.value: config.exit.profit_target_power_hour[1],
        }

    # ------------------------------------------------------------------
    # Daily scorecard
    # ------------------------------------------------------------------

    def generate_daily_scorecard(self, trades: List[TradeRecord]) -> DailyScoreCard:
        """Compute a complete performance scorecard for a list of trades.

        Parameters
        ----------
        trades : List[TradeRecord]
            Trades to evaluate (typically one day's worth).

        Returns
        -------
        DailyScoreCard
            Fully populated scorecard with dimensional breakdowns.
        """
        if not trades:
            return DailyScoreCard()

        pnls = np.array([t.pnl_dollars for t in trades], dtype=np.float64)
        wins = int(np.sum(pnls > 0))
        losses = int(np.sum(pnls <= 0))
        total = len(trades)
        win_rate = wins / total if total > 0 else 0.0

        scorecard = DailyScoreCard(
            date=trades[0].timestamp_entry[:10],
            total_trades=total,
            wins=wins,
            losses=losses,
            win_rate=win_rate,
            total_pnl=float(np.sum(pnls)),
            avg_pnl_per_trade=float(np.mean(pnls)),
            max_win=float(np.max(pnls)) if total > 0 else 0.0,
            max_loss=float(np.min(pnls)) if total > 0 else 0.0,
            by_scan_type=self._breakdown(trades, key_fn=lambda t: t.scan_type),
            by_time_zone=self._breakdown(trades, key_fn=lambda t: t.time_zone),
            by_session_type=self._breakdown(trades, key_fn=lambda t: t.session_type),
            by_vix_regime=self._breakdown(trades, key_fn=lambda t: self._vix_regime(t.vix_at_entry)),
            sharpe_estimate=self._sharpe(pnls),
            max_drawdown=self._max_drawdown(pnls),
        )
        return scorecard

    # ------------------------------------------------------------------
    # Factor weight optimization
    # ------------------------------------------------------------------

    def optimize_factor_weights(
        self,
        trades: List[TradeRecord],
        current_weights: Dict[str, float],
    ) -> Dict[str, float]:
        """Optimize composite factor weights using correlation feedback.

        For each factor the method computes the Pearson correlation between
        the factor's contribution score proxy and the trade P&L.  The
        ``optimal`` weight is proportional to ``max(corr, 0)``.  The actual
        update blends old and optimal via an EMA controlled by
        ``CalibrationConfig.weight_ema_alpha``.

        Parameters
        ----------
        trades : List[TradeRecord]
            Recent trade history.
        current_weights : Dict[str, float]
            Current factor weights keyed by factor name.

        Returns
        -------
        Dict[str, float]
            Updated (and re-normalised) factor weights.
        """
        if len(trades) < 10:
            return dict(current_weights)

        alpha = self._cal.weight_ema_alpha
        w_min = self._cal.min_single_factor_weight
        w_max = self._cal.max_single_factor_weight

        pnls = np.array([t.pnl_dollars for t in trades], dtype=np.float64)

        # Build proxy factor-score arrays from trade context fields.
        factor_arrays: Dict[str, np.ndarray] = {
            "market_internals": np.array(
                [t.tick_10min_avg for t in trades], dtype=np.float64
            ),
            "options_flow": np.array(
                [t.iv_at_entry for t in trades], dtype=np.float64
            ),
            "price_action": np.array(
                [t.composite_direction_score for t in trades], dtype=np.float64
            ),
            "gex_structure": np.array(
                [t.net_gex_at_entry for t in trades], dtype=np.float64
            ),
            "cross_asset": np.array(
                [t.ad_ratio_at_entry for t in trades], dtype=np.float64
            ),
        }

        # Compute correlations
        correlations: Dict[str, float] = {}
        for name, arr in factor_arrays.items():
            std_f = float(np.std(arr))
            std_p = float(np.std(pnls))
            if std_f < 1e-12 or std_p < 1e-12:
                correlations[name] = 0.0
            else:
                corr = float(np.corrcoef(arr, pnls)[0, 1])
                correlations[name] = corr if not math.isnan(corr) else 0.0

        # Derive optimal proportional weights from positive correlations
        positive_corrs = {k: max(v, 0.0) for k, v in correlations.items()}
        total_corr = sum(positive_corrs.values())
        if total_corr < 1e-12:
            optimal_weights = {k: 1.0 / len(current_weights) for k in current_weights}
        else:
            optimal_weights = {k: v / total_corr for k, v in positive_corrs.items()}

        # EMA blend
        new_weights: Dict[str, float] = {}
        for name in current_weights:
            old = current_weights.get(name, 1.0 / len(current_weights))
            opt = optimal_weights.get(name, old)
            blended = (1.0 - alpha) * old + alpha * opt
            blended = max(w_min, min(w_max, blended))
            new_weights[name] = blended

        # Re-normalise to sum to 1.0
        total_w = sum(new_weights.values())
        if total_w > 0:
            new_weights = {k: v / total_w for k, v in new_weights.items()}

        return new_weights

    # ------------------------------------------------------------------
    # Entry threshold optimization
    # ------------------------------------------------------------------

    def optimize_entry_threshold(
        self,
        trades: List[TradeRecord],
        current_threshold: float,
    ) -> float:
        """Find the entry composite-score threshold that maximises E[V].

        E[V](t) = win_rate(t) * avg_win(t)  -  loss_rate(t) * avg_loss(t)

        Thresholds from 30 to 70 (step 2) are evaluated.  The optimum is
        blended toward the current threshold with a hard cap of +/-2 points
        per calibration run to prevent instability.

        Parameters
        ----------
        trades : List[TradeRecord]
            Recent trade history with ``composite_direction_score`` populated.
        current_threshold : float
            The current entry threshold.

        Returns
        -------
        float
            Updated threshold clamped within +/-2 of the current value.
        """
        if len(trades) < 20:
            return current_threshold

        scores = np.array(
            [t.composite_direction_score for t in trades], dtype=np.float64
        )
        pnls = np.array([t.pnl_dollars for t in trades], dtype=np.float64)

        best_ev = -np.inf
        best_threshold = current_threshold

        for threshold in np.arange(30.0, 72.0, 2.0):
            mask = scores >= threshold
            if np.sum(mask) < 5:
                continue

            subset = pnls[mask]
            wins_arr = subset[subset > 0]
            losses_arr = subset[subset <= 0]

            wr = len(wins_arr) / len(subset)
            avg_win = float(np.mean(wins_arr)) if len(wins_arr) > 0 else 0.0
            avg_loss = float(np.mean(np.abs(losses_arr))) if len(losses_arr) > 0 else 0.0

            ev = wr * avg_win - (1.0 - wr) * avg_loss
            if ev > best_ev:
                best_ev = ev
                best_threshold = float(threshold)

        # Clamp adjustment to +/-2 points
        delta = best_threshold - current_threshold
        delta = max(-2.0, min(2.0, delta))
        return current_threshold + delta

    # ------------------------------------------------------------------
    # Profit target optimization
    # ------------------------------------------------------------------

    def optimize_profit_targets(
        self,
        trades: List[TradeRecord],
    ) -> Dict[str, float]:
        """Optimize profit-take targets per time zone.

        For each time zone with sufficient trades the method uses
        ``left_on_table_pct`` and ``was_stopped_prematurely`` to estimate
        where the profit target should be adjusted.  When a large fraction
        of trades was stopped prematurely the target is nudged down; when
        substantial profit was systematically left on the table the target
        is nudged up.

        Parameters
        ----------
        trades : List[TradeRecord]
            Recent trade history.

        Returns
        -------
        Dict[str, float]
            Updated profit target (as a multiplier) keyed by time-zone
            value string.
        """
        updated = dict(self._current_targets)
        adjust_rate = self._cal.target_adjust_rate

        # Group trades by time zone
        by_tz: Dict[str, List[TradeRecord]] = {}
        for t in trades:
            by_tz.setdefault(t.time_zone, []).append(t)

        for tz, tz_trades in by_tz.items():
            if len(tz_trades) < 10 or tz not in updated:
                continue

            left_arr = np.array(
                [t.left_on_table_pct for t in tz_trades], dtype=np.float64
            )
            premature_rate = np.mean(
                [1.0 if t.was_stopped_prematurely else 0.0 for t in tz_trades]
            )

            avg_left = float(np.mean(left_arr))
            current_target = updated[tz]

            # If most trades leave money on the table -> raise target
            if avg_left > 0.15:
                nudge = current_target * adjust_rate
                updated[tz] = current_target + nudge
            # If many trades are stopped prematurely -> lower target
            elif premature_rate > 0.40:
                nudge = current_target * adjust_rate
                updated[tz] = current_target - nudge

        return updated

    # ------------------------------------------------------------------
    # GEX accuracy tracking
    # ------------------------------------------------------------------

    def calibrate_gex_accuracy(self, trades: List[TradeRecord]) -> float:
        """Compute GEX directional-prediction accuracy over a rolling window.

        A trade is considered a correct GEX prediction when the sign of
        ``net_gex_at_entry`` (positive = bullish dealer gamma, negative =
        bearish) aligns with the trade direction *and* the trade was
        profitable, OR when it opposes the direction and the trade was
        unprofitable.

        Parameters
        ----------
        trades : List[TradeRecord]
            Recent trade history (ideally the rolling window worth).

        Returns
        -------
        float
            Accuracy in [0, 1].
        """
        if not trades:
            return 0.0

        window = self._cal.gex_accuracy_window_days
        # Take only the most recent window-days of trades
        cutoff = _date_n_days_ago(window)
        recent = [
            t for t in trades
            if t.timestamp_entry[:10] >= cutoff
        ]

        if not recent:
            return 0.0

        correct = 0
        total = 0
        for t in recent:
            if abs(t.net_gex_at_entry) < 1e-12:
                continue
            gex_bullish = t.net_gex_at_entry > 0
            trade_bullish = t.direction == SignalDirection.BULLISH.value
            profitable = t.pnl_dollars > 0

            prediction_aligned = gex_bullish == trade_bullish
            if (prediction_aligned and profitable) or (
                not prediction_aligned and not profitable
            ):
                correct += 1
            total += 1

        return correct / total if total > 0 else 0.0

    # ------------------------------------------------------------------
    # Regime change detection (CUSUM)
    # ------------------------------------------------------------------

    def detect_regime_change(
        self,
        trades: List[TradeRecord],
        lookback: int = 0,
    ) -> Optional[str]:
        """Detect structural regime changes via a two-sided CUSUM test.

        The method monitors both rolling win-rate and average P&L.  A
        cumulative-sum statistic is maintained and a regime change is
        flagged when the statistic exceeds a threshold derived from the
        standard deviation of the observations.

        Parameters
        ----------
        trades : List[TradeRecord]
            Full trade history (or at least several weeks).
        lookback : int, optional
            Number of most-recent trades to consider.  ``0`` means use
            ``CalibrationConfig.regime_lookback_days`` worth of trades.

        Returns
        -------
        Optional[str]
            Human-readable description of the detected regime change, or
            ``None`` if the market regime appears stable.
        """
        if lookback <= 0:
            lookback_days = self._cal.regime_lookback_days
            cutoff = _date_n_days_ago(lookback_days)
            recent = [t for t in trades if t.timestamp_entry[:10] >= cutoff]
        else:
            recent = trades[-lookback:] if len(trades) >= lookback else list(trades)

        if len(recent) < 20:
            return None

        pnls = np.array([t.pnl_dollars for t in recent], dtype=np.float64)
        win_flags = (pnls > 0).astype(np.float64)

        # --- CUSUM on win rate ---
        mean_wr = float(np.mean(win_flags))
        wr_shift = self._cusum_test(win_flags, mean_wr)

        # --- CUSUM on average P&L (using rolling 5-trade blocks) ---
        block = 5
        if len(pnls) >= block:
            block_means = np.array([
                float(np.mean(pnls[i:i + block]))
                for i in range(0, len(pnls) - block + 1, block)
            ])
            mean_pnl = float(np.mean(block_means))
            pnl_shift = self._cusum_test(block_means, mean_pnl)
        else:
            pnl_shift = None

        # Build description
        messages: List[str] = []
        if wr_shift is not None:
            messages.append(f"Win-rate regime shift detected: {wr_shift}")
        if pnl_shift is not None:
            messages.append(f"P&L regime shift detected: {pnl_shift}")

        return "; ".join(messages) if messages else None

    # ------------------------------------------------------------------
    # Main calibration entry point
    # ------------------------------------------------------------------

    def run_daily_calibration(
        self,
        trades: List[TradeRecord],
    ) -> CalibrationResult:
        """Execute the full daily calibration pipeline.

        Steps
        -----
        1. Generate daily scorecard.
        2. Optimize factor weights.
        3. Optimize entry thresholds for each scan type.
        4. Optimize profit targets per time zone.
        5. Calibrate GEX accuracy.
        6. Detect regime changes.
        7. Package everything into a ``CalibrationResult``.

        Parameters
        ----------
        trades : List[TradeRecord]
            All trades available for calibration (typically the last
            20+ trading days).

        Returns
        -------
        CalibrationResult
            Complete calibration output ready for persistence.
        """
        notes: List[str] = []

        # 1. Scorecard
        scorecard = self.generate_daily_scorecard(trades)
        notes.append(
            f"Scorecard: {scorecard.total_trades} trades, "
            f"win_rate={scorecard.win_rate:.2%}, "
            f"total_pnl=${scorecard.total_pnl:.2f}"
        )

        # 2. Factor weights
        new_weights = self.optimize_factor_weights(trades, self._current_weights)
        self._current_weights = new_weights
        notes.append("Factor weights updated via correlation-EMA blend.")

        # 3. Entry thresholds
        new_thresholds: Dict[str, float] = {}
        for scan_key, current_thresh in self._current_thresholds.items():
            scan_trades = [t for t in trades if t.scan_type == scan_key]
            optimized = self.optimize_entry_threshold(scan_trades, current_thresh)
            new_thresholds[scan_key] = optimized
        self._current_thresholds = new_thresholds
        notes.append("Entry thresholds optimized per scan type.")

        # 4. Profit targets
        new_targets = self.optimize_profit_targets(trades)
        self._current_targets = new_targets
        notes.append("Profit targets recalibrated per time zone.")

        # 5. GEX accuracy
        gex_acc = self.calibrate_gex_accuracy(trades)
        if gex_acc < self._cal.gex_low_accuracy_threshold:
            notes.append(
                f"WARNING: GEX accuracy low ({gex_acc:.2%}). "
                "Consider reducing GEX weight."
            )
        elif gex_acc >= self._cal.gex_high_accuracy_threshold:
            notes.append(f"GEX accuracy strong ({gex_acc:.2%}).")
        else:
            notes.append(f"GEX accuracy acceptable ({gex_acc:.2%}).")

        # 6. Regime detection
        regime = self.detect_regime_change(trades)
        if regime is not None:
            notes.append(f"REGIME CHANGE: {regime}")

        result = CalibrationResult(
            timestamp=datetime.utcnow().isoformat(),
            updated_weights=new_weights,
            updated_thresholds=new_thresholds,
            updated_profit_targets=new_targets,
            gex_accuracy=gex_acc,
            regime_detected=regime,
            notes=notes,
        )
        return result

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_calibration(self, result: CalibrationResult, filepath: str) -> None:
        """Persist a calibration result to a JSON file.

        Parameters
        ----------
        result : CalibrationResult
            The calibration output to save.
        filepath : str
            Destination file path.
        """
        dirpath = os.path.dirname(filepath)
        if dirpath and not os.path.isdir(dirpath):
            os.makedirs(dirpath, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as fh:
            json.dump(asdict(result), fh, indent=2)

    def load_calibration(self, filepath: str) -> Optional[CalibrationResult]:
        """Load a previously persisted calibration result.

        Parameters
        ----------
        filepath : str
            Path to the calibration JSON file.

        Returns
        -------
        Optional[CalibrationResult]
            The loaded calibration, or ``None`` if the file does not exist.
        """
        if not os.path.isfile(filepath):
            return None
        with open(filepath, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return CalibrationResult(**data)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @classmethod
    def _breakdown(
        cls,
        trades: List[TradeRecord],
        key_fn,
    ) -> Dict[str, Dict]:
        """Group trades by an arbitrary key and compute per-group stats.

        Returns a dict mapping each group key to
        ``{"win_rate": float, "avg_pnl": float, "count": int}``.
        """
        groups: Dict[str, List[float]] = {}
        for t in trades:
            key = key_fn(t)
            if not key:
                key = "unknown"
            groups.setdefault(key, []).append(t.pnl_dollars)

        result: Dict[str, Dict] = {}
        for key, pnls_list in groups.items():
            arr = np.array(pnls_list, dtype=np.float64)
            wins = int(np.sum(arr > 0))
            total = len(arr)
            result[key] = {
                "win_rate": wins / total if total > 0 else 0.0,
                "avg_pnl": float(np.mean(arr)) if total > 0 else 0.0,
                "count": total,
            }
        return result

    @classmethod
    def _vix_regime(cls, vix: float) -> str:
        """Classify a VIX reading into a regime bucket."""
        for name, lo, hi in cls._VIX_REGIME_BINS:
            if lo <= vix < hi:
                return name
        return "high"

    @staticmethod
    def _sharpe(pnls: np.ndarray) -> float:
        """Estimate annualised Sharpe ratio from per-trade P&L array.

        Uses ~252 trading days as the annualisation factor.
        """
        if len(pnls) < 2:
            return 0.0
        mean = float(np.mean(pnls))
        std = float(np.std(pnls, ddof=1))
        if std < 1e-12:
            return 0.0
        daily_sharpe = mean / std
        return daily_sharpe * math.sqrt(252)

    @staticmethod
    def _max_drawdown(pnls: np.ndarray) -> float:
        """Compute maximum drawdown from a sequence of P&L values.

        The drawdown is measured from peak cumulative P&L to the
        subsequent trough.

        Returns
        -------
        float
            Maximum drawdown as a non-negative dollar amount.
        """
        if len(pnls) == 0:
            return 0.0
        cum = np.cumsum(pnls)
        running_max = np.maximum.accumulate(cum)
        drawdowns = running_max - cum
        return float(np.max(drawdowns))

    @staticmethod
    def _cusum_test(
        values: np.ndarray,
        target_mean: float,
        threshold_factor: float = 4.0,
    ) -> Optional[str]:
        """Run a two-sided CUSUM test on *values* around *target_mean*.

        Parameters
        ----------
        values : np.ndarray
            Observation sequence.
        target_mean : float
            Expected (in-control) mean.
        threshold_factor : float
            Multiple of standard deviation used as the alarm threshold.

        Returns
        -------
        Optional[str]
            Description of the shift direction (``"upward"`` or
            ``"downward"``), or ``None`` if no shift is detected.
        """
        if len(values) < 5:
            return None
        std = float(np.std(values, ddof=1))
        if std < 1e-12:
            return None

        threshold = threshold_factor * std
        s_pos = 0.0
        s_neg = 0.0

        for v in values:
            diff = float(v) - target_mean
            s_pos = max(0.0, s_pos + diff)
            s_neg = max(0.0, s_neg - diff)

            if s_pos > threshold:
                return "upward"
            if s_neg > threshold:
                return "downward"

        return None


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _date_n_days_ago(n: int) -> str:
    """Return the ISO date string for *n* calendar days before today."""
    from datetime import timedelta
    return (date.today() - timedelta(days=n)).isoformat()
