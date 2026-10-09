"""The HUMAN ACCESSIBILITY TEST from the source prompt, run in code.

A URL passes only if a plain HTTP GET of the *exact* URL (no rewriting) returns real,
readable page or document content. Anything uncertain becomes
"Human Verification Required" rather than "Verified".

This is an automated approximation of a person opening the link in a browser. Pages
that only render with JavaScript fail it and are routed to human verification.
"""

import hashlib
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
ROBOTS_DEADLINE_SECONDS = 10
MAX_BYTES = 30 * 1024 * 1024  # larger documents are not downloaded in full

_robots_cache: dict[str, RobotFileParser | None] = {}
_origin_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


class FetchTooSlow(httpx.TimeoutException):
    pass


def fetch(client: httpx.Client, url: str, deadline: float, follow_redirects: bool = True):
    """GET with a hard limit on total time and size.

    httpx's own timeout applies per network read, so a server that trickles data slowly
    can otherwise hold a request open indefinitely (this once froze a whole run).
    """
    import time

    start = time.monotonic()
    chunks, size = [], 0
    with client.stream("GET", url, follow_redirects=follow_redirects) as response:
        for chunk in response.iter_bytes():
            chunks.append(chunk)
            size += len(chunk)
            if time.monotonic() - start > deadline:
                raise FetchTooSlow(
                    f"took longer than {deadline:.0f} seconds", request=response.request
                )
            if size > MAX_BYTES:
                break
        return httpx.Response(
            status_code=response.status_code,
            headers=response.headers,
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


def is_india_code(url: str) -> bool:
    return urlsplit(url).netloc.lower().endswith(INDIA_CODE_HOST)


def check_url(url: str, client: httpx.Client, cache_dir: Path, user_agent: str) -> AccessCheck:
    check = AccessCheck(url=url, checked_at=datetime.now(UTC).isoformat(timespec="seconds"))
    reasons = check.reasons

    if not _robots_allows(client, url, user_agent):
        check.verification_status = "Human Verification Required"
        reasons.append("robots.txt disallows automated fetching; a person must open the link.")
        return check

    response = None
    for attempt in (1, 2):  # many government servers drop the first connection
        try:
            response = fetch(client, url, PAGE_DEADLINE_SECONDS)
            break
        except FetchTooSlow as exc:
            reasons.append(f"Could not be opened: the website {exc}.")
            check.verification_status = "Human Verification Required"
            return check
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.RemoteProtocolError) as exc:
            if attempt == 2:
                detail = str(exc).lower()
                why = (
                    "the website's security certificate could not be checked automatically"
                    if "certificate" in detail or "ssl" in detail
                    else f"the connection failed ({type(exc).__name__})"
                )
                reasons.append(
                    f"Could not be opened automatically: {why}. Blocked to automated tools; "
                    "a person must open the link in a browser."
                )
                check.verification_status = "Human Verification Required"
                return check
        except httpx.HTTPError as exc:
            reasons.append(f"Could not be opened: {type(exc).__name__}.")
            return check

    check.status_code = response.status_code
    check.final_url = str(response.url)
    check.content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if response.status_code in BLOCKED_STATUS:
        reasons.append(
            f"HTTP {response.status_code}: the website refused the automated check. Blocked to "
            "automated tools; a person must open the link in a browser."
        )
        check.verification_status = "Human Verification Required"
        return check
    if response.status_code != 200:
        reasons.append(f"HTTP {response.status_code} when opening the exact URL.")
        return check
    if _site(check.final_url) != _site(url):
        reasons.append(f"Redirects to a different site ({check.final_url}).")
        check.verification_status = "Human Verification Required"
        return check
    if any(t in check.content_type for t in METADATA_TYPES):
        reasons.append(f"Returns an API/metadata response ({check.content_type}), not a page.")
        return check

    try:
        if "pdf" in check.content_type or response.content[:5] == b"%PDF-":
            text = pdf_to_text(response.content)
        elif "html" in check.content_type or "text" in check.content_type:
            text = html_to_text(response.text)
        else:
            reasons.append(f"Unsupported content type {check.content_type!r}.")
            check.verification_status = "Human Verification Required"
            return check
    except Exception as exc:  # malformed PDFs/HTML should not stop the run
        reasons.append(f"Content could not be read ({type(exc).__name__}).")
        check.verification_status = "Human Verification Required"
        return check

    check.words = len(text.split())
    lowered = text[:5000].lower()
    if marker := next((m for m in BLOCK_MARKERS if m in lowered), None):
        reasons.append(f"Page appears blocked or gated ({marker!r}).")
        return check
    if is_india_code(url) and (check.words < INDIA_CODE_MIN_WORDS or lowered.count("section") < 3):
        reasons.append(
            "India Code page shows only metadata, not the text of the Act; not human-verified."
        )
        return check
    if check.words < MIN_WORDS:
        reasons.append(
            f"Only {check.words} words of readable content (possibly JavaScript-rendered, "
            "a scanned PDF, or an empty page)."
        )
        check.verification_status = "Human Verification Required"
        return check

    cache_dir.mkdir(parents=True, exist_ok=True)
    stem = hashlib.sha1(url.encode()).hexdigest()[:16]
    path = cache_dir / f"{stem}.txt"
    path.write_text(f"SOURCE URL: {url}\n\n{text}", encoding="utf-8")
    check.content_path = str(path)
    # Keep the page exactly as downloaded, so a reviewer can see what was checked even
    # if the website changes later.
    snapshot = cache_dir / f"{stem}{'.pdf' if 'pdf' in check.content_type else '.html'}"
    snapshot.write_bytes(response.content)
    check.snapshot_path = str(snapshot)
    check.accessibility = "Public"
    check.verification_status = "Verified"
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
