"""Email template builder — renders alert events as HTML emails.

Converts event dicts into user-friendly HTML and plain-text.
No raw JSON, no technical field names, no internal IDs.
"""

from datetime import datetime
from typing import Any

# Keys excluded from the data table — internal / technical fields
_HIDDEN_KEYS = frozenset({
    "id", "created", "updated",
    "collectionId", "collectionName", "expand",
    "rule_name", "rule_id", "engine", "record_id",
    "record", "timestamp", "message", "created",
})

# Human-friendly labels for common data field keys
_FIELD_LABELS: dict[str, str] = {
    "machine_name": "Machine",
    "machine_id": "Machine ID",
    "reason_code": "Reason",
    "start_date": "Start Time",
    "end_date": "End Time",
    "duration": "Duration",
    "oee": "OEE (%)",
    "shift": "Shift",
    "job_status": "Job Status",
    "jobStatus": "Job Status",
    "isScheduled": "Scheduled",
    "displayName": "Display Name",
    "status": "Status",
    "customerApproved": "Customer Approved",
    "jobName": "Job Name",
    "jobNumber": "Job Number",
    "workCenter": "Work Center",
    "downtime_reason": "Downtime Reason",
    "downtime_type": "Downtime Type",
    "operator": "Operator",
    "line_name": "Line",
    "product_name": "Product",
    "batch_number": "Batch Number",
}


# ── Helpers ──────────────────────────────────────────────────


def _label(key: str) -> str:
    if key in _FIELD_LABELS:
        return _FIELD_LABELS[key]
    return key.replace("_", " ").replace("-", " ").title()


