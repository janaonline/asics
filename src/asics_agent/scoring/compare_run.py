"""Everything needed to compare one city: finds the files, reads both sides, runs the comparison.

Used by scripts/compare_human_ai.py and by the Scores page, so both give the same answer.
The human side is filled templates: the merged people's workbooks built from the uploaded
submissions (scoring/2027/merged/, see human_merge), or files you name; the AI side
is the AI's copies of the templates (scoring/2027/ai/), or for a category without templates the
older review sheet. Step 2's answers workbook adds the AI's class, confidence and citation.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from asics_agent import bank_version as bv
from asics_agent.bank_status import build_context
from asics_agent.categories import load_bank
from asics_agent.cities import load_register
from asics_agent.parastatal_types import ULG_TYPE, canonical_type, known_type
from asics_agent.scoring import compare as cmp
from asics_agent.scoring import consolidated as cons
from asics_agent.scoring.ai import ai_file
from asics_agent.scoring.name_resolution import NOT_IN_REGISTER, norm_name
from asics_agent.scoring.phase2 import phase2_status
from asics_agent.scoring.template_fill import ai_path, read_info, template_hash
from asics_agent.scoring.template_import import TemplateRead, read_filled_template
from asics_agent.scoring.template_scoring import template_sections
from asics_agent.sources_workbook import read_sources_workbook, sources_path, workspace_for


def human_dir(settings) -> Path:
    return settings.scoring_dir / "human" / settings.category


def human_files(settings) -> list[Path]:
    """The people's files of this category. A category scored in the team's templates has one
    merged, calculated file per section (built from the uploaded submissions, see human_merge);
    any other category keeps the filled files in its human folder."""
    if settings.scoring_templates:
        from asics_agent.scoring.human_merge import merged_files

        return merged_files(settings)
    folder = human_dir(settings)
    return sorted(p for p in folder.glob("*.xlsx") if not p.name.startswith(("~", ".")))


def ai_files(settings) -> list[Path]:
    """The AI's copies of the category's templates that exist."""
    found = []
    for section in template_sections(settings.scoring_templates):
        path = ai_path(settings.scoring_dir, settings.scoring_code, section)
        if path.exists():
            found.append(path)
    return found


def compare_dir(settings) -> Path:
    return settings.scoring_dir / "compare"


def read_human(paths: list[Path], scorer: str = "") -> list[TemplateRead]:
    return [read_filled_template(p, scorer) for p in paths]


def _recorded(workbook: Path | None, sidecar: bool):
    """The bank version a Step 2 answers file or a scoring workbook says it was made with."""
    if workbook is None or not workbook.exists():
        return None
    if sidecar:
        return bv.read_sidecar(workbook)
    try:
        return json.loads((workbook.parent / "run_summary.json").read_text()).get("bank_version")
    except (OSError, ValueError):
        pass
    found = bv.embedded_version(workbook)
    return found.as_dict() if found else None


def version_notes(settings, answers: Path | None, ais: list[Path], humans: list[Path], current):
    """Plain-language notes when the human files, the AI files, Step 2's answers and the question
    bank in use don't all match."""
    notes = []
    if answers is not None:
        note = bv.version_note(_recorded(answers, False), current)
        if note:
            notes.append(f"Step 2 answers ({answers.name}): {note}")
    templates = {s: p for s, p in template_sections(settings.scoring_templates).items()}
    for path in ais:
        info = read_info(path)
        note = bv.version_note(info.get("bank_version"), current)
        if note:
            notes.append(f"The AI's file ({path.name}): {note}")
        template = templates.get(info.get("section", ""))
        if (
            template
            and info.get("template_sha256")
            and info["template_sha256"] != template_hash(template)
        ):
            notes.append(
                f"The AI's file ({path.name}) was made from an earlier version of the template "
                f"{template.name}. Run Step 3 again to rebuild it."
            )
        if info and not info.get("calculated", True):
            notes.append(
                f"The AI's file ({path.name}) holds inputs but not calculated scores: the score "
                "calculates when it is opened in Excel."
            )
    if humans and settings.scoring_templates:
        from asics_agent.scoring.human_merge import newer_than_merge, read_merge_info

        for path in humans:
            note = bv.version_note(read_merge_info(path).get("bank_version") or None, current)
            if note:
                notes.append(f"People's file ({path.name}): {note}")
        waiting = newer_than_merge(settings)
        if waiting:
            notes.append(
                f"{len(waiting)} uploaded file(s) are not merged yet (Step 3 > People's "
                "scoring > Merge and calculate), so they are not in the numbers below."
            )
    elif humans:
        notes.append(
            "People's files don't record which question bank they were made with. Questions "
            "whose text in the file differs from the bank in use are marked 'question changed'."
        )
    return notes


