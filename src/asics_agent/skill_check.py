"""A free check (no AI) that the help files name only questions the question banks have.

Skills, team memory and prompts are help only; the Detailed Methodology is the rule. A skill that
names a question code no bank has (for example DPG 5j after the bank changed) is out of date.
The check cannot tell when a code still exists but now means something else: a person has to read
those. Codes are compared across every category's bank, because a generic section skill serves
more than one category.
"""

import re
from pathlib import Path

CODE = re.compile(r"\b(UPD|SC|DPG)[ -]?(\d+)([a-z]?)\b")
FOLDERS = ("skills", "memory", "prompts")


def normalise(prefix: str, number: str, letter: str) -> str:
    return f"{prefix} {number}{letter}"


def bank_codes(settings) -> set[str]:
    """Every question code of every category's bank."""
    from asics_agent.categories import category_settings, load_bank, load_categories

    found, _ = load_categories(settings.agent_setup_dir)
    codes: set[str] = set()
    for name in found:
        bank, _ = load_bank(category_settings(settings, name))
        codes |= set(bank)
    return codes


def skill_problems(settings) -> list[tuple[str, str]]:
    """[(file, message)] for each help file that names a question code no bank has."""
    root = Path(settings.agent_setup_dir)
    known = bank_codes(settings)
    if not known:
        return []
    out = []
    for folder in FOLDERS:
        for path in sorted((root / folder).rglob("*.md")):
            text = path.read_text(encoding="utf-8")
            missing = sorted(
                {
                    normalise(*m.groups())
                    for m in CODE.finditer(text)
                    if normalise(*m.groups()) not in known
                }
            )
            if missing:
                where = f"agent_setup/{path.relative_to(root).as_posix()}"
                out.append(
                    (
                        where,
                        f"{where} names {', '.join(missing)}, which is in no question bank. "
                        "It may describe an older bank: the Detailed Methodology is the rule.",
                    )
                )
    return out
