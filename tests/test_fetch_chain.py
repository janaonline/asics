"""The staged fetch (links/fetch_chain.py): each stage, the marks, the archive rules, the failure cache,
the time cap, the per-host limit. No real network and no model: httpx.MockTransport, a scripted
renderer and a scripted Wayback client. One test drives real Chromium against a local web server and
is skipped when Chromium is not installed."""

import dataclasses
import http.server
import threading
import time
from datetime import date, timedelta
from pathlib import Path

import httpx
import pytest
from openpyxl import load_workbook

from asics_agent.agents.links_builder import fetch_issues
from asics_agent.config import get_settings
from asics_agent.links import fetch_chain, marks
from asics_agent.links.browser import ChromiumRenderer, RenderResult
from asics_agent.links.fetch_chain import ChainTools, check_url_staged, is_official_host
from asics_agent.links.wayback import WaybackResult
from asics_agent.models import Parastatal, Source
from asics_agent.sources_workbook import read_sources_workbook, sources_path, workspace_for

BODY = " ".join(["The Board publishes its annual budget and reports here."] * 40)
PAGE = f"<html><body><p>{BODY}</p></body></html>"
SHORT = "<html><body><p>Loading</p></body></html>"
TODAY = date(2026, 11, 24)
UA = "test-agent ASICS-link-check/1.0"


@pytest.fixture(autouse=True)
def clean_state():
    from asics_agent.links import accessibility

    accessibility._robots_cache.clear()  # robots.txt answers are remembered per website
    fetch_chain._slots.clear()
    fetch_chain.CLOCK.begin()
    yield


@pytest.fixture
def settings(tmp_path):
    return dataclasses.replace(
        get_settings(),
        staged_fetch=True,
        outputs_dir=tmp_path,
        outputs_root=tmp_path,
        archive_max_age_days=365,
        failure_cache_hours=24,
        fetch_time_cap_minutes=20,
    )


class Renderer:
    def __init__(self, result=None):
        self.result = result or RenderResult(False, error="not scripted")
        self.calls = []

    def render(self, url, *, ignore_cert_errors, user_agent, timeout=60.0):
        self.calls.append({"url": url, "ignore_cert_errors": ignore_cert_errors, "ua": user_agent})
        return self.result

    def close(self):
        pass


class Archive:
    def __init__(self, result=None):
        self.result = result or WaybackResult(False, error="no archived copy")
        self.calls = []

    def fetch(self, url):
        self.calls.append(url)
        return self.result


def client_for(handler):
    """A client whose requests are answered by handler(request) and counted in .log."""
    log = []

    def wrapped(request):
        log.append(str(request.url))
        return handler(request)

    http = httpx.Client(transport=httpx.MockTransport(wrapped), headers={"User-Agent": UA})
    http.log = log
    return http


def ok(request):
    if request.url.path == "/robots.txt":
        return httpx.Response(404)
    return httpx.Response(200, html=PAGE)


def tools(tmp_path, *, renderer=None, wayback=None, unverified=None):
    return ChainTools(
        renderer=renderer or Renderer(),
        wayback=wayback or Archive(),
        unverified_client=(lambda ua: unverified) if unverified is not None else None,
        sleep=lambda s: None,
        today=lambda: TODAY,
        cache_root=tmp_path / "_cache",
    )


def run(url, http, tmp_path, settings, chain, official=frozenset()):
    return check_url_staged(
        url, http, tmp_path / "evidence", UA, official, settings=settings, tools=chain
    )


# -- stage 1: plain HTTP, and the switch -----------------------------------------------------------
def test_a_page_the_plain_check_opens_is_marked_plain_http(tmp_path, settings):
    chain = tools(tmp_path)
    check = run("https://x.gov.in/a", client_for(ok), tmp_path, settings, chain)
    assert check.verification_status == "Verified"
    assert check.copy_type == marks.PLAIN
    assert "Copy type: plain HTTP." in " ".join(check.reasons)
    assert chain.renderer.calls == [] and chain.wayback.calls == []


