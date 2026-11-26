"""Interactive Streamlit AppTest workflows exercising forms, uploads, preferences & chat."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from tindahaniq.ai.consultant import AIConsultantService
from tindahaniq.config import PROJECT_ROOT
from tindahaniq.models import ProviderTurnResult, ToolCallRequest

APP_SCRIPT = str(PROJECT_ROOT / "src" / "tindahaniq" / "app.py")


def test_inventory_forms_add_product_record_sale_adjust_edit_archive_and_preferences(
    isolated_env: Path,
) -> None:
    at = AppTest.from_file(APP_SCRIPT)
    at.run(timeout=25)
    assert not at.exception

    # 1. Navigate to Inventory and create a new product via `add_product_form`
    at.button(key="nav_inventory").click().run(timeout=25)
    assert not at.exception

    at.text_input(key="add_prod_name").set_value("Kopiko Brown Twin Pack")
    for btn in at.button:
        if "Create Product" in btn.label:
            btn.click().run(timeout=25)
            break
    assert not at.exception

    # 2. Record a Walk-In Sale via `record_walkin_sale_form`
    for btn in at.button:
        if "Record Sale" in btn.label:
            btn.click().run(timeout=25)
            break
    assert not at.exception

    # 3. Apply a Supplier Restock via `stock_adjustment_form`
    for btn in at.button:
        if "Apply Stock Update" in btn.label:
            btn.click().run(timeout=25)
            break
    assert not at.exception

    # 4. Save Product Changes & Archive -> Reactivate Product
    for btn in at.button:
        if "Save Product Changes" in btn.label:
            btn.click().run(timeout=25)
            break
    assert not at.exception

    at.button(key="archive_prod_btn").click().run(timeout=25)
    assert not at.exception
    at.button(key="restore_prod_btn").click().run(timeout=25)
    assert not at.exception

    # 5. Navigate to Settings & Help and save updated store preferences
    at.button(key="nav_system_help").click().run(timeout=25)
    assert not at.exception
    at.text_input(key="pref_store_name").set_value("Aling Nena Sari-Sari Store")
    for btn in at.button:
        if "Save Preferences" in btn.label:
            btn.click().run(timeout=25)
            break
    assert not at.exception
    assert any("Aling Nena Sari-Sari Store" in m.value for m in at.sidebar.markdown)


def test_upload_import_result_renderer_handles_clean_partial_and_failed_states() -> None:
    def _app_script() -> None:
        from tindahaniq.models import (
            CSVImportResult,
            ImportRowError,
            ImportType,
            ImportWarning,
        )
        from tindahaniq.ui.pages.upload_data import _render_import_result

        clean = CSVImportResult(
            import_type=ImportType.INVENTORY,
            filename="clean.csv",
            file_checksum="abc",
            rows_total=5,
            rows_created=5,
        )
        partial = CSVImportResult(
            import_type=ImportType.INVENTORY,
            filename="partial.csv",
            file_checksum="def",
            dry_run=True,
            rows_total=4,
            rows_created=2,
            rows_skipped_duplicate=1,
            rows_rejected=1,
            warnings=(ImportWarning(row_number=3, field="sku", message="Duplicate SKU skipped."),),
            errors=(
                ImportRowError(
                    row_number=4,
                    field="selling_price",
                    raw_value="-5",
                    message="Price cannot be negative.",
                ),
            ),
        )
        failed = CSVImportResult(
            import_type=ImportType.SALES,
            filename="failed.csv",
            file_checksum="ghi",
            rows_total=2,
            rows_rejected=2,
        )
        _render_import_result(clean)
        _render_import_result(partial)
        _render_import_result(failed)

    at = AppTest.from_function(_app_script)
    at.run(timeout=15)
    assert not at.exception
    assert len(at.success) == 1
    assert len(at.warning) == 1
    assert len(at.error) == 1
    assert len(at.dataframe) == 2


def test_upload_demo_14d_and_reset_store_data(isolated_env: Path) -> None:
    at = AppTest.from_file(APP_SCRIPT)
    at.run(timeout=25)
    assert not at.exception

    at.button(key="nav_upload_data").click().run(timeout=25)
    assert not at.exception

    at.button(key="upload_load_demo14d_btn").click().run(timeout=25)
    assert not at.exception
    assert len(at.dataframe) >= 1
    assert any("18 products" in s.value for s in at.success)

    at.button(key="nav_system_help").click().run(timeout=25)
    assert not at.exception
    at.checkbox(key="confirm_reset_store_chk").check().run(timeout=25)
    at.button(key="reset_store_data_btn").click().run(timeout=25)
    assert not at.exception
    assert any("Cleared all local store" in s.value for s in at.success)


def test_ai_assistant_chip_and_clear_history_with_mocked_provider(
    isolated_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-fake-key-for-apptest-12345")

    class _FakeUIProvider:
        def __init__(self) -> None:
            self._calls = 0

        def generate_turn(self, **_kwargs: object) -> ProviderTurnResult:
            self._calls += 1
            if self._calls == 1:
                return ProviderTurnResult(
                    tool_calls=(
                        ToolCallRequest(
                            call_id="c1",
                            name="analyze_profitability",
                            arguments={"sort_by": "gross_profit", "top_n": 3},
                        ),
                    )
                )
            return ProviderTurnResult(
                text="**Business Insight**\nCoca-Cola Mismo leads your store's gross profit."
            )

    monkeypatch.setattr(AIConsultantService, "_get_provider", lambda _self: _FakeUIProvider())

    at = AppTest.from_file(APP_SCRIPT)
    at.run(timeout=25)
    at.button(key="dash_load_sample").click().run(timeout=25)
    at.button(key="nav_ai_assistant").click().run(timeout=25)
    assert not at.exception

    at.button(key="ai_chip_0").click().run(timeout=25)
    assert not at.exception
    assert any("Coca-Cola Mismo leads" in m.value for m in at.markdown)
    assert any("analyze_profitability" in c.value for c in at.caption)

    at.button(key="ai_clear_btn").click().run(timeout=25)
    assert not at.exception
    assert not any("Coca-Cola Mismo leads" in m.value for m in at.markdown)
