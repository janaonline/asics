"""The HUMAN ACCESSIBILITY TEST from the source prompt, run in code.

A URL passes only if a plain HTTP GET of the *exact* URL (no rewriting) returns real,
readable page or document content. Anything uncertain becomes
"Human Verification Required" rather than "Verified".

This is an automated approximation of a person opening the link in a browser. Pages
that only render with JavaScript fail it and are routed to human verification.
"""

import hashlib
import re
import threading
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from asics_agent.links.text import html_to_text, pdf_to_text
from asics_agent.models import AccessCheck

MIN_WORDS = 150
INDIA_CODE_HOST = "indiacode.nic.in"
GOVERNMENT_SUFFIXES = (".gov.in", ".nic.in")
INDIA_CODE_MIN_WORDS = 800  # Handle pages with only metadata are much shorter than an Act.
BLOCK_MARKERS = (
    "access denied",
    "403 forbidden",
    "captcha",
    "are you a robot",
    "enable javascript to",
    "request blocked",
    "unusual traffic",
)
METADATA_TYPES = ("json", "xml", "rss", "atom")
# Government sites often answer automated requests with these even when a person can open
# the page in a browser. They mean "a person must check", never "the page is missing".
BLOCKED_STATUS = {401, 403, 405, 406, 429, 451, 503}
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0 Safari/537.36"
)

PAGE_DEADLINE_SECONDS = 60  # a whole page or PDF must arrive within this
INDIA_CODE_SECONDS = 120  # India Code's scanned Acts are large and slow: more time, per read too
_BODY_ENCODING_HEADERS = {"content-encoding", "content-length", "transfer-encoding"}
# A PDF with at least this many pages, over half of them empty, is a scan, not a text document.
SCAN_MIN_PAGES = 10
SCAN_EMPTY_SHARE = 0.5
SCAN_EMPTY_WORDS = 10  # a page with fewer words than this counts as empty
ROBOTS_DEADLINE_SECONDS = 10
MAX_BYTES = 30 * 1024 * 1024  # larger documents are not downloaded in full

# Why a check failed (AccessCheck.failure); the staged fetch (fetch_chain.py) decides from this which
# stage to try next. "" = the page opened.
FAILURES = (
    "robots",  # robots.txt disallows: never retried
    "network",  # no connection, timeout, too slow, 5xx-less transport error
    "certificate",  # the website's security certificate could not be checked
    "blocked_status",  # 401/403/405/406/429/451/503: refused the automated check
    "http_error",  # any other non-200 (404, 410, 500 ...): see status_code
    "redirect",  # to a different site: a person decides
    "unsupported",  # a content type that is not a page or document
    "unreadable",  # the file could not be read
    "scan",  # a PDF with no text layer
    "gated",  # a login, error or captcha page
    "metadata",  # an India Code record without the Act's text
    "too_short",  # too few words (often a JavaScript page)
    "other",
)

_robots_cache: dict[str, RobotFileParser | None] = {}
_origin_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


class FetchTooSlow(httpx.TimeoutException):
    pass


def fetch(
    client: httpx.Client,
    url: str,
    deadline: float,
    follow_redirects: bool = True,
    *,
    timeout: float | None = None,
    headers: dict | None = None,
):
    """GET with a hard limit on total time and size.

    httpx's own timeout applies per network read, so a server that trickles data slowly
    can otherwise hold a request open indefinitely (this once froze a whole run).

    `timeout` replaces the client's per-read timeout for this request (India Code is slow);
    `headers` are added to the client's own for this request only.
    """
    import time

    start = time.monotonic()
    chunks, size = [], 0
    options = {} if timeout is None else {"timeout": timeout}
    with client.stream(
        "GET", url, follow_redirects=follow_redirects, headers=headers, **options
    ) as response:
        for chunk in response.iter_bytes():  # already decompressed
            chunks.append(chunk)
            size += len(chunk)
            if time.monotonic() - start > deadline:
                raise FetchTooSlow(
                    f"took longer than {deadline:.0f} seconds", request=response.request
                )
            if size > MAX_BYTES:
                break
        # The body is already decompressed, so the headers that describe the compressed
        # body must not travel with it: httpx would decompress it a second time and fail
        # with "incorrect header check" (DecodingError) on every gzip/deflate reply.
        kept = [
            (k, v)
            for k, v in response.headers.multi_items()
            if k.lower() not in _BODY_ENCODING_HEADERS
        ]
        return httpx.Response(
            status_code=response.status_code,
            headers=kept,
            content=b"".join(chunks),
            request=response.request,
        )


def _robots_allows(client: httpx.Client, url: str, user_agent: str) -> bool:
    parts = urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    with _locks_guard:  # never hold a shared lock during network calls
        lock = _origin_locks.setdefault(origin, threading.Lock())
    with lock:  # one robots.txt request per website; other websites aren't blocked
        if origin not in _robots_cache:
            parser = None
            try:
                response = fetch(
                    client, f"{origin}/robots.txt", ROBOTS_DEADLINE_SECONDS, follow_redirects=False
                )
                if response.status_code == 200:
                    parser = RobotFileParser()
                    parser.parse(response.text.splitlines())
            except httpx.HTTPError:
                pass
            _robots_cache[origin] = parser
        parser = _robots_cache[origin]
    return parser is None or parser.can_fetch(user_agent, url)


