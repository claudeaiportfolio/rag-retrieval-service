# Session notes — overnight build of `rag-ingestion-platform`

End-of-session summary of what landed, where, and why. Written for the
human reading this in the morning. Keep this file in step with reality —
if you re-run any of the deferred steps, append a dated section.

---

## ▶ NEXT SESSION — START HERE (updated 2026-06-21, evening)

**All phases (0–5) done & merged.** Phases 4+5 shipped this session (PR #6):
- **`agent-core`** extracted to `ai-infra-templates` (tag **`agent-core-v0.1.2`**): bounded plan/act/observe
  `AgentLoop`, `MCPClient`, Auth0 M2M, JSONL+OTel tracing, SKILL.md loader. Generalised from snowflake's loop.
- **Phase 5** — `src/rag_agent/`: agentic plan→retrieve→critique→answer loop on agent-core; MCP tool
  **`query_knowledge_agentic`** (scope `query:read`); retrieve tool backed in-process by retrieval-api (no MCP recursion).
- **Phase 4** — `evals/`: `agent-evals[judge]` criteria (groundedness/faithfulness/refusal) + `evals/compare.py`
  (`make eval-compare`) single-shot vs agentic; recall@k stays local (`make eval`). Fixtures expanded (multi-hop + out-of-corpus).
- **LIVE eval ran** (full stack brought up, 20 fixtures). Honest **negative** result in `EVAL_FINDINGS.md`:
  single-shot beats agentic on groundedness (0.98 vs 0.83), faithfulness (0.98 vs 0.81), refusal (1.00 vs 0.75)
  at ~6× lower latency — single-hop corpus doesn't reward agentic; refusal regression on q19 (answered from
  parametric knowledge). Two measurement artifacts caught + fixed (300-char trace truncation → agent-core v0.1.1;
  flaky AOAI GlobalStandard → retrieval retries).

**Stack is TORN DOWN** again to protect the bill. **Full-teardown standard (do this every time, autonomously):**
`make teardown-full` = `az group delete --name rag-platform-uks` **+** `az aks stop` the shared cluster. Stop is
reversible (`az aks start`); **never delete** shared infra (cluster, Key Vault, ACR, DNS, shared UAMIs). Both done
this session: RG deleted, cluster stopped.

