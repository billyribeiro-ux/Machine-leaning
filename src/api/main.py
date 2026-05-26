"""
Scanify API - Main Application

Production-ready FastAPI application with:
- REST API endpoints for signals, alerts, and status
- WebSocket real-time streaming
- JWT authentication with tier-based access
- Rate limiting middleware
- Request correlation IDs and structured logging
- CORS configuration
"""

import logging
import os
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, WebSocket, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.api.routes import (
    signals_router,
    alerts_router,
    auth_router,
    status_router,
    admin_router,
)
from src.api.websocket.handlers import manager, websocket_endpoint
from src.api.middleware.rate_limit import RateLimitMiddleware
from src.api.middleware.request_context import (
    RequestContextMiddleware,
    install_request_id_filter,
    request_id_var,
)

logger = logging.getLogger("revolution.api")

_scanner_engine = None
_engine_lock = threading.Lock()
_start_time = datetime.now(timezone.utc)


def set_scanner_engine(engine) -> None:
    """Set the scanner engine for API access"""
    global _scanner_engine
    with _engine_lock:
        _scanner_engine = engine

    from src.api.routes import signals, alerts, status, admin
    from src.api.websocket import handlers

    signals.set_scanner_engine(engine)
    alerts.set_scanner_engine(engine)
    status.set_scanner_engine(engine)
    admin.set_scanner_engine(engine)
    handlers.manager.set_scanner_engine(engine)


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    uptime_seconds: int
    timestamp: str
    checks: dict


class ErrorResponse(BaseModel):
    error: str
    detail: str
    request_id: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    install_request_id_filter()
    logger.info("Scanify API starting")

    await manager.start_heartbeat(interval=30)

    with _engine_lock:
        if _scanner_engine:
            logger.info("Scanner engine connected")

    yield

    logger.info("Scanify API shutting down")


def create_app(
    title: str = "Scanify API",
    version: str = "1.0.0",
    debug: bool = False,
) -> FastAPI:
    app = FastAPI(
        title=title,
        description="""
# Scanify Trading Scanner API

Real-time trading signals and alerts powered by ML.

## Authentication

All protected endpoints require a Bearer token in the Authorization header:

```
Authorization: Bearer <your_jwt_token>
```

## Rate Limits

| Tier | Requests/Hour | WebSocket |
|------|--------------|-----------|
| Free | 60 | No |
| Basic | 500 | No |
| Pro | 5,000 | Yes |
| Elite | 50,000 | Yes |

## WebSocket

Connect to `/ws/signals?token=<jwt_token>` for real-time updates.
Requires PRO tier or higher.
        """,
        version=version,
        docs_url="/docs" if debug else "/api/docs",
        redoc_url="/redoc" if debug else "/api/redoc",
        openapi_url="/openapi.json" if debug else "/api/openapi.json",
        lifespan=lifespan,
    )

    # CORS
    allowed_origins = os.getenv("SCANIFY_CORS_ORIGINS", "").split(",")
    if not allowed_origins or allowed_origins == [""]:
        allowed_origins = [
            "http://localhost:3000",
            "http://localhost:5173",
            "http://localhost:1420",
            "https://scanify.app",
            "https://www.scanify.app",
            "tauri://localhost",
        ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
            "X-Request-ID",
            "X-Response-Time",
        ],
    )

    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestContextMiddleware)

    # Routers
    app.include_router(auth_router, prefix="/api")
    app.include_router(signals_router, prefix="/api")
    app.include_router(alerts_router, prefix="/api")
    app.include_router(status_router, prefix="/api")
    app.include_router(admin_router, prefix="/api")

    @app.websocket("/ws/signals")
    async def ws_signals(
        websocket: WebSocket,
        token: str = Query(..., description="JWT access token"),
    ):
        await websocket_endpoint(websocket, token)

    @app.get("/health", response_model=HealthResponse)
    async def health():
        """Deep health check with dependency status"""
        uptime = int((datetime.now(timezone.utc) - _start_time).total_seconds())
        checks: dict = {}

        with _engine_lock:
            engine_ok = _scanner_engine is not None
        checks["scanner_engine"] = "ok" if engine_ok else "unavailable"

        ws_stats = manager.get_stats()
        checks["websocket"] = "ok"
        checks["websocket_connections"] = ws_stats.get("total_connections", 0)

        overall = "healthy" if engine_ok else "degraded"

        return HealthResponse(
            status=overall,
            service="scanify-api",
            version=version,
            uptime_seconds=uptime,
            timestamp=datetime.now(timezone.utc).isoformat(),
            checks=checks,
        )

    @app.get("/readiness")
    async def readiness():
        """Readiness probe — returns 503 until scanner engine is attached"""
        with _engine_lock:
            ready = _scanner_engine is not None
        if not ready:
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready"},
            )
        return {"status": "ready"}

    @app.get("/")
    async def root():
        return JSONResponse(
            content={
                "message": "Welcome to Scanify API",
                "docs": "/api/docs",
                "health": "/health",
                "version": version,
            }
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        rid = request_id_var.get("-")
        logger.exception("Unhandled exception [request_id=%s]", rid)
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_server_error",
                "detail": str(exc) if debug else "An unexpected error occurred",
                "request_id": rid,
            },
            headers={"X-Request-ID": rid},
        )

    return app


app = create_app(
    debug=os.getenv("SCANIFY_DEBUG", "false").lower() == "true",
)
