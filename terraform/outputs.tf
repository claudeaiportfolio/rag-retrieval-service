output "resource_group_name" {
  value = azurerm_resource_group.this.name
}

output "identity" {
  description = "Client/principal IDs for each workload UAMI. Use the client_id values to annotate ServiceAccounts."
  value = {
    upload_api       = module.identity.upload_api
    embedding_worker = module.identity.embedding_worker
    retrieval_api    = module.identity.retrieval_api
    mcp_server       = module.identity.mcp_server
  }
}

output "postgres" {
  value = {
    primary_fqdn = module.postgres.primary_fqdn
    replica_fqdn = module.postgres.replica_fqdn
    admin_login  = module.postgres.admin_login
  }
}

output "storage" {
  value = {
    account_name   = module.storage.account_name
    container_name = module.storage.container_name
  }
}

output "openai" {
  value = {
    endpoint             = module.openai.endpoint
    embedding_deployment = module.openai.embedding_deployment
    chat_deployment      = module.openai.chat_deployment
  }
}

output "doc_intelligence_endpoint" {
  value = azurerm_cognitive_account.doc_intelligence.endpoint
}

output "aks_oidc_issuer_url" {
  description = "AKS OIDC issuer URL used by federated credentials. Keep for k8s manifest generation."
  value       = data.azurerm_kubernetes_cluster.portfolio.oidc_issuer_url
}
