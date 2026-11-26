"""The required-source table, the check and the full-text scan (source_requirements.py).
No model call and no network: sources are small text files in a temp folder."""

import re

import pytest

from asics_agent import source_requirements as sr
from asics_agent.models import Parastatal, Source

NO_ZERO_RULE = {"DPG 4", "DPG 7a", "SC 12b"}


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

    def make(tag, text="Nothing relevant here.", *, verified=True, url=None, source_type="Rules"):
        count[0] += 1
        path = tmp_path / f"s{count[0]}.txt"
        path.write_text(text, encoding="utf-8")
        return Source(
            citation_id=f"AAA-{count[0]:02d}",
            parastatal_id="AAA",
            title=f"Doc {count[0]}",
            url=url or f"https://example.gov.in/{count[0]}",
            source_type=source_type,
            useful_for=f"[{tag}] something" if tag else "something",
            verification_status="Verified" if verified else "Not verified",
            use_for_answers=True,
            content_path=str(path) if verified else None,
        )

    return make


# -- the table ------------------------------------------------------------------------------------
def test_table_has_the_52_scored_questions_as_drafts():
    table = sr.load()
    assert len(table.requirements) == 52
    assert {r.review_status for r in table.requirements.values()} == {"draft"}
    none = {r.code for r in table.requirements.values() if not r.has_zero_rule}
    assert none == NO_ZERO_RULE
    for req in table.requirements.values():
        for pattern in req.scan:
            re.compile(pattern)  # every scan pattern is a valid regular expression
        if req.has_zero_rule:
            assert req.groups, f"{req.code} has a zero rule but requires no source"
        else:
            assert not req.groups and not req.scan


def test_lookup_ignores_spacing_and_case():
    assert sr.required_for("UPD 1a") is sr.required_for("upd1a") is sr.required_for("UPD-1A")
    assert sr.required_for("NOPE 9") is None


def test_website_questions_never_require_the_document_they_look_for():
    # a budget row would make "no budget on the website" impossible to conclude
    groups = sr.required_for("DPG 5a").groups
    assert groups == (("WEB",), ("WEBPAGE",))


# -- the agency's legal basis ---------------------------------------------------------------------
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Bangalore Water Supply and Sewerage Act, 1964 (Karnataka Act 36 of 1964); form=Board",
            "act",
        ),
        ("", "constitution"),
        (
            "No parent Act located. WATCO is a company formed under the Companies Act, 2013.",
            "constitution",
        ),
        (
            "Companies Act, 2013 (Central Act); form=company (Special Purpose Vehicle)",
            "constitution",
        ),
        ("The Societies Registration Act, 1860; a registered society", "constitution"),
        ("Not established. K-RIDE appears to be a company.", "constitution"),
        ("Not verified. It points to a company form (Companies Act).", "constitution"),
        ("The Odisha Development Authorities Act, 1982 (Orissa Act); form=statutory", "act"),
    ],
)
def test_legal_base_kind_reads_the_governing_act_text(agency, text, expected):
    agency.governing_act = text
    assert sr.legal_base_kind(agency) == expected


# -- the tags of a row ----------------------------------------------------------------------------
def test_tags_of_reads_bracket_tags_and_the_website_row(make_source):
    assert sr.tags_of(make_source("ACT")) == {"ACT"}
    both = make_source("ACT")
    both.useful_for = "[ACT][RULES] text and a [unverified] note"
    assert {"ACT", "RULES"} <= sr.tags_of(both)
    site = make_source(None, source_type="Official website")
    assert sr.tags_of(site) == {"WEB"}
    assert sr.tags_of(make_source("AGENCY-WEBSITE")) == {"WEB"}
    assert sr.tags_of(make_source(None)) == set()


