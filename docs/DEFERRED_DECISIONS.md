# DEFERRED DECISIONS

Things deliberately not done in the v1 build, with the trigger that
would bring them back into scope.

## Qdrant alternative vector store

**Status.** Out of scope per handoff §0.

**Trigger to revisit.** A benchmark requires distance metrics that
pgvector can't express well (e.g. payload-conditioned filtering at
million-vector scale where pgvector's HNSW + WHERE struggles), or a
demonstrably faster alternative the portfolio can point to.

**Effort.** Helm Qdrant via Flux, new `src/common/vector_stores/` with a
`store: pgvector | qdrant` switch, sweep results into EXPERIMENTS.md.

## Argo Image Updater CR (digest-based)

**Status.** Cluster ships v1.2.x of the controller — CRD-based, not the
annotation flavour my Argo Application targets. v1 ships `:latest` +
`imagePullPolicy: Always`.

**Trigger.** First time we need to roll back to a specific image or pin
to a specific digest in production.

**Effort.** One `ImageUpdater` CR per service in
`flux/installs/rag-retrieval-service/`, plus an `argocd-image-updater`
ServiceAccount with read access to ACR via workload identity.

## Experiments 2-5

Replica split, HNSW vs IVFFlat, connection exhaustion (PgBouncer fix),
tenant isolation are all documented in `docs/EXPERIMENTS.md` as planned
with stubs in `scripts/experiments/`. Only `keda_burst` runs end-to-end.

**Trigger.** Time for the next portfolio iteration / show-and-tell.

## Private endpoints (handoff stage 9)

**Status.** All TF modules accept `var.enable_private_endpoints`. Off by
default to keep dev cost low.

**Trigger.** A residency / SOC2 narrative — flipping the flag and
re-applying surfaces the closed-network story.

## CNPG migration

**Status.** Azure Flexible Server with read replica chosen for the
managed-service portfolio narrative; the cluster also runs CNPG, so a
direct comparison is available later.

**Trigger.** A workshop or post comparing self-hosted CNPG to Azure
Flexible. Replace the TF postgres module with a CNPG `Cluster` CR.

## Postgres read replica firewall + admin

**Status.** Primary `rag-pg-uks` is fully wired (AllowAzureServices +
workload UAMI admins + chunks GRANTs). The read replica
`rag-pg-replica-uks` shares the primary's auth model but the firewall
rule was only added to the primary, so retrieval-api pods (which point
at `PG_REPLICA_HOST` by design) time out on connect.

**Trigger.** Next session — flip back from cleanup, then add:

```hcl
resource "azurerm_postgresql_flexible_server_firewall_rule" "allow_azure_replica" {
  name             = "AllowAzureServices"
  server_id        = azurerm_postgresql_flexible_server.replica.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}
```

…plus a sibling `azurerm_postgresql_flexible_server_active_directory_administrator`
on the replica for each workload UAMI.

**Effort.** ~10 lines of TF + one apply.

## Flux Image Automation (instead of Argo Image Updater)

**Status.** Plan said Flux IA. Cluster has both Flux and Argo running but
the Argo CD Application path I chose for this stack pairs better with
Argo Image Updater. See first deferred item.

**Trigger.** None — this is settled. Listed here only because the
original plan promised Flux IA.
