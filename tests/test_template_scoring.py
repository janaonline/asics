"""Step 3 in the team's templates: the AI fills a copy of each, the template calculates."""

import shutil
import warnings
from types import SimpleNamespace

import pytest
from openpyxl import load_workbook

from asics_agent.categories import category_settings
from asics_agent.config import get_settings
from asics_agent.models import Parastatal, Source
from asics_agent.scoring import consolidated as cons
from asics_agent.scoring import template_fill as fill
from asics_agent.scoring import template_scoring as ts
from asics_agent.scoring.ai import ScoreReply
from asics_agent.scoring.phase2 import CityEvidence, StepTwoAnswer
from asics_agent.scoring.recalc import soffice
from asics_agent.scoring.template_import import (
    read_filled_template,
    read_question_index,
    read_structures,
)
from tests.refdata import reference_templates

needs_calc = pytest.mark.skipif(soffice() is None, reason="LibreOffice is not installed")


def _load(path, **kw):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return load_workbook(path, **kw)


def _templates():
    return {p.name.split("_")[1]: p for p in reference_templates()}


@needs_calc
def test_step3_fills_a_copy_of_each_template(practice):
    ai_dir = practice[0] / "ai"
    files = sorted(ai_dir.glob("PARASTATAL_*_AI.xlsx"))
    assert [f.name for f in files] == [f"PARASTATAL_{s}_AI.xlsx" for s in ("DPG", "SC", "UPD")]
    for path in files:
        info = fill.read_info(path)
        assert info["scorer"] == "AI" and info["calculated"] is True
        assert info["model"] and info["agent_setup_fingerprint"] and info["bank_version"]
        assert info["template_sha256"] == fill.template_hash(_templates()[info["section"]])
        assert "Sample City A" in info["cities"]


@needs_calc
def test_nothing_but_inputs_evidence_and_comments_is_written(practice):
    """Every formula, header and other sheet is exactly as in the team's template."""
    ai_dir = practice[0] / "ai"
    for section, template in _templates().items():
        t, a = _load(template), _load(ai_dir / f"PARASTATAL_{section}_AI.xlsx")
        assert t.sheetnames == a.sheetnames
        for ws in t.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    value = cell.value
                    if isinstance(value, str) and value.startswith("="):
                        assert a[ws.title][cell.coordinate].value == value, (
                            ws.title,
                            cell.coordinate,
                        )
        specs = read_structures(t)
        for code, spec in specs.items():
            ws_t, ws_a = t[spec.sheet], a[spec.sheet]
            for r in range(1, spec.header_row + 1):  # the details and the headers
                for c in range(1, ws_t.max_column + 1):
                    assert ws_a.cell(r, c).value == ws_t.cell(r, c).value, (code, r, c)
            for r in range(spec.first_row, spec.last_row + 1):  # the team's own (Bengaluru) rows
                for c, col in spec.columns.items():
                    calculated_score = col.kind == "score" and spec.score_is_formula
                    if col.kind in ("identity", "check", "calculated") or calculated_score:
                        assert ws_a.cell(r, c).value == ws_t.cell(r, c).value, (code, r, c)
                    if col.kind in ("input", "evidence", "score") and not calculated_score:
                        assert ws_a.cell(r, c).value is None, (code, r, c)


@needs_calc
def test_the_structure_survives_and_the_dropdown_is_restored(practice):
    ai_dir = practice[0] / "ai"
    for section, template in _templates().items():
        before = fill.fingerprint(template)
        after = fill.fingerprint(ai_dir / f"PARASTATAL_{section}_AI.xlsx")
        for key in (
            "tables",
            "conditional_formats",
            "protected_sheets",
            "hidden_sheets",
            "sheet_names",
            "defined_names",
        ):
            assert after[key] == before[key], key
        assert after["validations"] >= before["validations"]  # the x14 drop-down is back
        assert after["formulas"] >= before["formulas"]


