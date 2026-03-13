"""Abstract base class for all notifiers.

To add a new notifier:
1. Create a file in app/notifiers/ (e.g. slack_notifier.py)
2. Subclass BaseNotifier and implement all abstract methods
3. That's it — auto-discovery registers it at startup
"""

from abc import ABC, abstractmethod


class BaseNotifier(ABC):
    """Contract every notification channel must follow."""

    @property
    @abstractmethod
    def channel_name(self) -> str:
        """Unique channel identifier, e.g. 'Email', 'In-App'."""

    @abstractmethod
    def send(self, rule: dict, events: list[dict]) -> None:
        """Deliver notifications for the given events.

        Args:
            rule: The full rule dict (targets, channel, etc.)
            events: List of triggered event dicts
        """

    def can_handle(self, rule: dict) -> bool:
        """Return True if this notifier should fire for the rule.
        Default: checks if rule['channel'] matches channel_name
        or rule['channel'] == 'Both'."""
        channel = rule.get("channel", "")
        return channel == self.channel_name or channel == "Both"
