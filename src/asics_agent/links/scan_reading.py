"""Stage 5 of the fetch chain: Claude reads a PDF that has no text layer (a scan), or whose pages had to
be rendered to images because the file is damaged.

What happens, in order (the numbers are settings; see config.py):

  1. `stage_five` (called by fetch_chain.check_url_staged, no money spent): keep the PDF in the shared
     cache; for a damaged file, try the free repair (PDFium rewrites it; if its text is then readable the
     copy is marked "repaired"); if a finished reading of the document is already cached, use it; else
     put the document in this run's QUEUE and leave the row "Human Verification Required".
  2. `process_queue` (called once at the end of Step 1, agents/scan_step.py): the queued documents are read
     in order of value, within `scan_reading_budget_usd`. A document that does not fit is skipped whole.
  3. Reading: chunks of at most 15 pages. 1 to 3 chunks go live; 4 or more go as ONE message batch (half
     price). If the batch is not finished after `scan_batch_wait_minutes` its id is saved in the cache,
     the row says "scan reading in progress" and the next Step 1 or re-check collects it.
  4. Every page of every chunk must come back with its "[page N]" marker, otherwise the document is a
     "partial scan" (it cannot support a zero, a required source or a complete crawl). The transcription
     is also checked for dropped text (section numbers that skip or repeat): "check transcription".

A document is read once, ever: chunks are cached under `<outputs>/_cache/scans/<sha1 of the PDF>/`, so a
second city, a second run, or the same document at another address costs nothing. Plain code except the
`Reader` (the Anthropic client), which tests replace.
"""

import hashlib
import json
import re
import threading
import time
from base64 import standard_b64encode
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from asics_agent.links import marks
from asics_agent.links.pdf_tools import (
    CHUNK_PAGES,
    REQUEST_LIMIT_BYTES,
    Pdf,
    chunk_ranges,
    page_count,
    read_pages,
    repair,
)
from asics_agent.models import AccessCheck
from asics_agent.usage import BATCH_SUFFIX, METER, UsageMeter

AGENT = "scan reading"  # the label the Costs page shows
PER_PAGE_USD = (
    0.013  # live, per page [measured $0.0087 to $0.0129 in the spikes, so this is the ceiling]
)
BATCH_FACTOR = 0.5
BATCH_MIN_CHUNKS = 4  # a document of this many chunks or more goes as one batch
# A page can cost more than PER_PAGE_USD: the one real test (a Kannada memo) cost $0.030 a page, 2.3 times
# the English-script figure (and a dense page could cost more). The budget therefore holds back this many
# times the estimate while a document
# is read, unless it cannot, in which case the first chunk is read first to measure the real price.
SURPRISE = 3.0
NOT_READ = "(page not read)"

PROMPT = (
    "Transcribe the text of these scanned pages exactly as printed, in reading order, keeping section "
    "numbers, sub-section letters, provisos, schedules and every amount or date. Do not summarise, "
    "translate, correct or add anything. Start each page with the line '[page N]' using the page numbers "
    "given below. If a page is blank, write '[page N] (blank)'."
)


# -- what the Anthropic client does (replaced in tests) ----------------------------------------------
@dataclass
class Read:
    text: str
    usage: dict  # a LangChain-style usage dict (see UsageMeter.record)
    model: str
    batch: bool = False


@dataclass
class BatchState:
    done: bool
    results: dict = field(default_factory=dict)  # custom_id -> Read, or None for a failed request


class Reader(Protocol):
    model: str

    def live(self, blocks: list[dict]) -> Read: ...

    def submit(self, items: list[tuple[str, list[dict]]]) -> str: ...

    def poll(self, batch_id: str) -> BatchState: ...


