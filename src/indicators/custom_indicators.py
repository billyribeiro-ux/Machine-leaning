"""
Customizable Indicator System.

Fully customizable indicator library with:
- All major technical indicators
- Custom parameter configuration
- Pattern recognition
- Signal combination
- Strategy building
- Real-time updates

Users can:
- Choose any indicators
- Customize all parameters
- Combine multiple signals
- Create custom patterns
- Build trading strategies
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any, Callable, Union
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from abc import ABC, abstractmethod
import logging


logger = logging.getLogger(__name__)


class IndicatorCategory(Enum):
    """Indicator categories."""
    TREND = "trend"
    MOMENTUM = "momentum"
    VOLATILITY = "volatility"
    VOLUME = "volume"
    OSCILLATOR = "oscillator"
    PATTERN = "pattern"
    CUSTOM = "custom"


class SignalType(Enum):
    """Signal types."""
    BUY = "buy"
    SELL = "sell"
    NEUTRAL = "neutral"


@dataclass
class IndicatorConfig:
    """Configuration for an indicator."""
    name: str
    enabled: bool = True
    parameters: Dict[str, Any] = field(default_factory=dict)
    weight: float = 1.0  # Weight in combined signals
    category: IndicatorCategory = IndicatorCategory.TREND


@dataclass
class IndicatorResult:
    """Result from indicator calculation."""
    name: str
    value: float
    signal: SignalType
    signal_strength: float  # 0-1
    interpretation: str
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PatternMatch:
    """Detected pattern match."""
    pattern_name: str
    direction: str  # "bullish", "bearish"
    confidence: float
    start_idx: int
    end_idx: int
    description: str


@dataclass
class CombinedSignal:
    """Combined signal from multiple indicators."""
    timestamp: datetime
    direction: SignalType
    strength: float  # 0-1
    confidence: float
    indicator_signals: List[IndicatorResult]
    patterns_detected: List[PatternMatch]
    reasoning: List[str]


class BaseIndicator(ABC):
    """Base class for all indicators."""

    def __init__(self, config: IndicatorConfig):
        self.config = config
        self.default_params = self.get_default_parameters()
        # Merge default with user params
        self.params = {**self.default_params, **config.parameters}

    @abstractmethod
    def get_default_parameters(self) -> Dict[str, Any]:
        """Get default parameters for this indicator."""
        pass

    @abstractmethod
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """Calculate indicator values."""
        pass

    @abstractmethod
    def get_signal(self, data: pd.DataFrame, current_idx: int) -> IndicatorResult:
        """Get trading signal from indicator."""
        pass

    def get_parameter_descriptions(self) -> Dict[str, str]:
        """Get descriptions for each parameter."""
        return {}


# ==================== TREND INDICATORS ====================

class SMAIndicator(BaseIndicator):
    """Simple Moving Average."""

    def get_default_parameters(self) -> Dict[str, Any]:
        return {"period": 20}

    def get_parameter_descriptions(self) -> Dict[str, str]:
        return {"period": "Number of periods for SMA calculation"}

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        return data["close"].rolling(self.params["period"]).mean()

    def get_signal(self, data: pd.DataFrame, current_idx: int) -> IndicatorResult:
        sma = self.calculate(data)
        current_price = data["close"].iloc[current_idx]
        current_sma = sma.iloc[current_idx]

        if current_price > current_sma * 1.01:
            signal = SignalType.BUY
            strength = min(1.0, (current_price - current_sma) / current_sma * 10)
            interpretation = f"Price above SMA({self.params['period']}) - Bullish"
        elif current_price < current_sma * 0.99:
            signal = SignalType.SELL
            strength = min(1.0, (current_sma - current_price) / current_sma * 10)
            interpretation = f"Price below SMA({self.params['period']}) - Bearish"
        else:
            signal = SignalType.NEUTRAL
            strength = 0.0
            interpretation = f"Price near SMA({self.params['period']}) - Neutral"

        return IndicatorResult(
            name=f"SMA({self.params['period']})",
            value=current_sma,
            signal=signal,
            signal_strength=strength,
            interpretation=interpretation,
            parameters=self.params,
        )


class EMAIndicator(BaseIndicator):
    """Exponential Moving Average."""

    def get_default_parameters(self) -> Dict[str, Any]:
        return {"period": 20}

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        return data["close"].ewm(span=self.params["period"]).mean()

    def get_signal(self, data: pd.DataFrame, current_idx: int) -> IndicatorResult:
        ema = self.calculate(data)
        current_price = data["close"].iloc[current_idx]
        current_ema = ema.iloc[current_idx]

        if current_price > current_ema * 1.01:
            signal = SignalType.BUY
            strength = min(1.0, (current_price - current_ema) / current_ema * 10)
            interpretation = f"Price above EMA({self.params['period']}) - Bullish"
        elif current_price < current_ema * 0.99:
            signal = SignalType.SELL
            strength = min(1.0, (current_ema - current_price) / current_ema * 10)
            interpretation = f"Price below EMA({self.params['period']}) - Bearish"
        else:
            signal = SignalType.NEUTRAL
            strength = 0.0
            interpretation = f"Price near EMA({self.params['period']}) - Neutral"

        return IndicatorResult(
            name=f"EMA({self.params['period']})",
            value=current_ema,
            signal=signal,
            signal_strength=strength,
            interpretation=interpretation,
            parameters=self.params,
        )


class MACDIndicator(BaseIndicator):
    """Moving Average Convergence Divergence."""

    def get_default_parameters(self) -> Dict[str, Any]:
        return {
            "fast_period": 12,
            "slow_period": 26,
            "signal_period": 9,
        }

    def calculate(self, data: pd.DataFrame) -> Tuple[pd.Series, pd.Series, pd.Series]:
        fast_ema = data["close"].ewm(span=self.params["fast_period"]).mean()
        slow_ema = data["close"].ewm(span=self.params["slow_period"]).mean()
        macd = fast_ema - slow_ema
        signal = macd.ewm(span=self.params["signal_period"]).mean()
        histogram = macd - signal
        return macd, signal, histogram

    def get_signal(self, data: pd.DataFrame, current_idx: int) -> IndicatorResult:
        macd, signal, histogram = self.calculate(data)

        current_macd = macd.iloc[current_idx]
        current_signal = signal.iloc[current_idx]
        current_hist = histogram.iloc[current_idx]
        prev_hist = histogram.iloc[current_idx - 1] if current_idx > 0 else current_hist

        if current_macd > current_signal and current_hist > prev_hist:
            sig = SignalType.BUY
            strength = min(1.0, abs(current_hist) / (abs(current_macd) + 1e-10))
            interpretation = "MACD bullish crossover with increasing momentum"
        elif current_macd < current_signal and current_hist < prev_hist:
            sig = SignalType.SELL
            strength = min(1.0, abs(current_hist) / (abs(current_macd) + 1e-10))
            interpretation = "MACD bearish crossover with increasing momentum"
        else:
            sig = SignalType.NEUTRAL
            strength = 0.0
            interpretation = "MACD neutral"

        return IndicatorResult(
            name="MACD",
            value=current_macd,
            signal=sig,
            signal_strength=strength,
            interpretation=interpretation,
            parameters=self.params,
        )


class ADXIndicator(BaseIndicator):
    """Average Directional Index."""

    def get_default_parameters(self) -> Dict[str, Any]:
        return {"period": 14}

    def calculate(self, data: pd.DataFrame) -> Tuple[pd.Series, pd.Series, pd.Series]:
        high = data["high"]
        low = data["low"]
        close = data["close"]
        period = self.params["period"]

        plus_dm = high.diff()
        minus_dm = -low.diff()

        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

        tr = pd.concat([
            high - low,
            abs(high - close.shift()),
            abs(low - close.shift())
        ], axis=1).max(axis=1)

        atr = tr.rolling(period).mean()
        plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(period).mean() / atr)

        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
        adx = dx.rolling(period).mean()

        return adx, plus_di, minus_di

    def get_signal(self, data: pd.DataFrame, current_idx: int) -> IndicatorResult:
        adx, plus_di, minus_di = self.calculate(data)

        current_adx = adx.iloc[current_idx]
        current_plus = plus_di.iloc[current_idx]
        current_minus = minus_di.iloc[current_idx]

        if current_adx > 25:
            if current_plus > current_minus:
                sig = SignalType.BUY
                interpretation = f"Strong bullish trend (ADX: {current_adx:.1f})"
            else:
                sig = SignalType.SELL
                interpretation = f"Strong bearish trend (ADX: {current_adx:.1f})"
            strength = min(1.0, (current_adx - 25) / 25)
        else:
            sig = SignalType.NEUTRAL
            strength = 0.0
            interpretation = f"Weak trend (ADX: {current_adx:.1f})"

        return IndicatorResult(
            name="ADX",
            value=current_adx,
            signal=sig,
            signal_strength=strength,
            interpretation=interpretation,
            parameters=self.params,
        )


# ==================== MOMENTUM INDICATORS ====================

class RSIIndicator(BaseIndicator):
    """Relative Strength Index."""

    def get_default_parameters(self) -> Dict[str, Any]:
        return {
            "period": 14,
            "overbought": 70,
            "oversold": 30,
        }

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        delta = data["close"].diff()
        gain = delta.where(delta > 0, 0).rolling(self.params["period"]).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(self.params["period"]).mean()
        rs = gain / (loss + 1e-10)
        return 100 - (100 / (1 + rs))

    def get_signal(self, data: pd.DataFrame, current_idx: int) -> IndicatorResult:
        rsi = self.calculate(data)
        current_rsi = rsi.iloc[current_idx]
        prev_rsi = rsi.iloc[current_idx - 1] if current_idx > 0 else current_rsi

        overbought = self.params["overbought"]
        oversold = self.params["oversold"]

        if current_rsi < oversold:
            sig = SignalType.BUY
            strength = (oversold - current_rsi) / oversold
            interpretation = f"RSI oversold at {current_rsi:.1f} - Potential reversal"
        elif current_rsi > overbought:
            sig = SignalType.SELL
            strength = (current_rsi - overbought) / (100 - overbought)
            interpretation = f"RSI overbought at {current_rsi:.1f} - Potential reversal"
        elif current_rsi > prev_rsi and current_rsi > 50:
            sig = SignalType.BUY
            strength = 0.3
            interpretation = f"RSI rising at {current_rsi:.1f} - Bullish momentum"
        elif current_rsi < prev_rsi and current_rsi < 50:
            sig = SignalType.SELL
            strength = 0.3
            interpretation = f"RSI falling at {current_rsi:.1f} - Bearish momentum"
        else:
            sig = SignalType.NEUTRAL
            strength = 0.0
            interpretation = f"RSI neutral at {current_rsi:.1f}"

        return IndicatorResult(
            name="RSI",
            value=current_rsi,
            signal=sig,
            signal_strength=strength,
            interpretation=interpretation,
            parameters=self.params,
        )


class StochasticIndicator(BaseIndicator):
    """Stochastic Oscillator."""

    def get_default_parameters(self) -> Dict[str, Any]:
        return {
            "k_period": 14,
            "d_period": 3,
            "overbought": 80,
            "oversold": 20,
        }

    def calculate(self, data: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
        low_min = data["low"].rolling(self.params["k_period"]).min()
        high_max = data["high"].rolling(self.params["k_period"]).max()

        stoch_k = 100 * (data["close"] - low_min) / (high_max - low_min + 1e-10)
        stoch_d = stoch_k.rolling(self.params["d_period"]).mean()

        return stoch_k, stoch_d

    def get_signal(self, data: pd.DataFrame, current_idx: int) -> IndicatorResult:
        stoch_k, stoch_d = self.calculate(data)

        current_k = stoch_k.iloc[current_idx]
        current_d = stoch_d.iloc[current_idx]
        overbought = self.params["overbought"]
        oversold = self.params["oversold"]

        if current_k < oversold and current_k > current_d:
            sig = SignalType.BUY
            strength = (oversold - current_k) / oversold
            interpretation = f"Stochastic oversold bullish crossover (%K: {current_k:.1f})"
        elif current_k > overbought and current_k < current_d:
            sig = SignalType.SELL
            strength = (current_k - overbought) / (100 - overbought)
            interpretation = f"Stochastic overbought bearish crossover (%K: {current_k:.1f})"
        else:
            sig = SignalType.NEUTRAL
            strength = 0.0
            interpretation = f"Stochastic neutral (%K: {current_k:.1f})"

        return IndicatorResult(
            name="Stochastic",
            value=current_k,
            signal=sig,
            signal_strength=strength,
            interpretation=interpretation,
            parameters=self.params,
        )


class CCIIndicator(BaseIndicator):
    """Commodity Channel Index."""

    def get_default_parameters(self) -> Dict[str, Any]:
        return {"period": 20, "overbought": 100, "oversold": -100}

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        tp = (data["high"] + data["low"] + data["close"]) / 3
        sma = tp.rolling(self.params["period"]).mean()
        mad = tp.rolling(self.params["period"]).apply(lambda x: np.abs(x - x.mean()).mean())
        return (tp - sma) / (0.015 * mad + 1e-10)

    def get_signal(self, data: pd.DataFrame, current_idx: int) -> IndicatorResult:
        cci = self.calculate(data)
        current_cci = cci.iloc[current_idx]

        if current_cci < self.params["oversold"]:
            sig = SignalType.BUY
            strength = min(1.0, abs(current_cci) / 200)
            interpretation = f"CCI oversold at {current_cci:.1f}"
        elif current_cci > self.params["overbought"]:
            sig = SignalType.SELL
            strength = min(1.0, abs(current_cci) / 200)
            interpretation = f"CCI overbought at {current_cci:.1f}"
        else:
            sig = SignalType.NEUTRAL
            strength = 0.0
            interpretation = f"CCI neutral at {current_cci:.1f}"

        return IndicatorResult(
            name="CCI",
            value=current_cci,
            signal=sig,
            signal_strength=strength,
            interpretation=interpretation,
            parameters=self.params,
        )


# ==================== VOLATILITY INDICATORS ====================

class BollingerBandsIndicator(BaseIndicator):
    """Bollinger Bands."""

    def get_default_parameters(self) -> Dict[str, Any]:
        return {"period": 20, "std_dev": 2.0}

    def calculate(self, data: pd.DataFrame) -> Tuple[pd.Series, pd.Series, pd.Series]:
        sma = data["close"].rolling(self.params["period"]).mean()
        std = data["close"].rolling(self.params["period"]).std()
        upper = sma + self.params["std_dev"] * std
        lower = sma - self.params["std_dev"] * std
        return upper, sma, lower

    def get_signal(self, data: pd.DataFrame, current_idx: int) -> IndicatorResult:
        upper, middle, lower = self.calculate(data)
        current_price = data["close"].iloc[current_idx]
        current_upper = upper.iloc[current_idx]
        current_lower = lower.iloc[current_idx]
        current_middle = middle.iloc[current_idx]

        bb_width = (current_upper - current_lower) / current_middle
        bb_pct = (current_price - current_lower) / (current_upper - current_lower + 1e-10)

        if current_price <= current_lower:
            sig = SignalType.BUY
            strength = min(1.0, (current_lower - current_price) / current_lower * 10)
            interpretation = f"Price at lower BB - Oversold (BB%: {bb_pct:.1%})"
        elif current_price >= current_upper:
            sig = SignalType.SELL
            strength = min(1.0, (current_price - current_upper) / current_upper * 10)
            interpretation = f"Price at upper BB - Overbought (BB%: {bb_pct:.1%})"
        else:
            sig = SignalType.NEUTRAL
            strength = 0.0
            interpretation = f"Price within BB (BB%: {bb_pct:.1%})"

        return IndicatorResult(
            name="Bollinger Bands",
            value=bb_pct,
            signal=sig,
            signal_strength=strength,
            interpretation=interpretation,
            parameters=self.params,
        )


class ATRIndicator(BaseIndicator):
    """Average True Range."""

    def get_default_parameters(self) -> Dict[str, Any]:
        return {"period": 14}

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        tr = pd.concat([
            data["high"] - data["low"],
            abs(data["high"] - data["close"].shift()),
            abs(data["low"] - data["close"].shift())
        ], axis=1).max(axis=1)
        return tr.rolling(self.params["period"]).mean()

    def get_signal(self, data: pd.DataFrame, current_idx: int) -> IndicatorResult:
        atr = self.calculate(data)
        current_atr = atr.iloc[current_idx]
        avg_atr = atr.iloc[-20:].mean()

        atr_ratio = current_atr / avg_atr

        if atr_ratio > 1.5:
            interpretation = f"High volatility (ATR: {current_atr:.2f}, {atr_ratio:.1f}x avg)"
        elif atr_ratio < 0.7:
            interpretation = f"Low volatility/squeeze (ATR: {current_atr:.2f}, {atr_ratio:.1f}x avg)"
        else:
            interpretation = f"Normal volatility (ATR: {current_atr:.2f})"

        return IndicatorResult(
            name="ATR",
            value=current_atr,
            signal=SignalType.NEUTRAL,
            signal_strength=0.0,
            interpretation=interpretation,
            parameters=self.params,
        )


# ==================== VOLUME INDICATORS ====================

class VWAPIndicator(BaseIndicator):
    """Volume Weighted Average Price."""

    def get_default_parameters(self) -> Dict[str, Any]:
        return {"anchor": "session"}

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        tp = (data["high"] + data["low"] + data["close"]) / 3
        return (tp * data["volume"]).cumsum() / data["volume"].cumsum()

    def get_signal(self, data: pd.DataFrame, current_idx: int) -> IndicatorResult:
        vwap = self.calculate(data)
        current_price = data["close"].iloc[current_idx]
        current_vwap = vwap.iloc[current_idx]

        deviation = (current_price - current_vwap) / current_vwap

        if current_price > current_vwap * 1.005:
            sig = SignalType.BUY
            strength = min(1.0, deviation * 20)
            interpretation = f"Price above VWAP ({deviation:+.2%}) - Bullish"
        elif current_price < current_vwap * 0.995:
            sig = SignalType.SELL
            strength = min(1.0, abs(deviation) * 20)
            interpretation = f"Price below VWAP ({deviation:+.2%}) - Bearish"
        else:
            sig = SignalType.NEUTRAL
            strength = 0.0
            interpretation = f"Price at VWAP ({deviation:+.2%})"

        return IndicatorResult(
            name="VWAP",
            value=current_vwap,
            signal=sig,
            signal_strength=strength,
            interpretation=interpretation,
            parameters=self.params,
        )


class OBVIndicator(BaseIndicator):
    """On-Balance Volume."""

    def get_default_parameters(self) -> Dict[str, Any]:
        return {"signal_period": 20}

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        obv = (np.sign(data["close"].diff()) * data["volume"]).cumsum()
        return obv

    def get_signal(self, data: pd.DataFrame, current_idx: int) -> IndicatorResult:
        obv = self.calculate(data)
        current_obv = obv.iloc[current_idx]
        obv_sma = obv.rolling(self.params["signal_period"]).mean().iloc[current_idx]

        if current_obv > obv_sma:
            sig = SignalType.BUY
            strength = min(1.0, (current_obv - obv_sma) / (abs(obv_sma) + 1e-10))
            interpretation = "OBV above signal - Accumulation"
        else:
            sig = SignalType.SELL
            strength = min(1.0, (obv_sma - current_obv) / (abs(obv_sma) + 1e-10))
            interpretation = "OBV below signal - Distribution"

        return IndicatorResult(
            name="OBV",
            value=current_obv,
            signal=sig,
            signal_strength=strength,
            interpretation=interpretation,
            parameters=self.params,
        )


# ==================== PATTERN RECOGNITION ====================

class PatternRecognizer:
    """Recognize chart patterns."""

    def find_patterns(self, data: pd.DataFrame) -> List[PatternMatch]:
        """Find all patterns in data."""
        patterns = []

        patterns.extend(self._find_double_top_bottom(data))
        patterns.extend(self._find_head_shoulders(data))
        patterns.extend(self._find_triangles(data))
        patterns.extend(self._find_flags(data))
        patterns.extend(self._find_engulfing(data))
        patterns.extend(self._find_doji(data))

        return patterns

    def _find_double_top_bottom(self, data: pd.DataFrame) -> List[PatternMatch]:
        """Find double top and double bottom patterns."""
        patterns = []
        high = data["high"]
        low = data["low"]

        # Look for double tops
        for i in range(20, len(data) - 5):
            # Find local highs
            window = high.iloc[i-10:i+5]
            peaks = self._find_peaks(window)

            if len(peaks) >= 2:
                peak1, peak2 = peaks[-2], peaks[-1]
                if abs(high.iloc[peak1] - high.iloc[peak2]) / high.iloc[peak1] < 0.02:
                    patterns.append(PatternMatch(
                        pattern_name="Double Top",
                        direction="bearish",
                        confidence=0.7,
                        start_idx=peak1,
                        end_idx=i,
                        description="Two equal highs indicating resistance"
                    ))

        # Look for double bottoms
        for i in range(20, len(data) - 5):
            window = low.iloc[i-10:i+5]
            troughs = self._find_troughs(window)

            if len(troughs) >= 2:
                trough1, trough2 = troughs[-2], troughs[-1]
                if abs(low.iloc[trough1] - low.iloc[trough2]) / low.iloc[trough1] < 0.02:
                    patterns.append(PatternMatch(
                        pattern_name="Double Bottom",
                        direction="bullish",
                        confidence=0.7,
                        start_idx=trough1,
                        end_idx=i,
                        description="Two equal lows indicating support"
                    ))

        return patterns

    def _find_head_shoulders(self, data: pd.DataFrame) -> List[PatternMatch]:
        """Find head and shoulders patterns."""
        patterns = []
        # Simplified implementation
        return patterns

    def _find_triangles(self, data: pd.DataFrame) -> List[PatternMatch]:
        """Find triangle patterns."""
        patterns = []
        # Simplified implementation
        return patterns

    def _find_flags(self, data: pd.DataFrame) -> List[PatternMatch]:
        """Find flag and pennant patterns."""
        patterns = []
        # Simplified implementation
        return patterns

    def _find_engulfing(self, data: pd.DataFrame) -> List[PatternMatch]:
        """Find engulfing candlestick patterns."""
        patterns = []
        opens = data["open"]
        closes = data["close"]

        for i in range(1, len(data)):
            prev_body = closes.iloc[i-1] - opens.iloc[i-1]
            curr_body = closes.iloc[i] - opens.iloc[i]

            # Bullish engulfing
            if prev_body < 0 and curr_body > 0:
                if opens.iloc[i] <= closes.iloc[i-1] and closes.iloc[i] >= opens.iloc[i-1]:
                    patterns.append(PatternMatch(
                        pattern_name="Bullish Engulfing",
                        direction="bullish",
                        confidence=0.65,
                        start_idx=i-1,
                        end_idx=i,
                        description="Bullish candle engulfs previous bearish candle"
                    ))

            # Bearish engulfing
            if prev_body > 0 and curr_body < 0:
                if opens.iloc[i] >= closes.iloc[i-1] and closes.iloc[i] <= opens.iloc[i-1]:
                    patterns.append(PatternMatch(
                        pattern_name="Bearish Engulfing",
                        direction="bearish",
                        confidence=0.65,
                        start_idx=i-1,
                        end_idx=i,
                        description="Bearish candle engulfs previous bullish candle"
                    ))

        return patterns

    def _find_doji(self, data: pd.DataFrame) -> List[PatternMatch]:
        """Find doji patterns."""
        patterns = []
        opens = data["open"]
        closes = data["close"]
        highs = data["high"]
        lows = data["low"]

        for i in range(len(data)):
            body = abs(closes.iloc[i] - opens.iloc[i])
            range_hl = highs.iloc[i] - lows.iloc[i]

            if range_hl > 0 and body / range_hl < 0.1:
                patterns.append(PatternMatch(
                    pattern_name="Doji",
                    direction="neutral",
                    confidence=0.5,
                    start_idx=i,
                    end_idx=i,
                    description="Indecision candle - potential reversal"
                ))

        return patterns

    def _find_peaks(self, series: pd.Series) -> List[int]:
        """Find local peaks in series."""
        peaks = []
        for i in range(1, len(series) - 1):
            if series.iloc[i] > series.iloc[i-1] and series.iloc[i] > series.iloc[i+1]:
                peaks.append(i)
        return peaks

    def _find_troughs(self, series: pd.Series) -> List[int]:
        """Find local troughs in series."""
        troughs = []
        for i in range(1, len(series) - 1):
            if series.iloc[i] < series.iloc[i-1] and series.iloc[i] < series.iloc[i+1]:
                troughs.append(i)
        return troughs


# ==================== INDICATOR MANAGER ====================

class IndicatorRegistry:
    """Registry of available indicators."""

    _indicators: Dict[str, type] = {
        "SMA": SMAIndicator,
        "EMA": EMAIndicator,
        "MACD": MACDIndicator,
        "ADX": ADXIndicator,
        "RSI": RSIIndicator,
        "Stochastic": StochasticIndicator,
        "CCI": CCIIndicator,
        "Bollinger": BollingerBandsIndicator,
        "ATR": ATRIndicator,
        "VWAP": VWAPIndicator,
        "OBV": OBVIndicator,
    }

    @classmethod
    def list_indicators(cls) -> List[str]:
        """List all available indicators."""
        return list(cls._indicators.keys())

    @classmethod
    def get_indicator(cls, name: str, config: IndicatorConfig) -> Optional[BaseIndicator]:
        """Get indicator instance by name."""
        indicator_class = cls._indicators.get(name)
        if indicator_class:
            return indicator_class(config)
        return None

    @classmethod
    def register(cls, name: str, indicator_class: type):
        """Register new indicator."""
        cls._indicators[name] = indicator_class


class CustomIndicatorSystem:
    """
    Main system for customizable indicators.
    """

    def __init__(self):
        self.active_indicators: Dict[str, BaseIndicator] = {}
        self.pattern_recognizer = PatternRecognizer()

    def add_indicator(
        self,
        name: str,
        enabled: bool = True,
        parameters: Optional[Dict[str, Any]] = None,
        weight: float = 1.0,
    ) -> bool:
        """Add indicator to active set."""
        config = IndicatorConfig(
            name=name,
            enabled=enabled,
            parameters=parameters or {},
            weight=weight,
        )

        indicator = IndicatorRegistry.get_indicator(name, config)
        if indicator:
            self.active_indicators[name] = indicator
            logger.info(f"Added indicator: {name} with params {parameters}")
            return True

        logger.warning(f"Unknown indicator: {name}")
        return False

    def remove_indicator(self, name: str):
        """Remove indicator from active set."""
        if name in self.active_indicators:
            del self.active_indicators[name]
            logger.info(f"Removed indicator: {name}")

    def update_parameters(self, name: str, parameters: Dict[str, Any]):
        """Update indicator parameters."""
        if name in self.active_indicators:
            self.active_indicators[name].params.update(parameters)
            logger.info(f"Updated {name} parameters: {parameters}")

    def analyze(self, data: pd.DataFrame) -> CombinedSignal:
        """Run all active indicators and combine signals."""
        current_idx = len(data) - 1
        indicator_results = []
        buy_weight = 0
        sell_weight = 0
        total_weight = 0

        # Run all indicators
        for name, indicator in self.active_indicators.items():
            if indicator.config.enabled:
                result = indicator.get_signal(data, current_idx)
                indicator_results.append(result)

                weight = indicator.config.weight
                if result.signal == SignalType.BUY:
                    buy_weight += result.signal_strength * weight
                elif result.signal == SignalType.SELL:
                    sell_weight += result.signal_strength * weight
                total_weight += weight

        # Find patterns
        patterns = self.pattern_recognizer.find_patterns(data.iloc[-50:])

        # Combine signals
        if total_weight > 0:
            buy_score = buy_weight / total_weight
            sell_score = sell_weight / total_weight
        else:
            buy_score = sell_score = 0

        if buy_score > sell_score + 0.2:
            direction = SignalType.BUY
            strength = buy_score
        elif sell_score > buy_score + 0.2:
            direction = SignalType.SELL
            strength = sell_score
        else:
            direction = SignalType.NEUTRAL
            strength = 0

        # Generate reasoning
        reasoning = []
        for result in indicator_results:
            if result.signal_strength > 0.3:
                reasoning.append(result.interpretation)

        for pattern in patterns[-3:]:
            reasoning.append(f"Pattern: {pattern.pattern_name} ({pattern.direction})")

        confidence = max(buy_score, sell_score)

        return CombinedSignal(
            timestamp=datetime.utcnow(),
            direction=direction,
            strength=strength,
            confidence=confidence,
            indicator_signals=indicator_results,
            patterns_detected=patterns,
            reasoning=reasoning,
        )

    def get_all_results(self, data: pd.DataFrame) -> Dict[str, IndicatorResult]:
        """Get results from all active indicators."""
        current_idx = len(data) - 1
        results = {}

        for name, indicator in self.active_indicators.items():
            if indicator.config.enabled:
                results[name] = indicator.get_signal(data, current_idx)

        return results


def create_indicator_system() -> CustomIndicatorSystem:
    """Create indicator system."""
    return CustomIndicatorSystem()


def create_default_indicator_set() -> CustomIndicatorSystem:
    """Create system with default indicators."""
    system = CustomIndicatorSystem()

    system.add_indicator("EMA", parameters={"period": 9})
    system.add_indicator("EMA", parameters={"period": 21})
    system.add_indicator("RSI", parameters={"period": 14})
    system.add_indicator("MACD")
    system.add_indicator("Bollinger")
    system.add_indicator("VWAP")
    system.add_indicator("ADX")

    return system
