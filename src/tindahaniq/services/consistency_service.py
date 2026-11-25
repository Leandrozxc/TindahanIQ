"""Deterministic relational, stock-ledger, and arithmetic consistency verifier."""

from __future__ import annotations

from decimal import ROUND_HALF_UP

from tindahaniq.db.connection import DatabaseManager
from tindahaniq.models.product import ConsistencyIssue, DataConsistencyReport
from tindahaniq.utils.validation import TWO_PLACES, centavos_to_money, money_to_centavos


class ConsistencyService:
    """Audit store records for orphan rows, stock ledger drift, and revenue discrepancies."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    def verify_data_consistency(self) -> DataConsistencyReport:
        """Run deterministic consistency checks across products, inventory, and sales."""
        issues: list[ConsistencyIssue] = []

        with self._db.read_connection() as conn:
            total_products = int(
                conn.execute("SELECT COUNT(*) AS cnt FROM products").fetchone()["cnt"]
            )
            total_sales = int(
                conn.execute("SELECT COUNT(*) AS cnt FROM sales_transactions").fetchone()["cnt"]
            )

            # 1. Every product must have a 1-to-1 inventory row
            orphan_products = conn.execute(
                """
                SELECT p.id, p.sku, p.name
                FROM products p
                LEFT JOIN inventory i ON i.product_id = p.id
                WHERE i.product_id IS NULL
                ORDER BY p.id ASC
                """
            ).fetchall()
            for row in orphan_products:
                issues.append(
                    ConsistencyIssue(
                        severity="error",
                        code="MISSING_INVENTORY_RECORD",
                        entity_id=int(row["id"]),
                        sku=str(row["sku"]),
                        message=(
                            f"Product `{row['name']}` ({row['sku']}) is missing "
                            "its inventory record."
                        ),
                    )
                )

            # 2. Stock ledger invariant: current_stock == SUM(inventory_adjustments.quantity_delta)
            ledger_rows = conn.execute(
                """
                SELECT
                    p.id,
                    p.sku,
                    p.name,
                    i.current_stock,
                    COALESCE(SUM(a.quantity_delta), 0) AS ledger_sum
                FROM products p
                JOIN inventory i ON i.product_id = p.id
                LEFT JOIN inventory_adjustments a ON a.product_id = p.id
                GROUP BY p.id, p.sku, p.name, i.current_stock
                HAVING i.current_stock != COALESCE(SUM(a.quantity_delta), 0)
                ORDER BY p.id ASC
                """
            ).fetchall()
            for row in ledger_rows:
                issues.append(
                    ConsistencyIssue(
                        severity="error",
                        code="STOCK_LEDGER_MISMATCH",
                        entity_id=int(row["id"]),
                        sku=str(row["sku"]),
                        message=(
                            f"Stock ledger mismatch for `{row['name']}` ({row['sku']}): "
                            f"current_stock={row['current_stock']} vs "
                            f"adjustment_sum={row['ledger_sum']}."
                        ),
                    )
                )

            # 3. Sales arithmetic invariant: gross_revenue_centavos == unit_price * quantity_sold
            sales_rows = conn.execute(
                """
                SELECT
                    s.id,
                    p.sku,
                    s.quantity_sold,
                    s.unit_price_centavos,
                    s.gross_revenue_centavos
                FROM sales_transactions s
                JOIN products p ON p.id = s.product_id
                ORDER BY s.id ASC
                """
            ).fetchall()
            for row in sales_rows:
                unit_price = centavos_to_money(int(row["unit_price_centavos"]))
                qty = int(row["quantity_sold"])
                expected_centavos = money_to_centavos(
                    (unit_price * qty).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
                )
                actual_centavos = int(row["gross_revenue_centavos"])
                if actual_centavos != expected_centavos:
                    issues.append(
                        ConsistencyIssue(
                            severity="error",
                            code="SALE_REVENUE_MISMATCH",
                            entity_id=int(row["id"]),
                            sku=str(row["sku"]),
                            message=(
                                f"Sale #{row['id']} ({row['sku']}) stored gross_revenue "
                                f"₱{centavos_to_money(actual_centavos):.2f} does not match "
                                f"expected ₱{centavos_to_money(expected_centavos):.2f}."
                            ),
                        )
                    )

            # 4. Non-blocking warning: active products priced below supplier unit cost
            below_cost_rows = conn.execute(
                """
                SELECT id, sku, name, unit_cost_centavos, selling_price_centavos
                FROM products
                WHERE is_active = 1 AND selling_price_centavos < unit_cost_centavos
                ORDER BY id ASC
                """
            ).fetchall()
            for row in below_cost_rows:
                cost = centavos_to_money(int(row["unit_cost_centavos"]))
                price = centavos_to_money(int(row["selling_price_centavos"]))
                issues.append(
                    ConsistencyIssue(
                        severity="warning",
                        code="NEGATIVE_UNIT_MARGIN",
                        entity_id=int(row["id"]),
                        sku=str(row["sku"]),
                        message=(
                            f"Active product `{row['name']}` ({row['sku']}) has selling price "
                            f"₱{price:.2f} below unit cost ₱{cost:.2f}."
                        ),
                    )
                )

        has_errors = any(issue.severity == "error" for issue in issues)
        return DataConsistencyReport(
            is_consistent=not has_errors,
            products_checked=total_products,
            sales_checked=total_sales,
            issues=tuple(issues),
        )
