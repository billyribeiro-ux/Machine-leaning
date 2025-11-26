"""
Revolution Alpha Engine - Complete Trade Diagnostics System
State-of-the-art analysis showing EVERYTHING behind each trade decision.

This module provides:
- Complete trade reasoning with every factor explained
- Market internals interpretation
- Greeks impact analysis
- Flow attribution
- GEX implications
- Time decay projection
- Risk decomposition
- Historical pattern matching
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
from datetime import datetime, timedelta


class DiagnosticLevel(Enum):
    """Level of diagnostic detail."""
    SUMMARY = "summary"
    STANDARD = "standard"
    DETAILED = "detailed"
    EXHAUSTIVE = "exhaustive"


@dataclass
class MarketInternalsReading:
    """Complete market internals snapshot."""
    timestamp: datetime = field(default_factory=datetime.now)

    # Breadth indicators
    trin: float = 1.0  # Arms Index
    trin_interpretation: str = ""
    tick: float = 0.0  # NYSE TICK
    tick_interpretation: str = ""
    add: float = 0.0  # Advance/Decline
    add_interpretation: str = ""

    # Volume indicators
    uvol: int = 0  # Up volume
    dvol: int = 0  # Down volume
    uvol_dvol_ratio: float = 1.0
    uvol_interpretation: str = ""

    # Volatility indicators
    vix: float = 20.0
    vix_interpretation: str = ""
    vix_term_structure: str = "contango"
    vix9d: float = 18.0  # 9-day VIX
    vvix: float = 100.0  # VIX of VIX

    # Skew indicators
    skew: float = 120.0
    skew_interpretation: str = ""

    # Put/Call data
    put_call_ratio: float = 1.0
    equity_put_call: float = 0.8
    index_put_call: float = 1.2
    put_call_interpretation: str = ""

    # Sector rotation
    sector_rotation: str = "neutral"  # risk_on, risk_off, neutral
    leading_sectors: List[str] = field(default_factory=list)
    lagging_sectors: List[str] = field(default_factory=list)

    def calculate_interpretations(self):
        """Calculate all interpretations."""
        # TRIN interpretation
        if self.trin < 0.75:
            self.trin_interpretation = "EXTREMELY BULLISH - Strong buying pressure, breadth very positive"
        elif self.trin < 0.9:
            self.trin_interpretation = "BULLISH - Good buying pressure, more advances than declines"
        elif self.trin < 1.1:
            self.trin_interpretation = "NEUTRAL - Balanced market breadth"
        elif self.trin < 1.25:
            self.trin_interpretation = "BEARISH - Selling pressure, more declines than advances"
        else:
            self.trin_interpretation = "EXTREMELY BEARISH - Heavy selling, potential capitulation"

        # TICK interpretation
        if self.tick > 800:
            self.tick_interpretation = "EXTREME BULLISH TICK - Massive buying wave, potential exhaustion"
        elif self.tick > 400:
            self.tick_interpretation = "BULLISH TICK - Strong buying momentum"
        elif self.tick > 0:
            self.tick_interpretation = "SLIGHTLY BULLISH TICK - Mild buying interest"
        elif self.tick > -400:
            self.tick_interpretation = "SLIGHTLY BEARISH TICK - Mild selling interest"
        elif self.tick > -800:
            self.tick_interpretation = "BEARISH TICK - Strong selling momentum"
        else:
            self.tick_interpretation = "EXTREME BEARISH TICK - Massive selling wave, potential capitulation"

        # ADD interpretation
        if self.add > 1500:
            self.add_interpretation = "STRONG ADVANCE - Broad market participation to upside"
        elif self.add > 500:
            self.add_interpretation = "MODERATE ADVANCE - Good breadth support"
        elif self.add > -500:
            self.add_interpretation = "NEUTRAL - Mixed advance/decline"
        elif self.add > -1500:
            self.add_interpretation = "MODERATE DECLINE - Breadth weakening"
        else:
            self.add_interpretation = "STRONG DECLINE - Broad selling across market"

        # UVOL/DVOL interpretation
        if self.uvol > 0 and self.dvol > 0:
            self.uvol_dvol_ratio = self.uvol / self.dvol
        if self.uvol_dvol_ratio > 3:
            self.uvol_interpretation = "EXTREMELY BULLISH VOLUME - 3:1 up volume dominance"
        elif self.uvol_dvol_ratio > 1.5:
            self.uvol_interpretation = "BULLISH VOLUME - Up volume leading"
        elif self.uvol_dvol_ratio > 0.67:
            self.uvol_interpretation = "NEUTRAL VOLUME - Balanced volume"
        elif self.uvol_dvol_ratio > 0.33:
            self.uvol_interpretation = "BEARISH VOLUME - Down volume leading"
        else:
            self.uvol_interpretation = "EXTREMELY BEARISH VOLUME - 3:1 down volume dominance"

        # VIX interpretation
        if self.vix < 12:
            self.vix_interpretation = "EXTREME COMPLACENCY - Low fear, potential for vol spike"
        elif self.vix < 16:
            self.vix_interpretation = "LOW VOLATILITY - Calm markets, trending environment"
        elif self.vix < 20:
            self.vix_interpretation = "NORMAL VOLATILITY - Typical market conditions"
        elif self.vix < 25:
            self.vix_interpretation = "ELEVATED VOLATILITY - Increased uncertainty"
        elif self.vix < 30:
            self.vix_interpretation = "HIGH VOLATILITY - Fear increasing, wider ranges"
        else:
            self.vix_interpretation = "EXTREME FEAR - Panic levels, potential capitulation"

        # SKEW interpretation
        if self.skew < 110:
            self.skew_interpretation = "LOW SKEW - Little tail risk hedging, complacency"
        elif self.skew < 120:
            self.skew_interpretation = "NORMAL SKEW - Typical hedging activity"
        elif self.skew < 135:
            self.skew_interpretation = "ELEVATED SKEW - Increased tail risk hedging"
        elif self.skew < 150:
            self.skew_interpretation = "HIGH SKEW - Significant crash protection buying"
        else:
            self.skew_interpretation = "EXTREME SKEW - Heavy tail hedging, crash fear"

        # Put/Call interpretation
        if self.put_call_ratio < 0.7:
            self.put_call_interpretation = "EXTREMELY BULLISH P/C - Heavy call buying, potential top"
        elif self.put_call_ratio < 0.85:
            self.put_call_interpretation = "BULLISH P/C - Call buying dominates"
        elif self.put_call_ratio < 1.1:
            self.put_call_interpretation = "NEUTRAL P/C - Balanced options activity"
        elif self.put_call_ratio < 1.3:
            self.put_call_interpretation = "BEARISH P/C - Put buying dominates"
        else:
            self.put_call_interpretation = "EXTREMELY BEARISH P/C - Heavy put buying, potential bottom"

    def get_full_report(self) -> str:
        """Generate complete market internals report."""
        self.calculate_interpretations()

        lines = [
            "=" * 80,
            "MARKET INTERNALS DIAGNOSTIC REPORT",
            "=" * 80,
            f"Timestamp: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "-" * 40,
            "BREADTH INDICATORS",
            "-" * 40,
            f"TRIN (Arms Index): {self.trin:.2f}",
            f"  → {self.trin_interpretation}",
            "",
            f"NYSE TICK: {self.tick:+.0f}",
            f"  → {self.tick_interpretation}",
            "",
            f"Advance/Decline (ADD): {self.add:+.0f}",
            f"  → {self.add_interpretation}",
            "",
            "-" * 40,
            "VOLUME INDICATORS",
            "-" * 40,
            f"Up Volume (UVOL): {self.uvol:,}",
            f"Down Volume (DVOL): {self.dvol:,}",
            f"UVOL/DVOL Ratio: {self.uvol_dvol_ratio:.2f}",
            f"  → {self.uvol_interpretation}",
            "",
            "-" * 40,
            "VOLATILITY INDICATORS",
            "-" * 40,
            f"VIX: {self.vix:.2f}",
            f"  → {self.vix_interpretation}",
            f"VIX Term Structure: {self.vix_term_structure.upper()}",
            f"VIX9D: {self.vix9d:.2f}",
            f"VVIX: {self.vvix:.2f}",
            "",
            "-" * 40,
            "SKEW & OPTIONS",
            "-" * 40,
            f"CBOE SKEW: {self.skew:.2f}",
            f"  → {self.skew_interpretation}",
            "",
            f"Total Put/Call: {self.put_call_ratio:.2f}",
            f"Equity P/C: {self.equity_put_call:.2f}",
            f"Index P/C: {self.index_put_call:.2f}",
            f"  → {self.put_call_interpretation}",
            "",
            "-" * 40,
            "SECTOR ROTATION",
            "-" * 40,
            f"Rotation Bias: {self.sector_rotation.upper()}",
        ]

        if self.leading_sectors:
            lines.append(f"Leading: {', '.join(self.leading_sectors)}")
        if self.lagging_sectors:
            lines.append(f"Lagging: {', '.join(self.lagging_sectors)}")

        lines.append("=" * 80)
        return "\n".join(lines)


@dataclass
class GreeksImpactAnalysis:
    """Analysis of how Greeks will impact the position."""
    # Current Greeks
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    charm: float = 0.0
    vanna: float = 0.0

    # Position details
    contracts: int = 1
    entry_price: float = 1.0
    underlying_price: float = 4500.0

    # Impact projections
    delta_pnl_1pt: float = 0.0  # P&L for $1 move
    delta_pnl_10pt: float = 0.0  # P&L for $10 move
    gamma_acceleration: float = 0.0  # How delta changes
    theta_decay_1hr: float = 0.0  # Theta per hour
    theta_decay_eod: float = 0.0  # Theta to end of day
    vega_impact_1pct: float = 0.0  # P&L for 1% IV change

    # Risk scenarios
    scenario_up_10: float = 0.0  # P&L if underlying +10
    scenario_down_10: float = 0.0  # P&L if underlying -10
    scenario_vol_up: float = 0.0  # P&L if IV +5%
    scenario_vol_down: float = 0.0  # P&L if IV -5%

    def calculate_impacts(self, hours_to_close: float = 6.5):
        """Calculate all impact projections."""
        multiplier = 100 * self.contracts

        # Delta P&L
        self.delta_pnl_1pt = self.delta * 1 * multiplier
        self.delta_pnl_10pt = self.delta * 10 * multiplier

        # Gamma acceleration
        self.gamma_acceleration = self.gamma * multiplier

        # Theta decay
        theta_per_hour = self.theta / 6.5  # Approx trading hours
        self.theta_decay_1hr = theta_per_hour * multiplier
        self.theta_decay_eod = self.theta * hours_to_close / 6.5 * multiplier

        # Vega impact
        self.vega_impact_1pct = self.vega * 1 * multiplier  # Vega is per 1% already

        # Scenario analysis (simplified Black-Scholes approximation)
        # +10 points
        new_delta_up = self.delta + self.gamma * 10
        avg_delta_up = (self.delta + new_delta_up) / 2
        self.scenario_up_10 = avg_delta_up * 10 * multiplier

        # -10 points
        new_delta_down = self.delta - self.gamma * 10
        avg_delta_down = (self.delta + new_delta_down) / 2
        self.scenario_down_10 = avg_delta_down * -10 * multiplier

        # Vol up 5%
        self.scenario_vol_up = self.vega * 5 * multiplier

        # Vol down 5%
        self.scenario_vol_down = self.vega * -5 * multiplier

    def get_full_report(self) -> str:
        """Generate complete Greeks impact report."""
        self.calculate_impacts()

        lines = [
            "=" * 70,
            "GREEKS IMPACT ANALYSIS",
            "=" * 70,
            f"Position: {self.contracts} contracts @ ${self.entry_price:.2f}",
            f"Underlying: ${self.underlying_price:.2f}",
            "",
            "-" * 35,
            "CURRENT GREEKS",
            "-" * 35,
            f"Delta: {self.delta:+.4f}",
            f"  Each $1 move = ${self.delta_pnl_1pt:+.2f}",
            f"  Each $10 move = ${self.delta_pnl_10pt:+.2f}",
            "",
            f"Gamma: {self.gamma:.5f}",
            f"  Position acceleration: {self.gamma_acceleration:.3f} delta per $1",
            f"  (Delta will {'increase' if self.gamma > 0 else 'decrease'} as price moves in your direction)",
            "",
            f"Theta: ${self.theta:.3f}/day",
            f"  Decay per hour: ${self.theta_decay_1hr:.2f}",
            f"  Decay to EOD: ${self.theta_decay_eod:.2f}",
            f"  {'WARNING: High theta decay!' if abs(self.theta) > 0.3 else 'Theta manageable'}",
            "",
            f"Vega: ${self.vega:.3f} per 1% IV",
            f"  1% IV increase: ${self.vega_impact_1pct:+.2f}",
            f"  1% IV decrease: ${-self.vega_impact_1pct:+.2f}",
            "",
            "-" * 35,
            "HIGHER ORDER GREEKS",
            "-" * 35,
            f"Charm: {self.charm:.5f}",
            f"  (Delta is {'decaying' if self.charm < 0 else 'increasing'} with time)",
            "",
            f"Vanna: {self.vanna:.5f}",
            f"  (Sensitivity of delta to volatility changes)",
            "",
            "-" * 35,
            "SCENARIO ANALYSIS",
            "-" * 35,
            f"SPX +$10: ${self.scenario_up_10:+.2f}",
            f"SPX -$10: ${self.scenario_down_10:+.2f}",
            f"IV +5%:   ${self.scenario_vol_up:+.2f}",
            f"IV -5%:   ${self.scenario_vol_down:+.2f}",
            "",
            "-" * 35,
            "KEY INSIGHTS",
            "-" * 35,
        ]

        # Generate insights
        if abs(self.gamma) > 0.05:
            lines.append("• HIGH GAMMA: Position will move rapidly with underlying")
        if abs(self.theta) > abs(self.delta * 5):
            lines.append("• THETA DOMINANT: Time decay outpacing delta gains")
        if abs(self.vanna) > 0.05:
            lines.append("• HIGH VANNA: Volatility changes will shift delta significantly")

        lines.append("=" * 70)
        return "\n".join(lines)


@dataclass
class FlowAttribution:
    """Attribution of trade decision to flow signals."""
    # Flow components
    call_sweep_signal: float = 0.0  # -1 to 1
    put_sweep_signal: float = 0.0
    block_trade_signal: float = 0.0
    retail_flow_signal: float = 0.0
    institutional_flow_signal: float = 0.0

    # Premium analysis
    total_call_premium: float = 0.0
    total_put_premium: float = 0.0
    net_premium_direction: str = "neutral"

    # Unusual activity
    unusual_strikes: List[Dict] = field(default_factory=list)

    # Attribution weights
    flow_contribution: float = 0.0  # % of signal from flow

    def get_attribution_report(self) -> str:
        """Generate flow attribution report."""
        lines = [
            "-" * 50,
            "FLOW ATTRIBUTION",
            "-" * 50,
            f"Flow Contribution to Signal: {self.flow_contribution:.1f}%",
            "",
            "Signal Components:",
            f"  Call Sweeps: {self.call_sweep_signal:+.2f}",
            f"  Put Sweeps: {self.put_sweep_signal:+.2f}",
            f"  Block Trades: {self.block_trade_signal:+.2f}",
            f"  Institutional Flow: {self.institutional_flow_signal:+.2f}",
            f"  Retail Flow: {self.retail_flow_signal:+.2f}",
            "",
            "Premium Analysis:",
            f"  Call Premium: ${self.total_call_premium:,.0f}",
            f"  Put Premium: ${self.total_put_premium:,.0f}",
            f"  Net Direction: {self.net_premium_direction.upper()}",
        ]

        if self.unusual_strikes:
            lines.append("\nUnusual Activity at Strikes:")
            for ua in self.unusual_strikes[:5]:
                lines.append(f"  • {ua.get('strike', 'N/A')}: {ua.get('description', 'N/A')}")

        return "\n".join(lines)


@dataclass
class GEXAnalysis:
    """Detailed GEX analysis for the trade."""
    # GEX levels
    total_gex: float = 0.0
    call_gex: float = 0.0
    put_gex: float = 0.0
    net_gex: float = 0.0
    gex_flip_level: float = 0.0

    # Dealer positioning
    dealer_position: str = "neutral"
    dealer_hedge_direction: str = ""

    # Key strikes
    high_gamma_strikes: List[Tuple[float, float]] = field(default_factory=list)
    pin_risk_strikes: List[float] = field(default_factory=list)

    # Expected behavior
    volatility_expectation: str = "normal"
    trending_expectation: str = "neutral"

    def get_gex_report(self) -> str:
        """Generate GEX analysis report."""
        lines = [
            "-" * 50,
            "GAMMA EXPOSURE (GEX) ANALYSIS",
            "-" * 50,
            f"Total GEX: {self.total_gex:,.0f}",
            f"Call GEX: {self.call_gex:,.0f}",
            f"Put GEX: {self.put_gex:,.0f}",
            f"Net GEX: {self.net_gex:,.0f}",
            "",
            f"GEX Flip Level: {self.gex_flip_level:.2f}",
            f"Dealer Position: {self.dealer_position.upper()}",
            "",
            "Market Behavior Expectation:",
        ]

        if self.dealer_position == "long_gamma":
            lines.extend([
                "  • Dealers are LONG gamma",
                "  • They will SELL rallies and BUY dips",
                "  • Expect MEAN REVERSION",
                "  • Volatility likely to be COMPRESSED",
                "  • Range-bound action more likely",
            ])
        elif self.dealer_position == "short_gamma":
            lines.extend([
                "  • Dealers are SHORT gamma",
                "  • They will BUY rallies and SELL dips",
                "  • Expect TREND CONTINUATION",
                "  • Volatility likely to be ELEVATED",
                "  • Directional moves more likely",
            ])

        if self.high_gamma_strikes:
            lines.append("\nHigh Gamma Strikes (magnetic levels):")
            for strike, gex in self.high_gamma_strikes[:5]:
                lines.append(f"  • {strike:.0f}: {gex:,.0f} GEX")

        if self.pin_risk_strikes:
            lines.append(f"\nPin Risk Strikes: {', '.join([f'{s:.0f}' for s in self.pin_risk_strikes])}")

        return "\n".join(lines)


@dataclass
class CompleteTradeDiagnostics:
    """Complete diagnostic report for a trade decision."""
    timestamp: datetime = field(default_factory=datetime.now)
    diagnostic_level: DiagnosticLevel = DiagnosticLevel.DETAILED

    # Trade details
    direction: str = "LONG_CALL"
    strike: float = 0.0
    entry_price: float = 0.0
    contracts: int = 1
    underlying_price: float = 0.0

    # Component analyses
    market_internals: MarketInternalsReading = field(default_factory=MarketInternalsReading)
    greeks_impact: GreeksImpactAnalysis = field(default_factory=GreeksImpactAnalysis)
    flow_attribution: FlowAttribution = field(default_factory=FlowAttribution)
    gex_analysis: GEXAnalysis = field(default_factory=GEXAnalysis)

    # Overall scores
    confidence: float = 0.0
    market_alignment_score: float = 0.0
    timing_score: float = 0.0
    risk_score: float = 0.0

    # Decision factors
    bullish_factors: List[str] = field(default_factory=list)
    bearish_factors: List[str] = field(default_factory=list)
    neutral_factors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # Final reasoning
    primary_reason: str = ""
    supporting_reasons: List[str] = field(default_factory=list)
    trade_thesis: str = ""

    def compile_decision_factors(self):
        """Compile all factors influencing the decision."""
        self.bullish_factors = []
        self.bearish_factors = []
        self.neutral_factors = []
        self.warnings = []

        # Market internals factors
        if self.market_internals.trin < 0.9:
            self.bullish_factors.append(f"TRIN at {self.market_internals.trin:.2f} shows bullish breadth")
        elif self.market_internals.trin > 1.1:
            self.bearish_factors.append(f"TRIN at {self.market_internals.trin:.2f} shows bearish breadth")

        if self.market_internals.tick > 400:
            self.bullish_factors.append(f"TICK at {self.market_internals.tick:+.0f} shows buying pressure")
        elif self.market_internals.tick < -400:
            self.bearish_factors.append(f"TICK at {self.market_internals.tick:+.0f} shows selling pressure")

        if self.market_internals.uvol_dvol_ratio > 1.5:
            self.bullish_factors.append(f"Up volume dominating ({self.market_internals.uvol_dvol_ratio:.1f}x)")
        elif self.market_internals.uvol_dvol_ratio < 0.67:
            self.bearish_factors.append(f"Down volume dominating ({1/self.market_internals.uvol_dvol_ratio:.1f}x)")

        if self.market_internals.vix > 25:
            self.warnings.append(f"Elevated VIX at {self.market_internals.vix:.1f} - expect wider swings")

        if self.market_internals.put_call_ratio < 0.7:
            self.bullish_factors.append(f"Bullish P/C ratio at {self.market_internals.put_call_ratio:.2f}")
        elif self.market_internals.put_call_ratio > 1.3:
            self.bearish_factors.append(f"Bearish P/C ratio at {self.market_internals.put_call_ratio:.2f}")

        # GEX factors
        if self.gex_analysis.dealer_position == "short_gamma":
            self.bullish_factors.append("Dealers short gamma - trending market expected")
        elif self.gex_analysis.dealer_position == "long_gamma":
            self.neutral_factors.append("Dealers long gamma - mean reversion expected")

        if self.gex_analysis.pin_risk_strikes:
            self.warnings.append(f"Pin risk at strikes: {self.gex_analysis.pin_risk_strikes}")

        # Flow factors
        if self.flow_attribution.institutional_flow_signal > 0.5:
            self.bullish_factors.append("Strong institutional bullish flow")
        elif self.flow_attribution.institutional_flow_signal < -0.5:
            self.bearish_factors.append("Strong institutional bearish flow")

        # Greeks factors
        if abs(self.greeks_impact.theta) > 0.3:
            self.warnings.append(f"High theta decay: ${self.greeks_impact.theta:.2f}/day")

        if self.greeks_impact.gamma > 0.05:
            self.neutral_factors.append(f"High gamma {self.greeks_impact.gamma:.4f} - position sensitive")

    def generate_trade_thesis(self):
        """Generate the overall trade thesis."""
        is_bullish = "CALL" in self.direction or "SHORT_PUT" in self.direction

        if is_bullish:
            if len(self.bullish_factors) >= 3:
                strength = "STRONG"
            elif len(self.bullish_factors) >= 2:
                strength = "MODERATE"
            else:
                strength = "SPECULATIVE"

            self.trade_thesis = (
                f"{strength} BULLISH thesis with {len(self.bullish_factors)} supporting factors:\n"
                f"Primary driver: {self.primary_reason}\n"
                f"Supported by: {', '.join(self.supporting_reasons[:3])}"
            )
        else:
            if len(self.bearish_factors) >= 3:
                strength = "STRONG"
            elif len(self.bearish_factors) >= 2:
                strength = "MODERATE"
            else:
                strength = "SPECULATIVE"

            self.trade_thesis = (
                f"{strength} BEARISH thesis with {len(self.bearish_factors)} supporting factors:\n"
                f"Primary driver: {self.primary_reason}\n"
                f"Supported by: {', '.join(self.supporting_reasons[:3])}"
            )

    def get_complete_report(self) -> str:
        """Generate the complete diagnostic report."""
        self.compile_decision_factors()
        self.generate_trade_thesis()

        lines = [
            "█" * 80,
            "█" + " COMPLETE TRADE DIAGNOSTICS REPORT ".center(78) + "█",
            "█" * 80,
            f"Generated: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Diagnostic Level: {self.diagnostic_level.value.upper()}",
            "",
            "═" * 80,
            " TRADE OVERVIEW ",
            "═" * 80,
            f"Direction: {self.direction}",
            f"Strike: {self.strike:.0f}",
            f"Entry Price: ${self.entry_price:.2f}",
            f"Contracts: {self.contracts}",
            f"Underlying: ${self.underlying_price:.2f}",
            f"Confidence: {self.confidence:.1f}%",
            "",
            "═" * 80,
            " TRADE THESIS ",
            "═" * 80,
            self.trade_thesis,
            "",
        ]

        # Decision factors
        lines.extend([
            "═" * 80,
            " DECISION FACTORS ",
            "═" * 80,
            "",
            "BULLISH FACTORS:",
        ])
        for factor in self.bullish_factors:
            lines.append(f"  ✓ {factor}")

        lines.append("\nBEARISH FACTORS:")
        for factor in self.bearish_factors:
            lines.append(f"  ✗ {factor}")

        lines.append("\nNEUTRAL FACTORS:")
        for factor in self.neutral_factors:
            lines.append(f"  ○ {factor}")

        if self.warnings:
            lines.append("\n⚠ WARNINGS:")
            for warning in self.warnings:
                lines.append(f"  ⚠ {warning}")

        # Component analyses
        if self.diagnostic_level in [DiagnosticLevel.DETAILED, DiagnosticLevel.EXHAUSTIVE]:
            lines.append("\n")
            lines.append(self.market_internals.get_full_report())
            lines.append("\n")
            lines.append(self.greeks_impact.get_full_report())
            lines.append("\n")
            lines.append(self.flow_attribution.get_attribution_report())
            lines.append("\n")
            lines.append(self.gex_analysis.get_gex_report())

        lines.append("\n" + "█" * 80)

        return "\n".join(lines)


class TradeDiagnosticsEngine:
    """
    Engine for generating complete trade diagnostics.

    Integrates all analysis components to provide
    exhaustive reasoning behind every trade decision.
    """

    def __init__(self, diagnostic_level: DiagnosticLevel = DiagnosticLevel.DETAILED):
        self.diagnostic_level = diagnostic_level

    def generate_diagnostics(
        self,
        trade_signal: Dict,
        market_internals: Optional[Dict] = None,
        greeks: Optional[Dict] = None,
        flow_data: Optional[Dict] = None,
        gex_data: Optional[Dict] = None
    ) -> CompleteTradeDiagnostics:
        """
        Generate complete diagnostics for a trade signal.

        Args:
            trade_signal: The trade signal to analyze
            market_internals: Market internals data
            greeks: Greeks data
            flow_data: Options flow data
            gex_data: GEX data

        Returns:
            CompleteTradeDiagnostics with full analysis
        """
        diagnostics = CompleteTradeDiagnostics(
            diagnostic_level=self.diagnostic_level,
            direction=trade_signal.get('direction', 'LONG_CALL'),
            strike=trade_signal.get('strike', 0),
            entry_price=trade_signal.get('entry_price', 0),
            contracts=trade_signal.get('contracts', 1),
            underlying_price=trade_signal.get('underlying_price', 0),
            confidence=trade_signal.get('confidence', 0)
        )

        # Parse market internals
        if market_internals:
            diagnostics.market_internals = MarketInternalsReading(
                trin=market_internals.get('trin', 1.0),
                tick=market_internals.get('tick', 0),
                add=market_internals.get('add', 0),
                uvol=market_internals.get('uvol', 0),
                dvol=market_internals.get('dvol', 0),
                vix=market_internals.get('vix', 20),
                skew=market_internals.get('skew', 120),
                put_call_ratio=market_internals.get('put_call_ratio', 1.0)
            )

        # Parse Greeks
        if greeks:
            diagnostics.greeks_impact = GreeksImpactAnalysis(
                delta=greeks.get('delta', 0),
                gamma=greeks.get('gamma', 0),
                theta=greeks.get('theta', 0),
                vega=greeks.get('vega', 0),
                charm=greeks.get('charm', 0),
                vanna=greeks.get('vanna', 0),
                contracts=trade_signal.get('contracts', 1),
                entry_price=trade_signal.get('entry_price', 0),
                underlying_price=trade_signal.get('underlying_price', 0)
            )

        # Parse flow
        if flow_data:
            diagnostics.flow_attribution = FlowAttribution(
                call_sweep_signal=flow_data.get('call_sweep_signal', 0),
                put_sweep_signal=flow_data.get('put_sweep_signal', 0),
                institutional_flow_signal=flow_data.get('institutional_signal', 0),
                total_call_premium=flow_data.get('call_premium', 0),
                total_put_premium=flow_data.get('put_premium', 0)
            )

        # Parse GEX
        if gex_data:
            diagnostics.gex_analysis = GEXAnalysis(
                total_gex=gex_data.get('total_gex', 0),
                call_gex=gex_data.get('call_gex', 0),
                put_gex=gex_data.get('put_gex', 0),
                net_gex=gex_data.get('net_gex', 0),
                gex_flip_level=gex_data.get('gex_flip_level', 0),
                dealer_position=gex_data.get('dealer_position', 'neutral'),
                pin_risk_strikes=gex_data.get('pin_risk_strikes', [])
            )

        # Determine primary reason
        diagnostics.primary_reason = trade_signal.get('primary_reason', 'Pattern match')
        diagnostics.supporting_reasons = trade_signal.get('supporting_reasons', [])

        return diagnostics


# Convenience functions
def create_diagnostics_engine(
    level: str = "detailed"
) -> TradeDiagnosticsEngine:
    """Create a configured diagnostics engine."""
    levels = {
        'summary': DiagnosticLevel.SUMMARY,
        'standard': DiagnosticLevel.STANDARD,
        'detailed': DiagnosticLevel.DETAILED,
        'exhaustive': DiagnosticLevel.EXHAUSTIVE
    }
    return TradeDiagnosticsEngine(levels.get(level, DiagnosticLevel.DETAILED))