# -- the check ------------------------------------------------------------------------------------
def test_all_required_sources_present_allows_a_zero(agency, make_source):
    sources = [make_source("ACT"), make_source("RULES"), make_source("TCP")]
    gate = sr.check(sr.required_for("UPD 1a"), agency, sources)
    assert gate.state == "allowed"
    assert set(gate.present) == {"ACT", "RULES", "TCP"}
    assert len(gate.rows) == 3


def test_a_missing_required_source_is_named(agency, make_source):
    sources = [make_source("ACT"), make_source("RULES")]  # no T&CP Act
    gate = sr.check(sr.required_for("UPD 1a"), agency, sources)
    assert gate.state == "missing"
    assert gate.missing == ["TCP"]
    assert "Town and Country Planning Act" in gate.missing_text()


def test_a_required_source_that_failed_to_open_is_unreadable_not_missing(agency, make_source):
    site = make_source(
        None, source_type="Official website", verified=False, url="https://www.sample-board.in/"
    )
    site.notes = "SITE-CRAWL: complete, 1 of 1 links."
    page = make_source("BUDGET", url="https://www.sample-board.in/budget")
    gate = sr.check(sr.required_for("DPG 6"), agency, [site, page])
    assert gate.state == "unreadable"
    assert gate.unreadable == [site.citation_id]


def test_website_pages_count_only_after_a_complete_crawl_of_the_agencys_own_site(
    agency, make_source
):
    site = make_source(None, source_type="Official website", url="https://www.sample-board.in/")
    own = make_source("WEB", url="https://sample-board.in/budget.pdf")
    elsewhere = make_source("WEB", url="https://other.gov.in/budget.pdf")
    # no crawl marker: nothing can show that something is missing from the site
    gate = sr.check(sr.required_for("SC 6b"), agency, [site, own])
    assert gate.missing == ["SITECRAWL"]
    assert (
        "complete site crawl" in sr.decide_zero(sr.required_for("SC 6b"), agency, [site, own]).note
    )
    site.notes = "SITE-CRAWL: incomplete, 40 of 52 links (cap 15)."
    assert sr.check(sr.required_for("SC 6b"), agency, [site, own]).missing == ["SITECRAWL"]
    # complete, but the page is on another site
    site.notes = "SITE-CRAWL: complete, 1 of 1 links."
    assert sr.check(sr.required_for("SC 6b"), agency, [site, elsewhere]).missing == ["WEBPAGE"]
    # complete, with a page of the agency's own site
    assert sr.check(sr.required_for("SC 6b"), agency, [site, own]).state == "allowed"
    assert sr.crawl_status(agency, [site])[0] == "complete"
    assert sr.crawl_status(agency, [own])[0] == "none"


def test_a_company_needs_the_constitution_document_not_an_act(agency, make_source):
    agency.governing_act = "No parent Act located. A company under the Companies Act, 2013."
    with_act = [make_source("ACT"), make_source("RULES"), make_source("TCP")]
    gate = sr.check(sr.required_for("UPD 1a"), agency, with_act)
    assert gate.state == "missing"
    assert gate.missing == ["CONSTITUTION"]
    assert (
        "Missing: constitution document"
        in sr.decide_zero(sr.required_for("UPD 1a"), agency, with_act).note
    )
    with_constitution = [make_source("CONSTITUTION"), make_source("RULES"), make_source("TCP")]
    assert sr.check(sr.required_for("UPD 1a"), agency, with_constitution).state == "allowed"


def test_a_question_with_no_zero_condition_has_no_rule(agency, make_source):
    for code in sorted(NO_ZERO_RULE):
        gate = sr.check(sr.required_for(code), agency, [make_source("ACT")])
        assert gate.state == "no_rule"
    assert sr.decide_zero(sr.required_for("DPG 4"), agency, []).state == "no_rule"
    assert sr.check(None, agency, []).state == "no_rule"


