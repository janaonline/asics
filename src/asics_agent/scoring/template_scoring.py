"""Step 3 for a category scored in the team's templates: the AI fills a COPY of each template.

For each ready city (Step 2 done), unit (a parastatal, or the city's ULG) and question that
applies, the question-scorer agent gets the Step 2 answer and the reviewed Citation Sheet (no web
research) and gives the template's own input values, the evidence and a short comment. They are
written into scoring/2027/ai/<SCORING CODE>_<SECTION>_AI.xlsx, laid out exactly like the team's
template, whose formulas calculate the scores (see template_fill.py for what may be written).

The evidence rules are the ones of the older Step 3 (ai.check_step2 / ai.check_reply_evidence):
no answer, no evidence, a different question under the code, a citation no longer in the reviewed
sheet, or a quote not word for word in the saved page -> the row is left blank for a person.
Nothing here names a category: the unit ("parastatal" or "ulg") decides what a row is.
"""

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from asics_agent.agent_setup import fingerprint as setup_fingerprint
from asics_agent.applicability import applies_to
from asics_agent.bank_version import settings_version
from asics_agent.categories import ULG_UNIT_ID, agent_for, load_bank
from asics_agent.keep_awake import keep_awake
from asics_agent.links.text import locate_quote, rank_chunks
from asics_agent.llm import CallFailed, call_json
from asics_agent.models import Parastatal
from asics_agent.parastatal_types import ULG_TYPE, type_label
from asics_agent.run_options import current_options
from asics_agent.scoring.ai import (
    _KIND_BY_START,
    SOURCE_CHARS,
    AIRunReport,
    ScoreReply,
    _mark_scored,
    check_reply_evidence,
    check_step2,
    scored_cities,
)
from asics_agent.scoring.human import SEPARATOR, _code_matches
from asics_agent.scoring.phase2 import (
    CityEvidence,
    StepTwoAnswer,
    bank_ids,
    load_evidence,
    phase2_status,
)
from asics_agent.scoring.score_levels import score_levels
from asics_agent.scoring.template_fill import (
    AITemplate,
    ai_path,
    check_value,
    open_ai_template,
    read_info,
    template_hash,
    write_info,
)
from asics_agent.scoring.template_import import (
    SheetSpec,
    read_filled_template,
    section_of,
)
from asics_agent.tools import ToolContext

NOT_SCORED_REASONS = {
    "no_max": "this question has no maximum score in the template (the team did not score it)",
    "benchmark": "its score needs a benchmark from other cities, which the AI can't supply",
    "no_type": "the template has no row for this kind of parastatal",
    "not_applicable": "it does not apply to this parastatal",
    "template_problem": "the template has a problem the team must fix (see the issues below)",
}
# why a row is left for a person that the team should see in the run's issue list, not only in the cell
ISSUE_KINDS = {"off_level", "years", "template_problem"}


@dataclass
class TemplateTask:
    section: str
    code: str
    city: str  # the register's name
    state: str
    unit: str  # the parastatal's ID, or the ULG's
    label: str  # "City – BWSSB" (a parastatal) or the city (the ULG)
    parastatal: Parastatal


@dataclass
class TemplateCell:
    task: TemplateTask
    values: dict[int, object]  # column -> value to write
    log: dict
    outcome: str = "scored"  # "scored" | "needs_person" | "failed"
    kind: str = ""
    detail: str = ""
    notes: list[str] = field(default_factory=list)


@dataclass
class TemplateRunReport(AIRunReport):
    paths: list[Path] = field(default_factory=list)
    calculated: bool = True  # every file holds calculated values
    skipped: dict[str, int] = field(default_factory=dict)  # NOT_SCORED_REASONS key -> rows


def label_for(unit: str, city: str, parastatal: Parastatal) -> str:
    return city if unit == "ulg" else f"{city}{SEPARATOR}{parastatal.id}"


def _unit_name(unit: str, parastatal: Parastatal) -> str:
    """What identifies the unit in a template row's Parastatal Name cell ("" for the ULG)."""
    return "" if unit == "ulg" else parastatal.id


