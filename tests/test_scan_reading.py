"""Scan reading (links/scan_reading.py, agents/scan_step.py): chunks, batches, the budget, partial scans,
the transcription check, damaged PDFs, and the Needs Attention lines. A scripted reader stands in for
Claude: no network, no model call."""

import dataclasses
import re
from pathlib import Path

import httpx
import pytest

from asics_agent.agents import common, scan_step
from asics_agent.agents.common import SourceAssessment
from asics_agent.agents.links_builder import fetch_issues
from asics_agent.config import get_settings
from asics_agent.links import fetch_chain, marks, scan_reading
from asics_agent.links.fetch_chain import ChainTools, check_url_staged
from asics_agent.links.pdf_tools import chunk_ranges
from asics_agent.links.scan_reading import (
    BatchState,
    Read,
    ScanBudget,
    ScanJob,
    ScanStore,
    check_transcription,
    parse_chunk,
    read_document,
)
from asics_agent.models import Parastatal, RunContext, Source
from asics_agent.usage import METER
from tests.pdfs import damaged, scan_pdf, text_pdf

UA = "test-agent ASICS-link-check/1.0"
USAGE = {"input_tokens": 1000, "output_tokens": 500, "input_token_details": {}}  # $0.007 live


@pytest.fixture(autouse=True)
def clean_state():
    from asics_agent.links import accessibility

    accessibility._robots_cache.clear()
    fetch_chain._slots.clear()
    fetch_chain.begin_run()
    METER.reset()
    yield
    fetch_chain.begin_run()


def section_text(page: int, skip: bool = False) -> str:
    return f"{page + 1 if skip else page}. Heading {page}\n" + " ".join(
        [f"The Board shall do thing {page}."] * 6
    )


class Reader:
    """Answers each chunk with "[page N]" text for every page it is asked about, minus `drop`."""

    model = "claude-sonnet-5-5"

    usage = USAGE

    def __init__(self, drop=(), fail_at=None, skip=(), ready_after=0):
        self.drop, self.fail_at, self.skip = set(drop), fail_at, set(skip)
        self.live_calls, self.submitted, self.polls = [], [], 0
        self.ready_after = ready_after
        self._batches = {}

    @staticmethod
    def span(blocks):
        text = blocks[-1]["text"]
        a, b = re.search(r"first page below is page (\d+); the last is page (\d+)", text).groups()
        return int(a), int(b)

    def answer(self, blocks, batch=False) -> Read:
        a, b = self.span(blocks)
        text = "\n\n".join(
            f"[page {n}]\n{section_text(n, n in self.skip)}"
            for n in range(a, b + 1)
            if n not in self.drop
        )
        return Read(text, self.usage, self.model, batch)

    def live(self, blocks):
        self.live_calls.append(self.span(blocks))
        if self.fail_at is not None and len(self.live_calls) == self.fail_at:
            raise RuntimeError("the API is down")
        return self.answer(blocks)

    def submit(self, items):
        self.submitted.append([cid for cid, _ in items])
        batch_id = f"batch_{len(self.submitted)}"
        self._batches[batch_id] = {cid: self.answer(blocks, True) for cid, blocks in items}
        return batch_id

    def poll(self, batch_id):
        self.polls += 1
        if self.polls <= self.ready_after:
            return BatchState(False)
        return BatchState(True, dict(self._batches[batch_id]))


def job_for(pages: int, kind="pdf", url="https://x.gov.in/act.pdf", data=None) -> ScanJob:
    data = data if data is not None else scan_pdf(pages)
    import hashlib

    return ScanJob(url=url, sha=hashlib.sha1(data).hexdigest(), pages=pages, kind=kind, data=data)


def read(job, reader, tmp_path, budget=None, **kwargs):
    budget = budget or ScanBudget()
    if budget.limit == 0:
        budget.limit = 100
    kwargs.setdefault("sleep", lambda s: None)
    return read_document(
        job, reader=reader, store=ScanStore(tmp_path / "_cache"), budget=budget, **kwargs
    )


# -- chunks and parsing ------------------------------------------------------------------------------------
@pytest.mark.parametrize("pages", [1, 14, 15, 16, 30, 31, 46, 420])
def test_no_chunk_is_ever_larger_than_15_pages_and_together_they_cover_every_page(pages):
    ranges = chunk_ranges(pages)
    assert all(b - a + 1 <= 15 for a, b in ranges)
    assert [n for a, b in ranges for n in range(a, b + 1)] == list(range(1, pages + 1))


