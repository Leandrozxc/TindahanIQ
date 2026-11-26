"""SQLite and Turso (libSQL) connection management, schema initialization, and transactions."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from tindahaniq.db.turso import TursoConnection
from tindahaniq.exceptions import DatabaseError, TindahanIQError

if TYPE_CHECKING:
    from tindahaniq.config import AppSettings

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
DBConnection = sqlite3.Connection | TursoConnection


class DatabaseManager:
    """Manage local SQLite or production Turso (libSQL) connections and transactions."""

    def __init__(
        self,
        db_path: Path | str,
        *,
        turso_url: str | None = None,
        turso_auth_token: str | None = None,
        http_client: httpx.Client | None = None,
        on_commit: Callable[[], None] | None = None,
    ) -> None:
        self.db_path = Path(db_path) if str(db_path) != ":memory:" else Path(":memory:")
        self._is_memory = str(db_path) == ":memory:"
        self._turso_url = turso_url.strip() if turso_url else None
        self._turso_auth_token = turso_auth_token.strip() if turso_auth_token else None
        self._http_client = http_client
        self._on_commit = on_commit

    @classmethod
    def from_settings(
        cls,
        settings: AppSettings,
        *,
        http_client: httpx.Client | None = None,
        on_commit: Callable[[], None] | None = None,
    ) -> DatabaseManager:
        """Build a DatabaseManager routed to Turso in production or local SQLite otherwise."""
        if settings.app_env == "production" and settings.has_turso_config:
            assert settings.turso_http_url is not None
            assert settings.turso_auth_token is not None
            return cls(
                settings.resolved_database_path,
                turso_url=settings.turso_http_url,
                turso_auth_token=settings.turso_auth_token.get_secret_value(),
                http_client=http_client,
                on_commit=on_commit,
            )
        return cls(settings.resolved_database_path, on_commit=on_commit)

    @property
    def is_turso(self) -> bool:
        """Return True when this manager connects to a remote Turso (libSQL) database."""
        return bool(self._turso_url and self._turso_auth_token)

    def _open_connection(self) -> DBConnection:
        if self.is_turso:
            assert self._turso_url is not None
            assert self._turso_auth_token is not None
            conn = TursoConnection(
                self._turso_url,
                self._turso_auth_token,
                http_client=self._http_client,
            )
            conn.execute("PRAGMA foreign_keys = ON;")
            return conn

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
        except TindahanIQError:
            conn.rollback()
            raise
        except sqlite3.Error as exc:
            conn.rollback()
            raise DatabaseError(
                f"Failed to initialize database schema: {exc}",
                details={"db_path": str(self.db_path)},
            ) from exc
        finally:
            conn.close()

    @contextmanager
    def read_connection(self) -> Iterator[Any]:
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
    def transaction(self) -> Iterator[Any]:
        """Execute multiple SQL statements atomically, rolling back on any failure."""
        conn = self._open_connection()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            yield conn
            conn.commit()
            if self._on_commit is not None:
                self._on_commit()
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