def template_sections(paths) -> dict[str, Path]:
    """{section: template path} for the category's templates (the section is read from the file)."""
    from openpyxl import load_workbook

    from asics_agent.scoring.template_import import read_structures

    out = {}
    for path in paths:
        try:
            specs = read_structures(load_workbook(path))
        except Exception:
            continue
        section = section_of(specs)
        if section:
            out[section] = Path(path)
    return out


# -- the prompt ----------------------------------------------------------------------------------
def _hint(col) -> str:
    if col.options:
        return "choose one"
    if col.numeric:
        return "a number" + (f" (at least {col.minimum:g})" if col.minimum is not None else "")
    return "text"


def build_prompt(
    task: TemplateTask, spec: SheetSpec, answer: StepTwoAnswer, sources, unit_word: str
) -> str:
    lines = [f"City: {task.city}", f"State: {task.state}", f"{unit_word}: {task.unit}", ""]
    lines += [f"QUESTION {task.code}"]
    for label in ("Question", "Applicability (source)", "Detailed Methodology"):
        if spec.details.get(label):
            lines.append(f"{label}: {spec.details[label]}")
    for label, text in spec.details.items():
        if label.lower().startswith(("evidence", "notes")) and text:
            lines.append(f"{label}: {text}")
    if spec.max_score is not None:
        lines.append(f"Max Score: {spec.max_score:g}")
    if spec.inputs:
        lines += ["", "INPUT COLUMNS (fill each one):"]
        for col in spec.inputs:
            allowed = f" Allowed values: {' / '.join(col.options)}." if col.options else ""
            lines.append(f'- "{col.header}": {_hint(col)}.{allowed}')
    if spec.score_column and not spec.score_is_formula and spec.max_score is not None:
        lines += [
            "",
            f'SCORE: give "score" as a number from 0 to {spec.max_score:g} (the points for this '
            "row, decided from the methodology's bands).",
            *_score_scale(spec),
        ]
    lines += [
        "",
        "STEP 2 ANSWER",
        f"Status: {answer.status}",
        f"Answer: {answer.answer}",
        f"Citation ID: {answer.citation_id or '(none)'}",
        f"Quoted evidence: {answer.evidence or '(none)'}",
        f"Notes: {answer.notes}",
        "",
        "CITATION SHEET SOURCES FOR THIS UNIT: "
        + ", ".join(f"{s.citation_id} ({s.title})" for s in sources),
    ]
    cited = next((s for s in sources if s.citation_id == answer.citation_id), None)
    if cited and cited.content_path:
        text = Path(cited.content_path).read_text(encoding="utf-8")
        query = " ".join(
            [spec.question, spec.details.get("Detailed Methodology", ""), answer.evidence]
        )
        excerpt, _ = rank_chunks(text, query, SOURCE_CHARS)
        lines += ["", f"=== CITATION {cited.citation_id}: {cited.title} ===", excerpt]
    return "\n".join(lines)


def _levels(spec: SheetSpec):
    """The rule for the points a typed-score question may take (see score_levels.py)."""
    if spec.max_score is None or spec.score_is_formula or not spec.score_column:
        return None
    return score_levels(spec.details.get("Detailed Methodology", ""), spec.max_score)


def _score_scale(spec: SheetSpec) -> list[str]:
    """What the scorer is told about the scale: the Points cell takes 0 to the Max Score."""
    rule = _levels(spec)
    if rule is None:
        return []
    maximum = f"{spec.max_score:g}"
    if rule.kind == "free":
        return [
            f"PARTIAL CREDIT: this question can earn part of its score ({rule.basis}). Give the "
            f"points the parts add up to, any value from 0 to {maximum}."
        ]
    lines = [
        f"ALLOWED SCORES: {rule.allowed_text()}. The Points cell takes 0 to {maximum}: give "
        "exactly one of these values. Any other value is discarded, not converted."
    ]
    if rule.above_max:
        top = max(rule.listed)
        lines.append(
            f"The methodology lists a level of {top:g}, which the cell cannot take: enter "
            f"{maximum} for it. The other levels are entered as written."
        )
    return lines


