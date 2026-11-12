#!/usr/bin/env bash
# Creates the Entra ID app that GitHub Actions uses via OIDC (run once).
set -euo pipefail

REPO="abhinandansamal/recall-radar"
APP_NAME="gh-recall-radar-ci"
SUB_ID="$(az account show --query id -o tsv)"
TENANT_ID="$(az account show --query tenantId -o tsv)"
STATE_SA_ID="$(az storage account show -n strrtfstateefdcb1 -g rg-rr-tfstate --query id -o tsv)"

APP_ID="$(az ad app create --display-name "$APP_NAME" --query appId -o tsv)"
az ad sp create --id "$APP_ID" -o none
SP_ID="$(az ad sp show --id "$APP_ID" --query id -o tsv)"

# Trust GitHub tokens for pull requests and for the main branch of this repo only.
for pair in "pr:repo:${REPO}:pull_request" "main:repo:${REPO}:ref:refs/heads/main"; do
  name="${pair%%:*}"; subject="${pair#*:}"
  az ad app federated-credential create --id "$APP_ID" --parameters "{
    \"name\": \"github-${name}\",
    \"issuer\": \"https://token.actions.githubusercontent.com\",
    \"subject\": \"${subject}\",
    \"audiences\": [\"api://AzureADTokenExchange\"]
  }" -o none
done

# Read-only on the subscription; read/write on the state storage (plan needs the state lock).
az role assignment create --assignee-object-id "$SP_ID" --assignee-principal-type ServicePrincipal \
  --role "Reader" --scope "/subscriptions/${SUB_ID}" -o none
az role assignment create --assignee-object-id "$SP_ID" --assignee-principal-type ServicePrincipal \
  --role "Storage Blob Data Contributor" --scope "$STATE_SA_ID" -o none

# Non-secret IDs as GitHub repository variables.
gh variable set AZURE_CLIENT_ID --body "$APP_ID"
gh variable set AZURE_TENANT_ID --body "$TENANT_ID"
gh variable set AZURE_SUBSCRIPTION_ID --body "$SUB_ID"

echo "Done. CI app: $APP_NAME ($APP_ID)"
