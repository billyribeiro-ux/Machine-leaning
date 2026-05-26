"""
Revolution Alpha Engine - Squeeze Scanner

Institutional-grade scanner for detecting squeeze conditions:
- Short Squeeze: High short interest + rising price + volume surge
- Gamma Squeeze: High gamma exposure + price approaching strike walls
- Delta Squeeze: Rapid delta hedging creating feedback loops
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from dataclasses import dataclass, field
import logging
import math

from .base import (
    AsyncStreamingScanner,
    BaseScanner,
    ScanContext,
    MarketData,
    HistoricalData,
)
from .models import (
    SqueezeScanResult,
    SqueezeType,
    ScanMode,
    SignalDirection,
    ScannerConfig,
    SqueezeFilterConfig,
    TimeFrame,
)

logger = logging.getLogger(__name__)


@dataclass
class ShortInterestData:
    """Short interest and borrow data for a symbol."""
    symbol: str
    short_interest: float  # Percentage of float
    short_shares: int
    float_shares: int
    days_to_cover: float
    cost_to_borrow: float  # Annual percentage
    utilization: float  # Percentage of available shares on loan
    ftd_count: int = 0  # Fail-to-deliver shares
    ftd_value: float = 0  # FTD dollar value
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_heavily_shorted(self) -> bool:
        """Check if stock is heavily shorted (> 20%)."""
        return self.short_interest >= 20.0

    @property
    def is_hard_to_borrow(self) -> bool:
        """Check if stock is hard to borrow."""
        return self.cost_to_borrow >= 50.0 or self.utilization >= 90.0

    @property
    def squeeze_risk_score(self) -> float:
        """Calculate basic squeeze risk score."""
        score = 0.0

        # Short interest component (max 40)
        if self.short_interest >= 40:
            score += 40
        elif self.short_interest >= 25:
            score += 30
        elif self.short_interest >= 15:
            score += 20
        elif self.short_interest >= 10:
            score += 10

        # Days to cover component (max 25)
        if self.days_to_cover >= 5:
            score += 25
        elif self.days_to_cover >= 3:
            score += 20
        elif self.days_to_cover >= 2:
            score += 15
        elif self.days_to_cover >= 1:
            score += 10

        # Cost to borrow component (max 20)
        if self.cost_to_borrow >= 100:
            score += 20
        elif self.cost_to_borrow >= 50:
            score += 15
        elif self.cost_to_borrow >= 20:
            score += 10

        # Utilization component (max 15)
        if self.utilization >= 95:
            score += 15
        elif self.utilization >= 85:
            score += 10
        elif self.utilization >= 70:
            score += 5

        return min(100, score)


@dataclass
class GammaExposureData:
    """Gamma exposure data for squeeze analysis."""
    symbol: str
    net_gamma: float  # Net gamma exposure (positive = resistance, negative = support)
    gamma_walls: list[dict]  # Price levels with significant gamma
    zero_gamma_level: Optional[float] = None  # Price where gamma flips
    gamma_tilt: float = 0  # Positive = bullish bias, negative = bearish
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_gamma_squeeze_setup(self) -> bool:
        """Check if conditions favor gamma squeeze."""
        # Negative net gamma = dealers short gamma = they buy when price rises
        return self.net_gamma < -1000000 and len(self.gamma_walls) > 0


@dataclass
class SqueezeConditions:
    """Combined squeeze conditions analysis."""
    symbol: str
    squeeze_type: Optional[SqueezeType]
    squeeze_score: float
    is_triggered: bool
    trigger_reason: str
    short_data: Optional[ShortInterestData] = None
    gamma_data: Optional[GammaExposureData] = None
    price_momentum: float = 0
    volume_ratio: float = 1.0
    key_levels: list[float] = field(default_factory=list)


class ShortSqueezeScanner(AsyncStreamingScanner[SqueezeScanResult]):
    """
    Scanner for detecting short squeeze conditions.

    Analyzes short interest, cost to borrow, volume patterns,
    and price action to identify potential short squeeze setups.
    """

    def __init__(
        self,
        config: Optional[ScannerConfig] = None,
        squeeze_config: Optional[SqueezeFilterConfig] = None
    ):
        super().__init__(
            name="short_squeeze",
            scan_mode=ScanMode.SQUEEZE,
            config=config
        )
        self.squeeze_config = squeeze_config or SqueezeFilterConfig()

    async def scan_symbol(
        self,
        symbol: str,
        context: ScanContext
    ) -> Optional[SqueezeScanResult]:
        """Scan single symbol for short squeeze conditions."""
        try:
            market_data = context.market_data.get(symbol)
            if not market_data:
                return None

            # Apply basic filters
            if not self.apply_filters(market_data):
                return None

            # Get short interest data
            short_data = self._get_short_data(symbol, context)
            if not short_data:
                return None

            # Check minimum short interest
            if short_data.short_interest < self.squeeze_config.min_short_interest:
                return None

            # Calculate squeeze score
            squeeze_score = self._calculate_squeeze_score(
                short_data, market_data, context
            )

            if squeeze_score < self.squeeze_config.min_squeeze_score:
                return None

            # Calculate volume ratio
            volume_ratio = self._calculate_volume_ratio(symbol, market_data, context)
            if volume_ratio < self.squeeze_config.min_volume_ratio:
                return None

            # Generate signal
            return self._generate_signal(
                symbol, short_data, market_data, squeeze_score, volume_ratio, context
            )

        except Exception as e:
            self._logger.warning(f"Error scanning {symbol}: {e}")
            return None

    def _get_short_data(
        self,
        symbol: str,
        context: ScanContext
    ) -> Optional[ShortInterestData]:
        """Extract short interest data from context."""
        metadata = context.metadata.get("short_interest", {})
        symbol_data = metadata.get(symbol)

        if not symbol_data:
            return None

        return ShortInterestData(
            symbol=symbol,
            short_interest=symbol_data.get("short_interest", 0),
            short_shares=symbol_data.get("short_shares", 0),
            float_shares=symbol_data.get("float_shares", 0),
            days_to_cover=symbol_data.get("days_to_cover", 0),
            cost_to_borrow=symbol_data.get("cost_to_borrow", 0),
            utilization=symbol_data.get("utilization", 0),
            ftd_count=symbol_data.get("ftd_count", 0),
        )

    def _calculate_squeeze_score(
        self,
        short_data: ShortInterestData,
        market_data: MarketData,
        context: ScanContext
    ) -> float:
        """Calculate comprehensive squeeze score."""
        score = short_data.squeeze_risk_score

        # Price momentum component
        hist_data = context.historical_data.get(short_data.symbol)
        if hist_data and len(hist_data.bars) >= 5:
            recent_closes = hist_data.closes[-5:]
            price_change = (recent_closes[-1] - recent_closes[0]) / recent_closes[0] * 100

            if price_change > 10:
                score += 15  # Strong upward momentum
            elif price_change > 5:
                score += 10
            elif price_change > 0:
                score += 5

        # Volume surge component
        if market_data.relative_volume:
            if market_data.relative_volume >= 5:
                score += 15
            elif market_data.relative_volume >= 3:
                score += 10
            elif market_data.relative_volume >= 2:
                score += 5

        # FTD component
        if short_data.ftd_count > 0:
            ftd_ratio = short_data.ftd_count / max(1, short_data.short_shares) * 100
            if ftd_ratio >= 5:
                score += 10
            elif ftd_ratio >= 2:
                score += 5

        return min(100, score)

    def _calculate_volume_ratio(
        self,
        symbol: str,
        market_data: MarketData,
        context: ScanContext
    ) -> float:
        """Calculate current volume vs average."""
        if market_data.relative_volume:
            return market_data.relative_volume

        if market_data.avg_volume_20 and market_data.avg_volume_20 > 0:
            return market_data.volume / market_data.avg_volume_20

        return 1.0

    def _identify_key_levels(
        self,
        symbol: str,
        current_price: float,
        context: ScanContext
    ) -> list[float]:
        """Identify key price levels for the squeeze."""
        levels = []

        hist_data = context.historical_data.get(symbol)
        if not hist_data or len(hist_data.bars) < 20:
            return levels

        # Recent highs as resistance
        highs = sorted(hist_data.highs[-20:], reverse=True)[:3]
        levels.extend([h for h in highs if h > current_price])

        # Round numbers
        round_levels = [
            current_price * 1.1,  # 10% above
            current_price * 1.2,  # 20% above
            math.ceil(current_price / 5) * 5,  # Next $5 level
            math.ceil(current_price / 10) * 10,  # Next $10 level
        ]
        levels.extend([l for l in round_levels if l > current_price])

        # Remove duplicates and sort
        levels = sorted(set(round(l, 2) for l in levels))[:5]

        return levels

    def _generate_signal(
        self,
        symbol: str,
        short_data: ShortInterestData,
        market_data: MarketData,
        squeeze_score: float,
        volume_ratio: float,
        context: ScanContext
    ) -> SqueezeScanResult:
        """Generate short squeeze signal."""
        current_price = market_data.close

        # Identify key levels
        key_levels = self._identify_key_levels(symbol, current_price, context)

        # Calculate entry, stop, targets
        entry_price = current_price
        stop_loss = self.calculate_stop_loss(
            entry_price,
            SignalDirection.LONG,
            market_data.atr,
            atr_multiplier=2.0,
            pct_stop=5.0
        )

        # Targets based on key levels or percentage
        if key_levels:
            targets = key_levels[:3]
        else:
            targets = self.calculate_targets(
                entry_price, stop_loss, SignalDirection.LONG,
                rr_ratios=[2.0, 3.0, 5.0]
            )

        return SqueezeScanResult(
            symbol=symbol,
            scanner_type=self.name,
            direction=SignalDirection.LONG,
            confidence=squeeze_score,
            entry_price=entry_price,
            stop_loss=stop_loss,
            targets=targets,
            risk_reward=self.calculate_risk_reward(entry_price, stop_loss, targets[0]) if targets else None,
            squeeze_type=SqueezeType.SHORT,
            squeeze_score=squeeze_score,
            gamma_walls=[],  # Not applicable for short squeeze
            key_levels=key_levels,
            volume_ratio=volume_ratio,
            short_interest=short_data.short_interest,
            days_to_cover=short_data.days_to_cover,
            cost_to_borrow=short_data.cost_to_borrow,
            ftd_count=short_data.ftd_count,
            metadata={
                "utilization": short_data.utilization,
                "float_shares": short_data.float_shares,
                "short_shares": short_data.short_shares,
                "squeeze_risk_base": short_data.squeeze_risk_score,
            }
        )

    def validate_signal(
        self,
        result: SqueezeScanResult,
        context: ScanContext
    ) -> bool:
        """Validate short squeeze signal."""
        if result.confidence < self.config.min_confidence:
            return False

        if result.squeeze_score < self.squeeze_config.min_squeeze_score:
            return False

        if result.volume_ratio < self.squeeze_config.min_volume_ratio:
            return False

        return True


class GammaSqueezeScanner(BaseScanner[SqueezeScanResult]):
    """
    Scanner for detecting gamma squeeze conditions.

    Identifies situations where market maker hedging activity
    can create a feedback loop driving prices higher/lower.
    """

    def __init__(
        self,
        config: Optional[ScannerConfig] = None
    ):
        super().__init__(
            name="gamma_squeeze",
            scan_mode=ScanMode.SQUEEZE,
            config=config
        )
        self.gamma_threshold = -1000000  # Net negative gamma = squeeze potential
        self.min_call_volume_ratio = 2.0  # Calls vs puts volume

    async def scan(self, context: ScanContext) -> list[SqueezeScanResult]:
        """Scan for gamma squeeze conditions."""
        results: list[SqueezeScanResult] = []

        for symbol in context.universe:
            market_data = context.market_data.get(symbol)
            options_data = context.options_data.get(symbol)

            if not market_data or not options_data:
                continue

            if not self.apply_filters(market_data):
                continue

            result = await self._analyze_gamma_squeeze(
                symbol, market_data, options_data, context
            )
            if result:
                results.append(result)

        return results

    async def _analyze_gamma_squeeze(
        self,
        symbol: str,
        market_data: MarketData,
        options_data: dict,
        context: ScanContext
    ) -> Optional[SqueezeScanResult]:
        """Analyze gamma squeeze potential for a symbol."""
        underlying_price = market_data.close

        # Calculate net gamma exposure
        net_gamma = 0
        gamma_by_strike: dict[float, float] = {}
        total_call_volume = 0
        total_put_volume = 0

        for contract in options_data.get("contracts", []):
            strike = contract.get("strike", 0)
            gamma = contract.get("gamma", 0)
            oi = contract.get("open_interest", 0)
            volume = contract.get("volume", 0)
            option_type = contract.get("option_type", "CALL")

            # Calculate gamma exposure at this strike
            # Gamma exposure = gamma * OI * 100 * spot^2 / 100
            gamma_exp = gamma * oi * underlying_price

            if option_type == "CALL":
                total_call_volume += volume
                # Dealers are typically short calls (customer long)
                # Short call = short gamma
                gamma_by_strike[strike] = gamma_by_strike.get(strike, 0) - gamma_exp
            else:
                total_put_volume += volume
                # Dealers are typically short puts (customer long)
                # Short put = long gamma
                gamma_by_strike[strike] = gamma_by_strike.get(strike, 0) + gamma_exp

            net_gamma += gamma_exp if option_type == "PUT" else -gamma_exp

        # Check call/put volume ratio
        if total_put_volume > 0:
            cp_ratio = total_call_volume / total_put_volume
        else:
            cp_ratio = total_call_volume if total_call_volume > 0 else 0

        # Check gamma squeeze conditions
        # Net negative gamma + high call volume = squeeze potential
        if net_gamma >= self.gamma_threshold:
            return None  # Not enough negative gamma

        if cp_ratio < self.min_call_volume_ratio:
            return None  # Not enough call buying

        # Find gamma walls (significant gamma levels)
        gamma_walls = []
        for strike, gamma_exp in sorted(gamma_by_strike.items()):
            if abs(gamma_exp) > abs(net_gamma) * 0.1:  # Significant level
                wall_type = "resistance" if gamma_exp > 0 else "magnet"
                distance_pct = ((strike - underlying_price) / underlying_price) * 100
                gamma_walls.append({
                    "strike": strike,
                    "gamma_exposure": gamma_exp,
                    "type": wall_type,
                    "distance_pct": distance_pct
                })

        # Sort by proximity
        gamma_walls.sort(key=lambda x: abs(x["distance_pct"]))

        # Calculate squeeze score
        squeeze_score = self._calculate_gamma_squeeze_score(
            net_gamma, gamma_walls, cp_ratio, market_data
        )

        if squeeze_score < 50:
            return None

        # Key levels from gamma walls
        key_levels = [w["strike"] for w in gamma_walls if w["distance_pct"] > 0][:5]

        # Calculate entry and stops
        entry_price = underlying_price
        stop_loss = self.calculate_stop_loss(
            entry_price,
            SignalDirection.LONG,
            market_data.atr,
            atr_multiplier=1.5
        )

        targets = key_levels[:3] if key_levels else self.calculate_targets(
            entry_price, stop_loss, SignalDirection.LONG
        )

        return SqueezeScanResult(
            symbol=symbol,
            scanner_type=self.name,
            direction=SignalDirection.LONG,
            confidence=squeeze_score,
            entry_price=entry_price,
            stop_loss=stop_loss,
            targets=targets,
            risk_reward=self.calculate_risk_reward(entry_price, stop_loss, targets[0]) if targets else None,
            squeeze_type=SqueezeType.GAMMA,
            squeeze_score=squeeze_score,
            gamma_walls=gamma_walls[:5],
            key_levels=key_levels,
            volume_ratio=cp_ratio,
            metadata={
                "net_gamma": net_gamma,
                "call_volume": total_call_volume,
                "put_volume": total_put_volume,
                "call_put_ratio": cp_ratio,
            }
        )

    def _calculate_gamma_squeeze_score(
        self,
        net_gamma: float,
        gamma_walls: list[dict],
        cp_ratio: float,
        market_data: MarketData
    ) -> float:
        """Calculate gamma squeeze score."""
        score = 0.0

        # Net gamma component (more negative = higher score)
        gamma_magnitude = abs(net_gamma)
        if gamma_magnitude >= 10000000:
            score += 35
        elif gamma_magnitude >= 5000000:
            score += 28
        elif gamma_magnitude >= 2000000:
            score += 20
        elif gamma_magnitude >= 1000000:
            score += 12

        # Call/put ratio component
        if cp_ratio >= 5:
            score += 25
        elif cp_ratio >= 3:
            score += 20
        elif cp_ratio >= 2:
            score += 15
        elif cp_ratio >= 1.5:
            score += 10

        # Gamma walls component
        nearby_walls = [w for w in gamma_walls if 0 < w["distance_pct"] < 10]
        if len(nearby_walls) >= 3:
            score += 20
        elif len(nearby_walls) >= 2:
            score += 15
        elif len(nearby_walls) >= 1:
            score += 10

        # Volume component
        if market_data.relative_volume:
            if market_data.relative_volume >= 3:
                score += 15
            elif market_data.relative_volume >= 2:
                score += 10
            elif market_data.relative_volume >= 1.5:
                score += 5

        return min(100, score)

    def validate_signal(
        self,
        result: SqueezeScanResult,
        context: ScanContext
    ) -> bool:
        """Validate gamma squeeze signal."""
        if result.confidence < self.config.min_confidence:
            return False

        if result.squeeze_score < 50:
            return False

        return True


class CombinedSqueezeScanner(BaseScanner[SqueezeScanResult]):
    """
    Scanner that combines short squeeze and gamma squeeze analysis.

    Identifies the most powerful setups where both conditions align.
    """

    def __init__(
        self,
        config: Optional[ScannerConfig] = None,
        squeeze_config: Optional[SqueezeFilterConfig] = None
    ):
        super().__init__(
            name="combined_squeeze",
            scan_mode=ScanMode.SQUEEZE,
            config=config
        )
        self.squeeze_config = squeeze_config or SqueezeFilterConfig()
        self.short_scanner = ShortSqueezeScanner(config, squeeze_config)
        self.gamma_scanner = GammaSqueezeScanner(config)

    async def scan(self, context: ScanContext) -> list[SqueezeScanResult]:
        """Scan for combined squeeze conditions."""
        # Run both scanners
        short_results, _ = await self.short_scanner.execute(context)
        gamma_results, _ = await self.gamma_scanner.execute(context)

        # Create lookup by symbol
        short_by_symbol = {r.symbol: r for r in short_results}
        gamma_by_symbol = {r.symbol: r for r in gamma_results}

        combined_results: list[SqueezeScanResult] = []

        # Find symbols with both conditions
        combined_symbols = set(short_by_symbol.keys()) & set(gamma_by_symbol.keys())

        for symbol in combined_symbols:
            short_result = short_by_symbol[symbol]
            gamma_result = gamma_by_symbol[symbol]

            # Create combined result with boosted confidence
            combined_score = min(100, (short_result.squeeze_score + gamma_result.squeeze_score) / 2 + 15)

            # Merge gamma walls
            all_walls = short_result.gamma_walls + gamma_result.gamma_walls
            unique_walls = {w["strike"]: w for w in all_walls}.values()
            merged_walls = sorted(unique_walls, key=lambda x: abs(x.get("distance_pct", 0)))[:5]

            # Merge key levels
            all_levels = set(short_result.key_levels + gamma_result.key_levels)
            merged_levels = sorted(all_levels)[:5]

            combined = SqueezeScanResult(
                symbol=symbol,
                scanner_type=self.name,
                direction=SignalDirection.LONG,
                confidence=combined_score,
                entry_price=short_result.entry_price,
                stop_loss=short_result.stop_loss,
                targets=merged_levels if merged_levels else short_result.targets,
                risk_reward=short_result.risk_reward,
                squeeze_type=SqueezeType.COMBINED,
                squeeze_score=combined_score,
                gamma_walls=list(merged_walls),
                key_levels=merged_levels,
                volume_ratio=max(short_result.volume_ratio, gamma_result.volume_ratio),
                short_interest=short_result.short_interest,
                days_to_cover=short_result.days_to_cover,
                cost_to_borrow=short_result.cost_to_borrow,
                ftd_count=short_result.ftd_count,
                metadata={
                    "short_squeeze_score": short_result.squeeze_score,
                    "gamma_squeeze_score": gamma_result.squeeze_score,
                    "combined": True,
                    **short_result.metadata,
                    **gamma_result.metadata,
                }
            )
            combined_results.append(combined)

        # Add remaining high-confidence individual results
        for result in short_results:
            if result.symbol not in combined_symbols and result.squeeze_score >= 75:
                combined_results.append(result)

        for result in gamma_results:
            if result.symbol not in combined_symbols and result.squeeze_score >= 75:
                combined_results.append(result)

        # Sort by score
        combined_results.sort(key=lambda x: x.squeeze_score, reverse=True)

        return combined_results

    def validate_signal(
        self,
        result: SqueezeScanResult,
        context: ScanContext
    ) -> bool:
        """Validate combined squeeze signal."""
        if result.confidence < self.config.min_confidence:
            return False

        return result.squeeze_score >= self.squeeze_config.min_squeeze_score
