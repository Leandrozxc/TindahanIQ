"""Application service container wiring persistence, BI engines, and AI consultant."""

from __future__ import annotations

from dataclasses import dataclass

from tindahaniq.ai import AIConsultantService
from tindahaniq.config import PROJECT_ROOT, AppSettings
from tindahaniq.db import DatabaseManager
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


@dataclass(slots=True)
class AppContext:
    """Dependency container shared across UI views during a Streamlit request."""

    settings: AppSettings
    db: DatabaseManager
    csv_importer: CSVImportService
    inventory_service: InventoryService
    sales_service: SalesService
    consistency_service: ConsistencyService
    profitability: ProfitabilityAnalyzer
    sales_analytics: SalesAnalyticsService
    inventory_intel: InventoryIntelligenceService
    pricing_sim: PricingSimulatorService
    ai_consultant: AIConsultantService

    def has_active_products(self) -> bool:
        """Return True when the store catalog has at least one active product."""
        return len(self.inventory_service.list_inventory(active_only=True)) > 0

    def load_sample_store_data(self) -> tuple[int, int]:
        """Load the bundled sample sari-sari store inventory and sales CSVs."""
        inv_path = PROJECT_ROOT / "data" / "samples" / "sample_inventory.csv"
        sales_path = PROJECT_ROOT / "data" / "samples" / "sample_sales.csv"
        inv_res = self.csv_importer.import_inventory_csv(inv_path, allow_reimport=True)
        sales_res = self.csv_importer.import_sales_csv(sales_path, allow_reimport=True)
        return inv_res.rows_accepted, sales_res.rows_accepted


def build_app_context(settings: AppSettings) -> AppContext:
    """Instantiate and initialize database-backed services for the current request."""
    db = DatabaseManager(settings.resolved_database_path)
    db.initialize_schema()
    return AppContext(
        settings=settings,
        db=db,
        csv_importer=CSVImportService(db),
        inventory_service=InventoryService(db),
        sales_service=SalesService(db),
        consistency_service=ConsistencyService(db),
        profitability=ProfitabilityAnalyzer(db),
        sales_analytics=SalesAnalyticsService(db),
        inventory_intel=InventoryIntelligenceService(db),
        pricing_sim=PricingSimulatorService(db),
        ai_consultant=AIConsultantService(db, settings),
    )
