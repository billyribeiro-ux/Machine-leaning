"""
Revolution Alpha Engine - 0DTE SPX Options Scanner
State-of-the-art real-time scanner for 0DTE trading opportunities.

This module provides:
- Real-time opportunity detection
- Multi-criteria filtering
- Risk/reward optimization
- Entry timing signals
- Position sizing recommendations
- Complete trade analysis
"""

import logging
import json
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


class ScannerMode(Enum):
    """Scanner operating mode."""
    AGGRESSIVE = "aggressive"  # Lower thresholds, more signals
    NORMAL = "normal"  # Balanced approach
    CONSERVATIVE = "conservative"  # Higher thresholds, fewer signals
    SCALP = "scalp"  # Quick in/out trades
    SWING = "swing"  # Longer holding period within day


class OpportunityType(Enum):
    """Type of trading opportunity."""
    MOMENTUM_CALL = "momentum_call"
    MOMENTUM_PUT = "momentum_put"
    REVERSAL_CALL = "reversal_call"
    REVERSAL_PUT = "reversal_put"
    BREAKOUT_CALL = "breakout_call"
    BREAKDOWN_PUT = "breakdown_put"
    GAMMA_SQUEEZE_CALL = "gamma_squeeze_call"
    GAMMA_SQUEEZE_PUT = "gamma_squeeze_put"
    FLOW_DRIVEN_CALL = "flow_driven_call"
    FLOW_DRIVEN_PUT = "flow_driven_put"
    SPREAD_CALL = "spread_call"
    SPREAD_PUT = "spread_put"
    IRON_CONDOR = "iron_condor"
    STRADDLE = "straddle"


class AlertPriority(Enum):
    """Alert priority level."""
    CRITICAL = "critical"  # Immediate action required
    HIGH = "high"  # Strong opportunity
    MEDIUM = "medium"  # Good opportunity
    LOW = "low"  # Marginal opportunity


@dataclass
class ScannerConfig:
    """Configuration for the 0DTE scanner."""
    # Mode
    mode: ScannerMode = ScannerMode.NORMAL

    # Confidence thresholds
    min_confidence: float = 70.0
    min_confirmations: int = 4

    # Risk parameters
    max_risk_per_trade: float = 500.0  # Max dollar risk
    max_position_size: int = 10  # Max contracts
    min_risk_reward: float = 1.5

    # Filtering
    min_volume: int = 100
    min_open_interest: int = 500
    max_spread_pct: float = 10.0  # Max bid-ask spread %
    min_delta: float = 0.15
    max_delta: float = 0.70

    # Time filters
    avoid_first_minutes: int = 5  # Avoid first 5 minutes
    avoid_last_minutes: int = 15  # Avoid last 15 minutes
    avoid_lunch: bool = True  # 11:30-13:00

    # Greeks filters
    max_theta_decay_pct: float = 20.0  # Max theta as % of premium
    min_gamma: float = 0.01

    # Flow filters
    require_flow_alignment: bool = True
    min_sweep_premium: float = 50000

    # GEX filters
    use_gex_filter: bool = True


