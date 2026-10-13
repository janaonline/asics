"""Running an agent: Claude with its prompt, memory and tools, returning parsed JSON.

Every call returns the URLs that tools returned verbatim (see links/registry.py), so
downstream code can reject any URL the model wrote from memory or constructed.
"""

import base64
import contextvars
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Annotated, TypedDict, TypeVar

import anthropic
import httpx
import httpx2
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, ValidationError

from asics_agent.agent_setup import (
    MemoryScope,
    load_agent,
    memory_block,
    select_notes,
    system_prompt,
)
from asics_agent.links.registry import extract_fetched_pages, extract_tool_urls
from asics_agent.links.text import pdf_to_text
from asics_agent.run_options import current_options
from asics_agent.services import Services
from asics_agent.tools import ToolContext, build_tools
from asics_agent.usage import BATCH_SUFFIX, METER

MAX_CONTINUATIONS = 4
CACHE = {"cache_control": {"type": "ephemeral"}}  # prompt caching on every model call
NETWORK_RETRY_PAUSES = (2.0, 5.0)  # seconds before each retry of a call whose connection failed
NETWORK_ERRORS = (
    httpx.TransportError,  # timeouts, connection resets (ReadError), protocol errors, ...
    httpx2.TransportError,
    anthropic.APITimeoutError,
    anthropic.APIConnectionError,
)
MAX_FETCHED_PDF_CHARS = 100_000  # text kept from each fetched PDF on later turns
T = TypeVar("T", bound=BaseModel)


class CallFailed(RuntimeError):
    """A model call that couldn't complete. The message is plain language for the team."""


class ModelRefusal(CallFailed):
    pass


class CallTimedOut(CallFailed):
    pass


# Model calls run here so each one can be given a hard time limit (see `_invoke`).
_CALLS = ThreadPoolExecutor(max_workers=32, thread_name_prefix="claude-call")


def _invoke(llm, messages, timeout: float, batched: bool = False, **kwargs):
    """`llm.invoke` with a hard limit on total time.

    A batched call (Step 2, see batch.py) runs in the caller's thread with no time limit: it
    waits for its Message Batch, which can take up to an hour.

    A stalled connection can otherwise block a call (and the run) indefinitely. On timeout
    the call is abandoned and the run carries on without it.

    The SDK retries only the request that opens the stream. A read timeout or dropped
    connection while the reply is streaming comes out raw, so it is retried here and, if
    it keeps failing, turned into a CallFailed that affects only this call.
    """
    deadline = time.monotonic() + timeout
    for pause in NETWORK_RETRY_PAUSES + (None,):
        remaining = deadline - time.monotonic()
        try:
            if batched:
                return llm.invoke(messages, **kwargs)
            future = _CALLS.submit(contextvars.copy_context().run, llm.invoke, messages, **kwargs)
            return future.result(timeout=max(remaining, 0))
        except FuturesTimeout:
            future.cancel()
            raise CallTimedOut(
                f"the research took longer than {timeout / 60:.0f} minutes and was stopped"
            ) from None
        except anthropic.RequestTooLargeError:
            raise CallFailed(
                "the documents it read were too large to send to Claude together"
            ) from None
        except anthropic.BadRequestError as exc:
            raise CallFailed(f"Claude rejected the request ({exc})") from None
        except NETWORK_ERRORS as exc:
            if pause is None or (not batched and deadline - time.monotonic() <= pause):
                raise CallFailed(
                    f"the connection to Claude dropped or stalled ({type(exc).__name__}); "
                    "this usually clears on its own"
                ) from None
            time.sleep(pause)
    raise AssertionError("unreachable")


def _pdf_as_text(source: dict) -> dict:
    """A fetched PDF (base64) as the plain-text source web_fetch uses for web pages."""
    try:
        text = pdf_to_text(base64.b64decode(source.get("data") or ""))
    except Exception:  # malformed PDFs should not stop the call
        text = ""
    if not text:
        text = "(PDF with no readable text, e.g. a scanned document.)"
    elif len(text) > MAX_FETCHED_PDF_CHARS:
        more = len(text) - MAX_FETCHED_PDF_CHARS
        text = f"{text[:MAX_FETCHED_PDF_CHARS]}\n\n[document cut here; {more} more characters]"
    return {"type": "text", "media_type": "text/plain", "data": text}


