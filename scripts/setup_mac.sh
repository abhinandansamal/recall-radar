#!/usr/bin/env bash
# Installs the local toolchain on macOS (Apple Silicon). Safe to re-run.
# Usage: ./scripts/setup_mac.sh
set -euo pipefail

command -v brew >/dev/null || {
  echo "Install Homebrew first: https://brew.sh"; exit 1; }

brew update
brew install uv gh azure-cli kubectl helm kind jq gitleaks
# Homebrew core froze Terraform at an old version after the licence change; use HashiCorp's tap.
brew tap hashicorp/tap && brew install hashicorp/tap/terraform
brew tap databricks/tap && brew install databricks
brew install --cask docker   # Docker Desktop; open it once afterwards to finish setup

uv python install 3.12

echo
echo "Versions:"
uv --version; gh --version | head -1; az version --query '"azure-cli"' -o tsv
gitleaks version; terraform -version | head -1; kubectl version --client | head -1; helm version --short
databricks --version
echo
echo "Next: open Docker Desktop, then test cross-platform builds with:"
echo "  docker run --rm --platform linux/amd64 alpine uname -m    # should print x86_64"
