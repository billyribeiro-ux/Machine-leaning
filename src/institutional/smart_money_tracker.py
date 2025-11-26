"""
Revolution Alpha Engine - Smart Money Flow Tracker

ELITE-LEVEL tracking of institutional "smart money" activity.

This module tracks and analyzes the flow of smart money across:
- Options markets (sweep orders, unusual activity)
- Equity markets (block trades, dark pool prints)
- Futures markets (COT positioning)
- Cross-asset flows (sector rotation, risk-on/risk-off)

The goal is to identify where institutions are moving capital
BEFORE it becomes obvious in price action.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
from datetime import datetime, timedelta
from collections import defaultdict


class SmartMoneySignal(Enum):
    """Types of smart money signals."""
    AGGRESSIVE_ACCUMULATION = "aggressive_accumulation"
    AGGRESSIVE_DISTRIBUTION = "aggressive_distribution"
    SECTOR_ROTATION_IN = "sector_rotation_in"
    SECTOR_ROTATION_OUT = "sector_rotation_out"
    RISK_ON = "risk_on"
    RISK_OFF = "risk_off"
    FLIGHT_TO_SAFETY = "flight_to_safety"
    RETURN_TO_RISK = "return_to_risk"
    EARNINGS_POSITIONING = "earnings_positioning"
    MACRO_POSITIONING = "macro_positioning"
    SQUEEZE_SETUP = "squeeze_setup"
    CAPITULATION = "capitulation"


class FlowStrength(Enum):
    """Strength of detected flow."""
    EXTREME = "extreme"
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"


@dataclass
class SmartMoneyAlert:
    """Alert from smart money analysis."""
    timestamp: datetime
    signal_type: SmartMoneySignal
    strength: FlowStrength
    confidence: float

    # What triggered this
    symbols_involved: List[str] = field(default_factory=list)
    sectors_involved: List[str] = field(default_factory=list)

    # Flow details
    estimated_flow_millions: float = 0.0
    flow_direction: str = ""  # 'inflow', 'outflow'
    flow_persistence: int = 0  # Days of consistent flow

    # Evidence
    evidence: List[str] = field(default_factory=list)
    options_evidence: List[str] = field(default_factory=list)
    equity_evidence: List[str] = field(default_factory=list)

    # Prediction
    predicted_impact: str = ""
    predicted_timeframe: str = ""
    historical_accuracy: float = 0.0

    def get_report(self) -> str:
        """Generate alert report."""
        lines = [
            "═" * 70,
            "SMART MONEY FLOW ALERT",
            "═" * 70,
            f"Time: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Signal: {self.signal_type.value.upper().replace('_', ' ')}",
            f"Strength: {self.strength.value.upper()}",
            f"Confidence: {self.confidence:.1f}%",
            "",
            f"Estimated Flow: ${self.estimated_flow_millions:.1f}M {self.flow_direction.upper()}",
            f"Flow Persistence: {self.flow_persistence} days",
            "",
        ]

        if self.symbols_involved:
            lines.append(f"Symbols: {', '.join(self.symbols_involved[:10])}")
        if self.sectors_involved:
            lines.append(f"Sectors: {', '.join(self.sectors_involved)}")

        lines.extend([
            "",
            "─" * 35,
            "OPTIONS EVIDENCE",
            "─" * 35,
        ])
        for ev in self.options_evidence[:5]:
            lines.append(f"• {ev}")

        lines.extend([
            "",
            "─" * 35,
            "EQUITY EVIDENCE",
            "─" * 35,
        ])
        for ev in self.equity_evidence[:5]:
            lines.append(f"• {ev}")

        lines.extend([
            "",
            "─" * 35,
            "PREDICTION",
            "─" * 35,
            f"Impact: {self.predicted_impact}",
            f"Timeframe: {self.predicted_timeframe}",
            f"Historical Accuracy: {self.historical_accuracy:.1f}%",
            "═" * 70,
        ])

        return "\n".join(lines)


@dataclass
class SectorFlow:
    """Flow data for a sector."""
    sector: str
    inflow: float = 0.0
    outflow: float = 0.0
    net_flow: float = 0.0
    flow_rank: int = 0  # 1 = highest inflow
    options_sentiment: float = 0.0  # -1 to 1
    dark_pool_activity: float = 0.0
    institutional_ownership_change: float = 0.0


@dataclass
class SymbolFlow:
    """Flow data for individual symbol."""
    symbol: str
    sector: str

    # Options flow
    call_sweep_volume: int = 0
    put_sweep_volume: int = 0
    call_sweep_premium: float = 0.0
    put_sweep_premium: float = 0.0
    unusual_activity_count: int = 0

    # Equity flow
    dark_pool_volume: int = 0
    block_trade_volume: int = 0
    net_institutional_flow: float = 0.0

    # Derived
    options_sentiment: float = 0.0  # -1 (bearish) to 1 (bullish)
    flow_score: float = 0.0  # Composite score


class OptionsFlowAnalyzer:
    """
    Analyze options flow to detect smart money activity.

    Focuses on:
    - Sweep orders (aggressive, multi-exchange fills)
    - Unusual activity (vol > OI)
    - Large premium trades
    - Opening vs closing positions
    """

    def __init__(self):
        self.sweep_history: List[Dict] = []
        self.unusual_activity: List[Dict] = []

    def analyze_sweeps(self, sweeps_data: pd.DataFrame) -> Dict[str, SymbolFlow]:
        """Analyze sweep orders by symbol."""
        symbol_flows: Dict[str, SymbolFlow] = {}

        if sweeps_data.empty:
            return symbol_flows

        for _, row in sweeps_data.iterrows():
            symbol = row.get('symbol', '')
            if not symbol:
                continue

            if symbol not in symbol_flows:
                symbol_flows[symbol] = SymbolFlow(
                    symbol=symbol,
                    sector=row.get('sector', 'Unknown')
                )

            flow = symbol_flows[symbol]

            opt_type = row.get('type', '').lower()
            volume = int(row.get('volume', 0))
            premium = float(row.get('premium', 0))

            if opt_type == 'call':
                flow.call_sweep_volume += volume
                flow.call_sweep_premium += premium
            else:
                flow.put_sweep_volume += volume
                flow.put_sweep_premium += premium

            # Store for history
            self.sweep_history.append({
                'timestamp': row.get('timestamp', datetime.now()),
                'symbol': symbol,
                'type': opt_type,
                'volume': volume,
                'premium': premium,
                'strike': row.get('strike', 0),
                'expiry': row.get('expiry', ''),
                'side': row.get('side', '')  # buy/sell at bid/ask
            })

        # Calculate sentiment for each symbol
        for symbol, flow in symbol_flows.items():
            total_premium = flow.call_sweep_premium + flow.put_sweep_premium
            if total_premium > 0:
                flow.options_sentiment = (flow.call_sweep_premium - flow.put_sweep_premium) / total_premium
            else:
                flow.options_sentiment = 0

        return symbol_flows

    def detect_unusual_activity(self, options_data: pd.DataFrame) -> List[Dict]:
        """Detect unusual options activity."""
        unusual = []

        if options_data.empty:
            return unusual

        for _, row in options_data.iterrows():
            volume = int(row.get('volume', 0))
            oi = int(row.get('open_interest', 1))
            premium = float(row.get('premium', 0))

            vol_oi_ratio = volume / max(1, oi)

            if vol_oi_ratio > 1.5 or premium > 100000:
                unusual.append({
                    'symbol': row.get('symbol', ''),
                    'type': row.get('type', ''),
                    'strike': row.get('strike', 0),
                    'expiry': row.get('expiry', ''),
                    'volume': volume,
                    'open_interest': oi,
                    'vol_oi_ratio': vol_oi_ratio,
                    'premium': premium,
                    'sentiment': 'bullish' if row.get('type', '').lower() == 'call' else 'bearish'
                })

        self.unusual_activity.extend(unusual)
        return unusual


class SectorRotationTracker:
    """
    Track sector rotation to identify where smart money is flowing.

    Monitors:
    - Relative strength of sectors
    - Flow into/out of sectors
    - Risk-on vs risk-off rotation
    """

    SECTOR_MAP = {
        'XLK': 'Technology',
        'XLF': 'Financials',
        'XLV': 'Healthcare',
        'XLE': 'Energy',
        'XLI': 'Industrials',
        'XLP': 'Consumer Staples',
        'XLY': 'Consumer Discretionary',
        'XLU': 'Utilities',
        'XLB': 'Materials',
        'XLRE': 'Real Estate',
        'XLC': 'Communication Services'
    }

    RISK_ON_SECTORS = ['XLK', 'XLY', 'XLF', 'XLI', 'XLC']
    RISK_OFF_SECTORS = ['XLU', 'XLP', 'XLV', 'XLRE']

    def __init__(self):
        self.sector_flows: Dict[str, List[SectorFlow]] = defaultdict(list)
        self.rotation_history: List[Dict] = []

    def update_sector_flows(self, flow_data: Dict[str, float]):
        """Update sector flow data."""
        timestamp = datetime.now()

        for sector_etf, flow in flow_data.items():
            sector_name = self.SECTOR_MAP.get(sector_etf, sector_etf)
            sector_flow = SectorFlow(
                sector=sector_name,
                net_flow=flow,
                inflow=max(0, flow),
                outflow=abs(min(0, flow))
            )
            self.sector_flows[sector_etf].append(sector_flow)

        # Rank sectors by flow
        current_flows = {k: v[-1].net_flow if v else 0 for k, v in self.sector_flows.items()}
        sorted_sectors = sorted(current_flows.items(), key=lambda x: x[1], reverse=True)

        for rank, (sector, _) in enumerate(sorted_sectors, 1):
            if self.sector_flows[sector]:
                self.sector_flows[sector][-1].flow_rank = rank

    def detect_rotation(self) -> Tuple[str, List[str], List[str]]:
        """
        Detect sector rotation pattern.

        Returns:
            Tuple of (rotation_type, sectors_gaining, sectors_losing)
        """
        if not self.sector_flows:
            return "neutral", [], []

        # Get recent flows
        risk_on_flow = sum(
            self.sector_flows[s][-1].net_flow if self.sector_flows[s] else 0
            for s in self.RISK_ON_SECTORS
        )
        risk_off_flow = sum(
            self.sector_flows[s][-1].net_flow if self.sector_flows[s] else 0
            for s in self.RISK_OFF_SECTORS
        )

        # Find top gainers and losers
        current_flows = {k: v[-1].net_flow if v else 0 for k, v in self.sector_flows.items()}
        sorted_flows = sorted(current_flows.items(), key=lambda x: x[1], reverse=True)

        gainers = [self.SECTOR_MAP.get(s, s) for s, f in sorted_flows[:3] if f > 0]
        losers = [self.SECTOR_MAP.get(s, s) for s, f in sorted_flows[-3:] if f < 0]

        # Determine rotation type
        if risk_on_flow > risk_off_flow * 1.5:
            rotation_type = "risk_on"
        elif risk_off_flow > risk_on_flow * 1.5:
            rotation_type = "risk_off"
        else:
            rotation_type = "neutral"

        return rotation_type, gainers, losers


class SmartMoneyTracker:
    """
    MASTER CLASS: Comprehensive Smart Money Tracking System.

    Integrates:
    - Options flow analysis
    - Sector rotation tracking
    - Dark pool activity
    - Institutional positioning
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}

        # Components
        self.options_analyzer = OptionsFlowAnalyzer()
        self.sector_tracker = SectorRotationTracker()

        # State
        self.symbol_flows: Dict[str, SymbolFlow] = {}
        self.alerts: List[SmartMoneyAlert] = []

        # Historical for pattern matching
        self.flow_history: List[Dict] = []

    def analyze(
        self,
        sweeps_data: Optional[pd.DataFrame] = None,
        options_data: Optional[pd.DataFrame] = None,
        sector_flows: Optional[Dict[str, float]] = None,
        dark_pool_data: Optional[pd.DataFrame] = None
    ) -> List[SmartMoneyAlert]:
        """
        Run comprehensive smart money analysis.

        Args:
            sweeps_data: Options sweep orders
            options_data: Full options data for unusual activity
            sector_flows: Net flows by sector ETF
            dark_pool_data: Dark pool print data

        Returns:
            List of smart money alerts
        """
        alerts = []

        # === ANALYSIS 1: Options Flow ===
        if sweeps_data is not None:
            self.symbol_flows = self.options_analyzer.analyze_sweeps(sweeps_data)

            # Find aggressive positioning
            aggressive_alerts = self._detect_aggressive_positioning()
            alerts.extend(aggressive_alerts)

        # === ANALYSIS 2: Unusual Activity ===
        if options_data is not None:
            unusual = self.options_analyzer.detect_unusual_activity(options_data)

            if len(unusual) > 10:  # Significant unusual activity
                alert = self._create_unusual_activity_alert(unusual)
                if alert:
                    alerts.append(alert)

        # === ANALYSIS 3: Sector Rotation ===
        if sector_flows:
            self.sector_tracker.update_sector_flows(sector_flows)
            rotation_type, gainers, losers = self.sector_tracker.detect_rotation()

            if rotation_type != "neutral":
                alert = self._create_rotation_alert(rotation_type, gainers, losers)
                alerts.append(alert)

        # === ANALYSIS 4: Cross-Symbol Patterns ===
        pattern_alerts = self._detect_cross_symbol_patterns()
        alerts.extend(pattern_alerts)

        # Store alerts
        self.alerts.extend(alerts)

        return alerts

    def _detect_aggressive_positioning(self) -> List[SmartMoneyAlert]:
        """Detect aggressive smart money positioning."""
        alerts = []

        # Find symbols with heavy call sweeps (bullish)
        bullish_symbols = [
            (s, f) for s, f in self.symbol_flows.items()
            if f.call_sweep_premium > f.put_sweep_premium * 2
            and f.call_sweep_premium > 500000  # >$500k premium
        ]

        if bullish_symbols:
            symbols = [s for s, _ in bullish_symbols]
            total_premium = sum(f.call_sweep_premium for _, f in bullish_symbols)

            alert = SmartMoneyAlert(
                timestamp=datetime.now(),
                signal_type=SmartMoneySignal.AGGRESSIVE_ACCUMULATION,
                strength=FlowStrength.STRONG if total_premium > 5000000 else FlowStrength.MODERATE,
                confidence=75,
                symbols_involved=symbols[:20],
                estimated_flow_millions=total_premium / 1000000,
                flow_direction="inflow",
                options_evidence=[
                    f"Heavy call sweep activity in {len(symbols)} symbols",
                    f"Total call premium: ${total_premium:,.0f}",
                    f"Top symbols: {', '.join(symbols[:5])}"
                ],
                predicted_impact="Bullish pressure on affected names",
                predicted_timeframe="Days to weeks"
            )
            alerts.append(alert)

        # Find symbols with heavy put sweeps (bearish)
        bearish_symbols = [
            (s, f) for s, f in self.symbol_flows.items()
            if f.put_sweep_premium > f.call_sweep_premium * 2
            and f.put_sweep_premium > 500000
        ]

        if bearish_symbols:
            symbols = [s for s, _ in bearish_symbols]
            total_premium = sum(f.put_sweep_premium for _, f in bearish_symbols)

            alert = SmartMoneyAlert(
                timestamp=datetime.now(),
                signal_type=SmartMoneySignal.AGGRESSIVE_DISTRIBUTION,
                strength=FlowStrength.STRONG if total_premium > 5000000 else FlowStrength.MODERATE,
                confidence=75,
                symbols_involved=symbols[:20],
                estimated_flow_millions=total_premium / 1000000,
                flow_direction="outflow",
                options_evidence=[
                    f"Heavy put sweep activity in {len(symbols)} symbols",
                    f"Total put premium: ${total_premium:,.0f}",
                    f"Top symbols: {', '.join(symbols[:5])}"
                ],
                predicted_impact="Bearish pressure on affected names",
                predicted_timeframe="Days to weeks"
            )
            alerts.append(alert)

        return alerts

    def _create_unusual_activity_alert(self, unusual: List[Dict]) -> Optional[SmartMoneyAlert]:
        """Create alert for unusual options activity cluster."""
        if len(unusual) < 5:
            return None

        # Aggregate
        symbols = list(set(u['symbol'] for u in unusual))
        total_premium = sum(u['premium'] for u in unusual)

        bullish_count = sum(1 for u in unusual if u['sentiment'] == 'bullish')
        bearish_count = len(unusual) - bullish_count

        if bullish_count > bearish_count * 1.5:
            signal = SmartMoneySignal.AGGRESSIVE_ACCUMULATION
            direction = "inflow"
        elif bearish_count > bullish_count * 1.5:
            signal = SmartMoneySignal.AGGRESSIVE_DISTRIBUTION
            direction = "outflow"
        else:
            signal = SmartMoneySignal.MACRO_POSITIONING
            direction = "mixed"

        return SmartMoneyAlert(
            timestamp=datetime.now(),
            signal_type=signal,
            strength=FlowStrength.STRONG if len(unusual) > 20 else FlowStrength.MODERATE,
            confidence=70,
            symbols_involved=symbols[:20],
            estimated_flow_millions=total_premium / 1000000,
            flow_direction=direction,
            options_evidence=[
                f"Detected {len(unusual)} unusual activity alerts",
                f"Total premium: ${total_premium:,.0f}",
                f"Bullish signals: {bullish_count}, Bearish: {bearish_count}",
                f"Affected symbols: {len(symbols)}"
            ],
            predicted_impact="Elevated volatility in affected names",
            predicted_timeframe="Hours to days"
        )

    def _create_rotation_alert(
        self,
        rotation_type: str,
        gainers: List[str],
        losers: List[str]
    ) -> SmartMoneyAlert:
        """Create sector rotation alert."""
        if rotation_type == "risk_on":
            signal = SmartMoneySignal.RISK_ON
            impact = "Bullish for equities, rotation into growth/cyclicals"
        else:
            signal = SmartMoneySignal.RISK_OFF
            impact = "Defensive positioning, rotation into safety"

        return SmartMoneyAlert(
            timestamp=datetime.now(),
            signal_type=signal,
            strength=FlowStrength.MODERATE,
            confidence=65,
            sectors_involved=gainers + losers,
            flow_direction="rotation",
            equity_evidence=[
                f"Rotation type: {rotation_type.upper()}",
                f"Gaining sectors: {', '.join(gainers)}",
                f"Losing sectors: {', '.join(losers)}"
            ],
            predicted_impact=impact,
            predicted_timeframe="Weeks"
        )

    def _detect_cross_symbol_patterns(self) -> List[SmartMoneyAlert]:
        """Detect patterns across multiple symbols."""
        alerts = []

        if not self.symbol_flows:
            return alerts

        # Check for broad market sentiment
        sentiments = [f.options_sentiment for f in self.symbol_flows.values()]
        if sentiments:
            avg_sentiment = np.mean(sentiments)

            if avg_sentiment > 0.5:
                alert = SmartMoneyAlert(
                    timestamp=datetime.now(),
                    signal_type=SmartMoneySignal.RISK_ON,
                    strength=FlowStrength.MODERATE,
                    confidence=60,
                    options_evidence=[
                        f"Broad bullish sentiment across {len(sentiments)} symbols",
                        f"Average sentiment: {avg_sentiment:.2f}"
                    ],
                    predicted_impact="Bullish market bias",
                    predicted_timeframe="Days"
                )
                alerts.append(alert)
            elif avg_sentiment < -0.5:
                alert = SmartMoneyAlert(
                    timestamp=datetime.now(),
                    signal_type=SmartMoneySignal.RISK_OFF,
                    strength=FlowStrength.MODERATE,
                    confidence=60,
                    options_evidence=[
                        f"Broad bearish sentiment across {len(sentiments)} symbols",
                        f"Average sentiment: {avg_sentiment:.2f}"
                    ],
                    predicted_impact="Bearish market bias",
                    predicted_timeframe="Days"
                )
                alerts.append(alert)

        return alerts

    def get_top_smart_money_picks(self, n: int = 10, direction: str = "bullish") -> List[Tuple[str, float]]:
        """Get top symbols by smart money flow."""
        if not self.symbol_flows:
            return []

        if direction == "bullish":
            sorted_flows = sorted(
                self.symbol_flows.items(),
                key=lambda x: x[1].options_sentiment,
                reverse=True
            )
        else:
            sorted_flows = sorted(
                self.symbol_flows.items(),
                key=lambda x: x[1].options_sentiment
            )

        return [(s, f.options_sentiment) for s, f in sorted_flows[:n]]

    def get_summary(self) -> Dict[str, Any]:
        """Get tracking summary."""
        if not self.symbol_flows:
            return {'symbols_tracked': 0}

        sentiments = [f.options_sentiment for f in self.symbol_flows.values()]

        return {
            'symbols_tracked': len(self.symbol_flows),
            'avg_sentiment': np.mean(sentiments) if sentiments else 0,
            'bullish_symbols': sum(1 for s in sentiments if s > 0.3),
            'bearish_symbols': sum(1 for s in sentiments if s < -0.3),
            'neutral_symbols': sum(1 for s in sentiments if -0.3 <= s <= 0.3),
            'total_call_premium': sum(f.call_sweep_premium for f in self.symbol_flows.values()),
            'total_put_premium': sum(f.put_sweep_premium for f in self.symbol_flows.values()),
            'alerts_generated': len(self.alerts)
        }


# Convenience function
def create_smart_money_tracker(config: Optional[Dict] = None) -> SmartMoneyTracker:
    """Create a configured smart money tracker."""
    return SmartMoneyTracker(config)