def _shrink_fetched_pdfs(response: AIMessage) -> AIMessage:
    """Replace PDFs fetched with web_fetch by their text before the turn is sent again.

    web_fetch returns a PDF as the whole file in base64 (its size limit doesn't apply to
    PDFs), and the conversation is re-sent on every later turn, so a few large government
    PDFs once pushed a request over the API's 32 MB limit. Claude has already read the full
    PDF in the turn that fetched it.
    """
    if not isinstance(response.content, list):
        return response
    changed, content = False, []
    for block in response.content:
        result = block.get("content") if isinstance(block, dict) else None
        document = result.get("content") if isinstance(result, dict) else None
        source = document.get("source") if isinstance(document, dict) else None
        if (
            isinstance(block, dict)  # a streamed reply can mix plain strings into the list
            and block.get("type") == "web_fetch_tool_result"
            and isinstance(source, dict)
            and source.get("type") == "base64"
            and source.get("media_type") == "application/pdf"
        ):
            document = {**document, "source": _pdf_as_text(source)}
            block = {**block, "content": {**result, "content": document}}
            changed = True
        content.append(block)
    return response.model_copy(update={"content": content}) if changed else response


_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def parse_json(text: str, schema: type[T]) -> T:
    match = _JSON_OBJECT.search(text or "")
    if not match:
        raise ValueError("no JSON object in the reply")
    return schema.model_validate(json.loads(match.group(0)))


class _LoopState(TypedDict):
    messages: Annotated[list, add_messages]
    tool_calls: int


def _agent_loop(
    llm,
    client_tools: list,
    *,
    timeout: float,
    effort: str,
    max_tool_calls: int,
    on_response,
    batched: bool = False,
):
    """The agent as a LangGraph tool loop:

        model ──(our tool calls)──▶ tools ──▶ model ──(final reply)──▶ end
          ▲ └──(server tools paused the turn)──┘

    Server tools (web search / fetch) run inside the model call; our own tools run in the
    `tools` node (LangGraph's ToolNode). Each step is visible in LangGraph Studio.

    Every tool call in a reply must be answered before the next model call, or the API
    rejects the request. A call to a tool this agent doesn't have, or one whose arguments
    arrived incomplete, is answered with an error message instead of being run.
    """
    names = {t.name for t in client_tools}
    tool_node = ToolNode(client_tools, handle_tool_errors=True) if client_tools else None

    def ours(message) -> list:
        return [c for c in getattr(message, "tool_calls", []) or [] if c["name"] in names]

    def unanswerable(message) -> list[ToolMessage]:
        run = {c["id"] for c in ours(message)}
        blocks = message.content if isinstance(message.content, list) else []
        return [
            ToolMessage(
                "This tool call couldn't be run (unknown tool or incomplete arguments). Don't "
                "call it again; reply with the JSON answer.",
                tool_call_id=b["id"],
                name=b.get("name") or "unknown",
                status="error",
            )
            for b in blocks
            if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("id") not in run
        ]

    def model(state: _LoopState) -> dict:
        # cache_control: automatic prompt caching. Each turn of the tool loop resends the
        # whole conversation; with caching, the part already sent is read from the cache
        # at a tenth of the price.
        response: AIMessage = _invoke(
            llm, state["messages"], timeout, batched, reasoning_effort=effort, **CACHE
        )
        on_response(response)
        response = _shrink_fetched_pdfs(response)
        return {
            "messages": [response],
            "tool_calls": state.get("tool_calls", 0)
            + len(ours(response))
            + len(unanswerable(response)),
        }

    def route(state: _LoopState) -> str:
        last = state["messages"][-1]
        if ours(last) or unanswerable(last):
            return "over_limit" if state["tool_calls"] > max_tool_calls else "tools"
        if last.response_metadata.get("stop_reason") == "pause_turn":
            return "model"  # server tools paused mid-turn; let it continue
        return END

    def tools(state: _LoopState) -> dict:
        last = state["messages"][-1]
        answers = unanswerable(last)
        if calls := ours(last):
            only_ours = last.model_copy(update={"tool_calls": calls})
            answers = tool_node.invoke({"messages": [only_ours]})["messages"] + answers
        return {"messages": answers}

    def over_limit(state: _LoopState) -> dict:
        return {
            "messages": [
                ToolMessage(
                    f"Tool limit reached ({max_tool_calls} calls). Do not call more tools; "
                    "reply now with what you have.",
                    tool_call_id=c["id"],
                    name=c["name"],
                )
                for c in ours(state["messages"][-1])
            ]
            + unanswerable(state["messages"][-1])
        }

    graph = StateGraph(_LoopState)
    graph.add_node("model", model)
    graph.add_node("tools", tools)
    graph.add_node("over_limit", over_limit)
    graph.add_edge("tools", "model")
    graph.add_edge("over_limit", "model")
    graph.add_edge(START, "model")
    graph.add_conditional_edges("model", route, ["model", "tools", "over_limit", END])
    return graph.compile(checkpointer=False, name="agent_tool_loop")


def _without_unfinished_tool_use(messages: list) -> list:
    """Drop a last reply that stopped part-way through a tool call (e.g. it ran out of
    tokens): the API rejects any message after a tool_use that has no tool_result."""
    last = messages[-1] if messages else None
    blocks = last.content if isinstance(last, AIMessage) and isinstance(last.content, list) else []
    if any(isinstance(b, dict) and b.get("type") == "tool_use" for b in blocks):
        return messages[:-1]
    return messages


