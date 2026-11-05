"""The scoring steps, in the order the team runs them. Used by scripts/scoring.py and the app.

  check     each category's workbook follows the conventions; its cities match the register
  prepare   make each intern's copy from the assignments workbook
  merge     merge interns' work, calculate, and update the results workbook
  ai        the AI scores chosen questions/cities in its own copy; compared with people's

Folders (settings.scoring_dir, e.g. scoring/2027):
  templates/    the experts' scoring workbooks (one per category)
  assignments/  ASICS_2027_Scoring_Assignments.xlsx
  human/        one copy per intern per category; for a category scored in the team's
                templates: <category>/<section>/submissions/ (uploaded files, never edited)
  merged/       <SCORING_CODE>_human.xlsx: everyone's work, calculated; for the team's
                templates <SCORING_CODE>_<SECTION>_human.xlsx, built from the submissions
  ai/           <SCORING_CODE>_ai.xlsx: the AI's scores, calculated; runs/ has each call's log
  evals/        ASICS_2027_AI_Evals.xlsx: AI-vs-people agreement after each AI run
  results/      ASICS_2027_Scores.xlsx
"""

import dataclasses
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from asics_agent.categories import ULG_UNIT_ID, category_settings, load_bank, load_categories
from asics_agent.cities import load_register
from asics_agent.scoring import human
from asics_agent.scoring.ai import REASONS, ai_file, link_for_review, run_ai_scoring
from asics_agent.scoring.phase2 import bank_ids, load_evidence, phase2_status
from asics_agent.scoring.recalc import RecalcUnavailable, recalculate
from asics_agent.scoring.scores import (
    CategoryScores,
    add_eval_history,
    agreement,
    build_results,
    read_scores,
)
from asics_agent.scoring.template import read_template

RESULTS_FILE = "ASICS_2027_Scores.xlsx"
EVALS_FILE = "ASICS_2027_AI_Evals.xlsx"
DEFAULT_SCORING_WORKBOOKS = {  # scoring code -> its workbook in scoring/2027/templates
    "UPD": "ASICS_2027_UPD_Scoring_Workbook_v2.xlsx",
}  # (a category with `scoring_templates` is scored in copies of the team's templates instead)


@dataclass
class StepReport:
    title: str
    done: list[str] = field(default_factory=list)  # what happened
    problems: list[str] = field(default_factory=list)  # what needs a person's attention
    files: list[Path] = field(default_factory=list)
    # What each file is, for the app (path -> plain-language description)
    about: dict[Path, str] = field(default_factory=dict)
    breakdown: list[tuple[str, int]] = field(default_factory=list)  # why rows need a person
    skipped: list[str] = field(default_factory=list)  # rows a person chose to skip
    unregistered: list[str] = field(default_factory=list)  # merged but not in the register
    next_steps: list[str] = field(default_factory=list)  # what the team should do now
    cost: float | None = None  # US$ the AI calls cost (AI scoring runs)

    other: set[Path] = field(default_factory=set)  # shown under "Other files"

    def add_file(self, path: Path | None, about: str, other: bool = False) -> None:
        if path is not None:
            self.files.append(path)
            self.about[path] = about
            if other:
                self.other.add(path)


def assignments_path(settings) -> Path:
    path = settings.scoring_dir / "assignments" / human.ASSIGNMENTS_FILE
    if not path.exists():
        templates = settings.scoring_dir / "templates"
        human.write_assignments_template(
            path, {v: f for v, f in DEFAULT_SCORING_WORKBOOKS.items() if (templates / f).exists()}
        )
    return path


def configured(settings) -> dict:
    """{scoring code: that category's settings} for every category in agent_setup/categories/.
    These have Steps 1 and 2, so Step 3 scores them from their own answers and citations."""
    found, _ = load_categories(settings.agent_setup_dir)
    return {v.scoring_code: category_settings(settings, v.name) for v in found.values()}


