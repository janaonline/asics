"""The consolidated view of a category's scoring templates: one table per question of the team's
Parastatal_Consolidated_Scoring.xlsx, computed from the template files themselves.

Each template (one per section: UPD, SC, DPG) calculates its own "Raw Summary" (per parastatal:
the sum of scored main questions, their attainable max, the score out of 10) and "City Summary" (per
city). This module reads those sheets by their labels, never by position, from any such file
(a people's file, or the AI's copy), and puts the sections side by side:

  city_systems      per city: each section out of 10, the total (the average, only when every
                    section has a score) and "k of n"
  parastatal_scores per parastatal: each section's sum and max, and the overall score out of 10
                    (sum of the sums / sum of the maxes x 10), "k of n"
  question_matrix   per question: its score for every parastatal (main questions roll up from
                    their sub-questions, as the template computes)

`difference` puts People and AI side by side as AI - People. Nothing is built from the category's
name: the number and names of the sections are whatever template files are given.
"""

import shutil
import warnings
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import load_workbook

from asics_agent.scoring.recalc import RecalcUnavailable, recalculate
from asics_agent.scoring.template_import import normalise_code, read_structures, section_of

LABELS = {
    "city": "city",
    "parastatal": "parastatal",
    "type": "parastatal type",
    "key": "key",
    "sum": "sum of scored mq scores",
    "max": "attainable max of those mqs",
    "score": "score out of 10",
    "progress": "scored questions answered",
    "active": "active parastatals in city",
    "mqs": "mqs scored",
}


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def _num(value):
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


@dataclass
class Question:
    code: str
    text: str
    tag: str
    max_score: float | None
    level: str


@dataclass
class Slot:  # a parastatal (or the ULG) of one file
    city: str
    unit: str
    type: str
    key: str
    total: float | None = None
    maximum: float | None = None
    score10: float | None = None
    progress: str = ""
    scores: dict[str, object] = field(default_factory=dict)  # question code -> value


@dataclass
class CityColumn:
    city: str
    active: float | None = None
    total: float | None = None
    maximum: float | None = None
    score10: float | None = None
    progress: str = ""
    scores: dict[str, object] = field(default_factory=dict)


@dataclass
class SectionSummary:
    section: str  # UPD
    path: Path
    questions: list[Question] = field(default_factory=list)
    slots: list[Slot] = field(default_factory=list)
    cities: list[CityColumn] = field(default_factory=list)
    calculated: bool = True  # the file holds calculated values
    notes: list[str] = field(default_factory=list)


@dataclass
class Table:
    headers: list[str]
    rows: list[list]

    def __bool__(self) -> bool:
        return bool(self.rows)


