# ASICS project map

Written 6 Nov 2026 for the program lead; updated 11 Nov 2026 (methodology as the rule, the Law/Policy cut-off, and the plain-English prompt guide). Plain English. Short sentences.

**How to read the marks.** **[V]** = I checked it in the code or files. **[T]** = it passed an automated test or a practice run (scripted AI, made-up cities). **[A]** = my assumption, not checked. I do not know the roles of Anita and Pradeep, so in section 8 "who decides" uses *program team* and *developer*. Please fill in names.

---

## 1. Purpose and direction

ASICS scores how well Indian cities and their agencies work. Today the category is **Parastatal** (water boards, bus companies, development authorities). **ULG** (the city government) comes later.

The work has three steps. **Step 1** finds each city's parastatals and the official sources (the "Citation Sheet"). **Step 2** answers the question bank from those sources. **Step 3** scores. The research team uses the app on a laptop. Interns fill the scoring templates by hand.

**Target.**
- The user picks a city, then a category.
- The AI finds answers and sources (Step 2) and fills copies of the team's three scoring templates (Step 3).
- For a few "golden" cities, people fill the same templates. The portal compares people and AI.
- Later the team relies on the AI for all other cities. Golden data is used as examples, as a test set and to fix weak questions.
- There is no database. Files are the storage and are shared through git. The repo is public today and will become private.

---

## 2. Where we are

| # | Task | Status | Evidence | Not tested |
|---|---|---|---|---|
| a | A1/A2/R/P/M table with First-Principles layer and Who-answers-it | **Done** [V] | The 5-row table (columns Mode, What it means, First-Principles layer, Who answers it, Confidence/Score) is in `agent_setup/prompts/answer-question.md` and `answer-city-question.md`. Both are identical to the table in `docs/source_prompts/ASICS_Phase2_Prompt_v2.md`. Code reads the class: `agents/sections/base.py`. Test: `tests/test_answer_classes.py` [T]. | The model has not been run on real data since. Git history shows both files touched on 30 Oct, so I cannot say which edit added the columns [A]. |
| b | "vertical" → "category", city-first flow, ULG, unit names | **Done, with leftovers** [V] | `categories.py`, `agent_setup/categories/{parastatal,ulg}.md`, `legacy_names.py`. Unit values are `parastatal` and `ulg`. Sidebar is City then Category. | See the leftovers below. |
| c | New question bank, types, rules, versions | **Done** [V][T] | Bank has **69** questions (UPD 20, DPG 25, SC 24): 52 scored sub-questions with a template sheet, plus 17 main questions that roll up. Version `Bengaluru_Parastatal_Pilot_NC19102026_1@2026-11-04#9d2acfb3`. Rules in `data/applicability_rules.yaml`. Types in `parastatal_types.py`. Builder `bank_builder.py`. | Never used for a real Step 2 run. |
| d | Step 3 AI fills UPD / SC / DPG, recalculated by LibreOffice | **Done in code** [V][T] | `scoring/template_fill.py`, `template_scoring.py`, `recalc.py`. 48 of 52 questions reach the scorer; 4 are left for people (SC 2, SC 12a, SC 12b, DPG 4). | Only scripted AI on made-up cities. Never the real model on real answers. A delivered file was never opened in desktop Excel. |
| e | Scores page: Consolidated, Compare, Files | **Done in code** [V][T] | `compare_page.py`, `scoring/compare.py`, `compare_run.py`, `consolidated.py`. | Only synthetic people's files. |
| f | People's upload, storage, merge, intern copies | **Done in code** [V][T] | `people_page.py`, `scoring/submissions.py`, `human_merge.py`, `human_copies.py`. | No real filled template exists yet. Folders `scoring/2027/human/` and `merged/` do not exist yet [V]. |
| g | Name resolution (unknown cities / parastatals) | **Done in code** [V][T] | `scoring/name_resolution.py`, `register_edit.py`, `tests/test_name_resolution.py`. | Register edit tested on copies only. The "Add as new" input boxes were not click-tested. |
| h | Score levels, SC 1/SC 3 two-year rule, header checks | **Done in code** [V][T] | `scoring/score_levels.py`, `template_scoring.py`, `template_import.py`; `docs/AI_COVERAGE.csv`. 29 questions have fixed levels, 13 are partial credit. | Real model. UPD 1a middle level (2.5) is read as typed: needs program-team confirmation. |
| i | Follow-ups | **Mixed** [V] | See below. | |
| l | Methodology as the rule, and the Law/Policy cut-off (31 Aug 2026) | **Done in code** [V][T], not committed | New `cutoff.py`, `methodology.py`, `skill_check.py`, `citation_dates.py`, `scripts/date_citation_sheets.py`; two new Citation Sheet columns; Step 1, 2 and 3 changed; `tests/test_cutoff.py`. 312 tests pass. | The real model has never filled the new Step 1 columns. Run steps page not rendered headlessly. |
| j | Commits | See below | | |
| k | Real data | See below | | |

