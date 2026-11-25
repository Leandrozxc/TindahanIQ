"""SQLite persistence repository for products, inventory records, and stock adjustments."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from tindahaniq.db.connection import DatabaseManager
from tindahaniq.exceptions import ValidationError
from tindahaniq.models.common import AdjustmentReason
from tindahaniq.models.product import (
    InventoryRecord,
    Product,
    ProductCreate,
    ProductUpdate,
    ProductWithInventory,
    StockAdjustment,
)
from tindahaniq.utils.validation import centavos_to_money, money_to_centavos

_PRODUCT_INVENTORY_SELECT = """
SELECT
    p.id,
    p.sku,
    p.name,
    p.category,
    p.unit,
    p.unit_cost_centavos,
    p.selling_price_centavos,
    p.is_active,
    p.created_at,
    p.updated_at,
    i.current_stock,
    i.reorder_point,
    i.lead_time_days,
    i.last_restocked_at,
    i.updated_at AS inventory_updated_at
FROM products p
JOIN inventory i ON i.product_id = p.id
"""


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _row_to_product_with_inventory(row: sqlite3.Row) -> ProductWithInventory:
    product = Product(
        id=int(row["id"]),
        sku=str(row["sku"]),
        name=str(row["name"]),
        category=str(row["category"]),
        unit=str(row["unit"]),
        unit_cost=centavos_to_money(int(row["unit_cost_centavos"])),
        selling_price=centavos_to_money(int(row["selling_price_centavos"])),
        is_active=bool(row["is_active"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )
    last_restocked = (
        datetime.fromisoformat(row["last_restocked_at"])
        if row["last_restocked_at"] is not None
        else None
    )
    inventory = InventoryRecord(
        product_id=product.id,
        current_stock=int(row["current_stock"]),
        reorder_point=int(row["reorder_point"]),
        lead_time_days=int(row["lead_time_days"]),
        last_restocked_at=last_restocked,
        updated_at=datetime.fromisoformat(row["inventory_updated_at"]),
    )
    return ProductWithInventory(product=product, inventory=inventory)


def _row_to_adjustment(row: sqlite3.Row) -> StockAdjustment:
    return StockAdjustment(
        id=int(row["id"]),
        product_id=int(row["product_id"]),
        quantity_delta=int(row["quantity_delta"]),
        reason=AdjustmentReason(row["reason"]),
        notes=row["notes"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


class ProductRepository:
    """Data access operations for catalog products, inventory, and adjustment logs."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    @contextmanager
    def _use_read(self, conn: sqlite3.Connection | None) -> Iterator[sqlite3.Connection]:
        if conn is not None:
            yield conn
        else:
            with self._db.read_connection() as managed:
                yield managed

    @contextmanager
    def _use_write(self, conn: sqlite3.Connection | None) -> Iterator[sqlite3.Connection]:
        if conn is not None:
            yield conn
        else:
            with self._db.transaction() as managed:
                yield managed

    def create_product_with_inventory(
        self,
        item: ProductCreate,
        *,
        adjustment_reason: AdjustmentReason = AdjustmentReason.INITIAL_IMPORT,
        notes: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> ProductWithInventory:
        """Insert a new product, its inventory row, and an initial stock adjustment if > 0."""
        assert item.sku is not None
        now = _utc_now_iso()
        with self._use_write(conn) as active_conn:
            existing = self.get_by_sku(item.sku, conn=active_conn)
            if existing is not None:
                raise ValidationError(
                    f"Duplicate product SKU `{item.sku}`",
                    user_message=f"A product with SKU `{item.sku}` already exists.",
                    details={"sku": item.sku},
                )

            cursor = active_conn.execute(
                """
                INSERT INTO products (
                    sku, name, category, unit,
                    unit_cost_centavos, selling_price_centavos,
                    is_active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    item.sku,
                    item.name,
                    item.category,
                    item.unit,
                    money_to_centavos(item.unit_cost),
                    money_to_centavos(item.selling_price),
                    now,
                    now,
                ),
            )
            product_id = int(cursor.lastrowid)
            last_restocked = now if item.current_stock > 0 else None
            active_conn.execute(
                """
                INSERT INTO inventory (
                    product_id, current_stock, reorder_point,
                    lead_time_days, last_restocked_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    product_id,
                    item.current_stock,
                    item.reorder_point,
                    item.lead_time_days,
                    last_restocked,
                    now,
                ),
            )
            if item.current_stock > 0:
                active_conn.execute(
                    """
                    INSERT INTO inventory_adjustments (
                        product_id, quantity_delta, reason, notes, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (product_id, item.current_stock, adjustment_reason.value, notes, now),
                )

            created = self.get_by_id(product_id, conn=active_conn)
            assert created is not None
            return created

    def update_product(
        self,
        product_id: int,
        changes: ProductUpdate,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> ProductWithInventory:
        """Update catalog fields and/or reorder thresholds without altering stock or past sales."""
        now = _utc_now_iso()
        with self._use_write(conn) as active_conn:
            existing = self.get_by_id(product_id, conn=active_conn)
            if existing is None:
                raise ValidationError(
                    f"Product id={product_id} not found",
                    user_message=f"Product #{product_id} could not be found.",
                    details={"product_id": product_id},
                )

            new_name = changes.name if changes.name is not None else existing.product.name
            new_cat = (
                changes.category if changes.category is not None else existing.product.category
            )
            new_unit = changes.unit if changes.unit is not None else existing.product.unit
            new_cost = (
                changes.unit_cost if changes.unit_cost is not None else existing.product.unit_cost
            )
            new_price = (
                changes.selling_price
                if changes.selling_price is not None
                else existing.product.selling_price
            )
            new_reorder = (
                changes.reorder_point
                if changes.reorder_point is not None
                else existing.inventory.reorder_point
            )
            new_lead = (
                changes.lead_time_days
                if changes.lead_time_days is not None
                else existing.inventory.lead_time_days
            )

            active_conn.execute(
                """
                UPDATE products
                SET name = ?,
                    category = ?,
                    unit = ?,
                    unit_cost_centavos = ?,
                    selling_price_centavos = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    new_name,
                    new_cat,
                    new_unit,
                    money_to_centavos(new_cost),
                    money_to_centavos(new_price),
                    now,
                    product_id,
                ),
            )
            active_conn.execute(
                """
                UPDATE inventory
                SET reorder_point = ?,
                    lead_time_days = ?,
                    updated_at = ?
                WHERE product_id = ?
                """,
                (new_reorder, new_lead, now, product_id),
            )

            updated = self.get_by_id(product_id, conn=active_conn)
            assert updated is not None
            return updated

    def set_active_status(
        self,
        product_id: int,
        *,
        is_active: bool,
        conn: sqlite3.Connection | None = None,
    ) -> ProductWithInventory:
        """Soft-archive or reactivate a product without deleting historical records."""
        now = _utc_now_iso()
        with self._use_write(conn) as active_conn:
            existing = self.get_by_id(product_id, conn=active_conn)
            if existing is None:
                raise ValidationError(
                    f"Product id={product_id} not found",
                    user_message=f"Product #{product_id} could not be found.",
                    details={"product_id": product_id},
                )
            active_conn.execute(
                "UPDATE products SET is_active = ?, updated_at = ? WHERE id = ?",
                (1 if is_active else 0, now, product_id),
            )
            updated = self.get_by_id(product_id, conn=active_conn)
            assert updated is not None
            return updated

    def apply_stock_delta(
        self,
        product_id: int,
        *,
        quantity_delta: int,
        reason: AdjustmentReason,
        notes: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> tuple[ProductWithInventory, StockAdjustment]:
        """Atomically update current_stock and append an audit entry, rejecting negative stock."""
        if quantity_delta == 0:
            raise ValidationError(
                "Zero quantity_delta passed to apply_stock_delta",
                user_message="Stock adjustment quantity cannot be zero.",
                details={"field": "quantity_delta"},
            )

        now = _utc_now_iso()
        with self._use_write(conn) as active_conn:
            existing = self.get_by_id(product_id, conn=active_conn)
            if existing is None:
                raise ValidationError(
                    f"Product id={product_id} not found",
                    user_message=f"Product #{product_id} could not be found.",
                    details={"product_id": product_id},
                )

            new_stock = existing.inventory.current_stock + quantity_delta
            if new_stock < 0:
                requested = abs(quantity_delta)
                raise ValidationError(
                    f"Insufficient stock for product {product_id}: "
                    f"have={existing.inventory.current_stock}, requested_deduction={requested}",
                    user_message=(
                        f"Insufficient stock for `{existing.product.name}`: "
                        f"cannot deduct {requested} {existing.product.unit} "
                        f"(only {existing.inventory.current_stock} in stock)."
                    ),
                    details={
                        "product_id": product_id,
                        "sku": existing.product.sku,
                        "current_stock": existing.inventory.current_stock,
                        "quantity_delta": quantity_delta,
                    },
                )

            is_restock = quantity_delta > 0 and reason in {
                AdjustmentReason.RESTOCK,
                AdjustmentReason.INITIAL_IMPORT,
            }
            last_restocked = (
                now
                if is_restock
                else (
                    existing.inventory.last_restocked_at.isoformat(timespec="seconds")
                    if existing.inventory.last_restocked_at is not None
                    else None
                )
            )
            active_conn.execute(
                """
                UPDATE inventory
                SET current_stock = ?,
                    last_restocked_at = ?,
                    updated_at = ?
                WHERE product_id = ?
                """,
                (new_stock, last_restocked, now, product_id),
            )
            cursor = active_conn.execute(
                """
                INSERT INTO inventory_adjustments (
                    product_id, quantity_delta, reason, notes, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (product_id, quantity_delta, reason.value, notes, now),
            )
            adj_id = int(cursor.lastrowid)
            adj_row = active_conn.execute(
                """
                SELECT id, product_id, quantity_delta, reason, notes, created_at
                FROM inventory_adjustments
                WHERE id = ?
                """,
                (adj_id,),
            ).fetchone()
            assert adj_row is not None

            updated = self.get_by_id(product_id, conn=active_conn)
            assert updated is not None
            return updated, _row_to_adjustment(adj_row)

    def upsert_product_from_import(
        self,
        item: ProductCreate,
        *,
        notes: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> tuple[ProductWithInventory, bool]:
        """Create a new product or synchronize an existing SKU during CSV import."""
        assert item.sku is not None
        with self._use_write(conn) as active_conn:
            existing = self.get_by_sku(item.sku, conn=active_conn)
            if existing is None:
                record = self.create_product_with_inventory(
                    item,
                    adjustment_reason=AdjustmentReason.INITIAL_IMPORT,
                    notes=notes,
                    conn=active_conn,
                )
                return record, True

            now = _utc_now_iso()
            product_id = existing.product.id
            active_conn.execute(
                """
                UPDATE products
                SET name = ?,
                    category = ?,
                    unit = ?,
                    unit_cost_centavos = ?,
                    selling_price_centavos = ?,
                    is_active = 1,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    item.name,
                    item.category,
                    item.unit,
                    money_to_centavos(item.unit_cost),
                    money_to_centavos(item.selling_price),
                    now,
                    product_id,
                ),
            )

            stock_delta = item.current_stock - existing.inventory.current_stock
            last_restocked = (
                now
                if stock_delta > 0
                else (
                    existing.inventory.last_restocked_at.isoformat(timespec="seconds")
                    if existing.inventory.last_restocked_at
                    else None
                )
            )
            active_conn.execute(
                """
                UPDATE inventory
                SET current_stock = ?,
                    reorder_point = ?,
                    lead_time_days = ?,
                    last_restocked_at = ?,
                    updated_at = ?
                WHERE product_id = ?
                """,
                (
                    item.current_stock,
                    item.reorder_point,
                    item.lead_time_days,
                    last_restocked,
                    now,
                    product_id,
                ),
            )
            if stock_delta != 0:
                active_conn.execute(
                    """
                    INSERT INTO inventory_adjustments (
                        product_id, quantity_delta, reason, notes, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (product_id, stock_delta, AdjustmentReason.CSV_SYNC.value, notes, now),
                )

            updated = self.get_by_id(product_id, conn=active_conn)
            assert updated is not None
            return updated, False

    def get_by_id(
        self, product_id: int, *, conn: sqlite3.Connection | None = None
    ) -> ProductWithInventory | None:
        with self._use_read(conn) as active_conn:
            row = active_conn.execute(
                f"{_PRODUCT_INVENTORY_SELECT} WHERE p.id = ?",
                (product_id,),
            ).fetchone()
            return _row_to_product_with_inventory(row) if row else None

    def get_by_sku(
        self, sku: str, *, conn: sqlite3.Connection | None = None
    ) -> ProductWithInventory | None:
        normalized = sku.strip().upper()
        with self._use_read(conn) as active_conn:
            row = active_conn.execute(
                f"{_PRODUCT_INVENTORY_SELECT} WHERE p.sku = ?",
                (normalized,),
            ).fetchone()
            return _row_to_product_with_inventory(row) if row else None

    def find_by_name_case_insensitive(
        self, name: str, *, conn: sqlite3.Connection | None = None
    ) -> list[ProductWithInventory]:
        target = " ".join(name.split()).lower()
        with self._use_read(conn) as active_conn:
            rows = active_conn.execute(
                f"{_PRODUCT_INVENTORY_SELECT} WHERE LOWER(p.name) = ? ORDER BY p.id ASC",
                (target,),
            ).fetchall()
            return [_row_to_product_with_inventory(row) for row in rows]

    def search_products(
        self,
        *,
        query: str | None = None,
        category: str | None = None,
        active_only: bool = True,
        low_stock_only: bool = False,
        out_of_stock_only: bool = False,
        conn: sqlite3.Connection | None = None,
    ) -> list[ProductWithInventory]:
        """Search and filter catalog items by text query, category, and stock thresholds."""
        clauses: list[str] = []
        params: list[object] = []

        if active_only:
            clauses.append("p.is_active = 1")
        if category is not None and category.strip():
            clauses.append("LOWER(p.category) = ?")
            params.append(category.strip().lower())
        if query is not None and query.strip():
            escaped = (
                query.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            )
            pattern = f"%{escaped}%"
            clauses.append(
                "(LOWER(p.name) LIKE ? ESCAPE '\\' "
                "OR LOWER(p.sku) LIKE ? ESCAPE '\\' "
                "OR LOWER(p.category) LIKE ? ESCAPE '\\')"
            )
            params.extend([pattern, pattern, pattern])
        if out_of_stock_only:
            clauses.append("i.current_stock = 0")
        elif low_stock_only:
            clauses.append("i.current_stock <= i.reorder_point")

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._use_read(conn) as active_conn:
            rows = active_conn.execute(
                f"{_PRODUCT_INVENTORY_SELECT} {where_sql} ORDER BY p.name ASC, p.id ASC",
                params,
            ).fetchall()
            return [_row_to_product_with_inventory(row) for row in rows]

    def list_categories(
        self,
        *,
        active_only: bool = True,
        conn: sqlite3.Connection | None = None,
    ) -> list[str]:
        clause = "WHERE is_active = 1" if active_only else ""
        with self._use_read(conn) as active_conn:
            rows = active_conn.execute(
                f"SELECT DISTINCT category FROM products {clause} ORDER BY category ASC"
            ).fetchall()
            return [str(row["category"]) for row in rows]

    def list_all(
        self,
        *,
        active_only: bool = True,
        conn: sqlite3.Connection | None = None,
    ) -> list[ProductWithInventory]:
        return self.search_products(active_only=active_only, conn=conn)

    def list_adjustments(
        self,
        product_id: int | None = None,
        *,
        limit: int | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> list[StockAdjustment]:
        clauses: list[str] = []
        params: list[object] = []
        if product_id is not None:
            clauses.append("product_id = ?")
            params.append(product_id)

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        limit_sql = ""
        if limit is not None and limit > 0:
            limit_sql = "LIMIT ?"
            params.append(limit)

        with self._use_read(conn) as active_conn:
            rows = active_conn.execute(
                f"""
                SELECT id, product_id, quantity_delta, reason, notes, created_at
                FROM inventory_adjustments
                {where_sql}
                ORDER BY id ASC
                {limit_sql}
                """,
                params,
            ).fetchall()
            return [_row_to_adjustment(row) for row in rows]
