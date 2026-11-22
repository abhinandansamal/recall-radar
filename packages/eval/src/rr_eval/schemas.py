"""The shape of every gold-set case, checked on load.

Gold sets are JSON Lines files in ``evals/data/``. Each line is one case and must validate
against one of the models below; unknown fields are rejected, so a typo in a label never
silently turns into "no label".
"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Split = Literal["dev", "test", "holdout"]
Language = Literal["en", "de"]
Label = Literal["match", "similar", "clear"]

MatchingSlice = Literal[
    "exact_key",  # the listing carries a GTIN or brand + model that is in the alert
    "no_identifier",  # identifiers removed: only text and photo can find the alert
    "cross_language",  # listing language differs from the language of the matching alert text
    "image_only",  # only the photo is given
    "re_upload",  # built from a real repeat alert of the same product
    "evasion",  # brand, model or wording changed on purpose
    "look_alike",  # safe product of the same kind (hard negative)
    "similar_product",  # same brand or kind, different product (expected "similar")
]

AlertId = Annotated[str, StringConstraints(pattern=r"^[A-Z0-9]{1,5}/\d{5}/\d{2}$")]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Citation = Annotated[str, StringConstraints(pattern=r"^Art\. \d{1,3}(\(\d{1,2}\))?$")]

_STRICT = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ListingQuery(BaseModel):
    """A listing as the screening service receives it (seller-written, untrusted)."""

    model_config = _STRICT

    title: str = Field(default="", max_length=300)
    description: str = Field(default="", max_length=5000)
    brand: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=100)
    gtin: str | None = Field(default=None, pattern=r"^\d{8,14}$")
    category: str | None = Field(default=None, max_length=200)
    language: Language
    image_sha256: tuple[Sha256, ...] = ()

    @model_validator(mode="after")
    def _has_content(self) -> Self:
        if not self.title and not self.image_sha256:
            raise ValueError("a listing needs a title or at least one photo")
        return self


class MatchingCase(BaseModel):
    """One screening case: a listing and the alerts that should (or should not) be found.

    ``relevant`` holds graded alert ids: 2 = the same product, 1 = a similar product.
    ``exclude_ids`` are removed from every result list before scoring ("leave one out"): a
    case built from alert B with B excluded asks "would the listing have been caught by the
    *other* alert of the same product?".
    """

    model_config = _STRICT

    case_id: Annotated[str, StringConstraints(pattern=r"^M-\d{4}$")]
    split: Split
    slices: tuple[MatchingSlice, ...] = Field(min_length=1)
    query: ListingQuery
    expected: Label
    relevant: dict[AlertId, Literal[1, 2]] = Field(default_factory=dict)
    exclude_ids: tuple[AlertId, ...] = ()
    source: str = Field(min_length=1, max_length=200)
    notes: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def _labels_agree(self) -> Self:
        grades = set(self.relevant.values())
        if self.expected == "match" and 2 not in grades:
            raise ValueError("expected 'match' needs at least one alert with grade 2")
        if self.expected == "clear" and grades:
            raise ValueError("expected 'clear' cannot have relevant alerts")
        if self.expected == "similar" and grades != {1}:
            raise ValueError("expected 'similar' needs grade-1 alerts only")
        if set(self.exclude_ids) & set(self.relevant):
            raise ValueError("an alert cannot be both relevant and excluded")
        if "image_only" in self.slices and not self.query.image_sha256:
            raise ValueError("slice 'image_only' needs a photo")
        if "look_alike" in self.slices and self.expected != "clear":
            raise ValueError("slice 'look_alike' is a safe product: expected must be 'clear'")
        return self


class LegalCase(BaseModel):
    """One question for the legal RAG, with the GPSR articles a correct answer must cite.

    Citations use the label printed in the regulation (``Art. 22(4)``), not chunk ids, so the
    set stays valid when the chunking changes.
    """

    model_config = _STRICT

    case_id: Annotated[str, StringConstraints(pattern=r"^L-\d{4}$")]
    split: Split
    language: Language
    question: str = Field(min_length=5, max_length=1000)
    expected_citations: tuple[Citation, ...] = ()
    key_facts: tuple[str, ...] = ()
    should_abstain: bool = False
    verified_by_po: bool = False

    @model_validator(mode="after")
    def _abstain_or_cite(self) -> Self:
        if self.should_abstain == bool(self.expected_citations):
            raise ValueError("a case either cites articles or expects an abstention, not both")
        return self


Threat = Annotated[str, StringConstraints(pattern=r"^T\d{1,2}$")]
AdversarialExpectation = Literal[
    "result_unchanged",  # screening result must equal the result without the attack
    "no_exact_key_override",  # a deterministic match must stay a match
    "reject_input",  # input validation must refuse the request
    "refuse",  # the assistant must refuse
    "no_action",  # no tool with a side effect may be called
    "no_leak",  # no secret, system prompt or data outside the role in the output
]


class AdversarialCase(BaseModel):
    """One attack, mapped to a threat id from ``docs/security/threat-model.md``."""

    model_config = _STRICT

    case_id: Annotated[str, StringConstraints(pattern=r"^A-\d{4}$")]
    split: Split
    workload: Literal["screening", "assistant", "case_workflow"]
    threat: Threat
    language: Language
    listing: ListingQuery | None = None
    question: str | None = Field(default=None, max_length=10_000)
    baseline_case_id: str | None = None
    expected: AdversarialExpectation
    critical: bool = True
    notes: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def _one_input(self) -> Self:
        if (self.listing is None) == (self.question is None):
            raise ValueError("an attack has exactly one input: a listing or a question")
        if self.expected == "result_unchanged" and not self.baseline_case_id:
            raise ValueError("'result_unchanged' needs the clean case to compare with")
        return self


Route = Literal["legal_rag", "alert_lookup", "case_lookup", "kpi", "refuse", "clarify"]


class RoutingCase(BaseModel):
    """One assistant question with the route and filters the planner must choose."""

    model_config = _STRICT

    case_id: Annotated[str, StringConstraints(pattern=r"^R-\d{4}$")]
    split: Split
    language: Language
    question: str = Field(min_length=2, max_length=1000)
    expected_route: Route
    expected_filters: dict[str, str] = Field(default_factory=dict)


Case = MatchingCase | LegalCase | AdversarialCase | RoutingCase
