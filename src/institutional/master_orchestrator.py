"""
Master Scanner Orchestrator

The brain that coordinates all institutional scanners:
- VIX Institutional Tracker
- Dark Pool Activity Detector
- Smart Money Flow Tracker
- Regime Change Detector
- Cross-Asset Intelligence Engine
- Predictive Order Flow System

Combines signals with intelligent weighting and conflict resolution
to generate unified, high-conviction trading opportunities.

Author: Revolution Alpha Engine
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Callable
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict
import asyncio
import threading
from queue import Queue, Empty
import warnings

warnings.filterwarnings('ignore')


class SignalPriority(Enum):
    """Signal priority levels."""
    CRITICAL = 1    # Must act immediately
    HIGH = 2        # Strong opportunity
    MEDIUM = 3      # Standard signal
    LOW = 4         # Informational
    NOISE = 5       # Likely false signal


class ConvictionLevel(Enum):
    """Trading conviction levels."""
    EXTREME = "extreme"     # 90%+ confidence, multiple confirmations
    HIGH = "high"           # 75%+ confidence, strong confluence
    MODERATE = "moderate"   # 60%+ confidence, reasonable setup
    LOW = "low"            # 50%+ confidence, speculative
    NONE = "none"          # No trade


@dataclass
class UnifiedSignal:
    """Unified signal from multiple scanners."""
    symbol: str
    direction: str  # 'long', 'short', 'neutral'
    conviction: ConvictionLevel
    priority: SignalPriority
    composite_score: float  # 0-100
    entry_price: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    position_size_pct: float  # Suggested position size
    contributing_scanners: List[str]
    scanner_signals: Dict[str, Dict]
    confluence_count: int
    reasoning: str
    risk_reward: float
    expected_holding_period: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class MarketContext:
    """Current market context."""
    macro_regime: str
    volatility_regime: str
    risk_appetite: float
    market_breadth: float
    sector_leadership: List[str]
    institutional_activity: str
    trend_strength: float
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ScannerWeight:
    """Weight configuration for a scanner."""
    scanner_name: str
    base_weight: float
    regime_adjustments: Dict[str, float]
    volatility_adjustments: Dict[str, float]
    current_weight: float = 0.0


class SignalAggregator:
    """
    Aggregates and resolves signals from multiple scanners.
    """

    def __init__(self):
        self.signal_buffer: Dict[str, List[Dict]] = defaultdict(list)
        self.conflict_resolution_rules = {}

    def add_signal(
        self,
        scanner_name: str,
        symbol: str,
        signal: Dict
    ):
        """Add signal to buffer."""
        signal['scanner'] = scanner_name
        signal['received_at'] = datetime.now()
        self.signal_buffer[symbol].append(signal)

    def resolve_conflicts(
        self,
        symbol: str,
        weights: Dict[str, float]
    ) -> Dict:
        """
        Resolve conflicting signals for a symbol.

        Uses weighted voting and confidence-adjusted scoring.
        """
        signals = self.signal_buffer.get(symbol, [])

        if not signals:
            return {'direction': 'neutral', 'score': 0}

        # Separate by direction
        long_signals = [s for s in signals if s.get('direction') in ['long', 'buy', 'bullish']]
        short_signals = [s for s in signals if s.get('direction') in ['short', 'sell', 'bearish']]
        neutral_signals = [s for s in signals if s.get('direction') in ['neutral', 'hold']]

        # Calculate weighted scores
        long_score = sum(
            weights.get(s['scanner'], 1.0) * s.get('strength', 50) * s.get('confidence', 0.5)
            for s in long_signals
        )

        short_score = sum(
            weights.get(s['scanner'], 1.0) * s.get('strength', 50) * s.get('confidence', 0.5)
            for s in short_signals
        )

        neutral_score = sum(
            weights.get(s['scanner'], 1.0) * s.get('strength', 50) * s.get('confidence', 0.5)
            for s in neutral_signals
        )

        # Determine direction
        scores = {'long': long_score, 'short': short_score, 'neutral': neutral_score}
        direction = max(scores, key=scores.get)

        # Calculate net score
        if direction == 'long':
            net_score = long_score - short_score
        elif direction == 'short':
            net_score = short_score - long_score
        else:
            net_score = neutral_score

        # Normalize to 0-100
        max_possible = sum(weights.values()) * 100  # Max if all signals agree at 100%
        normalized_score = min(abs(net_score) / max_possible * 200, 100)

        return {
            'direction': direction,
            'score': normalized_score,
            'long_score': long_score,
            'short_score': short_score,
            'neutral_score': neutral_score,
            'signal_count': len(signals),
            'long_count': len(long_signals),
            'short_count': len(short_signals)
        }

    def clear_buffer(self, symbol: Optional[str] = None):
        """Clear signal buffer."""
        if symbol:
            self.signal_buffer[symbol] = []
        else:
            self.signal_buffer.clear()


class ConfluenceAnalyzer:
    """
    Analyzes confluence across multiple signals and timeframes.
    """

    def __init__(self):
        self.confluence_weights = {
            'same_direction': 1.0,
            'same_timeframe': 0.5,
            'different_scanner': 0.8,
            'institutional_confirmation': 1.5,
            'regime_alignment': 1.2
        }

    def calculate_confluence(
        self,
        signals: List[Dict],
        market_context: MarketContext
    ) -> Tuple[int, float]:
        """
        Calculate confluence score.

        Returns:
            confluence_count: Number of confirming signals
            confluence_score: Weighted confluence score
        """
        if not signals:
            return 0, 0.0

        # Get dominant direction
        directions = [s.get('direction', 'neutral') for s in signals]
        direction_counts = defaultdict(int)
        for d in directions:
            if d in ['long', 'buy', 'bullish']:
                direction_counts['long'] += 1
            elif d in ['short', 'sell', 'bearish']:
                direction_counts['short'] += 1

        dominant_direction = max(direction_counts, key=direction_counts.get) if direction_counts else 'neutral'

        # Count confirming signals
        confirming = [
            s for s in signals
            if (s.get('direction') in ['long', 'buy', 'bullish'] and dominant_direction == 'long')
            or (s.get('direction') in ['short', 'sell', 'bearish'] and dominant_direction == 'short')
        ]

        confluence_count = len(confirming)

        # Calculate weighted score
        score = 0.0

        # Same direction bonus
        score += confluence_count * self.confluence_weights['same_direction']

        # Different scanners bonus
        unique_scanners = len(set(s.get('scanner', 'unknown') for s in confirming))
        score += unique_scanners * self.confluence_weights['different_scanner']

        # Institutional confirmation (higher weight for VIX, dark pool, smart money)
        institutional_scanners = ['vix_tracker', 'dark_pool', 'smart_money']
        inst_count = sum(1 for s in confirming if s.get('scanner', '').lower() in institutional_scanners)
        score += inst_count * self.confluence_weights['institutional_confirmation']

        # Regime alignment
        if market_context:
            if (dominant_direction == 'long' and market_context.risk_appetite > 30) or \
               (dominant_direction == 'short' and market_context.risk_appetite < -30):
                score += self.confluence_weights['regime_alignment']

        return confluence_count, score


class RiskManager:
    """
    Position sizing and risk management for orchestrated signals.
    """

    def __init__(
        self,
        max_position_pct: float = 0.1,
        max_portfolio_risk: float = 0.02,
        correlation_penalty: float = 0.3
    ):
        self.max_position_pct = max_position_pct
        self.max_portfolio_risk = max_portfolio_risk
        self.correlation_penalty = correlation_penalty

        self.current_positions: Dict[str, float] = {}
        self.portfolio_risk = 0.0

    def calculate_position_size(
        self,
        signal: Dict,
        conviction: ConvictionLevel,
        volatility: float,
        existing_exposure: float = 0.0
    ) -> float:
        """
        Calculate optimal position size.

        Args:
            signal: Trading signal
            conviction: Conviction level
            volatility: Asset volatility
            existing_exposure: Current directional exposure

        Returns:
            Position size as fraction of portfolio
        """
        # Base position by conviction
        conviction_multipliers = {
            ConvictionLevel.EXTREME: 1.0,
            ConvictionLevel.HIGH: 0.75,
            ConvictionLevel.MODERATE: 0.5,
            ConvictionLevel.LOW: 0.25,
            ConvictionLevel.NONE: 0.0
        }

        base_size = self.max_position_pct * conviction_multipliers.get(conviction, 0.5)

        # Volatility adjustment (reduce for high vol)
        if volatility > 0.3:  # Annualized vol > 30%
            vol_adjustment = 0.3 / volatility
        else:
            vol_adjustment = 1.0

        base_size *= vol_adjustment

        # Correlation/exposure adjustment
        if abs(existing_exposure) > 0.5:
            base_size *= (1 - self.correlation_penalty)

        # Ensure within limits
        base_size = min(base_size, self.max_position_pct)

        # Check portfolio risk constraint
        stop_distance = signal.get('stop_loss_pct', 0.02)
        position_risk = base_size * stop_distance

        if self.portfolio_risk + position_risk > self.max_portfolio_risk:
            # Scale down to fit risk budget
            available_risk = max(0, self.max_portfolio_risk - self.portfolio_risk)
            if stop_distance > 0:
                base_size = min(base_size, available_risk / stop_distance)

        return max(0, base_size)

    def calculate_risk_reward(
        self,
        entry: float,
        stop_loss: float,
        take_profit: float
    ) -> float:
        """Calculate risk/reward ratio."""
        if entry is None or stop_loss is None or take_profit is None:
            return 0.0

        risk = abs(entry - stop_loss)
        reward = abs(take_profit - entry)

        if risk > 0:
            return reward / risk
        return 0.0


class MasterOrchestrator:
    """
    Master orchestrator for all institutional scanners.

    Coordinates scanner execution, signal aggregation,
    and generates unified high-conviction opportunities.
    """

    def __init__(self):
        # Scanner weights (adjusted by regime)
        self.scanner_weights = {
            'vix_tracker': ScannerWeight(
                scanner_name='vix_tracker',
                base_weight=1.5,
                regime_adjustments={'crisis': 2.0, 'high_vol': 1.8, 'low_vol': 0.8},
                volatility_adjustments={'high': 1.5, 'normal': 1.0, 'low': 0.7}
            ),
            'dark_pool': ScannerWeight(
                scanner_name='dark_pool',
                base_weight=1.3,
                regime_adjustments={'bull': 1.2, 'bear': 1.4, 'sideways': 1.0},
                volatility_adjustments={'high': 1.2, 'normal': 1.0, 'low': 1.1}
            ),
            'smart_money': ScannerWeight(
                scanner_name='smart_money',
                base_weight=1.4,
                regime_adjustments={'bull': 1.3, 'bear': 1.3, 'sideways': 0.9},
                volatility_adjustments={'high': 1.1, 'normal': 1.0, 'low': 1.0}
            ),
            'regime_detector': ScannerWeight(
                scanner_name='regime_detector',
                base_weight=1.2,
                regime_adjustments={'transition': 1.8, 'stable': 0.8},
                volatility_adjustments={'high': 1.3, 'normal': 1.0, 'low': 0.9}
            ),
            'cross_asset': ScannerWeight(
                scanner_name='cross_asset',
                base_weight=1.1,
                regime_adjustments={'risk_on': 1.2, 'risk_off': 1.3, 'uncertain': 0.8},
                volatility_adjustments={'high': 1.0, 'normal': 1.0, 'low': 1.0}
            ),
            'order_flow': ScannerWeight(
                scanner_name='order_flow',
                base_weight=1.3,
                regime_adjustments={'bull': 1.1, 'bear': 1.1, 'sideways': 1.3},
                volatility_adjustments={'high': 1.4, 'normal': 1.0, 'low': 0.8}
            )
        }

        # Components
        self.signal_aggregator = SignalAggregator()
        self.confluence_analyzer = ConfluenceAnalyzer()
        self.risk_manager = RiskManager()

        # State
        self.market_context: Optional[MarketContext] = None
        self.unified_signals: List[UnifiedSignal] = []
        self.scanner_results: Dict[str, Any] = {}

        # Scanners (initialized lazily)
        self._scanners = {}

    def _update_weights(self, context: MarketContext):
        """Update scanner weights based on market context."""
        for name, weight_config in self.scanner_weights.items():
            base = weight_config.base_weight

            # Regime adjustment
            regime_key = context.macro_regime.lower() if context.macro_regime else 'normal'
            regime_adj = weight_config.regime_adjustments.get(regime_key, 1.0)

            # Volatility adjustment
            vol_key = context.volatility_regime.lower() if context.volatility_regime else 'normal'
            vol_adj = weight_config.volatility_adjustments.get(vol_key, 1.0)

            weight_config.current_weight = base * regime_adj * vol_adj

    def update_market_context(
        self,
        macro_regime: str = 'normal',
        volatility_regime: str = 'normal',
        risk_appetite: float = 0.0,
        market_breadth: float = 0.0,
        sector_leadership: List[str] = None,
        institutional_activity: str = 'normal',
        trend_strength: float = 0.0
    ):
        """Update current market context."""
        self.market_context = MarketContext(
            macro_regime=macro_regime,
            volatility_regime=volatility_regime,
            risk_appetite=risk_appetite,
            market_breadth=market_breadth,
            sector_leadership=sector_leadership or [],
            institutional_activity=institutional_activity,
            trend_strength=trend_strength
        )

        self._update_weights(self.market_context)

    def add_scanner_result(
        self,
        scanner_name: str,
        result: Dict
    ):
        """
        Add result from a scanner.

        Args:
            scanner_name: Name of the scanner
            result: Scanner result dictionary
        """
        self.scanner_results[scanner_name] = result

        # Extract signals
        signals = result.get('signals', [])
        symbol = result.get('symbol', 'UNKNOWN')

        for signal in signals:
            self.signal_aggregator.add_signal(
                scanner_name=scanner_name,
                symbol=symbol,
                signal=signal
            )

    def _determine_conviction(
        self,
        confluence_count: int,
        confluence_score: float,
        composite_score: float,
        signal_agreement: float
    ) -> ConvictionLevel:
        """Determine conviction level from analysis."""

        # Extreme: Very high confluence, score, and agreement
        if confluence_count >= 4 and composite_score >= 80 and signal_agreement >= 0.8:
            return ConvictionLevel.EXTREME

        # High: Good confluence and scores
        if confluence_count >= 3 and composite_score >= 65 and signal_agreement >= 0.7:
            return ConvictionLevel.HIGH

        # Moderate: Decent confluence or scores
        if confluence_count >= 2 and composite_score >= 50:
            return ConvictionLevel.MODERATE

        # Low: Some signals but limited confluence
        if confluence_count >= 1 and composite_score >= 35:
            return ConvictionLevel.LOW

        return ConvictionLevel.NONE

    def _determine_priority(
        self,
        conviction: ConvictionLevel,
        urgency_score: float,
        risk_reward: float
    ) -> SignalPriority:
        """Determine signal priority."""

        if conviction == ConvictionLevel.EXTREME and risk_reward >= 3:
            return SignalPriority.CRITICAL

        if conviction in [ConvictionLevel.EXTREME, ConvictionLevel.HIGH] and risk_reward >= 2:
            return SignalPriority.HIGH

        if conviction in [ConvictionLevel.HIGH, ConvictionLevel.MODERATE]:
            return SignalPriority.MEDIUM

        if conviction == ConvictionLevel.LOW:
            return SignalPriority.LOW

        return SignalPriority.NOISE

    def _calculate_entry_targets(
        self,
        symbol: str,
        direction: str,
        current_price: float,
        volatility: float
    ) -> Tuple[float, float, float]:
        """Calculate entry, stop loss, and take profit."""

        # Dynamic stop based on volatility
        stop_distance = max(0.005, volatility * 0.5)  # At least 0.5%, up to volatility/2

        if direction == 'long':
            entry = current_price
            stop_loss = current_price * (1 - stop_distance)
            take_profit = current_price * (1 + stop_distance * 2.5)  # 2.5:1 R:R
        elif direction == 'short':
            entry = current_price
            stop_loss = current_price * (1 + stop_distance)
            take_profit = current_price * (1 - stop_distance * 2.5)
        else:
            entry = current_price
            stop_loss = None
            take_profit = None

        return entry, stop_loss, take_profit

    def generate_unified_signals(
        self,
        symbols: List[str],
        prices: Dict[str, float],
        volatilities: Dict[str, float] = None
    ) -> List[UnifiedSignal]:
        """
        Generate unified signals for all symbols.

        Args:
            symbols: List of symbols to analyze
            prices: Current prices for symbols
            volatilities: Optional volatility estimates

        Returns:
            List of unified signals
        """
        self.unified_signals = []

        if volatilities is None:
            volatilities = {s: 0.02 for s in symbols}  # Default 2% daily vol

        # Get current weights
        weights = {
            name: config.current_weight
            for name, config in self.scanner_weights.items()
        }

        for symbol in symbols:
            # Resolve conflicts and get composite score
            resolution = self.signal_aggregator.resolve_conflicts(symbol, weights)

            if resolution['signal_count'] == 0:
                continue

            # Get all signals for this symbol
            all_signals = self.signal_aggregator.signal_buffer.get(symbol, [])

            # Calculate confluence
            confluence_count, confluence_score = self.confluence_analyzer.calculate_confluence(
                all_signals, self.market_context
            )

            # Signal agreement
            total_signals = resolution['long_count'] + resolution['short_count']
            if total_signals > 0:
                if resolution['direction'] == 'long':
                    signal_agreement = resolution['long_count'] / total_signals
                else:
                    signal_agreement = resolution['short_count'] / total_signals
            else:
                signal_agreement = 0

            # Determine conviction
            conviction = self._determine_conviction(
                confluence_count,
                confluence_score,
                resolution['score'],
                signal_agreement
            )

            if conviction == ConvictionLevel.NONE:
                continue

            # Calculate entry/exit targets
            current_price = prices.get(symbol, 100)
            vol = volatilities.get(symbol, 0.02)

            entry, stop_loss, take_profit = self._calculate_entry_targets(
                symbol, resolution['direction'], current_price, vol
            )

            # Risk/reward
            risk_reward = self.risk_manager.calculate_risk_reward(entry, stop_loss, take_profit)

            # Priority
            urgency = confluence_score / 10  # Rough urgency estimate
            priority = self._determine_priority(conviction, urgency, risk_reward)

            # Position size
            position_size = self.risk_manager.calculate_position_size(
                {'stop_loss_pct': abs(current_price - stop_loss) / current_price if stop_loss else 0.02},
                conviction,
                vol * np.sqrt(252)  # Annualized vol
            )

            # Contributing scanners
            contributing = list(set(s.get('scanner', 'unknown') for s in all_signals))

            # Build reasoning
            reasoning_parts = []
            for s in all_signals[:5]:  # Top 5 signals
                if s.get('reasoning'):
                    reasoning_parts.append(f"[{s.get('scanner', 'unknown')}] {s['reasoning']}")

            reasoning = "; ".join(reasoning_parts) if reasoning_parts else "Multiple scanner confluence"

            # Holding period estimate
            if resolution['direction'] in ['long', 'short']:
                if confluence_count >= 4:
                    holding_period = "swing (2-5 days)"
                elif confluence_count >= 2:
                    holding_period = "short-term (1-2 days)"
                else:
                    holding_period = "intraday"
            else:
                holding_period = "N/A"

            # Create unified signal
            unified = UnifiedSignal(
                symbol=symbol,
                direction=resolution['direction'],
                conviction=conviction,
                priority=priority,
                composite_score=resolution['score'],
                entry_price=entry,
                stop_loss=stop_loss,
                take_profit=take_profit,
                position_size_pct=position_size,
                contributing_scanners=contributing,
                scanner_signals={
                    s.get('scanner', 'unknown'): {
                        'direction': s.get('direction'),
                        'strength': s.get('strength'),
                        'confidence': s.get('confidence')
                    }
                    for s in all_signals
                },
                confluence_count=confluence_count,
                reasoning=reasoning,
                risk_reward=risk_reward,
                expected_holding_period=holding_period
            )

            self.unified_signals.append(unified)

        # Sort by priority and score
        self.unified_signals.sort(
            key=lambda x: (x.priority.value, -x.composite_score)
        )

        return self.unified_signals

    def get_top_opportunities(
        self,
        n: int = 5,
        min_conviction: ConvictionLevel = ConvictionLevel.MODERATE
    ) -> List[UnifiedSignal]:
        """
        Get top trading opportunities.

        Args:
            n: Number of opportunities to return
            min_conviction: Minimum conviction level

        Returns:
            Top n opportunities
        """
        conviction_order = [
            ConvictionLevel.EXTREME,
            ConvictionLevel.HIGH,
            ConvictionLevel.MODERATE,
            ConvictionLevel.LOW,
            ConvictionLevel.NONE
        ]

        min_idx = conviction_order.index(min_conviction)

        filtered = [
            s for s in self.unified_signals
            if conviction_order.index(s.conviction) <= min_idx
        ]

        return filtered[:n]

    def get_actionable_signals(
        self,
        max_priority: SignalPriority = SignalPriority.MEDIUM
    ) -> List[UnifiedSignal]:
        """Get signals that require immediate action."""
        return [
            s for s in self.unified_signals
            if s.priority.value <= max_priority.value
        ]

    def get_market_summary(self) -> Dict[str, Any]:
        """Get overall market summary from all scanners."""
        summary = {
            'timestamp': datetime.now().isoformat(),
            'market_context': None,
            'scanner_status': {},
            'signal_summary': {},
            'top_opportunities': []
        }

        if self.market_context:
            summary['market_context'] = {
                'macro_regime': self.market_context.macro_regime,
                'volatility_regime': self.market_context.volatility_regime,
                'risk_appetite': self.market_context.risk_appetite,
                'trend_strength': self.market_context.trend_strength
            }

        # Scanner status
        for name, result in self.scanner_results.items():
            summary['scanner_status'][name] = {
                'signals_generated': len(result.get('signals', [])),
                'last_update': result.get('timestamp', 'unknown')
            }

        # Signal summary
        if self.unified_signals:
            long_signals = [s for s in self.unified_signals if s.direction == 'long']
            short_signals = [s for s in self.unified_signals if s.direction == 'short']

            summary['signal_summary'] = {
                'total_signals': len(self.unified_signals),
                'long_signals': len(long_signals),
                'short_signals': len(short_signals),
                'high_conviction': len([s for s in self.unified_signals if s.conviction in [ConvictionLevel.EXTREME, ConvictionLevel.HIGH]]),
                'actionable': len([s for s in self.unified_signals if s.priority.value <= SignalPriority.MEDIUM.value])
            }

        # Top opportunities
        top = self.get_top_opportunities(5)
        summary['top_opportunities'] = [
            {
                'symbol': s.symbol,
                'direction': s.direction,
                'conviction': s.conviction.value,
                'score': s.composite_score,
                'risk_reward': s.risk_reward
            }
            for s in top
        ]

        return summary

    def run_full_analysis(
        self,
        symbols: List[str],
        prices: Dict[str, float],
        scanner_data: Dict[str, Dict],
        volatilities: Dict[str, float] = None
    ) -> Dict[str, Any]:
        """
        Run complete orchestrated analysis.

        Args:
            symbols: Symbols to analyze
            prices: Current prices
            scanner_data: Results from each scanner
            volatilities: Optional volatility data

        Returns:
            Complete analysis results
        """
        # Clear previous signals
        self.signal_aggregator.clear_buffer()

        # Add all scanner results
        for scanner_name, result in scanner_data.items():
            self.add_scanner_result(scanner_name, result)

        # Generate unified signals
        signals = self.generate_unified_signals(symbols, prices, volatilities)

        # Get summary
        summary = self.get_market_summary()

        return {
            'unified_signals': [
                {
                    'symbol': s.symbol,
                    'direction': s.direction,
                    'conviction': s.conviction.value,
                    'priority': s.priority.value,
                    'composite_score': s.composite_score,
                    'entry_price': s.entry_price,
                    'stop_loss': s.stop_loss,
                    'take_profit': s.take_profit,
                    'position_size_pct': s.position_size_pct,
                    'contributing_scanners': s.contributing_scanners,
                    'confluence_count': s.confluence_count,
                    'risk_reward': s.risk_reward,
                    'reasoning': s.reasoning,
                    'holding_period': s.expected_holding_period
                }
                for s in signals
            ],
            'summary': summary,
            'actionable_count': len(self.get_actionable_signals()),
            'high_conviction_count': len(self.get_top_opportunities(100, ConvictionLevel.HIGH))
        }


def create_master_orchestrator() -> MasterOrchestrator:
    """Factory function to create master orchestrator."""
    return MasterOrchestrator()


# Example usage and testing
if __name__ == "__main__":
    print("="*60)
    print("MASTER SCANNER ORCHESTRATOR - TEST MODE")
    print("="*60)

    # Create orchestrator
    orchestrator = create_master_orchestrator()

    # Set market context
    orchestrator.update_market_context(
        macro_regime='bull',
        volatility_regime='normal',
        risk_appetite=35.0,
        market_breadth=0.65,
        sector_leadership=['XLK', 'XLY'],
        institutional_activity='accumulating',
        trend_strength=0.7
    )

    print("\nMarket Context Updated")
    print(f"  Macro Regime: bull")
    print(f"  Risk Appetite: 35.0")
    print(f"  Trend Strength: 0.7")

    # Simulate scanner results
    symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA']
    prices = {
        'AAPL': 185.50,
        'MSFT': 378.20,
        'GOOGL': 142.80,
        'AMZN': 178.90,
        'NVDA': 495.30
    }

    # Mock scanner results
    scanner_data = {
        'vix_tracker': {
            'symbol': 'AAPL',
            'signals': [
                {
                    'direction': 'long',
                    'strength': 75,
                    'confidence': 0.8,
                    'reasoning': 'VIX term structure bullish'
                }
            ]
        },
        'dark_pool': {
            'symbol': 'AAPL',
            'signals': [
                {
                    'direction': 'long',
                    'strength': 68,
                    'confidence': 0.72,
                    'reasoning': 'Dark pool accumulation detected'
                }
            ]
        },
        'smart_money': {
            'symbol': 'AAPL',
            'signals': [
                {
                    'direction': 'long',
                    'strength': 82,
                    'confidence': 0.85,
                    'reasoning': 'Large call sweeps above ask'
                }
            ]
        },
        'order_flow': {
            'symbol': 'AAPL',
            'signals': [
                {
                    'direction': 'long',
                    'strength': 71,
                    'confidence': 0.75,
                    'reasoning': 'Strong buying pressure'
                }
            ]
        },
        'regime_detector': {
            'symbol': 'AAPL',
            'signals': [
                {
                    'direction': 'long',
                    'strength': 65,
                    'confidence': 0.7,
                    'reasoning': 'Bull quiet regime'
                }
            ]
        },
        'cross_asset': {
            'symbol': 'MSFT',
            'signals': [
                {
                    'direction': 'long',
                    'strength': 60,
                    'confidence': 0.65,
                    'reasoning': 'Tech sector leadership'
                }
            ]
        }
    }

    # Run analysis
    print("\nRunning full orchestrated analysis...")
    results = orchestrator.run_full_analysis(
        symbols=['AAPL'],  # Focus on AAPL for demo
        prices=prices,
        scanner_data=scanner_data
    )

    print(f"\n{'='*60}")
    print("ANALYSIS RESULTS")
    print('='*60)

    print(f"\nUnified Signals: {len(results['unified_signals'])}")
    print(f"Actionable: {results['actionable_count']}")
    print(f"High Conviction: {results['high_conviction_count']}")

    for signal in results['unified_signals']:
        print(f"\n{'-'*40}")
        print(f"Symbol: {signal['symbol']}")
        print(f"Direction: {signal['direction'].upper()}")
        print(f"Conviction: {signal['conviction']}")
        print(f"Priority: {signal['priority']}")
        print(f"Composite Score: {signal['composite_score']:.1f}/100")
        print(f"Entry: ${signal['entry_price']:.2f}")
        print(f"Stop Loss: ${signal['stop_loss']:.2f}")
        print(f"Take Profit: ${signal['take_profit']:.2f}")
        print(f"Position Size: {signal['position_size_pct']:.1%}")
        print(f"Risk/Reward: {signal['risk_reward']:.2f}")
        print(f"Confluence: {signal['confluence_count']} scanners")
        print(f"Contributing: {', '.join(signal['contributing_scanners'])}")
        print(f"Holding Period: {signal['holding_period']}")
        print(f"Reasoning: {signal['reasoning'][:100]}...")

    # Summary
    print(f"\n{'='*60}")
    print("MARKET SUMMARY")
    print('='*60)
    summary = results['summary']

    if summary['market_context']:
        print(f"\nMarket Context:")
        print(f"  Regime: {summary['market_context']['macro_regime']}")
        print(f"  Volatility: {summary['market_context']['volatility_regime']}")
        print(f"  Risk Appetite: {summary['market_context']['risk_appetite']:.1f}")

    if summary['signal_summary']:
        print(f"\nSignal Summary:")
        print(f"  Total: {summary['signal_summary']['total_signals']}")
        print(f"  Long: {summary['signal_summary']['long_signals']}")
        print(f"  Short: {summary['signal_summary']['short_signals']}")
        print(f"  High Conviction: {summary['signal_summary']['high_conviction']}")
        print(f"  Actionable: {summary['signal_summary']['actionable']}")

    print(f"\n{'='*60}")
    print("MASTER ORCHESTRATOR - READY FOR PRODUCTION")
    print('='*60)
