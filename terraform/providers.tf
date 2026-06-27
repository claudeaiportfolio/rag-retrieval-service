provider "azurerm" {
  # Auth mode is driven by env vars so the same config works in both contexts:
  #   local dev   — Makefile exports ARM_USE_AZUREAD=true ARM_USE_CLI=true
  #   CI (Actions) — workflow env exports ARM_USE_AZUREAD=true ARM_USE_OIDC=true
  storage_use_azuread             = true
  resource_provider_registrations = "none"

  features {
    postgresql_flexible_server {
      restart_server_on_configuration_value_change = true
    }
  }
}
