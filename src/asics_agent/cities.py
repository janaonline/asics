"""The city register: one Excel file, maintained by the research team, listing every city
and its parastatals.

Sheets:
  * How to Fill  — instructions for the team
  * Cities       — City | State | City government (ULG) | Include in runs? | Notes
  * Parastatals  — City | Parastatal ID | Parastatal name | Type | four Yes/No questions
                   that decide which questions apply | Include in runs? | Notes

Problems are reported as plain-language Issues. A problem in one city never blocks
another city: each Issue carries the city it belongs to in `ref`.
"""

import re
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from asics_agent.models import CityConfig, Issue, Parastatal

CITIES_SHEET, PARASTATALS_SHEET, GUIDE_SHEET = "Cities", "Parastatals", "How to Fill"

CITY_COLUMNS = ["City", "State", "City government (ULG)", "Include in runs?", "Notes"]
PARASTATAL_COLUMNS = [
    "City",
    "Parastatal ID",
    "Parastatal name",
    "Type",
    "Raises its own revenue?",
    "Does capital works / builds infrastructure?",
    "Has an annual budget?",
    "Has a chief executive post?",
    "Include in runs?",
    "Notes",
]
TYPES = {
    "Water supply board": "water_supply_board",
    "Transport corporation": "transport_corporation",
    "Development authority": "development_authority",
    "Other": "other",
}
TYPE_LABELS = {v: k for k, v in TYPES.items()}
# Yes/No column -> (Parastatal field, value assumed when the cell is left blank)
FLAGS = {
    "Raises its own revenue?": ("revenue_raising", False),
    "Does capital works / builds infrastructure?": ("capex_mandate", False),
    "Has an annual budget?": ("has_annual_budget", True),
    "Has a chief executive post?": ("has_chief_executive", True),
}
YES, NO = {"yes", "y", "true", "1"}, {"no", "n", "false", "0"}

GUIDE = [
    ("How to fill in this register", ""),
    ("", ""),
    (
        "Cities sheet",
        'One row per city. "City government (ULG)" is the name of the city\'s '
        'municipal body. Set "Include in runs?" to No to hide a city from the app without '
        "deleting it.",
    ),
    (
        "Parastatals sheet",
        "OPTIONAL. The agent finds each city's parastatals by itself. Add a row here only "
        "for a parastatal you want to be sure is included; choose the City from the dropdown "
        "(it must match a row on the Cities sheet). Review and change the full list in each "
        "city's Sources workbook after Step 1.",
    ),
    (
        "Parastatal ID",
        "A short code, unique within the city, e.g. BWSSB. It is used in file "
        "names and in the workbook, so avoid spaces.",
    ),
    (
        "Type",
        "Water supply board, Transport corporation, Development authority, or Other. "
        "The type decides which questions apply. Use Other for any other kind of parastatal (e.g. "
        "metro rail, housing board); only the common questions will apply to it.",
    ),
    (
        "The four Yes/No questions",
        "They decide which of the State Capacities questions apply. "
        "If you leave one blank, the app assumes No for revenue and capital works, and Yes for "
        "annual budget and chief executive, and tells you so.",
    ),
    (
        "Websites",
        "Do NOT add website links. The tool must find every link itself during the "
        "run, so that each link can be checked.",
    ),
    (
        "After editing",
        "Save and close the file. The app picks up the changes next time you "
        'open the Start page, and shows any problems on the "Cities & parastatals" page.',
    ),
]

_HEADER = PatternFill("solid", fgColor="DDE7F0")


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def _issue(severity: str, message: str, city: str | None = None) -> Issue:
    return Issue(
        phase="initial_checks", severity=severity, message=message, ref=city, audience="team"
    )


def _rows(ws, columns: list[str], issues: list[Issue]) -> list[tuple[int, dict[str, str]]]:
    header = [_text(c.value) for c in ws[1]]
    missing = [c for c in columns if c not in header]
    if missing:
        issues.append(
            _issue(
                "error",
                f"The {ws.title} sheet is missing these columns: "
                f"{', '.join(missing)}. Put them back with the same names.",
            )
        )
        return []
    index = {name: header.index(name) for name in columns}
    rows = []
    for row_no, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        values = {name: _text(row[i]) if i < len(row) else "" for name, i in index.items()}
        if any(values.values()):
            rows.append((row_no, values))
    return rows


def _yes_no(value: str, default: bool, where: str, city: str, issues: list[Issue]) -> bool:
    lowered = value.lower()
    if lowered in YES:
        return True
    if lowered in NO:
        return False
    if value:
        issues.append(
            _issue(
                "warning",
                f'{where}: "{value}" should be Yes or No. We used {"Yes" if default else "No"}.',
                city,
            )
        )
    else:
        issues.append(
            _issue(
                "info", f"{where} was left blank, so we assumed {'Yes' if default else 'No'}.", city
            )
        )
    return default