def city_units(settings, city) -> tuple[dict[str, cmp.Unit], list[str]]:
    """{unit id: Unit} the city has: the register's parastatals and those in its Sources workbook."""
    workspace = workspace_for(settings.outputs_dir, city.name)
    units = {p.id: cmp.Unit(p.id, p.name, p.type) for p in city.parastatals}
    sources = sources_path(workspace, city.name)
    notes: list[str] = []
    if sources.exists():
        try:
            for p in read_sources_workbook(sources, workspace / "evidence")[0]:
                units.setdefault(p.id, cmp.Unit(p.id, p.name, p.type))
        except Exception as exc:
            notes.append(f"Could not read {sources.name}: {exc}")
    return units, notes


def build_inputs(
    settings,
    city,
    *,
    ai_reads: list[TemplateRead] | None = None,
    answers: Path | None = None,
    ai_workbook: Path | None = None,
    ai_runs: Path | None = None,
    human_paths: list[Path] | None = None,
) -> cmp.CityInputs:
    """The inputs of one city's comparison. `city` is a CityConfig of the register."""
    ulg = settings.unit == "ulg"
    bank, _ = load_bank(settings)
    current = bv.bank_version(settings.question_bank, bank) if bank else None
    ctx = build_context(bank, settings.question_bank)
    units, notes = city_units(settings, city)
    registered = find_city(settings, city.name) is not None
    unregistered = set()
    for u in unregistered_places(settings):
        if norm_name(u["city"]) == norm_name(city.name) and u["parastatal"]:
            code = u["parastatal"]
            units.setdefault(
                code,
                cmp.Unit(code, code, canonical_type(u["type"]) if known_type(u["type"]) else ""),
            )
            unregistered.add(code)
    if not registered:
        notes.insert(0, f"{city.name}: {NOT_IN_REGISTER}.")
    if ulg:
        units[cmp.ULG_UNIT] = cmp.Unit(cmp.ULG_UNIT, city.ulg or city.name, ULG_TYPE)
    ids = {}
    for u in units.values():
        ids[u.id.casefold()] = u.id
        if u.name:
            ids[u.name.casefold()] = u.id
    status = phase2_status(settings, city.name)
    answers = answers or status.answers
    if answers is None:
        notes.append(
            f"{city.name} has no Step 2 answers workbook: nothing to compare on that side."
        )
    elif not status.ready and status.answers == answers:
        notes.append(status.reason)
    templates_scored = bool(settings.scoring_templates)
    ais = ai_files(settings) if templates_scored else []
    if templates_scored:
        reads = ai_reads if ai_reads is not None else read_human(ais, "AI")
        step3 = cmp.step3_from_templates(reads)
    else:
        path = ai_workbook or ai_file(settings.scoring_dir, settings.scoring_code)
        step3 = cmp.read_step3(path, ai_runs or path.parent / "runs", settings.scoring_code)
        ais = [path] if path.exists() else []
    notes += version_notes(settings, answers, ais, human_paths or [], current)
    return cmp.CityInputs(
        city=city.name,
        aliases=city.aliases,
        units=units,
        bank=bank,
        retired=ctx.retired,
        raw_to_code=ctx.raw_to_code,
        old_raw_to_code=ctx.old_raw_to_code,
        step2=cmp.read_step2(answers, ids) if answers else {},
        step3=step3,
        unregistered=unregistered,
        city_in_register=registered,
        ulg=ulg,
        bank_version=current.version if current else "",
        notes=notes,
    )


