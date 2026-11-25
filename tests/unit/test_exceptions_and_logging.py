"""Unit tests for exception safety and rerun-safe logging configuration."""

from __future__ import annotations

import logging

from tindahaniq.exceptions import (
    GENERIC_ERROR_MESSAGE,
    AIServiceError,
    ConfigurationError,
    DatabaseError,
    DataImportError,
    ValidationError,
    get_user_safe_message,
)
from tindahaniq.logging_config import LOGGER_NAME, configure_logging, get_logger


def test_domain_exceptions_expose_safe_messages() -> None:
    err = ValidationError(
        "SQL constraint failed on table products.unit_cost < 0",
        user_message="Unit cost cannot be negative.",
        details={"field": "unit_cost"},
    )

    assert get_user_safe_message(err) == "Unit cost cannot be negative."
    assert err.details == {"field": "unit_cost"}


def test_all_domain_exception_defaults_are_safe() -> None:
    error_classes = (
        ConfigurationError,
        ValidationError,
        DatabaseError,
        DataImportError,
        AIServiceError,
    )
    for cls in error_classes:
        instance = cls("internal diagnostic detail")
        safe_msg = get_user_safe_message(instance)
        assert "internal diagnostic detail" not in safe_msg
        assert len(safe_msg) > 10


def test_unexpected_exception_masks_internal_details() -> None:
    unexpected = RuntimeError("sensitive C:/Users/secret_token traceback")

    assert get_user_safe_message(unexpected) == GENERIC_ERROR_MESSAGE


def test_configure_logging_is_idempotent_across_reruns() -> None:
    logger_first = configure_logging("INFO")
    handler_count = len(logger_first.handlers)

    logger_second = configure_logging("DEBUG")

    assert logger_first is logger_second
    assert len(logger_second.handlers) == handler_count == 1
    assert logger_second.level == logging.DEBUG


def test_get_logger_scopes_names_under_package_root() -> None:
    assert get_logger().name == LOGGER_NAME
    assert get_logger(LOGGER_NAME).name == LOGGER_NAME
    assert get_logger("health").name == f"{LOGGER_NAME}.health"
    assert get_logger(f"{LOGGER_NAME}.db").name == f"{LOGGER_NAME}.db"
