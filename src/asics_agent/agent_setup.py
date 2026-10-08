"""Reads the `agent_setup/` folder: agents, prompts, skills, section guidance and memory.

Everything that shapes what the AI does lives there as Markdown, so it can be read and
changed without touching code:

  agent_setup/agents/<agent>.md        settings (front matter) + description of each agent
  agent_setup/prompts/<prompt>.md      task instructions; shared-rules.md goes to every agent
  agent_setup/skills/<skill>.md        reusable know-how, attached to agents in their settings
  agent_setup/skills/sections/<CODE>.md  guidance for one question-bank section (UPD, DPG…)
  agent_setup/memory/…                 context from the research team, picked per run

Files are read fresh on every call, so edits (including from the app) apply to the next call.
"""

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from asics_agent.cities import slugify
from asics_agent.models import Issue

EFFORTS = {"low", "medium", "high", "xhigh", "max"}
WEB_TOOLS = {"web_search", "web_fetch"}
NOTE_FILTERS = {"parastatals", "sections", "agents", "steps", "cities", "title"}
IGNORED = {"README.md"}
IGNORED_DIRS = {"_archive", "_history"}
_FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.S)


class SetupError(RuntimeError):
    """agent_setup/ is missing something an agent needs. The message is plain language."""


@dataclass
class AgentConfig:
    name: str
    title: str
    step: int
    prompt: str
    skills: list[str]
    web_research: bool  # True if any web tool is on (kept for older agent files)
    effort: str
    description: str
    path: Path
    tools: dict = field(default_factory=dict)  # tool name -> options
    max_tool_calls: int = 20  # client tool calls per agent call
    model: str = ""  # optional: a different Claude model for this agent


@dataclass
class Note:
    path: str  # relative to agent_setup/memory, e.g. "cities/bengaluru.md"
    title: str
    text: str
    filters: dict
    scope: str  # "general" | "city" | "vertical"
    target: str = ""  # the city slug or vertical name the folder points at


@dataclass
class MemoryScope:
    """What a model call is about, used to pick the memory notes that apply."""

    agent: str = ""
    step: int | None = None
    city: str | None = None  # city name or slug
    parastatals: list[str] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)
    used: list[str] = field(default_factory=list)  # filled in: notes given to the model


def split_front_matter(text: str) -> tuple[dict, str]:
    match = _FRONT.match(text)
    if not match:
        return {}, text
    data = yaml.safe_load(match.group(1)) or {}
    if not isinstance(data, dict):
        raise ValueError("the settings block at the top must be 'key: value' lines")
    return data, text[match.end() :]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# -- agents, prompts, skills ----------------------------------------------------------------
def load_agents(root: Path) -> tuple[dict[str, AgentConfig], list[Issue]]:
    agents, issues = {}, []
    for path in sorted((root / "agents").glob("*.md")):
        try:
            meta, body = split_front_matter(_read(path))
        except (ValueError, yaml.YAMLError) as exc:
            issues.append(
                _dev(
                    "error",
                    f"agent_setup/agents/{path.name}: settings block can't be read ({exc}).",
                )
            )
            continue
        name = meta.get("name") or path.stem
        tools = meta.get("tools")
        if tools is None and meta.get("web_research"):  # older format: web_research: true
            tools = {"web_search": {}, "web_fetch": {}}
        if isinstance(tools, list):  # also accept a plain list of names
            tools = {t: {} for t in tools}
        tools = {str(k): dict(v or {}) for k, v in (tools or {}).items()}
        agents[name] = AgentConfig(
            name=name,
            title=meta.get("title", name),
            step=int(meta.get("step", 0)),
            prompt=meta.get("prompt", name),
            skills=list(meta.get("skills") or []),
            web_research=any(t in WEB_TOOLS for t in tools),
            effort=str(meta.get("effort", "high")),
            description=body.strip(),
            path=path,
            tools=tools,
            max_tool_calls=int(meta.get("max_tool_calls", 20)),
            model=str(meta.get("model") or ""),
        )
    return agents, issues


def load_agent(root: Path, name: str) -> AgentConfig:
    agents, _ = load_agents(root)
    if name not in agents:
        raise SetupError(f"agent_setup/agents/{name}.md is missing")
    return agents[name]


def _body(root: Path, kind: str, name: str) -> str:
    path = root / kind / f"{name}.md"
    if not path.exists():
        raise SetupError(f"agent_setup/{kind}/{name}.md is missing")
    return split_front_matter(_read(path))[1].strip()