def _plan(settings):
    register, _ = load_register(settings.city_register)
    skip = {v.scoring_code for v in configured(settings).values() if v.scoring_templates}
    plan, templates = human.read_plan(
        assignments_path(settings), settings.scoring_dir / "templates", register, skip
    )
    for code, vs in configured(settings).items():  # the category's own scoring workbook
        if code not in templates and vs.scoring_workbook and vs.scoring_workbook.exists():
            plan.categories[code] = vs.scoring_workbook
            templates[code] = read_template(vs.scoring_workbook)
    return plan, templates, register


def unit_of(label: str) -> str:
    """The unit a scoring-workbook row is about: the agency in "City – Agency", else the city
    government itself."""
    from asics_agent.scoring.name_resolution import split_label

    return split_label(label)[1] or ULG_UNIT_ID


def check(settings) -> StepReport:
    report = StepReport("Check scoring workbooks")
    plan, templates, register = _plan(settings)
    report.problems += plan.problems
    for code, template in templates.items():
        report.done.append(
            f"{code}: {len(template.questions)} question sheets, "
            f"{len(template.labels)} rows ({template.path.name})."
        )
        report.problems += [f"{code}: {p}" for p in template.problems]
        _, city_problems = human.match_cities(template.labels, register)
        report.problems += [f"{code}: {p}" for p in city_problems]
    for code, vs in configured(settings).items():
        if code in templates:
            report.problems += [f"{code}: {p}" for p in bank_mismatches(vs, templates[code])]
        if vs.scoring_templates:  # scored in copies of the team's templates
            from asics_agent.scoring.template_scoring import check_templates

            found, problems = check_templates(vs)
            report.done += [f"{vs.category_title}: {line}" for line in found]
            report.problems += [f"{vs.category_title}: {p}" for p in problems]
    return report


def bank_mismatches(vs, template) -> list[str]:
    """Questions whose text differs between the scoring workbook and the question bank that
    Steps 1 and 2 use. Step 3 won't score these, since the answer may be to another question."""
    from asics_agent.scoring.ai import question_details, same_question

    questions, _ = load_bank(vs)
    by_code = {q.id.replace(" ", ""): q for q in questions.values()}
    details = question_details(template, vs.scoring_dir / ".cache")
    problems = []
    for code in template.questions:
        asked = details.get(code, {}).get("Question", "")
        q = by_code.get(code)
        if q is None:
            problems.append(
                f"{code} is a retired question: it is in the scoring workbook but no longer "
                "in the question bank, so Step 2 never answers it and Step 3 leaves it out."
            )
        elif asked and not same_question(asked, q.text):
            problems.append(
                f'{code} is a different question in the scoring workbook ("{asked[:80]}") '
                f'and in the question bank ("{q.text[:80]}"). Step 3 won\'t score it '
                "until both use the same version."
            )
    return problems


