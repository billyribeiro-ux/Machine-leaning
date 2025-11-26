"""
Index Model - Specialized for SPY and QQQ.

Complete market internals analysis including:
- TRIN (Arms Index)
- TICK
- ADD (Advance/Decline)
- UVOL/DVOL (Up Volume/Down Volume)
- SKEW
- VIX analysis
- Put/Call ratio
- Sector rotation
- Breadth indicators

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


class IndexSymbol(Enum):
    """Supported index symbols."""
    SPY = "SPY"
    QQQ = "QQQ"
    IWM = "IWM"
    DIA = "DIA"


class MarketBias(Enum):
    """Market directional bias."""
    STRONG_BULLISH = "strong_bullish"
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"
    STRONG_BEARISH = "strong_bearish"


@dataclass
class MarketInternals:
    """Complete market internals snapshot."""
    timestamp: datetime

    # TRIN (Arms Index)
    # < 0.8 = bullish, > 1.2 = bearish
    trin: float = 1.0
    trin_5min_avg: float = 1.0
    trin_interpretation: str = ""

    # TICK
    # Measures net upticks vs downticks
    tick: float = 0.0
    tick_high: float = 0.0
    tick_low: float = 0.0
    tick_cumulative: float = 0.0
    tick_interpretation: str = ""

    # ADD (Advance/Decline)
    advancing: int = 0
    declining: int = 0
    unchanged: int = 0
    add_ratio: float = 1.0
    add_cumulative: float = 0.0
    add_interpretation: str = ""

    # Volume Internals
    uvol: int = 0  # Up volume
    dvol: int = 0  # Down volume
    uvol_dvol_ratio: float = 1.0
    uvol_interpretation: str = ""

    # VIX
    vix: float = 20.0
    vix_change: float = 0.0
    vix_percentile: float = 50.0
    vix_interpretation: str = ""

    # SKEW
    skew: float = 120.0
    skew_interpretation: str = ""

    # Put/Call
    put_call_ratio: float = 1.0
    put_call_interpretation: str = ""

    # Sector Performance
    sector_leaders: List[str] = field(default_factory=list)
    sector_laggards: List[str] = field(default_factory=list)

    # Overall Assessment
    overall_bias: MarketBias = MarketBias.NEUTRAL
    bias_strength: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for display."""
        return {
            "TRIN": {
                "value": f"{self.trin:.2f}",
                "5min_avg": f"{self.trin_5min_avg:.2f}",
                "interpretation": self.trin_interpretation,
            },
            "TICK": {
                "current": f"{self.tick:+.0f}",
                "high": f"{self.tick_high:+.0f}",
                "low": f"{self.tick_low:+.0f}",
                "cumulative": f"{self.tick_cumulative:+.0f}",
                "interpretation": self.tick_interpretation,
            },
            "ADD": {
                "advancing": self.advancing,
                "declining": self.declining,
                "ratio": f"{self.add_ratio:.2f}",
                "cumulative": f"{self.add_cumulative:+.0f}",
                "interpretation": self.add_interpretation,
            },
            "UVOL_DVOL": {
                "uvol": f"{self.uvol:,}",
                "dvol": f"{self.dvol:,}",
                "ratio": f"{self.uvol_dvol_ratio:.2f}",
                "interpretation": self.uvol_interpretation,
            },
            "VIX": {
                "value": f"{self.vix:.2f}",
                "change": f"{self.vix_change:+.2f}",
                "percentile": f"{self.vix_percentile:.0f}%",
                "interpretation": self.vix_interpretation,
            },
            "SKEW": {
                "value": f"{self.skew:.1f}",
                "interpretation": self.skew_interpretation,
            },
            "PUT_CALL": {
                "ratio": f"{self.put_call_ratio:.2f}",
                "interpretation": self.put_call_interpretation,
            },
            "OVERALL": {
                "bias": self.overall_bias.value,
                "strength": f"{self.bias_strength:.0%}",
            },
        }


