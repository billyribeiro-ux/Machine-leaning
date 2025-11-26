"""
Revolution Alpha Engine - Comprehensive Logging System

Professional-grade logging for:
- Application events
- Trade execution
- Performance metrics
- Audit trails
- Error tracking
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field, asdict
import json
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from functools import wraps
import traceback
import threading


# Custom log levels
TRADE = 25  # Between INFO and WARNING
SIGNAL = 23  # For trading signals
PERF = 22  # Performance metrics

logging.addLevelName(TRADE, 'TRADE')
logging.addLevelName(SIGNAL, 'SIGNAL')
logging.addLevelName(PERF, 'PERF')


class ColoredFormatter(logging.Formatter):
    """Colored formatter for terminal output."""

    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'PERF': '\033[35m',      # Magenta
        'SIGNAL': '\033[33m',    # Yellow
        'TRADE': '\033[34m',     # Blue
        'WARNING': '\033[93m',   # Light Yellow
        'ERROR': '\033[91m',     # Light Red
        'CRITICAL': '\033[41m',  # Red background
    }
    RESET = '\033[0m'

    def format(self, record):
        color = self.COLORS.get(record.levelname, '')
        record.levelname = f"{color}{record.levelname:8}{self.RESET}"
        return super().format(record)


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record):
        log_data = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }

        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)

        # Add extra fields
        if hasattr(record, 'extra_data'):
            log_data['data'] = record.extra_data

        return json.dumps(log_data)


def setup_logging(
    level: str = "INFO",
    log_dir: str = "logs",
    log_to_file: bool = True,
    log_to_console: bool = True,
    json_format: bool = False,
    max_file_size_mb: int = 100,
    backup_count: int = 10
) -> logging.Logger:
    """
    Setup logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Directory for log files
        log_to_file: Whether to log to files
        log_to_console: Whether to log to console
        json_format: Use JSON format for file logs
        max_file_size_mb: Max size per log file
        backup_count: Number of backup files to keep

    Returns:
        Root logger
    """
    # Create log directory
    if log_to_file:
        Path(log_dir).mkdir(parents=True, exist_ok=True)

    # Get root logger
    root_logger = logging.getLogger('revolution')
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Clear existing handlers
    root_logger.handlers.clear()

    # Console handler with colors
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_formatter = ColoredFormatter(
            '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

    # File handler
    if log_to_file:
        # Main log file
        main_log = Path(log_dir) / 'revolution.log'
        file_handler = RotatingFileHandler(
            main_log,
            maxBytes=max_file_size_mb * 1024 * 1024,
            backupCount=backup_count
        )
        file_handler.setLevel(logging.DEBUG)

        if json_format:
            file_formatter = JSONFormatter()
        else:
            file_formatter = logging.Formatter(
                '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

        # Error log file (errors only)
        error_log = Path(log_dir) / 'errors.log'
        error_handler = RotatingFileHandler(
            error_log,
            maxBytes=max_file_size_mb * 1024 * 1024,
            backupCount=backup_count
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(file_formatter)
        root_logger.addHandler(error_handler)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the given name.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(f'revolution.{name}')


@dataclass
class TradeRecord:
    """Record of a trade execution."""
    timestamp: datetime
    symbol: str
    direction: str
    quantity: int
    entry_price: float
    exit_price: Optional[float] = None
    stop_loss: float = 0.0
    take_profit: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    commission: float = 0.0
    slippage: float = 0.0
    status: str = "open"
    strategy: str = ""
    notes: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class TradeLogger:
    """
    Specialized logger for trade execution.

    Features:
    - Trade record tracking
    - P&L calculation
    - Trade history export
    - Performance statistics
    """

    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.logger = get_logger('trades')
        self.trades: List[TradeRecord] = []
        self.lock = threading.Lock()

        # Setup trade-specific file
        trade_log = self.log_dir / 'trades.log'
        handler = RotatingFileHandler(trade_log, maxBytes=50*1024*1024, backupCount=20)
        handler.setFormatter(logging.Formatter(
            '%(asctime)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
        handler.setLevel(TRADE)
        self.logger.addHandler(handler)

    def log_entry(
        self,
        symbol: str,
        direction: str,
        quantity: int,
        price: float,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        strategy: str = "",
        **metadata
    ) -> TradeRecord:
        """Log a trade entry."""
        record = TradeRecord(
            timestamp=datetime.now(),
            symbol=symbol,
            direction=direction,
            quantity=quantity,
            entry_price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            strategy=strategy,
            metadata=metadata
        )

        with self.lock:
            self.trades.append(record)

        self.logger.log(
            TRADE,
            f"ENTRY | {symbol} | {direction} | Qty: {quantity} | Price: ${price:.2f} | "
            f"SL: ${stop_loss:.2f} | TP: ${take_profit:.2f} | Strategy: {strategy}"
        )

        return record

    def log_exit(
        self,
        record: TradeRecord,
        exit_price: float,
        commission: float = 0.0,
        slippage: float = 0.0,
        notes: str = ""
    ) -> TradeRecord:
        """Log a trade exit."""
        record.exit_price = exit_price
        record.commission = commission
        record.slippage = slippage
        record.notes = notes
        record.status = "closed"

        # Calculate P&L
        if record.direction.upper() in ['BUY', 'LONG', 'LONG_CALL', 'LONG_PUT']:
            record.pnl = (exit_price - record.entry_price) * record.quantity * 100 - commission
        else:
            record.pnl = (record.entry_price - exit_price) * record.quantity * 100 - commission

        record.pnl_pct = (record.pnl / (record.entry_price * record.quantity * 100)) * 100

        self.logger.log(
            TRADE,
            f"EXIT  | {record.symbol} | {record.direction} | Qty: {record.quantity} | "
            f"Entry: ${record.entry_price:.2f} | Exit: ${exit_price:.2f} | "
            f"P&L: ${record.pnl:.2f} ({record.pnl_pct:+.2f}%)"
        )

        return record

    def get_statistics(self) -> Dict[str, Any]:
        """Get trading statistics."""
        closed_trades = [t for t in self.trades if t.status == 'closed']

        if not closed_trades:
            return {'total_trades': 0}

        wins = [t for t in closed_trades if t.pnl > 0]
        losses = [t for t in closed_trades if t.pnl < 0]

        total_pnl = sum(t.pnl for t in closed_trades)
        avg_win = sum(t.pnl for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t.pnl for t in losses) / len(losses) if losses else 0

        return {
            'total_trades': len(closed_trades),
            'winning_trades': len(wins),
            'losing_trades': len(losses),
            'win_rate': f"{len(wins) / len(closed_trades) * 100:.1f}%",
            'total_pnl': f"${total_pnl:,.2f}",
            'avg_win': f"${avg_win:,.2f}",
            'avg_loss': f"${avg_loss:,.2f}",
            'profit_factor': f"{abs(sum(t.pnl for t in wins) / sum(t.pnl for t in losses)):.2f}" if losses else "N/A",
            'largest_win': f"${max(t.pnl for t in wins):,.2f}" if wins else "$0",
            'largest_loss': f"${min(t.pnl for t in losses):,.2f}" if losses else "$0"
        }

    def export_trades(self, filepath: str, format: str = "csv"):
        """Export trade history."""
        import csv

        if format == "csv":
            with open(filepath, 'w', newline='') as f:
                if self.trades:
                    writer = csv.DictWriter(f, fieldnames=asdict(self.trades[0]).keys())
                    writer.writeheader()
                    for trade in self.trades:
                        row = asdict(trade)
                        row['timestamp'] = row['timestamp'].isoformat()
                        writer.writerow(row)
        elif format == "json":
            with open(filepath, 'w') as f:
                trades_data = []
                for trade in self.trades:
                    data = asdict(trade)
                    data['timestamp'] = data['timestamp'].isoformat()
                    trades_data.append(data)
                json.dump(trades_data, f, indent=2)


class PerformanceLogger:
    """
    Logger for performance metrics.

    Tracks execution times, resource usage, and system metrics.
    """

    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.logger = get_logger('performance')
        self.metrics: Dict[str, List[float]] = {}
        self.lock = threading.Lock()

        # Setup performance file
        perf_log = self.log_dir / 'performance.log'
        handler = RotatingFileHandler(perf_log, maxBytes=50*1024*1024, backupCount=10)
        handler.setFormatter(logging.Formatter(
            '%(asctime)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
        handler.setLevel(PERF)
        self.logger.addHandler(handler)

    def log_metric(self, name: str, value: float, unit: str = ""):
        """Log a performance metric."""
        with self.lock:
            if name not in self.metrics:
                self.metrics[name] = []
            self.metrics[name].append(value)

        unit_str = f" {unit}" if unit else ""
        self.logger.log(PERF, f"METRIC | {name}: {value:.3f}{unit_str}")

    def log_timing(self, operation: str, duration_ms: float):
        """Log operation timing."""
        self.log_metric(f"timing.{operation}", duration_ms, "ms")

    def log_throughput(self, operation: str, items_per_second: float):
        """Log throughput metric."""
        self.log_metric(f"throughput.{operation}", items_per_second, "items/s")

    def get_summary(self) -> Dict[str, Dict[str, float]]:
        """Get summary of all metrics."""
        import numpy as np

        summary = {}
        with self.lock:
            for name, values in self.metrics.items():
                if values:
                    summary[name] = {
                        'count': len(values),
                        'mean': np.mean(values),
                        'std': np.std(values),
                        'min': np.min(values),
                        'max': np.max(values),
                        'p50': np.percentile(values, 50),
                        'p95': np.percentile(values, 95),
                        'p99': np.percentile(values, 99)
                    }
        return summary


class AuditLogger:
    """
    Audit logger for compliance and security.

    Tracks all significant system events for audit trails.
    """

    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.logger = get_logger('audit')

        # Setup audit file with daily rotation
        audit_log = self.log_dir / 'audit.log'
        handler = TimedRotatingFileHandler(
            audit_log,
            when='midnight',
            interval=1,
            backupCount=365  # Keep 1 year of audit logs
        )
        handler.setFormatter(JSONFormatter())
        self.logger.addHandler(handler)

    def log_event(
        self,
        event_type: str,
        description: str,
        user: str = "system",
        ip_address: str = "",
        **details
    ):
        """Log an audit event."""
        record = {
            'event_type': event_type,
            'description': description,
            'user': user,
            'ip_address': ip_address,
            **details
        }

        # Create log record with extra data
        log_record = logging.LogRecord(
            name='revolution.audit',
            level=logging.INFO,
            pathname='',
            lineno=0,
            msg=json.dumps(record),
            args=(),
            exc_info=None
        )
        log_record.extra_data = record

        self.logger.handle(log_record)

    def log_login(self, user: str, ip_address: str, success: bool):
        """Log login attempt."""
        self.log_event(
            'LOGIN',
            f"Login {'successful' if success else 'failed'}",
            user=user,
            ip_address=ip_address,
            success=success
        )

    def log_config_change(self, user: str, setting: str, old_value: Any, new_value: Any):
        """Log configuration change."""
        self.log_event(
            'CONFIG_CHANGE',
            f"Changed {setting}",
            user=user,
            setting=setting,
            old_value=str(old_value),
            new_value=str(new_value)
        )

    def log_order(self, user: str, order_type: str, symbol: str, quantity: int, price: float):
        """Log order submission."""
        self.log_event(
            'ORDER',
            f"{order_type} order for {symbol}",
            user=user,
            order_type=order_type,
            symbol=symbol,
            quantity=quantity,
            price=price
        )


def log_exceptions(logger: Optional[logging.Logger] = None):
    """
    Decorator to log exceptions from functions.

    Example:
        @log_exceptions()
        def risky_function():
            pass
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            _logger = logger or get_logger(func.__module__)
            try:
                return func(*args, **kwargs)
            except Exception as e:
                _logger.exception(f"Exception in {func.__name__}: {e}")
                raise
        return wrapper
    return decorator
