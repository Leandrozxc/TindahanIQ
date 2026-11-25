"""Headless Streamlit integration smoke tests for the TindahanIQ entry point."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from tindahaniq.config import PROJECT_ROOT

APP_SCRIPT = str(PROJECT_ROOT / "src" / "tindahaniq" / "app.py")


def test_streamlit_app_renders_dashboard_shell_on_empty_store(isolated_env: Path) -> None:
    at = AppTest.from_file(APP_SCRIPT)
    at.run(timeout=20)

    assert not at.exception
    titles = [title.value for title in at.title]
    assert any("TindahanIQ" in text for text in titles)
    assert any("Store Overview" in text for text in titles)
    assert len(at.metric) == 4


def test_streamlit_healthz_query_param_returns_json(isolated_env: Path) -> None:
    at = AppTest.from_file(APP_SCRIPT)
    at.query_params["healthz"] = "1"
    at.run(timeout=20)

    assert not at.exception
    assert len(at.json) == 1
    assert '"healthy"' in at.json[0].value


def test_streamlit_app_displays_safe_error_on_invalid_config(
    isolated_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_ENV", "invalid_env_name")

    at = AppTest.from_file(APP_SCRIPT)
    at.run(timeout=20)

    assert not at.exception
    assert len(at.error) == 1
    assert "app_env" in at.error[0].value
