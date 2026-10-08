"""The scoring steps, in the order the team runs them. Used by scripts/scoring.py and the app.

  check     each vertical's workbook follows the conventions; its cities match the register
  prepare   make each intern's copy from the assignments workbook
  merge     merge interns' work, calculate, and update the results workbook
  ai        the AI scores chosen questions/cities in its own copy; compared with people's

Folders (settings.scoring_dir, e.g. scoring/2027):
  templates/    the experts' scoring workbooks (one per vertical)
  assignments/  ASICS_2027_Scoring_Assignments.xlsx
  human/        one copy per intern per vertical
  merged/       <VERTICAL>_human.xlsx: everyone's work, calculated
  ai/           <VERTICAL>_ai.xlsx: the AI's scores, calculated; runs/ has each call's log
  evals/        ASICS_2027_AI_Evals.xlsx: AI-vs-people agreement after each AI run
  results/      ASICS_2027_Scores.xlsx
"""

import dataclasses
from dataclasses import dataclass, field
from pathlib import Path

from asics_agent.cities import load_register
from asics_agent.scoring import human
from asics_agent.scoring.ai import REASONS, ai_file, run_ai_scoring
from asics_agent.scoring.phase2 import bank_ids, load_evidence, phase2_status
from asics_agent.scoring.recalc import RecalcUnavailable, recalculate
from asics_agent.scoring.scores import (
    VerticalScores,
    add_eval_history,
    agreement,
    build_results,
    read_scores,
)
from asics_agent.scoring.template import read_template
from asics_agent.verticals import CITY_UNIT_ID, load_bank, load_verticals, settings_for

RESULTS_FILE = "ASICS_2027_Scores.xlsx"
EVALS_FILE = "ASICS_2027_AI_Evals.xlsx"
DEFAULT_VERTICALS = {
    "UPD": "ASICS_2027_UPD_Scoring_Workbook_v2.xlsx",
    "PARASTATAL": "ASICS_2027_Parastatal_Scoring_Workbook_DRAFT.xlsx",
}


@dataclass
class StepReport:
    title: str
    done: list[str] = field(default_factory=list)  # what happened
    problems: list[str] = field(default_factory=list)  # what needs a person's attention
    files: list[Path] = field(default_factory=list)
    # What each file is, for the app (path -> plain-language description)
    about: dict[Path, str] = field(default_factory=dict)
    breakdown: list[tuple[str, int]] = field(default_factory=list)  # why rows need a person
    next_steps: list[str] = field(default_factory=list)  # what the team should do now

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
            path, {v: f for v, f in DEFAULT_VERTICALS.items() if (templates / f).exists()}
        )
    return path


def configured(settings) -> dict:
    """{vertical code: that vertical's settings} for every vertical in agent_setup/verticals/.
    These have Steps 1 and 2, so Step 3 scores them from their own answers and citations."""
    found, _ = load_verticals(settings.agent_setup_dir)
    return {v.code: settings_for(settings, v.name) for v in found.values()}


def _plan(settings):
    register, _ = load_register(settings.city_register)
    plan, templates = human.read_plan(
        assignments_path(settings), settings.scoring_dir / "templates", register
    )
    for code, vs in configured(settings).items():  # the vertical's own scoring workbook
        if code not in templates and vs.scoring_workbook and vs.scoring_workbook.exists():
            plan.verticals[code] = vs.scoring_workbook
            templates[code] = read_template(vs.scoring_workbook)
    return plan, templates, register


def unit_of(label: str) -> str:
    """The unit a scoring-workbook row is about: the agency in "City – Agency", else the city
    government itself."""
    return label.split(human.SEPARATOR, 1)[1].strip() if human.SEPARATOR in label else CITY_UNIT_ID


def check(settings) -> StepReport:
    report = StepReport("Check scoring workbooks")
    plan, templates, register = _plan(settings)
    report.problems += plan.problems
    for vertical, template in templates.items():
        report.done.append(
            f"{vertical}: {len(template.questions)} question sheets, "
            f"{len(template.labels)} rows ({template.path.name})."
        )
        report.problems += [f"{vertical}: {p}" for p in template.problems]
        _, city_problems = human.match_cities(template.labels, register)
        report.problems += [f"{vertical}: {p}" for p in city_problems]
    for code, vs in configured(settings).items():
        if code in templates:
            report.problems += [f"{code}: {p}" for p in bank_mismatches(vs, templates[code])]
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
                f"{code} is in the scoring workbook but not in the question bank, "
                "so Step 2 never answers it."
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
    evidence: dict[str, dict] = {}  # vertical -> city -> CityEvidence
    mappings: dict[str, dict] = {}
    for vertical, vs in configured(settings).items():
        if vertical not in templates:
            continue
        # Scored from Step 2: only cities this vertical's Step 2 has answered.
        mapping, _ = human.match_cities(templates[vertical].labels, register)
        status = {c: phase2_status(vs, c) for c in set(mapping.values())}
        ids = bank_ids(vs)
        ready = {c: load_evidence(s, ids) for c, s in status.items() if s.ready}
        evidence[vertical], mappings[vertical] = ready, mapping
        for a in (a for a in plan.assignments if a.vertical == vertical):
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

    def evidence_for(vertical, code, label):
        city = mappings.get(vertical, {}).get(human.city_of(label))
        found = evidence.get(vertical, {}).get(city)
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
    for a in sorted({(a.vertical, a.intern) for a in plan.assignments}):
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


