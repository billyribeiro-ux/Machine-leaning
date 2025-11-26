"""
Revolution Alpha Engine - Options Scanner

Institutional-grade options flow scanner for detecting unusual activity,
smart money positioning, and high-probability setups.
"""

from datetime import datetime, timedelta
from typing import Optional, Literal
from dataclasses import dataclass, field
import logging
import math

from .base import (
    BaseScanner,
    AsyncStreamingScanner,
    ScanContext,
    MarketData,
)
from .models import (
    OptionsScanResult,
    ScanMode,
    SignalDirection,
    ScannerConfig,
    OptionsFilterConfig,
    TimeFrame,
)

logger = logging.getLogger(__name__)


@dataclass
class OptionContract:
    """Represents a single option contract."""
    symbol: str
    underlying: str
    strike: float
    expiration: datetime
    option_type: Literal["CALL", "PUT"]
    bid: float
    ask: float
    last: float
    volume: int
    open_interest: int
    implied_volatility: float

    # Greeks
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    rho: Optional[float] = None

    # Flow data
    trade_count: int = 0
    avg_trade_size: float = 0
    buy_volume: int = 0
    sell_volume: int = 0

    @property
    def mid_price(self) -> float:
        """Calculate mid price."""
        return (self.bid + self.ask) / 2

    @property
    def spread(self) -> float:
        """Calculate bid-ask spread."""
        return self.ask - self.bid

    @property
    def spread_pct(self) -> float:
        """Calculate spread as percentage of mid."""
        mid = self.mid_price
        if mid > 0:
            return (self.spread / mid) * 100
        return 0

    @property
    def days_to_expiry(self) -> int:
        """Days until expiration."""
        return max(0, (self.expiration - datetime.utcnow()).days)

    @property
    def volume_oi_ratio(self) -> float:
        """Volume to open interest ratio."""
        if self.open_interest > 0:
            return self.volume / self.open_interest
        return 0

    @property
    def net_flow(self) -> int:
        """Net buying/selling flow."""
        return self.buy_volume - self.sell_volume

    @property
    def is_bullish_flow(self) -> bool:
        """Check if flow is bullish."""
        return self.net_flow > 0


@dataclass
class OptionsChain:
    """Container for options chain data."""
    underlying: str
    underlying_price: float
    contracts: list[OptionContract] = field(default_factory=list)
    iv_rank: Optional[float] = None
    iv_percentile: Optional[float] = None
    historical_iv: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def calls(self) -> list[OptionContract]:
        """Get all call options."""
        return [c for c in self.contracts if c.option_type == "CALL"]

    @property
    def puts(self) -> list[OptionContract]:
        """Get all put options."""
        return [c for c in self.contracts if c.option_type == "PUT"]

    @property
    def total_call_volume(self) -> int:
        """Total call volume."""
        return sum(c.volume for c in self.calls)

    @property
    def total_put_volume(self) -> int:
        """Total put volume."""
        return sum(c.volume for c in self.puts)

    @property
    def put_call_ratio(self) -> float:
        """Put/call volume ratio."""
        call_vol = self.total_call_volume
        if call_vol > 0:
            return self.total_put_volume / call_vol
        return 0

    def get_atm_strike(self) -> float:
        """Get at-the-money strike price."""
        if not self.contracts:
            return self.underlying_price

        strikes = sorted(set(c.strike for c in self.contracts))
        return min(strikes, key=lambda x: abs(x - self.underlying_price))

    def filter_by_dte(
        self,
        min_dte: int = 0,
        max_dte: int = 365
    ) -> list[OptionContract]:
        """Filter contracts by days to expiry."""
        return [
            c for c in self.contracts
            if min_dte <= c.days_to_expiry <= max_dte
        ]

    def filter_by_delta(
        self,
        min_delta: float = -1.0,
        max_delta: float = 1.0
    ) -> list[OptionContract]:
        """Filter contracts by delta."""
        return [
            c for c in self.contracts
            if c.delta is not None and min_delta <= c.delta <= max_delta
        ]


