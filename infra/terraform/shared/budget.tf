# US-005: cost guardrail. Email alerts before monthly spend passes EUR 25 (hard limit EUR 30).
data "azurerm_subscription" "current" {}

locals {
  budget_alerts = [
    { threshold = 50, type = "Actual" },
    { threshold = 80, type = "Actual" },
    { threshold = 100, type = "Actual" },
    { threshold = 80, type = "Forecasted" },
    { threshold = 100, type = "Forecasted" },
  ]
}

resource "azurerm_consumption_budget_subscription" "monthly" {
  name            = "budget-rr-monthly"
  subscription_id = data.azurerm_subscription.current.id
  amount          = var.budget_amount_eur
  time_grain      = "Monthly"

  time_period {
    start_date = "2026-11-01T00:00:00Z"
  }

  dynamic "notification" {
    for_each = local.budget_alerts
    content {
      enabled        = true
      threshold      = notification.value.threshold
      threshold_type = notification.value.type
      operator       = "GreaterThan"
      contact_emails = [var.budget_email]
    }
  }
}
