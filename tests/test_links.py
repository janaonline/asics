import pytest

from asics_agent.links.accessibility import check_url
from asics_agent.links.registry import extract_tool_urls
from asics_agent.practice import INDIA_CODE, PLAN, SITE, fake_http

UA = "test-agent"


def test_human_accessible_page_is_verified(tmp_path):
    check = check_url(SITE, fake_http(), tmp_path, UA)
    assert check.verification_status == "Verified"
    assert check.accessibility == "Public"


def test_india_code_metadata_page_is_not_verified(tmp_path):
    check = check_url(INDIA_CODE, fake_http(), tmp_path, UA)
    assert check.verification_status == "Not verified"
    assert "India Code" in " ".join(check.reasons)


def test_missing_page_is_not_verified(tmp_path):
    check = check_url(SITE + "missing", fake_http(), tmp_path, UA)
    assert check.verification_status == "Not verified"
    assert check.status_code == 404


def test_registry_accepts_search_results_and_rejects_constructed_fetches():
    blocks = [
        {"type": "server_tool_use", "input": {"url": "https://guessed.gov.in/"}},
        {"type": "web_search_tool_result", "content": [{"url": SITE}]},
        {
            "type": "web_fetch_tool_result",
            "content": {"url": SITE, "content": {"source": {"data": f"see {PLAN} for the plan."}}},
        },
        {"type": "web_fetch_tool_result", "content": {"url": "https://guessed.gov.in/"}},
    ]
    accepted, rejected = extract_tool_urls(blocks, known=set())
    assert accepted == {SITE, PLAN}
    assert rejected and "guessed.gov.in" in rejected[0]


def test_a_slow_website_cannot_hold_up_the_run(tmp_path, monkeypatch):
    import time

    import httpx

    from asics_agent.links import accessibility

    monkeypatch.setattr(accessibility, "PAGE_DEADLINE_SECONDS", 0.3)

    def trickle():
        for _ in range(50):  # each piece arrives quickly, but the page never finishes
            time.sleep(0.05)
            yield b"<p>word </p>"

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, headers={"content-type": "text/html"}, content=trickle())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    started = time.monotonic()
    check = check_url("https://slow.example.gov.in/", client, tmp_path, UA)
    assert time.monotonic() - started < 2
    assert check.verification_status == "Human Verification Required"
    assert "took longer than" in " ".join(check.reasons)


def test_a_stalled_model_call_is_stopped(monkeypatch):
    import dataclasses
    import time

    import pytest
    from pydantic import BaseModel

    from asics_agent.config import get_settings
    from asics_agent.llm import CallTimedOut, call_json
    from asics_agent.practice import FakeClaude, fake_http
    from asics_agent.services import Services

    class Stalled(FakeClaude):
        def _generate(self, *args, **kwargs):
            time.sleep(5)

    class Reply(BaseModel):
        ok: bool = True

    settings = dataclasses.replace(get_settings(), llm_call_timeout=0.2)
    services = Services(llm=Stalled(), http=fake_http(), settings=settings)
    with pytest.raises(CallTimedOut):
        call_json(services, "source-assessor", "x", Reply)


