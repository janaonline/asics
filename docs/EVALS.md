# Evals: how well does the AI match the people?

A small, repeatable way to answer "did this change help?" without a paid run. Everything here is free:
no model call, no web access. It compares what people scored with what the app already produced.

## The pieces

| File | What it is |
|---|---|
| `data/eval_set.yaml` | The 201 questions people scored in Bengaluru and Bhubaneswar (roll-ups left out), each with the human score, the links people cited, and a **dev** or **test** split. Built with a fixed seed (`asics-eval-2026-11`), so it never reshuffles. |
| `scripts/build_eval_set.py` | Rebuilds the eval set from the people's scoring files. Run it only if the scoring files change; the split stays the same for the same rows. |
| `scripts/eval_report.py` | Reads the eval set, the Sources workbooks, the latest Step 2 and Step 3 results and the cost records, and writes the results workbook. |
| `scoring/2027/evals/eval_results_<date>.xlsx` | One report. |
| `scoring/2027/evals/ASICS_2027_AI_Evals.xlsx` | The history: one row per recorded run, so you can see a trend. |

## How to run it

```bash
uv run python scripts/eval_report.py                       # prints a summary, writes eval_results_<today>.xlsx
uv run python scripts/eval_report.py --record "label"      # also adds one row per split to the history workbook
uv run python scripts/eval_report.py --out some/path.xlsx  # write the report somewhere else
```

Record a row only after a real Step 1 to 3 run you want to compare against later, with a label that says
what changed ("staged fetch on", "scan budget 5").

## How to read the sheets

- **Overall / By city / By parastatal**: one row per group and split.
  - *Step 2 coverage*: of the questions people scored, how many got a score from the app. A low number
    means "left blank for a person", which is the safe default, not an error.
  - *Step 2 agreement*: of the questions where both scored, how many scores match. Look at this together
    with coverage: 90% agreement on 5% coverage says little.
  - *False zeros*: the app wrote 0 where a person gave points. This is the number that must stay at 0.
  - *Step 3*: the same, for the scoring step.
  - *Links cited / Captured*: of the links people cited, how many have a Verified row in the Citation
    Sheet, split into found by the app, human-verified, and not captured. "Not captured" is the gap the
    fetch chain and scan reading are meant to close.
- **Step 2 by status and origin**: the same results split by answer status and by where the source came
  from (found by the app, human-verified).
- **Runs (cost and time)**: what the runs behind the numbers cost.
- **Read me**: the caveat below.

## Rules

1. **Never tune on the test split.** Change prompts, settings and code while looking at **dev** only. Look
   at **test** once, at the end, to check the change really helped. If you tune on test, the numbers
   stop meaning anything.
2. **Bengaluru and Bhubaneswar are easier than a new city.** People's links were added to their Citation
   Sheets (the *Human-Verified?* rows). Agreement and source capture here are an upper bound for a new
   city, not a forecast.
3. **Compare like with like.** A report is only comparable to another if the eval set is the same file.
   Rebuilding it from different scoring files makes a new baseline.
4. **The spike questions** (`spike: true`) are 20 dev questions that were used to design the acquisition
   build. Do not use them as proof the build works; use the rest of dev, then test.
