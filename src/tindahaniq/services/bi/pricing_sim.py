"""Pricing Simulator service for deterministic selling-price scenario modeling."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from tindahaniq.db.connection import DatabaseManager
from tindahaniq.db.repositories import ProductRepository, SalesRepository
from tindahaniq.exceptions import ValidationError
from tindahaniq.models.analytics import PriceSimulationResult
from tindahaniq.services.bi.formulas import (
    HUNDRED,
    ZERO,
    calculate_breakeven_volume_change_pct,
    calculate_cogs,
    calculate_gross_margin_pct,
    calculate_gross_profit,
    calculate_gross_revenue,
    calculate_markup_pct,
    calculate_pct_change,
    quantize_money,
    quantize_rate,
)
from tindahaniq.utils.validation import (
    CURRENCY_STRIP_RE,
    parse_money_decimal,
    parse_non_negative_int,
)


def _parse_signed_decimal(raw: object, *, field_name: str) -> Decimal:
    if raw is None or isinstance(raw, bool):
        raise ValidationError(
            f"Missing or boolean signed decimal for `{field_name}`",
            user_message=f"`{field_name}` must be a valid number.",
            details={"field": field_name},
        )
    if isinstance(raw, Decimal):
        val = raw
    elif isinstance(raw, int):
        val = Decimal(raw)
    elif isinstance(raw, float):
        if not math.isfinite(raw):
            raise ValidationError(
                f"Non-finite float for `{field_name}`",
                user_message=f"`{field_name}` must be a finite number.",
                details={"field": field_name},
            )
        val = Decimal(str(raw))
    elif isinstance(raw, str):
        cleaned = CURRENCY_STRIP_RE.sub("", raw.strip()).replace("%", "").replace(",", "").strip()
        if not cleaned:
            raise ValidationError(
                f"Blank string for `{field_name}`",
                user_message=f"`{field_name}` cannot be empty.",
                details={"field": field_name},
            )
        try:
            val = Decimal(cleaned)
        except InvalidOperation as exc:
            raise ValidationError(
                f"Invalid numeric string `{raw}` for `{field_name}`",
                user_message=f"`{field_name}` ('{raw}') must be a valid numeric value.",
                details={"field": field_name, "raw_value": raw},
            ) from exc
    else:
        raise ValidationError(
            f"Unsupported type {type(raw).__name__} for `{field_name}`",
            user_message=f"`{field_name}` must be a valid numeric value.",
            details={"field": field_name},
        )

    if not val.is_finite():
        raise ValidationError(
            f"Non-finite Decimal for `{field_name}`",
            user_message=f"`{field_name}` must be a finite numeric value.",
            details={"field": field_name},
        )
    return val


class PricingSimulatorService:
    """Simulate selling-price adjustments and compare deterministic profit impacts."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db
        self._products = ProductRepository(db)
        self._sales = SalesRepository(db)

    def simulate_price_change(
        self,
        product_id: int,
        *,
        new_selling_price: Decimal | str | int | float | None = None,
        price_delta_php: Decimal | str | int | float | None = None,
        price_change_pct: Decimal | str | int | float | None = None,
        expected_volume_change_pct: Decimal | str | int | float = Decimal("0.00"),
        baseline_units_override: int | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> PriceSimulationResult:
        """Simulate a proposed price change using historical or specified unit volume."""
        checked_id = parse_non_negative_int(product_id, field_name="product_id", min_value=1)

        provided_modes = sum(
            opt is not None for opt in (new_selling_price, price_delta_php, price_change_pct)
        )
        if provided_modes != 1:
            raise ValidationError(
                f"Expected exactly 1 pricing mode, received {provided_modes}",
                user_message=(
                    "Specify exactly one of `new_selling_price`, `price_delta_php`, "
                    "or `price_change_pct`."
                ),
                details={"field": "pricing_mode"},
            )

        vol_pct = quantize_rate(
            _parse_signed_decimal(
                expected_volume_change_pct, field_name="expected_volume_change_pct"
            )
        )
        if vol_pct < Decimal("-100.00"):
            raise ValidationError(
                f"Volume change {vol_pct}% < -100%",
                user_message="Expected volume change cannot be less than -100%.",
                details={"field": "expected_volume_change_pct"},
            )

        s_utc = (
            (start_at.replace(tzinfo=UTC) if start_at.tzinfo is None else start_at.astimezone(UTC))
            if start_at is not None
            else None
        )
        e_utc = (
            (end_at.replace(tzinfo=UTC) if end_at.tzinfo is None else end_at.astimezone(UTC))
            if end_at is not None
            else None
        )
        if s_utc is not None and e_utc is not None and s_utc > e_utc:
            raise ValidationError(
                "Invalid pricing simulator date range",
                user_message="Start date must be earlier than or equal to the end date.",
                details={"field": "date_range"},
            )

        with self._db.read_connection() as conn:
            record = self._products.get_by_id(checked_id, conn=conn)
            if record is None:
                raise ValidationError(
                    f"Product id={checked_id} not found for pricing simulation",
                    user_message=f"Product #{checked_id} could not be found.",
                    details={"product_id": checked_id},
                )
            sales = (
                []
                if baseline_units_override is not None
                else self._sales.list_sales(
                    product_id=checked_id, start_at=s_utc, end_at=e_utc, conn=conn
                )
            )

        prod = record.product
        current_price = prod.selling_price
        unit_cost = prod.unit_cost

        if new_selling_price is not None:
            proposed_price = parse_money_decimal(
                new_selling_price, field_name="new_selling_price", allow_zero=False
            )
        elif price_delta_php is not None:
            delta_val = _parse_signed_decimal(price_delta_php, field_name="price_delta_php")
            proposed_price = quantize_money(current_price + delta_val)
        else:
            pct_val = _parse_signed_decimal(price_change_pct, field_name="price_change_pct")
            proposed_price = quantize_money(current_price * (Decimal("1") + (pct_val / HUNDRED)))

        if proposed_price <= ZERO:
            raise ValidationError(
                f"Proposed selling price {proposed_price} <= 0",
                user_message="Proposed selling price must be greater than ₱0.00.",
                details={"field": "proposed_price"},
            )

        if baseline_units_override is not None:
            baseline_units = parse_non_negative_int(
                baseline_units_override, field_name="baseline_units_override", min_value=0
            )
        else:
            baseline_units = sum(tx.quantity_sold for tx in sales)

        simulated_units = int(
            (Decimal(baseline_units) * (Decimal("1") + (vol_pct / HUNDRED))).to_integral_value(
                rounding=ROUND_HALF_UP
            )
        )

        price_delta = quantize_money(proposed_price - current_price)
        pct_change = calculate_pct_change(proposed_price, current_price) or ZERO

        curr_unit_profit = quantize_money(current_price - unit_cost)
        prop_unit_profit = quantize_money(proposed_price - unit_cost)
        unit_profit_delta = quantize_money(prop_unit_profit - curr_unit_profit)

        curr_margin = calculate_gross_margin_pct(curr_unit_profit, current_price)
        prop_margin = calculate_gross_margin_pct(prop_unit_profit, proposed_price)
        margin_delta = (
            quantize_rate(prop_margin - curr_margin)
            if (curr_margin is not None and prop_margin is not None)
            else None
        )

        curr_markup = calculate_markup_pct(current_price, unit_cost)
        prop_markup = calculate_markup_pct(proposed_price, unit_cost)

        base_rev = calculate_gross_revenue(baseline_units, current_price)
        base_cogs = calculate_cogs(baseline_units, unit_cost)
        base_profit = calculate_gross_profit(base_rev, base_cogs)

        sim_rev = calculate_gross_revenue(simulated_units, proposed_price)
        sim_cogs = calculate_cogs(simulated_units, unit_cost)
        sim_profit = calculate_gross_profit(sim_rev, sim_cogs)

        rev_delta = quantize_money(sim_rev - base_rev)
        profit_delta = quantize_money(sim_profit - base_profit)
        breakeven_vol = calculate_breakeven_volume_change_pct(curr_unit_profit, prop_unit_profit)

        warnings: list[str] = []
        if proposed_price < unit_cost:
            warnings.append(
                f"Proposed price (₱{proposed_price:.2f}) is below supplier unit cost "
                f"(₱{unit_cost:.2f}), resulting in a loss of "
                f"₱{abs(prop_unit_profit):.2f} per {prod.unit}."
            )
        elif proposed_price == unit_cost:
            warnings.append(
                f"Proposed price (₱{proposed_price:.2f}) equals supplier unit cost; "
                "gross profit per unit will be ₱0.00."
            )

        assumptions: list[str] = [
            "Simulation figures are hypothetical estimates and do not guarantee "
            "future customer demand.",
            f"Supplier unit cost is held constant at ₱{unit_cost:.2f} per {prod.unit}.",
        ]
        if baseline_units_override is not None:
            assumptions.append(
                f"Baseline volume uses user-specified quantity of {baseline_units} {prod.unit}(s)."
            )
        elif baseline_units == 0:
            assumptions.append(
                "No historical sales were recorded for this product in the selected window; "
                "period totals reflect 0 baseline units while per-unit margin changes remain exact."
            )
        else:
            assumptions.append(
                f"Baseline volume uses {baseline_units} historical {prod.unit}(s) sold, "
                f"adjusted by {vol_pct:+.2f}% expected volume change "
                f"({simulated_units} {prod.unit}(s))."
            )

        return PriceSimulationResult(
            is_hypothetical=True,
            product_id=prod.id,
            sku=prod.sku,
            product_name=prod.name,
            unit=prod.unit,
            unit_cost=unit_cost,
            current_price=current_price,
            proposed_price=proposed_price,
            price_delta_php=price_delta,
            price_change_pct=pct_change,
            current_unit_profit=curr_unit_profit,
            proposed_unit_profit=prop_unit_profit,
            unit_profit_delta=unit_profit_delta,
            current_margin_pct=curr_margin,
            proposed_margin_pct=prop_margin,
            margin_pct_point_delta=margin_delta,
            current_markup_pct=curr_markup,
            proposed_markup_pct=prop_markup,
            baseline_units=baseline_units,
            simulated_units=simulated_units,
            expected_volume_change_pct=vol_pct,
            baseline_gross_revenue=base_rev,
            simulated_gross_revenue=sim_rev,
            revenue_delta=rev_delta,
            baseline_gross_profit=base_profit,
            simulated_gross_profit=sim_profit,
            gross_profit_delta=profit_delta,
            breakeven_volume_change_pct=breakeven_vol,
            warnings=tuple(warnings),
            assumptions=tuple(assumptions),
        )
