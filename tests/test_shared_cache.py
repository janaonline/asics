"""The shared copy cache (links/shared_cache.py) and its use by the fetch chain: one download serves
every city and step. No network (httpx.MockTransport), no model."""

import dataclasses
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from asics_agent.config import get_settings
from asics_agent.links import fetch_chain, marks
from asics_agent.links.fetch_chain import ChainTools, check_url_staged
from asics_agent.links.shared_cache import SharedCache
from asics_agent.links.wayback import WaybackResult
from asics_agent.models import AccessCheck

BODY = " ".join(["The Board publishes its annual budget and reports here."] * 40)
PAGE = f"<html><body><p>{BODY}</p></body></html>"
UA = "test-agent ASICS-link-check/1.0"


@pytest.fixture(autouse=True)
def clean_state():
    from asics_agent.links import accessibility

    accessibility._robots_cache.clear()
    fetch_chain._slots.clear()
    fetch_chain.begin_run()
    yield


@pytest.fixture
def settings(tmp_path):
    return dataclasses.replace(
        get_settings(),
        staged_fetch=True,
        outputs_dir=tmp_path,
        outputs_root=tmp_path,
        fetch_cache_max_age_days=30,
    )


def client(page=PAGE, status=200):
    log = []

    def handler(request):
        log.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(status, html=page)

    http = httpx.Client(transport=httpx.MockTransport(handler), headers={"User-Agent": UA})
    http.log = log
    return http


def run(url, http, tmp_path, settings, folder="evidence"):
    chain = ChainTools(sleep=lambda s: None, cache_root=tmp_path / "_cache")
    return check_url_staged(url, http, tmp_path / folder, UA, settings=settings, tools=chain)


def verified_check(tmp_path, url, text="x " * 120, copy_type="plain HTTP", folder="e", ext=".html"):
    """A saved copy in an evidence folder, as accept_text leaves it."""
    folder_path = tmp_path / folder
    folder_path.mkdir(exist_ok=True, parents=True)
    (folder_path / "a.txt").write_text(f"SOURCE URL: {url}\n\n{text}", encoding="utf-8")
    (folder_path / f"a{ext}").write_bytes(b"<html>original</html>")
    check = AccessCheck(url=url, verification_status="Verified", words=len(text.split()))
    check.content_path = str(folder_path / "a.txt")
    check.snapshot_path = str(folder_path / f"a{ext}")
    check.copy_type = copy_type
    return check


# -- through the fetch chain -----------------------------------------------------------------------
def test_a_second_city_reuses_the_copy_without_a_request_and_keeps_the_mark(tmp_path, settings):
    first = client()
    a = run("https://x.gov.in/budget", first, tmp_path, settings, folder="city_a/evidence")
    assert (
        a.verification_status == "Verified" and a.copy_type == marks.PLAIN and len(first.log) == 2
    )
    second = client(status=500)  # would fail if it were asked
    b = run("https://x.gov.in/budget", second, tmp_path, settings, folder="city_b/evidence")
    assert second.log == []
    assert b.verification_status == "Verified" and b.copy_type == marks.PLAIN
    assert "shared cache" in " ".join(b.reasons)
    # the copy sits in the second city's own evidence folder, under the usual name
    assert (
        "city_b" in b.content_path and Path(b.content_path).read_text().count("annual budget") > 10
    )
    assert b.snapshot_path and Path(b.snapshot_path).exists() and "city_b" in b.snapshot_path


def test_the_same_page_written_differently_is_one_cache_entry(tmp_path, settings):
    run("https://www.x.gov.in/budget/?utm_source=mail", client(), tmp_path, settings)
    other = client(status=500)
    hit = run("http://x.gov.in/budget", other, tmp_path, settings, folder="elsewhere")
    assert other.log == [] and hit.verification_status == "Verified"


def test_the_browser_and_archive_marks_travel_with_the_cached_copy(tmp_path, settings):
    class Archive:
        calls = 0

        def fetch(self, url):
            Archive.calls += 1
            return WaybackResult(
                True, body=PAGE.encode(), content_type="text/html", archived_on="2026-05-01"
            )

    chain = ChainTools(wayback=Archive(), sleep=lambda s: None, cache_root=tmp_path / "_cache")
    gone = client(status=404)
    got = check_url_staged(
        "https://x.gov.in/old", gone, tmp_path / "e1", UA, settings=settings, tools=chain
    )
    assert marks.is_archived(got.copy_type)
    again = check_url_staged(
        "https://x.gov.in/old",
        client(status=404),
        tmp_path / "e2",
        UA,
        settings=settings,
        tools=chain,
    )
    assert again.copy_type == got.copy_type and again.archived_on == got.archived_on
    assert Archive.calls == 1