@needs_calc
def test_scores_calculate_and_reach_the_roll_up(practice):
    ai_dir = practice[0] / "ai"
    read = read_filled_template(ai_dir / "PARASTATAL_UPD_AI.xlsx", "AI")
    rows = [r for r in read.rows if r.city == "Sample City A" and r.code in ("UPD 1a", "UPD 1b")]
    assert rows and all(r.score is not None and 0 < r.score <= r.max_score for r in rows)
    assert all("Scored by AI" in r.additional_comments and r.source_link for r in rows)
    assert all('Quote: "' in r.comments for r in rows)
    section = cons.read_section(ai_dir / "PARASTATAL_UPD_AI.xlsx", practice[0] / ".cache")
    slot = next(s for s in section.slots if s.city == "Sample City A")
    assert slot.scores["UPD 1a"] == next(r.score for r in rows if r.code == "UPD 1a")
    assert slot.scores["UPD 1"] is not None  # the main question rolls up


@needs_calc
def test_the_team_templates_are_never_changed(practice):
    for section, template in _templates().items():
        info = fill.read_info(practice[0] / "ai" / f"PARASTATAL_{section}_AI.xlsx")
        assert fill.template_hash(template) == info["template_sha256"]


def test_a_new_city_gets_identical_configuration_in_every_file(tmp_path):
    ais = []
    for section, template in _templates().items():
        ai = fill.AITemplate(tmp_path / f"{section}.xlsx", template)
        assert ai.ensure_unit("Testville", "TWB", "Water Supply Entity") == []
        assert ai.ensure_unit("Testville", "TWB", "Water Supply Entity") == []  # idempotent
        ais.append(ai)
    configs = [[(c.city, c.parastatal, c.parastatal_type) for c in ai.config_rows()] for ai in ais]
    assert configs[0] == configs[1] == configs[2]
    assert ("Testville", "TWB", "Water Supply Entity") in configs[0]
    assert not any(c[0] == "Bengaluru" and c[1] == "TWB" for c in configs[0])


def test_a_type_without_a_question_index_column_is_reported(tmp_path):
    ai = fill.AITemplate(tmp_path / "u.xlsx", _templates()["UPD"])
    problems = ai.ensure_unit("Testville", "XYZ", "Metro Rail")
    assert problems and "no column" in problems[0]


def test_new_rows_are_added_to_the_table_and_other_rows_are_untouched(tmp_path):
    ai = fill.AITemplate(tmp_path / "s.xlsx", _templates()["SC"])
    spec = ai.specs["SC 11"]
    before = {k: v for k, v in ai._row_map("SC 11").items()}
    row = ai.ensure_row("SC 11", "Testville", "TWB")
    assert row == spec.last_row and ai.row_of("SC 11", "Testville", "TWB") == row
    ref = ai.wb[spec.sheet].tables[spec.table].ref
    assert ref.endswith(str(row))
    assert all(ai.row_of("SC 11", *key) == r for key, r in before.items())
    assert ai.ensure_row("SC 11", "Testville", "TWB") == row  # asking again adds nothing


