"""The two small things the portal may do to the city register, and the list for the rest.

  * add_other_name: write a name from a people's file into a city's (or a parastatal's) "Other
    names" cell, so it matches by itself from then on. The register is copied to
    data/cities/history/ first, only that cell (and, once, an optional "Other names" column on the
    Parastatals sheet) changes, and the result is checked by loading the register again; if it does
    not load as before, the copy is put back.
  * names_to_add: what the research lead would add by hand: cities and parastatals people scored
    that are not in the register, and names not yet written as an "Other name".

Nothing else in the register is ever changed from the portal.
"""

import csv
import io
import shutil
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from asics_agent.cities import ALIASES, CITIES_SHEET, PARASTATALS_SHEET, load_register
from asics_agent.scoring.name_resolution import (
    Decision,
    match_city,
    match_unit,
    norm_name,
    remembered_decisions,
)

HISTORY = "history"


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def backup(path: Path) -> Path:
    folder = path.parent / HISTORY
    folder.mkdir(parents=True, exist_ok=True)
    copy = folder / f"{datetime.now():%Y%m%d-%H%M%S}_{path.name}"
    shutil.copyfile(path, copy)
    return copy


def _column(ws, name: str) -> int | None:
    return next(
        (c for c in range(1, ws.max_column + 1) if _text(ws.cell(1, c).value) == name), None
    )


def add_other_name(settings, kind: str, city_name: str, alias: str, code: str = "") -> str | None:
    """Write `alias` as an "Other name" of the register's city (or its parastatal `code`).
    Returns why it could not be done, or None when it was done."""
    path = settings.city_register
    if not path.exists():
        return f"The city register is not at {path}."
    if not norm_name(alias):
        return "There is no name to add."
    before, _ = load_register(path)
    errors_before = len(load_register(path)[1])
    wb = load_workbook(path)
    if CITIES_SHEET not in wb.sheetnames or PARASTATALS_SHEET not in wb.sheetnames:
        return "The register does not have the Cities and Parastatals sheets."
    cities, paras = wb[CITIES_SHEET], wb[PARASTATALS_SHEET]
    city_col = _column(cities, "City")
    row = next(
        (
            r
            for r in range(2, cities.max_row + 1)
            if norm_name(cities.cell(r, city_col).value) == norm_name(city_name)
        ),
        None,
    )
    if row is None:
        return f"{city_name} is not on the register's Cities sheet."
    if kind == "city":
        ws, target_row, column = cities, row, _column(cities, ALIASES)
        if column is None:
            column = cities.max_column + 1
            _add_header(cities, column)
    else:
        pcity, pid = _column(paras, "City"), _column(paras, "Parastatal ID")
        if pcity is None or pid is None:
            return "The register's Parastatals sheet has no City and Parastatal ID columns."
        target_row = next(
            (
                r
                for r in range(2, paras.max_row + 1)
                if norm_name(paras.cell(r, pcity).value) == norm_name(city_name)
                and norm_name(paras.cell(r, pid).value) == norm_name(code)
            ),
            None,
        )
        if target_row is None:
            return f"{code} is not a parastatal of {city_name} in the register."
        ws, column = paras, _column(paras, ALIASES)
        if column is None:
            column = paras.max_column + 1
            _add_header(paras, column)
    names = [n.strip() for n in _text(ws.cell(target_row, column).value).split(",") if n.strip()]
    if any(norm_name(n) == norm_name(alias) for n in names):
        return None  # already there
    copy = backup(path)
    ws.cell(target_row, column).value = ", ".join([*names, _text(alias)])
    partial = path.with_name(f".{path.name}.writing")
    wb.save(partial)
    partial.replace(path)
    after, issues = load_register(path)
    if len(issues) > errors_before or set(after) != set(before):
        shutil.copyfile(copy, path)  # it does not load as before: put the copy back
        return "The register could not be updated safely, so it was left as it was."
    return None


def _add_header(ws, column: int) -> None:
    from copy import copy

    ws.cell(1, column).value = ALIASES
    previous = ws.cell(1, column - 1)
    ws.cell(1, column)._style = copy(previous._style)
    ws.column_dimensions[get_column_letter(column)].width = 30


def names_to_add(settings) -> list[dict]:
    """What to add to the register by hand, from the decisions saved with the uploads."""
    register, _ = load_register(settings.city_register)
    by_slug = {c.slug: c for c in register.values()}
    rows = []
    for d in remembered_decisions(settings).values():
        row = _row_for(settings, register, by_slug, d)
        if row:
            rows.append(row)
    return sorted(rows, key=lambda r: (r["what_to_add"], r["city"], r["name_in_file"]))


def _row_for(settings, register, by_slug, d: Decision) -> dict | None:
    from asics_agent.scoring.compare_run import city_units

    base = {
        "name_in_file": d.as_written,
        "city": d.as_written if d.kind == "city" else d.city_as_written,
        "register_name": "",
        "parastatal_id": "",
        "type": d.type,
        "state": d.state,
        "ulg": d.ulg,
        "decided_by": d.decided_by,
        "decided_at": d.decided_at,
        "submission": d.submission_id,
    }
    if d.action == "new":
        if d.kind == "city":
            if match_city(register, d.as_written).kind in ("exact", "alias"):
                return None  # the register has it now
            return {**base, "what_to_add": "New city"}
        city = match_city(register, d.city_as_written)
        if city.kind in ("exact", "alias"):
            units = city_units(settings, by_slug[city.slug])[0]
            if match_unit(units, d.parastatal_code or d.as_written).kind in ("exact", "alias"):
                return None
        return {
            **base,
            "what_to_add": "New parastatal",
            "parastatal_id": d.parastatal_code or d.as_written,
        }
    if d.action == "map" and not d.other_name_in_register:
        city = by_slug.get(d.city_slug)
        if d.kind == "city":
            if city is None or match_city(register, d.as_written).kind in ("exact", "alias"):
                return None
            return {**base, "what_to_add": "Other name for a city", "register_name": city.name}
        parent = match_city(register, d.city_as_written)
        host = by_slug.get(parent.slug) if parent.kind in ("exact", "alias") else None
        if host is None:
            return None
        units = city_units(settings, host)[0]
        if match_unit(units, d.as_written).kind in ("exact", "alias"):
            return None
        return {
            **base,
            "what_to_add": "Other name for a parastatal",
            "city": host.name,
            "register_name": d.parastatal_code,
            "parastatal_id": d.parastatal_code,
        }
    return None


CSV_COLUMNS = [
    "what_to_add",
    "name_in_file",
    "city",
    "register_name",
    "parastatal_id",
    "type",
    "state",
    "ulg",
    "decided_by",
    "decided_at",
    "submission",
]


def names_csv(rows: list[dict]) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()
