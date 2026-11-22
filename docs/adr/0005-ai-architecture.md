# ADR-0005: AI architecture (three workloads, evaluation at every stage, security by design)

- Status: Accepted (Product Owner, 2026-11-16)
- Date: 2026-11-16
- Feature: F06, F07, F08 (E3) and F09–F12 (E4)

## Context

Sprints 0–2 built the data platform: 47,580 alerts per language with identifiers, photos and EN/DE keyword
search in Postgres (`kb`), empty vector columns (`halfvec(1024)` text, `halfvec(512)` image), the GPSR
text and the ABO catalogue in bronze. The AI part must meet the design brief targets (100 % exact-match
recall, recall@20 ≥ 0.90, precision@5 ≥ 0.80, catch rate ≥ 90 %, false alarms ≤ 5 %, citation correctness
≥ 95 %, listing check p95 ≤ 10 s) within **≤ €30 per month**, EU only, German and English.

Recall Radar has three different AI workloads with different needs:

| Workload | Volume | Needs |
|----------|--------|-------|
| W1 Screening (listing ↔ alerts, both triggers) | High (every listing event) | Fast, predictable, cheap, exact-match guarantee |
| W2 Compliance assistant (questions EN/DE) | Low | Correct legal citations, routing to the right source |
| W3 Case workflow (evidence → legal duty → actions) | Low | Several tools, a pause for a human, actions with legal weight |

## Options considered

| Topic | Option | Pros | Cons |
|-------|--------|------|------|
| Overall pattern | One agent for everything | One code path | Slow and costly for high-volume screening; harder to test; more attack surface |
| | **Level per workload: W1 fixed pipeline, W2 routed RAG, W3 one agent with approval** | **Simplest level that meets each target; cheap screening; agent only where needed** | Three code paths to maintain |
| | Multi-agent system | Parallel research | ~15× tokens; no use case for it |
| Store | Separate vector DB or search engine | More search features | Extra cost and system; not needed at ~0.7 GB of vectors |
| | **Postgres + pgvector (existing)** | **One system, transactions, roles/RLS, free tier** | Weaker German compound handling than a search engine (mitigated by vectors + `pg_trgm`) |
| Framework | LangGraph everywhere | Uniform | Unneeded complexity for fixed pipelines |
| | **Plain code for W1/W2, LangGraph for W3, MCP for tools, A2A for the legal agent** | **Each tool used where it adds value** | Two styles in one codebase |
| Evaluation | End-to-end LLM-judge scores only | Cheap to start | Cannot locate failures; judge bias |
| | **Gate per stage with its own metric and threshold, plus end-to-end** | **A bad stage is found where it fails, before later stages hide it** | More datasets and labels |
| Security | Rely on prompts and the LLM to behave | Little work | Not a control; injection cannot be fully prevented |
| | **Security by design: controls in code, data and roles; attack tests as gates** | **Holds even if the model is manipulated** | More tests and reviews per story |

## Decision

1. **Three workloads, each at the simplest level that meets its target:**
   - W1 screening is a **fixed pipeline in plain Python** (`rr_retrieval`): exact keys first (deterministic),
     then hybrid keyword (EN/DE) + text vector + photo vector candidates fused with RRF (k = 60), then a
     **cascade**: only listings above a retrieval threshold go to the rerank/LLM judge (structured output).
   - W2 assistant: **one planner call** (route, standalone question, filters, language) → GPSR RAG,
     lookup tools, predefined KPI queries, refusal or clarification. Every legal answer is verified.
   - W3 case workflow: **one LangGraph agent** with Postgres checkpoints and `interrupt()` for reviewer
     approval; tools via **MCP servers** (`kb-search`, `cases`, `marketplace`); the legal duty comes from an
     **A2A legal agent** reused by the assistant (dropped first if time runs short).
2. **Postgres + pgvector stays the only store** for keyword, vector, app data and agent checkpoints.
3. **Models are chosen per role by a bake-off on our own gold sets** (ADR-0006). Start candidates: Mistral
   (EU) for LLM, embeddings and moderation; open-weight `bge-m3`/`multilingual-e5-large`, OpenCLIP/SigLIP
   and `bge-reranker-v2-m3` as alternatives. Every vector stores its `embedding_model`.
4. **Gold sets come first** (matching 150, legal 50, adversarial 40, routing 60, baseline 10), with a
   dev/test split and a frozen holdout.
5. **Evaluation at every stage (PO rule, 16 Nov):** each stage of each workload has a named metric, a
   dataset slice and a threshold in `evals/gates.yaml`. A stage that fails its gate blocks the stages built
   on it: we do not tune a reranker on top of retrieval that misses the evidence. Every wrong result is
   labelled with its **first failing stage**. Details: [evaluation gates](../testing/evaluation-gates.md).
6. **Security by design (PO rule, 16 Nov):** a threat model ([threat model](../security/threat-model.md))
   names the controls per stage. Controls live in code, data and database roles, never only in prompts:
   - untrusted text (listings, questions) is labelled and sanitised;
   - exact-key matches can never be overruled by the LLM;
   - tools get identity from the session and have no role parameters;
   - actions follow Plan-Then-Execute and need reviewer approval;
   - recipients come only from SQL;
   - every legal citation and deadline is verified.

   Attack tests are gates like quality tests: **zero** critical attack successes and **zero** safety
   violations.
7. **Not built in v1:** GraphRAG, multi-agent research, a separate vector store, a semantic answer cache,
   fine-tuning, free text-to-SQL, query expansion techniques (unless a slice fails).

Feature mapping: F06 embeddings and screening retrieval; F07 reranking/judge and cited legal answers;
F08 gold sets, evaluation harness and gates. E4 (F09–F12): LLM gateway, MCP, LangGraph case workflow,
guardrails.

## Consequences

- Easier: locating failures (per-stage metrics); keeping screening cheap (no LLM for clear listings);
  changing a model (versioned vectors, export swap as blue-green).
- Harder: labelling effort for gold sets; more CI jobs; every AI story carries an eval and a security part.
- Definition of Done for AI stories adds: gate results in `evals/reports/`, and the story's threats from the
  threat model tested.
- Revisit when: a stage misses its gate after two attempts; German recall per slice fails; LLM cost goes
  over the budget share; the A2A legal agent does not pay for its operating effort.

## Proof

- Design plan with the review of the 11 RAG + Agents design documents: `AI-Design-Plan` (16 Nov 2026,
  shared with the PO).
- Gate results: `evals/reports/F06.md`, `F07.md`, `F08.md` (from Sprint 3).
- Sources for model facts: Mistral pricing and regional inference pages, `bge-reranker-v2-m3` model card
  (checked 2026-11-16; re-checked in the bake-off).
