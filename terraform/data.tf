data "azurerm_client_config" "current" {}

data "azurerm_kubernetes_cluster" "portfolio" {
  name                = var.aks_cluster_name
  resource_group_name = var.aks_resource_group
}
