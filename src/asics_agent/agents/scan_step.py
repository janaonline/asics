"""Step 1's scan-reading pass: at the end of the run, read the scanned PDFs the link check queued.

The link check (links/fetch_chain.py, stage 5) cannot order documents by value, because each agency's
links are checked in parallel; it only queues them. This pass runs once per run with every queued
document in view, reads them within `scan_reading_budget_usd` (legal texts [ACT] and [RULES] first, then the
documents the questions require, then the rest; smallest first inside each group), and re-checks
each source it could read, so the assessor, the cut-off check and the notes treat it like any other
verified page. All the money logic is in links/scan_reading.py.
"""

from functools import lru_cache

from asics_agent import source_requirements
from asics_agent.links import marks, scan_reading
from asics_agent.links.fetch_chain import _cache_root, norm_key
from asics_agent.links.shared_cache import SharedCache
from asics_agent.models import AccessCheck, Issue, Source

# [ACT] and [RULES] and the other laws the evidence tags name (the state Municipal Act, the T&CP Act, a
# constitution document, cross-cutting laws)
LEGAL_TAGS = frozenset({"ACT", "RULES", "TCP", "ULG-LAW", "CONSTITUTION", "CROSSLAW"})


@lru_cache(maxsize=1)
def required_tags() -> frozenset[str]:
    """Every evidence tag some question's required-source table asks for."""
    tags = set()
    for req in source_requirements.load().requirements.values():
        for group in req.groups:
            for tag in group:
                tags |= {"ACT", "CONSTITUTION"} if tag == "LEGAL_BASE" else {tag}
    return frozenset(tags)


def priority(source: Source) -> int:
    """Reading order: 0 a legal text ([ACT], [RULES]), 1 any other document a question requires, 2 the
    rest. Legal texts and required sources are read before everything else; within the first two the
    legal texts go first, because nearly every tagged document is "required" by some question and a
    plain smallest-first order would drop an Act in favour of an annual report."""
    tags = source_requirements.tags_of(source)
    if tags & LEGAL_TAGS:
        return 0
    return 1 if tags & required_tags() else 2


def _label(source: Source) -> str:
    return f"{source.citation_id or source.title[:40]} ({source.title[:60]})"


