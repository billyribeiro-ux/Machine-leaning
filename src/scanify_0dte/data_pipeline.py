"""
SCANIFY SPX 0DTE Options Day Trading Scanner - Real-Time Data Pipeline

Manages all real-time data feeds and provides a unified interface for the
scanner modules. Supports multiple data providers (Polygon.io, Alpaca, CBOE,
and a mock provider for testing/paper trading).

Data Feeds:
    - SPX Index: real-time price
    - ES Futures (front month): price + volume + OI
    - SPXW Options Chain (0DTE expiry): all strikes, bid/ask/mid/last/volume/OI
    - VIX, VIX1D, VIX9D: real-time
    - VIX Futures (front 2 months)
    - ES Futures Order Book: Level 2 depth (top 10)
    - SPX Market Internals: NYSE TICK, TRIN, A/D, Up/Down Vol, Cumulative Delta
    - Economic Calendar
    - Previous Session Data

Architecture:
    DataFeedManager orchestrates all feeds via asyncio tasks, each running on
    its own cadence.  Provider-specific logic is encapsulated in adapter classes
    (PolygonDataAdapter, etc.).  The MockDataProvider generates synthetic but
    realistic data for testing and paper trading without live market access.
"""

from __future__ import annotations

import asyncio
import logging
import math
import random
import time as _time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Deque, Dict, List, Optional, Tuple

try:
    import aiohttp
except ImportError:  # pragma: no cover - aiohttp optional for mock-only usage
    aiohttp = None  # type: ignore[assignment]

from .constants import (
    INTRADAY_ZONE_SCHEDULE,
    SPX_CONTRACT,
    TRADING_DAYS_PER_YEAR,
    TRADING_MINUTES_PER_DAY,
    IntradayZone,
)
from .models import (
    CrossAssetData,
    EconomicEvent,
    ESOrderBook,
    MarketInternals,
    OptionQuote,
    OptionsChain,
    OptionSide,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Timezone helpers
# ---------------------------------------------------------------------------

_ET_OFFSET_EST = timezone(timedelta(hours=-5))
_ET_OFFSET_EDT = timezone(timedelta(hours=-4))

# US market holidays for 2024-2026 (YYYY, M, D).  Extend as needed.
_MARKET_HOLIDAYS: frozenset[date] = frozenset(
    date(y, m, d)
    for y, m, d in [
        # 2024
        (2024, 1, 1), (2024, 1, 15), (2024, 2, 19), (2024, 3, 29),
        (2024, 5, 27), (2024, 6, 19), (2024, 7, 4), (2024, 9, 2),
        (2024, 11, 28), (2024, 12, 25),
        # 2025
        (2025, 1, 1), (2025, 1, 20), (2025, 2, 17), (2025, 4, 18),
        (2025, 5, 26), (2025, 6, 19), (2025, 7, 4), (2025, 9, 1),
        (2025, 11, 27), (2025, 12, 25),
        # 2026
        (2026, 1, 1), (2026, 1, 19), (2026, 2, 16), (2026, 4, 3),
        (2026, 5, 25), (2026, 6, 19), (2026, 7, 3), (2026, 9, 7),
        (2026, 11, 26), (2026, 12, 25),
    ]
)


def _is_dst(dt: datetime) -> bool:
    """Rough US Eastern DST check (second Sunday in March to first Sunday in November)."""
    year = dt.year
    # Second Sunday of March
    march_start = date(year, 3, 8)
    while march_start.weekday() != 6:  # Sunday
        march_start += timedelta(days=1)
    # First Sunday of November
    nov_start = date(year, 11, 1)
    while nov_start.weekday() != 6:
        nov_start += timedelta(days=1)
    d = dt.date() if isinstance(dt, datetime) else dt
    return march_start <= d < nov_start


def get_et_now() -> datetime:
    """Get the current time in US Eastern Time.

    Automatically handles EST/EDT transitions.

    Returns:
        datetime: Current time with Eastern Time timezone info.
    """
    utc_now = datetime.now(timezone.utc)
    offset = _ET_OFFSET_EDT if _is_dst(utc_now) else _ET_OFFSET_EST
    return utc_now.astimezone(offset)


def is_market_open() -> bool:
    """Check whether the US equity market is currently open.

    Accounts for weekends, known holidays, and regular trading hours
    (9:30 AM - 4:00 PM ET).  Does **not** handle early-close days.

    Returns:
        bool: True if the market is open right now.
    """
    now = get_et_now()
    if now.weekday() >= 5:  # Saturday or Sunday
        return False
    if now.date() in _MARKET_HOLIDAYS:
        return False
    market_open = time(9, 30)
    market_close = time(16, 0)
    return market_open <= now.time() <= market_close


def minutes_until_close() -> int:
    """Calculate the number of minutes remaining until the 4:00 PM ET close.

    If the market is closed or already past 4:00 PM, returns 0.

    Returns:
        int: Minutes remaining until close, or 0 if market is closed.
    """
    now = get_et_now()
    close_dt = now.replace(hour=16, minute=0, second=0, microsecond=0)
    if now >= close_dt:
        return 0
    open_dt = now.replace(hour=9, minute=30, second=0, microsecond=0)
    if now < open_dt:
        return TRADING_MINUTES_PER_DAY
    diff = close_dt - now
    return max(0, int(diff.total_seconds() / 60))


def get_trading_day_expiry() -> date:
    """Get today's 0DTE expiry date, accounting for weekends and holidays.

    If today is not a trading day, returns the next valid trading day.

    Returns:
        date: The 0DTE expiry date.
    """
    today = get_et_now().date()
    candidate = today
    # If weekend or holiday, roll forward
    while candidate.weekday() >= 5 or candidate in _MARKET_HOLIDAYS:
        candidate += timedelta(days=1)
    return candidate


# ---------------------------------------------------------------------------
# Black-Scholes IV solver (Newton-Raphson)
# ---------------------------------------------------------------------------

_SQRT_2PI = math.sqrt(2.0 * math.pi)


def _norm_cdf(x: float) -> float:
    """Standard normal CDF approximation (Abramowitz & Stegun 26.2.17)."""
    if x >= 0:
        k = 1.0 / (1.0 + 0.2316419 * x)
    else:
        k = 1.0 / (1.0 - 0.2316419 * x)
    poly = k * (0.319381530 + k * (-0.356563782 + k * (1.781477937
           + k * (-1.821255978 + k * 1.330274429))))
    if x >= 0:
        return 1.0 - (1.0 / _SQRT_2PI) * math.exp(-0.5 * x * x) * poly
    return (1.0 / _SQRT_2PI) * math.exp(-0.5 * x * x) * poly


def _norm_pdf(x: float) -> float:
    """Standard normal PDF."""
    return (1.0 / _SQRT_2PI) * math.exp(-0.5 * x * x)


def _bs_price(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    is_call: bool,
) -> float:
    """Black-Scholes European option price."""
    if T <= 0 or sigma <= 0:
        intrinsic = max(S - K, 0.0) if is_call else max(K - S, 0.0)
        return intrinsic
    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    if is_call:
        return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)


