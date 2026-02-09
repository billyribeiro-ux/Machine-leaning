"""
SCANIFY Data Feeds — Market data structures and feed management for the 0DTE SPX scanner.

Defines all data classes representing market data inputs (option quotes, futures,
VIX, market internals, economic events, cross-asset), the VIX1D expected-move
analyzer, and the central DataFeedManager that aggregates live feed state.
"""

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np

from .config import TimeZone


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class OptionType(Enum):
    """Option contract side."""
    CALL = "call"
    PUT = "put"


class ImpactLevel(Enum):
    """Economic event impact classification."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ---------------------------------------------------------------------------
# Data classes — Market Data Inputs
# ---------------------------------------------------------------------------

@dataclass
class OptionQuote:
    """A single option quote for one strike in the 0DTE chain.

    Attributes:
        strike: Strike price.
        bid: Current best bid.
        ask: Current best ask.
        mid: Mid-market price ((bid + ask) / 2).
        last: Last traded price.
        volume: Cumulative session volume.
        open_interest: Open interest at start of day.
        implied_vol: Implied volatility (annualized, decimal).
        delta: Option delta.
        gamma: Option gamma.
        theta: Option theta.
        vega: Option vega.
        option_type: CALL or PUT.
        timestamp: Quote observation time.
    """
    strike: float
    bid: float
    ask: float
    mid: float
    last: float
    volume: int
    open_interest: int
    implied_vol: float
    delta: float
    gamma: float
    theta: float
    vega: float
    option_type: OptionType
    timestamp: datetime


@dataclass
class OptionsChain:
    """Full 0DTE SPX options chain snapshot.

    Attributes:
        quotes: All option quotes in this chain snapshot.
        expiry_date: Expiration date (today for 0DTE).
        underlying_price: Current SPX cash index price.
        chain_timestamp: Time this chain snapshot was captured.
    """
    quotes: List[OptionQuote]
    expiry_date: date
    underlying_price: float
    chain_timestamp: datetime


@dataclass
class MarketInternalsData:
    """NYSE market-breadth internals used for directional scoring.

    Attributes:
        tick: NYSE TICK index (net uptick - downtick issues).
        trin: TRIN (Arms Index). Values < 1 are bullish, > 1 bearish.
        ad_ratio: Advance / Decline ratio.
        up_volume: Aggregate up-volume on NYSE (shares).
        down_volume: Aggregate down-volume on NYSE (shares).
        cumulative_delta: Intraday cumulative delta (bid vs ask volume).
        timestamp: Observation time.
    """
    tick: float
    trin: float
    ad_ratio: float
    up_volume: float
    down_volume: float
    cumulative_delta: float
    timestamp: datetime


@dataclass
class FuturesData:
    """E-mini S&P 500 (ES) futures data.

    Attributes:
        price: Last traded ES price.
        volume: Session cumulative volume.
        open_interest: Current open interest.
        bid_depth: Top 10 bid levels as (price, size) tuples, best first.
        ask_depth: Top 10 ask levels as (price, size) tuples, best first.
        timestamp: Observation time.
    """
    price: float
    volume: int
    open_interest: int
    bid_depth: List[Tuple[float, int]]
    ask_depth: List[Tuple[float, int]]
    timestamp: datetime


@dataclass
class VIXData:
    """CBOE Volatility Index family snapshot.

    Attributes:
        vix: VIX (30-day implied vol index).
        vix1d: VIX1D (1-day expected move index — primary for 0DTE).
        vix9d: VIX9D (9-day implied vol index).
        vix_timestamp: VIX observation time.
        vix1d_timestamp: VIX1D observation time.
        vix9d_timestamp: VIX9D observation time.
    """
    vix: float
    vix1d: float
    vix9d: float
    vix_timestamp: datetime
    vix1d_timestamp: datetime
    vix9d_timestamp: datetime


@dataclass
class EconomicEvent:
    """Scheduled economic release or event.

    Attributes:
        time: Scheduled release time (Eastern).
        name: Event name (e.g., "CPI", "FOMC Statement").
        impact_level: Expected market impact (LOW / MEDIUM / HIGH).
        expected_value: Consensus forecast (string to support varied formats).
        previous_value: Prior release value.
        actual_value: Actual released value; None before release.
    """
    time: datetime
    name: str
    impact_level: ImpactLevel
    expected_value: str
    previous_value: str
    actual_value: Optional[str] = None


@dataclass
class PriorSessionData:
    """Prior trading session reference levels.

    Attributes:
        spx_close: Prior day SPX closing price.
        spx_high: Prior day SPX session high.
        spx_low: Prior day SPX session low.
        spx_vwap: Prior day SPX VWAP.
        vix1d_close: Prior day VIX1D close.
        realized_vol_20d: 20-day realized (historical) volatility, annualized decimal.
    """
    spx_close: float
    spx_high: float
    spx_low: float
    spx_vwap: float
    vix1d_close: float
    realized_vol_20d: float


@dataclass
class SPXPriceBar:
    """One-minute SPX cash index price bar.

    Attributes:
        timestamp: Bar open timestamp.
        open: Open price.
        high: High price.
        low: Low price.
        close: Close price.
        volume: Bar volume.
    """
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass
class CrossAssetData:
    """Cross-asset context signals.

    Attributes:
        us_10y_yield: US 10-year Treasury yield (decimal, e.g. 0.045 = 4.5%).
        us_10y_yield_change: Intraday change in 10-year yield (bps).
        dxy_level: US Dollar Index level.
        dxy_change: Intraday percentage change in DXY.
        timestamp: Observation time.
    """
    us_10y_yield: float
    us_10y_yield_change: float
    dxy_level: float
    dxy_change: float
    timestamp: datetime


# ---------------------------------------------------------------------------
# VIX1D Analyzer
# ---------------------------------------------------------------------------

class VIX1DAnalyzer:
    """Calculates expected-move boundaries and vol-regime classification
    from VIX1D and related inputs.

    The three expected-move methods and their blend follow the SCANIFY spec:

    * Method 1 (VIX1D):  EM = SPX * (VIX1D / 100) / sqrt(252)
    * Method 2 (Straddle): EM = 0.85 * ATM_straddle_price
    * Method 3 (RV-adjusted): scales Method 1 by IV/RV ratio
    * Blended: 40 % M1 + 40 % M2 + 20 % M3  (default weights)

    Risk-premium adjustment per Albers (2025): subtract 0.16 vol points
    from VIX1D before any calculation.
    """

    # Albers (2025) empirical VIX1D risk-premium offset (vol points).
    RISK_PREMIUM_OFFSET: float = 0.16

    # Trading days in a year for annualized -> daily conversion.
    TRADING_DAYS_PER_YEAR: int = 252

    # Default blended expected-move weights: VIX1D, straddle, RV-adjusted.
    DEFAULT_WEIGHTS: Tuple[float, float, float] = (0.40, 0.40, 0.20)

    # Straddle-to-expected-move empirical multiplier.
    STRADDLE_MULTIPLIER: float = 0.85

    # -------------------------------------------------------------------
    # Expected-move calculations
    # -------------------------------------------------------------------

    def calculate_expected_move(
        self,
        spx_price: float,
        vix1d: float,
    ) -> Dict[str, float]:
        """Calculate 1-sigma and 2-sigma expected move from VIX1D (Method 1).

        Formula:  EM_1sigma = SPX * (VIX1D / 100) / sqrt(252)

        Args:
            spx_price: Current SPX cash index price.
            vix1d: VIX1D level (index points, e.g. 14.5).

        Returns:
            Dict with keys:
                ``em_1sigma`` — 1 standard-deviation expected move (points).
                ``em_2sigma`` — 2 standard-deviation expected move (points).
                ``upper_1sigma`` — SPX + 1-sigma.
                ``lower_1sigma`` — SPX - 1-sigma.
                ``upper_2sigma`` — SPX + 2-sigma.
                ``lower_2sigma`` — SPX - 2-sigma.
        """
        daily_vol = (vix1d / 100.0) / math.sqrt(self.TRADING_DAYS_PER_YEAR)
        em_1 = spx_price * daily_vol
        em_2 = em_1 * 2.0

        return {
            "em_1sigma": round(em_1, 2),
            "em_2sigma": round(em_2, 2),
            "upper_1sigma": round(spx_price + em_1, 2),
            "lower_1sigma": round(spx_price - em_1, 2),
            "upper_2sigma": round(spx_price + em_2, 2),
            "lower_2sigma": round(spx_price - em_2, 2),
        }

    def calculate_straddle_expected_move(
        self,
        atm_straddle_price: float,
    ) -> Dict[str, float]:
        """Calculate expected move from the ATM straddle price (Method 2).

        Formula:  EM = 0.85 * ATM_straddle_price

        The 0.85 multiplier reflects the empirical observation that
        markets move about 85 % of the straddle price on average.

        Args:
            atm_straddle_price: Combined ATM call + put mid price.

        Returns:
            Dict with ``em_straddle`` (expected move in SPX points).
        """
        em = self.STRADDLE_MULTIPLIER * atm_straddle_price
        return {"em_straddle": round(em, 2)}

    def calculate_rv_adjusted_expected_move(
        self,
        spx_price: float,
        vix1d: float,
        rv_20day: float,
    ) -> Dict[str, float]:
        """Calculate RV-adjusted expected move (Method 3).

        When implied vol (VIX1D) exceeds realized vol, the unadjusted
        expected move overstates the likely range.  This method scales
        the VIX1D-derived move by the IV / RV ratio so that:

        * IV/RV > 1  ->  expected move is *reduced* (IV is rich)
        * IV/RV < 1  ->  expected move is *increased* (IV is cheap)
        * IV/RV == 1 ->  identical to Method 1

        Specifically:
            adjusted_vol = vix1d * (2 / (1 + iv_rv_ratio))

        This produces a dampened adjustment: at IV/RV = 1.5 the adjusted
        vol is ~80 % of VIX1D rather than a naive 67 %.

        Args:
            spx_price: Current SPX cash index price.
            vix1d: VIX1D level (index points).
            rv_20day: 20-day realized volatility (annualized, decimal e.g. 0.12).

        Returns:
            Dict with ``em_rv_adjusted``, ``iv_rv_ratio``, ``adjusted_vol``.
        """
        iv_decimal = vix1d / 100.0
        if rv_20day <= 0:
            # Fallback: if RV is unavailable / zero, use unadjusted.
            iv_rv_ratio = 1.0
        else:
            iv_rv_ratio = iv_decimal / rv_20day

        # Dampened adjustment factor: 2 / (1 + ratio).
        adjusted_vol = iv_decimal * (2.0 / (1.0 + iv_rv_ratio))
        daily_adjusted = adjusted_vol / math.sqrt(self.TRADING_DAYS_PER_YEAR)
        em = spx_price * daily_adjusted

        return {
            "em_rv_adjusted": round(em, 2),
            "iv_rv_ratio": round(iv_rv_ratio, 4),
            "adjusted_vol": round(adjusted_vol, 6),
        }

    def calculate_blended_expected_move(
        self,
        spx_price: float,
        vix1d: float,
        atm_straddle_price: float,
        rv_20day: float,
        weights: Optional[Tuple[float, float, float]] = None,
    ) -> Dict[str, float]:
        """Blended expected move combining all three methods.

        Default weights (per spec): 40 % VIX1D + 40 % Straddle + 20 % RV.

        Args:
            spx_price: Current SPX cash index price.
            vix1d: VIX1D level (index points).
            atm_straddle_price: ATM straddle mid price.
            rv_20day: 20-day realized volatility (annualized decimal).
            weights: Optional (w1, w2, w3) override; must sum to 1.0.

        Returns:
            Dict with ``blended_em``, individual method EMs, weights used,
            and upper/lower boundaries.
        """
        w1, w2, w3 = weights if weights is not None else self.DEFAULT_WEIGHTS

        # Validate weights sum to ~1.0.
        weight_sum = w1 + w2 + w3
        if not math.isclose(weight_sum, 1.0, abs_tol=1e-6):
            raise ValueError(
                f"Blended weights must sum to 1.0, got {weight_sum:.6f}"
            )

        m1 = self.calculate_expected_move(spx_price, vix1d)["em_1sigma"]
        m2 = self.calculate_straddle_expected_move(atm_straddle_price)["em_straddle"]
        m3 = self.calculate_rv_adjusted_expected_move(spx_price, vix1d, rv_20day)[
            "em_rv_adjusted"
        ]

        blended = w1 * m1 + w2 * m2 + w3 * m3

        return {
            "blended_em": round(blended, 2),
            "method1_em": m1,
            "method2_em": m2,
            "method3_em": m3,
            "weights": (w1, w2, w3),
            "upper_bound": round(spx_price + blended, 2),
            "lower_bound": round(spx_price - blended, 2),
        }

    # -------------------------------------------------------------------
    # Vol-regime assessment
    # -------------------------------------------------------------------

    def assess_vol_regime(self, vix1d: float) -> Dict:
        """Classify the current VIX1D level into a volatility regime.

        Regime boundaries (VIX1D index points):
            * Ultra-low:   < 10
            * Low:         10 - 14
            * Normal:      14 - 20
            * Elevated:    20 - 28
            * High:        28 - 40
            * Extreme:     >= 40

        Args:
            vix1d: Current VIX1D level.

        Returns:
            Dict with ``regime`` (str), ``description`` (str),
            ``premium_sell_favorable`` (bool), ``directional_favorable`` (bool),
            and ``recommendations`` (list of str).
        """
        if vix1d < 10:
            regime = "ultra_low"
            description = "Suppressed implied vol; 0DTE premiums very thin."
            premium_sell = False
            directional = False
            recommendations = [
                "Premiums too low for credit spreads — stand aside or use debit structures.",
                "Expected moves are small; directional edges are minimal.",
                "Watch for vol expansion catalysts (event risk, VIX term-structure inversion).",
            ]
        elif vix1d < 14:
            regime = "low"
            description = "Below-average implied vol; modest premiums."
            premium_sell = True
            directional = False
            recommendations = [
                "Favor tight credit spreads with high probability of OTM expiry.",
                "Reduce position sizing — reward/risk on directional trades is thin.",
                "Monitor for regime transition toward normal.",
            ]
        elif vix1d < 20:
            regime = "normal"
            description = "Average implied vol; balanced opportunity set."
            premium_sell = True
            directional = True
            recommendations = [
                "All three scan types are viable.",
                "Standard strike selection and sizing apply.",
                "Expected-move boundaries are reliable reference levels.",
            ]
        elif vix1d < 28:
            regime = "elevated"
            description = "Above-average implied vol; richer premiums, wider moves."
            premium_sell = True
            directional = True
            recommendations = [
                "Widen credit-spread strikes to accommodate larger moves.",
                "Increase directional delta targets for risk-adjusted return.",
                "Tighten time stops — theta decay is faster but gap risk rises.",
            ]
        elif vix1d < 40:
            regime = "high"
            description = "High implied vol; large expected moves, elevated risk."
            premium_sell = False
            directional = True
            recommendations = [
                "Avoid premium selling — tail risk is significant.",
                "Directional trades with tight stops can exploit large swings.",
                "Reduce overall position sizing by 50 %.",
                "Watch for VIX1D mean-reversion as potential fade signal.",
            ]
        else:
            regime = "extreme"
            description = "Crisis-level implied vol; dislocated markets."
            premium_sell = False
            directional = False
            recommendations = [
                "Suspend automated scanning — market microstructure unreliable.",
                "Manual oversight required for any 0DTE activity.",
                "Spreads will be exceptionally wide; slippage risk is extreme.",
            ]

        return {
            "regime": regime,
            "vix1d": vix1d,
            "description": description,
            "premium_sell_favorable": premium_sell,
            "directional_favorable": directional,
            "recommendations": recommendations,
        }

    # -------------------------------------------------------------------
    # Risk-premium adjustment
    # -------------------------------------------------------------------

    def vix1d_risk_premium_adjustment(self, vix1d: float) -> Dict[str, float]:
        """Apply the Albers (2025) risk-premium adjustment to VIX1D.

        Empirical finding: VIX1D systematically overstates realized 1-day
        vol by approximately 0.16 index points on average.  Subtracting
        this offset yields a better point estimate for the true expected
        daily move.

        Args:
            vix1d: Raw VIX1D level.

        Returns:
            Dict with ``raw_vix1d``, ``adjusted_vix1d``, and
            ``risk_premium_offset``.
        """
        adjusted = max(vix1d - self.RISK_PREMIUM_OFFSET, 0.0)
        return {
            "raw_vix1d": round(vix1d, 4),
            "adjusted_vix1d": round(adjusted, 4),
            "risk_premium_offset": self.RISK_PREMIUM_OFFSET,
        }


# ---------------------------------------------------------------------------
# Data Feed Manager
# ---------------------------------------------------------------------------

class DataFeedManager:
    """Central aggregator for all live market data feeds.

    Stores the most recent snapshot of every data category and maintains
    a rolling history of 1-minute SPX price bars and the economic
    calendar for the session.

    Typical usage::

        mgr = DataFeedManager()
        mgr.update_options_chain(chain)
        mgr.update_vix(vix_data)
        snapshot = mgr.get_current_snapshot()
        if mgr.is_data_fresh(max_age_seconds=5):
            # proceed with scan
            ...
    """

    def __init__(self) -> None:
        # Current feed state --------------------------------------------------
        self._options_chain: Optional[OptionsChain] = None
        self._market_internals: Optional[MarketInternalsData] = None
        self._futures: Optional[FuturesData] = None
        self._vix: Optional[VIXData] = None
        self._cross_asset: Optional[CrossAssetData] = None
        self._prior_session: Optional[PriorSessionData] = None

        # History stores -------------------------------------------------------
        self._price_bars: List[SPXPriceBar] = []
        self._economic_calendar: List[EconomicEvent] = []

        # Timestamps of last updates ------------------------------------------
        self._last_update_times: Dict[str, Optional[datetime]] = {
            "options_chain": None,
            "market_internals": None,
            "futures": None,
            "vix": None,
            "cross_asset": None,
            "price_bar": None,
        }

    # ------------------------------------------------------------------
    # Update methods
    # ------------------------------------------------------------------

    def update_options_chain(self, chain: OptionsChain) -> None:
        """Replace the current options chain snapshot.

        Args:
            chain: New 0DTE options chain snapshot.
        """
        self._options_chain = chain
        self._last_update_times["options_chain"] = chain.chain_timestamp

    def update_market_internals(self, data: MarketInternalsData) -> None:
        """Replace the current market-internals reading.

        Args:
            data: Fresh NYSE breadth data.
        """
        self._market_internals = data
        self._last_update_times["market_internals"] = data.timestamp

    def update_futures(self, data: FuturesData) -> None:
        """Replace the current ES futures data.

        Args:
            data: Fresh ES futures snapshot.
        """
        self._futures = data
        self._last_update_times["futures"] = data.timestamp

    def update_vix(self, data: VIXData) -> None:
        """Replace the current VIX family data.

        Args:
            data: Fresh VIX / VIX1D / VIX9D snapshot.
        """
        self._vix = data
        self._last_update_times["vix"] = data.vix1d_timestamp

    def update_cross_asset(self, data: CrossAssetData) -> None:
        """Replace the current cross-asset context data.

        Args:
            data: Fresh rates / dollar snapshot.
        """
        self._cross_asset = data
        self._last_update_times["cross_asset"] = data.timestamp

    def update_price_bar(self, bar: SPXPriceBar) -> None:
        """Append a new 1-minute SPX price bar to the history.

        Bars are stored in chronological order.  Duplicate timestamps
        are silently ignored.

        Args:
            bar: New 1-minute OHLCV bar.
        """
        # Guard against duplicate bars.
        if self._price_bars and self._price_bars[-1].timestamp >= bar.timestamp:
            return
        self._price_bars.append(bar)
        self._last_update_times["price_bar"] = bar.timestamp

    def set_prior_session(self, data: PriorSessionData) -> None:
        """Set the prior-session reference levels (typically once per day).

        Args:
            data: Prior day SPX / VIX1D reference data.
        """
        self._prior_session = data

    def set_economic_calendar(self, events: List[EconomicEvent]) -> None:
        """Load the day's economic event calendar.

        Args:
            events: List of scheduled economic events for the session.
        """
        self._economic_calendar = sorted(events, key=lambda e: e.time)

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def options_chain(self) -> Optional[OptionsChain]:
        """Current options chain snapshot, or None if not yet received."""
        return self._options_chain

    @property
    def market_internals(self) -> Optional[MarketInternalsData]:
        """Current market internals, or None."""
        return self._market_internals

    @property
    def futures(self) -> Optional[FuturesData]:
        """Current ES futures data, or None."""
        return self._futures

    @property
    def vix(self) -> Optional[VIXData]:
        """Current VIX family data, or None."""
        return self._vix

    @property
    def cross_asset(self) -> Optional[CrossAssetData]:
        """Current cross-asset data, or None."""
        return self._cross_asset

    @property
    def prior_session(self) -> Optional[PriorSessionData]:
        """Prior session reference levels, or None."""
        return self._prior_session

    @property
    def price_bars(self) -> List[SPXPriceBar]:
        """Chronologically ordered list of 1-minute SPX price bars."""
        return self._price_bars

    @property
    def economic_calendar(self) -> List[EconomicEvent]:
        """Today's economic event calendar, sorted by time."""
        return self._economic_calendar

    # ------------------------------------------------------------------
    # Snapshot & freshness
    # ------------------------------------------------------------------

    def get_current_snapshot(self) -> Dict:
        """Return a dictionary of all current data feed values.

        Returns:
            Dict keyed by feed name with current data objects (or None).
        """
        return {
            "options_chain": self._options_chain,
            "market_internals": self._market_internals,
            "futures": self._futures,
            "vix": self._vix,
            "cross_asset": self._cross_asset,
            "prior_session": self._prior_session,
            "price_bars": list(self._price_bars),
            "economic_calendar": list(self._economic_calendar),
            "last_update_times": dict(self._last_update_times),
        }

    def is_data_fresh(self, max_age_seconds: float) -> bool:
        """Check whether all critical feeds have been updated recently.

        Critical feeds are: options_chain, market_internals, futures, vix.
        Cross-asset and price-bar staleness is tolerated because they
        update less frequently.

        Args:
            max_age_seconds: Maximum acceptable age (in seconds) for each
                critical feed.

        Returns:
            True if every critical feed was updated within *max_age_seconds*
            of ``datetime.now()``.  Returns False if any critical feed has
            never been populated.
        """
        now = datetime.now()
        critical_feeds = ["options_chain", "market_internals", "futures", "vix"]
        for feed_name in critical_feeds:
            last = self._last_update_times.get(feed_name)
            if last is None:
                return False
            age = (now - last).total_seconds()
            if age > max_age_seconds:
                return False
        return True

    def get_upcoming_events(self, within_minutes: float = 15.0) -> List[EconomicEvent]:
        """Return economic events occurring within the next *within_minutes*.

        Useful for pre-event risk checks (e.g., suspend scanning around FOMC).

        Args:
            within_minutes: Look-ahead window in minutes.

        Returns:
            List of upcoming EconomicEvent objects, chronologically ordered.
        """
        now = datetime.now()
        upcoming: List[EconomicEvent] = []
        for event in self._economic_calendar:
            delta = (event.time - now).total_seconds()
            if 0 <= delta <= within_minutes * 60:
                upcoming.append(event)
        return upcoming

    def get_high_impact_events(self) -> List[EconomicEvent]:
        """Return all HIGH impact events on today's calendar.

        Returns:
            List of EconomicEvent with impact_level == HIGH.
        """
        return [
            e for e in self._economic_calendar
            if e.impact_level == ImpactLevel.HIGH
        ]

    def get_recent_bars(self, count: int) -> List[SPXPriceBar]:
        """Return the most recent *count* price bars.

        Args:
            count: Number of bars to retrieve (from the end of history).

        Returns:
            Up to *count* bars in chronological order.
        """
        return self._price_bars[-count:] if count > 0 else []

    def get_vwap(self) -> Optional[float]:
        """Compute the session VWAP from stored price bars.

        Uses the typical price (H+L+C)/3 weighted by volume for each bar.

        Returns:
            VWAP as a float, or None if no price bars are available.
        """
        if not self._price_bars:
            return None

        prices = np.array(
            [(b.high + b.low + b.close) / 3.0 for b in self._price_bars],
            dtype=np.float64,
        )
        volumes = np.array(
            [b.volume for b in self._price_bars],
            dtype=np.float64,
        )

        total_volume = volumes.sum()
        if total_volume == 0:
            return None

        vwap = float(np.dot(prices, volumes) / total_volume)
        return round(vwap, 2)
