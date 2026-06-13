"""
SCANIFY API — REST endpoints for Options and Equity data.

Routers:
    - options: GEX computation, signals, dashboard, expected move, chain analysis
    - equity_price: SPX/ES price data, intraday bars, VWAP, technicals
    - equity_internals: Market breadth scoring, composite direction signals
    - equity_institutional: SEC EDGAR 13F filings, institutional positioning
    - equity_macro: Cross-asset context (VIX, yields, DXY), vol regime
"""

from .app import create_app

__all__ = ["create_app"]