# -- one row -------------------------------------------------------------------------------------
def _left(task: TemplateTask, spec: SheetSpec, reason: str, log: dict) -> TemplateCell:
    log["left_for_person"] = reason
    kind = next((k for start, k in _KIND_BY_START if reason.startswith(start)), "check_failed")
    col = spec.column_for("comments")
    # No Step 2 answer at all: the row stays blank (not scored); every other reason is a note a
    # person can read in the Scorer Comments.
    values = {col: f"AI: left for a person. {reason}"} if col and kind != "no_answer" else {}
    return TemplateCell(task, values, log, "needs_person", kind, reason)


def score_template_one(
    services, task: TemplateTask, spec: SheetSpec, evidence: CityEvidence, run_id: str
) -> TemplateCell:
    log = {
        "section": task.section,
        "code": task.code,
        "row": task.label,
        "question": spec.question,
        "at": datetime.now().isoformat(timespec="seconds"),
    }
    if spec.problems:  # never ask the model about a question whose headers cannot be trusted
        return _template_problem(task, spec, log)
    answer, sources, reason = check_step2(task.code, task.unit, spec.question, evidence, log)
    if reason:
        return _left(task, spec, reason, log)
    unit_word = services.settings.unit_label
    ctx = ToolContext(services=services, citations=sources)
    try:
        reply, _, _ = call_json(
            services,
            agent_for(services.settings, "score"),
            build_prompt(task, spec, answer, sources, unit_word),
            ScoreReply,
            tool_context=ctx,
        )
    except Exception as exc:  # one failed row must not stop the others
        why = str(exc) if isinstance(exc, CallFailed) else f"error: {type(exc).__name__}"
        log["error"] = f"{type(exc).__name__}: {exc}"
        col = spec.column_for("comments")
        values = {col: f"AI: not scored ({why}). Run Step 3 again."} if col else {}
        return TemplateCell(task, values, log, "failed", "failed", why)
    log.update(reply.model_dump(), tools_used=ctx.log)
    source, full, reason = check_reply_evidence(reply, sources, task.unit)
    if reason:
        return _left(task, spec, reason, log)

    values: dict[int, object] = {}
    notes: list[str] = []
    for col in spec.inputs:
        value = reply.inputs.get(col.header, "")
        if value in (None, ""):
            notes.append(f'"{col.header}" left blank: the Citation Sheet doesn\'t decide it.')
            continue
        ok, why = check_value(spec, col.column, value)
        if why:
            notes.append(f'"{col.header}" left blank: the AI gave "{value}", which {why}.')
            continue
        values[col.column] = ok
    complete, kind, detail, based_on = True, "undecided", "", ""
    if spec.score_is_formula and spec.min_years and spec.year_groups:
        # The template scores from at least N valid years (its own formula: Years with valid
        # data < N gives 0), so the row is written when N years have every figure the formula needs.
        groups = spec.year_groups
        done = [y for y, cols in groups.items() if all(c in values for c in cols)]
        if len(done) >= spec.min_years:
            for year in groups:
                if year not in done:  # a half-filled year is not written
                    dropped = [
                        c
                        for c in values
                        if spec.columns.get(c) and spec.columns[c].header.startswith(f"{year} ")
                    ]
                    for c in dropped:
                        del values[c]
                    notes.append(f"{year} left out: not every figure the template needs was found.")
            based_on = f"Based on {len(done)} of {len(groups)} years ({', '.join(done)})."
            log["years_used"] = done
        else:
            complete, kind = False, "years"
            detail = (
                f"found {len(done)} of {len(groups)} years with every figure the template needs; "
                f"it needs at least {spec.min_years}. Left for a person (the AI does not write a "
                "calculated 0: not finding the figures is not proof they do not exist)."
            )
            notes.append(detail)
    elif spec.score_is_formula:
        # The template calculates the points; a row with an input missing that the points need
        # could show a calculated 0, which would read as "scored zero": write none of the inputs.
        missing = [spec.columns[c].header for c in spec.required_inputs if c not in values]
        if missing:
            complete = False
            notes.append(
                "Not written, because the template's score needs a value for: "
                + ", ".join(missing)
                + "."
            )
    elif spec.score_column:
        complete, kind, detail = _typed_score(reply, spec, values, notes)
    if not complete:
        values = {}  # nothing partial reaches the template
    page, heading = locate_quote(full, reply.quote)
    found = {
        "source_link": source.url,
        "page": str(page) if page else "",
        "chapter": reply.chapter or (heading or ""),
        "provision": reply.provision,
        "clause": reply.clause,
        "latest_information": reply.latest_information,
    }
    for fld, text in found.items():
        col = spec.column_for(fld)
        if col and text and complete:
            values[col] = text
    comments = [
        f"AI ({reply.confidence} confidence), from Step 2 answer ({answer.status}) and "
        f"{source.citation_id}: {reply.comments}".strip()
        + (f" {based_on}" if based_on else ""),
        f'Quote: "{reply.quote}"',
        *notes,
    ]
    if col := spec.column_for("comments"):
        values[col] = "\n".join(comments)
    options = current_options()
    if col := spec.column_for("additional_comments"):
        values[col] = " | ".join(
            part
            for part in (
                "Scored by AI",
                f"Citation {source.citation_id}: {source.title}",
                f"Step 2 class {answer.answer_class}" if answer.answer_class else "",
                f"Step 2 confidence {answer.confidence}" if answer.confidence else "",
                f"model {options.model or services.settings.model}",
                f"run {run_id}",
            )
            if part
        )
    log["notes"] = notes
    if complete:
        return TemplateCell(task, values, log, "scored", notes=notes)
    return TemplateCell(task, values, log, "needs_person", kind, detail or " ".join(notes), notes)


