# Architecture

```
┌────────────┐   POST /documents   ┌──────────────┐   IngestMessage   ┌─────────────┐
│ MCP client │ ──────────────────► │  upload-api  │ ────────────────► │ Service Bus │
│ (Claude)   │   query_knowledge   │  retrieval-  │                   │  embed-jobs │
└────────────┘                     │    api       │                   └──────┬──────┘
       ▲                           └──────┬───────┘                          │ KEDA scaler
       │ MCP (JWT-signed)                 │ search                           │ messageCount
       │                                  │ chunks                           ▼
       │                                  ▼                          ┌──────────────┐
┌────────────┐                     ┌──────────────┐ writes ◄───────► │ embedding-   │
│ mcp-server │ ◄── ClusterIP ────► │ Postgres     │                  │ worker (KEDA │
│ (Auth0     │                     │ pgvector     │                  │ 0→N→0, spot) │
│ JWT gate)  │                     │ primary +    │                  └──────┬───────┘
└─────┬──────┘                     │ replica      │                         │ embed
      │                            └──────────────┘                         │ batch
      ▼                                                                     ▼
┌─────────────┐                                                    ┌────────────────┐
│ Envoy       │                                                    │ AOAI embedding │
│ Gateway     │                                                    │ (workload-id)  │
│ (Auth0      │                                                    └────────────────┘
│ JWT verify) │
└─────────────┘
```

## Identity & secrets

- 4 user-assigned managed identities (`upload-api`, `embedding-worker`,
  `retrieval-api`, `mcp-server`) federated to the AKS OIDC issuer.
- ServiceAccounts annotated with `azure.workload.identity/client-id`.
- Per-workload role assignments: SB Data Sender (upload), SB Data
  Receiver (worker), Storage Blob Data Contributor (upload), Storage
  Blob Data Reader (worker), Cognitive Services OpenAI User (worker +
  retrieval).
- No SAS keys, no service principals, no static secrets in env.
- `anthropic-portfolio-key` reaches the pod from Key Vault only when
  `GENERATION_BACKEND=anthropic` — AOAI path needs no secrets.
- Postgres AAD admins: the human user (for ad-hoc), plus the shared CI
  UAMI (so `terraform-postdeploy` can run hands-free).

## Data flow

1. **Ingest** — MCP `ingest_document` → upload-api HTTP → blob put +
   Service Bus enqueue. Returns `document_id`.
2. **Embed** — KEDA picks up queue depth → scales embedding-worker on
   the spot pool (0 → N) → worker downloads blob, chunks (heading or
   fixed strategy), embeds via AOAI, INSERTs into `chunks (..., embedding
   vector(1536))`. Queue empties → KEDA scales back to 0.
3. **Retrieve** — MCP `query_knowledge` → mcp-server (JWT-verified at
   the Envoy gateway) → retrieval-api ClusterIP → query embedded via
   AOAI → cosine similarity over pgvector → top-k chunks → LLM
   (Anthropic or AOAI, config-switchable) → grounded answer.

## OTel coverage

- `setup_telemetry(service_name)` ships traces + logs over OTLP gRPC to
  the shared in-cluster `otel-collector`. Auto-instrumented httpx and
  FastAPI; manual spans on `chat`, `embed`, `rag_query`,
  `process_document`, `mcp.ingest_document`, `mcp.query_knowledge`.
- GenAI semantic conventions on every model call: `gen_ai.request.model`,
  `gen_ai.provider.name`, `gen_ai.usage.input_tokens`,
  `gen_ai.usage.output_tokens`, plus RAG-specific
  `rag.retrieval.top_k` / `rag.retrieval.scores` / `rag.tenant.id`.

## Storage layout

| Tier | Container / Server | Lifecycle |
|---|---|---|
| Raw documents | `documents/<tenant>/raw/` | tier-to-cool 30 days |
| Processed flag (optional) | `documents/processed/` | tier-to-cool 30 days |
| Vectors | Postgres `chunks` table (HNSW index) | retained until tenant deletion |

## Scaling boundaries

- **Ingest** — embedding-worker scales 0–10 on queue depth. Spot
  nodepool absorbs the burst; on eviction KEDA re-creates the workers
  on the next sample tick.
- **Query** — retrieval-api HPA on CPU 60% (2–8 replicas). MCP server
  scales independently (single replica today; HPA to be added when
  agent load picks up).
- **Postgres** — primary takes embed writes; retrieval-api reads from
  the replica via `PG_REPLICA_HOST`.

## Ingress

Single Envoy `Gateway` (`cluster-issuer-gateway` in
`envoy-gateway-system`) terminates TLS for `*.dev.michaelalinks.com`.

| Hostname | Route |
|---|---|
| `rag.dev.michaelalinks.com` | mcp-server (Auth0 JWT enforced) |
| `ingest.rag.dev.michaelalinks.com` | upload-api (open for v1, behind Auth0 in stage 8 follow-up) |
| `retrieve.rag.dev.michaelalinks.com` | retrieval-api (eval-only; not publicly advertised) |

## Failure modes considered

- **AOAI 429** — wrap call in retry-after handling (TODO).
- **Postgres connection saturation** — PgBouncer experiment in
  `EXPERIMENTS.md` §4. Default pool size = 10 per worker; max workers
  capped at 10 → 100 connections (well below `max_connections=100` on
  GP_Standard_D2ds_v5; tighter on bigger SKUs).
- **Spot eviction mid-batch** — KEDA detects pod loss and rebalances;
  Service Bus message-lock TTL = 5 min, so partially-processed messages
  reappear and are retried by the next pod.
