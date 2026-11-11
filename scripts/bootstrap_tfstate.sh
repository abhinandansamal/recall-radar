#!/usr/bin/env bash
# Creates the storage account that holds Terraform state (run once).
set -euo pipefail

LOCATION="germanywestcentral"
RG="rg-rr-tfstate"
SA="strrtfstate$(openssl rand -hex 3)"   # globally unique, 3-24 lowercase letters/digits

az group create -n "$RG" -l "$LOCATION" --tags project=recall-radar purpose=tfstate -o none
az storage account create -n "$SA" -g "$RG" -l "$LOCATION" \
  --sku Standard_LRS --kind StorageV2 --min-tls-version TLS1_2 \
  --allow-blob-public-access false --allow-shared-key-access false -o none
az storage account blob-service-properties update --account-name "$SA" -g "$RG" \
  --enable-versioning true --enable-delete-retention true --delete-retention-days 7 -o none

# Give yourself data access with your Entra ID login (no storage keys).
ME="$(az ad signed-in-user show --query id -o tsv)"
SA_ID="$(az storage account show -n "$SA" -g "$RG" --query id -o tsv)"
az role assignment create --assignee "$ME" --role "Storage Blob Data Contributor" --scope "$SA_ID" -o none

echo "Waiting 60 s for the role assignment to take effect..."
sleep 60
az storage container create --name tfstate --account-name "$SA" --auth-mode login -o none

echo "Done. Storage account: $SA"
