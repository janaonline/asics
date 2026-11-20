# ruff: noqa: F811
# (the fixtures imported from other test modules are re-declared by name in each test's arguments)
"""Human-verified sources: the Citation Sheet column, Step 1 (never clears it, never lowers it), Steps
2 and 3 (marked, pinned, status), the gate, the crawl and the Compare split. Practice mode and
stubs only: no network, no real model. Workbooks are written in temp folders."""

import dataclasses
import json
from datetime import date
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from openpyxl import load_workbook

from asics_agent import source_requirements as sr
from asics_agent.agents.common import HUMAN_DOUBT_NOTE, HUMAN_UNOPENED_NOTE, dedupe_sources
from asics_agent.agents.sources_master import build_sources_graph
from asics_agent.citation_dates import date_citation_sheet
from asics_agent.cutoff import CutoffRule
from asics_agent.models import HUMAN_VERIFIED_MARK, Parastatal, Source
from asics_agent.practice import PLAN, FakeClaude, _plain
from asics_agent.sources_workbook import CITATIONS_SHEET, HUMAN_VERIFIED, read_sources_workbook

INPUTS = {"city": "sample_city_a", "only_questions": ["UPD 1"], "auto_approve": True}


class NotUseful(FakeClaude):
    """The practice model, except that the source assessor finds nothing useful."""

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if "TASK: assess_source" in _plain(messages[0].content):
            reply = {
                "useful": False,
                "useful_for": "",
                "current_status": "Unknown",
                "authority_score": 5,
                "notes": "The page does not support the stated use.",
                "effective_date": "",
                "form": "",
            }
            message = AIMessage(
                content=[{"type": "text", "text": json.dumps(reply)}],
                response_metadata={"stop_reason": "end_turn"},
            )
            return ChatResult(generations=[ChatGeneration(message=message)])
        return super()._generate(messages, stop, run_manager, **kwargs)


# -- helpers: edit the temp Sources workbook the way a team member would -----------------------------
def _edit(path, change):
    wb = load_workbook(path)
    ws = wb[CITATIONS_SHEET]
    header = {c.value: c.column for c in ws[1] if c.value}
    change(ws, header)
    wb.save(path)


def _find(ws, header, url_part, agency="SWB", exact=False):
    """The row of the Citation Sheet for one agency whose address contains (or is) `url_part`."""
    return next(
        r
        for r in range(2, ws.max_row + 1)
        if ws.cell(r, header["Parastatal"]).value == agency
        and (
            str(ws.cell(r, header["Official URL"]).value or "") == url_part
            if exact
            else url_part in str(ws.cell(r, header["Official URL"]).value or "")
        )
    )


def _flag(path, url_part, *, use=None, flag="Yes", agency="SWB", exact=False):
    def change(ws, header):
        r = _find(ws, header, url_part, agency, exact)
        ws.cell(r, header[HUMAN_VERIFIED]).value = flag
        if use is not None:
            ws.cell(r, header["Use for Answers?"]).value = use

    _edit(path, change)


def _add_row(path, **values):
    def change(ws, header):
        r = ws.max_row + 1
        for name, value in values.items():
            ws.cell(r, header[name]).value = value

    _edit(path, change)


def _rows(path):
    wb = load_workbook(path)
    ws = wb[CITATIONS_SHEET]
    header = [c.value for c in ws[1]]
    return [
        dict(zip(header, [c.value for c in row], strict=False)) for row in ws.iter_rows(min_row=2)
    ]


def _row(path, url_part, agency="SWB"):
    return next(
        r
        for r in _rows(path)
        if r["Parastatal"] == agency and url_part in str(r["Official URL"] or "")
    )


@pytest.fixture
def step1(run_steps):
    """A first Step 1 run in practice mode: the Sources workbook, ready for the team's edits."""
    return Path(run_steps("sources")["output_workbook"])


def _again(services, llm=None):
    use = dataclasses.replace(services, llm=llm) if llm is not None else services
    return build_sources_graph(use).invoke(INPUTS)


