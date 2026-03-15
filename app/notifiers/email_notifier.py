"""Email Notifier — standalone plugin.

Sends professional HTML email notifications via SMTP.
Runs in a background thread to avoid blocking.
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from threading import Thread

from app.core.base_notifier import BaseNotifier
from app.core.settings import settings
from app.notifiers.email_template import build_html, build_plain_text

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
    for event in events:
        for target in targets:
            try:
                _send_one(target, rule, event)
            except Exception as exc:
                logger.error(
                    "Email to %s failed: %s", target, exc
                )


def _send_one(
    to: str, rule: dict, event: dict
) -> None:
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.warning("SMTP not configured, skipping %s", to)
        return

    msg = _build_message(to, rule, event)
    _smtp_send(to, msg)
    logger.info(
        "Email sent to %s for rule '%s'",
        to,
        rule.get("name", ""),
    )


def _build_message(
    to: str, rule: dict, event: dict
) -> MIMEMultipart:
    message = event.get("message", "")
    subject = f"[Alert] {rule.get('name', '')} — {message}"

    msg = MIMEMultipart("alternative")
    msg["From"] = settings.EMAIL_FROM or settings.SMTP_USER
    msg["To"] = to
    msg["Subject"] = subject

    msg.attach(
        MIMEText(build_plain_text(rule, event), "plain")
    )
    msg.attach(MIMEText(build_html(rule, event), "html"))
    return msg


def _smtp_send(to: str, msg: MIMEMultipart) -> None:
    with smtplib.SMTP(
        settings.SMTP_HOST, settings.SMTP_PORT
    ) as smtp:
        if settings.SMTP_TLS:
            smtp.starttls()
        smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.send_message(msg)