def test_invalid_values_are_rejected_not_written(tmp_path):
    ai = fill.AITemplate(tmp_path / "d.xlsx", _templates()["DPG"])
    spec = ai.specs["DPG 1a"]
    row = ai.ensure_row("DPG 1a", "Testville", "TWB")
    scenario, acts = spec.inputs[0].column, spec.inputs[1].column
    result = ai.write("DPG 1a", row, {scenario: "Z", acts: "maybe"})
    assert result.written == 0 and len(result.rejected) == 2
    ok = ai.write("DPG 1a", row, {scenario: "b", acts: "yes"})
    assert ok.written == 2
    ws = ai.wb[spec.sheet]
    assert (ws.cell(row, scenario).value, ws.cell(row, acts).value) == ("B", "Yes")
    # a calculated Score and a formula are never writable
    assert ai.write("DPG 1a", row, {spec.score_column: 5}).written == 0
    sc = fill.AITemplate(tmp_path / "x.xlsx", _templates()["UPD"])
    s = sc.specs["UPD 1a"]
    r = sc.ensure_row("UPD 1a", "Testville", "TWB")
    assert sc.write("UPD 1a", r, {s.score_column: 99}).written == 0  # above the max
    assert sc.write("UPD 1a", r, {s.score_column: -1}).written == 0
    assert sc.write("UPD 1a", r, {s.score_column: 2.5}).written == 1
    dpg4 = fill.AITemplate(tmp_path / "y.xlsx", _templates()["DPG"])
    q4 = dpg4.specs["DPG 4"]
    assert q4.max_score is None
    assert (
        dpg4.write(
            "DPG 4", dpg4.ensure_row("DPG 4", "Testville", "TWB"), {q4.score_column: 3}
        ).written
        == 0
    )


@needs_calc
def test_formulas_calculate_the_score_from_the_inputs(tmp_path):
    """The calculated sheets give the team's own results (hand-calculated here)."""

    def scored(section, code, inputs_by_header_start, row_check=None):
        ai = fill.AITemplate(tmp_path / f"{section}.xlsx", _templates()[section])
        ai.ensure_unit("Testville", "TWB", "Water Supply Entity")
        spec = ai.specs[code]
        row = ai.ensure_row(code, "Testville", "TWB")
        values = {}
        for header, value in inputs_by_header_start.items():
            col = next(c for c in spec.inputs if c.header.startswith(header))
            values[col.column] = value
        assert ai.write(code, row, values).written == len(values)
        saved = ai.save(tmp_path / "profile")
        assert saved.calculated, saved.problems
        read = read_filled_template(saved.path)
        return next(r for r in read.rows if r.code == code and r.parastatal == "TWB")

    sc11 = scored("SC", "SC 11", {"Chief executives": 2})
    assert sc11.score == 5
    dpg2b = scored("DPG", "DPG 2b", {"Plans": "Yes", "Budgets": "Yes", "Annual": "No"})
    assert dpg2b.score == pytest.approx(3.34)
    dpg1a = scored("DPG", "DPG 1a", {"Devolution": "B", "Acts": "Yes"})
    assert dpg1a.score == 5


def test_required_inputs_are_found_from_the_formulas():
    for path in reference_templates():
        specs = read_structures(_load(path))
        for code, spec in specs.items():
            if spec.score_is_formula:
                assert spec.required_inputs, code
                assert all(spec.columns[c].kind == "input" for c in spec.required_inputs)
            if spec.needs_benchmark:  # needs other cities: the AI leaves these for a person
                assert code in ("SC 2", "SC 12a", "SC 12b")
    sc = read_structures(_load(_templates()["SC"]))
    assert len(sc["SC 11"].required_inputs) == 1  # the count; the names are optional
    assert (
        len(sc["SC 1"].required_inputs) == 9
    )  # own revenue, revenue and capital spending, 3 years


def test_the_templates_question_index_lists_the_types(tmp_path):
    for path in reference_templates():
        index, types = read_question_index(_load(path))
        assert index and set(types) >= {"development_authority", "water_supply_entity"}