def _template_problem(task: TemplateTask, spec: SheetSpec, log: dict) -> TemplateCell:
    text = f"template problem: {'; '.join(spec.problems)}. Fix the template, then run Step 3 again."
    log["left_for_person"] = text
    col = spec.column_for("comments")
    values = {col: f"AI: not scored ({text})"} if col else {}
    return TemplateCell(task, values, log, "needs_person", "template_problem", text)


def _typed_score(reply: ScoreReply, spec: SheetSpec, values: dict, notes: list) -> tuple:
    """Check the AI's points for a typed-score question and put them in `values`.

    Returns (complete, kind, detail). Fixed levels: the score must be one of them; free or partial
    credit: 0 to the Max Score. A score that is not allowed is not written and not converted."""
    rule = _levels(spec)
    if reply.score in (None, ""):
        notes.append("Score left blank: the Citation Sheet doesn't decide it.")
        return False, "undecided", ""
    try:
        number = float(reply.score)
    except (TypeError, ValueError):
        number = None
    if (
        number is not None
        and rule is not None
        and rule.kind == "levels"
        and not rule.allows(number)
    ):
        detail = (
            f"the AI gave {number:g}; the allowed scores are {rule.allowed_text()} "
            f"(the Points cell takes 0 to {spec.max_score:g})."
        )
        notes.append(f"Score not written: {detail}")
        return False, "off_level", detail
    ok, why = check_value(spec, spec.score_column, reply.score if number is None else number)
    if why:
        detail = f'the AI gave "{reply.score}", which {why}.'
        notes.append(f"Score not written: {detail}")
        return False, "off_level", detail
    values[spec.score_column] = ok
    return True, "", ""


