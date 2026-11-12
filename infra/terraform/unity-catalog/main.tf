locals {
  envs    = toset(["dev", "test", "prod"])
  layers  = ["bronze", "silver", "gold", "ops"]
  volumes = ["landing", "images"]

  schemas = {
    for pair in setproduct(local.envs, local.layers) :
    "${pair[0]}.${pair[1]}" => { env = pair[0], name = pair[1] }
  }

  bronze_volumes = {
    for pair in setproduct(local.envs, local.volumes) :
    "${pair[0]}.${pair[1]}" => { env = pair[0], name = pair[1] }
  }
}

resource "databricks_storage_credential" "lake" {
  name    = "rr-lake"
  comment = "Access connector identity for the Recall Radar lake (managed by Terraform)"

  azure_managed_identity {
    access_connector_id = local.shared.access_connector_id
  }
}

resource "databricks_external_location" "env" {
  for_each        = local.envs
  name            = "rr-${each.key}"
  url             = "abfss://uc-${each.key}@${local.shared.lake_account_name}.dfs.core.windows.net/"
  credential_name = databricks_storage_credential.lake.name
  comment         = "Storage for catalog rr_${each.key}"
}

resource "databricks_catalog" "env" {
  for_each     = local.envs
  name         = "rr_${each.key}"
  storage_root = databricks_external_location.env[each.key].url
  comment      = "Recall Radar ${each.key} environment"
}

resource "databricks_schema" "layer" {
  for_each     = local.schemas
  catalog_name = databricks_catalog.env[each.value.env].name
  name         = each.value.name
}

resource "databricks_volume" "bronze" {
  for_each     = local.bronze_volumes
  catalog_name = databricks_catalog.env[each.value.env].name
  schema_name  = databricks_schema.layer["${each.value.env}.bronze"].name
  name         = each.value.name
  volume_type  = "MANAGED"
}

output "catalogs" {
  value = [for c in databricks_catalog.env : c.name]
}