@dataclass
class IndexTradeSignal:
    """Trading signal for index with full analysis."""
    symbol: IndexSymbol
    direction: str  # "long" or "short"
    confidence: float
    timestamp: datetime

    # Entry/Exit levels
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float
    target_3: float

    # Complete market internals at signal time
    internals: MarketInternals

    # Technical analysis
    technicals: Dict[str, Any] = field(default_factory=dict)

    # Full reasoning
    primary_reason: str = ""
    supporting_reasons: List[str] = field(default_factory=list)
    risk_factors: List[str] = field(default_factory=list)

    # Timing
    optimal_entry: str = ""
    expected_duration: str = ""

    def get_full_reasoning(self) -> str:
        """Get complete trade reasoning."""
        lines = [
            f"{'='*60}",
            f"INDEX TRADE SIGNAL - {self.symbol.value}",
            f"{'='*60}",
            f"Direction: {self.direction.upper()}",
            f"Confidence: {self.confidence:.1%}",
            f"Timestamp: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            f"ENTRY: ${self.entry_price:.2f}",
            f"STOP: ${self.stop_loss:.2f}",
            f"TARGET 1: ${self.target_1:.2f}",
            f"TARGET 2: ${self.target_2:.2f}",
            f"TARGET 3: ${self.target_3:.2f}",
            "",
            "MARKET INTERNALS:",
            "-" * 40,
            f"  TRIN: {self.internals.trin:.2f} - {self.internals.trin_interpretation}",
            f"  TICK: {self.internals.tick:+.0f} (High: {self.internals.tick_high:+.0f}, Low: {self.internals.tick_low:+.0f})",
            f"       {self.internals.tick_interpretation}",
            f"  A/D: {self.internals.advancing}/{self.internals.declining} (Ratio: {self.internals.add_ratio:.2f})",
            f"       {self.internals.add_interpretation}",
            f"  UVOL/DVOL: {self.internals.uvol:,}/{self.internals.dvol:,} (Ratio: {self.internals.uvol_dvol_ratio:.2f})",
            f"             {self.internals.uvol_interpretation}",
            f"  VIX: {self.internals.vix:.2f} ({self.internals.vix_change:+.2f}) - {self.internals.vix_interpretation}",
            f"  SKEW: {self.internals.skew:.1f} - {self.internals.skew_interpretation}",
            f"  P/C Ratio: {self.internals.put_call_ratio:.2f} - {self.internals.put_call_interpretation}",
            "",
            f"OVERALL BIAS: {self.internals.overall_bias.value.upper()} ({self.internals.bias_strength:.0%})",
            "",
            "PRIMARY REASON:",
            f"  {self.primary_reason}",
            "",
            "SUPPORTING FACTORS:",
        ]

        for reason in self.supporting_reasons:
            lines.append(f"  ✓ {reason}")

        lines.extend([
            "",
            "RISK FACTORS:",
        ])

        for risk in self.risk_factors:
            lines.append(f"  ⚠ {risk}")

        lines.extend([
            "",
            f"TIMING: {self.optimal_entry}",
            f"EXPECTED DURATION: {self.expected_duration}",
            f"{'='*60}",
        ])

        return "\n".join(lines)


