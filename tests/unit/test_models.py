"""Unit tests for Pydantic product, inventory, and sales models."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError as PydanticValidationError

from tindahaniq.exceptions import ValidationError
from tindahaniq.models import Product, ProductCreate, SalesTransaction, SalesTransactionCreate


def test_product_create_applies_defaults_and_normalizes_fields() -> None:
    item = ProductCreate(
        name="  Silver Swan Soy Sauce 385ml ",
        unit_cost="₱19.00",  # type: ignore[arg-type]
        selling_price="25",  # type: ignore[arg-type]
        current_stock="12",  # type: ignore[arg-type]
    )

    assert item.name == "Silver Swan Soy Sauce 385ml"
    assert item.category == "Uncategorized"
    assert item.unit == "pcs"
    assert item.unit_cost == Decimal("19.00")
    assert item.selling_price == Decimal("25.00")
    assert item.current_stock == 12
    assert item.reorder_point == 10
    assert item.lead_time_days == 1
    assert item.sku == "SILVER-SWAN-SOY-SAUCE-385ML-PCS"


def test_product_unit_profit_is_exact_decimal() -> None:
    now = datetime.now(UTC)
    product = Product(
        id=1,
        sku="NOOD-001",
        name="Pancit Canton",
        category="Instant Noodles",
        unit="pack",
        unit_cost=Decimal("12.25"),
        selling_price=Decimal("16.00"),
        created_at=now,
        updated_at=now,
    )
    assert product.unit_profit == Decimal("3.75")


def test_sales_transaction_computes_exact_revenue_cogs_and_profit() -> None:
    create_model = SalesTransactionCreate(
        product_id=1,
        sold_at="2026-11-22 08:05:00",  # type: ignore[arg-type]
        quantity_sold=3,
        unit_price_at_sale=Decimal("16.00"),
        unit_cost_at_sale=Decimal("12.25"),
        external_ref=" TXN-99 ",
    )
    assert create_model.gross_revenue == Decimal("48.00")
    assert create_model.external_ref == "TXN-99"

    persisted = SalesTransaction(
        id=10,
        product_id=1,
        sold_at=create_model.sold_at,
        quantity_sold=3,
        unit_price_at_sale=Decimal("16.00"),
        unit_cost_at_sale=Decimal("12.25"),
        gross_revenue=create_model.gross_revenue,
        external_ref="TXN-99",
        created_at=datetime.now(UTC),
    )
    assert persisted.cogs == Decimal("36.75")
    assert persisted.gross_profit == Decimal("11.25")


def test_models_reject_invalid_quantities_and_prices() -> None:
    with pytest.raises((ValidationError, PydanticValidationError)):
        ProductCreate(
            name="Invalid Price Item",
            unit_cost=Decimal("10.00"),
            selling_price=Decimal("0.00"),
        )

    with pytest.raises((ValidationError, PydanticValidationError)):
        SalesTransactionCreate(
            product_id=1,
            sold_at=datetime.now(UTC),
            quantity_sold=0,
            unit_price_at_sale=Decimal("15.00"),
            unit_cost_at_sale=Decimal("10.00"),
        )
