"""Eval report: how well the AI did against the people's scores, from the workbooks that already exist.

No model call and no web access. Reads: data/eval_set.yaml (the questions people scored, with a dev/test
split), the merged human scoring files, the Sources workbooks (Citation Sheet), the latest Step 2 answers
workbooks, the AI scoring copies (Step 3) and the usage records. Writes a results table per city, per
parastatal and overall, for the dev split, the test split and both:

  * source acquisition: of the links the people cited, how many have a Verified Citation Sheet row
    (found by the app / human-verified / not captured, kept apart)
  * Step 2: coverage (a score was proposed, of the rows people scored), agreement when both scored, false
    zeros (AI 0, person above 0), split by Status and by source origin
  * Step 3: the same, from the AI scoring workbooks
  * cost and time of the runs, from the usage records

    uv run python scripts/eval_report.py                    # print, and write scoring/2027/evals/eval_results_<date>.xlsx
    uv run python scripts/eval_report.py --record "label"   # also add one row to scoring/2027/evals/ASICS_2027_AI_Evals.xlsx

CAVEAT (printed with every report): the links people cited were added to the Citation Sheets of Bengaluru and
Bhubaneswar (the Human-Verified? rows), so these two cities are EASIER than a new city. Source acquisition
and agreement here are not what a new city would score.
"""

import argparse
import collections
import json
import subprocess
from datetime import datetime
from pathlib import Path

import yaml
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

from asics_agent import bank_version as bv
from asics_agent.agent_setup import fingerprint
from asics_agent.categories import category_settings, load_bank
from asics_agent.config import PROJECT_ROOT, Settings, get_settings
from asics_agent.scoring import compare_run as cr
from asics_agent.scoring.compare import SAME_SCORE, normalise_url
from asics_agent.scoring.human_merge import apply_provenance
from asics_agent.scoring.phase2 import phase2_status
from asics_agent.sources_workbook import read_sources_workbook, sources_path, workspace_for
from asics_agent.workbook import canonical_header, is_scoring_sheet

EVALS = PROJECT_ROOT / "scoring" / "2027" / "evals"
HISTORY = EVALS / "ASICS_2027_AI_Evals.xlsx"
CITIES = ("Bengaluru", "Bhubaneswar")
CAVEAT = (
    "CAVEAT: the links people cited were added to these two cities' Citation Sheets (Human-Verified? rows), "
    "so Bengaluru and Bhubaneswar are EASIER than a new city. Source acquisition and agreement here are "
    "not what a new city would score."
)
HISTORY_COLUMNS = [
    "Date", "Label", "Git commit", "agent_setup fingerprint", "Bank version", "Model", "Settings changed",
    "Split", "Human-scored rows", "Step 2 coverage", "Step 2 agreement", "Step 2 false zeros",
    "Step 3 coverage", "Step 3 agreement", "Step 3 false zeros", "Sources captured (of human links)",
    "Cost of the runs (US$)", "Minutes of the runs",
]


# -- reading ------------------------------------------------------------------------------------------
def step2_table(settings, slug: str, unit_ids: dict, raw_to_code: dict) -> dict:
    """{(unit, code): {"status", "score", "source_needed"}} from the city's latest Step 2 answers workbook."""
    status = phase2_status(settings, slug)
    if status.answers is None:
        return {}
    wb = load_workbook(status.answers, read_only=True, data_only=True)
    sheet = next((w for w in wb.worksheets if is_scoring_sheet(w.title)), None)
    if sheet is None:
        return {}
    rows = sheet.iter_rows(values_only=True)
    header = [canonical_header(str(h or "")) for h in next(rows, ())]
    col = {h: i for i, h in enumerate(header)}
    out = {}
    for r in rows:
        unit = unit_ids.get(str(r[col["Parastatal"]] or "").casefold())
        code = raw_to_code.get(str(r[col["Question ID"]] or ""))
        if unit and code:
            out[(unit, code)] = {
                "status": str(r[col["Status"]] or "") if "Status" in col else "",
                "score": r[col["Proposed Score"]] if "Proposed Score" in col else None,
            }
    return out


def load_everything() -> dict:
    settings = category_settings(get_settings(), "parastatal")
    bank, _ = load_bank(settings)
    humans = cr.read_human(cr.human_files(settings))
    apply_provenance(humans, settings)
    ais = cr.read_human(cr.ai_files(settings), "AI")
    raw_to_code = {q.raw_id: q.id for q in bank.values()}
    data = {"settings": settings, "bank": bank, "cities": {}}
    for name in CITIES:
        slug = name.lower()
        city = cr.find_city(settings, name)
        comp = cr.compare_city_files(
            settings, city, humans, human_paths=cr.human_files(settings), ai_reads=ais
        )
        ws = workspace_for(settings.outputs_dir, slug)
        parastatals, citations, _ = read_sources_workbook(sources_path(ws, slug), ws / "evidence")
        unit_ids = {}
        for p in parastatals:
            unit_ids[p.id.casefold()] = p.id
            unit_ids[p.name.casefold()] = p.id
        data["cities"][name] = {
            "rows": {(r.unit, r.code): r for r in comp.rows},
            "citations": citations,
            "step2": step2_table(settings, slug, unit_ids, raw_to_code),
        }
    return data


