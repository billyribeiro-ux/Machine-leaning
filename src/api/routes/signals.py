"""
Scanify Signal Routes

Real-time and historical trading signals with tier-based access.
"""

import asyncio
import csv
import io
import json as json_module
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import APIRouter, HTTPException, status, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.api.auth.jwt import (
    get_current_active_user,
    get_optional_user,
    require_tier,
    User,
)
from src.api.auth.tiers import (
    SubscriptionTier,
    check_scanner_access,
    get_signal_delay,
    get_max_symbols,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/signals", tags=["Signals"])


# Response models
class SignalResponse(BaseModel):
    """Individual signal response"""
    id: str
    symbol: str
    scanner_type: str
    direction: str  # LONG, SHORT, NEUTRAL
    confidence: float
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    targets: List[float] = Field(default_factory=list)
    risk_reward: Optional[float] = None
    timeframe: str
    timestamp: datetime
    metadata: dict = Field(default_factory=dict)

    # Tier-restricted fields
    is_delayed: bool = False
    delay_seconds: int = 0


class SignalListResponse(BaseModel):
    """List of signals response"""
    signals: List[SignalResponse]
    total: int
    page: int
    page_size: int
    has_more: bool
    user_tier: str
    is_realtime: bool


class ScannerStats(BaseModel):
    """Scanner statistics"""
    scanner_type: str
    signals_today: int
    accuracy_7d: Optional[float] = None
    avg_confidence: float
    top_symbol: Optional[str] = None


# In-memory signal store for development
# In production, this would be populated by the scanner engine
_signals_cache: List[dict] = []
_scanner_engine = None


def set_scanner_engine(engine):
    """Set the scanner engine instance (called from main app)"""
    global _scanner_engine
    _scanner_engine = engine


def _apply_signal_delay(signal: dict, delay_seconds: int) -> dict:
    """Apply delay to signal timestamp for non-realtime tiers"""
    if delay_seconds <= 0:
        return signal

    signal_copy = signal.copy()
    signal_copy["is_delayed"] = True
    signal_copy["delay_seconds"] = delay_seconds

    # Only show signal if it's old enough
    signal_time = signal.get("timestamp", datetime.now(timezone.utc))
    if isinstance(signal_time, str):
        signal_time = datetime.fromisoformat(signal_time.replace("Z", "+00:00"))

    cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=delay_seconds)
    if signal_time > cutoff_time:
        return None  # Signal too recent for this tier

    return signal_copy


def _filter_signals_for_tier(
    signals: List[dict],
    tier: SubscriptionTier,
) -> List[dict]:
    """Filter signals based on user tier"""
    delay = get_signal_delay(tier)
    filtered = []

    for signal in signals:
        # Check scanner access
        scanner_type = signal.get("scanner_type", "").lower()
        if not check_scanner_access(tier, scanner_type):
            continue

        # Apply delay
        if delay > 0:
            delayed_signal = _apply_signal_delay(signal, delay)
            if delayed_signal:
                filtered.append(delayed_signal)
        else:
            signal_copy = signal.copy()
            signal_copy["is_delayed"] = False
            signal_copy["delay_seconds"] = 0
            filtered.append(signal_copy)

    return filtered


