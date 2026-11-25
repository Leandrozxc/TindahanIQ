"""SQLite integration tests for DatabaseManager and persistence repositories."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from tindahaniq.db import DatabaseManager, ProductRepository, SalesRepository
from tindahaniq.exceptions import ValidationError
from tindahaniq.models import AdjustmentReason, ProductCreate, SalesTransactionCreate


@pytest.fixture
def db_manager(tmp_path: Path) -> DatabaseManager:
    manager = DatabaseManager(tmp_path / "store_test.db")
    manager.initialize_schema()
    return manager


def test_product_repository_crud_and_adjustment_audit(db_manager: DatabaseManager) -> None:
    repo = ProductRepository(db_manager)

    created = repo.create_product_with_inventory(
        ProductCreate(
            sku="nood-001",
            name="Lucky Me! Pancit Canton",
            category="Instant Noodles",
            unit="pack",
            unit_cost=Decimal("12.25"),
            selling_price=Decimal("16.00"),
            current_stock=20,
            reorder_point=15,
            lead_time_days=1,
        )
    )
    assert created.product.sku == "NOOD-001"
    assert created.product.unit_cost == Decimal("12.25")
    assert created.inventory.current_stock == 20

    # Duplicate SKU is rejected
    with pytest.raises(ValidationError):
        repo.create_product_with_inventory(
            ProductCreate(
                sku="NOOD-001",
                name="Duplicate Item",
                unit_cost=Decimal("10.00"),
                selling_price=Decimal("15.00"),
            )
        )

    # Upsert updates stock and logs CSV_SYNC adjustment delta (+10)
    updated, was_created = repo.upsert_product_from_import(
        ProductCreate(
            sku="NOOD-001",
            name="Lucky Me! Pancit Canton",
            category="Instant Noodles",
            unit="pack",
            unit_cost=Decimal("12.50"),
            selling_price=Decimal("17.00"),
            current_stock=30,
            reorder_point=15,
        )
    )
    assert was_created is False
    assert updated.product.selling_price == Decimal("17.00")
    assert updated.inventory.current_stock == 30

    adjustments = repo.list_adjustments(created.product.id)
    assert len(adjustments) == 2
    assert adjustments[0].reason == AdjustmentReason.INITIAL_IMPORT
    assert adjustments[0].quantity_delta == 20
    assert adjustments[1].reason == AdjustmentReason.CSV_SYNC
    assert adjustments[1].quantity_delta == 10


def test_transaction_rolls_back_atomically_on_failure(db_manager: DatabaseManager) -> None:
    repo = ProductRepository(db_manager)

    with pytest.raises(RuntimeError, match="simulated crash"), db_manager.transaction() as conn:
        repo.create_product_with_inventory(
            ProductCreate(
                sku="ROLLBACK-1",
                name="Should Not Persist",
                unit_cost=Decimal("5.00"),
                selling_price=Decimal("8.00"),
                current_stock=5,
            ),
            conn=conn,
        )
        raise RuntimeError("simulated crash")

    assert repo.get_by_sku("ROLLBACK-1") is None
    assert repo.list_all() == []


def test_sales_repository_enforces_foreign_keys_and_ref_uniqueness(
    db_manager: DatabaseManager,
) -> None:
    product_repo = ProductRepository(db_manager)
    sales_repo = SalesRepository(db_manager)

    item = product_repo.create_product_with_inventory(
        ProductCreate(
            sku="BEV-001",
            name="Coca-Cola Mismo 290ml",
            unit_cost=Decimal("14.00"),
            selling_price=Decimal("20.00"),
            current_stock=36,
        )
    )

    # Foreign key rejects nonexistent product_id
    with pytest.raises(ValidationError):
        sales_repo.create_sale(
            SalesTransactionCreate(
                product_id=9999,
                sold_at=datetime(2026, 11, 20, 12, 0, tzinfo=UTC),
                quantity_sold=1,
                unit_price_at_sale=Decimal("20.00"),
                unit_cost_at_sale=Decimal("14.00"),
            )
        )

    sale_1 = sales_repo.create_sale(
        SalesTransactionCreate(
            product_id=item.product.id,
            sold_at=datetime(2026, 11, 20, 12, 0, tzinfo=UTC),
            quantity_sold=2,
            unit_price_at_sale=Decimal("20.00"),
            unit_cost_at_sale=Decimal("14.00"),
            external_ref="REC-100",
        )
    )
    assert sale_1.gross_revenue == Decimal("40.00")
    assert sale_1.gross_profit == Decimal("12.00")

    # Duplicate external_ref + product_id is rejected
    with pytest.raises(ValidationError):
        sales_repo.create_sale(
            SalesTransactionCreate(
                product_id=item.product.id,
                sold_at=datetime(2026, 11, 20, 12, 5, tzinfo=UTC),
                quantity_sold=1,
                unit_price_at_sale=Decimal("20.00"),
                unit_cost_at_sale=Decimal("14.00"),
                external_ref="REC-100",
            )
        )

    # Multiple walk-in sales without external_ref on the same day succeed
    sales_repo.create_sale(
        SalesTransactionCreate(
            product_id=item.product.id,
            sold_at=datetime(2026, 11, 20, 13, 0, tzinfo=UTC),
            quantity_sold=1,
            unit_price_at_sale=Decimal("20.00"),
            unit_cost_at_sale=Decimal("14.00"),
        )
    )
    sales_repo.create_sale(
        SalesTransactionCreate(
            product_id=item.product.id,
            sold_at=datetime(2026, 11, 20, 13, 0, tzinfo=UTC),
            quantity_sold=1,
            unit_price_at_sale=Decimal("20.00"),
            unit_cost_at_sale=Decimal("14.00"),
        )
    )

    all_sales = sales_repo.list_sales(product_id=item.product.id)
    assert len(all_sales) == 3
