"""Recalculates a scoring workbook's formulas with LibreOffice (no Excel needed).

Files written by this tool (merged human scores, AI copies) hold formulas but no calculated
values until a spreadsheet program opens them. To read the scores, the tool asks LibreOffice,
running in the background, to open the file, recalculate everything and save it again.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

CANDIDATES = [
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    "/usr/bin/soffice",
    "/usr/bin/libreoffice",
    "C:/Program Files/LibreOffice/program/soffice.exe",
]
# Recalculate on load ("always"), whatever the file says; otherwise LibreOffice keeps the
# (empty) cached values of files saved by openpyxl.
SETTINGS = """<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry"
 xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<item oor:path="/org.openoffice.Office.Calc/Formula/Load"><prop oor:name="OOXMLRecalcMode" \
oor:op="fuse"><value>0</value></prop></item>
<item oor:path="/org.openoffice.Office.Calc/Formula/Load"><prop oor:name="ODFRecalcMode" \
oor:op="fuse"><value>0</value></prop></item>
</oor:items>
"""


class RecalcUnavailable(RuntimeError):
    """LibreOffice isn't installed."""


def soffice() -> str | None:
    found = shutil.which("soffice") or shutil.which("libreoffice")
    return found or next((c for c in CANDIDATES if Path(c).exists()), None)


def _profile(base: Path) -> Path:
    profile = base / "libreoffice-profile"
    settings = profile / "user" / "registrymodifications.xcu"
    if not settings.exists():
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(SETTINGS)
    return profile


def recalculate(path: Path, profile_dir: Path, timeout: float = 300) -> Path:
    """Recalculate `path` in place and return it. Raises RecalcUnavailable or RuntimeError."""
    program = soffice()
    if program is None:
        raise RecalcUnavailable(
            "LibreOffice is needed to calculate the scores. Install it from "
            "https://www.libreoffice.org (free), then try again."
        )
    profile = _profile(profile_dir)
    with tempfile.TemporaryDirectory() as out:
        result = subprocess.run(
            [
                program,
                f"-env:UserInstallation={profile.resolve().as_uri()}",
                "--headless",
                "--norestore",
                "--calc",
                "--convert-to",
                "xlsx:Calc MS Excel 2007 XML",
                "--outdir",
                out,
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        produced = Path(out) / f"{path.stem}.xlsx"
        if result.returncode != 0 or not produced.exists():
            raise RuntimeError(
                f"LibreOffice couldn't calculate {path.name}: "
                f"{(result.stderr or result.stdout).strip()[:300]}"
            )
        shutil.move(produced, path)
    return path
