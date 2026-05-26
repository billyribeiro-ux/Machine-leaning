"""
Revolution Alpha Engine - Feature Engineering Pipeline

Comprehensive feature engineering for financial ML:
- 500+ engineered features
- Price-based features (returns, gaps, ranges)
- Momentum indicators (RSI, MACD, Stochastic)
- Volatility metrics (ATR, Bollinger, Keltner)
- Volume analysis (VWAP, MFI, OBV)
- Statistical features (Z-scores, entropy, kurtosis)
- Trend detection (ADX, Aroon, Ichimoku)
"""

from .engineering import (
    FeatureEngineer,
    PriceFeatures,
    MomentumFeatures,
    VolatilityFeatures,
    VolumeFeatures,
    TrendFeatures,
    StatisticalFeatures,
)

__all__ = [
    "FeatureEngineer",
    "PriceFeatures",
    "MomentumFeatures",
    "VolatilityFeatures",
    "VolumeFeatures",
    "TrendFeatures",
    "StatisticalFeatures",
]

__version__ = "0.1.0"
