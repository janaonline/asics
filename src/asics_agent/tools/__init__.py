"""Tools the agents can call, configured per agent in agent_setup/agents/<agent>.md:

    tools:
      web_search: {max_uses: 8, blocked_domains: [wikipedia.org]}
      check_link: {}

Each tool is described for the model in agent_setup/tools/<tool>.md. Two kinds:

* server tools (web_search, web_fetch) run on Anthropic's side, inside the model call;
* client tools (check_link, read_citation, search_citation_sheet, lookup_question) are Python
  functions in this package, run by LangGraph's ToolNode in the agent's tool loop (llm.py).

To add a client tool: write a module here with `TOOL = ClientTool(...)`, add
agent_setup/tools/<name>.md, and list it under an agent's `tools:`.
"""

import importlib
import pkgutil

from asics_agent.tools.base import (
    CLIENT_TOOLS,
    SERVER_TOOLS,
    ClientTool,
    ToolContext,
    build_tools,
    tool_description,
)

for _module in pkgutil.iter_modules(__path__):
    if _module.name != "base":
        importlib.import_module(f"{__name__}.{_module.name}")

__all__ = [
    "CLIENT_TOOLS",
    "SERVER_TOOLS",
    "ClientTool",
    "ToolContext",
    "build_tools",
    "tool_description",
]
