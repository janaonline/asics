from asics_agent.applicability import applies_to
from asics_agent.config import get_settings
from asics_agent.models import Parastatal
from asics_agent.question_bank import load_question_bank


def bank():
    return load_question_bank(get_settings().question_bank)


def test_loads_all_questions_and_normalises_ids():
    questions, issues = bank()
    assert len(questions) == 55
    assert {"DPG 2b", "DPG 5a", "DPG 5d", "SC 7b"} <= set(questions)
    assert questions["DPG 5d"].raw_id == "DPG d"
    assert any("has no number" in i.message and i.audience == "team" for i in issues)


def test_builds_mq_sq_hierarchy():
    questions, _ = bank()
    assert questions["UPD 1"].children == ["UPD 1a", "UPD 1b"]
    assert questions["UPD 1b"].parent_id == "UPD 1"
    assert len(questions["DPG 5"].children) == 10
    assert not questions["DPG 4"].is_rollup


def test_applicability_by_parastatal_type():
    questions, _ = bank()
    water = Parastatal(id="W", name="Water", type="water_supply_board")
    da = Parastatal(id="D", name="DA", type="development_authority")
    assert applies_to(questions["UPD 2a"], water) and not applies_to(questions["UPD 2c"], water)
    assert not applies_to(questions["DPG 7a"], da)
    assert applies_to(questions["SC 1"], da) is False  # not revenue-raising by default
