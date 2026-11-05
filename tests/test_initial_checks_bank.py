from asics_agent.agents.initial_checks import build_initial_checks


def test_checks_confirm_assumptions_and_do_not_treat_unscored_questions_as_errors(services):
    out = build_initial_checks(services, step="sources").invoke({"city": "sample_city_a"})
    team = [i for i in out["issues"] if i.audience == "team"]
    assert any(i.message.startswith("CONFIRM") and "UPD 3b" in i.message for i in team)
    unscored = [q for q in out["questions"].values() if q.max_score is None]
    assert unscored
    for q in unscored:  # e.g. a question the source does not score
        mine = [i for i in out["issues"] if i.ref == q.id and "maximum score" in i.message]
        assert mine and all(i.severity == "info" for i in mine)
    assert not [i for i in out["issues"] if i.severity == "error"]
    assert any("Question bank version" in i.message for i in out["issues"])
