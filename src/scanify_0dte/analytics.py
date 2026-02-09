"""
SCANIFY SPX 0DTE Options Day Trading Scanner + GEX Scanner -- Analytics Module

Advanced analytics for signal performance tracking, factor analysis, GEX signal
evaluation, risk monitoring, and market microstructure analysis.

Provides five production-grade analytics classes:

  1. SignalAnalytics     -- Rolling win rates, Sharpe/Sortino, profit factor,
                            expectancy, Kelly, streak analysis, time-bucketed PnL.
  2. FactorAnalysis      -- Correlation matrices, information ratios, stability
                            tracking, redundancy detection, decay rates, and
                            optimal weight discovery for the five-factor model.
  3. GEXAnalytics        -- Gamma wall hold rates, flip accuracy, charm flow
                            correlation, regime statistics, transition breakouts.
  4. RiskAnalytics       -- VaR, CVaR, drawdown analysis, Ulcer Index, tail ratio,
                            Omega ratio, correlation breakdown, concentration.
  5. MarketMicrostructureAnalytics -- Spread trends, order-flow toxicity, volume
                            profile, market impact estimation, quote stuffing.

All monetary values are in USD.  All timestamps are timezone-aware or UTC.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from typing import Any, Optional

import numpy as np
from scipy import optimize, stats

from .models import (
    DirectionScore,
    FactorWeights,
    GEXProfile,
    TradeDirection,
    TradeLog,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_ANNUALISATION_FACTOR = math.sqrt(252.0)
_FACTOR_NAMES = (
    "market_internals",
    "options_flow",
    "price_action",
    "gex_structure",
    "cross_asset",
)


def _safe_division(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Return *numerator / denominator* or *default* when denominator is zero."""
    if denominator == 0.0:
        return default
    return numerator / denominator


def _closed_trades(trades: list[TradeLog]) -> list[TradeLog]:
    """Filter to closed trades with non-null PnL."""
    return [t for t in trades if t.pnl_dollars is not None and not t.is_open]


# =============================================================================
# 1. SIGNAL ANALYTICS
# =============================================================================


