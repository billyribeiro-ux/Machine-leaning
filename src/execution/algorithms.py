"""
Professional Execution Algorithms.

Institutional-grade execution algorithms for minimizing market impact:
- TWAP (Time-Weighted Average Price)
- VWAP (Volume-Weighted Average Price)
- Implementation Shortfall
- Participation Rate
- Adaptive Execution
- Dark Pool Routing
- Smart Order Routing (SOR)

These algorithms are used by major institutions to execute
large orders while minimizing slippage and market impact.
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
import asyncio
import logging
from abc import ABC, abstractmethod
from collections import deque


logger = logging.getLogger(__name__)


class OrderSide(Enum):
    """Order side."""
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    """Order type."""
    MARKET = "market"
    LIMIT = "limit"
    LIMIT_ON_CLOSE = "loc"
    MARKET_ON_CLOSE = "moc"


class ExecutionStrategy(Enum):
    """Execution strategy type."""
    TWAP = "twap"
    VWAP = "vwap"
    IS = "implementation_shortfall"
    POV = "percent_of_volume"
    ADAPTIVE = "adaptive"
    DARK = "dark_pool"
    SOR = "smart_order_routing"


class ExecutionVenue(Enum):
    """Execution venues."""
    NYSE = "nyse"
    NASDAQ = "nasdaq"
    ARCA = "arca"
    BATS = "bats"
    IEX = "iex"
    DARK_POOL = "dark_pool"


@dataclass
class SliceOrder:
    """Individual slice of a parent order."""
    order_id: str
    parent_id: str
    symbol: str
    side: OrderSide
    quantity: int
    order_type: OrderType
    limit_price: Optional[float] = None
    venue: Optional[ExecutionVenue] = None
    scheduled_time: Optional[datetime] = None
    sent_time: Optional[datetime] = None
    filled_time: Optional[datetime] = None
    filled_quantity: int = 0
    filled_price: float = 0.0
    status: str = "pending"


@dataclass
class ExecutionPlan:
    """Complete execution plan for a parent order."""
    order_id: str
    symbol: str
    side: OrderSide
    total_quantity: int
    strategy: ExecutionStrategy
    slices: List[SliceOrder] = field(default_factory=list)
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None
    arrival_price: float = 0.0
    benchmark_price: float = 0.0
    urgency: float = 0.5  # 0-1, higher = more aggressive


@dataclass
class ExecutionReport:
    """Execution performance report."""
    order_id: str
    symbol: str
    side: OrderSide
    total_quantity: int
    filled_quantity: int
    average_price: float
    arrival_price: float
    vwap_price: float
    slippage_bps: float  # Basis points vs arrival
    vwap_slippage_bps: float
    implementation_shortfall_bps: float
    market_impact_bps: float
    timing_cost_bps: float
    execution_time_seconds: float
    participation_rate: float
    fill_rate: float


@dataclass
class MarketMicrostructure:
    """Real-time market microstructure data."""
    symbol: str
    timestamp: datetime
    bid: float
    ask: float
    mid: float
    spread_bps: float
    bid_size: int
    ask_size: int
    last_price: float
    last_size: int
    volume: int
    vwap: float
    volatility: float
    imbalance: float  # Order book imbalance


class VolumeProfile:
    """Historical volume profile for VWAP calculations."""

    def __init__(self, intraday_buckets: int = 78):  # 5-min buckets for 6.5hr day
        self.n_buckets = intraday_buckets
        self.volume_profile: np.ndarray = np.ones(intraday_buckets) / intraday_buckets

    def update(self, historical_volumes: List[List[float]]):
        """Update volume profile from historical data."""
        if not historical_volumes:
            return

        # Average across days
        profile = np.zeros(self.n_buckets)
        count = 0

        for day_volumes in historical_volumes:
            if len(day_volumes) >= self.n_buckets:
                profile += np.array(day_volumes[:self.n_buckets])
                count += 1

        if count > 0:
            profile /= count
            self.volume_profile = profile / profile.sum()

    def get_target_participation(
        self,
        start_bucket: int,
        end_bucket: int,
    ) -> np.ndarray:
        """Get target participation for each bucket."""
        participation = self.volume_profile[start_bucket:end_bucket].copy()
        return participation / participation.sum()


class ExecutionAlgorithm(ABC):
    """Base class for execution algorithms."""

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.slices: List[SliceOrder] = []
        self.is_running = False

    @abstractmethod
    def generate_schedule(
        self,
        total_quantity: int,
        side: OrderSide,
        start_time: datetime,
        end_time: datetime,
        **kwargs,
    ) -> List[SliceOrder]:
        """Generate execution schedule."""
        pass

    @abstractmethod
    def should_send_now(
        self,
        slice_order: SliceOrder,
        market_data: MarketMicrostructure,
    ) -> Tuple[bool, Optional[float]]:
        """Determine if slice should be sent now."""
        pass


class TWAPAlgorithm(ExecutionAlgorithm):
    """
    Time-Weighted Average Price Algorithm.

    Splits order equally across time intervals.
    Simple but effective for non-urgent orders.
    """

    def __init__(
        self,
        symbol: str,
        randomize: bool = True,
        randomize_pct: float = 0.2,
    ):
        super().__init__(symbol)
        self.randomize = randomize
        self.randomize_pct = randomize_pct

    def generate_schedule(
        self,
        total_quantity: int,
        side: OrderSide,
        start_time: datetime,
        end_time: datetime,
        n_slices: int = 20,
        **kwargs,
    ) -> List[SliceOrder]:
        """Generate TWAP schedule."""
        duration = (end_time - start_time).total_seconds()
        interval = duration / n_slices

        base_quantity = total_quantity // n_slices
        remainder = total_quantity % n_slices

        slices = []

        for i in range(n_slices):
            # Calculate quantity for this slice
            qty = base_quantity + (1 if i < remainder else 0)

            # Calculate scheduled time
            scheduled_time = start_time + timedelta(seconds=interval * i)

            # Optionally randomize timing
            if self.randomize:
                offset = np.random.uniform(
                    -interval * self.randomize_pct,
                    interval * self.randomize_pct
                )
                scheduled_time += timedelta(seconds=offset)

            slices.append(SliceOrder(
                order_id=f"TWAP_{i}_{datetime.now(timezone.utc).timestamp()}",
                parent_id="",
                symbol=self.symbol,
                side=side,
                quantity=qty,
                order_type=OrderType.LIMIT,
                scheduled_time=scheduled_time,
            ))

        self.slices = slices
        return slices

    def should_send_now(
        self,
        slice_order: SliceOrder,
        market_data: MarketMicrostructure,
    ) -> Tuple[bool, Optional[float]]:
        """Check if slice should be sent."""
        now = datetime.now(timezone.utc)

        if slice_order.scheduled_time and now >= slice_order.scheduled_time:
            # Calculate limit price
            if slice_order.side == OrderSide.BUY:
                limit_price = market_data.ask * 1.001  # Slightly above ask
            else:
                limit_price = market_data.bid * 0.999  # Slightly below bid

            return True, limit_price

        return False, None


class VWAPAlgorithm(ExecutionAlgorithm):
    """
    Volume-Weighted Average Price Algorithm.

    Executes according to historical volume profile to match
    or beat the day's VWAP.
    """

    def __init__(
        self,
        symbol: str,
        volume_profile: Optional[VolumeProfile] = None,
        min_participation: float = 0.05,
        max_participation: float = 0.25,
    ):
        super().__init__(symbol)
        self.volume_profile = volume_profile or VolumeProfile()
        self.min_participation = min_participation
        self.max_participation = max_participation

    def generate_schedule(
        self,
        total_quantity: int,
        side: OrderSide,
        start_time: datetime,
        end_time: datetime,
        n_slices: int = 39,  # 10-min intervals
        **kwargs,
    ) -> List[SliceOrder]:
        """Generate VWAP schedule based on volume profile."""
        # Get target participation
        start_bucket = self._time_to_bucket(start_time)
        end_bucket = self._time_to_bucket(end_time)

        if start_bucket >= end_bucket:
            end_bucket = start_bucket + 1

        participation = self.volume_profile.get_target_participation(
            start_bucket, min(end_bucket, self.volume_profile.n_buckets)
        )

        # Allocate quantity according to volume profile
        duration = (end_time - start_time).total_seconds()
        interval = duration / len(participation)

        slices = []
        remaining = total_quantity

        for i, pct in enumerate(participation):
            qty = min(int(total_quantity * pct), remaining)
            if qty <= 0:
                continue

            remaining -= qty

            scheduled_time = start_time + timedelta(seconds=interval * i)

            slices.append(SliceOrder(
                order_id=f"VWAP_{i}_{datetime.now(timezone.utc).timestamp()}",
                parent_id="",
                symbol=self.symbol,
                side=side,
                quantity=qty,
                order_type=OrderType.LIMIT,
                scheduled_time=scheduled_time,
            ))

        # Distribute any remainder
        if remaining > 0 and slices:
            slices[-1].quantity += remaining

        self.slices = slices
        return slices

    def _time_to_bucket(self, time: datetime) -> int:
        """Convert time to volume profile bucket."""
        # Assume market opens at 9:30 AM
        market_open = time.replace(hour=9, minute=30, second=0)
        minutes_since_open = (time - market_open).total_seconds() / 60
        bucket = int(minutes_since_open / 5)  # 5-minute buckets
        return max(0, min(bucket, self.volume_profile.n_buckets - 1))

    def should_send_now(
        self,
        slice_order: SliceOrder,
        market_data: MarketMicrostructure,
    ) -> Tuple[bool, Optional[float]]:
        """Check if slice should be sent based on volume."""
        now = datetime.now(timezone.utc)

        if slice_order.scheduled_time and now >= slice_order.scheduled_time:
            # Adjust participation based on actual volume
            participation_rate = slice_order.quantity / max(market_data.volume, 1)

            if participation_rate > self.max_participation:
                # Volume too low - be passive
                if slice_order.side == OrderSide.BUY:
                    limit_price = market_data.bid
                else:
                    limit_price = market_data.ask
            else:
                # Normal - be slightly aggressive
                if slice_order.side == OrderSide.BUY:
                    limit_price = market_data.mid
                else:
                    limit_price = market_data.mid

            return True, limit_price

        return False, None


class ImplementationShortfallAlgorithm(ExecutionAlgorithm):
    """
    Implementation Shortfall Algorithm.

    Minimizes implementation shortfall (difference between
    arrival price and execution price) by trading off
    market impact vs timing risk.
    """

    def __init__(
        self,
        symbol: str,
        urgency: float = 0.5,
        risk_aversion: float = 1.0,
        volatility: float = 0.02,
        temporary_impact: float = 0.1,
        permanent_impact: float = 0.05,
    ):
        super().__init__(symbol)
        self.urgency = urgency
        self.risk_aversion = risk_aversion
        self.volatility = volatility
        self.temporary_impact = temporary_impact
        self.permanent_impact = permanent_impact

    def generate_schedule(
        self,
        total_quantity: int,
        side: OrderSide,
        start_time: datetime,
        end_time: datetime,
        **kwargs,
    ) -> List[SliceOrder]:
        """
        Generate optimal trading trajectory using Almgren-Chriss model.
        """
        duration = (end_time - start_time).total_seconds()
        n_periods = max(10, int(duration / 300))  # 5-min periods

        # Almgren-Chriss optimal trajectory
        kappa = np.sqrt(
            self.risk_aversion * self.volatility ** 2 /
            (self.temporary_impact + 1e-8)
        )

        # Calculate optimal trading rate
        times = np.linspace(0, duration, n_periods + 1)
        trajectory = []

        for i in range(n_periods):
            t = times[i]
            T = duration

            # Remaining quantity at time t
            if kappa * T < 1e-6:
                remaining_pct = 1 - t / T
            else:
                remaining_pct = np.sinh(kappa * (T - t)) / np.sinh(kappa * T)

            trajectory.append(remaining_pct)

        trajectory.append(0)  # End with nothing remaining

        # Convert trajectory to quantities
        quantities = []
        for i in range(n_periods):
            qty = int(total_quantity * (trajectory[i] - trajectory[i + 1]))
            quantities.append(qty)

        # Adjust for rounding
        total_scheduled = sum(quantities)
        if total_scheduled != total_quantity and quantities:
            quantities[-1] += total_quantity - total_scheduled

        # Create slices
        interval = duration / n_periods
        slices = []

        for i, qty in enumerate(quantities):
            if qty <= 0:
                continue

            slices.append(SliceOrder(
                order_id=f"IS_{i}_{datetime.now(timezone.utc).timestamp()}",
                parent_id="",
                symbol=self.symbol,
                side=side,
                quantity=qty,
                order_type=OrderType.LIMIT,
                scheduled_time=start_time + timedelta(seconds=interval * i),
            ))

        self.slices = slices
        return slices

    def should_send_now(
        self,
        slice_order: SliceOrder,
        market_data: MarketMicrostructure,
    ) -> Tuple[bool, Optional[float]]:
        """Adaptive execution based on market conditions."""
        now = datetime.now(timezone.utc)

        if not slice_order.scheduled_time:
            return False, None

        time_diff = (now - slice_order.scheduled_time).total_seconds()

        if time_diff < 0:
            return False, None

        # More aggressive if behind schedule
        aggression = min(1.0, self.urgency + time_diff / 300)

        # Calculate limit price based on aggression
        if slice_order.side == OrderSide.BUY:
            limit_price = (
                market_data.bid * (1 - aggression) +
                market_data.ask * aggression
            )
        else:
            limit_price = (
                market_data.ask * (1 - aggression) +
                market_data.bid * aggression
            )

        return True, limit_price


class AdaptiveAlgorithm(ExecutionAlgorithm):
    """
    Adaptive Execution Algorithm.

    Dynamically adjusts execution based on real-time
    market conditions and order book state.
    """

    def __init__(
        self,
        symbol: str,
        base_algorithm: ExecutionAlgorithm,
        spread_threshold: float = 0.001,
        volatility_threshold: float = 0.02,
        imbalance_threshold: float = 0.3,
    ):
        super().__init__(symbol)
        self.base_algorithm = base_algorithm
        self.spread_threshold = spread_threshold
        self.volatility_threshold = volatility_threshold
        self.imbalance_threshold = imbalance_threshold

        self.current_regime: str = "normal"

    def generate_schedule(
        self,
        total_quantity: int,
        side: OrderSide,
        start_time: datetime,
        end_time: datetime,
        **kwargs,
    ) -> List[SliceOrder]:
        """Generate schedule using base algorithm."""
        return self.base_algorithm.generate_schedule(
            total_quantity, side, start_time, end_time, **kwargs
        )

    def should_send_now(
        self,
        slice_order: SliceOrder,
        market_data: MarketMicrostructure,
    ) -> Tuple[bool, Optional[float]]:
        """Adaptively determine execution timing and price."""
        # Detect regime
        self._update_regime(market_data, slice_order.side)

        # Get base decision
        should_send, base_price = self.base_algorithm.should_send_now(
            slice_order, market_data
        )

        if not should_send:
            return False, None

        # Adapt based on regime
        if self.current_regime == "favorable":
            # Be aggressive
            if slice_order.side == OrderSide.BUY:
                limit_price = market_data.ask
            else:
                limit_price = market_data.bid
        elif self.current_regime == "unfavorable":
            # Be passive
            if slice_order.side == OrderSide.BUY:
                limit_price = market_data.bid
            else:
                limit_price = market_data.ask
        elif self.current_regime == "volatile":
            # Use wider limits
            spread = market_data.ask - market_data.bid
            if slice_order.side == OrderSide.BUY:
                limit_price = market_data.mid + spread * 0.25
            else:
                limit_price = market_data.mid - spread * 0.25
        else:
            limit_price = base_price

        return True, limit_price

    def _update_regime(
        self,
        market_data: MarketMicrostructure,
        side: OrderSide,
    ):
        """Update market regime classification."""
        # Check spread
        if market_data.spread_bps > self.spread_threshold * 10000:
            self.current_regime = "wide_spread"
            return

        # Check volatility
        if market_data.volatility > self.volatility_threshold:
            self.current_regime = "volatile"
            return

        # Check order book imbalance
        if side == OrderSide.BUY:
            if market_data.imbalance > self.imbalance_threshold:
                self.current_regime = "unfavorable"  # More buyers
            elif market_data.imbalance < -self.imbalance_threshold:
                self.current_regime = "favorable"  # More sellers
            else:
                self.current_regime = "normal"
        else:
            if market_data.imbalance < -self.imbalance_threshold:
                self.current_regime = "unfavorable"  # More sellers
            elif market_data.imbalance > self.imbalance_threshold:
                self.current_regime = "favorable"  # More buyers
            else:
                self.current_regime = "normal"


class SmartOrderRouter:
    """
    Smart Order Router (SOR).

    Routes orders across multiple venues to achieve
    best execution.
    """

    def __init__(
        self,
        venues: List[ExecutionVenue],
        dark_pool_threshold: int = 1000,
    ):
        self.venues = venues
        self.dark_pool_threshold = dark_pool_threshold

        # Venue statistics
        self.venue_stats: Dict[ExecutionVenue, Dict[str, float]] = {
            venue: {
                "fill_rate": 0.8,
                "avg_improvement": 0.0,
                "latency_ms": 1.0,
            }
            for venue in venues
        }

    def route(
        self,
        slice_order: SliceOrder,
        market_data: Dict[ExecutionVenue, MarketMicrostructure],
    ) -> List[Tuple[ExecutionVenue, int, float]]:
        """
        Route order across venues.

        Returns list of (venue, quantity, limit_price) tuples.
        """
        routes = []
        remaining = slice_order.quantity

        # Check dark pool first for large orders
        if remaining >= self.dark_pool_threshold:
            dark_qty = min(remaining, int(remaining * 0.5))
            routes.append((ExecutionVenue.DARK_POOL, dark_qty, None))
            remaining -= dark_qty

        # Find best lit venue
        best_venue = None
        best_price = None

        for venue, data in market_data.items():
            if venue == ExecutionVenue.DARK_POOL:
                continue

            # Calculate effective price
            if slice_order.side == OrderSide.BUY:
                price = data.ask
            else:
                price = data.bid

            # Adjust for venue quality
            stats = self.venue_stats.get(venue, {})
            adjusted_price = price * (1 - stats.get("avg_improvement", 0))

            if best_price is None or (
                (slice_order.side == OrderSide.BUY and adjusted_price < best_price) or
                (slice_order.side == OrderSide.SELL and adjusted_price > best_price)
            ):
                best_price = adjusted_price
                best_venue = venue

        if best_venue and remaining > 0:
            routes.append((best_venue, remaining, best_price))

        return routes

    def update_stats(
        self,
        venue: ExecutionVenue,
        fill_rate: float,
        price_improvement: float,
        latency_ms: float,
    ):
        """Update venue statistics."""
        stats = self.venue_stats[venue]

        # Exponential moving average
        alpha = 0.1
        stats["fill_rate"] = alpha * fill_rate + (1 - alpha) * stats["fill_rate"]
        stats["avg_improvement"] = alpha * price_improvement + (1 - alpha) * stats["avg_improvement"]
        stats["latency_ms"] = alpha * latency_ms + (1 - alpha) * stats["latency_ms"]


class ExecutionEngine:
    """
    Master execution engine.

    Manages order lifecycle and execution algorithms.
    """

    def __init__(self):
        self.active_orders: Dict[str, ExecutionPlan] = {}
        self.completed_orders: Dict[str, ExecutionPlan] = {}
        self.reports: Dict[str, ExecutionReport] = {}

        self.algorithms: Dict[ExecutionStrategy, type] = {
            ExecutionStrategy.TWAP: TWAPAlgorithm,
            ExecutionStrategy.VWAP: VWAPAlgorithm,
            ExecutionStrategy.IS: ImplementationShortfallAlgorithm,
            ExecutionStrategy.ADAPTIVE: AdaptiveAlgorithm,
        }

        self.router = SmartOrderRouter([
            ExecutionVenue.NYSE,
            ExecutionVenue.NASDAQ,
            ExecutionVenue.ARCA,
            ExecutionVenue.IEX,
            ExecutionVenue.DARK_POOL,
        ])

        logger.info("ExecutionEngine initialized")

    def create_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: int,
        strategy: ExecutionStrategy,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        arrival_price: float = 0.0,
        urgency: float = 0.5,
        **kwargs,
    ) -> ExecutionPlan:
        """Create new execution order."""
        order_id = f"{symbol}_{side.value}_{datetime.now(timezone.utc).timestamp()}"

        start_time = start_time or datetime.now(timezone.utc)
        end_time = end_time or (start_time + timedelta(hours=1))

        # Create algorithm
        algo_class = self.algorithms.get(strategy, TWAPAlgorithm)
        algo = algo_class(symbol, **kwargs)

        # Generate schedule
        slices = algo.generate_schedule(
            quantity, side, start_time, end_time, **kwargs
        )

        # Create plan
        plan = ExecutionPlan(
            order_id=order_id,
            symbol=symbol,
            side=side,
            total_quantity=quantity,
            strategy=strategy,
            slices=slices,
            start_time=start_time,
            end_time=end_time,
            arrival_price=arrival_price,
            urgency=urgency,
        )

        for slice_order in plan.slices:
            slice_order.parent_id = order_id

        self.active_orders[order_id] = plan

        logger.info(f"Created {strategy.value} order: {order_id} for {quantity} {symbol}")

        return plan

    def generate_report(self, order_id: str) -> Optional[ExecutionReport]:
        """Generate execution report for completed order."""
        plan = self.completed_orders.get(order_id) or self.active_orders.get(order_id)

        if not plan:
            return None

        filled_slices = [s for s in plan.slices if s.filled_quantity > 0]

        if not filled_slices:
            return None

        total_filled = sum(s.filled_quantity for s in filled_slices)
        total_value = sum(s.filled_quantity * s.filled_price for s in filled_slices)

        avg_price = total_value / total_filled if total_filled > 0 else 0

        # Calculate slippage
        if plan.arrival_price > 0:
            if plan.side == OrderSide.BUY:
                slippage_bps = (avg_price - plan.arrival_price) / plan.arrival_price * 10000
            else:
                slippage_bps = (plan.arrival_price - avg_price) / plan.arrival_price * 10000
        else:
            slippage_bps = 0

        # Calculate execution time
        first_fill = min((s.filled_time for s in filled_slices if s.filled_time), default=plan.start_time)
        last_fill = max((s.filled_time for s in filled_slices if s.filled_time), default=datetime.now(timezone.utc))

        execution_time = (last_fill - first_fill).total_seconds() if first_fill and last_fill else 0

        report = ExecutionReport(
            order_id=order_id,
            symbol=plan.symbol,
            side=plan.side,
            total_quantity=plan.total_quantity,
            filled_quantity=total_filled,
            average_price=avg_price,
            arrival_price=plan.arrival_price,
            vwap_price=plan.benchmark_price,
            slippage_bps=slippage_bps,
            vwap_slippage_bps=0,  # Would need VWAP benchmark
            implementation_shortfall_bps=slippage_bps,  # Simplified
            market_impact_bps=slippage_bps * 0.6,  # Estimate
            timing_cost_bps=slippage_bps * 0.4,  # Estimate
            execution_time_seconds=execution_time,
            participation_rate=0.1,  # Would need volume data
            fill_rate=total_filled / plan.total_quantity,
        )

        self.reports[order_id] = report

        return report


def create_twap_algorithm(symbol: str) -> TWAPAlgorithm:
    """Create TWAP algorithm."""
    return TWAPAlgorithm(symbol)


def create_vwap_algorithm(
    symbol: str,
    volume_profile: Optional[VolumeProfile] = None,
) -> VWAPAlgorithm:
    """Create VWAP algorithm."""
    return VWAPAlgorithm(symbol, volume_profile)


def create_is_algorithm(
    symbol: str,
    urgency: float = 0.5,
) -> ImplementationShortfallAlgorithm:
    """Create Implementation Shortfall algorithm."""
    return ImplementationShortfallAlgorithm(symbol, urgency=urgency)


def create_execution_engine() -> ExecutionEngine:
    """Create execution engine."""
    return ExecutionEngine()
