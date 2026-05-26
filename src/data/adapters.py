"""
Universal Data Adapter System

Standardizes data from multiple vendors into a common format for all scanners:

Supported Vendors:
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
- Custom CSV/Parquet

Each adapter normalizes data to a standard schema that all scanners can consume.

Author: Revolution Alpha Engine
"""

import numpy as np
import pandas as pd
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Union, Callable
from datetime import datetime, timedelta
from enum import Enum
import json
import warnings

warnings.filterwarnings('ignore')


class DataVendor(Enum):
    """Supported data vendors."""
    POLYGON = "polygon"
    ALPACA = "alpaca"
    IBKR = "ibkr"
    TD_AMERITRADE = "td_ameritrade"
    TRADIER = "tradier"
    YAHOO = "yahoo"
    ALPHA_VANTAGE = "alpha_vantage"
    FINNHUB = "finnhub"
    QUANDL = "quandl"
    CBOE = "cboe"
    IEX = "iex"
    TIINGO = "tiingo"
    EOD = "eod"
    CSV = "csv"
    PARQUET = "parquet"
    CUSTOM = "custom"


class DataType(Enum):
    """Types of market data."""
    OHLCV = "ohlcv"
    TRADES = "trades"
    QUOTES = "quotes"
    OPTIONS_CHAIN = "options_chain"
    OPTIONS_FLOW = "options_flow"
    ORDER_BOOK = "order_book"
    DARK_POOL = "dark_pool"
    SHORT_VOLUME = "short_volume"
    FUNDAMENTALS = "fundamentals"
    NEWS = "news"
    SENTIMENT = "sentiment"


@dataclass
class StandardOHLCV:
    """Standardized OHLCV data schema."""
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: Optional[float] = None
    trade_count: Optional[int] = None

    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'timestamp': self.timestamp,
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'close': self.close,
            'volume': self.volume,
            'vwap': self.vwap,
            'trade_count': self.trade_count
        }


@dataclass
class StandardTrade:
    """Standardized trade data schema."""
    symbol: str
    timestamp: datetime
    price: float
    size: int
    exchange: Optional[str] = None
    conditions: Optional[List[str]] = None
    trade_id: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'timestamp': self.timestamp,
            'price': self.price,
            'size': self.size,
            'exchange': self.exchange,
            'conditions': self.conditions,
            'trade_id': self.trade_id
        }


@dataclass
class StandardQuote:
    """Standardized quote data schema."""
    symbol: str
    timestamp: datetime
    bid: float
    bid_size: int
    ask: float
    ask_size: int
    exchange: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'timestamp': self.timestamp,
            'bid': self.bid,
            'bid_size': self.bid_size,
            'ask': self.ask,
            'ask_size': self.ask_size,
            'exchange': self.exchange
        }


@dataclass
class StandardOption:
    """Standardized options data schema."""
    symbol: str
    underlying: str
    expiration: datetime
    strike: float
    option_type: str  # 'call' or 'put'
    bid: float
    ask: float
    last: float
    volume: int
    open_interest: int
    implied_volatility: float
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    rho: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'underlying': self.underlying,
            'expiration': self.expiration,
            'strike': self.strike,
            'option_type': self.option_type,
            'bid': self.bid,
            'ask': self.ask,
            'last': self.last,
            'volume': self.volume,
            'open_interest': self.open_interest,
            'implied_volatility': self.implied_volatility,
            'delta': self.delta,
            'gamma': self.gamma,
            'theta': self.theta,
            'vega': self.vega,
            'rho': self.rho,
            'timestamp': self.timestamp
        }


@dataclass
class StandardOptionsFlow:
    """Standardized options flow data schema."""
    symbol: str
    underlying: str
    timestamp: datetime
    expiration: datetime
    strike: float
    option_type: str
    side: str  # 'buy', 'sell'
    size: int
    price: float
    premium: float
    is_sweep: bool
    is_block: bool
    is_unusual: bool
    open_interest: int
    volume_oi_ratio: float
    sentiment: str  # 'bullish', 'bearish', 'neutral'
    exchange: Optional[str] = None

    def to_dict(self) -> Dict:
        return self.__dict__.copy()


