"""Names in people's files that the register does not know: resolve, remember, merge, flag."""

import dataclasses
import hashlib
import shutil

import pytest
from openpyxl import load_workbook

from asics_agent.categories import category_settings, load_bank
from asics_agent.cities import load_register
from asics_agent.scoring import compare_run, human_merge, register_edit, submissions
from asics_agent.scoring import name_resolution as nr
from asics_agent.scoring import template_scoring as ts
from asics_agent.scoring.recalc import soffice
from asics_agent.scoring.template_import import read_filled_template
from tests.test_human_submissions import make_file

needs_calc = pytest.mark.skipif(soffice() is None, reason="LibreOffice is not installed")
CITY, UNIT = "Sample City A", "SWB"


@pytest.fixture
def settings(practice, tmp_path):
    """The Parastatal category with a COPY of the practice register (tests may edit it)."""
    _, base, _ = practice
    vs = category_settings(base, "parastatal")
    outputs = vs.outputs_dir / "practice"
    register = tmp_path / "register.xlsx"
    shutil.copyfile(outputs / "practice_register.xlsx", register)
    return dataclasses.replace(
        vs, outputs_dir=outputs, city_register=register, scoring_dir=tmp_path / "scoring"
    )


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stored(settings, path, scorer="Asha", decisions=None):
    data = path.read_bytes()
    preview = submissions.preview_file(settings, "UPD", path.name, data)
    return preview, submissions.save_submission(settings, preview, data, scorer, "", decisions)


def resolutions(settings, path):
    return {
        (r.kind, r.city_as_written, r.as_written): r
        for r in submissions.preview_file(settings, "UPD", path.name, path.read_bytes()).resolutions
    }


# -- labels ------------------------------------------------------------------------------------
def test_row_labels_match_with_different_dashes_spaces_and_case():
    same = ["Bengaluru - BWSSB", "Bengaluru – BWSSB", "bengaluru—bwssb", "Bengaluru  –  BWSSB"]
    assert {nr.label_key(t) for t in same} == {("bengaluru", "bwssb")}
    assert all(nr.split_label(t) == ("Bengaluru", "BWSSB") or t.startswith("beng") for t in same)
    assert nr.split_label("Surat") == ("Surat", "")
    assert nr.split_label("Hubballi-Dharwad") == ("Hubballi-Dharwad", "")  # an unspaced hyphen
    assert nr.split_label("Hubballi-Dharwad - HDMC") == ("Hubballi-Dharwad", "HDMC")
    assert nr.split_label("Hubballi - Dharwad", ["Hubballi - Dharwad"]) == (
        "Hubballi - Dharwad",
        "",
    )
    # the old workbook code reads them the same way
    from asics_agent.scoring import human, workflow

    assert human.city_of("Bengaluru - BWSSB") == human.city_of("Bengaluru – BWSSB") == "Bengaluru"
    assert workflow.unit_of("Bengaluru - BWSSB") == workflow.unit_of("Bengaluru – BWSSB") == "BWSSB"
    assert workflow.unit_of("Surat") == "ULG"


# -- the preview's table -----------------------------------------------------------------------
def test_a_typo_city_is_matched_closely_and_a_known_one_needs_no_decision(settings, tmp_path):
    path = make_file(
        tmp_path / "a.xlsx",
        [("UPD 1a", "Sample Cty A", UNIT, {"score": 3}), ("UPD 1a", CITY, UNIT, {"score": 2})],
    )
    found = resolutions(settings, path)
    typo = found[("city", "", "Sample Cty A")]
    assert typo.match.kind == "close" and typo.match.name == CITY and typo.needs_decision
    assert not found[("city", "", CITY)].needs_decision  # exact: placed without asking
    assert not found[("parastatal", CITY, UNIT)].needs_decision


