"""
SCANIFY Equity Internals API — Market breadth scoring and direction signals.

Endpoints:
    GET  /api/equity/internals/direction    Composite 5-factor direction score
    GET  /api/equity/internals/breadth      Market breadth indicators (TICK, TRIN, A/D)
    GET  /api/equity/internals/flow         Options flow scoring (P/C ratio, sweeps, blocks)
    GET  /api/equity/internals/session      Session classification and setup
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/equity/internals", tags=["equity-internals"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class FactorScore(BaseModel):
    name: str
    score: float
    weight: float
    weighted_contribution: float
    details: Dict[str, str]

class DirectionResponse(BaseModel):
    direction: str
    raw_score: float
    weighted_score: float
    signal_valid: bool
    factors_agreeing: int
    has_strong_opposition: bool
    factors: List[FactorScore]

class BreadthResponse(BaseModel):
    tick_10min_avg: float
    cumulative_tick: float
    trin: float
    ad_ratio: float
    up_down_volume_ratio: float
    interpretation: str
    score: float

class FlowResponse(BaseModel):
    put_call_ratio: float
    put_call_score: float
    premium_flow_score: float
    block_trade_score: float
    sweep_score: float
    total_score: float
    interpretation: str

class SessionInfoResponse(BaseModel):
    session_type: str
    description: str
    scanners_active: List[str]
    vol_regime: str
    vol_regime_description: str
    premium_sell_favorable: bool
    directional_favorable: bool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/direction", response_model=DirectionResponse)
async def direction_score(
    request: Request,
    tick_avg: float = Query(0.0, description="NYSE TICK 10-min average"),
    trin: float = Query(1.0, description="TRIN / Arms Index"),
    ad_ratio: float = Query(1.0, description="Advance / Decline ratio"),
    up_volume: float = Query(1e9),
    down_volume: float = Query(1e9),
    put_call_ratio: float = Query(1.0),
    net_premium_flow: float = Query(0.0, description="Net premium in dollars"),
    block_direction: float = Query(0.0, description="+1 bullish, -1 bearish"),
    sweep_direction: float = Query(0.0, description="+1 bullish, -1 bearish"),
):
    """Composite 5-factor directional score.

    Accepts market internals and options flow data as query params and
    returns the weighted composite score with per-factor breakdown.
    GEX structure and cross-asset factors use live data from Yahoo Finance.
    """
    scorer = request.app.state.internals_scorer
    yahoo = request.app.state.yahoo
    engine = request.app.state.gex_engine

    from ..data_feeds import MarketInternalsData
    from datetime import datetime, timezone

    internals_data = MarketInternalsData(
        tick=tick_avg,
        trin=trin,
        ad_ratio=ad_ratio,
        up_volume=up_volume,
        down_volume=down_volume,
        cumulative_delta=0.0,
        timestamp=datetime.now(timezone.utc),
    )

    tick_history = [tick_avg] * 10

    int_score = scorer.score_market_internals(internals_data, tick_history)
    flow_score = scorer.score_options_flow(
        put_call_ratio, net_premium_flow, block_direction, sweep_direction
    )

    try:
        chain = yahoo.fetch_spx_options_chain()
        spot = chain.underlying_price
        vix_data = yahoo.fetch_vix_data()
        gex = engine.compute_gex(chain, spot)
        cross = yahoo.fetch_cross_asset_data()
    except Exception:
        spot = 0.0
        gex = None
        vix_data = None
        cross = None

    gex_score = None
    if gex is not None:
        tz_lo, tz_hi = gex.transition_zone
        gex_score = scorer.score_gex_structure(
            net_gex_positive=gex.total_net_gex >= 0,
            above_gamma_flip=spot > gex.gamma_flip_level > 0,
            moving_toward_plus_gex=spot < gex.plus_gex_strike if gex.plus_gex_strike > 0 else False,
            in_transition_zone=tz_lo <= spot <= tz_hi if tz_lo > 0 and tz_hi > 0 else False,
            breaking_above_tz=spot > tz_hi if tz_hi > 0 else False,
            breaking_below_tz=spot < tz_lo if tz_lo > 0 else False,
        )

    cross_score = None
    if vix_data is not None and cross is not None:
        cross_score = scorer.score_cross_asset(
            vix_falling=False,
            spx_rising=True,
            vix1d_vs_avg=0.0,
            yield_falling=cross.us_10y_yield_change < -0.02,
            yield_rising_sharply=cross.us_10y_yield_change > 0.10,
            dxy_falling=cross.dxy_change < -0.2,
            dxy_rising_sharply=cross.dxy_change > 0.5,
        )

    weights = {
        "market_internals": 0.30,
        "options_flow": 0.25,
        "price_action": 0.20,
        "gex_structure": 0.15,
        "cross_asset": 0.10,
    }

    raw = (
        int_score.total_score * weights["market_internals"]
        + flow_score.total_score * weights["options_flow"]
        + (gex_score.total_score if gex_score else 0.0) * weights["gex_structure"]
        + (cross_score.total_score if cross_score else 0.0) * weights["cross_asset"]
    )

    direction = "neutral"
    if raw >= 40:
        direction = "bullish"
    elif raw <= -40:
        direction = "bearish"

    factors = [
        FactorScore(
            name="Market Internals",
            score=int_score.total_score,
            weight=weights["market_internals"],
            weighted_contribution=round(int_score.total_score * weights["market_internals"], 2),
            details=int_score.details,
        ),
        FactorScore(
            name="Options Flow",
            score=flow_score.total_score,
            weight=weights["options_flow"],
            weighted_contribution=round(flow_score.total_score * weights["options_flow"], 2),
            details=flow_score.details,
        ),
    ]

    if gex_score:
        factors.append(FactorScore(
            name="GEX Structure",
            score=gex_score.total_score,
            weight=weights["gex_structure"],
            weighted_contribution=round(gex_score.total_score * weights["gex_structure"], 2),
            details=gex_score.details,
        ))
    if cross_score:
        factors.append(FactorScore(
            name="Cross-Asset",
            score=cross_score.total_score,
            weight=weights["cross_asset"],
            weighted_contribution=round(cross_score.total_score * weights["cross_asset"], 2),
            details=cross_score.details,
        ))

    agreeing = sum(1 for f in factors if (f.score > 0) == (raw > 0) and f.score != 0)
    opposition = any(
        abs(f.score) > 30 and (f.score > 0) != (raw > 0)
        for f in factors
    )

    return DirectionResponse(
        direction=direction,
        raw_score=round(raw, 2),
        weighted_score=round(raw, 2),
        signal_valid=abs(raw) >= 40 and agreeing >= 3 and not opposition,
        factors_agreeing=agreeing,
        has_strong_opposition=opposition,
        factors=factors,
    )


@router.get("/breadth", response_model=BreadthResponse)
async def market_breadth(
    request: Request,
    tick_avg: float = Query(0.0),
    trin: float = Query(1.0),
    ad_ratio: float = Query(1.0),
    up_volume: float = Query(1e9),
    down_volume: float = Query(1e9),
):
    """Score NYSE market breadth indicators."""
    scorer = request.app.state.internals_scorer
    from ..data_feeds import MarketInternalsData
    from datetime import datetime, timezone

    data = MarketInternalsData(
        tick=tick_avg, trin=trin, ad_ratio=ad_ratio,
        up_volume=up_volume, down_volume=down_volume,
        cumulative_delta=0.0, timestamp=datetime.now(timezone.utc),
    )
    result = scorer.score_market_internals(data, [tick_avg] * 10)

    ud_ratio = up_volume / max(down_volume, 1)
    if result.total_score > 25:
        interp = "Bullish breadth — broad-based buying"
    elif result.total_score < -25:
        interp = "Bearish breadth — broad-based selling"
    else:
        interp = "Neutral breadth — mixed signals"

    return BreadthResponse(
        tick_10min_avg=tick_avg,
        cumulative_tick=tick_avg * 10,
        trin=trin,
        ad_ratio=ad_ratio,
        up_down_volume_ratio=round(ud_ratio, 4),
        interpretation=interp,
        score=result.total_score,
    )


@router.get("/flow", response_model=FlowResponse)
async def options_flow(
    request: Request,
    put_call_ratio: float = Query(1.0),
    net_premium_flow: float = Query(0.0),
    block_direction: float = Query(0.0),
    sweep_direction: float = Query(0.0),
):
    """Score real-time options flow data."""
    scorer = request.app.state.internals_scorer
    result = scorer.score_options_flow(
        put_call_ratio, net_premium_flow, block_direction, sweep_direction
    )

    if result.total_score > 20:
        interp = "Bullish flow — call-dominant activity"
    elif result.total_score < -20:
        interp = "Bearish flow — put-dominant activity"
    else:
        interp = "Neutral flow — balanced options activity"

    return FlowResponse(
        put_call_ratio=put_call_ratio,
        put_call_score=result.put_call_ratio_score,
        premium_flow_score=result.premium_flow_score,
        block_trade_score=result.block_trade_score,
        sweep_score=result.sweep_score,
        total_score=result.total_score,
        interpretation=interp,
    )


@router.get("/session", response_model=SessionInfoResponse)
async def session_info(request: Request):
    """Session classification and vol regime assessment."""
    yahoo = request.app.state.yahoo
    analyzer = request.app.state.vix1d_analyzer

    try:
        vix_data = yahoo.fetch_vix_data()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"VIX fetch failed: {exc}")

    regime = analyzer.assess_vol_regime(vix_data.vix1d)

    scanners = []
    if regime["directional_favorable"]:
        scanners.append("directional")
    if regime["premium_sell_favorable"]:
        scanners.append("premium_sell")
    scanners.append("gamma_scalp")

    if vix_data.vix1d < 14:
        session_type = "range"
        description = "Low vol range-bound session expected"
    elif vix_data.vix1d < 22:
        session_type = "trending"
        description = "Normal vol — all strategies viable"
    elif vix_data.vix1d < 30:
        session_type = "volatile"
        description = "Elevated vol — wider moves expected"
    else:
        session_type = "event"
        description = "High vol event-driven session"

    return SessionInfoResponse(
        session_type=session_type,
        description=description,
        scanners_active=scanners,
        vol_regime=regime["regime"],
        vol_regime_description=regime["description"],
        premium_sell_favorable=regime["premium_sell_favorable"],
        directional_favorable=regime["directional_favorable"],
    )
