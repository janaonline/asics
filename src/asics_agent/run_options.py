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
    # Step 1 on a city that already has a Sources workbook: by default only questions with no
    # verified source are researched, and known agencies aren't searched for or profiled again.
    full_refresh: bool = False  # True: search again for everything


_DEFAULT = RunOptions()  # for work outside a graph run, e.g. Step 3 from the command line


def set_default_options(options: RunOptions) -> None:
    """Options for agent calls made outside a LangGraph run (Step 3 scoring)."""
    global _DEFAULT
    _DEFAULT = options


def current_options() -> RunOptions:
    """The options of the run this code is part of (or the default options outside a run)."""
    from langgraph.runtime import get_runtime

    try:
        context = get_runtime(RunOptions).context
    except Exception:  # not inside a graph run (e.g. Step 3, or a direct call in a test)
        return _DEFAULT
    return context if isinstance(context, RunOptions) else RunOptions(**(context or {}))
