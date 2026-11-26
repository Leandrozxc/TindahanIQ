"""CSV Upload, Dry-Run Validation Preview, Templates, and Sample Dataset view."""

from __future__ import annotations

import streamlit as st

from tindahaniq.db.repositories import ImportBatchRepository
from tindahaniq.exceptions import get_user_safe_message
from tindahaniq.models import CSVImportResult, ExistingProductPolicy
from tindahaniq.ui.context import AppContext
from tindahaniq.ui.state import set_flash_success
from tindahaniq.ui.theme import format_manila_dt

INVENTORY_TEMPLATE_CSV = (
    "sku,product_name,category,unit,unit_cost,selling_price,current_stock,reorder_point,lead_time_days\n"
    "NOOD-001,Lucky Me! Pancit Canton Calamansi 80g,Instant Noodles,pack,12.25,16.00,24,12,1\n"
    "BEV-001,Coca-Cola Mismo 290ml,Beverages,bottle,14.00,20.00,36,24,1\n"
)

SALES_TEMPLATE_CSV = (
    "transaction_id,sold_at,sku,product_name,quantity_sold,unit_price\n"
    "TXN-1001,2026-11-24 08:30:00,NOOD-001,Lucky Me! Pancit Canton Calamansi 80g,4,16.00\n"
    "TXN-1002,2026-11-24 12:15:00,BEV-001,Coca-Cola Mismo 290ml,6,20.00\n"
)


def render_upload_data(ctx: AppContext) -> None:
    """Render CSV upload forms, template downloads, sample loader, and import audit history."""
    st.title("Upload Store Data")
    st.caption(
        "Import your sari-sari store product inventory and historical sales CSV records "
        "with automatic validation and duplicate protection."
    )

    with st.container(border=True):
        t_col1, t_col2, t_col3, t_col4 = st.columns(4)
        t_col1.download_button(
            "⬇ Inventory CSV Template",
            data=INVENTORY_TEMPLATE_CSV.encode("utf-8"),
            file_name="tindahaniq_inventory_template.csv",
            mime="text/csv",
            width="stretch",
        )
        t_col2.download_button(
            "⬇ Sales CSV Template",
            data=SALES_TEMPLATE_CSV.encode("utf-8"),
            file_name="tindahaniq_sales_template.csv",
            mime="text/csv",
            width="stretch",
        )
        if t_col3.button(
            "🏪 Load Baseline Sample (10 Items)",
            width="stretch",
            key="upload_load_sample_btn",
        ):
            try:
                inv_cnt, sales_cnt = ctx.load_sample_store_data("baseline")
                set_flash_success(
                    f"Loaded baseline sample dataset ({inv_cnt} products, {sales_cnt} sales)."
                )
                st.rerun()
            except Exception as exc:
                st.error(get_user_safe_message(exc))
        if t_col4.button(
            "📊 Load 14-Day Demo (18 Items)",
            width="stretch",
            key="upload_load_demo14d_btn",
        ):
            try:
                inv_cnt, sales_cnt = ctx.load_sample_store_data("demo_14d")
                set_flash_success(
                    f"Loaded 14-day demo dataset ({inv_cnt} products, {sales_cnt} sales)."
                )
                st.rerun()
            except Exception as exc:
                st.error(get_user_safe_message(exc))

    tab_inv, tab_sales = st.tabs(["📦 1. Upload Inventory CSV", "🧾 2. Upload Sales CSV"])

    with tab_inv, st.container(border=True):
        st.markdown("#### Upload Product Inventory CSV")
        st.caption(
            "Required columns: `product_name`, `unit_cost`, `selling_price`, `current_stock` "
            "(also accepts local headers like `pangalan`, `puhunan`, `presyo`, `stock`)."
        )
        inv_file = st.file_uploader("Choose Inventory `.csv` file", type=["csv"], key="inv_csv_up")
        ic1, ic2, ic3 = st.columns(3)
        policy_choice = ic1.selectbox(
            "When SKU already exists",
            [("update", "Update existing product & stock"), ("skip", "Skip duplicate SKU")],
            format_func=lambda opt: opt[1],
            key="inv_dup_policy",
        )
        inv_dry_run = ic2.checkbox("Validate only (Dry-Run Preview)", key="inv_dry_chk")
        inv_reimport = ic3.checkbox("Allow re-uploading identical file", key="inv_reimp_chk")

        if st.button(
            "Validate Inventory CSV" if inv_dry_run else "Import Inventory CSV",
            type="primary",
            disabled=inv_file is None,
            key="run_inv_import_btn",
        ):
            assert inv_file is not None
            with st.spinner("Validating and processing inventory CSV..."):
                try:
                    res = ctx.csv_importer.import_inventory_csv(
                        inv_file.getvalue(),
                        filename=inv_file.name,
                        on_existing=ExistingProductPolicy(policy_choice[0]),
                        allow_reimport=inv_reimport,
                        dry_run=inv_dry_run,
                    )
                    _render_import_result(res)
                except Exception as exc:
                    st.error(get_user_safe_message(exc))

    with tab_sales, st.container(border=True):
        st.markdown("#### Upload Historical Sales CSV")
        st.caption(
            "Required columns: `sold_at` (or `date`), `sku` or `product_name`, "
            "and `quantity_sold`. Import your Inventory CSV first so products exist "
            "in the catalog."
        )
        sales_file = st.file_uploader("Choose Sales `.csv` file", type=["csv"], key="sales_csv_up")
        sc1, sc2 = st.columns(2)
        sales_dry_run = sc1.checkbox("Validate only (Dry-Run Preview)", key="sales_dry_chk")
        sales_reimport = sc2.checkbox("Allow re-uploading identical file", key="sales_reimp_chk")

        if st.button(
            "Validate Sales CSV" if sales_dry_run else "Import Sales CSV",
            type="primary",
            disabled=sales_file is None,
            key="run_sales_import_btn",
        ):
            assert sales_file is not None
            with st.spinner("Validating and processing sales CSV..."):
                try:
                    res = ctx.csv_importer.import_sales_csv(
                        sales_file.getvalue(),
                        filename=sales_file.name,
                        allow_reimport=sales_reimport,
                        dry_run=sales_dry_run,
                    )
                    _render_import_result(res)
                except Exception as exc:
                    st.error(get_user_safe_message(exc))

    st.markdown("#### Recent CSV Import History")
    batches = ImportBatchRepository(ctx.db).list_batches()
    if not batches:
        st.caption("No CSV files have been imported yet.")
    else:
        batch_rows = [
            {
                "Imported At (PHT)": format_manila_dt(b.imported_at),
                "Type": b.import_type.value,
                "Filename": b.filename,
                "Total Rows": b.rows_total,
                "Accepted": b.rows_accepted,
                "Duplicates Skipped": b.rows_skipped_duplicate,
                "Rejected": b.rows_rejected,
            }
            for b in batches[:15]
        ]
        st.dataframe(batch_rows, width="stretch", hide_index=True)


