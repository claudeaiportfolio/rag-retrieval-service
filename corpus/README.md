# Evaluation corpus — curated and version-pinned

These ten Markdown documents are the **source of truth** for ingestion and
evaluation. They are deliberately **committed to the repo and pinned**, not
re-fetched from upstream at run time.

## Why committed, not fetched

Retrieval metrics (recall@k, groundedness) are only comparable across runs if
the underlying documents are held fixed. A corpus that re-downloads from moving
upstream sources would make every eval number ambiguous — you couldn't tell a
retrieval regression from upstream doc churn. Pinning the corpus is the same
discipline as pinning a test fixture or a model version. See
`docs/SYSTEM_DESIGN_NOTES.md §5`.

(An earlier `scripts/fetch_corpus.py` purported to regenerate the corpus but
produced a *different* set of files — different names, nested paths, three docs
missing — and was removed in favour of this committed, documented set.)

## Contents

Each file is a concise, heading-structured summary of a public concept doc, kept
small so the heading-aware chunker has real structure to work with:

| File | Topic | Concept source |
|---|---|---|
| `k8s-namespaces.md`    | Kubernetes namespaces        | kubernetes.io concepts |
| `k8s-deployments.md`   | Kubernetes Deployments       | kubernetes.io concepts |
| `k8s-services.md`      | Kubernetes Services          | kubernetes.io concepts |
| `k8s-configmap.md`     | ConfigMaps                   | kubernetes.io concepts |
| `k8s-hpa.md`           | Horizontal Pod Autoscaling   | kubernetes.io concepts |
| `keda-overview.md`     | KEDA event-driven autoscaling| keda.sh docs |
| `pgvector-overview.md` | pgvector similarity search   | pgvector README |
| `azure-service-bus.md` | Azure Service Bus queues     | Microsoft Learn |
| `otel-collector.md`    | OpenTelemetry Collector      | opentelemetry.io docs |
| `otel-tracing.md`      | Traces & spans               | opentelemetry.io docs |

## Re-baselining

To evolve the corpus, edit/add files here deliberately, bump a corpus version in
the eval findings, and record old vs. new metrics — never let the corpus change
silently underneath a metric.

## Ingesting

`make ingest` (→ `scripts/ingest_corpus.py`) pushes every `*.md` here (recursively,
excluding this README) to upload-api.