class SignalAnalytics:
    """Real-time signal performance tracking and analysis.

    Computes rolling and cumulative performance metrics from a sequence of
    closed ``TradeLog`` records.  All rolling methods return a list whose
    length equals the number of closed trades; early values (where the
    window is not yet full) are computed over the available history.
    """

    # --------------------------------------------------------------------- #
    # Rolling metrics
    # --------------------------------------------------------------------- #

    @staticmethod
    def compute_rolling_win_rate(
        trades: list[TradeLog],
        window: int = 50,
    ) -> list[float]:
        """Compute a rolling win-rate over the last *window* closed trades.

        Parameters
        ----------
        trades:
            Ordered list of ``TradeLog`` records (oldest first).
        window:
            Look-back size.  When fewer trades are available, the full
            history is used.

        Returns
        -------
        list[float]
            Rolling win rate (0.0 -- 1.0) aligned 1:1 with *trades*.
        """
        closed = _closed_trades(trades)
        if not closed:
            return []

        wins = np.array([1.0 if t.is_winner else 0.0 for t in closed], dtype=np.float64)
        result: list[float] = []
        for i in range(len(wins)):
            start = max(0, i - window + 1)
            segment = wins[start: i + 1]
            result.append(float(np.mean(segment)))
        return result

    @staticmethod
    def compute_rolling_sharpe(
        daily_pnl: list[float],
        window: int = 20,
    ) -> list[float]:
        """Compute rolling annualised Sharpe ratio over *daily_pnl*.

        Parameters
        ----------
        daily_pnl:
            Daily PnL series (oldest first).
        window:
            Rolling look-back window (trading days).

        Returns
        -------
        list[float]
            Rolling Sharpe ratio aligned with *daily_pnl*.  Returns 0.0
            when the standard deviation in the window is zero.
        """
        arr = np.array(daily_pnl, dtype=np.float64)
        result: list[float] = []
        for i in range(len(arr)):
            start = max(0, i - window + 1)
            segment = arr[start: i + 1]
            if len(segment) < 2:
                result.append(0.0)
                continue
            mu = float(np.mean(segment))
            sigma = float(np.std(segment, ddof=1))
            if sigma == 0.0:
                result.append(0.0)
            else:
                result.append((mu / sigma) * _ANNUALISATION_FACTOR)
        return result

    @staticmethod
    def compute_rolling_sortino(
        daily_pnl: list[float],
        window: int = 20,
    ) -> list[float]:
        """Compute rolling annualised Sortino ratio over *daily_pnl*.

        The Sortino ratio penalises only downside deviation rather than
        total volatility.

        Parameters
        ----------
        daily_pnl:
            Daily PnL series (oldest first).
        window:
            Rolling look-back window (trading days).

        Returns
        -------
        list[float]
            Rolling Sortino ratio aligned with *daily_pnl*.
        """
        arr = np.array(daily_pnl, dtype=np.float64)
        result: list[float] = []
        for i in range(len(arr)):
            start = max(0, i - window + 1)
            segment = arr[start: i + 1]
            if len(segment) < 2:
                result.append(0.0)
                continue
            mu = float(np.mean(segment))
            downside = segment[segment < 0.0]
            if len(downside) < 1:
                # No negative days -- Sortino is effectively infinite; cap it.
                result.append(0.0 if mu <= 0.0 else 99.99)
                continue
            downside_dev = float(np.sqrt(np.mean(downside ** 2)))
            if downside_dev == 0.0:
                result.append(0.0)
            else:
                result.append((mu / downside_dev) * _ANNUALISATION_FACTOR)
        return result

    # --------------------------------------------------------------------- #
    # Aggregate metrics
    # --------------------------------------------------------------------- #

    @staticmethod
    def compute_profit_factor(trades: list[TradeLog]) -> float:
        """Gross profit divided by gross loss.

        Parameters
        ----------
        trades:
            List of ``TradeLog`` records (may include open trades which
            are filtered out).

        Returns
        -------
        float
            Profit factor.  Returns ``float('inf')`` when there are no
            losing trades and there are winners.  Returns 0.0 when there
            are no winning trades.
        """
        closed = _closed_trades(trades)
        gross_profit = sum(t.pnl_dollars for t in closed if t.pnl_dollars > 0)
        gross_loss = abs(sum(t.pnl_dollars for t in closed if t.pnl_dollars < 0))
        if gross_loss == 0.0:
            return float("inf") if gross_profit > 0.0 else 0.0
        return gross_profit / gross_loss

    @staticmethod
    def compute_expectancy(trades: list[TradeLog]) -> float:
        """Expected dollar PnL per trade.

        Expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)

        Parameters
        ----------
        trades:
            List of ``TradeLog`` records.

        Returns
        -------
        float
            Dollar expectancy per trade.
        """
        closed = _closed_trades(trades)
        if not closed:
            return 0.0

        winners = [t.pnl_dollars for t in closed if t.pnl_dollars > 0]
        losers = [abs(t.pnl_dollars) for t in closed if t.pnl_dollars < 0]

        win_rate = len(winners) / len(closed)
        loss_rate = len(losers) / len(closed)
        avg_win = float(np.mean(winners)) if winners else 0.0
        avg_loss = float(np.mean(losers)) if losers else 0.0

        return (win_rate * avg_win) - (loss_rate * avg_loss)

    @staticmethod
    def compute_kelly_criterion(
        win_rate: float,
        avg_win: float,
        avg_loss: float,
    ) -> float:
        """Compute the Kelly Criterion optimal bet fraction.

        Kelly% = W - (1 - W) / R
        where W = win probability, R = avg_win / avg_loss.

        Parameters
        ----------
        win_rate:
            Historical win probability (0.0 -- 1.0).
        avg_win:
            Average winning trade magnitude (positive).
        avg_loss:
            Average losing trade magnitude (positive).

        Returns
        -------
        float
            Optimal fraction of capital to risk.  Clamped to [0.0, 1.0].
            Returns 0.0 when inputs are invalid.
        """
        if avg_loss <= 0.0 or avg_win <= 0.0 or not (0.0 <= win_rate <= 1.0):
            return 0.0
        r = avg_win / avg_loss
        kelly = win_rate - (1.0 - win_rate) / r
        return max(0.0, min(1.0, kelly))

    # --------------------------------------------------------------------- #
    # Streak analysis
    # --------------------------------------------------------------------- #

    @staticmethod
    def compute_max_consecutive_losses(trades: list[TradeLog]) -> int:
        """Maximum number of consecutive losing trades.

        Parameters
        ----------
        trades:
            List of ``TradeLog`` records.

        Returns
        -------
        int
            Longest losing streak.  Returns 0 when there are no closed
            losing trades.
        """
        closed = _closed_trades(trades)
        max_streak = 0
        current_streak = 0
        for t in closed:
            if t.pnl_dollars is not None and t.pnl_dollars < 0:
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 0
        return max_streak

    @staticmethod
    def compute_max_consecutive_wins(trades: list[TradeLog]) -> int:
        """Maximum number of consecutive winning trades.

        Parameters
        ----------
        trades:
            List of ``TradeLog`` records.

        Returns
        -------
        int
            Longest winning streak.  Returns 0 when there are no closed
            winning trades.
        """
        closed = _closed_trades(trades)
        max_streak = 0
        current_streak = 0
        for t in closed:
            if t.pnl_dollars is not None and t.pnl_dollars > 0:
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 0
        return max_streak

    # --------------------------------------------------------------------- #
    # Time-based analysis
    # --------------------------------------------------------------------- #

    @staticmethod
    def compute_avg_hold_time(trades: list[TradeLog]) -> float:
        """Average holding time in minutes across closed trades.

        Uses the ``hold_time_minutes`` field when available; falls back to
        computing the difference between exit and entry timestamps.

        Parameters
        ----------
        trades:
            List of ``TradeLog`` records.

        Returns
        -------
        float
            Average hold time in minutes.  Returns 0.0 when no data is
            available.
        """
        closed = _closed_trades(trades)
        hold_times: list[float] = []
        for t in closed:
            if t.hold_time_minutes is not None:
                hold_times.append(t.hold_time_minutes)
            elif t.timestamp_exit is not None:
                delta = (t.timestamp_exit - t.timestamp_entry).total_seconds() / 60.0
                hold_times.append(delta)
        if not hold_times:
            return 0.0
        return float(np.mean(hold_times))

    @staticmethod
    def compute_pnl_by_hour(trades: list[TradeLog]) -> dict[int, dict[str, float]]:
        """Aggregate PnL statistics bucketed by entry hour (ET).

        Parameters
        ----------
        trades:
            List of ``TradeLog`` records.

        Returns
        -------
        dict[int, dict[str, float]]
            Keyed by hour (9, 10, ..., 15).  Each value contains:

            - ``total_pnl``: sum of PnL for trades entered in that hour.
            - ``avg_pnl``: average PnL per trade.
            - ``trade_count``: number of trades.
            - ``win_rate``: fraction of winning trades.
        """
        closed = _closed_trades(trades)
        buckets: dict[int, list[TradeLog]] = defaultdict(list)
        for t in closed:
            hour = t.timestamp_entry.hour
            buckets[hour].append(t)

        result: dict[int, dict[str, float]] = {}
        for hour in sorted(buckets.keys()):
            bucket = buckets[hour]
            pnls = [t.pnl_dollars for t in bucket if t.pnl_dollars is not None]
            wins = sum(1 for p in pnls if p > 0)
            result[hour] = {
                "total_pnl": float(np.sum(pnls)) if pnls else 0.0,
                "avg_pnl": float(np.mean(pnls)) if pnls else 0.0,
                "trade_count": float(len(bucket)),
                "win_rate": wins / len(pnls) if pnls else 0.0,
            }
        return result

    @staticmethod
    def compute_pnl_by_day_of_week(
        trades: list[TradeLog],
    ) -> dict[str, dict[str, float]]:
        """Aggregate PnL statistics bucketed by day of the week.

        Parameters
        ----------
        trades:
            List of ``TradeLog`` records.

        Returns
        -------
        dict[str, dict[str, float]]
            Keyed by weekday name (``"Monday"`` .. ``"Friday"``).  Each
            value contains ``total_pnl``, ``avg_pnl``, ``trade_count``,
            and ``win_rate``.
        """
        day_names = {0: "Monday", 1: "Tuesday", 2: "Wednesday",
                     3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday"}
        closed = _closed_trades(trades)
        buckets: dict[str, list[TradeLog]] = defaultdict(list)
        for t in closed:
            day = day_names.get(t.timestamp_entry.weekday(), "Unknown")
            buckets[day].append(t)

        ordered_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        result: dict[str, dict[str, float]] = {}
        for day in ordered_days:
            bucket = buckets.get(day, [])
            pnls = [t.pnl_dollars for t in bucket if t.pnl_dollars is not None]
            wins = sum(1 for p in pnls if p > 0)
            result[day] = {
                "total_pnl": float(np.sum(pnls)) if pnls else 0.0,
                "avg_pnl": float(np.mean(pnls)) if pnls else 0.0,
                "trade_count": float(len(bucket)),
                "win_rate": wins / len(pnls) if pnls else 0.0,
            }
        return result


# =============================================================================
# 2. FACTOR ANALYSIS
# =============================================================================


class FactorAnalysis:
    """Analyze contribution of each directional factor to signal quality.

    The five-factor composite direction scorer (market internals, options
    flow, price action, GEX structure, cross-asset) is the core of the
    SCANIFY directional engine.  This class provides tools to evaluate how
    each factor contributes to overall signal accuracy and how weights
    should evolve over time.
    """

    @staticmethod
    def _extract_factor_matrix(scores: list[DirectionScore]) -> np.ndarray:
        """Extract the five sub-scores from a list of ``DirectionScore`` into
        an (N x 5) numpy array.

        Column order follows ``_FACTOR_NAMES``:
        market_internals, options_flow, price_action, gex_structure, cross_asset.
        """
        rows = []
        for s in scores:
            rows.append([
                s.market_internals_score,
                s.options_flow_score,
                s.price_action_score,
                s.gex_structure_score,
                s.cross_asset_score,
            ])
        return np.array(rows, dtype=np.float64)

    # --------------------------------------------------------------------- #

    @staticmethod
    def compute_factor_correlation_matrix(
        scores: list[DirectionScore],
    ) -> np.ndarray:
        """Compute the Pearson correlation matrix across the five factors.

        Parameters
        ----------
        scores:
            Ordered list of ``DirectionScore`` snapshots (oldest first).

        Returns
        -------
        np.ndarray
            (5 x 5) symmetric correlation matrix.  Returns an identity
            matrix when fewer than 3 samples are available.
        """
        if len(scores) < 3:
            logger.warning(
                "compute_factor_correlation_matrix: fewer than 3 scores; "
                "returning identity matrix."
            )
            return np.eye(5)
        matrix = FactorAnalysis._extract_factor_matrix(scores)
        corr = np.corrcoef(matrix, rowvar=False)
        # Guard against NaN when a column has zero variance.
        corr = np.nan_to_num(corr, nan=0.0)
        return corr

    @staticmethod
    def compute_factor_information_ratio(
        scores: list[DirectionScore],
        outcomes: list[float],
    ) -> dict[str, float]:
        """Compute the information ratio of each factor against trade outcomes.

        The information ratio is defined as the mean excess return
        (factor-predicted vs. outcome) divided by the tracking error
        (standard deviation of the residual).  Here we adapt it: for each
        factor, we compute the Pearson correlation of the factor sub-score
        with the trade outcome, then divide by (1 - |corr|) as a
        stability-adjusted information coefficient.

        Parameters
        ----------
        scores:
            Ordered ``DirectionScore`` list (one per trade).
        outcomes:
            Trade outcomes (e.g., PnL) aligned with *scores*.

        Returns
        -------
        dict[str, float]
            Information ratio keyed by factor name.
        """
        n = min(len(scores), len(outcomes))
        if n < 3:
            return {name: 0.0 for name in _FACTOR_NAMES}
        matrix = FactorAnalysis._extract_factor_matrix(scores[:n])
        y = np.array(outcomes[:n], dtype=np.float64)
        result: dict[str, float] = {}
        for idx, name in enumerate(_FACTOR_NAMES):
            factor_col = matrix[:, idx]
            if np.std(factor_col) == 0.0 or np.std(y) == 0.0:
                result[name] = 0.0
                continue
            corr, _ = stats.pearsonr(factor_col, y)
            # Residual std as tracking error
            predicted = factor_col * (np.std(y) / np.std(factor_col)) * np.sign(corr)
            residual = y - predicted
            tracking_error = float(np.std(residual, ddof=1))
            mean_excess = float(np.mean(y - predicted))
            result[name] = _safe_division(mean_excess, tracking_error, 0.0)
        return result

    @staticmethod
    def compute_factor_stability(
        weight_history: list[FactorWeights],
        window: int = 20,
    ) -> dict[str, float]:
        """Measure the stability (inverse volatility) of each factor weight
        over a rolling window.

        A lower value indicates that the calibration system has been
        adjusting that factor's weight aggressively.

        Parameters
        ----------
        weight_history:
            Time-ordered list of ``FactorWeights`` snapshots.
        window:
            Rolling look-back length.

        Returns
        -------
        dict[str, float]
            Standard deviation of each factor's weight over the most
            recent *window* snapshots.  Lower = more stable.
        """
        if not weight_history:
            return {name: 0.0 for name in _FACTOR_NAMES}

        recent = weight_history[-window:]
        arrays: dict[str, list[float]] = {name: [] for name in _FACTOR_NAMES}
        for fw in recent:
            arrays["market_internals"].append(fw.market_internals)
            arrays["options_flow"].append(fw.options_flow)
            arrays["price_action"].append(fw.price_action)
            arrays["gex_structure"].append(fw.gex_structure)
            arrays["cross_asset"].append(fw.cross_asset)

        result: dict[str, float] = {}
        for name in _FACTOR_NAMES:
            vals = np.array(arrays[name], dtype=np.float64)
            result[name] = float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0
        return result

    @staticmethod
    def identify_redundant_factors(
        correlation_matrix: np.ndarray,
        threshold: float = 0.8,
    ) -> list[tuple[str, str, float]]:
        """Identify pairs of factors with correlation above *threshold*.

        High pairwise correlation suggests factor redundancy -- one of
        the pair could be dropped or down-weighted without losing
        information.

        Parameters
        ----------
        correlation_matrix:
            (5 x 5) correlation matrix produced by
            ``compute_factor_correlation_matrix``.
        threshold:
            Absolute correlation above which a pair is flagged.

        Returns
        -------
        list[tuple[str, str, float]]
            List of ``(factor_a, factor_b, correlation)`` tuples for
            every redundant pair.
        """
        redundant: list[tuple[str, str, float]] = []
        n = min(correlation_matrix.shape[0], len(_FACTOR_NAMES))
        for i in range(n):
            for j in range(i + 1, n):
                corr_val = abs(float(correlation_matrix[i, j]))
                if corr_val >= threshold:
                    redundant.append((_FACTOR_NAMES[i], _FACTOR_NAMES[j], corr_val))
        return redundant

    @staticmethod
    def compute_factor_decay_rate(
        scores: list[DirectionScore],
        outcomes: list[float],
        horizons: list[int],
    ) -> dict[str, list[float]]:
        """Measure how each factor's predictive power decays over different
        forward horizons.

        For each factor and each horizon *h* in *horizons*, we correlate
        the factor sub-score at time *t* with the outcome at time *t + h*.

        Parameters
        ----------
        scores:
            Ordered ``DirectionScore`` list.
        outcomes:
            Aligned outcome series (same length as *scores*).
        horizons:
            List of forward offsets (e.g. ``[1, 5, 10, 20]``).

        Returns
        -------
        dict[str, list[float]]
            Keyed by factor name; each value is a list of Pearson
            correlations aligned with *horizons*.
        """
        n = min(len(scores), len(outcomes))
        if n < 5:
            return {name: [0.0] * len(horizons) for name in _FACTOR_NAMES}

        matrix = FactorAnalysis._extract_factor_matrix(scores[:n])
        y = np.array(outcomes[:n], dtype=np.float64)

        result: dict[str, list[float]] = {name: [] for name in _FACTOR_NAMES}
        for h in horizons:
            if h >= n:
                for name in _FACTOR_NAMES:
                    result[name].append(0.0)
                continue
            for idx, name in enumerate(_FACTOR_NAMES):
                factor_slice = matrix[: n - h, idx]
                outcome_slice = y[h:]
                if len(factor_slice) < 3 or np.std(factor_slice) == 0.0 or np.std(outcome_slice) == 0.0:
                    result[name].append(0.0)
                else:
                    corr, _ = stats.pearsonr(factor_slice, outcome_slice)
                    result[name].append(float(corr))
        return result

    @staticmethod
    def optimal_factor_combination(
        scores: list[DirectionScore],
        outcomes: list[float],
    ) -> FactorWeights:
        """Find the optimal factor weight combination that maximises the
        Pearson correlation between the weighted composite score and the
        trade outcomes.

        Uses constrained optimisation (SLSQP) with the constraints that
        weights are in [0.05, 0.40] and sum to 1.0 -- mirroring the
        bounds in ``SelfLearningConstants``.

        Parameters
        ----------
        scores:
            Ordered ``DirectionScore`` list (one per trade).
        outcomes:
            Trade outcomes aligned with *scores*.

        Returns
        -------
        FactorWeights
            Optimised factor weights.
        """
        n = min(len(scores), len(outcomes))
        if n < 10:
            logger.warning(
                "optimal_factor_combination: fewer than 10 samples; "
                "returning equal weights."
            )
            equal = 0.20
            return FactorWeights(
                market_internals=equal,
                options_flow=equal,
                price_action=equal,
                gex_structure=equal,
                cross_asset=equal,
            )

        matrix = FactorAnalysis._extract_factor_matrix(scores[:n])
        y = np.array(outcomes[:n], dtype=np.float64)

        def neg_correlation(w: np.ndarray) -> float:
            composite = matrix @ w
            if np.std(composite) == 0.0:
                return 0.0
            corr, _ = stats.pearsonr(composite, y)
            return -corr  # Minimise negative correlation

        # Constraints: weights sum to 1.0
        constraints = {"type": "eq", "fun": lambda w: np.sum(w) - 1.0}
        # Bounds: each weight in [0.05, 0.40]
        bounds = [(0.05, 0.40)] * 5
        # Initial guess: equal weights
        x0 = np.array([0.20] * 5)

        result = optimize.minimize(
            neg_correlation,
            x0,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"maxiter": 500, "ftol": 1e-10},
        )

        if result.success:
            w = result.x
            # Normalise to exactly 1.0 to satisfy Pydantic validator.
            w = w / w.sum()
        else:
            logger.warning(
                "optimal_factor_combination: optimisation did not converge; "
                "returning equal weights. Message: %s",
                result.message,
            )
            w = np.array([0.20] * 5)

        return FactorWeights(
            market_internals=round(float(w[0]), 6),
            options_flow=round(float(w[1]), 6),
            price_action=round(float(w[2]), 6),
            gex_structure=round(float(w[3]), 6),
            cross_asset=round(float(w[4]), 6),
        )


