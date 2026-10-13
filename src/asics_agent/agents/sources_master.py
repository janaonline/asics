"""Step 1 master agent: find a city's parastatals and build its Citation Sheet.

    initial_checks ─▶ parastatal_discovery ─▶ confirm_scope (human) ─▶ shared_laws
        ─▶ links_agent × parastatal ─▶ finalize_sources  (writes the city's Sources workbook)

shared_laws looks once per city for the state laws every parastatal shares (the city
government's Act, the Town and Country Planning Act); they go in the Citation Sheet as
"All parastatals" rows, and each parastatal's search skips them.

The research team then reviews the Sources workbook, and can add to it, before Step 2
answers questions from it (see answers_master.py).
"""

from pathlib import Path

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send, interrupt

from asics_agent.agent_setup import MemoryScope, fingerprint
from asics_agent.agents.common import (
    CandidateList,
    CandidateSource,
    dedupe_sources,
    focus_on_selected,
    has_errors,
    memory_note,
    question_digest,
    selected_questions,
    tool_note,
    vet_many,
    vet_source,
)
from asics_agent.agents.final_qa import qa_sources
from asics_agent.agents.initial_checks import build_initial_checks
from asics_agent.agents.links_builder import build_links_agent
from asics_agent.agents.parastatal_discovery import build_parastatal_discovery
from asics_agent.agents.state import MasterState
from asics_agent.links.database import write_links_db
from asics_agent.links.manual import team_check
from asics_agent.llm import CallFailed, call_json
from asics_agent.models import ALL_PARASTATALS, Issue, Parastatal, Source
from asics_agent.progress import report
from asics_agent.run_options import RunOptions, current_options
from asics_agent.services import Services, default_services
from asics_agent.sources_workbook import sources_path, write_sources_workbook
from asics_agent.tools import ToolContext
from asics_agent.verticals import agent_for
from asics_agent.workbook import read_citation_sheet, write_checks_workbook, write_json

SHARED_TAGS = ("[ULG-LAW]", "[TCP]", "[CROSSLAW]")  # evidence tags shared by every parastatal


def _shared_law(source: Source) -> bool:
    return source.parastatal_id == ALL_PARASTATALS and any(
        tag in (source.useful_for or "") for tag in SHARED_TAGS
    )


def _everyone(city_name: str) -> Parastatal:
    return Parastatal(id=ALL_PARASTATALS, name=f"All parastatals in {city_name}", type="other")


def _to_research(state: MasterState) -> list[Parastatal]:
    return [p for p in _to_review(state) if p.include]


def _to_review(state: MasterState) -> list[Parastatal]:
    """Every parastatal shown on the review screen: ticked ones and unticked NEEDS REVIEW ones."""
    only = set(state.get("only_parastatals") or [])
    return [p for p in state.get("parastatals", []) if not only or p.id in only]


