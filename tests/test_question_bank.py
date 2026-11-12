"""The question bank loads whatever the team's workbook holds; expectations come from
docs/reference/ at test time, never from counts or codes written here."""

import re
import shutil
import warnings

import pytest
from openpyxl import load_workbook

from asics_agent import bank_builder as bb
from asics_agent.bank_version import bank_version, content_hash
from asics_agent.config import get_settings
from asics_agent.question_bank import load_question_bank
from asics_agent.scoring.skeleton import check_questions
from tests.refdata import expected_questions, reference_workbook


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """The bank built from the reference workbook, loaded."""
    tmp = tmp_path_factory.mktemp("bank")
    report = bb.read_source(reference_workbook())
    path = bb.write_bank(report, tmp / "bank.xlsx")
    questions, issues = load_question_bank(path)
    return report, path, questions, issues


def test_every_question_loads_with_exact_text_tag_max_and_applicability(built):
    _, _, questions, _ = built
    expected = expected_questions()
    assert set(questions) == set(expected)
    for code, want in expected.items():
        q = questions[code]
        assert q.text == want["text"]
        assert q.raw_id == want["raw"]
        assert q.applicability == want["applicability"]
        assert q.methodology == want["methodology"]
        want_max = None if want["max"] in (None, "") else float(want["max"])
        assert q.max_score == want_max
        if want["tag"]:  # a blank tag in the source is worked out from the code
            assert q.tag == want["tag"]


def test_the_bank_file_in_the_repo_matches_the_reference_workbook():
    questions, _ = load_question_bank(get_settings().question_bank)
    expected = expected_questions()
    assert set(questions) == set(expected)
    assert all(questions[c].text == w["text"] for c, w in expected.items())


def test_standalone_questions_are_derived_from_the_codes(built):
    _, _, questions, _ = built
    codes = set(questions)
    for code, q in questions.items():
        has_children = any(re.fullmatch(rf"{re.escape(code)}[a-z]", c) for c in codes)
        assert q.is_rollup == (q.tag == "MQ" and has_children), code
        if q.tag == "SQ":
            assert q.parent_id in questions
        assert sorted(q.children) == sorted(
            c for c in codes if re.fullmatch(rf"{re.escape(code)}[a-z]", c)
        )


def test_per_parastatal_rows_are_not_questions(built):
    report, _, questions, _ = built
    assert sum(s.data_rows for s in report.sheets) > 0  # e.g. "DPG 3 - BDA", "SC 9a: BDA"
    assert not [c for c in questions if not re.fullmatch(r"[A-Z]+ \d+[a-z]?", c)]


def test_a_question_with_no_max_score_does_not_break_anything(built):
    _, _, questions, _ = built
    unscored = [q for q in questions.values() if q.max_score is None]
    assert unscored, "the reference workbook has a question with no max score today"
    problems = check_questions(questions)  # the scoring skeleton's checks do not crash
    assert any(unscored[0].raw_id in p for p in problems)


def test_versions_are_stable_and_change_with_the_content(built, tmp_path):
    report, _, questions, _ = built
    again = bb.write_bank(bb.read_source(reference_workbook()), tmp_path / "again.xlsx")
    q2, _ = load_question_bank(again)
    assert content_hash(q2) == content_hash(questions)
    first = next(iter(q2.values()))
    first.text += " (edited)"
    assert content_hash(q2) != content_hash(questions)
    assert bank_version(again, questions).version.endswith(content_hash(questions)[:8])


def _copy_with(tmp_path, edit):
    dst = tmp_path / "source.xlsx"
    shutil.copyfile(reference_workbook(), dst)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = load_workbook(dst)
    edit(wb)
    wb.save(dst)
    return dst


def test_a_bank_with_an_extra_question_and_an_extra_column_still_loads(tmp_path):
    def edit(wb):
        ws = wb["SC"]
        header = next(r for r in range(1, 10) if ws.cell(r, 1).value == "City-Systems Pillar")
        new_col = ws.max_column + 1
        ws.cell(header, new_col, "Pilot Remarks")
        row = ws.max_row + 1
        for name, value in {
            "City-Systems Pillar": "SC 99z",
            "Question": "A question added next week?",
            "Tag": "SQ",
            "Score / Max Score": 2,
            "Applicability": "Common.",
        }.items():
            col = next(c for c in range(1, ws.max_column + 1) if ws.cell(header, c).value == name)
            ws.cell(row, col, value)
        ws.cell(row, new_col, "remember this")
        extra = wb.create_sheet("ABC")  # a new section the builder was not told about
        extra.append(["City-Systems Pillar", "Question", "Tag"])
        extra.append(["ABC 1", "A question in a new section?", "MQ"])

    report = bb.read_source(_copy_with(tmp_path, edit))
    assert "SC 99z" in [r["code"] for _, _, rows in report.rows for r in rows]
    assert any("Pilot Remarks" in s.not_copied for s in report.sheets)  # reported, not dropped
    assert any("ABC" in n for n in report.not_understood)  # listed, not guessed
    path = bb.write_bank(report, tmp_path / "bank.xlsx")
    questions, issues = load_question_bank(path)
    assert "SC 99z" in questions and questions["SC 99z"].max_score == 2
    assert len(questions) == len(expected_questions()) + 1
    assert not [i for i in issues if i.severity == "error"]

    # a column the bank file itself gains later is kept on the question, not dropped
    wb = load_workbook(path)
    ws = wb["Question Bank"]
    ws.cell(1, ws.max_column + 1, "Reviewer")
    for r in range(2, ws.max_row + 1):
        ws.cell(r, ws.max_column, "ok")
    wb.save(path)
    questions, issues = load_question_bank(path)
    assert questions["SC 99z"].extra == {"Reviewer": "ok"}
    assert not [i for i in issues if i.severity == "error"]


def test_the_diff_reports_added_removed_text_max_and_applicability(built):
    _, _, questions, _ = built
    old = {k: v.model_copy(deep=True) for k, v in questions.items()}
    code = next(iter(old))
    old[code].text = "Something completely different entirely"
    other = list(old)[1]
    old[other].max_score = 99
    third = list(old)[2]
    old[third].applicability = "Water supply board"
    gone = old.pop(list(old)[3])
    extra = old[code].model_copy(update={"id": "ZZZ 1", "raw_id": "ZZZ 1"})
    old["ZZZ 1"] = extra
    d = bb.diff_banks(old, questions)
    assert gone.id in d.added and "ZZZ 1" in d.removed
    assert code in d.text_changed and code in d.different_question
    assert other in [c for c, *_ in d.max_changed]
    assert third in [c for c, *_ in d.applicability_changed]
