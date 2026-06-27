-- Idempotent schema bootstrap. Run after `CREATE EXTENSION vector;`.
CREATE TABLE IF NOT EXISTS chunks (
    id           BIGSERIAL PRIMARY KEY,
    document_id  TEXT        NOT NULL,
    tenant_id    TEXT        NOT NULL,
    source_doc   TEXT        NOT NULL,
    heading_path TEXT        NOT NULL DEFAULT '',
    chunk_index  INTEGER     NOT NULL,
    token_count  INTEGER     NOT NULL,
    text         TEXT        NOT NULL,
    embedding    vector(1536) NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS chunks_tenant_idx
    ON chunks (tenant_id);

CREATE INDEX IF NOT EXISTS chunks_document_idx
    ON chunks (document_id);

-- HNSW index (default). Swap to ivfflat in EXPERIMENTS.md benchmark.
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx
    ON chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
