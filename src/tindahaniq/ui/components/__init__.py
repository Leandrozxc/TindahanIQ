"""Reusable Streamlit UI components for TindahanIQ."""

from tindahaniq.ui.components.charts import (
    build_category_profit_chart,
    build_price_simulation_chart,
    build_product_ranking_chart,
    build_revenue_profit_trend_chart,
    build_weekly_sales_bar_chart,
)
from tindahaniq.ui.components.empty_states import render_empty_store_onboarding
from tindahaniq.ui.components.insights_rail import render_business_insights_rail
from tindahaniq.ui.components.kpi_cards import render_top_kpi_strip

__all__ = [
    "build_category_profit_chart",
    "build_price_simulation_chart",
    "build_product_ranking_chart",
    "build_revenue_profit_trend_chart",
    "build_weekly_sales_bar_chart",
    "render_business_insights_rail",
    "render_empty_store_onboarding",
    "render_top_kpi_strip",
]
