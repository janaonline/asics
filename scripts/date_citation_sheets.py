"""Fill the cut-off columns of old Citation Sheets, into a COPY (free: no web, no AI).

    uv run python scripts/date_citation_sheets.py                    # every city's Sources workbook
    uv run python scripts/date_citation_sheets.py --city Bengaluru
    uv run python scripts/date_citation_sheets.py --cutoff 2026-08-31 --out-dir /some/folder

Writes ASICS_<City>_Sources_dated.xlsx beside each original (or in --out-dir) and prints how many
rows could be dated: properly dated (a full date), Bill or draft, year only, nothing usable. The
original workbook is never changed. Year-only rows stay "unknown".
"""

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from asics_agent.categories import category_settings  # noqa: E402
from asics_agent.citation_dates import date_citation_sheet  # noqa: E402
from asics_agent.config import get_settings  # noqa: E402
from asics_agent.cutoff import CutoffRule  # noqa: E402
from asics_agent.legacy_names import canonical_category  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--category", default="parastatal")
    ap.add_argument("--city", action="append", help="only this city (folder name); default: all")
    ap.add_argument("--cutoff", help="YYYY-MM-DD (default: the category's law_cutoff)")
    ap.add_argument(
        "--out-dir", type=Path, help="where to write the copies (default: beside each original)"
    )
    args = ap.parse_args(argv)
    settings = category_settings(get_settings(), canonical_category(args.category))
    day = date.fromisoformat(args.cutoff) if args.cutoff else settings.law_cutoff
    if day is None:
        ap.error("this category has no law_cutoff; give --cutoff YYYY-MM-DD")
    rule = CutoffRule(day, settings.undated_law_policy)
    wanted = {c.casefold() for c in args.city or []}
    done = 0
    for src in sorted((settings.outputs_dir / "cities").glob("*/ASICS_*_Sources.xlsx")):
        city = src.parent.name
        if wanted and city.casefold() not in wanted:
            continue
        dst = (args.out_dir or src.parent) / src.name.replace(
            "_Sources.xlsx", "_Sources_dated.xlsx"
        )
        try:
            report = date_citation_sheet(src, dst, rule)
        except FileExistsError as exc:
            print(f"{city}: {exc}")
            continue
        print(f"\n{city} (cut-off {day.isoformat()}):")
        print("\n".join(report.lines()))
        done += 1
    if not done:
        print("No Sources workbook was dated.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
