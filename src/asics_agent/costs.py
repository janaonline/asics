"""What each run cost, and what the next one will probably cost.

Every run started from the app or the command line saves a cost record in
outputs/_app/usage/: the step, category and cities, how much work it covered and the tokens
and US$ it used (usage.py prices them). The Costs page lists them.

Before a run starts, `estimate` multiplies the work planned by the cost per unit of work of
the last run of the same step and category:

    Step 1  per agency researched (the ULG category has one unit per city)
    Step 2  per answer
    Step 3  per row scored

Until there is a real run to go by, it uses the starting figures in DEFAULT_RATES, measured
on Bengaluru (October 2026, Claude Sonnet 5.5).
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from asics_agent.categories import ULG_UNIT_ID
from asics_agent.legacy_names import canonical_category, read_key
from asics_agent.usage import CACHE_WRITE, METER, PRICES, UsageMeter

UNITS = {1: "agency", 2: "answer", 3: "row"}
# US$ per unit when there is no earlier run: Step 1 ~$2.60 per agency (estimate after the
# Oct 2026 limits); Step 2 $0.076 per answer live (measured), half that with batches;
# Step 3 $0.029 per row (measured).
DEFAULT_RATES = {1: 2.60, 2: 0.076, 3: 0.029}
DEFAULT_AGENCIES = 7  # a city's parastatals before Step 1 has found them (Bengaluru had 7)

# Tokens from characters. The spikes measured real token counts of about characters / 2.5 for these
# pages (Indian-government English with tables and numbers), not the usual / 4.
CHARS_PER_TOKEN = 2.5
TOOL_LOOP_TURNS = (
    3  # [assumption] model calls in one answer's tool loop; the first real run replaces it
)
# [assumptions, calibrated so Claude Sonnet 5.5 comes to about the measured $0.076 per answer live]
EVIDENCE_FILL = 0.5  # the evidence a typical answer reads, as a share of `max_evidence_chars`
PROMPT_TOKENS = 6000  # instructions, question and tool descriptions sent with every call
ANSWER_OUTPUT_TOKENS = 2000  # the answer and its thinking


def tokens_for(chars: float) -> float:
    """Tokens in `chars` characters of page text (2.5 characters a token)."""
    return chars / CHARS_PER_TOKEN


def step2_default(settings, turns: int = TOOL_LOOP_TURNS) -> float:
    """US$ per answer, live, when there is no earlier Step 2 run: the first call of the tool loop writes the
    evidence to the prompt cache (1.25x input), the later ones read it (a tenth), plus the answer."""
    price = next(
        (p for m, p in PRICES.items() if str(getattr(settings, "model", "")).startswith(m)), None
    )
    if price is None:
        return DEFAULT_RATES[2]
    inp, out, read = price
    context = PROMPT_TOKENS + tokens_for(
        EVIDENCE_FILL * getattr(settings, "max_evidence_chars", 60000)
    )
    first = context * inp * CACHE_WRITE
    later = context * read * max(turns - 1, 0)
    return (first + later + ANSWER_OUTPUT_TOKENS * out) / 1_000_000


def usage_dir(settings) -> Path:
    from asics_agent.outputs_index import app_dir

    path = app_dir(settings) / "usage"
    path.mkdir(parents=True, exist_ok=True)
    return path


# -- recording ------------------------------------------------------------------------------
class RunMeter:
    """The tokens one run uses: what the shared meter counted from start() to stop()."""

    def __init__(self):
        self._start = METER.snapshot()

    def usage(self) -> UsageMeter:
        return METER.since(self._start)


def record_run(
    settings,
    meter: RunMeter,
    *,
    step: int,
    label: str,
    cities: list[str],
    work: int,
    started: datetime,
    group: str | None = None,
) -> Path | None:
    """Save the run's cost record; nothing is saved for a run that made no paid calls
    (practice runs, checks)."""
    usage = meter.usage()
    if not usage.by_model:
        return None
    record = {
        "kind": "run",
        "step": step,
        "category": getattr(settings, "category", ""),
        "category_title": getattr(settings, "category_title", ""),
        "label": label,
        "cities": cities,
        "work": work,
        "unit": UNITS[step],
        "started": started.isoformat(timespec="seconds"),
        "finished": datetime.now().isoformat(timespec="seconds"),
        "group": group,
        "total_usd": round(usage.total(), 4),
        "by_model": {m: {**vars(u), "usd": u.cost(m)} for m, u in usage.by_model.items()},
        "by_agent": {
            a: {**vars(u), "usd": u.cost(a.split(" · ")[-1])} for a, u in usage.by_agent.items()
        },
    }
    path = (
        usage_dir(settings) / f"{datetime.now():%Y%m%d-%H%M%S}_step{step}_{record['category']}.json"
    )
    path.write_text(json.dumps(record, indent=2, default=str))
    return path


# -- history --------------------------------------------------------------------------------
@dataclass
class CostRecord:
    path: Path
    when: datetime
    label: str
    total: float
    step: int | None = None
    category: str = ""
    category_title: str = ""
    cities: list[str] = field(default_factory=list)
    work: int = 0
    unit: str = ""
    group: str | None = None
    by_agent: dict = field(default_factory=dict)

    @property
    def per_unit(self) -> float | None:
        return self.total / self.work if self.work else None


def history(settings) -> list[CostRecord]:
    """Every saved cost record, newest first (older command-line records have no step)."""
    records = []
    for path in usage_dir(settings).glob("*.json"):
        try:
            data = json.loads(path.read_text())
            when = (
                datetime.fromisoformat(data["started"])
                if data.get("started")
                else datetime.strptime(path.name[:15], "%Y%m%d-%H%M%S")
            )
        except (ValueError, KeyError, OSError):
            continue
        label, step = data.get("label", path.stem), data.get("step")
        if step is None:  # saved by the command line before runs recorded their step
            step = 2 if label == "step_answers" else 3 if label.startswith("step3") else None
            label = {2: "Step 2 (command line)", 3: "Step 3 (command line)"}.get(step, label)
        records.append(
            CostRecord(
                path=path,
                when=when,
                label=label,
                total=float(data.get("total_usd") or 0),
                step=step,
                category=canonical_category(read_key(data, "category")),
                category_title=read_key(data, "category_title"),
                cities=data.get("cities", []),
                work=int(data.get("work") or 0),
                unit=data.get("unit", ""),
                group=data.get("group"),
                by_agent=data.get("by_agent", {}),
            )
        )
    return sorted(records, key=lambda r: r.when, reverse=True)


def group_total(settings, group: str) -> float | None:
    """What all the stages of one Run steps run cost, so far."""
    parts = [r.total for r in history(settings) if r.group == group]
    return sum(parts) if parts else None


# -- estimating -----------------------------------------------------------------------------
@dataclass
class Estimate:
    usd: float
    lines: list[str]  # one plain line per part: what it is based on
    first_time: bool  # no earlier run to go by: starting figures were used
    # Possible extra costs that are not in `usd` (scan reading: only if scanned PDFs are found)
    extra_lines: list[str] = field(default_factory=list)


def rate(settings, step: int, category: str) -> tuple[float, str, bool]:
    """(US$ per unit, what it is based on, is it a starting figure)."""
    runs = [r for r in history(settings) if r.step == step and r.work and r.total]
    same = [r for r in runs if r.category == category]
    for r in same or runs:
        other = "" if r in same else f" for {r.category_title or r.category}"
        return r.per_unit, f"your last Step {step} run{other}, {r.when:%d %b}", False
    usd = step2_default(settings) if step == 2 else DEFAULT_RATES[step]
    if step == 2 and getattr(settings, "batch_answers", False):
        usd /= 2
    return usd, "starting estimate: no run to go by yet", True


def plural(n: int, unit: str) -> str:
    return f"{n} {unit if n == 1 else ('agencies' if unit == 'agency' else unit + 's')}"


def estimate(settings, step: int, work: int) -> Estimate:
    usd, basis, first = rate(settings, step, getattr(settings, "category", ""))
    title = getattr(settings, "category_title", "") or getattr(settings, "category", "")
    line = (
        f"Step {step} · {title}: {plural(work, UNITS[step])} × ${usd:.3f} = "
        f"${usd * work:,.2f} ({basis})"
    )
    return Estimate(usd * work, [line], first, scan_allowance(settings, step, title))


def scan_allowance(settings, step: int, title: str = "") -> list[str]:
    """The line about what reading scanned PDFs could add to a Step 1 run (an upper bound: the budget)."""
    budget = float(getattr(settings, "scan_reading_budget_usd", 0) or 0)
    if step != 1 or budget <= 0 or not getattr(settings, "staged_fetch", False):
        return []
    return [
        f"Step 1 · {title}: plus up to ${budget:,.2f} more if scanned PDFs are found and Claude reads "
        "them (the scan_reading_budget_usd setting; a document that does not fit is skipped). Not "
        "included in the total above."
    ]


def combine(parts: list[Estimate]) -> Estimate:
    extras: list[str] = []
    for p in parts:
        extras += [line for line in p.extra_lines if line not in extras]
    return Estimate(
        sum(p.usd for p in parts),
        [line for p in parts for line in p.lines],
        any(p.first_time for p in parts),
        extras,
    )


# -- the work a run will do -----------------------------------------------------------------
def city_units(settings, city) -> list:
    """The units a city's run covers: the included agencies in its Sources workbook, the
    city government for the one-unit ULG category, or a typical number if Step 1 hasn't run."""
    from asics_agent.models import Parastatal
    from asics_agent.sources_workbook import read_sources_workbook, sources_path, workspace_for

    if getattr(settings, "unit", "parastatal") == "ulg":
        return [Parastatal(id=ULG_UNIT_ID, name=city.name, type="other")]
    workspace = workspace_for(settings.outputs_dir, city.name)
    path = sources_path(workspace, city.name)
    if path.exists():
        parastatals, _, _ = read_sources_workbook(path, workspace / "evidence")
        if included := [p for p in parastatals if p.include]:
            return included
    known = [p for p in city.parastatals if p.include]
    return known + [None] * max(0, DEFAULT_AGENCIES - len(known))  # None: not found yet


def planned_answers(settings, city, questions: dict, codes=None) -> int:
    """Answers (and rows to score) a city will have: each question for each unit it applies
    to; `codes` limits it to some questions."""
    from asics_agent.applicability import applies_to

    def norm(code) -> str:
        return str(code).replace(" ", "").replace("-", "").upper()

    chosen = {norm(c) for c in codes or ()}
    wanted = [
        q
        for q in questions.values()
        if not q.is_rollup and (not chosen or norm(q.id) in chosen or norm(q.raw_id) in chosen)
    ]
    return sum(
        1
        for p in city_units(settings, city)
        for q in wanted
        if p is None or applies_to(q, p) is not False
    )