# =============================================================================
# 3. GEX ANALYTICS
# =============================================================================


class GEXAnalytics:
    """Analytics specific to GEX signal performance.

    Evaluates how well gamma-exposure-derived signals (walls, flips,
    charm, transitions) have predicted subsequent price behaviour.
    """

    @staticmethod
    def compute_wall_hold_rate(
        wall_events: list[dict[str, Any]],
    ) -> dict[str, float]:
        """Compute the rate at which gamma walls held as support/resistance.

        Each event dict must contain:

        - ``wall_type``: ``"call_wall"`` or ``"put_wall"``
        - ``wall_strike``: strike price of the wall
        - ``held``: ``True`` if price reversed at the wall, ``False`` if
          price broke through

        Parameters
        ----------
        wall_events:
            List of wall interaction event dicts.

        Returns
        -------
        dict[str, float]
            Hold rate for each wall type plus ``"overall"``.
        """
        if not wall_events:
            return {"call_wall": 0.0, "put_wall": 0.0, "overall": 0.0}

        buckets: dict[str, list[bool]] = defaultdict(list)
        for event in wall_events:
            wall_type = event.get("wall_type", "unknown")
            held = bool(event.get("held", False))
            buckets[wall_type].append(held)

        result: dict[str, float] = {}
        all_held: list[bool] = []
        for wall_type in ("call_wall", "put_wall"):
            held_list = buckets.get(wall_type, [])
            all_held.extend(held_list)
            if held_list:
                result[wall_type] = sum(held_list) / len(held_list)
            else:
                result[wall_type] = 0.0

        result["overall"] = (sum(all_held) / len(all_held)) if all_held else 0.0
        return result

    @staticmethod
    def compute_gamma_flip_accuracy(
        flip_events: list[dict[str, Any]],
    ) -> float:
        """Compute the accuracy of gamma-flip-crossover signals.

        Each event dict must contain:

        - ``predicted_direction``: ``"BULL"`` or ``"BEAR"``
        - ``actual_direction``: ``"BULL"`` or ``"BEAR"``

        Parameters
        ----------
        flip_events:
            List of gamma flip event dicts.

        Returns
        -------
        float
            Fraction of flip signals where predicted matched actual
            direction.  Returns 0.0 when no events are provided.
        """
        if not flip_events:
            return 0.0
        correct = sum(
            1 for e in flip_events
            if e.get("predicted_direction") == e.get("actual_direction")
        )
        return correct / len(flip_events)

    @staticmethod
    def compute_charm_flow_correlation(
        predicted: list[float],
        actual: list[float],
    ) -> float:
        """Pearson correlation between predicted charm-driven flow and actual
        observed ES delta-hedging flow.

        Parameters
        ----------
        predicted:
            Predicted charm flow values (e.g., ES-contract equivalents).
        actual:
            Actual observed flow values.

        Returns
        -------
        float
            Pearson correlation coefficient.  Returns 0.0 when fewer than
            3 data points or zero-variance series.
        """
        n = min(len(predicted), len(actual))
        if n < 3:
            return 0.0
        p = np.array(predicted[:n], dtype=np.float64)
        a = np.array(actual[:n], dtype=np.float64)
        if np.std(p) == 0.0 or np.std(a) == 0.0:
            return 0.0
        corr, _ = stats.pearsonr(p, a)
        return float(corr)

    @staticmethod
    def compute_gex_regime_stats(
        profiles: list[GEXProfile],
    ) -> dict[str, dict[str, float]]:
        """Compute summary statistics for positive-gamma and negative-gamma
        regimes.

        Parameters
        ----------
        profiles:
            Time-ordered list of ``GEXProfile`` snapshots.

        Returns
        -------
        dict[str, dict[str, float]]
            Keyed by ``"positive_gamma"`` and ``"negative_gamma"``.  Each
            sub-dict contains:

            - ``count``: number of snapshots in this regime.
            - ``pct``: percentage of total snapshots.
            - ``avg_net_gex``: average net GEX.
            - ``avg_momentum``: average GEX momentum.
            - ``avg_charm_flow``: average charm net ES contracts.
            - ``avg_vanna_exposure``: average vanna net exposure.
        """
        if not profiles:
            empty = {
                "count": 0.0, "pct": 0.0, "avg_net_gex": 0.0,
                "avg_momentum": 0.0, "avg_charm_flow": 0.0,
                "avg_vanna_exposure": 0.0,
            }
            return {"positive_gamma": dict(empty), "negative_gamma": dict(empty)}

        buckets: dict[str, list[GEXProfile]] = {
            "positive_gamma": [],
            "negative_gamma": [],
        }
        for p in profiles:
            key = "positive_gamma" if p.is_positive_gamma_regime else "negative_gamma"
            buckets[key].append(p)

        total = len(profiles)
        result: dict[str, dict[str, float]] = {}
        for regime, regime_profiles in buckets.items():
            if not regime_profiles:
                result[regime] = {
                    "count": 0.0, "pct": 0.0, "avg_net_gex": 0.0,
                    "avg_momentum": 0.0, "avg_charm_flow": 0.0,
                    "avg_vanna_exposure": 0.0,
                }
                continue
            gex_vals = [p.total_net_gex for p in regime_profiles]
            momentum_vals = [p.gex_momentum for p in regime_profiles]
            charm_vals = [p.charm_net_es_contracts for p in regime_profiles]
            vanna_vals = [p.vanna_net_exposure for p in regime_profiles]
            result[regime] = {
                "count": float(len(regime_profiles)),
                "pct": len(regime_profiles) / total * 100.0,
                "avg_net_gex": float(np.mean(gex_vals)),
                "avg_momentum": float(np.mean(momentum_vals)),
                "avg_charm_flow": float(np.mean(charm_vals)),
                "avg_vanna_exposure": float(np.mean(vanna_vals)),
            }
        return result

    @staticmethod
    def compute_transition_zone_breakout_stats(
        events: list[dict[str, Any]],
    ) -> dict[str, float]:
        """Compute statistics for transition-zone breakout events.

        Each event dict must contain:

        - ``breakout_direction``: ``"up"`` or ``"down"``
        - ``magnitude_points``: how far price moved beyond the zone (SPX points)
        - ``held_breakout``: ``True`` if price sustained outside the zone for
          at least 5 minutes, ``False`` if it reverted.

        Parameters
        ----------
        events:
            List of transition-zone breakout event dicts.

        Returns
        -------
        dict[str, float]
            Summary statistics including breakout counts, hold rates, and
            average magnitudes by direction.
        """
        if not events:
            return {
                "total_events": 0.0,
                "up_count": 0.0,
                "down_count": 0.0,
                "up_hold_rate": 0.0,
                "down_hold_rate": 0.0,
                "overall_hold_rate": 0.0,
                "avg_magnitude_up": 0.0,
                "avg_magnitude_down": 0.0,
            }

        up_events = [e for e in events if e.get("breakout_direction") == "up"]
        down_events = [e for e in events if e.get("breakout_direction") == "down"]

        def _hold_rate(ev_list: list[dict]) -> float:
            if not ev_list:
                return 0.0
            return sum(1 for e in ev_list if e.get("held_breakout", False)) / len(ev_list)

        def _avg_magnitude(ev_list: list[dict]) -> float:
            mags = [e.get("magnitude_points", 0.0) for e in ev_list]
            return float(np.mean(mags)) if mags else 0.0

        all_held = sum(1 for e in events if e.get("held_breakout", False))
        return {
            "total_events": float(len(events)),
            "up_count": float(len(up_events)),
            "down_count": float(len(down_events)),
            "up_hold_rate": _hold_rate(up_events),
            "down_hold_rate": _hold_rate(down_events),
            "overall_hold_rate": all_held / len(events),
            "avg_magnitude_up": _avg_magnitude(up_events),
            "avg_magnitude_down": _avg_magnitude(down_events),
        }


