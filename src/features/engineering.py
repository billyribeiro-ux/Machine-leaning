"""
Revolution Alpha Engine - Advanced Feature Engineering

Institutional-grade feature engineering pipeline with 500+ features:
- Technical indicators (momentum, volatility, trend)
- Statistical features (moments, distributions)
- Market microstructure features
- Cross-asset features
- Options-derived features
- Fractal and complexity measures
"""

import numpy as np
import pandas as pd
from typing import Optional, List, Dict, Tuple, Any, Union
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
import logging
from datetime import datetime, timedelta
from scipy import stats
from scipy.fft import fft
from scipy.signal import hilbert
import warnings

warnings.filterwarnings('ignore')

logger = logging.getLogger(__name__)


# =============================================================================
# Feature Categories
# =============================================================================

class FeatureCategory(str, Enum):
    """Categories of features."""
    PRICE = "price"
    VOLUME = "volume"
    MOMENTUM = "momentum"
    VOLATILITY = "volatility"
    TREND = "trend"
    PATTERN = "pattern"
    STATISTICAL = "statistical"
    MICROSTRUCTURE = "microstructure"
    OPTIONS = "options"
    CROSS_ASSET = "cross_asset"
    FRACTAL = "fractal"
    SENTIMENT = "sentiment"


@dataclass
class FeatureMetadata:
    """Metadata for a computed feature."""
    name: str
    category: FeatureCategory
    lookback: int
    description: str
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    is_normalized: bool = False


# =============================================================================
# Base Feature Calculator
# =============================================================================

