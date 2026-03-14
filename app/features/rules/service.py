"""Rules Service — business logic layer.

Orchestrates rule CRUD with dispatcher/SSE routing.
No business logic in routers — all logic lives here.
"""

import logging

from app.db import pb_repositories as repo
from app.engine.registry import (
    get_default_params,
    get_engine,
    get_engine_registry_dict,
    rule_is_as_it_occurs,
    rule_is_scheduled,
)

logger = logging.getLogger(__name__)

_dispatcher = None
_sse_listener = None


def set_dispatcher(dispatcher):
    global _dispatcher
    _dispatcher = dispatcher


def set_sse_listener(listener):
    global _sse_listener
    _sse_listener = listener


class ServiceError(Exception):
    """Raised for user-facing errors with friendly messages."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def list_rules() -> list[dict]:
    try:
        return repo.get_all_rules()
    except Exception as exc:
        logger.error("Failed to list rules: %s", exc)
        raise ServiceError("Could not fetch rules. Please try again.")


def get_rule(rule_id: str) -> dict:
    try:
        return repo.get_rule_by_id(rule_id)
    except Exception as exc:
        logger.error("Failed to get rule %s: %s", rule_id, exc)
        raise ServiceError(
            "Rule not found or could not be retrieved.",
            status_code=404,
        )


def create_rule(data: dict) -> dict:
    """Create a rule and route it to dispatcher or SSE."""
    _validate_engine(data.get("engine", ""))
    _apply_default_params(data)

    try:
        rule = repo.create_rule(data)
    except Exception as exc:
        logger.error("Failed to create rule: %s", exc)
        raise ServiceError("Could not create rule. Check your input.")

    _route_new_rule(rule)
    return rule


def update_rule(rule_id: str, data: dict) -> dict:
    """Update a rule and re-route if needed."""
    old_rule = get_rule(rule_id)

    if "engine" in data:
        _validate_engine(data["engine"])

    try:
        rule = repo.update_rule(rule_id, data)
    except Exception as exc:
        logger.error("Failed to update rule %s: %s", rule_id, exc)
        raise ServiceError("Could not update rule. Check your input.")

    _unroute_old_rule(old_rule)
    if rule.get("enabled", True):
        _route_new_rule(rule)

    return rule


def toggle_rule(rule_id: str, enabled: bool) -> dict:
    """Enable or disable a rule."""
    try:
        rule = repo.update_rule(rule_id, {"enabled": enabled})
    except Exception as exc:
        logger.error("Failed to toggle rule %s: %s", rule_id, exc)
        raise ServiceError("Could not toggle rule.")

    if enabled:
        _route_rule_enabled(rule)
    else:
        _route_rule_disabled(rule)

    return rule


def delete_rule(rule_id: str) -> None:
    """Delete a rule and clean up routing."""
    rule = get_rule(rule_id)
    _route_rule_deleted(rule)

    try:
        repo.delete_rule(rule_id)
    except Exception as exc:
        logger.error("Failed to delete rule %s: %s", rule_id, exc)
        raise ServiceError("Could not delete rule.")

    logger.info("Rule '%s' deleted", rule.get("name", ""))


def get_execution_logs(rule_name: str | None = None) -> list[dict]:
    try:
        return repo.get_execution_logs(rule_name)
    except Exception as exc:
        logger.error("Failed to get logs: %s", exc)
        raise ServiceError("Could not fetch execution logs.")


def get_engine_registry() -> dict:
    return get_engine_registry_dict()


# ── Validation ───────────────────────────────────────────────


def _validate_engine(engine_name: str) -> None:
    try:
        get_engine(engine_name)
    except ValueError:
        raise ServiceError(
            f"Unknown engine type '{engine_name}'. "
            f"Check available engines at GET /engines."
        )


def _apply_default_params(data: dict) -> None:
    if data.get("params"):
        return
    try:
        data["params"] = get_default_params(data["engine"])
    except Exception:
        data["params"] = {}


# ── Routing ──────────────────────────────────────────────────


def _route_new_rule(rule: dict) -> None:
    if rule_is_as_it_occurs(rule):
        _register_sse(rule)
    elif rule_is_scheduled(rule):
        _dispatcher_action("on_rule_created", rule)


def _unroute_old_rule(old_rule: dict) -> None:
    if rule_is_as_it_occurs(old_rule):
        _unregister_sse(old_rule)
    elif rule_is_scheduled(old_rule):
        _dispatcher_action("on_rule_updated", old_rule)


def _route_rule_enabled(rule: dict) -> None:
    if rule_is_as_it_occurs(rule):
        _register_sse(rule)
    elif rule_is_scheduled(rule):
        _dispatcher_action("on_rule_enabled", rule)


def _route_rule_disabled(rule: dict) -> None:
    if rule_is_as_it_occurs(rule):
        _unregister_sse(rule)
    elif rule_is_scheduled(rule):
        _dispatcher_action("on_rule_disabled", rule)


def _route_rule_deleted(rule: dict) -> None:
    if rule_is_as_it_occurs(rule):
        _unregister_sse(rule)
    elif rule_is_scheduled(rule):
        _dispatcher_action("on_rule_deleted", rule)


def _register_sse(rule: dict) -> None:
    if _sse_listener:
        _sse_listener.add_rule(rule)
        logger.info("Rule '%s' added to SSE", rule.get("name", ""))


def _unregister_sse(rule: dict) -> None:
    if _sse_listener:
        _sse_listener.remove_rule(rule)
        logger.info("Rule '%s' removed from SSE", rule.get("name", ""))


def _dispatcher_action(method: str, rule: dict) -> None:
    """Call a dispatcher method by name, safely."""
    if not _dispatcher:
        return
    fn = getattr(_dispatcher, method, None)
    if not fn:
        return
    try:
        fn(rule)
    except Exception as exc:
        logger.error("Dispatcher.%s failed: %s", method, exc)
