"""
PaperBroker — a zero-risk simulated broker with correct accounting.

Schwab has no paper-trading mode (its "sandbox" serves synthetic data, not a
paper account), so this provides an honest local paper-trading layer:

  * Cash + long/short positions with average-cost tracking.
  * Immediate fills at a supplied reference price, plus configurable slippage
    and commission (basis points).
  * Mark-to-market equity, an equity curve, and a full trade blotter.
  * `rebalance_to_weights` to drive the book from target portfolio weights
    (supports negative weights for shorts; dollar-neutral if Σ|w| split evenly).

It is deliberately broker-agnostic: the same interface can later be backed by
Schwab order placement once OAuth is connected — only `submit` would change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from .algorithms import OrderSide


@dataclass
class Fill:
    timestamp: Optional[datetime]
    symbol: str
    side: OrderSide
    quantity: float
    price: float          # executed price incl. slippage
    commission: float
    cash_delta: float     # signed change to cash from this fill


@dataclass
class Position:
    symbol: str
    quantity: float = 0.0      # negative = short
    avg_price: float = 0.0

    def market_value(self, price: float) -> float:
        return self.quantity * price


@dataclass
class PaperBroker:
    """Simulated broker. All costs in basis points (1bp = 0.01%)."""
    starting_cash: float = 100_000.0
    commission_bps: float = 1.0
    slippage_bps: float = 1.0

    cash: float = field(init=False)
    positions: Dict[str, Position] = field(default_factory=dict, init=False)
    fills: List[Fill] = field(default_factory=list, init=False)
    equity_curve: List[tuple] = field(default_factory=list, init=False)
    total_commission: float = field(default=0.0, init=False)

    def __post_init__(self):
        self.cash = float(self.starting_cash)

    # ---- core fill primitive -------------------------------------------- #
    def submit(self, symbol: str, side: OrderSide, quantity: float, ref_price: float,
               ts: Optional[datetime] = None) -> Fill:
        """Fill `quantity` shares immediately at ref_price ± slippage."""
        if quantity <= 0 or ref_price <= 0:
            raise ValueError("quantity and ref_price must be positive")
        slip = self.slippage_bps / 1e4
        fill_price = ref_price * (1 + slip) if side is OrderSide.BUY else ref_price * (1 - slip)
        notional = fill_price * quantity
        commission = notional * (self.commission_bps / 1e4)

        pos = self.positions.setdefault(symbol, Position(symbol))
        signed = quantity if side is OrderSide.BUY else -quantity

        # average-cost update only when increasing exposure in the same direction
        new_qty = pos.quantity + signed
        if pos.quantity == 0 or (pos.quantity > 0) == (signed > 0):
            denom = pos.quantity + signed
            pos.avg_price = (
                (pos.avg_price * pos.quantity + fill_price * signed) / denom
                if denom != 0 else 0.0
            )
        elif (new_qty == 0) or ((pos.quantity > 0) != (new_qty > 0)):
            # crossed through zero -> remaining lot opens at fill price
            pos.avg_price = fill_price if new_qty != 0 else 0.0
        pos.quantity = new_qty

        cash_delta = -signed * fill_price - commission  # buy: cash down; sell/short: cash up
        self.cash += cash_delta
        self.total_commission += commission

        fill = Fill(ts, symbol, side, quantity, fill_price, commission, cash_delta)
        self.fills.append(fill)
        return fill

    # ---- valuation ------------------------------------------------------ #
    def equity(self, prices: Dict[str, float]) -> float:
        mv = sum(p.market_value(prices[s]) for s, p in self.positions.items() if s in prices)
        return self.cash + mv

    def gross_exposure(self, prices: Dict[str, float]) -> float:
        return sum(abs(p.market_value(prices.get(s, 0.0))) for s, p in self.positions.items())

    def mark(self, prices: Dict[str, float], ts: Optional[datetime] = None) -> float:
        eq = self.equity(prices)
        self.equity_curve.append((ts, eq))
        return eq

    # ---- portfolio-level driver ---------------------------------------- #
    def rebalance_to_weights(self, target_weights: Dict[str, float],
                             prices: Dict[str, float], ts: Optional[datetime] = None) -> None:
        """Trade the book to target weights (fraction of current equity).

        Positive weight = long, negative = short. Symbols absent from
        target_weights are flattened.
        """
        eq = self.equity(prices)
        if eq <= 0:
            return
        symbols = set(target_weights) | set(self.positions)
        for sym in symbols:
            px = prices.get(sym)
            if not px or px <= 0:
                continue
            target_qty = (target_weights.get(sym, 0.0) * eq) / px
            cur_qty = self.positions.get(sym, Position(sym)).quantity
            delta = target_qty - cur_qty
            if abs(delta * px) < 1e-6:
                continue
            side = OrderSide.BUY if delta > 0 else OrderSide.SELL
            self.submit(sym, side, abs(delta), px, ts)

    # ---- summary -------------------------------------------------------- #
    def summary(self, prices: Dict[str, float]) -> Dict:
        eq = self.equity(prices)
        return {
            "equity": eq,
            "cash": self.cash,
            "return_pct": (eq / self.starting_cash - 1.0) * 100.0,
            "n_fills": len(self.fills),
            "total_commission": self.total_commission,
            "open_positions": {s: p.quantity for s, p in self.positions.items() if abs(p.quantity) > 1e-9},
        }
