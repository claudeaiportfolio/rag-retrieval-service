# System-design notes — production-maturity decisions worth reasoning through

This is a study companion, not API docs. Each entry is a real decision made in
this repo, written the way you'd want to *talk through it in an interview*:
the symptom, the wrong-but-tempting fix, the trade-off, and the rule of thumb.
`ARCHITECTURE.md` says *what the system is*; this says *why these choices*.

The format is deliberate: **Problem → Naive answer → Why it bites → What we did
→ Generalisable principle → "If they push back…"**. The last line is the
follow-up an interviewer asks to see if you actually understand it.

---

## 1. Liveness vs. readiness probes are not the same check

**Problem.** Kubernetes wants to know about a pod's health. There are two probe
types, `livenessProbe` and `readinessProbe`. It's tempting to point both at one
`/healthz`.

**Naive answer.** "Add a `/healthz` that returns 200 and wire both probes to it."

**Why it bites.** The two probes have *opposite* failure semantics:
- **Liveness** failure → kubelet **restarts the container**. It means "this
  process is wedged; kill it."
- **Readiness** failure → kubelet **removes the pod from the Service's
  endpoints** but leaves it running. It means "don't send me traffic yet."

If your one health check pings the database and you wire it to **liveness**,
then a 5-second Postgres blip **restarts every pod** — converting a transient
dependency hiccup into a cluster-wide crash-loop right when the DB is already
struggling. That's a self-inflicted outage amplifier.

**What we did.**
- `/healthz` (liveness): cheap, in-process, touches **no** dependency.
- `/readyz` (readiness): proves the pod can actually do its job —
  retrieval-api runs `SELECT 1` on its connection pool; upload-api checks its
  queue + blob config is present; mcp-server checks its downstream URLs.
- A DB blip now only **drains traffic** from affected pods; they keep running
  and rejoin rotation when the DB recovers. No restart storm.

**Principle.** *Liveness = "am I broken?" (restart). Readiness = "should I get
traffic?" (drain).* Readiness may depend on downstreams; liveness must not.

**If they push back:** *"What about startup time / slow dependency on boot?"* →
that's the third probe, `startupProbe`, which gates the other two until the app
has finished initialising — so a slow cold start doesn't trip liveness.

---

## 2. Poison messages: dead-letter vs. retry (queue worker)

**Problem.** A background worker pulls messages off a queue, does work, and acks.
What do you do when processing throws?

**Naive answer.** "Catch the exception and `abandon` the message so it gets
retried." (Original code did exactly this for *every* exception.)

**Why it bites.** Failures split into two kinds:
- **Transient** — blob storage 503, DB connection reset, an embedding-API 429.
  These *can* succeed on retry. Abandon-and-retry is correct.
- **Poison** — the message body is malformed / fails schema validation. It will
  fail **every single time**. Abandoning it just rebounds it onto the queue
  forever: an infinite redelivery loop that burns the worker and can stall the
  whole queue behind one bad message.

**What we did.** Classify the failure and branch:
- Poison (Pydantic `ValidationError`) → **dead-letter immediately** with a
  reason. The message is parked on a dead-letter queue for inspection, not
  retried.