def test_with_the_switch_off_nothing_is_cached_or_reused(tmp_path, settings):
    off = dataclasses.replace(settings, staged_fetch=False)
    run("https://x.gov.in/a", client(), tmp_path, off)
    assert not (tmp_path / "_cache").exists()
    run("https://x.gov.in/a", client(), tmp_path, settings)  # a staged run stores it
    again = client()
    run("https://x.gov.in/a", again, tmp_path, off)
    assert again.log == ["https://x.gov.in/a"]  # the plain check ignores the cache


# -- the cache itself ------------------------------------------------------------------------------
def make_cache(tmp_path, now, days=30):
    return SharedCache(tmp_path / "_cache", days, today=lambda: now[0])


def test_a_live_copy_expires_after_the_setting_and_a_scan_never_does(tmp_path):
    now = [datetime(2026, 11, 1, tzinfo=UTC)]
    cache = make_cache(tmp_path, now)
    cache.store("https://x.gov.in/live", verified_check(tmp_path, "https://x.gov.in/live"))
    cache.store(
        "https://x.gov.in/scan",
        verified_check(tmp_path, "https://x.gov.in/scan", copy_type="read by Claude (scan)"),
        never_expires=True,
    )
    now[0] += timedelta(days=29)
    assert cache.lookup("https://x.gov.in/live", tmp_path / "out") is not None
    now[0] += timedelta(days=2)
    assert cache.lookup("https://x.gov.in/live", tmp_path / "out") is None
    assert cache.lookup("https://x.gov.in/scan", tmp_path / "out") is not None


def test_an_archived_copy_expires_like_a_live_one(tmp_path):
    now = [datetime(2026, 11, 1, tzinfo=UTC)]
    cache = make_cache(tmp_path, now)
    cache.store(
        "https://x.gov.in/old",
        verified_check(tmp_path, "https://x.gov.in/old", copy_type="ARCHIVED 2026-05-01"),
    )
    assert cache.lookup("https://x.gov.in/old", tmp_path / "out").copy_type == "ARCHIVED 2026-05-01"
    now[0] += timedelta(days=31)
    assert cache.lookup("https://x.gov.in/old", tmp_path / "out") is None


def test_zero_days_means_never_reuse(tmp_path):
    cache = make_cache(tmp_path, [datetime(2026, 11, 1, tzinfo=UTC)], days=0)
    cache.store("https://x.gov.in/a", verified_check(tmp_path, "https://x.gov.in/a"))
    assert cache.lookup("https://x.gov.in/a", tmp_path / "out") is None


def test_a_changed_page_keeps_both_versions_and_the_newer_one_wins(tmp_path):
    now = [datetime(2026, 11, 1, tzinfo=UTC)]
    cache = make_cache(tmp_path, now)
    url = "https://x.gov.in/a"
    cache.store(url, verified_check(tmp_path, url, text="old text " * 60))
    now[0] += timedelta(days=1)
    cache.store(url, verified_check(tmp_path, url, text="new text " * 60))
    folder = next((tmp_path / "_cache" / "fetch").iterdir())
    assert len(list(folder.glob("*.txt"))) == 2
    assert "new text" in Path(cache.lookup(url, tmp_path / "out").content_path).read_text()


def test_a_team_saved_copy_a_failed_check_and_a_copy_in_progress_are_never_stored(tmp_path):
    cache = make_cache(tmp_path, [datetime(2026, 11, 1, tzinfo=UTC)])
    for copy_type in ("saved by team", "scan reading in progress"):
        assert not cache.store(
            "https://x.gov.in/a",
            verified_check(tmp_path, "https://x.gov.in/a", copy_type=copy_type),
        )
    failed = verified_check(tmp_path, "https://x.gov.in/a")
    failed.verification_status = "Human Verification Required"
    assert not cache.store("https://x.gov.in/a", failed)
    assert not (tmp_path / "_cache").exists()


def test_an_unreadable_pdf_is_kept_so_it_is_not_downloaded_again(tmp_path):
    now = [datetime(2026, 11, 1, tzinfo=UTC)]
    cache = make_cache(tmp_path, now)
    cache.save_original("https://x.gov.in/s.pdf", b"%PDF-1.4 bytes")
    assert cache.original_fresh("https://x.gov.in/s.pdf") == b"%PDF-1.4 bytes"
    now[0] += timedelta(days=31)
    assert cache.original_fresh("https://x.gov.in/s.pdf") is None
