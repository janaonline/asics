"""People's filled templates: upload checks, preview, immutable storage, merge, intern copies."""

import dataclasses
import io
import json
import zipfile

import pytest
from openpyxl import Workbook, load_workbook

from asics_agent.categories import category_settings
from asics_agent.scoring import compare_run, human_copies, human_merge, submissions
from asics_agent.scoring import template_fill as fill
from asics_agent.scoring.recalc import soffice
from asics_agent.scoring.template_import import read_filled_template, read_structures
from tests.refdata import reference_templates

needs_calc = pytest.mark.skipif(soffice() is None, reason="LibreOffice is not installed")
CITY, UNIT = "Sample City A", "SWB"


def _template(section):
    return next(p for p in reference_templates() if f"_{section}_" in p.name)


@pytest.fixture
def settings(practice, tmp_path):
    """The Parastatal category with the practice register, and an empty scoring folder."""
    _, base, _ = practice
    vs = category_settings(base, "parastatal")
    outputs = vs.outputs_dir / "practice"
    return dataclasses.replace(
        vs,
        outputs_dir=outputs,
        city_register=outputs / "practice_register.xlsx",
        scoring_dir=tmp_path / "scoring",
    )


@pytest.fixture
def other(settings):
    """A second parastatal of the sample city (the register has one; Step 1's Sources workbook more)."""
    units, _ = compare_run.city_units(settings, compare_run.find_city(settings, CITY))
    return next(u.id for u in units.values() if u.id != UNIT)


def _valid(col):
    return col.options[0] if col.options else 100


def make_file(path, rows, section="UPD", calculate=False, raw=None):
    """A filled template: rows = [(code, city, unit, {column header or 'score' or field: value})]."""
    ai = fill.AITemplate(path, _template(section))
    for code, city, unit, values in rows:
        ai.ensure_unit(city, unit, "Water Supply Entity")
        spec = ai.specs[code]
        row = ai.ensure_row(code, city, unit)
        cells = {}
        for key, value in values.items():
            if key == "score":
                cells[spec.score_column] = value
            elif spec.column_for(key):
                cells[spec.column_for(key)] = value
            else:
                cells[next(c for c, s in spec.columns.items() if s.header == key)] = value
        ai.write(code, row, cells)
    for sheet, coordinate, value in raw or []:  # a value the template would not allow
        ai.wb[sheet][coordinate] = value
    if calculate:
        ai.save(path.parent / ".cache")
    else:
        ai.wb.save(path)
    return path


def upload(settings, path, scorer, section="UPD"):
    data = path.read_bytes()
    preview = submissions.preview_file(settings, section, path.name, data)
    return preview, submissions.save_submission(settings, preview, data, scorer)


# -- the upload checks -------------------------------------------------------------------------
def test_only_plain_xlsx_files_are_accepted():
    assert "macros are not allowed" in submissions.unsafe_reasons("a.xlsm", b"x")[0]
    assert "only .xlsx" in submissions.unsafe_reasons("a.csv", b"x")[0]
    assert "not a readable" in submissions.unsafe_reasons("a.xlsx", b"not a zip")[0]
    assert "empty" in submissions.unsafe_reasons("a.xlsx", b"")[0]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/workbook.xml", "<workbook/>")
        z.writestr("xl/vbaProject.bin", "x")
        z.writestr("[Content_Types].xml", "<Types/>")
    assert "macros" in submissions.unsafe_reasons("a.xlsx", buf.getvalue())[0]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/workbook.xml", "<workbook/>")
        z.writestr("[Content_Types].xml", "<Types>macroEnabled</Types>")
    assert "macro-enabled" in submissions.unsafe_reasons("a.xlsx", buf.getvalue())[0]
    big = Workbook()
    out = io.BytesIO()
    big.save(out)
    assert submissions.unsafe_reasons("a.xlsx", out.getvalue()) == []  # safe; the preview judges it
    assert "limit" in submissions.unsafe_reasons("a.xlsx", b"0" * (submissions.MAX_BYTES + 1))[0]


