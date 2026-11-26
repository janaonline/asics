"""Cost records for each run and the estimate shown before the next one (costs.py)."""

import dataclasses
from datetime import datetime

import pytest

from asics_agent import costs
from asics_agent.config import get_settings
from asics_agent.usage import METER

USAGE = {"input_tokens": 1_000_000, "output_tokens": 100_000}  # $2 + $1 on Sonnet 5.5


def test_a_run_records_only_its_own_usage(services):
    settings = services.settings
    METER.record("claude-sonnet-5-5", "earlier-run", USAGE)  # before this run: not counted
    meter = costs.RunMeter()
    METER.record("claude-sonnet-5-5", "answer-writer", USAGE)
    path = costs.record_run(
        settings,
        meter,
        step=2,
        label="Step 2 · Bengaluru",
        cities=["Bengaluru"],
        work=100,
        started=datetime.now(),
    )
    [record] = costs.history(settings)
    assert record.path == path and record.total == pytest.approx(3.0)
    assert record.per_unit == pytest.approx(0.03) and record.unit == "answer"
    assert list(record.by_agent) == ["answer-writer · claude-sonnet-5-5"]
    # Nothing paid (e.g. a practice run): nothing recorded.
    assert (
        costs.record_run(
            settings, costs.RunMeter(), step=1, label="x", cities=[], work=1, started=datetime.now()
        )
        is None
    )


def test_the_estimate_uses_the_last_run_else_a_starting_figure(services):
    settings = dataclasses.replace(services.settings, batch_answers=True)
    first = costs.estimate(settings, 2, 200)
    assert first.first_time and first.usd == pytest.approx(200 * costs.step2_default(settings) / 2)

    meter = costs.RunMeter()
    METER.record("claude-sonnet-5-5", "answer-writer", USAGE)  # $3 for 100 answers
    costs.record_run(
        settings, meter, step=2, label="Step 2", cities=["A"], work=100, started=datetime.now()
    )
    later = costs.estimate(settings, 2, 200)
    assert not later.first_time and later.usd == pytest.approx(6.0)
    assert "your last Step 2 run" in later.lines[0] and "200 answers" in later.lines[0]
    both = costs.combine([later, costs.estimate(settings, 3, 10)])
    assert both.usd == pytest.approx(6.0 + 10 * costs.DEFAULT_RATES[3]) and both.first_time


def test_planned_work_per_city(services):
    from asics_agent.categories import load_bank
    from asics_agent.cities import load_register

    settings = services.settings
    city = next(iter(load_register(settings.city_register)[0].values()))
    # No Sources workbook yet: the register's agencies plus typical ones not found yet.
    assert len(costs.city_units(settings, city)) == costs.DEFAULT_AGENCIES
    one_unit = dataclasses.replace(settings, unit="ulg")
    assert len(costs.city_units(one_unit, city)) == 1

    questions, _ = load_bank(settings)
    some = costs.planned_answers(settings, city, questions, codes=["UPD1a", "UPD 1b"])
    assert 0 < some <= 2 * costs.DEFAULT_AGENCIES
    assert costs.planned_answers(settings, city, questions) > some


# -- Part 1b: tokens, the first-run Step 2 figure, and the scan allowance ---------------------------------------
def test_two_and_a_half_characters_make_a_token():
    assert costs.CHARS_PER_TOKEN == 2.5
    assert costs.tokens_for(25_000) == 10_000


def test_the_first_run_step_2_figure_is_near_the_measured_cost_and_counts_the_tool_loop(services):
    settings = services.settings
    live = costs.step2_default(settings)
    assert live == pytest.approx(costs.DEFAULT_RATES[2], rel=0.25)  # measured: $0.076 an answer
    assert costs.step2_default(settings, turns=1) < live < costs.step2_default(settings, turns=6)
    # the first turn writes the cache (1.25x), later turns read it (a tenth): turn 2 costs little
    one = costs.step2_default(settings, turns=1)
    two = costs.step2_default(settings, turns=2)
    assert two - one == pytest.approx(
        (costs.PROMPT_TOKENS + costs.tokens_for(costs.EVIDENCE_FILL * settings.max_evidence_chars))
        * 0.20
        / 1e6,
    )


def test_an_unknown_model_falls_back_to_the_measured_figure(services):
    odd = dataclasses.replace(services.settings, model="some-other-model")
    assert costs.step2_default(odd) == costs.DEFAULT_RATES[2]


def test_the_step_1_estimate_carries_the_scan_allowance_outside_the_total(services):
    on = dataclasses.replace(
        services.settings, staged_fetch=True, scan_reading_budget_usd=5.0, batch_answers=False
    )
    one = costs.estimate(on, 1, 2)
    assert one.usd == pytest.approx(2 * costs.DEFAULT_RATES[1])  # the allowance is not in the total
    assert len(one.extra_lines) == 1 and "up to $5.00" in one.extra_lines[0]
    assert costs.estimate(on, 2, 2).extra_lines == []  # only Step 1 reads scans
    off = dataclasses.replace(on, scan_reading_budget_usd=0)
    assert costs.estimate(off, 1, 2).extra_lines == []
    assert costs.estimate(dataclasses.replace(on, staged_fetch=False), 1, 2).extra_lines == []


def test_combining_estimates_keeps_each_allowance_once(services):
    on = dataclasses.replace(services.settings, staged_fetch=True, scan_reading_budget_usd=3.0)
    both = costs.combine(
        [costs.estimate(on, 1, 2), costs.estimate(on, 1, 3), costs.estimate(on, 2, 5)]
    )
    assert len(both.extra_lines) == 1 and "up to $3.00" in both.extra_lines[0]
    assert costs.combine([costs.estimate(on, 2, 5)]).extra_lines == []


def test_the_parastatal_category_sets_the_scan_budget_to_five_dollars():
    from asics_agent.categories import category_settings

    parastatal = category_settings(get_settings(), "parastatal")
    assert parastatal.scan_reading_budget_usd == 5.0
    assert parastatal.scan_batch_wait_minutes == 20 and parastatal.fetch_cache_max_age_days == 30
    assert category_settings(get_settings(), "ulg").scan_reading_budget_usd == 3.0
