"""Domain models shared by every agent."""

import hashlib
from typing import Literal

from pydantic import BaseModel, Field

ParastatalType = Literal[
    "water_supply_board",
    "transport_corporation",
    "development_authority",
    "other",
    "city_government",  # verticals that assess the city government itself (e.g. UPD)
]

Accessibility = Literal["Public", "Not human-verified"]
VerificationStatus = Literal["Verified", "Not verified", "Human Verification Required"]
Provenance = Literal["phase1_citation_sheet", "web_search", "fetched_page", "research_team"]
FoundBy = Literal["Agent", "Your team"]

AnswerStatus = Literal[
    "Answered — Verified Source",
    "Partially Answered",
    "Insufficient Evidence",
    "Human Verification Required",
    "Computed from Sub-indicators",
    "Not Applicable",
    "Not Yet Assessed",
]


class Question(BaseModel):
    id: str  # normalised, e.g. "DPG 5a"
    raw_id: str  # as written in the question bank
    row: int  # row in the Question Bank sheet
    pillar: str  # e.g. "UPD"
    pillar_name: str
    text: str
    tag: Literal["MQ", "SQ"]
    max_score: float | None = None
    assessment_level: str | None = None
    unit: str | None = None
    applicability: str = ""
    methodology: str = ""
    evidence_requirement: str = ""
    rationale: str = ""
    parent_id: str | None = None
    children: list[str] = Field(default_factory=list)

    @property
    def is_rollup(self) -> bool:
        """MQs with sub-questions are computed from them, not researched directly."""
        return self.tag == "MQ" and bool(self.children)


class WebsiteCheck(BaseModel):
    """How much a candidate website can be trusted as the parastatal's official site."""

    url: str
    score: int = 0  # 0-100
    band: Literal["Official", "Probably official", "Not confirmed"] = "Not confirmed"
    reasons: list[str] = Field(default_factory=list)  # e.g. "gov.in domain (+40)"
    opens: bool = False

    @property
    def summary(self) -> str:
        return f"{self.score}/100 ({self.band}): " + "; ".join(self.reasons)


class Parastatal(BaseModel):
    id: str
    name: str
    type: ParastatalType
    revenue_raising: bool = False
    capex_mandate: bool = False
    has_annual_budget: bool = True
    has_chief_executive: bool = True
    notes: str = ""
    include: bool = True  # the research team's decision in the Sources workbook
    team_notes: str = ""  # the research team's own notes, never overwritten
    # Filled in by the parastatal discovery agent
    found_by: FoundBy = "Your team"
    governing_act: str = ""
    current_status: str = ""
    why_included: str = ""  # why the agent thinks it serves this city
    official_website: str = ""
    website_check: WebsiteCheck | None = None
    other_websites: list[WebsiteCheck] = Field(default_factory=list)


class CityConfig(BaseModel):
    slug: str
    name: str
    state: str
    ulg: str
    aliases: list[str] = Field(default_factory=list)  # other spellings, e.g. Bangalore
    parastatals: list[Parastatal] = Field(default_factory=list)  # optional: known to the team


class RunContext(BaseModel):
    run_id: str
    city: str
    city_name: str
    state_name: str
    ulg: str
    workspace: str  # the city's folder: Sources workbook, evidence, answer runs
    output_dir: str  # where this run writes its files
    cache_dir: str  # saved copies and extracted text of sources (shared by both steps)


class AccessCheck(BaseModel):
    url: str
    status_code: int | None = None
    final_url: str | None = None
    content_type: str | None = None
    words: int = 0
    accessibility: Accessibility = "Not human-verified"
    verification_status: VerificationStatus = "Not verified"
    reasons: list[str] = Field(default_factory=list)
    content_path: str | None = None  # extracted text, used by the agents
    snapshot_path: str | None = None  # the page/PDF exactly as downloaded, for reviewers
    checked_at: str = ""


ALL_PARASTATALS = "All parastatals"


class Source(BaseModel):
    citation_id: str = ""  # e.g. "BWSSB-07"; assigned when the Sources workbook is written
    parastatal_id: str  # or ALL_PARASTATALS for a source that applies to every parastatal
    title: str
    url: str
    source_type: str = ""
    useful_for: str = ""
    question_ids: list[str] = Field(default_factory=list)
    accessibility: Accessibility = "Not human-verified"
    current_status: str = "Unknown"
    verification_status: VerificationStatus = "Not verified"
    authority_score: float = 0
    provenance: Provenance = "web_search"
    found_by: FoundBy = "Agent"
    use_for_answers: bool = True  # the research team's decision in the Sources workbook
    team_notes: str = ""  # the research team's own notes, never overwritten
    notes: str = ""
    content_path: str | None = None
    snapshot_path: str | None = None
    checked_at: str = ""

    @property
    def key(self) -> str:
        return hashlib.sha1(f"{self.parastatal_id}|{self.url}".encode()).hexdigest()[:12]


class Answer(BaseModel):
    parastatal_id: str
    question_id: str
    answer: str = ""
    proposed_score: float | None = None
    status: AnswerStatus = "Insufficient Evidence"
    citation_id: str = ""  # the Citation Sheet row the answer relies on
    citation: str = ""  # source title and the section/page used
    citation_url: str = ""
    evidence_excerpt: str = ""
    source_used: Literal["Citation Sheet", "Sub-indicators", "None"] = "None"
    notes: str = ""
    missing_evidence: str = ""  # when unanswered: what kind of source would answer it
    # Help a reviewer find the evidence quickly
    where_to_find: str = ""  # e.g. "Page 12" or "Under the heading 'Section 16 ...'"
    search_phrase: str = ""  # words to search for with Ctrl+F / Cmd+F
    snapshot_path: str = ""  # saved copy of the source as it was when checked
    memory_used: list[str] = Field(default_factory=list)  # team memory notes given to the model


class Issue(BaseModel):
    """A problem or note found during a run.

    `audience="team"` messages are written in plain language and shown to the research
    team; everything else only appears in the Technical Log for developers.
    """

    phase: str
    severity: Literal["error", "warning", "info"]
    message: str
    ref: str | None = None
    audience: Literal["team", "developer"] = "developer"
