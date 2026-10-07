"""Sub-agent 1 — Initial checks.

Loads and validates every input before any money is spent on research: the question
bank, the city's parastatal list, an optional previous-phase workbook and credentials.
Errors stop the master agent; warnings are carried into the QA report.
"""

import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from asics_agent.agent_setup import validate as validate_setup
from asics_agent.agents.state import MasterState
from asics_agent.applicability import match_rule
from asics_agent.cities import issues_for_city, load_register
from asics_agent.llm import call_json
from asics_agent.models import Issue, RunContext
from asics_agent.question_bank import load_question_bank
from asics_agent.services import Services
from asics_agent.sources_workbook import read_sources_workbook, sources_path, workspace_for

_SCALE = re.compile(r"(?im)^\s*(?:score\s*)?(\d+(?:\.\d+)?)\s*(?:—|–|-|marks|if|where)")


class InitialChecksInput(TypedDict, total=False):
    city: str
    base_workbook: str | None
    only_parastatals: list[str] | None
    llm_bank_review: bool


class BankIssue(BaseModel):
    question_id: str
    severity: str = "warning"
    message: str


class BankReview(BaseModel):
    issues: list[BankIssue] = Field(default_factory=list)


def _issue(severity: str, message: str, ref: str | None = None, team: bool = False) -> Issue:
    return Issue(
        phase="initial_checks",
        severity=severity,
        message=message,
        ref=ref,
        audience="team" if team else "developer",
    )


