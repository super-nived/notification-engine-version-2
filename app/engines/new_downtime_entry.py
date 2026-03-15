"""New Downtime Entry Engine — standalone plugin.

Detects any new downtime record. Fully automatic, no user params.
Uses PocketBase expand to resolve machine and station names.
"""

import logging
from datetime import datetime, timezone

from app.core.base_engine import BaseEngine

logger = logging.getLogger(__name__)

_EXPAND = "machines,stationId"


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
        return "OCCDUBAI01_shift_downtime"

    @property
    def condition_type(self) -> str:
        return "new_record"

    @property
    def editable_params(self) -> list[dict]:
        return []

    def detect(self, rule: dict, fetch_records) -> list[dict]:
        """Fetch new records since last_seen with expand."""
        state = rule.get("state", {})
        last_seen = state.get("last_seen", "")

        filter_str = (
            f'created > "{last_seen}"' if last_seen else ""
        )
        records = fetch_records(
            self.collection,
            filter_str=filter_str,
            sort="created",
            expand=_EXPAND,
        )
        return [_make_event(rule, rec) for rec in records]

    def evaluate(self, rule: dict, record: dict) -> list[dict]:
        """Every new downtime record triggers.

        SSE records don't have expand data, so we fetch
        the full record with expand if needed.
        """
        if "expand" not in record or not record["expand"]:
            record = _fetch_with_expand(
                self.collection, record
            )
        return [_make_event(rule, record)]


def _fetch_with_expand(
    collection: str, record: dict
) -> dict:
    """Re-fetch a record with expand to get relation names."""
    from app.db.pb_client import pb_get_one

    record_id = record.get("id", "")
    if not record_id:
        return record
    try:
        # pb_get_one doesn't support expand, use pb_list
        from app.db.pb_client import pb_list

        data = pb_list(
            collection,
            page=1,
            per_page=1,
            filter_str=f'id="{record_id}"',
            expand=_EXPAND,
        )
        items = data.get("items", [])
        if items:
            return items[0]
    except Exception as exc:
        logger.debug("Could not expand record: %s", exc)
    return record


def _make_event(rule: dict, record: dict) -> dict:
    display = _build_display_data(record)
    machine_name = display.get("Machine", "Unknown machine")
    reason = display.get("Reason", "Not specified")

    return {
        "rule_name": rule.get("name", ""),
        "rule_id": rule.get("id", ""),
        "engine": "New Downtime Entry",
        "record_id": record.get("id", ""),
        "created": record.get("created", ""),
        "data": display,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": (
            f"New downtime recorded on {machine_name} "
            f"— Reason: {reason}"
        ),
    }


def _build_display_data(record: dict) -> dict:
    """Convert raw record to user-friendly display fields."""
    display = {}
    expand = record.get("expand", {})

    # Machine name from expand
    machines = expand.get("machines", [])
    if isinstance(machines, list) and machines:
        names = [
            m.get("displayName", m.get("name", ""))
            for m in machines
        ]
        display["Machine"] = ", ".join(
            n for n in names if n
        ) or "Unknown"
    elif isinstance(machines, dict):
        display["Machine"] = machines.get(
            "displayName", machines.get("name", "Unknown")
        )

    # Station name from expand
    station = expand.get("stationId")
    if isinstance(station, dict):
        display["Work Station"] = station.get(
            "displayName", station.get("name", "")
        )
    elif isinstance(station, list) and station:
        display["Work Station"] = station[0].get(
            "displayName", station[0].get("name", "")
        )

    # Direct fields
    if record.get("reason_code"):
        display["Reason"] = record["reason_code"]

    start = record.get("start_date")
    if start:
        display["Start Time"] = _format_datetime(start)

    end = record.get("end_date")
    if end:
        display["End Time"] = _format_datetime(end)

    return display


def _format_datetime(value: str) -> str:
    try:
        dt = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
        return dt.strftime("%b %d, %Y at %I:%M %p")
    except (ValueError, TypeError):
        return str(value)
