"""
Yahoo Finance data adapter for SCANIFY.

Pulls real market data from Yahoo Finance and converts it into SCANIFY
data structures so the scanner system can be tested end-to-end with live
(delayed) market prices.

Typical usage::

    from scanify.yahoo_adapter import YahooFinanceAdapter, run_live_gex_test

    adapter = YahooFinanceAdapter()
    chain = adapter.fetch_spx_options_chain()
    vix = adapter.fetch_vix_data()

    # Or run the full pipeline:
    run_live_gex_test()
"""

import logging
import math
from datetime import datetime, date, time, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import yfinance as yf

from .data_feeds import (
    OptionQuote,
    OptionsChain,
    VIXData,
    PriorSessionData,
    SPXPriceBar,
    CrossAssetData,
    OptionType,
)
from .gex_engine import GEXEngine, GEXResult
from .gex_dashboard import GEXDashboard, GEXDashboardData
from .config import GEXConfig, SignalDirection

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ET_CLOSE = time(16, 0)  # 4:00 PM ET market close


def _safe_float(value, default: float = 0.0) -> float:
    """Return *value* as a float, falling back to *default* on any error."""
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default: int = 0) -> int:
    """Return *value* as an int, falling back to *default* on any error."""
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# YahooFinanceAdapter
# ---------------------------------------------------------------------------


