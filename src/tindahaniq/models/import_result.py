"""Structured CSV import result, warning, error, and batch audit models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from tindahaniq.models.common import ImportType


class ImportRowError(BaseModel):
    """Line-level validation failure reported during CSV parsing."""

    model_config = ConfigDict(frozen=True)

    row_number: int = Field(ge=1)
    field: str
    raw_value: str = ""
    message: str


class ImportWarning(BaseModel):
    """Non-blocking data quality warning reported during CSV parsing."""

    model_config = ConfigDict(frozen=True)

    row_number: int = Field(ge=1)
    field: str
    message: str


class ImportBatch(BaseModel):
    """Persisted record of an uploaded CSV batch."""

    model_config = ConfigDict(frozen=True)

    id: int
    import_type: ImportType
    filename: str
    file_checksum: str
    rows_total: int
    rows_accepted: int
    rows_rejected: int
    rows_skipped_duplicate: int
    imported_at: datetime


class CSVImportResult(BaseModel):
    """Outcome summary returned by the CSV ingestion pipeline."""

    model_config = ConfigDict(frozen=True)

    import_type: ImportType
    filename: str
    file_checksum: str
    dry_run: bool = False
    batch_id: int | None = None
    rows_total: int = 0
    rows_created: int = 0
    rows_updated: int = 0
    rows_skipped_duplicate: int = 0
    rows_rejected: int = 0
    warnings: tuple[ImportWarning, ...] = ()
    errors: tuple[ImportRowError, ...] = ()

    @property
    def rows_accepted(self) -> int:
        """Total rows persisted (or eligible in dry-run)."""
        return self.rows_created + self.rows_updated
