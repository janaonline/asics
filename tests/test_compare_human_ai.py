from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

from asics_agent import bank_builder as bb
from asics_agent.question_bank import load_question_bank
from asics_agent.scoring import compare as cmp
from asics_agent.scoring.template_import import (
    HumanRow,
    ImportReport,
    QuestionMeta,
    TemplateRead,
)
from tests.refdata import reference_workbook

CITY = "Sampleton"


@pytest.fixture(scope="module")
def bank(tmp_path_factory):
    path = bb.write_bank(
        bb.read_source(reference_workbook()), tmp_path_factory.mktemp("b") / "b.xlsx"
    )
    return load_question_bank(path)[0]


def human(code, who, score, **kw):
    return HumanRow(
        city=CITY,
        parastatal=who,
        code=code,
        raw_code=code,
        score=score,
        scorer="Asha",
        file="filled.xlsx",
        sheet=code,
        row=14,
        **kw,
    )


def template(rows, texts=None):
    t = TemplateRead(Path("filled.xlsx"), rows=rows, report=ImportReport("filled.xlsx"))
    for code, text in (texts or {}).items():
        t.questions[code] = QuestionMeta(code=code, sheet=code, text=text)
    return t


def step2_file(path, rows):
    wb = Workbook()
    ws = wb.active
    ws.title = f"Parastatal Scoring - {CITY}"
    ws.append(
        [
            "Parastatal",
            "Question ID",
            "Question",
            "Status",
            "Answer",
            "Proposed Score",
            "Class",
            "Confidence",
            "Rubric Band",
            "Citation URL",
            "Where to Find It",
            "Notes",
            "Citation ID",
        ]
    )
    for r in rows:
        ws.append(r)
    wb.save(path)
    return path


def step3_file(path, rows):
    wb = Workbook()
    ws = wb.active
    ws.title = "Scores (start here)"
    ws.append(["Question", "Row", "Question text", "AI score", "Link", "Status"])
    for r in rows:
        ws.append(r)
    wb.save(path)
    return path


def build(tmp_path, bank, human_rows, s2_rows, s3_rows, extra_info=None, texts=None):
    units = {
        "BWSSB": cmp.Unit("BWSSB", "Water Board", "water_supply_entity"),
        "BMTC": cmp.Unit("BMTC", "Bus Corp", "public_bus_transport_operator"),
    }
    ids = {"bwssb": "BWSSB", "water board": "BWSSB", "bmtc": "BMTC", "bus corp": "BMTC"}
    info = cmp.CityInputs(
        city=CITY,
        aliases=[],
        units=units,
        bank=bank,
        raw_to_code={q.raw_id: q.id for q in bank.values()},
        step2=cmp.read_step2(step2_file(tmp_path / "s2.xlsx", s2_rows), ids),
        step3=cmp.read_step3(step3_file(tmp_path / "s3.xlsx", s3_rows), None, "PARASTATAL"),
        bank_version="test",
        **(extra_info or {}),
    )
    return cmp.compare_city(info, [template(human_rows, texts)])


def by_key(comp):
    return {(r.unit, r.code): r for r in comp.rows}


def test_every_status_and_agreement(tmp_path, bank):
    codes = [c for c, q in bank.items() if q.tag == "SQ" and q.max_score][:4]
    a, b, c, d = codes
    retired = {"DPG 5i": bank[a].model_copy(update={"id": "DPG 5i", "raw_id": "DPG 5i"})}
    comp = build(
        tmp_path,
        bank,
        human_rows=[
            human(a, "BWSSB", 5.0, source_link="http://www.Example.gov.in/act/#s1"),
            human(a, "BMTC", 2.5),
            human(b, "BWSSB", 3.0),
            human(d, "BWSSB", None),
            human("DPG 5i", "BWSSB", 1.0),
            human("UPD 88", "BWSSB", 1.0),
            human(c, "ZZZ", 2.0),
        ],
        s2_rows=[
            [
                "Water Board",
                bank[a].raw_id,
                bank[a].text,
                "Answered",
                "x",
                5,
                "A1",
                "High",
                "5",
                "https://example.gov.in/act",
                "Page 3",
            ],
            [
                "Water Board",
                bank[d].raw_id,
                bank[d].text,
                "Insufficient Evidence",
                "",
                None,
                "Needs review",
                "",
                "",
                "",
                "",
            ],
        ],
        s3_rows=[
            [
                a.replace(" ", ""),
                f"{CITY} – BWSSB",
                "",
                5,
                "https://example.gov.in/act",
                "Scored by AI",
            ],
            [a.replace(" ", ""), f"{CITY} – BMTC", "", 5, "", "Scored by AI"],
            [c.replace(" ", ""), f"{CITY} – BMTC", "", 4, "", "Scored by AI"],
        ],
        extra_info={"retired": retired},
    )
    rows = by_key(comp)
    both_ok, both_off = rows[("BWSSB", a)], rows[("BMTC", a)]
    assert (both_ok.status, both_ok.agrees, both_ok.difference) == ("both", "Yes", 0.0)
    assert (both_off.status, both_off.agrees, both_off.difference) == ("both", "No", 2.5)
    assert rows[("BWSSB", b)].status == "only human"
    assert rows[("BMTC", c)].status == "only AI"
    assert rows[("BWSSB", d)].status == "neither"
    assert rows[("BWSSB", "DPG 5i")].status == "retired question"
    assert rows[("BWSSB", "UPD 88")].status == "question not in this bank version"
    assert both_ok.same_source == "Yes"  # the same page, written two ways
    assert (both_ok.ai_class, both_ok.ai_confidence) == ("A1", "High")
    assert both_ok.human_source and both_ok.ai_citation_url and both_ok.ai_where_to_find == "Page 3"
    # an unknown parastatal goes to the review list and is still shown, never created or dropped
    assert any("ZZZ" in why for _, why in comp.review)
    assert ("ZZZ", c) in rows and "not matched" in "; ".join(rows[("ZZZ", c)].notes)