# =============================================================================
# 4. RISK ANALYTICS
# =============================================================================


class RiskAnalytics:
    """Real-time risk monitoring and analysis.

    Provides portfolio-level risk metrics computed from daily PnL series
    and equity curves.  All VaR and CVaR calculations use the historical
    simulation method (percentile-based) for robustness with 0DTE-style
    fat-tailed distributions.
    """

    @staticmethod
    def compute_value_at_risk(
        daily_pnl: list[float],
        confidence: float = 0.95,
    ) -> float:
        """Historical simulation Value at Risk (VaR).

        VaR at the given confidence level is the loss threshold that daily
        PnL exceeds (in the negative direction) only (1 - confidence) of
        the time.

        Parameters
        ----------
        daily_pnl:
            Daily PnL series.
        confidence:
            Confidence level (e.g., 0.95 for 95% VaR).

        Returns
        -------
        float
            VaR as a positive number representing the loss threshold.
            Returns 0.0 when no data is available.
        """
        if not daily_pnl:
            return 0.0
        arr = np.array(daily_pnl, dtype=np.float64)
        percentile = (1.0 - confidence) * 100.0
        var = float(np.percentile(arr, percentile))
        return abs(var) if var < 0 else 0.0

    @staticmethod
    def compute_conditional_var(
        daily_pnl: list[float],
        confidence: float = 0.95,
    ) -> float:
        """Conditional Value at Risk (CVaR / Expected Shortfall).

        CVaR is the average loss in the worst (1 - confidence) fraction
        of trading days -- a coherent risk measure that better captures
        tail risk than VaR alone.

        Parameters
        ----------
        daily_pnl:
            Daily PnL series.
        confidence:
            Confidence level (e.g., 0.95 for 95% CVaR).

        Returns
        -------
        float
            CVaR as a positive number.  Returns 0.0 when no data.
        """
        if not daily_pnl:
            return 0.0
        arr = np.array(daily_pnl, dtype=np.float64)
        percentile = (1.0 - confidence) * 100.0
        var_threshold = float(np.percentile(arr, percentile))
        tail = arr[arr <= var_threshold]
        if len(tail) == 0:
            return abs(var_threshold) if var_threshold < 0 else 0.0
        cvar = float(np.mean(tail))
        return abs(cvar) if cvar < 0 else 0.0

    @staticmethod
    def compute_max_drawdown(
        equity_curve: list[float],
    ) -> tuple[float, int, int]:
        """Compute the maximum drawdown from an equity curve.

        Parameters
        ----------
        equity_curve:
            Cumulative equity series (oldest first).

        Returns
        -------
        tuple[float, int, int]
            ``(max_drawdown, peak_index, trough_index)`` where
            ``max_drawdown`` is the absolute dollar decline from peak to
            trough.  Returns ``(0.0, 0, 0)`` when the curve is empty or
            monotonically increasing.
        """
        if not equity_curve:
            return (0.0, 0, 0)

        arr = np.array(equity_curve, dtype=np.float64)
        running_max = np.maximum.accumulate(arr)
        drawdowns = arr - running_max  # Negative values are drawdowns

        trough_idx = int(np.argmin(drawdowns))
        peak_idx = int(np.argmax(arr[:trough_idx + 1])) if trough_idx > 0 else 0
        max_dd = float(running_max[trough_idx] - arr[trough_idx])
        return (max_dd, peak_idx, trough_idx)

    @staticmethod
    def compute_drawdown_duration(
        equity_curve: list[float],
    ) -> list[int]:
        """Compute the duration (in periods) of each drawdown episode.

        A drawdown episode begins when equity drops below its running
        maximum and ends when a new high is established.

        Parameters
        ----------
        equity_curve:
            Cumulative equity series (oldest first).

        Returns
        -------
        list[int]
            Duration of each completed drawdown episode (in bars).
            An ongoing drawdown at the end of the series is included.
        """
        if not equity_curve:
            return []

        arr = np.array(equity_curve, dtype=np.float64)
        running_max = np.maximum.accumulate(arr)

        durations: list[int] = []
        current_dd_length = 0
        in_drawdown = False

        for i in range(len(arr)):
            if arr[i] < running_max[i]:
                current_dd_length += 1
                in_drawdown = True
            else:
                if in_drawdown:
                    durations.append(current_dd_length)
                    current_dd_length = 0
                    in_drawdown = False

        # Include ongoing drawdown at the end.
        if in_drawdown and current_dd_length > 0:
            durations.append(current_dd_length)

        return durations

    @staticmethod
    def compute_ulcer_index(equity_curve: list[float]) -> float:
        """Compute the Ulcer Index -- a volatility measure that penalises
        only drawdowns and weights them by depth and duration.

        Ulcer Index = sqrt(mean(drawdown_pct^2))

        Parameters
        ----------
        equity_curve:
            Cumulative equity series (oldest first).

        Returns
        -------
        float
            Ulcer Index (percentage-based).  Returns 0.0 when the curve
            is empty.
        """
        if not equity_curve:
            return 0.0
        arr = np.array(equity_curve, dtype=np.float64)
        if arr[0] == 0.0:
            return 0.0
        running_max = np.maximum.accumulate(arr)
        # Guard against division by zero in running_max
        safe_max = np.where(running_max == 0.0, 1.0, running_max)
        dd_pct = ((arr - running_max) / safe_max) * 100.0
        return float(np.sqrt(np.mean(dd_pct ** 2)))

    @staticmethod
    def compute_tail_ratio(daily_pnl: list[float]) -> float:
        """Compute the tail ratio: right-tail 95th percentile divided by
        the absolute value of the left-tail 5th percentile.

        A ratio > 1.0 indicates the right tail (gains) is fatter than the
        left tail (losses) -- a desirable property for a trading system.

        Parameters
        ----------
        daily_pnl:
            Daily PnL series.

        Returns
        -------
        float
            Tail ratio.  Returns 0.0 when the 5th percentile is zero.
        """
        if not daily_pnl or len(daily_pnl) < 5:
            return 0.0
        arr = np.array(daily_pnl, dtype=np.float64)
        right = float(np.percentile(arr, 95))
        left = float(np.percentile(arr, 5))
        if left == 0.0:
            return 0.0 if right == 0.0 else float("inf")
        return abs(right / left)

    @staticmethod
    def compute_omega_ratio(
        daily_pnl: list[float],
        threshold: float = 0.0,
    ) -> float:
        """Compute the Omega ratio.

        Omega = sum(max(r_i - threshold, 0)) / sum(max(threshold - r_i, 0))

        This captures all moments of the return distribution above and
        below the *threshold*, making it more informative than the Sharpe
        ratio for non-normal distributions typical of 0DTE trading.

        Parameters
        ----------
        daily_pnl:
            Daily PnL series.
        threshold:
            Minimum acceptable return (default 0.0).

        Returns
        -------
        float
            Omega ratio.  Returns ``float('inf')`` when there are no
            returns below the threshold.  Returns 0.0 when empty.
        """
        if not daily_pnl:
            return 0.0
        arr = np.array(daily_pnl, dtype=np.float64)
        gains = np.sum(np.maximum(arr - threshold, 0.0))
        losses = np.sum(np.maximum(threshold - arr, 0.0))
        if losses == 0.0:
            return float("inf") if gains > 0.0 else 0.0
        return float(gains / losses)

    @staticmethod
    def detect_correlation_breakdown(
        factor_corrs: list[np.ndarray],
    ) -> bool:
        """Detect a structural breakdown in inter-factor correlations.

        Compares the most recent correlation matrix against the average
        of prior matrices using the Frobenius norm of the difference.  A
        breakdown is flagged when the norm exceeds 2 standard deviations
        of the historical distribution of pairwise norms.

        Parameters
        ----------
        factor_corrs:
            Time-ordered list of (5 x 5) correlation matrices.

        Returns
        -------
        bool
            ``True`` if a correlation breakdown is detected.
        """
        if len(factor_corrs) < 5:
            return False

        # Compute pairwise Frobenius norms between consecutive matrices.
        diffs: list[float] = []
        for i in range(1, len(factor_corrs)):
            diff = factor_corrs[i] - factor_corrs[i - 1]
            diffs.append(float(np.linalg.norm(diff, "fro")))

        if len(diffs) < 3:
            return False

        mu = float(np.mean(diffs[:-1]))
        sigma = float(np.std(diffs[:-1], ddof=1))
        if sigma == 0.0:
            return False

        latest_diff = diffs[-1]
        z_score = (latest_diff - mu) / sigma
        return z_score > 2.0

    @staticmethod
    def compute_position_concentration(
        positions: list[Any],
    ) -> float:
        """Compute the Herfindahl-Hirschman Index (HHI) of position
        concentration.

        Each position in *positions* must have a ``max_risk`` attribute or
        be a numeric value representing the risk allocation.

        Parameters
        ----------
        positions:
            List of positions.  If items have a ``max_risk`` attribute it
            is used; otherwise items are treated as float risk amounts.

        Returns
        -------
        float
            HHI between 0.0 (perfectly diversified) and 1.0 (single
            position).  Returns 0.0 when no positions are present.
        """
        if not positions:
            return 0.0

        risks: list[float] = []
        for p in positions:
            if hasattr(p, "max_risk"):
                risks.append(float(p.max_risk))
            else:
                try:
                    risks.append(float(p))
                except (TypeError, ValueError):
                    continue

        if not risks:
            return 0.0

        total = sum(abs(r) for r in risks)
        if total == 0.0:
            return 0.0

        shares = [abs(r) / total for r in risks]
        hhi = sum(s ** 2 for s in shares)
        return float(hhi)


