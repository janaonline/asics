from pathlib import Path

from pydantic import BaseModel, Field

from asics_agent.links.accessibility import check_url
from asics_agent.tools.base import ClientTool, ToolContext, register


class Args(BaseModel):
    url: str = Field(description="The exact URL, as returned by a search or fetch in this task")


def run(ctx: ToolContext, url: str) -> str:
    url = url.strip()
    if url not in ctx.allowed_urls:
        return (
            "Refused: this URL was not returned by a search or fetch in this task. Only "
            "links found by a tool can be checked; never construct or remember URLs."
        )
    settings = ctx.services.settings
    cache = Path(ctx.run.cache_dir) if ctx.run else settings.outputs_dir / "evidence"
    check = check_url(url, ctx.services.http, cache, settings.user_agent)
    text = ""
    if check.content_path:
        text = Path(check.content_path).read_text(encoding="utf-8")[:3000]
    return (
        f"Verdict: {check.verification_status} (accessibility: {check.accessibility}).\n"
        f"Reasons: {' '.join(check.reasons)}\n"
        + (f"Start of readable text:\n{text}" if text else "No readable text.")
    )


TOOL = register(ClientTool(name="check_link", args=Args, run=run))
