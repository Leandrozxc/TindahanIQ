"""Rerun-safe structured logging configuration for TindahanIQ."""

from __future__ import annotations

import logging
import sys

LOGGER_NAME = "tindahaniq"
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(level: str = "INFO") -> logging.Logger:
    """Configure the package root logger idempotently across Streamlit script reruns."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(numeric_level)
    logger.propagate = False

    if not logger.handlers:
        handler = logging.StreamHandler(stream=sys.stderr)
        handler.setFormatter(logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT))
        logger.addHandler(handler)

    for handler in logger.handlers:
        handler.setLevel(numeric_level)

    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a child logger scoped under the `tindahaniq` namespace."""
    if not name or name == LOGGER_NAME:
        return logging.getLogger(LOGGER_NAME)
    if name.startswith(f"{LOGGER_NAME}."):
        return logging.getLogger(name)
    return logging.getLogger(f"{LOGGER_NAME}.{name}")
