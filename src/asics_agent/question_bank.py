"""Loads the ASICS parastatal question bank workbook.

The bank's IDs are written inconsistently ("DPG-2b", "DPG5a", "DPG d"), so IDs are
normalised to "<PILLAR> <number><letter>" and every fix is reported as an Issue.
"""

import re
from pathlib import Path

from openpyxl import load_workbook

from asics_agent.models import Issue, Question

SHEET = "Question Bank"
REQUIRED_COLUMNS = [
    "Sl. No.",
    "City-Systems Pillar",
    "Question",
    "Tag",
    "Score / Max Score",
    "Assessment Level",
    "Applicability",
    "Detailed Methodology",
    "Evidence / Source Requirement",
]

_ID = re.compile(r"^\s*([A-Za-z]+)[\s\-]*(\d*)\s*([a-z]?)\s*$")
_SECTION = re.compile(r"\(([A-Z]+)\)")


def _clean(value) -> str:
    return "" if value is None else str(value).strip()


def _score(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_question_bank(path: Path) -> tuple[dict[str, Question], list[Issue]]:
    ws = load_workbook(path, read_only=True, data_only=True)[SHEET]
    rows = list(ws.iter_rows(values_only=True))
    header = [_clean(h) for h in rows[0]]
    issues: list[Issue] = []
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        issues.append(
            Issue(
                phase="initial_checks",
                severity="error",
                audience="team",
                message="The Question Bank sheet is missing these columns: "
                f"{', '.join(missing)}. Add them back (with the same names) and try again.",
            )
        )
        return {}, issues
    col = {name: header.index(name) for name in header if name}

    questions: dict[str, Question] = {}
    pillar_code, pillar_name, parent = "", "", None
    for row_no, row in enumerate(rows[1:], start=2):
        raw_id = _clean(row[col["City-Systems Pillar"]])
        if not raw_id:
            # Section header row, e.g. "Urban Planning & Design (UPD)"
            pillar_name = _clean(row[0])
            if not pillar_name:
                continue
            match = _SECTION.search(pillar_name)
            pillar_code = match.group(1) if match else ""
            parent = None
            continue

        match = _ID.match(raw_id)
        if not match:
            issues.append(
                Issue(
                    phase="initial_checks",
                    severity="error",
                    ref=raw_id,
                    audience="team",
                    message=f'Question Bank row {row_no}: the ID "{raw_id}" isn\'t in a form '
                    'we understand (e.g. "UPD 1a"). Please correct it.',
                )
            )
            continue
        prefix, number, letter = match.groups()
        prefix = prefix.upper()
        tag = _clean(row[col["Tag"]]).upper()
        if not pillar_code:
            pillar_code = prefix
            issues.append(
                Issue(
                    phase="initial_checks",
                    severity="warning",
                    ref=raw_id,
                    message=f"Section {pillar_name!r} has no (CODE); using {prefix}",
                )
            )
        if prefix != pillar_code:
            issues.append(
                Issue(
                    phase="initial_checks",
                    severity="warning",
                    ref=raw_id,
                    message=f"Row {row_no}: ID prefix {prefix} differs from "
                    f"section code {pillar_code}",
                )
            )
        if not number and tag == "SQ" and parent:
            number = re.sub(r"\D", "", parent.id.split(" ")[1])
            issues.append(
                Issue(
                    phase="initial_checks",
                    severity="warning",
                    ref=raw_id,
                    audience="team",
                    message=f'Question Bank row {row_no}: the ID "{raw_id}" has no number. '
                    f"We treated it as part of {parent.id}. Please correct the ID in the "
                    "question bank.",
                )
            )
        qid = f"{pillar_code} {number}{letter}"
        if qid != raw_id:
            issues.append(
                Issue(
                    phase="initial_checks",
                    severity="info",
                    ref=qid,
                    message=f"Row {row_no}: normalised ID {raw_id!r} -> {qid!r}",
                )
            )
        if qid in questions:
            issues.append(
                Issue(
                    phase="initial_checks",
                    severity="error",
                    ref=qid,
                    audience="team",
                    message=f'Question Bank row {row_no}: the ID "{raw_id}" is used twice. '
                    "Each question needs its own ID; the second one was skipped.",
                )
            )
            continue

        question = Question(
            id=qid,
            raw_id=raw_id,
            row=row_no,
            pillar=pillar_code,
            pillar_name=pillar_name,
            text=_clean(row[col["Question"]]),
            tag="MQ" if tag == "MQ" else "SQ",
            max_score=_score(row[col["Score / Max Score"]]),
            assessment_level=_clean(row[col["Assessment Level"]]) or None,
            unit=_clean(row[col.get("Unit of Assessment", -1)])
            if "Unit of Assessment" in col
            else None,
            applicability=_clean(row[col["Applicability"]]),
            methodology=_clean(row[col["Detailed Methodology"]]),
            evidence_requirement=_clean(row[col["Evidence / Source Requirement"]]),
            rationale=_clean(row[col["Rationale"]]) if "Rationale" in col else "",
        )
        if question.tag == "MQ":
            parent = question
        elif parent is not None:
            question.parent_id = parent.id
            parent.children.append(qid)
        questions[qid] = question
    return questions, issues
