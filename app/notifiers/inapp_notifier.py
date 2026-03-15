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

        logger.info(
            "In-App sending %d event(s) for '%s'",
            len(events),
            rule.get("name", ""),
        )
        for event in events:
            try:
                payload = {
                    "rule_name": rule.get("name", ""),
                    "engine": rule.get("engine", ""),
                    "message": event.get("message", ""),
                    "data": event.get("data", {}),
                    "timestamp": event.get("timestamp", ""),
                }
                _websocket_manager.broadcast(payload)
            except Exception as exc:
                logger.error(
                    "WebSocket broadcast failed: %s", exc
                )
