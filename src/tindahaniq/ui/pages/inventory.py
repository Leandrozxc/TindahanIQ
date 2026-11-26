"""Inventory Intelligence, Budget Restock Planner, and Operational Stock CRUD view."""

from __future__ import annotations

import csv
import io
from decimal import Decimal

import streamlit as st

from tindahaniq.exceptions import get_user_safe_message
from tindahaniq.models import (
    AdjustmentReason,
    ProductCreate,
    ProductUpdate,
    SaleItemInput,
    StockAdjustmentCreate,
    StockUrgency,
)
from tindahaniq.ui.components import render_empty_store_onboarding
from tindahaniq.ui.context import AppContext
from tindahaniq.ui.state import set_flash_success
from tindahaniq.ui.theme import format_manila_dt, format_php
from tindahaniq.utils import escape_csv_formula


def render_inventory(ctx: AppContext) -> None:
    """Render Inventory Intelligence, Budget Planner, POS Checkout, and Catalog CRUD."""
    st.title("Inventory & Restock Management")
    st.caption(
        "Monitor stock levels, calculate restocking quantities, plan wholesaler budgets, "
        "and record live store transactions."
    )

    tab_intel, tab_budget, tab_ops, tab_catalog = st.tabs(
        [
            ":material/inventory_2: Stock & Restock Intelligence",
            ":material/payments: Budget Restock Planner",
            ":material/point_of_sale: Record Sale / Adjust Stock",
            ":material/add_box: Manage Catalog & Audit Log",
        ]
    )

    with tab_intel:
        _render_stock_intelligence_tab(ctx)

    with tab_budget:
        _render_budget_planner_tab(ctx)

    with tab_ops:
        _render_operations_tab(ctx)

    with tab_catalog:
        _render_catalog_and_audit_tab(ctx)


def _render_stock_intelligence_tab(ctx: AppContext) -> None:
    if not ctx.has_active_products():
        render_empty_store_onboarding(ctx, key_prefix="inv_intel")
        return

    lookback = int(st.session_state.get("lookback_days", 14))
    coverage = int(st.session_state.get("coverage_days", 7))
    report = ctx.inventory_intel.analyze_inventory(
        lookback_days=lookback,
        target_coverage_days=coverage,
    )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Active Products", f"{report.total_active_products}")
    m2.metric("Critical / Out of Stock", f"{report.critical_count}")
    m3.metric("High / Low Alerts", f"{report.high_count + report.low_count}")
    m4.metric("Full Restock Estimate", format_php(report.total_suggested_restock_cost))

    f_search, f_cat, f_urg = st.columns([3, 2, 2])
    search_q = (
        f_search.text_input(
            "Search by product name or SKU",
            placeholder="e.g. Pancit Canton, BEV-001",
            key="inv_search_q",
        )
        .strip()
        .lower()
    )
    categories = ["All Categories", *ctx.inventory_service.list_categories(active_only=True)]
    selected_cat = f_cat.selectbox("Category", categories, key="inv_cat_filter")
    urgency_mode = f_urg.selectbox(
        "Stock Filter",
        ["All Active Products", "Needs Restock / Low Stock", "Critical Only"],
        key="inv_urg_filter",
    )

    filtered = list(report.recommendations)
    if search_q:
        filtered = [
            r for r in filtered if search_q in r.product_name.lower() or search_q in r.sku.lower()
        ]
    if selected_cat != "All Categories":
        filtered = [r for r in filtered if r.category == selected_cat]
    if urgency_mode == "Needs Restock / Low Stock":
        filtered = [
            r for r in filtered if r.urgency != StockUrgency.HEALTHY or r.suggested_restock_qty > 0
        ]
    elif urgency_mode == "Critical Only":
        filtered = [r for r in filtered if r.urgency == StockUrgency.CRITICAL]

    if not filtered:
        st.info("No products match the selected filters.")
    else:
        rows = [
            {
                "SKU": r.sku,
                "Product": r.product_name,
                "Category": r.category,
                "Stock": f"{r.current_stock} {r.unit}",
                "Reorder Pt": r.reorder_point,
                "Priority": r.urgency.value,
                "Daily Velocity": f"{r.daily_velocity:.2f}/day",
                "Est. Days Left": (
                    f"{r.estimated_days_to_depletion:.1f}d"
                    if r.estimated_days_to_depletion is not None
                    else "—"
                ),
                "Suggested Restock": f"{r.suggested_restock_qty} {r.unit}",
                "Unit Cost": format_php(r.unit_cost),
                "Selling Price": format_php(r.selling_price),
                "Restock Cost": format_php(r.estimated_restock_cost),
            }
            for r in filtered
        ]
        st.dataframe(rows, width="stretch", hide_index=True)

    with st.expander("Calculation Window & Assumptions"):
        for note in report.assumptions:
            st.markdown(f"- {note}")


