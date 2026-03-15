"""Rule Engine — dispatches detection/evaluation to engine plugins.

detect() = scheduled mode (fetches records from datasource)
evaluate() = SSE mode (evaluates a single incoming record)
"""

import logging

from app.engine.registry import get_datasource, get_engine

logger = logging.getLogger(__name__)


def detect(rule: dict) -> list[dict]:
    """Scheduled mode: run engine.detect() with datasource fetch.

    Returns list of triggered events (empty = nothing).
    """
    try:
        engine = get_engine(rule["engine"])
        datasource = get_datasource()
        events = engine.detect(rule, datasource.fetch_records)
        _update_state_if_needed(rule, events)
        return events
    except Exception as exc:
        logger.error(
            "Detection failed for rule '%s': %s",
            rule.get("name", ""),
            exc,
        )
        raise


def evaluate(rule: dict, record: dict) -> list[dict]:
    """SSE mode: run engine.evaluate() on a single record.

    Returns list of triggered events (empty = no match).
    """
    try:
        engine = get_engine(rule["engine"])
        return engine.evaluate(rule, record)
    except Exception as exc:
        logger.error(
            "Evaluation failed for rule '%s': %s",
            rule.get("name", ""),
            exc,
        )
        raise


def _update_state_if_needed(
    rule: dict, events: list[dict]
) -> None:
    """Update last_seen state if new records were detected."""
    if not events:
        return

    latest = _find_latest_created(events)
    if not latest:
        logger.warning(
            "No 'created' field in events for '%s' — "
            "state not updated",
            rule.get("name", ""),
        )
        return

    _persist_state(rule, latest)


def _find_latest_created(events: list[dict]) -> str:
    """Extract the latest 'created' timestamp from events."""
    latest = ""
    for ev in events:
        created = ev.get("created", "")
        if created and created > latest:
            latest = created
    return latest


def _persist_state(rule: dict, latest_created: str) -> None:
    """Save updated last_seen back to the database."""
    from app.db.pb_repositories import update_rule_state

    state = rule.get("state", {})
    old_seen = state.get("last_seen", "")
    if latest_created <= old_seen:
        return

    new_state = {**state, "last_seen": latest_created}
    try:
        update_rule_state(rule["id"], new_state)
        logger.info(
            "State updated for '%s': last_seen=%s",
            rule.get("name", ""),
            latest_created,
        )
    except Exception as exc:
        logger.warning(
            "Failed to update state for '%s': %s",
            rule.get("name", ""),
            exc,
        )
