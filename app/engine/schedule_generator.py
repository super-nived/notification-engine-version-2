"""Schedule Generator — creates schedule records for scheduled rules.

Generates all records from now until expiry (or 30 days default).
Only used for scheduled rules, NOT for 'As It Occurs'.
"""

import logging
from datetime import datetime, timedelta, timezone

from app.db.pb_repositories import (
    create_schedule,
    get_schedules_for_rule,
)

logger = logging.getLogger(__name__)

FREQUENCY_MAP = {
    "Every 1 Minute": 1,
    "Hourly": 60,
    "Daily": 60 * 24,
    "Weekly": 60 * 24 * 7,
}

DEFAULT_WINDOW_DAYS = 30


def generate_schedules(rule: dict) -> int:
    """Generate all schedule records from now until expiry.
    Returns the number of schedules created."""
    minutes = parse_frequency_minutes(rule.get("frequency", "Hourly"))
    now = datetime.now(timezone.utc)
    end = _determine_end_time(rule, now)
    existing_times = _load_existing_times(rule["id"])

    return _create_missing_schedules(
        rule, now, end, minutes, existing_times
    )


def top_up_schedules(rule: dict) -> int:
    """Top up schedules for rules without expiry."""
    return generate_schedules(rule)


def parse_frequency_minutes(frequency: str) -> int:
    """Convert frequency string to minutes."""
    if frequency in FREQUENCY_MAP:
        return FREQUENCY_MAP[frequency]
    try:
        return int(frequency)
    except (ValueError, TypeError):
        return 60


def _determine_end_time(rule: dict, now: datetime) -> datetime:
    """Get schedule end time from expiry or default window."""
    expiry = _parse_expiry(rule.get("expiry_date"))
    if expiry:
        return expiry
    return now + timedelta(days=DEFAULT_WINDOW_DAYS)


def _load_existing_times(rule_id: str) -> set[str]:
    """Load all existing schedule times to avoid duplicates."""
    existing = get_schedules_for_rule(rule_id)
    return {s["scheduled_at"] for s in existing}


def _create_missing_schedules(
    rule: dict,
    now: datetime,
    end: datetime,
    minutes: int,
    existing_times: set[str],
) -> int:
    """Create schedule records for all missing time slots."""
    created = 0
    t = _next_slot(now, minutes)

    while t <= end:
        iso = t.strftime("%Y-%m-%d %H:%M:%S.000Z")
        if iso not in existing_times:
            _create_one(rule, iso)
            created += 1
        t += timedelta(minutes=minutes)

    _log_result(rule, created, minutes, end)
    return created


def _create_one(rule: dict, iso: str) -> None:
    create_schedule(
        {
            "rule_id": rule["id"],
            "rule_name": rule.get("name", ""),
            "scheduled_at": iso,
        }
    )


def _next_slot(now: datetime, interval_minutes: int) -> datetime:
    """Calculate the next even slot from now."""
    if interval_minutes >= 60:
        slot = now.replace(minute=0, second=0, microsecond=0)
    else:
        slot = now.replace(second=0, microsecond=0)
    return slot + timedelta(minutes=interval_minutes)


def _parse_expiry(expiry) -> datetime | None:
    if not expiry:
        return None
    if isinstance(expiry, datetime):
        return expiry.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(
            str(expiry).replace("Z", "+00:00")
        )
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _log_result(
    rule: dict, created: int, minutes: int, end: datetime
) -> None:
    logger.info(
        "Generated %d schedules for '%s' (every %d min, until %s)",
        created,
        rule.get("name", ""),
        minutes,
        end.strftime("%Y-%m-%d %H:%M"),
    )
