"""Tests for performance analytics."""
import numpy as np
import pytest

from src.execution.performance import (
    compute_metrics, drawdown_series, turnover_ratio,
)


def test_drawdown_series_basic():
    eq = [100, 110, 90, 95, 120]
    dd = drawdown_series(eq)
    assert dd[0] == 0.0
    assert dd[1] == 0.0                       # new peak
    assert dd[2] == pytest.approx((90 - 110) / 110)   # -18.2%
    assert dd[-1] == 0.0                      # new peak again


def test_compute_metrics_known_steady_growth():
    # +1% per day for 252 days
    eq = [100 * (1.01 ** i) for i in range(253)]
    m = compute_metrics(eq)
    assert m["total_return"] == pytest.approx(1.01 ** 252 - 1, rel=1e-6)
    assert m["max_drawdown"] == pytest.approx(0.0, abs=1e-9)  # monotonic
    assert m["hit_rate"] == pytest.approx(1.0)               # every day up
    assert m["sharpe"] > 10                                   # zero-vol-ish, huge
    assert m["calmar"] == 0.0                                 # no drawdown -> guarded


def test_sortino_ignores_upside_vol():
    rng = np.random.default_rng(0)
    r = rng.normal(0.0005, 0.01, 500)
    eq = 100 * np.cumprod(1 + r)
    m = compute_metrics(eq)
    # Sortino uses only downside deviation -> >= Sharpe for positive-drift series
    assert m["sortino"] >= m["sharpe"] - 1e-6
    assert -1.0 < m["max_drawdown"] <= 0.0


def test_turnover_ratio():
    # traded $200k over 100k mean equity in half a year -> 2x * 2 = 4x annualized
    t = turnover_ratio(traded_notional=200_000, mean_equity=100_000, n_days=126)
    assert t == pytest.approx(200_000 / 100_000 * (252 / 126))


def test_hit_rate_ignores_flat_cash_days():
    # equity: up, flat (cash), flat (cash), down -> 1 win / 1 loss among ACTIVE
    eq = [100, 101, 101, 101, 100]
    m = compute_metrics(eq)
    assert m["hit_rate"] == pytest.approx(0.5)          # 1 up / 2 active
    assert m["pct_days_in_market"] == pytest.approx(2 / 4)  # 2 active of 4 returns


def test_empty_curve_is_safe():
    m = compute_metrics([100.0])
    assert m["sharpe"] == 0.0 and m["n_days"] == 0


def test_sortino_hand_computed_value():
    # returns: +2%, -1%, -1%, -1%  -> mean = -0.0025
    # downside dev = sqrt(mean(min(r,0)^2)) = sqrt(3*0.0001/4) = 0.0086603
    # sortino = -0.0025/0.0086603*sqrt(252) = -4.5826  (audit: old code gave -4.5e14)
    eq = [100.0]
    for r in (0.02, -0.01, -0.01, -0.01):
        eq.append(eq[-1] * (1 + r))
    m = compute_metrics(eq)
    assert m["sortino"] == pytest.approx(-4.5826, abs=0.01)
