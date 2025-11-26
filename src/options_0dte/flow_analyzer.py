"""
Revolution Alpha Engine - Institutional Options Flow Analyzer
State-of-the-art analysis of options order flow for 0DTE trading.

This module provides:
- Sweep order detection and analysis
- Block trade identification
- Dark pool activity estimation
- Institutional vs retail flow separation
- Smart money direction detection
- Unusual activity alerts
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
from datetime import datetime, timedelta
from collections import deque


class OrderType(Enum):
    """Type of options order."""
    SWEEP = "sweep"  # Aggressive multi-exchange fill
    BLOCK = "block"  # Single large transaction
    SPLIT = "split"  # Large order split into pieces
    SPREAD = "spread"  # Multi-leg strategy
    SINGLE = "single"  # Standard single order


class OrderSide(Enum):
    """Side of the transaction."""
    BUY_TO_OPEN = "buy_to_open"  # Opening long position
    SELL_TO_OPEN = "sell_to_open"  # Opening short position
    BUY_TO_CLOSE = "buy_to_close"  # Closing short position
    SELL_TO_CLOSE = "sell_to_close"  # Closing long position
    UNKNOWN = "unknown"


class FlowSentiment(Enum):
    """Sentiment derived from flow."""
    EXTREMELY_BULLISH = "extremely_bullish"
    BULLISH = "bullish"
    SLIGHTLY_BULLISH = "slightly_bullish"
    NEUTRAL = "neutral"
    SLIGHTLY_BEARISH = "slightly_bearish"
    BEARISH = "bearish"
    EXTREMELY_BEARISH = "extremely_bearish"


@dataclass
class OptionsOrder:
    """Individual options order record."""
    timestamp: datetime
    symbol: str
    expiry: datetime
    strike: float
    option_type: str  # 'call' or 'put'
    side: OrderSide
    order_type: OrderType
    size: int
    price: float
    premium: float  # size * price * 100
    bid: float
    ask: float
    underlying_price: float
    delta: float = 0.0
    open_interest: int = 0
    volume: int = 0

    # Derived fields
    at_ask: bool = False  # Bought at ask (aggressive)
    at_bid: bool = False  # Sold at bid (aggressive)
    is_unusual: bool = False
    is_institutional: bool = False
    notes: str = ""

    def __post_init__(self):
        """Calculate derived fields."""
        mid = (self.bid + self.ask) / 2
        self.at_ask = self.price >= (mid + (self.ask - mid) * 0.7)
        self.at_bid = self.price <= (mid - (mid - self.bid) * 0.7)

        # Unusual activity: volume > 2x OI or premium > $100k
        if self.open_interest > 0:
            self.is_unusual = (self.volume > self.open_interest * 2) or (self.premium > 100000)
        else:
            self.is_unusual = self.premium > 100000

        # Institutional: large premium or sweep
        self.is_institutional = (self.premium > 50000) or (self.order_type == OrderType.SWEEP)


@dataclass
class FlowSummary:
    """Summary of options flow analysis."""
    timestamp: datetime = field(default_factory=datetime.now)
    period_minutes: int = 5

    # Volume metrics
    total_call_volume: int = 0
    total_put_volume: int = 0
    total_call_premium: float = 0.0
    total_put_premium: float = 0.0

    # Aggressive order metrics
    call_bought_ask: int = 0  # Calls bought at ask
    call_sold_bid: int = 0  # Calls sold at bid
    put_bought_ask: int = 0  # Puts bought at ask
    put_sold_bid: int = 0  # Puts sold at bid

    # Premium at bid/ask
    call_premium_at_ask: float = 0.0
    call_premium_at_bid: float = 0.0
    put_premium_at_ask: float = 0.0
    put_premium_at_bid: float = 0.0

    # Sweep activity
    call_sweep_count: int = 0
    put_sweep_count: int = 0
    call_sweep_premium: float = 0.0
    put_sweep_premium: float = 0.0

    # Block activity
    call_block_count: int = 0
    put_block_count: int = 0
    call_block_premium: float = 0.0
    put_block_premium: float = 0.0

    # Unusual activity
    unusual_activity_count: int = 0
    unusual_activity_premium: float = 0.0

    # Delta exposure
    net_delta_exposure: float = 0.0
    call_delta_exposure: float = 0.0
    put_delta_exposure: float = 0.0

    # Derived metrics
    put_call_ratio: float = 1.0
    net_premium: float = 0.0
    aggressive_buy_ratio: float = 0.5
    sentiment: FlowSentiment = FlowSentiment.NEUTRAL

    # Interpretation
    summary_text: str = ""
    key_observations: List[str] = field(default_factory=list)
    smart_money_direction: str = "neutral"

    def calculate_derived_metrics(self):
        """Calculate derived metrics from raw data."""
        # Put/Call ratio
        if self.total_call_volume > 0:
            self.put_call_ratio = self.total_put_volume / self.total_call_volume
        else:
            self.put_call_ratio = 1.0

        # Net premium (calls - puts for directional bias)
        # Positive = bullish flow, Negative = bearish flow
        call_net = self.call_premium_at_ask - self.call_premium_at_bid
        put_net = self.put_premium_at_ask - self.put_premium_at_bid
        self.net_premium = call_net - put_net

        # Aggressive buy ratio
        total_aggressive = (
            self.call_bought_ask + self.call_sold_bid +
            self.put_bought_ask + self.put_sold_bid
        )
        if total_aggressive > 0:
            bullish_aggressive = self.call_bought_ask + self.put_sold_bid
            self.aggressive_buy_ratio = bullish_aggressive / total_aggressive

        # Determine sentiment
        self._determine_sentiment()

        # Generate interpretation
        self._generate_interpretation()

    def _determine_sentiment(self):
        """Determine overall flow sentiment."""
        score = 0

        # Put/Call ratio impact
        if self.put_call_ratio < 0.5:
            score += 2
        elif self.put_call_ratio < 0.7:
            score += 1
        elif self.put_call_ratio > 1.5:
            score -= 2
        elif self.put_call_ratio > 1.2:
            score -= 1

        # Net premium impact
        if self.net_premium > 500000:
            score += 2
        elif self.net_premium > 100000:
            score += 1
        elif self.net_premium < -500000:
            score -= 2
        elif self.net_premium < -100000:
            score -= 1

        # Aggressive buy ratio impact
        if self.aggressive_buy_ratio > 0.7:
            score += 2
        elif self.aggressive_buy_ratio > 0.6:
            score += 1
        elif self.aggressive_buy_ratio < 0.3:
            score -= 2
        elif self.aggressive_buy_ratio < 0.4:
            score -= 1

        # Sweep activity impact
        call_sweep_bias = self.call_sweep_premium - self.put_sweep_premium
        if call_sweep_bias > 200000:
            score += 1
        elif call_sweep_bias < -200000:
            score -= 1

        # Map score to sentiment
        if score >= 4:
            self.sentiment = FlowSentiment.EXTREMELY_BULLISH
        elif score >= 2:
            self.sentiment = FlowSentiment.BULLISH
        elif score >= 1:
            self.sentiment = FlowSentiment.SLIGHTLY_BULLISH
        elif score <= -4:
            self.sentiment = FlowSentiment.EXTREMELY_BEARISH
        elif score <= -2:
            self.sentiment = FlowSentiment.BEARISH
        elif score <= -1:
            self.sentiment = FlowSentiment.SLIGHTLY_BEARISH
        else:
            self.sentiment = FlowSentiment.NEUTRAL

        # Smart money direction from sweeps and blocks
        smart_bullish = self.call_sweep_premium + self.call_block_premium
        smart_bearish = self.put_sweep_premium + self.put_block_premium
        if smart_bullish > smart_bearish * 1.5:
            self.smart_money_direction = "bullish"
        elif smart_bearish > smart_bullish * 1.5:
            self.smart_money_direction = "bearish"
        else:
            self.smart_money_direction = "neutral"

    def _generate_interpretation(self):
        """Generate human-readable interpretation."""
        observations = []

        # P/C ratio
        if self.put_call_ratio < 0.6:
            observations.append(f"BULLISH P/C ratio at {self.put_call_ratio:.2f} - Heavy call activity")
        elif self.put_call_ratio > 1.4:
            observations.append(f"BEARISH P/C ratio at {self.put_call_ratio:.2f} - Heavy put activity")

        # Net premium
        if abs(self.net_premium) > 100000:
            direction = "BULLISH" if self.net_premium > 0 else "BEARISH"
            observations.append(f"{direction} net premium: ${abs(self.net_premium):,.0f}")

        # Sweep activity
        if self.call_sweep_count + self.put_sweep_count > 5:
            total_sweep = self.call_sweep_premium + self.put_sweep_premium
            observations.append(f"HIGH sweep activity: {self.call_sweep_count + self.put_sweep_count} sweeps, ${total_sweep:,.0f} premium")

        # Block trades
        if self.call_block_count + self.put_block_count > 0:
            total_block = self.call_block_premium + self.put_block_premium
            observations.append(f"Block trades detected: {self.call_block_count + self.put_block_count} blocks, ${total_block:,.0f} premium")

        # Unusual activity
        if self.unusual_activity_count > 3:
            observations.append(f"HIGH unusual activity: {self.unusual_activity_count} alerts")

        # Delta exposure
        if abs(self.net_delta_exposure) > 10000:
            direction = "LONG" if self.net_delta_exposure > 0 else "SHORT"
            observations.append(f"Net delta exposure: {direction} {abs(self.net_delta_exposure):,.0f} deltas")

        self.key_observations = observations

        # Summary text
        self.summary_text = (
            f"Flow Sentiment: {self.sentiment.value.upper()}\n"
            f"Smart Money: {self.smart_money_direction.upper()}\n"
            f"P/C Ratio: {self.put_call_ratio:.2f} | Aggressive Buy: {self.aggressive_buy_ratio:.1%}\n"
            f"Call Premium: ${self.total_call_premium:,.0f} | Put Premium: ${self.total_put_premium:,.0f}\n"
            f"Sweeps: {self.call_sweep_count}C/{self.put_sweep_count}P | Blocks: {self.call_block_count}C/{self.put_block_count}P"
        )

    def get_full_analysis(self) -> str:
        """Get complete flow analysis report."""
        lines = [
            "=" * 70,
            "OPTIONS FLOW ANALYSIS REPORT",
            "=" * 70,
            f"Analysis Time: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Period: Last {self.period_minutes} minutes",
            "",
            "-" * 35,
            "VOLUME SUMMARY",
            "-" * 35,
            f"Total Call Volume: {self.total_call_volume:,}",
            f"Total Put Volume: {self.total_put_volume:,}",
            f"Put/Call Ratio: {self.put_call_ratio:.2f}",
            "",
            "-" * 35,
            "PREMIUM ANALYSIS",
            "-" * 35,
            f"Call Premium: ${self.total_call_premium:,.0f}",
            f"  - At Ask: ${self.call_premium_at_ask:,.0f}",
            f"  - At Bid: ${self.call_premium_at_bid:,.0f}",
            f"Put Premium: ${self.total_put_premium:,.0f}",
            f"  - At Ask: ${self.put_premium_at_ask:,.0f}",
            f"  - At Bid: ${self.put_premium_at_bid:,.0f}",
            f"Net Premium (Bull-Bear): ${self.net_premium:,.0f}",
            "",
            "-" * 35,
            "SWEEP ORDERS (Smart Money)",
            "-" * 35,
            f"Call Sweeps: {self.call_sweep_count} orders, ${self.call_sweep_premium:,.0f}",
            f"Put Sweeps: {self.put_sweep_count} orders, ${self.put_sweep_premium:,.0f}",
            "",
            "-" * 35,
            "BLOCK TRADES (Institutional)",
            "-" * 35,
            f"Call Blocks: {self.call_block_count} trades, ${self.call_block_premium:,.0f}",
            f"Put Blocks: {self.put_block_count} trades, ${self.put_block_premium:,.0f}",
            "",
            "-" * 35,
            "DELTA EXPOSURE",
            "-" * 35,
            f"Call Delta: {self.call_delta_exposure:+,.0f}",
            f"Put Delta: {self.put_delta_exposure:+,.0f}",
            f"Net Delta: {self.net_delta_exposure:+,.0f}",
            "",
            "-" * 35,
            "SENTIMENT ANALYSIS",
            "-" * 35,
            f"Overall Sentiment: {self.sentiment.value.upper()}",
            f"Smart Money Direction: {self.smart_money_direction.upper()}",
            f"Aggressive Buy Ratio: {self.aggressive_buy_ratio:.1%}",
            "",
            "-" * 35,
            "KEY OBSERVATIONS",
            "-" * 35,
        ]

        for obs in self.key_observations:
            lines.append(f"• {obs}")

        if not self.key_observations:
            lines.append("• No significant observations")

        lines.extend([
            "",
            "=" * 70,
        ])

        return "\n".join(lines)


class InstitutionalFlowAnalyzer:
    """
    Analyzes options flow to detect institutional activity.

    Features:
    - Sweep order detection
    - Block trade analysis
    - Dark pool estimation
    - Smart money tracking
    - Retail vs institutional separation
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}

        # Thresholds
        self.sweep_min_premium = self.config.get('sweep_min_premium', 25000)
        self.block_min_premium = self.config.get('block_min_premium', 100000)
        self.institutional_min_premium = self.config.get('institutional_min_premium', 50000)
        self.unusual_volume_multiple = self.config.get('unusual_volume_multiple', 2.0)

        # Order history
        self.order_history: deque = deque(maxlen=10000)
        self.sweep_history: deque = deque(maxlen=1000)
        self.block_history: deque = deque(maxlen=500)

        # Real-time state
        self.current_summary: Optional[FlowSummary] = None

    def process_order(self, order: OptionsOrder) -> Dict[str, Any]:
        """
        Process a single options order.

        Returns analysis of the order.
        """
        self.order_history.append(order)

        analysis = {
            'order': order,
            'is_sweep': order.order_type == OrderType.SWEEP,
            'is_block': order.order_type == OrderType.BLOCK,
            'is_institutional': order.is_institutional,
            'is_unusual': order.is_unusual,
            'sentiment': self._get_order_sentiment(order),
            'alerts': []
        }

        # Track sweeps
        if order.order_type == OrderType.SWEEP:
            self.sweep_history.append(order)
            analysis['alerts'].append(
                f"SWEEP: {order.option_type.upper()} {order.strike} - "
                f"${order.premium:,.0f} ({order.size} contracts)"
            )

        # Track blocks
        if order.order_type == OrderType.BLOCK or order.premium >= self.block_min_premium:
            self.block_history.append(order)
            analysis['alerts'].append(
                f"BLOCK: {order.option_type.upper()} {order.strike} - "
                f"${order.premium:,.0f} ({order.size} contracts)"
            )

        # Unusual activity alert
        if order.is_unusual:
            analysis['alerts'].append(
                f"UNUSUAL: {order.option_type.upper()} {order.strike} - "
                f"Vol/OI: {order.volume}/{order.open_interest}"
            )

        return analysis

    def _get_order_sentiment(self, order: OptionsOrder) -> str:
        """Determine sentiment of a single order."""
        is_call = order.option_type == 'call'

        # Bought at ask = aggressive buyer
        if order.at_ask:
            if is_call:
                return "bullish"  # Buying calls aggressively
            else:
                return "bearish"  # Buying puts aggressively

        # Sold at bid = aggressive seller
        if order.at_bid:
            if is_call:
                return "bearish"  # Selling calls aggressively
            else:
                return "bullish"  # Selling puts aggressively

        return "neutral"

    def analyze_flow(
        self,
        orders: List[OptionsOrder],
        period_minutes: int = 5
    ) -> FlowSummary:
        """
        Analyze a collection of orders.

        Args:
            orders: List of options orders
            period_minutes: Time period for analysis

        Returns:
            FlowSummary with complete analysis
        """
        summary = FlowSummary(period_minutes=period_minutes)

        for order in orders:
            # Process each order
            self.process_order(order)

            # Update volume
            if order.option_type == 'call':
                summary.total_call_volume += order.size
                summary.total_call_premium += order.premium

                if order.at_ask:
                    summary.call_bought_ask += order.size
                    summary.call_premium_at_ask += order.premium
                elif order.at_bid:
                    summary.call_sold_bid += order.size
                    summary.call_premium_at_bid += order.premium

                if order.order_type == OrderType.SWEEP:
                    summary.call_sweep_count += 1
                    summary.call_sweep_premium += order.premium

                if order.order_type == OrderType.BLOCK or order.premium >= self.block_min_premium:
                    summary.call_block_count += 1
                    summary.call_block_premium += order.premium

                # Delta exposure
                delta_exposure = order.size * order.delta * 100
                if order.at_ask:
                    summary.call_delta_exposure += delta_exposure
                elif order.at_bid:
                    summary.call_delta_exposure -= delta_exposure

            else:  # put
                summary.total_put_volume += order.size
                summary.total_put_premium += order.premium

                if order.at_ask:
                    summary.put_bought_ask += order.size
                    summary.put_premium_at_ask += order.premium
                elif order.at_bid:
                    summary.put_sold_bid += order.size
                    summary.put_premium_at_bid += order.premium

                if order.order_type == OrderType.SWEEP:
                    summary.put_sweep_count += 1
                    summary.put_sweep_premium += order.premium

                if order.order_type == OrderType.BLOCK or order.premium >= self.block_min_premium:
                    summary.put_block_count += 1
                    summary.put_block_premium += order.premium

                # Delta exposure (puts have negative delta)
                delta_exposure = order.size * abs(order.delta) * 100
                if order.at_ask:
                    summary.put_delta_exposure -= delta_exposure  # Buying puts = bearish delta
                elif order.at_bid:
                    summary.put_delta_exposure += delta_exposure  # Selling puts = bullish delta

            # Unusual activity
            if order.is_unusual:
                summary.unusual_activity_count += 1
                summary.unusual_activity_premium += order.premium

        # Calculate net delta
        summary.net_delta_exposure = summary.call_delta_exposure + summary.put_delta_exposure

        # Calculate derived metrics
        summary.calculate_derived_metrics()

        self.current_summary = summary
        return summary

    def get_recent_sweeps(self, minutes: int = 15) -> List[OptionsOrder]:
        """Get recent sweep orders."""
        cutoff = datetime.now() - timedelta(minutes=minutes)
        return [o for o in self.sweep_history if o.timestamp >= cutoff]

    def get_recent_blocks(self, minutes: int = 15) -> List[OptionsOrder]:
        """Get recent block trades."""
        cutoff = datetime.now() - timedelta(minutes=minutes)
        return [o for o in self.block_history if o.timestamp >= cutoff]

    def get_strike_concentration(self) -> Dict[float, Dict]:
        """Analyze flow concentration by strike."""
        strike_data = {}

        for order in self.order_history:
            strike = order.strike
            if strike not in strike_data:
                strike_data[strike] = {
                    'call_volume': 0,
                    'put_volume': 0,
                    'call_premium': 0,
                    'put_premium': 0,
                    'net_delta': 0
                }

            if order.option_type == 'call':
                strike_data[strike]['call_volume'] += order.size
                strike_data[strike]['call_premium'] += order.premium
            else:
                strike_data[strike]['put_volume'] += order.size
                strike_data[strike]['put_premium'] += order.premium

        return strike_data

    def detect_unusual_activity(
        self,
        orders: Optional[List[OptionsOrder]] = None
    ) -> List[Dict]:
        """Detect unusual options activity."""
        if orders is None:
            orders = list(self.order_history)

        unusual = []

        for order in orders:
            if not order.is_unusual:
                continue

            alert = {
                'timestamp': order.timestamp,
                'strike': order.strike,
                'option_type': order.option_type,
                'size': order.size,
                'premium': order.premium,
                'volume': order.volume,
                'open_interest': order.open_interest,
                'vol_oi_ratio': order.volume / max(1, order.open_interest),
                'sentiment': self._get_order_sentiment(order),
                'reason': []
            }

            if order.volume > order.open_interest * 2:
                alert['reason'].append(f"Volume {order.volume} > 2x OI {order.open_interest}")

            if order.premium > 100000:
                alert['reason'].append(f"Large premium ${order.premium:,.0f}")

            if order.order_type == OrderType.SWEEP:
                alert['reason'].append("Sweep order (multi-exchange)")

            unusual.append(alert)

        # Sort by premium
        unusual.sort(key=lambda x: x['premium'], reverse=True)
        return unusual

    def get_smart_money_bias(self) -> Dict[str, Any]:
        """
        Analyze smart money (institutional) positioning.

        Returns bias and confidence.
        """
        if not self.current_summary:
            return {'bias': 'neutral', 'confidence': 0.0, 'details': {}}

        summary = self.current_summary

        # Calculate bias score
        score = 0
        max_score = 0

        # Sweep premium direction
        sweep_diff = summary.call_sweep_premium - summary.put_sweep_premium
        if abs(sweep_diff) > 50000:
            max_score += 2
            if sweep_diff > 0:
                score += 2
            else:
                score -= 2

        # Block trade direction
        block_diff = summary.call_block_premium - summary.put_block_premium
        if abs(block_diff) > 100000:
            max_score += 2
            if block_diff > 0:
                score += 2
            else:
                score -= 2

        # Delta exposure
        if abs(summary.net_delta_exposure) > 5000:
            max_score += 1
            if summary.net_delta_exposure > 0:
                score += 1
            else:
                score -= 1

        # Calculate confidence
        if max_score > 0:
            confidence = abs(score) / max_score
        else:
            confidence = 0.0

        # Determine bias
        if score > 0:
            bias = 'bullish'
        elif score < 0:
            bias = 'bearish'
        else:
            bias = 'neutral'

        return {
            'bias': bias,
            'confidence': confidence,
            'score': score,
            'max_score': max_score,
            'details': {
                'sweep_diff': sweep_diff,
                'block_diff': block_diff,
                'net_delta': summary.net_delta_exposure
            }
        }