def prepare(settings) -> StepReport:
    report = StepReport("Make interns' copies")
    plan, templates, register = _plan(settings)
    report.problems += plan.problems
    evidence: dict[str, dict] = {}  # scoring code -> city -> CityEvidence
    mappings: dict[str, dict] = {}
    for code, vs in configured(settings).items():
        if code not in templates:
            continue
        # Scored from Step 2: only cities this category's Step 2 has answered.
        mapping, _ = human.match_cities(templates[code].labels, register)
        status = {c: phase2_status(vs, c) for c in set(mapping.values())}
        ids = bank_ids(vs)
        ready = {c: load_evidence(s, ids) for c, s in status.items() if s.ready}
        evidence[code], mappings[code] = ready, mapping
        for a in (a for a in plan.assignments if a.category == code):
            waiting = sorted(
                {mapping.get(human.city_of(r), human.city_of(r)) for r in a.rows} - set(ready)
            )
            for city in waiting:
                reason = status[city].reason if city in status else "not in the city register."
                report.problems.append(
                    f"{a.intern}: {city} left out of the copy, not ready for Step 3: {reason}"
                )
            a.rows = [r for r in a.rows if mapping.get(human.city_of(r)) in ready]
    plan.assignments = [a for a in plan.assignments if a.rows]

    def evidence_for(scoring_code, code, label):
        city = mappings.get(scoring_code, {}).get(human.city_of(label))
        found = evidence.get(scoring_code, {}).get(city)
        answer = found.answers.get((unit_of(label), code)) if found else None
        if answer is None:
            return None
        source = next((c for c in found.citations if c.citation_id == answer.citation_id), None)
        return {
            "Step 2 status": answer.status,
            "Citation ID": answer.citation_id,
            "Source": source.title if source else "",
            "Link": source.url if source else "",
            "Quote": answer.evidence,
            "Step 2 answer": answer.answer[:1500],
            "Source needed": answer.source_needed if not answer.citation_id else "",
        }

    report.done += human.prepare_intern_copies(plan, templates, settings.scoring_dir, evidence_for)
    for a in sorted({(a.category, a.intern) for a in plan.assignments}):
        report.add_file(
            human.intern_file(settings.scoring_dir, *a),
            f"{a[1]}'s {a[0]} copy: send it to them to fill in (their rows are in yellow).",
        )
    if report.files:
        report.next_steps = [
            "Send each intern their copy. They fill in only their yellow rows and send it back "
            "(or save it in place, in scoring/2027/human/).",
            "Then press Merge and calculate, as often as you like.",
        ]
    return report


def merge(settings, scoring_codes: list[str] | None = None) -> StepReport:
    """Merge every category with assignments, calculate, and rebuild the results workbook."""
    report = StepReport("Merge and calculate scores")
    plan, templates, _ = _plan(settings)
    report.problems += plan.problems
    profile = settings.scoring_dir / ".cache"
    wanted = scoring_codes or list(dict.fromkeys(a.category for a in plan.assignments))
    for code in wanted:
        result = human.merge_category(plan, templates, code, settings.scoring_dir)
        done = sum(d for d, _ in result.done.values())
        total = sum(t for _, t in result.done.values())
        report.done.append(
            f"{code}: merged {len(result.done)} intern(s); {done} of "
            f"{total} assigned rows complete."
        )
        report.problems += [f"{code}: {p}" for p in result.problems]
        report.add_file(
            result.path,
            f"{code}: everyone's work together, calculated. The Merge report sheet lists "
            "what needs a look.",
        )
        try:
            recalculate(result.path, profile)
        except RecalcUnavailable as e:
            report.problems.append(str(e))
            return report
    report.add_file(
        results(settings, templates),
        "All scores: each city and category, people and AI side by side.",
    )
    report.done.append("Updated the results workbook.")
    report.next_steps = [
        "Sort out anything under Needs a look (conflicting answers, values not allowed) in "
        "the interns' copies, then merge again.",
        "Compare people's and the AI's scores on the Scores page.",
    ]
    return report


def prepare_templates(settings) -> StepReport:
    """Intern copies of a category scored in the team's templates (see human_copies)."""
    from asics_agent.scoring import human_copies

    report = StepReport("Make interns' copies")
    made = human_copies.prepare_copies(settings)
    report.done += made.done
    report.problems += made.problems
    for path in made.files:
        report.add_file(
            path, f"{path.stem}: send it to the intern to fill in (their rows are yellow)."
        )
    if made.files:
        report.next_steps = [
            "Send each intern their copy. They fill in their yellow rows, save it as .xlsx and "
            "send it back.",
            "Upload what comes back above, then press Merge and calculate.",
        ]
    return report


