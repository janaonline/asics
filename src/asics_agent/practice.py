"""Practice mode: a scripted stand-in for Claude and a few sample web pages.

Lets the team learn the app, and the tests exercise both steps end to end, with no API key,
no internet and no cost. Everything it produces is sample data and is labelled as such.

The sample research finds two parastatals per city: the water board the register lists,
plus a transport corporation the agent "discovers". The water board has a gov.in website
linked from the state portal (rated Official); the transport corporation only has a .org
website with a government email address (rated Probably official).
"""

import json
import re

import httpx
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

PRACTICE_NOTE = "PRACTICE RUN: sample data, not real research."
PRACTICE_CITIES = ["Sample City A", "Sample City B"]

SITE = "https://bwssb.example.gov.in/"
TRANSPORT_SITE = "https://stc-transport.example.org/"
PORTAL = "https://urban.example.gov.in/parastatals"
PLAN = "https://urban.example.gov.in/water-plan-2024"
INDIA_CODE = "https://www.indiacode.nic.in/handle/123456789/7903?locale=en"
MADE_UP = "https://made-up.gov.in/never-returned"

FILLER = " ".join(f"word{i}" for i in range(300))
SITE_TEXT = (
    "Official website of the Water Board, Government of Sample State. Section 16. The Board "
    "shall prepare its water supply plan in consultation with the Corporation and shall "
    "consider its comments. Right to Information: Public Information Officer. " + FILLER
)
TRANSPORT_TEXT = (
    "Sample Transport Corporation. Contact the Managing Director: md[at]stc[dot]samplestate"
    "[dot]gov[dot]in. Right to Information details. " + FILLER
)
PLAN_TEXT = (
    "Water Supply Master Plan 2024. The Corporation passed a resolution on the draft plan and "
    "the Board recorded its responses to each of the Corporation's inputs. " + FILLER
)
PORTAL_TEXT = (
    f"Urban Development Department, Government of Sample State. Parastatals: Water Board "
    f"{SITE} ; Sample Transport Corporation {TRANSPORT_SITE} . Follow the Water Board on "
    "https://x.com/samplewaterboard . " + FILLER
)
PAGES = {
    SITE: "<html><head><title>Water Board</title></head><body><h1>Water Board</h1>"
    f"<p>{SITE_TEXT}</p><a href='https://x.com/samplewaterboard'>X</a></body></html>",
    TRANSPORT_SITE: "<html><head><title>STC</title></head><body>"
    f"<p>{TRANSPORT_TEXT}</p></body></html>",
    PORTAL: f"<html><body><p>{PORTAL_TEXT}</p></body></html>",
    PLAN: f"<html><body><p>{PLAN_TEXT}</p></body></html>",
    INDIA_CODE: "<html><body><p>Title: Water Supply and Sewerage Act, 1964. "
    "Date: 1964. Type: Act.</p></body></html>",
}


def fake_http() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/robots.txt"):
            return httpx.Response(404)
        if url in PAGES:
            return httpx.Response(200, html=PAGES[url])
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _search_block(*urls: str) -> dict:
    return {
        "type": "web_search_tool_result",
        "tool_use_id": "srv_1",
        "content": [{"type": "web_search_result", "url": u, "title": u} for u in urls],
    }


def _fetch_block(url: str, text: str) -> dict:
    return {
        "type": "web_fetch_tool_result",
        "tool_use_id": "srv_2",
        "content": {
            "type": "web_fetch_result",
            "url": url,
            "content": {"type": "document", "source": {"type": "text", "data": text}},
        },
    }


def _citation_with(user: str, phrase: str) -> str | None:
    """The CITATION id whose text block contains `phrase`."""
    for match in re.finditer(r"=== CITATION (\S+): .*?===\n(.*?)(?==== CITATION|\Z)", user, re.S):
        if phrase in match.group(2):
            return match.group(1)
    return None