def test_a_reused_code_is_not_compared(tmp_path, bank):
    code = next(c for c, q in bank.items() if q.tag == "SQ" and q.max_score)
    comp = build(
        tmp_path,
        bank,
        human_rows=[human(code, "BWSSB", 2.0)],
        s2_rows=[
            [
                "Water Board",
                bank[code].raw_id,
                "Is there a completely unrelated old question here",
                "Answered",
                "x",
                2,
                "A1",
                "High",
                "",
                "",
                "",
            ]
        ],
        s3_rows=[[code.replace(" ", ""), f"{CITY} – BWSSB", "", 2, "", ""]],
    )
    row = by_key(comp)[("BWSSB", code)]
    assert row.status == "question changed" and row.agrees == "" and row.difference is None
    assert "different question" in "; ".join(row.notes)


def test_an_old_raw_id_is_read_through_the_earlier_bank(tmp_path, bank):
    code = next(c for c, q in bank.items() if q.tag == "SQ" and q.max_score)
    comp = build(
        tmp_path,
        bank,
        human_rows=[],
        s2_rows=[
            [
                "Water Board",
                "OLD d",
                "An old different question",
                "Answered",
                "x",
                1,
                "A1",
                "",
                "",
                "",
                "",
            ]
        ],
        s3_rows=[],
        extra_info={"old_raw_to_code": {"OLD d": code}},
    )
    assert by_key(comp)[("BWSSB", code)].status == "question changed"


def test_the_summary_hides_percentages_below_the_minimum(tmp_path, bank):
    a = next(c for c, q in bank.items() if q.tag == "SQ" and q.max_score)
    comp = build(
        tmp_path,
        bank,
        human_rows=[human(a, "BWSSB", 5.0)],
        s2_rows=[],
        s3_rows=[[a.replace(" ", ""), f"{CITY} – BWSSB", "", 5, "", ""]],
    )
    for minimum, shown in ((20, False), (1, True)):
        path = cmp.write_comparison(comp, tmp_path / f"c{minimum}.xlsx", min_rows=minimum)
        wb = load_workbook(path)
        assert wb.sheetnames == ["Summary", "AI zeros", "Compare", "Review list"]
        cells = [
            str(c.value) for row in wb["Summary"].iter_rows() for c in row if c.value is not None
        ]
        assert ("100%" in cells) is shown
        assert (any("fewer than 20" in c for c in cells)) is (not shown)
    header = [c.value for c in wb["Compare"][1]]
    for name in (
        "Human score",
        "AI score",
        "Agrees? (exact)",
        "Same source?",
        "AI class",
        "Status",
    ):
        assert name in header


def test_urls_bands_and_inputs():
    assert cmp.normalise_url("HTTP://www.Example.gov.in/a/?utm_source=x#top") == "example.gov.in/a"
    assert cmp.normalise_url("") == ""
    scale = cmp.scale_of("10 — full\n5 — partial\n0 — none")
    assert scale == [0.0, 5.0, 10.0]
    assert cmp.band_of(5.0, scale) == "5" and cmp.band_of(6.0, scale) == "between bands"
    assert cmp.band_of(3.0, []) == ""
    assert (
        cmp._inputs_overlap({"Own revenue": 5, "x": 1}, {"own revenue": 5}) == "1 same, 0 different"
    )
    assert cmp._inputs_overlap({"a": 1}, {"b": 1}) == "no inputs with the same name"


