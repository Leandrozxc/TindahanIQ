"""Integration tests for ConsistencyService ledger and arithmetic checks."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from tindahaniq.config import PROJECT_ROOT
from tindahaniq.db import DatabaseManager
from tindahaniq.models import ProductCreate, SaleItemInput
from tindahaniq.services import (
    ConsistencyService,
    CSVImportService,
    InventoryService,
    SalesService,
)


def test_consistency_service_passes_on_clean_imported_and_transacted_store(
    tmp_path: Path,
) -> None:
    db = DatabaseManager(tmp_path / "consistent.db")
    db.initialize_schema()
    importer = CSVImportService(db)
    inv = InventoryService(db)
    sales = SalesService(db)
    checker = ConsistencyService(db)

    importer.import_inventory_csv(PROJECT_ROOT / "data" / "samples" / "sample_inventory.csv")
    importer.import_sales_csv(PROJECT_ROOT / "data" / "samples" / "sample_sales.csv")

    coke = inv.find_product_by_sku("BEV-001")
    assert coke is not None
    sales.record_sale(SaleItemInput(product_id=coke.product.id, quantity_sold=3))
    inv.restock_product(coke.product.id, 12)

    report = checker.verify_data_consistency()
    assert report.is_consistent is True
    assert report.error_count == 0
    assert report.warning_count == 0
    assert report.products_checked == 10
    assert report.sales_checked == 13


def test_consistency_service_detects_tampered_ledger_revenue_and_margin_warnings(
    tmp_path: Path,
) -> None:
    db = DatabaseManager(tmp_path / "tampered.db")
    db.initialize_schema()
    inv = InventoryService(db)
    sales = SalesService(db)
    checker = ConsistencyService(db)

    below_cost = inv.create_product(
        ProductCreate(
            sku="PROMO-01",
            name="Clearance Crackers",
            unit_cost=Decimal("20.00"),
            selling_price=Decimal("15.00"),
            current_stock=10,
        )
    )
    sale = sales.record_sale(SaleItemInput(product_id=below_cost.product.id, quantity_sold=2))

    # Simulate direct out-of-band SQL tampering on inventory stock and sale gross_revenue
    with db.transaction() as conn:
        conn.execute(
            "UPDATE inventory SET current_stock = 999 WHERE product_id = ?",
            (below_cost.product.id,),
        )
        conn.execute(
            "UPDATE sales_transactions SET gross_revenue_centavos = 100 WHERE id = ?",
            (sale.id,),
        )

    report = checker.verify_data_consistency()
    assert report.is_consistent is False
    assert report.error_count == 2
    assert report.warning_count == 1
    codes = {issue.code for issue in report.issues}
    assert codes == {
        "STOCK_LEDGER_MISMATCH",
        "SALE_REVENUE_MISMATCH",
        "NEGATIVE_UNIT_MARGIN",
    }
