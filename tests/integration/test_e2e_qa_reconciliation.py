"""Phase 7 End-to-End QA: reconciliation, security, adversarial CSV, AI edge cases & perf."""

from __future__ import annotations

import time
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from tindahaniq.ai import AIConsultantService, BusinessToolRegistry
from tindahaniq.config import PROJECT_ROOT, load_settings
from tindahaniq.db import DatabaseManager
from tindahaniq.models import (
    AdjustmentReason,
    ChatMessage,
    ProductCreate,
    ProductUpdate,
    ProviderTurnResult,
    SaleItemInput,
    StockAdjustmentCreate,
    ToolCallRequest,
    ToolResultMessage,
    ToolSpec,
)
from tindahaniq.services import (
    ConsistencyService,
    CSVImportService,
    InventoryIntelligenceService,
    InventoryService,
    PricingSimulatorService,
    ProfitabilityAnalyzer,
    SalesAnalyticsService,
    SalesService,
)
from tindahaniq.ui.context import build_app_context
from tindahaniq.ui.theme import urgency_badge_html
from tindahaniq.utils import escape_csv_formula


def test_cross_module_mathematical_conservation_and_full_lifecycle(tmp_path: Path) -> None:
    """Verify revenue, COGS, profit, and stock ledger reconcile across every module."""
    db = DatabaseManager(tmp_path / "e2e_reconciliation.db")
    db.initialize_schema()

    importer = CSVImportService(db)
    inv_svc = InventoryService(db)
    sales_svc = SalesService(db)
    prof_svc = ProfitabilityAnalyzer(db)
    analytics_svc = SalesAnalyticsService(db)
    consistency_svc = ConsistencyService(db)

    importer.import_inventory_csv(PROJECT_ROOT / "data" / "samples" / "sample_inventory.csv")
    importer.import_sales_csv(PROJECT_ROOT / "data" / "samples" / "sample_sales.csv")

    # Execute realistic store mutations: add product, restock, spoilage, price update, basket sale
    eggs = inv_svc.create_product(
        ProductCreate(
            sku="EGG-100",
            name="100% Farm Fresh Egg",
            category="Poultry & Eggs",
            unit="pc",
            unit_cost=Decimal("7.25"),
            selling_price=Decimal("10.00"),
            current_stock=30,
            reorder_point=12,
        )
    )
    inv_svc.restock_product(eggs.product.id, 10, notes="Morning tray delivery")
    inv_svc.adjust_stock(
        StockAdjustmentCreate(
            product_id=eggs.product.id,
            quantity_delta=-2,
            reason=AdjustmentReason.SPOILAGE,
            notes="Cracked eggs",
        )
    )
    sales_svc.record_sales_batch(
        [
            SaleItemInput(
                product_id=eggs.product.id,
                quantity_sold=6,
                sold_at=datetime(2026, 11, 23, 18, 0, tzinfo=UTC),
            ),
        ]
    )
    inv_svc.update_product(eggs.product.id, ProductUpdate(selling_price=Decimal("11.00")))

    # 1. Ledger & relational consistency must be 100% clean
    consistency = consistency_svc.verify_data_consistency()
    assert consistency.is_consistent is True
    assert consistency.error_count == 0

    # 2. Cross-module conservation: Store totals == Product sums == Category sums == Bucket sums
    prof = prof_svc.analyze_store_profitability()
    daily = analytics_svc.analyze_sales(granularity="daily")
    weekly = analytics_svc.analyze_sales(granularity="weekly")
    monthly = analytics_svc.analyze_sales(granularity="monthly")

    sum_prod_rev = sum((p.gross_revenue for p in prof.products), Decimal("0.00"))
    sum_cat_rev = sum((c.gross_revenue for c in prof.categories), Decimal("0.00"))
    sum_daily_rev = sum((b.gross_revenue for b in daily.buckets), Decimal("0.00"))
    sum_weekly_rev = sum((b.gross_revenue for b in weekly.buckets), Decimal("0.00"))
    sum_monthly_rev = sum((b.gross_revenue for b in monthly.buckets), Decimal("0.00"))

    assert (
        prof.gross_revenue
        == sum_prod_rev
        == sum_cat_rev
        == daily.total_gross_revenue
        == sum_daily_rev
        == sum_weekly_rev
        == sum_monthly_rev
    )

    sum_prod_profit = sum((p.gross_profit for p in prof.products), Decimal("0.00"))
    sum_cat_profit = sum((c.gross_profit for c in prof.categories), Decimal("0.00"))
    sum_daily_profit = sum((b.gross_profit for b in daily.buckets), Decimal("0.00"))
    assert (
        prof.gross_profit
        == sum_prod_profit
        == sum_cat_profit
        == daily.total_gross_profit
        == sum_daily_profit
    )


