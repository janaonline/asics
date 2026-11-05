"""Builds a question bank file from the team's question workbook.

The workbook has one sheet per section (UPD, SC, DPG). Sheets are found by name and columns by
their header text, never by position, so a new column, a moved column or a new question needs no
code change. Whatever the builder does not understand is listed and skipped, never guessed.
The bank file it writes is in the layout `question_bank.load_question_bank` reads, plus a
"Bank Info" sheet (see bank_version.py).
"""

import difflib
import hashlib
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from openpyxl.worksheet.worksheet import Worksheet

from asics_agent.applicability import get_rules, match_rule
from asics_agent.bank_version import INFO_SHEET
from asics_agent.models import Parastatal, Question
from asics_agent.parastatal_types import PARASTATAL_TYPES, canonical_type, known_type

DEFAULT_SECTIONS = ("UPD", "SC", "DPG")  # the sheets that hold questions today (a setting)
BANK_SHEET = "Question Bank"
# A question code and nothing else: "UPD 1a", "SC-6b", "DPG5a", "DPG 5d " (not "DPG 3 - BDA")
CODE = re.compile(r"^\s*([A-Za-z]{2,6})[\s\-]*(\d+)\s*([A-Za-z]?)\s*$")
# Our column -> the names a source sheet may give it (first match wins; matched ignoring
# capitals, spaces and punctuation)
ALIASES = {
    "code": ["City-Systems Pillar", "Question Code", "Question ID", "Q No", "Code"],
    "question": ["Question", "Question Text"],
    "tag": ["Tag", "MQ_SQ", "MQ/SQ"],
    "max": ["Score / Max Score", "Max Score", "Max", "Maximum Score"],
    "level": ["Assessment Level", "Assessment level"],
    "unit": ["Unit of Assessment", "Unit"],
    "applicability": ["Applicability"],
    "methodology": ["Detailed Methodology", "Methodology"],
    "evidence": ["Evidence / Source Requirement", "Evidence", "Evidence / Source"],
    "slno": ["Sl. No.", "S_No", "Sl No", "S No"],
    "origin": ["Origin"],
    "rationale": ["Rationale"],
}
# What the bank file calls each (the names the loader requires)
BANK_HEADERS = {
    "slno": "Sl. No.",
    "code": "City-Systems Pillar",
    "question": "Question",
    "tag": "Tag",
    "max": "Score / Max Score",
    "level": "Assessment Level",
    "unit": "Unit of Assessment",
    "applicability": "Applicability",
    "methodology": "Detailed Methodology",
    "evidence": "Evidence / Source Requirement",
    "origin": "Origin",
    "rationale": "Rationale",
}
# Columns the team's scorers fill in; they are not part of the question bank
SCORER_COLUMNS = [
    "Chapter",
    "Provision",
    "Clause",
    "Page Number",
    "Score",
    "Scorer Comments (Why the score was given)",
    "Additional Comments",
    "Source Link",
]
IGNORED_SHEET_HINTS = ("DNU", "SUMMARY", "FINAL SCORING", "PILOT")


def _key(text) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text or "").casefold())


def _text(value) -> str:
    return "" if value is None else str(value).strip()


@dataclass
class SheetReport:
    sheet: str
    questions: int = 0
    data_rows: int = 0  # rows like "DPG 3 - BDA": scoring rows for one parastatal, not questions
    notes: list[str] = field(default_factory=list)
    not_copied: list[str] = field(default_factory=list)  # source columns left out


@dataclass
class BuildReport:
    source: Path
    sheets: list[SheetReport] = field(default_factory=list)
    not_understood: list[str] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)
    rows: list[tuple[str, str, list[dict]]] = field(default_factory=list)  # (sheet, section, rows)

    @property
    def count(self) -> int:
        return sum(len(rows) for _, _, rows in self.rows)


