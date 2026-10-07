"""Graph state for the two master agents (sources, answers) and their sub-agents.

List fields use `operator.add` so parallel sub-agents (fanned out with `Send`) can each
append results. Sub-agent *inputs* use different key names from these outputs so that
nothing is appended twice when a sub-agent's state is merged back.
"""

import operator
from typing import Annotated, TypedDict

from asics_agent.models import (
    Answer,
    CityConfig,
    Issue,
    Parastatal,
    Question,
    RunContext,
    Source,
)


class MasterState(TypedDict, total=False):
    # Inputs
    city: str  # city slug from the city register, e.g. "bengaluru"
    base_workbook: str | None  # step 1: a previous-phase workbook whose citations to re-test
    only_parastatals: list[str] | None
    only_pillars: list[str] | None
    only_questions: list[str] | None
    auto_approve: bool
    llm_bank_review: bool
    skip_research: bool  # stop after checks (no web research / answering)

    # Initial checks
    run: RunContext
    questions: dict[str, Question]
    city_config: CityConfig
    known_parastatals: list[Parastatal]  # from the register and the city's Sources workbook
    parastatals: list[Parastatal]
    existing_citations: list[Source]  # step 1: re-tested; step 2: the list to answer from
    # Parastatal discovery (step 1)
    discovery_pages: list[tuple[str, str]]
    profiled: Annotated[list[Parastatal], operator.add]
    applicability: dict[str, list[str]]  # parastatal id -> question ids to answer
    # Citations + answers (appended by parallel sub-agents)
    tool_urls: Annotated[list[str], operator.add]
    sources: Annotated[list[Source], operator.add]
    answers: Annotated[list[Answer], operator.add]
    issues: Annotated[list[Issue], operator.add]
    # Outputs
    rollups: list[Answer]
    final_issues: list[Issue]  # every issue, incl. final QA, as shown in the workbook
    final_sources: list[Source]  # step 1: the Citation Sheet as written
    output_workbook: str  # step 1: the Sources workbook; step 2: the answers workbook
    links_db: str


class ParastatalTask(TypedDict, total=False):
    """Input for the per-parastatal links agent."""

    run: RunContext
    parastatal: Parastatal
    task_questions: list[Question]
    existing: list[Source]  # earlier Citation Sheet rows to re-test
    known_sources: list[Source]  # already verified this run (e.g. the official website)
    covered_urls: list[str]
    known_urls: list[str]
    # outputs
    tool_urls: Annotated[list[str], operator.add]
    sources: Annotated[list[Source], operator.add]
    issues: Annotated[list[Issue], operator.add]


class AnswerTask(TypedDict, total=False):
    """Input for a vertical answering sub-agent: one (parastatal, question) pair."""

    run: RunContext
    parastatal: Parastatal
    question: Question
    citation_sources: list[Source]  # the ONLY sources this answer may use
    # working state
    draft: dict
    # outputs
    answers: Annotated[list[Answer], operator.add]
    issues: Annotated[list[Issue], operator.add]


class ParastatalTaskOutput(TypedDict, total=False):
    tool_urls: Annotated[list[str], operator.add]
    sources: Annotated[list[Source], operator.add]
    issues: Annotated[list[Issue], operator.add]


class AnswerTaskOutput(TypedDict, total=False):
    answers: Annotated[list[Answer], operator.add]
    issues: Annotated[list[Issue], operator.add]
