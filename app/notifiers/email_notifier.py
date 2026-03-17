"""Email Notifier — standalone plugin.

Sends one summary HTML email per rule execution.
Reuses a single SMTP connection for all targets.
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
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.warning("SMTP not configured, skipping email")
        return

    html_body = build_summary_html(rule, events)
    text_body = build_summary_plain_text(rule, events)
    subject = _build_subject(rule, events)
    from_addr = settings.EMAIL_FROM or settings.SMTP_USER

    try:
        with smtplib.SMTP(
            settings.SMTP_HOST, settings.SMTP_PORT
        ) as smtp:
            if settings.SMTP_TLS:
                smtp.starttls()
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)

            for target in targets:
                try:
                    msg = _build_message(
                        from_addr, target, subject,
                        text_body, html_body,
                    )
                    smtp.send_message(msg)
                    logger.info(
                        "Email sent to %s for rule '%s' "
                        "(%d event(s))",
                        target,
                        rule.get("name", ""),
                        len(events),
                    )
                except smtplib.SMTPException as exc:
                    logger.error(
                        "Email to %s failed: %s", target, exc
                    )
    except Exception as exc:
        logger.error(
            "SMTP connection failed for rule '%s': %s",
            rule.get("name", ""),
            exc,
        )


def _build_subject(rule: dict, events: list[dict]) -> str:
    count = len(events)
    rule_name = rule.get("name", "Alert")
    if count == 1:
        return (
            f"[Alert] {rule_name} — "
            f"{events[0].get('message', 'Event detected')}"
        )
    return f"[Alert] {rule_name} — {count} event(s) detected"


def _build_message(
    from_addr: str,
    to: str,
    subject: str,
    text_body: str,
    html_body: str,
) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["From"] = from_addr
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))
    return msg