def _find_header(ws: Worksheet) -> tuple[int, dict[str, int]] | None:
    """The header row (searched in the first rows) and {our field: column index}."""
    for r, row in enumerate(ws.iter_rows(min_row=1, max_row=15, values_only=True), start=1):
        keys = {_key(v): i for i, v in enumerate(row) if v is not None}
        cols = {}
        for name, names in ALIASES.items():
            found = next((keys[_key(n)] for n in names if _key(n) in keys), None)
            if found is not None:
                cols[name] = found
        if "code" in cols and "question" in cols:
            return r, cols
    return None


def _looks_like_questions(ws: Worksheet) -> bool:
    return _find_header(ws) is not None


def read_source(source: Path, sections=DEFAULT_SECTIONS) -> BuildReport:
    """Read the question rows of the section sheets of the team's workbook."""
    report = BuildReport(source)
    wb = load_workbook(source, data_only=True)
    wanted = {s.upper(): s for s in sections}
    by_name = {ws.title.strip().upper(): ws for ws in wb.worksheets}
    for sheet_code in wanted:
        if sheet_code not in by_name:
            report.not_understood.append(
                f'There is no sheet named "{wanted[sheet_code]}" in {source.name}; '
                "its questions are not in the bank."
            )
    for ws in wb.worksheets:
        name = ws.title.strip()
        if name.upper() not in wanted:
            if ws.sheet_state != "visible":
                report.ignored.append(f'"{name}": hidden sheet, not read.')
            elif any(h in name.upper() for h in IGNORED_SHEET_HINTS):
                report.ignored.append(f'"{name}": not a question sheet (by its name), not read.')
            elif _looks_like_questions(ws):
                report.not_understood.append(
                    f'Sheet "{name}" has question columns but is not one of the sections '
                    f"({', '.join(sections)}); not read. Add it to the section list to include it."
                )
            else:
                report.ignored.append(f'"{name}": not a question sheet, not read.')
            continue
        rep = SheetReport(name)
        report.sheets.append(rep)
        found = _find_header(ws)
        if found is None:
            report.not_understood.append(
                f'Sheet "{name}": no header row with the question code and Question columns.'
            )
            continue
        header_row, cols = found
        headers = [
            _text(c)
            for c in next(ws.iter_rows(min_row=header_row, max_row=header_row, values_only=True))
        ]
        used = {i for i in cols.values()}
        for i, h in enumerate(headers):
            if h and i not in used:
                rep.not_copied.append(h)
        section_name, rows, seen = "", [], {}
        for r, row in enumerate(
            ws.iter_rows(min_row=header_row + 1, values_only=True), start=header_row + 1
        ):

            def get(field, row=row, cols=cols):
                i = cols.get(field)
                return row[i] if i is not None and i < len(row) else None

            raw = _text(get("code"))
            text = _text(get("question"))
            if not raw and not text:
                if not section_name and any(row):  # a section title row, e.g. "...(UPD)"
                    section_name = next((_text(v) for v in row if _text(v)), "")
                continue
            match = CODE.match(raw)
            if not match:
                if text:
                    report.not_understood.append(
                        f'Sheet "{name}" row {r}: has question text but the code "{raw}" is not '
                        "a question code, so it was not copied."
                    )
                elif raw:
                    if not section_name and re.fullmatch(r"[A-Za-z]{2,6}", raw):
                        # the pillar row ("SC", "UPD"): its first cell may name the section
                        title = _text(row[0])
                        section_name = title if title and title != raw else section_name
                    else:
                        rep.data_rows += 1
                continue
            if not text:
                rep.data_rows += 1  # "DPG 5c" repeated without text: a parastatal's row
                continue
            if raw in seen:
                report.not_understood.append(
                    f'Sheet "{name}" row {r}: the code "{raw}" is used again (first on row '
                    f"{seen[raw]}); the second was not copied."
                )
                continue
            seen[raw] = r
            tag = _text(get("tag")).upper()
            if tag not in ("MQ", "SQ", ""):
                rep.notes.append(f'{raw}: the Tag is "{tag}" (not MQ or SQ); copied as it is.')
            if not tag:
                rep.notes.append(
                    f"{raw}: no Tag in the source (the loader works it out from the code)."
                )
            if _text(get("unit")).upper() in ("MQ", "SQ"):
                rep.notes.append(
                    f'{raw}: the Unit of Assessment says "{_text(get("unit"))}", which looks like a Tag; copied as it is.'
                )
            if get("max") in (None, ""):
                rep.notes.append(f"{raw}: no max score in the source (it stays unscored).")
            rows.append(
                {
                    "slno": get("slno"),
                    "code": raw,
                    "question": get("question"),
                    "tag": get("tag"),
                    "max": get("max"),
                    "level": get("level"),
                    "unit": get("unit"),
                    "applicability": get("applicability"),
                    "methodology": get("methodology"),
                    "evidence": get("evidence"),
                    "origin": None,  # the source has none: never invented
                    "rationale": None,
                }
            )
            rep.questions += 1
        prefix = {CODE.match(r["code"]).group(1).upper() for r in rows}
        if prefix and prefix != {name.upper()}:
            rep.notes.append(
                f"codes start with {', '.join(sorted(prefix))}, not the sheet name {name}."
            )
        report.rows.append((name, section_name or name, rows))
    return report


