"""
Revolution Alpha Engine - Alternative Data & Alpha Generation

Beyond traditional market data for alpha generation:
- NLP sentiment analysis on news and social media
- SEC filing analysis (13F, 10-K, 8-K, Form 4)
- Earnings call transcript analysis
- Institutional flow detection
- Smart money tracking
"""

from .alternative_data import (
    AlternativeDataEngine,
    SentimentAnalyzer,
    SECFilingAnalyzer,
    EarningsCallAnalyzer,
    SocialSentimentAggregator,
    FinancialBERT,
    SentimentSource,
    FilingType,
    SentimentSignal,
    AggregatedSentiment,
    FilingSignal,
    EarningsSignal,
    create_alternative_data_engine,
)

__all__ = [
    "AlternativeDataEngine",
    "SentimentAnalyzer",
    "SECFilingAnalyzer",
    "EarningsCallAnalyzer",
    "SocialSentimentAggregator",
    "FinancialBERT",
    "SentimentSource",
    "FilingType",
    "SentimentSignal",
    "AggregatedSentiment",
    "FilingSignal",
    "EarningsSignal",
    "create_alternative_data_engine",
]

__version__ = "0.1.0"
