# Provisions ONLY this solution's M2M client via the shared auth0 module
# (centralise-don't-copy — the module lives in portfolio-infra). The RAG MCP API
# resource server (audience, scopes, 15-min token TTL) is a SHARED contract owned
# centrally in portfolio-infra so it can be reused across solutions; here we just
# register a client_credentials app and are granted the scopes by audience
# reference. The generated client_id + secret are written to Key Vault.
module "auth0" {
  source = "git::https://github.com/claudeaiportfolio/portfolio-infra.git//terraform/modules/auth0?ref=tf-modules-v0.1.0"

  auth0_apis    = {} # APIs are owned centrally in portfolio-infra
  auth0_clients = var.auth0_clients
  key_vault_id  = data.azurerm_key_vault.main.id
}
