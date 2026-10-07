"""Runs the master agent in the background and reports progress in plain language.

Used by the app (and usable from any other front end). One `PipelineRun` = one run of
the master agent; it pauses at the review step until `submit_review()` is called.
"""

import logging
import threading
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

import anthropic
import httpx
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.types import Command

from asics_agent.agents.answers_master import build_answers_graph
from asics_agent.agents.sources_master import build_sources_graph
from asics_agent.run_options import RunOptions
from asics_agent.services import Services

Status = Literal["running", "waiting_for_review", "finished", "failed"]

Step = Literal["sources", "answers"]
STEP_NAMES = {
    "sources": "Step 1: Find parastatals and sources",
    "answers": "Step 2: Answer questions",
}

STEP_DONE = {
    "initial_checks": "Checked the question bank and inputs",
    "parastatal_discovery": "Found the city's parastatals and checked their websites",
    "finalize_sources": "Ran the final checks and wrote the Sources workbook",
    "prepare_citations": "Loaded the Citation Sheet from the Sources workbook",
    "finalize_answers": "Ran the final checks and wrote the answers workbook",
}


def friendly_error(exc: Exception) -> str:
    if isinstance(exc, anthropic.AuthenticationError):
        return (
            "The Anthropic API key is missing or not valid. Ask your developer to check "
            "the ANTHROPIC_API_KEY setting in the .env file."
        )
    if isinstance(exc, anthropic.RateLimitError):
        return "Too many requests to Anthropic right now. Wait a few minutes, then try again."
    if isinstance(exc, anthropic.APIConnectionError | httpx.ConnectError):
        return "Couldn't connect to the internet or to Anthropic. Check your connection."
    if isinstance(exc, FileNotFoundError):
        return f"A file couldn't be found: {exc}"
    return (
        f"Something went wrong ({type(exc).__name__}). Your developer can see the details "
        "in outputs/app_errors.log."
    )


def new_checkpointer() -> InMemorySaver:
    """Saves the run's state at the review pause. Our own data types are allowed explicitly,
    because LangGraph will stop restoring unregistered types from checkpoints."""
    import asics_agent.models as models

    allowed = [
        (models.__name__, name)
        for name in (
            "Question",
            "Parastatal",
            "WebsiteCheck",
            "CityConfig",
            "RunContext",
            "AccessCheck",
            "Source",
            "Answer",
            "Issue",
        )
    ]
    return InMemorySaver(serde=JsonPlusSerializer(allowed_msgpack_modules=allowed))