class DarkPoolEstimator:
    """
    Estimates dark pool activity from public data.

    Dark pools are not directly observable but can be
    inferred from volume patterns and price action.
    """

    def __init__(self):
        self.volume_history: deque = deque(maxlen=1000)
        self.dark_pool_estimates: deque = deque(maxlen=100)

    def estimate_dark_pool_activity(
        self,
        reported_volume: int,
        expected_volume: int,
        price_impact: float
    ) -> Dict[str, Any]:
        """
        Estimate dark pool activity.

        Args:
            reported_volume: Volume reported on lit exchanges
            expected_volume: Expected volume based on historical patterns
            price_impact: Price move relative to volume

        Returns:
            Estimation of dark pool activity
        """
        # Volume discrepancy
        volume_ratio = reported_volume / max(1, expected_volume)

        # Low volume with significant price impact suggests dark pool
        if volume_ratio < 0.7 and abs(price_impact) > 0.2:
            estimated_dark_volume = expected_volume - reported_volume
            dark_pool_likelihood = 0.7
        elif volume_ratio < 0.5:
            estimated_dark_volume = expected_volume * 0.5
            dark_pool_likelihood = 0.8
        else:
            estimated_dark_volume = 0
            dark_pool_likelihood = 0.2

        estimate = {
            'timestamp': datetime.now(),
            'reported_volume': reported_volume,
            'expected_volume': expected_volume,
            'volume_ratio': volume_ratio,
            'estimated_dark_volume': estimated_dark_volume,
            'dark_pool_likelihood': dark_pool_likelihood,
            'price_impact': price_impact
        }

        self.dark_pool_estimates.append(estimate)
        return estimate


# Convenience functions
def create_flow_analyzer(config: Optional[Dict] = None) -> InstitutionalFlowAnalyzer:
    """Create a configured flow analyzer."""
    return InstitutionalFlowAnalyzer(config)


def create_options_order(
    timestamp: datetime,
    symbol: str,
    expiry: datetime,
    strike: float,
    option_type: str,
    size: int,
    price: float,
    bid: float,
    ask: float,
    underlying_price: float,
    delta: float = 0.0,
    open_interest: int = 0,
    volume: int = 0,
    order_type: str = "single",
    side: str = "unknown"
) -> OptionsOrder:
    """Create an options order from raw data."""
    return OptionsOrder(
        timestamp=timestamp,
        symbol=symbol,
        expiry=expiry,
        strike=strike,
        option_type=option_type,
        side=OrderSide(side) if side in [s.value for s in OrderSide] else OrderSide.UNKNOWN,
        order_type=OrderType(order_type) if order_type in [t.value for t in OrderType] else OrderType.SINGLE,
        size=size,
        price=price,
        premium=size * price * 100,
        bid=bid,
        ask=ask,
        underlying_price=underlying_price,
        delta=delta,
        open_interest=open_interest,
        volume=volume
    )
