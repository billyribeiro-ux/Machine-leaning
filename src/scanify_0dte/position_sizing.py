"""
SCANIFY SPX 0DTE Options Day Trading Scanner + GEX Scanner -- Position Sizing

Advanced position sizing strategies for the SCANIFY 0DTE SPX Scanner.
Implements multiple sizing methodologies (fixed-percentage, Kelly criterion,
volatility-adjusted, confidence-weighted) and composes them into a unified
pipeline that respects hard risk limits, GEX regime awareness, drawdown
throttling, and correlation management.

All monetary values are in USD.  Contract sizes assume SPX options with a
$100 multiplier unless explicitly overridden.

Safety Invariant:
    NO NAKED SHORT POSITIONS.  EVER.
    All short options must be part of a defined-risk spread.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from .constants import (
    MULTIPLIER,
    RISK_MANAGEMENT,
    TimeZoneBoundary,
    INTRADAY_ZONE_SCHEDULE,
    IntradayZone,
)
from .models import (
    PositionType,
    ScanSignal,
    ScanType,
    TimeZoneType,
    TradeDirection,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Mapping from TimeZoneType (model enum) to a scalar risk multiplier.
# Later zones carry higher gamma/theta risk and receive reduced sizing.
_TIME_ZONE_RISK_MULTIPLIERS: dict[str, float] = {
    TimeZoneType.PRE_MARKET.value: 0.50,
    TimeZoneType.OPENING_AUCTION.value: 0.70,
    TimeZoneType.MORNING_SESSION.value: 1.00,
    TimeZoneType.MIDDAY_LULL.value: 0.90,
    TimeZoneType.AFTERNOON_ACCEL.value: 0.75,
    TimeZoneType.POWER_HOUR.value: 0.50,
    TimeZoneType.SETTLEMENT_WINDOW.value: 0.25,
}

# Default performance-based budget allocation weights when no historical
# performance data exists.  Keyed by ScanType value.
_DEFAULT_BUDGET_ALLOCATION: dict[str, float] = {
    ScanType.DIRECTIONAL.value: 0.50,
    ScanType.PREMIUM_SELL.value: 0.30,
    ScanType.GAMMA_SCALP.value: 0.20,
}

# Minimum contracts that any sizing method can produce (if a trade is
# permitted at all).
_MIN_CONTRACTS: int = 1

# Maximum contracts for a single position -- hard safety cap regardless
# of what sizing logic computes.
_MAX_CONTRACTS_PER_POSITION: int = 50


# ============================================================================
# 1. PositionSizer
# ============================================================================


class PositionSizer:
    """Advanced position sizing engine for 0DTE SPX options.

    Combines multiple independent sizing methodologies into a layered pipeline
    that progressively adjusts the base size to reflect current market
    conditions, signal quality, risk utilisation, and portfolio state.

    The pipeline order is:
        1. Fixed-percentage base size
        2. Kelly criterion adjustment
        3. Volatility (VIX1D) adjustment
        4. Confidence weighting
        5. Time-of-day adjustment
        6. GEX regime adjustment
        7. Drawdown adjustment
        8. Concurrent-position check
        9. Total-exposure check

    Parameters
    ----------
    daily_risk_budget : float
        Maximum dollar amount allocated to risk for the entire trading day.
    max_risk_per_trade_pct : float
        Maximum fraction of ``daily_risk_budget`` risked on any single trade.
    max_daily_trades : int
        Hard cap on total trades executed in a single session.
    max_concurrent_positions : int
        Maximum number of positions held simultaneously.
    max_total_exposure : float
        Maximum aggregate dollar exposure across all open positions.
    kelly_fraction : float
        Fraction of the full Kelly bet to use.  0.25 (quarter-Kelly) is the
        default to reduce variance while capturing most of the growth benefit.
    """

    def __init__(
        self,
        daily_risk_budget: float = 10_000.0,
        max_risk_per_trade_pct: float = 0.02,
        max_daily_trades: int = 50,
        max_concurrent_positions: int = 10,
        max_total_exposure: float = 50_000.0,
        kelly_fraction: float = 0.25,
    ) -> None:
        if daily_risk_budget <= 0:
            raise ValueError(
                f"daily_risk_budget must be positive, got {daily_risk_budget}"
            )
        if not 0 < max_risk_per_trade_pct <= 1.0:
            raise ValueError(
                f"max_risk_per_trade_pct must be in (0, 1], got {max_risk_per_trade_pct}"
            )
        if max_daily_trades < 1:
            raise ValueError(
                f"max_daily_trades must be >= 1, got {max_daily_trades}"
            )
        if max_concurrent_positions < 1:
            raise ValueError(
                f"max_concurrent_positions must be >= 1, got {max_concurrent_positions}"
            )
        if max_total_exposure <= 0:
            raise ValueError(
                f"max_total_exposure must be positive, got {max_total_exposure}"
            )
        if not 0 < kelly_fraction <= 1.0:
            raise ValueError(
                f"kelly_fraction must be in (0, 1], got {kelly_fraction}"
            )

        self.daily_risk_budget = daily_risk_budget
        self.max_risk_per_trade_pct = max_risk_per_trade_pct
        self.max_daily_trades = max_daily_trades
        self.max_concurrent_positions = max_concurrent_positions
        self.max_total_exposure = max_total_exposure
        self.kelly_fraction = kelly_fraction

        # Running state
        self._trades_today: int = 0

        logger.info(
            "PositionSizer initialised: budget=$%.2f, max_risk_pct=%.2f%%, "
            "max_trades=%d, max_concurrent=%d, max_exposure=$%.2f, kelly=%.2f",
            daily_risk_budget,
            max_risk_per_trade_pct * 100,
            max_daily_trades,
            max_concurrent_positions,
            max_total_exposure,
            kelly_fraction,
        )

    # ------------------------------------------------------------------
    # a) Fixed Percentage
    # ------------------------------------------------------------------

    def fixed_percentage_size(
        self,
        risk_budget: float,
        max_risk_pct: float,
        option_price: float,
        multiplier: int = 100,
    ) -> int:
        """Fixed percentage of risk budget.  Most conservative.

        Allocates a fixed fraction of the available risk budget to a single
        trade, then converts to a whole number of contracts based on the
        per-contract dollar cost.

        Parameters
        ----------
        risk_budget : float
            Available risk capital in dollars.
        max_risk_pct : float
            Maximum fraction of ``risk_budget`` to allocate (0, 1].
        option_price : float
            Per-contract option mid price (before multiplier).
        multiplier : int
            Contract multiplier (default 100 for SPX).

        Returns
        -------
        int
            Number of contracts.  Always >= 1 if inputs are valid.
        """
        if risk_budget <= 0 or option_price <= 0 or multiplier <= 0:
            logger.warning(
                "fixed_percentage_size: invalid input "
                "(budget=%.2f, price=%.2f, mult=%d) -- returning %d",
                risk_budget,
                option_price,
                multiplier,
                _MIN_CONTRACTS,
            )
            return _MIN_CONTRACTS

        max_risk_pct = max(0.0, min(1.0, max_risk_pct))
        risk_dollars = risk_budget * max_risk_pct
        cost_per_contract = option_price * multiplier

        if cost_per_contract <= 0:
            return _MIN_CONTRACTS

        contracts = int(risk_dollars / cost_per_contract)
        return max(_MIN_CONTRACTS, min(contracts, _MAX_CONTRACTS_PER_POSITION))

    # ------------------------------------------------------------------
    # b) Kelly Criterion
    # ------------------------------------------------------------------

    def kelly_criterion_size(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        risk_budget: float,
        option_price: float,
        kelly_fraction: float = 0.25,
        multiplier: int = 100,
    ) -> int:
        """Quarter-Kelly sizing for optimal growth.

        Applies the Kelly criterion to determine the theoretically optimal
        bet fraction, then scales by ``kelly_fraction`` (default 0.25) to
        reduce variance.  The result is floored to whole contracts.

        The Kelly formula used is:

            f* = (p * b - q) / b

        where:
            p = win probability (win_rate)
            q = loss probability (1 - p)
            b = ratio of average win to average loss (odds)

        Parameters
        ----------
        win_rate : float
            Historical win probability [0, 1].
        avg_win : float
            Average dollar gain on winning trades (positive).
        avg_loss : float
            Average dollar loss on losing trades (positive magnitude).
        risk_budget : float
            Available risk capital in dollars.
        option_price : float
            Per-contract option mid price.
        kelly_fraction : float
            Fraction of full Kelly to apply (default quarter-Kelly).
        multiplier : int
            Contract multiplier.

        Returns
        -------
        int
            Number of contracts.
        """
        if win_rate <= 0 or win_rate >= 1.0:
            logger.debug(
                "kelly_criterion_size: win_rate=%.4f outside (0,1), "
                "returning minimum",
                win_rate,
            )
            return _MIN_CONTRACTS

        if avg_win <= 0 or avg_loss <= 0:
            logger.debug(
                "kelly_criterion_size: avg_win=%.2f or avg_loss=%.2f "
                "non-positive, returning minimum",
                avg_win,
                avg_loss,
            )
            return _MIN_CONTRACTS

        if risk_budget <= 0 or option_price <= 0:
            return _MIN_CONTRACTS

        # Kelly formula
        b = avg_win / avg_loss  # Win/loss ratio (odds)
        q = 1.0 - win_rate
        kelly_full = (win_rate * b - q) / b

        if kelly_full <= 0:
            # Negative edge -- should not be trading at all, but return
            # the minimum so upstream logic can decide.
            logger.warning(
                "kelly_criterion_size: negative Kelly (%.4f) indicates "
                "negative expected value.  Consider not trading.",
                kelly_full,
            )
            return _MIN_CONTRACTS

        kelly_adjusted = kelly_full * kelly_fraction
        risk_dollars = risk_budget * kelly_adjusted
        cost_per_contract = option_price * multiplier

        if cost_per_contract <= 0:
            return _MIN_CONTRACTS

        contracts = int(risk_dollars / cost_per_contract)
        return max(_MIN_CONTRACTS, min(contracts, _MAX_CONTRACTS_PER_POSITION))

    # ------------------------------------------------------------------
    # c) Volatility Adjusted
    # ------------------------------------------------------------------

    def volatility_adjusted_size(
        self,
        risk_budget: float,
        vix1d: float,
        option_price: float,
        base_vix: float = 16.0,
        multiplier: int = 100,
    ) -> int:
        """Scale position size inversely with volatility.

        When VIX1D is above the ``base_vix`` reference, the position size is
        reduced proportionally.  When VIX1D is below ``base_vix``, size is
        modestly increased (capped at 1.5x to prevent over-leveraging in
        deceptively calm markets).

        The scaling formula is:

            vol_factor = clamp(base_vix / vix1d, 0.25, 1.50)

        Parameters
        ----------
        risk_budget : float
            Available risk capital in dollars.
        vix1d : float
            Current CBOE VIX1D reading.
        option_price : float
            Per-contract option mid price.
        base_vix : float
            Reference VIX1D level representing "normal" volatility.
        multiplier : int
            Contract multiplier.

        Returns
        -------
        int
            Number of contracts.
        """
        if vix1d <= 0 or base_vix <= 0 or risk_budget <= 0 or option_price <= 0:
            return _MIN_CONTRACTS

        # Scale inversely with vol, clamped to [0.25, 1.50]
        vol_factor = max(0.25, min(1.50, base_vix / vix1d))
        adjusted_budget = risk_budget * self.max_risk_per_trade_pct * vol_factor
        cost_per_contract = option_price * multiplier

        if cost_per_contract <= 0:
            return _MIN_CONTRACTS

        contracts = int(adjusted_budget / cost_per_contract)
        return max(_MIN_CONTRACTS, min(contracts, _MAX_CONTRACTS_PER_POSITION))

    # ------------------------------------------------------------------
    # d) Confidence Weighted
    # ------------------------------------------------------------------

    def confidence_weighted_size(
        self,
        base_contracts: int,
        confidence: float,
        min_confidence: float = 40.0,
        max_confidence: float = 90.0,
    ) -> int:
        """Scale position with signal confidence.

        Linearly interpolates the contract count between a minimum floor
        (at ``min_confidence``) and the full ``base_contracts`` value (at
        ``max_confidence``).  Signals below ``min_confidence`` receive the
        minimum contract count; signals at or above ``max_confidence``
        receive the full base.

        Parameters
        ----------
        base_contracts : int
            Unscaled number of contracts from a prior sizing step.
        confidence : float
            Signal confidence score (0-100).
        min_confidence : float
            Confidence below which the minimum contract count is used.
        max_confidence : float
            Confidence at or above which the full base is used.

        Returns
        -------
        int
            Confidence-adjusted number of contracts.
        """
        if base_contracts < _MIN_CONTRACTS:
            return _MIN_CONTRACTS

        if confidence <= min_confidence:
            # Minimum sizing -- signal barely qualifies
            return _MIN_CONTRACTS

        if confidence >= max_confidence:
            # Full sizing -- high-conviction signal
            return base_contracts

        # Linear interpolation between min_confidence and max_confidence
        confidence_range = max_confidence - min_confidence
        if confidence_range <= 0:
            return base_contracts

        scale = (confidence - min_confidence) / confidence_range
        # Scale ranges from 0.0 (at min_confidence) to 1.0 (at max_confidence)
        # Map to contract range: [1, base_contracts]
        adjusted = _MIN_CONTRACTS + scale * (base_contracts - _MIN_CONTRACTS)
        return max(_MIN_CONTRACTS, min(int(adjusted), base_contracts))

    # ------------------------------------------------------------------
    # e) Time-of-Day Adjusted
    # ------------------------------------------------------------------

    def time_of_day_adjusted_size(
        self,
        base_contracts: int,
        time_zone: str,
    ) -> int:
        """Reduce size later in the day (theta/gamma risk).

        As the trading day progresses toward settlement, gamma and theta
        risks accelerate non-linearly.  This method applies a pre-defined
        multiplier for each intraday time zone to scale the position size
        accordingly.

        Parameters
        ----------
        base_contracts : int
            Unscaled number of contracts from a prior sizing step.
        time_zone : str
            Current intraday time zone (value from ``TimeZoneType``).

        Returns
        -------
        int
            Time-adjusted number of contracts.
        """
        if base_contracts < _MIN_CONTRACTS:
            return _MIN_CONTRACTS

        multiplier = _TIME_ZONE_RISK_MULTIPLIERS.get(time_zone, 1.0)
        adjusted = int(base_contracts * multiplier)
        return max(_MIN_CONTRACTS, min(adjusted, _MAX_CONTRACTS_PER_POSITION))

    # ------------------------------------------------------------------
    # f) GEX Regime Adjusted
    # ------------------------------------------------------------------

    def gex_regime_adjusted_size(
        self,
        base_contracts: int,
        net_gex: float,
        gex_threshold: float = 0,
    ) -> int:
        """Reduce size in negative GEX (destabilising) environment.

        When aggregate dealer gamma is negative (net_gex < gex_threshold),
        the market is in a "de-stabilising" regime where dealer hedging
        amplifies price moves.  Position size is reduced proportionally to
        how far below the threshold the GEX reading is.

        Scaling logic:
            - net_gex >= threshold:  no reduction (1.0x)
            - net_gex < threshold:   reduce by up to 50% as GEX becomes
              more negative, using a smooth sigmoid-inspired clamp.

        Parameters
        ----------
        base_contracts : int
            Unscaled number of contracts from a prior sizing step.
        net_gex : float
            Current aggregate net gamma exposure.
        gex_threshold : float
            Level below which GEX is considered destabilising (default 0).

        Returns
        -------
        int
            GEX-regime-adjusted number of contracts.
        """
        if base_contracts < _MIN_CONTRACTS:
            return _MIN_CONTRACTS

        if net_gex >= gex_threshold:
            # Positive or neutral gamma -- dealers dampen moves, no reduction
            return base_contracts

        # Negative gamma regime: scale between 0.50 and 1.0 based on magnitude.
        # We use a simple ratio: the further below zero, the more we cut.
        # A net_gex equal to -abs(gex_threshold or 1e6) produces 0.50x.
        reference_magnitude = max(abs(gex_threshold), 1_000_000.0)
        deviation = abs(net_gex - gex_threshold)
        reduction_ratio = min(deviation / reference_magnitude, 1.0)
        scale = 1.0 - (0.50 * reduction_ratio)  # Range: [0.50, 1.0]

        adjusted = int(base_contracts * scale)
        return max(_MIN_CONTRACTS, min(adjusted, _MAX_CONTRACTS_PER_POSITION))

    # ------------------------------------------------------------------
    # g) Drawdown Adjusted
    # ------------------------------------------------------------------

    def drawdown_adjusted_size(
        self,
        base_contracts: int,
        current_drawdown_pct: float,
        max_allowed_drawdown: float = 0.10,
    ) -> int:
        """Reduce size as drawdown increases.

        Applies a linear taper to position size as the daily drawdown
        approaches ``max_allowed_drawdown``.  At zero drawdown, the full
        base is used.  At ``max_allowed_drawdown``, the size is reduced to
        the minimum.

        Parameters
        ----------
        base_contracts : int
            Unscaled number of contracts from a prior sizing step.
        current_drawdown_pct : float
            Current drawdown as a fraction (0.0 = no drawdown, 0.10 = 10%).
        max_allowed_drawdown : float
            Drawdown level at which sizing is reduced to the minimum.

        Returns
        -------
        int
            Drawdown-adjusted number of contracts.
        """
        if base_contracts < _MIN_CONTRACTS:
            return _MIN_CONTRACTS

        if current_drawdown_pct <= 0:
            return base_contracts

        if max_allowed_drawdown <= 0:
            # Safety: if max drawdown is zero or negative, refuse all trades
            logger.warning(
                "drawdown_adjusted_size: max_allowed_drawdown=%.4f is non-positive; "
                "returning minimum",
                max_allowed_drawdown,
            )
            return _MIN_CONTRACTS

        if current_drawdown_pct >= max_allowed_drawdown:
            # Drawdown limit reached -- minimum sizing only
            logger.warning(
                "drawdown_adjusted_size: current drawdown %.2f%% has reached "
                "max allowed %.2f%% -- clamping to minimum",
                current_drawdown_pct * 100,
                max_allowed_drawdown * 100,
            )
            return _MIN_CONTRACTS

        # Linear taper: 1.0 at 0% drawdown, 0.0 at max_allowed_drawdown
        scale = 1.0 - (current_drawdown_pct / max_allowed_drawdown)
        adjusted = int(base_contracts * scale)
        return max(_MIN_CONTRACTS, min(adjusted, _MAX_CONTRACTS_PER_POSITION))

    # ------------------------------------------------------------------
    # h) Compute Optimal Size (Full Pipeline)
    # ------------------------------------------------------------------

    def compute_optimal_size(
        self,
        signal: ScanSignal,
        risk_budget: float,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        vix1d: float,
        time_zone: str,
        net_gex: float,
        current_drawdown_pct: float,
        active_position_count: int,
    ) -> dict[str, Any]:
        """Compute optimal position size considering ALL factors.

        Runs the full sizing pipeline sequentially, applying each adjustment
        layer on top of the previous result.  The pipeline is:

            1. Start with fixed-percentage base
            2. Apply Kelly criterion adjustment
            3. Apply volatility adjustment
            4. Apply confidence weighting
            5. Apply time-of-day adjustment
            6. Apply GEX regime adjustment
            7. Apply drawdown adjustment
            8. Check against max concurrent positions
            9. Check against max total exposure

        Parameters
        ----------
        signal : ScanSignal
            The scan signal being sized.
        risk_budget : float
            Current available risk budget in dollars.
        win_rate : float
            Historical win probability for this signal type [0, 1].
        avg_win : float
            Average dollar gain on winning trades.
        avg_loss : float
            Average dollar loss on losing trades (positive magnitude).
        vix1d : float
            Current CBOE VIX1D index level.
        time_zone : str
            Current intraday time zone (TimeZoneType value string).
        net_gex : float
            Current aggregate net gamma exposure.
        current_drawdown_pct : float
            Current daily drawdown as a fraction.
        active_position_count : int
            Number of currently open positions.

        Returns
        -------
        dict
            Dictionary with keys:
                ``contracts`` (int): Final recommended contract count.
                ``base_reason`` (str): Description of the base sizing method.
                ``adjustments_applied`` (list[str]): Log of each adjustment.
                ``final_risk_dollars`` (float): Dollar risk for the final size.
        """
        adjustments: list[str] = []
        option_price = signal.entry_price
        multiplier = int(MULTIPLIER)

        # --- Step 1: Fixed-percentage base ---
        base_contracts = self.fixed_percentage_size(
            risk_budget=risk_budget,
            max_risk_pct=self.max_risk_per_trade_pct,
            option_price=option_price,
            multiplier=multiplier,
        )
        base_reason = (
            f"Fixed {self.max_risk_per_trade_pct * 100:.1f}% of "
            f"${risk_budget:,.0f} budget -> {base_contracts} contracts"
        )
        adjustments.append(f"Step 1 (fixed %): {base_contracts} contracts")
        current = base_contracts

        # --- Step 2: Kelly criterion adjustment ---
        kelly_contracts = self.kelly_criterion_size(
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            risk_budget=risk_budget,
            option_price=option_price,
            kelly_fraction=self.kelly_fraction,
            multiplier=multiplier,
        )
        # Take the conservative (lower) of fixed and Kelly
        if kelly_contracts < current:
            adjustments.append(
                f"Step 2 (Kelly): reduced {current} -> {kelly_contracts} "
                f"(win_rate={win_rate:.2f}, avg_win=${avg_win:.0f}, "
                f"avg_loss=${avg_loss:.0f})"
            )
            current = kelly_contracts
        else:
            adjustments.append(
                f"Step 2 (Kelly): {kelly_contracts} contracts "
                f"(no reduction, Kelly >= fixed base)"
            )

        # --- Step 3: Volatility adjustment ---
        vol_contracts = self.volatility_adjusted_size(
            risk_budget=risk_budget,
            vix1d=vix1d,
            option_price=option_price,
            multiplier=multiplier,
        )
        if vol_contracts < current:
            adjustments.append(
                f"Step 3 (vol): reduced {current} -> {vol_contracts} "
                f"(VIX1D={vix1d:.1f})"
            )
            current = vol_contracts
        else:
            adjustments.append(
                f"Step 3 (vol): {vol_contracts} contracts "
                f"(no reduction, VIX1D={vix1d:.1f})"
            )

        # --- Step 4: Confidence weighting ---
        confidence = signal.direction_score.confidence
        conf_contracts = self.confidence_weighted_size(
            base_contracts=current,
            confidence=confidence,
        )
        if conf_contracts != current:
            adjustments.append(
                f"Step 4 (confidence): adjusted {current} -> {conf_contracts} "
                f"(confidence={confidence:.1f})"
            )
            current = conf_contracts
        else:
            adjustments.append(
                f"Step 4 (confidence): unchanged at {current} "
                f"(confidence={confidence:.1f})"
            )

        # --- Step 5: Time-of-day adjustment ---
        tod_contracts = self.time_of_day_adjusted_size(
            base_contracts=current,
            time_zone=time_zone,
        )
        if tod_contracts != current:
            adjustments.append(
                f"Step 5 (time-of-day): adjusted {current} -> {tod_contracts} "
                f"(zone={time_zone})"
            )
            current = tod_contracts
        else:
            adjustments.append(
                f"Step 5 (time-of-day): unchanged at {current} "
                f"(zone={time_zone})"
            )

        # --- Step 6: GEX regime adjustment ---
        gex_contracts = self.gex_regime_adjusted_size(
            base_contracts=current,
            net_gex=net_gex,
        )
        if gex_contracts != current:
            adjustments.append(
                f"Step 6 (GEX): adjusted {current} -> {gex_contracts} "
                f"(net_gex={net_gex:,.0f})"
            )
            current = gex_contracts
        else:
            adjustments.append(
                f"Step 6 (GEX): unchanged at {current} "
                f"(net_gex={net_gex:,.0f})"
            )

        # --- Step 7: Drawdown adjustment ---
        dd_contracts = self.drawdown_adjusted_size(
            base_contracts=current,
            current_drawdown_pct=current_drawdown_pct,
        )
        if dd_contracts != current:
            adjustments.append(
                f"Step 7 (drawdown): adjusted {current} -> {dd_contracts} "
                f"(drawdown={current_drawdown_pct * 100:.1f}%)"
            )
            current = dd_contracts
        else:
            adjustments.append(
                f"Step 7 (drawdown): unchanged at {current} "
                f"(drawdown={current_drawdown_pct * 100:.1f}%)"
            )

        # --- Step 8: Concurrent position check ---
        if active_position_count >= self.max_concurrent_positions:
            adjustments.append(
                f"Step 8 (concurrent): BLOCKED -- {active_position_count} "
                f"active positions >= max {self.max_concurrent_positions}"
            )
            current = 0
        else:
            remaining_slots = self.max_concurrent_positions - active_position_count
            adjustments.append(
                f"Step 8 (concurrent): OK -- {remaining_slots} slots available"
            )

        # --- Step 9: Total exposure check ---
        proposed_exposure = current * option_price * multiplier
        if proposed_exposure > self.max_total_exposure:
            max_contracts = int(
                self.max_total_exposure / (option_price * multiplier)
            )
            max_contracts = max(0, max_contracts)
            adjustments.append(
                f"Step 9 (exposure): capped {current} -> {max_contracts} "
                f"(exposure ${proposed_exposure:,.0f} > "
                f"max ${self.max_total_exposure:,.0f})"
            )
            current = max_contracts
        else:
            adjustments.append(
                f"Step 9 (exposure): OK -- "
                f"${proposed_exposure:,.0f} within ${self.max_total_exposure:,.0f}"
            )

        # Ensure minimum
        if current > 0:
            current = max(_MIN_CONTRACTS, current)

        final_risk = current * option_price * multiplier

        logger.info(
            "compute_optimal_size: %s %s -> %d contracts ($%.2f risk)",
            signal.scan_type.value,
            signal.direction.value,
            current,
            final_risk,
        )

        return {
            "contracts": current,
            "base_reason": base_reason,
            "adjustments_applied": adjustments,
            "final_risk_dollars": final_risk,
        }

    # ------------------------------------------------------------------
    # i) Validate Position Size
    # ------------------------------------------------------------------

    def validate_position_size(
        self,
        contracts: int,
        option_price: float,
        daily_budget_remaining: float,
        active_positions: int,
        position_type: PositionType = PositionType.SINGLE_LONG,
    ) -> tuple[int, str]:
        """Final validation -- ensure size is safe.

        Performs a sequence of safety checks and returns the (potentially
        reduced) contract count along with a reason string if any reduction
        was applied.

        Safety Invariant:
            **NO NAKED SHORT POSITIONS.  EVER.**
            Only SINGLE_LONG, DEBIT_SPREAD, CREDIT_SPREAD (defined-risk),
            and IRON_CONDOR (defined-risk) are permitted.  Any attempt to
            size a naked short will be rejected outright.

        Parameters
        ----------
        contracts : int
            Proposed number of contracts.
        option_price : float
            Per-contract option mid price.
        daily_budget_remaining : float
            Remaining daily risk budget in dollars.
        active_positions : int
            Number of currently open positions.
        position_type : PositionType
            The intended position structure.

        Returns
        -------
        tuple[int, str]
            ``(validated_contracts, reason_if_reduced)``
            If no reduction was needed, reason is an empty string.
        """
        reasons: list[str] = []
        validated = contracts

        # ----------------------------------------------------------
        # CRITICAL SAFETY CHECK: No naked short positions.  Ever.
        # ----------------------------------------------------------
        # All permitted position types in the SCANIFY system are
        # defined-risk.  This check exists as a redundant safety net.
        if RISK_MANAGEMENT.allow_naked_short is False:
            # Verify position type is defined-risk
            _defined_risk_types = {
                PositionType.SINGLE_LONG,
                PositionType.DEBIT_SPREAD,
                PositionType.CREDIT_SPREAD,
                PositionType.IRON_CONDOR,
            }
            if position_type not in _defined_risk_types:
                logger.critical(
                    "REJECTED: position_type=%s is not defined-risk. "
                    "NO NAKED SHORT POSITIONS.  EVER.",
                    position_type,
                )
                return 0, "REJECTED: naked short positions are NEVER permitted"

        # Check 1: Non-positive contracts
        if validated <= 0:
            return 0, "No contracts to validate (zero or negative input)"

        # Check 2: Maximum contracts per position
        if validated > _MAX_CONTRACTS_PER_POSITION:
            reasons.append(
                f"Capped from {validated} to {_MAX_CONTRACTS_PER_POSITION} "
                f"(hard max per position)"
            )
            validated = _MAX_CONTRACTS_PER_POSITION

        # Check 3: Daily trade count
        if self._trades_today >= self.max_daily_trades:
            logger.warning(
                "validate_position_size: daily trade limit reached "
                "(%d/%d) -- rejecting",
                self._trades_today,
                self.max_daily_trades,
            )
            return 0, (
                f"Daily trade limit reached ({self._trades_today}/"
                f"{self.max_daily_trades})"
            )

        # Check 4: Concurrent position limit
        if active_positions >= self.max_concurrent_positions:
            logger.warning(
                "validate_position_size: concurrent position limit reached "
                "(%d/%d) -- rejecting",
                active_positions,
                self.max_concurrent_positions,
            )
            return 0, (
                f"Concurrent position limit reached ({active_positions}/"
                f"{self.max_concurrent_positions})"
            )

        # Check 5: Budget remaining
        multiplier = int(MULTIPLIER)
        proposed_cost = validated * option_price * multiplier
        if proposed_cost > daily_budget_remaining:
            affordable = int(daily_budget_remaining / (option_price * multiplier))
            affordable = max(0, affordable)
            if affordable <= 0:
                return 0, (
                    f"Insufficient daily budget remaining "
                    f"(${daily_budget_remaining:,.2f} < "
                    f"${option_price * multiplier:,.2f} per contract)"
                )
            reasons.append(
                f"Reduced from {validated} to {affordable} "
                f"(budget remaining: ${daily_budget_remaining:,.2f})"
            )
            validated = affordable

        # Check 6: Maximum total exposure
        final_exposure = validated * option_price * multiplier
        if final_exposure > self.max_total_exposure:
            max_affordable = int(
                self.max_total_exposure / (option_price * multiplier)
            )
            max_affordable = max(0, max_affordable)
            if max_affordable <= 0:
                return 0, (
                    f"Exposure limit breached "
                    f"(${final_exposure:,.2f} > "
                    f"${self.max_total_exposure:,.2f})"
                )
            reasons.append(
                f"Reduced from {validated} to {max_affordable} "
                f"(exposure cap: ${self.max_total_exposure:,.2f})"
            )
            validated = max_affordable

        # Check 7: Maximum risk per trade
        max_risk_dollars = self.daily_risk_budget * self.max_risk_per_trade_pct
        trade_risk = validated * option_price * multiplier
        if trade_risk > max_risk_dollars:
            safe_contracts = int(max_risk_dollars / (option_price * multiplier))
            safe_contracts = max(0, safe_contracts)
            if safe_contracts <= 0:
                return 0, (
                    f"Single-trade risk limit breached "
                    f"(${trade_risk:,.2f} > ${max_risk_dollars:,.2f})"
                )
            reasons.append(
                f"Reduced from {validated} to {safe_contracts} "
                f"(max risk per trade: ${max_risk_dollars:,.2f})"
            )
            validated = safe_contracts

        # Final minimum
        if validated > 0:
            validated = max(_MIN_CONTRACTS, validated)

        reason_str = "; ".join(reasons) if reasons else ""
        return validated, reason_str

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def record_trade(self) -> None:
        """Increment the daily trade counter after a trade is executed."""
        self._trades_today += 1
        logger.debug(
            "Trade recorded: %d/%d daily trades used",
            self._trades_today,
            self.max_daily_trades,
        )

    def reset_daily_state(self) -> None:
        """Reset daily counters.  Call at start of each trading day."""
        self._trades_today = 0
        logger.info("PositionSizer daily state reset")

    @property
    def trades_remaining_today(self) -> int:
        """Number of trades remaining before the daily cap is hit."""
        return max(0, self.max_daily_trades - self._trades_today)


# ============================================================================
# 2. RiskBudgetManager
# ============================================================================


class RiskBudgetManager:
    """Manages daily risk budget allocation across scanner types.

    Distributes the total daily risk budget among the three scanner
    archetypes (DIRECTIONAL, PREMIUM_SELL, GAMMA_SCALP) based on their
    historical performance.  Tracks intraday consumption and enforces
    per-type limits.

    Parameters
    ----------
    total_daily_budget : float
        Total risk budget for the day in dollars.
    """

    def __init__(self, total_daily_budget: float = 10_000.0) -> None:
        if total_daily_budget <= 0:
            raise ValueError(
                f"total_daily_budget must be positive, got {total_daily_budget}"
            )
        self.total_daily_budget = total_daily_budget

        # Per-type allocations and consumption tracking
        self._allocations: dict[str, float] = {}
        self._consumed: dict[str, float] = {}

        # Initialise with default allocations
        self.allocate_budget(total_daily_budget, {})

        logger.info(
            "RiskBudgetManager initialised with $%.2f total budget",
            total_daily_budget,
        )

    def allocate_budget(
        self,
        total_budget: float,
        scan_type_performance: dict[str, float],
    ) -> dict[str, float]:
        """Allocate risk budget across scanner types based on performance.

        If performance data is provided (keyed by ScanType value, with
        values representing a performance metric such as Sharpe ratio or
        win rate), the allocation is weighted proportionally.  Otherwise,
        the default static allocation is used.

        Parameters
        ----------
        total_budget : float
            Total risk budget to distribute.
        scan_type_performance : dict[str, float]
            Performance metric per scanner type.  Higher is better.
            Example: ``{"DIRECTIONAL": 1.8, "PREMIUM_SELL": 2.1, "GAMMA_SCALP": 0.9}``

        Returns
        -------
        dict[str, float]
            Allocation per scanner type in dollars.
        """
        if not scan_type_performance:
            # Use default static allocation
            self._allocations = {
                k: total_budget * v
                for k, v in _DEFAULT_BUDGET_ALLOCATION.items()
            }
        else:
            # Performance-weighted allocation with floor
            # Ensure all scan types are represented
            all_types = list(_DEFAULT_BUDGET_ALLOCATION.keys())
            perf_values: dict[str, float] = {}

            for st in all_types:
                raw = scan_type_performance.get(st, 0.0)
                # Floor at a small positive to guarantee every type gets
                # at least some allocation
                perf_values[st] = max(raw, 0.01)

            total_perf = sum(perf_values.values())
            if total_perf <= 0:
                # Fallback to equal allocation
                equal_share = total_budget / max(len(all_types), 1)
                self._allocations = {st: equal_share for st in all_types}
            else:
                self._allocations = {
                    st: total_budget * (pv / total_perf)
                    for st, pv in perf_values.items()
                }

        # Ensure consumed tracking is initialised for all types
        for st in self._allocations:
            if st not in self._consumed:
                self._consumed[st] = 0.0

        logger.info(
            "Budget allocated: %s",
            {k: f"${v:,.2f}" for k, v in self._allocations.items()},
        )

        return dict(self._allocations)

    def get_remaining_budget(self, scan_type: str) -> float:
        """Return the remaining risk budget for a given scanner type.

        Parameters
        ----------
        scan_type : str
            Scanner type value (e.g. ``"DIRECTIONAL"``).

        Returns
        -------
        float
            Remaining budget in dollars.  Returns 0.0 if the type is unknown.
        """
        allocated = self._allocations.get(scan_type, 0.0)
        consumed = self._consumed.get(scan_type, 0.0)
        return max(0.0, allocated - consumed)

    def record_trade_risk(self, scan_type: str, risk_amount: float) -> None:
        """Record risk consumed by a trade.

        Parameters
        ----------
        scan_type : str
            Scanner type value.
        risk_amount : float
            Dollar risk consumed by this trade (positive).
        """
        if risk_amount < 0:
            logger.warning(
                "record_trade_risk: negative risk_amount=%.2f ignored",
                risk_amount,
            )
            return

        if scan_type not in self._consumed:
            self._consumed[scan_type] = 0.0
        self._consumed[scan_type] += risk_amount

        remaining = self.get_remaining_budget(scan_type)
        logger.debug(
            "Recorded $%.2f risk for %s (remaining: $%.2f)",
            risk_amount,
            scan_type,
            remaining,
        )

    def reset_daily_budget(self) -> None:
        """Reset all consumption tracking for a new trading day.

        Call this at the start of each session.  Allocations are preserved
        until ``allocate_budget`` is called again.
        """
        self._consumed = {st: 0.0 for st in self._allocations}
        logger.info("Daily risk budget reset for all scanner types")

    def get_budget_utilization(self) -> dict[str, dict[str, float]]:
        """Return budget utilisation statistics per scanner type.

        Returns
        -------
        dict[str, dict[str, float]]
            Nested dict with keys per scanner type, each containing:
                ``allocated``, ``consumed``, ``remaining``, ``utilization_pct``
        """
        result: dict[str, dict[str, float]] = {}
        for scan_type, allocated in self._allocations.items():
            consumed = self._consumed.get(scan_type, 0.0)
            remaining = max(0.0, allocated - consumed)
            utilization_pct = (
                (consumed / allocated * 100.0) if allocated > 0 else 0.0
            )
            result[scan_type] = {
                "allocated": allocated,
                "consumed": consumed,
                "remaining": remaining,
                "utilization_pct": round(utilization_pct, 2),
            }
        return result


# ============================================================================
# 3. CorrelationManager
# ============================================================================


class CorrelationManager:
    """Manages position correlation to avoid concentrated risk.

    Monitors the directional exposure of the active portfolio and provides
    guidance on whether a new position would create excessive directional
    concentration or breach aggregate Greek limits.

    Parameters
    ----------
    max_directional_concentration : float
        Maximum fraction of positions in the same direction before
        concentration is flagged (default 0.75 = 75%).
    max_portfolio_delta : float
        Maximum absolute net portfolio delta (in SPX-equivalent points)
        before new same-direction positions are restricted.
    max_portfolio_gamma : float
        Maximum absolute net portfolio gamma before new positions are
        restricted.
    """

    def __init__(
        self,
        max_directional_concentration: float = 0.75,
        max_portfolio_delta: float = 5.0,
        max_portfolio_gamma: float = 2.0,
    ) -> None:
        self.max_directional_concentration = max_directional_concentration
        self.max_portfolio_delta = max_portfolio_delta
        self.max_portfolio_gamma = max_portfolio_gamma

        logger.info(
            "CorrelationManager initialised: max_dir_conc=%.0f%%, "
            "max_delta=%.2f, max_gamma=%.2f",
            max_directional_concentration * 100,
            max_portfolio_delta,
            max_portfolio_gamma,
        )

    # ------------------------------------------------------------------
    # a) Directional Concentration
    # ------------------------------------------------------------------

    def check_directional_concentration(
        self,
        positions: list[dict[str, Any]],
    ) -> float:
        """Compute directional concentration of the current portfolio.

        Returns the fraction of positions aligned with the dominant
        direction.  A value of 1.0 means all positions are in the same
        direction; 0.5 means perfectly balanced.

        Each position dict is expected to contain at minimum:
            ``direction`` (str): ``"BULL"`` or ``"BEAR"``

        Positions with direction ``"NEUTRAL"`` are excluded from the
        calculation.

        Parameters
        ----------
        positions : list[dict[str, Any]]
            List of active position descriptors.

        Returns
        -------
        float
            Concentration ratio [0.0, 1.0].  Returns 0.0 for empty lists.
        """
        if not positions:
            return 0.0

        directional = [
            p for p in positions
            if p.get("direction") in (
                TradeDirection.BULL.value,
                TradeDirection.BEAR.value,
                TradeDirection.BULL,
                TradeDirection.BEAR,
            )
        ]
        if not directional:
            return 0.0

        bull_count = sum(
            1 for p in directional
            if p.get("direction") in (TradeDirection.BULL.value, TradeDirection.BULL)
        )
        bear_count = len(directional) - bull_count

        dominant = max(bull_count, bear_count)
        return dominant / len(directional)

    # ------------------------------------------------------------------
    # b) Portfolio Delta
    # ------------------------------------------------------------------

    def compute_portfolio_delta(
        self,
        positions: list[dict[str, Any]],
    ) -> float:
        """Compute aggregate portfolio delta.

        Each position dict is expected to contain:
            ``delta`` (float): Per-contract delta.
            ``contracts`` (int): Number of contracts.
            ``direction`` (str): ``"BULL"`` or ``"BEAR"``.

        Bear positions contribute negative delta (puts / short calls).
        Neutral positions contribute their raw delta without sign flip.

        Parameters
        ----------
        positions : list[dict[str, Any]]
            Active position descriptors.

        Returns
        -------
        float
            Net portfolio delta (positive = net long, negative = net short).
        """
        if not positions:
            return 0.0

        total_delta = 0.0
        for p in positions:
            delta = float(p.get("delta", 0.0))
            contracts = int(p.get("contracts", 0))
            direction = p.get("direction", "")

            # Normalise direction to string value for comparison
            if isinstance(direction, TradeDirection):
                direction = direction.value

            position_delta = delta * contracts
            if direction == TradeDirection.BEAR.value:
                # Bear positions: puts have negative delta already, but
                # if the caller passes absolute delta, flip the sign.
                position_delta = -abs(position_delta)
            elif direction == TradeDirection.BULL.value:
                position_delta = abs(position_delta)
            # NEUTRAL: use raw delta * contracts

            total_delta += position_delta

        return round(total_delta, 6)

    # ------------------------------------------------------------------
    # c) Portfolio Gamma
    # ------------------------------------------------------------------

    def compute_portfolio_gamma(
        self,
        positions: list[dict[str, Any]],
    ) -> float:
        """Compute aggregate portfolio gamma.

        Gamma is always positive for long options, so this returns the
        total gamma exposure across all open positions.

        Each position dict is expected to contain:
            ``gamma`` (float): Per-contract gamma.
            ``contracts`` (int): Number of contracts.

        Parameters
        ----------
        positions : list[dict[str, Any]]
            Active position descriptors.

        Returns
        -------
        float
            Total portfolio gamma (always >= 0 for long-only portfolios).
        """
        if not positions:
            return 0.0

        total_gamma = 0.0
        for p in positions:
            gamma = float(p.get("gamma", 0.0))
            contracts = int(p.get("contracts", 0))
            total_gamma += gamma * contracts

        return round(total_gamma, 6)

    # ------------------------------------------------------------------
    # d) Should Reduce Size
    # ------------------------------------------------------------------

    def should_reduce_size(
        self,
        new_signal_direction: str,
        existing_positions: list[dict[str, Any]],
    ) -> bool:
        """Determine whether a new signal's size should be reduced.

        Returns ``True`` when adding a position in ``new_signal_direction``
        would:
            1. Push directional concentration above the threshold, OR
            2. Push portfolio delta beyond the maximum absolute limit.

        Parameters
        ----------
        new_signal_direction : str
            Direction of the proposed new position (TradeDirection value).
        existing_positions : list[dict[str, Any]]
            List of active position descriptors.

        Returns
        -------
        bool
            ``True`` if the new position should be size-reduced.
        """
        if not existing_positions:
            return False

        # Normalise direction
        if isinstance(new_signal_direction, TradeDirection):
            new_signal_direction = new_signal_direction.value

        # Check 1: Directional concentration
        # Simulate adding the new position
        simulated = existing_positions + [{"direction": new_signal_direction}]
        concentration = self.check_directional_concentration(simulated)
        if concentration > self.max_directional_concentration:
            logger.info(
                "should_reduce_size: concentration %.2f > %.2f after adding %s",
                concentration,
                self.max_directional_concentration,
                new_signal_direction,
            )
            return True

        # Check 2: Portfolio delta
        current_delta = self.compute_portfolio_delta(existing_positions)
        if new_signal_direction == TradeDirection.BULL.value:
            if current_delta > 0 and abs(current_delta) >= self.max_portfolio_delta:
                logger.info(
                    "should_reduce_size: portfolio delta %.4f already at/above "
                    "limit %.2f for BULL addition",
                    current_delta,
                    self.max_portfolio_delta,
                )
                return True
        elif new_signal_direction == TradeDirection.BEAR.value:
            if current_delta < 0 and abs(current_delta) >= self.max_portfolio_delta:
                logger.info(
                    "should_reduce_size: portfolio delta %.4f already at/below "
                    "limit -%.2f for BEAR addition",
                    current_delta,
                    self.max_portfolio_delta,
                )
                return True

        return False

    # ------------------------------------------------------------------
    # e) Max Additional Contracts
    # ------------------------------------------------------------------

    def compute_max_additional_contracts(
        self,
        existing_positions: list[dict[str, Any]],
        risk_limit: float,
    ) -> int:
        """Compute the maximum additional contracts allowed given current risk.

        Calculates how much residual risk capacity is available based on
        aggregate portfolio delta and gamma, then converts to a contract
        count.

        Parameters
        ----------
        existing_positions : list[dict[str, Any]]
            Active position descriptors.
        risk_limit : float
            Total dollar risk limit for the portfolio.

        Returns
        -------
        int
            Maximum number of additional contracts that can be opened.
        """
        if risk_limit <= 0:
            return 0

        if not existing_positions:
            # No existing positions -- full capacity available.
            # Use a conservative estimate: risk_limit / (option price * multiplier).
            # Since we do not know the option price here, return a theoretical
            # max based on the hard cap.
            return _MAX_CONTRACTS_PER_POSITION

        # Compute current risk utilisation as fraction of limit
        current_delta = abs(self.compute_portfolio_delta(existing_positions))
        current_gamma = self.compute_portfolio_gamma(existing_positions)

        # Delta-based headroom
        delta_headroom = max(0.0, self.max_portfolio_delta - current_delta)
        delta_fraction = (
            delta_headroom / self.max_portfolio_delta
            if self.max_portfolio_delta > 0
            else 0.0
        )

        # Gamma-based headroom
        gamma_headroom = max(0.0, self.max_portfolio_gamma - current_gamma)
        gamma_fraction = (
            gamma_headroom / self.max_portfolio_gamma
            if self.max_portfolio_gamma > 0
            else 0.0
        )

        # Use the more restrictive of the two
        headroom_fraction = min(delta_fraction, gamma_fraction)

        # Convert to an approximate contract count
        # Assume average delta per contract ~0.30 for 0DTE options
        avg_delta_per_contract = 0.30
        max_by_delta = int(delta_headroom / avg_delta_per_contract) if avg_delta_per_contract > 0 else 0

        # Assume average gamma per contract ~0.05 for 0DTE options
        avg_gamma_per_contract = 0.05
        max_by_gamma = int(gamma_headroom / avg_gamma_per_contract) if avg_gamma_per_contract > 0 else 0

        max_additional = min(max_by_delta, max_by_gamma)
        max_additional = max(0, min(max_additional, _MAX_CONTRACTS_PER_POSITION))

        logger.debug(
            "compute_max_additional_contracts: delta_headroom=%.4f, "
            "gamma_headroom=%.4f, max_additional=%d",
            delta_headroom,
            gamma_headroom,
            max_additional,
        )

        return max_additional


# ============================================================================
# Module Exports
# ============================================================================

__all__: list[str] = [
    "PositionSizer",
    "RiskBudgetManager",
    "CorrelationManager",
]