class MarketInternalsAnalyzer:
    """
    Analyze market internals for index trading.
    """

    def __init__(self):
        self.trin_history: List[float] = []
        self.tick_history: List[float] = []
        self.add_history: List[float] = []

    def analyze(
        self,
        trin: float,
        tick: float,
        advancing: int,
        declining: int,
        uvol: int,
        dvol: int,
        vix: float,
        vix_prev: float,
        skew: float,
        put_call: float,
    ) -> MarketInternals:
        """Analyze all market internals."""
        internals = MarketInternals(timestamp=datetime.utcnow())

        # TRIN Analysis
        internals.trin = trin
        self.trin_history.append(trin)
        if len(self.trin_history) > 5:
            internals.trin_5min_avg = np.mean(self.trin_history[-5:])
        else:
            internals.trin_5min_avg = trin

        if trin < 0.5:
            internals.trin_interpretation = "EXTREME BULLISH - Heavy buying pressure"
        elif trin < 0.8:
            internals.trin_interpretation = "BULLISH - Buyers in control"
        elif trin < 1.0:
            internals.trin_interpretation = "SLIGHTLY BULLISH - Mild buying"
        elif trin < 1.2:
            internals.trin_interpretation = "NEUTRAL - Balanced market"
        elif trin < 1.5:
            internals.trin_interpretation = "BEARISH - Sellers in control"
        else:
            internals.trin_interpretation = "EXTREME BEARISH - Heavy selling (potential reversal)"

        # TICK Analysis
        internals.tick = tick
        self.tick_history.append(tick)
        if self.tick_history:
            internals.tick_high = max(self.tick_history[-100:]) if len(self.tick_history) > 100 else max(self.tick_history)
            internals.tick_low = min(self.tick_history[-100:]) if len(self.tick_history) > 100 else min(self.tick_history)
            internals.tick_cumulative = sum(self.tick_history[-100:]) if len(self.tick_history) > 100 else sum(self.tick_history)

        if tick > 800:
            internals.tick_interpretation = "EXTREME BULLISH - Strong buying surge"
        elif tick > 400:
            internals.tick_interpretation = "BULLISH - Buyers aggressive"
        elif tick > 0:
            internals.tick_interpretation = "SLIGHTLY BULLISH"
        elif tick > -400:
            internals.tick_interpretation = "SLIGHTLY BEARISH"
        elif tick > -800:
            internals.tick_interpretation = "BEARISH - Sellers aggressive"
        else:
            internals.tick_interpretation = "EXTREME BEARISH - Strong selling surge"

        # A/D Analysis
        internals.advancing = advancing
        internals.declining = declining
        total = advancing + declining
        internals.add_ratio = advancing / (declining + 1)

        current_add = advancing - declining
        self.add_history.append(current_add)
        internals.add_cumulative = sum(self.add_history[-100:]) if len(self.add_history) > 100 else sum(self.add_history)

        if internals.add_ratio > 3:
            internals.add_interpretation = "EXTREME BULLISH - Broad participation"
        elif internals.add_ratio > 2:
            internals.add_interpretation = "BULLISH - Good breadth"
        elif internals.add_ratio > 1.2:
            internals.add_interpretation = "SLIGHTLY BULLISH"
        elif internals.add_ratio > 0.8:
            internals.add_interpretation = "NEUTRAL"
        elif internals.add_ratio > 0.5:
            internals.add_interpretation = "BEARISH - Poor breadth"
        else:
            internals.add_interpretation = "EXTREME BEARISH - Broad selling"

        # UVOL/DVOL
        internals.uvol = uvol
        internals.dvol = dvol
        internals.uvol_dvol_ratio = uvol / (dvol + 1)

        if internals.uvol_dvol_ratio > 4:
            internals.uvol_interpretation = "EXTREME BULLISH - Volume strongly to upside"
        elif internals.uvol_dvol_ratio > 2:
            internals.uvol_interpretation = "BULLISH - Good upside volume"
        elif internals.uvol_dvol_ratio > 1.2:
            internals.uvol_interpretation = "SLIGHTLY BULLISH"
        elif internals.uvol_dvol_ratio > 0.8:
            internals.uvol_interpretation = "NEUTRAL"
        elif internals.uvol_dvol_ratio > 0.5:
            internals.uvol_interpretation = "BEARISH - Volume to downside"
        else:
            internals.uvol_interpretation = "EXTREME BEARISH - Heavy selling volume"

        # VIX Analysis
        internals.vix = vix
        internals.vix_change = vix - vix_prev

        # VIX percentile (simplified - would need historical data)
        if vix < 12:
            internals.vix_percentile = 5
        elif vix < 15:
            internals.vix_percentile = 20
        elif vix < 20:
            internals.vix_percentile = 50
        elif vix < 25:
            internals.vix_percentile = 70
        elif vix < 30:
            internals.vix_percentile = 85
        else:
            internals.vix_percentile = 95

        if vix < 12:
            internals.vix_interpretation = "EXTREME COMPLACENCY - Caution warranted"
        elif vix < 15:
            internals.vix_interpretation = "LOW FEAR - Bullish conditions"
        elif vix < 20:
            internals.vix_interpretation = "NORMAL - Balanced sentiment"
        elif vix < 25:
            internals.vix_interpretation = "ELEVATED - Some fear"
        elif vix < 30:
            internals.vix_interpretation = "HIGH FEAR - Potential bottom"
        else:
            internals.vix_interpretation = "EXTREME FEAR - Capitulation possible"

        # SKEW Analysis
        internals.skew = skew

        if skew < 110:
            internals.skew_interpretation = "LOW TAIL RISK - Complacent"
        elif skew < 125:
            internals.skew_interpretation = "NORMAL TAIL RISK"
        elif skew < 140:
            internals.skew_interpretation = "ELEVATED TAIL RISK - Hedging active"
        else:
            internals.skew_interpretation = "HIGH TAIL RISK - Crash concern"

        # Put/Call
        internals.put_call_ratio = put_call

        if put_call < 0.7:
            internals.put_call_interpretation = "EXTREME BULLISH - Low put buying"
        elif put_call < 0.9:
            internals.put_call_interpretation = "BULLISH"
        elif put_call < 1.1:
            internals.put_call_interpretation = "NEUTRAL"
        elif put_call < 1.3:
            internals.put_call_interpretation = "BEARISH - Elevated put buying"
        else:
            internals.put_call_interpretation = "EXTREME BEARISH - Heavy hedging (contrarian bullish)"

        # Overall bias calculation
        bullish_score = 0
        bearish_score = 0

        # TRIN contribution
        if trin < 0.8:
            bullish_score += 2
        elif trin < 1.0:
            bullish_score += 1
        elif trin > 1.2:
            bearish_score += 2
        elif trin > 1.0:
            bearish_score += 1

        # TICK contribution
        if tick > 400:
            bullish_score += 2
        elif tick > 0:
            bullish_score += 1
        elif tick < -400:
            bearish_score += 2
        elif tick < 0:
            bearish_score += 1

        # A/D contribution
        if internals.add_ratio > 2:
            bullish_score += 2
        elif internals.add_ratio > 1:
            bullish_score += 1
        elif internals.add_ratio < 0.5:
            bearish_score += 2
        elif internals.add_ratio < 1:
            bearish_score += 1

        # UVOL/DVOL contribution
        if internals.uvol_dvol_ratio > 2:
            bullish_score += 2
        elif internals.uvol_dvol_ratio > 1:
            bullish_score += 1
        elif internals.uvol_dvol_ratio < 0.5:
            bearish_score += 2
        elif internals.uvol_dvol_ratio < 1:
            bearish_score += 1

        # VIX contribution (contrarian)
        if vix > 30:
            bullish_score += 1  # Extreme fear = contrarian bullish
        elif vix < 12:
            bearish_score += 1  # Extreme complacency = contrarian bearish

        total_score = bullish_score + bearish_score
        if total_score > 0:
            internals.bias_strength = abs(bullish_score - bearish_score) / total_score
        else:
            internals.bias_strength = 0

        if bullish_score > bearish_score + 4:
            internals.overall_bias = MarketBias.STRONG_BULLISH
        elif bullish_score > bearish_score + 2:
            internals.overall_bias = MarketBias.BULLISH
        elif bearish_score > bullish_score + 4:
            internals.overall_bias = MarketBias.STRONG_BEARISH
        elif bearish_score > bullish_score + 2:
            internals.overall_bias = MarketBias.BEARISH
        else:
            internals.overall_bias = MarketBias.NEUTRAL

        return internals