def has_values(path: Path) -> bool:
    """Does the file hold calculated values (a file saved by a tool that doesn't calculate has
    formulas only)? Checked on the Raw Summary's first parastatal."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = load_workbook(path, data_only=True, read_only=True)
    ws = next((wb[n] for n in wb.sheetnames if n.strip().lower() == "raw summary"), None)
    if ws is None:
        return True  # nothing to read anyway
    for row in ws.iter_rows(min_row=1, max_row=12, values_only=True):
        cells = [_text(c).lower() for c in row]
        for i, cell in enumerate(cells):
            if cell == LABELS["city"] and i + 1 < len(row):
                return any(_text(c) for c in row[i + 1 :])
    return False


def readable_copy(path: Path, cache_dir: Path) -> tuple[Path, str]:
    """(the file to read, a note): `path` itself when it holds calculated values, else a
    temporary recalculated copy (never the file itself)."""
    if has_values(path):
        return path, ""
    copy = cache_dir / f"calculated_{path.name}"
    if not copy.exists() or copy.stat().st_mtime < path.stat().st_mtime:
        cache_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, copy)
        try:
            recalculate(copy, cache_dir)
        except (RecalcUnavailable, RuntimeError, OSError) as exc:
            copy.unlink(missing_ok=True)
            return (
                path,
                f"{path.name} has no calculated scores and could not be calculated here ({exc})",
            )
    return copy, f"{path.name} had no calculated scores: they were calculated in a temporary copy"


def _label_rows(ws, labels: dict[str, str]) -> tuple[int, dict[str, int]]:
    """(the column holding the labels, {name: row}) for the sheet's label column (the one with
    "City" and the sum/max/score labels), found by text."""
    best: tuple[int, dict[str, int]] = (0, {})
    for col in range(1, 10):
        found = {}
        for r in range(1, 20):
            text = _text(ws.cell(r, col).value).lower()
            for name, label in labels.items():
                if name not in found and text.startswith(label):
                    found[name] = r
        if len(found) > len(best[1]):
            best = (col, found)
    return best


def _header_row(ws, first_data_row: int) -> int | None:
    """The row above the questions: the one whose first cell is "Sl No" (or has "Max Score")."""
    for r in range(first_data_row, first_data_row + 12):
        cells = [_text(ws.cell(r, c).value).lower() for c in range(1, 9)]
        if "sl no" in cells or ("max score" in cells and "tag" in cells):
            return r
    return None


def _read_questions(ws, header: int, last_col: int) -> list[tuple[int, Question]]:
    cells = {_text(ws.cell(header, c).value).lower(): c for c in range(1, last_col + 1)}
    code_col = next(
        (c for h, c in cells.items() if "question no" in h or h in ("question code", "code")), 2
    )
    text_col = cells.get("question", 3)
    tag_col, max_col = cells.get("tag", 4), cells.get("max score", 5)
    level_col = cells.get("assessment level", 6)
    out = []
    for r in range(header + 1, ws.max_row + 1):
        code = normalise_code(ws.cell(r, code_col).value)
        if code is None:
            if not _text(ws.cell(r, code_col).value):
                break
            continue
        out.append(
            (
                r,
                Question(
                    code,
                    _text(ws.cell(r, text_col).value),
                    _text(ws.cell(r, tag_col).value),
                    _num(ws.cell(r, max_col).value),
                    _text(ws.cell(r, level_col).value),
                ),
            )
        )
    return out


def read_section(path: Path, cache_dir: Path) -> SectionSummary | None:
    """The Raw Summary and City Summary of one calculated template file, or None if the file is
    not a scoring template."""
    readable, note = readable_copy(Path(path), cache_dir)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = load_workbook(readable, data_only=True)
        specs = read_structures(load_workbook(path, read_only=False))
    section = section_of(specs)
    summary = SectionSummary(section, Path(path), calculated=has_values(readable))
    if note:
        summary.notes.append(note)
    raw = next((wb[n] for n in wb.sheetnames if n.strip().lower() == "raw summary"), None)
    city = next((wb[n] for n in wb.sheetnames if n.strip().lower() == "city summary"), None)
    if raw is None and city is None:
        return None
    if raw is not None:
        label_col, rows = _label_rows(raw, LABELS)
        if "city" in rows and label_col:
            header = _header_row(raw, max(rows.values()) + 1)
            questions = _read_questions(raw, header, label_col) if header else []
            summary.questions = [q for _, q in questions]
            for col in range(label_col + 1, raw.max_column + 1):
                city_name = _text(raw.cell(rows["city"], col).value)
                if not city_name:
                    continue

                def cell(name, col=col):
                    return raw.cell(rows[name], col).value if name in rows else None

                slot = Slot(
                    city_name,
                    _text(cell("parastatal")),
                    _text(cell("type")),
                    _text(cell("key")),
                    _num(cell("sum")),
                    _num(cell("max")),
                    _num(cell("score")),
                    _text(cell("progress")),
                )
                for r, q in questions:
                    slot.scores[q.code] = raw.cell(r, col).value
                summary.slots.append(slot)
    if city is not None:
        label_col, rows = _label_rows(city, LABELS)
        if "city" in rows and label_col:
            header = _header_row(city, max(rows.values()) + 1)
            questions = _read_questions(city, header, label_col) if header else []
            if not summary.questions:
                summary.questions = [q for _, q in questions]
            for col in range(label_col + 1, city.max_column + 1):
                name = _text(city.cell(rows["city"], col).value)
                if not name:
                    continue

                def ccell(key, col=col):
                    return city.cell(rows[key], col).value if key in rows else None

                column = CityColumn(
                    name,
                    _num(ccell("active")),
                    _num(ccell("sum")),
                    _num(ccell("max")),
                    _num(ccell("score")),
                    _text(ccell("mqs")),
                )
                for r, q in questions:
                    column.scores[q.code] = city.cell(r, col).value
                summary.cities.append(column)
    return summary


def read_sections(paths, cache_dir: Path) -> list[SectionSummary]:
    """Every readable file, in the order given (one section may have several files: their
    parastatals are put together; a parastatal in two files is taken from the first)."""
    found: dict[str, SectionSummary] = {}
    for path in paths:
        try:
            one = read_section(Path(path), cache_dir)
        except Exception as exc:  # one unreadable file never stops the rest
            one = SectionSummary(
                "",
                Path(path),
                calculated=False,
                notes=[f"{Path(path).name} could not be read ({exc})."],
            )
        if one is None or not one.section:
            continue
        if one.section not in found:
            found[one.section] = one
            continue
        base = found[one.section]
        have = {s.key for s in base.slots}
        for slot in one.slots:
            if slot.key in have:
                base.notes.append(
                    f"{slot.key} is in {base.path.name} and {one.path.name}; the first is used."
                )
            else:
                base.slots.append(slot)
        have_cities = {c.city.casefold() for c in base.cities}
        base.cities += [c for c in one.cities if c.city.casefold() not in have_cities]
        base.notes += one.notes
        base.calculated = base.calculated and one.calculated
    return list(found.values())


# -- the views ----------------------------------------------------------------------------------
def _shown(value):
    """A cell as the table shows it: numbers rounded, text kept ("NA", "Partial"), blank as ''."""
    n = _num(value)
    if n is not None:
        return round(n, 2)
    return _text(value)


def city_systems(sections: list[SectionSummary]) -> Table:
    """Per city: each section out of 10, the total (only when every section has a score) and
    "k of n"."""
    names: dict[str, str] = {}
    for s in sections:
        for c in s.cities:
            names.setdefault(c.city.casefold(), c.city)
        for slot in s.slots:
            names.setdefault(slot.city.casefold(), slot.city)
    headers = ["City", *[f"{s.section} (out of 10)" for s in sections], "Total", "Sections scored"]
    rows = []
    for key, city in names.items():
        scores = []
        for s in sections:
            col = next((c for c in s.cities if c.city.casefold() == key), None)
            scores.append(_num(col.score10) if col else None)
        have = [x for x in scores if x is not None]
        total = round(sum(have) / len(have), 2) if len(have) == len(sections) and have else ""
        rows.append(
            [
                city,
                *[round(x, 2) if x is not None else "" for x in scores],
                total,
                f"{len(have)} of {len(sections)}",
            ]
        )
    return Table(headers, rows)


def parastatal_scores(sections: list[SectionSummary]) -> Table:
    """Per parastatal: each section's sum and max, and the overall score out of 10."""
    order: dict[str, tuple[str, str, str]] = {}
    for s in sections:
        for slot in s.slots:
            order.setdefault(
                slot.key or f"{slot.city}|{slot.unit}", (slot.city, slot.unit, slot.type)
            )
    headers = ["City", "Parastatal", "Type"]
    for s in sections:
        headers += [f"{s.section} scored", f"{s.section} max"]
    headers += ["Overall (out of 10)", "Sections scored"]
    rows = []
    for key, (city, unit, kind) in order.items():
        row, total, maximum, got = [city, unit, kind], 0.0, 0.0, 0
        for s in sections:
            slot = next((x for x in s.slots if (x.key or f"{x.city}|{x.unit}") == key), None)
            t, m = (slot.total, slot.maximum) if slot else (None, None)
            row += [round(t, 2) if t is not None else "", round(m, 2) if m is not None else ""]
            if t is not None and m:
                total, maximum, got = total + t, maximum + m, got + 1
        row += [round(total / maximum * 10, 2) if maximum else "", f"{got} of {len(sections)}"]
        rows.append(row)
    return Table(headers, rows)


