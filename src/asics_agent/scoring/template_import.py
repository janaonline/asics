"""Reads a filled-in scoring template back as human scores (the Parastatal templates the
program team fills in by hand: Parastatal_UPD_Template.xlsx, _SC_ and _DPG_).

Nothing here depends on a fixed row, column letter or count. It finds things by name:

  * a question sheet is a sheet whose name (also the cell next to "Question Code") is a question
    code, and that has a header row (found by searching for the City and Score headers);
  * a column is found by its header text, with a list of accepted names per field, in any order;
  * a column it does not recognise is kept as an extra input (typed) or a calculated value
    (a formula), never dropped;
  * a sheet that is not a question sheet (Instructions, Configuration, Question_Index, summaries)
    is skipped, and a sheet it cannot classify is reported;
  * a blank score means "not scored", never zero; a formula with no saved value is reported.

One bad sheet or row never stops the rest. `TemplateRead.report` says, per sheet, what was read,
what was ignored and why, in plain language.
"""

import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from asics_agent.scoring.template import readable

# Our field -> header texts a template may use for it (matched ignoring capitals and punctuation)
ALIASES: dict[str, list[str]] = {
    "city": ["City"],
    "parastatal": ["Parastatal Name", "Parastatal", "Parastatal ID", "Agency", "Unit"],
    "parastatal_type": ["Parastatal Type", "Type"],
    "code": ["Question Code", "Code", "Question ID"],
    "description": ["Question Description", "Question", "Question Text"],
    "max_score": ["Max Score", "Maximum Score", "Max"],
    "score": ["Score", "Points (Auto-generate)", "Points", "Final Score"],
    "chapter": ["Chapter"],
    "provision": ["Provision"],
    "clause": ["Clause"],
    "page": ["Page Number", "Page No", "Page"],
    "comments": [
        "Scorer Comments (Why the score was given)",
        "SCORER COMMENTS",
        "Scorer Comments",
        "Comments",
    ],
    "additional_comments": ["Additional Comments"],
    "source_link": [
        "Source Link or Evidence Document",
        "Source Link",
        "Link",
        "Evidence Document",
    ],
    "latest_information": ["Latest Information (FY or Year or Date)", "Latest Information"],
    "key": ["Key"],
    "record_check": ["Record Check"],
    "scorer": ["Scorer", "Scored By", "Scorer Name", "Intern"],
    "applies": ["Applies?"],
}
# Fields stored on the row itself; every other column is an input or a calculated value
_CORE = set(ALIASES) - {"description"}
_SKIP_SHEET_WORDS = (
    "instruction",
    "configuration",
    "questionindex",
    "summary",
    "readme",
    "yourassignment",  # sheets the portal adds to an intern's copy
    "step2evidence",
)
CODE = re.compile(r"^\s*([A-Za-z]{2,6})[\s\-]*(\d+)\s*([A-Za-z]?)\s*$")
NOT_APPLICABLE = {"NA", "N/A", "NOT APPLICABLE", "-"}


def _key(text) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text or "").casefold())


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def normalise_code(raw) -> str | None:
    """'SC-6b', 'DPG5a', ' UPD 1a ' -> 'SC 6b', 'DPG 5a', 'UPD 1a'; None if it is not a code."""
    m = CODE.match(_text(raw))
    return f"{m.group(1).upper()} {m.group(2)}{m.group(3).lower()}" if m else None


@dataclass
class HumanRow:
    """One scorer's entry for one parastatal (or ULG) and one question."""

    city: str
    parastatal: str  # the short code, e.g. BWSSB
    code: str  # normalised, e.g. "DPG 5a"
    raw_code: str
    score: float | None  # None = not scored (never 0)
    score_note: str = ""  # why there is no score, or a problem with it
    max_score: float | None = None
    parastatal_type: str = ""
    inputs: dict = field(default_factory=dict)  # typed columns the reader does not know
    calculated: dict = field(default_factory=dict)  # formula columns the reader does not know
    chapter: str = ""
    provision: str = ""
    clause: str = ""
    page: str = ""
    comments: str = ""
    additional_comments: str = ""
    source_link: str = ""
    latest_information: str = ""
    record_check: str = ""
    scorer: str = ""
    file: str = ""
    sheet: str = ""
    row: int = 0


