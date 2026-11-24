"""scripts/build_eval_set.py: reading the links people cited, and the committed eval set. No network."""

import importlib.util
from collections import Counter

import pytest
import yaml

from asics_agent.config import PROJECT_ROOT


@pytest.fixture(scope="module")
def build():
    spec = importlib.util.spec_from_file_location(
        "build_eval_set", PROJECT_ROOT / "scripts" / "build_eval_set.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_link_ending_in_a_bracket_keeps_it(build):
    cell = "https://dpal.example.in/storage/acts/12%20of%201976%20(E).pdf"
    assert build.extract_urls(cell) == [cell]


def test_a_bracket_that_only_wraps_the_link_is_dropped(build):
    assert build.extract_urls("(see https://x.org/a) and more") == ["https://x.org/a"]
    assert build.extract_urls("https://x.org/a).") == ["https://x.org/a"]


def test_a_balanced_bracket_inside_the_link_and_at_its_end_stays(build):
    assert build.extract_urls("https://b.in/#googtrans(en|en)") == [
        "https://b.in/#googtrans(en|en)"
    ]


def test_punctuation_after_a_link_is_not_part_of_it_and_repeats_are_dropped(build):
    cell = "https://x.org/a, https://x.org/b; https://x.org/a. See https://x.org/c."
    assert build.extract_urls(cell) == ["https://x.org/a", "https://x.org/b", "https://x.org/c"]
    assert build.extract_urls("") == [] and build.extract_urls(None) == []


def test_the_committed_eval_set_keeps_its_bracketed_links_and_a_balanced_split():
    data = yaml.safe_load((PROJECT_ROOT / "data" / "eval_set.yaml").read_text())
    rows = data["rows"]
    assert len(rows) == 201 and data["seed"] == "asics-eval-2026-11"
    links = {u for r in rows for u in r["human_sources"]}
    assert any(u.endswith("(E).pdf") for u in links)
    assert not any(u.count("(") > u.count(")") for u in links)  # no link cut inside its brackets
    split = Counter(r["split"] for r in rows)
    assert split == {"dev": 102, "test": 99}
