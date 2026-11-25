"""AI Business Assistant split workspace modeled directly on Proposal Page 7."""

from __future__ import annotations

import streamlit as st

from tindahaniq.exceptions import get_user_safe_message
from tindahaniq.ui.components import render_business_insights_rail, render_top_kpi_strip
from tindahaniq.ui.context import AppContext
from tindahaniq.ui.state import get_chat_session

SUGGESTED_ACTIONS: tuple[tuple[str, str], ...] = (
    ("⚡ Analyze My Profits", "Which of my products generates the highest profit and margin?"),
    ("⚠️ Check Low Stock Items", "Which low-stock products should I prioritize for restocking?"),
    (
        "📈 Review Sales Performance",
        "Can you summarize my sales performance and identify any slow-moving products?",
    ),
    (
        "💰 Plan ₱2,000 Restock",
        "I have ₱2,000 available for restocking. Which products should I prioritize?",
    ),
)


def render_ai_assistant(ctx: AppContext) -> None:
    """Render the Proposal Page 7 AI Assistant copilot and Live Business Insights rail."""
    st.title("AI Business Assistant")
    st.caption("Your intelligent partner for managing your sari-sari store.")

    render_top_kpi_strip(ctx)

    col_chat, col_rail = st.columns([7, 4], gap="medium")

    with col_rail:
        render_business_insights_rail(ctx, key_prefix="ai_rail")

    with col_chat, st.container(border=True):
        session = get_chat_session()
        ai_ready = ctx.settings.has_ai_api_key

        head_title, head_export, head_clear = st.columns([5, 2, 2])
        with head_title:
            badge_text = "🟢 Online & Ready" if ai_ready else "🟠 API Key Needed"
            st.markdown(f"#### 🤖 TindahanIQ AI Assistant  `{badge_text}`")
            st.caption(
                f"Connected to local SQLite store records • Model `{ctx.settings.gemini_model}`"
            )
        with head_export:
            st.download_button(
                label="⬇ Export Chat",
                data=session.export_markdown().encode("utf-8"),
                file_name="tindahaniq_consultation.md",
                mime="text/markdown",
                use_container_width=True,
                key="ai_export_chat_btn",
            )
        with head_clear:
            if st.button("🗑 Clear History", use_container_width=True, key="ai_clear_btn"):
                session.clear()
                st.rerun()

        st.divider()

        if not ai_ready:
            st.warning(
                "**AI Chat Configuration Required:** Add `GEMINI_API_KEY=<your_key>` to your "
                "local `.env` file and restart TindahanIQ to enable live AI conversations. "
                "All deterministic analytics, restock calculations, and simulations remain active."
            )

        active_count = len(ctx.inventory_service.list_inventory(active_only=True))
        if not session.messages:
            with st.chat_message("assistant"):
                store_name = str(
                    st.session_state.get("store_display_name", ctx.settings.store_name)
                )
                if active_count == 0:
                    st.markdown(
                        f"Kumusta! Welcome to **TindahanIQ** for **{store_name}**. "
                        "Your store catalog is currently empty — upload your Inventory and Sales "
                        "CSV files (or load the sample store dataset) so I can analyze your "
                        "profits, restocking needs, and pricing scenarios."
                    )
                else:
                    st.markdown(
                        f"Kumusta! Welcome to **TindahanIQ**. I am connected to **{store_name}** "
                        f"({active_count} active products). Ask me about your most profitable "
                        "items, restocking quantities, slow movers, or price change simulations!"
                    )

        for msg in session.messages:
            with st.chat_message(msg.role):
                st.markdown(msg.content)
                if msg.role == "assistant" and msg.tools_used:
                    tools_label = ", ".join(f"`{name}`" for name in msg.tools_used)
                    st.caption(f"Calculated via deterministic tools: {tools_label}")

        st.markdown("**SUGGESTED ACTIONS**")
        chip_cols = st.columns(2)
        for idx, (chip_label, chip_prompt) in enumerate(SUGGESTED_ACTIONS):
            target_col = chip_cols[idx % 2]
            if target_col.button(
                chip_label,
                key=f"ai_chip_{idx}",
                disabled=not ai_ready,
                use_container_width=True,
            ):
                st.session_state["pending_ai_prompt"] = chip_prompt

        typed_prompt = st.chat_input(
            "Ask TindahanIQ about your business...",
            disabled=not ai_ready,
            key="ai_chat_input",
        )
        queued_prompt = st.session_state.get("pending_ai_prompt")
        st.session_state["pending_ai_prompt"] = None

        effective_prompt = typed_prompt or queued_prompt
        if effective_prompt and ai_ready:
            with st.spinner("Analyzing store data and running deterministic calculations..."):
                try:
                    ctx.ai_consultant.ask(str(effective_prompt), session=session)
                    st.rerun()
                except Exception as exc:
                    st.error(get_user_safe_message(exc))

        st.caption(
            "🔒 TindahanIQ calculates figures strictly from your local store database. "
            "It does not execute supplier purchases, access banking accounts, or guarantee "
            "future sales."
        )
