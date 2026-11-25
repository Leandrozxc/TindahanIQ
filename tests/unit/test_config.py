"""Unit tests for application configuration and secret handling."""

from __future__ import annotations

from pathlib import Path

import pytest

from tindahaniq.config import PROJECT_ROOT, load_settings
from tindahaniq.exceptions import ConfigurationError


def test_default_settings_load_cleanly(isolated_env: Path) -> None:
    settings = load_settings(env_file=None)

    assert settings.app_name == "TindahanIQ"
    assert settings.app_env == "development"
    assert settings.log_level == "INFO"
    assert settings.currency_symbol == "₱"
    assert settings.currency_code == "PHP"
    assert settings.resolved_database_path == isolated_env
    assert settings.has_ai_api_key is False


def test_env_normalization_and_relative_db_path(
    isolated_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_ENV", "  Testing ")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    monkeypatch.setenv("CURRENCY_CODE", "php")
    monkeypatch.setenv("DATABASE_PATH", "data/custom.db")

    settings = load_settings(env_file=None)

    assert settings.app_env == "testing"
    assert settings.log_level == "DEBUG"
    assert settings.currency_code == "PHP"
    assert settings.resolved_database_path == (PROJECT_ROOT / "data" / "custom.db").resolve()


def test_blank_api_key_treated_as_unconfigured(
    isolated_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "   ")

    settings = load_settings(env_file=None)

    assert settings.gemini_api_key is None
    assert settings.has_ai_api_key is False


def test_secret_api_key_is_masked_in_representations(
    isolated_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw_secret = "AIzaSyExampleSuperSecretKeyValue12345"
    monkeypatch.setenv("GEMINI_API_KEY", raw_secret)

    settings = load_settings(env_file=None)

    assert settings.has_ai_api_key is True
    assert raw_secret not in repr(settings)
    assert raw_secret not in str(settings)


def test_invalid_configuration_raises_domain_error(
    isolated_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOG_LEVEL", "NOT_A_VALID_LEVEL")

    with pytest.raises(ConfigurationError) as exc_info:
        load_settings(env_file=None)

    assert "log_level" in exc_info.value.details.get("fields", [])
    assert "log_level" in exc_info.value.user_message
