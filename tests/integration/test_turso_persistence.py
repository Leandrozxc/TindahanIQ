"""Integration tests for Turso (libSQL) Hrana v2 HTTP persistence seam."""

from __future__ import annotations

import json
import sqlite3
from decimal import Decimal
from typing import Any

import httpx
import pytest

from tindahaniq.config import load_settings
from tindahaniq.db.connection import DatabaseManager
from tindahaniq.models.common import AdjustmentReason
from tindahaniq.models.product import ProductCreate, StockAdjustmentCreate
from tindahaniq.models.sales import SaleItemInput
from tindahaniq.services.consistency_service import ConsistencyService
from tindahaniq.services.inventory_service import InventoryService
from tindahaniq.services.sales_service import SalesService


def _decode_hrana_arg(arg: dict[str, Any]) -> Any:
    kind = arg.get("type")
    if kind == "null":
        return None
    if kind == "integer":
        return int(arg["value"])
    if kind == "float":
        return float(arg["value"])
    if kind == "text":
        return str(arg["value"])
    if kind == "blob":
        return bytes.fromhex(arg["base64"])
    return arg.get("value")


def _encode_hrana_val(value: Any) -> dict[str, Any]:
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "integer", "value": "1" if value else "0"}
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    if isinstance(value, float):
        return {"type": "float", "value": value}
    return {"type": "text", "value": str(value)}


def _make_mock_turso_transport(expected_token: str) -> httpx.MockTransport:
    """Create an in-memory SQLite-backed Hrana v2 /v2/pipeline mock transport."""
    backing = sqlite3.connect(":memory:", check_same_thread=False)
    backing.execute("PRAGMA foreign_keys = ON;")
    baton_counter = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/v2/pipeline":
            return httpx.Response(404, json={"error": "not found"})
        if request.headers.get("Authorization") != f"Bearer {expected_token}":
            return httpx.Response(401, json={"error": "unauthorized"})

        payload = json.loads(request.content.decode("utf-8"))
        requests_list = payload.get("requests", [])
        results: list[dict[str, Any]] = []

        for req in requests_list:
            req_type = req.get("type")
            if req_type == "execute":
                stmt = req["stmt"]
                sql = stmt["sql"]
                args = [_decode_hrana_arg(a) for a in stmt.get("args", [])]
                try:
                    cur = backing.execute(sql, args)
                    cols = [{"name": desc[0], "decltype": None} for desc in (cur.description or ())]
                    rows = [[_encode_hrana_val(val) for val in row] for row in cur.fetchall()]
                    results.append(
                        {
                            "type": "ok",
                            "response": {
                                "type": "execute",
                                "result": {
                                    "cols": cols,
                                    "rows": rows,
                                    "affected_row_count": cur.rowcount if cur.rowcount >= 0 else 0,
                                    "last_insert_rowid": (
                                        str(cur.lastrowid) if cur.lastrowid is not None else None
                                    ),
                                },
                            },
                        }
                    )
                except sqlite3.Error as exc:
                    results.append(
                        {
                            "type": "error",
                            "error": {"message": str(exc), "code": "SQLITE_ERROR"},
                        }
                    )
            elif req_type == "sequence":
                try:
                    backing.executescript(req["sql"])
                    backing.execute("PRAGMA foreign_keys = ON;")
                    results.append({"type": "ok", "response": {"type": "sequence"}})
                except sqlite3.Error as exc:
                    results.append(
                        {
                            "type": "error",
                            "error": {"message": str(exc), "code": "SQLITE_ERROR"},
                        }
                    )
            elif req_type == "close":
                results.append({"type": "ok", "response": {"type": "close"}})

        baton_counter["n"] += 1
        return httpx.Response(
            200,
            json={
                "baton": f"baton_{baton_counter['n']}",
                "base_url": None,
                "results": results,
            },
        )

    return httpx.MockTransport(handler)


def test_turso_persistence_supports_full_store_lifecycle(
    isolated_env: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = "turso-test-token-123"
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("TURSO_DATABASE_URL", "libsql://tindahaniq-demo.turso.io")
    monkeypatch.setenv("TURSO_AUTH_TOKEN", token)
    settings = load_settings(env_file=None)

    client = httpx.Client(transport=_make_mock_turso_transport(token))
    db = DatabaseManager.from_settings(settings, http_client=client)
    assert db.is_turso is True

    db.initialize_schema()

    inv = InventoryService(db)
    sales = SalesService(db)
    consistency = ConsistencyService(db)

    created = inv.create_product(
        ProductCreate(
            sku="PANCIT-01",
            name="Lucky Me Pancit Canton",
            category="Noodles",
            unit="pcs",
            unit_cost=Decimal("12.25"),
            selling_price=Decimal("16.00"),
            current_stock=20,
            reorder_point=5,
            lead_time_days=2,
        )
    )
    inv.adjust_stock(
        StockAdjustmentCreate(
            product_id=created.product.id,
            quantity_delta=10,
            reason=AdjustmentReason.RESTOCK,
            notes="Morning delivery",
        )
    )
    inv.adjust_stock(
        StockAdjustmentCreate(
            product_id=created.product.id,
            quantity_delta=-2,
            reason=AdjustmentReason.SPOILAGE,
            notes="Damaged packs",
        )
    )
    sales.record_sale(
        SaleItemInput(
            product_id=created.product.id,
            quantity_sold=3,
            external_ref="POS-TURSO-001",
        )
    )

    refreshed = inv.get_product(created.product.id)
    assert refreshed.inventory.current_stock == 25

    report = consistency.verify_data_consistency()
    assert report.is_consistent is True
    assert report.products_checked == 1
