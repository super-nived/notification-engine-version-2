"""SSE Listener — subscribes to PocketBase real-time events.

Listens for 'As It Occurs' rules. One SSE connection per collection.
Auto-reconnects with exponential backoff on failure.
"""

import json
import logging
import threading
import time
from datetime import datetime, timezone
from queue import Queue
from threading import Thread

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
        self._lock = threading.Lock()

    def start(self):
        self._running = True
        with self._lock:
            collections = list(self._subscriptions.keys())
        for collection in collections:
            self._start_listener(collection)
        logger.info(
            "SSE Listener started with %d collection(s)",
            len(collections),
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
        with self._lock:
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
        with self._lock:
            if collection not in self._subscriptions:
                return

            self._subscriptions[collection] = [
                rule if r["id"] == rule["id"] else r
                for r in self._subscriptions[collection]
            ]

    def _register(self, rule: dict) -> str:
        collection = _get_collection(rule)
        with self._lock:
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
            with self._lock:
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
    """Single SSE connection lifecycle.

    Uses a background thread to keep reading the SSE stream
    while the subscribe POST is sent, preventing client ID
    expiration.
    """
    resp = pb_sse_connect()
    event_queue: Queue = Queue()

    reader = Thread(
        target=_read_events,
        args=(resp, event_queue),
        daemon=True,
    )
    reader.start()

    client_id = _wait_for_client_id(event_queue, listener)
    if not client_id:
        resp.close()
        raise RuntimeError("Failed to get SSE client ID")

    pb_sse_subscribe(client_id, [f"{collection}/*"])
    logger.info(
        "SSE subscribed to '%s/*' (client=%s)",
        collection,
        client_id,
    )

    _process_events(listener, event_queue, collection)
    resp.close()


def _read_events(resp, event_queue: Queue):
    """Read SSE events in background, push to queue.

    Uses iter_content instead of sseclient to avoid
    blocking issues with PocketBase's SSE stream.
    """
    buf = ""
    try:
        for chunk in resp.iter_content(
            chunk_size=4096, decode_unicode=True
        ):
            logger.debug("SSE raw chunk: %r", chunk[:200])
            buf += chunk
            while "\n\n" in buf:
                raw, buf = buf.split("\n\n", 1)
                logger.debug("SSE parsed block: %r", raw[:200])
                event = _parse_raw_sse(raw)
                if event:
                    logger.debug(
                        "SSE event: type=%s", event.event
                    )
                    event_queue.put(event)
    except Exception as exc:
        logger.warning("SSE reader stopped: %s", exc)
    event_queue.put(None)


def _parse_raw_sse(raw: str) -> dict | None:
    """Parse a raw SSE block into {event, data}."""
    result = {}
    for line in raw.strip().split("\n"):
        if line.startswith("event:"):
            result["event"] = line[6:].strip()
        elif line.startswith("data:"):
            result["data"] = line[5:].strip()
    if result.get("event"):
        return type("SSEEvent", (), result)()
    return None


def _wait_for_client_id(
    event_queue: Queue, listener: SSEListener
) -> str | None:
    """Wait for PB_CONNECT event to get client ID."""
    from queue import Empty

    while listener._running:
        try:
            event = event_queue.get(timeout=10)
        except Empty:
            logger.warning("Timeout waiting for SSE client ID")
            return None
        if event is None:
            logger.warning("SSE stream closed before client ID")
            return None
        logger.debug(
            "SSE waiting for PB_CONNECT, got: %s",
            event.event,
        )
        if event.event == "PB_CONNECT":
            data = json.loads(event.data)
            return data.get("clientId")
    return None


def _process_events(
    listener: SSEListener,
    event_queue: Queue,
    collection: str,
):
    """Process events from the queue."""
    while listener._running:
        with listener._lock:
            if collection not in listener._subscriptions:
                return

        try:
            event = event_queue.get(timeout=5)
        except Exception:
            continue

        if event is None:
            raise RuntimeError("SSE stream closed")

        if not event.event.startswith(collection):
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
    with listener._lock:
        rules = list(listener._subscriptions.get(collection, []))
    for rule in rules:
        if not rule.get("enabled", True):
            continue
        # Fetch fresh rule data from DB to avoid stale params/state
        fresh_rule = _fetch_fresh_rule(rule)
        if fresh_rule and fresh_rule.get("enabled", False):
            _process_rule(fresh_rule, record)


def _fetch_fresh_rule(rule: dict) -> dict | None:
    """Re-read rule from DB to get current params/state."""
    try:
        from app.db.pb_repositories import get_rule_by_id
        return get_rule_by_id(rule["id"])
    except Exception:
        return rule


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
