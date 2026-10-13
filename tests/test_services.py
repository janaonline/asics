"""The chat model replays server-tool blocks with their `caller` (see AsicsChatAnthropic)."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from asics_agent.services import AsicsChatAnthropic

CALLER = {"tool_id": "srvtoolu_exec", "type": "code_execution_20260120"}


def test_caller_survives_the_replay():
    reply = AIMessage(
        content=[
            {
                "type": "server_tool_use",
                "id": "srvtoolu_exec",
                "name": "code_execution",
                "input": {"code": "web_search('x'); web_search('y')"},
            },
            {
                "type": "server_tool_use",
                "id": "srvtoolu_s1",
                "name": "web_search",
                "input": {"query": "x"},
                "caller": CALLER,
            },
            {
                "type": "web_search_tool_result",
                "tool_use_id": "srvtoolu_s1",
                "content": [],
                "caller": CALLER,
            },
            {
                "type": "server_tool_use",
                "id": "srvtoolu_s2",
                "name": "web_search",
                "input": {"query": "y"},
                "caller": CALLER,
            },
            {
                "type": "web_search_tool_result",
                "tool_use_id": "srvtoolu_s2",
                "content": [],
                "caller": CALLER,
            },
            {
                "type": "code_execution_tool_result",
                "tool_use_id": "srvtoolu_exec",
                "content": {
                    "type": "code_execution_result",
                    "stdout": "",
                    "stderr": "",
                    "return_code": 0,
                    "content": [],
                },
            },
            {
                "type": "tool_use",
                "id": "toolu_1",
                "name": "check_link",
                "input": {"url": "https://a.gov.in"},
                "caller": {"type": "direct"},
            },
        ],
        tool_calls=[{"name": "check_link", "args": {"url": "https://a.gov.in"}, "id": "toolu_1"}],
    )
    model = AsicsChatAnthropic(model="claude-opus-5-5", api_key="test")
    payload = model._get_request_payload(
        [HumanMessage("score"), reply, ToolMessage("opens", tool_call_id="toolu_1")]
    )
    blocks = payload["messages"][1]["content"]
    nested = [
        b
        for b in blocks
        if b.get("id") in ("srvtoolu_s1", "srvtoolu_s2")
        or b.get("tool_use_id") in ("srvtoolu_s1", "srvtoolu_s2")
    ]
    assert len(nested) == 4 and all(b["caller"] == CALLER for b in nested)


def test_a_reply_cut_off_mid_tool_call_is_dropped_before_the_retry():
    from asics_agent.llm import _without_unfinished_tool_use

    cut = AIMessage(
        content=[
            {"type": "text", "text": "Let me check"},
            {"type": "tool_use", "id": "toolu_x", "name": "read_citation", "input": {}},
        ]
    )
    done = AIMessage(content=[{"type": "text", "text": '{"a": 1}'}])
    assert _without_unfinished_tool_use([HumanMessage("q"), cut]) == [HumanMessage("q")]
    assert _without_unfinished_tool_use([HumanMessage("q"), done])[-1] is done


def test_nothing_above_sonnet_5_5_can_run():
    import dataclasses

    import pytest

    from asics_agent.config import get_settings
    from asics_agent.services import ModelNotAllowed, check_model, make_chat_model

    assert check_model("claude-sonnet-5-5") == "claude-sonnet-5-5"
    for model in ("claude-opus-5-5", "claude-opus-4-8", "claude-fable-5-1"):
        with pytest.raises(ModelNotAllowed):
            make_chat_model(dataclasses.replace(get_settings(), model=model))
    haiku = make_chat_model(get_settings(), "claude-haiku-5-5")
    assert "fallbacks" not in (haiku.model_kwargs or {})  # Haiku 5.5 has no fallback


def test_every_agent_is_pinned_at_or_below_sonnet():
    from asics_agent.agent_setup import load_agents
    from asics_agent.config import get_settings
    from asics_agent.services import ALLOWED_MODELS

    agents, _ = load_agents(get_settings().agent_setup_dir)
    assert all(a.model in ALLOWED_MODELS for a in agents.values())


def test_prompts_are_cached():
    model = AsicsChatAnthropic(model="claude-sonnet-5-5", api_key="test")
    from langchain_core.messages import SystemMessage

    from asics_agent.llm import CACHE

    payload = model._get_request_payload(
        [
            SystemMessage(
                [{"type": "text", "text": "rules", "cache_control": {"type": "ephemeral"}}]
            ),
            HumanMessage("q"),
        ],
        **CACHE,
    )
    assert payload["system"][0]["cache_control"] == {"type": "ephemeral"}  # the instructions
    assert payload.get("cache_control") == {"type": "ephemeral"}  # automatic: the conversation


def test_usage_meter_counts_web_searches_and_cache_writes():
    from asics_agent.usage import UsageMeter

    meter = UsageMeter()
    usage = {
        "input_tokens": 3000,  # LangChain total: 1000 uncached + 1000 read + 1000 written
        "output_tokens": 100,
        "input_token_details": {
            "cache_read": 1000,
            "cache_creation": 0,
            "ephemeral_5m_input_tokens": 1000,
        },
    }
    blocks = [
        {"type": "server_tool_use", "name": "web_search", "id": "s1"},
        {"type": "server_tool_use", "name": "web_search", "id": "s2"},
        {"type": "server_tool_use", "name": "web_fetch", "id": "f1"},
        {"type": "text", "text": "done"},
    ]
    meter.record("claude-sonnet-5-5", "citation-builder", usage, blocks)
    row = meter.by_model["claude-sonnet-5-5"]
    assert (row.input, row.cache_read, row.cache_write) == (1000, 1000, 1000)
    assert (row.searches, row.fetches) == (2, 1)
    tokens = (1000 * 2 + 1000 * 2 * 1.25 + 1000 * 0.2 + 100 * 10) / 1_000_000
    assert abs(meter.total() - (tokens + 2 * 0.01)) < 1e-9
    assert "2 searches, 1 fetches" in meter.lines()[0]


def test_a_reply_with_plain_string_blocks_is_left_as_is():
    from langchain_core.messages import AIMessage

    from asics_agent.llm import _shrink_fetched_pdfs

    reply = AIMessage(content=['{"useful": true}', {"type": "text", "text": "ok"}])
    assert _shrink_fetched_pdfs(reply) is reply  # Haiku 5.5 streams plain strings like this