def question_matrix(sections: list[SectionSummary]) -> Table:
    """Per question: the score for every parastatal (main questions are their sub-questions' sum)."""
    slots = []
    for s in sections:
        for slot in s.slots:
            key = slot.key or f"{slot.city}|{slot.unit}"
            if key not in [k for k, _ in slots]:
                slots.append((key, f"{slot.city} – {slot.unit}"))
    headers = ["Section", "Question", "Tag", "Max score", *[label for _, label in slots]]
    rows = []
    for s in sections:
        by_key = {x.key or f"{x.city}|{x.unit}": x for x in s.slots}
        for q in s.questions:
            row = [s.section, q.code, q.tag, q.max_score if q.max_score is not None else ""]
            for key, _ in slots:
                slot = by_key.get(key)
                row.append(_shown(slot.scores.get(q.code)) if slot else "")
            rows.append(row)
    return Table(headers, rows)


def difference(people: Table, ai: Table, key_cols: int) -> Table:
    """AI - People for every cell both have a number in; text ("NA", "Partial") if they differ
    only there; blank otherwise. Rows and columns are matched by their labels."""
    headers = ai.headers if ai.headers else people.headers
    by_key = {tuple(r[:key_cols]): r for r in people.rows}
    people_cols = {h: i for i, h in enumerate(people.headers)}
    rows = []
    for row in ai.rows:
        match = by_key.get(tuple(row[:key_cols]))
        out = list(row[:key_cols])
        for i in range(key_cols, len(headers)):
            a = row[i] if i < len(row) else ""
            p = ""
            if match is not None and headers[i] in people_cols:
                p = match[people_cols[headers[i]]]
            if isinstance(a, int | float) and isinstance(p, int | float):
                out.append(round(a - p, 2))
            else:
                out.append("")
        rows.append(out)
    return Table(headers, rows)