- Everything else → abandon → retry (the broker's redelivery/backoff handles it).

The decision is a one-line pure function `is_poison(exc)` so it's unit-testable
without standing up a real broker.

**Principle.** *Retries are only valid for failures that retrying can fix.*
Always separate "the world is temporarily unavailable" from "this input is
permanently invalid," and give the second one a dead-letter path.

**If they push back:** *"What stops a transient failure from retrying forever?"*
→ a max-delivery-count on the queue (or `rq.Retry(max=…)` when this moves to
Redis/RQ in Phase 2): after N transient attempts the broker *also* dead-letters
it, so even mis-classified failures have a ceiling. Dead-lettering is the
backstop; idempotent processing is what makes retries safe in the first place.

---

## 3. An API field that pretends to be a knob (per-query `index_type`)

**Problem.** The query API exposed `index_type: "hnsw" | "ivfflat"` per request,
implying a caller could choose the vector index at query time.

**Why it bites.** That's not how pgvector (or most ANN indexes) work. The index
is a property of the **table/column** — you build *one* HNSW or IVFFlat index on
the embedding column, once. At query time Postgres's planner just uses whatever
index exists for the `<=>` distance operator. The request field selected
*nothing*; it was decorative, and worse, *misleading* — it suggests a capability
the system doesn't have, which is how bad assumptions get baked into clients.

**What we did.** Removed the field from the request model. The retrieval span now
records the **actually-configured** index (`settings.index_type`) so traces still
tell you which index served the query — that's real, the per-request choice was
not.

**Principle.** *Don't expose configuration as if it were a parameter.* If a knob
can't actually change behaviour, removing it is a feature: smaller API surface,
no false mental model. HNSW vs. IVFFlat is a *deployment/experiment* decision
(recall vs. build-time vs. memory), measured offline — not a per-call toggle.

**If they push back:** *"How would you actually compare HNSW vs. IVFFlat then?"*
→ as an experiment: build each index on the same corpus, run the recall@k eval
harness against both, compare recall and p50/p99 latency. It's an A/B on the
*index*, not a request flag.

---

## 4. Secret hygiene as a *gate*, not a habit (defense in depth)

**Problem.** A public repo committed real identifying values into k8s
configmaps and a render script (AOAI endpoint, storage account, Postgres FQDNs,
the operator's name as `PG_USER`, workload-identity client-id GUIDs). "Just
remember not to commit secrets" had already failed — the values were *in git*.

**Naive answer.** "Be careful next time / do a code review."

**Why it bites.** Attention is not a control. A reviewer who's tired misses it
once and it's public forever (and in git history). The render script *mutated
the committed manifests in place*, so running it and committing the result
leaked values **by design** — the happy path produced the leak.

**What we did — make the leak structurally impossible, then enforce it:**
1. **Committed manifests hold only `__PLACEHOLDERS__`.** Real values never live
   in tracked files.
2. **`render-k8s.sh` renders into a git-ignored `build/`** instead of editing
   committed sources. The thing that fills in real values *cannot* dirty a
   tracked file, so there's nothing to accidentally commit.
3. **A `gitleaks` pre-commit hook + CI job** with a project denylist (resource
   patterns, storage/FQDN regexes, the operator's name) **fails the commit /
   the build** if a matching value reappears.

That's three layers: the value isn't there (1), the tool that knows it can't
write where git looks (2), and a mechanical check rejects it if it slips (3).

**Principle.** *Encode a hard standard as an executable gate, and fix the
mechanism that made violating it the easy path.* A control you have to remember
isn't a control. Prefer "impossible" over "discouraged."

**If they push back:** *"The repo is public and the history still has the old
values — isn't the gate theatre?"* → no: the leaked items are resource *names*,
not live credentials (auth is workload-identity / Key Vault, no static secrets),
so the residual risk is reconnaissance, not compromise. The gate stops
*regression*; a history scrub is a separate, lower-priority cleanup that's
documented in `SESSION_NOTES.md`. Knowing which leaks are credentials vs. names —
and triaging accordingly — is the actual skill.

---

## 5. Reproducible eval corpus: curated-and-pinned vs. fetched-fresh

**Problem.** A `fetch_corpus.py` script claimed to (re)build the eval corpus by
downloading upstream docs, but it produced *different* files than the committed
corpus (different names, nested paths, three docs missing), and the ingest step
globbed a flat layout the fetch never wrote. The "reproducible" corpus wasn't
reproducible.

**Why it matters for evals.** If your corpus is re-fetched from moving upstream
sources, your eval numbers aren't comparable across runs — recall@k drifts
because the *documents* changed, not because your retrieval changed. You can't
tell a regression from upstream churn.

**What we did / the trade-off.** Treat the corpus as a **curated, version-pinned
artifact committed to the repo** — the source of truth — and document its
provenance. A stable corpus is the *right* call for an eval baseline; a
self-updating corpus is the wrong one. (The misleading fetch script is removed
in favour of the committed corpus + documented provenance.)

**Principle.** *Evaluation inputs must be pinned.* Reproducibility of a
measurement requires holding the data fixed; "freshness" is the enemy of
comparability. Same reasoning as pinning a test fixture or a model version.

**If they push back:** *"How do you keep a pinned corpus from going stale?"* →
version it explicitly (corpus v1, v2…) and re-baseline deliberately when you bump
it, recording both numbers. The point isn't *never* update — it's *never update
silently underneath a metric*.

---

_Add new entries as decisions land (Redis/RQ queue semantics, KEDA scale-to-zero
on list depth, agentic-vs-single-shot retrieval eval comparison)._
