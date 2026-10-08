"""Verticals: each is a settings file; all run the same Steps 1, 2 and 3."""

import dataclasses

import pytest

from asics_agent.config import _base_settings, get_settings
from asics_agent.verticals import CITY_UNIT_ID, agent_for, load_bank, load_verticals, settings_for


def test_parastatal_settings_are_unchanged():
    s = get_settings()
    base = _base_settings()
    assert s.vertical == "parastatal" and s.unit == "parastatal"
    assert s.question_bank == base.question_bank and s.outputs_dir == base.outputs_dir
    assert s.shared_rules == "shared-rules" and s.vertical_title == "Parastatal"
    for role, agent in [
        ("discover", "parastatal-discovery"),
        ("profile", "website-profiler"),
        ("sources", "citation-builder"),
        ("answer", "answer-writer"),
        ("score", "question-scorer"),
    ]:
        assert agent_for(s, role) == agent


def test_every_vertical_is_complete():
    found, issues = load_verticals(get_settings().agent_setup_dir)
    assert {"parastatal", "upd"} <= set(found) and issues == []


def test_upd_has_its_own_bank_agents_and_folders():
    u = settings_for(get_settings(), "upd")
    assert u.unit == "city_government" and u.vertical_code == "UPD"
    assert u.outputs_dir.parts[-2:] == ("verticals", "upd")
    assert agent_for(u, "answer") == "city-answer-writer" and u.shared_rules == "shared-rules-city"
    questions, issues = load_bank(u)
    assert len(questions) > 90 and questions["UPD 3"].children == ["UPD 3a", "UPD 3b", "UPD 3c"]
    assert not [i for i in issues if i.severity == "error"]


@pytest.fixture
def upd_services(tmp_path):
    from asics_agent.practice import practice_services

    upd = dataclasses.replace(
        settings_for(get_settings(), "upd"), outputs_dir=tmp_path, scoring_dir=tmp_path / "scoring"
    )
    return practice_services(upd)


def test_upd_runs_steps_1_2_3(upd_services, tmp_path):
    from asics_agent.agents.answers_master import build_answers_graph
    from asics_agent.agents.sources_master import build_sources_graph
    from asics_agent.cities import load_register
    from asics_agent.scoring.ai import run_ai_scoring
    from asics_agent.scoring.phase2 import phase2_status
    from asics_agent.scoring.skeleton import build_skeleton, gather_units
    from asics_agent.scoring.template import read_template

    s = upd_services.settings
    inputs = {"city": "sample_city_a", "only_questions": ["UPD 3"], "auto_approve": True}
    before = len(upd_services.llm.calls)
    sources = build_sources_graph(upd_services).invoke(inputs)
    assert [p.id for p in sources["parastatals"]] == [CITY_UNIT_ID]  # the city government
    assert "discover_parastatals" not in upd_services.llm.calls[before:]  # nothing to discover
    build_answers_graph(upd_services).invoke(inputs)
    status = phase2_status(s, "Sample City A")
    assert status.ready and status.answers.name.startswith("ASICS_UPD_")

    register, _ = load_register(s.city_register)
    questions, issues = load_bank(s)
    units, _ = gather_units(s)
    path = s.scoring_dir / "templates" / "upd.xlsx"
    build_skeleton(questions, units, path, "UPD", issues)
    report = run_ai_scoring(
        upd_services, read_template(path), "UPD", register, codes=["UPD3a"], workers=1
    )
    assert report.cities == ["Sample City A"]
    assert report.scored + report.needs_person == 1  # one row: the city government
