# Context-assembly policy comparison

Policy × (accuracy, tokens, latency) over the in-corpus fixtures.

| policy | groundedness | recall@5 | mean ctx tokens | p50 ms | p95 ms |
|---|---|---|---|---|---|
| top_k_by_fused | 0.98 | 1.00 | 417 | 1405 | 3226 |
| rerank_then_top_k | 0.98 | 1.00 | 395 | 20381 | 21694 |
| rerank_then_compress | 0.96 | 1.00 | 395 | 19425 | 21143 |

_Groundedness is the agent-evals judge (0-1); '—' means no judge key was set. recall@5 is ~constant across policies (same retrieval) — the assembly tradeoff lives in tokens/latency/groundedness, which is the whole point: what goes in the window is a measured decision, not a default._
