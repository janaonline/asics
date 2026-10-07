"""Tracks which URLs were returned verbatim by a tool in this run.

Source prompt, ABSOLUTE URL RULE 5: "A URL may be written to Excel ONLY if that EXACT
URL was returned verbatim by a tool call in THIS SESSION."

Accepted:
  * URLs in web_search results;
  * URLs that appear verbatim inside the text of a fetched page/document;
  * the URL of a web_fetch result, but only if it was itself already accepted
    (otherwise the model constructed it).
The model's own text and tool *inputs* are never trusted as a URL source.
"""

import re
from collections.abc import Iterable

_URL_IN_TEXT = re.compile(r"https?://[^\s<>\"'\)\]\}]+")


def _walk_urls(node) -> Iterable[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "url" and isinstance(value, str):
                yield value
            else:
                yield from _walk_urls(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_urls(item)


def _walk_text(node) -> Iterable[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in {"data", "text"} and isinstance(value, str):
                yield value
            else:
                yield from _walk_text(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_text(item)


def extract_tool_urls(content_blocks: list, known: set[str]) -> tuple[set[str], list[str]]:
    """Return (accepted URLs, rejected-fetch notes) from one response's content blocks."""
    accepted: set[str] = set()
    fetches: list[dict] = []
    for block in content_blocks:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "web_search_tool_result":
            accepted.update(_walk_urls(block.get("content")))
        elif block.get("type") == "web_fetch_tool_result":
            fetches.append(block)
            for text in _walk_text(block.get("content")):
                accepted.update(u.rstrip(".,;:") for u in _URL_IN_TEXT.findall(text))

    rejected: list[str] = []
    allowed = known | accepted
    for block in fetches:
        content = block.get("content") or {}
        url = content.get("url") if isinstance(content, dict) else None
        if not url:
            continue
        if url in allowed:
            accepted.add(url)
        else:
            rejected.append(f"Fetched URL not previously returned by a tool (constructed?): {url}")
    return accepted, rejected


def extract_fetched_pages(content_blocks: list) -> list[tuple[str, str]]:
    """(url, text) of every page fetched with web_fetch in one response.

    Used for the website trust check: an official government page that links to a
    candidate website is evidence the website is genuine.
    """
    pages = []
    for block in content_blocks:
        if isinstance(block, dict) and block.get("type") == "web_fetch_tool_result":
            content = block.get("content") or {}
            url = content.get("url") if isinstance(content, dict) else None
            text = "\n".join(_walk_text(content))
            if url and text:
                pages.append((url, text))
    return pages
