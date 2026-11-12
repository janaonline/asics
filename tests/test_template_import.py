import warnings

from openpyxl import load_workbook

from asics_agent.scoring.template_import import read_filled_template
from tests.refdata import fill_template, reference_templates, template_index


def template(name):
    return next(p for p in reference_templates() if name in p.name)


def first_code_rows(path):
    """(sheet, parastatal short codes) of the first sheet of a template that has typed scoring."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = load_workbook(path)
    for ws in wb.worksheets:
        header = next((r for r in range(1, 40) if ws.cell(r, 1).value == "City"), None)
        cols = {ws.cell(header, c).value: c for c in range(1, ws.max_column + 1)} if header else {}
        if (
            header
            and "Score" in cols
            and not str(ws.cell(header + 1, cols["Score"]).value or "").startswith("=")
        ):
            return ws.title, [
                ws.cell(r, 2).value
                for r in range(header + 1, ws.max_row + 1)
                if ws.cell(r, 2).value
            ]
    raise AssertionError("no typed-score sheet")


def test_reads_every_question_sheet_by_name_and_skips_the_rest():
    for path in reference_templates():
        read = read_filled_template(path)
        index = template_index()[path.name]
        scored_sheets = {q.sheet for q in read.questions.values()}
        assert set(read.questions) <= set(index)  # every sheet read is a question of the index
        assert scored_sheets == set(read.report.sheets_read)
        skipped = {s for s, _ in read.report.sheets_skipped}
        assert {"Instructions", "Configuration", "Question_Index"} <= skipped
        assert not read.report.rows_skipped
        # an empty template has no scores: a blank score is "not scored", never 0
        assert all(r.score is None for r in read.rows)


def test_reads_typed_scores_sources_and_inputs(tmp_path):
    src = template("UPD")
    sheet, who = first_code_rows(src)
    filled = fill_template(
        src,
        tmp_path / "f.xlsx",
        {(sheet, who[0]): 3.5, (sheet, who[1]): 0},
        link={(sheet, who[0]): "https://example.gov.in/act"},
    )
    read = read_filled_template(filled, scorer="Asha")
    rows = {r.parastatal: r for r in read.rows if r.sheet == sheet}
    assert rows[who[0]].score == 3.5 and rows[who[0]].source_link == "https://example.gov.in/act"
    assert rows[who[1]].score == 0.0  # a real zero is kept
    assert rows[who[0]].scorer == "Asha" and rows[who[0]].code == sheet
    assert rows[who[0]].max_score and rows[who[0]].city


def test_renamed_and_shuffled_columns_still_read(tmp_path):
    src = template("UPD")
    sheet, who = first_code_rows(src)
    plain = read_filled_template(fill_template(src, tmp_path / "a.xlsx", {(sheet, who[0]): 4}))
    odd = fill_template(
        src,
        tmp_path / "b.xlsx",
        {(sheet, who[0]): 4},
        rename={
            "Score": "Points (Auto-generate)",
            "Scorer Comments (Why the score was given)": "SCORER COMMENTS",
        },
        shuffle=True,
    )
    read = read_filled_template(odd)
    a = next(r for r in plain.rows if r.sheet == sheet and r.parastatal == who[0])
    b = next(r for r in read.rows if r.sheet == sheet and r.parastatal == who[0])
    assert (b.score, b.city, b.parastatal, b.max_score) == (
        a.score,
        a.city,
        a.parastatal,
        a.max_score,
    )
    assert read.report.rows_read == plain.report.rows_read


def test_unknown_columns_are_kept_as_extra_inputs_and_reported(tmp_path):
    src = template("UPD")
    sheet, who = first_code_rows(src)
    filled = fill_template(
        src, tmp_path / "x.xlsx", {(sheet, who[0]): 2}, extra={"Reviewer Remark": "double-check"}
    )
    read = read_filled_template(filled)
    row = next(r for r in read.rows if r.sheet == sheet and r.parastatal == who[0])
    assert row.inputs["Reviewer Remark"] == "double-check"
    assert "Reviewer Remark" in read.report.unknown_columns[sheet]


def test_calculation_template_inputs_are_kept(tmp_path):
    src = template("SC")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = load_workbook(src)
    ws = wb["SC 11"]
    header = next(r for r in range(1, 40) if ws.cell(r, 1).value == "City")
    cols = {ws.cell(header, c).value: c for c in range(1, ws.max_column + 1)}
    inputs = [h for h in cols if h and "chief" in str(h).lower() and "Score" not in str(h)]
    assert inputs, "SC 11 has a chief-executive count input"
    ws.cell(header + 1, cols[inputs[0]], 2)
    wb.save(tmp_path / "sc.xlsx")
    row = next(r for r in read_filled_template(tmp_path / "sc.xlsx").rows if r.sheet == "SC 11")
    assert row.inputs[inputs[0]] == 2
    assert row.score is None and "no saved value" in row.score_note  # a formula, not stored as 0


def test_one_bad_sheet_never_stops_the_rest(tmp_path):
    src = template("UPD")
    sheet, who = first_code_rows(src)
    filled = fill_template(src, tmp_path / "f.xlsx", {(sheet, who[0]): 1})
    wb = load_workbook(filled)
    junk = wb.create_sheet("Odd notes")
    junk.append(["something", "else"])
    broken = wb.create_sheet("UPD 77z")  # looks like a question sheet, has no usable table
    broken.append(["Question Code", "UPD 77z"])
    wb.save(filled)
    read = read_filled_template(filled)
    skipped = dict(read.report.sheets_skipped)
    assert "Odd notes" in skipped and "UPD 77z" in skipped
    assert any(r.sheet == sheet and r.score == 1.0 for r in read.rows)


def test_a_duplicate_city_parastatal_row_uses_only_the_first(tmp_path):
    src = template("UPD")
    sheet, who = first_code_rows(src)
    filled = fill_template(src, tmp_path / "f.xlsx", {(sheet, who[0]): 1})
    wb = load_workbook(filled)
    ws = wb[sheet]
    header = next(r for r in range(1, 40) if ws.cell(r, 1).value == "City")
    cols = {ws.cell(header, c).value: c for c in range(1, ws.max_column + 1)}
    last = max(r for r in range(header, ws.max_row + 1) if ws.cell(r, 1).value) + 1
    ws.cell(last, 1, ws.cell(header + 1, 1).value)
    ws.cell(last, 2, who[0])
    ws.cell(last, cols["Score"], 9)
    wb.save(filled)
    read = read_filled_template(filled)
    assert [r for r in read.report.rows_skipped if r[0] == sheet and "only the first" in r[2]]
    assert next(r for r in read.rows if r.sheet == sheet and r.parastatal == who[0]).score == 1.0
