"""Unit tests verifying Streamlit Cloud packaging files stay in sync."""

from __future__ import annotations

import tomllib

from tindahaniq.config import PROJECT_ROOT


def test_requirements_txt_matches_pyproject_runtime_dependencies() -> None:
    pyproject_path = PROJECT_ROOT / "pyproject.toml"
    requirements_path = PROJECT_ROOT / "requirements.txt"

    assert requirements_path.exists(), "requirements.txt is required for Streamlit Community Cloud"

    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    deps: list[str] = pyproject["project"]["dependencies"]
    req_lines = {
        line.strip()
        for line in requirements_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }

    for dep in deps:
        assert dep in req_lines, f"Missing dependency `{dep}` in requirements.txt"
    assert "." in req_lines or "-e ." in req_lines
