"""CSV parsing, flexible header mapping, row validation, and batch persistence."""

from __future__ import annotations

import hashlib
import io
import re
from pathlib import Path
from typing import BinaryIO

import pandas as pd
from pydantic import ValidationError as PydanticValidationError

from tindahaniq.db.connection import DatabaseManager
from tindahaniq.db.repositories import (
    ImportBatchRepository,
    ProductRepository,
    SalesRepository,
)
from tindahaniq.exceptions import DataImportError, ValidationError
from tindahaniq.logging_config import get_logger
from tindahaniq.models.common import ExistingProductPolicy, ImportType
from tindahaniq.models.import_result import CSVImportResult, ImportRowError, ImportWarning
from tindahaniq.models.product import ProductCreate, ProductWithInventory
from tindahaniq.models.sales import SalesTransactionCreate

MAX_CSV_BYTES = 25 * 1024 * 1024  # 25 MB safety limit
HEADER_NORM_RE = re.compile(r"[^a-z0-9]+")

INVENTORY_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "sku": ("sku", "code", "product_code", "item_code", "barcode"),
    "name": ("product_name", "name", "product", "item", "item_name", "pangalan"),
    "category": ("category", "cat", "product_category", "kategorya"),
    "unit": ("unit", "uom", "unit_of_measure"),
    "unit_cost": ("unit_cost", "cost", "cost_price", "supplier_cost", "puhunan"),
    "selling_price": ("selling_price", "price", "retail_price", "srp", "presyo"),
    "current_stock": (
        "current_stock",
        "stock",
        "quantity",
        "qty",
        "stock_qty",
        "qty_on_hand",
    ),
    "reorder_point": ("reorder_point", "min_stock", "reorder_level", "low_stock_threshold"),
    "lead_time_days": ("lead_time_days", "lead_time"),
}
INVENTORY_REQUIRED = ("name", "unit_cost", "selling_price", "current_stock")

SALES_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "external_ref": ("external_ref", "transaction_id", "receipt_no", "receipt_id", "ref"),
    "sold_at": ("sold_at", "date", "sale_date", "timestamp", "transaction_date", "petsa"),
    "sku": ("sku", "code", "product_code", "item_code"),
    "product_name": ("product_name", "name", "product", "item", "item_name"),
    "quantity_sold": ("quantity_sold", "quantity", "qty", "units_sold"),
    "unit_price": ("unit_price", "selling_price", "price", "unit_price_at_sale"),
}
SALES_REQUIRED = ("sold_at", "quantity_sold")


def _normalize_header(col: object) -> str:
    return HEADER_NORM_RE.sub("_", str(col).strip().lower()).strip("_")


def _extract_bytes_and_name(
    source: bytes | str | Path | BinaryIO,
    filename: str | None,
) -> tuple[bytes, str]:
    if isinstance(source, Path):
        resolved_name = filename or source.name
        try:
            raw_bytes = source.read_bytes()
        except OSError as exc:
            raise DataImportError(
                f"Cannot read CSV file `{source}`: {exc}",
                user_message=f"Could not open file `{resolved_name}`.",
            ) from exc
        return raw_bytes, resolved_name

    if isinstance(source, str):
        path_candidate = Path(source)
        if "\n" not in source and "\r" not in source and path_candidate.exists():
            return path_candidate.read_bytes(), filename or path_candidate.name
        return source.encode("utf-8"), filename or "inline.csv"

    if isinstance(source, bytes):
        return source, filename or "upload.csv"

    if hasattr(source, "read"):
        stream_name = getattr(source, "name", None)
        resolved_name = filename or (Path(str(stream_name)).name if stream_name else "upload.csv")
        if hasattr(source, "seek"):
            source.seek(0)
        raw_bytes = source.read()
        if isinstance(raw_bytes, str):
            raw_bytes = raw_bytes.encode("utf-8")
        return raw_bytes, resolved_name

    raise DataImportError(
        f"Unsupported CSV source type: {type(source).__name__}",
        user_message="Unsupported file format provided for CSV import.",
    )


