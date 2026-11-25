"""Integration tests for operational InventoryService product and stock operations."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from tindahaniq.db import DatabaseManager
from tindahaniq.exceptions import ValidationError
from tindahaniq.models import (
    AdjustmentReason,
    ProductCreate,
    ProductUpdate,
    StockAdjustmentCreate,
)
from tindahaniq.services import InventoryService


@pytest.fixture
def inv_service(tmp_path: Path) -> InventoryService:
    db = DatabaseManager(tmp_path / "inventory_ops.db")
    db.initialize_schema()
    return InventoryService(db)


def test_product_lifecycle_search_and_archive(inv_service: InventoryService) -> None:
    noodles = inv_service.create_product(
        ProductCreate(
            sku="NOOD-01",
            name="Lucky Me! Pancit Canton",
            category="Instant Noodles",
            unit="pack",
            unit_cost=Decimal("12.25"),
            selling_price=Decimal("16.00"),
            current_stock=5,
            reorder_point=12,
        )
    )
    soda = inv_service.create_product(
        ProductCreate(
            sku="BEV-01",
            name="Coca-Cola Mismo 290ml",
            category="Beverages",
            unit="bottle",
            unit_cost=Decimal("14.00"),
            selling_price=Decimal("20.00"),
            current_stock=0,
            reorder_point=10,
        )
    )

    assert inv_service.list_categories() == ["Beverages", "Instant Noodles"]
    assert len(inv_service.list_inventory(query="pancit")) == 1
    assert len(inv_service.list_inventory(low_stock_only=True)) == 2
    assert [p.product.sku for p in inv_service.list_inventory(out_of_stock_only=True)] == ["BEV-01"]

    updated = inv_service.update_product(
        noodles.product.id,
        ProductUpdate(selling_price=Decimal("17.00"), reorder_point=20),
    )
    assert updated.product.selling_price == Decimal("17.00")
    assert updated.inventory.reorder_point == 20
    assert updated.inventory.current_stock == 5

    archived = inv_service.deactivate_product(soda.product.id)
    assert archived.product.is_active is False
    assert len(inv_service.list_inventory(active_only=True)) == 1
    assert len(inv_service.list_inventory(active_only=False)) == 2

    restored = inv_service.reactivate_product(soda.product.id)
    assert restored.product.is_active is True


def test_stock_adjustments_restock_reconcile_and_negative_guard(
    inv_service: InventoryService,
) -> None:
    coffee = inv_service.create_product(
        ProductCreate(
            sku="COFF-01",
            name="Great Taste White Coffee",
            category="Beverages",
            unit="sachet",
            unit_cost=Decimal("11.50"),
            selling_price=Decimal("15.00"),
            current_stock=6,
            reorder_point=20,
        )
    )

    # Restock +24 updates stock to 30 and sets last_restocked_at
    after_restock, restock_adj = inv_service.restock_product(
        coffee.product.id, 24, notes="Divisoria restock"
    )
    assert after_restock.inventory.current_stock == 30
    assert after_restock.inventory.last_restocked_at is not None
    assert restock_adj.reason == AdjustmentReason.RESTOCK

    # Spoilage -2 updates stock to 28
    after_spoilage, _ = inv_service.adjust_stock(
        StockAdjustmentCreate(
            product_id=coffee.product.id,
            quantity_delta=-2,
            reason=AdjustmentReason.SPOILAGE,
            notes="Torn sachets",
        )
    )
    assert after_spoilage.inventory.current_stock == 28

    # Deducting more than available stock (e.g. -50) fails cleanly and preserves 28
    with pytest.raises(ValidationError, match="Insufficient stock"):
        inv_service.adjust_stock(
            StockAdjustmentCreate(
                product_id=coffee.product.id,
                quantity_delta=-50,
                reason=AdjustmentReason.MANUAL_ADJUSTMENT,
            )
        )
    assert inv_service.get_product(coffee.product.id).inventory.current_stock == 28

    # Physical stocktake matching current count (28) is a clean no-op
    unchanged, noop_adj = inv_service.reconcile_stock_count(coffee.product.id, 28)
    assert unchanged.inventory.current_stock == 28
    assert noop_adj is None

    # Physical stocktake count of 25 logs a -3 delta
    reconciled, count_adj = inv_service.reconcile_stock_count(coffee.product.id, 25)
    assert reconciled.inventory.current_stock == 25
    assert count_adj is not None
    assert count_adj.quantity_delta == -3

    history = inv_service.get_adjustment_history(product_id=coffee.product.id)
    assert [entry.quantity_delta for entry in history] == [6, 24, -2, -3]
