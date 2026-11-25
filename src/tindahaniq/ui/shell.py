"""Main navigation shell, sidebar layout, and page router for TindahanIQ."""

from __future__ import annotations

from collections.abc import Callable

import streamlit as st

from tindahaniq import __version__
from tindahaniq.config import AppSettings
from tindahaniq.ui.context import AppContext, build_app_context
from tindahaniq.ui.pages import (
    render_ai_assistant,
    render_dashboard,
    render_inventory,
    render_pricing_sim,
    render_sales_profit,
    render_system_help,
    render_upload_data,
)
from tindahaniq.ui.state import (
    PAGE_ITEMS,
    PageKey,
    consume_flash_success,
    get_active_page,
    init_session_state,
    navigate_to,
)
from tindahaniq.ui.theme import inject_theme_css

ROUTES: dict[PageKey, Callable[[AppContext], None]] = {
    "dashboard": render_dashboard,
    "ai_assistant": render_ai_assistant,
    "inventory": render_inventory,
    "sales_profit": render_sales_profit,
    "pricing_sim": render_pricing_sim,
    "upload_data": render_upload_data,
    "system_help": render_system_help,
}


def render_sidebar(ctx: AppContext) -> None:
    """Render the Proposal Page 7 left navigation sidebar and active store footer."""
    active_page = get_active_page()
    store_display = str(st.session_state.get("store_display_name", ctx.settings.store_name))

    with st.sidebar:
        st.title(ctx.settings.app_name)
        st.caption("Smarter Business Decisions.")
        st.divider()

        for page_key, label in PAGE_ITEMS:
            is_current = page_key == active_page
            if st.button(
                label,
                key=f"nav_{page_key}",
                type="primary" if is_current else "secondary",
                use_container_width=True,
            ):
                navigate_to(page_key)
                st.rerun()

        st.divider()
        st.markdown(f"**🏪 {store_display}**")
        st.caption(
            f"Currency: {ctx.settings.currency_symbol} ({ctx.settings.currency_code}) "
            f"• v{__version__}"
        )


def run_ui(settings: AppSettings) -> None:
    """Initialize session state, theme CSS, services, sidebar, and active page view."""
    inject_theme_css()
    init_session_state(settings)
    active_store_name = str(st.session_state.get("store_display_name", settings.store_name))
    ctx = build_app_context(settings, store_name=active_store_name)
    render_sidebar(ctx)

    flash_msg = consume_flash_success()
    if flash_msg:
        st.success(flash_msg)

    active_page = get_active_page()
    view_fn = ROUTES[active_page]
    view_fn(ctx)