def _format_value(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def _format_timestamp(ts: str) -> str:
    if not ts:
        return "—"
    try:
        dt = datetime.fromisoformat(
            ts.replace("Z", "+00:00")
        )
        return dt.strftime("%b %d, %Y at %I:%M %p UTC")
    except (ValueError, TypeError):
        return ts


def _visible_fields(data: dict) -> list[tuple[str, str]]:
    if not isinstance(data, dict):
        return []
    return [
        (_label(k), _format_value(v))
        for k, v in data.items()
        if k not in _HIDDEN_KEYS
    ]


def _display_fields(data: dict) -> list[tuple[str, str]]:
    """Extract display fields — keys are already labels."""
    if not isinstance(data, dict):
        return []
    return [
        (k, _format_value(v))
        for k, v in data.items()
        if k not in _HIDDEN_KEYS
    ]


def _esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ── Public API ───────────────────────────────────────────────


def build_plain_text(
    rule: dict, event: dict
) -> str:
    """Plain-text fallback for email clients."""
    rule_name = rule.get("name", "Alert")
    message = event.get("message", "")
    data = event.get("data", {})
    time_str = _format_timestamp(
        event.get("timestamp", event.get("triggered_at", ""))
    )

    lines = [f"Alert: {rule_name}", "", message, ""]
    for label, value in _display_fields(data):
        lines.append(f"  {label}: {value}")
    lines.append("")
    lines.append(f"Time: {time_str}")
    lines.append("")
    lines.append("— iApps Notification Engine")
    return "\n".join(lines)


def build_html(rule: dict, event: dict) -> str:
    """Professional HTML email from rule + event."""
    rule_name = rule.get("name", "Alert")
    engine = rule.get("engine", "")
    message = event.get("message", "")
    data = event.get("data", {})
    time_str = _format_timestamp(
        event.get("timestamp", event.get("triggered_at", ""))
    )

    data_rows = _build_data_rows(data)
    data_table = _build_data_table(data_rows)

    return (
        "<!DOCTYPE html>"
        "<html><head>"
        '<meta charset="UTF-8">'
        '<meta name="viewport" '
        'content="width=device-width,initial-scale=1.0">'
        "</head>"
        '<body style="margin:0;padding:0;background:#f5f6fa;'
        "font-family:'Segoe UI',Arial,Helvetica,sans-serif\">"
        '<table width="100%" cellpadding="0" cellspacing="0" '
        'style="background:#f5f6fa;padding:32px 0">'
        '<tr><td align="center">'
        + _card_html(rule_name, engine, message, data_table, time_str)
        + _footer_hint()
        + "</td></tr></table>"
        "</body></html>"
    )


def _build_data_rows(data: dict) -> str:
    rows = ""
    for label, value in _display_fields(data):
        rows += (
            "<tr>"
            '<td style="padding:10px 16px;font-size:13px;'
            "color:#6b7280;border-bottom:1px solid #f0f0f0;"
            'white-space:nowrap;font-weight:500">'
            f"{_esc(label)}</td>"
            '<td style="padding:10px 16px;font-size:13px;'
            'color:#1e2535;border-bottom:1px solid #f0f0f0">'
            f"{_esc(value)}</td>"
            "</tr>"
        )
    return rows


def _build_data_table(rows: str) -> str:
    if not rows:
        return ""
    return (
        '<table width="100%" cellpadding="0" cellspacing="0" '
        'style="border:1px solid #e5e7eb;border-radius:8px;'
        'overflow:hidden;border-collapse:separate;'
        'margin-top:20px">'
        f"<tbody>{rows}</tbody></table>"
    )


def _card_html(
    rule_name: str,
    engine: str,
    message: str,
    data_table: str,
    time_str: str,
) -> str:
    return (
        '<table width="560" cellpadding="0" cellspacing="0" '
        'style="background:#ffffff;border-radius:12px;'
        "overflow:hidden;"
        'box-shadow:0 2px 8px rgba(0,0,0,0.06)">'
        # Header
        '<tr><td style="background:#e15a2d;padding:24px 32px">'
        '<table width="100%" cellpadding="0" cellspacing="0">'
        "<tr><td>"
        '<div style="font-size:18px;font-weight:700;'
        'color:#ffffff;letter-spacing:0.3px">'
        "Alert Notification</div>"
        '<div style="font-size:12px;'
        'color:rgba(255,255,255,0.80);margin-top:4px">'
        f"{_esc(rule_name)}</div>"
        "</td>"
        '<td align="right" style="vertical-align:top">'
        '<div style="background:rgba(255,255,255,0.20);'
        "border-radius:20px;padding:5px 14px;font-size:11px;"
        'color:#ffffff;font-weight:600;display:inline-block">'
        f"{_esc(engine)}</div>"
        "</td></tr></table>"
        "</td></tr>"
        # Body
        '<tr><td style="padding:28px 32px 16px">'
        '<div style="background:#fef3f0;'
        "border-left:4px solid #e15a2d;"
        "border-radius:0 8px 8px 0;"
        'padding:14px 18px;margin-bottom:4px">'
        '<div style="font-size:14px;color:#1e2535;'
        f'line-height:1.6;font-weight:500">{_esc(message)}'
        "</div></div>"
        f"{data_table}"
        "</td></tr>"
        # Footer
        '<tr><td style="padding:0 32px 28px">'
        '<table width="100%" cellpadding="0" cellspacing="0" '
        'style="border-top:1px solid #f0f0f0;padding-top:16px">'
        "<tr>"
        '<td style="font-size:11px;color:#9ca3af;'
        f'line-height:1.6">Triggered on {_esc(time_str)}</td>'
        '<td align="right" style="font-size:11px;'
        'color:#9ca3af">iApps Notification Engine</td>'
        "</tr></table>"
        "</td></tr>"
        "</table>"
    )


def _footer_hint() -> str:
    return (
        '<div style="text-align:center;margin-top:20px;'
        'font-size:11px;color:#9ca3af;line-height:1.5">'
        "This is an automated alert from iApps "
        "Notification Engine.<br>"
        "To stop receiving these, disable the rule or "
        "remove your email from targets."
        "</div>"
    )