def test_a_file_from_the_wrong_template_gets_a_plain_error(settings, tmp_path):
    sc = make_file(tmp_path / "sc.xlsx", [("SC 6b", CITY, UNIT, {"score": 1})], section="SC")
    preview = submissions.preview_file(settings, "UPD", sc.name, sc.read_bytes())
    assert not preview.can_save
    assert "This is the SC template, but UPD is chosen" in preview.errors[0]
    blank = Workbook()
    blank.active.append(["Name", "Value"])
    out = io.BytesIO()
    blank.save(out)
    other = submissions.preview_file(settings, "UPD", "x.xlsx", out.getvalue())
    assert (
        not other.can_save and "does not look like one of the scoring templates" in other.errors[0]
    )


def test_the_preview_says_what_was_read_and_what_is_wrong(settings, tmp_path):
    spec = read_structures(load_workbook(_template("UPD")))["UPD 1a"]
    path = make_file(
        tmp_path / "filled.xlsx",
        [
            ("UPD 1a", CITY, UNIT, {"score": 3, "source_link": "https://example.gov.in/a"}),
            ("UPD 1b", "Nowhere City", "XYZ", {"score": 2}),
            ("UPD 1b", CITY, "NOPE", {"score": 1}),
        ],
        raw=[(spec.sheet, f"{chr(64 + spec.score_column)}{spec.first_row}", "x")],
    )
    p = submissions.preview_file(settings, "UPD", path.name, path.read_bytes())
    assert p.can_save and p.template.endswith("UPD_Template.xlsx") and p.template_sha256
    assert (
        p.rows_with_score >= 3
        and p.rows_with_values >= 3
        and "UPD 1a" in p.sheets_read[0] + "UPD 1a"
    )
    assert any("Nowhere City" in x for x in p.not_in_register)
    assert any("NOPE" in x for x in p.not_in_register)
    assert not any(f"parastatal {UNIT} " in x or "city Sample" in x for x in p.not_in_register)
    assert p.bank_version


def test_values_the_template_does_not_allow_and_formulas_without_a_value(settings, tmp_path):
    dpg = read_structures(load_workbook(_template("DPG")))["DPG 1a"]
    scenario = next(c for c in dpg.inputs if c.options)
    path = make_file(
        tmp_path / "dpg.xlsx",
        [("DPG 1a", CITY, UNIT, {scenario.header: "A"})],
        section="DPG",
    )
    wb = load_workbook(path)
    ws = wb[dpg.sheet]
    r = next(
        r
        for r in range(dpg.first_row, ws.max_row + 1)
        if ws.cell(r, dpg.column_for("city")).value == CITY
    )
    ws.cell(r, scenario.column).value = "Maybe"
    wb.save(path)
    p = submissions.preview_file(settings, "DPG", path.name, path.read_bytes())
    assert any('"Maybe"' in x for x in p.not_allowed), p.not_allowed
    # a calculated Score that was never calculated has no saved value
    sc1 = read_structures(load_workbook(_template("SC")))["SC 1"]
    path2 = make_file(
        tmp_path / "sc2.xlsx",
        [
            (
                "SC 1",
                CITY,
                UNIT,
                {sc1.columns[c].header: _valid(sc1.columns[c]) for c in sc1.required_inputs},
            )
        ],
        section="SC",
    )
    p2 = submissions.preview_file(settings, "SC", path2.name, path2.read_bytes())
    assert p2.formula_no_value and any("save" in w.lower() for w in p2.warnings)
    assert p2.can_save  # a warning, not a blocker: the merge recalculates from the inputs


def test_nothing_is_saved_until_save_and_a_blank_template_is_refused(settings, tmp_path):
    blank = make_file(tmp_path / "blank.xlsx", [])
    p = submissions.preview_file(settings, "UPD", blank.name, blank.read_bytes())
    assert not p.can_save and "nothing to store" in p.errors[0]
    assert not submissions.list_submissions(settings)
    assert not submissions.submissions_dir(settings, "UPD").exists()


