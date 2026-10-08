"""Step 3, AI scoring: the question-scorer agent fills the same workbook cells an intern would.

Step 3 comes after Step 2. For each question and agency in a city, the agent gets the Step 2
answer and the reviewed Citation Sheet (no web research), and gives the inputs the row above
each column asks for (e.g. YES / NO), the Citation ID it relied on and a word-for-word quote.
They are written into the AI copy of the vertical's workbook (scoring/2027/ai/<VERTICAL>_ai.xlsx),
whose formulas compute the points exactly as for people's scores.

Evidence rules, enforced in code (not just asked of the model):
- a city is scored only when Step 2 has answered it after the last change to its Sources
  workbook;
- when Step 2 found no evidence for a question, the AI isn't asked: the row is left for a
  person, with what evidence is missing;
- the Citation ID must be a reviewed, verified Citation Sheet row for that agency, and the
  quote must appear word for word in its saved text; otherwise the inputs are discarded;
- the document name and link are copied from the Citation Sheet, never written by the AI;
- every input must be one of the column's allowed values (or a number, as instructed).
Every row is logged to scoring/2027/ai/runs/<run>.jsonl (the audit trail).
"""

import json
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from openpyxl import load_workbook
from pydantic import BaseModel, Field

from asics_agent.links.text import locate_quote, rank_chunks
from asics_agent.llm import CallFailed, call_json
from asics_agent.scoring.human import (
    SEPARATOR,
    _code_matches,
    _input_problem,
    city_of,
    match_cities,
)
from asics_agent.scoring.phase2 import (
    NO_EVIDENCE,
    CityEvidence,
    StepTwoAnswer,
    bank_ids,
    load_evidence,
    phase2_status,
)
from asics_agent.scoring.recalc import RecalcUnavailable, recalculate
from asics_agent.scoring.template import QuestionSheet, VerticalTemplate
from asics_agent.tools import ToolContext
from asics_agent.verticals import CITY_UNIT_ID, agent_for

SOURCE_CHARS = 20000
SCORED_FILE = "scored_cities.json"


class ScoreReply(BaseModel):
    inputs: dict[str, str | float | int | None] = Field(default_factory=dict)
    citation_id: str = ""
    quote: str = ""
    chapter: str = ""
    provision: str = ""
    clause: str = ""
    comments: str = ""
    confidence: Literal["high", "medium", "low"] = "low"


@dataclass
class Task:
    code: str
    label: str
    city: str  # register name
    state: str
    agency: str  # agency ID


@dataclass
class ScoredCell:
    task: Task
    values: dict[int, object]  # column -> value to write
    log: dict
    outcome: str = "scored"  # "scored" | "needs_person" | "failed"
    kind: str = ""  # why it needs a person: a key of REASONS
    detail: str = ""  # the reason in full


@dataclass
class AIRunReport:
    path: Path
    scored: int = 0  # every input filled from checked evidence
    needs_person: int = 0  # no evidence in Step 2, or a check failed: left for a person
    failed: int = 0  # the call itself failed: run again
    cities: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    log_path: Path | None = None
    reasons: dict[str, int] = field(default_factory=dict)  # REASONS key -> rows


def ai_file(scoring_dir: Path, vertical: str) -> Path:
    return scoring_dir / "ai" / f"{vertical}_ai.xlsx"


def scored_cities(scoring_dir: Path, vertical: str) -> dict[str, str]:
    """{city: when the AI last scored it (ISO time)}."""
    path = scoring_dir / "ai" / SCORED_FILE
    try:
        return json.loads(path.read_text()).get(vertical, {})
    except (OSError, ValueError):
        return {}


def _mark_scored(scoring_dir: Path, vertical: str, cities: list[str]) -> None:
    path = scoring_dir / "ai" / SCORED_FILE
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        data = {}
    now = datetime.now().isoformat(timespec="seconds")
    data.setdefault(vertical, {}).update({c: now for c in cities})
    path.write_text(json.dumps(data, indent=2))


