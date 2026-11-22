# Sprint 3 planning: Retrieval & Evaluation (E3)

- Dates: 22–24 Nov 2026 (re-planned on 22 Nov)
- Goal: every stage of screening retrieval is measured on our own gold sets, and the best models are chosen
  by evidence: gold sets and gates → GPSR chunks → embedding bake-off → vectors in Postgres → screening
  retrieval
- Design: [AI design plan](../architecture/ai-design-plan.md), [ADR-0005](../adr/0005-ai-architecture.md),
  [evaluation gates](../testing/evaluation-gates.md), [threat model](../security/threat-model.md)

## Why the plan changed

The Sprint 2 review (16 Nov) planned Sprint 3 for 17–19 Nov. Before writing any AI code, 16–21 Nov became
an **AI design phase**: RAG and agent design options were evaluated against the PRD and the design brief,
and the design was decided and written down (AI design plan, ADR-0005, evaluation gates, threat model
v1, Sprint 3 stories with an evaluation gate and a security part each). Scope stays the same (PO decision of
13 Nov); the sprint dates move.

## Capacity

| Day | Hours | Points (≈ 1.5 points per hour, measured in Sprint 2) |
|-----|------:|------:|
| 22 Nov | 10–12 | ~15 (minus ~2 h for re-planning and merges) |
| 23 Nov | 10–12 | ~16 |
| 24 Nov | 4–5 | ~7 |
| **Total** | | **~35** |

## Sprint backlog (order matters)

| Story | Points | Gate it must pass |
|-------|-------:|-------------------|
| US-013 Gold sets v1, evaluation harness and per-stage gates | 5 | Harness metrics correct (unit tests) |
| US-014 GPSR article chunks with citations (EN/DE) in `kb` | 5 | Stage 0: 100 % articles and paragraphs, complete citation fields |
| US-015 Embedding model bake-off (ADR-0006) | 5 | Stage 1: no slice below recall@50 = 0.80 |
| US-016 Vectors for alerts, photos and GPSR chunks in Postgres | 5 | 100 % coverage; recall@50 within 1 point of the bake-off |
| US-017 Screening retrieval: exact keys, hybrid text and photo search, RRF | 8 | Exact-key recall 100 %; recall@20 ≥ 0.90 (≥ 0.85 per slice) |
| US-018 Match / similar / clear with cascade and judge (stretch) | 5 | Cascade recall ≥ 0.98; precision@5 ≥ 0.80 |
| **Committed / with stretch** | **28 / 33** | |

Every story also carries its security part from the threat model (T1–T5, T12, T13).

## New release plan

| Sprint | Dates | Epic | Capacity |
|--------|-------|------|----------|
| Sprint 3 | 22–24 Nov | E3 Retrieval & Evaluation | ~35 points |
| Sprint 4 | 25–30 Nov | E4 Agentic Core | 6 days × 4–5 h ≈ 40 points |
| Sprint 5 | 1–8 Dec | E5 Product Interfaces + E7 RadarMart | 8 days × 4–5 h ≈ 55 points |
| Sprint 6 | 9–12 Dec | E6 Release & Operations | 4 days × 4–5 h ≈ 28 points |
| **v1.0.0** | **12 Dec 2026** | | |

E4 to E6 are not yet broken into stories; their size is checked in each sprint planning, and the release
date is confirmed or moved in each sprint review.

## Risks

| Risk | Mitigation |
|------|------------|
| Labelling the gold sets takes longer than planned | Start with the cases that can be built automatically from Safety Gate (photo + translated title, id removed); label the rest by hand |
| Embedding open-weight models on CPU is slow | Bake-off on the dev set only; batch jobs in Databricks; API model as a fallback |
| Only 2,000 alert photos stored so far | Image-only cases use alerts with stored photos; photo backfill (#43) stays open |