def _usage(u) -> dict:
    read = int(getattr(u, "cache_read_input_tokens", 0) or 0)
    write = int(getattr(u, "cache_creation_input_tokens", 0) or 0)
    plain = int(getattr(u, "input_tokens", 0) or 0)
    return {
        "input_tokens": plain + read + write,
        "output_tokens": int(getattr(u, "output_tokens", 0) or 0),
        "input_token_details": {"cache_read": read, "cache_creation": write},
    }


def _text(message) -> str:
    return "".join(b.text for b in message.content if getattr(b, "type", "") == "text")


class AnthropicReader:
    """The real reader: Claude PDF/image reading through the Anthropic SDK."""

    def __init__(self, client, model: str):
        self.client, self.model = client, model

    def _params(self, blocks: list[dict]) -> dict:
        return {
            "model": self.model,
            "max_tokens": 16000,
            "messages": [{"role": "user", "content": blocks}],
            "output_config": {"effort": "low"},
        }

    def live(self, blocks: list[dict]) -> Read:
        message = self.client.messages.create(**self._params(blocks))
        return Read(_text(message), _usage(message.usage), self.model)

    def submit(self, items: list[tuple[str, list[dict]]]) -> str:
        batch = self.client.messages.batches.create(
            requests=[{"custom_id": cid, "params": self._params(blocks)} for cid, blocks in items]
        )
        return batch.id

    def poll(self, batch_id: str) -> BatchState:
        batch = self.client.messages.batches.retrieve(batch_id)
        if batch.processing_status != "ended":
            return BatchState(False)
        results = {}
        for entry in self.client.messages.batches.results(batch_id):
            ok = entry.result.type == "succeeded" and entry.result.message.stop_reason != "refusal"
            results[entry.custom_id] = (
                Read(
                    _text(entry.result.message),
                    _usage(entry.result.message.usage),
                    self.model,
                    True,
                )
                if ok
                else None
            )
        return BatchState(True, results)


def reader_for(services) -> Reader | None:
    """The reader for a run's services: a test's `scan_reader`, else the Anthropic client of the live
    model. None for practice and test models (no scan reading there)."""
    if getattr(services, "scan_reader", None) is not None:
        return services.scan_reader
    client = getattr(getattr(services, "llm", None), "_client", None)
    if client is None:
        return None
    return AnthropicReader(client, services.settings.model)


def cost_of(read: Read) -> float:
    key = read.model + (BATCH_SUFFIX if read.batch else "")
    meter = UsageMeter()
    meter.record(key, AGENT, read.usage)
    row = meter.by_model.get(key)
    return float((row.cost(key) if row else 0) or 0)


def record(read: Read) -> float:
    """Count the call on the run's usage meter (the Costs page shows it as "scan reading")."""
    key = read.model + (BATCH_SUFFIX if read.batch else "")
    METER.record(key, AGENT, read.usage)
    return cost_of(read)


# -- the budget of a run -------------------------------------------------------------------------------
class ScanBudget:
    def __init__(self):
        self._lock = threading.Lock()
        self.limit = 0.0
        self.spent = 0.0

    def begin(self) -> None:
        """A new run: nothing is spent yet (the limit is set when the queue is processed)."""
        with self._lock:
            self.spent = 0.0

    def reserve(self, usd: float) -> bool:
        with self._lock:
            if self.spent + usd > self.limit + 1e-9:
                return False
            self.spent += usd
            return True

    def settle(self, reserved: float, actual: float) -> None:
        with self._lock:
            self.spent += actual - reserved

    @property
    def remaining(self) -> float:
        with self._lock:
            return max(self.limit - self.spent, 0.0)


BUDGET = ScanBudget()


class Hold:
    """What one document has reserved from the budget: it can grow while the document is read, and is
    settled to what was really spent."""

    def __init__(self, budget: ScanBudget):
        self.budget, self.amount = budget, 0.0

    def grow_to(self, usd: float) -> bool:
        if usd <= self.amount:
            return True
        if self.budget.reserve(usd - self.amount):
            self.amount = usd
            return True
        return False

    def settle(self, actual: float) -> None:
        self.budget.settle(self.amount, actual)
        self.amount = actual