def test_with_the_switch_off_the_result_is_the_plain_check_exactly(tmp_path, settings):
    off = dataclasses.replace(settings, staged_fetch=False)
    chain = tools(tmp_path)
    check = run(
        "https://x.gov.in/a", client_for(lambda r: httpx.Response(404)), tmp_path, off, chain
    )
    assert check.verification_status == "Not verified"
    assert check.copy_type == "" and check.stages == []
    assert chain.renderer.calls == [] and chain.wayback.calls == []


# -- stage 2: retries and address variants ---------------------------------------------------------
def test_a_site_that_only_answers_on_http_opens_on_the_variant(tmp_path, settings):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.scheme == "https":
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(200, html=PAGE)

    check = run("https://x.gov.in/a", client_for(handler), tmp_path, settings, tools(tmp_path))
    assert check.verification_status == "Verified"
    assert check.copy_type == marks.PLAIN
    assert "http://x.gov.in/a" in " ".join(check.reasons)
    assert check.stages[-1].startswith("retries and address variants (opened")


def test_the_www_form_is_tried(tmp_path, settings):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.host == "www.x.gov.in":
            return httpx.Response(200, html=PAGE)
        raise httpx.ConnectError("no route", request=request)

    check = run("https://x.gov.in/a", client_for(handler), tmp_path, settings, tools(tmp_path))
    assert check.verification_status == "Verified" and "www.x.gov.in" in " ".join(check.reasons)


