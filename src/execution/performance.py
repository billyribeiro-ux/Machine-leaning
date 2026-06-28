"""
Performance analytics for the paper-trading engine.

Pure functions over an equity curve (and optional fills), so they are trivially
testable and reusable by any backtest/paper/live report.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

TRADING_DAYS = 252


def _returns(equity: np.ndarray) -> np.ndarray:
    equity = np.asarray(equity, dtype=float)
    if len(equity) < 2:
        return np.array([])
    return np.diff(equity) / equity[:-1]


def drawdown_series(equity: Sequence[float]) -> np.ndarray:
    """Return the rolling drawdown (<=0) at each point of the equity curve."""
    eq = np.asarray(equity, dtype=float)
    if len(eq) == 0:
        return np.array([])
    peak = np.maximum.accumulate(eq)
    return (eq - peak) / peak


def turnover_ratio(traded_notional: float, mean_equity: float,
                   n_days: int, periods_per_year: int = TRADING_DAYS) -> float:
    """Annualized turnover = traded notional / mean equity, scaled to 1 year."""
    if mean_equity <= 0 or n_days <= 0:
        return 0.0
    return float(traded_notional / mean_equity * (periods_per_year / n_days))


def compute_metrics(
    equity_curve: Sequence[float],
    periods_per_year: int = TRADING_DAYS,
    traded_notional: Optional[float] = None,
) -> Dict[str, float]:
    """Full performance summary from an equity curve.

    Includes: total/annualized return, volatility, Sharpe, Sortino, Calmar,
    max drawdown, hit rate, best/worst day, and (if traded_notional given)
    annualized turnover.
    """
    eq = np.asarray(equity_curve, dtype=float)
    r = _returns(eq)
    out: Dict[str, float] = {}
    if len(r) == 0:
        return {k: 0.0 for k in (
            "total_return", "annualized_return", "volatility", "sharpe",
            "sortino", "calmar", "max_drawdown", "hit_rate", "pct_days_in_market",
            "best_day", "worst_day", "n_days")}

    n = len(r)
    total = float(eq[-1] / eq[0] - 1.0)
    ann = float((1.0 + total) ** (periods_per_year / n) - 1.0)
    vol = float(r.std(ddof=1) * np.sqrt(periods_per_year)) if r.std(ddof=1) > 0 else 0.0
    sharpe = float(r.mean() / r.std(ddof=1) * np.sqrt(periods_per_year)) if r.std(ddof=1) > 0 else 0.0

    downside = r[r < 0]
    dd_std = downside.std(ddof=1) if len(downside) > 1 else 0.0
    sortino = float(r.mean() / dd_std * np.sqrt(periods_per_year)) if dd_std > 0 else 0.0

    max_dd = float(drawdown_series(eq).min())
    calmar = float(ann / abs(max_dd)) if max_dd < 0 else 0.0

    # Hit rate is computed over ACTIVE days (non-zero P&L). Counting flat
    # cash days would understate it and mislead; we expose time-in-market
    # separately so an intermittent strategy is read honestly.
    active = r != 0
    hit_rate = float(np.mean(r[active] > 0)) if active.any() else 0.0

    out.update(
        total_return=total,
        annualized_return=ann,
        volatility=vol,
        sharpe=sharpe,
        sortino=sortino,
        calmar=calmar,
        max_drawdown=max_dd,
        hit_rate=hit_rate,
        pct_days_in_market=float(np.mean(active)),
        best_day=float(r.max()),
        worst_day=float(r.min()),
        n_days=int(n),
    )
    if traded_notional is not None:
        out["turnover_annualized"] = turnover_ratio(traded_notional, float(eq.mean()), n, periods_per_year)
    return out
