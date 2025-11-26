"""
Scanner Data Integration Layer

Connects all scanners to multi-vendor data sources:
- Options Scanner
- Squeeze Scanner
- Momentum Scanner
- MTF Scanner
- 0DTE Scanner
- Institutional Scanners

Provides unified data access with caching and real-time support.

Author: Revolution Alpha Engine
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Union, Callable
from datetime import datetime, timedelta
from enum import Enum
from abc import ABC, abstractmethod
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings

warnings.filterwarnings('ignore')

# Import data components
import sys
sys.path.append('..')
try:
    from src.data.adapters import (
        UniversalDataManager,
        DataVendor,
        DataType
    )
    from src.ml.data_pipeline import (
        MLDataPipeline,
        FeatureEngineer,
        FeatureConfig
    )
except ImportError:
    UniversalDataManager = None
    MLDataPipeline = None


class ScannerType(Enum):
    """Types of scanners."""
    OPTIONS_DAY = "options_day"
    OPTIONS_SWING = "options_swing"
    SQUEEZE = "squeeze"
    MOMENTUM = "momentum"
    MTF = "mtf"
    REVERSAL = "reversal"
    BREAKOUT = "breakout"
    ZERO_DTE = "0dte"
    VIX_TRACKER = "vix_tracker"
    DARK_POOL = "dark_pool"
    SMART_MONEY = "smart_money"
    REGIME = "regime"
    CROSS_ASSET = "cross_asset"
    ORDER_FLOW = "order_flow"


@dataclass
class ScannerDataConfig:
    """Configuration for scanner data requirements."""
    scanner_type: ScannerType
    requires_ohlcv: bool = True
    requires_options: bool = False
    requires_trades: bool = False
    requires_quotes: bool = False
    requires_order_book: bool = False
    requires_dark_pool: bool = False
    requires_short_data: bool = False
    lookback_days: int = 60
    min_data_points: int = 20
    timeframe: str = "1d"
    refresh_interval_seconds: int = 60


# Scanner data requirements mapping
SCANNER_REQUIREMENTS = {
    ScannerType.OPTIONS_DAY: ScannerDataConfig(
        scanner_type=ScannerType.OPTIONS_DAY,
        requires_options=True,
        requires_trades=True,
        lookback_days=5,
        timeframe="5m"
    ),
    ScannerType.OPTIONS_SWING: ScannerDataConfig(
        scanner_type=ScannerType.OPTIONS_SWING,
        requires_options=True,
        lookback_days=30,
        timeframe="1d"
    ),
    ScannerType.SQUEEZE: ScannerDataConfig(
        scanner_type=ScannerType.SQUEEZE,
        requires_options=True,
        requires_short_data=True,
        lookback_days=60,
        timeframe="1d"
    ),
    ScannerType.MOMENTUM: ScannerDataConfig(
        scanner_type=ScannerType.MOMENTUM,
        lookback_days=60,
        timeframe="1d"
    ),
    ScannerType.MTF: ScannerDataConfig(
        scanner_type=ScannerType.MTF,
        lookback_days=252,
        timeframe="1d"
    ),
    ScannerType.REVERSAL: ScannerDataConfig(
        scanner_type=ScannerType.REVERSAL,
        lookback_days=30,
        timeframe="1h"
    ),
    ScannerType.BREAKOUT: ScannerDataConfig(
        scanner_type=ScannerType.BREAKOUT,
        lookback_days=60,
        timeframe="1d"
    ),
    ScannerType.ZERO_DTE: ScannerDataConfig(
        scanner_type=ScannerType.ZERO_DTE,
        requires_options=True,
        requires_trades=True,
        requires_quotes=True,
        lookback_days=1,
        timeframe="1m",
        refresh_interval_seconds=5
    ),
    ScannerType.VIX_TRACKER: ScannerDataConfig(
        scanner_type=ScannerType.VIX_TRACKER,
        requires_options=True,
        lookback_days=90,
        timeframe="1d"
    ),
    ScannerType.DARK_POOL: ScannerDataConfig(
        scanner_type=ScannerType.DARK_POOL,
        requires_trades=True,
        requires_quotes=True,
        requires_dark_pool=True,
        lookback_days=30,
        timeframe="1d"
    ),
    ScannerType.SMART_MONEY: ScannerDataConfig(
        scanner_type=ScannerType.SMART_MONEY,
        requires_options=True,
        requires_trades=True,
        lookback_days=30,
        timeframe="1d"
    ),
    ScannerType.REGIME: ScannerDataConfig(
        scanner_type=ScannerType.REGIME,
        lookback_days=252,
        timeframe="1d"
    ),
    ScannerType.CROSS_ASSET: ScannerDataConfig(
        scanner_type=ScannerType.CROSS_ASSET,
        lookback_days=252,
        timeframe="1d"
    ),
    ScannerType.ORDER_FLOW: ScannerDataConfig(
        scanner_type=ScannerType.ORDER_FLOW,
        requires_trades=True,
        requires_quotes=True,
        requires_order_book=True,
        lookback_days=1,
        timeframe="1m",
        refresh_interval_seconds=1
    ),
}


@dataclass
class ScannerDataPackage:
    """Complete data package for a scanner."""
    symbol: str
    scanner_type: ScannerType
    timestamp: datetime
    ohlcv: Optional[pd.DataFrame] = None
    options: Optional[pd.DataFrame] = None
    trades: Optional[pd.DataFrame] = None
    quotes: Optional[pd.DataFrame] = None
    order_book: Optional[Dict] = None
    dark_pool: Optional[pd.DataFrame] = None
    short_data: Optional[pd.DataFrame] = None
    features: Optional[pd.DataFrame] = None
    metadata: Dict = field(default_factory=dict)

    def is_valid(self, config: ScannerDataConfig) -> bool:
        """Check if data package meets requirements."""
        if config.requires_ohlcv and (self.ohlcv is None or len(self.ohlcv) < config.min_data_points):
            return False
        if config.requires_options and self.options is None:
            return False
        if config.requires_trades and self.trades is None:
            return False
        if config.requires_quotes and self.quotes is None:
            return False
        if config.requires_order_book and self.order_book is None:
            return False
        return True


class BaseScannerDataProvider(ABC):
    """Abstract base class for scanner data providers."""

    @abstractmethod
    def get_data(self, symbol: str, config: ScannerDataConfig) -> ScannerDataPackage:
        """Get data for scanner."""
        pass

    @abstractmethod
    def get_batch_data(self, symbols: List[str], config: ScannerDataConfig) -> Dict[str, ScannerDataPackage]:
        """Get data for multiple symbols."""
        pass


class UniversalScannerDataProvider(BaseScannerDataProvider):
    """
    Universal scanner data provider using multi-vendor adapters.

    Automatically fetches required data from available vendors.
    """

    def __init__(
        self,
        data_manager: Optional[UniversalDataManager] = None,
        feature_engineer: Optional[FeatureEngineer] = None,
        max_workers: int = 10
    ):
        self.data_manager = data_manager
        self.feature_engineer = feature_engineer or FeatureEngineer()
        self.max_workers = max_workers

        # Cache
        self._cache: Dict[str, ScannerDataPackage] = {}
        self._cache_timestamps: Dict[str, datetime] = {}

    def get_data(
        self,
        symbol: str,
        config: ScannerDataConfig,
        use_cache: bool = True,
        vendor: Optional[DataVendor] = None
    ) -> ScannerDataPackage:
        """
        Get complete data package for scanner.

        Args:
            symbol: Stock symbol
            config: Scanner data configuration
            use_cache: Whether to use cached data
            vendor: Specific vendor to use

        Returns:
            ScannerDataPackage with all required data
        """
        cache_key = f"{symbol}_{config.scanner_type.value}"

        # Check cache
        if use_cache and cache_key in self._cache:
            cache_time = self._cache_timestamps.get(cache_key)
            if cache_time and (datetime.now() - cache_time).seconds < config.refresh_interval_seconds:
                return self._cache[cache_key]

        # Initialize package
        package = ScannerDataPackage(
            symbol=symbol,
            scanner_type=config.scanner_type,
            timestamp=datetime.now()
        )

        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=config.lookback_days + 10)

        # Fetch required data
        if config.requires_ohlcv and self.data_manager:
            package.ohlcv = self.data_manager.get_ohlcv(
                symbol, start_date, end_date, config.timeframe, vendor
            )

        if config.requires_options and self.data_manager:
            package.options = self.data_manager.get_options_chain(symbol, vendor=vendor)

        if config.requires_trades and self.data_manager:
            # For intraday, get recent trades
            trade_start = end_date - timedelta(days=min(config.lookback_days, 5))
            package.trades = self.data_manager.get_trades(symbol, trade_start, end_date, vendor)

        if config.requires_quotes and self.data_manager:
            quote_start = end_date - timedelta(days=min(config.lookback_days, 1))
            package.quotes = self.data_manager.get_quotes(symbol, quote_start, end_date, vendor)

        # Generate features if OHLCV available
        if package.ohlcv is not None and len(package.ohlcv) > 0:
            package.features = self.feature_engineer.generate_all_features(
                package.ohlcv,
                package.trades,
                package.quotes,
                package.options
            )

        # Add metadata
        package.metadata = {
            'vendor': vendor.value if vendor else 'auto',
            'fetch_time_ms': (datetime.now() - package.timestamp).total_seconds() * 1000,
            'data_points': len(package.ohlcv) if package.ohlcv is not None else 0
        }

        # Cache
        self._cache[cache_key] = package
        self._cache_timestamps[cache_key] = datetime.now()

        return package

    def get_batch_data(
        self,
        symbols: List[str],
        config: ScannerDataConfig,
        use_cache: bool = True,
        vendor: Optional[DataVendor] = None
    ) -> Dict[str, ScannerDataPackage]:
        """
        Get data for multiple symbols in parallel.

        Args:
            symbols: List of symbols
            config: Scanner data configuration
            use_cache: Whether to use cached data
            vendor: Specific vendor to use

        Returns:
            Dict mapping symbols to data packages
        """
        results = {}

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self.get_data, symbol, config, use_cache, vendor): symbol
                for symbol in symbols
            }

            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    results[symbol] = future.result()
                except Exception as e:
                    print(f"Error fetching {symbol}: {e}")
                    results[symbol] = ScannerDataPackage(
                        symbol=symbol,
                        scanner_type=config.scanner_type,
                        timestamp=datetime.now(),
                        metadata={'error': str(e)}
                    )

        return results

    def clear_cache(self, symbol: Optional[str] = None, scanner_type: Optional[ScannerType] = None):
        """Clear cache."""
        if symbol and scanner_type:
            key = f"{symbol}_{scanner_type.value}"
            self._cache.pop(key, None)
            self._cache_timestamps.pop(key, None)
        elif symbol:
            keys_to_remove = [k for k in self._cache if k.startswith(symbol)]
            for k in keys_to_remove:
                self._cache.pop(k, None)
                self._cache_timestamps.pop(k, None)
        else:
            self._cache.clear()
            self._cache_timestamps.clear()


class ScannerDataIntegration:
    """
    Master integration layer connecting all scanners to data sources.

    Provides a unified interface for:
    - All scanner types
    - Multiple data vendors
    - Real-time and historical data
    - Feature engineering
    """

    def __init__(
        self,
        data_manager: Optional[UniversalDataManager] = None,
        ml_pipeline: Optional[MLDataPipeline] = None
    ):
        self.data_manager = data_manager
        self.ml_pipeline = ml_pipeline

        # Data provider
        self.provider = UniversalScannerDataProvider(data_manager)

        # Active subscriptions for real-time
        self._subscriptions: Dict[str, List[Callable]] = {}

        # Scan results cache
        self._results_cache: Dict[str, Any] = {}

    def get_scanner_data(
        self,
        scanner_type: ScannerType,
        symbols: List[str],
        vendor: Optional[DataVendor] = None
    ) -> Dict[str, ScannerDataPackage]:
        """
        Get data for a specific scanner type.

        Args:
            scanner_type: Type of scanner
            symbols: Symbols to scan
            vendor: Specific data vendor (optional)

        Returns:
            Dict mapping symbols to data packages
        """
        config = SCANNER_REQUIREMENTS.get(scanner_type)
        if config is None:
            config = ScannerDataConfig(scanner_type=scanner_type)

        return self.provider.get_batch_data(symbols, config, vendor=vendor)

    def prepare_options_scanner(
        self,
        symbols: List[str],
        scan_type: str = "day",
        vendor: Optional[DataVendor] = None
    ) -> Dict[str, Dict]:
        """
        Prepare data specifically for options scanner.

        Args:
            symbols: Symbols to scan
            scan_type: "day" or "swing"
            vendor: Data vendor

        Returns:
            Scanner-ready data dict
        """
        scanner_type = ScannerType.OPTIONS_DAY if scan_type == "day" else ScannerType.OPTIONS_SWING
        packages = self.get_scanner_data(scanner_type, symbols, vendor)

        result = {}
        for symbol, package in packages.items():
            if package.ohlcv is not None and package.options is not None:
                result[symbol] = {
                    'current_price': package.ohlcv['close'].iloc[-1] if len(package.ohlcv) > 0 else None,
                    'ohlcv': package.ohlcv,
                    'options_chain': package.options,
                    'features': package.features,
                    'volume': package.ohlcv['volume'].iloc[-1] if len(package.ohlcv) > 0 else 0,
                    'volatility': package.features['volatility_20'].iloc[-1] if package.features is not None and 'volatility_20' in package.features else None
                }

        return result

    def prepare_squeeze_scanner(
        self,
        symbols: List[str],
        vendor: Optional[DataVendor] = None
    ) -> Dict[str, Dict]:
        """
        Prepare data for squeeze scanner.

        Args:
            symbols: Symbols to scan
            vendor: Data vendor

        Returns:
            Scanner-ready data dict
        """
        packages = self.get_scanner_data(ScannerType.SQUEEZE, symbols, vendor)

        result = {}
        for symbol, package in packages.items():
            if package.ohlcv is not None:
                # Calculate squeeze-specific metrics
                close = package.ohlcv['close']
                volume = package.ohlcv['volume']

                # Short interest proxy (would need real data)
                avg_volume = volume.rolling(20).mean().iloc[-1] if len(volume) >= 20 else volume.mean()
                volume_surge = volume.iloc[-1] / avg_volume if avg_volume > 0 else 1

                result[symbol] = {
                    'current_price': close.iloc[-1] if len(close) > 0 else None,
                    'ohlcv': package.ohlcv,
                    'options': package.options,
                    'features': package.features,
                    'volume_surge': volume_surge,
                    'short_interest': package.short_data['short_interest'].iloc[-1] if package.short_data is not None else None,
                    'days_to_cover': package.short_data['days_to_cover'].iloc[-1] if package.short_data is not None else None
                }

        return result

    def prepare_momentum_scanner(
        self,
        symbols: List[str],
        vendor: Optional[DataVendor] = None
    ) -> Dict[str, Dict]:
        """
        Prepare data for momentum scanner.

        Args:
            symbols: Symbols to scan
            vendor: Data vendor

        Returns:
            Scanner-ready data dict
        """
        packages = self.get_scanner_data(ScannerType.MOMENTUM, symbols, vendor)

        result = {}
        for symbol, package in packages.items():
            if package.ohlcv is not None and package.features is not None:
                features = package.features

                result[symbol] = {
                    'current_price': package.ohlcv['close'].iloc[-1],
                    'ohlcv': package.ohlcv,
                    'rsi_14': features['rsi_14'].iloc[-1] if 'rsi_14' in features else None,
                    'macd': features['macd'].iloc[-1] if 'macd' in features else None,
                    'macd_signal': features['macd_signal'].iloc[-1] if 'macd_signal' in features else None,
                    'momentum_20': features['momentum_20'].iloc[-1] if 'momentum_20' in features else None,
                    'adx': features['adx'].iloc[-1] if 'adx' in features else None,
                    'trend_regime': features['trend_regime'].iloc[-1] if 'trend_regime' in features else None,
                    'features': features
                }

        return result

    def prepare_0dte_scanner(
        self,
        underlying: str = "SPX",
        vendor: Optional[DataVendor] = None
    ) -> Dict:
        """
        Prepare data for 0DTE options scanner.

        Args:
            underlying: Underlying symbol (SPX, SPY, QQQ)
            vendor: Data vendor

        Returns:
            Scanner-ready data dict
        """
        config = SCANNER_REQUIREMENTS[ScannerType.ZERO_DTE]
        package = self.provider.get_data(underlying, config, vendor=vendor)

        if package.ohlcv is None:
            return {}

        # Filter for 0DTE options
        options_0dte = None
        if package.options is not None:
            today = datetime.now().date()
            if 'expiration' in package.options.columns:
                options_0dte = package.options[
                    package.options['expiration'].dt.date == today
                ]

        current_price = package.ohlcv['close'].iloc[-1] if len(package.ohlcv) > 0 else None

        return {
            'underlying': underlying,
            'current_price': current_price,
            'ohlcv': package.ohlcv,
            'options_chain': options_0dte,
            'all_options': package.options,
            'trades': package.trades,
            'quotes': package.quotes,
            'features': package.features,
            'timestamp': datetime.now()
        }

    def prepare_institutional_scanners(
        self,
        symbols: List[str],
        scanner_types: Optional[List[ScannerType]] = None,
        vendor: Optional[DataVendor] = None
    ) -> Dict[str, Dict]:
        """
        Prepare data for institutional scanners.

        Args:
            symbols: Symbols to analyze
            scanner_types: Which institutional scanners (default: all)
            vendor: Data vendor

        Returns:
            Data dict organized by scanner type
        """
        if scanner_types is None:
            scanner_types = [
                ScannerType.VIX_TRACKER,
                ScannerType.DARK_POOL,
                ScannerType.SMART_MONEY,
                ScannerType.REGIME,
                ScannerType.CROSS_ASSET,
                ScannerType.ORDER_FLOW
            ]

        result = {}

        for scanner_type in scanner_types:
            packages = self.get_scanner_data(scanner_type, symbols, vendor)

            scanner_data = {}
            for symbol, package in packages.items():
                scanner_data[symbol] = {
                    'ohlcv': package.ohlcv,
                    'options': package.options,
                    'trades': package.trades,
                    'quotes': package.quotes,
                    'features': package.features,
                    'dark_pool': package.dark_pool,
                    'metadata': package.metadata
                }

            result[scanner_type.value] = scanner_data

        return result

    def prepare_cross_asset_data(
        self,
        asset_classes: Optional[Dict[str, List[str]]] = None,
        vendor: Optional[DataVendor] = None
    ) -> Dict[str, pd.DataFrame]:
        """
        Prepare data for cross-asset analysis.

        Args:
            asset_classes: Dict mapping asset class to symbols
            vendor: Data vendor

        Returns:
            Dict mapping symbols to OHLCV DataFrames
        """
        if asset_classes is None:
            asset_classes = {
                'equity': ['SPY', 'QQQ', 'IWM', 'EEM'],
                'fixed_income': ['TLT', 'IEF', 'HYG', 'LQD'],
                'commodity': ['GLD', 'SLV', 'USO'],
                'currency': ['UUP', 'FXE', 'FXY'],
                'volatility': ['VIX']
            }

        all_symbols = [s for symbols in asset_classes.values() for s in symbols]
        packages = self.get_scanner_data(ScannerType.CROSS_ASSET, all_symbols, vendor)

        result = {}
        for symbol, package in packages.items():
            if package.ohlcv is not None:
                result[symbol] = package.ohlcv

        return result

    def subscribe_realtime(
        self,
        symbol: str,
        scanner_type: ScannerType,
        callback: Callable
    ):
        """
        Subscribe to real-time data updates.

        Args:
            symbol: Symbol to subscribe to
            scanner_type: Scanner type for data requirements
            callback: Function to call with new data
        """
        key = f"{symbol}_{scanner_type.value}"
        if key not in self._subscriptions:
            self._subscriptions[key] = []
        self._subscriptions[key].append(callback)

    def unsubscribe_realtime(
        self,
        symbol: str,
        scanner_type: ScannerType,
        callback: Optional[Callable] = None
    ):
        """Unsubscribe from real-time updates."""
        key = f"{symbol}_{scanner_type.value}"
        if callback:
            if key in self._subscriptions:
                self._subscriptions[key] = [
                    cb for cb in self._subscriptions[key] if cb != callback
                ]
        else:
            self._subscriptions.pop(key, None)

    def get_watchlist_data(
        self,
        watchlist: List[str],
        scanner_type: ScannerType = ScannerType.MOMENTUM,
        vendor: Optional[DataVendor] = None
    ) -> pd.DataFrame:
        """
        Get summary data for watchlist.

        Args:
            watchlist: List of symbols
            scanner_type: Type of analysis
            vendor: Data vendor

        Returns:
            DataFrame with summary for each symbol
        """
        packages = self.get_scanner_data(scanner_type, watchlist, vendor)

        records = []
        for symbol, package in packages.items():
            if package.ohlcv is None or len(package.ohlcv) == 0:
                continue

            ohlcv = package.ohlcv
            features = package.features

            record = {
                'symbol': symbol,
                'price': ohlcv['close'].iloc[-1],
                'change_1d': ((ohlcv['close'].iloc[-1] / ohlcv['close'].iloc[-2]) - 1) * 100 if len(ohlcv) > 1 else 0,
                'volume': ohlcv['volume'].iloc[-1],
                'volume_ratio': ohlcv['volume'].iloc[-1] / ohlcv['volume'].rolling(20).mean().iloc[-1] if len(ohlcv) >= 20 else 1
            }

            if features is not None:
                if 'rsi_14' in features:
                    record['rsi'] = features['rsi_14'].iloc[-1]
                if 'macd' in features:
                    record['macd'] = features['macd'].iloc[-1]
                if 'volatility_20' in features:
                    record['volatility'] = features['volatility_20'].iloc[-1]
                if 'trend_regime' in features:
                    record['trend'] = features['trend_regime'].iloc[-1]

            records.append(record)

        return pd.DataFrame(records)


# Factory functions
def create_scanner_data_provider(
    data_manager: Optional[UniversalDataManager] = None
) -> UniversalScannerDataProvider:
    """Create scanner data provider."""
    return UniversalScannerDataProvider(data_manager)


def create_scanner_integration(
    data_manager: Optional[UniversalDataManager] = None,
    ml_pipeline: Optional[MLDataPipeline] = None
) -> ScannerDataIntegration:
    """Create scanner data integration."""
    return ScannerDataIntegration(data_manager, ml_pipeline)


# Convenience function to get scanner requirements
def get_scanner_requirements(scanner_type: ScannerType) -> ScannerDataConfig:
    """Get data requirements for scanner type."""
    return SCANNER_REQUIREMENTS.get(
        scanner_type,
        ScannerDataConfig(scanner_type=scanner_type)
    )


# Example usage
if __name__ == "__main__":
    print("="*60)
    print("SCANNER DATA INTEGRATION - TEST MODE")
    print("="*60)

    # Create integration
    integration = create_scanner_integration()

    print("\nScanner Data Requirements:")
    print("-" * 40)

    for scanner_type, config in SCANNER_REQUIREMENTS.items():
        print(f"\n{scanner_type.value}:")
        print(f"  OHLCV: {config.requires_ohlcv}")
        print(f"  Options: {config.requires_options}")
        print(f"  Trades: {config.requires_trades}")
        print(f"  Quotes: {config.requires_quotes}")
        print(f"  Order Book: {config.requires_order_book}")
        print(f"  Lookback: {config.lookback_days} days")
        print(f"  Timeframe: {config.timeframe}")

    print("\n" + "="*60)
    print("Usage Example")
    print("="*60)
    print("""
