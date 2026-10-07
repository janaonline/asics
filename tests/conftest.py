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

    return practice_services(dataclasses.replace(get_settings(), outputs_dir=tmp_path))


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