@dataclass
class QuestionMeta:
    code: str
    sheet: str
    text: str = ""
    tag: str = ""
    max_score: float | None = None
    applicability: str = ""
    header_row: int = 0
    columns: dict = field(default_factory=dict)  # field -> header text found
    extra_columns: list[str] = field(default_factory=list)  # inputs and calculated columns


@dataclass
class ConfigRow:
    city: str
    parastatal: str
    parastatal_type: str
    active: bool


@dataclass
class ImportReport:
    file: str
    sheets_read: list[str] = field(default_factory=list)
    sheets_skipped: list[tuple[str, str]] = field(default_factory=list)  # (sheet, why)
    problems: list[str] = field(default_factory=list)  # plain language, per sheet or row
    rows_read: int = 0
    rows_skipped: list[tuple[str, int, str]] = field(default_factory=list)  # (sheet, row, why)
    unknown_columns: dict[str, list[str]] = field(default_factory=dict)  # sheet -> headers kept
    counts: dict[tuple[str, str], dict[str, int]] = field(default_factory=dict)  # (city, code)

    def lines(self) -> list[str]:
        out = [
            f"{self.file}: read {len(self.sheets_read)} question sheet(s), {self.rows_read} "
            f"row(s); skipped {len(self.sheets_skipped)} sheet(s) and {len(self.rows_skipped)} row(s)."
        ]
        out += [f"Sheet {s} skipped: {why}" for s, why in self.sheets_skipped]
        out += [f"Sheet {s}, row {r} skipped: {why}" for s, r, why in self.rows_skipped]
        out += [
            f"Sheet {s}: columns kept as extra inputs: {', '.join(cols)}"
            for s, cols in self.unknown_columns.items()
        ]
        out += self.problems
        return out


@dataclass
class TemplateRead:
    path: Path
    rows: list[HumanRow] = field(default_factory=list)
    questions: dict[str, QuestionMeta] = field(default_factory=dict)
    config: list[ConfigRow] = field(default_factory=list)
    report: ImportReport = field(default_factory=lambda: ImportReport(""))


def _number(value) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(_text(value).rstrip("%"))
    except ValueError:
        return None


def _find_header(ws, wsf) -> tuple[int, dict[str, int], dict[int, str]] | None:
    """(header row, {field: column}, {column: header text}) for the question table, searching
    the whole sheet's top rows for a row that has the City and Score headers."""
    for r in range(1, min(ws.max_row, 80) + 1):
        headers = {}
        for c in range(1, ws.max_column + 1):
            v = ws.cell(r, c).value
            if v is None and wsf is not None:
                f = wsf.cell(r, c).value
                v = readable(f) if isinstance(f, str) and f.startswith('="') else None
            if _text(v):
                headers[c] = _text(v)
        keyed = {_key(h): c for c, h in headers.items()}
        cols = {}
        for name, names in ALIASES.items():
            found = next((keyed[_key(n)] for n in names if _key(n) in keyed), None)
            if found is not None and found not in cols.values():
                cols[name] = found
        if "city" in cols and ("score" in cols or "parastatal" in cols) and len(headers) >= 4:
            return r, cols, headers
    return None


def _meta(ws, code: str, header_row: int) -> QuestionMeta:
    """The question's details from the label/value cells above the table ("Question", "Tag",
    "Max Score", "Applicability (source)"), found by their labels."""
    meta = QuestionMeta(code=code, sheet=ws.title, header_row=header_row)
    for r in range(1, header_row):
        for c in range(1, ws.max_column + 1):
            label = _key(ws.cell(r, c).value)
            nxt = ws.cell(r, c + 1).value
            if label == "question" and not meta.text:
                meta.text = _text(nxt)
            elif label == "tag" and not meta.tag:
                meta.tag = _text(nxt)
            elif label == "maxscore" and meta.max_score is None:
                meta.max_score = _number(nxt)
            elif label.startswith("applicability") and not meta.applicability:
                meta.applicability = _text(nxt)
    return meta


def _question_code(ws, header_row: int) -> tuple[str | None, str | None]:
    """(code, raw) from the cell beside "Question Code" above the table, else the sheet name."""
    for r in range(1, header_row):
        for c in range(1, ws.max_column + 1):
            if _key(ws.cell(r, c).value) == "questioncode":
                raw = ws.cell(r, c + 1).value
                if normalise_code(raw):
                    return normalise_code(raw), _text(raw)
    return normalise_code(ws.title), (ws.title if normalise_code(ws.title) else None)