class PipelineRun:
    def __init__(
        self,
        services: Services,
        inputs: dict,
        label: str,
        step: Step = "sources",
        options: RunOptions | None = None,
    ):
        self.id = uuid.uuid4().hex[:8]
        self.label = label
        self.step = step
        self.options = options or RunOptions()
        self.inputs = inputs
        self.started = datetime.now()
        self.status: Status = "running"
        self.log: list[str] = []
        self.links_done = self.links_total = 0
        self.answers_done = self.answers_total = 0
        self.review: dict | None = None
        self.activity: dict[str, tuple[datetime, str]] = {}  # latest live message per item
        self.last_event = datetime.now()
        self.result: dict | None = None
        self.error: str | None = None
        self._services = services
        build = build_sources_graph if step == "sources" else build_answers_graph
        self._graph = build(services, checkpointer=new_checkpointer())
        self._config = {
            "configurable": {"thread_id": self.id},
            "max_concurrency": services.settings.max_concurrency,
            "recursion_limit": 500,
        }

    # -- public -------------------------------------------------------------------------
    def start(self) -> "PipelineRun":
        """Run in a background thread until the review pause (or the end)."""
        threading.Thread(target=self.run_until_pause, daemon=True).start()
        return self

    def submit_review(self, decision: dict) -> None:
        """Continue in a background thread after the review."""
        self.status = "running"
        threading.Thread(target=self.resume, args=(decision,), daemon=True).start()

    def run_until_pause(self) -> None:
        """Run in the calling thread until the review pause (or the end)."""
        self._say("Started")
        self._drive(self.inputs)

    def resume(self, decision: dict) -> None:
        """Continue in the calling thread after the review."""
        review, self.review, self.status = self.review or {}, None, "running"
        action = decision.get("action", "approve")
        if action == "stop":
            self._say(
                "Review done: stopped here. The parastatals found will be saved; no "
                "sources will be researched."
            )
        else:
            count = (
                len(decision.get("parastatals") or [])
                if action == "edit"
                else len(review.get("parastatals", []))
            )
            self._say(
                f"Review done. Now building the Citation Sheet for {count} "
                f"parastatal(s). Each one takes several minutes; up to "
                f"{self._services.settings.max_concurrency} are worked on at the same "
                "time. Progress appears below."
            )
        self._drive(Command(resume=decision))

    @property
    def issues(self) -> list:
        values = self.result or {}
        return values.get("final_issues") or values.get("issues", [])

    @property
    def answers(self) -> list:
        values = self.result or {}
        return values.get("answers", []) + values.get("rollups", [])

    @property
    def blocked(self) -> bool:
        """Finished without a workbook: the initial checks found a problem to fix first."""
        return self.status == "finished" and not (self.result or {}).get("output_workbook")

    @property
    def output_dir(self) -> Path | None:
        values = self.result or {}
        return Path(values["output_workbook"]).parent if values.get("output_workbook") else None

    # -- internals ----------------------------------------------------------------------
    def _say(self, message: str) -> None:
        self.log.append(f"{datetime.now():%H:%M}  {message}")

    def _values(self) -> dict:
        return self._graph.get_state(self._config).values

    def _drive(self, payload) -> None:
        try:
            for namespace, mode, chunk in self._graph.stream(
                payload,
                self._config,
                stream_mode=["updates", "custom"],
                subgraphs=True,
                context=self.options,
            ):
                self.last_event = datetime.now()
                if mode == "custom":
                    self._on_activity(chunk)
                else:
                    self._on_update(namespace, chunk)
            snapshot = self._graph.get_state(self._config)
            if snapshot.interrupts:
                self.review = snapshot.interrupts[0].value
                self.status = "waiting_for_review"
                self._say("Waiting for you to review the parastatals")
            else:
                self.result = snapshot.values
                self.status = "finished"
                self._say("Finished")
        except Exception as exc:  # shown to the user in plain language
            log = self._services.settings.outputs_dir / "app_errors.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open("a") as fh:
                fh.write(f"\n--- {datetime.now()} run {self.id}\n{traceback.format_exc()}")
            logging.exception("run %s failed", self.id)
            self.error, self.status = friendly_error(exc), "failed"
            self._say("Stopped because of a problem")

    def _on_activity(self, chunk: dict) -> None:
        """Live messages from inside the agents (see progress.py)."""
        activity = chunk.get("activity") if isinstance(chunk, dict) else None
        if not activity:
            return
        key, text = activity["key"], activity["text"]
        self.activity[key] = (datetime.now(), text)
        if not text.startswith(("Checking", "Re-checking earlier links")):  # milestones only
            self._say(f"{key}: {text}")

    def _on_update(self, namespace: tuple, chunk: dict) -> None:
        for node, update in chunk.items():
            if node == "__interrupt__":
                continue
            if namespace:
                if node == "discover":
                    found = (update or {}).get("parastatals", [])
                    self._say(
                        f"Found {len(found)} parastatal(s): " + ", ".join(p.id for p in found)
                    )
                elif node == "profile_parastatal":
                    for p in (update or {}).get("profiled", []):
                        check = p.website_check
                        site = (
                            f"website {check.url} scored {check.score}/100 ({check.band})"
                            if check
                            else "no website found"
                        )
                        self._say(f"Checked {p.id}: {site}")
                continue
            if node == "confirm_scope":
                values = self._values()
                only = set(values.get("only_parastatals") or [])
                self.links_total = sum(
                    1
                    for p in values.get("parastatals", [])
                    if p.include and (not only or p.id in only)
                )
            elif node == "links_agent":
                self.links_done += 1
                self._say(
                    f"Built the Citation Sheet for {self.links_done} of "
                    f"{self.links_total} parastatal(s)"
                )
            elif node == "prepare_citations":
                # Read the matrix from this update: the saved state may not include it yet.
                questions = self._values().get("questions", {})
                applicability = (update or {}).get("applicability", {})
                self.answers_total = sum(
                    1
                    for ids in applicability.values()
                    for q in ids
                    if q in questions and not questions[q].is_rollup
                )
                self._say(STEP_DONE[node])
                self._say(f"Answering {self.answers_total} questions from the Citation Sheet…")
            elif node.startswith("answer_"):
                self.answers_done += 1
                if self.answers_done % 5 == 0 or self.answers_done == self.answers_total:
                    self._say(f"Answered {self.answers_done} of {self.answers_total} questions")
            if node in STEP_DONE and node != "prepare_citations":
                self._say(STEP_DONE[node])


