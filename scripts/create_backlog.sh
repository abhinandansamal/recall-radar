#!/usr/bin/env bash
# Creates the 6 epics and the Sprint 1 user stories as GitHub issues.
# Later sprints are refined at their own sprint planning (that is how Scrum works).
# Usage: ./scripts/create_backlog.sh <owner>/<repo>
set -euo pipefail

REPO="${1:?usage: $0 <owner>/<repo>}"
S1="Sprint 1: Data Foundation"

epic() { gh issue create --repo "$REPO" --title "$1" --label "type:epic" --body "$2" >/dev/null; echo "  epic: $1"; }
story() {
  # $1 title, $2 feature label, $3 points, $4 body
  gh issue create --repo "$REPO" --title "$1" --label "type:story,$2" --milestone "$S1" \
    --body "**Story points:** $3

$4" >/dev/null
  echo "  story: $1"
}

echo "==> Epics"
epic "E1: Platform Foundation"      "Repo, CI, logging, config, Terraform for dev/test/prod. Features F01-F02."
epic "E2: Data Platform"            "Medallion pipelines on Databricks for Safety Gate, ABO and GPSR text; DQ, lineage, export to Postgres. Features F03-F05."
epic "E3: Retrieval & Evaluation"   "Gold sets, chunking, embeddings, hybrid search, reranking, cited answers, RAGAS. Features F06-F08."
epic "E4: Agentic Core"             "LLM gateway, MCP servers, LangGraph multi-agent workflow, memory, HITL, guardrails. Features F09-F12."
epic "E5: Product Interfaces"       "FastAPI with roles, A2A legal agent, Discord + Gmail notifications, bilingual Next.js UI. Features F13-F15."
epic "E7: RadarMart demonstration marketplace" "Storefront, cart, simulated checkout, orders, seller portal, back office; signed listing events to Recall Radar. See PD-002."
epic "E6: Release & Operations"     "Docker, Helm, AKS proof run, Container Apps deploy, load test, cost report, v1.0.0 release. Features F16-F17."

echo "==> Sprint 0 (Product Discovery) items, created and closed with evidence"
done_item() {
  url=$(gh issue create --repo "$REPO" --title "$1" --label "type:chore" --milestone "Sprint 0: Setup" --body "$2")
  gh issue close "$url" --comment "Done. Evidence: $3" >/dev/null; echo "  closed: $1"
}
done_item "S0-1: Choose problem and validate market and law" "Compare candidate problems; verify GPSR/DSA/ProdSG duties with sources." "docs/product/product-requirements.md section 2"
done_item "S0-2: Verify data availability and licences" "Download and parse Safety Gate, ABO and GPSR; measure field coverage." "docs/data/data-sources.md"
done_item "S0-3: Manual study 1 (alert to catalogue)" "Check real alerts against the catalogue by hand." "evals/baseline/README.md (Study 1)"
done_item "S0-4: Product decision PD-001 two-trigger screening" "Decide direction based on study 1 and two-year data analysis." "docs/product/decisions/PD-001-two-trigger-screening.md"
done_item "S0-5: Product decision PD-002 RadarMart" "Decide on the demonstration marketplace." "docs/product/decisions/PD-002-radarmart.md"
done_item "S0-6: Product Requirements Document v1.0" "Problem, users, features, KPIs, risks." "docs/product/product-requirements.md"
gh issue create --repo "$REPO" --title "S0-7: Manual study 2 (10 listings, timed baseline)" --label "type:chore,eval" --milestone "Sprint 0: Setup" --body "Follow evals/baseline/README.md (Study 2). Output: evals/reports/baseline.md" >/dev/null

echo "==> Sprint 1 stories"
story "US-001: CI quality gates on every PR" "F01" 3 \
"As a developer, I want every PR checked automatically so that broken or insecure code cannot reach main.

- Given a PR, when CI runs, then lint, format, mypy strict, unit tests, coverage >= 85 %, secret scan and dependency audit all run.
- Given a commit containing a fake secret, when CI runs, then the secret scan fails the build.
- Given any CI run, then JUnit and coverage reports are uploaded as artifacts."

