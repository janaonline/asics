"""Old files that name retired or reused question codes still open, with a plain note."""

from pathlib import Path

import pytest

from asics_agent.bank_status import CHANGED, NOT_IN_BANK, RETIRED, archived_banks, build_context
from asics_agent.config import get_settings
from asics_agent.question_bank import load_question_bank


@pytest.fixture(scope="module")
def ctx():
    settings = get_settings()
    bank, _ = load_question_bank(settings.question_bank)
    if not list(archived_banks(settings.question_bank)):
        pytest.skip("no archived bank to compare with")
    return build_context(bank, settings.question_bank), settings


def test_retired_questions_are_flagged_not_errors(ctx):
    context, settings = ctx
    retired = [q for q in context.retired.values()]
    assert retired, "the archived bank has questions the current bank dropped"
    for q in retired:
        assert context.flag(q.raw_id, q.text) == RETIRED


def test_an_old_spelling_of_a_reused_code_is_flagged_as_changed(ctx):
    context, settings = ctx
    old = {}
    for _, questions in archived_banks(settings.question_bank):
        old.update({q.raw_id: q for q in questions.values()})
    reused = [
        q
        for raw, q in old.items()
        if raw not in context.raw_to_code
        and q.id in context.bank
        and q.text != context.bank[q.id].text
    ]
    assert reused
    changed = [q for q in reused if context.flag(q.raw_id, q.text) == CHANGED]
    assert changed  # e.g. an old "DPG d" now sits under a code that asks something else


def test_an_unknown_id_is_not_in_this_bank_version(ctx):
    context, _ = ctx
    assert context.flag("ZZZ 123") == NOT_IN_BANK
    assert context.flag("not a code") == NOT_IN_BANK


def test_every_saved_answers_file_opens(ctx):
    """The real old answers workbooks in outputs/ (if any) read without error."""
    from asics_agent.scoring.compare import read_step2

    context, _ = ctx
    files = sorted(
        Path(__file__).resolve().parents[1].glob("outputs/Parastatal/cities/*/answers/*/*.xlsx")
    )
    if not files:
        pytest.skip("no saved answers workbooks")
    for path in files:
        rows = read_step2(path, {})
        assert rows
        for (_, raw), row in rows.items():
            context.flag(raw, row.question)  # never raises
