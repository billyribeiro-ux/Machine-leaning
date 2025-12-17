"""
Scanify WebSocket Handlers

Real-time signal streaming via WebSocket connections.
Tier-based access with connection limits.
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Optional, Set
from dataclasses import dataclass, field
from enum import Enum

from fastapi import WebSocket, WebSocketDisconnect, HTTPException, status
from jose import JWTError, jwt

from src.api.auth.jwt import SECRET_KEY, ALGORITHM
from src.api.auth.tiers import (
    SubscriptionTier,
    check_tier_access,
    check_scanner_access,
    get_signal_delay,
)


class MessageType(str, Enum):
    """WebSocket message types"""
    SIGNAL = "signal"
    ALERT = "alert"
    STATUS = "status"
    HEARTBEAT = "heartbeat"
    ERROR = "error"
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    ACK = "ack"


@dataclass
class Connection:
    """Represents a WebSocket connection"""
    websocket: WebSocket
    user_id: str
    tier: SubscriptionTier
    connected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    subscriptions: Set[str] = field(default_factory=set)  # Scanner types to receive
    symbols: Set[str] = field(default_factory=set)  # Symbols to filter
    last_heartbeat: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class WebSocketManager:
    """
    Manages WebSocket connections with tier-based access control.

    Features:
    - Connection pooling per user
    - Subscription management (scanners, symbols)
    - Heartbeat monitoring
    - Graceful disconnection
    """

    def __init__(self):
        self.connections: dict[str, list[Connection]] = {}  # user_id -> connections
        self.all_connections: list[Connection] = []
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._scanner_engine = None

    def set_scanner_engine(self, engine):
        """Set scanner engine for alert callbacks"""
        self._scanner_engine = engine
        if engine and hasattr(engine, "add_alert_callback"):
            engine.add_alert_callback(self._broadcast_alert)

    async def connect(
        self,
        websocket: WebSocket,
        token: str,
    ) -> Connection:
        """
        Authenticate and establish WebSocket connection.

        Validates JWT token and checks tier access.
        """
        # Verify token
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id = payload.get("sub")
            tier_str = payload.get("tier", "free")
            tier = SubscriptionTier(tier_str)
        except JWTError:
            await websocket.close(code=4001, reason="Invalid token")
            raise HTTPException(status_code=401, detail="Invalid token")

        # Check WebSocket access
        if not check_tier_access(tier, "websocket"):
            await websocket.close(code=4003, reason="WebSocket requires PRO tier or higher")
            raise HTTPException(
                status_code=403,
                detail="WebSocket access requires PRO tier or higher",
            )

        # Check connection limits
        user_connections = self.connections.get(user_id, [])
        max_connections = 3 if tier == SubscriptionTier.PRO else 10
        if len(user_connections) >= max_connections:
            await websocket.close(code=4029, reason="Connection limit reached")
            raise HTTPException(
                status_code=429,
                detail=f"Maximum {max_connections} connections allowed",
            )

        # Accept connection
        await websocket.accept()

        # Create connection object
        connection = Connection(
            websocket=websocket,
            user_id=user_id,
            tier=tier,
        )

        # Store connection
        if user_id not in self.connections:
            self.connections[user_id] = []
        self.connections[user_id].append(connection)
        self.all_connections.append(connection)

        # Send welcome message
        await self._send(connection, {
            "type": MessageType.ACK,
            "message": "Connected to Scanify",
            "user_id": user_id,
            "tier": tier.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return connection

    async def disconnect(self, connection: Connection):
        """Remove a connection"""
        user_id = connection.user_id

        if user_id in self.connections:
            self.connections[user_id] = [
                c for c in self.connections[user_id]
                if c.websocket != connection.websocket
            ]
            if not self.connections[user_id]:
                del self.connections[user_id]

        if connection in self.all_connections:
            self.all_connections.remove(connection)

    async def _send(self, connection: Connection, data: dict):
        """Send data to a single connection"""
        try:
            await connection.websocket.send_json(data)
        except Exception:
            await self.disconnect(connection)

    async def broadcast_signal(self, signal: dict):
        """
        Broadcast a signal to all subscribed connections.

        Respects tier-based filtering and delays.
        """
        scanner_type = signal.get("scanner_type", "").lower()

        for connection in self.all_connections.copy():
            # Check scanner access
            if not check_scanner_access(connection.tier, scanner_type):
                continue

            # Check subscription filter
            if connection.subscriptions and scanner_type not in connection.subscriptions:
                continue

            # Check symbol filter
            symbol = signal.get("symbol", "").upper()
            if connection.symbols and symbol not in connection.symbols:
                continue

            # Apply delay if needed
            delay = get_signal_delay(connection.tier)
            if delay > 0:
                # For delayed tiers, we'd queue this for later delivery
                # For simplicity, we skip non-realtime here
                continue

            # Send signal
            await self._send(connection, {
                "type": MessageType.SIGNAL,
                "data": signal,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    async def _broadcast_alert(self, alert):
        """Callback for scanner engine alerts"""
        alert_data = {
            "alert_id": alert.alert_id,
            "symbol": alert.scan_result.symbol if alert.scan_result else None,
            "scanner_type": alert.scan_result.scanner_type if alert.scan_result else None,
            "direction": alert.scan_result.direction.value if alert.scan_result and hasattr(alert.scan_result.direction, "value") else None,
            "confidence": alert.scan_result.confidence if alert.scan_result else None,
            "message": alert.message,
            "priority": alert.priority.value if hasattr(alert.priority, "value") else str(alert.priority),
            "created_at": alert.created_at.isoformat() if alert.created_at else None,
        }

        for connection in self.all_connections.copy():
            scanner_type = alert_data.get("scanner_type", "").lower()
            if not check_scanner_access(connection.tier, scanner_type):
                continue

            await self._send(connection, {
                "type": MessageType.ALERT,
                "data": alert_data,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    async def broadcast_status(self, status_data: dict):
        """Broadcast system status to all connections"""
        for connection in self.all_connections.copy():
            await self._send(connection, {
                "type": MessageType.STATUS,
                "data": status_data,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    async def handle_message(self, connection: Connection, message: str):
        """Handle incoming WebSocket message"""
        try:
            data = json.loads(message)
            msg_type = data.get("type", "").lower()

            if msg_type == "subscribe":
                # Subscribe to scanners/symbols
                scanners = data.get("scanners", [])
                symbols = data.get("symbols", [])

                # Validate scanner access
                for scanner in scanners:
                    if not check_scanner_access(connection.tier, scanner):
                        await self._send(connection, {
                            "type": MessageType.ERROR,
                            "message": f"No access to {scanner} scanner",
                        })
                        return

                connection.subscriptions.update(s.lower() for s in scanners)
                connection.symbols.update(s.upper() for s in symbols)

                await self._send(connection, {
                    "type": MessageType.ACK,
                    "message": "Subscribed",
                    "subscriptions": list(connection.subscriptions),
                    "symbols": list(connection.symbols),
                })

            elif msg_type == "unsubscribe":
                scanners = data.get("scanners", [])
                symbols = data.get("symbols", [])

                connection.subscriptions -= set(s.lower() for s in scanners)
                connection.symbols -= set(s.upper() for s in symbols)

                await self._send(connection, {
                    "type": MessageType.ACK,
                    "message": "Unsubscribed",
                    "subscriptions": list(connection.subscriptions),
                    "symbols": list(connection.symbols),
                })

            elif msg_type == "heartbeat" or msg_type == "ping":
                connection.last_heartbeat = datetime.now(timezone.utc)
                await self._send(connection, {
                    "type": MessageType.HEARTBEAT,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

            else:
                await self._send(connection, {
                    "type": MessageType.ERROR,
                    "message": f"Unknown message type: {msg_type}",
                })

        except json.JSONDecodeError:
            await self._send(connection, {
                "type": MessageType.ERROR,
                "message": "Invalid JSON",
            })

    async def start_heartbeat(self, interval: int = 30):
        """Start heartbeat monitoring"""
        async def heartbeat_loop():
            while True:
                await asyncio.sleep(interval)
                now = datetime.now(timezone.utc)

                for connection in self.all_connections.copy():
                    # Check for stale connections
                    elapsed = (now - connection.last_heartbeat).total_seconds()
                    if elapsed > interval * 3:
                        await self.disconnect(connection)
                        continue

                    # Send heartbeat
                    await self._send(connection, {
                        "type": MessageType.HEARTBEAT,
                        "timestamp": now.isoformat(),
                    })

        self._heartbeat_task = asyncio.create_task(heartbeat_loop())

    def get_stats(self) -> dict:
        """Get connection statistics"""
        tier_counts = {}
        for connection in self.all_connections:
            tier = connection.tier.value
            tier_counts[tier] = tier_counts.get(tier, 0) + 1

        return {
            "total_connections": len(self.all_connections),
            "unique_users": len(self.connections),
            "by_tier": tier_counts,
        }


# Global manager instance
manager = WebSocketManager()


async def websocket_endpoint(websocket: WebSocket, token: str):
    """
    WebSocket endpoint handler.

    Usage:
        ws://localhost:8000/ws/signals?token=<jwt_token>
    """
    connection = await manager.connect(websocket, token)

    try:
        while True:
            message = await websocket.receive_text()
            await manager.handle_message(connection, message)
    except WebSocketDisconnect:
        await manager.disconnect(connection)
    except Exception:
        await manager.disconnect(connection)
