# Sprint 2 review and retrospective: AI Core (carry-over first)

- Dates: 14–16 Nov 2026
- Goal: finish the Sprint 1 carry-over (silver, photos, gold + export, ABO) first, then start the AI core
- Result: goal **partly met**: the whole data platform (E2) is done; no AI story was started

## Review: what was delivered

| Story | Points | Status | Evidence |
|-------|--------|--------|----------|
| US-010 Silver layer with DQ, quarantine and SCD2 | 8 | Done | PR #41, `docs/proof/sprint2/silver-sg-alerts-checks.png`, `silver-sg-alerts-history.png` |
| US-011 Content-addressed image storage | 3 | Done | PR #44, `docs/proof/sprint2/sg-images-checks.png` |
| US-012 Gold layer and export to Postgres | 5 | Done | PR #46, `docs/proof/sprint2/kb-export-postgres.png` |
| US-008 ABO catalogue subset, profile and overlap | 5 | Done | PR #47, `evals/reports/F03.md`, `docs/proof/sprint2/abo-bronze-checks.png` |
| E3 / E4 AI stories | – | **Not started** | Stories not yet written; moved to Sprint 3 and 4 |

**Velocity:** 21 points in 2 working days (Sprint 1: 24 points in 4 days). All carried-over points are done; nothing new was carried over.

### Demo highlights
- **Silver:** 96,570 bronze rows → 96,554 clean + 16 quarantined; 47,580 alerts per language; SCD2 history for corrected reports. A data problem never hides a dangerous product (Rule A).
- **Photos:** stored once per SHA-256; 2,000 newest photos stored, 0 rejected. `pip-audit` blocked a vulnerable Pillow before it ran.
- **Gold → Postgres:** 47,580 alerts, 73,998 identifiers, 2,200 photo links; loaded into staging, checked against the manifest and the schema contract, swapped live in one transaction. Keyword search in German and English works.
- **Tests:** 195 tests at 98 % coverage; CI now runs the database tests against a real Postgres + pgvector.
- **ABO:** 147,702 listings profiled; 39,324 listings in 197 reviewed product types in bronze with licence attribution. Honest overlap: 53.1 % of alerts are in categories with ≥ 100 listings (78.7 % with ≥ 1).

## Retrospective

### What went well
- **Carry-over first** worked: the sprint closed every open data story instead of starting new ones in parallel.
- **Testing outside Databricks first:** local Spark found the strict-ANSI empty-array error, and a real Postgres in CI proves the exporter's failure paths (wrong counts, broken keys, invalid values, concurrent runs).
- **Measure before planning:** photo size and count (197 KB, 2.4 per alert) cut the backfill estimate from 50 GB / 18 h to 20 GB / 5.8 h.
- **Product decisions were written down** (Rule A, footwear kept, reviewed category mapping), so the data can be explained.

### What did not go well
- **Docker Desktop hung** and blocked work for about 30 minutes (a stuck backend process).
- **Tool slips:**
  - `gh pr create --body-file` failed twice because the body file was not created first;
  - a `git stash pop` conflict on `uv.lock`;
  - the project bot moved a merged PR back to Backlog.
- **Databricks Git folder:** running notebooks changes their files; one Pull was blocked until the changes were discarded.
- **The AI part has not started**, and the original release date (19 Nov) is no longer reachable.

### Actions for Sprint 3
| Action | Owner |
|--------|-------|
| If a `docker` command hangs: `pgrep -fl com.docker`, end the stuck backend, `open -a Docker`, `make up` (see Day 8 notes) | Dev |
| Create the PR body file in the same command as `gh pr create` (`pbpaste > /tmp/pr.md && gh pr create … --body-file /tmp/pr.md`) | Dev |
| After every merge: check the project status of the issue and the PR is **Done** | Dev |
| Before every Databricks Pull: "No changed files", otherwise discard | Dev |
| Write all Sprint 3 stories with acceptance criteria and points **before** the first line of code | PO |

## New plan (Product Owner decision, 16 Nov)

The scope stays as in PRD v1.0; the release date moves from 19 Nov to **29 Nov**. One epic per sprint:

| Sprint | Dates | Epic | Goal |
|--------|-------|------|------|
| Sprint 3 | 17–19 Nov | E3 Retrieval & Evaluation (F06–F08) | Gold test sets first, then embeddings, hybrid search and reranking, measured against the targets in the design brief |
| Sprint 4 | 20–22 Nov | E4 Agentic Core (F09–F12) | LLM gateway, MCP tools, LangGraph workflow with human approval and guardrails |
| Sprint 5 | 23–26 Nov | E5 Product Interfaces (F13–F15) + E7 RadarMart | API with roles, review UI (EN/DE), notifications, RadarMart with signed events |
| Sprint 6 | 27–29 Nov | E6 Release & Operations (F16–F17) | Deployment, load test, cost report, before-and-after comparison, v1.0.0 |

Rules: at most 2 stories per day; data follow-ups #42 and #43 are scheduled when a sprint has spare capacity. Progress against this plan is checked in every sprint review.
