"""Shared pytest fixtures."""

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def api_client():
    """TestClient with API key auth bypassed."""
    from src.api import api
    from src.util.auth import verify_api_key

    api.dependency_overrides[verify_api_key] = lambda: None
    client = TestClient(api)
    yield client
    api.dependency_overrides.clear()


@pytest.fixture()
def auth_headers():
    """Headers carrying a valid test API key."""
    return {"X-API-Key": "test-key"}


@pytest.fixture()
def audit_log_path(tmp_path: Path) -> Path:
    """Temporary audit log file; patches the module-level path."""
    log_file = tmp_path / "test_audit.log"
    return log_file


@pytest.fixture()
def mock_env_vars(monkeypatch):
    """Helper fixture — call with a dict to set env vars for the test."""
    def _set(mapping: dict[str, str]):
        for key, value in mapping.items():
            monkeypatch.setenv(key, value)
    return _set
