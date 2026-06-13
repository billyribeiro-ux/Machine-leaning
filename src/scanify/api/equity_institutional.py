"""
SCANIFY Equity Institutional API — SEC EDGAR 13F filings and positioning.

Endpoints:
    GET  /api/equity/institutional/holders     Major SPX/SPY institutional holders
    GET  /api/equity/institutional/sentiment   Aggregate institutional sentiment
    GET  /api/equity/institutional/options      Options-heavy institution filing activity
    GET  /api/equity/institutional/filings      13F filings for a specific institution
    GET  /api/equity/institutional/report       Full formatted institutional report
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/equity/institutional", tags=["equity-institutional"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class HolderResponse(BaseModel):
    cik: str
    name: str
    filing_date: str
    report_date: str
    shares_held: int
    value_usd: float
    share_change: int
    change_pct: float
    portfolio_pct: float

class SentimentResponse(BaseModel):
    sentiment: str
    confidence: float
    num_holders: int
    new_positions: int
    increased: int
    decreased: int
    sold_out: int
    large_changes: List[Dict]

class OptionsPositionResponse(BaseModel):
    holder_name: str
    filing_date: str
    put_value: float
    call_value: float
    put_call_ratio: float
    total_options_value: float

class FilingResponse(BaseModel):
    accession_number: str
    filing_date: str
    report_date: str
    form: str

class ReportResponse(BaseModel):
    report: str
    generated_at: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/holders", response_model=List[HolderResponse])
async def major_holders(request: Request):
    """Major SPX/SPY institutional holders from 13F filings.

    Returns filing metadata for Vanguard, BlackRock, State Street,
    Fidelity, JPMorgan, Citadel, and Bridgewater.
    """
    edgar = request.app.state.edgar
    try:
        holders = edgar.get_major_spx_holders()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"EDGAR fetch failed: {exc}")

    return [
        HolderResponse(
            cik=h.cik,
            name=h.name,
            filing_date=h.filing_date,
            report_date=h.report_date,
            shares_held=h.shares_held,
            value_usd=h.value_usd,
            share_change=h.share_change,
            change_pct=h.change_pct,
            portfolio_pct=h.portfolio_pct,
        )
        for h in holders
    ]


@router.get("/sentiment", response_model=SentimentResponse)
async def institutional_sentiment(request: Request):
    """Aggregate institutional sentiment analysis from 13F data."""
    edgar = request.app.state.edgar
    try:
        holders = edgar.get_major_spx_holders()
        analysis = edgar.analyze_institutional_sentiment(holders)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Sentiment analysis failed: {exc}")

    details = analysis["details"]
    return SentimentResponse(
        sentiment=analysis["sentiment"],
        confidence=analysis["confidence"],
        num_holders=details["num_holders"],
        new_positions=details["new_positions"],
        increased=details["increased"],
        decreased=details["decreased"],
        sold_out=details["sold_out"],
        large_changes=details["large_changes"],
    )


@router.get("/options", response_model=List[OptionsPositionResponse])
async def options_heavy_filings(
    request: Request,
    days_back: int = Query(90, ge=1, le=365),
):
    """Recent 13F filings from options-heavy institutions.

    Covers Citadel, Susquehanna, Jane Street, Wolverine, Two Sigma,
    and DE Shaw.
    """
    edgar = request.app.state.edgar
    try:
        positions = edgar.get_options_activity_filings(days_back=days_back)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Options filings fetch failed: {exc}")

    return [
        OptionsPositionResponse(
            holder_name=p.holder_name,
            filing_date=p.filing_date,
            put_value=p.put_value,
            call_value=p.call_value,
            put_call_ratio=p.put_call_ratio,
            total_options_value=p.total_options_value,
        )
        for p in positions
    ]


@router.get("/filings", response_model=List[FilingResponse])
async def institution_filings(
    request: Request,
    cik: str = Query(..., description="Institution CIK (e.g. 0000102909 for Vanguard)"),
    limit: int = Query(4, ge=1, le=20),
):
    """Fetch recent 13F filings for a specific institution by CIK."""
    edgar = request.app.state.edgar
    try:
        filings = edgar.get_13f_filings(cik, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Filing fetch failed: {exc}")

    return [
        FilingResponse(
            accession_number=f.get("accessionNumber", ""),
            filing_date=f.get("filingDate", ""),
            report_date=f.get("reportDate", ""),
            form=f.get("form", ""),
        )
        for f in filings
    ]


@router.get("/report", response_model=ReportResponse)
async def full_report(request: Request):
    """Full formatted institutional positioning report."""
    edgar = request.app.state.edgar
    from datetime import datetime, timezone

    try:
        report = edgar.get_report()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Report generation failed: {exc}")

    return ReportResponse(
        report=report,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
