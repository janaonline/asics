"""Per-run options, passed to the graphs as LangGraph run context (`context_schema`).

LangGraph Studio shows these as a form for each run; the CLI sets them with flags. Anything
left empty falls back to the agent's own setting (agent_setup/agents/) and then to .env.
"""

from dataclasses import dataclass


@dataclass
class RunOptions:
    model: str | None = None  # Claude model for agents that don't name their own
    effort: str | None = None  # low | medium | high | xhigh | max, for every agent
    web_search_max_uses: int | None = None  # searches / fetches per call, for every agent
    max_tool_calls: int | None = None  # client tool calls per agent call
    memory_max_chars: int | None = None  # team memory given to the model per call


def current_options() -> RunOptions:
    """The options of the run this code is part of (or defaults outside a run)."""
    from langgraph.runtime import get_runtime

    try:
        context = get_runtime(RunOptions).context
    except Exception:  # not inside a graph run (e.g. a direct call in a test)
        return RunOptions()
    return context if isinstance(context, RunOptions) else RunOptions(**(context or {}))
