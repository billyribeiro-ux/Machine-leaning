"""
SCANIFY Premium Selling Scanner — Core Scan #2: Credit Spreads / Iron Condors.

Implements the premium-selling strategy for 0DTE SPX options in range-bound
or squeeze market regimes.  The scanner identifies opportunities to sell
credit spreads (bull put, bear call) and iron condors when implied volatility
exceeds realised volatility and directional risk is low.

Entry conditions are strict — all eight must pass simultaneously:
    1. Session is RANGE or SQUEEZE.
    2. VIX1D between 10 and 22.
    3. SPX within 0.5 sigma of VWAP.
    4. Net GEX positive (dealers long gamma -> mean-reversion bias).
    5. Time between 10:00 and 14:00 ET.
    6. No economic event within 60 minutes.
    7. NYSE TICK between -500 and +500 (no extreme breadth skew).
    8. IV / RV ratio > 1.1 (implied vol is rich relative to realised).

Strike selection anchors short strikes beyond both the GEX support/resistance
level and the 1-sigma expected move boundary, with probability-of-OTM checks
to ensure at least 80 % estimated chance of expiring worthless.

Close targets escalate through the session:
    - Before 2:30 PM ET: close at 50 % of max profit.
    - After 2:30 PM ET:  close at 80 % of max profit.
"""

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Dict, List, Optional, Tuple
import math
import numpy as np

from .config import (
    PremiumSellConfig, ScanifyConfig, SignalDirection,
    ScanType, TimeZone, SessionType
)
from .data_feeds import (
    OptionsChain, OptionQuote, MarketInternalsData, VIXData,
    SPXPriceBar, OptionType
)
from .gex_engine import GEXResult
from .pre_market import SessionSetup, ExpectedMove


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

_SQRT_2 = math.sqrt(2.0)


