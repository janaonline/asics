"""Build the question bank file from the team's question workbook.

    uv run python scripts/build_question_bank.py docs/reference/Bengaluru_Parastatal_Pilot_NC19102026_1.xlsx
    uv run python scripts/build_question_bank.py SOURCE.xlsx --dry-run     # report only, write nothing
    uv run python scripts/build_question_bank.py SOURCE.xlsx --sections UPD SC DPG

Reads the section sheets (UPD, SC, DPG) by sheet name and the columns by header text, writes the
bank file the app loads, moves the previous bank to data/question_banks/archive/ (git mv), and
prints what changed: added, removed, text changed, max changed, applicability changed. Anything
it does not understand is listed under "not understood" and skipped. Running it again on the same
source changes nothing.
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from asics_agent import bank_builder as bb  # noqa: E402
from asics_agent.bank_version import bank_version, make_version  # noqa: E402
from asics_agent.question_bank import load_question_bank  # noqa: E402

BANKS = ROOT / "data" / "question_banks"
DEFAULT_OUT = BANKS / "Parastatal_ASICS_Question_Bank.xlsx"
DEFAULT_TEMPLATES = sorted(
    (ROOT / "scoring" / "2027" / "templates").glob("Parastatal_*_Template.xlsx")
)


def _show(title: str, lines, limit: int = 60):
    lines = list(lines)
    print(f"\n{title} ({len(lines)})")
    for line in lines[:limit]:
        print(f"  - {line}")
    if len(lines) > limit:
        print(f"  ... and {len(lines) - limit} more")


def _archive(old: Path) -> Path:
    questions, _ = load_question_bank(old)
    version = bank_version(old, questions)
    stem = f"{old.stem}__{version.version.split('@', 1)[-1].replace('@', '_').replace('#', '-')}"
    target = BANKS / "archive" / f"{stem}.xlsx"
    target.parent.mkdir(parents=True, exist_ok=True)
    tracked = (
        subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(old)], cwd=ROOT, capture_output=True
        ).returncode
        == 0
    )
    if tracked:
        subprocess.run(["git", "mv", str(old), str(target)], cwd=ROOT, check=True)
    else:
        shutil.move(old, target)
    return target


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("source", type=Path, help="the team's question workbook")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="the bank file to write")
    ap.add_argument("--sections", nargs="+", default=list(bb.DEFAULT_SECTIONS))
    ap.add_argument(
        "--templates",
        nargs="*",
        type=Path,
        default=DEFAULT_TEMPLATES,
        help="scoring templates whose Question_Index is compared with the rules",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    report = bb.read_source(args.source, args.sections)
    previous, previous_issues = ({}, [])
    if args.out.exists():
        previous, previous_issues = load_question_bank(args.out)
    names = {q.pillar.upper(): q.pillar_name.split("(")[0].strip() for q in previous.values()}

    with tempfile.TemporaryDirectory() as tmp:
        draft = Path(tmp) / "bank.xlsx"
        bb.write_bank(report, draft, names=names)
        questions, issues = load_question_bank(draft)
        digest_version = bank_version(draft, questions)
        final = Path(tmp) / "final.xlsx"
        bb.write_bank(
            report, final, digest_version.content_hash, bb.file_sha256(args.source), names
        )

        print(f"Source: {args.source.name}")
        for s in report.sheets:
            print(
                f"  {s.sheet}: {s.questions} questions, {s.data_rows} per-parastatal rows skipped"
            )
        print(f"Questions in the new bank: {len(questions)}")
        version = make_version(
            args.source.name, bb.date.today().isoformat(), digest_version.content_hash
        )
        print(f"Bank version: {version}")
        diff = bb.diff_banks(previous, questions) if previous else None
        unchanged = (
            bool(previous)
            and bank_version(args.out, previous).content_hash == digest_version.content_hash
        )

        if diff is not None:
            _show("Added", [f"{c}: {questions[c].text[:90]}" for c in diff.added])
            _show("Removed", [f"{c}: {previous[c].text[:90]}" for c in diff.removed])
            _show(
                "Text changed",
                [
                    f"{c}"
                    + (
                        "  <- very different: probably another question under the same code"
                        if c in diff.different_question
                        else ""
                    )
                    for c in diff.text_changed
                ],
            )
            _show("Max score changed", [f"{c}: {a} -> {b}" for c, a, b in diff.max_changed])
            _show(
                "Applicability changed",
                [f'{c}: "{a}" -> "{b}"' for c, a, b in diff.applicability_changed],
            )
            _show("Tag changed", [f"{c}: {a} -> {b}" for c, a, b in diff.tag_changed])
            _show("Methodology / evidence / level / unit changed", diff.other_changed)
        else:
            print("\nThere is no previous bank to compare with.")

        _show("Not understood (listed and skipped)", report.not_understood)
        _show("Ignored sheets", report.ignored)
        _show(
            "Source columns not copied (scorers' columns or unknown)",
            [f"{s.sheet}: {', '.join(s.not_copied)}" for s in report.sheets if s.not_copied],
        )
        _show("Notes on the source", [f"{s.sheet}: {n}" for s in report.sheets for n in s.notes])
        _show("Loader messages (team)", [i.message for i in issues if i.audience == "team"])
        _show("Applicability wording no rule recognises", bb.unrecognised_applicability(questions))

        print(
            "\nWho each question applies to (Y/N per type; 'if <flag>' = decided by a Yes/No flag)"
        )
        codes = [t.code for t in bb.PARASTATAL_TYPES]
        print(f"  {'question':9} " + " ".join(f"{c[:12]:12}" for c in codes) + "  rule")
        for row in bb.applicability_table(questions):
            print(
                f"  {row['code']:9} "
                + " ".join(f"{row['types'][c]:12}" for c in codes)
                + f"  {row['rule']}"
            )
        differences, notes = bb.compare_with_templates(questions, args.templates)
        _show("Differences from the templates' Question_Index (columns J-L)", differences, 200)
        _show("Not compared", notes)

        if args.dry_run:
            print("\nDry run: nothing written.")
            return 0
        if unchanged:
            print("\nThe bank file already has exactly these questions: nothing written.")
            return 0
        if args.out.exists():
            print(f"\nPrevious bank moved to {_archive(args.out).relative_to(ROOT)}")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(final, args.out)
        print(f"Wrote {args.out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