def write_bank(
    report: BuildReport,
    path: Path,
    digest: str = "",
    sha: str = "",
    names: dict[str, str] | None = None,
) -> Path:
    """Write the bank file: a "Question Bank" sheet the loader reads, and a "Bank Info" sheet."""
    wb = Workbook()
    ws = wb.active
    ws.title = BANK_SHEET
    ws.append([BANK_HEADERS[f] for f in BANK_HEADERS])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    sheet_names = [sheet for sheet, _, _ in report.rows]
    for code, section, rows in report.rows:
        if section.strip().upper() == code.upper() and names and names.get(code.upper()):
            section = names[code.upper()]  # the source doesn't name the section: keep the old name
        has_code = re.search(rf"\({re.escape(code.upper())}\)", section)
        title = section if has_code else f"{section} ({code.upper()})"
        ws.append([title])
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True)
        for row in rows:
            ws.append([row[f] for f in BANK_HEADERS])
    info = wb.create_sheet(INFO_SHEET)
    info.append(["Source file", report.source.name])
    info.append(["Source SHA-256", sha])
    info.append(["Built at", date.today().isoformat()])
    info.append(["Built by", "scripts/build_question_bank.py"])
    info.append(["Sections", ", ".join(sheet_names)])
    info.append(["Questions", report.count])
    info.append(["Content hash", digest])
    info.column_dimensions["A"].width = 18
    info.column_dimensions["B"].width = 80
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# -- what changed against the previous bank ----------------------------------------------------
@dataclass
class BankDiff:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    text_changed: list[str] = field(default_factory=list)
    different_question: list[str] = field(default_factory=list)  # text changed a lot
    max_changed: list[tuple[str, object, object]] = field(default_factory=list)
    applicability_changed: list[tuple[str, str, str]] = field(default_factory=list)
    tag_changed: list[tuple[str, str, str]] = field(default_factory=list)
    other_changed: list[str] = field(default_factory=list)  # methodology/evidence/level/unit


def diff_banks(old: dict[str, Question], new: dict[str, Question]) -> BankDiff:
    d = BankDiff()
    d.added = sorted(set(new) - set(old))
    d.removed = sorted(set(old) - set(new))
    for code in sorted(set(old) & set(new)):
        a, b = old[code], new[code]
        if a.text != b.text:
            d.text_changed.append(code)
            if difflib.SequenceMatcher(None, a.text.lower(), b.text.lower()).ratio() < 0.5:
                d.different_question.append(code)
        if a.max_score != b.max_score:
            d.max_changed.append((code, a.max_score, b.max_score))
        if a.applicability.strip() != b.applicability.strip():
            d.applicability_changed.append((code, a.applicability, b.applicability))
        if a.tag != b.tag:
            d.tag_changed.append((code, a.tag, b.tag))
        if (a.methodology, a.evidence_requirement, a.assessment_level, a.unit) != (
            b.methodology,
            b.evidence_requirement,
            b.assessment_level,
            b.unit,
        ):
            d.other_changed.append(code)
    return d


