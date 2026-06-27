# HANDOFF — `rag-ingestion-platform`

Greenfield build. Async document ingestion + RAG query platform on AKS,
queue-decoupled, KEDA-scaled. This is a portfolio Tier-3 piece demonstrating
RAG, vector DBs, DB scaling, and message queues as one coherent system. It
reuses patterns and packages from the existing repos — read the "Reuse"
section before writing anything new.

---

## 0. Pre-flight

Before writing code:

1. Confirm provider versions. `azurerm` and the AzureRM Function-App-style
   resources move fast and training data is stale. For any Azure resource
   you generate, fetch current docs first — same discipline as
   `terraform-skill-harness`. Raw provider docs live at
   `https://raw.githubusercontent.com/hashicorp/terraform-provider-azurerm/main/website/docs/r/{resource}.html.markdown`.
   Do NOT trust `registry.terraform.io` over plain HTTP — it serves a JS
   shell.
2. Confirm KEDA `azure-servicebus` scaler auth shape against current KEDA
   docs — the `TriggerAuthentication` + workload identity wiring is the
   part most likely to be stale.
3. `uv` for Python, not pip/poetry. Mirror `agent-evals` packaging.

If a version or resource name surprises you, stop and ask. Don't generate
from memory.

---

## 1. What we're building

Two decoupled paths on one AKS cluster:

- **Ingestion (async):** `upload-api` accepts docs → blob storage + Service
  Bus message → KEDA-scaled `embedding-worker` pool chunks, embeds, writes
  vectors to pgvector. Scales 0→N→0 on queue depth. This is the centrepiece.
- **Query (sync):** `retrieval-api` embeds query → pgvector similarity
  search + rerank → LLM → response. Stateless, HPA on RPS.

OTel GenAI spans across both paths, same convention as the agent loop in
`snowflake-forecasting`.