def test_parse_chunk_reports_the_pages_that_did_not_come_back():
    got, missing = parse_chunk("[page 16]\nA\n\n[page 18]\nB (blank)\n", 16, 18)
    assert sorted(got) == [16, 18] and missing == [17]


def test_a_chunk_numbered_from_one_is_moved_to_its_own_page_numbers():
    got, missing = parse_chunk("[page 1]\nA\n\n[page 2]\nB\n\n[page 3]\nC", 31, 33)
    assert sorted(got) == [31, 32, 33] and missing == []


# -- the transcription check ----------------------------------------------------------------------------------
def pages_of(numbers):
    """One page per section number: page i holds section numbers[i]."""
    return {i + 1: f"{n}. Heading {n}\nText." for i, n in enumerate(numbers)}


def test_consecutive_section_numbers_pass():
    assert check_transcription(pages_of(range(1, 21))) == []


def test_a_gap_and_a_repeat_in_the_section_numbers_are_reported_with_their_pages():
    numbers = [*range(1, 8), 9, *range(10, 14), 13, *range(14, 20)]
    problems = check_transcription(pages_of(numbers))
    assert any("jump from 7" in p and "to 9" in p for p in problems)
    assert any("section 13 appears twice" in p for p in problems)


def test_inserted_sections_schedules_and_a_table_of_contents_are_not_flagged():
    body = [f"{n}. Heading {n}\nText." for n in range(1, 13)]
    body.insert(5, "5A. Inserted section\nText.")  # an amendment
    toc = [f"{n}. Heading {n}" for n in range(1, 13)]
    pages = {
        1: "\n".join(toc),
        2: "\n".join(body),
        3: "THE SCHEDULE\n40. Not a section\n44. Another",
    }
    assert check_transcription(pages) == []


def test_a_short_document_or_one_without_numbered_sections_is_never_flagged():
    assert check_transcription({1: "1. Title\n3. Odd", 2: "Budget table 5 7 9"}) == []


# -- reading a document ----------------------------------------------------------------------------------------
def test_up_to_three_chunks_are_read_live_and_every_page_comes_back(tmp_path):
    reader = Reader()
    result = read(job_for(40), reader, tmp_path)  # 15 + 15 + 10 pages
    assert result.status == "read" and result.mode == "live"
    assert reader.live_calls == [(1, 15), (16, 30), (31, 40)] and reader.submitted == []
    assert all(f"[page {n}]" in result.text for n in range(1, 41))
    assert result.missing == [] and result.problems == []
    assert result.copy_type == marks.SCAN


def test_the_cost_is_recorded_on_the_run_meter_as_scan_reading(tmp_path):
    result = read(job_for(40), Reader(), tmp_path)
    assert result.cost == pytest.approx(3 * 0.007)
    assert list(METER.by_agent) == ["scan reading · claude-sonnet-5-5"]
    assert METER.by_agent["scan reading · claude-sonnet-5-5"].calls == 3


def test_four_or_more_chunks_go_as_one_batch_at_half_price(tmp_path):
    reader = Reader()
    result = read(job_for(46), reader, tmp_path)  # 4 chunks
    assert result.mode == "batch" and result.status == "read"
    assert len(reader.submitted) == 1 and len(reader.submitted[0]) == 4
    assert reader.live_calls == []
    assert result.cost == pytest.approx(4 * 0.007 / 2)
    assert "scan reading · claude-sonnet-5-5 (batch)" in METER.by_agent


def test_a_document_is_never_read_twice_not_in_a_second_run_nor_at_another_address(tmp_path):
    first = Reader()
    read(job_for(40), first, tmp_path)
    again = Reader()
    result = read(job_for(40), again, tmp_path)
    assert result.status == "read" and again.live_calls == [] and result.cost == 0
    # the same file at another address has the same hash, so the same chunks
    elsewhere = Reader()
    other = job_for(40, url="https://other.gov.in/copy.pdf")
    assert read(other, elsewhere, tmp_path).status == "read" and elsewhere.live_calls == []


