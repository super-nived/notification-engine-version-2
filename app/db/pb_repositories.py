"""Domain-level CRUD for rules, schedules, execution_logs.

All PocketBase access goes through pb_client.py.
"""

import json
import logging
from datetime import datetime, timezone

from app.db.pb_client import (
    pb_create,
    pb_delete,
    pb_get_full_list,
    pb_get_one,
    pb_list,
    pb_update,
)

logger = logging.getLogger(__name__)

RULES_COLLECTION = "rules"
SCHEDULES_COLLECTION = "schedules"
EXECUTION_LOGS_COLLECTION = "execution_logs"


# ── Domain mapping ────────────────────────────────────────────


def _rule_to_domain(record: dict) -> dict:
    """Map a PocketBase rule record to domain dict."""
    return {
        "id": record["id"],
        "name": record.get("name", ""),
        "engine": record.get("engine", ""),
        "frequency": record.get("frequency", ""),
        "channel": record.get("channel", "In-App"),
        "targets": _parse_json_field(record.get("targets", "[]")),
        "params": _parse_json_field(record.get("params", "{}")),
        "description": record.get("description", ""),
        "expiry_date": record.get("expiry_date"),
        "enabled": record.get("enabled", False),
        "state": _parse_json_field(record.get("state", "{}")),
        "last_run_at": record.get("last_run_at"),
        "last_status": record.get("last_status", ""),
        "next_run_at": record.get("next_run_at"),
        "created": record.get("created", ""),
    }


def _schedule_to_domain(record: dict) -> dict:
    return {
        "id": record["id"],
        "rule_id": record.get("rule_id", ""),
        "rule_name": record.get("rule_name", ""),
        "scheduled_at": record.get("scheduled_at", ""),
        "status": record.get("status", "pending"),
        "executed_at": record.get("executed_at"),
        "events_count": record.get("events_count", 0),
        "error": record.get("error", ""),
    }


def _parse_json_field(value) -> dict | list:
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


# ── Rules CRUD ────────────────────────────────────────────────


def get_all_rules() -> list[dict]:
    records = pb_get_full_list(RULES_COLLECTION, sort="-created")
    return [_rule_to_domain(r) for r in records]


def get_enabled_rules() -> list[dict]:
    records = pb_get_full_list(
        RULES_COLLECTION,
        filter_str="enabled=true",
        sort="-created",
    )
    return [_rule_to_domain(r) for r in records]


def get_rule_by_id(rule_id: str) -> dict:
    record = pb_get_one(RULES_COLLECTION, rule_id)
    return _rule_to_domain(record)


def create_rule(data: dict) -> dict:
    payload = _build_create_payload(data)
    record = pb_create(RULES_COLLECTION, payload)
    return _rule_to_domain(record)


def _build_create_payload(data: dict) -> dict:
    return {
        "name": data["name"],
        "engine": data["engine"],
        "frequency": data.get("frequency", "As It Occurs"),
        "channel": data.get("channel", "In-App"),
        "targets": json.dumps(data.get("targets", [])),
        "params": json.dumps(data.get("params", {})),
        "description": data.get("description", ""),
        "expiry_date": data.get("expiry_date"),
        "enabled": data.get("enabled", True),
        "state": json.dumps({}),
        "last_run_at": None,
        "last_status": "",
        "next_run_at": data.get("next_run_at"),
    }


def update_rule(rule_id: str, data: dict) -> dict:
    payload = _build_update_payload(data)
    record = pb_update(RULES_COLLECTION, rule_id, payload)
    return _rule_to_domain(record)


def _build_update_payload(data: dict) -> dict:
    payload = {}
    direct_fields = [
        "name", "engine", "frequency", "channel",
        "description", "expiry_date", "enabled",
        "last_run_at", "last_status", "next_run_at",
    ]
    for field in direct_fields:
        if field in data:
            payload[field] = data[field]

    if "targets" in data:
        payload["targets"] = json.dumps(data["targets"])
    if "params" in data:
        payload["params"] = json.dumps(data["params"])
    if "state" in data:
        payload["state"] = json.dumps(data["state"])

    return payload


def delete_rule(rule_id: str) -> None:
    pb_delete(RULES_COLLECTION, rule_id)


def update_rule_state(rule_id: str, state: dict) -> None:
    pb_update(
        RULES_COLLECTION,
        rule_id,
        {"state": json.dumps(state)},
    )


def update_rule_last_run(
    rule_id: str, status: str, timestamp: str | None = None
) -> None:
    ts = timestamp or datetime.now(timezone.utc).isoformat()
    pb_update(
        RULES_COLLECTION,
        rule_id,
        {"last_run_at": ts, "last_status": status},
    )


def update_rule_next_run(
    rule_id: str, next_run_at: str
) -> None:
    """Update the next_run_at field on a rule."""
    pb_update(
        RULES_COLLECTION,
        rule_id,
        {"next_run_at": next_run_at},
    )


