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

from asics_agent import cutoff, methodology, source_requirements
from asics_agent.agent_setup import (
    MemoryScope,
    section_codes,
    section_guidance,
    section_skill,
)
from asics_agent.agents.common import read_source_text
from asics_agent.agents.state import AnswerTask, AnswerTaskOutput
from asics_agent.categories import agent_for
from asics_agent.links.text import locate_quote, relevance, search_phrase
from asics_agent.llm import CallFailed, call_json
from asics_agent.models import ANSWER_CLASSES, CONFIDENCES, HUMAN_VERIFIED_MARK, Answer, Source
from asics_agent.services import Services
from asics_agent.tools import ToolContext

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
    # A 0 for "nothing found", given only when the required sources are all present and the scan of
    # their full text found nothing (source_requirements.zero_block tells the model when)
    zero_checked: bool = False


# What can follow BAND in the model's notes (see prompts/answer-question.md).
_AFTER_BAND = r"CONFIRM:|SCORE-BLANK:|ALSO:|RTI-TARGET:|SCALE-MISMATCH|Reviewer to capture"


def parse_class_line(notes: str) -> tuple[str, str, str, list[str]]:
    """(class, confidence, band, problems) from the start of the model's notes.

    The prompt asks for "CLASS: <A1|A2|R|P|M|Needs review>; CONFIDENCE: <High|Medium|Low>;
    BAND: <…>". Spacing and case are forgiven; a value that is missing or not in the allowed
    list is left blank and reported in `problems`, never guessed.
    """
    text, pos, found = notes.strip().lstrip("\"'"), 0, {}
    stops = {
        "CLASS": r"[;,\n]|CONFIDENCE\b|BAND\b",
        "CONFIDENCE": r"[;,\n]|BAND\b",
        "BAND": _AFTER_BAND,
    }
    for key, stop in stops.items():
        start = re.compile(rf"\s*[;,]?\s*{key}\s*[:=]\s*", re.I).match(text, pos)
        if not start:
            found[key] = ""
            continue
        value = re.compile(rf"(.*?)(?=\s*(?:{stop})|$)", re.I | re.S).match(text, start.end())
        found[key] = re.sub(r"\s+", " ", value.group(1)).strip(" .;,")
        pos = value.end()

    problems, result = [], {}
    for key, value, allowed in (
        ("CLASS", found["CLASS"], ANSWER_CLASSES),
        ("CONFIDENCE", found["CONFIDENCE"], CONFIDENCES),
        ("BAND", found["BAND"], None),
    ):
        match = next((a for a in allowed or () if a.lower() == value.lower()), "")
        result[key] = (match if allowed else value) if value else ""
        if value and allowed and not match:
            problems.append(
                f"{key} '{value}' is not one of {', '.join(allowed)}, so that column was left blank."
            )
    if not any(found.values()):
        problems = [
            "the notes don't start with CLASS, CONFIDENCE and BAND, so those columns were left blank."
        ]
    else:
        for key in ("CLASS", "CONFIDENCE", "BAND"):
            if not found[key]:
                problems.append(f"{key} is missing from the notes, so that column was left blank.")
    if result["CLASS"] == "A2" and result["CONFIDENCE"] == "High":
        problems.append("Class A2 is never High confidence. Check the Confidence.")
    return result["CLASS"], result["CONFIDENCE"], result["BAND"], problems


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


def _question_block(
    section_title: str, task: AnswerTask, unit_label: str = "Parastatal", extra: str = ""
) -> str:
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
        f"{extra}"
    )


