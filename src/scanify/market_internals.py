"""
SCANIFY Market Internals Scoring Engine

Multi-factor market internals scoring system for the SCANIFY 0DTE SPX scanner.
Computes directional bias scores across five categories:

    1. Market Internals  (TICK, TRIN, A/D, up/down volume)
    2. Options Flow       (P/C ratio, premium flow, blocks, sweeps)
    3. Price Action        (VWAP, expected move, ES delta, order book, momentum)
    4. GEX Structure       (net GEX modifier, gamma flip, targets, transition zone)
    5. Cross-Asset         (VIX, VIX1D, yields, DXY)

Individual factor scores are combined via a weighted composite to produce a
final directional signal with confidence gating.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np

from .config import SignalDirection
from .data_feeds import (
    MarketInternalsData,
    FuturesData,
    CrossAssetData,
    VIXData,
    SPXPriceBar,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _clamp(value: float, lo: float, hi: float) -> float:
    """Clamp *value* to the closed interval [lo, hi]."""
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Score dataclasses
# ---------------------------------------------------------------------------

@dataclass
class InternalsScore:
    """Score derived from NYSE/market-breadth internals.

    Each sub-score reflects one breadth indicator.  ``total_score`` is the
    arithmetic sum clamped to [-100, +100].
    """

    tick_score: float = 0.0
    cumulative_tick_score: float = 0.0
    trin_score: float = 0.0
    ad_ratio_score: float = 0.0
    up_down_volume_score: float = 0.0
    total_score: float = 0.0
    details: Dict[str, str] = field(default_factory=dict)


@dataclass
class FlowScore:
    """Score derived from real-time options-flow data.

    ``total_score`` is clamped to [-100, +100].
    """

    put_call_ratio_score: float = 0.0
    premium_flow_score: float = 0.0
    block_trade_score: float = 0.0
    sweep_score: float = 0.0
    total_score: float = 0.0
    details: Dict[str, str] = field(default_factory=dict)


@dataclass
class PriceActionScore:
    """Score derived from SPX / ES price-action signals.

    ``total_score`` is clamped to [-100, +100].
    """

    vwap_score: float = 0.0
    expected_move_score: float = 0.0
    es_delta_score: float = 0.0
    order_book_score: float = 0.0
    momentum_score: float = 0.0
    total_score: float = 0.0
    details: Dict[str, str] = field(default_factory=dict)


@dataclass
class GEXStructuralScore:
    """Score derived from Gamma-Exposure structural analysis.

    ``net_gex_modifier`` is a multiplicative modifier (typically ±20 %) that
    amplifies or dampens the composite signal magnitude.
    ``total_score`` is clamped to [-100, +100].
    """

    net_gex_modifier: float = 0.0
    gamma_flip_score: float = 0.0
    gex_target_score: float = 0.0
    transition_zone_score: float = 0.0
    total_score: float = 0.0
    details: Dict[str, str] = field(default_factory=dict)


@dataclass
class CrossAssetScore:
    """Score derived from cross-asset confirmation signals.

    ``total_score`` is clamped to [-50, +50] — a tighter range because
    cross-asset signals are confirmatory, not primary.
    """

    vix_direction_score: float = 0.0
    vix1d_score: float = 0.0
    yield_score: float = 0.0
    dxy_score: float = 0.0
    total_score: float = 0.0
    details: Dict[str, str] = field(default_factory=dict)


@dataclass
class CompositeDirectionScore:
    """Final composite directional signal produced by the scoring engine.

    Attributes
    ----------
    market_internals : InternalsScore
        Breadth-based component.
    options_flow : FlowScore
        Options-flow component.
    price_action : PriceActionScore
        Price-action component.
    gex_structure : GEXStructuralScore
        GEX-structural component.
    cross_asset : CrossAssetScore
        Cross-asset confirmation component.
    raw_score : float
        Weighted sum **before** the GEX modifier is applied.
    weighted_score : float
        Final score **after** the GEX modifier.
    direction : SignalDirection
        Derived direction (BULLISH / BEARISH / NEUTRAL).
    factors_agreeing : int
        Number of the five factor categories whose sign matches the overall
        direction.
    has_strong_opposition : bool
        True when any single factor exceeds 30 pts against the composite
        direction.
    signal_valid : bool
        True only when the score exceeds the threshold, at least 3 factors
        agree, and there is no strong opposition.
    timestamp : datetime
        UTC timestamp of the computation.
    """

    market_internals: InternalsScore = field(default_factory=InternalsScore)
    options_flow: FlowScore = field(default_factory=FlowScore)
    price_action: PriceActionScore = field(default_factory=PriceActionScore)
    gex_structure: GEXStructuralScore = field(default_factory=GEXStructuralScore)
    cross_asset: CrossAssetScore = field(default_factory=CrossAssetScore)
    raw_score: float = 0.0
    weighted_score: float = 0.0
    direction: SignalDirection = SignalDirection.NEUTRAL
    factors_agreeing: int = 0
    has_strong_opposition: bool = False
    signal_valid: bool = False
    timestamp: datetime = field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------

class MarketInternalsScorer:
    """Multi-factor market-internals scoring engine.

    Maintains rolling history for cumulative calculations and exposes one
    method per scoring category plus a final ``compute_composite_score``
    aggregator.

    Usage
    -----
    >>> scorer = MarketInternalsScorer()
    >>> internals = scorer.score_market_internals(data, tick_history)
    >>> flow = scorer.score_options_flow(...)
    >>> pa = scorer.score_price_action(...)
    >>> gex = scorer.score_gex_structure(...)
    >>> ca = scorer.score_cross_asset(...)
    >>> composite = scorer.compute_composite_score(
    ...     internals, flow, pa, gex, ca, weights
    ... )
    """

    def __init__(self) -> None:
        """Initialise the scorer with empty history buffers."""
        self._tick_history: List[float] = []
        self._cumulative_tick_history: List[float] = []
        self._premium_flow_history: List[float] = []

    # ------------------------------------------------------------------
    # 1. Market internals
    # ------------------------------------------------------------------

    def score_market_internals(
        self,
        data: MarketInternalsData,
        tick_history: List[float],
    ) -> InternalsScore:
        """Score NYSE / market-breadth internals.

        Parameters
        ----------
        data : MarketInternalsData
            Current snapshot of market-internals fields (TICK, TRIN,
            advance/decline counts, up/down volume).
        tick_history : list[float]
            Recent TICK readings used to compute the 10-min average and
            cumulative trend.

        Returns
        -------
        InternalsScore
            Scored internals with ``total_score`` in [-100, +100].

        Scoring rules
        -------------
        * **TICK 10-min avg**:  >+500 → +40, >+300 → +25,
          <-500 → -40, <-300 → -25.
        * **Cumulative TICK**: positive & rising → +15,
          negative & falling → -15.
        * **TRIN**: <0.75 → +15, >2.0 → +10 (contrarian),
          >1.50 → -15.
        * **A/D ratio**: >2:1 → +15, <1:2 → -15.
        * **Up/Down volume**: >3:1 → +15, <1:3 → -15.
        """

        details: Dict[str, str] = {}

        # -- TICK 10-minute average --
        tick_score = 0.0
        if tick_history:
            tick_avg = float(np.mean(tick_history))
            if tick_avg > 500:
                tick_score = 40.0
                details["tick"] = f"TICK 10m avg {tick_avg:+.0f} > +500 → +40"
            elif tick_avg > 300:
                tick_score = 25.0
                details["tick"] = f"TICK 10m avg {tick_avg:+.0f} > +300 → +25"
            elif tick_avg < -500:
                tick_score = -40.0
                details["tick"] = f"TICK 10m avg {tick_avg:+.0f} < -500 → -40"
            elif tick_avg < -300:
                tick_score = -25.0
                details["tick"] = f"TICK 10m avg {tick_avg:+.0f} < -300 → -25"
            else:
                details["tick"] = f"TICK 10m avg {tick_avg:+.0f} — neutral"
        else:
            details["tick"] = "No TICK history available"

        # -- Cumulative TICK --
        cum_tick_score = 0.0
        if len(tick_history) >= 2:
            cum_tick = float(np.cumsum(tick_history)[-1])
            cum_tick_prev = float(np.cumsum(tick_history)[-2])
            rising = cum_tick > cum_tick_prev
            if cum_tick > 0 and rising:
                cum_tick_score = 15.0
                details["cumulative_tick"] = (
                    f"Cumulative TICK {cum_tick:+.0f} positive & rising → +15"
                )
            elif cum_tick < 0 and not rising:
                cum_tick_score = -15.0
                details["cumulative_tick"] = (
                    f"Cumulative TICK {cum_tick:+.0f} negative & falling → -15"
                )
            else:
                details["cumulative_tick"] = (
                    f"Cumulative TICK {cum_tick:+.0f} — neutral"
                )
        else:
            details["cumulative_tick"] = "Insufficient TICK history for cumulative"

        # -- TRIN --
        trin_score = 0.0
        trin = getattr(data, "trin", None)
        if trin is not None:
            if trin > 2.0:
                # Extreme TRIN → contrarian bullish
                trin_score = 10.0
                details["trin"] = f"TRIN {trin:.2f} > 2.00 — contrarian bullish → +10"
            elif trin > 1.50:
                trin_score = -15.0
                details["trin"] = f"TRIN {trin:.2f} > 1.50 — bearish → -15"
            elif trin < 0.75:
                trin_score = 15.0
                details["trin"] = f"TRIN {trin:.2f} < 0.75 — bullish → +15"
            else:
                details["trin"] = f"TRIN {trin:.2f} — neutral"
        else:
            details["trin"] = "TRIN data unavailable"

        # -- Advance / Decline ratio --
        ad_score = 0.0
        advances = getattr(data, "advances", None)
        declines = getattr(data, "declines", None)
        if advances is not None and declines is not None and declines > 0:
            ad_ratio = advances / declines
            if ad_ratio > 2.0:
                ad_score = 15.0
                details["ad_ratio"] = f"A/D ratio {ad_ratio:.2f} > 2:1 → +15"
            elif ad_ratio < 0.5:
                ad_score = -15.0
                details["ad_ratio"] = f"A/D ratio {ad_ratio:.2f} < 1:2 → -15"
            else:
                details["ad_ratio"] = f"A/D ratio {ad_ratio:.2f} — neutral"
        else:
            details["ad_ratio"] = "A/D data unavailable or zero declines"

        # -- Up / Down volume ratio --
        ud_score = 0.0
        up_vol = getattr(data, "up_volume", None)
        down_vol = getattr(data, "down_volume", None)
        if up_vol is not None and down_vol is not None and down_vol > 0:
            ud_ratio = up_vol / down_vol
            if ud_ratio > 3.0:
                ud_score = 15.0
                details["up_down_volume"] = (
                    f"Up/Down vol {ud_ratio:.2f} > 3:1 → +15"
                )
            elif ud_ratio < (1.0 / 3.0):
                ud_score = -15.0
                details["up_down_volume"] = (
                    f"Up/Down vol {ud_ratio:.2f} < 1:3 → -15"
                )
            else:
                details["up_down_volume"] = (
                    f"Up/Down vol {ud_ratio:.2f} — neutral"
                )
        else:
            details["up_down_volume"] = "Up/Down volume data unavailable"

        total = _clamp(
            tick_score + cum_tick_score + trin_score + ad_score + ud_score,
            -100.0,
            100.0,
        )

        return InternalsScore(
            tick_score=tick_score,
            cumulative_tick_score=cum_tick_score,
            trin_score=trin_score,
            ad_ratio_score=ad_score,
            up_down_volume_score=ud_score,
            total_score=total,
            details=details,
        )

    # ------------------------------------------------------------------
    # 2. Options flow
    # ------------------------------------------------------------------

    def score_options_flow(
        self,
        put_call_ratio: float,
        net_premium_flow: float,
        net_block_direction: float,
        sweep_direction: float,
    ) -> FlowScore:
        """Score real-time options-flow signals.

        Parameters
        ----------
        put_call_ratio : float
            Current intraday put/call ratio.
        net_premium_flow : float
            Net premium flow in dollars (positive = call-heavy).
        net_block_direction : float
            Net block-trade direction: +1 bullish, -1 bearish, 0 neutral.
        sweep_direction : float
            Net sweep direction: +1 bullish, -1 bearish, 0 neutral.

        Returns
        -------
        FlowScore
            Scored flow with ``total_score`` in [-100, +100].

        Scoring rules
        -------------
        * P/C < 0.70 → +20 (call-heavy),  P/C > 1.50 → -20.
        * Net premium >+$50M → +25, <-$50M → -25, else proportional.
        * Block direction: ±15.
        * Sweep direction: ±20.
        """

        details: Dict[str, str] = {}

        # -- Put/Call ratio --
        pc_score = 0.0
        if put_call_ratio < 0.70:
            pc_score = 20.0
            details["put_call"] = f"P/C {put_call_ratio:.2f} < 0.70 — call-heavy → +20"
        elif put_call_ratio > 1.50:
            pc_score = -20.0
            details["put_call"] = f"P/C {put_call_ratio:.2f} > 1.50 — put-heavy → -20"
        else:
            details["put_call"] = f"P/C {put_call_ratio:.2f} — neutral"

        # -- Net premium flow --
        premium_threshold = 50_000_000.0  # $50M
        prem_score = 0.0
        if net_premium_flow > premium_threshold:
            prem_score = 25.0
            details["premium_flow"] = (
                f"Net premium ${net_premium_flow / 1e6:+.1f}M > +$50M → +25"
            )
        elif net_premium_flow < -premium_threshold:
            prem_score = -25.0
            details["premium_flow"] = (
                f"Net premium ${net_premium_flow / 1e6:+.1f}M < -$50M → -25"
            )
        else:
            # Proportional scoring between -$50M and +$50M
            prem_score = 25.0 * (net_premium_flow / premium_threshold)
            prem_score = _clamp(prem_score, -25.0, 25.0)
            details["premium_flow"] = (
                f"Net premium ${net_premium_flow / 1e6:+.1f}M → "
                f"proportional {prem_score:+.1f}"
            )

        # -- Block trade direction --
        block_score = _clamp(net_block_direction * 15.0, -15.0, 15.0)
        details["block_trade"] = (
            f"Block direction {net_block_direction:+.2f} → {block_score:+.1f}"
        )

        # -- Sweep direction --
        sweep_score = _clamp(sweep_direction * 20.0, -20.0, 20.0)
        details["sweep"] = (
            f"Sweep direction {sweep_direction:+.2f} → {sweep_score:+.1f}"
        )

        total = _clamp(
            pc_score + prem_score + block_score + sweep_score,
            -100.0,
            100.0,
        )

        return FlowScore(
            put_call_ratio_score=pc_score,
            premium_flow_score=prem_score,
            block_trade_score=block_score,
            sweep_score=sweep_score,
            total_score=total,
            details=details,
        )

    # ------------------------------------------------------------------
    # 3. Price action
    # ------------------------------------------------------------------

    def score_price_action(
        self,
        spx_price: float,
        vwap: float,
        em_upper: float,
        em_lower: float,
        es_cum_delta: float,
        es_cum_delta_rising: bool,
        es_book_imbalance: float,
        momentum_5min: float,
    ) -> PriceActionScore:
        """Score SPX / ES price-action signals.

        Parameters
        ----------
        spx_price : float
            Current SPX price.
        vwap : float
            Session VWAP.
        em_upper : float
            Upper expected-move boundary.
        em_lower : float
            Lower expected-move boundary.
        es_cum_delta : float
            ES cumulative delta (positive = net buying).
        es_cum_delta_rising : bool
            Whether cumulative delta is trending higher.
        es_book_imbalance : float
            Ratio of bid size to ask size in the ES order book.
        momentum_5min : float
            5-minute price momentum (positive = accelerating up,
            negative = accelerating down).  Near zero indicates
            deceleration.

        Returns
        -------
        PriceActionScore
            Scored price action with ``total_score`` in [-100, +100].

        Scoring rules
        -------------
        * Above VWAP & rising: +15.  Below VWAP & falling: -15.
          Crossing VWAP: ±10 in direction of cross.
        * Near upper EM boundary: -10.  Near lower EM: +10.
        * ES delta positive & rising: +15.  Negative & falling: -15.
        * Book imbalance bid > 2x ask: +15.  Ask > 2x bid: -15.
        * Positive acceleration: +10.  Negative acceleration: -10.
          Decelerating (|mom| small): -5.
        """

        details: Dict[str, str] = {}

        # -- VWAP --
        vwap_score = 0.0
        price_vs_vwap = spx_price - vwap
        if price_vs_vwap > 0 and momentum_5min > 0:
            vwap_score = 15.0
            details["vwap"] = (
                f"SPX {spx_price:.2f} above VWAP {vwap:.2f} & rising → +15"
            )
        elif price_vs_vwap < 0 and momentum_5min < 0:
            vwap_score = -15.0
            details["vwap"] = (
                f"SPX {spx_price:.2f} below VWAP {vwap:.2f} & falling → -15"
            )
        elif abs(price_vs_vwap) < 1.0:
            # Crossing / near VWAP — direction determined by momentum
            if momentum_5min > 0:
                vwap_score = 10.0
                details["vwap"] = (
                    f"SPX crossing VWAP {vwap:.2f} upward → +10"
                )
            elif momentum_5min < 0:
                vwap_score = -10.0
                details["vwap"] = (
                    f"SPX crossing VWAP {vwap:.2f} downward → -10"
                )
            else:
                details["vwap"] = f"SPX near VWAP {vwap:.2f} — neutral"
        else:
            details["vwap"] = (
                f"SPX {spx_price:.2f} vs VWAP {vwap:.2f} — neutral"
            )

        # -- Expected Move boundaries --
        em_score = 0.0
        em_range = em_upper - em_lower
        proximity_threshold = 0.05 * em_range if em_range > 0 else 1.0
        if spx_price >= em_upper - proximity_threshold:
            em_score = -10.0
            details["expected_move"] = (
                f"SPX {spx_price:.2f} near upper EM {em_upper:.2f} → -10"
            )
        elif spx_price <= em_lower + proximity_threshold:
            em_score = 10.0
            details["expected_move"] = (
                f"SPX {spx_price:.2f} near lower EM {em_lower:.2f} → +10"
            )
        else:
            details["expected_move"] = (
                f"SPX {spx_price:.2f} within EM [{em_lower:.2f}, {em_upper:.2f}]"
            )

        # -- ES cumulative delta --
        es_score = 0.0
        if es_cum_delta > 0 and es_cum_delta_rising:
            es_score = 15.0
            details["es_delta"] = (
                f"ES cum delta {es_cum_delta:+.0f} positive & rising → +15"
            )
        elif es_cum_delta < 0 and not es_cum_delta_rising:
            es_score = -15.0
            details["es_delta"] = (
                f"ES cum delta {es_cum_delta:+.0f} negative & falling → -15"
            )
        else:
            details["es_delta"] = (
                f"ES cum delta {es_cum_delta:+.0f} — neutral"
            )

        # -- Order book imbalance --
        book_score = 0.0
        if es_book_imbalance > 2.0:
            book_score = 15.0
            details["order_book"] = (
                f"Book imbalance {es_book_imbalance:.2f} bid > 2x ask → +15"
            )
        elif es_book_imbalance < 0.5:
            book_score = -15.0
            details["order_book"] = (
                f"Book imbalance {es_book_imbalance:.2f} ask > 2x bid → -15"
            )
        else:
            details["order_book"] = (
                f"Book imbalance {es_book_imbalance:.2f} — balanced"
            )

        # -- Momentum / acceleration --
        mom_score = 0.0
        decel_threshold = 0.05  # near-zero threshold
        if abs(momentum_5min) < decel_threshold:
            mom_score = -5.0
            details["momentum"] = (
                f"Momentum {momentum_5min:+.4f} decelerating → -5"
            )
        elif momentum_5min > 0:
            mom_score = 10.0
            details["momentum"] = (
                f"Momentum {momentum_5min:+.4f} positive accel → +10"
            )
        else:
            mom_score = -10.0
            details["momentum"] = (
                f"Momentum {momentum_5min:+.4f} negative accel → -10"
            )

        total = _clamp(
            vwap_score + em_score + es_score + book_score + mom_score,
            -100.0,
            100.0,
        )

        return PriceActionScore(
            vwap_score=vwap_score,
            expected_move_score=em_score,
            es_delta_score=es_score,
            order_book_score=book_score,
            momentum_score=mom_score,
            total_score=total,
            details=details,
        )

    # ------------------------------------------------------------------
    # 4. GEX structure
    # ------------------------------------------------------------------

    def score_gex_structure(
        self,
        net_gex_positive: bool,
        above_gamma_flip: bool,
        moving_toward_plus_gex: bool,
        in_transition_zone: bool,
        breaking_above_tz: bool,
        breaking_below_tz: bool,
    ) -> GEXStructuralScore:
        """Score Gamma-Exposure structural conditions.

        Parameters
        ----------
        net_gex_positive : bool
            True when aggregate dealer gamma exposure is positive (mean-
            reverting regime).
        above_gamma_flip : bool
            True when SPX is above the gamma-flip level.
        moving_toward_plus_gex : bool
            True when SPX is moving toward positive-gamma territory.
        in_transition_zone : bool
            True when SPX sits inside the gamma transition zone.
        breaking_above_tz : bool
            True when SPX is breaking above the transition zone.
        breaking_below_tz : bool
            True when SPX is breaking below the transition zone.

        Returns
        -------
        GEXStructuralScore
            Scored GEX structure with ``total_score`` in [-100, +100].

        Scoring rules
        -------------
        * **Net GEX modifier**: positive → reduces signal magnitude by
          20 %, negative → increases by 20 %.
        * Above gamma flip: +20, below: -20.
        * Moving toward +GEX: +15, toward -GEX: -15.
        * In transition zone: 0.  Breaking above: +25, below: -25.
        """

        details: Dict[str, str] = {}

        # -- Net GEX modifier (±20 %) --
        if net_gex_positive:
            gex_mod = -0.20  # dampen magnitude (mean-reversion environment)
            details["net_gex"] = (
                "Net GEX positive — magnitude dampened by 20 %"
            )
        else:
            gex_mod = 0.20  # amplify magnitude (trending environment)
            details["net_gex"] = (
                "Net GEX negative — magnitude amplified by 20 %"
            )

        # -- Gamma flip level --
        flip_score = 0.0
        if above_gamma_flip:
            flip_score = 20.0
            details["gamma_flip"] = "Above gamma flip → +20"
        else:
            flip_score = -20.0
            details["gamma_flip"] = "Below gamma flip → -20"

        # -- GEX target (movement toward positive/negative gamma) --
        target_score = 0.0
        if moving_toward_plus_gex:
            target_score = 15.0
            details["gex_target"] = "Moving toward +GEX → +15"
        else:
            target_score = -15.0
            details["gex_target"] = "Moving toward -GEX → -15"

        # -- Transition zone --
        tz_score = 0.0
        if in_transition_zone:
            if breaking_above_tz:
                tz_score = 25.0
                details["transition_zone"] = (
                    "In TZ, breaking above → +25"
                )
            elif breaking_below_tz:
                tz_score = -25.0
                details["transition_zone"] = (
                    "In TZ, breaking below → -25"
                )
            else:
                tz_score = 0.0
                details["transition_zone"] = "In transition zone — neutral"
        else:
            if breaking_above_tz:
                tz_score = 25.0
                details["transition_zone"] = "Breaking above TZ → +25"
            elif breaking_below_tz:
                tz_score = -25.0
                details["transition_zone"] = "Breaking below TZ → -25"
            else:
                details["transition_zone"] = "Outside TZ — no signal"

        total = _clamp(
            flip_score + target_score + tz_score,
            -100.0,
            100.0,
        )

        return GEXStructuralScore(
            net_gex_modifier=gex_mod,
            gamma_flip_score=flip_score,
            gex_target_score=target_score,
            transition_zone_score=tz_score,
            total_score=total,
            details=details,
        )

    # ------------------------------------------------------------------
    # 5. Cross-asset
    # ------------------------------------------------------------------

    def score_cross_asset(
        self,
        vix_falling: bool,
        spx_rising: bool,
        vix1d_vs_avg: float,
        yield_falling: bool,
        yield_rising_sharply: bool,
        dxy_falling: bool,
        dxy_rising_sharply: bool,
    ) -> CrossAssetScore:
        """Score cross-asset confirmation signals.

        Parameters
        ----------
        vix_falling : bool
            True when VIX is trending lower.
        spx_rising : bool
            True when SPX is trending higher.
        vix1d_vs_avg : float
            VIX1D relative to its recent average: negative means below
            average, positive means above average.
        yield_falling : bool
            True when Treasury yields are falling.
        yield_rising_sharply : bool
            True when yields are rising sharply (risk-off move).
        dxy_falling : bool
            True when the dollar index is falling.
        dxy_rising_sharply : bool
            True when DXY is rising sharply (risk-off move).

        Returns
        -------
        CrossAssetScore
            Scored cross-asset signals with ``total_score`` in [-50, +50].

        Scoring rules
        -------------
        * VIX falling + SPX rising: +15.  VIX rising + SPX falling: -15.
        * VIX rising + SPX rising (divergence): -10.
          VIX falling + SPX falling (divergence): +10.
        * VIX1D below avg: +10, above avg: -10.
        * Yields falling + SPX rising: +10.  Rising sharply: -10.
        * DXY falling: +5.  Rising sharply: -5.
        """

        details: Dict[str, str] = {}

        # -- VIX vs SPX interplay --
        vix_score = 0.0
        vix_rising = not vix_falling
        spx_falling = not spx_rising

        if vix_falling and spx_rising:
            vix_score = 15.0
            details["vix_direction"] = "VIX falling + SPX rising → +15"
        elif vix_rising and spx_falling:
            vix_score = -15.0
            details["vix_direction"] = "VIX rising + SPX falling → -15"
        elif vix_rising and spx_rising:
            vix_score = -10.0
            details["vix_direction"] = (
                "VIX rising + SPX rising (divergence) → -10"
            )
        elif vix_falling and spx_falling:
            vix_score = 10.0
            details["vix_direction"] = (
                "VIX falling + SPX falling (divergence) → +10"
            )

        # -- VIX1D vs average --
        vix1d_score = 0.0
        if vix1d_vs_avg < 0:
            vix1d_score = 10.0
            details["vix1d"] = (
                f"VIX1D {vix1d_vs_avg:+.2f} below avg → +10"
            )
        elif vix1d_vs_avg > 0:
            vix1d_score = -10.0
            details["vix1d"] = (
                f"VIX1D {vix1d_vs_avg:+.2f} above avg → -10"
            )
        else:
            details["vix1d"] = "VIX1D at avg — neutral"

        # -- Yields --
        yld_score = 0.0
        if yield_rising_sharply:
            yld_score = -10.0
            details["yield"] = "Yields rising sharply → -10"
        elif yield_falling and spx_rising:
            yld_score = 10.0
            details["yield"] = "Yields falling + SPX rising → +10"
        else:
            details["yield"] = "Yield conditions — neutral"

        # -- DXY --
        dxy_score = 0.0
        if dxy_rising_sharply:
            dxy_score = -5.0
            details["dxy"] = "DXY rising sharply → -5"
        elif dxy_falling:
            dxy_score = 5.0
            details["dxy"] = "DXY falling → +5"
        else:
            details["dxy"] = "DXY — neutral"

        total = _clamp(
            vix_score + vix1d_score + yld_score + dxy_score,
            -50.0,
            50.0,
        )

        return CrossAssetScore(
            vix_direction_score=vix_score,
            vix1d_score=vix1d_score,
            yield_score=yld_score,
            dxy_score=dxy_score,
            total_score=total,
            details=details,
        )

    # ------------------------------------------------------------------
    # 6. Composite
    # ------------------------------------------------------------------

    def compute_composite_score(
        self,
        internals: InternalsScore,
        flow: FlowScore,
        price_action: PriceActionScore,
        gex: GEXStructuralScore,
        cross_asset: CrossAssetScore,
        weights: Optional[Dict[str, float]] = None,
        signal_threshold: float = 40.0,
        min_factors_agreeing: int = 3,
        max_opposing_factor_score: float = 30.0,
    ) -> CompositeDirectionScore:
        """Compute the final weighted composite directional score.

        Parameters
        ----------
        internals : InternalsScore
            Market-breadth scoring result.
        flow : FlowScore
            Options-flow scoring result.
        price_action : PriceActionScore
            Price-action scoring result.
        gex : GEXStructuralScore
            GEX-structural scoring result.
        cross_asset : CrossAssetScore
            Cross-asset scoring result.
        weights : dict[str, float] | None
            Optional override for factor weights.  Expected keys:
            ``"market_internals"``, ``"options_flow"``,
            ``"price_action"``, ``"gex_structure"``,
            ``"cross_asset"``.  Values must sum to 1.0.  When *None*,
            the default SCANIFY weights are used (0.30 / 0.25 / 0.20 /
            0.15 / 0.10).
        signal_threshold : float
            Minimum absolute composite score to consider the signal
            actionable (default 40).
        min_factors_agreeing : int
            Minimum number of factor categories whose sign must match
            the composite direction (default 3).
        max_opposing_factor_score : float
            If any single factor's absolute score exceeds this value
            **against** the composite direction, the signal is flagged
            as having strong opposition (default 30).

        Returns
        -------
        CompositeDirectionScore
            Final composite signal with validity gating.

        Algorithm
        ---------
        1. Weighted average of all five factor ``total_score`` values.
        2. Count how many factors agree on direction.
        3. Check for strong opposition (any factor > 30 pts counter to
           the composite direction).
        4. Apply GEX modifier to the magnitude:
           ``weighted_score = raw_score * (1 + gex.net_gex_modifier)``
        5. Signal is valid only when:
           a. ``|weighted_score| >= signal_threshold``
           b. ``factors_agreeing >= min_factors_agreeing``
           c. ``has_strong_opposition is False``
        """

        if weights is None:
            weights = {
                "market_internals": 0.30,
                "options_flow": 0.25,
                "price_action": 0.20,
                "gex_structure": 0.15,
                "cross_asset": 0.10,
            }

        # -- Weighted raw score --
        factor_scores = {
            "market_internals": internals.total_score,
            "options_flow": flow.total_score,
            "price_action": price_action.total_score,
            "gex_structure": gex.total_score,
            "cross_asset": cross_asset.total_score,
        }

        raw_score = sum(
            factor_scores[k] * weights.get(k, 0.0)
            for k in factor_scores
        )

        # -- Apply GEX modifier --
        weighted_score = raw_score * (1.0 + gex.net_gex_modifier)

        # -- Direction --
        if weighted_score > 0:
            direction = SignalDirection.BULLISH
        elif weighted_score < 0:
            direction = SignalDirection.BEARISH
        else:
            direction = SignalDirection.NEUTRAL

        # -- Count factors agreeing on direction --
        direction_sign = (
            1.0 if direction == SignalDirection.BULLISH
            else (-1.0 if direction == SignalDirection.BEARISH else 0.0)
        )
        factors_agreeing = 0
        has_strong_opposition = False

        for name, score in factor_scores.items():
            if direction_sign == 0.0:
                # NEUTRAL — no factor can "agree"
                continue
            if np.sign(score) == direction_sign:
                factors_agreeing += 1
            # Check for strong opposition
            if np.sign(score) == -direction_sign and abs(score) > max_opposing_factor_score:
                has_strong_opposition = True

        # -- Validity gate --
        signal_valid = (
            abs(weighted_score) >= signal_threshold
            and factors_agreeing >= min_factors_agreeing
            and not has_strong_opposition
        )

        return CompositeDirectionScore(
            market_internals=internals,
            options_flow=flow,
            price_action=price_action,
            gex_structure=gex,
            cross_asset=cross_asset,
            raw_score=round(raw_score, 4),
            weighted_score=round(weighted_score, 4),
            direction=direction,
            factors_agreeing=factors_agreeing,
            has_strong_opposition=has_strong_opposition,
            signal_valid=signal_valid,
            timestamp=datetime.utcnow(),
        )