def load_register(path: Path) -> tuple[dict[str, CityConfig], list[Issue]]:
    """Return ({city slug: config} for included cities, issues)."""
    issues: list[Issue] = []
    if not path.exists():
        return {}, [_issue("error", f"The city register couldn't be found at {path}.")]
    wb = load_workbook(path, data_only=True)
    for sheet in (CITIES_SHEET, PARASTATALS_SHEET):
        if sheet not in wb.sheetnames:
            issues.append(_issue("error", f'The city register has no "{sheet}" sheet.'))
    if issues:
        return {}, issues

    cities: dict[str, dict] = {}
    for row_no, v in _rows(wb[CITIES_SHEET], CITY_COLUMNS, issues):
        name = v["City"]
        where = f"Cities sheet, row {row_no}"
        if not name:
            issues.append(_issue("error", f"{where}: the City name is empty."))
            continue
        if slugify(name) in cities:
            issues.append(_issue("error", f"{where}: {name} is listed twice. Keep one row.", name))
            continue
        for field in ("State", "City government (ULG)"):
            if not v[field]:
                issues.append(_issue("warning", f"{where}: {name} has no {field}.", name))
        include = _yes_no(v["Include in runs?"], True, f"{where} (Include in runs?)", name, [])
        cities[slugify(name)] = {
            "name": name,
            "state": v["State"],
            "ulg": v["City government (ULG)"],
            "include": include,
            "parastatals": [],
        }

    for row_no, v in _rows(wb[PARASTATALS_SHEET], PARASTATAL_COLUMNS, issues):
        where = f"Parastatals sheet, row {row_no}"
        city = cities.get(slugify(v["City"]))
        if city is None:
            issues.append(
                _issue(
                    "error",
                    f'{where}: the city "{v["City"]}" isn\'t on the '
                    "Cities sheet. Add it there, or fix the spelling.",
                )
            )
            continue
        name = city["name"]
        if not _yes_no(v["Include in runs?"], True, where, name, []):
            continue
        pid = re.sub(r"\s+", "", v["Parastatal ID"]).upper()
        if not pid or not v["Parastatal name"]:
            issues.append(
                _issue("error", f"{where}: every parastatal needs an ID and a name.", name)
            )
            continue
        if any(p.id == pid for p in city["parastatals"]):
            issues.append(
                _issue(
                    "error",
                    f"{where}: {name} already has a parastatal with the "
                    f"ID {pid}. IDs must be unique within a city.",
                    name,
                )
            )
            continue
        kind = next(
            (code for label, code in TYPES.items() if label.lower() == v["Type"].lower()), None
        )
        if kind is None:
            issues.append(
                _issue(
                    "error", f"{where}: the Type of {pid} must be one of: {', '.join(TYPES)}.", name
                )
            )
            continue
        flags = {
            field: _yes_no(v[column], default, f'{where}, {pid}: "{column}"', name, issues)
            for column, (field, default) in FLAGS.items()
        }
        city["parastatals"].append(
            Parastatal(id=pid, name=v["Parastatal name"], type=kind, notes=v["Notes"], **flags)
        )

    configs = {}
    for slug, city in cities.items():
        if not city["include"]:
            continue
        configs[slug] = CityConfig(
            slug=slug,
            name=city["name"],
            state=city["state"],
            ulg=city["ulg"],
            parastatals=city["parastatals"],
        )
    return configs, issues


def issues_for_city(issues: list[Issue], city_name: str) -> list[Issue]:
    """Register problems that affect this city: its own, plus register-wide ones."""
    return [i for i in issues if i.ref in (None, city_name)]


def write_register(path: Path, cities: list[CityConfig], city_notes: dict[str, str] | None = None):
    """Create a register file (used to make the template and for practice runs)."""
    wb = Workbook()
    guide = wb.active
    guide.title = GUIDE_SHEET
    guide.column_dimensions["A"].width = 28
    guide.column_dimensions["B"].width = 100
    for row in GUIDE:
        guide.append(list(row))
    guide["A1"].font = Font(bold=True, size=14)
    for r in range(3, guide.max_row + 1):
        guide.cell(row=r, column=1).font = Font(bold=True)
        guide.cell(row=r, column=2).alignment = Alignment(wrap_text=True, vertical="top")

    def sheet(title, columns, widths):
        ws = wb.create_sheet(title)
        ws.append(columns)
        for cell in ws[1]:
            cell.font, cell.fill = Font(bold=True), _HEADER
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            ws.column_dimensions[cell.column_letter].width = widths.get(cell.value, 18)
        ws.freeze_panes = "A2"
        return ws

    def dropdown(ws, column: int, formula: str, prompt: str):
        letter = ws.cell(row=1, column=column).column_letter
        validation = DataValidation(type="list", formula1=formula, allow_blank=True)
        validation.prompt, validation.error = prompt, prompt
        validation.showErrorMessage = True
        ws.add_data_validation(validation)
        validation.add(f"{letter}2:{letter}500")

    cities_ws = sheet(
        CITIES_SHEET,
        CITY_COLUMNS,
        {"City": 20, "State": 18, "City government (ULG)": 45, "Notes": 50},
    )
    for city in cities:
        cities_ws.append(
            [city.name, city.state, city.ulg, "Yes", (city_notes or {}).get(city.name, "")]
        )
    dropdown(cities_ws, 4, '"Yes,No"', "Choose Yes or No")

    ws = sheet(
        PARASTATALS_SHEET,
        PARASTATAL_COLUMNS,
        {"City": 18, "Parastatal ID": 14, "Parastatal name": 45, "Type": 24, "Notes": 50},
    )
    for city in cities:
        for p in city.parastatals:
            ws.append(
                [
                    city.name,
                    p.id,
                    p.name,
                    TYPE_LABELS[p.type],
                    *["Yes" if getattr(p, field) else "No" for field, _ in FLAGS.values()],
                    "Yes",
                    p.notes,
                ]
            )
    dropdown(ws, 1, f"'{CITIES_SHEET}'!$A$2:$A$200", "Choose a city from the Cities sheet")
    dropdown(ws, 4, f'"{",".join(TYPES)}"', "Choose a type")
    for column in range(5, 10):
        dropdown(ws, column, '"Yes,No"', "Choose Yes or No")

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path
