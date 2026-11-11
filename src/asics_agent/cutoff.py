"""The Law/Policy cut-off: which sources a Law/Policy question may use.

A question whose assessment level is Law/Policy may only use sources that took effect on or before
the category's cut-off date (parastatal.md: `law_cutoff: 2026-08-31`). The test is when the
provision or policy took effect, or the "amended up to" date of the cited text. It is never the web
page's "last updated" and never the date we fetched it.

Each Citation Sheet row says it in two columns:
  Effective / As-of Date  the date the cited text or version took effect (or "amended up to")
  Cut-off Check           ok | later | unknown | Bill-draft

How a source is used, for a Law/Policy question only:
  later       not shown to the model and cannot be cited (it stays in the sheet and may still be
              used for an Implementation question)
  Bill-draft  not usable as law in force
  unknown     used with a CONFIRM note and Confidence at most Medium (setting undated_law_policy:
              confirm), or treated like "later" (undated_law_policy: block)
If every available source is "later" or a Bill, the answer is Pending fetch with a one-line reason.

A year without a day ("an Act of 2025") is not a date: it is "unknown". Old Citation Sheets have
neither column; `check_of` then reads the Current/Active Status text, only to fill the gap.
"""

import re
from dataclasses import dataclass, field
from datetime import date

OK, LATER, UNKNOWN, BILL = "ok", "later", "unknown", "Bill-draft"
CHECKS = (OK, LATER, UNKNOWN, BILL)
NOT_LAW_FORMS = ("bill", "draft", "proposed", "ordinance draft")
MONTHS = {m: i for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}
# a clause about the web page or the fetch, not about when the provision took effect
_NOISE = re.compile(
    r"last[ -]?update[d]?|footer|snapshot|retrieved|fetched|accessed|printed|news|page itself|"
    r"live|submission deadline|audit period",
    re.I,
)
# words that say a date in a clause is about the law's own timing
_LEGAL_TIMING = re.compile(
    r"amend|enact|assent|commenc|in force|effective|w\.?e\.?f|notif|gazette|modified|as of|up to",
    re.I,
)


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def is_law_policy(level) -> bool:
    """True for a Law/Policy assessment level, in every spelling the banks use ("Law/policy",
    "Law or Policy", "Law/Policy & Implementation", "Law or Policy/Implementation"). Empty,
    "Implementation" and "NA- ..." are not."""
    text = _text(level).casefold()
    return "law" in text or text == "policy"


@dataclass(frozen=True)
class CutoffRule:
    day: date
    undated: str = "confirm"  # "confirm" | "block"

    @property
    def label(self) -> str:
        return f"{self.day.day} {self.day:%b %Y}"


def rule_from(settings) -> CutoffRule | None:
    """The category's cut-off rule, or None when it has none (the ULG today)."""
    day = getattr(settings, "law_cutoff", None)
    if not day:
        return None
    undated = getattr(settings, "undated_law_policy", "confirm")
    return CutoffRule(day, undated if undated in ("confirm", "block") else "confirm")


def cutoff_text(settings) -> str | None:
    """The cut-off as ISO text for run records (run_summary.json etc.), or None when there is none."""
    day = getattr(settings, "law_cutoff", None)
    return day.isoformat() if day else None


def describe(rule: CutoffRule) -> str:
    """One plain sentence for the Run steps page: what the cut-off does."""
    undated = (
        "used with a CONFIRM note, Confidence at most Medium"
        if rule.undated == "confirm"
        else "not used"
    )
    return (
        f"Law/Policy questions use only sources in force on or before {rule.label}. A source with "
        f"no effective date is {undated}. Change it in the category's settings file "
        "(law_cutoff, undated_law_policy)."
    )


