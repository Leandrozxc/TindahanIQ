"""Sales Analytics and Profitability Analyzer view."""

from __future__ import annotations

import streamlit as st

from tindahaniq.models.analytics import PeriodGranularity, ProfitSortBy
from tindahaniq.ui.components import (
    build_category_profit_chart,
    build_product_ranking_chart,
    build_revenue_profit_trend_chart,
    render_empty_store_onboarding,
)
from tindahaniq.ui.context import AppContext
from tindahaniq.ui.theme import AMBER_WARN, EMERALD_PRIMARY, format_pct, format_php


def render_sales_profit(ctx: AppContext) -> None:
    """Render Sales Analytics trends, top/slow movers, and Product Profitability Analyzer."""
    st.title("Sales Analytics & Profitability")
    st.caption("Evaluate product margins, markups, best-sellers, slow movers, and revenue trends.")

    if not ctx.has_active_products():
        render_empty_store_onboarding(ctx, key_prefix="sales_prof")
        return

    ctrl_1, ctrl_2, ctrl_3 = st.columns(3)
    granularity_label = ctrl_1.selectbox(
        "Time Grouping",
        ["Daily", "Weekly", "Monthly"],
        key="sp_granularity",
    )
    granularity: PeriodGranularity = granularity_label.lower()  # type: ignore[assignment]
    top_n = int(ctrl_2.slider("Top / Slow Products Count", min_value=3, max_value=10, value=5))
    sort_label = ctrl_3.selectbox(
        "Rank Profitability By",
        [
            ("gross_profit", "Total Gross Profit (₱)"),
            ("gross_margin_pct", "Realized Gross Margin (%)"),
            ("gross_revenue", "Total Gross Revenue (₱)"),
            ("unit_profit", "Catalog Unit Profit (₱)"),
        ],
        format_func=lambda item: item[1],
        key="sp_profit_sort",
    )
    sort_by: ProfitSortBy = sort_label[0]  # type: ignore[assignment]

    prof_report = ctx.profitability.analyze_store_profitability(sort_by=sort_by)
    sales_report = ctx.sales_analytics.analyze_sales(granularity=granularity, top_n=top_n)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Gross Revenue", format_php(prof_report.gross_revenue))
    k2.metric("Cost of Goods Sold", format_php(prof_report.cogs))
    k3.metric("Gross Profit", format_php(prof_report.gross_profit))
    k4.metric(
        "Gross Profit Margin",
        format_pct(prof_report.gross_margin_pct),
        delta=f"Markup {format_pct(prof_report.markup_pct)}"
        if prof_report.markup_pct is not None
        else None,
        delta_color="off",
        help=(
            "Gross Margin = Gross Profit ÷ Selling Revenue. Markup = Gross Profit ÷ Supplier Cost."
        ),
    )

    c_trend, c_cat = st.columns([6, 5], gap="medium")
    with c_trend, st.container(border=True):
        st.markdown(f"#### {granularity_label} Revenue vs. Gross Profit")
        if not sales_report.buckets:
            st.info("No sales recorded yet.")
        else:
            st.plotly_chart(
                build_revenue_profit_trend_chart(sales_report.buckets),
                use_container_width=True,
                config={"displayModeBar": False},
                key="sp_trend_chart",
            )
            peak_str = sales_report.peak_hour.label if sales_report.peak_hour else "N/A"
            st.caption(
                f"Average Daily Revenue: **{format_php(sales_report.average_daily_revenue)}** "
                f"• Peak Sales Window: **{peak_str}**"
            )

    with c_cat, st.container(border=True):
        st.markdown("#### Category Gross Profit")
        if not prof_report.categories or prof_report.total_units_sold == 0:
            st.info("Record sales to compare category profitability.")
        else:
            st.plotly_chart(
                build_category_profit_chart(prof_report.categories),
                use_container_width=True,
                config={"displayModeBar": False},
                key="sp_cat_chart",
            )

    c_top, c_slow = st.columns(2, gap="medium")
    with c_top, st.container(border=True):
        st.markdown(f"#### 🏆 Top {top_n} Best-Selling Products")
        if not sales_report.top_selling:
            st.caption("No unit sales recorded yet.")
        else:
            st.plotly_chart(
                build_product_ranking_chart(sales_report.top_selling, color=EMERALD_PRIMARY),
                use_container_width=True,
                config={"displayModeBar": False},
                key="sp_top_chart",
            )

    with c_slow, st.container(border=True):
        st.markdown(f"#### 🐢 Slow-Moving & Zero-Sale Products (Bottom {top_n})")
        if not sales_report.slow_moving:
            st.caption("No active products found.")
        else:
            slow_rows = [
                {
                    "SKU": p.sku,
                    "Product": p.product_name,
                    "Units Sold": f"{p.units_sold} {p.unit}",
                    "Shelf Stock": f"{p.current_stock} {p.unit}",
                    "Days Unsold": (
                        f"{p.days_since_last_sale}d"
                        if p.days_since_last_sale is not None
                        else "Never sold"
                    ),
                    "Revenue": format_php(p.gross_revenue),
                }
                for p in sales_report.slow_moving
            ]
            st.dataframe(slow_rows, use_container_width=True, hide_index=True)
            if any(p.units_sold == 0 for p in sales_report.slow_moving):
                st.caption(
                    "Tip: Items with 0 sales tie up working capital — consider bundling or "
                    "testing a lower price in the Pricing Simulator."
                )
            else:
                st.plotly_chart(
                    build_product_ranking_chart(sales_report.slow_moving, color=AMBER_WARN),
                    use_container_width=True,
                    config={"displayModeBar": False},
                    key="sp_slow_chart",
                )

    st.markdown("#### Complete Product Profitability Comparison")
    prof_rows = [
        {
            "SKU": p.sku,
            "Product": p.product_name,
            "Category": p.category,
            "Unit Cost": format_php(p.current_unit_cost),
            "Selling Price": format_php(p.current_selling_price),
            "Unit Profit": format_php(p.current_unit_profit),
            "Units Sold": p.units_sold,
            "Gross Revenue": format_php(p.gross_revenue),
            "COGS": format_php(p.cogs),
            "Gross Profit": format_php(p.gross_profit),
            "Realized Margin": format_pct(p.realized_margin_pct),
            "Realized Markup": format_pct(p.realized_markup_pct),
        }
        for p in prof_report.products
    ]
    st.dataframe(prof_rows, use_container_width=True, hide_index=True)

    with st.expander("Recent Sales Transactions Log"):
        recent_tx = ctx.sales_service.get_sales_history(limit=30)
        if not recent_tx:
            st.caption("No sales transactions recorded yet.")
        else:
            tx_rows = [
                {
                    "Sold At (UTC)": f"{r.sale.sold_at:%Y-%m-%d %H:%M}",
                    "Ref": r.sale.external_ref or "—",
                    "SKU": r.sku,
                    "Product": r.product_name,
                    "Qty": f"{r.sale.quantity_sold} {r.unit}",
                    "Unit Price": format_php(r.sale.unit_price_at_sale),
                    "Gross Revenue": format_php(r.sale.gross_revenue),
                    "Gross Profit": format_php(r.sale.gross_profit),
                }
                for r in recent_tx
            ]
            st.dataframe(tx_rows, use_container_width=True, hide_index=True)
