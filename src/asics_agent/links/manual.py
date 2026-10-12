"""Pages the research team saved by hand, for links that block automated tools.

Many government websites refuse the automated link check, so their rows say "Human
Verification Required". A team member opens the page in a browser and saves it as

    <city folder>/evidence/manual/<Citation ID>.pdf   (or .html, .htm, .txt)

When the Sources workbook is read, each such file is read with the same text extraction and
the same content checks as the link checker. A copy that passes makes the row Verified, so
Step 2 can use it; one that doesn't is reported to the team and the row is left as it was.
"""

from datetime import datetime
from pathlib import Path

from asics_agent.links.accessibility import content_problem
from asics_agent.links.text import html_to_text, pdf_to_text
from asics_agent.models import AccessCheck, Issue, Source

MANUAL_DIR = "manual"  # inside the city's evidence folder
TEXT_DIR = "manual_text"  # the extracted text of each saved copy
EXTENSIONS = (".pdf", ".html", ".htm", ".txt")
TEAM_NOTE = "Verified by the research team from a saved copy"


def _warning(message: str, ref: str | None = None) -> Issue:
    return Issue(
        phase="initial_checks", severity="warning", message=message, ref=ref, audience="team"
    )


def saved_copy(cache_dir: Path, citation_id: str) -> Path | None:
    """The file the team saved for a Citation ID (the newest one), if any."""
    folder = cache_dir / MANUAL_DIR
    if not citation_id or not folder.is_dir():
        return None
    found = [
        p
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in EXTENSIONS and p.stem.lower() == citation_id.lower()
    ]
    return max(found, key=lambda p: p.stat().st_mtime, default=None)


def _extract(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        return pdf_to_text(path.read_bytes())
    text = path.read_text(encoding="utf-8", errors="replace")
    return text if path.suffix.lower() == ".txt" else html_to_text(text)


def _problem_message(citation_id: str, path: Path, problem: str, detail: str, words: int) -> str:
    if problem == "blocked":
        return (
            f"{citation_id}: the saved copy ({path.name}) looks like a login, error or blocked "
            f"page ({detail!r}). Open the document itself and save that."
        )
    if problem == "metadata":
        return (
            f"{citation_id}: the saved copy ({path.name}) is an India Code page that shows only "
            "the Act's details, not its text. Save the page that shows the full text of the Act."
        )
    return (
        f"{citation_id}: the saved copy ({path.name}) has almost no readable text ({words} "
        "words) - is it a scanned PDF? Save a version with selectable text, or a .txt copy."
    )


def apply_saved_copies(sources: list[Source], cache_dir: Path) -> tuple[list[Source], list[Issue]]:
    """Verify every row that has a saved copy; return the rows and warnings for the team.

    Rows keep their "Use for Answers?" decision. A copy that fails the content checks leaves
    its row unchanged. A newer automated copy of the page (its text is `content_path`) is
    preferred over an older saved copy.
    """
    folder = cache_dir / MANUAL_DIR
    if not folder.is_dir():
        return sources, []
    issues: list[Issue] = []
    by_id: dict[str, list[Path]] = {}
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.name.startswith((".", "~")):
            continue
        if path.suffix.lower() in EXTENSIONS:
            by_id.setdefault(path.stem.lower(), []).append(path)
        else:
            issues.append(
                _warning(
                    f"evidence/{MANUAL_DIR}/{path.name} was ignored: save the page as "
                    f"{', '.join(EXTENSIONS)}."
                )
            )
    known = {s.citation_id.lower() for s in sources if s.citation_id}
    for stem, paths in by_id.items():
        if stem not in known:
            issues.append(
                _warning(
                    f"evidence/{MANUAL_DIR}/{paths[0].name} matches no Citation ID in the "
                    "Citation Sheet, so it was not used. Check the file name."
                )
            )

    result = []
    for source in sources:
        paths = by_id.get(source.citation_id.lower(), []) if source.citation_id else []
        if paths:
            source, found = _apply_one(source, paths, cache_dir)
            issues += found
        result.append(source)
    return result, issues


def _apply_one(source: Source, paths: list[Path], cache_dir: Path) -> tuple[Source, list[Issue]]:
    path = max(paths, key=lambda p: p.stat().st_mtime)
    issues = []
    if len(paths) > 1:
        issues.append(
            _warning(
                f"{source.citation_id} has {len(paths)} saved copies; the newest "
                f"({path.name}) was used. Delete the others.",
                source.citation_id,
            )
        )
    saved = path.stat().st_mtime
    saved_at = datetime.fromtimestamp(saved).isoformat(timespec="seconds")
    if (
        source.verification_status == "Not verified"
        and TEAM_NOTE in source.notes
        and source.checked_at == saved_at
    ):  # Step 1 read this very copy and found it doesn't support what the source is for
        message = (
            f"{source.citation_id}: the saved copy ({path.name}) was read, but it doesn't "
            "seem to support what this source is for (see Notes). Replace the copy if it is "
            "the wrong page."
        )
        return source, issues + [_warning(message, source.citation_id)]
    if source.content_path and Path(source.content_path).stat().st_mtime > saved:
        return source, issues  # the automatic check has since opened the page: its copy is fresher
    try:
        text = _extract(path)
    except Exception as exc:  # a damaged file should not stop the run
        message = f"{source.citation_id}: the saved copy ({path.name}) couldn't be read "
        return source, issues + [_warning(f"{message}({type(exc).__name__}).", source.citation_id)]
    problem, detail = content_problem(source.url, text)
    if problem:
        message = _problem_message(source.citation_id, path, problem, detail, len(text.split()))
        return source, issues + [_warning(message, source.citation_id)]

    text_path = cache_dir / TEXT_DIR / f"{source.citation_id}.txt"
    if not text_path.exists() or text_path.stat().st_mtime < saved:
        text_path.parent.mkdir(parents=True, exist_ok=True)
        text_path.write_text(f"SOURCE URL: {source.url}\n\n{text}", encoding="utf-8")
    note = f"{TEAM_NOTE} (evidence/{MANUAL_DIR}/{path.name})."
    return source.model_copy(
        update={
            "verification_status": "Verified",
            "accessibility": "Public",
            "snapshot_path": str(path),
            "content_path": str(text_path),
            "team_saved_copy": True,
            "checked_at": saved_at,
            "notes": source.notes
            if TEAM_NOTE in source.notes
            else f"{source.notes} {note}".strip(),
        }
    ), issues


def team_check(source: Source) -> AccessCheck | None:
    """The saved copy of a row as a link-check result, or None if the row has none."""
    if not source.team_saved_copy:
        return None
    where = f"evidence/{MANUAL_DIR}/{Path(source.snapshot_path or '').name}"
    return AccessCheck(
        url=source.url,
        accessibility="Public",
        verification_status="Verified",
        reasons=[f"{TEAM_NOTE} ({where})."],
        content_path=source.content_path,
        snapshot_path=source.snapshot_path,
        checked_at=source.checked_at,
    )
