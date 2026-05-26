"""
SCANIFY SPX 0DTE - Core Scan #1: Directional OTM Scanner

Identifies the highest-probability directional OTM option trade for each
session by synthesising five independent scoring factors into a composite
direction score, selecting an optimal strike, verifying entry conditions,
and emitting a fully-specified trade signal.

Scan cadence: every 1 minute, 9:45 AM - 3:00 PM ET.

Factor Model
-------------
1. Market Internals   (NYSE TICK, TRIN, A/D, Up/Down Volume)
2. Options Flow       (P/C ratio, premium flow, blocks, sweeps)
3. Price Action       (VWAP, expected move, cumulative delta, order book)
4. GEX Structure      (net GEX, gamma flip, transition zones)
5. Cross-Asset        (VIX, VIX1D, 10Y yield, DXY)

Each factor produces a score in [-100, +100] (cross-asset: [-50, +50]).
The composite is a weighted average that must clear threshold *and*
confluence filters before a signal is generated.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .models import (
    DirectionScore,
    StrikeSelection,
    ScanSignal,
    ScanType,
    TradeDirection,
    PositionType,
    SessionType,
    TimeZoneType,
    MarketInternals,
    CrossAssetData,
    ESOrderBook,
    GEXProfile,
    OptionsChain,
    OptionSide,
)
from .constants import (
    DIRECTION_THRESHOLDS,
    FACTOR_WEIGHTS,
    STRIKE_SELECTION,
    EXIT_CONSTANTS,
    LIQUIDITY_FILTERS,
    TIME_ZONES,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_SCORE_FLOOR: float = -100.0
_SCORE_CEIL: float = 100.0
_CROSS_ASSET_FLOOR: float = -50.0
_CROSS_ASSET_CEIL: float = 50.0


def _clamp(value: float, lo: float, hi: float) -> float:
    """Clamp *value* to the closed interval [lo, hi]."""
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Core Scanner
# ---------------------------------------------------------------------------

class DirectionalOTMScanner:
    """Core Scan #1: Identifies highest-probability directional OTM option trades.

    Executes every 1 minute from 9:45 AM - 3:00 PM ET.

    The scanner follows a strict four-step pipeline:
        1. **Direction determination** -- score five independent factors and
           compute a weighted composite direction score.
        2. **Strike selection** -- given the directional signal, select the
           optimal OTM strike respecting delta, liquidity, and time-of-day
           constraints.
        3. **Entry condition verification** -- confirm that all pre-requisites
           (no imminent events, no VIX spike, valid window) are satisfied.
        4. **Signal generation** -- package entry price, stop, target, and
           position sizing into a :class:`ScanSignal`.

    Parameters
    ----------
    factor_weights : dict
        Mapping with keys ``market_internals``, ``options_flow``,
        ``price_action``, ``gex_structure``, ``cross_asset`` whose float
        values must sum to 1.0.
    entry_threshold : float
        Minimum absolute composite score to trigger a directional signal.
    strong_threshold : float
        Absolute composite score above which the signal is classified as
        *strong*, enabling more aggressive strike selection.
    min_confluence : int
        Minimum number of the five factors that must agree on direction.
    max_opposing : float
        Maximum score (in the opposing direction) that any single factor
        may register without invalidating the signal.
    """

    # --------------------------------------------------------------------- #
    # Construction
    # --------------------------------------------------------------------- #

    def __init__(
        self,
        factor_weights: Dict[str, float],
        entry_threshold: float = 40.0,
        strong_threshold: float = 65.0,
        min_confluence: int = 3,
        max_opposing: float = 30.0,
    ) -> None:
        # Validate weights ------------------------------------------------
        required_keys = {
            "market_internals",
            "options_flow",
            "price_action",
            "gex_structure",
            "cross_asset",
        }
        missing = required_keys - set(factor_weights.keys())
        if missing:
            raise ValueError(
                f"factor_weights missing required keys: {missing}"
            )

        weight_sum = sum(factor_weights[k] for k in required_keys)
        if abs(weight_sum - 1.0) > 1e-6:
            raise ValueError(
                f"factor_weights must sum to 1.0, got {weight_sum:.6f}"
            )

        for key in required_keys:
            if factor_weights[key] < 0.0:
                raise ValueError(
                    f"factor_weights['{key}'] must be non-negative, "
                    f"got {factor_weights[key]}"
                )

        self.factor_weights: Dict[str, float] = dict(factor_weights)
        self.entry_threshold: float = entry_threshold
        self.strong_threshold: float = strong_threshold
        self.min_confluence: int = min_confluence
        self.max_opposing: float = max_opposing

        logger.info(
            "DirectionalOTMScanner initialised  "
            "entry=%.1f  strong=%.1f  confluence=%d  max_opposing=%.1f  "
            "weights=%s",
            self.entry_threshold,
            self.strong_threshold,
            self.min_confluence,
            self.max_opposing,
            {k: f"{v:.2f}" for k, v in self.factor_weights.items()},
        )

    # ================================================================== #
    #  STEP 1 -- Direction Determination (five scoring factors)           #
    # ================================================================== #

    # ------------------------------------------------------------------ #
    # Factor 1: Market Internals
    # ------------------------------------------------------------------ #

    def score_market_internals(self, internals: MarketInternals) -> float:
        """Score market internals on a -100 to +100 scale.

        Sub-components
        --------------
        **NYSE TICK (10-min average)**
            * > +500 : +40
            * > +300 : +25
            * < -500 : -40
            * < -300 : -25

        **Cumulative TICK**
            * Positive / rising : +15
            * Negative / falling : -15

        **NYSE TRIN**
            * < 0.75 : +15  (bullish breadth)
            * > 2.00 : +10  (contrarian reversal)
            * > 1.50 : -15  (bearish breadth)

        **Advance / Decline Ratio**
            * > 2:1 : +15
            * < 1:2 : -15

        **Up / Down Volume Ratio**
            * > 3:1 : +15
            * < 1:3 : -15

        Parameters
        ----------
        internals : MarketInternals
            Current market-internals snapshot.

        Returns
        -------
        float
            Composite market-internals score in [-100, +100].
        """
        score: float = 0.0

        # -- NYSE TICK (10-min average) -----------------------------------
        tick_avg: float = getattr(internals, "tick_10min_avg", 0.0)
        if tick_avg > 500:
            score += 40.0
        elif tick_avg > 300:
            score += 25.0
        elif tick_avg < -500:
            score -= 40.0
        elif tick_avg < -300:
            score -= 25.0

        # -- Cumulative TICK ----------------------------------------------
        cum_tick: float = getattr(internals, "tick_cumulative", 0.0)
        cum_tick_rising: bool = getattr(internals, "tick_cumulative_rising", cum_tick > 0)
        if cum_tick > 0 and cum_tick_rising:
            score += 15.0
        elif cum_tick < 0 and not cum_tick_rising:
            score -= 15.0

        # -- NYSE TRIN ----------------------------------------------------
        trin: float = getattr(internals, "trin", 1.0)
        if trin < 0.75:
            score += 15.0
        elif trin > 2.00:
            # Extreme bearish TRIN is contrarian bullish
            score += 10.0
        elif trin > 1.50:
            score -= 15.0

        # -- Advance / Decline Ratio --------------------------------------
        ad_ratio: float = getattr(internals, "ad_ratio", 1.0)
        if ad_ratio > 2.0:
            score += 15.0
        elif ad_ratio < 0.5:
            score -= 15.0

        # -- Up / Down Volume Ratio ----------------------------------------
        uvol_dvol_ratio: float = getattr(internals, "uvol_dvol_ratio", 1.0)
        if uvol_dvol_ratio > 3.0:
            score += 15.0
        elif uvol_dvol_ratio < (1.0 / 3.0):
            score -= 15.0

        clamped = _clamp(score, _SCORE_FLOOR, _SCORE_CEIL)
        logger.debug(
            "Market internals score: %.1f  (tick_avg=%.0f, cum_tick=%.0f, "
            "trin=%.2f, ad=%.2f, uvdv=%.2f)",
            clamped, tick_avg, cum_tick, trin, ad_ratio, uvol_dvol_ratio,
        )
        return clamped

    # ------------------------------------------------------------------ #
    # Factor 2: Options Flow
    # ------------------------------------------------------------------ #

    def score_options_flow(
        self,
        chain: OptionsChain,
        flow_data: Optional[dict] = None,
    ) -> float:
        """Score options flow on a -100 to +100 scale.

        Sub-components
        --------------
        **0DTE Put/Call Ratio**
            * < 0.70 : +20  (call-heavy, bullish)
            * > 1.50 : -20  (put-heavy, bearish)

        **0DTE Premium Flow** ($ calls at ask - $ puts at ask)
            * Net positive > $50 M : +25
            * Net negative > $50 M : -25

        **Block Trade Direction** (trades > 100 contracts)
            * Net bullish : +15
            * Net bearish : -15

        **Sweep Detection** (multi-exchange sweeps)
            * Call sweeps dominant : +20
            * Put sweeps dominant  : -20

        Parameters
        ----------
        chain : OptionsChain
            Current 0DTE options chain.
        flow_data : dict, optional
            Supplemental real-time flow data. Expected keys:
            ``net_premium_flow`` (float, dollars),
            ``block_net_direction`` (float, positive=bullish),
            ``call_sweep_count`` (int), ``put_sweep_count`` (int).

        Returns
        -------
        float
            Options-flow score in [-100, +100].
        """
        score: float = 0.0
        flow: dict = flow_data or {}

        # -- Put / Call Ratio (from chain) --------------------------------
        pc_ratio: float = getattr(chain, "put_call_ratio", 0.0)
        if pc_ratio > 0:
            if pc_ratio < 0.70:
                score += 20.0
            elif pc_ratio > 1.50:
                score -= 20.0

        # -- Premium Flow -------------------------------------------------
        net_premium: float = flow.get("net_premium_flow", 0.0)
        premium_threshold: float = 50_000_000.0  # $50 M
        if net_premium > premium_threshold:
            score += 25.0
        elif net_premium < -premium_threshold:
            score -= 25.0

        # -- Block Trade Direction ----------------------------------------
        block_net: float = flow.get("block_net_direction", 0.0)
        if block_net > 0:
            score += 15.0
        elif block_net < 0:
            score -= 15.0

        # -- Sweep Detection ----------------------------------------------
        call_sweeps: int = flow.get("call_sweep_count", 0)
        put_sweeps: int = flow.get("put_sweep_count", 0)
        if call_sweeps > put_sweeps and call_sweeps > 0:
            score += 20.0
        elif put_sweeps > call_sweeps and put_sweeps > 0:
            score -= 20.0

        clamped = _clamp(score, _SCORE_FLOOR, _SCORE_CEIL)
        logger.debug(
            "Options flow score: %.1f  (pc_ratio=%.2f, net_premium=%.0f, "
            "block_net=%.0f, call_sweeps=%d, put_sweeps=%d)",
            clamped, pc_ratio, net_premium, block_net,
            call_sweeps, put_sweeps,
        )
        return clamped

    # ------------------------------------------------------------------ #
    # Factor 3: Price Action
    # ------------------------------------------------------------------ #

    def score_price_action(
        self,
        spx_price: float,
        vwap: float,
        em_upper: float,
        em_lower: float,
        es_cum_delta: float,
        order_book: ESOrderBook,
        momentum_5min: float,
    ) -> float:
        """Score price action on a -100 to +100 scale.

        Sub-components
        --------------
        **Position vs VWAP**
            * Above VWAP and rising : +15
            * Below VWAP and falling : -15

        **Position vs Expected Move bounds**
            * Near upper EM boundary : -10  (mean-reversion headwind)
            * Near lower EM boundary : +10  (mean-reversion tailwind)

        **ES Cumulative Delta**
            * Positive / rising : +15
            * Negative / falling : -15

        **ES Order Book Imbalance**
            * Bid side > ask side by 2x : +15
            * Ask side > bid side by 2x : -15

        **5-min Momentum**
            * Positive acceleration : +10
            * Negative acceleration : -10

        Parameters
        ----------
        spx_price : float
            Current SPX spot price.
        vwap : float
            Session VWAP.
        em_upper : float
            Upper expected-move boundary.
        em_lower : float
            Lower expected-move boundary.
        es_cum_delta : float
            ES futures cumulative delta (positive = net buying).
        order_book : ESOrderBook
            Current ES Level-II order-book snapshot.
        momentum_5min : float
            5-minute price momentum (positive = accelerating upward).

        Returns
        -------
        float
            Price-action score in [-100, +100].
        """
        score: float = 0.0

        # -- VWAP ----------------------------------------------------------
        above_vwap: bool = spx_price > vwap
        # "Rising" is approximated by momentum being in the same direction
        if above_vwap and momentum_5min > 0:
            score += 15.0
        elif not above_vwap and momentum_5min < 0:
            score -= 15.0

        # -- Expected Move boundaries -------------------------------------
        em_range = em_upper - em_lower
        if em_range > 0:
            upper_proximity = (em_upper - spx_price) / em_range
            lower_proximity = (spx_price - em_lower) / em_range
            # "Near" = within 20% of the boundary from the edge
            if upper_proximity < 0.20:
                score -= 10.0
            elif lower_proximity < 0.20:
                score += 10.0

        # -- ES Cumulative Delta ------------------------------------------
        es_cum_delta_rising: bool = getattr(
            order_book, "cum_delta_rising", es_cum_delta > 0
        )
        if es_cum_delta > 0 and es_cum_delta_rising:
            score += 15.0
        elif es_cum_delta < 0 and not es_cum_delta_rising:
            score -= 15.0

        # -- Order Book Imbalance -----------------------------------------
        total_bid: float = getattr(order_book, "total_bid_size", 0.0)
        total_ask: float = getattr(order_book, "total_ask_size", 0.0)
        if total_ask > 0 and total_bid / total_ask >= 2.0:
            score += 15.0
        elif total_bid > 0 and total_ask / total_bid >= 2.0:
            score -= 15.0

        # -- 5-min Momentum -----------------------------------------------
        if momentum_5min > 0:
            score += 10.0
        elif momentum_5min < 0:
            score -= 10.0

        clamped = _clamp(score, _SCORE_FLOOR, _SCORE_CEIL)
        logger.debug(
            "Price action score: %.1f  (spx=%.2f, vwap=%.2f, "
            "es_delta=%.0f, mom5=%.2f)",
            clamped, spx_price, vwap, es_cum_delta, momentum_5min,
        )
        return clamped

    # ------------------------------------------------------------------ #
    # Factor 4: GEX Structure
    # ------------------------------------------------------------------ #

    def score_gex_structure(
        self,
        gex_profile: GEXProfile,
        spx_price: float,
        prior_spx: float,
    ) -> float:
        """Score GEX (gamma exposure) structure on a -100 to +100 scale.

        Sub-components
        --------------
        **Net GEX sign**
            * Positive (dealers long gamma) : reduces directional score by 20 %
            * Negative (dealers short gamma) : increases directional score by 20 %

        **Position vs Gamma Flip level**
            * Above gamma flip : +20
            * Below gamma flip : -20

        **Distance to +GEX / -GEX targets**
            * Moving toward +GEX wall : +15
            * Moving toward -GEX wall : -15

        **Transition Zone**
            * Inside : 0
            * Breaking above : +25
            * Breaking below : -25

        Parameters
        ----------
        gex_profile : GEXProfile
            Current GEX profile with net exposure, flip level, and walls.
        spx_price : float
            Current SPX spot price.
        prior_spx : float
            SPX price at the prior scan interval (1 min ago).

        Returns
        -------
        float
            GEX-structural score in [-100, +100].
        """
        score: float = 0.0

        # -- Position vs Gamma Flip level ----------------------------------
        gamma_flip: float = getattr(gex_profile, "gamma_flip_level", spx_price)
        if spx_price > gamma_flip:
            score += 20.0
        elif spx_price < gamma_flip:
            score -= 20.0

        # -- Distance to major GEX walls -----------------------------------
        pos_gex_target: float = getattr(
            gex_profile, "positive_gex_target", spx_price
        )
        neg_gex_target: float = getattr(
            gex_profile, "negative_gex_target", spx_price
        )
        price_move = spx_price - prior_spx
        dist_to_pos = abs(pos_gex_target - spx_price)
        dist_to_neg = abs(neg_gex_target - spx_price)

        if price_move > 0 and dist_to_pos < dist_to_neg:
            # Moving upward toward positive-GEX wall (bullish magnet)
            score += 15.0
        elif price_move < 0 and dist_to_neg < dist_to_pos:
            # Moving downward toward negative-GEX wall (bearish magnet)
            score -= 15.0

        # -- Transition Zone -----------------------------------------------
        transition_upper: float = getattr(
            gex_profile, "transition_upper", gamma_flip
        )
        transition_lower: float = getattr(
            gex_profile, "transition_lower", gamma_flip
        )
        inside_transition = transition_lower <= spx_price <= transition_upper

        if inside_transition:
            # Inside the transition zone -- directionally neutral
            pass
        elif spx_price > transition_upper and prior_spx <= transition_upper:
            # Breaking above the transition zone
            score += 25.0
        elif spx_price < transition_lower and prior_spx >= transition_lower:
            # Breaking below the transition zone
            score -= 25.0

        # -- Net GEX sign modifier -----------------------------------------
        net_gex: float = getattr(gex_profile, "net_gex", 0.0)
        if net_gex > 0:
            # Positive GEX (dealers long gamma) dampens directional moves
            score *= 0.80
        elif net_gex < 0:
            # Negative GEX (dealers short gamma) amplifies directional moves
            score *= 1.20

        clamped = _clamp(score, _SCORE_FLOOR, _SCORE_CEIL)
        logger.debug(
            "GEX structure score: %.1f  (net_gex=%.0f, flip=%.1f, "
            "spx=%.2f, prior=%.2f)",
            clamped, net_gex, gamma_flip, spx_price, prior_spx,
        )
        return clamped

    # ------------------------------------------------------------------ #
    # Factor 5: Cross-Asset Confirmation
    # ------------------------------------------------------------------ #

    def score_cross_asset(
        self,
        cross_data: CrossAssetData,
        spx_direction: float,
    ) -> float:
        """Score cross-asset confirmation on a -50 to +50 scale.

        Sub-components
        --------------
        **VIX vs SPX**
            * VIX falling + SPX rising : +15  (confirming)
            * VIX rising + SPX falling : +15  (confirming)
            * Divergence (VIX rising + SPX rising) : -15

        **VIX1D vs intraday average**
            * VIX1D below average : +10
            * VIX1D above average : -10

        **US 10Y yield**
            * Falling + SPX rising : +10  (goldilocks)
            * Rising sharply + SPX falling : -10

        **DXY (Dollar Index)**
            * Falling : +5
            * Rising sharply : -5

        Parameters
        ----------
        cross_data : CrossAssetData
            Cross-asset snapshot (VIX, VIX1D, yields, DXY).
        spx_direction : float
            Current directional bias of SPX (positive = up, negative = down).

        Returns
        -------
        float
            Cross-asset score in [-50, +50].
        """
        score: float = 0.0
        spx_rising: bool = spx_direction > 0

        # -- VIX vs SPX ----------------------------------------------------
        vix_change: float = getattr(cross_data, "vix_change", 0.0)
        vix_falling: bool = vix_change < 0

        if vix_falling and spx_rising:
            score += 15.0
        elif not vix_falling and not spx_rising:
            # VIX rising while SPX falling -- confirming the bearish move
            score += 15.0
        elif not vix_falling and spx_rising:
            # Divergence -- VIX rising while SPX also rising
            score -= 15.0

        # -- VIX1D vs intraday average ------------------------------------
        vix1d: float = getattr(cross_data, "vix1d", 0.0)
        vix1d_avg: float = getattr(cross_data, "vix1d_intraday_avg", vix1d)
        if vix1d_avg > 0:
            if vix1d < vix1d_avg:
                score += 10.0
            elif vix1d > vix1d_avg:
                score -= 10.0

        # -- US 10Y yield --------------------------------------------------
        yield_10y_change: float = getattr(cross_data, "yield_10y_change", 0.0)
        if yield_10y_change < 0 and spx_rising:
            score += 10.0
        elif yield_10y_change > 0.05 and not spx_rising:
            score -= 10.0

        # -- DXY -----------------------------------------------------------
        dxy_change: float = getattr(cross_data, "dxy_change", 0.0)
        if dxy_change < 0:
            score += 5.0
        elif dxy_change > 0.30:
            # "Rising sharply" defined as > 0.30% intraday move
            score -= 5.0

        clamped = _clamp(score, _CROSS_ASSET_FLOOR, _CROSS_ASSET_CEIL)
        logger.debug(
            "Cross-asset score: %.1f  (vix_chg=%.2f, vix1d=%.1f, "
            "10y_chg=%.3f, dxy_chg=%.3f)",
            clamped, vix_change, vix1d, yield_10y_change, dxy_change,
        )
        return clamped

    # ------------------------------------------------------------------ #
    # Composite Direction Score
    # ------------------------------------------------------------------ #

    def compute_direction_score(
        self,
        internals: MarketInternals,
        chain: OptionsChain,
        spx_price: float,
        vwap: float,
        em_upper: float,
        em_lower: float,
        order_book: ESOrderBook,
        gex_profile: GEXProfile,
        cross_data: CrossAssetData,
        prior_spx: float,
        momentum_5min: float,
        flow_data: Optional[dict] = None,
    ) -> DirectionScore:
        """Compute the composite direction score from all five factors.

        The composite is computed as::

            COMPOSITE = SUM(Factor_i * Weight_i) / SUM(Weight_i)

        **Signal Thresholds**

        ============================  ==========================================
        Score                         Interpretation
        ============================  ==========================================
        > +40                         BULLISH -- scan for OTM CALL entries
        < -40                         BEARISH -- scan for OTM PUT entries
        between -40 and +40           NO SIGNAL -- wait
        > +65                         STRONG BULLISH -- aggressive strikes
        < -65                         STRONG BEARISH -- aggressive strikes
        ============================  ==========================================

        **Confluence Requirements**

        * At least ``min_confluence`` of the 5 factors must agree on
          direction (same sign as composite).
        * No single factor may be *strongly opposing* (i.e. > ``max_opposing``
          points counter to the composite direction).

        Parameters
        ----------
        internals : MarketInternals
        chain : OptionsChain
        spx_price, vwap, em_upper, em_lower : float
        order_book : ESOrderBook
        gex_profile : GEXProfile
        cross_data : CrossAssetData
        prior_spx, momentum_5min : float
        flow_data : dict, optional

        Returns
        -------
        DirectionScore
            Fully populated direction-score object.
        """
        # --- Compute individual factor scores ----------------------------
        f1 = self.score_market_internals(internals)
        f2 = self.score_options_flow(chain, flow_data=flow_data)
        f3 = self.score_price_action(
            spx_price, vwap, em_upper, em_lower,
            getattr(order_book, "cumulative_delta", 0.0),
            order_book, momentum_5min,
        )
        f4 = self.score_gex_structure(gex_profile, spx_price, prior_spx)
        f5 = self.score_cross_asset(cross_data, spx_direction=momentum_5min)

        factor_scores: Dict[str, float] = {
            "market_internals": f1,
            "options_flow": f2,
            "price_action": f3,
            "gex_structure": f4,
            "cross_asset": f5,
        }

        # --- Weighted composite ------------------------------------------
        weighted_sum: float = 0.0
        weight_total: float = 0.0
        for key, fscore in factor_scores.items():
            w = self.factor_weights[key]
            weighted_sum += fscore * w
            weight_total += w

        composite: float = weighted_sum / weight_total if weight_total > 0 else 0.0
        composite = _clamp(composite, _SCORE_FLOOR, _SCORE_CEIL)

        # --- Direction & strength ----------------------------------------
        if composite > self.strong_threshold:
            direction = TradeDirection.BULL
            is_strong = True
        elif composite > self.entry_threshold:
            direction = TradeDirection.BULL
            is_strong = False
        elif composite < -self.strong_threshold:
            direction = TradeDirection.BEAR
            is_strong = True
        elif composite < -self.entry_threshold:
            direction = TradeDirection.BEAR
            is_strong = False
        else:
            direction = TradeDirection.NEUTRAL
            is_strong = False

        # --- Confluence check --------------------------------------------
        composite_sign = 1.0 if composite >= 0 else -1.0
        agreeing_count: int = 0
        max_opposing_score: float = 0.0

        for key, fscore in factor_scores.items():
            # Factor agrees if its sign matches the composite sign
            if fscore * composite_sign > 0:
                agreeing_count += 1
            else:
                # Track the magnitude of the strongest opposing factor
                opposing_magnitude = abs(fscore)
                if opposing_magnitude > max_opposing_score:
                    max_opposing_score = opposing_magnitude

        confluence_met: bool = agreeing_count >= self.min_confluence
        no_strong_opposition: bool = max_opposing_score <= self.max_opposing

        # If confluence or opposition filters fail, suppress the signal
        signal_valid: bool = True
        invalidation_reason: str = ""

        if direction != TradeDirection.NEUTRAL:
            if not confluence_met:
                signal_valid = False
                invalidation_reason = (
                    f"Confluence not met: {agreeing_count}/{self.min_confluence} "
                    f"factors agree"
                )
                logger.info(
                    "Direction score %.1f invalidated -- %s",
                    composite, invalidation_reason,
                )
            elif not no_strong_opposition:
                signal_valid = False
                invalidation_reason = (
                    f"Strong opposing factor: {max_opposing_score:.1f} "
                    f"> max {self.max_opposing:.1f}"
                )
                logger.info(
                    "Direction score %.1f invalidated -- %s",
                    composite, invalidation_reason,
                )

        if not signal_valid:
            direction = TradeDirection.NEUTRAL
            is_strong = False

        logger.info(
            "Composite direction score: %.1f  direction=%s  strong=%s  "
            "confluence=%d/5  max_opposing=%.1f  factors=[%.1f, %.1f, "
            "%.1f, %.1f, %.1f]%s",
            composite, direction.name if hasattr(direction, "name") else direction,
            is_strong, agreeing_count, max_opposing_score,
            f1, f2, f3, f4, f5,
            f"  INVALIDATED: {invalidation_reason}" if invalidation_reason else "",
        )

        return DirectionScore(
            composite=composite,
            direction=direction,
            is_strong=is_strong,
            factor_scores=factor_scores,
            factor_weights=dict(self.factor_weights),
            agreeing_factors=agreeing_count,
            max_opposing_factor=max_opposing_score,
            signal_valid=signal_valid,
            invalidation_reason=invalidation_reason,
        )

    # ================================================================== #
    #  STEP 2 -- Strike Selection                                         #
    # ================================================================== #

    def select_strike(
        self,
        chain: OptionsChain,
        direction: TradeDirection,
        score_magnitude: float,
        vix1d: float,
        time_zone: str,
        session_type: SessionType,
        spx_price: float,
    ) -> Optional[StrikeSelection]:
        """Select the optimal OTM strike for the given directional signal.

        The selection algorithm proceeds through the following stages:

        1. **Determine target delta range** based on signal strength:

           * MODERATE (score 40-65): delta 0.15 - 0.25, distance 10-20 pts OTM
           * STRONG (score > 65): delta 0.25 - 0.40, distance 5-15 pts OTM

        2. **Apply time-of-day adjustment**:

           * Before 11:00 AM   : standard delta (no adjustment)
           * 11:00 AM - 1:30 PM: +0.05 delta (need closer strike)
           * 1:30 PM - 3:00 PM : +0.10 delta (theta cliff)
           * After 3:00 PM     : ATM or 1 strike OTM only

        3. **Apply VIX1D adjustment**:

           * VIX1D > 25 : move 5 pts further OTM
           * VIX1D < 12 : move 5 pts closer to ATM

        4. **Spread width filter**:

           * < $5 premium  : max $0.50 spread
           * $5-$20 premium: max $1.00 spread
           * > $20 premium : max $2.00 spread

        5. **Liquidity filter** (min OI 500, min volume 200):

           If the candidate strike fails, move 1 strike closer to ATM and
           recheck.

        Parameters
        ----------
        chain : OptionsChain
            0DTE options chain.
        direction : TradeDirection
            BULLISH or BEARISH.
        score_magnitude : float
            Absolute value of the composite direction score.
        vix1d : float
            Current VIX1D reading.
        time_zone : str
            Current intraday time zone identifier.
        session_type : SessionType
            Current session classification.
        spx_price : float
            Current SPX price.

        Returns
        -------
        StrikeSelection or None
            Selected strike with metadata, or ``None`` if no suitable strike
            is found.
        """
        if direction == TradeDirection.NEUTRAL:
            logger.debug("select_strike called with NEUTRAL direction; returning None")
            return None

        # -- Determine option side ----------------------------------------
        option_side: OptionSide = (
            OptionSide.CALL if direction == TradeDirection.BULL
            else OptionSide.PUT
        )

        # -- Target delta range -------------------------------------------
        is_strong = score_magnitude >= self.strong_threshold
        if is_strong:
            delta_low = 0.25
            delta_high = 0.40
            distance_min = 5.0
            distance_max = 15.0
        else:
            delta_low = 0.15
            delta_high = 0.25
            distance_min = 10.0
            distance_max = 20.0

        # -- Time-of-day delta adjustment ----------------------------------
        time_delta_adj = self._time_of_day_delta_adjustment(time_zone)
        delta_low += time_delta_adj
        delta_high += time_delta_adj

        # Ensure delta bounds stay meaningful
        delta_low = max(0.05, delta_low)
        delta_high = min(0.95, delta_high)

        # Check for post-3 PM override (ATM or 1 strike OTM only)
        force_atm = self._is_post_3pm(time_zone)

        # -- VIX1D adjustment (distance offset, not delta) ----------------
        vix_distance_adj: float = 0.0
        if vix1d > 25.0:
            vix_distance_adj = 5.0   # Move further OTM
        elif vix1d < 12.0:
            vix_distance_adj = -5.0  # Move closer to ATM

        distance_min = max(0.0, distance_min + vix_distance_adj)
        distance_max = max(distance_min, distance_max + vix_distance_adj)

        # -- Retrieve candidate contracts ---------------------------------
        contracts = self._get_otm_candidates(chain, option_side)
        if not contracts:
            logger.warning("No OTM %s contracts found in chain", option_side)
            return None

        # Sort by distance from ATM (ascending)
        contracts.sort(key=lambda c: abs(c.strike - spx_price))

        # -- Force ATM if post-3 PM ----------------------------------------
        if force_atm and contracts:
            candidate = contracts[0]  # Closest to ATM
            if self._passes_liquidity_filter(candidate):
                if self._passes_spread_filter(candidate):
                    return self._build_strike_selection(
                        candidate, option_side, spx_price, is_strong,
                    )
            # If ATM fails filters, try next closest
            if len(contracts) > 1:
                candidate = contracts[1]
                if (self._passes_liquidity_filter(candidate)
                        and self._passes_spread_filter(candidate)):
                    return self._build_strike_selection(
                        candidate, option_side, spx_price, is_strong,
                    )
            logger.info("Post-3PM: no liquid ATM/near-ATM strike found")
            return None

        # -- Standard selection: filter by delta and distance ---------------
        best: Optional[object] = None
        for contract in contracts:
            distance = abs(contract.strike - spx_price)

            # Delta filter
            contract_delta = abs(getattr(contract, "delta", 0.0) or 0.0)
            if not (delta_low <= contract_delta <= delta_high):
                continue

            # Distance filter
            if not (distance_min <= distance <= distance_max):
                continue

            # Spread width filter
            if not self._passes_spread_filter(contract):
                continue

            # Liquidity filter
            if not self._passes_liquidity_filter(contract):
                continue

            best = contract
            break

        # -- Fallback: relax liquidity, move 1 strike closer ---------------
        if best is None:
            logger.debug(
                "Primary strike selection failed; attempting fallback "
                "(1 strike closer, relaxed liquidity)"
            )
            for contract in contracts:
                distance = abs(contract.strike - spx_price)
                contract_delta = abs(getattr(contract, "delta", 0.0) or 0.0)

                # Relax delta range slightly
                if not (delta_low * 0.8 <= contract_delta <= delta_high * 1.2):
                    continue

                # Relax distance: allow closer
                if distance > distance_max:
                    continue

                # Still enforce spread filter
                if not self._passes_spread_filter(contract):
                    continue

                # Relaxed liquidity: 50% of normal thresholds
                oi = getattr(contract, "open_interest", 0)
                vol = getattr(contract, "volume", 0)
                if oi >= 250 and vol >= 100:
                    best = contract
                    break

        if best is None:
            logger.info(
                "No suitable OTM %s strike found (delta=[%.2f, %.2f], "
                "dist=[%.0f, %.0f], vix1d=%.1f, tz=%s)",
                option_side, delta_low, delta_high,
                distance_min, distance_max, vix1d, time_zone,
            )
            return None

        return self._build_strike_selection(best, option_side, spx_price, is_strong)

    # -- Strike-selection helper methods -----------------------------------

    @staticmethod
    def _time_of_day_delta_adjustment(time_zone: str) -> float:
        """Return the additive delta adjustment for the current time zone.

        Before 11:00 AM  : 0.00  (standard)
        11:00 AM - 1:30 PM: +0.05
        1:30 PM - 3:00 PM : +0.10
        After 3:00 PM     : 0.00  (handled separately via force-ATM)
        """
        tz_upper = time_zone.upper() if isinstance(time_zone, str) else ""
        if "MIDDAY" in tz_upper or "LULL" in tz_upper:
            return 0.05
        if "AFTERNOON" in tz_upper or "ACCEL" in tz_upper:
            return 0.10
        return 0.0

    @staticmethod
    def _is_post_3pm(time_zone: str) -> bool:
        """Return True if the time zone indicates post-3:00 PM."""
        tz_upper = time_zone.upper() if isinstance(time_zone, str) else ""
        return "POWER" in tz_upper or "SETTLEMENT" in tz_upper

    @staticmethod
    def _get_otm_candidates(chain: OptionsChain, side: OptionSide) -> list:
        """Extract OTM contracts of the specified side from the chain."""
        spx_price: float = getattr(chain, "underlying_price", 0.0)
        all_contracts = getattr(chain, "contracts", [])

        candidates = []
        for c in all_contracts:
            opt_type = getattr(c, "option_type", "")
            strike = getattr(c, "strike", 0.0)

            # Match side
            side_str = side.value if hasattr(side, "value") else str(side)
            if opt_type.upper() != side_str.upper():
                continue

            # OTM filter
            if side_str.upper() == "CALL" and strike <= spx_price:
                continue
            if side_str.upper() == "PUT" and strike >= spx_price:
                continue

            candidates.append(c)

        return candidates

    @staticmethod
    def _passes_spread_filter(contract) -> bool:
        """Check bid-ask spread width filter.

        Max allowed spread:
            < $5  premium : $0.50
            $5 - $20      : $1.00
            > $20         : $2.00
        """
        bid = getattr(contract, "bid", 0.0)
        ask = getattr(contract, "ask", 0.0)
        spread = ask - bid
        mid = (bid + ask) / 2.0

        if mid <= 0:
            return False

        if mid < 5.0:
            return spread <= 0.50
        elif mid <= 20.0:
            return spread <= 1.00
        else:
            return spread <= 2.00

    @staticmethod
    def _passes_liquidity_filter(contract) -> bool:
        """Check minimum open interest (500) and volume (200)."""
        oi = getattr(contract, "open_interest", 0)
        vol = getattr(contract, "volume", 0)
        return oi >= 500 and vol >= 200

    @staticmethod
    def _build_strike_selection(
        contract,
        option_side: OptionSide,
        spx_price: float,
        is_strong: bool,
    ) -> StrikeSelection:
        """Build a :class:`StrikeSelection` from the chosen contract."""
        strike = getattr(contract, "strike", 0.0)
        bid = getattr(contract, "bid", 0.0)
        ask = getattr(contract, "ask", 0.0)
        mid_price = (bid + ask) / 2.0
        delta = abs(getattr(contract, "delta", 0.0) or 0.0)
        distance = abs(strike - spx_price)
        oi = getattr(contract, "open_interest", 0)
        volume = getattr(contract, "volume", 0)
        iv = getattr(contract, "implied_volatility", 0.0)

        return StrikeSelection(
            strike=strike,
            option_side=option_side,
            delta=delta,
            mid_price=mid_price,
            bid=bid,
            ask=ask,
            spread=ask - bid,
            distance_from_atm=distance,
            open_interest=oi,
            volume=volume,
            implied_volatility=iv,
            is_strong_signal=is_strong,
        )

    # ================================================================== #
    #  STEP 3 -- Entry Timing                                             #
    # ================================================================== #

    def check_entry_conditions(
        self,
        direction_score: DirectionScore,
        strike: StrikeSelection,
        vix1d: float,
        vix1d_5min_change: float,
        minutes_to_event: int,
        time_zone: str,
    ) -> Tuple[bool, str]:
        """Verify that **all** entry conditions are met simultaneously.

        Conditions (ALL must be true)
        -----------------------------
        1. Direction score exceeds the entry threshold.
        2. A valid strike has been selected and passes liquidity filters.
        3. No major economic event within 15 minutes.
        4. VIX1D not spiking (< 20 % increase in the last 5 min).
        5. ES futures not in a trading halt (implied by valid price data).
        6. Time within the valid scanning window (9:45 AM - 3:00 PM ET).

        Parameters
        ----------
        direction_score : DirectionScore
            Result of :meth:`compute_direction_score`.
        strike : StrikeSelection
            Result of :meth:`select_strike`.
        vix1d : float
            Current VIX1D reading.
        vix1d_5min_change : float
            Percentage change in VIX1D over the last 5 minutes (e.g. 0.15
            means a 15 % increase).
        minutes_to_event : int
            Minutes until the next scheduled macro event. ``-1`` or a
            large value indicates no imminent event.
        time_zone : str
            Current intraday time zone identifier.

        Returns
        -------
        tuple[bool, str]
            ``(can_enter, reason)`` where *reason* describes the first
            failing condition (empty string if all conditions pass).
        """
        # Condition 1 -- Direction score above threshold
        if not direction_score.signal_valid:
            reason = (
                f"Signal invalid: "
                f"{direction_score.invalidation_reason or 'below threshold'}"
            )
            logger.debug("Entry blocked -- %s", reason)
            return False, reason

        if abs(direction_score.composite) < self.entry_threshold:
            reason = (
                f"Composite score {direction_score.composite:.1f} below "
                f"entry threshold {self.entry_threshold:.1f}"
            )
            logger.debug("Entry blocked -- %s", reason)
            return False, reason

        # Condition 2 -- Strike is valid
        if strike is None:
            reason = "No valid strike selected"
            logger.debug("Entry blocked -- %s", reason)
            return False, reason

        strike_price = getattr(strike, "strike", 0.0)
        if strike_price <= 0:
            reason = "Strike price is zero or negative"
            logger.debug("Entry blocked -- %s", reason)
            return False, reason

        # Condition 3 -- No economic event within 15 minutes
        if 0 <= minutes_to_event <= 15:
            reason = (
                f"Economic event in {minutes_to_event} min "
                f"(must be > 15 min away)"
            )
            logger.debug("Entry blocked -- %s", reason)
            return False, reason

        # Condition 4 -- VIX1D not spiking (< 20% increase in 5 min)
        vix1d_spike_limit: float = 0.20
        if vix1d_5min_change >= vix1d_spike_limit:
            reason = (
                f"VIX1D spiking: {vix1d_5min_change:.1%} increase in 5 min "
                f"(limit {vix1d_spike_limit:.0%})"
            )
            logger.debug("Entry blocked -- %s", reason)
            return False, reason

        # Condition 5 -- ES not halted (implied by having valid data;
        #                an explicit halt flag can be added here)

        # Condition 6 -- Within valid scanning window (9:45 AM - 3:00 PM)
        if not self._is_valid_scan_window(time_zone):
            reason = (
                f"Outside valid scan window (9:45 AM - 3:00 PM). "
                f"Current zone: {time_zone}"
            )
            logger.debug("Entry blocked -- %s", reason)
            return False, reason

        logger.info(
            "All entry conditions met  score=%.1f  strike=%.0f  "
            "vix1d=%.1f  mins_to_event=%d  tz=%s",
            direction_score.composite, strike_price,
            vix1d, minutes_to_event, time_zone,
        )
        return True, ""

    @staticmethod
    def _is_valid_scan_window(time_zone: str) -> bool:
        """Return True if the current time zone falls within 9:45 AM - 3:00 PM.

        Valid zones: MORNING_SESSION, MIDDAY_LULL, AFTERNOON_ACCEL.
        Invalid zones: PRE_MARKET, OPENING_AUCTION, POWER_HOUR,
                       SETTLEMENT_WINDOW.
        """
        tz_upper = time_zone.upper() if isinstance(time_zone, str) else ""
        valid_keywords = {"MORNING", "MIDDAY", "LULL", "AFTERNOON", "ACCEL"}
        return any(kw in tz_upper for kw in valid_keywords)

    # ================================================================== #
    #  Signal Generation                                                  #
    # ================================================================== #

    def generate_scan_signal(
        self,
        direction_score: DirectionScore,
        strike: StrikeSelection,
        spx_price: float,
        time_zone: str,
        session_type: SessionType,
        vix1d: float,
        gex_profile: GEXProfile,
    ) -> ScanSignal:
        """Generate a complete scan signal with entry, stop, target, and sizing.

        **Entry**: mid-price of the selected strike.

        **Stop**: 50 % of premium paid.

        **Profit Target**: scaled by time of day:

        * Morning (before 11:00 AM)   : 100 % - 200 % of premium
        * Midday (11:00 AM - 1:30 PM) : 75 % - 150 % of premium
        * Afternoon (1:30 PM - 3:00 PM): 50 % - 100 % of premium

        **Position Type**: ``SINGLE_LONG`` for standard signals,
        ``DEBIT_SPREAD`` when the selected strike is far from ATM.

        **Max Risk**: 2 % of the daily risk budget.

        Parameters
        ----------
        direction_score : DirectionScore
        strike : StrikeSelection
        spx_price : float
        time_zone : str
        session_type : SessionType
        vix1d : float
        gex_profile : GEXProfile

        Returns
        -------
        ScanSignal
            Fully specified trade signal.
        """
        entry_price: float = getattr(strike, "mid_price", 0.0)
        stop_loss: float = entry_price * 0.50  # 50% of premium

        # -- Profit target scaled by time of day ---------------------------
        profit_target_pct = self._profit_target_by_zone(time_zone)
        profit_target: float = entry_price * profit_target_pct

        # -- Position type -------------------------------------------------
        distance = getattr(strike, "distance_from_atm", 0.0)
        if distance > 15.0:
            position_type = PositionType.DEBIT_SPREAD
        else:
            position_type = PositionType.SINGLE_LONG

        # -- Risk sizing: 2% of daily budget (expressed as max loss) -------
        max_risk_pct: float = 0.02

        # -- Net GEX context -----------------------------------------------
        net_gex: float = getattr(gex_profile, "net_gex", 0.0)

        signal = ScanSignal(
            scan_type=ScanType.DIRECTIONAL_OTM,
            direction=direction_score.direction,
            option_side=getattr(strike, "option_side", OptionSide.CALL),
            strike=getattr(strike, "strike", 0.0),
            entry_price=entry_price,
            stop_loss=stop_loss,
            profit_target=profit_target,
            position_type=position_type,
            direction_score=direction_score,
            strike_selection=strike,
            spx_price=spx_price,
            vix1d=vix1d,
            time_zone=time_zone,
            session_type=session_type,
            max_risk_pct=max_risk_pct,
            net_gex=net_gex,
        )

        logger.info(
            "Scan signal generated: %s %s @ %.0f  entry=%.2f  stop=%.2f  "
            "target=%.2f  type=%s  risk=%.0f%%",
            direction_score.direction,
            getattr(strike, "option_side", ""),
            getattr(strike, "strike", 0),
            entry_price, stop_loss, profit_target,
            position_type, max_risk_pct * 100,
        )
        return signal

    @staticmethod
    def _profit_target_by_zone(time_zone: str) -> float:
        """Return the profit target as a multiplier of entry premium.

        Morning   (before 11:00 AM)   : 1.50  (midpoint of 100-200%)
        Midday    (11:00 AM - 1:30 PM): 1.00  (midpoint of 75-150% -- conservative)
        Afternoon (1:30 PM - 3:00 PM) : 0.75  (midpoint of 50-100%)
        Default fallback               : 0.75
        """
        tz_upper = time_zone.upper() if isinstance(time_zone, str) else ""
        if "MORNING" in tz_upper:
            return 1.50
        if "MIDDAY" in tz_upper or "LULL" in tz_upper:
            return 1.00
        if "AFTERNOON" in tz_upper or "ACCEL" in tz_upper:
            return 0.75
        # Conservative default for late-day
        return 0.75

    # ================================================================== #
    #  MAIN METHOD -- scan()                                              #
    # ================================================================== #

    def scan(
        self,
        chain: OptionsChain,
        internals: MarketInternals,
        spx_price: float,
        vwap: float,
        em_upper: float,
        em_lower: float,
        order_book: ESOrderBook,
        gex_profile: GEXProfile,
        cross_data: CrossAssetData,
        prior_spx: float,
        momentum_5min: float,
        vix1d: float,
        vix1d_5min_change: float,
        minutes_to_event: int,
        time_zone: str,
        session_type: SessionType,
        flow_data: Optional[dict] = None,
    ) -> Optional[ScanSignal]:
        """Execute the full directional OTM scan pipeline.

        This is the top-level entry point, designed to be called every
        1 minute between 9:45 AM and 3:00 PM ET.

        Pipeline
        --------
        1. **Direction determination** -- compute the weighted composite
           direction score from all five factors.
        2. **Strike selection** -- if a directional signal is present,
           select the optimal OTM strike.
        3. **Entry condition check** -- verify that all prerequisites
           (event proximity, VIX stability, time window) are satisfied.
        4. **Signal generation** -- package the trade signal with entry,
           stop, target, and position sizing.

        Parameters
        ----------
        chain : OptionsChain
            Current 0DTE SPX options chain.
        internals : MarketInternals
            NYSE breadth / internals snapshot.
        spx_price : float
            Current SPX spot price.
        vwap : float
            Session VWAP.
        em_upper : float
            Upper expected-move boundary.
        em_lower : float
            Lower expected-move boundary.
        order_book : ESOrderBook
            ES futures Level-II order-book snapshot.
        gex_profile : GEXProfile
            Current GEX profile.
        cross_data : CrossAssetData
            Cross-asset data (VIX, VIX1D, yields, DXY).
        prior_spx : float
            SPX price at the prior scan interval.
        momentum_5min : float
            5-minute price momentum.
        vix1d : float
            Current VIX1D reading.
        vix1d_5min_change : float
            VIX1D percentage change over the last 5 minutes.
        minutes_to_event : int
            Minutes until the next scheduled macro event.
        time_zone : str
            Current intraday time zone identifier.
        session_type : SessionType
            Current session classification.
        flow_data : dict, optional
            Supplemental real-time options-flow data.

        Returns
        -------
        ScanSignal or None
            A fully specified trade signal if all conditions are met,
            otherwise ``None``.
        """
        logger.debug(
            "--- Directional OTM scan  spx=%.2f  tz=%s  session=%s ---",
            spx_price, time_zone, session_type,
        )

        # ---- Step 1: Direction Determination ----------------------------
        direction_score: DirectionScore = self.compute_direction_score(
            internals=internals,
            chain=chain,
            spx_price=spx_price,
            vwap=vwap,
            em_upper=em_upper,
            em_lower=em_lower,
            order_book=order_book,
            gex_profile=gex_profile,
            cross_data=cross_data,
            prior_spx=prior_spx,
            momentum_5min=momentum_5min,
            flow_data=flow_data,
        )

        if direction_score.direction == TradeDirection.NEUTRAL:
            logger.debug(
                "No directional signal (composite=%.1f). Scan complete.",
                direction_score.composite,
            )
            return None

        # ---- Step 2: Strike Selection -----------------------------------
        strike: Optional[StrikeSelection] = self.select_strike(
            chain=chain,
            direction=direction_score.direction,
            score_magnitude=abs(direction_score.composite),
            vix1d=vix1d,
            time_zone=time_zone,
            session_type=session_type,
            spx_price=spx_price,
        )

        if strike is None:
            logger.info(
                "Directional signal present (%.1f) but no suitable strike found.",
                direction_score.composite,
            )
            return None

        # ---- Step 3: Entry Condition Check ------------------------------
        can_enter, reason = self.check_entry_conditions(
            direction_score=direction_score,
            strike=strike,
            vix1d=vix1d,
            vix1d_5min_change=vix1d_5min_change,
            minutes_to_event=minutes_to_event,
            time_zone=time_zone,
        )

        if not can_enter:
            logger.info(
                "Entry conditions not met: %s  (score=%.1f, strike=%.0f)",
                reason, direction_score.composite,
                getattr(strike, "strike", 0),
            )
            return None

        # ---- Step 4: Signal Generation ----------------------------------
        signal: ScanSignal = self.generate_scan_signal(
            direction_score=direction_score,
            strike=strike,
            spx_price=spx_price,
            time_zone=time_zone,
            session_type=session_type,
            vix1d=vix1d,
            gex_profile=gex_profile,
        )

        logger.info(
            "SCAN SIGNAL EMITTED: %s %s @ %.0f  entry=%.2f  score=%.1f",
            signal.direction,
            signal.option_side,
            signal.strike,
            signal.entry_price,
            direction_score.composite,
        )
        return signal
