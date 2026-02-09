"""
SCANIFY 0DTE SPX Scanner -- Real-Time WebSocket Streaming Handler
=================================================================

Provides eight dedicated streaming channels for the SCANIFY 0DTE system,
each with its own cadence, payload schema, and rate-limiting budget:

    1. gex_profile      -- Full GEX profile every 60 s
    2. gex_signals      -- GEX signals (event-driven)
    3. scan_signals     -- Scanner signals from all 3 scanners (event-driven)
    4. positions        -- Active position P&L updates every 5 s
    5. direction_score  -- Composite direction score every 60 s
    6. market_data      -- SPX/VIX1D/ES tick stream every 1 s
    7. alerts           -- System alerts, econ events, VIX spikes (event-driven)
    8. dashboard        -- Aggregated dashboard snapshot every 5 s

Architecture
------------
Each connected client subscribes to a subset of channels.  A dedicated
``ScanifyStreamManager`` runs background asyncio tasks for each periodic
channel and exposes ``emit_*`` methods for event-driven channels.  The
manager handles:

    - Channel subscription / unsubscription
    - Per-channel rate limiting (token-bucket)
    - Connection lifecycle (connect, heartbeat, graceful disconnect)
    - Serialisation of Pydantic / dataclass models to JSON
    - Backpressure via bounded send queues per connection
    - Clean task cancellation on shutdown

Wire Protocol
-------------
Client -> Server::

    {"action": "subscribe",   "channels": ["gex_profile", "scan_signals"]}
    {"action": "unsubscribe", "channels": ["market_data"]}
    {"action": "ping"}

Server -> Client::

    {
        "channel": "<channel_name>",
        "timestamp": "2025-03-15T14:32:10.123456+00:00",
        "sequence": 42,
        "data": { ... }
    }

Dependencies
------------
    fastapi, asyncio, json, logging, dataclasses, pydantic, jose (JWT)
    Internal: auth (JWT + tiers), models (GEXProfile, ScanSignal, etc.)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set

from fastapi import WebSocket, WebSocketDisconnect
from jose import JWTError, jwt

from src.api.auth.jwt import SECRET_KEY, ALGORITHM
from src.api.auth.tiers import (
    SubscriptionTier,
    check_tier_access,
    get_signal_delay,
    tier_can_access_realtime,
)

logger = logging.getLogger(__name__)


# =============================================================================
# 1. CHANNEL DEFINITIONS
# =============================================================================


class ScanifyChannel(str, Enum):
    """Available streaming channels."""

    GEX_PROFILE = "gex_profile"
    GEX_SIGNALS = "gex_signals"
    SCAN_SIGNALS = "scan_signals"
    POSITIONS = "positions"
    DIRECTION_SCORE = "direction_score"
    MARKET_DATA = "market_data"
    ALERTS = "alerts"
    DASHBOARD = "dashboard"


class ScanifyMessageType(str, Enum):
    """Server-to-client message types."""

    DATA = "data"
    ACK = "ack"
    ERROR = "error"
    HEARTBEAT = "heartbeat"
    WELCOME = "welcome"
    GOODBYE = "goodbye"


# Channel metadata: (interval_seconds, description, min_tier)
# interval_seconds = 0 means event-driven (no periodic task)
CHANNEL_CONFIG: Dict[ScanifyChannel, Dict[str, Any]] = {
    ScanifyChannel.GEX_PROFILE: {
        "interval_seconds": 60,
        "description": "Full GEX profile with all strike data, gamma flip, walls",
        "min_tier": SubscriptionTier.PRO,
        "rate_limit_per_minute": 2,
    },
    ScanifyChannel.GEX_SIGNALS: {
        "interval_seconds": 0,
        "description": "GEX signals (gamma flip crossover, wall approach, etc.)",
        "min_tier": SubscriptionTier.PRO,
        "rate_limit_per_minute": 30,
    },
    ScanifyChannel.SCAN_SIGNALS: {
        "interval_seconds": 0,
        "description": "Scan signals from directional, premium, and gamma scalp scanners",
        "min_tier": SubscriptionTier.PRO,
        "rate_limit_per_minute": 30,
    },
    ScanifyChannel.POSITIONS: {
        "interval_seconds": 5,
        "description": "Active position P&L updates and exit alerts",
        "min_tier": SubscriptionTier.PRO,
        "rate_limit_per_minute": 15,
    },
    ScanifyChannel.DIRECTION_SCORE: {
        "interval_seconds": 60,
        "description": "Composite direction score with five-factor breakdown",
        "min_tier": SubscriptionTier.PRO,
        "rate_limit_per_minute": 2,
    },
    ScanifyChannel.MARKET_DATA: {
        "interval_seconds": 1,
        "description": "SPX price, VIX1D, ES price, key internals",
        "min_tier": SubscriptionTier.PRO,
        "rate_limit_per_minute": 65,
    },
    ScanifyChannel.ALERTS: {
        "interval_seconds": 0,
        "description": "System alerts, economic event warnings, VIX spikes",
        "min_tier": SubscriptionTier.PRO,
        "rate_limit_per_minute": 60,
    },
    ScanifyChannel.DASHBOARD: {
        "interval_seconds": 5,
        "description": "Aggregated dashboard update (positions, P&L, key levels)",
        "min_tier": SubscriptionTier.PRO,
        "rate_limit_per_minute": 15,
    },
}

ALL_CHANNELS: Set[str] = {ch.value for ch in ScanifyChannel}


# =============================================================================
# 2. TOKEN-BUCKET RATE LIMITER (per-channel, per-connection)
# =============================================================================


class ChannelRateLimiter:
    """Simple token-bucket rate limiter for a single channel on one connection.

    Refills ``max_tokens`` tokens every 60 seconds.  Each ``consume()`` call
    removes one token.  If the bucket is empty the message is dropped and the
    method returns ``False``.
    """

    __slots__ = ("max_tokens", "tokens", "last_refill")

    def __init__(self, max_per_minute: int) -> None:
        self.max_tokens: int = max_per_minute
        self.tokens: float = float(max_per_minute)
        self.last_refill: float = time.monotonic()

    def consume(self) -> bool:
        """Attempt to consume one token.  Returns True if allowed."""
        now = time.monotonic()
        elapsed = now - self.last_refill

        # Refill proportionally
        if elapsed > 0:
            refill = elapsed * (self.max_tokens / 60.0)
            self.tokens = min(self.max_tokens, self.tokens + refill)
            self.last_refill = now

        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


# =============================================================================
# 3. CONNECTION MODEL
# =============================================================================


@dataclass
class ScanifyConnection:
    """Represents one authenticated WebSocket connection to the SCANIFY streamer."""

    connection_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    websocket: WebSocket = field(default=None)  # type: ignore[assignment]
    user_id: str = ""
    tier: SubscriptionTier = SubscriptionTier.PRO
    connected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_heartbeat: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    subscriptions: Set[str] = field(default_factory=set)
    rate_limiters: Dict[str, ChannelRateLimiter] = field(default_factory=dict)
    sequence: int = 0
    _send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _closed: bool = False

    def init_rate_limiters(self) -> None:
        """Initialise per-channel rate limiters from CHANNEL_CONFIG."""
        for ch in ScanifyChannel:
            config = CHANNEL_CONFIG[ch]
            self.rate_limiters[ch.value] = ChannelRateLimiter(
                max_per_minute=config["rate_limit_per_minute"]
            )

    def next_sequence(self) -> int:
        """Return and increment the monotonic sequence counter."""
        self.sequence += 1
        return self.sequence


# =============================================================================
# 4. DATA SERIALISATION HELPERS
# =============================================================================


def _serialize(obj: Any) -> Any:
    """Recursively serialise an object for JSON transport.

    Handles Pydantic BaseModel, dataclasses, enums, datetime, and common
    types.  Falls back to ``str(obj)`` for unknown types.
    """
    if obj is None:
        return None

    # Pydantic v2 BaseModel
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")

    # Pydantic v1 fallback
    if hasattr(obj, "dict"):
        return obj.dict()

    # dataclasses
    if hasattr(obj, "__dataclass_fields__"):
        from dataclasses import asdict
        try:
            return asdict(obj)
        except Exception:
            return {k: _serialize(getattr(obj, k)) for k in obj.__dataclass_fields__}

    # Enums
    if isinstance(obj, Enum):
        return obj.value

    # datetime
    if isinstance(obj, datetime):
        return obj.isoformat()

    # Containers
    if isinstance(obj, dict):
        return {str(k): _serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize(v) for v in obj]
    if isinstance(obj, set):
        return [_serialize(v) for v in sorted(obj, key=str)]

    # Numeric / string / bool pass through
    if isinstance(obj, (int, float, str, bool)):
        return obj

    # Fallback
    return str(obj)


def _build_message(
    channel: str,
    data: Any,
    sequence: int,
    msg_type: ScanifyMessageType = ScanifyMessageType.DATA,
) -> dict:
    """Build a wire-protocol envelope."""
    return {
        "type": msg_type.value,
        "channel": channel,
        "sequence": sequence,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": _serialize(data),
    }


# =============================================================================
# 5. SCANIFY STREAM DATA PROVIDERS (interfaces)
# =============================================================================


class ScanifyDataProvider:
    """Interface for the engine components that feed data into the streamer.

    The ``ScanifyStreamManager`` calls these methods on each tick cycle.
    Subclass or duck-type to plug in the real orchestrator, GEX engine,
    exit manager, etc.

    All methods return ``None`` when no data is available; the streamer
    skips transmission for that cycle.
    """

    async def get_gex_profile(self) -> Optional[Any]:
        """Return the latest GEXProfile or None."""
        return None

    async def get_direction_score(self) -> Optional[Any]:
        """Return the latest DirectionScore or None."""
        return None

    async def get_positions(self) -> Optional[list]:
        """Return list of active position snapshots or None."""
        return None

    async def get_market_data(self) -> Optional[dict]:
        """Return market data snapshot (SPX, VIX1D, ES, internals) or None."""
        return None

    async def get_dashboard(self) -> Optional[dict]:
        """Return aggregated dashboard snapshot or None."""
        return None


# =============================================================================
# 6. SCANIFY STREAM MANAGER
# =============================================================================


class ScanifyStreamManager:
    """Manages all SCANIFY WebSocket connections and channel streaming.

    Responsibilities
    ----------------
    - Authenticate and register connections (JWT / tier check)
    - Process subscribe / unsubscribe messages
    - Run periodic background tasks for each timer-based channel
    - Expose ``emit_*()`` methods for event-driven channels
    - Enforce per-channel rate limits
    - Heartbeat monitoring and stale connection cleanup
    - Graceful shutdown with task cancellation

    Parameters
    ----------
    data_provider : ScanifyDataProvider
        Source of live market data, GEX profiles, positions, etc.
    heartbeat_interval : int
        Seconds between heartbeat pings (default 15).
    stale_timeout : int
        Seconds of missed heartbeats before force-disconnect (default 60).
    max_connections_per_user : int
        Maximum concurrent SCANIFY WS connections per user (default 5).
    """

    def __init__(
        self,
        data_provider: Optional[ScanifyDataProvider] = None,
        heartbeat_interval: int = 15,
        stale_timeout: int = 60,
        max_connections_per_user: int = 5,
    ) -> None:
        self.data_provider: ScanifyDataProvider = data_provider or ScanifyDataProvider()
        self.heartbeat_interval: int = heartbeat_interval
        self.stale_timeout: int = stale_timeout
        self.max_connections_per_user: int = max_connections_per_user

        # Connection storage
        self._connections: Dict[str, ScanifyConnection] = {}  # conn_id -> connection
        self._user_connections: Dict[str, List[str]] = defaultdict(list)  # user_id -> [conn_id]

        # Channel subscriber index: channel_name -> set of conn_ids
        self._channel_subscribers: Dict[str, Set[str]] = {
            ch.value: set() for ch in ScanifyChannel
        }

        # Background tasks
        self._tasks: List[asyncio.Task] = []
        self._running: bool = False
        self._shutdown_event: asyncio.Event = asyncio.Event()

        # Event callbacks (external code can register listeners)
        self._on_connect_callbacks: List[Callable] = []
        self._on_disconnect_callbacks: List[Callable] = []

    # -----------------------------------------------------------------
    # Properties
    # -----------------------------------------------------------------

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    @property
    def unique_user_count(self) -> int:
        return len(self._user_connections)

    # -----------------------------------------------------------------
    # a) Connection lifecycle
    # -----------------------------------------------------------------

    async def connect(
        self,
        websocket: WebSocket,
        token: str,
    ) -> ScanifyConnection:
        """Authenticate, accept, and register a new WebSocket connection.

        Raises
        ------
        WebSocketDisconnect
            When authentication fails or connection limit is reached.
        """
        # --- JWT verification ---
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id: str = payload.get("sub", "")
            tier_str: str = payload.get("tier", "pro")
            tier = SubscriptionTier(tier_str)
        except (JWTError, ValueError) as exc:
            await websocket.accept()
            await websocket.send_json({
                "type": ScanifyMessageType.ERROR.value,
                "channel": "_system",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": {"error": "authentication_failed", "detail": str(exc)},
            })
            await websocket.close(code=4001, reason="Invalid or expired token")
            raise WebSocketDisconnect(code=4001, reason="Invalid token")

        # --- Tier check: WebSocket requires PRO+ ---
        if not check_tier_access(tier, "websocket"):
            await websocket.accept()
            await websocket.send_json({
                "type": ScanifyMessageType.ERROR.value,
                "channel": "_system",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": {
                    "error": "insufficient_tier",
                    "detail": "SCANIFY WebSocket streaming requires PRO tier or higher",
                    "current_tier": tier.value,
                    "required_tier": "pro",
                },
            })
            await websocket.close(code=4003, reason="PRO tier required")
            raise WebSocketDisconnect(code=4003, reason="Insufficient tier")

        # --- Connection limit ---
        user_conn_ids = self._user_connections.get(user_id, [])
        if len(user_conn_ids) >= self.max_connections_per_user:
            await websocket.accept()
            await websocket.send_json({
                "type": ScanifyMessageType.ERROR.value,
                "channel": "_system",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": {
                    "error": "connection_limit",
                    "detail": f"Maximum {self.max_connections_per_user} concurrent connections",
                    "current": len(user_conn_ids),
                },
            })
            await websocket.close(code=4029, reason="Connection limit reached")
            raise WebSocketDisconnect(code=4029, reason="Connection limit")

        # --- Accept ---
        await websocket.accept()

        # --- Create connection ---
        conn = ScanifyConnection(
            websocket=websocket,
            user_id=user_id,
            tier=tier,
        )
        conn.init_rate_limiters()

        self._connections[conn.connection_id] = conn
        self._user_connections[user_id].append(conn.connection_id)

        # --- Welcome message ---
        await self._send(conn, {
            "type": ScanifyMessageType.WELCOME.value,
            "channel": "_system",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {
                "connection_id": conn.connection_id,
                "user_id": user_id,
                "tier": tier.value,
                "available_channels": [
                    {
                        "name": ch.value,
                        "description": CHANNEL_CONFIG[ch]["description"],
                        "interval_seconds": CHANNEL_CONFIG[ch]["interval_seconds"],
                    }
                    for ch in ScanifyChannel
                ],
                "heartbeat_interval": self.heartbeat_interval,
            },
        })

        # --- Notify callbacks ---
        for cb in self._on_connect_callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(conn)
                else:
                    cb(conn)
            except Exception:
                logger.exception("Error in on_connect callback")

        logger.info(
            "SCANIFY WS connected: user=%s tier=%s conn_id=%s",
            user_id, tier.value, conn.connection_id,
        )
        return conn

    async def disconnect(self, conn: ScanifyConnection) -> None:
        """Cleanly remove a connection from all tracking structures."""
        if conn._closed:
            return
        conn._closed = True

        conn_id = conn.connection_id

        # Remove from channel subscribers
        for channel_set in self._channel_subscribers.values():
            channel_set.discard(conn_id)

        # Remove from user connections
        user_conns = self._user_connections.get(conn.user_id, [])
        if conn_id in user_conns:
            user_conns.remove(conn_id)
        if not user_conns and conn.user_id in self._user_connections:
            del self._user_connections[conn.user_id]

        # Remove from global map
        self._connections.pop(conn_id, None)

        # Close the WebSocket
        try:
            await conn.websocket.close(code=1000, reason="Disconnected")
        except Exception:
            pass

        # Notify callbacks
        for cb in self._on_disconnect_callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(conn)
                else:
                    cb(conn)
            except Exception:
                logger.exception("Error in on_disconnect callback")

        logger.info(
            "SCANIFY WS disconnected: user=%s conn_id=%s",
            conn.user_id, conn_id,
        )

    # -----------------------------------------------------------------
    # b) Message sending
    # -----------------------------------------------------------------

    async def _send(self, conn: ScanifyConnection, message: dict) -> bool:
        """Send a JSON message to a single connection, thread-safe.

        Returns True if the send succeeded, False otherwise.
        """
        if conn._closed:
            return False

        try:
            async with conn._send_lock:
                await asyncio.wait_for(
                    conn.websocket.send_json(message),
                    timeout=5.0,
                )
            return True
        except asyncio.TimeoutError:
            logger.warning(
                "Send timeout for conn=%s, scheduling disconnect",
                conn.connection_id,
            )
            asyncio.create_task(self.disconnect(conn))
            return False
        except Exception:
            asyncio.create_task(self.disconnect(conn))
            return False

    async def _send_to_channel(
        self,
        channel: str,
        data: Any,
    ) -> int:
        """Broadcast data to all subscribers of a channel, applying rate limits.

        Returns the number of connections that received the message.
        """
        subscriber_ids = self._channel_subscribers.get(channel, set())
        if not subscriber_ids:
            return 0

        sent_count = 0
        for conn_id in list(subscriber_ids):
            conn = self._connections.get(conn_id)
            if conn is None or conn._closed:
                subscriber_ids.discard(conn_id)
                continue

            # Rate limit check
            limiter = conn.rate_limiters.get(channel)
            if limiter and not limiter.consume():
                continue

            # Apply tier-based signal delay (only relevant for non-realtime tiers)
            delay = get_signal_delay(conn.tier)
            if delay > 0:
                # Non-realtime tiers should not receive SCANIFY streams at all;
                # they are blocked at connect time.  This is a defence-in-depth check.
                continue

            message = _build_message(
                channel=channel,
                data=data,
                sequence=conn.next_sequence(),
            )

            if await self._send(conn, message):
                sent_count += 1

        return sent_count

    # -----------------------------------------------------------------
    # c) Subscription management
    # -----------------------------------------------------------------

    def _subscribe(self, conn: ScanifyConnection, channels: List[str]) -> dict:
        """Subscribe a connection to the requested channels.

        Returns a result dict with successes and failures.
        """
        subscribed = []
        errors = []

        for ch_name in channels:
            ch_name = ch_name.strip().lower()

            if ch_name not in ALL_CHANNELS:
                errors.append({"channel": ch_name, "error": "unknown_channel"})
                continue

            channel_enum = ScanifyChannel(ch_name)
            config = CHANNEL_CONFIG[channel_enum]

            # Tier check for individual channels
            min_tier = config.get("min_tier", SubscriptionTier.PRO)
            tier_order = [
                SubscriptionTier.FREE,
                SubscriptionTier.BASIC,
                SubscriptionTier.PRO,
                SubscriptionTier.ELITE,
                SubscriptionTier.ADMIN,
            ]
            if tier_order.index(conn.tier) < tier_order.index(min_tier):
                errors.append({
                    "channel": ch_name,
                    "error": "insufficient_tier",
                    "required": min_tier.value,
                })
                continue

            conn.subscriptions.add(ch_name)
            self._channel_subscribers[ch_name].add(conn.connection_id)
            subscribed.append(ch_name)

        return {
            "subscribed": subscribed,
            "errors": errors,
            "active_subscriptions": sorted(conn.subscriptions),
        }

    def _unsubscribe(self, conn: ScanifyConnection, channels: List[str]) -> dict:
        """Unsubscribe a connection from the requested channels."""
        unsubscribed = []

        for ch_name in channels:
            ch_name = ch_name.strip().lower()
            if ch_name in conn.subscriptions:
                conn.subscriptions.discard(ch_name)
                self._channel_subscribers.get(ch_name, set()).discard(conn.connection_id)
                unsubscribed.append(ch_name)

        return {
            "unsubscribed": unsubscribed,
            "active_subscriptions": sorted(conn.subscriptions),
        }

    # -----------------------------------------------------------------
    # d) Inbound message handling
    # -----------------------------------------------------------------

    async def handle_message(
        self,
        conn: ScanifyConnection,
        raw_message: str,
    ) -> None:
        """Parse and dispatch a client message."""
        try:
            msg = json.loads(raw_message)
        except json.JSONDecodeError:
            await self._send(conn, _build_message(
                channel="_system",
                data={"error": "invalid_json", "detail": "Message is not valid JSON"},
                sequence=conn.next_sequence(),
                msg_type=ScanifyMessageType.ERROR,
            ))
            return

        action = msg.get("action", "").strip().lower()

        if action == "subscribe":
            channels = msg.get("channels", [])
            # Also support the flat {"subscribe": [...]} shorthand
            if not channels:
                channels = msg.get("subscribe", [])
            if not isinstance(channels, list):
                channels = [channels]

            result = self._subscribe(conn, channels)
            await self._send(conn, _build_message(
                channel="_system",
                data={"action": "subscribe", **result},
                sequence=conn.next_sequence(),
                msg_type=ScanifyMessageType.ACK,
            ))

        elif action == "unsubscribe":
            channels = msg.get("channels", [])
            if not channels:
                channels = msg.get("unsubscribe", [])
            if not isinstance(channels, list):
                channels = [channels]

            result = self._unsubscribe(conn, channels)
            await self._send(conn, _build_message(
                channel="_system",
                data={"action": "unsubscribe", **result},
                sequence=conn.next_sequence(),
                msg_type=ScanifyMessageType.ACK,
            ))

        elif action in ("ping", "heartbeat"):
            conn.last_heartbeat = datetime.now(timezone.utc)
            await self._send(conn, _build_message(
                channel="_system",
                data={"pong": True},
                sequence=conn.next_sequence(),
                msg_type=ScanifyMessageType.HEARTBEAT,
            ))

        else:
            # Check for {"subscribe": [...]} without "action" key
            if "subscribe" in msg:
                channels = msg["subscribe"]
                if not isinstance(channels, list):
                    channels = [channels]
                result = self._subscribe(conn, channels)
                await self._send(conn, _build_message(
                    channel="_system",
                    data={"action": "subscribe", **result},
                    sequence=conn.next_sequence(),
                    msg_type=ScanifyMessageType.ACK,
                ))
            elif "unsubscribe" in msg:
                channels = msg["unsubscribe"]
                if not isinstance(channels, list):
                    channels = [channels]
                result = self._unsubscribe(conn, channels)
                await self._send(conn, _build_message(
                    channel="_system",
                    data={"action": "unsubscribe", **result},
                    sequence=conn.next_sequence(),
                    msg_type=ScanifyMessageType.ACK,
                ))
            else:
                await self._send(conn, _build_message(
                    channel="_system",
                    data={
                        "error": "unknown_action",
                        "detail": f"Unrecognised action: {action!r}",
                        "valid_actions": ["subscribe", "unsubscribe", "ping"],
                    },
                    sequence=conn.next_sequence(),
                    msg_type=ScanifyMessageType.ERROR,
                ))

    # -----------------------------------------------------------------
    # e) Event-driven emitters (called from engine code)
    # -----------------------------------------------------------------

    async def emit_gex_signal(self, signal: Any) -> int:
        """Push a GEX signal to all ``gex_signals`` subscribers.

        Parameters
        ----------
        signal : GEXSignal or dict
            The signal payload.

        Returns
        -------
        int
            Number of connections reached.
        """
        return await self._send_to_channel(ScanifyChannel.GEX_SIGNALS.value, signal)

    async def emit_scan_signal(self, signal: Any) -> int:
        """Push a scan signal to all ``scan_signals`` subscribers.

        Parameters
        ----------
        signal : ScanSignal or dict
            The signal payload.

        Returns
        -------
        int
            Number of connections reached.
        """
        return await self._send_to_channel(ScanifyChannel.SCAN_SIGNALS.value, signal)

    async def emit_alert(self, alert: Any) -> int:
        """Push an alert to all ``alerts`` subscribers.

        Parameters
        ----------
        alert : dict
            Alert payload with keys like ``alert_type``, ``severity``,
            ``message``, ``details``.

        Returns
        -------
        int
            Number of connections reached.
        """
        return await self._send_to_channel(ScanifyChannel.ALERTS.value, alert)

    async def emit_position_update(self, positions: Any) -> int:
        """Push position data outside the periodic cycle (e.g. exit alert).

        Parameters
        ----------
        positions : list or dict
            Position data.

        Returns
        -------
        int
            Number of connections reached.
        """
        return await self._send_to_channel(ScanifyChannel.POSITIONS.value, positions)

    # -----------------------------------------------------------------
    # f) Periodic background tasks
    # -----------------------------------------------------------------

    async def _periodic_gex_profile(self) -> None:
        """Fetch and broadcast GEX profile every 60 seconds."""
        interval = CHANNEL_CONFIG[ScanifyChannel.GEX_PROFILE]["interval_seconds"]
        while self._running:
            try:
                data = await self.data_provider.get_gex_profile()
                if data is not None:
                    await self._send_to_channel(
                        ScanifyChannel.GEX_PROFILE.value, data,
                    )
            except Exception:
                logger.exception("Error in _periodic_gex_profile")
            await asyncio.sleep(interval)

    async def _periodic_positions(self) -> None:
        """Fetch and broadcast position updates every 5 seconds."""
        interval = CHANNEL_CONFIG[ScanifyChannel.POSITIONS]["interval_seconds"]
        while self._running:
            try:
                data = await self.data_provider.get_positions()
                if data is not None:
                    await self._send_to_channel(
                        ScanifyChannel.POSITIONS.value, data,
                    )
            except Exception:
                logger.exception("Error in _periodic_positions")
            await asyncio.sleep(interval)

    async def _periodic_direction_score(self) -> None:
        """Fetch and broadcast direction score every 60 seconds."""
        interval = CHANNEL_CONFIG[ScanifyChannel.DIRECTION_SCORE]["interval_seconds"]
        while self._running:
            try:
                data = await self.data_provider.get_direction_score()
                if data is not None:
                    await self._send_to_channel(
                        ScanifyChannel.DIRECTION_SCORE.value, data,
                    )
            except Exception:
                logger.exception("Error in _periodic_direction_score")
            await asyncio.sleep(interval)

    async def _periodic_market_data(self) -> None:
        """Fetch and broadcast market data every 1 second."""
        interval = CHANNEL_CONFIG[ScanifyChannel.MARKET_DATA]["interval_seconds"]
        while self._running:
            try:
                data = await self.data_provider.get_market_data()
                if data is not None:
                    await self._send_to_channel(
                        ScanifyChannel.MARKET_DATA.value, data,
                    )
            except Exception:
                logger.exception("Error in _periodic_market_data")
            await asyncio.sleep(interval)

    async def _periodic_dashboard(self) -> None:
        """Fetch and broadcast dashboard snapshot every 5 seconds."""
        interval = CHANNEL_CONFIG[ScanifyChannel.DASHBOARD]["interval_seconds"]
        while self._running:
            try:
                data = await self.data_provider.get_dashboard()
                if data is not None:
                    await self._send_to_channel(
                        ScanifyChannel.DASHBOARD.value, data,
                    )
            except Exception:
                logger.exception("Error in _periodic_dashboard")
            await asyncio.sleep(interval)

    async def _heartbeat_loop(self) -> None:
        """Send heartbeats and prune stale connections."""
        while self._running:
            now = datetime.now(timezone.utc)

            for conn in list(self._connections.values()):
                if conn._closed:
                    continue

                elapsed = (now - conn.last_heartbeat).total_seconds()

                # Prune stale connections
                if elapsed > self.stale_timeout:
                    logger.warning(
                        "Stale connection detected: conn=%s user=%s elapsed=%.0fs",
                        conn.connection_id, conn.user_id, elapsed,
                    )
                    asyncio.create_task(self.disconnect(conn))
                    continue

                # Send heartbeat ping
                await self._send(conn, {
                    "type": ScanifyMessageType.HEARTBEAT.value,
                    "channel": "_system",
                    "timestamp": now.isoformat(),
                    "data": {
                        "server_time": now.isoformat(),
                        "connection_uptime_seconds": (
                            now - conn.connected_at
                        ).total_seconds(),
                        "subscriptions": sorted(conn.subscriptions),
                    },
                })

            await asyncio.sleep(self.heartbeat_interval)

    # -----------------------------------------------------------------
    # g) Lifecycle management
    # -----------------------------------------------------------------

    async def start(self) -> None:
        """Start all background streaming tasks.

        Safe to call multiple times; will not double-start.
        """
        if self._running:
            logger.warning("ScanifyStreamManager.start() called but already running")
            return

        self._running = True
        self._shutdown_event.clear()

        task_coros = [
            self._periodic_gex_profile(),
            self._periodic_positions(),
            self._periodic_direction_score(),
            self._periodic_market_data(),
            self._periodic_dashboard(),
            self._heartbeat_loop(),
        ]

        for coro in task_coros:
            task = asyncio.create_task(coro)
            self._tasks.append(task)

        logger.info(
            "ScanifyStreamManager started with %d background tasks",
            len(self._tasks),
        )

    async def shutdown(self) -> None:
        """Gracefully stop all background tasks and disconnect all clients."""
        if not self._running:
            return

        logger.info("ScanifyStreamManager shutting down...")
        self._running = False
        self._shutdown_event.set()

        # Cancel background tasks
        for task in self._tasks:
            task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        # Disconnect all connections
        for conn in list(self._connections.values()):
            try:
                await self._send(conn, {
                    "type": ScanifyMessageType.GOODBYE.value,
                    "channel": "_system",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "data": {"reason": "server_shutdown"},
                })
            except Exception:
                pass
            await self.disconnect(conn)

        logger.info("ScanifyStreamManager shutdown complete")

    def set_data_provider(self, provider: ScanifyDataProvider) -> None:
        """Hot-swap the data provider (e.g. when the orchestrator initialises)."""
        self.data_provider = provider

    def on_connect(self, callback: Callable) -> None:
        """Register a callback invoked when a new connection is established."""
        self._on_connect_callbacks.append(callback)

    def on_disconnect(self, callback: Callable) -> None:
        """Register a callback invoked when a connection is removed."""
        self._on_disconnect_callbacks.append(callback)

    # -----------------------------------------------------------------
    # h) Statistics
    # -----------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return current streaming statistics."""
        channel_counts = {
            ch: len(subs) for ch, subs in self._channel_subscribers.items()
        }
        tier_counts: Dict[str, int] = defaultdict(int)
        for conn in self._connections.values():
            tier_counts[conn.tier.value] += 1

        return {
            "total_connections": self.connection_count,
            "unique_users": self.unique_user_count,
            "by_tier": dict(tier_counts),
            "channel_subscribers": channel_counts,
            "running": self._running,
            "background_tasks": len(self._tasks),
        }


