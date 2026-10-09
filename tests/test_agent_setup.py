import dataclasses
import shutil

import pytest

from asics_agent.agent_setup import (
    MemoryScope,
    fingerprint,
    load_agents,
    save_note,
    select_notes,
    system_prompt,
    validate,
)
from asics_agent.config import PROJECT_ROOT, get_settings


@pytest.fixture
def setup_dir(tmp_path):
    root = tmp_path / "agent_setup"
    shutil.copytree(PROJECT_ROOT / "agent_setup", root)
    # Start from an empty memory folder, so the team's real notes don't change the results.
    for path in (root / "memory").rglob("*.md"):
        if path.name != "README.md":
            path.unlink()
    return root


def note(root, rel, text):
    path = root / "memory" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def picked(root, **scope):
    chosen, _ = select_notes(root, MemoryScope(**scope), "parastatal", 20000)
    return [n.path for n in chosen]


def test_every_agent_has_its_prompt_and_skills():
    root = PROJECT_ROOT / "agent_setup"
    agents, issues = load_agents(root)
    assert {
        "parastatal-discovery",
        "website-profiler",
        "citation-builder",
        "source-assessor",
        "answer-writer",
        "question-bank-reviewer",
    } <= set(agents)
    assert not [
        i
        for i in validate(root, ["Bengaluru"], "parastatal", {"UPD", "DPG", "SC"})
        if i.severity == "error"
    ]
    prompt = system_prompt(root, agents["answer-writer"])
    assert (
        prompt.index("ABSOLUTE URL RULES")
        < prompt.index("SKILL: scoring-methodology")
        < prompt.index("TASK: answer_question")
    )


def test_memory_is_picked_by_folder_and_settings(setup_dir):
    note(setup_dir, "general/terms.md", "ULG means the city government.")
    note(setup_dir, "cities/bengaluru.md", "Since 2025 the ULG is the GBA corporations.")
    note(setup_dir, "cities/chennai.md", "Chennai note.")
    note(setup_dir, "verticals/parastatal/boards.md", "Boards publish budgets under Finance.")
    note(setup_dir, "verticals/mobility/buses.md", "Mobility note.")
    note(setup_dir, "general/bwssb-only.md", "---\nparastatals: [BWSSB]\n---\nBWSSB note.")
    note(setup_dir, "general/answers-only.md", "---\nagents: [answer-writer]\n---\nAnswer note.")

    bwssb = picked(setup_dir, agent="citation-builder", city="Bengaluru", parastatals=["BWSSB"])
    assert bwssb == [
        "general/bwssb-only.md",
        "general/terms.md",
        "verticals/parastatal/boards.md",
        "cities/bengaluru.md",
    ]
    bmtc = picked(setup_dir, agent="answer-writer", city="Bengaluru", parastatals=["BMTC"])
    assert "general/bwssb-only.md" not in bmtc and "general/answers-only.md" in bmtc
    assert "cities/chennai.md" not in bmtc and "verticals/mobility/buses.md" not in bmtc


def test_size_limit_keeps_the_most_specific_notes(setup_dir):
    note(setup_dir, "general/long.md", "x" * 900)
    note(setup_dir, "cities/bengaluru.md", "y" * 900)
    chosen, skipped = select_notes(setup_dir, MemoryScope(city="Bengaluru"), "parastatal", 1000)
    assert [n.path for n in chosen] == ["cities/bengaluru.md"]
    assert [n.path for n in skipped] == ["general/long.md"]


def test_problems_in_the_setup_are_reported(setup_dir):
    (setup_dir / "skills" / "india-code-and-acts.md").unlink()
    note(setup_dir, "cities/atlantis.md", "Unknown city.")
    note(setup_dir, "general/broken.md", "---\nparastatals: [BWSSB\n---\nBroken.")
    issues = validate(setup_dir, ["Bengaluru"], "parastatal", {"UPD"})
    messages = " ".join(i.message for i in issues)
    assert any(i.severity == "error" and "india-code-and-acts" in i.message for i in issues)
    assert "atlantis.md is for a city that isn't in the city register" in messages
    assert "broken.md: the settings block at the top can't be read" in messages


def test_saving_a_note_keeps_the_previous_version(setup_dir):
    path = setup_dir / "memory" / "general" / "terms.md"
    save_note(setup_dir, path, "first")
    before = fingerprint(setup_dir)
    save_note(setup_dir, path, "second")
    assert path.read_text() == "second\n"
    assert list((setup_dir / "memory" / "_history").glob("*terms.md"))
    assert fingerprint(setup_dir) != before


def test_memory_reaches_the_model_and_is_recorded_on_answers(services, setup_dir):
    from asics_agent.agents.answers_master import build_answers_graph
    from asics_agent.agents.sources_master import build_sources_graph

    note(setup_dir, "cities/sample_city_a.md", "The Water Board's plans are on the portal.")
    services.settings = dataclasses.replace(services.settings, agent_setup_dir=setup_dir)
    inputs = {"city": "sample_city_a", "only_questions": ["UPD 1"], "auto_approve": True}
    build_sources_graph(services).invoke(inputs)
    result = build_answers_graph(services).invoke(inputs)

    answer = next(a for a in result["answers"] if a.question_id == "UPD 1a")
    assert answer.memory_used == ["cities/sample_city_a.md"]
    assert "Team context used" in answer.notes
    sent = [m for m in services.llm.sent if "The Water Board's plans are on the portal." in m]
    assert sent and all("CONTEXT FROM THE RESEARCH TEAM" in m for m in sent)


def test_web_research_only_for_agents_set_up_for_it(services):
    from asics_agent.agent_setup import load_agent

    root = get_settings().agent_setup_dir
    assert load_agent(root, "citation-builder").web_research
    assert not load_agent(root, "answer-writer").web_research


def test_note_title_comes_from_its_heading(setup_dir):
    from asics_agent.agent_setup import list_notes

    note(setup_dir, "general/budget-pages.md", "# Where budgets are published\n\nUnder Finance.")
    notes, _ = list_notes(setup_dir)
    assert (
        next(n for n in notes if n.path == "general/budget-pages.md").title
        == "Where budgets are published"
    )
