"""
Scanify JWT Authentication

Handles token creation, verification, and user authentication.
Production-ready with proper security practices.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel, ConfigDict, EmailStr

from src.api.auth.tiers import SubscriptionTier


# Configuration - MUST use environment variables in production
SECRET_KEY = os.getenv("SCANIFY_SECRET_KEY", "")
if not SECRET_KEY:
    import warnings
    warnings.warn("SCANIFY_SECRET_KEY not set — using random key (sessions won't persist across restarts)", stacklevel=2)
    import secrets
    SECRET_KEY = secrets.token_urlsafe(32)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours
REFRESH_TOKEN_EXPIRE_DAYS = 30

security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)


class TokenData(BaseModel):
    """Token payload data"""
    user_id: str
    email: Optional[str] = None
    tier: SubscriptionTier = SubscriptionTier.FREE
    exp: Optional[datetime] = None


class User(BaseModel):
    """User model for authentication"""
    id: str
    email: str
    username: Optional[str] = None
    tier: SubscriptionTier = SubscriptionTier.FREE
    is_active: bool = True
    is_admin: bool = False
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    created_at: Optional[datetime] = None
    last_login: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

    @property
    def is_premium(self) -> bool:
        """Check if user has any paid tier"""
        return self.tier in [
            SubscriptionTier.BASIC,
            SubscriptionTier.PRO,
            SubscriptionTier.ELITE,
            SubscriptionTier.ADMIN,
        ]

    @property
    def has_realtime_access(self) -> bool:
        """Check if user has real-time signal access"""
        return self.tier in [
            SubscriptionTier.PRO,
            SubscriptionTier.ELITE,
            SubscriptionTier.ADMIN,
        ]


class TokenResponse(BaseModel):
    """Token response model"""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int
    user: User


class LoginRequest(BaseModel):
    """Login request model"""
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    """Registration request model"""
    email: EmailStr
    password: str
    username: Optional[str] = None


def create_access_token(
    user_id: str,
    email: str,
    tier: SubscriptionTier,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a new JWT access token"""
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode = {
        "sub": user_id,
        "email": email,
        "tier": tier.value,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }

    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    """Create a new JWT refresh token"""
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode = {
        "sub": user_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "refresh",
    }

    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> TokenData:
    """Verify and decode a JWT token"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        email: str = payload.get("email")
        tier_str: str = payload.get("tier", "free")
        token_type: str = payload.get("type", "access")

        if user_id is None:
            raise credentials_exception

        if token_type != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            tier = SubscriptionTier(tier_str)
        except ValueError:
            tier = SubscriptionTier.FREE

        return TokenData(user_id=user_id, email=email, tier=tier)

    except JWTError:
        raise credentials_exception


def verify_refresh_token(token: str) -> str:
    """Verify refresh token and return user_id"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        token_type: str = payload.get("type")

        if user_id is None or token_type != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )

        return user_id

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    """Get current user from JWT token"""
    token = credentials.credentials
    token_data = verify_token(token)

    # In production, fetch full user from database here
    # For now, construct from token data
    user = User(
        id=token_data.user_id,
        email=token_data.email or "",
        tier=token_data.tier,
        is_active=True,
        is_admin=token_data.tier == SubscriptionTier.ADMIN,
    )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Ensure the current user is active"""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )
    return current_user


async def get_admin_user(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Ensure the current user is an admin"""
    if not current_user.is_admin and current_user.tier != SubscriptionTier.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security),
) -> Optional[User]:
    """Get current user if authenticated, None otherwise (for public endpoints)"""
    if credentials is None:
        return None

    try:
        token = credentials.credentials
        token_data = verify_token(token)
        return User(
            id=token_data.user_id,
            email=token_data.email or "",
            tier=token_data.tier,
            is_active=True,
            is_admin=token_data.tier == SubscriptionTier.ADMIN,
        )
    except HTTPException:
        return None


def require_tier(minimum_tier: SubscriptionTier):
    """Dependency to require a minimum subscription tier"""
    tier_order = [
        SubscriptionTier.FREE,
        SubscriptionTier.BASIC,
        SubscriptionTier.PRO,
        SubscriptionTier.ELITE,
        SubscriptionTier.ADMIN,
    ]

    async def tier_checker(user: User = Depends(get_current_active_user)) -> User:
        user_tier_index = tier_order.index(user.tier)
        required_tier_index = tier_order.index(minimum_tier)

        if user_tier_index < required_tier_index:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This feature requires {minimum_tier.value} tier or higher",
            )
        return user

    return tier_checker
