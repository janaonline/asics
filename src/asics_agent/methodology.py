"""Checks that an answer or a score follows the question's Detailed Methodology.

The Detailed Methodology is the rule. Skill and memory files are help only. These helpers do the
small checks that can be done in code; a doubt becomes a CONFIRM note, never a silent change.
"""

import re

from asics_agent.scoring.score_levels import _PART, EPS, score_levels


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def is_placeholder(methodology: str) -> bool:
    """True when the methodology is only a note (DPG 4: "scoring ... not undertaken ... awaiting
    support from the state teams"): there is no rule to apply."""
    text = _text(methodology)
    if not re.match(r"^\[?\s*note\s*:", text, re.I) or len(text) > 700:
        return False
    return not score_levels(text, 1.0).listed


def placeholder_reason(code: str) -> str:
    return (
        f"The methodology for {code} is only a placeholder note, with no scoring rule, so there "
        "is nothing to apply. Left for a person."
    )


def band_problem(methodology: str, max_score: float | None, band: str) -> str | None:
    """Why a BAND (the methodology level or part an answer says it supports) does not match the
    methodology, or None. Only clear mismatches are reported: an empty, "?" or descriptive band
    (no number) is not checked."""
    band = _text(band)
    if not band or band.strip("?- ").casefold() in {"", "n/a", "na", "none"}:
        return None
    parts = sorted(set(_PART.findall(methodology or "")))
    if len(parts) >= 2:
        if not re.search(r"part|\(?[a-d]\)|\b[A-D]\s*[:=-]", band, re.I):
            return (
                f'BAND "{band[:40].rstrip()}" does not say which part of the methodology it rests on '
                f"(Part {', Part '.join(parts)})."
            )
        return None
    if not max_score:
        return None
    rule = score_levels(methodology or "", max_score)
    if rule.kind != "levels":
        return None
    # The band is short ("2.5", "Score 2.5", "10 - ULG approval"); only its leading number counts,
    # so figures in any prose after it cannot match by accident.
    lead = re.match(r"\W*(?:score|level|band)?\W*(\d+(?:\.\d+)?)", band, re.I)
    if lead is None:
        return None
    numbers = [float(lead.group(1))]
    known = [*rule.listed, *rule.levels]
    if any(abs(n - k) < EPS for n in numbers for k in known):
        return None
    shown = " / ".join(f"{v:g}" for v in sorted(set(rule.listed), reverse=True))
    return f'BAND "{lead.group(1)}" is not a level of the methodology (levels: {shown}).'
