"""Profitability Analyzer service computing product, category, and store margins."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal

from tindahaniq.db.connection import DatabaseManager
from tindahaniq.db.repositories import ProductRepository, SalesRepository
from tindahaniq.exceptions import ValidationError
from tindahaniq.models.analytics import (
    CategoryProfitability,
    ProductProfitability,
    ProfitSortBy,
    StoreProfitabilityReport,
)
from tindahaniq.services.bi.formulas import (
    ZERO,
    calculate_cogs,
    calculate_gross_margin_pct,
    calculate_gross_profit,
    calculate_markup_pct,
    quantize_money,
)


def _normalize_window(
    start_at: datetime | None,
    end_at: datetime | None,
) -> tuple[datetime | None, datetime | None]:
    s_utc = (
        (start_at.replace(tzinfo=UTC) if start_at.tzinfo is None else start_at.astimezone(UTC))
        if start_at is not None
        else None
    )
    e_utc = (
        (end_at.replace(tzinfo=UTC) if end_at.tzinfo is None else end_at.astimezone(UTC))
        if end_at is not None
        else None
    )
    if s_utc is not None and e_utc is not None and s_utc > e_utc:
        raise ValidationError(
            f"Invalid profitability date window: {s_utc} > {e_utc}",
            user_message="Start date must be earlier than or equal to the end date.",
            details={"field": "date_range"},
        )
    return s_utc, e_utc


class ProfitabilityAnalyzer:
    """Calculate deterministic gross revenue, COGS, gross profit, margins, and markups."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db
        self._products = ProductRepository(db)
        self._sales = SalesRepository(db)

    def analyze_store_profitability(
        self,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        active_only: bool = False,
        sort_by: ProfitSortBy = "gross_profit",
        descending: bool = True,
    ) -> StoreProfitabilityReport:
        """Compute store-wide, per-product, and per-category profitability."""
        s_utc, e_utc = _normalize_window(start_at, end_at)

        with self._db.read_connection() as conn:
            catalog = self._products.list_all(active_only=active_only, conn=conn)
            sales = self._sales.list_sales(start_at=s_utc, end_at=e_utc, conn=conn)

        units_by_prod: dict[int, int] = defaultdict(int)
        rev_by_prod: dict[int, Decimal] = defaultdict(lambda: ZERO)
        cogs_by_prod: dict[int, Decimal] = defaultdict(lambda: ZERO)

        for sale in sales:
            units_by_prod[sale.product_id] += sale.quantity_sold
            rev_by_prod[sale.product_id] = quantize_money(
                rev_by_prod[sale.product_id] + sale.gross_revenue
            )
            line_cogs = calculate_cogs(sale.quantity_sold, sale.unit_cost_at_sale)
            cogs_by_prod[sale.product_id] = quantize_money(
                cogs_by_prod[sale.product_id] + line_cogs
            )

        product_rows: list[ProductProfitability] = []
        cat_prod_count: dict[str, int] = defaultdict(int)
        cat_units: dict[str, int] = defaultdict(int)
        cat_rev: dict[str, Decimal] = defaultdict(lambda: ZERO)
        cat_cogs: dict[str, Decimal] = defaultdict(lambda: ZERO)

        for entry in catalog:
            prod = entry.product
            units = units_by_prod[prod.id]
            rev = rev_by_prod[prod.id]
            cogs = cogs_by_prod[prod.id]
            profit = calculate_gross_profit(rev, cogs)

            unit_profit = prod.unit_profit
            cat_margin = calculate_gross_margin_pct(unit_profit, prod.selling_price)
            cat_markup = calculate_markup_pct(prod.selling_price, prod.unit_cost)
            realized_margin = calculate_gross_margin_pct(profit, rev)
            realized_markup = calculate_markup_pct(rev, cogs)

            product_rows.append(
                ProductProfitability(
                    product_id=prod.id,
                    sku=prod.sku,
                    product_name=prod.name,
                    category=prod.category,
                    unit=prod.unit,
                    is_active=prod.is_active,
                    current_unit_cost=prod.unit_cost,
                    current_selling_price=prod.selling_price,
                    current_unit_profit=unit_profit,
                    catalog_margin_pct=cat_margin,
                    catalog_markup_pct=cat_markup,
                    units_sold=units,
                    gross_revenue=rev,
                    cogs=cogs,
                    gross_profit=profit,
                    realized_margin_pct=realized_margin,
                    realized_markup_pct=realized_markup,
                )
            )

            cat_prod_count[prod.category] += 1
            cat_units[prod.category] += units
            cat_rev[prod.category] = quantize_money(cat_rev[prod.category] + rev)
            cat_cogs[prod.category] = quantize_money(cat_cogs[prod.category] + cogs)

        product_rows.sort(
            key=lambda item: _profit_sort_key(item, sort_by=sort_by),
            reverse=descending,
        )

        category_rows: list[CategoryProfitability] = []
        for cat_name in sorted(cat_prod_count):
            c_rev = cat_rev[cat_name]
            c_cogs = cat_cogs[cat_name]
            c_profit = calculate_gross_profit(c_rev, c_cogs)
            category_rows.append(
                CategoryProfitability(
                    category=cat_name,
                    product_count=cat_prod_count[cat_name],
                    units_sold=cat_units[cat_name],
                    gross_revenue=c_rev,
                    cogs=c_cogs,
                    gross_profit=c_profit,
                    gross_margin_pct=calculate_gross_margin_pct(c_profit, c_rev),
                )
            )
        category_rows.sort(key=lambda c: (c.gross_profit, c.gross_revenue), reverse=True)

        total_units = sum(item.units_sold for item in product_rows)
        total_rev = quantize_money(sum((item.gross_revenue for item in product_rows), ZERO))
        total_cogs = quantize_money(sum((item.cogs for item in product_rows), ZERO))
        total_profit = calculate_gross_profit(total_rev, total_cogs)

        return StoreProfitabilityReport(
            start_at=s_utc,
            end_at=e_utc,
            total_units_sold=total_units,
            gross_revenue=total_rev,
            cogs=total_cogs,
            gross_profit=total_profit,
            gross_margin_pct=calculate_gross_margin_pct(total_profit, total_rev),
            markup_pct=calculate_markup_pct(total_rev, total_cogs),
            products=tuple(product_rows),
            categories=tuple(category_rows),
        )

    def get_product_profitability(
        self,
        product_id: int,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> ProductProfitability:
        """Return profitability metrics for a single product ID."""
        report = self.analyze_store_profitability(start_at=start_at, end_at=end_at)
        for prod in report.products:
            if prod.product_id == product_id:
                return prod
        raise ValidationError(
            f"Product id={product_id} not found for profitability analysis",
            user_message=f"Product #{product_id} could not be found.",
            details={"product_id": product_id},
        )


def _profit_sort_key(
    item: ProductProfitability,
    *,
    sort_by: ProfitSortBy,
) -> tuple[Decimal, Decimal, str]:
    if sort_by == "gross_margin_pct":
        margin = (
            item.realized_margin_pct if item.realized_margin_pct is not None else Decimal("-999999")
        )
        return (margin, item.gross_profit, item.product_name)
    if sort_by == "gross_revenue":
        return (item.gross_revenue, item.gross_profit, item.product_name)
    if sort_by == "unit_profit":
        return (item.current_unit_profit, item.gross_profit, item.product_name)
    return (item.gross_profit, item.gross_revenue, item.product_name)