def _is_skipped_by_name(title: str) -> bool:
    k = _key(title)
    return any(w in k for w in _SKIP_SHEET_WORDS)


def _tables(ws):
    """[(name, table)] of a sheet's Excel tables (openpyxl keeps them as a name -> table map)."""
    return [(name, ws.tables[name]) for name in ws.tables]


def config_table(wb):
    """(sheet, table) of the table listing the parastatals: the one with City, Parastatal Type,
    Parastatal Name and Active columns, found by its headers, not its name."""
    want = {"city", "parastataltype", "parastatalname", "active"}
    for ws in wb.worksheets:
        for _, table in _tables(ws):
            if want <= {_key(c.name) for c in table.tableColumns}:
                return ws, table
    return None, None


def read_config(wb) -> list[ConfigRow]:
    """The parastatals a template lists (its Configuration table), found by its headers."""
    from openpyxl.utils import range_boundaries

    ws, table = config_table(wb)
    if table is None:
        return []
    first_col, first_row, last_col, last_row = range_boundaries(table.ref)
    cols = {_key(c.name): first_col + i for i, c in enumerate(table.tableColumns)}
    out = []
    for r in range(first_row + 1, last_row + 1):
        city = _text(ws.cell(r, cols["city"]).value)
        who = _text(ws.cell(r, cols["parastatalname"]).value)
        if not city or not who:
            continue
        kind = _text(ws.cell(r, cols["parastataltype"]).value)
        active = _text(ws.cell(r, cols["active"]).value).upper()
        out.append(ConfigRow(city, who, kind, active not in ("N", "NO", "FALSE", "0")))
    return out


def read_filled_template(path: Path, scorer: str = "") -> TemplateRead:
    """Read every question sheet of a filled template. `scorer` names who filled it in; if not
    given, a Scorer column is used when the template has one, else the file name."""
    path = Path(path)
    result = TemplateRead(path, report=ImportReport(path.name))
    report = result.report
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        values = load_workbook(path, data_only=True)
        formulas = load_workbook(path)
    result.config = read_config(values)
    default_scorer = scorer or path.stem
    for ws in values.worksheets:
        try:
            _read_sheet(ws, formulas[ws.title], result, default_scorer)
        except Exception as e:  # one bad sheet never stops the rest
            report.sheets_skipped.append((ws.title, f"could not be read ({type(e).__name__}: {e})"))
    return result


