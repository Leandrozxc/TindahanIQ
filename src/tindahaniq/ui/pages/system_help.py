"""Settings, Data Consistency Verification, System Health, and Retail Glossary view."""

from __future__ import annotations

import streamlit as st

from tindahaniq.exceptions import get_user_safe_message
from tindahaniq.health import CheckStatus, run_health_checks
from tindahaniq.ui.context import AppContext
from tindahaniq.ui.state import get_chat_session, set_flash_success

STATUS_LABELS: dict[CheckStatus, str] = {
    "ok": "PASS",
    "notice": "NOTICE",
    "error": "FAIL",
}


def render_system_help(ctx: AppContext) -> None:
    """Render store display preferences, data consistency audit, health check, and help guide."""
    st.title("Settings, Diagnostics & Help")
    st.caption("Configure analysis defaults, verify store data integrity, and review formulas.")

    col_pref, col_cons = st.columns(2, gap="medium")

    with col_pref, st.container(border=True):
        st.markdown("#### :material/storefront: Session Store Preferences")
        with st.form("session_preferences_form"):
            new_store = st.text_input(
                "Store Display Name",
                value=str(st.session_state.get("store_display_name", ctx.settings.store_name)),
                max_chars=100,
                key="pref_store_name",
            )
            new_lookback = st.number_input(
                "Default Velocity Lookback Window (Days)",
                min_value=1,
                max_value=90,
                value=int(st.session_state.get("lookback_days", 14)),
            )
            new_cov = st.number_input(
                "Default Target Restock Coverage (Days)",
                min_value=1,
                max_value=60,
                value=int(st.session_state.get("coverage_days", 7)),
            )
            if st.form_submit_button("Save Preferences", type="primary"):
                cleaned_name = new_store.strip() or ctx.settings.store_name
                st.session_state["store_display_name"] = cleaned_name
                st.session_state["lookback_days"] = int(new_lookback)
                st.session_state["coverage_days"] = int(new_cov)
                set_flash_success("Updated session preferences.")
                st.rerun()

    with col_cons, st.container(border=True):
        st.markdown("#### :material/verified_user: Data Consistency & Ledger Verification")
        consistency = ctx.consistency_service.verify_data_consistency()
        if consistency.is_consistent:
            st.success(
                f"Ledger Consistent: {consistency.products_checked} product(s) and "
                f"{consistency.sales_checked} sale(s) verified with 0 structural errors."
            )
        else:
            st.error(f"Detected {consistency.error_count} structural consistency error(s).")
        if consistency.issues:
            st.dataframe(
                [
                    {
                        "Severity": i.severity.upper(),
                        "Code": i.code,
                        "SKU": i.sku or "—",
                        "Details": i.message,
                    }
                    for i in consistency.issues
                ],
                width="stretch",
                hide_index=True,
            )

    with st.container(border=True):
        st.markdown("#### :material/monitor_heart: System & Environment Health")
        report = run_health_checks(ctx.settings)
        st.table(
            [
                {
                    "Diagnostic Check": item.name,
                    "Status": STATUS_LABELS[item.status],
                    "Details": item.detail,
                }
                for item in report.checks
            ]
        )

    with st.expander(
        "Sari-Sari Store Financial Glossary & Important Scope Notes",
        icon=":material/menu_book:",
        expanded=True,
    ):
        st.markdown(
            "\n".join(
                [
                    "- **Gross Revenue (₱):** Total sales collected (`Qty × Selling Price`).",
                    "- **Cost of Goods Sold — COGS (₱):** Supplier cost (`puhunan`) of items "
                    "sold (`Qty × Unit Cost`).",
                    "- **Gross Profit (₱):** Money earned after subtracting supplier item cost "
                    "(`Gross Revenue - COGS`).",
                    "- **Gross Profit Margin (%):** Share of selling price kept as profit "
                    "(`Gross Profit ÷ Gross Revenue × 100`).",
                    "- **Markup (%):** Percentage added on top of supplier cost "
                    "(`(Selling Price - Unit Cost) ÷ Unit Cost × 100`).",
                    "- **Scope & Limitations:** TindahanIQ provides decision-support analytics "
                    "based strictly on your uploaded/recorded data. It does **not** place "
                    "supplier orders, access bank/payment accounts, guarantee future sales, "
                    "or replace certified accounting or tax services.",
                ]
            )
        )

    with st.expander(
        "Reset / Clear Store Database",
        icon=":material/warning:",
        expanded=False,
    ):
        st.caption(
            "Use this to wipe all products, inventory, sales transactions, and CSV import "
            "history (for example, before switching between demo datasets)."
        )
        confirm_reset = st.checkbox(
            "I understand this permanently deletes all local store records.",
            key="confirm_reset_store_chk",
        )
        if st.button(
            "Clear All Store Data",
            icon=":material/delete_forever:",
            disabled=not confirm_reset,
            key="reset_store_data_btn",
        ):
            try:
                ctx.reset_store_data()
                get_chat_session().clear()
                set_flash_success("Cleared all local store products, inventory, and sales records.")
                st.rerun()
            except Exception as exc:
                st.error(get_user_safe_message(exc))