def question_details(template: VerticalTemplate, cache_dir: Path) -> dict[str, dict[str, str]]:
    """{code: {detail label: text}} from a calculated copy of the template (the details are
    formulas that look the question up in the questions list)."""
    copy = cache_dir / f"values_{template.path.name}"
    if not copy.exists() or copy.stat().st_mtime < template.path.stat().st_mtime:
        cache_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(template.path, copy)
        try:
            recalculate(copy, cache_dir)
        except RecalcUnavailable:
            pass  # fall back to whatever plain text the sheets hold
    wb = load_workbook(copy, data_only=True)
    details = {}
    for code, sheet in template.questions.items():
        ws = wb[sheet.sheet]
        details[code] = {
            label: str(ws.cell(row=r, column=2).value or "").strip()
            for label, r in sheet.details.items()
            if label != "Question Code"
        }
    return details


def plan_tasks(
    template: VerticalTemplate, register, settings, codes=None, cities=None
) -> tuple[list[Task], list[str], list[str]]:
    """(tasks, cities ready for Step 3, problems). Only cities Step 2 has answered."""
    mapping, problems = match_cities(template.labels, register)
    by_name = {c.name: c for c in register.values()}
    wanted = {c.casefold() for c in cities or []}
    chosen = [c for c in dict.fromkeys(mapping.values()) if not wanted or c.casefold() in wanted]
    ready = []
    for city in chosen:
        status = phase2_status(settings, city)
        if status.ready:
            ready.append(city)
        else:
            problems.append(f"{city} isn't ready for Step 3: {status.reason}")
    tasks = []
    for code, sheet in template.questions.items():
        if codes and not any(_code_matches(code, pattern) for pattern in codes):
            continue
        for label in sheet.rows:
            city = mapping.get(city_of(label))
            if city in ready:  # "City – Agency" rows, or the city government itself
                agency = (
                    label.split(SEPARATOR, 1)[1].strip() if SEPARATOR in label else CITY_UNIT_ID
                )
                tasks.append(Task(code, label, city, by_name[city].state, agency))
    return tasks, ready, problems


def _applies(ws, sheet: QuestionSheet, row: int) -> bool:
    from asics_agent.scoring.human import _applies as applies

    return applies(ws, sheet, row)


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _full_text(source) -> str:
    return Path(source.content_path).read_text(encoding="utf-8") if source.content_path else ""


def _prompt(
    task: Task, sheet: QuestionSheet, details: dict[str, str], answer: StepTwoAnswer, sources
) -> str:
    lines = [f"City: {task.city}", f"State: {task.state}", f"Agency: {task.agency}", ""]
    lines += [f"QUESTION {task.code}"]
    lines += [f"{label}: {text}" for label, text in details.items() if text]
    lines += ["", "INPUT COLUMNS (fill each one):"]
    for spec in sheet.inputs:
        allowed = f" Allowed values: {' / '.join(spec.options)}." if spec.options else ""
        lines.append(f'- "{spec.header}": {spec.instruction}.{allowed}')
    lines += [
        "",
        "STEP 2 ANSWER",
        f"Status: {answer.status}",
        f"Answer: {answer.answer}",
        f"Citation ID: {answer.citation_id or '(none)'}",
        f"Quoted evidence: {answer.evidence or '(none)'}",
        f"Notes: {answer.notes}",
        "",
        "CITATION SHEET SOURCES FOR THIS AGENCY: "
        + ", ".join(f"{s.citation_id} ({s.title})" for s in sources),
    ]
    cited = next((s for s in sources if s.citation_id == answer.citation_id), None)
    if cited:
        query = " ".join([*details.values(), answer.evidence])
        text, _ = rank_chunks(_full_text(cited), query, SOURCE_CHARS)
        lines += ["", f"=== CITATION {cited.citation_id}: {cited.title} ===", text]
    return "\n".join(lines)


# Why a row was left for a person, in plain words (the to-do sheet and the summary use these).
REASONS = {
    "no_evidence": "Step 2 found no evidence: a source needs to be found and added",
    "no_answer": "Step 2 has no answer for this question and agency",
    "mismatch": "Step 2 answered a different question under this code: the scoring workbook "
    "and the question bank don't match",
    "citation_changed": "Step 2's citation is no longer in the reviewed Citation Sheet",
    "check_failed": "The AI's citation or quote failed the check",
    "undecided": "The citation didn't settle every input",
    "failed": "The AI call failed: run Step 3 again",
}
_KIND_BY_START = [
    ("Step 2 has no answer", "no_answer"),
    ("The scoring workbook's question", "mismatch"),
    ("Step 2 found no evidence", "no_evidence"),
    ("Step 2 cited", "citation_changed"),
    ("The AI", "check_failed"),
]


