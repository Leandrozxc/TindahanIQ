"""Unit tests enforcing zero-emoji UI icon standards across TindahanIQ."""

from __future__ import annotations

import re

from tindahaniq.config import PROJECT_ROOT

EMOJI_PATTERN = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]")


def test_no_emoji_icons_in_ui_or_app_entrypoint() -> None:
    targets = [
        PROJECT_ROOT / "src" / "tindahaniq" / "app.py",
        *sorted((PROJECT_ROOT / "src" / "tindahaniq" / "ui").rglob("*.py")),
    ]
    offenders: list[str] = []
    for path in targets:
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if EMOJI_PATTERN.search(line):
                offenders.append(f"{path.name}:{line_no}: {line.strip()}")

    assert not offenders, "Found emoji icons in UI code:\n" + "\n".join(offenders)
