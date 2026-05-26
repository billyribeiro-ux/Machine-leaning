"""
Scanify Admin Routes

Administrative endpoints for system management.
"""

from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, HTTPException, status, Depends, Query
from pydantic import BaseModel

from src.api.auth.jwt import get_admin_user, User
from src.api.auth.tiers import SubscriptionTier

router = APIRouter(prefix="/admin", tags=["Admin"])


class UserSummary(BaseModel):
    """User summary for admin view"""
    id: str
    email: str
    username: Optional[str]
    tier: SubscriptionTier
    is_active: bool
    created_at: Optional[datetime]
    last_login: Optional[datetime]
    signals_viewed: int = 0


class SystemMetrics(BaseModel):
    """System metrics"""
    active_connections: int
    websocket_connections: int
    api_requests_hour: int
    signals_generated_today: int
    alerts_sent_today: int
    avg_response_time_ms: float
    error_rate_percent: float
    memory_usage_mb: float
    cpu_usage_percent: float


class ScannerControl(BaseModel):
    """Scanner control command"""
    scanner_name: str
    action: str  # start, stop, pause, resume


class MessageResponse(BaseModel):
    message: str


# Module state
_scanner_engine = None


def set_scanner_engine(engine):
    """Set scanner engine reference"""
    global _scanner_engine
    _scanner_engine = engine


@router.get("/users", response_model=List[UserSummary])
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    tier: Optional[SubscriptionTier] = None,
    admin_user: User = Depends(get_admin_user),
):
    """List all users (admin only)"""
    # In production, fetch from database
    # Import from auth routes for demo
    from src.api.routes.auth import _users_db

    users = []
    for email, data in _users_db.items():
        if tier and data.get("tier") != tier:
            continue
        users.append(UserSummary(
            id=data["id"],
            email=email,
            username=data.get("username"),
            tier=data.get("tier", SubscriptionTier.FREE),
            is_active=data.get("is_active", True),
            created_at=data.get("created_at"),
            last_login=data.get("last_login"),
        ))

    # Paginate
    start = (page - 1) * page_size
    end = start + page_size
    return users[start:end]


@router.put("/users/{user_id}/tier", response_model=MessageResponse)
async def update_user_tier(
    user_id: str,
    tier: SubscriptionTier,
    admin_user: User = Depends(get_admin_user),
):
    """Update a user's subscription tier (admin only)"""
    from src.api.routes.auth import _users_db

    # Find user
    for email, data in _users_db.items():
        if data["id"] == user_id:
            data["tier"] = tier
            return {"message": f"User {email} updated to {tier.value} tier"}

    raise HTTPException(status_code=404, detail="User not found")


@router.put("/users/{user_id}/status", response_model=MessageResponse)
async def update_user_status(
    user_id: str,
    is_active: bool,
    admin_user: User = Depends(get_admin_user),
):
    """Enable/disable a user account (admin only)"""
    from src.api.routes.auth import _users_db

    for email, data in _users_db.items():
        if data["id"] == user_id:
            data["is_active"] = is_active
            return {"message": f"User {email} {'enabled' if is_active else 'disabled'}"}

    raise HTTPException(status_code=404, detail="User not found")


@router.get("/metrics", response_model=SystemMetrics)
async def get_system_metrics(
    admin_user: User = Depends(get_admin_user),
):
    """Get system metrics (admin only)"""
    import psutil

    # Get actual system metrics
    memory = psutil.virtual_memory()
    cpu = psutil.cpu_percent(interval=0.1)

    return SystemMetrics(
        active_connections=42,  # Would come from connection manager
        websocket_connections=15,
        api_requests_hour=1250,
        signals_generated_today=709,
        alerts_sent_today=156,
        avg_response_time_ms=45.2,
        error_rate_percent=0.3,
        memory_usage_mb=memory.used / (1024 * 1024),
        cpu_usage_percent=cpu,
    )


@router.post("/scanner/control")
async def control_scanner(
    control: ScannerControl,
    admin_user: User = Depends(get_admin_user),
):
    """Control scanner operation (admin only)"""
    if not _scanner_engine:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Scanner engine not initialized",
        )

    action = control.action.lower()

    if action == "start":
        await _scanner_engine.start(continuous=True)
    elif action == "stop":
        await _scanner_engine.stop()
    elif action == "pause":
        await _scanner_engine.pause()
    elif action == "resume":
        await _scanner_engine.resume()
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown action: {action}",
        )

    return {
        "message": f"Scanner {control.scanner_name} {action} command sent",
        "timestamp": datetime.now(timezone.utc),
    }


@router.post("/broadcast")
async def broadcast_message(
    message: str,
    priority: str = "info",
    admin_user: User = Depends(get_admin_user),
):
    """Broadcast a message to all connected clients (admin only)"""
    # Would broadcast via WebSocket manager
    return {
        "message": "Broadcast sent",
        "content": message,
        "priority": priority,
        "timestamp": datetime.now(timezone.utc),
    }


@router.get("/logs")
async def get_recent_logs(
    lines: int = Query(100, ge=1, le=1000),
    level: str = Query("INFO"),
    admin_user: User = Depends(get_admin_user),
):
    """Get recent application logs (admin only)"""
    # In production, would read from log files or logging service
    return {
        "logs": [
            {"timestamp": datetime.now(timezone.utc), "level": "INFO", "message": "Scanner cycle completed"},
            {"timestamp": datetime.now(timezone.utc), "level": "INFO", "message": "45 signals generated"},
        ],
        "total_lines": lines,
        "level_filter": level,
    }


@router.delete("/cache")
async def clear_cache(
    cache_type: str = Query("all", pattern="^(all|signals|alerts|users)$"),
    admin_user: User = Depends(get_admin_user),
):
    """Clear application cache (admin only)"""
    # Would clear appropriate caches
    return {
        "message": f"Cache '{cache_type}' cleared",
        "timestamp": datetime.now(timezone.utc),
    }
