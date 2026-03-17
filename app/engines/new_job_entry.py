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
    def description(self) -> str:
        return (
            "Watches for new job records and sends an alert when a "
            "job matches your configured field values. Triggers "
            "instantly via real-time events — no polling delay."
        )

    @property
    def use_cases(self) -> list[str]:
        return [
            "Alert when a new job is released for production",
            "Alert when a customer-approved job is created",
            "Alert when a high-priority job enters the system",
            "Alert when a specific job type is logged",
        ]

    @property
    def example(self) -> str:
        return (
            "Job status must be = Released · "
            "Customer approved must be = YES\n"
            "→ You get an alert the moment a new job with "
            "these values is created. Instant, no delay."
        )

    @property
    def collection(self) -> str:
        return "OCCDUBAI01_jobDetails"

    @property
    def condition_type(self) -> str:
        return "new_record"

    @property
    def editable_params(self) -> list[dict]:
        return [
            {
                "key": "jobStatus_value",
                "label": "Job status must be",
                "type": "text",
                "default": "Released",
            },
            {
                "key": "customerApproved_value",
                "label": "Customer approved must be",
                "type": "text",
                "default": "YES",
            },
        ]

    def detect(self, rule: dict, fetch_records) -> list[dict]:
        """Fetch new records since last_seen, filter by params."""
        params = rule.get("params", {})
        state = rule.get("state", {})
        last_seen = state.get("last_seen", "")

        filter_str = (
            f'created > "{last_seen}"' if last_seen else ""
        )
        records = fetch_records(
            self.collection,
            filter_str=filter_str,
            sort="created",
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


def _record_matches_params(
    record: dict, params: dict
) -> bool:
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
    display = _build_display_data(record)
    customer = display.get("Customer Name", "N/A")
    order_id = display.get("Order ID", "N/A")

    return {
        "rule_name": rule.get("name", ""),
        "rule_id": rule.get("id", ""),
        "engine": "New Job Entry",
        "record_id": record.get("id", ""),
        "created": record.get("created", ""),
        "data": display,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": (
            f"New job released for {customer} "
            f"— Order: {order_id}"
        ),
    }


def _build_display_data(record: dict) -> dict:
    """Convert raw record to user-friendly display fields."""
    display = {}

    # Order ID = soNumber - soLineNumber
    so_number = record.get("soNumber", "")
    so_line = record.get("soLineNumber", "")
    if so_number:
        order_id = f"{so_number} - {so_line}" if so_line else str(so_number)
        display["Order ID"] = order_id

    # Simple field mappings
    field_map = {
        "customerName": "Customer Name",
        "jobQty": "Order Quantity",
        "jobCreationDate": "Expected Delivery Date",
        "productType": "Product Type",
    }

    for key, label in field_map.items():
        val = record.get(key)
        if val is not None and val != "":
            display[label] = str(val)

    # Format the date if present
    if "Expected Delivery Date" in display:
        display["Expected Delivery Date"] = _format_date(
            display["Expected Delivery Date"]
        )

    return display


def _format_date(value: str) -> str:
    """Format ISO date to readable format."""
    try:
        dt = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
        return dt.strftime("%b %d, %Y")
    except (ValueError, TypeError):
        return str(value)
