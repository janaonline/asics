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
