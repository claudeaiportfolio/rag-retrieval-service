.PHONY: tf-init tf-fmt tf-validate tf-plan tf-apply tf-destroy \
        tf-auth0-init tf-auth0-plan tf-auth0-apply \
        render-k8s test lint typecheck secret-scan ingest eval \
        experiment smoke cluster-start cluster-stop teardown teardown-full

# AzureAD-backed remote state. The provider itself uses az CLI auth
# (use_cli = true in providers.tf), so the subscription is inherited from the
# active az login — nothing tenant-specific lands in this Makefile.
TF_ENV := ARM_USE_AZUREAD=true ARM_USE_CLI=true
TF_DIR := terraform

tf-init:
	cd $(TF_DIR) && $(TF_ENV) terraform init -input=false

tf-fmt:
	cd $(TF_DIR) && terraform fmt -recursive

tf-validate:
	cd $(TF_DIR) && $(TF_ENV) terraform validate

tf-plan:
	cd $(TF_DIR) && $(TF_ENV) terraform plan -input=false -out=tfplan

tf-apply:
	cd $(TF_DIR) && $(TF_ENV) terraform apply -input=false tfplan

tf-destroy:
	cd $(TF_DIR) && $(TF_ENV) terraform destroy -input=false

# Persistent Auth0 M2M client — separate root + state (rag-auth0.tfstate),
# decoupled from the ephemeral infra stack above.
TF_AUTH0_DIR := terraform/auth0

tf-auth0-init:
	cd $(TF_AUTH0_DIR) && $(TF_ENV) terraform init -input=false

tf-auth0-plan:
	cd $(TF_AUTH0_DIR) && $(TF_ENV) terraform plan -input=false -out=tfplan

tf-auth0-apply:
	cd $(TF_AUTH0_DIR) && $(TF_ENV) terraform apply -input=false tfplan

render-k8s:
	bash scripts/render-k8s.sh

test:
	uv run pytest tests/unit -q

lint:
	uv run ruff check src tests evals scripts

typecheck:
	uv run mypy

secret-scan:
	gitleaks dir . --config .gitleaks.toml --redact --no-banner --exit-code 1

ingest:
	uv run python scripts/ingest_corpus.py

eval:
	uv run python -m evals.layer1

experiment:
	uv run python scripts/experiments/keda_burst.py

smoke:
	uv run python scripts/smoke.py

cluster-start:
	az aks start --name localk8scluster --resource-group kubernetes

cluster-stop:
	az aks stop --name localk8scluster --resource-group kubernetes

teardown:
	az group delete --name rag-platform-uks --yes --no-wait

# Full teardown standard: delete this stack's OWN RG and STOP (never delete) the
# shared cluster. Stop is reversible via `make cluster-start`.
teardown-full: teardown cluster-stop
