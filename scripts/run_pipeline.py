"""Run Step 1 (find parastatals and sources) or Step 2 (answer questions) for one or more
cities from the city register.

Examples:
    # Free: validate inputs and show which questions apply, for every city
    uv run python scripts/run_pipeline.py --step sources --all-cities --checks-only

    # Step 1 for one city: find its parastatals, rate websites, build the Citation Sheet
    uv run python scripts/run_pipeline.py --step sources --city Bengaluru

    # (the research team reviews outputs/cities/Bengaluru/ASICS_Bengaluru_Sources.xlsx)

    # Step 2: answer questions using only that Citation Sheet
    uv run python scripts/run_pipeline.py --step answers --city Bengaluru --pillar DPG
"""

import argparse
import sys
import time

from asics_agent.cities import load_register, slugify
from asics_agent.reporting import answer_summary, headline, severity_label, team_issues
from asics_agent.run_options import RunOptions
from asics_agent.runner import BatchRun
from asics_agent.services import default_services
from asics_agent.workbook import city_outcome


def ask(prompt: str, options: dict[str, str]) -> str:
    """Numbered menu; re-asks until the answer is valid. Enter picks option 1."""
    keys = list(options)
    print()
    for n, key in enumerate(keys, 1):
        print(f"  {n}. {options[key]}")
    while True:
        answer = input(f"{prompt} [1-{len(keys)}, Enter = 1]: ").strip()
        if not answer:
            return keys[0]
        if answer.isdigit() and 1 <= int(answer) <= len(keys):
            return keys[int(answer) - 1]
        print(f"  Please type a number from 1 to {len(keys)}.")