def test_a_changed_template_rebuilds_the_file_and_carries_the_work_over(tmp_path):
    from asics_agent.scoring.template_scoring import carry_over

    template = tmp_path / "Parastatal_UPD_Template.xlsx"
    shutil.copyfile(_templates()["UPD"], template)
    path = tmp_path / "ai" / "PARASTATAL_UPD_AI.xlsx"
    path.parent.mkdir()
    ai, _ = fill.open_ai_template(path, template, carry_over=carry_over)
    ai.ensure_unit("Testville", "TWB", "Water Supply Entity")
    spec = ai.specs["UPD 1a"]
    ai.write("UPD 1a", ai.ensure_row("UPD 1a", "Testville", "TWB"), {spec.score_column: 4})
    saved = ai.save(tmp_path / "profile")
    fill.write_info(saved.path, {"template_sha256": fill.template_hash(template)})
    # the team edits the template
    wb = _load(template)
    wb["UPD 1a"]["B8"] = "A note the team added"
    wb.save(template)
    again, notes = fill.open_ai_template(path, template, carry_over=carry_over)
    assert any("changed" in n for n in notes) and any("Carried over 1" in n for n in notes)
    read = again.config_rows()
    assert any(c.parastatal == "TWB" for c in read)
    row = again.row_of("UPD 1a", "Testville", "TWB")
    assert again.wb["UPD 1a"].cell(row, spec.score_column).value == 4


# -- the scorer, one row at a time (the model is replaced by a fixed reply) -----------------------
SOURCE_TEXT = "Section 16. The Board shall prepare its plans in coordination with the ULG."


def _scorer(tmp_path, monkeypatch, section, code, reply, answer_question=None):
    ai = fill.AITemplate(tmp_path / f"{section}.xlsx", _templates()[section])
    spec = ai.specs[code]
    page = tmp_path / "source.txt"
    page.write_text(SOURCE_TEXT)
    unit = Parastatal(id="TWB", name="Test Water Board", type="water_supply_entity")
    source = Source(
        citation_id="TWB-01",
        parastatal_id="TWB",
        title="The Act",
        url="https://x.gov.in/act",
        content_path=str(page),
    )
    answer = StepTwoAnswer(
        status="Answered — Verified Source",
        answer="Yes",
        citation_id="TWB-01",
        evidence="shall prepare",
        notes="",
        source_needed="",
        question=answer_question if answer_question is not None else spec.question,
        answer_class="A1",
        confidence="High",
    )
    evidence = CityEvidence(
        parastatals={"TWB": unit},
        citations=[source],
        answers={("TWB", code.replace(" ", "")): answer},
    )
    monkeypatch.setattr(ts, "call_json", lambda *a, **k: (reply, None, None))
    settings = category_settings(get_settings(), "parastatal")
    task = ts.TemplateTask(section, code, "Testville", "State", "TWB", "Testville – TWB", unit)
    cell = ts.score_template_one(SimpleNamespace(settings=settings), task, spec, evidence, "run1")
    return cell, spec


def _reply(**kw):
    base = dict(
        citation_id="TWB-01",
        quote="shall prepare its plans in coordination",
        comments="Clear.",
        confidence="high",
    )
    return ScoreReply(**{**base, **kw})


def test_a_typed_score_is_written_with_its_evidence(tmp_path, monkeypatch):
    cell, spec = _scorer(tmp_path, monkeypatch, "UPD", "UPD 1a", _reply(score=5, chapter="II"))
    assert cell.outcome == "scored"
    assert cell.values[spec.score_column] == 5
    assert cell.values[spec.column_for("source_link")] == "https://x.gov.in/act"
    assert cell.values[spec.column_for("chapter")] == "II"
    assert 'Quote: "shall prepare' in cell.values[spec.column_for("comments")]
    extra = cell.values[spec.column_for("additional_comments")]
    assert "Scored by AI" in extra and "TWB-01" in extra and "class A1" in extra


@pytest.mark.parametrize(
    "score, ok", [(5, True), (2.5, True), (0, True), (3.2, False), (10, False)]
)
def test_upd_1a_takes_only_the_levels_its_points_cell_takes(tmp_path, monkeypatch, score, ok):
    """UPD 1a: methodology 10 / 2.5 / 0, Max Score 5, the cell takes 0 to 5: allowed 5 / 2.5 / 0."""
    cell, spec = _scorer(tmp_path, monkeypatch, "UPD", "UPD 1a", _reply(score=score))
    comments = cell.values[spec.column_for("comments")]
    if ok:
        assert cell.outcome == "scored" and cell.values[spec.score_column] == score
        assert "Converted" not in comments  # nothing is converted
    else:
        assert cell.outcome == "needs_person" and cell.kind == "off_level"
        assert spec.score_column not in cell.values  # not written
        assert f"the AI gave {score:g}" in cell.detail
        assert "allowed scores are 5 / 2.5 / 0" in cell.detail
        assert "Score not written" in comments
        assert spec.column_for("source_link") not in cell.values  # no partial row