# -- the column -----------------------------------------------------------------------------------
def test_the_column_is_last_with_its_exact_header_and_a_yes_no_dropdown(step1):
    wb = load_workbook(step1)
    ws = wb[CITATIONS_SHEET]
    assert ws.cell(1, ws.max_column).value == "Human-Verified?" == HUMAN_VERIFIED
    letter = ws.cell(1, ws.max_column).column_letter
    lists = [
        v for v in ws.data_validations.dataValidation if letter in str(v.sqref) and v.type == "list"
    ]
    assert lists and lists[0].formula1 == '"Yes,No"'
    assert all(r["Human-Verified?"] in (None, "") for r in _rows(step1))  # blank unless flagged


def test_a_flagged_row_is_written_as_yes_and_read_back(step1):
    _flag(step1, "bwssb.example.gov.in")
    row = _row(step1, "bwssb.example.gov.in")
    assert row["Human-Verified?"] == "Yes"
    workspace = step1.parent
    _, citations, _ = read_sources_workbook(step1, workspace / "evidence")
    flagged = [c for c in citations if c.human_verified]
    assert flagged and all("bwssb.example.gov.in" in c.url for c in flagged)


def test_a_flag_without_a_link_is_ignored_with_a_note_and_your_team_alone_is_not_a_flag(step1):
    _add_row(step1, **{"Parastatal": "SWB", "Source Title": "No link", HUMAN_VERIFIED: "Yes"})
    _add_row(
        step1,
        **{
            "Parastatal": "SWB",
            "Source Title": "Team row",
            "Official URL": PLAN,
            "Found By": "Your team",
        },
    )
    _, citations, issues = read_sources_workbook(step1, step1.parent / "evidence")
    assert any('"Human-Verified?" Yes' in i.message and "no web link" in i.message for i in issues)
    team = [c for c in citations if c.found_by == "Your team" and c.url == PLAN]
    assert team and not any(c.human_verified for c in team)


def test_an_old_workbook_without_the_column_loads_and_runs_as_before(services, step1, run_steps):
    def drop(ws, header):
        ws.delete_cols(header[HUMAN_VERIFIED])

    _edit(step1, drop)
    assert HUMAN_VERIFIED not in [c.value for c in load_workbook(step1)[CITATIONS_SHEET][1]]
    _, citations, _ = read_sources_workbook(step1, step1.parent / "evidence")
    assert citations and not any(c.human_verified for c in citations)
    _again(services)  # Step 1 again: the column comes back, blank
    assert HUMAN_VERIFIED in [c.value for c in load_workbook(step1)[CITATIONS_SHEET][1]]
    answers = run_steps("answers")["answers"]
    assert answers and all(a.status != "Answered — Human-Verified Source" for a in answers)


# -- Step 1: opens it, never lowers or clears the flag -----------------------------------------------
def test_a_flagged_row_that_opens_stays_verified_in_use_and_flagged(services, step1):
    _flag(step1, "bwssb.example.gov.in")
    _again(services)
    row = _row(step1, "bwssb.example.gov.in")
    assert row["Human-Verified?"] == "Yes" and row["Verification Status"] == "Verified"
    assert row["Use for Answers?"] == "Yes"


def test_a_flagged_row_the_assessor_doubts_stays_in_use_and_needs_attention(services, step1):
    _flag(step1, "bwssb.example.gov.in")
    result = _again(services, NotUseful())
    row = _row(step1, "bwssb.example.gov.in")
    assert row["Human-Verified?"] == "Yes"
    assert row["Verification Status"] == "Verified" and row["Use for Answers?"] == "Yes"
    assert HUMAN_DOUBT_NOTE in row["Notes"]
    lines = [m.message for m in result["final_issues"] if "doubts" in m.message]
    assert len(lines) == 1 and row["Citation ID"] in lines[0]
    # an app-found row the assessor doubts is still switched off, as before
    other = _row(step1, PLAN)  # the assessor's doubt still counts for a row nobody verified
    assert other["Verification Status"] == "Not verified"


