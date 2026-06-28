resource "azurerm_resource_group" "this" {
  name     = var.resource_group_name
  location = var.location
  tags     = var.tags
}

locals {
  prefix          = var.name_prefix
  loc_short       = "uks"
  oidc_issuer_url = data.azurerm_kubernetes_cluster.portfolio.oidc_issuer_url
}

# Reusable modules are sourced from the central portfolio-infra library
# (centralise-don't-copy); only this invocation is repo-local.
module "identity" {
  source = "git::https://github.com/claudeaiportfolio/portfolio-infra.git//terraform/modules/identity?ref=tf-modules-v0.1.0"

  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  name_prefix         = local.prefix
  loc_short           = local.loc_short
  oidc_issuer_url     = local.oidc_issuer_url
  tags                = var.tags
}

module "storage" {
  source = "git::https://github.com/claudeaiportfolio/portfolio-infra.git//terraform/modules/storage?ref=tf-modules-v0.1.0"

  resource_group_name      = azurerm_resource_group.this.name
  location                 = azurerm_resource_group.this.location
  name_prefix              = local.prefix
  loc_short                = local.loc_short
  upload_api_principal_id  = module.identity.upload_api.principal_id
  worker_principal_id      = module.identity.embedding_worker.principal_id
  enable_private_endpoints = var.enable_private_endpoints
  tags                     = var.tags
}

module "postgres" {
  source = "git::https://github.com/claudeaiportfolio/portfolio-infra.git//terraform/modules/postgres?ref=tf-modules-v0.1.0"

  resource_group_name      = azurerm_resource_group.this.name
  location                 = azurerm_resource_group.this.location
  name_prefix              = local.prefix
  loc_short                = local.loc_short
  sku_name                 = var.postgres_sku_name
  storage_mb               = var.postgres_storage_mb
  aad_admin_object_id      = var.postgres_aad_admin_object_id
  aad_admin_principal_name = var.postgres_aad_admin_principal_name
  aad_admin_principal_type = var.postgres_aad_admin_principal_type
  ci_admin_object_id       = var.postgres_ci_admin_object_id
  ci_admin_principal_name  = var.postgres_ci_admin_principal_name
  tenant_id                = data.azurerm_client_config.current.tenant_id
  enable_private_endpoints = var.enable_private_endpoints
  tags                     = var.tags

  # Each workload's UAMI is also registered as a Microsoft Entra admin
  # so per-pod tokens authenticate directly against pgvector. Avoids the
  # need for pgaadauth_create_principal helpers that this PG version
  # doesn't expose.
  workload_admins = {
    upload_api       = { object_id = module.identity.upload_api.principal_id, principal_name = module.identity.upload_api.name }
    embedding_worker = { object_id = module.identity.embedding_worker.principal_id, principal_name = module.identity.embedding_worker.name }
    retrieval_api    = { object_id = module.identity.retrieval_api.principal_id, principal_name = module.identity.retrieval_api.name }
    mcp_server       = { object_id = module.identity.mcp_server.principal_id, principal_name = module.identity.mcp_server.name }
  }
}

module "openai" {
  source = "git::https://github.com/claudeaiportfolio/portfolio-infra.git//terraform/modules/openai?ref=tf-modules-v0.1.0"

  resource_group_name      = azurerm_resource_group.this.name
  location                 = azurerm_resource_group.this.location
  name_prefix              = local.prefix
  loc_short                = local.loc_short
  worker_principal_id      = module.identity.embedding_worker.principal_id
  retrieval_principal_id   = module.identity.retrieval_api.principal_id
  embedding_capacity       = var.embedding_model_capacity
  chat_capacity            = var.chat_model_capacity
  enable_private_endpoints = var.enable_private_endpoints
  tags                     = var.tags
}

module "aks_nodepool" {
  source = "git::https://github.com/claudeaiportfolio/portfolio-infra.git//terraform/modules/aks-nodepool?ref=tf-modules-v0.1.0"

  aks_cluster_id = data.azurerm_kubernetes_cluster.portfolio.id
  name_prefix    = local.prefix
  spot_max_price = var.spot_max_price
  tags           = var.tags
}

# --- Shared Redis password ---------------------------------------------------
# RQ runs on a shared self-hosted Redis (installed via the cluster-mgmt repo).
# Generate the password here and store it in the SHARED Key Vault; External
# Secrets Operator syncs it into the redis + ingestion namespaces, so no raw
# secret ever lands in git or a k8s manifest. The KV lives in RG `kubernetes`,
# so the secret survives `az group delete` of this app's resource group.
data "azurerm_key_vault" "shared" {
  name                = "localdevenv"
  resource_group_name = "kubernetes"
}

resource "random_password" "redis" {
  length  = 32
  special = false
}

resource "azurerm_key_vault_secret" "redis_password" {
  name         = "redis-password"
  value        = random_password.redis.result
  key_vault_id = data.azurerm_key_vault.shared.id
}

# The workload UAMIs read app secrets (e.g. the optional Anthropic key) from the
# shared dev Key Vault, which lives in RG `kubernetes` outside this stack's RG.
# Least-privilege: Secrets User (read), not a broader KV role. The app also
# degrades gracefully if this is ever absent (common/config.load_secrets).
resource "azurerm_role_assignment" "workload_kv_secrets" {
  for_each = {
    upload_api       = module.identity.upload_api.principal_id
    embedding_worker = module.identity.embedding_worker.principal_id
    retrieval_api    = module.identity.retrieval_api.principal_id
    mcp_server       = module.identity.mcp_server.principal_id
  }
  scope                = data.azurerm_key_vault.shared.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = each.value
}