class FakeClaude(BaseChatModel):
    """Answers each TASK prompt with canned JSON; web tasks include tool-result blocks."""

    calls: list = []
    sent: list = []  # every message text the agents sent (tests check memory reached it)
    delay: float = 0.0  # seconds per call; the app uses a pause so progress is visible

    @property
    def _llm_type(self) -> str:
        return "fake-claude"

    bound: list = []  # names of the tools the agent was given

    def bind_tools(self, tools, **kwargs):
        names = [t["name"] if isinstance(t, dict) else t.name for t in tools]
        return self.model_copy(update={"bound": names})

    def _tool_call(self, name: str, args: dict, blocks: list) -> ChatResult:
        message = AIMessage(
            content=blocks,
            tool_calls=[{"name": name, "args": args, "id": f"call_{name}"}],
            response_metadata={"stop_reason": "tool_use"},
        )
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if self.delay:
            import time

            time.sleep(self.delay)
        system, user = messages[0].content, messages[-1].content
        self.sent.append(user)
        used_tools = any(isinstance(m, ToolMessage) for m in messages)
        if used_tools:  # the agent is replying after a tool call; find the original task input
            user = next(m.content for m in messages if m.type == "human")
        task = re.search(r"TASK: (\w+)", system).group(1)
        self.calls.append(task)
        blocks, reply = [], {}
        if task == "discover_parastatals":
            blocks += [_search_block(PORTAL), _fetch_block(PORTAL, PORTAL_TEXT)]
            reply = {
                "parastatals": [
                    {
                        "id": "SWB",
                        "name": "Water Board",
                        "type": "water_supply_board",
                        "revenue_raising": True,
                        "capex_mandate": True,
                        "why_included": "Supplies water to the city.",
                        "evidence_urls": [PORTAL],
                    },
                    {
                        "id": "STC",
                        "name": "Sample Transport Corporation",
                        "type": "transport_corporation",
                        "revenue_raising": True,
                        "capex_mandate": False,
                        "why_included": "Runs the city's buses.",
                        "evidence_urls": [PORTAL],
                    },
                ],
                "notes": "",
            }
        elif task == "parastatal_profile":
            transport = "(STC)" in user
            site = TRANSPORT_SITE if transport else SITE
            blocks += [_search_block(PORTAL, site), _fetch_block(PORTAL, PORTAL_TEXT)]
            reply = {
                "governing_act": "Sample Act, 1964",
                "current_status": "Active",
                "has_chief_executive": True,
                "has_annual_budget": True,
                "candidate_websites": [site],
                "government_pages_checked": [PORTAL],
                "notes": "From the state portal.",
            }
        elif task == "find_sources":
            if "check_link" in self.bound and not used_tools and "still have NO" not in user:
                # Check a link before proposing it, as the prompt asks.
                return self._tool_call("check_link", {"url": SITE}, [_search_block(SITE)])
            if "still have NO verified source" in user:  # the gap-filling pass
                blocks.append(_search_block(PLAN))
                reply = {
                    "sources": [
                        {
                            "title": "Water Supply Master Plan 2024",
                            "url": PLAN,
                            "source_type": "Plan",
                            "useful_for": "ULG participation",
                            "question_ids": ["UPD 1b"],
                        }
                    ],
                    "notes": "",
                }
            else:
                blocks.append(_search_block(SITE, INDIA_CODE))
                reply = {
                    "sources": [
                        {
                            "title": "Water Board website",
                            "url": SITE,
                            "source_type": "Website",
                            "useful_for": "Planning duties",
                            "question_ids": ["UPD 1a"],
                        },
                        {
                            "title": "Act (India Code)",
                            "url": INDIA_CODE,
                            "source_type": "Act",
                            "useful_for": "Text of the Act",
                            "question_ids": ["UPD 1a"],
                        },
                        {
                            "title": "Invented link",
                            "url": MADE_UP,
                            "source_type": "Act",
                            "useful_for": "Should be discarded",
                            "question_ids": [],
                        },
                    ],
                    "notes": "",
                }
        elif task == "assess_source":
            reply = {
                "useful": True,
                "useful_for": "Planning duties and ULG participation",
                "current_status": "Current",
                "authority_score": 10,
                "notes": "Official.",
            }
        elif task == "answer_question":
            plan = _citation_with(user, "recorded its responses")
            site = _citation_with(user, "The Board shall prepare")
            if "read_citation" in self.bound and not used_tools and (plan or site):
                # Read further into the citation before answering.
                return self._tool_call(
                    "read_citation", {"citation_id": plan or site, "query": "consultation"}, []
                )
            if "UPD 1b" in user and plan:
                reply = {
                    "sufficiency": "sufficient",
                    "answer": "The ULG commented and the Board responded.",
                    "proposed_score": 10,
                    "citation_id": plan,
                    "citation": "Section on consultation",
                    "evidence_excerpt": "the Board recorded its responses to each of the "
                    "Corporation's inputs",
                    "notes": "The plan documents ULG participation.",
                }
            elif "UPD 1a" in user and site:
                reply = {
                    "sufficiency": "sufficient",
                    "answer": "Consultation is mandatory and comments must be considered.",
                    "proposed_score": 7.5,
                    "citation_id": site,
                    "citation": "Section 16",
                    "evidence_excerpt": "The Board shall prepare its water supply plan in "
                    "consultation with the Corporation",
                    "notes": "Section 16 applies.",
                }
            else:
                reply = {
                    "sufficiency": "insufficient",
                    "missing_evidence": "the latest plan document or consultation record",
                    "notes": "None of the citations covers this question.",
                }
        blocks.append({"type": "text", "text": json.dumps(reply)})
        message = AIMessage(content=blocks, response_metadata={"stop_reason": "end_turn"})
        return ChatResult(generations=[ChatGeneration(message=message)])


def practice_register(path):
    """A small register of made-up cities, so practice runs never touch the real one."""
    from asics_agent.cities import write_register
    from asics_agent.models import CityConfig, Parastatal

    cities = [
        CityConfig(
            slug=name.lower().replace(" ", "_"),
            name=name,
            state="Sample State",
            ulg=f"{name} Municipal Corporation",
            parastatals=[
                Parastatal(
                    id="SWB",
                    name="Water Board",
                    type="water_supply_board",
                    revenue_raising=True,
                    capex_mandate=True,
                )
            ],
        )
        for name in PRACTICE_CITIES
    ]
    return write_register(path, cities)


def practice_services(settings, delay: float = 0.0):
    """Services for a practice run; outputs go to outputs/practice/."""
    import dataclasses

    from asics_agent.services import Services

    outputs = settings.outputs_dir / "practice"
    register = practice_register(outputs / "practice_register.xlsx")
    return Services(
        llm=FakeClaude(delay=delay),
        http=fake_http(),
        settings=dataclasses.replace(settings, outputs_dir=outputs, city_register=register),
    )
