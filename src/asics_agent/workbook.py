"""Reads a previous-phase workbook and writes the output workbook.

"PRESERVE WORKBOOK": existing sheets, sheet names, columns, formatting and row order are
kept. Rows are updated in place and new rows are appended; missing columns are added at
the end of the header row.
"""

import json
import os
import re
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.worksheet import Worksheet

from asics_agent.models import Answer, Issue, Parastatal, Question, Source
from asics_agent.reporting import STATUS_HELP, VERIFICATION_HELP, severity_label, team_issues

CITATION_SHEET = "Citation Sheet"
EXCEL_MAX_SHEET_TITLE = 31


def scoring_sheet_title(city_name: str) -> str:
    """ "Parastatal Scoring - <City>", shortened to fit Excel's 31-character limit."""
    for title in (f"Parastatal Scoring - {city_name}", f"Scoring - {city_name}"):
        if len(title) <= EXCEL_MAX_SHEET_TITLE:
            return title
    return f"Scoring - {city_name}"[:EXCEL_MAX_SHEET_TITLE].rstrip()


def is_scoring_sheet(title: str) -> bool:
    return title.startswith(("Parastatal Scoring", "Scoring - "))


# (canonical header, accepted aliases in an existing sheet). New sheets use this order,
# which puts what a reviewer needs first; existing sheets keep their own order.
CITATION_COLUMNS = [
    ("Citation ID", ["citation id", "citation no", "id"]),
    ("Parastatal", ["parastatal", "parastatal name", "agency"]),
    ("Source Title", ["source title", "source", "title", "source name", "document"]),
    ("Source Type", ["source type", "type"]),
    ("Official URL", ["official url", "url", "link", "source url"]),
    ("Saved Copy", ["saved copy", "snapshot"]),
    ("What This Source Is Useful For", ["what this source is useful for", "useful for"]),
    ("Question IDs", ["question ids", "questions", "question id"]),
    ("Accessibility", ["accessibility"]),
    ("Current/Active Status", ["current/active status", "current status", "active status"]),
    ("Verification Status", ["verification status", "verified"]),
    ("Authority Score", ["authority score", "score"]),
    ("Notes", ["notes", "remarks", "comments"]),
    ("Found By", ["found by"]),
    ("Last Checked", ["last checked", "checked at", "date checked"]),
]

SCORING_COLUMNS = [
    ("Parastatal", ["parastatal", "parastatal name", "agency"]),
    ("Question ID", ["question id", "id", "indicator", "city-systems pillar"]),
    ("Question", ["question"]),
    ("Status", ["status"]),
    ("Answer", ["answer", "response"]),
    ("Proposed Score", ["proposed score", "score"]),
    ("Max Score", ["max score", "score / max score"]),
    ("Citation ID", ["citation id"]),
    ("Citation", ["citation", "source"]),
    ("Citation URL", ["citation url", "url", "source url"]),
    ("Where to Find It", ["where to find it"]),
    ("Search Phrase", ["search phrase"]),
    ("Evidence Excerpt", ["evidence excerpt", "evidence", "quote"]),
    ("Saved Copy", ["saved copy", "snapshot"]),
    ("Notes", ["notes", "remarks", "comments"]),
    ("Source Needed", ["source needed"]),
    ("Team Context Used", ["team context used"]),
    ("Reviewer Decision", ["reviewer decision"]),
    ("Reviewer Comments", ["reviewer comments"]),
    ("Parastatal Type", ["parastatal type"]),
    ("Pillar", ["pillar"]),
    ("Tag", ["tag"]),
    ("Assessment Level", ["assessment level"]),
    ("Source Used", ["source used"]),
]

REVIEWER_DECISIONS = ["Agree", "Disagree", "Needs change"]

_HEADER_FILL = PatternFill("solid", fgColor="DDE7F0")


def _norm(value) -> str:
    return re.sub(r"[^a-z0-9/]+", " ", str(value or "").lower()).strip()


