# Recall Radar

Finds online-marketplace listings that match EU **Safety Gate** dangerous-product alerts, checks them
against the **General Product Safety Regulation (EU) 2023/988**, and prepares notices that a human
reviewer approves. Text + image (multi-modal) matching, retrieval-augmented legal answers with
citations, multi-agent workflow with MCP tools and an A2A legal agent. English and German.

> Status: Sprint 1 in progress. Architecture docs, ADRs and evaluation reports live in `docs/` and
> `evals/`.

## Project journey (how this product was built)

| Phase | What happened | Evidence |
|-------|---------------|----------|
| Sprint 0: Product Discovery | Problem validated, data checked, manual baseline, product decisions, PRD | [Discovery log](docs/product/discovery-log.md), [PRD](docs/product/product-requirements.md) ([PDF](docs/product/Recall-Radar-PRD-v1.0.pdf)) |
| Sprint 1: Data Foundation | _in progress_ | [Board](https://github.com/users/abhinandansamal/projects/2), [Devlog](docs/devlog/) |
| Sprint 2: AI Core | _planned_ | |
| Sprint 3: Product & Release | _planned_ | |

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
| `packages/` | Python libraries (core, llm_gateway, rag, agents) |
| `apps/api`, `apps/web` | FastAPI service, Next.js UI |
| `services/` | MCP servers and the A2A legal agent |
| `data/` | Databricks Asset Bundle (pipelines, jobs) |
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
