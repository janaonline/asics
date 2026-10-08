"""Step 1 master agent: find a city's parastatals and build its Citation Sheet.

    initial_checks ─▶ parastatal_discovery ─▶ confirm_scope (human) ─▶ links_agent × parastatal
        ─▶ finalize_sources  (writes the city's Sources workbook)

The research team then reviews the Sources workbook, and can add to it, before Step 2
answers questions from it (see answers_master.py).
"""

from pathlib import Path

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send, interrupt

from asics_agent.agent_setup import fingerprint
from asics_agent.agents.common import (
    CandidateSource,
    dedupe_sources,
    focus_on_selected,
    has_errors,
    selected_questions,
    vet_source,
)
from asics_agent.agents.final_qa import qa_sources
from asics_agent.agents.initial_checks import build_initial_checks
from asics_agent.agents.links_builder import build_links_agent
from asics_agent.agents.parastatal_discovery import build_parastatal_discovery
from asics_agent.agents.state import MasterState
from asics_agent.links.database import write_links_db
from asics_agent.models import ALL_PARASTATALS, Issue, Parastatal
from asics_agent.run_options import RunOptions
from asics_agent.services import Services, default_services
from asics_agent.sources_workbook import sources_path, write_sources_workbook
from asics_agent.workbook import read_citation_sheet, write_checks_workbook, write_json


def _to_research(state: MasterState) -> list[Parastatal]:
    only = set(state.get("only_parastatals") or [])
    return [p for p in state.get("parastatals", []) if p.include and (not only or p.id in only)]


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
                "message": 'Review the parastatals found. Resume with {"action": "approve"}, '
                '{"action": "stop"}, or {"action": "edit", "parastatals": '
                "[ids to research]}.",
                "parastatals": [p.model_dump() for p in _to_research(state)],
                "applicability": {
                    p.id: state["applicability"].get(p.id, []) for p in _to_research(state)
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

    def route_links(state: MasterState):
        if state.get("skip_research"):
            return "finalize_sources"
        questions = state["questions"]
        earlier = list(state.get("existing_citations", []))
        if base := state.get("base_workbook"):
            seeded, _ = read_citation_sheet(Path(base), state["parastatals"])
            earlier += seeded
        found = state.get("sources", [])
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
                    "known_sources": [s for s in found if s.parastatal_id == p.id],
                    "covered_urls": [s.url for s in found if s.parastatal_id == p.id],
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
        everyone = Parastatal(
            id=ALL_PARASTATALS, name=f"All parastatals in {run.city_name}", type="other"
        )
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
    graph.add_node("links_agent", build_links_agent(services))
    graph.add_node("finalize_sources", finalize_sources)
    graph.add_edge(START, "initial_checks")
    graph.add_conditional_edges("initial_checks", after_checks, ["parastatal_discovery", END])
    graph.add_edge("parastatal_discovery", "confirm_scope")
    graph.add_conditional_edges("confirm_scope", route_links, ["links_agent", "finalize_sources"])
    graph.add_edge("links_agent", "finalize_sources")
    graph.add_edge("finalize_sources", END)
    return graph.compile(checkpointer=checkpointer, name="asics_step1_sources")


# Entry point for `langgraph dev` / LangGraph Studio (see langgraph.json).
graph = build_sources_graph()
