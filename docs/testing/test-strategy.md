# Test strategy

Every feature is tested before the next one starts (TDD). Each layer below has an owner tool, a place
in the repo, an environment, and a gate that blocks merge or release.

## Layers

| # | Layer | What it proves | Tools | Repo path | Runs where / when | Gate |
|---|-------|----------------|-------|-----------|-------------------|------|
| 1 | **Unit** | Each function does what it promises, without network or LLM | pytest, fake LLM client, fixtures | `tests/unit/` | Dev + CI, every commit / PR | All pass; coverage ≥ 85 % on core packages |
| 2 | **Integration** | Our code works with real Postgres/pgvector and Redis | pytest + Testcontainers | `tests/integration/` | CI on every PR | All pass |
| 3 | **Contract** | Interfaces between parts do not break silently | OpenAPI snapshot + property-based API tests; JSON-Schema snapshots of MCP tools; A2A Agent Card validation; Pydantic data contracts on gold tables; Databricks expectations; Pydantic schemas for LLM structured outputs | `tests/contract/` | CI on every PR | No unreviewed schema change; all contracts pass |
| 4 | **Eval suite (regression)** | Quality does not get worse when code, prompts, models or data change | Versioned gold sets; retrieval metrics (recall@k, MRR, nDCG); RAGAS (faithfulness, answer relevancy, context precision); citation check by the claim verifier; agent task success; readability (Flesch EN / Flesch-Amstad DE) | `evals/` (data, harness, reports) | PR (small sample, only when `packages/rag`, `packages/agents` or prompts change), nightly on Test (full set), before every release | Metric may not drop more than the agreed tolerance vs. the stored baseline on `main` |
| 5 | **Adversarial / red-team** | The system resists misuse | Own attack set (EN + DE): direct and indirect prompt injection (poisoned alert or listing text), jailbreaks, system-prompt / secret extraction, PII leakage, MCP tool misuse (e.g. unapproved notifications), role/RBAC bypass, oversized inputs; mapped to OWASP Top 10 for LLM Applications. Scanner tool chosen in F12 (ADR) | `tests/security/` | CI on every PR touching agents/guardrails; full run before release | Attack success rate ≤ threshold **and** false-refusal rate on benign questions ≤ threshold |
| 6 | **End-to-end** | A real user flow works through the UI | Playwright | `tests/e2e/` | After every deploy to Test | Critical flows pass (login per role, chat, review + approve, notification) |
| 7 | **Load** | The system meets its service levels under traffic | Locust: chat, search, case investigation; measures p50/p95 latency, throughput, error rate, cache hit rate, LLM rate-limit behaviour, € per 1,000 requests | `tests/load/` | Test environment only, before release (never against Prod) | p95 latency and error rate within SLO |
| 8 | **Shadow** (production) | A new model / prompt / retrieval change is better on real traffic before users see it | App-level mirroring: a sample of Prod requests is also sent asynchronously to the candidate pipeline; its answers are never shown; Langfuse scores (claim verifier, LLM-as-judge) compare old vs. new. Low traffic is topped up by replaying gold-set sessions | `packages/agents` (feature flag), Langfuse | Prod, for AI changes only | Candidate ≥ current on online scores, no new safety failures |
| 9 | **Canary** (production) | A new release is safe with real users | Azure Container Apps revisions with traffic split (e.g. 10 % → 50 % → 100 %); watch error rate, p95 latency and online eval scores; automatic rollback to the previous revision | `.github/workflows/release.yml` (F17) | Prod, every release | SLOs hold during each step, otherwise rollback |
| 10 | **Smoke** | The deployment is alive and wired correctly | `/healthz`, `/readyz`, one real request | CI after each deploy | Test + Prod | Pass, else the deploy is marked failed |

## Where results are stored

- CI test logs: JUnit XML + coverage XML as workflow artifacts (30 days), summary on the PR
- Eval results: `evals/reports/Fxx.md` (per feature) and `evals/reports/baseline.json` (current baseline on `main`); every run records dataset version, model, prompt version and commit
- Online scores, shadow comparisons, traces: Langfuse (one project per environment)
- Load and red-team reports, AKS proof run, canary screenshots: `docs/proof/`
- Release: the GitHub Release attaches the test report, eval summary, red-team summary and SBOM

## Test data rules

- Unit/contract tests use small fixtures in `tests/fixtures/` (cut from the real public sources, with attribution)
- Gold sets live in `evals/data/` with a version number and a data card; they are never used to tune prompts directly (separate dev / test splits)
- No personal data in any test set
