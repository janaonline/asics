"""The one place that knows the old names ("vertical", "upd", "city_government").

Saved work (outputs/, memory notes, workbooks, .env files) may still use them. The rest of the
code uses only the new names and asks this module to read the old ones; it writes new names only.

  old                                  new
  vertical                             category
  vertical "upd"                       category "ulg"
  unit "city_government"               unit "ulg"
  ASICS_VERTICAL                       ASICS_CATEGORY
  outputs/UPD/, skills/sections/upd/   outputs/ULG/, skills/sections/ulg/
  ASICS_UPD_<City>_Phase2.xlsx         ASICS_ULG_<City>_Phase2.xlsx
"""

import logging
import os
import sys
from pathlib import Path

CATEGORY_ALIASES = {"upd": "ulg"}  # the old "upd" vertical is the ULG category
UNIT_ALIASES = {"city_government": "ulg", "city government": "ulg"}
# category -> the folder names its work used to be kept under (outputs/, skills/sections/)
OLD_FOLDERS = {"ulg": ("UPD",)}
# memory/<folder>/<category>/: notes for one category (the old folder is still read)
MEMORY_FOLDERS = ("categories", "verticals")
# category title -> the title its answers files used to carry (ASICS_<title>_<City>_Phase2.xlsx)
OLD_FILE_TITLES = {"ULG": ("UPD",)}


def canonical_category(name: str) -> str:
    name = (name or "").strip().lower()
    return CATEGORY_ALIASES.get(name, name)


def canonical_unit(value: str) -> str:
    value = (value or "").strip().lower()
    return UNIT_ALIASES.get(value, value)


def env_category(default: str = "parastatal") -> str:
    """ASICS_CATEGORY, else the old ASICS_VERTICAL (with a warning), else `default`."""
    if value := os.getenv("ASICS_CATEGORY"):
        return canonical_category(value)
    if value := os.getenv("ASICS_VERTICAL"):
        logging.warning("ASICS_VERTICAL is the old name: set ASICS_CATEGORY=%s instead.", value)
        return canonical_category(value)
    return default


def old_folders(category: str) -> tuple[str, ...]:
    return OLD_FOLDERS.get(category, ())


def pick_dir(parent: Path, new: str, *old: str) -> Path:
    """parent/new, unless only an old folder exists (then that one, so saved work still loads)."""
    path = parent / new
    if path.exists():
        return path
    return next((parent / name for name in old if (parent / name).exists()), path)


OLD_KEYS = {"category": "vertical", "category_title": "vertical_title"}  # saved JSON keys


def read_key(data: dict, new: str, default=""):
    """A value saved under the new key, else under its old key."""
    return data[new] if new in data else data.get(OLD_KEYS.get(new, new), default)


def answers_globs(title: str) -> list[str]:
    """File patterns of a category's answers workbooks: the new name, then the old ones."""
    return [f"ASICS_{t}_*.xlsx" for t in (title, *OLD_FILE_TITLES.get(title, ()))]


# Workbook sheet names and column headers that used to say "Vertical" (results, assignments, evals).
OLD_LABELS = {"Category": "Vertical", "Categories": "Verticals"}
_NEW_LABELS = {old: new for new, old in OLD_LABELS.items()}


def current_label(text: str) -> str:
    """A sheet name or header read from a workbook, with an old name turned into the new one."""
    return _NEW_LABELS.get(text, text)


def sheet_name(names: list[str], new: str) -> str:
    """The sheet called `new` in a workbook, else the one with its old name (else `new`)."""
    old = OLD_LABELS.get(new)
    return new if new in names or old not in names else old


def old_option(value: str) -> str:
    """The category named by the old `--vertical` option (a name or a scoring code, e.g. UPD);
    prints a one-line warning."""
    category = canonical_category(value)
    print(f"Warning: --vertical is the old name: use --category {category}.", file=sys.stderr)
    return category


OLD_APP_FILES = {"last_category": "last_vertical"}  # outputs/_app/ files


def read_app_file(folder: Path, name: str) -> str:
    """The text of an outputs/_app/ file, else of the file it used to be called (else "")."""
    for candidate in (name, OLD_APP_FILES.get(name)):
        if candidate and (folder / candidate).exists():
            return (folder / candidate).read_text().strip()
    return ""


# outputs/ places of earlier layouts -> where scripts/tidy_outputs.py moves them now
OLD_OUTPUT_MOVES = [
    ("verticals/upd", "ULG"),
    ("UPD", "ULG"),
    (".last_vertical", "_app/last_category"),
    ("_app/last_vertical", "_app/last_category"),
]
OLD_OUTPUT_FOLDER = "verticals"  # removed by tidy_outputs once empty