def test_security_defenses_like_wildcards_sql_injection_and_csv_formula_escaping(
    isolated_env: Path,
    tmp_path: Path,
) -> None:
    """Verify DEFECT-01..04 fixes: CSV escaping, LIKE wildcards, AI ints, store sync."""
    # DEFECT-01: CSV formula injection escaping preserves negative currency while escaping formulas
    assert escape_csv_formula("=CMD|' /C calc'!A0") == "'=CMD|' /C calc'!A0"
    assert escape_csv_formula("+SUM(A1:A5)") == "'+SUM(A1:A5)"
    assert escape_csv_formula("@IMPORTXML(A1,A2)") == "'@IMPORTXML(A1,A2)"
    assert escape_csv_formula("-1+1") == "'-1+1"
    assert escape_csv_formula("-₱40.50") == "-₱40.50"
    assert escape_csv_formula("Lucky Me! Pancit Canton") == "Lucky Me! Pancit Canton"

    db = DatabaseManager(tmp_path / "security_qa.db")
    db.initialize_schema()
    inv = InventoryService(db)
    inv.create_product(
        ProductCreate(
            sku="PCT-100",
            name="100% Pure Calamansi Juice",
            category="Beverages",
            unit_cost=Decimal("15.00"),
            selling_price=Decimal("22.00"),
            current_stock=10,
        )
    )
    inv.create_product(
        ProductCreate(
            sku="WATER-01",
            name="Mineral Water 500ml",
            category="Beverages",
            unit_cost=Decimal("8.00"),
            selling_price=Decimal("15.00"),
            current_stock=20,
        )
    )

    # DEFECT-02: Searching literal '%' only matches "100% Pure Calamansi Juice", NOT all rows!
    pct_matches = inv.list_inventory(query="100%")
    assert [m.product.sku for m in pct_matches] == ["PCT-100"]
    only_pct_char = inv.list_inventory(query="%")
    assert [m.product.sku for m in only_pct_char] == ["PCT-100"]

    # Parameterized SQL safety against SQL injection strings
    sqli_matches = inv.list_inventory(query="' OR 1=1 --")
    assert sqli_matches == []

    # DEFECT-03: Malformed non-integer tool argument returns structured validation error, not crash
    registry = BusinessToolRegistry(db)
    bad_tool_res = registry.execute(
        ToolCallRequest(
            call_id="bad_int",
            name="get_store_overview",
            arguments={"window_days": "not_a_number"},
        )
    )
    assert bad_tool_res.payload["status"] == "error"
    assert "window_days" in bad_tool_res.payload["error"]

    # DEFECT-04: Custom store_name propagates into AIConsultantService live snapshot
    settings = load_settings(env_file=None)
    ctx = build_app_context(settings, store_name="Aling Maria Sari-Sari Store")
    assert ctx.ai_consultant._tools.get_store_snapshot()["store_name"] == (
        "Aling Maria Sari-Sari Store"
    )
    assert "<span" in urgency_badge_html(
        InventoryIntelligenceService(db).analyze_inventory().recommendations[0].urgency
    )


