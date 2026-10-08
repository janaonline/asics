"""Step 3 (scoring) from the command line; the app's Step 3 · Score page does the same.

uv run python scripts/scoring.py check     # workbooks follow the conventions? cities match?
uv run python scripts/scoring.py prepare   # make each intern's copy from the assignments
uv run python scripts/scoring.py merge     # merge interns' work, calculate, update results
uv run python scripts/scoring.py ai --vertical PARASTATAL --question UPD1a --city Bengaluru
                                           # the AI scores cities Step 2 has answered, from
                                           # Step 2's answers and Citation Sheet only
                                           # (--practice: the practice cities, free)
"""

import argparse

from asics_agent.config import get_settings
from asics_agent.scoring import workflow


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("step", choices=["check", "prepare", "merge", "ai"])
    parser.add_argument("--vertical", action="append", help="only this vertical (merge, ai)")
    parser.add_argument("--question", action="append", help="only this question code (ai)")
    parser.add_argument("--city", action="append", help="only this city (ai)")
    parser.add_argument("--practice", action="store_true", help="scripted AI, no cost (ai)")
    args = parser.parse_args()
    settings = get_settings()
    if args.step == "merge":
        reports = [workflow.merge(settings, args.vertical)]
    elif args.step == "ai":
        if not args.vertical:
            parser.error("choose a vertical with --vertical, e.g. --vertical UPD")
        reports = [
            workflow.ai_score(settings, v.upper(), codes=args.question, cities=args.city,
                              practice=args.practice,
                              on_progress=lambda i, n: print(f"  {i}/{n}", end="\r"))
            for v in args.vertical
        ]
    else:
        reports = [getattr(workflow, args.step)(settings)]
    for report in reports:
        print(f"\n{report.title}")
        for line in report.done:
            print(f"  ✓ {line}")
        if report.problems:
            print(f"\nNeeds a look ({len(report.problems)}):")
            for line in report.problems:
                print(f"  • {line}")
        for path in report.files:
            print(f"  → {path}")


if __name__ == "__main__":
    main()