def system_prompt(
    root: Path, agent: AgentConfig, extra_skills: list[str] = (), rules: str = "shared-rules"
) -> str:
    """Shared rules (the vertical's), then the agent's skills, then its task prompt. This part
    is the same for every call of the agent (memory goes in the message), which keeps calls
    cache-friendly."""
    parts = [_body(root, "prompts", rules)]
    for skill in [*agent.skills, *extra_skills]:
        parts.append(f"# SKILL: {skill}\n{_body(root, 'skills', skill)}")
    parts.append(_body(root, "prompts", agent.prompt))
    return "\n\n".join(parts)


def section_skill(root: Path, code: str, vertical: str = "") -> str | None:
    """The guidance skill for a section: the vertical's own (skills/sections/<vertical>/
    <code>.md) if it has one, else the shared one (skills/sections/<code>.md)."""
    for name in ([f"sections/{vertical}/{code.lower()}"] if vertical else []) + [
        f"sections/{code.lower()}"
    ]:
        if (root / "skills" / f"{name}.md").exists():
            return name
    return None


def section_guidance(root: Path, code: str, vertical: str = "") -> tuple[str, str, str]:
    """(title, guidance, evidence hints) for a question-bank section, or empty strings."""
    skill = section_skill(root, code, vertical)
    path = root / "skills" / f"{skill}.md" if skill else None
    if path is None:
        return "", "", ""
    meta, body = split_front_matter(_read(path))
    return meta.get("title", code), body.strip(), str(meta.get("evidence_hints", ""))


def section_codes(root: Path) -> dict[str, str]:
    """{CODE: title} for every section that has a guidance file."""
    codes = {}
    for path in sorted((root / "skills" / "sections").glob("*.md")):
        meta, _ = split_front_matter(_read(path))
        codes[str(meta.get("name", path.stem)).upper()] = meta.get("title", path.stem.upper())
    return codes


# -- memory ---------------------------------------------------------------------------------
def list_notes(root: Path) -> tuple[list[Note], list[Issue]]:
    notes, issues = [], []
    base = root / "memory"
    for path in sorted(base.rglob("*.md")):
        rel = path.relative_to(base)
        if path.name in IGNORED or IGNORED_DIRS & set(rel.parts):
            continue
        try:
            meta, body = split_front_matter(_read(path))
        except (ValueError, yaml.YAMLError) as exc:
            issues.append(
                _team(
                    "warning",
                    f"Memory note {rel.as_posix()}: the settings block at "
                    f"the top can't be read ({exc}), so the note was not used.",
                )
            )
            continue
        if unknown := set(meta) - NOTE_FILTERS:
            issues.append(
                _team(
                    "warning",
                    f"Memory note {rel.as_posix()}: unknown setting(s) "
                    f"{', '.join(sorted(unknown))}; they are ignored.",
                )
            )
        top = rel.parts[0]
        scope, target = "general", ""
        if top == "cities" and len(rel.parts) > 1:
            scope, target = "city", slugify(Path(rel.parts[1]).stem)
        elif top == "verticals" and len(rel.parts) > 2:
            scope, target = "vertical", rel.parts[1].lower()
        notes.append(
            Note(
                path=rel.as_posix(),
                title=meta.get("title")
                or next((ln[2:].strip() for ln in body.splitlines() if ln.startswith("# ")), "")
                or path.stem.replace("-", " ").capitalize(),
                text=body.strip(),
                filters=meta,
                scope=scope,
                target=target,
            )
        )
    return notes, issues


def _matches(note: Note, scope: MemoryScope, vertical: str) -> bool:
    if note.scope == "city" and (not scope.city or slugify(scope.city) != note.target):
        return False
    if note.scope == "vertical" and note.target != vertical.lower():
        return False

    def wants(key: str, values) -> bool:
        allowed = note.filters.get(key)
        if not allowed:
            return True
        allowed = {str(a).lower() for a in (allowed if isinstance(allowed, list) else [allowed])}
        return bool(allowed & {str(v).lower() for v in values})

    return (
        wants("agents", [scope.agent])
        and wants("steps", [scope.step])
        and wants("cities", [scope.city or "", slugify(scope.city or "")])
        and (not note.filters.get("parastatals") or wants("parastatals", scope.parastatals))
        and (not note.filters.get("sections") or wants("sections", scope.sections))
    )


