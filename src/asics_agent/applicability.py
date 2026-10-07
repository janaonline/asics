"""Maps a question's free-text "Applicability" to the parastatals it applies to.

Rules are checked in order; the first match wins. Add a rule here when the question
bank introduces a new applicability phrase — initial checks flag any phrase that no
rule recognises.
"""

from collections.abc import Callable

from asics_agent.models import Parastatal, Question

Rule = tuple[str, Callable[[Parastatal], bool]]

RULES: list[Rule] = [
    ("excluding development authorities", lambda p: p.type != "development_authority"),
    ("water supply board", lambda p: p.type == "water_supply_board"),
    ("transport corporation", lambda p: p.type == "transport_corporation"),
    ("development authorit", lambda p: p.type == "development_authority"),
    ("revenue-raising", lambda p: p.revenue_raising),
    ("capital-expenditure mandate", lambda p: p.capex_mandate),
    ("with an annual budget", lambda p: p.has_annual_budget),
    ("chief executive", lambda p: p.has_chief_executive),
    ("common", lambda p: True),
]


def match_rule(applicability: str) -> Rule | None:
    text = applicability.lower()
    return next((rule for rule in RULES if rule[0] in text), None)


def applies_to(question: Question, parastatal: Parastatal) -> bool | None:
    """True/False, or None when the applicability text is not recognised."""
    rule = match_rule(question.applicability)
    return None if rule is None else rule[1](parastatal)