def same_question(a: str, b: str) -> bool:
    """Is this the same question, allowing for small wording edits between versions?"""
    from difflib import SequenceMatcher

    # A sub-question sheet may show "main question >:< sub-question": compare the sub-question.
    a, b = _normalise(a.split(">:<")[-1]), _normalise(b.split(">:<")[-1])
    # Measured on the Parastatal and UPD banks: rewordings of the same question score 0.72+,
    # different questions under the same code score 0.33 or less.
    return a == b or SequenceMatcher(None, a, b).ratio() >= 0.6


def _for_person(task: Task, sheet: QuestionSheet, reason: str, log: dict) -> ScoredCell:
    log["left_for_person"] = reason
    kind = next((k for start, k in _KIND_BY_START if reason.startswith(start)), "check_failed")
    values = {sheet.comments_column: f"AI: left for a person. {reason}"}
    cell = ScoredCell(task, values if sheet.comments_column else {}, log, "needs_person")
    cell.kind, cell.detail = kind, reason
    return cell


def score_one(
    services, task: Task, sheet: QuestionSheet, details: dict[str, str], evidence: CityEvidence
) -> ScoredCell:
    log = {
        "code": task.code,
        "row": task.label,
        "question": details.get("Question", ""),
        "at": datetime.now().isoformat(timespec="seconds"),
    }
    answer = evidence.answers.get((task.agency, task.code))
    if answer is None:
        return _for_person(
            task,
            sheet,
            "Step 2 has no answer for this question and agency "
            "(was the agency added after Step 2?).",
            log,
        )
    log["step2_status"] = answer.status
    log["step2_answer"] = answer.answer[:1500]
    asked = details.get("Question", "")
    if asked and answer.question and not same_question(asked, answer.question):
        return _for_person(
            task,
            sheet,
            f"The scoring workbook's question {task.code} (\"{asked[:120]}\") isn't the "
            f'question Step 2 answered under that code ("{answer.question[:120]}"). Build '
            "the scoring workbook from the same question bank as Steps 1 and 2.",
            log,
        )
    if answer.status in NO_EVIDENCE or not answer.citation_id:
        needed = f" Source needed: {answer.source_needed}" if answer.source_needed else ""
        status = answer.status or "no status"
        return _for_person(task, sheet, f"Step 2 found no evidence ({status}).{needed}", log)
    sources = [c for c in evidence.citations if c.parastatal_id in (task.agency, "ALL")]
    if not any(s.citation_id == answer.citation_id for s in sources):
        return _for_person(
            task,
            sheet,
            f"Step 2 cited {answer.citation_id}, which is no longer "
            "a reviewed, verified Citation Sheet row. Run Step 2 again.",
            log,
        )
    ctx = ToolContext(services=services, citations=sources)
    try:
        reply, _, _ = call_json(
            services,
            agent_for(services.settings, "score"),
            _prompt(task, sheet, details, answer, sources),
            ScoreReply,
            tool_context=ctx,
        )
    except Exception as exc:  # one failed row must not stop the others
        reason = str(exc) if isinstance(exc, CallFailed) else f"error: {type(exc).__name__}"
        log["error"] = f"{type(exc).__name__}: {exc}"
        values = {sheet.comments_column: f"AI: not scored ({reason}). Run Step 3 again."}
        return ScoredCell(
            task, values if sheet.comments_column else {}, log, "failed", "failed", reason
        )
    log.update(reply.model_dump(), tools_used=ctx.log)

    # The evidence must be a real Citation Sheet row, quoted word for word.
    source = next((s for s in sources if s.citation_id == reply.citation_id.strip()), None)
    full = _full_text(source) if source else ""
    if source is None:
        return _for_person(
            task,
            sheet,
            f'The AI cited "{reply.citation_id}", which isn\'t a '
            f"reviewed Citation Sheet row for {task.agency}. Its answer was "
            f"discarded. AI comments: {reply.comments}",
            log,
        )
    if not reply.quote or _normalise(reply.quote) not in _normalise(full):
        return _for_person(
            task,
            sheet,
            f"The AI's quote couldn't be found word for word in "
            f"{source.citation_id}, so its answer was discarded. AI comments: "
            f"{reply.comments}",
            log,
        )

    values, notes = {}, []
    for spec in sheet.inputs:
        value = reply.inputs.get(spec.header, "")
        if value in (None, ""):
            notes.append(f'"{spec.header}" left blank: the Citation Sheet doesn\'t decide it.')
            continue
        if isinstance(value, str) and spec.options:
            value = next(
                (o for o in spec.options if o.casefold() == value.strip().casefold()), value.strip()
            )
        if problem := _input_problem(sheet, spec.column, value):
            notes.append(f'"{spec.header}" left blank: the AI gave "{value}", which {problem}.')
            continue
        values[spec.column] = _number_or_text(value)
    page, heading = locate_quote(full, reply.quote)
    found = {  # from the Citation Sheet and the saved text, not from the AI
        "Act Name/Web name/Doc name": f"{source.title} [{source.citation_id}]",
        "Link": source.url,
        "Page Number": str(page) if page else "",
        "Chapter": reply.chapter or (heading or ""),
        "Provision": reply.provision,
        "Clause": reply.clause,
    }
    for header, column in sheet.evidence.items():
        if found.get(header):
            values[column] = found[header]
    if sheet.comments_column:
        text = [
            f"AI ({reply.confidence} confidence), from Step 2 answer ({answer.status}) and "
            f"{source.citation_id}: {reply.comments}".strip(),
            f'Quote: "{reply.quote}"',
            *notes,
        ]
        values[sheet.comments_column] = "\n".join(text)
    if all(i.column in values for i in sheet.inputs):
        return ScoredCell(task, values, log, "scored")
    return ScoredCell(task, values, log, "needs_person", "undecided", " ".join(notes))