def _norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function.

    Uses ``math.erfc`` for full double-precision accuracy, matching the
    implementation in :mod:`.gex_engine`.
    """
    return 0.5 * math.erfc(-x / _SQRT_2)


def _compute_vwap(price_bars: List[SPXPriceBar]) -> Optional[float]:
    """Compute session VWAP from a list of 1-minute price bars.

    Uses the typical price ``(high + low + close) / 3`` weighted by volume.

    Returns
    -------
    float or None
        VWAP value, or None if bars are empty or total volume is zero.
    """
    if not price_bars:
        return None

    prices = np.array(
        [(b.high + b.low + b.close) / 3.0 for b in price_bars],
        dtype=np.float64,
    )
    volumes = np.array(
        [b.volume for b in price_bars],
        dtype=np.float64,
    )

    total_volume = volumes.sum()
    if total_volume == 0:
        return None

    vwap = float(np.dot(prices, volumes) / total_volume)
    return round(vwap, 2)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SpreadLeg:
    """A single leg of a credit spread.

    Attributes
    ----------
    strike : float
        Strike price.
    option_type : OptionType
        CALL or PUT.
    side : str
        ``"short"`` or ``"long"``.
    bid : float
        Current best bid.
    ask : float
        Current best ask.
    mid : float
        Mid-market price ``(bid + ask) / 2``.
    delta : float
        Option delta.
    gamma : float
        Option gamma.
    volume : int
        Cumulative session volume.
    open_interest : int
        Open interest at start of day.
    """
    strike: float
    option_type: OptionType
    side: str  # "short" or "long"
    bid: float
    ask: float
    mid: float
    delta: float
    gamma: float
    volume: int
    open_interest: int


@dataclass
class CreditSpread:
    """A vertical credit spread (bull put or bear call).

    Attributes
    ----------
    spread_type : str
        ``"bull_put"`` or ``"bear_call"``.
    short_leg : SpreadLeg
        The sold (short) option leg.
    long_leg : SpreadLeg
        The bought (long) protective option leg.
    width : float
        Distance between strikes (points).
    credit : float
        Net credit received per contract.
    max_loss : float
        Maximum loss per contract (width - credit).
    max_profit : float
        Maximum profit per contract (credit).
    credit_pct_of_width : float
        Credit as a fraction of the spread width.
    prob_otm : float
        Estimated probability of the short strike expiring OTM.
    risk_reward : float
        Risk/reward ratio (max_profit / max_loss).
    breakeven : float
        Breakeven price at expiration.
    """
    spread_type: str  # "bull_put" or "bear_call"
    short_leg: SpreadLeg
    long_leg: SpreadLeg
    width: float
    credit: float
    max_loss: float
    max_profit: float
    credit_pct_of_width: float
    prob_otm: float
    risk_reward: float
    breakeven: float


@dataclass
class IronCondor:
    """An iron condor combining a bull put spread and a bear call spread.

    Attributes
    ----------
    put_spread : CreditSpread
        The bull put (lower) side of the condor.
    call_spread : CreditSpread
        The bear call (upper) side of the condor.
    total_credit : float
        Combined credit from both spreads.
    total_max_loss : float
        Maximum loss (width - total_credit; only one side can lose).
    breakeven_lower : float
        Lower breakeven price.
    breakeven_upper : float
        Upper breakeven price.
    breakeven_range : float
        Width of the breakeven range (upper - lower).
    expected_move_contained : bool
        True if the breakeven range contains the full 1-sigma expected move.
    """
    put_spread: CreditSpread
    call_spread: CreditSpread
    total_credit: float
    total_max_loss: float
    breakeven_lower: float
    breakeven_upper: float
    breakeven_range: float
    expected_move_contained: bool


@dataclass
class PremiumSellSignal:
    """Output signal from the premium-selling scanner.

    Attributes
    ----------
    timestamp : datetime
        Time the signal was generated.
    scan_type : ScanType
        Always ``ScanType.PREMIUM_SELL``.
    trade_type : str
        ``"bull_put"``, ``"bear_call"``, or ``"iron_condor"``.
    spread : CreditSpread or None
        The single credit spread (if trade_type is not iron_condor).
    condor : IronCondor or None
        The iron condor (if trade_type is iron_condor).
    close_target_pct : float
        Profit-taking threshold as a fraction of max profit.
    max_hold_time : str
        Latest time to hold the position (e.g. ``"15:30"``).
    session_type : SessionType
        Current session classification.
    vix1d : float
        VIX1D level at signal time.
    iv_rv_ratio : float
        Implied / realised volatility ratio.
    reasons : list of str
        Reasons supporting the trade.
    warnings : list of str
        Risk warnings and caveats.
    confidence : float
        Overall signal confidence (0.0 to 1.0).
    """
    timestamp: datetime
    scan_type: ScanType = ScanType.PREMIUM_SELL
    trade_type: str = "iron_condor"
    spread: Optional[CreditSpread] = None
    condor: Optional[IronCondor] = None
    close_target_pct: float = 0.50
    max_hold_time: str = "15:30"
    session_type: SessionType = SessionType.RANGE
    vix1d: float = 0.0
    iv_rv_ratio: float = 0.0
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    confidence: float = 0.0


# ---------------------------------------------------------------------------
# Premium Selling Scanner
# ---------------------------------------------------------------------------

class PremiumSellingScanner:
    """Core Scan #2 — Premium Selling Scanner for 0DTE SPX credit spreads
    and iron condors.

    The scanner runs every 5 minutes during the 10:00 - 14:00 ET window
    and looks for opportunities to sell premium when the market is
    range-bound and implied volatility is rich.

    Parameters
    ----------
    config : ScanifyConfig
        Master SCANIFY configuration instance.
    """

    def __init__(self, config: ScanifyConfig) -> None:
        self.config = config

    # ------------------------------------------------------------------
    # Entry conditions
    # ------------------------------------------------------------------

    def check_entry_conditions(
        self,
        session_setup: SessionSetup,
        vix_data: VIXData,
        spx_price: float,
        vwap: float,
        gex: GEXResult,
        internals: MarketInternalsData,
        iv_rv_ratio: float,
    ) -> Tuple[bool, List[str]]:
        """Validate all eight entry conditions for premium selling.

        Every condition must pass simultaneously for the scanner to
        proceed to spread construction.  The returned list contains
        human-readable descriptions of each failed condition, enabling
        transparent logging and debugging.

        Parameters
        ----------
        session_setup : SessionSetup
            Pre-market session classification and expected-move data.
        vix_data : VIXData
            Current VIX family snapshot.
        spx_price : float
            Current SPX cash index price.
        vwap : float
            Session VWAP.
        gex : GEXResult
            Current GEX snapshot.
        internals : MarketInternalsData
            NYSE breadth internals.
        iv_rv_ratio : float
            Current implied / realised volatility ratio.

        Returns
        -------
        tuple of (bool, list of str)
            ``(True, [])`` if all conditions pass, otherwise
            ``(False, [list of failure descriptions])``.
        """
        ps = self.config.premium_sell
        failed: List[str] = []

        # 1. Session is RANGE or SQUEEZE
        if session_setup.session_type not in (SessionType.RANGE, SessionType.SQUEEZE):
            failed.append(
                f"Session type {session_setup.session_type.value} "
                f"is not RANGE or SQUEEZE"
            )

        # 2. VIX1D between configured min and max
        if not (ps.vix1d_min <= vix_data.vix1d <= ps.vix1d_max):
            failed.append(
                f"VIX1D {vix_data.vix1d:.1f} outside range "
                f"[{ps.vix1d_min}, {ps.vix1d_max}]"
            )

        # 3. SPX within 0.5 sigma of VWAP
        em_1sigma = session_setup.expected_move.em_1sigma
        max_distance = ps.max_vwap_distance_sigma * em_1sigma
        vwap_distance = abs(spx_price - vwap)
        if max_distance > 0 and vwap_distance > max_distance:
            failed.append(
                f"SPX distance from VWAP ({vwap_distance:.1f} pts) "
                f"exceeds {ps.max_vwap_distance_sigma} sigma "
                f"({max_distance:.1f} pts)"
            )

        # 4. Net GEX positive (dealers long gamma)
        if gex.total_net_gex <= 0:
            failed.append(
                f"Net GEX is not positive ({gex.total_net_gex:,.0f})"
            )

        # 5. Time between 10:00 and 14:00 ET
        now = datetime.now()
        scan_start = self._parse_time(ps.scan_start)
        scan_end = self._parse_time(ps.scan_end)
        current_time = now.time()
        if not (scan_start <= current_time <= scan_end):
            failed.append(
                f"Current time {current_time.strftime('%H:%M')} outside "
                f"scan window [{ps.scan_start}, {ps.scan_end}]"
            )

        # 6. No economic event within 60 minutes
        for event in session_setup.event_risk.events_today:
            try:
                delta_seconds = abs((event.time - now).total_seconds())
            except (TypeError, AttributeError):
                continue
            if delta_seconds <= 3600:
                failed.append(
                    f"Economic event '{event.name}' within 60 minutes"
                )
                break

        # 7. TICK between -500 and +500
        if not (ps.tick_range_min <= internals.tick <= ps.tick_range_max):
            failed.append(
                f"TICK {internals.tick:.0f} outside range "
                f"[{ps.tick_range_min:.0f}, {ps.tick_range_max:.0f}]"
            )

        # 8. IV/RV ratio > 1.1
        if iv_rv_ratio < ps.min_iv_rv_ratio:
            failed.append(
                f"IV/RV ratio {iv_rv_ratio:.2f} below minimum "
                f"{ps.min_iv_rv_ratio}"
            )

        return (len(failed) == 0, failed)

    # ------------------------------------------------------------------
    # Probability estimation
    # ------------------------------------------------------------------

    def estimate_prob_otm(
        self,
        strike: float,
        spot: float,
        em_1sigma: float,
        option_type: OptionType,
    ) -> float:
        """Estimate the probability of a strike expiring out-of-the-money.

        Uses a normal distribution centred at *spot* with standard
        deviation equal to the 1-sigma expected move.

        Formulas
        --------
        - Puts:  P(SPX > strike) = N((spot - strike) / em_1sigma)
        - Calls: P(SPX < strike) = N((strike - spot) / em_1sigma)

        Parameters
        ----------
        strike : float
            The option strike price.
        spot : float
            Current SPX cash index price.
        em_1sigma : float
            One-standard-deviation expected move (points).
        option_type : OptionType
            CALL or PUT.

        Returns
        -------
        float
            Estimated probability of expiring OTM, in [0, 1].
        """
        if em_1sigma <= 0:
            # If expected move is zero or negative, cannot estimate.
            return 0.5

        if option_type == OptionType.PUT:
            # Put is OTM when SPX > strike.
            z = (spot - strike) / em_1sigma
        else:
            # Call is OTM when SPX < strike.
            z = (strike - spot) / em_1sigma

        return _norm_cdf(z)

    # ------------------------------------------------------------------
    # Spread builders
    # ------------------------------------------------------------------

    def build_put_credit_spread(
        self,
        chain: OptionsChain,
        spot: float,
        gex: GEXResult,
        em: ExpectedMove,
        config: PremiumSellConfig,
    ) -> Optional[CreditSpread]:
        """Build a bull put credit spread from the options chain.

        Strike selection logic:
            - Short strike is placed at whichever level is further below
              spot: the -GEX strike (major put support) or the 1-sigma
              lower expected move boundary.
            - Long strike = short strike - spread width (default 5 pts).
            - Both strikes are snapped to the nearest available quote in
              the chain.

        Validation checks:
            - Minimum credit of $0.50.
            - Target credit >= 30 % of spread width.
            - Estimated probability of expiring OTM >= 80 %.

        Parameters
        ----------
        chain : OptionsChain
            0DTE SPX options chain snapshot.
        spot : float
            Current SPX price.
        gex : GEXResult
            Current GEX snapshot.
        em : ExpectedMove
            Expected-move envelope.
        config : PremiumSellConfig
            Premium-selling configuration.

        Returns
        -------
        CreditSpread or None
            A valid bull put credit spread, or None if conditions are
            not met.
        """
        # Determine the target short strike: whichever is further below spot.
        candidate_gex = gex.minus_gex_strike if gex.minus_gex_strike > 0 else 0.0
        candidate_em = em.lower_1sigma

        # For puts below spot, "further from spot" means the lower value.
        if candidate_gex > 0 and candidate_em > 0:
            target_short_strike = min(candidate_gex, candidate_em)
        elif candidate_gex > 0:
            target_short_strike = candidate_gex
        elif candidate_em > 0:
            target_short_strike = candidate_em
        else:
            # Fallback: 1 sigma below spot
            target_short_strike = spot - em.em_1sigma

        # Ensure short strike is below spot
        if target_short_strike >= spot:
            target_short_strike = spot - em.em_1sigma

        target_long_strike = target_short_strike - config.spread_width

        # Find nearest available chain quotes
        short_quote = self._find_nearest_quote(
            chain, target_short_strike, OptionType.PUT
        )
        if short_quote is None:
            return None

        long_quote = self._find_nearest_quote(
            chain, target_long_strike, OptionType.PUT
        )
        if long_quote is None:
            return None

        # Ensure the long strike is below the short strike
        if long_quote.strike >= short_quote.strike:
            return None

        # Compute spread metrics
        # Credit = short bid - long ask (conservative fill estimate)
        credit = short_quote.bid - long_quote.ask
        if credit <= 0:
            # Try mid-price estimate as fallback
            credit = short_quote.mid - long_quote.mid
            if credit <= 0:
                return None

        width = short_quote.strike - long_quote.strike
        if width <= 0:
            return None

        max_loss = width - credit
        max_profit = credit
        credit_pct = credit / width if width > 0 else 0.0

        # Probability of OTM for the short strike
        prob_otm = self.estimate_prob_otm(
            short_quote.strike, spot, em.em_1sigma, OptionType.PUT
        )

        # Risk/reward
        risk_reward = max_profit / max_loss if max_loss > 0 else 0.0

        # Breakeven for bull put spread: short strike - credit
        breakeven = short_quote.strike - credit

        # --- Validation checks ---
        if credit < config.min_credit:
            return None
        if credit_pct < config.target_credit_pct:
            return None
        if prob_otm < config.min_prob_otm:
            return None

        # Build legs
        short_leg = SpreadLeg(
            strike=short_quote.strike,
            option_type=OptionType.PUT,
            side="short",
            bid=short_quote.bid,
            ask=short_quote.ask,
            mid=short_quote.mid,
            delta=short_quote.delta,
            gamma=short_quote.gamma,
            volume=short_quote.volume,
            open_interest=short_quote.open_interest,
        )

        long_leg = SpreadLeg(
            strike=long_quote.strike,
            option_type=OptionType.PUT,
            side="long",
            bid=long_quote.bid,
            ask=long_quote.ask,
            mid=long_quote.mid,
            delta=long_quote.delta,
            gamma=long_quote.gamma,
            volume=long_quote.volume,
            open_interest=long_quote.open_interest,
        )

        return CreditSpread(
            spread_type="bull_put",
            short_leg=short_leg,
            long_leg=long_leg,
            width=round(width, 2),
            credit=round(credit, 2),
            max_loss=round(max_loss, 2),
            max_profit=round(max_profit, 2),
            credit_pct_of_width=round(credit_pct, 4),
            prob_otm=round(prob_otm, 4),
            risk_reward=round(risk_reward, 4),
            breakeven=round(breakeven, 2),
        )

    def build_call_credit_spread(
        self,
        chain: OptionsChain,
        spot: float,
        gex: GEXResult,
        em: ExpectedMove,
        config: PremiumSellConfig,
    ) -> Optional[CreditSpread]:
        """Build a bear call credit spread from the options chain.

        Same logic as :meth:`build_put_credit_spread` but for the upside:
            - Short strike is placed at whichever level is further above
              spot: the +GEX strike (major call resistance) or the 1-sigma
              upper expected move boundary.
            - Long strike = short strike + spread width.

        Parameters
        ----------
        chain : OptionsChain
            0DTE SPX options chain snapshot.
        spot : float
            Current SPX price.
        gex : GEXResult
            Current GEX snapshot.
        em : ExpectedMove
            Expected-move envelope.
        config : PremiumSellConfig
            Premium-selling configuration.

        Returns
        -------
        CreditSpread or None
            A valid bear call credit spread, or None if conditions are
            not met.
        """
        # Determine the target short strike: whichever is further above spot.
        candidate_gex = gex.plus_gex_strike if gex.plus_gex_strike > 0 else 0.0
        candidate_em = em.upper_1sigma

        # For calls above spot, "further from spot" means the higher value.
        if candidate_gex > 0 and candidate_em > 0:
            target_short_strike = max(candidate_gex, candidate_em)
        elif candidate_gex > 0:
            target_short_strike = candidate_gex
        elif candidate_em > 0:
            target_short_strike = candidate_em
        else:
            # Fallback: 1 sigma above spot
            target_short_strike = spot + em.em_1sigma

        # Ensure short strike is above spot
        if target_short_strike <= spot:
            target_short_strike = spot + em.em_1sigma

        target_long_strike = target_short_strike + config.spread_width

        # Find nearest available chain quotes
        short_quote = self._find_nearest_quote(
            chain, target_short_strike, OptionType.CALL
        )
        if short_quote is None:
            return None

        long_quote = self._find_nearest_quote(
            chain, target_long_strike, OptionType.CALL
        )
        if long_quote is None:
            return None

        # Ensure the long strike is above the short strike
        if long_quote.strike <= short_quote.strike:
            return None

        # Compute spread metrics
        # Credit = short bid - long ask (conservative fill estimate)
        credit = short_quote.bid - long_quote.ask
        if credit <= 0:
            # Try mid-price estimate as fallback
            credit = short_quote.mid - long_quote.mid
            if credit <= 0:
                return None

        width = long_quote.strike - short_quote.strike
        if width <= 0:
            return None

        max_loss = width - credit
        max_profit = credit
        credit_pct = credit / width if width > 0 else 0.0

        # Probability of OTM for the short strike
        prob_otm = self.estimate_prob_otm(
            short_quote.strike, spot, em.em_1sigma, OptionType.CALL
        )

        # Risk/reward
        risk_reward = max_profit / max_loss if max_loss > 0 else 0.0

        # Breakeven for bear call spread: short strike + credit
        breakeven = short_quote.strike + credit

        # --- Validation checks ---
        if credit < config.min_credit:
            return None
        if credit_pct < config.target_credit_pct:
            return None
        if prob_otm < config.min_prob_otm:
            return None

        # Build legs
        short_leg = SpreadLeg(
            strike=short_quote.strike,
            option_type=OptionType.CALL,
            side="short",
            bid=short_quote.bid,
            ask=short_quote.ask,
            mid=short_quote.mid,
            delta=short_quote.delta,
            gamma=short_quote.gamma,
            volume=short_quote.volume,
            open_interest=short_quote.open_interest,
        )

        long_leg = SpreadLeg(
            strike=long_quote.strike,
            option_type=OptionType.CALL,
            side="long",
            bid=long_quote.bid,
            ask=long_quote.ask,
            mid=long_quote.mid,
            delta=long_quote.delta,
            gamma=long_quote.gamma,
            volume=long_quote.volume,
            open_interest=long_quote.open_interest,
        )

        return CreditSpread(
            spread_type="bear_call",
            short_leg=short_leg,
            long_leg=long_leg,
            width=round(width, 2),
            credit=round(credit, 2),
            max_loss=round(max_loss, 2),
            max_profit=round(max_profit, 2),
            credit_pct_of_width=round(credit_pct, 4),
            prob_otm=round(prob_otm, 4),
            risk_reward=round(risk_reward, 4),
            breakeven=round(breakeven, 2),
        )

    def build_iron_condor(
        self,
        put_spread: CreditSpread,
        call_spread: CreditSpread,
        em: ExpectedMove,
    ) -> IronCondor:
        """Combine a bull put spread and a bear call spread into an iron condor.

        The iron condor collects premium from both sides of the market.
        Since only one side can lose at expiration, the maximum loss is
        the width of one spread minus the total credit received.

        Parameters
        ----------
        put_spread : CreditSpread
            The bull put (lower) side.
        call_spread : CreditSpread
            The bear call (upper) side.
        em : ExpectedMove
            Expected-move envelope for containment check.

        Returns
        -------
        IronCondor
            Fully populated iron condor structure.
        """
        total_credit = put_spread.credit + call_spread.credit

        # Max loss uses the wider of the two spreads, minus total credit.
        max_width = max(put_spread.width, call_spread.width)
        total_max_loss = max_width - total_credit
        if total_max_loss < 0:
            total_max_loss = 0.0

        # Breakevens: total credit buffers both sides.
        breakeven_lower = put_spread.short_leg.strike - total_credit
        breakeven_upper = call_spread.short_leg.strike + total_credit
        breakeven_range = breakeven_upper - breakeven_lower

        # Check if 1-sigma expected move is contained within the breakevens.
        expected_move_contained = (
            breakeven_lower <= em.lower_1sigma
            and breakeven_upper >= em.upper_1sigma
        )

        return IronCondor(
            put_spread=put_spread,
            call_spread=call_spread,
            total_credit=round(total_credit, 2),
            total_max_loss=round(total_max_loss, 2),
            breakeven_lower=round(breakeven_lower, 2),
            breakeven_upper=round(breakeven_upper, 2),
            breakeven_range=round(breakeven_range, 2),
            expected_move_contained=expected_move_contained,
        )

    # ------------------------------------------------------------------
    # Main scan entry point
    # ------------------------------------------------------------------

    def scan(
        self,
        chain: OptionsChain,
        internals: MarketInternalsData,
        vix_data: VIXData,
        gex: GEXResult,
        session_setup: SessionSetup,
        price_bars: List[SPXPriceBar],
        iv_rv_ratio: float,
    ) -> Optional[PremiumSellSignal]:
        """Run the premium-selling scan (called every 5 minutes).

        Orchestrates the full scan pipeline:
            1. Compute VWAP from intraday price bars.
            2. Check all eight entry conditions.
            3. Attempt to build a bull put credit spread.
            4. Attempt to build a bear call credit spread.
            5. If both are valid, combine into an iron condor (preferred).
            6. Otherwise, return whichever single spread is valid.
            7. If neither is valid, return None.
            8. Set close targets based on time of day.
            9. Assemble reasons and warnings.

        Parameters
        ----------
        chain : OptionsChain
            0DTE SPX options chain snapshot.
        internals : MarketInternalsData
            NYSE breadth internals.
        vix_data : VIXData
            Current VIX family snapshot.
        gex : GEXResult
            Current GEX snapshot.
        session_setup : SessionSetup
            Pre-market session setup.
        price_bars : list of SPXPriceBar
            Session 1-minute price bars for VWAP computation.
        iv_rv_ratio : float
            Current implied / realised volatility ratio.

        Returns
        -------
        PremiumSellSignal or None
            A premium-selling signal if a valid trade is found,
            otherwise None.
        """
        ps_config = self.config.premium_sell
        now = datetime.now()

        # --- 1. Current price and VWAP -----------------------------------
        spx_price = chain.underlying_price
        if spx_price <= 0 and price_bars:
            spx_price = price_bars[-1].close

        if spx_price <= 0:
            return None

        vwap = _compute_vwap(price_bars)
        if vwap is None:
            # Fallback: use current price as VWAP (no bars yet)
            vwap = spx_price

        # --- 2. Check entry conditions -----------------------------------
        conditions_passed, failed_reasons = self.check_entry_conditions(
            session_setup=session_setup,
            vix_data=vix_data,
            spx_price=spx_price,
            vwap=vwap,
            gex=gex,
            internals=internals,
            iv_rv_ratio=iv_rv_ratio,
        )

        if not conditions_passed:
            return None

        # --- 3. Build put credit spread ----------------------------------
        em = session_setup.expected_move
        put_spread = self.build_put_credit_spread(
            chain, spx_price, gex, em, ps_config
        )

        # --- 4. Build call credit spread ---------------------------------
        call_spread = self.build_call_credit_spread(
            chain, spx_price, gex, em, ps_config
        )

        # --- 5-7. Determine trade type -----------------------------------
        trade_type: str
        spread_result: Optional[CreditSpread] = None
        condor_result: Optional[IronCondor] = None

        if put_spread is not None and call_spread is not None:
            # Both valid: build iron condor (preferred)
            condor_result = self.build_iron_condor(put_spread, call_spread, em)
            trade_type = "iron_condor"
        elif put_spread is not None:
            spread_result = put_spread
            trade_type = "bull_put"
        elif call_spread is not None:
            spread_result = call_spread
            trade_type = "bear_call"
        else:
            # Neither spread is valid
            return None

        # --- 8. Set close targets based on time of day -------------------
        late_cutoff = time(14, 30)
        current_time = now.time()

        if current_time >= late_cutoff:
            close_target_pct = ps_config.close_late_profit_pct
        else:
            close_target_pct = ps_config.close_at_profit_pct

        max_hold_time = ps_config.max_hold_time

        # --- 9. Build reasons and warnings -------------------------------
        reasons: List[str] = []
        warnings: List[str] = []

        reasons.append(
            f"Session type: {session_setup.session_type.value} "
            f"(premium selling favoured)"
        )
        reasons.append(
            f"VIX1D at {vix_data.vix1d:.1f} — implied vol is rich "
            f"(IV/RV = {iv_rv_ratio:.2f})"
        )
        reasons.append(
            f"Net GEX positive ({gex.total_net_gex:,.0f}) — "
            f"dealers long gamma, mean-reversion bias"
        )
        reasons.append(
            f"SPX at {spx_price:.1f}, VWAP at {vwap:.1f} — "
            f"within {abs(spx_price - vwap):.1f} pts"
        )
        reasons.append(
            f"TICK at {internals.tick:.0f} — neutral breadth"
        )

        if trade_type == "iron_condor" and condor_result is not None:
            reasons.append(
                f"Iron condor: total credit ${condor_result.total_credit:.2f}, "
                f"breakeven range {condor_result.breakeven_lower:.0f} - "
                f"{condor_result.breakeven_upper:.0f}"
            )
            if condor_result.expected_move_contained:
                reasons.append(
                    "Breakeven range contains 1-sigma expected move"
                )
            else:
                warnings.append(
                    "Breakeven range does NOT fully contain 1-sigma "
                    "expected move — elevated risk"
                )
        elif spread_result is not None:
            reasons.append(
                f"{spread_result.spread_type} spread: "
                f"credit ${spread_result.credit:.2f} "
                f"({spread_result.credit_pct_of_width:.0%} of width), "
                f"prob OTM {spread_result.prob_otm:.0%}"
            )

        # Add time-based warnings
        if current_time >= late_cutoff:
            warnings.append(
                "After 2:30 PM — using aggressive close target "
                f"({close_target_pct:.0%} of max profit)"
            )

        # GEX structure warnings
        if gex.total_net_gex < 50000:
            warnings.append(
                "Net GEX is positive but low — monitor for gamma flip"
            )

        # VIX term structure warning
        if vix_data.vix1d > 18:
            warnings.append(
                f"VIX1D at {vix_data.vix1d:.1f} — approaching upper "
                f"comfort zone; widen strikes if possible"
            )

        # Event proximity warning
        for event in session_setup.event_risk.events_today:
            try:
                delta_minutes = (event.time - now).total_seconds() / 60.0
            except (TypeError, AttributeError):
                continue
            if 60 < delta_minutes <= 120:
                warnings.append(
                    f"Economic event '{event.name}' in "
                    f"{delta_minutes:.0f} minutes — monitor closely"
                )
                break

        # --- Compute confidence ------------------------------------------
        confidence = self._compute_confidence(
            trade_type=trade_type,
            spread=spread_result,
            condor=condor_result,
            iv_rv_ratio=iv_rv_ratio,
            vix1d=vix_data.vix1d,
            gex=gex,
            num_warnings=len(warnings),
        )

        return PremiumSellSignal(
            timestamp=now,
            scan_type=ScanType.PREMIUM_SELL,
            trade_type=trade_type,
            spread=spread_result,
            condor=condor_result,
            close_target_pct=round(close_target_pct, 2),
            max_hold_time=max_hold_time,
            session_type=session_setup.session_type,
            vix1d=round(vix_data.vix1d, 2),
            iv_rv_ratio=round(iv_rv_ratio, 4),
            reasons=reasons,
            warnings=warnings,
            confidence=round(confidence, 4),
        )

    # ==================================================================
    # Private helpers
    # ==================================================================

    @staticmethod
    def _parse_time(time_str: str) -> time:
        """Parse an ``"HH:MM"`` string into a :class:`datetime.time`.

        Parameters
        ----------
        time_str : str
            Time string in ``"HH:MM"`` format.

        Returns
        -------
        datetime.time
        """
        parts = time_str.split(":")
        return time(int(parts[0]), int(parts[1]))

    @staticmethod
    def _find_nearest_quote(
        chain: OptionsChain,
        target_strike: float,
        option_type: OptionType,
    ) -> Optional[OptionQuote]:
        """Find the option quote with the nearest strike to *target_strike*.

        Searches only quotes matching the requested *option_type*.
        Returns None if no matching quotes exist in the chain.

        Parameters
        ----------
        chain : OptionsChain
            The options chain to search.
        target_strike : float
            Desired strike price.
        option_type : OptionType
            CALL or PUT.

        Returns
        -------
        OptionQuote or None
            The nearest matching quote, or None if none found.
        """
        best_quote: Optional[OptionQuote] = None
        best_distance = float("inf")

        for quote in chain.quotes:
            if quote.option_type != option_type:
                continue

            distance = abs(quote.strike - target_strike)
            if distance < best_distance:
                best_distance = distance
                best_quote = quote

        # Sanity: reject quotes that are unreasonably far from target.
        # Allow up to 2x the standard strike interval (5 pts -> 10 pts).
        if best_quote is not None and best_distance > 10.0:
            return None

        return best_quote

    @staticmethod
    def _compute_confidence(
        trade_type: str,
        spread: Optional[CreditSpread],
        condor: Optional[IronCondor],
        iv_rv_ratio: float,
        vix1d: float,
        gex: GEXResult,
        num_warnings: int,
    ) -> float:
        """Compute an overall confidence score for the signal.

        The score starts at a base of 0.50 and is adjusted by:
            - Iron condor bonus (+0.10) for dual-sided protection.
            - High probability of OTM bonus (up to +0.10).
            - Strong IV/RV ratio bonus (up to +0.10).
            - Comfortable VIX1D range bonus (+0.05).
            - Warning penalty (-0.05 per warning).

        Clamped to the [0.0, 1.0] range.

        Parameters
        ----------
        trade_type : str
        spread : CreditSpread or None
        condor : IronCondor or None
        iv_rv_ratio : float
        vix1d : float
        gex : GEXResult
        num_warnings : int

        Returns
        -------
        float
            Confidence score in [0, 1].
        """
        confidence = 0.50

        # Iron condor bonus (dual-sided protection)
        if trade_type == "iron_condor":
            confidence += 0.10

        # Probability of OTM bonus
        if condor is not None:
            avg_prob = (
                condor.put_spread.prob_otm + condor.call_spread.prob_otm
            ) / 2.0
            confidence += min(0.10, (avg_prob - 0.80) * 0.50)
            # Expected move containment bonus
            if condor.expected_move_contained:
                confidence += 0.05
        elif spread is not None:
            confidence += min(0.10, (spread.prob_otm - 0.80) * 0.50)

        # IV/RV richness bonus: higher ratio = more edge for sellers
        if iv_rv_ratio > 1.2:
            confidence += min(0.10, (iv_rv_ratio - 1.1) * 0.20)

        # Comfortable VIX1D range (sweet spot: 12-18)
        if 12.0 <= vix1d <= 18.0:
            confidence += 0.05

        # Strong positive GEX (mean-reversion support)
        if gex.total_net_gex > 100000:
            confidence += 0.05

        # Warning penalty
        confidence -= num_warnings * 0.05

        return max(0.0, min(1.0, confidence))
