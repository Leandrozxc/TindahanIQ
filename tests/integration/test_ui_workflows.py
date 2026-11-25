"""Interactive Streamlit AppTest workflows exercising forms, uploads, preferences & chat."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from tindahaniq.config import PROJECT_ROOT

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
