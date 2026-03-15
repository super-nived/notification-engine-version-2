import asyncio
import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages active WebSocket connections for in-app
    notifications."""

    def __init__(self):
        self._connections: list[WebSocket] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        """Store the main event loop for cross-thread calls."""
        self._loop = loop

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.append(ws)
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        logger.info(
            "WebSocket connected (%d active)",
            len(self._connections),
        )

    def disconnect(self, ws: WebSocket):
        if ws in self._connections:
            self._connections.remove(ws)
        logger.info(
            "WebSocket disconnected (%d active)",
            len(self._connections),
        )

    def broadcast(self, event: dict):
        """Broadcast event to all connected clients.
        Safe to call from background threads."""
        if not self._connections:
            logger.warning("No WebSocket clients connected")
            return

        if self._loop is None or self._loop.is_closed():
            logger.warning("Event loop not available")
            return

        logger.info(
            "Broadcasting to %d client(s): %s",
            len(self._connections),
            event.get("message", "")[:80],
        )

        dead: list[WebSocket] = []
        for ws in list(self._connections):
            try:
                future = asyncio.run_coroutine_threadsafe(
                    ws.send_json(event), self._loop
                )
                future.result(timeout=5)
                logger.info("WebSocket message sent OK")
            except Exception as exc:
                logger.warning("WebSocket send failed: %s", exc)
                dead.append(ws)

        for ws in dead:
            self.disconnect(ws)


ws_manager = WebSocketManager()
