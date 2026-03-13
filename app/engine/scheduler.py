"""Dispatcher — executes scheduled rules at their exact times.

Single-threaded loop that sleeps until the next schedule,
then fires all due schedules. Auto-scales with ThreadPool
when more than CONCURRENT_THRESHOLD schedules are due.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Event, Thread

from app.db.pb_repositories import (
    create_execution_log,
    disable_rule,
    get_due_schedules,
    get_enabled_rules,
    get_rule_by_id,
    mark_schedule_done,
    mark_schedule_failed,
    mark_schedule_running,
    mark_stale_running_as_failed,
    get_next_pending_schedule,
)
from app.engine.delivery import deliver
from app.engine.registry import rule_is_scheduled
from app.engine.rule_engine import detect
from app.engine.schedule_generator import (
    generate_schedules,
    top_up_schedules,
)

logger = logging.getLogger(__name__)

CONCURRENT_THRESHOLD = 5


class Dispatcher:
    """Executes scheduled rules at their exact times."""

    def __init__(self):
        self._running = False
        self._thread: Thread | None = None
        self._wake = Event()

    def start(self):
        _recover_stale_schedules()
        _generate_all_schedules()
        self._running = True
        self._thread = Thread(
            target=self._loop, daemon=True
        )
        self._thread.start()
        logger.info("Dispatcher started")

    def stop(self):
        self._running = False
        self._wake.set()
        logger.info("Dispatcher stopped")

    def wake(self):
        """Wake the dispatcher to check for new schedules."""
        self._wake.set()

    def _loop(self):
        while self._running:
            try:
                self._tick()
            except Exception as exc:
                logger.error("Dispatcher tick failed: %s", exc)
                self._sleep(60)

    def _tick(self):
        """Single iteration of the dispatch loop."""
        next_sched = _get_next_schedule()
        if not next_sched:
            self._sleep(60)
            return

        wait = _calc_wait(next_sched["scheduled_at"])
        if wait > 0:
            self._sleep(wait)
            if not self._running:
                return

        due = _get_due_now()
        if due:
            _run_due_schedules(due)
            _top_up_all()

    def _sleep(self, timeout: float):
        self._wake.wait(timeout=timeout)
        self._wake.clear()


def _recover_stale_schedules():
    try:
        mark_stale_running_as_failed()
    except Exception as exc:
        logger.warning(
            "Could not mark stale schedules: %s", exc
        )


def _generate_all_schedules():
    """Generate schedules for all enabled scheduled rules."""
    try:
        rules = get_enabled_rules()
    except Exception as exc:
        logger.error("Failed to load rules: %s", exc)
        return

    for rule in rules:
        if rule_is_scheduled(rule):
            _safe_generate(rule)


def _safe_generate(rule: dict):
    try:
        generate_schedules(rule)
    except Exception as exc:
        logger.error(
            "Failed to generate schedules for '%s': %s",
            rule.get("name", ""),
            exc,
        )


def _get_next_schedule() -> dict | None:
    try:
        return get_next_pending_schedule()
    except Exception as exc:
        logger.error("Failed to get next schedule: %s", exc)
        return None


def _get_due_now() -> list[dict]:
    now_iso = datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S.000Z"
    )
    try:
        return get_due_schedules(now_iso)
    except Exception as exc:
        logger.error("Failed to get due schedules: %s", exc)
        return []


def _run_due_schedules(due: list[dict]):
    if len(due) <= CONCURRENT_THRESHOLD:
        for s in due:
            _execute(s)
    else:
        with ThreadPoolExecutor(5) as pool:
            pool.map(_execute, due)


def _execute(schedule: dict):
    """Execute a single schedule record."""
    try:
        mark_schedule_running(schedule["id"])
    except Exception as exc:
        logger.error("Failed to mark running: %s", exc)
        return

    started_at = datetime.now(timezone.utc).isoformat()
    try:
        rule = get_rule_by_id(schedule["rule_id"])
        events = _run_rule(rule, schedule, started_at)
        _mark_success(schedule, rule, started_at, events)
    except Exception as exc:
        _mark_failure(schedule, started_at, str(exc))


def _run_rule(
    rule: dict, schedule: dict, started_at: str
) -> list[dict]:
    """Check expiry and detect events."""
    if _rule_expired(rule):
        mark_schedule_done(schedule["id"], 0)
        _safe_disable(rule["id"])
        return []

    events = detect(rule)
    if events:
        deliver(rule, events)
    return events


def _mark_success(
    schedule: dict, rule: dict, started_at: str, events: list
):
    mark_schedule_done(schedule["id"], len(events))
    _log_execution(rule, started_at, "ok", len(events))
    logger.info(
        "Schedule %s done: '%s', %d event(s)",
        schedule["id"],
        rule.get("name", ""),
        len(events),
    )


def _mark_failure(schedule: dict, started_at: str, error: str):
    logger.error("Schedule %s failed: %s", schedule["id"], error)
    try:
        mark_schedule_failed(schedule["id"], error)
    except Exception:
        pass
    _log_execution(
        {"name": schedule.get("rule_name", "")},
        started_at,
        "error",
        0,
        error,
    )


def _safe_disable(rule_id: str):
    try:
        disable_rule(rule_id)
    except Exception:
        pass


def _top_up_all():
    """Top up schedule records for all scheduled rules."""
    try:
        rules = get_enabled_rules()
    except Exception:
        return

    for rule in rules:
        if rule_is_scheduled(rule):
            try:
                top_up_schedules(rule)
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


def _calc_wait(scheduled_at: str) -> float:
    try:
        dt = datetime.fromisoformat(
            str(scheduled_at).replace("Z", "+00:00")
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
