# SCOPING — Piece 1 of 3: RAG Retrieval Service (AKS)

## The use case, in plain language (lead with this — it's what the README opens on)

A regulated financial firm has a large pile of documents — regulatory guidance,
policy updates, compliance memos, credit agreements. People need to **ask
questions of that pile in plain language and get answers they can trust, with
citations back to the source document**. "What's our current policy on X?"
"Which of these updated guidance notes affect our lending criteria?" Today a
person hunts through SharePoint by hand. This service answers the question
directly, grounded in the firm's own documents.

**Where the AI actually is:** only at the *end*. The system finds the relevant
document chunks (that's search — partly plain keyword maths, partly small
embedding/reranker models doing *matching*, not reasoning), then a language model
(Claude/OpenAI) reads those chunks and writes one grounded, cited answer. **The
LLM is used once, to compose the answer.** Everything before it is retrieval
engineering. Being able to say precisely which bounded thing the LLM does — and
that the rest is search and plumbing — is the senior signal; most of the value
and most of the failure modes live in the retrieval, *not* the model.

**Why it's the deterministic (non-agent) piece:** answering "what does this
document say" is one lookup, one answer. The path is fixed — there's no point
where the system must decide its next move based on what it just found. An agent
loop here would pay more for the same result (the 6× negative you already
measured). The sophistication is retrieval *quality*, not agency.

---

**Org context:** `claudeaiportfolio` is being restructured as a platform, not a
repo pile. Three application repos on an AKS→ACA→Container Apps Jobs compute split, two
centralised library repos beneath them (`ai-infra-templates` = swappable
platform code; `portfolio-infra` = shared Terraform), and a `.github` profile
README that makes the whole shape legible at a glance. This is piece 1.

**This piece evolves the existing `rag-ingestion-platform`** (don't greenfield —
it already has the RQ/Redis/KEDA/pgvector/eval bones and an A− SCORECARD). The
job is to turn a *proven ingestion+retrieval demo* into a *production retrieval
service* that hits the JD bullets the demo doesn't: production RAG (rerank,
hybrid, freshness), a real **API surface**, and **scaling/latency as measured
artefacts**.

**This doc also defines the provider-abstraction seam** that pieces 2 and 3
consume. That section is here because RAG is where the seam first gets
exercised; the later docs reference it rather than redefining it.

---

## Explicit technology stack (every service named)

**Compute / platform**
- **Azure Kubernetes Service (AKS)** — hosts the retrieval service, model-server
  pods, and the KEDA-scaled ingestion workers. Justified below (not portfolio
  optics).
- **KEDA** — event-driven autoscaling of ingestion workers on Redis queue depth
  (`LLEN`); proven 0→10→0.
- **Envoy Gateway** — ingress, static IP, wildcard TLS termination, JWT verify at
  the edge.

**Data / retrieval**
- **PostgreSQL (Flexible Server)** with **pgvector** + **HNSW** index — vector
  store; primary + read replica topology.
- **PostgreSQL FTS** (or a dedicated BM25 index) — keyword half of hybrid retrieval.
- **Redis** — ingestion job queue (RQ) + caching.
- **Embedding model** + **cross-encoder reranker** — served as warm pods (small,
  single-purpose ML models — *not* the LLM).

**LLM / agent layer**
- **`LLMProvider` seam** (in `ai-infra-templates`) — Claude + OpenAI behind one
  protocol; used here only for the single answer-generation call.
- **Anthropic Python SDK** / **OpenAI SDK** — the two seam implementations.

**API / interface**
- **FastAPI** — versioned HTTP service (`/v1/search`, `/v1/answer`), Pydantic
  contracts, structured outputs, published OpenAPI.
- **MCP server** — same retrieval exposed as MCP tools alongside the HTTP API.

**Identity / secrets**
- **Entra ID Workload Identity Federation** — pod → Azure, no service principals.
- **Azure Key Vault** + **External Secrets Operator (ESO)** — secrets injection.
- **Auth0** (`michaelalinks.uk.auth0.com`) — JWT issuer; per-tool-scope auth on
  the API/MCP boundary (RFC 9728 / OAuth 2.1).

**Observability / eval**
- **OpenTelemetry** (GenAI semantic conventions 1.41.0) — the *contract*; the
  customer's production substrate.
