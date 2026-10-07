"""Answer agents, one per question-bank section. Section guidance lives in
agent_setup/skills/sections/; modules in this package add optional code-level hooks and are
imported automatically."""

import importlib
import pkgutil

from asics_agent.agents.sections.base import (
    GENERIC,
    SectionSpec,
    build_section_agent,
    register,
    section_for,
    section_nodes,
)

for _module in pkgutil.iter_modules(__path__):
    if _module.name != "base":
        importlib.import_module(f"{__name__}.{_module.name}")

__all__ = [
    "GENERIC",
    "SectionSpec",
    "build_section_agent",
    "register",
    "section_for",
    "section_nodes",
]
