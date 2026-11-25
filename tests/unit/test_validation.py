"""Unit tests for data validation, currency parsing, SKU generation, and sanitization."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from tindahaniq.exceptions import ValidationError
from tindahaniq.utils.validation import (
    centavos_to_money,
    money_to_centavos,
    normalize_sku,
    parse_money_decimal,
    parse_non_negative_int,
    parse_sale_timestamp,
    sanitize_text,
)


def test_parse_money_decimal_handles_php_formats() -> None:
    assert parse_money_decimal("₱12.50") == Decimal("12.50")
    assert parse_money_decimal("PHP 1,250.75") == Decimal("1250.75")
    assert parse_money_decimal("  15 ") == Decimal("15.00")
    assert parse_money_decimal(0, allow_zero=True) == Decimal("0.00")
    assert parse_money_decimal(12.5) == Decimal("12.50")


@pytest.mark.parametrize(
    "bad_input",
    ["", "abc", "-5.00", Decimal("-0.01"), float("nan"), float("inf"), True, None],
)
def test_parse_money_decimal_rejects_invalid_values(bad_input: object) -> None:
    with pytest.raises(ValidationError):
        parse_money_decimal(bad_input, field_name="selling_price")


def test_parse_money_decimal_disallows_zero_when_configured() -> None:
    with pytest.raises(ValidationError):
        parse_money_decimal("0.00", field_name="selling_price", allow_zero=False)


def test_centavo_roundtrip_preserves_exact_decimal_values() -> None:
    for raw in ("0.00", "0.01", "12.25", "199.99", "2000.00"):
        dec = Decimal(raw)
        centavos = money_to_centavos(dec)
        assert isinstance(centavos, int)
        assert centavos_to_money(centavos) == dec


def test_parse_non_negative_int_accepts_whole_numbers_and_rejects_fractions() -> None:
    assert parse_non_negative_int("24", field_name="stock") == 24
    assert parse_non_negative_int("1,000", field_name="stock") == 1000
    assert parse_non_negative_int(10.0, field_name="stock") == 10

    for bad in ("2.5", 2.5, -1, True, "", "dozen", None):
        with pytest.raises(ValidationError):
            parse_non_negative_int(bad, field_name="stock", min_value=0)

    with pytest.raises(ValidationError):
        parse_non_negative_int(0, field_name="quantity_sold", min_value=1)


def test_sanitize_text_strips_control_chars_and_enforces_length() -> None:
    dirty = "  Lucky\x00 Me!\n\tPancit\x1b Canton  "
    assert sanitize_text(dirty, field_name="name") == "Lucky Me! Pancit Canton"
    assert sanitize_text(None, field_name="notes", allow_empty=True) == ""

    with pytest.raises(ValidationError):
        sanitize_text("   ", field_name="name")

    with pytest.raises(ValidationError):
        sanitize_text("A" * 121, field_name="name", max_length=120)


def test_normalize_sku_generates_collision_safe_slugs() -> None:
    assert normalize_sku(" nood 001 ") == "NOOD-001"
    auto_sku = normalize_sku(None, fallback_name="Coca-Cola Mismo 290ml", fallback_unit="bottle")
    assert auto_sku == "COCA-COLA-MISMO-290ML-BOTTLE"

    long_a = "Lucky Me Instant Pancit Canton Extra Special Seasoning Pack Variant Alpha"
    long_b = "Lucky Me Instant Pancit Canton Extra Special Seasoning Pack Variant Bravo"
    sku_a = normalize_sku(None, fallback_name=long_a, fallback_unit="pack")
    sku_b = normalize_sku(None, fallback_name=long_b, fallback_unit="pack")
    assert len(sku_a) <= 64
    assert len(sku_b) <= 64
    assert sku_a != sku_b


def test_parse_sale_timestamp_supports_multiple_formats() -> None:
    dt_iso = parse_sale_timestamp("2026-11-20 08:15:00")
    assert dt_iso == datetime(2026, 11, 20, 8, 15, 0, tzinfo=UTC)

    dt_us = parse_sale_timestamp("11/20/2026 04:30 PM")
    assert dt_us == datetime(2026, 11, 20, 16, 30, 0, tzinfo=UTC)

    dt_date = parse_sale_timestamp(date(2026, 11, 20))
    assert dt_date == datetime(2026, 11, 20, 0, 0, 0, tzinfo=UTC)

    with pytest.raises(ValidationError):
        parse_sale_timestamp("2026-13-99")