def _read_sheet(ws, wsf, result: TemplateRead, default_scorer: str) -> None:
    report = result.report
    if _is_skipped_by_name(ws.title):
        report.sheets_skipped.append((ws.title, "not a question sheet (by its name)"))
        return
    found = _find_header(ws, wsf)
    if found is None:
        report.sheets_skipped.append(
            (ws.title, "no table with City and Score headers, so it is not a question sheet")
        )
        return
    header_row, cols, headers = found
    for column in range(1, ws.max_column + 1):  # a header formula whose text was never saved
        formula = wsf.cell(header_row, column).value
        if ws.cell(header_row, column).value is None and isinstance(formula, str):
            if formula.startswith("="):
                letter = get_column_letter(column)
                kept = readable(formula) if formula.startswith('="') else ""
                report.problems.append(
                    f"Sheet {ws.title}: template problem: the header of column {letter} is a formula "
                    f"({formula[:60]}) with no saved text, "
                    + (f'so it was read as "{kept}"' if kept else "so the column was not read")
                    + ". Open the file in Excel and save it, or make the header plain text."
                )
    code, raw_code = _question_code(ws, header_row)
    if code is None:
        report.sheets_skipped.append(
            (ws.title, "has a score table but no question code (sheet name or 'Question Code')")
        )
        report.problems.append(
            f"Sheet {ws.title} looks like a question sheet but its question code can't be read; "
            "its rows were not read."
        )
        return
    if code != normalise_code(ws.title):
        report.problems.append(
            f"Sheet {ws.title} says its question code is {raw_code}; used {code}."
        )
    meta = _meta(ws, code, header_row)
    meta.columns = {f: headers[c] for f, c in cols.items()}
    known_cols = set(cols.values()) | {
        c for c, h in headers.items() if _key(h) in {_key(n) for n in ALIASES["description"]}
    }
    extras = [c for c in sorted(headers) if c not in known_cols]
    meta.extra_columns = [headers[c] for c in extras]
    if code in result.questions:
        report.problems.append(
            f"Question {code} is on more than one sheet ({result.questions[code].sheet} and "
            f"{ws.title}); only the first was read."
        )
        report.sheets_skipped.append((ws.title, f"{code} is already read from another sheet"))
        return
    result.questions[code] = meta
    report.sheets_read.append(ws.title)
    if meta.extra_columns:
        report.unknown_columns[ws.title] = meta.extra_columns

    seen: dict[tuple[str, str], int] = {}
    for r in range(header_row + 1, ws.max_row + 1):

        def cell(field_name, r=r):
            c = cols.get(field_name)
            return ws.cell(r, c).value if c else None

        city, who = _text(cell("city")), _text(cell("parastatal"))
        score_cell = cell("score")
        if not city and not who:
            if any(
                ws.cell(r, c).value not in (None, "") for c in extras + [cols.get("score", 0)] if c
            ):
                report.rows_skipped.append((ws.title, r, "has entries but no City and Parastatal"))
            continue
        if not city or not who:
            report.rows_skipped.append(
                (ws.title, r, f"no {'City' if not city else 'Parastatal'} on the row")
            )
            continue
        ident = (city.casefold(), who.casefold())
        if ident in seen:
            report.rows_skipped.append(
                (
                    ws.title,
                    r,
                    f"{city} / {who} is already on row {seen[ident]}; only the first row is used",
                )
            )
            continue
        seen[ident] = r
        score, note = None, ""
        if score_cell not in (None, ""):
            score = _number(score_cell)
            if score is None:
                note = (
                    "not applicable"
                    if _text(score_cell).upper() in NOT_APPLICABLE
                    else f'the score "{_text(score_cell)}" is not a number'
                )
        elif cols.get("score") and str(wsf.cell(r, cols["score"]).value or "").startswith("="):
            note = "the score is a formula with no saved value: open the file in Excel and save it"
        max_score = _number(cell("max_score"))
        if max_score is None:
            max_score = meta.max_score
        if score is not None and max_score is not None and score > max_score + 1e-9:
            note = f"the score {score:g} is above the maximum {max_score:g}"
        inputs, calculated = {}, {}
        for c in extras:
            value = ws.cell(r, c).value
            if value in (None, ""):
                continue
            is_formula = str(wsf.cell(r, c).value or "").startswith("=")
            (calculated if is_formula else inputs)[headers[c]] = value
        row_scorer = _text(cell("scorer")) or default_scorer
        result.rows.append(
            HumanRow(
                city=city,
                parastatal=who,
                code=code,
                raw_code=raw_code or code,
                score=score,
                score_note=note,
                max_score=max_score,
                parastatal_type=_text(cell("parastatal_type")),
                inputs=inputs,
                calculated=calculated,
                chapter=_text(cell("chapter")),
                provision=_text(cell("provision")),
                clause=_text(cell("clause")),
                page=_text(cell("page")),
                comments=_text(cell("comments")),
                additional_comments=_text(cell("additional_comments")),
                source_link=_text(cell("source_link")),
                latest_information=_text(cell("latest_information")),
                record_check=_text(cell("record_check")),
                scorer=row_scorer,
                file=result.path.name,
                sheet=ws.title,
                row=r,
            )
        )
        report.rows_read += 1
        counts = report.counts.setdefault((city, code), {"read": 0, "scored": 0, "not_scored": 0})
        counts["read"] += 1
        counts["scored" if score is not None else "not_scored"] += 1
        if note and note != "not applicable":
            report.problems.append(f"Sheet {ws.title}, row {r} ({city} / {who}): {note}.")
        if _text(cell("record_check")).upper().startswith("CHECK"):
            report.problems.append(
                f"Sheet {ws.title}, row {r} ({city} / {who}): the template flags this row "
                f"({_text(cell('record_check'))})."
            )


# -- the structure of a template (for writing into a copy of it) --------------------------------
EVIDENCE_FIELDS = (
    "chapter",
    "provision",
    "clause",
    "page",
    "comments",
    "additional_comments",
    "source_link",
    "latest_information",
)
_THIS_ROW = re.compile(r"\[#This Row\],\s*\[(.+?)\]\]")


