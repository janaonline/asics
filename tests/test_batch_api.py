"""Step 2 through the Message Batches API (batch.py), against a fake batch API."""

import threading
from types import SimpleNamespace

import anthropic
import pytest

from asics_agent.batch import FALLBACK_BETA, Batcher, BatchItemFailed


def message(text: str, stop: str = "end_turn") -> anthropic.types.Message:
    return anthropic.types.Message.model_validate(
        {
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "model": "claude-sonnet-5-5",
            "content": [{"type": "text", "text": text}],
            "stop_reason": stop,
            "stop_sequence": None,
            "usage": {"input_tokens": 100, "output_tokens": 10},
        }
    )


class FakeBatches:
    """messages.batches: every request is answered with its own last user message, except
    ones asking to fail or be refused."""

    def __init__(self):
        self.created = []

    def create(self, requests, betas=None):
        self.created.append({"requests": list(requests), "betas": betas})
        return SimpleNamespace(id=f"batch_{len(self.created)}", processing_status="in_progress")

    def retrieve(self, batch_id):
        return SimpleNamespace(id=batch_id, processing_status="ended")

    def results(self, batch_id):
        batch = self.created[int(batch_id.split("_")[1]) - 1]
        for r in batch["requests"]:
            text = r["params"]["messages"][-1]["content"]
            if text == "fail":
                result = SimpleNamespace(type="errored")
            else:
                stop = "refusal" if text == "refuse" else "end_turn"
                result = SimpleNamespace(type="succeeded", message=message(f"re: {text}", stop))
            yield SimpleNamespace(custom_id=r["custom_id"], result=result)


@pytest.fixture
def fake_api():
    batches = FakeBatches()
    client = SimpleNamespace(
        messages=SimpleNamespace(batches=batches),
        beta=SimpleNamespace(messages=SimpleNamespace(batches=batches)),
    )
    return client, batches


def ask(batcher, text, out, betas=None):
    payload = {"model": "claude-sonnet-5-5", "messages": [{"role": "user", "content": text}]}
    if betas:
        payload |= {"betas": betas, "fallbacks": "default"}
    try:
        out[text] = batcher.submit(payload).content[0].text
    except BatchItemFailed as exc:
        out[text] = f"failed: {exc}"


def test_calls_made_together_go_out_as_one_batch(fake_api):
    client, batches = fake_api
    batcher = Batcher(client, idle=0.3, poll=0.01, live_up_to=0)
    out = {}
    threads = [
        threading.Thread(target=ask, args=(batcher, t, out, [FALLBACK_BETA]))
        for t in ("a", "b", "fail", "refuse")
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert len(batches.created) == 1 and len(batches.created[0]["requests"]) == 4
    # The refusal fallback isn't sent in a batch (a refused item is re-sent live instead).
    params = batches.created[0]["requests"][0]["params"]
    assert "fallbacks" not in params and "betas" not in params
    assert batches.created[0]["betas"] is None
    assert out["a"] == "re: a" and out["b"] == "re: b"
    assert out["fail"].startswith("failed") and out["refuse"].startswith("failed")


def test_the_model_sends_through_the_batcher_and_is_metered_at_half_price(fake_api):
    from langchain_core.messages import HumanMessage

    from asics_agent.services import AsicsChatAnthropic
    from asics_agent.usage import BATCH_SUFFIX, UsageMeter

    client, batches = fake_api
    llm = AsicsChatAnthropic(
        model="claude-sonnet-5-5",
        api_key="test",
        streaming=True,
        batcher=Batcher(client, idle=0.05, poll=0.01, live_up_to=0),
    )
    reply = llm.invoke([HumanMessage("hello")])
    assert reply.text == "re: hello"
    assert reply.response_metadata["batch"] is True
    assert reply.response_metadata["stop_reason"] == "end_turn"
    assert len(batches.created) == 1

    meter = UsageMeter()
    usage = {"input_tokens": 1_000_000, "output_tokens": 0}
    meter.record("claude-sonnet-5-5" + BATCH_SUFFIX, "answer-writer", usage)
    meter.record("claude-sonnet-5-5", "answer-writer", usage)
    assert meter.total() == pytest.approx(1.0 + 2.0)  # $2 per million, half in a batch


def test_step2_batches_only_real_claude(services):
    from asics_agent.runner import answer_concurrency

    # Practice and tests use a stand-in model: no batches, normal concurrency.
    assert answer_concurrency(services) == services.settings.max_concurrency


def test_a_small_round_is_sent_live_not_batched(fake_api):
    client, batches = fake_api
    batcher = Batcher(client, idle=0.05, poll=0.01, live_up_to=5)
    out = {}
    ask(batcher, "the last straggler", out)
    assert out["the last straggler"].startswith("failed: only 1 call")  # the model goes live
    assert batches.created == []


def test_the_model_answers_a_small_round_live(fake_api, monkeypatch):
    from langchain_anthropic import ChatAnthropic
    from langchain_core.messages import AIMessageChunk, HumanMessage
    from langchain_core.outputs import ChatGenerationChunk

    from asics_agent.services import AsicsChatAnthropic

    def live_stream(self, messages, stop=None, run_manager=None, **kwargs):
        yield ChatGenerationChunk(message=AIMessageChunk(content="live reply"))

    monkeypatch.setattr(ChatAnthropic, "_stream", live_stream)
    client, batches = fake_api
    llm = AsicsChatAnthropic(
        model="claude-sonnet-5-5",
        api_key="test",
        streaming=True,
        batcher=Batcher(client, idle=0.05, poll=0.01, live_up_to=5),
    )
    reply = llm.invoke([HumanMessage("hello")])
    assert reply.text == "live reply" and not reply.response_metadata.get("batch")
    assert batches.created == []  # charged at the full price, as a live call