@dataclass
class ScanResult:
    """Individual scan result / opportunity."""
    timestamp: datetime = field(default_factory=datetime.now)
    opportunity_type: OpportunityType = OpportunityType.MOMENTUM_CALL
    priority: AlertPriority = AlertPriority.MEDIUM

    # Instrument details
    symbol: str = "SPX"
    strike: float = 0.0
    expiry: datetime = field(default_factory=datetime.now)
    option_type: str = "call"

    # Pricing
    bid: float = 0.0
    ask: float = 0.0
    mid: float = 0.0
    underlying_price: float = 0.0

    # Greeks
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    iv: float = 0.0

    # Volume/OI
    volume: int = 0
    open_interest: int = 0

    # Analysis scores
    confidence: float = 0.0
    flow_score: float = 0.0
    technical_score: float = 0.0
    gex_score: float = 0.0
    timing_score: float = 0.0

    # Trade setup
    entry_price: float = 0.0
    target_1: float = 0.0
    target_2: float = 0.0
    target_3: float = 0.0
    stop_loss: float = 0.0
    position_size: int = 1

    # Risk metrics
    max_risk: float = 0.0
    max_reward: float = 0.0
    risk_reward_ratio: float = 0.0

    # Context
    confirmations: List[str] = field(default_factory=list)
    alerts: List[str] = field(default_factory=list)
    reasoning: List[str] = field(default_factory=list)

    # Full analysis reference
    full_analysis: Optional[Dict] = None

    def get_summary(self) -> str:
        """Get brief summary of the opportunity."""
        direction = "CALL" if "call" in self.opportunity_type.value else "PUT"
        return (
            f"[{self.priority.value.upper()}] {self.opportunity_type.value.upper()}\n"
            f"SPX {self.strike:.0f} {direction} @ ${self.mid:.2f}\n"
            f"Confidence: {self.confidence:.1f}% | R:R {self.risk_reward_ratio:.1f}:1\n"
            f"Entry: ${self.entry_price:.2f} | Stop: ${self.stop_loss:.2f} | T1: ${self.target_1:.2f}"
        )

    def get_full_report(self) -> str:
        """Get complete analysis report."""
        lines = [
            "=" * 70,
            "0DTE SCANNER OPPORTUNITY REPORT",
            "=" * 70,
            f"Generated: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Priority: {self.priority.value.upper()}",
            f"Type: {self.opportunity_type.value.upper()}",
            "",
            "-" * 35,
            "INSTRUMENT",
            "-" * 35,
            f"Symbol: {self.symbol}",
            f"Strike: {self.strike:.0f}",
            f"Type: {self.option_type.upper()}",
            f"Underlying: ${self.underlying_price:.2f}",
            f"Distance: {((self.strike/self.underlying_price)-1)*100:+.2f}%",
            "",
            "-" * 35,
            "PRICING",
            "-" * 35,
            f"Bid: ${self.bid:.2f}",
            f"Ask: ${self.ask:.2f}",
            f"Mid: ${self.mid:.2f}",
            f"Spread: ${self.ask - self.bid:.2f} ({((self.ask-self.bid)/self.mid)*100:.1f}%)",
            f"IV: {self.iv*100:.1f}%",
            "",
            "-" * 35,
            "GREEKS",
            "-" * 35,
            f"Delta: {self.delta:.3f}",
            f"Gamma: {self.gamma:.4f}",
            f"Theta: ${self.theta:.2f}",
            f"Vega: ${self.vega:.2f}",
            "",
            "-" * 35,
            "VOLUME & INTEREST",
            "-" * 35,
            f"Volume: {self.volume:,}",
            f"Open Interest: {self.open_interest:,}",
            f"Vol/OI Ratio: {self.volume/max(1,self.open_interest):.2f}",
            "",
            "-" * 35,
            "SCORES",
            "-" * 35,
            f"Overall Confidence: {self.confidence:.1f}%",
            f"Flow Score: {self.flow_score:.1f}/100",
            f"Technical Score: {self.technical_score:.1f}/100",
            f"GEX Score: {self.gex_score:.1f}/100",
            f"Timing Score: {self.timing_score:.1f}/100",
            "",
            "-" * 35,
            "TRADE SETUP",
            "-" * 35,
            f"Entry: ${self.entry_price:.2f}",
            f"Position Size: {self.position_size} contracts",
            f"Stop Loss: ${self.stop_loss:.2f} (-{(1-self.stop_loss/self.entry_price)*100:.0f}%)",
            f"Target 1: ${self.target_1:.2f} (+{(self.target_1/self.entry_price-1)*100:.0f}%)",
            f"Target 2: ${self.target_2:.2f} (+{(self.target_2/self.entry_price-1)*100:.0f}%)",
            f"Target 3: ${self.target_3:.2f} (+{(self.target_3/self.entry_price-1)*100:.0f}%)",
            "",
            "-" * 35,
            "RISK METRICS",
            "-" * 35,
            f"Max Risk: ${self.max_risk:.2f}",
            f"Max Reward: ${self.max_reward:.2f}",
            f"Risk/Reward: 1:{self.risk_reward_ratio:.1f}",
            "",
            "-" * 35,
            "CONFIRMATIONS",
            "-" * 35,
        ]

        for conf in self.confirmations:
            lines.append(f"✓ {conf}")

        lines.extend([
            "",
            "-" * 35,
            "REASONING",
            "-" * 35,
        ])

        for i, reason in enumerate(self.reasoning, 1):
            lines.append(f"{i}. {reason}")

        if self.alerts:
            lines.extend([
                "",
                "-" * 35,
                "ALERTS",
                "-" * 35,
            ])
            for alert in self.alerts:
                lines.append(f"⚠ {alert}")

        lines.append("=" * 70)
        return "\n".join(lines)


