"""
SCANIFY Schwab OAuth API — Authorization flow and status endpoints.

Endpoints:
    GET  /api/admin/schwab/status       Check Schwab API connection status
    GET  /api/admin/schwab/authorize    Get authorization URL for OAuth flow
    POST /api/admin/schwab/callback     Exchange authorization code for tokens
"""

import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/admin/schwab", tags=["schwab-auth"])

_ADMIN_TOKEN = os.environ.get("SCANIFY_ADMIN_TOKEN", "")


def _check_admin(token: Optional[str]) -> None:
    if _ADMIN_TOKEN and token != _ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid admin token")


class SchwabStatusResponse(BaseModel):
    configured: bool
    has_refresh_token: bool
    has_access_token: bool
    authorization_url: Optional[str]


class AuthUrlResponse(BaseModel):
    url: str
    instructions: str


class TokenResponse(BaseModel):
    success: bool
    message: str


@router.get("/status", response_model=SchwabStatusResponse)
async def schwab_status(request: Request):
    """Check Schwab API connection status."""
    schwab = request.app.state.schwab

    auth_url = None
    if schwab.is_configured and not schwab.has_refresh_token:
        auth_url = schwab.get_authorization_url()

    return SchwabStatusResponse(
        configured=schwab.is_configured,
        has_refresh_token=schwab.has_refresh_token,
        has_access_token=schwab._access_token is not None,
        authorization_url=auth_url,
    )


@router.get("/authorize", response_model=AuthUrlResponse)
async def get_auth_url(request: Request):
    """Get the Schwab OAuth authorization URL."""
    schwab = request.app.state.schwab

    if not schwab.is_configured:
        raise HTTPException(
            status_code=400,
            detail="Schwab credentials not configured. Set client_id and client_secret "
                   "via /api/admin/credentials/vendors/schwab or environment variables.",
        )

    url = schwab.get_authorization_url()

    return AuthUrlResponse(
        url=url,
        instructions=(
            "1. Open this URL in your browser\n"
            "2. Log in with your Schwab brokerage account\n"
            "3. Authorize the app\n"
            "4. Copy the authorization code from the callback URL\n"
            "5. POST it to /api/admin/schwab/callback"
        ),
    )


@router.post("/callback", response_model=TokenResponse)
async def exchange_code(
    request: Request,
    code: str = Query(..., description="Authorization code from Schwab OAuth callback"),
    admin_token: Optional[str] = Query(None, alias="token"),
):
    """Exchange an authorization code for access + refresh tokens."""
    _check_admin(admin_token)

    schwab = request.app.state.schwab

    if not schwab.is_configured:
        raise HTTPException(status_code=400, detail="Schwab credentials not configured.")

    try:
        schwab.exchange_authorization_code(code)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Token exchange failed: {exc}",
        )

    return TokenResponse(
        success=True,
        message="Schwab tokens acquired successfully. Options chain data is now available.",
    )
