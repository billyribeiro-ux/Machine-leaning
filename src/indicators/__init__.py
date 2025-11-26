"""
Revolution Alpha Engine - Customizable Indicator System

Fully customizable technical indicators:
- All major indicators (SMA, EMA, RSI, MACD, etc.)
- Custom parameter configuration
- Pattern recognition
- Signal combination
- Strategy building

Users can choose any indicators, customize parameters,
and combine multiple signals for pattern recognition.
"""

from .custom_indicators import (
    CustomIndicatorSystem,
    BaseIndicator,
    IndicatorConfig,
    IndicatorResult,
    IndicatorCategory,
    IndicatorRegistry,
    PatternRecognizer,
    PatternMatch,
    CombinedSignal,
    SignalType,
    # Individual indicators
    SMAIndicator,
    EMAIndicator,
    MACDIndicator,
    ADXIndicator,
    RSIIndicator,
    StochasticIndicator,
    CCIIndicator,
    BollingerBandsIndicator,
    ATRIndicator,
    VWAPIndicator,
    OBVIndicator,
    # Factory functions
    create_indicator_system,
    create_default_indicator_set,
)

__all__ = [
    # Main classes
    "CustomIndicatorSystem",
    "BaseIndicator",
    "IndicatorConfig",
    "IndicatorResult",
    "IndicatorCategory",
    "IndicatorRegistry",
    "PatternRecognizer",
    "PatternMatch",
    "CombinedSignal",
    "SignalType",
    # Indicators
    "SMAIndicator",
    "EMAIndicator",
    "MACDIndicator",
    "ADXIndicator",
    "RSIIndicator",
    "StochasticIndicator",
    "CCIIndicator",
    "BollingerBandsIndicator",
    "ATRIndicator",
    "VWAPIndicator",
    "OBVIndicator",
    # Factory functions
    "create_indicator_system",
    "create_default_indicator_set",
]

__version__ = "0.1.0"
