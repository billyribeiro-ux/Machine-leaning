"""
Scanify Signal Routes

Real-time and historical trading signals with tier-based access.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import APIRouter, HTTPException, status, Depends, Query
from pydantic import BaseModel

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
    targets: List[float] = []
    risk_reward: Optional[float] = None
    timeframe: str
    timestamp: datetime
    metadata: dict = {}

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
    format: str = Query("csv", regex="^(csv|json|xlsx)$"),
    current_user: User = Depends(require_tier(SubscriptionTier.PRO)),
):
    """
    Export signals to file.

    Requires PRO tier or higher.
    """
    return {
        "message": "Export initiated",
        "format": format,
        "download_url": f"/api/signals/download/{format}",  # Would generate actual file
    }
