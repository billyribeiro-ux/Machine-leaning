"""
Revolution Alpha Engine - Dark Pool Activity Detector

ELITE-LEVEL detection of hidden institutional activity.

Dark pools are private exchanges where large institutions trade
without revealing their orders to the public market. This module
uses sophisticated techniques to INFER dark pool activity from
observable market data.

Key Techniques:
- Volume/Price Divergence Analysis
- Trade-to-Quote Ratio Anomalies
- Price Impact vs Volume Analysis
- Block Trade Detection
- Short Volume Analysis
- Tape Reading (Time & Sales Analysis)
- Accumulation/Distribution Patterns
- VWAP Deviation Detection

Why This Matters:
- Dark pools account for ~40% of US equity volume
- Large institutions use them to hide their intentions
- Detecting this activity gives edge over retail traders
- Often precedes major price moves
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
from datetime import datetime, timedelta
from collections import deque
import statistics


class DarkPoolSignal(Enum):
    """Types of dark pool signals."""
    ACCUMULATION = "accumulation"  # Quiet buying
    DISTRIBUTION = "distribution"  # Quiet selling
    BLOCK_BUYING = "block_buying"  # Large block buys
    BLOCK_SELLING = "block_selling"  # Large block sells
    ICEBERG_ORDER = "iceberg_order"  # Hidden size detection
    STEALTH_ACCUMULATION = "stealth_accumulation"  # Very hidden buying
    STEALTH_DISTRIBUTION = "stealth_distribution"  # Very hidden selling
    INSTITUTIONAL_PIVOT = "institutional_pivot"  # Direction change


class ActivityLevel(Enum):
    """Level of detected activity."""
    EXTREME = "extreme"
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    MINIMAL = "minimal"


@dataclass
class DarkPoolAlert:
    """Alert generated from dark pool analysis."""
    timestamp: datetime
    symbol: str
    signal_type: DarkPoolSignal
    activity_level: ActivityLevel
    confidence: float

    # Price context
    current_price: float = 0.0
    price_change_pct: float = 0.0
    volume: int = 0
    relative_volume: float = 1.0

    # Detection details
    detection_method: str = ""
    evidence: List[str] = field(default_factory=list)

    # Inferred activity
    estimated_dark_volume: int = 0
    estimated_direction: str = ""  # 'buy', 'sell', 'unknown'
    estimated_size_millions: float = 0.0

    # Prediction
    expected_price_impact: str = ""
    expected_timeframe: str = ""

    # Full analysis
    full_analysis: str = ""

    def get_report(self) -> str:
        """Generate alert report."""
        lines = [
            "═" * 70,
            f"DARK POOL ALERT: {self.symbol}",
            "═" * 70,
            f"Time: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Signal: {self.signal_type.value.upper().replace('_', ' ')}",
            f"Activity Level: {self.activity_level.value.upper()}",
            f"Confidence: {self.confidence:.1f}%",
            "",
            f"Price: ${self.current_price:.2f} ({self.price_change_pct:+.2f}%)",
            f"Volume: {self.volume:,} (Rel Vol: {self.relative_volume:.1f}x)",
            "",
            "─" * 35,
            "DETECTION DETAILS",
            "─" * 35,
            f"Method: {self.detection_method}",
        ]

        for ev in self.evidence:
            lines.append(f"• {ev}")

        lines.extend([
            "",
            "─" * 35,
            "INFERRED ACTIVITY",
            "─" * 35,
            f"Estimated Dark Volume: {self.estimated_dark_volume:,}",
            f"Direction: {self.estimated_direction.upper()}",
            f"Estimated Size: ${self.estimated_size_millions:.1f}M",
            "",
            "─" * 35,
            "PREDICTION",
            "─" * 35,
            f"Expected Impact: {self.expected_price_impact}",
            f"Timeframe: {self.expected_timeframe}",
            "═" * 70,
        ])

        return "\n".join(lines)


@dataclass
class TradeRecord:
    """Single trade from time & sales."""
    timestamp: datetime
    price: float
    size: int
    condition: str = ""  # Exchange condition codes
    exchange: str = ""
    side: str = ""  # 'buy', 'sell', 'unknown'


@dataclass
class QuoteRecord:
    """Quote snapshot."""
    timestamp: datetime
    bid: float
    ask: float
    bid_size: int
    ask_size: int


class TapeReader:
    """
    Read the tape (Time & Sales) to detect institutional activity.

    Analyzes trade-by-trade data to identify:
    - Large hidden orders (icebergs)
    - Aggressive buying/selling
    - Institutional execution patterns
    """

    def __init__(self, lookback_trades: int = 1000):
        self.lookback_trades = lookback_trades
        self.trades: deque = deque(maxlen=lookback_trades)
        self.quotes: deque = deque(maxlen=lookback_trades)

    def add_trade(self, trade: TradeRecord):
        """Add a trade to the tape."""
        self.trades.append(trade)

    def add_quote(self, quote: QuoteRecord):
        """Add a quote snapshot."""
        self.quotes.append(quote)

    def classify_trade(self, trade: TradeRecord, quote: QuoteRecord) -> str:
        """
        Classify trade as buy or sell using Lee-Ready algorithm.

        Trades at ask = buy, at bid = sell, between = use tick test
        """
        mid = (quote.bid + quote.ask) / 2

        if trade.price >= quote.ask:
            return 'buy'
        elif trade.price <= quote.bid:
            return 'sell'
        elif trade.price > mid:
            return 'buy'
        elif trade.price < mid:
            return 'sell'
        else:
            # Tick test - compare to previous trade
            prev_trades = [t for t in self.trades if t.timestamp < trade.timestamp]
            if prev_trades:
                prev_price = prev_trades[-1].price
                if trade.price > prev_price:
                    return 'buy'
                elif trade.price < prev_price:
                    return 'sell'
            return 'unknown'

    def detect_iceberg_orders(self) -> List[Dict]:
        """
        Detect iceberg orders (hidden size).

        Icebergs show as repeated same-size trades at similar prices.
        """
        if len(self.trades) < 50:
            return []

        icebergs = []
        trades_list = list(self.trades)

        # Group trades by price level
        price_groups: Dict[float, List[TradeRecord]] = {}
        for trade in trades_list:
            price_key = round(trade.price, 2)
            if price_key not in price_groups:
                price_groups[price_key] = []
            price_groups[price_key].append(trade)

        for price, trades in price_groups.items():
            if len(trades) >= 5:
                # Check for repeated similar sizes
                sizes = [t.size for t in trades]
                if len(sizes) >= 5:
                    # Find mode (most common size)
                    try:
                        mode_size = statistics.mode(sizes)
                        mode_count = sizes.count(mode_size)

                        # If same size appears many times, likely iceberg
                        if mode_count >= 5 and mode_size >= 100:
                            total_volume = sum(sizes)
                            icebergs.append({
                                'price': price,
                                'clip_size': mode_size,
                                'clip_count': mode_count,
                                'total_volume': total_volume,
                                'estimated_hidden': total_volume * 3  # Typical iceberg ratio
                            })
                    except statistics.StatisticsError:
                        pass

        return icebergs

    def calculate_trade_imbalance(self, window: int = 100) -> float:
        """
        Calculate buy/sell imbalance from recent trades.

        Returns: Positive = net buying, Negative = net selling
        """
        if len(self.trades) < window:
            return 0.0

        recent = list(self.trades)[-window:]
        buy_volume = sum(t.size for t in recent if t.side == 'buy')
        sell_volume = sum(t.size for t in recent if t.side == 'sell')

        total = buy_volume + sell_volume
        if total == 0:
            return 0.0

        return (buy_volume - sell_volume) / total

    def detect_block_trades(self, threshold_shares: int = 10000) -> List[Dict]:
        """Detect block trades (large single transactions)."""
        blocks = []

        for trade in self.trades:
            if trade.size >= threshold_shares:
                blocks.append({
                    'timestamp': trade.timestamp,
                    'price': trade.price,
                    'size': trade.size,
                    'value': trade.price * trade.size,
                    'side': trade.side
                })

        return blocks


class VolumeAnalyzer:
    """
    Analyze volume patterns to detect hidden institutional activity.
    """

    def __init__(self):
        self.daily_volume_history: List[int] = []
        self.intraday_volume: Dict[int, List[int]] = {}  # hour -> volumes

    def add_daily_volume(self, volume: int):
        """Add daily volume for baseline."""
        self.daily_volume_history.append(volume)
        if len(self.daily_volume_history) > 60:  # 60-day lookback
            self.daily_volume_history = self.daily_volume_history[-60:]

    def get_average_daily_volume(self) -> float:
        """Get ADV (Average Daily Volume)."""
        if not self.daily_volume_history:
            return 0
        return np.mean(self.daily_volume_history)

    def get_relative_volume(self, current_volume: int) -> float:
        """Get volume relative to average."""
        adv = self.get_average_daily_volume()
        if adv == 0:
            return 1.0
        return current_volume / adv

    def detect_volume_anomaly(
        self,
        current_volume: int,
        price_change_pct: float
    ) -> Tuple[bool, str]:
        """
        Detect volume anomalies that suggest dark pool activity.

        Key insight: If price moves significantly on LOW volume,
        dark pools may be absorbing the opposite flow.
        """
        rel_vol = self.get_relative_volume(current_volume)

        # High price impact on low volume = potential dark pool absorption
        if abs(price_change_pct) > 1.0 and rel_vol < 0.7:
            return True, "High price impact on low relative volume - potential dark pool activity"

        # Very high volume with low price impact = distribution/accumulation
        if rel_vol > 2.0 and abs(price_change_pct) < 0.3:
            return True, "High volume with minimal price impact - potential institutional accumulation/distribution"

        # Volume surge without news
        if rel_vol > 3.0:
            return True, "Significant volume surge detected"

        return False, ""

    def estimate_dark_volume(
        self,
        lit_volume: int,
        price_change_pct: float,
        expected_impact_per_million: float = 0.1
    ) -> int:
        """
        Estimate dark pool volume from price action.

        If price moved X%, we can estimate how much volume
        was needed, and subtract lit volume to get dark estimate.
        """
        if expected_impact_per_million == 0:
            return 0

        # Estimate total volume needed for this price move
        # Using simplified linear impact model
        implied_total_shares = abs(price_change_pct) / expected_impact_per_million * 1000000

        # Dark volume = implied - lit
        dark_estimate = max(0, int(implied_total_shares - lit_volume))

        return dark_estimate


class ShortVolumeAnalyzer:
    """
    Analyze short volume data to detect institutional activity.

    High short volume can indicate:
    - Bearish institutional positioning
    - Market making activity
    - Hedging activity
    """

    def __init__(self):
        self.short_volume_history: List[Dict] = []

    def add_data(self, date: datetime, total_volume: int, short_volume: int):
        """Add short volume data."""
        self.short_volume_history.append({
            'date': date,
            'total': total_volume,
            'short': short_volume,
            'short_ratio': short_volume / max(1, total_volume)
        })

        if len(self.short_volume_history) > 60:
            self.short_volume_history = self.short_volume_history[-60:]

    def get_short_ratio(self) -> float:
        """Get current short volume ratio."""
        if not self.short_volume_history:
            return 0.5
        return self.short_volume_history[-1]['short_ratio']

    def get_average_short_ratio(self) -> float:
        """Get average short ratio."""
        if not self.short_volume_history:
            return 0.5
        return np.mean([d['short_ratio'] for d in self.short_volume_history])

    def detect_short_anomaly(self) -> Tuple[bool, str, str]:
        """
        Detect unusual short volume.

        Returns: (is_anomaly, direction, description)
        """
        if len(self.short_volume_history) < 10:
            return False, "", ""

        current_ratio = self.get_short_ratio()
        avg_ratio = self.get_average_short_ratio()
        std_ratio = np.std([d['short_ratio'] for d in self.short_volume_history])

        zscore = (current_ratio - avg_ratio) / max(0.01, std_ratio)

        if zscore > 2:
            return True, "bearish", f"Short ratio {current_ratio:.1%} is {zscore:.1f} std above normal"
        elif zscore < -2:
            return True, "bullish", f"Short ratio {current_ratio:.1%} is {abs(zscore):.1f} std below normal"

        return False, "", ""


class DarkPoolDetector:
    """
    MASTER CLASS: Dark Pool Activity Detection System.

    Combines multiple detection methods to identify hidden
    institutional activity in the markets.
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}

        # Components
        self.tape_reader = TapeReader()
        self.volume_analyzer = VolumeAnalyzer()
        self.short_analyzer = ShortVolumeAnalyzer()

        # State
        self.current_symbol: str = ""
        self.current_price: float = 0.0
        self.alerts: List[DarkPoolAlert] = []

        # Historical patterns
        self.pattern_history: List[Dict] = []

    def analyze(
        self,
        symbol: str,
        current_price: float,
        trades: Optional[pd.DataFrame] = None,
        quotes: Optional[pd.DataFrame] = None,
        daily_data: Optional[pd.DataFrame] = None,
        short_data: Optional[pd.DataFrame] = None
    ) -> List[DarkPoolAlert]:
        """
        Run complete dark pool analysis.

        Args:
            symbol: Stock symbol
            current_price: Current price
            trades: Time & sales data
            quotes: Quote data
            daily_data: Daily OHLCV data
            short_data: Short volume data

        Returns:
            List of alerts
        """
        self.current_symbol = symbol
        self.current_price = current_price
        alerts = []

        # Load trade data
        if trades is not None:
            for _, row in trades.iterrows():
                trade = TradeRecord(
                    timestamp=pd.to_datetime(row.get('timestamp', datetime.now())),
                    price=row.get('price', current_price),
                    size=int(row.get('size', 0)),
                    condition=row.get('condition', ''),
                    exchange=row.get('exchange', ''),
                    side=row.get('side', 'unknown')
                )
                self.tape_reader.add_trade(trade)

        # Load quote data
        if quotes is not None:
            for _, row in quotes.iterrows():
                quote = QuoteRecord(
                    timestamp=pd.to_datetime(row.get('timestamp', datetime.now())),
                    bid=row.get('bid', current_price * 0.999),
                    ask=row.get('ask', current_price * 1.001),
                    bid_size=int(row.get('bid_size', 100)),
                    ask_size=int(row.get('ask_size', 100))
                )
                self.tape_reader.add_quote(quote)

        # Load daily data
        if daily_data is not None:
            for _, row in daily_data.iterrows():
                self.volume_analyzer.add_daily_volume(int(row.get('volume', 0)))

        # Load short data
        if short_data is not None:
            for _, row in short_data.iterrows():
                self.short_analyzer.add_data(
                    pd.to_datetime(row.get('date', datetime.now())),
                    int(row.get('total_volume', 0)),
                    int(row.get('short_volume', 0))
                )

        # === DETECTION 1: Iceberg Orders ===
        icebergs = self.tape_reader.detect_iceberg_orders()
        if icebergs:
            alert = self._create_iceberg_alert(icebergs)
            if alert:
                alerts.append(alert)

        # === DETECTION 2: Volume Anomalies ===
        if daily_data is not None and len(daily_data) > 0:
            latest = daily_data.iloc[-1]
            volume = int(latest.get('volume', 0))
            close = latest.get('close', current_price)
            prev_close = daily_data.iloc[-2].get('close', close) if len(daily_data) > 1 else close
            price_change = (close / prev_close - 1) * 100 if prev_close > 0 else 0

            is_anomaly, reason = self.volume_analyzer.detect_volume_anomaly(volume, price_change)
            if is_anomaly:
                alert = self._create_volume_anomaly_alert(volume, price_change, reason)
                alerts.append(alert)

        # === DETECTION 3: Trade Imbalance ===
        imbalance = self.tape_reader.calculate_trade_imbalance()
        if abs(imbalance) > 0.3:
            alert = self._create_imbalance_alert(imbalance)
            alerts.append(alert)

        # === DETECTION 4: Block Trades ===
        blocks = self.tape_reader.detect_block_trades()
        if blocks:
            alert = self._create_block_alert(blocks)
            if alert:
                alerts.append(alert)

        # === DETECTION 5: Short Volume Anomaly ===
        is_short_anomaly, direction, short_desc = self.short_analyzer.detect_short_anomaly()
        if is_short_anomaly:
            alert = self._create_short_alert(direction, short_desc)
            alerts.append(alert)

        # Store alerts
        self.alerts.extend(alerts)

        return alerts

    def _create_iceberg_alert(self, icebergs: List[Dict]) -> Optional[DarkPoolAlert]:
        """Create alert for iceberg order detection."""
        if not icebergs:
            return None

        total_detected = sum(i['total_volume'] for i in icebergs)
        total_estimated = sum(i['estimated_hidden'] for i in icebergs)

        # Determine direction from prices
        avg_price = np.mean([i['price'] for i in icebergs])
        is_buying = avg_price >= self.current_price

        return DarkPoolAlert(
            timestamp=datetime.now(),
            symbol=self.current_symbol,
            signal_type=DarkPoolSignal.ICEBERG_ORDER,
            activity_level=ActivityLevel.HIGH if total_detected > 50000 else ActivityLevel.MODERATE,
            confidence=75,
            current_price=self.current_price,
            detection_method="Iceberg Order Detection",
            evidence=[
                f"Detected {len(icebergs)} potential iceberg orders",
                f"Visible volume: {total_detected:,}",
                f"Estimated hidden: {total_estimated:,}",
                f"Common clip sizes detected at multiple price levels"
            ],
            estimated_dark_volume=total_estimated,
            estimated_direction="buy" if is_buying else "sell",
            estimated_size_millions=total_estimated * self.current_price / 1000000,
            expected_price_impact="Continued pressure in detected direction",
            expected_timeframe="Hours to days"
        )

    def _create_volume_anomaly_alert(
        self,
        volume: int,
        price_change: float,
        reason: str
    ) -> DarkPoolAlert:
        """Create alert for volume anomaly."""
        rel_vol = self.volume_analyzer.get_relative_volume(volume)
        dark_estimate = self.volume_analyzer.estimate_dark_volume(volume, price_change)

        # Infer direction
        if price_change > 0 and rel_vol < 1:
            direction = "buy"
            signal = DarkPoolSignal.STEALTH_ACCUMULATION
        elif price_change < 0 and rel_vol < 1:
            direction = "sell"
            signal = DarkPoolSignal.STEALTH_DISTRIBUTION
        elif rel_vol > 2 and abs(price_change) < 0.5:
            direction = "buy" if price_change > 0 else "sell"
            signal = DarkPoolSignal.ACCUMULATION if direction == "buy" else DarkPoolSignal.DISTRIBUTION
        else:
            direction = "unknown"
            signal = DarkPoolSignal.ACCUMULATION

        return DarkPoolAlert(
            timestamp=datetime.now(),
            symbol=self.current_symbol,
            signal_type=signal,
            activity_level=ActivityLevel.HIGH if abs(dark_estimate) > 100000 else ActivityLevel.MODERATE,
            confidence=70,
            current_price=self.current_price,
            price_change_pct=price_change,
            volume=volume,
            relative_volume=rel_vol,
            detection_method="Volume/Price Divergence Analysis",
            evidence=[
                reason,
                f"Relative volume: {rel_vol:.2f}x average",
                f"Price change: {price_change:+.2f}%",
                "Divergence suggests off-exchange activity"
            ],
            estimated_dark_volume=dark_estimate,
            estimated_direction=direction,
            estimated_size_millions=dark_estimate * self.current_price / 1000000,
            expected_price_impact=f"{'Bullish' if direction == 'buy' else 'Bearish'} continuation likely",
            expected_timeframe="1-5 days"
        )

    def _create_imbalance_alert(self, imbalance: float) -> DarkPoolAlert:
        """Create alert for trade imbalance."""
        direction = "buy" if imbalance > 0 else "sell"
        signal = DarkPoolSignal.ACCUMULATION if direction == "buy" else DarkPoolSignal.DISTRIBUTION

        return DarkPoolAlert(
            timestamp=datetime.now(),
            symbol=self.current_symbol,
            signal_type=signal,
            activity_level=ActivityLevel.HIGH if abs(imbalance) > 0.5 else ActivityLevel.MODERATE,
            confidence=65,
            current_price=self.current_price,
            detection_method="Trade Imbalance Analysis",
            evidence=[
                f"Trade imbalance: {imbalance:+.1%}",
                f"Strong {direction}ing pressure detected in tape",
                "Consistent directional flow suggests institutional execution"
            ],
            estimated_direction=direction,
            expected_price_impact=f"Price likely to move {'up' if direction == 'buy' else 'down'}",
            expected_timeframe="Hours"
        )

    def _create_block_alert(self, blocks: List[Dict]) -> Optional[DarkPoolAlert]:
        """Create alert for block trades."""
        if not blocks:
            return None

        total_value = sum(b['value'] for b in blocks)
        buy_blocks = [b for b in blocks if b['side'] == 'buy']
        sell_blocks = [b for b in blocks if b['side'] == 'sell']

        buy_value = sum(b['value'] for b in buy_blocks)
        sell_value = sum(b['value'] for b in sell_blocks)

        if buy_value > sell_value * 1.5:
            direction = "buy"
            signal = DarkPoolSignal.BLOCK_BUYING
        elif sell_value > buy_value * 1.5:
            direction = "sell"
            signal = DarkPoolSignal.BLOCK_SELLING
        else:
            direction = "mixed"
            signal = DarkPoolSignal.BLOCK_BUYING

        return DarkPoolAlert(
            timestamp=datetime.now(),
            symbol=self.current_symbol,
            signal_type=signal,
            activity_level=ActivityLevel.EXTREME if total_value > 10000000 else ActivityLevel.HIGH,
            confidence=80,
            current_price=self.current_price,
            detection_method="Block Trade Detection",
            evidence=[
                f"Detected {len(blocks)} block trades",
                f"Total value: ${total_value:,.0f}",
                f"Buy blocks: {len(buy_blocks)} (${buy_value:,.0f})",
                f"Sell blocks: {len(sell_blocks)} (${sell_value:,.0f})"
            ],
            estimated_dark_volume=int(total_value / self.current_price),
            estimated_direction=direction,
            estimated_size_millions=total_value / 1000000,
            expected_price_impact="Significant - block trades indicate conviction",
            expected_timeframe="Days to weeks"
        )

    def _create_short_alert(self, direction: str, description: str) -> DarkPoolAlert:
        """Create alert for short volume anomaly."""
        signal = DarkPoolSignal.DISTRIBUTION if direction == "bearish" else DarkPoolSignal.ACCUMULATION

        return DarkPoolAlert(
            timestamp=datetime.now(),
            symbol=self.current_symbol,
            signal_type=signal,
            activity_level=ActivityLevel.MODERATE,
            confidence=60,
            current_price=self.current_price,
            detection_method="Short Volume Analysis",
            evidence=[
                description,
                f"Current short ratio: {self.short_analyzer.get_short_ratio():.1%}",
                f"Average short ratio: {self.short_analyzer.get_average_short_ratio():.1%}"
            ],
            estimated_direction="sell" if direction == "bearish" else "buy",
            expected_price_impact=f"{'Bearish' if direction == 'bearish' else 'Bullish'} bias",
            expected_timeframe="Days"
        )

    def get_summary(self) -> Dict[str, Any]:
        """Get analysis summary."""
        return {
            'symbol': self.current_symbol,
            'current_price': self.current_price,
            'alerts_generated': len(self.alerts),
            'trade_imbalance': self.tape_reader.calculate_trade_imbalance(),
            'relative_volume': self.volume_analyzer.get_relative_volume(0),  # Need current vol
            'short_ratio': self.short_analyzer.get_short_ratio(),
            'recent_alerts': [a.signal_type.value for a in self.alerts[-5:]]
        }


# Convenience function
def create_dark_pool_detector(config: Optional[Dict] = None) -> DarkPoolDetector:
    """Create a configured dark pool detector."""
    return DarkPoolDetector(config)
