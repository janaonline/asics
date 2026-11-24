"""The staged fetch: how a link is opened when the plain check cannot open it.

    1. plain HTTP        today's `check_url`, unchanged, always first
    2. retries           the same site again with backoff, and its http/https and www forms
    3. browser render    headless Chromium: JavaScript pages, #/ routes, certificate errors
    4. Wayback Machine   an archived copy, for a 404, a 5xx or a site that cannot be reached

The first stage that gives readable text (the same content checks as the plain check) wins. Every copy
carries a mark of how it was obtained (links/marks.py: "plain HTTP", "browser-rendered", "certificate not
verified", "ARCHIVED <date>") in `AccessCheck.copy_type`, and the reasons that become the row's Notes say
what was tried. Stage 5 (reading a scanned PDF with Claude) belongs to a later part and is not here.

Rules this module keeps:
* robots.txt is honoured before every stage; at most 2 requests at a time per host; the user agent names
  the tool (config.py).
* A certificate that cannot be verified is bypassed ONLY for an official host (the agency's own site, or
  .gov.in / .nic.in), and the copy is marked "certificate not verified".
* An archived copy older than `archive_max_age_days` is not used ("stale archive", Human Verification
  Required). An archived copy may support a positive finding but never a zero, a required source or a
  complete crawl (source_requirements.py reads the mark).
* A URL that failed the whole chain is not tried again for `failure_cache_hours`; the chain has a time cap
  per run (`fetch_time_cap_minutes`), after which links are opened by the plain check only and are
  listed in Needs Attention as "not retried this run".
* With `staged_fetch` off the result is exactly the plain check's.
"""

import json
import re
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from asics_agent.links import marks
from asics_agent.links.accessibility import (
    GOVERNMENT_SUFFIXES,
    FetchTooSlow,
    _robots_allows,
    _site,
    accept_text,
    check_url,
    evaluate_response,
    fetch,
)
from asics_agent.links.browser import Renderer, default_renderer
from asics_agent.links.text import html_to_text, pdf_to_text
from asics_agent.links.wayback import Wayback, age_days
from asics_agent.models import AccessCheck

NOT_RETRIED_NOTE = "Not retried this run"
VARIANT_BUDGET_SECONDS = 75
BACKOFFS = (0, 2, 5)
PER_HOST = 2
# A page that is a challenge or an error page even though it opened: a failure, not a copy.
CHALLENGE = (
    "just a moment", "checking your browser", "attention required", "ddos protection",
    "verify you are human", "cf-chl", "incapsula incident", "request unsuccessful",
    "the requested url was rejected", "pardon our interruption",
)  # fmt: skip
SOFT_404 = (
    "page not found", "404 not found", "error 404", "the page you requested could not be found",
    "page cannot be found", "this page does not exist",
)  # fmt: skip
SOFT_404_MAX_WORDS = 400

# Which plain-check failures each later stage may try (accessibility.FAILURES)
RETRY_KINDS = {"network", "certificate", "http_error", "blocked_status"}
BROWSER_KINDS = {"too_short", "network", "certificate", "blocked_status", "metadata"}
ARCHIVE_KINDS = {"http_error", "network", "certificate", "blocked_status"}


# -- the run's clock, the per-host limit and the failure cache --------------------------------------
class RunClock:
    """The chain's time cap for one run. `begin()` starts a window; a call after a long idle gap starts
    a new one, so a long-lived app process does not carry one run's cap into the next."""

    IDLE_RESTART = 30 * 60

    def __init__(self):
        self._lock = threading.Lock()
        self.started: float | None = None
        self._last = 0.0

    def begin(self) -> None:
        with self._lock:
            self.started = self._last = time.monotonic()

    def expired(self, cap_minutes: float) -> bool:
        if cap_minutes <= 0:
            return False
        with self._lock:
            now = time.monotonic()
            if self.started is None or now - self._last > self.IDLE_RESTART:
                self.started = now
            self._last = now
            return now - self.started > cap_minutes * 60


