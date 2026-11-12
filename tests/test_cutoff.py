"""Methodology as the rule, and the Law/Policy cut-off (31 Aug 2026).

Practice mode and stubs only: no model is called and nothing costs money.
"""

import hashlib
import json
import warnings
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from openpyxl import load_workbook

from asics_agent import citation_dates, cutoff, methodology
from asics_agent.agents.sections import base
from asics_agent.categories import _parse, category_settings, load_bank, load_categories
from asics_agent.config import get_settings
from asics_agent.models import Parastatal, Source
from asics_agent.scoring import template_fill as fill
from asics_agent.scoring import template_scoring as ts
from asics_agent.scoring.ai import ScoreReply
from asics_agent.scoring.phase2 import CityEvidence, StepTwoAnswer
from asics_agent.skill_check import skill_problems
from asics_agent.sources_workbook import (
    read_sources_workbook,
    sources_path,
    workspace_for,
)
from tests.refdata import ROOT, reference_templates

RULE = cutoff.CutoffRule(date(2026, 8, 31))
BLOCK = cutoff.CutoffRule(date(2026, 8, 31), "block")
REAL = ROOT / "outputs" / "Parastatal" / "cities"


def src(cid, check="", effective="", status="Unknown", title="An Act", **kw):
    return Source(
        citation_id=cid,
        parastatal_id="SWB",
        title=title,
        url=f"https://x.gov.in/{cid}",
        current_status=status,
        effective_date=effective,
        cutoff_check=check,
        **kw,
    )


# -- the Law/Policy test and the dates ------------------------------------------------------------
def test_every_level_spelling_in_both_banks_is_read():
    law, other = set(), set()
    for name in ("parastatal", "ulg"):
        bank, _ = load_bank(category_settings(get_settings(), name))
        for q in bank.values():
            (law if cutoff.is_law_policy(q.assessment_level) else other).add(q.assessment_level)
    assert {"Law/Policy", "Law/policy", "Law or Policy", "Law/Policy & Implementation"} <= law
    assert {"Law or Policy & Implementation", "Law or Policy/Implementation"} <= law
    assert {"Law/Policy + Implementation", "Law/Policy and Implementation"} <= law
    assert {None, "Implementation", "Implementation (Numeric)"} <= other
    assert "NA- question already covered in ASICS 2017" in other
    bank, _ = load_bank(category_settings(get_settings(), "parastatal"))
    leaf_law = [
        q.id for q in bank.values() if not q.is_rollup and cutoff.is_law_policy(q.assessment_level)
    ]
    assert len(leaf_law) == 19 and "DPG 1a" in leaf_law and "DPG 4" in leaf_law


def test_a_date_needs_a_day_and_a_year_alone_is_not_a_date():
    d = cutoff.parse_date
    assert (
        d("2026-03-31")
        == d("31.03.2026")
        == d("31/03/2026")
        == d("31 Mar 2026")
        == date(2026, 3, 31)
    )
    assert d("Mar 31, 2026") == date(2026, 3, 31) and d("w.e.f. 1.6.2005") == date(2005, 6, 1)
    assert d("2025") is None and d("Mar 2026") is None and d("Act 36 of 2025") is None


def test_the_check_follows_the_effective_date_and_the_form():
    c = cutoff.check_from
    assert c("2026-08-31", "in force", RULE) == "ok"  # on the cut-off day counts
    assert c("2026-09-01", "in force", RULE) == "later"
    assert c("", "in force", RULE) == "unknown"
    assert c("2025", "in force", RULE) == "unknown"  # a year only
    assert (
        c("2020-01-01", "bill", RULE) == "Bill-draft"
        and c("2020-01-01", "draft", RULE) == "Bill-draft"
    )
    assert cutoff.assessment_fields("2024-05-01", "in force", None) == ("2024-05-01", "")  # no rule


