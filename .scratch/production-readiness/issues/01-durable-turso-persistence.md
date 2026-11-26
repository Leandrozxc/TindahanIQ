# 01: Durable Turso persistence for Store data

**What to build:** In `production`, Store catalog, Inventory, Sales Transactions, and Stock Adjustments persist in Turso (libSQL) using `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN`, while `development` and `testing` continue using local SQLite. Schema initialization, transactional writes, Store consistency verification, and the health probe all operate against both backends transparently.

**Blocked by:** None (can start immediately)

**Status:** done

- [x] `production` environment connects to Turso (libSQL) while `development` and `testing` use local SQLite with no SQL dialect regressions.
- [x] All existing Store operations (Product creation, CSV import, Restock, Spoilage, Sales Transaction, and Stock Adjustment ledger reconciliation) pass against the Turso-capable persistence layer.
- [x] Health probe reports persistence status without exposing `TURSO_AUTH_TOKEN` or other secrets.
