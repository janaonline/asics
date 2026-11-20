"""Step 2 and the zero gate: what the model is told, and what a score of 0 needs. A scripted model
answers; no network, no real model."""

import dataclasses
import json
import re

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from asics_agent.agents.sections.base import build_section_agent
from asics_agent.categories import category_settings, load_bank
from asics_agent.config import get_settings
from asics_agent.models import Parastatal, RunContext, Source
from asics_agent.practice import FakeClaude, _plain


class Scripted(FakeClaude):
    """Answers every Step 2 question with `reply`; everything else as the practice model."""

    reply: dict = {}

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if re.search(r"TASK: answer_question", _plain(messages[0].content)):
            self.sent.append(messages[-1].content)
            message = AIMessage(
                content=[{"type": "text", "text": json.dumps(self.reply)}],
                response_metadata={"stop_reason": "end_turn"},
            )
            return ChatResult(generations=[ChatGeneration(message=message)])
        return super()._generate(messages, stop, run_manager, **kwargs)


@pytest.fixture(scope="module")
def bank():
    questions, _ = load_bank(category_settings(get_settings(), "parastatal"))
    return questions


@pytest.fixture
def agency():
    return Parastatal(
        id="AAA",
        name="Sample Board",
        type="water_supply_entity",
        governing_act="Sample Water Act, 1970 (State Act 3 of 1970)",
        official_website="https://www.sample-board.in/",
    )


@pytest.fixture
def make_source(tmp_path):
    count = [0]

    def make(
        tag,
        text="Section 1. Short title.\n\nSection 2. Definitions.",
        *,
        verified=True,
        human=False,
        qids=(),
    ):
        count[0] += 1
        path = tmp_path / f"s{count[0]}.txt"
        path.write_text(text, encoding="utf-8")
        return Source(
            citation_id=f"AAA-{count[0]:02d}",
            parastatal_id="AAA",
            title=f"Doc {count[0]}",
            url=f"https://example.gov.in/{count[0]}",
            useful_for=f"[{tag}] something",
            verification_status="Verified" if verified else "Not verified",
            use_for_answers=True,
            content_path=str(path) if verified else None,
            human_verified=human,
            question_ids=list(qids),
        )

    return make


@pytest.fixture
def ask(tmp_path, bank, agency):
    """Ask Step 2 one question: ask(code, reply, sources, setting=True) -> (Answer, message)."""

    def run(code, reply, sources, *, required=True, human=True):
        settings = dataclasses.replace(
            category_settings(get_settings(), "parastatal"),
            outputs_dir=tmp_path,
            required_sources=required,
            human_verified_sources=human,
        )
        llm = Scripted(reply=reply)
        llm.sent.clear()
        from asics_agent.services import Services

        services = Services(llm=llm, http=None, settings=settings)
        q = bank[code]
        task = {
            "run": RunContext(
                run_id="r1",
                city="sample",
                city_name="Sample City",
                state_name="Sample State",
                ulg="Sample City Municipal Corporation",
                workspace=str(tmp_path),
                output_dir=str(tmp_path),
                cache_dir=str(tmp_path),
            ),
            "parastatal": agency,
            "question": q,
            "citation_sources": [s for s in sources if s.verification_status == "Verified"],
            "citation_all": sources,
        }
        out = build_section_agent(q.pillar, services).invoke(task)
        message = next(m for m in llm.sent if "Question " in m)
        return out["answers"][0], message

    return run


ZERO = {
    "sufficiency": "sufficient",
    "answer": "No formal role for the ULG is provided.",
    "proposed_score": 0,
    "zero_checked": True,
    "notes": "CLASS: A1; CONFIDENCE: High; BAND: 0",
}
FULL = lambda make: [make("ACT"), make("RULES"), make("TCP")]  # noqa: E731


