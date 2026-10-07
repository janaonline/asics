import dataclasses
import shutil

from pydantic import BaseModel

from asics_agent.agent_setup import load_agent, validate
from asics_agent.config import PROJECT_ROOT
from asics_agent.llm import call_json
from asics_agent.models import Source
from asics_agent.practice import PLAN, SITE
from asics_agent.tools import ToolContext, build_tools


def test_agents_get_exactly_their_configured_tools(services):
    root = services.settings.agent_setup_dir
    builder = load_agent(root, "citation-builder")
    server, client = build_tools(root, builder.tools, ToolContext(services=services))
    assert [t["name"] for t in server] == ["web_search", "web_fetch"]
    assert server[0]["blocked_domains"][0] == "wikipedia.org" and server[0]["max_uses"] == 8
    assert [t.name for t in client] == ["check_link"]
    assert "human-accessibility test" in client[0].description  # from agent_setup/tools/

    writer = load_agent(root, "answer-writer")
    server, client = build_tools(root, writer.tools, ToolContext(services=services))
    assert server == []  # Step 2 never gets web tools
    assert {t.name for t in client} == {"read_citation", "search_citation_sheet", "lookup_question"}


def test_check_link_refuses_urls_no_tool_returned(services, tmp_path):
    from asics_agent.tools.check_link import run

    ctx = ToolContext(services=services, allowed_urls={SITE})
    assert run(ctx, "https://made-up.gov.in/").startswith("Refused")
    assert "Verdict: Verified" in run(ctx, SITE)


def test_citation_tools_only_reach_the_citation_sheet(services, tmp_path):
    from asics_agent.tools.citations import read, search

    text = tmp_path / "plan.txt"
    text.write_text("[page 1]\nIntro\n[page 4]\nThe Board recorded its responses to the ULG.")
    ctx = ToolContext(
        services=services,
        citations=[
            Source(
                citation_id="SWB-03",
                parastatal_id="SWB",
                title="Plan",
                url=PLAN,
                content_path=str(text),
            )
        ],
    )
    assert "recorded its responses" in read(ctx, "swb-03")
    assert read(ctx, "SWB-99").startswith("No Citation Sheet source")
    assert "[SWB-03, page 4]" in search(ctx, "board responses")


def test_both_steps_use_their_tools_and_record_it(run_steps):
    step1 = run_steps("sources")
    log = [i.message for i in step1["final_issues"] if i.phase == "tools"]
    assert any("Citation builder called: check_link" in m for m in log)

    step2 = run_steps("answers")
    answer = next(a for a in step2["answers"] if a.question_id == "UPD 1a")
    assert answer.status == "Answered — Verified Source"
    assert "Looked further with: read_citation" in answer.notes


def test_tool_calls_are_capped(services):
    from asics_agent.practice import FakeClaude

    class Greedy(FakeClaude):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            self.calls.append(str(messages[-1].content))
            if "Tool limit reached" in self.calls[-1]:
                return super()._generate(messages, **kwargs)  # now it replies
            return self._tool_call("lookup_question", {"question_id": "UPD 1a"}, [])

    class Reply(BaseModel):
        sufficiency: str = ""

    services.llm = llm = Greedy()
    reply, _, _ = call_json(services, "answer-writer", "x", Reply)
    assert reply.sufficiency == "insufficient"
    # 8 tool calls allowed (answer-writer's max_tool_calls), the 9th refused, then a reply.
    # (the last entry is the practice model's own record of its final reply)
    assert len(llm.calls) == 11 and "Tool limit reached" in llm.calls[9]


def test_tool_problems_are_reported(tmp_path):
    root = tmp_path / "agent_setup"
    shutil.copytree(PROJECT_ROOT / "agent_setup", root)
    path = root / "agents" / "answer-writer.md"
    path.write_text(
        path.read_text().replace("  read_citation: {}", "  web_search: {}\n  made_up_tool: {}")
    )
    messages = " ".join(i.message for i in validate(root, [], "parastatal", set()))
    assert "unknown tool 'made_up_tool'" in messages
    assert "must not have web_search or web_fetch" in messages


def test_run_options_override_agent_settings(services):
    from langgraph.graph import START, StateGraph

    from asics_agent.run_options import RunOptions, current_options

    seen = {}

    def node(state):
        seen["options"] = current_options()
        return {}

    graph = StateGraph(dict, context_schema=RunOptions)
    graph.add_node("node", node)
    graph.add_edge(START, "node")
    graph.compile().invoke({}, context=RunOptions(effort="low", max_tool_calls=3))
    assert seen["options"].effort == "low" and seen["options"].max_tool_calls == 3
    assert current_options() == RunOptions()  # outside a run: defaults


def test_each_agent_can_name_its_own_model(services):
    from langchain_anthropic import ChatAnthropic

    from asics_agent.services import Services

    real = Services(
        llm=ChatAnthropic(model="claude-opus-5-5"),
        http=services.http,
        settings=dataclasses.replace(services.settings, enable_fallbacks=False),
    )
    assert real.llm_for(None) is real.llm
    assert real.llm_for("claude-sonnet-5-5").model == "claude-sonnet-5-5"
    assert real.llm_for("claude-sonnet-5-5") is real.llm_for("claude-sonnet-5-5")  # reused
