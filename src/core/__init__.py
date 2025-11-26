"""
Revolution Alpha Engine - Core Infrastructure

High-performance core utilities for the entire trading system.
"""

from .performance import (
    memoize,
    async_memoize,
    LRUCache,
    TTLCache,
    vectorize_dataframe,
    parallel_apply,
    JITCompiler
)

from .config import (
    Config,
    TradingConfig,
    RiskConfig,
    ScannerConfig,
    MLConfig,
    load_config,
    save_config
)

from .validation import (
    validate_dataframe,
    validate_options_chain,
    validate_price_data,
    validate_trade_signal,
    ValidationError,
    DataQualityChecker
)

from .logging import (
    setup_logging,
    get_logger,
    TradeLogger,
    PerformanceLogger,
    AuditLogger
)

from .exceptions import (
    RevolutionError,
    DataError,
    ConfigError,
    TradingError,
    ValidationError,
    ConnectionError
)

__all__ = [
    # Performance
    'memoize', 'async_memoize', 'LRUCache', 'TTLCache',
    'vectorize_dataframe', 'parallel_apply', 'JITCompiler',
    # Config
    'Config', 'TradingConfig', 'RiskConfig', 'ScannerConfig', 'MLConfig',
    'load_config', 'save_config',
    # Validation
    'validate_dataframe', 'validate_options_chain', 'validate_price_data',
    'validate_trade_signal', 'ValidationError', 'DataQualityChecker',
    # Logging
    'setup_logging', 'get_logger', 'TradeLogger', 'PerformanceLogger', 'AuditLogger',
    # Exceptions
    'RevolutionError', 'DataError', 'ConfigError', 'TradingError', 'ConnectionError'
]
