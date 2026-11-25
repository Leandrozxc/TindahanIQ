"""SQLite persistence repository for sales transactions and product sales summaries."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from tindahaniq.db.connection import DatabaseManager
from tindahaniq.exceptions import ValidationError
from tindahaniq.models.sales import (
    ProductSalesSummary,
    SaleRecordWithProduct,
    SalesTransaction,
    SalesTransactionCreate,
)
from tindahaniq.utils.validation import centavos_to_money, money_to_centavos


def _row_to_sale(row: sqlite3.Row) -> SalesTransaction:
    return SalesTransaction(
        id=int(row["id"]),
        product_id=int(row["product_id"]),
        sold_at=datetime.fromisoformat(row["sold_at"]),
        quantity_sold=int(row["quantity_sold"]),
        unit_price_at_sale=centavos_to_money(int(row["unit_price_centavos"])),
        unit_cost_at_sale=centavos_to_money(int(row["unit_cost_centavos"])),
        gross_revenue=centavos_to_money(int(row["gross_revenue_centavos"])),
        external_ref=row["external_ref"],
        import_batch_id=int(row["import_batch_id"]) if row["import_batch_id"] is not None else None,
        created_at=datetime.fromisoformat(row["created_at"]),
    )


class SalesRepository:
    """Data access operations for historical and operational sales transactions."""

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

    def exists_by_external_ref(
        self,
        external_ref: str,
        product_id: int,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> bool:
        with self._use_read(conn) as active_conn:
            row = active_conn.execute(
                """
                SELECT 1 FROM sales_transactions
                WHERE external_ref = ? AND product_id = ?
                LIMIT 1
                """,
                (external_ref, product_id),
            ).fetchone()
            return row is not None

    def create_sale(
        self,
        item: SalesTransactionCreate,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> SalesTransaction:
        now = datetime.now(UTC).isoformat(timespec="seconds")
        sold_iso = item.sold_at.astimezone(UTC).isoformat(timespec="seconds")
        with self._use_write(conn) as active_conn:
            if item.external_ref is not None and self.exists_by_external_ref(
                item.external_ref, item.product_id, conn=active_conn
            ):
                raise ValidationError(
                    f"Duplicate sale external_ref `{item.external_ref}` "
                    f"for product {item.product_id}",
                    user_message=(
                        f"Transaction `{item.external_ref}` for this product was already recorded."
                    ),
                    details={
                        "external_ref": item.external_ref,
                        "product_id": item.product_id,
                    },
                )

            try:
                cursor = active_conn.execute(
                    """
                    INSERT INTO sales_transactions (
                        external_ref, product_id, sold_at, quantity_sold,
                        unit_price_centavos, unit_cost_centavos,
                        gross_revenue_centavos, import_batch_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.external_ref,
                        item.product_id,
                        sold_iso,
                        item.quantity_sold,
                        money_to_centavos(item.unit_price_at_sale),
                        money_to_centavos(item.unit_cost_at_sale),
                        money_to_centavos(item.gross_revenue),
                        item.import_batch_id,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValidationError(
                    f"Integrity constraint failed while recording sale: {exc}",
                    user_message="Unable to record sale: referenced product does not exist.",
                    details={"product_id": item.product_id},
                ) from exc

            sale_id = int(cursor.lastrowid)
            row = active_conn.execute(
                "SELECT * FROM sales_transactions WHERE id = ?",
                (sale_id,),
            ).fetchone()
            assert row is not None
            return _row_to_sale(row)

    def list_sales(
        self,
        *,
        product_id: int | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> list[SalesTransaction]:
        clauses: list[str] = []
        params: list[object] = []
        if product_id is not None:
            clauses.append("product_id = ?")
            params.append(product_id)
        if start_at is not None:
            clauses.append("sold_at >= ?")
            params.append(start_at.astimezone(UTC).isoformat(timespec="seconds"))
        if end_at is not None:
            clauses.append("sold_at <= ?")
            params.append(end_at.astimezone(UTC).isoformat(timespec="seconds"))

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._use_read(conn) as active_conn:
            rows = active_conn.execute(
                f"SELECT * FROM sales_transactions {where_sql} ORDER BY sold_at ASC, id ASC",
                params,
            ).fetchall()
            return [_row_to_sale(row) for row in rows]

    def list_sales_with_product(
        self,
        *,
        product_id: int | None = None,
        category: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        newest_first: bool = True,
        limit: int | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> list[SaleRecordWithProduct]:
        """Return sales history joined with product metadata and optional filters."""
        clauses: list[str] = []
        params: list[object] = []
        if product_id is not None:
            clauses.append("s.product_id = ?")
            params.append(product_id)
        if category is not None and category.strip():
            clauses.append("LOWER(p.category) = ?")
            params.append(category.strip().lower())
        if start_at is not None:
            clauses.append("s.sold_at >= ?")
            params.append(start_at.astimezone(UTC).isoformat(timespec="seconds"))
        if end_at is not None:
            clauses.append("s.sold_at <= ?")
            params.append(end_at.astimezone(UTC).isoformat(timespec="seconds"))

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        order_sql = "DESC" if newest_first else "ASC"
        limit_sql = ""
        if limit is not None and limit > 0:
            limit_sql = "LIMIT ?"
            params.append(limit)

        with self._use_read(conn) as active_conn:
            rows = active_conn.execute(
                f"""
                SELECT
                    s.*,
                    p.sku,
                    p.name AS product_name,
                    p.category,
                    p.unit
                FROM sales_transactions s
                JOIN products p ON p.id = s.product_id
                {where_sql}
                ORDER BY s.sold_at {order_sql}, s.id {order_sql}
                {limit_sql}
                """,
                params,
            ).fetchall()
            return [
                SaleRecordWithProduct(
                    sale=_row_to_sale(row),
                    sku=str(row["sku"]),
                    product_name=str(row["product_name"]),
                    category=str(row["category"]),
                    unit=str(row["unit"]),
                )
                for row in rows
            ]

    def get_product_sales_summaries(
        self,
        *,
        active_only: bool = False,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> list[ProductSalesSummary]:
        """Aggregate operational transaction counts and units sold per catalog product."""
        join_clauses: list[str] = ["s.product_id = p.id"]
        params: list[object] = []
        if start_at is not None:
            join_clauses.append("s.sold_at >= ?")
            params.append(start_at.astimezone(UTC).isoformat(timespec="seconds"))
        if end_at is not None:
            join_clauses.append("s.sold_at <= ?")
            params.append(end_at.astimezone(UTC).isoformat(timespec="seconds"))

        where_sql = "WHERE p.is_active = 1" if active_only else ""
        with self._use_read(conn) as active_conn:
            rows = active_conn.execute(
                f"""
                SELECT
                    p.id AS product_id,
                    p.sku,
                    p.name AS product_name,
                    p.category,
                    p.unit,
                    p.is_active,
                    COUNT(s.id) AS transaction_count,
                    COALESCE(SUM(s.quantity_sold), 0) AS total_units_sold,
                    MAX(s.sold_at) AS last_sold_at
                FROM products p
                LEFT JOIN sales_transactions s ON {" AND ".join(join_clauses)}
                {where_sql}
                GROUP BY p.id, p.sku, p.name, p.category, p.unit, p.is_active
                ORDER BY total_units_sold DESC, p.name ASC
                """,
                params,
            ).fetchall()
            return [
                ProductSalesSummary(
                    product_id=int(row["product_id"]),
                    sku=str(row["sku"]),
                    product_name=str(row["product_name"]),
                    category=str(row["category"]),
                    unit=str(row["unit"]),
                    is_active=bool(row["is_active"]),
                    transaction_count=int(row["transaction_count"]),
                    total_units_sold=int(row["total_units_sold"]),
                    last_sold_at=datetime.fromisoformat(row["last_sold_at"])
                    if row["last_sold_at"] is not None
                    else None,
                )
                for row in rows
            ]
