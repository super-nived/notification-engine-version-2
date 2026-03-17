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

OP_LABELS = {
    "lt": "below",
    "gt": "above",
    "eq": "equal to",
    "lte": "at or below",
    "gte": "at or above",
}


class ThresholdBreachEngine(BaseEngine):

    @property
    def name(self) -> str:
        return "Threshold Breach"

    @property
    def description(self) -> str:
        return (
            "Checks the latest record's numeric field against a "
            "fixed limit. Alerts once when the value crosses the "
            "threshold. Resets automatically when the value "
            "recovers — so it won't spam alerts every cycle."
        )

    @property
    def use_cases(self) -> list[str]:
        return [
            "Alert when OEE drops below 60%",
            "Alert when machine temperature exceeds 90°C",
            "Alert when production count falls below target "
            "(e.g. < 100 units)",
            "Alert when error rate goes above 5%",
        ]

    @property
    def example(self) -> str:
        return (
            "Metric to monitor = OEE · "
            "Alert when value is = Less than · "
            "Threshold value = 60\n"
            "→ You get one alert when OEE falls below 60. "
            "Automatically clears when it recovers. "
            "No duplicate alerts."
        )

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
                "label": "Metric to monitor",
                "type": "text",
                "default": "oee",
            },
            {
                "key": "condition_op",
                "label": "Alert when value is",
                "type": "select",
                "options": [
                    {"value": "lt", "label": "Less than"},
                    {"value": "gt", "label": "Greater than"},
                    {"value": "eq", "label": "Equal to"},
                    {
                        "value": "lte",
                        "label": "Less than or equal",
                    },
                    {
                        "value": "gte",
                        "label": "Greater than or equal",
                    },
                ],
                "default": "lt",
            },
            {
                "key": "condition_value",
                "label": "Threshold value",
                "type": "number",
                "default": 65,
            },
        ]

    def detect(self, rule: dict, fetch_records) -> list[dict]:
        """Fetch latest record and check threshold."""
        params = rule.get("params", {})
        field = params.get("condition_field", "oee")
        op = params.get("condition_op", "lt")
        value = params.get("condition_value", 65)

        records = fetch_records(
            self.collection, filter_str="", sort="-created",
            limit=1,
        )
        if not records:
            return []
        latest = records[0]
        rec_val = latest.get(field)
        if rec_val is None:
            return []
        if _check_op(op, rec_val, value):
            return [_make_event(rule, latest, field, op, value)]
        return []

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
            return [_make_event(rule, record, field, op, value)]
        return []


def _check_op(op: str, actual, threshold) -> bool:
    op_func = OPS.get(op)
    if not op_func:
        return False
    try:
        return op_func(actual, threshold)
    except (ValueError, TypeError):
        return False


def _make_event(
    rule: dict, record: dict, field: str, op: str, threshold
) -> dict:
    actual_val = record.get(field, "N/A")
    field_label = field.replace("_", " ").upper()
    op_label = OP_LABELS.get(op, op)

    return {
        "rule_name": rule.get("name", ""),
        "rule_id": rule.get("id", ""),
        "engine": "Threshold Breach",
        "record_id": record.get("id", ""),
        "created": record.get("created", ""),
        "data": {
            "Metric": field_label,
            "Current Value": str(actual_val),
            "Threshold": f"{op_label} {threshold}",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": (
            f"{field_label} is {actual_val} — "
            f"crossed the threshold ({op_label} {threshold})"
        ),
    }
