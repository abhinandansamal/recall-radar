"""Gate file loading and gate evaluation."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from rr_eval.gates import (
    Gate,
    GateError,
    MetricValue,
    Status,
    evaluate_gates,
    load_gates,
    run_passed,
)

REPO_GATES = Path(__file__).resolve().parents[3] / "evals" / "gates.yaml"


def gate(**overrides):
    data = {
        "workload": "screening",
        "stage": "candidates",
        "metric": "recall@20",
        "op": ">=",
        "threshold": 0.9,
    }
    data.update(overrides)
    return Gate.model_validate(data)


def mv(value, n=10):
    return MetricValue(value=value, n=n)


def test_repository_gates_file_is_valid():
    gates = load_gates(REPO_GATES)
    exact = [g for g in gates if g.metric == "exact_key_recall"]
    assert exact and exact[0].hard and exact[0].threshold == 1.0


def test_pass_fail_warning_and_not_run():
    gates = (
        gate(),
        gate(metric="recall@50", threshold=0.95, hard=False),
        gate(stage="rerank", metric="precision@5", threshold=0.8),
    )
    metrics = {("all", "recall@20"): mv(0.92), ("all", "recall@50"): mv(0.93)}
    results = evaluate_gates(gates, "screening", metrics)
    assert [r.status for r in results] == [Status.PASSED, Status.WARNING, Status.NOT_RUN]
    assert run_passed(results)


def test_failed_hard_gate_fails_the_run():
    results = evaluate_gates((gate(),), "screening", {("all", "recall@20"): mv(0.5)})
    assert results[0].status is Status.FAILED
    assert not run_passed(results)


def test_each_slice_is_judged_separately():
    metrics = {
        ("all", "recall@20"): mv(0.95),
        ("de", "recall@20"): mv(0.80),
        ("en", "recall@20"): mv(0.99),
    }
    results = evaluate_gates((gate(slice="each", threshold=0.85),), "screening", metrics)
    assert {r.slice: r.status for r in results} == {"de": Status.FAILED, "en": Status.PASSED}


def test_other_workloads_are_ignored_and_operators_work():
    gates = (
        gate(workload="assistant"),
        gate(metric="false_alarm_rate", op="<=", threshold=0.05),
        gate(metric="false_exact_match_rate", op="==", threshold=0.0),
    )
    metrics = {("all", "false_alarm_rate"): mv(0.04), ("all", "false_exact_match_rate"): mv(0.0)}
    results = evaluate_gates(gates, "screening", metrics)
    assert [r.status for r in results] == [Status.PASSED, Status.PASSED]
    assert results[0].target == "<= 0.05"


def test_no_regression_compares_with_baseline():
    g = gate(metric="mrr", op="no_regression", tolerance=0.02, threshold=None)
    metrics = {("all", "mrr"): mv(0.70)}
    assert evaluate_gates((g,), "screening", metrics)[0].status is Status.NOT_RUN
    ok = evaluate_gates((g,), "screening", metrics, baseline={("all", "mrr"): mv(0.71)})
    bad = evaluate_gates((g,), "screening", metrics, baseline={("all", "mrr"): mv(0.75)})
    assert ok[0].status is Status.PASSED
    assert bad[0].status is Status.FAILED
    assert bad[0].target == "no drop > 0.02"


def test_gate_needs_threshold_or_tolerance():
    with pytest.raises(ValidationError, match="needs a threshold"):
        gate(threshold=None)
    with pytest.raises(ValidationError, match="needs a tolerance"):
        gate(op="no_regression", threshold=None)


def test_broken_gate_files(tmp_path):
    with pytest.raises(GateError, match="not found"):
        load_gates(tmp_path / "missing.yaml")
    bad = tmp_path / "gates.yaml"
    bad.write_text("version: 1\ngates: []\n", encoding="utf-8")
    with pytest.raises(GateError, match=r"gates\.yaml"):
        load_gates(bad)
    bad.write_text("version: [1\n", encoding="utf-8")
    with pytest.raises(GateError, match=r"gates\.yaml"):
        load_gates(bad)