def disable_rule(rule_id: str) -> dict:
    record = pb_update(
        RULES_COLLECTION, rule_id, {"enabled": False}
    )
    return _rule_to_domain(record)


# ── Rules: next_run queries (for next_run mode) ─────────────


def get_next_due_rule() -> dict | None:
    """Get the earliest enabled rule with next_run_at."""
    now_iso = datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S.000Z"
    )
    data = pb_list(
        RULES_COLLECTION,
        page=1,
        per_page=1,
        filter_str=(
            'enabled=true && next_run_at!="" '
            '&& next_run_at!=""'
        ),
        sort="next_run_at",
    )
    items = data.get("items", [])
    if items:
        return _rule_to_domain(items[0])
    return None


def get_due_rules(before_iso: str) -> list[dict]:
    """Get all enabled rules with next_run_at <= before_iso."""
    records = pb_get_full_list(
        RULES_COLLECTION,
        filter_str=(
            f'enabled=true && next_run_at<="{before_iso}" '
            f'&& next_run_at!=""'
        ),
        sort="next_run_at",
    )
    return [_rule_to_domain(r) for r in records]


# ── Schedules CRUD (for schedule_records mode) ───────────────


def create_schedule(data: dict) -> dict:
    payload = {
        "rule_id": data["rule_id"],
        "rule_name": data.get("rule_name", ""),
        "scheduled_at": data["scheduled_at"],
        "status": "pending",
        "executed_at": None,
        "events_count": 0,
        "error": "",
    }
    record = pb_create(SCHEDULES_COLLECTION, payload)
    return _schedule_to_domain(record)


def get_next_pending_schedule() -> dict | None:
    data = pb_list(
        SCHEDULES_COLLECTION,
        page=1,
        per_page=1,
        filter_str='status="pending"',
        sort="scheduled_at",
    )
    items = data.get("items", [])
    if items:
        return _schedule_to_domain(items[0])
    return None


def get_due_schedules(before_iso: str) -> list[dict]:
    f = f'status="pending" && scheduled_at<="{before_iso}"'
    records = pb_get_full_list(
        SCHEDULES_COLLECTION,
        filter_str=f,
        sort="scheduled_at",
    )
    return [_schedule_to_domain(r) for r in records]


def mark_schedule_running(schedule_id: str) -> None:
    pb_update(
        SCHEDULES_COLLECTION, schedule_id, {"status": "running"}
    )


def mark_schedule_done(
    schedule_id: str, events_count: int
) -> None:
    pb_update(
        SCHEDULES_COLLECTION,
        schedule_id,
        {
            "status": "done",
            "executed_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "events_count": events_count,
        },
    )


def mark_schedule_failed(
    schedule_id: str, error_msg: str
) -> None:
    pb_update(
        SCHEDULES_COLLECTION,
        schedule_id,
        {
            "status": "failed",
            "executed_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "error": error_msg,
        },
    )


def mark_schedule_skipped(schedule_id: str) -> None:
    pb_update(
        SCHEDULES_COLLECTION, schedule_id, {"status": "skipped"}
    )


def delete_schedules_for_rule(rule_id: str) -> None:
    records = pb_get_full_list(
        SCHEDULES_COLLECTION,
        filter_str=f'rule_id="{rule_id}"',
    )
    for r in records:
        pb_delete(SCHEDULES_COLLECTION, r["id"])


def skip_pending_schedules_for_rule(rule_id: str) -> None:
    records = pb_get_full_list(
        SCHEDULES_COLLECTION,
        filter_str=f'rule_id="{rule_id}" && status="pending"',
    )
    for r in records:
        mark_schedule_skipped(r["id"])


def mark_stale_running_as_failed() -> None:
    records = pb_get_full_list(
        SCHEDULES_COLLECTION,
        filter_str='status="running"',
    )
    for r in records:
        mark_schedule_failed(
            r["id"], "Stale: was running when server restarted"
        )


def get_schedules_for_rule(rule_id: str) -> list[dict]:
    records = pb_get_full_list(
        SCHEDULES_COLLECTION,
        filter_str=f'rule_id="{rule_id}"',
        sort="-scheduled_at",
    )
    return [_schedule_to_domain(r) for r in records]


# ── Execution Logs ────────────────────────────────────────────


def create_execution_log(data: dict) -> dict:
    payload = {
        "rule_name": data.get("rule_name", ""),
        "started_at": data.get("started_at", ""),
        "finished_at": data.get(
            "finished_at",
            datetime.now(timezone.utc).isoformat(),
        ),
        "status": data.get("status", "ok"),
        "events_count": data.get("events_count", 0),
        "error": data.get("error", ""),
    }
    return pb_create(EXECUTION_LOGS_COLLECTION, payload)


def get_execution_logs(
    rule_name: str | None = None,
) -> list[dict]:
    f = f'rule_name="{rule_name}"' if rule_name else ""
    return pb_get_full_list(
        EXECUTION_LOGS_COLLECTION,
        filter_str=f,
        sort="-started_at",
    )