story "US-002: JSON logs with correlation IDs" "F01" 3 \
"As an operator, I want JSON logs with a correlation ID so that I can follow one request across all services.

- Given any log call, then the output is one JSON line with timestamp (UTC ISO 8601), level, event, env, service, correlation_id.
- Given two concurrent async tasks, then each keeps its own correlation ID.
- Given a log field named api_key, password, authorization or email, then its value is redacted."

story "US-003: Typed settings per environment" "F01" 2 \
"As a developer, I want validated settings for dev/test/prod so that a wrong setting fails at startup, not in production.

- Given APP_ENV outside {dev,test,prod}, then startup fails with a clear error.
- Given APP_ENV=prod without an LLM API key, then startup fails.
- Given any secret setting, then it never appears in repr() or logs."

story "US-004: Terraform base for dev/test/prod" "F02" 5 \
"As a platform engineer, I want infrastructure as code per environment so that environments are reproducible and isolated.

- Given infra/terraform/envs/{test,prod}, when terraform plan runs, then it shows only the expected resources.
- Given each environment, then its state lives in its own remote state file with locking.
- Given CI, then it authenticates to Azure with OIDC (no stored cloud keys)."

story "US-005: Cost guardrails" "F02" 1 \
"As the budget owner, I want alerts before spending exceeds EUR 25 per month so that the project stays under EUR 30.

- Given the subscription budget, when actual or forecast spend crosses 50/80/100 % of EUR 25, then an email alert is sent.
- Given Log Analytics, then a daily ingestion cap is set."

story "US-006: Databricks workspace and Unity Catalog per environment" "F02" 3 \
"As a data engineer, I want one catalog per environment so that dev, test and prod data never mix.

- Given the workspace, then catalogs rr_dev, rr_test, rr_prod exist with schemas bronze, silver, gold, ops.
- Given the catalogs, then volumes for landing files and images exist."

story "US-007: Bronze ingestion of Safety Gate alerts" "F03" 5 \
"As a data engineer, I want raw Safety Gate alerts ingested incrementally so that every weekly report is captured exactly once.

- Given a new weekly file in the landing volume, when the pipeline runs, then its alerts appear in bronze with _source_file, _ingested_at, _batch_id.
- Given the same file again, then no duplicate rows are created.
- Given an unknown field, then it is kept in the rescued-data column."

story "US-008: Bronze ingestion and profiling of the ABO catalogue subset" "F03" 5 \
"As a data engineer, I want a profiled subset of Amazon Berkeley Objects listings so that matching is tested on realistic marketplace data.

- Given the profiling notebook, then category overlap with Safety Gate is measured and recorded in evals/reports/F03.md.
- Given the selected categories, then listings and image metadata land in bronze with licence attribution."

story "US-009: Bronze ingestion of GPSR legal text" "F03" 2 \
"As a compliance analyst, I want the GPSR text (EN + DE) ingested so that answers can cite the law.

- Given EUR-Lex sources, then EN and DE texts land in bronze with source URL and retrieval date."

story "US-010: Silver layer with data quality, quarantine and SCD2" "F04" 8 \
"As a data engineer, I want clean, typed data with quality rules so that bad records never reach the app.

- Given expectations, then invalid rows go to ops.quarantine_* and pass/fail counts are stored.
- Given an updated or withdrawn alert, then silver keeps history (valid_from, valid_to, is_current).
- Given an invalid GTIN check digit, then the record is quarantined."

story "US-011: Content-addressed image storage" "F04" 3 \
"As a data engineer, I want each image stored once under its SHA-256 so that storage and embeddings are not duplicated.

- Given two identical images, then only one file exists in the images volume.
- Given an image, then silver.images holds sha256, size, perceptual hash, licence and source URL."

story "US-012: Gold layer and export to Postgres" "F05" 5 \
"As the application, I want gold data in Postgres + pgvector so that search is fast and cheap.

- Given a gold refresh, when the export runs, then data is loaded into staging tables and swapped atomically.
- Given the export, then row counts match gold and contract tests on the schemas pass."

echo "Done. Add the issues to the project board and move Sprint 1 stories to 'Ready'."