def select_notes(root: Path, scope: MemoryScope, vertical: str, budget: int):
    """(notes to use, notes left out because of the size limit), most specific first."""
    notes, _ = list_notes(root)
    matching = [n for n in notes if _matches(n, scope, vertical)]
    weight = {"city": 2, "vertical": 1, "general": 0}
    matching.sort(
        key=lambda n: (
            weight[n.scope] + sum(k in n.filters for k in ("parastatals", "sections", "agents")),
            n.path,
        ),
        reverse=True,
    )
    chosen, skipped, size = [], [], 0
    for note in matching:
        if size + len(note.text) > budget:
            skipped.append(note)
            continue
        chosen.append(note)
        size += len(note.text)
    order = {"general": 0, "vertical": 1, "city": 2}  # broad to specific in the prompt
    return sorted(chosen, key=lambda n: (order[n.scope], n.path)), skipped


def memory_block(notes: list[Note]) -> str:
    if not notes:
        return ""
    parts = [
        "# CONTEXT FROM THE RESEARCH TEAM",
        "Guidance only: not evidence, never cite it. If it disagrees with a source, follow "
        "the source and say so in your notes.",
    ]
    for note in notes:
        parts.append(f"## {note.title} (memory/{note.path})\n{note.text}")
    return "\n\n".join(parts)


# -- checks, audit, editing -----------------------------------------------------------------
def validate(
    root: Path, city_names: list[str], vertical: str, section_codes_in_bank: set[str]
) -> list[Issue]:
    issues: list[Issue] = []
    if not root.exists():
        return [_dev("error", f"The agent_setup folder is missing ({root}).")]
    agents, issues_ = load_agents(root)
    issues += issues_
    if not (root / "prompts" / "shared-rules.md").exists():
        issues.append(_dev("error", "agent_setup/prompts/shared-rules.md is missing."))
    for agent in agents.values():
        where = f"agent_setup/agents/{agent.path.name}"
        if not (root / "prompts" / f"{agent.prompt}.md").exists():
            issues.append(
                _dev(
                    "error",
                    f"{where} uses prompt '{agent.prompt}', but "
                    f"agent_setup/prompts/{agent.prompt}.md doesn't exist.",
                )
            )
        for skill in agent.skills:
            if not (root / "skills" / f"{skill}.md").exists():
                issues.append(
                    _dev(
                        "error",
                        f"{where} uses skill '{skill}', but "
                        f"agent_setup/skills/{skill}.md doesn't exist.",
                    )
                )
        if agent.effort not in EFFORTS:
            issues.append(_dev("error", f"{where}: effort must be one of {sorted(EFFORTS)}."))
        if agent.model and not agent.model.startswith("claude-"):
            issues.append(
                _dev(
                    "error",
                    f"{where}: model '{agent.model}' doesn't look like a "
                    "Claude model ID (e.g. claude-sonnet-5-5).",
                )
            )
        issues += _validate_tools(root, agent, where)
    known = set(section_codes(root))
    for code in sorted(section_codes_in_bank - known):
        issues.append(
            _dev(
                "info",
                f"Question-bank section {code} has no guidance file "
                f"(agent_setup/skills/sections/{code.lower()}.md); the general "
                "answer guidance is used.",
            )
        )

    notes, note_issues = list_notes(root)
    issues += note_issues
    city_slugs = {slugify(c) for c in city_names}
    for note in notes:
        if note.scope == "city" and note.target not in city_slugs:
            issues.append(
                _team(
                    "warning",
                    f"Memory note {note.path} is for a city that isn't in "
                    "the city register, so it is never used. Check the file name.",
                )
            )
        if note.scope == "vertical" and note.target != vertical.lower():
            issues.append(
                _team(
                    "info",
                    f"Memory note {note.path} is for the "
                    f"'{note.target}' vertical, so it isn't used in "
                    f"'{vertical}' runs.",
                )
            )
        if note.scope == "general" and note.path.count("/") == 0:
            issues.append(
                _team(
                    "info",
                    f"Memory note {note.path} is directly in memory/; it is "
                    "used everywhere. Move it into memory/general/ to make that "
                    "clear.",
                )
            )
    return issues


