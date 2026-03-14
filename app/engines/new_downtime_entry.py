"""New Downtime Entry Engine — standalone plugin.

Detects any new downtime record. Fully automatic, no user params.
"""

import logging
from datetime import datetime, timezone

from app.core.base_engine import BaseEngine

logger = logging.getLogger(__name__)


class NewDowntimeEntryEngine(BaseEngine):

    @property
    def name(self) -> str:
        return "New Downtime Entry"

    @property
    def description(self) -> str:
        return (
            "Sends an alert immediately whenever a new downtime "
            "record is logged. Fully automatic — no configuration "
            "needed. Every new entry triggers a notification."
        )

    @property
    def use_cases(self) -> list[str]:
        return [
            "Alert the maintenance team when any machine goes down",
            "Notify supervisors of unplanned production stops",
            "Track downtime events in real-time for shift reports",
            "Escalate repeated downtime on the same machine",
        ]

    @property
    def example(self) -> str:
        return (
            "No setup needed — fully automatic\n"
            "→ Every new downtime record triggers an instant "
            "alert to your chosen targets. Zero configuration."
        )

    @property
    def collection(self) -> str:
        return "shift_downtime"

    @property
    def condition_type(self) -> str:
        return "new_record"

    @property
    def editable_params(self) -> list[dict]:
        return []

    def detect(self, rule: dict, fetch_records) -> list[dict]:
        """Fetch new records since last_seen."""
        state = rule.get("state", {})
        last_seen = state.get("last_seen", "")

        filter_str = f'created > "{last_seen}"' if last_seen else ""
        records = fetch_records(
            self.collection, filter_str=filter_str, sort="created"
        )
        return [_make_event(rule, rec) for rec in records]

    def evaluate(self, rule: dict, record: dict) -> list[dict]:
        """Every new downtime record triggers."""
        return [_make_event(rule, record)]


def _make_event(rule: dict, record: dict) -> dict:
    return {
        "rule_name": rule.get("name", ""),
        "rule_id": rule.get("id", ""),
        "engine": rule.get("engine", ""),
        "record_id": record.get("id", ""),
        "record": record,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": (
            f"[{rule.get('engine', '')}] Rule "
            f"'{rule.get('name', '')}' triggered on "
            f"record {record.get('id', 'N/A')}"
        ),
    }
