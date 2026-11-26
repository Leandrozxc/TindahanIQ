"""Reusable empty-state onboarding component when store database has zero products."""

from __future__ import annotations

import streamlit as st

from tindahaniq.exceptions import get_user_safe_message
from tindahaniq.ui.context import AppContext
from tindahaniq.ui.state import navigate_to, set_flash_success


def render_empty_store_onboarding(ctx: AppContext, *, key_prefix: str) -> None:
    """Display an actionable onboarding card when no inventory items exist yet."""
    with st.container(border=True):
        st.subheader("Welcome to TindahanIQ — Let's Set Up Your Store")
        st.markdown(
            "Your store database does not have any products or sales records yet. "
            "To unlock real profitability analytics, low-stock restock quantities, "
            "pricing simulations, and AI consultation:"
        )
        col_upload, col_sample = st.columns(2)
        with col_upload:
            if st.button(
                "📤 Upload Your Store CSV Files",
                key=f"{key_prefix}_goto_upload",
                type="primary",
                width="stretch",
            ):
                navigate_to("upload_data")
                st.rerun()
        with col_sample:
            if st.button(
                "🏪 Load Sample Sari-Sari Store Dataset (Demo)",
                key=f"{key_prefix}_load_sample",
                width="stretch",
            ):
                try:
                    inv_cnt, sales_cnt = ctx.load_sample_store_data()
                    set_flash_success(
                        f"Loaded sample demo dataset: {inv_cnt} products and "
                        f"{sales_cnt} sales transactions."
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(get_user_safe_message(exc))
        st.caption(
            "Note: Sample dataset loads realistic Filipino sari-sari store products "
            "(Lucky Me!, Coca-Cola Mismo, Great Taste, Silver Swan, Bear Brand, etc.) "
            "clearly identified for testing and academic demonstration."
        )
