"""
SCANIFY Credential Store — API key management with encryption at rest.

Provides a unified credential management layer for all data vendor
integrations. Keys are encrypted using Fernet symmetric encryption
and stored in ``~/.scanify/credentials.json``.

Supports:
    - Multiple vendor auth types (API key, bearer token, user-agent, OAuth)
    - Add / update / delete / rotate credentials
    - Environment variable overrides (env vars always win)
    - Encrypted file-based persistence
    - Vendor validation and health checks

Credential resolution order:
    1. Environment variable (e.g. ``SCANIFY_POLYGON_API_KEY``)
    2. Encrypted credentials file (``~/.scanify/credentials.json``)
    3. Vendor default (if any)
"""

import base64
import hashlib
import json
import logging
import os
import platform
import secrets
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AuthType(Enum):
    """Authentication method required by a data vendor."""
    API_KEY = "api_key"
    BEARER_TOKEN = "bearer_token"
    USER_AGENT = "user_agent"
    OAUTH_CLIENT = "oauth_client"
    BASIC_AUTH = "basic_auth"
    NONE = "none"


class VendorStatus(Enum):
    """Current status of a vendor credential."""
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    NOT_CONFIGURED = "not_configured"


# ---------------------------------------------------------------------------
# Vendor registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VendorSpec:
    """Specification for a supported data vendor."""
    vendor_id: str
    display_name: str
    auth_type: AuthType
    required_fields: Tuple[str, ...]
    optional_fields: Tuple[str, ...] = ()
    env_prefix: str = ""
    base_url: str = ""
    docs_url: str = ""
    default_values: Dict[str, str] = field(default_factory=dict)
    rate_limit_per_sec: float = 10.0


VENDOR_REGISTRY: Dict[str, VendorSpec] = {
    "yahoo_finance": VendorSpec(
        vendor_id="yahoo_finance",
        display_name="Yahoo Finance",
        auth_type=AuthType.NONE,
        required_fields=(),
        optional_fields=("api_key",),
        env_prefix="SCANIFY_YAHOO",
        base_url="https://query1.finance.yahoo.com",
        docs_url="https://pypi.org/project/yfinance/",
        default_values={},
        rate_limit_per_sec=2.0,
    ),
    "sec_edgar": VendorSpec(
        vendor_id="sec_edgar",
        display_name="SEC EDGAR",
        auth_type=AuthType.USER_AGENT,
        required_fields=("user_agent",),
        optional_fields=(),
        env_prefix="SCANIFY_EDGAR",
        base_url="https://data.sec.gov",
        docs_url="https://www.sec.gov/edgar/sec-api-documentation",
        default_values={"user_agent": "ScanifyScanner admin@scanify.dev"},
        rate_limit_per_sec=10.0,
    ),
    "polygon": VendorSpec(
        vendor_id="polygon",
        display_name="Polygon.io",
        auth_type=AuthType.API_KEY,
        required_fields=("api_key",),
        optional_fields=("plan",),
        env_prefix="SCANIFY_POLYGON",
        base_url="https://api.polygon.io",
        docs_url="https://polygon.io/docs",
        rate_limit_per_sec=5.0,
    ),
    "tradier": VendorSpec(
        vendor_id="tradier",
        display_name="Tradier",
        auth_type=AuthType.BEARER_TOKEN,
        required_fields=("access_token",),
        optional_fields=("account_id",),
        env_prefix="SCANIFY_TRADIER",
        base_url="https://api.tradier.com",
        docs_url="https://documentation.tradier.com/",
        rate_limit_per_sec=1.0,
    ),
    "cboe_livevol": VendorSpec(
        vendor_id="cboe_livevol",
        display_name="CBOE LiveVol",
        auth_type=AuthType.API_KEY,
        required_fields=("api_key",),
        optional_fields=("subscription_level",),
        env_prefix="SCANIFY_CBOE",
        base_url="https://api.livevol.com",
        docs_url="https://www.cboe.com/data/",
        rate_limit_per_sec=5.0,
    ),
    "ibkr": VendorSpec(
        vendor_id="ibkr",
        display_name="Interactive Brokers",
        auth_type=AuthType.BASIC_AUTH,
        required_fields=("username", "password"),
        optional_fields=("gateway_port", "account_id"),
        env_prefix="SCANIFY_IBKR",
        base_url="https://localhost:5000",
        docs_url="https://interactivebrokers.github.io/cpwebapi/",
        default_values={"gateway_port": "5000"},
        rate_limit_per_sec=10.0,
    ),
    "schwab": VendorSpec(
        vendor_id="schwab",
        display_name="Charles Schwab (TD Ameritrade)",
        auth_type=AuthType.OAUTH_CLIENT,
        required_fields=("client_id", "client_secret"),
        optional_fields=("redirect_uri", "refresh_token"),
        env_prefix="SCANIFY_SCHWAB",
        base_url="https://api.schwabapi.com",
        docs_url="https://developer.schwab.com/",
        rate_limit_per_sec=2.0,
    ),
    "unusual_whales": VendorSpec(
        vendor_id="unusual_whales",
        display_name="Unusual Whales",
        auth_type=AuthType.BEARER_TOKEN,
        required_fields=("api_token",),
        optional_fields=(),
        env_prefix="SCANIFY_UW",
        base_url="https://api.unusualwhales.com",
        docs_url="https://docs.unusualwhales.com/",
        rate_limit_per_sec=1.0,
    ),
    "orats": VendorSpec(
        vendor_id="orats",
        display_name="ORATS (Options Research & Technology Services)",
        auth_type=AuthType.API_KEY,
        required_fields=("api_key",),
        optional_fields=(),
        env_prefix="SCANIFY_ORATS",
        base_url="https://api.orats.io",
        docs_url="https://docs.orats.io/",
        rate_limit_per_sec=5.0,
    ),
}


