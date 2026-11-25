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

    def list_all(
        self,
        *,
        active_only: bool = True,
        conn: sqlite3.Connection | None = None,
    ) -> list[ProductWithInventory]:
        clause = "WHERE p.is_active = 1" if active_only else ""
        with self._use_read(conn) as active_conn:
            rows = active_conn.execute(
                f"{_PRODUCT_INVENTORY_SELECT} {clause} ORDER BY p.name ASC, p.id ASC"
            ).fetchall()
            return [_row_to_product_with_inventory(row) for row in rows]

    def list_adjustments(
        self, product_id: int, *, conn: sqlite3.Connection | None = None
    ) -> list[StockAdjustment]:
        with self._use_read(conn) as active_conn:
            rows = active_conn.execute(
                """
                SELECT id, product_id, quantity_delta, reason, notes, created_at
                FROM inventory_adjustments
                WHERE product_id = ?
                ORDER BY id ASC
                """,
                (product_id,),
            ).fetchall()
            return [
                StockAdjustment(
                    id=int(row["id"]),
                    product_id=int(row["product_id"]),
                    quantity_delta=int(row["quantity_delta"]),
                    reason=AdjustmentReason(row["reason"]),
                    notes=row["notes"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
                for row in rows
            ]