def _rows(*statuses_and_agreement):
    return [
        cmp.CompareRow(
            city="Testville",
            unit="BWSSB",
            unit_type="water_supply_entity",
            code=f"UPD {i}",
            section="UPD",
            status=status,
            agrees=agrees,
        )
        for i, (status, agrees) in enumerate(statuses_and_agreement, start=1)
    ]


def test_coverage_and_agreement_are_two_separate_numbers():
    # 4 rows a person scored; the AI scored 2 of them, and one of those 2 agrees. Plus a row only
    # the AI scored and one neither scored: neither counts towards coverage.
    rows = _rows(
        ("both", "Yes"),
        ("both", "No"),
        ("only human", ""),
        ("only human", ""),
        ("only AI", ""),
        ("neither", ""),
    )
    assert cmp.coverage(rows) == (4, 2)
    assert cmp.coverage_text(rows) == "2 of 4 (50%)"
    assert cmp.agreement_text(rows, min_rows=20) == (
        "1 of 2 agree (a percentage shows from 20 compared rows)"
    )
    assert cmp.agreement_text(rows, min_rows=2) == "1 of 2 (50%)"
    assert cmp.coverage_text([]) == "no human-scored rows"
    assert cmp.agreement_text(_rows(("only human", ""))) == "no row is scored by both"


def test_the_summary_shows_coverage_and_agreement_on_separate_lines(tmp_path, bank):
    a = next(c for c, q in bank.items() if q.tag == "SQ" and q.max_score)
    comp = build(
        tmp_path,
        bank,
        human_rows=[human(a, "BWSSB", 5.0)],
        s2_rows=[],
        s3_rows=[[a.replace(" ", ""), f"{CITY} – BWSSB", "", 5, "", ""]],
    )
    path = cmp.write_comparison(comp, tmp_path / "c.xlsx", min_rows=1)
    rows = {
        row[0].value: row[1].value
        for row in load_workbook(path)["Summary"].iter_rows()
        if row[0].value
    }
    assert rows["Coverage (AI scored of human scored)"] == "1 of 1 (100%)"
    assert rows["Agreement when both scored"] == "1 of 1 (100%)"
    sections = [
        r
        for r in load_workbook(path)["Summary"].iter_rows(values_only=True)
        if r[0] == "By section"
    ]
    assert sections[0][1:4] == (
        "Human scored",
        "Coverage (AI scored of them)",
        "Compared (both scored)",
    )


def test_a_human_zero_the_ai_left_blank_for_a_missing_source_is_a_candidate_zero(tmp_path, bank):
    a, b, c = [c for c, q in bank.items() if q.tag == "SQ" and q.max_score][:3]

    def blank(code, note):
        return [
            "Water Board",
            bank[code].raw_id,
            bank[code].text,
            "Insufficient Evidence",
            "",
            None,
            "Needs review",
            "",
            "",
            "",
            "",
            note,
        ]

    comp = build(
        tmp_path,
        bank,
        human_rows=[human(a, "BWSSB", 0.0), human(b, "BWSSB", 0.0), human(c, "BWSSB", 5.0)],
        s2_rows=[
            blank(
                a,
                "Zero not allowed: Missing: parent Act [ACT]; Rules made under the Act [RULES]. More.",
            ),
            blank(b, "Zero not allowed: Blocked: relevant text found in BWSSB-02."),
            blank(c, "Zero not allowed: Missing: parent Act [ACT]."),
        ],
        s3_rows=[],
    )
    rows = by_key(comp)
    first = rows[("BWSSB", a)]
    assert first.status == "only human"
    assert first.candidate_zero == (
        "candidate 0: missing parent Act [ACT]; Rules made under the Act [RULES]"
    )
    assert first.candidate_zero in first.notes
    assert rows[("BWSSB", b)].candidate_zero == ""  # blocked by the scan: not a missing source
    assert rows[("BWSSB", c)].candidate_zero == ""  # the human score was not 0

    path = cmp.write_comparison(comp, tmp_path / "c.xlsx", min_rows=1)
    summary = {
        row[0].value.strip(): row[1].value
        for row in load_workbook(path)["Summary"].iter_rows()
        if row[0].value
    }
    assert summary["Candidate 0 (human 0, AI blank, a required source is missing)"] == 1
    assert summary["candidate 0: missing parent Act [ACT]; Rules made under the Act [RULES]"] == 1
    header = [c.value for c in load_workbook(path)["Compare"][1]]
    assert "Candidate 0 (AI blank: a required source is missing)" in header


