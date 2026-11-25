"""Unit tests verifying exact hand-calculated Decimal formulas and edge cases."""

from __future__ import annotations

from decimal import Decimal

import pytest

from tindahaniq.exceptions import ValidationError
from tindahaniq.models.analytics import StockUrgency
from tindahaniq.services.bi.formulas import (
    calculate_breakeven_volume_change_pct,
    calculate_cogs,
    calculate_daily_velocity,
    calculate_days_to_depletion,
    calculate_gross_margin_pct,
    calculate_gross_profit,
    calculate_gross_revenue,
    calculate_markup_pct,
    calculate_pct_change,
    calculate_suggested_restock_qty,
    classify_stock_urgency,
)


def test_revenue_cogs_profit_margin_vs_markup_exact_math() -> None:
    # Lucky Me! Pancit Canton: 8 packs sold @ ₱16.00, cost ₱12.25
    rev = calculate_gross_revenue(8, Decimal("16.00"))
    cogs = calculate_cogs(8, Decimal("12.25"))
    profit = calculate_gross_profit(rev, cogs)
    margin = calculate_gross_margin_pct(profit, rev)
    markup = calculate_markup_pct(rev, cogs)

    assert rev == Decimal("128.00")
    assert cogs == Decimal("98.00")
    assert profit == Decimal("30.00")
    # Margin = 30 / 128 = 23.4375% -> 23.44%
    assert margin == Decimal("23.44")
    # Markup = 30 / 98 = 30.6122...% -> 30.61%
    assert markup == Decimal("30.61")


def test_zero_denominator_guards_return_none() -> None:
    assert calculate_gross_margin_pct(Decimal("0.00"), Decimal("0.00")) is None
    assert calculate_markup_pct(Decimal("10.00"), Decimal("0.00")) is None
    assert calculate_pct_change(Decimal("500.00"), Decimal("0.00")) is None
    assert calculate_days_to_depletion(current_stock=10, units_sold=0, effective_days=7) is None


def test_pct_change_positive_and_negative_deltas() -> None:
    assert calculate_pct_change(Decimal("1124.00"), Decimal("1000.00")) == Decimal("12.40")
    assert calculate_pct_change(Decimal("750.00"), Decimal("1000.00")) == Decimal("-25.00")


def test_velocity_depletion_and_rational_ceiling_restock_math() -> None:
    # 20 units sold over 3 days = 6.6666... units/day -> display 6.67
    assert calculate_daily_velocity(20, 3) == Decimal("6.67")
    # Over a 3-day horizon (2 coverage + 1 lead), exact needed = 20 * 3 / 3 = 20
    # (NOT premature rounded 6.67 * 3 = 20.01 -> 21!)
    qty, fallback = calculate_suggested_restock_qty(
        current_stock=5,
        reorder_point=10,
        lead_time_days=1,
        target_coverage_days=2,
        units_sold_in_window=20,
        effective_window_days=3,
    )
    assert qty == 15
    assert fallback is False

    # Zero sales fallback when below reorder point
    fb_qty, fb_used = calculate_suggested_restock_qty(
        current_stock=3,
        reorder_point=12,
        lead_time_days=1,
        target_coverage_days=7,
        units_sold_in_window=0,
        effective_window_days=14,
    )
    assert fb_qty == 9
    assert fb_used is True

    assert calculate_days_to_depletion(0, 10, 5) == Decimal("0.00")
    assert calculate_days_to_depletion(9, 18, 4) == Decimal("2.00")


def test_stock_urgency_classification_tiers() -> None:
    assert (
        classify_stock_urgency(
            current_stock=0, reorder_point=10, lead_time_days=1, days_to_depletion=Decimal("0.00")
        )
        == StockUrgency.CRITICAL
    )
    assert (
        classify_stock_urgency(
            current_stock=4, reorder_point=24, lead_time_days=1, days_to_depletion=Decimal("0.89")
        )
        == StockUrgency.CRITICAL
    )
    assert (
        classify_stock_urgency(
            current_stock=10, reorder_point=24, lead_time_days=1, days_to_depletion=Decimal("2.50")
        )
        == StockUrgency.HIGH
    )
    assert (
        classify_stock_urgency(
            current_stock=18, reorder_point=20, lead_time_days=1, days_to_depletion=Decimal("8.00")
        )
        == StockUrgency.LOW
    )
    assert (
        classify_stock_urgency(
            current_stock=40, reorder_point=20, lead_time_days=1, days_to_depletion=Decimal("15.00")
        )
        == StockUrgency.HEALTHY
    )


def test_breakeven_volume_change_and_invalid_input_guards() -> None:
    # Cost ₱12, Current ₱16 (profit ₱4) -> Proposed ₱18 (profit ₱6) => (4/6 - 1)*100 = -33.33%
    assert calculate_breakeven_volume_change_pct(Decimal("4.00"), Decimal("6.00")) == Decimal(
        "-33.33"
    )
    assert calculate_breakeven_volume_change_pct(Decimal("4.00"), Decimal("0.00")) is None

    with pytest.raises(ValidationError):
        calculate_gross_revenue(-1, Decimal("10.00"))
    with pytest.raises(ValidationError):
        calculate_daily_velocity(5, 0)