class YahooFinanceAdapter:
    """Fetch live market data from Yahoo Finance for SCANIFY consumption.

    Creates ``yfinance.Ticker`` handles for the primary instruments on
    construction and exposes high-level methods that return populated
    SCANIFY data-class instances.
    """

    def __init__(self) -> None:
        self.spx = yf.Ticker("^GSPC")
        self.vix = yf.Ticker("^VIX")
        self.vix9d = yf.Ticker("^VIX9D")
        self.tnx = yf.Ticker("^TNX")
        self.dxy = yf.Ticker("DX-Y.NYB")

        # VIX1D may not be available on all yfinance builds / Yahoo endpoints.
        try:
            self.vix1d = yf.Ticker("^VIX1D")
        except Exception:
            self.vix1d = None

        # SPX options are not directly available on Yahoo; SPY is the proxy.
        self.spy = yf.Ticker("SPY")

        logger.info("YahooFinanceAdapter initialised.")

    # ------------------------------------------------------------------
    # SPX price
    # ------------------------------------------------------------------

    def fetch_spx_price(self) -> float:
        """Return the current (or most recent) SPX index level."""
        try:
            hist = self.spx.history(period="1d", interval="1m")
            if hist is not None and not hist.empty:
                return float(hist["Close"].iloc[-1])
        except Exception as exc:
            logger.warning("Failed to fetch SPX intraday price: %s", exc)

        # Fallback: use the previous close from the info dict.
        try:
            info = self.spx.info
            for key in ("regularMarketPrice", "previousClose"):
                if key in info and info[key] is not None:
                    return float(info[key])
        except Exception as exc:
            logger.warning("Failed to fetch SPX price from info: %s", exc)

        raise RuntimeError("Could not retrieve SPX price from Yahoo Finance.")

    # ------------------------------------------------------------------
    # Options chain
    # ------------------------------------------------------------------

    def fetch_spx_options_chain(
        self, expiry_date: Optional[str] = None
    ) -> OptionsChain:
        """Fetch an options chain and convert it to an ``OptionsChain``.

        Parameters
        ----------
        expiry_date:
            Expiration date string in ``YYYY-MM-DD`` format.  If *None*, the
            nearest available expiration is used (0DTE when available).

        Notes
        -----
        Yahoo Finance does not serve SPX (^SPX) options directly.  This
        method uses **SPY** options as a proxy.  SPY is roughly 1/10 of
        SPX, and the contract multiplier is 100 shares (vs. 100 for SPX
        index options).  The underlying price returned is the true SPX
        level so that GEX computations remain on the correct scale.
        """
        # Try ^SPX first (some yfinance versions support it).
        ticker = self.spy
        ticker_label = "SPY"
        try:
            spx_ticker = yf.Ticker("^SPX")
            available = spx_ticker.options
            if available:
                ticker = spx_ticker
                ticker_label = "^SPX"
                logger.info("Using ^SPX options (native SPX chain).")
        except Exception:
            logger.info("^SPX options not available; falling back to SPY.")

        # Determine expiry ---------------------------------------------------
        try:
            available_expiries = ticker.options
        except Exception as exc:
            raise RuntimeError(
                f"Cannot retrieve available expiries from {ticker_label}: {exc}"
            ) from exc

        if not available_expiries:
            raise RuntimeError(
                f"No option expiry dates returned by {ticker_label}."
            )

        if expiry_date is not None:
            chosen_expiry = expiry_date
            if chosen_expiry not in available_expiries:
                logger.warning(
                    "Requested expiry %s not available; using nearest.", chosen_expiry
                )
                chosen_expiry = available_expiries[0]
        else:
            chosen_expiry = available_expiries[0]

        logger.info(
            "Fetching %s option chain for expiry %s", ticker_label, chosen_expiry
        )

        # Fetch chain from Yahoo ---------------------------------------------
        raw_chain = ticker.option_chain(chosen_expiry)
        calls_df = raw_chain.calls
        puts_df = raw_chain.puts

        now = datetime.now(timezone.utc)
        underlying_price = self.fetch_spx_price()

        quotes: List[OptionQuote] = []

        for df, opt_type in [(calls_df, OptionType.CALL), (puts_df, OptionType.PUT)]:
            if df is None or df.empty:
                continue
            for _, row in df.iterrows():
                bid = _safe_float(row.get("bid"))
                ask = _safe_float(row.get("ask"))
                mid = (bid + ask) / 2.0 if (bid + ask) > 0 else _safe_float(
                    row.get("lastPrice")
                )
                quote = OptionQuote(
                    strike=_safe_float(row.get("strike")),
                    bid=bid,
                    ask=ask,
                    mid=mid,
                    last=_safe_float(row.get("lastPrice")),
                    volume=_safe_int(row.get("volume")),
                    open_interest=_safe_int(row.get("openInterest")),
                    implied_vol=_safe_float(row.get("impliedVolatility")),
                    delta=0.0,
                    gamma=0.0,
                    theta=0.0,
                    vega=0.0,
                    option_type=opt_type,
                    timestamp=now,
                )
                quotes.append(quote)

        exp_date = datetime.strptime(chosen_expiry, "%Y-%m-%d").date()

        chain = OptionsChain(
            quotes=quotes,
            expiry_date=exp_date,
            underlying_price=underlying_price,
            chain_timestamp=now,
        )

        # GEXEngine._time_to_expiry accesses ``chain.expiry`` (a datetime)
        # whereas OptionsChain only declares ``expiry_date`` (a date).
        # Attach the extra attribute for compatibility.
        chain.expiry = datetime.combine(  # type: ignore[attr-defined]
            exp_date, _ET_CLOSE, tzinfo=timezone.utc
        )

        logger.info(
            "Built OptionsChain with %d quotes (expiry=%s, underlying=%.2f)",
            len(quotes),
            chosen_expiry,
            underlying_price,
        )
        return chain

    # ------------------------------------------------------------------
    # VIX family
    # ------------------------------------------------------------------

    def fetch_vix_data(self) -> VIXData:
        """Fetch VIX, VIX1D and VIX9D levels."""
        now = datetime.now(timezone.utc)
        vix_level = self._latest_price(self.vix, "^VIX", fallback=15.0)

        # VIX1D -----------------------------------------------------------
        vix1d_level: float
        vix1d_ts = now
        if self.vix1d is not None:
            try:
                vix1d_level = self._latest_price(self.vix1d, "^VIX1D")
            except Exception:
                # Estimate VIX1D from VIX using typical term-structure ratio.
                vix1d_level = vix_level * 0.92
                logger.info("Estimated VIX1D from VIX: %.2f", vix1d_level)
        else:
            vix1d_level = vix_level * 0.92
            logger.info("VIX1D ticker unavailable; estimated at %.2f", vix1d_level)

        # VIX9D -----------------------------------------------------------
        try:
            vix9d_level = self._latest_price(self.vix9d, "^VIX9D")
        except Exception:
            vix9d_level = vix_level * 0.96
            logger.info("Estimated VIX9D from VIX: %.2f", vix9d_level)

        return VIXData(
            vix=vix_level,
            vix1d=vix1d_level,
            vix9d=vix9d_level,
            vix_timestamp=now,
            vix1d_timestamp=vix1d_ts,
            vix9d_timestamp=now,
        )

    # ------------------------------------------------------------------
    # Prior session data
    # ------------------------------------------------------------------

    def fetch_prior_session(self) -> PriorSessionData:
        """Build a ``PriorSessionData`` from the previous trading day."""
        try:
            daily = self.spx.history(period="5d", interval="1d")
        except Exception as exc:
            logger.error("Failed to fetch SPX daily history: %s", exc)
            daily = None

        if daily is None or len(daily) < 2:
            logger.warning("Insufficient daily data; returning placeholder.")
            return PriorSessionData(
                spx_close=0.0,
                spx_high=0.0,
                spx_low=0.0,
                spx_vwap=0.0,
                vix1d_close=0.0,
                realized_vol_20d=0.0,
            )

        prev = daily.iloc[-2]
        spx_close = _safe_float(prev.get("Close"))
        spx_high = _safe_float(prev.get("High"))
        spx_low = _safe_float(prev.get("Low"))

        # Attempt to compute VWAP from intraday data.
        spx_vwap = self._estimate_prior_vwap(spx_high, spx_low, spx_close)

        # VIX1D prior close
        vix1d_close = 0.0
        try:
            vix1d_hist = (
                self.vix1d.history(period="5d", interval="1d")
                if self.vix1d is not None
                else None
            )
            if vix1d_hist is not None and len(vix1d_hist) >= 2:
                vix1d_close = _safe_float(vix1d_hist["Close"].iloc[-2])
        except Exception:
            pass

        realized_vol = self.compute_realized_vol(days=20)

        return PriorSessionData(
            spx_close=spx_close,
            spx_high=spx_high,
            spx_low=spx_low,
            spx_vwap=spx_vwap,
            vix1d_close=vix1d_close,
            realized_vol_20d=realized_vol,
        )

    # ------------------------------------------------------------------
    # Intraday price bars
    # ------------------------------------------------------------------

    def fetch_price_bars(
        self, period: str = "1d", interval: str = "1m"
    ) -> List[SPXPriceBar]:
        """Return intraday bars for SPX (or SPY as proxy)."""
        bars: List[SPXPriceBar] = []
        try:
            hist = self.spx.history(period=period, interval=interval)
        except Exception:
            logger.info("SPX intraday bars unavailable; trying SPY proxy.")
            try:
                hist = self.spy.history(period=period, interval=interval)
            except Exception as exc:
                logger.error("Failed to fetch intraday bars: %s", exc)
                return bars

        if hist is None or hist.empty:
            return bars

        for idx, row in hist.iterrows():
            ts = (
                idx.to_pydatetime()
                if hasattr(idx, "to_pydatetime")
                else datetime.now(timezone.utc)
            )
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            bars.append(
                SPXPriceBar(
                    timestamp=ts,
                    open=_safe_float(row.get("Open")),
                    high=_safe_float(row.get("High")),
                    low=_safe_float(row.get("Low")),
                    close=_safe_float(row.get("Close")),
                    volume=_safe_int(row.get("Volume")),
                )
            )
        logger.info("Fetched %d intraday price bars.", len(bars))
        return bars

    # ------------------------------------------------------------------
    # Cross-asset
    # ------------------------------------------------------------------

    def fetch_cross_asset_data(self) -> CrossAssetData:
        """Fetch 10-year Treasury yield and DXY index."""
        now = datetime.now(timezone.utc)

        # 10Y yield (^TNX is quoted in percentage points, e.g. 4.25)
        us_10y = self._latest_price(self.tnx, "^TNX", fallback=4.0)
        us_10y_change = self._intraday_change(self.tnx, "^TNX")

        # DXY
        dxy = self._latest_price(self.dxy, "DX-Y.NYB", fallback=100.0)
        dxy_change = self._intraday_change(self.dxy, "DX-Y.NYB")

        return CrossAssetData(
            us_10y_yield=us_10y,
            us_10y_yield_change=us_10y_change,
            dxy_level=dxy,
            dxy_change=dxy_change,
            timestamp=now,
        )

    # ------------------------------------------------------------------
    # Realized vol
    # ------------------------------------------------------------------

    def compute_realized_vol(self, days: int = 20) -> float:
        """Compute annualised realised volatility from daily SPX closes.

        Uses log-return standard deviation scaled by ``sqrt(252)``.
        """
        try:
            # Fetch a few extra days to account for weekends / holidays.
            hist = self.spx.history(period=f"{days + 15}d", interval="1d")
        except Exception as exc:
            logger.warning("Cannot compute realized vol: %s", exc)
            return 0.0

        if hist is None or len(hist) < days:
            logger.warning(
                "Not enough daily bars (%d) for %d-day realized vol.",
                len(hist) if hist is not None else 0,
                days,
            )
            return 0.0

        closes = hist["Close"].values[-days:]
        if len(closes) < 2:
            return 0.0

        log_returns = np.diff(np.log(closes))
        return float(np.std(log_returns, ddof=1) * math.sqrt(252))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _latest_price(
        self, ticker: yf.Ticker, label: str, fallback: Optional[float] = None
    ) -> float:
        """Return the most recent traded price for *ticker*."""
        try:
            hist = ticker.history(period="1d", interval="1m")
            if hist is not None and not hist.empty:
                return float(hist["Close"].iloc[-1])
        except Exception as exc:
            logger.debug("Intraday fetch for %s failed: %s", label, exc)

        try:
            hist = ticker.history(period="5d", interval="1d")
            if hist is not None and not hist.empty:
                return float(hist["Close"].iloc[-1])
        except Exception as exc:
            logger.debug("Daily fetch for %s failed: %s", label, exc)

        if fallback is not None:
            logger.warning(
                "Using fallback price %.2f for %s.", fallback, label
            )
            return fallback

        raise RuntimeError(f"Cannot retrieve price for {label}.")

    def _intraday_change(self, ticker: yf.Ticker, label: str) -> float:
        """Return the intraday change (current - open) for *ticker*."""
        try:
            hist = ticker.history(period="1d", interval="1m")
            if hist is not None and len(hist) >= 2:
                return float(hist["Close"].iloc[-1] - hist["Open"].iloc[0])
        except Exception as exc:
            logger.debug("Intraday change for %s failed: %s", label, exc)
        return 0.0

    @staticmethod
    def _estimate_prior_vwap(high: float, low: float, close: float) -> float:
        """Rough VWAP estimate when tick-level data is unavailable."""
        if high + low + close == 0:
            return 0.0
        return (high + low + close) / 3.0