def test_partial_credit_questions_keep_the_range_check_only(tmp_path, monkeypatch):
    cell, spec = _scorer(tmp_path, monkeypatch, "UPD", "UPD 3a", _reply(score=3.75))
    assert cell.outcome == "scored" and cell.values[spec.score_column] == 3.75
    cell, spec = _scorer(tmp_path, monkeypatch, "UPD", "UPD 3a", _reply(score=6))
    assert cell.kind == "off_level" and "above the maximum" in cell.detail
    assert spec.score_column not in cell.values


def test_the_prompt_tells_the_scorer_which_scale_to_use(tmp_path):
    unit = Parastatal(id="TWB", name="x", type="water_supply_entity")
    answer = StepTwoAnswer("Answered", "a", "TWB-01", "q", "", "")

    def prompt(section, code):
        spec = fill.AITemplate(tmp_path / f"{code}.xlsx", _templates()[section]).specs[code]
        task = ts.TemplateTask(section, code, "T", "S", "TWB", "l", unit)
        return ts.build_prompt(task, spec, answer, [], "Parastatal")

    upd1a = prompt("UPD", "UPD 1a")
    assert "ALLOWED SCORES: 5 / 2.5 / 0." in upd1a and "enter 5 for it" in upd1a
    assert "SCALE:" not in upd1a  # no proportional conversion any more
    assert "ALLOWED SCORES: 5 / 0." in prompt("UPD", "UPD 1b")
    assert "ALLOWED SCORES: 10 / 0." in prompt("DPG", "DPG 6")
    partial = prompt("UPD", "UPD 3a")
    assert "PARTIAL CREDIT" in partial and "ALLOWED SCORES" not in partial


def test_calculated_sheets_get_inputs_not_a_score(tmp_path, monkeypatch):
    inputs = {
        "Plans required to be submitted": "yes",
        "Budgets required": "Yes",
        "Annual or perf": "No",
    }
    reply = _reply(inputs={}, score=4)
    spec = fill.AITemplate(tmp_path / "p.xlsx", _templates()["DPG"]).specs["DPG 2b"]
    reply.inputs = {c.header: v for c, v in zip(spec.inputs, inputs.values(), strict=True)}
    cell, spec = _scorer(tmp_path, monkeypatch, "DPG", "DPG 2b", reply)
    assert cell.outcome == "scored"
    assert [cell.values[c.column] for c in spec.inputs] == ["Yes", "Yes", "No"]
    assert spec.score_column not in cell.values  # the template calculates it


def test_a_row_the_formula_needs_more_from_is_not_written_at_all(tmp_path, monkeypatch):
    spec = fill.AITemplate(tmp_path / "p.xlsx", _templates()["DPG"]).specs["DPG 2b"]
    reply = _reply(inputs={spec.inputs[0].header: "Yes", spec.inputs[1].header: "Yes"})
    cell, spec = _scorer(tmp_path, monkeypatch, "DPG", "DPG 2b", reply)
    assert cell.outcome == "needs_person"
    assert not [c for c in cell.values if c in {i.column for i in spec.inputs}]  # no partial row
    assert "Not written" in cell.values[spec.column_for("comments")]
    bad = _reply(inputs={i.header: "Maybe" for i in spec.inputs})
    cell, _ = _scorer(tmp_path, monkeypatch, "DPG", "DPG 2b", bad)
    assert (
        cell.outcome == "needs_person" and "not one of" in cell.values[spec.column_for("comments")]
    )