def review_scope(payload: dict) -> dict:
    print(
        "\n" + "=" * 70 + "\nPARASTATALS FOUND: REVIEW BEFORE SOURCES ARE RESEARCHED\n" + "=" * 70
    )
    for p in payload["parastatals"]:
        pid, check = p["id"], p.get("website_check") or {}
        print(
            f"\n{p['name']} ({pid})  found by: {p['found_by']}, "
            f"{len(payload['applicability'].get(pid, []))} questions"
        )
        if p.get("why_included"):
            print(f"  Why:     {p['why_included']}")
        print(
            f"  Website: {p.get('official_website') or 'not confirmed'}"
            + (f"  [{check.get('score')}/100, {check.get('band')}]" if check else "")
        )
        print(f"  Act:     {p.get('governing_act') or 'not found'}")
        print(f"  Status:  {p.get('current_status') or 'unknown'}")
        for issue in payload["issues"]:
            if issue.get("audience") == "team" and issue.get("ref") == pid:
                print(f"  ! {issue['message']}")
    choice = ask(
        "What next?",
        {
            "approve": "Continue with all of these parastatals",
            "edit": "Continue with only some of them",
            "stop": "Stop here (no research)",
        },
    )
    if choice != "edit":
        return {"action": choice}
    ids = list(payload["applicability"])
    while True:
        typed = input(f"Which ones? Type IDs separated by commas ({', '.join(ids)}): ")
        keep = [p.strip().upper() for p in typed.split(",") if p.strip().upper() in ids]
        if keep:
            return {"action": "edit", "parastatals": keep}
        print("  None of those matched. Please try again.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument(
        "--city",
        action="append",
        help="City name from the city register (repeat for several cities)",
    )
    which.add_argument(
        "--all-cities",
        action="store_true",
        help="Every city marked to include in the city register",
    )
    parser.add_argument(
        "--step",
        choices=["sources", "answers"],
        required=True,
        help="sources = Step 1: find parastatals and build the Citation Sheet; "
        "answers = Step 2: answer questions from the reviewed Citation Sheet",
    )
    parser.add_argument(
        "--base-workbook",
        help="Step 1: previous-phase workbook whose Citation Sheet to re-check; "
        "Step 2: workbook to write the answers into (one city only)",
    )
    parser.add_argument("--parastatal", action="append", help="Limit to parastatal ID(s)")
    parser.add_argument("--pillar", action="append", help="Limit to pillar code(s): UPD, DPG, SC")
    parser.add_argument("--questions", help='Comma-separated IDs, e.g. "UPD 1, DPG 5a"')
    parser.add_argument("--auto-approve", action="store_true", help="Skip the review pause")
    parser.add_argument(
        "--checks-only",
        action="store_true",
        help="Run initial checks and applicability only (no web research)",
    )
    parser.add_argument(
        "--llm-bank-review",
        action="store_true",
        help="Also ask Claude to review the question bank for problems",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Also show technical messages for developers"
    )
    tuning = parser.add_argument_group("run options (override agent_setup/agents and .env)")
    tuning.add_argument("--model", help="Claude model for agents that don't name their own")
    tuning.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"])
    tuning.add_argument("--web-searches", type=int, help="web searches / fetches per call")
    tuning.add_argument("--max-tool-calls", type=int, help="tool calls per agent call")
    args = parser.parse_args()

    services = default_services()
    register, register_issues = load_register(services.settings.city_register)
    if args.all_cities:
        cities = {slug: c.name for slug, c in register.items()}
    else:
        cities = {
            slugify(name): register[slugify(name)].name if slugify(name) in register else name
            for name in args.city
        }
    if args.base_workbook and len(cities) > 1:
        sys.exit("--base-workbook can only be used with a single city.")

    parastatals = None
    if args.parastatal:
        wanted = {p.upper() for p in args.parastatal}
        parastatals = {}
        for slug in list(cities):
            ids = [p.id for p in register[slug].parastatals] if slug in register else []
            if ids and not wanted & set(ids):
                del cities[slug]  # none of the requested parastatals are in this city
            else:
                parastatals[slug] = sorted(wanted & set(ids)) or None
    if not cities:
        sys.exit("No cities to run. Check the names against the city register.")

    inputs = {
        "base_workbook": args.base_workbook,
        "only_pillars": args.pillar,
        "only_questions": [q.strip() for q in args.questions.split(",")]
        if args.questions
        else None,
        "auto_approve": args.auto_approve,
        "skip_research": args.checks_only,
        "llm_bank_review": args.llm_bank_review,
    }
    batch = BatchRun(
        services,
        cities,
        inputs,
        parastatals,
        label=f"{len(cities)} cities" if len(cities) > 1 else next(iter(cities.values())),
        step=args.step,
        options=RunOptions(
            model=args.model,
            effort=args.effort,
            web_search_max_uses=args.web_searches,
            max_tool_calls=args.max_tool_calls,
        ),
    )
    batch.start()
    printed: dict[str, int] = {}

    def follow(until: set[str]) -> None:
        while batch.status not in until:
            for slug, run in batch.runs.items():
                for line in run.log[printed.get(slug, 0) :]:
                    print(f"[{run.label}] {line}")
                printed[slug] = len(run.log)
            time.sleep(0.5)

    follow({"waiting_for_review", "finished", "failed"})
    if batch.status == "waiting_for_review":
        decisions = {}
        for slug, review in batch.reviews.items():
            print(f"\n##### {batch.runs[slug].label} #####")
            decisions[slug] = review_scope(review)
        batch.submit_review(decisions)
        follow({"finished", "failed"})

    for run in batch.runs.values():
        print("\n" + "=" * 70 + f"\n{run.label}: {city_outcome(run)}")
        print(headline(run.answers, run.issues))
        for status, count, meaning in answer_summary(run.answers):
            print(f"  {count:>4}  {status}: {meaning}")
        for issue in team_issues(run.issues):
            print(f"  [{severity_label(issue.severity)}] {issue.message}")
        if args.verbose:
            for issue in run.issues:
                print(
                    f"  {issue.severity:<7} {issue.phase:<18} {issue.ref or '':<20} {issue.message}"
                )
    if batch.error:
        print(f"\nProblem: {batch.error}")
    print()
    for run in batch.runs.values():
        if workbook := (run.result or {}).get("output_workbook"):
            print(f"{run.label}: {workbook}")
    if batch.summary_path and len(batch.runs) > 1:
        print(f"Index of all cities: {batch.summary_path}")


if __name__ == "__main__":
    main()
