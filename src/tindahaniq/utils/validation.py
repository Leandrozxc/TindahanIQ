"""Strict data validation, currency conversion, SKU generation, and sanitization."""

from __future__ import annotations

import hashlib
import math
import re
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from tindahaniq.exceptions import ValidationError

TWO_PLACES = Decimal("0.01")
CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]+")
WHITESPACE_RE = re.compile(r"\s+")
CURRENCY_STRIP_RE = re.compile(r"(?i)^(?:\s*(?:php|₱|\$)\s*)|(?:\s*(?:php)\s*)$")
SKU_CLEAN_RE = re.compile(r"[^A-Z0-9]+")

SUPPORTED_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%m/%d/%Y",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M",
    "%m/%d/%Y %I:%M %p",
    "%m/%d/%Y %I:%M:%S %p",
)


def _is_missing_scalar(raw: object) -> bool:
    if raw is None:
        return True
    return bool(isinstance(raw, float) and math.isnan(raw))


def sanitize_text(
    raw: object,
    *,
    field_name: str,
    max_length: int = 120,
    allow_empty: bool = False,
) -> str:
    """Strip control characters, collapse whitespace, and enforce length bounds."""
    if _is_missing_scalar(raw):
        if allow_empty:
            return ""
        raise ValidationError(
            f"Missing required text field `{field_name}`",
            user_message=f"`{field_name}` is required and cannot be blank.",
            details={"field": field_name},
        )
    if not isinstance(raw, str):
        raw = str(raw)

    cleaned = CONTROL_CHAR_RE.sub(" ", raw)
    cleaned = WHITESPACE_RE.sub(" ", cleaned).strip()

    if not cleaned and not allow_empty:
        raise ValidationError(
            f"Blank value for `{field_name}`",
            user_message=f"`{field_name}` cannot be empty.",
            details={"field": field_name},
        )
    if len(cleaned) > max_length:
        raise ValidationError(
            f"`{field_name}` length {len(cleaned)} exceeds max {max_length}",
            user_message=f"`{field_name}` must be at most {max_length} characters.",
            details={"field": field_name, "max_length": max_length},
        )
    return cleaned


def parse_money_decimal(
    raw: object,
    *,
    field_name: str = "amount",
    allow_zero: bool = True,
) -> Decimal:
    """Parse PHP currency inputs (`₱12.50`, `1,250`, Decimal) into quantized Decimal."""
    if _is_missing_scalar(raw) or isinstance(raw, bool):
        raise ValidationError(
            f"Missing or boolean monetary value for `{field_name}`",
            user_message=f"`{field_name}` must be a valid monetary amount.",
            details={"field": field_name},
        )

    if isinstance(raw, Decimal):
        candidate = raw
    elif isinstance(raw, int):
        candidate = Decimal(raw)
    elif isinstance(raw, float):
        if not math.isfinite(raw):
            raise ValidationError(
                f"Non-finite float for `{field_name}`",
                user_message=f"`{field_name}` must be a finite monetary amount.",
                details={"field": field_name},
            )
        candidate = Decimal(str(raw))
    elif isinstance(raw, str):
        text = raw.strip()
        text = CURRENCY_STRIP_RE.sub("", text).replace(",", "").strip()
        if not text:
            raise ValidationError(
                f"Empty monetary string for `{field_name}`",
                user_message=f"`{field_name}` is required.",
                details={"field": field_name},
            )
        try:
            candidate = Decimal(text)
        except InvalidOperation as exc:
            raise ValidationError(
                f"Invalid monetary string `{raw}` for `{field_name}`",
                user_message=f"`{field_name}` ('{raw}') is not a valid currency amount.",
                details={"field": field_name, "raw_value": raw},
            ) from exc
    else:
        raise ValidationError(
            f"Unsupported type {type(raw).__name__} for `{field_name}`",
            user_message=f"`{field_name}` must be a valid currency amount.",
            details={"field": field_name},
        )

    if not candidate.is_finite():
        raise ValidationError(
            f"Non-finite Decimal for `{field_name}`",
            user_message=f"`{field_name}` must be a finite monetary amount.",
            details={"field": field_name},
        )

    quantized = candidate.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    if quantized < Decimal("0.00"):
        raise ValidationError(
            f"Negative amount {quantized} for `{field_name}`",
            user_message=f"`{field_name}` cannot be negative.",
            details={"field": field_name},
        )
    if not allow_zero and quantized == Decimal("0.00"):
        raise ValidationError(
            f"Zero amount not permitted for `{field_name}`",
            user_message=f"`{field_name}` must be greater than ₱0.00.",
            details={"field": field_name},
        )
    return quantized


def money_to_centavos(amount: Decimal) -> int:
    """Convert a Decimal peso amount into exact integer centavos."""
    quantized = amount.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    return int(quantized * 100)