- **LGTM stack** (OTel Collector → **Grafana Tempo** → **Grafana**) — production
  observability: latency, cost, autoscale dashboards.
- **Self-hosted Langfuse** (on AKS) — the *eval* surface (trace-level inspection
  during development). Self-hosted, not SaaS, because eval traces contain
  customer-document snippets → data residency rules out third-party SaaS. Swapped
  behind the eval adapter in `ai-infra-templates` (Braintrust is the alternative
  implementation).

**IaC / CI**
- **Terraform** (shared modules in `portfolio-infra`, referenced by ref tag).
- **GitHub Actions** + **Flux CD** (GitOps) — build + reconcile.
- **uv** + **hatchling** — Python packaging; **Docker** — container builds.

---

## Infra justification — why AKS, and why not ACA or Functions

The compute choice is defended on *workload characteristics*, not the "compute
heterogeneity" narrative. The honest test: would this workload run worse on the
other two? Yes — and here's why.

- **Stateful data layer.** Postgres + pgvector + HNSW + a primary/replica split is
  a stateful set with persistent storage. Serverless compute fights this; you'd be
  bolting an always-on stateful dependency onto a scale-to-zero front end and
  getting the worst of both.
- **Warm caches are latency-critical.** The HNSW index and the embedding/reranker
  models want to stay resident in memory. Cold-starting them on scale-from-zero
  would wreck p95 — the exact latency number this piece exists to *prove* is good.
  Scale-to-zero would trade away p95 for idle savings a constantly-queried service
  doesn't need.
- **The ingestion path is already KEDA-on-AKS.** Redis-queue-driven worker
  autoscaling (the ModelML JD bullet: Redis, task queues, scaling) is native to
  the cluster.

**Why not ACA:** scale-to-zero is a liability here, not an asset — the service is
queried constantly and needs warm state. **Why not Functions:** retrieval is a
warm-path, stateful, latency-sensitive request/response service, not discrete
event-triggered units of work. **The interview sentence:** "Retrieval lives on AKS
because the vector index and model servers must stay warm and the data layer is
stateful — serverless would trade my p95 away for idle savings I don't need."

---

## Mapping to the original 11 points

| # | Point | Where it's hit in this piece |
|---|---|---|
| 1 | Compliance posture (SOC2/ISO/GDPR awareness) | §3d — workload identity, residency-driven self-hosted Langfuse, audit logging; awareness-only, non-certification |
| 2 | **API experience** | §3b — FastAPI versioned endpoints, Pydantic contracts, structured outputs, published OpenAPI; MCP surface alongside |
| 3 | Observability visuals | §4 — latency dashboard (per-stage p50/95/99), rerank on/off, autoscale curve (Grafana/LGTM) |
| 4 | Scorecard carry-forward | §5 — standing per-repo SCORECARD, production-bar grading, baseline→re-grade table |
| 5 | Infra + token-cost visuals | §4 — token-cost-per-query panel from `gen_ai.usage.*` GenAI spans |
| 6 | Okta kill switch / runtime authz | **Not here** — belongs to piece 2 (agent piece). Stated in cut-list. |
| 7 | Azure AI infra (APIM AI gateway; Foundry dropped) | **DECIDED: not in piece 1** — relocated to the shared platform substrate (its justification only holds across multiple model consumers, not one service). See note below. |
| 8 | MCP + Skills (Anthropic JD) | MCP: §3b (MCP server surface). **Skills: not here** — no agent surface; belongs to piece 2. Stated in cut-list. |
| 9 | Data pipelines + Snowflake | **Not here** — the eval-data pipeline + Snowflake-as-eval-warehouse is piece 3. This piece feeds it (emits OTel traces) but doesn't own it. |
| 10 | **Scaling + latency** | §3c — per-stage p50/95/99 under load, KEDA autoscale curve, replica split |
| 11 | Reusability / templating / provider portability | §2 — the `LLMProvider` seam (Claude+OpenAI, config swap) defined here, consumed by 2 & 3; eval adapter (Langfuse/Braintrust) swappable |

