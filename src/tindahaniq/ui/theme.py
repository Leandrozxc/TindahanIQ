"""Theme tokens, scoped CSS styling, currency formatters, and urgency badges."""

from __future__ import annotations

import html
from decimal import Decimal

import streamlit as st

from tindahaniq.models.analytics import StockUrgency

EMERALD_DARK = "#065F46"
EMERALD_PRIMARY = "#059669"
EMERALD_MINT = "#A7F3D0"
SLATE_NAVY = "#0F292A"
AMBER_WARN = "#D97706"
CRIMSON_ALERT = "#DC2626"

URGENCY_STYLES: dict[StockUrgency, tuple[str, str, str]] = {
    StockUrgency.CRITICAL: ("#FEE2E2", "#B91C1C", "Critical"),
    StockUrgency.HIGH: ("#FEF3C7", "#B45309", "High"),
    StockUrgency.LOW: ("#E0F2FE", "#0369A1", "Low"),
    StockUrgency.HEALTHY: ("#DCFCE7", "#15803D", "Healthy"),
}


def format_php(amount: Decimal | int | float | None) -> str:
    """Format a monetary figure in Philippine Peso with tabular precision."""
    if amount is None:
        return "—"
    dec = Decimal(str(amount))
    if dec < 0:
        return f"-₱{abs(dec):,.2f}"
    return f"₱{dec:,.2f}"


def format_pct(rate: Decimal | None, *, signed: bool = False) -> str:
    """Format a percentage figure or return an em-dash if undefined."""
    if rate is None:
        return "—"
    if signed:
        return f"{rate:+.1f}%"
    return f"{rate:.1f}%"


def urgency_badge_html(urgency: StockUrgency) -> str:
    """Render a compact pill badge for stock urgency status."""
    bg, fg, label = URGENCY_STYLES[urgency]
    safe_label = html.escape(label)
    return (
        f'<span style="background:{bg};color:{fg};padding:2px 8px;'
        f'border-radius:999px;font-size:0.75rem;font-weight:600;">{safe_label}</span>'
    )


def inject_theme_css() -> None:
    """Inject restrained, tabular-numeral and sidebar styling modeled on Proposal Page 7."""
    st.markdown(
        """
        <style>
        /* Tabular numerals across metrics and tables for crisp PHP alignment */
        [data-testid="stMetricValue"],
        [data-testid="stMetricDelta"],
        [data-testid="stTable"],
        [data-testid="stDataFrame"],
        .tiq-tabular {
            font-variant-numeric: tabular-nums;
        }

        /* Sidebar dark slate-emerald styling inspired by Proposal Page 7 */
        [data-testid="stSidebar"] {
            background-color: #0F292A;
        }
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h1,
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h2,
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3,
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] span,
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
            color: #E2E8F0 !important;
        }
        [data-testid="stSidebar"] button[kind="secondary"] {
            background-color: transparent;
            color: #E2E8F0 !important;
            border: 1px solid rgba(226, 232, 240, 0.14);
            text-align: left;
            justify-content: flex-start;
        }
        [data-testid="stSidebar"] button[kind="secondary"]:hover {
            background-color: rgba(5, 150, 105, 0.22);
            border-color: #10B981;
        }
        [data-testid="stSidebar"] button[kind="primary"] {
            background-color: #059669 !important;
            border-color: #059669 !important;
            color: #FFFFFF !important;
            font-weight: 600;
            justify-content: flex-start;
        }

        /* Compact insight item rows */
        .tiq-insight-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px 0;
            border-bottom: 1px solid #F1F5F9;
            font-variant-numeric: tabular-nums;
        }
        .tiq-insight-row:last-child {
            border-bottom: none;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
