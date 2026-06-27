# rag-ingestion-platform — final re-grade scorecard (post-rework)

Re-grade of the final state against the **same dimensions** as the 2026-06-20
baseline review, so the before/after is apples-to-apples. Baseline preserved in
`rag-original-review-scorecard.md`.

**Grading lens (unchanged):** *"what I'd expect to pass review at a company
running this in production"* — not the (already-strong) portfolio bar.

## Overall: B+ → **A−**  (~75–80% → ~90% of the way to production)

The baseline's verdict was "architecture is production-grade; what's missing is
the unglamorous hardening — retries, a couple of real security gaps, test depth."
**That hardening is now done**, and on top of it the rework added the role-headline
capabilities (eval-driven judgment, an agentic layer, Redis/RQ + KEDA) that the
original repo didn't have. What keeps it from a clean A is operational, not
architectural: the latest images aren't redeployed, CI still has no automated
integration tests, and GitOps is on manual sync.

## Re-grade — same dimensions as baseline

Same `Dimension | Grade | Note` shape as the baseline, with the baseline grade
kept inline so the movement is visible at a glance.

| Dimension | Grade (was → now) | Note (now) |
|---|---|---|
| Architecture / decoupling | A → **A** | Clean async preserved through the SB→RQ swap and the added agentic path; agent runtime extracted to a shared package. |
| Identity & secrets | A− → **A** | Hardcoded UUID gone (placeholders → git-ignored `build/`); Auth0 M2M, 15-min TTL; secret passed directly, never via `os.environ` (a gate-caught CRITICAL, fixed). |
| Observability | A → **A** | GenAI/MCP semconv spans + JSONL traces that the eval suite consumes; non-fatal setup. (Instrumentation only — no live dashboard this session.) |
| Security (authz) | C → **A−** | Per-tool scope enforcement wired + enforced (PyJWT, `python-jose` dropped, JWKS TTL), incl. the new agentic tool; two further review CRITICALs fixed. Minus: wrong-scope rejection not re-verified live this session. |
| Resilience / error handling | C+ → **A−** | `tenacity` on model calls, dead-letter for poison jobs, DB-touching `/readyz`, batch splitting, RQ `Retry`. Minus: `Retry` was inert without `work(with_scheduler=True)` — fixed in code, not yet redeployed. |
| Testing | C+ → **B** | `mypy` CI gate; 25 unit tests incl. agent retrieve-tool + auth-scope logic; a real live E2E (ingest → KEDA → retrieve → eval). Minus: no automated integration tests in CI (deliberate prod-E2E-over-stubs). |
| Packaging / CI / Docker | B+ → **A−** | centralise-don't-copy realised — `platform-core` / `agent-core` (v0.1.2) / `agent-evals` via pinned tags; org-wide shared security action; 4 image builds + test + blocking secret-scan; Docker lock fallback removed. |
| Readability / style | A → **A** | ruff + mypy clean across 21 source files; consistent, typed, well-commented. |
| Compliance posture (SOC 2 / ISO 27001) † | — → **B** | Strong control *primitives* — per-tool least-privilege scope enforcement, 15-min M2M tokens, Key Vault secrets + blocking leak scan, TLS, PR/IaC change management, OTel audit trails, retries/dead-letter/HA — mapped to SOC 2 CC and ISO 27001 Annex A. It's an unaudited demo, so the governance/evidence layer (policies, log retention, access reviews, DR drills, pen test) is out of scope. Full mapping: [`COMPLIANCE.md`](COMPLIANCE.md). |

† New dimension — not assessed in the original baseline; added for the regulated/fintech context of the target role.

## New capabilities (role headline — not gradeable at baseline, didn't exist)

| Capability | Grade | Evidence |
|---|---|---|
| LLM evaluation (accuracy / safety) | **A** | recall@k (deterministic) + `agent-evals` judge (groundedness / faithfulness / refusal); **live** single-shot-vs-agentic numbers in `EVAL_FINDINGS.md`; caught + corrected two measurement artifacts mid-run. The eval-driven *judgment* (incl. reporting a negative result honestly) is the strongest signal for the role. |
| Multi-agent / agentic RAG | **B+** | `rag_agent` plan→retrieve→critique→answer on `agent-core`; MCP tool `query_knowledge_agentic`. Built and **measured** — it underperformed single-shot on this single-hop corpus (0.83 vs 0.98 groundedness, ~6× latency). Built+measured+honest > built+hyped; the corpus not favouring agentic is a fair limitation, not a defect. |
| Background workers / RQ / Redis + KEDA | **A** | Service Bus → RQ on self-hosted Redis (ACL-scoped, ESO secrets); **live** KEDA scale-to-zero 0→10→0 on list depth (50 jobs, 0 failed). Literal JD bullets. |
| Reuse / packaging hygiene | **A−** | Three shared packages + central TF modules + a shared security action; real consumption via pinned git tags, not copy-paste. |

## Baseline gaps — all closed

1. Dead per-tool scope enforcement → **wired + enforced** (PyJWT). ✅
2. `python-jose` CVEs / no-TTL JWKS / sync httpx → **PyJWT + TTL**. ✅
3. Hardcoded MI client_id in `scaledobject.yaml` → **placeholder-rendered**. ✅
4. No model-call resilience / per-call clients / no batch limits → **tenacity + batching**. ✅
5. Portfolio-level test depth, no type gate → **mypy gate + broader units + live E2E**. ✅
6. Liveness-only health, no dead-letter, unused `index_type`, Docker lock fallback → **all fixed**. ✅

## Remaining gaps to a clean A (production-ready)

- **Redeploy** the latest images — the `with_scheduler` fix and `query_knowledge_agentic`
  are on `main` + built by CI but the (now torn-down) cluster ran older images.
- **Automated integration tests in CI** — currently relies on a manually-driven live E2E.
- **GitOps render-on-sync** — the rag Argo app is on manual sync (placeholder rendering).
- **Live performance monitoring** — OTel is wired; no dashboard/SLO artifact shown.
- **Agentic value** — needs a genuinely multi-hop corpus to show where the loop earns its
  latency; the current finding is "don't pay 6× for single-hop", which is itself the right call.

---
_Re-graded 2026-06-21 against `rag-original-review-scorecard.md`. Live evidence in
`EVAL_FINDINGS.md`; build history in PRs #1–#8._
