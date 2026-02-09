"""
SCANIFY 0DTE Core Scan #3: Gamma Scalp / Acceleration Scanner

THE MOST ADVANCED SCAN -- exploits the gamma explosion in the final 2 hours
of the trading day (2:00 PM - 3:45 PM ET).  Executes every 30 seconds.

Theoretical foundation:
    As expiration approaches, at-the-money gamma grows without bound:

        Gamma_ATM = N'(d1) / (S * sigma * sqrt(T))

    When T -> 0, sqrt(T) -> 0, so Gamma_ATM -> infinity.  This creates a
    regime where small price movements produce enormous delta changes,
    forcing dealers to hedge aggressively.  The hedging itself moves the
    market, creating positive feedback loops (gamma squeezes) or sudden
    releases from pinned strikes (gamma unpins).

    This scanner detects three distinct setups:

    1. GAMMA SQUEEZE: Price approaching a strike with large negative dealer
       gamma.  Dealers must hedge in the same direction as the move, amplifying
       it.  Classic positive feedback loop.

    2. GAMMA UNPIN / RELEASE: Price has been pinned at a max-OI / max-pain
       strike for an extended period.  As gamma decays in the final 30 minutes,
       the pin weakens and a directional release occurs, driven by MOC
       (market-on-close) imbalances and net charm flows.

    3. GENERAL GAMMA ACCELERATION: Price at a high-gamma cluster point with
       negative net GEX and strong directional conviction.  Not a squeeze or
       unpin specifically, but a general setup where gamma amplification is
       likely.

Key concepts:
    - Net Dealer Gamma: The dollar-weighted gamma exposure across all strikes.
      Negative net dealer gamma = amplification mode (dealers hedge WITH moves).
      Positive net dealer gamma = dampening mode (dealers hedge AGAINST moves).

    - Speed (dGamma/dS): Third derivative of option price w.r.t. spot.
      High positive speed near a strike means gamma will ACCELERATE if price
      moves there -- a "gamma landmine."

    - Gamma Pin: When large positive dealer gamma at a strike acts like a
      magnet, pulling price back repeatedly.  Breaks down near expiry.

Dependencies:
    numpy, logging, datetime, typing

Author: SCANIFY Engine
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np

from .greeks_engine import BlackScholes0DTE, annualized_time
from .models import (
    ScanSignal,
    ScanType,
    TradeDirection,
    PositionType,
    SessionType,
    GEXProfile,
    OptionsChain,
    OptionQuote,
    OptionSide,
    StrikeSelection,
    DirectionScore,
)

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS LOCAL TO GAMMA SCALP SCANNER
# =============================================================================

# Annualization constants (must match greeks_engine)
_TRADING_DAYS_PER_YEAR: int = 252
_MINUTES_PER_TRADING_DAY: int = 390
_MINUTES_PER_YEAR: int = _TRADING_DAYS_PER_YEAR * _MINUTES_PER_TRADING_DAY

# SPX multiplier for dollar-gamma conversion
_SPX_MULTIPLIER: float = 100.0

# Scan execution interval
_SCAN_INTERVAL_SECONDS: int = 30

# Operating window boundaries (Eastern Time)
_SCAN_WINDOW_START: time = time(14, 0)   # 2:00 PM ET
_SCAN_WINDOW_END: time = time(15, 45)    # 3:45 PM ET

# Gamma unpin detection window
_UNPIN_WINDOW_START: time = time(15, 30)  # 3:30 PM ET
_UNPIN_WINDOW_END: time = time(15, 50)    # 3:50 PM ET

# Minimum implied volatility floor to prevent numerical instability
_MIN_IV: float = 0.01

# Minimum open interest to consider a strike meaningful for gamma analysis
_MIN_OI_FOR_GAMMA: int = 50

# Volume spike multiplier threshold for squeeze detection
_VOLUME_SPIKE_MULTIPLIER: float = 2.0

# Minimum bid-ask spread ratio (spread / mid) for liquidity filter
_MAX_SPREAD_PCT: float = 0.20  # 20% of mid

# Minimum open interest for trade entry
_MIN_OI_FOR_ENTRY: int = 500

# Minimum volume for trade entry
_MIN_VOLUME_FOR_ENTRY: int = 200

# Maximum strikes from ATM for gamma scalp after 3:00 PM
_MAX_OTM_STRIKES_LATE: int = 1

# Speed risk level thresholds (absolute value of speed)
_SPEED_RISK_LOW: float = 0.0001
_SPEED_RISK_MEDIUM: float = 0.001
_SPEED_RISK_HIGH: float = 0.005

# Gamma cluster detection: minimum gamma to be considered "high"
_HIGH_GAMMA_PERCENTILE: float = 75.0

# Confidence score boundaries
_CONFIDENCE_MIN: float = 0.0
_CONFIDENCE_MAX: float = 100.0


# =============================================================================
# GAMMA SCALP SCANNER
# =============================================================================

class GammaScalpScanner:
    """Core Scan #3: Exploits gamma explosion in the final 2 hours (2:00 PM - 3:45 PM).

    Executes every 30 seconds during its operating window.

    The gamma scalp scanner detects three categories of setups:

    1. **Gamma Squeeze**: Price approaching a strike with large negative dealer
       gamma, creating a positive feedback loop as dealer hedging amplifies the
       directional move.

    2. **Gamma Unpin / Release**: Price has been pinned at a high-OI strike and
       the pin weakens in the final 30 minutes, releasing into a directional
       move driven by MOC imbalances and charm flows.

    3. **General Gamma Acceleration**: High-gamma cluster with negative net GEX
       and directional conviction, but not fitting neatly into squeeze or unpin.

    The scanner produces :class:`ScanSignal` objects containing entry strikes,
    exit parameters, and comprehensive metadata about the gamma environment.

    Args:
        bs_calc: Pre-configured :class:`BlackScholes0DTE` instance for all
            Greeks calculations.
        min_direction_score: Minimum absolute value of the composite direction
            score required to establish directional conviction.  Default 50.0.
        profit_target_pct: Profit target as a fraction of entry premium.
            Range 0.50 - 1.00 (50-100%).  Default 0.75.
        stop_loss_pct: Stop loss as a fraction of entry premium.
            Default 0.30 (30%).
        absolute_exit_time: Hard time stop for all gamma scalp positions,
            formatted as ``"HH:MM"`` in Eastern Time.  Default ``"15:50"``.
        gamma_squeeze_distance: Maximum distance in SPX points from a high
            negative-gamma strike to qualify as a squeeze approach.  Default 3.0.
        pin_duration_threshold: Minimum number of minutes price must be pinned
            near a strike before an unpin/release is considered.  Default 30.
    """

    def __init__(
        self,
        bs_calc: BlackScholes0DTE,
        min_direction_score: float = 50.0,
        profit_target_pct: float = 0.75,
        stop_loss_pct: float = 0.30,
        absolute_exit_time: str = "15:50",
        gamma_squeeze_distance: float = 3.0,
        pin_duration_threshold: int = 30,
    ) -> None:
        self.bs_calc: BlackScholes0DTE = bs_calc
        self.min_direction_score: float = min_direction_score

        # Clamp profit target to [0.50, 1.00]
        self.profit_target_pct: float = float(np.clip(profit_target_pct, 0.50, 1.00))
        self.stop_loss_pct: float = stop_loss_pct

        # Parse absolute exit time
        parts = absolute_exit_time.split(":")
        self.absolute_exit_time: time = time(int(parts[0]), int(parts[1]))
        self.absolute_exit_time_str: str = absolute_exit_time

        self.gamma_squeeze_distance: float = gamma_squeeze_distance
        self.pin_duration_threshold: int = pin_duration_threshold

        logger.info(
            "GammaScalpScanner initialised: "
            "min_direction_score=%.1f, profit_target=%.0f%%, stop_loss=%.0f%%, "
            "exit_time=%s, squeeze_dist=%.1f pts, pin_threshold=%d min",
            self.min_direction_score,
            self.profit_target_pct * 100,
            self.stop_loss_pct * 100,
            self.absolute_exit_time_str,
            self.gamma_squeeze_distance,
            self.pin_duration_threshold,
        )

    # -----------------------------------------------------------------
    # (a) Real-time Gamma Profile
    # -----------------------------------------------------------------

    def compute_realtime_gamma_profile(
        self,
        chain: OptionsChain,
        spx_price: float,
        minutes_remaining: int,
    ) -> Dict[float, float]:
        """Calculate real-time gamma per strike for all 0DTE options.

        For each strike ``K`` in the chain, gamma is computed as:

            Gamma_strike = N'(d1) / (S * sigma * sqrt(T))

        where ``T = minutes_remaining / (390 * 252)`` (annualized).

        As ``T -> 0``, ``Gamma_ATM -> infinity`` (the gamma pin).  In
        practice, the engine clamps ``T`` to a 1-minute floor.  Gamma is only
        meaningfully large for strikes within approximately $10 of the current
        SPX price; further-OTM strikes have exponentially smaller gamma due to
        the ``N'(d1)`` decay.

        The returned profile sums call gamma and put gamma at each strike,
        weighted by their respective open interest, to produce a total
        gamma-per-strike measure.

        Args:
            chain: Current 0DTE options chain snapshot.
            spx_price: Current SPX index level.
            minutes_remaining: Trading minutes until 4:00 PM settlement.

        Returns:
            Dictionary mapping each strike price to its aggregate gamma value.
            Strikes with negligible gamma (< 1e-12) are excluded.
        """
        T = annualized_time(minutes_remaining)
        gamma_profile: Dict[float, float] = {}

        # Collect all unique strikes from the chain
        quotes: List[OptionQuote] = chain.quotes if hasattr(chain, "quotes") else []
        if not quotes:
            logger.debug("compute_realtime_gamma_profile: empty chain, returning {}")
            return gamma_profile

        for quote in quotes:
            strike = quote.strike
            iv = max(quote.implied_volatility, _MIN_IV)

            # Compute gamma via the Black-Scholes engine
            gamma_val = self.bs_calc.gamma(spx_price, strike, T, iv)

            # Accumulate: both calls and puts at the same strike contribute
            if strike not in gamma_profile:
                gamma_profile[strike] = 0.0
            gamma_profile[strike] += gamma_val

        # Filter out negligible entries
        gamma_profile = {
            k: v for k, v in gamma_profile.items() if v > 1e-12
        }

        logger.debug(
            "Gamma profile computed: %d strikes, T=%.8f (%.1f min), "
            "max_gamma=%.6f at strike=%.1f",
            len(gamma_profile),
            T,
            float(minutes_remaining),
            max(gamma_profile.values()) if gamma_profile else 0.0,
            max(gamma_profile, key=gamma_profile.get) if gamma_profile else 0.0,
        )

        return gamma_profile

    # -----------------------------------------------------------------
    # (b) Net Dealer Gamma
    # -----------------------------------------------------------------

    def compute_net_dealer_gamma(
        self,
        chain: OptionsChain,
        spx_price: float,
        minutes_remaining: int,
    ) -> Dict[float, float]:
        """Calculate NET DEALER GAMMA at each strike in dollar terms.

        Dealer positioning convention (standard market-maker assumption):

            Dealer_Gamma_Call = -1 * Gamma_call * OI_call * 100 * S
            Dealer_Gamma_Put  = +1 * Gamma_put  * OI_put  * 100 * S

        Rationale:
            - Dealers are typically SHORT calls (sold to retail/institutional
              buyers), so call gamma exposure for dealers is NEGATIVE.
            - Dealers are typically LONG puts (bought from retail/institutional
              sellers via market-making), so put gamma exposure is POSITIVE.

        Net_Dealer_Gamma = Dealer_Gamma_Call + Dealer_Gamma_Put

        A strike with negative net dealer gamma means dealers are net short
        gamma there and will hedge IN THE DIRECTION of price movement
        (amplification).  Positive net dealer gamma means dealers hedge
        AGAINST the move (dampening).

        Args:
            chain: Current 0DTE options chain snapshot.
            spx_price: Current SPX index level.
            minutes_remaining: Trading minutes until settlement.

        Returns:
            Dictionary mapping each strike price to net dealer gamma in
            dollar-notional terms.  Negative values indicate amplification
            (short gamma) at that strike.
        """
        T = annualized_time(minutes_remaining)
        dealer_gamma: Dict[float, float] = {}

        quotes: List[OptionQuote] = chain.quotes if hasattr(chain, "quotes") else []
        if not quotes:
            logger.debug("compute_net_dealer_gamma: empty chain, returning {}")
            return dealer_gamma

        for quote in quotes:
            strike = quote.strike
            iv = max(quote.implied_volatility, _MIN_IV)
            oi = quote.open_interest

            # Skip strikes with negligible open interest
            if oi < _MIN_OI_FOR_GAMMA:
                continue

            # Compute per-contract gamma at this strike
            gamma_val = self.bs_calc.gamma(spx_price, strike, T, iv)

            # Determine dealer sign based on option side (call vs put)
            if quote.side == OptionSide.CALL:
                # Dealers short calls -> negative gamma contribution
                contribution = -1.0 * gamma_val * float(oi) * _SPX_MULTIPLIER * spx_price
            else:
                # Dealers long puts -> positive gamma contribution
                contribution = +1.0 * gamma_val * float(oi) * _SPX_MULTIPLIER * spx_price

            if strike not in dealer_gamma:
                dealer_gamma[strike] = 0.0
            dealer_gamma[strike] += contribution

        if dealer_gamma:
            total_net = sum(dealer_gamma.values())
            most_neg_strike = min(dealer_gamma, key=dealer_gamma.get)
            most_pos_strike = max(dealer_gamma, key=dealer_gamma.get)
            logger.debug(
                "Net dealer gamma: total=$%.0f, most_negative=%.1f ($%.0f), "
                "most_positive=%.1f ($%.0f)",
                total_net,
                most_neg_strike,
                dealer_gamma[most_neg_strike],
                most_pos_strike,
                dealer_gamma[most_pos_strike],
            )

        return dealer_gamma

    # -----------------------------------------------------------------
    # (c) Gamma Squeeze Detection
    # -----------------------------------------------------------------

    def detect_gamma_squeeze(
        self,
        gex_profile: GEXProfile,
        spx_price: float,
        es_volume: float,
        avg_es_volume: float,
        direction_score: float,
        vix1d: float,
        vix1d_prior: float,
    ) -> Optional[Dict]:
        """Detect an active or imminent GAMMA SQUEEZE.

        A gamma squeeze occurs when price moves toward a strike with large
        NEGATIVE dealer gamma.  As price approaches, dealers must buy futures
        (for upward squeeze) or sell futures (for downward squeeze) to maintain
        delta neutrality.  This hedging pushes price further in the same
        direction, increasing delta exposure, requiring MORE hedging --
        a classic positive feedback loop.

        Detection requires ALL of the following conditions:

        1. **Proximity**: Price is within ``gamma_squeeze_distance`` points
           of a strike where net dealer gamma is significantly negative.
        2. **Volume spike**: ES futures volume exceeds 2x the average for
           this time of day (institutional urgency).
        3. **Directional conviction**: Composite direction score is increasing
           and has meaningful magnitude.
        4. **Vol compression**: VIX1D is declining or stable (characteristic
           of squeeze regimes where realized movement exceeds implied).

        Args:
            gex_profile: Current gamma exposure profile with per-strike data.
            spx_price: Current SPX index level.
            es_volume: Current ES futures volume (contracts/interval).
            avg_es_volume: Average ES volume for this time of day.
            direction_score: Current composite direction score (-100 to +100).
            vix1d: Current VIX1D level.
            vix1d_prior: VIX1D level from the prior scan interval.

        Returns:
            Dictionary with keys:
                - ``signal`` (bool): Always True if returned.
                - ``strike`` (float): The high negative-gamma strike being
                  approached.
                - ``direction`` (:class:`TradeDirection`): LONG_CALL for upside
                  squeeze, LONG_PUT for downside squeeze.
                - ``confidence`` (float): Confidence score 0-100.
                - ``description`` (str): Human-readable description.
                - ``dealer_gamma_at_strike`` (float): Dollar dealer gamma.
                - ``volume_ratio`` (float): ES volume / average volume.
                - ``vix1d_change`` (float): VIX1D change from prior interval.

            Returns ``None`` if no squeeze conditions are met.
        """
        # Access per-strike dealer gamma from the GEX profile
        strike_gamma: Dict[float, float] = {}
        if hasattr(gex_profile, "strike_gamma"):
            strike_gamma = gex_profile.strike_gamma
        elif hasattr(gex_profile, "dealer_gamma"):
            strike_gamma = gex_profile.dealer_gamma
        else:
            logger.warning("GEXProfile has no strike-level gamma data; squeeze detection skipped")
            return None

        if not strike_gamma:
            return None

        # ----- Condition 1: Find negative-gamma strikes near price -----
        candidate_strikes: List[Tuple[float, float]] = []  # (strike, dealer_gamma)
        for strike, dgamma in strike_gamma.items():
            distance = abs(spx_price - strike)
            if distance <= self.gamma_squeeze_distance and dgamma < 0:
                candidate_strikes.append((strike, dgamma))

        if not candidate_strikes:
            logger.debug(
                "No negative-gamma strikes within %.1f pts of SPX %.1f",
                self.gamma_squeeze_distance,
                spx_price,
            )
            return None

        # Select the strike with the MOST negative dealer gamma
        candidate_strikes.sort(key=lambda x: x[1])  # most negative first
        target_strike, target_gamma = candidate_strikes[0]

        # ----- Condition 2: Volume spike -----
        avg_es_volume = max(avg_es_volume, 1.0)  # prevent division by zero
        volume_ratio = es_volume / avg_es_volume

        if volume_ratio < _VOLUME_SPIKE_MULTIPLIER:
            logger.debug(
                "Volume ratio %.2fx below %.1fx threshold for squeeze at strike %.1f",
                volume_ratio,
                _VOLUME_SPIKE_MULTIPLIER,
                target_strike,
            )
            return None

        # ----- Condition 3: Directional conviction -----
        abs_score = abs(direction_score)
        if abs_score < self.min_direction_score:
            logger.debug(
                "Direction score %.1f below threshold %.1f for squeeze",
                abs_score,
                self.min_direction_score,
            )
            return None

        # ----- Condition 4: VIX1D declining or stable (vol compression) -----
        vix1d_change = vix1d - vix1d_prior
        if vix1d_change > 0.5:
            # VIX1D rising meaningfully -- not characteristic of a squeeze
            logger.debug(
                "VIX1D rising (+%.2f) -- not consistent with squeeze regime",
                vix1d_change,
            )
            return None

        # ----- ALL conditions met: compute confidence and direction -----
        # Determine direction: positive direction score = upside squeeze
        if direction_score > 0:
            direction = TradeDirection.LONG_CALL
            squeeze_direction_label = "UPSIDE"
        else:
            direction = TradeDirection.LONG_PUT
            squeeze_direction_label = "DOWNSIDE"

        # Confidence scoring (0-100):
        #   - Volume ratio contribution:  scaled 0-30
        #   - Direction score magnitude:  scaled 0-30
        #   - Dealer gamma magnitude:     scaled 0-25
        #   - VIX1D compression:          scaled 0-15
        conf_volume = float(np.clip((volume_ratio - 2.0) / 3.0 * 30.0, 0.0, 30.0))
        conf_direction = float(np.clip((abs_score - self.min_direction_score) / 50.0 * 30.0, 0.0, 30.0))
        conf_gamma = float(np.clip(abs(target_gamma) / 5_000_000.0 * 25.0, 0.0, 25.0))
        conf_vix = float(np.clip((-vix1d_change) / 2.0 * 15.0, 0.0, 15.0))
        confidence = float(np.clip(
            conf_volume + conf_direction + conf_gamma + conf_vix,
            _CONFIDENCE_MIN,
            _CONFIDENCE_MAX,
        ))

        description = (
            f"GAMMA SQUEEZE {squeeze_direction_label}: SPX {spx_price:.1f} approaching "
            f"strike {target_strike:.0f} (dealer gamma ${target_gamma:,.0f}). "
            f"ES volume {volume_ratio:.1f}x avg. VIX1D {vix1d_change:+.2f}. "
            f"Direction score {direction_score:+.1f}. Confidence {confidence:.0f}%."
        )

        logger.info("GAMMA SQUEEZE DETECTED: %s", description)

        return {
            "signal": True,
            "strike": target_strike,
            "direction": direction,
            "confidence": confidence,
            "description": description,
            "dealer_gamma_at_strike": target_gamma,
            "volume_ratio": volume_ratio,
            "vix1d_change": vix1d_change,
        }

    # -----------------------------------------------------------------
    # (d) Gamma Unpin / Release Detection
    # -----------------------------------------------------------------

    def detect_gamma_unpin(
        self,
        gex_profile: GEXProfile,
        spx_price: float,
        max_oi_strike: float,
        pin_duration_minutes: int,
        moc_imbalance: float,
        net_charm_direction: float,
        current_time: str,
    ) -> Optional[Dict]:
        """Detect GAMMA UNPIN / RELEASE conditions.

        A gamma pin occurs when large positive dealer gamma at a strike (high
        open interest) acts as a magnet: every time price moves away, dealer
        hedging pushes it back.  This pin weakens in the final 30 minutes as
        gamma itself decays (gamma-of-gamma, or "color," becomes large and
        negative, eroding the pin).

        The release direction is determined by:
            - **MOC (market-on-close) imbalance**: Published near 3:50 PM ET,
              this reveals the net buy/sell pressure for the closing auction.
            - **Net charm flow direction**: As OTM options lose delta (charm),
              the net flow of delta hedging unwinds creates a directional bias.

        Detection requires:
            1. Price within $3 of the pin strike (max OI / max pain).
            2. Pinned for at least ``pin_duration_threshold`` minutes.
            3. Current time is within the unpin window (3:30-3:50 PM ET).
            4. MOC imbalance data available (non-zero) OR charm direction
               is definitive.

        Args:
            gex_profile: Current gamma exposure profile.
            spx_price: Current SPX index level.
            max_oi_strike: Strike with maximum open interest (the pin target).
            pin_duration_minutes: Number of minutes price has been within $3
                of the max_oi_strike.
            moc_imbalance: Market-on-close imbalance in dollars.  Positive =
                buy imbalance, negative = sell imbalance.  Zero if not yet
                published.
            net_charm_direction: Net charm-driven delta flow direction.
                Positive = upward pressure, negative = downward pressure.
            current_time: Current time as ``"HH:MM"`` string in Eastern Time.

        Returns:
            Dictionary with keys:
                - ``signal`` (bool): Always True if returned.
                - ``pin_strike`` (float): The strike price has been pinned to.
                - ``direction`` (:class:`TradeDirection`): Expected release
                  direction.
                - ``confidence`` (float): Confidence score 0-100.
                - ``description`` (str): Human-readable description.
                - ``pin_duration`` (int): Minutes pinned.
                - ``moc_imbalance`` (float): MOC imbalance value.
                - ``charm_direction`` (float): Net charm direction.
                - ``release_catalyst`` (str): Primary catalyst for the release.

            Returns ``None`` if unpin conditions are not met.
        """
        # Parse current time
        try:
            parts = current_time.split(":")
            ct = time(int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            logger.error("Invalid current_time format: '%s' (expected HH:MM)", current_time)
            return None

        # ----- Condition 1: Price proximity to pin strike -----
        pin_distance = abs(spx_price - max_oi_strike)
        if pin_distance > 3.0:
            logger.debug(
                "Price %.1f is %.1f pts from pin strike %.0f (>3.0 limit)",
                spx_price,
                pin_distance,
                max_oi_strike,
            )
            return None

        # ----- Condition 2: Sufficient pin duration -----
        if pin_duration_minutes < self.pin_duration_threshold:
            logger.debug(
                "Pin duration %d min < threshold %d min",
                pin_duration_minutes,
                self.pin_duration_threshold,
            )
            return None

        # ----- Condition 3: Within unpin time window (3:30-3:50 PM) -----
        if ct < _UNPIN_WINDOW_START or ct > _UNPIN_WINDOW_END:
            logger.debug(
                "Current time %s outside unpin window %s-%s",
                current_time,
                _UNPIN_WINDOW_START.strftime("%H:%M"),
                _UNPIN_WINDOW_END.strftime("%H:%M"),
            )
            return None

        # ----- Condition 4: Directional catalyst available -----
        has_moc = abs(moc_imbalance) > 0
        has_charm = abs(net_charm_direction) > 0.001

        if not has_moc and not has_charm:
            logger.debug("No directional catalyst: MOC=0, charm~0")
            return None

        # ----- Determine release direction -----
        # MOC imbalance is the stronger signal when available; charm is secondary
        if has_moc:
            # MOC imbalance dominates direction determination
            release_catalyst = "MOC_IMBALANCE"
            if moc_imbalance > 0:
                # Net buy imbalance -> upside release
                directional_signal = 1.0
            else:
                # Net sell imbalance -> downside release
                directional_signal = -1.0

            # Weight: 70% MOC, 30% charm (when both available)
            if has_charm:
                charm_sign = 1.0 if net_charm_direction > 0 else -1.0
                combined_signal = 0.70 * directional_signal + 0.30 * charm_sign
                if abs(combined_signal) < 0.1:
                    # Conflicting signals -- reduce confidence but use MOC direction
                    release_catalyst = "MOC_IMBALANCE (conflicting charm)"
                directional_signal = 1.0 if combined_signal > 0 else -1.0
        else:
            # Only charm available
            release_catalyst = "CHARM_FLOW"
            directional_signal = 1.0 if net_charm_direction > 0 else -1.0

        if directional_signal > 0:
            direction = TradeDirection.LONG_CALL
            release_label = "UPSIDE"
        else:
            direction = TradeDirection.LONG_PUT
            release_label = "DOWNSIDE"

        # ----- Confidence scoring -----
        # Pin duration contribution: longer pin = higher confidence in release (0-25)
        conf_pin = float(np.clip(
            (pin_duration_minutes - self.pin_duration_threshold) / 30.0 * 25.0,
            0.0, 25.0,
        ))
        # Time contribution: closer to 3:50 = higher confidence (0-25)
        minutes_into_window = (ct.hour * 60 + ct.minute) - (_UNPIN_WINDOW_START.hour * 60 + _UNPIN_WINDOW_START.minute)
        window_length = (_UNPIN_WINDOW_END.hour * 60 + _UNPIN_WINDOW_END.minute) - (_UNPIN_WINDOW_START.hour * 60 + _UNPIN_WINDOW_START.minute)
        conf_time = float(np.clip(
            minutes_into_window / max(window_length, 1) * 25.0,
            0.0, 25.0,
        ))
        # MOC signal strength (0-30)
        if has_moc:
            # Normalize MOC: large imbalances ($500M+) are high conviction
            conf_moc = float(np.clip(abs(moc_imbalance) / 500_000_000.0 * 30.0, 0.0, 30.0))
        else:
            conf_moc = 0.0
        # Charm contribution (0-20)
        conf_charm = float(np.clip(abs(net_charm_direction) * 10.0, 0.0, 20.0))

        confidence = float(np.clip(
            conf_pin + conf_time + conf_moc + conf_charm,
            _CONFIDENCE_MIN,
            _CONFIDENCE_MAX,
        ))

        description = (
            f"GAMMA UNPIN {release_label}: SPX {spx_price:.1f} pinned at "
            f"{max_oi_strike:.0f} for {pin_duration_minutes} min. "
            f"Catalyst: {release_catalyst}. "
            f"MOC ${moc_imbalance / 1e6:+.0f}M, charm {net_charm_direction:+.4f}. "
            f"Confidence {confidence:.0f}%."
        )

        logger.info("GAMMA UNPIN DETECTED: %s", description)

        return {
            "signal": True,
            "pin_strike": max_oi_strike,
            "direction": direction,
            "confidence": confidence,
            "description": description,
            "pin_duration": pin_duration_minutes,
            "moc_imbalance": moc_imbalance,
            "charm_direction": net_charm_direction,
            "release_catalyst": release_catalyst,
        }

    # -----------------------------------------------------------------
    # (e) Gamma Landmines
    # -----------------------------------------------------------------

    def identify_gamma_landmines(
        self,
        chain: OptionsChain,
        spx_price: float,
        minutes_remaining: int,
        distance_threshold: float = 5.0,
    ) -> List[Dict]:
        """Identify gamma landmines -- strikes where dealer hedging will intensify violently.

        A gamma landmine is a strike where SPEED (the third derivative of
        option price w.r.t. spot, equivalently ``dGamma/dS``) is high and
        positive.  This means that if price moves toward that strike, gamma
        will ACCELERATE, compounding the hedging pressure.

        Mathematically, speed is computed numerically via:

            Speed = (Gamma(S + dS, K, T, sigma) - Gamma(S, K, T, sigma)) / dS

        The ``BlackScholes0DTE.speed()`` method handles this with a $1 bump.

        Only strikes within ``distance_threshold`` of the current SPX price
        are considered, since speed is negligible far from the money.

        Args:
            chain: Current 0DTE options chain snapshot.
            spx_price: Current SPX index level.
            minutes_remaining: Trading minutes until settlement.
            distance_threshold: Maximum distance in SPX points from current
                price to consider.  Default 5.0.

        Returns:
            List of dictionaries, each containing:
                - ``strike`` (float): The landmine strike.
                - ``speed`` (float): Speed value (dGamma/dS).
                - ``gamma`` (float): Gamma at the strike.
                - ``distance_from_spot`` (float): Signed distance
                  (positive = above spot, negative = below).
                - ``risk_level`` (str): ``"LOW"``, ``"MEDIUM"``, or ``"HIGH"``
                  based on absolute speed magnitude.

            Sorted by absolute speed descending (most dangerous first).
        """
        T = annualized_time(minutes_remaining)
        landmines: List[Dict] = []

        quotes: List[OptionQuote] = chain.quotes if hasattr(chain, "quotes") else []
        if not quotes:
            return landmines

        # Deduplicate strikes and track the best IV per strike
        strike_iv_map: Dict[float, float] = {}
        for quote in quotes:
            strike = quote.strike
            distance = abs(spx_price - strike)
            if distance > distance_threshold:
                continue
            iv = max(quote.implied_volatility, _MIN_IV)
            # Take the maximum IV at each strike (more conservative)
            if strike not in strike_iv_map or iv > strike_iv_map[strike]:
                strike_iv_map[strike] = iv

        for strike, iv in strike_iv_map.items():
            gamma_val = self.bs_calc.gamma(spx_price, strike, T, iv)
            speed_val = self.bs_calc.speed(spx_price, strike, T, iv)

            abs_speed = abs(speed_val)
            if abs_speed >= _SPEED_RISK_HIGH:
                risk_level = "HIGH"
            elif abs_speed >= _SPEED_RISK_MEDIUM:
                risk_level = "MEDIUM"
            elif abs_speed >= _SPEED_RISK_LOW:
                risk_level = "LOW"
            else:
                # Negligible speed -- not a landmine
                continue

            landmines.append({
                "strike": strike,
                "speed": speed_val,
                "gamma": gamma_val,
                "distance_from_spot": strike - spx_price,
                "risk_level": risk_level,
            })

        # Sort by absolute speed descending (most dangerous first)
        landmines.sort(key=lambda x: abs(x["speed"]), reverse=True)

        if landmines:
            logger.info(
                "Identified %d gamma landmines within %.1f pts of SPX %.1f. "
                "Most dangerous: strike %.0f (speed=%.6f, risk=%s)",
                len(landmines),
                distance_threshold,
                spx_price,
                landmines[0]["strike"],
                landmines[0]["speed"],
                landmines[0]["risk_level"],
            )
        else:
            logger.debug(
                "No gamma landmines within %.1f pts of SPX %.1f",
                distance_threshold,
                spx_price,
            )

        return landmines

    # -----------------------------------------------------------------
    # (f) Acceleration Strike Selection
    # -----------------------------------------------------------------

    def select_acceleration_strike(
        self,
        chain: OptionsChain,
        direction: TradeDirection,
        spx_price: float,
        minutes_remaining: int,
    ) -> Optional[StrikeSelection]:
        """Select the optimal strike for a gamma scalp / acceleration trade.

        Strike selection for gamma scalps is more constrained than directional
        or premium-selling scans because the gamma environment requires
        proximity to the money:

        **After 3:00 PM (< 60 minutes remaining):**
            Only ATM or 1 strike OTM.  Further OTM strikes have insufficient
            gamma for meaningful acceleration.

        **Before 3:00 PM:**
            ATM or up to 2 strikes OTM, targeting the strike at the nearest
            high-gamma cluster point.

        Liquidity requirements:
            - Open interest >= 500 contracts
            - Volume >= 200 contracts
            - Bid-ask spread <= 20% of mid price

        Args:
            chain: Current 0DTE options chain snapshot.
            direction: Trade direction (:attr:`TradeDirection.LONG_CALL` or
                :attr:`TradeDirection.LONG_PUT`).
            spx_price: Current SPX index level.
            minutes_remaining: Trading minutes until settlement.

        Returns:
            :class:`StrikeSelection` with the chosen strike, or ``None`` if
            no suitable strike meets all criteria.
        """
        T = annualized_time(minutes_remaining)
        quotes: List[OptionQuote] = chain.quotes if hasattr(chain, "quotes") else []
        if not quotes:
            logger.debug("select_acceleration_strike: empty chain")
            return None

        # Determine target side
        is_call = direction in (TradeDirection.LONG_CALL,)
        target_side = OptionSide.CALL if is_call else OptionSide.PUT

        # Filter to the correct side
        side_quotes = [q for q in quotes if q.side == target_side]
        if not side_quotes:
            logger.debug("No %s quotes available for strike selection", target_side)
            return None

        # Determine maximum OTM distance (in number of strikes)
        if minutes_remaining <= 60:
            max_otm_count = _MAX_OTM_STRIKES_LATE  # Only 1 strike OTM
        else:
            max_otm_count = 2  # Up to 2 strikes OTM

        # Get sorted unique strikes
        all_strikes = sorted(set(q.strike for q in side_quotes))
        if not all_strikes:
            return None

        # Find ATM strike
        atm_strike = min(all_strikes, key=lambda k: abs(k - spx_price))

        # Build candidate list: ATM + up to max_otm_count OTM strikes
        if is_call:
            # OTM calls are ABOVE spot
            candidates = [k for k in all_strikes if k >= atm_strike]
            candidates = candidates[: max_otm_count + 1]  # ATM + N OTM
        else:
            # OTM puts are BELOW spot
            candidates = [k for k in all_strikes if k <= atm_strike]
            candidates = candidates[-(max_otm_count + 1):]  # ATM + N OTM

        if not candidates:
            return None

        # Score each candidate by gamma magnitude (higher = better) with
        # liquidity filter
        best_strike: Optional[float] = None
        best_gamma: float = -1.0
        best_quote: Optional[OptionQuote] = None

        for strike in candidates:
            # Find quotes at this strike
            strike_quotes = [q for q in side_quotes if q.strike == strike]
            if not strike_quotes:
                continue

            # Use the quote with best liquidity (highest volume)
            quote = max(strike_quotes, key=lambda q: q.volume)

            # Liquidity filters
            if quote.open_interest < _MIN_OI_FOR_ENTRY:
                logger.debug("Strike %.0f rejected: OI %d < %d", strike, quote.open_interest, _MIN_OI_FOR_ENTRY)
                continue
            if quote.volume < _MIN_VOLUME_FOR_ENTRY:
                logger.debug("Strike %.0f rejected: volume %d < %d", strike, quote.volume, _MIN_VOLUME_FOR_ENTRY)
                continue

            # Bid-ask spread check
            mid = (quote.bid + quote.ask) / 2.0
            if mid > 0:
                spread_pct = (quote.ask - quote.bid) / mid
                if spread_pct > _MAX_SPREAD_PCT:
                    logger.debug("Strike %.0f rejected: spread %.1f%% > %.1f%%",
                                 strike, spread_pct * 100, _MAX_SPREAD_PCT * 100)
                    continue

            # Compute gamma at this strike
            iv = max(quote.implied_volatility, _MIN_IV)
            gamma_val = self.bs_calc.gamma(spx_price, strike, T, iv)

            if gamma_val > best_gamma:
                best_gamma = gamma_val
                best_strike = strike
                best_quote = quote

        if best_strike is None or best_quote is None:
            logger.debug("No suitable strike found for gamma scalp (%s)", direction)
            return None

        # Compute delta at the selected strike for information
        iv = max(best_quote.implied_volatility, _MIN_IV)
        option_type_str = "call" if is_call else "put"
        delta_val = self.bs_calc.delta(
            spx_price, best_strike, T, iv, option_type=option_type_str
        )
        mid_price = (best_quote.bid + best_quote.ask) / 2.0

        logger.info(
            "Selected acceleration strike: %.0f %s (gamma=%.6f, delta=%.4f, "
            "mid=$%.2f, OI=%d, vol=%d)",
            best_strike,
            option_type_str.upper(),
            best_gamma,
            delta_val,
            mid_price,
            best_quote.open_interest,
            best_quote.volume,
        )

        return StrikeSelection(
            strike=best_strike,
            side=target_side,
            delta=delta_val,
            gamma=best_gamma,
            mid_price=mid_price,
            bid=best_quote.bid,
            ask=best_quote.ask,
            open_interest=best_quote.open_interest,
            volume=best_quote.volume,
            implied_volatility=iv,
        )

    # -----------------------------------------------------------------
    # (g) Exit Parameter Generation
    # -----------------------------------------------------------------

    def generate_exit_params(
        self,
        entry_price: float,
        time_zone: str,
        minutes_remaining: int,
    ) -> Dict:
        """Generate exit parameters for gamma scalp trades.

        Gamma scalp trades require aggressive profit-taking because the setups
        are fleeting and the gamma environment can reverse in seconds.

        Exit hierarchy:
            1. **Profit target**: 50-100% of entry premium, WITHIN MINUTES.
               The exact target scales with time remaining -- closer to expiry
               means higher percentage targets are achievable but must be taken
               faster.
            2. **Stop loss**: 30% of entry premium.  Hard stop, no exceptions.
            3. **Time stop**: 3:50 PM ET absolute exit.  All gamma scalp
               positions must be flat by this time.
            4. **Trailing stop**: Activated once position reaches 25% profit.
               Trails at 40% of maximum profit achieved.
            5. **Gamma failure exit**: If price is rejected from the target
               gamma strike (squeeze fails), exit IMMEDIATELY at market.

        Args:
            entry_price: Entry price (premium paid per contract).
            time_zone: Current intraday time zone identifier.
            minutes_remaining: Trading minutes until settlement.

        Returns:
            Dictionary containing:
                - ``profit_target`` (float): Dollar profit target per contract.
                - ``profit_target_price`` (float): Option price at profit target.
                - ``stop_loss`` (float): Dollar stop loss per contract.
                - ``stop_loss_price`` (float): Option price at stop loss.
                - ``time_stop`` (str): Absolute time stop (``"HH:MM"``).
                - ``time_stop_minutes`` (int): Minutes until time stop.
                - ``trail_stop_activation`` (float): Profit level to activate
                  trailing stop.
                - ``trail_stop_pct`` (float): Trailing stop distance as
                  fraction of max profit.
                - ``gamma_failure_exit`` (bool): Whether gamma failure exit
                  is active (always True for this scan type).
        """
        # Scale profit target: more aggressive closer to expiry
        # With < 30 min remaining, target the full profit_target_pct
        # With > 60 min remaining, use 75% of profit_target_pct
        if minutes_remaining <= 30:
            effective_target_pct = self.profit_target_pct
        elif minutes_remaining <= 60:
            effective_target_pct = self.profit_target_pct * 0.90
        else:
            effective_target_pct = self.profit_target_pct * 0.75

        profit_target_dollar = entry_price * effective_target_pct
        profit_target_price = entry_price + profit_target_dollar

        stop_loss_dollar = entry_price * self.stop_loss_pct
        stop_loss_price = max(entry_price - stop_loss_dollar, 0.01)

        # Time stop: compute minutes until absolute exit time
        # Use minutes_remaining as a proxy (absolute_exit_time is 3:50 PM,
        # settlement is 4:00 PM -> 10 min before settlement)
        time_stop_minutes_val = max(minutes_remaining - 10, 0)

        # Trailing stop parameters
        trail_activation = entry_price * 0.25  # Activate at 25% profit
        trail_pct = 0.40  # Trail 40% below peak

        exit_params = {
            "profit_target": profit_target_dollar,
            "profit_target_price": profit_target_price,
            "profit_target_pct": effective_target_pct,
            "stop_loss": stop_loss_dollar,
            "stop_loss_price": stop_loss_price,
            "stop_loss_pct": self.stop_loss_pct,
            "time_stop": self.absolute_exit_time_str,
            "time_stop_minutes": time_stop_minutes_val,
            "trail_stop_activation": trail_activation,
            "trail_stop_activation_price": entry_price + trail_activation,
            "trail_stop_pct": trail_pct,
            "gamma_failure_exit": True,
        }

        logger.debug(
            "Exit params: target=$%.2f (%.0f%%), stop=$%.2f (%.0f%%), "
            "time=%s (%d min), trail_act=$%.2f, trail=%.0f%%",
            profit_target_dollar,
            effective_target_pct * 100,
            stop_loss_dollar,
            self.stop_loss_pct * 100,
            self.absolute_exit_time_str,
            time_stop_minutes_val,
            trail_activation,
            trail_pct * 100,
        )

        return exit_params

    # -----------------------------------------------------------------
    # (h) Main Scan Method
    # -----------------------------------------------------------------

    def scan(
        self,
        chain: OptionsChain,
        gex_profile: GEXProfile,
        spx_price: float,
        direction_score: DirectionScore,
        es_volume: float,
        avg_es_volume: float,
        vix1d: float,
        vix1d_prior: float,
        max_oi_strike: float,
        pin_duration_minutes: int,
        moc_imbalance: float,
        net_charm_direction: float,
        minutes_remaining: int,
        time_zone: str,
        current_time_str: str,
    ) -> Optional[ScanSignal]:
        """Main scan method.  Runs every 30 seconds from 2:00 PM - 3:45 PM.

        This is the top-level entry point for the gamma scalp scanner.  It
        evaluates entry conditions and checks for three distinct setups in
        priority order:

        **Entry preconditions (ALL must be true):**
            - Time: 2:00 PM - 3:45 PM ET only.
            - Price is approaching a high-gamma strike cluster.
            - Net GEX is negative (dealers short gamma = amplification mode).
            - Directional conviction exists (composite score > +/-50).
            - Sufficient liquidity at the target strike.

        **Setup detection order:**
            1. **Gamma squeeze** (highest priority): Positive feedback loop
               from dealer hedging.
            2. **Gamma unpin/release** (second priority): Pin break in the
               final 30 minutes.
            3. **General gamma acceleration** (third priority): Generic
               high-gamma directional setup.

        The first setup that triggers produces the signal.  If none trigger,
        the scan returns ``None``.

        Args:
            chain: Current 0DTE options chain snapshot.
            gex_profile: Current gamma exposure profile with per-strike data.
            spx_price: Current SPX index level.
            direction_score: Composite directional score object.
            es_volume: Current ES futures volume (contracts/interval).
            avg_es_volume: Average ES volume for this time of day.
            vix1d: Current VIX1D level.
            vix1d_prior: VIX1D level from the prior scan interval.
            max_oi_strike: Strike with maximum open interest (pin target).
            pin_duration_minutes: Minutes price has been near the pin strike.
            moc_imbalance: Market-on-close imbalance in dollars.
            net_charm_direction: Net charm-driven delta flow direction.
            minutes_remaining: Trading minutes until settlement.
            time_zone: Current intraday time zone identifier.
            current_time_str: Current time as ``"HH:MM"`` in Eastern Time.

        Returns:
            :class:`ScanSignal` with complete trade setup, or ``None`` if no
            setup is detected.
        """
        # ---- Parse current time ----
        try:
            parts = current_time_str.split(":")
            current_time_obj = time(int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            logger.error("Invalid current_time_str: '%s'", current_time_str)
            return None

        # ---- Time window check ----
        if current_time_obj < _SCAN_WINDOW_START or current_time_obj > _SCAN_WINDOW_END:
            logger.debug(
                "Outside scan window: %s not in [%s, %s]",
                current_time_str,
                _SCAN_WINDOW_START.strftime("%H:%M"),
                _SCAN_WINDOW_END.strftime("%H:%M"),
            )
            return None

        # ---- Extract numeric direction score ----
        if hasattr(direction_score, "composite_score"):
            dir_score_val: float = float(direction_score.composite_score)
        elif hasattr(direction_score, "score"):
            dir_score_val = float(direction_score.score)
        elif hasattr(direction_score, "value"):
            dir_score_val = float(direction_score.value)
        else:
            dir_score_val = float(direction_score)

        # ---- Directional conviction check ----
        abs_dir_score = abs(dir_score_val)
        if abs_dir_score < self.min_direction_score:
            logger.debug(
                "Direction score %.1f below threshold %.1f -- no conviction",
                dir_score_val,
                self.min_direction_score,
            )
            return None

        # ---- Net GEX check (must be negative for amplification) ----
        net_gex: float = 0.0
        if hasattr(gex_profile, "net_gex"):
            net_gex = float(gex_profile.net_gex)
        elif hasattr(gex_profile, "total_gex"):
            net_gex = float(gex_profile.total_gex)

        if net_gex >= 0:
            logger.debug(
                "Net GEX is non-negative ($%.0f) -- dealers not in amplification mode",
                net_gex,
            )
            return None

        # ---- Compute gamma profile and check for high-gamma clusters ----
        gamma_profile = self.compute_realtime_gamma_profile(
            chain, spx_price, minutes_remaining
        )
        if not gamma_profile:
            logger.debug("Empty gamma profile -- no strikes to scan")
            return None

        # Identify high-gamma cluster: strikes with gamma above the 75th percentile
        gamma_values = np.array(list(gamma_profile.values()))
        if len(gamma_values) == 0:
            return None

        gamma_threshold = float(np.percentile(gamma_values, _HIGH_GAMMA_PERCENTILE))
        high_gamma_strikes = [
            k for k, v in gamma_profile.items()
            if v >= gamma_threshold and abs(k - spx_price) <= 10.0
        ]

        if not high_gamma_strikes:
            logger.debug(
                "No high-gamma strikes within 10 pts of SPX %.1f (threshold=%.6f)",
                spx_price,
                gamma_threshold,
            )
            return None

        # ---- Determine overall trade direction ----
        if dir_score_val > 0:
            trade_direction = TradeDirection.LONG_CALL
        else:
            trade_direction = TradeDirection.LONG_PUT

        # =================================================================
        # SETUP 1: Gamma Squeeze (highest priority)
        # =================================================================
        squeeze_result = self.detect_gamma_squeeze(
            gex_profile=gex_profile,
            spx_price=spx_price,
            es_volume=es_volume,
            avg_es_volume=avg_es_volume,
            direction_score=dir_score_val,
            vix1d=vix1d,
            vix1d_prior=vix1d_prior,
        )

        if squeeze_result is not None:
            return self._build_signal_from_squeeze(
                squeeze_result=squeeze_result,
                chain=chain,
                spx_price=spx_price,
                minutes_remaining=minutes_remaining,
                time_zone=time_zone,
                dir_score_val=dir_score_val,
                net_gex=net_gex,
                gamma_profile=gamma_profile,
                current_time_str=current_time_str,
            )

        # =================================================================
        # SETUP 2: Gamma Unpin / Release (second priority)
        # =================================================================
        unpin_result = self.detect_gamma_unpin(
            gex_profile=gex_profile,
            spx_price=spx_price,
            max_oi_strike=max_oi_strike,
            pin_duration_minutes=pin_duration_minutes,
            moc_imbalance=moc_imbalance,
            net_charm_direction=net_charm_direction,
            current_time=current_time_str,
        )

        if unpin_result is not None:
            return self._build_signal_from_unpin(
                unpin_result=unpin_result,
                chain=chain,
                spx_price=spx_price,
                minutes_remaining=minutes_remaining,
                time_zone=time_zone,
                dir_score_val=dir_score_val,
                net_gex=net_gex,
                gamma_profile=gamma_profile,
                current_time_str=current_time_str,
            )

        # =================================================================
        # SETUP 3: General Gamma Acceleration (lowest priority)
        # =================================================================
        return self._check_general_acceleration(
            chain=chain,
            gex_profile=gex_profile,
            spx_price=spx_price,
            trade_direction=trade_direction,
            dir_score_val=dir_score_val,
            minutes_remaining=minutes_remaining,
            time_zone=time_zone,
            net_gex=net_gex,
            gamma_profile=gamma_profile,
            high_gamma_strikes=high_gamma_strikes,
            current_time_str=current_time_str,
        )

    # -----------------------------------------------------------------
    # PRIVATE: Build ScanSignal from Gamma Squeeze result
    # -----------------------------------------------------------------

    def _build_signal_from_squeeze(
        self,
        squeeze_result: Dict,
        chain: OptionsChain,
        spx_price: float,
        minutes_remaining: int,
        time_zone: str,
        dir_score_val: float,
        net_gex: float,
        gamma_profile: Dict[float, float],
        current_time_str: str,
    ) -> Optional[ScanSignal]:
        """Construct a ScanSignal from a confirmed gamma squeeze detection."""
        direction: TradeDirection = squeeze_result["direction"]

        # Select strike
        strike_sel = self.select_acceleration_strike(
            chain=chain,
            direction=direction,
            spx_price=spx_price,
            minutes_remaining=minutes_remaining,
        )

        if strike_sel is None:
            logger.warning(
                "Gamma squeeze detected but no suitable strike found at SPX %.1f",
                spx_price,
            )
            return None

        # Generate exit parameters
        entry_price = strike_sel.mid_price
        exit_params = self.generate_exit_params(
            entry_price=entry_price,
            time_zone=time_zone,
            minutes_remaining=minutes_remaining,
        )

        # Identify landmines for metadata
        landmines = self.identify_gamma_landmines(
            chain=chain,
            spx_price=spx_price,
            minutes_remaining=minutes_remaining,
        )

        # Compute net dealer gamma for metadata
        dealer_gamma = self.compute_net_dealer_gamma(
            chain=chain,
            spx_price=spx_price,
            minutes_remaining=minutes_remaining,
        )

        signal = ScanSignal(
            signal_id=str(uuid.uuid4()),
            scan_type=ScanType.GAMMA_SCALP,
            direction=direction,
            position_type=PositionType.LONG,
            strike=strike_sel.strike,
            strike_selection=strike_sel,
            entry_price=entry_price,
            confidence=squeeze_result["confidence"],
            timestamp=current_time_str,
            session_type=SessionType.POWER_HOUR,
            description=squeeze_result["description"],
            exit_params=exit_params,
            metadata={
                "setup_type": "GAMMA_SQUEEZE",
                "squeeze_strike": squeeze_result["strike"],
                "dealer_gamma_at_strike": squeeze_result["dealer_gamma_at_strike"],
                "volume_ratio": squeeze_result["volume_ratio"],
                "vix1d_change": squeeze_result["vix1d_change"],
                "direction_score": dir_score_val,
                "net_gex": net_gex,
                "gamma_profile_summary": {
                    "num_strikes": len(gamma_profile),
                    "max_gamma": max(gamma_profile.values()) if gamma_profile else 0.0,
                    "max_gamma_strike": (
                        max(gamma_profile, key=gamma_profile.get)
                        if gamma_profile else 0.0
                    ),
                },
                "landmines": landmines[:3],  # Top 3 most dangerous
                "dealer_gamma_summary": {
                    "total_net": sum(dealer_gamma.values()) if dealer_gamma else 0.0,
                    "num_negative_strikes": sum(
                        1 for v in dealer_gamma.values() if v < 0
                    ),
                },
                "minutes_remaining": minutes_remaining,
                "spx_price": spx_price,
            },
        )

        logger.info(
            "SCAN SIGNAL [GAMMA_SQUEEZE]: %s strike=%.0f, entry=$%.2f, "
            "conf=%.0f%%, target=$%.2f, stop=$%.2f",
            direction.value if hasattr(direction, "value") else str(direction),
            strike_sel.strike,
            entry_price,
            squeeze_result["confidence"],
            exit_params["profit_target_price"],
            exit_params["stop_loss_price"],
        )

        return signal

    # -----------------------------------------------------------------
    # PRIVATE: Build ScanSignal from Gamma Unpin result
    # -----------------------------------------------------------------

    def _build_signal_from_unpin(
        self,
        unpin_result: Dict,
        chain: OptionsChain,
        spx_price: float,
        minutes_remaining: int,
        time_zone: str,
        dir_score_val: float,
        net_gex: float,
        gamma_profile: Dict[float, float],
        current_time_str: str,
    ) -> Optional[ScanSignal]:
        """Construct a ScanSignal from a confirmed gamma unpin detection."""
        direction: TradeDirection = unpin_result["direction"]

        # Select strike
        strike_sel = self.select_acceleration_strike(
            chain=chain,
            direction=direction,
            spx_price=spx_price,
            minutes_remaining=minutes_remaining,
        )

        if strike_sel is None:
            logger.warning(
                "Gamma unpin detected but no suitable strike found at SPX %.1f",
                spx_price,
            )
            return None

        # Generate exit parameters
        entry_price = strike_sel.mid_price
        exit_params = self.generate_exit_params(
            entry_price=entry_price,
            time_zone=time_zone,
            minutes_remaining=minutes_remaining,
        )

        signal = ScanSignal(
            signal_id=str(uuid.uuid4()),
            scan_type=ScanType.GAMMA_SCALP,
            direction=direction,
            position_type=PositionType.LONG,
            strike=strike_sel.strike,
            strike_selection=strike_sel,
            entry_price=entry_price,
            confidence=unpin_result["confidence"],
            timestamp=current_time_str,
            session_type=SessionType.POWER_HOUR,
            description=unpin_result["description"],
            exit_params=exit_params,
            metadata={
                "setup_type": "GAMMA_UNPIN",
                "pin_strike": unpin_result["pin_strike"],
                "pin_duration": unpin_result["pin_duration"],
                "moc_imbalance": unpin_result["moc_imbalance"],
                "charm_direction": unpin_result["charm_direction"],
                "release_catalyst": unpin_result["release_catalyst"],
                "direction_score": dir_score_val,
                "net_gex": net_gex,
                "minutes_remaining": minutes_remaining,
                "spx_price": spx_price,
            },
        )

        logger.info(
            "SCAN SIGNAL [GAMMA_UNPIN]: %s strike=%.0f, entry=$%.2f, "
            "conf=%.0f%%, pin=%.0f, duration=%d min, catalyst=%s",
            direction.value if hasattr(direction, "value") else str(direction),
            strike_sel.strike,
            entry_price,
            unpin_result["confidence"],
            unpin_result["pin_strike"],
            unpin_result["pin_duration"],
            unpin_result["release_catalyst"],
        )

        return signal

    # -----------------------------------------------------------------
    # PRIVATE: Check for General Gamma Acceleration
    # -----------------------------------------------------------------

    def _check_general_acceleration(
        self,
        chain: OptionsChain,
        gex_profile: GEXProfile,
        spx_price: float,
        trade_direction: TradeDirection,
        dir_score_val: float,
        minutes_remaining: int,
        time_zone: str,
        net_gex: float,
        gamma_profile: Dict[float, float],
        high_gamma_strikes: List[float],
        current_time_str: str,
    ) -> Optional[ScanSignal]:
        """Check for a general gamma acceleration setup.

        This is the fallback when neither a squeeze nor an unpin is detected,
        but the general gamma environment is conducive to acceleration:
            - Price is near a high-gamma cluster.
            - Net GEX is negative (amplification mode).
            - Directional conviction exists.
            - A suitable strike with liquidity is available.

        Args:
            chain: Options chain.
            gex_profile: GEX profile.
            spx_price: Current SPX level.
            trade_direction: Determined direction.
            dir_score_val: Numeric direction score.
            minutes_remaining: Minutes to settlement.
            time_zone: Intraday time zone.
            net_gex: Net gamma exposure.
            gamma_profile: Per-strike gamma mapping.
            high_gamma_strikes: Strikes in the high-gamma cluster.
            current_time_str: Current time string.

        Returns:
            ScanSignal or None.
        """
        # Check proximity to a high-gamma strike
        nearest_high_gamma = min(
            high_gamma_strikes,
            key=lambda k: abs(k - spx_price),
        )
        distance_to_gamma = abs(spx_price - nearest_high_gamma)

        # Must be within 5 points of a high-gamma strike
        if distance_to_gamma > 5.0:
            logger.debug(
                "Nearest high-gamma strike %.0f is %.1f pts away (>5.0 limit)",
                nearest_high_gamma,
                distance_to_gamma,
            )
            return None

        # Select strike
        strike_sel = self.select_acceleration_strike(
            chain=chain,
            direction=trade_direction,
            spx_price=spx_price,
            minutes_remaining=minutes_remaining,
        )

        if strike_sel is None:
            logger.debug("General acceleration: no suitable strike")
            return None

        # Compute confidence for general acceleration (typically lower than
        # squeeze or unpin since the setup is less specific)
        # Components:
        #   - Gamma proximity:    0-25 (closer to high-gamma strike = higher)
        #   - Direction score:    0-25
        #   - Net GEX magnitude:  0-25
        #   - Gamma magnitude:    0-25
        conf_proximity = float(np.clip((5.0 - distance_to_gamma) / 5.0 * 25.0, 0.0, 25.0))
        conf_direction = float(np.clip(
            (abs(dir_score_val) - self.min_direction_score) / 50.0 * 25.0,
            0.0, 25.0,
        ))
        conf_gex = float(np.clip(abs(net_gex) / 5_000_000.0 * 25.0, 0.0, 25.0))
        gamma_at_nearest = gamma_profile.get(nearest_high_gamma, 0.0)
        conf_gamma = float(np.clip(gamma_at_nearest / 0.10 * 25.0, 0.0, 25.0))

        confidence = float(np.clip(
            conf_proximity + conf_direction + conf_gex + conf_gamma,
            _CONFIDENCE_MIN,
            _CONFIDENCE_MAX,
        ))

        # General acceleration needs at least 40% confidence
        if confidence < 40.0:
            logger.debug(
                "General acceleration confidence %.0f%% < 40%% threshold",
                confidence,
            )
            return None

        entry_price = strike_sel.mid_price
        exit_params = self.generate_exit_params(
            entry_price=entry_price,
            time_zone=time_zone,
            minutes_remaining=minutes_remaining,
        )

        # Identify landmines for context
        landmines = self.identify_gamma_landmines(
            chain=chain,
            spx_price=spx_price,
            minutes_remaining=minutes_remaining,
        )

        dir_label = "BULLISH" if dir_score_val > 0 else "BEARISH"
        description = (
            f"GAMMA ACCELERATION {dir_label}: SPX {spx_price:.1f} near "
            f"high-gamma strike {nearest_high_gamma:.0f} "
            f"(gamma={gamma_at_nearest:.6f}). "
            f"Net GEX ${net_gex:,.0f} (amplification). "
            f"Direction {dir_score_val:+.1f}. "
            f"Confidence {confidence:.0f}%."
        )

        signal = ScanSignal(
            signal_id=str(uuid.uuid4()),
            scan_type=ScanType.GAMMA_SCALP,
            direction=trade_direction,
            position_type=PositionType.LONG,
            strike=strike_sel.strike,
            strike_selection=strike_sel,
            entry_price=entry_price,
            confidence=confidence,
            timestamp=current_time_str,
            session_type=SessionType.POWER_HOUR,
            description=description,
            exit_params=exit_params,
            metadata={
                "setup_type": "GAMMA_ACCELERATION",
                "nearest_high_gamma_strike": nearest_high_gamma,
                "gamma_at_nearest": gamma_at_nearest,
                "distance_to_gamma": distance_to_gamma,
                "direction_score": dir_score_val,
                "net_gex": net_gex,
                "gamma_profile_summary": {
                    "num_strikes": len(gamma_profile),
                    "max_gamma": max(gamma_profile.values()) if gamma_profile else 0.0,
                    "high_gamma_strikes": high_gamma_strikes[:5],
                },
                "landmines": landmines[:3],
                "minutes_remaining": minutes_remaining,
                "spx_price": spx_price,
            },
        )

        logger.info(
            "SCAN SIGNAL [GAMMA_ACCELERATION]: %s strike=%.0f, entry=$%.2f, "
            "conf=%.0f%%, near_gamma_strike=%.0f",
            trade_direction.value if hasattr(trade_direction, "value") else str(trade_direction),
            strike_sel.strike,
            entry_price,
            confidence,
            nearest_high_gamma,
        )

        return signal
