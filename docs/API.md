# API surface

One retrieval service, two surfaces for two consumer classes:

- **HTTP (FastAPI)** — how a human-built application (a compliance dashboard, an
  internal tool) consumes retrieval.
- **MCP** — how an *agent* consumes the same retrieval as a tool (e.g. piece 2's
  diligence agent).

Both enforce per-scope Auth0 JWT auth (`query:read` for retrieval, `ingest:write`
for ingest). The full contract is published at [`openapi.json`](openapi.json).

## HTTP — versioned endpoints

### `POST /v1/search` — retrieval only (for agents)

Hybrid (BM25 + vector, RRF) + cross-encoder rerank, **no** answer generation.
Returns the evidence to reason over.

```bash
curl -s https://retrieve.rag.dev.michaelalinks.com/v1/search \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is our current policy on adverse credit?", "top_k": 5}'
```

```jsonc
{
  "chunks": [
    {
      "source_doc": "credit-policy-2026.md",
      "heading_path": "Lending > Adverse credit",
      "text": "Applicants with adverse credit in the last 24 months …",
      "score": 0.0182,
      "created_at": "2026-06-20T11:04:00Z"
    }
  ],
  "hybrid": true,
  "rerank": true
}
```

### `POST /v1/answer` — retrieval + grounded answer (for apps)

Retrieves, assembles the context under the configured policy, and generates one
grounded, **cited** answer. Structured (typed) response — never a free-text blob.

```bash
curl -s https://retrieve.rag.dev.michaelalinks.com/v1/answer \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is our current policy on adverse credit?", "top_k": 8}'
```

```jsonc
{
  "answer": "Applicants with adverse credit within the last 24 months are …",
  "chunks": [ /* the cited evidence, as in /v1/search */ ],
  "model": "gpt-4o-mini",
  "backend": "aoai",
  "assembly_policy": "rerank_then_top_k",
  "context_tokens": 1840,
  "chunks_used": 6
}
```

Per-request overrides (used by the evals to measure the tradeoffs): `hybrid`,
`rerank`, `assembly_policy` (`top_k_by_fused` | `rerank_then_top_k` |
`rerank_then_compress`).

`POST /query` is a **deprecated** alias of `/v1/answer`.

## MCP — same retrieval, agent-facing

The MCP server exposes the same retrieval as tools (Auth0 JWT, per-tool scope):

| tool | scope | returns |
|---|---|---|
| `search_knowledge(query, tenant_id?, top_k?)` | `query:read` | `{chunks}` (retrieval only) |
| `query_knowledge(query, tenant_id?, top_k?)`  | `query:read` | `{answer, chunks}` (composed) |
| `ingest_document(content, source_doc, tenant_id?)` | `ingest:write` | `{document_id}` |

That `search_knowledge` ↔ `/v1/search` and `query_knowledge` ↔ `/v1/answer`
correspondence is deliberate: one service, the right interface for each consumer
class — not "MCP to tick a box".
