"""Human scores against the AI's, one row per (unit, question), for one city.

Human data is read from filled scoring templates (template_import.py). The AI's data is what the
repo already saves: the Step 2 answers workbook (answer, class, confidence, citation) and the
Step 3 AI scoring workbook (`Scores (start here)`, plus the run logs for its inputs). Rows are
matched by city + the unit's short code (BWSSB) + the normalised question code. A parastatal or a
question nobody knows goes to a review list; it is never created or silently dropped.

"Agrees?" is an exact match: the same tolerance as the Scores page's "Same score?"
(scoring/scores.py). Other rules (a tolerance, the same band, the same source) are shown beside it
but are not used to decide agreement; which rule to adopt is the program team's decision.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from asics_agent.agents.initial_checks import _SCALE
from asics_agent.models import Question
from asics_agent.parastatal_types import ULG_TYPE, canonical_type, known_type
from asics_agent.scoring.ai import same_question
from asics_agent.scoring.human import SEPARATOR, city_of
from asics_agent.scoring.name_resolution import NOT_IN_REGISTER, split_label
from asics_agent.scoring.template_import import TemplateRead, normalise_code

SAME_SCORE = 1e-9  # as scoring/scores.py ("Same score?")
MIN_ROWS = 20  # fewer compared rows than this: no percentage (a setting; --min-rows)
ULG_UNIT = "ULG"
REVIEW_SHEET_NAMES = ("Scores (start here)",)
STATUSES = (
    "both",
    "only human",
    "only AI",
    "neither",
    "retired question",
    "question not in this bank version",
    "question changed",
)
_HEAD = PatternFill("solid", fgColor="DDE7F0")


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def _key(text) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text or "").casefold())


def _number(value) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(_text(value))
    except ValueError:
        return None


def normalise_url(url: str) -> str:
    """The same page written differently (scheme, www, trailing slash, tracking, #fragment)."""
    text = _text(url)
    if not text:
        return ""
    parts = urlsplit(text if "//" in text else "//" + text)
    query = urlencode(
        sorted((k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith("utm_"))
    )
    host = parts.netloc.lower().removeprefix("www.")
    path = parts.path.rstrip("/")
    return f"{host}{path}" + (f"?{query}" if query else "")


def scale_of(methodology: str) -> list[float]:
    """The scores a question's methodology lists (its bands), as the initial checks read them."""
    return sorted({float(n) for n in _SCALE.findall(methodology or "")})


def band_of(score: float | None, scale: list[float]) -> str:
    if score is None or not scale:
        return ""
    near = next((v for v in scale if abs(v - score) < SAME_SCORE), None)
    return f"{near:g}" if near is not None else "between bands"


# -- the AI's side -------------------------------------------------------------------------------
@dataclass
class Step2Row:
    unit: str  # the unit's short code (BWSSB, ULG) or the name found when unknown
    raw_id: str
    question: str = ""
    proposed_score: float | None = None
    answer_class: str = ""
    confidence: str = ""
    rubric_band: str = ""
    citation_url: str = ""
    where_to_find: str = ""
    status: str = ""
    unit_type: str = ""
    known_unit: bool = True


@dataclass
class Step3Row:
    ai_score: float | None = None
    your_score: float | None = None
    link: str = ""
    status: str = ""
    inputs: dict = field(default_factory=dict)
    chapter: str = ""
    provision: str = ""
    clause: str = ""
    confidence: str = ""
    question_text: str = ""
    citation_id: str = ""  # the Citation Sheet row the AI relied on
    quote: str = ""  # the passage it quoted
    score_note: str = ""  # why there is no score (e.g. not calculated yet)


def read_step2(
    answers: Path, unit_ids: dict[str, str], unit_types: dict[str, str] | None = None
) -> dict[tuple[str, str], Step2Row]:
    """{(unit, raw question id): row} from a Step 2 answers workbook, columns found by header.
    `unit_ids` maps a unit's name or short code (any capitals) to its short code."""
    from asics_agent.workbook import canonical_header, is_scoring_sheet

    wb = load_workbook(answers, read_only=True, data_only=True)
    sheet = next((ws for ws in wb.worksheets if is_scoring_sheet(ws.title)), None)
    out: dict[tuple[str, str], Step2Row] = {}
    if sheet is None:
        return out
    rows = sheet.iter_rows(values_only=True)
    header = [canonical_header(_text(h)) for h in next(rows, ())]
    col = {_key(h): i for i, h in enumerate(header) if h}

    def get(row, name):
        i = col.get(_key(name))
        return "" if i is None or i >= len(row) or row[i] is None else row[i]

    for row in rows:
        name, raw = _text(get(row, "Parastatal")), _text(get(row, "Question ID"))
        if not name or not raw:
            continue
        unit = unit_ids.get(name.casefold())
        out[(unit or name, raw)] = Step2Row(
            unit=unit or name,
            raw_id=raw,
            question=_text(get(row, "Question")),
            proposed_score=_number(get(row, "Proposed Score")),
            answer_class=_text(get(row, "Class")),
            confidence=_text(get(row, "Confidence")),
            rubric_band=_text(get(row, "Rubric Band")),
            citation_url=_text(get(row, "Citation URL")),
            where_to_find=_text(get(row, "Where to Find It")),
            status=_text(get(row, "Status")),
            unit_type=_text(get(row, "Parastatal Type")),
            known_unit=unit is not None,
        )
    return out


def read_step3(
    ai_workbook: Path, runs_dir: Path | None, scoring_code: str
) -> dict[tuple[str, str], Step3Row]:
    """{(normalised code, row label): row} from the AI scoring workbook's review sheet (found by
    header text), with each row's inputs from the latest run log that scored it."""
    out: dict[tuple[str, str], Step3Row] = {}
    if ai_workbook is None or not Path(ai_workbook).exists():
        return out
    wb = load_workbook(ai_workbook, read_only=True, data_only=True)
    ws = next((wb[n] for n in REVIEW_SHEET_NAMES if n in wb.sheetnames), None)
    if ws is not None:
        rows = ws.iter_rows(values_only=True)
        header = [_key(h) for h in next(rows, ())]
        col = {h: i for i, h in enumerate(header) if h}

        def get(row, name):
            i = col.get(_key(name))
            return "" if i is None or i >= len(row) or row[i] is None else row[i]

        for row in rows:
            code = _text(get(row, "Question"))
            label = _text(get(row, "Row"))
            norm = normalise_code(code)
            if not norm or not label:
                continue
            out[(norm, label)] = Step3Row(
                ai_score=_number(get(row, "AI score")),
                your_score=_number(get(row, "★ Your score")),
                link=_text(get(row, "Link")),
                status=_text(get(row, "Status")),
                question_text=_text(get(row, "Question text")),
            )
    latest: dict[tuple[str, str], dict] = {}
    for path in sorted(Path(runs_dir).glob(f"{scoring_code}_*.jsonl")) if runs_dir else []:
        try:
            lines = path.read_text().splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            norm = normalise_code(rec.get("code", ""))
            if not norm or not rec.get("row"):
                continue
            key = (norm, _text(rec["row"]))
            if key not in latest or _text(rec.get("at")) >= _text(latest[key].get("at")):
                latest[key] = rec
    for key, rec in latest.items():
        row = out.setdefault(key, Step3Row())
        row.inputs = rec.get("inputs") or {}
        row.chapter, row.provision = _text(rec.get("chapter")), _text(rec.get("provision"))
        row.clause, row.confidence = _text(rec.get("clause")), _text(rec.get("confidence"))
        if not row.link:
            row.link = _text(rec.get("link"))
    return out


# -- the comparison ------------------------------------------------------------------------------
@dataclass
class Unit:
    id: str  # short code, e.g. BWSSB, or ULG
    name: str = ""
    type: str = ""  # a type code, or ULG_TYPE


@dataclass
class CityInputs:
    city: str  # the register's name
    aliases: list[str]  # other names the files may use (Bangalore)
    units: dict[str, Unit]  # short code -> unit (the register and the Sources workbook)
    bank: dict[str, Question]  # the current bank, by normalised code
    retired: dict[str, Question] = field(default_factory=dict)  # codes of earlier banks
    raw_to_code: dict[str, str] = field(default_factory=dict)  # a bank's own id -> normalised
    old_raw_to_code: dict[str, str] = field(default_factory=dict)  # same, for earlier banks
    step2: dict[tuple[str, str], Step2Row] = field(default_factory=dict)
    step3: dict[tuple[str, str], Step3Row] = field(default_factory=dict)
    ulg: bool = False  # the ULG category: one unit per city, labelled by the bare city name
    bank_version: str = ""
    notes: list[str] = field(default_factory=list)
    unregistered: set = field(default_factory=set)  # unit codes the register lacks
    city_in_register: bool = True


@dataclass
class CompareRow:
    city: str
    unit: str
    unit_type: str
    code: str
    section: str
    status: str
    question: str = ""
    max_score: float | None = None
    human_score: float | None = None
    ai_score: float | None = None
    ai_score_from: str = ""
    difference: float | None = None
    agrees: str = ""
    human_band: str = ""
    ai_band: str = ""
    same_band: str = ""
    human_inputs: str = ""
    ai_inputs: str = ""
    inputs_in_common: str = ""
    human_source: str = ""
    human_location: str = ""
    ai_citation_url: str = ""
    ai_where_to_find: str = ""
    ai_step3_link: str = ""
    ai_citation_id: str = ""
    ai_quote: str = ""
    same_source: str = ""
    ai_class: str = ""
    ai_confidence: str = ""
    ai_rubric_band: str = ""
    scorer: str = ""
    human_file: str = ""
    human_comments: str = ""
    notes: list[str] = field(default_factory=list)


@dataclass
class Comparison:
    city: str
    rows: list[CompareRow] = field(default_factory=list)
    review: list[tuple[str, str]] = field(default_factory=list)  # (what, why)
    notes: list[str] = field(default_factory=list)
    bank_version: str = ""
    files: list[str] = field(default_factory=list)


def _inputs_text(values: dict) -> str:
    return "; ".join(f"{k}: {v}" for k, v in values.items() if v not in (None, ""))


def _inputs_overlap(human: dict, ai: dict) -> str:
    h = {_key(k): v for k, v in human.items() if v not in (None, "")}
    a = {_key(k): v for k, v in (ai or {}).items() if v not in (None, "")}
    common = set(h) & set(a)
    if not common:
        return "no inputs with the same name" if h and a else ""
    same = sum(1 for k in common if _text(h[k]).casefold() == _text(a[k]).casefold())
    return f"{same} same, {len(common) - same} different"


def _label(unit: str, city: str, ulg: bool) -> str:
    return city if ulg else f"{city}{SEPARATOR}{unit}"


def code_for_raw(raw: str, info: CityInputs) -> tuple[str | None, bool]:
    """(normalised code, found in the current bank) for the id a Step 2 file uses."""
    from asics_agent.bank_status import BankContext

    return BankContext(
        info.bank, info.retired, info.raw_to_code, info.old_raw_to_code
    ).code_for_raw(raw)


def compare_city(info: CityInputs, templates: list[TemplateRead]) -> Comparison:
    """Compare the human rows of `templates` for `info.city` with the AI's saved results."""
    out = Comparison(info.city, bank_version=info.bank_version, notes=list(info.notes))
    names = {n.casefold() for n in [info.city, *info.aliases]}
    unit_lookup = {u.id.casefold(): u for u in info.units.values()}
    unit_lookup.update({u.name.casefold(): u for u in info.units.values() if u.name})
    ulg_names = {n.casefold() for n in [info.city, *info.aliases, ULG_UNIT.casefold()]}

    # (unit id, code) -> sources
    human: dict[tuple[str, str], object] = {}
    template_text: dict[str, str] = {}
    for t in templates:
        out.files.append(t.path.name)
        unclassified = [  # sheets skipped by their name (Instructions...) are expected
            f"Sheet {s}: {why}" for s, why in t.report.sheets_skipped if "by its name" not in why
        ]
        for line in t.report.problems + unclassified:
            out.review.append((f"{t.path.name}", line))
        for sheet, row, why in t.report.rows_skipped:
            out.review.append((f"{t.path.name} / {sheet} row {row}", f"row skipped: {why}"))
        for row in t.rows:
            if _text(row.city).casefold() not in names:
                continue
            unit = unit_lookup.get(row.parastatal.casefold())
            if info.ulg and row.parastatal.casefold() in ulg_names:
                unit = unit_lookup.get(ULG_UNIT.casefold()) or Unit(ULG_UNIT, info.city, ULG_TYPE)
            if unit is None:
                out.review.append(
                    (
                        f"{t.path.name} / {row.sheet} row {row.row}",
                        f"The parastatal {row.parastatal} ({row.city}) is not a known unit of "
                        f"{info.city}, so it was not matched with the AI's. Add it to the city "
                        "register or fix its short code in the template.",
                    )
                )
                unit = Unit(row.parastatal, row.parastatal, canonical_type(row.parastatal_type))
            human[(unit.id, row.code)] = row
            template_text[row.code] = (
                t.questions.get(row.code).text if row.code in t.questions else ""
            )

    ai_keys: dict[tuple[str, str], tuple[Step2Row | None, Step3Row | None]] = {}
    for (unit_name, raw), s2 in info.step2.items():
        code, _ = code_for_raw(raw, info)
        if code is None:
            out.review.append(
                (f"Step 2 answer {unit_name} / {raw}", "The question id is not a code we can read.")
            )
            continue
        if not s2.known_unit:
            out.review.append(
                (
                    f"Step 2 answer {unit_name} / {raw}",
                    f"The Step 2 file names {unit_name}, which is not a known unit of {info.city}.",
                )
            )
        ai_keys[(s2.unit, code)] = (s2, ai_keys.get((s2.unit, code), (None, None))[1])
    for (code, label), s3 in info.step3.items():
        if _text(city_of(label)).casefold() not in names:
            continue
        who = split_label(label)[1] or ULG_UNIT
        unit = unit_lookup.get(who.casefold())
        if unit is None and not info.ulg:
            out.review.append(
                (f"AI score {label} / {code}", f"{who} is not a known unit of {info.city}.")
            )
        unit_id = unit.id if unit else who
        ai_keys[(unit_id, code)] = (ai_keys.get((unit_id, code), (None, None))[0], s3)

    for key in sorted(set(human) | set(ai_keys)):
        unit_id, code = key
        h = human.get(key)
        s2, s3 = ai_keys.get(key, (None, None))
        unit = info.units.get(unit_id) or unit_lookup.get(unit_id.casefold())
        unit_type = (unit.type if unit else "") or (
            canonical_type(h.parastatal_type) if h and known_type(h.parastatal_type) else ""
        )
        if not unit_type and s2 and s2.unit_type:
            unit_type = canonical_type(s2.unit_type) if known_type(s2.unit_type) else ""
        q = info.bank.get(code)
        row = CompareRow(
            city=info.city,
            unit=unit_id,
            unit_type=unit_type or "unknown",
            code=code,
            section=code.split(" ")[0],
            status="",
            question=q.text if q else "",
            max_score=q.max_score if q else (h.max_score if h else None),
            scorer=h.scorer if h else "",
            human_file=h.file if h else "",
        )
        if unit is None:
            row.notes.append("not matched to a known unit")
        if unit_id in info.unregistered or not info.city_in_register:
            row.notes.append(NOT_IN_REGISTER)
        if q is None:
            archived = info.retired.get(code)
            row.status = "retired question" if archived else "question not in this bank version"
            row.question = archived.text if archived else (template_text.get(code, "") or "")
            row.notes.append(
                "this question is in an earlier question bank but not the current one"
                if archived
                else "the current question bank has no such code"
            )
        scale = scale_of(q.methodology) if q else []
        if h:
            row.human_score = h.score
            if h.score_note:
                row.notes.append(f"human: {h.score_note}")
            row.human_inputs = _inputs_text({**h.inputs, **h.calculated})
            row.human_source = h.source_link
            row.human_location = "; ".join(
                f"{label} {value}"
                for label, value in (
                    ("chapter", h.chapter),
                    ("provision", h.provision),
                    ("clause", h.clause),
                    ("page", h.page),
                )
                if value
            )
            row.human_comments = h.comments
            row.human_band = band_of(h.score, scale)
        if s2:
            row.ai_class, row.ai_confidence = s2.answer_class, s2.confidence
            row.ai_rubric_band = s2.rubric_band
            row.ai_citation_url, row.ai_where_to_find = s2.citation_url, s2.where_to_find
        if s3:
            row.ai_step3_link = s3.link
            row.ai_citation_id, row.ai_quote = s3.citation_id, s3.quote
            if s3.score_note:
                row.notes.append(f"AI: {s3.score_note}")
            row.ai_confidence = row.ai_confidence or s3.confidence
            row.ai_inputs = _inputs_text(s3.inputs)
            if s3.ai_score is not None:
                row.ai_score, row.ai_score_from = s3.ai_score, "Step 3"
        if row.ai_score is None and s2 and s2.proposed_score is not None:
            row.ai_score, row.ai_score_from = s2.proposed_score, "Step 2 proposal"
        row.ai_band = band_of(row.ai_score, scale)
        row.inputs_in_common = _inputs_overlap(
            {**(h.inputs if h else {}), **(h.calculated if h else {})}, s3.inputs if s3 else {}
        )
        urls = [normalise_url(u) for u in (row.ai_citation_url, row.ai_step3_link) if u]
        if row.human_source and urls:
            row.same_source = "Yes" if normalise_url(row.human_source) in urls else "No"

        # did the human and the AI answer the question the bank now asks?
        if q is not None:
            changed = []
            if (h_text := template_text.get(code, "")) and not same_question(h_text, q.text):
                changed.append("the scoring template asks a different question from the bank")
            if s2 and s2.question and not same_question(s2.question, q.text):
                changed.append("Step 2 answered a different question under this code")
            if s3 and s3.question_text and not same_question(s3.question_text, q.text):
                changed.append("Step 3 scored a different question under this code")
            row.notes += changed
        if row.status == "":
            has_human, has_ai = row.human_score is not None, row.ai_score is not None
            if changed_text := [n for n in row.notes if "different question" in n]:
                row.status = "question changed"
                row.notes.append("not compared: " + "; ".join(changed_text))
            elif has_human and has_ai:
                row.status = "both"
            elif has_human:
                row.status = "only human"
            elif has_ai:
                row.status = "only AI"
            else:
                row.status = "neither"
        if row.status == "both":
            row.difference = round(row.ai_score - row.human_score, 6)
            row.agrees = "Yes" if abs(row.ai_score - row.human_score) < SAME_SCORE else "No"
            row.same_band = (
                ("Yes" if row.human_band == row.ai_band else "No")
                if row.human_band and row.ai_band
                else ""
            )
        out.rows.append(row)
    out.rows.sort(key=lambda r: (r.unit, r.code))
    return out


# -- the summary ---------------------------------------------------------------------------------
def _split_code(code: str):
    m = re.match(r"([A-Za-z]+)\s*(\d+)\s*([a-z]?)", code)
    return (m.group(1), int(m.group(2)), m.group(3)) if m else (code, 0, "")


def summarise(rows: list[CompareRow], key, min_rows: int) -> list[list]:
    """[group, compared, agree, % agree, only human, only AI]: the % shows only from min_rows."""
    groups: dict[str, list[CompareRow]] = {}
    for r in rows:
        groups.setdefault(key(r) or "(blank)", []).append(r)
    out = []
    for name in sorted(groups):
        both = [r for r in groups[name] if r.status == "both"]
        agree = sum(r.agrees == "Yes" for r in both)
        pct = (
            f"{100 * agree / len(both):.0f}%"
            if len(both) >= min_rows
            else f"not shown (fewer than {min_rows} compared)"
        )
        out.append(
            [
                name,
                len(both),
                agree,
                pct,
                sum(r.status == "only human" for r in groups[name]),
                sum(r.status == "only AI" for r in groups[name]),
            ]
        )
    return out


COLUMNS = [
    ("City", "city"),
    ("Unit", "unit"),
    ("Unit type", "unit_type"),
    ("Section", "section"),
    ("Question", "code"),
    ("Status", "status"),
    ("Question text (bank)", "question"),
    ("Max score", "max_score"),
    ("Human score", "human_score"),
    ("AI score", "ai_score"),
    ("AI score from", "ai_score_from"),
    ("Difference (AI − human)", "difference"),
    ("Agrees? (exact)", "agrees"),
    ("Human band", "human_band"),
    ("AI band", "ai_band"),
    ("Same band?", "same_band"),
    ("Human inputs", "human_inputs"),
    ("AI inputs", "ai_inputs"),
    ("Inputs in common", "inputs_in_common"),
    ("Human source link", "human_source"),
    ("Human chapter / provision / clause / page", "human_location"),
    ("AI citation URL (Step 2)", "ai_citation_url"),
    ("AI where to find it (Step 2)", "ai_where_to_find"),
    ("AI link (Step 3)", "ai_step3_link"),
    ("AI citation ID", "ai_citation_id"),
    ("AI quote", "ai_quote"),
    ("Same source?", "same_source"),
    ("AI class", "ai_class"),
    ("AI confidence", "ai_confidence"),
    ("AI rubric band (Step 2)", "ai_rubric_band"),
    ("Scorer", "scorer"),
    ("Human file", "human_file"),
    ("Human comments", "human_comments"),
    ("Notes", "notes"),
]


def write_comparison(
    comp: Comparison, path: Path, min_rows: int = MIN_ROWS, extra: dict | None = None
) -> Path:
    """`extra`: the consolidated tables ({source: {view: Table}}), added as sheets so Excel users
    get the same views as the Scores page."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws.append([f"{comp.city}: human scores compared with the AI's"])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append(
        [
            "Files",
            "; ".join(comp.files) or "none",
        ]
    )
    ws.append(["Question bank", comp.bank_version or "unknown"])
    ws.append(
        [
            "Agrees?",
            "An exact match of the human score and the AI score (same tolerance as the Scores "
            f"page). Percentages show only from {min_rows} compared rows (setting).",
        ]
    )
    by_status = {s: sum(r.status == s for r in comp.rows) for s in STATUSES}
    ws.append([])
    ws.append(["Rows by status", "Rows"])
    for s, n in by_status.items():
        ws.append([s, n])
    header = ["", "Compared (both scored)", "Agree", "% agree", "Only human", "Only AI"]
    for title, key in (
        ("By section", lambda r: r.section),
        ("By AI class", lambda r: r.ai_class or "(no AI class)"),
        ("By parastatal type", lambda r: r.unit_type),
    ):
        ws.append([])
        ws.append([title, *header[1:]])
        for cell in ws[ws.max_row]:
            cell.font, cell.fill = Font(bold=True), _HEAD
        for line in summarise(comp.rows, key, min_rows):
            ws.append(line)
    both = sorted(
        (r for r in comp.rows if r.status == "both" and r.agrees == "No"),
        key=lambda r: -abs(r.difference or 0),
    )
    ws.append([])
    ws.append(["Biggest disagreements first", "Unit", "Human", "AI", "Difference", "AI class"])
    for cell in ws[ws.max_row]:
        cell.font, cell.fill = Font(bold=True), _HEAD
    for r in both[:25]:
        ws.append([r.code, r.unit, r.human_score, r.ai_score, r.difference, r.ai_class])
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 26
    for c in "CDEF":
        ws.column_dimensions[c].width = 18

    cmp = wb.create_sheet("Compare")
    cmp.append([name for name, _ in COLUMNS])
    for cell in cmp[1]:
        cell.font, cell.fill = Font(bold=True), _HEAD
    for r in sorted(comp.rows, key=lambda r: (r.unit, _split_code(r.code))):
        cmp.append(
            ["; ".join(r.notes) if attr == "notes" else getattr(r, attr) for _, attr in COLUMNS]
        )
    for i, (name, _) in enumerate(COLUMNS, start=1):
        cmp.column_dimensions[get_column_letter(i)].width = (
            60
            if "text" in name
            or name
            in (
                "Human inputs",
                "AI inputs",
                "Notes",
            )
            else 18
        )
    cmp.freeze_panes = "G2"
    for row in cmp.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    for source, views in (extra or {}).items():
        for name, table in views.items():
            if not table:
                continue
            sheet = wb.create_sheet(f"{source} - {name}"[:31])
            sheet.append(table.headers)
            for cell in sheet[1]:
                cell.font, cell.fill = Font(bold=True), _HEAD
            for row in table.rows:
                sheet.append(row)
            sheet.freeze_panes = sheet.cell(row=2, column=min(4, len(table.headers)))
            sheet.column_dimensions["A"].width = 18
    rev = wb.create_sheet("Review list")
    rev.append(["Where", "What needs a look"])
    for cell in rev[1]:
        cell.font, cell.fill = Font(bold=True), _HEAD
    for where, why in comp.review:
        rev.append([where, why])
    for n in comp.notes:
        rev.append(["Note", n])
    rev.column_dimensions["A"].width = 50
    rev.column_dimensions["B"].width = 120
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


# -- the AI's side read from the AI's copies of the templates ----------------------------------
_CITATION = re.compile(r"Citation\s+(\S+?):")
_QUOTE = re.compile(r'Quote:\s*"(.*?)"\s*(?:\n|$)', re.S)
_CONFIDENCE = re.compile(r"AI \((\w+) confidence\)")


def step3_from_templates(reads: list[TemplateRead]) -> dict[tuple[str, str], Step3Row]:
    """{(normalised code, row label): row} from AI-filled templates, read with the same reader as
    the human ones. The label is "City – Parastatal" (just the city for a ULG template)."""
    out: dict[tuple[str, str], Step3Row] = {}
    for read in reads:
        for row in read.rows:
            label = f"{row.city}{SEPARATOR}{row.parastatal}" if row.parastatal else row.city
            quote = _QUOTE.search(row.comments)
            cid = _CITATION.search(row.additional_comments)
            conf = _CONFIDENCE.search(row.comments)
            out[(row.code, label)] = Step3Row(
                ai_score=row.score,
                link=row.source_link,
                inputs={**row.inputs, **row.calculated},
                chapter=row.chapter,
                provision=row.provision,
                clause=row.clause,
                confidence=conf.group(1).capitalize() if conf else "",
                question_text=read.questions[row.code].text if row.code in read.questions else "",
                citation_id=cid.group(1) if cid else "",
                quote=quote.group(1) if quote else "",
                score_note=row.score_note,
            )
    return out