def _client(handler):
    import httpx

    def wrapped(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return handler(request)

    return httpx.Client(transport=httpx.MockTransport(wrapped))


def test_site_that_refuses_bots_goes_to_a_person(tmp_path):
    import httpx

    check = check_url(
        "https://agency.karnataka.gov.in/page",
        _client(lambda r: httpx.Response(403, text="Forbidden")),
        tmp_path,
        UA,
    )
    assert check.verification_status == "Human Verification Required"
    assert "Blocked to automated tools" in " ".join(check.reasons)


def test_www_redirect_on_the_same_site_is_not_a_different_site(tmp_path):
    import httpx

    body = "<html><body>" + "<p>Water supply and sewerage board annual report</p>" * 40
    body += "</body></html>"

    def handler(request):
        if request.url.host == "agency.gujarat.gov.in":
            return httpx.Response(301, headers={"location": "https://www.agency.gujarat.gov.in/"})
        return httpx.Response(200, headers={"content-type": "text/html"}, text=body)

    check = check_url("https://agency.gujarat.gov.in/", _client(handler), tmp_path, UA)
    assert check.verification_status == "Verified"


def test_connection_failure_is_retried_then_sent_to_a_person(tmp_path):
    import httpx

    calls = []

    def handler(request):
        calls.append(request.url)
        raise httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer")

    check = check_url("https://agency.gov.in/doc.pdf", _client(handler), tmp_path, UA)
    assert len(calls) == 2
    assert check.verification_status == "Human Verification Required"
    assert "certificate" in " ".join(check.reasons)


# -- compressed replies, redirects, timeouts and scans (TS-1337) ---------------------------------
PAGE = "<html><body>" + "<p>Water supply and sewerage board annual report for the year</p>" * 40
PAGE += "</body></html>"


@pytest.fixture
def local_site():
    """A real HTTP server on this computer that sends compressed replies, like government sites."""
    import gzip
    import http.server
    import threading
    import zlib

    body = PAGE.encode()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            accepted = self.headers.get("Accept-Encoding", "")
            path = self.path
            if path == "/robots.txt":
                self.send_response(404)
                self.end_headers()
                return
            data, encoding = body, None
            if path == "/gzip":
                data, encoding = gzip.compress(body), "gzip"
            elif path == "/deflate":
                data, encoding = zlib.compress(body), "deflate"
            elif path == "/damaged" and "identity" not in accepted:
                data, encoding = (
                    b"this is not gzip data at all",
                    "gzip",
                )  # damaged unless asked plain
            elif path == "/always-damaged":
                data, encoding = b"this is not gzip data at all", "gzip"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            if encoding:
                self.send_header("Content-Encoding", encoding)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.mark.parametrize("path", ["/gzip", "/deflate", "/plain"])
def test_a_compressed_page_opens_instead_of_failing_with_a_decoding_error(
    local_site, tmp_path, path
):
    from asics_agent.links.accessibility import make_http_client

    check = check_url(local_site + path, make_http_client(UA, 10), tmp_path, UA)
    assert check.verification_status == "Verified", check.reasons
    assert check.words > 150


def test_fetch_returns_the_text_once_without_the_compression_headers(local_site):
    from asics_agent.links.accessibility import fetch, make_http_client

    response = fetch(make_http_client(UA, 10), local_site + "/gzip", 10)
    assert response.text == PAGE
    assert "content-encoding" not in response.headers


def test_a_damaged_compressed_reply_is_asked_for_again_uncompressed(local_site, tmp_path):
    from asics_agent.links.accessibility import make_http_client

    check = check_url(local_site + "/damaged", make_http_client(UA, 10), tmp_path, UA)
    assert check.verification_status == "Verified", check.reasons


def test_a_reply_that_stays_damaged_is_reported_not_verified(local_site, tmp_path):
    from asics_agent.links.accessibility import make_http_client

    check = check_url(local_site + "/always-damaged", make_http_client(UA, 10), tmp_path, UA)
    assert check.verification_status == "Not verified"
    assert "DecodingError" in " ".join(check.reasons)


def _redirecting_client(final_host: str):
    import httpx

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.host == "kbda.karnataka.gov.in":
            return httpx.Response(301, headers={"location": f"https://{final_host}/"})
        return httpx.Response(200, headers={"content-type": "text/html"}, text=PAGE)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_a_gov_in_alias_that_redirects_to_the_confirmed_official_site_is_accepted(tmp_path):
    url = "https://kbda.karnataka.gov.in/"
    check = check_url(
        url, _redirecting_client("bdakarnataka.in"), tmp_path, UA, {"bdakarnataka.in"}
    )
    assert check.verification_status == "Verified"
    assert "CONFIRM" in " ".join(check.reasons)
    assert "bdakarnataka.in" in " ".join(check.reasons)


def test_a_redirect_to_any_other_site_is_still_left_to_a_person(tmp_path):
    url = "https://kbda.karnataka.gov.in/"
    # no confirmed website, or a different one
    for hosts in (frozenset(), {"somewhere-else.in"}):
        check = check_url(url, _redirecting_client("bdakarnataka.in"), tmp_path, UA, hosts)
        assert check.verification_status == "Human Verification Required"
        assert "Redirects to a different site" in " ".join(check.reasons)


def test_only_a_government_address_may_redirect_to_the_official_site(tmp_path):
    import httpx

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.host == "old-agency.example.com":
            return httpx.Response(301, headers={"location": "https://agency.in/"})
        return httpx.Response(200, headers={"content-type": "text/html"}, text=PAGE)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    check = check_url("https://old-agency.example.com/", client, tmp_path, UA, {"agency.in"})
    assert check.verification_status == "Human Verification Required"


def test_a_read_timeout_is_tried_once_more(tmp_path):
    import httpx

    calls = []

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(200, headers={"content-type": "text/html"}, text=PAGE)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert check_url("https://slow.example.gov.in/", client, tmp_path, UA).verification_status == (
        "Verified"
    )
    assert len(calls) == 2


def test_a_read_timeout_twice_goes_to_a_person_with_a_plain_reason(tmp_path):
    import httpx

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        raise httpx.ReadTimeout("slow", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    check = check_url("https://slow.example.gov.in/", client, tmp_path, UA)
    assert check.verification_status == "Human Verification Required"
    assert "too slow to answer" in " ".join(check.reasons)


def test_india_code_gets_more_time_than_other_sites(tmp_path, monkeypatch):
    import httpx

    from asics_agent.links import accessibility

    seen = {}

    def spy(client, url, deadline, follow_redirects=True, *, timeout=None, headers=None):
        seen[url] = (deadline, timeout)
        raise httpx.ConnectError("stop here")

    monkeypatch.setattr(accessibility, "fetch", spy)
    monkeypatch.setattr(accessibility, "_robots_allows", lambda *a: True)
    client = httpx.Client()
    check_url("https://www.indiacode.nic.in/bitstream/1/2/act.pdf", client, tmp_path, UA)
    check_url("https://agency.gov.in/page", client, tmp_path, UA)
    assert seen["https://www.indiacode.nic.in/bitstream/1/2/act.pdf"] == (120, 120)
    assert seen["https://agency.gov.in/page"] == (accessibility.PAGE_DEADLINE_SECONDS, None)


def test_a_pdf_with_mostly_empty_pages_is_flagged_as_a_scan(tmp_path, monkeypatch):
    import httpx

    from asics_agent.links import accessibility
    from asics_agent.links.accessibility import scanned_pdf

    readable = "\n\n".join(f"[page {i}]\n" + "word " * 60 for i in range(1, 4))
    empty = "\n\n".join(f"[page {i}]\n" for i in range(4, 15))
    assert scanned_pdf(readable + "\n\n" + empty) == (11, 14)
    assert scanned_pdf(readable) is None  # too few pages to call it a scan
    assert scanned_pdf("\n\n".join(f"[page {i}]\n" + "word " * 60 for i in range(1, 20))) is None
    assert scanned_pdf("a web page with no page markers " * 100) is None

    monkeypatch.setattr(accessibility, "pdf_to_text", lambda data: readable + "\n\n" + empty)

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF-1.4")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    check = check_url("https://agency.gov.in/act.pdf", client, tmp_path, UA)
    assert check.verification_status == "Human Verification Required"
    assert "11 of this PDF's 14 pages have no readable text" in " ".join(check.reasons)
    assert not check.content_path


def test_site_of_gives_the_host_without_www_and_port():
    from asics_agent.links.accessibility import site_of

    assert site_of("https://www.BDA.gov.in:8443/x") == "bda.gov.in"
    assert site_of("") == ""
