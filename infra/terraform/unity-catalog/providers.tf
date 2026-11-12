data "terraform_remote_state" "shared" {
  backend = "azurerm"
  config = {
    resource_group_name  = "rg-rr-tfstate"
    storage_account_name = "strrtfstateefdcb1"
    container_name       = "tfstate"
    key                  = "shared.tfstate"
    use_azuread_auth     = true
  }
}

locals {
  shared = data.terraform_remote_state.shared.outputs
}

provider "databricks" {
  host      = local.shared.databricks_workspace_url
  auth_type = "azure-cli"
}
