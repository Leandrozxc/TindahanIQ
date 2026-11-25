"""Pure deterministic Decimal formulas for TindahanIQ's Business Intelligence Engine.

Every authoritative financial, velocity, restock, and pricing calculation in
TindahanIQ delegates here. Functions perform zero database or network I/O.
"""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

from tindahaniq.exceptions import ValidationError
from tindahaniq.models.analytics import StockUrgency

TWO_PLACES = Decimal("0.01")
ZERO = Decimal("0.00")
HUNDRED = Decimal("100")


def quantize_money(value: Decimal) -> Decimal:
    """Round a Decimal peso figure to 2 decimal places using ROUND_HALF_UP."""
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def quantize_rate(value: Decimal) -> Decimal:
    """Round a percentage or daily rate to 2 decimal places using ROUND_HALF_UP."""
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def calculate_gross_revenue(quantity_sold: int, unit_price: Decimal) -> Decimal:
    """Gross Revenue = Quantity Sold * Unit Selling Price."""
    if quantity_sold < 0:
        raise ValidationError(
            f"Negative quantity_sold={quantity_sold}",
            user_message="Quantity sold cannot be negative.",
            details={"field": "quantity_sold"},
        )
    return quantize_money(Decimal(quantity_sold) * unit_price)


def calculate_cogs(quantity_sold: int, unit_cost: Decimal) -> Decimal:
    """Cost of Goods Sold (COGS) = Quantity Sold * Unit Cost."""
    if quantity_sold < 0:
        raise ValidationError(
            f"Negative quantity_sold={quantity_sold}",
            user_message="Quantity sold cannot be negative.",
            details={"field": "quantity_sold"},
        )
    return quantize_money(Decimal(quantity_sold) * unit_cost)


def calculate_gross_profit(gross_revenue: Decimal, cogs: Decimal) -> Decimal:
    """Gross Profit = Gross Revenue - COGS."""
    return quantize_money(gross_revenue - cogs)


def calculate_gross_margin_pct(
    gross_profit: Decimal,
    gross_revenue: Decimal,
) -> Decimal | None:
    """Gross Profit Margin (%) = (Gross Profit / Gross Revenue) * 100.

    Returns `None` when `gross_revenue <= 0` to prevent division by zero.
    """
    if gross_revenue <= ZERO:
        return None
    return quantize_rate((gross_profit / gross_revenue) * HUNDRED)


def calculate_markup_pct(
    revenue_or_price: Decimal,
    cost: Decimal,
) -> Decimal | None:
    """Markup (%) = ((Selling Price - Unit Cost) / Unit Cost) * 100.

    Returns `None` when `cost <= 0` to prevent division by zero.
    """
    if cost <= ZERO:
        return None
    return quantize_rate(((revenue_or_price - cost) / cost) * HUNDRED)


def calculate_pct_change(
    current_value: Decimal,
    previous_value: Decimal,
) -> Decimal | None:
    """Percentage Change (%) = ((Current - Previous) / |Previous|) * 100.

    Returns `None` when `previous_value == 0`.
    """
    if previous_value == ZERO:
        return None
    return quantize_rate(((current_value - previous_value) / abs(previous_value)) * HUNDRED)


def calculate_daily_velocity(units_sold: int, effective_days: int) -> Decimal:
    """Daily Sales Velocity = Units Sold / Effective Window Days (rounded to 0.01)."""
    if effective_days < 1:
        raise ValidationError(
            f"Invalid effective_days={effective_days}",
            user_message="Lookback window must be at least 1 day.",
            details={"field": "effective_days"},
        )
    if units_sold < 0:
        raise ValidationError(
            f"Negative units_sold={units_sold}",
            user_message="Units sold cannot be negative.",
            details={"field": "units_sold"},
        )
    return quantize_rate(Decimal(units_sold) / Decimal(effective_days))