# -- planning ------------------------------------------------------------------------------------
def plan(settings, ais: dict[str, AITemplate], register, bank, codes=None, cities=None):
    """(tasks, ready cities, evidence by city, problems, skipped counts). Also adds the cities'
    units and the rows of every applicable question to the AI files."""
    problems: list[str] = []
    skipped: dict[str, int] = {}
    wanted = {c.casefold() for c in cities or []}
    ready, evidence = [], {}
    ids = bank_ids(settings)
    for city in register.values():
        if wanted and city.name.casefold() not in wanted:
            continue
        status = phase2_status(settings, city.name)
        if status.ready:
            ready.append(city.name)
            evidence[city.name] = load_evidence(status, ids)
        else:
            problems.append(f"{city.name} isn't ready for Step 3: {status.reason}")
    tasks: list[TemplateTask] = []
    by_name = {c.name: c for c in register.values()}
    for city in ready:
        units = evidence[city].parastatals
        if settings.unit == "ulg":
            units = {ULG_UNIT_ID: next(iter(units.values()), None) or _ulg_unit(by_name[city])}
        for unit_id, parastatal in units.items():
            who = _unit_name(settings.unit, parastatal)
            for ai in ais.values():
                if settings.unit != "ulg":
                    for problem in ai.ensure_unit(
                        city,
                        who,
                        type_label(parastatal.type) if parastatal.type != ULG_TYPE else "",
                    ):
                        if problem not in problems:
                            problems.append(problem)
                for code, spec in ai.specs.items():
                    if spec.problems:
                        key = f"{code}: template problem: {'; '.join(spec.problems)}. Fix the template."
                        if key not in problems:
                            problems.append(key)
                        skipped["template_problem"] = skipped.get("template_problem", 0) + 1
                        continue
                    question = bank.get(code)
                    if question is None:
                        key = f"{code} is not in the current question bank."
                        if key not in problems:
                            problems.append(key)
                        continue
                    if applies_to(question, parastatal) is False:
                        skipped["not_applicable"] = skipped.get("not_applicable", 0) + 1
                        continue
                    types = ai.applicable_types(code)
                    if (
                        settings.unit != "ulg"
                        and types is not None
                        and parastatal.type not in types
                    ):
                        skipped["no_type"] = skipped.get("no_type", 0) + 1
                        continue
                    ai.ensure_row(code, city, who)  # the row people fill too
                    if codes and not any(_code_matches(code, p) for p in codes):
                        continue
                    if spec.max_score is None and not spec.score_is_formula:
                        skipped["no_max"] = skipped.get("no_max", 0) + 1
                        continue
                    if spec.needs_benchmark:
                        skipped["benchmark"] = skipped.get("benchmark", 0) + 1
                        continue
                    tasks.append(
                        TemplateTask(
                            ai.section,
                            code,
                            city,
                            by_name[city].state,
                            unit_id,
                            label_for(settings.unit, city, parastatal),
                            parastatal,
                        )
                    )
    return tasks, ready, evidence, problems, skipped


def _ulg_unit(city) -> Parastatal:
    return Parastatal(id=ULG_UNIT_ID, name=city.ulg or city.name, type=ULG_TYPE)


# -- carrying the AI's cells over to a rebuilt file ---------------------------------------------
def carry_over(ai: AITemplate, old: Path) -> list[str]:
    """Copy what the AI wrote in `old` (an earlier build of this file) into the rebuilt `ai`."""
    notes: list[str] = []
    try:
        read = read_filled_template(old)
    except Exception as exc:
        return [f"The earlier file could not be read, so nothing was carried over ({exc})."]
    for cfg in read.config:
        if cfg.active and cfg.parastatal and not ai.has_unit(cfg.city, cfg.parastatal):
            ai.ensure_unit(cfg.city, cfg.parastatal, cfg.parastatal_type)
    moved = lost = 0
    for row in read.rows:
        spec = ai.specs.get(row.code)
        if spec is None:
            lost += 1
            continue
        target = ai.ensure_row(row.code, row.city, row.parastatal)
        if target is None:
            lost += 1
            continue
        values: dict[int, object] = {}
        by_header = {c.header: c.column for c in spec.columns.values() if c.kind == "input"}
        for header, value in row.inputs.items():
            if header in by_header:
                values[by_header[header]] = value
        if spec.score_column and not spec.score_is_formula:
            values[spec.score_column] = row.score
        for fld, value in (
            ("chapter", row.chapter),
            ("provision", row.provision),
            ("clause", row.clause),
            ("page", row.page),
            ("comments", row.comments),
            ("additional_comments", row.additional_comments),
            ("source_link", row.source_link),
            ("latest_information", row.latest_information),
        ):
            if (col := spec.column_for(fld)) and value:
                values[col] = value
        if values:
            result = ai.write(row.code, target, values)
            moved += bool(result.written)
            lost += bool(result.rejected)
    notes.append(f"Carried over {moved} row(s) of the AI's work; {lost} could not move.")
    return notes