**Points deliberately NOT in piece 1 (and why — anti-shoehorn):** #6 kill-switch
and #8 Skills both require an agent surface this piece doesn't have; forcing them
in would be the overengineering you flagged. Both move to piece 2. #9 data
pipeline is piece 3's core. **#7 APIM AI-gateway — DECIDED OUT of piece 1.**
A gateway in front of one service guards a single door; its value (centralised
model access, token quotas/rate-limiting, per-team cost attribution, gateway-level
provider failover, single egress/credential point) only earns its "what breaks if
absent" test *across multiple model consumers*. So it relocates to the **shared
platform substrate** (alongside `ai-infra-templates` / `portfolio-infra`), sitting
in front of all three pieces' model calls — where it ties together #5 (cost
visibility) and #11 (provider portability at the *network* tier, complementing the
code-level seam). To be scoped at the org-level design stage, not here.

---

## 0. Path-determinacy verdict (the gate — read first)

Per the standing project instruction, the verdict comes before any scope.

- **(a) Control flow:** The retrieval path is **determinate**. A query comes in,
  you embed it, you retrieve, you (optionally) rerank, you return. You can draw
  the flowchart completely in advance. The next step does *not* depend on what
  the last step found.
- **(b) Predicted sign:** For the **retrieval itself**, single-shot **wins** —
  and you already measured this (agentic RAG: 0.83 vs 0.98 groundedness, ~6×
  latency on single-hop). **This piece is therefore deliberately NOT an agent
  piece.** It is a deterministic production service, and that is the correct
  engineering answer.
- **(c) Where judgment lives:** The sophistication here is **not** agency — it's
  *retrieval quality engineering*: hybrid (BM25 + vector) fusion, reranking,
  freshness/dedup, and the **eval that proves the rerank stage earns its added
  latency**. That last clause is the interview-defensible thesis: "I added a
  reranker and measured that it improved recall enough to justify its p95 cost —
  here's the number." Sophistication justified by measurement, not by fashion.

**Why this passes the gate without being an agent piece:** the gate says new
pieces must sit on the agent-wins side OR be honestly designed as the
deterministic answer with the reasoning shown. This is the latter, explicitly.
It is the portfolio's "I know retrieval is determinate, so I built a fast
correct pipeline, not a loop" exhibit — the counterweight that makes the
agent-*wins* piece (piece 2) credible.

---

## 1. What this piece proves (succinct justification per JD cluster)

Each capability below has a **"what breaks if absent"** test. If the honest
answer is "nothing, it's keyword coverage," it's cut. Nothing here failed the
test; the justification is stated so you can defend each in interview.

| Capability | What it proves | What breaks if absent |
|---|---|---|
| Hybrid retrieval (BM25 + vector) | Production RAG ≠ naive vector search | Pure-vector misses exact-term/code/ID matches; regulated-doc queries with specific clause refs fail |
| Reranking stage | Retrieval-quality engineering + the latency/quality tradeoff judgment | Top-k by cosine alone returns plausible-but-wrong chunks; no defensible answer to "how do you improve precision?" |
| Freshness + dedup on ingest | "Production RAG at scale" (the demo→senior line) | Stale/duplicate chunks silently corrupt answers; the exact gap Tek Ninjas names as the senior bar |
| FastAPI service surface | The API experience the JDs name (ModelML, JPM) | No artefact shows you ship consumable services, only infra+agents |
| p50/p95/p99 under load | Scaling + latency (recurring in your screening calls) | "It scales" is unproven assertion; reranker cost is hand-waved |
| Provider seam (defined here) | The portability thesis (ModelML founder / Fable disablement) | Model lock-in; can't answer "what if you had to swap providers" |
| MCP interface on the service | Anthropic JD (MCP) + reuses existing live-MCP credibility | Loses the MCP signal you've already earned |
| Compliance *posture* (light) | Awareness, not certification | Regulated-buyer conversations have no platform-maturity signal |

---

## 2. The provider-abstraction seam (defined here, consumed by pieces 2 & 3)

**Decision (locked): thin seam, `LLMProvider` protocol, Claude + OpenAI
implementations, config swap.** Lives in `ai-infra-templates`, not in this repo.

### 2a. The defensible boundary
Abstract the **agent loop's interaction surface** — the coupling points where
Claude and OpenAI actually differ — and pass provider-specific *config* through
as opaque. Do **not** abstract differentiating features.

- **Abstract (real coupling):** messages, tool-call requests, tool results, and
  the **stream event contract**. This is where Claude (content blocks,
  `tool_use`/`tool_result`) and OpenAI (`tool_calls`, function objects) diverge,
  and where a naive `complete(str)->str` interface would be too thin to be real.
