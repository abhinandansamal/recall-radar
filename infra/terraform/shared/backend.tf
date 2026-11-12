terraform {
  backend "azurerm" {
    resource_group_name  = "rg-rr-tfstate"
    storage_account_name = "strrtfstateefdcb1"
    container_name       = "tfstate"
    key                  = "shared.tfstate"
    use_azuread_auth     = true
  }
}