def compare_city_files(
    settings, city, humans: list[TemplateRead], human_paths: list[Path] | None = None, **kw
) -> cmp.Comparison:
    """Compare a city's human files (already read) with the AI's, as one Comparison."""
    info = build_inputs(settings, city, human_paths=human_paths, **kw)
    return cmp.compare_city(info, humans)


# -- what the Scores page shows -----------------------------------------------------------------
@dataclass
class ViewData:
    """Everything the Scores page shows for one city of one category."""

    city: str
    human_paths: list[Path] = field(default_factory=list)
    ai_paths: list[Path] = field(default_factory=list)
    comparison: cmp.Comparison | None = None
    tables: dict[str, dict[str, cons.Table]] = field(
        default_factory=dict
    )  # source -> view -> table
    notes: list[str] = field(default_factory=list)
    reports: list[str] = field(default_factory=list)  # what was read and ignored, per file
    not_in_register: bool = False  # a city only the people's files know


def unregistered_places(settings) -> list[dict]:
    """Cities and parastatals the people's merged files hold that the register does not (from the
    merge records): {city, parastatal, type, city_in_register, state, ulg, rows, submissions}."""
    from asics_agent.scoring.human_merge import merged_files, read_merge_info
    from asics_agent.scoring.name_resolution import norm_name

    found: dict[tuple[str, str], dict] = {}
    for path in merged_files(settings):
        for u in read_merge_info(path).get("unregistered", []):
            found[(norm_name(u["city"]), norm_name(u["parastatal"]))] = u
    return list(found.values())


def find_city_or_unregistered(settings, name: str):
    """The register's city, else a stand-in for a city only the people's files know."""
    from asics_agent.scoring.name_resolution import norm_name, pseudo_city

    city = find_city(settings, name)
    if city is not None:
        return city
    mine = [u for u in unregistered_places(settings) if norm_name(u["city"]) == norm_name(name)]
    if not mine:
        return None
    return pseudo_city(
        mine[0]["city"], [u for u in mine if u["parastatal"]], mine[0]["state"], mine[0]["ulg"]
    )


def find_city(settings, name: str):
    """The register's CityConfig for a city name (or one of its other names)."""
    register, _ = load_register(settings.city_register)
    wanted = name.casefold()
    return next(
        (c for c in register.values() if wanted in {n.casefold() for n in [c.name, *c.aliases]}),
        None,
    )


def load_view(settings, city_name: str, human_paths: list[Path] | None = None) -> ViewData:
    """Read the people's and the AI's files for a city and build the consolidated tables and the
    comparison. Read-only: no file is changed."""
    out = ViewData(city_name)
    out.not_in_register = find_city(settings, city_name) is None
    out.human_paths = human_paths if human_paths is not None else human_files(settings)
    out.ai_paths = ai_files(settings)
    cache = settings.scoring_dir / ".cache"
    city = find_city_or_unregistered(settings, city_name)
    humans = read_human(out.human_paths)
    if settings.scoring_templates:  # the merged files name no scorer; their records do
        from asics_agent.scoring.human_merge import apply_provenance

        apply_provenance(humans, settings)
    ais = read_human(out.ai_paths, "AI")
    for read in [*humans, *ais]:
        out.reports += read.report.lines()
    if city is None:
        out.notes.append(f'"{city_name}" is not in the city register.')
        return out
    people = cons.read_sections(out.human_paths, cache)
    ai = cons.read_sections(out.ai_paths, cache)
    out.tables = cons.consolidated(people, ai)
    out.notes += cons.note_lines(people, ai)
    out.comparison = compare_city_files(
        settings, city, humans, human_paths=out.human_paths, ai_reads=ais
    )
    out.notes += out.comparison.notes
    return out


def comparison_workbook(settings, view: ViewData, min_rows: int = cmp.MIN_ROWS) -> Path | None:
    """Write the city's compare workbook (what scripts/compare_human_ai.py writes) and return it."""
    if view.comparison is None:
        return None
    path = compare_dir(settings) / f"{view.city.replace(' ', '_')}_human_vs_ai.xlsx"
    return cmp.write_comparison(view.comparison, path, min_rows, extra=view.tables)
