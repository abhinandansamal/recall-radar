# ADR-0001: Record architecture decisions

- Status: Accepted
- Date: 2026-11-08
- Feature: F01

## Context
Every tool, model and pattern in this project must be backed by a clear reason and evidence, both
for engineering quality and so the decisions can be explained in interviews. Decisions made only in
chat or in someone's head get lost.

## Options considered
| Option | Pros | Cons |
|--------|------|------|
| ADRs in the repo (Markdown, numbered) | Versioned with the code, reviewed in PRs, cheap | Needs discipline |
| Wiki / external docs | Rich editing | Drifts from the code, not reviewed with the change |
| No formal record | No effort | Reasons are forgotten, decisions get re-argued |

## Decision
We record each significant decision as a numbered ADR in `docs/adr/`, using `0000-template.md`.
An ADR is required when we choose between real alternatives (tool, model, pattern, data design).
The ADR is part of the PR that implements the decision.

## Consequences
Small overhead per feature. In return, the HLD/LLD documents can be assembled from the ADRs at the
end, and every "why X and not Y?" question has a written, evidenced answer.