**Carry-forward / open items:**
1. **Local `main` divergence:** a stale local-only commit `9fc2ada` (old session-notes) sits on top of old main;
   origin/main is canonical (PR #6 = `a896a33`). Reset local main to origin/main when convenient.
2. **New images not yet deployed:** the worker `with_scheduler=True` fix and `query_knowledge_agentic` are on
   main + built by CI, but the cluster runs the old images. On next bringup, re-apply overlays + **rollout restart**
   (stale pods carry OLD workload-identity client-ids after a TF recreate → `AADSTS700016`).
3. **AOAI soft-delete:** deleting the RG soft-deletes the AOAI account; the next `tf apply` 409s
   (`FlagMustBeSetForRestore`). **Purge first**: `az cognitiveservices account purge --location uksouth
   --resource-group rag-platform-uks --name rag-aoai-uks`, then apply. (Don't pipe apply through `| tail` — it
   masks the non-zero exit.) See memory `[[reference-azure-resource-gotchas]]`.
4. **PG replica firewall still deferred** — retrieval-api was pointed at the PRIMARY for the eval (the replica's
   `AllowAzureServices` rule is a user-owned network decision; the classifier gates opening it).
5. GitOps render-on-sync wiring still TODO (Argo MANUAL sync). See `[[reference-phase2-keda-redis-e2e]]`.

---

## Progress — 2026-06-21: Phase 2 (RQ/Redis + KEDA) shipped & proven LIVE ✅

- **`platform-core[queue]`** package in `ai-infra-templates` (`platform-core-v0.1.0`): TLS-capable Redis conn
  factory + RQ Queue/Worker builders. ruff+mypy+pytest green.
- **rag swap merged** (PR #5): upload-api `queue.enqueue`; embedding-worker = RQ `SimpleWorker`
  (`embedding_worker.tasks.process_document`); config `redis_*`; servicebus module/output deleted; TF generates
  the Redis password into KV; KEDA `redis` ScaledObject; `ExternalSecret` (ESO) syncs the password.
- **Shared Redis** in cluster-mgmt `flux/installs/redis` (official image, least-priv ACL: `rag` app user,
  read-only `keda`; password via ESO). cluster-mgmt PRs #67–#70.
- **LIVE E2E:** brought the stack up; 50-doc burst → KEDA scaled `embedding-worker` **0→1→4→8→10** on
  `LLEN rq:queue:embed-jobs`, drained, **→0** after cooldown. 50 finished / 0 failed.
- **Debugged live (all fixed):** KEDA scaler ACL needs `+@read +eval +eval_ro` (it reads list len via a Lua
  EVAL calling type/exists/llen); Flux reverts live edits (fix via git + reconcile); rag Argo app set to
  **manual sync** because raw `k8s/` carries unrendered placeholders (`InvalidImageName`).
- **PG bootstrapped** (vector ext + `chunks` table/HNSW + grants) as the aad admin. Then **torn down**
  (RG deleted, cluster stopped) to protect the bill — Phases 4+5 live work resumes on next bring-up.
- Full detail + gotchas: memory `[[reference-phase2-keda-redis-e2e]]`.

---

## Progress — 2026-06-20 (PM): TF-module centralisation + Auth0 M2M client ✅

**TF modules centralised (was a centralise-don't-copy violation by the 2026-06-15 scaffold).**
- Moved the 5 reusable modules (`identity`, `storage`, `postgres`, `openai`, `aks-nodepool`) into
  `portfolio-infra/terraform/modules/` (PR #2, merged; tag `tf-modules-v0.1.0`). Verified byte-identical,
  fmt clean, gitleaks clean.
- rag `terraform/main.tf` repointed to `git::…/portfolio-infra//terraform/modules/<name>?ref=tf-modules-v0.1.0`;
  local copies trashed (rag PR #3). State-inert (module addresses unchanged; init fetches from tag, `validate`
  + `plan` pass). `servicebus` kept local — removed in Phase 2.

**Auth0: shared RAG MCP API central in portfolio-infra; M2M client local in this repo.**
- **portfolio-infra owns the RAG MCP API** (resource server `https://rag.dev.michaelalinks.com`, scopes
  `ingest:write`/`query:read`/`admin:reindex`, **15-min `token_lifetime=900`**) so it's reusable across
  solutions (`auth0.tfstate`; portfolio-infra PR #3, merged).
- **This repo keeps ONLY the `rag-m2m` client** — `terraform/auth0/` (own state `rag-auth0.tfstate`, separate
  from the ephemeral infra so the credential survives teardown), invoking the shared module with
  `auth0_apis={}` + the client, granted scopes by audience. KV: `auth0-client-id-rag-m2m`,
  `auth0-client-secret-rag-m2m`. (rag PR #4.)
- **Correction:** I first (wrongly) put the API in this repo; the user had said it belongs in portfolio-infra.
  Fixed non-destructively by `import`ing the live API into `auth0.tfstate` and `state rm`-ing it here — the API
  never went down, tokens kept minting. (Lesson saved to memory: don't deviate from explicit instructions.)
- **GOTCHA fixed:** the `terraform` Auth0 mgmt app lacked `read:client_keys`, so the provider wrote an EMPTY
  client secret to KV (token `access_denied`). Added the scope to the tenant → re-applied → secret persisted.
  Verified end-to-end: token `expires_in=900`, scope `ingest:write query:read admin:reindex`, aud rag.
- **Follow-up:** snowflake-forecasting still owns its own API + `mcp-client` locally; centralise those into
  portfolio-infra to fully realise the shared-API model (commented-out stubs left in portfolio-infra tfvars).

---

## Resumption note — 2026-06-20 (Redis/RQ + hardening + role-alignment rework)

**Why this work exists:** repurposing the repo to present for an Applied AI Engineer
role (Model ML). Full approved plan: `~/.claude/plans/moonlit-doodling-sutherland.md`.
Standing prefs + gotchas: the project memory dir (`MEMORY.md` index).

**Branch:** `feat/redis-rq-hardening`. **Done & committed:**
- `fix(auth)` — per-tool Auth0 scope enforcement wired into MCP tools; `python-jose` → `PyJWT` w/ TTL'd async JWKS. +6 tests.
- `fix(llm)` — reused clients (auto-refresh AAD tokens), `tenacity` backoff, `embed_batch` sub-batching.
- `ruff` clean, 14/14 unit tests pass.
- claude-config PR #1 (centralise-don't-copy convention) **merged**.

**Decisions locked:** RQ on self-hosted Redis · KEDA on list depth · ACL+TLS+KV-CSI auth ·
central `platform-core`/`agent-core` packages in `ai-infra-templates` · identifying config
delivered via Key Vault CSI (Argo syncs `k8s/` from git, so no raw values committed) ·
prod E2E over local stubs (assistant drives cluster lifecycle per memory) · multi-agent
layer = honest agentic planner/critic loop, measured vs single-shot RAG.

**Then infra boundary (needs human input):** Auth0 test tokens for scope E2E;
phase-PR merge policy. (AKS `Failed` state is RESOLVED — cluster is
`Succeeded`/`Stopped`; `az aks start` works, no `az aks update` needed.)

### Progress — 2026-06-20 (no-infra batch: Phase 0.5 + rest of Phase 1) ✅

All static gates green: **ruff clean · mypy clean (18 files) · 20/20 unit tests · gitleaks 0 leaks.**

- **Phase 0.5 — security gates.**
  - `gitleaks` gate added: `.gitleaks.toml` (denylist for service FQDNs, generated
    AOAI/storage names, workload-identity GUIDs, operator name; allowlist for IaC/docs +
    shared KV/public domains), `.pre-commit-config.yaml` (system gitleaks + ruff),
    `.github/workflows/secret-scan.yml` (scans **working tree**, not history, so the
    deferred history-scrub doesn't block CI). Verified it *catches* the old values (6 hits).
    `gitleaks` added to package-installs Brewfile + installed.
  - `render-k8s.sh` rewritten: copies `k8s/` → git-ignored `build/k8s/` and renders **there**;
    never mutates committed sources; fails loudly on any unrendered `__PLACEHOLDER__`.
  - **All identifying values pulled out of committed manifests** → placeholders: both
    configmaps (AOAI/SB/storage/PG endpoints; `PG_USER` dropped — every DB pod overrides it),
    both serviceaccounts (client-id GUIDs), scaledobject (identityId + SB namespace), all four
    deployment image refs (`__ACR_LOGIN_SERVER__`) and the two DB-pod `PG_USER` principals.
  - `pg_bootstrap.py` de-leaked: host/user from env (no defaults), workload principals from
    `WORKLOAD_DB_PRINCIPALS`; `terraform-postdeploy.yml` derives both from TF outputs.
- **Phase 1 — hardening.**
  - Worker: poison messages (Pydantic `ValidationError`) **dead-lettered** immediately;
    transient failures still abandoned/retried. Pure `is_poison()` + tests.
  - `/readyz` added to retrieval-api (DB `SELECT 1`), upload-api (queue/storage config),
    mcp-server (custom_route, unauth). Probes rewired: readiness→`/readyz`, liveness→`/healthz`;
    mcp-server got probes for the first time. (liveness ≠ readiness — see SYSTEM_DESIGN_NOTES §1.)
  - Dropped misleading per-query `index_type` (ANN index is a schema property, not a request knob).
  - Corpus: removed the misleading `fetch_corpus.py` (→ Trash); corpus is now a documented,
    curated+pinned 10-doc set (`corpus/README.md`); `ingest_corpus.py` made recursive + skips README.
  - Type gate: `mypy` added to dev deps + CI + `make typecheck` (fixed 4 real type bugs).
- **New doc:** `docs/SYSTEM_DESIGN_NOTES.md` — interview-oriented reasoning for each decision
  (probes, dead-letter, index_type, secret-gate, pinned corpus).

**Deferred / called out:** git **history** still contains the pre-existing resource names
(low sensitivity — names not live creds; auth is workload-identity/KV). Scrub is optional,
tracked here. GitOps must apply the **rendered** `build/k8s` (or mount identifying config via
KV CSI) rather than raw `k8s/` placeholders — that wiring is Phase 2. Not yet committed.

---

## What works at the end of the session

- **Terraform layer applied** — `rag-platform-uks` RG holds Postgres
  flexible server + read replica + `vector` extension allow-listed,
  AOAI account with `embedding` + `chat` deployments, Service Bus +
  `embed-jobs` queue, storage account + lifecycle, 4 user-assigned
  identities federated to the AKS OIDC issuer, and a spot
  user-nodepool on the shared portfolio cluster.
- **Postgres** — `vector` extension installed; `chunks` table + HNSW
  index created via the `terraform-postdeploy` workflow. The CI UAMI
  and each workload UAMI are registered as Microsoft Entra admins so
  pods can authenticate with their own workload-identity tokens
  (Postgres's `pgaadauth_create_principal*` helpers aren't exposed on
  this server version — multi-admin is the workaround).
- **K8s** — `k8s/` synced into the shared cluster by Argo CD with
  prune + self-heal. KEDA installed via Flux in the cluster-mgmt repo.
- **Images** — `:latest` images for upload-api, embedding-worker,
  retrieval-api and mcp-server pushed to ACR
  (`localacrk8s.azurecr.io/rag-*`).
- **Pods** — `upload-api`, `mcp-server`, `retrieval-api` reconciled by
  Argo. `embedding-worker` scaled to 0 by KEDA (waiting for the first
  message on `embed-jobs`).
- **Evals** — Layer 1 recall@k harness committed (`evals/layer1.py`);
  Layer 2 LLM-judge wired against Claude Haiku via the existing
  `ANTHROPIC_API_KEY` org secret. Workflow at
  `.github/workflows/eval.yml`.
- **KEDA experiment** — `scripts/experiments/keda_burst.py` + workflow
  ready. Dispatch with `gh workflow run experiment.yml -f experiment=keda-burst`.
- **Auth0** — reservation at `https://rag.dev.michaelalinks.com`
  updated on `portfolio-infra` with `ingest:write`, `query:read`,
  `admin:reindex`. Envoy Gateway `SecurityPolicy` enforces JWT on
  the `mcp-server` HTTPRoute.

## Repos touched

| Repo | Commits | Purpose |
|---|---|---|
| `rag-ingestion-platform` | several | terraform, src, k8s, workflows |
| `claudeaiportfolio/Kubernetes` | 2 | KEDA install + Argo Application registration under `flux/installs/` |
| `portfolio-infra` | 1 | Auth0 scopes for the RAG MCP resource server |

(Use `git log --oneline --since=<session start>` on each repo for the
exact set.)

## Resources created

| Type | Name |
|---|---|
| Resource group | `rag-platform-uks` (uksouth) |
| Postgres Flex | `rag-pg-uks` + `rag-pg-replica-uks` |
| AOAI | `rag-aoai-uks` + `embedding` (text-embedding-3-small) + `chat` (gpt-4o-mini) |
| Service Bus | `rag-sb-uks` + queue `embed-jobs` |
| Storage | `ragstuks*` + container `documents` |
| UAMIs | `rag-upload-api-uks`, `rag-embedding-worker-uks`, `rag-retrieval-api-uks`, `rag-mcp-server-uks` |
| AKS node pool | `embedspot` (on `localk8scluster`) |

## Hands-free model in place

| Action | Trigger |
|---|---|
| terraform plan | PR + push to main + `gh workflow run terraform-plan.yml` |
| terraform apply | `gh workflow run terraform-apply.yml -f confirm=apply` |
| terraform postdeploy (CREATE EXTENSION + schema) | `gh workflow run terraform-postdeploy.yml` |
| docker images | push to main on `src/**` → matrix builds → ACR |
| k8s reconciliation | Argo CD app sync (auto + prune + selfHeal) |
| evals | `gh workflow run eval.yml [-f include_judge=true]` (recall@k always; judge = agent-evals compare) |
| experiments | `gh workflow run experiment.yml -f experiment=keda-burst` |

## Deviations from the original plan

- **GitOps engine.** Plan said Argo CD; the cluster's installed Argo CD
  is now wired to drive this stack's `k8s/` directory. KEDA itself moved
  to a Flux HelmRelease in the cluster-mgmt repo because Argo CD can't
  reconcile a Flux CR.
- **Image promotion.** Plan said Flux Image Automation; the cluster has
  the CRD-based `argocd-image-updater-controller` v1.2.x, not the
  annotation-driven `argocd-image-updater`. For v1, deployments use
  `:latest` + `imagePullPolicy: Always`. A follow-up can swap to an
  ImageUpdater CR with digest pinning.
- **Postgres AAD admin.** The pgaadauth_create_principal helper this
  server exposes is the legacy form, not the OID-based one in current
  docs. Workaround: each workload UAMI is registered as a parallel
  Microsoft Entra admin (Postgres supports multiple). Pods authenticate
  with their own UAMI token; `pg_bootstrap.py` runs the plain GRANTs on
  `chunks` once the admin assignments exist.
- **Postgres firewall.** Default policy is deny-all on a fresh
  Flexible Server. Added `AllowAzureServices` so the GitHub Actions
  runner and the AKS egress IPs can both reach the server. A private
  endpoint replaces this when `var.enable_private_endpoints` flips
  (stage 9).

## Deferred (`docs/DEFERRED_DECISIONS.md`-worthy)

- ImageUpdater CR with `digest` strategy on the new images.
- Experiments 2–5 (replica split, HNSW vs IVFFlat, conn exhaustion,
  tenant isolation) — only the KEDA burst experiment runs in v1.
- Private endpoints (handoff stage 9) — TF wired behind
  `var.enable_private_endpoints`, left off for cost.
- Qdrant alternative store — explicitly deferred per handoff §0.

## Cleanup performed at end of session

- `az group delete --name rag-platform-uks --yes --no-wait` —
  dispatched. Drops Postgres + replica + AOAI + Service Bus + storage +
  the 4 workload UAMIs + federated credentials. State remains in
  `localtfsa/tfstate/rag-ingestion-platform.tfstate` so the IaC replays
  cleanly.
- `az aks nodepool delete --name embedspot ...` — dispatched. The spot
  pool was attached to the shared cluster (not inside `rag-platform-uks`),
  so it has to come out separately.
- **AKS cluster state — RESOLVED (2026-06-20).** The shared `localk8scluster`
  was previously in a `Failed` provisioning state (from an earlier nodepool
  modify before `lifecycle.ignore_changes` was set), which made the CLI refuse
  `stop`. The user reconciled it. Verified `az aks show`: **provisioningState
  `Succeeded`, power `Stopped`** (k8s 1.33.12). So `az aks start/stop` now work
  normally and no `az aks update` is needed — the Phase 2 infra blocker is gone.
  Bring the stack up with `az aks start --name localk8scluster --resource-group
  kubernetes` per the standing AKS-lifecycle authorization.

Nothing else was touched: shared UAMIs, storage account, Key Vault, ACR,
DNS zone and the cluster-mgmt repo's pre-existing files are untouched.
The Argo `Application` + `keda` Flux entries added in `flux/installs/`
are kept on purpose so a future `make tf-apply` brings the stack back
without re-running the cluster-mgmt step.

## Re-running from cold

```
make tf-init                                  # remote state already lives
make tf-plan && make tf-apply                  # ~12-15 min
gh workflow run terraform-postdeploy.yml       # pgvector + schema
gh workflow run docker-build.yml               # builds + pushes :latest
az aks start --name localk8scluster --resource-group kubernetes
# Argo will pick the app up on its next reconcile cycle.
```
