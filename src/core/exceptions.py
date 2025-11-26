"""
Revolution Alpha Engine - Custom Exceptions

Hierarchical exception system for comprehensive error handling.
"""

from typing import Optional, Any, Dict


class RevolutionError(Exception):
    """Base exception for all Revolution Alpha Engine errors."""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.code = code or self.__class__.__name__
        self.details = details or {}
        super().__init__(self.message)

    def __str__(self):
        if self.details:
            return f"[{self.code}] {self.message} | Details: {self.details}"
        return f"[{self.code}] {self.message}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary."""
        return {
            'error': self.code,
            'message': self.message,
            'details': self.details
        }


# Data Errors
class DataError(RevolutionError):
    """Base class for data-related errors."""
    pass


class DataNotFoundError(DataError):
    """Raised when requested data is not found."""

    def __init__(self, data_type: str, identifier: str):
        super().__init__(
            f"{data_type} not found: {identifier}",
            code="DATA_NOT_FOUND",
            details={'data_type': data_type, 'identifier': identifier}
        )


class DataValidationError(DataError):
    """Raised when data validation fails."""

    def __init__(self, message: str, field: Optional[str] = None, value: Any = None):
        details = {}
        if field:
            details['field'] = field
        if value is not None:
            details['value'] = str(value)

        super().__init__(message, code="DATA_VALIDATION", details=details)


class DataQualityError(DataError):
    """Raised when data quality is insufficient."""

    def __init__(self, message: str, quality_score: Optional[float] = None):
        details = {}
        if quality_score is not None:
            details['quality_score'] = quality_score

        super().__init__(message, code="DATA_QUALITY", details=details)


class StaleDataError(DataError):
    """Raised when data is too old."""

    def __init__(self, data_type: str, age_seconds: float, max_age_seconds: float):
        super().__init__(
            f"{data_type} is stale: {age_seconds:.0f}s old (max: {max_age_seconds:.0f}s)",
            code="STALE_DATA",
            details={
                'data_type': data_type,
                'age_seconds': age_seconds,
                'max_age_seconds': max_age_seconds
            }
        )


# Configuration Errors
class ConfigError(RevolutionError):
    """Base class for configuration errors."""
    pass


class ConfigNotFoundError(ConfigError):
    """Raised when configuration file is not found."""

    def __init__(self, config_path: str):
        super().__init__(
            f"Configuration file not found: {config_path}",
            code="CONFIG_NOT_FOUND",
            details={'path': config_path}
        )


class ConfigValidationError(ConfigError):
    """Raised when configuration validation fails."""

    def __init__(self, message: str, setting: Optional[str] = None):
        details = {}
        if setting:
            details['setting'] = setting

        super().__init__(message, code="CONFIG_VALIDATION", details=details)


# Trading Errors
class TradingError(RevolutionError):
    """Base class for trading-related errors."""
    pass


class InsufficientFundsError(TradingError):
    """Raised when there are insufficient funds for a trade."""

    def __init__(self, required: float, available: float):
        super().__init__(
            f"Insufficient funds: required ${required:,.2f}, available ${available:,.2f}",
            code="INSUFFICIENT_FUNDS",
            details={'required': required, 'available': available}
        )


class OrderRejectedError(TradingError):
    """Raised when an order is rejected."""

    def __init__(self, reason: str, order_id: Optional[str] = None):
        details = {'reason': reason}
        if order_id:
            details['order_id'] = order_id

        super().__init__(f"Order rejected: {reason}", code="ORDER_REJECTED", details=details)


class PositionLimitError(TradingError):
    """Raised when position limits are exceeded."""

    def __init__(self, limit_type: str, current: float, limit: float):
        super().__init__(
            f"Position limit exceeded: {limit_type} is {current}, limit is {limit}",
            code="POSITION_LIMIT",
            details={'limit_type': limit_type, 'current': current, 'limit': limit}
        )


class RiskLimitError(TradingError):
    """Raised when risk limits are exceeded."""

    def __init__(self, risk_type: str, current_risk: float, max_risk: float):
        super().__init__(
            f"Risk limit exceeded: {risk_type} risk is {current_risk:.2f}%, max is {max_risk:.2f}%",
            code="RISK_LIMIT",
            details={'risk_type': risk_type, 'current_risk': current_risk, 'max_risk': max_risk}
        )


