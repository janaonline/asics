"""Step 1 with the required_sources setting: what the finder is told, what counts as covered, and
the Needs Attention lines. Practice mode and temp files only: no model call, no network."""

import dataclasses
import re

import pytest

from asics_agent import source_requirements as sr
from asics_agent.agents.common import question_digest
from asics_agent.agents.links_builder import covered_questions
from asics_agent.categories import category_settings, load_bank
from asics_agent.config import get_settings
from asics_agent.models import Parastatal, Source


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


def test_the_digest_carries_check_and_requires_only_when_asked(bank, agency):
    q = [bank["UPD 1a"], bank["DPG 4"]]
    plain = question_digest(q)
    assert "Check:" not in plain and "Requires:" not in plain
    full = question_digest(q, requirements=True, parastatal=agency)
    assert "Check: Check the relevant Parastatal Act/Rules and the State Town and Country" in full
    assert "Requires: parent Act [ACT]; Rules made under the Act [RULES]; Town and Country" in full
    dpg4 = full.split("- DPG 4")[1]
    assert "Requires:" not in dpg4  # no zero rule: nothing is required
    # an agency with no parent Act is told to find its constitution document instead
    agency.governing_act = "No parent Act located. A company under the Companies Act, 2013."
    assert "constitution document" in question_digest(
        [bank["UPD 1a"]], requirements=True, parastatal=agency
    )


def test_the_shared_laws_digest_lists_only_questions_that_need_a_shared_law(bank):
    questions = [bank["UPD 1a"], bank["UPD 1b"], bank["SC 6b"]]
    text = question_digest(questions, requirements=True, only=sr.SHARED_ONLY)
    assert "Requires: Town and Country Planning Act [TCP]" in text
    assert "Rules made under the Act" not in text and "official website" not in text
    # a question that needs no shared law has no Check or Requires line in that search
    after_1b = text.split("- UPD 1b")[1]
    assert "Requires:" not in after_1b


def test_the_finder_is_told_the_legal_basis(agency):
    assert "statutory" in sr.legal_base_line(agency)
    agency.governing_act = ""
    line = sr.legal_base_line(agency)
    assert "NO parent Act" in line and "[CONSTITUTION]" in line


def _source(tmp_path, n, tag, qids, *, url=None):
    path = tmp_path / f"s{n}.txt"
    path.write_text("Some readable text.", encoding="utf-8")
    return Source(
        citation_id=f"AAA-{n:02d}",
        parastatal_id="AAA",
        title=f"Doc {n}",
        url=url or f"https://example.gov.in/{n}",
        useful_for=f"[{tag}] something",
        question_ids=qids,
        verification_status="Verified",
        use_for_answers=True,
        content_path=str(path),
    )


def test_coverage_needs_the_required_documents_not_just_any_source(bank, agency, tmp_path):
    settings = category_settings(get_settings(), "parastatal")
    q = bank["UPD 1a"]
    wrong_kind = _source(tmp_path, 1, "IDENTITY", ["UPD 1a"])  # tagged for the question, wrong kind
    task = {"parastatal": agency, "task_questions": [q], "sources": [wrong_kind]}
    assert covered_questions(task, settings) == set()
    # with the setting off the earlier rule applies: any verified source tagged for it
    off = dataclasses.replace(settings, required_sources=False)
    assert covered_questions(task, off) == {"UPD 1a"}
    full = [
        wrong_kind,
        _source(tmp_path, 2, "ACT", []),
        _source(tmp_path, 3, "RULES", []),
        _source(tmp_path, 4, "TCP", []),
    ]
    assert covered_questions({**task, "sources": full}, settings) == {"UPD 1a"}


def test_a_question_without_a_zero_rule_keeps_the_earlier_coverage_rule(bank, agency, tmp_path):
    settings = category_settings(get_settings(), "parastatal")
    q = bank["DPG 4"]
    some = _source(tmp_path, 1, "IDENTITY", ["DPG 4"])
    task = {"parastatal": agency, "task_questions": [q], "sources": [some]}
    assert covered_questions(task, settings) == {"DPG 4"}
    assert covered_questions({**task, "sources": []}, settings) == set()