def _find_sheet(wb: Workbook, name: str) -> Worksheet | None:
    target = _norm(name)
    return next((ws for ws in wb.worksheets if _norm(ws.title) == target), None)


def _column_map(ws: Worksheet, columns) -> dict[str, int]:
    """Map canonical column -> 1-based index, adding missing columns at the end."""
    headers = {_norm(c.value): c.column for c in ws[1] if c.value}
    mapping: dict[str, int] = {}
    for canonical, aliases in columns:
        index = next(
            (
                headers[_norm(a)]
                for a in [canonical, *aliases]
                if _norm(a) in headers and headers[_norm(a)] not in mapping.values()
            ),
            None,
        )
        if index is None:
            index = ws.max_column + 1 if ws.max_column > 1 or ws["A1"].value else 1
            cell = ws.cell(row=1, column=index, value=canonical)
            cell.font, cell.fill = Font(bold=True), _HEADER_FILL
        mapping[canonical] = index
    return mapping


def _new_sheet(wb: Workbook, title: str, columns, widths: dict[str, int]) -> Worksheet:
    ws = wb.create_sheet(title)
    for index, (name, _) in enumerate(columns, start=1):
        cell = ws.cell(row=1, column=index, value=name)
        cell.font, cell.fill = Font(bold=True), _HEADER_FILL
        ws.column_dimensions[cell.column_letter].width = widths.get(name, 18)
    ws.freeze_panes = "A2"
    return ws


def _match_parastatal(value: str, parastatals: list[Parastatal]) -> Parastatal | None:
    text = _norm(value)
    return next(
        (
            p
            for p in parastatals
            if text in {_norm(p.id), _norm(p.name)}
            or _norm(p.id) in text.split()
            or _norm(p.name) in text
        ),
        None,
    )


def read_citation_sheet(
    path: Path, parastatals: list[Parastatal]
) -> tuple[list[Source], list[Issue]]:
    wb = load_workbook(path, data_only=True)
    ws = _find_sheet(wb, CITATION_SHEET)
    issues = []
    if ws is None:
        issues.append(
            Issue(
                phase="initial_checks",
                severity="info",
                audience="team",
                message=f"The previous workbook ({path.name}) has no {CITATION_SHEET}, so a new "
                "one will be built from scratch.",
            )
        )
        return [], issues
    headers = {_norm(c.value): c.column - 1 for c in ws[1] if c.value}

    def get(row, canonical):
        aliases = dict(CITATION_COLUMNS)[canonical]
        index = next(
            (headers[_norm(a)] for a in [canonical, *aliases] if _norm(a) in headers), None
        )
        return "" if index is None or row[index] is None else str(row[index]).strip()

    sources = []
    for row_no, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        url = get(row, "Official URL")
        if not url:
            continue
        parastatal = _match_parastatal(get(row, "Parastatal"), parastatals)
        if parastatal is None:
            issues.append(
                Issue(
                    phase="initial_checks",
                    severity="warning",
                    audience="team",
                    message=f'{CITATION_SHEET} row {row_no}: "{get(row, "Parastatal")}" '
                    "isn't one of the parastatals in this run, so that row was left as it is.",
                )
            )
            continue
        score = get(row, "Authority Score")
        sources.append(
            Source(
                parastatal_id=parastatal.id,
                title=get(row, "Source Title") or url,
                url=url,  # exact value from the sheet; never normalised
                source_type=get(row, "Source Type"),
                useful_for=get(row, "What This Source Is Useful For"),
                question_ids=[q.strip() for q in get(row, "Question IDs").split(",") if q.strip()],
                verification_status="Not verified",
                authority_score=float(score) if re.fullmatch(r"\d+(\.\d+)?", score) else 0,
                provenance="phase1_citation_sheet",
                notes=get(row, "Notes"),
            )
        )
    return sources, issues


class Link:
    """A clickable cell: shows `text`, opens `target` (a web URL or a local file path)."""

    def __init__(self, target: str, text: str | None = None):
        self.target, self.text = target, text or target


