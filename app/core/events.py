"""Application lifespan — startup and shutdown hooks.

Authenticates PocketBase, loads plugins, and starts
both the Dispatcher and SSE Listener.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.pb_client import authenticate
from app.db.pb_repositories import get_enabled_rules
from app.engine.registry import load_all_plugins, rule_is_as_it_occurs
from app.engine.scheduler import Dispatcher
from app.engine.sse_listener import SSEListener
from app.features.rules.service import set_dispatcher, set_sse_listener
from app.notifiers.inapp_notifier import set_websocket_manager
from app.notifiers.websocket_manager import ws_manager

logger = logging.getLogger(__name__)

dispatcher = Dispatcher()
sse_listener = SSEListener()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    load_all_plugins()

    _authenticate()
    _wire_dependencies()
    _load_sse_rules()

    sse_listener.start()
    dispatcher.start()
    logger.info("Notification engine started")

    yield

    dispatcher.stop()
    sse_listener.stop()
    logger.info("Notification engine stopped")


def _configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    logging.getLogger("app.engine.sse_listener").setLevel(
        logging.DEBUG
    )


def _authenticate():
    try:
        authenticate()
    except Exception as exc:
        logger.error("PocketBase auth failed: %s", exc)


def _wire_dependencies():
    set_websocket_manager(ws_manager)
    set_dispatcher(dispatcher)
    set_sse_listener(sse_listener)


def _load_sse_rules():
    try:
        rules = get_enabled_rules()
        sse_rules = [r for r in rules if rule_is_as_it_occurs(r)]
        sse_listener.load_rules(sse_rules)
    except Exception as exc:
        logger.error("Failed to load SSE rules: %s", exc)
