terraform {
  required_version = ">= 1.5"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    auth0 = {
      source  = "auth0/auth0"
      version = "~> 1.0"
    }
  }

  # The persistent Auth0 M2M client lives in its OWN state, separate from the
  # ephemeral RAG infra stack (../). Tearing the compute infra down and back up
  # (az group delete + make tf-apply) must never churn the agent credential.
  backend "azurerm" {
    resource_group_name  = "claudeaiportfolio"
    storage_account_name = "localtfsa"
    container_name       = "tfstate"
    key                  = "rag-auth0.tfstate"
    use_azuread_auth     = true
  }
}
