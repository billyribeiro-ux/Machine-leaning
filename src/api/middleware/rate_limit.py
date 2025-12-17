"""
Scanify Rate Limiting Middleware

Tier-based rate limiting with sliding window algorithm.
"""

import time
from collections import defaultdict
from typing import Optional, Callable
from dataclasses import dataclass, field

from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from src.api.auth.tiers import SubscriptionTier, get_rate_limit


@dataclass
class RateLimitState:
    """Tracks rate limit state for a user"""
    requests: list = field(default_factory=list)
    window_start: float = field(default_factory=time.time)


class RateLimiter:
    """
    Sliding window rate limiter with tier-based limits.

    Uses in-memory storage. For production at scale, use Redis.
    """

    def __init__(self, window_seconds: int = 3600):
        self.window_seconds = window_seconds
        self.states: dict[str, RateLimitState] = defaultdict(RateLimitState)

    def _clean_old_requests(self, state: RateLimitState) -> None:
        """Remove requests outside the current window"""
        current_time = time.time()
        cutoff = current_time - self.window_seconds
        state.requests = [t for t in state.requests if t > cutoff]

    def check_rate_limit(
        self,
        identifier: str,
        tier: SubscriptionTier = SubscriptionTier.FREE,
    ) -> tuple[bool, int, int]:
        """
        Check if request is within rate limit.

        Returns:
            (allowed, remaining, reset_seconds)
        """
        limit = get_rate_limit(tier)

        # Unlimited for admin/elite with -1
        if limit == -1:
            return True, -1, 0

        state = self.states[identifier]
        self._clean_old_requests(state)

        current_count = len(state.requests)
        remaining = max(0, limit - current_count)

        # Calculate reset time
        if state.requests:
            oldest_request = min(state.requests)
            reset_seconds = int(oldest_request + self.window_seconds - time.time())
        else:
            reset_seconds = self.window_seconds

        if current_count >= limit:
            return False, 0, reset_seconds

        # Record this request
        state.requests.append(time.time())
        return True, remaining - 1, reset_seconds

    def get_usage(self, identifier: str) -> dict:
        """Get current usage stats for an identifier"""
        state = self.states[identifier]
        self._clean_old_requests(state)
        return {
            "requests_in_window": len(state.requests),
            "window_seconds": self.window_seconds,
        }


# Global rate limiter instance
rate_limiter = RateLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for rate limiting.

    Applies tier-based rate limits to all API requests.
    """

    def __init__(self, app, limiter: Optional[RateLimiter] = None):
        super().__init__(app)
        self.limiter = limiter or rate_limiter

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip rate limiting for non-API routes
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        # Skip rate limiting for health checks
        if request.url.path in ["/api/health", "/api/status"]:
            return await call_next(request)

        # Get user identifier and tier from request state (set by auth)
        user_id = getattr(request.state, "user_id", None)
        tier = getattr(request.state, "tier", SubscriptionTier.FREE)

        # Use IP as fallback identifier for unauthenticated requests
        if user_id is None:
            forwarded = request.headers.get("X-Forwarded-For")
            if forwarded:
                identifier = forwarded.split(",")[0].strip()
            else:
                identifier = request.client.host if request.client else "unknown"
            tier = SubscriptionTier.FREE
        else:
            identifier = user_id

        # Check rate limit
        allowed, remaining, reset_seconds = self.limiter.check_rate_limit(
            identifier, tier
        )

        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "Rate limit exceeded",
                    "retry_after": reset_seconds,
                    "tier": tier.value,
                    "upgrade_url": "/pricing",
                },
                headers={
                    "Retry-After": str(reset_seconds),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_seconds),
                },
            )

        # Process request
        response = await call_next(request)

        # Add rate limit headers
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_seconds)

        return response


def check_rate_limit(
    identifier: str,
    tier: SubscriptionTier = SubscriptionTier.FREE,
) -> None:
    """
    Utility function to manually check rate limit.
    Raises HTTPException if limit exceeded.
    """
    allowed, remaining, reset_seconds = rate_limiter.check_rate_limit(identifier, tier)

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Try again in {reset_seconds} seconds.",
            headers={"Retry-After": str(reset_seconds)},
        )
