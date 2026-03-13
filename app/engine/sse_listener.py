"""SSE Listener — subscribes to PocketBase real-time events.

Listens for 'As It Occurs' rules. One SSE connection per collection.
Auto-reconnects with exponential backoff on failure.
"""

import json
import logging
import time
from datetime import datetime, timezone
from threading import Thread

import sseclient

from app.db.pb_client import pb_sse_connect, pb_sse_subscribe
from app.db.pb_repositories import (
    create_execution_log,
    disable_rule,
    update_rule_last_run,
)
from app.engine.delivery import deliver
from app.engine.registry import get_engine_config
from app.engine.rule_engine import evaluate

logger = logging.getLogger(__name__)


class SSEListener:
    """Listens to PocketBase SSE for 'As It Occurs' rules."""

    def __init__(self):
        self._subscriptions: dict[str, list[dict]] = {}
        self._threads: dict[str, Thread] = {}
        self._running = False

    def start(self):
        self._running = True
        for collection in list(self._subscriptions.keys()):
            self._start_listener(collection)
        logger.info(
            "SSE Listener started with %d collection(s)",
            len(self._subscriptions),
        )

    def stop(self):
        self._running = False
        logger.info("SSE Listener stopped")

    def load_rules(self, rules: list[dict]):
        """Load all enabled 'As It Occurs' rules."""
        for rule in rules:
            self._register(rule)

    def add_rule(self, rule: dict):
        """Register a new rule, start listener if needed."""
        collection = self._register(rule)
        if self._running and collection not in self._threads:
            self._start_listener(collection)

    def remove_rule(self, rule: dict):
        """Unregister a rule, stop listener if empty."""
        collection = _get_collection(rule)
        if collection not in self._subscriptions:
            return

        self._subscriptions[collection] = [
            r
            for r in self._subscriptions[collection]
            if r["id"] != rule["id"]
        ]
        if not self._subscriptions[collection]:
            del self._subscriptions[collection]
            logger.info(
                "No more rules for '%s'", collection
            )

    def update_rule(self, rule: dict):
        """Update a rule in the subscriptions."""
        collection = _get_collection(rule)
        if collection not in self._subscriptions:
            return

        self._subscriptions[collection] = [
            rule if r["id"] == rule["id"] else r
            for r in self._subscriptions[collection]
        ]

    def _register(self, rule: dict) -> str:
        collection = _get_collection(rule)
        if collection not in self._subscriptions:
            self._subscriptions[collection] = []
        self._subscriptions[collection].append(rule)
        return collection

    def _start_listener(self, collection: str):
        t = Thread(
            target=self._listen,
            args=(collection,),
            daemon=True,
        )
        t.start()
        self._threads[collection] = t
        logger.info("SSE thread started for '%s'", collection)

    def _listen(self, collection: str):
        """Connect with exponential backoff reconnect."""
        backoff = 1
        while self._running:
            if collection not in self._subscriptions:
                self._threads.pop(collection, None)
                return

            try:
                _sse_loop(self, collection)
                backoff = 1
            except Exception as exc:
                if not self._running:
                    break
                logger.error(
                    "SSE error for '%s': %s. Retry in %ds",
                    collection,
                    exc,
                    backoff,
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)

        self._threads.pop(collection, None)


def _get_collection(rule: dict) -> str:
    cfg = get_engine_config(rule["engine"])
    return cfg["collection"]


def _sse_loop(listener: SSEListener, collection: str):
    """Single SSE connection lifecycle."""
    resp = pb_sse_connect()
    client = sseclient.SSEClient(resp)

    client_id = _get_client_id(client, listener)
    if not client_id:
        raise RuntimeError("Failed to get SSE client ID")

    pb_sse_subscribe(client_id, [f"{collection}/*"])
    logger.info(
        "SSE subscribed to '%s/*' (client=%s)",
        collection,
        client_id,
    )

    _process_events(listener, client, collection)


def _get_client_id(client, listener: SSEListener) -> str | None:
    for event in client.events():
        if not listener._running:
            return None
        if event.event == "PB_CONNECT":
            data = json.loads(event.data)
            return data.get("clientId")
    return None


def _process_events(
    listener: SSEListener, client, collection: str
):
    for event in client.events():
        if not listener._running:
            return
        if collection not in listener._subscriptions:
            return

        if event.event != collection:
            continue

        record = _parse_create_event(event)
        if record:
            _handle_new_record(listener, collection, record)


def _parse_create_event(event) -> dict | None:
    try:
        data = json.loads(event.data)
    except json.JSONDecodeError:
        return None
    if data.get("action") == "create":
        return data.get("record", {})
    return None


def _handle_new_record(
    listener: SSEListener, collection: str, record: dict
):
    """Run all rules for this collection against the record."""
    rules = listener._subscriptions.get(collection, [])
    for rule in rules:
        if not rule.get("enabled", True):
            continue
        _process_rule(rule, record)


def _process_rule(rule: dict, record: dict):
    if _rule_expired(rule):
        logger.info("Rule '%s' expired", rule.get("name", ""))
        _safe_disable(rule["id"])
        return

    started_at = datetime.now(timezone.utc).isoformat()
    try:
        events = evaluate(rule, record)
        if events:
            deliver(rule, events)
            _log_success(rule, started_at, len(events))
    except Exception as exc:
        logger.error(
            "SSE rule '%s' failed: %s",
            rule.get("name", ""),
            exc,
        )
        _log_failure(rule, started_at, str(exc))


def _log_success(rule: dict, started_at: str, count: int):
    _safe_update_last_run(rule["id"], "ok", started_at)
    _safe_log_execution(rule, started_at, "ok", count)
    logger.info(
        "SSE rule '%s' fired %d event(s)",
        rule.get("name", ""),
        count,
    )


def _log_failure(rule: dict, started_at: str, error: str):
    _safe_update_last_run(rule["id"], "error", started_at)
    _safe_log_execution(rule, started_at, "error", 0, error)


def _safe_update_last_run(rule_id, status, timestamp):
    try:
        update_rule_last_run(rule_id, status, timestamp)
    except Exception:
        pass


def _safe_disable(rule_id: str):
    try:
        disable_rule(rule_id)
    except Exception:
        pass


def _safe_log_execution(
    rule, started_at, status, count, error=""
):
    try:
        create_execution_log(
            {
                "rule_name": rule.get("name", ""),
                "started_at": started_at,
                "finished_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "status": status,
                "events_count": count,
                "error": error,
            }
        )
    except Exception as exc:
        logger.warning("Failed to log execution: %s", exc)


def _rule_expired(rule: dict) -> bool:
    expiry = rule.get("expiry_date")
    if not expiry:
        return False
    try:
        exp_dt = datetime.fromisoformat(
            str(expiry).replace("Z", "+00:00")
        )
        if exp_dt.tzinfo is None:
            exp_dt = exp_dt.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > exp_dt
    except (ValueError, TypeError):
        return False