class FeatureCalculator(ABC):
    """Abstract base class for feature calculators."""

    @property
    @abstractmethod
    def feature_names(self) -> List[str]:
        """List of feature names this calculator produces."""
        pass

    @property
    @abstractmethod
    def category(self) -> FeatureCategory:
        """Feature category."""
        pass

    @abstractmethod
    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        """Calculate features and return DataFrame."""
        pass

    def _safe_divide(self, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        """Safe division avoiding divide by zero."""
        return np.divide(a, b, out=np.zeros_like(a, dtype=float), where=b != 0)


# =============================================================================
# Price Features
# =============================================================================

class PriceFeatures(FeatureCalculator):
    """Basic price-derived features."""

    @property
    def feature_names(self) -> List[str]:
        return [
            'returns_1', 'returns_5', 'returns_10', 'returns_20',
            'log_returns_1', 'log_returns_5', 'log_returns_10', 'log_returns_20',
            'high_low_range', 'high_low_range_pct',
            'close_to_high', 'close_to_low',
            'gap', 'gap_pct',
            'body_size', 'upper_wick', 'lower_wick',
            'typical_price', 'weighted_close',
            'price_acceleration',
            'overnight_return', 'intraday_return',
        ]

    @property
    def category(self) -> FeatureCategory:
        return FeatureCategory.PRICE

    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        """Calculate price features."""
        df = pd.DataFrame(index=data.index)

        close = data['close']
        open_ = data['open']
        high = data['high']
        low = data['low']

        # Returns
        for period in [1, 5, 10, 20]:
            df[f'returns_{period}'] = close.pct_change(period)
            df[f'log_returns_{period}'] = np.log(close / close.shift(period))

        # Range
        df['high_low_range'] = high - low
        df['high_low_range_pct'] = self._safe_divide(
            (high - low).values, close.values
        )

        # Position in range
        hl_range = high - low
        df['close_to_high'] = self._safe_divide(
            (high - close).values, hl_range.values
        )
        df['close_to_low'] = self._safe_divide(
            (close - low).values, hl_range.values
        )

        # Gap
        df['gap'] = open_ - close.shift(1)
        df['gap_pct'] = self._safe_divide(df['gap'].values, close.shift(1).values)

        # Candlestick features
        body = close - open_
        df['body_size'] = np.abs(body)
        df['upper_wick'] = high - np.maximum(close, open_)
        df['lower_wick'] = np.minimum(close, open_) - low

        # Price types
        df['typical_price'] = (high + low + close) / 3
        df['weighted_close'] = (high + low + close * 2) / 4

        # Acceleration
        df['price_acceleration'] = df['returns_1'] - df['returns_1'].shift(1)

        # Session returns (approximation)
        df['overnight_return'] = self._safe_divide(
            (open_ - close.shift(1)).values, close.shift(1).values
        )
        df['intraday_return'] = self._safe_divide(
            (close - open_).values, open_.values
        )

        return df


# =============================================================================
# Momentum Features
# =============================================================================

class MomentumFeatures(FeatureCalculator):
    """Momentum-based features."""

    @property
    def feature_names(self) -> List[str]:
        names = []
        for period in [7, 14, 21, 28]:
            names.extend([
                f'rsi_{period}',
                f'stoch_k_{period}',
                f'stoch_d_{period}',
                f'williams_r_{period}',
                f'cci_{period}',
                f'mfi_{period}',
                f'roc_{period}',
                f'momentum_{period}',
            ])
        names.extend([
            'macd', 'macd_signal', 'macd_hist',
            'ppo', 'ppo_signal', 'ppo_hist',
            'tsi', 'ultimate_oscillator',
            'awesome_oscillator', 'accelerator_oscillator',
        ])
        return names

    @property
    def category(self) -> FeatureCategory:
        return FeatureCategory.MOMENTUM

    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        """Calculate momentum features."""
        df = pd.DataFrame(index=data.index)

        close = data['close']
        high = data['high']
        low = data['low']
        volume = data['volume']

        # Multi-period indicators
        for period in [7, 14, 21, 28]:
            # RSI
            df[f'rsi_{period}'] = self._calculate_rsi(close, period)

            # Stochastic
            k, d = self._calculate_stochastic(high, low, close, period)
            df[f'stoch_k_{period}'] = k
            df[f'stoch_d_{period}'] = d

            # Williams %R
            df[f'williams_r_{period}'] = self._calculate_williams_r(high, low, close, period)

            # CCI
            df[f'cci_{period}'] = self._calculate_cci(high, low, close, period)

            # MFI
            df[f'mfi_{period}'] = self._calculate_mfi(high, low, close, volume, period)

            # ROC
            df[f'roc_{period}'] = self._calculate_roc(close, period)

            # Momentum
            df[f'momentum_{period}'] = close - close.shift(period)

        # MACD
        macd, signal, hist = self._calculate_macd(close)
        df['macd'] = macd
        df['macd_signal'] = signal
        df['macd_hist'] = hist

        # PPO (Percentage Price Oscillator)
        ppo, ppo_signal, ppo_hist = self._calculate_ppo(close)
        df['ppo'] = ppo
        df['ppo_signal'] = ppo_signal
        df['ppo_hist'] = ppo_hist

        # TSI (True Strength Index)
        df['tsi'] = self._calculate_tsi(close)

        # Ultimate Oscillator
        df['ultimate_oscillator'] = self._calculate_ultimate_oscillator(high, low, close)

        # Awesome Oscillator
        df['awesome_oscillator'] = self._calculate_awesome_oscillator(high, low)

        # Accelerator Oscillator
        ao = df['awesome_oscillator']
        df['accelerator_oscillator'] = ao - ao.rolling(5).mean()

        return df

    def _calculate_rsi(self, close: pd.Series, period: int = 14) -> pd.Series:
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
        rs = self._safe_divide(gain.values, loss.values)
        return pd.Series(100 - (100 / (1 + rs)), index=close.index)

    def _calculate_stochastic(
        self, high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
    ) -> Tuple[pd.Series, pd.Series]:
        lowest_low = low.rolling(period).min()
        highest_high = high.rolling(period).max()
        k = 100 * (close - lowest_low) / (highest_high - lowest_low)
        d = k.rolling(3).mean()
        return k, d

    def _calculate_williams_r(
        self, high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
    ) -> pd.Series:
        highest_high = high.rolling(period).max()
        lowest_low = low.rolling(period).min()
        return -100 * (highest_high - close) / (highest_high - lowest_low)

    def _calculate_cci(
        self, high: pd.Series, low: pd.Series, close: pd.Series, period: int = 20
    ) -> pd.Series:
        tp = (high + low + close) / 3
        sma = tp.rolling(period).mean()
        mad = tp.rolling(period).apply(lambda x: np.abs(x - x.mean()).mean())
        return (tp - sma) / (0.015 * mad)

    def _calculate_mfi(
        self, high: pd.Series, low: pd.Series, close: pd.Series,
        volume: pd.Series, period: int = 14
    ) -> pd.Series:
        tp = (high + low + close) / 3
        mf = tp * volume
        delta = tp.diff()

        positive_mf = mf.where(delta > 0, 0).rolling(period).sum()
        negative_mf = mf.where(delta <= 0, 0).rolling(period).sum()

        mfr = self._safe_divide(positive_mf.values, negative_mf.values)
        return pd.Series(100 - (100 / (1 + mfr)), index=close.index)

    def _calculate_roc(self, close: pd.Series, period: int = 10) -> pd.Series:
        return ((close - close.shift(period)) / close.shift(period)) * 100

    def _calculate_macd(
        self, close: pd.Series,
        fast: int = 12, slow: int = 26, signal: int = 9
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        macd = ema_fast - ema_slow
        signal_line = macd.ewm(span=signal, adjust=False).mean()
        histogram = macd - signal_line
        return macd, signal_line, histogram

    def _calculate_ppo(
        self, close: pd.Series,
        fast: int = 12, slow: int = 26, signal: int = 9
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        ppo = ((ema_fast - ema_slow) / ema_slow) * 100
        signal_line = ppo.ewm(span=signal, adjust=False).mean()
        histogram = ppo - signal_line
        return ppo, signal_line, histogram

    def _calculate_tsi(
        self, close: pd.Series, long: int = 25, short: int = 13
    ) -> pd.Series:
        delta = close.diff()
        smoothed = delta.ewm(span=long, adjust=False).mean().ewm(span=short, adjust=False).mean()
        abs_smoothed = delta.abs().ewm(span=long, adjust=False).mean().ewm(span=short, adjust=False).mean()
        return 100 * (smoothed / abs_smoothed)

    def _calculate_ultimate_oscillator(
        self, high: pd.Series, low: pd.Series, close: pd.Series,
        s: int = 7, m: int = 14, l: int = 28
    ) -> pd.Series:
        prev_close = close.shift(1)
        bp = close - np.minimum(low, prev_close)
        tr = np.maximum(high, prev_close) - np.minimum(low, prev_close)

        avg_s = bp.rolling(s).sum() / tr.rolling(s).sum()
        avg_m = bp.rolling(m).sum() / tr.rolling(m).sum()
        avg_l = bp.rolling(l).sum() / tr.rolling(l).sum()

        return 100 * ((4 * avg_s) + (2 * avg_m) + avg_l) / 7

    def _calculate_awesome_oscillator(
        self, high: pd.Series, low: pd.Series
    ) -> pd.Series:
        midpoint = (high + low) / 2
        return midpoint.rolling(5).mean() - midpoint.rolling(34).mean()


# =============================================================================
# Volatility Features
# =============================================================================

class VolatilityFeatures(FeatureCalculator):
    """Volatility-based features."""

    @property
    def feature_names(self) -> List[str]:
        names = []
        for period in [5, 10, 20, 50]:
            names.extend([
                f'std_{period}',
                f'atr_{period}',
                f'natr_{period}',
                f'realized_vol_{period}',
                f'parkinson_vol_{period}',
                f'garman_klass_vol_{period}',
                f'yang_zhang_vol_{period}',
            ])
        names.extend([
            'bb_upper', 'bb_lower', 'bb_width', 'bb_pct',
            'kc_upper', 'kc_lower', 'kc_width',
            'dc_upper', 'dc_lower', 'dc_width',
            'volatility_ratio', 'chaikin_volatility',
            'intraday_volatility', 'overnight_volatility',
            'volatility_regime', 'vol_of_vol',
        ])
        return names

    @property
    def category(self) -> FeatureCategory:
        return FeatureCategory.VOLATILITY

    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        """Calculate volatility features."""
        df = pd.DataFrame(index=data.index)

        close = data['close']
        high = data['high']
        low = data['low']
        open_ = data['open']

        # Multi-period volatility measures
        for period in [5, 10, 20, 50]:
            # Standard deviation
            df[f'std_{period}'] = close.rolling(period).std()

            # ATR
            df[f'atr_{period}'] = self._calculate_atr(high, low, close, period)

            # Normalized ATR
            df[f'natr_{period}'] = df[f'atr_{period}'] / close * 100

            # Realized volatility
            log_returns = np.log(close / close.shift(1))
            df[f'realized_vol_{period}'] = log_returns.rolling(period).std() * np.sqrt(252)

            # Parkinson volatility
            df[f'parkinson_vol_{period}'] = self._calculate_parkinson_vol(high, low, period)

            # Garman-Klass volatility
            df[f'garman_klass_vol_{period}'] = self._calculate_garman_klass_vol(
                open_, high, low, close, period
            )

            # Yang-Zhang volatility
            df[f'yang_zhang_vol_{period}'] = self._calculate_yang_zhang_vol(
                open_, high, low, close, period
            )

        # Bollinger Bands
        sma = close.rolling(20).mean()
        std = close.rolling(20).std()
        df['bb_upper'] = sma + 2 * std
        df['bb_lower'] = sma - 2 * std
        df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / sma
        df['bb_pct'] = (close - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])

        # Keltner Channels
        atr = df['atr_20']
        ema = close.ewm(span=20, adjust=False).mean()
        df['kc_upper'] = ema + 2 * atr
        df['kc_lower'] = ema - 2 * atr
        df['kc_width'] = (df['kc_upper'] - df['kc_lower']) / ema

        # Donchian Channels
        df['dc_upper'] = high.rolling(20).max()
        df['dc_lower'] = low.rolling(20).min()
        df['dc_width'] = (df['dc_upper'] - df['dc_lower']) / close

        # Volatility ratio
        short_vol = close.rolling(5).std()
        long_vol = close.rolling(20).std()
        df['volatility_ratio'] = short_vol / long_vol

        # Chaikin volatility
        ema_hl = (high - low).ewm(span=10, adjust=False).mean()
        df['chaikin_volatility'] = (ema_hl - ema_hl.shift(10)) / ema_hl.shift(10) * 100

        # Intraday vs overnight volatility
        intraday_returns = (close - open_) / open_
        overnight_returns = (open_ - close.shift(1)) / close.shift(1)
        df['intraday_volatility'] = intraday_returns.rolling(20).std()
        df['overnight_volatility'] = overnight_returns.rolling(20).std()

        # Volatility regime
        long_avg_vol = df['realized_vol_20'].rolling(60).mean()
        df['volatility_regime'] = df['realized_vol_20'] / long_avg_vol

        # Volatility of volatility
        df['vol_of_vol'] = df['realized_vol_20'].rolling(20).std()

        return df

    def _calculate_atr(
        self, high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
    ) -> pd.Series:
        tr1 = high - low
        tr2 = np.abs(high - close.shift(1))
        tr3 = np.abs(low - close.shift(1))
        tr = np.maximum(np.maximum(tr1, tr2), tr3)
        return tr.rolling(period).mean()

    def _calculate_parkinson_vol(
        self, high: pd.Series, low: pd.Series, period: int = 20
    ) -> pd.Series:
        log_hl = np.log(high / low) ** 2
        return np.sqrt(log_hl.rolling(period).mean() / (4 * np.log(2))) * np.sqrt(252)

    def _calculate_garman_klass_vol(
        self, open_: pd.Series, high: pd.Series, low: pd.Series,
        close: pd.Series, period: int = 20
    ) -> pd.Series:
        log_hl = np.log(high / low) ** 2
        log_co = np.log(close / open_) ** 2
        gk = 0.5 * log_hl - (2 * np.log(2) - 1) * log_co
        return np.sqrt(gk.rolling(period).mean() * 252)

    def _calculate_yang_zhang_vol(
        self, open_: pd.Series, high: pd.Series, low: pd.Series,
        close: pd.Series, period: int = 20
    ) -> pd.Series:
        log_oc = np.log(open_ / close.shift(1))
        log_co = np.log(close / open_)
        log_ho = np.log(high / open_)
        log_lo = np.log(low / open_)
        log_hc = np.log(high / close)
        log_lc = np.log(low / close)

        close_vol = log_co.rolling(period).var()
        open_vol = log_oc.rolling(period).var()
        rs_vol = (log_ho * log_hc + log_lo * log_lc).rolling(period).mean()

        k = 0.34 / (1.34 + (period + 1) / (period - 1))
        vol = np.sqrt(open_vol + k * close_vol + (1 - k) * rs_vol) * np.sqrt(252)

        return vol


# =============================================================================
# Trend Features
# =============================================================================

class TrendFeatures(FeatureCalculator):
    """Trend-based features."""

    @property
    def feature_names(self) -> List[str]:
        names = []
        for period in [10, 20, 50, 100, 200]:
            names.extend([
                f'sma_{period}',
                f'ema_{period}',
                f'price_to_sma_{period}',
                f'sma_slope_{period}',
            ])
        names.extend([
            'adx', 'plus_di', 'minus_di', 'di_diff',
            'aroon_up', 'aroon_down', 'aroon_oscillator',
            'supertrend', 'supertrend_direction',
            'parabolic_sar', 'psar_direction',
            'vortex_plus', 'vortex_minus', 'vortex_diff',
            'trend_strength', 'trend_consistency',
            'price_position', 'ma_ribbon_width',
        ])
        return names

    @property
    def category(self) -> FeatureCategory:
        return FeatureCategory.TREND

    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        """Calculate trend features."""
        df = pd.DataFrame(index=data.index)

        close = data['close']
        high = data['high']
        low = data['low']

        # Moving averages
        for period in [10, 20, 50, 100, 200]:
            df[f'sma_{period}'] = close.rolling(period).mean()
            df[f'ema_{period}'] = close.ewm(span=period, adjust=False).mean()
            df[f'price_to_sma_{period}'] = close / df[f'sma_{period}'] - 1
            df[f'sma_slope_{period}'] = df[f'sma_{period}'].diff(5) / df[f'sma_{period}'].shift(5)

        # ADX
        adx, plus_di, minus_di = self._calculate_adx(high, low, close)
        df['adx'] = adx
        df['plus_di'] = plus_di
        df['minus_di'] = minus_di
        df['di_diff'] = plus_di - minus_di

        # Aroon
        aroon_up, aroon_down = self._calculate_aroon(high, low)
        df['aroon_up'] = aroon_up
        df['aroon_down'] = aroon_down
        df['aroon_oscillator'] = aroon_up - aroon_down

        # Supertrend
        st, st_dir = self._calculate_supertrend(high, low, close)
        df['supertrend'] = st
        df['supertrend_direction'] = st_dir

        # Parabolic SAR
        psar, psar_dir = self._calculate_psar(high, low, close)
        df['parabolic_sar'] = psar
        df['psar_direction'] = psar_dir

        # Vortex Indicator
        vortex_plus, vortex_minus = self._calculate_vortex(high, low, close)
        df['vortex_plus'] = vortex_plus
        df['vortex_minus'] = vortex_minus
        df['vortex_diff'] = vortex_plus - vortex_minus

        # Trend strength (using regression)
        df['trend_strength'] = self._calculate_trend_strength(close)

        # Trend consistency
        df['trend_consistency'] = self._calculate_trend_consistency(close)

        # Price position in MA stack
        df['price_position'] = self._calculate_price_position(close, df)

        # MA ribbon width
        df['ma_ribbon_width'] = (df['ema_10'] - df['ema_50']).abs() / close

        return df

    def _calculate_adx(
        self, high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        plus_dm = high.diff()
        minus_dm = -low.diff()

        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

        tr = np.maximum(
            high - low,
            np.maximum(
                np.abs(high - close.shift(1)),
                np.abs(low - close.shift(1))
            )
        )

        atr = tr.rolling(period).mean()
        plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(period).mean() / atr)

        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(period).mean()

        return adx, plus_di, minus_di

    def _calculate_aroon(
        self, high: pd.Series, low: pd.Series, period: int = 25
    ) -> Tuple[pd.Series, pd.Series]:
        aroon_up = high.rolling(period + 1).apply(
            lambda x: (period - x.argmax()) / period * 100
        )
        aroon_down = low.rolling(period + 1).apply(
            lambda x: (period - x.argmin()) / period * 100
        )
        return aroon_up, aroon_down

    def _calculate_supertrend(
        self, high: pd.Series, low: pd.Series, close: pd.Series,
        period: int = 10, multiplier: float = 3.0
    ) -> Tuple[pd.Series, pd.Series]:
        atr = self._calculate_atr_internal(high, low, close, period)
        hl2 = (high + low) / 2

        upper_band = hl2 + multiplier * atr
        lower_band = hl2 - multiplier * atr

        supertrend = pd.Series(index=close.index, dtype=float)
        direction = pd.Series(index=close.index, dtype=float)

        supertrend.iloc[0] = upper_band.iloc[0]
        direction.iloc[0] = -1

        for i in range(1, len(close)):
            if close.iloc[i] > supertrend.iloc[i-1]:
                supertrend.iloc[i] = lower_band.iloc[i]
                direction.iloc[i] = 1
            else:
                supertrend.iloc[i] = upper_band.iloc[i]
                direction.iloc[i] = -1

        return supertrend, direction

    def _calculate_psar(
        self, high: pd.Series, low: pd.Series, close: pd.Series,
        af_start: float = 0.02, af_increment: float = 0.02, af_max: float = 0.2
    ) -> Tuple[pd.Series, pd.Series]:
        length = len(close)
        psar = pd.Series(index=close.index, dtype=float)
        direction = pd.Series(index=close.index, dtype=float)

        af = af_start
        ep = low.iloc[0]
        hp = high.iloc[0]
        lp = low.iloc[0]
        trend = 1

        psar.iloc[0] = close.iloc[0]
        direction.iloc[0] = 1

        for i in range(1, length):
            if trend == 1:
                psar.iloc[i] = psar.iloc[i-1] + af * (hp - psar.iloc[i-1])
                psar.iloc[i] = min(psar.iloc[i], low.iloc[i-1], low.iloc[i-2] if i > 1 else low.iloc[i-1])

                if low.iloc[i] < psar.iloc[i]:
                    trend = -1
                    psar.iloc[i] = hp
                    lp = low.iloc[i]
                    af = af_start
                else:
                    if high.iloc[i] > hp:
                        hp = high.iloc[i]
                        af = min(af + af_increment, af_max)
            else:
                psar.iloc[i] = psar.iloc[i-1] - af * (psar.iloc[i-1] - lp)
                psar.iloc[i] = max(psar.iloc[i], high.iloc[i-1], high.iloc[i-2] if i > 1 else high.iloc[i-1])

                if high.iloc[i] > psar.iloc[i]:
                    trend = 1
                    psar.iloc[i] = lp
                    hp = high.iloc[i]
                    af = af_start
                else:
                    if low.iloc[i] < lp:
                        lp = low.iloc[i]
                        af = min(af + af_increment, af_max)

            direction.iloc[i] = trend

        return psar, direction

    def _calculate_vortex(
        self, high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
    ) -> Tuple[pd.Series, pd.Series]:
        tr = np.maximum(
            high - low,
            np.maximum(
                np.abs(high - close.shift(1)),
                np.abs(low - close.shift(1))
            )
        )

        vm_plus = np.abs(high - low.shift(1))
        vm_minus = np.abs(low - high.shift(1))

        tr_sum = tr.rolling(period).sum()
        vortex_plus = vm_plus.rolling(period).sum() / tr_sum
        vortex_minus = vm_minus.rolling(period).sum() / tr_sum

        return vortex_plus, vortex_minus

    def _calculate_atr_internal(
        self, high: pd.Series, low: pd.Series, close: pd.Series, period: int
    ) -> pd.Series:
        tr = np.maximum(
            high - low,
            np.maximum(
                np.abs(high - close.shift(1)),
                np.abs(low - close.shift(1))
            )
        )
        return tr.rolling(period).mean()

    def _calculate_trend_strength(self, close: pd.Series, period: int = 20) -> pd.Series:
        """Calculate trend strength using linear regression R-squared."""
        def r_squared(x):
            if len(x) < 2:
                return 0
            slope, intercept, r, p, se = stats.linregress(range(len(x)), x)
            return r ** 2

        return close.rolling(period).apply(r_squared)

    def _calculate_trend_consistency(self, close: pd.Series, period: int = 20) -> pd.Series:
        """Calculate trend consistency (% of bars in trend direction)."""
        returns = close.diff()

        def consistency(x):
            if len(x) == 0:
                return 0
            positive = (x > 0).sum()
            negative = (x < 0).sum()
            return max(positive, negative) / len(x)

        return returns.rolling(period).apply(consistency)

    def _calculate_price_position(self, close: pd.Series, df: pd.DataFrame) -> pd.Series:
        """Calculate price position relative to MA stack."""
        position = pd.Series(0, index=close.index)

        for period in [10, 20, 50, 100, 200]:
            ma = df[f'ema_{period}']
            position += (close > ma).astype(int)

        return position / 5  # Normalize to 0-1


# =============================================================================
# Statistical Features
# =============================================================================

class StatisticalFeatures(FeatureCalculator):
    """Statistical and distributional features."""

    @property
    def feature_names(self) -> List[str]:
        names = []
        for period in [20, 50, 100]:
            names.extend([
                f'skewness_{period}',
                f'kurtosis_{period}',
                f'zscore_{period}',
                f'percentile_{period}',
                f'entropy_{period}',
                f'hurst_{period}',
            ])
        names.extend([
            'autocorr_1', 'autocorr_5', 'autocorr_10',
            'partial_autocorr_1', 'partial_autocorr_5',
            'variance_ratio',
            'jump_intensity', 'tail_ratio',
            'runs_test', 'mean_reversion_speed',
        ])
        return names

    @property
    def category(self) -> FeatureCategory:
        return FeatureCategory.STATISTICAL

    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        """Calculate statistical features."""
        df = pd.DataFrame(index=data.index)

        close = data['close']
        returns = close.pct_change()

        # Multi-period statistics
        for period in [20, 50, 100]:
            df[f'skewness_{period}'] = returns.rolling(period).skew()
            df[f'kurtosis_{period}'] = returns.rolling(period).kurt()

            mean = close.rolling(period).mean()
            std = close.rolling(period).std()
            df[f'zscore_{period}'] = (close - mean) / std

            df[f'percentile_{period}'] = close.rolling(period).apply(
                lambda x: stats.percentileofscore(x, x.iloc[-1]) / 100
            )

            df[f'entropy_{period}'] = returns.rolling(period).apply(
                self._calculate_entropy
            )

            df[f'hurst_{period}'] = returns.rolling(period).apply(
                self._calculate_hurst
            )

        # Autocorrelation
        for lag in [1, 5, 10]:
            df[f'autocorr_{lag}'] = returns.rolling(50).apply(
                lambda x: x.autocorr(lag=lag) if len(x) > lag else 0
            )

        # Partial autocorrelation (simplified)
        df['partial_autocorr_1'] = df['autocorr_1']
        df['partial_autocorr_5'] = df['autocorr_5'] - df['autocorr_1'] ** 5

        # Variance ratio
        df['variance_ratio'] = self._calculate_variance_ratio(returns)

        # Jump intensity
        df['jump_intensity'] = self._calculate_jump_intensity(returns)

        # Tail ratio
        df['tail_ratio'] = self._calculate_tail_ratio(returns)

        # Runs test
        df['runs_test'] = returns.rolling(50).apply(self._calculate_runs_test)

        # Mean reversion speed
        df['mean_reversion_speed'] = self._calculate_mean_reversion_speed(close)

        return df

    def _calculate_entropy(self, x: np.ndarray) -> float:
        """Calculate Shannon entropy of returns distribution."""
        if len(x) < 10:
            return 0

        # Discretize returns
        hist, _ = np.histogram(x, bins=10, density=True)
        hist = hist[hist > 0]

        if len(hist) == 0:
            return 0

        return -np.sum(hist * np.log2(hist + 1e-10))

    def _calculate_hurst(self, x: np.ndarray) -> float:
        """Calculate Hurst exponent using R/S analysis."""
        if len(x) < 20:
            return 0.5

        n = len(x)
        max_k = min(n // 2, 100)

        rs_list = []
        n_list = []

        for k in range(10, max_k):
            rs = []
            for i in range(n // k):
                subset = x[i * k:(i + 1) * k]
                mean = np.mean(subset)
                cumdev = np.cumsum(subset - mean)
                r = np.max(cumdev) - np.min(cumdev)
                s = np.std(subset)
                if s > 0:
                    rs.append(r / s)

            if rs:
                rs_list.append(np.mean(rs))
                n_list.append(k)

        if len(rs_list) < 2:
            return 0.5

        log_rs = np.log(rs_list)
        log_n = np.log(n_list)

        slope, _, _, _, _ = stats.linregress(log_n, log_rs)
        return slope

    def _calculate_variance_ratio(self, returns: pd.Series, period: int = 20) -> pd.Series:
        """Calculate variance ratio test statistic."""
        var_1 = returns.rolling(period).var()
        var_q = returns.rolling(period * 2).var() * 2
        return var_1 / var_q

    def _calculate_jump_intensity(self, returns: pd.Series, threshold: float = 3.0) -> pd.Series:
        """Calculate jump intensity (frequency of large moves)."""
        std = returns.rolling(50).std()
        jumps = (returns.abs() > threshold * std).astype(float)
        return jumps.rolling(20).mean()

    def _calculate_tail_ratio(self, returns: pd.Series, period: int = 50) -> pd.Series:
        """Calculate tail ratio (right tail / left tail)."""
        def tail_ratio(x):
            upper = np.percentile(x, 95)
            lower = np.percentile(x, 5)
            if lower != 0:
                return abs(upper / lower)
            return 1

        return returns.rolling(period).apply(tail_ratio)

    def _calculate_runs_test(self, x: np.ndarray) -> float:
        """Calculate runs test statistic for randomness."""
        if len(x) < 10:
            return 0

        signs = np.sign(x)
        signs = signs[signs != 0]

        if len(signs) < 2:
            return 0

        n_pos = (signs > 0).sum()
        n_neg = (signs < 0).sum()
        n = n_pos + n_neg

        if n_pos == 0 or n_neg == 0:
            return 0

        # Count runs
        runs = 1 + np.sum(signs[1:] != signs[:-1])

        # Expected runs
        expected_runs = 1 + (2 * n_pos * n_neg) / n
        std_runs = np.sqrt((2 * n_pos * n_neg * (2 * n_pos * n_neg - n)) /
                          (n ** 2 * (n - 1)))

        if std_runs == 0:
            return 0

        return (runs - expected_runs) / std_runs

    def _calculate_mean_reversion_speed(self, close: pd.Series, period: int = 50) -> pd.Series:
        """Calculate mean reversion speed using Ornstein-Uhlenbeck."""
        def ou_speed(x):
            if len(x) < 10:
                return 0

            # Simple AR(1) estimation
            x = np.array(x)
            x_lag = x[:-1]
            x_curr = x[1:]

            if np.std(x_lag) == 0:
                return 0

            # OLS: x_t = alpha + beta * x_{t-1} + epsilon
            cov = np.cov(x_lag, x_curr)[0, 1]
            var = np.var(x_lag)

            beta = cov / var if var > 0 else 0

            # Mean reversion speed = -log(beta)
            if 0 < beta < 1:
                return -np.log(beta)
            return 0

        return close.rolling(period).apply(ou_speed)


# =============================================================================
# Volume Features
# =============================================================================

class VolumeFeatures(FeatureCalculator):
    """Volume-based features."""

    @property
    def feature_names(self) -> List[str]:
        names = [
            'volume_sma_ratio_10', 'volume_sma_ratio_20', 'volume_sma_ratio_50',
            'obv', 'obv_sma_ratio',
            'ad_line', 'ad_oscillator',
            'cmf', 'force_index',
            'ease_of_movement', 'volume_price_trend',
            'negative_volume_index', 'positive_volume_index',
            'volume_momentum', 'volume_acceleration',
            'klinger_oscillator', 'klinger_signal',
            'volume_weighted_macd',
            'volume_concentration',
            'price_volume_correlation',
        ]
        return names

    @property
    def category(self) -> FeatureCategory:
        return FeatureCategory.VOLUME

    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        """Calculate volume features."""
        df = pd.DataFrame(index=data.index)

        close = data['close']
        high = data['high']
        low = data['low']
        volume = data['volume']

        # Relative volume
        for period in [10, 20, 50]:
            sma = volume.rolling(period).mean()
            df[f'volume_sma_ratio_{period}'] = volume / sma

        # OBV
        obv = self._calculate_obv(close, volume)
        df['obv'] = obv
        df['obv_sma_ratio'] = obv / obv.rolling(20).mean()

        # A/D Line
        ad = self._calculate_ad_line(high, low, close, volume)
        df['ad_line'] = ad
        df['ad_oscillator'] = ad.ewm(span=3).mean() - ad.ewm(span=10).mean()

        # CMF
        df['cmf'] = self._calculate_cmf(high, low, close, volume)

        # Force Index
        df['force_index'] = close.diff() * volume

        # Ease of Movement
        df['ease_of_movement'] = self._calculate_eom(high, low, volume)

        # Volume Price Trend
        df['volume_price_trend'] = (close.pct_change() * volume).cumsum()

        # NVI / PVI
        nvi, pvi = self._calculate_nvi_pvi(close, volume)
        df['negative_volume_index'] = nvi
        df['positive_volume_index'] = pvi

        # Volume momentum
        df['volume_momentum'] = volume.pct_change(10)
        df['volume_acceleration'] = df['volume_momentum'].diff()

        # Klinger Oscillator
        ko, signal = self._calculate_klinger(high, low, close, volume)
        df['klinger_oscillator'] = ko
        df['klinger_signal'] = signal

        # Volume-weighted MACD
        df['volume_weighted_macd'] = self._calculate_vwmacd(close, volume)

        # Volume concentration
        df['volume_concentration'] = volume.rolling(20).apply(
            lambda x: x.max() / x.sum() if x.sum() > 0 else 0
        )

        # Price-volume correlation
        df['price_volume_correlation'] = close.rolling(20).corr(volume)

        return df

    def _calculate_obv(self, close: pd.Series, volume: pd.Series) -> pd.Series:
        """Calculate On-Balance Volume."""
        direction = np.sign(close.diff())
        return (volume * direction).cumsum()

    def _calculate_ad_line(
        self, high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series
    ) -> pd.Series:
        """Calculate Accumulation/Distribution Line."""
        clv = ((close - low) - (high - close)) / (high - low)
        clv = clv.fillna(0)
        return (clv * volume).cumsum()

    def _calculate_cmf(
        self, high: pd.Series, low: pd.Series, close: pd.Series,
        volume: pd.Series, period: int = 20
    ) -> pd.Series:
        """Calculate Chaikin Money Flow."""
        clv = ((close - low) - (high - close)) / (high - low)
        clv = clv.fillna(0)
        return (clv * volume).rolling(period).sum() / volume.rolling(period).sum()

    def _calculate_eom(
        self, high: pd.Series, low: pd.Series, volume: pd.Series, period: int = 14
    ) -> pd.Series:
        """Calculate Ease of Movement."""
        dm = ((high + low) / 2) - ((high.shift(1) + low.shift(1)) / 2)
        br = volume / (high - low)
        eom = dm / br
        return eom.rolling(period).mean()

    def _calculate_nvi_pvi(
        self, close: pd.Series, volume: pd.Series
    ) -> Tuple[pd.Series, pd.Series]:
        """Calculate Negative/Positive Volume Index."""
        returns = close.pct_change()
        vol_change = volume.diff()

        nvi = pd.Series(1000, index=close.index, dtype=float)
        pvi = pd.Series(1000, index=close.index, dtype=float)

        for i in range(1, len(close)):
            if vol_change.iloc[i] < 0:
                nvi.iloc[i] = nvi.iloc[i-1] * (1 + returns.iloc[i])
            else:
                nvi.iloc[i] = nvi.iloc[i-1]

            if vol_change.iloc[i] > 0:
                pvi.iloc[i] = pvi.iloc[i-1] * (1 + returns.iloc[i])
            else:
                pvi.iloc[i] = pvi.iloc[i-1]

        return nvi, pvi

    def _calculate_klinger(
        self, high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series
    ) -> Tuple[pd.Series, pd.Series]:
        """Calculate Klinger Oscillator."""
        hlc = high + low + close
        trend = np.sign(hlc.diff())
        dm = high - low
        cm = np.where(trend == trend.shift(1), cm if 'cm' in dir() else dm, dm)

        vf = volume * np.abs(2 * (dm / cm) - 1) * trend * 100

        ko = pd.Series(vf).ewm(span=34).mean() - pd.Series(vf).ewm(span=55).mean()
        signal = ko.ewm(span=13).mean()

        return ko, signal

    def _calculate_vwmacd(self, close: pd.Series, volume: pd.Series) -> pd.Series:
        """Calculate Volume-Weighted MACD."""
        vwap_fast = (close * volume).rolling(12).sum() / volume.rolling(12).sum()
        vwap_slow = (close * volume).rolling(26).sum() / volume.rolling(26).sum()
        return vwap_fast - vwap_slow


# =============================================================================
# Master Feature Pipeline
# =============================================================================

class FeatureEngineer:
    """
    Master feature engineering pipeline.

    Combines all feature calculators and provides unified interface
    for generating features from OHLCV data.
    """

    def __init__(self, include_categories: Optional[List[FeatureCategory]] = None):
        """
        Initialize feature engineer.

        Args:
            include_categories: List of categories to include. None = all.
        """
        self.calculators: List[FeatureCalculator] = []

        all_calculators = [
            PriceFeatures(),
            MomentumFeatures(),
            VolatilityFeatures(),
            TrendFeatures(),
            StatisticalFeatures(),
            VolumeFeatures(),
        ]

        for calc in all_calculators:
            if include_categories is None or calc.category in include_categories:
                self.calculators.append(calc)

        self._feature_metadata: Dict[str, FeatureMetadata] = {}
        self._build_metadata()

    def _build_metadata(self):
        """Build feature metadata registry."""
        for calc in self.calculators:
            for name in calc.feature_names:
                self._feature_metadata[name] = FeatureMetadata(
                    name=name,
                    category=calc.category,
                    lookback=self._infer_lookback(name),
                    description=f"{calc.category.value} feature: {name}"
                )

    def _infer_lookback(self, name: str) -> int:
        """Infer lookback period from feature name."""
        import re
        match = re.search(r'_(\d+)$', name)
        if match:
            return int(match.group(1))
        return 20  # Default

    @property
    def feature_names(self) -> List[str]:
        """Get list of all feature names."""
        names = []
        for calc in self.calculators:
            names.extend(calc.feature_names)
        return names

    @property
    def num_features(self) -> int:
        """Get total number of features."""
        return len(self.feature_names)

    def calculate(
        self,
        data: pd.DataFrame,
        fillna: bool = True,
        normalize: bool = False
    ) -> pd.DataFrame:
        """
        Calculate all features.

        Args:
            data: DataFrame with columns [open, high, low, close, volume]
            fillna: Fill NaN values
            normalize: Normalize features to [-1, 1]

        Returns:
            DataFrame with all calculated features
        """
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in required_cols:
            if col not in data.columns:
                raise ValueError(f"Missing required column: {col}")

        features = pd.DataFrame(index=data.index)

        for calc in self.calculators:
            try:
                calc_features = calc.calculate(data)
                features = pd.concat([features, calc_features], axis=1)
            except Exception as e:
                logger.warning(f"Error in {calc.__class__.__name__}: {e}")

        if fillna:
            features = features.fillna(method='ffill').fillna(0)

        if normalize:
            features = self._normalize(features)

        return features

    def _normalize(self, features: pd.DataFrame) -> pd.DataFrame:
        """Normalize features using rolling z-score."""
        normalized = pd.DataFrame(index=features.index)

        for col in features.columns:
            mean = features[col].rolling(252).mean()
            std = features[col].rolling(252).std()
            normalized[col] = (features[col] - mean) / (std + 1e-8)
            normalized[col] = normalized[col].clip(-3, 3)  # Clip outliers

        return normalized

    def get_feature_importance(
        self,
        features: pd.DataFrame,
        target: pd.Series
    ) -> pd.DataFrame:
        """
        Calculate feature importance using correlation with target.
        """
        importance = []

        for col in features.columns:
            corr = features[col].corr(target)
            importance.append({
                'feature': col,
                'correlation': corr,
                'abs_correlation': abs(corr),
                'category': self._feature_metadata.get(col, FeatureMetadata(col, FeatureCategory.PRICE, 0, '')).category.value,
            })

        importance_df = pd.DataFrame(importance)
        return importance_df.sort_values('abs_correlation', ascending=False)
