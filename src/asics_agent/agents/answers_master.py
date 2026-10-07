"""Step 2 master agent: answer questions ONLY from the city's reviewed Citation Sheet.

    initial_checks ─▶ prepare_citations ─▶ answer_<VERTICAL> × (parastatal, question)
        ─▶ finalize_answers  (roll-ups, final QA, the answers workbook)

No web research happens in this step. `prepare_citations` makes sure every row the team
marked "Use for Answers? = Yes" has readable, verified content: rows the team added are
opened and checked now, exactly like the agent's own rows were in Step 1.
"""

from pathlib import Path

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from asics_agent.agent_setup import fingerprint
from asics_agent.agents.common import (
    applicability_matrix,
    focus_on_selected,
    has_errors,
    selected_questions,
)
from asics_agent.agents.final_qa import qa_answers
from asics_agent.agents.initial_checks import build_initial_checks
from asics_agent.agents.rollup import compute_rollups
from asics_agent.agents.sections import build_section_agent, section_for, section_nodes
from asics_agent.agents.state import MasterState
from asics_agent.links.accessibility import check_url
from asics_agent.links.database import write_links_db
from asics_agent.models import ALL_PARASTATALS, Issue, Source
from asics_agent.run_options import RunOptions
from asics_agent.services import Services, default_services
from asics_agent.workbook import write_json, write_workbook

OUTPUT_NAME = "ASICS_Parastatal_{city}_Phase2.xlsx"


def usable(source: Source) -> bool:
    return (
        source.use_for_answers
        and source.verification_status == "Verified"
        and bool(source.content_path)
        and Path(source.content_path).exists()
    )


def build_answers_graph(
    services: Services | None = None, checkpointer: BaseCheckpointSaver | None = None
):
    services = services or default_services()
    root = services.settings.agent_setup_dir

    def after_checks(state: MasterState) -> str:
        return END if has_errors(state, "initial_checks") else "prepare_citations"

    def prepare_citations(state: MasterState) -> dict:
        run, settings = state["run"], services.settings
        citations, issues = [], []
        for s in state.get("existing_citations", []):
            if s.use_for_answers and not usable(s):
                check = check_url(s.url, services.http, Path(run.cache_dir), settings.user_agent)
                if check.verification_status == "Verified":
                    s = s.model_copy(
                        update={
                            "verification_status": "Verified",
                            "accessibility": "Public",
                            "content_path": check.content_path,
                            "snapshot_path": check.snapshot_path,
                            "checked_at": check.checked_at,
                            "notes": (
                                s.notes + " Checked again for Step 2: " + " ".join(check.reasons)
                            ).strip(),
                        }
                    )
                else:
                    issues.append(
                        Issue(
                            phase="prepare_citations",
                            severity="warning",
                            audience="team",
                            ref=s.citation_id or s.parastatal_id,
                            message=f"{s.citation_id or s.title}: this link couldn't be opened and "
                            f"read automatically, so answers can't use it ({' '.join(check.reasons)}"
                            "). Replace it with a direct link to the document if you can.",
                        )
                    )
            citations.append(s)
        in_use = sum(usable(s) for s in citations)
        issues.append(
            Issue(
                phase="prepare_citations",
                severity="info",
                audience="team",
                ref=run.city_name,
                message=f"{run.city_name}: answering from {in_use} Citation Sheet row(s) marked for "
                f"use (of {len(citations)} in the Sources workbook). No other sources are used.",
            )
        )
        matrix, matrix_issues = applicability_matrix(
            state["parastatals"], selected_questions(state)
        )
        return {
            "existing_citations": citations,
            "applicability": matrix,
            "issues": issues + matrix_issues,
        }

    def route_answers(state: MasterState):
        if state.get("skip_research"):
            return "finalize_answers"
        questions = state["questions"]
        citations = [s for s in state.get("existing_citations", []) if usable(s)]
        sends = []
        for p in state["parastatals"]:
            own = [s for s in citations if s.parastatal_id in (p.id, ALL_PARASTATALS)]
            for qid in state["applicability"].get(p.id, []):
                q = questions[qid]
                if q.is_rollup:
                    continue
                sends.append(
                    Send(
                        f"answer_{section_for(q.pillar, root)}",
                        {
                            "run": state["run"],
                            "parastatal": p,
                            "question": q,
                            "citation_sources": own,
                        },
                    )
                )
        return sends or "finalize_answers"

    def finalize_answers(state: MasterState) -> dict:
        run = state["run"]
        out_dir = Path(run.output_dir)
        citations = state.get("existing_citations", [])
        answers = state.get("answers", [])
        applicability = state.get("applicability", {})
        rollups = (
            []
            if state.get("skip_research")
            else compute_rollups(state["questions"], applicability, answers)
        )
        all_answers = answers + rollups

        selected_ids = [q.id for q in selected_questions(state)]
        issues = list(state.get("issues", []))
        if not state.get("skip_research"):
            issues = focus_on_selected(issues, state["questions"], set(selected_ids))
            issues += qa_answers(all_answers, citations, applicability)

        workbook = write_workbook(
            base=Path(state.get("base_workbook") or services.settings.question_bank),
            out=out_dir / OUTPUT_NAME.format(city=run.city_name.replace(" ", "_")),
            city_name=run.city_name,
            questions=state["questions"],
            selected=selected_ids,
            parastatals=state["parastatals"],
            applicability=applicability,
            sources=citations,
            answers=all_answers,
            issues=issues,
        )
        write_links_db(out_dir / "links.db", citations, set(), all_answers, issues)
        write_json(
            out_dir / "run_summary.json",
            {
                "run": run.model_dump(),
                "agent_setup_fingerprint": fingerprint(services.settings.agent_setup_dir),
                "memory_used": sorted({m for a in all_answers for m in a.memory_used}),
                "applicability": applicability,
                "counts": {
                    "citations_used": sum(usable(s) for s in citations),
                    "answers": len(all_answers),
                    "errors": sum(i.severity == "error" for i in issues),
                },
            },
        )
        return {
            "rollups": rollups,
            "output_workbook": str(workbook),
            "links_db": str(out_dir / "links.db"),
            "final_issues": issues,
        }

    graph = StateGraph(MasterState, context_schema=RunOptions)  # per-run options
    graph.add_node("initial_checks", build_initial_checks(services, step="answers"))
    graph.add_node("prepare_citations", prepare_citations)
    answer_nodes = []
    for code in section_nodes(root):
        name = f"answer_{code}"
        graph.add_node(name, build_section_agent(code, services))
        graph.add_edge(name, "finalize_answers")
        answer_nodes.append(name)
    graph.add_node("finalize_answers", finalize_answers)
    graph.add_edge(START, "initial_checks")
    graph.add_conditional_edges("initial_checks", after_checks, ["prepare_citations", END])
    graph.add_conditional_edges(
        "prepare_citations", route_answers, [*answer_nodes, "finalize_answers"]
    )
    graph.add_edge("finalize_answers", END)
    return graph.compile(checkpointer=checkpointer, name="asics_step2_answers")


# Entry point for `langgraph dev` / LangGraph Studio (see langgraph.json).
graph = build_answers_graph()
