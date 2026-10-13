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
    assert server[0]["allowed_domains"] == ["gov.in", "nic.in", "prsindia.org"]
    assert server[0]["max_uses"] == 5 and server[1]["max_content_tokens"] == 10000
    assert client == []  # links are checked by code afterwards, not by the agent

    # The agency's own domain is added for each call.
    server, _ = build_tools(
        root, builder.tools, ToolContext(services=services), web_domains={"bmrc.co.in"}
    )
    assert all(t["allowed_domains"][-1] == "bmrc.co.in" for t in server)

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
    assert not any("check_link" in m for m in log)  # the code checks links, not the agent

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


def _web_limits(services, monkeypatch, **options):
    """Run Step 1 and return {agent kind: web limits passed} for every agent that has web tools."""
    from asics_agent import llm
    from asics_agent.agents.sources_master import build_sources_graph
    from asics_agent.run_options import RunOptions

    seen = {}
    real = llm.build_tools

    def spy(root, tools, ctx, web_max_uses=None, web_domains=frozenset()):
        server, client = real(root, tools, ctx, web_max_uses=web_max_uses, web_domains=web_domains)
        kind = "source finder" if "allowed_domains" in tools.get("web_search", {}) else "other"
        seen.setdefault(kind, set()).update(t["max_uses"] for t in server)
        return server, client

    monkeypatch.setattr(llm, "build_tools", spy)
    build_sources_graph(services).invoke(
        {"city": "sample_city_a", "only_questions": ["UPD 1"], "auto_approve": True},
        context=RunOptions(**options),
    )
    return seen


def test_source_finder_keeps_its_own_limit_when_the_setting_is_not_set(services, monkeypatch):
    assert services.settings.find_sources_max_uses is None
    assert _web_limits(services, monkeypatch) == {"source finder": {5}, "other": {8}}


def test_source_finder_gets_its_own_search_limit(services, monkeypatch):
    from asics_agent.services import Services

    settings = dataclasses.replace(services.settings, find_sources_max_uses=20)
    limited = Services(llm=services.llm, http=services.http, settings=settings)
    assert _web_limits(limited, monkeypatch) == {"source finder": {20}, "other": {8}}


def test_a_run_override_beats_the_source_finder_limit(services, monkeypatch):
    from asics_agent.services import Services

    settings = dataclasses.replace(services.settings, find_sources_max_uses=20)
    limited = Services(llm=services.llm, http=services.http, settings=settings)
    seen = _web_limits(limited, monkeypatch, web_search_max_uses=5)
    assert seen == {"source finder": {5}, "other": {5}}
