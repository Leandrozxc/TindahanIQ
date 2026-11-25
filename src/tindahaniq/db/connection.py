"""SQLite connection management, schema initialization, and atomic transactions."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from tindahaniq.exceptions import DatabaseError, TindahanIQError

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


class DatabaseManager:
    """Manage local SQLite connections with foreign-key enforcement and WAL journaling."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path) if str(db_path) != ":memory:" else Path(":memory:")
        self._is_memory = str(db_path) == ":memory:"

    def _open_connection(self) -> sqlite3.Connection:
        try:
            if not self._is_memory:
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
            target = ":memory:" if self._is_memory else str(self.db_path)
            conn = sqlite3.connect(target, timeout=10.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA busy_timeout = 5000;")
            if not self._is_memory:
                conn.execute("PRAGMA journal_mode = WAL;")
            return conn
        except sqlite3.Error as exc:
            raise DatabaseError(
                f"Failed to open SQLite database at `{self.db_path}`: {exc}",
                details={"db_path": str(self.db_path)},
            ) from exc
        except OSError as exc:
            raise DatabaseError(
                f"Filesystem error preparing SQLite path `{self.db_path}`: {exc}",
                details={"db_path": str(self.db_path)},
            ) from exc

    def initialize_schema(self) -> None:
        """Apply declarative DDL idempotently to ensure all tables and indexes exist."""
        ddl = SCHEMA_PATH.read_text(encoding="utf-8")
        conn = self._open_connection()
        try:
            conn.executescript(ddl)
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.commit()
        except sqlite3.Error as exc:
            conn.rollback()
            raise DatabaseError(
                f"Failed to initialize database schema: {exc}",
                details={"db_path": str(self.db_path)},
            ) from exc
        finally:
            conn.close()

    @contextmanager
    def read_connection(self) -> Iterator[sqlite3.Connection]:
        """Provide a short-lived read connection guaranteed to close on exit."""
        conn = self._open_connection()
        try:
            yield conn
        except TindahanIQError:
            raise
        except sqlite3.Error as exc:
            raise DatabaseError(f"Database query failed: {exc}") from exc
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Execute multiple SQL statements atomically, rolling back on any failure."""
        conn = self._open_connection()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            yield conn
            conn.commit()
        except TindahanIQError:
            conn.rollback()
            raise
        except sqlite3.Error as exc:
            conn.rollback()
            raise DatabaseError(f"Database transaction failed: {exc}") from exc
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
