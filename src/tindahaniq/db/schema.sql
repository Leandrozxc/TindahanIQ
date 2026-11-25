-- TindahanIQ Relational Database Schema (SQLite 3)
-- All monetary amounts are stored as exact integer centavos (1 PHP = 100 centavos).

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'Uncategorized',
    unit TEXT NOT NULL DEFAULT 'pcs',
    unit_cost_centavos INTEGER NOT NULL CHECK (unit_cost_centavos >= 0),
    selling_price_centavos INTEGER NOT NULL CHECK (selling_price_centavos > 0),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_products_name_lower ON products (LOWER(name));
CREATE INDEX IF NOT EXISTS idx_products_category ON products (category);

CREATE TABLE IF NOT EXISTS inventory (
    product_id INTEGER PRIMARY KEY REFERENCES products(id) ON DELETE CASCADE,
    current_stock INTEGER NOT NULL DEFAULT 0 CHECK (current_stock >= 0),
    reorder_point INTEGER NOT NULL DEFAULT 10 CHECK (reorder_point >= 0),
    lead_time_days INTEGER NOT NULL DEFAULT 1 CHECK (lead_time_days >= 1),
    last_restocked_at TEXT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS inventory_adjustments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    quantity_delta INTEGER NOT NULL CHECK (quantity_delta != 0),
    reason TEXT NOT NULL,
    notes TEXT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_adjustments_product_id ON inventory_adjustments (product_id, created_at);

CREATE TABLE IF NOT EXISTS import_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    import_type TEXT NOT NULL CHECK (import_type IN ('INVENTORY', 'SALES')),
    filename TEXT NOT NULL,
    file_checksum TEXT NOT NULL,
    rows_total INTEGER NOT NULL CHECK (rows_total >= 0),
    rows_accepted INTEGER NOT NULL CHECK (rows_accepted >= 0),
    rows_rejected INTEGER NOT NULL CHECK (rows_rejected >= 0),
    rows_skipped_duplicate INTEGER NOT NULL CHECK (rows_skipped_duplicate >= 0),
    imported_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_import_batches_checksum ON import_batches (import_type, file_checksum);

CREATE TABLE IF NOT EXISTS sales_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_ref TEXT NULL,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    sold_at TEXT NOT NULL,
    quantity_sold INTEGER NOT NULL CHECK (quantity_sold > 0),
    unit_price_centavos INTEGER NOT NULL CHECK (unit_price_centavos >= 0),
    unit_cost_centavos INTEGER NOT NULL CHECK (unit_cost_centavos >= 0),
    gross_revenue_centavos INTEGER NOT NULL CHECK (gross_revenue_centavos >= 0),
    import_batch_id INTEGER NULL REFERENCES import_batches(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sales_product_id ON sales_transactions (product_id);
CREATE INDEX IF NOT EXISTS idx_sales_sold_at ON sales_transactions (sold_at);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sales_external_ref_product
    ON sales_transactions (external_ref, product_id)
    WHERE external_ref IS NOT NULL;