# ---------------------------------------------------------------------------
# Credential entry
# ---------------------------------------------------------------------------

@dataclass
class CredentialEntry:
    """A single vendor's stored credentials."""
    vendor_id: str
    fields: Dict[str, str]
    status: str = "active"
    created_at: str = ""
    updated_at: str = ""
    rotated_at: str = ""
    rotation_count: int = 0
    notes: str = ""

    def __post_init__(self):
        now = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now


# ---------------------------------------------------------------------------
# Encryption helpers
# ---------------------------------------------------------------------------

def _derive_key(master_key: str) -> bytes:
    """Derive a Fernet key from a master key string."""
    dk = hashlib.pbkdf2_hmac("sha256", master_key.encode(), b"scanify-salt-v1", 100_000)
    return base64.urlsafe_b64encode(dk)


def _default_master_key() -> str:
    """Generate a machine-specific master key as fallback."""
    node = platform.node()
    mac = hex(platform.node().__hash__())
    return f"scanify-{node}-{mac}-default"


# ---------------------------------------------------------------------------
# Credential Store
# ---------------------------------------------------------------------------

class CredentialStore:
    """Manages encrypted credential storage and retrieval.

    Usage::

        store = CredentialStore()
        store.set("polygon", {"api_key": "pk_..."})
        key = store.get("polygon", "api_key")
        store.rotate("polygon", {"api_key": "pk_new_..."})
        store.delete("polygon")
    """

    DEFAULT_PATH = os.path.expanduser("~/.scanify/credentials.json")

    def __init__(
        self,
        credentials_path: Optional[str] = None,
        master_key: Optional[str] = None,
    ):
        self._path = Path(credentials_path or self.DEFAULT_PATH)
        self._master_key = (
            master_key
            or os.environ.get("SCANIFY_MASTER_KEY")
            or _default_master_key()
        )
        self._fernet = Fernet(_derive_key(self._master_key))
        self._credentials: Dict[str, CredentialEntry] = {}
        self._load()

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------

    def set(self, vendor_id: str, fields: Dict[str, str], notes: str = "") -> CredentialEntry:
        """Add or replace credentials for a vendor.

        Validates against the vendor spec's required fields.
        """
        spec = VENDOR_REGISTRY.get(vendor_id)
        if spec is None:
            raise ValueError(f"Unknown vendor: {vendor_id}")

        for req in spec.required_fields:
            if req not in fields or not fields[req]:
                raise ValueError(f"Missing required field '{req}' for {spec.display_name}")

        now = datetime.now(timezone.utc).isoformat()
        existing = self._credentials.get(vendor_id)

        entry = CredentialEntry(
            vendor_id=vendor_id,
            fields=fields,
            status="active",
            created_at=existing.created_at if existing else now,
            updated_at=now,
            rotated_at=existing.rotated_at if existing else "",
            rotation_count=existing.rotation_count if existing else 0,
            notes=notes,
        )
        self._credentials[vendor_id] = entry
        self._save()
        logger.info("Credential set for vendor: %s", vendor_id)
        return entry

    def get(self, vendor_id: str, field_name: str) -> Optional[str]:
        """Retrieve a single credential field.

        Resolution order: env var -> stored credential -> vendor default.
        """
        spec = VENDOR_REGISTRY.get(vendor_id)

        # 1. Environment variable override
        if spec and spec.env_prefix:
            env_key = f"{spec.env_prefix}_{field_name.upper()}"
            env_val = os.environ.get(env_key)
            if env_val:
                return env_val

        # 2. Stored credential
        entry = self._credentials.get(vendor_id)
        if entry and field_name in entry.fields:
            return entry.fields[field_name]

        # 3. Vendor default
        if spec and field_name in spec.default_values:
            return spec.default_values[field_name]

        return None

    def get_all_fields(self, vendor_id: str) -> Dict[str, str]:
        """Retrieve all credential fields for a vendor (merged with env/defaults)."""
        spec = VENDOR_REGISTRY.get(vendor_id)
        result: Dict[str, str] = {}

        # Start with defaults
        if spec:
            result.update(spec.default_values)

        # Layer stored credentials
        entry = self._credentials.get(vendor_id)
        if entry:
            result.update(entry.fields)

        # Layer env vars (highest priority)
        if spec and spec.env_prefix:
            all_field_names = set(spec.required_fields) | set(spec.optional_fields)
            if entry:
                all_field_names |= set(entry.fields.keys())
            for fn in all_field_names:
                env_key = f"{spec.env_prefix}_{fn.upper()}"
                env_val = os.environ.get(env_key)
                if env_val:
                    result[fn] = env_val

        return result

    def delete(self, vendor_id: str) -> bool:
        """Remove stored credentials for a vendor."""
        if vendor_id in self._credentials:
            del self._credentials[vendor_id]
            self._save()
            logger.info("Credential deleted for vendor: %s", vendor_id)
            return True
        return False

    def rotate(self, vendor_id: str, new_fields: Dict[str, str]) -> CredentialEntry:
        """Rotate credentials — replace with new values and increment counter."""
        spec = VENDOR_REGISTRY.get(vendor_id)
        if spec is None:
            raise ValueError(f"Unknown vendor: {vendor_id}")

        for req in spec.required_fields:
            if req not in new_fields or not new_fields[req]:
                raise ValueError(f"Missing required field '{req}' for rotation")

        now = datetime.now(timezone.utc).isoformat()
        existing = self._credentials.get(vendor_id)

        entry = CredentialEntry(
            vendor_id=vendor_id,
            fields=new_fields,
            status="active",
            created_at=existing.created_at if existing else now,
            updated_at=now,
            rotated_at=now,
            rotation_count=(existing.rotation_count + 1) if existing else 1,
            notes=existing.notes if existing else "",
        )
        self._credentials[vendor_id] = entry
        self._save()
        logger.info(
            "Credential rotated for vendor: %s (rotation #%d)",
            vendor_id, entry.rotation_count,
        )
        return entry

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def list_vendors(self) -> List[Dict]:
        """List all registered vendors with their configuration status."""
        result = []
        for vid, spec in VENDOR_REGISTRY.items():
            entry = self._credentials.get(vid)
            status = "not_configured"
            if entry:
                status = entry.status
            elif spec.auth_type == AuthType.NONE:
                status = "active"

            # Check if env vars provide the credentials
            env_configured = False
            if spec.env_prefix:
                for req in spec.required_fields:
                    env_key = f"{spec.env_prefix}_{req.upper()}"
                    if os.environ.get(env_key):
                        env_configured = True
                        break

            if env_configured and status == "not_configured":
                status = "active (env)"

            result.append({
                "vendor_id": vid,
                "display_name": spec.display_name,
                "auth_type": spec.auth_type.value,
                "status": status,
                "required_fields": list(spec.required_fields),
                "optional_fields": list(spec.optional_fields),
                "has_stored_credential": entry is not None,
                "env_configured": env_configured,
                "rotation_count": entry.rotation_count if entry else 0,
                "last_updated": entry.updated_at if entry else None,
                "docs_url": spec.docs_url,
            })
        return result

    def get_vendor_status(self, vendor_id: str) -> Dict:
        """Detailed status for a single vendor."""
        spec = VENDOR_REGISTRY.get(vendor_id)
        if spec is None:
            return {"error": f"Unknown vendor: {vendor_id}"}

        entry = self._credentials.get(vendor_id)
        fields_configured = []
        fields_missing = []

        for req in spec.required_fields:
            val = self.get(vendor_id, req)
            if val:
                fields_configured.append(req)
            else:
                fields_missing.append(req)

        return {
            "vendor_id": vendor_id,
            "display_name": spec.display_name,
            "auth_type": spec.auth_type.value,
            "status": entry.status if entry else ("active" if spec.auth_type == AuthType.NONE else "not_configured"),
            "fields_configured": fields_configured,
            "fields_missing": fields_missing,
            "is_ready": len(fields_missing) == 0 or spec.auth_type == AuthType.NONE,
            "created_at": entry.created_at if entry else None,
            "updated_at": entry.updated_at if entry else None,
            "rotated_at": entry.rotated_at if entry else None,
            "rotation_count": entry.rotation_count if entry else 0,
            "notes": entry.notes if entry else "",
            "base_url": spec.base_url,
            "docs_url": spec.docs_url,
            "rate_limit_per_sec": spec.rate_limit_per_sec,
        }

    def is_vendor_ready(self, vendor_id: str) -> bool:
        """Check whether a vendor has all required credentials configured."""
        spec = VENDOR_REGISTRY.get(vendor_id)
        if spec is None:
            return False
        if spec.auth_type == AuthType.NONE:
            return True
        for req in spec.required_fields:
            if not self.get(vendor_id, req):
                return False
        return True

    # ------------------------------------------------------------------
    # Persistence (encrypted JSON)
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load and decrypt credentials from disk."""
        if not self._path.exists():
            logger.debug("No credentials file at %s", self._path)
            return

        try:
            raw = self._path.read_bytes()
            decrypted = self._fernet.decrypt(raw)
            data = json.loads(decrypted)
        except InvalidToken:
            logger.error(
                "Cannot decrypt credentials file — master key mismatch. "
                "Set SCANIFY_MASTER_KEY or delete %s to start fresh.",
                self._path,
            )
            return
        except Exception as exc:
            logger.error("Failed to load credentials: %s", exc)
            return

        for vid, entry_data in data.items():
            try:
                self._credentials[vid] = CredentialEntry(**entry_data)
            except Exception as exc:
                logger.warning("Skipping corrupt entry for %s: %s", vid, exc)

        logger.info("Loaded credentials for %d vendors.", len(self._credentials))

    def _save(self) -> None:
        """Encrypt and persist credentials to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            vid: asdict(entry)
            for vid, entry in self._credentials.items()
        }
        plaintext = json.dumps(data, indent=2).encode()
        encrypted = self._fernet.encrypt(plaintext)

        self._path.write_bytes(encrypted)
        os.chmod(self._path, 0o600)
        logger.debug("Credentials saved to %s", self._path)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def generate_admin_token() -> str:
        """Generate a secure random admin token for API access."""
        return secrets.token_urlsafe(32)

    def export_masked(self) -> Dict:
        """Export credentials with values masked (for display/logging)."""
        result = {}
        for vid, entry in self._credentials.items():
            masked_fields = {}
            for k, v in entry.fields.items():
                if len(v) > 8:
                    masked_fields[k] = v[:4] + "****" + v[-4:]
                elif v:
                    masked_fields[k] = "****"
                else:
                    masked_fields[k] = ""
            result[vid] = {
                "vendor_id": vid,
                "fields": masked_fields,
                "status": entry.status,
                "updated_at": entry.updated_at,
                "rotation_count": entry.rotation_count,
            }
        return result
