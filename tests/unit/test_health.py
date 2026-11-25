"""Unit tests for deterministic runtime and storage health checks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tindahaniq.config import load_settings
from tindahaniq.health import _check_python_runtime, run_health_checks


def test_health_report_healthy_without_ai_key(isolated_env: Path) -> None:
    settings = load_settings(env_file=None)

    report = run_health_checks(settings)

    assert report.overall_status == "healthy"
    statuses = {item.name: item.status for item in report.checks}
    assert statuses["Application Configuration"] == "ok"
    assert statuses["Python Runtime"] == "ok"
    assert statuses["Local Data Directory"] == "ok"
    assert statuses["AI Provider Key"] == "notice"


def test_health_report_masks_configured_ai_key(
    isolated_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "AIzaSyTopSecretKey999"
    monkeypatch.setenv("GEMINI_API_KEY", secret)
    settings = load_settings(env_file=None)

    report = run_health_checks(settings)
    serialized = json.dumps(report.to_dict())

    assert report.overall_status == "healthy"
    statuses = {item.name: item.status for item in report.checks}
    assert statuses["AI Provider Key"] == "ok"
    assert secret not in serialized


def test_python_runtime_version_check_flags_unsupported_python() -> None:
    ok_item = _check_python_runtime((3, 12, 6))
    fail_item = _check_python_runtime((3, 11, 8))

    assert ok_item.status == "ok"
    assert fail_item.status == "error"


def test_unwritable_storage_directory_marks_report_degraded(
    isolated_env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blocking_file = tmp_path / "not_a_directory"
    blocking_file.write_text("conflict", encoding="utf-8")
    monkeypatch.setenv("DATABASE_PATH", str(blocking_file / "tindahaniq.db"))
    settings = load_settings(env_file=None)

    report = run_health_checks(settings)

    assert report.overall_status == "degraded"
    statuses = {item.name: item.status for item in report.checks}
    assert statuses["Local Data Directory"] == "error"
