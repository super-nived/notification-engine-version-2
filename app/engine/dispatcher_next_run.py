"""Dispatcher: next_run mode — default, efficient scheduler.

Stores next_run_at on the rule itself. No bulk schedule records.
After each execution, calculates and saves the next run time.
Expiry check before every execution. Auto-scales with ThreadPool.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event, Thread

from app.db.pb_repositories import (
    create_execution_log,
    disable_rule,
    get_due_rules,
    get_enabled_rules,
    get_next_due_rule,
    get_rule_by_id,
    update_rule_last_run,
    update_rule_next_run,
)
from app.engine.delivery import deliver
from app.engine.registry import rule_is_scheduled
from app.engine.rule_engine import detect
from app.engine.schedule_generator import parse_frequency_minutes

logger = logging.getLogger(__name__)

CONCURRENT_THRESHOLD = 5


class NextRunDispatcher:
    """Executes rules based on next_run_at field."""

    def __init__(self):
        self._running = False
        self._thread: Thread | None = None
        self._wake = Event()

    def start(self):
        _init_next_run_for_all()
        self._running = True
        self._thread = Thread(
            target=self._loop, daemon=True
        )
        self._thread.start()
        logger.info("NextRunDispatcher started")

    def stop(self):
        self._running = False
        self._wake.set()
        logger.info("NextRunDispatcher stopped")

    def wake(self):
        """Wake to check for new/changed rules."""
        self._wake.set()

    def on_rule_created(self, rule: dict) -> None:
        """Set next_run_at for a new scheduled rule."""
        _set_initial_next_run(rule)
        self.wake()

    def on_rule_disabled(self, rule: dict) -> None:
        """Clear next_run_at when rule is disabled."""
        _clear_next_run(rule["id"])

    def on_rule_enabled(self, rule: dict) -> None:
        """Recalculate next_run_at when rule is re-enabled."""
        _set_initial_next_run(rule)
        self.wake()

    def on_rule_deleted(self, rule: dict) -> None:
        """Nothing to clean up — rule is gone."""
        pass

    def on_rule_updated(self, rule: dict) -> None:
        """Recalculate next_run_at after update."""
        _set_initial_next_run(rule)
        self.wake()

    def _loop(self):
        while self._running:
            try:
                self._tick()
            except Exception as exc:
                logger.error("Dispatcher tick failed: %s", exc)
                self._sleep(60)

    def _tick(self):
        """Single iteration of the dispatch loop."""
        next_rule = _get_next_rule()
        if not next_rule:
            self._sleep(60)
            return

        wait = _calc_wait(next_rule.get("next_run_at", ""))
        if wait > 0:
            self._sleep(wait)
            if not self._running:
                return

        due = _get_due_now()
        if due:
            _run_due_rules(due)

    def _sleep(self, timeout: float):
        self._wake.wait(timeout=timeout)
        self._wake.clear()


# ── Startup ──────────────────────────────────────────────────


def _init_next_run_for_all():
    """Set next_run_at for rules that don't have one yet."""
    try:
        rules = get_enabled_rules()
    except Exception as exc:
        logger.error("Failed to load rules: %s", exc)
        return

    for rule in rules:
        if not rule_is_scheduled(rule):
            continue
        if rule.get("next_run_at"):
            _handle_missed_run(rule)
        else:
            _set_initial_next_run(rule)


def _handle_missed_run(rule: dict) -> None:
    """If next_run_at is in the past, keep it so it runs immediately."""
    pass


# ── Next run calculation ─────────────────────────────────────


def _set_initial_next_run(rule: dict) -> None:
    """Calculate and save the first next_run_at."""
    freq = rule.get("frequency", "Hourly")
    minutes = parse_frequency_minutes(freq)
    now = datetime.now(timezone.utc)
    next_time = _next_slot(now, minutes)

    iso = next_time.strftime("%Y-%m-%d %H:%M:%S.000Z")
    try:
        update_rule_next_run(rule["id"], iso)
    except Exception as exc:
        logger.error(
            "Failed to set next_run for '%s': %s",
            rule.get("name", ""),
            exc,
        )