REVIEW_SHEET = "Scores (start here)"
OLD_REVIEW_SHEETS = ("AI scoring",)
YOUR_SCORE, YOUR_COMMENTS = "★ Your score", "★ Your comments"
REVIEW_COLUMNS = [
    "Question",
    "Row",
    "Question text",
    "AI score",
    "Max score",
    YOUR_SCORE,
    YOUR_COMMENTS,
    "Agrees with AI?",
    "Status",
    "Step 2 status",
    "Step 2 answer",
    "Citation",
    "Link",
    "Quote",
    "AI's reasoning",
    "Why left for a person",
]
_AI, _MAX, _YOURS, _AGREE = "D", "E", "F", "H"


def _review_rows(ws) -> dict[tuple[str, str], dict]:
    """Rows of an existing review sheet, by (question, row), as {column name: value}."""
    header = [str(c.value or "") for c in ws[1]]
    rows = {}
    for values in ws.iter_rows(min_row=2, values_only=True):
        if values and values[0]:
            rows[(str(values[0]), str(values[1]))] = dict(zip(header, values, strict=False))
    return rows


def _summary_sheet(
    wb, template: VerticalTemplate, results: list[ScoredCell], details: dict | None = None
) -> None:
    """The one sheet the team works from: every question and row the AI has handled, with
    the AI's score and why, the Step 2 answer and citation behind it, and highlighted columns
    for a person's own score and comments (kept when the AI scores again)."""
    from openpyxl.formatting.rule import FormulaRule
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    details = details or {}
    rows: dict[tuple[str, str], dict] = {}
    for name in (REVIEW_SHEET, *OLD_REVIEW_SHEETS):
        if name in wb.sheetnames:
            rows.update(_review_rows(wb[name]))
            wb.remove(wb[name])
    for cell in results:
        sheet = template.questions[cell.task.code]
        found = {h: cell.values.get(c, "") for h, c in sheet.evidence.items()}
        log, key = cell.log, (cell.task.code, cell.task.label)
        before = rows.get(key, {})
        rows[key] = {
            "Question": cell.task.code,
            "Row": cell.task.label,
            "Question text": log.get("question", ""),
            "Max score": details.get(cell.task.code, {}).get("Max Score", ""),
            YOUR_SCORE: before.get(YOUR_SCORE),  # a person's entries are never overwritten
            YOUR_COMMENTS: before.get(YOUR_COMMENTS),
            "Status": "Left for a person" if cell.kind else "Scored by AI",
            "Step 2 status": log.get("step2_status") or "(no answer)",
            "Step 2 answer": log.get("step2_answer", ""),
            "Citation": found.get("Act Name/Web name/Doc name", ""),
            "Link": found.get("Link", ""),
            "Quote": log.get("quote", "") if cell.kind in ("", "undecided") else "",
            "AI's reasoning": log.get("comments", ""),
            "Why left for a person": REASONS.get(cell.kind, "")
            + (f". {cell.detail}" if cell.detail else ""),
        }
    order = {
        (code, label): (i, j)
        for i, (code, sheet) in enumerate(template.questions.items())
        for j, label in enumerate(sheet.rows)
    }
    ws = wb.create_sheet(REVIEW_SHEET, 0)
    ws.append(REVIEW_COLUMNS)
    for r, key in enumerate(sorted(rows, key=lambda k: order.get(k, (10**6, 0))), start=2):
        row = rows[key]
        sheet = template.questions.get(key[0])
        if sheet and sheet.points_column and key[1] in sheet.rows:  # live from the workbook
            row["AI score"] = (
                f"=IFERROR('{sheet.sheet}'!{get_column_letter(sheet.points_column)}"
                f'{sheet.rows[key[1]]},"")'
            )
        row["Agrees with AI?"] = (
            f'=IF(OR({_YOURS}{r}="",NOT(ISNUMBER({_AI}{r}))),"",'
            f'IF(ABS({_YOURS}{r}-{_AI}{r})<0.001,"Yes","No"))'
        )
        ws.append([row.get(c) for c in REVIEW_COLUMNS])
    widths = [9, 24, 50, 9, 8, 12, 30, 10, 16, 20, 60, 36, 30, 50, 70, 50]
    yellow = PatternFill("solid", fgColor="FFF2B3")
    for c, (head, width) in enumerate(zip(ws[1], widths, strict=True), start=1):
        head.font, head.fill = Font(bold=True), PatternFill("solid", fgColor="DDE7F0")
        head.alignment = Alignment(wrap_text=True, vertical="top")
        ws.column_dimensions[get_column_letter(c)].width = width
    for c in (_YOURS, "G"):
        ws[f"{c}1"].fill = PatternFill("solid", fgColor="F2C200")
        for r in range(2, ws.max_row + 1):
            ws[f"{c}{r}"].fill = yellow
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    last = max(ws.max_row, 2)
    ws.conditional_formatting.add(  # rows the AI left: orange status
        f"I2:I{last}",
        FormulaRule(
            formula=['$I2="Left for a person"'], fill=PatternFill("solid", fgColor="FBD5B5")
        ),
    )
    ws.conditional_formatting.add(
        f"{_AGREE}2:{_AGREE}{last}",
        FormulaRule(formula=[f'${_AGREE}2="No"'], fill=PatternFill("solid", fgColor="F4B6B6")),
    )
    ws.freeze_panes = "D2"
    ws.auto_filter.ref = ws.dimensions
    wb.active = 0


