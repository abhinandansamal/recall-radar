module "environment" {
  source = "../../modules/environment"
  env    = "prod"
}

output "resource_group_name" {
  value = module.environment.resource_group_name
}

output "key_vault_name" {
  value = module.environment.key_vault_name
}
