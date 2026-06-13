"""
SCANIFY Equity Macro API — Cross-asset context, VIX, vol regime.

Endpoints:
    GET  /api/equity/macro/vix           VIX family data (VIX, VIX1D, VIX9D)
    GET  /api/equity/macro/vol-regime    Volatility regime classification
    GET  /api/equity/macro/cross-asset   Cross-asset context (yields, DXY)
    GET  /api/equity/macro/risk-premium  VIX1D risk premium adjustment (Albers 2025)
    GET  /api/equity/macro/snapshot      Combined macro snapshot
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/equity/macro", tags=["equity-macro"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class VIXResponse(BaseModel):
    vix: float
    vix1d: float
    vix9d: float
    term_structure: str
    vix1d_vix_ratio: float

class VolRegimeResponse(BaseModel):
    regime: str
    vix1d: float
    description: str
    premium_sell_favorable: bool
    directional_favorable: bool
    recommendations: List[str]

class CrossAssetResponse(BaseModel):
    us_10y_yield: float
    us_10y_yield_change: float
    dxy_level: float
    dxy_change: float
    yield_signal: str
    dollar_signal: str

class RiskPremiumResponse(BaseModel):
    raw_vix1d: float
    adjusted_vix1d: float
    risk_premium_offset: float
    em_raw_1sigma: float
    em_adjusted_1sigma: float

class MacroSnapshotResponse(BaseModel):
    vix: float
    vix1d: float
    vix9d: float
    vol_regime: str
    vol_regime_description: str
    us_10y_yield: float
    us_10y_yield_change: float
    dxy_level: float
    dxy_change: float
    term_structure: str
    risk_premium_adjusted_vix1d: float
    premium_sell_favorable: bool
    directional_favorable: bool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/vix", response_model=VIXResponse)
async def vix_data(request: Request):
    """VIX family data: VIX (30d), VIX1D (1d), VIX9D (9d)."""
    yahoo = request.app.state.yahoo
    try:
        vix = yahoo.fetch_vix_data()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"VIX fetch failed: {exc}")

    ratio = round(vix.vix1d / max(vix.vix, 0.01), 4)
    if vix.vix1d > vix.vix:
        term = "inverted (near-term fear elevated)"
    elif vix.vix1d < vix.vix * 0.85:
        term = "contango (normal, complacency)"
    else:
        term = "flat"

    return VIXResponse(
        vix=round(vix.vix, 2),
        vix1d=round(vix.vix1d, 2),
        vix9d=round(vix.vix9d, 2),
        term_structure=term,
        vix1d_vix_ratio=ratio,
    )


@router.get("/vol-regime", response_model=VolRegimeResponse)
async def vol_regime(request: Request):
    """Volatility regime classification from VIX1D level."""
    yahoo = request.app.state.yahoo
    analyzer = request.app.state.vix1d_analyzer

    try:
        vix = yahoo.fetch_vix_data()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"VIX fetch failed: {exc}")

    regime = analyzer.assess_vol_regime(vix.vix1d)
    return VolRegimeResponse(
        regime=regime["regime"],
        vix1d=round(vix.vix1d, 2),
        description=regime["description"],
        premium_sell_favorable=regime["premium_sell_favorable"],
        directional_favorable=regime["directional_favorable"],
        recommendations=regime["recommendations"],
    )


@router.get("/cross-asset", response_model=CrossAssetResponse)
async def cross_asset(request: Request):
    """Cross-asset context: 10Y Treasury yield and US Dollar Index."""
    yahoo = request.app.state.yahoo
    try:
        data = yahoo.fetch_cross_asset_data()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Cross-asset fetch failed: {exc}")

    yield_signal = "neutral"
    if data.us_10y_yield_change > 0.05:
        yield_signal = "rising yields — equity headwind"
    elif data.us_10y_yield_change < -0.05:
        yield_signal = "falling yields — equity tailwind"

    dollar_signal = "neutral"
    if data.dxy_change > 0.3:
        dollar_signal = "dollar strengthening — risk-off"
    elif data.dxy_change < -0.3:
        dollar_signal = "dollar weakening — risk-on"

    return CrossAssetResponse(
        us_10y_yield=round(data.us_10y_yield, 4),
        us_10y_yield_change=round(data.us_10y_yield_change, 4),
        dxy_level=round(data.dxy_level, 2),
        dxy_change=round(data.dxy_change, 4),
        yield_signal=yield_signal,
        dollar_signal=dollar_signal,
    )


@router.get("/risk-premium", response_model=RiskPremiumResponse)
async def risk_premium(request: Request):
    """VIX1D risk premium adjustment per Albers (2025).

    VIX1D systematically overstates realized 1-day vol by ~0.16 pts.
    """
    yahoo = request.app.state.yahoo
    analyzer = request.app.state.vix1d_analyzer

    try:
        spot = yahoo.fetch_spx_price()
        vix = yahoo.fetch_vix_data()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Data fetch failed: {exc}")

    adjustment = analyzer.vix1d_risk_premium_adjustment(vix.vix1d)
    em_raw = analyzer.calculate_expected_move(spot, vix.vix1d)
    em_adj = analyzer.calculate_expected_move(spot, adjustment["adjusted_vix1d"])

    return RiskPremiumResponse(
        raw_vix1d=adjustment["raw_vix1d"],
        adjusted_vix1d=adjustment["adjusted_vix1d"],
        risk_premium_offset=adjustment["risk_premium_offset"],
        em_raw_1sigma=em_raw["em_1sigma"],
        em_adjusted_1sigma=em_adj["em_1sigma"],
    )


@router.get("/snapshot", response_model=MacroSnapshotResponse)
async def macro_snapshot(request: Request):
    """Combined macro context: VIX, yields, DXY, vol regime, risk premium."""
    yahoo = request.app.state.yahoo
    analyzer = request.app.state.vix1d_analyzer

    try:
        vix = yahoo.fetch_vix_data()
        cross = yahoo.fetch_cross_asset_data()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Macro snapshot failed: {exc}")

    regime = analyzer.assess_vol_regime(vix.vix1d)
    adj = analyzer.vix1d_risk_premium_adjustment(vix.vix1d)

    if vix.vix1d > vix.vix:
        term = "inverted"
    elif vix.vix1d < vix.vix * 0.85:
        term = "contango"
    else:
        term = "flat"

    return MacroSnapshotResponse(
        vix=round(vix.vix, 2),
        vix1d=round(vix.vix1d, 2),
        vix9d=round(vix.vix9d, 2),
        vol_regime=regime["regime"],
        vol_regime_description=regime["description"],
        us_10y_yield=round(cross.us_10y_yield, 4),
        us_10y_yield_change=round(cross.us_10y_yield_change, 4),
        dxy_level=round(cross.dxy_level, 2),
        dxy_change=round(cross.dxy_change, 4),
        term_structure=term,
        risk_premium_adjusted_vix1d=adj["adjusted_vix1d"],
        premium_sell_favorable=regime["premium_sell_favorable"],
        directional_favorable=regime["directional_favorable"],
    )