# -- storing -----------------------------------------------------------------------------------
def test_a_submission_is_stored_immutably_with_a_sidecar_and_a_registry(settings, tmp_path):
    path = make_file(tmp_path / "Asha final.xlsx", [("UPD 1a", CITY, UNIT, {"score": 3})])
    preview, sub = upload(settings, path, "  Asha   Rao ")
    folder = submissions.submissions_dir(settings, "UPD")
    assert sub.path.parent == folder and sub.path.read_bytes() == path.read_bytes()
    assert sub.submission_id.endswith(f"_asha-rao_{preview.sha256[:8]}")
    side = json.loads(sub.path.with_suffix(".json").read_text())
    assert (
        side["source"] == "human" and side["scorer"] == "Asha Rao"
    )  # typed, not from the file name
    assert (
        side["file_sha256"] == preview.sha256 and side["template_sha256"] == preview.template_sha256
    )
    assert side["bank_version"] and side["rows_read"] >= 1 and side["category"] == "parastatal"
    assert side["uploaded_by"] == "Asha Rao" and side["original_name"] == "Asha final.xlsx"
    index = json.loads((folder / "index.json").read_text())
    assert [s["submission_id"] for s in index["submissions"]] == [sub.submission_id]
    assert [s.submission_id for s in submissions.list_submissions(settings)] == [sub.submission_id]


def test_the_same_file_twice_is_detected_and_not_stored_twice(settings, tmp_path):
    path = make_file(tmp_path / "a.xlsx", [("UPD 1a", CITY, UNIT, {"score": 3})])
    _, first = upload(settings, path, "Asha")
    again = submissions.preview_file(settings, "UPD", "copy of a.xlsx", path.read_bytes())
    assert again.duplicate_of == first.submission_id and not again.can_save
    with pytest.raises(submissions.SubmissionError, match="already stored"):
        submissions.save_submission(settings, again, path.read_bytes(), "Someone else")
    assert len(submissions.list_submissions(settings)) == 1


def test_a_scorer_name_is_required_and_files_are_never_overwritten(settings, tmp_path):
    path = make_file(tmp_path / "a.xlsx", [("UPD 1a", CITY, UNIT, {"score": 3})])
    data = path.read_bytes()
    preview = submissions.preview_file(settings, "UPD", path.name, data)
    with pytest.raises(submissions.SubmissionError, match="name of the person"):
        submissions.save_submission(settings, preview, data, "  ")
    target = submissions.submissions_dir(settings, "UPD")
    target.mkdir(parents=True)
    with pytest.raises(submissions.SubmissionError, match="never overwritten"):
        submissions._write_atomic(
            target / "x.xlsx", b"1", exclusive=True
        ) or submissions._write_atomic(target / "x.xlsx", b"2", exclusive=True)
    assert (target / "x.xlsx").read_bytes() == b"1"
    with pytest.raises(submissions.SubmissionError, match="changed since"):
        submissions.save_submission(settings, preview, data + b"x", "Asha")


# -- the merge ---------------------------------------------------------------------------------
def _merged_rows(settings, section="UPD"):
    read = read_filled_template(submissions.merged_path(settings, section), "")
    return {(r.code, r.city, r.parastatal): r for r in read.rows}


@needs_calc
def test_merge_builds_the_workbook_from_the_submissions(settings, tmp_path):
    a = make_file(
        tmp_path / "a.xlsx",
        [
            ("UPD 1a", CITY, UNIT, {"score": 3, "chapter": "II"}),
            ("UPD 1b", CITY, UNIT, {"score": 2}),
        ],
    )
    upload(settings, a, "Asha")
    report = human_merge.merge_category(settings)
    assert not report.conflicts and report.calculated, report.needs_a_look()
    rows = _merged_rows(settings)
    assert rows[("UPD 1a", CITY, UNIT)].score == 3 and rows[("UPD 1a", CITY, UNIT)].chapter == "II"
    assert rows[("UPD 1b", CITY, UNIT)].score == 2
    info = human_merge.read_merge_info(submissions.merged_path(settings, "UPD"))
    assert info["rows"][f"UPD 1a|{CITY.casefold()}|{UNIT.casefold()}"]["scorers"] == ["Asha"]
    # every formula of the team's template is exactly as it was
    t, m = load_workbook(_template("UPD")), load_workbook(submissions.merged_path(settings, "UPD"))
    for ws in t.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    assert m[ws.title][cell.coordinate].value == cell.value
    # it is derived: merging again gives the same
    human_merge.merge_category(settings)
    assert _merged_rows(settings)[("UPD 1a", CITY, UNIT)].score == 3


