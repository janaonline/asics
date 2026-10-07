"""Helpers shared by the sub-agents."""

import contextvars
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

from asics_agent.agent_setup import MemoryScope
from asics_agent.links.accessibility import check_url, is_india_code
from asics_agent.links.text import rank_chunks
from asics_agent.llm import call_json
from asics_agent.models import Issue, Parastatal, Question, RunContext, Source
from asics_agent.services import Services

OFFICIAL_SUFFIXES = (".gov.in", ".nic.in", ".gov", ".kar.nic.in")
UNVERIFIED_SCORE_CAP = 0  # "0 = unusable/unverified"
NON_OFFICIAL_SCORE_CAP = 5  # "4-5 = secondary/indirect source"


class CandidateSource(BaseModel):
    title: str
    url: str = ""
    source_type: str = ""
    useful_for: str = ""
    question_ids: list[str] = Field(default_factory=list)


class CandidateList(BaseModel):
    sources: list[CandidateSource] = Field(default_factory=list)
    notes: str = ""


class SourceAssessment(BaseModel):
    useful: bool
    useful_for: str = ""
    current_status: str = "Unknown"
    authority_score: float = 0
    notes: str = ""


def is_official(url: str, official_hosts: set[str] = frozenset()) -> bool:
    host = urlsplit(url).netloc.lower()
    return host.endswith(OFFICIAL_SUFFIXES) or host in official_hosts


def question_digest(questions: list[Question]) -> str:
    return "\n".join(
        f"- {q.id} [{q.assessment_level or q.tag}] {q.text}\n  Evidence: {q.evidence_requirement}"
        for q in questions
    )


def read_source_text(source: Source, query: str, budget: int) -> tuple[str, bool]:
    if not source.content_path or not Path(source.content_path).exists():
        return "", False
    return rank_chunks(Path(source.content_path).read_text(encoding="utf-8"), query, budget)


def vet_source(
    services: Services,
    run: RunContext,
    parastatal: Parastatal,
    candidate: CandidateSource,
    *,
    provenance: str,
    allowed_urls: set[str] | None,
    official_hosts: set[str] = frozenset(),
) -> tuple[Source | None, list[Issue]]:
    """Apply the URL rule, the human-accessibility test and the authority rules to one URL.

    `allowed_urls=None` skips the "returned by a tool" check; used only when re-testing
    URLs that already exist in a previous-phase Citation Sheet.
    """
    issues: list[Issue] = []
    url = candidate.url.strip()
    if not url:
        return None, issues
    if allowed_urls is not None and url not in allowed_urls:
        issues.append(
            Issue(
                phase="links",
                severity="warning",
                ref=parastatal.id,
                message=f"Discarded URL not returned verbatim by any tool this run: {url}",
            )
        )
        return None, issues

    settings = services.settings
    check = check_url(url, services.http, Path(run.cache_dir), settings.user_agent)
    source = Source(
        parastatal_id=parastatal.id,
        title=candidate.title,
        url=url,
        source_type=candidate.source_type,
        useful_for=candidate.useful_for,
        question_ids=candidate.question_ids,
        accessibility=check.accessibility,
        verification_status=check.verification_status,
        # Only links that passed the check are offered for answers; the team can change this.
        use_for_answers=check.verification_status == "Verified",
        provenance=provenance,
        content_path=check.content_path,
        snapshot_path=check.snapshot_path,
        checked_at=check.checked_at,
    )
    notes = [" ".join(check.reasons)]

    if check.verification_status == "Verified":
        text, trimmed = read_source_text(source, candidate.useful_for, settings.max_evidence_chars)
        assessment, _, _ = call_json(
            services,
            "source-assessor",
            f"Parastatal: {parastatal.name} ({parastatal.id})\n"
            f"Title: {candidate.title}\nURL: {url}\nSource type: {candidate.source_type}\n"
            f"What This Source Is Useful For (claimed): {candidate.useful_for}\n"
            f"{'(Text below is an excerpt of the most relevant parts.)' if trimmed else ''}\n\n"
            f"--- RETRIEVED TEXT ---\n{text}",
            SourceAssessment,
            scope=MemoryScope(city=run.city_name, parastatals=[parastatal.id]),
        )
        source.useful_for = assessment.useful_for or source.useful_for
        source.current_status = assessment.current_status
        source.authority_score = max(0.0, min(10.0, assessment.authority_score))
        notes.append(assessment.notes)
        if not assessment.useful:
            source.verification_status = "Not verified"
            source.use_for_answers = False
            source.authority_score = UNVERIFIED_SCORE_CAP
            notes.append("Opened successfully but does not support the stated use.")
        elif (
            not is_official(url, official_hosts) and source.authority_score > NON_OFFICIAL_SCORE_CAP
        ):
            source.authority_score = NON_OFFICIAL_SCORE_CAP
            notes.append("Score capped: not an official government domain.")
        if is_india_code(url) and source.verification_status == "Verified":
            notes.append("India Code page passed the content check; spot-check recommended.")
    else:
        source.authority_score = UNVERIFIED_SCORE_CAP
        if is_india_code(url):
            notes.append("India Code link could not be confirmed as human-accessible.")

    source.notes = " ".join(n for n in notes if n).strip()
    return source, issues


