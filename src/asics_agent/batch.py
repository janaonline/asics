"""Step 2 through Anthropic's Message Batches API: the same calls at half the price.

Step 2's answers are independent and nobody waits on any single one, so instead of sending
each model call on its own, the Batcher collects them and sends them together as one
Message Batch. Every answer's agent loop runs as usual in its own thread; its model call
just waits here until its batch has finished. An answer that calls a tool (read_citation…)
then sends its next turn, and those turns go out together as the next batch.

    answers start ─▶ batch 1 (first turns) ─▶ tools run ─▶ batch 2 (next turns) ─▶ …

A batch is sent once no new call has arrived for `idle` seconds (or `max_wait` after the
first one). Most batches finish within minutes, some take up to an hour, the API allows 24
hours. A request the batch couldn't complete (errored, expired, or declined by the safety
classifier) is sent again as an ordinary call, with the usual refusal fallback.

A round of `live_up_to` calls or fewer (default 5) is sent live, not as a batch: the last
rounds are usually one or two answers still reading their citations, and waiting minutes
per round for them would hold up the whole city for little saving.
"""

import itertools
import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future

FALLBACK_BETA = "server-side-fallback-2026-07-01"
log = logging.getLogger(__name__)


class BatchItemFailed(RuntimeError):
    """The batch didn't return a usable reply for this request; send it as a normal call."""


class SendLive(BatchItemFailed):
    """Too few calls in this round to be worth a batch; send it as a normal call."""


class Batcher:
    def __init__(
        self,
        client,
        *,
        idle: float = 10.0,
        max_wait: float = 120.0,
        poll: float = 20.0,
        max_requests: int = 5000,
        live_up_to: int = 5,
        on_status: Callable[[str], None] | None = None,
        progress_key: str = "Batches",
    ):
        self.client = client  # anthropic.Anthropic
        self.idle, self.max_wait, self.poll, self.max_requests = idle, max_wait, poll, max_requests
        self.live_up_to = live_up_to
        self.on_status = on_status or self._report
        self.progress_key = progress_key
        self._writer = None  # the run's live-progress writer, taken from a calling node
        self._pending: list[tuple[str, dict, Future]] = []
        self._first = self._last = 0.0
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._sender: threading.Thread | None = None
        self.batches: list[str] = []  # ids of every batch sent, for the record

    def submit(self, payload: dict):
        """Send one Messages API request in the next batch; wait for and return its reply
        (an anthropic Message). Raises BatchItemFailed if the batch couldn't complete it."""
        future: Future = Future()
        try:
            from langgraph.config import get_stream_writer

            self._writer = get_stream_writer()
        except Exception:  # not inside a graph run
            pass
        with self._lock:
            now = time.monotonic()
            if not self._pending:
                self._first = now
            self._last = now
            self._pending.append((f"r{next(self._ids)}", payload, future))
            if self._sender is None or not self._sender.is_alive():
                self._sender = threading.Thread(target=self._send_loop, daemon=True)
                self._sender.start()
        self._wake.set()
        return future.result()

    def _report(self, text: str) -> None:
        if self._writer is not None:
            try:
                self._writer({"activity": {"key": self.progress_key, "text": text}})
            except Exception:
                pass

    # -- sending ------------------------------------------------------------------------
    def _send_loop(self) -> None:
        while True:
            with self._lock:
                if not self._pending:
                    self._sender = None
                    return
                now = time.monotonic()
                due = (
                    now - self._last >= self.idle
                    or now - self._first >= self.max_wait
                    or len(self._pending) >= self.max_requests
                )
                if due:
                    taken, self._pending = self._pending, []
            if not due:
                self._wake.wait(timeout=1.0)
                self._wake.clear()
                continue
            # Sent on its own thread so new calls keep collecting for the next batch.
            threading.Thread(target=self._run_batch, args=(taken,), daemon=True).start()

    def _run_batch(self, items: list[tuple[str, dict, Future]]) -> None:
        if len(items) <= self.live_up_to:
            for _, _, future in items:
                future.set_exception(SendLive(f"only {len(items)} call(s) in this round"))
            return
        groups: dict[tuple, list] = {}
        for custom_id, payload, future in items:
            params = {k: v for k, v in payload.items() if k not in ("betas", "fallbacks")}
            betas = tuple(sorted(b for b in payload.get("betas") or [] if b != FALLBACK_BETA))
            groups.setdefault(betas, []).append((custom_id, params, future))
        for betas, group in groups.items():
            try:
                self._send(betas, group)
            except Exception as exc:  # the batch itself failed: each call goes live instead
                log.exception("message batch failed")
                for _, _, future in group:
                    if not future.done():
                        future.set_exception(BatchItemFailed(f"the batch failed: {exc}"))

    def _send(self, betas: tuple, group: list) -> None:
        api = self.client.beta.messages.batches if betas else self.client.messages.batches
        extra = {"betas": list(betas)} if betas else {}
        batch = api.create(
            requests=[{"custom_id": cid, "params": params} for cid, params, _ in group], **extra
        )
        self.batches.append(batch.id)
        self.on_status(
            f"Sent {len(group)} answer call(s) as one batch (half price). Waiting for it to "
            "finish: usually minutes, sometimes up to an hour."
        )
        while batch.processing_status != "ended":
            time.sleep(self.poll)
            batch = api.retrieve(batch.id)
        futures = {cid: future for cid, _, future in group}
        for entry in api.results(batch.id):
            future = futures.pop(entry.custom_id, None)
            if future is None:
                continue
            result = entry.result
            if result.type == "succeeded" and result.message.stop_reason != "refusal":
                future.set_result(result.message)
            else:
                why = "declined" if result.type == "succeeded" else result.type
                future.set_exception(BatchItemFailed(f"the batch request was {why}"))
        for future in futures.values():  # not in the results at all
            future.set_exception(BatchItemFailed("the batch returned no result"))
        self.on_status(f"Batch done ({len(group)} call(s)); continuing")
