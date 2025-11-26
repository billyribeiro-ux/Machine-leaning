"""
Revolution Alpha Engine - Universal Data Module

Multi-vendor data adapter system supporting:
- Polygon.io
- Alpaca Markets
- Interactive Brokers (IBKR)
- TD Ameritrade / Schwab
- Tradier
- Yahoo Finance
- Alpha Vantage
- Finnhub
- Quandl / Nasdaq Data Link
- CBOE (options/VIX data)
- IEX Cloud
- Tiingo
- EOD Historical Data
- Custom CSV/Parquet files

Author: Revolution Alpha Engine
"""

from .adapters import (
    # Enums
    DataVendor,
    DataType,

    # Standard schemas
    StandardOHLCV,
    StandardTrade,
    StandardQuote,
    StandardOption,
    StandardOptionsFlow,
    StandardOrderBook,

    # Base adapter
    BaseDataAdapter,

    # Vendor adapters
    PolygonAdapter,
    AlpacaAdapter,
    IBKRAdapter,
    TDAmeritradeAdapter,
    YahooAdapter,
    CBOEAdapter,
    CSVAdapter,

    # Managers
    UniversalDataManager,
    ScannerDataPreparer,

    # Factory functions
    create_data_manager,
    create_scanner_data_preparer,
    create_polygon_adapter,
    create_alpaca_adapter,
    create_ibkr_adapter,
    create_yahoo_adapter,
    create_cboe_adapter,
    create_csv_adapter,
)


__all__ = [
    # Enums
    'DataVendor',
    'DataType',

    # Standard schemas
    'StandardOHLCV',
    'StandardTrade',
    'StandardQuote',
    'StandardOption',
    'StandardOptionsFlow',
    'StandardOrderBook',

    # Base adapter
    'BaseDataAdapter',

    # Vendor adapters
    'PolygonAdapter',
    'AlpacaAdapter',
    'IBKRAdapter',
    'TDAmeritradeAdapter',
    'YahooAdapter',
    'CBOEAdapter',
    'CSVAdapter',

    # Managers
    'UniversalDataManager',
    'ScannerDataPreparer',

    # Factory functions
    'create_data_manager',
    'create_scanner_data_preparer',
    'create_polygon_adapter',
    'create_alpaca_adapter',
    'create_ibkr_adapter',
    'create_yahoo_adapter',
    'create_cboe_adapter',
    'create_csv_adapter',
]
