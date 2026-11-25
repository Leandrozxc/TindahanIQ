"""Headless Streamlit integration smoke tests for the Phase 1 entry point."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from tindahaniq.config import PROJECT_ROOT

APP_SCRIPT = str(PROJECT_ROOT / "src" / "tindahaniq" / "app.py")


def test_streamlit_app_renders_healthy_foundation_shell(isolated_env: Path) -> None:
    at = AppTest.from_file(APP_SCRIPT)
    at.run(timeout=15)

    assert not at.exception
    titles = [title.value for title in at.title]
    assert any("TindahanIQ" in text for text in titles)
    metric_values = [metric.value for metric in at.metric]
    assert "HEALTHY" in metric_values
    assert len(at.table) == 1


def test_streamlit_healthz_query_param_returns_json(isolated_env: Path) -> None:
    at = AppTest.from_file(APP_SCRIPT)
    at.query_params["healthz"] = "1"
    at.run(timeout=15)

    assert not at.exception
    assert len(at.json) == 1
    assert '"overall_status": "healthy"' in at.json[0].value or '"healthy"' in at.json[0].value


def test_streamlit_app_displays_safe_error_on_invalid_config(
    isolated_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_ENV", "invalid_env_name")

    at = AppTest.from_file(APP_SCRIPT)
    at.run(timeout=15)

    assert not at.exception
    assert len(at.error) == 1
    assert "app_env" in at.error[0].value