def test_a_flagged_row_that_does_not_open_is_listed_and_a_saved_copy_makes_it_usable(
    services, step1
):
    lost = "https://bwssb.example.gov.in/lost-page"
    _add_row(
        step1,
        **{
            "Parastatal": "SWB",
            "Source Title": "Lost page",
            "Official URL": lost,
            "Use for Answers?": "Yes",
            HUMAN_VERIFIED: "Yes",
        },
    )
    result = _again(services)
    row = _row(step1, "lost-page")
    assert row["Human-Verified?"] == "Yes" and row["Use for Answers?"] == "Yes"
    assert row["Verification Status"] == "Human Verification Required"
    assert HUMAN_UNOPENED_NOTE in row["Notes"]
    lines = [
        m.message for m in result["final_issues"] if "could not be opened by the app" in m.message
    ]
    assert len(lines) == 1 and row["Citation ID"] in lines[0]
    # the team saves a copy by hand (evidence/manual/<Citation ID>.html): the row becomes usable
    folder = step1.parent / "evidence" / "manual"
    folder.mkdir(parents=True, exist_ok=True)
    words = " ".join(f"word{i}" for i in range(200))
    (folder / f"{row['Citation ID']}.html").write_text(f"<html><body><p>{words}</p></body></html>")
    _again(services)
    saved = _row(step1, "lost-page")
    assert saved["Verification Status"] == "Verified" and saved["Human-Verified?"] == "Yes"


@pytest.mark.parametrize("path", ["opens", "not useful", "does not open"])
def test_a_team_decision_of_no_on_a_flagged_row_is_kept(services, step1, path):
    url = "bwssb.example.gov.in"
    if path == "does not open":
        _add_row(
            step1,
            **{
                "Parastatal": "SWB",
                "Source Title": "Lost page",
                "Official URL": "https://bwssb.example.gov.in/lost-page",
                "Use for Answers?": "No",
                HUMAN_VERIFIED: "Yes",
            },
        )
        url = "lost-page"
    else:
        _flag(step1, url, use="No")
    _again(services, NotUseful() if path == "not useful" else None)
    row = _row(step1, url)
    assert row["Use for Answers?"] == "No" and row["Human-Verified?"] == "Yes"


# -- Step 1 never clears the flag, on any path -----------------------------------------------------
def test_a_repeat_run_keeps_the_flag_on_every_row_that_had_it(
    services, step1
):  # discovery, re-test
    _flag(step1, "bwssb.example.gov.in")
    _flag(step1, PLAN)
    _again(services)
    _again(services)
    flagged = {r["Official URL"] for r in _rows(step1) if r["Human-Verified?"] == "Yes"}
    assert any("bwssb.example.gov.in" in str(u) for u in flagged) and any(
        PLAN in str(u) for u in flagged
    )


def test_the_second_search_does_not_clear_or_duplicate_a_flagged_row(services, step1):  # fill_gaps
    _flag(step1, PLAN)  # the gap-filling search returns this very address
    _again(services)
    rows = [r for r in _rows(step1) if PLAN in str(r["Official URL"]) and r["Parastatal"] == "SWB"]
    assert len(rows) == 1 and rows[0]["Human-Verified?"] == "Yes"


def test_a_flagged_shared_law_row_keeps_its_flag(services, step1):  # shared rows are re-vetted
    shared = next(r for r in _rows(step1) if r["Parastatal"] == "All parastatals")
    _flag(step1, str(shared["Official URL"]), agency="All parastatals", exact=True)
    _again(services)
    again = next(r for r in _rows(step1) if r["Official URL"] == shared["Official URL"])
    assert again["Human-Verified?"] == "Yes"


def test_merging_duplicates_keeps_the_flag_if_any_copy_has_it():
    plain = Source(parastatal_id="A", title="t", url="https://x.gov.in/p", authority_score=9)
    flagged = plain.model_copy(update={"human_verified": True, "authority_score": 1})
    for order in ([plain, flagged], [flagged, plain]):
        merged = dedupe_sources(order)
        assert len(merged) == 1 and merged[0].human_verified


def test_the_dated_copy_converter_keeps_the_column_and_the_flag(services, step1, tmp_path):
    _flag(step1, "bwssb.example.gov.in")
    copy = tmp_path / "dated.xlsx"
    date_citation_sheet(step1, copy, CutoffRule(date(2026, 8, 31), "confirm"))
    ws = load_workbook(copy)[CITATIONS_SHEET]
    header = {c.value: c.column for c in ws[1] if c.value}
    r = _find(ws, header, "bwssb.example.gov.in")
    assert ws.cell(r, header[HUMAN_VERIFIED]).value == "Yes"