def merge_templates(settings) -> StepReport:
    """Merge the uploaded submissions of a category scored in the team's templates (human_merge)."""
    from asics_agent.scoring import human_merge

    report = StepReport("Merge and calculate scores")
    merged = human_merge.merge_category(settings)
    report.done += merged.done
    report.problems += merged.needs_a_look()
    report.skipped += merged.skipped
    report.unregistered += [
        f"{u['parastatal'] or u['city']} ({u['city']}), {u['rows']} row(s)"
        for u in merged.unregistered
    ]
    for path in merged.files:
        report.add_file(
            path,
            f"{path.stem}: everyone's uploaded work together, calculated by the template.",
        )
    if merged.files and not merged.calculated:
        report.problems.append(
            "The workbooks hold the inputs but not calculated scores (LibreOffice is missing or "
            "its result did not match): the score calculates when a file is opened in Excel."
        )
    if merged.files:
        report.next_steps = [
            "Agree on anything under Needs a look with the scorers, upload corrected files, and "
            "merge again.",
            "Compare people's and the AI's scores on the Scores page.",
        ]
    return report


def refresh_scores(settings) -> StepReport:
    """After people have entered scores in Excel: recalculate each category's scoring
    workbook and rebuild the results, so the totals include their scores."""
    report = StepReport("Update scores")
    _, templates, _ = _plan(settings)
    for code, vs in configured(settings).items():
        path = ai_file(vs.scoring_dir, code)
        if not path.exists() or code not in templates:
            continue
        try:
            link_for_review(path, templates[code], vs.scoring_dir / ".cache")
            recalculate(path, vs.scoring_dir / ".cache")
        except RecalcUnavailable as exc:
            report.problems.append(str(exc))
            return report
        except (RuntimeError, PermissionError) as exc:  # e.g. open in Excel and locked
            report.problems.append(f"{path.name}: {exc} Close it in Excel and try again.")
            continue
        report.done.append(f"Recalculated {path.name}.")
    report.add_file(
        results(settings), "Every city and category, including people's scores.", other=True
    )
    return report


def results(settings, templates: dict | None = None, eval_label: str = "") -> Path:
    """Rebuild the results workbook from whatever calculated files exist. With an
    `eval_label` (after an AI run), also record AI-vs-people agreement in the evals history."""
    if templates is None:
        _, templates, _ = _plan(settings)
    found: list[CategoryScores] = []
    evals = []
    for code, template in templates.items():
        pair = {}
        for source, path in [
            ("People", settings.scoring_dir / "merged" / f"{code}_human.xlsx"),
            ("AI", ai_file(settings.scoring_dir, code)),
        ]:
            if path.exists():
                pair[source] = read_scores(template, path, code, source)
                found.append(pair[source])
        if len(pair) == 2:
            evals.append(agreement(pair["People"], pair["AI"], set(template.questions)))
    if eval_label and evals:
        add_eval_history(evals, settings.scoring_dir / "evals" / EVALS_FILE, eval_label)
    register, _ = load_register(settings.city_register)
    names = {}
    for city in register.values():
        for name in [city.name, *city.aliases]:
            names[name.casefold()] = city.name
    categories, _ = load_categories(settings.agent_setup_dir)
    return build_results(
        found,
        settings.scoring_dir / "results" / RESULTS_FILE,
        canon=lambda city: names.get(city.casefold(), city),
        only={city.name for city in register.values()},
        titles={c.scoring_code: c.title for c in categories.values()},
    )


def step3_category(settings) -> str:
    """The scoring code of the category being run (e.g. PARASTATAL)."""
    return settings.scoring_code


def practice_template(vs, services) -> Path:
    """A scoring workbook for the practice cities, from the category's question bank."""
    from asics_agent.scoring.skeleton import build_skeleton, gather_units

    path = services.settings.scoring_dir / "templates" / f"PRACTICE_{vs.scoring_code}.xlsx"
    sources = list(services.settings.outputs_dir.glob("cities/*/ASICS_*_Sources.xlsx"))
    newest = max((f.stat().st_mtime for f in sources), default=0)
    if path.exists() and path.stat().st_mtime >= newest:
        return path  # its rows (the practice agencies) haven't changed
    questions, issues = load_bank(vs)
    units, _ = gather_units(services.settings)
    build_skeleton(questions, units, path, vs.scoring_code, issues)
    return path