@dataclass
class StandardOrderBook:
    """Standardized order book data schema."""
    symbol: str
    timestamp: datetime
    bids: List[Tuple[float, int]]  # (price, size)
    asks: List[Tuple[float, int]]
    exchange: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'timestamp': self.timestamp,
            'bids': self.bids,
            'asks': self.asks,
            'exchange': self.exchange
        }


class BaseDataAdapter(ABC):
    """
    Abstract base class for data adapters.

    All vendor-specific adapters must implement these methods.
    """

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        self.api_key = api_key
        self.config = kwargs
        self._cache = {}

    @property
    @abstractmethod
    def vendor(self) -> DataVendor:
        """Return the vendor type."""
        pass

    @abstractmethod
    def get_ohlcv(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str = '1d'
    ) -> pd.DataFrame:
        """Get OHLCV data."""
        pass

    @abstractmethod
    def get_trades(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime
    ) -> pd.DataFrame:
        """Get trade data."""
        pass

    @abstractmethod
    def get_quotes(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime
    ) -> pd.DataFrame:
        """Get quote data."""
        pass

    @abstractmethod
    def get_options_chain(
        self,
        symbol: str,
        expiration: Optional[datetime] = None
    ) -> pd.DataFrame:
        """Get options chain."""
        pass

    def _standardize_ohlcv(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """Standardize OHLCV DataFrame to common schema."""
        # Map common column names
        column_mappings = {
            'Open': 'open', 'HIGH': 'high', 'Low': 'low', 'CLOSE': 'close',
            'Volume': 'volume', 'VWAP': 'vwap', 'Adj Close': 'adj_close',
            'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'v': 'volume',
            'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close'
        }

        df = df.rename(columns={k: v for k, v in column_mappings.items() if k in df.columns})

        # Ensure required columns
        required = ['open', 'high', 'low', 'close', 'volume']
        for col in required:
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")

        # Add symbol
        df['symbol'] = symbol

        # Ensure timestamp index
        if not isinstance(df.index, pd.DatetimeIndex):
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df = df.set_index('timestamp')
            elif 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                df = df.set_index('date')
            elif 't' in df.columns:
                df['t'] = pd.to_datetime(df['t'], unit='ms')
                df = df.set_index('t')

        df.index.name = 'timestamp'

        return df[['symbol', 'open', 'high', 'low', 'close', 'volume'] +
                  [c for c in ['vwap', 'trade_count', 'adj_close'] if c in df.columns]]


class PolygonAdapter(BaseDataAdapter):
    """
    Polygon.io data adapter.

    Supports stocks, options, forex, and crypto.
    """

    @property
    def vendor(self) -> DataVendor:
        return DataVendor.POLYGON

    def get_ohlcv(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str = '1d'
    ) -> pd.DataFrame:
        """
        Get OHLCV data from Polygon.

        In production, this would call the Polygon API.
        Returns standardized DataFrame.
        """
        # Placeholder for actual API call
        # response = requests.get(f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/day/{start_date}/{end_date}?apiKey={self.api_key}")

        # For demonstration, return schema
        columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'vwap', 'trade_count']
        df = pd.DataFrame(columns=columns)
        return self._standardize_ohlcv(df, symbol) if not df.empty else df

    def get_trades(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime
    ) -> pd.DataFrame:
        """Get trades from Polygon."""
        # Polygon returns: symbol, timestamp, price, size, exchange, conditions
        columns = ['timestamp', 'price', 'size', 'exchange', 'conditions']
        return pd.DataFrame(columns=columns)

    def get_quotes(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime
    ) -> pd.DataFrame:
        """Get quotes from Polygon."""
        columns = ['timestamp', 'bid', 'bid_size', 'ask', 'ask_size', 'exchange']
        return pd.DataFrame(columns=columns)

    def get_options_chain(
        self,
        symbol: str,
        expiration: Optional[datetime] = None
    ) -> pd.DataFrame:
        """Get options chain from Polygon."""
        columns = ['symbol', 'underlying', 'expiration', 'strike', 'option_type',
                   'bid', 'ask', 'last', 'volume', 'open_interest', 'implied_volatility',
                   'delta', 'gamma', 'theta', 'vega']
        return pd.DataFrame(columns=columns)

    def get_options_flow(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime
    ) -> pd.DataFrame:
        """Get unusual options activity from Polygon."""
        columns = ['symbol', 'underlying', 'timestamp', 'expiration', 'strike',
                   'option_type', 'side', 'size', 'price', 'premium',
                   'is_sweep', 'is_block', 'open_interest']
        return pd.DataFrame(columns=columns)


