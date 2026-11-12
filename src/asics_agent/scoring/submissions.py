"""People's filled scoring templates: check them, preview them, store them as submissions.

A submission is one uploaded .xlsx, kept exactly as it came (never edited, never overwritten),
with a sidecar JSON saying who scored it, who uploaded it, when, and which template and question
bank it was made with:

  scoring/2027/human/<category>/<section>/submissions/<timestamp>_<scorer>_<hash8>.xlsx
                                                      <same name>.json     (the sidecar)
                                                      index.json           (the registry)

The sidecars are the record; index.json is rebuilt from them, so two uploads at the same moment
cannot lose an entry. Nothing here opens a file with anything but openpyxl: no macro runs, no
formula is calculated and no link is refreshed. human_merge.py builds the merged people's workbook
from these files.
"""

import hashlib
import io
import json
import os
import re
import tempfile
import warnings
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from openpyxl import load_workbook

from asics_agent import bank_version as bv
from asics_agent.bank_status import build_context
from asics_agent.categories import load_bank
from asics_agent.scoring.name_resolution import (
    Decision,
    Resolution,
    resolve_file,
    stamp,
)
from asics_agent.scoring.template_fill import check_value, template_hash
from asics_agent.scoring.template_import import (
    EVIDENCE_FIELDS,
    TemplateRead,
    read_filled_template,
    read_structures,
)

MAX_BYTES = 25 * 1024 * 1024  # one uploaded file
MAX_UNZIPPED = 400 * 1024 * 1024  # what an .xlsx may unpack to (a zip bomb is small on disk)
MAX_ENTRIES = 3000
MAX_ISSUES_KEPT = 200
NO_VALUE_NOTE = "formula with no saved value"  # the reader's wording for a Score with no cache


class SubmissionError(Exception):
    """A submission that can't be stored, in words the user can act on."""


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def scorer_key(name: str) -> str:
    return re.sub(r"\s+", " ", _text(name)).casefold()


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", _text(name)).strip("-").lower()[:40] or "scorer"


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# -- where things live ---------------------------------------------------------------------------
def human_root(settings) -> Path:
    return settings.scoring_dir / "human" / settings.category


def submissions_dir(settings, section: str) -> Path:
    return human_root(settings) / section / "submissions"


def copies_dir(settings, section: str) -> Path:
    return human_root(settings) / section / "copies"


def merged_dir(settings) -> Path:
    return settings.scoring_dir / "merged"


def merged_path(settings, section: str) -> Path:
    """e.g. merged/PARASTATAL_UPD_human.xlsx (ULG's older merged/UPD_human.xlsx is another file)."""
    return merged_dir(settings) / f"{settings.scoring_code}_{section}_human.xlsx"


# -- is the file safe to open? -------------------------------------------------------------------
def unsafe_reasons(name: str, data: bytes) -> list[str]:
    """Why a file must not even be opened. Only a plain .xlsx workbook is accepted."""
    suffix = Path(name).suffix.lower()
    if suffix != ".xlsx":
        what = "macros are not allowed" if suffix in {".xlsm", ".xlsb", ".xltm"} else "only .xlsx"
        return [
            f'"{name}" is a {suffix or "file without an extension"} file: {what}. In Excel, '
            "use Save As and choose Excel Workbook (.xlsx)."
        ]
    if len(data) > MAX_BYTES:
        return [f"The file is {len(data) / 1e6:.0f} MB; the limit is {MAX_BYTES // 1_000_000} MB."]
    if not data:
        return ["The file is empty."]
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            infos = z.infolist()
            names = {i.filename for i in infos}
            if "xl/workbook.xml" not in names:
                return ["This is not an Excel workbook (.xlsx): it has no workbook inside."]
            if len(infos) > MAX_ENTRIES or sum(i.file_size for i in infos) > MAX_UNZIPPED:
                return ["The file is far larger inside than it looks, so it was not opened."]
            if any(n.lower().endswith("vbaproject.bin") for n in names):
                return ["The workbook contains macros, which are not allowed. Save it without."]
            types = z.read("[Content_Types].xml").decode("utf8", "ignore").lower()
            if "macroenabled" in types:
                return ["The workbook is macro-enabled, which is not allowed. Save it as .xlsx."]
    except (zipfile.BadZipFile, KeyError):
        return ["This is not a readable Excel workbook (.xlsx); it may be damaged."]
    return []


# -- the templates the category is scored in -----------------------------------------------------
@lru_cache(maxsize=16)
def _template_specs(path: str, mtime: float):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return read_structures(load_workbook(path))


def template_specs(path: Path):
    return _template_specs(str(path), Path(path).stat().st_mtime)