def test_ai_consultant_max_tool_rounds_synthesis_fallback(
    isolated_env: Path,
    tmp_path: Path,
) -> None:
    """Verify AIConsultantService synthesizes cleanly if the LLM hits max_tool_rounds."""
    db = DatabaseManager(tmp_path / "max_rounds.db")
    db.initialize_schema()
    settings = load_settings(env_file=None)

    class _LoopingProvider:
        def __init__(self) -> None:
            self.calls = 0

        def generate_turn(
            self,
            *,
            conversation: Sequence[ChatMessage],
            current_turn_steps: Sequence[tuple[ProviderTurnResult, Sequence[ToolResultMessage]]],
            system_instruction: str,
            tools: Sequence[ToolSpec],
        ) -> ProviderTurnResult:
            self.calls += 1
            if tools:
                return ProviderTurnResult(
                    tool_calls=(
                        ToolCallRequest(call_id=f"loop_{self.calls}", name="get_store_overview"),
                    )
                )
            return ProviderTurnResult(text="Synthesized final answer after tool ceiling.")

    loop_provider = _LoopingProvider()
    svc = AIConsultantService(db, settings, provider=loop_provider, max_tool_rounds=2)
    res = svc.ask("Give me an overview")
    assert loop_provider.calls == 3  # 2 tool rounds + 1 tool-free synthesis turn
    assert res.answer == "Synthesized final answer after tool ceiling."


def test_performance_benchmark_500_products_and_5000_sales(tmp_path: Path) -> None:
    """Verify CSV ingestion and all 4 BI engines complete well under 2.5s on 5,000 sales."""
    db = DatabaseManager(tmp_path / "perf_benchmark.db")
    db.initialize_schema()
    importer = CSVImportService(db)

    inv_lines = [
        "sku,product_name,category,unit,unit_cost,selling_price,current_stock,reorder_point"
    ]
    for i in range(1, 501):
        cat = f"Category-{(i % 8) + 1}"
        cost = 10 + (i % 20)
        price = 15 + (i % 25)
        inv_lines.append(
            f"SKU-{i:04d},Retail Item {i},{cat},pcs,{cost:.2f},{price:.2f},{i % 40},15"
        )
    inv_csv = "\n".join(inv_lines)

    base_dt = datetime(2026, 11, 1, 8, 0, tzinfo=UTC)
    sales_lines = ["transaction_id,sold_at,sku,quantity_sold"]
    for j in range(1, 5001):
        sku_idx = ((j * 7) % 500) + 1
        ts = base_dt + timedelta(minutes=j * 5)
        sales_lines.append(f"TX-{j:05d},{ts:%Y-%m-%d %H:%M:%S},SKU-{sku_idx:04d},{(j % 4) + 1}")
    sales_csv = "\n".join(sales_lines)

    t0 = time.perf_counter()
    inv_res = importer.import_inventory_csv(inv_csv, filename="perf_inv.csv")
    sales_res = importer.import_sales_csv(sales_csv, filename="perf_sales.csv")
    import_elapsed = time.perf_counter() - t0

    assert inv_res.rows_created == 500
    assert sales_res.rows_created == 5000

    t1 = time.perf_counter()
    prof = ProfitabilityAnalyzer(db).analyze_store_profitability()
    sales_rep = SalesAnalyticsService(db).analyze_sales(granularity="daily", top_n=10)
    intel = InventoryIntelligenceService(db).plan_restock_within_budget(Decimal("10000.00"))
    sim = PricingSimulatorService(db).simulate_price_change(
        prof.products[0].product_id, price_delta_php=Decimal("2.00")
    )
    bi_elapsed = time.perf_counter() - t1

    assert prof.total_units_sold > 10000
    assert len(sales_rep.buckets) >= 15
    assert intel.total_allocated_cost <= Decimal("10000.00")
    assert sim.is_hypothetical is True
    # 4 BI engines combined must finish in under 2.5 seconds (typically < 0.25s)
    assert bi_elapsed < 2.5
    assert import_elapsed < 10.0
