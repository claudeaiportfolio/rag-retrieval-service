# pgvector

pgvector is an open-source Postgres extension for vector similarity search. It enables storing embedding vectors as a first-class column type and supports approximate nearest neighbor search.

## Supported distance functions

pgvector supports three distance functions:

- L2 distance (`<->`) — Euclidean distance, the default metric.
- Inner product (`<#>`) — Negative inner product.
- Cosine distance (`<=>`) — One minus cosine similarity.

For most embedding models that produce normalised vectors, cosine distance is the most appropriate metric.

## Index types

pgvector ships with two ANN index types:

### HNSW

Hierarchical Navigable Small World creates a multilayer graph. HNSW has better query performance than IVFFlat (in terms of speed-recall tradeoff), but it has slower build times and uses more memory. Building an HNSW index does not require a training step like IVFFlat, so it can be built without any data in the table.

Key tunables:
- `m` — max connections per layer (default 16)
- `ef_construction` — search list size at build time (default 64)
- `ef_search` — search list size at query time

### IVFFlat

Inverted File with Flat compression divides vectors into lists. At query time, only the closest lists are searched. IVFFlat has faster build times and uses less memory than HNSW, but it has lower query performance (in terms of speed-recall tradeoff).

IVFFlat requires training. Before creating the index, the table should have a representative sample of data.

Key tunables:
- `lists` — number of partitions
- `probes` — number of lists to search at query time

## Choosing an index

For under 1M vectors, IVFFlat is usually faster to build and serves well. Beyond that, HNSW's recall-latency tradeoff at large scale tends to be better. Both are worth benchmarking against the actual corpus.

## Filtering

You can combine vector search with traditional filters (`WHERE tenant_id = ...`) using the standard SQL syntax. Approximate index types may return fewer rows than expected when filtered heavily — consider iterative scans or partial indexes for high-cardinality filters.