def test_an_other_name_matches_without_asking(settings, tmp_path):
    assert register_edit.add_other_name(settings, "city", CITY, "Sample Cty A") is None
    path = make_file(tmp_path / "a.xlsx", [("UPD 1a", "sample  cty a", UNIT, {"score": 3})])
    r = resolutions(settings, path)[("city", "", "sample cty a")]
    assert r.match.kind == "alias" and not r.needs_decision


# -- merging with decisions ---------------------------------------------------------------------
def places(settings, section="UPD"):
    read = read_filled_template(submissions.merged_path(settings, section), "")
    return {(r.code, r.city, r.parastatal): r for r in read.rows}


@needs_calc
def test_mapping_a_typo_city_merges_it_under_the_register_city(settings, tmp_path):
    path = make_file(tmp_path / "a.xlsx", [("UPD 1a", "Sample Cty A", UNIT, {"score": 3})])
    r = resolutions(settings, path)
    decisions = [
        nr.Decision(
            "city", "Sample Cty A", "map", city_slug=r[("city", "", "Sample Cty A")].match.slug
        ),
        nr.Decision(
            "parastatal",
            UNIT,
            "map",
            "Sample Cty A",
            city_slug="sample_city_a",
            parastatal_code=UNIT,
        ),
    ]
    stored(settings, path, decisions=decisions)
    report = human_merge.merge_category(settings)
    assert not report.unregistered and not report.skipped, report.needs_a_look()
    assert places(settings)[("UPD 1a", CITY, UNIT)].score == 3


@needs_calc
def test_without_a_decision_a_near_spelling_is_merged_as_its_own_place_not_guessed(
    settings, tmp_path
):
    path = make_file(tmp_path / "a.xlsx", [("UPD 1a", "Sample Cty A", UNIT, {"score": 3})])
    stored(settings, path)
    report = human_merge.merge_category(settings)
    assert [u["city"] for u in report.unregistered] == ["Sample Cty A"]
    assert ("UPD 1a", "Sample Cty A", UNIT) in places(settings)  # nothing silently dropped
    assert ("UPD 1a", CITY, UNIT) not in places(settings)  # and not joined to a guess


@needs_calc
def test_a_new_city_is_merged_flagged_and_the_register_is_untouched(settings, tmp_path):
    path = make_file(tmp_path / "a.xlsx", [("UPD 1a", "Testville", "TWB", {"score": 4})])
    before = sha(settings.city_register)
    decisions = [
        nr.Decision("city", "Testville", "new", state="Karnataka", city_slug="testville"),
        nr.Decision(
            "parastatal",
            "TWB",
            "new",
            "Testville",
            parastatal_code="TWB",
            type="water_supply_entity",
        ),
    ]
    stored(settings, path, decisions=decisions)
    report = human_merge.merge_category(settings)
    assert [(u["city"], u["parastatal"]) for u in report.unregistered] == [("Testville", "TWB")]
    assert places(settings)[("UPD 1a", "Testville", "TWB")].score == 4
    assert sha(settings.city_register) == before
    info = human_merge.read_merge_info(submissions.merged_path(settings, "UPD"))
    assert info["unregistered"][0]["type"] == "Water Supply Entity"
    # the Scores page can show it, flagged, with no AI side
    assert [u["city"] for u in compare_run.unregistered_places(settings)] == ["Testville"]
    view = compare_run.load_view(settings, "Testville")
    assert view.not_in_register and view.comparison is not None
    rows = view.comparison.rows
    assert rows and all(nr.NOT_IN_REGISTER in r.notes for r in rows)
    assert all(r.ai_score is None for r in rows)
    assert any(r.human_score == 4 for r in rows)


@needs_calc
def test_a_parastatal_not_in_the_register_of_a_known_city_is_flagged_on_its_rows_only(
    settings, tmp_path
):
    path = make_file(
        tmp_path / "a.xlsx",
        [("UPD 1a", CITY, "NEWCO", {"score": 2}), ("UPD 1a", CITY, UNIT, {"score": 3})],
    )
    stored(settings, path)
    report = human_merge.merge_category(settings)
    assert [(u["city"], u["parastatal"], u["city_in_register"]) for u in report.unregistered] == [
        (CITY, "NEWCO", True)
    ]
    assert places(settings)[("UPD 1a", CITY, "NEWCO")].score == 2
    view = compare_run.load_view(settings, CITY)
    flagged = {r.unit for r in view.comparison.rows if nr.NOT_IN_REGISTER in r.notes}
    assert flagged == {"NEWCO"}
    assert not view.not_in_register


