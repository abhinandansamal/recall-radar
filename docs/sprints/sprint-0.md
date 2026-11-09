# Sprint 0: Product Discovery (8 Nov 2026)

**Sprint goal:** Prove the problem is real and the data is usable, and set up a repo that enforces quality from the first commit.
**Result:** Goal met. 6 of 7 items done; S0-7 carried over.

## Sprint review

| Item | Outcome | Evidence |
|---|---|---|
| S0-1 Repo and quality gates | Done | PR #1, CI green (`quality`, `secret-scan`) |
| S0-2 Data availability check | Done | `docs/data/data-sources.md` |
| S0-3 Manual baseline, Study 1 | Done (stopped early) | `evals/baseline/README.md` |
| S0-4 Product decisions | Done | PD-001 two-trigger screening, PD-002 RadarMart |
| S0-5 PRD v1.0 | Done | `docs/product/Recall-Radar-PRD-v1.0.pdf` |
| S0-6 Backlog and board | Done | Project board: Sprint board, Epics, Roadmap |
| S0-7 Manual baseline, Study 2 | Carried over | Issue #15 → Sprint 1 |

**Key finding:** Matching Safety Gate alerts against ABO (Amazon's own catalogue) gave almost no matches, so a single-direction search adds no value. We pivoted to two-trigger screening (PD-001), with ABO as the "safe listings" background.

## Retrospective

**Went well**
- Checking the data by hand, before writing code, exposed a design flaw on Day 1 instead of Day 6.
- Quality gates (pre-commit, CI, branch protection) were in place before the first feature.

**To improve**
- Setup steps ran in the wrong order (hooks before `git init`; repo create before the first commit).
- One commit mixed several topics, and a hook rewrote a staged file.
- The upstream gitleaks hook needed `pass_filenames: false`.

**Actions for Sprint 1**
- Run each setup script step on a clean shell, and record the order in the Feature Card.
- One topic per commit; run `pre-commit run --all-files` before staging.
- Check every third-party hook's arguments before adding it.
