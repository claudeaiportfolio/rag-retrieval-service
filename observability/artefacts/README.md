# Live capture artefacts

Captured from a real bring-up on AKS (2026-06-28): terraform apply (Postgres
primary+replica, AOAI, storage, identity), 4 images via `az acr build`, deployed
to the shared cluster, corpus ingested (10 docs → 55 chunks via KEDA-scaled
workers), then load-tested through `/v1/answer`. Torn down after
(`make teardown-full`).

## `latency.png` / `latency.json` — per-stage latency attribution

The signature "where does the latency go" artefact. Per-stage p50 (ms), from
the `timings_ms` the endpoint returns:

| stage | p50 (ms) | note |
|---|---|---|
| embed | ~200 | AOAI `text-embedding-3-small` |
| **retrieve** | **~17,500** | **hybrid + cross-encoder rerank — dominates** |
| assemble | ~1 | deterministic, model-free |
| generate | ~700–3,000 | AOAI `gpt-4o-mini` |

**The headline finding (honest, and the whole point of per-stage attribution):**
retrieval dominates, and inside it the **cross-encoder reranker is the
bottleneck**. `BAAI/bge-reranker-base` on a **CPU** TEI pod takes ~15–18s per
call (queue ~7s + inference ~3s for the candidate pool) and becomes **unreliable
under concurrency** (connection failures when many requests hit the single CPU
pod at once). The latency is now *attributable* rather than hand-waved — exactly
what separates a measured service from a demo.

**Production recommendation (the senior read):** the reranker needs a **GPU**
node (TEI on GPU is ~10–50× faster) or a lighter reranker, plus replicas behind
the service, before the rerank stage earns its place at production p95. On the
CPU dev pod it does *not* — and the right move is to measure that and say so,
not to claim a number the hardware can't hit. That's the rerank-ON/OFF tradeoff
the eval (`make eval-rerank`) is built to quantify on adequate hardware.

## Reproduce

Bring the stack up (see repo memory / SCORECARD), then:

```bash
RAG_BEARER_TOKEN=$(…auth0 client_credentials…) \
RETRIEVAL_API_URL=https://retrieve.rag.dev.michaelalinks.com \
make loadtest eval-rerank eval-assembly
```
