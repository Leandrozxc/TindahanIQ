"""SQLite persistence repository for CSV import batch audit and checksum lookups."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from tindahaniq.db.connection import DatabaseManager
from tindahaniq.models.common import ImportType
from tindahaniq.models.import_result import ImportBatch


def _row_to_batch(row: sqlite3.Row) -> ImportBatch:
    return ImportBatch(
        id=int(row["id"]),
        import_type=ImportType(row["import_type"]),
        filename=str(row["filename"]),
        file_checksum=str(row["file_checksum"]),
        rows_total=int(row["rows_total"]),
        rows_accepted=int(row["rows_accepted"]),
        rows_rejected=int(row["rows_rejected"]),
        rows_skipped_duplicate=int(row["rows_skipped_duplicate"]),
        imported_at=datetime.fromisoformat(row["imported_at"]),
    )


class ImportBatchRepository:
    """Record and query uploaded CSV import batches."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    @contextmanager
    def _use_read(self, conn: sqlite3.Connection | None) -> Iterator[sqlite3.Connection]:
        if conn is not None:
            yield conn
        else:
            with self._db.read_connection() as managed:
                yield managed

    @contextmanager
    def _use_write(self, conn: sqlite3.Connection | None) -> Iterator[sqlite3.Connection]:
        if conn is not None:
            yield conn
        else:
            with self._db.transaction() as managed:
                yield managed

    def find_by_checksum(
        self,
        import_type: ImportType,
        file_checksum: str,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> ImportBatch | None:
        with self._use_read(conn) as active_conn:
            row = active_conn.execute(
                """
                SELECT * FROM import_batches
                WHERE import_type = ? AND file_checksum = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (import_type.value, file_checksum),
            ).fetchone()
            return _row_to_batch(row) if row else None

    def create_batch(
        self,
        *,
        import_type: ImportType,
        filename: str,
        file_checksum: str,
        rows_total: int,
        rows_accepted: int,
        rows_rejected: int,
        rows_skipped_duplicate: int,
        conn: sqlite3.Connection | None = None,
    ) -> ImportBatch:
        now = datetime.now(UTC).isoformat(timespec="seconds")
        with self._use_write(conn) as active_conn:
            cursor = active_conn.execute(
                """
                INSERT INTO import_batches (
                    import_type, filename, file_checksum,
                    rows_total, rows_accepted, rows_rejected,
                    rows_skipped_duplicate, imported_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    import_type.value,
                    filename,
                    file_checksum,
                    rows_total,
                    rows_accepted,
                    rows_rejected,
                    rows_skipped_duplicate,
                    now,
                ),
            )
            batch_id = int(cursor.lastrowid)
            row = active_conn.execute(
                "SELECT * FROM import_batches WHERE id = ?",
                (batch_id,),
            ).fetchone()
            assert row is not None
            return _row_to_batch(row)

    def list_batches(
        self,
        import_type: ImportType | None = None,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> list[ImportBatch]:
        with self._use_read(conn) as active_conn:
            if import_type is None:
                rows = active_conn.execute(
                    "SELECT * FROM import_batches ORDER BY id DESC"
                ).fetchall()
            else:
                rows = active_conn.execute(
                    "SELECT * FROM import_batches WHERE import_type = ? ORDER BY id DESC",
                    (import_type.value,),
                ).fetchall()
            return [_row_to_batch(row) for row in rows]
