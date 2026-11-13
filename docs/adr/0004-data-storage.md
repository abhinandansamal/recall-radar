# ADR-0004: Data and storage design (lakehouse + one Postgres server)

- Status: Accepted
- Date: 2026-11-13
- Feature: F03, F04, F05 (US-007 to US-012)

## Context

Recall Radar ingests three public sources (Safety Gate alerts with photos, the ABO catalogue, the GPSR text),
screens marketplace listings in seconds, and records human decisions with legal weight. RadarMart is a
separate demonstration marketplace. Constraints: ≤ €30 per month, EU only, one developer, Postgres B1ms
(1 vCore, 2 GiB RAM, 32 GB) on the free tier, listing check p95 ≤ 10 s. Full analysis, estimates and
diagrams: [data and storage design](../architecture/data-storage-design.md).

Estimate (section 4 of the design): up to 100,000 alerts and 330,000 alert photos. With full-precision
vectors and separate EN and DE text vectors, vectors need ~1.6 GB, which does not fit next to the app data
in 2 GiB RAM.

## Options considered

| Topic | Option | Pros | Cons |
|-------|--------|------|------|
| Vector memory | Bigger Postgres server | No compromise | Leaves free tier; budget risk |
| | Separate vector/search service | Scales further | Extra cost and system; breaks "one database" |
| | **`halfvec` + one text vector per alert (+ fewer old photos if needed)** | **~0.7 GB, fits; same design** | Small precision loss; cross-language recall must be measured |
| Safety Gate photos | Hash + embedding only | Lowest licence risk | Every model change re-downloads ~330k photos (~18 h); results not reproducible if EC changes photos |
| | **Private copy in the lake, never served** | **Fast re-embedding, reproducible evals, dedup by SHA-256** | ~50 GB storage for full history; controlled licence risk |
| RadarMart data | Shared database and tables | Least code | Hidden coupling; checker reads buyer data; contradicts PD-002 |
| | Separate server | Strongest isolation | Double cost |
| | **Own database on the same server, events + connector** | **Clear ownership, realistic, same cost** | Event code (outbox, dedup, retries); seconds of delay |

## Decision

1. The **lakehouse is the source of truth for ingested public data**; Postgres `kb` is a derived copy loaded
   from gold with staging tables and an atomic swap.
2. **Postgres `recall_radar.app` is the source of truth** for snapshots, screenings, cases, reviews, actions,
   outbox and audit log (strong consistency).
3. Vectors are stored as **`halfvec`** with **one text vector per alert** (multilingual model). Image vectors for
   older alerts are reduced only if memory measurements require it.
4. **Exact keys (GTIN, brand + model) are matched with B-tree indexes before any AI step.**
5. Safety Gate photos are kept as a **private copy**, once per SHA-256, in the `bronze.images` volume; they are
   never served publicly; the UI shows the official EC image URL; licence and source URL are stored per
   image; a deletion request removes file, row and vector. Photos are downloaded **newest years first**.
6. **RadarMart owns its own database** (`radarmart`) on the same server. It sends signed listing events
   (transactional outbox); Recall Radar stores an **immutable snapshot** of every checked listing and never
   stores buyer contact data; buyer notices are sent by RadarMart through the catalogue connector after approval.
7. No managed Redis, search engine or vector database for now; triggers for adding them are listed in
   section 12 of the design.

This decision replaces the provisional note in `docs/data/data-sources.md` ("store link + hash + embedding,
not the photo").

## Consequences

- Easier: re-embedding and model comparison (F06); reproducible evals; one database to operate; audit evidence
  that cannot change after the decision.
- Harder: event plumbing between RadarMart and Recall Radar; an export job with contract tests; photo backfill
  takes many hours.
- Monitor: vector recall@20 on the gold set (≥ 0.90), Postgres cache hit ratio and p95 search time,
  lake storage growth, Databricks cost per run.
- Revisit when: recall with `halfvec` or single-language vectors misses the target; memory pressure appears;
  the Commission states photo terms that forbid private copies; a real catalogue with millions of listings is
  connected.

## Proof

- Estimates: real run in section 4 of the [design](../architecture/data-storage-design.md).
- Data facts: [data sources](../data/data-sources.md) (Sprint 0 measurements).
- Method: Storage 01 (CAP, consistency) and Storage 07 (choosing storage) learning notes; Kleppmann,
  *Designing Data-Intensive Applications*.
- Recall measurements will be added after F06.