class MarketClosedError(TradingError):
    """Raised when attempting to trade while market is closed."""

    def __init__(self, market: str = "US Equities"):
        super().__init__(
            f"Market is closed: {market}",
            code="MARKET_CLOSED",
            details={'market': market}
        )


class InvalidSymbolError(TradingError):
    """Raised when an invalid trading symbol is used."""

    def __init__(self, symbol: str):
        super().__init__(
            f"Invalid symbol: {symbol}",
            code="INVALID_SYMBOL",
            details={'symbol': symbol}
        )


# Connection Errors
class ConnectionError(RevolutionError):
    """Base class for connection-related errors."""
    pass


class APIConnectionError(ConnectionError):
    """Raised when API connection fails."""

    def __init__(self, api_name: str, message: str):
        super().__init__(
            f"Failed to connect to {api_name}: {message}",
            code="API_CONNECTION",
            details={'api': api_name}
        )


class WebSocketError(ConnectionError):
    """Raised when WebSocket connection fails."""

    def __init__(self, endpoint: str, message: str):
        super().__init__(
            f"WebSocket error for {endpoint}: {message}",
            code="WEBSOCKET_ERROR",
            details={'endpoint': endpoint}
        )


class TimeoutError(ConnectionError):
    """Raised when an operation times out."""

    def __init__(self, operation: str, timeout_seconds: float):
        super().__init__(
            f"Operation timed out: {operation} (timeout: {timeout_seconds}s)",
            code="TIMEOUT",
            details={'operation': operation, 'timeout_seconds': timeout_seconds}
        )


class RateLimitError(ConnectionError):
    """Raised when rate limit is exceeded."""

    def __init__(self, api_name: str, retry_after: Optional[float] = None):
        details = {'api': api_name}
        if retry_after:
            details['retry_after_seconds'] = retry_after

        super().__init__(
            f"Rate limit exceeded for {api_name}",
            code="RATE_LIMIT",
            details=details
        )


# Model Errors
class ModelError(RevolutionError):
    """Base class for ML model errors."""
    pass


class ModelNotFoundError(ModelError):
    """Raised when a model file is not found."""

    def __init__(self, model_name: str, model_path: str):
        super().__init__(
            f"Model not found: {model_name} at {model_path}",
            code="MODEL_NOT_FOUND",
            details={'model_name': model_name, 'path': model_path}
        )


class ModelLoadError(ModelError):
    """Raised when model loading fails."""

    def __init__(self, model_name: str, reason: str):
        super().__init__(
            f"Failed to load model {model_name}: {reason}",
            code="MODEL_LOAD",
            details={'model_name': model_name, 'reason': reason}
        )


class InferenceError(ModelError):
    """Raised when model inference fails."""

    def __init__(self, model_name: str, reason: str):
        super().__init__(
            f"Inference failed for {model_name}: {reason}",
            code="INFERENCE",
            details={'model_name': model_name, 'reason': reason}
        )


# Scanner Errors
class ScannerError(RevolutionError):
    """Base class for scanner errors."""
    pass


class ScannerConfigError(ScannerError):
    """Raised when scanner configuration is invalid."""

    def __init__(self, scanner_name: str, message: str):
        super().__init__(
            f"Invalid configuration for {scanner_name}: {message}",
            code="SCANNER_CONFIG",
            details={'scanner': scanner_name}
        )


class ScannerTimeoutError(ScannerError):
    """Raised when scanner operation times out."""

    def __init__(self, scanner_name: str):
        super().__init__(
            f"Scanner timed out: {scanner_name}",
            code="SCANNER_TIMEOUT",
            details={'scanner': scanner_name}
        )


# Validation Errors (re-export from validation module)
class ValidationError(RevolutionError):
    """Raised when validation fails."""

    def __init__(self, message: str, errors: Optional[list] = None):
        super().__init__(
            message,
            code="VALIDATION",
            details={'errors': errors} if errors else {}
        )
        self.errors = errors or []


def handle_exception(exc: Exception) -> Dict[str, Any]:
    """
    Convert an exception to a standardized error response.

    Args:
        exc: The exception to handle

    Returns:
        Dictionary with error details
    """
    if isinstance(exc, RevolutionError):
        return exc.to_dict()

    # Handle standard Python exceptions
    return {
        'error': exc.__class__.__name__,
        'message': str(exc),
        'details': {}
    }
