"""One run across verticals, cities and steps (the app's Run steps page)."""

import dataclasses
import time

from asics_agent.config import get_settings
from asics_agent.plan import PlanRun
from asics_agent.practice import practice_services


def _plan(tmp_path, steps, **kwargs):
    base = dataclasses.replace(
        get_settings(), outputs_dir=tmp_path, outputs_root=None, scoring_dir=tmp_path / "scoring"
    )
    return PlanRun(
        base,
        ["parastatal", "upd"],
        {"sample_city_a": "Sample City A"},
        steps,
        practice=True,
        services_for=lambda vs: practice_services(vs),  # no pauses between practice steps
        **kwargs,
    )


def _wait(plan, until, timeout=120):
    end = time.time() + timeout
    while plan.status not in until and time.time() < end:
        time.sleep(0.2)
    return plan.status


def test_all_verticals_run_steps_1_2_3_in_order(tmp_path):
    plan = _plan(tmp_path, [1, 2, 3], review_parastatals=False, pause_after_sources=False)
    assert [s.title for s in plan.stages] == [
        "Step 1 · Parastatal · Find sources",
        "Step 1 · UPD · Find sources",
        "Step 2 · Parastatal · Answer questions",
        "Step 2 · UPD · Answer questions",
        "Step 3 · Parastatal · Score",
        "Step 3 · UPD · Score",
    ]
    assert _wait(plan.start(), {"finished", "failed"}) == "finished", plan.error
    assert [s.status for s in plan.stages] == ["done"] * 6
    assert all("Scored Sample City A" in s.note for s in plan.stages[4:])
    # each vertical keeps its own folders
    assert any((tmp_path / "practice" / "cities").iterdir())  # Parastatal: outputs/
    assert any((tmp_path / "verticals" / "upd" / "practice" / "cities").iterdir())


def test_pauses_for_the_sources_review_before_answering(tmp_path):
    plan = _plan(tmp_path, [1, 2], review_parastatals=False, pause_after_sources=True).start()
    assert _wait(plan, {"waiting_for_sources", "finished", "failed"}) == "waiting_for_sources"
    assert [s.status for s in plan.stages] == ["done", "done", "waiting", "waiting"]
    plan.continue_after_review()
    assert _wait(plan, {"finished", "failed"}) == "finished", plan.error
    assert [s.status for s in plan.stages] == ["done"] * 4
