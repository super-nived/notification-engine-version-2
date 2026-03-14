"""Engine & Notifier Registry — powered by auto-discovery.

At startup, scans app/engines/ and app/notifiers/ for plugins.
Provides lookup helpers used by the rest of the system.
"""

import logging

from app.core.base_engine import BaseEngine
from app.core.base_notifier import BaseNotifier
from app.core.base_datasource import BaseDataSource
from app.core.plugin_loader import (
    discover_datasources,
    discover_engines,
    discover_notifiers,
)

logger = logging.getLogger(__name__)

_engines: dict[str, BaseEngine] = {}
_notifiers: dict[str, BaseNotifier] = {}
_datasources: dict[str, BaseDataSource] = {}


def load_all_plugins() -> None:
    """Discover and register all plugins. Call once at startup."""
    global _engines, _notifiers, _datasources
    _engines = discover_engines("app.engines")
    _notifiers = discover_notifiers("app.notifiers")
    _datasources = discover_datasources("app.datasources")


def get_engine(engine_name: str) -> BaseEngine:
    """Get engine instance by name. Raises ValueError if unknown."""
    engine = _engines.get(engine_name)
    if engine is None:
        available = list(_engines.keys())
        raise ValueError(
            f"Unknown engine '{engine_name}'. "
            f"Available: {available}"
        )
    return engine


def get_engine_config(engine_name: str) -> dict:
    """Backward-compatible: return engine config as dict."""
    engine = get_engine(engine_name)
    return {
        "collection": engine.collection,
        "condition_type": engine.condition_type,
        "editable_params": engine.editable_params,
    }


def get_default_params(engine_name: str) -> dict:
    """Get default param values for an engine."""
    engine = get_engine(engine_name)
    return {
        p["key"]: p["default"] for p in engine.editable_params
    }


def get_engine_registry_dict() -> dict:
    """Return full registry as serializable dict for the API.

    Only user-facing fields are exposed. Internal fields like
    collection, condition_type stay server-side.
    """
    return {
        name: {
            "description": eng.description,
            "use_cases": eng.use_cases,
            "example": eng.example,
            "editable_params": eng.editable_params,
        }
        for name, eng in _engines.items()
    }


def get_notifiers_for_rule(rule: dict) -> list[BaseNotifier]:
    """Return all notifiers that should fire for this rule."""
    return [n for n in _notifiers.values() if n.can_handle(rule)]


def get_datasource(source_type: str = "pocketbase") -> BaseDataSource:
    """Get datasource by type. Defaults to pocketbase."""
    ds = _datasources.get(source_type)
    if ds is None:
        available = list(_datasources.keys())
        raise ValueError(
            f"Unknown datasource '{source_type}'. "
            f"Available: {available}"
        )
    return ds


def rule_is_as_it_occurs(rule: dict) -> bool:
    """Check the rule's user-selected frequency."""
    return rule.get("frequency", "") == "As It Occurs"


def rule_is_scheduled(rule: dict) -> bool:
    """Any frequency other than 'As It Occurs' means scheduled."""
    freq = rule.get("frequency", "")
    return freq != "" and freq != "As It Occurs"