def _render_budget_planner_tab(ctx: AppContext) -> None:
    if not ctx.has_active_products():
        render_empty_store_onboarding(ctx, key_prefix="inv_budget")
        return

    st.markdown(
        "Plan your wholesaler / Divisoria restocking trip by entering your available "
        "cash budget. TindahanIQ prioritizes **Critical** and fast-moving profitable staples."
    )
    b_col1, b_col2, b_col3 = st.columns(3)
    budget_val = b_col1.number_input(
        "Available Restocking Budget (₱)",
        min_value=50.0,
        max_value=500000.0,
        value=2000.0,
        step=100.0,
        key="budget_php_input",
    )
    lookback = int(
        b_col2.number_input(
            "Sales Lookback Window (Days)",
            min_value=1,
            max_value=90,
            value=int(st.session_state.get("lookback_days", 14)),
            key="budget_lookback_input",
        )
    )
    coverage = int(
        b_col3.number_input(
            "Target Stock Coverage (Days)",
            min_value=1,
            max_value=60,
            value=int(st.session_state.get("coverage_days", 7)),
            key="budget_cov_input",
        )
    )

    plan = ctx.inventory_intel.plan_restock_within_budget(
        Decimal(str(budget_val)),
        lookback_days=lookback,
        target_coverage_days=coverage,
    )

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Available Budget", format_php(plan.budget_php))
    k2.metric("Allocated Spend", format_php(plan.total_allocated_cost))
    k3.metric("Remaining Cash", format_php(plan.remaining_budget_php))
    k4.metric("Projected Gross Profit", format_php(plan.total_expected_gross_profit))

    if not plan.funded_items:
        st.info(
            "No restock items could be funded (either all stock is healthy or budget is too low)."
        )
    else:
        st.markdown("#### Recommended Restock Shopping List")
        funded_rows = [
            {
                "Priority": item.urgency.value,
                "SKU": item.sku,
                "Product": item.product_name,
                "Current Stock": f"{item.current_stock} {item.unit}",
                "Buy Qty": f"{item.funded_qty} {item.unit}",
                "Full Target Qty": f"{item.full_suggested_qty} {item.unit}",
                "Unit Cost": format_php(item.unit_cost),
                "Line Cost": format_php(item.allocated_cost),
                "Expected Profit": format_php(item.expected_gross_profit),
            }
            for item in plan.funded_items
        ]
        st.dataframe(funded_rows, width="stretch", hide_index=True)

        csv_buf = io.StringIO()
        writer = csv.DictWriter(csv_buf, fieldnames=list(funded_rows[0].keys()))
        writer.writeheader()
        safe_csv_rows = [
            {col: escape_csv_formula(val) for col, val in row.items()} for row in funded_rows
        ]
        writer.writerows(safe_csv_rows)
        st.download_button(
            "⬇ Download Restock Shopping List (.csv)",
            data=csv_buf.getvalue().encode("utf-8"),
            file_name="tindahaniq_restock_list.csv",
            mime="text/csv",
            key="download_restock_csv",
        )

    if plan.deferred_items:
        with st.expander(f"Unfunded / Deferred Items ({len(plan.deferred_items)})"):
            def_rows = [
                {
                    "Priority": i.urgency.value,
                    "SKU": i.sku,
                    "Product": i.product_name,
                    "Suggested Qty": f"{i.full_suggested_qty} {i.unit}",
                    "Unit Cost": format_php(i.unit_cost),
                }
                for i in plan.deferred_items
            ]
            st.dataframe(def_rows, width="stretch", hide_index=True)


