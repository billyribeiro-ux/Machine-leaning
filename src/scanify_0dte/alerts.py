"""
SCANIFY SPX 0DTE Options Day Trading Scanner + GEX Scanner -- Alert & Notification System

Production-grade alert management, rule-based alert generation, and multi-channel
notification dispatching for the SCANIFY 0DTE trading system.

This module provides:

    AlertLevel / AlertType      Enumerations for severity and category classification.
    Alert                       Immutable dataclass representing a single alert instance.
    AlertManager                Central registry for creating, querying, acknowledging,
                                and expiring alerts.
    AlertRuleEngine             Automatic alert generation from market conditions,
                                position state, and risk thresholds.
    NotificationDispatcher      Async multi-channel dispatch (terminal, webhook, sound)
                                with structured formatting.

All timestamps are UTC.  Alert IDs are UUID4 strings.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional

import aiohttp

from .constants import (
    GEX_SCANNER,
    RISK_MANAGEMENT,
    VIX1D,
)

logger = logging.getLogger(__name__)


# =============================================================================
# 1. ENUMERATIONS
# =============================================================================


class AlertLevel(str, Enum):
    """Severity classification for alerts.

    Ordered from most severe to least severe.  Consumers may filter on
    level to control notification volume (e.g. only CRITICAL and HIGH
    during settlement window).
    """

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class AlertType(str, Enum):
    """Category classification for alerts.

    Each alert type maps to a specific domain event within the SCANIFY
    system -- from trade lifecycle events through GEX structural shifts
    to system health notifications.
    """

    # -- Trade lifecycle ------------------------------------------------------
    SIGNAL_GENERATED = "SIGNAL_GENERATED"
    POSITION_OPENED = "POSITION_OPENED"
    POSITION_CLOSED = "POSITION_CLOSED"
    PROFIT_TARGET_HIT = "PROFIT_TARGET_HIT"
    STOP_LOSS_HIT = "STOP_LOSS_HIT"

    # -- GEX / gamma events ---------------------------------------------------
    GEX_FLIP = "GEX_FLIP"
    GAMMA_SQUEEZE = "GAMMA_SQUEEZE"
    GAMMA_WALL_BREACH = "GAMMA_WALL_BREACH"

    # -- Market condition events ----------------------------------------------
    VIX_SPIKE = "VIX_SPIKE"
    ECONOMIC_EVENT_WARNING = "ECONOMIC_EVENT_WARNING"
    SESSION_CHANGE = "SESSION_CHANGE"
    REGIME_CHANGE = "REGIME_CHANGE"

    # -- System health --------------------------------------------------------
    SYSTEM_ERROR = "SYSTEM_ERROR"
    CONNECTION_LOST = "CONNECTION_LOST"
    CALIBRATION_COMPLETE = "CALIBRATION_COMPLETE"


# =============================================================================
# 2. ALERT DATA MODEL
# =============================================================================


# Severity ordering for comparison and sorting (lower index = more severe)
_LEVEL_SEVERITY_ORDER: dict[AlertLevel, int] = {
    AlertLevel.CRITICAL: 0,
    AlertLevel.HIGH: 1,
    AlertLevel.MEDIUM: 2,
    AlertLevel.LOW: 3,
    AlertLevel.INFO: 4,
}


@dataclass
class Alert:
    """Immutable representation of a single alert instance.

    Attributes:
        alert_id:       Unique UUID4 identifier for this alert.
        alert_type:     Category of the alert (trade, GEX, system, etc.).
        level:          Severity level (CRITICAL through INFO).
        title:          Short human-readable headline (< 120 chars recommended).
        message:        Detailed description of the alert condition.
        timestamp:      UTC datetime when the alert was created.
        data:           Arbitrary key-value payload with context-specific data
                        (e.g. strike prices, PnL figures, GEX values).
        acknowledged:   Whether a human or automated consumer has acknowledged
                        this alert.
        expired:        Whether this alert has exceeded its TTL and should no
                        longer appear in active queries.
    """

    alert_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    alert_type: AlertType = AlertType.SIGNAL_GENERATED
    level: AlertLevel = AlertLevel.INFO
    title: str = ""
    message: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    data: dict[str, Any] = field(default_factory=dict)
    acknowledged: bool = False
    expired: bool = False

    # -- Computed helpers ------------------------------------------------------

    @property
    def severity_rank(self) -> int:
        """Numeric severity rank (0 = most severe)."""
        return _LEVEL_SEVERITY_ORDER.get(self.level, 99)

    @property
    def age_seconds(self) -> float:
        """Seconds elapsed since this alert was created."""
        now = datetime.now(timezone.utc)
        return (now - self.timestamp).total_seconds()

    @property
    def is_actionable(self) -> bool:
        """Alert is neither acknowledged nor expired."""
        return not self.acknowledged and not self.expired

    def __repr__(self) -> str:
        return (
            f"Alert(id={self.alert_id[:8]}..., type={self.alert_type.value}, "
            f"level={self.level.value}, title={self.title!r})"
        )


# =============================================================================
# 3. ALERT MANAGER
# =============================================================================


class AlertManager:
    """Central registry for creating, querying, and managing alerts.

    The AlertManager maintains an in-memory ring buffer of alerts with
    configurable capacity and automatic expiry.  It serves as the single
    source of truth for the alert state consumed by the UI, webhook
    dispatcher, and rule engine.

    Parameters:
        max_alerts:                     Maximum number of alerts retained in
                                        the ring buffer.  Oldest alerts are
                                        evicted when the limit is exceeded.
        alert_expiry_minutes:           Minutes after creation at which an
                                        unacknowledged alert is marked expired.
        enable_sound:                   Whether audible terminal bells are
                                        permitted for CRITICAL alerts.
        enable_desktop_notifications:   Whether OS-level desktop notifications
                                        are dispatched (requires platform support).
        webhook_urls:                   List of HTTP(S) endpoints to receive
                                        JSON alert payloads via POST.

    Example::

        manager = AlertManager(max_alerts=500, alert_expiry_minutes=30)
        alert = manager.create_alert(
            alert_type=AlertType.VIX_SPIKE,
            level=AlertLevel.HIGH,
            title="VIX1D spike detected",
            message="VIX1D surged 35% in the last 5 minutes.",
            data={"vix1d": 22.5, "vix1d_5min_ago": 16.7},
        )
    """

    def __init__(
        self,
        max_alerts: int = 1000,
        alert_expiry_minutes: int = 60,
        enable_sound: bool = True,
        enable_desktop_notifications: bool = True,
        webhook_urls: list[str] | None = None,
    ) -> None:
        self._max_alerts = max_alerts
        self._alert_expiry_minutes = alert_expiry_minutes
        self.enable_sound = enable_sound
        self.enable_desktop_notifications = enable_desktop_notifications
        self.webhook_urls: list[str] = webhook_urls if webhook_urls is not None else []

        # Internal storage -- list used as an ordered ring buffer
        self._alerts: list[Alert] = []
        # Fast lookup by ID
        self._alerts_by_id: dict[str, Alert] = {}

        logger.info(
            "AlertManager initialised: max_alerts=%d, expiry=%d min, "
            "webhooks=%d, sound=%s, desktop=%s",
            self._max_alerts,
            self._alert_expiry_minutes,
            len(self.webhook_urls),
            self.enable_sound,
            self.enable_desktop_notifications,
        )

    # -- Creation -------------------------------------------------------------

    def create_alert(
        self,
        alert_type: AlertType,
        level: AlertLevel,
        title: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> Alert:
        """Create a new alert, register it, and return it.

        If the buffer is at capacity, the oldest alert is evicted before
        the new one is inserted.

        Args:
            alert_type: Category of the alert.
            level:      Severity level.
            title:      Short headline.
            message:    Detailed description.
            data:       Optional context payload.

        Returns:
            The newly created ``Alert`` instance.
        """
        alert = Alert(
            alert_type=alert_type,
            level=level,
            title=title,
            message=message,
            data=data if data is not None else {},
        )

        # Enforce ring-buffer capacity
        if len(self._alerts) >= self._max_alerts:
            if self._alerts:
                evicted = self._alerts.pop(0)
                self._alerts_by_id.pop(evicted.alert_id, None)
            logger.debug(
                "Alert buffer full -- evicted oldest alert %s", evicted.alert_id[:8]
            )

        self._alerts.append(alert)
        self._alerts_by_id[alert.alert_id] = alert

        logger.info(
            "Alert created: [%s] %s -- %s (id=%s)",
            level.value,
            alert_type.value,
            title,
            alert.alert_id[:8],
        )

        return alert

    # -- Querying -------------------------------------------------------------

    def get_active_alerts(
        self,
        level: AlertLevel | None = None,
        alert_type: AlertType | None = None,
    ) -> list[Alert]:
        """Return all alerts that are neither acknowledged nor expired.

        Results are sorted by severity (most severe first), then by
        timestamp (newest first within the same severity).

        Args:
            level:      Optional filter -- only return alerts at this level.
            alert_type: Optional filter -- only return alerts of this type.

        Returns:
            List of active ``Alert`` instances matching the filters.
        """
        active: list[Alert] = []
        for alert in self._alerts:
            if alert.acknowledged or alert.expired:
                continue
            if level is not None and alert.level != level:
                continue
            if alert_type is not None and alert.alert_type != alert_type:
                continue
            active.append(alert)

        # Sort: severity ascending (lower rank = more severe), then newest first
        active.sort(key=lambda a: (a.severity_rank, -a.timestamp.timestamp()))
        return active

    def get_recent_alerts(self, minutes: int = 30) -> list[Alert]:
        """Return all alerts created within the last ``minutes`` minutes.

        Includes acknowledged and expired alerts.  Results are sorted
        newest-first.

        Args:
            minutes: Lookback window in minutes.

        Returns:
            List of ``Alert`` instances created within the window.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        recent = [a for a in self._alerts if a.timestamp >= cutoff]
        recent.sort(key=lambda a: a.timestamp, reverse=True)
        return recent

    # -- State mutations ------------------------------------------------------

    def acknowledge_alert(self, alert_id: str) -> None:
        """Mark an alert as acknowledged by its unique ID.

        Args:
            alert_id: UUID4 string of the alert to acknowledge.

        Raises:
            KeyError: If no alert with the given ID exists.
        """
        alert = self._alerts_by_id.get(alert_id)
        if alert is None:
            raise KeyError(f"Alert not found: {alert_id}")
        alert.acknowledged = True
        logger.debug("Alert acknowledged: %s", alert_id[:8])

    def clear_expired(self) -> int:
        """Mark all alerts older than the configured TTL as expired.

        Returns:
            The number of alerts newly marked as expired in this pass.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(
            minutes=self._alert_expiry_minutes
        )
        count = 0
        for alert in self._alerts:
            if not alert.expired and alert.timestamp < cutoff:
                alert.expired = True
                count += 1

        if count > 0:
            logger.debug("Expired %d alert(s) older than %d min", count, self._alert_expiry_minutes)
        return count

    # -- Analytics ------------------------------------------------------------

    def get_alert_count_by_level(self) -> dict[str, int]:
        """Return a count of active (non-acknowledged, non-expired) alerts
        grouped by severity level.

        Returns:
            Dictionary mapping ``AlertLevel.value`` strings to integer counts.
        """
        counts: dict[str, int] = {level.value: 0 for level in AlertLevel}
        for alert in self._alerts:
            if not alert.acknowledged and not alert.expired:
                counts[alert.level.value] += 1
        return counts

    @property
    def total_alert_count(self) -> int:
        """Total number of alerts currently in the buffer (all states)."""
        return len(self._alerts)

    @property
    def active_alert_count(self) -> int:
        """Number of alerts that are neither acknowledged nor expired."""
        return sum(
            1 for a in self._alerts if not a.acknowledged and not a.expired
        )


# =============================================================================
# 4. ALERT RULE ENGINE
# =============================================================================


class AlertRuleEngine:
    """Automatic alert generation from market conditions and position state.

    The rule engine evaluates a set of predefined rules against the
    current market snapshot and open positions.  Each rule produces an
    ``Alert`` (via the bound ``AlertManager``) when its condition is met,
    or returns ``None`` when the condition is not triggered.

    All threshold values default to the constants defined in
    ``scanify_0dte.constants`` but can be overridden at construction time.

    Parameters:
        alert_manager:  The ``AlertManager`` instance used to register
                        generated alerts.

    Example::

        engine = AlertRuleEngine(alert_manager=manager)
        alert = engine.check_vix_spike(vix1d=24.0, vix1d_5min_ago=17.5)
        if alert:
            await dispatcher.dispatch_alert(alert)
    """

    def __init__(self, alert_manager: AlertManager) -> None:
        self._manager = alert_manager
        logger.info("AlertRuleEngine initialised with AlertManager")

    # -- Individual rule checks -----------------------------------------------

    def check_vix_spike(
        self,
        vix1d: float,
        vix1d_5min_ago: float,
    ) -> Optional[Alert]:
        """Check for a VIX1D intraday spike exceeding the configured threshold.

        A spike is defined as a percentage increase in VIX1D over the
        observation window that exceeds ``VIX1D.spike_threshold_pct``.

        Args:
            vix1d:          Current VIX1D reading.
            vix1d_5min_ago: VIX1D reading 5 minutes prior.

        Returns:
            An ``Alert`` if a spike is detected, otherwise ``None``.
        """
        if vix1d_5min_ago <= 0:
            return None

        change_pct = (vix1d - vix1d_5min_ago) / vix1d_5min_ago

        if change_pct >= VIX1D.spike_threshold_pct:
            level = (
                AlertLevel.CRITICAL
                if change_pct >= VIX1D.spike_threshold_pct * 2.0
                else AlertLevel.HIGH
            )
            return self._manager.create_alert(
                alert_type=AlertType.VIX_SPIKE,
                level=level,
                title=f"VIX1D spike: {vix1d:.1f} (+{change_pct * 100:.1f}%)",
                message=(
                    f"VIX1D surged from {vix1d_5min_ago:.2f} to {vix1d:.2f} "
                    f"({change_pct * 100:.1f}% increase) in the last 5 minutes.  "
                    f"Threshold: {VIX1D.spike_threshold_pct * 100:.0f}%.  "
                    f"Consider reducing position size or tightening stops."
                ),
                data={
                    "vix1d": vix1d,
                    "vix1d_5min_ago": vix1d_5min_ago,
                    "change_pct": round(change_pct * 100, 2),
                    "threshold_pct": VIX1D.spike_threshold_pct * 100,
                },
            )
        return None

    def check_gex_shift(
        self,
        current_gex: float,
        prior_gex: float,
    ) -> Optional[Alert]:
        """Check for a significant shift in aggregate net GEX.

        A shift is triggered when the absolute percentage change in net
        GEX exceeds ``GEX_SCANNER.shift_alert_threshold_pct``.  A sign
        change (positive to negative or vice versa) is elevated to a
        GEX_FLIP alert at CRITICAL level.

        Args:
            current_gex: Current aggregate net GEX value.
            prior_gex:   Prior aggregate net GEX value (from the last
                         observation window).

        Returns:
            An ``Alert`` if a significant shift is detected, otherwise ``None``.
        """
        if abs(prior_gex) < GEX_SCANNER.min_meaningful_gex:
            return None

        # Detect sign flip (positive gamma <-> negative gamma)
        sign_flipped = (current_gex > 0) != (prior_gex > 0)

        change_pct = abs(current_gex - prior_gex) / abs(prior_gex)

        if sign_flipped:
            return self._manager.create_alert(
                alert_type=AlertType.GEX_FLIP,
                level=AlertLevel.CRITICAL,
                title="GEX flip detected: gamma regime change",
                message=(
                    f"Aggregate dealer gamma flipped from "
                    f"{'positive' if prior_gex > 0 else 'negative'} to "
                    f"{'positive' if current_gex > 0 else 'negative'} territory.  "
                    f"Prior GEX: {prior_gex:,.0f}, Current GEX: {current_gex:,.0f}.  "
                    f"Expect a change in market microstructure and hedging flow direction."
                ),
                data={
                    "current_gex": current_gex,
                    "prior_gex": prior_gex,
                    "change_pct": round(change_pct * 100, 2),
                    "sign_flipped": True,
                    "new_regime": "positive" if current_gex > 0 else "negative",
                },
            )

        if change_pct >= GEX_SCANNER.shift_alert_threshold_pct:
            return self._manager.create_alert(
                alert_type=AlertType.GEX_FLIP,
                level=AlertLevel.HIGH,
                title=f"GEX shift: {change_pct * 100:.1f}% change detected",
                message=(
                    f"Aggregate net GEX shifted {change_pct * 100:.1f}% "
                    f"(from {prior_gex:,.0f} to {current_gex:,.0f}) within the "
                    f"last {GEX_SCANNER.shift_alert_window_minutes} minutes.  "
                    f"Threshold: {GEX_SCANNER.shift_alert_threshold_pct * 100:.0f}%."
                ),
                data={
                    "current_gex": current_gex,
                    "prior_gex": prior_gex,
                    "change_pct": round(change_pct * 100, 2),
                    "sign_flipped": False,
                },
            )

        return None

    def check_economic_event_approaching(
        self,
        events: list[Any],
        current_time: datetime,
    ) -> Optional[Alert]:
        """Check whether a high-impact economic event is imminent.

        Scans the provided event list for HIGH-impact events occurring
        within the next 15 minutes.  Events that have already been
        released (``is_released is True``) are skipped.

        Args:
            events:         List of ``EconomicEvent`` model instances.
            current_time:   Current UTC datetime.

        Returns:
            An ``Alert`` if a high-impact event is approaching, otherwise ``None``.
        """
        warning_window = timedelta(minutes=15)

        for event in events:
            # Skip already-released events
            if hasattr(event, "is_released") and event.is_released:
                continue

            # Only alert on high-impact events
            if hasattr(event, "is_high_impact") and not event.is_high_impact:
                continue

            event_time = event.time if hasattr(event, "time") else None
            if event_time is None:
                continue

            time_until = event_time - current_time
            if timedelta(0) < time_until <= warning_window:
                minutes_remaining = time_until.total_seconds() / 60.0
                event_name = getattr(event, "name", "Unknown")

                level = (
                    AlertLevel.CRITICAL
                    if minutes_remaining <= 5.0
                    else AlertLevel.HIGH
                )
                return self._manager.create_alert(
                    alert_type=AlertType.ECONOMIC_EVENT_WARNING,
                    level=level,
                    title=f"Economic event in {minutes_remaining:.0f} min: {event_name}",
                    message=(
                        f"HIGH-impact economic event '{event_name}' is scheduled in "
                        f"{minutes_remaining:.1f} minutes (at {event_time.strftime('%H:%M:%S')} UTC).  "
                        f"Consider reducing exposure or widening stops to account for "
                        f"potential volatility spike on release."
                    ),
                    data={
                        "event_name": event_name,
                        "event_time": event_time.isoformat(),
                        "minutes_remaining": round(minutes_remaining, 1),
                        "impact_level": getattr(
                            getattr(event, "impact_level", None), "value", "HIGH"
                        ),
                    },
                )

        return None

    def check_position_at_risk(
        self,
        position: Any,
        current_price: float,
    ) -> Optional[Alert]:
        """Check whether an open position is approaching its stop-loss level.

        Triggers a warning when the current price has moved more than 70%
        of the way from the entry to the stop, giving the trader time to
        act before the hard stop fires.

        Args:
            position:       An object with ``entry_price``, ``stop_loss``,
                            ``direction``, ``strike``, and ``option_type``
                            attributes (e.g. a ``ScanSignal`` or ``TradeLog``).
            current_price:  Current mid-market price of the position.

        Returns:
            An ``Alert`` if the position is at risk, otherwise ``None``.
        """
        entry_price = getattr(position, "entry_price", None)
        stop_loss = getattr(position, "stop_loss", None)

        if entry_price is None or stop_loss is None or entry_price == stop_loss:
            return None

        # Calculate how far through the entry-to-stop range the price has moved
        total_distance = abs(entry_price - stop_loss)
        current_distance = abs(entry_price - current_price)

        # Only warn when the price is moving *towards* the stop
        if total_distance <= 0:
            return None

        risk_ratio = current_distance / total_distance

        if risk_ratio >= 0.70:
            direction = getattr(position, "direction", "UNKNOWN")
            strike = getattr(position, "strike", "N/A")
            option_type = getattr(position, "option_type", "N/A")

            level = AlertLevel.CRITICAL if risk_ratio >= 0.90 else AlertLevel.HIGH

            return self._manager.create_alert(
                alert_type=AlertType.STOP_LOSS_HIT,
                level=level,
                title=f"Position at risk: {risk_ratio * 100:.0f}% toward stop",
                message=(
                    f"Position ({direction} {strike} {option_type}) is "
                    f"{risk_ratio * 100:.0f}% of the way from entry ({entry_price:.2f}) "
                    f"to stop-loss ({stop_loss:.2f}).  Current price: {current_price:.2f}.  "
                    f"Remaining buffer: {total_distance - current_distance:.2f}."
                ),
                data={
                    "entry_price": entry_price,
                    "stop_loss": stop_loss,
                    "current_price": current_price,
                    "risk_ratio": round(risk_ratio, 4),
                    "remaining_buffer": round(total_distance - current_distance, 4),
                    "direction": str(direction),
                    "strike": str(strike),
                },
            )

        return None

    def check_daily_loss_limit(
        self,
        daily_pnl: float,
        limit: float,
    ) -> Optional[Alert]:
        """Check whether the daily PnL has breached the loss limit.

        Generates a HIGH alert at 75% of the limit and a CRITICAL alert
        when the full limit is breached.

        Args:
            daily_pnl: Current cumulative daily PnL (negative = loss).
            limit:     Maximum allowable daily loss (positive number
                       representing the absolute loss cap in dollars).

        Returns:
            An ``Alert`` if the daily loss limit is approached or breached,
            otherwise ``None``.
        """
        if limit <= 0 or daily_pnl >= 0:
            return None

        loss_magnitude = abs(daily_pnl)
        loss_ratio = loss_magnitude / limit

        if loss_ratio >= 1.0:
            return self._manager.create_alert(
                alert_type=AlertType.SYSTEM_ERROR,
                level=AlertLevel.CRITICAL,
                title=f"DAILY LOSS LIMIT BREACHED: ${loss_magnitude:,.2f}",
                message=(
                    f"Daily PnL has breached the maximum loss limit.  "
                    f"PnL: -${loss_magnitude:,.2f}, Limit: ${limit:,.2f} "
                    f"({loss_ratio * 100:.1f}% of limit).  "
                    f"ALL TRADING SHOULD HALT IMMEDIATELY."
                ),
                data={
                    "daily_pnl": daily_pnl,
                    "limit": limit,
                    "loss_ratio": round(loss_ratio, 4),
                    "breached": True,
                },
            )
        elif loss_ratio >= 0.75:
            return self._manager.create_alert(
                alert_type=AlertType.SYSTEM_ERROR,
                level=AlertLevel.HIGH,
                title=f"Approaching daily loss limit: {loss_ratio * 100:.0f}%",
                message=(
                    f"Daily PnL is at {loss_ratio * 100:.0f}% of the maximum loss limit.  "
                    f"PnL: -${loss_magnitude:,.2f}, Limit: ${limit:,.2f}.  "
                    f"Remaining budget: ${limit - loss_magnitude:,.2f}.  "
                    f"Consider reducing position sizes or pausing new entries."
                ),
                data={
                    "daily_pnl": daily_pnl,
                    "limit": limit,
                    "loss_ratio": round(loss_ratio, 4),
                    "remaining_budget": round(limit - loss_magnitude, 2),
                    "breached": False,
                },
            )

        return None

    def check_gamma_explosion(
        self,
        gamma: float,
        threshold: float,
    ) -> Optional[Alert]:
        """Check for an extreme gamma condition (gamma squeeze / explosion).

        When ATM gamma exceeds the specified threshold, dealer hedging
        flows can amplify directional moves in a self-reinforcing loop.

        Args:
            gamma:      Current aggregate or per-strike gamma value.
            threshold:  Gamma level above which an explosion alert fires.

        Returns:
            An ``Alert`` if gamma exceeds the threshold, otherwise ``None``.
        """
        if gamma <= threshold:
            return None

        explosion_ratio = gamma / threshold if threshold > 0 else float("inf")

        level = (
            AlertLevel.CRITICAL
            if explosion_ratio >= 2.0
            else AlertLevel.HIGH
            if explosion_ratio >= 1.5
            else AlertLevel.MEDIUM
        )

        return self._manager.create_alert(
            alert_type=AlertType.GAMMA_SQUEEZE,
            level=level,
            title=f"Gamma explosion: {explosion_ratio:.1f}x threshold",
            message=(
                f"Current gamma ({gamma:.4f}) exceeds the explosion threshold "
                f"({threshold:.4f}) by {explosion_ratio:.1f}x.  "
                f"Dealer hedging flow is likely amplifying directional moves.  "
                f"Expect accelerated price action and potential pin risk."
            ),
            data={
                "gamma": gamma,
                "threshold": threshold,
                "explosion_ratio": round(explosion_ratio, 4),
            },
        )

    def check_liquidity_deterioration(
        self,
        spread: float,
        avg_spread: float,
    ) -> Optional[Alert]:
        """Check for deteriorating liquidity conditions.

        Fires when the current bid-ask spread exceeds the recent average
        by a significant margin, indicating reduced market-maker presence
        or elevated uncertainty.

        Args:
            spread:     Current bid-ask spread (in dollars or basis points).
            avg_spread: Recent average spread over the same metric.

        Returns:
            An ``Alert`` if liquidity has significantly deteriorated,
            otherwise ``None``.
        """
        if avg_spread <= 0 or spread <= avg_spread:
            return None

        spread_ratio = spread / avg_spread

        # 2x average = MEDIUM, 3x = HIGH, 5x = CRITICAL
        if spread_ratio >= 5.0:
            level = AlertLevel.CRITICAL
        elif spread_ratio >= 3.0:
            level = AlertLevel.HIGH
        elif spread_ratio >= 2.0:
            level = AlertLevel.MEDIUM
        else:
            return None

        return self._manager.create_alert(
            alert_type=AlertType.REGIME_CHANGE,
            level=level,
            title=f"Liquidity deterioration: spread {spread_ratio:.1f}x average",
            message=(
                f"Current bid-ask spread ({spread:.4f}) is {spread_ratio:.1f}x "
                f"the recent average ({avg_spread:.4f}).  "
                f"Market-maker participation may be reduced.  "
                f"Consider widening slippage tolerance or avoiding new entries "
                f"until liquidity normalises."
            ),
            data={
                "spread": spread,
                "avg_spread": avg_spread,
                "spread_ratio": round(spread_ratio, 4),
            },
        )

    # -- Aggregate evaluation -------------------------------------------------

    def evaluate_all_rules(self, market_state: dict[str, Any]) -> list[Alert]:
        """Evaluate all registered rules against the provided market snapshot.

        This is the primary entry point for periodic rule evaluation.  It
        collects alerts from every individual rule that fires and returns
        them as a single batch.

        The ``market_state`` dictionary is expected to contain the following
        keys (all optional -- missing keys cause the corresponding rule to
        be skipped):

            vix1d               Current VIX1D value.
            vix1d_5min_ago      VIX1D value 5 minutes ago.
            current_gex         Current aggregate net GEX.
            prior_gex           Prior aggregate net GEX.
            economic_events     List of EconomicEvent instances.
            current_time        Current UTC datetime.
            positions           List of open position objects.
            position_prices     Dict mapping position index to current price.
            daily_pnl           Cumulative daily PnL.
            daily_loss_limit    Maximum daily loss.
            gamma               Current aggregate gamma.
            gamma_threshold     Gamma explosion threshold.
            spread              Current bid-ask spread.
            avg_spread          Recent average spread.

        Args:
            market_state: Dictionary of current market data and position state.

        Returns:
            List of ``Alert`` instances generated by rules that fired.
        """
        alerts: list[Alert] = []

        # -- VIX spike --------------------------------------------------------
        vix1d = market_state.get("vix1d")
        vix1d_5min_ago = market_state.get("vix1d_5min_ago")
        if vix1d is not None and vix1d_5min_ago is not None:
            alert = self.check_vix_spike(vix1d, vix1d_5min_ago)
            if alert is not None:
                alerts.append(alert)

        # -- GEX shift --------------------------------------------------------
        current_gex = market_state.get("current_gex")
        prior_gex = market_state.get("prior_gex")
        if current_gex is not None and prior_gex is not None:
            alert = self.check_gex_shift(current_gex, prior_gex)
            if alert is not None:
                alerts.append(alert)

        # -- Economic events --------------------------------------------------
        events = market_state.get("economic_events")
        current_time = market_state.get("current_time")
        if events is not None and current_time is not None:
            alert = self.check_economic_event_approaching(events, current_time)
            if alert is not None:
                alerts.append(alert)

        # -- Positions at risk ------------------------------------------------
        positions = market_state.get("positions", [])
        position_prices = market_state.get("position_prices", {})
        for idx, position in enumerate(positions):
            price = position_prices.get(idx)
            if price is not None:
                alert = self.check_position_at_risk(position, price)
                if alert is not None:
                    alerts.append(alert)

        # -- Daily loss limit -------------------------------------------------
        daily_pnl = market_state.get("daily_pnl")
        daily_loss_limit = market_state.get("daily_loss_limit")
        if daily_pnl is not None and daily_loss_limit is not None:
            alert = self.check_daily_loss_limit(daily_pnl, daily_loss_limit)
            if alert is not None:
                alerts.append(alert)

        # -- Gamma explosion --------------------------------------------------
        gamma = market_state.get("gamma")
        gamma_threshold = market_state.get("gamma_threshold")
        if gamma is not None and gamma_threshold is not None:
            alert = self.check_gamma_explosion(gamma, gamma_threshold)
            if alert is not None:
                alerts.append(alert)

        # -- Liquidity deterioration ------------------------------------------
        spread = market_state.get("spread")
        avg_spread = market_state.get("avg_spread")
        if spread is not None and avg_spread is not None:
            alert = self.check_liquidity_deterioration(spread, avg_spread)
            if alert is not None:
                alerts.append(alert)

        if alerts:
            logger.info(
                "Rule evaluation complete: %d alert(s) generated from %d rules",
                len(alerts),
                7,
            )

        return alerts


# =============================================================================
# 5. NOTIFICATION DISPATCHER
# =============================================================================

# ANSI colour codes for terminal output
_ANSI_COLORS: dict[AlertLevel, str] = {
    AlertLevel.CRITICAL: "\033[1;97;41m",  # Bold white on red background
    AlertLevel.HIGH: "\033[1;91m",          # Bold bright red
    AlertLevel.MEDIUM: "\033[1;93m",        # Bold yellow
    AlertLevel.LOW: "\033[1;96m",           # Bold cyan
    AlertLevel.INFO: "\033[0;37m",          # Normal white/grey
}
_ANSI_RESET = "\033[0m"

# Level symbols for compact terminal display
_LEVEL_SYMBOLS: dict[AlertLevel, str] = {
    AlertLevel.CRITICAL: "!!!",
    AlertLevel.HIGH: " !! ",
    AlertLevel.MEDIUM: " ! ",
    AlertLevel.LOW: " i ",
    AlertLevel.INFO: "   ",
}


class NotificationDispatcher:
    """Multi-channel alert dispatcher with async webhook delivery.

    Dispatches ``Alert`` instances to one or more output channels:

        - **Terminal**: Coloured formatted output to stderr.
        - **Webhook**: Async HTTP POST of JSON payloads to configured URLs.
        - **Sound**: Terminal bell character for CRITICAL and HIGH alerts.

    The dispatcher is stateless -- it does not track which alerts have
    been dispatched.  Deduplication is the responsibility of the caller
    (typically the ``AlertManager``).

    Parameters:
        alert_manager:      The ``AlertManager`` providing configuration
                            (webhook URLs, sound/desktop toggles).
        webhook_timeout:    Timeout in seconds for each webhook POST request.

    Example::

        dispatcher = NotificationDispatcher(alert_manager=manager)
        await dispatcher.dispatch_alert(alert)
    """

    def __init__(
        self,
        alert_manager: AlertManager,
        webhook_timeout: float = 10.0,
    ) -> None:
        self._manager = alert_manager
        self._webhook_timeout = webhook_timeout
        logger.info(
            "NotificationDispatcher initialised: webhook_timeout=%.1fs",
            self._webhook_timeout,
        )

    # -- Primary dispatch entry point -----------------------------------------

    async def dispatch_alert(self, alert: Alert) -> None:
        """Dispatch an alert to all configured channels.

        This coroutine runs the terminal output synchronously, then
        fires webhook POSTs concurrently.  Sound is emitted after
        all other channels have been dispatched.

        Args:
            alert: The ``Alert`` instance to dispatch.
        """
        # Terminal output (always enabled)
        terminal_text = self.format_terminal_alert(alert)
        sys.stderr.write(terminal_text + "\n")
        sys.stderr.flush()

        # Webhook dispatch (concurrent)
        if self._manager.webhook_urls:
            webhook_tasks = [
                self.send_webhook(url, alert)
                for url in self._manager.webhook_urls
            ]
            results = await asyncio.gather(*webhook_tasks, return_exceptions=True)
            success_count = sum(1 for r in results if r is True)
            failure_count = len(results) - success_count
            if failure_count > 0:
                logger.warning(
                    "Webhook dispatch: %d/%d succeeded for alert %s",
                    success_count,
                    len(results),
                    alert.alert_id[:8],
                )

        # Sound alert (terminal bell)
        self.sound_alert(alert.level)

        logger.debug(
            "Alert dispatched to all channels: %s [%s]",
            alert.alert_id[:8],
            alert.level.value,
        )

    # -- Webhook delivery -----------------------------------------------------

    async def send_webhook(self, url: str, alert: Alert) -> bool:
        """Send an alert payload to a single webhook URL via HTTP POST.

        The request body is the JSON-serialised output of
        ``format_json_alert()``.  Follows a fire-and-forget pattern with
        a configurable timeout.

        Args:
            url:    The webhook endpoint URL (must be HTTPS in production).
            alert:  The ``Alert`` to send.

        Returns:
            ``True`` if the POST returned a 2xx status, ``False`` otherwise.
        """
        payload = self.format_json_alert(alert)
        timeout = aiohttp.ClientTimeout(total=self._webhook_timeout)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                ) as response:
                    if 200 <= response.status < 300:
                        logger.debug(
                            "Webhook delivered: %s -> %s (HTTP %d)",
                            alert.alert_id[:8],
                            url,
                            response.status,
                        )
                        return True
                    else:
                        logger.warning(
                            "Webhook failed: %s -> %s (HTTP %d)",
                            alert.alert_id[:8],
                            url,
                            response.status,
                        )
                        return False
        except asyncio.TimeoutError:
            logger.warning(
                "Webhook timeout: %s -> %s (%.1fs)",
                alert.alert_id[:8],
                url,
                self._webhook_timeout,
            )
            return False
        except aiohttp.ClientError as exc:
            logger.warning(
                "Webhook connection error: %s -> %s (%s)",
                alert.alert_id[:8],
                url,
                exc,
            )
            return False
        except Exception as exc:
            logger.error(
                "Unexpected webhook error: %s -> %s (%s: %s)",
                alert.alert_id[:8],
                url,
                type(exc).__name__,
                exc,
            )
            return False

    # -- Formatting -----------------------------------------------------------

    def format_terminal_alert(self, alert: Alert) -> str:
        """Format an alert as a coloured terminal string.

        Produces a multi-line block with ANSI colour codes suitable for
        direct output to a terminal emulator.  The format includes:

            - Severity-coloured prefix with level symbol
            - Alert type and timestamp
            - Title (bold)
            - Message body (wrapped to ~80 chars where practical)

        Args:
            alert: The ``Alert`` to format.

        Returns:
            ANSI-coloured string ready for terminal output.
        """
        colour = _ANSI_COLORS.get(alert.level, _ANSI_RESET)
        symbol = _LEVEL_SYMBOLS.get(alert.level, "   ")
        ts = alert.timestamp.strftime("%H:%M:%S")

        separator = f"{colour}{'=' * 72}{_ANSI_RESET}"
        header = (
            f"{colour}[{symbol}] [{alert.level.value:>8s}] "
            f"{alert.alert_type.value}  |  {ts}{_ANSI_RESET}"
        )
        title_line = f"{colour}    {alert.title}{_ANSI_RESET}"
        message_line = f"    {alert.message}"
        id_line = f"    id: {alert.alert_id}"

        return "\n".join([separator, header, title_line, message_line, id_line, separator])

    def format_json_alert(self, alert: Alert) -> dict[str, Any]:
        """Serialise an alert to a JSON-compatible dictionary.

        The output is suitable for webhook payloads, logging backends,
        and persistent storage.  All values are JSON-native types.

        Args:
            alert: The ``Alert`` to serialise.

        Returns:
            Dictionary with string keys and JSON-serialisable values.
        """
        return {
            "alert_id": alert.alert_id,
            "alert_type": alert.alert_type.value,
            "level": alert.level.value,
            "title": alert.title,
            "message": alert.message,
            "timestamp": alert.timestamp.isoformat(),
            "data": alert.data,
            "acknowledged": alert.acknowledged,
            "expired": alert.expired,
        }

    # -- Sound ----------------------------------------------------------------

    def sound_alert(self, level: AlertLevel) -> None:
        """Emit an audible terminal bell for high-severity alerts.

        Outputs the ASCII BEL character (``\\a``) to stderr for CRITICAL
        and HIGH level alerts when sound is enabled in the AlertManager
        configuration.  CRITICAL alerts emit a triple bell for urgency.

        Args:
            level: The severity level of the alert.
        """
        if not self._manager.enable_sound:
            return

        if level == AlertLevel.CRITICAL:
            # Triple bell for maximum urgency
            sys.stderr.write("\a\a\a")
            sys.stderr.flush()
        elif level == AlertLevel.HIGH:
            # Single bell for attention
            sys.stderr.write("\a")
            sys.stderr.flush()
        # MEDIUM, LOW, INFO -- no sound


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__: list[str] = [
    "AlertLevel",
    "AlertType",
    "Alert",
    "AlertManager",
    "AlertRuleEngine",
    "NotificationDispatcher",
]