@dataclass
class ColumnSpec:
    column: int
    header: str
    field: str  # a key of ALIASES, or "" for a column the reader does not know
    kind: str  # identity | calculated | input | evidence | score | check
    options: list[str] | None = None  # a list validation ("Yes,No"); None = any value
    minimum: float | None = None
    maximum: float | None = None
    max_is_question_max: bool = False  # the bound is the sheet's Max Score cell (e.g. $D$3)
    numeric: bool = False  # a number validation


@dataclass
class SheetSpec:
    sheet: str
    code: str
    table: str  # the Excel table's name ("" when the sheet has none)
    header_row: int
    first_row: int
    last_row: int  # the last row of the table (rows below it are free)
    columns: dict[int, ColumnSpec]
    max_score: float | None
    details: dict[
        str, str
    ]  # the label/value cells above the table: Question, Detailed Methodology...
    score_column: int | None
    score_is_formula: bool
    required_inputs: list[int]  # input columns the Score formula needs a value from
    # "Years with valid data < N" in the Score formula: the row scores from N or more years. The
    # needed inputs are grouped by year ("Yr1", "Yr2"...); empty when the formula has no such rule.
    min_years: int | None = None
    year_groups: dict[str, list[int]] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)  # a header the AI cannot rely on

    @property
    def needs_benchmark(self) -> bool:
        """An input that needs data from other cities (a benchmark): the AI can't supply it."""
        return any("benchmark" in s.header.lower() for s in self.inputs)

    def column_for(self, field_name: str) -> int | None:
        return next((c for c, spec in self.columns.items() if spec.field == field_name), None)

    @property
    def inputs(self) -> list[ColumnSpec]:
        return [s for _, s in sorted(self.columns.items()) if s.kind == "input"]

    @property
    def question(self) -> str:
        return self.details.get("Question", "")

    @property
    def applicability(self) -> str:
        return next((v for k, v in self.details.items() if k.lower().startswith("applicab")), "")


def _validations(ws, header_row: int, columns: dict[int, ColumnSpec]) -> None:
    """Fill options and bounds from the sheet's standard data validations (found per column)."""
    for dv in ws.data_validations.dataValidation:
        for cells in dv.sqref.ranges:
            if not cells.min_row <= header_row + 1 <= cells.max_row:
                continue
            for column in range(cells.min_col, cells.max_col + 1):
                spec = columns.get(column)
                if spec is None:
                    continue
                if dv.type == "list" and dv.formula1 and dv.formula1.startswith('"'):
                    spec.options = [
                        o.strip() for o in dv.formula1.strip('"').split(",") if o.strip()
                    ]
                elif dv.type in ("decimal", "whole"):
                    spec.numeric = True
                    low = _number(dv.formula1)
                    if dv.operator in (None, "between"):
                        spec.minimum = low
                        high = _number(dv.formula2)
                        if high is not None:
                            spec.maximum = high
                        elif dv.formula2 and re.fullmatch(r"\$?[A-Z]+\$?\d+", dv.formula2.strip()):
                            spec.max_is_question_max = True  # e.g. $D$3: the sheet's Max Score
                    elif dv.operator == "greaterThanOrEqual":
                        spec.minimum = low
                    elif dv.operator == "lessThanOrEqual":
                        spec.maximum = low


def _calculated_formulas(ws, table, header_row: int, first_row: int, columns) -> dict[str, str]:
    """{header: formula} of the calculated columns (the table's own definition, else the first
    data row's cell)."""
    out = {}
    names = {c.name: c for c in table.tableColumns} if table is not None else {}
    for column, spec in columns.items():
        formula = ""
        tc = names.get(spec.header)
        if tc is not None and tc.calculatedColumnFormula is not None:
            formula = tc.calculatedColumnFormula.attr_text or ""
        if not formula:
            value = ws.cell(first_row, column).value
            formula = value if isinstance(value, str) and value.startswith("=") else ""
        if formula:
            out[spec.header] = formula
    return out


