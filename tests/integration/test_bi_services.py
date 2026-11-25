"""Integration tests verifying all four Phase 4 Business Intelligence services."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from tindahaniq.config import PROJECT_ROOT
from tindahaniq.db import DatabaseManager
from tindahaniq.exceptions import ValidationError
from tindahaniq.models import StockUrgency
from tindahaniq.services import (
    CSVImportService,
    InventoryIntelligenceService,
    PricingSimulatorService,
    ProfitabilityAnalyzer,
    SalesAnalyticsService,
)


@pytest.fixture
def populated_store_db(tmp_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_path / "bi_engine.db")
    db.initialize_schema()
    importer = CSVImportService(db)
    importer.import_inventory_csv(PROJECT_ROOT / "data" / "samples" / "sample_inventory.csv")
    importer.import_sales_csv(PROJECT_ROOT / "data" / "samples" / "sample_sales.csv")
    return db


def test_profitability_analyzer_matches_exact_sample_store_totals(
    populated_store_db: DatabaseManager,
) -> None:
    analyzer = ProfitabilityAnalyzer(populated_store_db)
    report = analyzer.analyze_store_profitability(sort_by="gross_profit")

    # Hand-verified totals across all 12 transactions in sample_sales.csv:
    # COFF-001: 6 * 15 = 90.00, cogs 69.00, profit 21.00
    # NOOD-001: 18 * 16 = 288.00, cogs 220.50, profit 67.50
    # BEV-001: 41 * 20 = 820.00, cogs 574.00, profit 246.00
    # MILK-001: 5 * 15 = 75.00, cogs 56.25, profit 18.75
    # COFF-002: 5 * 15 = 75.00, cogs 57.50, profit 17.50
    # CAN-001: 3 * 38 = 114.00, cogs 94.50, profit 19.50
    # COND-001: 4 * 25 = 100.00, cogs 76.00, profit 24.00
    # HOME-001: 9 * 8 = 72.00, cogs 47.25, profit 24.75
    # CAN-002: 2 * 42 = 84.00, cogs 68.00, profit 16.00
    # CARE-001: 0 sold -> 0.00
    assert report.total_units_sold == 93
    assert report.gross_revenue == Decimal("1718.00")
    assert report.cogs == Decimal("1263.00")
    assert report.gross_profit == Decimal("455.00")
    assert report.gross_margin_pct == Decimal("26.48")  # 455 / 1718 * 100 = 26.48428...

    # Highest total profit item is Coca-Cola Mismo (₱246.00)
    top_profit = report.products[0]
    assert top_profit.sku == "BEV-001"
    assert top_profit.gross_profit == Decimal("246.00")
    assert top_profit.realized_margin_pct == Decimal("30.00")

    # Zero-sale item (CARE-001 Safeguard) has None realized_margin_pct but valid catalog margin
    by_sku = {p.sku: p for p in report.products}
    safeguard = by_sku["CARE-001"]
    assert safeguard.units_sold == 0
    assert safeguard.realized_margin_pct is None
    assert safeguard.catalog_margin_pct == Decimal("22.92")  # 5.50 / 24.00 * 100


def test_sales_analytics_top_slow_buckets_peak_hour_and_period_comparison(
    populated_store_db: DatabaseManager,
) -> None:
    analytics = SalesAnalyticsService(populated_store_db)
    report = analytics.analyze_sales(granularity="daily", top_n=3)

    assert report.effective_days == 4  # Nov 20..23 inclusive
    assert report.total_transactions == 12
    assert report.total_units_sold == 93
    assert len(report.buckets) == 4
    assert report.average_daily_revenue == Decimal("429.50")  # 1718 / 4
    assert report.peak_hour is not None

    # Best-seller by units: BEV-001 (41 bottles), followed by NOOD-001 (18 packs)
    assert [p.sku for p in report.top_selling[:2]] == ["BEV-001", "NOOD-001"]
    # Slowest mover is CARE-001 with 0 units sold
    assert report.slow_moving[0].sku == "CARE-001"
    assert report.slow_moving[0].units_sold == 0

    # Compare 2-day window (Nov 22-23) vs prior 2-day window (Nov 20-21)
    comp = analytics.compare_periods(
        window_days=2,
        current_end=datetime(2026, 11, 23, 23, 59, 59, tzinfo=UTC),
    )
    # Nov 20-21 revenue: (90+128+240+75) + (75+114+300) = 533 + 489 = 1022.00
    # Nov 22-23 revenue: (160+100+72) + (84+280) = 332 + 364 = 696.00
    assert comp.previous_revenue == Decimal("1022.00")
    assert comp.current_revenue == Decimal("696.00")
    assert comp.revenue_delta == Decimal("-326.00")
    assert comp.revenue_change_pct == Decimal("-31.90")


def test_inventory_intelligence_and_budget_restock_planner(
    populated_store_db: DatabaseManager,
) -> None:
    intel_svc = InventoryIntelligenceService(populated_store_db)
    report = intel_svc.analyze_inventory(lookback_days=14, target_coverage_days=7)

    # Sample sales span 4 days within the 14-day window -> effective_lookback_days == 4
    assert report.effective_lookback_days == 4
    assert report.critical_count >= 3

    by_sku = {r.sku: r for r in report.recommendations}
    # NOOD-001: 18 sold in 4 days (4.5/day), stock=4, lead=1, cover=7
    # -> ceil(18*8/4)=36 -> 36-4=32 packs!
    pancit = by_sku["NOOD-001"]
    assert pancit.urgency == StockUrgency.CRITICAL
    assert pancit.daily_velocity == Decimal("4.50")
    assert pancit.suggested_restock_qty == 32
    assert pancit.estimated_restock_cost == Decimal("392.00")  # 32 * 12.25

    # Test tight working-capital budget (e.g. ₱500.00)
    tight_plan = intel_svc.plan_restock_within_budget(Decimal("500.00"))
    assert tight_plan.budget_php == Decimal("500.00")
    assert tight_plan.total_allocated_cost <= Decimal("500.00")
    assert tight_plan.total_allocated_cost + tight_plan.remaining_budget_php == Decimal("500.00")
    assert len(tight_plan.funded_items) >= 1
    assert tight_plan.funded_items[0].urgency == StockUrgency.CRITICAL


def test_pricing_simulator_modes_breakeven_and_below_cost_warning(
    populated_store_db: DatabaseManager,
) -> None:
    inv_intel = InventoryIntelligenceService(populated_store_db)
    pancit_rec = next(
        r for r in inv_intel.analyze_inventory().recommendations if r.sku == "NOOD-001"
    )

    sim_svc = PricingSimulatorService(populated_store_db)
    # Proposal query: "What happens to my profit if I increase the price of this product by ₱2?"
    # Current price ₱16.00 -> ₱18.00, cost ₱12.25, historical baseline 18 packs
    sim = sim_svc.simulate_price_change(
        pancit_rec.product_id,
        price_delta_php=Decimal("2.00"),
    )
    assert sim.is_hypothetical is True
    assert sim.current_price == Decimal("16.00")
    assert sim.proposed_price == Decimal("18.00")
    assert sim.baseline_units == 18
    assert sim.current_unit_profit == Decimal("3.75")
    assert sim.proposed_unit_profit == Decimal("5.75")
    assert sim.baseline_gross_profit == Decimal("67.50")
    assert sim.simulated_gross_profit == Decimal("103.50")
    assert sim.gross_profit_delta == Decimal("36.00")
    assert sim.breakeven_volume_change_pct == Decimal("-34.78")  # (3.75 / 5.75 - 1) * 100
    assert sim.warnings == ()

    # Below-cost simulation triggers warning
    loss_sim = sim_svc.simulate_price_change(
        pancit_rec.product_id,
        new_selling_price=Decimal("10.00"),
    )
    assert len(loss_sim.warnings) == 1
    assert loss_sim.simulated_gross_profit == Decimal("-40.50")

    # Passing multiple pricing modes simultaneously is rejected
    with pytest.raises(ValidationError):
        sim_svc.simulate_price_change(
            pancit_rec.product_id,
            new_selling_price=Decimal("18.00"),
            price_delta_php=Decimal("2.00"),
        )


def test_weekly_monthly_buckets_single_product_queries_and_pct_price_sim(
    populated_store_db: DatabaseManager,
) -> None:
    prof_svc = ProfitabilityAnalyzer(populated_store_db)
    sales_svc = SalesAnalyticsService(populated_store_db)
    intel_svc = InventoryIntelligenceService(populated_store_db)
    sim_svc = PricingSimulatorService(populated_store_db)

    weekly = sales_svc.analyze_sales(granularity="weekly")
    monthly = sales_svc.analyze_sales(granularity="monthly")
    assert len(weekly.buckets) >= 1
    assert monthly.buckets[0].period_label == "2026-11"
    assert monthly.buckets[0].gross_revenue == Decimal("1718.00")

    margin_sorted = prof_svc.analyze_store_profitability(sort_by="gross_margin_pct")
    safeguard = next(p for p in margin_sorted.products if p.sku == "CARE-001")
    single_prof = prof_svc.get_product_profitability(safeguard.product_id)
    assert single_prof.sku == "CARE-001"

    single_restock = intel_svc.get_product_restock_recommendation(safeguard.product_id)
    assert single_restock.sku == "CARE-001"

    # Percentage-based simulation with volume sensitivity on zero-sale item + override
    pct_sim = sim_svc.simulate_price_change(
        safeguard.product_id,
        price_change_pct="+10%",
        expected_volume_change_pct="-10%",
        baseline_units_override=20,
    )
    assert pct_sim.proposed_price == Decimal("26.40")
    assert pct_sim.simulated_units == 18

    zero_hist_sim = sim_svc.simulate_price_change(
        safeguard.product_id,
        price_delta_php="₱1.00",
    )
    assert zero_hist_sim.baseline_units == 0
    assert zero_hist_sim.unit_profit_delta == Decimal("1.00")
