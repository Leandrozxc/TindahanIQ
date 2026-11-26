"""Turso (libSQL) Hrana v2 HTTP pipeline adapter with a DB-API-compatible interface."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any

import httpx

from tindahaniq.exceptions import DatabaseError


def _encode_arg(value: Any) -> dict[str, Any]:
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "integer", "value": "1" if value else "0"}
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    if isinstance(value, float):
        return {"type": "float", "value": value}
    if isinstance(value, bytes | bytearray):
        return {"type": "blob", "base64": bytes(value).hex()}
    return {"type": "text", "value": str(value)}


def _decode_val(cell: dict[str, Any]) -> Any:
    kind = cell.get("type")
    if kind == "null":
        return None
    if kind == "integer":
        return int(cell["value"])
    if kind == "float":
        return float(cell["value"])
    if kind == "text":
        return str(cell["value"])
    if kind == "blob":
        raw = cell.get("base64", "")
        return bytes.fromhex(raw) if isinstance(raw, str) else b""
    return cell.get("value")


class TursoRow:
    """Row object supporting both column-name and positional indexing like sqlite3.Row."""

    __slots__ = ("_columns", "_values", "_index")

    def __init__(self, columns: tuple[str, ...], values: tuple[Any, ...]) -> None:
        self._columns = columns
        self._values = values
        self._index = {name: idx for idx, name in enumerate(columns)}

    def __getitem__(self, key: str | int) -> Any:
        if isinstance(key, int):
            return self._values[key]
        return self._values[self._index[key]]

    def __iter__(self) -> Iterator[Any]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def keys(self) -> tuple[str, ...]:
        """Return column names in result order."""
        return self._columns


class TursoCursor:
    """Cursor wrapper holding materialized rows and metadata from a Hrana execute result."""

    def __init__(
        self,
        rows: list[TursoRow],
        *,
        lastrowid: int | None = None,
        rowcount: int = -1,
    ) -> None:
        self._rows = rows
        self._pos = 0
        self.lastrowid = lastrowid
        self.rowcount = rowcount

    def fetchone(self) -> TursoRow | None:
        """Return the next row or None when exhausted."""
        if self._pos >= len(self._rows):
            return None
        row = self._rows[self._pos]
        self._pos += 1
        return row

    def fetchall(self) -> list[TursoRow]:
        """Return all remaining rows."""
        remaining = self._rows[self._pos :]
        self._pos = len(self._rows)
        return remaining


class TursoConnection:
    """DB-API-style connection backed by Turso's Hrana v2 HTTP `/v2/pipeline` endpoint."""

    def __init__(
        self,
        base_url: str,
        auth_token: str,
        *,
        http_client: httpx.Client | None = None,
        timeout: float = 15.0,
    ) -> None:
        normalized = base_url.strip().rstrip("/")
        if normalized.startswith("libsql://"):
            normalized = "https://" + normalized[len("libsql://") :]
        self._pipeline_url = f"{normalized}/v2/pipeline"
        self._auth_token = auth_token.strip()
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(timeout=timeout)
        self._baton: str | None = None
        self._in_transaction = False

    def _send_pipeline(self, requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"requests": requests}
        if self._baton is not None:
            payload["baton"] = self._baton

        try:
            response = self._client.post(
                self._pipeline_url,
                json=payload,
                headers={"Authorization": f"Bearer {self._auth_token}"},
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            raise DatabaseError(
                f"Turso HTTP request failed: {exc.__class__.__name__}",
                user_message="Could not reach the production database service.",
            ) from exc
        except ValueError as exc:
            raise DatabaseError(
                "Turso returned invalid JSON response",
                user_message="Production database returned an unexpected response.",
            ) from exc

        if "baton" in data:
            self._baton = data["baton"]

        results: list[dict[str, Any]] = data.get("results", [])
        for item in results:
            if item.get("type") == "error":
                err = item.get("error", {})
                msg = err.get("message", "Unknown Turso SQL error")
                raise DatabaseError(
                    f"Turso SQL error: {msg}",
                    details={"code": err.get("code")},
                )
        return results

    def execute(self, sql: str, params: Sequence[Any] = ()) -> TursoCursor:
        """Execute a single parameterized SQL statement."""
        upper = sql.strip().upper()
        if upper.startswith("BEGIN"):
            self._in_transaction = True

        stmt = {
            "sql": sql,
            "args": [_encode_arg(p) for p in params],
        }
        results = self._send_pipeline([{"type": "execute", "stmt": stmt}])
        result = results[0].get("response", {}).get("result", {})

        cols = tuple(str(col.get("name", "")) for col in result.get("cols", []))
        raw_rows = result.get("rows", [])
        rows = [
            TursoRow(cols, tuple(_decode_val(cell) for cell in raw_row)) for raw_row in raw_rows
        ]
        raw_rowid = result.get("last_insert_rowid")
        lastrowid = int(raw_rowid) if raw_rowid is not None else None
        rowcount = int(result.get("affected_row_count", -1))
        return TursoCursor(rows, lastrowid=lastrowid, rowcount=rowcount)

    def executemany(self, sql: str, seq_of_params: Sequence[Sequence[Any]]) -> TursoCursor:
        """Execute the same parameterized SQL statement for each parameter tuple."""
        if not seq_of_params:
            return TursoCursor([], rowcount=0)
        requests = [
            {
                "type": "execute",
                "stmt": {"sql": sql, "args": [_encode_arg(p) for p in params]},
            }
            for params in seq_of_params
        ]
        results = self._send_pipeline(requests)
        total_affected = sum(
            int(res.get("response", {}).get("result", {}).get("affected_row_count", 0))
            for res in results
        )
        return TursoCursor([], rowcount=total_affected)

    def executescript(self, ddl: str) -> None:
        """Execute a multi-statement SQL script atomically on Turso."""
        self._send_pipeline([{"type": "sequence", "sql": ddl}])

    def commit(self) -> None:
        """Commit an open transaction if one was started."""
        if self._in_transaction:
            self.execute("COMMIT;")
            self._in_transaction = False

    def rollback(self) -> None:
        """Roll back an open transaction if one was started."""
        if self._in_transaction:
            try:
                self.execute("ROLLBACK;")
            finally:
                self._in_transaction = False

    def close(self) -> None:
        """Close the Hrana stream baton and owned HTTP client."""
        try:
            if self._baton is not None:
                try:
                    self._send_pipeline([{"type": "close"}])
                except DatabaseError:
                    pass
                finally:
                    self._baton = None
        finally:
            if self._owns_client:
                self._client.close()