# -- metrics ------------------------------------------------------------------------------------------
def score_metrics(pairs: list[tuple[float, float | None]]) -> dict:
    """pairs of (human score, AI score or None)."""
    n = len(pairs)
    scored = [(h, a) for h, a in pairs if a is not None]
    agree = [1 for h, a in scored if abs(float(a) - float(h)) < SAME_SCORE]
    false0 = [1 for h, a in scored if float(a) == 0 and float(h) > 0]
    return {
        "human_scored": n,
        "coverage": f"{len(scored)} of {n} ({100 * len(scored) / n:.0f}%)" if n else "-",
        "agreement": f"{len(agree)} of {len(scored)} ({100 * len(agree) / len(scored):.0f}%)" if scored else "-",
        "false_zeros": len(false0),
    }


def acquisition(rows: list[dict], data: dict) -> dict:
    """Of the links people cited in these rows (distinct per city, agency and normalised address)."""
    seen, tally = set(), collections.Counter()
    for r in rows:
        cits = data["cities"][r["city"]]["citations"]
        for url in r["human_sources"]:
            key = (r["city"], r["parastatal"], normalise_url(url))
            if key in seen:
                continue
            seen.add(key)
            mine = [c for c in cits if c.parastatal_id in (r["parastatal"], "All parastatals") and normalise_url(c.url) == key[2]]
            ver = [c for c in mine if c.verification_status == "Verified"]
            if any(c.human_verified for c in ver):
                tally["human-verified"] += 1
            elif ver:
                tally["found by the app"] += 1
            else:
                tally["not captured"] += 1
    total = sum(tally.values())
    return {
        "links_cited": total,
        "found by the app": tally["found by the app"],
        "human-verified": tally["human-verified"],
        "not captured": tally["not captured"],
        "captured": f"{total - tally['not captured']} of {total}" if total else "-",
    }


def table_for(rows: list[dict], data: dict) -> dict:
    s2, s3 = [], []
    by_status: dict[str, list] = collections.defaultdict(list)
    by_origin: dict[str, list] = collections.defaultdict(list)
    for r in rows:
        c = data["cities"][r["city"]]
        cmp_row = c["rows"].get((r["parastatal"], r["question"]))
        a2 = c["step2"].get((r["parastatal"], r["question"]), {})
        h = r["human_score"]
        s2.append((h, a2.get("score")))
        by_status[a2.get("status") or "no answer"].append((h, a2.get("score")))
        s3.append((h, cmp_row.ai_score if cmp_row is not None and cmp_row.ai_score_from == "Step 3" else None))
        by_origin[(cmp_row.source_origin if cmp_row is not None else "") or "App-found"].append((h, a2.get("score")))
    return {
        "step2": score_metrics(s2),
        "step3": score_metrics(s3),
        "acquisition": acquisition(rows, data),
        "by_status": {k: score_metrics(v) for k, v in sorted(by_status.items())},
        "by_origin": {k: score_metrics(v) for k, v in sorted(by_origin.items())},
    }


def usage_runs(settings) -> list[dict]:
    out = []
    folder = settings.outputs_root / "_app" / "usage" if settings.outputs_root else None
    for f in sorted((folder or Path()).glob("*.json")) if folder and folder.exists() else []:
        d = json.loads(f.read_text())
        if d.get("category") not in (None, "parastatal"):
            continue
        minutes = None
        try:
            minutes = round((datetime.fromisoformat(d["finished"]) - datetime.fromisoformat(d["started"])).total_seconds() / 60, 1)
        except (KeyError, TypeError, ValueError):
            pass
        out.append({"file": f.name, "step": d.get("step"), "cities": ", ".join(d.get("cities") or []), "usd": d.get("total_usd"), "minutes": minutes})
    return out


# -- output -------------------------------------------------------------------------------------------
def split_rows(rows: list[dict]) -> dict[str, list[dict]]:
    return {"dev": [r for r in rows if r["split"] == "dev"], "test": [r for r in rows if r["split"] == "test"], "both": rows}