def section_templates(settings) -> dict[str, Path]:
    from asics_agent.scoring.template_scoring import template_sections

    return template_sections(settings.scoring_templates)


# -- the preview ---------------------------------------------------------------------------------
@dataclass
class Preview:
    name: str
    size: int
    sha256: str
    section: str
    errors: list[str] = field(default_factory=list)  # nothing can be saved
    warnings: list[str] = field(default_factory=list)  # saved, but worth a look
    template: str = ""
    template_sha256: str = ""
    bank_version: str = ""
    sheets_read: list[str] = field(default_factory=list)
    rows_read: int = 0
    rows_with_score: int = 0
    rows_with_values: int = 0
    ignored: list[str] = field(default_factory=list)  # rows and sheets not read, and why
    formula_no_value: list[str] = field(default_factory=list)
    retired_or_changed: list[str] = field(default_factory=list)
    not_allowed: list[str] = field(default_factory=list)
    not_in_register: list[str] = field(default_factory=list)
    other: list[str] = field(default_factory=list)
    duplicate_of: str = ""  # the submission with the same file hash
    scorers_in_file: list[str] = field(default_factory=list)
    resolutions: list[Resolution] = field(default_factory=list)  # the cities and parastatals

    @property
    def can_save(self) -> bool:
        return not self.errors and not self.duplicate_of

    @property
    def issue_count(self) -> int:
        return sum(
            len(x)
            for x in (
                self.formula_no_value,
                self.retired_or_changed,
                self.not_allowed,
                self.not_in_register,
                self.other,
            )
        )

    def issues(self) -> list[str]:
        out = [
            *(f"formula with no saved value: {x}" for x in self.formula_no_value),
            *(f"retired or changed question: {x}" for x in self.retired_or_changed),
            *(f"value not allowed: {x}" for x in self.not_allowed),
            *(f"not in the register: {x}" for x in self.not_in_register),
            *self.other,
        ]
        return out[:MAX_ISSUES_KEPT]


def _match_template(p: Preview, read: TemplateRead, templates: dict[str, Path], section: str):
    """Fill the preview's template match, or its error: the sheets' question codes against each
    of the category's templates."""
    codes = {s: set(template_specs(path)) for s, path in templates.items()}
    found = set(read.questions)
    if not found:
        skipped = [s for s, why in read.report.sheets_skipped if "by its name" not in why][:8]
        p.errors.append(
            "This does not look like one of the scoring templates: no sheet has a question "
            "table (City and Score columns) with a question code."
            + (f" Sheets in the file: {', '.join(skipped)}." if skipped else "")
        )
        return
    overlap = {s: len(found & c) for s, c in codes.items()}
    best = max(overlap, key=overlap.get)
    if overlap[best] == 0:
        p.errors.append(
            f"None of this file's question sheets ({', '.join(sorted(found)[:6])}) is a question "
            f"of the {', '.join(sorted(codes))} templates. Is it the right template?"
        )
        return
    if best != section and overlap[best] > overlap[section]:
        p.errors.append(
            f"This is the {best} template, but {section} is chosen. Choose {best} and add the "
            "file again."
        )
        return
    mine = codes[section]
    if len(found & mine) < len(mine) / 2:
        p.errors.append(
            f"Only {len(found & mine)} of the {len(mine)} question sheets of the {section} "
            "template are in this file, so it is not that template (or it has been cut down)."
        )
        return
    missing, extra = sorted(mine - found), sorted(found - mine)
    if missing:
        p.warnings.append(
            f"{len(missing)} question sheet(s) of the {section} template are not in this file "
            f"(deleted or renamed): {', '.join(missing[:8])}{'…' if len(missing) > 8 else ''}."
        )
    if extra:
        p.warnings.append(
            f"Sheets for questions the {section} template doesn't have: {', '.join(extra)}. "
            "They are kept in the submission but not merged."
        )
    p.template = templates[section].name
    p.template_sha256 = template_hash(templates[section])


def preview_file(settings, section: str, name: str, data: bytes) -> Preview:
    """Everything the user should see before saving. Reads the file; stores nothing."""
    p = Preview(name=name, size=len(data), sha256=sha256_of(data), section=section)
    p.errors += unsafe_reasons(name, data)
    templates = section_templates(settings)
    if section not in templates:
        p.errors.append(f"{settings.category_title} has no {section} scoring template.")
    if p.errors:
        return p
    if (dup := find_by_hash(settings, p.sha256)) is not None:
        p.duplicate_of = dup.submission_id
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "upload.xlsx"
        path.write_bytes(data)
        try:
            read = read_filled_template(path, "")
        except Exception as exc:
            p.errors.append(
                f"The workbook could not be opened ({type(exc).__name__}). Open it in Excel, "
                "save it as .xlsx, and add it again."
            )
            return p
    read.path = Path(name)
    read.report.file = name
    _match_template(p, read, templates, section)
    if p.errors:
        return p
    bank, _ = load_bank(settings)
    current = bv.bank_version(settings.question_bank, bank) if bank else None
    p.bank_version = current.version if current else ""
    _analyse(settings, p, read, templates[section], bank)
    if not p.rows_with_values:
        p.errors.append(
            "No row has a score, an input or any evidence yet, so there is nothing to store. "
            "Fill the template in first."
        )
    return p


