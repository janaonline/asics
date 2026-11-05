"""People's files against the AI's, as the Scores page and the compare workbook show them."""

import dataclasses
import json

import pytest
from openpyxl import load_workbook

from asics_agent.categories import category_settings
from asics_agent.scoring import compare_run, human_merge, submissions
from asics_agent.scoring import template_fill as fill
from asics_agent.scoring.recalc import soffice
from tests.refdata import reference_templates

needs_calc = pytest.mark.skipif(soffice() is None, reason="LibreOffice is not installed")
CITY, UNIT = "Sample City A", "SWB"


def _template(section):
    return next(p for p in reference_templates() if f"_{section}_" in p.name)


@pytest.fixture(scope="module")
def view_settings(practice):
    """Settings that see the practice run's files, plus one people's file made for the sample city."""
    folder, base, _ = practice
    vs = category_settings(base, "parastatal")
    outputs = vs.outputs_dir / "practice"
    vs = dataclasses.replace(
        vs,
        outputs_dir=outputs,
        city_register=outputs / "practice_register.xlsx",
        scoring_dir=folder,
    )
    filled = vs.scoring_dir / "UPD filled by Asha.xlsx"
    ai = fill.AITemplate(filled, _template("UPD"))
    ai.ensure_unit(CITY, UNIT, "Water Supply Entity")
    spec = ai.specs["UPD 1a"]
    ai.write(
        "UPD 1a",
        ai.ensure_row("UPD 1a", CITY, UNIT),
        {
            spec.score_column: 3,
            spec.column_for("source_link"): "https://www.example.gov.in/act/",
            spec.column_for("chapter"): "II",
        },
    )
    spec_b = ai.specs["UPD 1b"]
    ai.write("UPD 1b", ai.ensure_row("UPD 1b", CITY, UNIT), {spec_b.score_column: 2})
    ai.save(vs.scoring_dir / ".cache")
    # a person's file reaches the page the way the team's files do: uploaded, stored, merged
    data = filled.read_bytes()
    preview = submissions.preview_file(vs, "UPD", filled.name, data)
    if preview.can_save:  # (a second run of this module finds it stored already)
        submissions.save_submission(vs, preview, data, "Asha")
    human_merge.merge_category(vs)
    return vs


@needs_calc
def test_the_compare_view_has_every_status_and_the_evidence(view_settings):
    view = compare_run.load_view(view_settings, CITY)
    rows = {(r.unit, r.code): r for r in view.comparison.rows}
    both = rows[(UNIT, "UPD 1a")]
    assert both.status == "both" and both.human_score == 3 and both.ai_score == 5
    assert both.difference == 2 and both.agrees == "No"
    assert both.ai_citation_id and both.ai_quote and both.ai_step3_link  # the AI's evidence
    assert both.human_source and both.human_location == "chapter II"  # the person's
    assert both.scorer == "Asha"  # typed when it was uploaded
    assert rows[(UNIT, "UPD 1b")].status == "both"
    only_ai = [r for r in view.comparison.rows if r.status == "only AI"]
    assert only_ai  # the other sample parastatal, scored by the AI alone
    assert all(r.human_score is None and r.ai_score is not None for r in only_ai)
    assert any(r.status == "neither" for r in view.comparison.rows)


@needs_calc
def test_the_consolidated_view_has_people_ai_and_the_difference(view_settings):
    view = compare_run.load_view(view_settings, CITY)
    assert set(view.tables) == {"People", "AI", "Difference"}
    for views in view.tables.values():
        assert set(views) == {"City systems", "Parastatals", "Questions"}
    people = {tuple(r[:3]): r for r in view.tables["People"]["Parastatals"].rows}
    ai = {tuple(r[:3]): r for r in view.tables["AI"]["Parastatals"].rows}
    diff = {tuple(r[:3]): r for r in view.tables["Difference"]["Parastatals"].rows}
    key = next(k for k in people if k[0] == CITY and k[1] == UNIT)
    headers = view.tables["AI"]["Parastatals"].headers
    scored = headers.index("UPD scored")
    assert people[key][scored] == 5  # UPD 1 = 1a + 1b = 3 + 2 (people)
    assert ai[key][scored] == 10  # the AI: 5 + 5
    assert diff[key][scored] == 5  # AI minus people
    questions = view.tables["Difference"]["Questions"]
    label = f"{CITY} – {UNIT}"
    column = questions.headers.index(label)
    row = next(r for r in questions.rows if r[1] == "UPD 1a")
    assert row[column] == 2  # the same difference, question by question


@needs_calc
def test_the_compare_workbook_agrees_with_the_page(view_settings):
    view = compare_run.load_view(view_settings, CITY)
    path = compare_run.comparison_workbook(view_settings, view)
    wb = load_workbook(path)
    assert "People - City systems" in wb.sheetnames and "Difference - Questions" in wb.sheetnames
    sheet = wb["Compare"]
    header = [c.value for c in sheet[1]]
    statuses = [r[header.index("Status")] for r in sheet.iter_rows(min_row=2, values_only=True)]
    for status in set(statuses):
        assert statuses.count(status) == sum(r.status == status for r in view.comparison.rows)
    assert len(statuses) == len(view.comparison.rows)
    summary = " ".join(
        str(c.value) for row in wb["Summary"].iter_rows() for c in row if c.value is not None
    )
    assert "fewer than 20" in summary  # no percentage from a handful of rows


@needs_calc
def test_notes_say_when_the_files_and_the_bank_differ(view_settings):
    view = compare_run.load_view(view_settings, CITY)
    text = " ".join(view.notes)
    assert "don't record which question bank" not in text  # the merged file says
    merged = human_merge.merged_files(view_settings)[0]
    info = human_merge.read_merge_info(merged)
    try:
        human_merge.info_path(merged).write_text(
            json.dumps({**info, "bank_version": "an-older-bank@2020-01-01#abcd1234"})
        )
        assert any(
            "People's file" in n and "an-older-bank" in n
            for n in compare_run.load_view(view_settings, CITY).notes
        )
    finally:
        human_merge.info_path(merged).write_text(json.dumps(info))
    path = compare_run.ai_files(view_settings)[0]
    original = fill.read_info(path)
    try:
        fill.write_info(
            path,
            {
                **original,
                "bank_version": {
                    "version": "an-older-bank@2020-01-01#abcd1234",
                    "content_hash": "0",
                },
            },
        )
        newer = compare_run.load_view(view_settings, CITY)
        assert any("an-older-bank" in n for n in newer.notes)
    finally:
        fill.write_info(path, original)  # the practice folder is shared by the tests of this module


def test_a_file_without_calculated_scores_is_read_through_a_temporary_copy(tmp_path):
    """A template saved by a tool that doesn't calculate: never changed, read via a copy."""
    from asics_agent.scoring import consolidated as cons

    template = _template("DPG")  # this one holds no calculated values
    before = template.read_bytes()
    section = cons.read_section(template, tmp_path)
    assert section.section == "DPG" and section.questions
    assert template.read_bytes() == before
    if soffice() is not None:
        assert section.calculated and any("temporary copy" in n for n in section.notes)
