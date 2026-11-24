"""Sub-agent 3 — Links database (Citation Sheet), one run per parastatal.

1. Re-test every existing Citation Sheet row (from an earlier run or a previous-phase
   workbook). Previous verification is never trusted.
2. Research new official sources for the questions that apply to this parastatal.
3. Fill gaps: a second, targeted search for questions that still have no verified source.
4. Vet each URL: tool-returned verbatim -> human-accessibility test -> relevance and
   authority review -> score caps. The results feed the links database.
"""

import re
from pathlib import Path
from urllib.parse import urlparse

from langgraph.graph import END, START, StateGraph

from asics_agent import cutoff, source_requirements
from asics_agent.agent_setup import MemoryScope
from asics_agent.agents.common import (
    HUMAN_DOUBT_NOTE,
    CandidateList,
    CandidateSource,
    memory_note,
    own_domains,
    question_digest,
    tool_note,
    vet_many,
)
from asics_agent.agents.state import ParastatalTask, ParastatalTaskOutput
from asics_agent.categories import agent_for
from asics_agent.links import crawl, marks
from asics_agent.links.accessibility import site_of
from asics_agent.links.fetch_chain import NOT_RETRIED_NOTE
from asics_agent.links.manual import team_check
from asics_agent.llm import CallFailed, call_json
from asics_agent.models import Issue
from asics_agent.progress import report
from asics_agent.run_options import current_options
from asics_agent.services import Services
from asics_agent.tools import ToolContext


def own_domain(website: str | None) -> set[str]:
    """The agency's own official domain, for the source finder's allowed domains. gov.in and
    nic.in sites are allowed already."""
    host = (urlparse(website or "").hostname or "").removeprefix("www.")
    if not host or host.endswith((".gov.in", ".nic.in")):
        return set()
    return {host}


CANDIDATE_MIN_SCORE = 20  # at least "linked from a government page" (see links/trust.py)


def candidate_website(parastatal) -> str:
    """The best candidate website to search when none could be confirmed as official (for
    example the profile step could not open it because of a certificate error). "" when the
    agency has a confirmed website, no candidate, or the candidate looks like a known
    non-official site (those score 0). Its sources are marked CONFIRM."""
    check = getattr(parastatal, "website_check", None)
    if getattr(parastatal, "official_website", "") or check is None:
        return ""
    return check.url if check.url and check.score >= CANDIDATE_MIN_SCORE else ""


def use_after_retest(old, source) -> tuple[bool, str]:
    """(Use for Answers?, a note) for an earlier row after it was re-tested.

    A human-verified row always keeps the team's decision: a person who set it to No keeps No.
    The team's decision is kept, with one exception: a row that was "No" only because its link
    could not be opened (it was not verified, and the team did not add it) is switched to "Yes"
    when it now opens and passes the check. Without this a link recovered by a fix would stay
    unused. A row the team unticked while it was verified, or one the team added, stays as it was."""
    if old.human_verified:
        return old.use_for_answers, ""
    if (
        not old.use_for_answers
        and old.verification_status != "Verified"
        and old.found_by != "Your team"
        and source.verification_status == "Verified"
    ):
        return True, (
            "Now verified, so Use for Answers is set to Yes (it was No only because the link "
            "could not be opened before). "
        )
    return old.use_for_answers, ""


def _verified_questions(task: ParastatalTask) -> set[str]:
    sources = task.get("sources", []) + task.get("known_sources", [])
    return {q for s in sources if s.verification_status == "Verified" for q in s.question_ids}


def covered_questions(task: ParastatalTask, settings) -> set[str]:
    """The questions that already have what they need. Without the required_sources setting: any
    verified source tagged for the question. With it, a question that has a zero rule is covered
    only when every document it requires has a usable row (source_requirements.coverage); a
    question without one keeps the earlier rule."""
    old = _verified_questions(task)
    if not settings.required_sources:
        return old
    sources = task.get("sources", []) + task.get("known_sources", [])
    questions = task.get("task_questions", [])
    covered, _, _ = source_requirements.coverage(
        questions, task["parastatal"], sources, rule=cutoff.rule_from(settings)
    )
    return covered | {
        q.id for q in questions if not source_requirements.has_rule(q) and q.id in old
    }