def _saved_copy(snapshot_path: str | None, workbook_dir: Path) -> Link | str:
    if not snapshot_path or not Path(snapshot_path).exists():
        return ""
    return Link(os.path.relpath(snapshot_path, workbook_dir), "Open saved copy")


def _source_values(s: Source, names: dict[str, str], workbook_dir: Path) -> dict[str, object]:
    return {
        "Citation ID": s.citation_id,
        "Parastatal": names.get(s.parastatal_id, s.parastatal_id),
        "Source Title": s.title,
        "Source Type": s.source_type,
        "Official URL": Link(s.url),  # exact URL, shown and opened unchanged
        "Saved Copy": _saved_copy(s.snapshot_path, workbook_dir),
        "What This Source Is Useful For": s.useful_for,
        "Question IDs": ", ".join(s.question_ids),
        "Accessibility": s.accessibility,
        "Current/Active Status": s.current_status,
        "Verification Status": s.verification_status,
        "Authority Score": s.authority_score,
        "Notes": s.notes,
        "Found By": s.found_by,
        "Last Checked": s.checked_at,
    }


_FILLS = {
    "green": PatternFill("solid", fgColor="E3F1E0"),
    "amber": PatternFill("solid", fgColor="FCEFD2"),
    "red": PatternFill("solid", fgColor="F8DEDC"),
    "grey": PatternFill("solid", fgColor="EEEEEE"),
}
STATUS_COLOURS = {
    "Answered — Verified Source": "green",
    "Computed from Sub-indicators": "green",
    "Verified": "green",
    "Partially Answered": "amber",
    "Human Verification Required": "amber",
    "Insufficient Evidence": "red",
    "Not verified": "red",
    "Not Applicable": "grey",
    "Not Yet Assessed": "grey",
}
_LINK_FONT = Font(color="1F5FA8", underline="single")


def _write_rows(ws: Worksheet, columns, rows: list[tuple[tuple, dict]], key_columns):
    """Update rows whose key matches; append the rest. `rows` = [(key, values)]."""
    mapping = _column_map(ws, columns)
    existing = {}
    for r in range(2, ws.max_row + 1):
        key = tuple(_norm(ws.cell(row=r, column=mapping[c]).value) for c in key_columns)
        if any(key):
            existing.setdefault(key, r)
    wrap = Alignment(wrap_text=True, vertical="top")
    for key, values in rows:
        r = existing.get(tuple(_norm(k) for k in key))
        if r is None:
            r = ws.max_row + 1
        for name, value in values.items():
            cell = ws.cell(row=r, column=mapping[name])
            if isinstance(value, Link):
                cell.value, cell.hyperlink, cell.font = value.text, value.target, _LINK_FONT
            else:
                cell.value = value
                if cell.hyperlink:
                    cell.hyperlink = None
            cell.alignment = wrap
            if isinstance(value, str) and value in STATUS_COLOURS:
                cell.fill = _FILLS[STATUS_COLOURS[value]]
    return mapping


def _add_dropdown(ws: Worksheet, column: int, options: list[str]) -> None:
    letter = ws.cell(row=1, column=column).column_letter
    validation = DataValidation(type="list", formula1=f'"{",".join(options)}"', allow_blank=True)
    validation.prompt, validation.promptTitle = "Choose one: " + ", ".join(options), "Decision"
    ws.add_data_validation(validation)
    validation.add(f"{letter}2:{letter}{max(ws.max_row, 2)}")


def _replace_sheet(wb: Workbook, title: str, index: int | None = None) -> Worksheet:
    if (old := _find_sheet(wb, title)) is not None:
        wb.remove(old)
    return wb.create_sheet(title, index)