def _render_import_result(res: CSVImportResult) -> None:
    mode_prefix = "Dry-Run Preview" if res.dry_run else "Import Completed"
    if res.rows_accepted > 0 and res.rows_rejected == 0:
        st.success(f"**{mode_prefix}:** {res.rows_accepted} of {res.rows_total} row(s) accepted.")
    elif res.rows_accepted > 0:
        st.warning(
            f"**{mode_prefix} (Partial):** {res.rows_accepted} accepted, "
            f"{res.rows_rejected} rejected, {res.rows_skipped_duplicate} skipped."
        )
    else:
        st.error(f"**{mode_prefix}:** 0 rows accepted ({res.rows_rejected} rejected).")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Rows", res.rows_total)
    m2.metric("Created / Updated", f"{res.rows_created} / {res.rows_updated}")
    m3.metric("Duplicates Skipped", res.rows_skipped_duplicate)
    m4.metric("Rejected Rows", res.rows_rejected)

    if res.warnings:
        st.markdown("**Data Quality Warnings**")
        st.dataframe(
            [
                {"CSV Line": w.row_number, "Field": w.field, "Warning": w.message}
                for w in res.warnings
            ],
            width="stretch",
            hide_index=True,
        )

    if res.errors:
        st.markdown("**Rejected Rows (Action Required)**")
        st.dataframe(
            [
                {
                    "CSV Line": e.row_number,
                    "Column": e.field,
                    "Value": e.raw_value,
                    "Reason": e.message,
                }
                for e in res.errors
            ],
            width="stretch",
            hide_index=True,
        )