# -- the documents of this run -------------------------------------------------------------------------
@dataclass
class ScanJob:
    url: str
    sha: str
    pages: int
    kind: str  # "pdf": Claude reads the PDF; "images": the pages are rendered and read as pictures
    path: Path | None = None  # the PDF in the shared cache
    data: bytes | None = None  # or in memory (no shared cache)
    cache_dir: Path | None = None  # the city's evidence folder the copy goes to

    def pdf_bytes(self) -> bytes:
        return self.data if self.data is not None else self.path.read_bytes()

    @property
    def estimate(self) -> float:
        return self.pages * PER_PAGE_USD


QUEUE: dict[str, ScanJob] = {}  # url -> the documents waiting to be read (this run)
RESULTS: dict[
    str, AccessCheck
] = {}  # url -> the copy a reading produced this run (partial ones too)
_guard = threading.Lock()


def reset_run() -> None:
    with _guard:
        QUEUE.clear()
        RESULTS.clear()
    BUDGET.begin()


def _key(url: str) -> str:
    from asics_agent.links.fetch_chain import norm_key

    return norm_key(url)


# -- the cache of one document ------------------------------------------------------------------------
class ScanStore:
    """`<root>/scans/<sha>/`: chunk_<a>-<b>.txt (a chunk whose every page came back), chunk_<a>-<b>.part
    (what a chunk returned when pages were missing: kept for the partial copy, never counted as read),
    meta.json (pages, cost, the saved batch)."""

    def __init__(self, root: Path | None):
        self.root = root

    def _dir(self, sha: str) -> Path | None:
        return (self.root / "scans" / sha) if self.root else None

    def meta(self, sha: str) -> dict:
        d = self._dir(sha)
        try:
            return (
                json.loads((d / "meta.json").read_text())
                if d and (d / "meta.json").exists()
                else {}
            )
        except (OSError, ValueError):
            return {}

    def save_meta(self, sha: str, meta: dict) -> None:
        if d := self._dir(sha):
            d.mkdir(parents=True, exist_ok=True)
            (d / "meta.json").write_text(json.dumps(meta, indent=1))

    def chunk(
        self, sha: str, first: int, last: int, partial: bool = False
    ) -> dict[int, str] | None:
        d = self._dir(sha)
        path = d / f"chunk_{first}-{last}.{'part' if partial else 'txt'}" if d else None
        if not path or not path.exists():
            return None
        return read_pages(path.read_text(encoding="utf-8"))

    def save_chunk(
        self, sha: str, first: int, last: int, pages: dict[int, str], complete: bool
    ) -> None:
        if d := self._dir(sha):
            d.mkdir(parents=True, exist_ok=True)
            text = "\n\n".join(f"[page {n}]\n{pages[n]}" for n in sorted(pages))
            (d / f"chunk_{first}-{last}.{'txt' if complete else 'part'}").write_text(
                text, encoding="utf-8"
            )
            if complete and (part := d / f"chunk_{first}-{last}.part").exists():
                part.unlink()


# -- reading --------------------------------------------------------------------------------------------
def parse_chunk(text: str, first: int, last: int) -> tuple[dict[int, str], list[int]]:
    """({page: text} for the pages of first..last that came back, the pages that did not). Accepts a
    chunk numbered from 1 when it has exactly its own page count."""
    pages = read_pages(text)
    wanted = set(range(first, last + 1))
    if first != 1 and set(pages) == set(range(1, last - first + 2)):
        pages = {n + first - 1: body for n, body in pages.items()}
    got = {n: body for n, body in pages.items() if n in wanted}
    return got, sorted(wanted - set(got))