def build_section_agent(code: str, services: Services):
    spec = _HOOKS.get(code, SectionSpec(code=code))
    if spec.build:
        return spec.build(spec, services)
    budget = services.settings.max_evidence_chars
    root = services.settings.agent_setup_dir

    def answer_from_citations(task: AnswerTask) -> dict:
        q = task["question"]
        category = services.settings.category
        title, guidance, hints = section_guidance(root, q.pillar, category)  # read fresh
        query = f"{q.text} {q.methodology} {q.evidence_requirement} {hints}"
        if methodology.is_placeholder(q.methodology):  # no rule to apply: a person answers it
            return {
                "draft": {
                    "sufficiency": "insufficient",
                    "valid": False,
                    "blocked": methodology.placeholder_reason(q.id),
                    "sources_reviewed": [],
                }
            }
        # Law/Policy question: only sources that took effect on or before the cut-off (cutoff.py).
        rule = cutoff.rule_from(services.settings)
        # A score of 0 needs the sources the question requires (source_requirements.py)
        req = source_requirements.required_for(q.id) if services.settings.required_sources else None
        decision = (
            source_requirements.decide_zero(
                req,
                task["parastatal"],
                task.get("citation_all") or task.get("citation_sources", []),
                rule=rule,
            )
            if req is not None and req.has_zero_rule
            else None
        )
        zero = (
            {"zero_state": decision.state, "zero_note": decision.note}
            if decision is not None
            else {}
        )
        law = rule is not None and cutoff.is_law_policy(q.assessment_level)
        screen = cutoff.screen_sources(task.get("citation_sources", []), rule, law)
        if screen.pending:
            return {
                "draft": {
                    "sufficiency": "insufficient",
                    "valid": False,
                    "pending_fetch": screen.pending,
                    "sources_reviewed": [],
                    **zero,
                }
            }
        offered = screen.usable
        texts: dict[str, tuple[Source, str]] = {}
        full: dict[str, str] = {}
        for s in offered:
            if s.content_path and Path(s.content_path).exists():
                full[s.citation_id] = Path(s.content_path).read_text(encoding="utf-8")
        # Pinned first, so the model reads them: the human-verified rows tagged for this question
        # (Question IDs), then the documents the question requires, all within the MAX_SOURCES
        # places; at least two places stay for the required documents. The rest are ranked as usual;
        # a human-verified row not tagged for this question gets no priority.
        hv_on = services.settings.human_verified_sources
        by_relevance = sorted(
            (s for s in offered if s.citation_id in full),
            key=lambda s: (q.id in s.question_ids, relevance(full[s.citation_id], query)),
            reverse=True,
        )
        required_rows = [
            s for s in (decision.gate.rows if decision else []) if s.citation_id in full
        ]
        required_rows = required_rows[: MAX_SOURCES // 2]
        tagged = [s for s in by_relevance if hv_on and s.human_verified and q.id in s.question_ids]
        tagged = tagged[: MAX_SOURCES - min(len(required_rows), 2)]
        ranked: list[Source] = []
        for s in [*tagged, *required_rows, *by_relevance]:
            if s.citation_id not in {r.citation_id for r in ranked} and len(ranked) < MAX_SOURCES:
                ranked.append(s)
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
                    **zero,
                }
            }

        hv_ids = [cid for cid, (s, _) in texts.items() if hv_on and s.human_verified]
        evidence = "\n\n".join(
            f"=== CITATION {cid}: {s.title} ({s.source_type}) ==="
            + (f" [{HUMAN_VERIFIED_MARK}]" if cid in hv_ids else "")
            + f"\n{text}"
            for cid, (s, text) in texts.items()
        )
        hv_line = (
            f"{HUMAN_VERIFIED_MARK} ({', '.join(hv_ids)}). Look at these first, but read the text, "
            "quote it word for word and apply the methodology, the zero rule and the cut-off as "
            "for any source: a person's check is not proof that a provision exists or is absent.\n"
            if hv_ids
            else ""
        )
        try:
            scope = MemoryScope(
                city=task["run"].city_name, parastatals=[task["parastatal"].id], sections=[q.pillar]
            )
            reply, _, _ = call_json(
                services,
                agent_for(services.settings, "answer"),
                f"{_question_block(title, task, services.settings.unit_label, hv_line + source_requirements.zero_block(req, decision))}"
                f"\n--- CITATION SHEET SOURCES ---\n{evidence}",
                AnswerReply,
                scope=scope,
                extra_skills=[s] if (s := section_skill(root, q.pillar, category)) else [],
                # read_citation / search_citation_sheet reach only these rows.
                tool_context=(
                    tools := ToolContext(
                        services=services,
                        run=task["run"],
                        citations=list(offered),
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
                    **zero,
                }
            }

        used = texts.get(reply.citation_id.strip())
        problems = []
        confirm = ""
        zero_checked = False
        hold = ""
        if decision is not None:
            claims_zero = reply.zero_checked and reply.proposed_score in (None, 0)
            plain_zero = not reply.zero_checked and reply.proposed_score == 0
            if claims_zero and decision.allowed:
                # Every required source was read in full and the scan found nothing: a recorded zero
                primary = decision.gate.rows[0]
                zero_checked, used = True, (primary, "")
                reply = reply.model_copy(
                    update={
                        "sufficiency": "sufficient",
                        "proposed_score": 0.0,
                        "citation_id": primary.citation_id,
                        "evidence_excerpt": "",
                        "answer": reply.answer
                        or "Nothing in the required sources meets the methodology's test, so the "
                        "score is 0.",
                    }
                )
            elif (claims_zero or plain_zero) and not decision.allowed:
                # A 0 needs the required sources: it is dropped, and the note says why
                if decision.state == "unreadable":
                    hold = decision.note
                reply = reply.model_copy(
                    update={
                        "proposed_score": None,
                        "sufficiency": "insufficient" if claims_zero else reply.sufficiency,
                    }
                )
            elif decision.state == "unreadable" and reply.sufficiency == "insufficient":
                hold = decision.note  # a required source did not open: a person must open it
        if law and rule is not None:
            if used is not None and used[0].citation_id in screen.unknown:
                confirm = cutoff.confirm_note(used[0].citation_id, rule)
            late = cutoff.period_after_cutoff(reply.answer, rule)
            if late is not None:
                problems.append(
                    f"the answer's own period runs to {late.isoformat()}, after the "
                    f"{rule.label} cut-off for Law/Policy questions"
                )
        if reply.sufficiency != "insufficient" and not zero_checked:
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
                "replied": True,
                "valid": not problems,
                "problems": problems,
                "cutoff_confirm": confirm,
                "trimmed": trimmed,
                "sources_reviewed": list(texts),
                "source": used[0] if used else None,
                "memory_used": scope.used,
                "tools_used": tools.log,
                "zero_checked": zero_checked,
                "source_hold": hold,
                "source_flags": {
                    cid: (hv_on and s.human_verified) for cid, (s, _) in texts.items()
                },
                **zero,
                **(
                    _location(used[0], reply.evidence_excerpt)
                    if used and not problems and not zero_checked
                    else {}
                ),
            }
        }

    def finalize(task: AnswerTask) -> dict:
        q, p, d = task["question"], task["parastatal"], task["draft"]
        sufficiency, valid = d.get("sufficiency", "insufficient"), d.get("valid", False)
        # A citation is recorded only when it actually supports (part of) the answer.
        source: Source | None = d.get("source") if valid and sufficiency != "insufficient" else None
        held = d.get("pending_fetch") or d.get("blocked") or d.get("source_hold")
        if (
            held
        ):  # a person has to act: no source in force at the cut-off, no rule, or an unopened source
            status = "Human Verification Required"
            sufficiency, valid = "insufficient", False
            prefix = (
                "PENDING FETCH: "
                if d.get("pending_fetch")
                else "SOURCE DID NOT OPEN: "
                if d.get("source_hold") and not d.get("blocked")
                else "NO RULE: "
            )
            d = {**d, "answer": prefix + held}
        elif sufficiency != "insufficient" and not valid:
            status = "Human Verification Required"
        elif sufficiency == "sufficient":
            # The status follows the MAIN citation: a person-verified row, or any other verified one
            human = services.settings.human_verified_sources and source is not None
            status = (
                "Answered — Human-Verified Source"
                if human and source.human_verified
                else "Answered — Verified Source"
            )
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
        if status == "Insufficient Evidence" or held:
            score = None

        if source:
            notes.append(f"Evidence from Citation Sheet row {source.citation_id} ({source.title}).")
            flags = d.get("source_flags") or {}
            if flags.get(source.citation_id):
                notes.append("Main source human-verified: a person confirmed it for this agency.")
            # Other sources the model says it used (its "ALSO:" ids), each with its origin
            also = re.search(
                r"ALSO:\s*(.+?)(?=\s*(?:CONFIRM:|SCORE-BLANK:|RTI-TARGET:|SCALE-MISMATCH|Reviewer to capture)|$)",
                d.get("notes", ""),
                re.S,
            )
            others = [
                cid
                for cid in dict.fromkeys(
                    re.findall(r"[A-Z][A-Z0-9]*-\d+", also.group(1) if also else "")
                )
                if cid in flags and cid != source.citation_id
            ]
            if others and services.settings.human_verified_sources:
                notes.append(
                    "Other sources used: "
                    + ", ".join(
                        f"{cid} ({'human-verified' if flags[cid] else 'app-found'})"
                        for cid in others
                    )
                    + "."
                )
        answer_class = confidence = band = ""
        if d.get("notes"):
            notes.append(d["notes"])
        if d.get("replied"):
            answer_class, confidence, band, flags = parse_class_line(d.get("notes", ""))
            notes += [f"Reviewer: {flag[0].upper()}{flag[1:]}" for flag in flags]
        if held:
            notes.append(f"CONFIRM: {'PENDING FETCH - ' if d.get('pending_fetch') else ''}{held}")
        if d.get("zero_checked"):
            # A zero the gate allowed: every required source read in full, the scan found nothing
            confidence = "Medium" if confidence in ("", "High", "Medium") else confidence
            notes.append(f"{source_requirements.ZERO_CHECKED}: {d.get('zero_note', '')}")
        elif d.get("zero_note") and score is None and d.get("zero_state") != "allowed" and not held:
            notes.append(f"Zero not allowed: {d['zero_note']}")
        if d.get("cutoff_confirm"):
            notes.append(d["cutoff_confirm"])
            confidence = cutoff.cap_confidence(confidence)
        if d.get("replied") and (
            flag := methodology.band_problem(q.methodology, q.max_score, band)
        ):
            notes.append(f"CONFIRM: {flag}")
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
        missing = d.get("missing_evidence", "") if not status.startswith("Answered") else ""
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
            answer_class=answer_class,
            confidence=confidence,
            rubric_band=band,
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
