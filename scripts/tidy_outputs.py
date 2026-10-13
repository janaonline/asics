"""Move an outputs folder from the earlier layouts into the current one, then write
outputs/START_HERE.xlsx. Nothing is deleted: files are only moved, and a file that already
exists at its new place is left where it was (and listed).

    uv run python scripts/tidy_outputs.py            # show what would move
    uv run python scripts/tidy_outputs.py --apply    # move it

Current layout (see src/asics_agent/outputs_index.py):
    outputs/START_HERE.xlsx
    outputs/<Vertical>/cities|batches|practice/
    outputs/_app/          the app's error log, uploads, last vertical chosen
    outputs/_old/          earlier layouts' leftovers
"""

import argparse
import shutil
from pathlib import Path

from asics_agent.config import get_settings
from asics_agent.outputs_index import write_index

# earlier place (inside outputs/) -> current place
MOVES = [
    ("cities", "Parastatal/cities"),
    ("batches", "Parastatal/batches"),
    ("practice", "Parastatal/practice"),
    ("verticals/upd", "UPD"),
    ("app_errors.log", "_app/app_errors.log"),
    (".last_vertical", "_app/last_vertical"),
    ("uploads", "_app/uploads"),
    ("bengaluru", "_old/bengaluru"),  # the first version's single-city runs
    ("evidence", "_old/evidence"),  # the first version's shared evidence cache
]


def move(src: Path, dst: Path, apply: bool, skipped: list[str]) -> None:
    """Move src to dst; merge folder contents if dst already exists."""
    if src.is_dir() and dst.is_dir():
        for child in sorted(src.iterdir()):
            move(child, dst / child.name, apply, skipped)
        if apply and not any(src.iterdir()):
            src.rmdir()
        return
    if dst.exists():
        skipped.append(f"{src} (already at {dst})")
        return
    print(f"  {src}  →  {dst}")
    if apply:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="move the files (default: preview)")
    args = parser.parse_args()
    settings = get_settings()
    root = settings.outputs_root or settings.outputs_dir
    skipped: list[str] = []
    print("Moving:" if args.apply else "Would move (run with --apply to do it):")
    for old, new in MOVES:
        if (root / old).exists():
            move(root / old, root / new, args.apply, skipped)
    verticals = root / "verticals"
    if args.apply and verticals.is_dir() and not any(p for p in verticals.iterdir()
                                                     if p.name != ".DS_Store"):
        shutil.rmtree(verticals)  # only an empty folder (and a Finder file) is left
    for line in skipped:
        print(f"  left in place: {line}")
    if args.apply:
        print(f"Wrote {write_index(settings)}")


if __name__ == "__main__":
    main()
