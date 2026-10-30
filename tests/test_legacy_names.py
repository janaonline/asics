"""Work saved before the rename (old names) still loads; new work uses only the new names."""

import dataclasses
import json
import logging
from datetime import datetime

from asics_agent import costs, legacy_names
from asics_agent.agent_setup import MemoryScope, section_skill, select_notes
from asics_agent.categories import category_settings, load_categories
from asics_agent.config import _base_settings, get_settings
from asics_agent.models import Parastatal
from asics_agent.workbook import answers_files, answers_patterns


def test_old_names_map_to_the_new_ones():
    assert legacy_names.canonical_category("UPD") == "ulg"
    assert legacy_names.canonical_category("Parastatal") == "parastatal"
    assert legacy_names.canonical_unit("city_government") == "ulg"
    assert legacy_names.canonical_unit("City government") == "ulg"


def test_old_environment_variable_is_read_with_a_warning(monkeypatch, caplog):
    monkeypatch.delenv("ASICS_CATEGORY", raising=False)
    monkeypatch.setenv("ASICS_VERTICAL", "upd")
    with caplog.at_level(logging.WARNING):
        assert legacy_names.env_category() == "ulg"
    assert "ASICS_CATEGORY" in caplog.text
    monkeypatch.setenv("ASICS_CATEGORY", "parastatal")  # the new one wins
    assert legacy_names.env_category() == "parastatal"
    assert _base_settings().category == "parastatal"


def test_an_old_outputs_folder_is_used_until_the_new_one_exists(tmp_path):
    base = dataclasses.replace(get_settings(), outputs_dir=tmp_path, outputs_root=tmp_path)
    assert category_settings(base, "ulg").outputs_dir == tmp_path / "ULG"
    (tmp_path / "UPD").mkdir()
    assert category_settings(base, "ulg").outputs_dir == tmp_path / "UPD"  # saved before
    assert category_settings(base, "upd").category == "ulg"  # the old name is accepted
    (tmp_path / "ULG").mkdir()
    assert category_settings(base, "ulg").outputs_dir == tmp_path / "ULG"


def test_old_settings_file_keys_still_load(tmp_path):
    folder = tmp_path / "categories"
    folder.mkdir()
    (tmp_path / "agents").mkdir()
    (tmp_path / "prompts").mkdir()
    (folder / "upd.md").write_text("---\nname: upd\ncode: UPD\nunit: city_government\n---\nOld.\n")
    found, _ = load_categories(tmp_path)
    assert found["ulg"].unit == "ulg" and found["ulg"].scoring_code == "UPD"


def test_old_answers_files_are_found(tmp_path):
    settings = category_settings(get_settings(), "ulg")
    run = tmp_path / "answers" / "20261012-084650-9843"
    run.mkdir(parents=True)
    old = run / "ASICS_UPD_Bengaluru_Phase2.xlsx"
    old.write_text("")
    assert "ASICS_ULG_*.xlsx" in answers_patterns(settings)
    assert answers_files(tmp_path, settings) == [old]
    assert answers_files(tmp_path, category_settings(get_settings(), "parastatal")) == []


def test_the_old_unit_type_is_read_as_ulg():
    old = Parastatal(id="ULG", name="Bengaluru city government", type="city_government")
    assert old.type == "ulg"


def test_notes_in_the_old_memory_folder_still_apply(tmp_path):
    note = tmp_path / "memory" / "verticals" / "upd" / "old.md"
    note.parent.mkdir(parents=True)
    note.write_text("An older ULG note.")
    chosen, _ = select_notes(tmp_path, MemoryScope(city="Bengaluru"), "ulg", 20000)
    assert [(n.path, n.scope, n.target) for n in chosen] == [
        ("verticals/upd/old.md", "category", "ulg")
    ]
    chosen, _ = select_notes(tmp_path, MemoryScope(city="Bengaluru"), "parastatal", 20000)
    assert chosen == []


def test_section_guidance_in_the_old_folder_still_applies(tmp_path):
    (tmp_path / "skills" / "sections" / "upd").mkdir(parents=True)
    (tmp_path / "skills" / "sections" / "upd" / "upd.md").write_text("Old ULG guidance.")
    (tmp_path / "skills" / "sections" / "upd.md").write_text("Shared.")
    assert section_skill(tmp_path, "UPD", "ulg") == "sections/upd/upd"
    assert section_skill(tmp_path, "UPD", "parastatal") == "sections/upd"
    (tmp_path / "skills" / "sections" / "ulg").mkdir()
    (tmp_path / "skills" / "sections" / "ulg" / "upd.md").write_text("New ULG guidance.")
    assert section_skill(tmp_path, "UPD", "ulg") == "sections/ulg/upd"


def test_old_cost_records_count_for_the_new_category(tmp_path):
    base = dataclasses.replace(get_settings(), outputs_dir=tmp_path, outputs_root=tmp_path)
    folder = costs.usage_dir(base)
    record = {
        "kind": "run",
        "step": 1,
        "total_usd": 2.0,
        "work": 4,
        "unit": "agency",
        "started": datetime(2026, 10, 12, 8, 0).isoformat(),
        "label": "old",
        "vertical": "upd",
        "vertical_title": "UPD",
    }
    (folder / "20261012-080000_step1_upd.json").write_text(json.dumps(record))
    (old,) = costs.history(base)
    assert (old.category, old.category_title) == ("ulg", "UPD")
    assert costs.rate(base, 1, "ulg")[0] == 0.5


def test_the_last_category_file_may_have_its_old_name(tmp_path):
    assert legacy_names.read_app_file(tmp_path, "last_category") == ""
    (tmp_path / "last_vertical").write_text("upd\n")
    assert legacy_names.read_app_file(tmp_path, "last_category") == "upd"
    (tmp_path / "last_category").write_text("ulg")
    assert legacy_names.read_app_file(tmp_path, "last_category") == "ulg"


def test_unit_headers_read_both_ways():
    from asics_agent.workbook import canonical_header, unit_sheet, unit_text

    assert unit_text("Parastatal ID", "ULG") == "ULG ID"
    assert unit_text("Parastatals", "ULG") == "ULG"
    assert unit_text("Parastatal ID") == "Parastatal ID"  # the Parastatal category is unchanged
    assert [canonical_header(h) for h in ("ULG ID", "ULG Name", "ULG Type", "ULG")] == [
        "Parastatal ID",
        "Parastatal Name",
        "Parastatal Type",
        "Parastatal",
    ]
    assert canonical_header("Source Title") == "Source Title"
    assert unit_sheet(["How to Use", "ULG"]) == "ULG"
    assert unit_sheet(["How to Use", "Parastatals"]) == "Parastatals"
