# Observability artefacts

Production observability is the **LGTM stack** (OTel Collector → Grafana Tempo →
Grafana), installed cluster-side via the cluster-management repo. This folder
holds the artefacts that live with the service:

- **grafana-rag-dashboard.json** — three panels, importable into the shared
  Grafana:
  - **Retrieval latency p50/p95/p99** — spanmetrics over the `rag_query` span.
  - **Token cost per query** — `gen_ai.usage.input_tokens` / `output_tokens` on
    the answer-generation span (× $/token = the FinOps view).
  - **KEDA autoscale curve** — Redis queue depth (`LLEN`) vs embedding-worker
    replicas (the proven 0→10→0).

- **Per-stage latency attribution** (embed / retrieve / rerank / generate) is the
  committed `out/latency.png` from `make loadtest`: `/v1/answer` returns
  `timings_ms` per request, which the load test aggregates into per-stage
  p50/p95/p99.

Why per-stage matters: it makes the reranker's added p95 *attributable* — the
"where does the latency go" answer that separates a senior service from a demo,
rather than asserting "it scales".