def write_results(path: Path, rows: list[dict], data: dict, runs: list[dict]) -> dict:
    wb = Workbook()
    wb.remove(wb.active)
    summary = {}
    for level, keyfn in (("Overall", lambda r: "all"), ("By city", lambda r: r["city"]), ("By parastatal", lambda r: f"{r['city']} / {r['parastatal']}")):
        ws = wb.create_sheet(level)
        head = ["Group", "Split", "Human-scored rows", "Step 2 coverage", "Step 2 agreement", "Step 2 false zeros",
                "Step 3 coverage", "Step 3 agreement", "Step 3 false zeros", "Links cited", "Captured", "Found by the app", "Human-verified", "Not captured"]
        ws.append(head)
        for c in ws[1]:
            c.font = Font(bold=True)
        groups = sorted({keyfn(r) for r in rows})
        for g in groups:
            for split, sub in split_rows([r for r in rows if keyfn(r) == g]).items():
                if not sub:
                    continue
                t = table_for(sub, data)
                ws.append([g, split, t["step2"]["human_scored"], t["step2"]["coverage"], t["step2"]["agreement"], t["step2"]["false_zeros"],
                           t["step3"]["coverage"], t["step3"]["agreement"], t["step3"]["false_zeros"],
                           t["acquisition"]["links_cited"], t["acquisition"]["captured"], t["acquisition"]["found by the app"],
                           t["acquisition"]["human-verified"], t["acquisition"]["not captured"]])
                if level == "Overall":
                    summary[split] = t
        for col in "ABCDEFGHIJKLMN":
            ws.column_dimensions[col].width = 22
    ws = wb.create_sheet("Step 2 by status and origin")
    ws.append(["Split", "Kind", "Value", "Human-scored rows", "Coverage", "Agreement", "False zeros"])
    for split, sub in split_rows(rows).items():
        t = table_for(sub, data)
        for kind, block in (("Status", t["by_status"]), ("Source origin", t["by_origin"])):
            for k, m in block.items():
                ws.append([split, kind, k, m["human_scored"], m["coverage"], m["agreement"], m["false_zeros"]])
    ws = wb.create_sheet("Runs (cost and time)")
    ws.append(["Usage file", "Step", "Cities", "US$", "Minutes"])
    for r in runs:
        ws.append([r["file"], r["step"], r["cities"], r["usd"], r["minutes"]])
    ws = wb.create_sheet("Read me")
    ws.append([CAVEAT])
    ws.append(["Rows are the questions people scored in data/eval_set.yaml (answerable questions only, no roll-ups); dev and test halves are balanced by section and by zero versus points."])
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return summary


def settings_changed(settings) -> str:
    names = ["required_sources", "human_verified_sources", "crawl_max_pages", "crawl_incomplete_on_dead_link", "find_sources_max_uses", "max_evidence_chars", "batch_answers"]
    out = []
    for n in names:
        default = Settings.__dataclass_fields__[n].default if n in Settings.__dataclass_fields__ else None
        if getattr(settings, n, None) != default:
            out.append(f"{n}={getattr(settings, n, None)}")
    return "; ".join(out) or "none"


def record(label: str, summary: dict, data: dict, runs: list[dict]) -> None:
    settings = data["settings"]
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=PROJECT_ROOT).stdout.strip()
    version = bv.bank_version(settings.question_bank, data["bank"])
    if HISTORY.exists():
        wb = load_workbook(HISTORY)
        ws = wb["Runs"]
    else:
        HISTORY.parent.mkdir(parents=True, exist_ok=True)
        wb = Workbook()
        ws = wb.active
        ws.title = "Runs"
        ws.append(HISTORY_COLUMNS)
        for c in ws[1]:
            c.font = Font(bold=True)
    cost = round(sum(r["usd"] or 0 for r in runs), 2)
    minutes = round(sum(r["minutes"] or 0 for r in runs), 1)
    for split in ("dev", "test", "both"):
        t = summary.get(split)
        if not t:
            continue
        ws.append([datetime.now().isoformat(timespec="minutes"), label, commit, fingerprint(settings.agent_setup_dir),
                   version.version if version else "", settings.model, settings_changed(settings), split,
                   t["step2"]["human_scored"], t["step2"]["coverage"], t["step2"]["agreement"], t["step2"]["false_zeros"],
                   t["step3"]["coverage"], t["step3"]["agreement"], t["step3"]["false_zeros"], t["acquisition"]["captured"], cost, minutes])
    wb.save(HISTORY)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-set", type=Path, default=PROJECT_ROOT / "data" / "eval_set.yaml")
    ap.add_argument("--out", type=Path, default=EVALS / f"eval_results_{datetime.now():%Y%m%d}.xlsx")
    ap.add_argument("--record", metavar="LABEL", help="also add one row per split to the evals history workbook")
    args = ap.parse_args(argv)
    rows = yaml.safe_load(args.eval_set.read_text())["rows"]
    data = load_everything()
    runs = usage_runs(data["settings"])
    summary = write_results(args.out, rows, data, runs)
    print(CAVEAT, "\n")
    for split in ("dev", "test", "both"):
        t = summary[split]
        print(f"[{split}] {t['step2']['human_scored']} rows | Step 2: coverage {t['step2']['coverage']}, agreement {t['step2']['agreement']}, false zeros {t['step2']['false_zeros']}"
              f" | Step 3: coverage {t['step3']['coverage']}, agreement {t['step3']['agreement']}, false zeros {t['step3']['false_zeros']}"
              f" | links captured {t['acquisition']['captured']} (app {t['acquisition']['found by the app']}, human-verified {t['acquisition']['human-verified']}, not captured {t['acquisition']['not captured']})")
    print(f"\nwrote {args.out}")
    if args.record:
        record(args.record, summary, data, runs)
        print(f"added a row per split to {HISTORY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