def test_the_pages_last_updated_date_is_never_the_effective_date():
    status = "Current; era=n/a; period=page footer 'Last Updated on: 12-Oct-2026'; Act as amended up to 31.03.2024"
    assert cutoff.fallback_from_text(status, "An Act", RULE) == ("2024-03-31", "ok")
    only_page = "Current; era=n/a; period=page last updated 12-Oct-2026"
    assert cutoff.fallback_from_text(only_page, "A website", RULE) == ("", "unknown")
    assert cutoff.fallback_from_text("Unknown", "A website", RULE) == ("", "unknown")
    year = "Current status unclear; era=n/a; period=as enacted 2019"
    assert cutoff.fallback_from_text(year, "An Act", RULE) == ("", "unknown")  # not ok
    bill = "Current status unclear; era=GBA-era; period=Bill as printed 12 Aug 2025"
    assert cutoff.fallback_from_text(bill, "A Bill", RULE) == ("", "Bill-draft")
    later = "Current; period=Act as amended up to 05.10.2026 (assent)"
    assert cutoff.fallback_from_text(later, "An Act", RULE)[1] == "later"


# -- which sources a question may use -----------------------------------------------------------
def test_only_a_law_policy_question_is_restricted():
    sources = [src("A", "ok"), src("B", "later"), src("C", "Bill-draft"), src("D", "unknown")]
    law = cutoff.screen_sources(sources, RULE, True)
    assert [s.citation_id for s in law.usable] == ["A", "D"]
    assert law.later == ["B"] and law.bills == ["C"] and law.unknown == {"D"} and not law.pending
    impl = cutoff.screen_sources(sources, RULE, False)  # a "later" source stays usable here
    assert [s.citation_id for s in impl.usable] == ["A", "B", "C", "D"] and not impl.pending
    assert cutoff.screen_sources(sources, None, True).usable == sources  # no cut-off set


def test_undated_confirm_or_block():
    sources = [src("A", "ok"), src("D", "unknown")]
    assert [s.citation_id for s in cutoff.screen_sources(sources, BLOCK, True).usable] == ["A"]
    assert cutoff.screen_sources(sources, BLOCK, True).blocked_unknown == ["D"]
    only = cutoff.screen_sources([src("D", "unknown")], BLOCK, True)
    assert not only.usable and "undated" in only.pending


def test_when_every_source_is_later_or_a_bill_the_answer_is_pending_fetch():
    screen = cutoff.screen_sources([src("A", "later"), src("B", "Bill-draft")], RULE, True)
    assert not screen.usable
    assert screen.pending.startswith("every available source is dated after 31 Aug 2026 (A)")
    assert "a Bill or draft, not law in force (B)" in screen.pending and "\n" not in screen.pending
    assert cutoff.screen_sources([], RULE, True).pending == ""  # no sources at all: the old message


def test_old_rows_without_the_columns_are_read_from_their_text():
    old = src("OLD", status="Current status unclear; period=as amended up to 31.03.2024")
    assert cutoff.check_of(old, RULE) == "ok"
    filled = src("NEW", check="later", status="Current; period=as amended up to 31.03.2024")
    assert cutoff.check_of(filled, RULE) == "later"  # the column wins over the text
    assert cutoff.check_of(src("E", effective="2030-01-01"), RULE) == "later"


def test_period_in_the_answer_after_the_cutoff_is_found():
    text = "ANSWER: yes | EVIDENCE: s.5 | CAVEATS: none | PERIOD: Act as amended up to 12.10.2026 | LIMITS: none"
    assert cutoff.period_after_cutoff(text, RULE) == date(2026, 10, 12)
    ok = "ANSWER: yes | PERIOD: as amended up to 31.03.2024; page fetched 13-10-2026 | LIMITS: none"
    assert cutoff.period_after_cutoff(ok, RULE) is None  # a fetch date is not the law's period
    assert cutoff.confirm_note("BWSSB-04", RULE).startswith(
        "CONFIRM: BWSSB-04 has no effective date"
    )
    assert cutoff.cap_confidence("High") == "Medium" and cutoff.cap_confidence("Low") == "Low"