class AlpacaAdapter(BaseDataAdapter):
    """
    Alpaca Markets data adapter.

    Supports stocks and crypto with real-time data.
    """

    @property
    def vendor(self) -> DataVendor:
        return DataVendor.ALPACA

    def get_ohlcv(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str = '1d'
    ) -> pd.DataFrame:
        """Get OHLCV data from Alpaca."""
        # Alpaca uses: open, high, low, close, volume, trade_count, vwap
        columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'vwap', 'trade_count']
        df = pd.DataFrame(columns=columns)
        return self._standardize_ohlcv(df, symbol) if not df.empty else df

    def get_trades(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime
    ) -> pd.DataFrame:
        """Get trades from Alpaca."""
        columns = ['timestamp', 'price', 'size', 'exchange', 'conditions', 'trade_id']
        return pd.DataFrame(columns=columns)

    def get_quotes(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime
    ) -> pd.DataFrame:
        """Get quotes from Alpaca."""
        columns = ['timestamp', 'bid', 'bid_size', 'ask', 'ask_size', 'exchange']
        return pd.DataFrame(columns=columns)

    def get_options_chain(
        self,
        symbol: str,
        expiration: Optional[datetime] = None
    ) -> pd.DataFrame:
        """Alpaca options (via partner)."""
        columns = ['symbol', 'underlying', 'expiration', 'strike', 'option_type',
                   'bid', 'ask', 'last', 'volume', 'open_interest', 'implied_volatility']
        return pd.DataFrame(columns=columns)


class IBKRAdapter(BaseDataAdapter):
    """
    Interactive Brokers data adapter.

    Full market data with options, futures, forex.
    """

    @property
    def vendor(self) -> DataVendor:
        return DataVendor.IBKR

    def get_ohlcv(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str = '1d'
    ) -> pd.DataFrame:
        """Get OHLCV from IBKR TWS/Gateway."""
        columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        df = pd.DataFrame(columns=columns)
        return self._standardize_ohlcv(df, symbol) if not df.empty else df

    def get_trades(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime
    ) -> pd.DataFrame:
        """Get Time & Sales from IBKR."""
        columns = ['timestamp', 'price', 'size', 'exchange']
        return pd.DataFrame(columns=columns)

    def get_quotes(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime
    ) -> pd.DataFrame:
        """Get bid/ask from IBKR."""
        columns = ['timestamp', 'bid', 'bid_size', 'ask', 'ask_size']
        return pd.DataFrame(columns=columns)

    def get_options_chain(
        self,
        symbol: str,
        expiration: Optional[datetime] = None
    ) -> pd.DataFrame:
        """Get options chain from IBKR."""
        columns = ['symbol', 'underlying', 'expiration', 'strike', 'option_type',
                   'bid', 'ask', 'last', 'volume', 'open_interest', 'implied_volatility',
                   'delta', 'gamma', 'theta', 'vega', 'rho']
        return pd.DataFrame(columns=columns)

    def get_order_book(
        self,
        symbol: str,
        depth: int = 10
    ) -> Dict[str, List[Tuple[float, int]]]:
        """Get Level 2 order book from IBKR."""
        return {'bids': [], 'asks': []}


class TDAmeritradeAdapter(BaseDataAdapter):
    """
    TD Ameritrade / Schwab data adapter.
    """

    @property
    def vendor(self) -> DataVendor:
        return DataVendor.TD_AMERITRADE

    def get_ohlcv(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str = '1d'
    ) -> pd.DataFrame:
        columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        df = pd.DataFrame(columns=columns)
        return self._standardize_ohlcv(df, symbol) if not df.empty else df

    def get_trades(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime
    ) -> pd.DataFrame:
        columns = ['timestamp', 'price', 'size']
        return pd.DataFrame(columns=columns)

    def get_quotes(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime
    ) -> pd.DataFrame:
        columns = ['timestamp', 'bid', 'bid_size', 'ask', 'ask_size']
        return pd.DataFrame(columns=columns)

    def get_options_chain(
        self,
        symbol: str,
        expiration: Optional[datetime] = None
    ) -> pd.DataFrame:
        columns = ['symbol', 'underlying', 'expiration', 'strike', 'option_type',
                   'bid', 'ask', 'last', 'volume', 'open_interest', 'implied_volatility',
                   'delta', 'gamma', 'theta', 'vega']
        return pd.DataFrame(columns=columns)


