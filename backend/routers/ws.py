"""
WebSocket Telemetry and Live Stream Router.
Broadcasts real-time job progress, transmission updates, and system log events to connected clients.
"""

import asyncio
import json
from typing import Set, Dict, Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.job_queue import job_worker
from logger import get_logger

logger = get_logger("WebSocketManager")
router = APIRouter(tags=["Realtime"])


class ConnectionManager:
    """Manages active client WebSocket connections and broadcasts async messages."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.debug(f"Client connected to WebSocket. Total active: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        logger.debug(f"Client disconnected. Total active: {len(self.active_connections)}")

    async def broadcast_json(self, data: Dict[str, Any]):
        """Asynchronously dispatches a JSON payload to all active WebSocket clients."""
        dead_connections = set()
        message_str = json.dumps(data)
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message_str)
            except Exception:
                dead_connections.add(connection)
        for dead in dead_connections:
            self.active_connections.discard(dead)

    def dispatch_from_thread(self, data: Dict[str, Any]):
        """Dispatches an event from a synchronous worker thread into the async event loop."""
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self.broadcast_json(data), self._loop)


ws_manager = ConnectionManager()

# Bridge job_worker broadcast listener into WebSocket manager
job_worker.register_listener(ws_manager.dispatch_from_thread)


@router.websocket("/ws")
async def websocket_telemetry_endpoint(websocket: WebSocket):
    """Real-time bidirectional WebSocket stream for progress updates and logs."""
    # Capture current running event loop for thread-safe cross-dispatch
    ws_manager.set_loop(asyncio.get_running_loop())
    await ws_manager.connect(websocket)
    try:
        # Send initial connection acknowledgment
        active_job = job_worker.get_active_job()
        await websocket.send_json({
            "type": "connection_established",
            "active_job": active_job
        })
        while True:
            # Keep socket alive and receive client messages (e.g. heartbeat ping)
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.debug(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)