def test_the_ai_zeros_sheet_lists_every_zero_with_its_route_documents_and_scan(tmp_path, bank):
    from asics_agent.models import Parastatal, Source

    water = Parastatal(
        id="BWSSB",
        name="Water Board",
        type="water_supply_entity",
        governing_act="The Water Act, 1970 (State Act 3 of 1970)",
    )
    page = tmp_path / "act.txt"
    page.write_text("Section 1. Short title.\n\nSection 2. Definitions.")
    act = Source(
        citation_id="BWSSB-01",
        parastatal_id="BWSSB",
        title="The Water Act",
        url="https://x.gov.in/act",
        useful_for="[ACT] the Act",
        verification_status="Verified",
        use_for_answers=True,
        content_path=str(page),
    )
    a, b = "UPD 1a", "UPD 2a"
    comp = build(
        tmp_path,
        bank,
        human_rows=[human(a, "BWSSB", 5.0), human(b, "BWSSB", 0.0)],
        s2_rows=[
            [
                "Water Board",
                bank[a].raw_id,
                bank[a].text,
                "Answered — Verified Source",
                "x",
                0,
                "A2",
                "Medium",
                "0",
                "",
                "",
                "ZERO-CHECKED: Checked: BWSSB-01.",
            ]
        ],
        s3_rows=[
            [a.replace(" ", ""), f"{CITY} – BWSSB", "", 0, "", ""],
            [b.replace(" ", ""), f"{CITY} – BWSSB", "", 0, "", ""],
        ],
        extra_info={"parastatals": {"BWSSB": water}, "citations": [act]},
    )
    rows = by_key(comp)
    assert rows[("BWSSB", a)].zero_route == "Step 2 ZERO-CHECKED"
    assert rows[("BWSSB", b)].zero_route == "Step 3 typed"
    assert rows[("BWSSB", a)].zero_gate == "required source missing"
    assert "parent Act [ACT]: present (BWSSB-01)" in rows[("BWSSB", a)].zero_documents
    assert "Rules made under the Act [RULES]: MISSING" in rows[("BWSSB", a)].zero_documents
    assert "not run" in rows[("BWSSB", a)].zero_scan

    path = cmp.write_comparison(comp, tmp_path / "z.xlsx", min_rows=1)
    wb = load_workbook(path)
    sheet = list(wb["AI zeros"].iter_rows(values_only=True))
    header = list(sheet[0])
    assert header[:2] == ["City", "Parastatal"] and "Route" in header and "Scan result" in header
    assert len(sheet) == 3  # header + the two zeros
    first = dict(zip(header, sheet[1], strict=True))
    assert first["Question"] == a  # the false zero comes first
    assert first["Agree?"] == "No: false zero"
    assert first["False zero? (AI 0, human above 0)"] == "Yes"
    second = dict(zip(header, sheet[2], strict=True))
    assert second["Agree?"] == "Yes" and second["Route"] == "Step 3 typed"
    summary = {
        row[0].value.strip(): row[1].value for row in wb["Summary"].iter_rows() if row[0].value
    }
    assert summary["AI zeros (rows where the AI wrote a 0)"] == 2
    assert summary["False zeros (AI 0, human above 0)"] == 1
    assert summary["AI 0 and human 0"] == 1
    assert summary["Step 2 ZERO-CHECKED"] == 1 and summary["Step 3 typed"] == 1


def test_a_comparison_without_zeros_still_has_the_sheet_and_a_zero_count(tmp_path, bank):
    a = next(c for c, q in bank.items() if q.tag == "SQ" and q.max_score)
    comp = build(
        tmp_path,
        bank,
        human_rows=[human(a, "BWSSB", 5.0)],
        s2_rows=[],
        s3_rows=[[a.replace(" ", ""), f"{CITY} – BWSSB", "", 5, "", ""]],
    )
    wb = load_workbook(cmp.write_comparison(comp, tmp_path / "n.xlsx", min_rows=1))
    assert len(list(wb["AI zeros"].iter_rows())) == 1  # only the header
    summary = {r[0].value.strip(): r[1].value for r in wb["Summary"].iter_rows() if r[0].value}
    assert summary["AI zeros (rows where the AI wrote a 0)"] == 0
    assert summary["False zeros (AI 0, human above 0)"] == 0


def test_a_roll_up_zero_is_labelled_as_a_sum_of_its_parts(tmp_path, bank):
    roll = next(c for c, q in bank.items() if q.is_rollup and q.max_score)
    comp = build(
        tmp_path,
        bank,
        human_rows=[human(roll, "BWSSB", 3.0)],
        s2_rows=[],
        s3_rows=[[roll.replace(" ", ""), f"{CITY} – BWSSB", "", 0, "", ""]],
    )
    row = by_key(comp)[("BWSSB", roll)]
    assert row.ai_score == 0 and row.zero_gate.startswith("roll-up question")