def test_all_required_sources_and_a_clear_scan_give_a_recorded_zero(ask, make_source):
    answer, message = ask("UPD 1a", ZERO, FULL(make_source))
    assert answer.status == "Answered — Verified Source"
    assert answer.proposed_score == 0
    assert answer.confidence == "Medium"  # never High, whatever the model said
    assert answer.citation_id == "AAA-01"  # the parent Act, the primary required source
    assert answer.evidence_excerpt == ""
    assert "ZERO-CHECKED: Checked: AAA-01" in answer.notes
    assert "Scanned in full: no match" in answer.notes
    # the model was told the zero condition, its precedence and what is present
    assert "ZERO CONDITION (from the methodology): 0" in message
    assert "PRECEDENCE" in message
    assert "every one is in the Citation Sheet and was read: AAA-01, AAA-02, AAA-03" in message


def test_a_missing_required_source_keeps_the_score_blank_and_says_what_is_missing(ask, make_source):
    answer, message = ask("UPD 1a", ZERO, [make_source("ACT"), make_source("RULES")])
    assert answer.proposed_score is None
    assert answer.status == "Insufficient Evidence"
    assert "Missing: Town and Country Planning Act [TCP]" in answer.notes
    assert "REQUIRED SOURCES: MISSING" in message


def test_a_required_source_that_did_not_open_keeps_human_verification_required(ask, make_source):
    sources = [make_source("ACT", verified=False), make_source("RULES"), make_source("TCP")]
    answer, _ = ask("UPD 1a", ZERO, sources)
    assert answer.status == "Human Verification Required"
    assert answer.proposed_score is None
    assert answer.answer.startswith("SOURCE DID NOT OPEN")


def test_a_scan_hit_blocks_the_zero_and_the_passages_reach_the_model(ask, make_source):
    deep = (
        "\n\n".join(f"Section {i}. Nothing about this." for i in range(300))
        + "\n\nSection 301. The Board shall prepare its plan in consultation with the municipal "
        "corporation."
    )
    sources = [make_source("ACT", deep), make_source("RULES"), make_source("TCP")]
    answer, message = ask("UPD 1a", ZERO, sources)
    assert answer.proposed_score is None and answer.status == "Insufficient Evidence"
    assert "Blocked: relevant text found in AAA-01" in answer.notes
    assert "SCAN FOUND" in message
    assert "in consultation with the municipal corporation" in message


def test_a_positive_score_is_never_blocked_by_a_missing_source(ask, make_source):
    text = "Section 16. The Board shall prepare its plan in consultation with the Corporation."
    sources = [make_source("ACT", text)]  # Rules and the T&CP Act are missing
    reply = {
        "sufficiency": "sufficient",
        "answer": "Consultation is mandatory.",
        "proposed_score": 2.5,
        "citation_id": "AAA-01",
        "evidence_excerpt": "The Board shall prepare its plan in consultation with the Corporation",
        "notes": "CLASS: A1; CONFIDENCE: Medium; BAND: 2.5",
    }
    answer, _ = ask("UPD 1a", reply, sources)
    assert answer.status == "Answered — Verified Source" and answer.proposed_score == 2.5


def test_an_ordinary_zero_with_a_quote_still_needs_the_required_sources(ask, make_source):
    text = "Section 16. The Board shall prepare its plan in consultation with the Corporation."
    reply = {
        "sufficiency": "sufficient",
        "answer": "No role.",
        "proposed_score": 0,
        "citation_id": "AAA-01",
        "evidence_excerpt": "The Board shall prepare its plan",
        "notes": "CLASS: A1; CONFIDENCE: Medium; BAND: 0",
    }
    answer, _ = ask("UPD 1a", reply, [make_source("ACT", text)])
    assert answer.proposed_score is None
    assert "Missing:" in answer.notes


def test_no_zero_condition_means_the_gate_allows_no_zero(ask, make_source):
    # DPG 7a states no zero condition: a zero_checked flag is ignored and no zero is recorded
    answer, message = ask("DPG 7a", ZERO, [make_source("WEB")])
    assert "ZERO-CHECKED" not in answer.notes
    assert answer.status != "Answered — Verified Source"
    assert "the methodology states none for this question" in message


def test_with_the_setting_off_nothing_changes(ask, make_source):
    answer, message = ask("UPD 1a", ZERO, FULL(make_source), required=False)
    assert "ZERO-CHECKED" not in answer.notes
    assert "ZERO CONDITION" not in message and "REQUIRED SOURCES" not in message