# -- settings, summaries, page line -------------------------------------------------------------
def test_the_setting_is_read_and_shown():
    assert get_settings().law_cutoff == date(2026, 8, 31)
    assert get_settings().undated_law_policy == "confirm"
    assert category_settings(get_settings(), "ulg").law_cutoff is None  # the ULG is unchanged
    assert cutoff.rule_from(category_settings(get_settings(), "ulg")) is None
    line = cutoff.describe(cutoff.rule_from(get_settings()))
    assert "31 Aug 2026" in line and "CONFIRM" in line and "law_cutoff" in line


def test_a_bad_setting_is_reported(tmp_path):
    folder = tmp_path / "categories"
    folder.mkdir()
    (folder / "x.md").write_text(
        "---\nname: x\nlaw_cutoff: next week\nundated_law_policy: maybe\n---\n"
    )
    found, issues = load_categories(tmp_path)
    messages = " ".join(i.message for i in issues)
    assert (
        "law_cutoff must be a date" in messages
        and "undated_law_policy must be confirm or block" in messages
    )
    assert _parse(folder / "x.md").law_cutoff == "next week"


# -- the Citation Sheet: two new columns, old sheets still load ----------------------------------
def test_the_new_columns_round_trip_and_an_old_sheet_still_loads(services, run_steps, tmp_path):
    run_steps("sources")
    path = sources_path(
        workspace_for(services.settings.outputs_dir, "Sample City A"), "Sample City A"
    )
    ws = load_workbook(path)["Citation Sheet"]
    header = [c.value for c in ws[1]]
    assert header[-2:] == ["Effective / As-of Date", "Cut-off Check"]
    rows = [
        dict(zip(header, [c.value for c in r], strict=False))
        for r in ws.iter_rows(min_row=2)
        if r[0].value
    ]
    verified = [r for r in rows if r["Verification Status"] == "Verified"]
    assert verified and all(
        r["Cut-off Check"] == "ok" and r["Effective / As-of Date"] == "1964-04-01" for r in verified
    )
    # a row the assessor never read (not verified) is left blank, and is not usable anyway
    assert all(not r["Cut-off Check"] for r in rows if r["Verification Status"] != "Verified")
    # remove the two columns: a sheet from before this work loads, with the fields empty
    wb = load_workbook(path)
    ws = wb["Citation Sheet"]
    ws.delete_cols(len(header) - 1, 2)
    old = tmp_path / path.name
    wb.save(old)
    _, citations, issues = read_sources_workbook(old, tmp_path / "evidence")
    assert citations and all(c.effective_date == "" and c.cutoff_check == "" for c in citations)
    assert not [i for i in issues if i.severity == "error"]


