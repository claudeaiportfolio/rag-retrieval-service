#!/usr/bin/env bash
# Render terraform output values into deployable k8s manifests.
#
# IMPORTANT: this NEVER edits the committed k8s/ sources. It copies them into a
# git-ignored build/k8s/ and substitutes placeholders there, so a real
# identifying value can never end up in a tracked file (enforced by gitleaks).
# Apply the rendered output: `kubectl apply -k build/k8s` (or point your GitOps
# tool at build/k8s / mount identifying config via Key Vault CSI — see Phase 2).
#
# Idempotent. Portable across bash 3.2 (macOS) and 5+ (CI).

set -eo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/k8s"
BUILD="$ROOT/build/k8s"

cd "$ROOT/terraform"
OUT=$(ARM_USE_AZUREAD=true ARM_USE_CLI=true terraform output -json)
cd "$ROOT"

get() { jq -r "$1" <<<"$OUT"; }

AUTH0_DOMAIN="$(az keyvault secret show --vault-name localdevenv --name auth0-domain --query value -o tsv 2>/dev/null || echo '')"
# ACR login server is shared, cluster-level infra (not in this stack's TF state),
# so it comes from the environment. Defaults to the portfolio cluster's ACR.
ACR_LOGIN_SERVER="${ACR_LOGIN_SERVER:-$(az acr list --query '[0].loginServer' -o tsv 2>/dev/null || echo '')}"

# Fresh build dir each run so stale renders never linger.
rm -rf "$BUILD"
mkdir -p "$(dirname "$BUILD")"
cp -R "$SRC" "$BUILD"

# placeholder<TAB>value, one per line. Tabs are safe inside sed replacement values.
PAIRS=$(cat <<EOF
__UPLOAD_API_CLIENT_ID__	$(get '.identity.value.upload_api.client_id')
__EMBEDDING_WORKER_CLIENT_ID__	$(get '.identity.value.embedding_worker.client_id')
__RETRIEVAL_API_CLIENT_ID__	$(get '.identity.value.retrieval_api.client_id')
__MCP_SERVER_CLIENT_ID__	$(get '.identity.value.mcp_server.client_id')
__EMBEDDING_WORKER_PRINCIPAL_NAME__	$(get '.identity.value.embedding_worker.name')
__RETRIEVAL_API_PRINCIPAL_NAME__	$(get '.identity.value.retrieval_api.name')
__AOAI_ENDPOINT__	$(get '.openai.value.endpoint')
__STORAGE_ACCOUNT__	$(get '.storage.value.account_name')
__PG_PRIMARY_FQDN__	$(get '.postgres.value.primary_fqdn')
__PG_REPLICA_FQDN__	$(get '.postgres.value.replica_fqdn')
__ACR_LOGIN_SERVER__	$ACR_LOGIN_SERVER
__AUTH0_DOMAIN__	$AUTH0_DOMAIN
EOF
)

while IFS=$'\t' read -r placeholder value; do
  if [[ -z "$value" || "$value" == "null" ]]; then
    echo "skipping $placeholder — empty value"; continue
  fi
  find "$BUILD" -type f -name '*.yaml' -print0 |
    xargs -0 sed -i.bak "s|${placeholder}|${value}|g"
  echo "rendered $placeholder"
done <<<"$PAIRS"

find "$BUILD" -name '*.bak' -delete

# Fail loudly if any placeholder survived — a missing TF output or env var.
if grep -rnE '__[A-Z_]+__' "$BUILD" >/dev/null 2>&1; then
  echo "ERROR: unrendered placeholders remain in $BUILD:" >&2
  grep -rnE '__[A-Z_]+__' "$BUILD" >&2
  exit 1
fi

echo "done — rendered manifests in $BUILD (git-ignored). Apply with: kubectl apply -k build/k8s"
