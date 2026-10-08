"""The answering sub-agent, one per question-bank section (UPD, DPG, SC, …).

    answer_from_citations --> finalize

It may use ONLY the Citation Sheet rows it is given (from the city's Sources workbook) and
never researches. Each answer names the Citation ID it relies on, with a verbatim quote that
is checked against that source's saved text. If nothing in the list answers the question,
the answer says so and suggests what kind of source to add.

What the agent is told comes from agent_setup/: the answer-writer agent's prompt and skills,
plus the section's guidance in agent_setup/skills/sections/<code>.md, plus any matching
memory notes. A section only needs Python (a module in this package calling `register`) for
code-level checks such as SC's `require_figures`.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from asics_agent.agent_setup import (
    MemoryScope,
    section_codes,
    section_guidance,
    section_skill,
)
from asics_agent.agents.common import read_source_text
from asics_agent.agents.state import AnswerTask, AnswerTaskOutput
from asics_agent.links.text import locate_quote, relevance, search_phrase
from asics_agent.llm import CallFailed, call_json
from asics_agent.models import Answer, Source
from asics_agent.services import Services
from asics_agent.tools import ToolContext
from asics_agent.verticals import agent_for

MAX_SOURCES = 8  # per answer, most relevant first


@dataclass(frozen=True)
class SectionSpec:
    """Optional code-level hooks for a section; its guidance lives in agent_setup/."""

    code: str  # section code used in question IDs, e.g. "UPD"
    # Adjust or check each answer before it is saved.
    postprocess: Callable[[Answer, AnswerTask], Answer] | None = None
    # Full override: build your own sub-agent graph for this section.
    build: Callable[["SectionSpec", Services], object] | None = None


_HOOKS: dict[str, SectionSpec] = {}
GENERIC = "GENERIC"


def register(spec: SectionSpec) -> SectionSpec:
    _HOOKS[spec.code] = spec
    return spec


def section_nodes(root: Path) -> list[str]:
    """Every section that gets its own answer node: those with a guidance file or hooks."""
    return sorted(set(section_codes(root)) | set(_HOOKS)) + [GENERIC]


def section_for(pillar: str, root: Path) -> str:
    return pillar if pillar in set(section_codes(root)) | set(_HOOKS) else GENERIC


class AnswerReply(BaseModel):
    sufficiency: Literal["sufficient", "partial", "insufficient"] = "insufficient"
    answer: str = ""
    proposed_score: float | None = None
    citation_id: str = ""
    citation: str = ""
    evidence_excerpt: str = ""
    missing_evidence: str = ""
    notes: str = ""


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _location(source: Source, quote: str) -> dict:
    """Tell a reviewer where the quote is: PDF page and/or section heading."""
    full_text = Path(source.content_path).read_text(encoding="utf-8") if source.content_path else ""
    page, heading = locate_quote(full_text, quote)
    parts = []
    if page:
        parts.append(f"Page {page} of the PDF")
    if heading:
        parts.append(f'under the heading "{heading[:120]}"')
    where = ", ".join(parts) or "On the linked page"
    return {
        "where_to_find": where[0].upper() + where[1:] + ".",
        "search_phrase": search_phrase(quote),
        "snapshot_path": source.snapshot_path or "",
    }


def _question_block(section_title: str, task: AnswerTask, unit_label: str = "Parastatal") -> str:
    q, p, run = task["question"], task["parastatal"], task["run"]
    max_score = f"{q.max_score:g}" if q.max_score is not None else "not given"
    return (
        f"City: {run.city_name}, {run.state_name}. City government (ULG): {run.ulg}\n"
        f"{unit_label}: {p.name} ({p.id}), type {p.type}\n"
        f"Section: {section_title or q.pillar_name}\n"
        f"Question {q.raw_id} [{q.tag}, max score {max_score}]: {q.text}\n"
        f"Assessment level: {q.assessment_level}\n"
        f"Detailed Methodology:\n{q.methodology}\n"
        f"Evidence / Source Requirement: {q.evidence_requirement}\n"
    )


def build_section_agent(code: str, services: Services):
    spec = _HOOKS.get(code, SectionSpec(code=code))
    if spec.build:
        return spec.build(spec, services)
    budget = services.settings.max_evidence_chars
    root = services.settings.agent_setup_dir

    def answer_from_citations(task: AnswerTask) -> dict:
        q = task["question"]
        vertical = services.settings.vertical
        title, guidance, hints = section_guidance(root, q.pillar, vertical)  # read fresh
        query = f"{q.text} {q.methodology} {q.evidence_requirement} {hints}"
        texts: dict[str, tuple[Source, str]] = {}
        full: dict[str, str] = {}
        for s in task.get("citation_sources", []):
            if s.content_path and Path(s.content_path).exists():
                full[s.citation_id] = Path(s.content_path).read_text(encoding="utf-8")
        ranked = sorted(
            (s for s in task.get("citation_sources", []) if s.citation_id in full),
            key=lambda s: (q.id in s.question_ids, relevance(full[s.citation_id], query)),
            reverse=True,
        )[:MAX_SOURCES]
        per_source = max(4000, budget // max(1, len(ranked)))
        trimmed = False
        for s in ranked:
            text, cut = read_source_text(s, query, per_source)
            texts[s.citation_id] = (s, text)
            trimmed |= cut
        if not texts:
            return {
                "draft": {
                    "sufficiency": "insufficient",
                    "valid": False,
                    "sources_reviewed": [],
                    "notes": "The Citation Sheet has no usable source for this parastatal (no rows "
                    "marked Use for Answers = Yes with readable, verified content).",
                }
            }

        evidence = "\n\n".join(
            f"=== CITATION {cid}: {s.title} ({s.source_type}) ===\n{text}"
            for cid, (s, text) in texts.items()
        )
        try:
            scope = MemoryScope(
                city=task["run"].city_name, parastatals=[task["parastatal"].id], sections=[q.pillar]
            )
            reply, _, _ = call_json(
                services,
                agent_for(services.settings, "answer"),
                f"{_question_block(title, task, services.settings.unit_label)}\n--- CITATION SHEET SOURCES ---\n{evidence}",
                AnswerReply,
                scope=scope,
                extra_skills=[s] if (s := section_skill(root, q.pillar, vertical)) else [],
                # read_citation / search_citation_sheet reach only these rows.
                tool_context=(
                    tools := ToolContext(
                        services=services,
                        run=task["run"],
                        citations=list(task.get("citation_sources", [])),
                        progress_key=task["parastatal"].id,
                    )
                ),
            )
        except CallFailed as exc:
            return {
                "draft": {
                    "sufficiency": "insufficient",
                    "valid": False,
                    "notes": str(exc),
                    "sources_reviewed": list(texts),
                }
            }

        used = texts.get(reply.citation_id.strip())
        problems = []
        if reply.sufficiency != "insufficient":
            if used is None:
                problems.append(
                    f'the answer cites "{reply.citation_id}", which is not one of '
                    "the Citation Sheet sources provided"
                )
            elif not reply.evidence_excerpt or _normalise(reply.evidence_excerpt) not in (
                _normalise(full[used[0].citation_id])
            ):
                problems.append(
                    f"the quoted evidence could not be found word for word in {used[0].citation_id}"
                )
        return {
            "draft": {
                **reply.model_dump(),
                "valid": not problems,
                "problems": problems,
                "trimmed": trimmed,
                "sources_reviewed": list(texts),
                "source": used[0] if used else None,
                "memory_used": scope.used,
                "tools_used": tools.log,
                **(_location(used[0], reply.evidence_excerpt) if used and not problems else {}),
            }
        }

    def finalize(task: AnswerTask) -> dict:
        q, p, d = task["question"], task["parastatal"], task["draft"]
        sufficiency, valid = d.get("sufficiency", "insufficient"), d.get("valid", False)
        # A citation is recorded only when it actually supports (part of) the answer.
        source: Source | None = d.get("source") if valid and sufficiency != "insufficient" else None
        if sufficiency != "insufficient" and not valid:
            status = "Human Verification Required"
        elif sufficiency == "sufficient":
            status = "Answered — Verified Source"
        elif sufficiency == "partial":
            status = "Partially Answered"
        else:
            status = "Insufficient Evidence"

        notes, score_note = [], ""
        score = d.get("proposed_score")
        if score is not None and q.max_score is not None:
            if float(score) > q.max_score:
                score_note = (
                    f"Proposed score {float(score):g} exceeds the maximum "
                    f"{q.max_score:g}; capped. Confirm the methodology's scale."
                )
            score = max(0.0, min(float(score), q.max_score))
        if status == "Insufficient Evidence":
            score = None

        if source:
            notes.append(f"Evidence from Citation Sheet row {source.citation_id} ({source.title}).")
        if d.get("notes"):
            notes.append(d["notes"])
        if score_note and status != "Insufficient Evidence":
            notes.append(score_note)
        if d.get("sources_reviewed"):
            notes.append(f"Citations reviewed: {', '.join(d['sources_reviewed'])}.")
        if d.get("trimmed"):
            notes.append("Long documents were reduced to their most relevant passages.")
        if d.get("problems"):
            notes.append("Human verification required: " + "; ".join(d["problems"]) + ".")
        if d.get("tools_used"):
            notes.append(f"Looked further with: {'; '.join(d['tools_used'])}.")
        if d.get("memory_used"):
            notes.append(f"Team context used (guidance only): {', '.join(d['memory_used'])}.")
        missing = d.get("missing_evidence", "") if status != "Answered — Verified Source" else ""
        if status == "Insufficient Evidence":
            notes.append(
                "No answer given because no Citation Sheet source supports one."
                + (f" A source that would help: {missing}" if missing else "")
            )

        answer = Answer(
            parastatal_id=p.id,
            question_id=q.id,
            answer=d.get("answer", "") if status != "Insufficient Evidence" else "",
            proposed_score=score,
            status=status,
            citation_id=source.citation_id if source else "",
            citation=f"{source.title}: {d.get('citation', '')}".rstrip(": ") if source else "",
            citation_url=source.url if source else "",
            evidence_excerpt=d.get("evidence_excerpt", "") if source else "",
            source_used="Citation Sheet" if source else "None",
            notes=" ".join(notes),
            missing_evidence=missing,
            where_to_find=d.get("where_to_find", "") if source else "",
            search_phrase=d.get("search_phrase", "") if source else "",
            snapshot_path=d.get("snapshot_path", "") if source else "",
            memory_used=d.get("memory_used", []),
        )
        if spec.postprocess:
            answer = spec.postprocess(answer, task)
        return {"answers": [answer]}

    graph = StateGraph(AnswerTask, output_schema=AnswerTaskOutput)
    graph.add_node("answer_from_citations", answer_from_citations)
    graph.add_node("finalize", finalize)
    graph.add_edge(START, "answer_from_citations")
    graph.add_edge("answer_from_citations", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile(name=f"answer_{code}")
