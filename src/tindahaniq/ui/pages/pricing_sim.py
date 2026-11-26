"""Interactive Pricing Simulator view."""

from __future__ import annotations

from decimal import Decimal

import streamlit as st

from tindahaniq.exceptions import get_user_safe_message
from tindahaniq.ui.components import build_price_simulation_chart, render_empty_store_onboarding
from tindahaniq.ui.context import AppContext
from tindahaniq.ui.theme import format_pct, format_php


def render_pricing_sim(ctx: AppContext) -> None:
    """Render the interactive product price-change and margin simulator."""
    st.title("Pricing Simulator")
    st.caption(
        "Test hypothetical selling-price changes and compare unit margins, breakeven volume "
        "sensitivity, and projected profit before changing shelf tags."
    )

    if not ctx.has_active_products():
        render_empty_store_onboarding(ctx, key_prefix="pricing_sim")
        return

    active_items = ctx.inventory_service.list_inventory(active_only=True)
    prod_map = {
        f"{i.product.name} ({i.product.sku}) — Current: {format_php(i.product.selling_price)}": i
        for i in active_items
    }

    col_cfg, col_res = st.columns([4, 7], gap="medium")

    with col_cfg, st.container(border=True):
        st.markdown("#### Simulation Parameters")
        chosen_label = st.selectbox("Select Product", list(prod_map.keys()), key="sim_prod_sel")
        selected = prod_map[chosen_label]
        prod = selected.product

        st.caption(
            f"Supplier Cost: **{format_php(prod.unit_cost)}** / {prod.unit} • "
            f"Current Unit Profit: **{format_php(prod.unit_profit)}**"
        )

        mode = st.radio(
            "Price Adjustment Mode",
            [
                "Change by Peso Amount (₱)",
                "Set Target Selling Price (₱)",
                "Change by Percentage (%)",
            ],
            key="sim_mode_radio",
        )

        new_price: Decimal | None = None
        delta_php: Decimal | None = None
        pct_change: Decimal | None = None

        if mode == "Change by Peso Amount (₱)":
            raw_delta = st.number_input(
                "Peso Change per Unit (₱)",
                min_value=-float(prod.selling_price) + 0.25,
                max_value=500.0,
                value=2.00,
                step=0.50,
                key="sim_delta_input",
            )
            delta_php = Decimal(str(raw_delta))
        elif mode == "Set Target Selling Price (₱)":
            raw_target = st.number_input(
                "Proposed New Selling Price (₱)",
                min_value=0.25,
                max_value=10000.0,
                value=float(prod.selling_price) + 2.00,
                step=0.50,
                key="sim_target_input",
            )
            new_price = Decimal(str(raw_target))
        else:
            raw_pct = st.slider(
                "Price Percentage Change (%)",
                min_value=-50,
                max_value=100,
                value=10,
                step=1,
                key="sim_pct_slider",
            )
            pct_change = Decimal(str(raw_pct))

        vol_change = st.slider(
            "Expected Customer Volume Change (%)",
            min_value=-50,
            max_value=50,
            value=0,
            step=5,
            help=(
                "Estimate whether higher prices might reduce unit sales "
                "(or lower prices boost sales)."
            ),
            key="sim_vol_slider",
        )
        use_custom_vol = st.checkbox(
            "Override historical unit sales volume?",
            key="sim_override_vol_chk",
        )
        custom_units: int | None = None
        if use_custom_vol:
            custom_units = int(
                st.number_input(
                    f"Simulated Baseline Volume ({prod.unit}s)",
                    min_value=1,
                    max_value=100000,
                    value=30,
                    step=5,
                    key="sim_custom_units_in",
                )
            )

    with col_res:
        try:
            sim = ctx.pricing_sim.simulate_price_change(
                prod.id,
                new_selling_price=new_price,
                price_delta_php=delta_php,
                price_change_pct=pct_change,
                expected_volume_change_pct=Decimal(str(vol_change)),
                baseline_units_override=custom_units,
            )
        except Exception as exc:
            st.error(get_user_safe_message(exc))
            return

        st.info(
            "**Hypothetical Simulation:** Figures below model potential price impacts and do "
            "not modify your actual catalog selling price."
        )
        for warn in sim.warnings:
            st.warning(warn)

        r1, r2, r3, r4 = st.columns(4)
        r1.metric(
            "Proposed Price",
            format_php(sim.proposed_price),
            delta=(
                f"{format_php(sim.price_delta_php)} "
                f"({format_pct(sim.price_change_pct, signed=True)})"
            ),
        )
        r2.metric(
            "Unit Gross Profit",
            format_php(sim.proposed_unit_profit),
            delta=format_php(sim.unit_profit_delta),
        )
        r3.metric(
            "Proposed Margin",
            format_pct(sim.proposed_margin_pct),
            delta=(
                f"{sim.margin_pct_point_delta:+.2f} pts"
                if sim.margin_pct_point_delta is not None
                else None
            ),
        )
        r4.metric(
            f"Projected Profit ({sim.simulated_units} {sim.unit})",
            format_php(sim.simulated_gross_profit),
            delta=format_php(sim.gross_profit_delta),
        )

        if sim.breakeven_volume_change_pct is not None:
            if sim.breakeven_volume_change_pct < 0:
                st.success(
                    f"**Volume Cushion:** At **{format_php(sim.proposed_price)}**, unit sales "
                    f"could drop by up to **{abs(sim.breakeven_volume_change_pct):.1f}%** before "
                    "total gross profit falls below current levels."
                )
            elif sim.breakeven_volume_change_pct > 0:
                st.warning(
                    f"**Volume Needed to Break Even:** Lowering the price to "
                    f"**{format_php(sim.proposed_price)}** requires at least "
                    f"**+{sim.breakeven_volume_change_pct:.1f}%** more units sold to match "
                    "your current gross profit."
                )

        with st.container(border=True):
            st.markdown("#### Current vs. Simulated Financial Comparison")
            st.plotly_chart(
                build_price_simulation_chart(sim),
                width="stretch",
                config={"displayModeBar": False},
                key="sim_comparison_chart",
            )

            comp_table = [
                {
                    "Metric": "Selling Price per Unit",
                    "Current": format_php(sim.current_price),
                    "Simulated": format_php(sim.proposed_price),
                    "Difference": format_php(sim.price_delta_php),
                },
                {
                    "Metric": "Gross Profit per Unit",
                    "Current": format_php(sim.current_unit_profit),
                    "Simulated": format_php(sim.proposed_unit_profit),
                    "Difference": format_php(sim.unit_profit_delta),
                },
                {
                    "Metric": "Gross Margin (%)",
                    "Current": format_pct(sim.current_margin_pct),
                    "Simulated": format_pct(sim.proposed_margin_pct),
                    "Difference": (
                        f"{sim.margin_pct_point_delta:+.2f} pts"
                        if sim.margin_pct_point_delta is not None
                        else "—"
                    ),
                },
                {
                    "Metric": "Markup on Cost (%)",
                    "Current": format_pct(sim.current_markup_pct),
                    "Simulated": format_pct(sim.proposed_markup_pct),
                    "Difference": "—",
                },
                {
                    "Metric": (
                        f"Total Revenue ({sim.baseline_units} → {sim.simulated_units} {sim.unit})"
                    ),
                    "Current": format_php(sim.baseline_gross_revenue),
                    "Simulated": format_php(sim.simulated_gross_revenue),
                    "Difference": format_php(sim.revenue_delta),
                },
                {
                    "Metric": "Total Gross Profit",
                    "Current": format_php(sim.baseline_gross_profit),
                    "Simulated": format_php(sim.simulated_gross_profit),
                    "Difference": format_php(sim.gross_profit_delta),
                },
            ]
            st.table(comp_table)

        with st.expander("Simulation Assumptions"):
            for note in sim.assumptions:
                st.markdown(f"- {note}")