class ZeroDTEScanner:
    """
    Real-time scanner for 0DTE SPX options opportunities.

    Features:
    - Multi-criteria filtering
    - Risk/reward optimization
    - Entry timing signals
    - Flow-based confirmation
    - GEX-aware positioning
    """

    def __init__(self, config: Optional[ScannerConfig] = None):
        self.config = config or ScannerConfig()

        # Scan results
        self.current_opportunities: List[ScanResult] = []
        self.opportunity_history: deque = deque(maxlen=1000)

        # State
        self.last_scan_time: Optional[datetime] = None
        self.scan_count: int = 0

        # Callbacks
        self.alert_callbacks: List[Callable] = []

    def add_alert_callback(self, callback: Callable[[ScanResult], None]):
        """Add callback for new opportunities."""
        self.alert_callbacks.append(callback)

    def _notify_alert(self, result: ScanResult):
        """Notify all callbacks of new opportunity."""
        for callback in self.alert_callbacks:
            try:
                callback(result)
            except Exception:
                logging.getLogger(__name__).exception("Alert callback error")

    def _is_valid_trading_time(self, dt: Optional[datetime] = None) -> Tuple[bool, str]:
        """Check if current time is valid for trading."""
        dt = dt or datetime.now()
        t = dt.time()

        market_open = time(9, 30)
        market_close = time(16, 0)

        # Before market
        if t < market_open:
            return False, "Market not open yet"

        # After market
        if t >= market_close:
            return False, "Market closed"

        # First minutes
        minutes_since_open = (dt.hour - 9) * 60 + dt.minute - 30
        if minutes_since_open < self.config.avoid_first_minutes:
            return False, f"Avoiding first {self.config.avoid_first_minutes} minutes"

        # Last minutes
        minutes_to_close = (16 - dt.hour) * 60 - dt.minute
        if minutes_to_close < self.config.avoid_last_minutes:
            return False, f"Avoiding last {self.config.avoid_last_minutes} minutes"

        # Lunch period
        if self.config.avoid_lunch:
            if time(11, 30) <= t < time(13, 0):
                return False, "Avoiding lunch period (11:30-13:00)"

        return True, "Valid trading time"

    def _get_timing_score(self, dt: Optional[datetime] = None) -> float:
        """Get timing score (0-100) based on time of day."""
        dt = dt or datetime.now()
        t = dt.time()

        # Calculate minutes since open
        minutes = (dt.hour - 9) * 60 + dt.minute - 30

        # Best times: 10:00-11:30 and 15:00-15:45
        if 30 <= minutes <= 120:  # 10:00-11:30
            return 90.0
        elif 330 <= minutes <= 375:  # 15:00-15:45
            return 85.0
        elif 0 <= minutes < 30:  # 9:30-10:00 (open drive)
            return 75.0
        elif 120 < minutes < 210:  # Lunch
            return 40.0
        else:  # Afternoon
            return 65.0

    def _calculate_flow_score(
        self,
        option_type: str,
        flow_data: Optional[Dict] = None
    ) -> float:
        """Calculate flow alignment score."""
        if flow_data is None:
            return 50.0

        score = 50.0
        is_call = option_type == 'call'

        # Put/Call ratio
        pcr = flow_data.get('put_call_ratio', 1.0)
        if is_call and pcr < 0.7:
            score += 15
        elif not is_call and pcr > 1.3:
            score += 15

        # Sweep activity
        call_sweep = flow_data.get('call_sweep_premium', 0)
        put_sweep = flow_data.get('put_sweep_premium', 0)
        if is_call and call_sweep > put_sweep * 1.5:
            score += 20
        elif not is_call and put_sweep > call_sweep * 1.5:
            score += 20

        # Smart money direction
        smart_money = flow_data.get('smart_money_direction', 'neutral')
        if (is_call and smart_money == 'bullish') or (not is_call and smart_money == 'bearish'):
            score += 15

        return min(100.0, score)

    def _calculate_technical_score(
        self,
        underlying_price: float,
        strike: float,
        option_type: str,
        price_data: Optional[pd.DataFrame] = None
    ) -> float:
        """Calculate technical analysis score."""
        if price_data is None or price_data.empty:
            return 50.0

        score = 50.0
        is_call = option_type == 'call'

        close = price_data['close'].values

        # Trend alignment
        if len(close) >= 20:
            sma_20 = np.mean(close[-20:])
            if is_call and close[-1] > sma_20:
                score += 10
            elif not is_call and close[-1] < sma_20:
                score += 10

        # Momentum
        if len(close) >= 5:
            momentum = (close[-1] / close[-5] - 1) * 100
            if is_call and momentum > 0.5:
                score += 15
            elif not is_call and momentum < -0.5:
                score += 15

        # RSI
        if len(close) >= 14:
            deltas = np.diff(close[-15:])
            gains = np.where(deltas > 0, deltas, 0)
            losses = np.where(deltas < 0, -deltas, 0)
            avg_gain = np.mean(gains)
            avg_loss = np.mean(losses)
            if avg_loss != 0:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))
            else:
                rsi = 100

            if is_call and 40 < rsi < 70:  # Not overbought
                score += 10
            elif not is_call and 30 < rsi < 60:  # Not oversold
                score += 10

        # Strike relative to levels
        distance_pct = abs((strike - underlying_price) / underlying_price) * 100
        if 0.5 <= distance_pct <= 2.0:  # Sweet spot for 0DTE
            score += 15

        return min(100.0, score)

    def _calculate_gex_score(
        self,
        underlying_price: float,
        strike: float,
        option_type: str,
        gex_data: Optional[Dict] = None
    ) -> float:
        """Calculate GEX alignment score."""
        if gex_data is None:
            return 50.0

        score = 50.0
        is_call = option_type == 'call'

        dealer_position = gex_data.get('dealer_position', 'neutral')
        gex_flip = gex_data.get('gex_flip_level', underlying_price)
        pin_strikes = gex_data.get('pin_risk_strikes', [])

        # Dealer positioning
        if dealer_position == 'short_gamma':
            # Trending market expected - good for directional
            score += 15
        elif dealer_position == 'long_gamma':
            # Mean reversion expected - be careful
            score -= 10

        # Position relative to GEX flip
        if is_call and underlying_price > gex_flip:
            score += 10  # In positive gamma zone for calls
        elif not is_call and underlying_price < gex_flip:
            score += 10  # In negative gamma zone for puts

        # Avoid pin risk strikes
        for pin_strike in pin_strikes:
            if abs(strike - pin_strike) < underlying_price * 0.005:
                score -= 20  # Near pin risk
                break

        return max(0.0, min(100.0, score))

    def _calculate_overall_confidence(
        self,
        flow_score: float,
        technical_score: float,
        gex_score: float,
        timing_score: float,
        greeks_valid: bool,
        spread_valid: bool
    ) -> float:
        """Calculate overall confidence score."""
        # Weighted average
        confidence = (
            flow_score * 0.30 +
            technical_score * 0.25 +
            gex_score * 0.20 +
            timing_score * 0.25
        )

        # Penalties
        if not greeks_valid:
            confidence *= 0.8
        if not spread_valid:
            confidence *= 0.9

        return confidence

    def _get_confirmations(
        self,
        flow_score: float,
        technical_score: float,
        gex_score: float,
        timing_score: float,
        option_data: Dict,
        flow_data: Optional[Dict],
        gex_data: Optional[Dict]
    ) -> List[str]:
        """Get list of confirmations."""
        confirmations = []

        # Flow confirmations
        if flow_score >= 70:
            confirmations.append("Options flow aligned with direction")
        if flow_data and flow_data.get('call_sweep_premium', 0) + flow_data.get('put_sweep_premium', 0) > 100000:
            confirmations.append("Heavy sweep activity detected")

        # Technical confirmations
        if technical_score >= 70:
            confirmations.append("Technical indicators aligned")

        # GEX confirmations
        if gex_score >= 70:
            confirmations.append("GEX positioning favorable")
        if gex_data and gex_data.get('dealer_position') == 'short_gamma':
            confirmations.append("Dealers short gamma - trend continuation likely")

        # Timing confirmations
        if timing_score >= 80:
            confirmations.append("Optimal trading time window")

        # Volume confirmations
        if option_data.get('volume', 0) > option_data.get('open_interest', 1) * 0.5:
            confirmations.append("High relative volume")

        # Spread confirmation
        spread_pct = (option_data.get('ask', 0) - option_data.get('bid', 0)) / max(0.01, option_data.get('mid', 1)) * 100
        if spread_pct < 5:
            confirmations.append("Tight bid-ask spread")

        return confirmations

    def _generate_reasoning(
        self,
        opportunity_type: OpportunityType,
        option_data: Dict,
        flow_score: float,
        technical_score: float,
        gex_score: float,
        flow_data: Optional[Dict],
        gex_data: Optional[Dict]
    ) -> List[str]:
        """Generate reasoning for the trade."""
        reasoning = []
        is_call = 'call' in opportunity_type.value

        # Direction reasoning
        if 'momentum' in opportunity_type.value:
            reasoning.append(f"Momentum {'up' if is_call else 'down'} detected - riding the trend")
        elif 'reversal' in opportunity_type.value:
            reasoning.append(f"Potential reversal setup - market {'oversold' if is_call else 'overbought'}")
        elif 'breakout' in opportunity_type.value:
            reasoning.append("Breakout pattern forming - price compression releasing")
        elif 'gamma_squeeze' in opportunity_type.value:
            reasoning.append("Gamma squeeze setup - dealer hedging will amplify move")
        elif 'flow_driven' in opportunity_type.value:
            reasoning.append("Institutional flow driving direction - following smart money")

        # Flow reasoning
        if flow_data:
            pcr = flow_data.get('put_call_ratio', 1.0)
            reasoning.append(f"Put/Call ratio at {pcr:.2f} - {'bullish' if pcr < 0.8 else 'bearish' if pcr > 1.2 else 'neutral'} positioning")

            smart_money = flow_data.get('smart_money_direction', 'neutral')
            reasoning.append(f"Smart money showing {smart_money} bias")

        # GEX reasoning
        if gex_data:
            dealer = gex_data.get('dealer_position', 'neutral')
            if dealer == 'short_gamma':
                reasoning.append("Dealers short gamma - expect trending/volatile action")
            elif dealer == 'long_gamma':
                reasoning.append("Dealers long gamma - expect mean reversion/chop")

            gex_flip = gex_data.get('gex_flip_level', 0)
            if gex_flip > 0:
                reasoning.append(f"GEX flip level at {gex_flip:.0f}")

        # Greeks reasoning
        delta = option_data.get('delta', 0)
        gamma = option_data.get('gamma', 0)
        theta = option_data.get('theta', 0)

        reasoning.append(f"Delta {delta:.2f} provides {abs(delta)*100:.0f}% directional exposure")
        if gamma > 0.05:
            reasoning.append(f"High gamma {gamma:.3f} - position will accelerate quickly")
        reasoning.append(f"Theta decay ${abs(theta):.2f}/day - time pressure {'high' if abs(theta) > 0.3 else 'manageable'}")

        return reasoning

    def scan(
        self,
        options_chain: pd.DataFrame,
        underlying_price: float,
        flow_data: Optional[Dict] = None,
        gex_data: Optional[Dict] = None,
        price_data: Optional[pd.DataFrame] = None
    ) -> List[ScanResult]:
        """
        Scan options chain for opportunities.

        Args:
            options_chain: DataFrame with options data
            underlying_price: Current SPX price
            flow_data: Options flow data
            gex_data: Gamma exposure data
            price_data: Historical price data

        Returns:
            List of scan results / opportunities
        """
        self.scan_count += 1
        self.last_scan_time = datetime.now()

        # Check trading time
        valid_time, time_msg = self._is_valid_trading_time()
        if not valid_time:
            return []

        opportunities = []
        timing_score = self._get_timing_score()

        # Apply mode-based thresholds
        if self.config.mode == ScannerMode.AGGRESSIVE:
            min_confidence = self.config.min_confidence * 0.85
            min_rr = self.config.min_risk_reward * 0.8
        elif self.config.mode == ScannerMode.CONSERVATIVE:
            min_confidence = self.config.min_confidence * 1.15
            min_rr = self.config.min_risk_reward * 1.3
        else:
            min_confidence = self.config.min_confidence
            min_rr = self.config.min_risk_reward

        # Scan each option
        for _, row in options_chain.iterrows():
            option_data = row.to_dict()

            # Basic filters
            if option_data.get('volume', 0) < self.config.min_volume:
                continue
            if option_data.get('open_interest', 0) < self.config.min_open_interest:
                continue

            # Delta filter
            delta = abs(option_data.get('delta', 0))
            if delta < self.config.min_delta or delta > self.config.max_delta:
                continue

            # Spread filter
            bid = option_data.get('bid', 0)
            ask = option_data.get('ask', 0)
            mid = (bid + ask) / 2
            if mid > 0:
                spread_pct = (ask - bid) / mid * 100
                if spread_pct > self.config.max_spread_pct:
                    continue

            option_type = option_data.get('type', 'call')
            strike = option_data.get('strike', underlying_price)

            # Calculate scores
            flow_score = self._calculate_flow_score(option_type, flow_data)
            technical_score = self._calculate_technical_score(
                underlying_price, strike, option_type, price_data
            )
            gex_score = self._calculate_gex_score(
                underlying_price, strike, option_type, gex_data
            )

            # Greeks validation
            gamma = option_data.get('gamma', 0)
            theta = option_data.get('theta', 0)
            greeks_valid = gamma >= self.config.min_gamma
            if mid > 0 and abs(theta / mid * 100) > self.config.max_theta_decay_pct:
                greeks_valid = False

            # Spread validation
            spread_valid = spread_pct < self.config.max_spread_pct * 0.7

            # Overall confidence
            confidence = self._calculate_overall_confidence(
                flow_score, technical_score, gex_score, timing_score,
                greeks_valid, spread_valid
            )

            if confidence < min_confidence:
                continue

            # Determine opportunity type
            is_call = option_type == 'call'
            if flow_score > 75:
                opp_type = OpportunityType.FLOW_DRIVEN_CALL if is_call else OpportunityType.FLOW_DRIVEN_PUT
            elif technical_score > 75:
                opp_type = OpportunityType.MOMENTUM_CALL if is_call else OpportunityType.MOMENTUM_PUT
            elif gex_score > 75 and gex_data and gex_data.get('dealer_position') == 'short_gamma':
                opp_type = OpportunityType.GAMMA_SQUEEZE_CALL if is_call else OpportunityType.GAMMA_SQUEEZE_PUT
            else:
                opp_type = OpportunityType.MOMENTUM_CALL if is_call else OpportunityType.MOMENTUM_PUT

            # Calculate trade setup
            entry_price = ask  # Buy at ask for conservative entry
            stop_loss = entry_price * 0.5  # 50% stop
            target_1 = entry_price * 1.5  # 50% profit
            target_2 = entry_price * 2.0  # 100% profit
            target_3 = entry_price * 3.0  # 200% profit

            # Position sizing
            risk_per_contract = (entry_price - stop_loss) * 100
            if risk_per_contract > 0:
                position_size = min(
                    self.config.max_position_size,
                    int(self.config.max_risk_per_trade / risk_per_contract)
                )
            else:
                position_size = 1

            position_size = max(1, position_size)

            # Risk metrics
            max_risk = risk_per_contract * position_size
            max_reward = (target_2 - entry_price) * 100 * position_size
            risk_reward = max_reward / max(1, max_risk)

            if risk_reward < min_rr:
                continue

            # Get confirmations and reasoning
            confirmations = self._get_confirmations(
                flow_score, technical_score, gex_score, timing_score,
                option_data, flow_data, gex_data
            )

            if len(confirmations) < self.config.min_confirmations:
                continue

            reasoning = self._generate_reasoning(
                opp_type, option_data, flow_score, technical_score, gex_score,
                flow_data, gex_data
            )

            # Determine priority
            if confidence >= 90:
                priority = AlertPriority.CRITICAL
            elif confidence >= 80:
                priority = AlertPriority.HIGH
            elif confidence >= 70:
                priority = AlertPriority.MEDIUM
            else:
                priority = AlertPriority.LOW

            # Create result
            result = ScanResult(
                opportunity_type=opp_type,
                priority=priority,
                strike=strike,
                option_type=option_type,
                bid=bid,
                ask=ask,
                mid=mid,
                underlying_price=underlying_price,
                delta=option_data.get('delta', 0),
                gamma=gamma,
                theta=theta,
                vega=option_data.get('vega', 0),
                iv=option_data.get('iv', 0.2),
                volume=option_data.get('volume', 0),
                open_interest=option_data.get('open_interest', 0),
                confidence=confidence,
                flow_score=flow_score,
                technical_score=technical_score,
                gex_score=gex_score,
                timing_score=timing_score,
                entry_price=entry_price,
                target_1=target_1,
                target_2=target_2,
                target_3=target_3,
                stop_loss=stop_loss,
                position_size=position_size,
                max_risk=max_risk,
                max_reward=max_reward,
                risk_reward_ratio=risk_reward,
                confirmations=confirmations,
                reasoning=reasoning
            )

            opportunities.append(result)

            # Store in history
            self.opportunity_history.append(result)

            # Notify if high priority
            if priority in [AlertPriority.CRITICAL, AlertPriority.HIGH]:
                self._notify_alert(result)

        # Sort by confidence
        opportunities.sort(key=lambda x: x.confidence, reverse=True)
        self.current_opportunities = opportunities

        return opportunities

    def get_best_opportunity(self) -> Optional[ScanResult]:
        """Get the best current opportunity."""
        if not self.current_opportunities:
            return None
        return self.current_opportunities[0]

    def get_opportunities_by_type(
        self,
        opp_type: OpportunityType
    ) -> List[ScanResult]:
        """Get opportunities of a specific type."""
        return [o for o in self.current_opportunities if o.opportunity_type == opp_type]

    def get_opportunities_by_priority(
        self,
        priority: AlertPriority
    ) -> List[ScanResult]:
        """Get opportunities of a specific priority."""
        return [o for o in self.current_opportunities if o.priority == priority]

    def export_opportunities(self, filepath: str, format: str = "json"):
        """Export current opportunities to file."""
        if format == "json":
            data = [
                {
                    'timestamp': o.timestamp.isoformat(),
                    'type': o.opportunity_type.value,
                    'priority': o.priority.value,
                    'strike': o.strike,
                    'option_type': o.option_type,
                    'confidence': o.confidence,
                    'entry': o.entry_price,
                    'stop': o.stop_loss,
                    'targets': [o.target_1, o.target_2, o.target_3],
                    'risk_reward': o.risk_reward_ratio,
                    'confirmations': o.confirmations,
                    'reasoning': o.reasoning
                }
                for o in self.current_opportunities
            ]
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
        else:
            # Text report
            with open(filepath, 'w') as f:
                for o in self.current_opportunities:
                    f.write(o.get_full_report())
                    f.write("\n\n")

        print(f"Exported {len(self.current_opportunities)} opportunities to {filepath}")


