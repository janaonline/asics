"""Sub-agent 2 — Parastatal discovery.

The agent works out for itself which parastatals serve the city (the research team's list,
if any, is only a starting point), then profiles each one in parallel:

  discover ──▶ profile_parastatal × parastatal ──▶ finish

Profiling establishes the governing Act, status and chief-executive/budget facts, and finds
the official website. Every candidate website is opened and rated by the website trust check
(links/trust.py); the best one scoring "Probably official" or better becomes the official
website, and research continues either way.
"""

import re
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from pydantic import BaseModel, Field

from asics_agent.agent_setup import MemoryScope
from asics_agent.agents.common import (
    CandidateSource,
    applicability_matrix,
    memory_note,
    selected_questions,
    vet_source,
)
from asics_agent.agents.state import MasterState
from asics_agent.links.accessibility import check_url
from asics_agent.links.trust import best_official, host_of, is_official_host, rate_website
from asics_agent.llm import CallFailed, call_json
from asics_agent.models import Issue, Parastatal, Question, RunContext
from asics_agent.progress import report
from asics_agent.services import Services

MAX_CANDIDATES = 4


class Discovered(BaseModel):
    id: str
    name: str
    type: str = "other"
    revenue_raising: bool | None = None
    capex_mandate: bool | None = None
    why_included: str = ""
    evidence_urls: list[str] = Field(default_factory=list)


class DiscoverReply(BaseModel):
    parastatals: list[Discovered] = Field(default_factory=list)
    notes: str = ""


class ProfileReply(BaseModel):
    governing_act: str | None = None
    current_status: str = "Unknown"
    has_chief_executive: bool | None = None
    has_annual_budget: bool | None = None
    candidate_websites: list[str] = Field(default_factory=list)
    government_pages_checked: list[str] = Field(default_factory=list)
    notes: str = ""


class DiscoveryInput(TypedDict, total=False):
    run: RunContext
    questions: dict[str, Question]
    known_parastatals: list[Parastatal]  # from the city register / an earlier Sources workbook
    only_parastatals: list[str] | None
    only_pillars: list[str] | None
    only_questions: list[str] | None
    skip_research: bool


class ProfileTask(TypedDict, total=False):
    run: RunContext
    parastatal: Parastatal
    official_pages: list[tuple[str, str]]


def _team(severity: str, message: str, ref: str | None) -> Issue:
    return Issue(
        phase="parastatal_checks", severity=severity, message=message, ref=ref, audience="team"
    )


def _clean_id(value: str, name: str) -> str:
    pid = re.sub(r"[^A-Z0-9]", "", value.upper())
    return pid or "".join(w[0] for w in re.findall(r"[A-Za-z]+", name)).upper()[:8]


def _same(a: Parastatal, b: Parastatal) -> bool:
    norm = lambda s: re.sub(r"[^a-z]", "", s.lower())  # noqa: E731
    return a.id == b.id or norm(a.name) == norm(b.name)


