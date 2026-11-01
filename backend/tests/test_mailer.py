import asyncio
import logging

import httpx
import pytest

from backend.app import mailer


class FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class FakeAsyncClient:
    def __init__(self, *, timeout: httpx.Timeout) -> None:
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]):
        self.url = url
        self.headers = headers
        self.payload = json
        return FakeResponse(200)


def test_send_email_uses_resend_https_api_without_smtp(monkeypatch) -> None:
    monkeypatch.setenv("RESEND_API_KEY", "unit-test-only-key")
    monkeypatch.setenv("STUDYRAG_EMAIL_FROM", "StudyRAG <noreply@example.test>")
    monkeypatch.setenv("STUDYRAG_SMTP_URL", "smtps://ignored.invalid:465")
    clients: list[FakeAsyncClient] = []

    def fake_client(*, timeout: httpx.Timeout) -> FakeAsyncClient:
        client = FakeAsyncClient(timeout=timeout)
        clients.append(client)
        return client

    monkeypatch.setattr(mailer.httpx, "AsyncClient", fake_client)
    asyncio.run(mailer.send_email("student@example.test", "Verify", "Plain-text link"))

    assert len(clients) == 1
    client = clients[0]
    assert client.url == "https://api.resend.com/emails"
    assert client.headers == {
        "Authorization": "Bearer unit-test-only-key",
        "Content-Type": "application/json",
        "User-Agent": "StudyRAG/1.0",
    }
    assert client.payload == {
        "from": "StudyRAG <noreply@example.test>",
        "to": ["student@example.test"],
        "subject": "Verify",
        "text": "Plain-text link",
    }


def test_send_email_rejects_resend_error_without_logging_secrets_or_body(monkeypatch, caplog) -> None:
    monkeypatch.setenv("RESEND_API_KEY", "unit-test-only-key")
    monkeypatch.setenv("STUDYRAG_EMAIL_FROM", "noreply@example.test")
    caplog.set_level(logging.WARNING, logger="studyrag.email")

    class RejectedAsyncClient(FakeAsyncClient):
        async def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]):
            self.url = url
            self.headers = headers
            self.payload = json
            return FakeResponse(429)

    monkeypatch.setattr(mailer.httpx, "AsyncClient", RejectedAsyncClient)
    with pytest.raises(mailer.EmailDeliveryError, match="Email delivery failed"):
        asyncio.run(mailer.send_email("student@example.test", "Verify", "Sensitive body"))

    assert "429" in caplog.text
    assert "unit-test-only-key" not in caplog.text
    assert "student@example.test" not in caplog.text
    assert "Sensitive body" not in caplog.text


def test_send_email_reports_missing_resend_configuration_safely(monkeypatch, caplog) -> None:
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.setenv("STUDYRAG_EMAIL_FROM", "noreply@example.test")
    caplog.set_level(logging.ERROR, logger="studyrag.email")

    with pytest.raises(mailer.EmailDeliveryError, match="Email delivery is not configured"):
        asyncio.run(mailer.send_email("student@example.test", "Verify", "Body"))

    assert "missing or invalid" in caplog.text
    assert "unit-test-only-key" not in caplog.text
