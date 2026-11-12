data "azurerm_client_config" "current" {}

resource "random_string" "suffix" {
  length  = 4
  upper   = false
  special = false
}

locals {
  tags = {
    project    = "recall-radar",
    env        = "shared",
    managed_by = "terraform"
  }
}

resource "azurerm_resource_group" "this" {
  name     = "rg-rr-shared"
  location = var.location
  tags     = local.tags
}
