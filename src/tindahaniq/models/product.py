"""Pydantic domain schemas for products, inventory state, adjustments, and consistency."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tindahaniq.exceptions import ValidationError
from tindahaniq.models.common import AdjustmentReason
from tindahaniq.utils.validation import (
    normalize_sku,
    parse_money_decimal,
    parse_non_negative_int,
    parse_nonzero_int,
    sanitize_text,
)

ConsistencySeverity = Literal["error", "warning"]


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


class ProductUpdate(BaseModel):
    """Partial update input model for modifying product metadata, pricing, or thresholds."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    category: str | None = None
    unit: str | None = None
    unit_cost: Decimal | None = None
    selling_price: Decimal | None = None
    reorder_point: int | None = None
    lead_time_days: int | None = None

    @field_validator("name", mode="before")
    @classmethod
    def _validate_name(cls, value: object) -> str | None:
        if value is None:
            return None
        return sanitize_text(value, field_name="product_name", max_length=120)

    @field_validator("category", mode="before")
    @classmethod
    def _validate_category(cls, value: object) -> str | None:
        if value is None:
            return None
        return sanitize_text(value, field_name="category", max_length=64)

    @field_validator("unit", mode="before")
    @classmethod
    def _validate_unit(cls, value: object) -> str | None:
        if value is None:
            return None
        return sanitize_text(value, field_name="unit", max_length=32)

    @field_validator("unit_cost", mode="before")
    @classmethod
    def _validate_unit_cost(cls, value: object) -> Decimal | None:
        if value is None:
            return None
        return parse_money_decimal(value, field_name="unit_cost", allow_zero=True)

    @field_validator("selling_price", mode="before")
    @classmethod
    def _validate_selling_price(cls, value: object) -> Decimal | None:
        if value is None:
            return None
        return parse_money_decimal(value, field_name="selling_price", allow_zero=False)

    @field_validator("reorder_point", mode="before")
    @classmethod
    def _validate_reorder_point(cls, value: object) -> int | None:
        if value is None:
            return None
        return parse_non_negative_int(value, field_name="reorder_point", min_value=0)

    @field_validator("lead_time_days", mode="before")
    @classmethod
    def _validate_lead_time_days(cls, value: object) -> int | None:
        if value is None:
            return None
        return parse_non_negative_int(value, field_name="lead_time_days", min_value=1)

    @model_validator(mode="after")
    def _ensure_non_empty_update(self) -> ProductUpdate:
        if all(
            getattr(self, field) is None
            for field in (
                "name",
                "category",
                "unit",
                "unit_cost",
                "selling_price",
                "reorder_point",
                "lead_time_days",
            )
        ):
            raise ValidationError(
                "Empty ProductUpdate payload",
                user_message="Provide at least one product field to update.",
                details={"field": "product_update"},
            )
        return self


class StockAdjustmentCreate(BaseModel):
    """Validated input model for manual restocks, spoilage, or stock corrections."""

    model_config = ConfigDict(extra="forbid")

    product_id: int
    quantity_delta: int
    reason: AdjustmentReason = AdjustmentReason.MANUAL_ADJUSTMENT
    notes: str | None = None

    @field_validator("product_id", mode="before")
    @classmethod
    def _validate_product_id(cls, value: object) -> int:
        return parse_non_negative_int(value, field_name="product_id", min_value=1)

    @field_validator("quantity_delta", mode="before")
    @classmethod
    def _validate_delta(cls, value: object) -> int:
        return parse_nonzero_int(value, field_name="quantity_delta")

    @field_validator("notes", mode="before")
    @classmethod
    def _validate_notes(cls, value: object) -> str | None:
        cleaned = sanitize_text(value, field_name="notes", max_length=240, allow_empty=True)
        return cleaned or None


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

    @property
    def is_out_of_stock(self) -> bool:
        """True when shelf stock is completely depleted."""
        return self.current_stock == 0

    @property
    def is_low_stock(self) -> bool:
        """True when shelf stock is at or below the product's reorder point."""
        return self.current_stock <= self.reorder_point


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


class ConsistencyIssue(BaseModel):
    """Single structural error or pricing warning found during consistency verification."""

    model_config = ConfigDict(frozen=True)

    severity: ConsistencySeverity
    code: str
    entity_id: int | None = None
    sku: str | None = None
    message: str


class DataConsistencyReport(BaseModel):
    """Summary of database ledger, relational, and arithmetic consistency checks."""

    model_config = ConfigDict(frozen=True)

    is_consistent: bool
    products_checked: int
    sales_checked: int
    issues: tuple[ConsistencyIssue, ...] = ()

    @property
    def error_count(self) -> int:
        """Count of structural consistency errors."""
        return sum(1 for issue in self.issues if issue.severity == "error")

    @property
    def warning_count(self) -> int:
        """Count of non-structural business data warnings."""
        return sum(1 for issue in self.issues if issue.severity == "warning")
