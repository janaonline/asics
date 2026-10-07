"""Text extraction and keyword ranking used to pick evidence for the model."""

import io
import re
from collections import Counter
from html.parser import HTMLParser

from pypdf import PdfReader

_WORD = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    "a an and are as be by does for from has have in is it its of on or the to with without "
    "this that shall any other such where which whether there their these those".split()
)


class _TextExtractor(HTMLParser):
    _SKIP = {"script", "style", "noscript", "svg", "head"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in {"h1", "h2", "h3", "h4"}:
            self.parts.append("\n## ")  # heading marker, used to tell reviewers where to look
        elif tag == "a":
            href = dict(attrs).get("href") or ""
            if href.startswith("http"):
                self.parts.append(f" [{href}] ")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag in {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "section"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip_depth:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    text = "".join(parser.parts)
    return re.sub(r"\n\s*\n+", "\n\n", re.sub(r"[ \t]+", " ", text)).strip()


def pdf_to_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n\n".join(
        f"[page {i}]\n{page.extract_text() or ''}" for i, page in enumerate(reader.pages, 1)
    ).strip()


def tokens(text: str) -> list[str]:
    return [t for t in _WORD.findall(text.lower()) if t not in _STOPWORDS and len(t) > 2]


def rank_chunks(
    text: str, query: str, budget_chars: int, chunk_chars: int = 3000
) -> tuple[str, bool]:
    """Return the chunks of `text` most relevant to `query`, in document order.

    The second value is True when the text was cut down to fit the budget, so callers
    can say so in the Notes instead of truncating silently.
    """
    if len(text) <= budget_chars:
        return text, False
    chunks = [text[i : i + chunk_chars] for i in range(0, len(text), chunk_chars)]
    terms = Counter(tokens(query))
    scores = []
    for index, chunk in enumerate(chunks):
        counts = Counter(tokens(chunk))
        scores.append((sum(min(n, counts[t]) for t, n in terms.items()), index))
    keep = sorted(i for _, i in sorted(scores, reverse=True)[: max(1, budget_chars // chunk_chars)])
    return "\n[...]\n".join(chunks[i] for i in keep), True


_PAGE = re.compile(r"^\[page (\d+)\]$")


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def locate_quote(text: str, quote: str) -> tuple[int | None, str | None]:
    """Return (PDF page number, nearest heading) for where `quote` appears in `text`.

    Works on text produced by `pdf_to_text` ("[page N]" markers) or `html_to_text`
    ("## " heading markers). Returns (None, None) if the quote is not found.
    """
    target = _squash(quote)
    if not target:
        return None, None
    flat, page, heading = "", None, None
    markers: list[tuple[int, int | None, str | None]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if match := _PAGE.match(stripped):
            page = int(match.group(1))
        elif stripped.startswith("## "):
            heading = stripped[3:].strip() or heading
        markers.append((len(flat), page, heading))
        flat += _squash(line) + " "
    position = flat.find(target)
    if position < 0:
        return None, None
    found_page, found_heading = None, None
    for start, marker_page, marker_heading in markers:
        if start > position:
            break
        found_page, found_heading = marker_page, marker_heading
    return found_page, found_heading


def search_phrase(quote: str, words: int = 8) -> str:
    """A short, distinctive run of words from the quote for Ctrl+F / Cmd+F."""
    parts = quote.split()
    return " ".join(parts[:words]).strip(" .,;:")


def relevance(text: str, query: str) -> float:
    """How strongly `text` matches `query` (share of query words it contains)."""
    terms = set(tokens(query))
    if not terms:
        return 0.0
    return len(terms & set(tokens(text))) / len(terms)