def selected_questions(state: dict) -> list[Question]:
    """The questions a run covers, after the section and question filters."""
    questions = list(state["questions"].values())
    if pillars := state.get("only_pillars"):
        questions = [q for q in questions if q.pillar in pillars]
    if only := state.get("only_questions"):
        wanted = {w.replace("-", " ").strip() for w in only}
        questions = [
            q for q in questions if q.id in wanted or q.raw_id in only or q.parent_id in wanted
        ]
    return questions


def applicability_matrix(parastatals: list[Parastatal], questions: list[Question]):
    """{parastatal id: [question ids that apply]} and team issues for unknown wording."""
    from asics_agent.applicability import applies_to

    matrix, issues = {}, []
    for p in parastatals:
        ids = []
        for q in questions:
            applies = applies_to(q, p)
            if applies is None:
                issues.append(
                    Issue(
                        phase="parastatal_checks",
                        severity="warning",
                        ref=q.id,
                        message=f"Applicability unknown for {p.id}; question "
                        "included for human review",
                    )
                )
            if applies is not False:
                ids.append(q.id)
        matrix[p.id] = ids
    return matrix, issues


def has_errors(state: dict, phase: str | None = None) -> bool:
    return any(
        i.severity == "error" and (phase is None or i.phase == phase)
        for i in state.get("issues", [])
    )


def focus_on_selected(issues: list[Issue], questions: dict, selected: set[str]) -> list[Issue]:
    """Keep question-bank messages about other questions out of the team's view.

    A run limited to "UPD 1" shouldn't tell the team about problems with DPG questions;
    those still appear in the Technical Log (and in full checks-only runs).
    """
    raw_to_id = {q.raw_id: q.id for q in questions.values()}
    result = []
    for issue in issues:
        qid = raw_to_id.get(issue.ref or "", issue.ref)
        if (
            issue.audience == "team"
            and issue.phase == "initial_checks"
            and qid in questions
            and qid not in selected
        ):
            issue = issue.model_copy(update={"audience": "developer"})
        result.append(issue)
    return result


def dedupe_sources(sources: list[Source]) -> list[Source]:
    """One row per (parastatal, URL): the best-verified one, keeping the research team's
    Citation ID, decisions and notes from any duplicate."""
    rank = {"Verified": 2, "Human Verification Required": 1, "Not verified": 0}
    groups: dict[str, list[Source]] = {}
    for s in sources:
        groups.setdefault(s.key, []).append(s)
    result = []
    for group in groups.values():
        best = max(group, key=lambda s: (rank[s.verification_status], s.authority_score))
        result.append(
            best.model_copy(
                update={
                    "question_ids": sorted({q for s in group for q in s.question_ids}),
                    "citation_id": next((s.citation_id for s in group if s.citation_id), ""),
                    "use_for_answers": all(s.use_for_answers for s in group),
                    "team_notes": next((s.team_notes for s in group if s.team_notes), ""),
                    "found_by": "Your team"
                    if any(s.found_by == "Your team" for s in group)
                    else "Agent",
                }
            )
        )
    return result


def vet_many(
    services: Services,
    run: RunContext,
    parastatal: Parastatal,
    candidates: list[CandidateSource],
    *,
    provenance: str,
    allowed_urls: set[str] | None,
    label: str = "Checking links",
) -> list[tuple[CandidateSource, Source | None, list[Issue]]]:
    """`vet_source` for several links at once, a few in parallel, reporting progress.

    Results come back in the same order as `candidates`.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from asics_agent.progress import report

    total = len(candidates)
    if not total:
        return []
    results: list = [None] * total
    verified = 0
    with ThreadPoolExecutor(max_workers=services.settings.check_workers) as pool:
        futures = {
            pool.submit(
                contextvars.copy_context().run,  # keep the run's options and progress stream
                vet_source,
                services,
                run,
                parastatal,
                c,
                provenance=provenance,
                allowed_urls=allowed_urls,
            ): i
            for i, c in enumerate(candidates)
        }
        for done, future in enumerate(as_completed(futures), start=1):
            i = futures[future]
            source, issues = future.result()
            results[i] = (candidates[i], source, issues)
            verified += bool(source and source.verification_status == "Verified")
            report(parastatal.id, f"{label}: {done} of {total} done, {verified} verified so far")
    return results


def memory_note(scope, ref: str | None, what: str) -> list[Issue]:
    """A Technical Log entry saying which team memory notes shaped a call (for audit)."""
    if not scope.used:
        return []
    return [
        Issue(
            phase="memory",
            severity="info",
            ref=ref,
            message=f"{what} used team context: {', '.join(scope.used)}",
        )
    ]


def tool_note(ctx, ref: str | None, what: str) -> list[Issue]:
    """A Technical Log entry listing the tools an agent called (for audit)."""
    if not ctx.log:
        return []
    return [
        Issue(
            phase="tools", severity="info", ref=ref, message=f"{what} called: {'; '.join(ctx.log)}"
        )
    ]