@router.get("/latest", response_model=SignalListResponse)
async def get_latest_signals(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    scanner_type: Optional[str] = None,
    symbol: Optional[str] = None,
    direction: Optional[str] = None,
    min_confidence: float = Query(0, ge=0, le=100),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """
    Get latest trading signals.

    - **FREE**: 15-min delayed signals, momentum scanner only
    - **BASIC**: 1-min delay, basic scanners
    - **PRO/ELITE**: Real-time, all scanners
    """
    # Determine tier
    tier = current_user.tier if current_user else SubscriptionTier.FREE
    is_realtime = get_signal_delay(tier) == 0

    # Get signals from scanner engine or cache
    if _scanner_engine and hasattr(_scanner_engine, "last_results"):
        raw_signals = []
        if _scanner_engine.last_results:
            for result in _scanner_engine.last_results.results:
                raw_signals.append({
                    "id": f"sig_{result.symbol}_{result.timestamp.timestamp()}",
                    "symbol": result.symbol,
                    "scanner_type": result.scanner_type,
                    "direction": result.direction.value if hasattr(result.direction, "value") else str(result.direction),
                    "confidence": result.confidence,
                    "entry_price": result.entry_price,
                    "stop_loss": result.stop_loss,
                    "targets": result.targets or [],
                    "risk_reward": result.risk_reward,
                    "timeframe": result.timeframe.value if hasattr(result.timeframe, "value") else str(result.timeframe),
                    "timestamp": result.timestamp,
                    "metadata": result.metadata or {},
                })
    else:
        raw_signals = _signals_cache

    # Filter for tier
    signals = _filter_signals_for_tier(raw_signals, tier)

    # Apply additional filters
    if scanner_type:
        signals = [s for s in signals if s["scanner_type"].lower() == scanner_type.lower()]
    if symbol:
        signals = [s for s in signals if s["symbol"].upper() == symbol.upper()]
    if direction:
        signals = [s for s in signals if s["direction"].upper() == direction.upper()]
    if min_confidence > 0:
        signals = [s for s in signals if s["confidence"] >= min_confidence]

    # Sort by timestamp (newest first) and confidence
    signals.sort(key=lambda x: (x.get("timestamp", datetime.min), x.get("confidence", 0)), reverse=True)

    # Paginate
    total = len(signals)
    start = (page - 1) * page_size
    end = start + page_size
    page_signals = signals[start:end]

    return SignalListResponse(
        signals=[SignalResponse(**s) for s in page_signals],
        total=total,
        page=page,
        page_size=page_size,
        has_more=end < total,
        user_tier=tier.value,
        is_realtime=is_realtime,
    )


@router.get("/symbol/{symbol}", response_model=SignalListResponse)
async def get_signals_for_symbol(
    symbol: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get signals for a specific symbol.

    Requires authentication.
    """
    tier = current_user.tier
    max_symbols = get_max_symbols(tier)

    # Get signals
    if _scanner_engine:
        results = await _scanner_engine.scan_single(symbol.upper())
        raw_signals = [
            {
                "id": f"sig_{r.symbol}_{r.timestamp.timestamp()}",
                "symbol": r.symbol,
                "scanner_type": r.scanner_type,
                "direction": r.direction.value if hasattr(r.direction, "value") else str(r.direction),
                "confidence": r.confidence,
                "entry_price": r.entry_price,
                "stop_loss": r.stop_loss,
                "targets": r.targets or [],
                "risk_reward": r.risk_reward,
                "timeframe": r.timeframe.value if hasattr(r.timeframe, "value") else str(r.timeframe),
                "timestamp": r.timestamp,
                "metadata": r.metadata or {},
            }
            for r in results
        ]
    else:
        raw_signals = [s for s in _signals_cache if s["symbol"].upper() == symbol.upper()]

    signals = _filter_signals_for_tier(raw_signals, tier)

    # Paginate
    total = len(signals)
    start = (page - 1) * page_size
    end = start + page_size

    return SignalListResponse(
        signals=[SignalResponse(**s) for s in signals[start:end]],
        total=total,
        page=page,
        page_size=page_size,
        has_more=end < total,
        user_tier=tier.value,
        is_realtime=get_signal_delay(tier) == 0,
    )


@router.get("/scanners", response_model=List[ScannerStats])
async def get_scanner_stats(
    current_user: Optional[User] = Depends(get_optional_user),
):
    """
    Get statistics for all available scanners.

    Shows which scanners are available for the user's tier.
    """
    tier = current_user.tier if current_user else SubscriptionTier.FREE

    # Scanner types and their stats
    all_scanners = [
        {"scanner_type": "momentum", "signals_today": 45, "accuracy_7d": 72.5, "avg_confidence": 78.3, "top_symbol": "SPY"},
        {"scanner_type": "breakout", "signals_today": 23, "accuracy_7d": 68.2, "avg_confidence": 82.1, "top_symbol": "NVDA"},
        {"scanner_type": "reversal", "signals_today": 18, "accuracy_7d": 65.8, "avg_confidence": 75.6, "top_symbol": "AAPL"},
        {"scanner_type": "options_flow", "signals_today": 67, "accuracy_7d": 71.3, "avg_confidence": 80.2, "top_symbol": "TSLA"},
        {"scanner_type": "squeeze", "signals_today": 12, "accuracy_7d": 74.1, "avg_confidence": 85.4, "top_symbol": "GME"},
        {"scanner_type": "gamma", "signals_today": 8, "accuracy_7d": 69.7, "avg_confidence": 79.8, "top_symbol": "SPX"},
        {"scanner_type": "mtf", "signals_today": 34, "accuracy_7d": 73.2, "avg_confidence": 81.5, "top_symbol": "QQQ"},
    ]

    # Filter based on tier access
    available_scanners = [
        ScannerStats(**s)
        for s in all_scanners
        if check_scanner_access(tier, s["scanner_type"])
    ]

    return available_scanners


@router.get("/history")
async def get_signal_history(
    days: int = Query(7, ge=1, le=365),
    scanner_type: Optional[str] = None,
    current_user: User = Depends(require_tier(SubscriptionTier.BASIC)),
):
    """
    Get historical signals.

    - **BASIC**: 7 days
    - **PRO**: 30 days
    - **ELITE**: 365 days

    Requires BASIC tier or higher.
    """
    from src.api.auth.tiers import get_tier_limits

    limits = get_tier_limits(current_user.tier)
    max_days = limits.get("historical_days", 7)

    if max_days != -1 and days > max_days:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Your tier allows up to {max_days} days of history. Upgrade for more.",
        )

    # In production, fetch from database
    return {
        "message": "Historical data endpoint",
        "days_requested": days,
        "max_days_allowed": max_days,
        "scanner_type": scanner_type,
        "data": [],  # Would contain historical signals
    }


@router.post("/export")
async def export_signals(
    format: str = Query("csv", pattern="^(csv|json|pdf)$"),
    scanner_type: Optional[str] = None,
    min_confidence: float = Query(0, ge=0, le=100),
    current_user: User = Depends(require_tier(SubscriptionTier.PRO)),
):
    """
    Export signals as a downloadable file.

    Supported formats: **csv**, **json**, **pdf**.
    Requires PRO tier or higher.
    """
    tier = current_user.tier

    if _scanner_engine and hasattr(_scanner_engine, "last_results") and _scanner_engine.last_results:
        raw_signals = []
        for result in _scanner_engine.last_results.results:
            sig: dict = {
                "symbol": result.symbol,
                "scanner_type": result.scanner_type,
                "direction": result.direction.value if hasattr(result.direction, "value") else str(result.direction),
                "confidence": result.confidence,
                "entry_price": result.entry_price,
                "stop_loss": result.stop_loss,
                "targets": result.targets or [],
                "risk_reward": result.risk_reward,
                "timeframe": result.timeframe.value if hasattr(result.timeframe, "value") else str(result.timeframe),
                "timestamp": result.timestamp.isoformat() if hasattr(result.timestamp, "isoformat") else str(result.timestamp),
            }
            _enrich_precision_alpha(sig, result)
            raw_signals.append(sig)
    else:
        raw_signals = _filter_signals_for_tier(_signals_cache, tier)

    if scanner_type:
        raw_signals = [s for s in raw_signals if s.get("scanner_type", "").lower() == scanner_type.lower()]
    if min_confidence > 0:
        raw_signals = [s for s in raw_signals if s.get("confidence", 0) >= min_confidence]

    raw_signals.sort(
        key=lambda x: (x.get("timestamp", ""), x.get("confidence", 0)),
        reverse=True,
    )

    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if format == "json":
        content = json_module.dumps(raw_signals, indent=2, default=str)
        return StreamingResponse(
            io.BytesIO(content.encode()),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="scanify_signals_{timestamp_str}.json"'
            },
        )

    if format == "csv":
        return _build_csv_response(raw_signals, timestamp_str)

    if format == "pdf":
        return _build_pdf_response(raw_signals, timestamp_str)

    raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")


def _enrich_precision_alpha(sig: dict, result) -> None:
    """Add dimension scores and option recommendation for precision_alpha signals."""
    if getattr(result, "scanner_type", "") != "precision_alpha":
        return
    meta = getattr(result, "metadata", None) or {}
    dims = meta.get("dimensions")
    if dims:
        for dim_name, dim_data in dims.items():
            sig[f"dim_{dim_name}"] = dim_data.get("score", "")
            sig[f"dim_{dim_name}_dir"] = dim_data.get("direction", "")
        sig["regime"] = meta.get("regime", "")
    opt = meta.get("option_recommendation")
    if opt:
        sig["opt_type"] = opt.get("type", "")
        sig["opt_strike"] = opt.get("strike", "")
        sig["opt_dte"] = opt.get("dte", "")
        sig["opt_delta"] = opt.get("delta", "")
        sig["opt_premium"] = opt.get("premium", "")
        sig["opt_breakeven"] = opt.get("breakeven", "")
        sig["opt_max_risk"] = opt.get("max_risk", "")
        sig["opt_target_pnl_pct"] = opt.get("target_pnl_pct", "")


def _build_csv_response(signals: list, timestamp_str: str) -> StreamingResponse:
    """Build a CSV StreamingResponse from a list of signal dicts."""
    base_fields = [
        "timestamp", "symbol", "scanner_type", "direction",
        "confidence", "entry_price", "stop_loss", "targets",
        "risk_reward", "timeframe",
    ]
    has_pa = any(s.get("scanner_type") == "precision_alpha" for s in signals)
    if has_pa:
        pa_dim_fields = []
        for s in signals:
            if s.get("scanner_type") == "precision_alpha":
                pa_dim_fields = [k for k in s if k.startswith("dim_") or k.startswith("opt_") or k == "regime"]
                break
        fieldnames = base_fields + pa_dim_fields
    else:
        fieldnames = base_fields

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for sig in signals:
        row = dict(sig)
        if isinstance(row.get("targets"), list):
            row["targets"] = ";".join(str(t) for t in row["targets"])
        writer.writerow(row)

    return StreamingResponse(
        io.BytesIO(buf.getvalue().encode()),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="scanify_signals_{timestamp_str}.csv"'
        },
    )


def _build_pdf_response(signals: list, timestamp_str: str) -> StreamingResponse:
    """Build a PDF report from signals using only the stdlib.

    Generates a minimal but valid PDF with a signals table.  No third-party
    PDF library is required.
    """
    lines: list[str] = []
    lines.append(f"SCANIFY Signal Export  |  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"Total signals: {len(signals)}")
    lines.append("")
    lines.append(f"{'Symbol':<8} {'Scanner':<14} {'Dir':<7} {'Conf':>6} {'Entry':>10} {'Stop':>10} {'R:R':>6} {'Time'}")
    lines.append("-" * 90)
    for sig in signals:
        symbol = str(sig.get("symbol", ""))[:8]
        scanner = str(sig.get("scanner_type", ""))[:14]
        direction = str(sig.get("direction", ""))[:7]
        confidence = sig.get("confidence", 0)
        entry = sig.get("entry_price")
        stop = sig.get("stop_loss")
        rr = sig.get("risk_reward")
        ts = str(sig.get("timestamp", ""))[:19]
        entry_str = f"{entry:>10.2f}" if entry is not None else f"{'N/A':>10}"
        stop_str = f"{stop:>10.2f}" if stop is not None else f"{'N/A':>10}"
        rr_str = f"{rr:>6.2f}" if rr is not None else f"{'N/A':>6}"
        lines.append(f"{symbol:<8} {scanner:<14} {direction:<7} {confidence:>6.1f} {entry_str} {stop_str} {rr_str} {ts}")

    pa_signals = [s for s in signals if s.get("scanner_type") == "precision_alpha"]
    if pa_signals:
        lines.append("")
        lines.append("=" * 90)
        lines.append("PRECISION ALPHA — Dimension Breakdown")
        lines.append("=" * 90)
        for sig in pa_signals:
            sym = sig.get("symbol", "")
            regime = sig.get("regime", "N/A")
            lines.append(f"\n  {sym}  |  Regime: {regime}  |  Composite: {sig.get('confidence', 0):.1f}")
            lines.append(f"  {'Dimension':<24} {'Score':>7} {'Direction':>10}")
            lines.append(f"  {'-' * 44}")
            for key in sorted(sig.keys()):
                if key.startswith("dim_") and not key.endswith("_dir"):
                    dim_name = key[4:]
                    score = sig.get(key, "")
                    d = sig.get(f"dim_{dim_name}_dir", "")
                    score_str = f"{float(score):>7.1f}" if score != "" else f"{'N/A':>7}"
                    dir_str = f"{float(d):>10.3f}" if d != "" else f"{'N/A':>10}"
                    lines.append(f"  {dim_name:<24} {score_str} {dir_str}")
            if sig.get("opt_type"):
                lines.append(f"  Option: {sig['opt_type']} ${sig.get('opt_strike', '')} "
                             f"({sig.get('opt_dte', '')}d) "
                             f"delta={sig.get('opt_delta', '')} "
                             f"prem=${sig.get('opt_premium', '')} "
                             f"BE=${sig.get('opt_breakeven', '')}")

    text = "\n".join(lines)
    pdf_bytes = _text_to_pdf(text)

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="scanify_signals_{timestamp_str}.pdf"'
        },
    )


def _text_to_pdf(text: str) -> bytes:
    """Convert plain text to a minimal valid PDF (no third-party deps).

    Uses a fixed-width Courier font so tabular data aligns properly.
    """
    text_lines = text.split("\n")
    font_size = 9
    leading = font_size + 3
    margin_x = 40
    margin_y = 40
    page_w = 842  # A4 landscape width in points
    page_h = 595  # A4 landscape height in points
    usable_h = page_h - 2 * margin_y
    lines_per_page = int(usable_h / leading)

    pages: list[list[str]] = []
    for i in range(0, len(text_lines), lines_per_page):
        pages.append(text_lines[i : i + lines_per_page])

    objects: list[bytes] = []
    offsets: list[int] = []
    current_offset = 0

    def add_object(data: bytes) -> int:
        nonlocal current_offset
        offsets.append(current_offset)
        objects.append(data)
        current_offset += len(data)
        return len(objects)

    header = b"%PDF-1.4\n"
    current_offset = len(header)

    # 1 - Catalog
    add_object(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")

    # 2 - Pages (placeholder, will rewrite)
    pages_obj_index = len(objects)
    kids = " ".join(f"{i + 4} 0 R" for i in range(len(pages)))
    add_object(f"2 0 obj\n<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>\nendobj\n".encode())

    # 3 - Font
    add_object(b"3 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>\nendobj\n")

    # Page objects + stream objects
    next_obj_num = 4
    for page_lines in pages:
        page_obj_num = next_obj_num
        stream_obj_num = next_obj_num + 1
        next_obj_num += 2

        # Build text stream
        stream_parts = [f"BT\n/F1 {font_size} Tf\n"]
        y = page_h - margin_y
        for line in page_lines:
            safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            stream_parts.append(f"1 0 0 1 {margin_x} {y} Tm\n({safe}) Tj\n")
            y -= leading
        stream_parts.append("ET\n")
        stream_data = "".join(stream_parts).encode()

        add_object(
            f"{page_obj_num} 0 obj\n"
            f"<< /Type /Page /Parent 2 0 R "
            f"/MediaBox [0 0 {page_w} {page_h}] "
            f"/Contents {stream_obj_num} 0 R "
            f"/Resources << /Font << /F1 3 0 R >> >> >>\n"
            f"endobj\n".encode()
        )
        add_object(
            f"{stream_obj_num} 0 obj\n"
            f"<< /Length {len(stream_data)} >>\n"
            f"stream\n".encode()
            + stream_data
            + b"\nendstream\nendobj\n"
        )

    # Cross-reference table
    xref_offset = len(header) + sum(len(o) for o in objects)
    xref_lines = [f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"]
    running = len(header)
    for obj in objects:
        xref_lines.append(f"{running:010d} 00000 n \n")
        running += len(obj)
    xref_lines.append(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    )

    return header + b"".join(objects) + "".join(xref_lines).encode()
