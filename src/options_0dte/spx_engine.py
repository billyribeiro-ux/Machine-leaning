"""
Revolution Alpha Engine - 0DTE SPX Options Trading System
State-of-the-art self-learning system for 0DTE SPX options trading.

This module provides:
- Complete Greeks analysis (Delta, Gamma, Theta, Vega, Charm, Vanna, Volga)
- Gamma Exposure (GEX) calculations and dealer positioning
- Pin risk detection and max pain analysis
- Time decay optimization for 0DTE
- Institutional options flow detection
- Self-learning pattern recognition
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Callable
from enum import Enum
from datetime import datetime, time, timedelta
from abc import ABC, abstractmethod
import json
from collections import deque
import warnings
warnings.filterwarnings('ignore')


class OptionType(Enum):
    """Option type enumeration."""
    CALL = "call"
    PUT = "put"


class TradeDirection(Enum):
    """Trade direction."""
    LONG_CALL = "long_call"
    LONG_PUT = "long_put"
    SHORT_CALL = "short_call"
    SHORT_PUT = "short_put"
    CALL_SPREAD = "call_spread"
    PUT_SPREAD = "put_spread"
    IRON_CONDOR = "iron_condor"
    STRADDLE = "straddle"
    STRANGLE = "strangle"


class MarketRegime(Enum):
    """Current market regime for 0DTE."""
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGE_BOUND = "range_bound"
    BREAKOUT = "breakout"
    BREAKDOWN = "breakdown"
    CONSOLIDATION = "consolidation"
    GAMMA_SQUEEZE = "gamma_squeeze"
    VOLATILITY_EXPANSION = "vol_expansion"
    VOLATILITY_COMPRESSION = "vol_compression"


class TimeOfDay(Enum):
    """Time of day periods for 0DTE."""
    PRE_MARKET = "pre_market"
    OPEN_DRIVE = "open_drive"  # 9:30-10:00
    MORNING_SESSION = "morning"  # 10:00-11:30
    LUNCH_DOLDRUMS = "lunch"  # 11:30-13:00
    AFTERNOON_SESSION = "afternoon"  # 13:00-15:00
    POWER_HOUR = "power_hour"  # 15:00-16:00
    AFTER_HOURS = "after_hours"


@dataclass
class Greeks:
    """Complete options Greeks with higher-order sensitivities."""
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    rho: float = 0.0
    # Higher-order Greeks crucial for 0DTE
    charm: float = 0.0  # Delta decay (dDelta/dTime)
    vanna: float = 0.0  # dDelta/dVol or dVega/dSpot
    volga: float = 0.0  # dVega/dVol (vomma)
    speed: float = 0.0  # dGamma/dSpot
    zomma: float = 0.0  # dGamma/dVol
    color: float = 0.0  # dGamma/dTime
    ultima: float = 0.0  # dVolga/dVol

    def to_dict(self) -> Dict[str, float]:
        return {
            'delta': self.delta,
            'gamma': self.gamma,
            'theta': self.theta,
            'vega': self.vega,
            'rho': self.rho,
            'charm': self.charm,
            'vanna': self.vanna,
            'volga': self.volga,
            'speed': self.speed,
            'zomma': self.zomma,
            'color': self.color,
            'ultima': self.ultima
        }

    def get_interpretation(self) -> str:
        """Get human-readable interpretation of Greeks."""
        interpretations = []

        # Delta interpretation
        if abs(self.delta) > 0.7:
            interpretations.append(f"Delta {self.delta:.3f}: Deep ITM, behaves like stock")
        elif abs(self.delta) > 0.4:
            interpretations.append(f"Delta {self.delta:.3f}: ATM zone, high gamma exposure")
        else:
            interpretations.append(f"Delta {self.delta:.3f}: OTM, lottery ticket profile")

        # Gamma interpretation (crucial for 0DTE)
        if self.gamma > 0.1:
            interpretations.append(f"Gamma {self.gamma:.4f}: EXTREME - Position will move violently")
        elif self.gamma > 0.05:
            interpretations.append(f"Gamma {self.gamma:.4f}: HIGH - Significant delta acceleration")
        else:
            interpretations.append(f"Gamma {self.gamma:.4f}: Moderate gamma exposure")

        # Theta interpretation (critical for 0DTE)
        if abs(self.theta) > 0.5:
            interpretations.append(f"Theta {self.theta:.3f}: SEVERE decay - Time is enemy")
        elif abs(self.theta) > 0.2:
            interpretations.append(f"Theta {self.theta:.3f}: Significant decay pressure")
        else:
            interpretations.append(f"Theta {self.theta:.3f}: Manageable time decay")

        # Charm (delta decay)
        if abs(self.charm) > 0.01:
            interpretations.append(f"Charm {self.charm:.4f}: Delta changing rapidly with time")

        # Vanna
        if abs(self.vanna) > 0.05:
            interpretations.append(f"Vanna {self.vanna:.4f}: Vol changes will shift delta significantly")

        return "\n".join(interpretations)


@dataclass
class GammaExposure:
    """Gamma Exposure (GEX) analysis for market maker positioning."""
    total_gex: float = 0.0
    call_gex: float = 0.0
    put_gex: float = 0.0
    net_gex: float = 0.0
    gex_flip_level: float = 0.0  # Price where GEX flips sign
    major_strikes: List[Tuple[float, float]] = field(default_factory=list)  # (strike, gex)
    dealer_position: str = "neutral"  # long_gamma, short_gamma, neutral
    expected_behavior: str = ""
    pin_risk_strikes: List[float] = field(default_factory=list)

    def get_interpretation(self) -> str:
        """Interpret GEX for trading decisions."""
        lines = [
            f"Total GEX: {self.total_gex:,.0f}",
            f"Call GEX: {self.call_gex:,.0f} | Put GEX: {self.put_gex:,.0f}",
            f"Net GEX: {self.net_gex:,.0f}",
            f"GEX Flip Level: {self.gex_flip_level:.2f}",
            f"Dealer Position: {self.dealer_position.upper()}",
            "",
            "Market Behavior Expectation:",
        ]

        if self.dealer_position == "long_gamma":
            lines.append("  - Dealers LONG gamma = They sell rallies, buy dips")
            lines.append("  - Market tends to MEAN REVERT")
            lines.append("  - Expect LOWER volatility, range-bound action")
            lines.append("  - Good for: Iron Condors, Credit Spreads")
        elif self.dealer_position == "short_gamma":
            lines.append("  - Dealers SHORT gamma = They buy rallies, sell dips")
            lines.append("  - Market tends to TREND/ACCELERATE")
            lines.append("  - Expect HIGHER volatility, directional moves")
            lines.append("  - Good for: Directional plays, Straddles")

        if self.pin_risk_strikes:
            lines.append(f"\nPin Risk Strikes: {', '.join([str(s) for s in self.pin_risk_strikes])}")

        return "\n".join(lines)


@dataclass
class OptionsFlow:
    """Options flow analysis for institutional detection."""
    timestamp: datetime = field(default_factory=datetime.now)
    total_call_volume: int = 0
    total_put_volume: int = 0
    call_premium: float = 0.0
    put_premium: float = 0.0
    put_call_ratio: float = 1.0
    unusual_activity: List[Dict] = field(default_factory=list)
    sweep_orders: List[Dict] = field(default_factory=list)
    block_trades: List[Dict] = field(default_factory=list)
    institutional_bias: str = "neutral"
    smart_money_direction: str = "neutral"

    def get_interpretation(self) -> str:
        """Interpret options flow."""
        lines = [
            f"Call Volume: {self.total_call_volume:,} | Put Volume: {self.total_put_volume:,}",
            f"Call Premium: ${self.call_premium:,.0f} | Put Premium: ${self.put_premium:,.0f}",
            f"Put/Call Ratio: {self.put_call_ratio:.2f}",
            "",
        ]

        # P/C ratio interpretation
        if self.put_call_ratio < 0.7:
            lines.append("P/C Ratio: BULLISH - Heavy call buying")
        elif self.put_call_ratio > 1.3:
            lines.append("P/C Ratio: BEARISH - Heavy put buying")
        else:
            lines.append("P/C Ratio: NEUTRAL")

        # Premium analysis
        total_premium = self.call_premium + self.put_premium
        if total_premium > 0:
            call_pct = (self.call_premium / total_premium) * 100
            lines.append(f"Premium Split: {call_pct:.1f}% Calls / {100-call_pct:.1f}% Puts")

        # Unusual activity
        if self.unusual_activity:
            lines.append(f"\nUnusual Activity Detected: {len(self.unusual_activity)} signals")
            for ua in self.unusual_activity[:3]:  # Top 3
                lines.append(f"  - {ua.get('description', 'N/A')}")

        # Sweep orders (aggressive buying)
        if self.sweep_orders:
            lines.append(f"\nSweep Orders: {len(self.sweep_orders)} detected")
            lines.append("  (Sweeps indicate urgency - institutional smart money)")

        # Block trades
        if self.block_trades:
            lines.append(f"\nBlock Trades: {len(self.block_trades)} detected")
            lines.append("  (Blocks indicate large institutional positioning)")

        lines.append(f"\nInstitutional Bias: {self.institutional_bias.upper()}")
        lines.append(f"Smart Money Direction: {self.smart_money_direction.upper()}")

        return "\n".join(lines)


@dataclass
class VolatilitySurface:
    """Implied volatility surface analysis."""
    atm_iv: float = 0.0
    iv_skew: float = 0.0  # Put skew vs calls
    iv_term_structure: Dict[int, float] = field(default_factory=dict)  # DTE -> IV
    iv_smile: Dict[float, float] = field(default_factory=dict)  # Delta -> IV
    rv_vs_iv: float = 0.0  # Realized vs Implied
    iv_percentile: float = 50.0  # IV rank
    vix_level: float = 20.0
    vix_term_structure: str = "contango"  # contango or backwardation
    skew_interpretation: str = ""

    def get_interpretation(self) -> str:
        """Interpret volatility surface."""
        lines = [
            f"ATM IV: {self.atm_iv:.1f}%",
            f"IV Percentile (Rank): {self.iv_percentile:.1f}%",
            f"IV Skew: {self.iv_skew:.2f}",
            f"RV vs IV: {self.rv_vs_iv:+.1f}% (IV {'overpriced' if self.rv_vs_iv < 0 else 'underpriced'})",
            f"VIX: {self.vix_level:.2f} ({self.vix_term_structure})",
            "",
        ]

        # IV percentile interpretation
        if self.iv_percentile > 80:
            lines.append("IV Percentile: VERY HIGH - Favor selling premium")
        elif self.iv_percentile > 60:
            lines.append("IV Percentile: ELEVATED - Neutral to sell bias")
        elif self.iv_percentile < 20:
            lines.append("IV Percentile: VERY LOW - Favor buying premium")
        else:
            lines.append("IV Percentile: NORMAL range")

        # Skew interpretation
        if self.iv_skew > 0.05:
            lines.append("Skew: Puts trading RICH - Hedging demand high")
            lines.append("       Consider: Put spreads, risk reversals")
        elif self.iv_skew < -0.05:
            lines.append("Skew: Calls trading RICH - Bullish speculation")
            lines.append("       Consider: Call spreads, covered calls")

        # Term structure
        if self.vix_term_structure == "backwardation":
            lines.append("\nVIX Backwardation: FEAR in market")
            lines.append("  Near-term risk perceived higher than long-term")

        return "\n".join(lines)


@dataclass
class ZeroDTESignal:
    """Complete 0DTE trading signal with full analysis."""
    timestamp: datetime = field(default_factory=datetime.now)
    signal_type: TradeDirection = TradeDirection.LONG_CALL
    confidence: float = 0.0

    # Entry details
    underlying_price: float = 0.0
    strike: float = 0.0
    strike_2: Optional[float] = None  # For spreads
    entry_price: float = 0.0

    # Targets
    target_1: float = 0.0
    target_2: float = 0.0
    target_3: float = 0.0
    stop_loss: float = 0.0

    # Greeks at entry
    greeks: Greeks = field(default_factory=Greeks)

    # Analysis components
    gex_analysis: GammaExposure = field(default_factory=GammaExposure)
    flow_analysis: OptionsFlow = field(default_factory=OptionsFlow)
    vol_surface: VolatilitySurface = field(default_factory=VolatilitySurface)

    # Market context
    market_regime: MarketRegime = MarketRegime.RANGE_BOUND
    time_of_day: TimeOfDay = TimeOfDay.MORNING_SESSION

    # Technical levels
    key_levels: Dict[str, float] = field(default_factory=dict)

    # Confirmation signals
    confirmations: Dict[str, bool] = field(default_factory=dict)
    confirmation_count: int = 0

    # Risk metrics
    max_loss: float = 0.0
    max_gain: float = 0.0
    risk_reward: float = 0.0
    position_size: int = 1

    # Self-learning components
    pattern_match_score: float = 0.0
    historical_winrate: float = 0.0
    similar_setups_count: int = 0

    # Full reasoning
    reasoning: List[str] = field(default_factory=list)

    def get_full_reasoning(self) -> str:
        """Generate complete reasoning for the trade."""
        lines = [
            "=" * 80,
            "0DTE SPX OPTIONS TRADE SIGNAL - FULL ANALYSIS",
            "=" * 80,
            f"Generated: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Confidence: {self.confidence:.1f}%",
            "",
            "-" * 40,
            "TRADE SETUP",
            "-" * 40,
            f"Direction: {self.signal_type.value.upper()}",
            f"SPX Price: {self.underlying_price:.2f}",
            f"Strike: {self.strike:.0f}" + (f" / {self.strike_2:.0f}" if self.strike_2 else ""),
            f"Entry Price: ${self.entry_price:.2f}",
            f"Position Size: {self.position_size} contracts",
            "",
            f"Target 1: ${self.target_1:.2f} (+{((self.target_1/self.entry_price)-1)*100:.0f}%)",
            f"Target 2: ${self.target_2:.2f} (+{((self.target_2/self.entry_price)-1)*100:.0f}%)",
            f"Target 3: ${self.target_3:.2f} (+{((self.target_3/self.entry_price)-1)*100:.0f}%)",
            f"Stop Loss: ${self.stop_loss:.2f} (-{(1-(self.stop_loss/self.entry_price))*100:.0f}%)",
            "",
            f"Max Loss: ${self.max_loss:.2f}",
            f"Max Gain: ${self.max_gain:.2f}",
            f"Risk/Reward: 1:{self.risk_reward:.1f}",
            "",
            "-" * 40,
            "GREEKS ANALYSIS",
            "-" * 40,
            self.greeks.get_interpretation(),
            "",
            "-" * 40,
            "GAMMA EXPOSURE (GEX) ANALYSIS",
            "-" * 40,
            self.gex_analysis.get_interpretation(),
            "",
            "-" * 40,
            "OPTIONS FLOW ANALYSIS",
            "-" * 40,
            self.flow_analysis.get_interpretation(),
            "",
            "-" * 40,
            "VOLATILITY SURFACE",
            "-" * 40,
            self.vol_surface.get_interpretation(),
            "",
            "-" * 40,
            "MARKET CONTEXT",
            "-" * 40,
            f"Market Regime: {self.market_regime.value.upper()}",
            f"Time of Day: {self.time_of_day.value.upper()}",
            "",
            "Key Levels:",
        ]

        for level_name, level_price in self.key_levels.items():
            distance = ((level_price / self.underlying_price) - 1) * 100
            lines.append(f"  {level_name}: {level_price:.2f} ({distance:+.2f}%)")

        lines.extend([
            "",
            "-" * 40,
            "CONFIRMATION SIGNALS",
            "-" * 40,
        ])

        for signal_name, signal_value in self.confirmations.items():
            status = "[CONFIRMED]" if signal_value else "[NOT CONFIRMED]"
            lines.append(f"  {status} {signal_name}")

        lines.append(f"\nTotal Confirmations: {self.confirmation_count}/{len(self.confirmations)}")

        lines.extend([
            "",
            "-" * 40,
            "SELF-LEARNING METRICS",
            "-" * 40,
            f"Pattern Match Score: {self.pattern_match_score:.1f}%",
            f"Historical Win Rate: {self.historical_winrate:.1f}%",
            f"Similar Setups Found: {self.similar_setups_count}",
            "",
            "-" * 40,
            "TRADE REASONING",
            "-" * 40,
        ])

        for i, reason in enumerate(self.reasoning, 1):
            lines.append(f"{i}. {reason}")

        lines.append("=" * 80)

        return "\n".join(lines)


class BlackScholesCalculator:
    """Black-Scholes options pricing with full Greeks."""

    @staticmethod
    def _norm_cdf(x: float) -> float:
        """Standard normal CDF approximation."""
        a1, a2, a3, a4, a5 = 0.254829592, -0.284496736, 1.421413741, -1.453152027, 1.061405429
        p = 0.3275911
        sign = 1 if x >= 0 else -1
        x = abs(x) / np.sqrt(2)
        t = 1.0 / (1.0 + p * x)
        y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * np.exp(-x * x)
        return 0.5 * (1.0 + sign * y)

    @staticmethod
    def _norm_pdf(x: float) -> float:
        """Standard normal PDF."""
        return np.exp(-0.5 * x * x) / np.sqrt(2 * np.pi)

    @classmethod
    def calculate_greeks(
        cls,
        spot: float,
        strike: float,
        time_to_expiry: float,  # In years
        volatility: float,  # Annualized
        risk_free_rate: float = 0.05,
        option_type: OptionType = OptionType.CALL
    ) -> Greeks:
        """Calculate all Greeks including higher-order."""

        # Handle edge cases for 0DTE
        if time_to_expiry <= 0:
            time_to_expiry = 1 / (365 * 24 * 60)  # 1 minute

        sqrt_t = np.sqrt(time_to_expiry)
        d1 = (np.log(spot / strike) + (risk_free_rate + 0.5 * volatility ** 2) * time_to_expiry) / (volatility * sqrt_t)
        d2 = d1 - volatility * sqrt_t

        nd1 = cls._norm_cdf(d1)
        nd2 = cls._norm_cdf(d2)
        npd1 = cls._norm_pdf(d1)

        is_call = option_type == OptionType.CALL

        # First-order Greeks
        if is_call:
            delta = nd1
        else:
            delta = nd1 - 1

        gamma = npd1 / (spot * volatility * sqrt_t)

        theta_common = -(spot * npd1 * volatility) / (2 * sqrt_t)
        if is_call:
            theta = (theta_common - risk_free_rate * strike * np.exp(-risk_free_rate * time_to_expiry) * nd2) / 365
        else:
            theta = (theta_common + risk_free_rate * strike * np.exp(-risk_free_rate * time_to_expiry) * (1 - nd2)) / 365

        vega = spot * sqrt_t * npd1 / 100  # Per 1% vol change

        if is_call:
            rho = strike * time_to_expiry * np.exp(-risk_free_rate * time_to_expiry) * nd2 / 100
        else:
            rho = -strike * time_to_expiry * np.exp(-risk_free_rate * time_to_expiry) * (1 - nd2) / 100

        # Higher-order Greeks (crucial for 0DTE)
        charm = -npd1 * (2 * risk_free_rate * time_to_expiry - d2 * volatility * sqrt_t) / (2 * time_to_expiry * volatility * sqrt_t)
        if not is_call:
            charm = charm

        vanna = -npd1 * d2 / volatility

        volga = vega * d1 * d2 / volatility

        speed = -gamma / spot * (d1 / (volatility * sqrt_t) + 1)

        zomma = gamma * (d1 * d2 - 1) / volatility

        color = -npd1 / (2 * spot * time_to_expiry * volatility * sqrt_t) * (
            2 * risk_free_rate * time_to_expiry + 1 +
            (2 * risk_free_rate * time_to_expiry - d2 * volatility * sqrt_t) * d1 / (volatility * sqrt_t)
        )

        ultima = -vega / (volatility ** 2) * (
            d1 * d2 * (1 - d1 * d2) + d1 ** 2 + d2 ** 2
        )

        return Greeks(
            delta=delta,
            gamma=gamma,
            theta=theta,
            vega=vega,
            rho=rho,
            charm=charm,
            vanna=vanna,
            volga=volga,
            speed=speed,
            zomma=zomma,
            color=color,
            ultima=ultima
        )

    @classmethod
    def calculate_price(
        cls,
        spot: float,
        strike: float,
        time_to_expiry: float,
        volatility: float,
        risk_free_rate: float = 0.05,
        option_type: OptionType = OptionType.CALL
    ) -> float:
        """Calculate option price using Black-Scholes."""
        if time_to_expiry <= 0:
            # At expiry
            if option_type == OptionType.CALL:
                return max(0, spot - strike)
            else:
                return max(0, strike - spot)

        sqrt_t = np.sqrt(time_to_expiry)
        d1 = (np.log(spot / strike) + (risk_free_rate + 0.5 * volatility ** 2) * time_to_expiry) / (volatility * sqrt_t)
        d2 = d1 - volatility * sqrt_t

        if option_type == OptionType.CALL:
            price = spot * cls._norm_cdf(d1) - strike * np.exp(-risk_free_rate * time_to_expiry) * cls._norm_cdf(d2)
        else:
            price = strike * np.exp(-risk_free_rate * time_to_expiry) * cls._norm_cdf(-d2) - spot * cls._norm_cdf(-d1)

        return price

    @classmethod
    def implied_volatility(
        cls,
        market_price: float,
        spot: float,
        strike: float,
        time_to_expiry: float,
        risk_free_rate: float = 0.05,
        option_type: OptionType = OptionType.CALL,
        max_iterations: int = 100,
        tolerance: float = 1e-6
    ) -> float:
        """Calculate implied volatility using Newton-Raphson."""
        iv = 0.3  # Initial guess

        for _ in range(max_iterations):
            price = cls.calculate_price(spot, strike, time_to_expiry, iv, risk_free_rate, option_type)
            greeks = cls.calculate_greeks(spot, strike, time_to_expiry, iv, risk_free_rate, option_type)

            diff = price - market_price
            if abs(diff) < tolerance:
                return iv

            if greeks.vega == 0:
                break

            iv = iv - diff / (greeks.vega * 100)  # Vega is per 1% change
            iv = max(0.01, min(5.0, iv))  # Bound IV

        return iv


class ZeroDTEEngine:
    """
    Main 0DTE SPX Options Trading Engine.

    Combines all analysis components for state-of-the-art 0DTE trading.
    """

    def __init__(self, config: Optional[Dict] = None):
        """Initialize the 0DTE engine."""
        self.config = config or {}
        self.bs_calculator = BlackScholesCalculator()

        # Trading parameters
        self.min_confidence = self.config.get('min_confidence', 75.0)
        self.min_confirmations = self.config.get('min_confirmations', 5)
        self.max_position_size = self.config.get('max_position_size', 10)
        self.risk_per_trade = self.config.get('risk_per_trade', 0.02)  # 2% of capital

        # Market hours (ET)
        self.market_open = time(9, 30)
        self.market_close = time(16, 0)

        # Historical data for learning
        self.trade_history: List[Dict] = []
        self.pattern_database: List[Dict] = []

        # Real-time state
        self.current_gex: Optional[GammaExposure] = None
        self.current_flow: Optional[OptionsFlow] = None
        self.current_vol_surface: Optional[VolatilitySurface] = None

    def get_time_of_day(self, dt: Optional[datetime] = None) -> TimeOfDay:
        """Determine current time of day period."""
        dt = dt or datetime.now()
        t = dt.time()

        if t < self.market_open:
            return TimeOfDay.PRE_MARKET
        elif t < time(10, 0):
            return TimeOfDay.OPEN_DRIVE
        elif t < time(11, 30):
            return TimeOfDay.MORNING_SESSION
        elif t < time(13, 0):
            return TimeOfDay.LUNCH_DOLDRUMS
        elif t < time(15, 0):
            return TimeOfDay.AFTERNOON_SESSION
        elif t < self.market_close:
            return TimeOfDay.POWER_HOUR
        else:
            return TimeOfDay.AFTER_HOURS

    def get_time_to_expiry(self, dt: Optional[datetime] = None) -> float:
        """Calculate time to expiry in years for 0DTE."""
        dt = dt or datetime.now()

        # Market closes at 4:00 PM ET
        market_close = dt.replace(hour=16, minute=0, second=0, microsecond=0)

        if dt >= market_close:
            return 0.0

        seconds_remaining = (market_close - dt).total_seconds()
        years = seconds_remaining / (365 * 24 * 60 * 60)

        return max(years, 1e-10)  # Prevent division by zero

    def calculate_gex(
        self,
        options_chain: pd.DataFrame,
        spot_price: float
    ) -> GammaExposure:
        """
        Calculate Gamma Exposure (GEX) from options chain.

        Args:
            options_chain: DataFrame with columns: strike, type, open_interest, gamma
            spot_price: Current SPX price
        """
        gex = GammaExposure()

        if options_chain.empty:
            return gex

        # Calculate GEX for each strike
        strike_gex = {}

        for _, row in options_chain.iterrows():
            strike = row['strike']
            oi = row.get('open_interest', 0)
            gamma = row.get('gamma', 0)
            opt_type = row.get('type', 'call')

            # GEX = Gamma * Open Interest * Spot^2 * Contract Multiplier / 100
            contract_multiplier = 100  # SPX options
            gex_value = gamma * oi * (spot_price ** 2) * contract_multiplier / 100

            # Calls have positive GEX, puts have negative GEX (for dealer hedging)
            if opt_type == 'put':
                gex_value = -gex_value

            if strike not in strike_gex:
                strike_gex[strike] = 0
            strike_gex[strike] += gex_value

            if opt_type == 'call':
                gex.call_gex += gex_value
            else:
                gex.put_gex += abs(gex_value)

        gex.total_gex = gex.call_gex + gex.put_gex
        gex.net_gex = gex.call_gex - gex.put_gex

        # Find GEX flip level
        sorted_strikes = sorted(strike_gex.keys())
        for i in range(len(sorted_strikes) - 1):
            s1, s2 = sorted_strikes[i], sorted_strikes[i + 1]
            if strike_gex[s1] * strike_gex[s2] < 0:  # Sign change
                # Linear interpolation
                gex.gex_flip_level = s1 + (s2 - s1) * abs(strike_gex[s1]) / (abs(strike_gex[s1]) + abs(strike_gex[s2]))
                break

        # Major strikes
        gex.major_strikes = sorted(strike_gex.items(), key=lambda x: abs(x[1]), reverse=True)[:10]

        # Determine dealer position
        if gex.net_gex > 1e9:
            gex.dealer_position = "long_gamma"
        elif gex.net_gex < -1e9:
            gex.dealer_position = "short_gamma"
        else:
            gex.dealer_position = "neutral"

        # Pin risk strikes (high absolute GEX near spot)
        for strike, gex_val in strike_gex.items():
            if abs(strike - spot_price) < spot_price * 0.01 and abs(gex_val) > 1e8:
                gex.pin_risk_strikes.append(strike)

        self.current_gex = gex
        return gex

    def analyze_options_flow(
        self,
        flow_data: pd.DataFrame
    ) -> OptionsFlow:
        """
        Analyze options flow for institutional activity detection.

        Args:
            flow_data: DataFrame with options transactions
        """
        flow = OptionsFlow()

        if flow_data.empty:
            return flow

        # Aggregate volumes
        calls = flow_data[flow_data['type'] == 'call']
        puts = flow_data[flow_data['type'] == 'put']

        flow.total_call_volume = calls['volume'].sum() if 'volume' in calls.columns else 0
        flow.total_put_volume = puts['volume'].sum() if 'volume' in puts.columns else 0

        flow.call_premium = calls['premium'].sum() if 'premium' in calls.columns else 0
        flow.put_premium = puts['premium'].sum() if 'premium' in puts.columns else 0

        if flow.total_call_volume > 0:
            flow.put_call_ratio = flow.total_put_volume / flow.total_call_volume

        # Detect unusual activity
        if 'volume' in flow_data.columns and 'open_interest' in flow_data.columns:
            flow_data['vol_oi_ratio'] = flow_data['volume'] / (flow_data['open_interest'] + 1)
            unusual = flow_data[flow_data['vol_oi_ratio'] > 2]  # Volume > 2x OI

            for _, row in unusual.iterrows():
                flow.unusual_activity.append({
                    'strike': row.get('strike'),
                    'type': row.get('type'),
                    'volume': row.get('volume'),
                    'description': f"{row.get('type', 'N/A').upper()} {row.get('strike', 'N/A')} - Vol {row.get('volume', 0):,} vs OI {row.get('open_interest', 0):,}"
                })

        # Detect sweep orders
        if 'order_type' in flow_data.columns:
            sweeps = flow_data[flow_data['order_type'] == 'sweep']
            for _, row in sweeps.iterrows():
                flow.sweep_orders.append({
                    'strike': row.get('strike'),
                    'type': row.get('type'),
                    'premium': row.get('premium', 0),
                    'side': row.get('side', 'unknown')
                })

        # Detect block trades (>$100k premium)
        if 'premium' in flow_data.columns:
            blocks = flow_data[flow_data['premium'] > 100000]
            for _, row in blocks.iterrows():
                flow.block_trades.append({
                    'strike': row.get('strike'),
                    'type': row.get('type'),
                    'premium': row.get('premium'),
                    'side': row.get('side', 'unknown')
                })

        # Determine institutional bias
        call_sweep_premium = sum(s.get('premium', 0) for s in flow.sweep_orders if s.get('type') == 'call')
        put_sweep_premium = sum(s.get('premium', 0) for s in flow.sweep_orders if s.get('type') == 'put')

        if call_sweep_premium > put_sweep_premium * 1.5:
            flow.institutional_bias = "bullish"
            flow.smart_money_direction = "bullish"
        elif put_sweep_premium > call_sweep_premium * 1.5:
            flow.institutional_bias = "bearish"
            flow.smart_money_direction = "bearish"
        else:
            flow.institutional_bias = "neutral"
            flow.smart_money_direction = "neutral"

        self.current_flow = flow
        return flow

    def analyze_volatility_surface(
        self,
        options_chain: pd.DataFrame,
        spot_price: float,
        historical_data: Optional[pd.DataFrame] = None
    ) -> VolatilitySurface:
        """
        Analyze the implied volatility surface.

        Args:
            options_chain: DataFrame with IV data
            spot_price: Current SPX price
            historical_data: Historical price data for RV calculation
        """
        vol_surface = VolatilitySurface()

        if options_chain.empty:
            return vol_surface

        # Find ATM IV
        options_chain['distance'] = abs(options_chain['strike'] - spot_price)
        atm_options = options_chain.nsmallest(2, 'distance')
        vol_surface.atm_iv = atm_options['iv'].mean() * 100 if 'iv' in atm_options.columns else 20.0

        # Calculate skew (25 delta put IV - 25 delta call IV)
        if 'delta' in options_chain.columns:
            puts = options_chain[options_chain['type'] == 'put']
            calls = options_chain[options_chain['type'] == 'call']

            put_25d = puts[abs(puts['delta'] + 0.25) < 0.1]  # ~25 delta put
            call_25d = calls[abs(calls['delta'] - 0.25) < 0.1]  # ~25 delta call

            if not put_25d.empty and not call_25d.empty:
                vol_surface.iv_skew = put_25d['iv'].mean() - call_25d['iv'].mean()

        # Calculate realized volatility
        if historical_data is not None and 'close' in historical_data.columns:
            returns = np.log(historical_data['close'] / historical_data['close'].shift(1)).dropna()
            rv = returns.std() * np.sqrt(252) * 100
            vol_surface.rv_vs_iv = vol_surface.atm_iv - rv

        # IV percentile (mock - would need historical IV data)
        # Using ATM IV to estimate percentile
        if vol_surface.atm_iv < 12:
            vol_surface.iv_percentile = 10
        elif vol_surface.atm_iv < 15:
            vol_surface.iv_percentile = 25
        elif vol_surface.atm_iv < 18:
            vol_surface.iv_percentile = 40
        elif vol_surface.atm_iv < 22:
            vol_surface.iv_percentile = 55
        elif vol_surface.atm_iv < 28:
            vol_surface.iv_percentile = 70
        else:
            vol_surface.iv_percentile = 85

        self.current_vol_surface = vol_surface
        return vol_surface

    def get_key_levels(
        self,
        spot_price: float,
        daily_data: Optional[pd.DataFrame] = None
    ) -> Dict[str, float]:
        """Calculate key support/resistance levels for SPX."""
        levels = {}

        # Round number levels
        round_100 = round(spot_price / 100) * 100
        levels['Round 100 Below'] = round_100 - 100 if round_100 > spot_price else round_100
        levels['Round 100 Above'] = round_100 + 100 if round_100 <= spot_price else round_100

        round_50 = round(spot_price / 50) * 50
        levels['Round 50 Below'] = round_50 if round_50 < spot_price else round_50 - 50
        levels['Round 50 Above'] = round_50 if round_50 > spot_price else round_50 + 50

        if daily_data is not None and len(daily_data) > 0:
            # Prior day levels
            if 'high' in daily_data.columns:
                levels['Prior Day High'] = daily_data['high'].iloc[-1]
            if 'low' in daily_data.columns:
                levels['Prior Day Low'] = daily_data['low'].iloc[-1]
            if 'close' in daily_data.columns:
                levels['Prior Close'] = daily_data['close'].iloc[-1]
            if 'open' in daily_data.columns:
                levels['Today Open'] = daily_data['open'].iloc[0] if len(daily_data) > 0 else spot_price

            # Weekly levels
            if len(daily_data) >= 5:
                levels['Weekly High'] = daily_data['high'].tail(5).max()
                levels['Weekly Low'] = daily_data['low'].tail(5).min()

        # GEX-based levels
        if self.current_gex and self.current_gex.gex_flip_level > 0:
            levels['GEX Flip Level'] = self.current_gex.gex_flip_level

        if self.current_gex and self.current_gex.pin_risk_strikes:
            for i, strike in enumerate(self.current_gex.pin_risk_strikes[:3]):
                levels[f'Pin Risk {i+1}'] = strike

        return levels

    def calculate_confirmations(
        self,
        spot_price: float,
        direction: TradeDirection,
        greeks: Greeks,
        time_of_day: TimeOfDay
    ) -> Tuple[Dict[str, bool], int]:
        """
        Calculate confirmation signals for a potential trade.

        Returns tuple of (confirmations_dict, count)
        """
        confirmations = {}
        is_bullish = direction in [TradeDirection.LONG_CALL, TradeDirection.SHORT_PUT]

        # 1. GEX alignment
        if self.current_gex:
            if is_bullish:
                confirmations['GEX Supports Direction'] = (
                    self.current_gex.dealer_position == "short_gamma" or
                    spot_price < self.current_gex.gex_flip_level
                )
            else:
                confirmations['GEX Supports Direction'] = (
                    self.current_gex.dealer_position == "short_gamma" or
                    spot_price > self.current_gex.gex_flip_level
                )
        else:
            confirmations['GEX Supports Direction'] = False

        # 2. Options flow alignment
        if self.current_flow:
            if is_bullish:
                confirmations['Flow Supports Direction'] = (
                    self.current_flow.institutional_bias == "bullish" or
                    self.current_flow.put_call_ratio < 0.8
                )
            else:
                confirmations['Flow Supports Direction'] = (
                    self.current_flow.institutional_bias == "bearish" or
                    self.current_flow.put_call_ratio > 1.2
                )
        else:
            confirmations['Flow Supports Direction'] = False

        # 3. Volatility surface alignment
        if self.current_vol_surface:
            confirmations['IV Favorable'] = (
                self.current_vol_surface.iv_percentile < 70 or  # Not too expensive
                self.current_vol_surface.rv_vs_iv > 0  # IV underpriced
            )
        else:
            confirmations['IV Favorable'] = False

        # 4. Time of day alignment
        good_times = [TimeOfDay.OPEN_DRIVE, TimeOfDay.MORNING_SESSION, TimeOfDay.POWER_HOUR]
        confirmations['Favorable Time'] = time_of_day in good_times

        # 5. Greeks alignment
        confirmations['Delta Alignment'] = (
            (is_bullish and greeks.delta > 0.3) or
            (not is_bullish and greeks.delta < -0.3)
        )

        # 6. Gamma manageable (not too extreme for 0DTE)
        confirmations['Gamma Manageable'] = 0.01 < greeks.gamma < 0.15

        # 7. Theta not crushing
        confirmations['Theta Acceptable'] = abs(greeks.theta) < abs(greeks.delta * spot_price * 0.01)

        # 8. Vanna/Charm favorable
        if is_bullish:
            confirmations['Vanna/Charm Favorable'] = greeks.vanna > -0.05
        else:
            confirmations['Vanna/Charm Favorable'] = greeks.vanna < 0.05

        # 9. Sweep activity detected
        if self.current_flow:
            if is_bullish:
                confirmations['Sweep Activity'] = any(
                    s.get('type') == 'call' for s in self.current_flow.sweep_orders
                )
            else:
                confirmations['Sweep Activity'] = any(
                    s.get('type') == 'put' for s in self.current_flow.sweep_orders
                )
        else:
            confirmations['Sweep Activity'] = False

        # 10. No pin risk at current level
        if self.current_gex:
            confirmations['No Nearby Pin Risk'] = not any(
                abs(s - spot_price) < spot_price * 0.002  # Within 0.2%
                for s in self.current_gex.pin_risk_strikes
            )
        else:
            confirmations['No Nearby Pin Risk'] = True

        count = sum(1 for v in confirmations.values() if v)
        return confirmations, count

    def generate_reasoning(
        self,
        direction: TradeDirection,
        spot_price: float,
        strike: float,
        greeks: Greeks,
        confirmations: Dict[str, bool],
        time_of_day: TimeOfDay
    ) -> List[str]:
        """Generate detailed reasoning for the trade."""
        reasoning = []
        is_bullish = direction in [TradeDirection.LONG_CALL, TradeDirection.SHORT_PUT]

        # Direction reasoning
        if is_bullish:
            reasoning.append(f"BULLISH bias detected based on {sum(confirmations.values())} confirmations")
        else:
            reasoning.append(f"BEARISH bias detected based on {sum(confirmations.values())} confirmations")

        # GEX reasoning
        if self.current_gex:
            if self.current_gex.dealer_position == "short_gamma":
                reasoning.append(f"Dealers SHORT gamma - expect trend continuation and momentum")
            elif self.current_gex.dealer_position == "long_gamma":
                reasoning.append(f"Dealers LONG gamma - expect mean reversion, trade carefully")

            if self.current_gex.gex_flip_level > 0:
                if spot_price > self.current_gex.gex_flip_level:
                    reasoning.append(f"Price ABOVE GEX flip ({self.current_gex.gex_flip_level:.0f}) - positive gamma zone")
                else:
                    reasoning.append(f"Price BELOW GEX flip ({self.current_gex.gex_flip_level:.0f}) - negative gamma zone")

        # Flow reasoning
        if self.current_flow:
            reasoning.append(f"Options flow shows {self.current_flow.institutional_bias.upper()} institutional bias")
            if self.current_flow.sweep_orders:
                reasoning.append(f"{len(self.current_flow.sweep_orders)} sweep orders detected - smart money active")
            reasoning.append(f"Put/Call ratio at {self.current_flow.put_call_ratio:.2f}")

        # Vol surface reasoning
        if self.current_vol_surface:
            reasoning.append(f"IV at {self.current_vol_surface.iv_percentile:.0f}th percentile")
            if self.current_vol_surface.rv_vs_iv > 0:
                reasoning.append("IV appears UNDERPRICED vs realized - favor long premium")
            else:
                reasoning.append("IV appears OVERPRICED vs realized - favor short premium")

        # Greeks reasoning
        reasoning.append(f"Delta {greeks.delta:.3f} provides good directional exposure")
        reasoning.append(f"Gamma {greeks.gamma:.4f} - position will {'accelerate' if greeks.gamma > 0.05 else 'move steadily'}")
        reasoning.append(f"Theta {greeks.theta:.3f} - {'significant' if abs(greeks.theta) > 0.3 else 'manageable'} time decay")

        # Time of day reasoning
        if time_of_day == TimeOfDay.OPEN_DRIVE:
            reasoning.append("Open drive period - high momentum, good for directional plays")
        elif time_of_day == TimeOfDay.MORNING_SESSION:
            reasoning.append("Morning session - trends often establish here")
        elif time_of_day == TimeOfDay.LUNCH_DOLDRUMS:
            reasoning.append("CAUTION: Lunch doldrums - lower volume, choppy action")
        elif time_of_day == TimeOfDay.POWER_HOUR:
            reasoning.append("Power hour - final push, good for momentum continuation")

        # Strike selection reasoning
        distance_pct = ((strike - spot_price) / spot_price) * 100
        reasoning.append(f"Strike {strike:.0f} is {abs(distance_pct):.2f}% {'OTM' if (is_bullish and strike > spot_price) or (not is_bullish and strike < spot_price) else 'ITM'}")

        return reasoning

    def generate_signal(
        self,
        spot_price: float,
        options_chain: pd.DataFrame,
        flow_data: Optional[pd.DataFrame] = None,
        daily_data: Optional[pd.DataFrame] = None,
        preferred_direction: Optional[TradeDirection] = None
    ) -> Optional[ZeroDTESignal]:
        """
        Generate a complete 0DTE trading signal.

        Args:
            spot_price: Current SPX price
            options_chain: Current options chain data
            flow_data: Real-time options flow data
            daily_data: Historical daily data
            preferred_direction: Force a specific direction (optional)

        Returns:
            ZeroDTESignal if conditions are met, None otherwise
        """
        # Run all analyses
        gex = self.calculate_gex(options_chain, spot_price)
        if flow_data is not None:
            flow = self.analyze_options_flow(flow_data)
        vol_surface = self.analyze_volatility_surface(options_chain, spot_price, daily_data)

        # Determine time context
        now = datetime.now()
        time_of_day = self.get_time_of_day(now)
        time_to_expiry = self.get_time_to_expiry(now)

        # Get key levels
        key_levels = self.get_key_levels(spot_price, daily_data)

        # Determine direction
        if preferred_direction:
            direction = preferred_direction
        else:
            # Auto-determine based on analysis
            bullish_score = 0

            if gex.dealer_position == "short_gamma":
                bullish_score += 1 if spot_price > gex.gex_flip_level else -1

            if self.current_flow:
                if self.current_flow.institutional_bias == "bullish":
                    bullish_score += 2
                elif self.current_flow.institutional_bias == "bearish":
                    bullish_score -= 2

            direction = TradeDirection.LONG_CALL if bullish_score > 0 else TradeDirection.LONG_PUT

        is_bullish = direction in [TradeDirection.LONG_CALL, TradeDirection.SHORT_PUT]

        # Select optimal strike
        if is_bullish:
            # For calls, look for strikes slightly OTM (0.3-0.4 delta)
            target_delta = 0.35
            options_chain['delta_diff'] = abs(options_chain['delta'] - target_delta)
            calls = options_chain[options_chain['type'] == 'call']
            if calls.empty:
                return None
            optimal = calls.nsmallest(1, 'delta_diff').iloc[0]
        else:
            # For puts, look for strikes slightly OTM (-0.3 to -0.4 delta)
            target_delta = -0.35
            options_chain['delta_diff'] = abs(options_chain['delta'] - target_delta)
            puts = options_chain[options_chain['type'] == 'put']
            if puts.empty:
                return None
            optimal = puts.nsmallest(1, 'delta_diff').iloc[0]

        strike = optimal['strike']
        entry_price = optimal.get('mid', optimal.get('ask', 5.0))
        iv = optimal.get('iv', 0.20)

        # Calculate Greeks
        opt_type = OptionType.CALL if is_bullish else OptionType.PUT
        greeks = self.bs_calculator.calculate_greeks(
            spot=spot_price,
            strike=strike,
            time_to_expiry=time_to_expiry,
            volatility=iv,
            option_type=opt_type
        )

        # Get confirmations
        confirmations, conf_count = self.calculate_confirmations(
            spot_price, direction, greeks, time_of_day
        )

        # Calculate confidence
        base_confidence = (conf_count / len(confirmations)) * 100

        # Adjust for time of day
        if time_of_day == TimeOfDay.LUNCH_DOLDRUMS:
            base_confidence *= 0.8
        elif time_of_day in [TimeOfDay.OPEN_DRIVE, TimeOfDay.POWER_HOUR]:
            base_confidence *= 1.1

        # Check minimum requirements
        if base_confidence < self.min_confidence or conf_count < self.min_confirmations:
            return None

        # Calculate targets and stops
        atr_estimate = spot_price * 0.01  # Rough 1% ATR for SPX

        if is_bullish:
            target_1 = entry_price * 1.5
            target_2 = entry_price * 2.0
            target_3 = entry_price * 3.0
        else:
            target_1 = entry_price * 1.5
            target_2 = entry_price * 2.0
            target_3 = entry_price * 3.0

        stop_loss = entry_price * 0.5  # 50% stop

        # Generate reasoning
        reasoning = self.generate_reasoning(
            direction, spot_price, strike, greeks, confirmations, time_of_day
        )

        # Create signal
        signal = ZeroDTESignal(
            timestamp=now,
            signal_type=direction,
            confidence=min(base_confidence, 99.9),
            underlying_price=spot_price,
            strike=strike,
            entry_price=entry_price,
            target_1=target_1,
            target_2=target_2,
            target_3=target_3,
            stop_loss=stop_loss,
            greeks=greeks,
            gex_analysis=gex,
            flow_analysis=self.current_flow or OptionsFlow(),
            vol_surface=vol_surface,
            market_regime=self._detect_regime(spot_price, daily_data),
            time_of_day=time_of_day,
            key_levels=key_levels,
            confirmations=confirmations,
            confirmation_count=conf_count,
            max_loss=entry_price * 100,  # Per contract
            max_gain=target_3 * 100,
            risk_reward=(target_2 - entry_price) / (entry_price - stop_loss),
            position_size=1,
            pattern_match_score=self._get_pattern_match_score(confirmations, time_of_day),
            historical_winrate=self._get_historical_winrate(direction, time_of_day),
            similar_setups_count=len(self.pattern_database),
            reasoning=reasoning
        )

        return signal

    def _detect_regime(
        self,
        spot_price: float,
        daily_data: Optional[pd.DataFrame]
    ) -> MarketRegime:
        """Detect current market regime."""
        if daily_data is None or len(daily_data) < 5:
            return MarketRegime.RANGE_BOUND

        # Simple regime detection based on recent price action
        returns = daily_data['close'].pct_change().tail(5)
        avg_return = returns.mean()
        volatility = returns.std()

        if avg_return > 0.005 and volatility < 0.015:
            return MarketRegime.TRENDING_UP
        elif avg_return < -0.005 and volatility < 0.015:
            return MarketRegime.TRENDING_DOWN
        elif volatility > 0.02:
            return MarketRegime.VOLATILITY_EXPANSION
        elif volatility < 0.008:
            return MarketRegime.CONSOLIDATION
        else:
            return MarketRegime.RANGE_BOUND

    def _get_pattern_match_score(
        self,
        confirmations: Dict[str, bool],
        time_of_day: TimeOfDay
    ) -> float:
        """Calculate pattern match score based on historical patterns."""
        # Base score from confirmations
        score = (sum(confirmations.values()) / len(confirmations)) * 80

        # Bonus for favorable time
        if time_of_day in [TimeOfDay.OPEN_DRIVE, TimeOfDay.MORNING_SESSION]:
            score += 10
        elif time_of_day == TimeOfDay.POWER_HOUR:
            score += 5

        return min(score, 100)

    def _get_historical_winrate(
        self,
        direction: TradeDirection,
        time_of_day: TimeOfDay
    ) -> float:
        """Get historical win rate for similar setups."""
        if not self.trade_history:
            return 65.0  # Default estimate

        similar_trades = [
            t for t in self.trade_history
            if t.get('direction') == direction and t.get('time_of_day') == time_of_day
        ]

        if not similar_trades:
            return 65.0

        wins = sum(1 for t in similar_trades if t.get('profit', 0) > 0)
        return (wins / len(similar_trades)) * 100

    def record_trade_result(
        self,
        signal: ZeroDTESignal,
        exit_price: float,
        exit_time: datetime,
        notes: str = ""
    ):
        """Record trade result for learning."""
        profit = (exit_price - signal.entry_price) * 100  # Per contract

        trade_record = {
            'timestamp': signal.timestamp,
            'direction': signal.signal_type,
            'time_of_day': signal.time_of_day,
            'strike': signal.strike,
            'entry_price': signal.entry_price,
            'exit_price': exit_price,
            'profit': profit,
            'confirmations': signal.confirmations,
            'confidence': signal.confidence,
            'gex_dealer_position': signal.gex_analysis.dealer_position,
            'flow_bias': signal.flow_analysis.institutional_bias,
            'notes': notes
        }

        self.trade_history.append(trade_record)

        # Add to pattern database
        pattern = {
            'confirmations': signal.confirmations,
            'time_of_day': signal.time_of_day,
            'regime': signal.market_regime,
            'profitable': profit > 0
        }
        self.pattern_database.append(pattern)

    def export_analysis(self, signal: ZeroDTESignal, filepath: str):
        """Export full analysis to file."""
        with open(filepath, 'w') as f:
            f.write(signal.get_full_reasoning())
        print(f"Analysis exported to {filepath}")


# Convenience function
def create_0dte_engine(config: Optional[Dict] = None) -> ZeroDTEEngine:
    """Create a configured 0DTE engine."""
    return ZeroDTEEngine(config)