def _write_guide(wb: Workbook) -> None:
    ws = _replace_sheet(wb, "How to Review", 0)
    ws.column_dimensions["A"].width = 32
    ws.column_dimensions["B"].width = 70
    ws.column_dimensions["C"].width = 60
    bold, title = Font(bold=True), Font(bold=True, size=14)
    rows: list[tuple] = [
        ("How to review this workbook",),
        (),
        (
            "1. Start with Needs Attention",
            "Problems to fix before trusting the results, in "
            'plain language. "Must fix" items come first.',
        ),
        (
            "2. Review each answer",
            "In the scoring sheet, Citation ID names the Citation Sheet row the answer relies "
            "on. Click the link in Citation URL, then use Where to Find It and Search Phrase "
            "(Ctrl+F on Windows, Cmd+F on Mac) to find the quote in Evidence Excerpt. Answers only "
            "ever use sources from the Citation Sheet.",
        ),
        (
            "3. If the website has changed",
            "Click Open saved copy to see the page exactly as it "
            "was when it was checked. Keep this workbook in the same folder as the evidence "
            "folder so these links work.",
        ),
        (
            "4. Record your decision",
            "Choose Agree, Disagree or Needs change in Reviewer "
            "Decision, and explain in Reviewer Comments.",
        ),
        (
            "5. Before sharing results",
            "Use Re-check links in the app to confirm every link "
            "still opens and still contains its quote.",
        ),
        (),
        ("What each Status means", "Meaning", "What to do"),
        *[(status, meaning, action) for status, (meaning, action) in STATUS_HELP.items()],
        (),
        ("Citation Sheet: Verification Status", "Meaning"),
        *[(status, meaning) for status, meaning in VERIFICATION_HELP.items()],
    ]
    for row in rows:
        ws.append(list(row))
    ws["A1"].font = title
    for r in range(1, ws.max_row + 1):
        ws.cell(row=r, column=1).font = bold
        for c in range(1, 4):
            ws.cell(row=r, column=c).alignment = Alignment(wrap_text=True, vertical="top")
        value = ws.cell(row=r, column=1).value
        if value in STATUS_COLOURS:
            ws.cell(row=r, column=1).fill = _FILLS[STATUS_COLOURS[value]]
        if value in {"What each Status means", "Citation Sheet: Verification Status"}:
            for c in range(1, 4):
                ws.cell(row=r, column=c).fill = _HEADER_FILL
                ws.cell(row=r, column=c).font = bold


def _write_issue_sheets(wb: Workbook, issues: list[Issue]) -> None:
    attention = _replace_sheet(wb, "Needs Attention", 1)
    for index, (name, width) in enumerate(
        [("Priority", 20), ("About", 22), ("What we found and what to do", 110)], start=1
    ):
        cell = attention.cell(row=1, column=index, value=name)
        cell.font, cell.fill = Font(bold=True), _HEADER_FILL
        attention.column_dimensions[cell.column_letter].width = width
    attention.freeze_panes = "A2"
    colour = {"error": "red", "warning": "amber", "info": "grey"}
    team = team_issues(issues)
    for issue in team:
        attention.append([severity_label(issue.severity), issue.ref or "", issue.message])
        attention.cell(row=attention.max_row, column=1).fill = _FILLS[colour[issue.severity]]
        attention.cell(row=attention.max_row, column=3).alignment = Alignment(wrap_text=True)
    if not team:
        attention.append(["", "", "Nothing needs your attention."])

    if (old := _find_sheet(wb, "QA Report")) is not None:  # sheet name used by older runs
        wb.remove(old)
    log = _replace_sheet(wb, "Technical Log")
    log.append(["Severity", "Phase", "Ref", "Audience", "Message"])
    for cell in log[1]:
        cell.font, cell.fill = Font(bold=True), _HEADER_FILL
    log.column_dimensions["C"].width = 40
    log.column_dimensions["E"].width = 110
    for i in issues:
        log.append([i.severity, i.phase, i.ref, i.audience, i.message])


