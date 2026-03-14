"""Rules Router — REST API endpoints.

No business logic here. All logic lives in service.py.
Returns standardized success()/error() responses.
"""

import logging

from fastapi import APIRouter

from app.features.rules.schema import (
    RuleCreate,
    RuleToggle,
    RuleUpdate,
)
from app.features.rules import service
from app.features.rules.service import ServiceError
from app.utils.response import error, success

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rules", tags=["rules"])


@router.get("")
def list_rules():
    return _handle(
        lambda: success(
            data=service.list_rules(),
            message="Rules fetched",
        )
    )


@router.get("/engines")
def list_engines():
    return _handle(
        lambda: success(
            data=service.get_engine_registry(),
            message="Engine registry",
        )
    )


@router.get("/logs")
def list_logs(rule_name: str | None = None):
    return _handle(
        lambda: success(
            data=service.get_execution_logs(rule_name),
            message="Execution logs",
        )
    )


@router.get("/{rule_id}")
def get_rule(rule_id: str):
    return _handle(lambda: success(data=service.get_rule(rule_id)))


@router.post("")
def create_rule(body: RuleCreate):
    return _handle(
        lambda: success(
            data=service.create_rule(body.model_dump()),
            message="Rule created successfully",
            status_code=201,
        )
    )


@router.patch("/{rule_id}")
def update_rule(rule_id: str, body: RuleUpdate):
    data = body.model_dump(exclude_none=True)
    return _handle(
        lambda: success(
            data=service.update_rule(rule_id, data),
            message="Rule updated successfully",
        )
    )


@router.patch("/{rule_id}/toggle")
def toggle_rule(rule_id: str, body: RuleToggle):
    state = "enabled" if body.enabled else "disabled"
    return _handle(
        lambda: success(
            data=service.toggle_rule(rule_id, body.enabled),
            message=f"Rule {state} successfully",
        )
    )


@router.delete("/{rule_id}")
def delete_rule(rule_id: str):
    return _handle(
        lambda: (
            service.delete_rule(rule_id)
            or success(message="Rule deleted successfully")
        )
    )


def _handle(fn):
    """Wrap endpoint logic with error handling.
    Catches ServiceError for user-friendly messages,
    and generic exceptions as fallback."""
    try:
        return fn()
    except ServiceError as exc:
        logger.warning("Service error: %s", exc)
        return error(
            message=str(exc),
            status_code=exc.status_code,
        )
    except Exception as exc:
        logger.error("Unexpected error: %s", exc, exc_info=True)
        return error(
            message="An unexpected error occurred. Please try again.",
            status_code=500,
        )
