# Sprint 1 review and retrospective: Data Foundation

- Dates: 10–13 Nov 2026 (extended by one day on 11 Nov, see devlog 2026-11-11)
- Goal: platform foundation (F01, F02) and data ingestion into the lakehouse (F03–F05)
- Result: goal **partly met**: foundation complete, bronze layer for Safety Gate and GPSR live; silver/gold not started

## Review: what was delivered

| Story | Points | Status | Evidence |
|-------|--------|--------|----------|
| US-001 CI quality gates on every PR | 3 | Done | PR #32 |
| US-002 JSON logs with correlation IDs | 3 | Done | PR #32; lazy-logger fix in PR #38 |
| US-003 Typed settings per environment | 2 | Done | PR #32 |
| US-004 Terraform base for dev/test/prod | 5 | Done | PR #34, ADR-0003 |
| US-005 Cost guardrails | 1 | Done | PR #34, `budget-rr-monthly` |
| US-006 Databricks workspace and Unity Catalog | 3 | Done | PR #34, `docs/proof/sprint1/unity-catalog.png` |
| SPIKE data and storage design | – | Done | PR #37, ADR-0004 |
| US-007 Bronze ingestion of Safety Gate alerts | 5 | Done | PR #38; 47,780 alerts per language since 2005 |
| US-009 Bronze ingestion of GPSR legal text | 2 | Done | PR #39; 4 documents (EN/DE, original + consolidated) |
| US-008 Bronze ingestion and profiling of ABO subset | 5 | **Carried over** | Not started |
| US-010 Silver layer with DQ, quarantine, SCD2 | 8 | **Carried over** | Design ready (ADR-0004, section 6.2) |
| US-011 Content-addressed image storage | 3 | **Carried over** | Design ready (ADR-0004, D4) |
| US-012 Gold layer and export to Postgres | 5 | **Carried over** | Design ready (ADR-0004, section 7.4) |

**Velocity:** 24 of 45 planned points (53 %). The carry-over (21 points) moves openly to Sprint 2.

### Demo highlights
- Every PR runs 5 required checks: lint/types/tests, secret scan, Terraform validate, and a read-only Terraform plan for test and prod via GitHub OIDC (no stored secrets).
- **Safety Gate:** the full history since 2005 is in `rr_dev.bronze.sg_alerts_raw`: 1,124 weekly reports × EN/DE, about 47,600 distinct alerts per language. A re-run adds 0 rows; the self-test proves the three acceptance criteria on Databricks.
- **GPSR:** the text is in `rr_dev.bronze.gpsr_raw`, with source URL and retrieval date.
- **Budget:** €25/month with alerts, as code.

## Retrospective

### What went well
- **Looking at real data before writing code** found four problems early:
  - the `&amp;` in Safety Gate URLs;
  - error pages returned with HTTP 200;
  - two XML "dialects" of the same report;
  - the EUR-Lex bot challenge (HTTP 202, empty body).
  Each one is now a unit test.
- Designing storage before pipelines (ADR-0004) made US-007 and US-009 fast to build.
- Small commits, required checks and squash merges keep `main` green and readable.

### What did not go well
- **Planning:** six stories planned for the last day; two were done. Time estimates for external downloads were too low (Safety Gate backfill: about 2 h, not 45 min).
- **Process slips:**
  - A PR without a closing keyword left the spike issue open.
  - A GitHub 500 during a push left a PR pointing at an old commit.
  - Screenshots exceeded the 500 KB limit.
- **Assumptions:** the alert history was estimated at up to 100k; it is about 47.6k per language. The Sprint 0 budget was at billing-profile scope, so the CLI did not find it.

### Actions for Sprint 2
| Action | Owner |
|--------|-------|
| Plan at most 2 stories per day; time-box external downloads by measuring first | PO / Dev |
| Every PR: `gh pr create … --body "Closes #N"` | Dev |
| After any push error: check `gh pr view <n> --json headRefOid` before merging | Dev |
| Resize screenshots with `sips -Z 1400` before `git add` | Dev |
| Update section 4 of the storage design with the measured alert count | Dev (US-012) |

## Sprint 2 (14–16 Nov): proposed scope
1. **Carry-over first:** US-010 silver (incl. SCD2 for the two corrected reports), US-011 images, US-008 ABO subset, US-012 gold + export.
2. Then the Sprint 2 stories as far as capacity allows.
3. **Scope decision (Product Owner, 13 Nov):** all planned v1.0 features stay in scope. If the remaining work does not fit into Sprint 2 and 3, the release date moves; no feature is silently dropped. Progress against the original date (19 Nov) is tracked in each sprint review.