def parse_date(text) -> date | None:
    """A full date in the text (2026-03-31, 31.03.2026, 31 Mar 2026, Mar 31, 2026), else None.
    A bare year or month is not a date."""
    t = _text(text)
    for y, m, d in re.findall(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t):
        try:
            return date(int(y), int(m), int(d))
        except ValueError:
            continue
    for d, m, y in re.findall(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b", t):
        try:
            return date(int(y), int(m), int(d))
        except ValueError:
            continue
    for d, m, y in re.findall(
        r"\b(\d{1,2})(?:st|nd|rd|th)?[ ,-]+([A-Za-z]{3})[a-z]*\.?,? ?(\d{4})\b", t
    ):
        if m.lower() in MONTHS:
            return date(int(y), MONTHS[m.lower()], int(d))
    for m, d, y in re.findall(r"\b([A-Za-z]{3})[a-z]*\.? (\d{1,2}),? (\d{4})\b", t):
        if m.lower() in MONTHS:
            return date(int(y), MONTHS[m.lower()], int(d))
    return None


def all_dates(text) -> list[date]:
    """Every full date in the text, in the order found."""
    out, rest = [], _text(text)
    while rest:
        d = parse_date(rest)
        if d is None:
            break
        out.append(d)
        # drop the first date written, so the next call finds the following one
        patterns = (
            r"\b\d{4}-\d{1,2}-\d{1,2}\b",
            r"\b\d{1,2}[./-]\d{1,2}[./-]\d{4}\b",
            r"\b\d{1,2}(?:st|nd|rd|th)?[ ,-]+[A-Za-z]{3}[a-z]*\.?,? ?\d{4}\b",
            r"\b[A-Za-z]{3}[a-z]*\.? \d{1,2},? \d{4}\b",
        )
        matches = [m for p in patterns if (m := re.search(p, rest))]
        if not matches:
            break
        first = min(matches, key=lambda m: m.start())
        rest = rest[: first.start()] + " " + rest[first.end() :]
    return out


def form_is_not_law(form: str) -> bool:
    f = _text(form).casefold()
    return any(w in f for w in NOT_LAW_FORMS)


def check_from(effective_date: str, form: str, rule: CutoffRule) -> str:
    """The Cut-off Check for a source's effective date and form (in force / Bill / draft)."""
    if form_is_not_law(form):
        return BILL
    day = parse_date(effective_date)
    if day is None:
        return UNKNOWN
    return OK if day <= rule.day else LATER


def assessment_fields(effective_date: str, form: str, rule: CutoffRule | None) -> tuple[str, str]:
    """(Effective / As-of Date, Cut-off Check) for a source the assessor has read. A date the
    assessor gave without a day is kept as written but checks as unknown."""
    effective = _text(effective_date)
    if rule is None:
        return effective, ""
    return effective, check_from(effective, form, rule)


def fallback_from_text(status: str, title: str, rule: CutoffRule) -> tuple[str, str]:
    """For an OLD Citation Sheet row (no new columns): (effective date as ISO text or "", check),
    read from the Current/Active Status text and the title. It ignores "last updated", footers
    and fetch dates, treats Bill-stage text as Bill-draft, and calls a year-only or undated row
    unknown. "later" only when the clause itself talks about amending or enacting."""
    s, t = _text(status), _text(title)
    if (re.search(r"\bBill\b", s) and "as enacted" not in s) or re.search(r"\bBILL\b", t):
        return "", BILL
    period = s.split("period=", 1)[1] if "period=" in s else s
    best: date | None = None
    for clause in re.split(r"[;]", period):
        if _NOISE.search(clause):
            continue
        for d in all_dates(clause):
            if d > rule.day and not _LEGAL_TIMING.search(clause):
                continue  # a date after the cut-off that is not about the law's timing
            if best is None or d > best:
                best = d
    if best is None:
        return "", UNKNOWN
    return best.isoformat(), (OK if best <= rule.day else LATER)


def check_of(source, rule: CutoffRule) -> str:
    """The Cut-off Check of a Citation Sheet row: its own column, else from its effective date,
    else (old rows) from the status text."""
    own = _text(getattr(source, "cutoff_check", ""))
    if own.casefold() in {c.casefold() for c in CHECKS}:
        return next(c for c in CHECKS if c.casefold() == own.casefold())
    effective = _text(getattr(source, "effective_date", ""))
    if effective:
        return check_from(effective, "", rule)
    return fallback_from_text(
        getattr(source, "current_status", ""), getattr(source, "title", ""), rule
    )[1]


@dataclass
class Screen:
    """The sources a question may use, and why the others are held back."""

    usable: list = field(default_factory=list)
    later: list[str] = field(default_factory=list)  # citation IDs not shown
    bills: list[str] = field(default_factory=list)
    blocked_unknown: list[str] = field(default_factory=list)  # held back by undated: block
    unknown: set[str] = field(default_factory=set)  # shown, with a CONFIRM note
    pending: str = ""  # the one-line reason when nothing is left although sources existed


def screen_sources(sources: list, rule: CutoffRule | None, law_policy: bool) -> Screen:
    """Apply the cut-off to the sources offered for one question. Only a Law/Policy question is
    restricted; for any other question every source is usable, whatever its check says."""
    out = Screen(usable=list(sources))
    if rule is None or not law_policy:
        return out
    out.usable = []
    for s in sources:
        check = check_of(s, rule)
        cid = getattr(s, "citation_id", "") or getattr(s, "title", "")
        if check == LATER:
            out.later.append(cid)
        elif check == BILL:
            out.bills.append(cid)
        elif check == UNKNOWN and rule.undated == "block":
            out.blocked_unknown.append(cid)
        else:
            out.usable.append(s)
            if check == UNKNOWN:
                out.unknown.add(cid)
    held = out.later + out.bills + out.blocked_unknown
    if sources and not out.usable and held:
        parts = []
        if out.later:
            parts.append(f"dated after {rule.label} ({', '.join(out.later[:4])})")
        if out.bills:
            parts.append(f"a Bill or draft, not law in force ({', '.join(out.bills[:4])})")
        if out.blocked_unknown:
            parts.append(f"undated ({', '.join(out.blocked_unknown[:4])})")
        out.pending = (
            f"every available source is {' or '.join(parts)}: fetch the version in force on "
            f"{rule.label}."
        )
    return out


def confirm_note(citation_id: str, rule: CutoffRule) -> str:
    return (
        f"CONFIRM: {citation_id} has no effective date, so it cannot be shown to be in force on "
        f"{rule.label}. Confidence is at most Medium."
    )


def cap_confidence(confidence: str) -> str:
    """Confidence at most Medium (High becomes Medium; Medium, Low and empty stay)."""
    return "Medium" if _text(confidence).casefold() == "high" else confidence


def period_after_cutoff(answer_text: str, rule: CutoffRule) -> date | None:
    """A date after the cut-off in the answer's own `PERIOD:` part, else None. Fetch, access and
    "last updated" dates are ignored: only the period of the law matters."""
    match = re.search(r"PERIOD:\s*(.*?)(?:\|\s*LIMITS:|$)", _text(answer_text), re.S | re.I)
    if not match:
        return None
    for clause in re.split(r"[;,]", match.group(1)):
        if _NOISE.search(clause):
            continue
        for d in all_dates(clause):
            if d > rule.day:
                return d
    return None
