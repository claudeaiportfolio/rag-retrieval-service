# Live capture artefacts

Captured from a real bring-up on AKS (2026-06-28): `terraform apply` (Postgres
primary+replica, AOAI, storage, workload identities), 4 images via `az acr
build`, deployed to the shared cluster, corpus ingested (10 docs → **55 chunks**
via KEDA-scaled workers), then load-tested and evaluated through `/v1/answer`.
Torn down after (`make teardown-full`). All four artefacts below are real
measured numbers, not illustrations.

## 1. Per-stage latency — `latency.{png,json}`

Where the latency goes, attributed by stage (load test, 40 req, concurrency 4,
**0 errors**):

| stage | p50 (ms) | note |
|---|---|---|
| embed | ~240 | AOAI `text-embedding-3-small` |
| **retrieve** | **~34,700** | hybrid + cross-encoder rerank — **dominates** |
| assemble | ~1 | deterministic, model-free |
| generate | ~1,100 | AOAI `gpt-4o-mini` |

The reranker is the bottleneck, now *attributable* rather than asserted.

## 2. Rerank ON/OFF delta — `rerank_delta.{md,json}`

The headline retrieval-quality artefact (16 in-corpus fixtures):

| metric | rerank OFF | rerank ON | Δ |
|---|---|---|---|
| recall@1 | 0.88 | 0.94 | **+0.06** |
| recall@3 | 1.00 | 1.00 | 0 |
| latency p50 | 1.3s | 18.8s | **+17.5s** |
| latency p95 | 3.6s | 22.5s | +18.9s |

**The defensible read:** the reranker lifts recall@1 by 6 points but costs
~17.5s p50 on a CPU pod. On this small single-hop corpus — where recall@3 is
already perfect — that cost **isn't worth it**, and the measurement says so. On a
larger/noisier corpus, or with a GPU reranker (~10–50× faster), the calculus
flips. That's the whole thesis: *measure whether the reranker earns its p95, don't
assume it.*

## 3. Context-assembly policy — `assembly_table.{md,json}`

Policy × (accuracy, tokens, latency); groundedness via the agent-evals judge:

| policy | groundedness | recall@5 | ctx tokens | p50 (ms) |
|---|---|---|---|---|
| top_k_by_fused | 0.98 | 1.00 | 417 | **1,405** |
| rerank_then_top_k | 0.98 | 1.00 | 395 | 20,381 |
| rerank_then_compress | 0.96 | 1.00 | 395 | 19,425 |

On this corpus the rerank-based policies buy **no** groundedness/recall gain for
~15× latency, and compression slightly *hurt* groundedness (0.96). `top_k_by_fused`
is the right policy here — chosen against a table, not inherited from a framework.

## 4. KEDA autoscale — `autoscale/{replicas.png,timeline.csv,summary.md}`

Ingestion burst (5 replays × 11 docs) → embedding-worker pool **0 → 10 → 0**:
peaked at **10 replicas** on Redis queue depth, drained, settled back to zero,
no human in the loop.

---

## The honest engineering takeaway

The reranker dominates p95 (~17.5s/call) and on this corpus doesn't earn it.
**Production fix:** a GPU reranker (or a lighter cross-encoder) plus the 2 warm
replicas already in the manifest. The point of piece 1 isn't a fast number — it's
*measuring* the tradeoff and being able to say, with data, when a stage is and
isn't worth its cost.

Reproduce: bring the stack up, then
`RAG_BEARER_TOKEN=… RETRIEVAL_API_URL=… make loadtest eval-rerank eval-assembly`
plus `make experiment` for the autoscale curve.
