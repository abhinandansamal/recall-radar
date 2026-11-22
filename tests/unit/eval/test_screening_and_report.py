"""Stage-by-stage screening evaluation, first failing stage and the report."""

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pytest
from eval_helpers import A1, A2, A3, matching

from rr_eval.gates import Status, evaluate_gates, load_gates
from rr_eval.report import RunInfo, load_metrics, render_markdown, write_report
from rr_eval.screening import ScreeningRun, evaluate_screening

REPO_GATES = Path(__file__).resolve().parents[3] / "evals" / "gates.yaml"


def screener_from(runs):
    """A stub screener that returns a fixed run per listing title."""
    return lambda query: runs[query.title]


def q(title):
    return {"title": title, "language": "en"}


def test_perfect_pipeline_passes_every_stage():
    case = matching(query=q("t1"), slices=["exact_key"])
    runs = {"t1": ScreeningRun(exact_hits=(A1,), candidates=(A1,), reranked=(A1,), label="match")}
    report = evaluate_screening([case], screener_from(runs))
    (result,) = report.results
    assert result.stages == {"exact_keys": True, "candidates": True, "rerank": True, "result": True}
    assert result.first_failing_stage is None
    assert report.metrics[("all", "exact_key_recall")].value == 1.0
    assert report.metrics[("exact_key", "recall@20")].value == 1.0


@pytest.mark.parametrize(
    ("run", "slices", "first"),
    [
        # exact-key case, exact step finds nothing although the later stages do
        (
            ScreeningRun(candidates=(A1,), reranked=(A1,), label="match"),
            ["exact_key"],
            "exact_keys",
        ),
        # exact step returns a wrong alert: false exact match
        (
            ScreeningRun(exact_hits=(A3,), candidates=(A1,), label="match"),
            ["re_upload"],
            "exact_keys",
        ),
        # retrieval misses: the reranker cannot fix it
        (
            ScreeningRun(candidates=(A2,), reranked=(A2,), label="clear"),
            ["re_upload"],
            "candidates",
        ),
        # retrieval finds it, rerank pushes it out of the top 5
        (
            ScreeningRun(
                candidates=(A1,),
                reranked=(A2, A3, "SR/00004/26", "SR/00005/26", "SR/00006/26", A1),
                label="match",
            ),
            ["re_upload"],
            "rerank",
        ),
        # everything ranked right, final label wrong
        (ScreeningRun(candidates=(A1,), reranked=(A1,), label="clear"), ["re_upload"], "result"),
    ],
)
def test_first_failing_stage(run, slices, first):
    case = matching(query=q("t"), slices=slices)
    report = evaluate_screening([case], screener_from({"t": run}))
    assert report.results[0].first_failing_stage == first
    assert report.failing_stage_counts == Counter({first: 1})


def test_stages_that_are_not_built_are_skipped():
    case = matching(query=q("t"))
    report = evaluate_screening([case], screener_from({"t": ScreeningRun(candidates=(A1,))}))
    assert report.results[0].stages == {"candidates": True}
    assert ("all", "precision@5") not in report.metrics
    assert ("all", "catch_rate") not in report.metrics


def test_leave_one_out_excludes_the_source_alert():
    case = matching(query=q("t"), relevant={A1: 2}, exclude_ids=[A2])
    run = ScreeningRun(candidates=(A2, A1))
    report = evaluate_screening([case], screener_from({"t": run}))
    assert report.metrics[("all", "mrr")].value == 1.0  # A2 removed, A1 now at rank 1


def test_safe_look_alikes_measure_false_alarms():
    safe = matching("M-0002", query=q("safe"), slices=["look_alike"], expected="clear", relevant={})
    danger = matching("M-0001", query=q("danger"))
    runs = {
        "safe": ScreeningRun(candidates=(A3,), label="similar"),
        "danger": ScreeningRun(candidates=(A1,), label="match", latency_ms=120.0),
    }
    report = evaluate_screening([danger, safe], screener_from(runs))
    m = report.metrics
    assert m[("all", "catch_rate")].value == 1.0
    assert m[("all", "false_alarm_rate")].value == 1.0
    assert m[("look_alike", "false_alarm_rate")].n == 1
    assert ("look_alike", "recall@20") not in m  # no relevant alerts, no recall
    assert m[("all", "latency_p95_ms")].value == 120.0
    assert report.results[1].first_failing_stage == "result"


def test_false_exact_match_rate_counts_only_wrong_hits():
    right = matching("M-0001", query=q("right"), slices=["exact_key"], relevant={A1: 2, A2: 1})
    wrong = matching(
        "M-0002", query=q("wrong"), slices=["look_alike"], expected="clear", relevant={}
    )
    runs = {
        "right": ScreeningRun(exact_hits=(A2,), candidates=(A1,)),  # similar hit, not wrong
        "wrong": ScreeningRun(exact_hits=(A3,)),
    }
    m = evaluate_screening([right, wrong], screener_from(runs)).metrics
    assert m[("all", "false_exact_match_rate")].value == pytest.approx(0.5)
    assert m[("all", "exact_key_recall")].value == 0.0  # no same-product exact hit


def test_report_with_repository_gates(tmp_path):
    cases = [
        matching(f"M-{i:04d}", query=q(f"t{i}"), slices=["re_upload", "cross_language"])
        for i in range(1, 5)
    ]
    runs = {f"t{i}": ScreeningRun(candidates=(A1,) if i < 4 else (A2,)) for i in range(1, 5)}
    report = evaluate_screening(cases, screener_from(runs))
    results = evaluate_gates(load_gates(REPO_GATES), "screening", report.metrics)
    by_metric = {(r.gate.metric, r.slice): r.status for r in results}
    assert by_metric[("recall@20", "all")] is Status.FAILED  # 3 of 4 = 0.75
    assert by_metric[("precision@5", "all")] is Status.NOT_RUN

    info = RunInfo(
        title="Screening dev run",
        workload="screening",
        dataset_version="matching-v1@abc",
        split="dev",
        commit="abc1234",
        created_at=datetime(2026, 11, 22, 18, 0, tzinfo=UTC),
        models={"text_embedding": "stub"},
    )
    md_path, json_path = write_report(
        tmp_path, info, results, report.metrics, report.failing_stage_counts
    )
    text = md_path.read_text(encoding="utf-8")
    assert "Result: **FAILED**" in text
    assert "| candidates | 1 |" in text
    assert md_path.name == "screening-dev-20261122T180000.md"
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["passed"] is False
    assert payload["first_failing_stage"] == {"candidates": 1}
    assert load_metrics(json_path)[("all", "recall@20")].value == pytest.approx(0.75)


def test_markdown_without_wrong_cases():
    info = RunInfo(
        title="t",
        workload="screening",
        dataset_version="d",
        split="dev",
        commit="c",
        created_at=datetime(2026, 11, 22, tzinfo=UTC),
        models={},
    )
    text = render_markdown(info, [], {}, Counter())
    assert "No wrong cases." in text
    assert "Result: **PASSED**" in text
