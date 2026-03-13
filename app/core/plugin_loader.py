"""Auto-discovery for engines, notifiers, and datasources.

Scans directories for Python files, imports them, and collects
subclasses of BaseEngine / BaseNotifier / BaseDataSource.
"""

import importlib
import logging
import pkgutil
from pathlib import Path

from app.core.base_engine import BaseEngine
from app.core.base_notifier import BaseNotifier
from app.core.base_datasource import BaseDataSource

logger = logging.getLogger(__name__)


def discover_engines(package_path: str) -> dict[str, BaseEngine]:
    """Scan a package dir and return {name: instance} for engines."""
    return _discover(package_path, BaseEngine, "name")


def discover_notifiers(package_path: str) -> dict[str, BaseNotifier]:
    """Scan a package dir and return {channel_name: instance}."""
    return _discover(package_path, BaseNotifier, "channel_name")


def discover_datasources(
    package_path: str,
) -> dict[str, BaseDataSource]:
    """Scan a package dir and return {source_type: instance}."""
    return _discover(package_path, BaseDataSource, "source_type")


def _discover(
    package_path: str, base_cls: type, key_attr: str
) -> dict:
    """Import all modules in a package and collect subclasses."""
    registry: dict = {}
    package = importlib.import_module(package_path)
    pkg_dir = Path(package.__file__).parent

    for finder, module_name, _ in pkgutil.iter_modules([str(pkg_dir)]):
        full_name = f"{package_path}.{module_name}"
        try:
            mod = importlib.import_module(full_name)
        except Exception as exc:
            logger.error("Failed to import %s: %s", full_name, exc)
            continue

        _collect_from_module(mod, base_cls, key_attr, registry)

    logger.info(
        "Discovered %d %s(s): %s",
        len(registry),
        base_cls.__name__,
        list(registry.keys()),
    )
    return registry


def _collect_from_module(
    mod, base_cls: type, key_attr: str, registry: dict
) -> None:
    """Find and instantiate all subclasses of base_cls in a module."""
    for attr_name in dir(mod):
        cls = getattr(mod, attr_name)
        if not _is_valid_subclass(cls, base_cls):
            continue
        try:
            instance = cls()
            key = getattr(instance, key_attr)
            registry[key] = instance
        except Exception as exc:
            logger.error("Failed to instantiate %s: %s", cls, exc)


def _is_valid_subclass(cls, base_cls: type) -> bool:
    """Check if cls is a non-abstract subclass of base_cls."""
    return (
        isinstance(cls, type)
        and issubclass(cls, base_cls)
        and cls is not base_cls
        and not getattr(cls, "__abstractmethods__", None)
    )
