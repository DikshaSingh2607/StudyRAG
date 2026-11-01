from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from .config import smtp_settings

logger = logging.getLogger(__name__)


def _send(recipient: str, subject: str, body: str) -> None:
    host, port, implicit_tls, username, password, sender = smtp_settings()

    try:
        message = EmailMessage()
        message["From"] = sender
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)

        client_type = smtplib.SMTP_SSL if implicit_tls else smtplib.SMTP

        with client_type(host, port, timeout=15) as client:
            if not implicit_tls:
                client.ehlo()
                client.starttls()
                client.ehlo()

            if username:
                client.login(username, password or "")

            client.send_message(message)

    except Exception:
        logger.exception(
            "Email delivery failed to %s via %s:%s",
            recipient,
            host,
            port,
        )
        raise


async def send_email(recipient: str, subject: str, body: str) -> None:
    await asyncio.to_thread(_send, recipient, subject, body)