def test_an_untrusted_certificate_is_bypassed_for_an_official_host_and_marked(tmp_path, settings):
    def refuse(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        raise httpx.ConnectError("certificate verify failed", request=request)

    unverified = client_for(ok)
    chain = tools(tmp_path, unverified=unverified)
    check = run(
        "https://x.bda-own.in/a",
        client_for(refuse),
        tmp_path,
        settings,
        chain,
        official={"bda-own.in"},
    )
    assert check.verification_status == "Verified"
    assert check.copy_type == "plain HTTP; certificate not verified"
    assert unverified.log  # the unverified client was used


def test_an_untrusted_certificate_is_never_bypassed_for_another_host(tmp_path, settings):
    def refuse(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        raise httpx.ConnectError("certificate verify failed", request=request)

    unverified = client_for(ok)
    renderer = Renderer(
        RenderResult(
            True,
            text=BODY,
            html=PAGE,
            content_type="text/html",
            final_url="https://shop.example.com/a",
        )
    )
    chain = tools(tmp_path, renderer=renderer, unverified=unverified)
    check = run(
        "https://shop.example.com/a",
        client_for(refuse),
        tmp_path,
        settings,
        chain,
        official={"bda-own.in"},
    )
    assert check.verification_status != "Verified"
    assert unverified.log == [] and renderer.calls == []
    assert "not an official host" in " ".join(check.stages)


def test_official_hosts():
    assert is_official_host("https://a.b.gov.in/x") and is_official_host("https://w.nic.in/")
    assert is_official_host("https://sub.bwssb.org/x", {"bwssb.org"})
    assert not is_official_host("https://evilbwssb.org/x", {"bwssb.org"})
    assert not is_official_host("https://example.com/")


# -- stage 3: the browser -------------------------------------------------------------------------
def js_page(request):
    if request.url.path == "/robots.txt":
        return httpx.Response(404)
    return httpx.Response(200, html=SHORT)


def test_a_javascript_page_opens_in_the_browser_and_is_marked(tmp_path, settings):
    renderer = Renderer(
        RenderResult(
            True,
            text=BODY,
            html=PAGE,
            content_type="text/html",
            final_url="https://x.gov.in/a",
            status=200,
        )
    )
    chain = tools(tmp_path, renderer=renderer)
    check = run("https://x.gov.in/a", client_for(js_page), tmp_path, settings, chain)
    assert check.verification_status == "Verified"
    assert check.copy_type == marks.BROWSER
    assert (
        renderer.calls[0]["ignore_cert_errors"] is False
        and "ASICS-link-check" in renderer.calls[0]["ua"]
    )
    assert check.snapshot_path and check.snapshot_path.endswith(
        ".html"
    )  # the rendered HTML, for the crawl
    assert Path(check.content_path).read_text().count("annual budget") >= 40
    assert chain.wayback.calls == []  # not needed


def test_the_browser_gets_a_certificate_error_through_only_on_an_official_host(tmp_path, settings):
    def refuse(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        raise httpx.ConnectError("certificate verify failed", request=request)

    result = RenderResult(
        True, text=BODY, html=PAGE, content_type="text/html", final_url="https://x.gov.in/a"
    )
    renderer = Renderer(result)
    chain = tools(tmp_path, renderer=renderer, unverified=client_for(lambda r: httpx.Response(500)))
    check = run("https://x.gov.in/a", client_for(refuse), tmp_path, settings, chain)
    assert check.verification_status == "Verified"
    assert renderer.calls[0]["ignore_cert_errors"] is True
    assert check.copy_type == "browser-rendered; certificate not verified"


def test_a_challenge_page_after_the_browser_is_a_failure_not_a_copy(tmp_path, settings):
    text = "Just a moment... " + BODY
    renderer = Renderer(
        RenderResult(
            True,
            text=text,
            html=f"<p>{text}</p>",
            content_type="text/html",
            final_url="https://x.gov.in/a",
        )
    )
    check = run(
        "https://x.gov.in/a",
        client_for(js_page),
        tmp_path,
        settings,
        tools(tmp_path, renderer=renderer),
    )
    assert check.verification_status != "Verified" and check.copy_type == ""
    assert "challenge page" in " ".join(check.stages)


def test_a_soft_404_after_the_browser_is_a_failure(tmp_path, settings):
    text = "Page not found. " + " ".join(["menu"] * 50)
    renderer = Renderer(
        RenderResult(
            True,
            text=text,
            html=f"<p>{text}</p>",
            content_type="text/html",
            final_url="https://x.gov.in/a",
        )
    )
    check = run(
        "https://x.gov.in/a",
        client_for(js_page),
        tmp_path,
        settings,
        tools(tmp_path, renderer=renderer),
    )
    assert check.verification_status != "Verified" and "soft 404" in " ".join(check.stages)


def test_a_browser_redirect_to_another_site_is_refused(tmp_path, settings):
    renderer = Renderer(
        RenderResult(
            True,
            text=BODY,
            html=PAGE,
            content_type="text/html",
            final_url="https://other-site.com/a",
        )
    )
    check = run(
        "https://x.gov.in/a",
        client_for(js_page),
        tmp_path,
        settings,
        tools(tmp_path, renderer=renderer),
    )
    assert check.verification_status != "Verified" and "different site" in " ".join(check.stages)


def test_without_chromium_the_stage_is_skipped_and_says_so(tmp_path, settings):
    renderer = Renderer(
        RenderResult(
            False,
            error="browser not installed: run `uv run playwright install chromium` once on this computer",
            unavailable=True,
        )
    )
    check = run(
        "https://x.gov.in/a",
        client_for(js_page),
        tmp_path,
        settings,
        tools(tmp_path, renderer=renderer),
    )
    assert check.verification_status != "Verified"
    assert "browser not installed" in " ".join(check.reasons)


def test_the_zero_words_message_lists_the_stages_tried(tmp_path, settings):
    renderer = Renderer(RenderResult(False, error="TimeoutError: page took too long"))
    check = run(
        "https://x.gov.in/a",
        client_for(js_page),
        tmp_path,
        settings,
        tools(tmp_path, renderer=renderer),
    )
    text = " ".join(check.reasons)
    assert "Only 0 words of readable content" in text or "Only 1 words" in text
    assert "Tried: plain HTTP (only" in text
    assert "retries: not needed" in text and "browser render (Chromium): TimeoutError" in text
    assert "Wayback: not tried" in text


# -- stage 4: the Wayback Machine -----------------------------------------------------------------
def archived(day, body=PAGE):
    return WaybackResult(True, body.encode(), "text/html", day, "https://web.archive.org/web/x")


def gone(request):
    if request.url.path == "/robots.txt":
        return httpx.Response(404)
    return httpx.Response(404, html="<p>gone</p>")


def test_a_404_with_a_recent_archived_copy_opens_and_is_marked(tmp_path, settings):
    day = (TODAY - timedelta(days=30)).isoformat()
    archive = Archive(archived(day))
    renderer = Renderer()
    check = run(
        "https://x.gov.in/a",
        client_for(gone),
        tmp_path,
        settings,
        tools(tmp_path, renderer=renderer, wayback=archive),
    )
    assert check.verification_status == "Verified"
    assert check.copy_type == f"ARCHIVED {day}" and check.archived_on == day
    assert renderer.calls == []  # an error page looks the same in a browser
    assert "archived copy" in " ".join(check.reasons)


def test_an_unreachable_site_falls_back_to_the_archive(tmp_path, settings):
    def down(request):
        raise httpx.ConnectTimeout("timed out", request=request)

    day = (TODAY - timedelta(days=100)).isoformat()
    renderer = Renderer(RenderResult(False, error="TimeoutError"))
    check = run(
        "https://x.gov.in/a",
        client_for(down),
        tmp_path,
        settings,
        tools(tmp_path, renderer=renderer, wayback=Archive(archived(day))),
    )
    assert check.verification_status == "Verified" and check.copy_type == f"ARCHIVED {day}"
    assert len(renderer.calls) == 1  # the browser was tried first


def test_a_stale_archive_is_not_used(tmp_path, settings):
    day = (TODAY - timedelta(days=400)).isoformat()
    check = run(
        "https://x.gov.in/a",
        client_for(gone),
        tmp_path,
        settings,
        tools(tmp_path, wayback=Archive(archived(day))),
    )
    assert check.verification_status == "Human Verification Required"
    assert check.stale_archive and "stale archive" in check.copy_type and day in check.copy_type
    assert not check.content_path
    assert "400 days old" in " ".join(check.reasons)


def test_a_challenge_page_in_the_archive_is_not_a_copy(tmp_path, settings):
    body = "<p>Attention Required! " + BODY + "</p>"
    check = run(
        "https://x.gov.in/a",
        client_for(gone),
        tmp_path,
        settings,
        tools(tmp_path, wayback=Archive(archived(TODAY.isoformat(), body))),
    )
    assert check.verification_status != "Verified"


# -- what the chain never retries -----------------------------------------------------------------
def test_robots_txt_stops_every_stage(tmp_path, settings):
    def robots(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /")
        return httpx.Response(200, html=PAGE)

    chain = tools(tmp_path)
    check = run("https://x.gov.in/a", client_for(robots), tmp_path, settings, chain)
    assert check.verification_status == "Human Verification Required" and check.failure == "robots"
    assert chain.renderer.calls == [] and chain.wayback.calls == []


def test_a_redirect_to_a_different_site_is_left_to_a_person(tmp_path, settings):
    def moved(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.host == "x.gov.in":
            return httpx.Response(302, headers={"location": "https://elsewhere.com/a"})
        return httpx.Response(200, html=PAGE)

    chain = tools(tmp_path)
    check = run("https://x.gov.in/a", client_for(moved), tmp_path, settings, chain)
    assert (
        check.verification_status == "Human Verification Required" and check.failure == "redirect"
    )
    assert chain.renderer.calls == [] and chain.wayback.calls == []


# -- the failure cache and the time cap -----------------------------------------------------------
def test_a_link_that_failed_every_stage_is_not_retried_within_the_window(tmp_path, settings):
    chain = tools(tmp_path)
    first_client = client_for(gone)
    first = run("https://x.gov.in/a", first_client, tmp_path, settings, chain)
    assert first.verification_status != "Verified" and not first.not_retried and first_client.log
    second_client = client_for(ok)  # would open it, but must not be asked
    second = run("https://x.gov.in/a", second_client, tmp_path, settings, chain)
    assert second.not_retried and second_client.log == []
    assert fetch_chain.NOT_RETRIED_NOTE in " ".join(second.reasons)
    # after the window the link is tried again
    store = fetch_chain.FailureCache(tmp_path / "_cache", 24)
    data = store._load()
    key = fetch_chain.norm_key("https://x.gov.in/a")
    data[key]["at"] = (fetch_chain.datetime.now(fetch_chain.UTC) - timedelta(hours=25)).isoformat()
    store.path.write_text(__import__("json").dumps(data))
    third = run("https://x.gov.in/a", second_client, tmp_path, settings, chain)
    assert third.verification_status == "Verified" and second_client.log


def test_the_failure_window_is_a_setting_and_zero_turns_it_off(tmp_path, settings):
    off = dataclasses.replace(settings, failure_cache_hours=0)
    chain = tools(tmp_path)
    run("https://x.gov.in/a", client_for(gone), tmp_path, off, chain)
    again = client_for(ok)
    assert run("https://x.gov.in/a", again, tmp_path, off, chain).verification_status == "Verified"


def test_past_the_time_cap_links_get_the_plain_check_only_and_are_listed(tmp_path, settings):
    capped = dataclasses.replace(settings, fetch_time_cap_minutes=0.0001)
    fetch_chain.CLOCK.begin()
    time.sleep(0.02)
    renderer = Renderer(
        RenderResult(
            True, text=BODY, html=PAGE, content_type="text/html", final_url="https://x.gov.in/a"
        )
    )
    chain = tools(tmp_path, renderer=renderer)
    check = run("https://x.gov.in/a", client_for(js_page), tmp_path, capped, chain)
    assert check.not_retried and check.verification_status != "Verified"
    assert renderer.calls == [] and chain.wayback.calls == []
    assert fetch_chain.NOT_RETRIED_NOTE in " ".join(check.reasons)
    # a plain success past the cap still counts: stage 1 always runs
    assert (
        run("https://x.gov.in/b", client_for(ok), tmp_path, capped, chain).verification_status
        == "Verified"
    )


# -- politeness ------------------------------------------------------------------------------------
def test_at_most_two_requests_at_a_time_to_one_host():
    running, peak, lock = [0], [0], threading.Lock()

    def work():
        with fetch_chain.host_slot("https://www.x.gov.in/a"):
            with lock:
                running[0] += 1
                peak[0] = max(peak[0], running[0])
            time.sleep(0.05)
            with lock:
                running[0] -= 1

    threads = [threading.Thread(target=work) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert peak[0] == 2
    # a different host is not held up by the first
    with fetch_chain.host_slot("https://other.in/"):
        pass


def test_the_default_user_agent_names_the_tool():
    assert "ASICS-link-check" in get_settings().user_agent


# -- the marks, in the Citation Sheet and in Needs Attention --------------------------------------
def test_marks_helpers():
    assert marks.archived("2024-03-02") == "ARCHIVED 2024-03-02"
    assert (
        marks.join("browser-rendered", "", "certificate not verified")
        == "browser-rendered; certificate not verified"
    )
    assert marks.cannot_support_zero("ARCHIVED 2024-03-02") and marks.cannot_support_zero(
        "partial scan"
    )
    assert not marks.cannot_support_zero("browser-rendered; certificate not verified")
    assert marks.is_stale("ARCHIVED 2024-03-02; stale archive")


def make_source(**kwargs):
    base = dict(parastatal_id="AAA", title="Doc", url="https://x.gov.in/a", citation_id="AAA-01")
    return Source(**{**base, **kwargs})


def test_needs_attention_lists_archived_stale_certificate_and_not_retried_rows():
    agency = Parastatal(id="AAA", name="Sample Board", type="water_supply_entity")
    sources = [
        make_source(citation_id="AAA-01", url="https://x/1", copy_type="ARCHIVED 2025-01-02"),
        make_source(
            citation_id="AAA-02", url="https://x/2", copy_type="ARCHIVED 2022-01-02; stale archive"
        ),
        make_source(
            citation_id="AAA-03",
            url="https://x/3",
            copy_type="browser-rendered; certificate not verified",
        ),
        make_source(
            citation_id="AAA-04",
            url="https://x/4",
            notes=f"{fetch_chain.NOT_RETRIED_NOTE}: time cap",
        ),
        make_source(
            citation_id="AAA-05",
            url="https://x/5",
            notes="Tried: plain HTTP (only 0 words); browser render (Chromium): browser not installed: run it.",
        ),
    ]
    text = "\n".join(i.message for i in fetch_issues(agency, sources))
    assert "AAA-01 (ARCHIVED 2025-01-02)" in text and "never a zero" in text
    assert "stale archived copy" in text and "AAA-02" in text
    assert "without verifying" in text and "AAA-03" in text
    assert "not retried this run" in text and "AAA-04" in text
    assert "Chromium is not installed" in text
    assert fetch_issues(agency, [make_source(copy_type="plain HTTP")]) == []


def test_copy_type_round_trips_and_an_old_sheet_without_it_still_loads(
    services, run_steps, tmp_path
):
    run_steps("sources")
    path = sources_path(
        workspace_for(services.settings.outputs_dir, "Sample City A"), "Sample City A"
    )
    wb = load_workbook(path)
    ws = wb["Citation Sheet"]
    assert ws.cell(1, ws.max_column).value == "Copy Type"
    # the team's own columns stay: Human-Verified? is just before it
    assert ws.cell(1, ws.max_column - 1).value == "Human-Verified?"
    column = ws.max_column
    ws.cell(2, column).value = "ARCHIVED 2024-03-02"
    marked = tmp_path / "marked.xlsx"
    wb.save(marked)
    _, citations, _ = read_sources_workbook(marked, tmp_path / "evidence")
    assert [c.copy_type for c in citations][0] == "ARCHIVED 2024-03-02"
    # a sheet from before this column
    ws.delete_cols(column)
    old = tmp_path / "old.xlsx"
    wb.save(old)
    _, citations, issues = read_sources_workbook(old, tmp_path / "evidence")
    assert citations and all(c.copy_type == "" for c in citations)
    assert not [i for i in issues if i.severity == "error"]


# -- an archived copy and the zero gate, the crawl, and the cut-off ------------------------------------------
def test_an_archived_copy_never_satisfies_a_required_source(tmp_path):
    from asics_agent import source_requirements as sr

    agency = Parastatal(
        id="AAA",
        name="Sample Board",
        type="water_supply_entity",
        governing_act="Sample Water Act, 1970 (State Act 3 of 1970)",
        official_website="https://www.sample-board.in/",
    )
    path = tmp_path / "act.txt"
    path.write_text("The Board shall exist.", encoding="utf-8")

    def act(copy_type):
        return Source(
            citation_id="AAA-01",
            parastatal_id="AAA",
            title="Act",
            url="https://x.gov.in/act",
            source_type="Enabling Act / Legislation",
            useful_for="[ACT] the Act",
            verification_status="Verified",
            use_for_answers=True,
            content_path=str(path),
            copy_type=copy_type,
        )

    req = dataclasses.replace(sr.required_for("DPG 1a"), groups=(("LEGAL_BASE",),))  # only the Act
    assert req.has_zero_rule
    live = sr.check(req, agency, [act("plain HTTP")])
    assert live.state == "allowed" and [s.citation_id for s in live.rows] == ["AAA-01"]
    archived_gate = sr.check(req, agency, [act("ARCHIVED 2025-05-01")])
    assert archived_gate.state == "unreadable" and archived_gate.unreadable == ["AAA-01"]
    assert archived_gate.rows == []
    assert "archived copy" in sr.decide_zero(req, agency, [act("ARCHIVED 2025-05-01")]).note
    partial = sr.check(req, agency, [act("read by Claude (scan); partial scan")])
    assert partial.state == "unreadable"  # a partial scan cannot support a zero either


def test_an_archived_copy_with_no_date_in_the_text_uses_the_archive_date_for_the_cutoff(
    services, monkeypatch, tmp_path
):
    from asics_agent.agents import common
    from asics_agent.agents.common import SourceAssessment, vet_source
    from asics_agent.models import AccessCheck, RunContext
    from asics_agent.practice import fake_http  # noqa: F401

    cache = tmp_path / "evidence"
    cache.mkdir()
    text = cache / "t.txt"
    text.write_text("x " * 300, encoding="utf-8")
    settings = dataclasses.replace(services.settings, law_cutoff=date(2026, 8, 31))
    services = dataclasses.replace(services, settings=settings)

    def stub(day):
        monkeypatch.setattr(
            common,
            "check_url_staged",
            lambda *a, **k: AccessCheck(
                url="https://x.gov.in/a",
                verification_status="Verified",
                accessibility="Public",
                content_path=str(text),
                copy_type=f"ARCHIVED {day}",
                archived_on=day,
                checked_at="2026-11-24T10:00:00",
            ),
        )

    def assess(date_text):
        monkeypatch.setattr(
            common,
            "assess_source",
            lambda *a, **k: SourceAssessment(
                useful=True, effective_date=date_text, form="Act in force"
            ),
        )

    agency = Parastatal(id="AAA", name="Sample Board", type="water_supply_entity")
    run_context = RunContext(
        run_id="r",
        city="sample_city_a",
        city_name="Sample City A",
        state_name="S",
        ulg="U",
        workspace=str(tmp_path),
        output_dir=str(tmp_path),
        cache_dir=str(cache),
    )
    candidate = common.CandidateSource(
        title="Act",
        url="https://x.gov.in/a",
        source_type="Enabling Act / Legislation",
        useful_for="the Act",
    )

    stub("2026-03-02"), assess("")
    before, _ = vet_source(
        services, run_context, agency, candidate, provenance="web_search", allowed_urls=None
    )
    assert (
        before.effective_date == "2026-03-02"
        and before.cutoff_check == "ok"
        and before.copy_type == "ARCHIVED 2026-03-02"
    )
    stub("2026-10-01"), assess("")
    after, _ = vet_source(
        services, run_context, agency, candidate, provenance="web_search", allowed_urls=None
    )
    assert after.effective_date == "2026-10-01" and after.cutoff_check == "later"
    stub("2026-10-01"), assess("1964-04-01")  # the assessor's own date from the text wins
    own, _ = vet_source(
        services, run_context, agency, candidate, provenance="web_search", allowed_urls=None
    )
    assert own.effective_date == "1964-04-01" and own.cutoff_check == "ok"


# -- real Chromium against a local site (skipped when Chromium is not installed) -----------------------
class Site(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/robots.txt":
            self.send_response(404)
            self.end_headers()
            return
        page = (
            "<html><body><div id=app>Loading</div><script>document.getElementById('app').innerText = "
            f"{BODY!r};</script></body></html>"
        )
        self.send_response(200)
        self.send_header("content-type", "text/html")
        self.end_headers()
        self.wfile.write(page.encode())


@pytest.fixture
def local_site():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Site)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_real_chromium_draws_a_javascript_page_the_plain_check_cannot_read(
    local_site, tmp_path, settings
):
    renderer = ChromiumRenderer()
    try:
        probe = renderer.render(local_site + "/", ignore_cert_errors=False, user_agent=UA)
        if probe.unavailable:
            pytest.skip(f"Chromium is not installed here: {probe.error}")
        chain = ChainTools(
            renderer=renderer,
            wayback=Archive(),
            sleep=lambda s: None,
            today=lambda: TODAY,
            cache_root=tmp_path / "_cache",
        )
        plain = httpx.Client(headers={"User-Agent": UA})
        check = check_url_staged(
            local_site + "/", plain, tmp_path / "evidence", UA, settings=settings, tools=chain
        )
        assert check.verification_status == "Verified" and check.copy_type == marks.BROWSER
        assert check.words > 300 and "annual budget" in Path(check.content_path).read_text()
    finally:
        renderer.close()


def test_own_domains_come_from_the_agency_rows_of_the_citation_sheet():
    from asics_agent.agents.common import own_domains

    agency = Parastatal(
        id="AAA",
        name="Sample Board",
        type="water_supply_entity",
        official_website="https://www.sample.gov.in/",
    )
    rows = [
        make_source(
            url="https://livesite.org/",
            source_type="Official Parastatal Website",
            human_verified=True,
        ),
        make_source(
            url="https://checked.org/x",
            source_type="Official website",
            verification_status="Verified",
        ),
        make_source(
            url="https://unchecked.org/x", source_type="Official Parastatal Website"
        ),  # not verified, not flagged
        make_source(
            url="https://news.com/x", source_type="Government Publication", human_verified=True
        ),  # not a website row
        make_source(
            url="https://other.org/",
            source_type="Official Parastatal Website",
            human_verified=True,
            parastatal_id="BBB",
        ),
    ]
    assert own_domains(agency, rows) == {"sample.gov.in", "livesite.org", "checked.org"}