def test_the_crawl_keeps_the_flag_on_the_home_row_and_is_not_completed_by_a_flagged_row(
    services, monkeypatch
):
    from asics_agent import practice
    from asics_agent.agents import links_builder

    base = practice.SITE
    menu = "".join(f"<li><a href='/{n}'>{n}</a></li>" for n in ("about", "budget"))
    pages = dict(practice.PAGES)
    pages[base] = (
        f"<html><body><nav class='menu'><ul>{menu}</ul></nav><p>{practice.SITE_TEXT}</p>"
        f"<p>{' '.join(f'w{i}' for i in range(200))}</p></body></html>"
    )
    for n in ("about", "budget"):
        pages[f"{base}{n}"] = (
            f"<html><body><p>{n} {' '.join(f'w{i}' for i in range(200))}</p></body></html>"
        )
    monkeypatch.setattr(practice, "PAGES", pages)
    path = Path(build_sources_graph(services).invoke(INPUTS)["output_workbook"])
    _flag(path, base, exact=True)  # the home page row
    _flag(path, f"{base}budget", exact=True)  # a menu page, already in the sheet

    opened = []
    real = links_builder.vet_many

    def spy(services_, run, parastatal, candidates, **kw):
        opened.append((kw.get("label"), [c.url for c in candidates]))
        return real(services_, run, parastatal, candidates, **kw)

    monkeypatch.setattr(links_builder, "vet_many", spy)
    result = build_sources_graph(services).invoke(INPUTS)
    home = next(
        s
        for s in result["final_sources"]
        if s.parastatal_id == "SWB" and s.source_type.lower() == "official website"
    )
    assert home.human_verified and "SITE-CRAWL: complete" in home.notes
    crawl = [urls for label, urls in opened if label == "Opening the site's menu links"]
    # the flagged menu page was opened again by the crawl; the unflagged one was not (already captured)
    assert any(f"{base}budget" in urls for urls in crawl)
    assert not any(f"{base}about" in urls for urls in crawl)
    budget = [s for s in result["final_sources"] if s.url == f"{base}budget"]
    assert len(budget) == 1 and budget[0].human_verified  # merged into one row, flag kept


# -- the gate and the scan: a flagged row counts as any other row -----------------------------------
def _source(tmp_path, n, tag, *, human=True, verified=True, text="Section 1. Short title."):
    page = tmp_path / f"s{n}.txt"
    page.write_text(text)
    return Source(
        citation_id=f"AAA-{n:02d}",
        parastatal_id="AAA",
        title=f"Doc {n}",
        url=f"https://example.gov.in/{n}",
        useful_for=f"[{tag}]",
        verification_status="Verified" if verified else "Human Verification Required",
        use_for_answers=True,
        content_path=str(page) if verified else None,
        human_verified=human,
    )


@pytest.fixture
def agency():
    return Parastatal(
        id="AAA",
        name="Sample Board",
        type="water_supply_entity",
        governing_act="The Sample Water Act, 1970",
        official_website="https://www.sample-board.in/",
    )


def test_a_flagged_row_is_a_present_required_document_only_when_verified_with_saved_text(
    tmp_path, agency
):
    req = sr.required_for("UPD 3a")  # needs the Act and its Rules
    ok = [_source(tmp_path, 1, "ACT"), _source(tmp_path, 2, "RULES")]
    assert sr.check(req, agency, ok).state == "allowed"
    unopened = [_source(tmp_path, 1, "ACT"), _source(tmp_path, 2, "RULES", verified=False)]
    gate = sr.check(req, agency, unopened)
    assert gate.state == "unreadable" and gate.unreadable == ["AAA-02"]


def test_a_flagged_row_does_not_bypass_the_scan(tmp_path, agency):
    text = "Section 5. Concessions for the poor and for women shall be provided on the tariff."
    sources = [_source(tmp_path, 1, "ACT", text=text), _source(tmp_path, 2, "RULES")]
    decision = sr.decide_zero(sr.required_for("UPD 3a"), agency, sources)
    assert decision.state == "blocked_by_scan" and not decision.allowed


