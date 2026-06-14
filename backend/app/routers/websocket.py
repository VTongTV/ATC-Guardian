"""WebSocket router — real-time radar data streaming to frontend.

Provides the /ws/radar endpoint that pushes RadarSnapshot JSON
to all connected clients every simulation tick, replacing the
need for HTTP polling.
"""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from shared.models import RadarSnapshot

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts radar snapshots.

    Maintains a set of connected clients and provides methods to
    add/remove connections and broadcast data to all clients.
    """

    def __init__(self) -> None:
        """Initialize with an empty set of active connections."""
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection.

        Args:
            websocket: The incoming WebSocket connection to accept.
        """
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("WebSocket client connected. Total: %d", len(self.active_connections))

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection from the active set.

        Args:
            websocket: The WebSocket connection to remove.
        """
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info("WebSocket client disconnected. Total: %d", len(self.active_connections))

    async def broadcast_snapshot(self, snapshot: RadarSnapshot) -> None:
        """Serialize and broadcast a radar snapshot to all connected clients.

        If a client connection fails during broadcast, it is removed
        from the active set automatically.

        Args:
            snapshot: The RadarSnapshot to broadcast as JSON.
        """
        if not self.active_connections:
            return

        payload = snapshot.model_dump_json()
        disconnected: list[WebSocket] = []

        for connection in self.active_connections:
            try:
                await connection.send_text(payload)
            except Exception:
                disconnected.append(connection)

        for connection in disconnected:
            self.disconnect(connection)


manager = ConnectionManager()


@router.websocket("/ws/radar")
async def websocket_radar(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time radar data streaming.

    Clients connect and receive a continuous stream of RadarSnapshot
    JSON messages, one per simulation tick (every 4 seconds by default).

    The server pushes data — clients do not need to send messages.
    If the connection drops, the server cleans up automatically.
    """
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive — client can send pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
