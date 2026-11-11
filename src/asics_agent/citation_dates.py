"""Fill the two cut-off columns of an OLD Citation Sheet, into a COPY.

Citation Sheets made before the cut-off work have no "Effective / As-of Date" and "Cut-off Check"
columns. This reads each row's Current/Active Status text and Source Title (the only places the
period was written, as free text) and fills both columns in a copy of the workbook. The original is
never opened for writing and the copy is never written over it. A row that already has a value in
either column is left as it is.

What it can and cannot do (free, no web, no AI):
  * a full date about the law's own timing ("as amended up to 31.03.2024", "w.e.f. 1.6.2005")
    becomes the Effective / As-of Date and the check is ok or later;
  * Bill-stage text becomes Bill-draft;
  * a year without a day ("an Act of 2025") is NOT a date: the row is unknown. The report counts
    these separately, so a year never passes for a date;
  * "last updated", footer, fetch and news dates are ignored.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.styles import Alignment
from openpyxl.worksheet.datavalidation import DataValidation

from asics_agent.cutoff import (
    BILL,
    LATER,
    OK,
    CutoffRule,
    check_of,
    fallback_from_text,
)

SHEET = "Citation Sheet"
EFFECTIVE, CHECK = "Effective / As-of Date", "Cut-off Check"
LEGAL_TYPES = (
    "enabling act",
    "amendment act",
    "rules",
    "legislature paper",
    "secondary legal",
    "gazette",
    "government order",
    "regulations",
    "bye",
)
_YEAR = re.compile(r"\b(19\d\d|20[0-2]\d)\b")


def _norm(text) -> str:
    return re.sub(r"[^a-z0-9/]+", " ", str(text or "").casefold()).strip()


@dataclass
class DatingReport:
    source: str
    copy: str
    rows: int = 0
    already_filled: int = 0
    dated: int = 0  # a full date: ok or later
    bill_draft: int = 0
    year_only: int = 0  # unknown, but a year was written
    unknown: int = 0  # nothing usable
    legal_rows: int = 0
    legal_dated: int = 0
    legal_bill: int = 0
    legal_year_only: int = 0
    legal_unknown: int = 0
    by_check: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def lines(self) -> list[str]:
        d = self.dated + self.bill_draft
        return [
            f"{Path(self.source).name} -> {Path(self.copy).name}",
            f"  rows {self.rows}; already had a value {self.already_filled}",
            f"  properly dated (a full date): {self.dated}"
            f" (ok {self.by_check.get(OK, 0)}, later {self.by_check.get(LATER, 0)});"
            f" Bill or draft: {self.bill_draft}",
            f"  year only (counted as unknown): {self.year_only}; nothing usable: {self.unknown}",
            f"  datable in all (dated + Bill/draft): {d} of {self.rows}",
            f"  legal citations {self.legal_rows}: with a real date {self.legal_dated}, "
            f"Bill or draft {self.legal_bill}, year only {self.legal_year_only}, "
            f"nothing usable {self.legal_unknown}",
            *[f"  note: {n}" for n in self.notes],
        ]


def _year_written(status: str) -> bool:
    period = status.split("period=", 1)[1] if "period=" in status else status
    return bool(_YEAR.search(period))


def date_citation_sheet(source: Path, copy: Path, rule: CutoffRule) -> DatingReport:
    """Write `copy` (a new file) from the Sources workbook `source`, with the two columns filled
    where they were empty, and report what could be dated."""
    source, copy = Path(source), Path(copy)
    if source.resolve() == copy.resolve():
        raise ValueError("The copy must be a different file: the original is never overwritten.")
    if copy.exists():
        raise FileExistsError(f"{copy} already exists; remove it or choose another name.")
    report = DatingReport(str(source), str(copy))
    wb = load_workbook(source)  # the file on disk is not touched: we save to `copy` only
    if SHEET not in wb.sheetnames:
        raise ValueError(f'{source.name} has no "{SHEET}" sheet.')
    ws = wb[SHEET]
    header = {_norm(c.value): c.column for c in ws[1] if c.value}
    last = ws.max_column
    for name in (EFFECTIVE, CHECK):
        if _norm(name) not in header:
            last += 1
            header[_norm(name)] = last
            cell = ws.cell(1, last, name)
            cell._style = ws.cell(1, last - 1)._style
            ws.column_dimensions[cell.column_letter].width = 16
    col = {k: header[_norm(k)] for k in (EFFECTIVE, CHECK)}

    def at(row, name):
        c = header.get(_norm(name))
        return "" if c is None else str(ws.cell(row, c).value or "").strip()

    for r in range(2, ws.max_row + 1):
        if not at(r, "Citation ID"):
            continue
        report.rows += 1
        legal = any(k in at(r, "Source Type").casefold() for k in LEGAL_TYPES)
        report.legal_rows += legal
        if at(r, EFFECTIVE) or at(r, CHECK):
            report.already_filled += 1
            continue
        status, title = at(r, "Current/Active Status"), at(r, "Source Title")
        effective, check = fallback_from_text(status, title, rule)
        ws.cell(r, col[EFFECTIVE], effective or None)
        ws.cell(r, col[CHECK], check)
        ws.cell(r, col[CHECK]).alignment = Alignment(horizontal="left")
        report.by_check[check] = report.by_check.get(check, 0) + 1
        if check == BILL:
            report.bill_draft += 1
            report.legal_bill += legal
        elif check in (OK, LATER):
            report.dated += 1
            report.legal_dated += legal
        elif _year_written(status):
            report.year_only += 1
            report.legal_year_only += legal
        else:
            report.unknown += 1
            report.legal_unknown += legal
    dv = DataValidation(type="list", formula1='"ok,later,unknown,Bill-draft"', allow_blank=True)
    letter = ws.cell(1, col[CHECK]).column_letter
    dv.add(f"{letter}2:{letter}{max(ws.max_row, 500)}")
    ws.add_data_validation(dv)
    copy.parent.mkdir(parents=True, exist_ok=True)
    wb.save(copy)
    return report


def sheet_checks(path: Path, rule: CutoffRule) -> dict[str, int]:
    """How many rows of a Sources workbook check ok / later / unknown / Bill-draft now (own
    column if filled, else read from the text)."""
    from asics_agent.sources_workbook import read_sources_workbook

    out: dict[str, int] = {}
    _, citations, _ = read_sources_workbook(Path(path), Path(path).parent / "evidence")
    for s in citations:
        k = check_of(s, rule)
        out[k] = out.get(k, 0) + 1
    return out
