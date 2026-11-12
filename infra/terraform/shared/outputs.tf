output "databricks_workspace_url" {
  value = "https://${azurerm_databricks_workspace.this.workspace_url}"
}

output "access_connector_id" {
  value = azurerm_databricks_access_connector.uc.id
}

output "lake_account_name" {
  value = azurerm_storage_account.lake.name
}

output "postgres_fqdn" {
  value = azurerm_postgresql_flexible_server.this.fqdn
}

output "postgres_admin_password" {
  value     = random_password.pg_admin.result
  sensitive = true
}
