"""Compare people's scores (filled scoring templates) with the AI's, one workbook per city.

    uv run python scripts/compare_human_ai.py Parastatal_UPD_Template.xlsx Parastatal_SC_Template.xlsx
    uv run python scripts/compare_human_ai.py FILLED.xlsx --city Bengaluru --min-rows 10
    uv run python scripts/compare_human_ai.py FILLED.xlsx --category ulg

With no file named, a category scored in the team's templates uses the merged people's workbooks
(scoring/2027/merged/, built from the files uploaded in the app: Step 3 > People's scoring).
The filled templates are read by name (sheet = question code, columns by header text), so
renamed or reordered columns and extra columns are fine. The AI's side is the city's latest
Step 2 answers workbook and the Step 3 AI scoring workbook, found as the app finds them (or give
--answers / --ai-workbook / --ai-runs). Each city's workbook goes to scoring/2027/compare/ with
a Compare sheet (one row per unit and question), a Summary sheet and a Review list sheet.
Unknown parastatals or questions are listed for review, never created or dropped.
"""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from asics_agent.categories import category_settings  # noqa: E402
from asics_agent.cities import load_register  # noqa: E402
from asics_agent.config import get_settings  # noqa: E402
from asics_agent.legacy_names import canonical_category  # noqa: E402
from asics_agent.scoring import compare as cmp  # noqa: E402
from asics_agent.scoring import compare_run  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument(
        "templates",
        nargs="*",
        type=Path,
        help="filled scoring templates (default: the merged people's workbooks)",
    )
    ap.add_argument("--category", default="parastatal", help="parastatal (default) or ulg")
    ap.add_argument("--city", action="append", help="only this city (default: every city found)")
    ap.add_argument("--out-dir", type=Path, help="default: scoring/2027/compare/")
    ap.add_argument(
        "--min-rows",
        type=int,
        default=int(os.getenv("ASICS_COMPARE_MIN_ROWS", cmp.MIN_ROWS)),
        help=f"show a percentage only from this many compared rows (default {cmp.MIN_ROWS})",
    )
    ap.add_argument(
        "--scorer", default="", help="who filled the templates (default: the file name)"
    )
    ap.add_argument(
        "--answers", type=Path, help="a Step 2 answers workbook (else the city's latest)"
    )
    ap.add_argument(
        "--ai-workbook", type=Path, help="the Step 3 AI workbook (else scoring/2027/ai)"
    )
    ap.add_argument(
        "--ai-runs", type=Path, help="folder of the AI run logs (else beside the workbook)"
    )
    args = ap.parse_args(argv)

    base = get_settings()
    settings = category_settings(base, canonical_category(args.category))
    register, register_issues = load_register(settings.city_register)
    cities = {c.name.casefold(): c for c in register.values()}
    for c in register.values():
        cities.update({a.casefold(): c for a in c.aliases})

    args.templates = args.templates or compare_run.human_files(settings)
    if not args.templates:
        ap.error(f"no filled templates given, and none in {compare_run.human_dir(settings)}")
    reads = compare_run.read_human(args.templates, args.scorer)
    for r in reads:
        print(f"\n{r.report.lines()[0]}")
        for line in r.report.lines()[1:]:
            print(f"  - {line}")
    found = sorted({row.city for r in reads for row in r.rows})
    wanted = {c.casefold() for c in args.city} if args.city else None
    out_dir = args.out_dir or compare_run.compare_dir(settings)
    done = set()
    for name in found:
        city = cities.get(name.casefold())
        if city is None:
            print(
                f'\nThe city "{name}" in the templates is not in the city register: not compared.'
            )
            continue
        if city.name in done or (
            wanted and name.casefold() not in wanted and city.name.casefold() not in wanted
        ):
            continue
        done.add(city.name)
        info_kwargs = dict(answers=args.answers, ai_workbook=args.ai_workbook, ai_runs=args.ai_runs)
        info = compare_run.build_inputs(settings, city, human_paths=args.templates, **info_kwargs)
        comp = cmp.compare_city(info, reads)
        path = cmp.write_comparison(
            comp, out_dir / f"{city.name.replace(' ', '_')}_human_vs_ai.xlsx", args.min_rows
        )
        counts = {s: sum(r.status == s for r in comp.rows) for s in cmp.STATUSES}
        print(f"\n{city.name}: {len(comp.rows)} rows -> {path}")
        print("  " + ", ".join(f"{s}: {n}" for s, n in counts.items() if n))
        print(f"  review list: {len(comp.review) + len(comp.notes)} item(s)")
        for n in comp.notes:
            print(f"  note: {n}")
    if not done:
        print("\nNo city was compared.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