# -- who each question applies to --------------------------------------------------------------
def applicability_table(questions: dict[str, Question]) -> list[dict]:
    """One row per question: 'Y'/'N' for each parastatal type, or 'if <flag>' for a question that
    depends on a Yes/No flag; None when the wording is not recognised."""
    rows = []
    for q in questions.values():
        rule = match_rule(q.applicability, q.id)
        row = {"code": q.id, "applicability": q.applicability.strip(), "rule": None, "types": {}}
        if rule is not None:
            row["rule"] = rule.describe() + (" (assumed, please confirm)" if rule.confirm else "")
        for t in PARASTATAL_TYPES:
            if rule is None:
                row["types"][t.code] = "?"
            elif rule.kind == "flag":
                row["types"][t.code] = f"if {rule.value}"
            else:
                person = Parastatal(id="X", name="X", type=t.code)
                row["types"][t.code] = "Y" if rule.test(person) else "N"
        rows.append(row)
    return rows


def read_template_index(path: Path) -> dict[str, dict[str, str]]:
    """{question code: {type code: 'Y'|'N'}} from a template's Question_Index sheet.

    The sheet is found by name, its header row by the "Question Code" text, and a type column by a
    header that names a parastatal type (new or old name)."""
    wb = load_workbook(path, read_only=True, data_only=True)
    name = next((n for n in wb.sheetnames if _key(n) == "questionindex"), None)
    if name is None:
        return {}
    rows = list(wb[name].iter_rows(values_only=True))
    header_at = next(
        (i for i, r in enumerate(rows[:20]) if any(_key(c) == "questioncode" for c in r)), None
    )
    if header_at is None:
        return {}
    header = rows[header_at]
    code_col = next(i for i, c in enumerate(header) if _key(c) == "questioncode")
    type_cols = {
        i: canonical_type(_text(c))
        for i, c in enumerate(header)
        if _text(c)
        and known_type(_text(c))
        and canonical_type(_text(c)) in {t.code for t in PARASTATAL_TYPES}
    }
    out = {}
    for row in rows[header_at + 1 :]:
        code = _text(row[code_col]) if code_col < len(row) else ""
        m = CODE.match(code)
        if not m:
            continue
        key = f"{m.group(1).upper()} {m.group(2)}{m.group(3).lower()}"
        out[key] = {t: _text(row[i]).upper() for i, t in type_cols.items() if i < len(row)}
    return out


def compare_with_templates(
    questions: dict[str, Question], templates: list[Path]
) -> tuple[list[str], list[str]]:
    """Lines listing every difference between the rules and the templates' Question_Index, and
    notes about what could not be compared."""
    differences, notes = [], []
    table = {r["code"]: r for r in applicability_table(questions)}
    for path in templates:
        try:
            index = read_template_index(path)
        except Exception as e:
            notes.append(f"{path.name}: could not be read ({e}).")
            continue
        if not index:
            notes.append(f"{path.name}: no Question_Index sheet found.")
            continue
        types = sorted({t for v in index.values() for t in v})
        missing = [t.code for t in PARASTATAL_TYPES if t.code not in types]
        if missing:
            notes.append(f"{path.name}: has no column for {', '.join(missing)}; not compared.")
        for code, flags in index.items():
            row = table.get(code)
            if row is None:
                differences.append(f"{path.name}: {code} is in the template but not in the bank.")
                continue
            for t, template_says in flags.items():
                ours = row["types"].get(t)
                if ours == template_says:
                    continue
                differences.append(
                    f"{path.name}: {code} for {t}: rules say {ours}"
                    + (f" ({row['rule']})" if ours and ours.startswith("if ") else "")
                    + f", template says {template_says}."
                )
        for code in sorted(set(table) - set(index)):
            if code.split(" ")[0] == next(iter(index)).split(" ")[0]:
                differences.append(f"{path.name}: {code} is in the bank but not in the template.")
    return differences, notes


def unrecognised_applicability(questions: dict[str, Question]) -> list[str]:
    return [
        f'{q.raw_id}: "{q.applicability.strip()}"'
        for q in questions.values()
        if match_rule(q.applicability, q.id) is None
    ] + [f"(rules file) {p}" for p in get_rules().problems]
