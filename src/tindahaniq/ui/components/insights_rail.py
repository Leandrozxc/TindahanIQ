"""Right-hand Business Insights (Live Data) rail modeled on Proposal Page 7."""

from __future__ import annotations

import html
from decimal import Decimal

import streamlit as st

from tindahaniq.models.analytics import StockUrgency
from tindahaniq.ui.components.charts import build_weekly_sales_bar_chart
from tindahaniq.ui.context import AppContext
from tindahaniq.ui.state import navigate_to
from tindahaniq.ui.theme import format_php, urgency_badge_html


def render_business_insights_rail(ctx: AppContext, *, key_prefix: str = "rail") -> None:
    """Render Low Stock Alerts, Top-Selling Products, and Weekly Sales Trend cards."""
    st.markdown("#### 📈 Business Insights  `Live Data`")

    intel = ctx.inventory_intel.analyze_inventory(
        lookback_days=int(st.session_state.get("lookback_days", 14)),
        target_coverage_days=int(st.session_state.get("coverage_days", 7)),
    )
    sales_rep = ctx.sales_analytics.analyze_sales(granularity="daily", top_n=4)

    # 1. Low Stock Alert Card
    low_items = [r for r in intel.recommendations if r.urgency != StockUrgency.HEALTHY]
    with st.container(border=True):
        header_l, header_r = st.columns([3, 2])
        header_l.markdown("**🔴 Low Stock Alert**")
        header_r.caption(f"{intel.critical_count} of {len(low_items)} critical")

        if not low_items:
            st.caption("All active products are currently above their reorder thresholds.")
        else:
            for item in low_items[:3]:
                safe_name = html.escape(item.product_name)
                safe_unit = html.escape(item.unit)
                badge = urgency_badge_html(item.urgency)
                st.markdown(
                    f'<div class="tiq-insight-row">'
                    f'<div><div style="font-weight:600;font-size:0.9rem;">{safe_name}</div>'
                    f'<div style="color:#64748B;font-size:0.78rem;">'
                    f"Reorder point: {item.reorder_point} {safe_unit}</div></div>"
                    f'<div style="text-align:right;">'
                    f'<span style="font-weight:700;margin-right:6px;">'
                    f"{item.current_stock} {safe_unit}</span>{badge}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            if st.button(
                f"View all {len(low_items)} low-stock items →",
                key=f"{key_prefix}_view_low_stock",
                use_container_width=True,
            ):
                navigate_to("inventory")
                st.rerun()

    # 2. Top-Selling Products Card
    with st.container(border=True):
        top_l, top_r = st.columns([3, 2])
        top_l.markdown("**🏆 Top-Selling Products**")
        top_r.caption(f"{sales_rep.effective_days}d window")

        if not sales_rep.top_selling:
            st.caption("No product sales recorded yet.")
        else:
            for rank, prod in enumerate(sales_rep.top_selling[:4], start=1):
                safe_name = html.escape(prod.product_name)
                safe_unit = html.escape(prod.unit)
                rev_str = html.escape(format_php(prod.gross_revenue))
                st.markdown(
                    f'<div class="tiq-insight-row">'
                    f'<div><span style="background:#ECFDF5;color:#059669;'
                    f"padding:2px 7px;border-radius:999px;font-weight:700;"
                    f'font-size:0.78rem;margin-right:8px;">{rank}</span>'
                    f'<span style="font-weight:600;font-size:0.9rem;">{safe_name}</span>'
                    f'<div style="color:#64748B;font-size:0.78rem;margin-left:28px;">'
                    f"{prod.units_sold} {safe_unit} sold</div></div>"
                    f'<div style="color:#059669;font-weight:700;">{rev_str}</div>'
                    f"</div>",
                    unsafe_allow_html=True,
                )

    # 3. Weekly Sales Trend Card
    with st.container(border=True):
        recent_buckets = sales_rep.buckets[-7:]
        weekly_total = sum(
            (b.gross_revenue for b in recent_buckets),
            start=Decimal("0.00"),
        )
        tr_l, tr_r = st.columns([3, 2])
        tr_l.markdown("**📊 Sales Trend**")
        tr_r.caption(f"{format_php(weekly_total)} total")

        if not recent_buckets:
            st.caption("Upload or record sales transactions to view daily trends.")
        else:
            fig = build_weekly_sales_bar_chart(recent_buckets)
            st.plotly_chart(
                fig,
                use_container_width=True,
                config={"displayModeBar": False},
                key=f"{key_prefix}_weekly_chart",
            )
            foot_l, foot_r = st.columns(2)
            foot_l.caption(f"Daily Average: **{format_php(sales_rep.average_daily_revenue)}**")
            peak_text = sales_rep.peak_hour.label if sales_rep.peak_hour else "N/A"
            foot_r.caption(f"Peak Hour: **{peak_text}**")
