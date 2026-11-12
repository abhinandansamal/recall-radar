# Recall Radar: design brief

- Status: Draft for approval (Product Owner)
- Date: 2026-11-11
- Sources: [PRD v1.0](product/product-requirements.md), [data sources](data/data-sources.md),
  [baseline report](../evals/reports/baseline.md), [test strategy](testing/test-strategy.md)

This page is the bridge between the PRD (what and why) and the architecture (how). It states the
requirements as testable numbers and the constraints that rule options out.

## 1. Problem frame

| Area | Answer |
|------|--------|
| **User and job** | Product-safety analyst (Lena) screens listings against known dangerous products; compliance reviewer (Markus) approves actions. Today: manual Safety Gate search, **median ~10 min per listing**, 7/9 correct, 4/5 dangerous products found (Study 2) |
| **Frequency** | ~90 new alerts per week (Friday report); every new or changed listing; nightly re-check |
| **Value metric** | Analyst minutes per check and catch rate vs baseline; time from alert or upload to reviewed decision; deadline compliance (2 / 3 working days) |
| **Inputs** | Listings: title and description (DE/EN, any marketplace wording), photos, EAN, brand, model. Alerts: Safety Gate XML (EN + DE), photo URLs. Chat: free-text questions in DE/EN |
| **Knowledge** | Safety Gate alerts (European Commission, 2005 to today, ~4,700 per year, weekly, append + update); GPSR text (EUR-Lex, versioned by consolidation date); marketplace catalogue (owned by the marketplace; demo: ABO + RadarMart) |
| **Languages** | German and English (UI, explanations, chat, notices) |

## 2. Actions and human control

| Action | Type | Reversible? | Human approval |
|--------|------|-------------|----------------|
| Read alerts, listings, GPSR text | Read | n/a | No |
| Open a case, attach evidence | Internal write | Yes | No |
| Notify team (Discord, Gmail) | External message | No (sent) | No: internal team only, no personal data |
| Remove / reinstate listing | Write to marketplace | Yes (reinstate) | **Yes**, reviewer |
| Seller notice | External message | **No** | **Yes**, reviewer |
| Buyer recall notice | External message to consumers | **No** | **Yes**, reviewer (four-eyes in v1.1) |

## 3. Quality bar

| Error | Severity | Control |
|-------|----------|---------|
| Look-alike flagged as `similar` | Tolerable (costs reviewer time) | False-alarm KPI |
| Explanation slightly unclear | Tolerable | Readability metric, reviewer edits |
| **Exact-identifier match missed** (same EAN or brand + model as an alert) | **Catastrophic** | Deterministic exact-key match before any AI step; recall 100 % on exact-key gold cases |
| **Action executed without approval** | **Catastrophic** | HITL gate in the workflow; tests in the red-team set |
| **Notice sent to the wrong buyers or seller** | **Catastrophic** | Recipients derived only from order data of the approved listing; preview before send |
| **Invented legal citation or deadline** | **Catastrophic** | Citations only from retrieved GPSR passages; claim verifier; abstain if unsupported |
| Personal data or secrets in logs | Serious | Redaction (F01), demo data only |
| Prompt injection in listing or alert text changes behaviour | Serious | Input isolation, guardrails, adversarial test set |

## 4. Success criteria (testable)

**Component metrics**

| Component | Metric | Target |
|-----------|--------|--------|
| Exact-key matcher | Recall on exact EAN / brand + model cases | 100 % |
| Candidate retrieval (text + image) | Recall@20 on gold set | ≥ 0.90 |
| Reranker | Precision@5 | ≥ 0.80 |
| LLM structured outputs | JSON schema validity | 100 % (retry, then fail safely) |
| Agent tool calls | Correct tool + arguments | ≥ 95 % |
| Legal RAG | Context recall on legal questions | ≥ 0.90 |

**End-to-end quality**

| Metric | Target |
|--------|--------|
| Catch rate (match or similar) on dangerous gold listings | ≥ 90 % (baseline 80 %) |
| False-alarm rate on safe gold listings | ≤ 5 % |
| Faithfulness of explanations and chat answers | ≥ 0.95 |
| Citation correctness | ≥ 95 % |
| Agent task success (case prepared correctly) | ≥ 80 % |

**Operational**

| Metric | Target |
|--------|--------|
| Listing check, event → result | p95 ≤ 10 s |
| Back-scan after a new alert | ≤ 5 min for the demo catalogue |
| Chat | first token ≤ 3 s, full answer ≤ 10 s (p95, warm) |
| Analyst minutes per check | median ≤ 2 min (baseline ~10 min) |
| Error rate | < 1 % of requests |
| Availability | 99 % during demo period (cold start allowed) |
| Cost | ≤ €30 per month total; cost per 1,000 checks reported |

## 5. Volume (demo assumptions)

~1,000 listing checks per day (simulator), ~90 new alerts per week, up to 5 concurrent chat users,
catalogue of 10,000 to 15,000 listings. Budget per listing check: well below €0.01.

## 6. Data, compliance and risk

| Topic | Decision |
|-------|----------|
| Data location | EU only: Azure Germany West Central; Postgres in France Central (flexible server not offered in Germany West Central for this subscription); Langfuse EU region; LLM provider Mistral (EU company; processing region confirmed in F06) |
| Personal data | Demo buyer and seller data only (synthetic); no real personal data |
| Retention | Application logs 30 days; traces 30 days; cases and audit log kept for the demo lifetime (production: per legal retention duty) |
| GDPR | Data minimisation, redaction in logs, deletion on request (PRD K6) |
| EU AI Act | Own assessment (not legal advice): not an Annex III high-risk use; transparency duties of Art. 50 apply (users told when content is AI-generated) |
| Licences | Safety Gate: Commission reuse with attribution; ABO: CC BY 4.0; EUR-Lex: reuse with attribution |

## 7. Golden datasets (versioned in `evals/data/`)

| Set | Size (v1) | Built from | Tags |
|-----|-----------|-----------|------|
| Matching | 150 cases: 60 dangerous, 60 safe look-alikes, 30 edge | Safety Gate alerts (photo + translated title, ID removed); ABO listings in overlapping categories | exact-key, brand+model, image-only, cross-language, look-alike, re-upload, no-identifier |
| Legal Q&A | 50 questions with expected articles | GPSR Art. 19, 22 etc.; written by the PO, reviewed twice | simple lookup, multi-hop, out-of-scope, DE vs EN |
| Adversarial | 40 inputs | Own attack set (OWASP LLM Top 10) | injection in listing, injection in alert, jailbreak, PII extraction, unapproved action |
| Baseline | 10 listings | Study 2 | used for before/after comparison |

Rule: dev/test split fixed before tuning; test split never used to change prompts.

## 8. Constraints that rule options out

| Constraint | Consequence |
|-----------|-------------|
| ≤ €30 per month | Scale-to-zero hosting (Container Apps), small/efficient models, AKS only as a proof run, Databricks jobs on demand |
| EU-only processing | Azure EU region, EU-hosted LLM provider, Langfuse EU |
| One developer, 12 days | Managed services, one database (Postgres + pgvector) for vectors and app data |
| Public data only | Safety Gate, ABO, EUR-Lex; RadarMart simulates the marketplace |
| Human approval for external effects | Agent workflow with explicit approval state; no autonomous sending |