def test_an_interrupted_read_resumes_from_the_chunks_already_saved(tmp_path):
    broken = Reader(fail_at=2)
    result = read(job_for(40), broken, tmp_path)
    assert result.status == "failed" and "API is down" in result.detail
    assert broken.live_calls == [(1, 15), (16, 30)]
    resumed = Reader()
    done = read(job_for(40), resumed, tmp_path)
    assert done.status == "read" and resumed.live_calls == [(16, 30), (31, 40)]


# -- the budget --------------------------------------------------------------------------------------------------
def test_a_document_over_the_budget_is_skipped_whole_and_nothing_is_called(tmp_path):
    reader = Reader()
    budget = ScanBudget()
    budget.limit = 0.20  # 40 pages live would be $0.52
    result = read(job_for(40), reader, tmp_path, budget=budget)
    assert result.status == "over_budget" and result.estimate == pytest.approx(40 * 0.013)
    assert reader.live_calls == [] and reader.submitted == [] and budget.spent == 0
    assert result.text == ""


def test_the_budget_is_settled_to_what_was_really_spent(tmp_path):
    budget = ScanBudget()
    budget.limit = 5.0
    read(job_for(40), Reader(), tmp_path, budget=budget)
    assert budget.spent == pytest.approx(3 * 0.007)  # not the $0.52 reserved


def test_a_batch_that_is_not_finished_is_saved_and_collected_next_time_without_paying_twice(
    tmp_path,
):
    reader = Reader(ready_after=1000)  # never ready within the wait
    clock = iter(
        range(0, 100000, 400)
    )  # each look at the clock is 400 s later: past a 20-minute wait
    result = read(job_for(46), reader, tmp_path, clock=lambda: next(clock), wait_minutes=20)
    assert result.status == "pending" and result.batch_id == "batch_1"
    assert ScanStore(tmp_path / "_cache").meta(job_for(46).sha)["batch"]["id"] == "batch_1"
    reader.ready_after = 0  # the batch finishes
    later = read(job_for(46), reader, tmp_path)
    assert later.status == "read" and len(reader.submitted) == 1  # collected, not sent again
    assert all(f"[page {n}]" in later.text for n in range(1, 47))


# -- every page must appear: a partial scan ----------------------------------------------------------------------
def test_a_missing_page_makes_a_partial_scan_that_cannot_support_a_zero(tmp_path):
    reader = Reader(drop={7})
    result = read(job_for(20), reader, tmp_path)  # 15 + 5 pages
    assert result.status == "partial" and result.missing == [7]
    assert "[page 7]\n(page not read)" in result.text and "[page 8]" in result.text
    assert result.copy_type == "read by Claude (scan); partial scan"
    assert marks.cannot_support_zero(result.copy_type)


def test_only_the_chunk_with_the_missing_page_is_read_again_on_the_next_run(tmp_path):
    read(job_for(20), Reader(drop={7}), tmp_path)
    second = Reader()
    result = read(job_for(20), second, tmp_path)
    assert second.live_calls == [(1, 15)]  # the 5-page chunk was complete and is not read again
    assert result.status == "read" and result.missing == []
    assert not marks.cannot_support_zero(result.copy_type)


def test_dropped_section_text_is_marked_check_transcription_and_cannot_support_a_zero(tmp_path):
    result = read(job_for(20), Reader(skip={9}), tmp_path)  # page 9 comes back as section 10
    assert result.status == "read" and result.missing == []
    assert any("jump from 8" in p for p in result.problems)
    assert result.copy_type == "read by Claude (scan); check transcription"
    assert marks.cannot_support_zero(result.copy_type)


# -- stage 5 inside the fetch chain ---------------------------------------------------------------------------
@pytest.fixture
def settings(tmp_path):
    return dataclasses.replace(
        get_settings(),
        staged_fetch=True,
        outputs_dir=tmp_path,
        outputs_root=tmp_path,
        scan_reading_budget_usd=5.0,
        scan_batch_wait_minutes=20,
    )


def serve(data: bytes, ctype="application/pdf"):
    log = []

    def handler(request):
        log.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, content=data, headers={"content-type": ctype})

    http = httpx.Client(transport=httpx.MockTransport(handler), headers={"User-Agent": UA})
    http.log = log
    return http


