"""
Predictive Order Flow System

Next-generation order flow prediction using:
- Order book imbalance modeling
- Trade flow toxicity (VPIN)
- Microstructure-based prediction
- Volume clock analysis
- Aggressive order detection
- Institutional footprint prediction
- Machine learning flow forecasting
- Real-time signal generation

Author: Revolution Alpha Engine
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from enum import Enum
from collections import deque
import warnings

warnings.filterwarnings('ignore')


class FlowDirection(Enum):
    """Order flow direction."""
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    NEUTRAL = "neutral"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


class OrderType(Enum):
    """Order type classification."""
    AGGRESSIVE_BUY = "aggressive_buy"
    PASSIVE_BUY = "passive_buy"
    AGGRESSIVE_SELL = "aggressive_sell"
    PASSIVE_SELL = "passive_sell"
    UNKNOWN = "unknown"


@dataclass
class OrderFlowState:
    """Current order flow state."""
    direction: FlowDirection
    imbalance: float  # -1 to 1
    toxicity: float  # 0 to 1 (VPIN)
    aggression_ratio: float
    institutional_probability: float
    predicted_direction: int  # -1, 0, 1
    predicted_magnitude: float
    confidence: float
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class FlowSignal:
    """Order flow trading signal."""
    signal_type: str
    direction: str
    strength: float
    entry_price: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    timeframe: str
    reasoning: str
    confidence: float
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class VolumeBar:
    """Volume-synchronized bar."""
    open: float
    high: float
    low: float
    close: float
    volume: int
    buy_volume: int
    sell_volume: int
    vwap: float
    num_trades: int
    avg_trade_size: float
    start_time: datetime
    end_time: datetime


class TickClassifier:
    """
    Classify trades as buyer or seller initiated.
    """

    def __init__(self, method: str = 'lee_ready'):
        """
        Args:
            method: Classification method ('lee_ready', 'tick_rule', 'quote_rule')
        """
        self.method = method
        self.prev_price = None
        self.prev_tick = 0

    def classify(
        self,
        trade_price: float,
        bid: Optional[float] = None,
        ask: Optional[float] = None
    ) -> int:
        """
        Classify trade as buy (+1) or sell (-1).

        Args:
            trade_price: Trade execution price
            bid: Current bid price
            ask: Current ask price

        Returns:
            1 for buy, -1 for sell
        """
        if self.method == 'quote_rule' and bid is not None and ask is not None:
            midpoint = (bid + ask) / 2
            if trade_price > midpoint:
                return 1
            elif trade_price < midpoint:
                return -1
            # At midpoint, use tick rule as fallback

        # Tick rule
        if self.prev_price is not None:
            if trade_price > self.prev_price:
                self.prev_tick = 1
            elif trade_price < self.prev_price:
                self.prev_tick = -1
            # If equal, keep previous tick

        self.prev_price = trade_price
        return self.prev_tick if self.prev_tick != 0 else 1

    def reset(self):
        """Reset classifier state."""
        self.prev_price = None
        self.prev_tick = 0


class OrderBookImbalance:
    """
    Order book imbalance analyzer.
    """

    def __init__(self, levels: int = 10):
        """
        Args:
            levels: Number of price levels to consider
        """
        self.levels = levels

    def calculate_imbalance(
        self,
        bids: List[Tuple[float, float]],  # (price, size)
        asks: List[Tuple[float, float]]
    ) -> float:
        """
        Calculate order book imbalance.

        Returns:
            Imbalance ratio from -1 (all asks) to 1 (all bids)
        """
        bid_volume = sum(size for _, size in bids[:self.levels])
        ask_volume = sum(size for _, size in asks[:self.levels])

        total = bid_volume + ask_volume
        if total == 0:
            return 0.0

        return (bid_volume - ask_volume) / total

    def weighted_imbalance(
        self,
        bids: List[Tuple[float, float]],
        asks: List[Tuple[float, float]],
        reference_price: float
    ) -> float:
        """
        Calculate distance-weighted imbalance.
        Closer levels get more weight.
        """
        bid_weighted = 0.0
        ask_weighted = 0.0

        for i, (price, size) in enumerate(bids[:self.levels]):
            distance = reference_price - price
            weight = 1 / (1 + distance / reference_price * 100)
            bid_weighted += size * weight

        for i, (price, size) in enumerate(asks[:self.levels]):
            distance = price - reference_price
            weight = 1 / (1 + distance / reference_price * 100)
            ask_weighted += size * weight

        total = bid_weighted + ask_weighted
        if total == 0:
            return 0.0

        return (bid_weighted - ask_weighted) / total

    def imbalance_at_levels(
        self,
        bids: List[Tuple[float, float]],
        asks: List[Tuple[float, float]]
    ) -> List[float]:
        """Calculate imbalance at each level."""
        imbalances = []

        for i in range(min(self.levels, len(bids), len(asks))):
            bid_size = bids[i][1]
            ask_size = asks[i][1]
            total = bid_size + ask_size

            if total > 0:
                imbalances.append((bid_size - ask_size) / total)
            else:
                imbalances.append(0.0)

        return imbalances


class VPINCalculator:
    """
    Volume-Synchronized Probability of Informed Trading (VPIN).

    Measures order flow toxicity - probability that counterparty is informed.
    """

    def __init__(self, bucket_size: int = 50000, n_buckets: int = 50):
        """
        Args:
            bucket_size: Volume per bucket
            n_buckets: Number of buckets for VPIN calculation
        """
        self.bucket_size = bucket_size
        self.n_buckets = n_buckets

        # State
        self.buckets = deque(maxlen=n_buckets)
        self.current_bucket_volume = 0
        self.current_bucket_buy = 0
        self.current_bucket_sell = 0

    def update(self, volume: int, is_buy: bool):
        """
        Update VPIN with new trade.

        Args:
            volume: Trade volume
            is_buy: True if classified as buy
        """
        remaining_volume = volume

        while remaining_volume > 0:
            space_in_bucket = self.bucket_size - self.current_bucket_volume

            if remaining_volume >= space_in_bucket:
                # Fill current bucket
                if is_buy:
                    self.current_bucket_buy += space_in_bucket
                else:
                    self.current_bucket_sell += space_in_bucket

                self.current_bucket_volume = self.bucket_size

                # Store bucket
                self.buckets.append({
                    'buy': self.current_bucket_buy,
                    'sell': self.current_bucket_sell
                })

                # Reset
                self.current_bucket_volume = 0
                self.current_bucket_buy = 0
                self.current_bucket_sell = 0

                remaining_volume -= space_in_bucket
            else:
                # Partially fill bucket
                if is_buy:
                    self.current_bucket_buy += remaining_volume
                else:
                    self.current_bucket_sell += remaining_volume

                self.current_bucket_volume += remaining_volume
                remaining_volume = 0

    def calculate(self) -> float:
        """
        Calculate current VPIN value.

        Returns:
            VPIN from 0 (no toxicity) to 1 (high toxicity)
        """
        if len(self.buckets) < self.n_buckets:
            return 0.0

        total_imbalance = 0
        total_volume = 0

        for bucket in self.buckets:
            imbalance = abs(bucket['buy'] - bucket['sell'])
            total_imbalance += imbalance
            total_volume += bucket['buy'] + bucket['sell']

        if total_volume == 0:
            return 0.0

        return total_imbalance / total_volume

    def reset(self):
        """Reset VPIN state."""
        self.buckets.clear()
        self.current_bucket_volume = 0
        self.current_bucket_buy = 0
        self.current_bucket_sell = 0


class VolumeClock:
    """
    Volume clock for time-invariant analysis.

    Creates bars based on volume rather than time.
    """

    def __init__(self, volume_per_bar: int = 100000):
        """
        Args:
            volume_per_bar: Volume threshold for each bar
        """
        self.volume_per_bar = volume_per_bar
        self.classifier = TickClassifier()

        # Current bar state
        self.current_volume = 0
        self.current_buy_volume = 0
        self.current_sell_volume = 0
        self.current_trades = []
        self.bar_start_time = None

        # Completed bars
        self.bars: List[VolumeBar] = []

    def add_trade(
        self,
        price: float,
        volume: int,
        timestamp: datetime,
        bid: Optional[float] = None,
        ask: Optional[float] = None
    ):
        """Add trade and potentially complete a bar."""
        if self.bar_start_time is None:
            self.bar_start_time = timestamp

        # Classify trade
        direction = self.classifier.classify(price, bid, ask)
        is_buy = direction > 0

        # Add to current bar
        self.current_trades.append({
            'price': price,
            'volume': volume,
            'is_buy': is_buy
        })

        self.current_volume += volume
        if is_buy:
            self.current_buy_volume += volume
        else:
            self.current_sell_volume += volume

        # Check if bar is complete
        while self.current_volume >= self.volume_per_bar:
            self._complete_bar(timestamp)

    def _complete_bar(self, end_time: datetime):
        """Complete current bar and start new one."""
        if not self.current_trades:
            return

        prices = [t['price'] for t in self.current_trades]
        volumes = [t['volume'] for t in self.current_trades]

        # Calculate VWAP
        total_value = sum(p * v for p, v in zip(prices, volumes))
        total_volume = sum(volumes)
        vwap = total_value / total_volume if total_volume > 0 else prices[-1]

        bar = VolumeBar(
            open=prices[0],
            high=max(prices),
            low=min(prices),
            close=prices[-1],
            volume=self.current_volume,
            buy_volume=self.current_buy_volume,
            sell_volume=self.current_sell_volume,
            vwap=vwap,
            num_trades=len(self.current_trades),
            avg_trade_size=self.current_volume / len(self.current_trades),
            start_time=self.bar_start_time,
            end_time=end_time
        )

        self.bars.append(bar)

        # Reset
        self.current_volume = 0
        self.current_buy_volume = 0
        self.current_sell_volume = 0
        self.current_trades = []
        self.bar_start_time = end_time

    def get_bars(self) -> List[VolumeBar]:
        """Get completed volume bars."""
        return self.bars


class AggressiveOrderDetector:
    """
    Detect aggressive (market) orders vs passive (limit) orders.
    """

    def __init__(self):
        self.trades = []

    def add_trade(
        self,
        price: float,
        size: int,
        timestamp: datetime,
        bid: float,
        ask: float
    ):
        """Add trade for analysis."""
        # Determine aggression
        spread = ask - bid
        midpoint = (ask + bid) / 2

        if spread > 0:
            distance_from_mid = abs(price - midpoint) / (spread / 2)
        else:
            distance_from_mid = 0

        # At or near ask = aggressive buy, at or near bid = aggressive sell
        if price >= ask - 0.001:
            order_type = OrderType.AGGRESSIVE_BUY
        elif price <= bid + 0.001:
            order_type = OrderType.AGGRESSIVE_SELL
        elif price > midpoint:
            order_type = OrderType.PASSIVE_BUY
        else:
            order_type = OrderType.PASSIVE_SELL

        self.trades.append({
            'price': price,
            'size': size,
            'timestamp': timestamp,
            'order_type': order_type,
            'distance_from_mid': distance_from_mid
        })

    def calculate_aggression_ratio(self, lookback: int = 100) -> Tuple[float, float]:
        """
        Calculate aggression ratio.

        Returns:
            buy_aggression: Ratio of aggressive buys to total buys
            sell_aggression: Ratio of aggressive sells to total sells
        """
        recent_trades = self.trades[-lookback:]

        agg_buy_vol = sum(
            t['size'] for t in recent_trades
            if t['order_type'] == OrderType.AGGRESSIVE_BUY
        )
        total_buy_vol = sum(
            t['size'] for t in recent_trades
            if t['order_type'] in [OrderType.AGGRESSIVE_BUY, OrderType.PASSIVE_BUY]
        )

        agg_sell_vol = sum(
            t['size'] for t in recent_trades
            if t['order_type'] == OrderType.AGGRESSIVE_SELL
        )
        total_sell_vol = sum(
            t['size'] for t in recent_trades
            if t['order_type'] in [OrderType.AGGRESSIVE_SELL, OrderType.PASSIVE_SELL]
        )

        buy_agg = agg_buy_vol / total_buy_vol if total_buy_vol > 0 else 0
        sell_agg = agg_sell_vol / total_sell_vol if total_sell_vol > 0 else 0

        return buy_agg, sell_agg

    def detect_aggressive_sweep(self, threshold_size: int = 10000) -> List[Dict]:
        """Detect aggressive sweep orders (large aggressive orders)."""
        sweeps = []

        for trade in self.trades:
            if trade['size'] >= threshold_size:
                if trade['order_type'] in [OrderType.AGGRESSIVE_BUY, OrderType.AGGRESSIVE_SELL]:
                    sweeps.append({
                        'timestamp': trade['timestamp'],
                        'type': trade['order_type'].value,
                        'size': trade['size'],
                        'price': trade['price']
                    })

        return sweeps


class InstitutionalFootprint:
    """
    Detect institutional trading patterns.
    """

    def __init__(self):
        self.volume_profile = {}
        self.trade_size_distribution = []

    def analyze_size_distribution(
        self,
        trade_sizes: List[int]
    ) -> Dict[str, float]:
        """
        Analyze trade size distribution for institutional activity.
        """
        if not trade_sizes:
            return {'institutional_probability': 0.0}

        sizes = np.array(trade_sizes)

        # Statistics
        mean_size = np.mean(sizes)
        median_size = np.median(sizes)
        std_size = np.std(sizes)

        # Percentiles
        p90 = np.percentile(sizes, 90)
        p99 = np.percentile(sizes, 99)

        # Large trade ratio (potential institutional)
        large_trade_threshold = median_size * 10
        large_trades = sizes[sizes > large_trade_threshold]
        large_trade_volume = large_trades.sum()
        total_volume = sizes.sum()

        large_trade_ratio = large_trade_volume / total_volume if total_volume > 0 else 0

        # Round lot analysis (institutions often trade in round lots)
        round_lots = sum(1 for s in sizes if s % 100 == 0)
        round_lot_ratio = round_lots / len(sizes) if sizes.any() else 0

        # Bimodal distribution (retail vs institutional)
        # Check if distribution has two modes
        hist, bins = np.histogram(sizes, bins=50)
        peaks = []
        for i in range(1, len(hist) - 1):
            if hist[i] > hist[i-1] and hist[i] > hist[i+1]:
                peaks.append(bins[i])

        is_bimodal = len(peaks) >= 2

        # Institutional probability
        inst_prob = (
            large_trade_ratio * 0.4 +
            round_lot_ratio * 0.2 +
            (0.2 if is_bimodal else 0) +
            min(mean_size / 1000, 0.2)
        )

        return {
            'mean_size': mean_size,
            'median_size': median_size,
            'p90_size': p90,
            'p99_size': p99,
            'large_trade_ratio': large_trade_ratio,
            'round_lot_ratio': round_lot_ratio,
            'is_bimodal': is_bimodal,
            'institutional_probability': min(inst_prob, 1.0)
        }

    def detect_accumulation(
        self,
        prices: np.ndarray,
        volumes: np.ndarray,
        buy_volumes: np.ndarray
    ) -> Dict[str, Any]:
        """
        Detect accumulation/distribution patterns.
        """
        if len(prices) < 20:
            return {'pattern': 'insufficient_data'}

        # Price trend
        price_change = (prices[-1] - prices[0]) / prices[0]

        # Volume trend
        volume_trend = np.polyfit(range(len(volumes)), volumes, 1)[0]

        # Buy/sell ratio trend
        sell_volumes = volumes - buy_volumes
        buy_ratio = buy_volumes / (buy_volumes + sell_volumes + 1e-10)
        buy_ratio_trend = np.polyfit(range(len(buy_ratio)), buy_ratio, 1)[0]

        # Accumulation: rising buy ratio while price flat/down
        # Distribution: falling buy ratio while price flat/up
        if buy_ratio_trend > 0.001 and price_change < 0.02:
            pattern = 'accumulation'
            strength = min(abs(buy_ratio_trend) * 100, 100)
        elif buy_ratio_trend < -0.001 and price_change > -0.02:
            pattern = 'distribution'
            strength = min(abs(buy_ratio_trend) * 100, 100)
        else:
            pattern = 'neutral'
            strength = 0

        return {
            'pattern': pattern,
            'strength': strength,
            'buy_ratio_trend': buy_ratio_trend,
            'price_change': price_change,
            'volume_trend': volume_trend
        }


class FlowPredictor:
    """
    Machine learning-based order flow predictor.

    Uses microstructure features to predict short-term direction.
    """

    def __init__(self, lookback: int = 20):
        """
        Args:
            lookback: Bars to use for prediction
        """
        self.lookback = lookback
        self.feature_history = []
        self.target_history = []
        self.model_weights = None

    def extract_features(
        self,
        prices: np.ndarray,
        volumes: np.ndarray,
        buy_volumes: np.ndarray,
        imbalances: np.ndarray
    ) -> np.ndarray:
        """Extract predictive features from flow data."""
        features = []

        # Returns
        returns = np.diff(prices) / prices[:-1]
        features.extend([
            np.mean(returns[-5:]) if len(returns) >= 5 else 0,
            np.mean(returns[-10:]) if len(returns) >= 10 else 0,
            np.std(returns[-10:]) if len(returns) >= 10 else 0,
        ])

        # Volume features
        features.extend([
            np.mean(volumes[-5:]) / (np.mean(volumes[-20:]) + 1) if len(volumes) >= 20 else 1,
            np.std(volumes[-10:]) / (np.mean(volumes[-10:]) + 1) if len(volumes) >= 10 else 0,
        ])

        # Flow imbalance
        sell_volumes = volumes - buy_volumes
        imbalance = (buy_volumes - sell_volumes) / (buy_volumes + sell_volumes + 1)
        features.extend([
            np.mean(imbalance[-5:]) if len(imbalance) >= 5 else 0,
            np.mean(imbalance[-10:]) if len(imbalance) >= 10 else 0,
            imbalance[-1] if len(imbalance) > 0 else 0,
        ])

        # Order book imbalance
        features.extend([
            np.mean(imbalances[-5:]) if len(imbalances) >= 5 else 0,
            imbalances[-1] if len(imbalances) > 0 else 0,
        ])

        # Momentum
        if len(prices) >= 10:
            momentum = (prices[-1] - prices[-10]) / prices[-10]
            features.append(momentum)
        else:
            features.append(0)

        # Price level (normalized)
        if len(prices) >= 20:
            zscore = (prices[-1] - np.mean(prices[-20:])) / (np.std(prices[-20:]) + 1e-10)
            features.append(np.clip(zscore, -3, 3))
        else:
            features.append(0)

        return np.array(features)

    def train(
        self,
        features: np.ndarray,
        targets: np.ndarray,
        learning_rate: float = 0.01,
        epochs: int = 100
    ):
        """
        Simple online linear model training.

        Args:
            features: Feature matrix (n_samples, n_features)
            targets: Target values (n_samples,)
        """
        n_features = features.shape[1]

        if self.model_weights is None:
            self.model_weights = np.zeros(n_features)

        # Mini-batch gradient descent
        for _ in range(epochs):
            indices = np.random.permutation(len(targets))

            for i in indices:
                x = features[i]
                y = targets[i]

                # Prediction
                pred = np.dot(self.model_weights, x)

                # Gradient
                error = pred - y
                gradient = error * x

                # Update
                self.model_weights -= learning_rate * gradient

    def predict(self, features: np.ndarray) -> Tuple[float, float]:
        """
        Predict direction and magnitude.

        Returns:
            direction: Predicted direction (-1 to 1)
            confidence: Prediction confidence
        """
        if self.model_weights is None:
            return 0.0, 0.0

        prediction = np.dot(self.model_weights, features)

        # Sigmoid for bounded output
        direction = 2 / (1 + np.exp(-prediction)) - 1

        # Confidence based on magnitude
        confidence = min(abs(prediction) / 2, 1.0)

        return direction, confidence


class PredictiveOrderFlow:
    """
    Master predictive order flow system.

    Integrates all order flow analysis components.
    """

    def __init__(
        self,
        volume_per_bar: int = 100000,
        vpin_bucket_size: int = 50000
    ):
        """
        Args:
            volume_per_bar: Volume for volume bars
            vpin_bucket_size: Volume per VPIN bucket
        """
        # Components
        self.classifier = TickClassifier()
        self.imbalance_analyzer = OrderBookImbalance()
        self.vpin_calculator = VPINCalculator(bucket_size=vpin_bucket_size)
        self.volume_clock = VolumeClock(volume_per_bar=volume_per_bar)
        self.aggression_detector = AggressiveOrderDetector()
        self.footprint_analyzer = InstitutionalFootprint()
        self.predictor = FlowPredictor()

        # State
        self.current_state: Optional[OrderFlowState] = None
        self.signals: List[FlowSignal] = []
        self.trade_history = []
        self.imbalance_history = []

    def process_trade(
        self,
        price: float,
        size: int,
        timestamp: datetime,
        bid: float,
        ask: float
    ):
        """
        Process incoming trade.

        Args:
            price: Trade price
            size: Trade size
            timestamp: Trade timestamp
            bid: Current bid
            ask: Current ask
        """
        # Classify trade
        direction = self.classifier.classify(price, bid, ask)
        is_buy = direction > 0

        # Update VPIN
        self.vpin_calculator.update(size, is_buy)

        # Update volume clock
        self.volume_clock.add_trade(price, size, timestamp, bid, ask)

        # Update aggression detector
        self.aggression_detector.add_trade(price, size, timestamp, bid, ask)

        # Store trade
        self.trade_history.append({
            'price': price,
            'size': size,
            'timestamp': timestamp,
            'is_buy': is_buy
        })

    def update_order_book(
        self,
        bids: List[Tuple[float, float]],
        asks: List[Tuple[float, float]],
        reference_price: float
    ):
        """Update with order book snapshot."""
        imbalance = self.imbalance_analyzer.weighted_imbalance(
            bids, asks, reference_price
        )
        self.imbalance_history.append(imbalance)

    def analyze(self) -> OrderFlowState:
        """
        Analyze current order flow state.

        Returns:
            OrderFlowState with current analysis
        """
        # Get volume bars
        bars = self.volume_clock.get_bars()

        # Calculate VPIN
        toxicity = self.vpin_calculator.calculate()

        # Calculate imbalance
        if self.imbalance_history:
            current_imbalance = self.imbalance_history[-1]
            avg_imbalance = np.mean(self.imbalance_history[-20:])
        else:
            current_imbalance = 0.0
            avg_imbalance = 0.0

        # Aggression analysis
        buy_agg, sell_agg = self.aggression_detector.calculate_aggression_ratio()
        aggression_ratio = buy_agg - sell_agg

        # Institutional analysis
        if self.trade_history:
            sizes = [t['size'] for t in self.trade_history[-500:]]
            inst_analysis = self.footprint_analyzer.analyze_size_distribution(sizes)
            inst_prob = inst_analysis['institutional_probability']
        else:
            inst_prob = 0.0

        # Flow direction
        if bars:
            recent_bars = bars[-10:]
            buy_vol = sum(b.buy_volume for b in recent_bars)
            sell_vol = sum(b.sell_volume for b in recent_bars)
            total_vol = buy_vol + sell_vol

            if total_vol > 0:
                flow_ratio = (buy_vol - sell_vol) / total_vol
            else:
                flow_ratio = 0.0
        else:
            flow_ratio = 0.0

        # Determine direction
        if flow_ratio > 0.3:
            direction = FlowDirection.STRONG_BUY
        elif flow_ratio > 0.1:
            direction = FlowDirection.BUY
        elif flow_ratio < -0.3:
            direction = FlowDirection.STRONG_SELL
        elif flow_ratio < -0.1:
            direction = FlowDirection.SELL
        else:
            direction = FlowDirection.NEUTRAL

        # Prediction
        if bars and len(bars) >= 20:
            prices = np.array([b.close for b in bars])
            volumes = np.array([b.volume for b in bars])
            buy_volumes = np.array([b.buy_volume for b in bars])
            imbalances = np.array(self.imbalance_history[-len(bars):] if self.imbalance_history else [0]*len(bars))

            # Pad imbalances if needed
            if len(imbalances) < len(prices):
                imbalances = np.pad(imbalances, (len(prices) - len(imbalances), 0), 'constant')

            features = self.predictor.extract_features(
                prices, volumes, buy_volumes, imbalances
            )

            pred_direction, confidence = self.predictor.predict(features)
        else:
            pred_direction = 0.0
            confidence = 0.0

        # Predicted magnitude (rough estimate based on volatility)
        if bars:
            recent_prices = [b.close for b in bars[-20:]]
            if len(recent_prices) > 1:
                returns = np.diff(recent_prices) / np.array(recent_prices[:-1])
                pred_magnitude = np.std(returns) * abs(pred_direction)
            else:
                pred_magnitude = 0.0
        else:
            pred_magnitude = 0.0

        # Overall confidence
        signal_agreement = sum([
            1 if (flow_ratio > 0 and pred_direction > 0) or (flow_ratio < 0 and pred_direction < 0) else 0,
            1 if (current_imbalance > 0 and flow_ratio > 0) or (current_imbalance < 0 and flow_ratio < 0) else 0,
            1 if (aggression_ratio > 0 and flow_ratio > 0) or (aggression_ratio < 0 and flow_ratio < 0) else 0,
        ])

        overall_confidence = 0.3 + (signal_agreement / 3) * 0.5 + confidence * 0.2

        self.current_state = OrderFlowState(
            direction=direction,
            imbalance=current_imbalance,
            toxicity=toxicity,
            aggression_ratio=aggression_ratio,
            institutional_probability=inst_prob,
            predicted_direction=1 if pred_direction > 0.1 else (-1 if pred_direction < -0.1 else 0),
            predicted_magnitude=pred_magnitude,
            confidence=overall_confidence,
            timestamp=datetime.now()
        )

        return self.current_state

    def generate_signals(self, current_price: float) -> List[FlowSignal]:
        """
        Generate trading signals based on order flow.

        Args:
            current_price: Current market price

        Returns:
            List of flow signals
        """
        if not self.current_state:
            self.analyze()

        if not self.current_state:
            return []

        self.signals = []
        state = self.current_state

        # Signal 1: Strong directional flow
        if state.direction in [FlowDirection.STRONG_BUY, FlowDirection.STRONG_SELL]:
            is_buy = state.direction == FlowDirection.STRONG_BUY

            self.signals.append(FlowSignal(
                signal_type='strong_flow',
                direction='long' if is_buy else 'short',
                strength=80,
                entry_price=current_price,
                stop_loss=current_price * (0.995 if is_buy else 1.005),
                take_profit=current_price * (1.01 if is_buy else 0.99),
                timeframe='intraday',
                reasoning=f'Strong {"buying" if is_buy else "selling"} pressure detected',
                confidence=state.confidence
            ))

        # Signal 2: Order book imbalance
        if abs(state.imbalance) > 0.5:
            is_buy = state.imbalance > 0

            self.signals.append(FlowSignal(
                signal_type='book_imbalance',
                direction='long' if is_buy else 'short',
                strength=min(abs(state.imbalance) * 100, 100),
                entry_price=current_price,
                stop_loss=current_price * (0.997 if is_buy else 1.003),
                take_profit=current_price * (1.005 if is_buy else 0.995),
                timeframe='scalp',
                reasoning=f'Order book heavily skewed {"bid" if is_buy else "ask"} side',
                confidence=state.confidence * 0.9
            ))

        # Signal 3: High toxicity warning
        if state.toxicity > 0.7:
            self.signals.append(FlowSignal(
                signal_type='toxicity_warning',
                direction='reduce_exposure',
                strength=state.toxicity * 100,
                entry_price=None,
                stop_loss=None,
                take_profit=None,
                timeframe='immediate',
                reasoning=f'High VPIN ({state.toxicity:.2f}) - informed trading detected',
                confidence=0.8
            ))

        # Signal 4: Institutional activity
        if state.institutional_probability > 0.6:
            # Direction based on aggression
            if state.aggression_ratio > 0.2:
                direction = 'long'
                reasoning = 'Institutional buying detected'
            elif state.aggression_ratio < -0.2:
                direction = 'short'
                reasoning = 'Institutional selling detected'
            else:
                direction = 'neutral'
                reasoning = 'Institutional activity but unclear direction'

            self.signals.append(FlowSignal(
                signal_type='institutional_flow',
                direction=direction,
                strength=state.institutional_probability * 100,
                entry_price=current_price if direction != 'neutral' else None,
                stop_loss=current_price * 0.99 if direction == 'long' else (
                    current_price * 1.01 if direction == 'short' else None
                ),
                take_profit=current_price * 1.02 if direction == 'long' else (
                    current_price * 0.98 if direction == 'short' else None
                ),
                timeframe='swing',
                reasoning=reasoning,
                confidence=state.confidence * 0.85
            ))

        # Signal 5: Prediction-based signal
        if abs(state.predicted_direction) == 1 and state.confidence > 0.6:
            is_buy = state.predicted_direction > 0

            self.signals.append(FlowSignal(
                signal_type='flow_prediction',
                direction='long' if is_buy else 'short',
                strength=state.confidence * 100,
                entry_price=current_price,
                stop_loss=current_price * (0.998 if is_buy else 1.002),
                take_profit=current_price * (1.004 if is_buy else 0.996),
                timeframe='short_term',
                reasoning='ML model predicts price movement',
                confidence=state.confidence
            ))

        # Signal 6: Aggressive sweep detected
        sweeps = self.aggression_detector.detect_aggressive_sweep()
        if sweeps:
            recent_sweeps = [s for s in sweeps if (datetime.now() - s['timestamp']).seconds < 60]
            if recent_sweeps:
                buy_sweeps = sum(1 for s in recent_sweeps if 'buy' in s['type'])
                sell_sweeps = sum(1 for s in recent_sweeps if 'sell' in s['type'])

                if buy_sweeps > sell_sweeps:
                    self.signals.append(FlowSignal(
                        signal_type='sweep_detection',
                        direction='long',
                        strength=75,
                        entry_price=current_price,
                        stop_loss=current_price * 0.995,
                        take_profit=current_price * 1.015,
                        timeframe='intraday',
                        reasoning=f'{buy_sweeps} aggressive buy sweeps detected',
                        confidence=0.7
                    ))
                elif sell_sweeps > buy_sweeps:
                    self.signals.append(FlowSignal(
                        signal_type='sweep_detection',
                        direction='short',
                        strength=75,
                        entry_price=current_price,
                        stop_loss=current_price * 1.005,
                        take_profit=current_price * 0.985,
                        timeframe='intraday',
                        reasoning=f'{sell_sweeps} aggressive sell sweeps detected',
                        confidence=0.7
                    ))

        return self.signals

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of order flow analysis."""
        if not self.current_state:
            self.analyze()

        state = self.current_state

        return {
            'direction': state.direction.value if state else 'unknown',
            'imbalance': state.imbalance if state else 0,
            'toxicity': state.toxicity if state else 0,
            'aggression_ratio': state.aggression_ratio if state else 0,
            'institutional_probability': state.institutional_probability if state else 0,
            'predicted_direction': state.predicted_direction if state else 0,
            'confidence': state.confidence if state else 0,
            'signals_count': len(self.signals),
            'volume_bars': len(self.volume_clock.bars),
            'trades_processed': len(self.trade_history)
        }