def _decode_csv_bytes(raw_bytes: bytes, filename: str) -> str:
    if not raw_bytes or not raw_bytes.strip():
        raise DataImportError(
            f"Uploaded CSV `{filename}` is empty",
            user_message=(
                f"The file `{filename}` is empty. Please upload a CSV with header and data rows."
            ),
        )
    if len(raw_bytes) > MAX_CSV_BYTES:
        raise DataImportError(
            f"CSV `{filename}` exceeds {MAX_CSV_BYTES} bytes",
            user_message="The uploaded CSV file exceeds the 25 MB size limit.",
        )
    if b"\x00" in raw_bytes:
        raise DataImportError(
            f"Binary null byte detected in `{filename}`",
            user_message=(
                f"`{filename}` appears to be a binary file (such as `.xlsx` or an image). "
                "Please export and upload it as a `.csv` file."
            ),
        )

    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue

    raise DataImportError(
        f"Unable to decode `{filename}` as UTF-8 or Windows-1252",
        user_message=(
            f"`{filename}` uses an unsupported text encoding. Save as UTF-8 CSV and retry."
        ),
    )


def _read_dataframe(text: str, filename: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
    except (pd.errors.ParserError, pd.errors.EmptyDataError, ValueError) as exc:
        raise DataImportError(
            f"Failed to parse CSV `{filename}`: {exc}",
            user_message=f"`{filename}` could not be parsed as a valid CSV table.",
        ) from exc

    if df.empty and len(df.columns) == 0:
        raise DataImportError(
            f"CSV `{filename}` contains no columns",
            user_message=f"`{filename}` has no column headers.",
        )
    return df


def _resolve_column_mapping(
    columns: list[object],
    aliases: dict[str, tuple[str, ...]],
) -> dict[str, str]:
    normalized_to_original: dict[str, str] = {}
    for col in columns:
        norm = _normalize_header(col)
        if norm and norm not in normalized_to_original:
            normalized_to_original[norm] = str(col)

    resolved: dict[str, str] = {}
    for canonical, candidates in aliases.items():
        for candidate in candidates:
            if candidate in normalized_to_original:
                resolved[canonical] = normalized_to_original[candidate]
                break
    return resolved


def _is_blank_row(row: pd.Series) -> bool:
    return all(not str(val).strip() for val in row.values)


def _extract_validation_error(
    exc: ValidationError | PydanticValidationError,
    row_number: int,
    raw_lookup: dict[str, str],
) -> ImportRowError:
    if isinstance(exc, ValidationError):
        field = str(exc.details.get("field", "row"))
        raw_val = str(exc.details.get("raw_value", raw_lookup.get(field, "")))
        return ImportRowError(
            row_number=row_number,
            field=field,
            raw_value=raw_val,
            message=exc.user_message,
        )

    first = exc.errors()[0]
    loc = ".".join(str(part) for part in first.get("loc", ("row",)))
    ctx_err = first.get("ctx", {}).get("error")
    if isinstance(ctx_err, ValidationError):
        field = str(ctx_err.details.get("field", loc))
        raw_val = str(ctx_err.details.get("raw_value", raw_lookup.get(field, "")))
        return ImportRowError(
            row_number=row_number,
            field=field,
            raw_value=raw_val,
            message=ctx_err.user_message,
        )
    return ImportRowError(
        row_number=row_number,
        field=loc,
        raw_value=raw_lookup.get(loc, ""),
        message=first.get("msg", "Invalid value."),
    )


class CSVImportService:
    """Validate, deduplicate, and import retail inventory and sales CSV datasets."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db
        self._products = ProductRepository(db)
        self._sales = SalesRepository(db)
        self._batches = ImportBatchRepository(db)
        self._logger = get_logger("csv_importer")

    def import_inventory_csv(
        self,
        source: bytes | str | Path | BinaryIO,
        *,
        filename: str | None = None,
        on_existing: ExistingProductPolicy = ExistingProductPolicy.UPDATE,
        allow_reimport: bool = False,
        dry_run: bool = False,
    ) -> CSVImportResult:
        """Parse and persist an inventory CSV file with row-level error isolation."""
        raw_bytes, resolved_name = _extract_bytes_and_name(source, filename)
        checksum = hashlib.sha256(raw_bytes).hexdigest()

        if not allow_reimport and not dry_run:
            prior = self._batches.find_by_checksum(ImportType.INVENTORY, checksum)
            if prior is not None:
                raise DataImportError(
                    f"Duplicate inventory CSV checksum {checksum} (batch {prior.id})",
                    user_message=(
                        f"`{resolved_name}` matches an inventory file already imported "
                        f"on {prior.imported_at:%Y-%m-%d %H:%M} UTC."
                    ),
                    details={"batch_id": prior.id, "checksum": checksum},
                )

        text = _decode_csv_bytes(raw_bytes, resolved_name)
        df = _read_dataframe(text, resolved_name)
        mapping = _resolve_column_mapping(list(df.columns), INVENTORY_COLUMN_ALIASES)

        missing_cols = [col for col in INVENTORY_REQUIRED if col not in mapping]
        if missing_cols:
            friendly = ", ".join(missing_cols)
            raise DataImportError(
                f"Inventory CSV `{resolved_name}` missing required columns: {friendly}",
                user_message=f"Missing required inventory column(s): {friendly}.",
                details={"missing_columns": missing_cols},
            )

        valid_items: list[tuple[int, ProductCreate]] = []
        warnings: list[ImportWarning] = []
        errors: list[ImportRowError] = []
        seen_skus_in_file: dict[str, int] = {}
        rows_total = 0
        rows_skipped_duplicate = 0

        for idx, row in df.iterrows():
            if _is_blank_row(row):
                continue
            rows_total += 1
            row_number = int(idx) + 2  # 1-based line number accounting for CSV header

            raw_values: dict[str, str] = {
                canonical: str(row[orig_col]).strip() for canonical, orig_col in mapping.items()
            }
            payload: dict[str, object] = {
                "sku": raw_values.get("sku") or None,
                "name": raw_values["name"],
                "unit_cost": raw_values["unit_cost"],
                "selling_price": raw_values["selling_price"],
                "current_stock": raw_values["current_stock"],
            }
            if raw_values.get("category"):
                payload["category"] = raw_values["category"]
            if raw_values.get("unit"):
                payload["unit"] = raw_values["unit"]
            if raw_values.get("reorder_point"):
                payload["reorder_point"] = raw_values["reorder_point"]
            if raw_values.get("lead_time_days"):
                payload["lead_time_days"] = raw_values["lead_time_days"]

            try:
                item = ProductCreate.model_validate(payload)
            except (ValidationError, PydanticValidationError) as exc:
                errors.append(
                    _extract_validation_error(
                        exc,
                        row_number,
                        {**raw_values, "product_name": raw_values.get("name", "")},
                    )
                )
                continue

            assert item.sku is not None
            if item.sku in seen_skus_in_file:
                first_line = seen_skus_in_file[item.sku]
                rows_skipped_duplicate += 1
                warnings.append(
                    ImportWarning(
                        row_number=row_number,
                        field="sku",
                        message=(
                            f"Duplicate SKU `{item.sku}` in CSV "
                            f"(already seen on row {first_line}); duplicate row skipped."
                        ),
                    )
                )
                continue

            seen_skus_in_file[item.sku] = row_number
            if item.selling_price < item.unit_cost:
                warnings.append(
                    ImportWarning(
                        row_number=row_number,
                        field="selling_price",
                        message=(
                            f"`{item.name}` selling price (₱{item.selling_price:.2f}) is lower "
                            f"than unit cost (₱{item.unit_cost:.2f})."
                        ),
                    )
                )
            valid_items.append((row_number, item))

        if rows_total == 0:
            raise DataImportError(
                f"Inventory CSV `{resolved_name}` has no data rows",
                user_message=f"`{resolved_name}` contains headers only and no product rows.",
            )

        rows_created = 0
        rows_updated = 0
        batch_id: int | None = None

        if dry_run:
            with self._db.read_connection() as conn:
                for _row_num, item in valid_items:
                    assert item.sku is not None
                    existing = self._products.get_by_sku(item.sku, conn=conn)
                    if existing is None:
                        rows_created += 1
                    elif on_existing == ExistingProductPolicy.UPDATE:
                        rows_updated += 1
                    else:
                        rows_skipped_duplicate += 1
        else:
            with self._db.transaction() as conn:
                for _row_num, item in valid_items:
                    assert item.sku is not None
                    existing = self._products.get_by_sku(item.sku, conn=conn)
                    if existing is not None and on_existing == ExistingProductPolicy.SKIP:
                        rows_skipped_duplicate += 1
                        continue
                    _record, created = self._products.upsert_product_from_import(
                        item,
                        notes=f"Imported from {resolved_name}",
                        conn=conn,
                    )
                    if created:
                        rows_created += 1
                    else:
                        rows_updated += 1

                batch = self._batches.create_batch(
                    import_type=ImportType.INVENTORY,
                    filename=resolved_name,
                    file_checksum=checksum,
                    rows_total=rows_total,
                    rows_accepted=rows_created + rows_updated,
                    rows_rejected=len(errors),
                    rows_skipped_duplicate=rows_skipped_duplicate,
                    conn=conn,
                )
                batch_id = batch.id

        self._logger.info(
            "Inventory CSV `%s` processed: total=%d created=%d updated=%d "
            "skipped=%d rejected=%d dry_run=%s",
            resolved_name,
            rows_total,
            rows_created,
            rows_updated,
            rows_skipped_duplicate,
            len(errors),
            dry_run,
        )
        return CSVImportResult(
            import_type=ImportType.INVENTORY,
            filename=resolved_name,
            file_checksum=checksum,
            dry_run=dry_run,
            batch_id=batch_id,
            rows_total=rows_total,
            rows_created=rows_created,
            rows_updated=rows_updated,
            rows_skipped_duplicate=rows_skipped_duplicate,
            rows_rejected=len(errors),
            warnings=tuple(warnings),
            errors=tuple(errors),
        )

    def import_sales_csv(
        self,
        source: bytes | str | Path | BinaryIO,
        *,
        filename: str | None = None,
        allow_reimport: bool = False,
        dry_run: bool = False,
    ) -> CSVImportResult:
        """Parse and persist historical sales CSV records linked to catalog products."""
        raw_bytes, resolved_name = _extract_bytes_and_name(source, filename)
        checksum = hashlib.sha256(raw_bytes).hexdigest()

        if not allow_reimport and not dry_run:
            prior = self._batches.find_by_checksum(ImportType.SALES, checksum)
            if prior is not None:
                raise DataImportError(
                    f"Duplicate sales CSV checksum {checksum} (batch {prior.id})",
                    user_message=(
                        f"`{resolved_name}` matches a sales file already imported "
                        f"on {prior.imported_at:%Y-%m-%d %H:%M} UTC."
                    ),
                    details={"batch_id": prior.id, "checksum": checksum},
                )

        text = _decode_csv_bytes(raw_bytes, resolved_name)
        df = _read_dataframe(text, resolved_name)
        mapping = _resolve_column_mapping(list(df.columns), SALES_COLUMN_ALIASES)

        missing_cols = [col for col in SALES_REQUIRED if col not in mapping]
        has_identifier = "sku" in mapping or "product_name" in mapping
        if not has_identifier:
            missing_cols.append("sku or product_name")
        if missing_cols:
            friendly = ", ".join(missing_cols)
            raise DataImportError(
                f"Sales CSV `{resolved_name}` missing required columns: {friendly}",
                user_message=f"Missing required sales column(s): {friendly}.",
                details={"missing_columns": missing_cols},
            )

        warnings: list[ImportWarning] = []
        errors: list[ImportRowError] = []
        valid_sales: list[SalesTransactionCreate] = []
        seen_ref_keys: set[tuple[str, int]] = set()
        rows_total = 0
        rows_skipped_duplicate = 0

        with self._db.read_connection() as read_conn:
            for idx, row in df.iterrows():
                if _is_blank_row(row):
                    continue
                rows_total += 1
                row_number = int(idx) + 2

                raw_values: dict[str, str] = {
                    canonical: str(row[orig_col]).strip() for canonical, orig_col in mapping.items()
                }

                matched_product, lookup_err = self._resolve_sale_product(
                    raw_values, row_number, read_conn
                )
                if lookup_err is not None or matched_product is None:
                    assert lookup_err is not None
                    errors.append(lookup_err)
                    continue

                raw_price = raw_values.get("unit_price", "")
                unit_price_input: object = (
                    raw_price if raw_price else matched_product.product.selling_price
                )
                payload: dict[str, object] = {
                    "product_id": matched_product.product.id,
                    "sold_at": raw_values["sold_at"],
                    "quantity_sold": raw_values["quantity_sold"],
                    "unit_price_at_sale": unit_price_input,
                    "unit_cost_at_sale": matched_product.product.unit_cost,
                    "external_ref": raw_values.get("external_ref") or None,
                }

                try:
                    sale_item = SalesTransactionCreate.model_validate(payload)
                except (ValidationError, PydanticValidationError) as exc:
                    errors.append(
                        _extract_validation_error(
                            exc,
                            row_number,
                            {
                                **raw_values,
                                "unit_price_at_sale": raw_price,
                            },
                        )
                    )
                    continue

                if sale_item.external_ref is not None:
                    ref_key = (sale_item.external_ref, sale_item.product_id)
                    if ref_key in seen_ref_keys or self._sales.exists_by_external_ref(
                        sale_item.external_ref, sale_item.product_id, conn=read_conn
                    ):
                        rows_skipped_duplicate += 1
                        warnings.append(
                            ImportWarning(
                                row_number=row_number,
                                field="external_ref",
                                message=(
                                    f"Duplicate transaction reference `{sale_item.external_ref}` "
                                    f"for `{matched_product.product.name}` skipped."
                                ),
                            )
                        )
                        continue
                    seen_ref_keys.add(ref_key)

                valid_sales.append(sale_item)

        if rows_total == 0:
            raise DataImportError(
                f"Sales CSV `{resolved_name}` has no data rows",
                user_message=f"`{resolved_name}` contains headers only and no sales rows.",
            )

        batch_id: int | None = None
        if not dry_run:
            with self._db.transaction() as conn:
                batch = self._batches.create_batch(
                    import_type=ImportType.SALES,
                    filename=resolved_name,
                    file_checksum=checksum,
                    rows_total=rows_total,
                    rows_accepted=len(valid_sales),
                    rows_rejected=len(errors),
                    rows_skipped_duplicate=rows_skipped_duplicate,
                    conn=conn,
                )
                batch_id = batch.id
                for sale_item in valid_sales:
                    with_batch = sale_item.model_copy(update={"import_batch_id": batch_id})
                    self._sales.create_sale(with_batch, conn=conn)

        self._logger.info(
            "Sales CSV `%s` processed: total=%d created=%d skipped=%d rejected=%d dry_run=%s",
            resolved_name,
            rows_total,
            len(valid_sales),
            rows_skipped_duplicate,
            len(errors),
            dry_run,
        )
        return CSVImportResult(
            import_type=ImportType.SALES,
            filename=resolved_name,
            file_checksum=checksum,
            dry_run=dry_run,
            batch_id=batch_id,
            rows_total=rows_total,
            rows_created=len(valid_sales),
            rows_updated=0,
            rows_skipped_duplicate=rows_skipped_duplicate,
            rows_rejected=len(errors),
            warnings=tuple(warnings),
            errors=tuple(errors),
        )

    def _resolve_sale_product(
        self,
        raw_values: dict[str, str],
        row_number: int,
        conn: object,
    ) -> tuple[ProductWithInventory | None, ImportRowError | None]:
        import sqlite3

        assert isinstance(conn, sqlite3.Connection)
        raw_sku = raw_values.get("sku", "").strip()
        raw_name = raw_values.get("product_name", "").strip()

        if raw_sku:
            found = self._products.get_by_sku(raw_sku, conn=conn)
            if found is not None:
                return found, None
            if not raw_name:
                return None, ImportRowError(
                    row_number=row_number,
                    field="sku",
                    raw_value=raw_sku,
                    message=(
                        f"Unknown SKU `{raw_sku}`. Import or add this product to inventory first."
                    ),
                )

        if raw_name:
            matches = self._products.find_by_name_case_insensitive(raw_name, conn=conn)
            if len(matches) == 1:
                return matches[0], None
            if len(matches) > 1:
                skus = ", ".join(m.product.sku for m in matches)
                return None, ImportRowError(
                    row_number=row_number,
                    field="product_name",
                    raw_value=raw_name,
                    message=(
                        f"Multiple products match `{raw_name}` ({skus}). "
                        "Specify the exact `sku` column to disambiguate."
                    ),
                )
            return None, ImportRowError(
                row_number=row_number,
                field="product_name",
                raw_value=raw_name,
                message=(
                    f"Unknown product `{raw_name}`. Import or add this product to inventory first."
                ),
            )

        return None, ImportRowError(
            row_number=row_number,
            field="product_name",
            raw_value="",
            message="Each sales row must provide either a `sku` or `product_name`.",
        )
