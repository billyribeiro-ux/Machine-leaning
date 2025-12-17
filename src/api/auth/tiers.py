"""
Scanify Subscription Tiers

Defines access levels and rate limits for different subscription tiers.
"""

from enum import Enum
from typing import Any


class SubscriptionTier(str, Enum):
    """Subscription tier levels"""
    FREE = "free"
    BASIC = "basic"
    PRO = "pro"
    ELITE = "elite"
    ADMIN = "admin"  # For your own use / screen sharing


TIER_LIMITS: dict[str, dict[str, Any]] = {
    "free": {
        "name": "Free",
        "price_monthly": 0,
        "delay_seconds": 900,  # 15 minute delay
        "scanners": ["momentum"],
        "websocket": False,
        "api_calls_per_hour": 60,
        "max_symbols": 5,
        "historical_days": 0,
        "alerts_enabled": False,
        "export_enabled": False,
        "discord_access": False,
    },
    "basic": {
        "name": "Basic",
        "price_monthly": 29,
        "delay_seconds": 60,  # 1 minute delay
        "scanners": ["momentum", "breakout", "reversal"],
        "websocket": False,
        "api_calls_per_hour": 500,
        "max_symbols": 25,
        "historical_days": 7,
        "alerts_enabled": True,
        "export_enabled": False,
        "discord_access": True,
    },
    "pro": {
        "name": "Pro",
        "price_monthly": 99,
        "delay_seconds": 0,  # Real-time
        "scanners": ["all"],
        "websocket": True,
        "api_calls_per_hour": 5000,
        "max_symbols": 100,
        "historical_days": 30,
        "alerts_enabled": True,
        "export_enabled": True,
        "discord_access": True,
        "priority_alerts": True,
    },
    "elite": {
        "name": "Elite",
        "price_monthly": 299,
        "delay_seconds": 0,
        "scanners": ["all"],
        "websocket": True,
        "api_calls_per_hour": 50000,
        "max_symbols": -1,  # Unlimited
        "historical_days": 365,
        "alerts_enabled": True,
        "export_enabled": True,
        "api_key_access": True,
        "priority_support": True,
        "discord_access": True,
        "one_on_one_calls": True,
    },
    "admin": {
        "name": "Admin",
        "price_monthly": 0,
        "delay_seconds": 0,
        "scanners": ["all"],
        "websocket": True,
        "api_calls_per_hour": -1,  # Unlimited
        "max_symbols": -1,
        "historical_days": -1,
        "alerts_enabled": True,
        "export_enabled": True,
        "api_key_access": True,
        "admin_access": True,
        "discord_access": True,
    },
}


def get_tier_limits(tier: SubscriptionTier) -> dict[str, Any]:
    """Get limits for a subscription tier"""
    return TIER_LIMITS.get(tier.value, TIER_LIMITS["free"])


def check_tier_access(tier: SubscriptionTier, feature: str) -> bool:
    """Check if a tier has access to a specific feature"""
    limits = get_tier_limits(tier)

    feature_map = {
        "websocket": "websocket",
        "alerts": "alerts_enabled",
        "export": "export_enabled",
        "api_key": "api_key_access",
        "admin": "admin_access",
        "discord": "discord_access",
        "priority_alerts": "priority_alerts",
    }

    if feature in feature_map:
        return limits.get(feature_map[feature], False)

    if feature.startswith("scanner:"):
        scanner_name = feature.split(":")[1]
        allowed = limits.get("scanners", [])
        return "all" in allowed or scanner_name in allowed

    return False


def check_scanner_access(tier: SubscriptionTier, scanner_type: str) -> bool:
    """Check if tier can access a specific scanner"""
    limits = get_tier_limits(tier)
    allowed_scanners = limits.get("scanners", [])
    return "all" in allowed_scanners or scanner_type.lower() in allowed_scanners


def get_signal_delay(tier: SubscriptionTier) -> int:
    """Get the signal delay in seconds for a tier"""
    limits = get_tier_limits(tier)
    return limits.get("delay_seconds", 900)


def get_rate_limit(tier: SubscriptionTier) -> int:
    """Get API calls per hour limit for a tier"""
    limits = get_tier_limits(tier)
    return limits.get("api_calls_per_hour", 60)


def get_max_symbols(tier: SubscriptionTier) -> int:
    """Get maximum symbols a tier can track"""
    limits = get_tier_limits(tier)
    return limits.get("max_symbols", 5)


def tier_can_access_realtime(tier: SubscriptionTier) -> bool:
    """Check if tier has real-time access (no delay)"""
    return get_signal_delay(tier) == 0
