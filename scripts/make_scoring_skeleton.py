"""Generate a draft scoring workbook for a vertical from its question bank.

    uv run python scripts/make_scoring_skeleton.py                       # Parastatal
    uv run python scripts/make_scoring_skeleton.py --vertical upd
    uv run python scripts/make_scoring_skeleton.py --methodology other.xlsx   # another sheet

By default the questions come from the vertical's own question bank (the one Steps 1 and 2
use), so Step 3 scores exactly the questions Step 2 answered. Rows come from the city register
and each city's Sources workbook. The draft goes to scoring/2027/templates/ and lists what the
experts should check on its first sheet.
"""

import argparse
from pathlib import Path

from asics_agent.config import get_settings
from asics_agent.question_bank import load_question_bank
from asics_agent.scoring.skeleton import build_skeleton, gather_units
from asics_agent.verticals import load_bank, settings_for


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--vertical", default="parastatal")
    parser.add_argument("--methodology", type=Path, help="a different question/methodology file")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    settings = settings_for(get_settings(), args.vertical)
    out = args.out or settings.scoring_workbook or settings.scoring_dir / "templates" / (
        f"ASICS_2027_{settings.vertical_title}_Scoring_Workbook_DRAFT.xlsx"
    )
    if args.methodology:
        questions, issues = load_question_bank(args.methodology)
        print("Note: Step 3 only scores questions whose text matches the question bank Steps 1 "
              "and 2 used; use the same file for both.")
    else:
        questions, issues = load_bank(settings)
    units, notes = gather_units(settings)
    problems = build_skeleton(questions, units, out, settings.vertical_code, issues)
    print(f"Wrote {out}")
    print(f"{len(units)} rows (city – agency); {len(problems)} points for the experts to check.")
    for line in notes + problems:
        print(f"  • {line}")


if __name__ == "__main__":
    main()
