from fastapi.testclient import TestClient

from backend.app.config import database_url
from backend.app.google_oauth import credentials
from backend.app.main import app
from backend.app.rate_limit import bucket_digest, client_address


def test_google_provider_is_disabled_without_both_credentials(monkeypatch) -> None:
    monkeypatch.delenv("STUDYRAG_GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("STUDYRAG_GOOGLE_CLIENT_SECRET", raising=False)
    assert credentials() is None


def test_google_provider_is_not_partially_enabled(monkeypatch) -> None:
    monkeypatch.setenv("STUDYRAG_GOOGLE_CLIENT_ID", "client-id-configured-for-this-test")
    monkeypatch.delenv("STUDYRAG_GOOGLE_CLIENT_SECRET", raising=False)
    assert credentials() is None


def test_provider_discovery_reports_no_google_option_without_configuration(monkeypatch) -> None:
    monkeypatch.delenv("STUDYRAG_GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("STUDYRAG_GOOGLE_CLIENT_SECRET", raising=False)
    response = TestClient(app).get("/api/auth/providers")
    assert response.status_code == 200
    assert response.json() == {"google": False}


def test_google_flow_rejects_post_without_double_submit_csrf_token() -> None:
    response = TestClient(app).post("/api/auth/google/start")
    assert response.status_code == 403


def test_database_url_uses_asyncpg_and_translates_managed_tls(monkeypatch) -> None:
    monkeypatch.setenv("STUDYRAG_POSTGRES_URL", "postgresql://study_user:private-test-value@db.invalid/study?sslmode=require")
    normalized = database_url()
    assert normalized.startswith("postgresql+asyncpg://")
    assert "ssl=require" in normalized
    assert "sslmode=" not in normalized


def test_database_url_preserves_full_certificate_verification(monkeypatch) -> None:
    monkeypatch.setenv("STUDYRAG_POSTGRES_URL", "postgresql://study_user:private-test-value@db.invalid/study?sslmode=verify-full")
    normalized = database_url()
    assert "ssl=verify-full" in normalized


def test_forwarded_ip_is_ignored_from_an_untrusted_peer() -> None:
    assert client_address("198.51.100.9", "203.0.113.42", ("127.0.0.1/32",)) == "198.51.100.9"


def test_trusted_proxy_chain_uses_the_first_untrusted_hop() -> None:
    address = client_address(
        "127.0.0.1",
        "203.0.113.42, 10.1.2.3",
        ("127.0.0.1/32", "10.0.0.0/8"),
    )
    assert address == "203.0.113.42"


def test_rate_limit_bucket_hides_subject_and_address() -> None:
    digest = bucket_digest("login", "student@example.test", "198.51.100.10", b"unit-test-key")
    assert len(digest) == 64
    assert "student" not in digest and "198.51" not in digest
    assert digest != bucket_digest("login", "other@example.test", "198.51.100.10", b"unit-test-key")
