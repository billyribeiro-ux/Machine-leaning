"""
Scanify API Layer

Unified REST + WebSocket API for the Scanify trading scanner platform.
Supports both desktop and web clients with tier-based access control.
"""

from src.api.main import app, create_app

__all__ = ["app", "create_app"]
