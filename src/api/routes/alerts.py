"""
Scanify Alert Routes

Real-time alert management and notification preferences.
"""

from datetime import datetime, timezone
from typing import Optional, List
from enum import Enum

from fastapi import APIRouter, HTTPException, status, Depends, Query
from pydantic import BaseModel, Field

from src.api.auth.jwt import get_current_active_user, require_tier, User
from src.api.auth.tiers import SubscriptionTier, check_tier_access

router = APIRouter(prefix="/alerts", tags=["Alerts"])


class AlertPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AlertType(str, Enum):
    SIGNAL = "signal"
    PRICE = "price"
    VOLUME = "volume"
    NEWS = "news"
    SYSTEM = "system"


class AlertResponse(BaseModel):
    """Alert response model"""
    id: str
    type: AlertType
    priority: AlertPriority
    symbol: Optional[str] = None
    scanner_type: Optional[str] = None
    message: str
    direction: Optional[str] = None
    confidence: Optional[float] = None
    created_at: datetime
    expires_at: Optional[datetime] = None
    read: bool = False
    metadata: dict = Field(default_factory=dict)


class AlertPreferences(BaseModel):
    """User alert preferences"""
    email_alerts: bool = True
    push_alerts: bool = True
    sms_alerts: bool = False
    min_confidence: float = 70.0
    alert_types: List[AlertType] = Field(default_factory=lambda: [AlertType.SIGNAL])
    priority_filter: List[AlertPriority] = Field(
        default_factory=lambda: [AlertPriority.CRITICAL, AlertPriority.HIGH]
    )
    symbols_watchlist: List[str] = Field(default_factory=list)
    quiet_hours_start: Optional[str] = None  # "22:00"
    quiet_hours_end: Optional[str] = None    # "08:00"


class CreateAlertRule(BaseModel):
    """Create a custom alert rule"""
    name: str
    type: AlertType
    symbol: Optional[str] = None
    scanner_type: Optional[str] = None
    min_confidence: float = 70.0
    direction: Optional[str] = None
    is_active: bool = True


class AlertRule(CreateAlertRule):
    """Alert rule with ID"""
    id: str
    created_at: datetime
    triggered_count: int = 0
    last_triggered: Optional[datetime] = None


class AlertCountResponse(BaseModel):
    total: int
    unread: int
    critical: int


class MessageResponse(BaseModel):
    message: str


# In-memory stores
_alerts_cache: List[dict] = []
_user_preferences: dict[str, AlertPreferences] = {}
_user_rules: dict[str, List[AlertRule]] = {}
_scanner_engine = None


def set_scanner_engine(engine):
    """Set scanner engine reference"""
    global _scanner_engine
    _scanner_engine = engine


@router.get("/", response_model=List[AlertResponse])
async def get_alerts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    type: Optional[AlertType] = None,
    priority: Optional[AlertPriority] = None,
    unread_only: bool = False,
    current_user: User = Depends(require_tier(SubscriptionTier.BASIC)),
):
    """
    Get user's alerts.

    Requires BASIC tier or higher for alerts.
    """
    # Get alerts from scanner engine or cache
    if _scanner_engine and hasattr(_scanner_engine, "recent_alerts"):
        alerts = [
            {
                "id": alert.alert_id,
                "type": AlertType.SIGNAL,
                "priority": AlertPriority(alert.priority.value.lower()) if hasattr(alert.priority, "value") else AlertPriority.MEDIUM,
                "symbol": alert.scan_result.symbol if alert.scan_result else None,
                "scanner_type": alert.scan_result.scanner_type if alert.scan_result else None,
                "message": alert.message,
                "direction": alert.scan_result.direction.value if alert.scan_result and hasattr(alert.scan_result.direction, "value") else None,
                "confidence": alert.scan_result.confidence if alert.scan_result else None,
                "created_at": alert.created_at,
                "expires_at": alert.expires_at,
                "read": False,
                "metadata": {},
            }
            for alert in _scanner_engine.recent_alerts
        ]
    else:
        alerts = _alerts_cache

    # Apply filters
    if type:
        alerts = [a for a in alerts if a.get("type") == type]
    if priority:
        alerts = [a for a in alerts if a.get("priority") == priority]
    if unread_only:
        alerts = [a for a in alerts if not a.get("read", False)]

    # Sort by created_at descending
    alerts.sort(key=lambda x: x.get("created_at", datetime.min), reverse=True)

    # Paginate
    start = (page - 1) * page_size
    end = start + page_size

    return [AlertResponse(**a) for a in alerts[start:end]]


