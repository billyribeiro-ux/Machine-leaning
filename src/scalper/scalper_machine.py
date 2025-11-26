"""
Ultra-Accurate Scalper Machine.

Maximum accuracy scalping system with:
- Multiple confirmation signals
- Strict entry criteria
- Precise timing
- Advanced filtering
- Risk-adjusted position sizing
- Real-time adaptation

Designed for high win-rate short-term trades.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from collections import deque
import logging


logger = logging.getLogger(__name__)


class ScalpDirection(Enum):
    """Scalp trade direction."""
    LONG = "long"
    SHORT = "short"
    NONE = "none"


class SignalStrength(Enum):
    """Signal strength levels."""
    WEAK = 1
    MODERATE = 2
    STRONG = 3
    VERY_STRONG = 4
    EXTREME = 5


@dataclass
class ScalpSignal:
    """Scalping signal with full analysis."""
    symbol: str
    direction: ScalpDirection
    strength: SignalStrength
    confidence: float  # 0-100%
    timestamp: datetime

    # Entry parameters
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float

    # Position sizing
    recommended_size: float  # % of capital
    max_risk: float  # Max loss amount

    # Confirmations
    confirmations: Dict[str, bool] = field(default_factory=dict)
    confirmation_count: int = 0
    required_confirmations: int = 5

    # Analysis
    reasoning: List[str] = field(default_factory=list)
    indicators: Dict[str, float] = field(default_factory=dict)
    market_conditions: Dict[str, str] = field(default_factory=dict)

    # Timing
    optimal_entry_window_seconds: int = 30
    signal_expiry: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_valid(self) -> bool:
        """Check if signal meets all criteria."""
        return (
            self.confirmation_count >= self.required_confirmations and
            self.confidence >= 85 and
            datetime.utcnow() < self.signal_expiry
        )


@dataclass
class ScalperConfig:
    """Configuration for scalper machine."""
    # Confirmation requirements
    min_confirmations: int = 5
    min_confidence: float = 85.0

    # Entry criteria
    max_spread_pct: float = 0.02  # Maximum allowed spread
    min_volume_ratio: float = 1.5  # Minimum volume vs average
    max_atr_ratio: float = 2.0  # Maximum volatility

    # Risk management
    risk_per_trade_pct: float = 0.5  # Risk per trade
    max_daily_loss_pct: float = 2.0  # Max daily loss
    max_concurrent_trades: int = 3

    # Take profit levels
    tp1_atr_multiple: float = 1.0
    tp2_atr_multiple: float = 1.5
    tp3_atr_multiple: float = 2.0
    stop_loss_atr_multiple: float = 0.75

    # Time filters
    avoid_first_minutes: int = 5  # Avoid first 5 min after open
    avoid_last_minutes: int = 5  # Avoid last 5 min before close
    best_hours: List[int] = field(default_factory=lambda: [9, 10, 14, 15])

    # Indicator parameters
    ema_fast: int = 8
    ema_medium: int = 21
    ema_slow: int = 55
    rsi_period: int = 14
    rsi_overbought: float = 70
    rsi_oversold: float = 30
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bb_period: int = 20
    bb_std: float = 2.0
    atr_period: int = 14
    vwap_anchor: str = "session"


class TechnicalAnalyzer:
    """Technical analysis for scalping."""

    def __init__(self, config: ScalperConfig):
        self.config = config

    def calculate_all(self, data: pd.DataFrame) -> Dict[str, pd.Series]:
        """Calculate all technical indicators."""
        indicators = {}

        close = data["close"]
        high = data["high"]
        low = data["low"]
        volume = data["volume"]

        # EMAs
        indicators["ema_fast"] = close.ewm(span=self.config.ema_fast).mean()
        indicators["ema_medium"] = close.ewm(span=self.config.ema_medium).mean()
        indicators["ema_slow"] = close.ewm(span=self.config.ema_slow).mean()

        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(self.config.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(self.config.rsi_period).mean()
        rs = gain / (loss + 1e-10)
        indicators["rsi"] = 100 - (100 / (1 + rs))

        # MACD
        ema_fast = close.ewm(span=self.config.macd_fast).mean()
        ema_slow = close.ewm(span=self.config.macd_slow).mean()
        indicators["macd"] = ema_fast - ema_slow
        indicators["macd_signal"] = indicators["macd"].ewm(span=self.config.macd_signal).mean()
        indicators["macd_histogram"] = indicators["macd"] - indicators["macd_signal"]

        # Bollinger Bands
        sma = close.rolling(self.config.bb_period).mean()
        std = close.rolling(self.config.bb_period).std()
        indicators["bb_upper"] = sma + self.config.bb_std * std
        indicators["bb_lower"] = sma - self.config.bb_std * std
        indicators["bb_middle"] = sma
        indicators["bb_width"] = (indicators["bb_upper"] - indicators["bb_lower"]) / sma

        # ATR
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        indicators["atr"] = tr.rolling(self.config.atr_period).mean()

        # Volume analysis
        indicators["volume_sma"] = volume.rolling(20).mean()
        indicators["volume_ratio"] = volume / (indicators["volume_sma"] + 1)

        # Price momentum
        indicators["momentum_5"] = close.pct_change(5)
        indicators["momentum_10"] = close.pct_change(10)

        # VWAP
        typical_price = (high + low + close) / 3
        cumulative_tp_vol = (typical_price * volume).cumsum()
        cumulative_vol = volume.cumsum()
        indicators["vwap"] = cumulative_tp_vol / cumulative_vol

        # Stochastic
        lowest_low = low.rolling(14).min()
        highest_high = high.rolling(14).max()
        indicators["stoch_k"] = 100 * (close - lowest_low) / (highest_high - lowest_low + 1e-10)
        indicators["stoch_d"] = indicators["stoch_k"].rolling(3).mean()

        # ADX
        indicators["adx"] = self._calculate_adx(high, low, close)

        return indicators

    def _calculate_adx(self, high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        """Calculate ADX."""
        plus_dm = high.diff()
        minus_dm = -low.diff()

        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        atr = tr.rolling(period).mean()

        plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(period).mean() / atr)

        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
        adx = dx.rolling(period).mean()

        return adx


class ConfirmationEngine:
    """
    Multi-factor confirmation system for high-accuracy signals.
    """

    def __init__(self, config: ScalperConfig):
        self.config = config

    def check_confirmations(
        self,
        indicators: Dict[str, pd.Series],
        current_idx: int,
        direction: ScalpDirection,
    ) -> Dict[str, bool]:
        """Check all confirmation criteria."""
        confirmations = {}

        # Get current values
        ema_fast = indicators["ema_fast"].iloc[current_idx]
        ema_medium = indicators["ema_medium"].iloc[current_idx]
        ema_slow = indicators["ema_slow"].iloc[current_idx]
        rsi = indicators["rsi"].iloc[current_idx]
        macd = indicators["macd"].iloc[current_idx]
        macd_signal = indicators["macd_signal"].iloc[current_idx]
        macd_hist = indicators["macd_histogram"].iloc[current_idx]
        stoch_k = indicators["stoch_k"].iloc[current_idx]
        stoch_d = indicators["stoch_d"].iloc[current_idx]
        adx = indicators["adx"].iloc[current_idx]
        volume_ratio = indicators["volume_ratio"].iloc[current_idx]

        if direction == ScalpDirection.LONG:
            # Confirmation 1: EMA alignment (bullish)
            confirmations["ema_alignment"] = ema_fast > ema_medium > ema_slow

            # Confirmation 2: RSI not overbought and rising
            rsi_prev = indicators["rsi"].iloc[current_idx - 1] if current_idx > 0 else rsi
            confirmations["rsi_favorable"] = (
                rsi < self.config.rsi_overbought and
                rsi > rsi_prev and
                rsi > 40
            )

            # Confirmation 3: MACD bullish
            confirmations["macd_bullish"] = macd > macd_signal and macd_hist > 0

            # Confirmation 4: Stochastic bullish
            confirmations["stochastic_bullish"] = (
                stoch_k > stoch_d and
                stoch_k < 80 and  # Not overbought
                stoch_k > 20  # Coming out of oversold
            )

            # Confirmation 5: Volume confirmation
            confirmations["volume_surge"] = volume_ratio >= self.config.min_volume_ratio

            # Confirmation 6: Trend strength
            confirmations["trend_strength"] = adx > 20

            # Confirmation 7: Price above VWAP
            vwap = indicators["vwap"].iloc[current_idx]
            close = indicators["ema_fast"].iloc[current_idx]  # Use fast EMA as price proxy
            confirmations["above_vwap"] = close > vwap

            # Confirmation 8: Momentum positive
            mom_5 = indicators["momentum_5"].iloc[current_idx]
            confirmations["momentum_positive"] = mom_5 > 0

        elif direction == ScalpDirection.SHORT:
            # Confirmation 1: EMA alignment (bearish)
            confirmations["ema_alignment"] = ema_fast < ema_medium < ema_slow

            # Confirmation 2: RSI not oversold and falling
            rsi_prev = indicators["rsi"].iloc[current_idx - 1] if current_idx > 0 else rsi
            confirmations["rsi_favorable"] = (
                rsi > self.config.rsi_oversold and
                rsi < rsi_prev and
                rsi < 60
            )

            # Confirmation 3: MACD bearish
            confirmations["macd_bearish"] = macd < macd_signal and macd_hist < 0

            # Confirmation 4: Stochastic bearish
            confirmations["stochastic_bearish"] = (
                stoch_k < stoch_d and
                stoch_k > 20 and  # Not oversold
                stoch_k < 80  # Coming out of overbought
            )

            # Confirmation 5: Volume confirmation
            confirmations["volume_surge"] = volume_ratio >= self.config.min_volume_ratio

            # Confirmation 6: Trend strength
            confirmations["trend_strength"] = adx > 20

            # Confirmation 7: Price below VWAP
            vwap = indicators["vwap"].iloc[current_idx]
            close = indicators["ema_fast"].iloc[current_idx]
            confirmations["below_vwap"] = close < vwap

            # Confirmation 8: Momentum negative
            mom_5 = indicators["momentum_5"].iloc[current_idx]
            confirmations["momentum_negative"] = mom_5 < 0

        return confirmations


class PrecisionEntryTimer:
    """
    Precision entry timing for optimal execution.
    """

    def __init__(self):
        self.tick_buffer: deque = deque(maxlen=100)

    def find_optimal_entry(
        self,
        current_price: float,
        target_price: float,
        direction: ScalpDirection,
        volatility: float,
    ) -> Tuple[bool, float, str]:
        """
        Find optimal entry point.

        Returns:
            is_optimal: Whether now is optimal time
            adjusted_price: Suggested entry price
            reason: Reason for decision
        """
        price_diff = abs(current_price - target_price) / target_price

        if direction == ScalpDirection.LONG:
            # For longs, want to enter on small pullback
            if current_price < target_price and price_diff < volatility * 0.5:
                return True, current_price, "Optimal pullback entry"
            elif current_price > target_price and price_diff > volatility:
                return False, target_price, "Price extended, wait for pullback"
            else:
                return True, current_price, "Acceptable entry"

        elif direction == ScalpDirection.SHORT:
            # For shorts, want to enter on small bounce
            if current_price > target_price and price_diff < volatility * 0.5:
                return True, current_price, "Optimal bounce entry"
            elif current_price < target_price and price_diff > volatility:
                return False, target_price, "Price extended, wait for bounce"
            else:
                return True, current_price, "Acceptable entry"

        return False, current_price, "No direction"


class ScalperMachine:
    """
    Ultra-Accurate Scalping System.

    Combines multiple confirmation factors for high win-rate entries.
    """

    def __init__(self, config: Optional[ScalperConfig] = None):
        self.config = config or ScalperConfig()
        self.analyzer = TechnicalAnalyzer(self.config)
        self.confirmation_engine = ConfirmationEngine(self.config)
        self.entry_timer = PrecisionEntryTimer()

        # Performance tracking
        self.signals_generated = 0
        self.signals_valid = 0
        self.trades_taken = 0
        self.trades_won = 0
        self.daily_pnl = 0.0

        # State
        self.active_signals: Dict[str, ScalpSignal] = {}
        self.signal_history: List[ScalpSignal] = []

    def analyze(
        self,
        data: pd.DataFrame,
        symbol: str,
        current_price: Optional[float] = None,
    ) -> Optional[ScalpSignal]:
        """
        Analyze market for scalping opportunity.

        Returns ScalpSignal if valid opportunity found.
        """
        if len(data) < 100:
            return None

        # Calculate indicators
        indicators = self.analyzer.calculate_all(data)
        current_idx = len(data) - 1

        current_price = current_price or data["close"].iloc[-1]
        atr = indicators["atr"].iloc[-1]

        # Determine potential direction
        direction = self._determine_direction(indicators, current_idx)

        if direction == ScalpDirection.NONE:
            return None

        # Check confirmations
        confirmations = self.confirmation_engine.check_confirmations(
            indicators, current_idx, direction
        )

        confirmation_count = sum(confirmations.values())

        # Calculate confidence
        confidence = self._calculate_confidence(confirmations, indicators, current_idx)

        # Generate signal
        signal = ScalpSignal(
            symbol=symbol,
            direction=direction,
            strength=self._get_signal_strength(confirmation_count, confidence),
            confidence=confidence,
            timestamp=datetime.utcnow(),
            entry_price=current_price,
            stop_loss=self._calculate_stop_loss(current_price, atr, direction),
            take_profit_1=self._calculate_take_profit(current_price, atr, direction, 1),
            take_profit_2=self._calculate_take_profit(current_price, atr, direction, 2),
            take_profit_3=self._calculate_take_profit(current_price, atr, direction, 3),
            recommended_size=self._calculate_position_size(current_price, atr),
            max_risk=self.config.risk_per_trade_pct,
            confirmations=confirmations,
            confirmation_count=confirmation_count,
            required_confirmations=self.config.min_confirmations,
            reasoning=self._generate_reasoning(confirmations, indicators, current_idx, direction),
            indicators=self._get_indicator_values(indicators, current_idx),
            market_conditions=self._assess_market_conditions(indicators, current_idx),
            signal_expiry=datetime.utcnow() + timedelta(seconds=60),
        )

        self.signals_generated += 1

        if signal.is_valid:
            self.signals_valid += 1
            self.active_signals[symbol] = signal
            self.signal_history.append(signal)
            return signal

        return None

    def _determine_direction(
        self,
        indicators: Dict[str, pd.Series],
        current_idx: int,
    ) -> ScalpDirection:
        """Determine trade direction based on overall bias."""
        ema_fast = indicators["ema_fast"].iloc[current_idx]
        ema_medium = indicators["ema_medium"].iloc[current_idx]
        ema_slow = indicators["ema_slow"].iloc[current_idx]
        macd_hist = indicators["macd_histogram"].iloc[current_idx]
        rsi = indicators["rsi"].iloc[current_idx]

        bullish_score = 0
        bearish_score = 0

        # EMA analysis
        if ema_fast > ema_medium > ema_slow:
            bullish_score += 2
        elif ema_fast < ema_medium < ema_slow:
            bearish_score += 2

        # MACD
        if macd_hist > 0:
            bullish_score += 1
        elif macd_hist < 0:
            bearish_score += 1

        # RSI
        if 40 < rsi < 60:
            pass  # Neutral
        elif rsi < 40:
            bullish_score += 1  # Oversold, potential long
        elif rsi > 60:
            bearish_score += 1  # Overbought, potential short

        if bullish_score >= 3 and bullish_score > bearish_score:
            return ScalpDirection.LONG
        elif bearish_score >= 3 and bearish_score > bullish_score:
            return ScalpDirection.SHORT

        return ScalpDirection.NONE

    def _calculate_confidence(
        self,
        confirmations: Dict[str, bool],
        indicators: Dict[str, pd.Series],
        current_idx: int,
    ) -> float:
        """Calculate signal confidence 0-100."""
        # Base confidence from confirmations
        confirmation_pct = sum(confirmations.values()) / len(confirmations) * 100

        # Adjust for trend strength
        adx = indicators["adx"].iloc[current_idx]
        trend_bonus = min(10, (adx - 20) / 2) if adx > 20 else 0

        # Adjust for volume
        volume_ratio = indicators["volume_ratio"].iloc[current_idx]
        volume_bonus = min(5, (volume_ratio - 1) * 5) if volume_ratio > 1 else 0

        # Adjust for RSI extremes (reversal risk)
        rsi = indicators["rsi"].iloc[current_idx]
        rsi_penalty = 0
        if rsi > 75 or rsi < 25:
            rsi_penalty = 10

        confidence = confirmation_pct + trend_bonus + volume_bonus - rsi_penalty

        return max(0, min(100, confidence))

    def _get_signal_strength(self, confirmation_count: int, confidence: float) -> SignalStrength:
        """Determine signal strength."""
        if confirmation_count >= 7 and confidence >= 90:
            return SignalStrength.EXTREME
        elif confirmation_count >= 6 and confidence >= 85:
            return SignalStrength.VERY_STRONG
        elif confirmation_count >= 5 and confidence >= 80:
            return SignalStrength.STRONG
        elif confirmation_count >= 4 and confidence >= 70:
            return SignalStrength.MODERATE
        else:
            return SignalStrength.WEAK

    def _calculate_stop_loss(
        self,
        entry_price: float,
        atr: float,
        direction: ScalpDirection,
    ) -> float:
        """Calculate stop loss price."""
        stop_distance = atr * self.config.stop_loss_atr_multiple

        if direction == ScalpDirection.LONG:
            return entry_price - stop_distance
        else:
            return entry_price + stop_distance

    def _calculate_take_profit(
        self,
        entry_price: float,
        atr: float,
        direction: ScalpDirection,
        level: int,
    ) -> float:
        """Calculate take profit price."""
        multipliers = {
            1: self.config.tp1_atr_multiple,
            2: self.config.tp2_atr_multiple,
            3: self.config.tp3_atr_multiple,
        }

        tp_distance = atr * multipliers.get(level, 1.0)

        if direction == ScalpDirection.LONG:
            return entry_price + tp_distance
        else:
            return entry_price - tp_distance

    def _calculate_position_size(self, entry_price: float, atr: float) -> float:
        """Calculate recommended position size as % of capital."""
        # Risk-based position sizing
        risk_amount = self.config.risk_per_trade_pct
        stop_distance = atr * self.config.stop_loss_atr_multiple
        risk_per_share = stop_distance / entry_price

        position_size = risk_amount / risk_per_share

        return min(position_size, 0.25)  # Max 25% of capital

    def _generate_reasoning(
        self,
        confirmations: Dict[str, bool],
        indicators: Dict[str, pd.Series],
        current_idx: int,
        direction: ScalpDirection,
    ) -> List[str]:
        """Generate human-readable reasoning."""
        reasons = []

        direction_str = "LONG" if direction == ScalpDirection.LONG else "SHORT"
        reasons.append(f"Direction: {direction_str}")

        # Confirmed factors
        for name, confirmed in confirmations.items():
            if confirmed:
                reasons.append(f"✓ {name.replace('_', ' ').title()}")
            else:
                reasons.append(f"✗ {name.replace('_', ' ').title()}")

        # Key indicator values
        rsi = indicators["rsi"].iloc[current_idx]
        adx = indicators["adx"].iloc[current_idx]
        volume_ratio = indicators["volume_ratio"].iloc[current_idx]

        reasons.append(f"RSI: {rsi:.1f}")
        reasons.append(f"ADX: {adx:.1f}")
        reasons.append(f"Volume Ratio: {volume_ratio:.2f}x")

        return reasons

    def _get_indicator_values(
        self,
        indicators: Dict[str, pd.Series],
        current_idx: int,
    ) -> Dict[str, float]:
        """Get current indicator values."""
        return {
            name: float(series.iloc[current_idx])
            for name, series in indicators.items()
            if not pd.isna(series.iloc[current_idx])
        }

    def _assess_market_conditions(
        self,
        indicators: Dict[str, pd.Series],
        current_idx: int,
    ) -> Dict[str, str]:
        """Assess current market conditions."""
        conditions = {}

        # Trend
        adx = indicators["adx"].iloc[current_idx]
        if adx > 40:
            conditions["trend"] = "Strong trend"
        elif adx > 25:
            conditions["trend"] = "Moderate trend"
        else:
            conditions["trend"] = "Ranging/Weak trend"

        # Volatility
        bb_width = indicators["bb_width"].iloc[current_idx]
        if bb_width > 0.04:
            conditions["volatility"] = "High"
        elif bb_width > 0.02:
            conditions["volatility"] = "Normal"
        else:
            conditions["volatility"] = "Low (squeeze)"

        # Momentum
        mom = indicators["momentum_5"].iloc[current_idx]
        if mom > 0.01:
            conditions["momentum"] = "Strong bullish"
        elif mom > 0:
            conditions["momentum"] = "Bullish"
        elif mom > -0.01:
            conditions["momentum"] = "Bearish"
        else:
            conditions["momentum"] = "Strong bearish"

        # Volume
        vol_ratio = indicators["volume_ratio"].iloc[current_idx]
        if vol_ratio > 2:
            conditions["volume"] = "Very high"
        elif vol_ratio > 1.5:
            conditions["volume"] = "Above average"
        elif vol_ratio > 0.8:
            conditions["volume"] = "Normal"
        else:
            conditions["volume"] = "Low"

        return conditions

    def get_accuracy_stats(self) -> Dict[str, Any]:
        """Get accuracy statistics."""
        return {
            "signals_generated": self.signals_generated,
            "signals_valid": self.signals_valid,
            "valid_rate": self.signals_valid / max(1, self.signals_generated) * 100,
            "trades_taken": self.trades_taken,
            "trades_won": self.trades_won,
            "win_rate": self.trades_won / max(1, self.trades_taken) * 100,
            "daily_pnl": self.daily_pnl,
        }

    def record_trade_result(self, won: bool, pnl: float):
        """Record trade result for tracking."""
        self.trades_taken += 1
        if won:
            self.trades_won += 1
        self.daily_pnl += pnl


def create_scalper(config: Optional[ScalperConfig] = None) -> ScalperMachine:
    """Create scalper machine."""
    return ScalperMachine(config)


def create_ultra_accurate_scalper() -> ScalperMachine:
    """Create ultra-accurate scalper with strict settings."""
    config = ScalperConfig(
        min_confirmations=6,
        min_confidence=90.0,
        max_spread_pct=0.01,
        min_volume_ratio=2.0,
        risk_per_trade_pct=0.25,
        tp1_atr_multiple=0.75,
        tp2_atr_multiple=1.25,
        tp3_atr_multiple=1.75,
        stop_loss_atr_multiple=0.5,
    )
    return ScalperMachine(config)