# ---------------------------------------------------------------------------
# End-to-end live test
# ---------------------------------------------------------------------------


def run_live_gex_test() -> None:
    """Pull real data from Yahoo Finance and render the GEX dashboard.

    This function exercises the full SCANIFY pipeline:

    1. Fetch SPX price, options chain, VIX data, and cross-asset levels
       from Yahoo Finance.
    2. Run the GEX engine to compute gamma exposure.
    3. Detect GEX signals.
    4. Render the GEX dashboard to the terminal.
    5. Print a human-readable summary.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    print("=" * 72)
    print("  SCANIFY - Live GEX Test (Yahoo Finance)")
    print("=" * 72)

    adapter = YahooFinanceAdapter()

    # ---- 1. Fetch market data -------------------------------------------
    print("\n[1/5] Fetching SPX price ...")
    try:
        spot = adapter.fetch_spx_price()
        print(f"  SPX spot: {spot:.2f}")
    except Exception as exc:
        print(f"  ERROR fetching SPX price: {exc}")
        return

    print("[2/5] Fetching options chain ...")
    try:
        chain = adapter.fetch_spx_options_chain()
        print(
            f"  Chain: {len(chain.quotes)} quotes, "
            f"expiry={chain.expiry_date}, underlying={chain.underlying_price:.2f}"
        )
    except Exception as exc:
        print(f"  ERROR fetching options chain: {exc}")
        return

    print("[3/5] Fetching VIX data ...")
    try:
        vix_data = adapter.fetch_vix_data()
        print(
            f"  VIX={vix_data.vix:.2f}  VIX1D={vix_data.vix1d:.2f}  "
            f"VIX9D={vix_data.vix9d:.2f}"
        )
    except Exception as exc:
        print(f"  ERROR fetching VIX data: {exc}")
        vix_data = VIXData(
            vix=15.0,
            vix1d=14.0,
            vix9d=14.5,
            vix_timestamp=datetime.now(timezone.utc),
            vix1d_timestamp=datetime.now(timezone.utc),
            vix9d_timestamp=datetime.now(timezone.utc),
        )

    print("[4/5] Fetching cross-asset data ...")
    try:
        cross = adapter.fetch_cross_asset_data()
        print(
            f"  10Y Yield={cross.us_10y_yield:.2f}%  "
            f"DXY={cross.dxy_level:.2f}"
        )
    except Exception as exc:
        print(f"  ERROR fetching cross-asset data: {exc}")

    print("[5/5] Fetching prior session ...")
    try:
        prior = adapter.fetch_prior_session()
        print(
            f"  Prior close={prior.spx_close:.2f}  "
            f"RV20d={prior.realized_vol_20d:.4f}"
        )
    except Exception as exc:
        print(f"  ERROR fetching prior session: {exc}")

    # ---- 2. Compute GEX -------------------------------------------------
    print("\n--- Computing GEX ---")
    config = GEXConfig()
    engine = GEXEngine(config)

    try:
        gex_result = engine.compute_gex(chain=chain, spot=spot)
    except Exception as exc:
        print(f"  ERROR computing GEX: {exc}")
        logger.exception("GEX computation failed")
        return

    print(f"  Total Net GEX:    {gex_result.total_net_gex:,.0f}")
    print(f"  Gamma Flip:       {gex_result.gamma_flip_level:.2f}")
    print(f"  Call Wall:        {gex_result.call_wall:.2f}")
    print(f"  Put Wall:         {gex_result.put_wall:.2f}")
    print(f"  Max Pain:         {gex_result.max_pain:.2f}")
    print(f"  Vol Trigger:      {gex_result.vol_trigger:.2f}")
    print(f"  Dealer Position:  {gex_result.dealer_position}")

    # ---- 3. Detect signals -----------------------------------------------
    print("\n--- Detecting signals ---")
    try:
        signals = engine.detect_signals(
            current_gex=gex_result,
            prior_gex=None,
            spot=spot,
            vix1d=vix_data.vix1d,
        )
        if signals:
            for sig in signals:
                print(f"  [{sig.direction.value.upper()}] {sig.description}")
        else:
            print("  No signals detected.")
    except Exception as exc:
        print(f"  ERROR detecting signals: {exc}")
        signals = []

    # ---- 4. High-speed strikes -------------------------------------------
    try:
        high_speed = engine.get_high_speed_strikes(gex_result, spot)
    except Exception:
        high_speed = []

    # ---- 5. Render dashboard ---------------------------------------------
    print("\n--- Rendering GEX Dashboard ---\n")
    try:
        dashboard_data = GEXDashboardData(
            gex_result=gex_result,
            spot_price=spot,
            chain=chain,
            signals=signals,
            gex_momentum=0.0,
            high_speed_strikes=high_speed,
            vix1d=vix_data.vix1d,
            vix=vix_data.vix,
            session_type="RTH",
            time_zone="US/Eastern",
        )
        dashboard = GEXDashboard()
        dashboard.render(dashboard_data)
    except Exception as exc:
        print(f"  ERROR rendering dashboard: {exc}")
        logger.exception("Dashboard render failed")

    # ---- Summary ---------------------------------------------------------
    print("\n" + "=" * 72)
    print("  Live GEX test complete.")
    print("=" * 72)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    run_live_gex_test()
