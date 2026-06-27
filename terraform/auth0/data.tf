data "azurerm_key_vault" "main" {
  name                = "localdevenv"
  resource_group_name = "kubernetes"
}

data "azurerm_key_vault_secret" "auth0_domain" {
  name         = "auth0-domain"
  key_vault_id = data.azurerm_key_vault.main.id
}

data "azurerm_key_vault_secret" "auth0_client_id" {
  name         = "auth0-terraform-client-id"
  key_vault_id = data.azurerm_key_vault.main.id
}

data "azurerm_key_vault_secret" "auth0_client_secret" {
  name         = "auth0-terraform-client-secret"
  key_vault_id = data.azurerm_key_vault.main.id
}
