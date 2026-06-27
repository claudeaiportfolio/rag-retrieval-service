# Compliance posture — SOC 2 / ISO 27001 control mapping

**What this is:** a mapping of the technical controls this platform actually
implements to the SOC 2 Trust Service Criteria (TSC) and ISO/IEC 27001:2022
Annex A controls they support. It's written from a platform-engineering lens for
an AI system that would run inside a regulated (financial) environment.

**What this is *not*:** a claim of certification. SOC 2 and ISO 27001 are
*organizational* attestations — they require policies, risk assessments,
evidence collection, periodic reviews, and an external audit. A repository can
demonstrate the **technical control primitives** those frameworks expect; it
cannot be "SOC 2 compliant" on its own. The honest gaps (the governance and
evidence layer) are listed at the bottom.

Grades and the cross-reference live in [`SCORECARD.md`](SCORECARD.md).

---

## Control mapping (implemented → framework)

| Control area | SOC 2 TSC | ISO 27001:2022 | How this platform implements it | Evidence |
|---|---|---|---|---|
| **Least-privilege access (machine identity)** | CC6.1, CC6.3 | A.5.15, A.5.18, A.8.2, A.8.3 | Auth0 M2M (`client_credentials`) with **per-tool scope enforcement** — `ingest:write` / `query:read` / `admin:reindex` checked on every MCP tool; a `query:read` token cannot call `ingest_document`. | `src/mcp_server/auth.py` (`TOOL_SCOPES`, `authorize`), `src/mcp_server/main.py` |
| **Short-lived credentials** | CC6.1 | A.5.17, A.8.5 | M2M access-token TTL set to **15 minutes** (`token_lifetime = 900`) instead of the 24 h default, shrinking the replay window. | `terraform/auth0/`, [`SCORECARD.md`](SCORECARD.md) |
| **No static cloud credentials** | CC6.1, CC6.6 | A.5.16, A.8.2 | Workload Identity (OIDC federation) for every service + KEDA; managed identities, not keys. Redis uses **ACL-scoped users** (`rag` app user, read-only `keda`). | `terraform/` identity module, `flux/installs/redis/` ACL |
| **Secrets management** | CC6.1 | A.8.12, A.8.24 | Secrets in Azure Key Vault, surfaced via External Secrets Operator; **no secrets in git**; the Anthropic key is passed directly to the SDK, never promoted into `os.environ`. | `src/common/config.py`, `k8s/**/externalsecret.yaml` |
| **Secret-leak prevention (preventive)** | CC6.1, CC7.1 | A.8.12 | Blocking **gitleaks** scan on every push/PR via a shared org action; manifests carry `__PLACEHOLDERS__` rendered into a git-ignored `build/`, never committed. | `.github/workflows/*secret-scan*`, `scripts/render-k8s.sh` |
| **Encryption in transit / at rest** | CC6.7 | A.8.24 | In-cluster TLS to Redis; HTTPS at the Gateway; Azure-managed encryption at rest for Postgres, Storage, Key Vault. | gateway `httproute.yaml` / `securitypolicy.yaml`, Terraform |
| **Network boundary protection** | CC6.6 | A.8.20, A.8.21, A.8.22 | Envoy Gateway with a JWT `SecurityPolicy` on the MCP route; Postgres firewall rules; private-endpoint option in the OpenAI module. | `k8s/query/securitypolicy.yaml`, `terraform/` |
| **Tenant data isolation** | CC6.1 | A.8.10, A.8.11 | Every document and query is scoped by `tenant_id`; retrieval filters by tenant in the SQL `WHERE` clause. | `src/retrieval_api/main.py`, `src/common/models.py` |
| **Change management (SDLC)** | CC8.1 | A.8.31, A.8.32 | All changes via PR; **branch protection** enforced by a blocking security gate; reproducible infra in Terraform; GitOps (Flux/Argo) for cluster state. | PRs #1–#10, `.github/workflows/`, `terraform/` |
| **Secure development & vuln management** | CC7.1 | A.8.8, A.8.25, A.8.28 | Dropped CVE-prone `python-jose` for PyJWT; `ruff` + `mypy` gates; an **advisory LLM security review** in CI that has caught real CRITICALs (e.g. a secret-into-env issue, fixed pre-merge). | `.github/workflows/`, PR #6 review thread |
| **Logging & audit trail** | CC7.2 | A.8.15, A.8.16 | OpenTelemetry tracing with GenAI/MCP semantic conventions; structured logs; **auth-denied** events recorded as span attributes; JSONL agent traces (who/what/when per tool call). | `src/common/otel.py`, `agent_core` tracing |
| **Availability & resilience** | A1.1, A1.2 | A.5.30, A.8.14 | Retries with backoff (`tenacity`), **dead-letter** for poison jobs, DB-touching `/readyz`, KEDA scale-to-zero, HPA, Postgres primary/replica read-split. | `src/embedding_worker/`, `src/*/main.py` probes, `k8s/**/scaledobject.yaml` |
| **Configuration & environment separation** | CC8.1 | A.8.9, A.8.31 | Per-overlay config (Kustomize), IaC-managed, no manual drift; dev/test/prod separable by overlay + RG. | `k8s/`, `terraform/` |

> SOC 2 references use the 2017 TSC (Common Criteria + Availability). ISO references
> use ISO/IEC 27001:2022 Annex A. Mappings are indicative of *supporting* a control,
> not evidence of an audited control operating effectively over a period.

---

## Honest gaps — what a real SOC 2 / ISO 27001 effort still requires

These are **out of scope for a demo repo** but would be needed for an actual
attestation, and naming them is the point:

- **Governance artifacts:** information-security policy set, risk assessment +
  treatment plan, asset inventory, data classification (SOC 2 CC1/CC3; ISO A.5.1, A.5.9, A.5.12).
- **Access reviews:** periodic recertification of who/what has access, joiner-mover-leaver
  process (CC6.2/CC6.3; ISO A.5.18).
- **Log retention & alerting:** centralised, tamper-resistant log storage with a defined
  retention period and a SIEM/alerting pipeline — today traces are emitted, not retained or
  alerted on (CC7.2/CC7.3; ISO A.8.15/A.8.16).
- **Incident response:** documented IR plan, on-call, post-incident review (CC7.3/CC7.4; ISO A.5.24–A.5.27).
- **Business continuity / DR:** backup policy and **tested** restore/failover drills
  (A1.2/A1.3; ISO A.5.29/A.5.30).
- **Vendor / sub-processor management:** review of Anthropic, Azure OpenAI, Auth0 as
  sub-processors (CC9.2; ISO A.5.19–A.5.22).
- **People controls:** security training, background checks (ISO A.6.x) — organizational, not code.
- **Independent testing:** penetration test + continuous-compliance monitoring (e.g. Vanta/Drata)
  feeding evidence to an external auditor.

**Bottom line:** the technical control *primitives* are largely present and map cleanly
to the frameworks; the *governance and evidence* layer is what turns "controls exist in
code" into "controls operate effectively and are audited", and that is an organizational
programme, not a repository.
