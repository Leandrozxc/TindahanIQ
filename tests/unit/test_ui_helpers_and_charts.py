"""Unit tests for UI currency/percentage formatters, badges, and Plotly chart builders."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from tindahaniq.models.analytics import (
    CategoryProfitability,
    PriceSimulationResult,
    ProductSalesPerformance,
    SalesPeriodBucket,
    StockUrgency,
)
from tindahaniq.ui.components.charts import (
    build_category_profit_chart,
    build_price_simulation_chart,
    build_product_ranking_chart,
    build_revenue_profit_trend_chart,
    build_weekly_sales_bar_chart,
)
from tindahaniq.ui.theme import EMERALD_DARK, format_pct, format_php, urgency_badge_html


def test_format_php_and_format_pct_conventions() -> None:
    assert format_php(None) == "—"
    assert format_php(Decimal("1850.5")) == "₱1,850.50"
    assert format_php(Decimal("-40.50")) == "-₱40.50"

    assert format_pct(None) == "—"
    assert format_pct(Decimal("24.84")) == "24.8%"
    assert format_pct(Decimal("12.4"), signed=True) == "+12.4%"


def test_urgency_badge_renders_styled_pill() -> None:
    badge = urgency_badge_html(StockUrgency.CRITICAL)
    assert "Critical" in badge
    assert "<span" in badge


def test_all_plotly_chart_builders_return_valid_figures() -> None:
    buckets = [
        SalesPeriodBucket(
            period_label="2026-11-22",
            period_start=date(2026, 11, 22),
            period_end=date(2026, 11, 22),
            transaction_count=3,
            units_sold=20,
            gross_revenue=Decimal("332.00"),
            cogs=Decimal("240.00"),
            gross_profit=Decimal("92.00"),
        ),
        SalesPeriodBucket(
            period_label="2026-11-23",
            period_start=date(2026, 11, 23),
            period_end=date(2026, 11, 23),
            transaction_count=4,
            units_sold=30,
            gross_revenue=Decimal("520.00"),
            cogs=Decimal("370.00"),
            gross_profit=Decimal("150.00"),
        ),
    ]

    weekly_fig = build_weekly_sales_bar_chart(buckets)
    assert len(weekly_fig.data) == 1
    assert EMERALD_DARK in weekly_fig.data[0].marker.color

    trend_fig = build_revenue_profit_trend_chart(buckets)
    assert len(trend_fig.data) == 2

    cat_fig = build_category_profit_chart(
        [
            CategoryProfitability(
                category="Beverages",
                product_count=3,
                units_sold=52,
                gross_revenue=Decimal("985.00"),
                cogs=Decimal("700.50"),
                gross_profit=Decimal("284.50"),
                gross_margin_pct=Decimal("28.88"),
            )
        ]
    )
    assert len(cat_fig.data) == 1

    prod_fig = build_product_ranking_chart(
        [
            ProductSalesPerformance(
                product_id=1,
                sku="BEV-001",
                product_name="Coca-Cola Mismo",
                category="Beverages",
                unit="bottle",
                current_stock=36,
                transaction_count=3,
                units_sold=41,
                gross_revenue=Decimal("820.00"),
                gross_profit=Decimal("246.00"),
                daily_velocity=Decimal("10.25"),
                last_sold_at=None,
                days_since_last_sale=0,
            )
        ]
    )
    assert len(prod_fig.data) == 1

    sim_fig = build_price_simulation_chart(
        PriceSimulationResult(
            product_id=1,
            sku="NOOD-001",
            product_name="Pancit Canton",
            unit="pack",
            unit_cost=Decimal("12.25"),
            current_price=Decimal("16.00"),
            proposed_price=Decimal("18.00"),
            price_delta_php=Decimal("2.00"),
            price_change_pct=Decimal("12.50"),
            current_unit_profit=Decimal("3.75"),
            proposed_unit_profit=Decimal("5.75"),
            unit_profit_delta=Decimal("2.00"),
            current_margin_pct=Decimal("23.44"),
            proposed_margin_pct=Decimal("31.94"),
            margin_pct_point_delta=Decimal("8.50"),
            current_markup_pct=Decimal("30.61"),
            proposed_markup_pct=Decimal("46.94"),
            baseline_units=18,
            simulated_units=18,
            expected_volume_change_pct=Decimal("0.00"),
            baseline_gross_revenue=Decimal("288.00"),
            simulated_gross_revenue=Decimal("324.00"),
            revenue_delta=Decimal("36.00"),
            baseline_gross_profit=Decimal("67.50"),
            simulated_gross_profit=Decimal("103.50"),
            gross_profit_delta=Decimal("36.00"),
            breakeven_volume_change_pct=Decimal("-34.78"),
            warnings=(),
            assumptions=(),
        )
    )
    assert len(sim_fig.data) == 2