def _strip_calls(text: str, function: str) -> str:
    """`text` without the calls of `function(...)` (arguments may hold their own brackets)."""
    out, i = [], 0
    marker = function.upper() + "("
    while i < len(text):
        if text[i : i + len(marker)].upper() == marker and (i == 0 or not text[i - 1].isalnum()):
            depth, j = 0, i + len(function)
            while j < len(text):
                depth += text[j] == "("
                depth -= text[j] == ")"
                j += 1
                if depth == 0:
                    break
            i = j
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def read_structure(ws) -> SheetSpec | None:
    """The structure of one question sheet of a template (loaded WITH formulas), or None if the
    sheet is not a question sheet."""
    from openpyxl.utils import range_boundaries

    found = _find_header(ws, ws)
    if found is None:
        return None
    header_row, cols, headers = found
    code, _ = _question_code(ws, header_row)
    if code is None:
        return None
    table_name, table = "", None
    for name, candidate in _tables(ws):
        c1, r1, c2, r2 = range_boundaries(candidate.ref)
        if r1 == header_row:
            table_name, table = name, candidate
            break
    if table is not None:
        _, _, _, last_row = range_boundaries(table.ref)
    else:
        last_row = header_row
        while ws.cell(last_row + 1, 1).value not in (None, ""):
            last_row += 1
    first_row = header_row + 1
    by_field = {c: f for f, c in cols.items()}
    columns: dict[int, ColumnSpec] = {}
    for column, header in sorted(headers.items()):
        fld = by_field.get(column, "")
        sample = ws.cell(first_row, column).value
        in_table = table is not None and header in {c.name for c in table.tableColumns}
        defined = False
        if in_table:
            tc = next(c for c in table.tableColumns if c.name == header)
            defined = tc.calculatedColumnFormula is not None
        is_formula = defined or (isinstance(sample, str) and sample.startswith("="))
        if fld in ("city", "parastatal", "parastatal_type", "code", "description", "max_score"):
            kind = "identity"
        elif fld == "score":
            kind = "score"
        elif fld in ("key", "record_check"):
            kind = "check"
        elif fld in EVIDENCE_FIELDS:
            kind = "evidence"
        elif is_formula:
            kind = "calculated"
        else:
            kind = "input"
        columns[column] = ColumnSpec(column, header, fld, kind)
    _validations(ws, header_row, columns)
    details = {}
    for r in range(1, header_row):
        label, value = _text(ws.cell(r, 1).value), ws.cell(r, 2).value
        if label and not (isinstance(value, str) and value.startswith("=")):
            details[label] = _text(value)
    meta = _meta(ws, code, header_row)
    score_col = next((c for c, s in columns.items() if s.kind == "score"), None)
    formulas = _calculated_formulas(ws, table, header_row, first_row, columns)
    score_header = columns[score_col].header if score_col else ""
    required: set[str] = set()
    todo = [score_header] if score_header in formulas else []
    while todo:
        header = todo.pop()
        # COUNTA(...) only asks "is anything typed here?" (e.g. "Years with any data"): the
        # columns it counts are not needed for the score itself.
        text = _strip_calls(formulas.get(header, ""), "COUNTA")
        for ref in _THIS_ROW.findall(text):
            if ref not in required:
                required.add(ref)
                if ref in formulas:
                    todo.append(ref)
    required_inputs = [c for c, s in columns.items() if s.kind == "input" and s.header in required]
    min_years = _min_years(formulas.get(score_header, ""))
    year_groups = _year_groups(columns, required_inputs) if min_years else {}
    problems = _header_problems(ws, table, header_row, headers)
    return SheetSpec(
        sheet=ws.title,
        code=code,
        table=table_name,
        header_row=header_row,
        first_row=first_row,
        last_row=last_row,
        columns=columns,
        max_score=meta.max_score,
        details=details,
        score_column=score_col,
        score_is_formula=score_header in formulas,
        required_inputs=required_inputs,
        min_years=min_years if year_groups else None,
        year_groups=year_groups,
        problems=problems,
    )


_MIN_YEARS = re.compile(r"\[Years with valid data\]\]\s*<\s*(\d+)", re.I)
_YEAR_PREFIX = re.compile(r"^(Yr\d+)\b")


def _min_years(score_formula: str) -> int | None:
    """N from "Years with valid data < N" in a Score formula (SC 1, SC 3: 2), else None."""
    found = _MIN_YEARS.search(score_formula or "")
    return int(found.group(1)) if found else None