def ai_copy(template: VerticalTemplate, out: Path) -> str:
    """Make sure the AI's copy matches the current scoring workbook. A new copy is made when
    there is none, or when the workbook has changed since (e.g. the experts updated it); the
    AI's earlier answers are carried over for questions and rows that still exist."""
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and out.stat().st_mtime >= template.path.stat().st_mtime:
        return ""
    old = load_workbook(out) if out.exists() else None
    shutil.copyfile(template.path, out)
    if old is None:
        return ""
    wb = load_workbook(out)
    kept = 0
    for name in (REVIEW_SHEET, *OLD_REVIEW_SHEETS):  # people's scores and the AI's notes
        if name in old.sheetnames:
            copy = wb.create_sheet(REVIEW_SHEET, 0)
            for values in old[name].iter_rows(values_only=True):
                copy.append(list(values))
            break
    for sheet in template.questions.values():
        if sheet.sheet not in old.sheetnames:
            continue
        before = old[sheet.sheet]
        heads = {
            str(before.cell(row=sheet.header_row, column=c).value or "").strip(): c
            for c in range(1, before.max_column + 1)
        }
        rows = {
            str(before.cell(row=r, column=1).value or "").strip(): r
            for r in range(sheet.header_row + 1, before.max_row + 1)
        }
        columns = [*sheet.evidence.values(), *(i.column for i in sheet.inputs)]
        if sheet.comments_column:
            columns.append(sheet.comments_column)
        ws = wb[sheet.sheet]
        for label, r in sheet.rows.items():
            if label not in rows:
                continue
            for c in columns:
                head = str(ws.cell(row=sheet.header_row, column=c).value or "").strip()
                value = (
                    before.cell(row=rows[label], column=heads[head]).value
                    if head in heads
                    else None
                )
                if value not in (None, "") and not str(value).startswith("="):
                    ws.cell(row=r, column=c, value=value)
                    kept += 1
    wb.save(out)
    return (
        f"The {out.stem.replace('_ai', '')} scoring workbook has changed since the AI last "
        f"scored, so its copy was rebuilt from the new one; {kept} earlier AI entries were "
        "kept for questions and rows that still exist."
    )


