resource "azurerm_databricks_workspace" "this" {
  name                        = "dbw-rr"
  resource_group_name         = azurerm_resource_group.this.name
  location                    = azurerm_resource_group.this.location
  sku                         = "premium"
  managed_resource_group_name = "rg-rr-dbw-managed"
  tags                        = local.tags
}

resource "azurerm_storage_account" "lake" {
  name                            = "strrlake${random_string.suffix.result}"
  resource_group_name             = azurerm_resource_group.this.name
  location                        = azurerm_resource_group.this.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  account_kind                    = "StorageV2"
  is_hns_enabled                  = true
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  shared_access_key_enabled       = false
  tags                            = local.tags
}

resource "azurerm_storage_container" "uc" {
  for_each              = var.uc_envs
  name                  = "uc-${each.key}"
  storage_account_id    = azurerm_storage_account.lake.id
  container_access_type = "private"
}

resource "azurerm_databricks_access_connector" "uc" {
  name                = "dbac-rr"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  tags                = local.tags

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_role_assignment" "uc_lake" {
  scope                = azurerm_storage_account.lake.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_databricks_access_connector.uc.identity[0].principal_id
}
