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
from asics_agent.usage import METER, UsageMeter

UNITS = {1: "agency", 2: "answer", 3: "row"}
# US$ per unit when there is no earlier run: Step 1 ~$2.60 per agency (estimate after the
# Oct 2026 limits); Step 2 $0.076 per answer live (measured), half that with batches;
# Step 3 $0.029 per row (measured).
DEFAULT_RATES = {1: 2.60, 2: 0.076, 3: 0.029}
DEFAULT_AGENCIES = 7  # a city's parastatals before Step 1 has found them (Bengaluru had 7)


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


def rate(settings, step: int, category: str) -> tuple[float, str, bool]:
    """(US$ per unit, what it is based on, is it a starting figure)."""
    runs = [r for r in history(settings) if r.step == step and r.work and r.total]
    same = [r for r in runs if r.category == category]
    for r in same or runs:
        other = "" if r in same else f" for {r.category_title or r.category}"
        return r.per_unit, f"your last Step {step} run{other}, {r.when:%d %b}", False
    usd = DEFAULT_RATES[step]
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
    return Estimate(usd * work, [line], first)


def combine(parts: list[Estimate]) -> Estimate:
    return Estimate(
        sum(p.usd for p in parts),
        [line for p in parts for line in p.lines],
        any(p.first_time for p in parts),
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
