"""Writes the AI's values into a COPY of a scoring template (the team's UPD, SC or DPG template).

The AI file has exactly the template's layout, so people and the AI fill the same cells and the
template's own formulas calculate the scores. Rules enforced here, not left to the caller:

  * only input columns, evidence columns, comments (and the Score where the sheet has a typed
    Score) are written; never a formula, a header or another sheet;
  * every value is checked against the column's allowed values first; a bad value is reported
    and not written;
  * a new city or parastatal gets the template's own Configuration row (identical in every file
    of the category) and a row under each question table it applies to; other cities' rows are
    never touched;
  * the file is recalculated with LibreOffice and checked against the file before: if anything
    structural differs (tables, validations, protection, names...), the uncalculated file is kept
    and the caller is told, so the portal can say "the score calculates when opened in Excel".

openpyxl drops the template's x14 "Parastatal Name" drop-down; it is re-added as a standard
validation (the DPG template already has it that way).
"""

import hashlib
import json
import re
import shutil
import tempfile
import zipfile
from copy import copy
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.formula.translate import Translator
from openpyxl.utils import get_column_letter, range_boundaries
from openpyxl.worksheet.datavalidation import DataValidation

from asics_agent.scoring.recalc import RecalcUnavailable, recalculate
from asics_agent.scoring.template_import import (
    SheetSpec,
    config_table,
    normalise_code,
    read_config,
    read_question_index,
    read_structures,
    section_of,
)

INFO_SUFFIX = ".ai_info.json"
HISTORY_KEEP = 10
PARASTATAL_NAME_LIST = (
    "OFFSET(Configuration!$C$7,MATCH($A14,Configuration!$A$7:$A$306,0)-1,0,"
    "COUNTIF(Configuration!$A$7:$A$306,$A14),1)"
)


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def _key(text) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text or "").casefold())


