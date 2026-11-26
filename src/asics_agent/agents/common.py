"""Helpers shared by the sub-agents."""

import contextvars
import re
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

from asics_agent import source_requirements
from asics_agent.agent_setup import MemoryScope
from asics_agent.categories import agent_for
from asics_agent.cutoff import assessment_fields, check_from, rule_from
from asics_agent.links import marks
from asics_agent.links.accessibility import is_india_code, site_of
from asics_agent.links.fetch_chain import check_url_staged
from asics_agent.links.text import rank_chunks
from asics_agent.llm import call_json
from asics_agent.models import AccessCheck, Issue, Parastatal, Question, RunContext, Source
from asics_agent.services import Services

_CRAWL_NOTE = re.compile(rf"{source_requirements.SITE_CRAWL}:[^\n]*?(?:\.(?=\s|$)|$)")
OFFICIAL_SUFFIXES = (".gov.in", ".nic.in", ".gov", ".kar.nic.in")
HUMAN_DOUBT_NOTE = "Assessor doubts this source: please check."
HUMAN_UNOPENED_NOTE = "Human-verified, but the app could not open it: save a copy by hand."
UNVERIFIED_SCORE_CAP = 0  # "0 = unusable/unverified"
NON_OFFICIAL_SCORE_CAP = 5  # "4-5 = secondary/indirect source"


class CandidateSource(BaseModel):
    title: str
    url: str = ""
    source_type: str = ""
    useful_for: str = ""
    question_ids: list[str] = Field(default_factory=list)
    # A person has already checked this source (Citation Sheet "Human-Verified?"). It is carried
    # onto the Source and never changed by a check or by the assessor.
    human_verified: bool = False


class CandidateList(BaseModel):
    sources: list[CandidateSource] = Field(default_factory=list)
    notes: str = ""


class SourceAssessment(BaseModel):
    useful: bool
    useful_for: str = ""
    current_status: str = "Unknown"
    authority_score: float = 0
    notes: str = ""
    # Only when the message lists what the questions require: does this source meet it?
    meets_requirement: str = ""  # yes | partly | no | "" (not asked)
    # When the cited text or version took effect (or its "amended up to" date), as YYYY-MM-DD when
    # the day is known; and whether it is law in force, a Bill, or a draft. See cutoff.py.
    effective_date: str = ""
    form: str = ""


def is_official(url: str, official_hosts: set[str] = frozenset()) -> bool:
    host = urlsplit(url).netloc.lower()
    return host.endswith(OFFICIAL_SUFFIXES) or host in official_hosts


def question_digest(
    questions: list[Question],
    *,
    requirements: bool = False,
    parastatal: Parastatal | None = None,
    only=None,
) -> str:
    """The questions as the source finder sees them. With `requirements` (the category's
    required_sources setting) each question also carries the methodology's "Check ..." line and the
    documents it requires (source_requirements.py); `only` limits those to the shared laws."""
    out = []
    for q in questions:
        out.append(
            f"- {q.id} [{q.assessment_level or q.tag}] {q.text}\n  Evidence: {q.evidence_requirement}"
        )
        if requirements:
            out += source_requirements.digest_lines(q, parastatal, only=only)
    return "\n".join(out)


def read_source_text(source: Source, query: str, budget: int) -> tuple[str, bool]:
    if not source.content_path or not Path(source.content_path).exists():
        return "", False
    return rank_chunks(Path(source.content_path).read_text(encoding="utf-8"), query, budget)


def assess_source(
    services: Services,
    run: RunContext,
    parastatal: Parastatal,
    candidate: CandidateSource,
    source: Source,
) -> "SourceAssessment":
    """The source assessor's view of a page that opened: is it useful, and how authoritative.
    It reads at most ASICS_ASSESS_EVIDENCE_CHARS of the page, the parts most relevant to the
    claimed use."""
    text, trimmed = read_source_text(
        source, candidate.useful_for, services.settings.assess_evidence_chars
    )
    needs = (
        source_requirements.requirement_note(candidate.question_ids, parastatal)
        if services.settings.required_sources
        else ""
    )
    assessment, _, _ = call_json(
        services,
        agent_for(services.settings, "assess"),
        f"{services.settings.unit_label}: {parastatal.name} ({parastatal.id})\n"
        f"City: {run.city_name}, {run.state_name}\n"
        f"Title: {candidate.title}\nURL: {source.url}\nSource type: {candidate.source_type}\n"
        f"What This Source Is Useful For (claimed): {candidate.useful_for}\n"
        + (f"What the questions it was found for require:\n{needs}\n" if needs else "")
        + f"{'(Text below is an excerpt of the most relevant parts.)' if trimmed else ''}\n\n"
        f"--- RETRIEVED TEXT ---\n{text}",
        SourceAssessment,
        scope=MemoryScope(city=run.city_name, parastatals=[parastatal.id]),
    )
    return assessment


