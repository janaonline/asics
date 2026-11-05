"""Merge the stored submissions into the merged people's workbook, one per section.

The merged workbook is derived: every merge starts again from the team's template and writes the
submissions' values into it with the same writer the AI's files use, then LibreOffice calculates it.
Run it as often as you like; the submissions are never touched.

Rules:
  * A blank never overwrites a value. A scorer's value for a cell is the latest non-blank value
    across their submissions, so a re-submission replaces only what it fills in, and only for the
    rows it contains.
  * Two scorers who give different scores or inputs for the same question and row are both listed
    under "Needs a look". Nothing is resolved automatically: that row is left blank (not scored).
  * A question whose Score is calculated from inputs is written only when every input its Score
    needs has a value; otherwise the inputs stay out, so a half-filled row never shows as a 0.
  * A city or parastatal the register doesn't know is not merged (it stays in its submission).
  * Evidence and comments come from the first scorer who gave them.
"""

import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from asics_agent import bank_version as bv
from asics_agent.categories import load_bank
from asics_agent.cities import load_register
from asics_agent.scoring.name_resolution import (
    Decision,
    PlaceMap,
    config_types,
    remembered_decisions,
)
from asics_agent.scoring.submissions import (
    Submission,
    list_submissions,
    merged_path,
    scorer_key,
    section_templates,
    sha256_of,
    template_specs,
)
from asics_agent.scoring.template_fill import AITemplate, check_value, template_hash
from asics_agent.scoring.template_import import EVIDENCE_FIELDS, read_filled_template

INFO_SUFFIX = ".merge_info.json"
CONFIG_NOTE = "Added from the city register by the merge of people's submissions."


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def info_path(path: Path) -> Path:
    return path.with_name(path.stem + INFO_SUFFIX)


def read_merge_info(path: Path) -> dict:
    try:
        return json.loads(info_path(path).read_text())
    except (OSError, ValueError):
        return {}


def merged_files(settings) -> list[Path]:
    """The merged people's workbooks that exist for the category's sections."""
    return [
        p for s in sorted(section_templates(settings)) if (p := merged_path(settings, s)).exists()
    ]


def _numbers_equal(a, b) -> bool:
    try:
        return abs(float(_text(a).rstrip("%")) - float(_text(b).rstrip("%"))) < 1e-9
    except ValueError:
        return False


def same_value(a, b) -> bool:
    return _text(a).casefold() == _text(b).casefold() or _numbers_equal(a, b)


@dataclass
class Conflict:
    section: str
    code: str
    city: str
    unit: str
    field: str
    entries: list[dict]  # {scorer, value, submission_id, source, comments}

    def line(self) -> str:
        who = "; ".join(f'{e["scorer"]} entered "{e["value"]}"' for e in self.entries)
        return (
            f"{self.code}, {self.city} / {self.unit or 'ULG'}, {self.field}: {who}. Left blank "
            "until the scorers agree on one."
        )

    def as_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class MergeReport:
    files: list[Path] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)
    incomplete: list[str] = field(default_factory=list)
    not_merged: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # rows a person chose to skip
    unregistered: list[dict] = field(default_factory=list)  # merged, but the register lacks them
    problems: list[str] = field(default_factory=list)
    done: list[str] = field(default_factory=list)
    rows_merged: int = 0
    calculated: bool = True

    def needs_a_look(self) -> list[str]:
        return [
            *(c.line() for c in self.conflicts),
            *self.incomplete,
            *self.not_merged,
            *self.problems,
        ]


@dataclass
class _Entry:
    """One scorer's effective values for one question and row."""

    scorer: str
    order: int
    values: dict[str, tuple[object, str]] = field(
        default_factory=dict
    )  # field -> (value, submission)
    source: str = ""
    comments: str = ""


def _field_label(key: str) -> str:
    if key == "score":
        return "Score"
    return key.split(":", 1)[1] if ":" in key else key