def _site(url: str) -> str:
    host = urlsplit(url).netloc.lower().split(":")[0]
    return host.removeprefix("www.")


def site_of(url: str) -> str:
    """The website of a URL: its host name without "www." and the port ("" for no URL)."""
    return _site(url or "")


def is_india_code(url: str) -> bool:
    return urlsplit(url).netloc.lower().endswith(INDIA_CODE_HOST)


def scanned_pdf(text: str) -> tuple[int, int] | None:
    """(empty pages, pages) for a PDF whose text is mostly missing (a scan), else None. Needs the
    "[page N]" markers `pdf_to_text` writes; a web page has none."""
    pages = re.split(r"(?m)^\[page \d+\]$", text)[1:]
    if len(pages) < SCAN_MIN_PAGES:
        return None
    empty = sum(len(p.split()) < SCAN_EMPTY_WORDS for p in pages)
    return (empty, len(pages)) if empty / len(pages) >= SCAN_EMPTY_SHARE else None


def content_problem(url: str, text: str) -> tuple[str | None, str]:
    """What is wrong with a page's readable text, if anything: (problem, detail).

    The problem is "blocked" (a login, error or captcha page; the detail is the marker
    found), "metadata" (an India Code record without the Act's text) or "too_short".
    Used for downloaded pages and for copies the team saved by hand.
    """
    words = len(text.split())
    lowered = text[:5000].lower()
    if marker := next((m for m in BLOCK_MARKERS if m in lowered), None):
        return "blocked", marker
    if is_india_code(url) and (words < INDIA_CODE_MIN_WORDS or lowered.count("section") < 3):
        return "metadata", ""
    if words < MIN_WORDS:
        return "too_short", ""
    return None, ""


def check_url(
    url: str,
    client: httpx.Client,
    cache_dir: Path,
    user_agent: str,
    official_hosts: frozenset[str] | set[str] = frozenset(),
) -> AccessCheck:
    """`official_hosts`: websites already confirmed as this agency's own (host names without
    "www."). A gov.in / nic.in address that redirects to one of them is accepted, with a CONFIRM
    note; a redirect to any other site is still left to a person."""
    check = AccessCheck(url=url, checked_at=datetime.now(UTC).isoformat(timespec="seconds"))
    reasons = check.reasons

    if not _robots_allows(client, url, user_agent):
        check.verification_status = "Human Verification Required"
        check.failure = "robots"
        reasons.append("robots.txt disallows automated fetching; a person must open the link.")
        return check

    india = is_india_code(url)
    deadline = INDIA_CODE_SECONDS if india else PAGE_DEADLINE_SECONDS
    read_timeout = INDIA_CODE_SECONDS if india else None
    headers = None
    response = None
    for attempt in (1, 2):  # many government servers drop the first connection
        try:
            response = fetch(client, url, deadline, timeout=read_timeout, headers=headers)
            break
        except FetchTooSlow as exc:
            reasons.append(f"Could not be opened: the website {exc}.")
            check.verification_status = "Human Verification Required"
            check.failure = "network"
            return check
        except (
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.RemoteProtocolError,
            httpx.ReadTimeout,
        ) as exc:
            if attempt == 2:
                detail = str(exc).lower()
                check.failure = (
                    "certificate" if "certificate" in detail or "ssl" in detail else "network"
                )
                if check.failure == "certificate":
                    why = "the website's security certificate could not be checked automatically"
                elif isinstance(exc, httpx.ReadTimeout):
                    why = "the website was too slow to answer (ReadTimeout)"
                else:
                    why = f"the connection failed ({type(exc).__name__})"
                reasons.append(
                    f"Could not be opened automatically: {why}. Blocked to automated tools; "
                    "a person must open the link in a browser."
                )
                check.verification_status = "Human Verification Required"
                return check
        except httpx.DecodingError as exc:
            # A server that sends a damaged compressed reply: ask once for it uncompressed.
            if attempt == 1:
                headers = {"Accept-Encoding": "identity"}
                continue
            reasons.append(f"Could not be opened: {type(exc).__name__}.")
            check.failure = "other"
            return check
        except httpx.HTTPError as exc:
            reasons.append(f"Could not be opened: {type(exc).__name__}.")
            check.failure = "network"
            return check

    return evaluate_response(check, url, response, cache_dir, official_hosts)


