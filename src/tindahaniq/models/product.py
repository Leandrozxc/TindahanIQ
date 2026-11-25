"""Pydantic domain schemas for products, inventory state, and stock adjustments."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tindahaniq.models.common import AdjustmentReason
from tindahaniq.utils.validation import (
    normalize_sku,
    parse_money_decimal,
    parse_non_negative_int,
    sanitize_text,
)


class ProductCreate(BaseModel):
    """Validated input model for creating or importing a catalog product and its stock."""

    model_config = ConfigDict(extra="forbid")

    sku: str | None = None
    name: str
    category: str = "Uncategorized"
    unit: str = "pcs"
    unit_cost: Decimal
    selling_price: Decimal
    current_stock: int = 0
    reorder_point: int = 10
    lead_time_days: int = 1

    @field_validator("name", mode="before")
    @classmethod
    def _validate_name(cls, value: object) -> str:
        return sanitize_text(value, field_name="product_name", max_length=120)

    @field_validator("category", mode="before")
    @classmethod
    def _validate_category(cls, value: object) -> str:
        cleaned = sanitize_text(value, field_name="category", max_length=64, allow_empty=True)
        return cleaned or "Uncategorized"

    @field_validator("unit", mode="before")
    @classmethod
    def _validate_unit(cls, value: object) -> str:
        cleaned = sanitize_text(value, field_name="unit", max_length=32, allow_empty=True)
        return cleaned or "pcs"

    @field_validator("unit_cost", mode="before")
    @classmethod
    def _validate_unit_cost(cls, value: object) -> Decimal:
        return parse_money_decimal(value, field_name="unit_cost", allow_zero=True)

    @field_validator("selling_price", mode="before")
    @classmethod
    def _validate_selling_price(cls, value: object) -> Decimal:
        return parse_money_decimal(value, field_name="selling_price", allow_zero=False)

    @field_validator("current_stock", mode="before")
    @classmethod
    def _validate_current_stock(cls, value: object) -> int:
        return parse_non_negative_int(value, field_name="current_stock", min_value=0)

    @field_validator("reorder_point", mode="before")
    @classmethod
    def _validate_reorder_point(cls, value: object) -> int:
        return parse_non_negative_int(value, field_name="reorder_point", min_value=0)

    @field_validator("lead_time_days", mode="before")
    @classmethod
    def _validate_lead_time_days(cls, value: object) -> int:
        return parse_non_negative_int(value, field_name="lead_time_days", min_value=1)

    @model_validator(mode="after")
    def _finalize_sku(self) -> ProductCreate:
        self.sku = normalize_sku(
            self.sku,
            fallback_name=self.name,
            fallback_unit=self.unit,
        )
        return self


class Product(BaseModel):
    """Persisted retail product entity."""

    model_config = ConfigDict(frozen=True)

    id: int
    sku: str
    name: str
    category: str
    unit: str
    unit_cost: Decimal
    selling_price: Decimal
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    @property
    def unit_profit(self) -> Decimal:
        """Return deterministic gross profit per unit at current prices."""
        return self.selling_price - self.unit_cost


class InventoryRecord(BaseModel):
    """Persisted inventory state for a single product."""

    model_config = ConfigDict(frozen=True)

    product_id: int
    current_stock: int = Field(ge=0)
    reorder_point: int = Field(ge=0)
    lead_time_days: int = Field(ge=1)
    last_restocked_at: datetime | None = None
    updated_at: datetime


class ProductWithInventory(BaseModel):
    """Combined view of catalog metadata and live inventory counts."""

    model_config = ConfigDict(frozen=True)

    product: Product
    inventory: InventoryRecord


class StockAdjustment(BaseModel):
    """Audit log entry recording a stock change event."""

    model_config = ConfigDict(frozen=True)

    id: int
    product_id: int
    quantity_delta: int
    reason: AdjustmentReason
    notes: str | None = None
    created_at: datetime