def _blocks(pdf: Pdf, kind: str, first: int, last: int) -> list[dict]:
    note = {
        "type": "text",
        "text": f"{PROMPT}\nThe first page below is page {first}; the last is page {last}.",
    }
    if kind == "pdf":
        data = pdf.split(first, last)
        if len(data) <= REQUEST_LIMIT_BYTES:
            return [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": standard_b64encode(data).decode(),
                    },
                },
                note,
            ]
    blocks = []
    for n, png in zip(range(first, last + 1), pdf.render(first, last), strict=True):
        blocks.append({"type": "text", "text": f"Page {n}:"})
        blocks.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": standard_b64encode(png).decode(),
                },
            }
        )
    return [*blocks, note]


@dataclass
class DocResult:
    status: str  # read | partial | over_budget | pending | no_reader | failed
    job: ScanJob
    text: str = ""
    missing: list[int] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)  # from check_transcription
    cost: float = 0.0  # spent on this document in this run
    estimate: float = 0.0
    batch_id: str = ""
    mode: str = ""  # live | batch
    detail: str = ""
    stopped: str = ""  # why a reading stopped part-way (the price turned out higher than expected)

    @property
    def copy_type(self) -> str:
        base = marks.PAGE_IMAGES if self.job.kind == "images" else marks.SCAN
        return marks.join(
            base,
            marks.PARTIAL_SCAN if self.missing else "",
            marks.CHECK_TRANSCRIPTION if self.problems else "",
        )


def assemble(job: ScanJob, store: ScanStore) -> tuple[dict[int, str], list[int], bool]:
    """(pages read, pages missing, every chunk complete) from what the store holds."""
    pages: dict[int, str] = {}
    complete = True
    for first, last in chunk_ranges(job.pages):
        full = store.chunk(job.sha, first, last)
        if full is not None and set(range(first, last + 1)) <= set(full):
            pages.update(full)
            continue
        complete = False
        pages.update(store.chunk(job.sha, first, last, partial=True) or {})
    return pages, [n for n in range(1, job.pages + 1) if n not in pages], complete


def render_text(pages: dict[int, str], total: int) -> str:
    return "\n\n".join(f"[page {n}]\n{pages.get(n, NOT_READ)}" for n in range(1, total + 1))


# -- the transcription check ----------------------------------------------------------------------------
_SECTION = re.compile(r"^\s*(\d{1,3})([A-Z]{0,2})\s*[.—-]\s+(?=[A-Z\[“\"(])")
_SCHEDULE = re.compile(r"^\s*(?:THE\s+)?(?:\w+\s+)?SCHEDULES?\b", re.I)
MIN_RUN = 8  # a run of numbered sections must be this long before a gap in it means anything


def check_transcription(pages: dict[int, str]) -> list[str]:
    """Signs that a transcribed Act dropped text: section numbers that skip ahead or repeat. A heading with
    a letter ("12A") is an inserted section and is ignored; everything after a Schedule heading is ignored;
    a table of contents followed by the body (the numbering starts again at 1) is two runs. Needs at least
    MIN_RUN numbered sections in a run, so ordinary documents are never flagged. Pages that did not come
    back are reported by the partial-scan mark, not here."""
    runs: list[list[tuple[int, int]]] = [[]]
    for n in sorted(pages):
        for line in pages[n].splitlines():
            if _SCHEDULE.match(line) and len(line.split()) <= 6:
                return _problems(runs, pages)
            m = _SECTION.match(line)
            if not m or m.group(2):
                continue
            number = int(m.group(1))
            run = runs[-1]
            if run and number == 1 and run[-1][0] > 1:
                runs.append([])
                run = runs[-1]
            run.append((number, n))
    return _problems(runs, pages)


def _problems(runs, pages) -> list[str]:
    out = []
    for run in runs:
        if len(run) < MIN_RUN:
            continue
        for (a, pa), (b, pb) in zip(run, run[1:], strict=False):
            if b == a:
                out.append(f"section {a} appears twice (page {pa} and page {pb})")
            elif b > a + 1 and all(p in pages for p in range(pa + 1, pb)):
                # (a jump across a page that did not come back is that page's "partial scan", not this)
                out.append(f"section numbers jump from {a} (page {pa}) to {b} (page {pb})")
    return out[:6]


