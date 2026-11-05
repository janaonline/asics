"""The scores a typed-points question may take, read from the templates (not written by hand)."""

import csv
import warnings
from pathlib import Path

import pytest
from openpyxl import load_workbook

from asics_agent.scoring.score_levels import score_levels
from asics_agent.scoring.template_import import read_structures
from tests.refdata import ROOT, reference_templates


def typed_points():
    out = {}
    for path in reference_templates():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            specs = read_structures(load_workbook(path))
        for code, s in specs.items():
            if not (s.score_is_formula or s.inputs) and s.max_score is not None:
                out[code] = (
                    s,
                    score_levels(s.details.get("Detailed Methodology", ""), s.max_score),
                )
    return out


def test_every_typed_points_question_is_classified():
    rules = typed_points()
    assert len(rules) == 42  # UPD 14, SC 12, DPG 16
    kinds = {k: sorted(c for c, (_, r) in rules.items() if r.kind == k) for k in ("levels", "free")}
    assert len(kinds["levels"]) == 29 and len(kinds["free"]) == 13
    assert kinds["free"] == sorted(
        ["DPG 5a", "DPG 5b", "DPG 5c", "DPG 5d", "DPG 5e", "DPG 5f", "DPG 5g", "DPG 5h"]
        + ["DPG 7c", "UPD 3a", "UPD 3b", "UPD 4a", "UPD 4b"]
    )


@pytest.mark.parametrize(
    "code, allowed",
    [
        ("UPD 1a", (5, 2.5, 0)),  # methodology 10 / 2.5 / 0, the cell takes 0 to 5
        ("UPD 1b", (5, 0)),
        ("UPD 2a", (2.5, 1.25, 0)),
        ("SC 4a", (5, 2.5, 0)),
        ("SC 9", (10, 0)),
        ("DPG 6", (10, 0)),  # one "Part A" only: a plain 10 / 0
        ("DPG 8a", (5, 2.5, 1.25, 0)),
        ("DPG 7b", (3.33, 0)),
    ],
)
def test_the_allowed_levels_of_fixed_level_questions(code, allowed):
    spec, rule = typed_points()[code]
    assert rule.kind == "levels" and rule.levels == allowed
    assert rule.allows(allowed[0]) and not rule.allows(allowed[0] + 0.37)


def test_why_the_free_ones_are_free():
    rules = typed_points()
    assert "parts are added up" in rules["DPG 5a"][1].basis
    assert "below the Max Score" in rules["DPG 7c"][1].basis
    assert "parts are added up" in rules["UPD 3a"][1].basis
    free = rules["UPD 3a"][1]
    assert free.allows(3.75) and free.allows(0.1)  # no level check; the range check is elsewhere


def test_the_rule_on_made_up_methodology_text():
    assert score_levels("Score 10 if yes.\nScore 0 if no.", 10).levels == (10, 0)
    assert score_levels("Score 10, if yes.\nScore 0, if no.", 10).levels == (10, 0)  # comma
    assert score_levels("Score 5 if a.\nScore 2.5 if b.", 5).kind == "free"  # no 0 level
    assert score_levels("nothing to read", 5).kind == "free"
    assert score_levels("10 — a\n7.5 — b\n0 — c", 5).kind == "free"  # two levels above the cell
    assert score_levels("10 — a\n2.5 — b\n0 — c", 5).levels == (5, 2.5, 0)


def test_the_coverage_csv_has_the_score_levels_column():
    rows = list(csv.DictReader(Path(ROOT / "docs" / "AI_COVERAGE.csv").open(encoding="utf-8")))
    by = {r["question_code"]: r for r in rows}
    assert len(rows) == 52 and "score_levels" in rows[0]
    rules = typed_points()
    for code, (_, rule) in rules.items():
        assert by[code]["score_levels"] == rule.describe(), code
    assert by["UPD 1a"]["score_levels"].startswith("5 | 2.5 | 0 (methodology lists 10 | 2.5 | 0")
    assert by["DPG 4"]["score_levels"].startswith("not scored")
    assert by["SC 3"]["score_levels"] == ""  # calculated by the template, not typed
