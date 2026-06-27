# rag-retrieval-service

A regulated financial firm has a large pile of documents — regulatory guidance,
policy updates, compliance memos, credit agreements. People need to **ask
questions of that pile in plain language and get answers they can trust, with
citations back to the source document**: *"What's our current policy on adverse
credit?"*, *"Which updated guidance notes affect our lending criteria?"* Today
that means hunting through SharePoint by hand. This service answers the question
directly, grounded in the firm's own documents.

**Where the AI actually is: only at the end.** The system finds the relevant
document chunks — that's *search* (partly keyword maths, partly small
embedding/reranker models doing matching, not reasoning) — and then a language
model reads those chunks and writes one grounded, cited answer. **The LLM is used
once, to compose the answer.** Everything before it is retrieval engineering, and
that's where most of the value and most of the failure modes live.

**Why it's deterministic, not an agent.** Answering "what does this document say"
is one lookup, one answer — the path is fixed, nothing decides its next move based
on what it just found. An agentic loop here measured *worse* on a single-hop
corpus (0.83 vs 0.98 groundedness, ~6× latency), so this piece is deliberately a
fast, correct pipeline, not a loop. The sophistication is retrieval **quality**,
proven by measurement: a reranker that earns its p95 cost, an assembly policy
chosen against a table, not a default.

## Where it sits in the portfolio

`claudeaiportfolio` is a platform, not a repo pile: three application repos on an
**AKS → ACA → Container Apps Jobs** compute split, over two shared libraries
(`ai-infra-templates` = swappable platform code; `portfolio-infra` = shared
Terraform). This is **piece 1**, on **AKS** — because the vector index and the
embedding/reranker model servers must stay **warm** and the Postgres data layer
is **stateful**; serverless would trade away the p95 this piece exists to prove
for idle savings a constantly-queried service doesn't need.

## What it does (production-RAG depth)

- **Hybrid retrieval** — BM25 (Postgres FTS) + vector (pgvector HNSW), fused with
  Reciprocal Rank Fusion. RRF over weighted-sum: fuse on rank, no score
  normalisation or tuning to transfer between corpora.
- **Cross-encoder rerank** — a warm reranker pod re-scores the fused candidates.
  The [rerank ON/OFF eval](Makefile) (`make eval-rerank`) measures recall@k and
  p95 so the added latency is *justified*, not asserted.
- **Context assembly** — *what actually goes in the LLM window* is an explicit,
  swappable policy under a token budget (`top_k_by_fused` / `rerank_then_top_k` /
  `rerank_then_compress`), with a measured policy × (accuracy, tokens, latency)
  table (`make eval-assembly`). Context engineering as a measured decision, not a
  framework default.
- **Freshness + dedup** — content-hash dedup on ingest (no duplicate chunks); an
  ingest-timestamp freshness signal usable as a retrieval tiebreak.

## Interfaces — one service, the right surface per consumer

- **HTTP (FastAPI)** — versioned `POST /v1/search` (retrieval only, for agents)
  and `POST /v1/answer` (retrieve + grounded cited answer, for apps); typed
  Pydantic contracts, per-scope Auth0 JWT, published [OpenAPI](docs/openapi.json).
- **MCP** — the same retrieval as agent-callable tools (`search_knowledge`,
  `query_knowledge`).

See **[docs/API.md](docs/API.md)** for real consumer examples calling each.

The provider seam (`llm-provider`, in `ai-infra-templates`) keeps the single
answer-generation call portable across Claude and OpenAI — swap with one config
value, proven by a swap test on both arms.

## Scaling + latency (the measured artefacts)

- **Per-stage p50/p95/p99 under load** — `/v1/answer` returns `timings_ms`
  (embed / retrieve / rerank / generate); `make loadtest` aggregates them into the
  committed `out/latency.png`, so the reranker's cost is *attributable*.
- **KEDA autoscale** — Redis-queue-driven embedding workers, proven 0→10→0.
- **Token cost per query** — from `gen_ai.usage.*` spans.
- Production observability is the LGTM stack (OTel → Tempo → Grafana); the
  dashboard lives in [observability/](observability/).

## Compliance posture — considerations demonstrated (not a certification claim)

This is **awareness**, not an audited control mapping:

- **Workload identity over secrets** — Entra ID Workload Identity Federation pod →
  Azure; no service principals, no `.env` in CI; secrets via Key Vault + ESO.
- **Per-scope authorization** — Auth0 JWT with per-tool/route least-privilege
  scopes (`query:read`, `ingest:write`) on both the HTTP and MCP boundaries.
- **Data residency** — eval traces contain customer-document snippets, so the eval
  surface (Langfuse) is **self-hosted**, not third-party SaaS.
- **Audit trails** — OpenTelemetry GenAI/MCP spans on every retrieval and tool call.

A fuller SOC 2 / ISO 27001 control mapping is in [docs/COMPLIANCE.md](docs/COMPLIANCE.md);
the production-bar self-assessment is in [docs/SCORECARD.md](docs/SCORECARD.md).

## Layout

```
terraform/      Azure infra — invocations of portfolio-infra shared modules (RG, identity,
                postgres + replica, storage, openai, spot nodepool)
k8s/            Manifests: ingestion, query (retrieval-api, reranker, mcp-server), platform
src/            retrieval_api, upload_api, embedding_worker, mcp_server, common
evals/          recall@k, rerank ON/OFF delta, assembly-policy table
observability/  Grafana dashboard (latency / token-cost / autoscale)
docs/           API, ARCHITECTURE, COMPLIANCE, SCORECARD, SCOPING_1 + HANDOFF (piece 1)
```

## Conventions

- Python via `uv`; no `load_dotenv` — secrets reach pods via Workload Identity →
  Key Vault. Shared TF modules from `portfolio-infra` by pinned ref tag, not copied.
- Reusable code lives in `ai-infra-templates` (the `llm-provider` seam, the
  `agent-evals` harness) and is consumed via pinned git tags — never copy-pasted.
