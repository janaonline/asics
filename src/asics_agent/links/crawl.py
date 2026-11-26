"""A same-site crawl of an agency's own official website, one level deep.

Step 1 reads the saved home page of an agency whose official website is confirmed, takes the menu
and navigation links that stay on the same site, and lets the normal link check and source assessor
open them. The pages become Citation Sheet rows tagged [WEB]. Nothing is read from any scoring file:
the only input is the agency's own home page.

A crawl is COMPLETE only when every menu link found (same site, after the filters below) fits in the
page cap and every one of them was opened and saved. An incomplete crawl, or none, can never show
that something is missing from a website, so the gate (source_requirements.check) allows no zero for a
website question without a complete one. Links are ranked by topic first, so a cut by the cap keeps
the most relevant pages.

This module is plain code (no model call, no network): it extracts and ranks links and builds the
note that records the result. The opening of the pages is the job of agents/links_builder.py.
"""

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlsplit

from asics_agent.links.accessibility import site_of

# What a link's words or path must contain to rank first (a page a question may need)
TOPIC = re.compile(
    r"budget|account|financ|annual[- ]?report|report|tender|procure|rti|right[- ]to[- ]information|"
    r"grievance|complaint|charter|citizen|about|board|director|minutes|meeting|act\b|rules?\b|"
    r"regulation|notification|order|policy|plan|publication|download|document|scheme|project|"
    r"service|tariff|fare|staff|organi[sz]ation|contact|audit|benchmark",
    re.I,
)
# Words that mark a link as not a page of the site's content
SKIP_TEXT = re.compile(
    r"log ?in|sign ?in|register|search|skip to|screen reader|font size|contrast|"
    r"^\s*(a\+|a-|a|home|ok|top)\s*$|language|हिंदी|english|facebook|twitter|youtube|instagram",
    re.I,
)
SKIP_QUERY = re.compile(r"(^|&)(lang|language|theme|fontsize|contrast|print)=", re.I)
SKIP_EXT = (
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".ico", ".css", ".js", ".zip", ".rar", ".mp3",
    ".mp4", ".xls", ".xlsx", ".doc", ".docx", ".ppt", ".pptx", ".xml", ".json",
)  # fmt: skip
VOID = {"br", "img", "input", "meta", "link", "hr", "area", "base", "col", "embed", "source", "wbr"}
MENU_TAGS = {"nav", "header", "footer"}
MENU_WORDS = re.compile(r"menu|nav|dropdown|topbar|mega", re.I)
CRAWL_PAGE_TAG = "WEB"


@dataclass
class Link:
    url: str
    text: str
    in_menu: bool
    order: int
    topic: bool = False


class _Links(HTMLParser):
    """Every <a href> with its text, and whether it sits inside a navigation block."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str, bool]] = []
        self._stack: list[tuple[str, bool]] = []
        self._open: list[str] | None = None
        self._href = ""
        self._menu = False

    def _in_menu(self) -> bool:
        return any(is_menu for _, is_menu in self._stack)

    def handle_starttag(self, tag, attrs):
        if tag in VOID:
            return
        a = dict(attrs)
        is_menu = tag in MENU_TAGS or bool(
            MENU_WORDS.search(f"{a.get('class') or ''} {a.get('id') or ''}")
            or a.get("role") == "navigation"
        )
        self._stack.append((tag, is_menu))
        if tag == "a" and a.get("href"):
            self._open, self._href, self._menu = [], a["href"], self._in_menu()

    def handle_endtag(self, tag):
        if tag == "a" and self._open is not None:
            text = re.sub(r"\s+", " ", "".join(self._open)).strip()
            self.links.append((self._href, text, self._menu))
            self._open = None
        for i in range(len(self._stack) - 1, -1, -1):  # close the nearest matching tag
            if self._stack[i][0] == tag:
                del self._stack[i:]
                break

    def handle_data(self, data):
        if self._open is not None:
            self._open.append(data)


def _normal(url: str) -> str:
    return urldefrag(url)[0].rstrip("/").lower()


def extract_links(html: str, home_url: str) -> list[Link]:
    """The same-site page and PDF links of a home page, in page order, with the menu flag.

    Dropped: other sites, mailto/tel/javascript, fragments only, language and view switches,
    images and other files, login/search style links, the home page itself, and duplicates."""
    parser = _Links()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # a broken page gives the links read so far
        pass
    site, home = site_of(home_url), _normal(home_url)
    seen, out = set(), []
    for href, text, menu in parser.links:
        href = href.strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
            continue
        url = urldefrag(urljoin(home_url, href))[0]
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or site_of(url) != site:
            continue
        if parts.path.lower().endswith(SKIP_EXT) or SKIP_QUERY.search(parts.query):
            continue
        if SKIP_TEXT.search(text) or _normal(url) in (home, ""):
            continue
        if parts.path in ("", "/") and not parts.query:
            continue  # the home page again, however it is spelt
        key = _normal(url)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            Link(
                url=url,
                text=text[:120],
                in_menu=menu,
                order=len(out),
                topic=bool(TOPIC.search(f"{text} {parts.path}")),
            )
        )
    return out


@dataclass
class CrawlPlan:
    selected: list[Link] = field(default_factory=list)  # the menu links to open, best first
    menu_links: int = 0  # menu links found (same site, after the filters)
    cap: int = 0
    reason: str = ""  # why it cannot be complete ("" when the cap and the links allow it)

    @property
    def possible(self) -> bool:
        """Can the crawl be complete at all: menu links exist and all of them fit in the cap?"""
        return not self.reason


def plan_crawl(html: str, home_url: str, cap: int) -> CrawlPlan:
    """Choose the pages to open. Only menu links count. Topic words rank first, then page order, so
    a cut by the cap keeps the most relevant pages."""
    menu = [link for link in extract_links(html, home_url) if link.in_menu]
    plan = CrawlPlan(menu_links=len(menu), cap=cap)
    ranked = sorted(menu, key=lambda link: (not link.topic, link.order))
    plan.selected = ranked[: max(cap, 0)]
    if not menu:
        plan.reason = (
            "no menu links in the saved home page (a menu drawn by JavaScript, or one the page "
            "does not mark as navigation)"
        )
    elif len(menu) > cap:
        plan.reason = f"{len(menu)} menu links found, more than the cap of {cap}"
    return plan


def crawl_note(
    plan: CrawlPlan,
    captured: int,
    failed: list[str] | None = None,
    ignored: list[str] | None = None,
) -> str:
    """The text written in the Notes of the home page row, which the gate reads
    (source_requirements.crawl_status): complete only when the plan was possible and every
    selected link was captured. `failed`: links that did not open and count against the crawl.
    `ignored`: dead links the lenient setting set aside (no topic word in their text or address)."""
    failed, ignored = failed or [], ignored or []
    if (
        plan.possible
        and not failed
        and captured > 0
        and captured + len(ignored) >= len(plan.selected)
    ):
        lenient = (
            f" (lenient: {len(ignored)} dead link(s) without a topic word ignored)"
            if ignored
            else ""
        )
        return (
            f"SITE-CRAWL: complete, {captured} of {plan.menu_links} menu links captured{lenient}."
        )
    why = plan.reason or (
        f"{len(failed)} of {len(plan.selected)} menu links did not open ({', '.join(failed[:4])})"
        if failed
        else "no menu link was captured"
    )
    return (
        f"SITE-CRAWL: incomplete, {captured} of {plan.menu_links} menu links captured (cap "
        f"{plan.cap}): {why}."
    )