def chain(tmp_path):
    return ChainTools(sleep=lambda s: None, cache_root=tmp_path / "_cache")


def staged(url, http, tmp_path, settings, folder="evidence"):
    return check_url_staged(
        url, http, tmp_path / folder, UA, settings=settings, tools=chain(tmp_path)
    )


def test_a_scan_is_queued_not_read_by_the_link_check_and_nothing_is_spent(tmp_path, settings):
    http = serve(scan_pdf(20))
    check = staged("https://x.gov.in/act.pdf", http, tmp_path, settings)
    assert check.verification_status == "Human Verification Required"
    assert check.failure == "scan" and "Scan reading queued: 20 pages" in " ".join(check.reasons)
    assert [j.pages for j in scan_reading.queued()] == [20]
    assert not METER.by_model
    # the PDF is kept in the shared cache, so another run does not download it again
    again = staged("https://x.gov.in/act.pdf", serve(b"gone"), tmp_path, settings)
    assert "no new download" in " ".join(again.stages) and again.failure == "scan"


def test_with_scan_reading_off_the_scan_is_not_queued(tmp_path, settings):
    off = dataclasses.replace(settings, scan_reading_budget_usd=0)
    check = staged("https://x.gov.in/act.pdf", serve(scan_pdf(20)), tmp_path, off)
    assert scan_reading.queued() == [] and "Scan reading is off" in " ".join(check.reasons)


# -- the end-of-run pass: order, budget, re-check of the rows ---------------------------------------------------
AGENCY = Parastatal(id="AAA", name="Sample Board", type="water_supply_entity")


@pytest.fixture
def run_context(tmp_path):
    (tmp_path / "evidence").mkdir(exist_ok=True)
    return RunContext(
        run_id="r",
        city="sample_city_a",
        city_name="Sample City A",
        state_name="S",
        ulg="U",
        workspace=str(tmp_path),
        output_dir=str(tmp_path),
        cache_dir=str(tmp_path / "evidence"),
    )


def row(url, tag, title="Doc", **kw) -> Source:
    return Source(
        citation_id=kw.pop("citation_id", "AAA-01"),
        parastatal_id="AAA",
        title=title,
        url=url,
        source_type="Enabling Act / Legislation",
        useful_for=f"[{tag}] something",
        verification_status="Human Verification Required",
        use_for_answers=False,
        **kw,
    )


@pytest.fixture
def services_with(services, settings, monkeypatch):
    def make(reader, **overrides):
        monkeypatch.setattr(
            common,
            "assess_source",
            lambda *a, **k: SourceAssessment(useful=True, effective_date="", form="Act in force"),
        )
        return dataclasses.replace(
            services,
            settings=dataclasses.replace(settings, **overrides),
            scan_reader=reader,
        )

    return make


def queue_two(tmp_path, settings):
    """A 30-page scan tagged [ACT] and a 16-page one tagged [CROSSLAW-NOTE] (not required)."""
    for url, pages in (("https://x.gov.in/big-act.pdf", 30), ("https://x.gov.in/small.pdf", 16)):
        staged(url, serve(scan_pdf(pages)), tmp_path, settings)
    return [
        row("https://x.gov.in/small.pdf", "NOTE", "Small note", citation_id="AAA-02"),
        row("https://x.gov.in/big-act.pdf", "ACT", "The Act", citation_id="AAA-01"),
    ]


def test_legal_texts_are_read_before_other_documents_even_when_larger(
    tmp_path, settings, run_context, services_with
):
    sources = queue_two(tmp_path, settings)
    reader = Reader()
    out, issues = scan_step.collect_scans(
        services_with(reader), run_context, sources, {"AAA": AGENCY}.get
    )
    assert reader.live_calls[:2] == [(1, 15), (16, 30)]  # the Act first (30 pages > 16 pages)
    by = {s.citation_id: s for s in out}
    assert by["AAA-01"].verification_status == "Verified"
    assert by["AAA-01"].copy_type == marks.SCAN
    assert by["AAA-02"].verification_status == "Verified"
    assert any("Scan reading: Claude read 2 document(s), 46 pages" in i.message for i in issues)


