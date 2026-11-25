"""Typed Pydantic output models for the Phase 4 Business Intelligence Engine."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

PeriodGranularity = Literal["daily", "weekly", "monthly"]
ProfitSortBy = Literal["gross_profit", "gross_margin_pct", "gross_revenue", "unit_profit"]
SalesSortBy = Literal["units_sold", "gross_revenue"]


class StockUrgency(StrEnum):
    """Deterministic restock urgency tiers ordered from most to least urgent."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    LOW = "LOW"
    HEALTHY = "HEALTHY"


class ProductProfitability(BaseModel):
    """Realized and catalog profitability metrics for a single product."""

    model_config = ConfigDict(frozen=True)

    product_id: int
    sku: str
    product_name: str
    category: str
    unit: str
    is_active: bool
    current_unit_cost: Decimal
    current_selling_price: Decimal
    current_unit_profit: Decimal
    catalog_margin_pct: Decimal | None
    catalog_markup_pct: Decimal | None
    units_sold: int
    gross_revenue: Decimal
    cogs: Decimal
    gross_profit: Decimal
    realized_margin_pct: Decimal | None
    realized_markup_pct: Decimal | None


class CategoryProfitability(BaseModel):
    """Aggregated realized profitability across a product category."""

    model_config = ConfigDict(frozen=True)

    category: str
    product_count: int
    units_sold: int
    gross_revenue: Decimal
    cogs: Decimal
    gross_profit: Decimal
    gross_margin_pct: Decimal | None


class StoreProfitabilityReport(BaseModel):
    """Store-wide profitability totals and ranked product/category breakdowns."""

    model_config = ConfigDict(frozen=True)

    start_at: datetime | None
    end_at: datetime | None
    total_units_sold: int
    gross_revenue: Decimal
    cogs: Decimal
    gross_profit: Decimal
    gross_margin_pct: Decimal | None
    markup_pct: Decimal | None
    products: tuple[ProductProfitability, ...]
    categories: tuple[CategoryProfitability, ...]


class ProductSalesPerformance(BaseModel):
    """Sales velocity and volume metrics for a catalog product."""

    model_config = ConfigDict(frozen=True)

    product_id: int
    sku: str
    product_name: str
    category: str
    unit: str
    current_stock: int
    transaction_count: int
    units_sold: int
    gross_revenue: Decimal
    gross_profit: Decimal
    daily_velocity: Decimal
    last_sold_at: datetime | None
    days_since_last_sale: int | None


class SalesPeriodBucket(BaseModel):
    """Aggregated sales metrics for a single day, ISO week, or calendar month."""

    model_config = ConfigDict(frozen=True)

    period_label: str
    period_start: date
    period_end: date
    transaction_count: int
    units_sold: int
    gross_revenue: Decimal
    cogs: Decimal
    gross_profit: Decimal


class HourlySalesBucket(BaseModel):
    """Aggregated sales activity within an hour of the day (0..23)."""

    model_config = ConfigDict(frozen=True)

    hour: int
    label: str
    transaction_count: int
    units_sold: int
    gross_revenue: Decimal


class PeriodComparison(BaseModel):
    """Deterministic comparison between a current window and an equal-length prior window."""

    model_config = ConfigDict(frozen=True)

    window_days: int
    current_start: datetime
    current_end: datetime
    previous_start: datetime
    previous_end: datetime
    current_revenue: Decimal
    previous_revenue: Decimal
    revenue_delta: Decimal
    revenue_change_pct: Decimal | None
    current_gross_profit: Decimal
    previous_gross_profit: Decimal
    gross_profit_delta: Decimal
    gross_profit_change_pct: Decimal | None
    current_units_sold: int
    previous_units_sold: int
    units_delta: int
    current_transactions: int
    previous_transactions: int


class SalesAnalyticsReport(BaseModel):
    """Comprehensive sales analytics summary over a target window."""

    model_config = ConfigDict(frozen=True)

    granularity: PeriodGranularity
    start_at: datetime | None
    end_at: datetime | None
    effective_days: int
    total_transactions: int
    total_units_sold: int
    total_gross_revenue: Decimal
    total_gross_profit: Decimal
    average_daily_revenue: Decimal
    peak_hour: HourlySalesBucket | None
    buckets: tuple[SalesPeriodBucket, ...]
    top_selling: tuple[ProductSalesPerformance, ...]
    slow_moving: tuple[ProductSalesPerformance, ...]


class RestockRecommendation(BaseModel):
    """Per-product depletion forecast and suggested restock order quantity."""

    model_config = ConfigDict(frozen=True)

    product_id: int
    sku: str
    product_name: str
    category: str
    unit: str
    urgency: StockUrgency
    current_stock: int
    reorder_point: int
    lead_time_days: int
    unit_cost: Decimal
    selling_price: Decimal
    unit_profit: Decimal
    units_sold_in_window: int
    daily_velocity: Decimal
    estimated_days_to_depletion: Decimal | None
    suggested_restock_qty: int
    estimated_restock_cost: Decimal
    used_reorder_point_fallback: bool


class InventoryIntelligenceReport(BaseModel):
    """Store-wide inventory health, stockout alerts, and restocking recommendations."""

    model_config = ConfigDict(frozen=True)

    as_of: datetime
    requested_lookback_days: int
    effective_lookback_days: int
    target_coverage_days: int
    total_active_products: int
    critical_count: int
    high_count: int
    low_count: int
    healthy_count: int
    total_suggested_restock_cost: Decimal
    recommendations: tuple[RestockRecommendation, ...]
    assumptions: tuple[str, ...]


class BudgetAllocationItem(BaseModel):
    """Single product allocation within a budget-constrained restock plan."""

    model_config = ConfigDict(frozen=True)

    product_id: int
    sku: str
    product_name: str
    unit: str
    urgency: StockUrgency
    current_stock: int
    full_suggested_qty: int
    funded_qty: int
    unfunded_qty: int
    unit_cost: Decimal
    allocated_cost: Decimal
    expected_gross_profit: Decimal


class BudgetRestockPlan(BaseModel):
    """Prioritized restocking allocation constrained by available working capital."""

    model_config = ConfigDict(frozen=True)

    budget_php: Decimal
    total_allocated_cost: Decimal
    remaining_budget_php: Decimal
    funded_items: tuple[BudgetAllocationItem, ...]
    deferred_items: tuple[BudgetAllocationItem, ...]
    total_expected_gross_profit: Decimal
    assumptions: tuple[str, ...]


class PriceSimulationResult(BaseModel):
    """Deterministic comparison between current and simulated product pricing."""

    model_config = ConfigDict(frozen=True)

    is_hypothetical: bool = True
    product_id: int
    sku: str
    product_name: str
    unit: str
    unit_cost: Decimal
    current_price: Decimal
    proposed_price: Decimal
    price_delta_php: Decimal
    price_change_pct: Decimal
    current_unit_profit: Decimal
    proposed_unit_profit: Decimal
    unit_profit_delta: Decimal
    current_margin_pct: Decimal | None
    proposed_margin_pct: Decimal | None
    margin_pct_point_delta: Decimal | None
    current_markup_pct: Decimal | None
    proposed_markup_pct: Decimal | None
    baseline_units: int
    simulated_units: int
    expected_volume_change_pct: Decimal
    baseline_gross_revenue: Decimal
    simulated_gross_revenue: Decimal
    revenue_delta: Decimal
    baseline_gross_profit: Decimal
    simulated_gross_profit: Decimal
    gross_profit_delta: Decimal
    breakeven_volume_change_pct: Decimal | None
    warnings: tuple[str, ...]
    assumptions: tuple[str, ...]
