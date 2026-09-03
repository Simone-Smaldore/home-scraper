"""M0 smoke tests: no database required, they only pin the contract of /api/health."""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.db import normalize_database_url, redact_dsn
from app.main import app


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_health_reports_missing_database_without_crashing(monkeypatch):
    monkeypatch.setattr(
        "app.config.Settings",
        lambda: Settings(_env_file=None, database_url="", environment="test"),
    )

    response = TestClient(app).get("/api/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"] == "not_configured"
    assert body["environment"] == "test"


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("postgres://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
        (
            "postgresql://u:p@host/db?sslmode=require",
            "postgresql+psycopg://u:p@host/db?sslmode=require",
        ),
        ("postgresql+psycopg://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
    ],
)
def test_normalize_database_url_targets_psycopg3(given, expected):
    assert normalize_database_url(given) == expected


def test_redact_dsn_hides_the_password_but_keeps_the_rest():
    message = (
        "OperationalError: connection to postgresql+psycopg://neondb_owner:s3cret@"
        "ep-x-pooler.eu-central-1.aws.neon.tech/neondb failed: timeout expired"
    )
    redacted = redact_dsn(message)
    assert "s3cret" not in redacted
    assert redacted.startswith("OperationalError: connection to postgresql://[rimosso]")
    assert redacted.endswith("failed: timeout expired")


def test_gemini_models_accept_a_comma_separated_string():
    settings = Settings(_env_file=None, gemini_models="a, b,c,")
    assert settings.gemini_models == ["a", "b", "c"]