def test_when_the_budget_covers_only_one_the_legal_text_is_read_and_the_other_is_listed(
    tmp_path, settings, run_context, services_with
):
    class Pricey(Reader):  # each chunk really costs $0.21: the Act uses $0.42 of the $0.50
        usage = {"input_tokens": 30000, "output_tokens": 15000, "input_token_details": {}}

    sources = queue_two(tmp_path, settings)
    reader = Pricey()
    # 16 more pages would need $0.21 live, and only $0.08 is left
    out, issues = scan_step.collect_scans(
        services_with(reader, scan_reading_budget_usd=0.50),
        run_context,
        sources,
        {"AAA": AGENCY}.get,
    )
    by = {s.citation_id: s for s in out}
    assert by["AAA-01"].verification_status == "Verified"
    assert by["AAA-02"].verification_status == "Human Verification Required"
    assert "Scan reading: not read. 16 pages" in by["AAA-02"].notes
    over = [i for i in issues if "scanned document not read" in i.message]
    assert len(over) == 1 and "16 pages" in over[0].message and "$0.50" in over[0].message
    assert over[0].audience == "team" and over[0].severity == "warning"


def test_a_pending_batch_marks_the_row_and_the_next_run_collects_it(
    tmp_path, settings, run_context, services_with
):
    staged("https://x.gov.in/big.pdf", serve(scan_pdf(46)), tmp_path, settings)
    sources = [row("https://x.gov.in/big.pdf", "ACT", "The Act")]
    reader = Reader(ready_after=1000)
    ticks = iter(range(0, 10**6, 700))
    monkey = services_with(reader, scan_batch_wait_minutes=20)
    # a clock that runs 700 s per look: the 20-minute wait is over at once
    import asics_agent.links.scan_reading as sr

    original = sr.read_document
    sr.read_document = lambda job, **kw: original(job, **kw, clock=lambda: next(ticks))
    try:
        out, issues = scan_step.collect_scans(monkey, run_context, sources, {"AAA": AGENCY}.get)
    finally:
        sr.read_document = original
    assert out[0].copy_type == marks.SCAN_PENDING
    assert out[0].verification_status == "Human Verification Required"
    assert "Scan reading in progress" in out[0].notes
    assert any("scan reading in progress" in i.message for i in issues)
    assert marks.cannot_support_zero(out[0].copy_type)
    # next run: the same row is checked again, the finished batch is collected and nothing is re-sent
    reader.ready_after = 0
    fetch_chain.begin_run()
    staged("https://x.gov.in/big.pdf", serve(b"gone"), tmp_path, settings)
    done, _ = scan_step.collect_scans(monkey, run_context, sources, {"AAA": AGENCY}.get)
    assert done[0].verification_status == "Verified" and done[0].copy_type == marks.SCAN
    assert len(reader.submitted) == 1


def test_a_partial_scan_row_is_verified_for_a_positive_finding_but_flagged(
    tmp_path, settings, run_context, services_with
):
    staged("https://x.gov.in/act.pdf", serve(scan_pdf(20)), tmp_path, settings)
    out, issues = scan_step.collect_scans(
        services_with(Reader(drop={7})),
        run_context,
        [row("https://x.gov.in/act.pdf", "ACT", "The Act")],
        {"AAA": AGENCY}.get,
    )
    assert out[0].verification_status == "Verified"
    assert out[0].copy_type == "read by Claude (scan); partial scan"
    assert "Pages not read: 7." in out[0].notes
    lines = [i.message for i in fetch_issues(AGENCY, out, settings)]
    assert any("only PARTLY read" in m and "pages not read: 7" in m for m in lines)


def test_a_complete_scan_is_stored_for_good_and_a_second_city_does_not_pay(
    tmp_path, settings, run_context, services_with
):
    staged("https://x.gov.in/act.pdf", serve(scan_pdf(20)), tmp_path, settings)
    scan_step.collect_scans(
        services_with(Reader()),
        run_context,
        [row("https://x.gov.in/act.pdf", "ACT", "The Act")],
        {"AAA": AGENCY}.get,
    )
    # a later run in another city: the link check itself returns the read copy, with no request
    fetch_chain.begin_run()
    other_http = serve(b"unused")
    hit = staged(
        "https://x.gov.in/act.pdf", other_http, tmp_path, settings, folder="city_b/evidence"
    )
    assert hit.verification_status == "Verified" and hit.copy_type == marks.SCAN
    assert other_http.log == [] and Path(hit.content_path).parent.name == "evidence"
    assert "city_b" in hit.content_path and "[page 20]" in Path(hit.content_path).read_text()


