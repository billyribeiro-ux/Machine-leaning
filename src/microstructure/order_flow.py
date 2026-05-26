"""
Revolution Alpha Engine - Market Microstructure Analysis

Institutional-grade order flow and market microstructure analysis:
- Order flow imbalance detection
- Dark pool activity tracking
- Smart money footprint identification
- Liquidity analysis
- Toxic flow detection
- VPIN (Volume-Synchronized Probability of Informed Trading)
"""

import numpy as np
from typing import Optional, List, Dict, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from collections import deque
from enum import Enum
import logging
import math

logger = logging.getLogger(__name__)


class OrderType(str, Enum):
    """Order type classification."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    ICEBERG = "iceberg"
    HIDDEN = "hidden"


class TradeClassification(str, Enum):
    """Trade classification for order flow."""
    BUY = "buy"
    SELL = "sell"
    NEUTRAL = "neutral"


class FlowToxicity(str, Enum):
    """Flow toxicity levels."""
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    EXTREME = "extreme"


@dataclass
class Trade:
    """Individual trade record."""
    timestamp: datetime
    price: float
    size: int
    side: TradeClassification
    exchange: str = "unknown"
    conditions: List[str] = field(default_factory=list)

    @property
    def dollar_volume(self) -> float:
        return self.price * self.size

    @property
    def is_block(self) -> bool:
        """Check if this is a block trade (>10k shares or $200k)."""
        return self.size >= 10000 or self.dollar_volume >= 200000

    @property
    def is_odd_lot(self) -> bool:
        """Check if this is an odd lot (<100 shares)."""
        return self.size < 100


@dataclass
class Quote:
    """Best bid/offer quote."""
    timestamp: datetime
    bid: float
    bid_size: int
    ask: float
    ask_size: int

    @property
    def spread(self) -> float:
        return self.ask - self.bid

    @property
    def spread_bps(self) -> float:
        mid = (self.bid + self.ask) / 2
        return (self.spread / mid) * 10000 if mid > 0 else 0

    @property
    def mid_price(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def imbalance(self) -> float:
        """Order book imbalance: positive = more bids."""
        total = self.bid_size + self.ask_size
        if total == 0:
            return 0
        return (self.bid_size - self.ask_size) / total


@dataclass
class OrderBookLevel:
    """Single level in order book."""
    price: float
    size: int
    order_count: int
    timestamp: datetime


@dataclass
class OrderBook:
    """Full order book snapshot."""
    symbol: str
    timestamp: datetime
    bids: List[OrderBookLevel] = field(default_factory=list)
    asks: List[OrderBookLevel] = field(default_factory=list)

    @property
    def best_bid(self) -> Optional[float]:
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> Optional[float]:
        return self.asks[0].price if self.asks else None

    @property
    def mid_price(self) -> Optional[float]:
        if self.best_bid and self.best_ask:
            return (self.best_bid + self.best_ask) / 2
        return None

    @property
    def spread(self) -> Optional[float]:
        if self.best_bid and self.best_ask:
            return self.best_ask - self.best_bid
        return None

    def depth_at_level(self, levels: int = 5) -> Tuple[int, int]:
        """Get total depth at top N levels."""
        bid_depth = sum(level.size for level in self.bids[:levels])
        ask_depth = sum(level.size for level in self.asks[:levels])
        return bid_depth, ask_depth

    def weighted_mid_price(self, levels: int = 5) -> float:
        """Calculate volume-weighted mid price."""
        bid_depth, ask_depth = self.depth_at_level(levels)
        total = bid_depth + ask_depth

        if total == 0 or not self.best_bid or not self.best_ask:
            return self.mid_price or 0

        # Weight by opposite side depth
        return (self.best_bid * ask_depth + self.best_ask * bid_depth) / total


@dataclass
class OrderFlowMetrics:
    """Aggregated order flow metrics."""
    symbol: str
    timestamp: datetime
    period_seconds: int

    # Volume metrics
    buy_volume: int = 0
    sell_volume: int = 0
    total_volume: int = 0

    # Trade count metrics
    buy_trades: int = 0
    sell_trades: int = 0
    total_trades: int = 0

    # Dollar metrics
    buy_dollar_volume: float = 0
    sell_dollar_volume: float = 0

    # Block trades
    block_buy_volume: int = 0
    block_sell_volume: int = 0
    block_count: int = 0

    # Price levels
    vwap: float = 0
    high: float = 0
    low: float = 0

    # Spread metrics
    avg_spread_bps: float = 0
    max_spread_bps: float = 0

    @property
    def net_volume(self) -> int:
        """Net buying pressure."""
        return self.buy_volume - self.sell_volume

    @property
    def volume_imbalance(self) -> float:
        """Volume imbalance ratio (-1 to 1)."""
        if self.total_volume == 0:
            return 0
        return self.net_volume / self.total_volume

    @property
    def trade_imbalance(self) -> float:
        """Trade count imbalance ratio."""
        total = self.buy_trades + self.sell_trades
        if total == 0:
            return 0
        return (self.buy_trades - self.sell_trades) / total

    @property
    def avg_trade_size(self) -> float:
        """Average trade size."""
        if self.total_trades == 0:
            return 0
        return self.total_volume / self.total_trades

    @property
    def block_percentage(self) -> float:
        """Percentage of volume from block trades."""
        if self.total_volume == 0:
            return 0
        block_vol = self.block_buy_volume + self.block_sell_volume
        return (block_vol / self.total_volume) * 100


class TradeClassifier:
    """
    Classify trades as buyer or seller initiated.

    Uses multiple methods:
    - Lee-Ready algorithm
    - Tick rule
    - Quote rule
    - Bulk Volume Classification
    """

    def __init__(self, quote_delay_ms: int = 100):
        self.quote_delay_ms = quote_delay_ms
        self._last_trade_price: Optional[float] = None
        self._last_quote: Optional[Quote] = None

    def classify(
        self,
        trade: Trade,
        quote: Optional[Quote] = None
    ) -> TradeClassification:
        """
        Classify trade using Lee-Ready algorithm.

        1. Quote rule: If trade price > mid, it's a buy
        2. Tick rule: If trade price > last trade, it's a buy
        """
        if quote:
            self._last_quote = quote

        # Quote rule (primary)
        if self._last_quote:
            mid = self._last_quote.mid_price

            if trade.price > mid:
                classification = TradeClassification.BUY
            elif trade.price < mid:
                classification = TradeClassification.SELL
            elif trade.price == self._last_quote.ask:
                classification = TradeClassification.BUY
            elif trade.price == self._last_quote.bid:
                classification = TradeClassification.SELL
            else:
                # Fall back to tick rule
                classification = self._tick_rule(trade.price)
        else:
            classification = self._tick_rule(trade.price)

        self._last_trade_price = trade.price
        return classification

    def _tick_rule(self, price: float) -> TradeClassification:
        """Classify based on price change from last trade."""
        if self._last_trade_price is None:
            return TradeClassification.NEUTRAL

        if price > self._last_trade_price:
            return TradeClassification.BUY
        elif price < self._last_trade_price:
            return TradeClassification.SELL
        else:
            return TradeClassification.NEUTRAL

    def bulk_classify(
        self,
        trades: List[Trade],
        quotes: List[Quote]
    ) -> List[TradeClassification]:
        """Classify multiple trades with corresponding quotes."""
        classifications = []
        quote_idx = 0

        for trade in trades:
            # Find applicable quote (before trade time)
            while (quote_idx < len(quotes) - 1 and
                   quotes[quote_idx + 1].timestamp <= trade.timestamp):
                quote_idx += 1

            quote = quotes[quote_idx] if quote_idx < len(quotes) else None
            classifications.append(self.classify(trade, quote))

        return classifications


class VPINCalculator:
    """
    Volume-Synchronized Probability of Informed Trading (VPIN).

    VPIN measures the probability that trades are coming from
    informed traders, which can predict volatility and flash crashes.
    """

    def __init__(
        self,
        bucket_size: int = 50000,  # Volume per bucket
        num_buckets: int = 50,  # Number of buckets for calculation
    ):
        self.bucket_size = bucket_size
        self.num_buckets = num_buckets

        self._current_bucket_buy = 0
        self._current_bucket_sell = 0
        self._current_bucket_volume = 0

        self._buckets: deque = deque(maxlen=num_buckets)

    def update(
        self,
        volume: int,
        classification: TradeClassification
    ) -> Optional[float]:
        """
        Update VPIN with new trade.

        Returns VPIN value when a bucket is complete.
        """
        remaining = volume

        while remaining > 0:
            space_in_bucket = self.bucket_size - self._current_bucket_volume
            to_add = min(remaining, space_in_bucket)

            if classification == TradeClassification.BUY:
                self._current_bucket_buy += to_add
            elif classification == TradeClassification.SELL:
                self._current_bucket_sell += to_add
            else:
                # Split neutral evenly
                self._current_bucket_buy += to_add // 2
                self._current_bucket_sell += to_add // 2

            self._current_bucket_volume += to_add
            remaining -= to_add

            if self._current_bucket_volume >= self.bucket_size:
                # Bucket complete
                self._buckets.append({
                    'buy': self._current_bucket_buy,
                    'sell': self._current_bucket_sell,
                })
                self._current_bucket_buy = 0
                self._current_bucket_sell = 0
                self._current_bucket_volume = 0

        return self.calculate_vpin() if len(self._buckets) >= self.num_buckets else None

    def calculate_vpin(self) -> float:
        """Calculate current VPIN value."""
        if len(self._buckets) < self.num_buckets:
            return 0

        total_imbalance = 0
        total_volume = 0

        for bucket in self._buckets:
            imbalance = abs(bucket['buy'] - bucket['sell'])
            total_imbalance += imbalance
            total_volume += bucket['buy'] + bucket['sell']

        if total_volume == 0:
            return 0

        return total_imbalance / total_volume

    @property
    def toxicity_level(self) -> FlowToxicity:
        """Classify current flow toxicity."""
        vpin = self.calculate_vpin()

        if vpin >= 0.8:
            return FlowToxicity.EXTREME
        elif vpin >= 0.6:
            return FlowToxicity.HIGH
        elif vpin >= 0.4:
            return FlowToxicity.MODERATE
        else:
            return FlowToxicity.LOW


class OrderFlowAnalyzer:
    """
    Comprehensive order flow analysis engine.

    Analyzes trade and quote data to detect:
    - Institutional buying/selling
    - Smart money accumulation/distribution
    - Hidden liquidity
    - Order flow toxicity
    """

    def __init__(
        self,
        symbol: str,
        vpin_bucket_size: int = 50000,
        lookback_trades: int = 10000
    ):
        self.symbol = symbol

        # Components
        self.classifier = TradeClassifier()
        self.vpin_calculator = VPINCalculator(vpin_bucket_size)

        # Trade history
        self._trades: deque = deque(maxlen=lookback_trades)
        self._quotes: deque = deque(maxlen=lookback_trades)

        # Aggregation windows
        self._metrics_1m: Optional[OrderFlowMetrics] = None
        self._metrics_5m: Optional[OrderFlowMetrics] = None
        self._metrics_15m: Optional[OrderFlowMetrics] = None

        # Block trade tracking
        self._recent_blocks: deque = deque(maxlen=100)

        # Dark pool estimates
        self._dark_pool_volume = 0
        self._lit_volume = 0

    def process_trade(self, trade: Trade, quote: Optional[Quote] = None):
        """Process a new trade."""
        # Classify trade
        classification = self.classifier.classify(trade, quote)
        trade.side = classification

        # Add to history
        self._trades.append(trade)

        # Update VPIN
        self.vpin_calculator.update(trade.size, classification)

        # Track blocks
        if trade.is_block:
            self._recent_blocks.append(trade)

        # Check for dark pool indicators
        self._detect_dark_pool(trade)

    def process_quote(self, quote: Quote):
        """Process a new quote."""
        self._quotes.append(quote)

    def _detect_dark_pool(self, trade: Trade):
        """
        Detect potential dark pool activity.

        Indicators:
        - Large trades at mid-price
        - Trades with 'D' condition code
        - Odd timing patterns
        """
        if 'D' in trade.conditions or 'dark' in str(trade.exchange).lower():
            self._dark_pool_volume += trade.size
        else:
            self._lit_volume += trade.size

        # Large mid-price executions often indicate dark pools
        if self._quotes and trade.is_block:
            last_quote = self._quotes[-1]
            mid = last_quote.mid_price
            if abs(trade.price - mid) < last_quote.spread * 0.1:
                self._dark_pool_volume += trade.size * 0.5  # Partial attribution

    def calculate_metrics(self, period_seconds: int = 60) -> OrderFlowMetrics:
        """Calculate order flow metrics for given period."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=period_seconds)

        metrics = OrderFlowMetrics(
            symbol=self.symbol,
            timestamp=now,
            period_seconds=period_seconds,
        )

        prices = []
        volumes = []
        spreads = []

        for trade in self._trades:
            if trade.timestamp < cutoff:
                continue

            metrics.total_volume += trade.size
            metrics.total_trades += 1

            if trade.side == TradeClassification.BUY:
                metrics.buy_volume += trade.size
                metrics.buy_trades += 1
                metrics.buy_dollar_volume += trade.dollar_volume
                if trade.is_block:
                    metrics.block_buy_volume += trade.size
            elif trade.side == TradeClassification.SELL:
                metrics.sell_volume += trade.size
                metrics.sell_trades += 1
                metrics.sell_dollar_volume += trade.dollar_volume
                if trade.is_block:
                    metrics.block_sell_volume += trade.size

            if trade.is_block:
                metrics.block_count += 1

            prices.append(trade.price)
            volumes.append(trade.size)

            if metrics.high == 0 or trade.price > metrics.high:
                metrics.high = trade.price
            if metrics.low == 0 or trade.price < metrics.low:
                metrics.low = trade.price

        # Calculate VWAP
        if volumes and sum(volumes) > 0:
            metrics.vwap = sum(p * v for p, v in zip(prices, volumes)) / sum(volumes)

        # Calculate spread metrics
        for quote in self._quotes:
            if quote.timestamp >= cutoff:
                spreads.append(quote.spread_bps)

        if spreads:
            metrics.avg_spread_bps = np.mean(spreads)
            metrics.max_spread_bps = max(spreads)

        return metrics

    def detect_institutional_activity(self) -> Dict[str, Any]:
        """
        Detect institutional buying/selling patterns.

        Looks for:
        - Large block trades
        - Consistent directional pressure
        - Accumulation/distribution patterns
        - TWAP/VWAP execution patterns
        """
        metrics = self.calculate_metrics(300)  # 5 minutes

        signals = {
            'detected': False,
            'direction': None,
            'confidence': 0,
            'indicators': [],
        }

        # Block trade analysis
        if metrics.block_percentage > 30:
            signals['indicators'].append('high_block_percentage')

            if metrics.block_buy_volume > metrics.block_sell_volume * 1.5:
                signals['direction'] = 'accumulation'
                signals['confidence'] += 25
            elif metrics.block_sell_volume > metrics.block_buy_volume * 1.5:
                signals['direction'] = 'distribution'
                signals['confidence'] += 25

        # Consistent flow pressure
        if abs(metrics.volume_imbalance) > 0.3:
            signals['indicators'].append('strong_flow_imbalance')
            signals['confidence'] += 20

            if metrics.volume_imbalance > 0:
                signals['direction'] = signals.get('direction') or 'accumulation'
            else:
                signals['direction'] = signals.get('direction') or 'distribution'

        # VPIN toxicity
        vpin = self.vpin_calculator.calculate_vpin()
        if vpin > 0.5:
            signals['indicators'].append('elevated_vpin')
            signals['confidence'] += 15

        # Trade size analysis
        if metrics.avg_trade_size > 500:  # Large average size
            signals['indicators'].append('large_avg_trade_size')
            signals['confidence'] += 10

        signals['detected'] = signals['confidence'] >= 40
        signals['vpin'] = vpin
        signals['metrics'] = metrics

        return signals

    def get_flow_summary(self) -> Dict[str, Any]:
        """Get comprehensive order flow summary."""
        metrics_1m = self.calculate_metrics(60)
        metrics_5m = self.calculate_metrics(300)
        metrics_15m = self.calculate_metrics(900)

        institutional = self.detect_institutional_activity()

        dark_pool_pct = 0
        total = self._dark_pool_volume + self._lit_volume
        if total > 0:
            dark_pool_pct = (self._dark_pool_volume / total) * 100

        return {
            'symbol': self.symbol,
            'timestamp': datetime.now(timezone.utc),
            'metrics_1m': metrics_1m,
            'metrics_5m': metrics_5m,
            'metrics_15m': metrics_15m,
            'vpin': self.vpin_calculator.calculate_vpin(),
            'toxicity': self.vpin_calculator.toxicity_level.value,
            'institutional_activity': institutional,
            'dark_pool_estimate_pct': dark_pool_pct,
            'recent_blocks': len(self._recent_blocks),
        }