def _years(spec, years, optional=True):
    """Figures for the named years (every input of those years, or only the needed ones)."""
    needed = set(spec.required_inputs)
    return {
        c.header: (10 if c.numeric else "FY 2023-24")
        for c in spec.inputs
        if c.header.split(" ")[0] in years and (optional or c.column in needed)
    }


@pytest.mark.parametrize("code", ["SC 1", "SC 3"])
def test_two_valid_years_are_enough_for_a_calculated_row(tmp_path, monkeypatch, code):
    spec = fill.AITemplate(tmp_path / "p.xlsx", _templates()["SC"]).specs[code]
    assert spec.min_years == 2 and set(spec.year_groups) == {"Yr1", "Yr2", "Yr3"}
    cell, spec = _scorer(
        tmp_path, monkeypatch, "SC", code, _reply(inputs=_years(spec, {"Yr1", "Yr2"}))
    )
    assert cell.outcome == "scored"
    written = {spec.columns[c].header for c in cell.values if spec.columns[c].kind == "input"}
    assert written and not any(h.startswith("Yr3") for h in written)
    assert "Based on 2 of 3 years (Yr1, Yr2)." in cell.values[spec.column_for("comments")]
    assert spec.score_column not in cell.values  # the template calculates it


def test_three_years_say_three_of_three(tmp_path, monkeypatch):
    spec = fill.AITemplate(tmp_path / "p.xlsx", _templates()["SC"]).specs["SC 3"]
    figures = _years(spec, {"Yr1", "Yr2", "Yr3"})
    cell, spec = _scorer(tmp_path, monkeypatch, "SC", "SC 3", _reply(inputs=figures))
    assert cell.outcome == "scored"
    assert "Based on 3 of 3 years (Yr1, Yr2, Yr3)." in cell.values[spec.column_for("comments")]


def test_one_year_or_a_half_filled_year_is_not_enough(tmp_path, monkeypatch):
    spec = fill.AITemplate(tmp_path / "p.xlsx", _templates()["SC"]).specs["SC 3"]
    cell, spec = _scorer(tmp_path, monkeypatch, "SC", "SC 3", _reply(inputs=_years(spec, {"Yr1"})))
    assert cell.outcome == "needs_person" and cell.kind == "years"
    assert "found 1 of 3 years" in cell.detail and "at least 2" in cell.detail
    assert not [c for c in cell.values if spec.columns[c].kind in ("input", "score")]
    # Yr2 has only its budget figure: it does not count, so Yr1 alone is not enough
    half = _years(spec, {"Yr1"})
    half[next(c.header for c in spec.inputs if c.header.startswith("Yr2 Budgeted"))] = 10
    cell, _ = _scorer(tmp_path, monkeypatch, "SC", "SC 3", _reply(inputs=half))
    assert cell.kind == "years" and "found 1 of 3" in cell.detail
    # with Yr1 and Yr2 complete and Yr3 half-filled: written, Yr3 left out
    both = {
        **_years(spec, {"Yr1", "Yr2"}),
        **{next(c.header for c in spec.inputs if c.header.startswith("Yr3 Budgeted")): 10},
    }
    cell, _ = _scorer(tmp_path, monkeypatch, "SC", "SC 3", _reply(inputs=both))
    assert cell.outcome == "scored" and "Yr3 left out" in cell.values[spec.column_for("comments")]
    assert not any(
        spec.columns[c].header.startswith("Yr3") for c in cell.values if c in spec.columns
    )


def test_other_calculated_sheets_still_need_every_input(tmp_path, monkeypatch):
    for path in reference_templates():
        for code, spec in read_structures(_load(path)).items():
            if spec.score_is_formula and not spec.min_years:
                assert not spec.year_groups, code
    assert fill.AITemplate(tmp_path / "s.xlsx", _templates()["SC"]).specs["SC 11"].min_years is None


