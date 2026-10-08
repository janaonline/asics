"""One run across verticals, cities and steps: e.g. Parastatal and UPD, for Bengaluru and
Surat, Steps 1, 2 and 3.

Stages run in step order, each step for every chosen vertical:

  Step 1 · Parastatal → Step 1 · UPD → [team reviews the Sources workbooks]
  → Step 2 · Parastatal → Step 2 · UPD → Step 3 · Parastatal → Step 3 · UPD

Steps 1 and 2 are ordinary `BatchRun`s (with Step 1's review of the parastatals found, unless
switched off); Step 3 is the AI scorer. A stage only does what its gate allows: Step 2 needs
the city's Sources workbook, and Step 3 only scores cities whose Step 2 is up to date, so a
city that failed an earlier step is reported, not forced through.

Optionally the plan pauses after Step 1 so the team can review the Sources workbooks (the
Citation Sheet) before anything is answered: the designed control point of the process.
"""

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from asics_agent.run_options import RunOptions
from asics_agent.runner import BatchRun, friendly_error

STEP_TITLES = {1: "Find sources", 2: "Answer questions", 3: "Score"}


@dataclass
class Stage:
    step: int
    vertical: str  # vertical name, e.g. "upd"
    title: str  # e.g. "Step 2 · UPD · Answer questions"
    status: str = "waiting"  # waiting | running | needs_review | done | failed | skipped
    note: str = ""  # outcome, in plain language
    batch: BatchRun | None = None
    report: object | None = None  # Step 3's StepReport
    progress: tuple[int, int] = (0, 0)  # Step 3 rows scored / total


@dataclass
class PlanRun:
    """Runs the stages in a background thread. The app shows `stages`, the current batch's
    live progress, and its review; `continue_after_review()` resumes after the pause."""

    settings: object  # base settings; each stage uses settings_for(vertical)
    verticals: list[str]
    cities: dict[str, str]  # slug -> name
    steps: list[int]
    practice: bool = False
    review_parastatals: bool = True  # Step 1: pause to review the parastatals found
    pause_after_sources: bool = True  # pause after Step 1 for the Sources workbook review
    options: RunOptions = field(default_factory=RunOptions)
    services_for: object = None  # (vertical settings) -> Services; injectable for tests
    stages: list[Stage] = field(default_factory=list)
    status: str = "running"  # running | waiting_for_review | waiting_for_sources | finished
    error: str | None = None

    def __post_init__(self):
        from asics_agent.verticals import load_verticals

        self.started = datetime.now()
        self.id = f"{self.started:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}"
        found, _ = load_verticals(self.settings.agent_setup_dir)
        titles = {name: found[name].title if name in found else name for name in self.verticals}
        self.stages = [
            Stage(step, v, f"Step {step} · {titles[v]} · {STEP_TITLES[step]}")
            for step in sorted(self.steps)
            for v in self.verticals
        ]
        where = (
            next(iter(self.cities.values()))
            if len(self.cities) == 1
            else f"{len(self.cities)} cities"
        )
        self.label = (
            f"{'Practice · ' if self.practice else ''}Steps "
            f"{', '.join(str(s) for s in sorted(self.steps))} · "
            f"{', '.join(titles.values())} · {where}"
        )
        self._resume = threading.Event()

    # -- what the app reads -----------------------------------------------------------------
    @property
    def current(self) -> Stage | None:
        return next((s for s in self.stages if s.status in {"running", "needs_review"}), None)

    @property
    def batch(self) -> BatchRun | None:
        stage = self.current
        return stage.batch if stage else None

    # -- control ---------------------------------------------------------------------------
    def start(self) -> "PlanRun":
        threading.Thread(target=self._run, daemon=True, name=f"plan-{self.id}").start()
        return self

    def continue_after_review(self) -> None:
        """The team has reviewed the Sources workbooks: go on to Step 2."""
        self.status = "running"
        self._resume.set()

    # -- the work --------------------------------------------------------------------------
    def _settings(self, vertical: str):
        from asics_agent.verticals import settings_for

        return settings_for(self.settings, vertical)

    def _services(self, vs):
        if self.services_for:
            return self.services_for(vs)
        if self.practice:
            from asics_agent.practice import practice_services

            return practice_services(vs, delay=1.5)
        from asics_agent.services import default_services

        return default_services(vs)

    def _run(self) -> None:
        try:
            for stage in self.stages:
                if (
                    stage.step == 2
                    and self.pause_after_sources
                    and 1 in self.steps
                    and not self._resume.is_set()
                ):
                    self.status = "waiting_for_sources"
                    self._resume.wait()
                    self.status = "running"
                stage.status = "running"
                if stage.step in (1, 2):
                    self._batch(stage)
                else:
                    self._score(stage)
            self.status = "finished"
        except Exception as exc:  # shown in plain language; details in the log
            logging.exception("plan %s failed", self.id)
            self.error, self.status = friendly_error(exc), "failed"
            for stage in self.stages:
                if stage.status in {"running", "needs_review"}:
                    stage.status, stage.note = "failed", self.error

    def _batch(self, stage: Stage) -> None:
        from asics_agent.workbook import city_outcome

        vs = self._settings(stage.vertical)
        step = "sources" if stage.step == 1 else "answers"
        inputs = {
            "only_pillars": None,
            "only_questions": ["UPD 1"] if self.practice else None,
            "auto_approve": not self.review_parastatals,
        }
        stage.batch = BatchRun(
            self._services(vs),
            self.cities,
            inputs,
            None,
            label=stage.title,
            step=step,
            options=self.options,
        ).start()
        while stage.batch.status in {"running", "waiting_for_review"}:
            waiting = stage.batch.status == "waiting_for_review"
            stage.status = "needs_review" if waiting else "running"
            self.status = "waiting_for_review" if waiting else "running"
            time.sleep(1)
        self.status = "running"
        if stage.batch.status == "failed":
            stage.status, stage.note = "failed", stage.batch.error or "Stopped"
            return
        outcomes = [f"{r.label}: {city_outcome(r)}" for r in stage.batch.runs.values()]
        stage.status, stage.note = "done", "; ".join(outcomes)

    def _score(self, stage: Stage) -> None:
        from asics_agent.scoring import workflow

        vs = self._settings(stage.vertical)

        def progress(i, n):
            stage.progress = (i, n)

        report = workflow.ai_score(
            vs,
            vs.vertical_code,
            cities=list(self.cities.values()),
            practice=self.practice,
            on_progress=progress,
        )
        stage.report = report
        stage.status = "done" if report.done else "skipped"
        stage.note = " ".join(report.done) or "; ".join(report.problems[-2:])