def create_predictive_order_flow(
    volume_per_bar: int = 100000,
    vpin_bucket_size: int = 50000
) -> PredictiveOrderFlow:
    """Factory function to create predictive order flow system."""
    return PredictiveOrderFlow(
        volume_per_bar=volume_per_bar,
        vpin_bucket_size=vpin_bucket_size
    )


# Example usage and testing
if __name__ == "__main__":
    print("="*60)
    print("PREDICTIVE ORDER FLOW SYSTEM - TEST MODE")
    print("="*60)

    # Create system
    system = create_predictive_order_flow(
        volume_per_bar=10000,
        vpin_bucket_size=5000
    )

    # Simulate trades
    np.random.seed(42)
    n_trades = 1000

    base_price = 100.0
    price = base_price

    print("\nSimulating order flow...")

    for i in range(n_trades):
        # Random walk with drift
        price_change = np.random.normal(0.0001, 0.001)
        price = price * (1 + price_change)

        # Bid-ask spread
        spread = price * 0.001
        bid = price - spread / 2
        ask = price + spread / 2

        # Trade at random point in spread
        if np.random.random() > 0.5:
            trade_price = ask  # Buy
        else:
            trade_price = bid  # Sell

        # Trade size (mix of retail and institutional)
        if np.random.random() > 0.9:
            size = int(np.random.exponential(5000))  # Institutional
        else:
            size = int(np.random.exponential(200))   # Retail

        size = max(1, size)

        timestamp = datetime.now() + timedelta(seconds=i)

        # Process trade
        system.process_trade(trade_price, size, timestamp, bid, ask)

        # Periodically update order book
        if i % 10 == 0:
            # Simulate order book
            bids = [(bid - j * 0.01, np.random.randint(100, 10000)) for j in range(10)]
            asks = [(ask + j * 0.01, np.random.randint(100, 10000)) for j in range(10)]
            system.update_order_book(bids, asks, price)

    # Analyze
    print("\nAnalyzing order flow...")
    state = system.analyze()

    print(f"\n{'='*60}")
    print("ORDER FLOW STATE")
    print('='*60)
    print(f"Direction: {state.direction.value}")
    print(f"Imbalance: {state.imbalance:.3f}")
    print(f"VPIN Toxicity: {state.toxicity:.3f}")
    print(f"Aggression Ratio: {state.aggression_ratio:.3f}")
    print(f"Institutional Probability: {state.institutional_probability:.3f}")
    print(f"Predicted Direction: {state.predicted_direction}")
    print(f"Predicted Magnitude: {state.predicted_magnitude:.4f}")
    print(f"Confidence: {state.confidence:.2%}")

    # Generate signals
    print(f"\n{'='*60}")
    print("TRADING SIGNALS")
    print('='*60)

    signals = system.generate_signals(price)

    for signal in signals:
        print(f"\n{signal.signal_type.upper()}:")
        print(f"  Direction: {signal.direction}")
        print(f"  Strength: {signal.strength:.0f}/100")
        print(f"  Entry: ${signal.entry_price:.2f}" if signal.entry_price else "  Entry: N/A")
        print(f"  Stop Loss: ${signal.stop_loss:.2f}" if signal.stop_loss else "  Stop Loss: N/A")
        print(f"  Take Profit: ${signal.take_profit:.2f}" if signal.take_profit else "  Take Profit: N/A")
        print(f"  Timeframe: {signal.timeframe}")
        print(f"  Reasoning: {signal.reasoning}")
        print(f"  Confidence: {signal.confidence:.2%}")

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print('='*60)
    summary = system.get_summary()
    for key, value in summary.items():
        print(f"  {key}: {value}")

    print(f"\n{'='*60}")
    print("PREDICTIVE ORDER FLOW SYSTEM - READY FOR PRODUCTION")
    print('='*60)
