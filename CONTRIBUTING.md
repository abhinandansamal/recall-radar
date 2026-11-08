# Working agreement

This project follows Scrum, adapted for a team of one (Product Owner + Developer) with an external
architect/reviewer. Everything below applies to every change, without exception.

## Flow of work

1. Pick a story from **Ready** on the project board and move it to **In Progress**.
2. Create a branch from `main`: `feat/F01-repo-bootstrap`, `fix/<short-name>`, `docs/<short-name>`.
3. **Red:** commit failing tests first (`test(F01): ...`).
4. **Green:** implement until tests pass (`feat(F01): ...`).
5. **Refactor**, then `make check`.
6. Open a PR using the template. CI must be green. Squash-merge into `main`.
7. Move the story to **Done** only when the Definition of Done is met.

`main` is protected: no direct pushes, PR + green CI required. The pre-commit hook also refuses
commits on `main`.

## Commit messages: Conventional Commits

`<type>(<scope>): <summary>` with type in `feat | fix | test | refactor | docs | chore | ci | build | perf`.
Example: `feat(F01): add JSON logging with correlation IDs`. These messages generate the changelog
for the release.

## Definition of Ready (before a story enters a sprint)

- Story written as "As a ..., I want ..., so that ..."
- Acceptance criteria in Given / When / Then form, all testable
- Evaluation metric named (if the story has measurable quality)
- Dependencies known; estimated in story points (1, 2, 3, 5, 8)

## Definition of Done

Test layers and gates: see [docs/testing/test-strategy.md](docs/testing/test-strategy.md).

- Tests written first; unit tests pass; integration tests pass where relevant
- `make check` green: ruff, ruff format, mypy strict, coverage ≥ 85 % on core packages
- Google-style docstrings on public functions and classes
- JSON log events for new behaviour; no secrets or personal data in logs
- Security review done (secrets, input validation, OWASP Top 10 for LLM apps where relevant)
- Evaluation report `evals/reports/Fxx.md` (if the feature has a metric)
- ADR written for every decision with alternatives; devlog updated
- PR merged with green CI; deployed to **Test** and acceptance criteria shown there (from F17 on)

## Environments

| Env  | Where                         | Deployed by                        |
|------|-------------------------------|------------------------------------|
| dev  | your Mac (Docker Compose)     | you                                |
| test | Azure Container Apps `rr-test`| automatically on merge to `main`   |
| prod | Azure Container Apps `rr-prod`| git tag `vX.Y.Z` + manual approval |

## Secrets

Never commit secrets. Local: `.env` (git-ignored, copy from `.env.example`). Test/Prod: Azure Key
Vault, read by managed identity. CI authenticates to Azure with OIDC, so no cloud keys live in GitHub.

## Scrum events (time-boxed)

| Event                 | When                 | Time-box | Output                                 |
|-----------------------|----------------------|----------|----------------------------------------|
| Sprint planning       | first day of sprint  | 30 min   | Sprint goal + sprint backlog           |
| Daily stand-up        | start of each day    | 10 min   | `docs/devlog/YYYY-MM-DD.md`            |
| Sprint review         | last day of sprint   | 30 min   | Demo GIF + evaluation reports          |
| Retrospective         | after review         | 15 min   | Start / Stop / Continue in devlog      |
