# 0001. Turso (libSQL) for Production Persistence

**Status:** accepted

We use **Turso (libSQL)** as the durable external database in `production` on Streamlit Community Cloud, while retaining local **SQLite 3** (`data/tindahaniq.db` / `:memory:`) in `development` and `testing`.

## Context & Trade-offs

Streamlit Community Cloud uses an ephemeral container filesystem that wipes local SQLite files on app sleep, restart, or redeploy. Migrating to PostgreSQL (Neon/Supabase) would require rewriting `schema.sql` (`AUTOINCREMENT`, partial unique indexes, `LOWER(name)` indexes), changing `?` parameter placeholders to `%s`, and adapting `sqlite3.Row` hydration across all repositories. Turso preserves the exact SQLite 3 SQL dialect and integer-centavo schema with minimal implementation overhead while providing durable remote persistence.
