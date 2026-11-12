variable "env" {
  description = "Environment name: test or prod."
  type        = string
  validation {
    condition     = contains(["test", "prod"], var.env)
    error_message = "env must be test or prod."
  }
}

variable "location" {
  description = "Azure region."
  type        = string
  default     = "germanywestcentral"
}

variable "log_daily_quota_gb" {
  description = "Daily Log Analytics ingestion cap in GB (cost guardrail)."
  type        = number
  default     = 0.5
}

variable "tags" {
  description = "Extra tags for all resources."
  type        = map(string)
  default     = {}
}
