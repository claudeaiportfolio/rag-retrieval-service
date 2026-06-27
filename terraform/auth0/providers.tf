provider "azurerm" {
  # Auth mode is driven by env vars so the same config works in both contexts:
  #   local dev    — ARM_USE_AZUREAD=true ARM_USE_CLI=true
  #   CI (Actions) — ARM_USE_AZUREAD=true ARM_USE_OIDC=true
  storage_use_azuread             = true
  resource_provider_registrations = "none"

  features {}
}

# The Auth0 management-API credentials (a dedicated terraform M2M app) are read
# from the shared Key Vault at apply time — nothing tenant-specific is committed.
provider "auth0" {
  domain        = data.azurerm_key_vault_secret.auth0_domain.value
  client_id     = data.azurerm_key_vault_secret.auth0_client_id.value
  client_secret = data.azurerm_key_vault_secret.auth0_client_secret.value
}
