# EXPERIMENTS

Runbook for the scaling demonstrations called for by the handoff. Each
experiment is a discrete `workflow_dispatch` on `experiment.yml` that
captures its data as artifact `out/<experiment>/{timeline.csv,summary.md,replicas.png}`.

## 1. KEDA 0 → N → 0 (`keda-burst`)

**What it shows.** Embedding worker pool scales from 0 to N on Redis (RQ)
queue depth (`LLEN`), drains the queue, then idles back to 0 — without a human
in the loop.

**Run.**

```
gh workflow run experiment.yml -f experiment=keda-burst
```

**Knobs.** `BURST_REPLAYS` (default 5), `BURST_SAMPLE_SECONDS` (default 600),
`BURST_SAMPLE_INTERVAL` (default 10s). Tune for the corpus size in use.

**What to look for in the artifact.**
- Initial replica count: 0 (the deployment.spec.replicas is 0, KEDA owns scale).
- Within ~30 s of the flood: replicas activate (1 → N).
- Plateau: replicas track `messageCount / 5` per the ScaledObject.
- After ~`cooldownPeriod` (120 s) of empty queue: replicas drop back to 0.

`out/keda_burst/replicas.png` is the headline chart.

## 2. Read/write split (`replica-split`) — planned

Generates concurrent ingestion (writes → primary) and query load (reads →
replica). Snapshots `pg_stat_database` on both servers to demonstrate the
split. Stub script lives at `scripts/experiments/replica_split.py` —
populate when needed.

## 3. HNSW vs IVFFlat (`index-bench`) — planned

Bulk-ingests, builds both index variants, sweeps recall@k + p95 query
latency at corpus sizes 1k / 10k / 100k chunks. Captures Layer-1 recall
deltas alongside latency to show the speed-recall tradeoff.

## 4. Connection exhaustion → PgBouncer (`conn-exhaustion`) — planned

Scales `embedding-worker` past Postgres `max_connections`. Captures the
failure, then re-runs with PgBouncer in front and demonstrates recovery.

## 5. Tenant isolation (`tenant-isolation`) — planned

Compares per-tenant `WHERE tenant_id = ...` over a shared HNSW index
against a collection-per-tenant approach. Layer-1 recall + latency at
varying tenant counts.

---

Experiments 2-5 ship as stubs in `scripts/experiments/` with a `# TODO`
marker; KEDA burst (the headline chart) is the v1 deliverable.
