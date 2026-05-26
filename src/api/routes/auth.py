"""
Scanify Authentication Routes

Handles login, registration, token refresh, and user management.
"""

import os
import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, EmailStr

from src.api.auth.jwt import (
    create_access_token,
    create_refresh_token,
    verify_refresh_token,
    get_current_active_user,
    User,
    TokenResponse,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)
from src.api.auth.tiers import SubscriptionTier, get_tier_limits

router = APIRouter(prefix="/auth", tags=["Authentication"])


# In-memory user store for development
# Replace with database in production
_users_db: dict[str, dict] = {}


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    username: Optional[str] = None


class RefreshRequest(BaseModel):
    refresh_token: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


class UserProfile(BaseModel):
    id: str
    email: str
    username: Optional[str]
    tier: SubscriptionTier
    tier_name: str
    is_active: bool
    created_at: Optional[datetime]
    features: dict


def _hash_password(password: str) -> str:
    """Hash password using PBKDF2 with per-user random salt."""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations=600_000)
    return f"{salt}${dk.hex()}"


def _verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against a PBKDF2 hash."""
    if "$" not in stored_hash:
        return False
    salt, dk_hex = stored_hash.split("$", 1)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations=600_000)
    return secrets.compare_digest(dk.hex(), dk_hex)


def _generate_user_id() -> str:
    """Generate unique user ID"""
    return f"user_{secrets.token_hex(12)}"


@router.post("/register", response_model=TokenResponse)
async def register(request: RegisterRequest):
    """
    Register a new user account.

    New users start on the FREE tier.
    """
    email = request.email.lower()

    # Check if user already exists
    if email in _users_db:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create new user
    user_id = _generate_user_id()
    user_data = {
        "id": user_id,
        "email": email,
        "username": request.username or email.split("@")[0],
        "password_hash": _hash_password(request.password),
        "tier": SubscriptionTier.FREE,
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
        "last_login": datetime.now(timezone.utc),
    }

    _users_db[email] = user_data

    # Generate tokens
    access_token = create_access_token(
        user_id=user_id,
        email=email,
        tier=SubscriptionTier.FREE,
    )
    refresh_token = create_refresh_token(user_id)

    user = User(
        id=user_id,
        email=email,
        username=user_data["username"],
        tier=SubscriptionTier.FREE,
        is_active=True,
        created_at=user_data["created_at"],
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user,
    )


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """
    Login with email and password.

    Returns access and refresh tokens.
    """
    email = request.email.lower()

    # Find user
    user_data = _users_db.get(email)
    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Verify password
    password_hash = _hash_password(request.password)
    if password_hash != user_data["password_hash"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Check if active
    if not user_data.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    # Update last login
    user_data["last_login"] = datetime.now(timezone.utc)

    # Generate tokens
    access_token = create_access_token(
        user_id=user_data["id"],
        email=email,
        tier=user_data["tier"],
    )
    refresh_token = create_refresh_token(user_data["id"])

    user = User(
        id=user_data["id"],
        email=email,
        username=user_data.get("username"),
        tier=user_data["tier"],
        is_active=True,
        created_at=user_data.get("created_at"),
        last_login=user_data["last_login"],
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshRequest):
    """
    Refresh access token using refresh token.
    """
    user_id = verify_refresh_token(request.refresh_token)

    # Find user by ID
    user_data = None
    for email, data in _users_db.items():
        if data["id"] == user_id:
            user_data = data
            break

    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    # Generate new access token
    access_token = create_access_token(
        user_id=user_data["id"],
        email=user_data["email"],
        tier=user_data["tier"],
    )

    user = User(
        id=user_data["id"],
        email=user_data["email"],
        username=user_data.get("username"),
        tier=user_data["tier"],
        is_active=user_data.get("is_active", True),
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=request.refresh_token,  # Return same refresh token
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user,
    )


@router.get("/me", response_model=UserProfile)
async def get_current_user_profile(
    current_user: User = Depends(get_current_active_user),
):
    """
    Get current user's profile and subscription details.
    """
    tier_limits = get_tier_limits(current_user.tier)

    return UserProfile(
        id=current_user.id,
        email=current_user.email,
        username=current_user.username,
        tier=current_user.tier,
        tier_name=tier_limits["name"],
        is_active=current_user.is_active,
        created_at=current_user.created_at,
        features={
            "realtime_signals": tier_limits.get("delay_seconds", 900) == 0,
            "websocket_access": tier_limits.get("websocket", False),
            "alerts_enabled": tier_limits.get("alerts_enabled", False),
            "export_enabled": tier_limits.get("export_enabled", False),
            "max_symbols": tier_limits.get("max_symbols", 5),
            "scanners": tier_limits.get("scanners", ["momentum"]),
            "api_calls_per_hour": tier_limits.get("api_calls_per_hour", 60),
        },
    )


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_active_user)):
    """
    Logout current user.

    In a production system, this would invalidate the refresh token.
    """
    # In production, add refresh token to blacklist or delete from database
    return {"message": "Successfully logged out"}


@router.post("/change-password")
async def change_password(
    request: PasswordChangeRequest,
    current_user: User = Depends(get_current_active_user),
):
    """
    Change user's password.
    """
    user_data = _users_db.get(current_user.email)
    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Verify current password
    current_hash = _hash_password(request.current_password)
    if current_hash != user_data["password_hash"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )

    # Update password
    user_data["password_hash"] = _hash_password(request.new_password)

    return {"message": "Password changed successfully"}


# Admin endpoint to create test users with specific tiers
@router.post("/admin/create-user", include_in_schema=False)
async def admin_create_user(
    email: str,
    password: str,
    tier: SubscriptionTier,
    admin_key: str,
):
    """Create a user with specific tier (admin only)"""
    expected_key = os.getenv("SCANIFY_ADMIN_KEY", "")
    if not expected_key:
        raise HTTPException(status_code=503, detail="Admin endpoint not configured")
    if not secrets.compare_digest(admin_key, expected_key):
        raise HTTPException(status_code=403, detail="Invalid admin key")

    email = email.lower()
    user_id = _generate_user_id()

    _users_db[email] = {
        "id": user_id,
        "email": email,
        "username": email.split("@")[0],
        "password_hash": _hash_password(password),
        "tier": tier,
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
    }

    return {"message": f"User {email} created with {tier.value} tier", "user_id": user_id}
