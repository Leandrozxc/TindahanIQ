"""Executive Store Dashboard view."""

from __future__ import annotations

import streamlit as st

from tindahaniq.ui.components import (
    build_category_profit_chart,
    build_revenue_profit_trend_chart,
    render_business_insights_rail,
    render_empty_store_onboarding,
    render_top_kpi_strip,
)
from tindahaniq.ui.context import AppContext
from tindahaniq.ui.state import navigate_to


def render_dashboard(ctx: AppContext) -> None:
    """Render the executive store performance overview."""
    store_title = str(st.session_state.get("store_display_name", ctx.settings.store_name))
    st.title("Store Overview")
    st.caption(f"Live operational & profitability summary for **{store_title}**")

    render_top_kpi_strip(ctx)

    if not ctx.has_active_products():
        render_empty_store_onboarding(ctx, key_prefix="dash")
        return

    col_main, col_rail = st.columns([7, 4], gap="medium")

    with col_main:
        sales_rep = ctx.sales_analytics.analyze_sales(granularity="daily", top_n=5)
        prof_rep = ctx.profitability.analyze_store_profitability()

        with st.container(border=True):
            st.markdown("#### Gross Revenue vs. Gross Profit")
            if not sales_rep.buckets:
                st.info("No sales transactions recorded yet. Upload or record sales to see trends.")
            else:
                st.plotly_chart(
                    build_revenue_profit_trend_chart(sales_rep.buckets),
                    width="stretch",
                    config={"displayModeBar": False},
                    key="dash_rev_profit_chart",
                )

        with st.container(border=True):
            st.markdown("#### Profitability by Product Category")
            if not prof_rep.categories or prof_rep.total_units_sold == 0:
                st.caption("Category profit comparisons will appear once sales are recorded.")
            else:
                st.plotly_chart(
                    build_category_profit_chart(prof_rep.categories),
                    width="stretch",
                    config={"displayModeBar": False},
                    key="dash_cat_profit_chart",
                )

        qa_1, qa_2, qa_3 = st.columns(3)
        if qa_1.button("🤖 Ask AI Consultant", width="stretch", type="primary"):
            navigate_to("ai_assistant")
            st.rerun()
        if qa_2.button("💰 Budget Restock Planner", width="stretch"):
            navigate_to("inventory")
            st.rerun()
        if qa_3.button("🏷️ Simulate Product Pricing", width="stretch"):
            navigate_to("pricing_sim")
            st.rerun()

    with col_rail:
        render_business_insights_rail(ctx, key_prefix="dash_rail")