def _analyse(settings, p: Preview, read: TemplateRead, template: Path, bank) -> None:
    report = read.report
    p.sheets_read = list(report.sheets_read)
    p.rows_read = report.rows_read
    p.ignored = [f"Sheet {s}, row {r}: {why}" for s, r, why in report.rows_skipped]
    p.ignored += [
        f"Sheet {s} not read: {why}" for s, why in report.sheets_skipped if "by its name" not in why
    ]
    for line in report.problems:
        (p.formula_no_value if NO_VALUE_NOTE in line else p.other).append(line)
    for sheet, headers in report.unknown_columns.items():
        p.warnings.append(
            f"Sheet {sheet} has columns the template doesn't: {', '.join(headers)}. They are "
            "kept in the submission but not merged."
        )
    ctx = build_context(bank, settings.question_bank)
    for code, meta in read.questions.items():
        note = ctx.flag(code, meta.text)
        if note:
            p.retired_or_changed.append(f"{code}: {note}")
    specs = template_specs(template)
    p.resolutions = resolve_file(settings, read)
    for row in read.rows:
        spec = specs.get(row.code)
        has_values = (
            row.score is not None
            or bool(row.inputs)
            or any(getattr(row, f) for f in EVIDENCE_FIELDS)
        )
        p.rows_with_score += row.score is not None
        p.rows_with_values += bool(has_values)
        if row.scorer and row.scorer not in p.scorers_in_file:
            p.scorers_in_file.append(row.scorer)
        if not has_values:
            continue
        where = f"Sheet {row.sheet}, row {row.row} ({row.city} / {row.parastatal})"
        if spec is None:
            continue
        by_header = {c.header: col for col, c in spec.columns.items() if c.kind == "input"}
        for header, value in row.inputs.items():
            if header in by_header:
                _, why = check_value(spec, by_header[header], value)
                if why:
                    p.not_allowed.append(f'{where}: "{header}" {why}.')
        if row.score is not None and spec.score_column and not spec.score_is_formula:
            _, why = check_value(spec, spec.score_column, row.score)
            if why and not row.score_note:
                p.not_allowed.append(f"{where}: the score {why}.")
    for r in p.resolutions:
        if not r.needs_decision:
            continue
        near = f" (closest in the register: {r.match.name})" if r.match.kind == "close" else ""
        where = f" of {r.city_as_written}" if r.kind == "parastatal" else ""
        p.not_in_register.append(
            f"the {r.kind} {r.as_written}{where} is not in the register{near}. Map it to an "
            "existing one, add it as new (kept in people's scoring only) or skip it."
        )
    if p.formula_no_value:
        p.warnings.append(
            f"{len(p.formula_no_value)} score formula(s) have no saved value. Open the file in "
            "Excel and save it first. It can still be stored: the merge recalculates from the "
            "inputs."
        )


# -- stored submissions --------------------------------------------------------------------------
@dataclass
class Submission:
    submission_id: str
    section: str
    scorer: str
    uploaded_by: str
    uploaded_at: str
    file_name: str  # the stored file's name
    original_name: str
    file_sha256: str
    template_name: str
    template_sha256: str
    bank_version: str
    rows_read: int
    rows_with_score: int
    rows_with_values: int
    issue_count: int
    category: str = ""
    source: str = "human"
    replaces: list = field(default_factory=list)  # earlier submissions of the same scorer
    issues: list = field(default_factory=list)
    decisions: list = field(default_factory=list)  # what was decided about names (name_resolution)
    decision_history: list = field(default_factory=list)  # earlier decisions, never deleted
    path: Path | None = None

    def as_dict(self) -> dict:
        d = dict(self.__dict__)
        d.pop("path", None)
        return d


def _from_sidecar(path: Path) -> Submission | None:
    try:
        raw = json.loads(path.read_text())
        names = Submission.__dataclass_fields__
        sub = Submission(**{k: v for k, v in raw.items() if k in names and k != "path"})
    except (OSError, ValueError, TypeError):
        return None
    sub.path = path.with_suffix(".xlsx")
    return sub