# -- the run -------------------------------------------------------------------------------------
def run_template_scoring(
    services,
    settings,
    register,
    *,
    codes=None,
    cities=None,
    workers: int | None = None,
    on_progress=None,
) -> TemplateRunReport:
    """Score the chosen questions for the chosen ready cities into copies of the templates."""
    scoring_dir = settings.scoring_dir
    report = TemplateRunReport(path=Path())
    sections = template_sections(settings.scoring_templates)
    if not sections:
        report.problems.append(
            f"None of the scoring templates in {settings.category}'s settings could be read."
        )
        return report
    ais: dict[str, AITemplate] = {}
    for section, template in sections.items():
        ai, notes = open_ai_template(
            ai_path(scoring_dir, settings.scoring_code, section),
            template,
            carry_over=carry_over,
        )
        ais[section] = ai
        report.problems += notes
    bank, _ = load_bank(settings)
    tasks, report.cities, evidence, problems, report.skipped = plan(
        settings, ais, register, bank, codes, cities
    )
    report.problems += problems
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    results: list[TemplateCell] = []
    with keep_awake(), ThreadPoolExecutor(max_workers=workers or settings.max_concurrency) as pool:
        futures = [
            pool.submit(
                score_template_one,
                services,
                t,
                ais[t.section].specs[t.code],
                evidence[t.city],
                run_id,
            )
            for t in tasks
        ]
        for i, future in enumerate(futures, start=1):
            results.append(future.result())
            if on_progress:
                on_progress(i, len(futures))
    runs = scoring_dir / "ai" / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    logs = {section: runs / f"{settings.scoring_code}_{section}_{run_id}.jsonl" for section in ais}
    handles = {section: path.open("w") for section, path in logs.items()}
    try:
        for cell in results:
            ai = ais[cell.task.section]
            spec = ai.specs[cell.task.code]
            row = ai.row_of(
                cell.task.code, cell.task.city, _unit_name(settings.unit, cell.task.parastatal)
            )
            if row is None:
                report.problems.append(f"{cell.task.label} / {cell.task.code}: no row to write to.")
                continue
            ai.clear(cell.task.code, row)
            written = ai.write(cell.task.code, row, cell.values)
            for rejected in written.rejected:
                text = f"{cell.task.label}: {rejected}"
                if text not in report.problems:
                    report.problems.append(text)
            setattr(report, cell.outcome, getattr(report, cell.outcome) + 1)
            if cell.kind in ISSUE_KINDS and cell.task.code:
                issue = f"{cell.task.code}, {cell.task.label}: {cell.detail}"
                if issue not in report.problems:
                    report.problems.append(issue)
            if cell.kind:
                report.reasons[cell.kind] = report.reasons.get(cell.kind, 0) + 1
            handles[cell.task.section].write(json.dumps(cell.log, default=str) + "\n")
            del spec
    finally:
        for handle in handles.values():
            handle.close()
    report.log_path = next(iter(logs.values()), None)
    options = current_options()
    version = settings_version(settings)
    for section, ai in ais.items():
        saved = ai.save(scoring_dir / ".cache", scoring_dir / "ai" / "history")
        report.problems += saved.problems
        if saved.calculated:
            report.problems += _check_valid_years(
                saved.path, [r for r in results if r.task.section == section]
            )
        report.paths.append(saved.path)
        report.calculated = report.calculated and saved.calculated
        info = read_info(saved.path)
        info.update(
            scorer="AI",
            section=section,
            template=sections[section].name,
            template_sha256=template_hash(sections[section]),
            agent="question-scorer",
            model=options.model or settings.model,
            effort=options.effort or settings.effort,
            agent_setup_fingerprint=setup_fingerprint(settings.agent_setup_dir),
            bank_version=version.as_dict() if version else None,
            calculated=saved.calculated,
            last_run_id=run_id,
        )
        cities_info = info.setdefault("cities", {})
        for city in report.cities:
            cities_info[city] = {
                "run_id": run_id,
                "at": datetime.now().isoformat(timespec="seconds"),
            }
        write_info(saved.path, info)
    report.path = report.paths[0] if report.paths else Path()
    if results and not codes:  # a full run; a few questions is a trial, not "scored"
        _mark_scored(scoring_dir, settings.scoring_code, report.cities)
    return report


