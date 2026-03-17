"""In-App (WebSocket) Notifier — standalone plugin.

Broadcasts a single summary notification to all connected
WebSocket clients per rule execution.
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
        """Broadcast one summary message via WebSocket."""
        if _websocket_manager is None:
            logger.warning("WebSocket manager not set")
            return

        count = len(events)
        if count == 1:
            message = events[0].get("message", "Event detected")
        else:
            message = f"{count} event(s) detected"

        payload = {
            "rule_name": rule.get("name", ""),
            "engine": rule.get("engine", ""),
            "message": message,
            "count": count,
            "timestamp": events[0].get("timestamp", ""),
        }

        try:
            _websocket_manager.broadcast(payload)
        except Exception as exc:
            logger.error(
                "WebSocket broadcast failed: %s", exc
            )
