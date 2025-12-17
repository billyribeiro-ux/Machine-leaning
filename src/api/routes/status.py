"""
Scanify Status Routes

System health, scanner status, and market information.
"""

from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.auth.jwt import get_optional_user, get_current_active_user, User

router = APIRouter(prefix="/status", tags=["Status"])


class SystemHealth(BaseModel):
    """System health status"""
    status: str  # healthy, degraded, down
    version: str
    uptime_seconds: int
    environment: str
    timestamp: datetime


class ScannerStatus(BaseModel):
    """Individual scanner status"""
    name: str
    status: str  # running, paused, stopped, error
    last_scan: Optional[datetime] = None
    signals_generated: int = 0
    avg_scan_time_ms: float = 0
    error_count: int = 0


class MarketStatus(BaseModel):
    """Market status"""
    market: str  # US, CRYPTO, FOREX
    status: str  # open, closed, pre-market, after-hours
    next_open: Optional[datetime] = None
    next_close: Optional[datetime] = None


class DataProviderStatus(BaseModel):
    """Data provider status"""
    provider: str
    status: str  # connected, disconnected, rate_limited
    latency_ms: Optional[float] = None
    last_data_at: Optional[datetime] = None


class FullStatusResponse(BaseModel):
    """Complete system status"""
    system: SystemHealth
    scanners: List[ScannerStatus]
    markets: List[MarketStatus]
    data_providers: List[DataProviderStatus]
    active_users: int
    signals_today: int


# Module-level state
_start_time = datetime.now(timezone.utc)
_scanner_engine = None


def set_scanner_engine(engine):
    """Set scanner engine reference"""
    global _scanner_engine
    _scanner_engine = engine


@router.get("/health", response_model=SystemHealth)
async def health_check():
    """
    Basic health check endpoint.

    No authentication required. Used for load balancers and monitoring.
    """
    uptime = (datetime.now(timezone.utc) - _start_time).total_seconds()

    status = "healthy"
    if _scanner_engine:
        engine_state = getattr(_scanner_engine, "state", None)
        if engine_state and hasattr(engine_state, "value"):
            if engine_state.value == "error":
                status = "degraded"
            elif engine_state.value == "stopped":
                status = "degraded"

    return SystemHealth(
        status=status,
        version="1.0.0",
        uptime_seconds=int(uptime),
        environment="production",
        timestamp=datetime.now(timezone.utc),
    )


@router.get("/", response_model=FullStatusResponse)
async def get_full_status(
    current_user: Optional[User] = Depends(get_optional_user),
):
    """
    Get complete system status.

    Public endpoint with basic info. Authenticated users see more details.
    """
    uptime = (datetime.now(timezone.utc) - _start_time).total_seconds()

    # System health
    system = SystemHealth(
        status="healthy",
        version="1.0.0",
        uptime_seconds=int(uptime),
        environment="production",
        timestamp=datetime.now(timezone.utc),
    )

    # Scanner status
    scanners = []
    if _scanner_engine:
        summary = _scanner_engine.get_summary() if hasattr(_scanner_engine, "get_summary") else {}
        scanner_names = ["momentum", "breakout", "reversal", "options_flow", "squeeze", "gamma", "mtf"]
        for name in scanner_names:
            scanners.append(ScannerStatus(
                name=name,
                status="running" if summary.get("state") == "RUNNING" else "stopped",
                last_scan=datetime.now(timezone.utc),
                signals_generated=summary.get("total_signals", 0) // len(scanner_names),
                avg_scan_time_ms=summary.get("avg_scan_time_ms", 50),
                error_count=0,
            ))
    else:
        # Demo data
        scanners = [
            ScannerStatus(name="momentum", status="running", signals_generated=145, avg_scan_time_ms=45.2),
            ScannerStatus(name="breakout", status="running", signals_generated=89, avg_scan_time_ms=52.1),
            ScannerStatus(name="reversal", status="running", signals_generated=67, avg_scan_time_ms=48.7),
            ScannerStatus(name="options_flow", status="running", signals_generated=234, avg_scan_time_ms=78.3),
            ScannerStatus(name="squeeze", status="running", signals_generated=34, avg_scan_time_ms=62.5),
            ScannerStatus(name="gamma", status="running", signals_generated=28, avg_scan_time_ms=55.8),
            ScannerStatus(name="mtf", status="running", signals_generated=112, avg_scan_time_ms=95.4),
        ]

    # Market status
    now = datetime.now(timezone.utc)
    hour = now.hour
    weekday = now.weekday()

    # Simplified market hours check (EST converted to UTC)
    us_market_open = 14 <= hour < 21 and weekday < 5
    markets = [
        MarketStatus(
            market="US",
            status="open" if us_market_open else "closed",
            next_open=None,
            next_close=None,
        ),
        MarketStatus(
            market="CRYPTO",
            status="open",  # 24/7
        ),
        MarketStatus(
            market="FOREX",
            status="open" if weekday < 5 else "closed",
        ),
    ]

    # Data providers
    data_providers = [
        DataProviderStatus(
            provider="polygon",
            status="connected",
            latency_ms=12.5,
            last_data_at=datetime.now(timezone.utc),
        ),
        DataProviderStatus(
            provider="alpaca",
            status="connected",
            latency_ms=18.2,
            last_data_at=datetime.now(timezone.utc),
        ),
    ]

    return FullStatusResponse(
        system=system,
        scanners=scanners,
        markets=markets,
        data_providers=data_providers,
        active_users=42,  # Would come from connection manager
        signals_today=sum(s.signals_generated for s in scanners),
    )


@router.get("/scanners", response_model=List[ScannerStatus])
async def get_scanner_status(
    current_user: User = Depends(get_current_active_user),
):
    """Get detailed scanner status (authenticated)"""
    if _scanner_engine and hasattr(_scanner_engine, "scanners"):
        scanners = []
        for name, scanner in _scanner_engine.scanners.items():
            scanners.append(ScannerStatus(
                name=name,
                status="running",
                last_scan=datetime.now(timezone.utc),
                signals_generated=0,
                avg_scan_time_ms=50,
                error_count=0,
            ))
        return scanners

    # Demo data
    return [
        ScannerStatus(name="momentum", status="running", signals_generated=145),
        ScannerStatus(name="breakout", status="running", signals_generated=89),
        ScannerStatus(name="options_flow", status="running", signals_generated=234),
    ]


@router.get("/markets", response_model=List[MarketStatus])
async def get_market_status():
    """Get current market status (public)"""
    now = datetime.now(timezone.utc)
    hour = now.hour
    weekday = now.weekday()
    us_market_open = 14 <= hour < 21 and weekday < 5

    return [
        MarketStatus(market="US", status="open" if us_market_open else "closed"),
        MarketStatus(market="CRYPTO", status="open"),
        MarketStatus(market="FOREX", status="open" if weekday < 5 else "closed"),
    ]
