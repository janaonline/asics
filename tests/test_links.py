from asics_agent.links.accessibility import check_url
from asics_agent.links.registry import extract_tool_urls
from asics_agent.practice import INDIA_CODE, PLAN, SITE, fake_http

UA = "test-agent"


def test_human_accessible_page_is_verified(tmp_path):
    check = check_url(SITE, fake_http(), tmp_path, UA)
    assert check.verification_status == "Verified"
    assert check.accessibility == "Public"


def test_india_code_metadata_page_is_not_verified(tmp_path):
    check = check_url(INDIA_CODE, fake_http(), tmp_path, UA)
    assert check.verification_status == "Not verified"
    assert "India Code" in " ".join(check.reasons)


def test_missing_page_is_not_verified(tmp_path):
    check = check_url(SITE + "missing", fake_http(), tmp_path, UA)
    assert check.verification_status == "Not verified"
    assert check.status_code == 404


def test_registry_accepts_search_results_and_rejects_constructed_fetches():
    blocks = [
        {"type": "server_tool_use", "input": {"url": "https://guessed.gov.in/"}},
        {"type": "web_search_tool_result", "content": [{"url": SITE}]},
        {
            "type": "web_fetch_tool_result",
            "content": {"url": SITE, "content": {"source": {"data": f"see {PLAN} for the plan."}}},
        },
        {"type": "web_fetch_tool_result", "content": {"url": "https://guessed.gov.in/"}},
    ]
    accepted, rejected = extract_tool_urls(blocks, known=set())
    assert accepted == {SITE, PLAN}
    assert rejected and "guessed.gov.in" in rejected[0]


def test_a_slow_website_cannot_hold_up_the_run(tmp_path, monkeypatch):
    import time

    import httpx

    from asics_agent.links import accessibility

    monkeypatch.setattr(accessibility, "PAGE_DEADLINE_SECONDS", 0.3)

    def trickle():
        for _ in range(50):  # each piece arrives quickly, but the page never finishes
            time.sleep(0.05)
            yield b"<p>word </p>"

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, headers={"content-type": "text/html"}, content=trickle())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    started = time.monotonic()
    check = check_url("https://slow.example.gov.in/", client, tmp_path, UA)
    assert time.monotonic() - started < 2
    assert check.verification_status == "Human Verification Required"
    assert "took longer than" in " ".join(check.reasons)


def test_a_stalled_model_call_is_stopped(monkeypatch):
    import dataclasses
    import time

    import pytest
    from pydantic import BaseModel

    from asics_agent.config import get_settings
    from asics_agent.llm import CallTimedOut, call_json
    from asics_agent.practice import FakeClaude, fake_http
    from asics_agent.services import Services

    class Stalled(FakeClaude):
        def _generate(self, *args, **kwargs):
            time.sleep(5)

    class Reply(BaseModel):
        ok: bool = True

    settings = dataclasses.replace(get_settings(), llm_call_timeout=0.2)
    services = Services(llm=Stalled(), http=fake_http(), settings=settings)
    with pytest.raises(CallTimedOut):
        call_json(services, "source-assessor", "x", Reply)
