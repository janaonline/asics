import base64

import anthropic
import httpx
import pytest
from langchain_core.messages import AIMessage

from asics_agent import llm


def fetch_result(source: dict) -> dict:
    return {
        "type": "web_fetch_tool_result",
        "tool_use_id": "srvtoolu_1",
        "content": {
            "type": "web_fetch_result",
            "url": "https://bwssb.karnataka.gov.in/report.pdf",
            "content": {"type": "document", "source": source, "title": "Report"},
        },
    }


def test_fetched_pdfs_are_sent_again_as_text(monkeypatch):
    monkeypatch.setattr(llm, "pdf_to_text", lambda data: f"text of {data.decode()}")
    pdf = {
        "type": "base64",
        "media_type": "application/pdf",
        "data": base64.b64encode(b"annual report").decode(),
    }
    page = {"type": "text", "media_type": "text/plain", "data": "an HTML page"}
    response = AIMessage(
        content=[{"type": "text", "text": "Reading"}, fetch_result(pdf), fetch_result(page)]
    )

    shrunk = llm._shrink_fetched_pdfs(response)

    assert shrunk.content[1]["content"]["content"]["source"] == {
        "type": "text",
        "media_type": "text/plain",
        "data": "text of annual report",
    }
    assert shrunk.content[0] == response.content[0]
    assert shrunk.content[2] == response.content[2]  # web pages are already text
    assert response.content[1]["content"]["content"]["source"] == pdf  # original untouched


def test_long_or_unreadable_pdfs(monkeypatch):
    monkeypatch.setattr(llm, "pdf_to_text", lambda data: "x" * (llm.MAX_FETCHED_PDF_CHARS + 5))
    long = llm._pdf_as_text({"data": ""})["data"]
    assert long.endswith("[document cut here; 5 more characters]")

    monkeypatch.setattr(llm, "pdf_to_text", lambda data: 1 / 0)
    assert "no readable text" in llm._pdf_as_text({"data": ""})["data"]


def test_too_large_request_fails_only_that_call():
    class TooLarge:
        def invoke(self, messages, **kwargs):
            request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
            raise anthropic.RequestTooLargeError(
                "too large", response=httpx.Response(413, request=request), body=None
            )

    with pytest.raises(llm.CallFailed, match="too large"):
        llm._invoke(TooLarge(), [], timeout=5)


class Scripted:
    """A fake model that returns the given replies in turn and records what it was sent."""

    def __init__(self, *replies):
        self.replies, self.sent = list(replies), []

    def invoke(self, messages, **kwargs):
        self.sent.append(list(messages))
        return self.replies.pop(0)


def test_every_tool_call_is_answered_before_the_next_turn():
    unknown = {"type": "tool_use", "id": "toolu_unknown", "name": "web_search_x", "input": {}}
    cut_off = {"type": "tool_use", "id": "toolu_cut", "name": "read_citation", "input": {}}
    first = AIMessage(
        content=[unknown, cut_off],
        invalid_tool_calls=[
            {"type": "invalid_tool_call", "id": "toolu_cut", "name": "read_citation", "args": "{"}
        ],
    )
    model = Scripted(first, AIMessage(content='{"answer": 1}'))
    loop = llm._agent_loop(
        model, [], timeout=5, effort="low", max_tool_calls=4, on_response=lambda r: None
    )

    state = loop.invoke({"messages": [], "tool_calls": 0})

    assert state["messages"][-1].text == '{"answer": 1}'
    answered = {m.tool_call_id for m in model.sent[1] if m.type == "tool"}
    assert answered == {"toolu_unknown", "toolu_cut"}


def test_bad_request_fails_only_that_call():
    class Rejects:
        def invoke(self, messages, **kwargs):
            request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
            raise anthropic.BadRequestError(
                "bad", response=httpx.Response(400, request=request), body=None
            )

    with pytest.raises(llm.CallFailed, match="rejected"):
        llm._invoke(Rejects(), [], timeout=5)
