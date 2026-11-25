"""Reusable Plotly figure builders with PHP (₱) formatting and restrained styling."""

from __future__ import annotations

from collections.abc import Sequence

import plotly.graph_objects as go

from tindahaniq.models.analytics import (
    CategoryProfitability,
    PriceSimulationResult,
    ProductSalesPerformance,
    SalesPeriodBucket,
)
from tindahaniq.ui.theme import EMERALD_DARK, EMERALD_MINT, EMERALD_PRIMARY

_BASE_LAYOUT = {
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor": "rgba(0,0,0,0)",
    "font": {"family": "sans-serif", "color": "#0F172A"},
}


def build_weekly_sales_bar_chart(buckets: Sequence[SalesPeriodBucket]) -> go.Figure:
    """Build the compact 7-day bar chart modeled on Proposal Page 7's Weekly Sales Trend."""
    recent = list(buckets[-7:])
    labels = [b.period_start.strftime("%a %d") for b in recent]
    values = [float(b.gross_revenue) for b in recent]
    max_val = max(values) if values else 0.0
    colors = [EMERALD_DARK if (max_val > 0 and v == max_val) else EMERALD_MINT for v in values]

    fig = go.Figure(
        data=[
            go.Bar(
                x=labels,
                y=values,
                marker_color=colors,
                hovertemplate="<b>%{x}</b><br>Sales: ₱%{y:,.2f}<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        **_BASE_LAYOUT,
        height=190,
        margin={"l": 8, "r": 8, "t": 8, "b": 24},
        xaxis={"showgrid": False, "tickfont": {"size": 11}},
        yaxis={"showgrid": True, "gridcolor": "#F1F5F9", "tickprefix": "₱"},
        showlegend=False,
    )
    return fig


def build_revenue_profit_trend_chart(buckets: Sequence[SalesPeriodBucket]) -> go.Figure:
    """Build a grouped Revenue vs. Gross Profit time-series bar chart."""
    labels = [b.period_label for b in buckets]
    revenues = [float(b.gross_revenue) for b in buckets]
    profits = [float(b.gross_profit) for b in buckets]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            name="Gross Revenue",
            x=labels,
            y=revenues,
            marker_color="#94A3B8",
            hovertemplate="<b>%{x}</b><br>Gross Revenue: ₱%{y:,.2f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            name="Gross Profit",
            x=labels,
            y=profits,
            marker_color=EMERALD_PRIMARY,
            hovertemplate="<b>%{x}</b><br>Gross Profit: ₱%{y:,.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        **_BASE_LAYOUT,
        barmode="group",
        height=320,
        margin={"l": 16, "r": 16, "t": 28, "b": 32},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
        xaxis={"showgrid": False},
        yaxis={"gridcolor": "#E2E8F0", "tickprefix": "₱"},
    )
    return fig


def build_category_profit_chart(categories: Sequence[CategoryProfitability]) -> go.Figure:
    """Build a horizontal bar chart ranking gross profit by store category."""
    ordered = list(reversed(categories))
    names = [c.category for c in ordered]
    profits = [float(c.gross_profit) for c in ordered]
    revenues = [float(c.gross_revenue) for c in ordered]

    fig = go.Figure(
        data=[
            go.Bar(
                x=profits,
                y=names,
                orientation="h",
                marker_color=EMERALD_PRIMARY,
                customdata=revenues,
                hovertemplate=(
                    "<b>%{y}</b><br>Gross Profit: ₱%{x:,.2f}"
                    "<br>Gross Revenue: ₱%{customdata:,.2f}<extra></extra>"
                ),
            )
        ]
    )
    fig.update_layout(
        **_BASE_LAYOUT,
        height=max(240, 48 * len(names)),
        margin={"l": 16, "r": 16, "t": 16, "b": 24},
        xaxis={"gridcolor": "#E2E8F0", "tickprefix": "₱"},
        yaxis={"showgrid": False},
        showlegend=False,
    )
    return fig


def build_product_ranking_chart(
    items: Sequence[ProductSalesPerformance],
    *,
    color: str = EMERALD_PRIMARY,
) -> go.Figure:
    """Build a horizontal bar chart comparing product unit sales and revenue."""
    ordered = list(reversed(items))
    names = [p.product_name for p in ordered]
    units = [p.units_sold for p in ordered]
    revs = [float(p.gross_revenue) for p in ordered]

    fig = go.Figure(
        data=[
            go.Bar(
                x=units,
                y=names,
                orientation="h",
                marker_color=color,
                customdata=revs,
                hovertemplate=(
                    "<b>%{y}</b><br>Units Sold: %{x}<br>Revenue: ₱%{customdata:,.2f}<extra></extra>"
                ),
            )
        ]
    )
    fig.update_layout(
        **_BASE_LAYOUT,
        height=max(220, 46 * len(names)),
        margin={"l": 16, "r": 16, "t": 12, "b": 24},
        xaxis={"gridcolor": "#E2E8F0", "title": "Units Sold"},
        yaxis={"showgrid": False},
        showlegend=False,
    )
    return fig


def build_price_simulation_chart(sim: PriceSimulationResult) -> go.Figure:
    """Build a side-by-side Current vs. Proposed Revenue and Gross Profit chart."""
    metrics = ["Gross Revenue", "Gross Profit"]
    current_vals = [float(sim.baseline_gross_revenue), float(sim.baseline_gross_profit)]
    proposed_vals = [float(sim.simulated_gross_revenue), float(sim.simulated_gross_profit)]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            name=f"Current (₱{sim.current_price:,.2f})",
            x=metrics,
            y=current_vals,
            marker_color="#64748B",
            hovertemplate="<b>%{x}</b> (Current)<br>₱%{y:,.2f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            name=f"Simulated (₱{sim.proposed_price:,.2f})",
            x=metrics,
            y=proposed_vals,
            marker_color=EMERALD_PRIMARY if sim.gross_profit_delta >= 0 else "#DC2626",
            hovertemplate="<b>%{x}</b> (Simulated)<br>₱%{y:,.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        **_BASE_LAYOUT,
        barmode="group",
        height=290,
        margin={"l": 16, "r": 16, "t": 28, "b": 24},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
        yaxis={"gridcolor": "#E2E8F0", "tickprefix": "₱"},
    )
    return fig
