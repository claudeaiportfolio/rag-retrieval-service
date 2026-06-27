# rag-ingestion-platform — ORIGINAL review scorecard (baseline)

Recovered from the 2026-06-20 review session that produced the rework plan.
This is the **pre-rework baseline** — use the same dimensions for the final re-grade
so the before/after is apples-to-apples.

**Grading lens:** graded against *"what I'd expect to pass review at a company running
this in production"*, not *"is this good for a portfolio"* (by the portfolio bar it was
already strong).

## Overall (baseline): ~B+ / strong senior-level, ~75–80% of the way to production

Architecture and patterns were genuinely production-grade; what was missing was the
unglamorous hardening — retries, a couple of real security gaps, and test depth.

## Dimension scorecard (baseline)

| Dimension | Grade | Note |
|---|---|---|
| Architecture / decoupling | A | Clean, correct async, well-separated |
| Identity & secrets | A− | Exemplary, minus the one hardcoded UUID |
| Observability | A | GenAI semconv, non-fatal setup |
| Security (authz) | C | Scope enforcement not wired; `python-jose` CVEs |
| Resilience / error handling | C+ | No retries; per-call clients; batch limits |
| Testing | C+ | Pure-function only; no integration/type gate |
| Packaging / CI / Docker | B+ | Solid, minor masking issues |
| Readability / style | A | Consistent, typed, well-commented |

## Gaps identified (these drove the rework)

1. **Security — per-tool scope enforcement was dead code.** `auth.py` defined
   `verify_jwt`/`assert_scope`/`TOOL_SCOPES` but `mcp_server/main.py` never called them
   (a `query:read` token could call `ingest_document`). *Most important finding.*
2. **`python-jose` wrong choice** (unmaintained, algorithm-confusion CVEs); `_fetch_jwks`
   `@lru_cache`'d with no TTL + sync `httpx.get` in an async service.
3. **Hardcoded managed-identity client_id** in `scaledobject.yaml` (violated the
   never-hardcode-identifiers safety rule).
4. **No resilience on model calls** — no `tenacity`/backoff; new client per call;
   `embed_batch` sent all chunks in one request with no batch/token-limit splitting.
5. **Test depth portfolio-level** — pure functions only; no service/DB/auth/queue coverage;
   CI had no `mypy`/type-check gate.
6. **Smaller:** `healthz` liveness-only (no readiness touching the DB); worker abandons-and-
   retries even on unparseable messages instead of dead-lettering; `req.index_type` was a
   span attribute only, not used in the query; `Dockerfile` `uv sync … || … --no-lock`
   fallback masked a broken lockfile.

---
_Source: Claude Code transcript `3fd64b5e-…` (2026-06-20). Recovered 2026-06-21._