def fetch_issues(parastatal, sources, settings=None) -> list[Issue]:
    """Needs Attention lines for how the staged fetch obtained the agency's copies (links/fetch_chain.py):
    archived copies, stale archives, copies read without a verified certificate, links not retried this
    run, and a browser that is not installed. Each line lists the Citation IDs."""
    archived, stale, cert, skipped = [], [], [], []
    no_browser = False
    seen = set()
    for s in sources:
        if s.url in seen:
            continue
        seen.add(s.url)
        label = s.citation_id or s.title
        notes = s.notes or ""
        if marks.is_stale(s.copy_type):
            stale.append(f"{label} ({s.copy_type})")
        elif marks.is_archived(s.copy_type):
            archived.append(f"{label} ({s.copy_type})")
        if marks.has(s.copy_type, marks.CERT):
            cert.append(label)
        if NOT_RETRIED_NOTE in notes:
            skipped.append(label)
        no_browser = no_browser or "browser not installed" in notes
    limit = getattr(settings, "archive_max_age_days", 365)
    name = parastatal.name

    def line(message: str) -> Issue:
        return Issue(
            phase="links",
            severity="warning",
            ref=parastatal.id,
            audience="team",
            message=f"{name}: {message}",
        )

    out = []
    if archived:
        out.append(
            line(
                f"{len(archived)} source(s) are ARCHIVED copies from the Wayback Machine, because the "
                f"live page did not open: {', '.join(archived)}. They are used for answers but can "
                "support a positive finding only: never a zero, a required source or a complete "
                "crawl. Open the live page; if it opens now, run Step 1 again to replace the copy."
            )
        )
    if stale:
        out.append(
            line(
                f"{len(stale)} link(s) have only a stale archived copy (older than {limit} days), "
                f"which is not used: {', '.join(stale)}. A person must open the live page."
            )
        )
    if cert:
        out.append(
            line(
                f"{len(cert)} source(s) were read without verifying the website's security "
                f"certificate (allowed for the agency's own site and .gov.in / .nic.in only): "
                f"{', '.join(cert)}. Check that the page is the right one."
            )
        )
    if skipped:
        out.append(
            line(
                f"{len(skipped)} link(s) were not retried this run (a recent failure is remembered, "
                f"or the fetch chain's time cap was reached): {', '.join(skipped)}. Run Step 1 again "
                "later, or open them in a browser."
            )
        )
    if no_browser:
        out.append(
            line(
                "the browser stage could not run because Chromium is not installed on this "
                "computer, so JavaScript pages were not opened. Run `uv run playwright install "
                "chromium` once, then run Step 1 again."
            )
        )
    return out


def human_verified_issues(parastatal, sources) -> list[Issue]:
    """Needs Attention lines for the agency's human-verified rows: one line for those the assessor
    doubts and one for those the app could not open, each listing the Citation IDs. The rows keep
    their flag and the team's Use for Answers decision (the lines only ask for a look)."""
    doubted, unopened = [], []
    seen = set()
    for s in sources:
        if not s.human_verified or s.url in seen:
            continue
        seen.add(s.url)
        label = s.citation_id or s.title
        if HUMAN_DOUBT_NOTE in (s.notes or ""):
            doubted.append(label)
        elif s.verification_status != "Verified":
            unopened.append(label)
    out = []
    if doubted:
        out.append(
            Issue(
                phase="links",
                severity="warning",
                ref=parastatal.id,
                audience="team",
                message=f"{parastatal.name}: the assessor doubts {len(doubted)} human-verified "
                f"source(s): {', '.join(doubted)}. They stay marked Human-Verified? and in use "
                "(your decision), but please check that each supports what it is listed for.",
            )
        )
    if unopened:
        out.append(
            Issue(
                phase="links",
                severity="warning",
                ref=parastatal.id,
                audience="team",
                message=f"{parastatal.name}: {len(unopened)} human-verified source(s) could not "
                f"be opened by the app: {', '.join(unopened)}. Open each in a browser, save the "
                "page as PDF in evidence/manual/<Citation ID>.pdf, and run Step 1 or Step 2 again.",
            )
        )
    return out


