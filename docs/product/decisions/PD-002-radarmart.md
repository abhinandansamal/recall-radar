# PD-002: Build RadarMart, a production-grade demonstration marketplace

- Status: Accepted
- Date: 2026-11-08
- Decided by: Product Owner

## Context
Recall Radar is used by marketplaces. To show it working end to end, a live system is needed in which
sellers create listings, buyers order, and approved actions (removal, seller notice, buyer recall
notice) become visible. No real marketplace data or API can be used.

## Options
| Option | Assessment |
|--------|-----------|
| Script that only sends fake events | Cheap, but the loop (removal, buyer notice) is invisible; weak demo |
| Minimal one-page seller form | Shows Trigger A only; no orders, so buyer recall notices cannot be shown |
| **Full demonstration marketplace (storefront, cart, simulated checkout, orders, seller portal, back office)** | Shows every journey in the PRD; also demonstrates secure web engineering |

## Decision
Build RadarMart to production standards (security, roles, bilingual UI, tests), with **simulated payment**
(no real money) and only demo personal data. It connects to Recall Radar exactly like a real marketplace:
signed listing events in, catalogue connector out.

## Consequences
- Additional scope (estimated about 2 working days); Timeline extended from 10 to 12 days (decided 08.11.2026).
- Buyer recall notice (GPSR duty to inform consumers) becomes demonstrable.
- RadarMart gets its own epic, backlog and tests.