@needs_calc
def test_a_skipped_city_is_not_merged_and_is_listed(settings, tmp_path):
    path = make_file(
        tmp_path / "a.xlsx",
        [("UPD 1a", "Faraway", "FW", {"score": 5}), ("UPD 1a", CITY, UNIT, {"score": 3})],
    )
    stored(settings, path, decisions=[nr.Decision("city", "Faraway", "skip")])
    report = human_merge.merge_category(settings)
    assert not report.unregistered
    assert any("Faraway" in line and "skipped by your choice" in line for line in report.skipped)
    got = places(settings)
    assert ("UPD 1a", CITY, UNIT) in got and not any(k[1] == "Faraway" for k in got)
    from asics_agent.scoring import workflow

    step = workflow.merge_templates(settings)
    assert any("Faraway" in line for line in step.skipped)


@needs_calc
def test_decisions_are_remembered_and_the_same_file_twice_adds_nothing(settings, tmp_path):
    path = make_file(tmp_path / "a.xlsx", [("UPD 1a", "Sample Cty A", UNIT, {"score": 3})])
    decisions = [
        nr.Decision("city", "Sample Cty A", "map", city_slug="sample_city_a"),
        nr.Decision(
            "parastatal",
            UNIT,
            "map",
            "Sample Cty A",
            city_slug="sample_city_a",
            parastatal_code=UNIT,
        ),
    ]
    _, first = stored(settings, path, decisions=decisions)
    again = submissions.preview_file(settings, "UPD", "copy.xlsx", path.read_bytes())
    assert again.duplicate_of == first.submission_id and not again.can_save
    with pytest.raises(submissions.SubmissionError, match="already stored"):
        submissions.save_submission(settings, again, path.read_bytes(), "Ben", "", decisions)
    assert len(submissions.list_submissions(settings)) == 1
    assert len(submissions.list_submissions(settings)[0].decisions) == 2  # unchanged
    # another file with the same spelling is pre-filled and asks nothing
    other = make_file(tmp_path / "b.xlsx", [("UPD 1b", "Sample Cty A", UNIT, {"score": 2})])
    preview = submissions.preview_file(settings, "UPD", other.name, other.read_bytes())
    asked = [r for r in preview.resolutions if r.needs_decision]
    assert {r.as_written for r in asked} == {"Sample Cty A"}  # its parastatal then matches by code
    assert all(r.remembered is not None and r.remembered.action == "map" for r in asked)
    assert not nr.undecided(preview.resolutions, list(nr.remembered_decisions(settings).values()))
    # a change of mind is possible and the earlier decisions are kept
    changed = nr.Decision("city", "Sample Cty A", "skip")
    sub = submissions.update_decisions(settings, first.submission_id, [changed], "Lead")
    assert len(sub.decision_history) == 2 and sub.decisions[0]["action"] == "skip"
    assert nr.remembered_decisions(settings)[changed.key()].action == "skip"


