"""Domain and DTO schemas for TindahanIQ."""

from tindahaniq.models.common import AdjustmentReason, ExistingProductPolicy, ImportType
from tindahaniq.models.import_result import (
    CSVImportResult,
    ImportBatch,
    ImportRowError,
    ImportWarning,
)
from tindahaniq.models.product import (
    ConsistencyIssue,
    ConsistencySeverity,
    DataConsistencyReport,
    InventoryRecord,
    Product,
    ProductCreate,
    ProductUpdate,
    ProductWithInventory,
    StockAdjustment,
    StockAdjustmentCreate,
)
from tindahaniq.models.sales import (
    ProductSalesSummary,
    SaleItemInput,
    SaleRecordWithProduct,
    SalesTransaction,
    SalesTransactionCreate,
)

__all__ = [
    "AdjustmentReason",
    "CSVImportResult",
    "ConsistencyIssue",
    "ConsistencySeverity",
    "DataConsistencyReport",
    "ExistingProductPolicy",
    "ImportBatch",
    "ImportRowError",
    "ImportType",
    "ImportWarning",
    "InventoryRecord",
    "Product",
    "ProductCreate",
    "ProductSalesSummary",
    "ProductUpdate",
    "ProductWithInventory",
    "SaleItemInput",
    "SaleRecordWithProduct",
    "SalesTransaction",
    "SalesTransactionCreate",
    "StockAdjustment",
    "StockAdjustmentCreate",
]