- **Pass through opaque (don't abstract):** model names, prompt-caching flags,
  extended-thinking toggles, structured-output modes. These are provider
  *config*, not interface.

### 2b. Protocol shape (illustrative, not final)
```python
class LLMProvider(Protocol):
    async def complete(self, messages: list[Message],
                       tools: list[ToolSpec] | None = None,
                       config: ProviderConfig | None = None) -> Completion: ...
    async def stream(self, messages: list[Message],
                     tools: list[ToolSpec] | None = None,
                     config: ProviderConfig | None = None) -> AsyncIterator[StreamEvent]: ...
```
`Message`, `ToolSpec`, `ToolResult`, `StreamEvent`, `Completion` are
provider-neutral Pydantic types. `ProviderConfig` is an opaque bag the
implementation interprets (Claude impl reads `cache_control`; OpenAI impl
ignores it). Swap is one config value: `LLM_PROVIDER=claude|openai`.

### 2c. The interview sentence (the justification)
> "I abstracted the loop's dependency on the provider — messages, tool round-trip,
> stream contract — not the providers' differentiating features. Abstracting away
> prompt caching or structured outputs would cost more than the lock-in it saves.
> The Fable/Mythos disablement is the proof case: teams that hadn't hard-wired one
> provider shifted in minutes."

### 2d. The proof the swap is real
A swap test in `ai-infra-templates`: the same eval suite runs against
`LLM_PROVIDER=claude` and `LLM_PROVIDER=openai`, both green. Not "the interface
compiles" — "the same agent behaviour passes evals on both." That test is the
artefact; without it the seam is just an interface nobody proved.

**Scope note:** the seam is *defined and unit-tested* in this piece, but it's
the **agent loop** (piece 2) that exercises it hardest. In the RAG service the
seam is used only for the answer-generation call (retrieval itself uses no LLM).
So: build the seam here, prove the basic swap here, stress it in piece 2.

---

## 3. The retrieval service — concrete scope

### 3a. Retrieval pipeline (the production-RAG depth)
- **Hybrid:** BM25 (Postgres FTS or a dedicated index) + pgvector HNSW, fused
  (Reciprocal Rank Fusion is the defensible default — simple, no tuning, explain
  why over weighted-sum).
- **Rerank:** a cross-encoder rerank stage over the fused candidate set. **The
  eval must measure recall@k and p95 with rerank ON vs OFF** — that delta is the
  headline artefact and the thing you defend in interview.
- **Freshness + dedup:** content-hash dedup on ingest (no duplicate chunks);
  a freshness signal (ingest timestamp) usable as a retrieval filter/tiebreak.
  This is the "reliable freshness, dedup" the senior bar names.

### 3a-bis. Context assembly (the context-engineering signal — make it explicit)

This is where the JD phrase "context engineering" actually lives, and it's worth
making a *visible, measured* policy decision rather than an implicit default —
because it's the senior signal most candidates only have the framework-feature
version of.

**The decision:** once retrieval returns candidate chunks, *what actually goes
into the LLM's context window* for the answer call is a choice with a token
budget. You can't just stuff all candidates in — there's a fixed budget, and more
context is not monotonically better. The defensible move is to make the assembly
policy **explicit and swappable** (e.g. top-k-by-fused-score vs. rerank-then-
top-k vs. rerank-then-compress) and **measure each against the same eval** on
both answer accuracy *and* token cost. That comparison table — policy ×
(accuracy, tokens, latency) — is the artefact. It demonstrates you treat "what
goes in the window" as an engineering decision with a measured tradeoff, not a
default you inherited from a framework.

**The honest frontier caveat (state this plainly — it's an interview asset):**
deciding what goes in the context window is, in the general case, an *unsolved*
optimisation problem, and anyone selling a clean general solution is overselling.
It's a knapsack with a fixed token budget and candidate items whose value is
**task-dependent and only partly observable**, which makes it genuinely harder
than it looks for four specific reasons:

- **Value is unknown at assembly time.** Unlike a cache hit/miss you get *after*
  the fact, you often can't cleanly attribute a good or bad answer to the presence
  of one chunk — the eval signal is noisy and entangled. You optimise against a
  reward you can barely measure.
- **Items interact.** Two chunks can be redundant (pay twice, gain once), or one
  only useful alongside another. So you can't score items independently and take
  top-k — which is exactly what naive RAG does, and why it plateaus.
- **Position matters.** Models weight the start and end of the window more than
  the middle ("lost in the middle"), so assembly is *what* to include *and where*
  — a constraint plain retrieval doesn't have.
- **The budget is contended by non-substitutable things.** Retrieved docs vs.
  conversation history vs. tool results vs. instructions all compete for the same
  tokens with no common currency, so the tradeoff is resolved by *policy*, not a
  clean metric.

**Why it's hand-tuned per workload (and why that's familiar territory for you):**
the right policy depends on the task's failure mode — a long support chat is
history-dominated (evict old turns, never drop the policy doc); a code task needs
current file contents and type signatures present; a research task needs
intermediate results compressed into running notes. There's no one policy that's
correct across all of them — **the same way there's no one cache-eviction or
autoscaling policy optimal across all access patterns.** That parallel is the
interview line: context assembly is cache-eviction tuning with fuzzier hit/miss
semantics, and it's native to your platform-engineering background. (Note: this
is *why* the portfolio deliberately does **not** build a shared "context manager"
abstraction across the three pieces — a single cross-workload assembler would
contradict the very thesis that assembly is necessarily per-workload. Each piece
tunes its own.)