def test_a_flagged_page_does_not_complete_the_site_crawl(tmp_path, agency):
    home = Source(
        parastatal_id="AAA",
        title="Website",
        url="https://www.sample-board.in/",
        source_type="Official website",
        verification_status="Verified",
        use_for_answers=True,
        content_path=str(tmp_path / "h.txt"),
    )
    (tmp_path / "h.txt").write_text("home")
    page = _source(tmp_path, 5, "WEB-FEATURE").model_copy(
        update={"url": "https://www.sample-board.in/budget"}
    )
    gate = sr.check(sr.required_for("SC 6b"), agency, [home, page])
    assert gate.missing == ["SITECRAWL"]  # no complete crawl: the flagged page cannot stand in


# -- Step 2: the mark, the pinning order and the status --------------------------------------------
from tests.test_step2_zero_gate import Scripted, ask, bank, make_source  # noqa: E402,F401

ANSWER = {
    "sufficiency": "sufficient",
    "answer": "Consultation is mandatory.",
    "proposed_score": 2.5,
    "citation_id": "AAA-01",
    "citation": "Section 16",
    "evidence_excerpt": "The Board shall prepare its plan in consultation with the Corporation",
    "notes": "CLASS: A1; CONFIDENCE: Medium; BAND: 2.5",
}
TEXT = "Section 16. The Board shall prepare its plan in consultation with the Corporation."


def test_an_answer_resting_on_a_human_verified_row_gets_the_new_status(ask, make_source):
    sources = [make_source("ACT", TEXT, human=True, qids=["UPD 1a"]), make_source("RULES")]
    answer, message = ask("UPD 1a", ANSWER, sources)
    assert answer.status == "Answered — Human-Verified Source"
    assert HUMAN_VERIFIED_MARK in message
    assert "Main source human-verified" in answer.notes


def test_an_answer_resting_on_another_row_keeps_the_old_status(ask, make_source):
    sources = [make_source("ACT", TEXT), make_source("RULES", human=True)]
    answer, message = ask("UPD 1a", ANSWER, sources)
    assert answer.status == "Answered — Verified Source"
    assert "Main source human-verified" not in answer.notes


def test_a_mixed_answer_follows_the_main_citation_and_lists_the_others(ask, make_source):
    # main citation app-found, a second source human-verified
    sources = [make_source("ACT", TEXT), make_source("RULES", human=True)]
    reply = {
        **ANSWER,
        "citation_id": sources[0].citation_id,
        "notes": f"{ANSWER['notes']} ALSO: {sources[1].citation_id}",
    }
    answer, _ = ask("UPD 1a", reply, sources)
    assert answer.status == "Answered — Verified Source"
    assert f"Other sources used: {sources[1].citation_id} (human-verified)." in answer.notes
    # main citation human-verified, a second source app-found
    sources = [make_source("ACT", TEXT, human=True), make_source("RULES")]
    reply = {
        **ANSWER,
        "citation_id": sources[0].citation_id,
        "notes": f"{ANSWER['notes']} ALSO: {sources[1].citation_id}",
    }
    answer, _ = ask("UPD 1a", reply, sources)
    assert answer.status == "Answered — Human-Verified Source"
    assert f"Other sources used: {sources[1].citation_id} (app-found)." in answer.notes


def test_the_setting_off_means_no_mark_and_the_old_status(ask, make_source):
    sources = [make_source("ACT", TEXT, human=True)]
    answer, message = ask("UPD 1a", ANSWER, sources, human=False)
    assert answer.status == "Answered — Verified Source"
    assert "HUMAN-VERIFIED" not in message


def test_a_human_verified_zero_checked_answer_follows_its_main_citation(ask, make_source):
    reply = {
        "sufficiency": "sufficient",
        "answer": "No role.",
        "proposed_score": 0,
        "zero_checked": True,
        "notes": "CLASS: A1; CONFIDENCE: High; BAND: 0",
    }
    sources = [make_source("ACT", human=True), make_source("RULES"), make_source("TCP")]
    answer, _ = ask("UPD 1a", reply, sources)
    assert answer.status == "Answered — Human-Verified Source" and answer.proposed_score == 0
    assert answer.confidence == "Medium"  # the zero rule is unchanged: never High


