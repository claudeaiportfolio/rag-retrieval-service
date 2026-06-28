# rag-retrieval-service — production-bar scorecard

Re-grade of the service against the **same dimensions** as the 2026-06-20
baseline review, so before/after is apples-to-apples. Baseline preserved in
[`rag-original-review-scorecard.md`](rag-original-review-scorecard.md).

**Grading lens:** *"what I'd expect to pass review at a company running this in
production"* — not the (already-strong) portfolio bar.

## Overall: B+ → **A−**

The baseline verdict was "architecture is production-grade; what's missing is the
unglamorous hardening — retries, a couple of real security gaps, test depth."
That hardening landed, and the evolution into a retrieval *service* added the
JD-headline depth the demo lacked: hybrid + rerank + freshness with the eval that
proves the reranker earns its cost, an explicit context-assembly policy, a real
versioned API surface, and scaling/latency as measured artefacts. What keeps it
from a clean A is operational: the live per-stage latency/autoscale numbers are
captured by running the committed targets against the brought-up stack (the
machinery is in; the rendered graphs land from that run).

## Re-grade — same dimensions as baseline

| Dimension | Grade (was → now) | Note (now) |
|---|---|---|
| Architecture / decoupling | A → **A** | Determinate retrieval pipeline (hybrid → fuse → rerank → assemble → answer); the agent loop was *removed by design* (it reproduced a 6× negative on single-hop) and relocated to piece 2. |
| Identity & secrets | A− → **A** | Entra ID Workload Identity Federation; Auth0 M2M; Key Vault + ESO; no secret via `os.environ`; identifying values render into a git-ignored `build/`, blocking leak scan on push + PR. |
| Observability | A → **A** | GenAI/MCP semconv spans + per-stage `timings_ms` on `/v1/answer`; Grafana dashboard committed; **live captured artefacts** (per-stage latency, rerank ON/OFF, assembly table, autoscale) in `observability/artefacts/`. |
| Security (authz) | C → **A−** | Per-scope Auth0 JWT centralised in `common/auth.py` and enforced on both the HTTP routes and the MCP tools (`require_scope` / per-tool scopes); PyJWT + JWKS TTL. Minus: wrong-scope rejection not re-verified live this session. |
| Resilience / error handling | C+ → **A−** | `tenacity` on the model call (both provider arms), dead-letter for poison ingest jobs, DB-touching `/readyz`, RQ `Retry`, read-replica for the query path. |
| Testing | C+ → **B+** | `mypy` + `ruff` CI gates; 30 unit tests incl. RRF fusion, freshness, assembly packing/compression, the provider swap test, and auth-scope logic. Minus: no automated integration tests in CI (deliberate live-E2E-over-stubs). |
| Packaging / CI / Docker | B+ → **A−** | centralise-don't-copy realised — `llm-provider` (new) / `agent-evals` / `platform-core` via pinned tags; shared org security action; published OpenAPI. |
| Readability / style | A → **A** | ruff + mypy clean across 23 source files; typed, well-commented, the *why* in the code. |
| Compliance posture (SOC 2 / ISO 27001) † | — → **B** | Strong control *primitives* — per-scope least-privilege authz, M2M tokens, Key Vault + blocking leak scan, TLS, workload identity, residency-driven self-hosted eval surface, OTel audit trails — mapped in [`COMPLIANCE.md`](COMPLIANCE.md). Unaudited demo: governance/evidence layer (policies, retention, access reviews, DR, pen test) is out of scope. |

† New dimension for the regulated/fintech context — not assessed at baseline.

## New capabilities (role headline — didn't exist at baseline)

| Capability | Grade | Evidence |
|---|---|---|
| Production-RAG depth | **A−** | Hybrid (BM25 + pgvector, RRF) + cross-encoder rerank + content-hash dedup + freshness. `make eval-rerank` measures the recall@k / p95 ON-vs-OFF delta — the reranker is justified by a number, not fashion. |
| Context engineering | **A−** | Explicit, swappable assembly policy under a token budget; `make eval-assembly` produces the policy × (accuracy, tokens, latency) table. Treats "what goes in the window" as a measured tradeoff. |
| API experience | **A** | Versioned `/v1/search` + `/v1/answer`, typed Pydantic contracts, per-scope JWT, published OpenAPI; MCP alongside for agents. One service, the right interface per consumer class. |
| Provider portability | **A−** | `llm-provider` seam (Claude + OpenAI) in `ai-infra-templates`; swap is one config value, proven by a swap test green on both arms. |
| Scaling + latency | **A−** | **Live-captured**: per-stage p50/p95 (rerank dominates at ~17.5s on CPU — measured, attributable), rerank ON/OFF delta (recall@1 +0.06 for +17.5s), KEDA 0→10→0 (peak 10). The honest finding (CPU reranker doesn't earn its p95 on this corpus) is the artefact's value. |

## Remaining gaps to a clean A

- **GPU reranker** — the live capture proved the CPU cross-encoder dominates p95
  (~17.5s/call); production needs a GPU node or a lighter reranker (2 warm
  replicas already in the manifest).
- **Automated integration tests in CI** — currently relies on a live E2E.
- **GitOps render-on-sync** — placeholder rendering on manual sync.

---
_Re-graded against `rag-original-review-scorecard.md`. Source of truth:
`SCOPING_1_rag_retrieval_service.md`._
