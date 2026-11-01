from __future__ import annotations

import logging

import httpx

from .config import resend_settings

logger = logging.getLogger("studyrag.email")
RESEND_EMAILS_URL = "https://api.resend.com/emails"


class EmailDeliveryError(RuntimeError):
    """Safe provider failure exposed to application handlers."""


async def send_email(recipient: str, subject: str, body: str) -> None:
    try:
        api_key, sender = resend_settings()
    except RuntimeError:
        logger.error("email delivery configuration is missing or invalid")
        raise EmailDeliveryError("Email delivery is not configured") from None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "StudyRAG/1.0",
    }
    payload = {
        "from": sender,
        "to": [recipient],
        "subject": subject,
        "text": body,
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0)) as client:
            response = await client.post(RESEND_EMAILS_URL, headers=headers, json=payload)
    except httpx.TimeoutException:
        logger.warning("Resend email request timed out")
        raise EmailDeliveryError("Email delivery failed") from None
    except httpx.RequestError as exc:
        logger.warning("Resend email request failed (%s)", type(exc).__name__)
        raise EmailDeliveryError("Email delivery failed") from None

    if not 200 <= response.status_code < 300:
        logger.warning("Resend email API returned HTTP %d", response.status_code)
        raise EmailDeliveryError("Email delivery failed")