# -- one document -------------------------------------------------------------------------------------
def _collect(job: ScanJob, store: ScanStore, reader: Reader | None, meta: dict) -> str:
    """Collect a batch saved by an earlier run: "done" (chunks saved), "waiting", or "none"."""
    batch = meta.get("batch")
    if not batch:
        return "none"
    if reader is None:
        return "waiting"
    state = reader.poll(batch["id"])
    if not state.done:
        return "waiting"
    cost = float(meta.get("cost") or 0)
    for first, last in chunk_ranges(job.pages):
        read = state.results.get(f"p{first}-{last}")
        if read is None:
            continue
        cost += record(read)
        got, missing = parse_chunk(read.text, first, last)
        store.save_chunk(job.sha, first, last, got, complete=not missing)
    meta.pop("batch", None)
    meta["cost"] = round(cost, 4)
    store.save_meta(job.sha, meta)
    return "done"


def read_document(
    job: ScanJob,
    *,
    reader: Reader | None,
    store: ScanStore,
    budget: ScanBudget,
    wait_minutes: float = 20.0,
    poll_seconds: float = 30.0,
    sleep=time.sleep,
    clock=time.monotonic,
) -> DocResult:
    """Read what of the document is not already cached, within the budget; the result says how far it got."""
    meta = store.meta(job.sha) or {"pages": job.pages, "kind": job.kind, "cost": 0.0}
    meta.update(pages=job.pages, kind=job.kind)
    outcome = _collect(job, store, reader, meta)
    pages, missing, complete = assemble(job, store)
    result = DocResult("read", job, cost=0.0)
    if outcome == "waiting":
        result.status, result.batch_id = "pending", meta["batch"]["id"]
        result.detail = f"batch {result.batch_id} sent {meta['batch'].get('sent', '?')}"
        return result
    todo = [
        (a, b)
        for a, b in chunk_ranges(job.pages)
        if set(range(a, b + 1)) - set(store.chunk(job.sha, a, b) or {})
    ]
    spent = 0.0
    if todo:
        batch = len(todo) >= BATCH_MIN_CHUNKS
        factor = BATCH_FACTOR if batch else 1.0
        result.mode = "batch" if batch else "live"
        todo_pages = sum(b - a + 1 for a, b in todo)
        result.estimate = todo_pages * PER_PAGE_USD * factor
        if reader is None:
            result.status = "no_reader"
            return result
        hold = Hold(budget)
        if not hold.grow_to(result.estimate):  # must fit at the expected (English-script) price
            result.status = "over_budget"
            return result
        # A page can cost more than the estimate (a Kannada page cost 2.3x in the one real test), so the
        # estimate is only trusted when the budget also covers SURPRISE times it. If it does not, the
        # first chunk is read live to measure what this document really costs, and the rest is decided
        # on that.
        probe = not hold.grow_to(result.estimate * SURPRISE)
        pdf = Pdf(job.pdf_bytes())
        live = todo if not batch else (todo[:1] if probe else [])
        pages_read = 0
        try:
            for a, b in live:
                read = reader.live(_blocks(pdf, job.kind, a, b))
                spent += record(read)
                pages_read += b - a + 1
                got, miss = parse_chunk(read.text, a, b)
                store.save_chunk(job.sha, a, b, got, complete=not miss)
                left = todo_pages - pages_read
                if left:  # what the rest will cost at the price just measured must still fit
                    projected = spent / pages_read * left * (BATCH_FACTOR if batch else 1.0)
                    if not hold.grow_to(spent + projected * 1.2):
                        rate = spent / pages_read
                        result.stopped = (
                            f"stopped after page {b}: this document costs about ${rate:,.3f} a page, "
                            f"more than the ${PER_PAGE_USD:,.3f} expected, and the rest "
                            f"(${projected:,.2f}) does not fit the scan budget"
                        )
                        break
            rest = todo[len(live) :] if batch else []
            before = float(meta.get("cost") or 0) + spent
            if rest and not result.stopped:
                items = [(f"p{a}-{b}", _blocks(pdf, job.kind, a, b)) for a, b in rest]
                batch_id = reader.submit(items)
                meta["batch"] = {"id": batch_id, "sent": time.strftime("%Y-%m-%d %H:%M")}
                meta["cost"] = round(before, 4)
                store.save_meta(job.sha, meta)
                result.batch_id = batch_id
                deadline = clock() + wait_minutes * 60
                while True:
                    outcome = _collect(job, store, reader, meta)
                    if outcome == "done":
                        break
                    if clock() >= deadline:
                        result.status = "pending"
                        result.detail = f"batch {batch_id} sent {meta['batch']['sent']}"
                        return result  # budget stays reserved: the batch will be paid for
                    sleep(poll_seconds)
                spent += float(meta.get("cost") or 0) - before
            else:
                meta["cost"] = round(before, 4)
                store.save_meta(job.sha, meta)
        except (
            Exception
        ) as exc:  # the API failed: nothing more is spent, the chunks done so far are kept
            hold.settle(spent)
            result.status, result.cost = "failed", spent
            result.detail = f"{type(exc).__name__}: {str(exc)[:120]}"
            return result
        hold.settle(spent)
        result.cost = spent
        pages, missing, complete = assemble(job, store)
    result.missing = missing
    result.status = "read" if complete else "partial"
    result.text = render_text(pages, job.pages)
    result.problems = check_transcription(pages)
    return result


