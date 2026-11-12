"""The People's scoring and Scores pages, clicked through headlessly (Streamlit's AppTest)."""

import dataclasses

import pytest
from openpyxl import load_workbook
from streamlit.testing.v1 import AppTest

from asics_agent import hosting
from asics_agent.categories import category_settings
from asics_agent.scoring import human_merge, submissions
from asics_agent.scoring.recalc import soffice
from asics_agent.scoring.template_import import read_structures
from tests.test_human_submissions import CITY, UNIT, _template, make_file

needs_calc = pytest.mark.skipif(soffice() is None, reason="LibreOffice is not installed")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def people_script():
    import streamlit as st

    import people_page

    people_page.render(st.session_state["settings"], None)


def scores_script():
    import streamlit as st

    import compare_page

    compare_page.render(st.session_state["settings"], None, st.session_state["city"])


@pytest.fixture
def settings(practice, tmp_path):
    folder, base, _ = practice
    vs = category_settings(base, "parastatal")
    outputs = vs.outputs_dir / "practice"
    vs = dataclasses.replace(
        vs,
        outputs_dir=outputs,
        city_register=outputs / "practice_register.xlsx",
        scoring_dir=tmp_path / "scoring",
    )
    for ai in folder.glob("ai/PARASTATAL_*_AI*"):  # the AI's practice files, to compare with
        target = vs.scoring_dir / "ai" / ai.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(ai.read_bytes())
    return vs


def _filled(settings, tmp_path):
    """(section, file) with a typed-score question filled in for the sample city."""
    section = next(iter(submissions.section_templates(settings)))
    specs = read_structures(load_workbook(_template(section)))
    code, spec = next((c, s) for c, s in specs.items() if s.max_score and not s.score_is_formula)
    path = make_file(
        tmp_path / "Scored by Asha.xlsx",
        [(code, CITY, UNIT, {"score": spec.max_score / 2})],
        section,
    )
    return section, code, path


def _app(settings, script=people_script, **state):
    at = AppTest.from_function(script, default_timeout=180)
    at.session_state["settings"] = settings
    for k, v in state.items():
        at.session_state[k] = v
    return at.run()


@needs_calc
def test_upload_preview_save_merge_and_see_it_on_the_scores_page(settings, tmp_path):
    section, code, path = _filled(settings, tmp_path)
    at = _app(settings)
    assert not at.exception
    assert any("Upload" in m.value for m in at.markdown)
    at.text_input(key="people-scorer").set_value("Asha Rao").run()
    at.file_uploader(key=f"people-files-{section}").set_value(
        [(path.name, path.read_bytes(), XLSX)]
    ).run()
    assert not at.exception
    assert not submissions.list_submissions(settings)  # nothing is stored until Save
    assert any("Rows with a score" in m.label for m in at.metric)
    save = next(b for b in at.button if b.key.endswith("-save"))
    save.click().run()
    assert not at.exception
    stored = submissions.list_submissions(settings)
    assert [s.scorer for s in stored] == ["Asha Rao"] and stored[0].section == section
    assert not [b for b in at.button if b.key.endswith("-save")]  # the same file is a duplicate now
    assert any("already stored" in i.value for i in at.info)
    at.button(key="people-merge").click().run()
    assert not at.exception, at.exception
    assert [p.name for p in human_merge.merged_files(settings)] == [
        f"PARASTATAL_{section}_human.xlsx"
    ]
    assert any("Merged" in s.value for s in at.success)

    scores = _app(settings, scores_script, city=CITY)
    assert not scores.exception, scores.exception
    assert any("Compare" in t.label for t in scores.tabs)


def test_files_that_cannot_be_saved_say_why(settings, tmp_path):
    section = next(iter(submissions.section_templates(settings)))
    at = _app(settings)
    at.file_uploader(key=f"people-files-{section}").set_value(
        [("damaged.xlsx", b"not a workbook", XLSX)]  # (Streamlit itself refuses .xlsm)
    ).run()
    assert not at.exception
    assert any("not a readable Excel workbook" in e.value for e in at.error)
    other = next(s for s in submissions.section_templates(settings) if s != section)
    wrong = make_file(
        tmp_path / "wrong.xlsx",
        [(next(iter(read_structures(load_workbook(_template(other))))), CITY, UNIT, {"score": 0})],
        other,
    )
    at.file_uploader(key=f"people-files-{section}").set_value(
        [(wrong.name, wrong.read_bytes(), XLSX)]
    ).run()
    assert any(f"This is the {other} template" in e.value for e in at.error)
    assert not submissions.list_submissions(settings)
    assert not [b for b in at.button if b.key.endswith("-save")]


def test_open_buttons_hide_on_a_server_but_downloads_stay(monkeypatch):
    opener = lambda path: None  # noqa: E731
    monkeypatch.delenv("ASICS_HOSTED", raising=False)
    assert hosting.can_open(opener) and not hosting.can_open(None)
    monkeypatch.setenv("ASICS_HOSTED", "1")
    assert hosting.hosted() and not hosting.can_open(opener)


def _typo_file(settings, tmp_path, name, score):
    section = next(iter(submissions.section_templates(settings)))
    specs = read_structures(load_workbook(_template(section)))
    code, spec = next((c, s) for c, s in specs.items() if s.max_score and not s.score_is_formula)
    path = make_file(
        tmp_path / name, [(code, "Sample Cty A", UNIT, {"score": spec.max_score * score})], section
    )
    return section, path


def test_the_resolution_table_asks_once_prefills_later_and_lists_names_to_add(settings, tmp_path):
    section, path = _typo_file(settings, tmp_path, "one.xlsx", 0.5)
    at = _app(settings)
    at.text_input(key="people-scorer").set_value("Asha Rao").run()
    at.file_uploader(key=f"people-files-{section}").set_value(
        [(path.name, path.read_bytes(), XLSX)]
    ).run()
    assert not at.exception, at.exception
    sha8 = submissions.sha256_of(path.read_bytes())[:8]
    save = next(b for b in at.button if b.key.endswith("-save"))
    assert save.disabled  # two names need a choice first
    assert any("Cities and parastatals" in m.value for m in at.markdown)
    at.selectbox(key=f"res-{sha8}-0-act").select("Map to existing").run()
    at.selectbox(key=f"res-{sha8}-1-act").select("Map to existing").run()
    assert not at.exception, at.exception
    save = next(b for b in at.button if b.key.endswith("-save"))
    assert not save.disabled
    save.click().run()
    assert not at.exception, at.exception
    first = submissions.list_submissions(settings)[0]
    assert [(d["kind"], d["action"], d["as_written"]) for d in first.decisions] == [
        ("city", "map", "Sample Cty A"),
        ("parastatal", "map", UNIT),
    ]
    assert any(b.label == "Download as CSV" for b in at.get("download_button"))  # names to add

    # a new file with the same spellings: pre-filled, nothing to answer; a choice can still change
    section2, path2 = _typo_file(settings, tmp_path, "two.xlsx", 1.0)
    at.file_uploader(key=f"people-files-{section}").set_value(
        [(path2.name, path2.read_bytes(), XLSX)]
    ).run()
    sha8b = submissions.sha256_of(path2.read_bytes())[:8]
    assert at.selectbox(key=f"res-{sha8b}-0-act").value == "Map to existing"
    save2 = next(b for b in at.button if b.key.endswith("-save") and not b.disabled)
    at.selectbox(key=f"res-{sha8b}-0-act").select("Skip").run()
    assert not at.exception, at.exception
    assert any(not b.disabled for b in at.button if b.key.endswith("-save"))  # still savable
    assert save2 is not None
