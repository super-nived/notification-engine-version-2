"""Delivery module — routes events to the right notifier plugins.

Shared by both the Dispatcher (scheduled) and SSE Listener (real-time).
"""

import logging

from app.engine.registry import get_notifiers_for_rule

logger = logging.getLogger(__name__)


def deliver(rule: dict, events: list[dict]) -> None:
    """Send events through all matching notifier plugins."""
    logger.info(
        "Delivering %d event(s) for rule '%s' (channel=%s)",
        len(events),
        rule.get("name", ""),
        rule.get("channel", ""),
    )
    notifiers = get_notifiers_for_rule(rule)
    logger.info(
        "Matched notifiers: %s",
        [n.channel_name for n in notifiers],
    )
    if not notifiers:
        logger.warning(
            "No notifiers found for channel '%s'",
            rule.get("channel", ""),
        )
        return

    for notifier in notifiers:
        _safe_send(notifier, rule, events)


def _safe_send(notifier, rule: dict, events: list[dict]) -> None:
    """Call notifier.send() with error protection."""
    try:
        notifier.send(rule, events)
    except Exception as exc:
        logger.error(
            "Notifier '%s' failed for rule '%s': %s",
            notifier.channel_name,
            rule.get("name", ""),
            exc,
        )