class BatchRun:
    """Runs one step for several cities, one after another, with a single review.

    Step 1 (sources): each city runs until its review pause (its parastatals have been found
    by then); the reviewer approves all cities at once; each city's Citation Sheet is then
    built in turn, giving one Sources workbook per city.
    Step 2 (answers): each city is answered in turn from its Sources workbook, giving one
    answers workbook per city. There is no review pause.
    Each city's files live in outputs/cities/<City>/; the batch folder holds an index.
    """

    def __init__(
        self,
        services: Services,
        cities: dict[str, str],
        inputs: dict,
        parastatals: dict[str, list[str]] | None = None,
        label: str = "Run",
        step: Step = "sources",
        options: RunOptions | None = None,
    ):
        self.started = datetime.now()
        self.id = f"{self.started:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}"
        self.label = label
        self.step = step
        self.options = options or RunOptions()
        self.folder = services.settings.outputs_dir / "batches" / self.id
        self.status: Status = "running"
        self.current: str | None = None  # city slug being worked on
        self.summary_path: Path | None = None
        self.error: str | None = None
        self._services = services
        self.runs: dict[str, PipelineRun] = {
            slug: PipelineRun(
                services,
                {**inputs, "city": slug, "only_parastatals": (parastatals or {}).get(slug)},
                name,
                step,
                options,
            )
            for slug, name in cities.items()
        }

    def start(self) -> "BatchRun":
        threading.Thread(target=self._first_half, daemon=True).start()
        return self

    def submit_review(self, decisions: dict[str, dict]) -> None:
        """`decisions` maps city slug -> {"action": "approve" | "stop"} or
        {"action": "edit", "parastatals": [ids to keep]}."""
        self.status = "running"
        threading.Thread(target=self._second_half, args=(decisions,), daemon=True).start()

    @property
    def reviews(self) -> dict[str, dict]:
        return {slug: r.review for slug, r in self.runs.items() if r.status == "waiting_for_review"}

    def _first_half(self) -> None:
        for slug, run in self.runs.items():
            self.current = slug
            run.run_until_pause()
        self.current = None
        if self.reviews:
            self.status = "waiting_for_review"
        else:
            self._finish()

    def _second_half(self, decisions: dict[str, dict]) -> None:
        for slug, run in self.runs.items():
            if run.status == "waiting_for_review":
                self.current = slug
                run.resume(decisions.get(slug, {"action": "approve"}))
        self.current = None
        self._finish()

    def _finish(self) -> None:
        from asics_agent.workbook import write_batch_summary

        try:
            self.summary_path = write_batch_summary(self.folder, self.label, self.runs, self.step)
            self.status = "finished"
        except Exception as exc:
            logging.exception("batch summary failed")
            self.error, self.status = friendly_error(exc), "failed"
