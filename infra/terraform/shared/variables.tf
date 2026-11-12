variable "subscription_id" {
  description = "Azure subscription ID."
  type        = string
}

variable "location" {
  description = "Azure region."
  type        = string
  default     = "germanywestcentral"
}

variable "my_ip" {
  description = "Your public IP address, allowed through the Postgres firewall."
  type        = string
}

variable "uc_envs" {
  description = "Environments that get a Unity Catalog storage container."
  type        = set(string)
  default     = ["dev", "test", "prod"]
}

variable "postgres_location" {
  description = "Region for Postgres (Germany West Central offers no flexible server for this subscription)."
  type        = string
  default     = "francecentral"
}

variable "budget_amount_eur" {
  description = "Monthly budget in EUR; alerts fire at 50/80/100 % of it."
  type        = number
  default     = 25
}

variable "budget_email" {
  description = "Where budget alerts are sent. Passed via TF_VAR_budget_email, never committed."
  type        = string
}
