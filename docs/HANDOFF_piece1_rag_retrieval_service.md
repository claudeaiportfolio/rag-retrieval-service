# HANDOFF — Piece 1: RAG Retrieval Service (AKS)

**Surface:** Claude Code (live repo operations).
**Repo:** `rag-ingestion-platform` (evolve in place — do **not** greenfield; it
already has RQ/Redis/KEDA/pgvector/eval bones and an A− scorecard).
**Source of truth:** `SCOPING_1_rag_retrieval_service.md`. This doc is the
execution layer — read SCOPING_1 for full justification before deviating.

---

## Mission

Turn a proven ingestion+retrieval *demo* into a production retrieval *service*.
Close the three JD gaps the demo doesn't hit: production RAG depth (hybrid +
rerank + freshness), a real **API surface** (FastAPI + MCP), and **scaling/latency
as committed artefacts**.

This is the **deterministic, non-agent** piece. No agent loop, no Skills, no
kill-switch here (all → piece 2). The signature is *measured numbers*, not agency.

---

## Path-determinacy verdict (already cleared — do not re-litigate)

Retrieval is determinate; single-shot wins (agentic RAG already measured at 0.83
vs 0.98 groundedness, ~6× latency on single-hop). Sophistication lives in
**retrieval quality + the eval that proves rerank earns its p95 cost**, not in a
loop. This piece passes the gate as the honestly-designed deterministic answer.

---

## Build order (work top-down; each step lands committed + evidenced)

1. **Prereq — unblock read replica.** Firewall + AD-admin TF (~10 lines, already
   scoped in the earlier RAG handoff). Query path must use the replica.
2. **Seam — `LLMProvider` in `ai-infra-templates`.** Claude + OpenAI impls; swap
   test green over the answer-gen call on the same groundedness eval (not "it
   compiles"). Used lightly here (answer-gen only); full agent-behaviour parity is
   stressed and proven in piece 2. Shape per SCOPING_1 §2 — abstract messages/tool
   round-trip/stream contract; pass model name, caching, structured-output mode
   through as opaque config.
3. **Retrieval depth.** Hybrid (BM25 + pgvector HNSW, fused via RRF — defend RRF
   over weighted-sum), then cross-encoder rerank stage, then freshness +
   content-hash dedup on ingest. **Eval the rerank ON/OFF delta as you go.**
3b. **Context-assembly policy — explicit + swappable.** top-k-by-fused-score vs
   rerank-then-top-k vs rerank-then-compress. Produce the **policy ×
   (accuracy, tokens, latency)** comparison table. This is the context-engineering
   artefact; do not bury it as an implicit default.
4. **API surface.** FastAPI versioned endpoints (`/v1/search`, `/v1/answer`),
   Pydantic contracts, structured outputs, auth on the boundary (build on the
   already-fixed per-tool-scope JWT model), published OpenAPI. **MCP interface
   alongside** the HTTP API — different consumer classes (app vs agent), not
   redundant. README shows a real consumer calling each.
5. **Scaling/latency artefacts.** Per-stage p50/p95/p99 under load (embed /
   retrieve / rerank / generate, so rerank cost is *attributable*), KEDA autoscale
   curve (0→10→0), token-cost-per-query panel from `gen_ai.usage.*`. **Commit the
   graphs**, not prose.
6. **Posture + SCORECARD + README.** Compliance-posture section (awareness-only,
   explicit "not a certification claim"), re-grade the scorecard against the
   production bar with a baseline→final table, README opens on the customer problem
   and places the repo in the AKS→ACA→Container-Apps-Jobs org shape.

---

## Definition of done (the checklist to drive against)

- [ ] Read replica unblocked; query path uses it.
- [ ] `LLMProvider` seam in `ai-infra-templates`; Claude + OpenAI impls; swap test
      green over the answer-gen call on the same groundedness eval (full
      agent-behaviour parity is proven in piece 2, not here).
- [ ] Hybrid retrieval (BM25 + vector, RRF) live.
- [ ] Rerank stage live; eval shows recall@k and p95 with rerank ON vs OFF.
- [ ] Context-assembly policy explicit + swappable; policy × (accuracy, tokens,
      latency) table committed.
- [ ] Freshness + content-hash dedup on ingest.
- [ ] FastAPI surface: versioned endpoints, Pydantic contracts, structured
      outputs, auth, published OpenAPI; real consumer example in README.
- [ ] MCP interface exposing the same retrieval.
- [ ] Per-stage p50/p95/p99 under load committed as a graph; autoscale curve;
      token-cost-per-query panel.
- [ ] Compliance-posture README section (awareness, non-certification).
- [ ] SCORECARD re-graded against production bar, baseline→final table.
- [ ] README opens with customer problem + places repo in the org compute shape.

---

## Explicitly out of scope (anti-shoehorn — do not add)

- **No agent loop** (reproduces the 6× negative; loop is piece 2).
- **No Skills** (no agent surface; first-class in piece 2, anchored to the +168%
  finding).
- **No kill-switch / runtime-authz** (no agent to govern; → piece 2).
- **No APIM AI-gateway** (guards one door here; relocates to shared substrate
  across all three consumers — org-level design stage).
- **No AI Foundry** (production penetration unverified).
- **No thick provider abstraction** (thin seam only — locked).
- **No shared "context manager"** abstraction (contradicts the per-workload
  assembly thesis; each piece tunes its own).
- **No compliance certification language** (posture-awareness only).
- Do not abstract provider-specific features (caching, structured outputs) behind
  the seam — pass through as opaque config.

---

## Standing conventions (apply throughout — non-negotiable)

- `uv` for Python; `hatchling`; src layout; `pyproject.toml`; pydantic-settings.
- **`os.environ` reads only in application code.** Never `load_dotenv()` / in-app
  secrets-loading, even dev-only. `.env` lives in the invocation surface
  (`uv run --env-file`, Makefile, direnv) — never in Python source.
- **Production posture everywhere:** Entra ID Workload Identity Federation over
  service principals; managed identity over credentials; Key Vault + ESO for
  secrets; no `.env` in CI. Never legacy auth patterns.
- Commit style `type(scope): subject` with a *why* body. **No commit hashes in
  handoff/committed docs** (they desync across Claude Code ↔ claude.ai sessions).
- Shared TF modules referenced from `portfolio-infra` **by ref tag, not copied**.
- **Verify Azure provider/resource versions and Anthropic product details against
  live docs before generating** — training data is stale on both.
- Every new capability passes the **"what breaks if absent"** test before it's
  built.
- Surface ambiguities/divergences explicitly rather than picking a default
  silently. Measure before claiming (rerank delta, assembly table, p-latencies).

---

## Coordination

Handoff docs and committed task files are the coordination layer between surfaces
— git and committed files, not copy-paste. Treat `Sync now` as a deliberate
session-start action. Strategy/reasoning happens in the Claude Project; this repo
is where it gets executed.
