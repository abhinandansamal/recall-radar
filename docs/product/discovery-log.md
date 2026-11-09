# Sprint 0: Product Discovery log

Sprint 0 = **Product Discovery / Inception**. Goal: prove that the problem is real, the data exists and
the value is measurable **before** any code is written. Each entry links to its evidence.

| # | Date | Step | Outcome | Evidence |
|---|------|------|---------|----------|
| 1 | 08.11.2026 | Market scan: 3 problem candidates (supply chain, banking, e-commerce) | E-commerce product safety (GPSR) chosen: stable law, real pain, fits multi-modal AI | this log; PRD §2 |
| 2 | 08.11.2026 | Regulatory check (GPSR, DSA, ProdSG, EU AI Act) | Marketplace duties, deadlines and fines confirmed with sources | PRD §2.3 |
| 3 | 08.11.2026 | Data availability check (Safety Gate, ABO, GPSR) | All three live, licensed, parsed; field coverage measured | `docs/data/data-sources.md` |
| 4 | 08.11.2026 | Manual study 1: alert → catalogue by hand | Mostly "no match"; keyword/category search fails; catalogue rarely contains alerted products | `evals/baseline/README.md` (Study 1), `manual_baseline_2026-11-08.csv` |
| 5 | 08.11.2026 | Two-year data analysis (104 reports, 8,739 alerts) | 677 alerts name a marketplace (Amazon 213 ...); 443 repeat alerts; re-upload problem confirmed | `docs/data/data-sources.md` (Direction change) |
| 6 | 08.11.2026 | **Product decision PD-001**: two-trigger screening (listing → all alerts; alert → whole catalogue) | Design changed based on evidence | `docs/product/decisions/PD-001-two-trigger-screening.md` |
| 7 | 08.11.2026 | **Product decision PD-002**: RadarMart demonstration marketplace | Full end-to-end loop can be shown; buyer recall notice becomes demonstrable | `docs/product/decisions/PD-002-radarmart.md` |
| 8 | 08.11.2026 | PRD v1.0 written | Problem, users, features (MoSCoW), KPIs, risks | `docs/product/product-requirements.md` (+ PDF) |
| 9 | 09.11.2026 | Manual study 2: 10 listings → Safety Gate by hand (timed baseline) | 7/9 correct, catch rate 4/5, median ~10 min per listing; title and EAN search fail | `evals/reports/baseline.md` |
| 10 | 09.11.2026 | Sprint 0 review and retrospective | Sprint goal met: 6 of 7 items done; S0-7 carried over to Sprint 1 (#15); 3 improvement actions agreed; Sprint 1 planned (12 stories, F01–F05); PRD v1.0 approved by Product Owner | `docs/sprints/sprint-0.md`, release `sprint-0` |

## What a reviewer should take away

1. The problem and its value were validated with public facts **and** first-hand evidence.
2. A wrong assumption (the catalogue would contain alerted products) was found by testing, not after
   building, and the product was changed with a recorded decision.
3. Success is defined as measurable KPIs with a manual baseline, before development starts.