def _missing_note(task: ParastatalTask, settings, missing_ids: list[str]) -> str:
    """What each uncovered question still lacks, for the second search."""
    if not settings.required_sources:
        return ""
    sources = task.get("sources", []) + task.get("known_sources", [])
    by_id = {q.id: q for q in task.get("task_questions", [])}
    lines = []
    for qid in missing_ids:
        q = by_id.get(qid)
        req = source_requirements.required_for(qid)
        if q is None or req is None or not req.has_zero_rule:
            continue
        gate = source_requirements.check(
            req, task["parastatal"], sources, rule=cutoff.rule_from(settings)
        )
        if gate.state in ("missing", "unreadable"):
            lacks = gate.missing_text() or "a required source that did not open"
            lines.append(f"- {qid} still lacks: {lacks}")
    return ("Still missing for these questions:\n" + "\n".join(lines) + "\n") if lines else ""


def build_links_agent(services: Services):
    def retest_existing(task: ParastatalTask) -> dict:
        p, earlier = task["parastatal"], task.get("existing", [])
        if not earlier:
            return {}
        report(p.id, f"Re-checking {len(earlier)} link(s) from the existing Citation Sheet")
        candidates = [
            CandidateSource(
                title=o.title,
                url=o.url,
                source_type=o.source_type,
                useful_for=o.useful_for,
                question_ids=o.question_ids,
                human_verified=o.human_verified,
            )
            for o in earlier
        ]
        sources, issues = [], []
        results = vet_many(
            services,
            task["run"],
            p,
            candidates,
            provenance="phase1_citation_sheet",
            allowed_urls=None,
            label="Re-checking earlier links",
            # A saved copy by the team is kept if the automatic check still fails.
            team_copies={o.url: copy for o in earlier if (copy := team_check(o))},
            own_hosts=own_domains(p, earlier),
        )
        for old, (_, source, vet_issues) in zip(earlier, results, strict=True):
            issues += vet_issues
            if source:
                use, why = use_after_retest(old, source)
                source = source.model_copy(
                    update={
                        "citation_id": old.citation_id,
                        "use_for_answers": use,
                        "team_notes": old.team_notes,
                        "found_by": old.found_by,
                        "provenance": old.provenance,
                        "human_verified": old.human_verified,
                    }
                )
                previous = f"Previous status: {old.verification_status or 'blank'}"
                if old.authority_score:
                    previous += f", score {old.authority_score:g}"
                source.notes = f"Re-tested this run. {previous}. {why}{source.notes}"
                sources.append(source)
        return {"sources": sources, "issues": issues}

    def research(task: ParastatalTask, questions, already: set[str], note: str) -> dict:
        p, run = task["parastatal"], task["run"]
        required = services.settings.required_sources
        known = set(task.get("known_urls", []))
        candidate_site = candidate_website(p)
        report(
            p.id,
            f"Searching the web for sources for {len(questions)} question(s) "
            "(this usually takes a few minutes)",
        )
        try:
            found, urls, rejected = call_json(
                services,
                agent_for(services.settings, "sources"),
                f"{services.settings.unit_label}: {p.name} ({p.id}), type {p.type}\n"
                f"City: {run.city_name}, {run.state_name}. City government (ULG): {run.ulg}\n"
                f"Official website: {p.official_website or 'not confirmed'}\n"
                + (source_requirements.legal_base_line(p) if required else "")
                + (
                    "Candidate website (NOT confirmed as official; you may search and open it, "
                    f"and every source from it is marked CONFIRM): {candidate_site}\n"
                    if candidate_site
                    else ""
                )
                + (
                    "Shared state laws already in the Citation Sheet for every parastatal "
                    "(do not search for these again):\n" + "\n".join(task["shared_laws"]) + "\n"
                    if task.get("shared_laws")
                    else ""
                )
                + "\n"
                f"{note}\nQuestions to support:\n"
                f"{question_digest(questions, requirements=required, parastatal=p)}\n\n"
                "Already in the Citation Sheet (skip these):\n"
                + ("\n".join(sorted(already)) or "(none)"),
                CandidateList,
                scope=(
                    scope := MemoryScope(
                        city=run.city_name,
                        parastatals=[p.id],
                        sections=sorted({q.pillar for q in questions}),
                    )
                ),
                known_urls=known,
                tool_context=(tools := ToolContext(services=services, run=run, progress_key=p.id)),
                web_max_uses=services.settings.find_sources_max_uses,
                web_domains=own_domain(p.official_website) | own_domain(candidate_site),
            )
        except CallFailed as exc:
            report(p.id, f"Stopped this search: {exc}")
            return {
                "issues": [
                    Issue(
                        phase="links",
                        severity="warning",
                        ref=p.id,
                        audience="team",
                        message=f"{p.name}: a search for sources didn't finish ({exc}). Sources found "
                        "so far are kept; run Step 1 again to try once more.",
                    )
                ]
            }

        sources = []
        issues = [Issue(phase="links", severity="info", ref=p.id, message=m) for m in rejected]
        issues += memory_note(scope, p.id, "Citation builder")
        issues += tool_note(tools, p.id, "Citation builder")
        if found.notes:
            issues.append(Issue(phase="links", severity="info", ref=p.id, message=found.notes))
        # Sources already checked this run (the official website, re-tested earlier rows):
        # keep the question tags the search gives them, without checking them again.
        fresh = {x.url: x for x in task.get("known_sources", []) + task.get("sources", [])}
        to_check = []
        for candidate in found.sources:
            if candidate.url in fresh:
                known_source = fresh[candidate.url]
                sources.append(
                    known_source.model_copy(
                        update={
                            "question_ids": sorted(
                                set(known_source.question_ids) | set(candidate.question_ids)
                            )
                        }
                    )
                )
            elif candidate.url not in already:
                already.add(candidate.url)
                to_check.append(candidate)
        report(p.id, f"Found {len(to_check)} new possible source(s); opening and checking each")
        for _, source, vet_issues in vet_many(
            services,
            run,
            p,
            to_check,
            provenance="web_search",
            allowed_urls=urls | known,
            own_hosts=own_domains(p, [*task.get("known_sources", []), *task.get("sources", [])]),
        ):
            issues += vet_issues
            if source:
                if candidate_site and site_of(source.url) == site_of(candidate_site):
                    source.notes = (
                        f"CONFIRM: {site_of(candidate_site)} is only a candidate website for {p.id} "
                        f"(not confirmed as official). {source.notes}"
                    ).strip()
                sources.append(source)
        return {"sources": sources, "tool_urls": sorted(urls), "issues": issues}

    def discover_sources(task: ParastatalTask) -> dict:
        already = {s.url for s in task.get("existing", [])} | set(task.get("covered_urls", []))
        questions = task["task_questions"]
        if task.get("existing") and not current_options().full_refresh:
            # A repeat run: the re-tested Citation Sheet rows that are still verified keep
            # their questions; search only for the rest (fill_gaps then tries once more).
            covered = covered_questions(task, services.settings)
            questions = [q for q in questions if q.id not in covered]
            what = (
                "what they require" if services.settings.required_sources else "a verified source"
            )
            if not questions:
                report(task["parastatal"].id, f"Every question already has {what}")
                return {}
            report(
                task["parastatal"].id,
                f"{len(task['task_questions']) - len(questions)} question(s) already have "
                f"{what}; searching for the other {len(questions)}",
            )
        return research(task, questions, already, "")

    def fill_gaps(task: ParastatalTask) -> dict:
        """Second, targeted search for questions that still have no verified source."""
        sources = task.get("sources", []) + task.get("known_sources", [])
        covered = covered_questions(task, services.settings)
        missing = [q for q in task["task_questions"] if q.id not in covered]
        if not missing:
            report(task["parastatal"].id, "Done: every question has what it needs")
            return {}
        report(
            task["parastatal"].id,
            f"Second search, for {len(missing)} question(s) that still lack "
            + ("a required source" if services.settings.required_sources else "a source"),
        )
        already = {s.url for s in sources}
        result = research(
            task,
            missing,
            already,
            f"A first search found sources for the other questions. These "
            f"{len(missing)} question(s) still have NO verified source"
            + (" for what they require" if services.settings.required_sources else "")
            + "; search specifically for the documents that answer them.\n"
            + _missing_note(task, services.settings, [q.id for q in missing]),
        )
        found = [x for x in result.get("sources", []) if x.verification_status == "Verified"]
        report(
            task["parastatal"].id, f"Done: the second search added {len(found)} verified source(s)"
        )
        return result

    def crawl_site(task: ParastatalTask) -> dict:
        """Open the menu links of the agency's confirmed official home page, one level deep, so the
        Citation Sheet holds the pages of its own site (links/crawl.py). The result is written in the
        Notes of the home page row: the gate allows no zero for a website question without a
        complete crawl."""
        settings, p, run = services.settings, task["parastatal"], task["run"]
        cap = settings.crawl_max_pages
        if not (settings.required_sources and cap > 0 and settings.unit == "parastatal"):
            return {}
        own = site_of(p.official_website)

        def info(message: str, severity="info") -> dict:
            report(p.id, message)
            return {"issues": [Issue(phase="links", severity=severity, ref=p.id, message=message)]}

        if not own:
            return info("Site crawl: no confirmed official website, so there is nothing to crawl.")
        rows = task.get("sources", []) + task.get("known_sources", [])
        home = next(
            (
                s
                for s in rows
                if s.verification_status == "Verified"
                and not marks.cannot_support_zero(
                    s.copy_type
                )  # an archived home page cannot show a menu is complete
                and site_of(s.url) == own
                and s.snapshot_path
                and s.snapshot_path.endswith(".html")
                and Path(s.snapshot_path).exists()
                and (
                    (s.source_type or "").strip().lower() == "official website"
                    or urlparse(s.url).path in ("", "/")
                )
            ),
            None,
        )
        if home is None:
            return info(
                "Site crawl: the home page of the official website did not open (an archived copy "
                "does not count for a crawl), so its menu could not be read."
            )
        html = Path(home.snapshot_path).read_bytes().decode("utf-8", errors="replace")
        plan = crawl.plan_crawl(html, home.url, cap)
        # A human-verified row never counts as a captured menu link: the crawl opens that page
        # itself (the two rows for one address are merged afterwards, keeping the flag)
        crawled = [s for s in rows if not s.human_verified]
        verified = {
            s.url
            for s in crawled
            if s.verification_status == "Verified" and not marks.cannot_support_zero(s.copy_type)
        }
        known = {s.url for s in crawled}
        to_open = [link for link in plan.selected if link.url not in known]
        report(
            p.id,
            f"Site crawl: {plan.menu_links} menu link(s) on the home page; opening {len(to_open)} "
            f"new one(s) (cap {cap})",
        )
        candidates = [
            CandidateSource(
                title=link.text or urlparse(link.url).path.rsplit("/", 1)[-1] or link.url,
                url=link.url,
                source_type="Official Parastatal Website",
                useful_for=f"[{crawl.CRAWL_PAGE_TAG}] {link.text or 'page'}: page linked from the "
                "menu of the official home page",
            )
            for link in to_open
        ]
        new_sources, issues = [], []
        for _, source, vet_issues in vet_many(
            services,
            run,
            p,
            candidates,
            provenance="fetched_page",
            allowed_urls={c.url for c in candidates},
            label="Opening the site's menu links",
            own_hosts=own_domains(p, rows),
        ):
            issues += vet_issues
            if source:
                if not source_requirements.tags_of(source) & source_requirements.WEBPAGE_TAGS:
                    source.useful_for = f"[{crawl.CRAWL_PAGE_TAG}] {source.useful_for}".strip()
                new_sources.append(source)
        now_verified = verified | {
            s.url
            for s in new_sources
            if s.verification_status == "Verified" and not marks.cannot_support_zero(s.copy_type)
        }
        dead = [link for link in plan.selected if link.url not in now_verified]
        # lenient: a dead link that names no topic word is set aside; strict (the default) counts all
        lenient = settings.crawl_incomplete_on_dead_link == "lenient"
        ignored = [link.url for link in dead if lenient and not link.topic]
        failed = [link.url for link in dead if link.url not in ignored]
        note = crawl.crawl_note(
            plan, captured=len(plan.selected) - len(dead), failed=failed, ignored=ignored
        )
        stale = re.sub(rf"{source_requirements.SITE_CRAWL}:[^\n]*?(?:\.(?=\s|$)|$)", "", home.notes)
        home_row = home.model_copy(update={"notes": f"{stale.strip()} {note}".strip()})
        issues.append(
            Issue(phase="links", severity="info", ref=p.id, message=f"Site crawl: {note}")
        )
        report(p.id, note)
        return {"sources": [*new_sources, home_row], "issues": issues}

    def coverage_report(task: ParastatalTask) -> dict:
        """Needs Attention lines for what the questions still lack after both searches: one line
        per agency and missing document (the question codes it affects), and one per required
        source that is in the sheet but did not open."""
        settings = services.settings
        p = task["parastatal"]
        sources = task.get("sources", []) + task.get("known_sources", [])
        human = human_verified_issues(p, sources) + fetch_issues(p, sources, settings)
        if not settings.required_sources:
            return {"issues": human} if human else {}
        questions = task.get("task_questions", [])
        _, missing, unopened = source_requirements.coverage(
            questions, p, sources, rule=cutoff.rule_from(settings)
        )
        order = {q.id: i for i, q in enumerate(questions)}

        def codes(ids):
            return ", ".join(sorted(set(ids), key=lambda i: order.get(i, 0)))

        issues = list(human)
        for tag, ids in missing.items():
            name = source_requirements.DOCUMENT_NAMES.get(tag, tag)
            if tag == "SITECRAWL":
                state, text = source_requirements.crawl_status(p, sources)
                name += ". " + (
                    text
                    if text
                    else "The crawl did not run: no confirmed official website, or its home page "
                    "did not open"
                )
            how = (
                "Run Step 1 again, or add the pages of the website as team rows."
                if tag in ("SITECRAWL", "WEBPAGE")
                else "Add it to the Citation Sheet (or save a copy of the document) and run Step 1 again."
            )
            issues.append(
                Issue(
                    phase="links",
                    severity="warning",
                    ref=p.id,
                    audience="team",
                    message=f"{p.name}: missing required source: {name}. A score of 0 is not "
                    f"allowed without it. Questions affected: {codes(ids)}. {how}",
                )
            )
        by_id = {s.citation_id: s for s in sources if s.citation_id}
        for cid, ids in unopened.items():
            row = by_id.get(cid)
            what = f" ({row.title[:70]}, {row.url})" if row else ""
            issues.append(
                Issue(
                    phase="links",
                    severity="warning",
                    ref=p.id,
                    audience="team",
                    message=f"{p.name}: a required source is in the Citation Sheet but did not "
                    f"open: {cid}{what}. Questions affected: {codes(ids)}. Open it in a browser, "
                    "save the page as PDF and add it as a team row.",
                )
            )
        if issues:
            report(p.id, f"{len(issues)} required document(s) still missing or unopened")
        return {"issues": issues}

    graph = StateGraph(ParastatalTask, output_schema=ParastatalTaskOutput)
    graph.add_node("retest_existing", retest_existing)
    graph.add_node("crawl_site", crawl_site)
    graph.add_node("discover_sources", discover_sources)
    graph.add_node("fill_gaps", fill_gaps)
    graph.add_node("coverage_report", coverage_report)
    graph.add_edge(START, "retest_existing")
    graph.add_edge("retest_existing", "crawl_site")
    graph.add_edge("crawl_site", "discover_sources")
    graph.add_edge("discover_sources", "fill_gaps")
    graph.add_edge("fill_gaps", "coverage_report")
    graph.add_edge("coverage_report", END)
    return graph.compile(name="links_agent")
