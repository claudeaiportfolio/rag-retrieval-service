# Eval findings — single-shot vs agentic RAG

> **Historical artefact (piece 1).** The agentic RAG path this compares against
> was **removed** from the production service in piece 1 — retrieval here is
> deterministic by design (see `SCOPING_1_rag_retrieval_service.md` §0). This
> document records the measurement that justified that decision; it is no longer
> reproducible from this repo (`make eval-compare` and `src/rag_agent/` are gone).
> The multi-hop/agentic line of work moves to piece 2.

**Headline: on this corpus, the agentic loop is strictly worse than single-shot
RAG, at ~6× the latency.** That is a real, measured result — not the answer I
expected, and the more useful one to report.

Run: 20 fixtures (16 in-corpus, 4 out-of-corpus) against the live stack on AKS
(pgvector retrieval, AOAI `text-embedding-3-small` + `gpt-4o-mini`).
Agent: `claude-sonnet-4-5`. Judge: `claude-haiku-4-5-20251001`.
Reproduce with `make eval-compare` (writes `out/compare.json`,
`out/EVAL_FINDINGS.md`).

## Scores

Judge scores normalised 0–1 (groundedness/faithfulness from a 0–3 rubric,
refusal_safety binary). Higher is better.

| criterion | single-shot | agentic | Δ (agentic − single-shot) |
|---|---|---|---|
| groundedness | 0.98 | 0.83 | **−0.15** |
| faithfulness | 0.98 | 0.81 | **−0.17** |
| refusal_safety | 1.00 | 0.75 | **−0.25** |

| cost | single-shot | agentic |
|---|---|---|
| mean latency | **2.4 s** | **14.3 s** (≈6×) |
| retrievals / query | 1.0 | 2.5 |
| model turns / query | 1 | 2.9 |

## Why agentic loses here

1. **The corpus is single-hop.** 19 of 20 questions are answerable from one
   document section. Decomposing a single-hop question into sub-queries adds
   retrievals and tokens without adding evidence, and gives the model more room
   to synthesise beyond the sources — which *lowers* groundedness rather than
   raising it. The single-shot path's tight extractive prompt stays closer to
   the chunks.

2. **Refusal regression — helpfulness beats grounding.** The one refusal miss
   was q19 ("write a Terraform module for an S3 bucket"). The agent correctly
   observed *"the knowledge base doesn't contain information about Terraform"* —
   and then answered anyway from parametric knowledge: *"Let me provide you with
   a Terraform module…"*. Single-shot, with no agency to "be helpful", refused
   cleanly (1.00). The other three out-of-corpus questions (Lambda, Kafka,
   ibuprofen) were refused correctly by both.

3. **Latency is dominated by the extra round-trips**, not the work: ~2.9 model
   turns and 2.5 retrievals per query, each a Sonnet call, for answers a single
   `gpt-4o-mini` pass produced more faithfully.

## When agentic *would* win

The one genuinely multi-hop fixture (q15, "compare how KEDA scales to zero with
how the HPA computes replicas") is exactly the shape agentic is built for: the
agent issued separate sub-queries for KEDA and the HPA and noted where the corpus
was thin on the HPA algorithm. A corpus weighted toward multi-hop / cross-document
synthesis would be the fair test; this one isn't, and a single-hop FAQ should not
pay 6× latency for the privilege. The honest takeaway is **match the retrieval
strategy to the question distribution** — agentic RAG is not a free upgrade.

## Methodology notes (and two artifacts caught)

- Both paths are scored by the **same** `agent-evals` judge over the same trace
  shape: the single-shot path is rendered as a 1-retrieve trace, the agentic path
  emits its own multi-retrieve trace. recall@k stays a separate deterministic
  metric (`make eval`).
- **Artifact 1 — truncated traces.** A first run showed agentic groundedness at
  0.52. That was a measurement bug, not a result: `agent-core` stored only a
  300-char preview of each tool result, so the judge saw far less context for the
  agentic path than for single-shot. Fixed in `agent-core` v0.1.1 (8 KB preview);
  groundedness corrected to 0.83. Worth stating plainly because it nearly became
  a wrong headline.
- **Artifact 2 — flaky dependency.** The freshly-created AOAI **GlobalStandard**
  embedding deployment returned intermittent `DeploymentNotFound` during data-plane
  propagation. The harness now retries retrieval (8 attempts, capped backoff) so a
  flaky dependency degrades a single call instead of aborting the eval.
