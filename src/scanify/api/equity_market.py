"""
SCANIFY Equity Market API — FMP-specific market data not covered by Yahoo/EDGAR.

Provides company fundamentals, screening, sector rotation, market movers,
technical indicators, and calendars — sourced from Financial Modeling Prep.

Endpoints:
    GET  /api/equity/market/quote/{symbol}        Real-time quote for any symbol
    GET  /api/equity/market/movers                Gainers / losers / most active
    GET  /api/equity/market/sectors               Sector performance breakdown
    GET  /api/equity/market/screener              Stock screener (fundamentals + market)
    GET  /api/equity/market/profile/{symbol}      Company profile
    GET  /api/equity/market/financials/{symbol}   Income / balance / cash flow
    GET  /api/equity/market/ratios/{symbol}       Key metrics + ratios + DCF
    GET  /api/equity/market/technical/{symbol}    Technical indicator series
    GET  /api/equity/market/calendar/earnings     Earnings calendar
    GET  /api/equity/market/calendar/economic     Economic events calendar
    GET  /api/equity/market/constituents/{index}  Index constituents
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/equity/market", tags=["equity-market"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class MoversResponse(BaseModel):
    gainers: List[Dict]
    losers: List[Dict]
    most_active: List[Dict]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/quote/{symbol}")
async def quote(request: Request, symbol: str):
    """Real-time quote for any stock, ETF, or index symbol."""
    fmp = request.app.state.fmp
    try:
        data = fmp.get_quote(symbol)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Quote fetch failed: {exc}")
    if not data:
        raise HTTPException(status_code=404, detail=f"No quote for {symbol}")
    return data


@router.get("/movers", response_model=MoversResponse)
async def movers(request: Request, limit: int = Query(10, ge=1, le=50)):
    """Top gainers, losers, and most active stocks."""
    fmp = request.app.state.fmp
    try:
        gainers = fmp.get_gainers()[:limit]
        losers = fmp.get_losers()[:limit]
        active = fmp.get_most_active()[:limit]
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Movers fetch failed: {exc}")
    return MoversResponse(gainers=gainers, losers=losers, most_active=active)


@router.get("/sectors")
async def sectors(request: Request, historical: bool = Query(False)):
    """Sector performance breakdown (current or historical)."""
    fmp = request.app.state.fmp
    try:
        if historical:
            return fmp.get_historical_sector_performance()
        return fmp.get_sector_performance()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Sector fetch failed: {exc}")


@router.get("/screener")
async def screener(
    request: Request,
    market_cap_min: Optional[float] = Query(None),
    market_cap_max: Optional[float] = Query(None),
    sector: Optional[str] = Query(None),
    industry: Optional[str] = Query(None),
    beta_min: Optional[float] = Query(None),
    beta_max: Optional[float] = Query(None),
    dividend_min: Optional[float] = Query(None),
    volume_min: Optional[int] = Query(None),
    price_min: Optional[float] = Query(None),
    price_max: Optional[float] = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    """Screen stocks by fundamental and market criteria."""
    fmp = request.app.state.fmp
    try:
        return fmp.stock_screener(
            market_cap_min=market_cap_min,
            market_cap_max=market_cap_max,
            sector=sector,
            industry=industry,
            beta_min=beta_min,
            beta_max=beta_max,
            dividend_min=dividend_min,
            volume_min=volume_min,
            price_min=price_min,
            price_max=price_max,
            limit=limit,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Screener failed: {exc}")


@router.get("/profile/{symbol}")
async def profile(request: Request, symbol: str):
    """Company profile (sector, industry, market cap, description)."""
    fmp = request.app.state.fmp
    try:
        data = fmp.get_company_profile(symbol)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Profile fetch failed: {exc}")
    if not data:
        raise HTTPException(status_code=404, detail=f"No profile for {symbol}")
    return data


@router.get("/financials/{symbol}")
async def financials(
    request: Request,
    symbol: str,
    statement: str = Query("income", pattern="^(income|balance|cash)$"),
    period: str = Query("annual", pattern="^(annual|quarter)$"),
    limit: int = Query(5, ge=1, le=40),
):
    """Financial statements: income, balance sheet, or cash flow."""
    fmp = request.app.state.fmp
    try:
        if statement == "income":
            return fmp.get_income_statement(symbol, period=period, limit=limit)
        if statement == "balance":
            return fmp.get_balance_sheet(symbol, period=period, limit=limit)
        return fmp.get_cash_flow(symbol, period=period, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Financials fetch failed: {exc}")


@router.get("/ratios/{symbol}")
async def ratios(
    request: Request,
    symbol: str,
    period: str = Query("annual", pattern="^(annual|quarter)$"),
    limit: int = Query(5, ge=1, le=40),
):
    """Key metrics, financial ratios, and DCF valuation."""
    fmp = request.app.state.fmp
    try:
        return {
            "key_metrics": fmp.get_key_metrics(symbol, period=period, limit=limit),
            "ratios": fmp.get_ratios(symbol, period=period, limit=limit),
            "dcf": fmp.get_dcf(symbol),
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Ratios fetch failed: {exc}")


@router.get("/technical/{symbol}")
async def technical(
    request: Request,
    symbol: str,
    indicator: str = Query("sma"),
    period: int = Query(20, ge=2, le=400),
    interval: str = Query("daily"),
):
    """Technical indicator series (SMA, EMA, RSI, MACD, ADX, etc.)."""
    fmp = request.app.state.fmp
    try:
        return fmp.get_technical_indicator(
            symbol, indicator=indicator, period=period, interval=interval
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Technical fetch failed: {exc}")


@router.get("/calendar/earnings")
async def earnings_calendar(
    request: Request,
    from_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    to_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    """Upcoming earnings announcements."""
    fmp = request.app.state.fmp
    try:
        return fmp.get_earnings_calendar(from_date=from_date, to_date=to_date)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Earnings calendar failed: {exc}")


@router.get("/calendar/economic")
async def economic_calendar(
    request: Request,
    from_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    to_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    """Economic events calendar (CPI, FOMC, NFP, etc.)."""
    fmp = request.app.state.fmp
    try:
        return fmp.get_economic_calendar(from_date=from_date, to_date=to_date)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Economic calendar failed: {exc}")


@router.get("/constituents/{index}")
async def constituents(request: Request, index: str = "sp500"):
    """Index constituents (sp500, nasdaq, dowjones)."""
    fmp = request.app.state.fmp
    try:
        return fmp.get_index_constituents(index)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Constituents fetch failed: {exc}")