def build_sources_graph(
    services: Services | None = None, checkpointer: BaseCheckpointSaver | None = None
):
    services = services or default_services()

    def after_checks(state: MasterState) -> str:
        return END if has_errors(state, "initial_checks") else "parastatal_discovery"

    def confirm_scope(state: MasterState) -> dict:
        city_level = services.settings.unit == "city_government"  # one unit: nothing to review
        if state.get("auto_approve") or state.get("skip_research") or city_level:
            return {}
        decision = interrupt(
            {
                "message": "Review the parastatals found. Ones with include = false (NEEDS "
                'REVIEW) are not researched unless you tick them. Resume with {"action": '
                '"approve"} (research the ones with include = true), {"action": "stop"}, or '
                '{"action": "edit", "parastatals": [ids to research]}.',
                "parastatals": [p.model_dump() for p in _to_review(state)],
                "applicability": {
                    p.id: state["applicability"].get(p.id, []) for p in _to_review(state)
                },
                "issues": [
                    i.model_dump()
                    for i in state.get("issues", [])
                    if i.phase == "parastatal_checks"
                ],
            }
        )
        action = (decision or {}).get("action", "approve")
        if action == "stop":
            return {
                "skip_research": True,
                "issues": [
                    Issue(
                        phase="confirm_scope",
                        severity="info",
                        audience="team",
                        message="Stopped at the review step. The parastatals found are saved in the "
                        "Sources workbook, but no sources were researched.",
                    )
                ],
            }
        if action == "edit":
            keep = set(decision.get("parastatals") or [])
            # Unticked parastatals stay in the Sources workbook with Include? = No.
            return {
                "parastatals": [
                    p.model_copy(update={"include": p.id in keep}) for p in state["parastatals"]
                ]
            }
        return {}

    def shared_laws(state: MasterState) -> dict:
        """One search per city for the state laws every parastatal shares, instead of one per
        parastatal. Skipped for a single unit (e.g. UPD's city government), and on a repeat
        run whose Citation Sheet already has them."""
        todo = _to_research(state)
        if state.get("skip_research") or services.settings.unit != "parastatal" or len(todo) < 2:
            return {}
        run = state["run"]
        earlier = [s for s in state.get("existing_citations", []) if _shared_law(s)]
        if earlier and not current_options().full_refresh:
            return {}
        everyone = _everyone(run.city_name)
        wanted = {q for p in todo for q in state["applicability"].get(p.id, [])}
        questions = [
            q for q_id, q in state["questions"].items() if q_id in wanted and not q.is_rollup
        ]
        report(run.city_name, "Searching once for the state laws all parastatals share")
        try:
            found, urls, rejected = call_json(
                services,
                agent_for(services.settings, "sources"),
                f"{services.settings.unit_label}: {everyone.name} ({ALL_PARASTATALS})\n"
                f"City: {run.city_name}, {run.state_name}. City government (ULG): {run.ulg}\n"
                f"Parastatals: {', '.join(p.name for p in todo)}\n\n"
                "SHARED LAWS ONLY: find the state laws every parastatal here shares - "
                "[ULG-LAW] the city government's Act (and its Rules), [TCP] the Town and Country "
                "Planning Act (and its Rules), and [CROSSLAW] state laws naming these services "
                "(service guarantee, RTI rules, procurement). Do not look for any one "
                "parastatal's own Act, website or documents: each is researched separately.\n"
                f"Questions these laws may help with:\n{question_digest(questions)}",
                CandidateList,
                scope=(scope := MemoryScope(city=run.city_name)),
                known_urls=set(state.get("tool_urls", [])),
                tool_context=(
                    tools := ToolContext(services=services, run=run, progress_key=run.city_name)
                ),
                web_max_uses=services.settings.find_sources_max_uses,
            )
        except CallFailed as exc:
            message = f"Couldn't search for the shared state laws ({exc}); each parastatal's "
            message += "search will look for them instead."
            return {"issues": [Issue(phase="links", severity="warning", message=message)]}
        issues = [
            Issue(phase="links", severity="info", ref=run.city_name, message=m) for m in rejected
        ]
        issues += memory_note(scope, run.city_name, "Shared-laws search")
        issues += tool_note(tools, run.city_name, "Shared-laws search")
        if found.notes:
            issues.append(
                Issue(phase="links", severity="info", ref=run.city_name, message=found.notes)
            )
        sources = []
        for _, source, vet_issues in vet_many(
            services, run, everyone, found.sources, provenance="web_search", allowed_urls=urls
        ):
            issues += vet_issues
            if source:
                sources.append(source.model_copy(update={"parastatal_id": ALL_PARASTATALS}))
        verified = sum(s.verification_status == "Verified" for s in sources)
        report(run.city_name, f"Done: {verified} shared law source(s) verified")
        return {"sources": sources, "tool_urls": sorted(urls), "issues": issues}

    def route_links(state: MasterState):
        if state.get("skip_research"):
            return "finalize_sources"
        questions = state["questions"]
        earlier = list(state.get("existing_citations", []))
        if base := state.get("base_workbook"):
            seeded, _ = read_citation_sheet(Path(base), state["parastatals"])
            earlier += seeded
        found = state.get("sources", [])
        shared = [s for s in found + earlier if _shared_law(s)]  # never re-vetted per agency
        return [
            Send(
                "links_agent",
                {
                    "run": state["run"],
                    "parastatal": p,
                    "task_questions": [
                        questions[q]
                        for q in state["applicability"].get(p.id, [])
                        if not questions[q].is_rollup
                    ],
                    "existing": [s for s in earlier if s.parastatal_id == p.id],
                    "known_sources": [s for s in found if s.parastatal_id == p.id]
                    + [s for s in shared if s.verification_status == "Verified"],
                    "covered_urls": [s.url for s in found if s.parastatal_id == p.id]
                    + [s.url for s in shared],
                    "shared_laws": [f"{s.title}: {s.url}" for s in shared],
                    "known_urls": state.get("tool_urls", []),
                },
            )
            for p in _to_research(state)
        ] or "finalize_sources"

    def finalize_sources(state: MasterState) -> dict:
        run = state["run"]
        researched = (
            {p.id for p in _to_research(state)} if not state.get("skip_research") else set()
        )
        issues = list(state.get("issues", []))
        # Earlier rows that weren't re-tested this run are kept as they were.
        kept = [
            s
            for s in state.get("existing_citations", [])
            if s.parastatal_id not in researched and s.parastatal_id != ALL_PARASTATALS
        ]
        # Rows the team added for "All parastatals" are re-tested here.
        everyone = _everyone(run.city_name)
        shared = []
        for old in state.get("existing_citations", []):
            if old.parastatal_id != ALL_PARASTATALS:
                continue
            if state.get("skip_research"):
                shared.append(old)
                continue
            source, _ = vet_source(
                services,
                run,
                everyone,
                CandidateSource(
                    title=old.title,
                    url=old.url,
                    source_type=old.source_type,
                    useful_for=old.useful_for,
                    question_ids=old.question_ids,
                ),
                provenance=old.provenance,
                allowed_urls=None,
                team_copy=team_check(old),
            )
            shared.append(
                (source or old).model_copy(
                    update={
                        "parastatal_id": ALL_PARASTATALS,
                        "citation_id": old.citation_id,
                        "use_for_answers": old.use_for_answers,
                        "team_notes": old.team_notes,
                        "found_by": old.found_by,
                        "provenance": old.provenance,
                    }
                )
            )

        sources = dedupe_sources(state.get("sources", []) + kept + shared)
        tool_urls = set(state.get("tool_urls", []))
        selected_ids = {q.id for q in selected_questions(state)}
        if not state.get("skip_research"):  # a checks-only run shows every bank problem
            issues = focus_on_selected(issues, state["questions"], selected_ids)
        if not state.get("skip_research"):
            issues += qa_sources([s for s in sources if s.parastatal_id in researched], tool_urls)

        workspace = Path(run.workspace)
        stopped_at_review = any(i.phase == "confirm_scope" for i in issues)
        if state.get("skip_research") and not stopped_at_review:
            # Checks only: report, but leave the team's Sources workbook untouched.
            name = f"ASICS_{run.city_name.replace(' ', '_')}_Checks_{run.run_id}.xlsx"
            report = write_checks_workbook(workspace / "checks" / name, run.city_name, issues)
            return {
                "output_workbook": str(report),
                "final_issues": issues,
                "final_sources": sources,
            }
        path = write_sources_workbook(
            sources_path(workspace, run.city_name),
            run.city_name,
            state.get("parastatals", []),
            sources,
            state["questions"],
            state.get("applicability", {}),
            issues,
        )
        write_links_db(workspace / "links.db", sources, tool_urls, (), issues)
        write_json(
            workspace / "sources_summary.json",
            {
                "run": run.model_dump(),
                "agent_setup_fingerprint": fingerprint(services.settings.agent_setup_dir),
                "parastatals": [p.model_dump() for p in state.get("parastatals", [])],
                "counts": {
                    "sources": len(sources),
                    "verified": sum(s.verification_status == "Verified" for s in sources),
                },
            },
        )
        return {
            "output_workbook": str(path),
            "links_db": str(workspace / "links.db"),
            "final_issues": issues,
            "final_sources": sources,
        }

    graph = StateGraph(MasterState, context_schema=RunOptions)  # per-run options
    graph.add_node("initial_checks", build_initial_checks(services, step="sources"))
    graph.add_node("parastatal_discovery", build_parastatal_discovery(services))
    graph.add_node("confirm_scope", confirm_scope)
    graph.add_node("shared_laws", shared_laws)
    graph.add_node("links_agent", build_links_agent(services))
    graph.add_node("finalize_sources", finalize_sources)
    graph.add_edge(START, "initial_checks")
    graph.add_conditional_edges("initial_checks", after_checks, ["parastatal_discovery", END])
    graph.add_edge("parastatal_discovery", "confirm_scope")
    graph.add_edge("confirm_scope", "shared_laws")
    graph.add_conditional_edges("shared_laws", route_links, ["links_agent", "finalize_sources"])
    graph.add_edge("links_agent", "finalize_sources")
    graph.add_edge("finalize_sources", END)
    return graph.compile(checkpointer=checkpointer, name="asics_step1_sources")


# Entry point for `langgraph dev` / LangGraph Studio (see langgraph.json).
graph = build_sources_graph()
