# rag-ingestion-platform

Async document ingestion + RAG query platform on AKS. Queue-decoupled, KEDA-scaled to zero, vector search on Postgres `pgvector`. Exposed to Claude and other agents as an MCP server.

## Architecture (one-liner)

`upload → blob + Redis/RQ queue → KEDA-scaled embedding workers → pgvector` for ingestion. `query → embed → pgvector similarity search → LLM → answer` for retrieval, with an **agentic** plan→retrieve→critique→answer path alongside the single-shot one. OpenTelemetry GenAI spans across both paths.

Full design in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Status

Built and proven live — ingestion → KEDA scale-to-zero → retrieval → eval, end to
end on AKS. The queue is **Redis/RQ** (migrated from Service Bus); both single-shot
and **agentic** RAG paths are exposed via MCP. See the final quality re-grade in
[`docs/SCORECARD.md`](docs/SCORECARD.md) and the SOC 2 / ISO 27001 control mapping in
[`docs/COMPLIANCE.md`](docs/COMPLIANCE.md).

## Layout

```
terraform/         Azure infra (RG, identity, postgres, storage, openai, spot nodepool)
k8s/               Manifests: ingestion, query, platform (KEDA, OTel Collector, ESO)
src/               upload_api, retrieval_api, embedding_worker, mcp_server, rag_agent, common
corpus/            Sample documents (Kubernetes/OTel docs) used for the scaling demos
evals/             recall@k (local) + agent-evals LLM-judge; single-shot vs agentic compare
docs/              ARCHITECTURE, EXPERIMENTS, DEFERRED_DECISIONS, SCORECARD, COMPLIANCE
```

## Conventions

- Python managed with `uv`. No `load_dotenv`; secrets reach pods via Azure Workload Identity → Key Vault → env.
- No service principals. AKS OIDC issuer federates user-assigned managed identities per workload.
- OpenTelemetry GenAI semantic conventions on embedding + LLM spans.
- Terraform `azurerm ~> 4.0`, OIDC auth, remote state in the shared portfolio backend.

## Reuse from sibling repos

- `ai-infra-templates` — `agent-evals` (LLM-judge; recall@k stays local, retrieval-specific), `agent-core` (agentic loop runtime), `platform-core` (Redis/RQ factory) — consumed via pinned git tags
- `snowflake-forecasting` — OTel tracer setup pattern (`src/common/otel.py`)
- `portfolio-infra` — Auth0 resource server reservation at `rag.dev.michaelalinks.com`
