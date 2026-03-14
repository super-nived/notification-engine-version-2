"""Domain-level CRUD for rules and execution_logs.

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


def update_rule_next_run(rule_id: str, next_run_at: str) -> None:
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


# ── Rules: next_run queries ──────────────────────────────────


def get_next_due_rule() -> dict | None:
    """Get the earliest enabled rule with next_run_at set."""
    data = pb_list(
        RULES_COLLECTION,
        page=1,
        per_page=1,
        filter_str='enabled=true && next_run_at!=""',
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


def get_execution_logs(rule_name: str | None = None) -> list[dict]:
    f = f'rule_name="{rule_name}"' if rule_name else ""
    return pb_get_full_list(
        EXECUTION_LOGS_COLLECTION,
        filter_str=f,
        sort="-started_at",
    )


def count_active_rules() -> int:
    """Count enabled rules."""
    data = pb_list(
        RULES_COLLECTION,
        page=1,
        per_page=1,
        filter_str="enabled=true",
    )
    return data.get("totalItems", 0)


def count_executions_today(status: str | None = None) -> int:
    """Count execution logs from today, optionally filtered by status."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d 00:00:00.000Z")
    f = f'started_at>="{today}"'
    if status:
        f += f' && status="{status}"'
    data = pb_list(
        EXECUTION_LOGS_COLLECTION,
        page=1,
        per_page=1,
        filter_str=f,
    )
    return data.get("totalItems", 0)
