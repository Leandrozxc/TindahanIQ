"""Deterministic runtime, storage, and SQLite schema health checks for TindahanIQ."""

from __future__ import annotations

import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from tindahaniq import __version__
from tindahaniq.config import AppSettings
from tindahaniq.db.connection import DatabaseManager
from tindahaniq.exceptions import DatabaseError

CheckStatus = Literal["ok", "notice", "error"]
OverallStatus = Literal["healthy", "degraded"]

MIN_PYTHON = (3, 12)


@dataclass(frozen=True, slots=True)
class HealthCheckItem:
    """Result of a single diagnostic check."""

    name: str
    status: CheckStatus
    detail: str


@dataclass(frozen=True, slots=True)
class SystemHealthReport:
    """Aggregated application health check report."""

    overall_status: OverallStatus
    app_version: str
    environment: str
    checked_at_utc: str
    checks: tuple[HealthCheckItem, ...]

    def to_dict(self) -> dict[str, Any]:
        """Serialize health report to a JSON-compatible dictionary."""
        return asdict(self)


def _check_python_runtime(version_info: tuple[int, int, int] | None = None) -> HealthCheckItem:
    current = version_info or (
        sys.version_info.major,
        sys.version_info.minor,
        sys.version_info.micro,
    )
    version_str = f"{current[0]}.{current[1]}.{current[2]}"
    if current[:2] >= MIN_PYTHON:
        return HealthCheckItem(
            name="Python Runtime",
            status="ok",
            detail=f"Python {version_str} meets >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]} requirement.",
        )
    return HealthCheckItem(
        name="Python Runtime",
        status="error",
        detail=f"Python {version_str} is below required {MIN_PYTHON[0]}.{MIN_PYTHON[1]}.",
    )


def _check_storage_directory(db_path: Path) -> HealthCheckItem:
    data_dir = db_path.parent
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=data_dir, prefix=".health_", delete=True) as probe:
            probe.write(b"ok")
            probe.flush()
    except OSError as exc:
        return HealthCheckItem(
            name="Local Data Directory",
            status="error",
            detail=f"Storage directory `{data_dir}` is not writable ({exc.__class__.__name__}).",
        )
    return HealthCheckItem(
        name="Local Data Directory",
        status="ok",
        detail=f"Directory `{data_dir}` exists and is writable.",
    )


def _check_sqlite_database(db_path: Path) -> HealthCheckItem:
    try:
        manager = DatabaseManager(db_path)
        manager.initialize_schema()
    except DatabaseError as exc:
        return HealthCheckItem(
            name="SQLite Persistence",
            status="error",
            detail=f"Database schema check failed ({exc.user_message}).",
        )
    return HealthCheckItem(
        name="SQLite Persistence",
        status="ok",
        detail=f"SQLite schema verified at `{db_path.name}` (foreign keys & WAL active).",
    )


def _check_ai_configuration(settings: AppSettings) -> HealthCheckItem:
    if settings.has_ai_api_key:
        return HealthCheckItem(
            name="AI Provider Key",
            status="ok",
            detail=f"API key configured for model `{settings.openai_model}` (value masked).",
        )
    return HealthCheckItem(
        name="AI Provider Key",
        status="notice",
        detail=(
            "OPENAI_API_KEY is not configured yet. Optional until Phase 5 (AI Business Consultant)."
        ),
    )


def run_health_checks(settings: AppSettings) -> SystemHealthReport:
    """Execute deterministic health checks without exposing secrets."""
    resolved_db = settings.resolved_database_path
    storage_check = _check_storage_directory(resolved_db)
    db_check = (
        _check_sqlite_database(resolved_db)
        if storage_check.status == "ok"
        else HealthCheckItem(
            name="SQLite Persistence",
            status="error",
            detail="Skipped SQLite initialization because storage directory is unavailable.",
        )
    )
    checks = (
        HealthCheckItem(
            name="Application Configuration",
            status="ok",
            detail=(
                f"Store `{settings.store_name}` | "
                f"Currency `{settings.currency_symbol} ({settings.currency_code})`"
            ),
        ),
        _check_python_runtime(),
        storage_check,
        db_check,
        _check_ai_configuration(settings),
    )
    has_error = any(item.status == "error" for item in checks)
    return SystemHealthReport(
        overall_status="degraded" if has_error else "healthy",
        app_version=__version__,
        environment=settings.app_env,
        checked_at_utc=datetime.now(UTC).isoformat(timespec="seconds"),
        checks=checks,
    )
