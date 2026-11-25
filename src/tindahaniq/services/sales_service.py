"""Operational sales transaction management, atomic checkout, and sales tracking service."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from tindahaniq.db.connection import DatabaseManager
from tindahaniq.db.repositories import ProductRepository, SalesRepository
from tindahaniq.exceptions import ValidationError
from tindahaniq.logging_config import get_logger
from tindahaniq.models.common import AdjustmentReason
from tindahaniq.models.sales import (
    ProductSalesSummary,
    SaleItemInput,
    SaleRecordWithProduct,
    SalesTransaction,
    SalesTransactionCreate,
)


def _validate_date_window(start_at: datetime | None, end_at: datetime | None) -> None:
    if start_at is not None and end_at is not None:
        s_utc = (
            start_at.replace(tzinfo=UTC) if start_at.tzinfo is None else start_at.astimezone(UTC)
        )
        e_utc = end_at.replace(tzinfo=UTC) if end_at.tzinfo is None else end_at.astimezone(UTC)
        if s_utc > e_utc:
            raise ValidationError(
                f"Invalid date window: start_at ({s_utc}) > end_at ({e_utc})",
                user_message="Start date must be earlier than or equal to the end date.",
                details={"field": "date_range"},
            )


class SalesService:
    """Record live or historical sales, manage stock deductions, and query sales history."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db
        self._products = ProductRepository(db)
        self._sales = SalesRepository(db)
        self._logger = get_logger("sales_service")

    def record_sale(
        self,
        item: SaleItemInput,
        *,
        deduct_stock: bool = True,
    ) -> SalesTransaction:
        """Record a single product sale, deducting stock atomically by default."""
        return self.record_sales_batch([item], deduct_stock=deduct_stock)[0]

    def record_sales_batch(
        self,
        items: Sequence[SaleItemInput],
        *,
        deduct_stock: bool = True,
    ) -> list[SalesTransaction]:
        """Record one or more basket sale lines atomically in a single transaction."""
        if not items:
            raise ValidationError(
                "Empty items sequence passed to record_sales_batch",
                user_message="At least one sale item is required.",
                details={"field": "items"},
            )

        recorded: list[SalesTransaction] = []
        default_sold_at = datetime.now(UTC)

        with self._db.transaction() as conn:
            for item in items:
                product_record = self._products.get_by_id(item.product_id, conn=conn)
                if product_record is None:
                    raise ValidationError(
                        f"Product id={item.product_id} not found during sale checkout",
                        user_message=f"Product #{item.product_id} does not exist.",
                        details={"product_id": item.product_id},
                    )

                if deduct_stock and not product_record.product.is_active:
                    raise ValidationError(
                        f"Attempted live sale on inactive product id={item.product_id}",
                        user_message=(
                            f"`{product_record.product.name}` is archived and cannot be sold "
                            "until reactivated."
                        ),
                        details={"product_id": item.product_id, "sku": product_record.product.sku},
                    )

                if deduct_stock:
                    note = (
                        f"Sale ({item.external_ref})"
                        if item.external_ref
                        else "Operational sale deduction"
                    )
                    self._products.apply_stock_delta(
                        item.product_id,
                        quantity_delta=-item.quantity_sold,
                        reason=AdjustmentReason.SALE,
                        notes=note,
                        conn=conn,
                    )

                unit_price = (
                    item.unit_price_override
                    if item.unit_price_override is not None
                    else product_record.product.selling_price
                )
                sale_create = SalesTransactionCreate(
                    product_id=item.product_id,
                    sold_at=item.sold_at or default_sold_at,
                    quantity_sold=item.quantity_sold,
                    unit_price_at_sale=unit_price,
                    unit_cost_at_sale=product_record.product.unit_cost,
                    external_ref=item.external_ref,
                )
                created_sale = self._sales.create_sale(sale_create, conn=conn)
                recorded.append(created_sale)

        self._logger.info(
            "Recorded %d sale line(s) (deduct_stock=%s)",
            len(recorded),
            deduct_stock,
        )
        return recorded

    def get_sales_history(
        self,
        *,
        product_id: int | None = None,
        category: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        newest_first: bool = True,
        limit: int | None = None,
    ) -> list[SaleRecordWithProduct]:
        """Return sales transactions enriched with product metadata."""
        _validate_date_window(start_at, end_at)
        return self._sales.list_sales_with_product(
            product_id=product_id,
            category=category,
            start_at=start_at,
            end_at=end_at,
            newest_first=newest_first,
            limit=limit,
        )

    def get_product_sales_tracking(
        self,
        *,
        active_only: bool = False,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> list[ProductSalesSummary]:
        """Return per-product sales counts, total units sold, and last sale timestamps."""
        _validate_date_window(start_at, end_at)
        return self._sales.get_product_sales_summaries(
            active_only=active_only,
            start_at=start_at,
            end_at=end_at,
        )
