"""New Job Entry Engine — standalone plugin.

Detects new job records that match user-configured field values.
For example: jobStatus = "Released" AND customerApproved = "YES".
"""

import logging
from datetime import datetime, timezone

from app.core.base_engine import BaseEngine

logger = logging.getLogger(__name__)


class NewJobEntryEngine(BaseEngine):

    @property
    def name(self) -> str:
        return "New Job Entry"

    @property
    def collection(self) -> str:
        return "job_details"

    @property
    def condition_type(self) -> str:
        return "new_record"

    @property
    def editable_params(self) -> list[dict]:
        return [
            {
                "key": "jobStatus_value",
                "label": "Job Status",
                "type": "text",
                "default": "Released",
            },
            {
                "key": "customerApproved_value",
                "label": "Customer Approved",
                "type": "text",
                "default": "YES",
            },
        ]

    def detect(self, rule: dict, fetch_records) -> list[dict]:
        """Fetch new records since last_seen, filter by params."""
        params = rule.get("params", {})
        state = rule.get("state", {})
        last_seen = state.get("last_seen", "")

        filter_str = f'created > "{last_seen}"' if last_seen else ""
        records = fetch_records(
            self.collection, filter_str=filter_str, sort="created"
        )
        return _match_and_collect(rule, records, params)

    def evaluate(self, rule: dict, record: dict) -> list[dict]:
        """Check a single SSE record against params."""
        params = rule.get("params", {})
        if _record_matches_params(record, params):
            return [_make_event(rule, record)]
        return []


def _match_and_collect(
    rule: dict, records: list[dict], params: dict
) -> list[dict]:
    events = []
    for rec in records:
        if _record_matches_params(rec, params):
            events.append(_make_event(rule, rec))
    return events


def _record_matches_params(record: dict, params: dict) -> bool:
    """Params like 'jobStatus_value' match field 'jobStatus'."""
    for key, expected in params.items():
        if not key.endswith("_value"):
            continue
        field_name = key[: -len("_value")]
        actual = record.get(field_name)
        if actual is not None and str(actual) != str(expected):
            return False
    return True


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
