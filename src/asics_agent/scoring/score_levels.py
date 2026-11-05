"""The scores a typed-points question may take, read from its methodology.

A typed-points question has a Points cell that takes any number from 0 to the Max Score (its data
validation), so the template alone does not say which scores make sense. The methodology does, for
most questions: "Score 5: ... Score 2.5: ... Score 0: ...". Two kinds:

  levels  the methodology lists whole-question levels (at least two, one of them 0): the AI's score
          must be one of them, exactly as a person would type it into the cell. A level the cell
          cannot take (above the Max Score) is entered as the Max Score; nothing is scaled.
  free    the score is built from parts that are added up ("Part A ... Part B ..."), or the levels
          are missing or do not fit the Max Score: any number from 0 to the Max Score is allowed
          (the range check only).
"""

import re
from dataclasses import dataclass

from asics_agent.scoring.bands import LEVEL

EPS = 1e-6
_INLINE = re.compile(r"(?<!\d)(?<!\d[.,])(\d+(?:\.\d+)?)\s*[—–]\s")  # "10 — full credit"
_WHERE = re.compile(
    r"\bScore\s+(\d+(?:\.\d+)?)\s*,?\s*(?:where|if|when)\b", re.I
)  # "Score 3.33, if"
_PART = re.compile(r"\bPart\s+([A-Z])\b")  # "Part A: ..." "Part B: ..."


def _num(value: float) -> str:
    return f"{value:g}"


@dataclass(frozen=True)
class LevelRule:
    kind: str  # "levels" | "free"
    max_score: float
    levels: tuple[float, ...] = ()  # allowed scores, highest first (kind "levels")
    listed: tuple[float, ...] = ()  # the levels the methodology lists, as written
    basis: str = ""

    def allows(self, score: float) -> bool:
        return self.kind != "levels" or any(abs(score - v) < EPS for v in self.levels)

    def allowed_text(self, sep: str = " / ") -> str:
        return sep.join(_num(v) for v in self.levels)

    @property
    def above_max(self) -> bool:
        return any(v > self.max_score + EPS for v in self.listed)

    def describe(self) -> str:
        """For the coverage CSV."""
        if self.kind == "levels":
            text = self.allowed_text(" | ")
            if self.listed and tuple(sorted(self.listed, reverse=True)) != self.levels:
                text += (
                    f" (methodology lists {' | '.join(_num(v) for v in sorted(self.listed, reverse=True))}; "
                    f"the cell takes 0 to {_num(self.max_score)}, so the top level is entered as "
                    f"{_num(self.max_score)} and the others as written)"
                )
            return text
        return f"free / partial credit: range check 0 to {_num(self.max_score)} only ({self.basis})"


def score_levels(methodology: str, max_score: float) -> LevelRule:
    text = methodology or ""
    listed = tuple(
        sorted(
            {float(v) for v in LEVEL.findall(text) + _INLINE.findall(text) + _WHERE.findall(text)}
        )
    )
    parts = sorted(set(_PART.findall(text)))
    if len(parts) >= 2:
        return LevelRule(
            "free",
            max_score,
            listed=listed,
            basis=f"parts are added up: Part {', Part '.join(parts)}",
        )
    if len(listed) < 2 or 0.0 not in listed:
        found = " / ".join(_num(v) for v in listed) or "none"
        return LevelRule(
            "free", max_score, listed=listed, basis=f"levels listed: {found}; need 0 and another"
        )
    top = max(listed)
    if top < max_score - EPS:
        return LevelRule(
            "free",
            max_score,
            listed=listed,
            basis=f"top level {_num(top)} is below the Max Score {_num(max_score)}",
        )
    above = [v for v in listed if v > max_score + EPS]
    if len(above) > 1:
        return LevelRule(
            "free",
            max_score,
            listed=listed,
            basis="more than one level is above the Max Score, which the cell cannot take",
        )
    allowed = {round(v, 4) for v in listed if v <= max_score + EPS}
    if above:
        allowed.add(round(max_score, 4))
    return LevelRule("levels", max_score, tuple(sorted(allowed, reverse=True)), listed, "")
