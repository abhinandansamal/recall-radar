"""Write an evaluation run as Markdown (for people) and JSON (for comparing runs).

Every report records what produced it: dataset version, commit, models, prompt version and
time. Without these, two numbers cannot be compared.
"""

import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from rr_eval.gates import GateResult, MetricValue, Status, run_passed


@dataclass(frozen=True)
class RunInfo:
    """What produced the numbers in a report."""

    title: str
    workload: str
    dataset_version: str
    split: str
    commit: str
    created_at: datetime
    models: Mapping[str, str]
    prompt_version: str = "-"


def render_markdown(
    info: RunInfo,
    gate_results: list[GateResult],
    metrics: Mapping[tuple[str, str], MetricValue],
    failing_stages: Counter[str],
) -> str:
    """Render the run as a Markdown report."""
    verdict = "PASSED" if run_passed(gate_results) else "FAILED"
    lines = [
        f"# {info.title}",
        "",
        f"- Result: **{verdict}**",
        f"- Workload: {info.workload}, split: {info.split}",
        f"- Dataset: `{info.dataset_version}`",
        f"- Commit: `{info.commit}`, time: {info.created_at.isoformat(timespec='seconds')}",
        f"- Models: {', '.join(f'{k}={v}' for k, v in sorted(info.models.items())) or '-'}",
        f"- Prompt version: {info.prompt_version}",
        "",
        "## Gates",
        "",
        "| Stage | Metric | Slice | Value | n | Target | Hard | Status |",
        "|-------|--------|-------|------:|--:|--------|:----:|--------|",
    ]
    for r in gate_results:
        value = f"{r.value.value:.3f}" if r.value else "-"
        n = str(r.value.n) if r.value else "-"
        hard = "yes" if r.gate.hard else "no"
        lines.append(
            f"| {r.gate.stage} | {r.gate.metric} | {r.slice} | {value} | {n} | {r.target} "
            f"| {hard} | {_status(r.status)} |"
        )
    lines += ["", "## First failing stage", ""]
    if failing_stages:
        lines += ["| Stage | Wrong cases |", "|-------|------------:|"]
        lines += [f"| {stage} | {count} |" for stage, count in failing_stages.most_common()]
    else:
        lines.append("No wrong cases.")
    lines += ["", "## All metrics", "", "| Slice | Metric | Value | n |", "|---|---|---:|--:|"]
    for (slice_name, metric), measured in sorted(metrics.items()):
        lines.append(f"| {slice_name} | {metric} | {measured.value:.3f} | {measured.n} |")
    return "\n".join(lines) + "\n"


def write_report(
    folder: Path,
    info: RunInfo,
    gate_results: list[GateResult],
    metrics: Mapping[tuple[str, str], MetricValue],
    failing_stages: Counter[str],
) -> tuple[Path, Path]:
    """Write ``<name>.md`` and ``<name>.json`` and return both paths.

    The name is ``<workload>-<split>-<YYYYMMDDTHHMMSS>``, so reports never overwrite each other.
    """
    folder.mkdir(parents=True, exist_ok=True)
    stem = f"{info.workload}-{info.split}-{info.created_at.strftime('%Y%m%dT%H%M%S')}"
    md_path = folder / f"{stem}.md"
    json_path = folder / f"{stem}.json"
    md_path.write_text(
        render_markdown(info, gate_results, metrics, failing_stages), encoding="utf-8"
    )
    payload = {
        "info": {
            "title": info.title,
            "workload": info.workload,
            "dataset_version": info.dataset_version,
            "split": info.split,
            "commit": info.commit,
            "created_at": info.created_at.isoformat(),
            "models": dict(info.models),
            "prompt_version": info.prompt_version,
        },
        "passed": run_passed(gate_results),
        "gates": [
            {
                "stage": r.gate.stage,
                "metric": r.gate.metric,
                "slice": r.slice,
                "value": r.value.value if r.value else None,
                "n": r.value.n if r.value else None,
                "target": r.target,
                "hard": r.gate.hard,
                "status": r.status.value,
            }
            for r in gate_results
        ],
        "metrics": [
            {"slice": s, "metric": m, "value": v.value, "n": v.n}
            for (s, m), v in sorted(metrics.items())
        ],
        "first_failing_stage": dict(failing_stages),
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return md_path, json_path


def load_metrics(json_path: Path) -> dict[tuple[str, str], MetricValue]:
    """Read the metrics of an earlier report (the baseline for ``no_regression`` gates)."""
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    return {
        (item["slice"], item["metric"]): MetricValue(value=float(item["value"]), n=int(item["n"]))
        for item in payload["metrics"]
    }


def _status(status: Status) -> str:
    return {
        Status.PASSED: "passed",
        Status.FAILED: "**FAILED**",
        Status.WARNING: "warning",
        Status.NOT_RUN: "not run",
    }[status]