def write_workbook(
    *,
    base: Path,
    out: Path,
    city_name: str,
    questions: dict[str, Question],
    selected: list[str],
    parastatals: list[Parastatal],
    applicability: dict[str, list[str]],
    sources: list[Source],
    answers: list[Answer],
    issues: list[Issue],
) -> Path:
    wb = load_workbook(base)
    names = {p.id: p.name for p in parastatals}
    out_dir = out.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    ws = _find_sheet(wb, CITATION_SHEET) or _new_sheet(
        wb,
        CITATION_SHEET,
        CITATION_COLUMNS,
        {
            "Source Title": 40,
            "Official URL": 50,
            "What This Source Is Useful For": 40,
            "Notes": 60,
            "Verification Status": 24,
        },
    )
    _write_rows(
        ws,
        CITATION_COLUMNS,
        [
            (
                (names.get(s.parastatal_id, s.parastatal_id), s.url),
                _source_values(s, names, out_dir),
            )
            for s in sources
        ],
        key_columns=["Parastatal", "Official URL"],
    )

    scoring_title = scoring_sheet_title(city_name)
    ws = _find_sheet(wb, scoring_title) or _new_sheet(
        wb,
        scoring_title,
        SCORING_COLUMNS,
        {
            "Question": 45,
            "Answer": 50,
            "Citation": 30,
            "Citation URL": 40,
            "Status": 26,
            "Where to Find It": 30,
            "Search Phrase": 30,
            "Evidence Excerpt": 45,
            "Notes": 60,
            "Reviewer Decision": 16,
            "Reviewer Comments": 40,
        },
    )
    by_key = {(a.parastatal_id, a.question_id): a for a in answers}
    rows = []
    for p in parastatals:
        for qid in selected:
            q = questions[qid]
            a = by_key.get((p.id, qid))
            if a is None and qid not in applicability.get(p.id, []):
                a = Answer(
                    parastatal_id=p.id,
                    question_id=qid,
                    status="Not Applicable",
                    notes=f"The question bank says this applies to: "
                    f"{q.applicability or 'not stated'}. {p.name} is a "
                    f"{p.type.replace('_', ' ')}.",
                )
            a = a or Answer(
                parastatal_id=p.id,
                question_id=qid,
                status="Not Yet Assessed",
                notes="Applies to this parastatal, but was not researched in this run.",
            )
            # Reviewer Decision / Comments are never written, so a re-run keeps them.
            rows.append(
                (
                    (p.name, q.raw_id),
                    {
                        "Parastatal": p.name,
                        "Question ID": q.raw_id,
                        "Question": q.text,
                        "Status": a.status,
                        "Answer": a.answer,
                        "Proposed Score": a.proposed_score,
                        "Max Score": q.max_score,
                        "Citation ID": a.citation_id,
                        "Citation": a.citation,
                        "Citation URL": Link(a.citation_url) if a.citation_url else "",
                        "Where to Find It": a.where_to_find,
                        "Search Phrase": a.search_phrase,
                        "Evidence Excerpt": a.evidence_excerpt,
                        "Saved Copy": _saved_copy(a.snapshot_path, out_dir),
                        "Notes": a.notes,
                        "Source Needed": a.missing_evidence,
                        "Team Context Used": ", ".join(a.memory_used),
                        "Parastatal Type": p.type,
                        "Pillar": q.pillar_name,
                        "Tag": q.tag,
                        "Assessment Level": q.assessment_level,
                        "Source Used": a.source_used,
                    },
                )
            )
    mapping = _write_rows(ws, SCORING_COLUMNS, rows, key_columns=["Parastatal", "Question ID"])
    _add_dropdown(ws, mapping["Reviewer Decision"], REVIEWER_DECISIONS)

    _write_guide(wb)
    _write_issue_sheets(wb, issues)
    wb.save(out)
    return out


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


def city_outcome(run) -> str:
    """One plain sentence describing how a city's run ended (for the index and the app)."""
    if run.status == "failed":
        return f"Stopped because of a problem: {run.error}"
    if run.blocked:
        must_fix = [i for i in team_issues(run.issues) if i.severity == "error"]
        first = must_fix[0].message if must_fix else "see Needs Attention"
        return f"Not run. Fix this first: {first}"
    if run.status != "finished":
        return "Not finished"
    if any("stopped at the review step" in i.message.lower() for i in run.issues):
        return "Stopped at the review step (not researched)"
    return "Done"