def _year_groups(columns, required_inputs) -> dict[str, list[int]]:
    """{"Yr1": [columns the formula needs for that year]...}; empty unless every needed input
    belongs to a year and there are at least two years."""
    groups: dict[str, list[int]] = {}
    for column in required_inputs:
        match = _YEAR_PREFIX.match(columns[column].header)
        if match is None:
            return {}
        groups.setdefault(match.group(1), []).append(column)
    return groups if len(groups) >= 2 else {}


def _header_problems(ws, table, header_row: int, headers: dict[int, str]) -> list[str]:
    """Headers the AI cannot rely on: a formula, an empty or non-text header in the table, or two
    columns with the same header (the AI's reply is keyed by header text)."""
    from openpyxl.utils import get_column_letter, range_boundaries

    out = []
    for column, text in sorted(headers.items()):
        if text.startswith("="):
            out.append(
                f"the header of column {get_column_letter(column)} is a formula ({text[:70]}), not "
                "plain text, so the AI cannot tell which input it is"
            )
    if table is not None:
        c1, _, c2, _ = range_boundaries(table.ref)
        for column in range(c1, c2 + 1):
            value = ws.cell(header_row, column).value
            if not isinstance(value, str) or not value.strip():
                out.append(
                    f"the header of column {get_column_letter(column)} is empty or not text, so "
                    "the AI cannot tell which input it is"
                )
    seen: dict[str, int] = {}
    for column, text in sorted(headers.items()):
        key = " ".join(text.casefold().split())
        if key in seen:
            out.append(
                f"columns {get_column_letter(seen[key])} and {get_column_letter(column)} have the "
                f'same header "{text}", so the AI\'s answer cannot say which one it is for'
            )
        seen.setdefault(key, column)
    return out


def read_structures(wb) -> dict[str, SheetSpec]:
    """{question code: SheetSpec} for every question sheet of a workbook loaded with formulas.
    A sheet that is not a question sheet (Instructions, summaries...) is skipped."""
    out: dict[str, SheetSpec] = {}
    for ws in wb.worksheets:
        if _is_skipped_by_name(ws.title):
            continue
        try:
            spec = read_structure(ws)
        except Exception:  # one odd sheet never stops the rest
            continue
        if spec is not None and spec.code not in out:
            out[spec.code] = spec
    return out


def section_of(codes) -> str:
    """The section a template covers: the most common code prefix of its questions (UPD, SC)."""
    prefixes = [c.split(" ")[0] for c in codes]
    return max(set(prefixes), key=prefixes.count) if prefixes else ""


@dataclass
class QuestionIndexRow:
    code: str
    tag: str
    max_score: float | None
    types: dict[str, str]  # parastatal type code -> "Y" | "N"


def read_question_index(wb) -> tuple[dict[str, QuestionIndexRow], list[str]]:
    """({code: row}, the parastatal type codes the sheet has columns for), found by header text."""
    from asics_agent.parastatal_types import PARASTATAL_TYPES, canonical_type

    name = next((n for n in wb.sheetnames if _key(n) == "questionindex"), None)
    if name is None:
        return {}, []
    rows = list(wb[name].iter_rows(values_only=True))
    at = next(
        (i for i, r in enumerate(rows[:30]) if any(_key(c) == "questioncode" for c in r)), None
    )
    if at is None:
        return {}, []
    header = rows[at]
    known = {t.code for t in PARASTATAL_TYPES}
    type_cols = {}
    for i, c in enumerate(header):
        if _text(c) and canonical_type(_text(c)) in known and i not in type_cols:
            type_cols[i] = canonical_type(_text(c))
    code_col = next(i for i, c in enumerate(header) if _key(c) == "questioncode")
    tag_col = next((i for i, c in enumerate(header) if _key(c) == "tag"), None)
    max_col = next((i for i, c in enumerate(header) if _key(c) == "maxscore"), None)
    out = {}
    for row in rows[at + 1 :]:
        code = normalise_code(row[code_col]) if code_col < len(row) else None
        if code:
            out[code] = QuestionIndexRow(
                code,
                _text(row[tag_col]) if tag_col is not None else "",
                _number(row[max_col]) if max_col is not None else None,
                {t: _text(row[i]).upper() for i, t in type_cols.items() if i < len(row)},
            )
    return out, sorted(set(type_cols.values()))