def merge_category(settings) -> MergeReport:
    """Build the merged people's workbook of every section that has submissions."""
    report = MergeReport()
    templates = section_templates(settings)
    if not templates:
        report.problems.append(f"{settings.category_title} has no scoring templates.")
        return report
    subs = {s: list_submissions(settings, s) for s in templates}
    if not any(subs.values()):
        report.problems.append("No people's files have been uploaded yet.")
        return report
    register, _ = load_register(settings.city_register)
    bank, _ = load_bank(settings)
    current = bv.bank_version(settings.question_bank, bank) if bank else None
    remembered = remembered_decisions(settings)
    lookup = PlaceMap(settings, register, remembered)
    types: dict[tuple[str, str], str] = {}
    unreg: dict[tuple[str, str], dict] = {}
    skipped: dict[str, int] = {}

    # (section, code, city, unit) -> {scorer key: _Entry}
    rows: dict[tuple[str, str, str, str], dict[str, _Entry]] = {}
    used: dict[str, list[Submission]] = {}
    for section, items in subs.items():
        specs = template_specs(templates[section])
        order: dict[str, int] = {}
        for sub in items:  # oldest first, so a later submission of the same scorer replaces
            if sub.path is None or not sub.path.exists():
                report.problems.append(f"{sub.submission_id}: the stored file is missing.")
                continue
            if sha256_of(sub.path.read_bytes()) != sub.file_sha256:
                report.problems.append(
                    f"{sub.submission_id}: the stored file no longer matches its record, so it "
                    "was not used."
                )
                continue
            used.setdefault(section, []).append(sub)
            read = read_filled_template(sub.path, sub.scorer)
            own = {}
            for raw in sub.decisions:
                if (d := Decision.from_dict(raw)) is not None:
                    own[d.key()] = d
            lookup.decisions = {**remembered, **own}  # this file's own choice wins
            lookup.file_types = config_types(read)
            key = scorer_key(sub.scorer)
            order.setdefault(key, len(order))
            for row in read.rows:
                spec = specs.get(row.code)
                values = _row_values(row, spec) if spec else None
                if values is None:
                    note = f"{row.code} is not a question of the {section} template."
                    if note not in report.not_merged:
                        report.not_merged.append(note)
                    continue
                if not values:
                    continue
                place = lookup.place(row.city, row.parastatal)
                if place.skipped:
                    skipped[place.why] = skipped.get(place.why, 0) + 1
                    continue
                entry = rows.setdefault((section, row.code, place.city, place.unit), {}).setdefault(
                    key, _Entry(sub.scorer, order[key])
                )
                for name, value in values.items():
                    entry.values[name] = (value, sub.submission_id)
                entry.source = row.source_link or entry.source
                entry.comments = row.comments or entry.comments
                types[(place.city, place.unit)] = place.type_label
                if not place.registered:
                    info = unreg.setdefault(
                        (place.city, place.unit),
                        {
                            "city": place.city,
                            "parastatal": place.unit,
                            "type": place.type_label,
                            "city_in_register": place.city_registered,
                            "state": place.state,
                            "ulg": place.ulg,
                            "rows": 0,
                            "submissions": [],
                        },
                    )
                    info["rows"] += 1
                    if sub.submission_id not in info["submissions"]:
                        info["submissions"].append(sub.submission_id)

    report.skipped = [
        f"{why}: {n} row(s) not merged (skipped by your choice)." for why, n in skipped.items()
    ]
    report.unregistered = list(unreg.values())
    for u in report.unregistered:
        if not u["type"] and u["parastatal"]:
            report.problems.append(
                f"{u['parastatal']} ({u['city']}) has no known type, so no question of the "
                "template can apply to it yet. Add it as new with its type."
            )
    units = sorted(types.items())
    out_dir = merged_path(settings, next(iter(templates))).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    for section, template in templates.items():
        if section not in used:
            continue
        _build_section(
            settings,
            report,
            section,
            template,
            used[section],
            rows,
            units,
            current.version if current else "",
        )
    n = len(report.files)
    report.done.append(
        f"Merged {sum(len(v) for v in used.values())} submission(s) into {n} workbook(s): "
        f"{report.rows_merged} row(s) written, {len(report.conflicts)} conflict(s), "
        f"{len(report.incomplete)} incomplete."
    )
    return report


def _row_values(row, spec) -> dict[str, object] | None:
    """The cells of a row that count: {field: value}, blanks left out. None = nothing to merge."""
    out: dict[str, object] = {}
    if row.score is not None and spec.score_column and not spec.score_is_formula:
        out["score"] = row.score
    by_header = {c.header: col for col, c in spec.columns.items() if c.kind == "input"}
    for header, value in row.inputs.items():
        if header in by_header and value not in (None, ""):
            out[f"in:{header}"] = value
    for name in EVIDENCE_FIELDS:
        value = getattr(row, name)
        if value and spec.column_for(name):
            out[f"tx:{name}"] = value
    return out


