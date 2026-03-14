"""Scheduler factory — creates the right dispatcher based on config.

SCHEDULER_MODE in .env:
  "next_run"          → NextRunDispatcher (default, efficient)
  "schedule_records"  → ScheduleRecordsDispatcher (old method)

Both dispatchers share the same public interface:
  start(), stop(), wake()
  on_rule_created(), on_rule_disabled(), on_rule_enabled()
  on_rule_deleted(), on_rule_updated()
"""

import logging

from app.core.settings import settings

logger = logging.getLogger(__name__)


def create_dispatcher():
    """Factory: return the right dispatcher based on config."""
    mode = settings.SCHEDULER_MODE

    if mode == "schedule_records":
        return _create_schedule_records_dispatcher()

    return _create_next_run_dispatcher()


def _create_next_run_dispatcher():
    from app.engine.dispatcher_next_run import NextRunDispatcher

    logger.info("Using NextRunDispatcher (SCHEDULER_MODE=next_run)")
    return NextRunDispatcher()


def _create_schedule_records_dispatcher():
    from app.engine.dispatcher_schedule_records import (
        ScheduleRecordsDispatcher,
    )

    logger.info(
        "Using ScheduleRecordsDispatcher "
        "(SCHEDULER_MODE=schedule_records)"
    )
    return ScheduleRecordsDispatcher()