def build_initial_checks(services: Services, step: str = "sources"):
    settings = services.settings

    def load_inputs(state: MasterState) -> dict:
        issues: list[Issue] = []
        configs, register_issues = load_register(settings.city_register)
        city = configs.get(state["city"])
        if city is None:
            names = ", ".join(c.name for c in configs.values()) or "none"
            return {
                "issues": register_issues
                + [
                    _issue(
                        "error",
                        f'The city "{state["city"]}" isn\'t in the city register, or it is '
                        f"marked not to include. Cities available: {names}.",
                        team=True,
                    )
                ]
            }
        issues += issues_for_city(register_issues, city.name)
        questions, bank_issues = load_question_bank(settings.question_bank)
        issues += bank_issues

        workspace = workspace_for(settings.outputs_dir, city.name)
        run_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
        run = RunContext(
            run_id=run_id,
            city=city.slug,
            city_name=city.name,
            state_name=city.state,
            ulg=city.ulg,
            workspace=str(workspace),
            output_dir=str(workspace if step == "sources" else workspace / "answers" / run_id),
            cache_dir=str(workspace / "evidence"),
        )

        # The city's Sources workbook: step 1 builds on it, step 2 answers from it.
        known, citations = list(city.parastatals), []
        sources_file = sources_path(workspace, city.name)
        if sources_file.exists():
            earlier, citations, wb_issues = read_sources_workbook(sources_file, Path(run.cache_dir))
            issues += wb_issues
            for p in earlier:  # the Sources workbook has the team's latest decisions
                known = [k for k in known if k.id != p.id] + [p]
        elif step == "answers":
            issues.append(
                _issue(
                    "error",
                    f"{city.name} has no Sources workbook yet. Run Step 1 "
                    "(Find parastatals and sources) first.",
                    city.name,
                    team=True,
                )
            )

        parastatals = [p for p in known if p.include]
        if step == "answers":
            if only := state.get("only_parastatals"):
                if unknown := set(only) - {p.id for p in parastatals}:
                    issues.append(
                        _issue(
                            "error",
                            f"These parastatals aren't included in the {city.name} Sources "
                            f"workbook: {', '.join(sorted(unknown))}.",
                            city.name,
                            team=True,
                        )
                    )
                parastatals = [p for p in parastatals if p.id in only]
            if sources_file.exists() and not parastatals:
                issues.append(
                    _issue(
                        "error",
                        f"No parastatals are marked Include = Yes in the "
                        f"{city.name} Sources workbook.",
                        city.name,
                        team=True,
                    )
                )

        if (base := state.get("base_workbook")) and not Path(base).exists():
            issues.append(
                _issue("error", f"The previous workbook couldn't be found: {base}", team=True)
            )
        return {
            "run": run,
            "city_config": city,
            "questions": questions,
            "known_parastatals": known,
            "parastatals": parastatals,
            "existing_citations": citations,
            "issues": issues,
        }

    def structural_checks(state: MasterState) -> dict:
        if "questions" not in state:  # the city couldn't be loaded; nothing to check
            return {}
        configs, _ = load_register(settings.city_register)
        issues: list[Issue] = validate_setup(
            settings.agent_setup_dir,
            [c.name for c in configs.values()],
            settings.vertical,
            {q.pillar for q in state["questions"].values()},
        )
        questions = state["questions"]
        for q in questions.values():
            if match_rule(q.applicability) is None:
                issues.append(
                    _issue(
                        "warning",
                        f"{q.raw_id}: we don't recognise who this applies to "
                        f'("{q.applicability}"), so it is included for every parastatal. '
                        "Ask your developer to add a rule for this wording.",
                        q.id,
                        team=True,
                    )
                )
            if q.max_score is None:
                issues.append(
                    _issue(
                        "warning",
                        f"{q.raw_id}: no maximum score in the question bank. Please add one.",
                        q.id,
                        team=True,
                    )
                )
            if not q.is_rollup and not q.methodology:
                issues.append(
                    _issue(
                        "warning",
                        f"{q.raw_id}: no Detailed Methodology in the "
                        "question bank, so answers can't be scored.",
                        q.id,
                        team=True,
                    )
                )
            scale = [float(n) for n in _SCALE.findall(q.methodology)]
            if q.max_score and scale and max(scale) > q.max_score:
                issues.append(
                    _issue(
                        "warning",
                        f"{q.raw_id}: the scoring guide goes up to {max(scale):g}, but the "
                        f"maximum score is {q.max_score:g}. Please confirm which is right. "
                        f"Until then, scores above {q.max_score:g} are reduced to "
                        f"{q.max_score:g}.",
                        q.id,
                        team=True,
                    )
                )
            if q.is_rollup and "sum" not in q.methodology.lower():
                issues.append(
                    _issue(
                        "info",
                        f"{q.raw_id}: the methodology doesn't say how its sub-questions add up, "
                        "so its total is left for a person to score.",
                        q.id,
                        team=True,
                    )
                )
        if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")):
            issues.append(
                _issue(
                    "warning",
                    "ANTHROPIC_API_KEY is not set; relying on an "
                    "`ant auth login` profile if one exists",
                )
            )
        return {"issues": issues}

    def llm_bank_review(state: MasterState) -> dict:
        if not state.get("llm_bank_review") or "questions" not in state:
            return {}
        rows = "\n\n".join(
            f"{q.id} | {q.tag} | max {q.max_score} | {q.assessment_level} | {q.applicability}\n"
            f"Q: {q.text}\nMethodology: {q.methodology}"
            for q in state["questions"].values()
        )
        review, _, _ = call_json(services, "question-bank-reviewer", rows, BankReview)
        return {
            "issues": [
                _issue(
                    "error" if i.severity == "error" else "warning",
                    f"{i.question_id} (suggested by the automatic review): {i.message}",
                    i.question_id,
                    team=True,
                )
                for i in review.issues
            ]
        }

    graph = StateGraph(MasterState, input_schema=InitialChecksInput)
    graph.add_node("load_inputs", load_inputs)
    graph.add_node("structural_checks", structural_checks)
    graph.add_node("llm_bank_review", llm_bank_review)
    graph.add_edge(START, "load_inputs")
    graph.add_edge("load_inputs", "structural_checks")
    graph.add_edge("structural_checks", "llm_bank_review")
    graph.add_edge("llm_bank_review", END)
    return graph.compile(name="initial_checks")