**b. Leftover "vertical" words.** [V]
- `legacy_names.py` keeps the old names on purpose, so old files still load.
- A hidden `--vertical` option remains in 3 scripts.
- Old-name tests exist.
- The old folder `outputs/UPD/` (the old name of the ULG folder) and a state file `outputs/_app/last_vertical` still exist. There is no `outputs/ULG/` yet.
- Other hits are layout words (`vertical_alignment`), not names.
- Code still models a ULG as a "Parastatal" object. `docs/NAMING.md` section 4 lists every place. This was not changed.
- Your local `.env` had the old `ASICS_VERTICAL`. I renamed it on 6 Nov.

**i. Follow-ups.**
- **.gitignore safety:** reversed on purpose. We first ignored `outputs/`, `scoring/2027/ai/` and similar. You then asked for them in the repo. `.gitignore` now ignores only `.env`, the virtual environment, caches and `.DS_Store`.
- **Conflict status on the Scores page:** **not done.** The status list has no "conflict" [V]. Conflicts show only in People's scoring under "Needs a look" and in the merge record.
- **Version stamp in intern copies:** **not done.** `human_copies.py` writes none [V].
- **Download buttons on Steps 1 and 2:** **partly.** Steps 3 and Scores have them. Some Step 1 and 2 buttons still only "Open in Excel" (`app.py`, `city_view_page.py`). I did not check each pair.
- **Hosting notes in `docs/DB_DESIGN.md`:** **not done.** The file has no hosting section. Hosting is mentioned only in `README.md` and `hosting.py` (`ASICS_HOSTED=1`).
- **Unused setting:** `.env` sets `ASICS_WEB_SEARCH_MAX_USES`, but no code reads it [V].
- **Outdated skills (11 Nov):** **done.** `skills/sections/sc.md`, `dpg.md`, `upd.md` and `scoring-methodology.md` were cleaned: lines about the old question list were removed, and each now says the methodology is the rule. A free check (`skill_check.py`) lists any help file that names a question no bank has; it finds none now [V][T]. The memory notes were not changed.

**j. Commits.** Branch `rename-vertical-to-category`, in step with origin. Newest: `80a043e` (this file), `af9f1e7` (warning filter), `0d3d4b9` (outputs added to the repo), `dda52ac` (team reference files), `fea1da8` (the main work in one commit), `e51bcad` (the rename). `main` is the old "first commit" and is 15 behind `origin/main`. **Not committed (11 Nov work):** the cut-off and methodology changes (29 edited files, 6 new files, 2 dated Citation Sheet copies in `outputs/Parastatal/cities/*/`), and this update. Two other uncommitted changes are not from this work: an edit to the city register (Mysore replaced by Bhubaneswar, Lucknow added) and a rewritten `outputs/START_HERE.xlsx`. Never merged to `main`.

**k. Real data.**
- **Real runs:** Step 1 and Step 2 on **Bengaluru and Surat**, 12–13 Oct, on the **old** bank. Old Step 3 on the draft workbook and the old UPD workbook. Files are in `outputs/` [V]. The old Step 2 summaries carry no bank version.
- **Real files, free tools only (11 Nov):** the date-filling script ran on the real Bengaluru and Surat Citation Sheets (copies only; originals unchanged).
- **Not on real data:** Step 2 with the new bank. Step 3 on the three templates. A real people's upload, merge, name resolution or compare. Cost on real runs (the usage folder is empty).
- **Only tested with practice or synthetic data:** everything in d–h and l (except the date-filling script above).

