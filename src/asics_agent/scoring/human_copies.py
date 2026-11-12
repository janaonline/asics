"""Intern copies of the team's templates, for a category scored in them (Parastatal).

The assignments workbook is the same as for the older categories: its Assignments sheet has one
row per intern and set of questions (Category | Intern | Questions | Cities | Notes), with the
category's code (PARASTATAL) in the Category column. Questions are codes or patterns ("UPD*",
"SC 1", "DPG 5*"); cities are names or "All". An intern's copy is a copy of the section's template
with the rows for the cities Step 2 has answered (every parastatal, every applicable question)
added and the assigned ones marked in yellow, plus a "Step 2 evidence" sheet with the citation
for each row. An existing copy is never replaced. The intern fills it in, saves it as .xlsx, and
the team uploads it (Step 3 > People's scoring); copies are not read back from this folder.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

from asics_agent.applicability import applies_to
from asics_agent.categories import ULG_UNIT_ID, load_bank
from asics_agent.cities import load_register
from asics_agent.legacy_names import sheet_name
from asics_agent.models import Parastatal
from asics_agent.parastatal_types import ULG_TYPE, type_label
from asics_agent.scoring import human
from asics_agent.scoring.phase2 import bank_ids, load_evidence, phase2_status
from asics_agent.scoring.submissions import copies_dir, section_templates
from asics_agent.scoring.template_fill import AITemplate

MINE = PatternFill("solid", fgColor="FFF6D5")
HEAD = PatternFill("solid", fgColor="DDE7F0")


@dataclass
class TemplateAssignment:
    intern: str
    patterns: list[str]
    cities: list[str]  # the register's names
    row: int


@dataclass
class CopyReport:
    done: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    files: list[Path] = field(default_factory=list)


def read_template_assignments(path: Path, scoring_code: str, register) -> tuple[list, list[str]]:
    """The Assignments rows for `scoring_code`, read tolerantly (renamed sheets and columns)."""
    problems: list[str] = []
    wb = load_workbook(path, data_only=True)
    name = sheet_name(wb.sheetnames, human.ASSIGNMENTS_SHEET)
    if name not in wb.sheetnames:
        return [], [f'The assignments workbook has no "{human.ASSIGNMENTS_SHEET}" sheet.']
    names = {}
    for city in register.values():
        for n in [city.name, *city.aliases]:
            names[human._key(n)] = city.name
    found = []
    for r, v in human._sheet_rows(wb[name], human.ASSIGNMENT_COLUMNS, problems):
        if v["Category"].upper() != scoring_code.upper():
            continue
        where = f"Assignments sheet, row {r}"
        if not v["Intern"]:
            problems.append(f"{where}: add the intern's name.")
            continue
        wanted = human._split(v["Cities"])
        if not wanted or [w.lower() for w in wanted] == ["all"]:
            cities = sorted({c.name for c in register.values()})
        else:
            cities = []
            for c in wanted:
                if human._key(c) in names:
                    cities.append(names[human._key(c)])
                else:
                    problems.append(f'{where}: the city "{c}" is not in the city register.')
        found.append(
            TemplateAssignment(v["Intern"], human._split(v["Questions"]) or ["*"], cities, r)
        )
    return found, problems


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_") or "intern"


def prepare_copies(settings) -> CopyReport:
    """Make every assigned intern's copy of each section's template. Existing copies stay."""
    from asics_agent.scoring.workflow import assignments_path

    report = CopyReport()
    register, _ = load_register(settings.city_register)
    templates = section_templates(settings)
    assignments, problems = read_template_assignments(
        assignments_path(settings), settings.scoring_code, register
    )
    report.problems += problems
    if not assignments:
        report.problems.append(
            f"No rows for {settings.scoring_code} on the Assignments sheet: add who scores which "
            "questions for which cities."
        )
        return report
    bank, _ = load_bank(settings)
    by_name = {c.name: c for c in register.values()}
    ready: dict[str, object] = {}
    for a in assignments:
        for city in a.cities:
            if city in ready:
                continue
            status = phase2_status(settings, city)
            if status.ready:
                ready[city] = load_evidence(status, bank_ids(settings))
            else:
                report.problems.append(f"{city} left out of the copies: {status.reason}")
    by_intern: dict[str, list[TemplateAssignment]] = {}
    for a in assignments:
        by_intern.setdefault(a.intern, []).append(a)
    for intern, items in by_intern.items():
        for section, template in templates.items():
            _copy(settings, report, intern, items, section, template, ready, by_name, bank)
    return report


def _units(settings, evidence, city) -> dict[str, Parastatal]:
    if settings.unit == "ulg":
        return {
            ULG_UNIT_ID: next(iter(evidence.parastatals.values()), None)
            or Parastatal(id=ULG_UNIT_ID, name=city.ulg or city.name, type=ULG_TYPE)
        }
    return evidence.parastatals


def _copy(settings, report, intern, items, section, template, ready, by_name, bank) -> None:
    path = copies_dir(settings, section) / f"{_slug(intern)}.xlsx"
    if path.exists():
        report.done.append(f"{intern} already has a {section} copy; left as it is.")
        return
    ai = AITemplate(path, template)
    ai.config_note = f"Added for {intern} from the city register."
    codes = [
        c
        for c in ai.specs
        if any(any(human._code_matches(c, p) for p in a.patterns) for a in items)
    ]
    if not codes:
        return
    mine: dict[str, list[str]] = {}
    evidence_rows = []
    for a in items:
        for city in a.cities:
            found = ready.get(city)
            if found is None:
                continue
            for unit_id, parastatal in _units(settings, found, by_name[city]).items():
                who = "" if settings.unit == "ulg" else parastatal.id
                if settings.unit != "ulg":
                    report.problems += [
                        p
                        for p in ai.ensure_unit(
                            city,
                            who,
                            type_label(parastatal.type) if parastatal.type != ULG_TYPE else "",
                        )
                        if p not in report.problems
                    ]
                for code in codes:
                    if not any(human._code_matches(code, p) for p in a.patterns):
                        continue
                    question = bank.get(code)
                    if question is not None and applies_to(question, parastatal) is False:
                        continue
                    types = ai.applicable_types(code)
                    if (
                        settings.unit != "ulg"
                        and types is not None
                        and parastatal.type not in types
                    ):
                        continue
                    row = ai.ensure_row(code, city, who)
                    spec = ai.specs[code]
                    ai.wb[spec.sheet].cell(row, spec.column_for("city")).fill = MINE
                    mine.setdefault(code, []).append(f"{city} / {who or 'ULG'}")
                    answer = found.answers.get((unit_id, re.sub(r"[\s\-]", "", code)))
                    if answer is not None:
                        source = next(
                            (c for c in found.citations if c.citation_id == answer.citation_id),
                            None,
                        )
                        evidence_rows.append(
                            {
                                "Question": code,
                                "City": city,
                                "Parastatal": who or "ULG",
                                "Step 2 status": answer.status,
                                "Citation ID": answer.citation_id,
                                "Source": source.title if source else "",
                                "Link": source.url if source else "",
                                "Quote": answer.evidence,
                                "Step 2 answer": answer.answer[:1500],
                                "Source needed": "" if answer.citation_id else answer.source_needed,
                            }
                        )
    if not mine:
        return
    _add_sheets(ai.wb, intern, section, mine, evidence_rows)
    saved = ai.save(settings.scoring_dir / ".cache", None)
    report.problems += saved.problems
    report.files.append(path)
    report.done.append(f"Made {path.name} for {intern} ({section}).")


def _add_sheets(wb, intern: str, section: str, mine: dict, evidence_rows: list[dict]) -> None:
    ws = wb.create_sheet("Your assignment")
    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 90
    ws.append([f"{intern}: your {section} questions"])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append(
        [
            "Fill in only the rows whose City cell is yellow on each question sheet: what each "
            "column asks for, the evidence (document, provision, page, link) and your comments. "
            "Don't change formulas. Save as .xlsx and send it to the team to upload."
        ]
    )
    ws["A2"].alignment = Alignment(wrap_text=True)
    ws.append([])
    ws.append(["Question", "Rows to score"])
    for cell in ws[4]:
        cell.font, cell.fill = Font(bold=True), HEAD
    for code, rows in mine.items():
        ws.append([code, ", ".join(rows)])
        ws.cell(ws.max_row, 2).alignment = Alignment(wrap_text=True)
    if not evidence_rows:
        return
    ev = wb.create_sheet("Step 2 evidence")
    ev.append(
        [
            "Score from these Step 2 citations (the reviewed Citation Sheet). If one doesn't "
            "support the answer, say so in the comments."
        ]
    )
    ev["A1"].font = Font(bold=True)
    columns = list(evidence_rows[0])
    ev.append(columns)
    for cell in ev[2]:
        cell.font, cell.fill = Font(bold=True), HEAD
        ev.column_dimensions[cell.column_letter].width = 22
    for row in evidence_rows:
        ev.append([row.get(c, "") for c in columns])
        if row.get("Link"):
            ev.cell(ev.max_row, columns.index("Link") + 1).hyperlink = row["Link"]
    for name in ("Quote", "Step 2 answer"):
        ev.column_dimensions[ev.cell(2, columns.index(name) + 1).column_letter].width = 70
    ev.freeze_panes = "C3"


def replace_assignments(settings, data: bytes, name: str) -> str | None:
    """Replace the assignments workbook with an edited copy; the old one is kept in
    assignments/history. Returns why it was refused, or None."""
    import io
    import shutil
    from datetime import datetime

    from asics_agent.scoring.submissions import unsafe_reasons
    from asics_agent.scoring.workflow import assignments_path

    if why := unsafe_reasons(name, data):
        return why[0]
    try:
        wb = load_workbook(io.BytesIO(data), data_only=True)
    except Exception as exc:
        return f"The workbook could not be opened ({type(exc).__name__})."
    problems: list[str] = []
    found = sheet_name(wb.sheetnames, human.ASSIGNMENTS_SHEET)
    if found not in wb.sheetnames:
        return (
            f'It has no "{human.ASSIGNMENTS_SHEET}" sheet, so it is not the assignments workbook.'
        )
    list(human._sheet_rows(wb[found], human.ASSIGNMENT_COLUMNS, problems))
    if problems:
        return problems[0]
    path = assignments_path(settings)
    history = path.parent / "history"
    history.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, history / f"{datetime.now():%Y%m%d-%H%M%S}_{path.name}")
    path.write_bytes(data)
    return None