def coverage_counts(values: dict) -> tuple[int, int]:
    """(questions with at least one usable source, questions with none) after Step 1."""
    questions = values.get("questions", {})
    sources = [
        s
        for s in values.get("final_sources", [])
        if s.verification_status == "Verified" and s.use_for_answers
    ]
    covered = missing = 0
    for p in values.get("parastatals", []):
        if not p.include:
            continue
        for qid in values.get("applicability", {}).get(p.id, []):
            if questions[qid].is_rollup:
                continue
            if any(
                s.parastatal_id in (p.id, "All parastatals") and qid in s.question_ids
                for s in sources
            ):
                covered += 1
            else:
                missing += 1
    return covered, missing


def write_batch_summary(folder: Path, label: str, runs: dict, step: str = "answers") -> Path:
    """The index workbook for a run: one row per city, linking to its workbook."""
    from collections import Counter

    wb = Workbook()
    ws = wb.active
    ws.title = "All Cities"
    ws.append([label])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append(["One row per city. Click a link to open that city's workbook."])
    ws.append([])
    if step == "sources":
        columns = [
            "City",
            "Outcome",
            "Sources workbook",
            "Parastatals included",
            "Citations verified",
            "Questions with a source",
            "Questions with no source yet",
            "Problems that must be fixed",
        ]
    else:
        columns = [
            "City",
            "Outcome",
            "Answers workbook",
            "Questions researched",
            "Answered with a checked source",
            "Need a person to look",
            "No evidence found",
            "Problems that must be fixed",
        ]
    ws.append(columns)
    header_row = ws.max_row
    for cell in ws[header_row]:
        cell.font, cell.fill = Font(bold=True), _HEADER_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    for letter, width in zip("ABCDEFGH", [20, 60, 22, 14, 16, 14, 14, 16], strict=True):
        ws.column_dimensions[letter].width = width

    for run in runs.values():
        values = run.result or {}
        workbook = values.get("output_workbook")
        outcome = city_outcome(run)
        must_fix = sum(i.severity == "error" for i in team_issues(run.issues))
        if step == "sources":
            covered, missing = coverage_counts(values) if values.get("questions") else (0, 0)
            numbers = [
                sum(p.include for p in values.get("parastatals", [])),
                sum(s.verification_status == "Verified" for s in values.get("final_sources", [])),
                covered,
                missing,
            ]
        else:
            counts = Counter(a.status for a in run.answers)
            numbers = [
                sum(
                    n
                    for s, n in counts.items()
                    if s
                    not in {"Not Applicable", "Not Yet Assessed", "Computed from Sub-indicators"}
                ),
                counts["Answered — Verified Source"],
                counts["Human Verification Required"] + counts["Partially Answered"],
                counts["Insufficient Evidence"],
            ]
        ws.append([run.label, outcome, "", *numbers, must_fix])
        row = ws.max_row
        if workbook:
            cell = ws.cell(row=row, column=3, value="Open workbook")
            cell.hyperlink = os.path.relpath(workbook, folder)
            cell.font = _LINK_FONT
        colour = (
            "green" if outcome == "Done" else "amber" if outcome.startswith("Stopped at") else "red"
        )
        ws.cell(row=row, column=2).fill = _FILLS[colour]
        ws.cell(row=row, column=2).alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)

    folder.mkdir(parents=True, exist_ok=True)
    name = (
        "ASICS_All_Cities_Sources_Index.xlsx"
        if step == "sources"
        else "ASICS_All_Cities_Answers_Index.xlsx"
    )
    path = folder / name
    wb.save(path)
    return path


def write_checks_workbook(path: Path, city_name: str, issues: list[Issue]) -> Path:
    """A checks-only run's report: what needs attention, without touching any other file."""
    wb = Workbook()
    ws = wb.active
    ws.title = "About"
    ws.append([f"Checks for {city_name}"])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append(
        [
            "A checks-only run looks at the question bank and the city register, without "
            "any web research. See Needs Attention for anything to fix."
        ]
    )
    _write_issue_sheets(wb, issues)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path