def test_human_verified_rows_tagged_for_the_question_are_pinned_before_required_rows(
    ask, make_source
):
    filler = "Nothing about plans here. " * 40
    # eight ordinary rows that rank high, a required Act, and two flagged rows
    sources = [make_source("OTHER", f"{TEXT} {i}") for i in range(8)]
    required = [
        make_source("ACT", filler),
        make_source("RULES", filler),
        make_source("TCP", filler),
    ]
    tagged = make_source("MISC", filler, human=True, qids=["UPD 1a"])
    untagged = make_source("MISC", filler, human=True, qids=[])
    answer, message = ask("UPD 1a", ANSWER, [*sources, *required, tagged, untagged])
    assert f"=== CITATION {tagged.citation_id}" in message  # pinned first
    assert f"=== CITATION {required[0].citation_id}" in message  # then the required rows
    assert f"=== CITATION {untagged.citation_id}" not in message  # no priority when not tagged
    assert message.count("=== CITATION") == 8  # within the 8 in all


# -- Step 3: the new status passes, and the scorer is told ------------------------------------------
from tests.test_template_scoring import _reply, _scorer, _tagged  # noqa: E402


def test_step3_takes_the_new_status_and_says_the_source_is_human_verified(tmp_path, monkeypatch):
    prompts = []
    flagged = _tagged(
        tmp_path, 1, "ACT", "Section 16. The Board shall prepare its plans.", human=True
    )
    cell, spec = _scorer(
        tmp_path,
        monkeypatch,
        "UPD",
        "UPD 1a",
        _reply(score=5, quote="The Board shall prepare its plans", citation_id="TWB-01"),
        sources=[flagged],
        status="Answered — Human-Verified Source",
        prompts=prompts,
    )
    assert cell.outcome == "scored" and cell.values[spec.score_column] == 5
    comments = cell.values[spec.column_for("comments")]
    assert comments.startswith("Source human-verified.")
    assert "Source human-verified" in cell.values[spec.column_for("additional_comments")]
    assert "[HUMAN-VERIFIED]" in prompts[0] and HUMAN_VERIFIED_MARK in prompts[0]


def test_step3_does_not_mark_an_app_found_source(tmp_path, monkeypatch):
    prompts = []
    plain = _tagged(tmp_path, 1, "ACT", "Section 16. The Board shall prepare its plans.")
    cell, spec = _scorer(
        tmp_path,
        monkeypatch,
        "UPD",
        "UPD 1a",
        _reply(score=5, quote="The Board shall prepare its plans", citation_id="TWB-01"),
        sources=[plain],
        prompts=prompts,
    )
    assert cell.outcome == "scored"
    assert "human-verified" not in cell.values[spec.column_for("comments")].lower()
    assert "HUMAN-VERIFIED" not in prompts[0]


def test_step3_refuses_nothing_because_of_the_new_status_when_the_gate_applies(
    tmp_path, monkeypatch
):
    # a ZERO-CHECKED answer on a human-verified main citation: the same gate runs as for any status
    sources = [
        _tagged(tmp_path, 1, "ACT", human=True),
        _tagged(tmp_path, 2, "RULES"),
        _tagged(tmp_path, 3, "TCP"),
    ]
    cell, spec = _scorer(
        tmp_path,
        monkeypatch,
        "UPD",
        "UPD 1a",
        _reply(score=0, quote="", citation_id="TWB-01"),
        required=True,
        sources=sources,
        notes="ZERO-CHECKED: Checked: TWB-01.",
        status="Answered — Human-Verified Source",
    )
    assert cell.outcome == "scored" and cell.values[spec.score_column] == 0


# -- Compare: the Source origin split ---------------------------------------------------------------
from tests.test_compare_human_ai import CITY, build, by_key, human  # noqa: E402
from tests.test_compare_human_ai import bank as compare_bank  # noqa: E402,F401


