# This solution's M2M client only. The RAG MCP API resource server (audience,
# scopes, 15-min token TTL) is a shared contract owned centrally in
# portfolio-infra (terraform/terraform.tfvars) and reused across solutions.
#
# No secrets or identifying values here — only public config. The module writes
# the generated client_id/secret to Key Vault as auth0-client-id-rag-m2m /
# auth0-client-secret-rag-m2m. Per-tool scope enforcement lives in
# src/mcp_server/auth.py (TOOL_SCOPES).
auth0_clients = {
  "rag-m2m" = {
    name                  = "RAG M2M"
    app_type              = "non_interactive"
    grant_types           = ["client_credentials"]
    authentication_method = "client_secret_post"
    api_identifier        = "https://rag.dev.michaelalinks.com"
    api_scopes            = ["ingest:write", "query:read", "admin:reindex"]
  }
}
