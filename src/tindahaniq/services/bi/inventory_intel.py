"""Inventory Intelligence service for low-stock detection, velocity, and restock planning."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from tindahaniq.db.connection import DatabaseManager
from tindahaniq.db.repositories import ProductRepository, SalesRepository
from tindahaniq.exceptions import ValidationError
from tindahaniq.models.analytics import (
    BudgetAllocationItem,
    BudgetRestockPlan,
    InventoryIntelligenceReport,
    RestockRecommendation,
    StockUrgency,
)
from tindahaniq.models.sales import SalesTransaction
from tindahaniq.services.bi.formulas import (
    ZERO,
    calculate_daily_velocity,
    calculate_days_to_depletion,
    calculate_suggested_restock_qty,
    classify_stock_urgency,
    quantize_money,
)
from tindahaniq.utils.validation import parse_money_decimal, parse_non_negative_int

URGENCY_RANK: dict[StockUrgency, int] = {
    StockUrgency.CRITICAL: 0,
    StockUrgency.HIGH: 1,
    StockUrgency.LOW: 2,
    StockUrgency.HEALTHY: 3,
}


def _to_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


class InventoryIntelligenceService:
    """Compute stockout risks, restock quantities, and budget-constrained allocations."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db
        self._products = ProductRepository(db)
        self._sales = SalesRepository(db)

    def analyze_inventory(
        self,
        *,
        lookback_days: int = 14,
        target_coverage_days: int = 7,
        as_of: datetime | None = None,
        needs_restock_only: bool = False,
    ) -> InventoryIntelligenceReport:
        """Analyze active inventory health, velocity, depletion, and restock quantities."""
        checked_lookback = parse_non_negative_int(
            lookback_days, field_name="lookback_days", min_value=1
        )
        checked_coverage = parse_non_negative_int(
            target_coverage_days, field_name="target_coverage_days", min_value=1
        )

        with self._db.read_connection() as conn:
            active_items = self._products.list_all(active_only=True, conn=conn)
            all_sales = self._sales.list_sales(conn=conn)

        anchor = _resolve_as_of(as_of, all_sales)
        window_sales, effective_days, assumptions = _slice_lookback_sales(
            all_sales, anchor, checked_lookback
        )

        units_by_prod: dict[int, int] = defaultdict(int)
        for tx in window_sales:
            units_by_prod[tx.product_id] += tx.quantity_sold

        recommendations: list[RestockRecommendation] = []
        used_any_fallback = False

        for entry in active_items:
            prod = entry.product
            inv = entry.inventory
            units_sold = units_by_prod[prod.id]
            velocity = calculate_daily_velocity(units_sold, effective_days)
            depletion = calculate_days_to_depletion(inv.current_stock, units_sold, effective_days)
            suggested_qty, used_fallback = calculate_suggested_restock_qty(
                current_stock=inv.current_stock,
                reorder_point=inv.reorder_point,
                lead_time_days=inv.lead_time_days,
                target_coverage_days=checked_coverage,
                units_sold_in_window=units_sold,
                effective_window_days=effective_days,
            )
            if used_fallback:
                used_any_fallback = True

            urgency = classify_stock_urgency(
                current_stock=inv.current_stock,
                reorder_point=inv.reorder_point,
                lead_time_days=inv.lead_time_days,
                days_to_depletion=depletion,
            )
            est_cost = quantize_money(Decimal(suggested_qty) * prod.unit_cost)

            recommendations.append(
                RestockRecommendation(
                    product_id=prod.id,
                    sku=prod.sku,
                    product_name=prod.name,
                    category=prod.category,
                    unit=prod.unit,
                    urgency=urgency,
                    current_stock=inv.current_stock,
                    reorder_point=inv.reorder_point,
                    lead_time_days=inv.lead_time_days,
                    unit_cost=prod.unit_cost,
                    selling_price=prod.selling_price,
                    unit_profit=prod.unit_profit,
                    units_sold_in_window=units_sold,
                    daily_velocity=velocity,
                    estimated_days_to_depletion=depletion,
                    suggested_restock_qty=suggested_qty,
                    estimated_restock_cost=est_cost,
                    used_reorder_point_fallback=used_fallback,
                )
            )

        if used_any_fallback:
            assumptions.append(
                "Items with zero sales in the lookback window used `reorder_point - current_stock` "
                "as a fallback restock estimate."
            )
        assumptions.append(
            f"Suggested restock quantities target {checked_coverage} coverage day(s) "
            "plus each product's supplier lead time, assuming historical daily demand continues."
        )

        recommendations.sort(key=_restock_priority_key)

        critical_cnt = sum(1 for r in recommendations if r.urgency == StockUrgency.CRITICAL)
        high_cnt = sum(1 for r in recommendations if r.urgency == StockUrgency.HIGH)
        low_cnt = sum(1 for r in recommendations if r.urgency == StockUrgency.LOW)
        healthy_cnt = sum(1 for r in recommendations if r.urgency == StockUrgency.HEALTHY)

        filtered = (
            [
                r
                for r in recommendations
                if r.suggested_restock_qty > 0 or r.urgency != StockUrgency.HEALTHY
            ]
            if needs_restock_only
            else recommendations
        )
        total_restock_cost = quantize_money(sum((r.estimated_restock_cost for r in filtered), ZERO))

        return InventoryIntelligenceReport(
            as_of=anchor,
            requested_lookback_days=checked_lookback,
            effective_lookback_days=effective_days,
            target_coverage_days=checked_coverage,
            total_active_products=len(active_items),
            critical_count=critical_cnt,
            high_count=high_cnt,
            low_count=low_cnt,
            healthy_count=healthy_cnt,
            total_suggested_restock_cost=total_restock_cost,
            recommendations=tuple(filtered),
            assumptions=tuple(assumptions),
        )

    def get_product_restock_recommendation(
        self,
        product_id: int,
        *,
        lookback_days: int = 14,
        target_coverage_days: int = 7,
        as_of: datetime | None = None,
    ) -> RestockRecommendation:
        """Return the restock recommendation for a single active product."""
        checked_id = parse_non_negative_int(product_id, field_name="product_id", min_value=1)
        report = self.analyze_inventory(
            lookback_days=lookback_days,
            target_coverage_days=target_coverage_days,
            as_of=as_of,
        )
        for rec in report.recommendations:
            if rec.product_id == checked_id:
                return rec
        raise ValidationError(
            f"Active product id={checked_id} not found for restock analysis",
            user_message=f"Active product #{checked_id} could not be found.",
            details={"product_id": checked_id},
        )

    def plan_restock_within_budget(
        self,
        budget_php: Decimal | str | int | float,
        *,
        lookback_days: int = 14,
        target_coverage_days: int = 7,
        as_of: datetime | None = None,
    ) -> BudgetRestockPlan:
        """Deterministically allocate a fixed PHP working-capital budget across priority items."""
        budget = parse_money_decimal(budget_php, field_name="budget_php", allow_zero=False)
        intel = self.analyze_inventory(
            lookback_days=lookback_days,
            target_coverage_days=target_coverage_days,
            as_of=as_of,
        )

        candidates = [r for r in intel.recommendations if r.suggested_restock_qty > 0]
        candidates.sort(key=_restock_priority_key)

        remaining = budget
        funded: list[BudgetAllocationItem] = []
        deferred: list[BudgetAllocationItem] = []

        for rec in candidates:
            if rec.unit_cost <= ZERO:
                funded_qty = rec.suggested_restock_qty
            else:
                max_affordable = int(remaining // rec.unit_cost)
                funded_qty = min(rec.suggested_restock_qty, max_affordable)

            allocated_cost = quantize_money(Decimal(funded_qty) * rec.unit_cost)
            remaining = quantize_money(remaining - allocated_cost)
            unfunded_qty = rec.suggested_restock_qty - funded_qty
            expected_profit = quantize_money(Decimal(funded_qty) * rec.unit_profit)

            entry = BudgetAllocationItem(
                product_id=rec.product_id,
                sku=rec.sku,
                product_name=rec.product_name,
                unit=rec.unit,
                urgency=rec.urgency,
                current_stock=rec.current_stock,
                full_suggested_qty=rec.suggested_restock_qty,
                funded_qty=funded_qty,
                unfunded_qty=unfunded_qty,
                unit_cost=rec.unit_cost,
                allocated_cost=allocated_cost,
                expected_gross_profit=expected_profit,
            )
            if funded_qty > 0:
                funded.append(entry)
            else:
                deferred.append(entry)

        total_allocated = quantize_money(budget - remaining)
        total_expected_profit = quantize_money(
            sum((item.expected_gross_profit for item in funded), ZERO)
        )
        plan_assumptions = list(intel.assumptions)
        plan_assumptions.append(
            "Budget allocation prioritizes urgency tier first "
            "(CRITICAL -> HIGH -> LOW -> HEALTHY), "
            "then earliest stockout risk and daily profit return per peso of supplier cost."
        )

        return BudgetRestockPlan(
            budget_php=budget,
            total_allocated_cost=total_allocated,
            remaining_budget_php=remaining,
            funded_items=tuple(funded),
            deferred_items=tuple(deferred),
            total_expected_gross_profit=total_expected_profit,
            assumptions=tuple(plan_assumptions),
        )


def _resolve_as_of(
    explicit_as_of: datetime | None,
    all_sales: list[SalesTransaction],
) -> datetime:
    if explicit_as_of is not None:
        return _to_utc(explicit_as_of)
    if all_sales:
        return max(tx.sold_at for tx in all_sales)
    return datetime.now(UTC)


def _slice_lookback_sales(
    all_sales: list[SalesTransaction],
    anchor: datetime,
    lookback_days: int,
) -> tuple[list[SalesTransaction], int, list[str]]:
    assumptions: list[str] = []
    anchor_day = anchor.date()
    requested_start_day = anchor_day - timedelta(days=lookback_days - 1)
    end_bound = datetime(anchor_day.year, anchor_day.month, anchor_day.day, 23, 59, 59, tzinfo=UTC)

    eligible_sales = [tx for tx in all_sales if tx.sold_at <= end_bound]
    if not eligible_sales:
        assumptions.append(
            "No historical sales records found up to the analysis date; "
            "daily sales velocity is 0.00 units/day."
        )
        return [], lookback_days, assumptions

    earliest_day = min(tx.sold_at.astimezone(UTC).date() for tx in eligible_sales)
    effective_start_day = max(requested_start_day, earliest_day)
    effective_days = max(1, (anchor_day - effective_start_day).days + 1)

    if effective_days < lookback_days:
        assumptions.append(
            f"Recorded sales history covers {effective_days} day(s) within the requested "
            f"{lookback_days}-day window; daily velocity is calculated "
            f"over {effective_days} day(s)."
        )

    start_bound = datetime(
        effective_start_day.year,
        effective_start_day.month,
        effective_start_day.day,
        0,
        0,
        0,
        tzinfo=UTC,
    )
    window_sales = [tx for tx in eligible_sales if start_bound <= tx.sold_at <= end_bound]
    return window_sales, effective_days, assumptions


def _restock_priority_key(rec: RestockRecommendation) -> tuple[int, Decimal, Decimal, str]:
    depletion_sort = (
        rec.estimated_days_to_depletion
        if rec.estimated_days_to_depletion is not None
        else Decimal("999999")
    )
    daily_profit = rec.daily_velocity * rec.unit_profit
    roi_per_day = (daily_profit / rec.unit_cost) if rec.unit_cost > ZERO else daily_profit
    return (
        URGENCY_RANK[rec.urgency],
        depletion_sort,
        -roi_per_day,
        rec.product_name,
    )
