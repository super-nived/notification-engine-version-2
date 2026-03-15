"""Email Notifier — standalone plugin.

Sends one summary HTML email per rule execution.
Runs in a background thread to avoid blocking.
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from threading import Thread

from app.core.base_notifier import BaseNotifier
from app.core.settings import settings
from app.notifiers.email_template import (
    build_summary_html,
    build_summary_plain_text,
)

logger = logging.getLogger(__name__)


class EmailNotifier(BaseNotifier):

    @property
    def channel_name(self) -> str:
        return "Email"

    def send(self, rule: dict, events: list[dict]) -> None:
        """Send one summary email to all targets."""
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
    msg = _build_message(rule, events)
    for target in targets:
        try:
            _smtp_send(target, msg)
            logger.info(
                "Email sent to %s for rule '%s' (%d event(s))",
                target,
                rule.get("name", ""),
                len(events),
            )
        except Exception as exc:
            logger.error(
                "Email to %s failed: %s", target, exc
            )


def _build_message(
    rule: dict, events: list[dict]
) -> MIMEMultipart:
    count = len(events)
    rule_name = rule.get("name", "Alert")

    if count == 1:
        subject = (
            f"[Alert] {rule_name} — "
            f"{events[0].get('message', 'Event detected')}"
        )
    else:
        subject = (
            f"[Alert] {rule_name} — "
            f"{count} event(s) detected"
        )

    msg = MIMEMultipart("alternative")
    msg["From"] = settings.EMAIL_FROM or settings.SMTP_USER
    msg["Subject"] = subject

    msg.attach(
        MIMEText(
            build_summary_plain_text(rule, events), "plain"
        )
    )
    msg.attach(
        MIMEText(build_summary_html(rule, events), "html")
    )
    return msg


def _smtp_send(to: str, msg: MIMEMultipart) -> None:
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.warning("SMTP not configured, skipping %s", to)
        return

    send_msg = MIMEMultipart("alternative")
    for key in ("From", "Subject"):
        send_msg[key] = msg[key]
    send_msg["To"] = to
    for part in msg.get_payload():
        send_msg.attach(part)

    with smtplib.SMTP(
        settings.SMTP_HOST, settings.SMTP_PORT
    ) as smtp:
        if settings.SMTP_TLS:
            smtp.starttls()
        smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.send_message(send_msg)
