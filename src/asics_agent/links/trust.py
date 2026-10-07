"""Website trust check: is a candidate website really the parastatal's official site?

Every signal is checked in code and explained in plain language, so the research team can
see *why* a website was trusted. Points (capped at 100):

  Government domain (.gov.in / .nic.in)                         +40
  Linked from other official government websites ("backlinks") +20 (one site) / +30 (two+)
  Says it is run by the government / hosted by NIC               +10
  Lists a government email address (…@….gov.in / nic.in)         +10
  Opens properly and shows real content                          +10
  Has Right to Information (RTI) / PIO details                   +5
  Its social media accounts are also linked from a government page  +5
  Name or short name appears in the web address or page title    +5

A known non-official site (Wikipedia, directories, social media, blog hosts) scores 0. A
website that doesn't open scores at most 49, but a gov.in / nic.in address carrying the
parastatal's own name is still rated "Probably official", for a person to confirm.

Bands: 70+ "Official", 50-69 "Probably official" (used, but the team should confirm),
below 50 "Not confirmed" (not used as the official website).
"""

import re
from pathlib import Path
from urllib.parse import urlsplit

from asics_agent.models import AccessCheck, WebsiteCheck

OFFICIAL_SUFFIXES = (".gov.in", ".nic.in")
NOT_OFFICIAL_HOSTS = {
    "wikipedia.org": "an encyclopedia",
    "justdial.com": "a business directory",
    "indiamart.com": "a business directory",
    "facebook.com": "a social media page",
    "twitter.com": "a social media page",
    "x.com": "a social media page",
    "instagram.com": "a social media page",
    "linkedin.com": "a social media page",
    "youtube.com": "a video site",
    "blogspot.com": "a blog",
    "wordpress.com": "a blog",
    "medium.com": "a blog",
    "sites.google.com": "a free website builder",
}
SOCIAL = re.compile(
    r"https?://(?:www\.)?(?:twitter\.com|x\.com|facebook\.com|instagram\.com|youtube\.com)"
    r"/(?:@)?([A-Za-z0-9_.\-]{3,})",
    re.I,
)
GOV_EMAIL = re.compile(r"[\w.+\-]+@(?:[\w\-]+\.)*(?:gov\.in|nic\.in)\b", re.I)
OWNERSHIP = re.compile(
    r"government of [a-z ]+|govt\.? of [a-z ]+|national informatics cent(?:re|er)|"
    r"(?:hosted|designed|developed|maintained) by nic\b|official website of",
    re.I,
)
RTI = re.compile(r"right to information|\bRTI\b|public information officer", re.I)
TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)

OFFICIAL, PROBABLY = 70, 50


def host_of(url: str) -> str:
    host = urlsplit(url).netloc.lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host


def is_official_host(url: str) -> bool:
    return host_of(url).endswith(OFFICIAL_SUFFIXES)


def _not_official(host: str) -> str | None:
    return next(
        (kind for h, kind in NOT_OFFICIAL_HOSTS.items() if host == h or host.endswith("." + h)),
        None,
    )


def _deobfuscate(text: str) -> str:
    """Indian government sites often write emails as name[at]dept[dot]gov[dot]in."""
    return re.sub(
        r"\s*[\[\(]\s*dot\s*[\]\)]\s*",
        ".",
        re.sub(r"\s*[\[\(]\s*at\s*[\]\)]\s*", "@", text, flags=re.I),
        flags=re.I,
    )


def _read(path: str | None) -> str:
    if not path or not Path(path).exists():
        return ""
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def rate_website(
    url: str,
    check: AccessCheck,
    parastatal_id: str,
    parastatal_name: str,
    official_pages: list[tuple[str, str]],
) -> WebsiteCheck:
    """Score one candidate. `official_pages` are (url, text) of pages fetched during
    research; only those on government domains count as backlinks."""
    host = host_of(url)
    result = WebsiteCheck(url=url, opens=check.verification_status == "Verified")
    reasons = result.reasons

    if kind := _not_official(host):
        reasons.append(f"This is {kind}, not an official website (0)")
        return result

    score = 0
    if host.endswith(OFFICIAL_SUFFIXES):
        score += 40
        reasons.append("Government web address (gov.in / nic.in) (+40)")

    linking = sorted(
        {
            host_of(page_url)
            for page_url, text in official_pages
            if is_official_host(page_url) and host_of(page_url) != host and host in text.lower()
        }
    )
    if linking:
        points = 30 if len(linking) > 1 else 20
        score += points
        reasons.append(
            f"Linked from {len(linking)} other government website(s): "
            f"{', '.join(linking[:4])} (+{points})"
        )
    else:
        reasons.append("No other government website seen linking to it (0)")

    html = _read(check.snapshot_path)
    text = _deobfuscate(_read(check.content_path) or html)
    if result.opens:
        score += 10
        reasons.append("Opens properly and shows real content (+10)")
    else:
        reasons.append(
            "Did not open properly in the automatic check: "
            + (" ".join(check.reasons) or "unknown reason")
        )

    if text:
        if OWNERSHIP.search(text):
            score += 10
            reasons.append("Says it is run by the government or hosted by NIC (+10)")
        if email := GOV_EMAIL.search(text):
            score += 10
            reasons.append(f"Lists a government email address ({email.group(0)}) (+10)")
        if RTI.search(text):
            score += 5
            reasons.append("Has Right to Information (RTI) details (+5)")

        handles = {m.group(1).lower() for m in SOCIAL.finditer(html or text)}
        shared = sorted(
            h
            for h in handles
            if any(is_official_host(u) and h in t.lower() for u, t in official_pages)
        )
        if shared:
            score += 5
            reasons.append(
                f"Its social media account ({shared[0]}) is also linked from a government page (+5)"
            )

    title = TITLE.search(html)
    title_text = title.group(1).lower() if title else ""
    words = [
        w
        for w in re.findall(r"[a-z]{4,}", parastatal_name.lower())
        if w not in {"board", "authority", "corporation", "limited", "development"}
    ]
    name_matches = parastatal_id.lower() in host or (
        title_text
        and (parastatal_id.lower() in title_text or sum(w in title_text for w in words) >= 2)
    )
    if name_matches:
        score += 5
        reasons.append("Its name or short name is in the web address or page title (+5)")

    score = min(score, 100)
    if not result.opens:
        score = min(score, PROBABLY - 1)  # a site that doesn't open can't be confirmed
    result.score = score
    result.band = (
        "Official"
        if score >= OFFICIAL
        else "Probably official"
        if score >= PROBABLY
        else "Not confirmed"
    )
    if not result.opens and host.endswith(OFFICIAL_SUFFIXES) and name_matches:
        # Many genuine government sites are slow or need JavaScript, so the automatic check
        # can't open them. A government address carrying the parastatal's own name is still
        # strong evidence; a person confirms it by opening the link.
        result.band = "Probably official"
        reasons.append(
            "Government web address with its own name, but the automatic check "
            "couldn't open it: please open it in your browser to confirm"
        )
    return result


def best_official(checks: list[WebsiteCheck]) -> WebsiteCheck | None:
    usable = [c for c in checks if c.band != "Not confirmed"]
    return max(usable, key=lambda c: c.score) if usable else None