def merge(settings, verticals: list[str] | None = None) -> StepReport:
    """Merge every vertical with assignments, calculate, and rebuild the results workbook."""
    report = StepReport("Merge and calculate scores")
    plan, templates, _ = _plan(settings)
    report.problems += plan.problems
    profile = settings.scoring_dir / ".cache"
    wanted = verticals or list(dict.fromkeys(a.vertical for a in plan.assignments))
    for vertical in wanted:
        result = human.merge_vertical(plan, templates, vertical, settings.scoring_dir)
        done = sum(d for d, _ in result.done.values())
        total = sum(t for _, t in result.done.values())
        report.done.append(
            f"{vertical}: merged {len(result.done)} intern(s); {done} of "
            f"{total} assigned rows complete."
        )
        report.problems += [f"{vertical}: {p}" for p in result.problems]
        report.add_file(
            result.path,
            f"{vertical}: everyone's work together, calculated. The Merge report sheet lists "
            "what needs a look.",
        )
        try:
            recalculate(result.path, profile)
        except RecalcUnavailable as e:
            report.problems.append(str(e))
            return report
    report.add_file(
        results(settings, templates),
        "All scores: each city and vertical, people and AI side by side.",
    )
    report.done.append("Updated the results workbook.")
    report.next_steps = [
        "Sort out anything under Needs a look (conflicting answers, values not allowed) in "
        "the interns' copies, then merge again.",
        "Compare people's and the AI's scores on the Scores page.",
    ]
    return report


def results(settings, templates: dict | None = None, eval_label: str = "") -> Path:
    """Rebuild the results workbook from whatever calculated files exist. With an
    `eval_label` (after an AI run), also record AI-vs-people agreement in the evals history."""
    if templates is None:
        _, templates, _ = _plan(settings)
    found: list[VerticalScores] = []
    evals = []
    for vertical, template in templates.items():
        pair = {}
        for source, path in [
            ("People", settings.scoring_dir / "merged" / f"{vertical}_human.xlsx"),
            ("AI", ai_file(settings.scoring_dir, vertical)),
        ]:
            if path.exists():
                pair[source] = read_scores(template, path, vertical, source)
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
    return build_results(
        found,
        settings.scoring_dir / "results" / RESULTS_FILE,
        canon=lambda city: names.get(city.casefold(), city),
    )


def step3_vertical(settings) -> str:
    """The code of the vertical being run (e.g. PARASTATAL)."""
    return settings.vertical_code


def practice_template(vs, services) -> Path:
    """A scoring workbook for the practice cities, from the vertical's question bank."""
    from asics_agent.scoring.skeleton import build_skeleton, gather_units

    path = services.settings.scoring_dir / "templates" / f"PRACTICE_{vs.vertical_code}.xlsx"
    sources = list(services.settings.outputs_dir.glob("cities/*/ASICS_*_Sources.xlsx"))
    newest = max((f.stat().st_mtime for f in sources), default=0)
    if path.exists() and path.stat().st_mtime >= newest:
        return path  # its rows (the practice agencies) haven't changed
    questions, issues = load_bank(vs)
    units, _ = gather_units(services.settings)
    build_skeleton(questions, units, path, vs.vertical_code, issues)
    return path


def ai_score(
    settings, vertical: str, *, codes=None, cities=None, practice=False, on_progress=None
) -> StepReport:
    """Step 3 with the AI: score the chosen questions for the chosen cities that the
    vertical's Step 2 has answered, from its answers and Citation Sheet only."""
    from asics_agent.practice import practice_services
    from asics_agent.services import default_services

    report = StepReport(f"Step 3 · AI scoring: {vertical}")
    vs = configured(settings).get(vertical)
    if vs is None:
        report.problems.append(
            f"{vertical} has no settings file in agent_setup/verticals/, so it has no Steps 1 "
            "and 2 to score from. People can score it (assign it to interns); see the README "
            "to add the vertical."
        )
        return report
    if practice:  # scripted AI, sample cities; needs a practice Step 1 and Step 2 first
        services = practice_services(vs)
        services.settings = dataclasses.replace(
            services.settings, scoring_dir=vs.scoring_dir / "practice"
        )
        register, _ = load_register(services.settings.city_register)
        template = read_template(practice_template(vs, services))
        templates = {vertical: template}
    else:
        _, templates, register = _plan(vs)
        if vertical not in templates:
            report.problems.append(
                f"{vertical} has no scoring workbook: set scoring_workbook in its settings "
                "file, or add it to the Verticals sheet of the assignments workbook."
            )
            return report
        services = default_services()
        services.settings = vs
        template = templates[vertical]
    run = run_ai_scoring(
        services,
        template,
        vertical,
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
    report.done.append(
        f"Scored {', '.join(run.cities)}: the AI scored {run.scored} row(s) from checked "
        f"evidence and left {left} for a person."
    )
    report.breakdown = [
        (REASONS[k], n) for k, n in sorted(run.reasons.items(), key=lambda x: -x[1])
    ]
    label = f"{vertical} AI run" + (" (practice)" if practice else "")
    scores = results(services.settings, templates, eval_label=label)
    report.add_file(
        run.path,
        "The one workbook to use. Its first sheet, Scores (start here), has every question: "
        "the AI's score and why, the Step 2 answer and citation behind it, and yellow columns "
        "for your own score and comments. Filter Status for the rows left for a person.",
    )
    report.add_file(
        scores,
        "Every city and vertical side by side (also on the Scores page).",
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
        "enter your own score where you disagree. 'Agrees with AI?' turns red where you differ."
    )
    report.next_steps.append("Compare cities and verticals on the Scores page.")
    if run.failed:
        report.problems.append(
            f"{run.failed} row(s) couldn't be scored because the AI call failed. Run Step 3 "
            "again to retry them."
        )
    return report
