variable "location" {
  description = "Azure region for the RAG platform."
  type        = string
  default     = "uksouth"
}

variable "resource_group_name" {
  description = "Dedicated resource group for the RAG platform."
  type        = string
  default     = "rag-platform-uks"
}

variable "name_prefix" {
  description = "Short prefix applied to every resource name."
  type        = string
  default     = "rag"
}

variable "aks_cluster_name" {
  description = "Name of the existing portfolio AKS cluster that workloads will federate against."
  type        = string
}

variable "aks_resource_group" {
  description = "Resource group containing the existing AKS cluster."
  type        = string
}

variable "aks_node_resource_group_override" {
  description = "Optional override for the AKS node resource group (used when adding the spot pool). Leave null to use the cluster's MC_* RG."
  type        = string
  default     = null
}

variable "enable_private_endpoints" {
  description = "Toggle private endpoints + private DNS for Postgres, Storage, AOAI. Off by default to keep dev cost low."
  type        = bool
  default     = false
}

variable "postgres_sku_name" {
  description = "Flexible Server SKU. GP tier is required for read replicas."
  type        = string
  default     = "GP_Standard_D2ds_v5"
}

variable "postgres_storage_mb" {
  description = "Primary server storage in MB. Can only scale up."
  type        = number
  default     = 32768
}

variable "postgres_aad_admin_object_id" {
  description = "Object ID of the AAD principal granted Postgres admin (your user, a group, or a service principal)."
  type        = string
}

variable "postgres_aad_admin_principal_name" {
  description = "UPN or display name of the AAD admin (shown in az postgres-flexible-server)."
  type        = string
}

variable "postgres_aad_admin_principal_type" {
  description = "Principal type for the AAD admin (User, Group, or ServicePrincipal)."
  type        = string
  default     = "User"
}

variable "postgres_ci_admin_object_id" {
  description = "Object ID of the CI service principal granted parallel Postgres AAD admin (lets terraform-postdeploy run CREATE EXTENSION hands-free). Leave empty to skip."
  type        = string
  default     = ""
}

variable "postgres_ci_admin_principal_name" {
  description = "Display name of the CI service principal (must match the UAMI name in AAD)."
  type        = string
  default     = ""
}

variable "embedding_model_capacity" {
  description = "TPM capacity (in thousands) for the embedding deployment."
  type        = number
  default     = 50
}

variable "chat_model_capacity" {
  description = "TPM capacity (in thousands) for the chat deployment."
  type        = number
  default     = 30
}

variable "spot_max_price" {
  description = "Spot pool max price in USD. -1 caps at on-demand."
  type        = number
  default     = -1
}

variable "tags" {
  description = "Tags applied to every resource."
  type        = map(string)
  default = {
    project = "rag-retrieval-service"
    tier    = "portfolio"
    iac     = "terraform"
  }
}