# =============================================================================
# 7. GLOBAL INSTANCE + FASTAPI ENDPOINT
# =============================================================================

# Singleton manager -- imported and used by the main app module
scanify_stream_manager = ScanifyStreamManager()


async def scanify_websocket_endpoint(
    websocket: WebSocket,
    token: str,
) -> None:
    """FastAPI WebSocket endpoint for the SCANIFY 0DTE streaming system.

    Usage::

        ws://localhost:8000/ws/scanify?token=<jwt_token>

    After connection, send::

        {"subscribe": ["gex_profile", "scan_signals", "market_data"]}

    To unsubscribe::

        {"unsubscribe": ["market_data"]}

    Heartbeat (keep alive)::

        {"action": "ping"}

    Parameters
    ----------
    websocket : WebSocket
        The FastAPI WebSocket instance.
    token : str
        JWT access token passed as a query parameter.
    """
    conn: Optional[ScanifyConnection] = None

    try:
        conn = await scanify_stream_manager.connect(websocket, token)
    except WebSocketDisconnect:
        return
    except Exception:
        logger.exception("Unexpected error during SCANIFY WS connect")
        try:
            await websocket.close(code=1011, reason="Internal error")
        except Exception:
            pass
        return

    try:
        while True:
            raw = await websocket.receive_text()
            await scanify_stream_manager.handle_message(conn, raw)
    except WebSocketDisconnect:
        logger.debug("Client disconnected: conn=%s", conn.connection_id)
    except asyncio.CancelledError:
        logger.debug("Connection cancelled: conn=%s", conn.connection_id)
    except Exception:
        logger.exception(
            "Error in SCANIFY WS message loop: conn=%s", conn.connection_id,
        )
    finally:
        if conn is not None:
            await scanify_stream_manager.disconnect(conn)