**l. Methodology and cut-off (11 Nov).** [V][T]
- **Methodology is the rule.** The Detailed Methodology already reaches the model word for word in Step 2 and Step 3 (all 69 questions, tested). New: a precedence line in the shared prompts (conflict → follow the methodology, add `CONFIRM:`), a check that Step 2's BAND is a real level or part of the methodology, "Methodology: <band>" at the start of Step 3's Scorer Comments, and DPG 4 (methodology is only a placeholder note) left for a person.
- **Cut-off.** `agent_setup/categories/parastatal.md` sets `law_cutoff: 2026-08-31` and `undated_law_policy: confirm`. The Citation Sheet has two new columns, **Effective / As-of Date** and **Cut-off Check** (`ok`, `later`, `unknown`, `Bill-draft`); the answers workbook is unchanged. For a Law/Policy question only: `later` sources are hidden and cannot be cited; Bills are not law; `unknown` (including year-only) is used with a CONFIRM note and Confidence at most Medium; if nothing usable is left the answer is Human Verification Required with `PENDING FETCH: <reason>`. Implementation questions are not restricted. Step 3 applies the same rule. The setting shows on Run steps and is saved in `run_summary.json`, `sources_summary.json` and `.ai_info.json`. ULG has no cut-off.
- **Old data.** The date-filling script wrote copies of the Bengaluru and Surat Citation Sheets. Bengaluru: 51 of 240 rows have a full date, 17 are Bills, 64 year-only, 108 nothing; of 68 legal citations 25 have a real date. Surat: 30 of 116 dated, 0 Bills; of 31 legal citations 14 have a real date. Bengaluru's old answers cite 17 distinct Bills (106 answer rows); Surat none.
- **Bank rows whose level looks wrong (bank not changed):** DPG 4 (Law/Policy, but no scoring rule), UPD 6 (empty), DPG 1a ("Law/policy"), DPG 8 ("and" instead of "+"); ULG UPD 13 ("NA- ...") and five spellings of "both".

---

## 3. How the app is structured

