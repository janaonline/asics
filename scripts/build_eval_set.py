"""Build data/eval_set.yaml: every answerable question that a person scored, with a dev/test split.

Read-only on the merged human files and the question bank (no model call). Answerable = the 52
questions that are not roll-up main questions (43 sub-questions plus the 9 main questions that have no
sub-questions). The split is stratified by (section, human score is 0 or not), deterministic (a fixed
seed), and alternates dev/test inside each stratum, so each half is balanced by section and by zeros.
Only the dev split may be used for tuning or for experiments. Also marks the 20 dev questions of the
spike (14 Bengaluru BWSSB/BMTC, 6 Bhubaneswar BDA/CRUT; a mix of zeros and points).

    uv run python scripts/build_eval_set.py [--out data/eval_set.yaml]
"""

import argparse
import collections
import hashlib
import re
from pathlib import Path

import yaml

from asics_agent.categories import category_settings, load_bank
from asics_agent.config import PROJECT_ROOT, get_settings
from asics_agent.scoring import compare_run as cr
from asics_agent.scoring.human_merge import apply_provenance

SEED = "asics-eval-2026-11"
CITIES = ("Bengaluru", "Bhubaneswar")
EXPERIMENT = {  # city -> (parastatals, how many)
    "Bengaluru": (("BWSSB", "BMTC"), 14),
    "Bhubaneswar": (("BDA", "CRUT"), 6),
}
URL = re.compile(r"https?://[^\s;,<>\"')]+")


def _rank(*parts) -> str:
    return hashlib.sha1("|".join([SEED, *map(str, parts)]).encode()).hexdigest()


def build() -> list[dict]:
    settings = category_settings(get_settings(), "parastatal")
    bank, _ = load_bank(settings)
    humans = cr.read_human(cr.human_files(settings))
    apply_provenance(humans, settings)
    ais = cr.read_human(cr.ai_files(settings), "AI")
    rows = []
    for name in CITIES:
        comp = cr.compare_city_files(
            settings,
            cr.find_city(settings, name),
            humans,
            human_paths=cr.human_files(settings),
            ai_reads=ais,
        )
        for r in comp.rows:
            q = bank.get(r.code)
            if r.human_score is None or q is None or q.is_rollup:
                continue
            rows.append(
                {
                    "city": name,
                    "parastatal": r.unit,
                    "question": r.code,
                    "section": r.section,
                    "question_text": q.text,
                    "max_score": q.max_score,
                    "human_score": r.human_score,
                    "human_zero": r.human_score == 0,
                    "human_sources": list(dict.fromkeys(URL.findall(r.human_source or ""))),
                }
            )
    # stratified, alternating split
    strata = collections.defaultdict(list)
    for row in rows:
        strata[(row["section"], row["human_zero"])].append(row)
    for _, group in sorted(strata.items()):
        group.sort(key=lambda row: _rank(row["city"], row["parastatal"], row["question"]))
        for i, row in enumerate(group):
            row["split"] = "dev" if i % 2 == 0 else "test"
    # the 20 spike questions, from dev only: a balanced mix of zeros and points, spread over sections
    for city, (units, n) in EXPERIMENT.items():
        pool = [
            r for r in rows if r["city"] == city and r["parastatal"] in units and r["split"] == "dev"
        ]
        picked = []
        for zero in (True, False):
            sub = sorted(
                [r for r in pool if r["human_zero"] == zero],
                key=lambda r: (r["section"], _rank("exp", r["parastatal"], r["question"])),
            )
            by_section = collections.defaultdict(list)
            for r in sub:
                by_section[r["section"]].append(r)
            want, queue = n // 2, []
            while len(queue) < want and any(by_section.values()):
                for sec in sorted(by_section):
                    if by_section[sec] and len(queue) < want:
                        queue.append(by_section[sec].pop(0))
            picked += queue
        for r in picked:
            r["spike"] = True
    for r in rows:
        r.setdefault("spike", False)
    rows.sort(key=lambda r: (r["city"], r["parastatal"], r["section"], r["question"]))
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=PROJECT_ROOT / "data" / "eval_set.yaml")
    args = ap.parse_args(argv)
    rows = build()
    header = (
        "# Every answerable question (the 52 that are not roll-ups) that a person scored, in\n"
        "# Bengaluru and Bhubaneswar. split: dev (for tuning and experiments) or test (never tuned on).\n"
        "# spike: true marks the 20 dev questions used by the acquisition and reading spike.\n"
        "# Built by scripts/build_eval_set.py (fixed seed). The human_sources are the links people cited;\n"
        "# the human links were added to the Citation Sheet for these two cities, so they are easier\n"
        "# than a new city.\n"
    )
    args.out.write_text(
        header + yaml.safe_dump({"seed": SEED, "rows": rows}, sort_keys=False, allow_unicode=True, width=110)
    )
    c = collections.Counter
    print(f"{len(rows)} rows written to {args.out}")
    print("split:", dict(c(r["split"] for r in rows)))
    for split in ("dev", "test"):
        sub = [r for r in rows if r["split"] == split]
        print(f"  {split}: sections {dict(c(r['section'] for r in sub))} | zeros {sum(r['human_zero'] for r in sub)} of {len(sub)} | cities {dict(c(r['city'] for r in sub))}")
    spike = [r for r in rows if r["spike"]]
    print("spike questions:", len(spike), dict(c((r["city"], r["parastatal"]) for r in spike)), "| zeros", sum(r["human_zero"] for r in spike), "| sections", dict(c(r["section"] for r in spike)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