def _advance_next_run(rule: dict) -> None:
    """Calculate the next run time after execution."""
    freq = rule.get("frequency", "Hourly")
    minutes = parse_frequency_minutes(freq)
    now = datetime.now(timezone.utc)
    next_time = now + timedelta(minutes=minutes)

    iso = next_time.strftime("%Y-%m-%d %H:%M:%S.000Z")
    try:
        update_rule_next_run(rule["id"], iso)
    except Exception as exc:
        logger.error(
            "Failed to advance next_run for '%s': %s",
            rule.get("name", ""),
            exc,
        )


def _clear_next_run(rule_id: str) -> None:
    """Clear next_run_at (rule disabled/deleted)."""
    try:
        update_rule_next_run(rule_id, "")
    except Exception as exc:
        logger.error("Failed to clear next_run: %s", exc)


def _next_slot(now: datetime, interval_minutes: int) -> datetime:
    """Calculate the next even slot from now."""
    if interval_minutes >= 60:
        slot = now.replace(minute=0, second=0, microsecond=0)
    else:
        slot = now.replace(second=0, microsecond=0)
    return slot + timedelta(minutes=interval_minutes)


# ── Query helpers ────────────────────────────────────────────


def _get_next_rule() -> dict | None:
    try:
        return get_next_due_rule()
    except Exception as exc:
        logger.error("Failed to get next rule: %s", exc)
        return None


def _get_due_now() -> list[dict]:
    now_iso = datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S.000Z"
    )
    try:
        return get_due_rules(now_iso)
    except Exception as exc:
        logger.error("Failed to get due rules: %s", exc)
        return []


# ── Execution ────────────────────────────────────────────────


def _run_due_rules(due: list[dict]):
    if len(due) <= CONCURRENT_THRESHOLD:
        for rule in due:
            _execute(rule)
    else:
        with ThreadPoolExecutor(5) as pool:
            pool.map(_execute, due)


def _execute(rule: dict):
    """Execute a single rule and advance next_run_at."""
    started_at = datetime.now(timezone.utc).isoformat()

    if _rule_expired(rule):
        _safe_disable(rule["id"])
        _clear_next_run(rule["id"])
        logger.info("Rule '%s' expired", rule.get("name", ""))
        return

    try:
        events = detect(rule)
        if events:
            deliver(rule, events)
        _on_success(rule, started_at, events)
    except Exception as exc:
        _on_failure(rule, started_at, str(exc))


def _on_success(
    rule: dict, started_at: str, events: list
):
    _advance_next_run(rule)
    _safe_update_last_run(rule["id"], "ok", started_at)
    _log_execution(rule, started_at, "ok", len(events))
    logger.info(
        "Rule '%s' done, %d event(s)",
        rule.get("name", ""),
        len(events),
    )


def _on_failure(rule: dict, started_at: str, error: str):
    _advance_next_run(rule)
    _safe_update_last_run(rule["id"], "error", started_at)
    _log_execution(rule, started_at, "error", 0, error)
    logger.error(
        "Rule '%s' failed: %s",
        rule.get("name", ""),
        error,
    )


# ── Safety wrappers ──────────────────────────────────────────


def _safe_disable(rule_id: str):
    try:
        disable_rule(rule_id)
    except Exception:
        pass


def _safe_update_last_run(rule_id, status, timestamp):
    try:
        update_rule_last_run(rule_id, status, timestamp)
    except Exception:
        pass


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


def _calc_wait(next_run_at: str) -> float:
    if not next_run_at:
        return 60
    try:
        dt = datetime.fromisoformat(
            str(next_run_at).replace("Z", "+00:00")
        )
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        diff = (dt - datetime.now(timezone.utc)).total_seconds()
        return max(0, diff)
    except (ValueError, TypeError):
        return 0


def _log_execution(
    rule: dict,
    started_at: str,
    status: str,
    events_count: int,
    error: str = "",
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
                "events_count": events_count,
                "error": error,
            }
        )
    except Exception as exc:
        logger.warning("Failed to log execution: %s", exc)
