"""Per-stage gates: read ``evals/gates.yaml`` and judge measured metrics against it.

A gate names a workload, a stage, a metric, a slice, a comparison and a threshold. A gate
whose metric was not measured (the stage is not built yet), or was measured on fewer than
``min_n`` cases, is ``not_run``: it neither passes
nor fails. A failed **hard** gate fails the run; a failed soft gate is a warning.

``slice: each`` applies the threshold to every slice that has the metric (for example
"recall@20 ≥ 0.85 in every slice").

``op: no_regression`` compares with a baseline value (the last result on ``main``) and fails
when the value drops by more than ``tolerance``.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

Workload = Literal["screening", "assistant", "case_workflow", "security"]
Operator = Literal[">=", "<=", "==", "no_regression"]


class GateError(Exception):
    """The gates file is missing or invalid."""


class Gate(BaseModel):
    """One threshold for one metric of one stage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    workload: Workload
    stage: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    slice: str = "all"
    op: Operator
    threshold: float | None = None
    tolerance: float | None = Field(default=None, ge=0)
    hard: bool = True
    min_n: int = Field(default=1, ge=1)  # fewer cases: "not_run", the value is noise
    reason: str = ""

    @model_validator(mode="after")
    def _threshold_matches_op(self) -> "Gate":
        if self.op == "no_regression":
            if self.tolerance is None:
                raise ValueError("'no_regression' needs a tolerance")
        elif self.threshold is None:
            raise ValueError(f"'{self.op}' needs a threshold")
        return self


class GateFile(BaseModel):
    """The whole ``gates.yaml``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = Field(ge=1)
    gates: tuple[Gate, ...] = Field(min_length=1)


class Status(StrEnum):
    """Outcome of one gate."""

    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    NOT_RUN = "not_run"


@dataclass(frozen=True)
class MetricValue:
    """A measured metric: the value and how many cases it is based on."""

    value: float
    n: int


@dataclass(frozen=True)
class GateResult:
    """The outcome of one gate for one slice."""

    gate: Gate
    slice: str
    value: MetricValue | None
    status: Status

    @property
    def target(self) -> str:
        """Readable target, e.g. ``>= 0.9`` or ``no drop > 0.02``."""
        if self.gate.op == "no_regression":
            return f"no drop > {self.gate.tolerance}"
        return f"{self.gate.op} {self.gate.threshold}"


Metrics = Mapping[tuple[str, str], MetricValue]
"""Measured metrics keyed by ``(slice, metric)``."""


def load_gates(path: Path) -> tuple[Gate, ...]:
    """Read and validate a gates file.

    Raises:
        GateError: If the file is missing or does not match the gate schema.
    """
    if not path.is_file():
        raise GateError(f"gates file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return GateFile.model_validate(data).gates
    except (yaml.YAMLError, ValidationError) as error:
        raise GateError(f"{path.name}: {error}") from error


def evaluate_gates(
    gates: tuple[Gate, ...],
    workload: Workload,
    metrics: Metrics,
    baseline: Metrics | None = None,
) -> list[GateResult]:
    """Judge the measured metrics of one workload against its gates.

    Args:
        gates: All gates (other workloads are ignored).
        workload: The workload that was measured.
        metrics: Measured values keyed by ``(slice, metric)``.
        baseline: Values from the last run on ``main``, for ``no_regression`` gates.

    Returns:
        One result per gate and slice.
    """
    results: list[GateResult] = []
    for gate in (g for g in gates if g.workload == workload):
        slices = _slices_for(gate, metrics)
        if not slices:
            results.append(GateResult(gate, gate.slice, None, Status.NOT_RUN))
            continue
        for slice_name in slices:
            value = metrics[(slice_name, gate.metric)]
            if value.n < gate.min_n:
                results.append(GateResult(gate, slice_name, value, Status.NOT_RUN))
                continue
            reference = (baseline or {}).get((slice_name, gate.metric))
            passed = _passes(gate, value.value, reference.value if reference else None)
            if passed is None:
                status = Status.NOT_RUN
            elif passed:
                status = Status.PASSED
            else:
                status = Status.FAILED if gate.hard else Status.WARNING
            results.append(GateResult(gate, slice_name, value, status))
    return results


def run_passed(results: list[GateResult]) -> bool:
    """``True`` when no hard gate failed (warnings and ``not_run`` do not fail a run)."""
    return all(result.status is not Status.FAILED for result in results)


def _slices_for(gate: Gate, metrics: Metrics) -> list[str]:
    if gate.slice == "each":
        return sorted(s for (s, m) in metrics if m == gate.metric and s != "all")
    return [gate.slice] if (gate.slice, gate.metric) in metrics else []


def _passes(gate: Gate, value: float, reference: float | None) -> bool | None:
    if gate.op == "no_regression":
        if reference is None:
            return None
        return value >= reference - (gate.tolerance or 0.0)
    threshold = gate.threshold if gate.threshold is not None else 0.0
    if gate.op == ">=":
        return value >= threshold
    if gate.op == "<=":
        return value <= threshold
    return value == threshold
