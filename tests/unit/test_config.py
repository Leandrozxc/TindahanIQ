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
    monkeypatch.setenv("OPENAI_API_KEY", "   ")

    settings = load_settings(env_file=None)

    assert settings.openai_api_key is None
    assert settings.has_ai_api_key is False


def test_secret_api_key_is_masked_in_representations(
    isolated_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw_secret = "sk-cal-ExampleSuperSecretKeyValue12345"
    monkeypatch.setenv("OPENAI_API_KEY", raw_secret)

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


def test_turso_credentials_load_and_mask_auth_token(
    isolated_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw_token = "eyJhbGciOiJFZERTQSJ9.super_secret_turso_token"
    monkeypatch.setenv("TURSO_DATABASE_URL", "libsql://tindahaniq-prod.turso.io")
    monkeypatch.setenv("TURSO_AUTH_TOKEN", raw_token)

    settings = load_settings(env_file=None)

    assert settings.has_turso_config is True
    assert settings.turso_http_url == "https://tindahaniq-prod.turso.io"
    assert raw_token not in repr(settings)
    assert raw_token not in str(settings)


def test_blank_turso_credentials_treated_as_unconfigured(
    isolated_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TURSO_DATABASE_URL", "   ")
    monkeypatch.setenv("TURSO_AUTH_TOKEN", "   ")

    settings = load_settings(env_file=None)

    assert settings.turso_database_url is None
    assert settings.turso_auth_token is None
    assert settings.has_turso_config is False


def test_streamlit_secrets_populate_settings_and_env_takes_precedence(
    isolated_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret_ai = "sk-streamlit-cloud-secret-999"
    secret_turso = "turso-streamlit-cloud-token-888"
    monkeypatch.setenv("STORE_NAME", "Env Override Store")

    settings = load_settings(
        env_file=None,
        secrets={
            "APP_ENV": "production",
            "STORE_NAME": "Secrets Store",
            "TURSO_DATABASE_URL": "libsql://cloud-prod.turso.io",
            "TURSO_AUTH_TOKEN": secret_turso,
            "OPENAI_API_KEY": secret_ai,
        },
    )

    assert settings.app_env == "production"
    assert settings.store_name == "Env Override Store"
    assert settings.has_turso_config is True
    assert settings.has_ai_api_key is True
    assert secret_ai not in repr(settings)
    assert secret_turso not in repr(settings)
