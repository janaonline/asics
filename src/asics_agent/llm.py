"""Running an agent: Claude with its prompt, memory and tools, returning parsed JSON.

Every call returns the URLs that tools returned verbatim (see links/registry.py), so
downstream code can reject any URL the model wrote from memory or constructed.
"""

import contextvars
import json
import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Annotated, TypedDict, TypeVar

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
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
from asics_agent.run_options import current_options
from asics_agent.services import Services
from asics_agent.tools import ToolContext, build_tools

MAX_CONTINUATIONS = 4
T = TypeVar("T", bound=BaseModel)


class CallFailed(RuntimeError):
    """A model call that couldn't complete. The message is plain language for the team."""


class ModelRefusal(CallFailed):
    pass


class CallTimedOut(CallFailed):
    pass


# Model calls run here so each one can be given a hard time limit (see `_invoke`).
_CALLS = ThreadPoolExecutor(max_workers=32, thread_name_prefix="claude-call")


def _invoke(llm, messages, timeout: float, **kwargs):
    """`llm.invoke` with a hard limit on total time.

    A stalled connection can otherwise block a call (and the run) indefinitely. On timeout
    the call is abandoned and the run carries on without it.
    """
    future = _CALLS.submit(contextvars.copy_context().run, llm.invoke, messages, **kwargs)
    try:
        return future.result(timeout=timeout)
    except FuturesTimeout:
        future.cancel()
        raise CallTimedOut(
            f"the research took longer than {timeout / 60:.0f} minutes and was stopped"
        ) from None


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
    llm, client_tools: list, *, timeout: float, effort: str, max_tool_calls: int, on_response
):
    """The agent as a LangGraph tool loop:

        model ──(our tool calls)──▶ tools ──▶ model ──(final reply)──▶ end
          ▲ └──(server tools paused the turn)──┘

    Server tools (web search / fetch) run inside the model call; our own tools run in the
    `tools` node (LangGraph's ToolNode). Each step is visible in LangGraph Studio.
    """
    names = {t.name for t in client_tools}
    tool_node = ToolNode(client_tools, handle_tool_errors=True) if client_tools else None

    def ours(message) -> list:
        return [c for c in getattr(message, "tool_calls", []) or [] if c["name"] in names]

    def model(state: _LoopState) -> dict:
        response: AIMessage = _invoke(llm, state["messages"], timeout, reasoning_effort=effort)
        on_response(response)
        return {
            "messages": [response],
            "tool_calls": state.get("tool_calls", 0) + len(ours(response)),
        }

    def route(state: _LoopState) -> str:
        last = state["messages"][-1]
        if ours(last):
            return "over_limit" if state["tool_calls"] > max_tool_calls else "tools"
        if last.response_metadata.get("stop_reason") == "pause_turn":
            return "model"  # server tools paused mid-turn; let it continue
        return END

    def tools(state: _LoopState) -> dict:
        last = state["messages"][-1]
        only_ours = last.model_copy(update={"tool_calls": ours(last)})
        return tool_node.invoke({"messages": [only_ours]})

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
        }

    graph = StateGraph(_LoopState)
    graph.add_node("model", model)
    targets = ["model", END]
    if tool_node:
        graph.add_node("tools", tools)
        graph.add_node("over_limit", over_limit)
        graph.add_edge("tools", "model")
        graph.add_edge("over_limit", "model")
        targets += ["tools", "over_limit"]
    graph.add_edge(START, "model")
    graph.add_conditional_edges("model", route, targets)
    return graph.compile(checkpointer=False, name="agent_tool_loop")


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
) -> tuple[T, set[str], list[str]]:
    """Run one agent (defined in agent_setup/agents/<agent>.md) and parse its JSON reply.

    - Prompt: the agent's shared rules + skills + task prompt; matching team memory goes at
      the top of the message (`scope.used` records which notes).
    - Tools: exactly those listed under the agent's `tools:`. Client tools see only what
      `tool_context` gives them.
    - Model and effort: the agent's own settings, unless the run's RunOptions override them.

    Returns (parsed reply, URLs returned verbatim by tools, notes about rejected URLs).
    If `pages` is given, every page fetched with web_fetch is appended to it as (url, text).
    """
    settings = services.settings
    options = current_options()
    root = settings.agent_setup_dir
    config = load_agent(root, agent)

    ctx = tool_context or ToolContext(services=services)
    ctx.allowed_urls |= set(known_urls)
    server_tools, client_tools = build_tools(
        root, config.tools, ctx, web_max_uses=options.web_search_max_uses
    )
    llm = services.llm_for(config.model or options.model)
    if server_tools or client_tools:
        llm = llm.bind_tools([*server_tools, *client_tools])

    if scope is not None:
        scope.agent, scope.step = config.name, config.step
        budget = options.memory_max_chars or settings.memory_max_chars
        notes_used, _ = select_notes(root, scope, settings.vertical, budget)
        scope.used = [n.path for n in notes_used]
        if block := memory_block(notes_used):
            user = f"{block}\n\n# TASK INPUT\n{user}"
    messages = [SystemMessage(system_prompt(root, config, list(extra_skills))), HumanMessage(user)]
    urls: set[str] = set()
    notes: list[str] = []

    def on_response(response: AIMessage) -> None:
        blocks = response.content if isinstance(response.content, list) else []
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
    )
    limit = {"recursion_limit": 2 * max_calls + 4 * MAX_CONTINUATIONS + 10}
    for attempt in range(2):
        state = loop.invoke({"messages": messages, "tool_calls": 0}, limit)
        messages = state["messages"]
        response = messages[-1]
        try:
            return parse_json(response.text, schema), urls, notes
        except (ValueError, ValidationError) as exc:
            if attempt:
                raise
            messages = [
                *messages,
                HumanMessage(
                    f"Your reply could not be parsed ({exc}). Reply again with only the JSON "
                    f"object matching this schema:\n{json.dumps(schema.model_json_schema())}"
                ),
            ]
    raise AssertionError("unreachable")
