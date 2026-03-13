"""Threshold Breach Engine — standalone plugin.

Detects when a numeric field breaches a configured threshold.
Supports operators: lt, gt, eq, lte, gte.
"""

from datetime import datetime, timezone

from app.core.base_engine import BaseEngine

OPS = {
    "lt": lambda a, b: float(a) < float(b),
    "gt": lambda a, b: float(a) > float(b),
    "eq": lambda a, b: str(a) == str(b),
    "lte": lambda a, b: float(a) <= float(b),
    "gte": lambda a, b: float(a) >= float(b),
}


class ThresholdBreachEngine(BaseEngine):

    @property
    def name(self) -> str:
        return "Threshold Breach"

    @property
    def collection(self) -> str:
        return "production_metrics"

    @property
    def condition_type(self) -> str:
        return "threshold"

    @property
    def editable_params(self) -> list[dict]:
        return [
            {
                "key": "condition_field",
                "label": "Field",
                "type": "text",
                "default": "oee",
            },
            {
                "key": "condition_op",
                "label": "Operator",
                "type": "select",
                "options": ["lt", "gt", "eq", "lte", "gte"],
                "default": "lt",
            },
            {
                "key": "condition_value",
                "label": "Threshold",
                "type": "number",
                "default": 65,
            },
        ]

    def detect(self, rule: dict, fetch_records) -> list[dict]:
        """Fetch all records and check threshold."""
        params = rule.get("params", {})
        field = params.get("condition_field", "oee")
        op = params.get("condition_op", "lt")
        value = params.get("condition_value", 65)

        records = fetch_records(
            self.collection, filter_str="", sort="-created"
        )
        return self._filter_breaches(rule, records, field, op, value)

    def evaluate(self, rule: dict, record: dict) -> list[dict]:
        """Check a single SSE record against threshold."""
        params = rule.get("params", {})
        field = params.get("condition_field", "oee")
        op = params.get("condition_op", "lt")
        value = params.get("condition_value", 65)

        record_val = record.get(field)
        if record_val is None:
            return []
        if _check_op(op, record_val, value):
            return [_make_event(rule, record)]
        return []

    def _filter_breaches(
        self, rule, records, field, op, value
    ) -> list[dict]:
        events = []
        for rec in records:
            rec_val = rec.get(field)
            if rec_val is None:
                continue
            if _check_op(op, rec_val, value):
                events.append(_make_event(rule, rec))
        return events


def _check_op(op: str, actual, threshold) -> bool:
    op_func = OPS.get(op)
    if not op_func:
        return False
    try:
        return op_func(actual, threshold)
    except (ValueError, TypeError):
        return False


def _make_event(rule: dict, record: dict) -> dict:
    return {
        "rule_name": rule.get("name", ""),
        "rule_id": rule.get("id", ""),
        "engine": rule.get("engine", ""),
        "record_id": record.get("id", ""),
        "record": record,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": (
            f"[{rule.get('engine', '')}] Rule "
            f"'{rule.get('name', '')}' triggered on "
            f"record {record.get('id', 'N/A')}"
        ),
    }