# -- damaged PDFs -----------------------------------------------------------------------------------------------
def test_a_damaged_pdf_with_text_is_repaired_for_free_and_marked_repaired(tmp_path, settings):
    check = staged("https://x.gov.in/doc.pdf", serve(damaged(text_pdf(3))), tmp_path, settings)
    assert check.verification_status == "Verified" and check.copy_type == marks.REPAIRED
    assert "[page 3]" in Path(check.content_path).read_text()
    assert scan_reading.queued() == [] and not METER.by_model


def test_a_damaged_image_only_pdf_is_rendered_to_page_images_and_read_within_the_budget(
    tmp_path, settings, run_context, services_with
):
    check = staged("https://x.gov.in/doc.pdf", serve(damaged(scan_pdf(4))), tmp_path, settings)
    assert check.verification_status == "Human Verification Required"
    assert [(j.kind, j.pages) for j in scan_reading.queued()] == [("images", 4)]
    blocks = []

    class Spy(Reader):
        def live(self, b):
            blocks.append([x["type"] for x in b])
            return super().live(b)

    out, _ = scan_step.collect_scans(
        services_with(Spy()),
        run_context,
        [row("https://x.gov.in/doc.pdf", "ACT", "The Act")],
        {"AAA": AGENCY}.get,
    )
    assert blocks == [["text", "image"] * 4 + ["text"]]  # four page images, then the instruction
    assert out[0].verification_status == "Verified"
    assert out[0].copy_type == "read by Claude (page images)"


def test_a_file_that_cannot_be_opened_even_after_repair_stays_unreadable_and_costs_nothing(
    tmp_path, settings
):
    check = staged(
        "https://x.gov.in/doc.pdf", serve(b"%PDF-1.4\nnot really a pdf at all"), tmp_path, settings
    )
    assert check.verification_status == "Human Verification Required"
    assert check.failure == "unreadable" and "damaged and could not be opened" in " ".join(
        check.reasons
    )
    assert scan_reading.queued() == [] and not METER.by_model


# -- the download limit that made four real PDFs look damaged ------------------------------------------------------
def test_a_pdf_over_the_web_page_limit_but_under_the_pdf_limit_is_read_whole(
    tmp_path, settings, monkeypatch
):
    from asics_agent.links import accessibility

    data = text_pdf(3)
    monkeypatch.setattr(accessibility, "MAX_BYTES", 500)  # smaller than the file
    check = staged("https://x.gov.in/big.pdf", serve(data), tmp_path, settings)
    assert len(data) > 500 and check.verification_status == "Verified"
    assert check.copy_type == marks.PLAIN


def test_a_pdf_over_the_pdf_limit_says_so_instead_of_reading_half_a_file(
    tmp_path, settings, monkeypatch
):
    from asics_agent.links import accessibility

    monkeypatch.setattr(accessibility, "MAX_PDF_BYTES", 500)
    check = staged("https://x.gov.in/big.pdf", serve(text_pdf(3)), tmp_path, settings)
    assert check.failure == "too_large" and "download limit" in " ".join(check.reasons)
    assert scan_reading.queued() == []


# -- what the team sees ------------------------------------------------------------------------------------------------
def test_needs_attention_lines_for_each_scan_copy_state(settings):
    def src(cid, copy_type, notes=""):
        return Source(
            citation_id=cid,
            parastatal_id="AAA",
            title=cid,
            url=f"https://x.gov.in/{cid}",
            verification_status="Verified",
            copy_type=copy_type,
            notes=notes,
        )

    rows = [
        src("A1", "read by Claude (scan)"),
        src("A2", "read by Claude (scan); partial scan", "Pages not read: 4, 5."),
        src(
            "A3",
            "read by Claude (scan); check transcription",
            "Transcription check: section numbers jump from 8 (page 3) to 10 (page 4). Copy type: x.",
        ),
        src("A4", "repaired"),
        src("A5", "scan reading in progress"),
    ]
    text = "\n".join(i.message for i in fetch_issues(AGENCY, rows, settings))
    assert "only PARTLY read" in text and "A2 (pages not read: 4, 5)" in text
    assert "dropped text" in text and "jump from 8 (page 3) to 10 (page 4)" in text
    assert "transcribed from scanned pages" in text and "A1" in text
    assert "damaged and rewritten" in text and "A4" in text
    assert "scan reading is in progress for 1 document" in text and "A5" in text


