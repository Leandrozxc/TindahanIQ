# 03: Resilient AI Business Consultant with bounded fallback

**What to build:** AI Business Consultant requests enforce a `30s` total timeout (`5s` connect), up to `2` jittered retries on transient `429`/`5xx`/network errors, an optional secondary OpenAI-compatible provider fallback, and graceful degradation so deterministic BI dashboards remain usable when upstream AI endpoints are unavailable.

**Blocked by:** None (can start immediately)

**Status:** done

- [x] Primary AI provider enforces `30s` request timeout (`5s` connect) and at most `2` jittered retries on `429`, `502`, `503`, `504`, connection, and timeout errors.
- [x] Optional secondary fallback credentials (`OPENAI_FALLBACK_BASE_URL`, `OPENAI_FALLBACK_MODEL`, `OPENAI_FALLBACK_API_KEY`) are supported and invoked when the primary provider fails.
- [x] Existing deterministic pre-grounding fallback, prompt-injection sanitization, secret scrubbing, and user-safe error messages continue passing automated tests.
