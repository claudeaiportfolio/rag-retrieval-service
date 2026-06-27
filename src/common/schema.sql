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

-- Content-hash dedup: the same chunk text re-ingested for a tenant is a no-op
-- (INSERT ... ON CONFLICT DO NOTHING), so re-runs and overlapping documents
-- don't silently duplicate evidence. Added via ALTER so existing tables migrate.
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS content_hash TEXT;

-- Keyword half of hybrid retrieval: a generated tsvector kept in lockstep with
-- `text`, indexed with GIN. `ts_rank_cd` over `websearch_to_tsquery` catches
-- exact-term / clause-ref / code matches that pure vector search misses.
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', text)) STORED;

CREATE INDEX IF NOT EXISTS chunks_tenant_idx
    ON chunks (tenant_id);

CREATE INDEX IF NOT EXISTS chunks_document_idx
    ON chunks (document_id);

-- Dedup key. NULLs (pre-migration rows) stay distinct, so this is safe to add
-- to a populated table; new inserts always carry a hash.
CREATE UNIQUE INDEX IF NOT EXISTS chunks_tenant_hash_uidx
    ON chunks (tenant_id, content_hash);

CREATE INDEX IF NOT EXISTS chunks_tsv_gin_idx
    ON chunks USING gin (tsv);

-- HNSW index (default). Swap to ivfflat in EXPERIMENTS.md benchmark.
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx
    ON chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
