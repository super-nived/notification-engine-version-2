"""In-App (WebSocket) Notifier — standalone plugin.

Broadcasts events to all connected WebSocket clients.
"""

import logging

from app.core.base_notifier import BaseNotifier

logger = logging.getLogger(__name__)

_websocket_manager = None


def set_websocket_manager(manager) -> None:
    global _websocket_manager
    _websocket_manager = manager


class InAppNotifier(BaseNotifier):

    @property
    def channel_name(self) -> str:
        return "In-App"

    def send(self, rule: dict, events: list[dict]) -> None:
        """Broadcast each event via WebSocket."""
        if _websocket_manager is None:
            logger.warning("WebSocket manager not set")
            return

        for event in events:
            try:
                _websocket_manager.broadcast(event)
            except Exception as exc:
                logger.error(
                    "WebSocket broadcast failed: %s", exc
                )
