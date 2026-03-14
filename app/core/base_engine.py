"""Abstract base class for all rule engines.

To add a new engine:
1. Create a file in app/engines/ (e.g. my_engine.py)
2. Subclass BaseEngine and implement all abstract methods
3. That's it — auto-discovery registers it at startup
"""

from abc import ABC, abstractmethod


class BaseEngine(ABC):
    """Contract every rule engine must follow."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique display name, e.g. 'Threshold Breach'."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Short user-friendly description of what this engine does."""

    @property
    @abstractmethod
    def use_cases(self) -> list[str]:
        """List of 'when to use this' examples."""

    @property
    @abstractmethod
    def example(self) -> str:
        """Concrete example showing how this engine works."""

    @property
    @abstractmethod
    def collection(self) -> str:
        """PocketBase collection this engine reads from."""

    @property
    @abstractmethod
    def condition_type(self) -> str:
        """Type of condition: 'threshold', 'new_record', etc."""

    @property
    @abstractmethod
    def editable_params(self) -> list[dict]:
        """List of user-editable parameter definitions.
        Each dict: {key, label, type, default, [options]}."""

    @abstractmethod
    def detect(self, rule: dict, fetch_records) -> list[dict]:
        """Scheduled mode: fetch records and return events.

        Args:
            rule: The full rule dict (params, state, etc.)
            fetch_records: callable(collection, filter_str, sort)
                           returns list[dict] of records

        Returns:
            List of event dicts (empty = nothing triggered).
        """

    @abstractmethod
    def evaluate(self, rule: dict, record: dict) -> list[dict]:
        """SSE mode: evaluate a single record against rule.

        Args:
            rule: The full rule dict
            record: The incoming SSE record

        Returns:
            List of event dicts (empty = no match).
        """
