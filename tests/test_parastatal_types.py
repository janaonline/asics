from pathlib import Path

import pytest

from asics_agent import parastatal_types as pt
from asics_agent.cities import TYPES, load_register, write_register
from asics_agent.models import CityConfig, Parastatal

ROOT = Path(__file__).resolve().parents[1]


def test_old_names_are_read_as_the_new_codes():
    for old, new in [
        ("water_supply_board", "water_supply_entity"),
        ("Water supply board", "water_supply_entity"),
        ("transport_corporation", "public_bus_transport_operator"),
        ("Transport corporation", "public_bus_transport_operator"),
        ("Development authority", "development_authority"),
        ("city_government", pt.ULG_TYPE),
        ("City government", pt.ULG_TYPE),
    ]:
        assert pt.canonical_type(old) == new
        assert Parastatal(id="X", name="x", type=old).type == new
    assert pt.canonical_type("water_supply_entity") == "water_supply_entity"


def test_an_unknown_type_is_rejected_not_guessed():
    with pytest.raises(ValueError):
        Parastatal(id="X", name="x", type="airport_authority")


def test_the_type_list_is_the_one_place_that_names_types():
    assert set(TYPES.values()) == set(pt.TYPE_CODES)
    assert {t.label for t in pt.PARASTATAL_TYPES} == set(TYPES)
    prompt = (ROOT / "agent_setup/prompts/discover-parastatals.md").read_text()
    for code in pt.TYPE_CODES:
        assert f'"{code}"' in prompt  # the discovery prompt offers every type
    assert "water_supply_board" not in prompt and "transport_corporation" not in prompt


def test_no_old_type_name_is_written_back(tmp_path):
    cities = [
        CityConfig(
            slug="c",
            name="C",
            state="S",
            ulg="C Corp",
            parastatals=[
                Parastatal(id="W", name="Water", type="water_supply_board"),
                Parastatal(id="B", name="Buses", type="transport_corporation"),
            ],
        )
    ]
    path = tmp_path / "register.xlsx"
    write_register(path, cities)
    from openpyxl import load_workbook

    wb = load_workbook(path)
    text = " ".join(str(c.value) for ws in wb.worksheets for row in ws.iter_rows() for c in row)
    assert "Water supply board" not in text and "Transport corporation" not in text
    assert "Water Supply Entity" in text and "Public Bus Transport Operator" in text
    configs, issues = load_register(path)
    assert not [i for i in issues if i.severity == "error"]
    assert {p.id: p.type for p in configs["c"].parastatals} == {
        "W": "water_supply_entity",
        "B": "public_bus_transport_operator",
    }


def test_a_register_with_old_labels_still_loads(tmp_path):
    from openpyxl import load_workbook

    path = tmp_path / "register.xlsx"
    write_register(
        path,
        [
            CityConfig(
                slug="c",
                name="C",
                state="S",
                ulg="C Corp",
                parastatals=[Parastatal(id="W", name="Water", type="water_supply_entity")],
            )
        ],
    )
    wb = load_workbook(path)
    ws = wb["Parastatals"]
    ws.cell(2, 4, "Water supply board")  # how the old register spelled it
    wb.save(path)
    configs, issues = load_register(path)
    assert not [i for i in issues if i.severity == "error"]
    assert configs["c"].parastatals[0].type == "water_supply_entity"
