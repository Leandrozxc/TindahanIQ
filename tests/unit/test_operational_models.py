"""Unit tests for Phase 3 operational schemas and signed integer validation."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError as PydanticValidationError

from tindahaniq.exceptions import ValidationError
from tindahaniq.models import ProductUpdate, SaleItemInput, StockAdjustmentCreate
from tindahaniq.utils import parse_nonzero_int


def test_parse_nonzero_int_handles_signed_values_and_rejects_zero() -> None:
    assert parse_nonzero_int("-5") == -5
    assert parse_nonzero_int("+12") == 12
    assert parse_nonzero_int(-3.0) == -3

    for invalid in (0, "0", "2.5", True, None, "", "abc"):
        with pytest.raises(ValidationError):
            parse_nonzero_int(invalid)


def test_product_update_requires_at_least_one_field() -> None:
    with pytest.raises((ValidationError, PydanticValidationError)):
        ProductUpdate()

    valid = ProductUpdate(selling_price="₱18.50")  # type: ignore[arg-type]
    assert valid.selling_price == Decimal("18.50")
    assert valid.name is None


def test_stock_adjustment_create_rejects_zero_delta() -> None:
    with pytest.raises((ValidationError, PydanticValidationError)):
        StockAdjustmentCreate(product_id=1, quantity_delta=0)

    adj = StockAdjustmentCreate(product_id=1, quantity_delta=-2, notes="  Damaged pack ")
    assert adj.quantity_delta == -2
    assert adj.notes == "Damaged pack"


def test_sale_item_input_validates_override_price_and_qty() -> None:
    sale_in = SaleItemInput(product_id=2, quantity_sold="4", unit_price_override="₱19.50")  # type: ignore[arg-type]
    assert sale_in.quantity_sold == 4
    assert sale_in.unit_price_override == Decimal("19.50")

    with pytest.raises((ValidationError, PydanticValidationError)):
        SaleItemInput(product_id=2, quantity_sold=0)
