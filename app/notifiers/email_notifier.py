"""Email Notifier — standalone plugin.

Sends email notifications via SMTP to rule targets.
Runs in a background thread to avoid blocking.
"""

import logging
import smtplib
from email.mime.text import MIMEText
from threading import Thread

from app.core.base_notifier import BaseNotifier
from app.core.settings import settings

logger = logging.getLogger(__name__)


class EmailNotifier(BaseNotifier):

    @property
    def channel_name(self) -> str:
        return "Email"

    def send(self, rule: dict, events: list[dict]) -> None:
        """Send emails to all targets in a background thread."""
        targets = _extract_email_targets(rule)
        if not targets:
            return

        Thread(
            target=_send_all,
            args=(rule, events, targets),
            daemon=True,
        ).start()


def _extract_email_targets(rule: dict) -> list[str]:
    targets = rule.get("targets", [])
    return [t for t in targets if "@" in t]


def _send_all(
    rule: dict, events: list[dict], targets: list[str]
) -> None:
    for target in targets:
        try:
            _send_one(target, rule, events)
        except Exception as exc:
            logger.error(
                "Email to %s failed: %s", target, exc
            )


def _send_one(
    to: str, rule: dict, events: list[dict]
) -> None:
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.warning("SMTP not configured, skipping %s", to)
        return

    msg = _build_message(to, rule, events)
    _smtp_send(to, msg)
    logger.info(
        "Email sent to %s for rule '%s'",
        to,
        rule.get("name", ""),
    )


def _build_message(
    to: str, rule: dict, events: list[dict]
) -> MIMEText:
    subject = (
        f"[Notification] {rule.get('name', '')} "
        f"- {len(events)} event(s)"
    )
    body_lines = [
        f"Rule: {rule.get('name', '')}",
        f"Engine: {rule.get('engine', '')}",
        f"Events: {len(events)}",
        "",
    ]
    for i, ev in enumerate(events, 1):
        body_lines.append(f"--- Event {i} ---")
        body_lines.append(ev.get("message", ""))
        body_lines.append("")

    msg = MIMEText("\n".join(body_lines))
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_USER
    msg["To"] = to
    return msg


def _smtp_send(to: str, msg: MIMEText) -> None:
    with smtplib.SMTP(
        settings.SMTP_HOST, settings.SMTP_PORT
    ) as smtp:
        smtp.starttls()
        smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.send_message(msg)
