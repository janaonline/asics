import yaml

from asics_agent import applicability as ap
from asics_agent.models import Parastatal, Question
from asics_agent.parastatal_types import PARASTATAL_TYPES, ULG_TYPE
from tests.refdata import expected_questions, template_index


def q(code, text):
    return Question(
        id=code,
        raw_id=code,
        row=1,
        pillar=code.split()[0],
        pillar_name="",
        text="t",
        tag="SQ",
        applicability=text,
    )


def unit(kind, **flags):
    return Parastatal(id="X", name="X", type=kind, **flags)


def test_old_and_new_phrases_give_the_same_answer():
    water, bus, da = (
        unit("water_supply_entity"),
        unit("public_bus_transport_operator"),
        unit("development_authority"),
    )
    for text in ("Water supply entity", "Water supply board"):
        assert ap.applies_to(q("UPD 9", text), water) and not ap.applies_to(q("UPD 9", text), bus)
    for text in ("Public bus transport operator", "Transport Corporation"):
        assert ap.applies_to(q("UPD 9", text), bus) and not ap.applies_to(q("UPD 9", text), water)
    excl = q("UPD 9", "All parastatals excluding Development Authorities")
    assert not ap.applies_to(excl, da) and ap.applies_to(excl, water)
    assert ap.applies_to(q("UPD 9", "Development authorities only"), da)


def test_flags_decide_the_conditional_questions():
    rules = [
        ("Revenue-raising parastatals only ", "revenue_raising"),
        (
            "Parastatals with an infrastructure-delivery/capital-expenditure mandate. ",
            "capex_mandate",
        ),
        ("Common — all parastatal types with an annual budget.", "has_annual_budget"),
        (
            "Common — all parastatal types with a designated chief executive/executive authority post.",
            "has_chief_executive",
        ),
    ]
    for text, flag in rules:
        on = unit("other", **{flag: True})
        off = unit("other", **{flag: False})
        assert ap.applies_to(q("SC 1", text), on) is True
        assert ap.applies_to(q("SC 1", text), off) is False
    assert ap.applies_to(q("SC 4", "Common."), unit("other")) is True


def test_unrecognised_wording_is_reported_not_guessed():
    assert ap.applies_to(q("UPD 9", "Only airports"), unit("other")) is None
    assert ap.match_rule("Only airports") is None


def test_first_match_wins_and_a_bad_rule_is_reported(tmp_path):
    data = yaml.safe_load(
        """
rules:
  - {phrase: special, rule: type_is, value: other}
  - {phrase: special things, rule: common}
  - {phrase: broken, rule: type_is, value: no_such_type}
  - {phrase: also broken, rule: nonsense}
"""
    )
    rules = ap.parse_rules(data)
    assert len(rules.rules) == 2 and len(rules.problems) == 2
    assert ap.match_rule("special things", rules=rules).kind == "type_is"


def test_a_type_added_to_the_rules_file_is_one_edit(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text("rules:\n  - {phrase: rail operator, rule: type_is, value: other}\n")
    rules = ap.load_rules(path)
    assert not rules.problems
    assert ap.applies_to(q("UPD 9", "Rail operator"), unit("other"), rules)


def test_the_override_is_for_parastatals_only_and_is_shown_for_confirmation():
    expected = expected_questions()
    assert "UPD 3b" in expected
    question = q("UPD 3b", expected["UPD 3b"]["applicability"])
    assert ap.applies_to(question, unit("water_supply_entity")) is True
    assert ap.applies_to(question, unit("public_bus_transport_operator")) is False
    assert ap.applies_to(question, unit(ULG_TYPE)) is True  # the ULG has its own UPD 3b
    notes = ap.override_notes({"UPD 3b": question})
    assert notes and "confirm" in notes[0][1].lower()


def test_rules_against_the_templates_question_index():
    """The only differences from the templates' Question_Index (columns J-L) are the questions
    the four Yes/No flags decide: the templates mark them applicable to every type."""
    expected = expected_questions()
    labels = {t.label: t.code for t in PARASTATAL_TYPES}
    questions = {c: q(c, w["applicability"]) for c, w in expected.items()}
    flagged = {
        c
        for c, question in questions.items()
        if (r := ap.match_rule(question.applicability, c)) and r.kind == "flag"
    }
    assert flagged, "the reference workbook has flag-decided questions today"
    for file, index in template_index().items():
        for code, by_label in index.items():
            if code not in questions:
                continue
            for label, template_says in by_label.items():
                person = unit(labels[label])
                ours = ap.applies_to(questions[code], person)
                if code in flagged:
                    continue  # decided by the register's flags, not by type
                assert ours == (template_says == "Y"), (file, code, label)