CLOCK = RunClock()


def begin_run() -> None:
    """Start the time cap for a run (Step 1, Step 2's re-check, a re-check of a workbook)."""
    CLOCK.begin()


_slots: dict[str, threading.BoundedSemaphore] = {}
_slots_guard = threading.Lock()


@contextmanager
def host_slot(url: str):
    """At most PER_HOST requests at a time to one website."""
    host = urlsplit(url).netloc.lower().split(":")[0].removeprefix("www.")
    with _slots_guard:
        slot = _slots.setdefault(host, threading.BoundedSemaphore(PER_HOST))
    with slot:
        yield


def norm_key(url: str) -> str:
    """The same page written differently (scheme, www, trailing slash, tracking, #fragment), except
    a single-page app's #/ route, which is a different page."""
    parts = urlsplit(url.strip())
    query = urlencode(
        sorted((k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith("utm_"))
    )
    route = parts.fragment if parts.fragment.startswith("/") else ""
    host = parts.netloc.lower().removeprefix("www.")
    return (
        f"{host}{parts.path.rstrip('/')}"
        + (f"?{query}" if query else "")
        + (f"#{route}" if route else "")
    )


class FailureCache:
    """URLs that failed the whole chain, so the next run does not spend minutes on them again."""

    def __init__(self, root: Path | None, hours: float):
        self.path = (root / "failures.json") if root else None
        self.hours = hours
        self._lock = threading.Lock()

    def _load(self) -> dict:
        try:
            return json.loads(self.path.read_text()) if self.path and self.path.exists() else {}
        except (OSError, ValueError):
            return {}

    def get(self, url: str) -> dict | None:
        if not self.path or self.hours <= 0:
            return None
        with self._lock:
            entry = self._load().get(norm_key(url))
        if not entry:
            return None
        try:
            when = datetime.fromisoformat(entry["at"])
        except (KeyError, ValueError):
            return None
        return entry if datetime.now(UTC) - when < timedelta(hours=self.hours) else None

    def put(self, url: str, check: AccessCheck) -> None:
        if not self.path or self.hours <= 0:
            return
        with self._lock:
            data = self._load()
            cutoff = datetime.now(UTC) - timedelta(hours=self.hours)
            data = {k: v for k, v in data.items() if _after(v.get("at"), cutoff)}
            data[norm_key(url)] = {
                "at": datetime.now(UTC).isoformat(timespec="seconds"),
                "status": check.verification_status,
                "failure": check.failure,
                "status_code": check.status_code,
                "words": check.words,
                "reasons": check.reasons,
                "stages": check.stages,
                "copy_type": check.copy_type,
                "stale_archive": check.stale_archive,
            }
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(json.dumps(data, indent=1))
            except OSError:
                pass


def _after(stamp, cutoff) -> bool:
    try:
        return datetime.fromisoformat(stamp) > cutoff
    except (TypeError, ValueError):
        return False


# -- what the chain uses (replaceable in tests) -----------------------------------------------------
@dataclass
class ChainTools:
    renderer: Renderer | None = None
    wayback: Wayback | None = None
    unverified_client: Callable[[str], httpx.Client] | None = None
    sleep: Callable[[float], None] = time.sleep
    today: Callable[[], date] = date.today
    cache_root: Path | None = None  # where failures.json lives (default: <outputs root>/_cache)
    _own: dict = field(default_factory=dict, repr=False)

    def get_renderer(self) -> Renderer:
        return self.renderer or default_renderer()

    def get_wayback(self) -> Wayback:
        if self.wayback is not None:
            return self.wayback
        return self._own.setdefault("wayback", Wayback())

    def get_unverified(self, user_agent: str) -> httpx.Client:
        if self.unverified_client is not None:
            return self.unverified_client(user_agent)
        from asics_agent.links.accessibility import BROWSER_USER_AGENT

        if "unverified" not in self._own:
            self._own["unverified"] = httpx.Client(
                timeout=30,
                verify=False,  # only ever used for an official host (see is_official_host)
                headers={"User-Agent": user_agent or BROWSER_USER_AGENT},
            )
        return self._own["unverified"]


_DEFAULT_TOOLS = ChainTools()


def is_official_host(url: str, official_hosts=frozenset()) -> bool:
    """May a certificate that cannot be verified be bypassed for this address?"""
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    own = {h.removeprefix("www.").lower() for h in official_hosts if h}
    return host.endswith(GOVERNMENT_SUFFIXES) or any(
        host == h or host.endswith("." + h) for h in own
    )


def _cache_root(settings) -> Path | None:
    root = getattr(settings, "outputs_root", None) or getattr(settings, "outputs_dir", None)
    return (Path(root) / "_cache") if root else None


# -- helpers ----------------------------------------------------------------------------------------
def _variants(url: str) -> list[str]:
    """The same page at the other scheme and the other www form (never the original)."""
    p = urlsplit(url)
    other_scheme = "http" if p.scheme == "https" else "https"
    host = p.netloc[4:] if p.netloc.startswith("www.") else "www." + p.netloc
    return [
        urlunsplit((other_scheme, p.netloc, p.path, p.query, p.fragment)),
        urlunsplit((p.scheme, host, p.path, p.query, p.fragment)),
        urlunsplit((other_scheme, host, p.path, p.query, p.fragment)),
    ]


def _outcome(check: AccessCheck) -> str:
    """One short phrase for what a stage found (for the "Tried:" sentence)."""
    kind = check.failure
    if kind == "too_short":
        return f"only {check.words} words"
    if kind in ("http_error", "blocked_status"):
        return f"HTTP {check.status_code}"
    if kind == "certificate":
        return "security certificate could not be checked"
    if kind == "network":
        return "no answer from the website"
    if kind == "robots":
        return "robots.txt disallows"
    if kind == "scan":
        return "a scan with no text layer"
    return kind or "did not open"


def _page_problem(text: str) -> str:
    """A challenge page or a soft 404 that content_problem does not catch ('' = fine)."""
    head = text[:3000].lower()
    if any(m in head for m in CHALLENGE):
        return "a challenge page (the site asks the visitor to prove they are human)"
    if len(text.split()) < SOFT_404_MAX_WORDS and any(m in head for m in SOFT_404):
        return "an error page (soft 404)"
    return ""


def _fresh(url: str, checked_at: str) -> AccessCheck:
    return AccessCheck(url=url, checked_at=checked_at)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _verified(check: AccessCheck, copy_type: str, note: str) -> AccessCheck:
    check.copy_type = copy_type
    check.reasons.append(note)
    check.reasons.append(f"Copy type: {copy_type}.")
    return check


# -- the chain --------------------------------------------------------------------------------------
def check_url_staged(
    url: str,
    client: httpx.Client,
    cache_dir: Path,
    user_agent: str,
    official_hosts: frozenset[str] | set[str] = frozenset(),
    *,
    settings=None,
    tools: ChainTools | None = None,
    own_hosts: frozenset[str] | set[str] = frozenset(),
) -> AccessCheck:
    """`check_url` plus the later stages. Same arguments and result type; see the module doc.
    `settings=None` or `staged_fetch` off: exactly `check_url`. `own_hosts`: the agency's own domains from
    its Citation Sheet (common.own_domains); with `official_hosts` and .gov.in / .nic.in they are the
    only hosts whose unverifiable certificate may be bypassed."""
    if settings is None or not getattr(settings, "staged_fetch", False):
        return check_url(url, client, cache_dir, user_agent, official_hosts)
    tools = tools or _DEFAULT_TOOLS
    cap = float(getattr(settings, "fetch_time_cap_minutes", 20))
    hours = float(getattr(settings, "failure_cache_hours", 24))
    max_age = int(getattr(settings, "archive_max_age_days", 365))
    failures = FailureCache(tools.cache_root or _cache_root(settings), hours)

    if (entry := failures.get(url)) is not None:
        return _from_failure_cache(url, entry, hours)

    with host_slot(url):
        check = check_url(url, client, cache_dir, user_agent, official_hosts)
    if check.verification_status == "Verified":
        check.copy_type = marks.PLAIN
        check.stages = [f"plain HTTP: opened, {check.words} words"]
        check.reasons.append(f"Copy type: {marks.PLAIN}.")
        return check

    kind = check.failure
    stages = [f"plain HTTP ({_outcome(check)})"]
    first_reasons = list(check.reasons)
    wanted = {
        "retry": kind in RETRY_KINDS,
        "browser": kind in BROWSER_KINDS,
        "archive": kind in ARCHIVE_KINDS and _archivable(check),
    }
    if not any(wanted.values()):
        check.stages = [*stages, f"later stages: not tried ({_why_not(kind)})"]
        return check
    if CLOCK.expired(cap):
        check.stages = [*stages, "later stages: not run (time cap)"]
        check.not_retried = True
        check.reasons.append(
            f"{NOT_RETRIED_NOTE}: the fetch chain's time cap ({cap:g} minutes) was reached, so the "
            "retry, browser and archive stages were skipped for this link."
        )
        return check

    official = is_official_host(url, {*official_hosts, *own_hosts})
    cert_ok = kind != "certificate" or official
    dns_dead = False

    # 2. retries and address variants
    if wanted["retry"]:
        won, note, dns_dead = _stage_retries(
            url, client, cache_dir, user_agent, official_hosts, official, kind, tools
        )
        if won is not None:
            won.stages = [*stages, note]
            return won
        stages.append(note)
    else:
        stages.append("retries: not needed (the website answered)")

    # 3. browser render
    if wanted["browser"] and not dns_dead:
        won, note, _unavailable = _stage_browser(
            url, client, cache_dir, user_agent, official_hosts, official, kind, cert_ok, tools
        )
        if won is not None:
            won.stages = [*stages, note]
            return won
        stages.append(note)
    elif wanted["browser"]:
        stages.append("browser render: skipped (the address does not resolve)")
    else:
        stages.append("browser render: not tried (an error page looks the same in a browser)")

    # 4. Wayback
    stale = None
    if wanted["archive"]:
        won, note, stale = _stage_archive(url, cache_dir, max_age, tools)
        if won is not None:
            won.stages = [*stages, note]
            return won
        stages.append(note)
    else:
        stages.append("Wayback: not tried (only for a 404, a 5xx or a site that cannot be reached)")

    final = stale or check
    final.reasons = first_reasons if final is check else final.reasons
    final.stages = stages
    final.reasons.append("Tried: " + "; ".join(stages) + ".")
    if stale is None:
        final.copy_type = ""
    failures.put(url, final)
    return final


def _why_not(kind: str) -> str:
    return {
        "robots": "robots.txt does not allow automated access",
        "redirect": "it redirects to a different site; a person decides",
        "scan": "a scanned PDF; see the scan-reading setting",
        "gated": "a login, error or captcha page",
        "unreadable": "the file could not be read",
        "unsupported": "not a page or document",
    }.get(kind, "nothing to retry")


def _archivable(check: AccessCheck) -> bool:
    if check.failure in ("network", "certificate"):
        return True
    code = check.status_code or 0
    return code in (404, 410) or code >= 500


def _from_failure_cache(url: str, entry: dict, hours: float) -> AccessCheck:
    check = AccessCheck(url=url, checked_at=_now())
    check.verification_status = entry.get("status", "Not verified")
    check.failure = entry.get("failure", "")
    check.status_code = entry.get("status_code")
    check.words = int(entry.get("words") or 0)
    check.copy_type = entry.get("copy_type", "")
    check.stale_archive = bool(entry.get("stale_archive"))
    check.stages = list(entry.get("stages", []))
    check.not_retried = True
    check.reasons = [
        f"{NOT_RETRIED_NOTE}: this link failed the whole fetch chain at {entry.get('at', '?')} "
        f"(retry after {hours:g} hours).",
        *entry.get("reasons", []),
    ]
    return check


# -- stage 2 ---------------------------------------------------------------------------------------
def _stage_retries(url, client, cache_dir, user_agent, official_hosts, official, kind, tools):
    """(a verified check or None, a note, dns_dead)."""
    started = time.monotonic()
    last = "no answer"
    candidates = _variants(url)
    errors: list[str] = []
    for round_no, backoff in enumerate(BACKOFFS):
        if backoff:
            tools.sleep(backoff)
        for candidate in candidates if round_no == 0 else [url, *candidates]:
            remaining = VARIANT_BUDGET_SECONDS - (time.monotonic() - started)
            if remaining <= 0:
                return None, f"retries and address variants (time budget used; last: {last})", False
            reply, bypassed, error = _get(
                candidate, client, user_agent, min(remaining, 30), official, tools
            )
            if error:
                errors.append(error.lower())
                # keep the most informative reason: a refusal or a timeout beats "name not known"
                if last == "no answer" or not _is_dns(error) or _is_dns(last):
                    last = error
                continue
            attempt = evaluate_response(_fresh(url, _now()), url, reply, cache_dir, official_hosts)
            if attempt.verification_status == "Verified":
                copy = marks.join(marks.PLAIN, marks.CERT if bypassed else "")
                where = "" if candidate == url else f" at {candidate}"
                return (
                    _verified(
                        attempt,
                        copy,
                        f"Opened{where} on retry (the same site): HTTP 200, {attempt.words} words.",
                    ),
                    f"retries and address variants (opened{where or ' on retry'})",
                    False,
                )
            errors.append("answered")
            last = _outcome(attempt)
    # every attempt failed because the name does not resolve: a browser cannot do better
    dns_dead = bool(errors) and all(_is_dns(e) for e in errors)
    return None, f"retries and address variants ({last})", dns_dead


def _is_dns(error: str) -> bool:
    low = error.lower()
    return any(
        m in low
        for m in ("nodename nor servname", "name or service not known", "errno 8", "getaddrinfo")
    )


def _get(candidate, client, user_agent, deadline, official, tools):
    """(reply, certificate_bypassed, error text). Verified TLS first; unverified only for an official host."""
    for verify in (True, False):
        if not verify and not official:
            break
        http = client if verify else tools.get_unverified(user_agent)
        try:
            with host_slot(candidate):
                reply = fetch(http, candidate, deadline)
            return reply, not verify, ""
        except FetchTooSlow as exc:
            return None, False, f"too slow ({exc})"
        except (
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.RemoteProtocolError,
            httpx.ReadTimeout,
        ) as exc:
            text = str(exc).lower()
            if verify and ("certificate" in text or "ssl" in text):
                continue  # try once without verifying, if the host is official
            return (
                None,
                False,
                f"{type(exc).__name__}: {'certificate' if 'certificate' in text else text[:60]}",
            )
        except httpx.HTTPError as exc:
            return None, False, type(exc).__name__
    return None, False, "certificate could not be verified and this is not an official host"


# -- stage 3 ---------------------------------------------------------------------------------------
def _stage_browser(
    url, client, cache_dir, user_agent, official_hosts, official, kind, cert_ok, tools
):
    """(a verified check or None, a note, unavailable)."""
    name = "browser render (Chromium)"
    if not cert_ok:
        return (
            None,
            f"{name}: skipped (certificate not verified and this is not an official host)",
            False,
        )
    try:
        if not _robots_allows(client, url, user_agent):
            return None, f"{name}: skipped (robots.txt disallows)", False
    except Exception:
        pass
    renderer = tools.get_renderer()
    result = renderer.render(
        url, ignore_cert_errors=(kind == "certificate" and official), user_agent=user_agent
    )
    if result.unavailable:
        return None, f"{name}: {result.error}", True
    if not result.ok:
        return None, f"{name}: {result.error or 'did not open'}", False
    check = _fresh(url, _now())
    check.final_url = result.final_url
    check.status_code = result.status or 200
    check.content_type = result.content_type
    if result.final_url and _site(result.final_url) != _site(url):
        if _site(result.final_url) not in {h.removeprefix("www.") for h in official_hosts}:
            return None, f"{name}: redirected to a different site ({result.final_url})", False
    if result.body:
        try:
            text = pdf_to_text(result.body)
        except Exception as exc:
            return None, f"{name}: the file could not be read ({type(exc).__name__})", False
        body, ext = result.body, ".pdf"
    else:
        text = result.text
        body, ext = result.html.encode("utf-8"), ".html"
    if problem := _page_problem(text):
        return None, f"{name}: {problem}", False
    accept_text(check, url, text, cache_dir, body=body, snapshot_ext=ext)
    if check.verification_status != "Verified":
        return None, f"{name}: {_outcome(check)}", False
    copy = marks.join(marks.BROWSER, marks.CERT if (kind == "certificate" and official) else "")
    return (
        _verified(
            check, copy, f"Opened by a browser render: {check.words} words of readable content."
        ),
        f"{name} (opened, {check.words} words)",
        False,
    )


# -- stage 4 ---------------------------------------------------------------------------------------
def _stage_archive(url, cache_dir, max_age, tools):
    """(a verified check or None, a note, a stale-archive check or None)."""
    name = "Wayback"
    result = tools.get_wayback().fetch(url)
    if not result.ok:
        return None, f"{name}: {result.error}", None
    age = age_days(result.archived_on, tools.today())
    check = _fresh(url, _now())
    check.final_url = result.snapshot_url
    check.status_code = 200
    check.content_type = result.content_type
    check.archived_on = result.archived_on
    if age is not None and age > max_age:
        check.verification_status = "Human Verification Required"
        check.stale_archive = True
        check.failure = "other"
        check.copy_type = marks.join(marks.archived(result.archived_on), marks.STALE)
        check.reasons.append(
            f"Only an archived copy from {result.archived_on} exists, which is {age} days old (the "
            f"limit is {max_age}). It is not used: a person must open the live page."
        )
        return None, f"{name}: only a stale archived copy ({result.archived_on})", check
    try:
        if "pdf" in result.content_type or result.body[:5] == b"%PDF-":
            text, ext = pdf_to_text(result.body), ".pdf"
        else:
            text, ext = html_to_text(result.body.decode("utf-8", errors="replace")), ".html"
    except Exception as exc:
        return None, f"{name}: the archived copy could not be read ({type(exc).__name__})", None
    if problem := _page_problem(text):
        return None, f"{name}: the archived copy is {problem}", None
    accept_text(check, url, text, cache_dir, body=result.body, snapshot_ext=ext)
    if check.verification_status != "Verified":
        return None, f"{name}: {_outcome(check)}", None
    copy = marks.archived(result.archived_on)
    return (
        _verified(
            check,
            copy,
            f"Opened an archived copy from {result.archived_on} (the live page did not open); "
            "check the live page before relying on it.",
        ),
        f"{name} (opened a copy from {result.archived_on}, {check.words} words)",
        None,
    )


def stages_text(check: AccessCheck) -> str:
    """ "plain HTTP (only 0 words); ..." for a message, from the stages the chain recorded."""
    return "; ".join(check.stages)


_TRIED = re.compile(r"Tried: [^\n]*?\.(?=\s|$)")


def tried_in(notes: str) -> str:
    """The "Tried: ..." sentence inside a row's Notes, or ''."""
    m = _TRIED.search(notes or "")
    return m.group(0) if m else ""
