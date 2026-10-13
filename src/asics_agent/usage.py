"""Counts the tokens every AI call uses, by model, and what they cost.

Every agent call goes through llm.call_json, which records each response's usage here. A run
(command line or app) can then report its cost, and saves the figures to
outputs/_app/usage/ so costs can be compared across runs and models.

Prices are Anthropic's first-party API rates in US$ per million tokens (input, output, cache
read); writing to the prompt cache costs 1.25x the input rate. Each web search costs $10 per
1,000 searches on top of tokens; web fetches cost only the tokens of the page read. Searches
and fetches are counted from the server-tool blocks in each response.
"""

import dataclasses
import json
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

PRICES = {  # model -> (input, output, cache read) per million tokens
    "claude-opus-5-5": (4.00, 20.00, 0.20),
    "claude-opus-5": (5.00, 25.00, 0.50),
    "claude-opus-4-8": (5.00, 25.00, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00, 0.20),
    "claude-sonnet-5": (2.00, 10.00, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
}
CACHE_WRITE = 1.25
SEARCH_PRICE = 10.00 / 1000  # US$ per web search
BATCH_SUFFIX = " (batch)"  # calls sent as Message Batches (Step 2) cost half, tokens only


@dataclass
class ModelUsage:
    calls: int = 0
    input: int = 0  # uncached input tokens
    cache_read: int = 0
    cache_write: int = 0
    output: int = 0  # includes thinking tokens
    searches: int = 0
    fetches: int = 0

    def cost(self, model: str) -> float | None:
        price = next((p for m, p in PRICES.items() if model.startswith(m)), None)
        if price is None:
            return None
        inp, out, read = price
        tokens = (
            self.input * inp
            + self.cache_write * inp * CACHE_WRITE
            + self.cache_read * read
            + self.output * out
        ) / 1_000_000
        if model.endswith(BATCH_SUFFIX):
            tokens /= 2
        return tokens + self.searches * SEARCH_PRICE


@dataclass
class UsageMeter:
    by_model: dict[str, ModelUsage] = field(default_factory=dict)
    by_agent: dict[str, ModelUsage] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(
        self, model: str, agent: str, usage: dict | None, blocks: list | None = None
    ) -> None:
        """`usage` is a LangChain usage_metadata dict; its input_tokens include cached ones.
        `blocks` is the response content, where each web search or fetch is a server_tool_use."""
        if not usage:
            return
        details = usage.get("input_token_details") or {}
        read = int(details.get("cache_read") or 0)
        write = int(details.get("cache_creation") or 0) + sum(
            int(details.get(k) or 0)
            for k in ("ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens")
        )
        tools = [
            b.get("name")
            for b in blocks or []
            if isinstance(b, dict) and b.get("type") == "server_tool_use"
        ]
        with self._lock:
            for key, table in ((model, self.by_model), (f"{agent} · {model}", self.by_agent)):
                row = table.setdefault(key, ModelUsage())
                row.calls += 1
                row.input += max(int(usage.get("input_tokens") or 0) - read - write, 0)
                row.cache_read += read
                row.cache_write += write
                row.output += int(usage.get("output_tokens") or 0)
                row.searches += tools.count("web_search")
                row.fetches += tools.count("web_fetch")

    def snapshot(self) -> "UsageMeter":
        """A copy of the counts so far (see `since`)."""
        with self._lock:
            return UsageMeter(
                by_model={k: dataclasses.replace(v) for k, v in self.by_model.items()},
                by_agent={k: dataclasses.replace(v) for k, v in self.by_agent.items()},
            )

    def since(self, earlier: "UsageMeter") -> "UsageMeter":
        """What was counted after the `earlier` snapshot: one run's usage."""
        now = self.snapshot()
        for table, before in ((now.by_model, earlier.by_model), (now.by_agent, earlier.by_agent)):
            for key, row in list(table.items()):
                old = before.get(key)
                if old:
                    for name in vars(row):
                        setattr(row, name, getattr(row, name) - getattr(old, name))
                if not row.calls:
                    del table[key]
        return now

    def reset(self) -> None:
        with self._lock:
            self.by_model.clear()
            self.by_agent.clear()

    def total(self) -> float:
        return sum(u.cost(m) or 0 for m, u in self.by_model.items())

    def lines(self) -> list[str]:
        out = []
        for key, u in sorted(self.by_agent.items()):
            model = key.split(" · ")[-1]
            cost = u.cost(model)
            out.append(
                f"{key}: {u.calls} calls, {u.input:,} in + {u.cache_read:,} cached + "
                f"{u.cache_write:,} cache-write, {u.output:,} out"
                + (
                    f", {u.searches} searches, {u.fetches} fetches"
                    if u.searches or u.fetches
                    else ""
                )
                + (f" = ${cost:.2f}" if cost is not None else " (no price on file)")
            )
        out.append(f"Total: ${self.total():.2f}")
        return out

    def save(self, folder: Path, label: str) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{datetime.now():%Y%m%d-%H%M%S}_{label}.json"
        path.write_text(
            json.dumps(
                {
                    "label": label,
                    "total_usd": round(self.total(), 4),
                    "by_model": {
                        m: {**vars(u), "usd": u.cost(m)} for m, u in self.by_model.items()
                    },
                    "by_agent": {a: vars(u) for a, u in self.by_agent.items()},
                },
                indent=2,
                default=str,
            )
        )
        return path


METER = UsageMeter()
