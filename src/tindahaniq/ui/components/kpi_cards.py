"""Top 4 KPI summary cards modeled on Proposal Page 7."""

from __future__ import annotations

import streamlit as st

from tindahaniq.models.analytics import StockUrgency
from tindahaniq.ui.context import AppContext
from tindahaniq.ui.theme import format_pct, format_php


def render_top_kpi_strip(ctx: AppContext) -> None:
    """Render the 4 executive store metrics across the top of Dashboard and AI Assistant."""
    active_products = ctx.inventory_service.list_inventory(active_only=True)
    categories = ctx.inventory_service.list_categories(active_only=True)
    prof = ctx.profitability.analyze_store_profitability()
    intel = ctx.inventory_intel.analyze_inventory(
        lookback_days=int(st.session_state.get("lookback_days", 14)),
        target_coverage_days=int(st.session_state.get("coverage_days", 7)),
    )
    weekly_comp = ctx.sales_analytics.compare_periods(window_days=7)
    daily_comp = ctx.sales_analytics.compare_periods(window_days=1)

    low_items = [r for r in intel.recommendations if r.urgency != StockUrgency.HEALTHY]

    col_prod, col_prof, col_stock, col_sales = st.columns(4)

    with col_prod, st.container(border=True):
        st.metric(
            label="TOTAL PRODUCTS",
            value=f"{len(active_products)}",
            delta=f"Across {len(categories)} categories" if categories else "No categories yet",
            delta_color="off",
        )

    with col_prof, st.container(border=True):
        margin_text = (
            f"Margin {format_pct(prof.gross_margin_pct)}"
            if prof.gross_margin_pct is not None
            else "No sales yet"
        )
        profit_delta = (
            f"{format_pct(weekly_comp.gross_profit_change_pct, signed=True)} vs prior 7d"
            if weekly_comp.gross_profit_change_pct is not None
            else margin_text
        )
        st.metric(
            label="GROSS PROFIT",
            value=format_php(prof.gross_profit),
            delta=profit_delta,
            delta_color="normal" if weekly_comp.gross_profit_change_pct is not None else "off",
        )
        if weekly_comp.gross_profit_change_pct is not None:
            st.caption(margin_text)

    with col_stock, st.container(border=True):
        crit_label = (
            f"{intel.critical_count} Critical — Needs restocking"
            if intel.critical_count > 0
            else ("Needs attention" if low_items else "All stock healthy")
        )
        st.metric(
            label="LOW STOCK ITEMS",
            value=f"{len(low_items)}",
            delta=crit_label,
            delta_color="inverse" if intel.critical_count > 0 else "off",
        )

    with col_sales, st.container(border=True):
        day_delta = (
            f"{format_pct(daily_comp.revenue_change_pct, signed=True)} vs prior day"
            if daily_comp.revenue_change_pct is not None
            else f"{daily_comp.current_transactions} transaction(s) logged"
        )
        st.metric(
            label="LATEST DAY SALES",
            value=format_php(daily_comp.current_revenue),
            delta=day_delta,
            delta_color="normal" if daily_comp.revenue_change_pct is not None else "off",
        )
        if daily_comp.revenue_change_pct is not None:
            st.caption(f"{daily_comp.current_transactions} transaction(s) logged")
