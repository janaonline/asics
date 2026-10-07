import time

from asics_agent.runner import PipelineRun

INPUTS = {"city": "sample_city_a", "only_questions": ["UPD 1"]}


def wait_for(run, *statuses, timeout=30):
    deadline = time.time() + timeout
    while run.status not in statuses and time.time() < deadline:
        time.sleep(0.05)
    return run.status


def test_step1_pauses_for_review_then_step2_answers(services):
    run = PipelineRun(services, INPUTS, "test", step="sources").start()
    assert wait_for(run, "waiting_for_review", "failed") == "waiting_for_review"
    assert {p["id"] for p in run.review["parastatals"]} == {"SWB", "STC"}

    run.submit_review({"action": "edit", "parastatals": ["SWB"]})
    assert wait_for(run, "finished", "failed") == "finished", run.error
    assert any("Found 2 parastatal" in line for line in run.log)
    stc = next(p for p in run.result["parastatals"] if p.id == "STC")
    assert not stc.include  # unticked at review, kept in the Sources workbook as No

    answers = PipelineRun(services, INPUTS, "test", step="answers").start()
    assert wait_for(answers, "finished", "failed") == "finished", answers.error
    assert answers.answers_done == answers.answers_total == 2
    assert {a.parastatal_id for a in answers.answers} == {"SWB"}


def test_progress_is_reported_live_and_after_the_review(services):
    run = PipelineRun(services, INPUTS, "test", step="sources").start()
    assert wait_for(run, "waiting_for_review", "failed") == "waiting_for_review"
    run.submit_review({"action": "approve"})
    assert wait_for(run, "finished", "failed") == "finished", run.error

    assert any("Review done. Now building the Citation Sheet for 2" in line for line in run.log)
    # Live messages from inside the agents, per parastatal.
    assert {"SWB", "STC"} <= set(run.activity)
    assert any("Searching the web for sources" in line for line in run.log)
    assert any("SWB: Done" in line for line in run.log)