# -- the register ------------------------------------------------------------------------------
def test_an_other_name_is_written_with_a_backup_and_only_that_cell_changes(settings):
    path = settings.city_register
    before = {
        ws.title: [[c.value for c in row] for row in ws.iter_rows()]
        for ws in load_workbook(path).worksheets
    }
    assert register_edit.add_other_name(settings, "city", CITY, "Bangalor") is None
    history = path.parent / register_edit.HISTORY
    assert len(list(history.glob("*_register.xlsx"))) == 1
    after = {
        ws.title: [[c.value for c in row] for row in ws.iter_rows()]
        for ws in load_workbook(path).worksheets
    }
    changed = [
        (sheet, r, c)
        for sheet in before
        for r, (old, new) in enumerate(zip(before[sheet], after[sheet], strict=False))
        for c, (a, b) in enumerate(zip(old, new, strict=False))
        if a != b
    ]
    assert len(changed) == 1 and changed[0][0] == "Cities"
    register, issues = load_register(path)
    assert "Bangalor" in register["sample_city_a"].aliases
    assert register_edit.add_other_name(settings, "city", CITY, "bangalor") is None  # already there
    assert len(list(history.glob("*_register.xlsx"))) == 1  # no second backup for no change


def test_a_parastatal_other_name_adds_the_optional_column_to_an_older_register(settings):
    wb = load_workbook(settings.city_register)
    ws = wb["Parastatals"]
    last = ws.max_column
    assert ws.cell(1, last).value == "Other names"
    ws.delete_cols(last)  # a register from before parastatals had Other names
    wb.save(settings.city_register)
    assert register_edit.add_other_name(settings, "parastatal", CITY, "Water Brd", UNIT) is None
    register, _ = load_register(settings.city_register)
    unit = next(p for p in register["sample_city_a"].parastatals if p.id == UNIT)
    assert unit.aliases == ["Water Brd"]
    assert nr.match_unit({unit.id: unit}, "water  brd").kind == "alias"
    assert "not" in (
        register_edit.add_other_name(settings, "parastatal", CITY, "x", "NOPE") or "not"
    )


def test_the_names_to_add_list_and_its_csv(settings, tmp_path):
    path = make_file(
        tmp_path / "a.xlsx",
        [
            ("UPD 1a", "Testville", "TWB", {"score": 4}),
            ("UPD 1a", "Sample Cty A", UNIT, {"score": 3}),
        ],
    )
    decisions = [
        nr.Decision("city", "Testville", "new", state="Karnataka", city_slug="testville"),
        nr.Decision("parastatal", "TWB", "new", "Testville", parastatal_code="TWB", type="other"),
        nr.Decision("city", "Sample Cty A", "map", city_slug="sample_city_a"),
        nr.Decision(
            "parastatal",
            UNIT,
            "map",
            "Sample Cty A",
            parastatal_code=UNIT,
            city_slug="sample_city_a",
        ),
    ]
    stored(settings, path, decisions=decisions)
    rows = register_edit.names_to_add(settings)
    kinds = {(r["what_to_add"], r["name_in_file"]) for r in rows}
    assert ("New city", "Testville") in kinds and ("New parastatal", "TWB") in kinds
    assert ("Other name for a city", "Sample Cty A") in kinds
    assert ("Other name for a parastatal", UNIT) not in kinds  # SWB already matches by its code
    text = register_edit.names_csv(rows)
    assert text.splitlines()[0].startswith("what_to_add,name_in_file,city")
    # once the register has the name as an Other name, it leaves the list
    register_edit.add_other_name(settings, "city", CITY, "Sample Cty A")
    assert ("Other name for a city", "Sample Cty A") not in {
        (r["what_to_add"], r["name_in_file"]) for r in register_edit.names_to_add(settings)
    }


# -- the AI path is unchanged -------------------------------------------------------------------
@needs_calc
def test_an_unregistered_city_never_enters_an_ai_run(settings, tmp_path, practice):
    path = make_file(tmp_path / "a.xlsx", [("UPD 1a", "Testville", "TWB", {"score": 4})])
    stored(settings, path)
    human_merge.merge_category(settings)
    register, _ = load_register(settings.city_register)
    bank, _ = load_bank(settings)
    ais = {
        s: ts.AITemplate(tmp_path / f"{s}.xlsx", t)
        for s, t in submissions.section_templates(settings).items()
    }
    tasks, ready, _, problems, _ = ts.plan(settings, ais, register, bank, None, None)
    assert "Testville" not in ready and not any(t.city == "Testville" for t in tasks)
