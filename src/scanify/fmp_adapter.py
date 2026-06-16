"""
SCANIFY FMP Adapter — Financial Modeling Prep equity data integration.

FMP provides comprehensive equity market data via REST API:
  - Real-time and historical stock quotes
  - Company financials (income, balance sheet, cash flow)
  - Market indices and sector performance
  - Gainers / losers / most active
  - Economic calendar and earnings
  - Technical indicators
  - Institutional holdings (13F)

All endpoints require an API key passed as ``?apikey=...`` query param.
Free tier: 250 requests/day. Paid tiers: higher limits + real-time.

API docs: https://site.financialmodelingprep.com/developer/docs
"""

import logging
import math
import time as time_module
from datetime import datetime, date, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import requests

from .data_feeds import (
    PriorSessionData,
    SPXPriceBar,
    CrossAssetData,
    VIXData,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default: int = 0) -> int:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# FMP Adapter
# ---------------------------------------------------------------------------

class FMPAdapter:
    """Financial Modeling Prep equity data adapter.

    Parameters
    ----------
    api_key : str
        FMP API key. Can also be set via ``SCANIFY_FMP_API_KEY`` env var.
    credential_store : optional
        If provided, the API key is resolved from the credential store.
    """

    BASE_URL = "https://financialmodelingprep.com/api"

    def __init__(
        self,
        api_key: Optional[str] = None,
        credential_store=None,
    ) -> None:
        import os

        self._api_key = api_key
        if not self._api_key and credential_store:
            self._api_key = credential_store.get("fmp", "api_key")
        if not self._api_key:
            self._api_key = os.environ.get("SCANIFY_FMP_API_KEY", "")

        if not self._api_key:
            logger.warning(
                "FMP API key not configured. Set SCANIFY_FMP_API_KEY or add via "
                "/api/admin/credentials/vendors/fmp"
            )

        self._session = requests.Session()
        self._last_request: float = 0.0
        self._min_interval: float = 0.2

        logger.info("FMPAdapter initialised.")

    # ------------------------------------------------------------------
    # Internal request helper
    # ------------------------------------------------------------------

    def _get(self, path: str, params: Optional[Dict] = None, version: str = "v3") -> any:
        """Rate-limited GET request to FMP API."""
        elapsed = time_module.time() - self._last_request
        if elapsed < self._min_interval:
            time_module.sleep(self._min_interval - elapsed)

        url = f"{self.BASE_URL}/{version}/{path}"
        req_params = {"apikey": self._api_key}
        if params:
            req_params.update(params)

        self._last_request = time_module.time()
        resp = self._session.get(url, params=req_params, timeout=15)
        resp.raise_for_status()
        return resp.json()

    # ==================================================================
    # Quote / Price
    # ==================================================================

    def get_quote(self, symbol: str = "^GSPC") -> Dict:
        """Real-time quote for a symbol.

        Returns full quote dict with price, change, volume, market cap, etc.
        """
        data = self._get(f"quote/{symbol}")
        if isinstance(data, list) and data:
            return data[0]
        return data if isinstance(data, dict) else {}

    def get_spx_price(self) -> float:
        """Current S&P 500 index level."""
        quote = self.get_quote("^GSPC")
        price = _safe_float(quote.get("price"))
        if price <= 0:
            raise RuntimeError("FMP returned zero/invalid SPX price")
        return price

    def get_stock_quote(self, symbol: str) -> Dict:
        """Full quote for any stock/ETF symbol."""
        return self.get_quote(symbol)

    def get_batch_quotes(self, symbols: List[str]) -> List[Dict]:
        """Batch quotes for multiple symbols in a single request."""
        joined = ",".join(symbols)
        data = self._get(f"quote/{joined}")
        return data if isinstance(data, list) else [data]

    # ==================================================================
    # Historical Price Data
    # ==================================================================

    def get_historical_daily(
        self,
        symbol: str = "^GSPC",
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: int = 30,
    ) -> List[Dict]:
        """Daily OHLCV bars.

        Parameters
        ----------
        symbol : str
        from_date : str, optional — YYYY-MM-DD
        to_date : str, optional — YYYY-MM-DD
        limit : int — max bars (FMP default 1 year if no dates)
        """
        params = {}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date

        data = self._get(f"historical-price-full/{symbol}", params=params)
        bars = data.get("historical", []) if isinstance(data, dict) else []
        return bars[:limit]

    def get_intraday_bars(
        self,
        symbol: str = "^GSPC",
        interval: str = "1min",
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> List[Dict]:
        """Intraday OHLCV bars (1min, 5min, 15min, 30min, 1hour, 4hour).

        Parameters
        ----------
        interval : str — one of "1min", "5min", "15min", "30min", "1hour", "4hour"
        """
        params = {}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date

        data = self._get(f"historical-chart/{interval}/{symbol}", params=params)
        return data if isinstance(data, list) else []

    def fetch_price_bars(
        self,
        symbol: str = "^GSPC",
        interval: str = "1min",
    ) -> List[SPXPriceBar]:
        """Fetch intraday bars and convert to SCANIFY SPXPriceBar format."""
        raw = self.get_intraday_bars(symbol=symbol, interval=interval)
        bars: List[SPXPriceBar] = []
        for r in raw:
            try:
                ts = datetime.strptime(r.get("date", ""), "%Y-%m-%d %H:%M:%S")
                ts = ts.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                ts = datetime.now(timezone.utc)
            bars.append(SPXPriceBar(
                timestamp=ts,
                open=_safe_float(r.get("open")),
                high=_safe_float(r.get("high")),
                low=_safe_float(r.get("low")),
                close=_safe_float(r.get("close")),
                volume=_safe_int(r.get("volume")),
            ))
        bars.sort(key=lambda b: b.timestamp)
        return bars

    # ==================================================================
    # Prior Session
    # ==================================================================

    def fetch_prior_session(self, symbol: str = "^GSPC") -> PriorSessionData:
        """Build PriorSessionData from FMP daily bars."""
        bars = self.get_historical_daily(symbol=symbol, limit=5)
        if len(bars) < 2:
            logger.warning("Insufficient daily bars from FMP for prior session.")
            return PriorSessionData(
                spx_close=0.0, spx_high=0.0, spx_low=0.0,
                spx_vwap=0.0, vix1d_close=0.0, realized_vol_20d=0.0,
            )

        prev = bars[1]  # FMP returns newest first
        spx_close = _safe_float(prev.get("close"))
        spx_high = _safe_float(prev.get("high"))
        spx_low = _safe_float(prev.get("low"))
        spx_vwap = round((spx_high + spx_low + spx_close) / 3.0, 2)

        rv = self.compute_realized_vol(symbol=symbol, days=20)

        return PriorSessionData(
            spx_close=spx_close,
            spx_high=spx_high,
            spx_low=spx_low,
            spx_vwap=spx_vwap,
            vix1d_close=0.0,
            realized_vol_20d=rv,
        )

    # ==================================================================
    # VIX Data
    # ==================================================================

    def fetch_vix_data(self) -> VIXData:
        """Fetch VIX family data from FMP."""
        now = datetime.now(timezone.utc)
        vix = _safe_float(self.get_quote("^VIX").get("price"), 15.0)

        try:
            vix1d = _safe_float(self.get_quote("^VIX1D").get("price"))
            if vix1d <= 0:
                vix1d = vix * 0.92
        except Exception:
            vix1d = vix * 0.92

        try:
            vix9d = _safe_float(self.get_quote("^VIX9D").get("price"))
            if vix9d <= 0:
                vix9d = vix * 0.96
        except Exception:
            vix9d = vix * 0.96

        return VIXData(
            vix=vix, vix1d=vix1d, vix9d=vix9d,
            vix_timestamp=now, vix1d_timestamp=now, vix9d_timestamp=now,
        )

    # ==================================================================
    # Cross-Asset
    # ==================================================================

    def fetch_cross_asset_data(self) -> CrossAssetData:
        """Fetch 10Y yield and DXY from FMP."""
        now = datetime.now(timezone.utc)

        tnx = self.get_quote("^TNX")
        us_10y = _safe_float(tnx.get("price"), 4.0)
        us_10y_change = _safe_float(tnx.get("change"))

        dxy = self.get_quote("DX-Y.NYB")
        dxy_level = _safe_float(dxy.get("price"), 100.0)
        dxy_change = _safe_float(dxy.get("changesPercentage"))

        return CrossAssetData(
            us_10y_yield=us_10y,
            us_10y_yield_change=us_10y_change,
            dxy_level=dxy_level,
            dxy_change=dxy_change,
            timestamp=now,
        )

    # ==================================================================
    # Realized Volatility
    # ==================================================================

    def compute_realized_vol(self, symbol: str = "^GSPC", days: int = 20) -> float:
        """Annualized realized vol from daily closes."""
        bars = self.get_historical_daily(symbol=symbol, limit=days + 5)
        if len(bars) < days:
            return 0.0
        closes = [_safe_float(b.get("close")) for b in bars[:days]]
        closes = [c for c in closes if c > 0]
        if len(closes) < 2:
            return 0.0
        closes.reverse()
        log_returns = np.diff(np.log(closes))
        return float(np.std(log_returns, ddof=1) * math.sqrt(252))

    # ==================================================================
    # Market Movers
    # ==================================================================

    def get_gainers(self) -> List[Dict]:
        """Top gainers in the market."""
        return self._get("stock_market/gainers")

    def get_losers(self) -> List[Dict]:
        """Top losers in the market."""
        return self._get("stock_market/losers")

    def get_most_active(self) -> List[Dict]:
        """Most actively traded stocks."""
        return self._get("stock_market/actives")

    # ==================================================================
    # Sector Performance
    # ==================================================================

    def get_sector_performance(self) -> List[Dict]:
        """Current sector performance breakdown."""
        return self._get("sector-performance")

    def get_historical_sector_performance(self, limit: int = 30) -> List[Dict]:
        """Historical sector performance."""
        return self._get("historical-sectors-performance", params={"limit": str(limit)})

    # ==================================================================
    # Company Financials
    # ==================================================================

    def get_company_profile(self, symbol: str) -> Dict:
        """Company profile (description, sector, industry, market cap, etc.)."""
        data = self._get(f"profile/{symbol}")
        if isinstance(data, list) and data:
            return data[0]
        return data if isinstance(data, dict) else {}

    def get_income_statement(self, symbol: str, period: str = "annual", limit: int = 5) -> List[Dict]:
        """Income statements (annual or quarterly)."""
        return self._get(f"income-statement/{symbol}", params={"period": period, "limit": str(limit)})

    def get_balance_sheet(self, symbol: str, period: str = "annual", limit: int = 5) -> List[Dict]:
        """Balance sheet statements."""
        return self._get(f"balance-sheet-statement/{symbol}", params={"period": period, "limit": str(limit)})

    def get_cash_flow(self, symbol: str, period: str = "annual", limit: int = 5) -> List[Dict]:
        """Cash flow statements."""
        return self._get(f"cash-flow-statement/{symbol}", params={"period": period, "limit": str(limit)})

    def get_key_metrics(self, symbol: str, period: str = "annual", limit: int = 5) -> List[Dict]:
        """Key financial metrics (PE, PB, EV/EBITDA, etc.)."""
        return self._get(f"key-metrics/{symbol}", params={"period": period, "limit": str(limit)})

    def get_ratios(self, symbol: str, period: str = "annual", limit: int = 5) -> List[Dict]:
        """Financial ratios (profitability, liquidity, leverage, efficiency)."""
        return self._get(f"ratios/{symbol}", params={"period": period, "limit": str(limit)})

    def get_dcf(self, symbol: str) -> Dict:
        """Discounted cash flow valuation."""
        data = self._get(f"discounted-cash-flow/{symbol}")
        if isinstance(data, list) and data:
            return data[0]
        return data if isinstance(data, dict) else {}

    # ==================================================================
    # Technical Indicators
    # ==================================================================

    def get_technical_indicator(
        self,
        symbol: str,
        indicator: str = "sma",
        period: int = 20,
        interval: str = "daily",
    ) -> List[Dict]:
        """Technical indicator data (SMA, EMA, RSI, MACD, etc.).

        Parameters
        ----------
        indicator : str — sma, ema, rsi, macd, adx, williams, stochastic, etc.
        period : int — lookback period
        interval : str — "daily", "1min", "5min", "15min", "30min", "1hour", "4hour"
        """
        return self._get(
            f"technical_indicator/{interval}/{symbol}",
            params={"period": str(period), "type": indicator},
        )

    # ==================================================================
    # Earnings & Economic Calendar
    # ==================================================================

    def get_earnings_calendar(
        self,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> List[Dict]:
        """Upcoming earnings announcements."""
        params = {}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        return self._get("earning_calendar", params=params)

    def get_economic_calendar(
        self,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> List[Dict]:
        """Economic events calendar (CPI, FOMC, NFP, etc.)."""
        params = {}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        return self._get("economic_calendar", params=params)

    # ==================================================================
    # Institutional Holdings (13F via FMP)
    # ==================================================================

    def get_institutional_holders(self, symbol: str) -> List[Dict]:
        """Institutional holders for a stock (from 13F filings)."""
        return self._get(f"institutional-holder/{symbol}")

    def get_mutual_fund_holders(self, symbol: str) -> List[Dict]:
        """Mutual fund holders for a stock."""
        return self._get(f"mutual-fund-holder/{symbol}")

    def get_etf_holders(self, symbol: str) -> List[Dict]:
        """ETF holders for a stock."""
        return self._get(f"etf-holder/{symbol}")

    # ==================================================================
    # Market Index Data
    # ==================================================================

    def get_index_quote(self, index: str = "^GSPC") -> Dict:
        """Quote for a market index."""
        return self.get_quote(index)

    def get_index_constituents(self, index: str = "sp500") -> List[Dict]:
        """Constituents of a market index (sp500, nasdaq, dowjones)."""
        return self._get(f"{index}_constituent")

    # ==================================================================
    # Screening
    # ==================================================================

    def stock_screener(
        self,
        market_cap_min: Optional[float] = None,
        market_cap_max: Optional[float] = None,
        sector: Optional[str] = None,
        industry: Optional[str] = None,
        beta_min: Optional[float] = None,
        beta_max: Optional[float] = None,
        dividend_min: Optional[float] = None,
        volume_min: Optional[int] = None,
        price_min: Optional[float] = None,
        price_max: Optional[float] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """Screen stocks by fundamental and market criteria."""
        params: Dict = {"limit": str(limit)}
        if market_cap_min is not None:
            params["marketCapMoreThan"] = str(int(market_cap_min))
        if market_cap_max is not None:
            params["marketCapLowerThan"] = str(int(market_cap_max))
        if sector:
            params["sector"] = sector
        if industry:
            params["industry"] = industry
        if beta_min is not None:
            params["betaMoreThan"] = str(beta_min)
        if beta_max is not None:
            params["betaLowerThan"] = str(beta_max)
        if dividend_min is not None:
            params["dividendMoreThan"] = str(dividend_min)
        if volume_min is not None:
            params["volumeMoreThan"] = str(volume_min)
        if price_min is not None:
            params["priceMoreThan"] = str(price_min)
        if price_max is not None:
            params["priceLowerThan"] = str(price_max)
        return self._get("stock-screener", params=params)


# ---------------------------------------------------------------------------
# Standalone Test
# ---------------------------------------------------------------------------

def run_fmp_test(api_key: Optional[str] = None) -> None:
    """Test FMP adapter with live data."""
    import os
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    key = api_key or os.environ.get("SCANIFY_FMP_API_KEY", "")
    if not key:
        print("Set SCANIFY_FMP_API_KEY env var or pass api_key argument.")
        return

    adapter = FMPAdapter(api_key=key)

    print("=" * 68)
    print("  SCANIFY — FMP Equity Data Test")
    print("=" * 68)

    print("\n[1] SPX Quote")
    try:
        quote = adapter.get_quote("^GSPC")
        print(f"  Price: {quote.get('price')}  Change: {quote.get('change')}  "
              f"Volume: {quote.get('volume')}")
    except Exception as exc:
        print(f"  ERROR: {exc}")

    print("\n[2] Batch Quotes (SPY, QQQ, IWM)")
    try:
        quotes = adapter.get_batch_quotes(["SPY", "QQQ", "IWM"])
        for q in quotes:
            print(f"  {q.get('symbol')}: ${q.get('price')}  ({q.get('changesPercentage'):+.2f}%)")
    except Exception as exc:
        print(f"  ERROR: {exc}")

    print("\n[3] VIX Data")
    try:
        vix = adapter.fetch_vix_data()
        print(f"  VIX={vix.vix:.2f}  VIX1D={vix.vix1d:.2f}  VIX9D={vix.vix9d:.2f}")
    except Exception as exc:
        print(f"  ERROR: {exc}")

    print("\n[4] Prior Session")
    try:
        prior = adapter.fetch_prior_session()
        print(f"  Close={prior.spx_close:.2f}  High={prior.spx_high:.2f}  "
              f"Low={prior.spx_low:.2f}  RV20d={prior.realized_vol_20d:.4f}")
    except Exception as exc:
        print(f"  ERROR: {exc}")

    print("\n[5] Cross-Asset")
    try:
        cross = adapter.fetch_cross_asset_data()
        print(f"  10Y={cross.us_10y_yield:.3f}%  DXY={cross.dxy_level:.2f}")
    except Exception as exc:
        print(f"  ERROR: {exc}")

    print("\n[6] Sector Performance")
    try:
        sectors = adapter.get_sector_performance()
        for s in sectors[:5]:
            print(f"  {s.get('sector', 'N/A'):<30s}  {s.get('changesPercentage', 'N/A')}")
    except Exception as exc:
        print(f"  ERROR: {exc}")

    print("\n[7] Gainers")
    try:
        gainers = adapter.get_gainers()
        for g in gainers[:5]:
            print(f"  {g.get('symbol'):<8s}  ${g.get('price'):>8.2f}  "
                  f"{g.get('changesPercentage', 0):+.2f}%")
    except Exception as exc:
        print(f"  ERROR: {exc}")

    print("\n[8] AAPL Company Profile")
    try:
        profile = adapter.get_company_profile("AAPL")
        print(f"  {profile.get('companyName')}  Mkt Cap: ${profile.get('mktCap', 0)/1e9:.0f}B  "
              f"Sector: {profile.get('sector')}")
    except Exception as exc:
        print(f"  ERROR: {exc}")

    print("\n" + "=" * 68)
    print("  FMP test complete.")
    print("=" * 68)


if __name__ == "__main__":
    run_fmp_test()