def evaluate_response(
    check: AccessCheck,
    url: str,
    response: httpx.Response,
    cache_dir: Path,
    official_hosts: frozenset[str] | set[str] = frozenset(),
) -> AccessCheck:
    """Judge an HTTP reply to a request for `url` (status, redirect, content type, readable text) and
    save the copy. Shared by the plain check and by the retry stage of the fetch chain."""
    reasons = check.reasons
    check.status_code = response.status_code
    check.final_url = str(response.url)
    check.content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if response.status_code in BLOCKED_STATUS:
        reasons.append(
            f"HTTP {response.status_code}: the website refused the automated check. Blocked to "
            "automated tools; a person must open the link in a browser."
        )
        check.verification_status = "Human Verification Required"
        check.failure = "blocked_status"
        return check
    if response.status_code != 200:
        reasons.append(f"HTTP {response.status_code} when opening the exact URL.")
        check.failure = "http_error"
        return check
    if _site(check.final_url) != _site(url):
        if _site(check.final_url) in official_hosts and _site(url).endswith(GOVERNMENT_SUFFIXES):
            reasons.append(
                f"CONFIRM: this government address redirects to {check.final_url}, which is this "
                "agency's own confirmed official website. Check the redirect is intended."
            )
        else:
            reasons.append(f"Redirects to a different site ({check.final_url}).")
            check.verification_status = "Human Verification Required"
            check.failure = "redirect"
            return check
    if any(t in check.content_type for t in METADATA_TYPES):
        reasons.append(f"Returns an API/metadata response ({check.content_type}), not a page.")
        check.failure = "unsupported"
        return check

    try:
        if "pdf" in check.content_type or response.content[:5] == b"%PDF-":
            text = pdf_to_text(response.content)
        elif "html" in check.content_type or "text" in check.content_type:
            text = html_to_text(response.text)
        else:
            reasons.append(f"Unsupported content type {check.content_type!r}.")
            check.verification_status = "Human Verification Required"
            check.failure = "unsupported"
            return check
    except Exception as exc:  # malformed PDFs/HTML should not stop the run
        reasons.append(f"Content could not be read ({type(exc).__name__}).")
        check.verification_status = "Human Verification Required"
        check.failure = "unreadable"
        return check

    return accept_text(
        check,
        url,
        text,
        cache_dir,
        body=response.content,
        snapshot_ext=".pdf" if "pdf" in check.content_type else ".html",
    )


def accept_text(
    check: AccessCheck,
    url: str,
    text: str,
    cache_dir: Path,
    *,
    body: bytes,
    snapshot_ext: str,
) -> AccessCheck:
    """Apply the content checks to readable `text` obtained for `url` and, if it passes, save the text
    and the copy (`body`, as downloaded or as rendered) under the URL's evidence name. Used for a plain
    reply, a retried reply, a browser render and an archived copy alike."""
    reasons = check.reasons
    check.words = len(text.split())
    if (scan := scanned_pdf(text)) is not None:
        empty, pages = scan
        reasons.append(
            f"{empty} of this PDF's {pages} pages have no readable text, so it is probably a scan. "
            "A person can open it and save a readable copy (see How to Use); it is not used "
            "for answers until then."
        )
        check.verification_status = "Human Verification Required"
        check.failure = "scan"
        return check
    problem, detail = content_problem(url, text)
    if problem == "blocked":
        reasons.append(f"Page appears blocked or gated ({detail!r}).")
        check.failure = "gated"
        return check
    if problem == "metadata":
        reasons.append(
            "India Code page shows only metadata, not the text of the Act; not human-verified."
        )
        check.failure = "metadata"
        return check
    if problem == "too_short":
        reasons.append(
            f"Only {check.words} words of readable content (possibly JavaScript-rendered, "
            "a scanned PDF, or an empty page)."
        )
        check.verification_status = "Human Verification Required"
        check.failure = "too_short"
        return check

    cache_dir.mkdir(parents=True, exist_ok=True)
    stem = hashlib.sha1(url.encode()).hexdigest()[:16]
    path = cache_dir / f"{stem}.txt"
    path.write_text(f"SOURCE URL: {url}\n\n{text}", encoding="utf-8")
    check.content_path = str(path)
    # Keep the page exactly as downloaded, so a reviewer can see what was checked even
    # if the website changes later.
    snapshot = cache_dir / f"{stem}{snapshot_ext}"
    snapshot.write_bytes(body)
    check.snapshot_path = str(snapshot)
    check.accessibility = "Public"
    check.verification_status = "Verified"
    check.failure = ""
    reasons.append(f"Opened the exact URL: HTTP 200, {check.words} words of readable content.")
    return check


def _ssl_context():
    """Use the computer's own certificate store, like a browser does.

    Many Indian government sites send an incomplete certificate chain. Browsers (and the
    macOS/Windows certificate store) fill in the missing piece; Python's bundled list does
    not, so the same link fails only in the automated check. Falls back to the default if
    the optional `truststore` package is not installed.
    """
    try:
        import ssl

        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return True


def make_http_client(user_agent: str, timeout: float) -> httpx.Client:
    return httpx.Client(
        timeout=timeout,
        verify=_ssl_context(),
        headers={
            "User-Agent": user_agent or BROWSER_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-IN,en;q=0.9",
        },
    )
