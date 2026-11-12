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