class IndexTechnicalAnalyzer:
    """Technical analysis specifically for index trading."""

    def analyze(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Analyze price data for index."""
        close = data["close"]
        high = data["high"]
        low = data["low"]
        volume = data["volume"]

        analysis = {}

        # Moving averages
        analysis["sma_9"] = close.rolling(9).mean().iloc[-1]
        analysis["sma_20"] = close.rolling(20).mean().iloc[-1]
        analysis["sma_50"] = close.rolling(50).mean().iloc[-1]
        analysis["ema_8"] = close.ewm(span=8).mean().iloc[-1]
        analysis["ema_21"] = close.ewm(span=21).mean().iloc[-1]
        analysis["vwap"] = ((close * volume).cumsum() / volume.cumsum()).iloc[-1]

        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 1e-10)
        analysis["rsi"] = (100 - (100 / (1 + rs))).iloc[-1]

        # MACD
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        analysis["macd"] = macd.iloc[-1]
        analysis["macd_signal"] = signal.iloc[-1]
        analysis["macd_histogram"] = (macd - signal).iloc[-1]

        # Bollinger Bands
        sma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        analysis["bb_upper"] = (sma20 + 2 * std20).iloc[-1]
        analysis["bb_lower"] = (sma20 - 2 * std20).iloc[-1]
        analysis["bb_middle"] = sma20.iloc[-1]

        # ATR
        tr = pd.concat([
            high - low,
            abs(high - close.shift()),
            abs(low - close.shift())
        ], axis=1).max(axis=1)
        analysis["atr"] = tr.rolling(14).mean().iloc[-1]

        # Price position
        analysis["current_price"] = close.iloc[-1]
        analysis["day_high"] = high.iloc[-1]
        analysis["day_low"] = low.iloc[-1]
        analysis["price_vs_vwap"] = "above" if close.iloc[-1] > analysis["vwap"] else "below"

        # Trend
        if analysis["ema_8"] > analysis["ema_21"] > analysis["sma_50"]:
            analysis["trend"] = "bullish"
        elif analysis["ema_8"] < analysis["ema_21"] < analysis["sma_50"]:
            analysis["trend"] = "bearish"
        else:
            analysis["trend"] = "neutral"

        return analysis


class IndexModel:
    """
    Complete Index Trading Model for SPY/QQQ.

    Combines market internals with technical analysis
    for high-probability index trades.
    """

    def __init__(self, symbol: IndexSymbol = IndexSymbol.SPY):
        self.symbol = symbol
        self.internals_analyzer = MarketInternalsAnalyzer()
        self.technical_analyzer = IndexTechnicalAnalyzer()

        self.signal_history: List[IndexTradeSignal] = []

    def generate_signal(
        self,
        price_data: pd.DataFrame,
        trin: float,
        tick: float,
        advancing: int,
        declining: int,
        uvol: int,
        dvol: int,
        vix: float,
        vix_prev: float,
        skew: float,
        put_call: float,
    ) -> Optional[IndexTradeSignal]:
        """
        Generate trading signal with complete analysis.
        """
        # Analyze internals
        internals = self.internals_analyzer.analyze(
            trin, tick, advancing, declining,
            uvol, dvol, vix, vix_prev, skew, put_call
        )

        # Analyze technicals
        technicals = self.technical_analyzer.analyze(price_data)

        # Determine if signal should be generated
        direction, confidence = self._evaluate_setup(internals, technicals)

        if direction is None or confidence < 0.7:
            return None

        current_price = technicals["current_price"]
        atr = technicals["atr"]

        # Calculate levels
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

        # Generate reasoning
        primary_reason, supporting, risks = self._generate_reasoning(
            direction, internals, technicals
        )

        signal = IndexTradeSignal(
            symbol=self.symbol,
            direction=direction,
            confidence=confidence,
            timestamp=datetime.utcnow(),
            entry_price=current_price,
            stop_loss=stop_loss,
            target_1=target_1,
            target_2=target_2,
            target_3=target_3,
            internals=internals,
            technicals=technicals,
            primary_reason=primary_reason,
            supporting_reasons=supporting,
            risk_factors=risks,
            optimal_entry=self._get_optimal_entry(direction, internals, technicals),
            expected_duration=self._estimate_duration(atr, current_price),
        )

        self.signal_history.append(signal)

        return signal

    def _evaluate_setup(
        self,
        internals: MarketInternals,
        technicals: Dict[str, Any],
    ) -> Tuple[Optional[str], float]:
        """Evaluate if setup warrants a trade."""
        bullish_points = 0
        bearish_points = 0

        # Internals scoring
        if internals.overall_bias == MarketBias.STRONG_BULLISH:
            bullish_points += 3
        elif internals.overall_bias == MarketBias.BULLISH:
            bullish_points += 2
        elif internals.overall_bias == MarketBias.STRONG_BEARISH:
            bearish_points += 3
        elif internals.overall_bias == MarketBias.BEARISH:
            bearish_points += 2

        # Technical scoring
        if technicals["trend"] == "bullish":
            bullish_points += 2
        elif technicals["trend"] == "bearish":
            bearish_points += 2

        if technicals["price_vs_vwap"] == "above":
            bullish_points += 1
        else:
            bearish_points += 1

        if technicals["rsi"] < 30:
            bullish_points += 2  # Oversold
        elif technicals["rsi"] < 40:
            bullish_points += 1
        elif technicals["rsi"] > 70:
            bearish_points += 2  # Overbought
        elif technicals["rsi"] > 60:
            bearish_points += 1

        if technicals["macd_histogram"] > 0:
            bullish_points += 1
        else:
            bearish_points += 1

        total_points = bullish_points + bearish_points

        if total_points == 0:
            return None, 0.0

        if bullish_points > bearish_points + 2:
            direction = "long"
            confidence = bullish_points / (bullish_points + bearish_points)
        elif bearish_points > bullish_points + 2:
            direction = "short"
            confidence = bearish_points / (bullish_points + bearish_points)
        else:
            return None, 0.0

        return direction, min(confidence, 0.95)

    def _generate_reasoning(
        self,
        direction: str,
        internals: MarketInternals,
        technicals: Dict[str, Any],
    ) -> Tuple[str, List[str], List[str]]:
        """Generate complete trade reasoning."""
        supporting = []
        risks = []

        if direction == "long":
            primary = f"LONG {self.symbol.value}: {internals.overall_bias.value.upper()} market internals align with {technicals['trend']} technical trend"

            # Supporting factors
            if internals.trin < 1.0:
                supporting.append(f"TRIN at {internals.trin:.2f} shows buying pressure")
            if internals.tick > 0:
                supporting.append(f"TICK positive at {internals.tick:+.0f}")
            if internals.add_ratio > 1:
                supporting.append(f"A/D ratio {internals.add_ratio:.2f} - more advancers")
            if internals.uvol_dvol_ratio > 1:
                supporting.append(f"Up volume dominates ({internals.uvol_dvol_ratio:.2f}x)")
            if technicals["price_vs_vwap"] == "above":
                supporting.append(f"Price above VWAP (${technicals['vwap']:.2f})")
            if technicals["macd_histogram"] > 0:
                supporting.append(f"MACD histogram positive ({technicals['macd_histogram']:.3f})")
            if technicals["rsi"] < 50:
                supporting.append(f"RSI has room to run ({technicals['rsi']:.1f})")

            # Risks
            if internals.vix < 15:
                risks.append("VIX complacency - potential for volatility spike")
            if internals.skew > 130:
                risks.append(f"Elevated SKEW ({internals.skew:.0f}) - tail risk hedging")
            if technicals["rsi"] > 70:
                risks.append(f"RSI overbought ({technicals['rsi']:.1f})")

        else:  # short
            primary = f"SHORT {self.symbol.value}: {internals.overall_bias.value.upper()} market internals align with {technicals['trend']} technical trend"

            # Supporting factors
            if internals.trin > 1.0:
                supporting.append(f"TRIN at {internals.trin:.2f} shows selling pressure")
            if internals.tick < 0:
                supporting.append(f"TICK negative at {internals.tick:+.0f}")
            if internals.add_ratio < 1:
                supporting.append(f"A/D ratio {internals.add_ratio:.2f} - more decliners")
            if internals.uvol_dvol_ratio < 1:
                supporting.append(f"Down volume dominates ({1/internals.uvol_dvol_ratio:.2f}x)")
            if technicals["price_vs_vwap"] == "below":
                supporting.append(f"Price below VWAP (${technicals['vwap']:.2f})")
            if technicals["macd_histogram"] < 0:
                supporting.append(f"MACD histogram negative ({technicals['macd_histogram']:.3f})")
            if technicals["rsi"] > 50:
                supporting.append(f"RSI has room to fall ({technicals['rsi']:.1f})")

            # Risks
            if internals.vix > 30:
                risks.append("VIX extreme - potential for reversal")
            if internals.put_call_ratio > 1.2:
                risks.append(f"High put/call ({internals.put_call_ratio:.2f}) - contrarian bullish")
            if technicals["rsi"] < 30:
                risks.append(f"RSI oversold ({technicals['rsi']:.1f})")

        return primary, supporting, risks

    def _get_optimal_entry(
        self,
        direction: str,
        internals: MarketInternals,
        technicals: Dict[str, Any],
    ) -> str:
        """Determine optimal entry timing."""
        if direction == "long":
            if internals.tick < 0 and internals.overall_bias in [MarketBias.BULLISH, MarketBias.STRONG_BULLISH]:
                return "Enter on TICK pullback below 0"
            elif technicals["current_price"] > technicals["vwap"]:
                return "Enter on pullback to VWAP"
            else:
                return "Enter at market"
        else:
            if internals.tick > 0 and internals.overall_bias in [MarketBias.BEARISH, MarketBias.STRONG_BEARISH]:
                return "Enter on TICK bounce above 0"
            elif technicals["current_price"] < technicals["vwap"]:
                return "Enter on bounce to VWAP"
            else:
                return "Enter at market"

    def _estimate_duration(self, atr: float, price: float) -> str:
        """Estimate trade duration."""
        atr_pct = atr / price
        if atr_pct > 0.02:
            return "30-60 minutes (high volatility)"
        elif atr_pct > 0.01:
            return "1-2 hours"
        else:
            return "2-4 hours (low volatility)"


def create_spy_model() -> IndexModel:
    """Create SPY-specialized model."""
    return IndexModel(IndexSymbol.SPY)


def create_qqq_model() -> IndexModel:
    """Create QQQ-specialized model."""
    return IndexModel(IndexSymbol.QQQ)


def create_index_model(symbol: str) -> IndexModel:
    """Create index model for any supported symbol."""
    symbol_map = {
        "SPY": IndexSymbol.SPY,
        "QQQ": IndexSymbol.QQQ,
        "IWM": IndexSymbol.IWM,
        "DIA": IndexSymbol.DIA,
    }
    return IndexModel(symbol_map.get(symbol.upper(), IndexSymbol.SPY))