# -- stage 5, inside the fetch chain ------------------------------------------------------------------
def finish_check(
    check: AccessCheck, result: DocResult, url: str, cache_dir: Path, pdf: bytes, shared
) -> AccessCheck:
    """The AccessCheck for a finished reading: the text goes through the usual content checks and is saved
    under the URL's evidence name; a complete reading is also stored in the shared cache, for good."""
    from asics_agent.links.accessibility import accept_text

    check.pdf_bytes = None
    check.failure = ""
    # The text is Claude's transcription, so a page with little on it (a map, a blank) is not "a scan" again.
    accept_text(check, url, result.text, cache_dir, body=pdf, snapshot_ext=".pdf", check_scan=False)
    if check.verification_status != "Verified":
        return check
    check.copy_type = result.copy_type
    check.reasons.append(
        f"Scan reading: Claude read this {result.job.pages}-page document "
        f"({'rendered page images' if result.job.kind == 'images' else 'PDF reading'})."
        + (f" Pages not read: {', '.join(map(str, result.missing))}." if result.missing else "")
        + (f" Transcription check: {'; '.join(result.problems)}." if result.problems else "")
    )
    check.reasons.append(f"Copy type: {check.copy_type}.")
    check.stages = [*check.stages, f"scan reading: {result.job.pages} pages"]
    if not result.missing and shared is not None:
        shared.store(
            url,
            check,
            never_expires=True,
            extra={
                "pages": result.job.pages,
                "reasons": check.reasons[-2:],
                "scan_cost": result.cost,
            },
        )
    return check