def side_by_side(people: Table, ai: Table, key_cols: int) -> Table:
    """Rows of both tables joined on their first `key_cols` columns, each value column twice."""
    keys, rows = [], []
    for table in (people, ai):
        for r in table.rows:
            if tuple(r[:key_cols]) not in keys:
                keys.append(tuple(r[:key_cols]))
    p_idx = {tuple(r[:key_cols]): r for r in people.rows}
    a_idx = {tuple(r[:key_cols]): r for r in ai.rows}
    value_headers = [h for h in ai.headers[key_cols:]] or people.headers[key_cols:]
    headers = list(ai.headers[:key_cols] or people.headers[:key_cols])
    for h in value_headers:
        headers += [f"{h} · People", f"{h} · AI"]
    p_cols = {h: i for i, h in enumerate(people.headers)}
    a_cols = {h: i for i, h in enumerate(ai.headers)}
    for k in keys:
        out = list(k)
        for h in value_headers:
            p = p_idx.get(k)
            a = a_idx.get(k)
            out += [
                p[p_cols[h]] if p is not None and h in p_cols else "",
                a[a_cols[h]] if a is not None and h in a_cols else "",
            ]
        rows.append(out)
    return Table(headers, rows)


def views(sections: list[SectionSummary]) -> dict[str, Table]:
    return {
        "City systems": city_systems(sections),
        "Parastatals": parastatal_scores(sections),
        "Questions": question_matrix(sections),
    }


KEY_COLUMNS = {"City systems": 1, "Parastatals": 3, "Questions": 3}


def consolidated(
    people: list[SectionSummary], ai: list[SectionSummary]
) -> dict[str, dict[str, Table]]:
    """{"People": views, "AI": views, "Difference": views}."""
    p, a = views(people), views(ai)
    return {
        "People": p,
        "AI": a,
        "Difference": {name: difference(p[name], a[name], KEY_COLUMNS[name]) for name in p},
    }


def note_lines(*sets: list[SectionSummary]) -> list[str]:
    out = []
    for sections in sets:
        for s in sections:
            out += s.notes
            if not s.calculated:
                out.append(
                    f"{s.path.name}: the scores are not calculated (open it in Excel and save)."
                )
    return list(dict.fromkeys(out))
