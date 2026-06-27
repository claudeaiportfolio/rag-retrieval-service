variable "auth0_clients" {
  description = "Map of Auth0 applications to provision. Key is a stable logical name (also used for the Key Vault secret suffix)."
  type = map(object({
    name                  = string
    app_type              = optional(string, "native")
    callbacks             = optional(list(string), [])
    logout_urls           = optional(list(string), [])
    grant_types           = optional(list(string), ["authorization_code", "refresh_token"])
    authentication_method = optional(string, "none")
    api_identifier        = optional(string, null)
    api_scopes            = optional(list(string), [])
  }))
  default = {}
}