@needs_calc
def test_the_template_calculates_the_two_year_rows_as_the_formula_says(tmp_path, monkeypatch):
    """SC 3: variance 10% and 20% over two years -> average 15% -> 10 points (hand-calculated)."""
    ai = fill.AITemplate(tmp_path / "sc.xlsx", _templates()["SC"])
    ai.ensure_unit("Testville", "TWB", "Water Supply Entity")
    spec = ai.specs["SC 3"]
    by = {c.header: c.column for c in spec.inputs}
    values = {
        by["Yr1 Budgeted income BE (Rs crore)"]: 100,
        by["Yr1 Actual income (Rs crore)"]: 110,
        by["Yr2 Budgeted income BE (Rs crore)"]: 100,
        by["Yr2 Actual income (Rs crore)"]: 80,
    }
    ai.write("SC 3", ai.ensure_row("SC 3", "Testville", "TWB"), values)
    saved = ai.save(tmp_path / "profile")
    assert saved.calculated, saved.problems
    row = next(
        r
        for r in read_filled_template(saved.path).rows
        if r.parastatal == "TWB" and r.code == "SC 3"
    )
    assert row.score == 10
    assert next(v for h, v in row.calculated.items() if h == "Years with valid data") == 2

    def scored(years):
        task = SimpleNamespace(city="Testville", unit="TWB", code="SC 3", section="SC")
        return SimpleNamespace(task=task, outcome="scored", log={"years_used": years})

    assert ts._check_valid_years(saved.path, [scored(["Yr1", "Yr2"])]) == []
    wrong = ts._check_valid_years(saved.path, [scored(["Yr1", "Yr2", "Yr3"])])
    assert wrong and "counts 2 valid year(s) but the AI wrote 3" in wrong[0]


def test_a_formula_header_stops_the_question_with_a_template_problem(tmp_path, monkeypatch):
    template = tmp_path / "Parastatal_SC_Template.xlsx"
    shutil.copyfile(_templates()["SC"], template)
    wb = _load(template)
    ws = wb["SC 3"]
    col = next(
        c
        for c in range(1, ws.max_column + 1)
        if ws.cell(13, c).value == "Yr1 Actual income (Rs crore)"
    )
    ws.cell(13, col).value = '="Yr1 Actual income "&"(Rs crore)"'
    wb.save(template)
    ai = fill.AITemplate(tmp_path / "ai.xlsx", template)
    spec = ai.specs["SC 3"]
    assert spec.problems and "is a formula" in spec.problems[0]
    # the question is left out of the plan, once, with a clear message
    from asics_agent.categories import load_bank
    from asics_agent.cities import load_register

    settings = category_settings(get_settings(), "parastatal")
    register, _ = load_register(settings.city_register)
    tasks, _, _, problems, skipped = ts.plan(settings, {"SC": ai}, register, load_bank(settings)[0])
    assert not [t for t in tasks if t.code == "SC 3"]
    assert [p for p in problems if p.startswith("SC 3: template problem") and "formula" in p]

    # and the scorer never asks the model about it
    def boom(*a, **k):
        raise AssertionError("the model must not be called")

    monkeypatch.setattr(ts, "call_json", boom)
    unit = Parastatal(id="TWB", name="x", type="water_supply_entity")
    task = ts.TemplateTask("SC", "SC 3", "Testville", "S", "TWB", "l", unit)
    cell = ts.score_template_one(
        SimpleNamespace(settings=settings), task, spec, CityEvidence(), "r"
    )
    assert cell.outcome == "needs_person" and cell.kind == "template_problem"
    assert cell.detail.startswith("template problem:") and "plain text" in cell.detail
    assert "template problem" in cell.values[spec.column_for("comments")]