def _check_valid_years(path: Path, cells: list) -> list[str]:
    """After the template has calculated: does it count as many valid years as the AI assumed?
    (A budget of 0 is not a valid year.) A difference is reported, never hidden."""
    expected = {
        (c.task.city, c.task.unit, c.task.code): len(c.log["years_used"])
        for c in cells
        if c.outcome == "scored" and c.log.get("years_used")
    }
    if not expected:
        return []
    out = []
    try:
        rows = read_filled_template(path, "AI").rows
    except Exception:
        return []
    for row in rows:
        want = expected.get((row.city, row.parastatal, row.code))
        have = next(
            (v for h, v in row.calculated.items() if h.strip().lower() == "years with valid data"),
            None,
        )
        if want is not None and have is not None and int(have) != want:
            out.append(
                f"{row.code}, {row.city} / {row.parastatal}: the template counts {int(have)} valid "
                f"year(s) but the AI wrote {want} (a zero budget or spending is not a valid year). "
                "A person should check the score."
            )
    return out


def ai_cities(scoring_dir: Path, scoring_code: str) -> dict[str, str]:
    """{city: when the AI last scored it}, as for the older Step 3."""
    return scored_cities(scoring_dir, scoring_code)


def check_templates(settings) -> tuple[list[str], list[str]]:
    """(what was found, problems) for the category's templates: can they be read, which questions
    are retired or now ask something else than the question bank."""
    from asics_agent.scoring.ai import same_question

    done, problems = [], []
    bank, _ = load_bank(settings)
    for path in settings.scoring_templates:
        if not Path(path).exists():
            problems.append(f"The scoring template {Path(path).name} is missing.")
            continue
        sections = template_sections([path])
        if not sections:
            problems.append(f"{Path(path).name} has no question sheets we can read.")
            continue
        section, template = next(iter(sections.items()))
        ai = AITemplate(Path(path), Path(path))
        done.append(
            f"{section}: {len(ai.specs)} question sheets in {template.name}, "
            f"{len(ai.config_rows())} parastatal row(s) in its Configuration."
        )
        for code, spec in ai.specs.items():
            question = bank.get(code)
            if question is None:
                problems.append(
                    f"{code} is a retired question: it is in {template.name} but no longer in "
                    "the question bank, so Step 2 never answers it and Step 3 leaves it out."
                )
            elif spec.question and not same_question(spec.question, question.text):
                problems.append(
                    f'{code} is a different question in {template.name} ("{spec.question[:80]}") '
                    f'and in the question bank ("{question.text[:80]}"). Step 3 won\'t score it '
                    "until both use the same version."
                )
        for code, question in bank.items():
            if (
                question.id.split(" ")[0] == section
                and code not in ai.specs
                and not question.is_rollup
            ):
                problems.append(
                    f"{code} is in the question bank but has no sheet in {template.name}, so "
                    "Step 3 can't score it."
                )
    return done, problems
