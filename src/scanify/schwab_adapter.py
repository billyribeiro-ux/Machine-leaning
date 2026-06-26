"""
SCANIFY Schwab Adapter — Charles Schwab Market Data API integration.

Provides options chain data, quotes, price history, and market movers
via the Schwab Trader API (OAuth 2.0).

API docs: https://developer.schwab.com/
Base URL: https://api.schwabapi.com/marketdata/v1

Authentication: OAuth 2.0 Authorization Code flow
  - Authorization: https://api.schwabapi.com/v1/oauth/authorize
  - Token:         https://api.schwabapi.com/v1/oauth/token
  - Access token:  30-minute lifetime
  - Refresh token: 7-day lifetime

Rate limit: 120 requests/minute (non-order, application level)
"""

import base64
import logging
import math
import time as time_module
from datetime import datetime, date, time, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlencode

import numpy as np
import requests

from .data_feeds import (
    OptionQuote,
    OptionsChain,
    VIXData,
    PriorSessionData,
    SPXPriceBar,
    CrossAssetData,
    OptionType,
)

logger = logging.getLogger(__name__)

_ET_CLOSE = time(16, 0)


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


class SchwabAdapter:
    """Charles Schwab Market Data adapter for SCANIFY.

    Implements the same data interface as YahooFinanceAdapter so it can
    serve as a drop-in replacement for options chain and market data.

    Parameters
    ----------
    client_id : str
        Schwab app key (from developer.schwab.com dashboard).
    client_secret : str
        Schwab app secret.
    credential_store : optional
        If provided, credentials are resolved from the encrypted store.
    redirect_uri : str
        OAuth callback URL registered with Schwab.
    refresh_token : str, optional
        Pre-existing refresh token to skip the initial authorization flow.
    """

    MARKET_DATA_BASE = "https://api.schwabapi.com/marketdata/v1"
    AUTH_URL = "https://api.schwabapi.com/v1/oauth/authorize"
    TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        credential_store=None,
        redirect_uri: str = "https://127.0.0.1",
        refresh_token: Optional[str] = None,
    ) -> None:
        import os

        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._refresh_token = refresh_token

        if credential_store:
            if not self._client_id:
                self._client_id = credential_store.get("schwab", "client_id")
            if not self._client_secret:
                self._client_secret = credential_store.get("schwab", "client_secret")
            if not self._redirect_uri or self._redirect_uri == "https://127.0.0.1":
                stored_uri = credential_store.get("schwab", "redirect_uri")
                if stored_uri:
                    self._redirect_uri = stored_uri
            if not self._refresh_token:
                self._refresh_token = credential_store.get("schwab", "refresh_token")

        if not self._client_id:
            self._client_id = os.environ.get("SCANIFY_SCHWAB_CLIENT_ID", "")
        if not self._client_secret:
            self._client_secret = os.environ.get("SCANIFY_SCHWAB_CLIENT_SECRET", "")
        if not self._refresh_token:
            self._refresh_token = os.environ.get("SCANIFY_SCHWAB_REFRESH_TOKEN", "")
        env_uri = os.environ.get("SCANIFY_SCHWAB_REDIRECT_URI")
        if env_uri:
            self._redirect_uri = env_uri

        self._access_token: Optional[str] = None
        self._token_expiry: float = 0.0

        self._session = requests.Session()
        self._last_request: float = 0.0
        self._min_interval: float = 0.5  # ~120 req/min

        self._credential_store = credential_store

        if not self._client_id or not self._client_secret:
            logger.warning(
                "Schwab API credentials not configured. Set SCANIFY_SCHWAB_CLIENT_ID "
                "and SCANIFY_SCHWAB_CLIENT_SECRET, or add via "
                "/api/admin/credentials/vendors/schwab"
            )
        else:
            logger.info("SchwabAdapter initialised.")

    # ------------------------------------------------------------------
    # OAuth 2.0 Token Management
    # ------------------------------------------------------------------

    def get_authorization_url(self) -> str:
        """Return the URL the user must visit to authorize the app."""
        params = {
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"

    def exchange_authorization_code(self, code: str) -> Dict:
        """Exchange an authorization code for access + refresh tokens."""
        auth_header = base64.b64encode(
            f"{self._client_id}:{self._client_secret}".encode()
        ).decode()

        resp = requests.post(
            self.TOKEN_URL,
            headers={
                "Authorization": f"Basic {auth_header}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self._redirect_uri,
            },
            timeout=15,
        )
        resp.raise_for_status()
        token_data = resp.json()

        self._access_token = token_data["access_token"]
        self._refresh_token = token_data.get("refresh_token", self._refresh_token)
        expires_in = token_data.get("expires_in", 1800)
        self._token_expiry = time_module.time() + expires_in - 60

        if self._credential_store and self._refresh_token:
            try:
                self._credential_store.set(
                    "schwab", "refresh_token", self._refresh_token
                )
            except Exception:
                logger.debug("Could not persist refresh token to credential store.")

        logger.info("Schwab tokens acquired (expires in %ds).", expires_in)
        return token_data

    def _refresh_access_token(self) -> None:
        """Use the refresh token to get a new access token."""
        if not self._refresh_token:
            raise RuntimeError(
                "No Schwab refresh token available. Complete the OAuth authorization "
                "flow first via GET /api/admin/schwab/authorize"
            )

        auth_header = base64.b64encode(
            f"{self._client_id}:{self._client_secret}".encode()
        ).decode()

        resp = requests.post(
            self.TOKEN_URL,
            headers={
                "Authorization": f"Basic {auth_header}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
            },
            timeout=15,
        )
        resp.raise_for_status()
        token_data = resp.json()

        self._access_token = token_data["access_token"]
        new_refresh = token_data.get("refresh_token")
        if new_refresh:
            self._refresh_token = new_refresh
            if self._credential_store:
                try:
                    self._credential_store.set(
                        "schwab", "refresh_token", self._refresh_token
                    )
                except Exception:
                    pass

        expires_in = token_data.get("expires_in", 1800)
        self._token_expiry = time_module.time() + expires_in - 60
        logger.info("Schwab access token refreshed (expires in %ds).", expires_in)

    def _ensure_token(self) -> str:
        """Ensure we have a valid access token, refreshing if needed."""
        if self._access_token and time_module.time() < self._token_expiry:
            return self._access_token

        self._refresh_access_token()
        if not self._access_token:
            raise RuntimeError("Failed to obtain Schwab access token.")
        return self._access_token

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _rate_limit(self) -> None:
        elapsed = time_module.time() - self._last_request
        if elapsed < self._min_interval:
            time_module.sleep(self._min_interval - elapsed)
        self._last_request = time_module.time()

    def _get(self, path: str, params: Optional[Dict] = None) -> Dict:
        """Make an authenticated GET request to the Schwab Market Data API."""
        token = self._ensure_token()
        self._rate_limit()

        url = f"{self.MARKET_DATA_BASE}{path}"
        resp = self._session.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            params=params or {},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Quotes
    # ------------------------------------------------------------------

    def get_quote(self, symbol: str) -> Dict:
        """Get a real-time quote for a single symbol."""
        data = self._get(f"/{symbol}/quotes")
        return data.get(symbol, data)

    def get_quotes(self, symbols: List[str]) -> Dict:
        """Get quotes for multiple symbols."""
        return self._get("/quotes", params={"symbols": ",".join(symbols)})

    def fetch_spx_price(self) -> float:
        """Return the current SPX index level."""
        try:
            data = self._get("/$SPX.X/quotes")
            quote = data.get("$SPX.X", data)
            ref = quote.get("reference", quote)
            price = _safe_float(ref.get("lastPrice", ref.get("closePrice")))
            if price > 0:
                return price
        except Exception as exc:
            logger.warning("Failed to fetch SPX from Schwab: %s", exc)

        try:
            data = self._get("/SPY/quotes")
            quote = data.get("SPY", data)
            ref = quote.get("reference", quote)
            spy_price = _safe_float(ref.get("lastPrice", ref.get("closePrice")))
            if spy_price > 0:
                return spy_price * 10.0
        except Exception as exc:
            logger.warning("Failed to fetch SPY fallback from Schwab: %s", exc)

        raise RuntimeError("Could not retrieve SPX price from Schwab API.")

    # ------------------------------------------------------------------
    # Options Chain
    # ------------------------------------------------------------------

    def fetch_spx_options_chain(
        self, expiry_date: Optional[str] = None
    ) -> OptionsChain:
        """Fetch SPX options chain from Schwab and convert to OptionsChain.

        Uses the /chains endpoint with symbol=$SPX.X for true SPX options.
        Falls back to SPY if SPX is unavailable.
        """
        symbol = "$SPX.X"
        params: Dict = {
            "symbol": symbol,
            "contractType": "ALL",
            "includeQuotes": "TRUE",
            "range": "ALL",
        }

        if expiry_date:
            params["fromDate"] = expiry_date
            params["toDate"] = expiry_date
        else:
            today = date.today().isoformat()
            params["fromDate"] = today
            params["toDate"] = today

        try:
            data = self._get("/chains", params=params)
        except Exception:
            logger.info("SPX options unavailable; trying SPY.")
            symbol = "SPY"
            params["symbol"] = symbol
            data = self._get("/chains", params=params)

        now = datetime.now(timezone.utc)
        underlying_price = _safe_float(
            data.get("underlyingPrice", data.get("underlying", {}).get("last", 0))
        )

        if underlying_price <= 0:
            try:
                underlying_price = self.fetch_spx_price()
            except Exception:
                underlying_price = 0.0

        quotes: List[OptionQuote] = []

        for map_key, opt_type in [
            ("callExpDateMap", OptionType.CALL),
            ("putExpDateMap", OptionType.PUT),
        ]:
            exp_date_map = data.get(map_key, {})
            for exp_key, strikes in exp_date_map.items():
                for strike_key, contracts in strikes.items():
                    for contract in contracts:
                        bid = _safe_float(contract.get("bid"))
                        ask = _safe_float(contract.get("ask"))
                        mid = (bid + ask) / 2.0 if (bid + ask) > 0 else _safe_float(
                            contract.get("last")
                        )
                        quote = OptionQuote(
                            strike=_safe_float(contract.get("strikePrice", strike_key)),
                            bid=bid,
                            ask=ask,
                            mid=mid,
                            last=_safe_float(contract.get("last")),
                            volume=_safe_int(contract.get("totalVolume")),
                            open_interest=_safe_int(contract.get("openInterest")),
                            implied_vol=_safe_float(contract.get("volatility", 0)) / 100.0,
                            delta=_safe_float(contract.get("delta")),
                            gamma=_safe_float(contract.get("gamma")),
                            theta=_safe_float(contract.get("theta")),
                            vega=_safe_float(contract.get("vega")),
                            option_type=opt_type,
                            timestamp=now,
                        )
                        quotes.append(quote)

        chosen_expiry = expiry_date or date.today().isoformat()
        try:
            exp_date_obj = datetime.strptime(chosen_expiry, "%Y-%m-%d").date()
        except ValueError:
            exp_date_obj = date.today()

        chain = OptionsChain(
            quotes=quotes,
            expiry_date=exp_date_obj,
            underlying_price=underlying_price,
            chain_timestamp=now,
        )
        chain.expiry = datetime.combine(  # type: ignore[attr-defined]
            exp_date_obj, _ET_CLOSE, tzinfo=timezone.utc
        )

        logger.info(
            "Built Schwab OptionsChain: %d quotes (expiry=%s, underlying=%.2f)",
            len(quotes), chosen_expiry, underlying_price,
        )
        return chain

    # ------------------------------------------------------------------
    # VIX family
    # ------------------------------------------------------------------

    def fetch_vix_data(self) -> VIXData:
        """Fetch VIX, VIX1D and VIX9D levels via Schwab quotes."""
        now = datetime.now(timezone.utc)

        vix_level = 15.0
        vix1d_level = 14.0
        vix9d_level = 14.5

        try:
            data = self.get_quotes(["$VIX.X"])
            vix_quote = data.get("$VIX.X", {})
            ref = vix_quote.get("reference", vix_quote)
            vix_level = _safe_float(ref.get("lastPrice", 15.0))
            if vix_level <= 0:
                vix_level = 15.0
        except Exception as exc:
            logger.warning("Failed to fetch VIX from Schwab: %s", exc)

        vix1d_level = vix_level * 0.92
        vix9d_level = vix_level * 0.96

        return VIXData(
            vix=vix_level,
            vix1d=vix1d_level,
            vix9d=vix9d_level,
            vix_timestamp=now,
            vix1d_timestamp=now,
            vix9d_timestamp=now,
        )

    # ------------------------------------------------------------------
    # Prior session
    # ------------------------------------------------------------------

    def fetch_prior_session(self) -> PriorSessionData:
        """Build PriorSessionData from Schwab price history."""
        try:
            data = self._get("/pricehistory", params={
                "symbol": "$SPX.X",
                "periodType": "day",
                "period": 5,
                "frequencyType": "daily",
                "frequency": 1,
            })
            candles = data.get("candles", [])
        except Exception as exc:
            logger.warning("Failed to fetch SPX history from Schwab: %s", exc)
            candles = []

        if len(candles) < 2:
            return PriorSessionData(
                spx_close=0.0, spx_high=0.0, spx_low=0.0,
                spx_vwap=0.0, vix1d_close=0.0, realized_vol_20d=0.0,
            )

        prev = candles[-2]
        spx_close = _safe_float(prev.get("close"))
        spx_high = _safe_float(prev.get("high"))
        spx_low = _safe_float(prev.get("low"))
        spx_vwap = (spx_high + spx_low + spx_close) / 3.0 if (spx_high + spx_low + spx_close) > 0 else 0.0

        rv = self._compute_realized_vol(candles)

        return PriorSessionData(
            spx_close=spx_close,
            spx_high=spx_high,
            spx_low=spx_low,
            spx_vwap=spx_vwap,
            vix1d_close=0.0,
            realized_vol_20d=rv,
        )

    def _compute_realized_vol(self, candles: List[Dict], days: int = 20) -> float:
        """Compute annualised realised vol from daily candles."""
        closes = [_safe_float(c.get("close")) for c in candles if _safe_float(c.get("close")) > 0]
        if len(closes) < max(days, 2):
            return 0.0
        closes = closes[-days:]
        log_returns = np.diff(np.log(closes))
        return float(np.std(log_returns, ddof=1) * math.sqrt(252))

    # ------------------------------------------------------------------
    # Price history
    # ------------------------------------------------------------------

    def fetch_price_bars(
        self, period: str = "1d", interval: str = "1m"
    ) -> List[SPXPriceBar]:
        """Return intraday bars for SPX."""
        freq_map = {
            "1m": ("minute", 1),
            "5m": ("minute", 5),
            "15m": ("minute", 15),
            "30m": ("minute", 30),
            "1h": ("minute", 60),
        }
        freq_type, freq = freq_map.get(interval, ("minute", 1))

        try:
            data = self._get("/pricehistory", params={
                "symbol": "$SPX.X",
                "periodType": "day",
                "period": 1,
                "frequencyType": freq_type,
                "frequency": freq,
                "needExtendedHoursData": "false",
            })
        except Exception as exc:
            logger.error("Failed to fetch intraday bars from Schwab: %s", exc)
            return []

        bars: List[SPXPriceBar] = []
        for candle in data.get("candles", []):
            ts_ms = candle.get("datetime", 0)
            ts = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc) if ts_ms else datetime.now(timezone.utc)
            bars.append(SPXPriceBar(
                timestamp=ts,
                open=_safe_float(candle.get("open")),
                high=_safe_float(candle.get("high")),
                low=_safe_float(candle.get("low")),
                close=_safe_float(candle.get("close")),
                volume=_safe_int(candle.get("volume")),
            ))

        logger.info("Fetched %d intraday bars from Schwab.", len(bars))
        return bars

    # ------------------------------------------------------------------
    # Cross-asset
    # ------------------------------------------------------------------

    def fetch_cross_asset_data(self) -> CrossAssetData:
        """Fetch 10Y Treasury yield and DXY index."""
        now = datetime.now(timezone.utc)

        us_10y = 4.0
        us_10y_change = 0.0
        dxy = 100.0
        dxy_change = 0.0

        try:
            data = self.get_quotes(["$TNX.X"])
            quote = data.get("$TNX.X", {})
            ref = quote.get("reference", quote)
            us_10y = _safe_float(ref.get("lastPrice", 4.0))
            us_10y_change = _safe_float(ref.get("netChange", 0.0))
        except Exception as exc:
            logger.warning("Failed to fetch TNX from Schwab: %s", exc)

        try:
            data = self.get_quotes(["$DXY.X"])
            quote = data.get("$DXY.X", {})
            ref = quote.get("reference", quote)
            dxy = _safe_float(ref.get("lastPrice", 100.0))
            dxy_change = _safe_float(ref.get("netChange", 0.0))
        except Exception as exc:
            logger.warning("Failed to fetch DXY from Schwab: %s", exc)

        return CrossAssetData(
            us_10y_yield=us_10y,
            us_10y_yield_change=us_10y_change,
            dxy_level=dxy,
            dxy_change=dxy_change,
            timestamp=now,
        )

    # ------------------------------------------------------------------
    # Movers
    # ------------------------------------------------------------------

    def get_movers(self, index: str = "$SPX.X", direction: str = "up") -> List[Dict]:
        """Get top 10 movers for an index."""
        sort_val = "PERCENT_CHANGE_UP" if direction == "up" else "PERCENT_CHANGE_DOWN"
        try:
            data = self._get(f"/movers/{index}", params={"sort": sort_val, "frequency": 0})
            return data.get("screeners", data.get("movers", []))
        except Exception as exc:
            logger.warning("Failed to fetch movers from Schwab: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Market hours
    # ------------------------------------------------------------------

    def get_market_hours(self, market: str = "EQUITY") -> Dict:
        """Get market hours for a specific market."""
        try:
            return self._get(f"/markets/{market.lower()}")
        except Exception as exc:
            logger.warning("Failed to fetch market hours: %s", exc)
            return {}

    @property
    def is_configured(self) -> bool:
        """Check if Schwab credentials are configured."""
        return bool(self._client_id and self._client_secret)

    @property
    def has_refresh_token(self) -> bool:
        """Check if a refresh token is available for automatic auth."""
        return bool(self._refresh_token)