def _needs_attention(result):
    return [
        i.message
        for i in result["final_issues"]
        if i.audience == "team" and "missing required source" in i.message
    ]


def test_needs_attention_has_one_line_per_agency_and_missing_document(run_steps):
    lines = _needs_attention(run_steps("sources"))
    swb = [m for m in lines if m.startswith("Water Board:")]
    assert swb, "the practice agency lacks required documents, so it needs lines"
    # one line per document: no document is named twice for the same agency
    documents = [re.search(r"missing required source: (.+?)\. A score", m).group(1) for m in swb]
    assert len(documents) == len(set(documents))
    # each line lists the question codes it affects, not one line per question
    act = next(m for m in swb if "parent Act" in m)
    assert "Questions affected:" in act and "UPD 1a" in act


def test_no_needs_attention_lines_when_the_setting_is_off(services):
    from asics_agent.agents.sources_master import build_sources_graph

    off = dataclasses.replace(
        services, settings=dataclasses.replace(services.settings, required_sources=False)
    )
    result = build_sources_graph(off).invoke(
        {"city": "sample_city_a", "only_questions": ["UPD 1"], "auto_approve": True}
    )
    assert _needs_attention(result) == []


# -- the site crawl in Step 1 -----------------------------------------------------------------------
def _words(n=200):
    return " ".join(f"word{i}" for i in range(n))


@pytest.fixture
def site_with_menu(monkeypatch):
    """The practice agency's home page, with a three-link menu whose pages open."""
    from asics_agent import practice

    base = practice.SITE
    menu = "".join(
        f"<li><a href='/{name}'>{label}</a></li>"
        for name, label in (
            ("about", "About Us"),
            ("gallery", "Photo Gallery"),
            ("budget", "Budget"),
            ("rti", "RTI"),
        )
    )
    pages = dict(practice.PAGES)
    pages[base] = (
        f"<html><body><nav class='menu'><ul>{menu}</ul></nav><p>{practice.SITE_TEXT}</p>"
        f"<p>{_words()}</p></body></html>"
    )
    for name in ("about", "gallery", "budget", "rti"):
        pages[f"{base}{name}"] = f"<html><body><p>{name} page. {_words()}</p></body></html>"
    monkeypatch.setattr(practice, "PAGES", pages)
    return base


def _home_note(result, agency="SWB"):
    row = next(
        s
        for s in result["final_sources"]
        if s.parastatal_id == agency and s.source_type.lower() == "official website"
    )
    return row.notes


def test_a_complete_crawl_adds_the_menu_pages_and_is_recorded_on_the_home_row(
    services, site_with_menu
):
    from asics_agent.agents.sources_master import build_sources_graph

    result = build_sources_graph(services).invoke(
        {"city": "sample_city_a", "only_questions": ["UPD 1"], "auto_approve": True}
    )
    assert "SITE-CRAWL: complete, 4 of 4 menu links captured." in _home_note(result)
    pages = {s.url for s in result["final_sources"] if s.parastatal_id == "SWB"}
    assert {f"{site_with_menu}{n}" for n in ("about", "gallery", "budget", "rti")} <= pages
    crawled = [s for s in result["final_sources"] if s.url == f"{site_with_menu}budget"]
    assert crawled and "WEB" in sr.tags_of(crawled[0]) and crawled[0].use_for_answers
    swb = next(p for p in result["parastatals"] if p.id == "SWB")
    assert sr.crawl_status(swb, result["final_sources"])[0] == "complete"
    # a complete crawl is not a Needs Attention item
    assert not [m for m in _needs_attention(result) if "complete site crawl" in m]


