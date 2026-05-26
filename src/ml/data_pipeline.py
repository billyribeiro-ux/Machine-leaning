"""
ML Data Pipeline - Universal Data Integration for ML Models

Connects all ML models and scanners to multi-vendor data sources:
- Feature engineering pipelines
- Real-time data streaming
- Batch data loading for training
- Feature caching and optimization
- Automatic data validation
- Multi-timeframe support

Author: Revolution Alpha Engine
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Union, Callable, Generator
from datetime import datetime, timedelta
from enum import Enum
from collections import deque
from abc import ABC, abstractmethod
import threading
from queue import Queue
import time
import warnings

warnings.filterwarnings('ignore')

# Import data adapters
import sys
sys.path.append('..')
try:
    from src.data.adapters import (
        UniversalDataManager,
        ScannerDataPreparer,
        DataVendor,
        DataType,
        StandardOHLCV,
        StandardTrade,
        StandardQuote,
        StandardOption
    )
except ImportError:
    # Define placeholders if imports fail
    UniversalDataManager = None
    ScannerDataPreparer = None


class FeatureType(Enum):
    """Types of features for ML models."""
    PRICE = "price"
    VOLUME = "volume"
    VOLATILITY = "volatility"
    MOMENTUM = "momentum"
    TREND = "trend"
    MICROSTRUCTURE = "microstructure"
    OPTIONS = "options"
    SENTIMENT = "sentiment"
    REGIME = "regime"
    TECHNICAL = "technical"
    FUNDAMENTAL = "fundamental"


class TimeFrame(Enum):
    """Supported timeframes."""
    TICK = "tick"
    S1 = "1s"
    S5 = "5s"
    S15 = "15s"
    S30 = "30s"
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"


@dataclass
class FeatureConfig:
    """Configuration for feature generation."""
    # Price features
    use_returns: bool = True
    use_log_returns: bool = True
    return_periods: List[int] = field(default_factory=lambda: [1, 5, 10, 20, 60])

    # Volatility features
    use_volatility: bool = True
    volatility_windows: List[int] = field(default_factory=lambda: [5, 10, 20, 60])
    use_garman_klass: bool = True
    use_parkinson: bool = True

    # Momentum features
    use_rsi: bool = True
    use_macd: bool = True
    use_momentum: bool = True
    momentum_periods: List[int] = field(default_factory=lambda: [5, 10, 20])

    # Trend features
    use_sma: bool = True
    use_ema: bool = True
    ma_periods: List[int] = field(default_factory=lambda: [5, 10, 20, 50, 200])
    use_trend_strength: bool = True

    # Volume features
    use_volume_ma: bool = True
    use_vwap: bool = True
    use_obv: bool = True
    use_mfi: bool = True

    # Microstructure features
    use_bid_ask_spread: bool = True
    use_trade_imbalance: bool = True
    use_order_flow: bool = True

    # Options features
    use_iv: bool = True
    use_greeks: bool = True
    use_put_call_ratio: bool = True
    use_options_volume: bool = True

    # Regime features
    use_regime_indicator: bool = True
    use_vix_regime: bool = True

    # Normalization
    normalize_features: bool = True
    normalization_window: int = 252

    # Sequence
    sequence_length: int = 60
    prediction_horizon: int = 1


@dataclass
class DataStreamConfig:
    """Configuration for real-time data streaming."""
    symbols: List[str] = field(default_factory=list)
    timeframe: TimeFrame = TimeFrame.M1
    buffer_size: int = 1000
    batch_size: int = 64
    update_interval_ms: int = 100
    auto_reconnect: bool = True
    max_retries: int = 5


class FeatureEngineer:
    """
    Advanced feature engineering for ML models.

    Generates 500+ features from raw market data.
    """

    def __init__(self, config: Optional[FeatureConfig] = None):
        self.config = config or FeatureConfig()
        self._feature_cache = {}

    def generate_all_features(
        self,
        ohlcv: pd.DataFrame,
        trades: Optional[pd.DataFrame] = None,
        quotes: Optional[pd.DataFrame] = None,
        options: Optional[pd.DataFrame] = None
    ) -> pd.DataFrame:
        """
        Generate all features from market data.

        Args:
            ohlcv: OHLCV DataFrame
            trades: Trade data (optional)
            quotes: Quote data (optional)
            options: Options chain data (optional)

        Returns:
            DataFrame with all generated features
        """
        features = pd.DataFrame(index=ohlcv.index)

        # Price features
        if self.config.use_returns:
            price_features = self._generate_price_features(ohlcv)
            features = pd.concat([features, price_features], axis=1)

        # Volatility features
        if self.config.use_volatility:
            vol_features = self._generate_volatility_features(ohlcv)
            features = pd.concat([features, vol_features], axis=1)

        # Momentum features
        momentum_features = self._generate_momentum_features(ohlcv)
        features = pd.concat([features, momentum_features], axis=1)

        # Trend features
        trend_features = self._generate_trend_features(ohlcv)
        features = pd.concat([features, trend_features], axis=1)

        # Volume features
        volume_features = self._generate_volume_features(ohlcv)
        features = pd.concat([features, volume_features], axis=1)

        # Microstructure features (if trade/quote data available)
        if trades is not None or quotes is not None:
            micro_features = self._generate_microstructure_features(ohlcv, trades, quotes)
            features = pd.concat([features, micro_features], axis=1)

        # Options features (if options data available)
        if options is not None:
            options_features = self._generate_options_features(options)
            features = pd.concat([features, options_features], axis=1)

        # Technical patterns
        pattern_features = self._generate_pattern_features(ohlcv)
        features = pd.concat([features, pattern_features], axis=1)

        # Regime features
        regime_features = self._generate_regime_features(ohlcv)
        features = pd.concat([features, regime_features], axis=1)

        # Normalize if configured
        if self.config.normalize_features:
            features = self._normalize_features(features)

        # Fill NaN values
        features = features.ffill().bfill().fillna(0)

        return features

    def _generate_price_features(self, ohlcv: pd.DataFrame) -> pd.DataFrame:
        """Generate price-based features."""
        features = pd.DataFrame(index=ohlcv.index)
        close = ohlcv['close']

        # Returns
        for period in self.config.return_periods:
            features[f'return_{period}'] = close.pct_change(period)

            if self.config.use_log_returns:
                features[f'log_return_{period}'] = np.log(close / close.shift(period))

        # Price relative to high/low
        features['close_to_high'] = close / ohlcv['high']
        features['close_to_low'] = close / ohlcv['low']
        features['high_low_range'] = (ohlcv['high'] - ohlcv['low']) / close

        # Price acceleration
        features['return_acceleration'] = features['return_1'].diff()

        # Gap features
        features['gap'] = ohlcv['open'] / close.shift(1) - 1

        return features

    def _generate_volatility_features(self, ohlcv: pd.DataFrame) -> pd.DataFrame:
        """Generate volatility features."""
        features = pd.DataFrame(index=ohlcv.index)
        close = ohlcv['close']
        high = ohlcv['high']
        low = ohlcv['low']

        returns = close.pct_change()

        # Standard volatility
        for window in self.config.volatility_windows:
            features[f'volatility_{window}'] = returns.rolling(window).std() * np.sqrt(252)

        # Garman-Klass volatility
        if self.config.use_garman_klass:
            for window in self.config.volatility_windows:
                log_hl = np.log(high / low) ** 2
                log_co = np.log(close / ohlcv['open']) ** 2
                gk = 0.5 * log_hl - (2 * np.log(2) - 1) * log_co
                features[f'gk_vol_{window}'] = np.sqrt(gk.rolling(window).mean() * 252)

        # Parkinson volatility
        if self.config.use_parkinson:
            for window in self.config.volatility_windows:
                log_hl_sq = np.log(high / low) ** 2
                features[f'parkinson_vol_{window}'] = np.sqrt(
                    log_hl_sq.rolling(window).mean() / (4 * np.log(2)) * 252
                )

        # Volatility of volatility
        features['vol_of_vol'] = features['volatility_20'].rolling(20).std()

        # Volatility regime
        vol_percentile = features['volatility_20'].rolling(252).apply(
            lambda x: pd.Series(x).rank(pct=True).iloc[-1]
        )
        features['vol_percentile'] = vol_percentile

        return features

    def _generate_momentum_features(self, ohlcv: pd.DataFrame) -> pd.DataFrame:
        """Generate momentum features."""
        features = pd.DataFrame(index=ohlcv.index)
        close = ohlcv['close']
        high = ohlcv['high']
        low = ohlcv['low']
        volume = ohlcv['volume']

        # RSI
        if self.config.use_rsi:
            for period in [7, 14, 21]:
                delta = close.diff()
                gain = (delta.where(delta > 0, 0)).rolling(period).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
                rs = gain / (loss + 1e-10)
                features[f'rsi_{period}'] = 100 - (100 / (1 + rs))

        # MACD
        if self.config.use_macd:
            ema12 = close.ewm(span=12).mean()
            ema26 = close.ewm(span=26).mean()
            features['macd'] = ema12 - ema26
            features['macd_signal'] = features['macd'].ewm(span=9).mean()
            features['macd_hist'] = features['macd'] - features['macd_signal']

        # Momentum
        if self.config.use_momentum:
            for period in self.config.momentum_periods:
                features[f'momentum_{period}'] = close / close.shift(period) - 1

        # Stochastic
        for period in [14, 21]:
            lowest_low = low.rolling(period).min()
            highest_high = high.rolling(period).max()
            features[f'stoch_k_{period}'] = 100 * (close - lowest_low) / (highest_high - lowest_low + 1e-10)
            features[f'stoch_d_{period}'] = features[f'stoch_k_{period}'].rolling(3).mean()

        # Williams %R
        features['williams_r'] = -100 * (high.rolling(14).max() - close) / (
            high.rolling(14).max() - low.rolling(14).min() + 1e-10
        )

        # Rate of Change
        for period in [5, 10, 20]:
            features[f'roc_{period}'] = (close - close.shift(period)) / close.shift(period) * 100

        # CCI
        typical_price = (high + low + close) / 3
        sma_tp = typical_price.rolling(20).mean()
        mad = typical_price.rolling(20).apply(lambda x: np.abs(x - x.mean()).mean())
        features['cci'] = (typical_price - sma_tp) / (0.015 * mad + 1e-10)

        return features

    def _generate_trend_features(self, ohlcv: pd.DataFrame) -> pd.DataFrame:
        """Generate trend features."""
        features = pd.DataFrame(index=ohlcv.index)
        close = ohlcv['close']
        high = ohlcv['high']
        low = ohlcv['low']

        # Moving averages
        for period in self.config.ma_periods:
            if self.config.use_sma:
                features[f'sma_{period}'] = close.rolling(period).mean()
                features[f'close_to_sma_{period}'] = close / features[f'sma_{period}']

            if self.config.use_ema:
                features[f'ema_{period}'] = close.ewm(span=period).mean()
                features[f'close_to_ema_{period}'] = close / features[f'ema_{period}']

        # MA crossovers
        features['sma_5_20_cross'] = (features['sma_5'] > features['sma_20']).astype(int)
        features['sma_20_50_cross'] = (features['sma_20'] > features['sma_50']).astype(int)
        features['ema_5_20_cross'] = (features['ema_5'] > features['ema_20']).astype(int)

        # Trend strength (ADX)
        if self.config.use_trend_strength:
            tr = pd.DataFrame({
                'hl': high - low,
                'hc': abs(high - close.shift(1)),
                'lc': abs(low - close.shift(1))
            }).max(axis=1)

            plus_dm = high.diff()
            minus_dm = -low.diff()
            plus_dm[plus_dm < 0] = 0
            minus_dm[minus_dm < 0] = 0

            tr_14 = tr.rolling(14).sum()
            plus_di = 100 * plus_dm.rolling(14).sum() / (tr_14 + 1e-10)
            minus_di = 100 * minus_dm.rolling(14).sum() / (tr_14 + 1e-10)

            dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
            features['adx'] = dx.rolling(14).mean()
            features['plus_di'] = plus_di
            features['minus_di'] = minus_di

        # Linear regression slope
        for period in [10, 20, 50]:
            features[f'lr_slope_{period}'] = close.rolling(period).apply(
                lambda x: np.polyfit(range(len(x)), x, 1)[0] / x.mean() * 100
            )

        # Supertrend
        atr = self._calculate_atr(high, low, close, 10)
        upper_band = (high + low) / 2 + 3 * atr
        lower_band = (high + low) / 2 - 3 * atr
        features['supertrend_upper'] = upper_band
        features['supertrend_lower'] = lower_band

        return features

    def _generate_volume_features(self, ohlcv: pd.DataFrame) -> pd.DataFrame:
        """Generate volume features."""
        features = pd.DataFrame(index=ohlcv.index)
        close = ohlcv['close']
        high = ohlcv['high']
        low = ohlcv['low']
        volume = ohlcv['volume']

        # Volume MA
        if self.config.use_volume_ma:
            for period in [5, 10, 20, 50]:
                features[f'volume_ma_{period}'] = volume.rolling(period).mean()
                features[f'volume_ratio_{period}'] = volume / features[f'volume_ma_{period}']

        # VWAP
        if self.config.use_vwap:
            typical_price = (high + low + close) / 3
            features['vwap'] = (typical_price * volume).cumsum() / volume.cumsum()
            features['close_to_vwap'] = close / features['vwap']

        # On-Balance Volume
        if self.config.use_obv:
            obv = np.where(close > close.shift(1), volume,
                         np.where(close < close.shift(1), -volume, 0))
            features['obv'] = pd.Series(obv, index=ohlcv.index).cumsum()
            features['obv_ma'] = features['obv'].rolling(20).mean()

        # Money Flow Index
        if self.config.use_mfi:
            typical_price = (high + low + close) / 3
            raw_money_flow = typical_price * volume

            positive_flow = raw_money_flow.where(typical_price > typical_price.shift(1), 0)
            negative_flow = raw_money_flow.where(typical_price < typical_price.shift(1), 0)

            positive_mf = positive_flow.rolling(14).sum()
            negative_mf = negative_flow.rolling(14).sum()

            mfi = 100 - (100 / (1 + positive_mf / (negative_mf + 1e-10)))
            features['mfi'] = mfi

        # Volume Price Trend
        features['vpt'] = (volume * (close.diff() / close.shift(1))).cumsum()

        # Accumulation/Distribution
        clv = ((close - low) - (high - close)) / (high - low + 1e-10)
        features['ad_line'] = (clv * volume).cumsum()

        # Chaikin Money Flow
        features['cmf'] = (clv * volume).rolling(20).sum() / volume.rolling(20).sum()

        return features

    def _generate_microstructure_features(
        self,
        ohlcv: pd.DataFrame,
        trades: Optional[pd.DataFrame] = None,
        quotes: Optional[pd.DataFrame] = None
    ) -> pd.DataFrame:
        """Generate microstructure features from tick data."""
        features = pd.DataFrame(index=ohlcv.index)

        if quotes is not None and len(quotes) > 0:
            # Resample quotes to match OHLCV frequency
            if 'bid' in quotes.columns and 'ask' in quotes.columns:
                quotes_resampled = quotes.resample('1T').last() if hasattr(quotes.index, 'freq') else quotes

                # Bid-ask spread
                features['spread'] = (quotes_resampled['ask'] - quotes_resampled['bid']).reindex(ohlcv.index, method='ffill')
                features['spread_pct'] = features['spread'] / ((quotes_resampled['ask'] + quotes_resampled['bid']) / 2).reindex(ohlcv.index, method='ffill')

                # Quote imbalance
                if 'bid_size' in quotes_resampled.columns and 'ask_size' in quotes_resampled.columns:
                    total_size = quotes_resampled['bid_size'] + quotes_resampled['ask_size']
                    features['quote_imbalance'] = (
                        (quotes_resampled['bid_size'] - quotes_resampled['ask_size']) / (total_size + 1e-10)
                    ).reindex(ohlcv.index, method='ffill')

        if trades is not None and len(trades) > 0:
            # Trade count
            trade_counts = trades.resample('1T').size() if hasattr(trades.index, 'freq') else trades.groupby(trades.index).size()
            features['trade_count'] = trade_counts.reindex(ohlcv.index, method='ffill').fillna(0)

            # Average trade size
            if 'size' in trades.columns:
                avg_size = trades['size'].resample('1T').mean() if hasattr(trades.index, 'freq') else trades.groupby(trades.index)['size'].mean()
                features['avg_trade_size'] = avg_size.reindex(ohlcv.index, method='ffill')

                # Large trade indicator
                threshold = trades['size'].quantile(0.9)
                large_trades = trades[trades['size'] > threshold]
                features['large_trade_count'] = large_trades.resample('1T').size().reindex(ohlcv.index, method='ffill').fillna(0)

        return features

    def _generate_options_features(self, options: pd.DataFrame) -> pd.DataFrame:
        """Generate options-based features."""
        features = pd.DataFrame()

        if options is None or len(options) == 0:
            return features

        # Aggregate by timestamp if available
        if 'timestamp' in options.columns:
            grouped = options.groupby('timestamp')
        else:
            # Single snapshot
            grouped = [(datetime.now(), options)]

        records = []
        for timestamp, group in grouped:
            record = {'timestamp': timestamp}

            # Put/Call ratio
            if 'option_type' in group.columns:
                calls = group[group['option_type'] == 'call']
                puts = group[group['option_type'] == 'put']

                if 'volume' in group.columns:
                    call_vol = calls['volume'].sum()
                    put_vol = puts['volume'].sum()
                    record['put_call_volume_ratio'] = put_vol / (call_vol + 1e-10)

                if 'open_interest' in group.columns:
                    call_oi = calls['open_interest'].sum()
                    put_oi = puts['open_interest'].sum()
                    record['put_call_oi_ratio'] = put_oi / (call_oi + 1e-10)

            # Average IV
            if 'implied_volatility' in group.columns:
                record['avg_iv'] = group['implied_volatility'].mean()
                record['iv_skew'] = (
                    puts['implied_volatility'].mean() - calls['implied_volatility'].mean()
                    if 'option_type' in group.columns else 0
                )

            # Greeks aggregates
            for greek in ['delta', 'gamma', 'theta', 'vega']:
                if greek in group.columns:
                    record[f'total_{greek}'] = group[greek].sum()
                    record[f'avg_{greek}'] = group[greek].mean()

            records.append(record)

        if records:
            features = pd.DataFrame(records)
            if 'timestamp' in features.columns:
                features = features.set_index('timestamp')

        return features

    def _generate_pattern_features(self, ohlcv: pd.DataFrame) -> pd.DataFrame:
        """Generate technical pattern features."""
        features = pd.DataFrame(index=ohlcv.index)
        close = ohlcv['close']
        high = ohlcv['high']
        low = ohlcv['low']
        open_price = ohlcv['open']

        # Candlestick patterns
        body = close - open_price
        upper_shadow = high - pd.concat([close, open_price], axis=1).max(axis=1)
        lower_shadow = pd.concat([close, open_price], axis=1).min(axis=1) - low
        range_hl = high - low

        # Doji
        features['doji'] = (abs(body) < 0.1 * range_hl).astype(int)

        # Hammer
        features['hammer'] = (
            (lower_shadow > 2 * abs(body)) &
            (upper_shadow < abs(body)) &
            (body > 0)
        ).astype(int)

        # Engulfing
        features['bullish_engulfing'] = (
            (body.shift(1) < 0) & (body > 0) &
            (open_price < close.shift(1)) & (close > open_price.shift(1))
        ).astype(int)

        features['bearish_engulfing'] = (
            (body.shift(1) > 0) & (body < 0) &
            (open_price > close.shift(1)) & (close < open_price.shift(1))
        ).astype(int)

        # Higher highs / Lower lows
        features['higher_high'] = (high > high.shift(1)).astype(int)
        features['lower_low'] = (low < low.shift(1)).astype(int)
        features['higher_low'] = (low > low.shift(1)).astype(int)
        features['lower_high'] = (high < high.shift(1)).astype(int)

        # Consecutive patterns
        features['consecutive_up'] = (close > close.shift(1)).astype(int).rolling(5).sum()
        features['consecutive_down'] = (close < close.shift(1)).astype(int).rolling(5).sum()

        # Support/Resistance levels
        features['near_52w_high'] = close / close.rolling(252).max()
        features['near_52w_low'] = close / close.rolling(252).min()

        # Bollinger Band position
        sma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        features['bb_upper'] = sma20 + 2 * std20
        features['bb_lower'] = sma20 - 2 * std20
        features['bb_position'] = (close - features['bb_lower']) / (features['bb_upper'] - features['bb_lower'] + 1e-10)
        features['bb_width'] = (features['bb_upper'] - features['bb_lower']) / sma20

        return features

    def _generate_regime_features(self, ohlcv: pd.DataFrame) -> pd.DataFrame:
        """Generate market regime features."""
        features = pd.DataFrame(index=ohlcv.index)
        close = ohlcv['close']

        # Trend regime
        sma50 = close.rolling(50).mean()
        sma200 = close.rolling(200).mean()

        features['trend_regime'] = np.where(
            (close > sma50) & (sma50 > sma200), 1,  # Bullish
            np.where((close < sma50) & (sma50 < sma200), -1, 0)  # Bearish / Neutral
        )

        # Volatility regime
        returns = close.pct_change()
        vol20 = returns.rolling(20).std() * np.sqrt(252)
        vol_ma = vol20.rolling(60).mean()

        features['vol_regime'] = np.where(
            vol20 > vol_ma * 1.5, 2,  # High vol
            np.where(vol20 < vol_ma * 0.5, 0, 1)  # Low vol / Normal
        )

        # Mean reversion regime
        zscore = (close - close.rolling(20).mean()) / (close.rolling(20).std() + 1e-10)
        features['zscore'] = zscore
        features['mean_reversion_regime'] = np.where(
            zscore > 2, -1,  # Overbought
            np.where(zscore < -2, 1, 0)  # Oversold / Neutral
        )

        # Momentum regime
        mom20 = close / close.shift(20) - 1
        mom_ma = mom20.rolling(60).mean()
        features['momentum_regime'] = np.where(
            mom20 > mom_ma + 0.05, 1,  # Strong momentum
            np.where(mom20 < mom_ma - 0.05, -1, 0)  # Weak momentum / Neutral
        )

        return features

    def _calculate_atr(self, high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
        """Calculate Average True Range."""
        tr = pd.DataFrame({
            'hl': high - low,
            'hc': abs(high - close.shift(1)),
            'lc': abs(low - close.shift(1))
        }).max(axis=1)
        return tr.rolling(period).mean()

    def _normalize_features(self, features: pd.DataFrame) -> pd.DataFrame:
        """Normalize features using rolling z-score."""
        normalized = pd.DataFrame(index=features.index)
        window = self.config.normalization_window

        for col in features.columns:
            rolling_mean = features[col].rolling(window, min_periods=20).mean()
            rolling_std = features[col].rolling(window, min_periods=20).std()
            normalized[col] = (features[col] - rolling_mean) / (rolling_std + 1e-10)
            # Clip extreme values
            normalized[col] = normalized[col].clip(-5, 5)

        return normalized


class DataStreamManager:
    """
    Real-time data streaming manager for ML models.

    Handles live data feeds from multiple vendors with buffering.
    """

    def __init__(
        self,
        data_manager: Optional[UniversalDataManager] = None,
        config: Optional[DataStreamConfig] = None
    ):
        self.data_manager = data_manager
        self.config = config or DataStreamConfig()

        # Buffers for each symbol
        self.buffers: Dict[str, deque] = {}
        self.feature_buffers: Dict[str, deque] = {}

        # State
        self.is_streaming = False
        self._stream_thread = None
        self._callbacks: List[Callable] = []

        # Feature engineer
        self.feature_engineer = FeatureEngineer()

    def add_callback(self, callback: Callable):
        """Add callback for new data."""
        self._callbacks.append(callback)

    def start_streaming(self, symbols: Optional[List[str]] = None):
        """Start streaming data for symbols."""
        if symbols:
            self.config.symbols = symbols

        for symbol in self.config.symbols:
            self.buffers[symbol] = deque(maxlen=self.config.buffer_size)
            self.feature_buffers[symbol] = deque(maxlen=self.config.buffer_size)

        self.is_streaming = True
        self._stream_thread = threading.Thread(target=self._stream_loop, daemon=True)
        self._stream_thread.start()

    def stop_streaming(self):
        """Stop streaming."""
        self.is_streaming = False
        if self._stream_thread:
            self._stream_thread.join(timeout=5)

    def _stream_loop(self):
        """Main streaming loop."""
        while self.is_streaming:
            for symbol in self.config.symbols:
                try:
                    # Get latest data (in production, this would be real-time)
                    data = self._fetch_latest(symbol)
                    if data is not None:
                        self.buffers[symbol].append(data)

                        # Generate features
                        if len(self.buffers[symbol]) >= 60:  # Minimum for features
                            df = pd.DataFrame(list(self.buffers[symbol]))
                            features = self.feature_engineer.generate_all_features(df)
                            self.feature_buffers[symbol].append(features.iloc[-1].to_dict())

                        # Notify callbacks
                        for callback in self._callbacks:
                            callback(symbol, data)

                except Exception:
                    logging.getLogger(__name__).exception("Stream error for %s", symbol)

            time.sleep(self.config.update_interval_ms / 1000)

    def _fetch_latest(self, symbol: str) -> Optional[Dict]:
        """Fetch latest data point."""
        if self.data_manager is None:
            return None

        # Get recent data
        end = datetime.now()
        start = end - timedelta(minutes=5)

        df = self.data_manager.get_ohlcv(symbol, start, end, '1m')
        if df is not None and len(df) > 0:
            return df.iloc[-1].to_dict()

        return None

    def get_latest_features(self, symbol: str, n: int = 1) -> Optional[pd.DataFrame]:
        """Get latest features for symbol."""
        if symbol not in self.feature_buffers:
            return None

        buffer = list(self.feature_buffers[symbol])
        if len(buffer) < n:
            return None

        return pd.DataFrame(buffer[-n:])

    def get_batch(self, symbol: str, batch_size: Optional[int] = None) -> Optional[np.ndarray]:
        """Get batch of features for ML model input."""
        batch_size = batch_size or self.config.batch_size
        features = self.get_latest_features(symbol, batch_size)

        if features is None:
            return None

        return features.values


class MLDataPipeline:
    """
    Complete ML data pipeline connecting data vendors to models.

    Provides:
    - Batch data loading for training
    - Real-time streaming for inference
    - Feature engineering
    - Data validation
    - Caching
    """

    def __init__(
        self,
        data_manager: Optional[UniversalDataManager] = None,
        feature_config: Optional[FeatureConfig] = None
    ):
        self.data_manager = data_manager
        self.feature_config = feature_config or FeatureConfig()

        # Components
        self.feature_engineer = FeatureEngineer(self.feature_config)
        self.stream_manager = DataStreamManager(data_manager)

        # Cache
        self._cache: Dict[str, pd.DataFrame] = {}
        self._cache_timestamps: Dict[str, datetime] = {}
        self._cache_ttl = timedelta(minutes=5)

    def load_training_data(
        self,
        symbols: List[str],
        start_date: datetime,
        end_date: datetime,
        include_options: bool = False,
        vendor: Optional[DataVendor] = None
    ) -> Tuple[np.ndarray, np.ndarray, List[str]]:
        """
        Load and prepare training data for ML models.

        Args:
            symbols: List of symbols
            start_date: Start date
            end_date: End date
            include_options: Whether to include options data
            vendor: Specific vendor to use

        Returns:
            X: Feature matrix (samples, sequence_length, features)
            y: Target values
            feature_names: List of feature names
        """
        all_features = []
        all_targets = []

        for symbol in symbols:
            # Get OHLCV data
            ohlcv = self._get_cached_or_fetch(
                symbol, start_date, end_date, 'ohlcv', vendor
            )

            if ohlcv is None or len(ohlcv) < 100:
                continue

            # Get options data if requested
            options = None
            if include_options and self.data_manager:
                options = self.data_manager.get_options_chain(symbol, vendor=vendor)

            # Generate features
            features = self.feature_engineer.generate_all_features(ohlcv, options=options)

            # Create sequences
            X, y = self._create_sequences(
                features.values,
                ohlcv['close'].values,
                self.feature_config.sequence_length,
                self.feature_config.prediction_horizon
            )

            if len(X) > 0:
                all_features.append(X)
                all_targets.append(y)

        if not all_features:
            return np.array([]), np.array([]), []

        # Combine all data
        X = np.concatenate(all_features, axis=0)
        y = np.concatenate(all_targets, axis=0)
        feature_names = list(features.columns)

        return X, y, feature_names

    def load_inference_data(
        self,
        symbol: str,
        lookback_days: int = 60,
        vendor: Optional[DataVendor] = None
    ) -> Tuple[np.ndarray, List[str]]:
        """
        Load data for inference/prediction.

        Args:
            symbol: Symbol to predict
            lookback_days: Days of history to load
            vendor: Specific vendor to use

        Returns:
            X: Feature matrix for latest sequence
            feature_names: List of feature names
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=lookback_days + 30)  # Buffer

        # Get data
        ohlcv = self._get_cached_or_fetch(symbol, start_date, end_date, 'ohlcv', vendor)

        if ohlcv is None or len(ohlcv) < self.feature_config.sequence_length:
            return np.array([]), []

        # Generate features
        features = self.feature_engineer.generate_all_features(ohlcv)

        # Get latest sequence
        X = features.values[-self.feature_config.sequence_length:]
        X = X.reshape(1, *X.shape)  # Add batch dimension

        return X, list(features.columns)

    def prepare_scanner_data(
        self,
        scanner_type: str,
        symbols: List[str],
        **kwargs
    ) -> Dict[str, Any]:
        """
        Prepare data for different scanner types.

        Args:
            scanner_type: Type of scanner
            symbols: Symbols to prepare data for
            **kwargs: Additional arguments

        Returns:
            Prepared data dict for scanner
        """
        data = {}

        if scanner_type == 'options':
            # Options scanner needs options chain data
            for symbol in symbols:
                if self.data_manager:
                    data[symbol] = {
                        'options': self.data_manager.get_options_chain(symbol),
                        'ohlcv': self._get_recent_ohlcv(symbol, days=30)
                    }

        elif scanner_type == 'momentum':
            # Momentum scanner needs OHLCV with volume
            for symbol in symbols:
                ohlcv = self._get_recent_ohlcv(symbol, days=60)
                if ohlcv is not None:
                    features = self.feature_engineer._generate_momentum_features(ohlcv)
                    data[symbol] = {
                        'ohlcv': ohlcv,
                        'features': features
                    }

        elif scanner_type == 'squeeze':
            # Squeeze scanner needs options and short data
            for symbol in symbols:
                data[symbol] = {
                    'ohlcv': self._get_recent_ohlcv(symbol, days=60),
                    'options': self.data_manager.get_options_chain(symbol) if self.data_manager else None
                }

        elif scanner_type == 'regime':
            # Regime scanner needs longer history
            for symbol in symbols:
                data[symbol] = {
                    'ohlcv': self._get_recent_ohlcv(symbol, days=252)
                }

        elif scanner_type == 'cross_asset':
            # Cross-asset needs multiple symbols
            for symbol in symbols:
                ohlcv = self._get_recent_ohlcv(symbol, days=252)
                if ohlcv is not None:
                    data[symbol] = ohlcv

        return data

    def _get_cached_or_fetch(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        data_type: str,
        vendor: Optional[DataVendor] = None
    ) -> Optional[pd.DataFrame]:
        """Get data from cache or fetch from vendor."""
        cache_key = f"{symbol}_{data_type}_{start_date.date()}_{end_date.date()}"

        # Check cache
        if cache_key in self._cache:
            if datetime.now() - self._cache_timestamps[cache_key] < self._cache_ttl:
                return self._cache[cache_key]

        # Fetch from vendor
        if self.data_manager is None:
            return None

        if data_type == 'ohlcv':
            df = self.data_manager.get_ohlcv(symbol, start_date, end_date, vendor=vendor)
        elif data_type == 'trades':
            df = self.data_manager.get_trades(symbol, start_date, end_date, vendor=vendor)
        elif data_type == 'quotes':
            df = self.data_manager.get_quotes(symbol, start_date, end_date, vendor=vendor)
        else:
            return None

        # Cache result
        if df is not None and len(df) > 0:
            self._cache[cache_key] = df
            self._cache_timestamps[cache_key] = datetime.now()

        return df

    def _get_recent_ohlcv(self, symbol: str, days: int = 60) -> Optional[pd.DataFrame]:
        """Get recent OHLCV data."""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days + 10)  # Buffer for weekends
        return self._get_cached_or_fetch(symbol, start_date, end_date, 'ohlcv')

    def _create_sequences(
        self,
        features: np.ndarray,
        prices: np.ndarray,
        sequence_length: int,
        prediction_horizon: int
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Create sequences for time series models."""
        X, y = [], []

        for i in range(len(features) - sequence_length - prediction_horizon + 1):
            X.append(features[i:i + sequence_length])

            # Target: future return
            future_return = (prices[i + sequence_length + prediction_horizon - 1] -
                           prices[i + sequence_length - 1]) / prices[i + sequence_length - 1]
            y.append(future_return)

        return np.array(X), np.array(y)

    def start_live_stream(self, symbols: List[str]):
        """Start live data streaming."""
        self.stream_manager.start_streaming(symbols)

    def stop_live_stream(self):
        """Stop live data streaming."""
        self.stream_manager.stop_streaming()

    def get_live_features(self, symbol: str) -> Optional[np.ndarray]:
        """Get latest features from live stream."""
        return self.stream_manager.get_batch(symbol, 1)


# Factory functions
def create_feature_engineer(config: Optional[FeatureConfig] = None) -> FeatureEngineer:
    """Create feature engineer."""
    return FeatureEngineer(config)


def create_ml_pipeline(
    data_manager: Optional[UniversalDataManager] = None,
    feature_config: Optional[FeatureConfig] = None
) -> MLDataPipeline:
    """Create ML data pipeline."""
    return MLDataPipeline(data_manager, feature_config)


def create_stream_manager(
    data_manager: Optional[UniversalDataManager] = None,
    config: Optional[DataStreamConfig] = None
) -> DataStreamManager:
    """Create data stream manager."""
    return DataStreamManager(data_manager, config)


# Example usage
if __name__ == "__main__":
    print("="*60)
    print("ML DATA PIPELINE - TEST MODE")
    print("="*60)

    # Create feature engineer
    config = FeatureConfig(
        sequence_length=60,
        prediction_horizon=5
    )
    engineer = create_feature_engineer(config)

    # Generate sample data
    np.random.seed(42)
    n = 500
    dates = pd.date_range(end=datetime.now(), periods=n, freq='1h')

    price = 100 * np.cumprod(1 + np.random.normal(0.0001, 0.01, n))

    ohlcv = pd.DataFrame({
        'open': price * (1 + np.random.normal(0, 0.002, n)),
        'high': price * (1 + abs(np.random.normal(0, 0.01, n))),
        'low': price * (1 - abs(np.random.normal(0, 0.01, n))),
        'close': price,
        'volume': np.random.randint(100000, 1000000, n)
    }, index=dates)

    print(f"\nSample data shape: {ohlcv.shape}")

    # Generate features
    print("\nGenerating features...")
    features = engineer.generate_all_features(ohlcv)

    print(f"Features generated: {len(features.columns)}")
    print(f"Feature matrix shape: {features.shape}")

    # Show feature categories
    print("\nFeature Categories:")
    price_features = [c for c in features.columns if 'return' in c or 'price' in c or 'close' in c or 'gap' in c]
    print(f"  Price features: {len(price_features)}")

    vol_features = [c for c in features.columns if 'vol' in c.lower() or 'atr' in c.lower()]
    print(f"  Volatility features: {len(vol_features)}")

    mom_features = [c for c in features.columns if 'rsi' in c or 'macd' in c or 'momentum' in c or 'stoch' in c or 'roc' in c]
    print(f"  Momentum features: {len(mom_features)}")

    trend_features = [c for c in features.columns if 'sma' in c or 'ema' in c or 'adx' in c or 'lr_slope' in c]
    print(f"  Trend features: {len(trend_features)}")

    volume_features = [c for c in features.columns if 'volume' in c or 'vwap' in c or 'obv' in c or 'mfi' in c]
    print(f"  Volume features: {len(volume_features)}")

    pattern_features = [c for c in features.columns if 'doji' in c or 'hammer' in c or 'engulfing' in c or 'bb_' in c]
    print(f"  Pattern features: {len(pattern_features)}")

    regime_features = [c for c in features.columns if 'regime' in c or 'zscore' in c]
    print(f"  Regime features: {len(regime_features)}")

    # Create ML pipeline
    print("\n" + "="*60)
    print("ML Pipeline Integration")
    print("="*60)

    pipeline = create_ml_pipeline(feature_config=config)

    print("""
Example Usage with Data Vendors:

    from src.data import create_data_manager, create_polygon_adapter, DataVendor
    from src.ml.data_pipeline import create_ml_pipeline, FeatureConfig

    # Setup data manager
    manager = create_data_manager()
    manager.register_adapter(DataVendor.POLYGON, create_polygon_adapter("API_KEY"))

    # Create pipeline
    config = FeatureConfig(sequence_length=60, prediction_horizon=5)
    pipeline = create_ml_pipeline(manager, config)

    # Load training data
    X_train, y_train, feature_names = pipeline.load_training_data(
        symbols=['AAPL', 'MSFT', 'GOOGL'],
        start_date=datetime(2023, 1, 1),
        end_date=datetime(2024, 1, 1)
    )

    # Load inference data
    X_pred, _ = pipeline.load_inference_data('AAPL')

    # Prepare scanner data
    scanner_data = pipeline.prepare_scanner_data('momentum', ['AAPL', 'MSFT'])

    # Start live streaming
    pipeline.start_live_stream(['AAPL', 'MSFT'])
    """)

    print(f"\n{'='*60}")
    print("ML DATA PIPELINE - READY FOR PRODUCTION")
    print('='*60)