@dataclass
class UnusualActivity:
    """Represents unusual options activity."""
    contract: OptionContract
    activity_type: str  # "sweep", "block", "split", "unusual_volume"
    sentiment: Literal["bullish", "bearish", "neutral"]
    premium: float
    score: float  # 0-100 activity score
    is_opening: bool = True
    is_above_ask: bool = False
    is_below_bid: bool = False

    @property
    def description(self) -> str:
        """Generate activity description."""
        direction = "opening" if self.is_opening else "closing"
        execution = ""
        if self.is_above_ask:
            execution = "above ask"
        elif self.is_below_bid:
            execution = "below bid"

        return (
            f"{self.activity_type.upper()} - {self.contract.option_type} "
            f"${self.contract.strike} {self.contract.expiration.strftime('%m/%d')} "
            f"| {direction} | ${self.premium:,.0f} premium"
            f"{f' | {execution}' if execution else ''}"
        )


class OptionsFlowScanner(AsyncStreamingScanner[OptionsScanResult]):
    """
    Scanner for detecting unusual options flow and smart money activity.

    Analyzes volume, open interest, trade execution, and positioning
    to identify high-probability directional signals.
    """

    def __init__(
        self,
        config: Optional[ScannerConfig] = None,
        options_config: Optional[OptionsFilterConfig] = None,
        scan_mode: ScanMode = ScanMode.OPTIONS_DAY
    ):
        super().__init__(
            name="options_flow",
            scan_mode=scan_mode,
            config=config
        )
        self.options_config = options_config or OptionsFilterConfig()

        # Thresholds for unusual activity detection
        self.volume_oi_threshold = 0.5  # Volume > 50% of OI is unusual
        self.volume_surge_threshold = 3.0  # 3x average volume
        self.premium_threshold = 50000  # $50k minimum premium for alerts
        self.sweep_size_threshold = 10  # Minimum orders for sweep detection

    async def scan_symbol(
        self,
        symbol: str,
        context: ScanContext
    ) -> Optional[OptionsScanResult]:
        """Scan a single symbol for options signals."""
        try:
            # Get options data from context
            options_data = context.options_data.get(symbol)
            if not options_data:
                return None

            chain = self._build_options_chain(symbol, options_data, context)
            if not chain or not chain.contracts:
                return None

            # Detect unusual activity
            unusual_activities = self._detect_unusual_activity(chain)
            if not unusual_activities:
                return None

            # Score and filter activities
            best_activity = self._select_best_activity(unusual_activities)
            if not best_activity:
                return None

            # Generate signal
            return self._generate_signal(chain, best_activity, context)

        except Exception as e:
            self._logger.warning(f"Error scanning {symbol}: {e}")
            return None

    def _build_options_chain(
        self,
        symbol: str,
        options_data: dict,
        context: ScanContext
    ) -> Optional[OptionsChain]:
        """Build options chain from raw data."""
        market_data = context.market_data.get(symbol)
        underlying_price = market_data.close if market_data else options_data.get("underlying_price", 0)

        if underlying_price <= 0:
            return None

        contracts = []
        for contract_data in options_data.get("contracts", []):
            try:
                contract = OptionContract(
                    symbol=contract_data.get("symbol", ""),
                    underlying=symbol,
                    strike=contract_data.get("strike", 0),
                    expiration=datetime.fromisoformat(contract_data.get("expiration", "")),
                    option_type=contract_data.get("option_type", "CALL"),
                    bid=contract_data.get("bid", 0),
                    ask=contract_data.get("ask", 0),
                    last=contract_data.get("last", 0),
                    volume=contract_data.get("volume", 0),
                    open_interest=contract_data.get("open_interest", 0),
                    implied_volatility=contract_data.get("iv", 0),
                    delta=contract_data.get("delta"),
                    gamma=contract_data.get("gamma"),
                    theta=contract_data.get("theta"),
                    vega=contract_data.get("vega"),
                    buy_volume=contract_data.get("buy_volume", 0),
                    sell_volume=contract_data.get("sell_volume", 0),
                )
                contracts.append(contract)
            except (KeyError, ValueError) as e:
                self._logger.debug(f"Skipping invalid contract: {e}")
                continue

        return OptionsChain(
            underlying=symbol,
            underlying_price=underlying_price,
            contracts=contracts,
            iv_rank=options_data.get("iv_rank"),
            iv_percentile=options_data.get("iv_percentile"),
        )

    def _detect_unusual_activity(
        self,
        chain: OptionsChain
    ) -> list[UnusualActivity]:
        """Detect unusual options activity in the chain."""
        activities: list[UnusualActivity] = []
        cfg = self.options_config

        for contract in chain.contracts:
            # Apply basic filters
            if not self._passes_options_filters(contract, cfg):
                continue

            # Calculate premium
            premium = contract.volume * contract.mid_price * 100

            # Check for unusual volume
            if contract.volume_oi_ratio >= self.volume_oi_threshold:
                score = self._calculate_activity_score(contract, premium, "unusual_volume")
                sentiment = self._determine_sentiment(contract, chain)

                activities.append(UnusualActivity(
                    contract=contract,
                    activity_type="unusual_volume",
                    sentiment=sentiment,
                    premium=premium,
                    score=score,
                    is_opening=contract.volume > contract.open_interest * 0.3,
                ))

            # Check for sweep-like activity (high trade count)
            if contract.trade_count >= self.sweep_size_threshold:
                score = self._calculate_activity_score(contract, premium, "sweep")
                sentiment = self._determine_sentiment(contract, chain)

                activities.append(UnusualActivity(
                    contract=contract,
                    activity_type="sweep",
                    sentiment=sentiment,
                    premium=premium,
                    score=score,
                    is_opening=True,
                    is_above_ask=contract.last > contract.ask,
                ))

            # Check for block trades (large single trades)
            if contract.avg_trade_size > 100 and premium >= self.premium_threshold:
                score = self._calculate_activity_score(contract, premium, "block")
                sentiment = self._determine_sentiment(contract, chain)

                activities.append(UnusualActivity(
                    contract=contract,
                    activity_type="block",
                    sentiment=sentiment,
                    premium=premium,
                    score=score,
                ))

        return activities

    def _passes_options_filters(
        self,
        contract: OptionContract,
        cfg: OptionsFilterConfig
    ) -> bool:
        """Check if contract passes filter criteria."""
        # DTE filter
        if not (cfg.min_dte <= contract.days_to_expiry <= cfg.max_dte):
            return False

        # Volume filter
        if contract.volume < cfg.min_volume:
            return False

        # Open interest filter
        if contract.open_interest < cfg.min_open_interest:
            return False

        # Spread filter
        if contract.spread_pct > cfg.max_spread_pct:
            return False

        # Delta filter
        if contract.delta is not None:
            min_delta, max_delta = cfg.delta_range
            if not (min_delta <= contract.delta <= max_delta):
                return False

        return True

    def _calculate_activity_score(
        self,
        contract: OptionContract,
        premium: float,
        activity_type: str
    ) -> float:
        """Calculate activity score based on multiple factors."""
        score = 0.0

        # Volume/OI component (max 30 points)
        vol_oi_score = min(30, contract.volume_oi_ratio * 30)
        score += vol_oi_score

        # Premium component (max 25 points)
        premium_score = min(25, (premium / 100000) * 5)
        score += premium_score

        # Days to expiry component (shorter = more aggressive, max 20 points)
        if contract.days_to_expiry <= 7:
            score += 20
        elif contract.days_to_expiry <= 14:
            score += 15
        elif contract.days_to_expiry <= 30:
            score += 10
        else:
            score += 5

        # Activity type bonus
        type_bonus = {
            "sweep": 15,
            "block": 12,
            "unusual_volume": 8,
            "split": 10,
        }
        score += type_bonus.get(activity_type, 5)

        # Net flow bonus
        if contract.is_bullish_flow:
            score += 5

        return min(100, score)

    def _determine_sentiment(
        self,
        contract: OptionContract,
        chain: OptionsChain
    ) -> Literal["bullish", "bearish", "neutral"]:
        """Determine sentiment of the activity."""
        # Call buying or put selling = bullish
        if contract.option_type == "CALL" and contract.is_bullish_flow:
            return "bullish"

        if contract.option_type == "PUT" and not contract.is_bullish_flow:
            return "bullish"

        # Put buying or call selling = bearish
        if contract.option_type == "PUT" and contract.is_bullish_flow:
            return "bearish"

        if contract.option_type == "CALL" and not contract.is_bullish_flow:
            return "bearish"

        return "neutral"

    def _select_best_activity(
        self,
        activities: list[UnusualActivity]
    ) -> Optional[UnusualActivity]:
        """Select the best activity to generate a signal from."""
        if not activities:
            return None

        # Filter by minimum score
        scored = [a for a in activities if a.score >= 50]
        if not scored:
            return None

        # Sort by score and premium
        scored.sort(key=lambda x: (x.score, x.premium), reverse=True)
        return scored[0]

    def _generate_signal(
        self,
        chain: OptionsChain,
        activity: UnusualActivity,
        context: ScanContext
    ) -> OptionsScanResult:
        """Generate a scan result from unusual activity."""
        contract = activity.contract

        # Determine direction
        if activity.sentiment == "bullish":
            direction = SignalDirection.LONG
        elif activity.sentiment == "bearish":
            direction = SignalDirection.SHORT
        else:
            direction = SignalDirection.NEUTRAL

        # Calculate confidence
        confidence = activity.score

        # Boost confidence for specific conditions
        if activity.is_above_ask:
            confidence = min(100, confidence + 5)
        if activity.activity_type == "sweep":
            confidence = min(100, confidence + 5)
        if chain.iv_rank and chain.iv_rank < 30:
            confidence = min(100, confidence + 5)  # Low IV = cheap options

        # Entry at current underlying price
        entry_price = chain.underlying_price

        # Calculate stops and targets
        atr = context.market_data.get(chain.underlying)
        atr_value = atr.atr if atr and atr.atr else entry_price * 0.02

        stop_loss = self.calculate_stop_loss(
            entry_price, direction, atr_value, atr_multiplier=1.5
        )

        targets = self.calculate_targets(
            entry_price, stop_loss, direction,
            rr_ratios=[1.0, 1.5, 2.0]
        )

        # Build greeks dict
        greeks = {}
        if contract.delta is not None:
            greeks["delta"] = contract.delta
        if contract.gamma is not None:
            greeks["gamma"] = contract.gamma
        if contract.theta is not None:
            greeks["theta"] = contract.theta
        if contract.vega is not None:
            greeks["vega"] = contract.vega

        return OptionsScanResult(
            symbol=chain.underlying,
            scanner_type=self.name,
            direction=direction,
            confidence=confidence,
            entry_price=entry_price,
            stop_loss=stop_loss,
            targets=targets,
            risk_reward=self.calculate_risk_reward(entry_price, stop_loss, targets[1]) if targets else None,
            strike=contract.strike,
            expiration=contract.expiration,
            option_type=contract.option_type,
            greeks=greeks,
            iv_rank=chain.iv_rank,
            iv_percentile=chain.iv_percentile,
            bid=contract.bid,
            ask=contract.ask,
            volume=contract.volume,
            open_interest=contract.open_interest,
            underlying_price=chain.underlying_price,
            metadata={
                "activity_type": activity.activity_type,
                "activity_score": activity.score,
                "premium": activity.premium,
                "sentiment": activity.sentiment,
                "is_opening": activity.is_opening,
                "volume_oi_ratio": contract.volume_oi_ratio,
                "put_call_ratio": chain.put_call_ratio,
            }
        )

    def validate_signal(
        self,
        result: OptionsScanResult,
        context: ScanContext
    ) -> bool:
        """Validate options signal."""
        # Must have valid entry
        if result.entry_price is None or result.entry_price <= 0:
            return False

        # Confidence threshold
        if result.confidence < self.config.min_confidence:
            return False

        # Spread must be reasonable
        if result.spread_pct and result.spread_pct > self.options_config.max_spread_pct:
            return False

        # Days to expiry check
        if result.days_to_expiry < self.options_config.min_dte:
            return False

        return True