def _number_or_text(value):
    if isinstance(value, (int, float)):
        return value
    try:
        number = float(str(value).rstrip("%"))
        return int(number) if number == int(number) else number
    except ValueError:
        return value


def run_ai_scoring(
    services,
    template: VerticalTemplate,
    vertical: str,
    register,
    *,
    codes=None,
    cities=None,
    workers: int | None = None,
    on_progress=None,
) -> AIRunReport:
    """Score the chosen questions for the chosen cities that are ready (Step 2 done), write
    them into the AI copy, then calculate."""
    settings = services.settings
    out = ai_file(settings.scoring_dir, vertical)
    note = ai_copy(template, out)
    report = AIRunReport(out)
    tasks, report.cities, report.problems = plan_tasks(template, register, settings, codes, cities)
    if note:
        report.problems.insert(0, note)
    wb = load_workbook(out)
    tasks = [
        t
        for t in tasks
        if _applies(
            wb[template.questions[t.code].sheet],
            template.questions[t.code],
            template.questions[t.code].rows[t.label],
        )
    ]
    ids = bank_ids(settings)
    evidence = {c: load_evidence(phase2_status(settings, c), ids) for c in report.cities}
    for city, found in evidence.items():
        missing = sorted({t.agency for t in tasks if t.city == city} - set(found.parastatals))
        if missing:
            report.problems.append(
                f"{city}: {', '.join(missing)} in the scoring workbook aren't in the city's "
                "Sources workbook, so they have no evidence. Regenerate the scoring workbook "
                "(scripts/make_scoring_skeleton.py) after Step 1 changes the agencies."
            )
    details = question_details(template, settings.scoring_dir / ".cache")
    results: list[ScoredCell] = []
    with ThreadPoolExecutor(max_workers=workers or settings.max_concurrency) as pool:
        futures = [
            pool.submit(
                score_one,
                services,
                t,
                template.questions[t.code],
                details.get(t.code, {}),
                evidence[t.city],
            )
            for t in tasks
        ]
        for i, future in enumerate(futures, start=1):
            results.append(future.result())
            if on_progress:
                on_progress(i, len(futures))
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    report.log_path = out.parent / "runs" / f"{vertical}_{run_id}.jsonl"
    report.log_path.parent.mkdir(parents=True, exist_ok=True)
    with report.log_path.open("w") as log:
        for cell in results:
            sheet = template.questions[cell.task.code]
            ws = wb[sheet.sheet]
            r = sheet.rows[cell.task.label]
            for column in [*sheet.evidence.values(), *(i.column for i in sheet.inputs)]:
                ws.cell(row=r, column=column, value=None)  # replace the previous AI answer
            for column, value in cell.values.items():
                ws.cell(row=r, column=column, value=value)
            setattr(report, cell.outcome, getattr(report, cell.outcome) + 1)
            if cell.kind:
                report.reasons[cell.kind] = report.reasons.get(cell.kind, 0) + 1
            log.write(json.dumps(cell.log, default=str) + "\n")
    _summary_sheet(wb, template, results, details)
    wb.save(out)
    try:
        recalculate(out, settings.scoring_dir / ".cache")
    except RecalcUnavailable as exc:
        report.problems.append(str(exc))
    if results and not codes:  # a full run; a few questions is a trial, not "scored"
        _mark_scored(settings.scoring_dir, vertical, report.cities)
    return report
