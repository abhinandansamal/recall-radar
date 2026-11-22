"""Load gold sets from JSON Lines files and give every run a dataset version.

Layout in ``evals/data/``::

    matching/v1.jsonl            dev + test cases
    matching/v1.holdout.jsonl    frozen holdout, only for the final report

The dataset version is the set name, the version and the first 12 hex digits of the SHA-256
of the file content, e.g. ``matching-v1@3f2a9c0d1e7b``. Every report records it, so two runs
can only be compared when they used the same data.
"""

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ValidationError

from rr_eval.schemas import Split


class DatasetError(Exception):
    """A gold-set file is missing, malformed or inconsistent."""


@dataclass(frozen=True)
class Dataset[CaseT: BaseModel]:
    """Validated cases of one gold-set file.

    Attributes:
        name: Set name, e.g. ``matching``.
        version: Human version from the file name, e.g. ``v1``.
        digest: First 12 hex digits of the SHA-256 of the file.
        cases: The validated cases in file order.
    """

    name: str
    version: str
    digest: str
    cases: tuple[CaseT, ...]

    @property
    def dataset_version(self) -> str:
        """Identifier recorded in every report, e.g. ``matching-v1@3f2a9c0d1e7b``."""
        return f"{self.name}-{self.version}@{self.digest}"

    def split(self, *splits: Split) -> tuple[CaseT, ...]:
        """Return the cases of the given splits, in file order."""
        return tuple(case for case in self.cases if getattr(case, "split", None) in splits)


def load_dataset[CaseT: BaseModel](path: Path, model: type[CaseT]) -> Dataset[CaseT]:
    """Read and validate one gold-set file.

    Args:
        path: File like ``evals/data/matching/v1.jsonl``.
        model: The case model every line must validate against.

    Returns:
        The validated dataset.

    Raises:
        DatasetError: If the file is missing, a line is not valid JSON or not a valid case, or
            a case id appears twice.
    """
    if not path.is_file():
        raise DatasetError(f"gold set not found: {path}")
    raw = path.read_bytes()
    cases: list[CaseT] = []
    seen: set[str] = set()
    for number, line in enumerate(raw.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            case = model.model_validate(json.loads(line))
        except (json.JSONDecodeError, ValidationError) as error:
            raise DatasetError(f"{path.name} line {number}: {error}") from error
        case_id = str(getattr(case, "case_id", ""))
        if case_id in seen:
            raise DatasetError(f"{path.name} line {number}: duplicate case id {case_id}")
        seen.add(case_id)
        cases.append(case)
    if not cases:
        raise DatasetError(f"gold set is empty: {path}")
    name = path.parent.name
    version = path.name.split(".", 1)[0]
    return Dataset(
        name=name,
        version=version,
        digest=hashlib.sha256(raw).hexdigest()[:12],
        cases=tuple(cases),
    )


def check_holdout_is_separate(main: Dataset[BaseModel], holdout: Dataset[BaseModel]) -> None:
    """Make sure the holdout file holds only holdout cases and shares no case with the main file.

    Raises:
        DatasetError: If a split is in the wrong file or a case id is in both files.
    """
    wrong_main = [c for c in main.cases if getattr(c, "split", None) == "holdout"]
    wrong_holdout = [c for c in holdout.cases if getattr(c, "split", None) != "holdout"]
    if wrong_main or wrong_holdout:
        raise DatasetError("holdout cases must live only in the .holdout.jsonl file")
    overlap = _ids(main.cases) & _ids(holdout.cases)
    if overlap:
        raise DatasetError(f"case ids in both files: {sorted(overlap)[:5]}")


def _ids(cases: Sequence[BaseModel]) -> set[str]:
    return {str(getattr(case, "case_id", "")) for case in cases}