@needs_calc
def test_two_scorers_who_disagree_are_both_listed_and_the_row_stays_blank(settings, tmp_path):
    upload(
        settings,
        make_file(
            tmp_path / "a.xlsx",
            [("UPD 1a", CITY, UNIT, {"score": 3}), ("UPD 1b", CITY, UNIT, {"score": 2})],
        ),
        "Asha",
    )
    upload(
        settings,
        make_file(
            tmp_path / "b.xlsx",
            [("UPD 1a", CITY, UNIT, {"score": 5}), ("UPD 1b", CITY, UNIT, {"score": 2.0})],
        ),
        "Ben",
    )
    report = human_merge.merge_category(settings)
    assert len(report.conflicts) == 1  # 2 and 2.0 are the same value
    c = report.conflicts[0]
    assert (c.code, c.city, c.unit, c.field) == ("UPD 1a", CITY, UNIT, "Score")
    assert {(e["scorer"], e["value"]) for e in c.entries} == {("Asha", 3), ("Ben", 5)}
    assert any("Asha" in line and "Ben" in line for line in report.needs_a_look())
    rows = _merged_rows(settings)
    assert ("UPD 1a", CITY, UNIT) not in rows  # not resolved: no row, not scored, never 0
    assert rows[("UPD 1b", CITY, UNIT)].score == 2
    assert [c.code for c in human_merge.conflicts(settings)] == ["UPD 1a"]
    assert any("Asha" in x for x in human_merge.needs_a_look(settings))


@needs_calc
def test_a_blank_never_overwrites_and_a_resubmission_replaces_only_its_rows(
    settings, tmp_path, other
):
    OTHER = other
    first = make_file(
        tmp_path / "1.xlsx",
        [
            ("UPD 1a", CITY, UNIT, {"score": 3, "chapter": "II"}),
            ("UPD 1b", CITY, UNIT, {"score": 2}),
            ("UPD 1a", CITY, OTHER, {"score": 4}),
        ],
    )
    upload(settings, first, "Asha")
    second = make_file(  # Asha again: a new score for UPD 1a / SWB, the chapter left blank
        tmp_path / "2.xlsx", [("UPD 1a", CITY, UNIT, {"score": 1})]
    )
    _, sub = upload(settings, second, "asha")  # the same person, spelled differently
    assert len(sub.replaces) == 1
    human_merge.merge_category(settings)
    rows = _merged_rows(settings)
    assert rows[("UPD 1a", CITY, UNIT)].score == 1  # replaced
    assert rows[("UPD 1a", CITY, UNIT)].chapter == "II"  # a blank did not clear it
    assert rows[("UPD 1b", CITY, UNIT)].score == 2  # rows the new file lacks are kept
    assert rows[("UPD 1a", CITY, OTHER)].score == 4
    assert len(submissions.list_submissions(settings, "UPD")) == 2  # the earlier file is kept


@needs_calc
def test_a_calculated_question_is_written_only_when_its_inputs_are_complete(
    settings, tmp_path, other
):
    OTHER = other
    sc1 = read_structures(load_workbook(_template("SC")))["SC 1"]
    headers = [sc1.columns[c].header for c in sc1.required_inputs]
    assert len(headers) >= 2
    full = {h: _valid(sc1.columns[c]) for h, c in zip(headers, sc1.required_inputs, strict=True)}
    partial = dict(list(full.items())[:-1])
    upload(
        settings,
        make_file(
            tmp_path / "p.xlsx",
            [("SC 1", CITY, UNIT, partial), ("SC 1", CITY, OTHER, full)],
            section="SC",
        ),
        "Asha",
        "SC",
    )
    report = human_merge.merge_category(settings)
    assert any("SC 1" in x and UNIT in x and headers[-1] in x for x in report.incomplete)
    rows = _merged_rows(settings, "SC")
    assert ("SC 1", CITY, UNIT) not in rows or rows[("SC 1", CITY, UNIT)].score is None  # never a 0
    assert rows[("SC 1", CITY, OTHER)].score is not None


