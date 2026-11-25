"""Operational product catalog, stock tracking, and inventory adjustment service."""

from __future__ import annotations

from tindahaniq.db.connection import DatabaseManager
from tindahaniq.db.repositories import ProductRepository
from tindahaniq.exceptions import ValidationError
from tindahaniq.logging_config import get_logger
from tindahaniq.models.common import AdjustmentReason
from tindahaniq.models.product import (
    ProductCreate,
    ProductUpdate,
    ProductWithInventory,
    StockAdjustment,
    StockAdjustmentCreate,
)
from tindahaniq.utils.validation import parse_non_negative_int, sanitize_text


class InventoryService:
    """Manage retail product records, live shelf quantities, and stock adjustments."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db
        self._products = ProductRepository(db)
        self._logger = get_logger("inventory_service")

    def create_product(
        self,
        item: ProductCreate,
        *,
        notes: str | None = None,
    ) -> ProductWithInventory:
        """Create a new product and initialize its inventory record."""
        clean_notes = (
            sanitize_text(notes, field_name="notes", max_length=240, allow_empty=True) or None
        )
        created = self._products.create_product_with_inventory(
            item,
            adjustment_reason=AdjustmentReason.INITIAL_IMPORT,
            notes=clean_notes,
        )
        self._logger.info(
            "Created product id=%d sku=%s initial_stock=%d",
            created.product.id,
            created.product.sku,
            created.inventory.current_stock,
        )
        return created

    def update_product(
        self,
        product_id: int,
        changes: ProductUpdate,
    ) -> ProductWithInventory:
        """Update product details, pricing, or reorder settings without altering stock."""
        checked_id = parse_non_negative_int(product_id, field_name="product_id", min_value=1)
        updated = self._products.update_product(checked_id, changes)
        self._logger.info("Updated product id=%d sku=%s", updated.product.id, updated.product.sku)
        return updated

    def deactivate_product(self, product_id: int) -> ProductWithInventory:
        """Soft-archive a product while preserving all historical sales and adjustments."""
        checked_id = parse_non_negative_int(product_id, field_name="product_id", min_value=1)
        updated = self._products.set_active_status(checked_id, is_active=False)
        self._logger.info("Archived product id=%d sku=%s", updated.product.id, updated.product.sku)
        return updated

    def reactivate_product(self, product_id: int) -> ProductWithInventory:
        """Restore a previously archived product to active catalog status."""
        checked_id = parse_non_negative_int(product_id, field_name="product_id", min_value=1)
        updated = self._products.set_active_status(checked_id, is_active=True)
        self._logger.info(
            "Reactivated product id=%d sku=%s", updated.product.id, updated.product.sku
        )
        return updated

    def get_product(self, product_id: int) -> ProductWithInventory:
        """Return a product and its inventory state by ID, or raise ValidationError."""
        checked_id = parse_non_negative_int(product_id, field_name="product_id", min_value=1)
        record = self._products.get_by_id(checked_id)
        if record is None:
            raise ValidationError(
                f"Product id={checked_id} does not exist",
                user_message=f"Product #{checked_id} could not be found.",
                details={"product_id": checked_id},
            )
        return record

    def find_product_by_sku(self, sku: str) -> ProductWithInventory | None:
        """Look up a product by SKU (case-insensitive)."""
        if not sku or not sku.strip():
            return None
        return self._products.get_by_sku(sku)

    def list_inventory(
        self,
        *,
        query: str | None = None,
        category: str | None = None,
        active_only: bool = True,
        low_stock_only: bool = False,
        out_of_stock_only: bool = False,
    ) -> list[ProductWithInventory]:
        """List and filter store products alongside live inventory records."""
        return self._products.search_products(
            query=query,
            category=category,
            active_only=active_only,
            low_stock_only=low_stock_only,
            out_of_stock_only=out_of_stock_only,
        )

    def list_categories(self, *, active_only: bool = True) -> list[str]:
        """Return sorted distinct product categories."""
        return self._products.list_categories(active_only=active_only)

    def adjust_stock(
        self,
        adjustment: StockAdjustmentCreate,
    ) -> tuple[ProductWithInventory, StockAdjustment]:
        """Apply a signed stock adjustment (restock, spoilage, manual adjustment) atomically."""
        updated, adj_record = self._products.apply_stock_delta(
            adjustment.product_id,
            quantity_delta=adjustment.quantity_delta,
            reason=adjustment.reason,
            notes=adjustment.notes,
        )
        self._logger.info(
            "Adjusted stock product_id=%d delta=%d new_stock=%d reason=%s",
            adjustment.product_id,
            adjustment.quantity_delta,
            updated.inventory.current_stock,
            adjustment.reason.value,
        )
        return updated, adj_record

    def restock_product(
        self,
        product_id: int,
        quantity_added: int,
        *,
        notes: str | None = None,
    ) -> tuple[ProductWithInventory, StockAdjustment]:
        """Add incoming supplier stock (`quantity_added >= 1`) and update `last_restocked_at`."""
        checked_qty = parse_non_negative_int(
            quantity_added, field_name="quantity_added", min_value=1
        )
        payload = StockAdjustmentCreate(
            product_id=product_id,
            quantity_delta=checked_qty,
            reason=AdjustmentReason.RESTOCK,
            notes=notes,
        )
        return self.adjust_stock(payload)

    def reconcile_stock_count(
        self,
        product_id: int,
        counted_stock: int,
        *,
        reason: AdjustmentReason = AdjustmentReason.MANUAL_ADJUSTMENT,
        notes: str | None = None,
    ) -> tuple[ProductWithInventory, StockAdjustment | None]:
        """Reconcile shelf stock to an exact physical count, logging the delta if changed."""
        checked_id = parse_non_negative_int(product_id, field_name="product_id", min_value=1)
        target_stock = parse_non_negative_int(
            counted_stock, field_name="counted_stock", min_value=0
        )
        clean_notes = (
            sanitize_text(notes, field_name="notes", max_length=240, allow_empty=True) or None
        )

        with self._db.transaction() as conn:
            existing = self._products.get_by_id(checked_id, conn=conn)
            if existing is None:
                raise ValidationError(
                    f"Product id={checked_id} not found during stock reconciliation",
                    user_message=f"Product #{checked_id} could not be found.",
                    details={"product_id": checked_id},
                )

            delta = target_stock - existing.inventory.current_stock
            if delta == 0:
                return existing, None

            updated, adj = self._products.apply_stock_delta(
                checked_id,
                quantity_delta=delta,
                reason=reason,
                notes=clean_notes or f"Stocktake count reconciled to {target_stock}",
                conn=conn,
            )
            return updated, adj

    def get_adjustment_history(
        self,
        *,
        product_id: int | None = None,
        limit: int | None = None,
    ) -> list[StockAdjustment]:
        """Return chronological stock adjustment audit entries."""
        return self._products.list_adjustments(product_id=product_id, limit=limit)
