"""
Futures Model - Specialized for ES and NQ Futures.

Complete futures-specific analysis including:
- Delta/Cumulative Delta
- Order Flow Imbalance
- Volume Profile
- Point of Control (POC)
- Value Area High/Low
- Market Profile
- Globex levels
- Fair Value Gap
- Liquidity pools
- Institutional levels

Every trade shows complete reasoning with all readings.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import logging


logger = logging.getLogger(__name__)


class FuturesSymbol(Enum):
    """Supported futures symbols."""
    ES = "ES"  # E-mini S&P 500
    NQ = "NQ"  # E-mini Nasdaq 100
    YM = "YM"  # E-mini Dow
    RTY = "RTY"  # E-mini Russell 2000


class SessionType(Enum):
    """Trading session types."""
    GLOBEX = "globex"
    RTH = "rth"  # Regular Trading Hours
    ETH = "eth"  # Extended Trading Hours


class OrderFlowBias(Enum):
    """Order flow directional bias."""
    STRONG_BUYING = "strong_buying"
    BUYING = "buying"
    NEUTRAL = "neutral"
    SELLING = "selling"
    STRONG_SELLING = "strong_selling"


@dataclass
class VolumeProfileData:
    """Volume profile analysis."""
    poc: float  # Point of Control
    vah: float  # Value Area High
    val: float  # Value Area Low
    hod: float  # High of Day
    lod: float  # Low of Day

    # Distribution
    volume_distribution: Dict[float, int] = field(default_factory=dict)

    # Key levels
    high_volume_nodes: List[float] = field(default_factory=list)
    low_volume_nodes: List[float] = field(default_factory=list)

    def get_interpretation(self, current_price: float) -> str:
        """Get interpretation relative to current price."""
        if current_price > self.vah:
            return f"Price ABOVE value area (VAH: {self.vah:.2f}) - Bullish acceptance"
        elif current_price < self.val:
            return f"Price BELOW value area (VAL: {self.val:.2f}) - Bearish acceptance"
        elif current_price > self.poc:
            return f"Price above POC ({self.poc:.2f}) - Buyers in control"
        else:
            return f"Price below POC ({self.poc:.2f}) - Sellers in control"


@dataclass
class OrderFlowData:
    """Order flow analysis data."""
    timestamp: datetime

    # Delta
    delta: float  # Buy volume - Sell volume
    cumulative_delta: float
    delta_divergence: bool  # Price/delta divergence

    # Imbalance
    bid_imbalance: float
    ask_imbalance: float
    imbalance_ratio: float

    # Absorption
    absorption_at_bid: float
    absorption_at_ask: float

    # Large orders
    large_buys: int
    large_sells: int
    large_order_imbalance: float

    # Interpretation
    bias: OrderFlowBias
    interpretation: str


@dataclass
class FuturesLevels:
    """Key futures levels."""
    # Session levels
    globex_high: float
    globex_low: float
    rth_high: float
    rth_low: float

    # Previous session
    prev_close: float
    prev_high: float
    prev_low: float

    # Calculated levels
    pivot: float
    r1: float
    r2: float
    r3: float
    s1: float
    s2: float
    s3: float

    # Fair value / premium
    fair_value: float
    premium_discount: float

    # Institutional levels
    weekly_vwap: float
    monthly_vwap: float

    def get_nearest_support(self, price: float) -> Tuple[float, str]:
        """Get nearest support level."""
        supports = [
            (self.s1, "S1"),
            (self.s2, "S2"),
            (self.s3, "S3"),
            (self.globex_low, "Globex Low"),
            (self.rth_low, "RTH Low"),
            (self.prev_low, "Previous Low"),
        ]

        below = [(level, name) for level, name in supports if level < price]
        if below:
            return max(below, key=lambda x: x[0])
        return (0, "None")

    def get_nearest_resistance(self, price: float) -> Tuple[float, str]:
        """Get nearest resistance level."""
        resistances = [
            (self.r1, "R1"),
            (self.r2, "R2"),
            (self.r3, "R3"),
            (self.globex_high, "Globex High"),
            (self.rth_high, "RTH High"),
            (self.prev_high, "Previous High"),
        ]

        above = [(level, name) for level, name in resistances if level > price]
        if above:
            return min(above, key=lambda x: x[0])
        return (99999, "None")


@dataclass
class FuturesTradeSignal:
    """Trading signal for futures with complete analysis."""
    symbol: FuturesSymbol
    direction: str  # "long" or "short"
    confidence: float
    timestamp: datetime
    session: SessionType

    # Entry/Exit levels
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float
    target_3: float

    # Tick value for PnL calculation
    tick_size: float
    tick_value: float
    potential_profit_ticks: int
    risk_ticks: int
    rr_ratio: float

    # Analysis components
    volume_profile: VolumeProfileData
    order_flow: OrderFlowData
    levels: FuturesLevels

    # Technical analysis
    technicals: Dict[str, Any] = field(default_factory=dict)

    # Market internals (passed from index model)
    market_internals: Dict[str, Any] = field(default_factory=dict)

    # Full reasoning
    primary_reason: str = ""
    order_flow_reasoning: List[str] = field(default_factory=list)
    level_reasoning: List[str] = field(default_factory=list)
    technical_reasoning: List[str] = field(default_factory=list)
    risk_factors: List[str] = field(default_factory=list)

    def get_full_reasoning(self) -> str:
        """Get complete trade reasoning with all details."""
        lines = [
            f"{'='*70}",
            f"FUTURES TRADE SIGNAL - {self.symbol.value}",
            f"{'='*70}",
            f"Direction: {self.direction.upper()}",
            f"Confidence: {self.confidence:.1%}",
            f"Session: {self.session.value.upper()}",
            f"Timestamp: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "TRADE PARAMETERS:",
            f"  Entry: {self.entry_price:.2f}",
            f"  Stop Loss: {self.stop_loss:.2f} ({self.risk_ticks} ticks, ${self.risk_ticks * self.tick_value:.2f})",
            f"  Target 1: {self.target_1:.2f}",
            f"  Target 2: {self.target_2:.2f}",
            f"  Target 3: {self.target_3:.2f} ({self.potential_profit_ticks} ticks, ${self.potential_profit_ticks * self.tick_value:.2f})",
            f"  Risk/Reward: 1:{self.rr_ratio:.1f}",
            "",
            "VOLUME PROFILE:",
            "-" * 50,
            f"  POC (Point of Control): {self.volume_profile.poc:.2f}",
            f"  VAH (Value Area High): {self.volume_profile.vah:.2f}",
            f"  VAL (Value Area Low): {self.volume_profile.val:.2f}",
            f"  {self.volume_profile.get_interpretation(self.entry_price)}",
            "",
            "ORDER FLOW ANALYSIS:",
            "-" * 50,
            f"  Delta: {self.order_flow.delta:+.0f}",
            f"  Cumulative Delta: {self.order_flow.cumulative_delta:+.0f}",
            f"  Imbalance Ratio: {self.order_flow.imbalance_ratio:.2f}",
            f"  Large Buys: {self.order_flow.large_buys}",
            f"  Large Sells: {self.order_flow.large_sells}",
            f"  Bias: {self.order_flow.bias.value.upper()}",
            f"  {self.order_flow.interpretation}",
            "",
            "KEY LEVELS:",
            "-" * 50,
            f"  Globex High: {self.levels.globex_high:.2f}",
            f"  Globex Low: {self.levels.globex_low:.2f}",
            f"  RTH High: {self.levels.rth_high:.2f}",
            f"  RTH Low: {self.levels.rth_low:.2f}",
            f"  Previous Close: {self.levels.prev_close:.2f}",
            f"  Fair Value: {self.levels.fair_value:.2f} ({self.levels.premium_discount:+.2f})",
            f"  Pivot: {self.levels.pivot:.2f}",
            f"  R1: {self.levels.r1:.2f} | S1: {self.levels.s1:.2f}",
            f"  R2: {self.levels.r2:.2f} | S2: {self.levels.s2:.2f}",
        ]

        if self.market_internals:
            lines.extend([
                "",
                "MARKET INTERNALS:",
                "-" * 50,
            ])
            for key, value in self.market_internals.items():
                lines.append(f"  {key}: {value}")

        lines.extend([
            "",
            "PRIMARY REASON:",
            f"  {self.primary_reason}",
            "",
            "ORDER FLOW FACTORS:",
        ])
        for reason in self.order_flow_reasoning:
            lines.append(f"  ✓ {reason}")

        lines.extend([
            "",
            "LEVEL-BASED FACTORS:",
        ])
        for reason in self.level_reasoning:
            lines.append(f"  ✓ {reason}")

        lines.extend([
            "",
            "TECHNICAL FACTORS:",
        ])
        for reason in self.technical_reasoning:
            lines.append(f"  ✓ {reason}")

        lines.extend([
            "",
            "RISK FACTORS:",
        ])
        for risk in self.risk_factors:
            lines.append(f"  ⚠ {risk}")

        lines.append(f"{'='*70}")

        return "\n".join(lines)


class VolumeProfileAnalyzer:
    """Analyze volume profile for futures."""

    def __init__(self, tick_size: float = 0.25):
        self.tick_size = tick_size
        self.volume_at_price: Dict[float, int] = {}

    def update(self, price: float, volume: int):
        """Update volume at price."""
        # Round to tick size
        price_level = round(price / self.tick_size) * self.tick_size

        if price_level not in self.volume_at_price:
            self.volume_at_price[price_level] = 0
        self.volume_at_price[price_level] += volume

    def calculate_profile(self, data: pd.DataFrame) -> VolumeProfileData:
        """Calculate complete volume profile."""
        # Build volume at price
        self.volume_at_price = {}
        for idx in range(len(data)):
            price = data["close"].iloc[idx]
            volume = data["volume"].iloc[idx]
            self.update(price, volume)

        if not self.volume_at_price:
            return VolumeProfileData(
                poc=data["close"].iloc[-1],
                vah=data["high"].max(),
                val=data["low"].min(),
                hod=data["high"].max(),
                lod=data["low"].min(),
            )

        # Find POC (highest volume price)
        poc = max(self.volume_at_price.keys(), key=lambda x: self.volume_at_price[x])

        # Calculate Value Area (70% of volume)
        total_volume = sum(self.volume_at_price.values())
        target_volume = total_volume * 0.70

        sorted_prices = sorted(self.volume_at_price.keys())
        poc_idx = sorted_prices.index(poc)

        # Expand from POC until 70% volume captured
        lower_idx = poc_idx
        upper_idx = poc_idx
        captured_volume = self.volume_at_price[poc]

        while captured_volume < target_volume:
            # Check which direction has more volume
            lower_vol = self.volume_at_price.get(sorted_prices[lower_idx - 1], 0) if lower_idx > 0 else 0
            upper_vol = self.volume_at_price.get(sorted_prices[upper_idx + 1], 0) if upper_idx < len(sorted_prices) - 1 else 0

            if lower_vol >= upper_vol and lower_idx > 0:
                lower_idx -= 1
                captured_volume += lower_vol
            elif upper_idx < len(sorted_prices) - 1:
                upper_idx += 1
                captured_volume += upper_vol
            else:
                break

        vah = sorted_prices[upper_idx]
        val = sorted_prices[lower_idx]

        # Find high/low volume nodes
        avg_volume = total_volume / len(self.volume_at_price)
        high_volume_nodes = [p for p, v in self.volume_at_price.items() if v > avg_volume * 1.5]
        low_volume_nodes = [p for p, v in self.volume_at_price.items() if v < avg_volume * 0.5]

        return VolumeProfileData(
            poc=poc,
            vah=vah,
            val=val,
            hod=data["high"].max(),
            lod=data["low"].min(),
            volume_distribution=self.volume_at_price.copy(),
            high_volume_nodes=sorted(high_volume_nodes),
            low_volume_nodes=sorted(low_volume_nodes),
        )


class OrderFlowAnalyzer:
    """Analyze order flow for futures."""

    def __init__(self):
        self.delta_history: List[float] = []
        self.cumulative_delta: float = 0

    def analyze(
        self,
        buy_volume: int,
        sell_volume: int,
        bid_volume: int,
        ask_volume: int,
        large_buys: int = 0,
        large_sells: int = 0,
        price_change: float = 0,
    ) -> OrderFlowData:
        """Analyze order flow data."""
        # Calculate delta
        delta = buy_volume - sell_volume
        self.delta_history.append(delta)
        self.cumulative_delta += delta

        # Calculate imbalance
        total_volume = buy_volume + sell_volume
        if total_volume > 0:
            imbalance_ratio = buy_volume / total_volume
        else:
            imbalance_ratio = 0.5

        # Detect absorption
        absorption_at_bid = bid_volume / (sell_volume + 1) if sell_volume > bid_volume * 0.7 else 0
        absorption_at_ask = ask_volume / (buy_volume + 1) if buy_volume > ask_volume * 0.7 else 0

        # Large order imbalance
        total_large = large_buys + large_sells
        large_order_imbalance = (large_buys - large_sells) / total_large if total_large > 0 else 0

        # Check for divergence
        delta_divergence = False
        if len(self.delta_history) >= 5:
            recent_delta_trend = sum(self.delta_history[-5:])
            if (price_change > 0 and recent_delta_trend < 0) or \
               (price_change < 0 and recent_delta_trend > 0):
                delta_divergence = True

        # Determine bias
        if imbalance_ratio > 0.65 and delta > 0:
            bias = OrderFlowBias.STRONG_BUYING
            interpretation = "Aggressive buying - institutions accumulating"
        elif imbalance_ratio > 0.55 and delta > 0:
            bias = OrderFlowBias.BUYING
            interpretation = "Moderate buying pressure"
        elif imbalance_ratio < 0.35 and delta < 0:
            bias = OrderFlowBias.STRONG_SELLING
            interpretation = "Aggressive selling - institutions distributing"
        elif imbalance_ratio < 0.45 and delta < 0:
            bias = OrderFlowBias.SELLING
            interpretation = "Moderate selling pressure"
        else:
            bias = OrderFlowBias.NEUTRAL
            interpretation = "Balanced order flow - no clear direction"

        if delta_divergence:
            interpretation += " [DIVERGENCE DETECTED]"

        return OrderFlowData(
            timestamp=datetime.utcnow(),
            delta=delta,
            cumulative_delta=self.cumulative_delta,
            delta_divergence=delta_divergence,
            bid_imbalance=bid_volume / (sell_volume + 1),
            ask_imbalance=ask_volume / (buy_volume + 1),
            imbalance_ratio=imbalance_ratio,
            absorption_at_bid=absorption_at_bid,
            absorption_at_ask=absorption_at_ask,
            large_buys=large_buys,
            large_sells=large_sells,
            large_order_imbalance=large_order_imbalance,
            bias=bias,
            interpretation=interpretation,
        )


class LevelCalculator:
    """Calculate key futures levels."""

    @staticmethod
    def calculate(
        globex_high: float,
        globex_low: float,
        rth_high: float,
        rth_low: float,
        prev_close: float,
        prev_high: float,
        prev_low: float,
        spot_price: float,
        futures_price: float,
        weekly_vwap: float = 0,
        monthly_vwap: float = 0,
    ) -> FuturesLevels:
        """Calculate all key levels."""
        # Pivot points (Standard)
        pivot = (prev_high + prev_low + prev_close) / 3
        r1 = 2 * pivot - prev_low
        s1 = 2 * pivot - prev_high
        r2 = pivot + (prev_high - prev_low)
        s2 = pivot - (prev_high - prev_low)
        r3 = prev_high + 2 * (pivot - prev_low)
        s3 = prev_low - 2 * (prev_high - pivot)

        # Fair value calculation
        fair_value = spot_price  # Simplified - would include dividends, interest
        premium_discount = futures_price - fair_value

        return FuturesLevels(
            globex_high=globex_high,
            globex_low=globex_low,
            rth_high=rth_high,
            rth_low=rth_low,
            prev_close=prev_close,
            prev_high=prev_high,
            prev_low=prev_low,
            pivot=pivot,
            r1=r1,
            r2=r2,
            r3=r3,
            s1=s1,
            s2=s2,
            s3=s3,
            fair_value=fair_value,
            premium_discount=premium_discount,
            weekly_vwap=weekly_vwap or futures_price,
            monthly_vwap=monthly_vwap or futures_price,
        )


class FuturesTechnicalAnalyzer:
    """Technical analysis for futures."""

    def analyze(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Analyze price data for futures."""
        close = data["close"]
        high = data["high"]
        low = data["low"]
        volume = data["volume"]

        analysis = {}

        # Price info
        analysis["current"] = close.iloc[-1]
        analysis["high"] = high.iloc[-1]
        analysis["low"] = low.iloc[-1]

        # Moving averages
        analysis["ema_9"] = close.ewm(span=9).mean().iloc[-1]
        analysis["ema_21"] = close.ewm(span=21).mean().iloc[-1]
        analysis["sma_50"] = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else close.mean()

        # VWAP
        analysis["vwap"] = ((close * volume).cumsum() / volume.cumsum()).iloc[-1]

        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 1e-10)
        analysis["rsi"] = (100 - (100 / (1 + rs))).iloc[-1]

        # ATR
        tr = pd.concat([
            high - low,
            abs(high - close.shift()),
            abs(low - close.shift())
        ], axis=1).max(axis=1)
        analysis["atr"] = tr.rolling(14).mean().iloc[-1]

        # Trend strength
        if analysis["ema_9"] > analysis["ema_21"] > analysis["sma_50"]:
            analysis["trend"] = "strong_bullish"
        elif analysis["ema_9"] > analysis["ema_21"]:
            analysis["trend"] = "bullish"
        elif analysis["ema_9"] < analysis["ema_21"] < analysis["sma_50"]:
            analysis["trend"] = "strong_bearish"
        elif analysis["ema_9"] < analysis["ema_21"]:
            analysis["trend"] = "bearish"
        else:
            analysis["trend"] = "neutral"

        return analysis


