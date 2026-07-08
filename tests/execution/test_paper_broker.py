"""Accounting-correctness tests for the PaperBroker."""
import math

import pytest

from src.execution.paper_broker import PaperBroker, Position
from src.execution.algorithms import OrderSide


def test_buy_reduces_cash_and_opens_position():
    b = PaperBroker(starting_cash=100_000, commission_bps=0, slippage_bps=0)
    b.submit("AAPL", OrderSide.BUY, 100, 200.0)
    assert b.positions["AAPL"].quantity == 100
    assert b.positions["AAPL"].avg_price == pytest.approx(200.0)
    assert b.cash == pytest.approx(100_000 - 100 * 200.0)
    # equity unchanged at the same price (value moved cash -> position)
    assert b.equity({"AAPL": 200.0}) == pytest.approx(100_000)


def test_pnl_on_price_move():
    b = PaperBroker(starting_cash=100_000, commission_bps=0, slippage_bps=0)
    b.submit("AAPL", OrderSide.BUY, 100, 10.0)
    # price rises to 11 -> +$100
    assert b.equity({"AAPL": 11.0}) == pytest.approx(100_000 + 100 * 1.0)


def test_round_trip_costs_only_loss():
    b = PaperBroker(starting_cash=100_000, commission_bps=1.0, slippage_bps=1.0)
    b.submit("X", OrderSide.BUY, 100, 50.0)
    b.submit("X", OrderSide.SELL, 100, 50.0)
    eq = b.equity({"X": 50.0})
    assert abs(b.positions["X"].quantity) < 1e-9        # flat
    assert eq < 100_000                                 # lost only costs
    assert (100_000 - eq) < 100_000 * 0.001             # costs are small


def test_short_sale_accounting():
    b = PaperBroker(starting_cash=100_000, commission_bps=0, slippage_bps=0)
    b.submit("Z", OrderSide.SELL, 100, 20.0)            # open short
    assert b.positions["Z"].quantity == -100
    assert b.cash == pytest.approx(100_000 + 100 * 20.0)  # proceeds in
    # price falls to 18 -> short gains +$200
    assert b.equity({"Z": 18.0}) == pytest.approx(100_000 + 200)
    # price rises to 22 -> short loses $200
    assert b.equity({"Z": 22.0}) == pytest.approx(100_000 - 200)


def test_rebalance_to_weights_hits_targets():
    b = PaperBroker(starting_cash=100_000, commission_bps=0, slippage_bps=0)
    prices = {"A": 100.0, "B": 50.0}
    b.rebalance_to_weights({"A": 0.5, "B": 0.5}, prices)
    eq = b.equity(prices)
    wa = b.positions["A"].market_value(prices["A"]) / eq
    wb = b.positions["B"].market_value(prices["B"]) / eq
    assert wa == pytest.approx(0.5, abs=1e-6)
    assert wb == pytest.approx(0.5, abs=1e-6)


def test_rebalance_flattens_dropped_symbols():
    b = PaperBroker(starting_cash=100_000, commission_bps=0, slippage_bps=0)
    prices = {"A": 100.0, "B": 50.0}
    b.rebalance_to_weights({"A": 1.0}, prices)
    b.rebalance_to_weights({"B": 1.0}, prices)          # drop A, go all B
    assert abs(b.positions["A"].quantity) < 1e-9
    assert b.positions["B"].quantity > 0


def test_dollar_neutral_long_short():
    b = PaperBroker(starting_cash=100_000, commission_bps=0, slippage_bps=0)
    prices = {"L": 10.0, "S": 10.0}
    b.rebalance_to_weights({"L": 0.5, "S": -0.5}, prices)
    long_mv = b.positions["L"].market_value(prices["L"])
    short_mv = b.positions["S"].market_value(prices["S"])
    assert long_mv == pytest.approx(-short_mv, rel=1e-6)   # dollar neutral
    assert b.equity(prices) == pytest.approx(100_000)


def test_invalid_order_rejected():
    b = PaperBroker()
    with pytest.raises(ValueError):
        b.submit("A", OrderSide.BUY, 0, 10.0)
    with pytest.raises(ValueError):
        b.submit("A", OrderSide.BUY, 10, 0.0)


def test_equity_raises_on_missing_price():
    b = PaperBroker(starting_cash=100_000, commission_bps=0, slippage_bps=0)
    b.submit("AAPL", OrderSide.BUY, 100, 500.0)
    with pytest.raises(KeyError):
        b.equity({})          # $50k position must not silently vanish


def test_rebalance_rejects_leverage():
    b = PaperBroker(starting_cash=100_000, commission_bps=0, slippage_bps=0)
    with pytest.raises(ValueError):
        b.rebalance_to_weights({"A": 5.0}, {"A": 100.0})   # 5x gross