**Pages** (left menu, `app.py`): Home; Run steps; Step 1 Find sources; Step 2 Answer questions; Step 3 Score (tabs AI scoring and People's scoring); Current run; City files; Re-check links; City register; Agent setup; Question bank check; Scores; Costs; Help. Start it by double-clicking `Start ASICS.command`.

**Modules** (`src/asics_agent/`):
- **Settings:** `config.py`, `categories.py`, `legacy_names.py`, `hosting.py`, `agent_setup.py` (reads prompts and memory).
- **Question bank:** `question_bank.py`, `bank_builder.py`, `bank_version.py`, `bank_status.py`, `applicability.py`, `parastatal_types.py`.
- **Methodology and cut-off:** `cutoff.py` (the Law/Policy test, effective dates, the check, which sources a question may use), `methodology.py` (BAND check, placeholder methodology), `skill_check.py` (help files that name a missing question), `citation_dates.py` (fills old Citation Sheets into a copy).
- **Register and cities:** `cities.py`, `scoring/register_edit.py`, `scoring/name_resolution.py`.
- **Step 1:** `agents/sources_master.py`, `parastatal_discovery.py`, `initial_checks.py`, `links_builder.py`, `links/*` (link checks, trust, saved pages), `sources_workbook.py`.
- **Step 2:** `agents/answers_master.py`, `agents/sections/base.py`, `rollup.py`, `batch.py`, `workbook.py`, `final_qa.py`.
- **Running and cost:** `llm.py`, `runner.py`, `plan.py`, `costs.py`, `usage.py`, `practice.py` (scripted AI), `recheck.py`.
- **Step 3 AI:** `scoring/template_fill.py`, `template_scoring.py`, `score_levels.py`, `phase2.py`, `recalc.py`. (`ai.py`, `skeleton.py`, `template.py`, `scores.py`, `human.py` are the older ULG path.)
- **People's scoring:** `scoring/submissions.py`, `human_merge.py`, `human_copies.py`, `template_import.py` (reads any filled template).
- **Compare and Scores:** `scoring/compare.py`, `compare_run.py`, `consolidated.py`, `workflow.py`.

**Agents** (`agent_setup/agents/`, 10 files): city-profiler, parastatal-discovery, website-profiler, source-assessor, citation-builder and city-citation-builder (Step 1); answer-writer and city-answer-writer (Step 2); question-scorer (Step 3); question-bank-reviewer. All use `claude-sonnet-5-5`. Their prompts are in section 5.

**Data files:** `data/question_banks/Parastatal_ASICS_Question_Bank.xlsx` (+ `archive/`), `data/applicability_rules.yaml`, `data/cities/ASICS_Cities_and_Parastatals.xlsx` (the register), the team's templates in `scoring/2027/templates/`, `scoring/2027/assignments/…Assignments.xlsx`.

**Category settings** (`agent_setup/categories/<category>.md`): question bank, scoring templates, agents, and (new) `law_cutoff` and `undated_law_policy`.

**Settings** (`.env`, template `.env.example`): `ANTHROPIC_API_KEY`; `ASICS_MODEL`, `ASICS_EFFORT`, `ASICS_ENABLE_FALLBACKS`; `ASICS_CATEGORY`; paths `ASICS_QUESTION_BANK`, `ASICS_CITY_REGISTER`, `ASICS_OUTPUTS_DIR`, `ASICS_AGENT_SETUP_DIR`, `ASICS_SCORING_DIR`; limits `ASICS_MAX_CONCURRENCY`, `ASICS_CHECK_WORKERS`, `ASICS_HTTP_TIMEOUT`, `ASICS_LLM_CALL_TIMEOUT`, `ASICS_API_READ_TIMEOUT`, `ASICS_MAX_EVIDENCE_CHARS`, `ASICS_ASSESS_EVIDENCE_CHARS`, `ASICS_MEMORY_MAX_CHARS`, `ASICS_FIND_SOURCES_MAX_USES`; Step 2 batching `ASICS_STEP2_BATCH`, `ASICS_STEP2_BATCH_LIVE_UP_TO`; `ASICS_HOSTED`; `ASICS_COMPARE_MIN_ROWS` (script only); `LANGSMITH_*` (tracing).

**Scripts** (`scripts/`): `run_pipeline.py` (Step 1/2), `scoring.py` (check, prepare, merge, ai), `compare_human_ai.py`, `build_question_bank.py`, `make_scoring_skeleton.py` (ULG draft workbook), `create_city_register.py`, `recheck_links.py`, `tidy_outputs.py`, `date_citation_sheets.py` (new: dates old Citation Sheets into copies).

**Data flow**

```
City register ──> Step 1 (find parastatals + sources) ──> Sources workbook (Citation Sheet,
                                                              with Effective date + Cut-off check)
                                                              │
                                                              ▼
                  Question bank ───────────────────> Step 2 (answers) ──> Answers workbook
                       (a Law/Policy question only sees sources in force by the cut-off)
                                                              │
                              team templates (UPD/SC/DPG) ──> Step 3 AI ──> scoring/2027/ai/PARASTATAL_<SECTION>_AI.xlsx

People fill templates ──> Upload + preview ──> Save (immutable submission) ──> Merge ──> scoring/2027/merged/PARASTATAL_<SECTION>_human.xlsx

AI workbooks + people's merged workbooks ──> Scores page (Consolidated / Compare / Files) ──> compare workbook
```

---

## 4. Folder structure

"Git" = tracked now. "Private?" = holds data that must not be public. [V] for tracking.

| Folder | What is in it | Written by | Git | Private? | Safe to delete? |
|---|---|---|---|---|---|
| `.env` | API keys and settings | person | **ignored** | **Yes: API key** | No (copy `.env.example` to rebuild) |
| `.venv/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/` | tools and caches | tools | ignored | No | Yes |
| `agent_setup/` | agents, prompts, skills, memory notes, category files | person | tracked | Team notes are internal (memory) | No |
| `data/` | question bank, rules, city register | person + code | tracked | Register is internal | No |
| `docs/` | design notes, source prompts, `reference/` (team's pilot workbook), `AI_COVERAGE.csv` | person + code | tracked | `reference/` is team-internal | Only generated files |
| `src/`, `tests/`, `scripts/`, `*.py` pages | code | developer | tracked | No | No |
| `scoring/2027/templates/` | team's three templates, old workbooks, `archive/`, `older/` | person | tracked | Team-internal | No |
| `scoring/2027/assignments/` | assignments workbook (intern names later) | person + code | tracked | **Names of interns** | No |
| `scoring/2027/ai/` | AI workbooks, run logs, `history/`, `archive/` (old Parastatal) | code | tracked (28 old files) + new | Internal | `archive/` and old logs: yes after a backup |
| `scoring/2027/human/…/submissions/`, `copies/` | uploaded people's files, intern copies | code (from uploads) | **will be tracked** | **Yes: scorer and uploader names** | **No: never** (originals) |
| `scoring/2027/merged/` | merged people's workbooks | code | will be tracked | Names (in records) | Yes (rebuilt) |
| `scoring/2027/results/`, `compare/`, `evals/` | results, compare workbooks, agreement history | code | tracked / not yet created | Internal | Yes except `evals` history |
| `scoring/2027/.cache/`, `practice/` | LibreOffice temp files; practice runs | code | ignored | No | Yes |
| `outputs/Parastatal/cities/<City>/` | Sources workbook (+ `_Sources_dated.xlsx` copy from the script, uncommitted), `answers/<run>/`, `evidence/`, `history/`, `links.db`, `checks/` | code | tracked (472 files) | Saved public pages; internal work | Only `history/` after a backup |
| `outputs/UPD/`, `outputs/cities/` | **old layouts** (ULG and earlier) | code (old) | tracked | Internal | Not before `tidy_outputs.py` and a backup |
| `outputs/_app/` | cost records, error log, last choices | app | tracked | Error log may show paths [A] | Yes |

Size: `outputs/` is about 556 MB (595 files, saved PDFs and pages) [V].

---

## 5. Prompts

The AI is steered by text files in `agent_setup/`. This is the short version. **What each one says, which rules the code enforces, where they disagree, and the file fingerprints are in [docs/PROMPT_GUIDE.md](PROMPT_GUIDE.md).**

| Prompt in plain words | Step | What it does in one line | Status |
|---|---|---|---|
| Rules for every parastatal task | 1, 2, 3 | The rulebook every AI call starts with: evidence, links, methodology first, the cut-off | Updated 11 Nov |
| Rules for every city (ULG) task | 1, 2, 3 | The same rulebook for the city government; the cut-off applies only if a date is set | Updated 11 Nov |
| Find the parastatals of a city | 1 | Finds the agencies that serve a city and says which look eligible | Up to date |
| Profile one parastatal | 1 | Finds its Act, status, chief executive, budget and official website | Updated 11 Nov |
| Profile the city government | 1 | The same for the city government | Up to date |
| Find sources for a parastatal | 1 | Builds its list of official sources (the Citation Sheet) | Updated 11 Nov |
| Find sources for a city | 1 | The same for the city government | Up to date |
| Judge one source | 1 | Reads one source, scores its authority, notes its effective date and whether it is a Bill | Updated 11 Nov |
| Answer a question for a parastatal | 2 | Answers one question from the Citation Sheet only, quoting the source | Updated 11 Nov |
| Answer a question for the city | 2 | The same for the city government, once per city | Updated 11 Nov |
| Score a question | 3 | Fills the team's UPD, SC or DPG template cells for one question (rules 8 and 13 overlap) | Needs update |
| Review the question bank | 0 (optional) | Spots problems in the question bank when asked | Up to date |
| Skills: scoring method and the UPD, SC and DPG guides | 2, 3 | Help notes for answering and scoring; the methodology always wins | Updated 11 Nov |
| Skills: government websites, India Code, ULG planning | 1, 2 | Help notes on finding and reading official sources | Up to date |
| Agent files (10) | all | Say which prompt, skills, tools and model each agent uses | Needs update |
| Tool descriptions (6) | 1, 2, 3 | Tell the AI what each tool does | Up to date |
| Team memory notes | 1, 2 | The research team's notes on cities and scope | Needs update |
| Category settings: Parastatal | all | Question bank, templates, cut-off date | Updated 11 Nov |
| Category settings: ULG | all | Same for the ULG; still points to the old UPD workbook | Needs update |

The team's original Phase 1 and Phase 2 prompts (`docs/source_prompts/`) are history. The app does not read them.

---

## 6. What happens after each run

Default costs are the app's own estimates in `costs.py`: Step 1 $2.60 per parastatal, Step 2 $0.076 per answer, Step 3 $0.029 per row [V]. They are defaults only [A]: no real cost record exists yet.

| Action | What is read | Files created, changed, or never touched | History / backup | Next for a person | Time and cost | What can go wrong |
|---|---|---|---|---|---|---|
| **Step 1 run** (Step 1 page or Run steps) | Register, bank, prompts, the web | Creates/changes `outputs/Parastatal/cities/<City>/ASICS_<City>_Sources.xlsx` (the Citation Sheet now also gets Effective / As-of Date and Cut-off Check for each source the assessor read), `links.db`, `evidence/`, `sources_summary.json` (records the cut-off); updates `outputs/START_HERE.xlsx`. Never touches `answers/` or `scoring/`. | Old Sources workbook copied to `history/…_Sources_<stamp>.xlsx` | Review the parastatal list and sources; edit in Excel | Minutes per parastatal (README); about $2.60 each [A] | Sites block fetching (save pages by hand); a stuck run (README: tell the team after 20 minutes) |
| **Step 2 run** | Sources workbook, bank, prompts | Creates `answers/<run-id>/ASICS_Parastatal_<City>_Phase2.xlsx`, `run_summary.json` (records the cut-off), `links.db`. For a Law/Policy question it hides later sources and Bills; may give `PENDING FETCH:`. Never edits the Sources workbook. | Every run keeps its own folder | Review answers | About $0.076 per answer; batch mode is half price but slower (`batch.py`) [A] | Old answers on the old bank are not valid for the new bank |
| **Step 3 AI run** | Latest Step 2 answers, Citation Sheet, templates | Creates/updates `scoring/2027/ai/PARASTATAL_<SECTION>_AI.xlsx` and `.ai_info.json` (records the cut-off); leaves a row for a person if its Law/Policy source is later, a Bill or blocked; `ai/runs/PARASTATAL_<SECTION>_<run>.jsonl`; `ai/scored_cities.json`. **Never writes to `human/` or `merged/`.** | Previous file copied to `ai/history/` (last 10) | Review "left for a person" rows; run Compare | About $0.029 per row [A]; seconds per file to recalculate | No LibreOffice → scores calculate only when opened in Excel; Step 2 not ready for the city |
| **People's upload: preview** | The uploaded file (in memory) | Writes nothing | n/a | Read the preview, choose names | Seconds | Wrong template, formulas with no saved value, unknown names |
| **People's upload: Save** | Same, plus bank and register | Creates `scoring/2027/human/parastatal/<SECTION>/submissions/<time>_<scorer>_<hash8>.xlsx`, `.json`, `index.json`. Never edits an earlier file. | The files are the history | Press Merge | Seconds | Same file twice (detected); scorer name typed wrong |
| **Merge and calculate** | All submissions of the category, register, template | Rebuilds `scoring/2027/merged/PARASTATAL_<SECTION>_human.xlsx` and `.merge_info.json`. Never touches submissions. | None: it is rebuilt each time | Fix "Needs a look" (conflicts) and upload again | Seconds per section; LibreOffice measured 1.3–1.9 s on blank templates [A for real size] | Two scorers disagree (row left blank); half-filled calculated rows left out |
| **Make interns' copies** | Assignments workbook, Step 2 evidence, templates | Creates `…/human/parastatal/<SECTION>/copies/<Intern>.xlsx`. Never replaces an existing copy. Uploading a new assignments workbook saves the old one in `assignments/history/`. | Old assignments kept | Send copies to interns; upload their returns | Seconds per copy | City not ready (Step 2); no assignment rows |
| **Compare / Scores refresh** | Merged and AI workbooks, Step 2 answers | Writes `scoring/2027/compare/<City>_human_vs_ai.xlsx` when the Files tab is shown; temp copies in `scoring/2027/.cache/`. Does not change the other files. | Overwritten each time | Read differences | Seconds | Merge not run yet (the page says so) |
| **Register edit** (Other name) | The register | Edits one cell in `data/cities/ASICS_Cities_and_Parastatals.xlsx` | Copy in `data/cities/history/<stamp>_…xlsx` | None | Instant | Register open in Excel; the code restores the copy if it would not load |
| **Date old Citation Sheets** (`scripts/date_citation_sheets.py`) | An existing Sources workbook (status text and title only) | Creates `ASICS_<City>_Sources_dated.xlsx` beside it, never the original, never over an existing copy | The original is the backup | Check the dated copy; fill gaps by hand; use it as the Sources workbook if wanted | Seconds, free | Year-only dates stay unknown on purpose; the text reader can miss a date |
| **Name resolution** | Names in the file, register | Saves choices in the submission's `.json`; builds the "Names to add" list (writes nothing) | `decision_history` in the sidecar | Add names to the register by hand | Instant | Wrong mapping; changeable later |

---

## 7. Golden data: how it would plug in

**Already there.**
- Compare per city: status, difference, same source link (`scoring/compare.py`) [V][T].
- An agreement calculation and an evals history workbook `scoring/2027/evals/ASICS_2027_AI_Evals.xlsx` (`scores.agreement`, `add_eval_history`) [V]. It runs only for the **old ULG path**. It is not wired to the new templates [V].
- Submissions with scorer, hashes, bank version and template hash; AI files with model, prompt fingerprint and bank version [V][T].
- A minimum of 20 compared rows before a percentage shows [V].

**Missing** [V: searched the code].
- An approved / golden status. Nothing in the code marks a row approved. A design is written in `docs/DB_DESIGN.md` (not built).
- A way to choose golden cities, and to split them into examples and test-only.
- Giving examples to the scorer. `score-question.md` has no example section.
- Comparing the AI's citations with the team's links beyond "same URL" (chapter, provision and quote are not compared).
- A per-question agreement report across cities, for the new templates.

**Recommended order (5 small steps).**
1. Real run on one golden city: Step 2 on the new bank, then Step 3, then a real filled template. This finds what breaks.
2. Add the approval marker (the append-only review file in `docs/DB_DESIGN.md`).
3. Add a small list of golden cities, marked "example" or "test only".
4. Per-question agreement report across the golden cities (extend Compare and the evals workbook to the templates).
5. Give 2–3 approved examples of weak questions to the scorer, keep the test cities hidden, and re-measure.

---

## 8. Risks and open questions (most important first)

1. **Nothing has run on real data with the new bank.** Real answers are from 12–13 Oct on the old bank, and the real model has never filled the new Citation Sheet columns. *Decide:* when to re-run Steps 1 and 2 and who pays. (Program team + developer)
2. **The repo is public and now holds 556 MB of outputs.** Making it private does not erase history, clones or forks. People's names will join later. *Decide:* keep outputs in git, or move them. (To assign: Anita / Pradeep)
3. **The cut-off has thin data.** Only 25 of Bengaluru's 68 and 14 of Surat's 31 legal citations have a real date, so many Law/Policy answers will carry CONFIRM or PENDING FETCH until dated versions are saved. Bengaluru's old answers lean on 17 Bills. The memory notes are still unchecked. *Decide:* who saves the dated versions, and the open questions from the program team (undated Acts, website pages, year-only dates). (Program team)
4. **UPD 1a / 1b scale.** Methodology says 10 / 2.5 / 0, Max Score 5. We accept 5 / 2.5 / 0. The middle level could mean 2.5 or 1.25. (Program team)
5. **SC 1, 2, 3, 11 apply only to some parastatals** by the register's flags, but the templates count them for all types. Roll-ups show "Partial". (Program team)
6. **Golden set may be small.** A few cities give a small test set. Examples could leak into the test. *Decide:* how many cities and how to split. (Program team)
7. **No database, files in git.** Two people uploading at once or git merge conflicts are untested. The scorer name is typed, with no login. (Developer; hosting owner to assign)
8. **A delivered file was never opened in desktop Excel,** and merge needs LibreOffice on the host. (Developer, with a team member to open one)
9. **The AI leaves 4 of 52 questions for people** (SC 2, 12a, 12b, DPG 4), and the ULG is still on the old 96-question workbook with no SC or DPG. (Program team)
10. **Cost and time are guesses.** Defaults only; the usage records are empty. (Developer; program team approves budget)

---

## 9. Next 5 steps

1. **Review and commit the 11 Nov work** (cut-off and methodology), then push; decide the private-repo question first. *Small.*
2. **Check the memory notes and the ULG category** against the new rules (they were not touched). *Small.*
3. **Real-data test:** one city (Bengaluru): Step 1 (fills the new columns for real), Step 2 on the new bank, Step 3 AI, read the files, open one in Excel. Save dated versions where an answer says PENDING FETCH. *Medium.*
4. **First real people's file:** upload, preview, merge, compare against the AI. Fix what breaks. *Small to medium.*
5. **Golden-data basics:** approval marker, golden city list, per-question agreement report (section 7, steps 2–4). *Medium to large.*

---

*Not verified (summary):* how well the real model fills the effective date and form; whether the Run steps page shows the cut-off line when rendered (only its text is tested); who added the A1/A2 columns and when; the real size and time of a merge; real cost; whether the model behaves on the new prompts; every Open-versus-Download button pair on Steps 1 and 2; the contents of the memory notes beyond their first lines; the roles of Anita and Pradeep.
