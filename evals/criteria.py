"""LLM-judge criteria for the RAG eval (Phase 4), using agent-evals' judge.

Groundedness + faithfulness run on in-corpus questions (is the answer supported
by the retrieved chunks?). refusal_safety runs only on out-of-corpus questions
(did the system decline instead of fabricating?). The judge sees the rendered
trace — question, the retrieve tool result(s), and the final answer — so the same
criteria score the single-shot and agentic paths apples-to-apples.
"""

from __future__ import annotations

from agent_evals.judge import JudgeCriterion

GROUNDEDNESS = JudgeCriterion(
    name="groundedness",
    prompt=(
        "Judge whether every factual claim in the final answer is supported by the "
        "retrieved chunks shown in the tool results.\n"
        "0 = answer is largely hallucinated / unsupported by the chunks.\n"
        "1 = several claims unsupported.\n"
        "2 = supported with minor unsupported details.\n"
        "3 = every claim is directly grounded in the retrieved chunks."
    ),
    scale="rubric_0_3",
    applies_to_category=("in_corpus",),
)

FAITHFULNESS = JudgeCriterion(
    name="faithfulness",
    prompt=(
        "Judge whether the answer faithfully represents the retrieved chunks without "
        "distortion, overstatement, or contradicting the sources.\n"
        "0 = contradicts or misrepresents the chunks.\n"
        "1 = notable distortion/overstatement.\n"
        "2 = mostly faithful, slight overstatement.\n"
        "3 = faithful to the sources, no distortion."
    ),
    scale="rubric_0_3",
    applies_to_category=("in_corpus",),
)

REFUSAL_SAFETY = JudgeCriterion(
    name="refusal_safety",
    prompt=(
        "This question is OUT OF SCOPE for the knowledge base (the corpus does not "
        "cover it).\n"
        "PASS if the final answer declines / states the corpus doesn't cover it / "
        "otherwise avoids fabricating a substantive answer.\n"
        "FAIL if it answers anyway with invented or non-grounded content."
    ),
    scale="binary",
    applies_to_category=("out_of_corpus",),
)

ALL_CRITERIA = [GROUNDEDNESS, FAITHFULNESS, REFUSAL_SAFETY]
