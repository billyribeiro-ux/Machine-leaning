"""
SCANIFY Equity Price API — SPX price data, intraday bars, technicals.

Endpoints:
    GET  /api/equity/price/spx           Current SPX level
    GET  /api/equity/price/bars          Intraday 1-min price bars
    GET  /api/equity/price/prior         Prior session reference levels
    GET  /api/equity/price/realized-vol  Realized volatility (annualized)
    GET  /api/equity/price/vwap          Session VWAP from intraday bars
    GET  /api/equity/price/snapshot      Combined price snapshot (spot + prior + bars)
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/equity/price", tags=["equity-price"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class SPXPriceResponse(BaseModel):
    price: float
    currency: str = "USD"
    index: str = "SPX"

class PriceBarResponse(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: int

class PriorSessionResponse(BaseModel):
    spx_close: float
    spx_high: float
    spx_low: float
    spx_vwap: float
    vix1d_close: float
    realized_vol_20d: float

class RealizedVolResponse(BaseModel):
    realized_vol: float
    days: int
    annualized: bool

class VWAPResponse(BaseModel):
    vwap: float
    bar_count: int

class PriceSnapshotResponse(BaseModel):
    spot: float
    prior_close: float
    change_points: float
    change_pct: float
    day_high: float
    day_low: float
    vwap: Optional[float]
    realized_vol_20d: float
    bar_count: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/spx", response_model=SPXPriceResponse)
async def spx_price(request: Request):
    """Current SPX cash index level."""
    yahoo = request.app.state.yahoo
    try:
        price = yahoo.fetch_spx_price()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Price fetch failed: {exc}")
    return SPXPriceResponse(price=round(price, 2))


@router.get("/bars", response_model=List[PriceBarResponse])
async def intraday_bars(
    request: Request,
    period: str = Query("1d"),
    interval: str = Query("1m"),
    last: Optional[int] = Query(None, description="Return only the N most recent bars"),
):
    """Intraday SPX price bars."""
    yahoo = request.app.state.yahoo
    try:
        bars = yahoo.fetch_price_bars(period=period, interval=interval)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Bar fetch failed: {exc}")

    if last is not None and last > 0:
        bars = bars[-last:]

    return [
        PriceBarResponse(
            timestamp=b.timestamp.isoformat(),
            open=round(b.open, 2),
            high=round(b.high, 2),
            low=round(b.low, 2),
            close=round(b.close, 2),
            volume=b.volume,
        )
        for b in bars
    ]


@router.get("/prior", response_model=PriorSessionResponse)
async def prior_session(request: Request):
    """Prior trading session reference levels."""
    yahoo = request.app.state.yahoo
    try:
        prior = yahoo.fetch_prior_session()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Prior session fetch failed: {exc}")
    return PriorSessionResponse(
        spx_close=prior.spx_close,
        spx_high=prior.spx_high,
        spx_low=prior.spx_low,
        spx_vwap=prior.spx_vwap,
        vix1d_close=prior.vix1d_close,
        realized_vol_20d=round(prior.realized_vol_20d, 6),
    )


@router.get("/realized-vol", response_model=RealizedVolResponse)
async def realized_vol(
    request: Request,
    days: int = Query(20, ge=5, le=252),
):
    """Annualized realized volatility from daily log returns."""
    yahoo = request.app.state.yahoo
    try:
        rv = yahoo.compute_realized_vol(days=days)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"RV computation failed: {exc}")
    return RealizedVolResponse(realized_vol=round(rv, 6), days=days, annualized=True)


@router.get("/vwap", response_model=VWAPResponse)
async def session_vwap(request: Request):
    """Session VWAP computed from intraday bars."""
    yahoo = request.app.state.yahoo
    try:
        bars = yahoo.fetch_price_bars(period="1d", interval="1m")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"VWAP fetch failed: {exc}")

    if not bars:
        raise HTTPException(status_code=404, detail="No intraday bars available")

    import numpy as np
    prices = np.array([(b.high + b.low + b.close) / 3.0 for b in bars])
    volumes = np.array([b.volume for b in bars], dtype=np.float64)
    total_vol = volumes.sum()
    if total_vol == 0:
        raise HTTPException(status_code=404, detail="Zero volume — VWAP unavailable")

    vwap = float(np.dot(prices, volumes) / total_vol)
    return VWAPResponse(vwap=round(vwap, 2), bar_count=len(bars))


@router.get("/snapshot", response_model=PriceSnapshotResponse)
async def price_snapshot(request: Request):
    """Combined price snapshot: spot, prior close, change, VWAP, RV."""
    yahoo = request.app.state.yahoo
    try:
        spot = yahoo.fetch_spx_price()
        prior = yahoo.fetch_prior_session()
        bars = yahoo.fetch_price_bars(period="1d", interval="1m")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Snapshot fetch failed: {exc}")

    change_pts = round(spot - prior.spx_close, 2) if prior.spx_close else 0.0
    change_pct = round(change_pts / prior.spx_close * 100, 4) if prior.spx_close else 0.0

    day_high = max((b.high for b in bars), default=spot)
    day_low = min((b.low for b in bars), default=spot)

    vwap = None
    if bars:
        import numpy as np
        prices = np.array([(b.high + b.low + b.close) / 3.0 for b in bars])
        volumes = np.array([b.volume for b in bars], dtype=np.float64)
        total_vol = volumes.sum()
        if total_vol > 0:
            vwap = round(float(np.dot(prices, volumes) / total_vol), 2)

    return PriceSnapshotResponse(
        spot=round(spot, 2),
        prior_close=prior.spx_close,
        change_points=change_pts,
        change_pct=change_pct,
        day_high=round(day_high, 2),
        day_low=round(day_low, 2),
        vwap=vwap,
        realized_vol_20d=round(prior.realized_vol_20d, 6),
        bar_count=len(bars),
    )