def list_submissions(settings, section: str | None = None) -> list[Submission]:
    """Every stored submission of the category (or one section), oldest first."""
    sections = [section] if section else sorted(section_templates(settings))
    found = []
    for s in sections:
        for sidecar in sorted(submissions_dir(settings, s).glob("*.json")):
            if sidecar.name == "index.json":
                continue
            if (sub := _from_sidecar(sidecar)) is not None:
                found.append(sub)
    return sorted(found, key=lambda x: (x.uploaded_at, x.submission_id))


def find_by_hash(settings, sha: str) -> Submission | None:
    return next((s for s in list_submissions(settings) if s.file_sha256 == sha), None)


def _write_atomic(path: Path, data: bytes, *, exclusive: bool = False) -> None:
    """Write beside the target, then rename into place. Exclusive: never replaces a file."""
    if exclusive and path.exists():
        raise SubmissionError(f"{path.name} already exists; a submission is never overwritten.")
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".part-")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        if exclusive:
            os.link(tmp, path)  # fails if the file appeared in the meantime
            os.unlink(tmp)
        else:
            os.replace(tmp, path)
    except FileExistsError as exc:
        os.unlink(tmp)
        raise SubmissionError(
            f"{path.name} already exists; a submission is never overwritten."
        ) from exc
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def rebuild_index(settings, section: str) -> Path:
    """The section's registry (index.json), rebuilt from the sidecars."""
    folder = submissions_dir(settings, section)
    folder.mkdir(parents=True, exist_ok=True)
    rows = [s.as_dict() for s in list_submissions(settings, section)]
    for row in rows:
        row.pop("issues", None)
    path = folder / "index.json"
    _write_atomic(path, json.dumps({"section": section, "submissions": rows}, indent=2).encode())
    return path


def save_submission(
    settings,
    preview: Preview,
    data: bytes,
    scorer: str,
    uploaded_by: str = "",
    decisions: list[Decision] | None = None,
) -> Submission:
    """Store a previewed file as an immutable submission. The scorer's name is typed, never
    taken from the file name."""
    scorer = re.sub(r"\s+", " ", _text(scorer))
    if not scorer:
        raise SubmissionError("Type the name of the person who scored this file.")
    if preview.errors:
        raise SubmissionError(preview.errors[0])
    if sha256_of(data) != preview.sha256:
        raise SubmissionError("The file changed since it was checked. Add it again.")
    if (dup := find_by_hash(settings, preview.sha256)) is not None:
        raise SubmissionError(
            f"This exact file is already stored ({dup.submission_id}, scorer {dup.scorer}); "
            "nothing was added."
        )
    now = datetime.now(UTC)
    sub_id = f"{now:%Y%m%dT%H%M%SZ}_{_slug(scorer)}_{preview.sha256[:8]}"
    folder = submissions_dir(settings, preview.section)
    folder.mkdir(parents=True, exist_ok=True)
    earlier = [
        s.submission_id
        for s in list_submissions(settings, preview.section)
        if scorer_key(s.scorer) == scorer_key(scorer)
    ]
    sub = Submission(
        submission_id=sub_id,
        section=preview.section,
        scorer=scorer,
        uploaded_by=_text(uploaded_by) or scorer,
        uploaded_at=now.isoformat(timespec="seconds"),
        file_name=f"{sub_id}.xlsx",
        original_name=preview.name,
        file_sha256=preview.sha256,
        template_name=preview.template,
        template_sha256=preview.template_sha256,
        bank_version=preview.bank_version,
        rows_read=preview.rows_read,
        rows_with_score=preview.rows_with_score,
        rows_with_values=preview.rows_with_values,
        issue_count=preview.issue_count,
        category=settings.category,
        replaces=earlier,
        issues=preview.issues(),
        decisions=[
            stamp(d, _text(uploaded_by) or scorer, sub_id).as_dict() for d in decisions or []
        ],
    )
    path = folder / sub.file_name
    _write_atomic(path, data, exclusive=True)
    _write_atomic(path.with_suffix(".json"), json.dumps(sub.as_dict(), indent=2).encode())
    sub.path = path
    rebuild_index(settings, preview.section)
    return sub


def update_decisions(
    settings, submission_id: str, decisions: list[Decision], by: str
) -> Submission:
    """Change what was decided about names for a stored submission. The uploaded file is not
    touched; the earlier decisions move to the sidecar's decision_history."""
    sub = next((s for s in list_submissions(settings) if s.submission_id == submission_id), None)
    if sub is None:
        raise SubmissionError(f"There is no stored submission {submission_id}.")
    sub.decision_history += sub.decisions
    sub.decisions = [stamp(d, by, submission_id).as_dict() for d in decisions]
    _write_atomic(sub.path.with_suffix(".json"), json.dumps(sub.as_dict(), indent=2).encode())
    rebuild_index(settings, sub.section)
    return sub
