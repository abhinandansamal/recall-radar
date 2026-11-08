## What and why
<!-- One or two sentences. Link the story: Closes #<issue> -->

Feature: F__ · Story: US-___

## Decision(s)
<!-- Link the ADR, or write "no new decision". -->

## Definition of Done
- [ ] Tests written first (red commit before green commit)
- [ ] `make check` passes locally (lint, format, mypy strict, tests, coverage ≥ 85%)
- [ ] Google-style docstrings on all public functions
- [ ] JSON log events added for new behaviour (INFO / ERROR), no secrets or personal data in logs
- [ ] Security review done (input validation, secrets, OWASP LLM items if relevant)
- [ ] Evaluation report added: `evals/reports/F__.md` (if the feature has a metric)
- [ ] ADR + devlog updated
- [ ] CI green

## Test evidence
<!-- Paste the pytest summary line, or link the CI test-report artifact. -->
