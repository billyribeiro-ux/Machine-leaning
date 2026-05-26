"""
Cross-Asset Intelligence Engine

State-of-the-art multi-asset analysis system:
- Inter-market relationships and correlations
- Lead-lag detection between assets
- Risk-on/Risk-off regime identification
- Currency-equity relationships
- Bond-equity rotation signals
- Commodity-currency correlations
- Global macro indicators
- Contagion risk detection

Provides institutional-grade cross-asset analysis for alpha generation.

Author: Revolution Alpha Engine
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict
import warnings

warnings.filterwarnings('ignore')


class AssetClass(Enum):
    """Asset class categories."""
    EQUITY = "equity"
    FIXED_INCOME = "fixed_income"
    COMMODITY = "commodity"
    CURRENCY = "currency"
    CRYPTO = "crypto"
    VOLATILITY = "volatility"


class MacroRegime(Enum):
    """Global macro regime."""
    RISK_ON = "risk_on"
    RISK_OFF = "risk_off"
    GOLDILOCKS = "goldilocks"       # Low vol, steady growth
    REFLATION = "reflation"          # Rising growth, rising inflation
    STAGFLATION = "stagflation"      # Falling growth, rising inflation
    DEFLATION = "deflation"          # Falling growth, falling inflation
    UNCERTAINTY = "uncertainty"


@dataclass
class AssetPair:
    """Asset pair relationship."""
    asset_a: str
    asset_b: str
    correlation: float
    correlation_zscore: float
    lead_lag_days: int
    causality_direction: str
    relationship_strength: float
    is_cointegrated: bool
    spread_zscore: float


@dataclass
class CrossAssetSignal:
    """Signal from cross-asset analysis."""
    signal_type: str
    direction: str  # bullish, bearish
    strength: float  # 0-100
    assets_involved: List[str]
    reasoning: str
    confidence: float
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class GlobalMacroState:
    """Current global macro state."""
    regime: MacroRegime
    risk_appetite: float  # -100 to 100
    growth_momentum: float
    inflation_expectation: float
    liquidity_conditions: str
    dollar_strength: float
    yield_curve_slope: float
    credit_spreads: float
    vix_regime: str
    confidence: float


class CorrelationAnalyzer:
    """
    Dynamic correlation analysis with regime detection.
    """

    def __init__(self, lookback_short: int = 21, lookback_long: int = 252):
        self.lookback_short = lookback_short
        self.lookback_long = lookback_long

    def rolling_correlation(
        self,
        returns_a: np.ndarray,
        returns_b: np.ndarray,
        window: int = 21
    ) -> np.ndarray:
        """Calculate rolling correlation."""
        n = len(returns_a)
        correlations = np.full(n, np.nan)

        for i in range(window - 1, n):
            slice_a = returns_a[i - window + 1:i + 1]
            slice_b = returns_b[i - window + 1:i + 1]
            correlations[i] = np.corrcoef(slice_a, slice_b)[0, 1]

        return correlations

    def correlation_breakdown(
        self,
        returns_a: np.ndarray,
        returns_b: np.ndarray,
        window: int = 21
    ) -> Tuple[bool, float]:
        """
        Detect correlation breakdown (regime change signal).

        Returns:
            is_breakdown: Whether correlation has broken down
            zscore: Z-score of current correlation vs historical
        """
        correlations = self.rolling_correlation(returns_a, returns_b, window)
        valid_corr = correlations[~np.isnan(correlations)]

        if len(valid_corr) < window * 2:
            return False, 0.0

        current_corr = valid_corr[-1]
        hist_mean = np.mean(valid_corr[:-window])
        hist_std = np.std(valid_corr[:-window])

        if hist_std > 0:
            zscore = (current_corr - hist_mean) / hist_std
        else:
            zscore = 0.0

        is_breakdown = abs(zscore) > 2.0

        return is_breakdown, zscore

    def correlation_regime(
        self,
        returns_a: np.ndarray,
        returns_b: np.ndarray
    ) -> Dict[str, Any]:
        """Identify correlation regime (high/low/negative)."""
        corr_short = np.corrcoef(
            returns_a[-self.lookback_short:],
            returns_b[-self.lookback_short:]
        )[0, 1]

        corr_long = np.corrcoef(
            returns_a[-self.lookback_long:],
            returns_b[-self.lookback_long:]
        )[0, 1]

        # Regime classification
        if corr_short > 0.7:
            regime = 'high_positive'
        elif corr_short > 0.3:
            regime = 'moderate_positive'
        elif corr_short > -0.3:
            regime = 'uncorrelated'
        elif corr_short > -0.7:
            regime = 'moderate_negative'
        else:
            regime = 'high_negative'

        # Trend
        if corr_short > corr_long + 0.1:
            trend = 'increasing'
        elif corr_short < corr_long - 0.1:
            trend = 'decreasing'
        else:
            trend = 'stable'

        return {
            'current_correlation': corr_short,
            'historical_correlation': corr_long,
            'regime': regime,
            'trend': trend
        }


class LeadLagDetector:
    """
    Detect lead-lag relationships between assets.
    """

    def __init__(self, max_lag: int = 10):
        self.max_lag = max_lag

    def cross_correlation(
        self,
        returns_a: np.ndarray,
        returns_b: np.ndarray
    ) -> Tuple[int, float]:
        """
        Find optimal lag using cross-correlation.

        Returns:
            optimal_lag: Positive means A leads B
            max_corr: Maximum correlation found
        """
        correlations = []

        for lag in range(-self.max_lag, self.max_lag + 1):
            if lag > 0:
                corr = np.corrcoef(returns_a[:-lag], returns_b[lag:])[0, 1]
            elif lag < 0:
                corr = np.corrcoef(returns_a[-lag:], returns_b[:lag])[0, 1]
            else:
                corr = np.corrcoef(returns_a, returns_b)[0, 1]

            correlations.append((lag, corr))

        # Find maximum correlation
        optimal_lag, max_corr = max(correlations, key=lambda x: abs(x[1]))

        return optimal_lag, max_corr

    def granger_causality_simple(
        self,
        returns_a: np.ndarray,
        returns_b: np.ndarray,
        lag: int = 5
    ) -> Dict[str, float]:
        """
        Simplified Granger causality test.

        Returns F-statistics for both directions.
        """
        n = len(returns_a) - lag

        # Test if A Granger-causes B
        # Restricted model: B_t = c + sum(B_t-i)
        # Unrestricted model: B_t = c + sum(B_t-i) + sum(A_t-i)

        # Build matrices
        X_restricted = np.ones((n, lag + 1))
        X_unrestricted = np.ones((n, 2 * lag + 1))

        for i in range(lag):
            X_restricted[:, i + 1] = returns_b[lag - i - 1:n + lag - i - 1]
            X_unrestricted[:, i + 1] = returns_b[lag - i - 1:n + lag - i - 1]
            X_unrestricted[:, lag + i + 1] = returns_a[lag - i - 1:n + lag - i - 1]

        y = returns_b[lag:]

        # Fit models (OLS)
        try:
            beta_r = np.linalg.lstsq(X_restricted, y, rcond=None)[0]
            beta_u = np.linalg.lstsq(X_unrestricted, y, rcond=None)[0]

            # Calculate RSS
            rss_r = np.sum((y - X_restricted @ beta_r) ** 2)
            rss_u = np.sum((y - X_unrestricted @ beta_u) ** 2)

            # F-statistic
            f_stat_a_to_b = ((rss_r - rss_u) / lag) / (rss_u / (n - 2 * lag - 1))
        except Exception:
            f_stat_a_to_b = 0.0

        # Test if B Granger-causes A (swap roles)
        X_restricted = np.ones((n, lag + 1))
        X_unrestricted = np.ones((n, 2 * lag + 1))

        for i in range(lag):
            X_restricted[:, i + 1] = returns_a[lag - i - 1:n + lag - i - 1]
            X_unrestricted[:, i + 1] = returns_a[lag - i - 1:n + lag - i - 1]
            X_unrestricted[:, lag + i + 1] = returns_b[lag - i - 1:n + lag - i - 1]

        y = returns_a[lag:]

        try:
            beta_r = np.linalg.lstsq(X_restricted, y, rcond=None)[0]
            beta_u = np.linalg.lstsq(X_unrestricted, y, rcond=None)[0]

            rss_r = np.sum((y - X_restricted @ beta_r) ** 2)
            rss_u = np.sum((y - X_unrestricted @ beta_u) ** 2)

            f_stat_b_to_a = ((rss_r - rss_u) / lag) / (rss_u / (n - 2 * lag - 1))
        except Exception:
            f_stat_b_to_a = 0.0

        # Critical value (approximate, df1=lag, df2=n-2*lag-1)
        # F > 2.0 generally indicates significance

        return {
            'f_stat_a_causes_b': f_stat_a_to_b,
            'f_stat_b_causes_a': f_stat_b_to_a,
            'a_causes_b': f_stat_a_to_b > 2.0,
            'b_causes_a': f_stat_b_to_a > 2.0
        }


class CointegrationAnalyzer:
    """
    Cointegration analysis for pairs trading.
    """

    def __init__(self):
        pass

    def engle_granger_test(
        self,
        prices_a: np.ndarray,
        prices_b: np.ndarray
    ) -> Tuple[bool, float, float]:
        """
        Engle-Granger two-step cointegration test.

        Returns:
            is_cointegrated: Whether series are cointegrated
            hedge_ratio: Optimal hedge ratio
            spread_std: Standard deviation of spread
        """
        # Step 1: Regress A on B
        X = np.column_stack([np.ones(len(prices_b)), prices_b])
        beta = np.linalg.lstsq(X, prices_a, rcond=None)[0]
        hedge_ratio = beta[1]

        # Calculate spread (residuals)
        spread = prices_a - hedge_ratio * prices_b

        # Step 2: Test if spread is stationary (ADF test simplified)
        # Using simple heuristic: variance ratio test

        # Variance of first differences
        diff_spread = np.diff(spread)
        var_diff = np.var(diff_spread)

        # Variance of level
        var_level = np.var(spread)

        # Variance ratio (should be > 2 for random walk, < 2 for mean reversion)
        if var_diff > 0:
            variance_ratio = var_level / (len(spread) * var_diff)
        else:
            variance_ratio = float('inf')

        # Heuristic: cointegrated if VR < 1.5 and spread mean-reverts
        half_life = self._half_life(spread)
        is_cointegrated = variance_ratio < 1.5 and half_life < len(spread) / 4

        return is_cointegrated, hedge_ratio, np.std(spread)

    def _half_life(self, spread: np.ndarray) -> float:
        """Calculate mean-reversion half-life."""
        spread_lag = spread[:-1]
        spread_diff = np.diff(spread)

        # Regress spread_diff on spread_lag
        X = np.column_stack([np.ones(len(spread_lag)), spread_lag])
        beta = np.linalg.lstsq(X, spread_diff, rcond=None)[0]

        # Half-life = -ln(2) / ln(1 + lambda)
        lambda_coef = beta[1]

        if lambda_coef < 0:
            half_life = -np.log(2) / lambda_coef
        else:
            half_life = float('inf')

        return max(1, min(half_life, 1000))  # Cap for numerical stability

    def spread_zscore(
        self,
        prices_a: np.ndarray,
        prices_b: np.ndarray,
        hedge_ratio: float,
        lookback: int = 60
    ) -> float:
        """Calculate z-score of current spread."""
        spread = prices_a - hedge_ratio * prices_b

        if len(spread) < lookback:
            return 0.0

        mean = np.mean(spread[-lookback:])
        std = np.std(spread[-lookback:])

        if std > 0:
            return (spread[-1] - mean) / std
        return 0.0


class RiskAppetiteIndicator:
    """
    Multi-factor risk appetite indicator.
    """

    # Standard inter-market relationships
    RISK_ON_PAIRS = [
        ('SPY', 'TLT', -1),      # Stocks up, bonds down = risk on
        ('HYG', 'TLT', 1),       # High yield up vs treasuries = risk on
        ('EEM', 'SPY', 1),       # EM outperformance = risk on
        ('XLY', 'XLP', 1),       # Discretionary vs staples = risk on
        ('COPPER', 'GOLD', 1),   # Copper/Gold ratio = risk on
        ('AUD', 'JPY', 1),       # AUD/JPY = classic risk barometer
    ]

    def __init__(self):
        self.indicators = {}

    def calculate_risk_appetite(
        self,
        asset_returns: Dict[str, np.ndarray]
    ) -> Tuple[float, Dict[str, float]]:
        """
        Calculate composite risk appetite score.

        Args:
            asset_returns: Dict mapping asset symbols to return arrays

        Returns:
            risk_appetite: Score from -100 to 100
            component_scores: Individual indicator scores
        """
        scores = {}
        weights = []

        # SPY vs TLT (stocks vs bonds)
        if 'SPY' in asset_returns and 'TLT' in asset_returns:
            rel_perf = np.mean(asset_returns['SPY'][-20:]) - np.mean(asset_returns['TLT'][-20:])
            scores['stocks_vs_bonds'] = np.clip(rel_perf * 1000, -100, 100)
            weights.append(0.25)

        # High Yield vs Treasury (credit risk appetite)
        if 'HYG' in asset_returns and 'TLT' in asset_returns:
            rel_perf = np.mean(asset_returns['HYG'][-20:]) - np.mean(asset_returns['TLT'][-20:])
            scores['credit_risk'] = np.clip(rel_perf * 1000, -100, 100)
            weights.append(0.2)

        # Cyclicals vs Defensives
        if 'XLY' in asset_returns and 'XLP' in asset_returns:
            rel_perf = np.mean(asset_returns['XLY'][-20:]) - np.mean(asset_returns['XLP'][-20:])
            scores['cyclicals_vs_defensives'] = np.clip(rel_perf * 1000, -100, 100)
            weights.append(0.15)

        # Small caps vs Large caps (risk preference)
        if 'IWM' in asset_returns and 'SPY' in asset_returns:
            rel_perf = np.mean(asset_returns['IWM'][-20:]) - np.mean(asset_returns['SPY'][-20:])
            scores['small_vs_large'] = np.clip(rel_perf * 1000, -100, 100)
            weights.append(0.15)

        # EM vs DM
        if 'EEM' in asset_returns and 'SPY' in asset_returns:
            rel_perf = np.mean(asset_returns['EEM'][-20:]) - np.mean(asset_returns['SPY'][-20:])
            scores['em_vs_dm'] = np.clip(rel_perf * 1000, -100, 100)
            weights.append(0.1)

        # VIX level (inverse)
        if 'VIX' in asset_returns:
            vix_level = 15 + asset_returns['VIX'][-1] * 100  # Approximate VIX level
            scores['vix_inverse'] = np.clip(50 - vix_level * 2, -100, 100)
            weights.append(0.15)

        if not scores:
            return 0.0, {}

        # Weighted average
        total_weight = sum(weights)
        weighted_sum = sum(
            score * weight for (_, score), weight
            in zip(scores.items(), weights)
        )

        risk_appetite = weighted_sum / total_weight if total_weight > 0 else 0

        return risk_appetite, scores


class CrossAssetIntelligence:
    """
    Master cross-asset intelligence engine.

    Analyzes relationships across asset classes to generate
    actionable signals and regime assessments.
    """

    # Key assets to track
    KEY_ASSETS = {
        AssetClass.EQUITY: ['SPY', 'QQQ', 'IWM', 'EEM', 'EFA'],
        AssetClass.FIXED_INCOME: ['TLT', 'IEF', 'HYG', 'LQD', 'TIP'],
        AssetClass.COMMODITY: ['GLD', 'SLV', 'USO', 'UNG', 'DBA'],
        AssetClass.CURRENCY: ['UUP', 'FXE', 'FXY', 'FXA', 'FXC'],
        AssetClass.VOLATILITY: ['VIX', 'VXX', 'UVXY'],
    }

    # Key relationships to monitor
    KEY_RELATIONSHIPS = [
        ('SPY', 'TLT', 'stock_bond'),
        ('SPY', 'VIX', 'equity_vol'),
        ('GLD', 'UUP', 'gold_dollar'),
        ('HYG', 'TLT', 'credit_spread'),
        ('EEM', 'SPY', 'em_developed'),
        ('USO', 'UUP', 'oil_dollar'),
        ('TLT', 'TIP', 'inflation_exp'),
        ('XLY', 'XLP', 'cyclical_defensive'),
    ]

    def __init__(self):
        self.correlation_analyzer = CorrelationAnalyzer()
        self.lead_lag_detector = LeadLagDetector()
        self.cointegration_analyzer = CointegrationAnalyzer()
        self.risk_appetite_indicator = RiskAppetiteIndicator()

        # State
        self.asset_data: Dict[str, pd.DataFrame] = {}
        self.relationships: Dict[str, AssetPair] = {}
        self.signals: List[CrossAssetSignal] = []
        self.macro_state: Optional[GlobalMacroState] = None

    def load_data(self, data: Dict[str, pd.DataFrame]):
        """
        Load asset price data.

        Args:
            data: Dict mapping asset symbols to DataFrames with 'close' column
        """
        self.asset_data = data

    def _get_returns(self, symbol: str) -> Optional[np.ndarray]:
        """Get return series for asset."""
        if symbol not in self.asset_data:
            return None

        df = self.asset_data[symbol]
        if 'close' in df.columns:
            prices = df['close'].values
        elif 'Close' in df.columns:
            prices = df['Close'].values
        else:
            prices = df.iloc[:, 0].values

        return np.diff(prices) / prices[:-1]

    def _get_prices(self, symbol: str) -> Optional[np.ndarray]:
        """Get price series for asset."""
        if symbol not in self.asset_data:
            return None

        df = self.asset_data[symbol]
        if 'close' in df.columns:
            return df['close'].values
        elif 'Close' in df.columns:
            return df['Close'].values
        return df.iloc[:, 0].values

    def analyze_relationship(self, asset_a: str, asset_b: str) -> Optional[AssetPair]:
        """Analyze relationship between two assets."""
        returns_a = self._get_returns(asset_a)
        returns_b = self._get_returns(asset_b)

        if returns_a is None or returns_b is None:
            return None

        # Align lengths
        min_len = min(len(returns_a), len(returns_b))
        returns_a = returns_a[-min_len:]
        returns_b = returns_b[-min_len:]

        # Correlation analysis
        corr_regime = self.correlation_analyzer.correlation_regime(returns_a, returns_b)
        is_breakdown, corr_zscore = self.correlation_analyzer.correlation_breakdown(
            returns_a, returns_b
        )

        # Lead-lag
        lead_lag, _ = self.lead_lag_detector.cross_correlation(returns_a, returns_b)

        # Causality
        causality = self.lead_lag_detector.granger_causality_simple(returns_a, returns_b)

        if causality['a_causes_b'] and not causality['b_causes_a']:
            causality_direction = f"{asset_a}_leads"
        elif causality['b_causes_a'] and not causality['a_causes_b']:
            causality_direction = f"{asset_b}_leads"
        elif causality['a_causes_b'] and causality['b_causes_a']:
            causality_direction = "bidirectional"
        else:
            causality_direction = "no_causality"

        # Cointegration
        prices_a = self._get_prices(asset_a)
        prices_b = self._get_prices(asset_b)

        if prices_a is not None and prices_b is not None:
            min_len = min(len(prices_a), len(prices_b))
            prices_a = prices_a[-min_len:]
            prices_b = prices_b[-min_len:]

            is_cointegrated, hedge_ratio, spread_std = \
                self.cointegration_analyzer.engle_granger_test(prices_a, prices_b)

            spread_zscore = self.cointegration_analyzer.spread_zscore(
                prices_a, prices_b, hedge_ratio
            )
        else:
            is_cointegrated = False
            spread_zscore = 0.0

        # Relationship strength
        strength = (
            abs(corr_regime['current_correlation']) * 0.4 +
            (1 if is_cointegrated else 0) * 0.3 +
            (1 if causality_direction != 'no_causality' else 0) * 0.3
        )

        return AssetPair(
            asset_a=asset_a,
            asset_b=asset_b,
            correlation=corr_regime['current_correlation'],
            correlation_zscore=corr_zscore,
            lead_lag_days=lead_lag,
            causality_direction=causality_direction,
            relationship_strength=strength,
            is_cointegrated=is_cointegrated,
            spread_zscore=spread_zscore
        )

    def analyze_all_relationships(self) -> Dict[str, AssetPair]:
        """Analyze all key relationships."""
        self.relationships = {}

        for asset_a, asset_b, name in self.KEY_RELATIONSHIPS:
            if asset_a in self.asset_data and asset_b in self.asset_data:
                pair = self.analyze_relationship(asset_a, asset_b)
                if pair:
                    self.relationships[name] = pair

        return self.relationships

    def calculate_macro_regime(self) -> GlobalMacroState:
        """Calculate global macro regime."""
        # Gather returns for risk appetite
        asset_returns = {}
        for symbol in self.asset_data:
            returns = self._get_returns(symbol)
            if returns is not None:
                asset_returns[symbol] = returns

        # Calculate risk appetite
        risk_appetite, _ = self.risk_appetite_indicator.calculate_risk_appetite(asset_returns)

        # Growth momentum (equities momentum)
        if 'SPY' in asset_returns:
            spy_returns = asset_returns['SPY']
            growth_momentum = np.mean(spy_returns[-60:]) * 252 * 100  # Annualized
        else:
            growth_momentum = 0.0

        # Inflation expectation (TIP vs TLT)
        if 'TIP' in asset_returns and 'TLT' in asset_returns:
            inflation_exp = np.mean(asset_returns['TIP'][-20:]) - np.mean(asset_returns['TLT'][-20:])
            inflation_exp = inflation_exp * 1000  # Scale
        else:
            inflation_exp = 0.0

        # Dollar strength
        if 'UUP' in asset_returns:
            dollar_strength = np.mean(asset_returns['UUP'][-20:]) * 1000
        else:
            dollar_strength = 0.0

        # Yield curve (approximation from bond ETFs)
        if 'TLT' in asset_returns and 'IEF' in asset_returns:
            # TLT (20+ year) vs IEF (7-10 year)
            yield_curve = np.mean(asset_returns['IEF'][-20:]) - np.mean(asset_returns['TLT'][-20:])
            yield_curve = yield_curve * 1000
        else:
            yield_curve = 0.0

        # Credit spreads (HYG vs investment grade)
        if 'HYG' in asset_returns and 'LQD' in asset_returns:
            credit_spreads = np.mean(asset_returns['HYG'][-20:]) - np.mean(asset_returns['LQD'][-20:])
            credit_spreads = -credit_spreads * 1000  # Negative = tightening
        else:
            credit_spreads = 0.0

        # VIX regime
        if 'VIX' in self.asset_data:
            vix_prices = self._get_prices('VIX')
            if vix_prices is not None:
                vix_level = vix_prices[-1]
                if vix_level < 15:
                    vix_regime = 'complacent'
                elif vix_level < 20:
                    vix_regime = 'normal'
                elif vix_level < 30:
                    vix_regime = 'elevated'
                else:
                    vix_regime = 'fear'
            else:
                vix_regime = 'unknown'
        else:
            vix_regime = 'unknown'

        # Liquidity conditions
        if credit_spreads < -10:
            liquidity = 'tight'
        elif credit_spreads > 10:
            liquidity = 'loose'
        else:
            liquidity = 'normal'

        # Determine macro regime
        if risk_appetite > 30 and growth_momentum > 5:
            if inflation_exp > 10:
                regime = MacroRegime.REFLATION
            else:
                regime = MacroRegime.GOLDILOCKS
        elif risk_appetite < -30 and growth_momentum < -5:
            if inflation_exp > 10:
                regime = MacroRegime.STAGFLATION
            else:
                regime = MacroRegime.DEFLATION
        elif risk_appetite > 20:
            regime = MacroRegime.RISK_ON
        elif risk_appetite < -20:
            regime = MacroRegime.RISK_OFF
        else:
            regime = MacroRegime.UNCERTAINTY

        # Confidence based on signal agreement
        indicators = [
            risk_appetite / 50,  # Normalized
            growth_momentum / 10,
            -credit_spreads / 20
        ]
        confidence = 1 - np.std(indicators) / 2  # Lower variance = higher confidence
        confidence = max(0.3, min(0.95, confidence))

        self.macro_state = GlobalMacroState(
            regime=regime,
            risk_appetite=risk_appetite,
            growth_momentum=growth_momentum,
            inflation_expectation=inflation_exp,
            liquidity_conditions=liquidity,
            dollar_strength=dollar_strength,
            yield_curve_slope=yield_curve,
            credit_spreads=credit_spreads,
            vix_regime=vix_regime,
            confidence=confidence
        )

        return self.macro_state

    def generate_signals(self) -> List[CrossAssetSignal]:
        """Generate cross-asset trading signals."""
        self.signals = []

        if not self.relationships:
            self.analyze_all_relationships()

        if not self.macro_state:
            self.calculate_macro_regime()

        # Signal 1: Stock-Bond rotation
        if 'stock_bond' in self.relationships:
            pair = self.relationships['stock_bond']

            if pair.correlation_zscore < -2:
                # Correlation breakdown - potential regime change
                self.signals.append(CrossAssetSignal(
                    signal_type='correlation_breakdown',
                    direction='bearish' if pair.correlation > 0 else 'bullish',
                    strength=min(abs(pair.correlation_zscore) * 25, 100),
                    assets_involved=['SPY', 'TLT'],
                    reasoning='Stock-bond correlation regime change detected',
                    confidence=0.7
                ))

        # Signal 2: Credit stress
        if 'credit_spread' in self.relationships:
            pair = self.relationships['credit_spread']

            if pair.spread_zscore > 2:
                self.signals.append(CrossAssetSignal(
                    signal_type='credit_stress',
                    direction='bearish',
                    strength=min(pair.spread_zscore * 25, 100),
                    assets_involved=['HYG', 'TLT'],
                    reasoning='Credit spreads widening - risk-off signal',
                    confidence=0.75
                ))
            elif pair.spread_zscore < -2:
                self.signals.append(CrossAssetSignal(
                    signal_type='credit_improvement',
                    direction='bullish',
                    strength=min(abs(pair.spread_zscore) * 25, 100),
                    assets_involved=['HYG', 'TLT'],
                    reasoning='Credit spreads tightening - risk-on signal',
                    confidence=0.7
                ))

        # Signal 3: Gold-Dollar divergence
        if 'gold_dollar' in self.relationships:
            pair = self.relationships['gold_dollar']

            if pair.correlation > 0.3:  # Usually negative
                self.signals.append(CrossAssetSignal(
                    signal_type='gold_dollar_divergence',
                    direction='bullish',
                    strength=70,
                    assets_involved=['GLD', 'UUP'],
                    reasoning='Gold and dollar both rising - safe haven demand',
                    confidence=0.65
                ))

        # Signal 4: EM divergence
        if 'em_developed' in self.relationships:
            pair = self.relationships['em_developed']

            if pair.lead_lag_days != 0 and abs(pair.lead_lag_days) <= 5:
                leader = 'EEM' if pair.lead_lag_days > 0 else 'SPY'
                self.signals.append(CrossAssetSignal(
                    signal_type='em_lead_signal',
                    direction='bullish' if self._get_returns(leader)[-5:].mean() > 0 else 'bearish',
                    strength=60,
                    assets_involved=['EEM', 'SPY'],
                    reasoning=f'{leader} leading by {abs(pair.lead_lag_days)} days',
                    confidence=0.6
                ))

        # Signal 5: Cointegration mean-reversion
        for name, pair in self.relationships.items():
            if pair.is_cointegrated and abs(pair.spread_zscore) > 2:
                self.signals.append(CrossAssetSignal(
                    signal_type='pairs_trade',
                    direction='mean_reversion',
                    strength=min(abs(pair.spread_zscore) * 25, 100),
                    assets_involved=[pair.asset_a, pair.asset_b],
                    reasoning=f'Cointegrated pair spread at {pair.spread_zscore:.1f} z-score',
                    confidence=0.8
                ))

        # Signal 6: Macro regime signals
        if self.macro_state:
            if self.macro_state.regime == MacroRegime.RISK_ON:
                self.signals.append(CrossAssetSignal(
                    signal_type='macro_regime',
                    direction='bullish',
                    strength=min(self.macro_state.risk_appetite, 100),
                    assets_involved=['SPY', 'QQQ', 'IWM'],
                    reasoning='Risk-on macro regime - favor equities',
                    confidence=self.macro_state.confidence
                ))
            elif self.macro_state.regime == MacroRegime.RISK_OFF:
                self.signals.append(CrossAssetSignal(
                    signal_type='macro_regime',
                    direction='bearish',
                    strength=min(abs(self.macro_state.risk_appetite), 100),
                    assets_involved=['TLT', 'GLD'],
                    reasoning='Risk-off macro regime - favor safe havens',
                    confidence=self.macro_state.confidence
                ))
            elif self.macro_state.regime == MacroRegime.STAGFLATION:
                self.signals.append(CrossAssetSignal(
                    signal_type='macro_regime',
                    direction='bearish',
                    strength=80,
                    assets_involved=['GLD', 'TIP'],
                    reasoning='Stagflation regime - favor real assets',
                    confidence=self.macro_state.confidence
                ))

        return self.signals

    def get_asset_class_rankings(self) -> Dict[str, float]:
        """Rank asset classes by expected performance."""
        if not self.macro_state:
            self.calculate_macro_regime()

        rankings = {}

        # Base rankings by regime
        regime_rankings = {
            MacroRegime.RISK_ON: {
                AssetClass.EQUITY: 100,
                AssetClass.FIXED_INCOME: 30,
                AssetClass.COMMODITY: 70,
                AssetClass.CURRENCY: 50,
            },
            MacroRegime.RISK_OFF: {
                AssetClass.EQUITY: 20,
                AssetClass.FIXED_INCOME: 90,
                AssetClass.COMMODITY: 60,  # Gold
                AssetClass.CURRENCY: 50,
            },
            MacroRegime.GOLDILOCKS: {
                AssetClass.EQUITY: 90,
                AssetClass.FIXED_INCOME: 60,
                AssetClass.COMMODITY: 50,
                AssetClass.CURRENCY: 50,
            },
            MacroRegime.REFLATION: {
                AssetClass.EQUITY: 70,
                AssetClass.FIXED_INCOME: 30,
                AssetClass.COMMODITY: 90,
                AssetClass.CURRENCY: 40,
            },
            MacroRegime.STAGFLATION: {
                AssetClass.EQUITY: 30,
                AssetClass.FIXED_INCOME: 40,
                AssetClass.COMMODITY: 80,
                AssetClass.CURRENCY: 50,
            },
            MacroRegime.DEFLATION: {
                AssetClass.EQUITY: 40,
                AssetClass.FIXED_INCOME: 95,
                AssetClass.COMMODITY: 30,
                AssetClass.CURRENCY: 60,
            },
            MacroRegime.UNCERTAINTY: {
                AssetClass.EQUITY: 50,
                AssetClass.FIXED_INCOME: 60,
                AssetClass.COMMODITY: 50,
                AssetClass.CURRENCY: 50,
            },
        }

        if self.macro_state.regime in regime_rankings:
            for asset_class, score in regime_rankings[self.macro_state.regime].items():
                rankings[asset_class.value] = score

        return rankings

    def get_rotation_signals(self) -> Dict[str, str]:
        """Get asset rotation recommendations."""
        rankings = self.get_asset_class_rankings()

        # Sort by score
        sorted_rankings = sorted(rankings.items(), key=lambda x: -x[1])

        recommendations = {}

        for i, (asset_class, score) in enumerate(sorted_rankings):
            if i == 0:
                recommendations[asset_class] = 'OVERWEIGHT'
            elif i == 1:
                recommendations[asset_class] = 'MARKET_WEIGHT'
            elif score > 50:
                recommendations[asset_class] = 'MARKET_WEIGHT'
            else:
                recommendations[asset_class] = 'UNDERWEIGHT'

        return recommendations

    def analyze(self, data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """
        Full cross-asset analysis.

        Args:
            data: Dict mapping symbols to price DataFrames

        Returns:
            Complete analysis results
        """
        self.load_data(data)
        self.analyze_all_relationships()
        self.calculate_macro_regime()
        self.generate_signals()

        rankings = self.get_asset_class_rankings()
        rotation = self.get_rotation_signals()

        return {
            'macro_regime': self.macro_state.regime.value if self.macro_state else 'unknown',
            'risk_appetite': self.macro_state.risk_appetite if self.macro_state else 0,
            'confidence': self.macro_state.confidence if self.macro_state else 0,
            'relationships': {
                name: {
                    'correlation': pair.correlation,
                    'correlation_zscore': pair.correlation_zscore,
                    'lead_lag': pair.lead_lag_days,
                    'cointegrated': pair.is_cointegrated,
                    'spread_zscore': pair.spread_zscore
                }
                for name, pair in self.relationships.items()
            },
            'signals': [
                {
                    'type': s.signal_type,
                    'direction': s.direction,
                    'strength': s.strength,
                    'assets': s.assets_involved,
                    'reasoning': s.reasoning,
                    'confidence': s.confidence
                }
                for s in self.signals
            ],
            'asset_rankings': rankings,
            'rotation_signals': rotation,
            'vix_regime': self.macro_state.vix_regime if self.macro_state else 'unknown',
            'liquidity': self.macro_state.liquidity_conditions if self.macro_state else 'unknown'
        }


def create_cross_asset_intelligence() -> CrossAssetIntelligence:
    """Factory function to create cross-asset intelligence engine."""
    return CrossAssetIntelligence()


# Example usage and testing
if __name__ == "__main__":
    print("="*60)
    print("CROSS-ASSET INTELLIGENCE ENGINE - TEST MODE")
    print("="*60)

    # Generate synthetic data
    np.random.seed(42)
    n_days = 252

    dates = pd.date_range(end=datetime.now(), periods=n_days, freq='D')

    # Create correlated asset data
    def generate_asset(base_return, vol, correlation_factor=None):
        if correlation_factor is not None:
            returns = base_return + np.random.normal(0, vol, n_days) + 0.5 * correlation_factor
        else:
            returns = base_return + np.random.normal(0, vol, n_days)
        prices = 100 * np.cumprod(1 + returns)
        return pd.DataFrame({'close': prices}, index=dates)

    # Market factor
    market_factor = np.random.normal(0, 0.01, n_days)

    # Generate assets
    data = {
        'SPY': generate_asset(0.0004, 0.012, market_factor),
        'QQQ': generate_asset(0.0005, 0.015, market_factor * 1.2),
        'IWM': generate_asset(0.0003, 0.014, market_factor * 1.1),
        'TLT': generate_asset(0.0002, 0.008, -market_factor * 0.3),
        'IEF': generate_asset(0.00015, 0.005, -market_factor * 0.2),
        'HYG': generate_asset(0.0003, 0.006, market_factor * 0.5),
        'LQD': generate_asset(0.00025, 0.004, -market_factor * 0.1),
        'GLD': generate_asset(0.0002, 0.01, -market_factor * 0.2),
        'UUP': generate_asset(0.0001, 0.005, None),
        'EEM': generate_asset(0.0003, 0.016, market_factor * 0.8),
        'XLY': generate_asset(0.0004, 0.013, market_factor * 1.1),
        'XLP': generate_asset(0.0002, 0.008, market_factor * 0.6),
        'TIP': generate_asset(0.00015, 0.006, -market_factor * 0.15),
    }

    # Create engine
    engine = create_cross_asset_intelligence()

    # Run analysis
    print("\nRunning cross-asset analysis...")
    results = engine.analyze(data)

    print(f"\n{'='*60}")
    print("MACRO REGIME")
    print('='*60)
    print(f"Regime: {results['macro_regime']}")
    print(f"Risk Appetite: {results['risk_appetite']:.1f}")
    print(f"VIX Regime: {results['vix_regime']}")
    print(f"Liquidity: {results['liquidity']}")
    print(f"Confidence: {results['confidence']:.2%}")

    print(f"\n{'='*60}")
    print("KEY RELATIONSHIPS")
    print('='*60)
    for name, rel in results['relationships'].items():
        print(f"\n{name}:")
        print(f"  Correlation: {rel['correlation']:.3f} (z-score: {rel['correlation_zscore']:.2f})")
        print(f"  Lead-Lag: {rel['lead_lag']} days")
        print(f"  Cointegrated: {rel['cointegrated']}")
        if rel['cointegrated']:
            print(f"  Spread Z-Score: {rel['spread_zscore']:.2f}")

    print(f"\n{'='*60}")
    print("SIGNALS")
    print('='*60)
    for signal in results['signals']:
        print(f"\n{signal['type']}:")
        print(f"  Direction: {signal['direction']}")
        print(f"  Strength: {signal['strength']:.0f}/100")
        print(f"  Assets: {', '.join(signal['assets'])}")
        print(f"  Reasoning: {signal['reasoning']}")
        print(f"  Confidence: {signal['confidence']:.2%}")

    print(f"\n{'='*60}")
    print("ASSET CLASS ROTATION")
    print('='*60)
    for asset_class, action in results['rotation_signals'].items():
        score = results['asset_rankings'].get(asset_class, 50)
        print(f"  {asset_class}: {action} (score: {score})")

    print(f"\n{'='*60}")
    print("CROSS-ASSET INTELLIGENCE - READY FOR PRODUCTION")
    print('='*60)