def call_json(
    services: Services,
    agent: str,
    user: str,
    schema: type[T],
    *,
    scope: MemoryScope | None = None,
    extra_skills: list[str] = (),
    known_urls: set[str] | frozenset[str] = frozenset(),
    pages: list[tuple[str, str]] | None = None,
    tool_context: ToolContext | None = None,
    web_max_uses: int | None = None,
    web_domains: set[str] | frozenset[str] = frozenset(),
) -> tuple[T, set[str], list[str]]:
    """Run one agent (defined in agent_setup/agents/<agent>.md) and parse its JSON reply.

    - Prompt: the agent's shared rules + skills + task prompt; matching team memory goes at
      the top of the message (`scope.used` records which notes).
    - Tools: exactly those listed under the agent's `tools:`. Client tools see only what
      `tool_context` gives them.
    - Model and effort: the agent's own settings, unless the run's RunOptions override them.
    - Web search/fetch limit: the run's option if set, else `web_max_uses` (the caller's), else
      the agent's own `max_uses`. `web_domains` are added to the web tools' allowed_domains.

    Returns (parsed reply, URLs returned verbatim by tools, notes about rejected URLs).
    If `pages` is given, every page fetched with web_fetch is appended to it as (url, text).
    """
    settings = services.settings
    options = current_options()
    root = settings.agent_setup_dir
    config = load_agent(root, agent)

    ctx = tool_context or ToolContext(services=services)
    ctx.allowed_urls |= set(known_urls)
    if options.web_search_max_uses is not None:
        web_max_uses = options.web_search_max_uses
    server_tools, client_tools = build_tools(
        root, config.tools, ctx, web_max_uses=web_max_uses, web_domains=web_domains
    )
    llm = services.llm_for(options.model or config.model)  # a run's choice beats the agent's
    requested = str(getattr(llm, "model", "") or "unknown")
    if server_tools or client_tools:
        llm = llm.bind_tools([*server_tools, *client_tools])

    if scope is not None:
        scope.agent, scope.step = config.name, config.step
        budget = options.memory_max_chars or settings.memory_max_chars
        notes_used, _ = select_notes(root, scope, settings.vertical, budget)
        scope.used = [n.path for n in notes_used]
        if block := memory_block(notes_used):
            user = f"{block}\n\n# TASK INPUT\n{user}"
    rules = getattr(settings, "shared_rules", "shared-rules")
    messages = [
        # The instructions are the same for every call of this agent: cache them too, so
        # every question reuses them (a second cache breakpoint).
        SystemMessage(
            [
                {
                    "type": "text",
                    "text": system_prompt(root, config, list(extra_skills), rules),
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        ),
        HumanMessage(user),
    ]
    urls: set[str] = set()
    notes: list[str] = []

    def on_response(response: AIMessage) -> None:
        served = response.response_metadata.get("model_name") or response.response_metadata.get(
            "model"
        )  # differs from the requested model when a refusal fallback answered
        blocks = response.content if isinstance(response.content, list) else []
        model = f"{served or requested}{BATCH_SUFFIX if response.response_metadata.get('batch') else ''}"
        METER.record(model, config.name, response.usage_metadata, blocks)
        found, rejected = extract_tool_urls(blocks, set(known_urls) | urls)
        urls.update(found)
        ctx.allowed_urls |= found  # check_link may now check these
        notes.extend(rejected)
        if pages is not None:
            pages.extend(extract_fetched_pages(blocks))
        if response.response_metadata.get("stop_reason") == "refusal":
            raise ModelRefusal("the AI declined this request")

    max_calls = options.max_tool_calls or config.max_tool_calls
    loop = _agent_loop(
        llm,
        client_tools,
        timeout=settings.llm_call_timeout,
        effort=options.effort or config.effort,
        max_tool_calls=max_calls,
        on_response=on_response,
        batched=services.batcher is not None,
    )
    limit = {"recursion_limit": 2 * max_calls + 4 * MAX_CONTINUATIONS + 10}
    for attempt in range(2):
        try:
            state = loop.invoke({"messages": messages, "tool_calls": 0}, limit)
        except GraphRecursionError:
            raise CallFailed("the AI kept calling tools without giving an answer") from None
        messages = state["messages"]
        response = messages[-1]
        try:
            return parse_json(response.text, schema), urls, notes
        except (ValueError, ValidationError) as exc:
            if attempt:
                raise
            messages = [
                *_without_unfinished_tool_use(messages),
                HumanMessage(
                    f"Your reply could not be parsed ({exc}). Reply again with only the JSON "
                    f"object matching this schema:\n{json.dumps(schema.model_json_schema())}"
                ),
            ]
    raise AssertionError("unreachable")
