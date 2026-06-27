# `terraform/auth0` — RAG Auth0 M2M client

A small, **separate** Terraform root that provisions this project's
machine-to-machine (`client_credentials`) Auth0 client and writes its
credentials into the shared Key Vault. It is deliberately split from the main
infra root (`../`) and has its own state (`rag-auth0.tfstate`) so the agent
credential survives the infra teardown/recreate lifecycle untouched.

## What it creates

Via the shared `auth0` module in `portfolio-infra` (centralise-don't-copy — the
module is central, the M2M-client invocation is local):

- `auth0_client` **RAG M2M** — `non_interactive`, `client_credentials` grant.
- `auth0_client_grant` attaching the client to the RAG MCP API
  (`https://rag.dev.michaelalinks.com`) with scopes `ingest:write`, `query:read`,
  `admin:reindex`.
- Key Vault secrets `auth0-client-id-rag-m2m` and `auth0-client-secret-rag-m2m`
  (in `localdevenv`).

The **RAG MCP API resource server** itself (audience, scopes, and the 15-minute
`token_lifetime`) is a **shared contract owned centrally in `portfolio-infra`**
(`terraform/terraform.tfvars`) so it can be reused across solutions. This root
only registers a client and is granted scopes by audience reference.

## Prerequisite — `read:client_keys`

The Auth0 management app the provider authenticates as (the `terraform` app,
creds in Key Vault as `auth0-terraform-client-*`) **must** hold the
`read:client_keys` management-API scope. Without it the provider cannot read a
newly generated `client_secret`, so it silently stores an **empty** value in
state and writes an empty `auth0-client-secret-*` to Key Vault — the client then
fails token requests with `access_denied / Unauthorized`. Grant it once
(Dashboard → the `terraform` app → APIs → Auth0 Management API →
`read:client_keys`), then re-apply so the secret is read and persisted.

## Usage

```bash
make tf-auth0-init     # init (azurerm backend + auth0 provider)
make tf-auth0-plan     # review
make tf-auth0-apply    # create the client; secrets land in Key Vault
```

Auth: local uses `ARM_USE_AZUREAD=true ARM_USE_CLI=true` (your `az login`); the
auth0 provider reads its management-API credentials from Key Vault.

## Consuming the credential

Pull the client_id/secret from Key Vault for token requests:

```bash
az keyvault secret show --vault-name localdevenv --name auth0-client-id-rag-m2m --query value -o tsv
az keyvault secret show --vault-name localdevenv --name auth0-client-secret-rag-m2m --query value -o tsv
```
