"""Pydantic domain schemas for historical and operational sales transactions."""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, ConfigDict, field_validator

from tindahaniq.utils.validation import (
    TWO_PLACES,
    parse_money_decimal,
    parse_non_negative_int,
    parse_sale_timestamp,
    sanitize_text,
)


class SalesTransactionCreate(BaseModel):
    """Validated input model for recording or importing a sales line item."""

    model_config = ConfigDict(extra="forbid")

    product_id: int
    sold_at: datetime
    quantity_sold: int
    unit_price_at_sale: Decimal
    unit_cost_at_sale: Decimal
    external_ref: str | None = None
    import_batch_id: int | None = None

    @field_validator("product_id", mode="before")
    @classmethod
    def _validate_product_id(cls, value: object) -> int:
        return parse_non_negative_int(value, field_name="product_id", min_value=1)

    @field_validator("sold_at", mode="before")
    @classmethod
    def _validate_sold_at(cls, value: object) -> datetime:
        return parse_sale_timestamp(value, field_name="sold_at")

    @field_validator("quantity_sold", mode="before")
    @classmethod
    def _validate_quantity_sold(cls, value: object) -> int:
        return parse_non_negative_int(value, field_name="quantity_sold", min_value=1)

    @field_validator("unit_price_at_sale", mode="before")
    @classmethod
    def _validate_unit_price(cls, value: object) -> Decimal:
        return parse_money_decimal(value, field_name="unit_price_at_sale", allow_zero=True)

    @field_validator("unit_cost_at_sale", mode="before")
    @classmethod
    def _validate_unit_cost(cls, value: object) -> Decimal:
        return parse_money_decimal(value, field_name="unit_cost_at_sale", allow_zero=True)

    @field_validator("external_ref", mode="before")
    @classmethod
    def _validate_external_ref(cls, value: object) -> str | None:
        cleaned = sanitize_text(value, field_name="external_ref", max_length=80, allow_empty=True)
        return cleaned or None

    @property
    def gross_revenue(self) -> Decimal:
        """Compute deterministic gross revenue for this transaction line."""
        return (self.unit_price_at_sale * self.quantity_sold).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP
        )


class SalesTransaction(BaseModel):
    """Persisted sales transaction entity with snapped historical price and cost."""

    model_config = ConfigDict(frozen=True)

    id: int
    product_id: int
    sold_at: datetime
    quantity_sold: int
    unit_price_at_sale: Decimal
    unit_cost_at_sale: Decimal
    gross_revenue: Decimal
    external_ref: str | None = None
    import_batch_id: int | None = None
    created_at: datetime

    @property
    def cogs(self) -> Decimal:
        """Compute deterministic Cost of Goods Sold for this transaction line."""
        return (self.unit_cost_at_sale * self.quantity_sold).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP
        )

    @property
    def gross_profit(self) -> Decimal:
        """Compute deterministic gross profit for this transaction line."""
        return self.gross_revenue - self.cogs