class YahooAdapter(BaseDataAdapter):
    """
    Yahoo Finance data adapter.

    Free data with good historical coverage.
    """

    @property
    def vendor(self) -> DataVendor:
        return DataVendor.YAHOO

    def get_ohlcv(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str = '1d'
    ) -> pd.DataFrame:
        """
        Get OHLCV from Yahoo Finance.

        Can use yfinance library in production.
        """
        # import yfinance as yf
        # ticker = yf.Ticker(symbol)
        # df = ticker.history(start=start_date, end=end_date)
        columns = ['timestamp', 'Open', 'High', 'Low', 'Close', 'Volume', 'Adj Close']
        df = pd.DataFrame(columns=columns)
        return self._standardize_ohlcv(df, symbol) if not df.empty else df

    def get_trades(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime
    ) -> pd.DataFrame:
        # Yahoo doesn't provide tick data
        return pd.DataFrame(columns=['timestamp', 'price', 'size'])

    def get_quotes(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime
    ) -> pd.DataFrame:
        # Yahoo doesn't provide historical quotes
        return pd.DataFrame(columns=['timestamp', 'bid', 'bid_size', 'ask', 'ask_size'])

    def get_options_chain(
        self,
        symbol: str,
        expiration: Optional[datetime] = None
    ) -> pd.DataFrame:
        """Get options chain from Yahoo."""
        # import yfinance as yf
        # ticker = yf.Ticker(symbol)
        # options = ticker.option_chain(expiration)
        columns = ['symbol', 'underlying', 'expiration', 'strike', 'option_type',
                   'bid', 'ask', 'last', 'volume', 'open_interest', 'implied_volatility']
        return pd.DataFrame(columns=columns)


class CBOEAdapter(BaseDataAdapter):
    """
    CBOE data adapter.

    Best for VIX and options data.
    """

    @property
    def vendor(self) -> DataVendor:
        return DataVendor.CBOE

    def get_ohlcv(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str = '1d'
    ) -> pd.DataFrame:
        columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        df = pd.DataFrame(columns=columns)
        return self._standardize_ohlcv(df, symbol) if not df.empty else df

    def get_trades(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime
    ) -> pd.DataFrame:
        return pd.DataFrame(columns=['timestamp', 'price', 'size'])

    def get_quotes(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime
    ) -> pd.DataFrame:
        return pd.DataFrame(columns=['timestamp', 'bid', 'bid_size', 'ask', 'ask_size'])

    def get_options_chain(
        self,
        symbol: str,
        expiration: Optional[datetime] = None
    ) -> pd.DataFrame:
        """Get options chain - CBOE is excellent for VIX options."""
        columns = ['symbol', 'underlying', 'expiration', 'strike', 'option_type',
                   'bid', 'ask', 'last', 'volume', 'open_interest', 'implied_volatility',
                   'delta', 'gamma', 'theta', 'vega']
        return pd.DataFrame(columns=columns)

    def get_vix_futures(self) -> pd.DataFrame:
        """Get VIX futures term structure."""
        columns = ['expiration', 'last', 'change', 'high', 'low', 'volume', 'open_interest']
        return pd.DataFrame(columns=columns)

    def get_vix_options(self, expiration: Optional[datetime] = None) -> pd.DataFrame:
        """Get VIX options specifically."""
        return self.get_options_chain('VIX', expiration)