def ai_score(
    settings,
    scoring_code: str,
    *,
    codes=None,
    cities=None,
    practice=False,
    on_progress=None,
    group: str | None = None,
) -> StepReport:
    """Step 3 with the AI: score the chosen questions for the chosen cities that the
    category's Step 2 has answered, from its answers and Citation Sheet only."""
    from asics_agent.costs import RunMeter
    from asics_agent.practice import practice_services
    from asics_agent.services import default_services

    meter, started = RunMeter(), datetime.now()
    report = StepReport(f"Step 3 · AI scoring: {scoring_code}")
    vs = configured(settings).get(scoring_code)
    if vs is None:
        report.problems.append(
            f"{scoring_code} has no settings file in agent_setup/categories/, so it has no Steps 1 "
            "and 2 to score from. People can score it (assign it to interns); see the README "
            "to add the category."
        )
        return report
    if vs.scoring_templates:  # scored in copies of the team's templates
        return _ai_score_templates(
            vs, report, meter, started, practice, codes, cities, on_progress, group
        )
    if practice:  # scripted AI, sample cities; needs a practice Step 1 and Step 2 first
        services = practice_services(vs)
        services.settings = dataclasses.replace(
            services.settings, scoring_dir=vs.scoring_dir / "practice"
        )
        register, _ = load_register(services.settings.city_register)
        template = read_template(practice_template(vs, services))
        templates = {scoring_code: template}
    else:
        _, templates, register = _plan(vs)
        if scoring_code not in templates:
            report.problems.append(
                f"{scoring_code} has no scoring workbook: set scoring_workbook in its settings "
                "file, or add it to the Categories sheet of the assignments workbook."
            )
            return report
        services = default_services()
        services.settings = vs
        template = templates[scoring_code]
    run = run_ai_scoring(
        services,
        template,
        scoring_code,
        register,
        codes=codes,
        cities=cities,
        on_progress=on_progress,
    )
    report.problems += run.problems
    if not run.cities:
        report.problems.append("No city is ready for Step 3 yet: run Step 2 first.")
        return report
    left = run.needs_person + run.failed
    if not practice:
        from asics_agent.costs import record_run

        saved = record_run(
            services.settings,
            meter,
            step=3,
            label=f"Step 3 · AI scoring · {scoring_code} · {', '.join(run.cities)}",
            cities=list(run.cities),
            work=run.scored + left,
            started=started,
            group=group,
        )
        if saved:
            report.cost = json.loads(saved.read_text())["total_usd"]
    report.done.append(
        f"Scored {', '.join(run.cities)}: the AI scored {run.scored} row(s) from checked "
        f"evidence and left {left} for a person."
    )
    report.breakdown = [
        (REASONS[k], n) for k, n in sorted(run.reasons.items(), key=lambda x: -x[1])
    ]
    label = f"{scoring_code} AI run" + (" (practice)" if practice else "")
    scores = results(services.settings, templates, eval_label=label)
    report.add_file(
        run.path,
        "The one workbook to use. Its first sheet, Scores (start here), has every question: "
        "the AI's score and why, the Step 2 answer and citation behind it, and yellow columns "
        "for your own score and comments. Filter Status for the rows left for a person.",
    )
    report.add_file(
        scores,
        "Every city and category side by side (also on the Scores page).",
        other=True,
    )
    report.add_file(run.log_path, "Technical log of every row (for developers).", other=True)
    if run.reasons.get("no_evidence"):
        report.next_steps.append(
            "Rows with no evidence need a source: add it to the city's Sources workbook "
            "(City files), run Step 2 again for that city, then Step 3."
        )
    if left:
        report.next_steps.append(
            "Open the workbook and filter Status to 'Left for a person': score those yourself "
            "in the yellow ★ Your score column (the reason is in the last column)."
        )
    report.next_steps.append(
        "Check the AI's scores: read the Step 2 answer, citation and the AI's reasoning, and "
        "enter your own score where you disagree. Your score becomes the Final score and the "
        "totals use it; 'Agrees with AI?' turns red where you differ."
    )
    report.next_steps.append(
        "Save and close the workbook, then press Update scores on the Scores page to see the "
        "city totals with your scores."
    )
    from asics_agent.outputs_index import refresh_index

    if not practice:
        refresh_index(settings)
    if run.failed:
        report.problems.append(
            f"{run.failed} row(s) couldn't be scored because the AI call failed. Run Step 3 "
            "again to retry them."
        )
    return report