# =============================================================================
# 5. MARKET MICROSTRUCTURE ANALYTICS
# =============================================================================


class MarketMicrostructureAnalytics:
    """Analyze market microstructure signals for 0DTE.

    Evaluates execution-quality indicators such as bid-ask spread trends,
    order-flow toxicity, volume profiles, market impact, and exchange
    anomalies.
    """

    @staticmethod
    def compute_bid_ask_spread_trend(
        spreads: list[float],
    ) -> str:
        """Classify the recent bid-ask spread trend.

        Uses linear regression on the spread series and classifies the
        slope into ``"TIGHTENING"``, ``"WIDENING"``, or ``"STABLE"``.

        Parameters
        ----------
        spreads:
            Time-ordered bid-ask spread observations (newest last).

        Returns
        -------
        str
            One of ``"TIGHTENING"``, ``"WIDENING"``, ``"STABLE"``.
        """
        if len(spreads) < 3:
            return "STABLE"

        y = np.array(spreads, dtype=np.float64)
        x = np.arange(len(y), dtype=np.float64)
        slope, _, _, _, _ = stats.linregress(x, y)

        # Normalise slope relative to mean spread for threshold comparison.
        mean_spread = float(np.mean(y))
        if mean_spread == 0.0:
            return "STABLE"

        normalised_slope = slope / mean_spread

        if normalised_slope > 0.01:
            return "WIDENING"
        elif normalised_slope < -0.01:
            return "TIGHTENING"
        return "STABLE"

    @staticmethod
    def compute_order_flow_toxicity(
        trades: list[dict[str, Any]],
    ) -> float:
        """Estimate order-flow toxicity using a simplified VPIN-inspired
        metric.

        Each trade dict must contain:

        - ``volume``: trade volume.
        - ``side``: ``"buy"`` or ``"sell"`` (aggressor side).

        The toxicity metric is the absolute imbalance between buy and sell
        volume as a fraction of total volume.

        Parameters
        ----------
        trades:
            List of trade event dicts.

        Returns
        -------
        float
            Toxicity score between 0.0 (balanced) and 1.0 (completely
            one-sided).
        """
        if not trades:
            return 0.0

        buy_vol = 0.0
        sell_vol = 0.0
        for t in trades:
            vol = float(t.get("volume", 0))
            side = t.get("side", "").lower()
            if side == "buy":
                buy_vol += vol
            elif side == "sell":
                sell_vol += vol

        total = buy_vol + sell_vol
        if total == 0.0:
            return 0.0
        return abs(buy_vol - sell_vol) / total

    @staticmethod
    def compute_volume_profile(
        volumes: list[float],
        prices: list[float],
    ) -> dict[str, Any]:
        """Compute a volume-weighted price profile (Value Area).

        Buckets volume into price bins and identifies the Point of Control
        (POC), Value Area High (VAH), and Value Area Low (VAL) using the
        conventional 70% value area rule.

        Parameters
        ----------
        volumes:
            Volume observations aligned with *prices*.
        prices:
            Price observations.

        Returns
        -------
        dict[str, Any]
            Contains ``poc`` (Point of Control price), ``vah`` (Value
            Area High), ``val`` (Value Area Low), ``total_volume``,
            and ``num_bins``.
        """
        n = min(len(volumes), len(prices))
        if n == 0:
            return {"poc": 0.0, "vah": 0.0, "val": 0.0,
                    "total_volume": 0.0, "num_bins": 0}

        v = np.array(volumes[:n], dtype=np.float64)
        p = np.array(prices[:n], dtype=np.float64)

        # Build a histogram with auto-sized bins.
        num_bins = max(10, int(np.sqrt(n)))
        hist, bin_edges = np.histogram(p, bins=num_bins, weights=v)

        # Point of Control: bin with highest volume
        poc_bin = int(np.argmax(hist))
        poc = float((bin_edges[poc_bin] + bin_edges[poc_bin + 1]) / 2.0)

        # Value Area (70% of total volume).
        total_vol = float(np.sum(hist))
        target_vol = total_vol * 0.70

        # Expand outward from POC bin until 70% is captured.
        accumulated = float(hist[poc_bin])
        lo = poc_bin
        hi = poc_bin
        while accumulated < target_vol and (lo > 0 or hi < len(hist) - 1):
            expand_lo = float(hist[lo - 1]) if lo > 0 else -1.0
            expand_hi = float(hist[hi + 1]) if hi < len(hist) - 1 else -1.0
            if expand_lo >= expand_hi:
                lo -= 1
                accumulated += float(hist[lo])
            else:
                hi += 1
                accumulated += float(hist[hi])

        val = float(bin_edges[lo])
        vah = float(bin_edges[hi + 1])

        return {
            "poc": poc,
            "vah": vah,
            "val": val,
            "total_volume": total_vol,
            "num_bins": num_bins,
        }

    @staticmethod
    def estimate_market_impact(
        order_size: int,
        avg_volume: float,
        spread: float,
    ) -> float:
        """Estimate the market impact cost of an order using a square-root
        model.

        impact = spread / 2 + k * spread * sqrt(order_size / avg_volume)

        where *k* is an empirically-calibrated constant (0.1 for liquid
        SPX options).

        Parameters
        ----------
        order_size:
            Number of contracts in the order.
        avg_volume:
            Average intraday volume for this contract.
        spread:
            Current bid-ask spread in dollars.

        Returns
        -------
        float
            Estimated one-way market impact in dollars per contract.
            Returns 0.0 when avg_volume is zero.
        """
        if avg_volume <= 0.0 or order_size <= 0:
            return 0.0
        k = 0.1  # SPX options liquidity constant
        participation = order_size / avg_volume
        return (spread / 2.0) + k * spread * math.sqrt(participation)

    @staticmethod
    def detect_quote_stuffing(
        quote_changes: list[int],
        window: int = 60,
    ) -> bool:
        """Detect potential quote stuffing within a rolling window.

        Quote stuffing is characterised by an abnormally high number of
        quote updates within a short period.  We flag it when the count
        in the last *window* observations exceeds the mean plus 3 standard
        deviations of the historical distribution.

        Parameters
        ----------
        quote_changes:
            Time-ordered count of quote changes per second (or per unit
            observation period).
        window:
            Number of most recent observations to evaluate.

        Returns
        -------
        bool
            ``True`` if quote stuffing is detected.
        """
        if len(quote_changes) < window + 10:
            return False

        arr = np.array(quote_changes, dtype=np.float64)
        historical = arr[: -window]
        recent = arr[-window:]

        mu = float(np.mean(historical))
        sigma = float(np.std(historical, ddof=1))
        if sigma == 0.0:
            return False

        recent_mean = float(np.mean(recent))
        z_score = (recent_mean - mu) / sigma
        return z_score > 3.0


# =============================================================================
# MODULE EXPORT
# =============================================================================

__all__: list[str] = [
    "SignalAnalytics",
    "FactorAnalysis",
    "GEXAnalytics",
    "RiskAnalytics",
    "MarketMicrostructureAnalytics",
]