class ScannerDashboard:
    """
    Terminal dashboard for the 0DTE scanner.

    Displays real-time opportunities in a formatted view.
    """

    def __init__(self, scanner: ZeroDTEScanner):
        self.scanner = scanner

    def render(self) -> str:
        """Render the dashboard as a string."""
        lines = [
            "╔" + "═" * 78 + "╗",
            "║" + " 0DTE SPX OPTIONS SCANNER ".center(78) + "║",
            "╠" + "═" * 78 + "╣",
        ]

        # Status line
        mode = self.scanner.config.mode.value.upper()
        scan_time = self.scanner.last_scan_time.strftime('%H:%M:%S') if self.scanner.last_scan_time else 'N/A'
        status = f"Mode: {mode} | Last Scan: {scan_time} | Scans: {self.scanner.scan_count}"
        lines.append("║ " + status.ljust(77) + "║")
        lines.append("╠" + "═" * 78 + "╣")

        # Opportunities
        opps = self.scanner.current_opportunities[:10]  # Top 10

        if not opps:
            lines.append("║" + " No opportunities found ".center(78) + "║")
        else:
            # Header
            header = f"{'PRI':<6} {'TYPE':<20} {'STRIKE':<8} {'CONF':<6} {'R:R':<6} {'ENTRY':<8}"
            lines.append("║ " + header.ljust(77) + "║")
            lines.append("║ " + "-" * 77 + "║")

            for opp in opps:
                pri = opp.priority.value[:3].upper()
                typ = opp.opportunity_type.value[:18]
                strike = f"{opp.strike:.0f}"
                conf = f"{opp.confidence:.0f}%"
                rr = f"1:{opp.risk_reward_ratio:.1f}"
                entry = f"${opp.entry_price:.2f}"

                row = f"{pri:<6} {typ:<20} {strike:<8} {conf:<6} {rr:<6} {entry:<8}"
                lines.append("║ " + row.ljust(77) + "║")

        lines.append("╚" + "═" * 78 + "╝")
        return "\n".join(lines)


# Convenience functions
def create_scanner(
    mode: str = "normal",
    min_confidence: float = 70.0,
    max_risk: float = 500.0
) -> ZeroDTEScanner:
    """Create a configured scanner."""
    config = ScannerConfig(
        mode=ScannerMode(mode),
        min_confidence=min_confidence,
        max_risk_per_trade=max_risk
    )
    return ZeroDTEScanner(config)


def create_scanner_dashboard(scanner: ZeroDTEScanner) -> ScannerDashboard:
    """Create a scanner dashboard."""
    return ScannerDashboard(scanner)