class FuturesModel:
    """
    Complete Futures Trading Model for ES/NQ.

    Combines order flow, volume profile, and levels analysis.
    """

    def __init__(self, symbol: FuturesSymbol = FuturesSymbol.ES):
        self.symbol = symbol
        self.volume_profile_analyzer = VolumeProfileAnalyzer(
            tick_size=0.25 if symbol in [FuturesSymbol.ES, FuturesSymbol.NQ] else 1.0
        )
        self.order_flow_analyzer = OrderFlowAnalyzer()
        self.technical_analyzer = FuturesTechnicalAnalyzer()

        # Symbol-specific settings
        self.tick_size = 0.25 if symbol in [FuturesSymbol.ES, FuturesSymbol.NQ] else 1.0
        self.tick_value = 12.50 if symbol == FuturesSymbol.ES else 5.00

        self.signal_history: List[FuturesTradeSignal] = []

    def generate_signal(
        self,
        price_data: pd.DataFrame,
        buy_volume: int,
        sell_volume: int,
        bid_volume: int,
        ask_volume: int,
        globex_high: float,
        globex_low: float,
        rth_high: float,
        rth_low: float,
        prev_close: float,
        prev_high: float,
        prev_low: float,
        spot_price: float,
        large_buys: int = 0,
        large_sells: int = 0,
        session: SessionType = SessionType.RTH,
        market_internals: Optional[Dict[str, Any]] = None,
    ) -> Optional[FuturesTradeSignal]:
        """Generate futures trading signal."""
        current_price = price_data["close"].iloc[-1]

        # Analyze components
        volume_profile = self.volume_profile_analyzer.calculate_profile(price_data)

        order_flow = self.order_flow_analyzer.analyze(
            buy_volume, sell_volume, bid_volume, ask_volume,
            large_buys, large_sells,
            price_data["close"].diff().iloc[-1]
        )

        levels = LevelCalculator.calculate(
            globex_high, globex_low, rth_high, rth_low,
            prev_close, prev_high, prev_low,
            spot_price, current_price
        )

        technicals = self.technical_analyzer.analyze(price_data)

        # Evaluate setup
        direction, confidence = self._evaluate_setup(
            current_price, volume_profile, order_flow, levels, technicals
        )

        if direction is None or confidence < 0.65:
            return None

        # Calculate entry/exit
        atr = technicals["atr"]

        if direction == "long":
            stop_loss = current_price - atr * 1.5
            target_1 = current_price + atr * 1.0
            target_2 = current_price + atr * 2.0
            target_3 = current_price + atr * 3.0
        else:
            stop_loss = current_price + atr * 1.5
            target_1 = current_price - atr * 1.0
            target_2 = current_price - atr * 2.0
            target_3 = current_price - atr * 3.0

        # Calculate ticks
        risk_ticks = int(abs(current_price - stop_loss) / self.tick_size)
        profit_ticks = int(abs(target_3 - current_price) / self.tick_size)
        rr_ratio = profit_ticks / max(1, risk_ticks)

        # Generate reasoning
        primary, of_reasons, level_reasons, tech_reasons, risks = self._generate_reasoning(
            direction, current_price, volume_profile, order_flow, levels, technicals
        )

        signal = FuturesTradeSignal(
            symbol=self.symbol,
            direction=direction,
            confidence=confidence,
            timestamp=datetime.utcnow(),
            session=session,
            entry_price=current_price,
            stop_loss=stop_loss,
            target_1=target_1,
            target_2=target_2,
            target_3=target_3,
            tick_size=self.tick_size,
            tick_value=self.tick_value,
            potential_profit_ticks=profit_ticks,
            risk_ticks=risk_ticks,
            rr_ratio=rr_ratio,
            volume_profile=volume_profile,
            order_flow=order_flow,
            levels=levels,
            technicals=technicals,
            market_internals=market_internals or {},
            primary_reason=primary,
            order_flow_reasoning=of_reasons,
            level_reasoning=level_reasons,
            technical_reasoning=tech_reasons,
            risk_factors=risks,
        )

        self.signal_history.append(signal)
        return signal

    def _evaluate_setup(
        self,
        price: float,
        vp: VolumeProfileData,
        of: OrderFlowData,
        levels: FuturesLevels,
        tech: Dict[str, Any],
    ) -> Tuple[Optional[str], float]:
        """Evaluate trading setup."""
        bullish_score = 0
        bearish_score = 0

        # Order flow scoring
        if of.bias == OrderFlowBias.STRONG_BUYING:
            bullish_score += 3
        elif of.bias == OrderFlowBias.BUYING:
            bullish_score += 2
        elif of.bias == OrderFlowBias.STRONG_SELLING:
            bearish_score += 3
        elif of.bias == OrderFlowBias.SELLING:
            bearish_score += 2

        # Volume profile scoring
        if price > vp.vah:
            bullish_score += 2  # Above value area
        elif price < vp.val:
            bearish_score += 2  # Below value area
        elif price > vp.poc:
            bullish_score += 1
        else:
            bearish_score += 1

        # Level scoring
        if price > levels.pivot:
            bullish_score += 1
        else:
            bearish_score += 1

        if price > levels.prev_close:
            bullish_score += 1
        else:
            bearish_score += 1

        # Technical scoring
        if tech["trend"] in ["strong_bullish", "bullish"]:
            bullish_score += 2
        elif tech["trend"] in ["strong_bearish", "bearish"]:
            bearish_score += 2

        if price > tech["vwap"]:
            bullish_score += 1
        else:
            bearish_score += 1

        # Large order imbalance
        if of.large_order_imbalance > 0.3:
            bullish_score += 2
        elif of.large_order_imbalance < -0.3:
            bearish_score += 2

        total = bullish_score + bearish_score
        if total == 0:
            return None, 0

        if bullish_score > bearish_score + 3:
            return "long", min(bullish_score / (bullish_score + bearish_score), 0.95)
        elif bearish_score > bullish_score + 3:
            return "short", min(bearish_score / (bullish_score + bearish_score), 0.95)

        return None, 0

    def _generate_reasoning(
        self,
        direction: str,
        price: float,
        vp: VolumeProfileData,
        of: OrderFlowData,
        levels: FuturesLevels,
        tech: Dict[str, Any],
    ) -> Tuple[str, List[str], List[str], List[str], List[str]]:
        """Generate complete reasoning."""
        of_reasons = []
        level_reasons = []
        tech_reasons = []
        risks = []

        if direction == "long":
            primary = f"LONG {self.symbol.value}: Order flow shows {of.bias.value} with price at/above key support"

            # Order flow
            if of.delta > 0:
                of_reasons.append(f"Positive delta: {of.delta:+.0f}")
            if of.cumulative_delta > 0:
                of_reasons.append(f"Cumulative delta positive: {of.cumulative_delta:+.0f}")
            if of.imbalance_ratio > 0.55:
                of_reasons.append(f"Buy imbalance: {of.imbalance_ratio:.1%}")
            if of.large_buys > of.large_sells:
                of_reasons.append(f"Large buyers dominating: {of.large_buys} vs {of.large_sells}")

            # Levels
            if price > vp.poc:
                level_reasons.append(f"Above POC ({vp.poc:.2f})")
            if price > levels.pivot:
                level_reasons.append(f"Above pivot ({levels.pivot:.2f})")
            support, support_name = levels.get_nearest_support(price)
            level_reasons.append(f"Support at {support_name}: {support:.2f}")

            # Technical
            if tech["trend"] in ["bullish", "strong_bullish"]:
                tech_reasons.append(f"Trend: {tech['trend']}")
            if price > tech["vwap"]:
                tech_reasons.append(f"Above VWAP ({tech['vwap']:.2f})")
            if tech["rsi"] < 60:
                tech_reasons.append(f"RSI has room ({tech['rsi']:.1f})")

            # Risks
            if of.delta_divergence:
                risks.append("Delta divergence detected")
            if tech["rsi"] > 70:
                risks.append(f"RSI overbought ({tech['rsi']:.1f})")
            if price > vp.vah * 1.01:
                risks.append("Extended above value area")

        else:  # short
            primary = f"SHORT {self.symbol.value}: Order flow shows {of.bias.value} with price at/below key resistance"

            # Order flow
            if of.delta < 0:
                of_reasons.append(f"Negative delta: {of.delta:+.0f}")
            if of.cumulative_delta < 0:
                of_reasons.append(f"Cumulative delta negative: {of.cumulative_delta:+.0f}")
            if of.imbalance_ratio < 0.45:
                of_reasons.append(f"Sell imbalance: {1-of.imbalance_ratio:.1%}")
            if of.large_sells > of.large_buys:
                of_reasons.append(f"Large sellers dominating: {of.large_sells} vs {of.large_buys}")

            # Levels
            if price < vp.poc:
                level_reasons.append(f"Below POC ({vp.poc:.2f})")
            if price < levels.pivot:
                level_reasons.append(f"Below pivot ({levels.pivot:.2f})")
            resistance, resistance_name = levels.get_nearest_resistance(price)
            level_reasons.append(f"Resistance at {resistance_name}: {resistance:.2f}")

            # Technical
            if tech["trend"] in ["bearish", "strong_bearish"]:
                tech_reasons.append(f"Trend: {tech['trend']}")
            if price < tech["vwap"]:
                tech_reasons.append(f"Below VWAP ({tech['vwap']:.2f})")
            if tech["rsi"] > 40:
                tech_reasons.append(f"RSI has room ({tech['rsi']:.1f})")

            # Risks
            if of.delta_divergence:
                risks.append("Delta divergence detected")
            if tech["rsi"] < 30:
                risks.append(f"RSI oversold ({tech['rsi']:.1f})")
            if price < vp.val * 0.99:
                risks.append("Extended below value area")

        return primary, of_reasons, level_reasons, tech_reasons, risks


def create_es_model() -> FuturesModel:
    """Create ES futures model."""
    return FuturesModel(FuturesSymbol.ES)


def create_nq_model() -> FuturesModel:
    """Create NQ futures model."""
    return FuturesModel(FuturesSymbol.NQ)


def create_futures_model(symbol: str) -> FuturesModel:
    """Create futures model for any supported symbol."""
    symbol_map = {
        "ES": FuturesSymbol.ES,
        "NQ": FuturesSymbol.NQ,
        "YM": FuturesSymbol.YM,
        "RTY": FuturesSymbol.RTY,
    }
    return FuturesModel(symbol_map.get(symbol.upper(), FuturesSymbol.ES))
