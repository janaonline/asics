"""ASICS verticals (Parastatal, UPD, Mobility…): each one is a settings file in
agent_setup/verticals/<name>.md, and every vertical runs the same three steps:

  Step 1  find sources    the units to assess, their official websites, the Citation Sheet
  Step 2  answer          every question, from the reviewed Citation Sheet only
  Step 3  score           every question, from its Step 2 answer and citation

What differs between verticals is configuration, not code:

  question bank   which workbook (and sheet), and how its columns are named
  unit            what is assessed in a city: "parastatal" (the agencies Step 1 discovers)
                  or "city_government" (the city government itself, e.g. UPD)
  agents          which agent does each job in each step (agent_setup/agents/<name>.md),
                  so a vertical can have its own prompts, skills and tools
  shared_rules    the rules every agent of the vertical gets (agent_setup/prompts/<name>.md)
  outputs         where its city folders go (inside the outputs folder)
  scoring         its scoring workbook (scoring/2027/templates/…)

`settings_for(settings, name)` returns the settings a run of that vertical uses.
"""

import dataclasses
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from asics_agent.models import Issue

FOLDER = "verticals"
UNITS = {"parastatal": "Parastatal", "city_government": "City government"}
CITY_UNIT_ID = "ULG"  # the unit ID when the city government itself is assessed
# role -> (step, default agent). A vertical may name its own agent for any role.
ROLES = {
    "discover": (1, "parastatal-discovery"),  # only for unit: parastatal
    "profile": (1, "website-profiler"),
    "sources": (1, "citation-builder"),
    "assess": (1, "source-assessor"),
    "bank_review": (0, "question-bank-reviewer"),
    "answer": (2, "answer-writer"),
    "score": (3, "question-scorer"),
}
_FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)


@dataclass(frozen=True)
class Vertical:
    name: str  # "parastatal"
    title: str  # "Parastatal"
    code: str  # "PARASTATAL": scoring workbook sheet names, file names
    unit: str = "parastatal"
    question_bank: str = ""
    question_bank_sheet: str = ""
    question_columns: dict = field(default_factory=dict)
    outputs: str = "."
    scoring_workbook: str = ""
    shared_rules: str = "shared-rules"
    agents: dict = field(default_factory=dict)  # role -> agent name
    description: str = ""
    path: Path | None = None

    @property
    def unit_label(self) -> str:
        return UNITS.get(self.unit, self.unit)

    def agent(self, role: str) -> str:
        return self.agents.get(role) or ROLES[role][1]


def _parse(path: Path) -> Vertical:
    text = path.read_text(encoding="utf-8")
    match = _FRONT.match(text)
    meta = yaml.safe_load(match.group(1)) if match else {}
    if not isinstance(meta, dict):
        raise ValueError("the settings block at the top must be 'key: value' lines")
    agents = {}
    for step in (meta.get("steps") or {}).values():
        agents.update({k: str(v) for k, v in (step or {}).items() if v})
    name = str(meta.get("name") or path.stem)
    return Vertical(
        name=name,
        title=str(meta.get("title") or name.title()),
        code=str(meta.get("code") or name.upper()),
        unit=str(meta.get("unit") or "parastatal"),
        question_bank=str(meta.get("question_bank") or ""),
        question_bank_sheet=str(meta.get("question_bank_sheet") or ""),
        question_columns=dict(meta.get("question_columns") or {}),
        outputs=str(meta.get("outputs") or "."),
        scoring_workbook=str(meta.get("scoring_workbook") or ""),
        shared_rules=str(meta.get("shared_rules") or "shared-rules"),
        agents=agents,
        description=text[match.end() :].strip() if match else text.strip(),
        path=path,
    )


def load_verticals(root: Path) -> tuple[dict[str, Vertical], list[Issue]]:
    """{name: Vertical} from agent_setup/verticals/*.md, and problems found in them."""
    verticals, issues = {}, []
    for path in sorted((root / FOLDER).glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        where = f"agent_setup/{FOLDER}/{path.name}"
        try:
            v = _parse(path)
        except (ValueError, yaml.YAMLError) as exc:
            issues.append(_issue(f"{where}: settings block can't be read ({exc})."))
            continue
        if v.unit not in UNITS:
            issues.append(_issue(f"{where}: unit must be one of {', '.join(UNITS)}."))
        for role in v.agents:
            if role not in ROLES:
                issues.append(_issue(f"{where}: unknown job '{role}' (known: {', '.join(ROLES)})."))
        for role in ROLES:
            if role == "discover" and v.unit != "parastatal":
                continue
            if not (root / "agents" / f"{v.agent(role)}.md").exists():
                issues.append(
                    _issue(
                        f"{where}: agent '{v.agent(role)}' ({role}) has no file "
                        f"agent_setup/agents/{v.agent(role)}.md."
                    )
                )
        if not (root / "prompts" / f"{v.shared_rules}.md").exists():
            issues.append(
                _issue(
                    f"{where}: shared_rules '{v.shared_rules}' has no file "
                    f"agent_setup/prompts/{v.shared_rules}.md."
                )
            )
        verticals[v.name] = v
    return verticals, issues


def _issue(message: str) -> Issue:
    return Issue(phase="initial_checks", severity="error", message=message, audience="team")


def _resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def settings_for(settings, name: str):
    """The settings for a run of vertical `name`. Without a settings file, the vertical
    runs as before (Parastatal defaults)."""
    from asics_agent.config import PROJECT_ROOT

    found, _ = load_verticals(settings.agent_setup_dir)
    v = found.get(name.lower())
    if v is None:
        return dataclasses.replace(
            settings,
            vertical=name.lower(),
            outputs_root=settings.outputs_root or settings.outputs_dir,
        )
    root = settings.outputs_root or settings.outputs_dir
    outputs = root / v.outputs if v.outputs not in ("", ".") else root
    return dataclasses.replace(
        settings,
        outputs_root=root,
        vertical=v.name,
        vertical_title=v.title,
        vertical_code=v.code,
        unit=v.unit,
        unit_label=v.unit_label,
        shared_rules=v.shared_rules,
        agents=tuple(sorted(v.agents.items())),
        question_bank=_resolve(PROJECT_ROOT, v.question_bank)
        if v.question_bank
        else settings.question_bank,
        question_bank_sheet=v.question_bank_sheet,
        question_columns=tuple(sorted(v.question_columns.items())),
        outputs_dir=outputs,
        scoring_workbook=_resolve(PROJECT_ROOT, v.scoring_workbook) if v.scoring_workbook else None,
    )


def agent_for(settings, role: str) -> str:
    """The agent that does `role` in this vertical (its settings file, else the default)."""
    return dict(getattr(settings, "agents", ()) or ()).get(role) or ROLES[role][1]


def load_bank(settings):
    """The vertical's question bank, read with its sheet and column names."""
    from asics_agent.question_bank import load_question_bank

    return load_question_bank(
        settings.question_bank,
        getattr(settings, "question_bank_sheet", "") or None,
        dict(getattr(settings, "question_columns", ()) or ()),
    )