def stage_five(
    check: AccessCheck, url: str, cache_dir: Path, settings, shared
) -> AccessCheck | None:
    """Stage 5 for a PDF that failed as "scan" or "unreadable". Spends nothing. Returns the check to
    give back to the caller, or None to leave the result as it was (scan reading off, or no PDF)."""
    data = check.pdf_bytes
    if not data:
        return None
    from asics_agent.links.accessibility import MIN_WORDS, scanned_pdf
    from asics_agent.links.text import pdf_to_text

    shared.save_original(url, data)
    kind = "pdf"
    if check.failure == "unreadable":
        fixed = repair(data)
        if fixed is None:
            check.reasons.append(
                "The PDF is damaged and could not be opened even after a repair attempt; a person must "
                "save a readable copy."
            )
            check.stages = [*check.stages, "repair: the file cannot be opened"]
            return check
        try:
            text = pdf_to_text(fixed)
        except Exception:
            text = ""
        data, kind = fixed, "images"
        if scanned_pdf(text) is None and len(text.split()) >= MIN_WORDS:
            from asics_agent.links.accessibility import accept_text

            check.pdf_bytes = None
            check.failure = ""
            accept_text(check, url, text, cache_dir, body=fixed, snapshot_ext=".pdf")
            if check.verification_status == "Verified":
                check.copy_type = marks.REPAIRED
                check.reasons.append(
                    "The PDF was damaged; the app rewrote it and read its text. "
                    f"Copy type: {marks.REPAIRED}."
                )
                check.stages = [*check.stages, "repair: rewritten, text read"]
                shared.store(url, check)
                return check
    pages = page_count(data)
    if pages is None:
        return None
    if getattr(settings, "scan_reading_budget_usd", 0) <= 0:
        check.reasons.append(
            f"Scan reading is off (scan_reading_budget_usd is 0): this {pages}-page document was not read."
        )
        return check
    job = ScanJob(
        url=url,
        sha=hashlib.sha1(data).hexdigest(),
        pages=pages,
        kind=kind,
        path=shared.original(url) if kind == "pdf" else None,
        data=data if kind == "images" or shared.original(url) is None else None,
        cache_dir=cache_dir,
    )
    store = ScanStore(shared.root)
    done_pages, missing, complete = assemble(job, store)
    if complete:  # an earlier reading finished: no new work
        result = DocResult("read", job, text=render_text(done_pages, pages))
        result.problems = check_transcription(done_pages)
        out = finish_check(check, result, url, cache_dir, data, shared)
        out.stages = [
            *out.stages[:-1],
            f"scan reading: {pages} pages (read earlier, from the cache)",
        ]
        return out
    with _guard:
        QUEUE[_key(url)] = job
    check.reasons.append(
        f"Scan reading queued: {pages} pages, about ${job.estimate:,.2f} to read live "
        f"(half as a batch). A person can instead save a readable copy (see How to Use)."
    )
    check.stages = [*check.stages, f"scan reading: queued ({pages} pages)"]
    return check


def take_result(url: str, cache_dir: Path) -> AccessCheck | None:
    """The copy a reading produced earlier in this run for `url` (a partial one too), copied to
    this check's evidence folder; None if there is none."""
    with _guard:
        hit = RESULTS.get(_key(url))
    if hit is None or not hit.content_path or not Path(hit.content_path).exists():
        return None
    out = hit.model_copy(deep=True)
    if Path(hit.content_path).parent != cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
        for src in (hit.content_path, hit.snapshot_path):
            if src and Path(src).exists():
                (cache_dir / Path(src).name).write_bytes(Path(src).read_bytes())
        out.content_path = str(cache_dir / Path(hit.content_path).name)
        out.snapshot_path = (
            str(cache_dir / Path(hit.snapshot_path).name) if hit.snapshot_path else None
        )
    return out


def put_result(url: str, check: AccessCheck) -> None:
    with _guard:
        RESULTS[_key(url)] = check


def queued() -> list[ScanJob]:
    with _guard:
        return list(QUEUE.values())


__all__ = [
    "AGENT",
    "BUDGET",
    "CHUNK_PAGES",
    "AnthropicReader",
    "DocResult",
    "QUEUE",
    "RESULTS",
    "Read",
    "Reader",
    "ScanBudget",
    "ScanJob",
    "ScanStore",
    "assemble",
    "check_transcription",
    "cost_of",
    "finish_check",
    "parse_chunk",
    "put_result",
    "queued",
    "read_document",
    "reader_for",
    "render_text",
    "reset_run",
    "stage_five",
    "take_result",
]
