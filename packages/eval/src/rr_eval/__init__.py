"""Gold sets, metrics and per-stage gates for the Recall Radar AI workloads.

Every stage of every AI workload is measured on its own (see ``docs/testing/evaluation-gates.md``):
a later stage cannot fix an earlier one, so each stage passes its gate before the next one is
built or tuned on top of it.
"""
