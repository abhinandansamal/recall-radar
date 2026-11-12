resource "random_password" "pg_admin" {
  length           = 32
  special          = true
  override_special = "-_"
}

resource "azurerm_postgresql_flexible_server" "this" {
  name                          = "psql-rr-${random_string.suffix.result}"
  resource_group_name           = azurerm_resource_group.this.name
  location                      = var.postgres_location
  version                       = "17"
  sku_name                      = "B_Standard_B1ms"
  storage_mb                    = 32768
  backup_retention_days         = 7
  geo_redundant_backup_enabled  = false
  public_network_access_enabled = true
  administrator_login           = "rradmin"
  administrator_password        = random_password.pg_admin.result
  tags                          = local.tags

  lifecycle {
    ignore_changes = [zone]
  }
}

resource "azurerm_postgresql_flexible_server_firewall_rule" "my_ip" {
  name             = "allow-developer-ip"
  server_id        = azurerm_postgresql_flexible_server.this.id
  start_ip_address = var.my_ip
  end_ip_address   = var.my_ip
}

resource "azurerm_postgresql_flexible_server_configuration" "extensions" {
  name      = "azure.extensions"
  server_id = azurerm_postgresql_flexible_server.this.id
  value     = "VECTOR"
}

resource "azurerm_postgresql_flexible_server_database" "env" {
  for_each  = toset(["rr_test", "rr_prod"])
  name      = each.key
  server_id = azurerm_postgresql_flexible_server.this.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}
