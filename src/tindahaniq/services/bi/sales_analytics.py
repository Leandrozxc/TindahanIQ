"""Sales Analytics service for top/slow movers, period summaries, and trend comparisons."""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from tindahaniq.db.connection import DatabaseManager
from tindahaniq.db.repositories import ProductRepository, SalesRepository
from tindahaniq.exceptions import ValidationError
from tindahaniq.models.analytics import (
    HourlySalesBucket,
    PeriodComparison,
    PeriodGranularity,
    ProductSalesPerformance,
    SalesAnalyticsReport,
    SalesPeriodBucket,
    SalesSortBy,
)
from tindahaniq.models.sales import SalesTransaction
from tindahaniq.services.bi.formulas import (
    ZERO,
    calculate_cogs,
    calculate_daily_velocity,
    calculate_gross_profit,
    calculate_pct_change,
    quantize_money,
)


def _to_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def _format_hour_label(hour: int) -> str:
    start_dt = datetime(2026, 1, 1, hour, 0, tzinfo=UTC)
    end_dt = start_dt + timedelta(hours=1)
    return f"{start_dt:%I:%M %p} - {end_dt:%I:%M %p}"


class SalesAnalyticsService:
    """Analyze product velocity, slow movers, daily/weekly/monthly buckets, and comparisons."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db
        self._products = ProductRepository(db)
        self._sales = SalesRepository(db)

    def analyze_sales(
        self,
        *,
        granularity: PeriodGranularity = "daily",
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        top_n: int = 5,
        sort_by: SalesSortBy = "units_sold",
        reference_time: datetime | None = None,
    ) -> SalesAnalyticsReport:
        """Generate a complete sales analytics report over an optional time window."""
        if top_n < 1:
            raise ValidationError(
                f"Invalid top_n={top_n}",
                user_message="`top_n` must be at least 1.",
                details={"field": "top_n"},
            )

        s_utc = _to_utc(start_at) if start_at is not None else None
        e_utc = _to_utc(end_at) if end_at is not None else None
        if s_utc is not None and e_utc is not None and s_utc > e_utc:
            raise ValidationError(
                f"Invalid sales analytics window: {s_utc} > {e_utc}",
                user_message="Start date must be earlier than or equal to the end date.",
                details={"field": "date_range"},
            )

        with self._db.read_connection() as conn:
            active_catalog = self._products.list_all(active_only=True, conn=conn)
            all_catalog = self._products.list_all(active_only=False, conn=conn)
            window_sales = self._sales.list_sales(start_at=s_utc, end_at=e_utc, conn=conn)
            all_sales = (
                window_sales
                if (s_utc is None and e_utc is None)
                else self._sales.list_sales(conn=conn)
            )

        effective_days = _compute_effective_days(window_sales, s_utc, e_utc)
        anchor_time = _resolve_anchor_time(reference_time, e_utc, all_sales)

        last_sale_overall: dict[int, datetime] = {}
        for tx in all_sales:
            prev = last_sale_overall.get(tx.product_id)
            if prev is None or tx.sold_at > prev:
                last_sale_overall[tx.product_id] = tx.sold_at

        tx_count_by_prod: dict[int, int] = defaultdict(int)
        units_by_prod: dict[int, int] = defaultdict(int)
        rev_by_prod: dict[int, Decimal] = defaultdict(lambda: ZERO)
        cogs_by_prod: dict[int, Decimal] = defaultdict(lambda: ZERO)

        for tx in window_sales:
            tx_count_by_prod[tx.product_id] += 1
            units_by_prod[tx.product_id] += tx.quantity_sold
            rev_by_prod[tx.product_id] = quantize_money(
                rev_by_prod[tx.product_id] + tx.gross_revenue
            )
            cogs_by_prod[tx.product_id] = quantize_money(
                cogs_by_prod[tx.product_id] + calculate_cogs(tx.quantity_sold, tx.unit_cost_at_sale)
            )

        all_by_id = {entry.product.id: entry for entry in all_catalog}
        perf_by_id: dict[int, ProductSalesPerformance] = {}
        for prod_id, entry in all_by_id.items():
            prod = entry.product
            units = units_by_prod[prod_id]
            rev = rev_by_prod[prod_id]
            profit = calculate_gross_profit(rev, cogs_by_prod[prod_id])
            last_sold = last_sale_overall.get(prod_id)
            days_since = (
                max(0, (anchor_time.date() - last_sold.astimezone(UTC).date()).days)
                if last_sold is not None
                else None
            )
            perf_by_id[prod_id] = ProductSalesPerformance(
                product_id=prod_id,
                sku=prod.sku,
                product_name=prod.name,
                category=prod.category,
                unit=prod.unit,
                current_stock=entry.inventory.current_stock,
                transaction_count=tx_count_by_prod[prod_id],
                units_sold=units,
                gross_revenue=rev,
                gross_profit=profit,
                daily_velocity=calculate_daily_velocity(units, effective_days),
                last_sold_at=last_sold,
                days_since_last_sale=days_since,
            )

        sold_candidates = [item for item in perf_by_id.values() if item.units_sold > 0]
        sold_candidates.sort(
            key=lambda p: (
                (p.gross_revenue, p.units_sold)
                if sort_by == "gross_revenue"
                else (Decimal(p.units_sold), p.gross_revenue)
            ),
            reverse=True,
        )
        top_selling = tuple(sold_candidates[:top_n])

        active_ids = {entry.product.id for entry in active_catalog}
        slow_candidates = [perf_by_id[pid] for pid in active_ids if pid in perf_by_id]
        slow_candidates.sort(
            key=lambda p: (
                p.units_sold,
                p.gross_revenue,
                -(p.days_since_last_sale if p.days_since_last_sale is not None else 999999),
                p.product_name,
            )
        )
        slow_moving = tuple(slow_candidates[:top_n])

        buckets = _build_period_buckets(window_sales, granularity, s_utc, e_utc)
        peak_hour = _detect_peak_hour(window_sales)

        total_tx = len(window_sales)
        total_units = sum(tx.quantity_sold for tx in window_sales)
        total_rev = quantize_money(sum((tx.gross_revenue for tx in window_sales), ZERO))
        total_cogs = quantize_money(
            sum(
                (calculate_cogs(tx.quantity_sold, tx.unit_cost_at_sale) for tx in window_sales),
                ZERO,
            )
        )
        total_profit = calculate_gross_profit(total_rev, total_cogs)
        avg_daily_rev = quantize_money(total_rev / Decimal(effective_days))

        return SalesAnalyticsReport(
            granularity=granularity,
            start_at=s_utc,
            end_at=e_utc,
            effective_days=effective_days,
            total_transactions=total_tx,
            total_units_sold=total_units,
            total_gross_revenue=total_rev,
            total_gross_profit=total_profit,
            average_daily_revenue=avg_daily_rev,
            peak_hour=peak_hour,
            buckets=buckets,
            top_selling=top_selling,
            slow_moving=slow_moving,
        )

    def compare_periods(
        self,
        *,
        window_days: int = 7,
        current_end: datetime | None = None,
    ) -> PeriodComparison:
        """Compare the trailing `window_days` period against the immediately preceding window."""
        if window_days < 1:
            raise ValidationError(
                f"Invalid window_days={window_days}",
                user_message="`window_days` must be at least 1.",
                details={"field": "window_days"},
            )

        with self._db.read_connection() as conn:
            all_sales = self._sales.list_sales(conn=conn)

        end_anchor = _resolve_anchor_time(current_end, None, all_sales)
        end_day = end_anchor.date()
        curr_start_day = end_day - timedelta(days=window_days - 1)
        prev_end_day = curr_start_day - timedelta(days=1)
        prev_start_day = prev_end_day - timedelta(days=window_days - 1)

        curr_start = datetime(
            curr_start_day.year, curr_start_day.month, curr_start_day.day, 0, 0, 0, tzinfo=UTC
        )
        curr_end = datetime(end_day.year, end_day.month, end_day.day, 23, 59, 59, tzinfo=UTC)
        prev_start = datetime(
            prev_start_day.year, prev_start_day.month, prev_start_day.day, 0, 0, 0, tzinfo=UTC
        )
        prev_end = datetime(
            prev_end_day.year, prev_end_day.month, prev_end_day.day, 23, 59, 59, tzinfo=UTC
        )

        curr_tx = [tx for tx in all_sales if curr_start <= tx.sold_at <= curr_end]
        prev_tx = [tx for tx in all_sales if prev_start <= tx.sold_at <= prev_end]

        curr_rev, curr_profit, curr_units = _summarize_transactions(curr_tx)
        prev_rev, prev_profit, prev_units = _summarize_transactions(prev_tx)

        rev_delta = quantize_money(curr_rev - prev_rev)
        profit_delta = quantize_money(curr_profit - prev_profit)

        return PeriodComparison(
            window_days=window_days,
            current_start=curr_start,
            current_end=curr_end,
            previous_start=prev_start,
            previous_end=prev_end,
            current_revenue=curr_rev,
            previous_revenue=prev_rev,
            revenue_delta=rev_delta,
            revenue_change_pct=calculate_pct_change(curr_rev, prev_rev),
            current_gross_profit=curr_profit,
            previous_gross_profit=prev_profit,
            gross_profit_delta=profit_delta,
            gross_profit_change_pct=calculate_pct_change(curr_profit, prev_profit),
            current_units_sold=curr_units,
            previous_units_sold=prev_units,
            units_delta=curr_units - prev_units,
            current_transactions=len(curr_tx),
            previous_transactions=len(prev_tx),
        )


def _summarize_transactions(
    transactions: list[SalesTransaction],
) -> tuple[Decimal, Decimal, int]:
    rev = quantize_money(sum((tx.gross_revenue for tx in transactions), ZERO))
    cogs = quantize_money(
        sum(
            (calculate_cogs(tx.quantity_sold, tx.unit_cost_at_sale) for tx in transactions),
            ZERO,
        )
    )
    profit = calculate_gross_profit(rev, cogs)
    units = sum(tx.quantity_sold for tx in transactions)
    return rev, profit, units


def _resolve_anchor_time(
    explicit_ref: datetime | None,
    end_at: datetime | None,
    sales: list[SalesTransaction],
) -> datetime:
    if explicit_ref is not None:
        return _to_utc(explicit_ref)
    if end_at is not None:
        return end_at
    if sales:
        return max(tx.sold_at for tx in sales)
    return datetime.now(UTC)


def _compute_effective_days(
    sales: list[SalesTransaction],
    start_at: datetime | None,
    end_at: datetime | None,
) -> int:
    if start_at is not None and end_at is not None:
        return max(1, (end_at.date() - start_at.date()).days + 1)
    if not sales:
        return 1
    first_day = min(tx.sold_at.astimezone(UTC).date() for tx in sales)
    last_day = max(tx.sold_at.astimezone(UTC).date() for tx in sales)
    if start_at is not None:
        first_day = start_at.date()
    if end_at is not None:
        last_day = end_at.date()
    return max(1, (last_day - first_day).days + 1)


def _build_period_buckets(
    sales: list[SalesTransaction],
    granularity: PeriodGranularity,
    start_at: datetime | None,
    end_at: datetime | None,
) -> tuple[SalesPeriodBucket, ...]:
    if not sales and (start_at is None or end_at is None):
        return ()

    grouped: dict[date, list[SalesTransaction]] = defaultdict(list)
    for tx in sales:
        d = tx.sold_at.astimezone(UTC).date()
        key = _bucket_start_date(d, granularity)
        grouped[key].append(tx)

    if granularity == "daily":
        first_d = start_at.date() if start_at is not None else min(grouped.keys())
        last_d = end_at.date() if end_at is not None else max(grouped.keys())
        cursor = first_d
        while cursor <= last_d:
            grouped.setdefault(cursor, [])
            cursor += timedelta(days=1)

    buckets: list[SalesPeriodBucket] = []
    for b_start in sorted(grouped):
        tx_list = grouped[b_start]
        b_end, label = _bucket_end_and_label(b_start, granularity)
        rev = quantize_money(sum((tx.gross_revenue for tx in tx_list), ZERO))
        cogs = quantize_money(
            sum(
                (calculate_cogs(tx.quantity_sold, tx.unit_cost_at_sale) for tx in tx_list),
                ZERO,
            )
        )
        buckets.append(
            SalesPeriodBucket(
                period_label=label,
                period_start=b_start,
                period_end=b_end,
                transaction_count=len(tx_list),
                units_sold=sum(tx.quantity_sold for tx in tx_list),
                gross_revenue=rev,
                cogs=cogs,
                gross_profit=calculate_gross_profit(rev, cogs),
            )
        )
    return tuple(buckets)


def _bucket_start_date(day: date, granularity: PeriodGranularity) -> date:
    if granularity == "weekly":
        return day - timedelta(days=day.weekday())
    if granularity == "monthly":
        return date(day.year, day.month, 1)
    return day


def _bucket_end_and_label(b_start: date, granularity: PeriodGranularity) -> tuple[date, str]:
    if granularity == "weekly":
        b_end = b_start + timedelta(days=6)
        iso_year, iso_week, _ = b_start.isocalendar()
        return b_end, f"{iso_year}-W{iso_week:02d}"
    if granularity == "monthly":
        last_dom = calendar.monthrange(b_start.year, b_start.month)[1]
        b_end = date(b_start.year, b_start.month, last_dom)
        return b_end, f"{b_start.year}-{b_start.month:02d}"
    return b_start, b_start.isoformat()


def _detect_peak_hour(sales: list[SalesTransaction]) -> HourlySalesBucket | None:
    timed_sales = [
        tx
        for tx in sales
        if (
            tx.sold_at.astimezone(UTC).hour != 0
            or tx.sold_at.astimezone(UTC).minute != 0
            or tx.sold_at.astimezone(UTC).second != 0
        )
    ]
    if not timed_sales:
        return None

    tx_by_hour: dict[int, list[SalesTransaction]] = defaultdict(list)
    for tx in timed_sales:
        tx_by_hour[tx.sold_at.astimezone(UTC).hour].append(tx)

    hourly_buckets = [
        HourlySalesBucket(
            hour=hour,
            label=_format_hour_label(hour),
            transaction_count=len(items),
            units_sold=sum(t.quantity_sold for t in items),
            gross_revenue=quantize_money(sum((t.gross_revenue for t in items), ZERO)),
        )
        for hour, items in tx_by_hour.items()
    ]
    hourly_buckets.sort(
        key=lambda h: (h.gross_revenue, h.transaction_count, h.units_sold, -h.hour),
        reverse=True,
    )
    return hourly_buckets[0]