class OptionsSwingScanner(OptionsFlowScanner):
    """
    Scanner optimized for swing trading options setups.

    Focuses on longer-dated options with better risk/reward profiles.
    """

    def __init__(
        self,
        config: Optional[ScannerConfig] = None,
        options_config: Optional[OptionsFilterConfig] = None
    ):
        # Override defaults for swing trading
        swing_options_config = options_config or OptionsFilterConfig(
            min_dte=14,
            max_dte=60,
            min_volume=50,
            min_open_interest=200,
            max_spread_pct=15.0,
            delta_range=(-0.50, 0.50)
        )

        super().__init__(
            config=config,
            options_config=swing_options_config,
            scan_mode=ScanMode.OPTIONS_SWING
        )

        self.name = "options_swing"
        self.premium_threshold = 25000  # Lower threshold for swings


class GammaExposureScanner(BaseScanner[OptionsScanResult]):
    """
    Scanner for detecting gamma exposure imbalances and walls.

    Identifies price levels where market makers have significant gamma
    exposure that may act as support/resistance.
    """

    def __init__(
        self,
        config: Optional[ScannerConfig] = None
    ):
        super().__init__(
            name="gamma_exposure",
            scan_mode=ScanMode.OPTIONS_DAY,
            config=config
        )
        self.gamma_threshold = 1000000  # Minimum gamma exposure for wall

    async def scan(self, context: ScanContext) -> list[OptionsScanResult]:
        """Scan for gamma exposure imbalances."""
        results: list[OptionsScanResult] = []

        for symbol in context.universe:
            options_data = context.options_data.get(symbol)
            if not options_data:
                continue

            result = await self._analyze_gamma_exposure(symbol, options_data, context)
            if result:
                results.append(result)

        return results

    async def _analyze_gamma_exposure(
        self,
        symbol: str,
        options_data: dict,
        context: ScanContext
    ) -> Optional[OptionsScanResult]:
        """Analyze gamma exposure for a symbol."""
        market_data = context.market_data.get(symbol)
        if not market_data:
            return None

        underlying_price = market_data.close

        # Calculate gamma exposure at each strike
        gamma_levels: dict[float, float] = {}

        for contract_data in options_data.get("contracts", []):
            strike = contract_data.get("strike", 0)
            gamma = contract_data.get("gamma", 0)
            oi = contract_data.get("open_interest", 0)
            option_type = contract_data.get("option_type", "CALL")

            # Gamma exposure = gamma * OI * 100 * underlying_price^2
            gamma_exp = gamma * oi * 100 * (underlying_price ** 2)

            # Adjust sign based on option type (calls positive, puts negative for MMs)
            if option_type == "PUT":
                gamma_exp = -gamma_exp

            if strike not in gamma_levels:
                gamma_levels[strike] = 0
            gamma_levels[strike] += gamma_exp

        if not gamma_levels:
            return None

        # Find significant gamma walls
        walls = []
        for strike, gamma_exp in gamma_levels.items():
            if abs(gamma_exp) >= self.gamma_threshold:
                walls.append({
                    "strike": strike,
                    "gamma_exposure": gamma_exp,
                    "type": "resistance" if gamma_exp > 0 else "support",
                    "distance_pct": ((strike - underlying_price) / underlying_price) * 100
                })

        if not walls:
            return None

        # Sort walls by proximity to current price
        walls.sort(key=lambda x: abs(x["distance_pct"]))

        # Determine direction based on gamma positioning
        net_gamma = sum(gamma_levels.values())
        if net_gamma > 0:
            direction = SignalDirection.NEUTRAL  # Pinning expected
        elif net_gamma < 0:
            direction = SignalDirection.LONG if walls[0]["type"] == "support" else SignalDirection.SHORT
        else:
            direction = SignalDirection.NEUTRAL

        # Calculate confidence based on wall strength
        max_gamma = max(abs(w["gamma_exposure"]) for w in walls)
        confidence = min(85, 50 + (max_gamma / self.gamma_threshold) * 10)

        # Use nearest wall as target
        nearest_wall = walls[0]

        return OptionsScanResult(
            symbol=symbol,
            scanner_type=self.name,
            direction=direction,
            confidence=confidence,
            entry_price=underlying_price,
            targets=[w["strike"] for w in walls[:3]],
            strike=nearest_wall["strike"],
            expiration=datetime.utcnow() + timedelta(days=7),  # Placeholder
            option_type="CALL",  # N/A for gamma scanner
            underlying_price=underlying_price,
            metadata={
                "gamma_walls": walls[:5],
                "net_gamma_exposure": net_gamma,
                "wall_count": len(walls),
            }
        )

    def validate_signal(
        self,
        result: OptionsScanResult,
        context: ScanContext
    ) -> bool:
        """Validate gamma exposure signal."""
        if result.confidence < self.config.min_confidence:
            return False

        # Must have identified gamma walls
        walls = result.metadata.get("gamma_walls", [])
        return len(walls) > 0
