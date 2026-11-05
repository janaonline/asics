import dataclasses
import os

import pytest

# Tests use a fake model; this only keeps the module-level default graphs importable.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-used")


@pytest.fixture
def services(tmp_path):
    """Practice services: scripted Claude, sample web pages, made-up cities, temp outputs."""
    from asics_agent.config import get_settings
    from asics_agent.practice import practice_services

    settings = dataclasses.replace(get_settings(), outputs_dir=tmp_path, outputs_root=tmp_path)
    return practice_services(settings)


@pytest.fixture
def run_steps(services):
    """Run Step 1 then (optionally) Step 2 for Sample City A, limited to UPD 1."""
    from asics_agent.agents.answers_master import build_answers_graph
    from asics_agent.agents.sources_master import build_sources_graph

    def run(step: str, **extra):
        inputs = {
            "city": "sample_city_a",
            "only_questions": ["UPD 1"],
            "auto_approve": True,
            **extra,
        }
        build = build_sources_graph if step == "sources" else build_answers_graph
        return build(services).invoke(inputs)

    return run


@pytest.fixture(scope="session")
def practice(tmp_path_factory):
    """A practice Step 1, 2 and 3 for the Parastatal category (sample cities, scripted AI).

    Returns (the practice scoring folder, the settings the run used, the run)."""
    import time

    from asics_agent.config import get_settings
    from asics_agent.plan import PlanRun
    from asics_agent.practice import practice_services

    tmp = tmp_path_factory.mktemp("step3")
    base = dataclasses.replace(
        get_settings(), outputs_dir=tmp, outputs_root=None, scoring_dir=tmp / "scoring"
    )
    plan = PlanRun(
        base,
        ["parastatal"],
        {"sample_city_a": "Sample City A"},
        [1, 2, 3],
        practice=True,
        services_for=lambda vs: practice_services(vs),
        review_parastatals=False,
        pause_after_sources=False,
    ).start()
    end = time.time() + 180
    while plan.status not in {"finished", "failed"} and time.time() < end:
        time.sleep(0.2)
    assert plan.status == "finished", plan.error
    return tmp / "scoring" / "practice", base, plan