def _s2(bank, code, cid, score, notes=""):
    return [
        "Water Board",
        bank[code].raw_id,
        bank[code].text,
        "Answered — Human-Verified Source" if cid == "BWSSB-01" else "Answered — Verified Source",
        "x",
        score,
        "A1",
        "Medium",
        "",
        "",
        "",
        notes,
        cid,
    ]


def test_compare_splits_coverage_agreement_and_false_zeros_by_source_origin(tmp_path, compare_bank):
    from asics_agent.scoring import compare as cmp

    bank = compare_bank
    a, b, c = [code for code, q in bank.items() if q.tag == "SQ" and q.max_score][:3]
    water = Parastatal(
        id="BWSSB", name="Water Board", type="water_supply_entity", governing_act="Water Act, 1970"
    )
    page = tmp_path / "p.txt"
    page.write_text("text")

    def row(cid, human, qids):
        return Source(
            citation_id=cid,
            parastatal_id="BWSSB",
            title=cid,
            url=f"https://x.gov.in/{cid}",
            verification_status="Verified",
            use_for_answers=True,
            content_path=str(page),
            human_verified=human,
            question_ids=qids,
        )

    comp = build(
        tmp_path,
        bank,
        human_rows=[human(a, "BWSSB", 5.0), human(b, "BWSSB", 5.0), human(c, "BWSSB", 0.0)],
        s2_rows=[_s2(bank, a, "BWSSB-01", 5), _s2(bank, b, "BWSSB-02", 0)],
        s3_rows=[
            [a.replace(" ", ""), f"{CITY} – BWSSB", "", 5, "", ""],
            [b.replace(" ", ""), f"{CITY} – BWSSB", "", 0, "", ""],
        ],
        extra_info={
            "parastatals": {"BWSSB": water},
            "citations": [
                row("BWSSB-01", True, [a]),
                row("BWSSB-02", False, [b]),
                row("BWSSB-03", True, [c]),
            ],
        },
    )
    rows = by_key(comp)
    assert rows[("BWSSB", a)].source_origin == "Human-verified"
    assert rows[("BWSSB", b)].source_origin == "App-found"
    # the AI left c blank: it cites nothing, so App-found, but a human-verified source was available
    assert rows[("BWSSB", c)].source_origin == "App-found"
    assert rows[("BWSSB", c)].hv_available == "Yes" and rows[("BWSSB", b)].hv_available == "No"

    split = {r[0]: r for r in cmp.summarise_with_zeros(comp.rows, lambda r: r.source_origin, 1)}
    human_verified, app_found = split["Human-verified"], split["App-found"]
    # [group, human scored, coverage, compared, agree, % agree, only human, only AI, AI zeros, false zeros]
    assert human_verified[1:5] == [1, "1 of 1 (100%)", 1, 1] and human_verified[8:] == [0, 0]
    assert app_found[1] == 2 and app_found[2] == "1 of 2 (50%)" and app_found[8:] == [1, 1]

    path = cmp.write_comparison(comp, tmp_path / "o.xlsx", min_rows=1)
    wb = load_workbook(path)
    lines = [r for r in wb["Summary"].iter_rows(values_only=True)]
    start = next(
        i for i, r in enumerate(lines) if r[0] == "By source origin (the rows the AI cited)"
    )
    assert lines[start][-2:] == ("AI zeros", "False zeros (AI 0, human above 0)")
    assert {lines[start + 1][0], lines[start + 2][0]} == {"App-found", "Human-verified"}
    assert any(r[0] == "By human-verified source available for the question" for r in lines)
    zero_header = [c.value for c in wb["AI zeros"][1]]
    assert zero_header[-2:] == ["Source origin", "Human-verified source available?"]
    zero_row = dict(zip(zero_header, [c.value for c in wb["AI zeros"][2]], strict=True))
    assert (
        zero_row["Source origin"] == "App-found"
        and zero_row["False zero? (AI 0, human above 0)"] == "Yes"
    )
    compare_header = [c.value for c in wb["Compare"][1]]
    assert (
        "Source origin" in compare_header and "Human-verified source available?" in compare_header
    )
