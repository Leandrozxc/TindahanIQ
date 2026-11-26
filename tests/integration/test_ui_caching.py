"""Integration tests for Streamlit resource caching and write-triggered cache invalidation."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from tindahaniq.config import load_settings
from tindahaniq.db.connection import DatabaseManager
from tindahaniq.models.product import ProductCreate
from tindahaniq.ui.context import build_app_context


def test_build_app_context_caches_schema_initialization_across_reruns(
    isolated_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    init_calls = {"count": 0}
    original_init = DatabaseManager.initialize_schema

    def counting_init(self: DatabaseManager) -> None:
        init_calls["count"] += 1
        original_init(self)

    monkeypatch.setattr(DatabaseManager, "initialize_schema", counting_init)
    settings = load_settings(env_file=None)

    ctx1 = build_app_context(settings)
    ctx2 = build_app_context(settings)

    assert ctx1.db is ctx2.db
    assert init_calls["count"] == 1


def test_transactional_write_invalidates_cached_store_reads(isolated_env: Path) -> None:
    settings = load_settings(env_file=None)
    ctx = build_app_context(settings)

    assert ctx.has_active_products() is False

    ctx.inventory_service.create_product(
        ProductCreate(
            sku="CACHE-01",
            name="Cached Sardines",
            category="Canned",
            unit="tin",
            unit_cost=Decimal("20.00"),
            selling_price=Decimal("25.00"),
            current_stock=10,
        )
    )

    assert ctx.has_active_products() is True