@router.get("/count", response_model=AlertCountResponse)
async def get_alert_count(
    current_user: User = Depends(require_tier(SubscriptionTier.BASIC)),
):
    """Get count of unread alerts"""
    if _scanner_engine and hasattr(_scanner_engine, "recent_alerts"):
        total = len(_scanner_engine.recent_alerts)
    else:
        total = len(_alerts_cache)

    return {
        "total": total,
        "unread": total,  # In production, track read status per user
        "critical": sum(1 for a in _alerts_cache if a.get("priority") == AlertPriority.CRITICAL),
    }


@router.post("/{alert_id}/read", response_model=MessageResponse)
async def mark_alert_read(
    alert_id: str,
    current_user: User = Depends(require_tier(SubscriptionTier.BASIC)),
):
    """Mark an alert as read"""
    # In production, update database
    return {"message": "Alert marked as read", "alert_id": alert_id}


@router.post("/read-all", response_model=MessageResponse)
async def mark_all_alerts_read(
    current_user: User = Depends(require_tier(SubscriptionTier.BASIC)),
):
    """Mark all alerts as read"""
    return {"message": "All alerts marked as read"}


@router.get("/preferences", response_model=AlertPreferences)
async def get_alert_preferences(
    current_user: User = Depends(require_tier(SubscriptionTier.BASIC)),
):
    """Get user's alert preferences"""
    prefs = _user_preferences.get(current_user.id, AlertPreferences())
    return prefs


@router.put("/preferences", response_model=AlertPreferences)
async def update_alert_preferences(
    preferences: AlertPreferences,
    current_user: User = Depends(require_tier(SubscriptionTier.BASIC)),
):
    """Update user's alert preferences"""
    # SMS alerts require PRO tier
    if preferences.sms_alerts and not check_tier_access(current_user.tier, "priority_alerts"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="SMS alerts require PRO tier or higher",
        )

    _user_preferences[current_user.id] = preferences
    return preferences


@router.get("/rules", response_model=List[AlertRule])
async def get_alert_rules(
    current_user: User = Depends(require_tier(SubscriptionTier.PRO)),
):
    """
    Get user's custom alert rules.

    Requires PRO tier or higher.
    """
    rules = _user_rules.get(current_user.id, [])
    return rules


@router.post("/rules", response_model=AlertRule)
async def create_alert_rule(
    rule: CreateAlertRule,
    current_user: User = Depends(require_tier(SubscriptionTier.PRO)),
):
    """
    Create a custom alert rule.

    Requires PRO tier or higher.
    """
    import secrets

    new_rule = AlertRule(
        id=f"rule_{secrets.token_hex(8)}",
        created_at=datetime.now(timezone.utc),
        **rule.model_dump(),
    )

    if current_user.id not in _user_rules:
        _user_rules[current_user.id] = []

    # Limit rules per user
    max_rules = 10 if current_user.tier == SubscriptionTier.PRO else 50
    if len(_user_rules[current_user.id]) >= max_rules:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {max_rules} rules allowed for your tier",
        )

    _user_rules[current_user.id].append(new_rule)
    return new_rule


@router.delete("/rules/{rule_id}", response_model=MessageResponse)
async def delete_alert_rule(
    rule_id: str,
    current_user: User = Depends(require_tier(SubscriptionTier.PRO)),
):
    """Delete an alert rule"""
    rules = _user_rules.get(current_user.id, [])
    _user_rules[current_user.id] = [r for r in rules if r.id != rule_id]
    return {"message": "Rule deleted", "rule_id": rule_id}


@router.put("/rules/{rule_id}/toggle")
async def toggle_alert_rule(
    rule_id: str,
    current_user: User = Depends(require_tier(SubscriptionTier.PRO)),
):
    """Toggle an alert rule on/off"""
    rules = _user_rules.get(current_user.id, [])
    for rule in rules:
        if rule.id == rule_id:
            rule.is_active = not rule.is_active
            return {"message": "Rule toggled", "rule_id": rule_id, "is_active": rule.is_active}

    raise HTTPException(status_code=404, detail="Rule not found")
