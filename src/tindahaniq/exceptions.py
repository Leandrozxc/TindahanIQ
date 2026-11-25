"""Domain and infrastructure exception hierarchy for TindahanIQ."""

from __future__ import annotations

from typing import Any

GENERIC_ERROR_MESSAGE = (
    "An unexpected application error occurred. Please check the application logs and try again."
)


class TindahanIQError(Exception):
    """Base exception carrying a user-safe message alongside internal diagnostic context."""

    default_user_message: str = GENERIC_ERROR_MESSAGE

    def __init__(
        self,
        message: str,
        *,
        user_message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.user_message = user_message or self.default_user_message
        self.details = details or {}


class ConfigurationError(TindahanIQError):
    """Raised when environment or application settings are invalid or missing."""

    default_user_message = (
        "Application configuration is invalid. Please verify your `.env` settings."
    )


class ValidationError(TindahanIQError):
    """Raised when business input or domain invariants fail validation."""

    default_user_message = "The provided input could not be validated. Please review the values."


class DatabaseError(TindahanIQError):
    """Raised when a persistence operation fails."""

    default_user_message = "A local data storage error occurred while processing your request."


class DataImportError(TindahanIQError):
    """Raised when an uploaded CSV file cannot be parsed or imported."""

    default_user_message = "The uploaded file could not be imported. Please check its format."


class AIServiceError(TindahanIQError):
    """Raised when the AI provider is unconfigured, unreachable, or returns an invalid response."""

    default_user_message = (
        "The AI Business Consultant is temporarily unavailable. "
        "Your store analytics and tools remain accessible."
    )


def get_user_safe_message(exc: BaseException) -> str:
    """Return a message safe to display in the UI without leaking secrets or stack traces."""
    if isinstance(exc, TindahanIQError):
        return exc.user_message
    return GENERIC_ERROR_MESSAGE