def test_an_empty_or_repeated_header_is_a_template_problem_and_the_real_ones_are_clean(tmp_path):
    for path in reference_templates():
        assert not [c for c, s in read_structures(_load(path)).items() if s.problems]
    template = tmp_path / "t.xlsx"
    shutil.copyfile(_templates()["DPG"], template)
    wb = _load(template)
    ws = wb["DPG 2b"]
    names = {c: ws.cell(13, c).value for c in range(1, ws.max_column + 1)}
    inputs = [c for c, v in names.items() if v and v.startswith(("Plans", "Budgets"))]
    ws.cell(13, inputs[1]).value = ws.cell(13, inputs[0]).value  # a repeated header
    wb.save(template)
    spec = read_structures(_load(template))["DPG 2b"]
    assert any("same header" in p for p in spec.problems)


def test_a_header_formula_without_saved_text_is_reported_on_the_people_side(tmp_path):
    template = tmp_path / "f.xlsx"
    shutil.copyfile(_templates()["SC"], template)
    wb = _load(template)
    ws = wb["SC 11"]
    col = next(
        c for c in range(1, ws.max_column + 1) if ws.cell(13, c).value == "Names and tenure periods"
    )
    ws.cell(13, col).value = '="Names and "&"tenure periods"'
    wb.save(template)
    read = read_filled_template(template, "x")
    assert any("template problem" in p and "SC 11" in p for p in read.report.problems)


def test_a_quote_that_is_not_in_the_source_discards_the_answer(tmp_path, monkeypatch):
    cell, spec = _scorer(
        tmp_path, monkeypatch, "UPD", "UPD 1a", _reply(score=5, quote="an invented sentence")
    )
    assert cell.outcome == "needs_person" and cell.kind == "check_failed"
    assert spec.score_column not in cell.values
    assert "word for word" in cell.values[spec.column_for("comments")]


def test_a_code_that_now_asks_a_different_question_is_not_scored(tmp_path, monkeypatch):
    cell, spec = _scorer(
        tmp_path,
        monkeypatch,
        "UPD",
        "UPD 1a",
        _reply(score=5),
        answer_question="Does the board publish audited annual accounts every year?",
    )
    assert cell.outcome == "needs_person" and cell.kind == "mismatch"
    assert spec.score_column not in cell.values


def test_no_answer_leaves_the_row_blank(tmp_path, monkeypatch):
    ai = fill.AITemplate(tmp_path / "u.xlsx", _templates()["UPD"])
    spec = ai.specs["UPD 1a"]
    unit = Parastatal(id="TWB", name="x", type="water_supply_entity")
    task = ts.TemplateTask("UPD", "UPD 1a", "Testville", "S", "TWB", "Testville – TWB", unit)
    settings = category_settings(get_settings(), "parastatal")
    cell = ts.score_template_one(
        SimpleNamespace(settings=settings), task, spec, CityEvidence(), "run1"
    )
    assert cell.outcome == "needs_person" and cell.kind == "no_answer" and cell.values == {}


def test_the_prompt_lists_the_template_inputs_and_the_score_line(tmp_path):
    ai = fill.AITemplate(tmp_path / "d.xlsx", _templates()["DPG"])
    unit = Parastatal(id="TWB", name="x", type="water_supply_entity")
    task = ts.TemplateTask("DPG", "DPG 1a", "Testville", "S", "TWB", "l", unit)
    answer = StepTwoAnswer("Answered", "a", "TWB-01", "q", "", "")
    prompt = ts.build_prompt(task, ai.specs["DPG 1a"], answer, [], "Parastatal")
    assert "INPUT COLUMNS" in prompt and "Allowed values: A / B / C." in prompt
    assert "SCORE:" not in prompt  # DPG 1a is calculated
    typed = ts.build_prompt(
        task,
        fill.AITemplate(tmp_path / "u.xlsx", _templates()["UPD"]).specs["UPD 1a"],
        answer,
        [],
        "Parastatal",
    )
    assert 'SCORE: give "score" as a number from 0 to 5' in typed
    assert "ALLOWED SCORES: 5 / 2.5 / 0." in typed
