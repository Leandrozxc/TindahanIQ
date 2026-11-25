"""Integration tests for operational SalesService, basket atomicity, and sales tracking."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from tindahaniq.db import DatabaseManager
from tindahaniq.exceptions import ValidationError
from tindahaniq.models import ProductCreate, ProductUpdate, SaleItemInput
from tindahaniq.services import InventoryService, SalesService


@pytest.fixture
def store_services(tmp_path: Path) -> tuple[InventoryService, SalesService]:
    db = DatabaseManager(tmp_path / "sales_ops.db")
    db.initialize_schema()
    return InventoryService(db), SalesService(db)


def test_live_sale_deducts_stock_and_preserves_historical_prices_after_update(
    store_services: tuple[InventoryService, SalesService],
) -> None:
    inv, sales = store_services
    soy = inv.create_product(
        ProductCreate(
            sku="COND-01",
            name="Silver Swan Soy Sauce 385ml",
            category="Condiments",
            unit="bottle",
            unit_cost=Decimal("19.00"),
            selling_price=Decimal("25.00"),
            current_stock=10,
        )
    )

    sale_1 = sales.record_sale(
        SaleItemInput(
            product_id=soy.product.id,
            quantity_sold=3,
            sold_at=datetime(2026, 11, 24, 9, 0, tzinfo=UTC),
        )
    )
    assert sale_1.gross_revenue == Decimal("75.00")
    assert sale_1.gross_profit == Decimal("18.00")
    assert inv.get_product(soy.product.id).inventory.current_stock == 7

    # Store owner raises cost and selling price later in the week
    inv.update_product(
        soy.product.id,
        ProductUpdate(unit_cost=Decimal("21.00"), selling_price=Decimal("28.00")),
    )

    sale_2 = sales.record_sale(
        SaleItemInput(
            product_id=soy.product.id,
            quantity_sold=2,
            sold_at=datetime(2026, 11, 25, 10, 0, tzinfo=UTC),
        )
    )
    assert sale_2.gross_revenue == Decimal("56.00")
    assert sale_2.gross_profit == Decimal("14.00")
    assert inv.get_product(soy.product.id).inventory.current_stock == 5

    # Historical sale_1 still retains exact original snapped cost (₱19) & price (₱25)
    history = sales.get_sales_history(product_id=soy.product.id, newest_first=False)
    assert len(history) == 2
    assert history[0].sale.unit_price_at_sale == Decimal("25.00")
    assert history[0].sale.unit_cost_at_sale == Decimal("19.00")
    assert history[1].sale.unit_price_at_sale == Decimal("28.00")
    assert history[1].sale.unit_cost_at_sale == Decimal("21.00")


def test_multi_item_basket_rolls_back_atomically_when_any_line_lacks_stock(
    store_services: tuple[InventoryService, SalesService],
) -> None:
    inv, sales = store_services
    bread = inv.create_product(
        ProductCreate(
            sku="BAK-01",
            name="Pinoy Tasty Loaf",
            category="Bakery",
            unit="loaf",
            unit_cost=Decimal("36.00"),
            selling_price=Decimal("42.00"),
            current_stock=5,
        )
    )
    milk = inv.create_product(
        ProductCreate(
            sku="MILK-01",
            name="Bear Brand 33g",
            category="Dairy",
            unit="pack",
            unit_cost=Decimal("11.25"),
            selling_price=Decimal("15.00"),
            current_stock=2,
        )
    )

    # Basket requests 2 bread (valid) + 3 milk (exceeds stock of 2) -> full rollback!
    with pytest.raises(ValidationError, match="Insufficient stock"):
        sales.record_sales_batch(
            [
                SaleItemInput(product_id=bread.product.id, quantity_sold=2),
                SaleItemInput(product_id=milk.product.id, quantity_sold=3),
            ]
        )

    assert inv.get_product(bread.product.id).inventory.current_stock == 5
    assert inv.get_product(milk.product.id).inventory.current_stock == 2
    assert sales.get_sales_history() == []


def test_archived_product_blocks_live_sale_and_sales_tracking_includes_zero_movers(
    store_services: tuple[InventoryService, SalesService],
) -> None:
    inv, sales = store_services
    soap = inv.create_product(
        ProductCreate(
            sku="CARE-01",
            name="Safeguard Bar Soap",
            category="Personal Care",
            unit="pc",
            unit_cost=Decimal("18.50"),
            selling_price=Decimal("24.00"),
            current_stock=10,
        )
    )
    candle = inv.create_product(
        ProductCreate(
            sku="HOME-02",
            name="White Vigil Candle",
            category="Household",
            unit="pc",
            unit_cost=Decimal("4.00"),
            selling_price=Decimal("7.00"),
            current_stock=20,
        )
    )

    sales.record_sale(SaleItemInput(product_id=soap.product.id, quantity_sold=4))

    summaries = sales.get_product_sales_tracking()
    by_sku = {s.sku: s for s in summaries}
    assert by_sku["CARE-01"].total_units_sold == 4
    assert by_sku["CARE-01"].transaction_count == 1
    assert by_sku["HOME-02"].total_units_sold == 0
    assert by_sku["HOME-02"].last_sold_at is None

    # Deactivating soap prevents live POS sale
    inv.deactivate_product(soap.product.id)
    with pytest.raises(ValidationError, match="inactive") as exc_info:
        sales.record_sale(SaleItemInput(product_id=soap.product.id, quantity_sold=1))
    assert "archived" in exc_info.value.user_message

    # Invalid date filter window raises ValidationError
    with pytest.raises(ValidationError):
        sales.get_sales_history(
            start_at=datetime(2026, 11, 25, tzinfo=UTC),
            end_at=datetime(2026, 11, 20, tzinfo=UTC),
        )
    assert candle.product.sku == "HOME-02"
