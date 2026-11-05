"""Maps a question's free-text "Applicability" to the parastatals it applies to.

The rules are data: data/applicability_rules.yaml (edit that file, not this one). Rules are
checked in order; the first phrase found in the text wins. Initial checks flag any wording that
no rule recognises, naming the question.
"""

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

import yaml

from asics_agent.config import PROJECT_ROOT
from asics_agent.models import Parastatal, Question
from asics_agent.parastatal_types import ULG_TYPE, canonical_type, known_type

RULES_FILE = "data/applicability_rules.yaml"
KINDS = ("type_is", "type_is_not", "flag", "common")
FLAG_FIELDS = ("revenue_raising", "capex_mandate", "has_annual_budget", "has_chief_executive")


class Rule(NamedTuple):
    """`phrase` found in the text -> `test(parastatal)`. (phrase, test) first, so rule[1] works."""

    phrase: str
    test: Callable[[Parastatal], bool]
    kind: str = ""
    value: str = ""
    confirm: str = ""  # an override's "please confirm" note

    def describe(self) -> str:
        return {
            "type_is": f"type is {self.value}",
            "type_is_not": f"type is not {self.value}",
            "flag": f"{self.value} is Yes",
            "common": "every parastatal",
        }.get(self.kind, self.kind)


@dataclass
class RuleSet:
    rules: list[Rule] = field(default_factory=list)
    overrides: dict[str, Rule] = field(default_factory=dict)  # normalised question id -> rule
    problems: list[str] = field(default_factory=list)  # plain-language problems in the file
    path: Path | None = None


def _make_rule(phrase: str, kind: str, value: str, confirm: str = "") -> Rule:
    if kind == "common":
        return Rule(phrase, lambda p: True, kind, "", confirm)
    if kind in ("type_is", "type_is_not"):
        code = canonical_type(value)  # an old type code in the file still works
        if not known_type(code):
            raise ValueError(f'"{value}" is not a parastatal type')
        if kind == "type_is":
            return Rule(phrase, lambda p, c=code: p.type == c, kind, code, confirm)
        return Rule(phrase, lambda p, c=code: p.type != c, kind, code, confirm)
    if kind == "flag":
        if value not in FLAG_FIELDS:
            raise ValueError(f'"{value}" is not one of the Yes/No flags: {", ".join(FLAG_FIELDS)}')
        return Rule(phrase, lambda p, f=value: bool(getattr(p, f)), kind, value, confirm)
    raise ValueError(f'unknown rule "{kind}" (use one of: {", ".join(KINDS)})')


def parse_rules(data: dict | None) -> RuleSet:
    """Build the rule set from the file's contents; a bad entry is reported and skipped."""
    out = RuleSet()
    data = data or {}
    for i, item in enumerate(data.get("rules") or [], start=1):
        try:
            phrase = str(item["phrase"]).strip().lower()
            if not phrase:
                raise ValueError("the phrase is empty")
            out.rules.append(_make_rule(phrase, item["rule"], str(item.get("value", ""))))
        except (KeyError, ValueError, TypeError) as e:
            out.problems.append(f"Applicability rules, rule {i}: {e}. It was skipped.")
    for code, item in (data.get("overrides") or {}).items():
        try:
            rule = _make_rule(
                "", item["rule"], str(item.get("value", "")), str(item.get("confirm", "")).strip()
            )
            out.overrides[_norm(code)] = rule
        except (KeyError, ValueError, TypeError, AttributeError) as e:
            out.problems.append(f"Applicability rules, override {code}: {e}. It was skipped.")
    return out


def _norm(code: str) -> str:
    return "".join(str(code).split()).upper()


def rules_path() -> Path:
    path = Path(os.getenv("ASICS_APPLICABILITY_RULES", RULES_FILE))
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_rules(path: Path | None = None) -> RuleSet:
    """Read the rules file. A missing or unreadable file is a reported problem, not a crash."""
    path = path or rules_path()
    try:
        with open(path, encoding="utf-8") as f:
            out = parse_rules(yaml.safe_load(f))
    except (OSError, yaml.YAMLError) as e:
        out = RuleSet(problems=[f"The applicability rules file ({path.name}) can't be read: {e}"])
    out.path = path
    return out


@lru_cache
def get_rules() -> RuleSet:
    return load_rules()


def reload_rules() -> None:
    get_rules.cache_clear()


def match_rule(applicability: str, code: str | None = None, rules: RuleSet | None = None):
    """The rule that decides `applicability` (a question's override first), else None."""
    rules = rules or get_rules()
    if code and (override := rules.overrides.get(_norm(code))):
        return override
    text = (applicability or "").lower()
    return next((rule for rule in rules.rules if rule.phrase in text), None)


def applies_to(
    question: Question, parastatal: Parastatal, rules: RuleSet | None = None
) -> bool | None:
    """True/False, or None when the applicability text is not recognised.

    Overrides are for the Parastatal category's questions, so they are not used for the ULG."""
    code = None if parastatal.type == ULG_TYPE else question.id
    rule = match_rule(question.applicability, code, rules)
    return None if rule is None else rule.test(parastatal)


def override_notes(questions: dict[str, Question], rules: RuleSet | None = None) -> list[tuple]:
    """(question, note) for each question in `questions` that has an assumed rule to confirm."""
    rules = rules or get_rules()
    return [
        (q, rules.overrides[_norm(q.id)].confirm)
        for q in questions.values()
        if _norm(q.id) in rules.overrides
    ]
