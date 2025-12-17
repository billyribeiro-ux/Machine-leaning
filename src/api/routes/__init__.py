"""Scanify API Routes"""

from src.api.routes.signals import router as signals_router
from src.api.routes.alerts import router as alerts_router
from src.api.routes.auth import router as auth_router
from src.api.routes.status import router as status_router
from src.api.routes.admin import router as admin_router

__all__ = [
    "signals_router",
    "alerts_router",
    "auth_router",
    "status_router",
    "admin_router",
]