### 3b. API surface (the gap to close)
A **FastAPI** service, not an MCP-only surface:
- Versioned endpoints (`/v1/search`, `/v1/answer`), Pydantic request/response
  contracts, **structured outputs** (typed, not free-text blobs).
- Auth on the API boundary (reuse the per-tool-scope JWT model already hardened
  in the repo — the dead-code authz gap was the most important baseline finding;
  it's fixed, build on it).
- OpenAPI spec published. The README shows a real consumer calling it.
- **MCP interface alongside** the HTTP API (DECIDED: keep both). The two surfaces
  are *not* redundant — they serve different consumers, and that distinction is
  the API-design signal: **FastAPI is how a human-built application** (a compliance
  dashboard, an internal tool) **consumes retrieval; MCP is how an agent consumes
  it** — e.g. how piece 2's diligence agent would call retrieval as a tool. "One
  service, the right interface for each consumer class (app vs agent)" is the
  justification — not "MCP to tick the Anthropic JD box." Also reuses your live-MCP
  credibility (`aks-mcp` PRs).

### 3c. Scaling + latency (the measured artefacts)
- KEDA autoscale curve (you have 0→10→0 proven) committed as a **graph**, not
  prose.
- **p50/p95/p99** latency under load, broken out by stage (embed / retrieve /
  rerank / generate) so the rerank cost is *attributable*. This is the
  "where does the latency go" answer that separates senior from demo.
- DB scaling: the read-replica split (currently blocked by the replica
  firewall/AD-admin TF — that unblock is a prerequisite, ~10 lines, already
  scoped in the earlier RAG handoff).

### 3d. Compliance posture (light, awareness-only)
**Not** a control-mapping doc. Just surface the posture choices you already make,
so a viewer sees you think about it:
- Workload identity over secrets (already true — make it *visible* in the README).
- Self-hosted Langfuse for data residency (already the plan — state *why* in one
  line: "eval traces contain customer-doc snippets, so residency rules out SaaS").
- Audit logging on every agent/tool action (who/what/when).
- One short README section: "Compliance posture — considerations demonstrated."
  Frames these as *awareness*, explicitly says "not a certification claim."

---

## 4. Observability + cost visuals (proof artefacts)

These exist to *prove §3c's numbers*, so an interviewer believes them rather than
takes your word. Instrumentation largely exists (OTel GenAI semconv wired).

- **Latency dashboard:** per-stage p50/p95/p99, the rerank on/off comparison.
- **Autoscale curve:** queue depth vs worker count vs latency, the KEDA story.
- **Token-cost panel:** cost per query / per document, derived from GenAI spans
  (`gen_ai.usage.*`) — the FinOps story a platform buyer cares about.

**DECIDED: Grafana for all of piece 1's panels; no bespoke custom page here.**
Piece 1 is the *deterministic* piece — its signature is the *measured numbers*
(retrieval-quality deltas, latency attribution), and Grafana shows those
credibly without a hand-built UI competing for time against the live-coding
round. The per-stage latency-attribution view is the signature *panel*. If you
want one bespoke, point-of-view custom visual anywhere in the portfolio, its
natural home is the eval/observability piece (piece 3), not the RAG service —
deferred to there.

---

## 5. SCORECARD (carry-forward, standing artefact)

Adopt the uploaded scorecard format as a **standing per-repo artefact**, graded
against *"would this pass review at a company running it in production,"* not the
portfolio bar. Maintain the baseline→re-grade dimension table so the before/after
proves you hardened to a production bar. Dimensions: Architecture, Identity &
secrets, Observability, Security (authz), Resilience, Testing, Packaging/CI,
Readability. This doubles as interview material ("here's how I assess my own work
against a production bar").

---

## 6. Build order

1. **Prereq:** unblock the read replica (firewall + AD admin TF). Already scoped.
2. **Seam:** define `LLMProvider` in `ai-infra-templates`, Claude + OpenAI impls,
   swap test green on both. (Used lightly here, hard in piece 2.)
3. **Retrieval depth:** hybrid + RRF, then rerank stage, then freshness/dedup.
   Eval the rerank on/off delta as you go — measure before claiming.
3b. **Context-assembly policy:** make it explicit and swappable (top-k vs
   rerank-then-top-k vs rerank-then-compress); produce the policy ×
   (accuracy, tokens, latency) comparison table.
4. **API surface:** FastAPI endpoints + Pydantic contracts + structured outputs +
   auth; MCP interface alongside; publish OpenAPI.
5. **Scaling/latency artefacts:** per-stage p-latency under load, autoscale graph,
   token-cost panel. Commit the graphs.
6. **Posture + SCORECARD + README:** compliance-posture section, re-grade the
   scorecard, README opens with the customer problem + the AKS placement in the
   org shape.

---

## 7. Out of scope / explicitly cut (anti-overengineering)

- **No agent loop in this piece.** Retrieval is determinate; an agent here would
  reproduce your 6× negative. The loop lives in piece 2.
- **No Skills here.** Skills are agent-loaded capability modules; this piece has
  no agent surface. Forcing a Skill in would be shoehorning. Skills are a
  first-class deliverable in **piece 2**, anchored to your +168% cost finding
  ("here's what a Skill costs per turn, here's when it's worth it").
- **No kill-switch / runtime-authz here.** Same reason — no agent to govern. The
  primitive + Okta landscape doc live in **piece 2**, where a multi-agent
  workflow touching financial data makes "govern what the agent does once inside"
  a real problem.
- **No AI Foundry.** Dropped — production penetration unverified and not worth the
  build.
- **No thick provider abstraction.** Thin seam only (locked decision).
- **No compliance certification language.** Posture-awareness only.
- **No multi-hop corpus here.** That belongs to piece 2 where the agent wins.
- Do not abstract provider-specific features (caching, structured outputs) behind
  the seam — pass them through as opaque config.

---

## 8. Definition of done

- [ ] Read replica unblocked; query path uses it.
- [ ] `LLMProvider` seam in `ai-infra-templates`; Claude + OpenAI impls; swap test
      green on both arms of the same eval.
- [ ] Hybrid retrieval (BM25 + vector, RRF) live.
- [ ] Rerank stage live; eval shows recall@k and p95 with rerank ON vs OFF.
- [ ] Context-assembly policy explicit and swappable; policy ×
      (accuracy, tokens, latency) comparison table committed.
- [ ] Freshness + content-hash dedup on ingest.
- [ ] FastAPI surface: versioned endpoints, Pydantic contracts, structured
      outputs, auth, published OpenAPI; a real consumer example in the README.
- [ ] MCP interface exposing the same retrieval.
- [ ] Per-stage p50/p95/p99 under load committed as a graph; autoscale curve;
      token-cost-per-query panel.
- [ ] Compliance-posture README section (awareness, non-certification).
- [ ] SCORECARD re-graded against the production bar, baseline→final table.
- [ ] README opens with the customer problem and places the repo in the
      AKS→ACA→Container Apps Jobs org shape.

---

## 9. Standing conventions (apply throughout)

- `uv`; no `load_dotenv()` anywhere; secrets via workload identity → Key Vault.
- `os.environ` reads only in application code.
- Commit style `type(scope): subject` with a *why* body; no commit hashes in docs.
- Shared TF modules referenced from `portfolio-infra` by ref tag, not copied.
- Verify Azure provider/resource versions against live docs before generating.
- Every new capability passes the "what breaks if absent" test before it's built.