def _render_operations_tab(ctx: AppContext) -> None:
    active_items = ctx.inventory_service.list_inventory(active_only=True)
    if not active_items:
        st.info("Add or import products first before recording walk-in sales or stock changes.")
        return

    options = {
        (
            f"{item.product.name} ({item.product.sku}) — "
            f"Stock: {item.inventory.current_stock} {item.product.unit}"
        ): item
        for item in active_items
    }
    labels = list(options.keys())

    col_sale, col_adj = st.columns(2, gap="medium")

    with col_sale, st.container(border=True):
        st.markdown("#### :material/point_of_sale: Record Walk-In Sale")
        st.caption("Atomically records revenue/COGS and deducts shelf stock.")
        with st.form("record_walkin_sale_form", clear_on_submit=True):
            chosen_sale_label = st.selectbox("Product", labels, key="pos_prod_sel")
            sale_qty = st.number_input("Quantity Sold", min_value=1, value=1, step=1)
            use_override = st.checkbox("Use custom promo/override unit price?")
            override_val = st.number_input(
                "Custom Unit Price (₱)", min_value=0.01, value=15.00, step=0.50
            )
            ref_note = st.text_input("Receipt / Reference (Optional)", placeholder="e.g. WALKIN-01")
            submitted_sale = st.form_submit_button("Record Sale", type="primary")
            if submitted_sale:
                target_item = options[chosen_sale_label]
                try:
                    tx = ctx.sales_service.record_sale(
                        SaleItemInput(
                            product_id=target_item.product.id,
                            quantity_sold=int(sale_qty),
                            unit_price_override=(
                                Decimal(str(override_val)) if use_override else None
                            ),
                            external_ref=ref_note or None,
                        ),
                        deduct_stock=True,
                    )
                    set_flash_success(
                        f"Recorded sale of {tx.quantity_sold} {target_item.product.unit} "
                        f"`{target_item.product.name}` ({format_php(tx.gross_revenue)})."
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(get_user_safe_message(exc))

    with col_adj, st.container(border=True):
        st.markdown("#### :material/assignment: Restock or Adjust Stock")
        st.caption("Log incoming supplier restocks, damaged/spoiled goods, or physical counts.")
        with st.form("stock_adjustment_form", clear_on_submit=True):
            chosen_adj_label = st.selectbox("Product", labels, key="adj_prod_sel")
            adj_mode = st.selectbox(
                "Adjustment Type",
                [
                    "Supplier Restock (+)",
                    "Spoilage / Damaged (-)",
                    "Set Exact Physical Shelf Count",
                ],
            )
            adj_qty = st.number_input("Quantity", min_value=0, value=10, step=1)
            adj_notes = st.text_input("Notes (Optional)", placeholder="e.g. Divisoria restock")
            submitted_adj = st.form_submit_button("Apply Stock Update", type="primary")
            if submitted_adj:
                target_item = options[chosen_adj_label]
                pid = target_item.product.id
                try:
                    if adj_mode == "Supplier Restock (+)":
                        updated, _ = ctx.inventory_service.restock_product(
                            pid, int(adj_qty), notes=adj_notes or None
                        )
                    elif adj_mode == "Spoilage / Damaged (-)":
                        updated, _ = ctx.inventory_service.adjust_stock(
                            StockAdjustmentCreate(
                                product_id=pid,
                                quantity_delta=-int(adj_qty),
                                reason=AdjustmentReason.SPOILAGE,
                                notes=adj_notes or None,
                            )
                        )
                    else:
                        updated, _ = ctx.inventory_service.reconcile_stock_count(
                            pid, int(adj_qty), notes=adj_notes or None
                        )
                    set_flash_success(
                        f"Updated `{updated.product.name}` stock to "
                        f"{updated.inventory.current_stock} {updated.product.unit}."
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(get_user_safe_message(exc))


def _render_catalog_and_audit_tab(ctx: AppContext) -> None:
    col_add, col_edit = st.columns(2, gap="medium")

    with col_add, st.container(border=True):
        st.markdown("#### :material/add_circle: Add New Product")
        with st.form("add_product_form", clear_on_submit=True):
            p_name = st.text_input(
                "Product Name *",
                placeholder="e.g. Milo Activ-Go 24g",
                key="add_prod_name",
            )
            c1, c2 = st.columns(2)
            p_sku = c1.text_input("SKU (Optional — auto-generated if blank)")
            p_cat = c2.text_input("Category", value="Beverages")
            c3, c4, c5 = st.columns(3)
            p_unit = c3.text_input("Unit", value="sachet")
            p_cost = c4.number_input("Supplier Cost (₱) *", min_value=0.0, value=8.50, step=0.25)
            p_price = c5.number_input("Selling Price (₱) *", min_value=0.01, value=11.00, step=0.25)
            c6, c7, c8 = st.columns(3)
            p_stock = c6.number_input("Initial Stock", min_value=0, value=24, step=1)
            p_reorder = c7.number_input("Reorder Point", min_value=0, value=12, step=1)
            p_lead = c8.number_input("Lead Time (Days)", min_value=1, value=1, step=1)

            if st.form_submit_button("Create Product", type="primary"):
                try:
                    created = ctx.inventory_service.create_product(
                        ProductCreate(
                            sku=p_sku or None,
                            name=p_name,
                            category=p_cat,
                            unit=p_unit,
                            unit_cost=Decimal(str(p_cost)),
                            selling_price=Decimal(str(p_price)),
                            current_stock=int(p_stock),
                            reorder_point=int(p_reorder),
                            lead_time_days=int(p_lead),
                        )
                    )
                    set_flash_success(
                        f"Added `{created.product.name}` ({created.product.sku}) to catalog."
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(get_user_safe_message(exc))

    with col_edit, st.container(border=True):
        st.markdown("#### :material/edit: Update Price / Archive Product")
        all_items = ctx.inventory_service.list_inventory(active_only=False)
        if not all_items:
            st.caption("No catalog products available to edit yet.")
        else:
            item_map = {
                f"{i.product.name} ({i.product.sku})"
                + ("" if i.product.is_active else " [ARCHIVED]"): i
                for i in all_items
            }
            sel_key = st.selectbox("Select Product", list(item_map.keys()), key="edit_prod_sel")
            sel_item = item_map[sel_key]

            with st.form("edit_product_form"):
                u_cost = st.number_input(
                    "Unit Cost (₱)",
                    min_value=0.0,
                    value=float(sel_item.product.unit_cost),
                    step=0.25,
                )
                u_price = st.number_input(
                    "Selling Price (₱)",
                    min_value=0.01,
                    value=float(sel_item.product.selling_price),
                    step=0.25,
                )
                u_reorder = st.number_input(
                    "Reorder Point",
                    min_value=0,
                    value=int(sel_item.inventory.reorder_point),
                    step=1,
                )
                save_btn = st.form_submit_button("Save Product Changes")
                if save_btn:
                    try:
                        ctx.inventory_service.update_product(
                            sel_item.product.id,
                            ProductUpdate(
                                unit_cost=Decimal(str(u_cost)),
                                selling_price=Decimal(str(u_price)),
                                reorder_point=int(u_reorder),
                            ),
                        )
                        set_flash_success(f"Updated `{sel_item.product.name}`.")
                        st.rerun()
                    except Exception as exc:
                        st.error(get_user_safe_message(exc))

            if sel_item.product.is_active:
                if st.button("Archive Product", key="archive_prod_btn"):
                    ctx.inventory_service.deactivate_product(sel_item.product.id)
                    set_flash_success(f"Archived `{sel_item.product.name}`.")
                    st.rerun()
            else:
                if st.button("Reactivate Product", key="restore_prod_btn", type="primary"):
                    ctx.inventory_service.reactivate_product(sel_item.product.id)
                    set_flash_success(f"Reactivated `{sel_item.product.name}`.")
                    st.rerun()

    st.markdown("#### :material/history: Recent Stock Adjustment Audit Log")
    adjustments = list(reversed(ctx.inventory_service.get_adjustment_history(limit=25)))
    if not adjustments:
        st.caption("No stock adjustments logged yet.")
    else:
        id_to_sku = {
            i.product.id: f"{i.product.name} ({i.product.sku})"
            for i in ctx.inventory_service.list_inventory(active_only=False)
        }
        adj_rows = [
            {
                "Timestamp (PHT)": format_manila_dt(a.created_at),
                "Product": id_to_sku.get(a.product_id, f"#{a.product_id}"),
                "Delta": f"{a.quantity_delta:+d}",
                "Reason": a.reason.value,
                "Notes": a.notes or "—",
            }
            for a in adjustments
        ]
        st.dataframe(adj_rows, width="stretch", hide_index=True)
