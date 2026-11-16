# Recall Radar

Finds online-marketplace listings that match EU **Safety Gate** dangerous-product alerts, checks them
against the **General Product Safety Regulation (EU) 2023/988**, and prepares notices that a human
reviewer approves. Text + image (multi-modal) matching, retrieval-augmented legal answers with
citations, multi-agent workflow with MCP tools and an A2A legal agent. English and German.

> Status (16 Nov 2026): data platform done (Sprints 0–2). Next: retrieval and evaluation (Sprint 3),
> agents (Sprint 4), interfaces and RadarMart (Sprint 5), release v1.0 on 29 Nov (Sprint 6).
> Architecture docs, ADRs and evaluation reports live in `docs/` and `evals/`.

## Project journey (how this product was built)

| Phase | What happened | Evidence |
|-------|---------------|----------|
| Sprint 0: Product Discovery | Problem validated, data checked, manual baseline, product decisions, PRD | [Discovery log](docs/product/discovery-log.md), [PRD](docs/product/product-requirements.md) ([PDF](docs/product/Recall-Radar-PRD-v1.0.pdf)) |
| Sprint 1: Data Foundation | CI gates, typed settings, JSON logs, Terraform dev/test/prod, Databricks + Unity Catalog, bronze Safety Gate (since 2005, EN/DE) and GPSR | [Sprint 1 review](docs/sprints/sprint-1.md), [ADR-0004](docs/adr/0004-data-storage.md) |
| Sprint 2: Data Platform completed | Silver with DQ, quarantine and SCD2; photos by SHA-256; gold and atomic export to Postgres + pgvector; ABO catalogue profiled | [Sprint 2 review](docs/sprints/sprint-2.md), [F03 report](evals/reports/F03.md) |
| Sprint 3: Retrieval & Evaluation | _planned, 17–19 Nov_ | [Board](https://github.com/users/abhinandansamal/projects/2), [Devlog](docs/devlog/) |
| Sprint 4: Agentic Core | _planned, 20–22 Nov_ | |
| Sprint 5: Interfaces & RadarMart | _planned, 23–26 Nov_ | |
| Sprint 6: Release & Operations | _planned, 27–29 Nov, v1.0.0_ | |

## Quick start (dev)

```bash
cp .env.example .env          # then fill in local values
make install                  # uv sync --locked
make hooks                    # pre-commit hooks
make up                       # Postgres 17 + pgvector, Redis
make check                    # lint, types, tests: same gates as CI
```

## Repository layout

| Path | Purpose |
|------|---------|
| `packages/` | Python libraries: core, ingest, transform, export (built); llm_gateway, rag, agents (planned) |
| `apps/api`, `apps/web` | FastAPI service, Next.js UI |
| `services/` | MCP servers and the A2A legal agent |
| `pipelines/` | Databricks notebooks: bronze, silver, gold, profiling, reviewed reference data |
| `data/` | Local working data, git-ignored (e.g. downloaded gold exports) |
| `infra/terraform/` | Azure infrastructure per environment |
| `deploy/` | Dockerfiles and Helm chart |
| `evals/` | Gold sets, evaluation harness, reports |
| `tests/` | unit, integration, e2e, fixtures |
| `docs/` | ADRs, devlog, diagrams, proof (screenshots, AKS run) |

## Data

Public sources only; availability, fields, volumes and licences are documented in
[docs/data/data-sources.md](docs/data/data-sources.md).

## How we work

See [CONTRIBUTING.md](CONTRIBUTING.md): Scrum, TDD, Conventional Commits, Definition of Done,
Dev / Test / Prod environments. AI assistance: used for architecture review and document drafting; implementation, testing and evaluation are my own work.
