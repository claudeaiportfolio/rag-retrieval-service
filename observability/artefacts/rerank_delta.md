# Rerank ON/OFF delta

Recall@k and latency for the in-corpus fixtures, rerank disabled vs enabled.

| metric | rerank OFF | rerank ON | Δ |
|---|---|---|---|
| recall@1 | 0.88 | 0.94 | +0.06 |
| recall@3 | 1.00 | 1.00 | +0.00 |
| recall@5 | 1.00 | 1.00 | +0.00 |
| recall@8 | 1.00 | 1.00 | +0.00 |
| latency p50 (ms) | 1307 | 18792 | +17485 |
| latency p95 (ms) | 3551 | 22492 | +18941 |
| latency mean (ms) | 1691 | 18822 | +17132 |

_n = 16 in-corpus fixtures. The recall gain is what justifies the reranker's added p95 cost; if Δrecall ≈ 0 the reranker isn't earning its latency on this corpus._