def _bs_vega(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-Scholes vega (partial derivative w.r.t. sigma)."""
    if T <= 0 or sigma <= 0:
        return 0.0
    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqrt_T)
    return S * _norm_pdf(d1) * sqrt_T


def compute_iv_newton(
    market_price: float,
    S: float,
    K: float,
    T: float,
    r: float,
    is_call: bool,
    *,
    initial_guess: float = 0.25,
    tol: float = 1e-6,
    max_iter: int = 50,
) -> float:
    """Compute implied volatility using Newton-Raphson iteration.

    Args:
        market_price: Observed option market price (mid preferred).
        S: Underlying spot price.
        K: Strike price.
        T: Time to expiry in years.
        r: Risk-free rate (annualized, continuous compounding).
        is_call: True for calls, False for puts.
        initial_guess: Starting IV guess.
        tol: Convergence tolerance.
        max_iter: Maximum iterations.

    Returns:
        float: Implied volatility estimate, or NaN if solver fails to converge.
    """
    intrinsic = max(S - K, 0.0) if is_call else max(K - S, 0.0)
    if market_price <= intrinsic + 1e-8:
        return 0.001  # Deep ITM with negligible time value

    sigma = initial_guess
    for _ in range(max_iter):
        price = _bs_price(S, K, T, r, sigma, is_call)
        vega = _bs_vega(S, K, T, r, sigma)
        if vega < 1e-12:
            break
        diff = price - market_price
        if abs(diff) < tol:
            return max(sigma, 0.001)
        sigma -= diff / vega
        sigma = max(sigma, 0.001)
        sigma = min(sigma, 10.0)  # Cap at 1000% IV
    # Did not converge cleanly; return best estimate
    if 0.001 < sigma < 10.0:
        return sigma
    return float("nan")


# ---------------------------------------------------------------------------
# Abstract data adapter
# ---------------------------------------------------------------------------

class BaseDataAdapter(ABC):
    """Abstract base for vendor-specific data adapters."""

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key
        self._session: Optional[aiohttp.ClientSession] = None

    async def ensure_session(self) -> aiohttp.ClientSession:
        """Lazily create an aiohttp session with sensible defaults."""
        if aiohttp is None:
            raise RuntimeError(
                "aiohttp is required for live data adapters. "
                "Install with: pip install aiohttp"
            )
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=15, connect=5)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers={"Accept": "application/json"},
            )
        return self._session

    async def close_session(self) -> None:
        """Close the HTTP session if open."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    @abstractmethod
    async def fetch_spx_price(self) -> float: ...

    @abstractmethod
    async def fetch_es_data(self) -> Dict[str, Any]: ...

    @abstractmethod
    async def fetch_options_chain(
        self, expiry_date: date, spx_price: float
    ) -> OptionsChain: ...

    @abstractmethod
    async def fetch_vix_data(self) -> Dict[str, float]: ...

    @abstractmethod
    async def fetch_market_internals(self) -> MarketInternals: ...

    @abstractmethod
    async def fetch_es_order_book(self, es_price: float) -> ESOrderBook: ...

    @abstractmethod
    async def fetch_economic_calendar(self, target_date: date) -> List[EconomicEvent]: ...

    @abstractmethod
    async def fetch_prior_session(self) -> Dict[str, Any]: ...


# ---------------------------------------------------------------------------
# Polygon.io adapter
# ---------------------------------------------------------------------------

class PolygonDataAdapter(BaseDataAdapter):
    """Adapter for Polygon.io real-time data feed.

    Implements the actual API calls to Polygon for options chain, indices,
    VIX term structure, ES futures, and market internals.  Uses aiohttp for
    async HTTP requests and handles rate limiting and connection management.
    """

    BASE_URL = "https://api.polygon.io"
    # Polygon rate limits: 5 calls/minute on free, unlimited on paid
    _MIN_REQUEST_INTERVAL = 0.05  # 50 ms between requests (safety margin)

    def __init__(self, api_key: str = "") -> None:
        super().__init__(api_key)
        self._last_request_time: float = 0.0
        self._request_count: int = 0
        self._rate_limit_reset: float = 0.0

    async def _rate_limited_get(
        self, url: str, params: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Execute a rate-limited GET request against the Polygon API.

        Handles HTTP errors, rate-limit backoff (429), and JSON parsing.

        Args:
            url: Full URL or path relative to BASE_URL.
            params: Query parameters.

        Returns:
            Parsed JSON response as a dict.

        Raises:
            ConnectionError: On HTTP errors or connectivity issues.
            ValueError: On invalid JSON responses.
        """
        session = await self.ensure_session()

        # Enforce minimum interval between requests
        elapsed = _time.monotonic() - self._last_request_time
        if elapsed < self._MIN_REQUEST_INTERVAL:
            await asyncio.sleep(self._MIN_REQUEST_INTERVAL - elapsed)

        full_url = url if url.startswith("http") else f"{self.BASE_URL}{url}"
        if params is None:
            params = {}
        params["apiKey"] = self.api_key

        retries = 3
        for attempt in range(retries):
            try:
                self._last_request_time = _time.monotonic()
                self._request_count += 1
                async with session.get(full_url, params=params) as resp:
                    if resp.status == 429:
                        # Rate limited -- exponential backoff
                        wait = 2 ** attempt
                        logger.warning(
                            "Polygon rate limit hit (attempt %d/%d), "
                            "backing off %.1fs",
                            attempt + 1, retries, wait,
                        )
                        await asyncio.sleep(wait)
                        continue
                    if resp.status == 403:
                        raise ConnectionError(
                            f"Polygon API: 403 Forbidden for {full_url}. "
                            "Check API key and subscription tier."
                        )
                    if resp.status >= 400:
                        body = await resp.text()
                        raise ConnectionError(
                            f"Polygon API error {resp.status}: {body[:500]}"
                        )
                    data = await resp.json()
                    return data
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                if attempt < retries - 1:
                    wait = 1.0 * (attempt + 1)
                    logger.warning(
                        "Polygon request failed (attempt %d/%d): %s. "
                        "Retrying in %.1fs",
                        attempt + 1, retries, exc, wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    raise ConnectionError(
                        f"Polygon API unreachable after {retries} attempts: {exc}"
                    ) from exc

        raise ConnectionError("Polygon API: exhausted retries")

    # -- SPX Price ---------------------------------------------------------

    async def fetch_spx_price(self) -> float:
        """Fetch the latest SPX index price from Polygon.

        Returns:
            float: Current SPX price.
        """
        data = await self._rate_limited_get(
            "/v2/last/trade/I:SPX"
        )
        results = data.get("results", {})
        price = results.get("p") or results.get("price", 0.0)
        if not price:
            # Fallback: snapshot
            snap = await self._rate_limited_get(
                "/v2/snapshot/locale/us/markets/stocks/tickers/SPY"
            )
            ticker = snap.get("ticker", {})
            day = ticker.get("day", {})
            price = day.get("c", 0.0)
            # Approximate SPX from SPY (* ~10)
            if price:
                price *= 10.0
        return float(price)

    # -- ES Futures --------------------------------------------------------

    async def fetch_es_data(self) -> Dict[str, Any]:
        """Fetch ES futures front-month data.

        Returns:
            Dict with keys: price, volume, open_interest, change, change_pct.
        """
        data = await self._rate_limited_get(
            "/v2/snapshot/locale/us/markets/stocks/tickers/ES=F"
        )
        ticker = data.get("ticker", {})
        day = ticker.get("day", {})
        return {
            "price": float(day.get("c", 0.0)),
            "volume": int(day.get("v", 0)),
            "open_interest": 0,  # OI requires separate endpoint
            "change": float(day.get("c", 0.0)) - float(day.get("o", 0.0)),
            "change_pct": 0.0,
        }

    # -- Options Chain -----------------------------------------------------

    async def fetch_options_chain(
        self, expiry_date: date, spx_price: float
    ) -> OptionsChain:
        """Fetch the complete SPXW 0DTE options chain for the given expiry.

        Retrieves all strikes from approximately 5 sigma OTM put to 5 sigma
        OTM call.  Computes implied volatility via Newton-Raphson if the
        feed does not supply it.

        Args:
            expiry_date: The 0DTE expiration date.
            spx_price: Current SPX spot price (used to scope strike range).

        Returns:
            OptionsChain: Fully populated chain with quotes and Greeks.
        """
        exp_str = expiry_date.strftime("%Y-%m-%d")

        # Determine strike range: roughly 5-sigma with VIX ~ 25 as upper bound
        daily_sigma = spx_price * 0.25 / math.sqrt(TRADING_DAYS_PER_YEAR)
        range_points = 5.0 * daily_sigma
        strike_low = int((spx_price - range_points) / 5) * 5
        strike_high = int((spx_price + range_points) / 5) * 5 + 5

        params = {
            "underlying_ticker": "SPX",
            "expiration_date": exp_str,
            "strike_price.gte": str(strike_low),
            "strike_price.lte": str(strike_high),
            "limit": "250",
            "order": "asc",
            "sort": "strike_price",
        }
        data = await self._rate_limited_get(
            "/v3/snapshot/options/SPX", params=params
        )
        results = data.get("results", [])

        # Time to expiry in years for IV computation
        now_et = get_et_now()
        close_today = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
        tte_seconds = max((close_today - now_et).total_seconds(), 60.0)
        tte_years = tte_seconds / (TRADING_DAYS_PER_YEAR * TRADING_MINUTES_PER_DAY * 60)
        risk_free_rate = 0.05  # Approximate; ideally from treasury feed

        quotes: List[OptionQuote] = []
        for item in results:
            details = item.get("details", {})
            greeks = item.get("greeks", {})
            day = item.get("day", {})
            last_quote = item.get("last_quote", {})

            strike = float(details.get("strike_price", 0))
            contract_type = details.get("contract_type", "").upper()
            is_call = contract_type == "CALL"

            bid = float(last_quote.get("bid", 0))
            ask = float(last_quote.get("ask", 0))
            mid = (bid + ask) / 2.0 if (bid > 0 and ask > 0) else 0.0
            last = float(day.get("close", mid))
            volume = int(day.get("volume", 0))
            oi = int(item.get("open_interest", 0))

            iv = float(greeks.get("implied_volatility", 0))
            if iv <= 0 and mid > 0:
                iv = compute_iv_newton(
                    mid, spx_price, strike, tte_years, risk_free_rate, is_call
                )

            quote = OptionQuote(
                strike=strike,
                side=OptionSide.CALL if is_call else OptionSide.PUT,
                bid=bid,
                ask=ask,
                mid=mid,
                last=last,
                volume=volume,
                open_interest=oi,
                implied_volatility=iv,
                delta=float(greeks.get("delta", 0)),
                gamma=float(greeks.get("gamma", 0)),
                theta=float(greeks.get("theta", 0)),
                vega=float(greeks.get("vega", 0)),
                timestamp=now_et,
            )
            quotes.append(quote)

        return OptionsChain(
            underlying_price=spx_price,
            expiry_date=expiry_date,
            quotes=quotes,
            timestamp=now_et,
        )

    # -- VIX Data ----------------------------------------------------------

    async def fetch_vix_data(self) -> Dict[str, float]:
        """Fetch VIX, VIX1D, VIX9D, and front two VIX futures.

        Returns:
            Dict with keys: vix, vix1d, vix9d, vix_f1, vix_f2.
        """
        result: Dict[str, float] = {
            "vix": 0.0,
            "vix1d": 0.0,
            "vix9d": 0.0,
            "vix_f1": 0.0,
            "vix_f2": 0.0,
        }
        tickers = {
            "vix": "I:VIX",
            "vix1d": "I:VIX1D",
            "vix9d": "I:VIX9D",
        }
        for key, ticker in tickers.items():
            try:
                data = await self._rate_limited_get(
                    f"/v2/last/trade/{ticker}"
                )
                price = data.get("results", {}).get("p", 0.0)
                result[key] = float(price) if price else 0.0
            except (ConnectionError, KeyError) as exc:
                logger.warning("Failed to fetch %s: %s", ticker, exc)
        return result

    # -- Market Internals --------------------------------------------------

    async def fetch_market_internals(self) -> MarketInternals:
        """Fetch NYSE market internals snapshot.

        Returns:
            MarketInternals with TICK, TRIN, A/D, volume metrics, and
            cumulative delta.
        """
        now_et = get_et_now()
        internals: Dict[str, float] = {}
        tickers = {
            "tick": "I:TICK",
            "trin": "I:TRIN",
            "advn": "I:ADVN",
            "decn": "I:DECN",
            "uvol": "I:UVOL",
            "dvol": "I:DVOL",
        }
        for key, ticker in tickers.items():
            try:
                data = await self._rate_limited_get(
                    f"/v2/last/trade/{ticker}"
                )
                val = data.get("results", {}).get("p", 0.0)
                internals[key] = float(val) if val else 0.0
            except (ConnectionError, KeyError) as exc:
                logger.warning("Failed to fetch %s: %s", ticker, exc)
                internals[key] = 0.0

        advancing = int(internals.get("advn", 0))
        declining = int(internals.get("decn", 0))
        up_volume = int(internals.get("uvol", 0))
        down_volume = int(internals.get("dvol", 0))

        return MarketInternals(
            nyse_tick=internals.get("tick", 0.0),
            trin=internals.get("trin", 1.0),
            advance_decline_ratio=(
                advancing / max(declining, 1)
            ),
            advancing_issues=advancing,
            declining_issues=declining,
            up_volume=up_volume,
            down_volume=down_volume,
            cumulative_delta=0.0,  # Requires tick-by-tick aggregation
            timestamp=now_et,
        )

    # -- ES Order Book -----------------------------------------------------

    async def fetch_es_order_book(self, es_price: float) -> ESOrderBook:
        """Fetch ES futures Level 2 order book (top 10 levels).

        Args:
            es_price: Current ES price (used for fallback generation).

        Returns:
            ESOrderBook with bid and ask levels.
        """
        now_et = get_et_now()
        try:
            data = await self._rate_limited_get(
                "/v3/snapshot/locale/us/markets/stocks/tickers/ES=F"
            )
            # Polygon snapshot may not include full L2; parse what's available
            bids: List[Tuple[float, int]] = []
            asks: List[Tuple[float, int]] = []
            book = data.get("book", {})
            for entry in book.get("bids", [])[:10]:
                bids.append(
                    (float(entry.get("p", 0)), int(entry.get("s", 0)))
                )
            for entry in book.get("asks", [])[:10]:
                asks.append(
                    (float(entry.get("p", 0)), int(entry.get("s", 0)))
                )
            return ESOrderBook(
                bids=bids,
                asks=asks,
                es_price=es_price,
                timestamp=now_et,
            )
        except (ConnectionError, KeyError) as exc:
            logger.warning("ES order book unavailable: %s", exc)
            return ESOrderBook(
                bids=[],
                asks=[],
                es_price=es_price,
                timestamp=now_et,
            )

    # -- Economic Calendar -------------------------------------------------

    async def fetch_economic_calendar(
        self, target_date: date
    ) -> List[EconomicEvent]:
        """Fetch scheduled economic events for a given date.

        Args:
            target_date: The calendar date to query.

        Returns:
            List of EconomicEvent instances ordered by time.
        """
        # Polygon does not natively provide an economic calendar.
        # We return an empty list; callers should use a dedicated provider
        # (e.g., Econoday, Trading Economics) or configure events manually.
        logger.debug(
            "Polygon adapter: economic calendar not supported natively. "
            "Returning empty list for %s.",
            target_date,
        )
        return []

    # -- Prior Session -----------------------------------------------------

    async def fetch_prior_session(self) -> Dict[str, Any]:
        """Fetch prior trading session data for SPX.

        Returns:
            Dict with keys: close, high, low, vwap, poc, vix1d_close,
            realized_vol_20d, and gex_profile.
        """
        result: Dict[str, Any] = {
            "close": 0.0,
            "high": 0.0,
            "low": 0.0,
            "vwap": 0.0,
            "poc": 0.0,
            "vix1d_close": 0.0,
            "realized_vol_20d": 0.0,
            "gex_profile": {},
        }
        try:
            data = await self._rate_limited_get(
                "/v2/aggs/ticker/I:SPX/prev"
            )
            agg = (data.get("results") or [{}])[0]
            result["close"] = float(agg.get("c", 0))
            result["high"] = float(agg.get("h", 0))
            result["low"] = float(agg.get("l", 0))
            result["vwap"] = float(agg.get("vw", 0)) or result["close"]
            result["poc"] = result["vwap"]  # Approximation
        except (ConnectionError, KeyError, IndexError) as exc:
            logger.warning("Failed to fetch prior session: %s", exc)

        # VIX1D prior close
        try:
            data = await self._rate_limited_get(
                "/v2/aggs/ticker/I:VIX1D/prev"
            )
            agg = (data.get("results") or [{}])[0]
            result["vix1d_close"] = float(agg.get("c", 0))
        except (ConnectionError, KeyError, IndexError) as exc:
            logger.debug("VIX1D prior close unavailable: %s", exc)

        # 20-day realized vol from daily bars
        try:
            today_str = get_et_now().strftime("%Y-%m-%d")
            from_str = (get_et_now() - timedelta(days=35)).strftime("%Y-%m-%d")
            data = await self._rate_limited_get(
                f"/v2/aggs/ticker/I:SPX/range/1/day/{from_str}/{today_str}",
                params={"limit": "30", "sort": "asc"},
            )
            bars = data.get("results", [])
            if len(bars) >= 20:
                closes = [float(b["c"]) for b in bars[-21:]]
                log_returns = [
                    math.log(closes[i] / closes[i - 1])
                    for i in range(1, len(closes))
                ]
                rv = (
                    (sum(r * r for r in log_returns) / len(log_returns)) ** 0.5
                ) * math.sqrt(TRADING_DAYS_PER_YEAR)
                result["realized_vol_20d"] = rv
        except (ConnectionError, KeyError, IndexError, ValueError) as exc:
            logger.debug("20-day RV calculation failed: %s", exc)

        return result


# ---------------------------------------------------------------------------
# Mock data provider
# ---------------------------------------------------------------------------

class MockDataProvider(BaseDataAdapter):
    """Mock data provider for testing and paper trading.

    Generates realistic SPX market data with configurable scenarios.
    Simulates intraday dynamics including trending, volatility expansion,
    squeezes, and event-day behaviour.

    Scenarios:
        normal: Typical range-bound 0DTE day.
        trending_up: Steady bullish drift with pullbacks.
        trending_down: Steady bearish drift with bounces.
        volatile: High-volatility whipsaw session.
        squeeze: Gamma squeeze scenario with accelerating moves.
        event_day: FOMC/CPI day with pre-event compression then expansion.
    """

    def __init__(
        self,
        scenario: str = "normal",
        base_spx: float = 6000.0,
        base_vix: float = 16.0,
    ) -> None:
        super().__init__(api_key="mock")
        self.scenario = scenario
        self.base_spx = base_spx
        self.base_vix = base_vix
        self._tick_count: int = 0
        self._trend_bias: float = 0.0
        self._rng = random.Random(42)
        self._spx_price = base_spx
        self._drift_accum = 0.0
        self._initialize_scenario()

    def _initialize_scenario(self) -> None:
        """Set internal state based on the chosen scenario."""
        scenario_params = {
            "normal": (0.0, 1.0),
            "trending_up": (0.0003, 0.8),
            "trending_down": (-0.0003, 0.8),
            "volatile": (0.0, 2.0),
            "squeeze": (0.0005, 1.5),
            "event_day": (0.0, 0.6),
        }
        self._trend_bias, self._vol_multiplier = scenario_params.get(
            self.scenario, (0.0, 1.0)
        )

    def _evolve_price(self) -> float:
        """Advance the simulated SPX price by one tick."""
        self._tick_count += 1
        noise = self._rng.gauss(0, 1) * 0.5 * self._vol_multiplier
        drift = self._trend_bias * self.base_spx
        self._drift_accum += drift
        self._spx_price += drift + noise

        # Mean-revert if too far from base
        reversion = (self.base_spx + self._drift_accum - self._spx_price) * 0.001
        self._spx_price += reversion
        return round(self._spx_price, 2)

    # -- BaseDataAdapter interface implementation --

    async def fetch_spx_price(self) -> float:
        return self._evolve_price()

    async def fetch_es_data(self) -> Dict[str, Any]:
        es_price = self._spx_price + self._rng.uniform(-2.0, 2.0)
        return {
            "price": round(es_price, 2),
            "volume": self._rng.randint(800_000, 2_500_000),
            "open_interest": self._rng.randint(2_000_000, 4_000_000),
            "change": round(es_price - self.base_spx, 2),
            "change_pct": round(
                (es_price - self.base_spx) / self.base_spx * 100, 3
            ),
        }

    async def fetch_options_chain(
        self, expiry_date: date, spx_price: float
    ) -> OptionsChain:
        """Alias for generate_options_chain with derived parameters."""
        mins_remaining = minutes_until_close() or 200
        return self.generate_options_chain(spx_price, mins_remaining, self.base_vix)

    async def fetch_vix_data(self) -> Dict[str, float]:
        vix = self.base_vix + self._rng.gauss(0, 0.5)
        vix1d = vix * self._rng.uniform(0.85, 1.30)
        vix9d = vix * self._rng.uniform(0.90, 1.10)
        return {
            "vix": round(max(vix, 9.0), 2),
            "vix1d": round(max(vix1d, 8.0), 2),
            "vix9d": round(max(vix9d, 8.5), 2),
            "vix_f1": round(vix + self._rng.uniform(0.5, 2.0), 2),
            "vix_f2": round(vix + self._rng.uniform(1.0, 3.0), 2),
        }

    async def fetch_market_internals(self) -> MarketInternals:
        trend = 1 if self._trend_bias >= 0 else -1
        return self.generate_market_internals(trend)

    async def fetch_es_order_book(self, es_price: float) -> ESOrderBook:
        trend = 1 if self._trend_bias >= 0 else -1
        return self.generate_es_order_book(es_price, trend)

    async def fetch_economic_calendar(
        self, target_date: date
    ) -> List[EconomicEvent]:
        return self.generate_economic_calendar()

    async def fetch_prior_session(self) -> Dict[str, Any]:
        return {
            "close": round(self.base_spx - self._rng.uniform(-10, 10), 2),
            "high": round(self.base_spx + self._rng.uniform(5, 25), 2),
            "low": round(self.base_spx - self._rng.uniform(5, 25), 2),
            "vwap": round(self.base_spx + self._rng.uniform(-3, 3), 2),
            "poc": round(self.base_spx + self._rng.uniform(-5, 5), 2),
            "vix1d_close": round(self.base_vix + self._rng.uniform(-2, 2), 2),
            "realized_vol_20d": round(
                self.base_vix / 100 * self._rng.uniform(0.8, 1.2), 4
            ),
            "gex_profile": {
                "total_gex": self._rng.uniform(-5e9, 5e9),
                "zero_gamma_level": round(
                    self.base_spx + self._rng.uniform(-20, 20), 0
                ),
                "call_wall": round(
                    self.base_spx + self._rng.uniform(10, 50), 0
                ),
                "put_wall": round(
                    self.base_spx - self._rng.uniform(10, 50), 0
                ),
            },
        }

    # -- Public generator methods ------------------------------------------

    def generate_options_chain(
        self,
        spx_price: float,
        minutes_remaining: int,
        vix_level: float,
    ) -> OptionsChain:
        """Generate a realistic synthetic 0DTE options chain.

        Produces call and put quotes across a wide strike range with
        Black-Scholes-consistent pricing, time-decayed IVs, and
        realistic bid-ask spreads.

        Args:
            spx_price: Current SPX spot price.
            minutes_remaining: Minutes until 4:00 PM ET close.
            vix_level: Current VIX level (annualized).

        Returns:
            OptionsChain: Synthetic chain with all quotes populated.
        """
        now_et = get_et_now()
        expiry = get_trading_day_expiry()

        # Time to expiry
        tte_minutes = max(minutes_remaining, 1)
        tte_years = tte_minutes / (TRADING_MINUTES_PER_DAY * TRADING_DAYS_PER_YEAR)
        daily_vol = vix_level / 100.0 / math.sqrt(TRADING_DAYS_PER_YEAR)
        sigma_points = daily_vol * spx_price

        # Strike range: 5 sigma each direction, rounded to $5 increments
        low_strike = int((spx_price - 5 * sigma_points) / 5) * 5
        high_strike = int((spx_price + 5 * sigma_points) / 5) * 5 + 5

        quotes: List[OptionQuote] = []
        risk_free = 0.05

        for strike in range(low_strike, high_strike + 1, 5):
            for side in (OptionSide.CALL, OptionSide.PUT):
                is_call = side == OptionSide.CALL
                moneyness = (spx_price - strike) / spx_price
                distance = abs(moneyness)

                # IV smile: ATM = vix_level, wings get higher
                iv = (vix_level / 100.0) * (1.0 + 1.5 * distance ** 0.8)
                # Add some randomness
                iv *= self._rng.uniform(0.95, 1.05)
                iv = max(iv, 0.01)

                # BS theoretical price
                theo = _bs_price(
                    spx_price, float(strike), tte_years, risk_free, iv, is_call
                )
                theo = max(theo, 0.05)

                # Bid-ask spread widens for OTM and near expiry
                spread_pct = 0.03 + 0.10 * distance + 0.02 / max(
                    tte_minutes / 60, 0.1
                )
                spread_pct = min(spread_pct, 0.50)
                half_spread = theo * spread_pct / 2
                bid = round(max(theo - half_spread, 0.05), 2)
                ask = round(theo + half_spread, 2)
                mid = round((bid + ask) / 2, 2)
                last = round(
                    mid + self._rng.uniform(-half_spread * 0.3, half_spread * 0.3),
                    2,
                )

                # Volume and OI: higher near ATM
                atm_factor = max(0, 1.0 - 3 * distance)
                volume = int(
                    self._rng.uniform(50, 5000) * (0.2 + atm_factor)
                )
                oi = int(
                    self._rng.uniform(500, 50000) * (0.2 + atm_factor)
                )

                # Greeks (simplified BS)
                sqrt_t = math.sqrt(max(tte_years, 1e-8))
                d1_num = math.log(spx_price / max(strike, 1)) + (
                    risk_free + 0.5 * iv * iv
                ) * tte_years
                d1 = d1_num / (iv * sqrt_t) if iv * sqrt_t > 1e-12 else 0.0
                d2 = d1 - iv * sqrt_t

                delta = _norm_cdf(d1) if is_call else _norm_cdf(d1) - 1.0
                gamma = _norm_pdf(d1) / (
                    spx_price * iv * sqrt_t
                ) if iv * sqrt_t > 1e-12 else 0.0
                theta = -(
                    spx_price * _norm_pdf(d1) * iv / (2 * sqrt_t)
                ) / TRADING_DAYS_PER_YEAR if sqrt_t > 1e-12 else 0.0
                vega = (
                    spx_price * _norm_pdf(d1) * sqrt_t / 100
                )

                quote = OptionQuote(
                    strike=float(strike),
                    side=side,
                    bid=bid,
                    ask=ask,
                    mid=mid,
                    last=last,
                    volume=volume,
                    open_interest=oi,
                    implied_volatility=round(iv, 4),
                    delta=round(delta, 4),
                    gamma=round(gamma, 6),
                    theta=round(theta, 4),
                    vega=round(vega, 4),
                    timestamp=now_et,
                )
                quotes.append(quote)

        return OptionsChain(
            underlying_price=spx_price,
            expiry_date=expiry,
            quotes=quotes,
            timestamp=now_et,
        )

    def generate_market_internals(
        self, trend_direction: int
    ) -> MarketInternals:
        """Generate a synthetic market internals snapshot.

        Args:
            trend_direction: +1 for bullish bias, -1 for bearish, 0 for neutral.

        Returns:
            MarketInternals: Synthetic but internally consistent data.
        """
        bias = trend_direction * self._rng.uniform(100, 400)
        tick = self._rng.gauss(bias, 200)
        tick = max(-2000, min(2000, tick))

        # TRIN: < 1 bullish, > 1 bearish
        trin_base = 1.0 - trend_direction * 0.2
        trin = max(0.3, self._rng.gauss(trin_base, 0.25))

        advancing = self._rng.randint(1000, 2500)
        declining = self._rng.randint(1000, 2500)
        if trend_direction > 0:
            advancing = int(advancing * 1.4)
        elif trend_direction < 0:
            declining = int(declining * 1.4)

        up_vol = self._rng.randint(500_000_000, 2_000_000_000)
        down_vol = self._rng.randint(500_000_000, 2_000_000_000)
        if trend_direction > 0:
            up_vol = int(up_vol * 1.5)
        elif trend_direction < 0:
            down_vol = int(down_vol * 1.5)

        cum_delta = trend_direction * self._rng.uniform(5000, 30000)

        return MarketInternals(
            nyse_tick=round(tick, 1),
            trin=round(trin, 3),
            advance_decline_ratio=round(advancing / max(declining, 1), 3),
            advancing_issues=advancing,
            declining_issues=declining,
            up_volume=up_vol,
            down_volume=down_vol,
            cumulative_delta=round(cum_delta, 0),
            timestamp=get_et_now(),
        )

    def generate_cross_asset_data(
        self, spx_price: float, vix_level: float
    ) -> CrossAssetData:
        """Generate synthetic cross-asset data.

        Args:
            spx_price: Current SPX price.
            vix_level: Current VIX level.

        Returns:
            CrossAssetData: Synthetic cross-asset snapshot.
        """
        es_price = spx_price + self._rng.uniform(-3, 3)
        vix1d = vix_level * self._rng.uniform(0.85, 1.30)
        vix9d = vix_level * self._rng.uniform(0.90, 1.10)
        yield_10y = self._rng.uniform(3.5, 5.0)
        dxy = self._rng.uniform(100, 108)

        return CrossAssetData(
            spx_price=spx_price,
            es_price=round(es_price, 2),
            es_volume=self._rng.randint(800_000, 2_500_000),
            vix=round(vix_level, 2),
            vix1d=round(vix1d, 2),
            vix9d=round(vix9d, 2),
            vix_futures_m1=round(vix_level + self._rng.uniform(0.5, 2.0), 2),
            vix_futures_m2=round(vix_level + self._rng.uniform(1.0, 3.0), 2),
            ten_year_yield=round(yield_10y, 3),
            dxy=round(dxy, 2),
            timestamp=get_et_now(),
        )

    def generate_es_order_book(
        self, es_price: float, trend_direction: int
    ) -> ESOrderBook:
        """Generate a synthetic ES Level 2 order book with top 10 levels.

        Args:
            es_price: Current ES futures price.
            trend_direction: +1 bullish, -1 bearish, 0 neutral.

        Returns:
            ESOrderBook: Synthetic order book.
        """
        bids: List[Tuple[float, int]] = []
        asks: List[Tuple[float, int]] = []

        for i in range(10):
            bid_price = round(es_price - 0.25 * (i + 1), 2)
            ask_price = round(es_price + 0.25 * (i + 1), 2)

            # Heavier on the buy side if bullish, sell side if bearish
            bid_mult = 1.3 if trend_direction > 0 else 0.8
            ask_mult = 0.8 if trend_direction > 0 else 1.3

            bid_size = int(
                self._rng.randint(50, 500) * bid_mult / (1 + i * 0.1)
            )
            ask_size = int(
                self._rng.randint(50, 500) * ask_mult / (1 + i * 0.1)
            )
            bids.append((bid_price, bid_size))
            asks.append((ask_price, ask_size))

        return ESOrderBook(
            bids=bids,
            asks=asks,
            es_price=es_price,
            timestamp=get_et_now(),
        )

    def generate_economic_calendar(self) -> List[EconomicEvent]:
        """Generate a synthetic economic calendar for the trading day.

        Returns:
            List of EconomicEvent instances with realistic timing and impact.
        """
        today = get_et_now().date()
        events = []

        # Some days have events, some don't
        if self.scenario == "event_day" or self._rng.random() < 0.4:
            possible_events = [
                ("CPI Release", time(8, 30), "high"),
                ("FOMC Rate Decision", time(14, 0), "high"),
                ("Initial Jobless Claims", time(8, 30), "medium"),
                ("ISM Manufacturing", time(10, 0), "medium"),
                ("Retail Sales", time(8, 30), "medium"),
                ("Consumer Confidence", time(10, 0), "low"),
                ("Existing Home Sales", time(10, 0), "low"),
            ]
            # Pick 1-3 events for the day
            count = self._rng.randint(1, 3) if self.scenario == "event_day" else 1
            selected = self._rng.sample(
                possible_events, min(count, len(possible_events))
            )
            for name, evt_time, impact in selected:
                events.append(
                    EconomicEvent(
                        name=name,
                        event_time=datetime.combine(today, evt_time),
                        impact=impact,
                        forecast="",
                        previous="",
                        actual="",
                    )
                )

        events.sort(key=lambda e: e.event_time)
        return events


# ---------------------------------------------------------------------------
# DataFeedManager
# ---------------------------------------------------------------------------

class DataFeedManager:
    """Manages all real-time data feeds required by the scanner system.

    Orchestrates concurrent data retrieval from multiple feeds, maintains
    current state for scanner consumption, and handles reconnection on
    failures.  The manager exposes both pull (fetch_*) and push (streaming)
    interfaces.

    Required data feeds:
        - SPX Index: real-time price
        - ES Futures (front month): price + volume + OI
        - SPXW Options Chain (0DTE expiry): all strikes, bid/ask/mid/last/volume/OI
        - VIX, VIX1D, VIX9D: real-time
        - VIX Futures (front 2 months)
        - ES Futures Order Book: Level 2 depth (top 10)
        - SPX Market Internals: NYSE TICK, TRIN, A/D, Up/Down Vol, Cumulative Delta
        - Economic Calendar
        - Previous Session Data

    Usage::

        manager = DataFeedManager(data_provider="mock")
        await manager.connect()
        await manager.start_streaming()

        snapshot = await manager.get_snapshot()
        # ... consume snapshot in scanner modules ...

        await manager.stop_streaming()
        await manager.disconnect()
    """

    # Supported data providers
    SUPPORTED_PROVIDERS = ("polygon", "alpaca", "cboe", "mock")

    def __init__(
        self,
        data_provider: str = "polygon",
        api_key: str = "",
        update_interval_seconds: float = 1.0,
        options_update_interval: float = 1.0,
        vix_update_interval: float = 15.0,
    ) -> None:
        """Initialize the DataFeedManager.

        Args:
            data_provider: Data vendor to use. One of "polygon", "alpaca",
                "cboe", or "mock".
            api_key: API key for the chosen data provider.
            update_interval_seconds: How often (in seconds) to refresh
                SPX price, ES data, and market internals.
            options_update_interval: How often (in seconds) to refresh
                the full options chain.
            vix_update_interval: How often (in seconds) to refresh VIX
                and cross-asset data.
        """
        if data_provider not in self.SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Unsupported data provider '{data_provider}'. "
                f"Choose from: {self.SUPPORTED_PROVIDERS}"
            )

        self._provider_name = data_provider
        self._api_key = api_key
        self._update_interval = update_interval_seconds
        self._options_update_interval = options_update_interval
        self._vix_update_interval = vix_update_interval

        # Adapter instance (set in connect())
        self._adapter: Optional[BaseDataAdapter] = None

        # -- Current state --
        self.spx_price: float = 0.0
        self.es_price: float = 0.0
        self.es_volume: int = 0
        self.options_chain: Optional[OptionsChain] = None
        self.market_internals: Optional[MarketInternals] = None
        self.cross_asset_data: Optional[CrossAssetData] = None
        self.es_order_book: Optional[ESOrderBook] = None
        self.economic_events: List[EconomicEvent] = []
        self.prior_session: Dict[str, Any] = {}
        self.is_connected: bool = False
        self.last_update: Optional[datetime] = None

        # -- Streaming tasks --
        self._streaming_tasks: List[asyncio.Task] = []
        self._stop_event: asyncio.Event = asyncio.Event()

        # -- History for staleness detection --
        self._spx_price_history: Deque[Tuple[datetime, float]] = deque(maxlen=300)
        self._reconnect_attempts: int = 0
        self._max_reconnect_attempts: int = 10
        self._reconnect_base_delay: float = 1.0

        # -- Error tracking --
        self._consecutive_errors: int = 0
        self._max_consecutive_errors: int = 20

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Initialize all data feed connections.

        Creates the appropriate adapter for the configured provider,
        establishes HTTP sessions, and fetches initial baseline data
        (prior session, economic calendar).

        Raises:
            ConnectionError: If the initial connection fails.
            ValueError: If the provider is not supported.
        """
        logger.info(
            "Connecting to data feeds via '%s' provider...", self._provider_name
        )

        # Instantiate the correct adapter
        if self._provider_name == "polygon":
            self._adapter = PolygonDataAdapter(api_key=self._api_key)
        elif self._provider_name == "mock":
            self._adapter = MockDataProvider()
        elif self._provider_name in ("alpaca", "cboe"):
            # Placeholder: use mock until dedicated adapters are implemented
            logger.warning(
                "Provider '%s' is not yet fully implemented. "
                "Falling back to mock data.",
                self._provider_name,
            )
            self._adapter = MockDataProvider()
        else:
            raise ValueError(f"Unsupported provider: {self._provider_name}")

        # Pre-warm with baseline data
        try:
            self.prior_session = await self._adapter.fetch_prior_session()
            self.economic_events = await self._adapter.fetch_economic_calendar(
                get_trading_day_expiry()
            )
            self.spx_price = await self._adapter.fetch_spx_price()
            es_data = await self._adapter.fetch_es_data()
            self.es_price = es_data.get("price", 0.0)
            self.es_volume = es_data.get("volume", 0)
        except Exception as exc:
            logger.error("Failed to fetch baseline data during connect: %s", exc)
            # For mock provider, this should never fail; for live, log and continue
            if self._provider_name != "mock":
                logger.warning(
                    "Continuing with empty baseline data. "
                    "Live data will populate on first streaming cycle."
                )

        self.is_connected = True
        self.last_update = get_et_now()
        self._reconnect_attempts = 0
        self._consecutive_errors = 0
        logger.info(
            "Data feed connected. SPX=%.2f, ES=%.2f, "
            "Prior close=%.2f, Events=%d",
            self.spx_price,
            self.es_price,
            self.prior_session.get("close", 0),
            len(self.economic_events),
        )

    async def disconnect(self) -> None:
        """Cleanly disconnect all data feeds.

        Stops any running streaming tasks and closes the HTTP session.
        """
        logger.info("Disconnecting data feeds...")
        await self.stop_streaming()

        if self._adapter is not None:
            await self._adapter.close_session()
            self._adapter = None

        self.is_connected = False
        logger.info("Data feeds disconnected.")

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    async def start_streaming(self) -> None:
        """Start streaming all data feeds.

        Launches concurrent asyncio tasks for each feed category, each
        running on its own cadence:
            - SPX + ES + internals: ``update_interval_seconds``
            - Options chain: ``options_update_interval``
            - VIX / cross-asset: ``vix_update_interval``
            - ES order book: ``update_interval_seconds``
        """
        if not self.is_connected:
            raise RuntimeError(
                "Cannot start streaming: not connected. Call connect() first."
            )
        if self._streaming_tasks:
            logger.warning("Streaming already running; ignoring duplicate start.")
            return

        self._stop_event.clear()
        logger.info("Starting data feed streaming...")

        self._streaming_tasks = [
            asyncio.create_task(
                self._stream_loop(
                    "spx_es_internals",
                    self._update_spx_es_internals,
                    self._update_interval,
                ),
                name="stream-spx-es-internals",
            ),
            asyncio.create_task(
                self._stream_loop(
                    "options_chain",
                    self._update_options_chain,
                    self._options_update_interval,
                ),
                name="stream-options-chain",
            ),
            asyncio.create_task(
                self._stream_loop(
                    "vix_cross_asset",
                    self._update_vix_cross_asset,
                    self._vix_update_interval,
                ),
                name="stream-vix-cross-asset",
            ),
            asyncio.create_task(
                self._stream_loop(
                    "es_order_book",
                    self._update_es_order_book,
                    self._update_interval,
                ),
                name="stream-es-order-book",
            ),
        ]
        logger.info(
            "Data streaming started (%d tasks).", len(self._streaming_tasks)
        )

    async def stop_streaming(self) -> None:
        """Stop all streaming tasks gracefully."""
        if not self._streaming_tasks:
            return

        logger.info("Stopping data feed streaming...")
        self._stop_event.set()

        for task in self._streaming_tasks:
            task.cancel()

        results = await asyncio.gather(
            *self._streaming_tasks, return_exceptions=True
        )
        for task, result in zip(self._streaming_tasks, results):
            if isinstance(result, Exception) and not isinstance(
                result, asyncio.CancelledError
            ):
                logger.warning(
                    "Streaming task '%s' raised during shutdown: %s",
                    task.get_name(),
                    result,
                )

        self._streaming_tasks.clear()
        logger.info("Data feed streaming stopped.")

    async def _stream_loop(
        self,
        name: str,
        update_fn,
        interval: float,
    ) -> None:
        """Generic streaming loop that calls ``update_fn`` every ``interval`` seconds.

        Handles errors with exponential backoff and reconnection logic.

        Args:
            name: Human-readable name for logging.
            update_fn: Async callable that performs the data update.
            interval: Seconds between updates.
        """
        logger.debug("Stream loop '%s' started (interval=%.2fs)", name, interval)
        consecutive_errors = 0
        max_consecutive = 10

        while not self._stop_event.is_set():
            try:
                await update_fn()
                consecutive_errors = 0
                self.last_update = get_et_now()
            except asyncio.CancelledError:
                logger.debug("Stream loop '%s' cancelled.", name)
                return
            except Exception as exc:
                consecutive_errors += 1
                backoff = min(
                    self._reconnect_base_delay * (2 ** (consecutive_errors - 1)),
                    60.0,
                )
                logger.error(
                    "Stream '%s' error (%d/%d): %s. "
                    "Retrying in %.1fs.",
                    name,
                    consecutive_errors,
                    max_consecutive,
                    exc,
                    backoff,
                )
                if consecutive_errors >= max_consecutive:
                    logger.critical(
                        "Stream '%s': too many consecutive errors (%d). "
                        "Attempting adapter reconnect...",
                        name,
                        consecutive_errors,
                    )
                    await self._attempt_reconnect()
                    consecutive_errors = 0
                else:
                    await asyncio.sleep(backoff)
                    continue

            # Wait for the next cycle, but respect the stop event
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=interval
                )
                # If we get here, stop_event was set
                return
            except asyncio.TimeoutError:
                # Normal: interval elapsed, loop again
                pass

    async def _attempt_reconnect(self) -> None:
        """Attempt to reconnect the data adapter after repeated failures."""
        self._reconnect_attempts += 1
        if self._reconnect_attempts > self._max_reconnect_attempts:
            logger.critical(
                "Max reconnect attempts (%d) exceeded. "
                "Manual intervention required.",
                self._max_reconnect_attempts,
            )
            self.is_connected = False
            return

        delay = min(
            self._reconnect_base_delay * (2 ** self._reconnect_attempts),
            120.0,
        )
        logger.warning(
            "Reconnect attempt %d/%d in %.1fs...",
            self._reconnect_attempts,
            self._max_reconnect_attempts,
            delay,
        )
        await asyncio.sleep(delay)

        try:
            if self._adapter:
                await self._adapter.close_session()
            await self.connect()
            logger.info("Reconnect successful.")
        except Exception as exc:
            logger.error("Reconnect failed: %s", exc)

    # ------------------------------------------------------------------
    # Internal update methods (called by stream loops)
    # ------------------------------------------------------------------

    async def _update_spx_es_internals(self) -> None:
        """Fetch and update SPX price, ES data, and market internals."""
        assert self._adapter is not None

        spx_price, es_data, internals = await asyncio.gather(
            self._adapter.fetch_spx_price(),
            self._adapter.fetch_es_data(),
            self._adapter.fetch_market_internals(),
        )

        if spx_price > 0:
            self.spx_price = spx_price
            self._spx_price_history.append((get_et_now(), spx_price))

        self.es_price = es_data.get("price", self.es_price)
        self.es_volume = es_data.get("volume", self.es_volume)
        self.market_internals = internals

    async def _update_options_chain(self) -> None:
        """Fetch and update the full 0DTE options chain."""
        assert self._adapter is not None

        if self.spx_price <= 0:
            logger.debug("Skipping options chain update: SPX price not available.")
            return

        expiry = get_trading_day_expiry()
        chain = await self._adapter.fetch_options_chain(expiry, self.spx_price)
        if chain and chain.quotes:
            self.options_chain = chain
        else:
            logger.debug("Options chain update returned empty chain.")

    async def _update_vix_cross_asset(self) -> None:
        """Fetch and update VIX family and cross-asset data."""
        assert self._adapter is not None

        vix_data = await self._adapter.fetch_vix_data()

        # If the adapter is a MockDataProvider, use its generate method
        if isinstance(self._adapter, MockDataProvider):
            self.cross_asset_data = self._adapter.generate_cross_asset_data(
                self.spx_price or self._adapter.base_spx,
                vix_data.get("vix", self._adapter.base_vix),
            )
        else:
            self.cross_asset_data = CrossAssetData(
                spx_price=self.spx_price,
                es_price=self.es_price,
                es_volume=self.es_volume,
                vix=vix_data.get("vix", 0.0),
                vix1d=vix_data.get("vix1d", 0.0),
                vix9d=vix_data.get("vix9d", 0.0),
                vix_futures_m1=vix_data.get("vix_f1", 0.0),
                vix_futures_m2=vix_data.get("vix_f2", 0.0),
                ten_year_yield=0.0,  # Requires separate feed
                dxy=0.0,  # Requires separate feed
                timestamp=get_et_now(),
            )

    async def _update_es_order_book(self) -> None:
        """Fetch and update the ES order book."""
        assert self._adapter is not None

        if self.es_price <= 0:
            return

        self.es_order_book = await self._adapter.fetch_es_order_book(self.es_price)

    # ------------------------------------------------------------------
    # Pull-based fetch methods
    # ------------------------------------------------------------------

    async def fetch_options_chain(
        self, expiry_date: Optional[date] = None
    ) -> OptionsChain:
        """Fetch the complete 0DTE options chain.

        If ``expiry_date`` is None, uses today's trading date.  Returns a
        chain with all strikes from approximately 5 sigma OTM put to
        5 sigma OTM call.  Computes IVs using Newton-Raphson if not
        provided by the data feed.

        Args:
            expiry_date: Override expiry date, or None for today.

        Returns:
            OptionsChain: The fetched options chain.

        Raises:
            RuntimeError: If not connected.
        """
        if not self.is_connected or self._adapter is None:
            raise RuntimeError("Not connected. Call connect() first.")

        if expiry_date is None:
            expiry_date = get_trading_day_expiry()

        spx = self.spx_price
        if spx <= 0:
            spx = await self._adapter.fetch_spx_price()
            if spx > 0:
                self.spx_price = spx

        chain = await self._adapter.fetch_options_chain(expiry_date, spx)
        self.options_chain = chain
        return chain

    async def fetch_market_internals(self) -> MarketInternals:
        """Fetch current market internals snapshot.

        Retrieves NYSE TICK (1-second), TRIN (1-minute), advance/decline
        ratio, up/down volume, and ES cumulative delta.

        Returns:
            MarketInternals: Current internals snapshot.

        Raises:
            RuntimeError: If not connected.
        """
        if not self.is_connected or self._adapter is None:
            raise RuntimeError("Not connected. Call connect() first.")

        internals = await self._adapter.fetch_market_internals()
        self.market_internals = internals
        return internals

    async def fetch_cross_asset_data(self) -> CrossAssetData:
        """Fetch VIX, VIX1D, VIX9D, 10Y yield, DXY, and ES data.

        Returns:
            CrossAssetData: Current cross-asset snapshot.

        Raises:
            RuntimeError: If not connected.
        """
        if not self.is_connected or self._adapter is None:
            raise RuntimeError("Not connected. Call connect() first.")

        vix_data = await self._adapter.fetch_vix_data()

        if isinstance(self._adapter, MockDataProvider):
            cross = self._adapter.generate_cross_asset_data(
                self.spx_price or self._adapter.base_spx,
                vix_data.get("vix", self._adapter.base_vix),
            )
        else:
            cross = CrossAssetData(
                spx_price=self.spx_price,
                es_price=self.es_price,
                es_volume=self.es_volume,
                vix=vix_data.get("vix", 0.0),
                vix1d=vix_data.get("vix1d", 0.0),
                vix9d=vix_data.get("vix9d", 0.0),
                vix_futures_m1=vix_data.get("vix_f1", 0.0),
                vix_futures_m2=vix_data.get("vix_f2", 0.0),
                ten_year_yield=0.0,
                dxy=0.0,
                timestamp=get_et_now(),
            )
        self.cross_asset_data = cross
        return cross

    async def fetch_es_order_book(self) -> ESOrderBook:
        """Fetch ES futures Level 2 order book (top 10 levels).

        Returns:
            ESOrderBook: Current ES order book snapshot.

        Raises:
            RuntimeError: If not connected.
        """
        if not self.is_connected or self._adapter is None:
            raise RuntimeError("Not connected. Call connect() first.")

        if self.es_price <= 0:
            es_data = await self._adapter.fetch_es_data()
            self.es_price = es_data.get("price", 0.0)

        book = await self._adapter.fetch_es_order_book(self.es_price)
        self.es_order_book = book
        return book

    async def fetch_economic_calendar(
        self, target_date: Optional[date] = None
    ) -> List[EconomicEvent]:
        """Fetch scheduled economic events for the day.

        Args:
            target_date: The date to query, or None for the current trading day.

        Returns:
            List of EconomicEvent instances, ordered by time.

        Raises:
            RuntimeError: If not connected.
        """
        if not self.is_connected or self._adapter is None:
            raise RuntimeError("Not connected. Call connect() first.")

        if target_date is None:
            target_date = get_trading_day_expiry()

        events = await self._adapter.fetch_economic_calendar(target_date)
        self.economic_events = events
        return events

    async def fetch_prior_session(self) -> Dict[str, Any]:
        """Fetch prior session data.

        Returns a dict containing:
            close, high, low, VWAP, POC, VIX1D close, GEX profile,
            and 20-day realized volatility.

        Returns:
            Dict[str, Any]: Prior session data.

        Raises:
            RuntimeError: If not connected.
        """
        if not self.is_connected or self._adapter is None:
            raise RuntimeError("Not connected. Call connect() first.")

        prior = await self._adapter.fetch_prior_session()
        self.prior_session = prior
        return prior

    # ------------------------------------------------------------------
    # Time / zone utilities
    # ------------------------------------------------------------------

    def get_minutes_remaining(self) -> int:
        """Calculate minutes remaining until 4:00 PM ET close.

        Returns:
            int: Minutes remaining. Returns 0 if market is closed or past close.
        """
        return minutes_until_close()

    def get_current_time_zone(self) -> str:
        """Determine the current intraday time zone based on ET time.

        Maps the current time to one of the defined intraday trading zones
        as specified in the SCANIFY constants module.

        Returns:
            str: One of PRE_MARKET, OPENING_AUCTION, MORNING_SESSION,
                MIDDAY_LULL, AFTERNOON_ACCEL, POWER_HOUR, SETTLEMENT_WINDOW.
        """
        now = get_et_now()
        current_time = now.time()

        for boundary in INTRADAY_ZONE_SCHEDULE:
            if boundary.start <= current_time < boundary.end:
                return boundary.zone.name

        # Before earliest zone or after latest zone
        if current_time < INTRADAY_ZONE_SCHEDULE[0].start:
            return IntradayZone.PRE_MARKET.name
        return IntradayZone.SETTLEMENT_WINDOW.name

    def is_within_event_buffer(
        self, buffer_minutes: int = 15
    ) -> Tuple[bool, Optional[EconomicEvent]]:
        """Check if the current time is within the buffer window of any economic event.

        Looks at both upcoming events (within ``buffer_minutes`` in the future)
        and recent events (within ``buffer_minutes`` in the past), since the
        market impact window extends both before and after a release.

        Args:
            buffer_minutes: Size of the buffer window on each side of the event.

        Returns:
            Tuple of (is_in_buffer, event_if_any).  ``event_if_any`` is the
            nearest event within the buffer, or None.
        """
        if not self.economic_events:
            return (False, None)

        now = get_et_now()
        buffer = timedelta(minutes=buffer_minutes)
        closest_event: Optional[EconomicEvent] = None
        closest_distance = timedelta.max

        for event in self.economic_events:
            event_dt = event.event_time
            # Ensure timezone-aware comparison
            if event_dt.tzinfo is None:
                event_dt = event_dt.replace(tzinfo=now.tzinfo)

            distance = abs(now - event_dt)
            if distance <= buffer and distance < closest_distance:
                closest_distance = distance
                closest_event = event

        if closest_event is not None:
            return (True, closest_event)
        return (False, None)

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    async def get_snapshot(self) -> Dict[str, Any]:
        """Get a complete market snapshot with all current data for scanner consumption.

        Returns a dict with all current data, time context, staleness
        indicators, and derived metrics.  This is the primary interface
        for scanner modules to consume market data.

        Returns:
            Dict containing:
                - spx_price (float)
                - es_price (float)
                - es_volume (int)
                - options_chain (OptionsChain or None)
                - market_internals (MarketInternals or None)
                - cross_asset_data (CrossAssetData or None)
                - es_order_book (ESOrderBook or None)
                - economic_events (list[EconomicEvent])
                - prior_session (dict)
                - minutes_remaining (int)
                - time_zone (str)
                - in_event_buffer (bool)
                - buffer_event (EconomicEvent or None)
                - market_open (bool)
                - last_update (datetime or None)
                - is_connected (bool)
                - data_quality (dict)
        """
        in_buffer, buffer_event = self.is_within_event_buffer()

        # Assess data quality / staleness
        now = get_et_now()
        stale_threshold = timedelta(seconds=30)
        data_quality: Dict[str, Any] = {
            "spx_stale": (
                self.last_update is not None
                and (now - self.last_update) > stale_threshold
            ),
            "options_chain_stale": (
                self.options_chain is not None
                and hasattr(self.options_chain, "timestamp")
                and (now - self.options_chain.timestamp) > timedelta(seconds=60)
            ),
            "has_spx_price": self.spx_price > 0,
            "has_options_chain": (
                self.options_chain is not None
                and bool(self.options_chain.quotes)
            ),
            "has_internals": self.market_internals is not None,
            "has_cross_asset": self.cross_asset_data is not None,
            "has_order_book": (
                self.es_order_book is not None
                and bool(self.es_order_book.bids)
            ),
            "has_prior_session": bool(self.prior_session),
            "seconds_since_update": (
                (now - self.last_update).total_seconds()
                if self.last_update
                else None
            ),
        }

        return {
            # Prices
            "spx_price": self.spx_price,
            "es_price": self.es_price,
            "es_volume": self.es_volume,
            # Data objects
            "options_chain": self.options_chain,
            "market_internals": self.market_internals,
            "cross_asset_data": self.cross_asset_data,
            "es_order_book": self.es_order_book,
            "economic_events": self.economic_events,
            "prior_session": self.prior_session,
            # Time context
            "minutes_remaining": self.get_minutes_remaining(),
            "time_zone": self.get_current_time_zone(),
            "in_event_buffer": in_buffer,
            "buffer_event": buffer_event,
            "market_open": is_market_open(),
            # Meta
            "last_update": self.last_update,
            "is_connected": self.is_connected,
            "data_quality": data_quality,
        }

    # ------------------------------------------------------------------
    # Dunder / repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"DataFeedManager("
            f"provider={self._provider_name!r}, "
            f"connected={self.is_connected}, "
            f"spx={self.spx_price:.2f}, "
            f"es={self.es_price:.2f})"
        )


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------

__all__ = [
    # Classes
    "DataFeedManager",
    "MockDataProvider",
    "PolygonDataAdapter",
    "BaseDataAdapter",
    # Helper functions
    "get_trading_day_expiry",
    "minutes_until_close",
    "is_market_open",
    "get_et_now",
    # IV computation
    "compute_iv_newton",
]