def template_hash(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ai_file_name(scoring_code: str, section: str) -> str:
    """e.g. PARASTATAL_UPD_AI.xlsx. The category is in the name because the ULG's own scoring
    file is UPD_ai.xlsx, which a plain UPD_AI.xlsx would be (macOS ignores capitals)."""
    return f"{scoring_code}_{section}_AI.xlsx"


def ai_path(scoring_dir: Path, scoring_code: str, section: str) -> Path:
    return scoring_dir / "ai" / ai_file_name(scoring_code, section)


def info_path(path: Path) -> Path:
    return path.with_name(path.stem + INFO_SUFFIX)


def read_info(path: Path) -> dict:
    try:
        return json.loads(info_path(path).read_text())
    except (OSError, ValueError):
        return {}


def write_info(path: Path, info: dict) -> None:
    info_path(path).write_text(json.dumps(info, indent=2, default=str))


def fingerprint(path: Path) -> dict:
    """What a template workbook is made of, from its XML (to prove nothing was lost)."""
    z = zipfile.ZipFile(path)
    names = z.namelist()
    sheets = "".join(
        z.read(n).decode("utf8", "ignore") for n in names if n.startswith("xl/worksheets/sheet")
    )
    book = z.read("xl/workbook.xml").decode("utf8", "ignore")
    tables = {}
    for n in names:
        if n.startswith("xl/tables/"):
            xml = z.read(n).decode("utf8", "ignore")
            name = re.search(r'\bname="([^"]+)"', xml)
            ref = re.search(r'\bref="([^"]+)"', xml)
            tables[name.group(1) if name else n] = ref.group(1) if ref else ""
    return {
        "tables": sorted(tables),
        "validations": len(re.findall(r"<dataValidation ", sheets)),
        "conditional_formats": len(re.findall(r"<conditionalFormatting", sheets)),
        "protected_sheets": len(re.findall(r"<sheetProtection", sheets)),
        "formulas": len(re.findall(r"<f[ >]", sheets)),
        "defined_names": sorted(re.findall(r'<definedName [^>]*name="([^"]+)"', book)),
        "hidden_sheets": len(re.findall(r'<sheet [^>]*state="hidden"', book)),
        "sheet_names": re.findall(r'<sheet [^>]*name="([^"]+)"', book),
    }


def same_structure(before: dict, after: dict) -> list[str]:
    """What differs between two fingerprints (empty = the same structure)."""
    return [
        f"{k}: {before[k]} -> {after[k]}"
        for k in before
        if k != "formulas" and before[k] != after.get(k)
    ] + (
        [f"formulas: {before['formulas']} -> {after['formulas']}"]
        if before["formulas"] != after.get("formulas")
        else []
    )


def error_cells(path: Path, limit: int = 5) -> dict[str, list[str]]:
    """{sheet: [first few error cells]} of a calculated workbook (Err:..., #REF!...)."""
    out = {}
    wb = load_workbook(path, data_only=True, read_only=True)
    for ws in wb.worksheets:
        found = []
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and (
                    c.value.startswith("#") or c.value.startswith("Err:")
                ):
                    found.append(f"{c.coordinate} {c.value}")
        if found:
            out[ws.title] = found[:limit]
    return out


def check_value(spec: SheetSpec, column: int, value) -> tuple[object, str]:
    """(value to write, "") or (None, why it can't be written), against the column's own
    validation. A blank value is (None, "")."""
    col = spec.columns.get(column)
    if col is None or col.kind not in ("input", "evidence", "score"):
        return None, f"column {column} is not one the AI may write to"
    if col.kind == "score" and spec.score_is_formula:
        return None, "the Score of this question is calculated by the template"
    if value in (None, ""):
        return None, ""
    if col.options:
        match = next((o for o in col.options if o.casefold() == _text(value).casefold()), None)
        if match is None:
            return None, f'"{value}" is not one of {" / ".join(col.options)}'
        return match, ""
    numeric = col.numeric or col.kind == "score"
    if numeric:
        try:
            number = (
                float(value)
                if isinstance(value, int | float) and not isinstance(value, bool)
                else float(_text(value).rstrip("%"))
            )
        except ValueError:
            return None, f'"{value}" is not a number'
        if col.minimum is not None and number < col.minimum:
            return None, f"{number:g} is below the minimum {col.minimum:g}"
        if col.kind == "score" or col.max_is_question_max:
            if spec.max_score is None:
                return None, "this question has no maximum score, so it is not scored"
            high = spec.max_score
        else:
            high = col.maximum
        if col.kind == "score" and number < 0:
            return None, f"{number:g} is below 0"
        if high is not None and number > high + 1e-9:
            return None, f"{number:g} is above the maximum {high:g}"
        return (int(number) if number == int(number) else number), ""
    return value, ""


@dataclass
class WriteResult:
    written: int = 0
    rejected: list[str] = field(default_factory=list)  # plain language: value not written + why


@dataclass
class SaveResult:
    path: Path
    calculated: bool  # the delivered file holds calculated values
    problems: list[str] = field(default_factory=list)


class AITemplate:
    """One AI workbook: a copy of a template, opened for writing."""

    def __init__(self, path: Path, template: Path):
        self.path, self.template = Path(path), Path(template)
        self.created = not self.path.exists()
        self.wb = load_workbook(self.path if self.path.exists() else self.template)
        self.specs: dict[str, SheetSpec] = read_structures(self.wb)
        self.section = section_of(self.specs)
        self.index, self.index_types = read_question_index(self.wb)
        self.rows: dict[str, dict[tuple[str, str], int]] = {}
        self.added_rows = 0
        self.problems: list[str] = []
        self.dirty = self.created
        self.config_note = "Added by the AI scorer from the city register."

    # -- reading the layout ------------------------------------------------------------------
    def _row_map(self, code: str) -> dict[tuple[str, str], int]:
        if code not in self.rows:
            spec = self.specs[code]
            ws = self.wb[spec.sheet]
            city_col = spec.column_for("city")
            who_col = spec.column_for("parastatal")
            found = {}
            for r in range(spec.first_row, spec.last_row + 1):
                city = _text(ws.cell(r, city_col).value) if city_col else ""
                who = _text(ws.cell(r, who_col).value) if who_col else ""
                if city and (who or not who_col):
                    found.setdefault((city.casefold(), who.casefold()), r)
            self.rows[code] = found
        return self.rows[code]

    def row_of(self, code: str, city: str, who: str) -> int | None:
        return self._row_map(code).get((city.casefold(), who.casefold()))

    def applicable_types(self, code: str) -> set[str] | None:
        """The parastatal types the template scores this question for (its Question_Index), or
        None when the template doesn't say."""
        row = self.index.get(code)
        if row is None or not row.types:
            return None
        return {t for t, v in row.types.items() if v == "Y"}

    def capacity(self) -> int | None:
        """How many active parastatals the Raw Summary has columns for (120 today)."""
        ws = next((self.wb[n] for n in self.wb.sheetnames if _key(n) == "rawsummary"), None)
        if ws is None:
            return None
        for r in range(1, 15):
            if any("key" in _key(ws.cell(r, c).value) for c in range(1, 8)):
                label_col = next(c for c in range(1, 8) if "key" in _key(ws.cell(r, c).value))
                return sum(
                    1
                    for c in range(label_col + 1, ws.max_column + 1)
                    if isinstance(ws.cell(r, c).value, str) and ws.cell(r, c).value.startswith("=")
                )
        return None

    # -- the Configuration table and the city list --------------------------------------------
    def config_rows(self):
        return read_config(self.wb)

    def has_unit(self, city: str, who: str) -> bool:
        return any(
            c.city.casefold() == city.casefold() and c.parastatal.casefold() == who.casefold()
            for c in self.config_rows()
        )

    def _extend_table(self, ws, table, rows: int = 1) -> int:
        c1, r1, c2, r2 = range_boundaries(table.ref)
        table.ref = f"{get_column_letter(c1)}{r1}:{get_column_letter(c2)}{r2 + rows}"
        if table.autoFilter is not None:
            table.autoFilter.ref = table.ref
        return r2 + rows

    def _clone_row(self, ws, from_row: int, to_row: int, first_col: int, last_col: int) -> None:
        for c in range(first_col, last_col + 1):
            src, dst = ws.cell(from_row, c), ws.cell(to_row, c)
            dst._style = copy(src._style)
            value = src.value
            if isinstance(value, str) and value.startswith("="):
                value = Translator(value, origin=src.coordinate).translate_formula(dst.coordinate)
                dst.value = value
            else:
                dst.value = None

    def ensure_unit(self, city: str, who: str, type_label: str) -> list[str]:
        """Add the city (tblCities) and the parastatal (Configuration table) if they are not there.
        Returns plain-language problems (e.g. no room, unknown type)."""
        problems = []
        ws, table = config_table(self.wb)
        if table is None:
            return [f"{self.path.name}: no Configuration table, so {city} / {who} can't be added."]
        if self.has_unit(city, who):
            return []
        if self.index_types and type_label and not self._type_known(type_label):
            problems.append(
                f"{city} / {who} is a '{type_label}', which this template has no column for in its "
                "Question_Index, so none of its questions can be scored here."
            )
        capacity = self.capacity()
        if capacity is not None and sum(c.active for c in self.config_rows()) >= capacity:
            return problems + [
                f"The template has room for {capacity} active parastatals: no room for {who}."
            ]
        c1, r1, c2, r2 = range_boundaries(table.ref)
        cols = {_key(c.name): c1 + i for i, c in enumerate(table.tableColumns)}
        new = self._extend_table(ws, table)
        self._clone_row(ws, r2, new, c1, c2)
        ws.cell(new, cols["city"], city)
        ws.cell(new, cols["parastatalname"], who)
        ws.cell(new, cols["parastataltype"], type_label)
        ws.cell(new, cols["active"], "Y")
        if "notesorsource" in cols:
            ws.cell(new, cols["notesorsource"], self.config_note)
        self._ensure_city(ws, city)
        self.dirty = True
        return problems

    def _type_known(self, type_label: str) -> bool:
        from asics_agent.parastatal_types import canonical_type

        return canonical_type(type_label) in self.index_types

    def _ensure_city(self, config_ws, city: str) -> None:
        for _, table in [(n, config_ws.tables[n]) for n in config_ws.tables]:
            names = [c.name for c in table.tableColumns]
            if (
                names
                and _key(names[0]) == "city"
                and "parastatalname" not in {_key(n) for n in names}
            ):
                c1, r1, c2, r2 = range_boundaries(table.ref)
                if any(
                    _text(config_ws.cell(r, c1).value).casefold() == city.casefold()
                    for r in range(r1 + 1, r2 + 1)
                ):
                    return
                new = self._extend_table(config_ws, table)
                self._clone_row(config_ws, r2, new, c1, c2)
                config_ws.cell(new, c1, city)
                for c in range(c1 + 1, c2 + 1):
                    config_ws.cell(new, c, None)
                return

    # -- question table rows -----------------------------------------------------------------
    def ensure_row(self, code: str, city: str, who: str) -> int | None:
        """The row of (city, parastatal) in the question's table; added at the end if missing."""
        spec = self.specs[code]
        row = self.row_of(code, city, who)
        if row is not None:
            return row
        ws = self.wb[spec.sheet]
        city_col, who_col = spec.column_for("city"), spec.column_for("parastatal")
        if city_col is None:
            return None
        new_row = spec.last_row + 1
        if spec.table:
            self._extend_table(ws, ws.tables[spec.table])
        template_row = spec.last_row if spec.last_row >= spec.first_row else spec.first_row
        width = max(spec.columns)
        self._clone_row(ws, template_row, new_row, min(spec.columns), width)
        ws.cell(new_row, city_col, city)
        if who_col:
            ws.cell(new_row, who_col, who)
        for column, col_spec in spec.columns.items():  # a cloned row starts empty
            if col_spec.kind in ("input", "evidence", "score") and not (
                col_spec.kind == "score" and spec.score_is_formula
            ):
                ws.cell(new_row, column).value = None
        spec.last_row = new_row
        self.rows[code][(city.casefold(), who.casefold())] = new_row
        self.added_rows += 1
        self.dirty = True
        return new_row

    # -- writing values ----------------------------------------------------------------------
    def check_value(self, spec: SheetSpec, column: int, value) -> tuple[object, str]:
        return check_value(spec, column, value)

    def write(self, code: str, row: int, values: dict[int, object]) -> WriteResult:
        spec, result = self.specs[code], WriteResult()
        ws = self.wb[spec.sheet]
        for column, value in values.items():
            ok, why = self.check_value(spec, column, value)
            header = spec.columns[column].header if column in spec.columns else str(column)
            if why:
                result.rejected.append(f'{code}, "{header}": {why}.')
                continue
            if ok is None:
                continue
            cell = ws.cell(row, column)
            cell.value = ok
            if isinstance(ok, str) and ok.startswith("="):
                cell.data_type = "s"  # text that looks like a formula stays text, never runs
            result.written += 1
        if result.written:
            self.dirty = True
        return result

    def clear(self, code: str, row: int) -> None:
        """Empty the AI-writable cells of a row (before a fresh run writes it again)."""
        spec = self.specs[code]
        ws = self.wb[spec.sheet]
        for column, col in spec.columns.items():
            if col.kind in ("input", "evidence") or (
                col.kind == "score" and not spec.score_is_formula
            ):
                ws.cell(row, column).value = None

    # -- saving ------------------------------------------------------------------------------
    def _restore_dropdowns(self) -> None:
        """Re-add the Parastatal Name drop-down that openpyxl drops (an x14 extension)."""
        for spec in self.specs.values():
            ws = self.wb[spec.sheet]
            col = spec.column_for("parastatal")
            if col is None:
                continue
            letter = get_column_letter(col)
            area = f"{letter}{spec.first_row}:{letter}500"
            if any(
                letter in str(dv.sqref)
                for dv in ws.data_validations.dataValidation
                if dv.type == "list" and dv.formula1 and "OFFSET" in dv.formula1
            ):
                continue
            dv = DataValidation(type="list", formula1=PARASTATAL_NAME_LIST, allow_blank=True)
            dv.add(area)
            ws.add_data_validation(dv)

    def save(self, profile_dir: Path, history_dir: Path | None = None) -> SaveResult:
        """Save, keep a history copy of what was there, recalculate and check the result."""
        problems = list(self.problems)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and history_dir is not None and self.dirty:
            history_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            shutil.copyfile(self.path, history_dir / f"{self.path.stem}_{stamp}.xlsx")
            for old in sorted(history_dir.glob(f"{self.path.stem}_*.xlsx"))[:-HISTORY_KEEP]:
                old.unlink()
        self._restore_dropdowns()
        with tempfile.TemporaryDirectory() as tmp:
            plain = Path(tmp) / "plain.xlsx"
            self.wb.save(plain)
            before = fingerprint(plain)
            calc = Path(tmp) / "calculated.xlsx"
            shutil.copyfile(plain, calc)
            calculated = False
            try:
                recalculate(calc, profile_dir)
                differences = same_structure(before, fingerprint(calc))
                if differences:
                    problems.append(
                        f"{self.path.name}: LibreOffice changed the file's structure ("
                        + "; ".join(differences[:3])
                        + "), so the uncalculated file was kept. The score calculates when the "
                        "file is opened in Excel."
                    )
                else:
                    calculated = True
                    errors = error_cells(calc)
                    for sheet, cells in errors.items():
                        problems.append(
                            f"{self.path.name}, sheet {sheet}: formula errors ({', '.join(cells)})."
                        )
            except RecalcUnavailable as exc:
                problems.append(f"{exc} The score calculates when the file is opened in Excel.")
            except (RuntimeError, OSError) as exc:
                problems.append(f"{self.path.name} could not be recalculated ({exc}).")
            shutil.copyfile(calc if calculated else plain, self.path)
        self.dirty = False
        return SaveResult(self.path, calculated, problems)


def open_ai_template(path: Path, template: Path, carry_over=None) -> tuple[AITemplate, list[str]]:
    """The AI workbook at `path`, made from `template`. If the template changed since the AI file
    was made, the file is rebuilt from the new template and what the AI wrote is carried over by
    (sheet, city, parastatal, header); anything that can't move is reported."""
    notes: list[str] = []
    info = read_info(path)
    current = template_hash(template)
    if path.exists() and info.get("template_sha256") and info["template_sha256"] != current:
        old = path.with_name(path.stem + ".previous.xlsx")
        shutil.copyfile(path, old)
        path.unlink()
        ai = AITemplate(path, template)
        notes.append(
            f"The template {Path(template).name} changed since {path.name} was made: the file was "
            "rebuilt from the new template. What the AI had written was carried over where the "
            "question, row and column still exist."
        )
        if carry_over is not None:
            notes += carry_over(ai, old)
        old.unlink(missing_ok=True)
        return ai, notes
    return AITemplate(path, template), notes


def normalise(raw) -> str | None:
    return normalise_code(raw)
