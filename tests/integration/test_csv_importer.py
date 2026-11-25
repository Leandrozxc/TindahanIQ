"""End-to-end integration tests for CSV inventory and sales ingestion."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from tindahaniq.config import PROJECT_ROOT
from tindahaniq.db import DatabaseManager, ImportBatchRepository, ProductRepository, SalesRepository
from tindahaniq.exceptions import DataImportError
from tindahaniq.models import ExistingProductPolicy
from tindahaniq.services import CSVImportService


@pytest.fixture
def importer_env(tmp_path: Path) -> tuple[CSVImportService, DatabaseManager]:
    db = DatabaseManager(tmp_path / "import_test.db")
    db.initialize_schema()
    return CSVImportService(db), db


def test_sample_inventory_and_sales_csvs_import_cleanly(
    importer_env: tuple[CSVImportService, DatabaseManager],
) -> None:
    importer, db = importer_env
    inv_path = PROJECT_ROOT / "data" / "samples" / "sample_inventory.csv"
    sales_path = PROJECT_ROOT / "data" / "samples" / "sample_sales.csv"

    inv_result = importer.import_inventory_csv(inv_path)
    assert inv_result.rows_total == 10
    assert inv_result.rows_created == 10
    assert inv_result.rows_rejected == 0
    assert inv_result.errors == ()

    sales_result = importer.import_sales_csv(sales_path)
    assert sales_result.rows_total == 12
    assert sales_result.rows_created == 12
    assert sales_result.rows_rejected == 0

    products = ProductRepository(db).list_all()
    sales = SalesRepository(db).list_sales()
    batches = ImportBatchRepository(db).list_batches()
    assert len(products) == 10
    assert len(sales) == 12
    assert len(batches) == 2

    # Whole-file duplicate checksum protection blocks accidental re-upload
    with pytest.raises(DataImportError):
        importer.import_inventory_csv(inv_path)
    with pytest.raises(DataImportError):
        importer.import_sales_csv(sales_path)


def test_inventory_csv_handles_bom_aliases_duplicates_warnings_and_bad_rows(
    importer_env: tuple[CSVImportService, DatabaseManager],
) -> None:
    importer, db = importer_env
    # Includes UTF-8 BOM, Tagalog/alias headers, ₱ formatting, in-file duplicate SKU,
    # below-cost warning item, negative stock error, and blank trailing row.
    csv_bytes = (
        "\ufeffCode,Pangalan,Puhunan,Presyo,Stock\n"
        "SOAP-01,Safeguard White 60g,₱18.50,₱24.00,15\n"
        "SOAP-01,Safeguard Duplicate Row,18.50,25.00,99\n"
        "CLEAR-01,Clearance Biscuits,20.00,15.00,5\n"
        "BAD-01,Negative Stock Item,10.00,15.00,-3\n"
        "BAD-02,,10.00,15.00,4\n"
        ",,,,\n"
    ).encode("utf-8")

    result = importer.import_inventory_csv(csv_bytes, filename="tindahan_export.csv")

    assert result.rows_total == 5
    assert result.rows_created == 2
    assert result.rows_skipped_duplicate == 1
    assert result.rows_rejected == 2
    assert len(result.warnings) == 2  # 1 duplicate SKU + 1 selling_price < unit_cost
    error_lines = [err.row_number for err in result.errors]
    assert error_lines == [5, 6]

    stored_soap = ProductRepository(db).get_by_sku("SOAP-01")
    assert stored_soap is not None
    assert stored_soap.inventory.current_stock == 15
    assert stored_soap.product.unit_cost == Decimal("18.50")


def test_inventory_dry_run_and_skip_existing_policy(
    importer_env: tuple[CSVImportService, DatabaseManager],
) -> None:
    importer, db = importer_env
    initial_csv = (
        "product_name,unit_cost,selling_price,current_stock\nMilo Sachet 24g,8.50,11.00,20\n"
    )

    preview = importer.import_inventory_csv(initial_csv, filename="preview.csv", dry_run=True)
    assert preview.dry_run is True
    assert preview.rows_created == 1
    assert ProductRepository(db).list_all() == []
    assert ImportBatchRepository(db).list_batches() == []

    importer.import_inventory_csv(initial_csv, filename="first.csv")

    second_csv = (
        "product_name,unit_cost,selling_price,current_stock\n"
        "Milo Sachet 24g,9.00,12.00,50\n"
        "Ovaltine Sachet,8.00,11.00,15\n"
    )
    skip_result = importer.import_inventory_csv(
        second_csv,
        filename="second.csv",
        on_existing=ExistingProductPolicy.SKIP,
    )
    assert skip_result.rows_created == 1
    assert skip_result.rows_updated == 0
    assert skip_result.rows_skipped_duplicate == 1

    milo = ProductRepository(db).get_by_sku("MILO-SACHET-24G-PCS")
    assert milo is not None
    assert milo.product.selling_price == Decimal("11.00")


def test_sales_csv_handles_name_lookup_price_fallback_duplicates_and_unknown_items(
    importer_env: tuple[CSVImportService, DatabaseManager],
) -> None:
    importer, db = importer_env
    importer.import_inventory_csv(
        "sku,product_name,unit_cost,selling_price,current_stock\n"
        "EGG-01,Fresh Medium Egg,7.00,10.00,60\n"
    )

    # Row 2: matches by name & falls back to catalog selling_price (₱10.00)
    # Row 3: duplicate receipt_no REC-1 for EGG-01 -> skipped
    # Row 4 & 5: two walk-in sales without receipt_no on same date -> both accepted!
    # Row 6: unknown product -> rejected
    sales_csv = (
        "receipt_no,date,product_name,qty,unit_price\n"
        "REC-1,11/24/2026,fresh medium egg,6,\n"
        "REC-1,11/24/2026,Fresh Medium Egg,6,10.00\n"
        ",2026-11-24,Fresh Medium Egg,2,10.00\n"
        ",2026-11-24,Fresh Medium Egg,3,10.00\n"
        "REC-9,2026-11-24,Nonexistent Soda,1,20.00\n"
    )
    result = importer.import_sales_csv(sales_csv, filename="daily_sales.csv")

    assert result.rows_total == 5
    assert result.rows_created == 3
    assert result.rows_skipped_duplicate == 1
    assert result.rows_rejected == 1
    assert result.errors[0].row_number == 6

    sales = SalesRepository(db).list_sales()
    assert len(sales) == 3
    assert sales[0].gross_revenue == Decimal("60.00")


@pytest.mark.parametrize(
    "bad_payload",
    [
        b"",
        b"   \n  ",
        b"sku,name\x00binary",
        b"wrong_col_a,wrong_col_b\n1,2\n",
        b"product_name,unit_cost,selling_price,current_stock\n",
    ],
)
def test_csv_importer_rejects_malformed_or_missing_header_files(
    importer_env: tuple[CSVImportService, DatabaseManager],
    bad_payload: bytes,
) -> None:
    importer, _db = importer_env
    with pytest.raises(DataImportError):
        importer.import_inventory_csv(bad_payload, filename="bad.csv")