def centavos_to_money(centavos: int) -> Decimal:
    """Convert exact integer centavos back into a 2-decimal peso Decimal."""
    return (Decimal(centavos) / Decimal(100)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def parse_non_negative_int(
    raw: object,
    *,
    field_name: str,
    min_value: int = 0,
) -> int:
    """Parse whole-number quantities while rejecting booleans, fractions, and negatives."""
    if _is_missing_scalar(raw) or isinstance(raw, bool):
        raise ValidationError(
            f"Missing or boolean integer for `{field_name}`",
            user_message=f"`{field_name}` must be a whole number.",
            details={"field": field_name},
        )

    if isinstance(raw, int):
        value = raw
    elif isinstance(raw, float):
        if not math.isfinite(raw) or not raw.is_integer():
            raise ValidationError(
                f"Non-integer float `{raw}` for `{field_name}`",
                user_message=f"`{field_name}` must be a whole number (no decimals).",
                details={"field": field_name, "raw_value": str(raw)},
            )
        value = int(raw)
    elif isinstance(raw, str):
        cleaned = raw.strip().replace(",", "")
        if not cleaned:
            raise ValidationError(
                f"Empty integer string for `{field_name}`",
                user_message=f"`{field_name}` is required.",
                details={"field": field_name},
            )
        try:
            dec = Decimal(cleaned)
        except InvalidOperation as exc:
            raise ValidationError(
                f"Invalid integer string `{raw}` for `{field_name}`",
                user_message=f"`{field_name}` ('{raw}') must be a whole number.",
                details={"field": field_name, "raw_value": raw},
            ) from exc
        if not dec.is_finite() or dec != dec.to_integral_value():
            raise ValidationError(
                f"Fractional numeric string `{raw}` for `{field_name}`",
                user_message=f"`{field_name}` ('{raw}') must be a whole number.",
                details={"field": field_name, "raw_value": raw},
            )
        value = int(dec)
    else:
        raise ValidationError(
            f"Unsupported type {type(raw).__name__} for `{field_name}`",
            user_message=f"`{field_name}` must be a whole number.",
            details={"field": field_name},
        )

    if value < min_value:
        comparator = "greater than 0" if min_value == 1 else f"at least {min_value}"
        raise ValidationError(
            f"Value {value} below minimum {min_value} for `{field_name}`",
            user_message=f"`{field_name}` must be {comparator}.",
            details={"field": field_name, "min_value": min_value},
        )
    return value


def normalize_sku(
    raw_sku: str | None,
    *,
    fallback_name: str = "",
    fallback_unit: str = "pcs",
    max_length: int = 64,
) -> str:
    """Normalize an explicit SKU or deterministically derive a collision-safe SKU slug."""
    candidate_raw = "" if _is_missing_scalar(raw_sku) else str(raw_sku).strip()
    if candidate_raw:
        slug = SKU_CLEAN_RE.sub("-", candidate_raw.upper()).strip("-")
        if not slug:
            raise ValidationError(
                f"SKU `{raw_sku}` contains no alphanumeric characters",
                user_message="SKU must contain letters or numbers.",
                details={"field": "sku", "raw_value": raw_sku},
            )
        if len(slug) > max_length:
            raise ValidationError(
                f"SKU `{slug}` exceeds max length {max_length}",
                user_message=f"SKU must be at most {max_length} characters.",
                details={"field": "sku", "max_length": max_length},
            )
        return slug

    name_clean = sanitize_text(fallback_name, field_name="product_name", max_length=120)
    unit_clean = sanitize_text(
        fallback_unit or "pcs",
        field_name="unit",
        max_length=32,
        allow_empty=True,
    )
    combined = f"{name_clean} {unit_clean}".strip().upper()
    slug = SKU_CLEAN_RE.sub("-", combined).strip("-")
    if not slug:
        raise ValidationError(
            "Unable to derive SKU from product name",
            user_message="Product name must contain letters or numbers to generate a SKU.",
            details={"field": "product_name"},
        )
    if len(slug) <= max_length:
        return slug

    digest = hashlib.sha256(combined.encode("utf-8")).hexdigest()[:6].upper()
    prefix = slug[: max_length - 7].rstrip("-")
    return f"{prefix}-{digest}"


def parse_sale_timestamp(raw: object, *, field_name: str = "sold_at") -> datetime:
    """Parse ISO or common retail date/datetime values into timezone-aware UTC datetimes."""
    if _is_missing_scalar(raw) or isinstance(raw, bool):
        raise ValidationError(
            f"Missing timestamp for `{field_name}`",
            user_message=f"`{field_name}` date/time is required.",
            details={"field": field_name},
        )

    if isinstance(raw, datetime):
        parsed = raw
    elif isinstance(raw, date):
        parsed = datetime(raw.year, raw.month, raw.day, tzinfo=UTC)
    elif isinstance(raw, str):
        text = raw.strip()
        if not text:
            raise ValidationError(
                f"Empty timestamp string for `{field_name}`",
                user_message=f"`{field_name}` date/time cannot be blank.",
                details={"field": field_name},
            )
        parsed = _parse_datetime_string(text, field_name=field_name)
    else:
        raise ValidationError(
            f"Unsupported type {type(raw).__name__} for `{field_name}`",
            user_message=f"`{field_name}` must be a valid date or timestamp.",
            details={"field": field_name},
        )

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_datetime_string(text: str, *, field_name: str) -> datetime:
    for fmt in SUPPORTED_DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValidationError(
            f"Unrecognized date format `{text}` for `{field_name}`",
            user_message=(
                f"`{field_name}` ('{text}') is not a recognized date format "
                "(use YYYY-MM-DD or MM/DD/YYYY)."
            ),
            details={"field": field_name, "raw_value": text},
        ) from exc
