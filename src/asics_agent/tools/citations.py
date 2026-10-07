"""read_citation and search_citation_sheet: reading the Citation Sheet, and nothing else."""

import re
from pathlib import Path

from pydantic import BaseModel, Field

from asics_agent.links.text import rank_chunks, tokens
from asics_agent.tools.base import ClientTool, ToolContext, register

READ_BUDGET = 12000
_PAGE = re.compile(r"\[page (\d+)\]")


def _text(source) -> str:
    if source.content_path and Path(source.content_path).exists():
        return Path(source.content_path).read_text(encoding="utf-8")
    return ""


def _find(ctx: ToolContext, citation_id: str):
    wanted = citation_id.strip().upper()
    return next((s for s in ctx.citations if s.citation_id.upper() == wanted), None)


class ReadArgs(BaseModel):
    citation_id: str = Field(description="A Citation ID from the Citation Sheet, e.g. BWSSB-07")
    query: str = Field(default="", description="What you are looking for in it (optional)")


def read(ctx: ToolContext, citation_id: str, query: str = "") -> str:
    source = _find(ctx, citation_id)
    if source is None:
        ids = ", ".join(s.citation_id for s in ctx.citations) or "none"
        return f"No Citation Sheet source {citation_id!r}. Available Citation IDs: {ids}."
    text = _text(source)
    if not text:
        return f"{source.citation_id} has no readable saved text."
    if query.strip():
        text, trimmed = rank_chunks(text, query, READ_BUDGET)
    else:
        trimmed, text = len(text) > READ_BUDGET, text[:READ_BUDGET]
    note = "\n[Only the most relevant parts are shown.]" if trimmed else ""
    return f"=== CITATION {source.citation_id}: {source.title} ===\n{text}{note}"


class SearchArgs(BaseModel):
    query: str = Field(description="Words or a phrase to look for")


def search(ctx: ToolContext, query: str, top: int = 6) -> str:
    terms = set(tokens(query))
    if not terms:
        return "Give some words to search for."
    hits = []
    for source in ctx.citations:
        text = _text(source)
        for start in range(0, len(text), 1500):
            chunk = text[start : start + 1500]
            score = len(terms & set(tokens(chunk)))
            if score:
                lowered = chunk.lower()
                first = min((lowered.find(t) for t in terms if t in lowered), default=0)
                pages = _PAGE.findall(text[: start + first])  # the page the match is on
                hits.append((score, source, pages[-1] if pages else None, chunk))
    if not hits:
        return "No Citation Sheet source mentions those words."
    hits.sort(key=lambda h: h[0], reverse=True)
    lines = []
    for _score, source, page, chunk in hits[:top]:
        where = f", page {page}" if page else ""
        snippet = re.sub(r"\s+", " ", chunk)[:300]
        lines.append(f"[{source.citation_id}{where}] {source.title}: …{snippet}…")
    return "\n".join(lines)


register(ClientTool(name="read_citation", args=ReadArgs, run=read))
register(ClientTool(name="search_citation_sheet", args=SearchArgs, run=search))