class SmartMoneyDetector:
    """
    Detect smart money footprints in order flow.

    Analyzes patterns that typically indicate institutional
    or informed trading activity.
    """

    def __init__(self):
        self._signals: List[Dict] = []

    def analyze(
        self,
        analyzer: OrderFlowAnalyzer,
        order_book: Optional[OrderBook] = None
    ) -> Dict[str, Any]:
        """
        Analyze for smart money activity.

        Returns detected patterns and confidence scores.
        """
        patterns = []
        total_confidence = 0

        # Get flow data
        flow_summary = analyzer.get_flow_summary()
        metrics = flow_summary['metrics_5m']

        # Pattern 1: Iceberg detection (large hidden orders)
        iceberg = self._detect_iceberg(analyzer, order_book)
        if iceberg['detected']:
            patterns.append(iceberg)
            total_confidence += iceberg['confidence']

        # Pattern 2: Absorption (large orders absorbed at level)
        absorption = self._detect_absorption(analyzer, order_book)
        if absorption['detected']:
            patterns.append(absorption)
            total_confidence += absorption['confidence']

        # Pattern 3: Sweep (aggressive order taking liquidity)
        sweep = self._detect_sweep(analyzer)
        if sweep['detected']:
            patterns.append(sweep)
            total_confidence += sweep['confidence']

        # Pattern 4: Accumulation (stealth buying)
        accumulation = self._detect_accumulation(metrics)
        if accumulation['detected']:
            patterns.append(accumulation)
            total_confidence += accumulation['confidence']

        # Pattern 5: Exhaustion (selling pressure exhausting)
        exhaustion = self._detect_exhaustion(analyzer)
        if exhaustion['detected']:
            patterns.append(exhaustion)
            total_confidence += exhaustion['confidence']

        # Combine signals
        direction = None
        if patterns:
            bullish = sum(1 for p in patterns if p.get('bias') == 'bullish')
            bearish = sum(1 for p in patterns if p.get('bias') == 'bearish')

            if bullish > bearish:
                direction = 'bullish'
            elif bearish > bullish:
                direction = 'bearish'

        return {
            'smart_money_detected': len(patterns) > 0,
            'patterns': patterns,
            'pattern_count': len(patterns),
            'total_confidence': min(100, total_confidence),
            'direction': direction,
            'flow_summary': flow_summary,
        }

    def _detect_iceberg(
        self,
        analyzer: OrderFlowAnalyzer,
        order_book: Optional[OrderBook]
    ) -> Dict[str, Any]:
        """Detect iceberg orders (hidden liquidity)."""
        result = {'name': 'iceberg', 'detected': False, 'confidence': 0, 'bias': None}

        # Look for repeated executions at same price with small shown size
        trades = list(analyzer._trades)[-100:]

        price_counts: Dict[float, int] = {}
        price_volumes: Dict[float, int] = {}

        for trade in trades:
            price = round(trade.price, 2)
            price_counts[price] = price_counts.get(price, 0) + 1
            price_volumes[price] = price_volumes.get(price, 0) + trade.size

        # Iceberg = many small trades at same price level
        for price, count in price_counts.items():
            if count >= 10:  # Many trades at same level
                avg_size = price_volumes[price] / count
                if avg_size < 500:  # Small individual trades
                    result['detected'] = True
                    result['confidence'] = min(30, count * 2)
                    result['price'] = price
                    result['trade_count'] = count
                    break

        return result

    def _detect_absorption(
        self,
        analyzer: OrderFlowAnalyzer,
        order_book: Optional[OrderBook]
    ) -> Dict[str, Any]:
        """Detect order absorption (large orders being absorbed)."""
        result = {'name': 'absorption', 'detected': False, 'confidence': 0, 'bias': None}

        metrics = analyzer.calculate_metrics(60)

        # High volume with minimal price movement suggests absorption
        if metrics.total_volume > 100000:  # Significant volume
            price_range = metrics.high - metrics.low if metrics.high and metrics.low else 0

            if price_range > 0:
                volume_per_tick = metrics.total_volume / (price_range * 100)

                if volume_per_tick > 50000:  # High volume relative to range
                    result['detected'] = True
                    result['confidence'] = min(35, int(volume_per_tick / 2000))

                    # Determine bias
                    if metrics.volume_imbalance > 0.2:
                        result['bias'] = 'bullish'
                    elif metrics.volume_imbalance < -0.2:
                        result['bias'] = 'bearish'

        return result

    def _detect_sweep(self, analyzer: OrderFlowAnalyzer) -> Dict[str, Any]:
        """Detect aggressive sweep orders."""
        result = {'name': 'sweep', 'detected': False, 'confidence': 0, 'bias': None}

        # Look for rapid sequence of large trades in same direction
        trades = list(analyzer._trades)[-50:]

        if len(trades) < 10:
            return result

        # Check for consecutive same-side large trades
        consecutive_buy = 0
        consecutive_sell = 0
        max_consecutive_buy = 0
        max_consecutive_sell = 0

        for trade in trades:
            if trade.is_block:
                if trade.side == TradeClassification.BUY:
                    consecutive_buy += 1
                    consecutive_sell = 0
                    max_consecutive_buy = max(max_consecutive_buy, consecutive_buy)
                elif trade.side == TradeClassification.SELL:
                    consecutive_sell += 1
                    consecutive_buy = 0
                    max_consecutive_sell = max(max_consecutive_sell, consecutive_sell)
            else:
                consecutive_buy = 0
                consecutive_sell = 0

        if max_consecutive_buy >= 3:
            result['detected'] = True
            result['confidence'] = min(40, max_consecutive_buy * 10)
            result['bias'] = 'bullish'
        elif max_consecutive_sell >= 3:
            result['detected'] = True
            result['confidence'] = min(40, max_consecutive_sell * 10)
            result['bias'] = 'bearish'

        return result

    def _detect_accumulation(self, metrics: OrderFlowMetrics) -> Dict[str, Any]:
        """Detect stealth accumulation pattern."""
        result = {'name': 'accumulation', 'detected': False, 'confidence': 0, 'bias': None}

        # Accumulation: steady buying with controlled impact
        if metrics.volume_imbalance > 0.2 and metrics.avg_spread_bps < 10:
            result['detected'] = True
            result['confidence'] = int(metrics.volume_imbalance * 50)
            result['bias'] = 'bullish'
        elif metrics.volume_imbalance < -0.2 and metrics.avg_spread_bps < 10:
            result['detected'] = True
            result['confidence'] = int(abs(metrics.volume_imbalance) * 50)
            result['bias'] = 'bearish'

        return result

    def _detect_exhaustion(self, analyzer: OrderFlowAnalyzer) -> Dict[str, Any]:
        """Detect selling/buying exhaustion."""
        result = {'name': 'exhaustion', 'detected': False, 'confidence': 0, 'bias': None}

        # Compare recent vs older flow
        recent = analyzer.calculate_metrics(60)
        older = analyzer.calculate_metrics(300)

        # Exhaustion: flow reversing with declining volume
        if older.volume_imbalance < -0.3 and recent.volume_imbalance > 0:
            if recent.total_volume < older.total_volume * 0.3:
                result['detected'] = True
                result['confidence'] = 30
                result['bias'] = 'bullish'  # Selling exhaustion = bullish
        elif older.volume_imbalance > 0.3 and recent.volume_imbalance < 0:
            if recent.total_volume < older.total_volume * 0.3:
                result['detected'] = True
                result['confidence'] = 30
                result['bias'] = 'bearish'  # Buying exhaustion = bearish

        return result