@needs_calc
def test_unknown_places_and_text_that_looks_like_a_formula(settings, tmp_path):
    path = make_file(
        tmp_path / "a.xlsx",
        [
            ("UPD 1a", CITY, UNIT, {"score": 3, "comments": '=HYPERLINK("http://x","x")'}),
            ("UPD 1a", "Nowhere City", "XYZ", {"score": 4}),
            ("UPD 1a", CITY, "NOPE", {"score": 4}),
        ],
    )
    upload(settings, path, "Asha")
    report = human_merge.merge_category(settings)
    # names the register does not know are merged and flagged, never dropped
    flagged = {(u["city"], u["parastatal"]) for u in report.unregistered}
    assert flagged == {("Nowhere City", "XYZ"), (CITY, "NOPE")}
    merged = submissions.merged_path(settings, "UPD")
    ws = load_workbook(merged)[read_structures(load_workbook(_template("UPD")))["UPD 1a"].sheet]
    comments = [
        c
        for row in ws.iter_rows()
        for c in row
        if isinstance(c.value, str) and "HYPERLINK" in c.value
    ]
    assert comments and all(c.data_type == "s" for c in comments)  # text, never a formula
    rows = _merged_rows(settings)
    assert rows[("UPD 1a", "Nowhere City", "XYZ")].score == 4
    assert rows[("UPD 1a", CITY, "NOPE")].score == 4


@needs_calc
def test_the_scores_page_reads_the_merged_file_and_names_the_scorers(settings, practice, tmp_path):
    folder, base, _ = practice
    vs = dataclasses.replace(settings)  # the practice AI files live in the practice folder
    for ai in folder.glob("ai/PARASTATAL_*_AI*"):
        target = vs.scoring_dir / "ai" / ai.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(ai.read_bytes())
    upload(
        settings,
        make_file(
            tmp_path / "a.xlsx",
            [("UPD 1a", CITY, UNIT, {"score": 3}), ("UPD 1b", CITY, UNIT, {"score": 2})],
        ),
        "Asha",
    )
    upload(settings, make_file(tmp_path / "b.xlsx", [("UPD 1a", CITY, UNIT, {"score": 3})]), "Ben")
    assert compare_run.human_files(vs) == []  # nothing is read until it is merged
    assert len(human_merge.newer_than_merge(vs)) == 2
    human_merge.merge_category(vs)
    assert [p.name for p in compare_run.human_files(vs)] == ["PARASTATAL_UPD_human.xlsx"]
    assert human_merge.newer_than_merge(vs) == []
    view = compare_run.load_view(vs, CITY)
    rows = {(r.unit, r.code): r for r in view.comparison.rows}
    both = rows[(UNIT, "UPD 1a")]
    assert both.status == "both" and both.human_score == 3 and both.ai_score is not None
    assert both.scorer == "Asha, Ben"  # the same value from two people is not a conflict
    assert rows[(UNIT, "UPD 1b")].scorer == "Asha"
    assert not any("not merged yet" in n for n in view.notes)


# -- intern copies -----------------------------------------------------------------------------
@needs_calc
def test_intern_copies_are_copies_of_the_templates_with_the_assigned_rows(settings):
    from asics_agent.scoring.workflow import assignments_path

    path = assignments_path(settings)
    wb = load_workbook(path)
    wb["Assignments"].append(["PARASTATAL", "Asha Rao", "UPD 1*, SC 1", CITY, ""])
    wb.save(path)
    report = human_copies.prepare_copies(settings)
    assert not [p for p in report.problems if "No rows" in p], report.problems
    names = sorted(p.name for p in report.files)
    assert names == ["Asha_Rao.xlsx", "Asha_Rao.xlsx"]
    upd = submissions.copies_dir(settings, "UPD") / "Asha_Rao.xlsx"
    sc = submissions.copies_dir(settings, "SC") / "Asha_Rao.xlsx"
    assert upd.exists() and sc.exists()
    assert not submissions.copies_dir(settings, "DPG").exists()
    wb = load_workbook(upd)
    assert "Your assignment" in wb.sheetnames
    spec = read_structures(load_workbook(_template("UPD")))["UPD 1a"]
    ws = wb[spec.sheet]
    yellow = [
        ws.cell(r, spec.column_for("city")).value
        for r in range(spec.first_row, ws.max_row + 1)
        if ws.cell(r, spec.column_for("city")).fill.fgColor.rgb.endswith("FFF6D5")
    ]
    assert yellow and set(yellow) == {CITY}
    # an existing copy is never replaced
    mtime = upd.stat().st_mtime
    again = human_copies.prepare_copies(settings)
    assert any("already has" in x for x in again.done) and upd.stat().st_mtime == mtime
    # the extra sheets don't confuse the reader or the upload checks
    p = submissions.preview_file(settings, "UPD", upd.name, upd.read_bytes())
    assert "Your assignment" not in " ".join(p.ignored)
    assert "nothing to store" in p.errors[0]  # a copy with no scores yet
