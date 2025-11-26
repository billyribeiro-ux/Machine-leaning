"""
Revolution Alpha Engine - Unified Configuration System

Centralized configuration management for all system components.
Supports YAML, JSON, and environment variables.
"""

import os
import json
import yaml
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Union
from enum import Enum


class Environment(Enum):
    """Deployment environment."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    BACKTEST = "backtest"


@dataclass
class TradingConfig:
    """Trading-specific configuration."""
    # Symbols
    symbols: List[str] = field(default_factory=lambda: ["SPY", "QQQ", "SPX"])
    futures_symbols: List[str] = field(default_factory=lambda: ["ES", "NQ"])

    # Trading hours (ET)
    market_open_hour: int = 9
    market_open_minute: int = 30
    market_close_hour: int = 16
    market_close_minute: int = 0

    # Position limits
    max_position_size: int = 100
    max_daily_trades: int = 50
    max_open_positions: int = 10

    # Order settings
    default_order_type: str = "limit"
    slippage_bps: float = 5.0  # Basis points
    commission_per_contract: float = 0.65

    # Timeouts
    order_timeout_seconds: int = 30
    data_timeout_seconds: int = 10


@dataclass
class RiskConfig:
    """Risk management configuration."""
    # Capital allocation
    max_portfolio_risk_pct: float = 2.0  # Max 2% of portfolio at risk
    max_position_risk_pct: float = 0.5  # Max 0.5% per position
    max_daily_loss_pct: float = 3.0  # Stop trading after 3% daily loss

    # Position sizing
    kelly_fraction: float = 0.25  # Quarter Kelly
    max_leverage: float = 2.0

    # Stop loss
    default_stop_loss_pct: float = 2.0
    trailing_stop_pct: float = 1.5

    # Greeks limits (for options)
    max_delta_exposure: float = 100.0
    max_gamma_exposure: float = 50.0
    max_vega_exposure: float = 1000.0
    max_theta_decay_daily: float = 500.0

    # Correlation
    max_correlation_exposure: float = 0.7


@dataclass
class ScannerConfig:
    """Scanner configuration."""
    # Scanning intervals
    scan_interval_seconds: int = 5
    momentum_lookback_periods: List[int] = field(default_factory=lambda: [5, 10, 20, 50])

    # Thresholds
    min_volume: int = 100000
    min_price: float = 5.0
    max_spread_pct: float = 0.5

    # Signals
    min_confidence: float = 70.0
    min_confirmations: int = 3

    # Scanner types enabled
    enable_momentum_scanner: bool = True
    enable_squeeze_scanner: bool = True
    enable_options_scanner: bool = True
    enable_mtf_scanner: bool = True

    # Alert settings
    alert_on_high_confidence: bool = True
    alert_threshold: float = 85.0


@dataclass
class MLConfig:
    """Machine learning configuration."""
    # Model settings
    model_type: str = "ensemble"  # ensemble, transformer, lstm
    hidden_sizes: List[int] = field(default_factory=lambda: [256, 128, 64])
    dropout_rate: float = 0.2
    learning_rate: float = 0.001

    # Training
    batch_size: int = 32
    epochs: int = 100
    early_stopping_patience: int = 10
    validation_split: float = 0.2

    # Feature engineering
    lookback_window: int = 60
    prediction_horizon: int = 5
    use_technical_features: bool = True
    use_sentiment_features: bool = True

    # Self-learning
    enable_online_learning: bool = True
    online_learning_rate: float = 0.0001
    experience_replay_size: int = 10000


@dataclass
class APIConfig:
    """API and connectivity configuration."""
    # Data providers
    primary_data_provider: str = "polygon"
    backup_data_provider: str = "alpaca"

    # API keys (loaded from environment)
    polygon_api_key: str = ""
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""

    # Endpoints
    use_paper_trading: bool = True
    websocket_enabled: bool = True

    # Rate limiting
    max_requests_per_second: int = 100
    max_websocket_connections: int = 5

    def load_from_env(self):
        """Load API keys from environment variables."""
        self.polygon_api_key = os.getenv("POLYGON_API_KEY", "")
        self.alpaca_api_key = os.getenv("ALPACA_API_KEY", "")
        self.alpaca_secret_key = os.getenv("ALPACA_SECRET_KEY", "")


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    format: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    date_format: str = "%Y-%m-%d %H:%M:%S"

    # File logging
    log_to_file: bool = True
    log_dir: str = "logs"
    max_file_size_mb: int = 100
    backup_count: int = 10

    # Trade logging
    log_trades: bool = True
    trade_log_file: str = "trades.log"

    # Performance logging
    log_performance: bool = True
    performance_log_file: str = "performance.log"


@dataclass
class DisplayConfig:
    """Display and UI configuration."""
    # Theme
    theme: str = "dark"  # dark, light
    color_scheme: str = "professional"  # professional, vibrant, minimal

    # Dashboard
    refresh_rate_ms: int = 1000
    show_charts: bool = True
    chart_height: int = 20

    # Alerts
    enable_sound_alerts: bool = False
    enable_desktop_notifications: bool = True

    # Table settings
    max_rows_display: int = 50
    truncate_long_text: bool = True


@dataclass
class Config:
    """
    Master configuration class.

    Aggregates all configuration sections.
    """
    # Environment
    environment: Environment = Environment.DEVELOPMENT
    version: str = "1.0.0"

    # Sub-configurations
    trading: TradingConfig = field(default_factory=TradingConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    scanner: ScannerConfig = field(default_factory=ScannerConfig)
    ml: MLConfig = field(default_factory=MLConfig)
    api: APIConfig = field(default_factory=APIConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)

    # Paths
    data_dir: str = "data"
    models_dir: str = "models"
    output_dir: str = "output"

    def __post_init__(self):
        """Post-initialization setup."""
        # Load API keys from environment
        self.api.load_from_env()

        # Create directories if they don't exist
        for dir_path in [self.data_dir, self.models_dir, self.output_dir, self.logging.log_dir]:
            Path(dir_path).mkdir(parents=True, exist_ok=True)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Config':
        """Create from dictionary."""
        # Handle environment enum
        if 'environment' in data and isinstance(data['environment'], str):
            data['environment'] = Environment(data['environment'])

        # Create sub-configs
        if 'trading' in data and isinstance(data['trading'], dict):
            data['trading'] = TradingConfig(**data['trading'])
        if 'risk' in data and isinstance(data['risk'], dict):
            data['risk'] = RiskConfig(**data['risk'])
        if 'scanner' in data and isinstance(data['scanner'], dict):
            data['scanner'] = ScannerConfig(**data['scanner'])
        if 'ml' in data and isinstance(data['ml'], dict):
            data['ml'] = MLConfig(**data['ml'])
        if 'api' in data and isinstance(data['api'], dict):
            data['api'] = APIConfig(**data['api'])
        if 'logging' in data and isinstance(data['logging'], dict):
            data['logging'] = LoggingConfig(**data['logging'])
        if 'display' in data and isinstance(data['display'], dict):
            data['display'] = DisplayConfig(**data['display'])

        return cls(**data)


def load_config(path: Union[str, Path]) -> Config:
    """
    Load configuration from file.

    Supports YAML and JSON formats.

    Args:
        path: Path to configuration file

    Returns:
        Config object
    """
    path = Path(path)

    if not path.exists():
        print(f"Config file not found: {path}. Using defaults.")
        return Config()

    with open(path, 'r') as f:
        if path.suffix in ['.yaml', '.yml']:
            data = yaml.safe_load(f)
        elif path.suffix == '.json':
            data = json.load(f)
        else:
            raise ValueError(f"Unsupported config format: {path.suffix}")

    return Config.from_dict(data or {})


def save_config(config: Config, path: Union[str, Path]) -> None:
    """
    Save configuration to file.

    Args:
        config: Config object
        path: Output path
    """
    path = Path(path)
    data = config.to_dict()

    # Convert enum to string
    if 'environment' in data:
        data['environment'] = data['environment'].value if hasattr(data['environment'], 'value') else str(data['environment'])

    with open(path, 'w') as f:
        if path.suffix in ['.yaml', '.yml']:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        elif path.suffix == '.json':
            json.dump(data, f, indent=2)
        else:
            raise ValueError(f"Unsupported config format: {path.suffix}")

    print(f"Configuration saved to: {path}")


def create_default_config_file(path: Union[str, Path] = "config.yaml") -> None:
    """Create a default configuration file."""
    config = Config()
    save_config(config, path)


# Global configuration instance
_global_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _global_config
    if _global_config is None:
        # Try to load from default locations
        for config_path in ['config.yaml', 'config.yml', 'config.json']:
            if Path(config_path).exists():
                _global_config = load_config(config_path)
                break
        if _global_config is None:
            _global_config = Config()
    return _global_config


def set_config(config: Config) -> None:
    """Set the global configuration instance."""
    global _global_config
    _global_config = config
