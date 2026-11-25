"""Shared enumerations and domain primitives."""

from __future__ import annotations

from enum import StrEnum


class AdjustmentReason(StrEnum):
    """Supported audit reasons for stock quantity changes."""

    INITIAL_IMPORT = "INITIAL_IMPORT"
    CSV_SYNC = "CSV_SYNC"
    RESTOCK = "RESTOCK"
    SALE = "SALE"
    SPOILAGE = "SPOILAGE"
    MANUAL_ADJUSTMENT = "MANUAL_ADJUSTMENT"


class ImportType(StrEnum):
    """Supported CSV dataset categories."""

    INVENTORY = "INVENTORY"
    SALES = "SALES"


class ExistingProductPolicy(StrEnum):
    """Conflict resolution policy when importing SKUs already in the catalog."""

    UPDATE = "update"
    SKIP = "skip"
