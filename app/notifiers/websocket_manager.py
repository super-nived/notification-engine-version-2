import asyncio
import logging
import threading

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages active WebSocket connections for in-app
    notifications."""

    def __init__(self):
        self._connections: list[WebSocket] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()

    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        """Store the main event loop for cross-thread calls."""
        self._loop = loop

    async def connect(self, ws: WebSocket):
        await ws.accept()
        with self._lock:
            self._connections.append(ws)
            if self._loop is None:
                self._loop = asyncio.get_running_loop()
            count = len(self._connections)
        logger.info("WebSocket connected (%d active)", count)

    def disconnect(self, ws: WebSocket):
        with self._lock:
            if ws in self._connections:
                self._connections.remove(ws)
            count = len(self._connections)
        logger.info("WebSocket disconnected (%d active)", count)

    def broadcast(self, event: dict):
        """Broadcast event to all connected clients.
        Safe to call from background threads."""
        with self._lock:
            snapshot = list(self._connections)
            loop = self._loop

        if not snapshot:
            logger.warning("No WebSocket clients connected")
            return

        if loop is None or loop.is_closed():
            logger.warning("Event loop not available")
            return

        logger.info(
            "Broadcasting to %d client(s): %s",
            len(snapshot),
            event.get("message", "")[:80],
        )

        dead: list[WebSocket] = []
        for ws in snapshot:
            try:
                future = asyncio.run_coroutine_threadsafe(
                    ws.send_json(event), loop
                )
                future.result(timeout=5)
                logger.info("WebSocket message sent OK")
            except Exception as exc:
                logger.warning("WebSocket send failed: %s", exc)
                dead.append(ws)

        for ws in dead:
            self.disconnect(ws)


ws_manager = WebSocketManager()