def test_reading_order_is_legal_texts_then_required_sources_then_the_rest():
    def tag(t):
        return scan_step.priority(row("https://x.gov.in/a", t))

    assert [tag("ACT"), tag("RULES"), tag("ULG-LAW"), tag("TCP")] == [0, 0, 0, 0]
    assert tag("BUDGET") == 1 and tag("AR") == 1
    assert tag("SOMETHING-ELSE") == 2


# -- a page that costs more than the estimate (the real test: Kannada, $0.030 a page) ----------------------------
class Expensive(Reader):  # $0.50 a chunk of 15 pages: $0.033 a page, 2.6x the $0.013 estimate
    usage = {"input_tokens": 50000, "output_tokens": 40000, "input_token_details": {}}


def test_a_document_that_costs_more_than_expected_stops_when_the_rest_does_not_fit(tmp_path):
    budget = ScanBudget()
    budget.limit = 0.90  # 40 pages are expected to cost $0.52, so the document is started...
    reader = Expensive()
    result = read(job_for(40), reader, tmp_path, budget=budget)
    # ...but the first chunk (read alone, to measure) shows $0.033 a page: the other 25 pages need ~$1
    assert reader.live_calls == [(1, 15)]
    assert result.status == "partial" and result.missing == list(range(16, 41))
    assert "stopped after page 15" in result.stopped and "$0.033 a page" in result.stopped
    assert budget.spent == pytest.approx(0.50) and budget.spent <= budget.limit
    assert marks.cannot_support_zero(result.copy_type)
    # with a bigger budget the next run reads only what is missing
    later = Expensive()
    big = ScanBudget()
    big.limit = 5.0
    done = read(job_for(40), later, tmp_path, budget=big)
    assert later.live_calls == [(16, 30), (31, 40)] and done.status == "read"


def test_the_budget_is_never_overspent_by_a_document_that_turns_out_dearer(tmp_path):
    for limit in (0.60, 0.90, 1.40):
        budget = ScanBudget()
        budget.limit = limit
        read(
            job_for(40, url=f"https://x.gov.in/{limit}.pdf"),
            Expensive(),
            tmp_path / str(limit),
            budget=budget,
        )
        assert budget.spent <= limit + 1e-9


def test_a_big_document_in_a_tight_budget_reads_its_first_chunk_live_then_sends_the_rest_as_a_batch(
    tmp_path,
):
    budget = ScanBudget()
    budget.limit = 0.50  # 46 pages as a batch are expected at $0.30, but 3x of that is $0.90
    reader = Reader()
    result = read(job_for(46), reader, tmp_path, budget=budget)
    assert reader.live_calls == [(1, 15)]
    assert reader.submitted == [["p16-30", "p31-45", "p46-46"]]
    assert result.status == "read" and result.mode == "batch"
    assert result.cost == pytest.approx(0.007 + 3 * 0.007 / 2)


def test_a_roomy_budget_sends_the_whole_document_as_one_batch_without_a_probe(tmp_path):
    reader = Reader()
    read(job_for(46), reader, tmp_path)  # the default test budget is $100
    assert reader.live_calls == [] and len(reader.submitted) == 1


def test_the_team_is_told_when_a_reading_stopped_because_the_price_was_higher(
    tmp_path, settings, run_context, services_with
):
    staged("https://x.gov.in/act.pdf", serve(scan_pdf(40)), tmp_path, settings)
    out, issues = scan_step.collect_scans(
        services_with(Expensive(), scan_reading_budget_usd=0.90),
        run_context,
        [row("https://x.gov.in/act.pdf", "ACT", "The Act")],
        {"AAA": AGENCY}.get,
    )
    assert out[0].copy_type == "read by Claude (scan); partial scan"
    assert any("stopped after page 15" in i.message and i.severity == "warning" for i in issues)
    lines = [i.message for i in fetch_issues(AGENCY, out, settings)]
    assert any("only PARTLY read" in m and "pages not read: 16, 17" in m for m in lines)
