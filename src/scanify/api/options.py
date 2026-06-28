"""
SCANIFY Options API — GEX computation, signals, chain analytics, expected move.

Endpoints:
    GET  /api/options/gex              Full GEX surface computation
    GET  /api/options/gex/levels       Key GEX levels only (call wall, put wall, etc.)
    GET  /api/options/gex/signals      Detect active GEX signals
    GET  /api/options/gex/dealer       Dealer positioning summary
    GET  /api/options/chain            Raw options chain data
    GET  /api/options/chain/summary    Chain statistics (OI distribution, vol skew)
    GET  /api/options/expected-move    Blended expected move envelope
    GET  /api/options/greeks/{strike}  Per-strike Greeks (delta, gamma, charm, vanna, speed)
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/options", tags=["options"])


def _get_options_adapter(request: Request):
    """Return Schwab adapter if configured with tokens, else Yahoo."""
    schwab = getattr(request.app.state, "schwab", None)
    if schwab and schwab.is_configured and schwab.has_refresh_token:
        return schwab
    return request.app.state.yahoo


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class GEXLevel(BaseModel):
    name: str
    strike: float
    distance_from_spot: float
    gex_value: float
    role: str

class GEXLevelsResponse(BaseModel):
    spot: float
    timestamp: str
    call_wall: float
    put_wall: float
    gamma_flip: float
    max_pain: float
    vol_trigger: float
    plus_gex_strike: float
    minus_gex_strike: float
    transition_zone: List[float]
    dealer_position: str
    levels: List[GEXLevel]

class GEXFullResponse(BaseModel):
    spot: float
    timestamp: str
    total_net_gex: float
    dealer_position: str
    gamma_flip: float
    call_wall: float
    put_wall: float
    max_pain: float
    vol_trigger: float
    plus_gex_strike: float
    minus_gex_strike: float
    transition_zone: List[float]
    net_charm_exposure: float
    charm_direction: str
    net_vanna_exposure: float
    gex_by_strike: Dict[str, float]
    call_gex_by_strike: Dict[str, float]
    put_gex_by_strike: Dict[str, float]
    speed_by_strike: Dict[str, float]
    high_speed_strikes: List[float]

class GEXSignalResponse(BaseModel):
    signal_type: str
    direction: str
    confidence: float
    trigger_price: float
    target_price: Optional[float]
    description: str

class DealerResponse(BaseModel):
    spot: float
    dealer_position: str
    total_net_gex: float
    market_effect: str
    implication: str
    net_charm_es_contracts: float
    charm_direction: str
    net_vanna_exposure: float
    gamma_landmines: List[float]

class ChainQuoteResponse(BaseModel):
    strike: float
    option_type: str
    bid: float
    ask: float
    mid: float
    last: float
    volume: int
    open_interest: int
    implied_vol: float
    delta: float
    gamma: float
    theta: float

class ChainSummaryResponse(BaseModel):
    spot: float
    expiry: str
    total_quotes: int
    total_call_oi: int
    total_put_oi: int
    put_call_oi_ratio: float
    total_call_volume: int
    total_put_volume: int
    put_call_volume_ratio: float
    max_call_oi_strike: float
    max_put_oi_strike: float
    atm_iv_call: Optional[float]
    atm_iv_put: Optional[float]
    iv_skew_25d: Optional[float]

class ExpectedMoveResponse(BaseModel):
    spot: float
    vix1d: float
    method1_vix1d: float
    method2_straddle: float
    method3_rv_adjusted: float
    blended_em: float
    upper_1sigma: float
    lower_1sigma: float
    upper_2sigma: float
    lower_2sigma: float
    iv_rv_ratio: float
    vol_regime: str

class StrikeGreeksResponse(BaseModel):
    strike: float
    spot: float
    time_to_expiry: float
    delta_call: float
    delta_put: float
    gamma: float
    theta: float
    charm: float
    vanna: float
    speed: float


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/gex", response_model=GEXFullResponse)
async def compute_gex(request: Request, expiry: Optional[str] = Query(None)):
    """Full GEX surface computation across the entire options chain."""
    adapter = _get_options_adapter(request)
    engine = request.app.state.gex_engine

    try:
        chain = adapter.fetch_spx_options_chain(expiry_date=expiry)
        spot = chain.underlying_price
        gex = engine.compute_gex(chain, spot)
        high_speed = engine.get_high_speed_strikes(gex, spot)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Data fetch failed: {exc}")

    return GEXFullResponse(
        spot=spot,
        timestamp=gex.timestamp.isoformat(),
        total_net_gex=gex.total_net_gex,
        dealer_position=gex.dealer_position,
        gamma_flip=gex.gamma_flip_level,
        call_wall=gex.call_wall,
        put_wall=gex.put_wall,
        max_pain=gex.max_pain,
        vol_trigger=gex.vol_trigger,
        plus_gex_strike=gex.plus_gex_strike,
        minus_gex_strike=gex.minus_gex_strike,
        transition_zone=list(gex.transition_zone),
        net_charm_exposure=gex.net_charm_exposure,
        charm_direction=gex.charm_direction.value,
        net_vanna_exposure=gex.net_vanna_exposure,
        gex_by_strike={str(k): v for k, v in gex.gex_by_strike.items()},
        call_gex_by_strike={str(k): v for k, v in gex.call_gex_by_strike.items()},
        put_gex_by_strike={str(k): v for k, v in gex.put_gex_by_strike.items()},
        speed_by_strike={str(k): v for k, v in gex.net_speed_by_strike.items()},
        high_speed_strikes=high_speed,
    )


@router.get("/gex/levels", response_model=GEXLevelsResponse)
async def gex_levels(request: Request, expiry: Optional[str] = Query(None)):
    """Key GEX levels: call wall, put wall, gamma flip, max pain, vol trigger."""
    adapter = _get_options_adapter(request)
    engine = request.app.state.gex_engine

    try:
        chain = adapter.fetch_spx_options_chain(expiry_date=expiry)
        spot = chain.underlying_price
        gex = engine.compute_gex(chain, spot)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Data fetch failed: {exc}")

    levels = []
    level_defs = [
        ("Call Wall", gex.call_wall, "Resistance — dealers sell to hedge"),
        ("Put Wall", gex.put_wall, "Support — dealers buy to hedge"),
        ("Gamma Flip", gex.gamma_flip_level, "Dealer gamma sign change"),
        ("Max Pain", gex.max_pain, "Pin magnet — max OI expires worthless"),
        ("Vol Trigger", gex.vol_trigger, "Volatility regime boundary"),
        ("+GEX Target", gex.plus_gex_strike, "Max positive gamma above spot"),
        ("-GEX Target", gex.minus_gex_strike, "Max negative gamma below spot"),
    ]
    for name, strike, role in level_defs:
        if strike > 0:
            levels.append(GEXLevel(
                name=name,
                strike=strike,
                distance_from_spot=round(strike - spot, 2),
                gex_value=gex.gex_by_strike.get(strike, 0.0),
                role=role,
            ))

    levels.sort(key=lambda lv: lv.strike, reverse=True)

    return GEXLevelsResponse(
        spot=spot,
        timestamp=gex.timestamp.isoformat(),
        call_wall=gex.call_wall,
        put_wall=gex.put_wall,
        gamma_flip=gex.gamma_flip_level,
        max_pain=gex.max_pain,
        vol_trigger=gex.vol_trigger,
        plus_gex_strike=gex.plus_gex_strike,
        minus_gex_strike=gex.minus_gex_strike,
        transition_zone=list(gex.transition_zone),
        dealer_position=gex.dealer_position,
        levels=levels,
    )


@router.get("/gex/signals", response_model=List[GEXSignalResponse])
async def gex_signals(request: Request, expiry: Optional[str] = Query(None)):
    """Detect active GEX signals (gamma flip, wall approach, collapse, etc.)."""
    adapter = _get_options_adapter(request)
    engine = request.app.state.gex_engine

    try:
        chain = adapter.fetch_spx_options_chain(expiry_date=expiry)
        spot = chain.underlying_price
        vix_data = adapter.fetch_vix_data()
        gex = engine.compute_gex(chain, spot)
        signals = engine.detect_signals(gex, None, spot, vix1d=vix_data.vix1d)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Data fetch failed: {exc}")

    return [
        GEXSignalResponse(
            signal_type=s.signal_type.value,
            direction=s.direction.value,
            confidence=round(s.confidence, 4),
            trigger_price=s.trigger_price,
            target_price=s.target_price,
            description=s.description,
        )
        for s in signals
    ]


@router.get("/gex/dealer", response_model=DealerResponse)
async def dealer_positioning(request: Request, expiry: Optional[str] = Query(None)):
    """Dealer positioning summary with charm, vanna, and gamma landmines."""
    adapter = _get_options_adapter(request)
    engine = request.app.state.gex_engine

    try:
        chain = adapter.fetch_spx_options_chain(expiry_date=expiry)
        spot = chain.underlying_price
        gex = engine.compute_gex(chain, spot)
        high_speed = engine.get_high_speed_strikes(gex, spot)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Data fetch failed: {exc}")

    is_long = gex.dealer_position == "long_gamma"

    return DealerResponse(
        spot=spot,
        dealer_position=gex.dealer_position,
        total_net_gex=gex.total_net_gex,
        market_effect="Dampening (stabilizing)" if is_long else "Amplifying (destabilizing)",
        implication="Dealers BUY dips, SELL rips — range-bound likely" if is_long
                    else "Dealers SELL dips, BUY rips — breakout/trend likely",
        net_charm_es_contracts=gex.net_charm_exposure,
        charm_direction=gex.charm_direction.value,
        net_vanna_exposure=gex.net_vanna_exposure,
        gamma_landmines=high_speed,
    )


@router.get("/chain", response_model=List[ChainQuoteResponse])
async def options_chain(
    request: Request,
    expiry: Optional[str] = Query(None),
    option_type: Optional[str] = Query(None, pattern="^(call|put)$"),
    min_strike: Optional[float] = Query(None),
    max_strike: Optional[float] = Query(None),
    min_oi: int = Query(0),
):
    """Raw options chain data with optional filters."""
    adapter = _get_options_adapter(request)

    try:
        chain = adapter.fetch_spx_options_chain(expiry_date=expiry)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Data fetch failed: {exc}")

    quotes = chain.quotes
    if option_type:
        quotes = [q for q in quotes if q.option_type.value == option_type]
    if min_strike is not None:
        quotes = [q for q in quotes if q.strike >= min_strike]
    if max_strike is not None:
        quotes = [q for q in quotes if q.strike <= max_strike]
    if min_oi > 0:
        quotes = [q for q in quotes if q.open_interest >= min_oi]

    return [
        ChainQuoteResponse(
            strike=q.strike,
            option_type=q.option_type.value,
            bid=q.bid,
            ask=q.ask,
            mid=q.mid,
            last=q.last,
            volume=q.volume,
            open_interest=q.open_interest,
            implied_vol=q.implied_vol,
            delta=q.delta,
            gamma=q.gamma,
            theta=q.theta,
        )
        for q in quotes
    ]


@router.get("/chain/summary", response_model=ChainSummaryResponse)
async def chain_summary(request: Request, expiry: Optional[str] = Query(None)):
    """Chain statistics: OI distribution, volume ratios, IV skew."""
    adapter = _get_options_adapter(request)

    try:
        chain = adapter.fetch_spx_options_chain(expiry_date=expiry)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Data fetch failed: {exc}")

    spot = chain.underlying_price
    calls = [q for q in chain.quotes if q.option_type.value == "call"]
    puts = [q for q in chain.quotes if q.option_type.value == "put"]

    total_call_oi = sum(q.open_interest for q in calls)
    total_put_oi = sum(q.open_interest for q in puts)
    total_call_vol = sum(q.volume for q in calls)
    total_put_vol = sum(q.volume for q in puts)

    max_call_oi_strike = max(calls, key=lambda q: q.open_interest).strike if calls else 0.0
    max_put_oi_strike = max(puts, key=lambda q: q.open_interest).strike if puts else 0.0

    atm_call = min(calls, key=lambda q: abs(q.strike - spot), default=None)
    atm_put = min(puts, key=lambda q: abs(q.strike - spot), default=None)

    return ChainSummaryResponse(
        spot=spot,
        expiry=str(chain.expiry_date),
        total_quotes=len(chain.quotes),
        total_call_oi=total_call_oi,
        total_put_oi=total_put_oi,
        put_call_oi_ratio=round(total_put_oi / max(total_call_oi, 1), 4),
        total_call_volume=total_call_vol,
        total_put_volume=total_put_vol,
        put_call_volume_ratio=round(total_put_vol / max(total_call_vol, 1), 4),
        max_call_oi_strike=max_call_oi_strike,
        max_put_oi_strike=max_put_oi_strike,
        atm_iv_call=atm_call.implied_vol if atm_call else None,
        atm_iv_put=atm_put.implied_vol if atm_put else None,
        iv_skew_25d=None,
    )


@router.get("/expected-move", response_model=ExpectedMoveResponse)
async def expected_move(request: Request):
    """Blended expected move envelope (VIX1D + straddle + RV-adjusted)."""
    adapter = _get_options_adapter(request)
    analyzer = request.app.state.vix1d_analyzer

    try:
        spot = adapter.fetch_spx_price()
        vix_data = adapter.fetch_vix_data()
        prior = adapter.fetch_prior_session()
        chain = adapter.fetch_spx_options_chain()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Data fetch failed: {exc}")

    vix1d = vix_data.vix1d
    rv20d = prior.realized_vol_20d

    calls = [q for q in chain.quotes if q.option_type.value == "call"]
    puts = [q for q in chain.quotes if q.option_type.value == "put"]
    atm_call = min(calls, key=lambda q: abs(q.strike - spot), default=None)
    atm_put = min(puts, key=lambda q: abs(q.strike - spot), default=None)
    straddle_price = 0.0
    if atm_call and atm_put:
        straddle_price = atm_call.mid + atm_put.mid

    m1 = analyzer.calculate_expected_move(spot, vix1d)
    m2 = analyzer.calculate_straddle_expected_move(straddle_price)
    m3 = analyzer.calculate_rv_adjusted_expected_move(spot, vix1d, rv20d)
    blended = analyzer.calculate_blended_expected_move(spot, vix1d, straddle_price, rv20d)
    regime = analyzer.assess_vol_regime(vix1d)

    return ExpectedMoveResponse(
        spot=spot,
        vix1d=vix1d,
        method1_vix1d=m1["em_1sigma"],
        method2_straddle=m2["em_straddle"],
        method3_rv_adjusted=m3["em_rv_adjusted"],
        blended_em=blended["blended_em"],
        upper_1sigma=round(spot + blended["blended_em"], 2),
        lower_1sigma=round(spot - blended["blended_em"], 2),
        upper_2sigma=round(spot + blended["blended_em"] * 2, 2),
        lower_2sigma=round(spot - blended["blended_em"] * 2, 2),
        iv_rv_ratio=m3["iv_rv_ratio"],
        vol_regime=regime["regime"],
    )


@router.get("/greeks/{strike}", response_model=StrikeGreeksResponse)
async def strike_greeks(
    request: Request,
    strike: float,
    iv: float = Query(0.20, description="Implied volatility (decimal)"),
    expiry: Optional[str] = Query(None),
):
    """Per-strike Greeks including higher-order charm, vanna, and speed."""
    adapter = _get_options_adapter(request)
    engine = request.app.state.gex_engine

    try:
        spot = adapter.fetch_spx_price()
        chain = adapter.fetch_spx_options_chain(expiry_date=expiry)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Data fetch failed: {exc}")

    T = engine._time_to_expiry(chain)

    near = min(chain.quotes, key=lambda q: abs(q.strike - strike), default=None)
    sigma = near.implied_vol if near and near.implied_vol > 0 else iv

    greeks = engine.compute_strike_greeks(spot, strike, T, sigma, 0.0, 0.0)

    return StrikeGreeksResponse(
        strike=strike,
        spot=spot,
        time_to_expiry=round(T, 8),
        delta_call=round(greeks["delta_call"], 6),
        delta_put=round(greeks["delta_put"], 6),
        gamma=round(greeks["gamma"], 8),
        theta=round(greeks["theta"], 4),
        charm=round(greeks["charm"], 6),
        vanna=round(greeks["vanna"], 6),
        speed=round(greeks["speed"], 10),
    )
