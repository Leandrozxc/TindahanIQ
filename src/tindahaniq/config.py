"""Typed application configuration management backed by environment variables."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic import ValidationError as PydanticValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from tindahaniq.exceptions import ConfigurationError

AppEnvironment = Literal["development", "testing", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class AppSettings(BaseSettings):
    """Validated runtime settings for TindahanIQ."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = Field(default="TindahanIQ", min_length=1, max_length=80)
    app_env: AppEnvironment = Field(default="development")
    log_level: LogLevel = Field(default="INFO")

    store_name: str = Field(default="My Sari-Sari Store", min_length=1, max_length=120)
    currency_symbol: str = Field(default="₱", min_length=1, max_length=5)
    currency_code: str = Field(default="PHP", min_length=3, max_length=3)

    database_path: Path = Field(default=Path("data/tindahaniq.db"))
    turso_database_url: str | None = Field(default=None)
    turso_auth_token: SecretStr | None = Field(default=None)

    openai_api_key: SecretStr | None = Field(default=None)
    openai_base_url: str = Field(
        default="https://aiki-labs.up.railway.app/api/v1",
        min_length=1,
        max_length=300,
    )
    openai_model: str = Field(default="gpt-6-luna", min_length=1, max_length=100)
    openai_max_completion_tokens: int = Field(default=1024, ge=64, le=16384)

    @field_validator("app_env", mode="before")
    @classmethod
    def _normalize_app_env(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("log_level", "currency_code", mode="before")
    @classmethod
    def _normalize_uppercase(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @field_validator("openai_api_key", "turso_auth_token", mode="before")
    @classmethod
    def _empty_key_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        if isinstance(value, SecretStr) and not value.get_secret_value().strip():
            return None
        return value

    @field_validator("turso_database_url", mode="before")
    @classmethod
    def _empty_url_to_none(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @property
    def resolved_database_path(self) -> Path:
        """Return an absolute filesystem path for the SQLite database file."""
        if self.database_path.is_absolute():
            return self.database_path
        return (PROJECT_ROOT / self.database_path).resolve()

    @property
    def has_ai_api_key(self) -> bool:
        """Indicate whether a non-empty AI API key is configured without exposing it."""
        return self.openai_api_key is not None and bool(
            self.openai_api_key.get_secret_value().strip()
        )

    @property
    def has_turso_config(self) -> bool:
        """Indicate whether both Turso URL and auth token are configured."""
        return (
            self.turso_database_url is not None
            and bool(self.turso_database_url.strip())
            and self.turso_auth_token is not None
            and bool(self.turso_auth_token.get_secret_value().strip())
        )

    @property
    def turso_http_url(self) -> str | None:
        """Normalize a libsql:// or https:// Turso URL to an HTTPS base URL."""
        if not self.turso_database_url:
            return None
        url = self.turso_database_url.strip().rstrip("/")
        if url.startswith("libsql://"):
            return "https://" + url[len("libsql://") :]
        return url


def _read_streamlit_secrets() -> Mapping[str, Any]:
    """Safely read top-level Streamlit secrets if running with a secrets.toml."""
    try:
        import streamlit as st

        return dict(st.secrets)
    except Exception:
        return {}


def load_settings(
    env_file: Path | str | None = ".env",
    *,
    secrets: Mapping[str, Any] | None = None,
) -> AppSettings:
    """Load and validate application settings, translating validation errors cleanly."""
    resolved_secrets = _read_streamlit_secrets() if secrets is None else secrets
    secret_overrides: dict[str, Any] = {}
    env_upper = {k.upper() for k in os.environ}
    valid_fields = set(AppSettings.model_fields)

    for raw_key, raw_val in resolved_secrets.items():
        field_name = str(raw_key).strip().lower()
        if field_name in valid_fields and field_name.upper() not in env_upper:
            secret_overrides[field_name] = raw_val

    try:
        return AppSettings(_env_file=env_file, **secret_overrides)
    except PydanticValidationError as exc:
        invalid_fields = [
            ".".join(str(part) for part in err.get("loc", ())) for err in exc.errors()
        ]
        raise ConfigurationError(
            f"Invalid configuration fields: {', '.join(invalid_fields)}",
            user_message=(
                "Configuration error detected in environment settings "
                f"({', '.join(invalid_fields)}). Check your `.env` file."
            ),
            details={"fields": invalid_fields},
        ) from exc