def test_a_cap_below_the_menu_size_is_incomplete_and_keeps_the_relevant_pages(
    services, site_with_menu
):
    from asics_agent.agents.sources_master import build_sources_graph

    capped = dataclasses.replace(
        services, settings=dataclasses.replace(services.settings, crawl_max_pages=3)
    )
    result = build_sources_graph(capped).invoke(
        {"city": "sample_city_a", "only_questions": ["UPD 1", "SC 6"], "auto_approve": True}
    )
    assert "SITE-CRAWL: incomplete, 3 of 4 menu links captured (cap 3)" in _home_note(result)
    urls = {s.url for s in result["final_sources"] if s.parastatal_id == "SWB"}
    # topic words rank first, so the cut drops the page with none
    assert f"{site_with_menu}budget" in urls and f"{site_with_menu}rti" in urls
    assert f"{site_with_menu}gallery" not in urls
    lines = [m for m in _needs_attention(result) if "complete site crawl" in m]
    assert any(m.startswith("Water Board:") and "incomplete" in m for m in lines)


def test_a_home_page_without_a_menu_is_an_incomplete_crawl(services):
    from asics_agent.agents.sources_master import build_sources_graph

    result = build_sources_graph(services).invoke(
        {"city": "sample_city_a", "only_questions": ["UPD 1"], "auto_approve": True}
    )
    assert "SITE-CRAWL: incomplete" in _home_note(result)
    assert "no menu links" in _home_note(result)


def test_the_crawl_can_be_switched_off(services, site_with_menu):
    from asics_agent.agents.sources_master import build_sources_graph

    off = dataclasses.replace(
        services, settings=dataclasses.replace(services.settings, crawl_max_pages=0)
    )
    result = build_sources_graph(off).invoke(
        {"city": "sample_city_a", "only_questions": ["UPD 1"], "auto_approve": True}
    )
    assert "SITE-CRAWL" not in _home_note(result)
    assert f"{site_with_menu}budget" not in {s.url for s in result["final_sources"]}


def test_a_repeat_run_keeps_the_crawl_note_and_does_not_open_the_pages_again(
    services, site_with_menu
):
    from asics_agent.agents.sources_master import build_sources_graph

    inputs = {"city": "sample_city_a", "only_questions": ["UPD 1"], "auto_approve": True}
    build_sources_graph(services).invoke(inputs)
    second = build_sources_graph(services).invoke(inputs)
    assert "SITE-CRAWL: complete, 4 of 4" in _home_note(second)
    budget = [s for s in second["final_sources"] if s.url == f"{site_with_menu}budget"]
    assert len(budget) == 1  # one row, not a duplicate


# -- crawl_incomplete_on_dead_link: strict (the default) or lenient --------------------------------
def _crawl_with(services, **settings):
    from asics_agent.agents.sources_master import build_sources_graph

    changed = dataclasses.replace(
        services, settings=dataclasses.replace(services.settings, **settings)
    )
    return build_sources_graph(changed).invoke(
        {"city": "sample_city_a", "only_questions": ["UPD 1"], "auto_approve": True}
    )


def test_the_dead_link_setting_is_strict_by_default():
    settings = category_settings(get_settings(), "parastatal")
    assert settings.crawl_incomplete_on_dead_link == "strict"
    assert category_settings(get_settings(), "ulg").crawl_incomplete_on_dead_link == "strict"


def test_strict_makes_any_dead_menu_link_an_incomplete_crawl(services, site_with_menu):
    from asics_agent import practice

    practice.PAGES.pop(f"{site_with_menu}gallery")  # a dead link with no topic word
    note = _home_note(_crawl_with(services))
    assert "SITE-CRAWL: incomplete" in note and "did not open" in note and "/gallery" in note


def test_lenient_ignores_a_dead_link_with_no_topic_word(services, site_with_menu):
    from asics_agent import practice

    practice.PAGES.pop(f"{site_with_menu}gallery")
    note = _home_note(_crawl_with(services, crawl_incomplete_on_dead_link="lenient"))
    assert "SITE-CRAWL: complete, 3 of 4 menu links captured (lenient: 1 dead link(s)" in note


def test_lenient_still_counts_a_dead_link_that_names_a_topic(services, site_with_menu):
    from asics_agent import practice

    practice.PAGES.pop(f"{site_with_menu}budget")  # "Budget" is a topic word
    note = _home_note(_crawl_with(services, crawl_incomplete_on_dead_link="lenient"))
    assert "SITE-CRAWL: incomplete" in note and "/budget" in note
