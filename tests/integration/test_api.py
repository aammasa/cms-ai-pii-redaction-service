"""
Integration tests — hit the real FastAPI app with TestClient.
These tests load actual Presidio models and require the full environment.
Mark with @pytest.mark.integration; run via: pytest tests/integration/ -v
"""

import pytest
from fastapi.testclient import TestClient

from src.api import api
from src.util.auth import verify_api_key

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def client():
    api.dependency_overrides[verify_api_key] = lambda: None
    yield TestClient(api)
    api.dependency_overrides.clear()


def test_health_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_entities_returns_list(client):
    response = client.get("/entities")
    assert response.status_code == 200
    assert len(response.json()["entities"]) > 0


def test_languages_includes_english(client):
    response = client.get("/languages")
    assert response.status_code == 200
    langs = {l["code"]: l for l in response.json()["languages"]}
    assert "en" in langs
    assert langs["en"]["installed"] is True


def test_redact_replaces_email(client):
    response = client.post("/redact", json={
        "text": "Send reports to alice@example.com",
        "language": "en",
        "operator": "replace",
    })
    assert response.status_code == 200
    data = response.json()
    assert "alice@example.com" not in data["redacted_text"]
    assert "EMAIL_ADDRESS" in data["entity_counts"]


def test_redact_mask_operator(client):
    response = client.post("/redact", json={
        "text": "Email: bob@example.com",
        "language": "en",
        "operator": "mask",
    })
    assert response.status_code == 200
    assert "*" in response.json()["redacted_text"]


def test_redact_invalid_operator_returns_422(client):
    response = client.post("/redact", json={
        "text": "some text",
        "operator": "invalid_op",
    })
    assert response.status_code == 422


def test_process_file_txt(client):
    response = client.post(
        "/process",
        files={"file": ("test.txt", b"My name is John Smith and email is test@test.com", "text/plain")},
    )
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert "detected_language" in data
    assert data["file_type"] == "txt"


def test_audit_logs_returns_list(client):
    response = client.get("/audit/logs")
    assert response.status_code == 200
    assert "events" in response.json()


def test_audit_stats_has_required_fields(client):
    response = client.get("/audit/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "retention_region" in data


def test_audit_verify_returns_valid(client):
    response = client.get("/audit/verify")
    assert response.status_code == 200
    data = response.json()
    assert "valid" in data


def test_audit_purge_dry_run(client):
    response = client.post("/audit/purge?dry_run=true")
    assert response.status_code == 200
    assert response.json()["dry_run"] is True
