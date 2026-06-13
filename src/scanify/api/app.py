"""
SCANIFY API — Main FastAPI application.

Mounts all routers and provides shared state (adapters, engines) via
app.state so endpoints avoid redundant instantiation.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from .options import router as options_router
from .equity_price import router as equity_price_router
from .equity_internals import router as equity_internals_router
from .equity_institutional import router as equity_institutional_router
from .equity_macro import router as equity_macro_router
from .admin_credentials import router as admin_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialise shared adapters on startup, tear down on shutdown."""
    from ..yahoo_adapter import YahooFinanceAdapter
    from ..edgar_adapter import EDGARAdapter
    from ..gex_engine import GEXEngine
    from ..config import GEXConfig
    from ..data_feeds import VIX1DAnalyzer
    from ..market_internals import MarketInternalsScorer
    from ..credentials import CredentialStore

    # Credential store (encrypted API key management)
    app.state.credential_store = CredentialStore()

    # Resolve vendor credentials for adapters
    store = app.state.credential_store
    edgar_ua = store.get("sec_edgar", "user_agent") or "ScanifyScanner admin@scanify.dev"

    app.state.yahoo = YahooFinanceAdapter()
    app.state.edgar = EDGARAdapter(user_agent=edgar_ua)
    app.state.gex_engine = GEXEngine(GEXConfig())
    app.state.vix1d_analyzer = VIX1DAnalyzer()
    app.state.internals_scorer = MarketInternalsScorer()

    yield


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    app = FastAPI(
        title="SCANIFY API",
        description=(
            "0DTE SPX Options Scanner & Gamma Exposure (GEX) API. "
            "Provides real-time options analytics, GEX computation, "
            "equity market data, institutional positioning, and "
            "cross-asset macro context."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    app.include_router(options_router)
    app.include_router(equity_price_router)
    app.include_router(equity_internals_router)
    app.include_router(equity_institutional_router)
    app.include_router(equity_macro_router)
    app.include_router(admin_router)

    @app.get("/", tags=["health"])
    async def root():
        return {
            "service": "SCANIFY API",
            "version": "1.0.0",
            "endpoints": {
                "options": "/api/options",
                "equity_price": "/api/equity/price",
                "equity_internals": "/api/equity/internals",
                "equity_institutional": "/api/equity/institutional",
                "equity_macro": "/api/equity/macro",
                "admin_credentials": "/api/admin/credentials",
            },
        }

    @app.get("/health", tags=["health"])
    async def health():
        return {"status": "ok"}

    return app
