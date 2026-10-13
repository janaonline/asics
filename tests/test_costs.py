"""Cost records for each run and the estimate shown before the next one (costs.py)."""

import dataclasses
from datetime import datetime

import pytest

from asics_agent import costs
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
    assert first.first_time and first.usd == pytest.approx(200 * costs.DEFAULT_RATES[2] / 2)

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
    from asics_agent.cities import load_register
    from asics_agent.verticals import load_bank

    settings = services.settings
    city = next(iter(load_register(settings.city_register)[0].values()))
    # No Sources workbook yet: the register's agencies plus typical ones not found yet.
    assert len(costs.city_units(settings, city)) == costs.DEFAULT_AGENCIES
    one_unit = dataclasses.replace(settings, unit="city_government")
    assert len(costs.city_units(one_unit, city)) == 1

    questions, _ = load_bank(settings)
    some = costs.planned_answers(settings, city, questions, codes=["UPD1a", "UPD 1b"])
    assert 0 < some <= 2 * costs.DEFAULT_AGENCIES
    assert costs.planned_answers(settings, city, questions) > some
