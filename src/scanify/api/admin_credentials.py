"""
SCANIFY Admin Credentials API — API key CRUD, rotation, vendor management.

All endpoints require ``X-Scanify-Admin-Token`` header for authentication.

Endpoints:
    GET     /api/admin/credentials/vendors           List all vendors with status
    GET     /api/admin/credentials/vendors/{id}       Vendor detail and readiness
    PUT     /api/admin/credentials/vendors/{id}       Add or update credentials
    DELETE  /api/admin/credentials/vendors/{id}       Remove credentials
    POST    /api/admin/credentials/vendors/{id}/rotate  Rotate credentials
    GET     /api/admin/credentials/export             Export masked credentials
    POST    /api/admin/credentials/generate-token     Generate a new admin token
"""

import os
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/admin/credentials", tags=["admin-credentials"])


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

def _verify_admin_token(
    x_scanify_admin_token: str = Header(..., alias="X-Scanify-Admin-Token"),
) -> str:
    """Validate the admin token from the request header."""
    expected = os.environ.get("SCANIFY_ADMIN_TOKEN", "")
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Admin token not configured. Set SCANIFY_ADMIN_TOKEN env var.",
        )
    if x_scanify_admin_token != expected:
        raise HTTPException(status_code=403, detail="Invalid admin token.")
    return x_scanify_admin_token


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class SetCredentialRequest(BaseModel):
    fields: Dict[str, str]
    notes: str = ""

class RotateCredentialRequest(BaseModel):
    new_fields: Dict[str, str]

class VendorSummary(BaseModel):
    vendor_id: str
    display_name: str
    auth_type: str
    status: str
    required_fields: List[str]
    optional_fields: List[str]
    has_stored_credential: bool
    env_configured: bool
    rotation_count: int
    last_updated: Optional[str]
    docs_url: str

class VendorDetail(BaseModel):
    vendor_id: str
    display_name: str
    auth_type: str
    status: str
    fields_configured: List[str]
    fields_missing: List[str]
    is_ready: bool
    created_at: Optional[str]
    updated_at: Optional[str]
    rotated_at: Optional[str]
    rotation_count: int
    notes: str
    base_url: str
    docs_url: str
    rate_limit_per_sec: float

class CredentialResponse(BaseModel):
    vendor_id: str
    status: str
    updated_at: str
    rotation_count: int
    message: str

class AdminTokenResponse(BaseModel):
    token: str
    message: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/vendors", response_model=List[VendorSummary])
async def list_vendors(
    request: Request,
    _token: str = Depends(_verify_admin_token),
):
    """List all registered data vendors with their credential status."""
    store = request.app.state.credential_store
    vendors = store.list_vendors()
    return [VendorSummary(**v) for v in vendors]


@router.get("/vendors/{vendor_id}", response_model=VendorDetail)
async def vendor_detail(
    request: Request,
    vendor_id: str,
    _token: str = Depends(_verify_admin_token),
):
    """Detailed status for a specific vendor."""
    store = request.app.state.credential_store
    detail = store.get_vendor_status(vendor_id)
    if "error" in detail:
        raise HTTPException(status_code=404, detail=detail["error"])
    return VendorDetail(**detail)


@router.put("/vendors/{vendor_id}", response_model=CredentialResponse)
async def set_credential(
    request: Request,
    vendor_id: str,
    body: SetCredentialRequest,
    _token: str = Depends(_verify_admin_token),
):
    """Add or update credentials for a vendor."""
    store = request.app.state.credential_store
    try:
        entry = store.set(vendor_id, body.fields, notes=body.notes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return CredentialResponse(
        vendor_id=vendor_id,
        status=entry.status,
        updated_at=entry.updated_at,
        rotation_count=entry.rotation_count,
        message=f"Credentials set for {vendor_id}.",
    )


@router.delete("/vendors/{vendor_id}", response_model=CredentialResponse)
async def delete_credential(
    request: Request,
    vendor_id: str,
    _token: str = Depends(_verify_admin_token),
):
    """Remove stored credentials for a vendor."""
    store = request.app.state.credential_store
    deleted = store.delete(vendor_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"No stored credentials for {vendor_id}.",
        )
    return CredentialResponse(
        vendor_id=vendor_id,
        status="deleted",
        updated_at="",
        rotation_count=0,
        message=f"Credentials deleted for {vendor_id}.",
    )


@router.post("/vendors/{vendor_id}/rotate", response_model=CredentialResponse)
async def rotate_credential(
    request: Request,
    vendor_id: str,
    body: RotateCredentialRequest,
    _token: str = Depends(_verify_admin_token),
):
    """Rotate credentials — replace with new values, increment rotation counter."""
    store = request.app.state.credential_store
    try:
        entry = store.rotate(vendor_id, body.new_fields)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return CredentialResponse(
        vendor_id=vendor_id,
        status=entry.status,
        updated_at=entry.updated_at,
        rotation_count=entry.rotation_count,
        message=f"Credentials rotated for {vendor_id} (rotation #{entry.rotation_count}).",
    )


@router.get("/export")
async def export_credentials(
    request: Request,
    _token: str = Depends(_verify_admin_token),
):
    """Export all credentials with values masked (for audit/display)."""
    store = request.app.state.credential_store
    return store.export_masked()


@router.post("/generate-token", response_model=AdminTokenResponse)
async def generate_admin_token(
    request: Request,
    _token: str = Depends(_verify_admin_token),
):
    """Generate a new secure admin token.

    The generated token is returned but NOT automatically applied.
    Set it as ``SCANIFY_ADMIN_TOKEN`` env var to use it.
    """
    from ..credentials import CredentialStore
    new_token = CredentialStore.generate_admin_token()
    return AdminTokenResponse(
        token=new_token,
        message="Set this as SCANIFY_ADMIN_TOKEN env var. Current token remains active until replaced.",
    )
