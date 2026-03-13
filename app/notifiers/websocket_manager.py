import json
import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages active WebSocket connections for in-app
    notifications."""

    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.append(ws)
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
        Called from sync threads — schedules async sends."""
        import asyncio

        dead: list[WebSocket] = []
        for ws in self._connections:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        ws.send_json(event), loop
                    )
                else:
                    asyncio.run(ws.send_json(event))
            except Exception:
                dead.append(ws)

        for ws in dead:
            self.disconnect(ws)


ws_manager = WebSocketManager()
