# Evaluation data and gates

How we measure every stage of every AI workload: [evaluation gates](../docs/testing/evaluation-gates.md).

| Path | What |
|------|------|
| `gates.yaml` | Thresholds per workload, stage, metric and slice. Changing one needs a PR with a reason. |
| `data/<set>/v1.jsonl` | Gold set, dev + test splits. One JSON case per line. |
| `data/<set>/v1.holdout.jsonl` | Holdout split. Used only for the final report, never for tuning. |

Sets: `matching` (W1 screening), `legal` (W2 legal RAG), `adversarial` (security), `routing` (W2 planner).
Every file is validated in CI (`tests/unit/eval/test_gold_set_files.py`).

## Matching set

Built by `pipelines/eval/matching_gold_set.py` from our gold tables:

- Repeat alerts of the same product (shared GTIN or brand + model), leave-one-out, in five
  variants: with identifiers, without identifiers, German text, photo only, evasion.
- Safe look-alikes from the ABO catalogue (expected result "clear").
- Splits per product: 60 % dev, 30 % test, 10 % holdout.

## Sources and licences

- Safety Gate alerts: European Commission, reuse allowed with acknowledgement of the source
  (Commission Decision 2011/833/EU). `source` field: `safety_gate:<case number>`.
- Amazon Berkeley Objects: CC BY 4.0, Amazon.com. `source` field: `abo:<item_id>`.
