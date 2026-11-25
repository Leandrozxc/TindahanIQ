"""Streamlit view modules for TindahanIQ."""

from tindahaniq.ui.pages.ai_assistant import render_ai_assistant
from tindahaniq.ui.pages.dashboard import render_dashboard
from tindahaniq.ui.pages.inventory import render_inventory
from tindahaniq.ui.pages.pricing_sim import render_pricing_sim
from tindahaniq.ui.pages.sales_profit import render_sales_profit
from tindahaniq.ui.pages.system_help import render_system_help
from tindahaniq.ui.pages.upload_data import render_upload_data

__all__ = [
    "render_ai_assistant",
    "render_dashboard",
    "render_inventory",
    "render_pricing_sim",
    "render_sales_profit",
    "render_system_help",
    "render_upload_data",
]