# -- the scan and the decision --------------------------------------------------------------------
def test_scan_text_needs_every_pattern_in_one_passage():
    text = "Section 4. The Board shall prepare plans.\n\nSection 9. The mayor may consult staff."
    assert sr.scan_text(text, (r"plans?", r"shall")) != []
    assert sr.scan_text(text, (r"plans?", r"mayor")) == []  # in different passages
    assert sr.scan_text(text, ()) == []


def test_scan_keeps_the_pdf_page_of_a_hit():
    text = "[page 1]\nIntro.\n\n[page 2]\nThe Board shall consult the municipal corporation on its plan."
    hits = sr.scan_text(text, (r"plan", r"consult"))
    assert [h.page for h in hits] == ["2"]


def test_a_zero_is_allowed_after_a_clear_full_text_scan(agency, make_source):
    sources = [
        make_source("ACT", "Section 1. Short title.\n\nSection 2. Definitions."),
        make_source("RULES"),
        make_source("TCP"),
    ]
    decision = sr.decide_zero(sr.required_for("UPD 1a"), agency, sources)
    assert decision.allowed
    assert decision.note.startswith("Checked: AAA-01")
    assert "Scanned in full: no match" in decision.note


def test_a_zero_is_blocked_when_the_full_text_has_relevant_passages(agency, make_source):
    # the sentence sits deep in a long document, where a trimmed excerpt could have missed it
    filler = "\n\n".join(f"Section {i}. Nothing about this topic." for i in range(2000))
    deep = (
        filler
        + "\n\nSection 2001. The Board shall prepare its plan in consultation with the municipal corporation."
    )
    sources = [make_source("ACT", deep), make_source("RULES"), make_source("TCP")]
    decision = sr.decide_zero(sr.required_for("UPD 1a"), agency, sources)
    assert decision.state == "blocked_by_scan"
    assert not decision.allowed
    assert decision.scan.hits[0].citation_id == "AAA-01"
    assert "Blocked: relevant text found in AAA-01" in decision.note


def test_a_missing_source_blocks_before_any_scan(agency, make_source):
    decision = sr.decide_zero(sr.required_for("UPD 1a"), agency, [make_source("ACT")])
    assert decision.state == "missing"
    assert decision.scan is None
    assert decision.note.startswith("Missing: ")


def test_a_condition_only_zero_needs_the_sources_but_no_scan(agency, make_source):
    # DPG 1a: the zero rests on what the provisions say, not on nothing being found
    req = sr.required_for("DPG 1a")
    assert req.scan == ()
    sources = [
        make_source("ACT", "The Board shall consult the municipal corporation."),
        make_source("ULG-LAW"),
    ]
    assert sr.decide_zero(req, agency, sources).allowed


def test_the_zero_audit_names_the_copy_type_of_each_document_a_zero_rests_on():
    """The "AI zeros" sheet's copy-type column: plain, archived (flagged) and Claude-read copies."""
    import dataclasses

    from asics_agent.models import Parastatal, Source

    agency = Parastatal(
        id="AAA",
        name="Sample Board",
        type="water_supply_entity",
        governing_act="Sample Water Act, 1970 (State Act 3 of 1970)",
    )

    def src(cid, tag, copy_type):
        return Source(
            citation_id=cid,
            parastatal_id="AAA",
            title=cid,
            url=f"https://x.gov.in/{cid}",
            useful_for=f"[{tag}] x",
            verification_status="Verified",
            use_for_answers=True,
            content_path=__file__,
            copy_type=copy_type,
        )

    req = dataclasses.replace(sr.required_for("UPD 1a"), groups=(("ACT",), ("RULES",)))
    audit = sr.audit_zero(
        req,
        agency,
        [src("AAA-01", "ACT", "read by Claude (scan)"), src("AAA-02", "RULES", "ARCHIVED 2026-05-01")],
    )
    assert audit["copies"] == (
        "AAA-01: read by Claude (scan); AAA-02: ARCHIVED 2026-05-01 (cannot support a zero)"
    )
