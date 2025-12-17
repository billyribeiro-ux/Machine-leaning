"""
Scanify API - Main Application

Production-ready FastAPI application with:
- REST API endpoints for signals, alerts, and status
- WebSocket real-time streaming
- JWT authentication with tier-based access
- Rate limiting middleware
- CORS configuration
"""

import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from src.api.routes import (
    signals_router,
    alerts_router,
    auth_router,
    status_router,
    admin_router,
)
from src.api.websocket.handlers import manager, websocket_endpoint
from src.api.middleware.rate_limit import RateLimitMiddleware


# Scanner engine reference (set externally)
_scanner_engine = None


def set_scanner_engine(engine):
    """Set the scanner engine for API access"""
    global _scanner_engine
    _scanner_engine = engine

    # Propagate to modules
    from src.api.routes import signals, alerts, status, admin
    from src.api.websocket import handlers

    signals.set_scanner_engine(engine)
    alerts.set_scanner_engine(engine)
    status.set_scanner_engine(engine)
    admin.set_scanner_engine(engine)
    handlers.manager.set_scanner_engine(engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    # Startup
    print("🚀 Scanify API starting...")

    # Start WebSocket heartbeat
    await manager.start_heartbeat(interval=30)

    # Initialize scanner if configured
    if _scanner_engine:
        print("📡 Scanner engine connected")

    yield

    # Shutdown
    print("👋 Scanify API shutting down...")


def create_app(
    title: str = "Scanify API",
    version: str = "1.0.0",
    debug: bool = False,
) -> FastAPI:
    """
    Create and configure the FastAPI application.

    Args:
        title: API title for documentation
        version: API version
        debug: Enable debug mode

    Returns:
        Configured FastAPI application
    """

    app = FastAPI(
        title=title,
        description="""
# Scanify Trading Scanner API

Real-time trading signals and alerts powered by ML.

## Features

- **Real-time Signals**: Get trading signals from multiple scanners
- **WebSocket Streaming**: Live signal updates for PRO+ tiers
- **Alert Management**: Custom alerts and notifications
- **Tier-based Access**: Different features per subscription level

## Authentication

All protected endpoints require a Bearer token in the Authorization header:

```
Authorization: Bearer <your_jwt_token>
```

## Rate Limits

| Tier | Requests/Hour | WebSocket |
|------|--------------|-----------|
| Free | 60 | ❌ |
| Basic | 500 | ❌ |
| Pro | 5,000 | ✅ |
| Elite | 50,000 | ✅ |

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

    # CORS configuration
    allowed_origins = os.getenv("SCANIFY_CORS_ORIGINS", "").split(",")
    if not allowed_origins or allowed_origins == [""]:
        allowed_origins = [
            "http://localhost:3000",      # Next.js dev
            "http://localhost:5173",      # Vite dev
            "http://localhost:1420",      # Tauri dev
            "https://scanify.app",        # Production
            "https://www.scanify.app",
            "tauri://localhost",          # Tauri production
        ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-RateLimit-Remaining", "X-RateLimit-Reset"],
    )

    # GZip compression
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # Rate limiting
    app.add_middleware(RateLimitMiddleware)

    # Register routers
    app.include_router(auth_router, prefix="/api")
    app.include_router(signals_router, prefix="/api")
    app.include_router(alerts_router, prefix="/api")
    app.include_router(status_router, prefix="/api")
    app.include_router(admin_router, prefix="/api")

    # WebSocket endpoint
    @app.websocket("/ws/signals")
    async def ws_signals(
        websocket: WebSocket,
        token: str = Query(..., description="JWT access token"),
    ):
        """
        WebSocket endpoint for real-time signal streaming.

        Requires PRO tier or higher.
        """
        await websocket_endpoint(websocket, token)

    # Health check (outside /api prefix for load balancers)
    @app.get("/health")
    async def health():
        """Basic health check"""
        return {"status": "healthy", "service": "scanify-api"}

    # Root redirect
    @app.get("/")
    async def root():
        """API root - redirect to docs"""
        return JSONResponse(
            content={
                "message": "Welcome to Scanify API",
                "docs": "/api/docs",
                "health": "/health",
                "version": version,
            }
        )

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "detail": str(exc) if debug else "An unexpected error occurred",
            },
        )

    return app


# Default app instance
app = create_app(
    debug=os.getenv("SCANIFY_DEBUG", "false").lower() == "true",
)