def build_parastatal_discovery(services: Services):
    def discover(state: MasterState) -> dict:
        run = state["run"]
        known = list(state.get("known_parastatals") or [])
        if state.get("skip_research"):
            return {"parastatals": known}
        listed = "\n".join(f"- {p.name} ({p.id})" for p in known) or "(none)"
        report(run.city_name, "Searching for the city's parastatals (usually a few minutes)")
        pages: list[tuple[str, str]] = []
        try:
            reply, urls, rejected = call_json(
                services,
                "parastatal-discovery",
                f"City: {run.city_name}, {run.state_name}\nCity government (ULG): {run.ulg}\n\n"
                f"Already listed by the research team (include these, then find any others):\n"
                f"{listed}",
                DiscoverReply,
                scope=(scope := MemoryScope(city=run.city_name)),
                pages=pages,
            )
        except CallFailed as exc:
            return {
                "parastatals": known,
                "issues": [
                    _team(
                        "error",
                        f"Couldn't research the parastatals for {run.city_name}: {exc}. "
                        "Try again, or add them to the city register.",
                        run.city_name,
                    )
                ],
            }

        parastatals = list(known)
        added = []
        for item in reply.parastatals:
            kind = (
                item.type
                if item.type
                in {"water_supply_board", "transport_corporation", "development_authority"}
                else "other"
            )
            evidence = [u for u in item.evidence_urls if u in urls]
            candidate = Parastatal(
                id=_clean_id(item.id, item.name),
                name=item.name.strip(),
                type=kind,
                revenue_raising=bool(item.revenue_raising),
                capex_mandate=bool(item.capex_mandate),
                found_by="Agent",
                why_included=item.why_included,
                notes="Evidence: " + ", ".join(evidence)
                if evidence
                else "No supporting link was returned by a search; please check.",
            )
            match = next((p for p in parastatals if _same(p, candidate)), None)
            if match:  # the team already listed it: keep the team's details
                match.why_included = match.why_included or candidate.why_included
                continue
            while any(p.id == candidate.id for p in parastatals):
                candidate.id += "2"
            parastatals.append(candidate)
            added.append(candidate)

        issues = [
            Issue(phase="parastatal_checks", severity="info", ref=run.city_name, message=m)
            for m in rejected
        ] + memory_note(scope, run.city_name, "Parastatal discovery")
        names = ", ".join(f"{p.name} ({p.id})" for p in parastatals) or "none"
        issues.append(
            _team(
                "info",
                f"{run.city_name}: {len(parastatals)} parastatal(s) to "
                f"assess ({len(added)} found by the agent): {names}.",
                run.city_name,
            )
        )
        if reply.notes:
            issues.append(
                _team(
                    "info",
                    f"{run.city_name}, notes from the research: {reply.notes}",
                    run.city_name,
                )
            )
        report(run.city_name, f"Done: {len(parastatals)} parastatal(s) to assess")
        official = [(u, t) for u, t in pages if is_official_host(u)]
        return {
            "parastatals": parastatals,
            "discovery_pages": official,
            "tool_urls": sorted(urls),
            "issues": issues,
        }

    def fan_out(state: MasterState):
        if state.get("skip_research") or not state.get("parastatals"):
            return "finish"
        only = set(state.get("only_parastatals") or [])
        todo = [p for p in state["parastatals"] if p.include and (not only or p.id in only)]
        # Parastatals the team excluded (Include? = No) are kept but not researched.
        return [
            Send(
                "profile_parastatal",
                {
                    "run": state["run"],
                    "parastatal": p,
                    "official_pages": state.get("discovery_pages", []),
                },
            )
            for p in todo
        ] or "finish"

    def profile_parastatal(task: ProfileTask) -> dict:
        p, run = task["parastatal"].model_copy(deep=True), task["run"]
        pages: list[tuple[str, str]] = []
        report(p.id, "Researching its Act, status and official website")
        try:
            reply, urls, rejected = call_json(
                services,
                "website-profiler",
                f"Parastatal: {p.name} ({p.id})\nCity: {run.city_name}, {run.state_name}\n"
                f"Type: {p.type}\nCity government (ULG): {run.ulg}",
                ProfileReply,
                scope=(scope := MemoryScope(city=run.city_name, parastatals=[p.id])),
                pages=pages,
            )
        except CallFailed as exc:
            return {
                "profiled": [p],
                "issues": [
                    _team(
                        "error",
                        f"{p.name}: couldn't research this parastatal ({exc}). Run Step 1 again.",
                        p.id,
                    )
                ],
            }

        p.governing_act = reply.governing_act or ""
        p.current_status = reply.current_status
        if p.found_by == "Agent":  # keep facts the team entered themselves
            if reply.has_chief_executive is not None:
                p.has_chief_executive = reply.has_chief_executive
            if reply.has_annual_budget is not None:
                p.has_annual_budget = reply.has_annual_budget
        official_pages = task.get("official_pages", []) + [
            (u, t) for u, t in pages if is_official_host(u)
        ]

        checks = []
        seen = set()
        for url in reply.candidate_websites:
            if url not in urls or host_of(url) in seen or len(checks) >= MAX_CANDIDATES:
                continue
            seen.add(host_of(url))
            report(p.id, f"Checking candidate website {url}")
            access = check_url(
                url, services.http, Path(run.cache_dir), services.settings.user_agent
            )
            checks.append(rate_website(url, access, p.id, p.name, official_pages))
        checks.sort(key=lambda c: c.score, reverse=True)
        best = best_official(checks)
        p.website_check = best or (checks[0] if checks else None)
        p.other_websites = [c for c in checks if c is not p.website_check]
        p.official_website = best.url if best else ""

        issues = [
            Issue(phase="parastatal_checks", severity="info", ref=p.id, message=m) for m in rejected
        ] + memory_note(scope, p.id, "Website profiler")
        sources = []
        if best is None:
            top = (
                f" The best candidate was {checks[0].url} ({checks[0].summary})."
                if checks
                else " No candidate website was found."
            )
            issues.append(
                _team(
                    "warning",
                    f"{p.name}: no website could be confirmed as "
                    f"official.{top} Sources will still be researched.",
                    p.id,
                )
            )
        else:
            if best.band == "Probably official":
                issues.append(
                    _team(
                        "warning",
                        f"{p.name}: the website {best.url} is probably "
                        f"official ({best.summary}). Please confirm it.",
                        p.id,
                    )
                )
            site, _ = vet_source(
                services,
                run,
                p,
                CandidateSource(
                    title=f"{p.name} — official website",
                    url=best.url,
                    source_type="Official website",
                    useful_for="Official information published by the parastatal",
                ),
                provenance="web_search",
                allowed_urls=urls,
            )
            if site:
                site.notes = f"Website check {best.summary}. {site.notes}"
                sources.append(site)
        if p.current_status and not p.current_status.lower().startswith("active"):
            issues.append(
                _team(
                    "warning",
                    f"{p.name}: may not be active under this name "
                    f'("{p.current_status}"). Please confirm.',
                    p.id,
                )
            )
        if reply.notes:
            p.notes = (p.notes + " " + reply.notes).strip()
        return {"profiled": [p], "sources": sources, "tool_urls": sorted(urls), "issues": issues}

    def finish(state: MasterState) -> dict:
        profiled = {p.id: p for p in state.get("profiled", [])}
        parastatals = [profiled.get(p.id, p) for p in state.get("parastatals", [])]
        matrix, issues = applicability_matrix(parastatals, selected_questions(state))
        return {"parastatals": parastatals, "applicability": matrix, "issues": issues}

    graph = StateGraph(MasterState, input_schema=DiscoveryInput)
    graph.add_node("discover", discover)
    graph.add_node("profile_parastatal", profile_parastatal)
    graph.add_node("finish", finish)
    graph.add_edge(START, "discover")
    graph.add_conditional_edges("discover", fan_out, ["profile_parastatal", "finish"])
    graph.add_edge("profile_parastatal", "finish")
    graph.add_edge("finish", END)
    return graph.compile(name="parastatal_discovery")