def collect_scans(
    services, run, sources: list[Source], parastatal_for
) -> tuple[list[Source], list[Issue]]:
    """Read the queued documents; return the sources with the read ones re-checked, and the Needs
    Attention lines (over budget, in progress, failed, and what was spent). `parastatal_for(id)` gives the
    Parastatal of a row."""
    from asics_agent.agents.common import CandidateSource, vet_source
    from asics_agent.agents.links_builder import use_after_retest

    settings = services.settings
    jobs = {norm_key(j.url): j for j in scan_reading.queued()}
    if not jobs:
        return sources, []
    limit = float(getattr(settings, "scan_reading_budget_usd", 0))
    scan_reading.BUDGET.limit = limit
    reader = scan_reading.reader_for(services)
    shared = SharedCache(
        _cache_root(settings), int(getattr(settings, "fetch_cache_max_age_days", 30))
    )
    store = scan_reading.ScanStore(shared.root)

    rows: dict[str, list[Source]] = {}
    for s in sources:
        if norm_key(s.url) in jobs and s.verification_status != "Verified":
            rows.setdefault(norm_key(s.url), []).append(s)
    order = sorted(rows, key=lambda k: (min(priority(s) for s in rows[k]), jobs[k].pages))

    issues: list[Issue] = []
    notes: dict[str, str] = {}
    pending_mark: set[str] = set()
    revet: set[str] = set()
    read_docs = read_pages = 0

    def line(severity, message, ref=None):
        issues.append(
            Issue(phase="links", severity=severity, ref=ref, audience="team", message=message)
        )

    for key in order:
        job, group = jobs[key], rows[key]
        who = ", ".join(_label(s) for s in group[:3])
        result = scan_reading.read_document(
            job,
            reader=reader,
            store=store,
            budget=scan_reading.BUDGET,
            wait_minutes=float(getattr(settings, "scan_batch_wait_minutes", 20)),
        )
        ref = group[0].parastatal_id
        name = parastatal_for(ref).name if parastatal_for(ref) else ref
        if result.status in ("read", "partial"):
            check = AccessCheck(url=job.url)
            check.failure, check.verification_status = "scan", "Human Verification Required"
            check = scan_reading.finish_check(
                check, result, job.url, job.cache_dir, job.pdf_bytes(), shared
            )
            if result.stopped:
                line("warning", f"{name}: scan reading {result.stopped} ({who}).", ref)
            if check.verification_status == "Verified":
                scan_reading.put_result(job.url, check)
                revet.add(key)
                read_docs += 1
                read_pages += job.pages
            else:
                notes[key] = (
                    f"Scan reading: Claude's transcription was not usable ({' '.join(check.reasons)})"
                )
                line("warning", f"{name}: scan reading gave no usable text for {who}.", ref)
        elif result.status == "over_budget":
            spent = scan_reading.BUDGET.spent
            notes[key] = (
                f"Scan reading: not read. {job.pages} pages, about ${result.estimate:,.2f} as a batch, "
                f"over this run's scan budget of ${limit:,.2f}."
            )
            line(
                "warning",
                f"{name}: scanned document not read: {who}: {job.pages} pages, about "
                f"${result.estimate:,.2f} to read (${job.estimate:,.2f} live); over this run's scan budget "
                f"of ${limit:,.2f} (${spent:,.2f} already used). Raise scan_reading_budget_usd in the "
                "category file, or save a readable copy by hand.",
                ref,
            )
        elif result.status == "pending":
            pending_mark.add(key)
            notes[key] = (
                f"Scan reading in progress ({result.detail}). The next Step 1 or re-check collects it."
            )
            line(
                "info",
                f"{name}: scan reading in progress for {who} ({job.pages} pages, {result.detail}). "
                "Run Step 1 or a re-check later to collect it; it is paid for already.",
                ref,
            )
        elif result.status == "no_reader":
            notes[key] = "Scan reading: not read (no Claude connection in this run)."
        else:
            notes[key] = f"Scan reading failed ({result.detail}); nothing more was spent on it."
            line("warning", f"{name}: scan reading failed for {who}: {result.detail}.", ref)
    if read_docs:
        line(
            "info",
            f"Scan reading: Claude read {read_docs} document(s), {read_pages} pages; "
            f"${scan_reading.BUDGET.spent:,.2f} of the ${limit:,.2f} scan budget used. Each is marked "
            '"read by Claude" and should be spot-checked against the PDF.',
        )

    out = []
    for s in sources:
        key = norm_key(s.url)
        if key in revet and s.verification_status != "Verified":
            p = parastatal_for(s.parastatal_id)
            new, vet_issues = vet_source(
                services,
                run,
                p,
                CandidateSource(
                    title=s.title,
                    url=s.url,
                    source_type=s.source_type,
                    useful_for=s.useful_for,
                    question_ids=s.question_ids,
                    human_verified=s.human_verified,
                ),
                provenance=s.provenance,
                allowed_urls=None,
                own_hosts=frozenset(),
            )
            issues += vet_issues
            if new is not None:
                use, why = use_after_retest(s, new)
                s = new.model_copy(
                    update={
                        "citation_id": s.citation_id,
                        "use_for_answers": use,
                        "team_notes": s.team_notes,
                        "found_by": s.found_by,
                        "provenance": s.provenance,
                        "human_verified": s.human_verified,
                        "notes": f"{why}{new.notes}".strip(),
                    }
                )
        elif key in notes:
            s = s.model_copy(
                update={
                    "notes": f"{s.notes} {notes[key]}".strip(),
                    **({"copy_type": marks.SCAN_PENDING} if key in pending_mark else {}),
                }
            )
        out.append(s)
    return out, issues


__all__ = ["collect_scans", "priority", "required_tags"]