@pytest.mark.skipif(
    not (REAL / "Bengaluru" / "ASICS_Bengaluru_Sources.xlsx").exists(), reason="no real sheet"
)
def test_the_real_old_sheet_loads_and_the_converter_never_touches_it(tmp_path):
    original = REAL / "Bengaluru" / "ASICS_Bengaluru_Sources.xlsx"
    before = hashlib.sha256(original.read_bytes()).hexdigest()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        _, citations, _ = read_sources_workbook(original, tmp_path / "evidence")
        assert citations and all(c.cutoff_check == "" for c in citations)
        copy = tmp_path / "Bengaluru_dated.xlsx"
        report = citation_dates.date_citation_sheet(original, copy, RULE)
    assert hashlib.sha256(original.read_bytes()).hexdigest() == before  # the original is untouched
    assert report.rows == len(citations) == 240
    assert report.dated + report.bill_draft + report.year_only + report.unknown == report.rows
    assert report.year_only > 0 and report.dated > 0 and report.bill_draft > 0
    assert (
        report.legal_dated + report.legal_bill + report.legal_year_only + report.legal_unknown
        == report.legal_rows
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        _, dated, _ = read_sources_workbook(copy, tmp_path / "evidence")
    checks = [c.cutoff_check for c in dated]
    assert checks.count("ok") + checks.count("later") == report.dated
    assert checks.count("Bill-draft") == report.bill_draft
    # a year alone never became a date
    assert all(c.effective_date == "" or cutoff.parse_date(c.effective_date) for c in dated)
    with pytest.raises(ValueError):
        citation_dates.date_citation_sheet(original, original, RULE)
    with pytest.raises(FileExistsError):
        citation_dates.date_citation_sheet(original, copy, RULE)


def test_the_converter_leaves_filled_rows_alone(services, run_steps, tmp_path):
    run_steps("sources")
    path = sources_path(
        workspace_for(services.settings.outputs_dir, "Sample City A"), "Sample City A"
    )
    wb = load_workbook(path)
    ws = wb["Citation Sheet"]
    header = [c.value for c in ws[1]]
    ws.cell(2, header.index("Cut-off Check") + 1, "later")
    ws.cell(2, header.index("Effective / As-of Date") + 1, "2026-10-01")
    wb.save(tmp_path / "in.xlsx")
    report = citation_dates.date_citation_sheet(tmp_path / "in.xlsx", tmp_path / "out.xlsx", RULE)
    assert report.already_filled >= 1
    out = load_workbook(tmp_path / "out.xlsx")["Citation Sheet"]
    assert out.cell(2, header.index("Cut-off Check") + 1).value == "later"
    assert out.cell(2, header.index("Effective / As-of Date") + 1).value == "2026-10-01"


# -- Step 2: the cut-off in the answers ------------------------------------------------------------
def _set_sheet(services, **by_column):
    path = sources_path(
        workspace_for(services.settings.outputs_dir, "Sample City A"), "Sample City A"
    )
    wb = load_workbook(path)
    ws = wb["Citation Sheet"]
    header = [c.value for c in ws[1]]
    for r in range(2, ws.max_row + 1):
        for name, value in by_column.items():
            ws.cell(r, header.index(name) + 1, value)
    wb.save(path)


@pytest.fixture
def step2(monkeypatch, run_steps, services):
    """Run Step 2 for UPD 1 (UPD 1a is Law/Policy, UPD 1b Implementation), recording the messages."""
    seen: list[str] = []
    real = base.call_json

    def call_json(svc, agent, message, schema, *a, **k):
        seen.append(message)
        reply, urls, notes = real(svc, agent, message, schema, *a, **k)
        if hasattr(reply, "notes"):
            reply = reply.model_copy(
                update={"notes": "CLASS: A1; CONFIDENCE: High; BAND: 10 " + reply.notes}
            )
        return reply, urls, notes

    def run(**columns):
        run_steps("sources")
        if columns:
            _set_sheet(services, **columns)
        monkeypatch.setattr(base, "call_json", call_json)
        result = run_steps("answers")
        return (
            {a.question_id: a for a in result["answers"] if a.parastatal_id == "SWB"},
            seen,
            result,
        )

    return run


def test_a_later_source_is_not_shown_for_law_policy_and_gives_pending_fetch(step2):
    answers, seen, result = step2(
        **{"Cut-off Check": "later", "Effective / As-of Date": "2026-10-01"}
    )
    law = answers["UPD 1a"]
    assert law.status == "Human Verification Required"
    assert law.answer.startswith("PENDING FETCH: every available source is dated after 31 Aug 2026")
    assert law.citation_id == "" and law.proposed_score is None  # never invent an answer
    assert "CONFIRM: PENDING FETCH" in law.notes
    # the Implementation question is NOT blocked: the "later" source is still used
    impl = answers["UPD 1b"]
    assert impl.citation_id and impl.status != "Human Verification Required"
    assert all("Question UPD1a" not in m and "Question UPD 1a" not in m for m in seen)
    summary = json.loads((Path(result["output_workbook"]).parent / "run_summary.json").read_text())
    assert summary["law_cutoff"] == "2026-08-31" and summary["undated_law_policy"] == "confirm"


def test_a_bill_is_not_law_in_force(step2):
    answers, _, _ = step2(**{"Cut-off Check": "Bill-draft", "Effective / As-of Date": ""})
    assert (
        answers["UPD 1a"].answer.startswith("PENDING FETCH:")
        and "Bill or draft" in answers["UPD 1a"].answer
    )
    assert answers["UPD 1b"].citation_id  # an Implementation question still uses it


def test_an_undated_source_is_used_with_a_confirm_note_and_confidence_capped(step2):
    answers, _, _ = step2(**{"Cut-off Check": "unknown", "Effective / As-of Date": ""})
    law = answers["UPD 1a"]
    assert law.citation_id and law.status != "Human Verification Required"
    assert "CONFIRM:" in law.notes and "has no effective date" in law.notes
    assert law.confidence == "Medium"  # the model said High; capped
    assert answers["UPD 1b"].confidence == "High"  # an Implementation question is not capped


def test_undated_block_treats_an_undated_source_like_a_later_one(step2, monkeypatch):
    monkeypatch.setattr(
        base,
        "cutoff",
        SimpleNamespace(**{**vars(cutoff), "rule_from": lambda settings: BLOCK}),
    )
    answers, _, _ = step2(**{"Cut-off Check": "unknown", "Effective / As-of Date": ""})
    assert (
        answers["UPD 1a"].answer.startswith("PENDING FETCH:")
        and "undated" in answers["UPD 1a"].answer
    )
    assert answers["UPD 1b"].citation_id


def test_a_source_in_force_is_used_normally(step2):
    answers, _, _ = step2()
    law = answers["UPD 1a"]
    assert (
        law.citation_id
        and "PENDING FETCH" not in law.notes
        and "has no effective date" not in law.notes
    )


def test_the_band_must_be_a_level_of_the_methodology(monkeypatch, run_steps, services):
    real = base.call_json

    def call_json(svc, agent, message, schema, *a, **k):
        reply, urls, notes = real(svc, agent, message, schema, *a, **k)
        if hasattr(reply, "notes"):
            reply = reply.model_copy(
                update={"notes": "CLASS: A1; CONFIDENCE: Low; BAND: 7.3 " + reply.notes}
            )
        return reply, urls, notes

    run_steps("sources")
    monkeypatch.setattr(base, "call_json", call_json)
    answers = {
        a.question_id: a for a in run_steps("answers")["answers"] if a.parastatal_id == "SWB"
    }
    assert (
        'CONFIRM: BAND "7.3" is not a level of the methodology (levels: 10 / 2.5 / 0)'
        in answers["UPD 1a"].notes
    )


# -- Step 3 -----------------------------------------------------------------------------------------
def _score(
    tmp_path, monkeypatch, cited, others=(), law=True, confidence="high", rule=RULE, band=""
):
    templates = {p.name.split("_")[1]: p for p in reference_templates()}
    ai = fill.AITemplate(tmp_path / "u.xlsx", templates["UPD"])
    spec = ai.specs["UPD 1a"]
    page = tmp_path / "source.txt"
    page.write_text("Section 16. The Board shall prepare its plans in coordination with the ULG.")
    sources = [cited, *others]
    for s in sources:
        s.content_path = str(page)
        s.verification_status = "Verified"
    unit = Parastatal(id="SWB", name="Water Board", type="water_supply_entity")
    answer = StepTwoAnswer(
        "Answered — Verified Source",
        "Yes",
        cited.citation_id,
        "shall prepare",
        "",
        "",
        question=spec.question,
        answer_class="A1",
        confidence="High",
    )
    evidence = CityEvidence(
        parastatals={"SWB": unit}, citations=sources, answers={("SWB", "UPD1a"): answer}
    )
    seen = {}

    def call_json(*args, **kwargs):
        seen["message"] = args[2]
        reply = ScoreReply(
            citation_id=cited.citation_id,
            quote="shall prepare its plans in coordination",
            comments="Clear.",
            confidence=confidence,
            score=5,
            band=band,
        )
        return reply, None, None

    monkeypatch.setattr(ts, "call_json", call_json)
    settings = category_settings(get_settings(), "parastatal")
    import dataclasses

    settings = dataclasses.replace(
        settings,
        law_cutoff=rule.day if rule else None,
        undated_law_policy=rule.undated if rule else "confirm",
    )
    task = ts.TemplateTask("UPD", "UPD 1a", "T", "S", "SWB", "T – SWB", unit, law)
    cell = ts.score_template_one(SimpleNamespace(settings=settings), task, spec, evidence, "r")
    return cell, spec, seen


def test_step3_leaves_a_row_when_step2_relied_on_a_later_source(tmp_path, monkeypatch):
    cell, spec, seen = _score(tmp_path, monkeypatch, src("SWB-01", "later", "2026-10-01"))
    assert cell.outcome == "needs_person" and cell.kind == "cutoff"
    assert "Cut-off: Step 2 relied on SWB-01, which is dated after 31 Aug 2026" in cell.detail
    assert "message" not in seen  # the model was never asked
    bill, _, _ = _score(tmp_path, monkeypatch, src("SWB-02", "Bill-draft"))[:3]
    assert bill.kind == "cutoff" and "Bill or draft" in bill.detail


def test_step3_uses_an_ok_source_and_hides_the_later_ones_from_the_model(tmp_path, monkeypatch):
    cell, spec, seen = _score(
        tmp_path,
        monkeypatch,
        src("SWB-01", "ok", "2024-01-01"),
        [src("SWB-09", "later", "2026-10-01")],
    )
    assert cell.outcome == "scored"
    assert "SWB-01" in seen["message"] and "SWB-09" not in seen["message"]


def test_step3_unknown_is_confirmed_and_capped_and_block_leaves_it(tmp_path, monkeypatch):
    cell, spec, _ = _score(tmp_path, monkeypatch, src("SWB-01", "unknown"))
    comments = cell.values[spec.column_for("comments")]
    assert cell.outcome == "scored" and "CONFIRM: SWB-01 has no effective date" in comments
    assert "AI (medium confidence)" in comments  # the model said high
    blocked, _, seen = _score(tmp_path, monkeypatch, src("SWB-01", "unknown"), rule=BLOCK)
    assert (
        blocked.kind == "cutoff"
        and "undated sources are blocked" in blocked.detail
        and "message" not in seen
    )


def test_step3_does_not_restrict_an_implementation_question_or_a_category_without_a_cutoff(
    tmp_path, monkeypatch
):
    later = src("SWB-01", "later", "2026-10-01")
    assert _score(tmp_path, monkeypatch, later, law=False)[0].outcome == "scored"
    assert _score(tmp_path, monkeypatch, later, rule=None)[0].outcome == "scored"


def test_step3_names_the_methodology_level_and_checks_it(tmp_path, monkeypatch):
    cell, spec, _ = _score(tmp_path, monkeypatch, src("SWB-01", "ok", "2024-01-01"), band="10")
    assert cell.values[spec.column_for("comments")].startswith(
        "Methodology: 10. AI (high confidence)"
    )
    bad, spec, _ = _score(tmp_path, monkeypatch, src("SWB-01", "ok", "2024-01-01"), band="7.3")
    assert (
        'CONFIRM: BAND "7.3" is not a level of the methodology'
        in bad.values[spec.column_for("comments")]
    )


# -- methodology as the rule ---------------------------------------------------------------------
def test_every_methodology_reaches_the_step_2_model_word_for_word():
    bank, _ = load_bank(category_settings(get_settings(), "parastatal"))
    run = SimpleNamespace(city_name="Bengaluru", state_name="Karnataka", ulg="GBA")
    unit = Parastatal(id="BWSSB", name="Board", type="water_supply_entity")
    assert len(bank) == 69
    for q in bank.values():
        assert q.methodology.strip(), q.id
        message = base._question_block("t", {"question": q, "parastatal": unit, "run": run})
        assert q.methodology in message and "Detailed Methodology:" in message, q.id


def test_every_methodology_reaches_the_step_3_model_word_for_word():
    for path in reference_templates():
        ai = fill.AITemplate(path, path)
        for code, spec in ai.specs.items():
            if code in ("DPG 4",):
                continue
            unit = Parastatal(id="X", name="x", type="water_supply_entity")
            task = ts.TemplateTask(code.split()[0], code, "T", "S", "X", "l", unit)
            answer = StepTwoAnswer("Answered", "a", "X-01", "q", "", "")
            prompt = ts.build_prompt(task, spec, answer, [], "Parastatal")
            assert spec.details["Detailed Methodology"] in prompt, code


def test_the_template_and_the_bank_say_the_same_methodology_or_the_difference_is_known():
    bank, _ = load_bank(category_settings(get_settings(), "parastatal"))
    different = []
    for path in reference_templates():
        for code, spec in fill.AITemplate(path, path).specs.items():
            a, b = (
                " ".join(spec.details["Detailed Methodology"].split()),
                " ".join(bank[code].methodology.split()),
            )
            if a != b:
                different.append(code)
    assert different == []  # a difference would mean Step 2 and Step 3 follow different rules


def test_a_placeholder_methodology_is_left_for_a_person():
    bank, _ = load_bank(category_settings(get_settings(), "parastatal"))
    placeholders = [q.id for q in bank.values() if methodology.is_placeholder(q.methodology)]
    assert placeholders == ["DPG 4"]


def test_a_placeholder_question_is_not_answered_by_step_2(monkeypatch, services):
    bank, _ = load_bank(category_settings(get_settings(), "parastatal"))
    agent = base.build_section_agent("DPG", services)
    called = []
    monkeypatch.setattr(base, "call_json", lambda *a, **k: called.append(1))
    run = SimpleNamespace(
        city_name="Bengaluru", state_name="Karnataka", ulg="GBA", city="bengaluru"
    )
    unit = Parastatal(id="BWSSB", name="Board", type="water_supply_entity")
    src_ = src("BWSSB-01", "ok", "2024-01-01")
    result = agent.invoke(
        {"question": bank["DPG 4"], "parastatal": unit, "run": run, "citation_sources": [src_]}
    )
    answer = result["answers"][0]
    assert not called and answer.status == "Human Verification Required"
    assert answer.answer.startswith("NO RULE: The methodology for DPG 4 is only a placeholder note")
    assert "CONFIRM:" in answer.notes and answer.proposed_score is None


def test_the_band_check_reads_levels_and_parts():
    bank, _ = load_bank(category_settings(get_settings(), "parastatal"))

    def check(code, band):
        return methodology.band_problem(bank[code].methodology, bank[code].max_score, band)

    assert (
        check("UPD 1a", "2.5") is None and check("UPD 1a", "10 — ULG approval is mandatory") is None
    )
    assert "not a level" in check("UPD 1a", "7.3")
    assert (
        check("UPD 1a", "Full marks") is None
        and check("UPD 1a", "?") is None
        and check("UPD 1a", "") is None
    )
    assert check("DPG 5a", "Part A: yes; Part B: ?") is None
    assert "does not say which part" in check("DPG 5a", "0.5")


# -- the skill-versus-bank check -----------------------------------------------------------------
def test_the_help_files_name_only_questions_the_banks_have():
    assert skill_problems(get_settings()) == []


def test_a_help_file_naming_an_old_question_is_flagged(tmp_path):
    import dataclasses

    root = tmp_path / "agent_setup"
    (root / "categories").mkdir(parents=True)
    (root / "skills" / "sections").mkdir(parents=True)
    for name in ("parastatal.md", "ulg.md"):
        text = (get_settings().agent_setup_dir / "categories" / name).read_text()
        (root / "categories" / name).write_text(text)
    (root / "skills" / "sections" / "old.md").write_text(
        "Cross-cutting laws (DPG 6a, DPG 5j) apply to SC-5; UPD 1a is fine."
    )
    found = skill_problems(dataclasses.replace(get_settings(), agent_setup_dir=root))
    assert len(found) == 1
    where, message = found[0]
    assert where == "agent_setup/skills/sections/old.md"
    assert "DPG 5j" in message and "DPG 6a" in message
    assert "UPD 1a" not in message and "SC 5" not in message  # these exist in a bank


def test_the_bank_check_reports_a_placeholder_methodology_and_an_empty_level(services):
    from asics_agent.agents.initial_checks import build_initial_checks

    graph = build_initial_checks(services)
    result = graph.invoke({"city": "sample_city_a"})
    text = " ".join(i.message for i in result["issues"])
    assert "DPG 4" in text and "placeholder note" in text
    assert "UPD 6" in text and "Assessment Level is empty" in text
