# PD-001: Two-trigger screening instead of alert-only catalogue search

- Status: Accepted
- Date: 2026-11-08
- Decided by: Product Owner, after Manual study 1

## Context
The first concept took each new Safety Gate alert and searched a catalogue for it. In Manual study 1 the
Product Owner searched the public demo catalogue (ABO) by alert name, category and model: almost every
search returned unrelated products or "no match". Analysis of two years of alerts showed that dangerous
products are sold on large marketplaces (677 alerts name the marketplace) and that the same products
return (443 repeat alerts; documented re-uploads after takedown).

## Options
| Option | Assessment |
|--------|-----------|
| A. Alert → catalogue only | Right for a real marketplace catalogue, but misses re-uploads after the alert, and cannot be demonstrated honestly with public data |
| B. Listing → all alerts only | Catches re-uploads at upload; misses products already listed before the alert |
| **C. Both triggers + nightly reconciliation** | Covers both cases; demonstrable with public data (Safety Gate re-uploads + ABO safe listings) |

## Decision
Option C. Trigger A: every new or changed listing is checked against all known dangerous products.
Trigger B: every new alert is checked against the whole catalogue. A nightly run re-checks changes.

## Consequences
- ABO's role changes to "normal, safe listings" (false-alarm and speed measurement).
- Test cases with known truth come from Safety Gate itself (photo + translated title, without the ID).
- The baseline study is redone in the new direction (Manual study 2).
