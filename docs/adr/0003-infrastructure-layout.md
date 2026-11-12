# ADR-0003: Infrastructure layout (Terraform stacks, regions, Unity Catalog, CI auth)

- **Status:** Accepted
- **Date:** 2026-11-12
- **Feature:** F02 (US-004, US-005, US-006)

## Context

Recall Radar needs cloud resources for two environments (test, prod) plus a local dev setup.
Constraints from the design brief:
- **Budget:** at most €30/month.
- **Data:** stays in the EU.
- **Secrets:** none in the repo.
- **Reproducibility:** everything can be rebuilt from code.
- **Size:** one engineer, 12-day timeline.

## Decision

### 1. Four Terraform stacks, each with its own remote state
| Stack | State file | Contents |
|---|---|---|
| `envs/test`, `envs/prod` | `test.tfstate`, `prod.tfstate` | Resource group, Key Vault (RBAC), Log Analytics (daily cap), via `modules/environment` |
| `shared` | `shared.tfstate` | Databricks workspace (premium), ADLS Gen2 lake, access connector, Postgres flexible server |
| `unity-catalog` | `unity-catalog.tfstate` | Storage credential, external locations, catalogs, schemas, volumes |

- **Remote state:** Azure Blob (`strrtfstateefdcb1`) with Entra ID auth (`use_azuread_auth`). Shared-key access is disabled. Blob leases lock the state.
- **Bootstrap:** `scripts/bootstrap_tfstate.sh` creates the state storage. It is the only resource not managed by Terraform.
- **`unity-catalog` reads `shared`:** it uses `shared`'s outputs through `terraform_remote_state` instead of copying IDs by hand.

### 2. Expensive things are shared, cheap things are per environment
- **One Postgres server, one database per environment** (`rr_test`, `rr_prod`).
  - The free tier covers one B1ms server (750 h/month, 32 GB).
  - A second server would double the cost.
- **One Databricks workspace and one lake.**
  - Environments are separated by **Unity Catalog** (see 4), not by workspaces.
- **Per environment:** Key Vault and Log Analytics. They are cheap, and separating them keeps prod secrets and logs apart from test.

### 3. Regions
- **Default:** Germany West Central.
- **Postgres: France Central.** The flexible server returned no available versions in Germany West Central for this subscription. France Central is still in the EU, so the data-location rule holds. The region is the variable `postgres_location`, so it can move back later.

### 4. Unity Catalog: one catalog per environment
- **Catalogs:** `rr_dev`, `rr_test`, `rr_prod`. Each has its own external location on its own container (`uc-dev`, `uc-test`, `uc-prod`).
- **Schemas:** `bronze`, `silver`, `gold`, `ops` in every catalog.
- **Volumes:** `landing` and `images` in `bronze`.
- **Access to the lake:** the Databricks access connector's managed identity. No keys.

### 5. CI authenticates to Azure with OIDC, read-only
- **Entra app:** `gh-recall-radar-ci` (`scripts/setup_github_oidc.sh`).
- **Trusted tokens:** federated credentials trust GitHub tokens only for this repo's pull requests and `main`.
- **Subject format:** `repo:<owner>@<owner_id>/<repo>@<repo_id>:<context>`. The immutable IDs stop a re-created repo with the same name from reusing the trust.
- **Roles:**
  - Reader on the subscription.
  - Storage Blob Data Contributor on the state storage account.
- **CI job:** the `terraform-plan` job runs `plan -lock=false -detailed-exitcode` for test and prod on every PR.
- **Applying:** still done locally by a human. CI never applies.

## Alternatives considered

| Option | Why not (for now) |
|---|---|
| One workspace and Postgres server per environment | Doubles the cost; breaks the €30 budget |
| Terraform workspaces instead of env folders | Easy to apply to the wrong environment by mistake; folders make the target explicit |
| Service principal secret in GitHub secrets | A long-lived secret to rotate and leak; OIDC tokens last minutes |
| CI applies on merge | Needs Contributor rights in CI; not worth the risk at this project size |
| Postgres on a different provider (e.g. Neon) | Keeps everything on one cloud and one IAM model |

## Consequences

**Good**
- **Rebuildable:** the whole stack can be rebuilt from code plus two bootstrap scripts.
- **Drift is visible:** every PR shows whether test/prod still match the code.
- **No secrets in CI:** nothing is stored in GitHub except non-secret IDs.

**Trade-offs and follow-ups**
- **Shared Postgres server:** a heavy test workload can slow prod. Acceptable at demo scale.
- **Postgres public access:** access is limited by a firewall rule on my IP (`my_ip`). Re-apply when the IP changes. Move to private networking if the project goes beyond demo.
- **Manual apply:** `apply` stays manual, so code and cloud can drift until someone applies. The plan job detects this.
- **CI is Reader only:** CI can't read Key Vault secret values. That's fine as long as Terraform never reads secrets through data sources.
