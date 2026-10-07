"""Sub-agent 3 — Links database (Citation Sheet), one run per parastatal.

1. Re-test every existing Citation Sheet row (from an earlier run or a previous-phase
   workbook). Previous verification is never trusted.
2. Research new official sources for the questions that apply to this parastatal.
3. Fill gaps: a second, targeted search for questions that still have no verified source.
4. Vet each URL: tool-returned verbatim -> human-accessibility test -> relevance and
   authority review -> score caps. The results feed the links database.
"""

from langgraph.graph import END, START, StateGraph

from asics_agent.agent_setup import MemoryScope
from asics_agent.agents.common import (
    CandidateList,
    CandidateSource,
    memory_note,
    question_digest,
    tool_note,
    vet_many,
)
from asics_agent.agents.state import ParastatalTask, ParastatalTaskOutput
from asics_agent.llm import CallFailed, call_json
from asics_agent.models import Issue
from asics_agent.progress import report
from asics_agent.services import Services
from asics_agent.tools import ToolContext


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
        )
        for old, (_, source, vet_issues) in zip(earlier, results, strict=True):
            issues += vet_issues
            if source:
                source = source.model_copy(
                    update={
                        "citation_id": old.citation_id,
                        "use_for_answers": old.use_for_answers,
                        "team_notes": old.team_notes,
                        "found_by": old.found_by,
                        "provenance": old.provenance,
                    }
                )
                previous = f"Previous status: {old.verification_status or 'blank'}"
                if old.authority_score:
                    previous += f", score {old.authority_score:g}"
                source.notes = f"Re-tested this run. {previous}. {source.notes}"
                sources.append(source)
        return {"sources": sources, "issues": issues}

    def research(task: ParastatalTask, questions, already: set[str], note: str) -> dict:
        p, run = task["parastatal"], task["run"]
        known = set(task.get("known_urls", []))
        report(
            p.id,
            f"Searching the web for sources for {len(questions)} question(s) "
            "(this usually takes a few minutes)",
        )
        try:
            found, urls, rejected = call_json(
                services,
                "citation-builder",
                f"Parastatal: {p.name} ({p.id}), type {p.type}\n"
                f"City: {run.city_name}, {run.state_name}. City government (ULG): {run.ulg}\n"
                f"Official website: {p.official_website or 'not confirmed'}\n\n"
                f"{note}\nQuestions to support:\n{question_digest(questions)}\n\n"
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
            services, run, p, to_check, provenance="web_search", allowed_urls=urls | known
        ):
            issues += vet_issues
            if source:
                sources.append(source)
        return {"sources": sources, "tool_urls": sorted(urls), "issues": issues}

    def discover_sources(task: ParastatalTask) -> dict:
        already = {s.url for s in task.get("existing", [])} | set(task.get("covered_urls", []))
        return research(task, task["task_questions"], already, "")

    def fill_gaps(task: ParastatalTask) -> dict:
        """Second, targeted search for questions that still have no verified source."""
        sources = task.get("sources", []) + task.get("known_sources", [])
        covered = {
            q for s in sources if s.verification_status == "Verified" for q in s.question_ids
        }
        missing = [q for q in task["task_questions"] if q.id not in covered]
        if not missing:
            report(task["parastatal"].id, "Done: every question has at least one source")
            return {}
        report(
            task["parastatal"].id,
            f"Second search, for {len(missing)} question(s) that still have no source",
        )
        already = {s.url for s in sources}
        result = research(
            task,
            missing,
            already,
            f"A first search found sources for the other questions. These "
            f"{len(missing)} question(s) still have NO verified source; search "
            "specifically for documents that answer them.",
        )
        found = [x for x in result.get("sources", []) if x.verification_status == "Verified"]
        report(
            task["parastatal"].id, f"Done: the second search added {len(found)} verified source(s)"
        )
        return result

    graph = StateGraph(ParastatalTask, output_schema=ParastatalTaskOutput)
    graph.add_node("retest_existing", retest_existing)
    graph.add_node("discover_sources", discover_sources)
    graph.add_node("fill_gaps", fill_gaps)
    graph.add_edge(START, "retest_existing")
    graph.add_edge("retest_existing", "discover_sources")
    graph.add_edge("discover_sources", "fill_gaps")
    graph.add_edge("fill_gaps", END)
    return graph.compile(name="links_agent")