def vet_source(
    services: Services,
    run: RunContext,
    parastatal: Parastatal,
    candidate: CandidateSource,
    *,
    provenance: str,
    allowed_urls: set[str] | None,
    official_hosts: set[str] = frozenset(),
    team_copy: AccessCheck | None = None,
    own_hosts: frozenset[str] = frozenset(),
) -> tuple[Source | None, list[Issue]]:
    """Apply the URL rule, the human-accessibility test and the authority rules to one URL.

    `allowed_urls=None` skips the "returned by a tool" check; used only when re-testing
    URLs that already exist in a previous-phase Citation Sheet.

    `team_copy` is the research team's saved copy of the page (see links/manual.py). The
    page is still opened automatically and the result recorded in the Notes. If that check
    now passes, its fresh copy is used; if not, the team's copy is kept and assessed like
    any other verified source.
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
    # The agency's confirmed official website lets a gov.in alias that redirects to it be accepted.
    confirmed = {site_of(parastatal.official_website)} - {""}
    check = check_url_staged(
        url,
        services.http,
        Path(run.cache_dir),
        settings.user_agent,
        official_hosts=confirmed,
        settings=settings,
        own_hosts=own_hosts,
    )
    notes = [" ".join(check.reasons)]
    if team_copy:
        automated = f"Automated check: {' '.join(check.reasons)}"
        if check.verification_status == "Verified":
            notes = [f"{automated} Using this fresh copy instead of the team's saved copy."]
            team_copy = None
        else:
            check = team_copy
            check.copy_type = marks.SAVED_BY_TEAM
            notes = [*team_copy.reasons, automated]
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
        copy_type=check.copy_type,
        archived_on=check.archived_on,
        team_saved_copy=team_copy is not None,
        human_verified=candidate.human_verified,
    )

    if check.verification_status == "Verified":
        assessment = assess_source(services, run, parastatal, candidate, source)
        source.useful_for = assessment.useful_for or source.useful_for
        source.current_status = assessment.current_status
        source.effective_date, source.cutoff_check = assessment_fields(
            assessment.effective_date, assessment.form, rule_from(settings)
        )
        if check.archived_on and not source.effective_date and rule_from(settings) is not None:
            # An archived copy shows the text as of the day it was archived: when the assessor found no
            # date in the text, that day is the as-of date for the Law/Policy cut-off check.
            source.effective_date = check.archived_on
            source.cutoff_check = check_from(
                check.archived_on, assessment.form, rule_from(settings)
            )
        source.authority_score = max(0.0, min(10.0, assessment.authority_score))
        notes.append(assessment.notes)
        if assessment.meets_requirement.strip().lower() in ("yes", "partly", "no"):
            notes.append(
                f"Meets what the questions require: {assessment.meets_requirement.strip().lower()}."
            )
        if not assessment.useful and candidate.human_verified:
            # A person checked this source: the assessor's doubt is a note, not a decision. The row
            # stays Verified and keeps its Use for Answers; Needs Attention asks for a look.
            notes.append(HUMAN_DOUBT_NOTE)
        elif not assessment.useful:
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
        if candidate.human_verified:
            # Never "Not verified": a person vouches for it, so it waits for a saved copy by hand
            source.verification_status = "Human Verification Required"
            notes.append(HUMAN_UNOPENED_NOTE)

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
        # The site crawl writes its result in the Notes of the home page row; the newest one wins
        crawl_note = next(
            (m.group(0) for s in reversed(group) if (m := _CRAWL_NOTE.search(s.notes or ""))), ""
        )
        notes = best.notes
        if crawl_note and crawl_note not in notes:
            notes = f"{_CRAWL_NOTE.sub('', notes).strip()} {crawl_note}".strip()
        result.append(
            best.model_copy(
                update={
                    "notes": notes,
                    "question_ids": sorted({q for s in group for q in s.question_ids}),
                    "citation_id": next((s.citation_id for s in group if s.citation_id), ""),
                    "human_verified": any(s.human_verified for s in group),
                    "use_for_answers": all(s.use_for_answers for s in group),
                    "team_notes": next((s.team_notes for s in group if s.team_notes), ""),
                    "found_by": "Your team"
                    if any(s.found_by == "Your team" for s in group)
                    else "Agent",
                }
            )
        )
    return result


def own_domains(parastatal: Parastatal, sources: list[Source]) -> frozenset[str]:
    """The agency's own websites, for the one thing that needs them (the staged fetch may read a page
    whose security certificate cannot be verified only on an own or government host): its confirmed
    official website, plus the host of every row of its Citation Sheet that is typed as the agency's
    website and is verified or marked Human-Verified?."""
    hosts = {site_of(parastatal.official_website)}
    for s in sources:
        kind = (s.source_type or "").strip().lower()
        if (
            s.parastatal_id == parastatal.id
            and kind in ("official parastatal website", "official website")
            and (s.human_verified or s.verification_status == "Verified")
        ):
            hosts.add(site_of(s.url))
    return frozenset(hosts - {""})


def vet_many(
    services: Services,
    run: RunContext,
    parastatal: Parastatal,
    candidates: list[CandidateSource],
    *,
    provenance: str,
    allowed_urls: set[str] | None,
    label: str = "Checking links",
    team_copies: dict[str, AccessCheck] | None = None,
    own_hosts: frozenset[str] = frozenset(),
) -> list[tuple[CandidateSource, Source | None, list[Issue]]]:
    """`vet_source` for several links at once, a few in parallel, reporting progress.

    Results come back in the same order as `candidates`. `team_copies` maps a URL to the
    team's saved copy of it.
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
                team_copy=(team_copies or {}).get(c.url),
                own_hosts=own_hosts,
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