def _validate_tools(root: Path, agent: AgentConfig, where: str) -> list[Issue]:
    from asics_agent.tools import CLIENT_TOOLS, SERVER_TOOLS
    from asics_agent.tools.base import SERVER_OPTIONS

    issues = []
    for name, options in agent.tools.items():
        if name not in SERVER_TOOLS and name not in CLIENT_TOOLS:
            known = ", ".join(sorted({*SERVER_TOOLS, *CLIENT_TOOLS}))
            issues.append(_dev("error", f"{where}: unknown tool '{name}'. Known tools: {known}."))
            continue
        if not (root / "tools" / f"{name}.md").exists():
            issues.append(
                _dev(
                    "warning",
                    f"agent_setup/tools/{name}.md is missing, so the "
                    "model gets no description of this tool.",
                )
            )
        allowed = SERVER_OPTIONS if name in SERVER_TOOLS else set()
        if unknown := set(options) - allowed:
            issues.append(
                _dev(
                    "error",
                    f"{where}: tool '{name}' has unknown option(s) "
                    f"{sorted(unknown)}; allowed: {sorted(allowed) or 'none'}.",
                )
            )
        if options.get("allowed_domains") and options.get("blocked_domains"):
            issues.append(
                _dev(
                    "error",
                    f"{where}: tool '{name}' can have allowed_domains or "
                    "blocked_domains, not both.",
                )
            )
    if agent.step in (2, 3) and agent.tools.keys() & WEB_TOOLS:
        issues.append(
            _dev(
                "error",
                f"{where}: Step {agent.step} agents work only from the Citation "
                "Sheet, so they must not have web_search or web_fetch.",
            )
        )
    return issues


def fingerprint(root: Path) -> str:
    """A short hash of every prompt, skill, agent and memory file: which setup produced a run."""
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.md")):
        rel = path.relative_to(root)
        if IGNORED_DIRS & set(rel.parts):
            continue
        digest.update(rel.as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def note_path(root: Path, scope: str, title: str, target: str = "") -> Path:
    """Where a new note goes: general/<title>.md, cities/<city>/<title>.md or
    verticals/<vertical>/<title>.md."""
    name = slugify(title).replace("_", "-") or "note"
    if scope == "city":
        return root / "memory" / "cities" / slugify(target) / f"{name}.md"
    if scope == "vertical":
        return root / "memory" / "verticals" / slugify(target) / f"{name}.md"
    return root / "memory" / "general" / f"{name}.md"


def save_note(root: Path, path: Path, text: str) -> None:
    """Save a note, keeping the previous version in memory/_history/."""
    if path.exists():
        from datetime import datetime

        history = root / "memory" / "_history"
        history.mkdir(parents=True, exist_ok=True)
        rel = path.relative_to(root / "memory").as_posix().replace("/", "__")
        (history / f"{datetime.now():%Y%m%d-%H%M%S}__{rel}").write_bytes(path.read_bytes())
    path.parent.mkdir(parents=True, exist_ok=True)
    split_front_matter(text)  # raises if the settings block is broken
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def archive_note(root: Path, path: Path) -> Path:
    """Move a note to memory/_archive/ (not used, not deleted)."""
    from datetime import datetime

    archive = root / "memory" / "_archive"
    archive.mkdir(parents=True, exist_ok=True)
    rel = path.relative_to(root / "memory").as_posix().replace("/", "__")
    target = archive / f"{datetime.now():%Y%m%d-%H%M%S}__{rel}"
    path.rename(target)
    return target


def _team(severity: str, message: str) -> Issue:
    return Issue(
        phase="initial_checks",
        severity=severity,
        message=message,
        audience="team",
        ref="agent_setup",
    )


def _dev(severity: str, message: str) -> Issue:
    return Issue(phase="initial_checks", severity=severity, message=message, ref="agent_setup")


def verticals(root: Path, current: str) -> list[str]:
    """Vertical folders under memory/verticals/, always including the current one."""
    base = root / "memory" / "verticals"
    found = {p.name for p in base.iterdir() if p.is_dir()} if base.exists() else set()
    return sorted(found | {current})


def add_vertical(root: Path, name: str) -> Path:
    folder = root / "memory" / "verticals" / slugify(name).replace("_", "-")
    folder.mkdir(parents=True, exist_ok=True)
    readme = folder / "README.md"
    if not readme.exists():
        readme.write_text(
            f"# {name}\n\nNotes for the {name} vertical. They are used only in "
            f"runs of that vertical (setting ASICS_VERTICAL={folder.name}).\n"
        )
    return folder


def note_with_settings(text: str, settings: dict) -> str:
    """Add a settings block (parastatals, sections, agents, steps) to a note's text."""
    settings = {k: v for k, v in settings.items() if v}
    if not settings:
        return text
    return f"---\n{yaml.safe_dump(settings, sort_keys=False).strip()}\n---\n{text}"