def calculate_days_to_depletion(
    current_stock: int,
    units_sold: int,
    effective_days: int,
) -> Decimal | None:
    """Estimated Days to Depletion = Current Stock / (Units Sold / Effective Days).

    Uses full-precision intermediate division prior to 2-decimal quantization.
    Returns `None` when `units_sold <= 0` (no observed consumption).
    """
    if effective_days < 1:
        raise ValidationError(
            f"Invalid effective_days={effective_days}",
            user_message="Lookback window must be at least 1 day.",
            details={"field": "effective_days"},
        )
    if units_sold <= 0:
        return None
    if current_stock <= 0:
        return ZERO
    exact_days = (Decimal(current_stock) * Decimal(effective_days)) / Decimal(units_sold)
    return quantize_rate(exact_days)


def calculate_suggested_restock_qty(
    *,
    current_stock: int,
    reorder_point: int,
    lead_time_days: int,
    target_coverage_days: int,
    units_sold_in_window: int,
    effective_window_days: int,
) -> tuple[int, bool]:
    """Compute whole-unit suggested restock quantity and whether fallback was used.

    When `units_sold_in_window > 0`:
        Target Stock = max(
            reorder_point,
            ceil((units_sold * (target_coverage_days + lead_time_days)) / effective_window_days)
        )
        Suggested Qty = max(0, Target Stock - Current Stock)

    When `units_sold_in_window == 0`:
        Falls back to `max(0, reorder_point - current_stock)` when below reorder point.
    """
    if effective_window_days < 1 or target_coverage_days < 1 or lead_time_days < 1:
        raise ValidationError(
            "Restock day parameters must be >= 1",
            user_message="Coverage, lead time, and lookback days must each be at least 1.",
            details={"field": "days"},
        )

    if units_sold_in_window > 0:
        horizon_days = target_coverage_days + lead_time_days
        exact_needed = (Decimal(units_sold_in_window) * Decimal(horizon_days)) / Decimal(
            effective_window_days
        )
        velocity_target = int(exact_needed.to_integral_value(rounding=ROUND_CEILING))
        target_stock = max(reorder_point, velocity_target)
        return max(0, target_stock - current_stock), False

    if current_stock < reorder_point:
        return reorder_point - current_stock, True
    return 0, False


def classify_stock_urgency(
    *,
    current_stock: int,
    reorder_point: int,
    lead_time_days: int,
    days_to_depletion: Decimal | None,
) -> StockUrgency:
    """Deterministically classify product stock urgency into CRITICAL, HIGH, LOW, or HEALTHY."""
    if current_stock <= 0:
        return StockUrgency.CRITICAL
    if days_to_depletion is not None and days_to_depletion <= Decimal(lead_time_days):
        return StockUrgency.CRITICAL
    if reorder_point > 0 and current_stock <= max(1, reorder_point // 4):
        return StockUrgency.CRITICAL

    if days_to_depletion is not None and days_to_depletion <= Decimal(lead_time_days + 2):
        return StockUrgency.HIGH
    if reorder_point > 0 and current_stock <= max(1, reorder_point // 2):
        return StockUrgency.HIGH

    if current_stock <= reorder_point:
        return StockUrgency.LOW
    if days_to_depletion is not None and days_to_depletion <= Decimal(lead_time_days + 5):
        return StockUrgency.LOW

    return StockUrgency.HEALTHY


def calculate_breakeven_volume_change_pct(
    current_unit_profit: Decimal,
    proposed_unit_profit: Decimal,
) -> Decimal | None:
    """Breakeven Volume Change (%) = ((Current Unit Profit / Proposed Unit Profit) - 1) * 100.

    Represents the percentage change in unit sales volume at which total gross
    profit under the proposed price equals current gross profit. Returns `None`
    when either unit profit is `<= 0`.
    """
    if current_unit_profit <= ZERO or proposed_unit_profit <= ZERO:
        return None
    ratio_delta = (current_unit_profit / proposed_unit_profit) - Decimal("1")
    return quantize_rate(ratio_delta * HUNDRED)
