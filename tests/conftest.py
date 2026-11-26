"""Shared pytest fixtures for isolated environment and storage testing."""

from __future__ import annotations

from pathlib import Path

import pytest

ENV_KEYS = (
    "APP_NAME",
    "APP_ENV",
    "LOG_LEVEL",
    "STORE_NAME",
    "CURRENCY_SYMBOL",
    "CURRENCY_CODE",
    "DATABASE_PATH",
    "TURSO_DATABASE_URL",
    "TURSO_AUTH_TOKEN",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "OPENAI_MAX_COMPLETION_TOKENS",
)


@pytest.fixture
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Clear TindahanIQ environment variables and point storage to a temporary directory."""
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "data" / "test_tindahaniq.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    return db_path