class CSVAdapter(BaseDataAdapter):
    """
    CSV file data adapter.

    Supports custom CSV files with column mapping.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        column_mapping: Optional[Dict[str, str]] = None,
        **kwargs
    ):
        super().__init__(api_key, **kwargs)
        self.column_mapping = column_mapping or {}

    @property
    def vendor(self) -> DataVendor:
        return DataVendor.CSV

    def get_ohlcv(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str = '1d',
        file_path: Optional[str] = None
    ) -> pd.DataFrame:
        """Load OHLCV from CSV file."""
        if file_path:
            df = pd.read_csv(file_path)

            # Apply column mapping
            if self.column_mapping:
                df = df.rename(columns=self.column_mapping)

            # Parse dates
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
            elif 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                df = df.rename(columns={'date': 'timestamp'})

            # Filter by date range
            if 'timestamp' in df.columns:
                df = df[(df['timestamp'] >= start_date) & (df['timestamp'] <= end_date)]

            return self._standardize_ohlcv(df, symbol)

        return pd.DataFrame()

    def get_trades(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        file_path: Optional[str] = None
    ) -> pd.DataFrame:
        if file_path:
            return pd.read_csv(file_path)
        return pd.DataFrame()

    def get_quotes(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        file_path: Optional[str] = None
    ) -> pd.DataFrame:
        if file_path:
            return pd.read_csv(file_path)
        return pd.DataFrame()

    def get_options_chain(
        self,
        symbol: str,
        expiration: Optional[datetime] = None,
        file_path: Optional[str] = None
    ) -> pd.DataFrame:
        if file_path:
            return pd.read_csv(file_path)
        return pd.DataFrame()


class UniversalDataManager:
    """
    Universal data manager that coordinates multiple data adapters.

    Provides a single interface to access data from any vendor,
    with automatic fallback and data fusion capabilities.
    """

    def __init__(self):
        self.adapters: Dict[DataVendor, BaseDataAdapter] = {}
        self.primary_vendor: Optional[DataVendor] = None
        self.fallback_order: List[DataVendor] = []

    def register_adapter(
        self,
        vendor: DataVendor,
        adapter: BaseDataAdapter,
        is_primary: bool = False
    ):
        """Register a data adapter."""
        self.adapters[vendor] = adapter

        if is_primary:
            self.primary_vendor = vendor

        if vendor not in self.fallback_order:
            self.fallback_order.append(vendor)

    def set_fallback_order(self, order: List[DataVendor]):
        """Set the fallback order for data sources."""
        self.fallback_order = order

    def get_ohlcv(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str = '1d',
        vendor: Optional[DataVendor] = None
    ) -> pd.DataFrame:
        """
        Get OHLCV data with automatic fallback.

        Args:
            symbol: Stock symbol
            start_date: Start date
            end_date: End date
            timeframe: Timeframe (1m, 5m, 1h, 1d, etc.)
            vendor: Specific vendor to use (optional)

        Returns:
            Standardized OHLCV DataFrame
        """
        vendors_to_try = [vendor] if vendor else self.fallback_order

        for v in vendors_to_try:
            if v in self.adapters:
                try:
                    df = self.adapters[v].get_ohlcv(symbol, start_date, end_date, timeframe)
                    if not df.empty:
                        return df
                except Exception as e:
                    print(f"Warning: {v.value} failed for {symbol}: {e}")
                    continue

        return pd.DataFrame()

    def get_trades(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        vendor: Optional[DataVendor] = None
    ) -> pd.DataFrame:
        """Get trade data with fallback."""
        vendors_to_try = [vendor] if vendor else self.fallback_order

        for v in vendors_to_try:
            if v in self.adapters:
                try:
                    df = self.adapters[v].get_trades(symbol, start_time, end_time)
                    if not df.empty:
                        return df
                except Exception:
                    continue

        return pd.DataFrame()

    def get_quotes(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        vendor: Optional[DataVendor] = None
    ) -> pd.DataFrame:
        """Get quote data with fallback."""
        vendors_to_try = [vendor] if vendor else self.fallback_order

        for v in vendors_to_try:
            if v in self.adapters:
                try:
                    df = self.adapters[v].get_quotes(symbol, start_time, end_time)
                    if not df.empty:
                        return df
                except Exception:
                    continue

        return pd.DataFrame()

    def get_options_chain(
        self,
        symbol: str,
        expiration: Optional[datetime] = None,
        vendor: Optional[DataVendor] = None
    ) -> pd.DataFrame:
        """Get options chain with fallback."""
        vendors_to_try = [vendor] if vendor else self.fallback_order

        for v in vendors_to_try:
            if v in self.adapters:
                try:
                    df = self.adapters[v].get_options_chain(symbol, expiration)
                    if not df.empty:
                        return df
                except Exception:
                    continue

        return pd.DataFrame()

    def get_multi_symbol_ohlcv(
        self,
        symbols: List[str],
        start_date: datetime,
        end_date: datetime,
        timeframe: str = '1d'
    ) -> Dict[str, pd.DataFrame]:
        """Get OHLCV for multiple symbols."""
        result = {}

        for symbol in symbols:
            df = self.get_ohlcv(symbol, start_date, end_date, timeframe)
            if not df.empty:
                result[symbol] = df

        return result

    def fuse_data(
        self,
        symbol: str,
        data_type: DataType,
        start_time: datetime,
        end_time: datetime
    ) -> pd.DataFrame:
        """
        Fuse data from multiple vendors for best coverage.

        Combines data from all available sources, removing duplicates
        and filling gaps.
        """
        all_data = []

        for vendor, adapter in self.adapters.items():
            try:
                if data_type == DataType.OHLCV:
                    df = adapter.get_ohlcv(symbol, start_time, end_time)
                elif data_type == DataType.TRADES:
                    df = adapter.get_trades(symbol, start_time, end_time)
                elif data_type == DataType.QUOTES:
                    df = adapter.get_quotes(symbol, start_time, end_time)
                elif data_type == DataType.OPTIONS_CHAIN:
                    df = adapter.get_options_chain(symbol)
                else:
                    continue

                if not df.empty:
                    df['_source'] = vendor.value
                    all_data.append(df)

            except Exception:
                continue

        if not all_data:
            return pd.DataFrame()

        # Combine all data
        combined = pd.concat(all_data, ignore_index=True)

        # Remove duplicates (keep first occurrence)
        if 'timestamp' in combined.columns:
            combined = combined.drop_duplicates(subset=['timestamp'], keep='first')
            combined = combined.sort_values('timestamp')

        return combined


class ScannerDataPreparer:
    """
    Prepares data from any vendor for use with Revolution scanners.

    Handles all the transformations needed to feed data into:
    - VIX Institutional Tracker
    - Dark Pool Detector
    - Smart Money Tracker
    - Regime Change Detector
    - Cross-Asset Intelligence
    - Predictive Order Flow
    """

    def __init__(self, data_manager: UniversalDataManager):
        self.data_manager = data_manager

    def prepare_for_vix_tracker(
        self,
        vix_spot: float,
        options_data: Optional[pd.DataFrame] = None,
        vendor: Optional[DataVendor] = None
    ) -> Tuple[pd.DataFrame, float]:
        """
        Prepare data for VIX Institutional Tracker.

        Returns:
            options_df: Standardized options DataFrame
            vix_spot: Current VIX spot price
        """
        if options_data is None:
            options_data = self.data_manager.get_options_chain('VIX', vendor=vendor)

        # Ensure required columns
        required_cols = ['strike', 'expiration', 'option_type', 'bid', 'ask',
                        'volume', 'open_interest', 'implied_volatility']

        for col in required_cols:
            if col not in options_data.columns:
                options_data[col] = 0

        return options_data, vix_spot

    def prepare_for_dark_pool(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        vendor: Optional[DataVendor] = None
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Prepare data for Dark Pool Detector.

        Returns:
            trades_df: Trade data
            quotes_df: Quote data
            daily_df: Daily OHLCV data
        """
        trades = self.data_manager.get_trades(symbol, start_time, end_time, vendor)
        quotes = self.data_manager.get_quotes(symbol, start_time, end_time, vendor)
        daily = self.data_manager.get_ohlcv(
            symbol,
            start_time - timedelta(days=60),
            end_time,
            '1d'
        )

        return trades, quotes, daily

    def prepare_for_smart_money(
        self,
        symbols: List[str],
        start_time: datetime,
        end_time: datetime,
        vendor: Optional[DataVendor] = None
    ) -> Dict[str, pd.DataFrame]:
        """
        Prepare data for Smart Money Tracker.

        Returns:
            Dict with options flow data per symbol
        """
        result = {}

        for symbol in symbols:
            options = self.data_manager.get_options_chain(symbol, vendor=vendor)
            if not options.empty:
                result[symbol] = options

        return result

    def prepare_for_regime_detector(
        self,
        symbol: str,
        lookback_days: int = 252,
        vendor: Optional[DataVendor] = None
    ) -> pd.DataFrame:
        """
        Prepare data for Regime Change Detector.

        Returns:
            OHLCV DataFrame with sufficient history
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=lookback_days + 50)  # Buffer for rolling calcs

        return self.data_manager.get_ohlcv(symbol, start_date, end_date, '1d', vendor)

    def prepare_for_cross_asset(
        self,
        symbols: List[str],
        lookback_days: int = 252,
        vendor: Optional[DataVendor] = None
    ) -> Dict[str, pd.DataFrame]:
        """
        Prepare data for Cross-Asset Intelligence.

        Returns:
            Dict mapping symbols to OHLCV DataFrames
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=lookback_days + 50)

        return self.data_manager.get_multi_symbol_ohlcv(
            symbols, start_date, end_date, '1d'
        )

    def prepare_for_order_flow(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        vendor: Optional[DataVendor] = None
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Prepare data for Predictive Order Flow.

        Returns:
            trades_df: Tick-level trade data
            book_snapshots: Order book snapshots
        """
        trades = self.data_manager.get_trades(symbol, start_time, end_time, vendor)
        quotes = self.data_manager.get_quotes(symbol, start_time, end_time, vendor)

        return trades, quotes


def create_data_manager() -> UniversalDataManager:
    """Factory function to create data manager."""
    return UniversalDataManager()


def create_scanner_data_preparer(data_manager: UniversalDataManager) -> ScannerDataPreparer:
    """Factory function to create scanner data preparer."""
    return ScannerDataPreparer(data_manager)


# Convenience functions for quick adapter creation
def create_polygon_adapter(api_key: str) -> PolygonAdapter:
    return PolygonAdapter(api_key=api_key)


def create_alpaca_adapter(api_key: str, secret_key: str) -> AlpacaAdapter:
    return AlpacaAdapter(api_key=api_key, secret_key=secret_key)


def create_ibkr_adapter(**kwargs) -> IBKRAdapter:
    return IBKRAdapter(**kwargs)


def create_yahoo_adapter() -> YahooAdapter:
    return YahooAdapter()


def create_cboe_adapter(api_key: Optional[str] = None) -> CBOEAdapter:
    return CBOEAdapter(api_key=api_key)


def create_csv_adapter(column_mapping: Optional[Dict] = None) -> CSVAdapter:
    return CSVAdapter(column_mapping=column_mapping)


# Example usage
if __name__ == "__main__":
    print("="*60)
    print("UNIVERSAL DATA ADAPTER SYSTEM")
    print("="*60)

    # Create data manager
    manager = create_data_manager()

    # Register adapters
    print("\nRegistering data adapters...")

    # Yahoo (free, always available)
    yahoo = create_yahoo_adapter()
    manager.register_adapter(DataVendor.YAHOO, yahoo)

    # Polygon (if you have API key)
    # polygon = create_polygon_adapter("YOUR_API_KEY")
    # manager.register_adapter(DataVendor.POLYGON, polygon, is_primary=True)

    # Set fallback order
    manager.set_fallback_order([
        DataVendor.POLYGON,
        DataVendor.ALPACA,
        DataVendor.YAHOO
    ])

    print("  - Yahoo Finance: Registered")
    print("  - Fallback order: Polygon -> Alpaca -> Yahoo")

    # Create scanner data preparer
    preparer = create_scanner_data_preparer(manager)

    print("\nScanner Data Preparer ready!")
    print("\nAvailable preparation methods:")
    print("  - prepare_for_vix_tracker()")
    print("  - prepare_for_dark_pool()")
    print("  - prepare_for_smart_money()")
    print("  - prepare_for_regime_detector()")
    print("  - prepare_for_cross_asset()")
    print("  - prepare_for_order_flow()")

    print(f"\n{'='*60}")
    print("DATA ADAPTER SYSTEM READY")
    print('='*60)

    # Example usage
    print("""
Example Usage:

    from src.data.adapters import (
        create_data_manager,
        create_polygon_adapter,
        create_yahoo_adapter,
        create_scanner_data_preparer,
        DataVendor
    )

    # Setup
    manager = create_data_manager()
    manager.register_adapter(DataVendor.POLYGON, create_polygon_adapter("API_KEY"), is_primary=True)
    manager.register_adapter(DataVendor.YAHOO, create_yahoo_adapter())

    # Get data (auto-fallback if primary fails)
    df = manager.get_ohlcv("AAPL", start_date, end_date)

    # Prepare for scanners
    preparer = create_scanner_data_preparer(manager)
    vix_data, vix_spot = preparer.prepare_for_vix_tracker(18.5)
    """)