def _build_section(settings, report, section, template, subs, rows, units, bank_version) -> None:
    specs = template_specs(template)
    out = merged_path(settings, section)
    work = Path(tempfile.mkdtemp(dir=out.parent, prefix=".build-"))
    try:
        ai = AITemplate(work / out.name, template)
        ai.config_note = CONFIG_NOTE
        for (city, unit), label in units if settings.unit != "ulg" else []:
            # the same order in every section's file
            for problem in ai.ensure_unit(city, unit, label):
                if problem not in report.problems:
                    report.problems.append(problem)
        provenance: dict[str, dict] = {}
        written = 0
        for (sec, code, city, unit), by_scorer in sorted(rows.items()):
            if sec != section:
                continue
            spec = specs[code]
            entries = sorted(by_scorer.values(), key=lambda e: e.order)
            conflicts = _conflicts(section, code, city, unit, entries)
            if conflicts:
                report.conflicts += conflicts
                continue
            chosen: dict[str, object] = {}
            for entry in entries:
                for name, (value, _) in entry.values.items():
                    chosen.setdefault(name, value)
            cells = _cells(spec, chosen, report, f"{code}, {city} / {unit or 'ULG'}")
            if spec.score_is_formula and spec.required_inputs:
                missing = [
                    spec.columns[c].header
                    for c in spec.required_inputs
                    if c not in cells or cells[c] in (None, "")
                ]
                if missing:
                    cells = {c: v for c, v in cells.items() if spec.columns[c].kind != "input"}
                    report.incomplete.append(
                        f"{code}, {city} / {unit or 'ULG'}: the score is calculated from inputs "
                        f"and these are missing: {', '.join(missing)}. The inputs were left out "
                        "of the merged workbook so it does not show a score of 0."
                    )
            if not cells:
                continue
            row = ai.ensure_row(code, city, unit)
            if row is None:
                continue
            result = ai.write(code, row, cells)
            report.problems += [f"{city} / {unit}: {r}" for r in result.rejected]
            written += 1
            provenance[f"{code}|{city.casefold()}|{unit.casefold()}"] = {
                "scorers": [e.scorer for e in entries],
                "submissions": sorted({s for e in entries for _, s in e.values.values()}),
            }
        saved = ai.save(settings.scoring_dir / ".cache", None)
        report.problems += saved.problems
        report.calculated = report.calculated and saved.calculated
        os.replace(saved.path, out)
        report.files.append(out)
        report.rows_merged += written
        info = {
            "source": "human",
            "section": section,
            "category": settings.category,
            "merged_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "template_name": template.name,
            "template_sha256": template_hash(template),
            "bank_version": bank_version,
            "calculated": saved.calculated,
            "submissions": [
                {"submission_id": s.submission_id, "scorer": s.scorer, "file_sha256": s.file_sha256}
                for s in subs
            ],
            "rows_merged": written,
            "conflicts": [c.as_dict() for c in report.conflicts if c.section == section],
            "incomplete": [x for x in report.incomplete if x.split(",")[0].startswith(section)],
            "unregistered": report.unregistered,
            "skipped": report.skipped,
            "rows": provenance,
        }
        info_path(out).write_text(json.dumps(info, indent=2, default=str))
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _conflicts(section, code, city, unit, entries) -> list[Conflict]:
    """Fields (the score and the inputs) on which two scorers gave different values."""
    keys = sorted({k for e in entries for k in e.values if k == "score" or k.startswith("in:")})
    found = []
    for key in keys:
        given = [(e, e.values[key]) for e in entries if key in e.values]
        if all(same_value(given[0][1][0], v[0]) for _, v in given[1:]):
            continue
        found.append(
            Conflict(
                section,
                code,
                city,
                unit,
                _field_label(key),
                [
                    {
                        "scorer": e.scorer,
                        "value": v[0],
                        "submission_id": v[1],
                        "source": e.source,
                        "comments": e.comments[:300],
                    }
                    for e, v in given
                ],
            )
        )
    return found


def _cells(spec, chosen: dict[str, object], report, where: str) -> dict[int, object]:
    """{column: value} for the writer, each value checked against the column's own rules."""
    by_header = {c.header: col for col, c in spec.columns.items() if c.kind == "input"}
    cells: dict[int, object] = {}
    for name, value in chosen.items():
        if name == "score":
            column = spec.score_column
        elif name.startswith("in:"):
            column = by_header.get(name[3:])
        else:
            column = spec.column_for(name[3:])
        if column is None:
            continue
        ok, why = check_value(spec, column, value)
        if why:
            report.problems.append(f'{where}, "{_field_label(name)}": {why}. Not merged.')
        elif ok is not None:
            cells[column] = ok
    return cells


# -- what the Scores page needs from the merge ----------------------------------------------------
def apply_provenance(reads, settings) -> None:
    """Name the scorer(s) on the rows read from a merged workbook (the file itself holds none)."""
    for read in reads:
        info = read_merge_info(Path(read.path))
        rows = info.get("rows") or {}
        for row in read.rows:
            found = rows.get(f"{row.code}|{row.city.casefold()}|{row.parastatal.casefold()}")
            if found:
                row.scorer = ", ".join(found["scorers"])


def needs_a_look(settings) -> list[str]:
    """What the last merge of each section left for people to sort out."""
    lines = []
    for path in merged_files(settings):
        info = read_merge_info(path)
        for c in info.get("conflicts", []):
            lines.append(Conflict(**c).line())
        lines += info.get("incomplete", [])
    return lines


def conflicts(settings) -> list[Conflict]:
    return [
        Conflict(**c)
        for path in merged_files(settings)
        for c in read_merge_info(path).get("conflicts", [])
    ]


def newer_than_merge(settings) -> list[Submission]:
    """Submissions stored after the last merge of their section (or never merged)."""
    out = []
    for section in sorted(section_templates(settings)):
        info = read_merge_info(merged_path(settings, section))
        stamp = info.get("merged_at", "")
        out += [s for s in list_submissions(settings, section) if s.uploaded_at > stamp]
    return out