from src.data import create_data_manager, create_polygon_adapter, DataVendor
from src.scanner.data_integration import create_scanner_integration, ScannerType

# Setup
manager = create_data_manager()
manager.register_adapter(DataVendor.POLYGON, create_polygon_adapter("API_KEY"))

integration = create_scanner_integration(manager)

# Options Scanner
options_data = integration.prepare_options_scanner(
    symbols=['AAPL', 'TSLA', 'NVDA'],
    scan_type='day'
)

# Momentum Scanner
momentum_data = integration.prepare_momentum_scanner(
    symbols=['SPY', 'QQQ', 'IWM']
)

# 0DTE Scanner
spx_0dte = integration.prepare_0dte_scanner(underlying='SPX')

# Institutional Scanners
inst_data = integration.prepare_institutional_scanners(
    symbols=['AAPL', 'MSFT'],
    scanner_types=[ScannerType.VIX_TRACKER, ScannerType.DARK_POOL]
)

# Cross-Asset Analysis
cross_asset = integration.prepare_cross_asset_data()

# Watchlist Summary
watchlist_df = integration.get_watchlist_data(
    watchlist=['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA']
)
    """)

    print(f"\n{'='*60}")
    print("SCANNER DATA INTEGRATION - READY FOR PRODUCTION")
    print('='*60)