def _ai_score_templates(
    vs, report: StepReport, meter, started, practice, codes, cities, on_progress, group
) -> StepReport:
    """Step 3 for a category scored in the team's templates (settings: scoring_templates)."""
    from asics_agent.practice import practice_services
    from asics_agent.scoring.template_scoring import run_template_scoring
    from asics_agent.services import default_services

    if practice:  # scripted AI, sample cities; needs a practice Step 1 and Step 2 first
        services = practice_services(vs)
        services.settings = dataclasses.replace(
            services.settings, scoring_dir=vs.scoring_dir / "practice"
        )
    else:
        services = default_services()
        services.settings = vs
    settings = services.settings
    register, _ = load_register(settings.city_register)
    run = run_template_scoring(
        services, settings, register, codes=codes, cities=cities, on_progress=on_progress
    )
    report.problems += run.problems
    if not run.cities:
        report.problems.append("No city is ready for Step 3 yet: run Step 2 first.")
        return report
    left = run.needs_person + run.failed
    if not practice:
        from asics_agent.costs import record_run

        saved = record_run(
            settings,
            meter,
            step=3,
            label=f"Step 3 · AI scoring · {vs.scoring_code} · {', '.join(run.cities)}",
            cities=list(run.cities),
            work=run.scored + left,
            started=started,
            group=group,
        )
        if saved:
            report.cost = json.loads(saved.read_text())["total_usd"]
    report.done.append(
        f"Scored {', '.join(run.cities)}: the AI filled {run.scored} row(s) of the templates from "
        f"checked evidence and left {left} for a person."
    )
    report.breakdown = [
        (REASONS[k], n) for k, n in sorted(run.reasons.items(), key=lambda x: -x[1])
    ]
    from asics_agent.scoring.template_scoring import NOT_SCORED_REASONS

    report.breakdown += [
        (f"Not scored by the AI: {NOT_SCORED_REASONS[k]}", n)
        for k, n in sorted(run.skipped.items(), key=lambda x: -x[1])
        if k in ("no_max", "benchmark")
    ]
    for path in run.paths:
        report.add_file(
            path,
            "The AI's copy of this template: the same layout and cells people fill, with the "
            "AI's inputs and evidence. The template's formulas calculate the scores."
            + ("" if run.calculated else " The score calculates when the file is opened in Excel."),
        )
    report.add_file(run.log_path, "Technical log of every row (for developers).", other=True)
    if run.reasons.get("no_evidence"):
        report.next_steps.append(
            "Rows with no evidence need a source: add it to the city's Sources workbook "
            "(City files), run Step 2 again for that city, then Step 3."
        )
    report.next_steps.append(
        "Compare the AI's scores with people's on the Scores page (Consolidated and Compare tabs)."
    )
    if not run.calculated:
        report.problems.append(
            "The scores are not calculated in these files yet: they calculate when a file is "
            "opened in Excel."
        )
    from asics_agent.outputs_index import refresh_index

    if not practice:
        refresh_index(settings)
    if run.failed:
        report.problems.append(
            f"{run.failed} row(s) couldn't be scored because the AI call failed. Run Step 3 "
            "again to retry them."
        )
    return report
