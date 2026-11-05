"""Expected values built from the reference files at test time (docs/reference/).

Nothing here is a count or a code written by hand: the team's workbook and templates are read,
independently of the code under test, so a newer copy of those files changes the expectations.
"""

import re
import warnings
from pathlib import Path

import pytest
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "docs" / "reference"
TEMPLATES = ROOT / "scoring" / "2027" / "templates"  # the team's scoring templates
CODE = re.compile(r"^\s*([A-Za-z]{2,6})[\s\-]*(\d+)\s*([A-Za-z]?)\s*$")


def reference_workbook() -> Path:
    found = sorted(REF.glob("*Pilot*.xlsx"))
    if not found:
        pytest.skip("docs/reference has no question workbook")
    return found[0]


def reference_templates() -> list[Path]:
    found = sorted(TEMPLATES.glob("Parastatal_*_Template.xlsx"))
    if not found:
        pytest.skip("scoring/2027/templates has no scoring templates")
    return found


def norm(raw) -> str | None:
    m = CODE.match("" if raw is None else str(raw))
    return f"{m.group(1).upper()} {m.group(2)}{m.group(3).lower()}" if m else None


def expected_questions(sections=("UPD", "SC", "DPG")) -> dict[str, dict]:
    """{code: fields} for every question row of the section sheets: the code cell is exactly a
    code and the question text is not empty."""
    wb = load_workbook(reference_workbook(), data_only=True)
    out = {}
    for name in sections:
        ws = wb[name]
        rows = list(ws.iter_rows(values_only=True))
        header = next(r for r in rows[:10] if "Question" in [str(c).strip() for c in r if c])
        col = {str(c).strip(): i for i, c in enumerate(header) if c}
        for row in rows[rows.index(header) + 1 :]:
            raw = row[col["City-Systems Pillar"]]
            text = row[col["Question"]]
            if norm(raw) and text and str(text).strip():
                out[norm(raw)] = {
                    "raw": str(raw).strip(),
                    "text": str(text).strip(),
                    "tag": str(row[col["Tag"]] or "").strip().upper(),
                    "max": row[col["Score / Max Score"]],
                    "applicability": str(row[col["Applicability"]] or "").strip(),
                    "methodology": str(row[col["Detailed Methodology"]] or "").strip(),
                }
    return out


def template_index() -> dict[str, dict[str, dict[str, str]]]:
    """{template file: {code: {type label: Y/N}}} from each template's Question_Index sheet."""
    out = {}
    for path in reference_templates():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            wb = load_workbook(path, data_only=True)
        rows = list(wb["Question_Index"].iter_rows(values_only=True))
        header = next(r for r in rows[:20] if "Question Code" in [str(c).strip() for c in r if c])
        types = {
            str(c).strip(): i
            for i, c in enumerate(header)
            if c
            and str(c).strip()
            in {"Development Authority", "Water Supply Entity", "Public Bus Transport Operator"}
        }
        index = {}
        for row in rows[rows.index(header) + 1 :]:
            code = norm(row[header.index("Question Code")])
            if code:
                index[code] = {t: str(row[i]).strip().upper() for t, i in types.items()}
        out[path.name] = index
    return out


def fill_template(src: Path, dst: Path, scores: dict[tuple[str, str, str], object], **opts) -> Path:
    """A copy of a template with scores typed in: {(sheet, parastatal short code): score}.

    opts: rename={"Score": "Points (Auto-generate)"} renames headers; shuffle=True reverses the
    order of the columns between City and Score's neighbours (headers and cells together);
    extra={"header": value} adds a column of that header (the value in every data row);
    link={(sheet, parastatal): url} types a source link."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = load_workbook(src)
    for (sheet, who, *_), score in scores.items():
        ws = wb[sheet]
        header_row = next(r for r in range(1, 40) if ws.cell(r, 1).value == "City")
        hdr = {ws.cell(header_row, c).value: c for c in range(1, ws.max_column + 1)}
        for r in range(header_row + 1, ws.max_row + 1):
            if ws.cell(r, 2).value == who:
                ws.cell(r, hdr["Score"], score)
                if link := opts.get("link", {}).get((sheet, who)):
                    ws.cell(r, hdr["Source Link or Evidence Document"], link)
    for sheet in {s for (s, *_) in scores}:
        ws = wb[sheet]
        header_row = next(r for r in range(1, 40) if ws.cell(r, 1).value == "City")
        for old, new in opts.get("rename", {}).items():
            for c in range(1, ws.max_column + 1):
                if ws.cell(header_row, c).value == old:
                    ws.cell(header_row, c, new)
        if opts.get("extra"):
            col = ws.max_column + 1
            for header, value in opts["extra"].items():
                ws.cell(header_row, col, header)
                for r in range(header_row + 1, ws.max_row + 1):
                    if ws.cell(r, 1).value:
                        ws.cell(r, col, value)
                col += 1
        if opts.get("shuffle"):
            _reverse_columns(ws, header_row, 4)  # keep City, Parastatal Name, Type, Code first
    wb.save(dst)
    return dst


def _reverse_columns(ws, header_row: int, first: int) -> None:
    """Reverse the order of the typed columns from `first` on (headers and values; the first two
    rows of values are enough for a test since the templates keep formulas in other columns)."""
    last = ws.max_column
    for r in range(header_row, ws.max_row + 1):
        values = [ws.cell(r, c).value for c in range(first, last + 1)]
        for offset, value in enumerate(reversed(values)):
            ws.cell(r, first + offset, value)