Full architecture is in `docs/ARCHITECTURE.md` (you'll write it — section 6).

---

## 2. Repo layout

```
rag-ingestion-platform/
├── README.md
├── pyproject.toml              # uv-managed
├── Makefile                    # eval + deploy + local targets
├── terraform/
│   ├── main.tf
│   ├── backend.tf              # remote state, see §3
│   ├── variables.tf
│   ├── outputs.tf
│   └── modules/
│       ├── aks/
│       ├── postgres/           # Flexible Server + pgvector
│       ├── servicebus/         # queue + DLQ
│       ├── storage/            # blob, lifecycle policy
│       └── identity/           # workload identity federation
├── k8s/
│   ├── ingestion/              # upload-api, embedding-worker, ScaledObject
│   ├── query/                  # retrieval-api, service, ingress
│   └── platform/               # keda, otel-collector, csi-driver
├── src/
│   ├── upload_api/
│   ├── retrieval_api/
│   ├── embedding_worker/
│   └── common/                 # otel setup, blob/sb clients, chunking
├── corpus/                     # sample docs to ingest, see §5
├── evals/                      # retrieval quality harness, see §7
└── docs/
    ├── ARCHITECTURE.md
    ├── EXPERIMENTS.md          # the scaling demos, runbook style
    └── DEFERRED_DECISIONS.md
```

---

## 3. Terraform

Remote state backend — use the existing portfolio storage account:

```
subscription: <see AZURE_SUBSCRIPTION_ID org secret>
resource group: claudeaiportfolio
storage account: localtfsa
container: tfstate
key: rag-ingestion-platform.tfstate
auth: AzureAD (use_azuread_storage_account = true), no shared keys
```

Module notes:

- **`identity/`** — Workload Identity federation. AKS OIDC issuer →
  user-assigned managed identities for: embedding-worker (Service Bus
  receive + Storage blob + Azure OpenAI), retrieval-api (Postgres + Azure
  OpenAI), upload-api (Service Bus send + Storage blob). No service
  principals, no connection strings. This is the "federated service
  accounts" story.
- **`postgres/`** — Flexible Server, General Purpose tier so read
  replicas are available. Enable the `vector` extension via
  `azurerm_postgresql_flexible_server_configuration` (`azure.extensions`).
  Provision one read replica — the read/write split is a demo artifact,
  not incidental.
- **`servicebus/`** — Standard tier is fine. One queue, DLQ is built in
  (set `max_delivery_count` and `dead_lettering_on_message_expiration`).
  Surface the queue name + namespace as outputs for the ScaledObject.
- **`storage/`** — one container, lifecycle rule tiering `processed/`
  blobs to cool after N days.
- Private endpoints behind a `var.enable_private_endpoints` flag (default
  false for cost; flip on for the residency story).

Confirm `azurerm_postgresql_flexible_server` replica and extension argument
names against current docs before writing — do not assume.

---

## 4. Kubernetes

Namespaces: `ingestion`, `query`, `platform`.

**The load-bearing piece — KEDA ScaledObject** (`k8s/ingestion/`):

- `embedding-worker` Deployment, `minReplicaCount: 0`.
- `ScaledObject` with `azure-servicebus` trigger on `messageCount`.
- Set `activationMessageCount` so a single straggler doesn't wake the pool.
- Tune `cooldownPeriod` so workers don't thrash.
- `TriggerAuthentication` via workload identity — NOT a connection string.
  This wiring is the thing most likely to be stale in your training data;
  verify it.
- Schedule workers on a spot nodepool (taint + toleration) — they're
  interruptible and KEDA handles restarts.

`retrieval-api` (`k8s/query/`): Deployment + Service + ingress, HPA on
CPU/RPS, stateless, multiple replicas.

`platform/`: KEDA operator, OTel Collector (Deployment), Secrets Store CSI
driver.

---

## 5. Corpus

Ship a sample corpus in `corpus/` so the demo is self-contained and the
queue actually backs up. Use Kubernetes/OTel docs (markdown,
heading-structured, on-brand, and you'll know whether retrieval returns
the right section). A few thousand chunks across mixed doc sizes — enough
to make KEDA scale visibly without a real bill.

Chunking: implement both fixed-size and recursive/heading-aware in
`src/common/chunking.py`, selectable by config. Store chunk metadata as
Postgres columns alongside the vector: `source_doc`, `heading_path`,
`token_count`, `tenant_id`. That metadata powers filtered search and the
tenant-isolation story.

---

## 6. Code conventions (inherited — do not deviate)

- `os.environ` only. No `load_dotenv()`. Secrets arrive via federated
  identity → Key Vault → injected env vars.
- No service principals anywhere.
- OTel GenAI semantic conventions on embedding + LLM spans — token counts,
  model, latency, retrieval scores as span attributes. Reuse the tracer
  setup pattern from `snowflake-forecasting` (`agent/loop.py` tracing);
  lift it into `src/common/otel.py`.
- Commit style: `type(scope): subject` with a substantive body explaining
  *why*, not what.
- Pre-commit must pass (Terraform fmt at minimum).

---

## 7. Evals — reuse `agent-evals`

Pull in `ai-infra-templates/agent-evals` (v0.2.0) as the eval framework.
Don't rebuild it. The two-layer architecture applies directly:

- **Layer 1 (deterministic):** recall@k against a labelled
  query→expected-chunk set. Does retrieval return the known-correct
  section? Index-param and chunk-strategy sweeps go here.
- **Layer 2 (LLM-judge):** answer faithfulness / groundedness — does the
  generated answer actually follow from retrieved context, or hallucinate?

`Makefile` targets mirroring the snowflake repo: `eval`,
`eval-with-judge`, `populate-findings`. Findings land in `docs/` with real
numbers, same as `EVAL_FINDINGS.md`.

---

## 8. The scaling demos (`docs/EXPERIMENTS.md`)

Runbook style, like the snowflake `EXPERIMENTS.md`. Each is a
screenshot/graph you can show in an interview:

1. **KEDA 0→N→0** — bulk-upload the corpus, watch worker count track queue
   depth. The headline graph.
2. **Read/write split** — replica serves query embeddings-search load
   while primary takes ingestion writes. Show pg_stat.
3. **HNSW vs IVFFlat** — recall@k and p95 latency as corpus grows.
   Layer 1 eval drives this.
4. **Connection exhaustion** — scale workers out until they exhaust
   Postgres connections, then add PgBouncer and fix it. A real induced
   failure, fixed on camera.
5. **Tenant isolation** — metadata-filtered shared index vs
   collection-per-tenant.

---

## 9. Build order

Vertical slice first, scaling pieces after:

1. Terraform: state backend + identity module + one nodepool.
   `plan`/`apply` clean.
2. Postgres module with pgvector enabled, `vector` extension confirmed
   live.
3. Service Bus + storage modules.
4. `common/`: otel, clients, chunking.
5. `upload-api` → blob + SB publish. Verify a message lands.
6. `embedding-worker` consuming, embedding, writing one vector. End-to-end
   one doc.
7. KEDA ScaledObject — confirm 0→1 on a message, back to 0.
8. `retrieval-api` — query → search → LLM. Vertical slice done.
9. Bulk-ingest corpus, wire evals, run the experiments in §8.
10. Private endpoints + residency hardening (flag-gated, last).

Stop after step 8 is green and confirm the slice before building out §8.

---

## Open questions for the human

- Generation model: Azure OpenAI in-region (clean residency story) or
  Anthropic for generation + Azure OpenAI embeddings only? Affects the
  identity module and the residency framing.
- Service Bus vs NATS JetStream — managed (simpler, Azure-native KEDA
  scaler) or self-hosted on AKS (more K8s-native, more to maintain).
  Default assumption: Service Bus.
- Qdrant comparison in scope, or pgvector only for v1? Default: pgvector
  only, Qdrant deferred to `DEFERRED_DECISIONS.md`.

---

*Original brief delivered via claude.ai handoff. Resolutions to the open
questions and deviations from the build order are captured in
`docs/SESSION_NOTES.md` and `docs/DEFERRED_DECISIONS.md`.*
