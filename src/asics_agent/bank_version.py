"""Question bank versions.

A bank's version says which questions a run, an answers file or a scoring file was made with, so
a newer bank never silently changes old results. It is

    <source file name>@<date the bank was built>#<first 8 characters of the content hash>

The hash covers only what the questions say (code, text, tag, max score, applicability,
methodology...), never the build date, so building the same source twice gives the same version.
`scripts/build_question_bank.py` writes the details on a "Bank Info" sheet in the bank file;
a bank without that sheet is `<file name>@unversioned#<hash>`.
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from openpyxl import load_workbook

from asics_agent.models import Question

INFO_SHEET = "Bank Info"
SIDECAR_SUFFIX = ".bank_version.json"
_FIELDS = (
    "id",
    "pillar",
    "tag",
    "text",
    "max_score",
    "assessment_level",
    "unit",
    "applicability",
    "methodology",
    "evidence_requirement",
    "rationale",
    "parent_id",
)


@dataclass
class BankVersion:
    version: str
    content_hash: str
    source_file: str = ""  # the file the bank was built from
    source_sha256: str = ""
    built_at: str = ""
    questions: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


def content_hash(questions: dict[str, Question]) -> str:
    """A hash of what the questions say; the same questions always give the same hash."""
    rows = [
        [getattr(q, f) for f in _FIELDS] + [sorted(q.extra.items())]
        for q in sorted(questions.values(), key=lambda q: q.id)
    ]
    blob = json.dumps(rows, ensure_ascii=False, default=str, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def read_info(path: Path) -> dict[str, str]:
    """The key/value rows of a bank file's "Bank Info" sheet ({} when there is none)."""
    try:
        wb = load_workbook(path, read_only=True, data_only=True)
    except Exception:
        return {}
    if INFO_SHEET not in wb.sheetnames:
        return {}
    info = {}
    for row in wb[INFO_SHEET].iter_rows(values_only=True):
        if row and row[0] and len(row) > 1 and row[1] is not None:
            info[str(row[0]).strip()] = str(row[1]).strip()
    return info


def make_version(source: str, built_at: str, digest: str) -> str:
    return f"{Path(source).stem}@{built_at[:10] or 'unversioned'}#{digest[:8]}"


def bank_version(path: Path, questions: dict[str, Question]) -> BankVersion:
    """The version of the bank at `path`, whose questions have been loaded."""
    digest = content_hash(questions)
    info = read_info(path)
    source = info.get("Source file") or Path(path).name
    built = info.get("Built at", "")
    return BankVersion(
        version=make_version(source, built, digest),
        content_hash=digest,
        source_file=info.get("Source file", ""),
        source_sha256=info.get("Source SHA-256", ""),
        built_at=built,
        questions=len(questions),
    )


def settings_version(settings) -> BankVersion | None:
    """The version of the category's current bank, or None when the bank can't be read."""
    from asics_agent.categories import load_bank

    questions, _ = load_bank(settings)
    return bank_version(settings.question_bank, questions) if questions else None


def embedded_version(workbook: Path) -> BankVersion | None:
    """The version of the bank an older answers workbook carries on its "Question Bank" sheet.

    Files made before versions existed record nothing; this fingerprints their own copy of the
    bank. None when the workbook has no such sheet."""
    from asics_agent.question_bank import load_question_bank

    try:
        wb = load_workbook(workbook, read_only=True)
        has = "Question Bank" in wb.sheetnames
        wb.close()
        if not has:
            return None
        questions, _ = load_question_bank(workbook, "Question Bank")
    except Exception:
        return None
    if not questions:
        return None
    digest = content_hash(questions)
    return BankVersion(
        version=f"{Path(workbook).stem}#{digest[:8]}",
        content_hash=digest,
        questions=len(questions),
    )


def write_sidecar(workbook: Path, version: BankVersion | None) -> None:
    """Record next to a scoring workbook which bank it was made with."""
    if version is None:
        return
    path = workbook.with_name(workbook.stem + SIDECAR_SUFFIX)
    path.write_text(json.dumps(version.as_dict(), indent=2))


def read_sidecar(workbook: Path) -> dict | None:
    path = workbook.with_name(workbook.stem + SIDECAR_SUFFIX)
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def version_note(recorded: dict | str | None, current: BankVersion | None) -> str | None:
    """A plain-language note when a file was made with a different bank than today's, else None.

    `recorded` is what the file says (a version or the dict from run_summary.json/the sidecar),
    or None when it says nothing (every file made before versions existed)."""
    if current is None:
        return None
    version = recorded.get("version") if isinstance(recorded, dict) else recorded
    digest = recorded.get("content_hash") if isinstance(recorded, dict) else None
    if not version:
        return (
            "This file doesn't say which question bank it was made with, so it may come from "
            f"an older one. The question bank now in use is {current.version}. Questions whose "
            "text changed may now mean something different."
        )
    if (digest and digest != current.content_hash) or (not digest and version != current.version):
        return (
            f"This file was made with question bank {version}, but the bank now in use is "
            f"{current.version}. Its results are kept as they are; questions that changed since "
            "then may now mean something different."
        )
    return None
