"""Tool registry and the per-call context client tools work with."""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from asics_agent.agent_setup import split_front_matter
from asics_agent.models import Question, RunContext, Source

# Anthropic-hosted tools: name -> API tool type.
SERVER_TOOLS = {"web_search": "web_search_20260209", "web_fetch": "web_fetch_20260209"}
SERVER_OPTIONS = {"max_uses", "allowed_domains", "blocked_domains"}


@dataclass
class ToolContext:
    """What client tools may see during one agent call. Anything not here is out of reach:
    e.g. read_citation can only read `citations`, check_link only `allowed_urls`."""

    services: object
    run: RunContext | None = None
    citations: list[Source] = field(default_factory=list)
    questions: dict[str, Question] = field(default_factory=dict)
    allowed_urls: set[str] = field(default_factory=set)  # returned verbatim by tools so far
    progress_key: str | None = None
    log: list[str] = field(default_factory=list)  # one line per tool call, for the audit trail


@dataclass(frozen=True)
class ClientTool:
    name: str
    args: type[BaseModel]
    run: Callable[..., str]  # run(ctx, **args) -> text for the model


CLIENT_TOOLS: dict[str, ClientTool] = {}


def register(tool: ClientTool) -> ClientTool:
    CLIENT_TOOLS[tool.name] = tool
    return tool


def tool_description(root: Path, name: str) -> tuple[dict, str]:
    path = root / "tools" / f"{name}.md"
    if not path.exists():
        return {}, ""
    return split_front_matter(path.read_text(encoding="utf-8"))


def build_tools(root: Path, settings: dict, ctx: ToolContext, web_max_uses: int | None = None):
    """(server tool dicts, LangChain client tools) for an agent's `tools:` settings."""
    server, client = [], []
    for name, options in (settings or {}).items():
        options = dict(options or {})
        meta, _ = tool_description(root, name)
        if name in SERVER_TOOLS:
            spec = {
                "type": SERVER_TOOLS[name],
                "name": name,
                **(meta.get("defaults") or {}),
                **options,
            }
            if web_max_uses is not None:
                spec["max_uses"] = web_max_uses
            if name == "web_search":
                spec.setdefault("user_location", {"type": "approximate", "country": "IN"})
            server.append(spec)
        elif name in CLIENT_TOOLS:
            client.append(_as_langchain(root, CLIENT_TOOLS[name], ctx))
    return server, client


def _as_langchain(root: Path, tool: ClientTool, ctx: ToolContext) -> StructuredTool:
    _, description = tool_description(root, tool.name)

    def call(**kwargs) -> str:
        from asics_agent.progress import report

        shown = ", ".join(f"{k}={v!r}" for k, v in kwargs.items())
        ctx.log.append(f"{tool.name}({shown})")
        if ctx.progress_key:
            report(ctx.progress_key, f"Using tool {tool.name}: {shown[:80]}")
        return tool.run(ctx, **kwargs)

    return StructuredTool.from_function(
        func=call,
        name=tool.name,
        description=description.strip() or tool.name,
        args_schema=tool.args,
    )
